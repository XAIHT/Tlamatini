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
# pptxer_build.py — THE ASSEMBLY ENGINE.  Deck model + Theme → a real .pptx.
#
# Sibling module of pptxer.py. python-pptx + Pillow + the sibling modules.
# Imports nothing from agent.*.
#
# ═════════════════════════════════════════════════════════════════════════════
#  THE ONE RULE THIS MODULE OBEYS
# ═════════════════════════════════════════════════════════════════════════════
#     EVERY SHAPE IS PLACED THROUGH THE SlideCanvas, AND THE CANVAS REFUSES
#     A PLACEMENT THAT WOULD OVERLAP OR LEAVE THE SAFE AREA.
#
# python-pptx does no layout whatsoever — it writes exactly the EMU numbers it
# is given. That is a gift, not a limitation: it means overlap is not a bug to
# detect afterwards but a state that can be made UNREACHABLE. Nothing in this
# module computes a position by hand; every box comes from the solver.
#
# ─────────────────────────────────────────────────────────────────────────────
# WHY AUTOFIT IS OFF EVERYWHERE
# ─────────────────────────────────────────────────────────────────────────────
# PowerPoint's "shrink text on overflow" is applied by the VIEWER, using the
# viewer's fonts, and the resulting size is never written to the file. A deck
# that leans on it renders differently on every machine and cannot be audited
# at all. PPTXer therefore SOLVES the size with real font metrics and writes an
# explicit one — `auto_size = NONE`, always.
#
# ─────────────────────────────────────────────────────────────────────────────
# SHAPE NAMES ARE LOAD-BEARING
# ─────────────────────────────────────────────────────────────────────────────
# Every shape is named `pptxer:<role>`. The name is the only metadata that
# survives save → reopen, so it is how the audit tells a deliberate full-bleed
# background from a content box that escaped its margin. Renaming these breaks
# the audit silently; add a role, never repurpose one.

import os

from pptxer_draw import compose_background, draw_scrim, make_seed
from pptxer_layout import (
    EMU_PER_POINT,
    Box,
    GridSolver,
    PlacementError,
    SlideCanvas,
    fit_image_box,
    solve_columns,
)

__all__ = ["build_deck", "BuildResult"]

# Roles used in shape names. The audit's _BLEED_MARKERS / _DECOR_MARKERS match
# on these, so the two modules must agree.
R_BLEED = "pptxer:bleed"
R_BACKGROUND = "pptxer:background"
R_SCRIM = "pptxer:scrim"
R_ORNAMENT = "pptxer:ornament"
R_GLOW = "pptxer:glow"


class BuildResult:
    """Everything the build produced, including what it could not do."""

    def __init__(self):
        self.path = ""
        self.slide_count = 0
        self.shape_count = 0
        self.images_embedded = 0
        self.videos_embedded = 0
        self.audio_embedded = 0
        self.tables = 0
        self.charts = 0
        self.diagrams = 0
        self.generated_art = 0
        self.warnings = []
        self.placement_diagnostics = []
        self.slide_specs = []      # for the geometric preview renderer
        self.text_boxes = []       # for the rendered-contrast audit
        self.media_failures = []
        self.ok = False
        self.error = ""

    def as_dict(self) -> dict:
        return {
            "path": self.path, "slides": self.slide_count,
            "shapes": self.shape_count, "images": self.images_embedded,
            "videos": self.videos_embedded, "audio": self.audio_embedded,
            "tables": self.tables, "charts": self.charts,
            "diagrams": self.diagrams, "generated_art": self.generated_art,
            "warnings": self.warnings,
            "placement_diagnostics": self.placement_diagnostics,
            "media_failures": self.media_failures,
            "ok": self.ok, "error": self.error,
        }


def _emu_pt(pt) -> int:
    return int(round(float(pt) * EMU_PER_POINT))


def build_deck(deck, theme, output_path, config=None, media_index=None,
               inventory=None) -> BuildResult:
    """Assemble the whole presentation. Never raises into the caller."""
    result = BuildResult()
    cfg = config or {}
    media = media_index or {}

    try:
        from pptx import Presentation
        from pptx.util import Emu
    except Exception as exc:                                      # noqa: BLE001
        result.error = (f"python-pptx is not available ({exc}); PPTXer cannot "
                        f"write a presentation without it")
        return result

    size_name = str(cfg.get("slide_size") or "16:9").strip().lower()
    margin_pt = float(cfg.get("margin_pt") or 48.0)

    try:
        probe = SlideCanvas(size_name, margin_pt=margin_pt)
    except Exception:                                             # noqa: BLE001
        probe = SlideCanvas("16:9", margin_pt=margin_pt)

    prs = Presentation()
    prs.slide_width = Emu(probe.width)
    prs.slide_height = Emu(probe.height)

    try:
        blank_layout = prs.slide_layouts[6]
    except Exception:                                             # noqa: BLE001
        blank_layout = prs.slide_layouts[len(prs.slide_layouts) - 1]

    seed_base = make_seed(deck.title, theme.nuance, len(deck.slides))

    try:
        slides, adjustments = _paginate(deck.slides, theme, cfg, media, inventory)
        result.warnings.extend(adjustments)
    except PlacementError as exc:
        result.error = f"No readable layout could be produced: {exc}"
        return result

    for index, slide_model in enumerate(slides, start=1):
        canvas = SlideCanvas(size_name, margin_pt=margin_pt,
                             gutter_pt=theme.space("gutter") / EMU_PER_POINT,
                             inventory=inventory)
        pslide = prs.slides.add_slide(blank_layout)
        spec = {"index": index, "background": None, "shapes": []}

        try:
            _build_one(pslide, slide_model, theme, canvas, spec, result,
                       media, cfg, seed_base + index, index, len(slides))
        except Exception as exc:                                  # noqa: BLE001
            # One broken slide must never cost the deck. Report it, keep going.
            result.error = f"slide {index} ({slide_model.kind}) could not be built: {exc}"
            return result

        audit = canvas.audit()
        for diag in audit.get("diagnostics", []):
            result.placement_diagnostics.append(f"slide {index}: {diag}")
        for over in audit.get("overlaps", []):
            result.warnings.append(
                f"slide {index}: {over['a']} and {over['b']} overlap by "
                f"{over['area_pt2']:.0f}pt² — the placement solver reported it "
                f"rather than emitting it silently")

        result.slide_specs.append(spec)
        result.slide_count += 1

    try:
        core = prs.core_properties
        core.title = deck.title or "Presentation"
        core.author = str(cfg.get("author") or deck.author or "Tlamatini")
        core.comments = (f"Generated by Tlamatini PPTXer — treatment: "
                         f"{theme.nuance}")
        if deck.subtitle:
            core.subject = deck.subtitle
    except Exception:                                             # noqa: BLE001
        pass

    staging = None
    try:
        parent = os.path.dirname(output_path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        import tempfile
        with tempfile.NamedTemporaryFile(dir=parent or ".", suffix=".pptx", delete=False) as file:
            staging = file.name
        prs.save(staging)
        os.replace(staging, output_path)
        result.path = output_path
        result.ok = True
    except Exception as exc:                                      # noqa: BLE001
        result.error = f"the presentation could not be saved: {exc}"
        result.ok = False
    finally:
        if staging and os.path.isfile(staging):
            os.remove(staging)

    return result


# ─────────────────────────────────────────────────────────────────────────────
# Per-slide composition
# ─────────────────────────────────────────────────────────────────────────────

def _paginate(models, theme, cfg, media, inventory):
    """Trial-compose against real fonts and actual boxes before writing a deck.

    Split the content model when its layout cannot hold it. No failed trial
    leaks into the output, and the caller's model is never mutated.
    """
    from collections import deque
    from copy import deepcopy
    from pptx import Presentation
    from pptxer_audit import audit_shape_tree, audit_text_fit

    pending = deque((deepcopy(m), 0) for m in models)
    accepted, notes = [], []
    trial_cfg = dict(cfg, generate_art=False)
    while pending:
        model, depth = pending.popleft()
        if model.body and model.bullets and model.kind in ("bullets", "agenda", "image_left", "image_right"):
            model.bullets.insert(0, model.body)
            model.body = ""
        if depth > 20 or len(accepted) + len(pending) > 1000:
            raise PlacementError("content exceeds the pagination limit")
        probe = SlideCanvas(cfg.get("slide_size", "16:9"),
                            margin_pt=float(cfg.get("margin_pt") or 48),
                            gutter_pt=theme.space("gutter") / EMU_PER_POINT,
                            inventory=inventory)
        if model.chart and not model.meta.get("keyed_chart"):
            from pptxer_docmodel import Slide
            from pptxer_fonts import measure_text
            key_lines = []
            categories = list(model.chart.get("categories", []))
            allowance = max(30.0, probe.safe.width_pt / max(1, len(categories)) - 12)
            for i, value in enumerate(categories):
                if measure_text(str(value), theme.font_for("caption"), theme.size("caption"), inventory)[0] > allowance:
                    categories[i] = f"C{i + 1}"
                    key_lines.append(f"C{i + 1}: {value}")
            model.chart["categories"] = categories
            for i, series in enumerate(model.chart.get("series", [])):
                value = series.get("name", "")
                if measure_text(str(value), theme.font_for("caption"), theme.size("caption"), inventory)[0] > probe.safe.width_pt * 0.4:
                    series["name"] = f"Series {i + 1}"
                    key_lines.append(f"Series {i + 1}: {value}")
            model.meta["keyed_chart"] = True
            if key_lines:
                pending.appendleft((Slide(kind="bullets", title="Chart labels", bullets=key_lines,
                                          meta={"reading_layout": True}), depth))
                notes.append(f"Placed long labels for {model.title!r} in a numbered chart key")
        prs = Presentation()
        prs.slide_width, prs.slide_height = probe.width, probe.height
        slide = prs.slides.add_slide(prs.slide_layouts[6])
        spec = {"index": 1, "background": None, "shapes": []}
        trial = BuildResult()
        reason = _capacity_reason(model)
        if not reason:
            try:
                _build_one(slide, model, theme, probe, spec, trial, media,
                           trial_cfg, 0, 1, 999)
                geometry = audit_shape_tree(prs, margin_pt=float(cfg.get("margin_pt") or 48))
                fit = audit_text_fit(prs, inventory=inventory)
                errors = (geometry["overlaps"] + geometry["off_slide"]
                          + [e for e in geometry["safe_escapes"] if not e.get("decorative")]
                          + fit["overflows"])
                reason = geometry.get("error") or fit.get("error") or (str(errors[0]) if errors else "")
                if trial.warnings:
                    reason = reason or trial.warnings[0]
            except Exception as exc:
                reason = str(exc)
        if not reason:
            accepted.append(model)
            continue
        parts = _split_content(model)
        if not parts:
            raise PlacementError(f"{model.kind} {model.title[:60]!r}: {reason}")
        notes.append(f"Reflowed {model.kind} {model.title[:40]!r}: {reason}")
        pending.extendleft((part, depth + 1) for part in reversed(parts))
    return accepted, notes


def _capacity_reason(model):
    if len(model.stats) > 6 or len(model.timeline) > 6 or len(model.columns) > 3:
        return "items need continuation slides"
    if model.diagram:
        kind = model.diagram.get("kind", "flow")
        cap = {"venn": 3, "matrix": 4, "pyramid": 5}.get(kind, 6)
        if len(model.diagram.get("nodes", [])) > cap:
            return "diagram nodes need continuation slides"
    if model.kind == "gallery" and len(model.images) > 6:
        return "images need continuation slides"
    return ""


def _split_string(text):
    """Cut at a word boundary when possible, retaining every character."""
    text = str(text)
    if len(text) < 2:
        return []
    middle = len(text) // 2
    boundary = text.rfind(" ", max(1, middle // 2), middle + 1)
    cut = boundary + 1 if boundary >= 0 else middle
    return [text[:cut], text[cut:]]


def _split_content(model):
    from copy import deepcopy
    from pptxer_docmodel import Slide

    def chunks(field, values):
        middle = (len(values) + 1) // 2
        parts = [deepcopy(model), deepcopy(model)]
        for part, values_part in zip(parts, (values[:middle], values[middle:])):
            setattr(part, field, values_part)
        parts[1].meta["continuation"] = True
        return parts

    if model.diagram and not model.meta.get("node_keys"):
        nodes = model.diagram.get("nodes", [])
        if any(len(str(node)) > 60 for node in nodes) and not _capacity_reason(model):
            diagram = deepcopy(model)
            diagram.diagram["nodes"] = [str(i + 1) for i in range(len(nodes))]
            diagram.meta["node_keys"] = True
            details = Slide(kind="bullets", title="Diagram labels",
                            bullets=[f"{i + 1}: {text}" for i, text in enumerate(nodes)],
                            meta={"reading_layout": True})
            return [diagram, details]

    for field in ("stats", "timeline", "bullets"):
        values = getattr(model, field)
        if len(values) > 1:
            return chunks(field, values)
    if model.kind == "gallery" and len(model.images) > 1:
        return chunks("images", model.images)
    if len(model.columns) > 1:
        return chunks("columns", model.columns)
    if model.diagram and len(model.diagram.get("nodes", [])) > 1:
        nodes = model.diagram["nodes"]
        parts = [deepcopy(model), deepcopy(model)]
        middle = (len(nodes) + 1) // 2
        parts[0].diagram["nodes"], parts[1].diagram["nodes"] = nodes[:middle], nodes[middle:]
        parts[1].meta["continuation"] = True
        return parts
    if model.table and len(model.table.get("rows", [])) > 1:
        rows = model.table["rows"]
        parts = [deepcopy(model), deepcopy(model)]
        middle = (len(rows) + 1) // 2
        parts[0].table["rows"], parts[1].table["rows"] = rows[:middle], rows[middle:]
        parts[1].meta["continuation"] = True
        return parts
    # A single dense card, row, or unusually long heading needs a reading
    # layout. Keep the original fields visible, including labels and values.
    if not model.meta.get("reading_layout"):
        texts = [model.title, model.subtitle, model.kicker, model.body, model.quote, model.attribution]
        texts.extend(model.bullets)
        for stat in model.stats:
            texts.append(f"{stat.get('value', '')}: {stat.get('label', '')}")
        for col in model.columns:
            texts.extend([col.get("title", ""), *col.get("bullets", [])])
        for item in model.timeline:
            texts.append(f"{item.get('when', '')}: {item.get('what', '')}")
        if model.diagram:
            texts.extend(model.diagram.get("nodes", []))
        if model.table:
            headers = model.table.get("headers", [])
            for row in model.table.get("rows", []):
                texts.extend(f"{headers[c] if c < len(headers) else c + 1}: {value}"
                             for c, value in enumerate(row))
            if not model.table.get("rows"):
                texts.extend(headers)
        if model.chart:
            texts.extend(str(c) for c in model.chart.get("categories", []))
            for series in model.chart.get("series", []):
                texts.append(str(series))
        if model.code:
            # Code keeps its indentation and monospace face across pages.
            part = deepcopy(model)
            part.title = "Code (continued)" if model.meta.get("continuation") else "Code"
            part.subtitle = part.kicker = ""
            part.meta["reading_layout"] = True
            return [Slide(kind="bullets", title="Code context", bullets=[t for t in texts if t],
                          meta={"reading_layout": True}), part]
        parts = [Slide(kind="bullets", title="Details (continued)" if model.meta.get("continuation") else "Details",
                      bullets=[str(t) for t in texts if str(t).strip()],
                      notes=model.notes, meta={"reading_layout": True})]
        if model.images:
            parts.append(Slide(kind="gallery", title="Images", images=model.images))
        if model.video:
            parts.append(Slide(kind="media", video=model.video))
        return parts
    field = "code" if model.code else ("body" if model.body else "bullets")
    value = model.bullets[0] if field == "bullets" and model.bullets else getattr(model, field)
    if not isinstance(value, str):
        return []
    strings = _split_string(value)
    parts = []
    for text in strings:
        part = deepcopy(model)
        setattr(part, field, [text] if field == "bullets" else text)
        if parts:
            part.meta["continuation"] = True
        parts.append(part)
    return parts


def _build_one(pslide, model, theme, canvas, spec, result, media, cfg,
               seed, index, total):
    kind = model.kind
    canvas.footer_height = _emu_pt(theme.size("footnote") * 1.6)
    if cfg.get("footer_note"):
        canvas.footer_height = max(canvas.footer_height, canvas.text_block_height(
            f"{cfg['footer_note']} · Continued · {total} / {total}", canvas.safe.width,
            theme.font_for("footnote"), 10.0))

    _paint_background(pslide, model, theme, canvas, spec, result, cfg, seed)

    builder = {
        "title_slide": _slide_title,
        "closing": _slide_title,
        "section_break": _slide_section,
        "statement": _slide_statement,
        "quote": _slide_quote,
        "bullets": _slide_bullets,
        "agenda": _slide_bullets,
        "two_column": _slide_two_column,
        "comparison": _slide_two_column,
        "stats": _slide_stats,
        "table": _slide_table,
        "image_full": _slide_image_full,
        "image_left": _slide_image_side,
        "image_right": _slide_image_side,
        "gallery": _slide_gallery,
        "media": _slide_media,
        "code": _slide_code,
        "timeline": _slide_timeline,
        "diagram": _slide_diagram,
        "chart": _slide_chart,
    }.get(kind, _slide_bullets)

    builder(pslide, model, theme, canvas, spec, result, media, cfg, seed)

    if cfg.get("slide_numbers", True) and kind not in ("title_slide",):
        note = str(cfg.get("footer_note") or "")
        if model.meta.get("continuation"):
            note = f"{note} · Continued" if note else "Continued"
        _add_footer(pslide, theme, canvas, spec, result, index, total,
                    note)

    if model.notes:
        try:
            pslide.notes_slide.notes_text_frame.text = model.notes
        except Exception:                                         # noqa: BLE001
            pass


def _paint_background(pslide, model, theme, canvas, spec, result, cfg, seed):
    """Full-bleed ground: a generated gradient+ornament PNG, or a flat fill."""
    bleed = canvas.bleed
    art = None

    if theme.decorations_allowed and cfg.get("generate_art", True):
        art = compose_background(
            max(960, canvas.width // 8000), max(540, canvas.height // 8000),
            theme, out_path=None, seed=seed,
            with_ornament=(model.kind not in ("table", "code", "chart")),
        )

    if art and os.path.isfile(art):
        try:
            pic = pslide.shapes.add_picture(art, 0, 0, bleed.width, bleed.height)
            pic.name = R_BACKGROUND
            canvas.reserve_bleed(bleed)
            spec["background"] = art
            result.generated_art += 1
            result.shape_count += 1
            return
        except Exception as exc:                                  # noqa: BLE001
            result.warnings.append(
                f"the generated background could not be embedded: {exc}; "
                f"a flat fill was used instead")

    shape = _add_rect(pslide, bleed, theme.hex("ground"), None, name=R_BLEED)
    if shape is not None:
        canvas.reserve_bleed(bleed)
        result.shape_count += 1
    spec["background"] = theme.color("ground").hex


# ─────────────────────────────────────────────────────────────────────────────
# Primitive emitters — every one records into `spec` for the preview renderer
# ─────────────────────────────────────────────────────────────────────────────

def _add_rect(pslide, box, fill_hex=None, line_hex=None, name="pptxer:panel",
              weight_pt=1.25, spec=None, radius=0):
    try:
        from pptx.enum.shapes import MSO_SHAPE
        from pptx.dml.color import RGBColor
        from pptx.util import Emu, Pt

        form = MSO_SHAPE.ROUNDED_RECTANGLE if radius else MSO_SHAPE.RECTANGLE
        shape = pslide.shapes.add_shape(form, Emu(box.left), Emu(box.top),
                                        Emu(box.width), Emu(box.height))
        shape.name = name
        if radius and shape.adjustments:
            shape.adjustments[0] = min(0.5, radius / max(1, min(box.width, box.height)))
        if fill_hex:
            shape.fill.solid()
            shape.fill.fore_color.rgb = RGBColor.from_string(fill_hex)
        else:
            shape.fill.background()
        if line_hex:
            shape.line.color.rgb = RGBColor.from_string(line_hex)
            shape.line.width = Pt(float(weight_pt))
        else:
            shape.line.fill.background()
        try:
            shape.shadow.inherit = False
        except Exception:                                         # noqa: BLE001
            pass
        if spec is not None:
            spec["shapes"].append({
                "kind": "rect", "box": box.as_dict(),
                "fill": f"#{fill_hex}" if fill_hex else None,
                "line": f"#{line_hex}" if line_hex else None,
                "weight": _emu_pt(weight_pt),
            })
        return shape
    except Exception:                                             # noqa: BLE001
        return None


def _cased(text, uppercase):
    """The string that will ACTUALLY be drawn.

    ⚠️ MEASURE WHAT YOU DRAW. `_add_text` renders `line.upper()` whenever a
    role is set in capitals, and capitals are materially wider than lowercase
    — so fitting the mixed-case string and then drawing the capitalised one
    computes the wrap for text that never appears on the slide. Measured
    2026-09-14: a stat label fitted as "Target frame rate on mid-range
    hardware" and drawn as "TARGET FRAME RATE ON MID-RANGE HARDWARE" needed
    42pt in a 39pt frame and overflowed by 3pt.

    This is the same defect class as estimating a glyph at half an em: the
    model of the text has to BE the text. `.upper()` is idempotent, so a call
    site may still pass `uppercase=` to `_add_text` for clarity.
    """
    return str(text).upper() if uppercase else str(text)


def _add_text(pslide, box, fitted, color_hex, name="pptxer:text", spec=None,
              theme=None, role="body", result=None, uppercase=False):
    """Emit a text frame at an EXPLICIT solved size. Autofit stays OFF."""
    if fitted.get("overflow"):
        raise PlacementError(f"{name}: {fitted['reason']}")
    try:
        from pptx.util import Emu

        tb = pslide.shapes.add_textbox(Emu(box.left), Emu(box.top),
                                       Emu(box.width), Emu(box.height))
        tb.name = name
        font = fitted.get("font")
        size_pt = float(fitted.get("size_pt", 18))
        lines = fitted.get("lines") or []
        _write_fitted_frame(tb.text_frame, fitted, color_hex,
                            uppercase=uppercase)

        if spec is not None:
            spec["shapes"].append({
                "kind": "text", "box": box.as_dict(),
                "lines": [ln.upper() if uppercase else ln for ln in lines],
                "size_pt": size_pt,
                "font_path": getattr(font, "path", "") or "",
                "color": f"#{color_hex}",
                "align": fitted.get("align", "left"),
                "line_spacing": float(fitted.get("line_spacing", 1.18)),
                "line_height_pt": fitted.get("line_height_pt"),
                "tracking_em": getattr(font, "tracking_em", 0.0),
                "inset_pt": 2.0,
            })
        if result is not None:
            result.text_boxes.append({
                "slide": spec.get("index", 0) if spec else 0,
                "name": name, "box": box.as_dict(), "color": f"#{color_hex}",
                "floor": 4.5 if role in ("title", "mega", "heading",
                                         "stat_value") else 7.0,
            })
        return tb
    except Exception as exc:                                      # noqa: BLE001
        raise PlacementError(f"could not emit {name}: {exc}") from exc


def _write_fitted_frame(frame, fitted, color_hex, uppercase=False,
                         margins=(2, 2, 2, 2), middle=False):
    """Write exactly the measured font, tracking, line breaks and spacing."""
    from pptx.dml.color import RGBColor
    from pptx.enum.text import MSO_AUTO_SIZE, MSO_ANCHOR, PP_ALIGN
    from pptx.util import Pt
    if fitted.get("overflow"):
        raise PlacementError(fitted["reason"])
    frame.clear()
    frame.auto_size = MSO_AUTO_SIZE.NONE
    frame.word_wrap = False  # the solver has already placed every line
    frame.vertical_anchor = MSO_ANCHOR.MIDDLE if middle else MSO_ANCHOR.TOP
    frame.margin_left, frame.margin_top, frame.margin_right, frame.margin_bottom = [Pt(v) for v in margins]
    font = fitted.get("font")
    size = fitted["size_pt"]
    para = frame.paragraphs[0]
    for i, line in enumerate(fitted.get("lines") or [""]):
        if i:
            para.add_line_break()
        para.alignment = {"center": PP_ALIGN.CENTER, "right": PP_ALIGN.RIGHT,
                          "justify": PP_ALIGN.JUSTIFY}.get(fitted.get("align"), PP_ALIGN.LEFT)
        para.line_spacing = Pt(fitted.get("line_height_pt", size * fitted.get("line_spacing", 1.18)))
        para.space_before = para.space_after = Pt(0)
        para.font.size = Pt(size)
        if font:
            para.font.name = font.family
        run = para.add_run()
        run.text = line.upper() if uppercase else line
        run.font.size = Pt(size)
        run.font.bold = bool(font and font.bold)
        run.font.italic = bool(font and font.italic)
        if font:
            run.font.name = font.family
            _set_letter_spacing(run, font.tracking_em * size)
        run.font.color.rgb = RGBColor.from_string(color_hex)


def _set_letter_spacing(run, points):
    """Letter-spacing — python-pptx exposes no API, so set the XML attribute.

    Tracking is what makes an all-caps kicker or an esports title look
    professionally set rather than merely capitalised. `spc` is in hundredths
    of a point.
    """
    try:
        run.font._rPr.set("spc", str(int(round(float(points) * 100))))
    except Exception:                                             # noqa: BLE001
        pass


def _add_picture(pslide, path, box, name="pptxer:image", spec=None, result=None, crop=False):
    try:
        from pptx.util import Emu
        pic = pslide.shapes.add_picture(str(path), Emu(box.left), Emu(box.top),
                                        Emu(box.width), Emu(box.height))
        pic.name = name
        if crop:
            image_w, image_h = pic.image.size
            ratio = image_w / image_h
            target = box.width / box.height
            if ratio > target:
                pic.crop_left = pic.crop_right = (1 - target / ratio) / 2
            else:
                pic.crop_top = pic.crop_bottom = (1 - ratio / target) / 2
        if spec is not None:
            spec["shapes"].append({"kind": "image", "box": box.as_dict(),
                                   "path": str(path), "crop": crop})
        if result is not None:
            result.images_embedded += 1
            result.shape_count += 1
        return pic
    except Exception as exc:                                      # noqa: BLE001
        if result is not None:
            result.warnings.append(f"an image could not be embedded: {exc}")
        return None


def _add_rule(pslide, box, color_hex, spec=None):
    return _add_rect(pslide, box, fill_hex=color_hex, line_hex=None,
                     name="pptxer:rule", spec=spec)


# ─────────────────────────────────────────────────────────────────────────────
# Common furniture
# ─────────────────────────────────────────────────────────────────────────────

def _header(pslide, model, theme, canvas, spec, result, grid):
    """Kicker + title + rule at the top. Returns the region left for content."""
    safe = canvas.safe
    y = safe.top
    upper = theme.shape.get("uppercase_titles", False)

    if model.kicker:
        kbox = Box(safe.left, y, safe.width, max(_emu_pt(theme.size("kicker") * 1.7), int(safe.height * 0.14)),
                   "kicker", "text")
        fit = canvas.fit_text(_cased(model.kicker, True), kbox,
                              theme.font_for("kicker"),
                              theme.size("kicker"), min_pt=10.0, align="left")
        canvas.place(kbox, strict=False)
        _add_text(pslide, kbox, fit, theme.hex("kicker"), "pptxer:kicker",
                  spec, theme, "kicker", result, uppercase=True)
        y = kbox.bottom + theme.space("bullet_gap")

    if model.title:
        # ⚠️ CAP THE HEADER. Measured 2026-09-14: an unbounded title box let a
        # two-line 119pt heading eat 55% of the slide, which squeezed the stat
        # tiles until the NUMBERS rendered smaller than their own labels — a
        # layout that passes every geometric check and still fails at the one
        # thing a stat slide is for.
        #
        # The content is the point; the header is the label on it. A heading
        # therefore never takes more than a third of the safe area, and
        # fit_text shrinks it to suit rather than stealing the room.
        max_h = min(_emu_pt(theme.size("heading") * 2.9),
                    int(safe.height * 0.34))
        tbox = Box(safe.left, y, safe.width, max_h, "title", "text")
        fit = canvas.fit_text(_cased(model.title, upper), tbox,
                              theme.font_for("heading"),
                              min(48.0, theme.size("heading")),
                              min_pt=18.0, align="left")
        used = _emu_pt(fit["text_height_pt"]) + _emu_pt(6)
        tbox = tbox.resized(height=min(max_h, max(used, _emu_pt(24))))
        canvas.place(tbox, strict=False)
        _add_text(pslide, tbox, fit, theme.hex("heading"), "pptxer:title",
                  spec, theme, "heading", result, uppercase=upper)
        y = tbox.bottom + _emu_pt(6)

        rule = Box(safe.left, y, min(safe.width, _emu_pt(96)),
                   theme.shape["rule"], "title-rule", "rule")
        canvas.place(rule, strict=False)
        _add_rule(pslide, rule, theme.hex("rule"), spec)
        result.shape_count += 1
        y = rule.bottom + theme.space("header_gap")

    if model.subtitle:
        sbox = Box(safe.left, y, safe.width, _emu_pt(theme.size("subtitle") * 2.4),
                   "subtitle", "text")
        fit = canvas.fit_text(model.subtitle, sbox, theme.font_for("subtitle"),
                              theme.size("subtitle"), min_pt=14.0, align="left")
        sbox = sbox.resized(height=_emu_pt(fit["text_height_pt"]) + _emu_pt(4))
        canvas.place(sbox, strict=False)
        _add_text(pslide, sbox, fit, theme.hex("subtitle"), "pptxer:subtitle",
                  spec, theme, "subtitle", result)
        y = sbox.bottom + theme.space("paragraph")

    # ⚠️ RESERVE THE FOOTER BAND. Measured 2026-09-14: without this the stat
    # tiles extended to safe.bottom and genuinely collided with the page
    # number — 4 real overlaps the audit caught. The footer is furniture every
    # non-title slide gets, so the content region must never have been offered
    # that strip in the first place. Preventing the collision beats detecting
    # it, which is this module's whole premise.
    footer_band = canvas.footer_height + theme.space("paragraph")
    bottom = max(y, safe.bottom - footer_band)

    return Box(safe.left, y, safe.width, max(0, bottom - y),
               "content", "region")


def _add_footer(pslide, theme, canvas, spec, result, index, total, note):
    safe = canvas.safe
    h = canvas.footer_height
    box = Box(safe.left, safe.bottom - h, safe.width, h, "footer", "text")
    text = f"{note}  ·  {index} / {total}" if note else f"{index} / {total}"
    fit = canvas.fit_text(text, box, theme.font_for("footnote"),
                          theme.size("footnote"), min_pt=10.0, align="right")
    canvas.place(box, strict=False)
    _add_text(pslide, box, fit, theme.hex("footer"), "pptxer:footer", spec,
              theme, "footnote", result)
    result.shape_count += 1


# ─────────────────────────────────────────────────────────────────────────────
# Slide builders
# ─────────────────────────────────────────────────────────────────────────────

def _slide_title(pslide, model, theme, canvas, spec, result, media, cfg, seed):
    safe = canvas.safe
    if model.kind != "title_slide" and cfg.get("slide_numbers", True):
        safe = safe.resized(height=safe.height - canvas.footer_height - theme.space("paragraph"))
    upper = theme.shape.get("uppercase_titles", False)
    content = []
    if model.kicker:
        content.append((_cased(model.kicker, True), "kicker", 11.0, safe.width))
    if model.title:
        content.append((_cased(model.title, upper), "mega", 24.0, safe.width))
    if model.subtitle:
        content.append((model.subtitle, "subtitle", 16.0, int(safe.width * 0.9)))
    gap = theme.space("paragraph")
    usable = safe.height - gap * max(0, len(content) - 1)
    fits = []
    for step in range(41):
        fits = []
        factor = 1.0 - step / 40.0
        for text, role, floor, width in content:
            start = max(floor, theme.size(role) * factor)
            fit = canvas.fit_text(text, Box(0, 0, width, usable), theme.font_for(role), start, min_pt=floor)
            fits.append((fit, _emu_pt(fit["text_height_pt"]) + _emu_pt(6)))
        if sum(height for _, height in fits) <= usable and not any(f["overflow"] for f, _ in fits):
            break
    else:
        raise PlacementError("cover text needs a continuation slide")
    total = sum(height for _, height in fits) + gap * max(0, len(fits) - 1)
    y = safe.top + max(0, (safe.height - total) // 2)
    for (_, role, _, width), (fit, height) in zip(content, fits):
        box = Box(safe.left, y, width, height, role, "text")
        canvas.place(box, strict=False)
        name = "pptxer:megatitle" if role == "mega" else f"pptxer:{role}"
        color = "title" if role == "mega" else role
        _add_text(pslide, box, fit, theme.hex(color), name, spec, theme, role, result)
        result.shape_count += 1
        y = box.bottom + gap


def _slide_section(pslide, model, theme, canvas, spec, result, media, cfg, seed):
    safe = canvas.safe
    upper = theme.shape.get("uppercase_titles", False)
    band_h = int(safe.height * 0.34)
    y = safe.top + (safe.height - band_h) // 2

    rule = Box(safe.left, y, int(safe.width * 0.14), theme.shape["rule"] * 2,
               "section-rule", "rule")
    canvas.place(rule, strict=False)
    _add_rule(pslide, rule, theme.hex("accent"), spec)
    result.shape_count += 1

    tbox = Box(safe.left, rule.bottom + theme.space("section"), safe.width,
               band_h, "section-title", "text")
    fit = canvas.fit_text(_cased(model.title or model.body, upper), tbox,
                          theme.font_for("title"), theme.size("title"),
                          min_pt=18.0)
    tbox = tbox.resized(height=_emu_pt(fit["text_height_pt"]) + _emu_pt(8))
    canvas.place(tbox, strict=False)
    _add_text(pslide, tbox, fit, theme.hex("title"), "pptxer:sectiontitle",
              spec, theme, "title", result, uppercase=upper)


def _slide_statement(pslide, model, theme, canvas, spec, result, media, cfg, seed):
    safe = canvas.safe
    text = model.body or model.title
    box = Box(safe.left + int(safe.width * 0.06), safe.top,
              int(safe.width * 0.88), safe.height, "statement", "text")
    fit = canvas.fit_text(text, box, theme.font_for("quote"),
                          theme.size("quote") * 1.25,
                          min_pt=theme.size("subtitle"), align="center")
    used = _emu_pt(fit["text_height_pt"]) + _emu_pt(10)
    box = Box(box.left, safe.top + max(0, (safe.height - used) // 2),
              box.width, used, "statement", "text")
    canvas.place(box, strict=False)
    _add_text(pslide, box, fit, theme.hex("text"), "pptxer:statement",
              spec, theme, "quote", result)


def _slide_quote(pslide, model, theme, canvas, spec, result, media, cfg, seed):
    safe = canvas.safe
    if cfg.get("slide_numbers", True):
        safe = safe.resized(height=safe.height - canvas.footer_height - theme.space("paragraph"))
    quote = model.quote or model.body
    width = int(safe.width * 0.84)
    attribution_height = _emu_pt(theme.size("caption") * 2.2) if model.attribution else 0
    gap = theme.space("section") if model.attribution else 0
    inner = Box(safe.left + int(safe.width * 0.08), safe.top,
                width, safe.height - attribution_height - gap, "quote", "text")
    fit = canvas.fit_text(f"“{quote}”", inner, theme.font_for("quote"),
                          theme.size("quote"), min_pt=16.0, align="center")
    used = _emu_pt(fit["text_height_pt"]) + _emu_pt(10)
    total = used + attribution_height + gap
    if total > safe.height:
        raise PlacementError("quote and attribution need a continuation slide")
    inner = Box(inner.left, safe.top + max(0, (safe.height - total) // 2),
                inner.width, used, "quote", "text")
    canvas.place(inner, strict=False)
    _add_text(pslide, inner, fit, theme.hex("quote"), "pptxer:quote", spec,
              theme, "quote", result)

    if model.attribution:
        abox = Box(inner.left, inner.bottom + gap, inner.width,
                   attribution_height, "attribution", "text")
        afit = canvas.fit_text(f"— {model.attribution}", abox,
                               theme.font_for("caption"), theme.size("caption"),
                               min_pt=10.0, align="center")
        canvas.place(abox, strict=False)
        _add_text(pslide, abox, afit, theme.hex("caption"), "pptxer:attribution",
                  spec, theme, "caption", result)


def _slide_bullets(pslide, model, theme, canvas, spec, result, media, cfg, seed):
    grid = GridSolver(canvas)
    region = _header(pslide, model, theme, canvas, spec, result, grid)
    if region.height <= 0:
        return

    items = list(model.bullets)
    if model.body and not items:
        _place_body(pslide, model.body, theme, canvas, spec, result, region)
        return

    if not items:
        return

    gap = theme.space("bullet_gap")
    per = max(_emu_pt(theme.size("bullet") * 1.35),
              (region.height - gap * (len(items) - 1)) // max(1, len(items)))
    marker_w = _emu_pt(theme.size("bullet") * 0.95)

    y = region.top
    for text in items:
        if y >= region.bottom:
            raise PlacementError("bullets need another slide")
        avail = min(per, region.bottom - y)
        dot = Box(region.left, y + _emu_pt(theme.size("bullet") * 0.42),
                  _emu_pt(theme.size("bullet") * 0.30),
                  _emu_pt(theme.size("bullet") * 0.30), "marker", "decor")
        tbox = Box(region.left + marker_w, y, region.width - marker_w, avail,
                   "bullet", "text")
        fit = canvas.fit_text(text, tbox, theme.font_for("bullet"),
                              theme.size("bullet"), min_pt=14.0)
        used = _emu_pt(fit["text_height_pt"]) + _emu_pt(4)
        tbox = tbox.resized(height=min(avail, max(used, _emu_pt(18))))

        canvas.place(dot, strict=False)
        canvas.place(tbox, strict=False)
        _add_rect(pslide, dot, theme.hex("bullet_marker"), None,
                  "pptxer:decor.marker", spec=spec)
        _add_text(pslide, tbox, fit, theme.hex("text"), "pptxer:bullet",
                  spec, theme, "bullet", result)
        result.shape_count += 2
        y = tbox.bottom + gap


def _place_body(pslide, body, theme, canvas, spec, result, region):
    fit = canvas.fit_text(body, region, theme.font_for("body"),
                          theme.size("body"), min_pt=14.0)
    box = region.resized(height=min(region.height,
                                    _emu_pt(fit["text_height_pt"]) + _emu_pt(8)))
    canvas.place(box, strict=False)
    _add_text(pslide, box, fit, theme.hex("text"), "pptxer:body", spec,
              theme, "body", result)
    result.shape_count += 1


def _slide_two_column(pslide, model, theme, canvas, spec, result, media, cfg, seed):
    grid = GridSolver(canvas)
    region = _header(pslide, model, theme, canvas, spec, result, grid)
    if region.height <= 0:
        return

    cols = model.columns
    if not cols:
        half = max(1, len(model.bullets) // 2 or 1)
        cols = [{"title": "", "bullets": model.bullets[:half]},
                {"title": "", "bullets": model.bullets[half:]}]

    boxes = canvas.columns(region, max(1, min(3, len(cols))))
    for cbox, col in zip(boxes, cols):
        panel = cbox
        if theme.decoration in ("moderate", "rich"):
            canvas.place(panel, strict=False)
            _add_rect(pslide, panel, theme.hex("surface"),
                      theme.hex("panel_border"), "pptxer:panel",
                      spec=spec, radius=theme.shape["radius"])
            result.shape_count += 1
            inner = panel.inset(theme.space("panel_pad"))
        else:
            inner = panel

        y = inner.top
        if col.get("title"):
            tb = Box(inner.left, y, inner.width,
                     _emu_pt(theme.size("subheading") * 2.2), "col-title", "text")
            fit = canvas.fit_text(col["title"], tb, theme.font_for("subheading"),
                                  theme.size("subheading"), min_pt=13.0)
            tb = tb.resized(height=_emu_pt(fit["text_height_pt"]) + _emu_pt(4))
            _add_text(pslide, tb, fit, theme.hex("accent_text"), "pptxer:coltitle",
                      spec, theme, "subheading", result)
            result.shape_count += 1
            y = tb.bottom + theme.space("paragraph")

        gap = theme.space("bullet_gap")
        for text in col.get("bullets", []):
            if y >= inner.bottom:
                raise PlacementError("column content needs another slide")
            tb = Box(inner.left, y, inner.width, inner.bottom - y, "col-bullet",
                     "text")
            fit = canvas.fit_text(text, tb, theme.font_for("body"),
                                  theme.size("body"), min_pt=12.0)
            used = _emu_pt(fit["text_height_pt"]) + _emu_pt(4)
            tb = tb.resized(height=min(inner.bottom - y, used))
            _add_text(pslide, tb, fit, theme.hex("text"), "pptxer:colbullet",
                      spec, theme, "body", result)
            result.shape_count += 1
            y = tb.bottom + gap


def _slide_stats(pslide, model, theme, canvas, spec, result, media, cfg, seed):
    grid = GridSolver(canvas)
    region = _header(pslide, model, theme, canvas, spec, result, grid)
    stats = model.stats or []
    if not stats or region.height <= 0:
        return

    count = len(stats)
    if count > 6:
        raise PlacementError("stat cards need another slide")
    cols = count if count <= 3 else (count + 1) // 2
    rows = 1 if count <= 3 else 2
    if canvas.height > canvas.width:
        cols = min(2, cols)
        rows = (count + cols - 1) // cols
    cells = canvas.grid(region, cols, rows)

    for cell, stat in zip(cells, stats[:count]):
        panel = cell
        canvas.place(panel, strict=False)
        if theme.decoration != "none":
            _add_rect(pslide, panel, theme.hex("surface"),
                      theme.hex("panel_border"), "pptxer:panel", spec=spec,
                      radius=theme.shape["radius"])
            result.shape_count += 1
        inner = panel.inset(theme.space("panel_pad"))

        # Reserve the complete label at a readable size before offering the
        # number any space. A decorative number must not crowd out evidence.
        min_label_h = canvas.text_block_height(_cased(stat.get("label", ""), True),
                                               inner.width, theme.font_for("stat_label"), 11.0)
        value_h = min(int(inner.height * 0.44), inner.height - min_label_h - _emu_pt(8))
        if value_h < _emu_pt(36):
            raise PlacementError("stat label and value need a larger card")

        vbox = Box(inner.left, inner.top, inner.width, value_h,
                   "stat-value", "text")
        value_cap = min(72.0, theme.size("stat_value"),
                        (value_h / EMU_PER_POINT) * 0.86)
        vfit = canvas.fit_text(str(stat.get("value", "")), vbox,
                               theme.font_for("stat_value"),
                               value_cap, min_pt=26.0, align="center")
        value = str(stat.get("value", ""))
        if len(value) <= 16 and "\n" not in value and vfit["line_count"] > 1:
            from pptxer_fonts import measure_text
            font = theme.font_for("stat_value")
            measured = measure_text(value, font, value_cap)[0]
            single_line_cap = value_cap * max(1, inner.width_pt - 4) / max(1, measured) * 0.98
            vfit = canvas.fit_text(value, vbox, font, max(26, single_line_cap),
                                   min_pt=26.0, align="center")
            if vfit["line_count"] > 1:
                raise PlacementError("short stat values need a wider card to stay on one line")
        # Return unused value height to the label while preserving the gap.
        value_used = _emu_pt(vfit["text_height_pt"]) + _emu_pt(4)
        vbox = vbox.resized(height=max(_emu_pt(14), min(value_h, value_used)))
        label_h = max(_emu_pt(12), inner.bottom - vbox.bottom)

        _add_text(pslide, vbox, vfit, theme.hex("stat_value"),
                  "pptxer:statvalue", spec, theme, "stat_value", result)

        lbox = Box(inner.left, vbox.bottom, inner.width, label_h,
                   "stat-label", "text")
        # The label is at most 45% of the SOLVED value size, so the hierarchy
        # survives even when the tile forced the value down.
        label_cap = min(18.0, theme.size("stat_label"),
                        vfit["size_pt"] * 0.45,
                        (label_h / EMU_PER_POINT) * 0.80)
        if label_cap < 11.0:
            raise PlacementError("stat card needs more room to preserve a readable label and value hierarchy")
        lfit = canvas.fit_text(_cased(stat.get("label", ""), True), lbox,
                               theme.font_for("stat_label"),
                               max(11.0, label_cap), min_pt=11.0,
                               align="center")
        _add_text(pslide, lbox, lfit, theme.hex("stat_label"),
                  "pptxer:statlabel", spec, theme, "stat_label", result,
                  uppercase=True)
        result.shape_count += 2


def _slide_table(pslide, model, theme, canvas, spec, result, media, cfg, seed):
    grid = GridSolver(canvas)
    region = _header(pslide, model, theme, canvas, spec, result, grid)
    table = model.table or {}
    headers = table.get("headers") or []
    rows = table.get("rows") or []
    if not headers and not rows:
        return

    all_rows = ([headers] if headers else []) + rows
    body_font = theme.font_for("table")
    head_font = theme.font_for("table_head")
    size = min(16.0, theme.size("table"))

    from pptxer_fonts import font_for_text, line_height_pt, wrap_text_to_width
    from pptx.util import Emu
    from pptx.dml.color import RGBColor

    solved = solve_columns(all_rows, body_font, size, region.width,
                           padding_pt=8.0, min_col_pt=42.0,
                           inventory=canvas._inventory, header_font=head_font)
    widths = solved["widths"]
    ncols = len(widths)
    # Native tables auto-grow to accommodate text. Solve every row BEFORE
    # creating the table, so Office never has to grow it past the content area.
    fitted_rows, heights = [], []
    for r, row in enumerate(all_rows):
        font = head_font if headers and r == 0 else body_font
        cells = []
        for c, width in enumerate(widths):
            text = str(row[c]) if c < len(row) and row[c] is not None else ""
            cell_font = font_for_text(font, text, canvas._inventory)
            lines = wrap_text_to_width(text, cell_font, size,
                                       max(1, width / EMU_PER_POINT - 16),
                                       canvas._inventory, break_long_words=True)
            cells.append({"lines": lines, "size_pt": size, "font": cell_font,
                          "line_spacing": 1.18, "line_height_pt": line_height_pt(cell_font, size, inventory=canvas._inventory), "align": "left"})
        height = _emu_pt(max((max(1, len(c["lines"])) * c["line_height_pt"] for c in cells), default=0) + 10)
        fitted_rows.append(cells)
        heights.append(height)
    if sum(heights) > region.height or not ncols:
        raise PlacementError("table rows need another slide at their readable font size")
    tbox = region.resized(height=sum(heights))
    canvas.place(tbox, strict=False)
    gfx = pslide.shapes.add_table(len(all_rows), ncols, Emu(tbox.left), Emu(tbox.top),
                                  Emu(tbox.width), Emu(tbox.height))
    gfx.name = "pptxer:table"
    tbl = gfx.table
    tbl.first_row = bool(headers)
    tbl.horz_banding = True
    for c, width in enumerate(widths):
        tbl.columns[c].width = Emu(int(width))
    y = tbox.top
    for r, (fits, height) in enumerate(zip(fitted_rows, heights)):
        tbl.rows[r].height = Emu(height)
        x = tbox.left
        for c, fit in enumerate(fits):
            cell = tbl.cell(r, c)
            is_head = bool(headers) and r == 0
            bg = theme.hex("table_head_bg") if is_head else theme.hex("table_row_alt" if r % 2 == 0 else "surface")
            fg = theme.hex("table_head_text" if is_head else "table_text")
            cell.fill.solid()
            cell.fill.fore_color.rgb = RGBColor.from_string(bg)
            _write_fitted_frame(cell.text_frame, fit, fg, margins=(6, 3, 6, 3))
            box = Box(x, y, widths[c], height)
            spec["shapes"].append({"kind": "rect", "box": box.as_dict(), "fill": f"#{bg}"})
            spec["shapes"].append({"kind": "text", "box": box.inset(_emu_pt(4)).as_dict(),
                                   "lines": fit["lines"], "size_pt": size,
                                   "font_path": fit["font"].path, "color": f"#{fg}",
                                   "line_spacing": 1.18, "line_height_pt": fit["line_height_pt"],
                                   "tracking_em": fit["font"].tracking_em})
            result.text_boxes.append({"slide": spec["index"], "name": f"pptxer:table[{r + 1},{c + 1}]",
                                      "box": box.as_dict(), "color": f"#{fg}", "floor": 7.0})
            x += widths[c]
        y += height
    result.tables += 1
    result.shape_count += 1


def _slide_image_full(pslide, model, theme, canvas, spec, result, media, cfg, seed):
    asset = _first_ok_image(model, media)
    bleed = canvas.bleed
    if asset:
        box = bleed
        _add_picture(pslide, asset.path, box, R_BLEED + ".photo", spec, result)
        canvas.reserve_bleed(box)

        scrim = draw_scrim(1200, 675, theme.color("ground_deep"), "bottom", 0.9)
        if scrim:
            _add_picture(pslide, scrim, bleed, R_SCRIM, spec, result)
            canvas.reserve_bleed(bleed)

    safe = canvas.safe
    y = safe.top + int(safe.height * 0.52)
    if model.title:
        tbox = Box(safe.left, y, int(safe.width * 0.82),
                   int(safe.height * 0.30), "title", "text")
        fit = canvas.fit_text(
            _cased(model.title,
                   theme.shape.get("uppercase_titles", False)),
            tbox, theme.font_for("title"),
            theme.size("title"), min_pt=20.0)
        tbox = tbox.resized(height=_emu_pt(fit["text_height_pt"]) + _emu_pt(8))
        canvas.place(tbox, strict=False)
        _add_text(pslide, tbox, fit, theme.hex("text"), "pptxer:title", spec,
                  theme, "title", result,
                  uppercase=theme.shape.get("uppercase_titles", False))
        y = tbox.bottom + theme.space("paragraph")

    if model.subtitle or model.body:
        text = model.subtitle or model.body
        sbox = Box(safe.left, y, int(safe.width * 0.68),
                   max(_emu_pt(20), safe.bottom - y - _emu_pt(24)),
                   "subtitle", "text")
        fit = canvas.fit_text(text, sbox, theme.font_for("subtitle"),
                              theme.size("subtitle"), min_pt=13.0)
        sbox = sbox.resized(height=_emu_pt(fit["text_height_pt"]) + _emu_pt(6))
        canvas.place(sbox, strict=False)
        _add_text(pslide, sbox, fit, theme.hex("subtitle"), "pptxer:subtitle",
                  spec, theme, "subtitle", result)


def _slide_image_side(pslide, model, theme, canvas, spec, result, media, cfg, seed):
    grid = GridSolver(canvas)
    region = _header(pslide, model, theme, canvas, spec, result, grid)
    if region.height <= 0:
        return

    image_left = (model.kind == "image_left")
    cols = canvas.columns(region, 2, weights=(1.0, 1.0))
    img_region, txt_region = (cols[0], cols[1]) if image_left else (cols[1], cols[0])

    asset = _first_ok_image(model, media)
    if asset:
        box = img_region
        canvas.place(box, strict=False)
        _add_picture(pslide, asset.path, box, "pptxer:image", spec, result, crop=True)

    y = txt_region.top
    gap = theme.space("bullet_gap")
    for text in (model.bullets or ([model.body] if model.body else [])):
        if y >= txt_region.bottom:
            raise PlacementError("image-side content needs another slide")
        tb = Box(txt_region.left, y, txt_region.width, txt_region.bottom - y,
                 "bullet", "text")
        fit = canvas.fit_text(text, tb, theme.font_for("body"),
                              theme.size("body"), min_pt=13.0)
        tb = tb.resized(height=min(txt_region.bottom - y,
                                   _emu_pt(fit["text_height_pt"]) + _emu_pt(4)))
        canvas.place(tb, strict=False)
        _add_text(pslide, tb, fit, theme.hex("text"), "pptxer:bullet", spec,
                  theme, "body", result)
        result.shape_count += 1
        y = tb.bottom + gap


def _slide_gallery(pslide, model, theme, canvas, spec, result, media, cfg, seed):
    grid = GridSolver(canvas)
    region = _header(pslide, model, theme, canvas, spec, result, grid)
    assets = [media.get(src) for src in model.images]
    assets = [a for a in assets if a is not None and a.ok]
    if not assets or region.height <= 0:
        return

    n = min(len(assets), 6)
    cols = 3 if n >= 5 else (2 if n >= 3 else n)
    rows = (n + cols - 1) // cols
    cells = canvas.grid(region, cols, rows)

    for cell, asset in zip(cells, assets[:n]):
        box = cell
        canvas.place(box, strict=False)
        _add_picture(pslide, asset.path, box, "pptxer:image", spec, result, crop=True)


def _slide_media(pslide, model, theme, canvas, spec, result, media, cfg, seed):
    grid = GridSolver(canvas)
    region = _header(pslide, model, theme, canvas, spec, result, grid)
    asset = media.get(model.video)

    if asset is None or not asset.ok:
        reason = asset.error if asset is not None else "no video was resolved"
        result.media_failures.append(
            f"slide {spec.get('index')}: the video could not be embedded — {reason}")
        _place_body(pslide, model.body or f"[video unavailable: {reason}]",
                    theme, canvas, spec, result, region)
        return

    box = fit_image_box(region, asset.width or 1920, asset.height or 1080,
                        "contain")
    canvas.place(box, strict=False)
    try:
        from pptx.util import Emu
        poster = asset.sha256 if (asset.sha256 and os.path.isfile(asset.sha256)) else None
        movie = pslide.shapes.add_movie(
            asset.path, Emu(box.left), Emu(box.top), Emu(box.width),
            Emu(box.height), poster_frame_image=poster,
            mime_type="video/mp4")
        movie.name = "pptxer:video"
        result.videos_embedded += 1
        result.shape_count += 1
        spec["shapes"].append({"kind": "image", "box": box.as_dict(),
                               "path": poster or ""})
        if not poster:
            result.warnings.append(
                f"slide {spec.get('index')}: the video was embedded without a "
                f"poster frame, so it shows as a black rectangle until played")
    except Exception as exc:                                      # noqa: BLE001
        result.media_failures.append(
            f"slide {spec.get('index')}: add_movie failed — {exc}")


def _slide_code(pslide, model, theme, canvas, spec, result, media, cfg, seed):
    grid = GridSolver(canvas)
    region = _header(pslide, model, theme, canvas, spec, result, grid)
    if not model.code or region.height <= 0:
        return

    canvas.place(region, strict=False)
    _add_rect(pslide, region, theme.hex("code_bg"), theme.hex("panel_border"),
              "pptxer:panel", spec=spec, radius=theme.shape["radius"])
    result.shape_count += 1

    inner = region.inset(theme.space("panel_pad"))
    fit = canvas.fit_text(model.code, inner, theme.font_for("code"),
                          theme.size("code"), min_pt=9.0, line_spacing=1.28)
    _add_text(pslide, inner, fit, theme.hex("code_text"), "pptxer:code", spec,
              theme, "code", result)
    result.shape_count += 1


def _slide_timeline(pslide, model, theme, canvas, spec, result, media, cfg, seed):
    grid = GridSolver(canvas)
    region = _header(pslide, model, theme, canvas, spec, result, grid)
    items = model.timeline or []
    if not items or region.height <= 0:
        return

    n = min(len(items), 6)
    axis_y = region.top + region.height // 3
    axis = Box(region.left, axis_y, region.width, theme.shape["rule"], "axis",
               "rule")
    canvas.place(axis, strict=False)
    _add_rule(pslide, axis, theme.hex("rule"), spec)
    result.shape_count += 1

    cells = canvas.columns(Box(region.left, axis.bottom, region.width,
                               region.bottom - axis.bottom, "tl", "region"), n)
    for i, (cell, item) in enumerate(zip(cells, items[:n])):
        dot_d = _emu_pt(11)
        dot = Box(cell.center_x - dot_d // 2, axis_y - dot_d // 2 + theme.shape["rule"] // 2,
                  dot_d, dot_d, "tl-dot", "decor")
        _add_rect(pslide, dot, theme.hex(f"series_{(i % 8) + 1}"), None,
                  "pptxer:decor.dot", spec=spec)
        result.shape_count += 1

        wbox = Box(cell.left, cell.top + _emu_pt(10), cell.width,
                   _emu_pt(theme.size("label") * 2.0), "tl-when", "text")
        wfit = canvas.fit_text(_cased(item.get("when", ""), True), wbox,
                               theme.font_for("label"), theme.size("label"),
                               min_pt=9.0, align="center")
        canvas.place(wbox, strict=False)
        _add_text(pslide, wbox, wfit, theme.hex("accent_text"), "pptxer:tlwhen",
                  spec, theme, "label", result, uppercase=True)

        tbox = Box(cell.left, wbox.bottom + _emu_pt(4), cell.width,
                   max(_emu_pt(20), cell.bottom - wbox.bottom - _emu_pt(4)),
                   "tl-what", "text")
        tfit = canvas.fit_text(str(item.get("what", "")), tbox,
                               theme.font_for("body"), theme.size("body") * 0.9,
                               min_pt=10.0, align="center")
        canvas.place(tbox, strict=False)
        _add_text(pslide, tbox, tfit, theme.hex("text"), "pptxer:tlwhat",
                  spec, theme, "body", result)
        result.shape_count += 2


def _slide_diagram(pslide, model, theme, canvas, spec, result, media, cfg, seed):
    grid = GridSolver(canvas)
    region = _header(pslide, model, theme, canvas, spec, result, grid)
    try:
        from pptxer_diagram import render_diagram
    except Exception as exc:                                      # noqa: BLE001
        result.warnings.append(f"the diagram engine is unavailable: {exc}")
        return
    try:
        count = render_diagram(pslide, model.diagram or {}, theme, canvas,
                               region, spec, result)
        result.diagrams += 1
        result.shape_count += count
    except Exception as exc:                                      # noqa: BLE001
        result.warnings.append(f"the diagram could not be drawn: {exc}")


def _slide_chart(pslide, model, theme, canvas, spec, result, media, cfg, seed):
    """A NATIVE PowerPoint chart — editable, not a picture of a chart.

    This matters: a chart embedded as an image cannot be re-coloured, re-typed
    or corrected by the person who receives the deck, and it goes soft on a
    projector. A real chart object stays crisp and stays theirs.
    """
    grid = GridSolver(canvas)
    region = _header(pslide, model, theme, canvas, spec, result, grid)
    chart = model.chart or {}
    categories = chart.get("categories") or []
    series = chart.get("series") or []
    if not categories or not series or region.height <= 0:
        return

    try:
        from pptx.chart.data import CategoryChartData
        from pptx.enum.chart import XL_CHART_TYPE, XL_LEGEND_POSITION
        from pptx.dml.color import RGBColor
        from pptx.util import Emu, Pt

        data = CategoryChartData()
        data.categories = [str(c) for c in categories]
        for s in series:
            try:
                values = [float(v) for v in (s.get("values") or [])]
            except (TypeError, ValueError):
                continue
            data.add_series(str(s.get("name", "Series")), values)

        kind = str(chart.get("kind", "bar")).lower()
        ctype = {
            "bar": XL_CHART_TYPE.COLUMN_CLUSTERED,
            "column": XL_CHART_TYPE.COLUMN_CLUSTERED,
            "hbar": XL_CHART_TYPE.BAR_CLUSTERED,
            "line": XL_CHART_TYPE.LINE_MARKERS,
            "pie": XL_CHART_TYPE.PIE,
            "doughnut": XL_CHART_TYPE.DOUGHNUT,
            "area": XL_CHART_TYPE.AREA,
            "scatter": XL_CHART_TYPE.XY_SCATTER,
            "radar": XL_CHART_TYPE.RADAR,
        }.get(kind, XL_CHART_TYPE.COLUMN_CLUSTERED)

        canvas.place(region, strict=False)
        gfx = pslide.shapes.add_chart(ctype, Emu(region.left), Emu(region.top),
                                      Emu(region.width), Emu(region.height), data)
        gfx.name = "pptxer:chart"
        obj = gfx.chart

        obj.has_title = False
        if len(series) > 1 or kind in ("pie", "doughnut"):
            obj.has_legend = True
            obj.legend.position = XL_LEGEND_POSITION.BOTTOM
            obj.legend.include_in_layout = False
            try:
                obj.legend.font.size = Pt(theme.size("caption"))
                obj.legend.font.color.rgb = RGBColor.from_string(theme.hex("text"))
                if theme.font_for("caption"):
                    obj.legend.font.name = theme.font_for("caption").family
            except Exception:                                     # noqa: BLE001
                pass
        else:
            obj.has_legend = False

        for i, plot_series in enumerate(obj.series):
            try:
                plot_series.format.fill.solid()
                plot_series.format.fill.fore_color.rgb = RGBColor.from_string(
                    theme.hex(f"series_{(i % 8) + 1}"))
                if kind in ("line", "scatter", "radar"):
                    color = RGBColor.from_string(theme.hex(f"series_{(i % 8) + 1}"))
                    plot_series.format.line.color.rgb = color
                    plot_series.format.line.width = Pt(2.5)
                    plot_series.marker.format.fill.solid()
                    plot_series.marker.format.fill.fore_color.rgb = color
                    plot_series.marker.format.line.color.rgb = color
            except Exception:                                     # noqa: BLE001
                pass

        if kind in ("pie", "doughnut"):
            from pptxer_color import contrast_ratio
            plot = obj.plots[0]
            plot.has_data_labels = True
            plot.data_labels.show_value = True
            for i, point in enumerate(obj.series[0].points):
                color = theme.hex(f"series_{(i % 8) + 1}")
                point.format.fill.solid()
                point.format.fill.fore_color.rgb = RGBColor.from_string(color)
                point.data_label.font.size = Pt(theme.size("caption"))
                point.data_label.font.name = theme.font_for("caption").family
                ink = "FFFFFF" if contrast_ratio("#" + color, "#FFFFFF") >= contrast_ratio("#" + color, "#000000") else "000000"
                point.data_label.font.color.rgb = RGBColor.from_string(ink)

        for axis_name in ("category_axis", "value_axis"):
            try:
                axis = getattr(obj, axis_name)
                axis.tick_labels.font.size = Pt(theme.size("caption"))
                axis.tick_labels.font.color.rgb = RGBColor.from_string(
                    theme.hex("chart_axis"))
                axis.format.line.color.rgb = RGBColor.from_string(
                    theme.hex("chart_axis"))
                if theme.font_for("caption"):
                    axis.tick_labels.font.name = theme.font_for("caption").family
            except Exception:                                     # noqa: BLE001
                pass

        result.charts += 1
        result.shape_count += 1
    except Exception as exc:                                      # noqa: BLE001
        result.warnings.append(f"the chart could not be built: {exc}")


def _first_ok_image(model, media):
    for src in model.images:
        asset = media.get(src)
        if asset is not None and asset.ok:
            return asset
    return None
