# ═══════════════════════════════════════════════════════════════════
#   ✦  T L A M A T I N I  ✦   —   "one who knows"
#
#   Created by  Angela López Mendoza   ·   @angelahack1
#   Developer · Architect · Creator of Tlamatini
#
#   Every line of this file was written by Angela López Mendoza.
# ═══════════════════════════════════════════════════════════════════
#   Tlamatini Author Banner — do not remove (releases scrub the name automatically)
"""Regression guard: a character the chosen font lacks must never vanish.

WHAT THIS FILE DEFENDS
----------------------
2026-11-25, the HandGI guide: "Capture → decision" was set in Corbel, which
has no arrow. ReportLab drew Corbel's empty .notdef glyph, nothing raised,
and the layout audit reported "every text run legible" over a page whose
arrows had disappeared.

1. **FALLBACK.** A missing character is drawn by a face that has it, in
   running text, bold text, a heading, a table cell, a list, a code block and
   the page footer, and the finished PDF is read back to prove it is there.
2. **HONEST FAILURE.** A character no installed face can draw prints as
   U+FFFD and turns the audit from CLEAN to FOUND ISSUES. The audit also sees
   a raw ReportLab .notdef blank, so the legacy engine cannot hide one either.
3. **NO COST WHEN NOT NEEDED.** Text the face covers stays one run, in the
   face that was asked for.

Run: ``python manage.py test agent.test_pdfer_glyph_fallback``
"""

from __future__ import annotations

import os
import sys
import tempfile
import unittest

_AGENT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          "agents", "pdfer")
if _AGENT_DIR not in sys.path:
    sys.path.insert(0, _AGENT_DIR)

try:
    import fitz
    import pdfer_atelier
    import pdfer_audit
    import pdfer_docmodel
    import pdfer_nuance
    import pdfer_theme
    import pdfer_typography as ptypo
    _STACK_OK = True
    _STACK_ERROR = ""
except Exception as exc:                       # pragma: no cover
    _STACK_OK = False
    _STACK_ERROR = "%s: %s" % (type(exc).__name__, exc)

ARROW = "→"
CHECK = "✓"
#: Unassigned in Unicode, so no font anywhere has a glyph for it.
NO_SUCH_GLYPH = "͸"
REPLACEMENT = "�"
#: Body families that ship without arrows on a stock Windows install.
_CANDIDATE_FAMILIES = ("Corbel", "Candara", "Constantia", "Georgia",
                       "Calibri", "Verdana", "Tahoma", "TrebuchetMS",
                       "Palatino", "BookAntiqua", "Rockwell")


def _temp_root():
    base = (os.environ.get("TLAMATINI_TEMP") or "").strip()
    if not base:
        base = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "..", "..", "Temp")
    root = os.path.join(os.path.abspath(base), "PDFerGlyphTests")
    os.makedirs(root, exist_ok=True)
    return root


def _pdf_text(path):
    with fitz.open(path) as doc:
        return "".join(page.get_text() for page in doc)


@unittest.skipUnless(_STACK_OK, "PDFer stack unavailable: %s" % _STACK_ERROR)
class GlyphFallbackTests(unittest.TestCase):
    """Every character reaches the page, or the audit says it did not."""

    @classmethod
    def setUpClass(cls):
        cls.book = ptypo.FontBook()
        cls.temp = tempfile.TemporaryDirectory(dir=_temp_root())

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def _family_without(self, character):
        """(family, regular face) of an installed body family lacking *character*."""
        for family in _CANDIDATE_FAMILIES:
            if self.book.has(family):
                face = self.book.resolve(family)
                if not ptypo.can_draw(face, character):
                    return family, face
        self.skipTest("no installed body family lacks %r" % character)

    def _render(self, markdown, name, **options):
        verdict = pdfer_nuance.classify(markdown, hint="software_manual")
        design = pdfer_theme.build_design_system(verdict, {}, self.book)
        path = os.path.join(self.temp.name, name)
        report = pdfer_atelier.Atelier(design, self.book).build(
            pdfer_docmodel.parse(markdown, "markdown"), path,
            title="Glyph check", **options)
        return path, report, design

    # ── the fallback itself ────────────────────────────────────────────────
    def test_a_face_without_the_arrow_gets_one_that_has_it(self):
        _family, face = self._family_without(ARROW)
        fallback = ptypo.fallback_for(ARROW, face)
        self.assertTrue(fallback, "no installed face draws %r" % ARROW)
        self.assertTrue(ptypo.can_draw(fallback, ARROW))

    def test_covered_text_stays_one_run_in_the_requested_face(self):
        _family, face = self._family_without(ARROW)
        self.assertEqual(ptypo.text_runs("Capture to decision", face),
                         [("Capture to decision", face)])
        self.assertFalse(ptypo.needs_glyph_fallback("Capture to decision", face))

    def test_only_the_missing_character_moves_to_the_fallback(self):
        _family, face = self._family_without(ARROW)
        text = "Capture " + ARROW + " decision"
        runs = ptypo.text_runs(text, face, record=False)
        self.assertEqual("".join(run for run, _ in runs), text,
                         "the text itself must never change")
        for run, run_face in runs:
            for character in run:
                self.assertTrue(ptypo.can_draw(run_face, character),
                                "%r is set in %s, which cannot draw it"
                                % (character, run_face))
        self.assertEqual([run_face == face for _run, run_face in runs],
                         [True, False, True])

    def test_bold_text_gets_a_fallback_that_draws_it(self):
        family, _face = self._family_without(ARROW)
        bold = self.book.resolve(family, "bold")
        if ptypo.can_draw(bold, ARROW):
            self.skipTest("%s draws the arrow itself" % bold)
        fallback = ptypo.fallback_for(ARROW, bold)
        self.assertTrue(fallback)
        self.assertTrue(ptypo.can_draw(fallback, ARROW))

    def test_measured_width_is_the_width_of_the_glyph_drawn(self):
        from reportlab.pdfbase import pdfmetrics
        _family, face = self._family_without(ARROW)
        fallback = ptypo.fallback_for(ARROW, face)
        self.assertAlmostEqual(self.book.text_width(ARROW, face, 10),
                               pdfmetrics.stringWidth(ARROW, fallback, 10),
                               places=3)

    def test_invisible_format_characters_never_become_blanks(self):
        _family, face = self._family_without(ARROW)
        zero_width = "​"
        joined = "".join(run for run, _ in ptypo.text_runs(
            "a" + zero_width + "b", face, record=False))
        expected = ("a" + zero_width + "b" if ptypo.can_draw(face, zero_width)
                    else "ab")
        self.assertEqual(joined, expected)

    def test_helpers_never_raise(self):
        for text in (None, "", "plain", ARROW * 3, NO_SUCH_GLYPH):
            for face in ("NoSuchFontAnywhere", "Helvetica", "Courier"):
                self.assertIsInstance(
                    ptypo.text_runs(text, face, record=False), list)
        self.assertEqual(ptypo.apply_glyph_fallback([]), [])
        self.assertIsNone(ptypo.apply_glyph_fallback(None))

    # ── the finished file ───────────────────────────────────────────────────
    def test_every_arrow_reaches_the_page(self):
        """Heading, text, bold, table, list, code and footer, read back from the PDF."""
        markdown = (
            "# Flow " + ARROW + " overview\n\n"
            "Capture " + ARROW + " decision, and **bold " + ARROW + " text**.\n\n"
            "| Step | Path |\n|---|---|\n| one | camera " + ARROW + " GPU |\n\n"
            "- list " + ARROW + " item\n\n"
            "```\ncamera " + ARROW + " decision " + CHECK + "\n```\n")
        path, report, design = self._render(
            markdown, "arrows.pdf", footer_note="Footer " + ARROW + " note")
        text = _pdf_text(path)
        self.assertGreaterEqual(text.count(ARROW), markdown.count(ARROW) + 1,
                                "an arrow went missing:\n" + text)
        self.assertIn(CHECK, text)
        self.assertNotIn(REPLACEMENT, text)
        if not ptypo.can_draw(design.fonts["body"], ARROW):
            self.assertIn(ARROW, report["glyph_substitutions"])
            self.assertTrue(any(repair.startswith("glyph fallback")
                                for repair in report["repairs"]),
                            report["repairs"])
        audit = pdfer_audit.audit_pdf(path, margin_mm=design.page["margin_mm"],
                                      check_contrast=False)
        self.assertEqual(audit.missing_glyph_count, 0, audit.detail())
        self.assertEqual(audit.overlap_count, 0, audit.detail())

    def test_a_character_no_font_has_fails_the_audit(self):
        path, report, design = self._render(
            "Before " + NO_SUCH_GLYPH + " after.\n", "missing.pdf")
        self.assertIn(NO_SUCH_GLYPH, report["missing_glyphs"])
        audit = pdfer_audit.audit_pdf(path, margin_mm=design.page["margin_mm"],
                                      check_contrast=False)
        audit.note_missing_glyphs(report["missing_glyphs"])
        self.assertFalse(audit.clean, audit.detail())
        self.assertGreater(audit.missing_glyph_count, 0)
        self.assertIn("no installed font can draw", audit.summary())
        self.assertNotIn("every text run legible", audit.summary())

    def test_the_audit_sees_a_raw_notdef_blank(self):
        """The legacy engine draws through ReportLab with no fallback at all."""
        from reportlab.pdfgen import canvas
        _family, face = self._family_without(ARROW)
        path = os.path.join(self.temp.name, "raw_notdef.pdf")
        pdf = canvas.Canvas(path)
        pdf.setFont(face, 14)
        pdf.drawString(72, 700, "Capture " + ARROW + " decision")
        pdf.save()
        audit = pdfer_audit.audit_pdf(path, margin_mm=18, check_contrast=False)
        self.assertGreater(audit.missing_glyph_count, 0, audit.detail())
        self.assertFalse(audit.clean)


if __name__ == "__main__":
    unittest.main()
