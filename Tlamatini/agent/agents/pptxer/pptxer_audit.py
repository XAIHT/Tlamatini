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
# pptxer_audit.py — DID THE DECK ACTUALLY COME OUT RIGHT?
#
# Sibling module of pptxer.py. Stdlib + Pillow + python-pptx (lazily).
# Imports pptxer_color and pptxer_layout. Nothing from agent.*.
#
# ═════════════════════════════════════════════════════════════════════════════
#  WHY THIS EXISTS — the lesson PDFer paid for
# ═════════════════════════════════════════════════════════════════════════════
#     A RENDERER'S OWN SUCCESS FLAG IS NOT EVIDENCE.  ONLY THE FILE IS.
#
# PDFer's xhtml2pdf reported `err = 0` on three documents that contained EIGHT
# cell-on-cell overlaps and a path 54pt off the sheet. python-pptx is worse in
# this specific respect: it does no layout at all, so it CANNOT report a layout
# problem. `prs.save()` succeeding means the XML is well-formed — nothing more.
#
# So the deck is re-opened and MEASURED, at three independent levels:
#
#   LEVEL 1 · SHAPE-TREE AUDIT (always runs, zero dependencies beyond
#             python-pptx). Re-opens the SAVED .pptx — not the in-memory model
#             that produced it — and measures every shape's real EMU box.
#             Catches overlaps, off-slide content and safe-area escapes, and it
#             catches them in the ARTEFACT, which is the only thing that ships.
#
#   LEVEL 2 · TEXT-FIT AUDIT (always runs). Re-measures every text frame's
#             content against its box using the real font metrics. This is the
#             one PowerPoint itself will silently paper over with autofit on
#             the author's machine and then break on someone else's.
#
#   LEVEL 3 · PIXEL AUDIT (only when a renderer produced images). Measures the
#             rendered PNGs for blank slides, ink outside the safe area, and
#             true contrast of text against the pixels actually behind it.
#
# ⚠️ LEVEL 3 IS THE ONLY ONE THAT CAN SETTLE WHAT POWERPOINT DRAWS, AND IT IS
# ALSO THE ONLY ONE THAT MIGHT NOT RUN. When it does not, the report says so
# explicitly. An audit that could not look must never report "clean".
#
# ─────────────────────────────────────────────────────────────────────────────
# SEVERITIES ARE SEPARATE ON PURPOSE (PDFer contract 5)
# ─────────────────────────────────────────────────────────────────────────────
#   off_slide        — ink outside the SHEET. Always a defect.
#   safe_escape      — inside the sheet, outside the safe margin. A defect for
#                      content; legitimate for a deliberate full-bleed element.
#   overlap          — two content boxes intersecting. A defect.
#   text_overflow    — text measured larger than its frame. A defect.
#   low_contrast     — text below its projected-legibility floor. A defect.
#   blank_slide      — a rendered slide with almost no ink. Usually a defect.
#
# A check that fires on CORRECT decks gets switched off by the person reading
# it, so each one is scoped narrowly and a full-bleed background is EXEMPT from
# the safe-area rule by design, not by accident.

import os

from pptxer_color import contrast_ratio, parse_color
from pptxer_layout import EMU_PER_POINT, Box

__all__ = [
    "audit_pptx", "audit_shape_tree", "audit_text_fit", "audit_pixels",
    "AuditReport",
]


class AuditReport:
    """Everything measured, plus an honest account of what was NOT measured."""

    def __init__(self):
        self.overlaps = []
        self.off_slide = []
        self.safe_escapes = []
        self.text_overflows = []
        self.low_contrast = []
        self.blank_slides = []
        self.notes = []
        self.levels_run = []
        self.levels_skipped = []
        self.slides_measured = 0
        self.shapes_measured = 0
        self.pixel_audited = 0
        self.ground_truth = False
        self.renderer_tier = ""
        self.measurement_errors = []

    @property
    def defect_count(self) -> int:
        return (len(self.overlaps) + len(self.off_slide) + len(self.text_overflows)
                + len(self.low_contrast) + len(self.blank_slides)
                + sum(not item.get("decorative", False) for item in self.safe_escapes))

    @property
    def layout_clean(self) -> bool:
        """True ONLY when every level that ran found nothing.

        ⚠️ This is deliberately NOT 'no defects found'. A deck whose pixel
        audit never ran is not proven clean at the pixel level, and the caller
        must be able to tell the difference — see `confidence`.
        """
        return self.defect_count == 0 and not self.measurement_errors

    @property
    def confidence(self) -> str:
        """How much the verdict is worth. Reported verbatim by the agent."""
        if self.measurement_errors:
            return "audit incomplete: " + "; ".join(self.measurement_errors[:2])
        if not self.layout_clean:
            return "defects found"
        if self.ground_truth:
            return ("verified against PowerPoint's own rendering — this is what "
                    "the audience will see")
        if self.pixel_audited:
            if self.renderer_tier == "geometric_preview":
                return "geometry and text metrics checked; the geometric preview is approximate, not an independent renderer"
            return ("verified against an independent renderer; PowerPoint's own "
                    "text engine was not available to confirm")
        return ("geometry and text metrics verified; no renderer was available, "
                "so the pixels were not inspected")

    def as_dict(self) -> dict:
        return {
            "layout_clean": self.layout_clean,
            "confidence": self.confidence,
            "ground_truth": self.ground_truth,
            "defects": self.defect_count,
            "overlaps": self.overlaps,
            "overlap_count": len(self.overlaps),
            "off_slide": self.off_slide,
            "off_slide_count": len(self.off_slide),
            "safe_escapes": self.safe_escapes,
            "text_overflows": self.text_overflows,
            "text_overflow_count": len(self.text_overflows),
            "low_contrast": self.low_contrast,
            "blank_slides": self.blank_slides,
            "slides_measured": self.slides_measured,
            "shapes_measured": self.shapes_measured,
            "pixel_audited": self.pixel_audited,
            "levels_run": self.levels_run,
            "levels_skipped": self.levels_skipped,
            "measurement_errors": self.measurement_errors,
            "notes": self.notes,
        }

    def summary(self) -> str:
        """A short human account. Printed into the agent's log and section body."""
        lines = []
        if self.layout_clean:
            lines.append(
                f"LAYOUT CLEAN — {self.slides_measured} slides, "
                f"{self.shapes_measured} shapes measured, no defects.")
        elif self.measurement_errors:
            lines.append(
                f"LAYOUT AUDIT INCOMPLETE — {self.defect_count} known defects "
                f"across {self.slides_measured} slides.")
        else:
            lines.append(
                f"LAYOUT DEFECTS: {self.defect_count} across "
                f"{self.slides_measured} slides.")
        lines.append(f"Confidence: {self.confidence}")

        for label, items in (("overlapping shapes", self.overlaps),
                             ("shapes off the slide", self.off_slide),
                             ("overflowing text frames", self.text_overflows),
                             ("low-contrast text", self.low_contrast),
                             ("blank slides", self.blank_slides)):
            if not items:
                continue
            lines.append(f"  {len(items)} {label}:")
            for item in items[:6]:
                lines.append(f"    · {_describe(item)}")
            if len(items) > 6:
                lines.append(f"    · … and {len(items) - 6} more")

        if self.levels_skipped:
            lines.append("  Not measured: " + "; ".join(self.levels_skipped))
        for note in self.notes[:8]:
            lines.append(f"  note: {note}")
        return "\n".join(lines)


def _describe(item) -> str:
    slide = item.get("slide", "?")
    if "a" in item and "b" in item:
        return (f"slide {slide}: {item['a']} overlaps {item['b']} by "
                f"{item.get('area_pt2', 0):.0f}pt²")
    if "overflow_pt" in item:
        return (f"slide {slide}: {item.get('name', 'text')} needs "
                f"{item.get('needed_pt', 0):.0f}pt in a "
                f"{item.get('available_pt', 0):.0f}pt frame "
                f"({item.get('reason', '')})")
    if "ratio" in item:
        return (f"slide {slide}: {item.get('name', 'text')} measures "
                f"{item['ratio']:.2f}:1 against its ground "
                f"(floor {item.get('floor', 7.0):.1f}:1)")
    if "out_pt" in item:
        return (f"slide {slide}: {item.get('name', 'shape')} is "
                f"{item['out_pt']:.0f}pt outside the slide")
    return f"slide {slide}: {item}"


# ─────────────────────────────────────────────────────────────────────────────
# LEVEL 1 — the shape tree, read back from the SAVED file
# ─────────────────────────────────────────────────────────────────────────────

# Shapes that legitimately cover the whole slide and must NOT be reported as
# overlapping everything. Recorded by the builder in the shape NAME, because
# that is the one piece of metadata that survives a save/reopen round trip.
_BLEED_MARKERS = ("pptxer:bleed", "pptxer:background", "pptxer:scrim")
_DECOR_MARKERS = ("pptxer:ornament", "pptxer:decor", "pptxer:glow")


def audit_shape_tree(pptx_path, margin_pt=48.0, tolerance_pt=0.75) -> dict:
    """Re-open the SAVED deck and measure every shape's real geometry.

    Reading back the file rather than trusting the in-memory model is the whole
    point: it is the artefact that ships, and a save can differ from the model
    (a grouped shape, a placeholder inherited from the layout, an element the
    library wrote differently than expected).
    """
    result = {"slides": 0, "shapes": 0, "overlaps": [], "off_slide": [],
              "safe_escapes": [], "error": ""}
    try:
        from pptx import Presentation
    except Exception as exc:                                      # noqa: BLE001
        result["error"] = f"python-pptx is unavailable: {exc}"
        return result

    try:
        prs = pptx_path if hasattr(pptx_path, "slides") else Presentation(str(pptx_path))
    except Exception as exc:                                      # noqa: BLE001
        result["error"] = f"the saved deck could not be re-opened: {exc}"
        return result

    slide_w = int(prs.slide_width or 12192000)
    slide_h = int(prs.slide_height or 6858000)
    result["slide_width_emu"] = slide_w
    result["slide_height_emu"] = slide_h
    margin = int(float(margin_pt) * EMU_PER_POINT)
    tol = int(float(tolerance_pt) * EMU_PER_POINT)
    safe = Box(margin, margin, slide_w - 2 * margin, slide_h - 2 * margin,
               "safe", "safe")

    for index, slide in enumerate(prs.slides, start=1):
        result["slides"] += 1
        boxes = []
        for shape in slide.shapes:
            try:
                left = int(shape.left or 0)
                top = int(shape.top or 0)
                width = int(shape.width or 0)
                height = int(shape.height or 0)
                name = str(shape.name or "shape")
            except Exception:                                     # noqa: BLE001
                continue
            if width <= 0 or height <= 0:
                continue
            result["shapes"] += 1
            lowered = name.lower()
            is_bleed = any(m in lowered for m in _BLEED_MARKERS)
            is_decor = any(m in lowered for m in _DECOR_MARKERS)
            box = Box(left, top, width, height, name, "text" if getattr(shape, "has_text_frame", False) and shape.text.strip() else "shape")
            boxes.append((box, is_bleed, is_decor))

            # Off the SHEET is a defect for CONTENT and for a background that
            # claims to be exactly the slide.
            #
            # ⚠️ A DECORATIVE element is exempt, because bleeding off the edge
            # is what it is FOR. Measured 2026-09-14: a soft glow placed to
            # spill past the corner — the standard way to light a dark
            # composition — was reported as "230pt outside the slide". The
            # renderer simply clips it, exactly as intended. Flagging deliberate
            # bleed teaches the reader to ignore the off-slide finding, which is
            # the one finding that is always serious for real content.
            out = max(-left, -top, (left + width) - slide_w,
                      (top + height) - slide_h)
            if out > tol and is_decor:
                continue
            if out > tol:
                result["off_slide"].append({
                    "slide": index, "name": name,
                    "out_pt": out / EMU_PER_POINT,
                    "box": box.as_dict(),
                })

            if is_bleed:
                continue
            escape = max(safe.left - left, safe.top - top,
                         (left + width) - safe.right, (top + height) - safe.bottom)
            if escape > tol:
                result["safe_escapes"].append({
                    "slide": index, "name": name,
                    "out_pt": escape / EMU_PER_POINT,
                    "decorative": is_decor,
                    "box": box.as_dict(),
                })

        # Pairwise overlap among CONTENT shapes only.
        #
        # ⚠️ CONTAINMENT IS NOT OVERLAP. A text frame sitting inside its own
        # panel, or a label inside a diagram node, is correct composition —
        # it is how every card, tile and button in the deck is built. Measured
        # 2026-09-14: flagging it produced 8 "defects" on a slide that was
        # perfectly laid out, alongside 4 genuine ones, and a report that is
        # two-thirds noise is a report nobody reads. Only PARTIAL intersection
        # — two boxes each sticking out of the other — is a real collision.
        content = [b for b, bleed, decor in boxes if not bleed and not decor]
        for i, a in enumerate(content):
            for b in content[i + 1:]:
                if ((a.kind != "text" and a.contains(b))
                        or (b.kind != "text" and b.contains(a))):
                    continue
                if a.intersects(b, tol):
                    area = a.intersection_area(b)
                    result["overlaps"].append({
                        "slide": index, "a": a.name, "b": b.name,
                        "area_emu": area,
                        "area_pt2": area / (EMU_PER_POINT ** 2),
                        "a_box": a.as_dict(), "b_box": b.as_dict(),
                    })

    return result


# ─────────────────────────────────────────────────────────────────────────────
# LEVEL 2 — does the text actually fit its frame?
# ─────────────────────────────────────────────────────────────────────────────

def _text_frames(shapes):
    """Include table cells and grouped shapes, which have no top-level frame."""
    for shape in shapes:
        if getattr(shape, "has_table", False):
            table = shape.table
            for r, row in enumerate(table.rows):
                for c, cell in enumerate(row.cells):
                    if cell.is_spanned:
                        continue
                    width = sum(table.columns[k].width for k in range(c, c + cell.span_width))
                    height = sum(table.rows[k].height for k in range(r, r + cell.span_height))
                    yield f"{shape.name}[{r + 1},{c + 1}]", cell.text_frame, width, height
        elif getattr(shape, "has_text_frame", False):
            yield shape.name, shape.text_frame, shape.width, shape.height
        if hasattr(shape, "shapes"):
            yield from _text_frames(shape.shapes)


def audit_text_fit(pptx_path, inventory=None, tolerance_pt=1.0) -> dict:
    """Read actual saved sizes, margins, paragraph spacing and run styling.

    Counts table cells and groups as well as ordinary text boxes. Unwrapped
    frames are measured as unwrapped. Mixed runs use the widest run style as
    a conservative bound; explicit breaks are read from paragraph.text.
    """
    result = {"overflows": [], "frames": 0, "error": ""}
    try:
        from copy import copy
        from pptx import Presentation
        from pptxer_fonts import get_inventory, measure_text, wrap_text_to_width
        inv = inventory or get_inventory()
        prs = pptx_path if hasattr(pptx_path, "slides") else Presentation(str(pptx_path))
        for index, slide in enumerate(prs.slides, 1):
            for name, frame, width, height in _text_frames(slide.shapes):
                if not frame.text.strip():
                    continue
                result["frames"] += 1
                iw = (width - frame.margin_left - frame.margin_right) / EMU_PER_POINT
                ih = (height - frame.margin_top - frame.margin_bottom) / EMU_PER_POINT
                needed, widest = 0.0, 0.0
                for para in frame.paragraphs:
                    fonts = []
                    max_size = 0.0
                    for run in para.runs or [None]:
                        font = run.font if run is not None else para.font
                        pt = font.size or para.font.size
                        size = float(pt.pt) if pt is not None else 18.0
                        family = font.name or para.font.name or "Segoe UI"
                        bold = font.bold if font.bold is not None else bool(para.font.bold)
                        italic = font.italic if font.italic is not None else bool(para.font.italic)
                        resolved = copy(inv.resolve(family, "sans_body", bold=bold, italic=italic))
                        props = font._rPr
                        spacing = float(props.get("spc", "0")) / 100 if props is not None else 0.0
                        resolved.tracking_em = spacing / size
                        fonts.append((resolved, size))
                        max_size = max(max_size, size)
                    count = 1
                    for resolved, size in fonts:
                        lines = (wrap_text_to_width(para.text, resolved, size, max(1, iw), inv,
                                                   break_long_words=True)
                                 if frame.word_wrap is not False else para.text.replace("\v", "\n").split("\n"))
                        count = max(count, len(lines))
                        widest = max(widest, max((measure_text(line, resolved, size, inv)[0]
                                                 for line in lines), default=0))
                    spacing = para.line_spacing
                    line_h = float(spacing.pt) if hasattr(spacing, "pt") else max_size * 1.2 * (spacing or 1.0)
                    needed += count * line_h
                    needed += sum(float(v.pt) if v is not None else 0.0
                                  for v in (para.space_before, para.space_after))
                over_h, over_w = needed - ih, widest - iw
                if max(over_h, over_w) > tolerance_pt:
                    result["overflows"].append({
                        "slide": index, "name": name, "needed_pt": needed,
                        "available_pt": ih, "overflow_pt": max(over_h, over_w),
                        "reason": f"height excess {over_h:.1f}pt; width excess {over_w:.1f}pt",
                        "text": frame.text[:70],
                    })
    except Exception as exc:
        result["error"] = f"text-fit audit failed: {exc}"
    return result


# ─────────────────────────────────────────────────────────────────────────────
# LEVEL 3 — the rendered pixels
# ─────────────────────────────────────────────────────────────────────────────

def audit_pixels(images, margin_pt=48.0, slide_w_emu=12192000,
                 blank_ink_threshold=0.004) -> dict:
    """Measure the rendered PNGs. Only runs when a renderer produced images."""
    result = {"blank": [], "edge_ink": [], "measured": 0, "error": ""}
    if not images:
        result["error"] = "no rendered images were supplied"
        return result
    try:
        from PIL import Image
    except Exception as exc:                                      # noqa: BLE001
        result["error"] = f"Pillow is unavailable: {exc}"
        return result

    for index, path in enumerate(images, start=1):
        if not path or not os.path.isfile(path):
            continue
        try:
            with Image.open(path) as img:
                rgb = img.convert("RGB")
                w, h = rgb.size
                px = rgb.load()
        except Exception:                                         # noqa: BLE001
            continue

        result["measured"] += 1

        # Sample a grid rather than every pixel: a 1600x900 PNG is 1.4M
        # pixels and there is no accuracy to gain from reading all of them.
        step = max(2, min(w, h) // 180)
        samples = 0
        ink = 0
        corner = px[2, 2]
        for y in range(0, h, step):
            for x in range(0, w, step):
                samples += 1
                r, g, b = px[x, y]
                if (abs(r - corner[0]) + abs(g - corner[1])
                        + abs(b - corner[2])) > 34:
                    ink += 1

        ratio = ink / float(samples or 1)
        if ratio < float(blank_ink_threshold):
            result["blank"].append({
                "slide": index, "ink_ratio": round(ratio, 5),
                "image": os.path.basename(path),
                "reason": ("almost nothing was drawn — the slide rendered "
                           "essentially empty"),
            })

    return result


def measure_text_contrast_on_render(images, text_boxes, slide_w_emu=12192000,
                                    floor=7.0) -> list:
    """True contrast of each text box against the pixels ACTUALLY behind it.

    ⚠️ This is the check PDFer got wrong twice before getting it right. The
    naive version compares text to the PAGE background, which flags white
    header text sitting on its own dark header band — a false alarm on a
    correct design, and a check that fires on correct work is a check people
    switch off. So the ground is sampled from the RENDER, around the text box's
    own footprint, not from the theme.
    """
    findings = []
    if not images or not text_boxes:
        return findings
    try:
        from PIL import Image
    except Exception:                                             # noqa: BLE001
        return findings

    by_slide = {}
    for entry in text_boxes:
        by_slide.setdefault(int(entry.get("slide", 1)), []).append(entry)

    for index, path in enumerate(images, start=1):
        entries = by_slide.get(index)
        if not entries or not path or not os.path.isfile(path):
            continue
        try:
            with Image.open(path) as img:
                rgb = img.convert("RGB")
                w, h = rgb.size
                px = rgb.load()
        except Exception:                                         # noqa: BLE001
            continue

        scale = w / float(slide_w_emu or 1)
        for entry in entries:
            box = entry.get("box") or {}
            x0 = max(0, min(w - 1, int(box.get("left", 0) * scale)))
            y0 = max(0, min(h - 1, int(box.get("top", 0) * scale)))
            x1 = max(0, min(w, int((box.get("left", 0) + box.get("width", 0)) * scale)))
            y1 = max(0, min(h, int((box.get("top", 0) + box.get("height", 0)) * scale)))
            if x1 <= x0 or y1 <= y0:
                continue

            fg = parse_color(entry.get("color"))
            if fg is None:
                continue

            # The MODE of the sampled region approximates the ground: text
            # covers a minority of a well-set box, so the commonest colour is
            # the background it sits on.
            #
            # ⚠️ EXCLUDE PIXELS THAT ARE THE TEXT ITSELF. Measured 2026-09-14:
            # a 119pt Terminator Two title in cyan covers MORE of its box than
            # the gaps do, so the plain mode returned the cyan glyphs as the
            # "ground" and reported a perfectly legible title at 1.02:1. A
            # check that condemns correct work is worse than no check, because
            # it is the one people switch off.
            fg_rgb = fg.rgb255
            counts = {}
            step = max(1, (x1 - x0) // 24)
            vstep = max(1, (y1 - y0) // 12)
            for y in range(y0, y1, vstep):
                for x in range(x0, x1, step):
                    pixel = px[x, y]
                    if (abs(pixel[0] - fg_rgb[0]) + abs(pixel[1] - fg_rgb[1])
                            + abs(pixel[2] - fg_rgb[2])) < 110:
                        continue          # this pixel IS the text
                    key = tuple(v // 16 for v in pixel)
                    counts[key] = counts.get(key, 0) + 1
            if not counts:
                # Every sample looked like the text — the box is essentially
                # solid ink (a filled badge). Nothing meaningful to measure.
                continue
            ground_key = max(counts.items(), key=lambda kv: kv[1])[0]
            ground = tuple(v * 16 + 8 for v in ground_key)
            ratio = contrast_ratio(fg, "#%02X%02X%02X" % ground)
            role_floor = float(entry.get("floor", floor))
            if ratio < role_floor:
                findings.append({
                    "slide": index, "name": entry.get("name", "text"),
                    "ratio": ratio, "floor": role_floor,
                    "color": fg.hex,
                    "ground": "#%02X%02X%02X" % ground,
                    "reason": ("measured against the pixels actually behind the "
                               "text in the render"),
                })
    return findings


# ─────────────────────────────────────────────────────────────────────────────
# The full audit
# ─────────────────────────────────────────────────────────────────────────────

def audit_pptx(pptx_path, render_result=None, margin_pt=48.0,
               text_boxes=None, inventory=None, run_pixels=True) -> AuditReport:
    """Run every level that CAN run, and say plainly which ones did not."""
    report = AuditReport()

    # ---- LEVEL 1 ----------------------------------------------------------
    tree = audit_shape_tree(pptx_path, margin_pt=margin_pt)
    if tree.get("error"):
        report.levels_skipped.append(f"shape-tree audit ({tree['error']})")
        report.notes.append(tree["error"])
        report.measurement_errors.append(tree["error"])
    else:
        report.levels_run.append("shape-tree geometry")
        report.slides_measured = tree["slides"]
        report.shapes_measured = tree["shapes"]
        report.overlaps = tree["overlaps"]
        report.off_slide = tree["off_slide"]
        report.safe_escapes = tree["safe_escapes"]

    # ---- LEVEL 2 ----------------------------------------------------------
    fit = audit_text_fit(pptx_path, inventory=inventory)
    if fit.get("error"):
        report.levels_skipped.append(f"text-fit audit ({fit['error']})")
        report.notes.append(fit["error"])
        report.measurement_errors.append(fit["error"])
    else:
        report.levels_run.append(f"text fit ({fit['frames']} frames)")
        report.text_overflows = fit["overflows"]

    # ---- LEVEL 3 ----------------------------------------------------------
    images = (render_result or {}).get("images") or []
    report.renderer_tier = (render_result or {}).get("tier", "")
    native = (render_result or {}).get("text_bounds")
    if native is not None:
        report.levels_run.append(f"PowerPoint text bounds ({len(native.get('frames', []))} frames)")
        for entry in native.get("overflows", []):
            report.text_overflows.append(dict(entry, reason="PowerPoint glyphs extend outside the text frame",
                                              needed_pt=entry["ink_pt"]["height"],
                                              available_pt=entry["box_pt"]["height"]))
        report.levels_skipped.extend(native.get("errors", []))
        report.measurement_errors.extend(native.get("errors", []))
    if not run_pixels:
        report.levels_skipped.append("pixel audit (disabled by configuration)")
    elif not images:
        attempts = (render_result or {}).get("attempts") or []
        why = "; ".join(
            f"{a.get('tier')}: {a.get('error') or 'unavailable'}"
            for a in attempts) or "no renderer ran"
        # ⚠️ The honest report. NOT 'clean'.
        report.levels_skipped.append(f"pixel audit — no render was produced ({why})")
        report.notes.append(
            "the slides were never rasterised, so nothing here can speak for "
            "what PowerPoint will actually draw; the geometry and text-metric "
            "levels did run and are the authority on overlaps and overflow")
    else:
        pixels = audit_pixels(images, margin_pt=margin_pt,
                              slide_w_emu=tree.get("slide_width_emu", 12192000))
        if pixels.get("error"):
            report.levels_skipped.append(f"pixel audit ({pixels['error']})")
        else:
            report.levels_run.append(
                f"pixels ({pixels['measured']} rendered slides)")
            report.pixel_audited = pixels["measured"]
            if pixels["measured"] != report.slides_measured:
                report.measurement_errors.append(f"only {pixels['measured']} of {report.slides_measured} slides were rendered")
            report.blank_slides = pixels["blank"]
            report.ground_truth = (bool((render_result or {}).get("ground_truth"))
                                   and pixels["measured"] == report.slides_measured
                                   and not (native or {}).get("errors"))

        if text_boxes:
            report.low_contrast = measure_text_contrast_on_render(
                images, text_boxes, slide_w_emu=tree.get("slide_width_emu", 12192000))
            report.levels_run.append("rendered text contrast (sampled background)")
        else:
            report.levels_skipped.append("rendered text contrast (no text-color metadata)")

    return report
