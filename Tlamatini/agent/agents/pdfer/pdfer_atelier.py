# ═══════════════════════════════════════════════════════════════════
#   ✦  T L A M A T I N I  ✦   —   "one who knows"
#
#   Created by  Angela López Mendoza   ·   @angelahack1
#   Developer · Architect · Creator of Tlamatini
#
#   Every line of this file was written by Angela López Mendoza.
# ═══════════════════════════════════════════════════════════════════
#   Tlamatini Author Banner — do not remove (releases scrub the name automatically)
"""PDFer atelier — the ReportLab Platypus renderer that replaced xhtml2pdf.

WHY A NEW ENGINE RATHER THAN A PATCHED STYLESHEET
--------------------------------------------------
Angela asked for four things ``xhtml2pdf`` structurally cannot give:

======================  =====================================================
asked for               why xhtml2pdf could not
======================  =====================================================
tables that don't       it places cell text at a computed x-offset without
overlap                 ever asking whether the text fits, and it reported
                        ``err=0`` on every one of the three tables that broke
gradients               it has no gradient support of any kind; a
                        ``linear-gradient`` is silently ignored
a black page with       ``background-color`` on ``@page`` is not honoured,
white text              so a dark theme printed black text on white paper
per-content typography  it cannot register arbitrary TrueType faces reliably,
                        so every document came out in Helvetica
======================  =====================================================

ReportLab gives all four natively: ``canvas.linearGradient`` and
``radialGradient`` are real, ``pdfmetrics.registerFont`` takes any TTF, a page
background is one ``canvas.rect`` in an ``onPage`` callback, and — decisively
— a ``Paragraph`` handed an explicit width **wraps inside that width**. It is
not capable of drawing outside it. That last property is what turns "we try
not to overlap" into "overlapping is geometrically impossible".

THE SHAPE OF A RENDER
---------------------
1. `Atelier.stylesheet()` derives ~20 paragraph styles from the design system.
   No size, colour or face is typed in here; every one comes from
   `design.sizes`, `design.palette` and `design.fonts`.
2. `Atelier.flow()` walks the block list from `pdfer_docmodel` and emits
   Platypus flowables. Tables go through `pdfer_tables.TableSolver` first.
3. `_paint_page` runs on every page: ground fill (the dark themes' whole
   reason for existing), optional edge ornament, footer, page number.
4. `build()` assembles the document and returns a report of what it did.

THE THREE OVERFLOW SOURCES, ALL CLOSED
---------------------------------------
A renderer has exactly three ways to put ink outside its frame, and all three
are handled explicitly rather than hoped about:

* **Table cells** → solved widths + ``Paragraph`` cells (`pdfer_tables`).
* **Code blocks** → code does not wrap on spaces, so a 200-character line
  would run off the page. `_wrap_code` measures the mono face and hard-wraps
  at the true character budget, marking continuations with ``↳`` so the
  reader can tell a wrap from a real newline.
* **Long words in prose** → `_safe_paragraph` measures the longest token and
  switches that paragraph to character wrapping when it cannot fit.

CONTRACTS (do NOT weaken)
-------------------------
1. **Every flowable is given an explicit width that fits the frame.** No
   flowable is ever emitted with an unbounded or assumed width.
2. **The page ground is painted BEFORE anything else** on every page, and
   under the margins too — a dark theme with a white margin band looks like a
   bug, because it is one.
3. **FAIL-OPEN per block.** A block that cannot be rendered becomes a visible
   plain-text fallback, never an exception that loses the other forty blocks.

Author: Angela López Mendoza.
"""

from __future__ import annotations

import os
import re

import pdfer_docmodel as dm
import pdfer_tables as ptab

__all__ = ["Atelier", "PAGE_SIZES", "render_document"]

#: mm → points, the only unit conversion in the module.
MM = 72.0 / 25.4

PAGE_SIZES = {
    "a4": (595.276, 841.890),
    "letter": (612.0, 792.0),
    "legal": (612.0, 1008.0),
    "a3": (841.890, 1190.551),
    "a5": (419.528, 595.276),
    "tabloid": (792.0, 1224.0),
}


def _page_size(name: str, orientation: str) -> tuple:
    size = PAGE_SIZES.get(str(name or "a4").strip().lower(), PAGE_SIZES["a4"])
    if str(orientation or "").strip().lower() == "landscape":
        return (size[1], size[0])
    return size


class Atelier:
    """Renders a `pdfer_docmodel.Document` through a `pdfer_theme.DesignSystem`."""

    def __init__(self, design, font_book, ornament=None, logger=None,
                 labels=None):
        self.design = design
        self.book = font_book
        self.ornament = ornament
        self.logger = logger
        self.labels = labels or {"page": "page", "of": "of",
                                 "contents": "Contents"}
        self.palette = design.palette
        self.fonts = design.fonts
        self.sizes = design.sizes
        self.spacing = design.spacing
        self.notes = []
        self.repairs = []
        self._toc_entries = []
        self._styles = None
        self.page_size = _page_size(design.page.get("size"),
                                    design.page.get("orientation"))
        self.margin = float(design.page.get("margin_mm", 18)) * MM
        self.frame_width = self.page_size[0] - 2 * self.margin
        self.frame_height = self.page_size[1] - 2 * self.margin

    # ── plumbing ────────────────────────────────────────────────────────
    def _log(self, message):
        if self.logger:
            try:
                self.logger(message)
            except Exception:
                pass

    def _c(self, role):
        """A palette role as a ReportLab colour."""
        return self.palette.get(role).as_reportlab()

    def _hex(self, role):
        return self.palette.get(role).hex

    def _cover_ink(self):
        """A text colour that is legible on THIS cover's artwork.

        The cover is the one place where text does not sit on a palette role —
        it sits on a generated gradient. So the ground is computed (the
        midpoint of ``cover_from → cover_to``, which is what the title band
        actually crosses), the more promising of the two text colours is
        chosen, and `ensure_contrast` guarantees the rest.

        When no cover art is drawn the title sits on the plain page, so the
        ordinary heading colour is correct and is used instead.
        """
        import pdfer_color as pc

        if not self.design.may_decorate("cover"):
            return self.palette.heading_1
        ground = pc.mix(self.palette.cover_from, self.palette.cover_to, 0.5)
        candidates = (self.palette.text, self.palette.text_inverse,
                      pc.Color(1, 1, 1), pc.Color(0, 0, 0))
        best = max(candidates, key=lambda c: c.contrast(ground))
        return pc.ensure_contrast(best, ground, pc.WCAG_AA_LARGE,
                                  preserve_hue=False)

    # ─────────────────────────────────────────────────────────────────
    #  STYLESHEET — derived entirely from the design system
    # ─────────────────────────────────────────────────────────────────
    def stylesheet(self) -> dict:
        if self._styles is not None:
            return self._styles
        from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT
        from reportlab.lib.styles import ParagraphStyle

        f, s, sp = self.fonts, self.sizes, self.spacing
        body_align = TA_JUSTIFY if self.design.justify else TA_LEFT

        base = ParagraphStyle(
            "tlm_body", fontName=f["body"], fontSize=s["body"],
            leading=self.design.scale.leading(s["body"]),
            textColor=self._c("text"), alignment=body_align,
            spaceAfter=sp["para_after"], allowWidows=0, allowOrphans=0,
            # Hyphenation-free justification can open ugly rivers; a small
            # word-spacing tolerance is what a typesetter would allow.
            splitLongWords=1, embeddedHyphenation=1)

        styles = {"body": base}

        for level in (1, 2, 3, 4, 5, 6):
            key = "h%d" % level
            size = s.get(key, s["h4"])
            colour_role = "heading_%d" % min(level, 4)
            styles[key] = ParagraphStyle(
                "tlm_" + key, parent=base,
                fontName=f["display_bold"] if level <= 2 else f["body_bold"],
                fontSize=size,
                leading=self.design.scale.leading(size),
                textColor=self._c(colour_role),
                spaceBefore=sp.get("h%d_before" % min(level, 4), sp["h4_before"]),
                spaceAfter=sp.get("h%d_after" % min(level, 4), sp["h4_after"]),
                alignment=TA_LEFT, keepWithNext=1)

        styles["lead"] = ParagraphStyle(
            "tlm_lead", parent=base, fontSize=s["body"] * 1.14,
            leading=self.design.scale.leading(s["body"] * 1.14),
            textColor=self._c("text_muted"), spaceAfter=sp["para_after"] * 1.4)

        styles["caption"] = ParagraphStyle(
            "tlm_caption", parent=base, fontName=f["body_italic"],
            fontSize=s["caption"],
            leading=self.design.scale.leading(s["caption"]),
            textColor=self._c("caption"), alignment=TA_CENTER,
            spaceBefore=2, spaceAfter=sp["para_after"])

        styles["footer"] = ParagraphStyle(
            "tlm_footer", parent=base, fontSize=s["footer"],
            leading=s["footer"] * 1.2, textColor=self._c("footer"),
            alignment=TA_CENTER, spaceAfter=0)

        styles["code"] = ParagraphStyle(
            "tlm_code", parent=base, fontName=f["mono"], fontSize=s["code"],
            leading=s["code_leading"], textColor=self._c("code_fg"),
            alignment=TA_LEFT, spaceAfter=0, spaceBefore=0)

        styles["quote"] = ParagraphStyle(
            "tlm_quote", parent=base, fontName=f["body_italic"],
            textColor=self._c("quote_fg"), alignment=TA_LEFT,
            leftIndent=sp["list_indent"] * 0.5)

        styles["list"] = ParagraphStyle(
            "tlm_list", parent=base, alignment=TA_LEFT,
            spaceAfter=sp["list_gap"])

        styles["cell"] = ParagraphStyle(
            "tlm_cell", parent=base, fontSize=s["body"] * 0.94,
            leading=s["body"] * 0.94 * 1.24, alignment=TA_LEFT,
            spaceAfter=0, spaceBefore=0)
        styles["cell_head"] = ParagraphStyle(
            "tlm_cell_head", parent=styles["cell"], fontName=f["body_bold"],
            textColor=self._c("table_header_fg"))
        styles["cell_num"] = ParagraphStyle(
            "tlm_cell_num", parent=styles["cell"], alignment=2)   # TA_RIGHT

        # ⚠️ COVER TEXT IS COLOURED AGAINST THE ART, NOT BY A FIXED ROLE.
        #
        # The first version used ``text_inverse`` whenever a cover was drawn.
        # On a DARK theme ``text_inverse`` is near-black (it is the inverse of
        # the light body text) — and the cover art is also dark, so the title
        # came out at **2.53:1** on ``scientific_dark``. The layout auditor
        # caught it against the rendered file, which is exactly why that
        # auditor exists.
        #
        # The ground here is artwork, not a palette role, so the colour has to
        # be solved: take the midpoint of the cover gradient (the tone the
        # title actually sits on), pick whichever of the two text colours
        # starts closer, and let `ensure_contrast` finish the job.
        cover_ink = self._cover_ink()
        styles["cover_title"] = ParagraphStyle(
            "tlm_cover_title", parent=base, fontName=f["display_bold"],
            fontSize=s["cover_title"],
            leading=self.design.scale.leading(s["cover_title"]),
            textColor=cover_ink.as_reportlab(),
            alignment=TA_LEFT, spaceAfter=6)
        styles["cover_subtitle"] = ParagraphStyle(
            "tlm_cover_subtitle", parent=base, fontName=f["display"],
            fontSize=s["cover_subtitle"],
            leading=self.design.scale.leading(s["cover_subtitle"]),
            textColor=cover_ink.with_alpha(0.86).as_reportlab(),
            alignment=TA_LEFT)

        styles["toc1"] = ParagraphStyle(
            "tlm_toc1", parent=base, fontName=f["body_bold"],
            textColor=self._c("heading_2"), spaceAfter=2, alignment=TA_LEFT)
        styles["toc2"] = ParagraphStyle(
            "tlm_toc2", parent=base, leftIndent=14, spaceAfter=1,
            alignment=TA_LEFT)
        styles["toc3"] = ParagraphStyle(
            "tlm_toc3", parent=base, leftIndent=28, fontSize=s["small"],
            textColor=self._c("text_muted"), spaceAfter=1, alignment=TA_LEFT)

        self._styles = styles
        return styles

    # ─────────────────────────────────────────────────────────────────
    #  OVERFLOW GUARD #3 — long words in running prose
    # ─────────────────────────────────────────────────────────────────
    def _safe_paragraph(self, markup, style, width=None):
        """A Paragraph that cannot exceed *width*.

        Platypus breaks on spaces only. A 90-character identifier or URL in a
        paragraph therefore overruns the frame exactly the way it overran a
        table cell. Measure the longest token; if it does not fit, switch this
        paragraph (and only this one) to character wrapping.
        """
        from reportlab.lib.styles import ParagraphStyle
        from reportlab.platypus import Paragraph

        available = width if width is not None else self.frame_width
        available -= getattr(style, "leftIndent", 0) + getattr(style,
                                                              "rightIndent", 0)
        try:
            longest = ptab.longest_unbreakable_width(
                markup, style.fontName, style.fontSize, self.book.text_width,
                allow_atom_split=True)
            if longest > max(8.0, available):
                style = ParagraphStyle("%s_cjk" % style.name, parent=style,
                                       wordWrap="CJK")
                self.repairs.append("char_wrap_paragraph")
        except Exception:
            pass
        try:
            return Paragraph(markup, style)
        except Exception:
            # A malformed inline fragment must not lose the text.
            return Paragraph(dm.escape_inline(dm.strip_inline(markup)), style)

    # ─────────────────────────────────────────────────────────────────
    #  OVERFLOW GUARD #2 — code blocks
    # ─────────────────────────────────────────────────────────────────
    def _wrap_code(self, text, width, font, size):
        """Hard-wrap code at the measured character budget.

        Code has no space to break at, so ReportLab's ``Preformatted`` will
        happily draw a 200-column line straight off the sheet. The budget is
        computed from the ACTUAL mono face at the ACTUAL size — a fixed
        "80 columns" guess is wrong for every font but one.

        Continuations are marked ``↳`` so a reader can always tell a wrap from
        a newline the author actually wrote. Indentation is preserved on the
        continuation, which is what makes wrapped Python still readable.
        """
        try:
            per_char = self.book.text_width("0", font, size) or (size * 0.6)
        except Exception:
            per_char = size * 0.6
        budget = max(20, int((width - 8) / per_char))
        out = []
        for line in (text or "").split("\n"):
            if len(line) <= budget:
                out.append(line)
                continue
            indent = len(line) - len(line.lstrip())
            prefix = " " * min(indent, budget // 3)
            remaining = line
            first = True
            while remaining:
                take = budget if first else budget - len(prefix) - 2
                take = max(10, take)
                chunk, remaining = remaining[:take], remaining[take:]
                out.append(chunk if first else "%s↳ %s" % (prefix, chunk))
                first = False
        return "\n".join(out)

    def _code_flowable(self, block, width):
        from reportlab.lib.styles import ParagraphStyle
        from reportlab.platypus import Preformatted, Table, TableStyle

        styles = self.stylesheet()
        pad = self.spacing["cell_padding"] + 2
        inner = width - 2 * pad
        wrapped = self._wrap_code(block.text, inner, self.fonts["mono"],
                                  self.sizes["code"])
        code_style = ParagraphStyle("tlm_code_inner", parent=styles["code"])
        pre = Preformatted(wrapped, code_style)
        table = Table([[pre]], colWidths=[width])
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), self._c("code_bg")),
            ("BOX", (0, 0), (-1, -1), 0.6, self._c("code_border")),
            ("LEFTPADDING", (0, 0), (-1, -1), pad),
            ("RIGHTPADDING", (0, 0), (-1, -1), pad),
            ("TOPPADDING", (0, 0), (-1, -1), pad * 0.8),
            ("BOTTOMPADDING", (0, 0), (-1, -1), pad * 0.8),
            ("LINEBEFORE", (0, 0), (0, -1), 2.4, self._c("primary")),
        ]))
        return table

    # ─────────────────────────────────────────────────────────────────
    #  OVERFLOW GUARD #1 — tables (the headline fix)
    # ─────────────────────────────────────────────────────────────────
    def _table_flowables(self, block, width):
        from reportlab.lib.styles import ParagraphStyle
        from reportlab.platypus import KeepTogether, Paragraph, Table, TableStyle

        styles = self.stylesheet()
        rows = block.normalised()
        if not rows:
            return []

        solver = ptab.TableSolver(
            measure=self.book.text_width,
            body_font=styles["cell"].fontName,
            head_font=styles["cell_head"].fontName,
            padding=self.spacing["cell_padding"])
        layout = solver.solve(rows, available_width=width,
                              font_size=styles["cell"].fontSize,
                              has_header=block.has_header,
                              allow_landscape=True)
        for note in layout.notes:
            self.notes.append("[table] " + note)
        self.repairs.extend(layout.repairs)

        groups = layout.split_groups or [list(range(layout.col_widths
                                                    and len(layout.col_widths)
                                                    or 0))]
        flowables = []
        for group_index, columns in enumerate(groups):
            if not columns:
                continue
            widths = [layout.col_widths[c] for c in columns]
            # A split group must still fill the frame, or the second half of a
            # split table renders as a narrow ribbon.
            total = sum(widths) or 1.0
            widths = [w * (width / total) for w in widths]

            data = []
            for row_index, row in enumerate(rows):
                is_head = block.has_header and row_index == 0
                cells = []
                for position, col in enumerate(columns):
                    raw = row[col] if col < len(row) else ""
                    markup = dm.inline_to_platypus(
                        str(raw), self.fonts["mono"], self._hex("code_fg"))
                    if is_head:
                        style = styles["cell_head"]
                    elif (layout.demands and col < len(layout.demands)
                          and layout.demands[col].numeric):
                        style = styles["cell_num"]
                    else:
                        style = styles["cell"]
                    if layout.font_size != style.fontSize or col in layout.char_wrap_cols:
                        style = ParagraphStyle(
                            "%s_%d" % (style.name, col), parent=style,
                            fontSize=layout.font_size,
                            leading=layout.font_size * 1.24,
                            wordWrap="CJK" if col in layout.char_wrap_cols
                            else style.wordWrap)
                    try:
                        cells.append(Paragraph(markup or "&nbsp;", style))
                    except Exception:
                        cells.append(Paragraph(
                            dm.escape_inline(dm.strip_inline(str(raw)))
                            or "&nbsp;", style))
                data.append(cells)

            table = Table(data, colWidths=widths,
                          repeatRows=1 if block.has_header else 0)
            commands = [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), layout.padding),
                ("RIGHTPADDING", (0, 0), (-1, -1), layout.padding),
                ("TOPPADDING", (0, 0), (-1, -1), layout.padding * 0.62),
                ("BOTTOMPADDING", (0, 0), (-1, -1), layout.padding * 0.62),
                ("GRID", (0, 0), (-1, -1), 0.4, self._c("table_border")),
            ]
            if block.has_header:
                commands += [
                    ("BACKGROUND", (0, 0), (-1, 0), self._c("table_header_bg")),
                    ("LINEBELOW", (0, 0), (-1, 0), 1.1, self._c("primary")),
                    ("ROWBACKGROUNDS", (0, 1), (-1, -1),
                     [self._c("background"), self._c("table_row_alt")]),
                ]
            else:
                commands.append(
                    ("ROWBACKGROUNDS", (0, 0), (-1, -1),
                     [self._c("background"), self._c("table_row_alt")]))
            table.setStyle(TableStyle(commands))

            if len(groups) > 1:
                label = dm.escape_inline(
                    "columns %d–%d of %d" % (columns[0] + 1, columns[-1] + 1,
                                             len(layout.col_widths)))
                flowables.append(Paragraph(label, styles["caption"]))
            flowables.append(table)
            if group_index < len(groups) - 1:
                from reportlab.platypus import Spacer
                flowables.append(Spacer(1, self.spacing["table_after"] * 0.5))

        if block.caption:
            flowables.append(Paragraph(
                dm.inline_to_platypus(block.caption, self.fonts["mono"]),
                styles["caption"]))
        # A small table should not be orphaned from its heading.
        if len(rows) <= 6 and len(flowables) <= 2:
            return [KeepTogether(flowables)]
        return flowables

    # ─────────────────────────────────────────────────────────────────
    #  Remaining block renderers
    # ─────────────────────────────────────────────────────────────────
    def _list_flowables(self, block, width):
        from reportlab.lib.styles import ParagraphStyle
        from reportlab.platypus import ListFlowable, ListItem

        styles = self.stylesheet()
        indent = self.spacing["list_indent"] * (1 + block.level)
        item_style = ParagraphStyle(
            "tlm_li_%d" % block.level, parent=styles["list"],
            leftIndent=0, bulletColor=self._c("primary"))
        items = []
        for raw in block.items:
            markup = dm.inline_to_platypus(str(raw), self.fonts["mono"],
                                           self._hex("code_fg"))
            items.append(ListItem(
                self._safe_paragraph(markup, item_style, width - indent),
                leftIndent=indent, value=None))
        try:
            return [ListFlowable(
                items, bulletType="1" if block.ordered else "bullet",
                start=block.start if block.ordered else None,
                bulletFontName=self.fonts["body_bold"],
                bulletFontSize=self.sizes["body"] * 0.92,
                bulletColor=self._c("primary"),
                leftIndent=indent, bulletDedent=indent * 0.72,
                spaceBefore=self.spacing["list_gap"],
                spaceAfter=self.spacing["para_after"])]
        except Exception:
            # Degrade to plain paragraphs rather than lose the list.
            marker = "•" if not block.ordered else ""
            out = []
            for index, raw in enumerate(block.items):
                prefix = marker or ("%d." % (block.start + index))
                out.append(self._safe_paragraph(
                    "%s&nbsp;&nbsp;%s" % (prefix,
                                          dm.inline_to_platypus(str(raw))),
                    item_style, width))
            return out

    def _quote_flowables(self, block, width):
        from reportlab.platypus import Table, TableStyle

        styles = self.stylesheet()
        pad = self.spacing["cell_padding"] + 3
        inner = self.flow(block.blocks, width - 2 * pad - 4,
                          quote_style=styles["quote"])
        if not inner:
            return []
        table = Table([[inner]], colWidths=[width])
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), self._c("quote_bg")),
            ("LINEBEFORE", (0, 0), (0, -1), 3.0, self._c("quote_bar")),
            ("LEFTPADDING", (0, 0), (-1, -1), pad + 4),
            ("RIGHTPADDING", (0, 0), (-1, -1), pad),
            ("TOPPADDING", (0, 0), (-1, -1), pad * 0.8),
            ("BOTTOMPADDING", (0, 0), (-1, -1), pad * 0.8),
        ]))
        return [table]

    def _callout_flowables(self, block, width):
        from reportlab.lib.styles import ParagraphStyle
        from reportlab.platypus import Paragraph, Table, TableStyle
        import pdfer_color as pc

        styles = self.stylesheet()
        tone = block.tone if block.tone in ("success", "warning", "danger",
                                            "info") else "info"
        bar = self.palette.get(tone)
        # A 12 % tint of the tone over the page ground: strong enough to read
        # as a distinct block, weak enough not to fight the body text.
        tint = pc.mix(bar, self.palette.background, 0.88)
        pad = self.spacing["cell_padding"] + 3
        title_style = ParagraphStyle(
            "tlm_callout_title", parent=styles["body"],
            fontName=self.fonts["body_bold"],
            textColor=pc.ensure_contrast(bar, tint,
                                         pc.WCAG_AA_LARGE).as_reportlab(),
            spaceAfter=self.spacing["para_after"] * 0.5)
        inner = []
        if block.title:
            inner.append(Paragraph(dm.escape_inline(block.title), title_style))
        inner.extend(self.flow(block.blocks, width - 2 * pad - 4))
        if not inner:
            return []
        table = Table([[inner]], colWidths=[width])
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), tint.as_reportlab()),
            ("LINEBEFORE", (0, 0), (0, -1), 3.4, bar.as_reportlab()),
            ("LEFTPADDING", (0, 0), (-1, -1), pad + 4),
            ("RIGHTPADDING", (0, 0), (-1, -1), pad),
            ("TOPPADDING", (0, 0), (-1, -1), pad * 0.8),
            ("BOTTOMPADDING", (0, 0), (-1, -1), pad * 0.8),
        ]))
        return [table]

    def _image_flowables(self, block, width, base_dir=""):
        from reportlab.platypus import Image as RLImage, Paragraph

        styles = self.stylesheet()
        path = self._resolve_image(block.src, base_dir)
        if not path:
            self.notes.append("image not found, replaced by its alt text: %s"
                              % str(block.src)[:120])
            label = block.alt or block.caption or os.path.basename(
                str(block.src))
            return [Paragraph("[image: %s]" % dm.escape_inline(label),
                              styles["caption"])] if label else []
        try:
            intrinsic = self._image_size(path)
            if not intrinsic:
                return []
            iw, ih = intrinsic
            scale = min(1.0, width / float(iw))
            # Never let one figure eat a whole page: cap at 62 % of the frame
            # height so a portrait screenshot still leaves room for its caption.
            max_h = self.frame_height * 0.62
            if ih * scale > max_h:
                scale = max_h / float(ih)
            flowables = [RLImage(path, width=iw * scale, height=ih * scale)]
            caption = block.caption or block.alt
            if caption:
                flowables.append(Paragraph(dm.escape_inline(caption),
                                           styles["caption"]))
            return flowables
        except Exception as exc:
            self.notes.append("image %s could not be embedded (%s)"
                              % (os.path.basename(path), type(exc).__name__))
            return []

    @staticmethod
    def _resolve_image(src, base_dir=""):
        """Resolve ``src`` the three ways a human actually writes it.

        This mirrors the 2026-08 ``_resolve_asset_uri`` fix: an unresolvable
        image must be REPORTED, never silently omitted, which is why the
        caller substitutes visible alt text instead of nothing.
        """
        from urllib.parse import unquote, urlparse

        text = str(src or "").strip()
        if not text or text.lower().startswith(("http://", "https://",
                                                "data:", "ftp://")):
            return ""
        path = text
        if text.lower().startswith("file:"):
            parsed = urlparse(text)
            path = unquote(parsed.path or "")
            if os.name == "nt" and re.match(r"^/[A-Za-z]:", path):
                path = path[1:]
            if parsed.netloc and parsed.netloc.lower() not in ("", "localhost"):
                path = "//%s%s" % (parsed.netloc, path)
        path = os.path.expandvars(os.path.expanduser(path))
        if os.name == "nt":
            path = path.replace("/", os.sep)
        candidates = [path]
        if base_dir and not os.path.isabs(path):
            candidates.insert(0, os.path.join(base_dir, path))
        for candidate in candidates:
            try:
                if os.path.isfile(candidate):
                    return os.path.normpath(candidate)
            except Exception:
                continue
        return ""

    @staticmethod
    def _image_size(path):
        try:
            from PIL import Image
            with Image.open(path) as im:
                return im.size
        except Exception:
            try:
                from reportlab.lib.utils import ImageReader
                return ImageReader(path).getSize()
            except Exception:
                return None

    def _rule_flowable(self, width):
        from reportlab.platypus import Image as RLImage, Spacer

        if self.ornament and self.design.may_decorate("section_rule"):
            path = self.ornament.section_rule(int(width), 3, salt="section")
            if path:
                try:
                    return [Spacer(1, self.spacing["rule_gap"]),
                            RLImage(path, width=width, height=3),
                            Spacer(1, self.spacing["rule_gap"])]
                except Exception:
                    pass
        from reportlab.platypus import HRFlowable
        return [HRFlowable(width="100%", thickness=0.7,
                           color=self._c("border"),
                           spaceBefore=self.spacing["rule_gap"],
                           spaceAfter=self.spacing["rule_gap"])]

    def _heading_flowables(self, block, width):
        from reportlab.platypus import Image as RLImage, KeepTogether, Spacer

        styles = self.stylesheet()
        style = styles.get("h%d" % block.level, styles["h4"])
        markup = dm.inline_to_platypus(block.text, self.fonts["mono"],
                                       self._hex("code_fg"))
        paragraph = self._safe_paragraph(markup, style, width)
        self._toc_entries.append((block.level, dm.strip_inline(block.text)))

        # A gradient rule under H1/H2 — this is what replaced the old flat
        # `border-bottom: 2px solid #C1272D`.
        if (block.level <= 2 and self.ornament
                and self.design.may_decorate("section_rule")):
            path = self.ornament.section_rule(
                int(width), 3, salt="h%d" % block.level)
            if path:
                try:
                    return [KeepTogether([paragraph, Spacer(1, 2),
                                          RLImage(path, width=width,
                                                  height=3)])]
                except Exception:
                    pass
        elif block.level == 1 and self.design.may_decorate("title_rule"):
            from reportlab.platypus import HRFlowable
            return [KeepTogether([
                paragraph,
                HRFlowable(width="100%", thickness=0.7,
                           color=self._c("rule"), spaceBefore=1,
                           spaceAfter=0)])]
        return [paragraph]

    # ─────────────────────────────────────────────────────────────────
    #  THE WALK
    # ─────────────────────────────────────────────────────────────────
    def flow(self, blocks, width=None, base_dir="", quote_style=None):
        """Block list → Platypus flowables. Per-block fail-open."""
        from reportlab.platypus import Paragraph, Spacer

        styles = self.stylesheet()
        width = self.frame_width if width is None else width
        out = []
        for block in blocks or ():
            try:
                kind = getattr(block, "kind", "")
                if kind == "heading":
                    out.extend(self._heading_flowables(block, width))
                elif kind == "paragraph":
                    style = quote_style or (styles["lead"] if
                                            getattr(block, "lead", False)
                                            else styles["body"])
                    markup = dm.inline_to_platypus(
                        block.text, self.fonts["mono"], self._hex("code_fg"))
                    if markup:
                        out.append(self._safe_paragraph(markup, style, width))
                elif kind == "list":
                    out.extend(self._list_flowables(block, width))
                elif kind == "table":
                    out.append(Spacer(1, self.spacing["table_before"]))
                    out.extend(self._table_flowables(block, width))
                    out.append(Spacer(1, self.spacing["table_after"]))
                elif kind == "code":
                    out.append(Spacer(1, self.spacing["block_before"]))
                    out.append(self._code_flowable(block, width))
                    out.append(Spacer(1, self.spacing["block_after"]))
                elif kind == "quote":
                    out.append(Spacer(1, self.spacing["block_before"] * 0.6))
                    out.extend(self._quote_flowables(block, width))
                    out.append(Spacer(1, self.spacing["block_after"] * 0.6))
                elif kind == "callout":
                    out.append(Spacer(1, self.spacing["block_before"] * 0.6))
                    out.extend(self._callout_flowables(block, width))
                    out.append(Spacer(1, self.spacing["block_after"] * 0.6))
                elif kind == "image":
                    out.append(Spacer(1, self.spacing["figure_gap"]))
                    out.extend(self._image_flowables(block, width, base_dir))
                    out.append(Spacer(1, self.spacing["figure_gap"]))
                elif kind == "rule":
                    out.extend(self._rule_flowable(width))
            except Exception as exc:
                # FAIL-OPEN PER BLOCK. One bad table must not cost the other
                # thirty-nine blocks — the reader gets plain text and a note.
                self.notes.append("block %s rendered plainly (%s: %s)"
                                  % (getattr(block, "kind", "?"),
                                     type(exc).__name__, exc))
                try:
                    plain = dm.escape_inline(
                        dm.strip_inline(getattr(block, "text", "")) or "")
                    if plain:
                        out.append(Paragraph(plain, styles["body"]))
                except Exception:
                    pass
        return out

    # ─────────────────────────────────────────────────────────────────
    #  COVER + TOC
    # ─────────────────────────────────────────────────────────────────
    def cover_flowables(self, title, subtitle="", author="", meta_line=""):
        from reportlab.platypus import (HRFlowable, NextPageTemplate,
                                        PageBreak, Paragraph, Spacer)

        styles = self.stylesheet()
        # ⚠️ SWITCH TEMPLATES BEFORE THE FIRST PAGE ENDS.
        #
        # ReportLab does NOT advance through the template list on its own: a
        # BaseDocTemplate keeps using the template that is current until a
        # ``NextPageTemplate`` says otherwise. Without this line every page in
        # the document kept the COVER template — so the full-bleed cover
        # artwork was painted behind the body text on pages 2..n, and a
        # six-page brochure had prose sitting on a violet gradient at 1.05:1.
        #
        # It looked harmless on short light documents (which is how it
        # survived the first test round); the layout auditor found it by
        # measuring the ink against the ground it really landed on.
        out = [NextPageTemplate("body"), Spacer(1, self.frame_height * 0.30)]
        out.append(Paragraph(dm.escape_inline(title), styles["cover_title"]))
        if self.design.may_decorate("title_rule") or True:
            out.append(Spacer(1, 6))
            out.append(HRFlowable(
                width="46%", thickness=2.2,
                color=self.palette.accent.as_reportlab(),
                hAlign="LEFT", spaceBefore=0, spaceAfter=8))
        if subtitle:
            out.append(Paragraph(dm.escape_inline(subtitle),
                                 styles["cover_subtitle"]))
        tail = " · ".join(x for x in (author, meta_line) if x)
        if tail:
            out.append(Spacer(1, 14))
            out.append(Paragraph(dm.escape_inline(tail),
                                 styles["cover_subtitle"]))
        out.append(PageBreak())
        return out

    def toc_flowables(self, entries):
        from reportlab.platypus import PageBreak, Paragraph, Spacer

        if not entries:
            return []
        styles = self.stylesheet()
        out = [Paragraph(dm.escape_inline(self.labels.get("contents",
                                                          "Contents")),
                         styles["h1"]), Spacer(1, 6)]
        for level, text in entries:
            if level > 3 or not text:
                continue
            out.append(Paragraph(dm.escape_inline(text),
                                 styles["toc%d" % min(level, 3)]))
        out.append(PageBreak())
        return out

    # ─────────────────────────────────────────────────────────────────
    #  PAGE PAINTING — ground, ornament, footer
    # ─────────────────────────────────────────────────────────────────
    def _paint_page(self, canvas, doc, cover=False):
        """Runs on EVERY page, before anything else is drawn.

        ⚠️ The ground fill covers the WHOLE sheet including the margins. A
        dark theme that only tints the text frame leaves a white border and
        reads as a rendering bug — which it would be.
        """
        try:
            canvas.saveState()
            width, height = self.page_size

            canvas.setFillColor(self._c("background"))
            canvas.rect(0, 0, width, height, stroke=0, fill=1)

            if cover and self.ornament and self.design.may_decorate("cover"):
                art = self.ornament.cover_art(int(width), int(height),
                                              salt="cover")
                if art:
                    canvas.drawImage(art, 0, 0, width=width, height=height,
                                     mask="auto")
            elif self.ornament and self.design.may_decorate("page_edge"):
                band = self.ornament.header_band(int(width), 8, salt="edge")
                if band:
                    canvas.drawImage(band, 0, height - 8, width=width,
                                     height=8, mask="auto")

            if not cover:
                self._paint_footer(canvas, doc)
            canvas.restoreState()
        except Exception:
            # A failed page decoration must never abort the build.
            try:
                canvas.restoreState()
            except Exception:
                pass

    def _paint_footer(self, canvas, doc):
        if not getattr(self, "page_numbers", True):
            return
        try:
            width = self.page_size[0]
            y = self.margin * 0.48
            canvas.setFont(self.fonts["body"], self.sizes["footer"])
            canvas.setFillColor(self._c("footer"))
            label = "%s %d" % (self.labels.get("page", "page"), doc.page)
            total = getattr(self, "_total_pages", 0)
            if total:
                label += " %s %d" % (self.labels.get("of", "of"), total)
            canvas.drawCentredString(width / 2.0, y, label)

            if self.footer_note:
                canvas.setFont(self.fonts["body"], self.sizes["footer"])
                canvas.drawString(self.margin, y, self.footer_note[:90])
            # A hairline above the footer, in the rule colour.
            canvas.setStrokeColor(self._c("border_soft"))
            canvas.setLineWidth(0.4)
            canvas.line(self.margin, y + self.sizes["footer"] + 3,
                        width - self.margin, y + self.sizes["footer"] + 3)
        except Exception:
            pass

    # ─────────────────────────────────────────────────────────────────
    #  BUILD
    # ─────────────────────────────────────────────────────────────────
    def build(self, document, output_path, title="", subtitle="", author="",
              cover=True, toc=False, base_dir="", page_numbers=True,
              footer_note="", meta_line=""):
        """Render *document* to *output_path*. Returns a report dict.

        Two passes when a total page count is needed, because "page 3 of 9"
        cannot be known on page 3 of the first pass. The second pass is cheap
        (the flowables are rebuilt, not re-solved from content) and it is the
        only honest way to print a total.
        """
        from reportlab.platypus import BaseDocTemplate, Frame, PageTemplate

        self.page_numbers = bool(page_numbers)
        self.footer_note = footer_note or ""
        self._total_pages = 0
        report = {"engine": "atelier", "pages": 0, "notes": self.notes,
                  "repairs": self.repairs, "images": 0, "tables": 0}

        def make_story():
            self._toc_entries = []
            story = []
            resolved_title = title or document.infer_title()
            if cover and resolved_title:
                story.extend(self.cover_flowables(resolved_title, subtitle,
                                                  author, meta_line))
            body = self.flow(document.blocks, self.frame_width, base_dir)
            if toc:
                outline = document.outline()
                story.extend(self.toc_flowables(outline))
            story.extend(body)
            return story

        def build_once(path, story):
            frame = Frame(self.margin, self.margin, self.frame_width,
                          self.frame_height, id="tlm_body",
                          leftPadding=0, rightPadding=0, topPadding=0,
                          bottomPadding=0)
            has_cover = bool(cover and (title or document.infer_title()))

            template_cover = PageTemplate(
                id="cover", frames=[frame],
                onPage=lambda c, d: self._paint_page(c, d, cover=True))
            template_body = PageTemplate(
                id="body", frames=[frame],
                onPage=lambda c, d: self._paint_page(c, d, cover=False))

            doc = BaseDocTemplate(
                path, pagesize=self.page_size,
                leftMargin=self.margin, rightMargin=self.margin,
                topMargin=self.margin, bottomMargin=self.margin,
                title=title or document.infer_title() or "Document",
                author=author or "Tlamatini",
                subject=self.design.nuance,
                creator="Tlamatini PDFer")
            doc.addPageTemplates(
                [template_cover, template_body] if has_cover
                else [template_body])
            doc.build(list(story))
            return doc.page

        pages = build_once(output_path, make_story())
        if self.page_numbers and pages > 1:
            self._total_pages = pages
            try:
                pages = build_once(output_path, make_story())
            except Exception as exc:
                self.notes.append(
                    "page totals unavailable (%s) — footers show the page "
                    "number without a total" % type(exc).__name__)

        report["pages"] = pages
        report["tables"] = document.count("table")
        report["images"] = document.count("image")
        report["repairs"] = sorted(set(self.repairs))
        return report


def render_document(document, design, font_book, output_path, ornament=None,
                    logger=None, **options):
    """Convenience wrapper — build an Atelier and render in one call."""
    atelier = Atelier(design, font_book, ornament=ornament, logger=logger,
                      labels=options.pop("labels", None))
    return atelier.build(document, output_path, **options)
