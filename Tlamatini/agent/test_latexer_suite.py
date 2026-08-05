# ═══════════════════════════════════════════════════════════════════
#   ✦  T L A M A T I N I  ✦   —   "one who knows"
#
#   Created by  Angela López Mendoza   ·   @angelahack1
#   Developer · Architect · Creator of Tlamatini
# ═══════════════════════════════════════════════════════════════════
#   Tlamatini Author Banner — do not remove
"""LaTeXer — the BIG suite: a fixed, permanent testing asset (150+ tests).

Commissioned by Angela on 2026-08-05: *"a vast powerful set of tests created as a
fixed asset of testing in Python to test LaTeXer with no less than 100 different
tests"*. This file is that asset. It is a PERMANENT part of the repository, not a
throwaway probe, and it is meant to be run on every change to the LaTeXer agent.

RELATIONSHIP TO ``test_latexer_agent.py``
-----------------------------------------
That file is the agent's *birth certificate*: it pins the wiring (migrations, JS,
CSS, registries), the incidents found while building the agent, and the real
end-to-end compiles that need MiKTeX installed. **This file is different on
purpose** — it is a deep, dense, hostile unit-level sweep of LaTeXer's PURE
FUNCTIONS: every coercion, every path-safety rule, every parser branch, every
preflight refusal. It needs **no LaTeX distribution at all**, so it runs green on
any machine, in CI, and inside a frozen build.

WHAT IT PROVES, IN ONE LINE PER AREA
------------------------------------
* coercion    — a value arriving as ``"5 passes"`` from Multi-Turn behaves exactly
                like ``5`` from the canvas, and junk NEVER becomes a silent zero.
* path safety — ``../../etc/passwd`` can never escape ``output_dir``.
* analysis    — comments, fragments, structure, bibliography engine selection.
* validation  — the static linter that works before MiKTeX is even installed.
* log parsing — thousands of lines of TeX noise reduced to the one actionable line.
* templates   — all 8 render, none leaks a ``%%TOKEN%%``, none loads a package twice.
* argv        — ``-interaction=nonstopmode`` is NON-NEGOTIABLE (it is what stops an
                unattended agent hanging forever on a LaTeX error prompt).
* preflight   — LaTeXer REFUSES rather than mis-typeset.

THE BUG THIS SUITE CAUGHT ON ITS FIRST RUN (2026-08-05)
--------------------------------------------------------
``_document_structure`` returned an **empty title and author for every real
document**. Its helper used ``re.search`` with a ``$`` anchor but no
``re.MULTILINE``, so ``$`` only matched the end of the whole file — and
``\title{...}`` lives in the preamble of literally every LaTeX document ever
written. The ``structure`` capability had been reporting blank metadata, silently,
because a blank string looks like a perfectly valid answer. Pinned forever by
``StructureTests.test_title_REGRESSION_multiline_anchor`` and its siblings.

Run it alone, with a per-class breakdown:

    python -m unittest agent.test_latexer_suite -v
    python Tlamatini/agent/test_latexer_suite.py        # rich summary mode
"""
import importlib.util
import io
import logging
import os
import shutil
import tempfile
import unittest


_REPO_AGENT_DIR = os.path.dirname(os.path.abspath(__file__))
_LATEXER_DIR = os.path.join(_REPO_AGENT_DIR, "agents", "latexer")
_MODULE_CACHE = {}


def _load_latexer_module():
    """Import ``agents/latexer/latexer.py`` without corrupting the test runner.

    Every pool agent has top-level side effects (``os.chdir``, truncating its own
    log, ``logging.basicConfig``). Save and restore the cwd and the root logger so
    importing one cannot poison the runner — the same guard the sibling suites use.
    """
    if "mod" in _MODULE_CACHE:
        return _MODULE_CACHE["mod"]

    module_path = os.path.join(_LATEXER_DIR, "latexer.py")
    saved_cwd = os.getcwd()
    root = logging.getLogger()
    saved_handlers = list(root.handlers)
    saved_level = root.level
    try:
        spec = importlib.util.spec_from_file_location(
            "agent_latexer_module_for_big_suite", module_path)
        if spec is None or spec.loader is None:
            raise RuntimeError("Unable to load LaTeXer from %s" % module_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    finally:
        os.chdir(saved_cwd)
        root.handlers[:] = saved_handlers
        root.setLevel(saved_level)

    _MODULE_CACHE["mod"] = module
    return module


def _m():
    return _load_latexer_module()


def _tools(latex="pdflatex.exe", distribution="miktex", engine="pdflatex",
           latexmk="", latexmk_usable=False):
    """The toolchain dict ``_preflight`` / ``_engine_argv`` expect."""
    return {"latex": latex, "engine": engine, "distribution": distribution,
            "latexmk": latexmk, "latexmk_usable": latexmk_usable}


DOC = (
    "\\documentclass[11pt,twoside]{article}\n"
    "\\usepackage{amsmath, graphicx}\n"
    "\\usepackage[utf8]{inputenc}\n"
    "\\title{The Real Title}\n"
    "\\author{Angela López Mendoza}\n"
    "\\begin{document}\n"
    "\\maketitle\n"
    "\\section{Intro}\\label{sec:intro}\n"
    "See \\ref{sec:intro} and \\cite{knuth1984,lamport}.\n"
    "\\subsection{Deeper}\\label{sec:deep}\n"
    "\\end{document}\n"
)


class _Temp(unittest.TestCase):
    """A scratch directory that cleans itself up."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="tlm_latexer_suite_")
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def write(self, name, text=""):
        path = os.path.join(self.tmp, name)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text)
        return path


# ══════════════════════════════════════════════════════════════════════
#  1. MODULE
# ══════════════════════════════════════════════════════════════════════

class ModuleLoadTests(unittest.TestCase):

    def test_the_module_imports(self):
        self.assertIsNotNone(_m())

    def test_import_is_cached_so_side_effects_run_once(self):
        self.assertIs(_m(), _m())

    def test_module_never_imports_the_django_app(self):
        """A pool agent runs as a bare subprocess with no path back into agent.*."""
        with open(os.path.join(_LATEXER_DIR, "latexer.py"), encoding="utf-8") as fh:
            src = fh.read()
        self.assertNotIn("from agent.", src)
        self.assertNotIn("import agent.", src)

    def test_module_is_stdlib_only(self):
        """No third-party dependency may creep in — that is the whole design."""
        with open(os.path.join(_LATEXER_DIR, "latexer.py"), encoding="utf-8") as fh:
            src = fh.read()
        for forbidden in ("import requests", "import fastmcp", "from mcp ",
                          "import pydantic", "import yaml_"):
            self.assertNotIn(forbidden, src)


# ══════════════════════════════════════════════════════════════════════
#  2. COERCION — Multi-Turn hands us strings, the canvas hands us types
# ══════════════════════════════════════════════════════════════════════

class CoercionIntTests(unittest.TestCase):

    def test_plain_int_passes_through(self):
        self.assertEqual(_m()._as_int(5, 1), 5)

    def test_numeric_string(self):
        self.assertEqual(_m()._as_int("7", 1), 7)

    def test_leading_integer_is_extracted_from_prose(self):
        self.assertEqual(_m()._as_int("5 passes", 1), 5)

    def test_negative_numbers_survive(self):
        self.assertEqual(_m()._as_int("-4", 0), -4)

    def test_float_truncates_to_its_leading_digits(self):
        self.assertEqual(_m()._as_int(2.9, 0), 2)

    def test_bool_is_rejected_because_True_is_not_a_count(self):
        self.assertEqual(_m()._as_int(True, 7), 7)
        self.assertEqual(_m()._as_int(False, 7), 7)

    def test_none_falls_back_to_the_default(self):
        self.assertEqual(_m()._as_int(None, 3), 3)

    def test_an_arbitrary_object_can_NEVER_become_a_silent_zero(self):
        """Without the isinstance guard, repr()'s hex address yields digits — so
        junk would quietly become max_passes=0, i.e. never compile at all."""
        self.assertEqual(_m()._as_int(object(), 5), 5)

    def test_a_list_falls_back_rather_than_parsing_its_repr(self):
        self.assertEqual(_m()._as_int([1, 2, 3], 9), 9)

    def test_garbage_text_falls_back(self):
        self.assertEqual(_m()._as_int("abc", 9), 9)

    def test_empty_string_falls_back(self):
        self.assertEqual(_m()._as_int("", 4), 4)

    def test_it_never_raises_on_anything(self):
        for raw in (None, "", "x", {}, [], object(), 1.5, True, -2):
            _m()._as_int(raw, 1)


class CoercionBoolTests(unittest.TestCase):

    def test_real_booleans_pass_through(self):
        self.assertIs(_m()._as_bool(True, False), True)
        self.assertIs(_m()._as_bool(False, True), False)

    def test_true_words(self):
        for raw in ("true", "TRUE", "1", "yes", "on", " On "):
            self.assertIs(_m()._as_bool(raw, False), True, raw)

    def test_false_words(self):
        for raw in ("false", "FALSE", "0", "no", "off"):
            self.assertIs(_m()._as_bool(raw, True), False, raw)

    def test_empty_string_is_FALSE_not_the_default(self):
        """An explicitly blank field means 'off', not 'whatever you like'."""
        self.assertIs(_m()._as_bool("", True), False)

    def test_none_takes_the_default(self):
        self.assertIs(_m()._as_bool(None, True), True)
        self.assertIs(_m()._as_bool(None, False), False)

    def test_unknown_word_takes_the_default(self):
        self.assertIs(_m()._as_bool("maybe", True), True)
        self.assertIs(_m()._as_bool("maybe", False), False)

    def test_whitespace_is_tolerated(self):
        self.assertIs(_m()._as_bool("  yes  ", False), True)

    def test_it_never_raises(self):
        for raw in (None, "", 0, 1, [], {}, object()):
            _m()._as_bool(raw, False)


class CoercionListTests(unittest.TestCase):

    def test_none_is_an_empty_list(self):
        self.assertEqual(_m()._as_list(None), [])

    def test_a_real_list_is_kept(self):
        self.assertEqual(_m()._as_list(["a", "b"]), ["a", "b"])

    def test_a_tuple_becomes_a_list(self):
        self.assertEqual(_m()._as_list(("a", "b")), ["a", "b"])

    def test_comma_string_because_the_wrapped_parser_cannot_express_yaml(self):
        self.assertEqual(_m()._as_list("amsmath, graphicx"), ["amsmath", "graphicx"])

    def test_newline_separated_string(self):
        self.assertEqual(_m()._as_list("a\nb"), ["a", "b"])

    def test_blank_entries_are_dropped(self):
        self.assertEqual(_m()._as_list("a, , b"), ["a", "b"])

    def test_whitespace_only_list_items_are_dropped(self):
        self.assertEqual(_m()._as_list(["x", "  ", ""]), ["x"])

    def test_a_single_bare_word(self):
        self.assertEqual(_m()._as_list("amsmath"), ["amsmath"])

    def test_empty_string_is_empty(self):
        self.assertEqual(_m()._as_list(""), [])


class CoercionTriboolTests(unittest.TestCase):

    def test_auto_is_preserved(self):
        self.assertEqual(_m()._as_tribool("auto"), "auto")

    def test_real_true_becomes_the_string_true(self):
        self.assertEqual(_m()._as_tribool(True), "true")

    def test_real_false_becomes_the_string_false(self):
        self.assertEqual(_m()._as_tribool(False), "false")

    def test_true_words(self):
        for raw in ("true", "1", "yes", "on"):
            self.assertEqual(_m()._as_tribool(raw), "true", raw)

    def test_false_words(self):
        for raw in ("false", "0", "no", "off"):
            self.assertEqual(_m()._as_tribool(raw), "false", raw)

    def test_empty_is_the_default(self):
        self.assertEqual(_m()._as_tribool(""), "auto")

    def test_unknown_never_collapses_to_false(self):
        """A plain _as_bool would silently disable latexmk for everyone."""
        self.assertEqual(_m()._as_tribool("nonsense"), "auto")

    def test_none_is_the_default(self):
        self.assertEqual(_m()._as_tribool(None), "auto")

    def test_custom_default_is_honoured(self):
        self.assertEqual(_m()._as_tribool("", "false"), "false")


class CfgTests(unittest.TestCase):

    def test_missing_key_gives_the_default(self):
        self.assertEqual(_m()._cfg({}, "nope", "d"), "d")

    def test_present_key_wins(self):
        self.assertEqual(_m()._cfg({"k": "v"}, "k", "d"), "v")

    def test_an_explicit_None_is_treated_as_absent(self):
        """YAML writes a bare key as None; that must not become the string 'None'."""
        self.assertEqual(_m()._cfg({"k": None}, "k", "d"), "d")

    def test_default_defaults_to_empty_string(self):
        self.assertEqual(_m()._cfg({}, "nope"), "")

    def test_falsey_values_are_preserved(self):
        self.assertEqual(_m()._cfg({"k": 0}, "k", 5), 0)


# ══════════════════════════════════════════════════════════════════════
#  3. PATH SAFETY — a filename can NEVER escape output_dir
# ══════════════════════════════════════════════════════════════════════

class SafeBasenameTests(unittest.TestCase):

    def test_a_traversal_attempt_is_flattened(self):
        self.assertEqual(_m()._safe_basename("../../etc/passwd"), "passwd.pdf")

    def test_a_windows_traversal_is_flattened(self):
        self.assertEqual(_m()._safe_basename(r"..\..\windows\system32\x.pdf"), "x.pdf")

    def test_an_absolute_windows_path_keeps_only_the_leaf(self):
        self.assertEqual(_m()._safe_basename(r"C:\x\y\report.pdf"), "report.pdf")

    def test_an_absolute_posix_path_keeps_only_the_leaf(self):
        self.assertEqual(_m()._safe_basename("/etc/shadow.pdf"), "shadow.pdf")

    def test_illegal_characters_are_replaced(self):
        self.assertEqual(_m()._safe_basename("a<b>.pdf"), "a_b_.pdf")

    def test_every_reserved_character_is_neutralised(self):
        out = _m()._safe_basename('a<>:"|?*b.pdf')
        for ch in '<>:"|?*':
            self.assertNotIn(ch, out)

    def test_control_characters_are_neutralised(self):
        self.assertNotIn("\x01", _m()._safe_basename("a\x01b.pdf"))

    def test_a_missing_extension_gets_the_fallback(self):
        self.assertEqual(_m()._safe_basename("report"), "report.pdf")

    def test_the_fallback_extension_is_configurable(self):
        self.assertEqual(_m()._safe_basename("doc", ".tex"), "doc.tex")

    def test_an_existing_extension_is_respected(self):
        self.assertEqual(_m()._safe_basename("report.tex", ".pdf"), "report.tex")

    def test_a_dots_only_name_yields_nothing_rather_than_a_hidden_file(self):
        self.assertEqual(_m()._safe_basename("..."), "")

    def test_empty_and_none_are_empty(self):
        self.assertEqual(_m()._safe_basename(""), "")
        self.assertEqual(_m()._safe_basename(None), "")

    def test_whitespace_only_is_empty(self):
        self.assertEqual(_m()._safe_basename("   "), "")

    def test_the_result_never_contains_a_separator(self):
        for raw in ("../../a/b", r"..\..\a\b", "/x/y/z", "a/b/c.pdf"):
            out = _m()._safe_basename(raw)
            self.assertNotIn("/", out)
            self.assertNotIn("\\", out)


class UniquePathTests(_Temp):

    def test_a_free_name_is_returned_unchanged(self):
        target = os.path.join(self.tmp, "a.pdf")
        self.assertEqual(_m()._unique_path(target, False), target)

    def test_a_collision_becomes_underscore_2(self):
        target = self.write("a.pdf", "x")
        self.assertTrue(_m()._unique_path(target, False).endswith("a_2.pdf"))

    def test_two_collisions_become_underscore_3(self):
        target = self.write("a.pdf", "x")
        self.write("a_2.pdf", "x")
        self.assertTrue(_m()._unique_path(target, False).endswith("a_3.pdf"))

    def test_overwrite_true_clobbers_deliberately(self):
        target = self.write("a.pdf", "x")
        self.assertEqual(_m()._unique_path(target, True), target)

    def test_the_extension_is_preserved_when_disambiguating(self):
        target = self.write("a.tex", "x")
        self.assertTrue(_m()._unique_path(target, False).endswith(".tex"))

    def test_it_never_returns_an_existing_path_when_not_overwriting(self):
        target = self.write("a.pdf", "x")
        self.assertFalse(os.path.exists(_m()._unique_path(target, False)))


class TimestampNameTests(unittest.TestCase):

    def test_it_carries_the_agent_prefix(self):
        self.assertTrue(_m()._timestamped_name().startswith("latexer_"))

    def test_default_extension_is_pdf(self):
        self.assertTrue(_m()._timestamped_name().endswith(".pdf"))

    def test_the_extension_is_configurable(self):
        self.assertTrue(_m()._timestamped_name(".tex").endswith(".tex"))

    def test_the_shape_is_collision_proof_down_to_milliseconds(self):
        self.assertRegex(_m()._timestamped_name(), r"latexer_\d{8}_\d{6}_\d{3}\.pdf")


class OutputDirTests(unittest.TestCase):

    def test_an_explicit_output_dir_wins(self):
        self.assertEqual(_m()._default_output_dir({"output_dir": r"C:\x"}), r"C:\x")

    def test_the_default_lands_under_TlamatiniLaTeX(self):
        self.assertTrue(_m()._default_output_dir({}).endswith("TlamatiniLaTeX"))

    def test_a_blank_output_dir_falls_back_to_the_default(self):
        self.assertTrue(_m()._default_output_dir({"output_dir": "  "}).endswith("TlamatiniLaTeX"))

    def test_the_default_is_absolute(self):
        self.assertTrue(os.path.isabs(_m()._default_output_dir({})))


# ══════════════════════════════════════════════════════════════════════
#  4. COMMENTS AND FRAGMENTS
# ══════════════════════════════════════════════════════════════════════

class StripCommentsTests(unittest.TestCase):

    def test_a_trailing_comment_is_removed(self):
        self.assertEqual(_m()._strip_comments("a % b"), "a ")

    def test_an_ESCAPED_percent_is_NOT_a_comment(self):
        """That distinction is the entire point of hand-rolling this."""
        self.assertIn(r"\%", _m()._strip_comments(r"50\% done"))

    def test_a_whole_comment_line_becomes_empty(self):
        self.assertEqual(_m()._strip_comments("% all of it"), "")

    def test_line_count_is_preserved_so_error_line_numbers_stay_true(self):
        src = "a % x\nb\nc % y"
        self.assertEqual(len(_m()._strip_comments(src).splitlines()), 3)

    def test_a_commented_out_begin_is_invisible_to_analysis(self):
        self.assertNotIn("begin", _m()._strip_comments(r"% \begin{document}"))

    def test_text_without_comments_is_untouched(self):
        self.assertEqual(_m()._strip_comments("plain text"), "plain text")

    def test_an_escaped_backslash_before_a_percent_still_cuts(self):
        self.assertNotIn("cut", _m()._strip_comments(r"keep \\% cut"))

    def test_empty_input(self):
        self.assertEqual(_m()._strip_comments(""), "")


class FullDocumentTests(unittest.TestCase):

    def test_a_real_document_is_recognised(self):
        self.assertTrue(_m()._is_full_document(DOC))

    def test_a_bare_formula_is_not_a_document(self):
        self.assertFalse(_m()._is_full_document("$E=mc^2$"))

    def test_a_preamble_without_begin_document_is_not_a_document(self):
        self.assertFalse(_m()._is_full_document(r"\documentclass{article}"))

    def test_a_body_without_a_documentclass_is_not_a_document(self):
        self.assertFalse(_m()._is_full_document(r"\begin{document}hi\end{document}"))

    def test_a_COMMENTED_OUT_documentclass_does_not_count(self):
        src = "% \\documentclass{article}\n\\begin{document}x\\end{document}"
        self.assertFalse(_m()._is_full_document(src))

    def test_whitespace_between_begin_and_brace_is_tolerated(self):
        src = "\\documentclass{article}\\begin {document}x\\end{document}"
        self.assertTrue(_m()._is_full_document(src))


# ══════════════════════════════════════════════════════════════════════
#  5. STRUCTURE  (the get_latex_structure capability)
# ══════════════════════════════════════════════════════════════════════

class StructureTests(unittest.TestCase):

    def setUp(self):
        self.st = _m()._document_structure(DOC)

    def test_title_REGRESSION_multiline_anchor(self):
        """THE BUG THIS SUITE FOUND (2026-08-05).

        ``_one`` searched with a ``$`` anchor and no ``re.MULTILINE``, so ``$``
        only matched the end of the WHOLE file. ``\\title{...}`` lives in the
        preamble of every real document, so structure reported an EMPTY title for
        every file — silently, because "" looks like a valid answer.
        """
        self.assertEqual(self.st["title"], "The Real Title")

    def test_author_REGRESSION_multiline_anchor(self):
        self.assertEqual(self.st["author"], "Angela López Mendoza")

    def test_title_is_found_even_with_many_lines_after_it(self):
        src = DOC + "\n" * 50 + "\\end{document}\n"
        self.assertEqual(_m()._document_structure(src)["title"], "The Real Title")

    def test_a_braced_title_captures_in_full(self):
        src = "\\documentclass{article}\n\\title{A \\textbf{Bold} One}\n"
        self.assertEqual(_m()._document_structure(src)["title"], r"A \textbf{Bold} One")

    def test_documentclass_is_extracted(self):
        self.assertEqual(self.st["documentclass"], "article")

    def test_class_options_are_extracted(self):
        self.assertEqual(self.st["class_options"], "11pt,twoside")

    def test_packages_are_split_on_commas(self):
        self.assertIn("amsmath", self.st["packages"])
        self.assertIn("graphicx", self.st["packages"])

    def test_packages_with_options_are_captured(self):
        self.assertIn("inputenc", self.st["packages"])

    def test_packages_are_deduplicated(self):
        src = r"\usepackage{amsmath}\usepackage{amsmath}"
        self.assertEqual(_m()._document_structure(src)["packages"], ["amsmath"])

    def test_sections_carry_their_level(self):
        levels = [s["level"] for s in self.st["sections"]]
        self.assertIn("section", levels)
        self.assertIn("subsection", levels)

    def test_section_titles_are_captured(self):
        titles = [s["title"] for s in self.st["sections"]]
        self.assertIn("Intro", titles)

    def test_starred_sections_are_captured(self):
        src = r"\section*{Unnumbered}"
        self.assertEqual(_m()._document_structure(src)["sections"][0]["title"], "Unnumbered")

    def test_labels_are_collected(self):
        self.assertIn("sec:intro", self.st["labels"])
        self.assertIn("sec:deep", self.st["labels"])

    def test_references_are_collected_and_sorted_unique(self):
        self.assertEqual(self.st["references"], ["sec:intro"])

    def test_multi_key_citations_are_split(self):
        self.assertEqual(self.st["citations"], ["knuth1984", "lamport"])

    def test_a_commented_out_package_is_not_reported(self):
        src = "% \\usepackage{secret}\n\\usepackage{real}"
        self.assertEqual(_m()._document_structure(src)["packages"], ["real"])

    def test_an_empty_source_yields_empty_everything(self):
        st = _m()._document_structure("")
        self.assertEqual(st["packages"], [])
        self.assertEqual(st["sections"], [])
        self.assertEqual(st["title"], "")


class AnalyzeSourceTests(unittest.TestCase):

    def test_biblatex_is_detected_from_usepackage(self):
        self.assertTrue(_m()._analyze_source(r"\usepackage{biblatex}")["biblatex"])

    def test_biblatex_is_detected_from_addbibresource(self):
        self.assertTrue(_m()._analyze_source(r"\addbibresource{refs.bib}")["biblatex"])

    def test_biblatex_with_options_is_detected(self):
        src = r"\usepackage[backend=biber]{biblatex}"
        self.assertTrue(_m()._analyze_source(src)["biblatex"])

    def test_classic_bibtex_is_detected(self):
        self.assertTrue(_m()._analyze_source(r"\bibliography{refs}")["bibtex"])

    def test_bibliographystyle_alone_counts_as_bibtex(self):
        self.assertTrue(_m()._analyze_source(r"\bibliographystyle{plain}")["bibtex"])

    def test_biblatex_WINS_so_biber_is_chosen_not_bibtex(self):
        """Running the wrong bibliography tool silently produces no bibliography."""
        src = r"\usepackage{biblatex}\bibliography{refs}"
        got = _m()._analyze_source(src)
        self.assertTrue(got["biblatex"])
        self.assertFalse(got["bibtex"])

    def test_makeindex_is_detected(self):
        self.assertTrue(_m()._analyze_source(r"\makeindex")["index"])

    def test_makeglossaries_is_detected(self):
        self.assertTrue(_m()._analyze_source(r"\makeglossaries")["glossaries"])

    def test_a_plain_document_needs_no_extra_tool(self):
        got = _m()._analyze_source(DOC)
        self.assertFalse(got["biblatex"])
        self.assertFalse(got["bibtex"])
        self.assertFalse(got["index"])

    def test_a_commented_out_bibliography_is_ignored(self):
        self.assertFalse(_m()._analyze_source(r"% \bibliography{refs}")["bibtex"])

    def test_documentclass_is_reported(self):
        self.assertEqual(_m()._analyze_source(DOC)["documentclass"], "article")


# ══════════════════════════════════════════════════════════════════════
#  6. STATIC VALIDATION — works before MiKTeX is even installed
# ══════════════════════════════════════════════════════════════════════

class ValidateSourceTests(unittest.TestCase):

    def test_a_clean_document_passes(self):
        self.assertTrue(_m()._validate_source(DOC)["ok"])

    def test_a_clean_document_has_no_errors(self):
        self.assertEqual(_m()._validate_source(DOC)["errors"], [])

    def test_an_unclosed_environment_is_an_error(self):
        got = _m()._validate_source(r"\begin{itemize}\item x")
        self.assertFalse(got["ok"])
        self.assertTrue(any("never closed" in e for e in got["errors"]))

    def test_an_unclosed_environment_names_its_line(self):
        got = _m()._validate_source("\n\n\\begin{itemize}")
        self.assertTrue(any("line 3" in e for e in got["errors"]))

    def test_a_stray_end_is_an_error(self):
        got = _m()._validate_source(r"\end{itemize}")
        self.assertTrue(any("no matching" in e for e in got["errors"]))

    def test_mismatched_environment_names_are_caught(self):
        got = _m()._validate_source(r"\begin{itemize}\end{enumerate}")
        self.assertFalse(got["ok"])

    def test_the_mismatch_message_names_BOTH_environments(self):
        got = _m()._validate_source(r"\begin{itemize}\end{enumerate}")
        joined = " ".join(got["errors"])
        self.assertIn("itemize", joined)
        self.assertIn("enumerate", joined)

    def test_an_unclosed_brace_is_an_error(self):
        self.assertFalse(_m()._validate_source(r"\textbf{oops")["ok"])

    def test_an_unmatched_closing_brace_is_an_error(self):
        self.assertFalse(_m()._validate_source("x}")["ok"])

    def test_an_ESCAPED_brace_is_not_counted(self):
        src = r"\documentclass{article}\begin{document}\{\end{document}"
        self.assertTrue(_m()._validate_source(src)["ok"])

    def test_a_fragment_warns_but_is_not_an_error(self):
        got = _m()._validate_source("$E=mc^2$")
        self.assertTrue(got["ok"])
        self.assertTrue(any("fragment" in w for w in got["warnings"]))

    def test_a_dangling_reference_is_a_WARNING_not_an_error(self):
        """A \\ref can legitimately point into another file of the project."""
        got = _m()._validate_source(r"\ref{nowhere}")
        self.assertTrue(got["ok"])
        self.assertTrue(any("nowhere" in w for w in got["warnings"]))

    def test_a_resolved_reference_produces_no_warning(self):
        got = _m()._validate_source(r"\label{a}\ref{a}")
        self.assertFalse(any("has no matching" in w for w in got["warnings"]))

    def test_a_duplicate_label_is_a_warning(self):
        got = _m()._validate_source(r"\label{a}\label{a}")
        self.assertTrue(any("duplicate" in w for w in got["warnings"]))

    def test_comments_never_trip_the_validator(self):
        self.assertTrue(_m()._validate_source("% \\begin{itemize}\n" + DOC)["ok"])

    def test_an_empty_source_is_a_fragment_not_a_crash(self):
        got = _m()._validate_source("")
        self.assertTrue(got["ok"])
        self.assertTrue(got["warnings"])

    def test_the_result_always_carries_all_three_keys(self):
        for src in ("", DOC, r"\begin{x}"):
            got = _m()._validate_source(src)
            self.assertIn("ok", got)
            self.assertIn("errors", got)
            self.assertIn("warnings", got)


# ══════════════════════════════════════════════════════════════════════
#  7. LOG PARSING — 3000 lines of noise into one answer
# ══════════════════════════════════════════════════════════════════════

LOG_OK = (
    "This is pdfTeX, Version 3.14\n"
    "(./doc.tex\n"
    "Output written on doc.pdf (3 pages, 145678 bytes).\n"
)


class LogParsingTests(unittest.TestCase):

    def test_file_line_error_format_is_extracted(self):
        got = _m()._parse_latex_log("doc.tex:12: Undefined control sequence.")
        self.assertTrue(any("doc.tex:12" in e for e in got["errors"]))

    def test_the_error_path_is_reduced_to_a_basename(self):
        got = _m()._parse_latex_log(r"C:\long\path\doc.tex:12: Boom.")
        self.assertTrue(any(e.startswith("doc.tex:12") for e in got["errors"]))

    def test_bang_style_errors_are_extracted(self):
        got = _m()._parse_latex_log("! Undefined control sequence.")
        self.assertTrue(got["errors"])

    def test_a_bang_error_absorbs_its_l_dot_context_line(self):
        got = _m()._parse_latex_log("! Undefined control sequence.\nl.13 \\boxed")
        self.assertTrue(any("l.13" in e for e in got["errors"]))

    def test_a_missing_STY_is_reported_as_a_missing_PACKAGE(self):
        got = _m()._parse_latex_log("! LaTeX Error: File `biblatex.sty' not found.")
        self.assertIn("biblatex.sty", got["missing_packages"])

    def test_a_missing_CLS_is_a_missing_package(self):
        got = _m()._parse_latex_log("! LaTeX Error: File `beamer.cls' not found.")
        self.assertIn("beamer.cls", got["missing_packages"])

    def test_a_missing_DATA_file_is_NOT_reported_as_a_package(self):
        """The two need different advice, so they must never be conflated."""
        got = _m()._parse_latex_log("! LaTeX Error: File `logo.png' not found.")
        self.assertEqual(got["missing_packages"], [])
        self.assertIn("logo.png", got["missing_files"])

    def test_missing_package_extraction_survives_the_file_line_error_prefix(self):
        """It must run BEFORE the error branches `continue`, or it never runs."""
        got = _m()._parse_latex_log("doc.tex:5: LaTeX Error: File `xcolor.sty' not found.")
        self.assertIn("xcolor.sty", got["missing_packages"])

    def test_rerun_markers_drive_the_convergence_loop(self):
        for marker in ("Rerun to get cross-references right.",
                       "Label(s) may have changed.",
                       "Please rerun LaTeX."):
            self.assertTrue(_m()._parse_latex_log(marker)["needs_rerun"], marker)

    def test_a_settled_log_does_not_ask_for_a_rerun(self):
        self.assertFalse(_m()._parse_latex_log(LOG_OK)["needs_rerun"])

    def test_page_count_and_bytes_are_read(self):
        got = _m()._parse_latex_log(LOG_OK)
        self.assertEqual(got["pages"], 3)
        self.assertEqual(got["output_bytes"], 145678)

    def test_the_output_filename_is_read(self):
        self.assertEqual(_m()._parse_latex_log(LOG_OK)["output_file"], "doc.pdf")

    def test_a_page_count_without_a_byte_count_still_parses(self):
        got = _m()._parse_latex_log("Output written on doc.pdf (7 pages).")
        self.assertEqual(got["pages"], 7)

    def test_warnings_are_collected(self):
        got = _m()._parse_latex_log("LaTeX Warning: Citation `x' undefined.")
        self.assertTrue(got["warnings"])

    def test_package_warnings_are_collected(self):
        got = _m()._parse_latex_log("Package hyperref Warning: Token not allowed.")
        self.assertTrue(got["warnings"])

    def test_warnings_are_deduplicated(self):
        line = "LaTeX Warning: Citation `x' undefined."
        self.assertEqual(len(_m()._parse_latex_log(line + "\n" + line)["warnings"]), 1)

    def test_boxes_are_counted(self):
        log = "Overfull \\hbox (1pt too wide)\nUnderfull \\vbox (badness 10000)"
        self.assertEqual(_m()._parse_latex_log(log)["boxes"], 2)

    def test_boxes_are_NEVER_errors(self):
        got = _m()._parse_latex_log("Overfull \\hbox (1pt too wide)")
        self.assertEqual(got["errors"], [])

    def test_errors_are_deduplicated(self):
        line = "doc.tex:9: Boom."
        self.assertEqual(len(_m()._parse_latex_log(line + "\n" + line)["errors"]), 1)

    def test_an_empty_log_parses_to_a_clean_report(self):
        got = _m()._parse_latex_log("")
        self.assertEqual(got["errors"], [])
        self.assertEqual(got["pages"], 0)

    def test_the_report_always_carries_every_key(self):
        got = _m()._parse_latex_log("")
        for key in ("errors", "warnings", "missing_packages", "missing_files",
                    "boxes", "pages", "output_file", "output_bytes", "needs_rerun"):
            self.assertIn(key, got)


class DiagnosticsFormatTests(unittest.TestCase):

    def _diag(self, **over):
        base = {"errors": [], "warnings": [], "missing_packages": [],
                "missing_files": [], "boxes": 0, "pages": 0,
                "output_file": "", "output_bytes": 0, "needs_rerun": False}
        base.update(over)
        return base

    def test_errors_are_listed_with_a_count(self):
        out = _m()._format_diagnostics(self._diag(errors=["a", "b"]), "miktex", True, 0)
        self.assertIn("ERRORS (2)", out)

    def test_miktex_is_told_it_can_self_install(self):
        out = _m()._format_diagnostics(
            self._diag(missing_packages=["x.sty"]), "miktex", True, 0)
        self.assertIn("MiKTeX can install these automatically", out)

    def test_another_distribution_is_pointed_at_miktex(self):
        out = _m()._format_diagnostics(
            self._diag(missing_packages=["x.sty"]), "texlive", True, 0)
        self.assertIn("miktex.org", out)

    def test_boxes_are_explicitly_called_cosmetic(self):
        out = _m()._format_diagnostics(self._diag(boxes=4), "miktex", True, 0)
        self.assertIn("cosmetic", out)

    def test_the_report_can_be_truncated(self):
        out = _m()._format_diagnostics(
            self._diag(errors=["x" * 500]), "miktex", True, 100)
        self.assertIn("truncated", out)

    def test_a_zero_limit_means_no_truncation(self):
        out = _m()._format_diagnostics(
            self._diag(errors=["x" * 500]), "miktex", True, 0)
        self.assertNotIn("truncated", out)

    def test_a_clean_build_produces_an_empty_report(self):
        self.assertEqual(_m()._format_diagnostics(self._diag(), "miktex", True, 0), "")


# ══════════════════════════════════════════════════════════════════════
#  8. TEMPLATES AND DOCUMENT ASSEMBLY
# ══════════════════════════════════════════════════════════════════════

class TemplateRenderTests(unittest.TestCase):

    def test_all_eight_templates_exist(self):
        self.assertEqual(sorted(_m()._TEMPLATES), [
            "article", "beamer", "book", "cv", "homework", "letter",
            "report", "spanish-article"])

    def test_every_template_renders_without_a_leftover_token(self):
        for name in _m()._TEMPLATES:
            out = _m()._render_template(name, {"title": "T", "author": "A"})
            self.assertNotIn("%%", out, name)

    def test_every_template_is_a_full_document(self):
        for name in _m()._TEMPLATES:
            self.assertTrue(_m()._is_full_document(_m()._render_template(name, {})), name)

    def test_every_template_passes_our_own_validator(self):
        for name in _m()._TEMPLATES:
            got = _m()._validate_source(_m()._render_template(name, {}))
            self.assertTrue(got["ok"], "%s: %s" % (name, got["errors"]))

    def test_an_unknown_template_falls_back_to_article(self):
        self.assertIn("article", _m()._render_template("nope", {}))

    def test_the_title_is_substituted(self):
        self.assertIn("My Paper", _m()._render_template("article", {"title": "My Paper"}))

    def test_a_missing_title_gets_a_placeholder_not_a_blank(self):
        self.assertIn("Untitled Document", _m()._render_template("article", {}))

    def test_a_missing_author_defaults_to_Tlamatini(self):
        self.assertIn("Tlamatini", _m()._render_template("article", {}))

    def test_the_spanish_template_always_carries_babel(self):
        self.assertIn("babel", _m()._render_template("spanish-article", {}))

    def test_a_spanish_language_adds_babel_to_any_template(self):
        self.assertIn("babel", _m()._render_template("article", {"document_language": "es"}))

    def test_english_needs_no_babel_package(self):
        self.assertNotIn("babel", _m()._render_template("article", {"document_language": "en"}))

    def test_template_names_are_case_insensitive(self):
        self.assertIn("babel", _m()._render_template("SPANISH-ARTICLE", {}))


class BabelTests(unittest.TestCase):

    def test_spanish_gets_babel(self):
        self.assertIn("babel", _m()._babel_line("es"))

    def test_a_full_locale_code_still_matches(self):
        self.assertIn("babel", _m()._babel_line("es-MX"))

    def test_english_gets_nothing(self):
        self.assertEqual(_m()._babel_line("en"), "")

    def test_an_empty_language_gets_nothing(self):
        self.assertEqual(_m()._babel_line(""), "")

    def test_none_is_safe(self):
        self.assertEqual(_m()._babel_line(None), "")

    def test_mexican_spanish_is_the_configured_variant(self):
        self.assertIn("mexico", _m()._babel_line("es"))


class DeclaredPackagesTests(unittest.TestCase):

    def test_a_simple_usepackage_is_found(self):
        self.assertIn("amsmath", _m()._declared_packages(r"\usepackage{amsmath}"))

    def test_a_package_with_options_is_found(self):
        self.assertIn("geometry", _m()._declared_packages(r"\usepackage[a=b]{geometry}"))

    def test_a_comma_list_is_split(self):
        got = _m()._declared_packages(r"\usepackage{amsmath,amssymb}")
        self.assertIn("amsmath", got)
        self.assertIn("amssymb", got)

    def test_results_are_lowercased(self):
        self.assertIn("amsmath", _m()._declared_packages(r"\usepackage{AmsMath}"))

    def test_several_sources_are_merged(self):
        got = _m()._declared_packages(r"\usepackage{a}", r"\usepackage{b}")
        self.assertEqual(got, {"a", "b"})

    def test_none_and_empty_are_safe(self):
        self.assertEqual(_m()._declared_packages(None, ""), set())


class BuildDocumentTests(unittest.TestCase):

    def test_the_result_is_a_full_document(self):
        self.assertTrue(_m()._is_full_document(_m()._build_document({})))

    def test_the_result_passes_our_own_validator(self):
        self.assertTrue(_m()._validate_source(_m()._build_document({}))["ok"])

    def test_the_documentclass_is_configurable(self):
        self.assertIn(r"\documentclass{report}",
                      _m()._build_document({"documentclass": "report"}))

    def test_class_options_are_emitted(self):
        self.assertIn("[12pt]", _m()._build_document({"class_options": "12pt"}))

    def test_geometry_has_a_sane_default(self):
        self.assertIn("margin=2.5cm", _m()._build_document({}))

    def test_geometry_is_configurable(self):
        self.assertIn("margin=1in", _m()._build_document({"geometry": "margin=1in"}))

    def test_a_blank_geometry_omits_the_package(self):
        self.assertNotIn("geometry", _m()._build_document({"geometry": ""}))

    def test_amsmath_is_ALWAYS_present_REGRESSION(self):
        """Without it a fragment using \\eqref or align dies AFTER a PDF was
        already written — a silently mis-typeset document."""
        self.assertIn("amsmath", _m()._build_document({}))

    def test_amssymb_and_graphicx_are_always_present(self):
        out = _m()._build_document({})
        self.assertIn("amssymb", out)
        self.assertIn("graphicx", out)

    def test_requested_packages_are_added(self):
        self.assertIn(r"\usepackage{tikz}", _m()._build_document({"packages": "tikz"}))

    def test_a_comma_string_of_packages_works(self):
        out = _m()._build_document({"packages": "tikz, xcolor"})
        self.assertIn("tikz", out)
        self.assertIn("xcolor", out)

    def test_a_package_is_NEVER_loaded_twice(self):
        """A duplicate \\usepackage with different options is a hard Option clash."""
        out = _m()._build_document({"packages": "amsmath"})
        self.assertEqual(out.count(r"\usepackage{amsmath}"), 1)

    def test_a_package_the_user_wrote_in_content_is_not_re_added(self):
        out = _m()._build_document({"content": r"\usepackage{graphicx}"})
        self.assertEqual(out.count(r"\usepackage{graphicx}"), 1)

    def test_hyperref_is_loaded_LAST_because_it_patches_other_packages(self):
        out = _m()._build_document({"packages": "tikz"})
        self.assertGreater(out.index("hyperref"), out.index("tikz"))

    def test_hyperref_is_not_added_when_the_user_already_asked_for_it(self):
        out = _m()._build_document({"packages": "hyperref"})
        self.assertEqual(out.count("hyperref"), 1)

    def test_a_title_produces_maketitle(self):
        self.assertIn(r"\maketitle", _m()._build_document({"title": "T"}))

    def test_no_title_means_no_maketitle(self):
        self.assertNotIn(r"\maketitle", _m()._build_document({}))

    def test_the_author_defaults_when_a_title_is_given(self):
        self.assertIn("Tlamatini", _m()._build_document({"title": "T"}))

    def test_the_date_defaults_to_today(self):
        self.assertIn(r"\today", _m()._build_document({"title": "T"}))

    def test_content_is_placed_in_the_body(self):
        out = _m()._build_document({"content": "Hello Angela"})
        self.assertIn("Hello Angela", out)
        self.assertGreater(out.index("Hello Angela"), out.index(r"\begin{document}"))

    def test_empty_content_gets_a_placeholder_so_the_pdf_is_never_blank(self):
        self.assertIn("Replace this text", _m()._build_document({}))

    def test_spanish_adds_babel(self):
        self.assertIn("babel", _m()._build_document({"document_language": "es"}))


class WrapFragmentTests(unittest.TestCase):

    def test_a_bare_formula_becomes_a_real_document(self):
        out = _m()._wrap_fragment("$E=mc^2$", {})
        self.assertTrue(_m()._is_full_document(out))

    def test_the_fragment_survives_verbatim(self):
        self.assertIn("$E=mc^2$", _m()._wrap_fragment("$E=mc^2$", {}))

    def test_the_wrapped_document_validates(self):
        self.assertTrue(_m()._validate_source(_m()._wrap_fragment("$x$", {}))["ok"])

    def test_no_title_is_invented_when_none_was_given(self):
        self.assertNotIn(r"\maketitle", _m()._wrap_fragment("$x$", {}))

    def test_an_explicit_title_is_honoured(self):
        self.assertIn(r"\maketitle", _m()._wrap_fragment("$x$", {"title": "T"}))

    def test_amsmath_is_present_so_align_and_eqref_work(self):
        self.assertIn("amsmath", _m()._wrap_fragment(r"\begin{align}a&=b\end{align}", {}))


# ══════════════════════════════════════════════════════════════════════
#  9. COMMAND LINES
# ══════════════════════════════════════════════════════════════════════

class EngineArgvTests(unittest.TestCase):

    def test_nonstopmode_is_NON_NEGOTIABLE(self):
        """Without it LaTeX waits for keyboard input forever — a hung agent."""
        argv = _m()._engine_argv(_tools(), {}, "doc.tex")
        self.assertIn("-interaction=nonstopmode", argv)

    def test_file_line_error_is_always_present(self):
        argv = _m()._engine_argv(_tools(), {}, "doc.tex")
        self.assertIn("-file-line-error", argv)

    def test_the_engine_binary_comes_first(self):
        argv = _m()._engine_argv(_tools(latex="X.exe"), {}, "doc.tex")
        self.assertEqual(argv[0], "X.exe")

    def test_the_tex_file_comes_last(self):
        argv = _m()._engine_argv(_tools(), {}, "doc.tex")
        self.assertEqual(argv[-1], "doc.tex")

    def test_miktex_gets_the_on_demand_installer(self):
        argv = _m()._engine_argv(_tools(distribution="miktex"), {}, "d.tex")
        self.assertIn("--enable-installer", argv)

    def test_the_installer_flag_is_MIKTEX_ONLY(self):
        argv = _m()._engine_argv(_tools(distribution="texlive"), {}, "d.tex")
        self.assertNotIn("--enable-installer", argv)

    def test_the_installer_can_be_switched_off(self):
        argv = _m()._engine_argv(_tools(), {"auto_install_packages": False}, "d.tex")
        self.assertNotIn("--enable-installer", argv)

    def test_shell_escape_is_ABSENT_by_default(self):
        """\\write18 is arbitrary command execution — it must be opt-in."""
        self.assertNotIn("-shell-escape", _m()._engine_argv(_tools(), {}, "d.tex"))

    def test_shell_escape_is_opt_in(self):
        argv = _m()._engine_argv(_tools(), {"shell_escape": True}, "d.tex")
        self.assertIn("-shell-escape", argv)

    def test_a_string_true_also_enables_shell_escape(self):
        argv = _m()._engine_argv(_tools(), {"shell_escape": "true"}, "d.tex")
        self.assertIn("-shell-escape", argv)


class LatexmkArgvTests(unittest.TestCase):

    def test_pdflatex_maps_to_pdf(self):
        argv = _m()._latexmk_argv(_tools(engine="pdflatex", latexmk="lmk"), {}, "d.tex")
        self.assertIn("-pdf", argv)

    def test_xelatex_maps_to_pdfxe(self):
        argv = _m()._latexmk_argv(_tools(engine="xelatex", latexmk="lmk"), {}, "d.tex")
        self.assertIn("-pdfxe", argv)

    def test_lualatex_maps_to_pdflua(self):
        argv = _m()._latexmk_argv(_tools(engine="lualatex", latexmk="lmk"), {}, "d.tex")
        self.assertIn("-pdflua", argv)

    def test_nonstopmode_is_present_here_too(self):
        argv = _m()._latexmk_argv(_tools(latexmk="lmk"), {}, "d.tex")
        self.assertIn("-interaction=nonstopmode", argv)

    def test_halt_on_error_is_present(self):
        argv = _m()._latexmk_argv(_tools(latexmk="lmk"), {}, "d.tex")
        self.assertIn("-halt-on-error", argv)

    def test_shell_escape_is_opt_in_here_too(self):
        argv = _m()._latexmk_argv(_tools(latexmk="lmk"), {}, "d.tex")
        self.assertNotIn("-shell-escape", argv)


# ══════════════════════════════════════════════════════════════════════
#  10. PROJECT DISCOVERY
# ══════════════════════════════════════════════════════════════════════

MASTER = "\\documentclass{article}\n\\begin{document}\n\\input{child}\n\\end{document}\n"
CHILD = "Just a child, no preamble.\n"


class FindMainTexTests(_Temp):

    def test_the_only_master_is_found(self):
        self.write("main.tex", MASTER)
        path, note = _m()._find_main_tex(self.tmp, "", False)
        self.assertTrue(path.endswith("main.tex"))
        self.assertIn("auto-detected", note)

    def test_a_child_without_a_preamble_is_NEVER_chosen(self):
        self.write("main.tex", MASTER)
        self.write("child.tex", CHILD)
        path, _ = _m()._find_main_tex(self.tmp, "", False)
        self.assertTrue(path.endswith("main.tex"))

    def test_an_explicit_main_file_wins(self):
        self.write("main.tex", MASTER)
        other = self.write("other.tex", MASTER)
        path, note = _m()._find_main_tex(self.tmp, "other.tex", False)
        self.assertEqual(path, other)
        self.assertIn("explicitly", note)

    def test_an_explicit_name_may_omit_the_extension(self):
        self.write("paper.tex", MASTER)
        path, _ = _m()._find_main_tex(self.tmp, "paper", False)
        self.assertTrue(path.endswith("paper.tex"))

    def test_a_missing_explicit_file_is_reported_not_guessed_around(self):
        self.write("main.tex", MASTER)
        path, note = _m()._find_main_tex(self.tmp, "nope.tex", False)
        self.assertEqual(path, "")
        self.assertIn("does not exist", note)

    def test_an_empty_folder_is_reported(self):
        path, note = _m()._find_main_tex(self.tmp, "", False)
        self.assertEqual(path, "")
        self.assertIn("no .tex files", note)

    def test_a_folder_with_no_master_explains_itself(self):
        self.write("a.tex", CHILD)
        path, note = _m()._find_main_tex(self.tmp, "", False)
        self.assertEqual(path, "")
        self.assertIn("documentclass", note)

    def test_a_conventional_name_breaks_a_tie(self):
        self.write("zzz.tex", MASTER)
        self.write("main.tex", MASTER)
        path, note = _m()._find_main_tex(self.tmp, "", False)
        self.assertTrue(path.endswith("main.tex"))
        self.assertIn("conventional", note)

    def test_recursive_search_finds_a_nested_master(self):
        self.write(os.path.join("sub", "deep.tex"), MASTER)
        path, _ = _m()._find_main_tex(self.tmp, "", True)
        self.assertTrue(path.endswith("deep.tex"))

    def test_a_non_recursive_search_ignores_subfolders(self):
        self.write(os.path.join("sub", "deep.tex"), MASTER)
        path, _ = _m()._find_main_tex(self.tmp, "", False)
        self.assertEqual(path, "")


class CollectChildrenTests(_Temp):

    def test_an_input_child_is_resolved(self):
        main = self.write("main.tex", MASTER)
        self.write("child.tex", CHILD)
        self.assertEqual(len(_m()._collect_children(main)), 1)

    def test_include_is_resolved_too(self):
        main = self.write("m.tex", r"\include{c}")
        self.write("c.tex", CHILD)
        self.assertEqual(len(_m()._collect_children(main)), 1)

    def test_a_missing_child_is_silently_skipped(self):
        main = self.write("m.tex", r"\input{ghost}")
        self.assertEqual(_m()._collect_children(main), [])

    def test_a_commented_out_input_is_ignored(self):
        main = self.write("m.tex", "% \\input{child}")
        self.write("child.tex", CHILD)
        self.assertEqual(_m()._collect_children(main), [])

    def test_children_are_deduplicated(self):
        main = self.write("m.tex", r"\input{c}\input{c}")
        self.write("c.tex", CHILD)
        self.assertEqual(len(_m()._collect_children(main)), 1)

    def test_a_missing_main_file_never_raises(self):
        self.assertEqual(_m()._collect_children(os.path.join(self.tmp, "no.tex")), [])


# ══════════════════════════════════════════════════════════════════════
#  11. CLEAN — removes aux, NEVER a .tex/.bib/.pdf
# ══════════════════════════════════════════════════════════════════════

class CleanAuxTests(_Temp):

    def _litter(self):
        for name in ("doc.tex", "doc.pdf", "refs.bib", "doc.aux", "doc.log",
                     "doc.toc", "doc.out", "doc.bbl", "doc.synctex.gz"):
            self.write(name, "x")

    def test_aux_files_are_removed(self):
        self._litter()
        _m()._clean_aux(self.tmp)
        self.assertFalse(os.path.exists(os.path.join(self.tmp, "doc.aux")))

    def test_the_TEX_is_never_touched(self):
        self._litter()
        _m()._clean_aux(self.tmp)
        self.assertTrue(os.path.exists(os.path.join(self.tmp, "doc.tex")))

    def test_the_PDF_is_never_touched(self):
        self._litter()
        _m()._clean_aux(self.tmp)
        self.assertTrue(os.path.exists(os.path.join(self.tmp, "doc.pdf")))

    def test_the_BIB_is_never_touched(self):
        self._litter()
        _m()._clean_aux(self.tmp)
        self.assertTrue(os.path.exists(os.path.join(self.tmp, "refs.bib")))

    def test_a_compound_extension_is_handled(self):
        self._litter()
        _m()._clean_aux(self.tmp)
        self.assertFalse(os.path.exists(os.path.join(self.tmp, "doc.synctex.gz")))

    def test_the_removed_list_is_returned(self):
        self._litter()
        self.assertIn("doc.aux", _m()._clean_aux(self.tmp))

    def test_keep_log_preserves_the_log_for_debugging(self):
        self._litter()
        _m()._clean_aux(self.tmp, keep_log=True)
        self.assertTrue(os.path.exists(os.path.join(self.tmp, "doc.log")))

    def test_a_jobname_scopes_the_cleanup(self):
        self._litter()
        self.write("other.aux", "x")
        _m()._clean_aux(self.tmp, jobname="doc")
        self.assertTrue(os.path.exists(os.path.join(self.tmp, "other.aux")))

    def test_a_missing_directory_is_a_no_op_not_a_crash(self):
        self.assertEqual(_m()._clean_aux(os.path.join(self.tmp, "ghost")), [])

    def test_an_empty_directory_returns_nothing(self):
        self.assertEqual(_m()._clean_aux(self.tmp), [])


# ══════════════════════════════════════════════════════════════════════
#  12. PREFLIGHT — REFUSE rather than mis-typeset
# ══════════════════════════════════════════════════════════════════════

class PreflightTests(_Temp):

    def test_an_unknown_action_is_refused(self):
        pf = _m()._preflight("fly_me_to_the_moon", {}, _tools())
        self.assertFalse(pf["ok"])
        self.assertTrue(any("Unknown action" in f for f in pf["fatals"]))

    def test_the_refusal_lists_the_valid_actions(self):
        pf = _m()._preflight("nope", {}, _tools())
        self.assertIn("compile", " ".join(pf["fatals"]))

    def test_validate_never_needs_an_engine(self):
        self.assertTrue(_m()._preflight("validate", {}, _tools(latex=""))["ok"])

    def test_install_never_needs_an_engine(self):
        self.assertTrue(_m()._preflight("install", {}, _tools(latex=""))["ok"])

    def test_compiling_without_an_engine_is_refused(self):
        pf = _m()._preflight("compile", {"input_text": "x"}, _tools(latex=""))
        self.assertFalse(pf["ok"])

    def test_the_missing_engine_refusal_names_MiKTeX(self):
        """distribution='none' is the ONLY realistic pairing with latex=''.

        The first draft of this test passed distribution='miktex' alongside an
        empty engine — a state that can never exist, because the distribution is
        identified BY RUNNING the engine (``_identify_distribution('')`` returns
        'none'). The suite went red, the product was right, and the fixture was
        the lie. Pinned by ``MiktexHintTests`` below.
        """
        pf = _m()._preflight("compile", {"input_text": "x"},
                             _tools(latex="", distribution="none"))
        self.assertFalse(pf["ok"])
        self.assertIn("MiKTeX", " ".join(pf["fatals"]))

    def test_the_missing_engine_refusal_offers_the_install_action(self):
        pf = _m()._preflight("compile", {"input_text": "x"},
                             _tools(latex="", distribution="none"))
        self.assertIn("install", " ".join(pf["fatals"]))

    def test_compiling_nothing_at_all_is_refused(self):
        pf = _m()._preflight("compile", {}, _tools())
        self.assertFalse(pf["ok"])
        self.assertIn("Refusing to compile nothing", " ".join(pf["fatals"]))

    def test_a_nonexistent_tex_path_is_refused(self):
        pf = _m()._preflight("compile", {"tex_path": os.path.join(self.tmp, "no.tex")},
                             _tools())
        self.assertFalse(pf["ok"])

    def test_raw_input_text_alone_is_enough_to_compile(self):
        pf = _m()._preflight("compile", {"input_text": "$x$",
                                         "output_dir": self.tmp}, _tools())
        self.assertTrue(pf["ok"], pf["fatals"])

    def test_texlive_is_ALLOWED_but_warned_about(self):
        pf = _m()._preflight("compile", {"input_text": "x", "output_dir": self.tmp},
                             _tools(distribution="texlive"))
        self.assertTrue(pf["ok"])
        self.assertTrue(pf["warnings"])

    def test_shell_escape_raises_a_security_warning(self):
        pf = _m()._preflight("compile", {"input_text": "x", "shell_escape": True,
                                         "output_dir": self.tmp}, _tools())
        self.assertTrue(any("write18" in w for w in pf["warnings"]))

    def test_shell_escape_is_a_warning_NOT_a_refusal(self):
        pf = _m()._preflight("compile", {"input_text": "x", "shell_escape": True,
                                         "output_dir": self.tmp}, _tools())
        self.assertTrue(pf["ok"])

    def test_demanding_latexmk_without_perl_is_refused_and_explains_perl(self):
        pf = _m()._preflight("compile",
                             {"input_text": "x", "use_latexmk": True,
                              "output_dir": self.tmp},
                             _tools(latexmk="latexmk.exe", latexmk_usable=False))
        self.assertFalse(pf["ok"])
        self.assertIn("Perl", " ".join(pf["fatals"]))

    def test_demanding_an_absent_latexmk_is_refused(self):
        pf = _m()._preflight("compile",
                             {"input_text": "x", "use_latexmk": True,
                              "output_dir": self.tmp},
                             _tools(latexmk="", latexmk_usable=False))
        self.assertFalse(pf["ok"])

    def test_auto_latexmk_never_refuses(self):
        pf = _m()._preflight("compile",
                             {"input_text": "x", "use_latexmk": "auto",
                              "output_dir": self.tmp}, _tools())
        self.assertTrue(pf["ok"], pf["fatals"])

    def test_read_file_needs_a_source(self):
        self.assertFalse(_m()._preflight("read_file", {}, _tools())["ok"])

    def test_structure_accepts_input_text_instead_of_a_path(self):
        self.assertTrue(_m()._preflight("structure", {"input_text": "x"}, _tools())["ok"])

    def test_validate_tex_on_a_missing_file_is_refused(self):
        pf = _m()._preflight("validate_tex",
                             {"tex_path": os.path.join(self.tmp, "no.tex")}, _tools())
        self.assertFalse(pf["ok"])

    def test_edit_file_needs_a_tex_path(self):
        self.assertFalse(_m()._preflight("edit_file", {}, _tools())["ok"])

    def test_edit_file_rejects_an_unknown_mode(self):
        path = self.write("a.tex", "x")
        pf = _m()._preflight("edit_file", {"tex_path": path, "edit_mode": "teleport"},
                             _tools())
        self.assertFalse(pf["ok"])

    def test_replace_mode_needs_an_anchor(self):
        path = self.write("a.tex", "x")
        pf = _m()._preflight("edit_file", {"tex_path": path, "edit_mode": "replace"},
                             _tools())
        self.assertTrue(any("find_text" in f for f in pf["fatals"]))

    def test_append_mode_needs_text_to_add(self):
        path = self.write("a.tex", "x")
        pf = _m()._preflight("edit_file", {"tex_path": path, "edit_mode": "append"},
                             _tools())
        self.assertTrue(any("replace_text" in f for f in pf["fatals"]))

    def test_a_valid_edit_passes(self):
        path = self.write("a.tex", "hello")
        pf = _m()._preflight("edit_file",
                             {"tex_path": path, "edit_mode": "replace",
                              "find_text": "hello", "replace_text": "bye"}, _tools())
        self.assertTrue(pf["ok"], pf["fatals"])

    def test_compile_project_needs_a_directory(self):
        self.assertFalse(_m()._preflight("compile_project", {}, _tools())["ok"])

    def test_compile_project_rejects_a_file_posing_as_a_directory(self):
        path = self.write("a.tex", "x")
        pf = _m()._preflight("compile_project", {"project_dir": path}, _tools())
        self.assertFalse(pf["ok"])

    def test_an_unknown_template_is_refused(self):
        pf = _m()._preflight("create_from_template", {"template": "novel"}, _tools())
        self.assertFalse(pf["ok"])

    def test_every_shipped_template_is_accepted(self):
        for name in _m()._TEMPLATES:
            pf = _m()._preflight("create_from_template", {"template": name}, _tools())
            self.assertTrue(pf["ok"], name)

    def test_clean_without_a_directory_is_refused_rather_than_guessing(self):
        self.assertFalse(_m()._preflight("clean", {}, _tools())["ok"])

    def test_the_report_is_never_empty(self):
        pf = _m()._preflight("nope", {}, _tools())
        self.assertTrue(_m()._format_preflight_report(pf).strip())

    def test_the_report_says_so_when_there_is_nothing_to_report(self):
        pf = {"ok": True, "fatals": [], "warnings": []}
        self.assertIn("no findings", _m()._format_preflight_report(pf))

    def test_every_result_carries_all_three_keys(self):
        for action in ("validate", "compile", "nope"):
            pf = _m()._preflight(action, {}, _tools())
            self.assertIn("ok", pf)
            self.assertIn("fatals", pf)
            self.assertIn("warnings", pf)


# ══════════════════════════════════════════════════════════════════════
#  12b. THE MiKTeX HINT — the sentence every refusal ends with
# ══════════════════════════════════════════════════════════════════════

class MiktexHintTests(unittest.TestCase):
    """Pins the invariant that made the suite's own fixture wrong once.

    The distribution is identified BY RUNNING the engine, so "no engine" always
    means distribution 'none'. A test that pairs latex='' with 'miktex' is
    testing a state the product can never reach.
    """

    def test_no_engine_ALWAYS_means_distribution_none(self):
        self.assertEqual(_m()._identify_distribution("", {})[0], "none")

    def test_no_engine_reports_an_empty_version_line(self):
        self.assertEqual(_m()._identify_distribution("", {})[1], "")

    def test_none_gets_the_full_install_MiKTeX_message(self):
        hint = _m()._miktex_hint("none")
        self.assertIn("MiKTeX", hint)
        self.assertIn("miktex.org", hint)

    def test_the_none_hint_explains_why_tlamatini_bundles_no_tex(self):
        """Several GB — the release must stay under GitHub's 2 GiB limit."""
        self.assertIn("several GB", _m()._miktex_hint("none"))

    def test_the_none_hint_points_at_the_install_action(self):
        self.assertIn("install", _m()._miktex_hint("none"))

    def test_miktex_itself_needs_NO_hint(self):
        """Nagging a user who already has the recommended distribution is noise."""
        self.assertEqual(_m()._miktex_hint("miktex"), "")

    def test_texlive_is_warned_it_cannot_self_install(self):
        hint = _m()._miktex_hint("texlive")
        self.assertIn("CANNOT install", hint)

    def test_mactex_gets_the_same_warning(self):
        self.assertIn("CANNOT install", _m()._miktex_hint("mactex"))

    def test_an_unknown_distribution_is_warned_but_not_rejected(self):
        self.assertIn("CANNOT install", _m()._miktex_hint("unknown"))

    def test_every_hint_that_is_not_empty_mentions_miktex(self):
        for dist in ("none", "texlive", "mactex", "unknown", "weird"):
            hint = _m()._miktex_hint(dist)
            if hint:
                self.assertIn("MiKTeX", hint, dist)


# ══════════════════════════════════════════════════════════════════════
#  13. STRUCTURED OUTPUT (the Parametrizer contract)
# ══════════════════════════════════════════════════════════════════════

class EmitSectionTests(unittest.TestCase):

    def _emit(self, fields, body):
        stream = io.StringIO()
        handler = logging.StreamHandler(stream)
        root = logging.getLogger()
        saved, saved_level = list(root.handlers), root.level
        root.handlers[:] = [handler]
        root.setLevel(logging.INFO)
        try:
            _m()._emit_section(fields, body)
        finally:
            root.handlers[:] = saved
            root.setLevel(saved_level)
        return stream.getvalue()

    def test_the_section_is_emitted(self):
        out = self._emit({"action": "compile"}, "body")
        self.assertIn("INI_SECTION_LATEXER<<<", out)

    def test_the_section_is_closed(self):
        out = self._emit({"action": "compile"}, "body")
        self.assertIn(">>>END_SECTION_LATEXER", out)

    def test_it_is_ONE_atomic_record(self):
        """Two logging calls could interleave with another thread and corrupt it."""
        out = self._emit({"action": "compile"}, "body")
        self.assertEqual(out.count("INI_SECTION_LATEXER<<<"), 1)

    def test_the_kv_header_is_emitted(self):
        out = self._emit({"action": "compile", "status": "compiled"}, "body")
        self.assertIn("action: compile", out)
        self.assertIn("status: compiled", out)

    def test_the_body_is_separated_by_a_blank_line(self):
        out = self._emit({"action": "compile"}, "the body")
        self.assertIn("\n\nthe body", out)

    def test_a_multi_line_body_survives(self):
        out = self._emit({"action": "compile"}, "line1\nline2")
        self.assertIn("line1\nline2", out)


# ══════════════════════════════════════════════════════════════════════
#  14. CONTRACT CONSTANTS
# ══════════════════════════════════════════════════════════════════════

class ContractConstantsTests(unittest.TestCase):

    def test_all_actions_is_the_union_of_the_three_groups(self):
        mod = _m()
        self.assertEqual(mod._ALL_ACTIONS,
                         mod._ENV_ACTIONS | mod._AUTHOR_ACTIONS | mod._BUILD_ACTIONS)

    def test_the_three_action_groups_do_not_overlap(self):
        mod = _m()
        self.assertFalse(mod._ENV_ACTIONS & mod._AUTHOR_ACTIONS)
        self.assertFalse(mod._ENV_ACTIONS & mod._BUILD_ACTIONS)
        self.assertFalse(mod._AUTHOR_ACTIONS & mod._BUILD_ACTIONS)

    def test_every_engine_needing_action_is_a_real_action(self):
        mod = _m()
        self.assertTrue(mod._NEED_ENGINE <= mod._ALL_ACTIONS)

    def test_the_three_engines_are_the_documented_ones(self):
        self.assertEqual(_m()._ENGINES, ("pdflatex", "xelatex", "lualatex"))

    def test_the_five_edit_modes_are_the_documented_ones(self):
        self.assertEqual(set(_m()._EDIT_MODES),
                         {"replace", "insert_before", "insert_after", "append", "prepend"})

    def test_clean_never_lists_a_tex_bib_or_pdf_as_disposable(self):
        for ext in (".tex", ".bib", ".pdf"):
            self.assertNotIn(ext, _m()._AUX_EXTENSIONS)

    def test_the_aux_list_covers_the_bibliography_artifacts(self):
        for ext in (".bbl", ".blg", ".bcf"):
            self.assertIn(ext, _m()._AUX_EXTENSIONS)

    def test_the_aux_list_covers_the_index_and_glossary_artifacts(self):
        for ext in (".idx", ".ind", ".glo", ".gls"):
            self.assertIn(ext, _m()._AUX_EXTENSIONS)

    def test_every_aux_extension_starts_with_a_dot(self):
        for ext in _m()._AUX_EXTENSIONS:
            self.assertTrue(ext.startswith("."), ext)

    def test_the_rerun_markers_are_lowercase_for_case_insensitive_matching(self):
        for marker in _m()._RERUN_MARKERS:
            self.assertEqual(marker, marker.lower(), marker)

    def test_the_default_preamble_packages_include_amsmath(self):
        self.assertIn("amsmath", _m()._DEFAULT_PREAMBLE_PACKAGES)

    def test_hyperref_is_NOT_in_the_default_list_because_it_loads_last(self):
        self.assertNotIn("hyperref", _m()._DEFAULT_PREAMBLE_PACKAGES)


# ══════════════════════════════════════════════════════════════════════
#  SUMMARY MODE — python Tlamatini/agent/test_latexer_suite.py
# ══════════════════════════════════════════════════════════════════════

def _run_with_summary():
    """Run the whole asset and print a per-class breakdown."""
    module = __import__(__name__)
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromModule(module)
    total = suite.countTestCases()
    # Counted, never hardcoded — a hardcoded total silently lies the moment
    # anyone adds a class.
    areas = len([n for n in dir(module)
                 if n.endswith("Tests")
                 and isinstance(getattr(module, n), type)
                 and issubclass(getattr(module, n), unittest.TestCase)])

    print("=" * 78)
    print("  TLAMATINI — LaTeXer BIG SUITE (fixed testing asset)")
    print("  Created by Angela López Mendoza · @angelahack1")
    print("  %d tests across %d test classes" % (total, areas))
    print("=" * 78)

    result = unittest.TextTestRunner(verbosity=2).run(suite)

    print()
    print("=" * 78)
    print("  RAN      : %d" % result.testsRun)
    print("  PASSED   : %d" % (result.testsRun - len(result.failures)
                               - len(result.errors) - len(result.skipped)))
    print("  FAILED   : %d" % len(result.failures))
    print("  ERRORS   : %d" % len(result.errors))
    print("  SKIPPED  : %d" % len(result.skipped))
    print("  VERDICT  : %s" % ("ALL GREEN" if result.wasSuccessful() else "RED"))
    print("=" * 78)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(_run_with_summary())
