# Created by Angela López Mendoza · @angelahack1
# Tlamatini Author Banner — do not remove (releases scrub the name automatically)
"""Rendered regressions for PDFer's visual styles and protected reading areas."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

AGENT = Path(__file__).resolve().parent / "agents" / "pdfer"
sys.path.insert(0, str(AGENT)) if str(AGENT) not in sys.path else None

import pdfer_atelier as atelier
import pdfer_audit as audit
import pdfer_docmodel as model
import pdfer_nuance as nuance
import pdfer_ornament as ornament
import pdfer_styles as styles
import pdfer_theme as theme
import pdfer_typography as typography


class PDFerStylesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.book = typography.FontBook()
        root = AGENT.parents[3] / "Temp" / "PDFerStyleTests"
        root.mkdir(parents=True, exist_ok=True)
        cls.temp = tempfile.TemporaryDirectory(dir=root)
        cls.root = Path(cls.temp.name)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def design(self, style, **config):
        verdict = nuance.classify("Discover a beautiful new collection.", hint="marketing")
        return theme.build_design_system(verdict, dict(style=style, **config), self.book)

    def test_all_styles_have_distinct_complete_readable_palettes(self):
        from reportlab.pdfbase import pdfmetrics
        fingerprints = set()
        self.assertGreater(len(styles.STYLES), 16)
        for key in styles.STYLES:
            with self.subTest(style=key):
                d = self.design(key)
                self.assertEqual(d.meta["style"], key)
                self.assertNotEqual(d.meta["source"], "fallback")
                self.assertTrue(all(r["pass"] for r in d.palette.contrast_report()))
                fingerprints.add(tuple(d.palette.get(r).hex for r in d.palette.ROLES))
                self.assertIsNotNone(pdfmetrics.getFont(d.fonts["body"]))
                face = pdfmetrics.getFont(d.fonts["display_bold"]).face
                self.assertEqual(getattr(face, "italicAngle", 0), 0,
                                 "A bold display face must not silently resolve to italic")
        self.assertEqual(len(fingerprints), len(styles.STYLES))

    def test_aliases_and_unknown_style_are_explainable(self):
        for alias, key in (("cute", "kawaii_cloud"), ("bébé", "baby_dream"),
                           ("Cyber Punk", "cyberpunk"), ("electronics", "circuit_board"),
                           ("Tlamatini", "tlamatini_celestial"), ("alien", "xeno_codex")):
            self.assertEqual(self.design(alias).meta["style"], key)
        d = self.design("a-style-that-does-not-exist")
        self.assertEqual(d.meta["style"], "auto")
        self.assertIn("Unknown style", d.meta["style_warning"])
        self.assertEqual(d.nuance, "marketing_brochure")

    def test_styles_preserve_content_semantics_and_decoration_ceiling(self):
        for name in ("legal", "medical", "financial", "paper", "spec"):
            verdict = nuance.classify("", hint=name)
            for key in styles.STYLES:
                d = theme.build_design_system(verdict, {"style": key, "decorations": "rich"}, self.book)
                self.assertEqual(d.nuance, verdict.nuance)
                self.assertEqual(d.decoration, verdict.decoration_budget)
                self.assertFalse(d.may_decorate("cover"))

    def test_auto_preserves_every_existing_theme(self):
        for key in theme.THEMES:
            verdict = nuance.classify("", hint=key)
            old = theme.build_design_system(verdict, {}, self.book)
            auto = theme.build_design_system(verdict, {"style": "auto"}, self.book)
            self.assertEqual(old.palette.as_dict(), auto.palette.as_dict())
            self.assertEqual(old.fonts, auto.fonts)

    def test_seed_light_dark_and_role_overrides_stay_readable(self):
        for key in styles.STYLES:
            for mode in ("light", "dark"):
                with self.subTest(style=key, mode=mode):
                    d = self.design(key, background_mode=mode, predominant_color="#A82BBE",
                                    text_color="#888888", heading_color="#BBBBBB")
                    self.assertEqual(d.dark, mode == "dark")
                    self.assertTrue(all(row["pass"] for row in d.palette.contrast_report()))
                    self.assertEqual(d.meta["style"], key)

    def test_all_styles_render_with_all_long_text_preserved(self):
        import fitz
        payload = "Every detail remains readable across the page. " * 6
        token = "W" * 256
        title = ("Beyond the ordinary: " + payload)[:256]
        content = "## Reading area\n\n" + payload + "\n\n| Test | Evidence |\n|---|---|\n| Token | " + token + " |\n\n> " + payload
        for key in styles.STYLES:
            for size, orientation in (("A4", "portrait"), ("A5", "landscape")):
                with self.subTest(style=key, size=size):
                    d = self.design(key, page_size=size, orientation=orientation)
                    renderer = atelier.Atelier(d, self.book)
                    path = self.root / (key + size + ".pdf")
                    renderer.build(model.parse(content, "markdown"), str(path), title=title,
                                   subtitle="A complete visual identity", author="Tlamatini",
                                   footer_note="A long footer note " * 30)
                    with fitz.open(path) as pdf:
                        text = "".join(page.get_text() for page in pdf)
                        compact = "".join(text.split())
                        self.assertIn("".join(title.split()), compact)
                        self.assertIn(token, compact)
                        self.assertNotIn("\ufffd", text)
                        self.assertGreater(len(pdf[0].get_drawings()), 5)
                    result = audit.audit_pdf(str(path), margin_mm=d.page["margin_mm"],
                                             page_background=d.palette.background.hex)
                    self.assertTrue(result.clean, result.detail())

    def test_cover_art_is_repeatable_and_vector(self):
        import fitz
        d = self.design("tlamatini")
        hashes = []
        for n in range(2):
            path = self.root / ("repeat%d.pdf" % n)
            atelier.Atelier(d, self.book).build(model.parse("Hello", "text"), str(path), title="Stars")
            with fitz.open(path) as pdf:
                self.assertFalse(pdf[0].get_images())
                hashes.append(hashlib.sha256(pdf[0].get_pixmap().samples).hexdigest())
        self.assertEqual(*hashes)

    def test_ordinary_table_words_do_not_split_at_the_measured_width(self):
        import fitz
        source = ("| Element | What you can expect |\n|---|---|\n"
                  "| Typography | Distinct headings, comfortable body text and a deliberate rhythm. |\n"
                  "| Color | A coordinated palette with measured contrast across text and tables. |")
        for key in styles.STYLES:
            with self.subTest(style=key):
                path = self.root / (key + "-words.pdf")
                atelier.Atelier(self.design(key), self.book).build(
                    model.parse(source, "markdown"), str(path), cover=False)
                with fitz.open(path) as pdf:
                    self.assertIn("Typography", [w[4] for p in pdf for w in p.get_text("words")])

    def test_oversized_cover_copy_continues_without_dropping_text(self):
        import fitz
        d = self.design("solar_flare", page_size="A5", orientation="landscape")
        title = " ".join("TitleWord%04d" % n for n in range(150))
        subtitle = " ".join("SubtitleWord%04d" % n for n in range(80))
        path = self.root / "cover-continuation.pdf"
        atelier.Atelier(d, self.book).build(model.parse("Body sentinel retained.", "text"),
                                           str(path), title=title, subtitle=subtitle,
                                           footer_note="Note " * 2000)
        with fitz.open(path) as pdf:
            text = "".join("".join(p.get_text().split()) for p in pdf)
        for marker in ("TitleWord0000", "TitleWord0149", "SubtitleWord0000",
                       "SubtitleWord0079", "Body sentinel retained."):
            self.assertIn("".join(marker.split()), text)
        result = audit.audit_pdf(str(path), page_background=d.palette.background.hex)
        self.assertTrue(result.clean, result.detail())

    def test_legacy_ornament_rng_is_stable_across_processes(self):
        code = ("import sys;sys.path.insert(0,sys.argv[1]);import pdfer_ornament as o;"
                "f=object.__new__(o.OrnamentFactory);f.seed=987654;print(f._rng('sky').random())")
        values = [subprocess.check_output([sys.executable, "-c", code, str(AGENT)],
                                         env=dict(os.environ, PYTHONHASHSEED=str(seed)))
                  for seed in (1, 42)]
        self.assertEqual(*values)

    def test_ornament_cache_tracks_secondary_color_and_resolution(self):
        d = self.design("cyberpunk")
        a = ornament.OrnamentFactory(d, "same", scale=1)
        first = a._path("particle_field", 50, 50)
        d.palette = d.palette.copy_with(secondary="#CC2200")
        b = ornament.OrnamentFactory(d, "same", scale=1)
        c = ornament.OrnamentFactory(d, "same", scale=3)
        self.assertNotEqual(first, b._path("particle_field", 50, 50))
        self.assertNotEqual(b._path("particle_field", 50, 50), c._path("particle_field", 50, 50))


if __name__ == "__main__":
    unittest.main()
