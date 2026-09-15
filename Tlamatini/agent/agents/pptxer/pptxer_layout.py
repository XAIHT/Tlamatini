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
# pptxer_layout.py — THE GEOMETRY SOLVER.  PPTXer's most important module.
#
# Sibling module of pptxer.py (flat neighbour, NOT a package). Stdlib + the
# sibling pptxer_fonts. Imports nothing from agent.*.
#
# ═════════════════════════════════════════════════════════════════════════════
#  WHY THIS MODULE EXISTS  —  the PDFer lesson, applied one layer earlier
# ═════════════════════════════════════════════════════════════════════════════
# PDFer (2026-09-06) shipped three ordinary tables that produced EIGHT cell-on-
# cell overlaps and a path 54pt off the sheet, while the renderer reported
# `err = 0` every single time. The root cause was that xhtml2pdf owned the
# layout and sized columns from a character-count guess.
#
# PPTX is different in one decisive way: **python-pptx does not lay anything
# out.** Every shape is placed by US at absolute EMU coordinates. So overlap is
# not something to detect afterwards — it is something to make IMPOSSIBLE.
#
# That is what this module does. It is a placement engine with ONE invariant:
#
#     ┌──────────────────────────────────────────────────────────────────┐
#     │  NO TWO PLACED BOXES MAY INTERSECT, AND NO BOX MAY LEAVE THE     │
#     │  SLIDE'S SAFE AREA.  A placement that cannot satisfy both is     │
#     │  REFUSED and reported — never silently emitted.                  │
#     └──────────────────────────────────────────────────────────────────┘
#
# Text is measured with the REAL font file at the REAL point size (see
# pptxer_fonts), so a box is sized for what will actually render, not for a
# half-em estimate that is −38% wrong on capital W's.
#
# ═════════════════════════════════════════════════════════════════════════════
#  WHAT THIS MODULE CANNOT GUARANTEE  (and therefore reports honestly)
# ═════════════════════════════════════════════════════════════════════════════
# PowerPoint re-flows text when it OPENS the file, using its own line-breaking
# and its own copy of the font. Three consequences PPTXer must not paper over:
#
#   · If the opening machine lacks the named font, PowerPoint substitutes, and
#     the substitute may be wider. PPTXer's answer: measure the SUBSTITUTE it
#     would itself pick, prefer portable core fonts for body text, and set an
#     explicit size rather than relying on autofit.
#   · PowerPoint's autofit ("shrink text on overflow") is applied by the VIEWER
#     and is not recorded as a final size in the file. A deck that depends on it
#     looks different everywhere. PPTXer therefore SOLVES the size itself and
#     writes it explicitly — autofit is left off by design.
#   · Kerning and justification differ by a hair between renderers. Every box
#     therefore carries a SAFETY INSET (see TEXT_SAFETY_INSET) so a hair never
#     becomes a clipped descender.
#
# This is why the render+audit ladder in pptxer_render/pptxer_audit still runs:
# this module prevents the failures it can prove, and the audit verifies the
# ones only a real renderer can settle. Prevention and verification, not one or
# the other.

import math

from pptxer_fonts import TEXT_RENDER_GUARD_PT, fit_point_size, font_for_text, get_inventory, line_height_pt, measure_text, wrap_text_to_width

__all__ = [
    "EMU_PER_INCH", "EMU_PER_POINT", "EMU_PER_CM",
    "SLIDE_SIZES", "Box", "SlideCanvas", "GridSolver",
    "PlacementError", "solve_columns", "distribute", "fit_image_box",
    "TEXT_SAFETY_INSET",
]

# ─────────────────────────────────────────────────────────────────────────────
# Units. PPTX speaks EMU (English Metric Units) — 914400 per inch, chosen
# because it divides evenly by both 72 (points) and 2.54 (centimetres), so
# conversions are EXACT integers with no accumulated rounding drift.
# ─────────────────────────────────────────────────────────────────────────────

EMU_PER_INCH = 914400
EMU_PER_POINT = 12700          # 914400 / 72
EMU_PER_CM = 360000

SLIDE_SIZES = {
    # name: (width_emu, height_emu, label)
    "16:9":      (12192000, 6858000, "13.333 x 7.5 in — widescreen (PowerPoint default)"),
    "16:10":     (12192000, 7620000, "13.333 x 8.333 in — widescreen 16:10"),
    "4:3":       (9144000, 6858000, "10 x 7.5 in — classic"),
    "a4_land":   (10692130, 7559040, "A4 landscape"),
    "a4_port":   (7559040, 10692130, "A4 portrait"),
    "letter":    (9906000, 7645400, "US Letter landscape"),
    "square":    (9144000, 9144000, "10 x 10 in — social square"),
    "vertical":  (6858000, 12192000, "7.5 x 13.333 in — stories / reels / TikTok"),
    "cinema":    (12192000, 5222875, "2.35:1 — cinematic key-art"),
    "ultrawide": (12192000, 5143500, "21:9 — ultrawide"),
}

# Every text box is inset by this much on each side before measuring. It
# absorbs the small disagreements between PIL's metrics and PowerPoint's
# renderer (kerning tables, hinting, the trailing side bearing) so a line that
# measures at exactly the box width does not clip its last glyph.
TEXT_SAFETY_INSET = 2.0 * EMU_PER_POINT


class PlacementError(Exception):
    """A box could not be placed without violating the invariant.

    Raised ONLY by the strict APIs. The forgiving APIs return a diagnostic
    instead, because a deck that refuses to build is usually worse than a deck
    that builds with one honestly-reported compromise.
    """


class Box:
    """An axis-aligned rectangle in EMU, with the slide's origin at top-left."""

    __slots__ = ("left", "top", "width", "height", "name", "kind", "z")

    def __init__(self, left, top, width, height, name="", kind="generic", z=0):
        self.left = int(round(left))
        self.top = int(round(top))
        self.width = max(0, int(round(width)))
        self.height = max(0, int(round(height)))
        self.name = name
        self.kind = kind
        self.z = int(z)

    # -- derived edges --------------------------------------------------------

    @property
    def right(self) -> int:
        return self.left + self.width

    @property
    def bottom(self) -> int:
        return self.top + self.height

    @property
    def center_x(self) -> int:
        return self.left + self.width // 2

    @property
    def center_y(self) -> int:
        return self.top + self.height // 2

    @property
    def area(self) -> int:
        return self.width * self.height

    # -- geometry -------------------------------------------------------------

    def intersects(self, other: "Box", tolerance: int = 0) -> bool:
        """STRICT intersection. A shared edge is NOT an intersection.

        `tolerance` shrinks both boxes before testing, which is how a deliberate
        1-EMU abutment (two panels sharing a seam) avoids being reported as an
        overlap while a real 3pt collision still is.
        """
        t = int(tolerance)
        return not (
            self.right - t <= other.left + t
            or other.right - t <= self.left + t
            or self.bottom - t <= other.top + t
            or other.bottom - t <= self.top + t
        )

    def intersection_area(self, other: "Box") -> int:
        dx = min(self.right, other.right) - max(self.left, other.left)
        dy = min(self.bottom, other.bottom) - max(self.top, other.top)
        return dx * dy if dx > 0 and dy > 0 else 0

    def contains(self, other: "Box") -> bool:
        return (self.left <= other.left and self.top <= other.top
                and self.right >= other.right and self.bottom >= other.bottom)

    def inset(self, amount) -> "Box":
        """Shrink on all four sides. Accepts a scalar or (l, t, r, b)."""
        if isinstance(amount, (tuple, list)) and len(amount) == 4:
            li, ti, ri, bi = (int(v) for v in amount)
        else:
            li = ti = ri = bi = int(amount)
        return Box(self.left + li, self.top + ti,
                   max(0, self.width - li - ri), max(0, self.height - ti - bi),
                   self.name, self.kind, self.z)

    def offset(self, dx=0, dy=0) -> "Box":
        return Box(self.left + dx, self.top + dy, self.width, self.height,
                   self.name, self.kind, self.z)

    def resized(self, width=None, height=None) -> "Box":
        return Box(self.left, self.top,
                   self.width if width is None else width,
                   self.height if height is None else height,
                   self.name, self.kind, self.z)

    def as_dict(self) -> dict:
        return {
            "name": self.name, "kind": self.kind,
            "left": self.left, "top": self.top,
            "width": self.width, "height": self.height,
            "right": self.right, "bottom": self.bottom, "z": self.z,
        }

    # -- unit helpers ---------------------------------------------------------

    @property
    def left_pt(self) -> float:
        return self.left / EMU_PER_POINT

    @property
    def top_pt(self) -> float:
        return self.top / EMU_PER_POINT

    @property
    def width_pt(self) -> float:
        return self.width / EMU_PER_POINT

    @property
    def height_pt(self) -> float:
        return self.height / EMU_PER_POINT

    @property
    def width_in(self) -> float:
        return self.width / EMU_PER_INCH

    @property
    def height_in(self) -> float:
        return self.height / EMU_PER_INCH

    @property
    def aspect(self) -> float:
        return (self.width / self.height) if self.height else 0.0

    def __repr__(self) -> str:
        return (f"Box({self.name or self.kind}: "
                f"{self.left_pt:.0f},{self.top_pt:.0f} "
                f"{self.width_pt:.0f}x{self.height_pt:.0f}pt)")


class SlideCanvas:
    """One slide's placement authority. Nothing is placed except through it.

    It owns the safe area, tracks every occupied box, and refuses (or reports)
    any placement that would break the invariant. Because ALL placement goes
    through one object, "did anything overlap?" is answerable exactly, at build
    time, with no rendering.
    """

    def __init__(self, size="16:9", margin_pt=48.0, gutter_pt=20.0,
                 inventory=None):
        if isinstance(size, (tuple, list)) and len(size) >= 2:
            self.width, self.height = int(size[0]), int(size[1])
            self.size_name = "custom"
        else:
            key = str(size or "16:9").strip().lower()
            spec = SLIDE_SIZES.get(key) or SLIDE_SIZES["16:9"]
            self.width, self.height = spec[0], spec[1]
            self.size_name = key if key in SLIDE_SIZES else "16:9"

        self.margin = int(round(float(margin_pt) * EMU_PER_POINT))
        self.gutter = int(round(float(gutter_pt) * EMU_PER_POINT))
        self._placed = []
        self._reserved = []      # full-bleed art: does not block text placement
        self._diagnostics = []
        self._inventory = inventory or get_inventory()

    # -- areas ----------------------------------------------------------------

    @property
    def bleed(self) -> Box:
        """The whole slide, including the region art may cover."""
        return Box(0, 0, self.width, self.height, "bleed", "bleed")

    @property
    def safe(self) -> Box:
        """The margin-inset area where CONTENT lives.

        Nothing readable may leave this. On a projected slide the outer inch is
        routinely lost to over-scan, a lectern, a head, or the bottom of a
        badly-aligned screen — so a title that merely fits the sheet can still
        be unreadable in the room.
        """
        return Box(self.margin, self.margin,
                   self.width - 2 * self.margin,
                   self.height - 2 * self.margin,
                   "safe", "safe")

    @property
    def placed(self) -> list:
        return list(self._placed)

    @property
    def diagnostics(self) -> list:
        return list(self._diagnostics)

    def remaining_height(self, region: Box = None) -> int:
        """Vertical EMU still free below everything placed inside `region`."""
        area = region or self.safe
        lowest = area.top
        for box in self._placed:
            if box.intersects(area) or area.intersects(box):
                lowest = max(lowest, box.bottom)
        return max(0, area.bottom - lowest)

    # -- the invariant --------------------------------------------------------

    def collisions(self, box: Box, tolerance: int = 0) -> list:
        return [p for p in self._placed if p.intersects(box, tolerance)]

    def escapes_safe(self, box: Box, tolerance: int = 0) -> bool:
        safe = self.safe
        t = int(tolerance)
        return (box.left < safe.left - t or box.top < safe.top - t
                or box.right > safe.right + t or box.bottom > safe.bottom + t)

    def can_place(self, box: Box, tolerance: int = 0) -> tuple:
        """(ok, reason). Pure query — changes nothing."""
        if box.width <= 0 or box.height <= 0:
            return (False, f"{box.name or box.kind!r} has zero area")
        hits = self.collisions(box, tolerance)
        if hits:
            names = ", ".join(h.name or h.kind for h in hits[:3])
            return (False, f"{box.name or box.kind!r} would overlap {names}")
        if self.escapes_safe(box, tolerance):
            return (False, f"{box.name or box.kind!r} would leave the safe area")
        return (True, "")

    def place(self, box: Box, strict: bool = True, tolerance: int = 0) -> Box:
        """Place `box`, enforcing the invariant.

        strict=True  → raise PlacementError rather than emit a broken slide.
        strict=False → record a diagnostic and place anyway (the caller has
                       decided a reported compromise beats no slide at all).
        """
        ok, reason = self.can_place(box, tolerance)
        if not ok:
            if strict:
                raise PlacementError(reason)
            self._diagnostics.append(reason)
        self._placed.append(box)
        return box

    def reserve_bleed(self, box: Box) -> Box:
        """Record full-bleed artwork WITHOUT blocking content placement.

        A background photo legitimately sits under everything. Treating it as an
        obstacle would make every slide unplaceable; ignoring it entirely would
        lose it from the audit. So it is tracked separately.
        """
        self._reserved.append(box)
        return box

    @property
    def reserved(self) -> list:
        return list(self._reserved)

    # -- flow placement -------------------------------------------------------

    def stack(self, region: Box, heights, spacing_pt=None) -> list:
        """Lay boxes top-to-bottom inside `region`, full width, never overflowing.

        If the requested heights plus spacing exceed the region, EVERY box is
        scaled by the same factor. Uniform scaling preserves the visual rhythm
        the theme intended; dropping or clipping the last item would silently
        lose the author's content.
        """
        gap = self.gutter if spacing_pt is None else int(float(spacing_pt) * EMU_PER_POINT)
        hs = [max(0, int(h)) for h in heights]
        if not hs:
            return []

        total = sum(hs) + gap * (len(hs) - 1)
        if total > region.height and total > 0:
            available = max(0, region.height - gap * (len(hs) - 1))
            scale = available / float(sum(hs)) if sum(hs) else 0.0
            hs = [int(h * scale) for h in hs]
            self._diagnostics.append(
                f"stack in {region.name or 'region'}: content exceeded the region by "
                f"{(total - region.height) / EMU_PER_POINT:.0f}pt; all {len(hs)} boxes "
                f"scaled by {scale:.3f} so nothing was dropped"
            )

        out = []
        y = region.top
        for h in hs:
            out.append(Box(region.left, y, region.width, h, kind="stacked"))
            y += h + gap
        return out

    def columns(self, region: Box, count: int, weights=None,
                gutter_pt=None) -> list:
        """Split `region` into `count` columns whose widths sum EXACTLY to it.

        The final column absorbs the integer remainder, so the columns always
        tile the region perfectly. Distributing the remainder instead would let
        a 1-EMU gap appear between panels — invisible on screen but a genuine
        overlap/gap finding in the audit.
        """
        n = max(1, int(count))
        gap = self.gutter if gutter_pt is None else int(float(gutter_pt) * EMU_PER_POINT)
        total_gap = gap * (n - 1)
        usable = max(0, region.width - total_gap)

        if weights and len(weights) == n:
            try:
                ws = [max(0.0, float(w)) for w in weights]
            except (TypeError, ValueError):
                ws = [1.0] * n
        else:
            ws = [1.0] * n
        if sum(ws) <= 0:
            ws = [1.0] * n

        widths = [int(usable * w / sum(ws)) for w in ws]
        widths[-1] = usable - sum(widths[:-1])      # exact tiling

        out = []
        x = region.left
        for w in widths:
            out.append(Box(x, region.top, w, region.height, kind="column"))
            x += w + gap
        return out

    def rows(self, region: Box, count: int, weights=None, gutter_pt=None) -> list:
        """Split `region` into `count` rows that tile it exactly."""
        n = max(1, int(count))
        gap = self.gutter if gutter_pt is None else int(float(gutter_pt) * EMU_PER_POINT)
        total_gap = gap * (n - 1)
        usable = max(0, region.height - total_gap)

        if weights and len(weights) == n:
            try:
                ws = [max(0.0, float(w)) for w in weights]
            except (TypeError, ValueError):
                ws = [1.0] * n
        else:
            ws = [1.0] * n
        if sum(ws) <= 0:
            ws = [1.0] * n

        heights = [int(usable * w / sum(ws)) for w in ws]
        heights[-1] = usable - sum(heights[:-1])

        out = []
        y = region.top
        for h in heights:
            out.append(Box(region.left, y, region.width, h, kind="row"))
            y += h + gap
        return out

    def grid(self, region: Box, cols: int, rows: int, gutter_pt=None) -> list:
        """A cols×rows grid of cells that tiles `region` exactly, row-major."""
        gap = self.gutter if gutter_pt is None else int(float(gutter_pt) * EMU_PER_POINT)
        row_boxes = self.rows(region, rows, gutter_pt=gap / EMU_PER_POINT)
        cells = []
        for rb in row_boxes:
            cells.extend(self.columns(rb, cols, gutter_pt=gap / EMU_PER_POINT))
        return cells

    # -- text fitting (the anti-overflow core) --------------------------------

    def fit_text(self, text, box: Box, resolved_font, start_pt,
                 min_pt=10.0, line_spacing=1.18, align="left") -> dict:
        """Solve the largest point size at which `text` fits INSIDE `box`.

        Returns a dict carrying the solved size, the wrapped lines, the measured
        extents, and — crucially — an honest ``overflow`` flag with a reason.

        The returned geometry is measured against the box MINUS
        TEXT_SAFETY_INSET on every side, so the answer holds even after
        PowerPoint's renderer disagrees with PIL by a fraction of a point.
        """
        inner = box.inset(TEXT_SAFETY_INSET)
        resolved_font = font_for_text(resolved_font, text, self._inventory)
        max_w_pt = max(1.0, inner.width_pt)
        max_h_pt = max(1.0, inner.height_pt)

        size, lines = fit_point_size(
            str(text or ""), resolved_font, max_w_pt, max_h_pt,
            float(start_pt), float(min_pt), float(line_spacing), self._inventory,
            break_long_words=True,
        )

        widest = 0.0
        for line in lines:
            w, _ = measure_text(line, resolved_font, size, self._inventory)
            widest = max(widest, w)
        line_h = line_height_pt(resolved_font, size, line_spacing, self._inventory)
        total_h = len(lines) * line_h + (TEXT_RENDER_GUARD_PT if lines else 0)

        overflow = False
        reason = ""
        if widest > max_w_pt + 0.01:
            overflow = True
            reason = (f"a line measures {widest:.1f}pt in a {max_w_pt:.1f}pt box "
                      f"even at the minimum size {size:.1f}pt — the longest "
                      f"unbreakable token does not fit")
        elif total_h > max_h_pt + 0.01:
            overflow = True
            reason = (f"{len(lines)} lines need {total_h:.1f}pt in a "
                      f"{max_h_pt:.1f}pt box even at {size:.1f}pt")

        if overflow:
            self._diagnostics.append(f"{box.name or box.kind!r}: {reason}")

        return {
            "size_pt": size,
            "lines": lines,
            "line_count": len(lines),
            "text_width_pt": widest,
            "text_height_pt": total_h,
            "box": box,
            "inner": inner,
            "overflow": overflow,
            "reason": reason,
            "align": align,
            "font": resolved_font,
            "line_spacing": float(line_spacing),
            "line_height_pt": line_h,
        }

    def text_block_height(self, text, box_width_emu, resolved_font, size_pt,
                          line_spacing=1.18) -> int:
        """EMU height a block of text needs at a FIXED size in a fixed width.

        Used when the type size is non-negotiable (a theme's body size) and the
        BOX must grow instead — the opposite direction from fit_text.
        """
        inner_w_pt = max(1.0, (box_width_emu - 2 * TEXT_SAFETY_INSET) / EMU_PER_POINT)
        resolved_font = font_for_text(resolved_font, text, self._inventory)
        lines = wrap_text_to_width(str(text or ""), resolved_font, float(size_pt),
                                   inner_w_pt, self._inventory, break_long_words=True)
        h_pt = max(1, len(lines)) * line_height_pt(resolved_font, size_pt, line_spacing, self._inventory) + TEXT_RENDER_GUARD_PT
        return int(round(h_pt * EMU_PER_POINT)) + 2 * TEXT_SAFETY_INSET

    # -- reporting ------------------------------------------------------------

    def audit(self, tolerance_pt: float = 0.5) -> dict:
        """Prove the invariant over everything placed. Pure geometry, no render.

        This runs on EVERY build, needs no renderer and no external tool, and is
        what makes "no overlaps" a checked fact rather than a hope.
        """
        tol = int(float(tolerance_pt) * EMU_PER_POINT)
        overlaps = []
        for i, a in enumerate(self._placed):
            for b in self._placed[i + 1:]:
                if a.intersects(b, tol):
                    area = a.intersection_area(b)
                    overlaps.append({
                        "a": a.name or a.kind, "b": b.name or b.kind,
                        "area_emu": area,
                        "area_pt2": area / (EMU_PER_POINT ** 2),
                        "a_box": a.as_dict(), "b_box": b.as_dict(),
                    })

        safe = self.safe
        escapes = []
        for box in self._placed:
            if self.escapes_safe(box, tol):
                out_l = max(0, safe.left - box.left)
                out_t = max(0, safe.top - box.top)
                out_r = max(0, box.right - safe.right)
                out_b = max(0, box.bottom - safe.bottom)
                escapes.append({
                    "name": box.name or box.kind,
                    "left_pt": out_l / EMU_PER_POINT,
                    "top_pt": out_t / EMU_PER_POINT,
                    "right_pt": out_r / EMU_PER_POINT,
                    "bottom_pt": out_b / EMU_PER_POINT,
                    "box": box.as_dict(),
                })

        bleeds = []
        for box in self._placed:
            if (box.left < 0 or box.top < 0
                    or box.right > self.width or box.bottom > self.height):
                bleeds.append({"name": box.name or box.kind, "box": box.as_dict()})

        return {
            "placed": len(self._placed),
            "reserved": len(self._reserved),
            "overlaps": overlaps,
            "overlap_count": len(overlaps),
            "safe_escapes": escapes,
            "safe_escape_count": len(escapes),
            "off_slide": bleeds,
            "off_slide_count": len(bleeds),
            "diagnostics": list(self._diagnostics),
            "clean": not overlaps and not escapes and not bleeds,
        }


# ─────────────────────────────────────────────────────────────────────────────
# Column solving — the direct descendant of PDFer's TableSolver
# ─────────────────────────────────────────────────────────────────────────────

def solve_columns(rows, resolved_font, size_pt, total_width_emu,
                  padding_pt=8.0, min_col_pt=44.0, inventory=None,
                  header_font=None) -> dict:
    """Solve table column widths from REAL font metrics.

    This is PDFer's water-fill algorithm, brought across because the failure it
    prevents is identical and because a table is the single most common way a
    slide overflows.

    For every column it measures:
      · MINIMUM  — the widest unbreakable atom (longest single word). A column
        narrower than this cannot render without the text escaping.
      · NATURAL  — the widest whole cell, i.e. the width at which nothing wraps.

    Then it water-fills: give every column its minimum, and share what is left
    in proportion to how much each still wants. The result ALWAYS sums to
    exactly `total_width_emu`.

    ⚠️ The final clamp is not optional. When the minimums alone exceed the
    available width, the columns are scaled down proportionally and
    ``min_violated`` is set — the caller MUST then shrink the type or split the
    table. Emitting columns that sum to more than the slide is exactly the bug
    that produced PDFer's eight overlaps.
    """
    inv = inventory or get_inventory()
    if not rows:
        return {"widths": [], "min_violated": False, "columns": 0,
                "reason": "no rows"}

    ncols = max(len(r) for r in rows)
    pad = float(padding_pt) * 2.0
    hdr_font = header_font or resolved_font

    minimums = [0.0] * ncols
    naturals = [0.0] * ncols

    for row_index, row in enumerate(rows):
        font = hdr_font if row_index == 0 else resolved_font
        for c in range(ncols):
            cell = str(row[c]) if c < len(row) and row[c] is not None else ""
            whole, _ = measure_text(cell, font, size_pt, inv)
            naturals[c] = max(naturals[c], whole + pad)
            longest_atom = 0.0
            for token in cell.split():
                w, _ = measure_text(token, font, size_pt, inv)
                longest_atom = max(longest_atom, w)
            minimums[c] = max(minimums[c], longest_atom + pad)

    floor_pt = float(min_col_pt)
    minimums = [max(m, floor_pt) for m in minimums]

    total_pt = total_width_emu / EMU_PER_POINT
    min_sum = sum(minimums)

    if min_sum > total_pt:
        # The destructive rung, and it is LAST for the same reason LaTeXer's
        # bisect is last: it is the only outcome that compromises the content.
        scale = total_pt / min_sum if min_sum else 0.0
        widths_pt = [m * scale for m in minimums]
        widths = [int(w * EMU_PER_POINT) for w in widths_pt]
        widths[-1] = total_width_emu - sum(widths[:-1])
        return {
            "widths": widths,
            "widths_pt": [w / EMU_PER_POINT for w in widths],
            "columns": ncols,
            "min_violated": True,
            "minimums_pt": minimums,
            "naturals_pt": naturals,
            "reason": (f"the {ncols} columns need at least {min_sum:.0f}pt but only "
                       f"{total_pt:.0f}pt is available; widths were scaled by "
                       f"{scale:.3f} and text WILL wrap tightly — reduce the font "
                       f"size, split the table, or use a wider slide"),
        }

    # Water-fill the surplus in proportion to unmet demand.
    surplus = total_pt - min_sum
    demand = [max(0.0, naturals[c] - minimums[c]) for c in range(ncols)]
    demand_sum = sum(demand)

    if demand_sum <= 0:
        widths_pt = [m + surplus / ncols for m in minimums]
    elif demand_sum <= surplus:
        # Everyone can have their natural width; share the leftover evenly.
        leftover = (surplus - demand_sum) / ncols
        widths_pt = [naturals[c] + leftover for c in range(ncols)]
    else:
        widths_pt = [minimums[c] + surplus * demand[c] / demand_sum
                     for c in range(ncols)]

    widths = [int(w * EMU_PER_POINT) for w in widths_pt]
    widths[-1] = total_width_emu - sum(widths[:-1])     # exact, always

    return {
        "widths": widths,
        "widths_pt": [w / EMU_PER_POINT for w in widths],
        "columns": ncols,
        "min_violated": False,
        "minimums_pt": minimums,
        "naturals_pt": naturals,
        "reason": "",
    }


def distribute(total, count, gap=0) -> list:
    """Split `total` into `count` integer parts that sum EXACTLY to `total`."""
    n = max(1, int(count))
    usable = max(0, int(total) - int(gap) * (n - 1))
    base = usable // n
    parts = [base] * n
    parts[-1] = usable - base * (n - 1)
    return parts


def fit_image_box(region: Box, native_w: int, native_h: int,
                  mode: str = "contain", align: str = "center") -> Box:
    """Fit an image of a given native aspect into `region` WITHOUT distortion.

    mode='contain' — the whole image fits inside; letterboxed. Never crops.
    mode='cover'   — the region is filled; the overflow is cropped by the frame.
    mode='stretch' — exactly the region. DISTORTS; offered only because a
                     deliberate background wash sometimes wants it.

    Aspect ratio is preserved in contain/cover because a stretched logo or a
    squashed face is the single most obvious sign of a machine-made deck.
    """
    if native_w <= 0 or native_h <= 0 or region.width <= 0 or region.height <= 0:
        return Box(region.left, region.top, region.width, region.height,
                   region.name, "image")

    m = (mode or "contain").strip().lower()
    if m == "stretch":
        return Box(region.left, region.top, region.width, region.height,
                   region.name, "image")

    native_aspect = native_w / float(native_h)
    region_aspect = region.width / float(region.height)

    if (m == "cover") == (native_aspect > region_aspect):
        # cover + wider image  → match height;  contain + wider image → match width
        height = region.height if m == "cover" else int(region.width / native_aspect)
        width = int(region.height * native_aspect) if m == "cover" else region.width
    else:
        width = region.width if m == "cover" else int(region.height * native_aspect)
        height = int(region.width / native_aspect) if m == "cover" else region.height

    width = max(1, width)
    height = max(1, height)

    a = (align or "center").strip().lower()
    if "left" in a:
        x = region.left
    elif "right" in a:
        x = region.right - width
    else:
        x = region.left + (region.width - width) // 2

    if "top" in a:
        y = region.top
    elif "bottom" in a:
        y = region.bottom - height
    else:
        y = region.top + (region.height - height) // 2

    return Box(x, y, width, height, region.name, "image")


class GridSolver:
    """A 12-column editorial grid — the layout language real designers use.

    Slots are expressed the way a designer says them ("columns 1-7", "the right
    third"), and the solver returns exact EMU boxes that tile without gaps.
    Building compositions from a shared grid is what makes a deck's slides feel
    like one document rather than twelve unrelated pictures.
    """

    def __init__(self, canvas: SlideCanvas, columns: int = 12, rows: int = 8):
        self.canvas = canvas
        self.columns = max(1, int(columns))
        self.rows = max(1, int(rows))
        safe = canvas.safe
        self.origin = safe
        gap = canvas.gutter
        self._col_w = (safe.width - gap * (self.columns - 1)) / float(self.columns)
        self._row_h = (safe.height - gap * (self.rows - 1)) / float(self.rows)
        self._gap = gap

    def span(self, col: int, row: int, col_span: int = 1, row_span: int = 1,
             name: str = "", kind: str = "cell") -> Box:
        """A box spanning grid cells. `col`/`row` are 0-based."""
        c = max(0, min(self.columns - 1, int(col)))
        r = max(0, min(self.rows - 1, int(row)))
        cs = max(1, min(self.columns - c, int(col_span)))
        rs = max(1, min(self.rows - r, int(row_span)))

        left = self.origin.left + int(round(c * (self._col_w + self._gap)))
        top = self.origin.top + int(round(r * (self._row_h + self._gap)))
        width = int(round(cs * self._col_w + (cs - 1) * self._gap))
        height = int(round(rs * self._row_h + (rs - 1) * self._gap))

        # Clamp to the safe area so rounding can never push the last cell out.
        right = min(left + width, self.origin.right)
        bottom = min(top + height, self.origin.bottom)
        return Box(left, top, right - left, bottom - top, name, kind)

    def golden_split(self, vertical: bool = True, flip: bool = False) -> tuple:
        """Split the safe area at the golden ratio (0.618).

        Used constantly in marketing layouts: image on the large side, message
        on the small side. It reads as "designed" because the proportion is the
        one the eye is trained on from print.
        """
        phi = 0.6180339887
        safe = self.origin
        gap = self._gap
        if vertical:
            big_w = int((safe.width - gap) * (1 - phi if flip else phi))
            small_w = safe.width - gap - big_w
            a = Box(safe.left, safe.top, big_w, safe.height, "major", "region")
            b = Box(safe.left + big_w + gap, safe.top, small_w, safe.height,
                    "minor", "region")
        else:
            big_h = int((safe.height - gap) * (1 - phi if flip else phi))
            small_h = safe.height - gap - big_h
            a = Box(safe.left, safe.top, safe.width, big_h, "major", "region")
            b = Box(safe.left, safe.top + big_h + gap, safe.width, small_h,
                    "minor", "region")
        return (a, b)

    def rule_of_thirds(self) -> dict:
        """The four thirds intersections — where a focal point wants to sit."""
        safe = self.origin
        return {
            "top_left": (safe.left + safe.width // 3, safe.top + safe.height // 3),
            "top_right": (safe.left + 2 * safe.width // 3, safe.top + safe.height // 3),
            "bottom_left": (safe.left + safe.width // 3, safe.top + 2 * safe.height // 3),
            "bottom_right": (safe.left + 2 * safe.width // 3,
                             safe.top + 2 * safe.height // 3),
        }


def modular_scale(base_pt: float, ratio: float = 1.333, steps: int = 7) -> list:
    """A typographic scale: base × ratio^n.

    Sizes chosen from one ratio relate to each other visibly, which is what
    makes a hierarchy read at a glance from the back of a room. 1.333 (the
    perfect fourth) is the default because it is decisive without being
    theatrical; 1.5 and 1.618 suit keynote and brand-story decks.
    """
    try:
        b = float(base_pt)
        r = float(ratio)
    except (TypeError, ValueError):
        b, r = 18.0, 1.333
    if r <= 1.0:
        r = 1.2
    return [round(b * math.pow(r, n), 1) for n in range(int(steps))]
