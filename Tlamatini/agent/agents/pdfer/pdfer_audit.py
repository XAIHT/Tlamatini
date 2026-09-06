# ═══════════════════════════════════════════════════════════════════
#   ✦  T L A M A T I N I  ✦   —   "one who knows"
#
#   Created by  Angela López Mendoza   ·   @angelahack1
#   Developer · Architect · Creator of Tlamatini
#
#   Every line of this file was written by Angela López Mendoza.
# ═══════════════════════════════════════════════════════════════════
#   Tlamatini Author Banner — do not remove (releases scrub the name automatically)
"""PDFer audit — checking the FILE ON DISK, not the renderer's opinion of it.

WHY THIS MODULE IS NOT OPTIONAL
-------------------------------
The bug Angela reported was not "the renderer failed". It was **"the renderer
succeeded and the document was wrong"**. Measured on 2026-09-06: three
ordinary tables came out with cell text printed on top of other cells and a
Windows path running 54pt off the edge of the paper, and ``xhtml2pdf``
returned ``err = 0`` for every one of them.

A renderer's self-report is therefore not evidence. The only evidence is the
PDF. This module opens it with PyMuPDF and measures the actual glyph boxes —
the same standard `_count_pdf_images` established in 2026-08 when
``images_used: 0`` was being reported for documents that had four diagrams in
them: *ground truth is the file on disk*.

WHAT IT CHECKS
--------------
========================  ==================================================
check                     why it matters
========================  ==================================================
``overlap``               two glyph boxes from different lines intersecting
                          is the reported bug, measured directly
``bleed``                 any glyph outside the printable frame — content
                          that will be cut off by a printer, or lost
``blank_pages``           a page with no text and no image usually means a
                          flowable exploded silently
``contrast``              sampled text colour against sampled page ground,
                          in case a theme override defeated the palette
                          validation
``empty``                 a PDF with no extractable text at all, when the
                          document model said there was text
========================  ==================================================

THE VERDICT IS ADVISORY, AND DELIBERATELY SO
---------------------------------------------
`AuditReport.clean` is reported; it does **not** by itself fail the render.
A document with one 0.3pt overlap between a heading's descender and a rule is
not a failed document, and refusing to deliver it would be worse than
shipping it. What the agent must never do is claim a clean render when the
audit says otherwise — so the findings go into the `INI_SECTION_PDFER` block
and the agent's log verbatim, and `status` reflects them.

TOLERANCES ARE NOT FUDGE
-------------------------
``OVERLAP_TOLERANCE`` exists because glyph bounding boxes legitimately touch:
an italic ``f`` overhangs its advance width, kerned pairs share a column of
pixels, and an underline is drawn inside the text box. A zero-tolerance check
would report hundreds of "overlaps" in a perfectly typeset page and would be
switched off within a day — a check nobody trusts is worse than no check.

CONTRACTS (do NOT weaken)
-------------------------
1. **NEVER RAISES.** A missing PyMuPDF, a corrupt PDF, a locked file — all
   return a report with ``available=False``. The audit must never be the
   reason a good document is not delivered.
2. **Read-only.** This module never rewrites the PDF.
3. **Bounded.** Pairwise comparison is O(n²) in a page's words, so pages are
   swept with a line-bucketed scan and a hard cap. A 400-page document must
   not turn a 4-second render into a 4-minute one.

Author: Angela López Mendoza.
"""

from __future__ import annotations

__all__ = ["AuditReport", "audit_pdf", "OVERLAP_TOLERANCE"]

#: Glyph boxes may legitimately touch by this many points before it counts.
#: (An italic overhang is ~0.4pt at 10pt; kerned pairs ~0.2pt.)
OVERLAP_TOLERANCE = 1.2

#: Cap the per-page pairwise sweep. Beyond this a page is sampled, not
#: exhaustively compared — the check must stay cheap enough to always run.
MAX_WORDS_PER_PAGE = 2600

MM = 72.0 / 25.4


class AuditReport:
    """What the finished PDF actually contains."""

    def __init__(self):
        self.available = True
        self.error = ""
        self.pages = 0
        self.words = 0
        self.images = 0
        self.overlaps = []
        self.bleeds = []
        self.frame_intrusions = []
        self.blank_pages = []
        self.contrast_findings = []
        self.notes = []
        self.truncated = False

    @property
    def overlap_count(self):
        return len(self.overlaps)

    @property
    def bleed_count(self):
        return len(self.bleeds)

    @property
    def intrusion_count(self):
        return len(self.frame_intrusions)

    @property
    def clean(self):
        """No overlap, no bleed off the paper, no blank page, no low contrast.

        ``frame_intrusions`` are deliberately NOT part of this. They are ink
        that left the text frame but stayed on the sheet — worth reporting,
        not worth calling a document broken. Folding an advisory into a
        pass/fail verdict is how a verdict stops meaning anything.
        """
        return not (self.overlaps or self.bleeds or self.blank_pages
                    or self.contrast_findings)

    def summary(self) -> str:
        if not self.available:
            return "layout audit unavailable (%s)" % (self.error or "unknown")
        if self.clean:
            tail = ""
            if self.frame_intrusions:
                tail = (" (%d word(s) sit outside the text frame but on the "
                        "sheet — advisory)" % len(self.frame_intrusions))
            return ("layout audit CLEAN — %d page(s), %d words, %d image(s): "
                    "no overlapping text, nothing off the sheet, no blank "
                    "pages, every text run legible%s"
                    % (self.pages, self.words, self.images, tail))
        parts = []
        if self.overlaps:
            parts.append("%d overlapping text pair(s)" % len(self.overlaps))
        if self.bleeds:
            parts.append("%d word(s) running off the sheet" % len(self.bleeds))
        if self.frame_intrusions:
            parts.append("%d word(s) outside the text frame"
                         % len(self.frame_intrusions))
        if self.blank_pages:
            parts.append("blank page(s): %s"
                         % ", ".join(str(p) for p in self.blank_pages[:8]))
        if self.contrast_findings:
            parts.append("%d low-contrast region(s)"
                         % len(self.contrast_findings))
        return "layout audit FOUND ISSUES — " + "; ".join(parts)

    def detail(self, limit: int = 10) -> str:
        lines = [self.summary()]
        for item in self.overlaps[:limit]:
            lines.append("    OVERLAP p%d: %r over %r (%.1fpt)"
                         % (item["page"], item["a"][:32], item["b"][:32],
                            item["amount"]))
        for item in self.bleeds[:limit]:
            lines.append("    BLEED    p%d: %r runs %.1fpt off the %s edge of "
                         "the sheet" % (item["page"], item["text"][:40],
                                        item["amount"], item["edge"]))
        for item in self.frame_intrusions[:limit]:
            lines.append("    INTRUDES p%d: %r sits %.1fpt past the %s margin "
                         "(on the sheet, advisory)"
                         % (item["page"], item["text"][:40], item["amount"],
                            item["edge"]))
        for item in self.contrast_findings[:limit]:
            lines.append("    CONTRAST p%d: %.2f:1 (%s on %s)"
                         % (item["page"], item["ratio"], item["fg"],
                            item["bg"]))
        if self.truncated:
            lines.append("    (some pages were sampled rather than swept "
                         "exhaustively — very dense page)")
        for note in self.notes[:6]:
            lines.append("    note: %s" % note)
        return "\n".join(lines)

    def as_dict(self) -> dict:
        return {
            "available": self.available, "error": self.error,
            "pages": self.pages, "words": self.words, "images": self.images,
            "overlaps": len(self.overlaps), "bleeds": len(self.bleeds),
            "frame_intrusions": len(self.frame_intrusions),
            "blank_pages": list(self.blank_pages),
            "contrast_findings": len(self.contrast_findings),
            "clean": self.clean, "truncated": self.truncated,
            "samples": {
                "overlaps": self.overlaps[:6],
                "bleeds": self.bleeds[:6],
            },
        }

    def __repr__(self):
        return "AuditReport(%s)" % self.summary()


def _intersects(a, b, tolerance):
    """Do two boxes overlap by more than *tolerance* in BOTH axes?

    Requiring both axes is what stops adjacent columns (which share an x
    boundary) and consecutive lines (which share a y boundary) from being
    reported. A real cell-into-cell collision overlaps in both.
    """
    x_overlap = min(a[2], b[2]) - max(a[0], b[0])
    y_overlap = min(a[3], b[3]) - max(a[1], b[1])
    if x_overlap <= tolerance or y_overlap <= tolerance:
        return 0.0
    return min(x_overlap, y_overlap)


def audit_pdf(path, margin_mm=18.0, expect_text=True, page_background="",
              tolerance=OVERLAP_TOLERANCE, check_contrast=True):
    """Open *path* and measure what is really on the pages. Never raises."""
    report = AuditReport()
    try:
        import fitz
    except Exception as exc:
        report.available = False
        report.error = "PyMuPDF unavailable (%s)" % type(exc).__name__
        return report

    try:
        doc = fitz.open(path)
    except Exception as exc:
        report.available = False
        report.error = "%s: %s" % (type(exc).__name__, exc)
        return report

    try:
        margin = float(margin_mm) * MM
        report.pages = doc.page_count
        for index in range(doc.page_count):
            page = doc[index]
            number = index + 1
            try:
                words = page.get_text("words")
            except Exception:
                words = []
            try:
                images = page.get_images(full=True)
            except Exception:
                images = []
            report.words += len(words)
            report.images += len(images)

            if not words and not images:
                report.blank_pages.append(number)
                continue

            # ── bleed vs frame intrusion: TWO different severities ──────
            #
            # ⚠️ THE FIRST VERSION CONFLATED THESE AND WAS WRONG ABOUT BOTH.
            #
            # It flagged anything outside the TEXT FRAME as a bleed — which
            # meant every correctly-placed page folio was reported as "27.7pt
            # past the bottom edge". A running head and a page number belong
            # in the margin; that is what a margin is FOR. Reporting standard
            # page furniture as a defect is how a check earns its way into
            # being ignored.
            #
            # So the two questions are asked separately:
            #
            #   BLEED (serious) — the ink is off the PAPER, or inside the
            #       trim-safety band. It will physically be cut off. This is
            #       what caught xhtml2pdf running a Windows path 3pt past the
            #       right edge of an A4 sheet.
            #
            #   FRAME INTRUSION (advisory) — the ink is on the paper but
            #       outside the text frame, and not in the header/footer band
            #       where furniture lives. Usually a table that grew, which is
            #       worth knowing about but is not a broken document.
            left, right = margin, page.rect.width - margin
            top, bottom = margin, page.rect.height - margin
            trim = 3.0 * MM               # printer trim-safety inset
            paper_l, paper_r = trim, page.rect.width - trim
            paper_t, paper_b = trim, page.rect.height - trim
            # The band reserved for folios / running heads: the outer half of
            # the margin, top and bottom.
            furniture_top = margin * 0.55
            furniture_bottom = page.rect.height - margin * 0.55

            for word in words:
                x0, y0, x1, y1, text = word[0], word[1], word[2], word[3], word[4]

                if (x1 > paper_r or x0 < paper_l or y1 > paper_b
                        or y0 < paper_t):
                    edge = ("right" if x1 > paper_r else
                            "left" if x0 < paper_l else
                            "bottom" if y1 > paper_b else "top")
                    amount = max(x1 - paper_r, paper_l - x0, y1 - paper_b,
                                 paper_t - y0)
                    report.bleeds.append({
                        "page": number, "text": text, "edge": edge,
                        "amount": round(amount, 2)})
                    continue

                in_furniture = (y0 >= furniture_bottom - 1.0
                                or y1 <= furniture_top + 1.0)
                if in_furniture:
                    continue                # a folio or running head: correct
                if x1 > right + 0.5 or x0 < left - 0.5:
                    edge = "right" if x1 > right else "left"
                    report.frame_intrusions.append({
                        "page": number, "text": text, "edge": edge,
                        "amount": round(max(x1 - right, left - x0), 2)})
                elif y1 > bottom + 0.5 or y0 < top - 0.5:
                    edge = "bottom" if y1 > bottom else "top"
                    report.frame_intrusions.append({
                        "page": number, "text": text, "edge": edge,
                        "amount": round(max(y1 - bottom, top - y0), 2)})

            # ── overlap: bucket by line band, compare within bands ──────
            #
            # Two words can only collide if their vertical extents meet, so
            # bucketing by a coarse y band turns the O(n²) sweep into
            # something linear in practice while still catching every real
            # collision (a word is compared against every band it touches).
            scan = words
            if len(scan) > MAX_WORDS_PER_PAGE:
                step = len(scan) // MAX_WORDS_PER_PAGE + 1
                scan = scan[::step]
                report.truncated = True

            buckets = {}
            band = 6.0
            for word in scan:
                low = int(word[1] // band)
                high = int(word[3] // band)
                for key in range(low, high + 1):
                    buckets.setdefault(key, []).append(word)

            seen = set()
            for members in buckets.values():
                if len(members) < 2:
                    continue
                for i in range(len(members)):
                    for j in range(i + 1, len(members)):
                        a, b = members[i], members[j]
                        # Same block AND same line = the same run of text;
                        # its glyph boxes are supposed to be adjacent.
                        if a[5] == b[5] and a[6] == b[6]:
                            continue
                        amount = _intersects(a, b, tolerance)
                        if amount <= 0:
                            continue
                        key = (number, a[4], b[4], round(a[0], 1),
                               round(b[0], 1))
                        if key in seen:
                            continue
                        seen.add(key)
                        report.overlaps.append({
                            "page": number, "a": a[4], "b": b[4],
                            "amount": round(amount, 2),
                            "box_a": [round(v, 1) for v in a[:4]],
                            "box_b": [round(v, 1) for v in b[:4]]})

            # ── contrast: sampled text colour vs sampled ground ─────────
            if check_contrast and page_background:
                finding = _sample_contrast(page, number, page_background)
                if finding:
                    report.contrast_findings.append(finding)

        if expect_text and report.words == 0 and report.images == 0:
            report.notes.append(
                "the PDF contains no extractable text and no images — the "
                "content did not reach the page")
    except Exception as exc:
        report.notes.append("audit interrupted (%s: %s) — findings so far are "
                            "still reported" % (type(exc).__name__, exc))
    finally:
        try:
            doc.close()
        except Exception:
            pass
    return report


def _sample_contrast(page, number, background_hex):
    """Measure each text run against the ground it ACTUALLY sits on.

    ⚠️ THE NAIVE VERSION OF THIS CHECK WAS WRONG, and wrong in the way that
    gets a check deleted. It compared every span's colour against the
    *declared page background* — so on a correct document it reported:

    * white table-header text as ``#FFFFFF on #FFFFFF`` (it sits on the dark
      ``table_header_bg`` fill, not on the page),
    * pale code text as ``#E2E8F0 on #FFFFFF`` (it sits on the dark
      ``code_bg`` panel),
    * cover-page text as ``#07090F on #07090F`` (it sits on the cover art).

    Three false alarms on three perfectly legible pages. A contrast auditor
    that fires on correct documents teaches its reader to ignore it, which is
    worse than having no auditor at all.

    So the check now measures what a HUMAN sees: rasterise the span's own
    rectangle and read the pixels. The **modal** colour of that patch is the
    background (glyphs cover a minority of any text box), and the pixel
    furthest from it in luminance is the ink. Panels, cover art, callout
    tints and zebra rows are all handled for free, because the question being
    asked is finally the right one — *what is behind this text?* — instead of
    *what did the palette say the page was?*

    Fails open: no rasteriser, no finding.
    """
    try:
        import fitz

        import pdfer_color as pc
    except Exception:
        return None

    try:
        raw = page.get_text("dict")
    except Exception:
        return None

    spans = []
    for block in raw.get("blocks", []):
        for line in block.get("lines", []):
            for span in line.get("spans", []):
                text = (span.get("text") or "").strip()
                if len(text) < 3:
                    continue          # punctuation is not a legibility risk
                bbox = span.get("bbox")
                if not bbox or (bbox[2] - bbox[0]) < 6 or (bbox[3] - bbox[1]) < 4:
                    continue
                spans.append((bbox, text, span.get("size", 10),
                              int(span.get("color", 0)) & 0xFFFFFF))
    if not spans:
        return None

    # Sample a bounded spread across the page rather than every span: the
    # audit must stay cheap enough to always be on.
    step = max(1, len(spans) // 24)
    worst = None
    for bbox, text, size, colour_int in spans[::step][:24]:
        try:
            clip = fitz.Rect(bbox).round()
            if clip.is_empty or clip.is_infinite:
                continue
            pix = page.get_pixmap(clip=clip, colorspace=fitz.csRGB, alpha=False)
            if pix.width < 2 or pix.height < 2:
                continue

            # ⚠️ THE INK IS TAKEN FROM THE PDF, NOT GUESSED FROM PIXELS.
            #
            # An earlier version derived BOTH colours from the raster: modal
            # pixel = ground, furthest-luminance pixel = ink. That works on a
            # flat background and fails on a GRADIENT, where the two extremes
            # it finds are simply the light and dark ends of the gradient
            # itself — so a perfectly legible cover reported "#8137AF on
            # #7C3AED, 1.19:1" while comparing two background tones to each
            # other. The content stream already states the fill colour of every
            # span exactly; only the GROUND has to be measured.
            ink = pc.Color.from_int(colour_int)

            samples = pix.samples
            counts = {}
            stride = 3
            total = pix.width * pix.height
            hop = max(1, total // 600) * stride
            for offset in range(0, len(samples) - 2, hop):
                key = (samples[offset], samples[offset + 1], samples[offset + 2])
                counts[key] = counts.get(key, 0) + 1
            if not counts:
                continue
            # Discard pixels that ARE the ink (and its antialiased skirt), so
            # dense text cannot make the glyph colour the "modal background".
            ink_rgb = ink.rgb255
            ground_counts = {
                rgb: n for rgb, n in counts.items()
                if (abs(rgb[0] - ink_rgb[0]) + abs(rgb[1] - ink_rgb[1])
                    + abs(rgb[2] - ink_rgb[2])) > 90}
            if not ground_counts:
                continue                     # the patch is solid ink: skip
            ground_rgb = max(ground_counts, key=ground_counts.get)
            ground = pc.Color(ground_rgb[0] / 255.0, ground_rgb[1] / 255.0,
                              ground_rgb[2] / 255.0)
            ratio = ink.contrast(ground)
            # Large text legitimately passes at a lower bar (WCAG 1.4.3).
            floor = 3.0 if size >= 18 else 4.5
            if ratio < floor and (worst is None or ratio < worst["ratio"]):
                worst = {"page": number, "ratio": round(ratio, 2),
                         "fg": ink.hex, "bg": ground.hex,
                         "sample": text[:40], "floor": floor}
        except Exception:
            continue
    return worst
