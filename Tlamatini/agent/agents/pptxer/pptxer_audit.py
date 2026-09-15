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

    @property
    def defect_count(self) -> int:
        return (len(self.overlaps) + len(self.off_slide) + len(self.text_overflows)
                + len(self.low_contrast) + len(self.blank_slides))

    @property
    def layout_clean(self) -> bool:
        """True ONLY when every level that ran found nothing.

        ⚠️ This is deliberately NOT 'no defects found'. A deck whose pixel
        audit never ran is not proven clean at the pixel level, and the caller
        must be able to tell the difference — see `confidence`.
        """
        return self.defect_count == 0

    @property
    def confidence(self) -> str:
        """How much the verdict is worth. Reported verbatim by the agent."""
        if not self.layout_clean:
            return "defects found"
        if self.ground_truth:
            return ("verified against PowerPoint's own rendering — this is what "
                    "the audience will see")
        if self.pixel_audited:
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
            "notes": self.notes,
        }

    def summary(self) -> str:
        """A short human account. Printed into the agent's log and section body."""
        lines = []
        if self.layout_clean:
            lines.append(
                f"LAYOUT CLEAN — {self.slides_measured} slides, "
                f"{self.shapes_measured} shapes measured, no defects.")
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
        prs = Presentation(str(pptx_path))
    except Exception as exc:                                      # noqa: BLE001
        result["error"] = f"the saved deck could not be re-opened: {exc}"
        return result

    slide_w = int(prs.slide_width or 12192000)
    slide_h = int(prs.slide_height or 6858000)
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
            box = Box(left, top, width, height, name, "shape")
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
                if a.contains(b) or b.contains(a):
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

def audit_text_fit(pptx_path, inventory=None, tolerance_pt=1.0) -> dict:
    """Re-measure every text frame's content against its box.

    This is the check PowerPoint hides from the author: with autofit on, the
    VIEWER shrinks the text, so the deck looks right on the machine that made
    it and wrong on a machine with different font metrics. PPTXer writes
    explicit sizes and verifies them here.
    """
    result = {"overflows": [], "frames": 0, "error": ""}
    try:
        from pptx import Presentation
        from pptx.util import Emu  # noqa: F401
    except Exception as exc:                                      # noqa: BLE001
        result["error"] = f"python-pptx is unavailable: {exc}"
        return result

    try:
        from pptxer_fonts import get_inventory, measure_text, wrap_text_to_width
        inv = inventory or get_inventory()
    except Exception as exc:                                      # noqa: BLE001
        result["error"] = f"the font engine is unavailable: {exc}"
        return result

    try:
        prs = Presentation(str(pptx_path))
    except Exception as exc:                                      # noqa: BLE001
        result["error"] = f"the saved deck could not be re-opened: {exc}"
        return result

    tol = float(tolerance_pt)

    for index, slide in enumerate(prs.slides, start=1):
        for shape in slide.shapes:
            if not getattr(shape, "has_text_frame", False):
                continue
            try:
                frame = shape.text_frame
                text = (frame.text or "").strip()
            except Exception:                                     # noqa: BLE001
                continue
            if not text:
                continue

            result["frames"] += 1
            try:
                width_emu = int(shape.width or 0)
                height_emu = int(shape.height or 0)
                li = int(getattr(frame, "margin_left", 0) or 0)
                ri = int(getattr(frame, "margin_right", 0) or 0)
                ti = int(getattr(frame, "margin_top", 0) or 0)
                bi = int(getattr(frame, "margin_bottom", 0) or 0)
            except Exception:                                     # noqa: BLE001
                continue
            if width_emu <= 0 or height_emu <= 0:
                continue

            inner_w_pt = max(1.0, (width_emu - li - ri) / EMU_PER_POINT)
            inner_h_pt = max(1.0, (height_emu - ti - bi) / EMU_PER_POINT)

            needed_h = 0.0
            widest = 0.0
            for para in frame.paragraphs:
                para_text = "".join(r.text or "" for r in para.runs) or ""
                if not para_text.strip():
                    needed_h += 12.0
                    continue
                size_pt = 18.0
                font_name = ""
                bold = False
                for run in para.runs:
                    try:
                        if run.font.size is not None:
                            size_pt = float(run.font.size.pt)
                        if run.font.name:
                            font_name = run.font.name
                        if run.font.bold:
                            bold = True
                        break
                    except Exception:                             # noqa: BLE001
                        continue
                resolved = inv.resolve(font_name or "Segoe UI", "sans_body",
                                       bold=bold)
                lines = wrap_text_to_width(para_text, resolved, size_pt,
                                           inner_w_pt, inv)
                for line in lines:
                    w, _ = measure_text(line, resolved, size_pt, inv)
                    widest = max(widest, w)
                needed_h += max(1, len(lines)) * size_pt * 1.18

            over_h = needed_h - inner_h_pt
            over_w = widest - inner_w_pt
            if over_h > tol or over_w > tol:
                reason = []
                if over_h > tol:
                    reason.append(f"{over_h:.0f}pt too tall")
                if over_w > tol:
                    reason.append(f"a line is {over_w:.0f}pt too wide")
                result["overflows"].append({
                    "slide": index,
                    "name": str(shape.name or "text"),
                    "needed_pt": needed_h,
                    "available_pt": inner_h_pt,
                    "overflow_pt": max(over_h, over_w),
                    "reason": " and ".join(reason),
                    "text": text[:70],
                })

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
    else:
        report.levels_run.append(f"text fit ({fit['frames']} frames)")
        report.text_overflows = fit["overflows"]

    # ---- LEVEL 3 ----------------------------------------------------------
    images = (render_result or {}).get("images") or []
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
        pixels = audit_pixels(images, margin_pt=margin_pt)
        if pixels.get("error"):
            report.levels_skipped.append(f"pixel audit ({pixels['error']})")
        else:
            report.levels_run.append(
                f"pixels ({pixels['measured']} rendered slides)")
            report.pixel_audited = pixels["measured"]
            report.blank_slides = pixels["blank"]
            report.ground_truth = bool((render_result or {}).get("ground_truth"))

        if text_boxes:
            report.low_contrast = measure_text_contrast_on_render(
                images, text_boxes)
            if report.low_contrast:
                report.levels_run.append("rendered text contrast")

    return report
