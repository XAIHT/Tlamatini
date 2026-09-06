# ═══════════════════════════════════════════════════════════════════
#   ✦  T L A M A T I N I  ✦   —   "one who knows"
#
#   Created by  Angela López Mendoza   ·   @angelahack1
#   Developer · Architect · Creator of Tlamatini
#
#   Every line of this file was written by Angela López Mendoza.
# ═══════════════════════════════════════════════════════════════════
#   Tlamatini Author Banner — do not remove (releases scrub the name automatically)
"""Regression guard for the PDFer nuance / typography / layout overhaul.

WHAT THIS FILE DEFENDS
----------------------
Angela's report, 2026-09-06: *"actually is way too flaky, way too mediocre …
this version always overlaps the cell's contents into another cells, it only
uses an ugly brown scheme of color, the same stupid font"*.

Every one of those three is pinned here, plus the contracts that make the fix
survivable:

1. **OVERLAP** — the measured bug. Three real tables that broke the old
   engine are solved and RENDERED, and the resulting PDF is re-opened and
   measured. ``xhtml2pdf`` reported ``err=0`` on all three, so the assertion
   is against the file, never against a renderer's self-report.
2. **COLOUR** — no theme may ship an unreadable role. Every one of the twenty
   themes, and every seeded palette, must clear its WCAG floor.
3. **TYPE** — the pairing catalog must resolve to fonts ReportLab can
   actually set, and the modular scale must be monotonic.
4. **SAFETY** — a contract, a dosage chart and a financial statement must get
   NO generated ornament, and no config flag may raise that ceiling.
5. **CONTRACTS** — the KV header PDFer emits, the Parametrizer field tuple,
   the Ask-Execs allowlist, and ``verbatim_fields`` must agree with each
   other. These are the couplings that rot silently.

⚠️ COUNTS AND FIELD LISTS ARE **DERIVED**, NEVER TYPED.
The 2026-08-16 lesson: a hand-typed number in a test is a time bomb that goes
red for the wrong reason and sends the reader to the wrong file. So the
Parametrizer check reads the tuple from the registry and the KV keys from the
agent's own source, and compares the two — an added field passes, a
*divergent* one fails.

Run: ``python manage.py test agent.test_pdfer_nuance_layout``
"""

from __future__ import annotations

import ast
import os
import re
import sys
import unittest

_AGENT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          "agents", "pdfer")
if _AGENT_DIR not in sys.path:
    sys.path.insert(0, _AGENT_DIR)

try:
    import pdfer_audit
    import pdfer_color
    import pdfer_docmodel
    import pdfer_nuance
    import pdfer_ornament
    import pdfer_tables
    import pdfer_theme
    import pdfer_typography
    _STACK_OK = True
    _STACK_ERROR = ""
except Exception as exc:                       # pragma: no cover
    _STACK_OK = False
    _STACK_ERROR = "%s: %s" % (type(exc).__name__, exc)

try:
    from reportlab.lib.pagesizes import A4      # noqa: F401
    _REPORTLAB = True
except Exception:                              # pragma: no cover
    _REPORTLAB = False

MM = 72.0 / 25.4


def _temp_dir():
    base = (os.environ.get("TLAMATINI_TEMP") or "").strip()
    if not base:
        base = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "..", "..", "Temp")
    out = os.path.join(os.path.abspath(base), "PDFerTests")
    os.makedirs(out, exist_ok=True)
    return out


# ── the three tables that actually broke, kept verbatim ──────────────────
BROKEN_TABLES = {
    "long_unbreakable_tokens": [
        ["Key", "Value"],
        ["install_path",
         r"C:\Users\angel\AppData\Local\Programs\Tlamatini\TlamatiniSourceCode"
         r"\agent\agents\pdfer\config.yaml"],
        ["endpoint",
         "https://raw.githubusercontent.com/XAIHT/Tlamatini/main/Tlamatini/"
         "agent/agents/pdfer/pdfer.py"],
    ],
    "eight_columns": [
        ["Agent", "Transport", "Command", "Timeout", "Idle", "Grace",
         "Description", "Status"],
        ["netspeed_calculator", "streamable-http",
         "npx -y @modelcontextprotocol/server-memory", "180", "10", "2",
         "Measures throughput with DerSimonian-Laird fusion", "operational"],
        ["instant_messaging_doctor", "stdio",
         "python -m agent.acpx.self_acp_server", "45", "6", "12",
         "Diagnoses Telegrammer and Whatsapper readiness", "degraded"],
    ],
    "wide_headers": [
        ["Identifier", "Fully qualified configuration key", "Default value",
         "Accepted range", "Consumer"],
        ["unified_agent_llm_step_timeout_seconds",
         "agent.self_healing.SelfHealingInvoker.timeout", "80", "1..3600",
         "MultiTurnToolAgentExecutor"],
    ],
}


@unittest.skipUnless(_STACK_OK, "PDFer design stack unavailable: %s" % _STACK_ERROR)
class TableOverlapTests(unittest.TestCase):
    """The headline bug: cell text printed on top of other cell text."""

    def setUp(self):
        self.book = pdfer_typography.FontBook()
        pair = self.book.pairing("technical")
        self.solver = pdfer_tables.TableSolver(
            measure=self.book.text_width, body_font=pair["body"],
            head_font=pair["body_bold"], padding=6.0)
        self.available = 595.276 - 2 * 18 * MM

    def test_solved_widths_never_exceed_the_frame(self):
        """The single invariant the whole fix rests on."""
        for name, rows in BROKEN_TABLES.items():
            layout = self.solver.solve(rows, self.available, font_size=10.5)
            self.assertLessEqual(
                layout.total_width, self.available + 0.75,
                "%s: solved widths sum to %.2f but the frame is only %.2f"
                % (name, layout.total_width, self.available))

    def test_every_column_clears_its_measured_minimum(self):
        """A column narrower than its widest unbreakable atom MUST overflow.

        This is the property that makes the guarantee structural rather than
        empirical: if every column is at least as wide as its narrowest
        possible content, a Paragraph cannot draw outside it.
        """
        for name, rows in BROKEN_TABLES.items():
            layout = self.solver.solve(rows, self.available, font_size=10.5)
            for index, demand in enumerate(layout.demands):
                floor = (demand.min_hard if index in layout.char_wrap_cols
                         else demand.min_soft)
                self.assertGreaterEqual(
                    layout.col_widths[index] + 0.5, floor,
                    "%s column %d got %.2fpt but needs at least %.2fpt"
                    % (name, index, layout.col_widths[index], floor))

    def test_absurd_column_count_still_fits(self):
        rows = [["c%02d" % i for i in range(24)],
                ["value_%d_long" % i for i in range(24)]]
        layout = self.solver.solve(rows, self.available, font_size=10.5)
        self.assertLessEqual(layout.total_width, self.available + 0.75)
        self.assertTrue(layout.char_wrap_cols,
                        "24 columns on A4 must trigger character wrapping")

    def test_solver_never_raises(self):
        """Fail-open: degenerate input yields a layout, never an exception."""
        for rows in ([], [[]], [[None, None]], [["x"]] * 200,
                     [["a" * 5000]], [[1, 2.5, None, True]]):
            layout = self.solver.solve(rows, self.available)
            self.assertIsNotNone(layout)
            if layout.col_widths:
                self.assertLessEqual(layout.total_width, self.available + 0.75)

    def test_the_users_text_is_never_mutated(self):
        """Rungs 1-4 change fonts, sizes and WRAP MODES — never characters.

        A filesystem path with a hyphen or a space injected into it is wrong
        data, and a document that corrupts the path it documents is worse
        than one that wraps it awkwardly.
        """
        path = BROKEN_TABLES["long_unbreakable_tokens"][1][1]
        atoms = pdfer_tables.soft_break_points(path)
        self.assertEqual("".join(atoms), path,
                         "soft_break_points must partition the token exactly")

    @unittest.skipUnless(_REPORTLAB, "ReportLab unavailable")
    def test_rendered_pdf_has_no_overlap_and_no_bleed(self):
        """THE decisive test: measure the produced file, not our intentions.

        ``xhtml2pdf`` returned ``err = 0`` for every one of these tables while
        printing one cell on top of another, which is exactly why the
        assertion here is against glyph boxes read back out of the PDF.
        """
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import ParagraphStyle
        from reportlab.platypus import (Paragraph, SimpleDocTemplate, Table,
                                        TableStyle)

        pair = self.book.pairing("technical")
        margin = 18 * MM
        for name, rows in BROKEN_TABLES.items():
            layout = self.solver.solve(rows, self.available, font_size=10.5)
            base = ParagraphStyle("c", fontName=pair["body"],
                                  fontSize=layout.font_size,
                                  leading=layout.font_size * 1.25,
                                  textColor=colors.HexColor("#101010"))
            cjk = ParagraphStyle("cjk", parent=base, wordWrap="CJK")
            data = [[Paragraph(str(cell),
                               cjk if col in layout.char_wrap_cols else base)
                     for col, cell in enumerate(row)] for row in rows]
            table = Table(data, colWidths=layout.col_widths, repeatRows=1)
            table.setStyle(TableStyle([
                ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#BBBBBB")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), layout.padding),
                ("RIGHTPADDING", (0, 0), (-1, -1), layout.padding),
            ]))
            path = os.path.join(_temp_dir(), "overlap_%s.pdf" % name)
            SimpleDocTemplate(path, pagesize=A4, leftMargin=margin,
                              rightMargin=margin, topMargin=margin,
                              bottomMargin=margin).build([table])

            report = pdfer_audit.audit_pdf(path, margin_mm=18,
                                           check_contrast=False)
            if not report.available:
                self.skipTest("PyMuPDF unavailable: %s" % report.error)
            self.assertEqual(
                report.overlap_count, 0,
                "%s produced overlapping text:\n%s" % (name, report.detail(6)))
            self.assertEqual(
                report.bleed_count, 0,
                "%s ran off the sheet:\n%s" % (name, report.detail(6)))


@unittest.skipUnless(_STACK_OK, "PDFer design stack unavailable")
class NuanceDetectionTests(unittest.TestCase):
    """The look is calculated from the CONTENT — Angela's two named cases."""

    SCIENCE = ("A tokamak confines a deuterium-tritium plasma with a toroidal "
               "magnetic field of 5 T and a poloidal field from a 15 MA plasma "
               "current. Superconducting magnets operate at 4 K in "
               "supercritical helium; the plasma reaches 150 MHz cyclotron "
               "frequencies above 100 million K. Neutron flux at the first "
               "wall approaches 2 MW/m2, driving tungsten sputtering and "
               "helium embrittlement of the lattice.")

    PAPER = ("# Coherent Phonon Transport\n## Abstract\nWe report anomalous "
             "thermal conductivity below the Neel temperature (p < 0.01).\n"
             "**Keywords:** phonon transport\n## 1. Introduction\nPrior work "
             "(Delgado et al., 2023) established this [4, 7, 12].\n"
             "## 2. Methodology\nRaman spectroscopy at 532 nm.\n"
             "## 3. Results\nConductivity 41.2 W/m/K.\n## References\n"
             "[1] Delgado, R. (2023). doi:10.1038/s41567-023-00001")

    def test_science_content_gets_the_dark_treatment(self):
        """Angela: 'science and technology → background black, font white'."""
        verdict = pdfer_nuance.classify(self.SCIENCE)
        self.assertEqual(verdict.nuance, "scientific_dark",
                         "science prose must classify as scientific_dark:\n%s"
                         % verdict.explain())
        design = pdfer_theme.build_design_system(verdict, {})
        self.assertTrue(design.dark, "scientific_dark must use a dark ground")
        self.assertTrue(design.palette.background.is_dark)
        self.assertGreater(design.palette.text.luminance, 0.7,
                           "the body text on a dark ground must be near-white")

    def test_a_paper_gets_the_journal_treatment(self):
        """Angela: 'an abstract … white background, black font, LaTeX styled'."""
        verdict = pdfer_nuance.classify(self.PAPER)
        self.assertEqual(verdict.nuance, "academic_paper", verdict.explain())
        design = pdfer_theme.build_design_system(verdict, {})
        self.assertFalse(design.dark)
        self.assertEqual(design.palette.background.hex, "#FFFFFF")
        self.assertLess(design.palette.text.luminance, 0.05,
                        "a journal article is set in near-black")
        self.assertTrue(design.justify, "a typeset paper is justified")
        self.assertEqual(design.decoration, "restrained")

    def test_structure_outranks_vocabulary(self):
        """An abstract + references beats a pile of science words.

        Both documents are about the same physics; only one is shaped like a
        paper. The classifier must read the SHAPE.
        """
        self.assertEqual(pdfer_nuance.classify(self.PAPER).nuance,
                         "academic_paper")
        self.assertEqual(pdfer_nuance.classify(self.SCIENCE).nuance,
                         "scientific_dark")

    def test_explicit_nuance_wins_over_detection(self):
        verdict = pdfer_nuance.classify(self.SCIENCE, hint="legal")
        self.assertEqual(verdict.nuance, "legal_instrument")
        self.assertEqual(verdict.source, "explicit")
        self.assertEqual(verdict.confidence, 1.0)

    def test_nuance_aliases_are_forgiving(self):
        for spelling in ("science", "Scientific", "TECH", "ciencia",
                         "scientific_dark", "scientific dark"):
            self.assertEqual(pdfer_nuance.normalise_nuance(spelling),
                             "scientific_dark", "alias %r failed" % spelling)
        for empty in ("", "auto", "  ", "not-a-real-nuance"):
            self.assertEqual(pdfer_nuance.normalise_nuance(empty), "",
                             "%r must fall through to detection" % empty)

    def test_classifier_never_raises(self):
        for blob in ("", "   \n\n ", "x", "\x00\x01\x02" * 500,
                     "word " * 50000, None):
            verdict = pdfer_nuance.classify(blob)
            self.assertIn(verdict.nuance, pdfer_nuance.NUANCES)

    def test_unreadable_content_is_never_confident(self):
        """A byte dump must not be handed a confident treatment."""
        noise = "".join(chr(33 + (i * 7) % 90) for i in range(4000))
        verdict = pdfer_nuance.classify(noise)
        self.assertLessEqual(verdict.confidence, 0.3,
                             "noise scored %.2f — a confidently wrong verdict "
                             "dresses a byte dump as a real document"
                             % verdict.confidence)


@unittest.skipUnless(_STACK_OK, "PDFer design stack unavailable")
class PaletteLegibilityTests(unittest.TestCase):
    """No theme, and no seeded palette, may ship an unreadable role."""

    def test_every_theme_passes_its_contrast_floors(self):
        for nuance in sorted(pdfer_theme.THEMES):
            palette = pdfer_theme.build_design_system(
                _StubVerdict(nuance), {}).palette
            failing = [row for row in palette.contrast_report()
                       if not row["pass"]]
            self.assertFalse(
                failing,
                "theme %s fails: %s" % (nuance, "; ".join(
                    "%s %.2f<%.1f" % (r["check"], r["ratio"], r["floor"])
                    for r in failing)))

    def test_a_seed_colour_produces_a_legible_palette_everywhere(self):
        seeds = ("#7F1D1D", "teal", "#0F52BA", "gold", "midnightblue",
                 "#98FF98", "rgb(220,20,60)", "obsidian")
        for seed in seeds:
            for nuance in ("scientific_dark", "academic_paper",
                           "legal_instrument", "marketing_brochure"):
                design = pdfer_theme.build_design_system(
                    _StubVerdict(nuance), {"predominant_color": seed})
                failing = [r for r in design.palette.contrast_report()
                           if not r["pass"]]
                self.assertFalse(failing, "seed %r on %s fails: %s"
                                 % (seed, nuance, failing))

    def test_ensure_contrast_always_reaches_the_floor(self):
        worst = 99.0
        for bg_hex in ("#FFFFFF", "#000000", "#0B0F17", "#808080", "#FFFF00",
                       "#00008B", "#7F1D1D", "#98FF98"):
            bg = pdfer_color.parse_color(bg_hex)
            for hue in range(0, 360, 45):
                for light in (0.2, 0.5, 0.8):
                    fixed = pdfer_color.ensure_contrast(
                        pdfer_color.Color.from_oklch(light, 0.16, hue), bg,
                        pdfer_color.WCAG_AA_NORMAL, preserve_hue=False)
                    worst = min(worst, fixed.contrast(bg))
        self.assertGreaterEqual(worst, pdfer_color.WCAG_AA_NORMAL,
                                "worst achieved contrast was %.3f" % worst)

    def test_colour_parsing_fails_open(self):
        for junk in ("", None, "not a colour", "#GGGGGG", 3.14, [], {}):
            self.assertEqual(
                pdfer_color.parse_color(junk, "#123456").hex, "#123456")

    def test_oklab_round_trip_is_exact(self):
        for hex_value in ("#000000", "#FFFFFF", "#FF0000", "#7F1D1D",
                          "#0B0F17", "#F59E0B", "#3CB371"):
            start = pdfer_color.parse_color(hex_value)
            back = pdfer_color.Color.from_oklab(*start.to_oklab())
            self.assertLessEqual(
                max(abs(a - b) for a, b in zip(start.rgb255, back.rgb255)), 1,
                "%s did not survive the OKLab round trip" % hex_value)


@unittest.skipUnless(_STACK_OK, "PDFer design stack unavailable")
class DecorationSafetyTests(unittest.TestCase):
    """Angela: ornament only 'if it knows that is plenty safe'."""

    NO_ORNAMENT = ("legal_instrument", "medical_clinical", "financial_ledger")

    def test_precision_critical_nuances_get_no_ornament_at_all(self):
        for nuance in self.NO_ORNAMENT:
            design = pdfer_theme.build_design_system(
                _StubVerdict(nuance, "none"), {})
            self.assertEqual(design.decoration, "none")
            for surface in ("cover", "page_edge", "header_band", "drop_cap",
                            "section_rule", "title_rule"):
                self.assertFalse(
                    design.may_decorate(surface),
                    "%s must not decorate %s — a decorated contract looks "
                    "forged and a decorated dosage chart is dangerous"
                    % (nuance, surface))

    def test_config_can_lower_the_ceiling_but_never_raise_it(self):
        levels = pdfer_nuance.DECORATION_LEVELS
        for budget in levels:
            for request in levels:
                design = pdfer_theme.build_design_system(
                    _StubVerdict("scientific_dark", budget),
                    {"decorations": request})
                self.assertLessEqual(
                    levels.index(design.decoration), levels.index(budget),
                    "budget=%s + request=%s produced %s — the content safety "
                    "ceiling was RAISED" % (budget, request, design.decoration))

    def test_low_confidence_holds_ornament_back(self):
        rich = pdfer_nuance.NuanceVerdict(
            "marketing_brochure", 0.95, {}, [], "en", 1.0, {"words": 900})
        unsure = pdfer_nuance.NuanceVerdict(
            "marketing_brochure", 0.20, {}, [], "en", 1.0, {"words": 900})
        levels = pdfer_nuance.DECORATION_LEVELS
        self.assertLess(levels.index(unsure.decoration_budget),
                        levels.index(rich.decoration_budget),
                        "an unsure classification must decorate less")

    def test_a_paper_gets_a_rule_and_nothing_more(self):
        design = pdfer_theme.build_design_system(
            _StubVerdict("academic_paper", "restrained"), {})
        self.assertTrue(design.may_decorate("title_rule"))
        for surface in ("cover", "page_edge", "header_band", "drop_cap"):
            self.assertFalse(design.may_decorate(surface))

    @unittest.skipUnless(pdfer_ornament.available() if _STACK_OK else False,
                         "Pillow unavailable")
    def test_every_motif_renders_without_raising(self):
        design = pdfer_theme.build_design_system(
            _StubVerdict("scientific_dark"), {})
        factory = pdfer_ornament.OrnamentFactory(design, seed_text="test")
        for motif in pdfer_ornament.MOTIFS:
            path = factory.draw(motif, 240, 120, salt="t")
            self.assertTrue(path and os.path.isfile(path),
                            "motif %s produced nothing" % motif)

    @unittest.skipUnless(pdfer_ornament.available() if _STACK_OK else False,
                         "Pillow unavailable")
    def test_ornament_generation_is_deterministic(self):
        """The same document must produce byte-identical art every run."""
        import hashlib
        design = pdfer_theme.build_design_system(
            _StubVerdict("scientific_dark"), {})
        made = []
        for _ in range(2):
            factory = pdfer_ornament.OrnamentFactory(design, seed_text="fixed")
            path = factory.draw("particle_field", 200, 140, salt="d")
            with open(path, "rb") as handle:
                made.append(hashlib.sha256(handle.read()).hexdigest())
        self.assertEqual(made[0], made[1],
                         "a document that looks different every render is one "
                         "nobody can trust")


@unittest.skipUnless(_STACK_OK, "PDFer design stack unavailable")
class TypographyTests(unittest.TestCase):
    """Angela: 'the same stupid font' — and 'perfect differentiated titles'."""

    def setUp(self):
        self.book = pdfer_typography.FontBook()

    def test_every_pairing_resolves_to_a_settable_face(self):
        from reportlab.pdfbase import pdfmetrics
        for name in pdfer_typography.PAIRINGS:
            pairing = self.book.pairing(name)
            for role in ("display", "display_bold", "body", "body_bold",
                         "body_italic", "body_bolditalic", "mono", "mono_bold"):
                face = pairing[role]
                self.assertTrue(face, "%s.%s resolved empty" % (name, role))
                pdfmetrics.stringWidth("Angela López Mendoza", face, 11)

    def test_the_type_scale_is_strictly_decreasing(self):
        for ratio in (1.15, 1.2, 1.25, 1.333, 1.414):
            sizes = pdfer_typography.TypeScale(10.5, ratio).as_dict()
            ladder = [sizes["cover_title"], sizes["title"], sizes["h1"],
                      sizes["h2"], sizes["h3"], sizes["h4"], sizes["body"],
                      sizes["caption"], sizes["footer"]]
            self.assertEqual(ladder, sorted(ladder, reverse=True),
                             "ratio %s does not differentiate the levels: %s"
                             % (ratio, ladder))

    def test_leading_eases_down_as_type_grows(self):
        scale = pdfer_typography.TypeScale(10.5, 1.25)
        factors = [scale.leading(size) / size for size in (9, 14, 20, 30, 42)]
        self.assertEqual(factors, sorted(factors, reverse=True),
                         "a large title needs proportionally LESS leading")

    def test_measurement_beats_the_half_em_guess(self):
        """Why the solver measures instead of estimating."""
        face = self.book.pairing("technical")["body"]
        narrow = self.book.text_width("lllllllllll", face, 10.5)
        wide = self.book.text_width("WWWWWWWWWWW", face, 10.5)
        self.assertGreater(wide, narrow * 2.0,
                           "real metrics must distinguish 'lll' from 'WWW' — "
                           "a per-character estimate cannot, and that is how "
                           "content escapes its cell")


@unittest.skipUnless(_STACK_OK, "PDFer design stack unavailable")
class DocumentModelTests(unittest.TestCase):

    def test_markdown_tables_survive_parsing(self):
        doc = pdfer_docmodel.parse(
            "| A | B |\n|---|---|\n| 1 | 2 |\n| 3 | 4 |", "markdown")
        tables = doc.tables()
        self.assertEqual(len(tables), 1)
        self.assertEqual(tables[0].ncols, 2)
        self.assertEqual(len(tables[0].rows), 3)

    def test_malformed_html_still_yields_content(self):
        doc = pdfer_docmodel.parse(
            "<table><tr><td>kept</td><tr><td>also kept", "html")
        self.assertGreater(doc.total_text(), 0,
                           "an unclosed table must be recovered, not dropped")

    def test_parser_never_raises_and_never_loses_everything(self):
        for blob in ("", "<<<>>>", "&&&", "\x00\x01", "<p>" * 5000):
            doc = pdfer_docmodel.parse(blob)
            self.assertIsNotNone(doc.blocks)

    def test_inline_markup_is_escaped_for_platypus(self):
        rendered = pdfer_docmodel.inline_to_platypus("a & b < c > d")
        self.assertNotIn("& ", rendered.replace("&amp;", ""))
        self.assertIn("&amp;", rendered)


# ═══════════════════════════════════════════════════════════════════════
#  CONTRACT COHERENCE — the couplings that rot silently
# ═══════════════════════════════════════════════════════════════════════
class ContractCoherenceTests(unittest.TestCase):
    """Every list that must agree with another list.

    ⚠️ NOTHING HERE IS A TYPED COUNT. Each side is read from source and
    compared to the other, so adding a field passes and DIVERGING fails.
    """

    @staticmethod
    def _agent_source():
        path = os.path.join(_AGENT_DIR, "pdfer.py")
        with open(path, "r", encoding="utf-8") as handle:
            return handle.read()

    def test_emitted_kv_header_matches_the_parametrizer_registry(self):
        """The INI_SECTION keys PDFer emits vs the fields Parametrizer knows.

        The KV header is lifted from the agent's own ``outcome`` dict literal
        by AST, so this cannot drift by editing one side.
        """
        from agent.services.agent_contracts import _PARAMETRIZER_OUTPUT_FIELDS

        tree = ast.parse(self._agent_source())
        emitted = set()
        for node in ast.walk(tree):
            if not isinstance(node, ast.Assign):
                continue
            targets = [t.id for t in node.targets if isinstance(t, ast.Name)]
            if "outcome" not in targets or not isinstance(node.value, ast.Dict):
                continue
            for key in node.value.keys:
                if isinstance(key, ast.Constant) and isinstance(key.value, str):
                    emitted.add(key.value)
        self.assertTrue(emitted, "could not read PDFer's outcome dict")

        registered = set(_PARAMETRIZER_OUTPUT_FIELDS["pdfer"])
        registered.discard("response_body")      # the body, not a KV field

        missing = emitted - registered
        self.assertFalse(
            missing,
            "PDFer emits %s but agent_contracts._PARAMETRIZER_OUTPUT_FIELDS"
            "['pdfer'] does not list them — a downstream Parametrizer cannot "
            "address a field the registry has never heard of. "
            "(views.PARAMETRIZER_SOURCE_OUTPUT_FIELDS is DERIVED from that "
            "registry; never hand-edit it.)" % sorted(missing))

        stale = registered - emitted
        self.assertFalse(
            stale,
            "agent_contracts lists %s for pdfer but the agent never emits "
            "them — a flow mapping those fields would resolve to nothing"
            % sorted(stale))

    def test_pdfer_is_a_registered_parametrizer_source(self):
        path = os.path.join(_AGENT_DIR, "..", "parametrizer",
                            "parametrizer.py")
        with open(os.path.abspath(path), "r", encoding="utf-8") as handle:
            body = handle.read()
        self.assertIn("'pdfer'", body,
                      "parametrizer.SECTION_AGENT_TYPES must contain 'pdfer'")

    def test_pdfer_declares_its_verbatim_fields(self):
        """``input_text`` is literal source text and must not be de-escaped.

        The generic parser collapses ``\\\\`` to ``\\``, which corrupts every
        Windows path and every escape in a Markdown document — the same class
        of silent corruption that flattened every table in Angela's OpenMP
        report before LaTeXer declared its own fields in 2026-08.
        """
        from agent.chat_agent_registry import WRAPPED_CHAT_AGENT_BY_TOOL_NAME

        spec = WRAPPED_CHAT_AGENT_BY_TOOL_NAME["chat_agent_pdfer"]
        self.assertIn("input_text", getattr(spec, "verbatim_fields", ()) or (),
                      "PDFer must declare input_text as a verbatim field")

    def test_pdfer_stays_on_the_ask_execs_allowlist(self):
        """It writes to a free-form output_dir + filename, like File-Creator."""
        from agent.mcp_agent import _ASK_EXECS_REQUIRED_TOOLS

        self.assertIn("chat_agent_pdfer", _ASK_EXECS_REQUIRED_TOOLS,
                      "PDFer can overwrite an arbitrary file and belongs on "
                      "the tier-A allowlist")

    def test_every_config_key_the_agent_reads_exists_in_config_yaml(self):
        """A knob the code reads but the template never declares is invisible.

        Nobody can discover it, the canvas dialog will not show it, and the
        Flow Compiler will not carry it — so it may as well not exist.
        """
        import yaml

        source = self._agent_source()
        keys = set(re.findall(r'_cfg\(config,\s*["\']([a-z0-9_]+)["\']',
                              source))
        with open(os.path.join(_AGENT_DIR, "config.yaml"), "r",
                  encoding="utf-8") as handle:
            declared = set((yaml.safe_load(handle) or {}).keys())
        # Read-only conveniences the agent derives rather than declares.
        exempt = {"cover"}
        missing = keys - declared - exempt
        self.assertFalse(
            missing,
            "pdfer.py reads %s but config.yaml never declares them"
            % sorted(missing))


class _StubVerdict:
    """A verdict stand-in, so themes can be tested without content."""

    def __init__(self, nuance, budget="rich"):
        self.nuance = nuance
        self._budget = budget
        self.language = "en"
        self.confidence = 0.9
        self.metrics = {"words": 500}

    @property
    def decoration_budget(self):
        return self._budget


if __name__ == "__main__":            # pragma: no cover
    unittest.main(verbosity=2)
