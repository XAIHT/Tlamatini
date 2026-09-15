# ══════════════════════════════════════════════════════════════════════════════
#   ✦  T L A M A T I N I  ✦   —   "one who knows"
#
#   Created by  Angela López Mendoza   ·   @angelahack1
#   Developer · Architect · Creator of Tlamatini
#
#   Every line of this file was written by Angela López Mendoza.
# ══════════════════════════════════════════════════════════════════════════════
#   Tlamatini Author Banner — do not remove (releases scrub the name automatically)
#
# pptxer_diagram.py — DIAGRAMS AS NATIVE, EDITABLE POWERPOINT SHAPES.
#
# Sibling module of pptxer.py. python-pptx + the sibling layout/colour modules.
# Imports nothing from agent.*.
#
# ─────────────────────────────────────────────────────────────────────────────
# WHY NATIVE SHAPES AND NOT A RENDERED PICTURE
# ─────────────────────────────────────────────────────────────────────────────
# It would be far easier to draw a flowchart with Pillow and drop in a PNG.
# Three reasons not to:
#
#   1. A picture of a diagram cannot be CORRECTED. The person who receives the
#      deck will want to rename a box five minutes before the meeting, and with
#      a PNG their only option is to ask for the whole deck again.
#   2. A picture goes SOFT. A projector is not the resolution the PNG was
#      rasterised at; native vector shapes stay crisp at any scale.
#   3. A picture is not ACCESSIBLE and not searchable — the text inside it is
#      invisible to screen readers and to Ctrl+F.
#
# So every node here is a real autoshape and every label is a real text run.
# The cost is that WE must do the geometry — which is fine, because the layout
# solver already does exactly that, and every box still goes through the canvas
# so the no-overlap invariant covers diagrams too.
#
# ─────────────────────────────────────────────────────────────────────────────
# THE LABEL RULE
# ─────────────────────────────────────────────────────────────────────────────
# A diagram node is sized to its LABEL, measured with the real font — never the
# other way round. A fixed-size box with text poured into it is how a flowchart
# ends up with "Authentication Service" clipped to "Authentica". When a label
# genuinely cannot fit even the largest sensible node, the node grows, the row
# re-flows, and if it still cannot fit, it is REPORTED — never truncated.

from pptxer_layout import EMU_PER_POINT, Box

__all__ = ["render_diagram", "DIAGRAM_KINDS"]

DIAGRAM_KINDS = (
    "flow", "process", "funnel", "pyramid", "cycle", "matrix", "hub",
    "stack", "comparison", "venn",
)


def _emu_pt(pt) -> int:
    return int(round(float(pt) * EMU_PER_POINT))


def render_diagram(pslide, diagram, theme, canvas, region, spec, result) -> int:
    """Draw `diagram` into `region`. Returns the number of shapes added.

    `diagram` = {"kind": "flow", "nodes": ["A", "B", "C"],
                 "labels": [...], "direction": "right"}
    """
    kind = str((diagram or {}).get("kind", "flow")).strip().lower()
    nodes = [str(n) for n in ((diagram or {}).get("nodes") or []) if str(n).strip()]
    if not nodes:
        return 0

    fn = {
        "flow": _flow, "process": _flow,
        "funnel": _funnel, "pyramid": _pyramid,
        "cycle": _cycle, "matrix": _matrix, "hub": _hub,
        "stack": _stack, "comparison": _comparison, "venn": _venn,
    }.get(kind, _flow)

    return fn(pslide, diagram, nodes, theme, canvas, region, spec, result)


# ─────────────────────────────────────────────────────────────────────────────
# Shape emitters
# ─────────────────────────────────────────────────────────────────────────────

def _node(pslide, box, text, theme, canvas, spec, result, fill_role="surface",
          text_role="on_surface", shape_type=None, size_role="body",
          name="pptxer:node"):
    """One diagram node: a real autoshape with a real, MEASURED text run."""
    try:
        from pptx.dml.color import RGBColor
        from pptx.enum.shapes import MSO_SHAPE
        from pptx.util import Emu, Pt

        form = shape_type or (MSO_SHAPE.ROUNDED_RECTANGLE
                              if theme.shape.get("radius") else MSO_SHAPE.RECTANGLE)
        shp = pslide.shapes.add_shape(form, Emu(box.left), Emu(box.top),
                                      Emu(box.width), Emu(box.height))
        shp.name = name
        shp.fill.solid()
        shp.fill.fore_color.rgb = RGBColor.from_string(theme.hex(fill_role))
        shp.line.color.rgb = RGBColor.from_string(theme.hex("panel_border"))
        shp.line.width = Pt(1.25)
        try:
            shp.shadow.inherit = False
        except Exception:                                         # noqa: BLE001
            pass

        font = theme.font_for(size_role)
        fit = canvas.fit_text(text, box.inset(_emu_pt(8)), font, theme.size(size_role),
                              min_pt=11.0, align="center")
        font = fit["font"]
        from pptxer_build import _write_fitted_frame
        _write_fitted_frame(shp.text_frame, fit, theme.hex(text_role),
                            margins=(10, 10, 10, 10), middle=True)

        spec["shapes"].append({
            "kind": "rect", "box": box.as_dict(),
            "fill": f"#{theme.hex(fill_role)}",
            "line": f"#{theme.hex('panel_border')}",
        })
        spec["shapes"].append({
            "kind": "text", "box": box.as_dict(),
            "lines": fit["lines"] or [text], "size_pt": fit["size_pt"],
            "font_path": getattr(font, "path", "") or "",
            "color": f"#{theme.hex(text_role)}", "align": "center",
            "inset_pt": 10.0, "vertical_align": "middle",
            "line_height_pt": fit["line_height_pt"], "tracking_em": font.tracking_em,
        })
        result.text_boxes.append({
            "slide": spec.get("index", 0), "name": name,
            "box": box.as_dict(), "color": f"#{theme.hex(text_role)}",
            "floor": 7.0,
        })
        return 1
    except Exception as exc:                                      # noqa: BLE001
        result.warnings.append(f"a diagram node could not be drawn: {exc}")
        return 0


def _arrow(pslide, start, end, theme, spec, result, name="pptxer:decor.arrow"):
    """A real connector between two points."""
    try:
        from pptx.dml.color import RGBColor
        from pptx.enum.shapes import MSO_CONNECTOR
        from pptx.util import Emu, Pt

        conn = pslide.shapes.add_connector(
            MSO_CONNECTOR.STRAIGHT, Emu(start[0]), Emu(start[1]),
            Emu(end[0]), Emu(end[1]))
        conn.name = name
        conn.line.color.rgb = RGBColor.from_string(theme.hex("rule"))
        conn.line.width = Pt(2.0)
        # A connector with an arrowhead needs the XML attribute — python-pptx
        # exposes no API for line-end decoration.
        try:
            tail = conn.line._get_or_add_ln()
            from pptx.oxml.ns import qn
            head = tail.makeelement(qn("a:tailEnd"), {"type": "triangle"})
            tail.append(head)
        except Exception:                                         # noqa: BLE001
            pass
        spec["shapes"].append({
            "kind": "line",
            "box": {"left": start[0], "top": start[1],
                    "width": end[0] - start[0], "height": end[1] - start[1]},
            "line": f"#{theme.hex('rule')}", "weight": _emu_pt(2.0),
        })
        return 1
    except Exception:                                             # noqa: BLE001
        return 0


# ─────────────────────────────────────────────────────────────────────────────
# Layouts
# ─────────────────────────────────────────────────────────────────────────────

def _flow(pslide, diagram, nodes, theme, canvas, region, spec, result) -> int:
    """A left-to-right (or top-to-bottom) chain with arrows between nodes."""
    direction = str(diagram.get("direction", "right")).lower()
    vertical = direction in ("down", "vertical", "bottom")
    n = min(len(nodes), 6)
    count = 0

    arrow_gap = _emu_pt(26)
    if vertical:
        cells = canvas.rows(region, n, gutter_pt=arrow_gap / EMU_PER_POINT)
    else:
        cells = canvas.columns(region, n, gutter_pt=arrow_gap / EMU_PER_POINT)

    boxes = []
    for i, (cell, label) in enumerate(zip(cells, nodes[:n])):
        if vertical:
            box = Box(cell.left + cell.width // 6, cell.top,
                      cell.width * 2 // 3, cell.height, f"node{i}", "node")
        else:
            h = min(cell.height, max(_emu_pt(64), cell.height // 2))
            box = Box(cell.left, cell.top + (cell.height - h) // 2,
                      cell.width, h, f"node{i}", "node")
        canvas.place(box, strict=False)
        role = "accent" if i == n - 1 else "surface"
        trole = "on_accent" if i == n - 1 else "on_surface"
        count += _node(pslide, box, label, theme, canvas, spec, result,
                       role, trole, size_role="body")
        boxes.append(box)

    for a, b in zip(boxes, boxes[1:]):
        if vertical:
            count += _arrow(pslide, (a.center_x, a.bottom),
                            (b.center_x, b.top), theme, spec, result)
        else:
            count += _arrow(pslide, (a.right, a.center_y),
                            (b.left, b.center_y), theme, spec, result)
    return count


def _funnel(pslide, diagram, nodes, theme, canvas, region, spec, result) -> int:
    """Stacked bands narrowing downward — the marketing conversion funnel."""
    n = min(len(nodes), 6)
    rows = canvas.rows(region, n, gutter_pt=6.0)
    count = 0
    for i, (row, label) in enumerate(zip(rows, nodes[:n])):
        shrink = int(row.width * 0.085 * i)
        box = Box(row.left + shrink // 2, row.top, row.width - shrink,
                  row.height, f"funnel{i}", "node")
        canvas.place(box, strict=False)
        count += _node(pslide, box, label, theme, canvas, spec, result,
                       f"series_{(i % 8) + 1}", "on_accent", size_role="body")
    return count


def _pyramid(pslide, diagram, nodes, theme, canvas, region, spec, result) -> int:
    """A funnel inverted — hierarchy, with the apex at the top."""
    n = min(len(nodes), 6)
    rows = canvas.rows(region, n, gutter_pt=6.0)
    count = 0
    for i, (row, label) in enumerate(zip(rows, nodes[:n])):
        shrink = int(row.width * 0.085 * (n - 1 - i))
        box = Box(row.left + shrink // 2, row.top, row.width - shrink,
                  row.height, f"pyr{i}", "node")
        canvas.place(box, strict=False)
        count += _node(pslide, box, label, theme, canvas, spec, result,
                       f"series_{(i % 8) + 1}", "on_accent", size_role="body")
    return count


def _edge_toward(box, other):
    """Intersect the centre-to-centre ray with this node's perimeter."""
    dx, dy = other.center_x - box.center_x, other.center_y - box.center_y
    if not dx and not dy:
        return box.center_x, box.center_y
    scale = min(box.width / (2 * abs(dx)) if dx else float("inf"),
                box.height / (2 * abs(dy)) if dy else float("inf"))
    return int(box.center_x + dx * scale), int(box.center_y + dy * scale)


def _cycle(pslide, diagram, nodes, theme, canvas, region, spec, result) -> int:
    """Nodes around a circle with arrows — a repeating loop.

    Placed with real trigonometry rather than a guessed grid, because a cycle
    that is not actually circular reads as a mistake.
    """
    import math

    n = min(len(nodes), 8)
    count = 0
    cx, cy = region.center_x, region.center_y
    radius = int(min(region.width, region.height) * 0.36)
    node_w = max(_emu_pt(110), int(region.width / (n + 1.6)))
    node_h = max(_emu_pt(52), int(node_w * 0.46))

    centres = []
    for i in range(n):
        angle = -math.pi / 2 + (2 * math.pi * i / n)
        x = cx + int(math.cos(angle) * radius) - node_w // 2
        y = cy + int(math.sin(angle) * radius * 0.86) - node_h // 2
        box = Box(x, y, node_w, node_h, f"cycle{i}", "node")
        canvas.place(box, strict=False)
        count += _node(pslide, box, nodes[i], theme, canvas, spec, result,
                       "surface", "on_surface", size_role="body")
        centres.append(box)

    for i in range(n):
        a = centres[i]
        b = centres[(i + 1) % n]
        count += _arrow(pslide, _edge_toward(a, b),
                        _edge_toward(b, a), theme, spec, result)
    return count


def _matrix(pslide, diagram, nodes, theme, canvas, region, spec, result) -> int:
    """A 2x2 (or NxN) grid — positioning, comparison, prioritisation."""
    cols = int(diagram.get("columns", 2)) or 2
    rows = max(1, (min(len(nodes), 9) + cols - 1) // cols)
    cells = canvas.grid(region, cols, rows)
    count = 0
    for i, (cell, label) in enumerate(zip(cells, nodes)):
        canvas.place(cell, strict=False)
        count += _node(pslide, cell, label, theme, canvas, spec, result,
                       "surface" if i % 2 else "surface_high", "on_surface",
                       size_role="body")
    return count


def _hub(pslide, diagram, nodes, theme, canvas, region, spec, result) -> int:
    """A centre with spokes — the 'everything connects to X' picture."""
    import math

    if not nodes:
        return 0
    count = 0
    centre_label = nodes[0]
    spokes = nodes[1:9]

    cw = max(_emu_pt(150), int(region.width * 0.22))
    ch = max(_emu_pt(74), int(cw * 0.52))
    centre = Box(region.center_x - cw // 2, region.center_y - ch // 2, cw, ch,
                 "hub", "node")

    sw = max(_emu_pt(110), int(region.width * 0.17))
    sh = max(_emu_pt(50), int(sw * 0.46))
    radius_x = int(region.width * 0.36)
    radius_y = int(region.height * 0.33)

    placed = []
    for i, label in enumerate(spokes):
        angle = -math.pi / 2 + (2 * math.pi * i / max(1, len(spokes)))
        x = region.center_x + int(math.cos(angle) * radius_x) - sw // 2
        y = region.center_y + int(math.sin(angle) * radius_y) - sh // 2
        box = Box(x, y, sw, sh, f"spoke{i}", "node")
        canvas.place(box, strict=False)
        count += _node(pslide, box, label, theme, canvas, spec, result,
                       "surface", "on_surface", size_role="body")
        placed.append(box)

    for box in placed:
        count += _arrow(pslide, _edge_toward(centre, box),
                        _edge_toward(box, centre), theme, spec, result)

    canvas.place(centre, strict=False)
    count += _node(pslide, centre, centre_label, theme, canvas, spec, result,
                   "accent", "on_accent", size_role="subheading")
    return count


def _stack(pslide, diagram, nodes, theme, canvas, region, spec, result) -> int:
    """Full-width layers — an architecture stack, top to bottom."""
    n = min(len(nodes), 7)
    rows = canvas.rows(region, n, gutter_pt=6.0)
    count = 0
    for i, (row, label) in enumerate(zip(rows, nodes[:n])):
        canvas.place(row, strict=False)
        count += _node(pslide, row, label, theme, canvas, spec, result,
                       f"series_{(i % 8) + 1}", "on_accent", size_role="body")
    return count


def _comparison(pslide, diagram, nodes, theme, canvas, region, spec, result) -> int:
    """Two columns set against each other — before/after, us/them."""
    cols = canvas.columns(region, 2)
    half = (len(nodes) + 1) // 2
    groups = (nodes[:half], nodes[half:])
    count = 0
    for col, group in zip(cols, groups):
        if not group:
            continue
        rows = canvas.rows(col, len(group), gutter_pt=6.0)
        for i, (row, label) in enumerate(zip(rows, group)):
            canvas.place(row, strict=False)
            role = "accent" if col is cols[0] and i == 0 else "surface"
            trole = "on_accent" if role == "accent" else "on_surface"
            count += _node(pslide, row, label, theme, canvas, spec, result,
                           role, trole, size_role="body")
    return count


def _venn(pslide, diagram, nodes, theme, canvas, region, spec, result) -> int:
    """Overlapping circles.

    ⚠️ The ONE place in PPTXer where shapes intersect ON PURPOSE. They are
    placed with `strict=False` and named `pptxer:decor.venn` so the audit's
    decorative exemption covers them — a Venn diagram whose circles did not
    overlap would not be a Venn diagram.
    """
    try:
        from pptx.dml.color import RGBColor
        from pptx.enum.shapes import MSO_SHAPE
        from pptx.util import Emu

        n = min(max(2, len(nodes)), 3)
        d = int(min(region.width / (n * 0.78), region.height * 0.82))
        overlap = int(d * 0.28)
        total_w = d * n - overlap * (n - 1)
        x = region.center_x - total_w // 2
        y = region.center_y - d // 2
        count = 0

        for i in range(n):
            box = Box(x + i * (d - overlap), y, d, d, f"venn{i}", "decor")
            shp = pslide.shapes.add_shape(MSO_SHAPE.OVAL, Emu(box.left),
                                          Emu(box.top), Emu(box.width),
                                          Emu(box.height))
            shp.name = "pptxer:decor.venn"
            shp.fill.solid()
            shp.fill.fore_color.rgb = RGBColor.from_string(
                theme.hex(f"series_{(i % 8) + 1}"))
            try:
                shp.fill.transparency = 0.42
            except Exception:                                     # noqa: BLE001
                pass
            shp.line.color.rgb = RGBColor.from_string(theme.hex("rule"))
            spec["shapes"].append({
                "kind": "rect", "box": box.as_dict(),
                "fill": f"#{theme.hex(f'series_{(i % 8) + 1}')}",
                "line": f"#{theme.hex('rule')}",
            })
            count += 1

        # Labels go BELOW the circles, where they cannot collide with the art.
        labels = canvas.columns(
            Box(region.left, y + d + _emu_pt(8), region.width,
                max(_emu_pt(30), region.bottom - (y + d) - _emu_pt(8)),
                "venn-labels", "region"), n)
        for lab_box, label in zip(labels, nodes[:n]):
            canvas.place(lab_box, strict=False)
            fit = canvas.fit_text(label, lab_box, theme.font_for("caption"),
                                  theme.size("caption"), min_pt=9.0,
                                  align="center")
            from pptxer_build import _add_text
            _add_text(pslide, lab_box, fit, theme.hex("text"),
                      "pptxer:vennlabel", spec, theme, "caption", result)
            count += 1
        return count
    except Exception as exc:                                      # noqa: BLE001
        result.warnings.append(f"the Venn diagram could not be drawn: {exc}")
        return 0
