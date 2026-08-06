"""Regression guards for the LaTeXer REPAIR LADDER (Layer 05).

Every test here pins a bug that was REAL: each one failed against an earlier
revision of the ladder during its first live run on 2026-08-05. They are pure
functions over strings, so the whole file runs in milliseconds and needs no TeX
distribution; the end-to-end build proof lives separately and is skipped when
no engine is installed.

DO NOT relax these. Each maps to a specific way an automatic repair can quietly
damage a document, which is far worse than a build that simply fails.
"""
import os
import sys
import unittest
import importlib.util

_LATEXER_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "agents", "latexer", "latexer.py")


def _load_latexer():
    """Import latexer.py WITHOUT running its agent bootstrap side effects.

    The module writes a PID file and truncates a log at import time when run as
    a pool agent; importing it under a throwaway module name from the test
    process is safe because all of that lives inside main(), but the log path
    is still resolved relative to the CWD, so it is loaded once and cached.
    """
    if "latexer_under_test" in sys.modules:
        return sys.modules["latexer_under_test"]
    spec = importlib.util.spec_from_file_location("latexer_under_test", _LATEXER_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules["latexer_under_test"] = module
    spec.loader.exec_module(module)
    return module


LX = _load_latexer()


class PackageInferenceTests(unittest.TestCase):
    """Rung 2 must infer the RIGHT package, and only when it is really needed."""

    def test_begin_does_not_infer_tikz(self):
        """\\begin must never map to a package.

        ``\\begin{tikzpicture}`` truncates to the bare token ``\\begin`` when the
        command index is built, so registering environment rows in the command
        map made EVERY document containing any \\begin infer tikz. The live
        trace showed "added tikz (tikz needed by \\begin)" on 11 unrelated
        documents, including a plain letter.
        """
        self.assertEqual(LX.package_for_command("\\begin"), "")

    def test_qty_resolves_to_siunitx_not_physics(self):
        """Both packages define \\qty and they genuinely clash.

        \\qty{5}{\\meter} (siunitx) is overwhelmingly the common usage, so
        siunitx must own the mapping.
        """
        self.assertEqual(LX.package_for_command("\\qty"), "siunitx")

    def test_meter_is_not_owned_by_quantikz(self):
        """quantikz defines \\meter (a measurement gate) but must not claim it.

        A name that generic made LaTeXer add \\usepackage{quantikz} to a
        document about the length of a rod.
        """
        self.assertEqual(LX.package_for_command("\\meter"), "")

    def test_align_environment_infers_amsmath(self):
        scan = LX.scan_required_packages(
            "\\documentclass{article}\n\\begin{document}\n"
            "\\begin{align}\na &= b\n\\end{align}\n\\end{document}\n")
        self.assertIn("amsmath", scan["missing"])

    def test_already_declared_package_is_not_re_added(self):
        scan = LX.scan_required_packages(
            "\\documentclass{article}\n\\usepackage{siunitx}\n"
            "\\begin{document}\n\\qty{5}{\\meter}\n\\end{document}\n")
        self.assertNotIn("siunitx", scan["missing"])

    def test_hyperref_is_ordered_last(self):
        """Load order is functional, not cosmetic: hyperref must come last."""
        ordered = LX.order_packages(["hyperref", "amsmath", "geometry", "cleveref"])
        self.assertEqual(ordered[-2:], ["hyperref", "cleveref"])
        self.assertEqual(ordered[0], "geometry")

    def test_physics_and_siunitx_are_a_known_conflict(self):
        conflicts = LX.detect_package_conflicts(["physics", "siunitx"])
        self.assertTrue(any(winner == "siunitx" for _a, _b, _why, winner in conflicts))


class InstallerFlagTests(unittest.TestCase):
    """`auto_install_packages` must actually control the installer."""

    _TOOLS = {"latex": "pdflatex.exe", "engine": "pdflatex", "distribution": "miktex"}

    def test_false_actively_disables_the_installer(self):
        """Omitting the flag is NOT the same as disabling it.

        Without --disable-installer, MiKTeX falls back to its own global
        AutoInstall setting -- typically "yes" -- so `auto_install_packages:
        false` silently did nothing and packages were still fetched behind the
        user's back. It also made rung 5 unreachable, because MiKTeX always won
        the race to fix a missing package first.
        """
        argv = LX._engine_argv(self._TOOLS, {"auto_install_packages": False}, "doc.tex")
        self.assertIn("--disable-installer", argv)
        self.assertNotIn("--enable-installer", argv)

    def test_true_enables_the_installer(self):
        argv = LX._engine_argv(self._TOOLS, {"auto_install_packages": True}, "doc.tex")
        self.assertIn("--enable-installer", argv)
        self.assertNotIn("--disable-installer", argv)

    def test_default_is_enabled(self):
        argv = LX._engine_argv(self._TOOLS, {}, "doc.tex")
        self.assertIn("--enable-installer", argv)

    def test_non_miktex_gets_neither_flag(self):
        """--enable-installer is MiKTeX-only; TeX Live would reject it."""
        texlive = dict(self._TOOLS, distribution="texlive")
        for value in (True, False):
            argv = LX._engine_argv(texlive, {"auto_install_packages": value}, "doc.tex")
            self.assertNotIn("--enable-installer", argv)
            self.assertNotIn("--disable-installer", argv)

    def test_nonstopmode_is_never_dropped(self):
        """Without it an unattended build hangs forever waiting for a keypress."""
        argv = LX._engine_argv(self._TOOLS, {}, "doc.tex")
        self.assertIn("-interaction=nonstopmode", argv)


class AcquireVerificationTests(unittest.TestCase):
    """Rung 5 must never call an install a success without checking."""

    def test_missing_kpsewhich_means_unverified_not_success(self):
        """Fail CLOSED: if we cannot verify, we must not claim a fix."""
        original = LX._which
        LX._which = lambda name, env: ""
        try:
            self.assertFalse(LX._file_resolves("anything.sty", {}, 5.0))
        finally:
            LX._which = original

    def test_refresh_never_raises(self):
        """A best-effort index refresh must not take the build down with it."""
        original = LX._which
        LX._which = lambda name, env: (_ for _ in ()).throw(RuntimeError("boom"))
        try:
            LX._refresh_filename_database("miktex", {}, 5.0)  # must not raise
        finally:
            LX._which = original


class StaticRepairTests(unittest.TestCase):
    """Rung 1 must repair structure WITHOUT damaging anything else."""

    def test_comments_survive_a_brace_repair(self):
        """THE data-loss guard.

        An early revision scanned _strip_comments(source) and then returned that
        stripped copy, silently deleting every % comment the author wrote.
        """
        source = ("\\documentclass{article}\n"
                  "% ANGELA'S NOTE: keep me\n"
                  "\\begin{document}\n"
                  "% a note with a { brace and a $ dollar inside it\n"
                  "A \\textbf{bold run that never closes.\n"
                  "\\end{document}\n")
        trace = []
        fixed = LX._balance_braces(source, trace)
        self.assertIn("ANGELA'S NOTE: keep me", fixed)
        self.assertIn("a note with a { brace", fixed)

    def test_brace_closes_on_the_opening_line_not_at_the_end(self):
        """Balanced is not enough -- it must also be SEMANTICALLY right.

        Appending every '}' before \\end{document} balances the count, but most
        LaTeX commands are not \\long, so a blank line inside the argument still
        gives "Paragraph ended before \\textbf was complete" and the build fails
        anyway. Cases 02/03 of the live proof were quarantined for this reason.
        """
        source = ("\\documentclass{article}\n\\begin{document}\n"
                  "A \\textbf{bold word that never closes.\n"
                  "\nSecond paragraph.\n\\end{document}\n")
        fixed = LX._balance_braces(source, [])
        line = [ln for ln in fixed.splitlines() if "bold word" in ln][0]
        self.assertTrue(line.rstrip().endswith("}"), "brace was not closed on its own line")

    def test_unclosed_environment_is_closed_before_end_document(self):
        source = ("\\documentclass{article}\n\\begin{document}\n"
                  "\\begin{itemize}\n\\item one\n\\end{document}\n")
        fixed = LX._close_unclosed_environments(source, [])
        self.assertIn("\\end{itemize}", fixed)
        self.assertLess(fixed.index("\\end{itemize}"), fixed.index("\\end{document}"))

    def test_dollar_inside_a_comment_does_not_count(self):
        """A '$' in a comment is not math and must not trigger a repair."""
        source = ("\\documentclass{article}\n\\begin{document}\n"
                  "% costs $5 in total\n"
                  "Balanced $x = 1$ here.\n\\end{document}\n")
        self.assertEqual(LX._balance_inline_math(source, []), source)

    def test_a_repair_that_worsens_lint_is_rejected(self):
        """The gate that makes the whole ladder safe to run unattended."""
        trace = []
        good = "\\documentclass{article}\n\\begin{document}\nfine\n\\end{document}\n"
        bad = "\\documentclass{article}\n\\begin{document}\n\\begin{itemize}\n\\end{document}\n"
        result = LX._accept_if_not_worse(good, bad, "rules", "test", "deliberately worse", trace)
        self.assertEqual(result, good, "a damaging repair was accepted")
        self.assertFalse(trace[-1]["applied"])
        self.assertIn("REJECTED", trace[-1]["detail"])


class RuleRepairTests(unittest.TestCase):
    def test_eqnarray_becomes_align(self):
        source = ("\\documentclass{article}\n\\begin{document}\n"
                  "\\begin{eqnarray}\na &=& b\n\\end{eqnarray}\n\\end{document}\n")
        fixed = LX._repair_deprecated_environments(source, [])
        self.assertIn("\\begin{align}", fixed)
        self.assertIn("\\end{align}", fixed)
        self.assertNotIn("eqnarray", fixed)

    def test_smart_quotes_are_folded(self):
        source = ("\\documentclass{article}\n\\begin{document}\n"
                  "She said \u201chello\u201d \u2014 it\u2019s fine\u2026\n\\end{document}\n")
        fixed = LX._repair_smart_characters(source, [])
        for glyph in ("\u201c", "\u201d", "\u2014", "\u2019", "\u2026"):
            self.assertNotIn(glyph, fixed)

    def test_odd_number_of_double_dollars_is_left_alone(self):
        """Unsafe to pair -> must refuse rather than corrupt the document."""
        source = ("\\documentclass{article}\n\\begin{document}\n"
                  "one $$ two $$ three $$ four\n\\end{document}\n")
        trace = []
        self.assertEqual(LX._repair_display_math(source, trace), source)
        self.assertFalse(trace[-1]["applied"])

    def test_duplicate_labels_are_renamed(self):
        source = ("\\documentclass{article}\n\\begin{document}\n"
                  "\\section{A}\\label{x}\n\\section{B}\\label{x}\n\\end{document}\n")
        fixed = LX._repair_duplicate_labels(source, [])
        self.assertIn("\\label{x}", fixed)
        self.assertIn("\\label{x-dup2}", fixed)


class LogDirectedRepairTests(unittest.TestCase):
    def test_undefined_control_sequence_adds_its_package(self):
        source = ("\\documentclass{article}\n\\begin{document}\n"
                  "\\qty{5}{\\meter}\n\\end{document}\n")
        diag = {"errors": ["! Undefined control sequence. l.3 \\qty"]}
        fixed = LX._repair_from_log(source, diag, [])
        self.assertIn("\\usepackage", fixed)
        self.assertIn("siunitx", fixed)

    def test_unknown_command_is_reported_not_guessed(self):
        """An unmappable command must be NAMED, never silently ignored."""
        trace = []
        source = "\\documentclass{article}\n\\begin{document}\nx\n\\end{document}\n"
        diag = {"errors": ["! Undefined control sequence. l.3 \\notarealcommandanywhere"]}
        LX._repair_from_log(source, diag, trace)
        self.assertTrue(any("not in the symbol universe" in r["detail"] for r in trace))


class BisectTests(unittest.TestCase):
    def test_blocks_never_split_inside_an_environment(self):
        """Splitting inside an environment would orphan a \\begin from its \\end."""
        source = ("\\documentclass{article}\n\\begin{document}\n"
                  "First.\n\n"
                  "\\begin{itemize}\n\n\\item spaced out\n\n\\end{itemize}\n\n"
                  "Last.\n\\end{document}\n")
        _head, blocks, _tail = LX._split_body_blocks(source)
        joined = "".join(blocks)
        for block in blocks:
            self.assertEqual(block.count("\\begin{itemize}"), block.count("\\end{itemize}"),
                             "a block orphaned an environment")
        self.assertIn("\\begin{itemize}", joined)

    def test_probe_document_always_has_typesettable_content(self):
        """An empty body yields "No pages of output" and therefore NO PDF.

        Without a placeholder the very first probe (preamble alone) always
        looked like a failure, so bisection aborted with "the fault is above
        \\begin{document}" on documents whose preamble was perfectly fine.
        """
        source = ("\\documentclass{article}\n\\begin{document}\n"
                  "One.\n\nTwo.\n\\end{document}\n")
        head, blocks, tail = LX._split_body_blocks(source)
        probe = LX._assemble(head, blocks, tail, set())
        self.assertIn("\\mbox{}", probe)

    def test_quarantine_note_is_visible_and_escaped(self):
        note = LX._quarantine_note("100% of \\the_stuff & more", 4)
        self.assertIn("quarantined", note)
        self.assertIn("block 5", note)
        self.assertNotIn("100% of", note, "an unescaped % would comment out the rest of the line")


class LadderContractTests(unittest.TestCase):
    def test_rung_order_puts_the_destructive_rung_last(self):
        """The ORDER is the design, on TWO axes.

        Cheap-and-deterministic first (rungs 1-6 before the model), but the
        tie at the end is broken by DESTRUCTIVENESS: bisect is the only rung
        that deletes the author's content, so it must come after the model.
        The original ordering had bisect at 7 and the model at 8, which meant a
        document the model could have repaired completely was shipped with a
        paragraph cut out of it instead -- and the model rung was effectively
        unreachable, because bisect nearly always produces *something*.
        """
        self.assertEqual(LX.LADDER_RUNGS[0], "lint")
        self.assertEqual(LX.LADDER_RUNGS[-1], "bisect",
                         "the only content-destroying rung must be the last resort")
        self.assertLess(LX.LADDER_RUNGS.index("model"), LX.LADDER_RUNGS.index("bisect"))
        for deterministic in ("lint", "preamble", "rules", "log_directed",
                              "acquire", "engine_swap"):
            self.assertLess(LX.LADDER_RUNGS.index(deterministic),
                            LX.LADDER_RUNGS.index("model"),
                            "%s must be tried before the model" % deterministic)

    def test_a_degraded_build_is_never_reported_as_success(self):
        result = LX._finalise_ladder(
            {"ok": True, "produced": True, "diag": {"errors": []}},
            [], LX.LADDER_RUNGS, [2], "x.tex", {"engine": "pdflatex"}, degraded=True)
        self.assertFalse(result["ok"], "a build with content removed read as a clean success")
        self.assertTrue(result["degraded"])

    def test_rungs_can_be_restricted_by_config(self):
        self.assertEqual(LX._enabled_rungs({"repair_rungs": ["lint", "rules"]}),
                         ("lint", "rules"))
        self.assertEqual(LX._enabled_rungs({}), tuple(LX.LADDER_RUNGS))

    def test_model_rung_is_disabled_without_an_explicit_model(self):
        """Rung 8 must be opt-in: no silent network calls."""
        trace = []
        source = "\\documentclass{article}\n\\begin{document}\nx\n\\end{document}\n"
        self.assertEqual(LX._ollama_repair(source, {}, {"repair_model": ""}, trace), source)
        self.assertFalse(trace[-1]["applied"])

    def test_model_reply_that_looks_truncated_is_discarded(self):
        """Truncation is the characteristic LLM failure on a long document."""
        trace = []
        long_source = ("\\documentclass{article}\n\\begin{document}\n"
                       + ("Real content the author wrote. " * 200)
                       + "\n\\end{document}\n")

        # NOTE: the context-manager protocol resolves __enter__/__exit__ on the
        # TYPE, never on the instance -- a SimpleNamespace with those attributes
        # set raises AttributeError inside `with`, which the repair swallows, so
        # the test would pass for entirely the wrong reason.
        class _FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, *_exc):
                return False

            def read(self):
                return (b'{"response": "\\\\documentclass{article}\\n'
                        b'\\\\begin{document}\\nx\\n\\\\end{document}"}')

        original = LX.urllib.request.urlopen
        LX.urllib.request.urlopen = lambda *a, **k: _FakeResponse()
        try:
            result = LX._ollama_repair(long_source, {"errors": []},
                                       {"repair_model": "test"}, trace)
        finally:
            LX.urllib.request.urlopen = original
        self.assertEqual(result, long_source, "a truncated model reply replaced the document")
        self.assertTrue(any("truncated" in r["detail"] for r in trace))


if __name__ == "__main__":
    unittest.main(verbosity=2)
