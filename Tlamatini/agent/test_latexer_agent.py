# ═══════════════════════════════════════════════════════════════════
#   ✦  T L A M A T I N I  ✦   —   "one who knows"
#
#   Created by  Angela López Mendoza   ·   @angelahack1
#   Developer · Architect · Creator of Tlamatini
#
#   Every line of this file was written by Angela López Mendoza.
# ═══════════════════════════════════════════════════════════════════
#   Tlamatini Author Banner — do not remove (releases scrub the name automatically)
"""Automated tests for the LaTeXer workflow agent and its surrounding infrastructure.

LaTeXer is Tlamatini's LaTeX TYPESETTING agent — the typesetting sibling of PDFer
(PDFer COMPOSES a PDF from Markdown/HTML/images; LaTeXer TYPESETS one from .tex
source). It is a standalone pool agent under ``agent/agents/latexer/`` loaded here
through importlib, exactly like ``test_pdfer_agent.py`` loads PDFer.

WHAT THESE TESTS DRIVE
----------------------
**Real code, no fakes for the thing under test.** Every parser, validator, template
and safety gate runs for real. The only thing that is conditional is the handful of
tests that need an actual TeX distribution: those SKIP when none is installed (so the
suite is green on a machine without MiKTeX) and RUN a genuine end-to-end compile when
one is present. That is deliberate — a test that silently fakes ``pdflatex`` would
prove nothing about the agent's real job.

THE INCIDENT THIS SUITE PINS
----------------------------
``LatexmkUsabilityTests`` exists because of a REAL failure found while building this
agent: ``latexmk.exe`` ships with EVERY MiKTeX installation, so ``shutil.which`` always
finds it — but it is a PERL SCRIPT, and Angela's machine (like most Windows machines)
has no Perl. Trusting "it is on disk" meant the DEFAULT build path died with
"MiKTeX could not find the script engine 'perl'", produced no PDF, AND reported
``errors: 0`` with no explanation. Three things were fixed and are pinned here:
usability probing, automatic fallback to the built-in loop, and never reporting a
failure with nothing to act on.
"""
import importlib.util
import io
import logging
import os
import re
import tempfile
import unittest


_REPO_AGENT_DIR = os.path.dirname(os.path.abspath(__file__))
_LATEXER_DIR = os.path.join(_REPO_AGENT_DIR, 'agents', 'latexer')
_MODULE_CACHE = {}


def _load_latexer_module():
    """Import agents/latexer/latexer.py.

    The module has top-level side effects (os.chdir, truncating its log,
    logging.basicConfig) because every pool agent does. Save and restore the cwd and
    the root logger's handlers so importing it cannot corrupt the test runner's own
    logging — the same guard test_pdfer_agent.py uses.
    """
    if 'mod' in _MODULE_CACHE:
        return _MODULE_CACHE['mod']

    module_path = os.path.join(_LATEXER_DIR, 'latexer.py')
    saved_cwd = os.getcwd()
    root = logging.getLogger()
    saved_handlers = list(root.handlers)
    saved_level = root.level
    try:
        spec = importlib.util.spec_from_file_location(
            'agent_latexer_module_for_tests', module_path)
        if spec is None or spec.loader is None:
            raise RuntimeError(f'Unable to load LaTeXer module from {module_path}')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    finally:
        os.chdir(saved_cwd)
        root.handlers[:] = saved_handlers
        root.setLevel(saved_level)

    _MODULE_CACHE['mod'] = module
    return module


def _m():
    return _load_latexer_module()


def _read(*parts):
    with io.open(os.path.join(*parts), 'r', encoding='utf-8') as f:
        return f.read()


def _migration_named(suffix):
    """Locate a LaTeXer migration by its NAME SUFFIX, not its number.

    The English and Spanish editions carry the SAME three migrations under
    DIFFERENT numbers: the Spanish tree already spent 0191 on
    ``0191_translate_prompt_catalog_to_spanish``, so its LaTeXer trio is
    0192/0193/0194 where English uses 0191/0192/0193. Globbing on the suffix
    keeps ONE test file valid in both editions - and keeps it valid after any
    future renumber, which a hardcoded number would silently break.
    """
    folder = os.path.join(_REPO_AGENT_DIR, 'migrations')
    hits = sorted(
        n for n in os.listdir(folder)
        if n.endswith(suffix) and re.match(r'^\d{4}_', n)
    )
    assert len(hits) == 1, f'expected exactly one *{suffix}, found {hits}'
    return os.path.join(folder, hits[0])


def _parse_section(text, agent_type='LATEXER'):
    """Parse an INI_SECTION_<TYPE> block the way Parametrizer does: KV header before
    the first blank line, body after it as `response_body`."""
    pattern = re.compile(
        r'INI_SECTION_' + agent_type + r'<<<\n(.*?)\n>>>END_SECTION_' + agent_type,
        re.DOTALL)
    match = pattern.search(text)
    if not match:
        return None
    raw = match.group(1)
    if '\n\n' in raw:
        header, body = raw.split('\n\n', 1)
    else:
        header, body = raw, ''
    fields = {}
    for line in header.splitlines():
        if ': ' in line:
            key, value = line.split(': ', 1)
            fields[key.strip()] = value.strip()
        elif line.endswith(':'):
            fields[line[:-1].strip()] = ''
    fields['response_body'] = body
    return fields


class _CaptureLog:
    """Capture the records LaTeXer emits through logging, so the INI_SECTION block can
    be parsed exactly as Parametrizer would read it out of the agent's .log."""

    def __init__(self):
        self.records = []

    def __enter__(self):
        outer = self

        class _H(logging.Handler):
            def emit(self, record):
                outer.records.append(record.getMessage())

        self.handler = _H()
        self.logger = logging.getLogger()
        self.saved_handlers = list(self.logger.handlers)
        self.saved_level = self.logger.level
        self.logger.handlers[:] = [self.handler]
        self.logger.setLevel(logging.INFO)
        return self

    def __exit__(self, *exc):
        self.logger.handlers[:] = self.saved_handlers
        self.logger.setLevel(self.saved_level)
        return False


def _has_latex():
    """Is a real TeX engine installed on THIS machine? Used to skip (never fake) the
    end-to-end compile tests."""
    try:
        mod = _m()
        tools = mod._resolve_toolchain({}, dict(os.environ))
        return bool(tools['latex'])
    except Exception:
        return False


# =====================================================================
# COERCION — the wrapped Multi-Turn parser hands everything over as strings
# =====================================================================

class CoercionTests(unittest.TestCase):

    def test_as_int_extracts_a_leading_number_from_prose(self):
        m = _m()
        self.assertEqual(m._as_int('5 passes please', 3), 5)
        self.assertEqual(m._as_int(7, 3), 7)
        self.assertEqual(m._as_int('7', 3), 7)

    def test_as_int_refuses_bools_and_objects(self):
        """The Recorder bug class: str(object) contains a hex address, whose digits
        would silently become a value — e.g. max_passes=0, i.e. never compile."""
        m = _m()
        self.assertEqual(m._as_int(True, 3), 3)
        self.assertEqual(m._as_int(object(), 3), 3)
        self.assertEqual(m._as_int(None, 3), 3)
        self.assertEqual(m._as_int('no digits here', 3), 3)

    def test_as_bool_round_trip(self):
        m = _m()
        for truthy in (True, 'true', 'True', 'YES', '1', 'on'):
            self.assertTrue(m._as_bool(truthy, False), truthy)
        for falsy in (False, 'false', 'no', '0', 'off', ''):
            self.assertFalse(m._as_bool(falsy, True), falsy)
        self.assertTrue(m._as_bool('nonsense', True))

    def test_as_list_accepts_a_comma_string(self):
        """The wrapped parser cannot express a YAML list, so packages='a, b' must work."""
        m = _m()
        self.assertEqual(m._as_list('amsmath, graphicx'), ['amsmath', 'graphicx'])
        self.assertEqual(m._as_list(['amsmath', 'graphicx']), ['amsmath', 'graphicx'])
        self.assertEqual(m._as_list(''), [])
        self.assertEqual(m._as_list(None), [])

    def test_as_tribool_keeps_auto_distinct_from_false(self):
        """use_latexmk is THREE-state. A plain _as_bool would collapse 'auto' to False
        and silently disable latexmk for everyone."""
        m = _m()
        self.assertEqual(m._as_tribool('auto'), 'auto')
        self.assertEqual(m._as_tribool(''), 'auto')
        self.assertEqual(m._as_tribool(True), 'true')
        self.assertEqual(m._as_tribool(False), 'false')
        self.assertEqual(m._as_tribool('no'), 'false')


# =====================================================================
# PATH SAFETY
# =====================================================================

class PathSafetyTests(unittest.TestCase):

    def test_safe_basename_cannot_escape_the_output_dir(self):
        m = _m()
        for hostile in ('../../etc/passwd', r'..\..\windows\system32\evil',
                        '/absolute/report', 'C:/Windows/report'):
            got = m._safe_basename(hostile, '.pdf')
            self.assertNotIn('..', got)
            self.assertNotIn('/', got)
            self.assertNotIn('\\', got)

    def test_safe_basename_adds_an_extension_and_strips_illegal_chars(self):
        m = _m()
        self.assertEqual(m._safe_basename('report', '.pdf'), 'report.pdf')
        self.assertEqual(m._safe_basename('report.pdf', '.pdf'), 'report.pdf')
        self.assertNotIn('|', m._safe_basename('re|port', '.pdf'))
        self.assertEqual(m._safe_basename('', '.pdf'), '')

    def test_unique_path_never_clobbers_unless_asked(self):
        m = _m()
        with tempfile.TemporaryDirectory() as tmp:
            target = os.path.join(tmp, 'doc.pdf')
            with io.open(target, 'w', encoding='utf-8') as f:
                f.write('x')
            self.assertEqual(m._unique_path(target, True), target)
            self.assertEqual(os.path.basename(m._unique_path(target, False)), 'doc_2.pdf')

    def test_timestamped_name_shape(self):
        m = _m()
        self.assertRegex(m._timestamped_name('.pdf'),
                         r'^latexer_\d{8}_\d{6}_\d{3}\.pdf$')

    def test_work_base_returns_empty_when_nothing_is_configured(self):
        """SAFETY: os.path.dirname(os.path.abspath('')) resolves to the PARENT OF THE
        AGENT'S OWN CWD. If `clean` fell back to that, an empty config would send it
        hunting for .aux/.log files inside the live agent pool. It must return ''."""
        m = _m()
        self.assertEqual(m._work_base({}), '')
        self.assertEqual(m._work_base({'project_dir': '', 'tex_path': ''}), '')
        self.assertTrue(m._work_base({'project_dir': '.'}))


# =====================================================================
# LaTeX SOURCE ANALYSIS
# =====================================================================

class SourceAnalysisTests(unittest.TestCase):

    def test_strip_comments_keeps_an_escaped_percent(self):
        """`\\%` is a literal percent sign, NOT a comment. Getting this wrong would
        truncate every document that prints a percentage."""
        m = _m()
        cleaned = m._strip_comments(r'100\% done % this is a comment')
        self.assertIn(r'100\% done', cleaned)
        self.assertNotIn('this is a comment', cleaned)

    def test_commented_out_environments_do_not_confuse_the_validator(self):
        m = _m()
        report = m._validate_source('% \\begin{itemize}\nreal text\n')
        self.assertEqual(report['errors'], [])

    def test_is_full_document_requires_both_markers(self):
        m = _m()
        self.assertTrue(m._is_full_document(
            r'\documentclass{article}\begin{document}hi\end{document}'))
        self.assertFalse(m._is_full_document(r'\documentclass{article}'))
        self.assertFalse(m._is_full_document('just some text'))

    def test_find_main_tex_ignores_input_children(self):
        """The headline feature of compile_project: given a folder of .tex, only the
        file with BOTH \\documentclass and \\begin{document} is the master."""
        m = _m()
        with tempfile.TemporaryDirectory() as tmp:
            with io.open(os.path.join(tmp, 'chapter.tex'), 'w', encoding='utf-8') as f:
                f.write('\\section{A}\nno preamble here\n')
            with io.open(os.path.join(tmp, 'main.tex'), 'w', encoding='utf-8') as f:
                f.write('\\documentclass{article}\n\\begin{document}\n'
                        '\\input{chapter}\n\\end{document}\n')
            found, note = m._find_main_tex(tmp, '', True)
            self.assertEqual(os.path.basename(found), 'main.tex')
            self.assertIn('auto-detected', note)

    def test_find_main_tex_prefers_the_conventional_name_on_a_tie(self):
        m = _m()
        with tempfile.TemporaryDirectory() as tmp:
            for name in ('zeta.tex', 'main.tex'):
                with io.open(os.path.join(tmp, name), 'w', encoding='utf-8') as f:
                    f.write('\\documentclass{article}\n\\begin{document}\n\\end{document}\n')
            found, _note = m._find_main_tex(tmp, '', True)
            self.assertEqual(os.path.basename(found), 'main.tex')

    def test_find_main_tex_reports_when_there_is_no_master(self):
        m = _m()
        with tempfile.TemporaryDirectory() as tmp:
            with io.open(os.path.join(tmp, 'frag.tex'), 'w', encoding='utf-8') as f:
                f.write('\\section{orphan}\n')
            found, note = m._find_main_tex(tmp, '', True)
            self.assertEqual(found, '')
            self.assertIn('documentclass', note)

    def test_collect_children_resolves_input_and_include(self):
        m = _m()
        with tempfile.TemporaryDirectory() as tmp:
            for name in ('one.tex', 'two.tex'):
                with io.open(os.path.join(tmp, name), 'w', encoding='utf-8') as f:
                    f.write('child\n')
            main = os.path.join(tmp, 'main.tex')
            with io.open(main, 'w', encoding='utf-8') as f:
                f.write('\\documentclass{article}\n\\begin{document}\n'
                        '\\input{one}\n\\include{two}\n\\end{document}\n')
            kids = [os.path.basename(p) for p in m._collect_children(main)]
            self.assertEqual(sorted(kids), ['one.tex', 'two.tex'])

    def test_analyze_source_picks_biber_for_biblatex_and_bibtex_for_classic(self):
        m = _m()
        biblatex = m._analyze_source(
            '\\usepackage[backend=biber]{biblatex}\n\\addbibresource{refs.bib}\n')
        self.assertTrue(biblatex['biblatex'])
        self.assertFalse(biblatex['bibtex'])

        classic = m._analyze_source(
            '\\bibliographystyle{plain}\n\\bibliography{refs}\n')
        self.assertTrue(classic['bibtex'])
        self.assertFalse(classic['biblatex'])

    def test_analyze_source_detects_index_and_glossaries(self):
        m = _m()
        needs = m._analyze_source('\\makeindex\n\\makeglossaries\n')
        self.assertTrue(needs['index'])
        self.assertTrue(needs['glossaries'])

    def test_document_structure_extracts_the_outline(self):
        m = _m()
        st = m._document_structure(
            '\\documentclass[12pt]{report}\n'
            '\\usepackage{amsmath,graphicx}\n'
            '\\usepackage[utf8]{inputenc}\n'
            '\\begin{document}\n'
            '\\chapter{One}\n\\label{ch:one}\n'
            '\\section{Two}\n'
            'See \\ref{ch:one} and \\cite{knuth1984,lamport1994}.\n'
            '\\end{document}\n')
        self.assertEqual(st['documentclass'], 'report')
        self.assertEqual(st['class_options'], '12pt')
        for pkg in ('amsmath', 'graphicx', 'inputenc'):
            self.assertIn(pkg, st['packages'])
        self.assertEqual([s['level'] for s in st['sections']], ['chapter', 'section'])
        self.assertIn('ch:one', st['labels'])
        self.assertIn('ch:one', st['references'])
        self.assertEqual(sorted(st['citations']), ['knuth1984', 'lamport1994'])


# =====================================================================
# STATIC VALIDATION — works with NO LaTeX installed
# =====================================================================

class ValidateSourceTests(unittest.TestCase):

    def test_clean_document_passes(self):
        m = _m()
        report = m._validate_source(
            '\\documentclass{article}\n\\begin{document}\n'
            '\\section{A}\\label{a}\nSee \\ref{a}.\n\\end{document}\n')
        self.assertTrue(report['ok'])
        self.assertEqual(report['errors'], [])
        self.assertEqual(report['warnings'], [])

    def test_unclosed_environment_is_an_error_with_a_line_number(self):
        m = _m()
        report = m._validate_source(
            '\\documentclass{article}\n\\begin{document}\n\\begin{itemize}\n'
            '\\item x\n\\end{document}\n')
        self.assertFalse(report['ok'])
        self.assertTrue(any('itemize' in e for e in report['errors']))
        self.assertTrue(any(re.search(r'line \d+', e) for e in report['errors']))

    def test_mismatched_environment_names_are_caught(self):
        m = _m()
        report = m._validate_source('\\begin{itemize}\n\\end{enumerate}\n')
        self.assertFalse(report['ok'])
        self.assertTrue(any('enumerate' in e and 'itemize' in e for e in report['errors']))

    def test_unbalanced_braces_are_caught_but_an_escaped_brace_is_not(self):
        m = _m()
        self.assertFalse(m._validate_source('\\section{oops\n')['ok'])
        # \{ and \} are literal characters, not grouping — they must NOT unbalance.
        self.assertTrue(m._validate_source(
            '\\documentclass{article}\n\\begin{document}\n'
            'a \\{ literal \\} brace\n\\end{document}\n')['ok'])

    def test_dangling_reference_is_a_warning_not_an_error(self):
        m = _m()
        report = m._validate_source(
            '\\documentclass{article}\n\\begin{document}\n'
            'See \\ref{nowhere}.\n\\end{document}\n')
        self.assertTrue(report['ok'])
        self.assertTrue(any('nowhere' in w for w in report['warnings']))

    def test_duplicate_label_is_a_warning(self):
        m = _m()
        report = m._validate_source('\\label{x}\ntext\n\\label{x}\n')
        self.assertTrue(any('duplicate' in w.lower() for w in report['warnings']))

    def test_a_fragment_warns_that_it_is_not_compilable(self):
        m = _m()
        report = m._validate_source('$E = mc^2$')
        self.assertTrue(report['ok'])
        self.assertTrue(any('documentclass' in w for w in report['warnings']))


# =====================================================================
# LOG PARSING — the difference between a usable report and 3000 lines of noise
# =====================================================================

class LogParsingTests(unittest.TestCase):

    def test_file_line_error_format_is_extracted(self):
        m = _m()
        diag = m._parse_latex_log('./main.tex:12: Undefined control sequence.\n')
        self.assertTrue(any('main.tex:12' in e for e in diag['errors']))

    def test_bang_errors_are_extracted(self):
        m = _m()
        diag = m._parse_latex_log('! LaTeX Error: Something bad.\nl.42 \\bad\n')
        self.assertTrue(diag['errors'])

    def test_missing_package_is_isolated_from_a_missing_data_file(self):
        m = _m()
        diag = m._parse_latex_log(
            "! LaTeX Error: File `biblatex.sty' not found.\n"
            "! LaTeX Error: File `photo.png' not found.\n")
        self.assertIn('biblatex.sty', diag['missing_packages'])
        self.assertNotIn('biblatex.sty', diag['missing_files'])
        self.assertIn('photo.png', diag['missing_files'])

    def test_rerun_markers_drive_the_convergence_loop(self):
        m = _m()
        for marker in ('LaTeX Warning: Label(s) may have changed. Rerun to get '
                       'cross-references right.',
                       'Please (re)run Biber on the file',
                       'There were undefined references.'):
            self.assertTrue(m._parse_latex_log(marker)['needs_rerun'], marker)
        self.assertFalse(m._parse_latex_log('all good\n')['needs_rerun'])

    def test_output_line_yields_page_count_and_bytes(self):
        m = _m()
        diag = m._parse_latex_log('Output written on main.pdf (7 pages, 123456 bytes).\n')
        self.assertEqual(diag['pages'], 7)
        self.assertEqual(diag['output_bytes'], 123456)
        self.assertEqual(diag['output_file'], 'main.pdf')

    def test_boxes_are_counted_but_never_treated_as_errors(self):
        m = _m()
        diag = m._parse_latex_log(
            'Overfull \\hbox (12.0pt too wide) in paragraph at lines 1--2\n'
            'Underfull \\vbox (badness 10000) has occurred\n')
        self.assertEqual(diag['boxes'], 2)
        self.assertEqual(diag['errors'], [])

    def test_warnings_are_deduplicated(self):
        m = _m()
        diag = m._parse_latex_log(
            'LaTeX Warning: Citation `x` undefined.\n' * 5)
        self.assertEqual(len(diag['warnings']), 1)

    def test_missing_package_report_names_miktex_when_the_distro_cannot_self_install(self):
        m = _m()
        diag = m._parse_latex_log("! LaTeX Error: File `fancyhdr.sty' not found.\n")
        text = m._format_diagnostics(diag, 'texlive', True, 20000)
        self.assertIn('fancyhdr.sty', text)
        self.assertIn('miktex.org', text.lower())


# =====================================================================
# ⚠️ THE latexmk / PERL INCIDENT (found live on 2026-08-05)
# =====================================================================

class LatexmkUsabilityTests(unittest.TestCase):
    """latexmk.exe ships with EVERY MiKTeX install, so shutil.which() always finds it —
    but it is a PERL SCRIPT and most Windows machines have no Perl. Trusting presence
    broke the DEFAULT build path with 'could not find the script engine perl', produced
    no PDF, and reported errors: 0 with no explanation."""

    def test_usability_probe_fails_closed_on_the_perl_error(self):
        m = _m()
        saved = m._run_cmd
        try:
            m._run_cmd = lambda *a, **k: (
                1, "Sorry, but latexmk.exe did not succeed for the following reason:\n"
                   "  MiKTeX could not find the script engine 'perl' which is required "
                   "to execute 'latexmk'.\n", "")
            self.assertFalse(m._latexmk_usable(r'C:\fake\latexmk.exe', {}))
        finally:
            m._run_cmd = saved

    def test_usability_probe_accepts_a_real_version_banner(self):
        m = _m()
        saved = m._run_cmd
        try:
            m._run_cmd = lambda *a, **k: (0, 'Latexmk, John Collins, Version 4.85\n', '')
            self.assertTrue(m._latexmk_usable(r'C:\fake\latexmk.exe', {}))
        finally:
            m._run_cmd = saved

    def test_usability_probe_is_false_for_an_absent_binary(self):
        self.assertFalse(_m()._latexmk_usable('', {}))

    def test_compile_uses_latexmk_usable_not_mere_presence(self):
        """A source contract: the moment someone rewrites this back to
        bool(tools["latexmk"]) the no-Perl regression returns."""
        source = _read(_LATEXER_DIR, 'latexer.py')
        self.assertIn('latexmk_available = bool(tools.get("latexmk_usable"))', source)
        self.assertNotIn('latexmk_available = bool(tools["latexmk"])', source)

    def test_compile_falls_back_to_the_builtin_loop_when_latexmk_makes_no_pdf(self):
        source = _read(_LATEXER_DIR, 'latexer.py')
        self.assertIn('falling back to LaTeXer', source)
        self.assertIn('ran_latexmk = False', source)

    def test_preflight_explains_perl_when_latexmk_is_demanded_but_unusable(self):
        m = _m()
        tools = {'engine': 'pdflatex', 'latex': 'x', 'latexmk': r'C:\mik\latexmk.exe',
                 'latexmk_usable': False, 'biber': '', 'bibtex': '', 'makeindex': '',
                 'makeglossaries': '', 'distribution': 'miktex', 'version_line': ''}
        pf = m._preflight('compile', {'use_latexmk': True, 'input_text': 'hi'}, tools)
        self.assertFalse(pf['ok'])
        self.assertTrue(any('Perl' in f for f in pf['fatals']))


# =====================================================================
# TEMPLATES — token replacement, NEVER str.format (LaTeX is all braces)
# =====================================================================

class TemplateTests(unittest.TestCase):

    def test_every_template_renders_without_leftover_tokens(self):
        m = _m()
        cfg = {'title': 'T', 'author': 'A', 'content': 'C', 'document_language': 'en'}
        for name in m._TEMPLATES:
            out = m._render_template(name, cfg)
            self.assertNotIn('%%', out, f'{name} left an unreplaced token')
            self.assertIn('\\begin{document}', out)
            self.assertIn('\\end{document}', out)

    def test_templates_are_valid_latex_by_our_own_validator(self):
        m = _m()
        cfg = {'title': 'T', 'author': 'A', 'content': 'C'}
        for name in m._TEMPLATES:
            report = m._validate_source(m._render_template(name, cfg))
            self.assertTrue(report['ok'], f'{name}: {report["errors"]}')

    def test_spanish_template_loads_babel_and_the_language_switch_works(self):
        m = _m()
        es = m._render_template('spanish-article', {'title': 'T'})
        self.assertIn('spanish', es)
        art_es = m._render_template('article', {'title': 'T', 'document_language': 'es'})
        self.assertIn('babel', art_es)
        art_en = m._render_template('article', {'title': 'T', 'document_language': 'en'})
        self.assertNotIn('babel', art_en)

    def test_build_document_honours_packages_and_geometry(self):
        m = _m()
        out = m._build_document({
            'documentclass': 'report', 'class_options': '12pt',
            'packages': 'amsmath, tikz', 'geometry': 'margin=1cm',
            'title': 'T', 'content': 'body'})
        self.assertIn('\\documentclass[12pt]{report}', out)
        self.assertIn('\\usepackage{amsmath}', out)
        self.assertIn('\\usepackage{tikz}', out)
        self.assertIn('\\usepackage[margin=1cm]{geometry}', out)
        self.assertIn('\\maketitle', out)

    def test_wrap_fragment_turns_a_bare_formula_into_a_real_document(self):
        m = _m()
        wrapped = m._wrap_fragment('$E = mc^2$', {})
        self.assertTrue(m._is_full_document(wrapped))
        self.assertIn('$E = mc^2$', wrapped)

    def test_generated_preamble_carries_amsmath_REGRESSION_2026_08_05(self):
        """The generated preamble must be as capable as the templates it stands in for.

        LIVE FAILURE (2026-08-05 08:13, run latexer_004_0f36dece): the wizard's Step-3
        fragment used \\eqref, the generated preamble had NO amsmath, and pdflatex died
        with 'latexer_wizard_step3.tex:13: Undefined control sequence' -- AFTER writing
        a PDF, so Angela was handed a silently mis-typeset document.
        """
        m = _m()
        wrapped = m._wrap_fragment(
            r'\begin{equation} E = mc^2 \label{eq:e} \end{equation} See \eqref{eq:e}.', {})
        for pkg in ('amsmath', 'amssymb', 'graphicx'):
            self.assertIn('\\usepackage{%s}' % pkg, wrapped,
                          'auto_preamble dropped %s -- \\eqref/align/\\text break again' % pkg)
        self.assertIn('hyperref', wrapped)
        # hyperref patches other packages' internals, so it must be loaded LAST.
        self.assertGreater(wrapped.index('hyperref'), wrapped.index('amsmath'))

    def test_generated_preamble_never_loads_a_package_twice(self):
        """A duplicate \\usepackage with different options is a hard 'Option clash' error."""
        m = _m()
        explicit = m._build_document({'packages': 'amsmath, hyperref', 'content': 'x'})
        self.assertEqual(explicit.count('\\usepackage{amsmath}'), 1)
        self.assertEqual(explicit.count('hyperref'), 1)
        # ... and when the caller wrote their own \usepackage inside the content.
        inline = m._build_document({'content': r'\usepackage{amsmath}' + '\ntext'})
        self.assertEqual(inline.count('\\usepackage{amsmath}'), 1)

    def test_exit_code_is_truthful_REGRESSION_2026_08_05(self):
        """LaTeXer must exit NON-ZERO when it did not succeed.

        LIVE FAILURE: latexer.py ended in a bare `sys.exit(0)`, so a `refused`, an
        `invalid` lint and a `compiled_with_errors` build all exited 0. The wrapped
        chat-agent runtime reads that code, so the Exec Report reported a failed
        typeset to the user as SUCCESS.
        """
        src = _read(_LATEXER_DIR, 'latexer.py')
        self.assertIn('sys.exit(0 if ok else 1)', src,
                      'LaTeXer must report its real verdict through its exit code')
        self.assertNotRegex(src, r'\n    sys\.exit\(0\)\s*$',
                            'a bare tail sys.exit(0) makes every run look like SUCCESS')


# =====================================================================
# CLEAN — must never delete the user's work
# =====================================================================

class CleanTests(unittest.TestCase):

    def test_clean_removes_aux_and_never_a_tex_bib_or_pdf(self):
        m = _m()
        with tempfile.TemporaryDirectory() as tmp:
            keep = ['main.tex', 'refs.bib', 'main.pdf', 'photo.png']
            drop = ['main.aux', 'main.log', 'main.toc', 'main.out', 'main.bbl',
                    'main.blg', 'main.bcf', 'main.idx', 'main.fls']
            for name in keep + drop:
                with io.open(os.path.join(tmp, name), 'w', encoding='utf-8') as f:
                    f.write('x')
            removed = m._clean_aux(tmp)
            survivors = set(os.listdir(tmp))
            for name in keep:
                self.assertIn(name, survivors, f'{name} must NEVER be deleted')
            for name in drop:
                self.assertNotIn(name, survivors, f'{name} should have been cleaned')
            self.assertEqual(sorted(removed), sorted(drop))

    def test_clean_can_keep_the_log_for_debugging(self):
        m = _m()
        with tempfile.TemporaryDirectory() as tmp:
            for name in ('main.aux', 'main.log'):
                with io.open(os.path.join(tmp, name), 'w', encoding='utf-8') as f:
                    f.write('x')
            m._clean_aux(tmp, keep_log=True)
            self.assertTrue(os.path.isfile(os.path.join(tmp, 'main.log')))
            self.assertFalse(os.path.isfile(os.path.join(tmp, 'main.aux')))

    def test_clean_on_a_missing_directory_is_a_no_op_not_a_crash(self):
        self.assertEqual(_m()._clean_aux(os.path.join('does', 'not', 'exist')), [])


# =====================================================================
# FAIL-SAFE PREFLIGHT — refuse, never mis-typeset
# =====================================================================

class PreflightTests(unittest.TestCase):

    def _tools(self, **over):
        base = {'engine': 'pdflatex', 'latex': 'C:/fake/pdflatex.exe', 'latexmk': '',
                'latexmk_usable': False, 'biber': '', 'bibtex': '', 'makeindex': '',
                'makeglossaries': '', 'distribution': 'miktex', 'version_line': 'x'}
        base.update(over)
        return base

    def test_unknown_action_is_refused(self):
        pf = _m()._preflight('teleport', {}, self._tools())
        self.assertFalse(pf['ok'])
        self.assertTrue(any('Unknown action' in f for f in pf['fatals']))

    def test_compile_with_no_source_at_all_is_refused(self):
        pf = _m()._preflight('compile', {}, self._tools())
        self.assertFalse(pf['ok'])
        self.assertTrue(any('needs a source' in f for f in pf['fatals']))

    def test_missing_engine_is_refused_and_names_miktex(self):
        pf = _m()._preflight('compile', {'input_text': 'hi'},
                             self._tools(latex='', distribution='none'))
        self.assertFalse(pf['ok'])
        self.assertTrue(any('MiKTeX' in f for f in pf['fatals']))
        self.assertTrue(any('miktex.org' in f for f in pf['fatals']))

    def test_texlive_is_allowed_but_warns_about_on_demand_packages(self):
        """TeX Live is ALLOWED (warning only); only a missing engine is fatal.

        The explicit output_dir keeps this a PURE POLICY assertion. Without it the
        preflight's destination-writability probe resolves the DEFAULT destination,
        which on Angela's machine is the OneDrive-redirected, Spanish-localized
        ``C:\\Users\\angel\\OneDrive\\Documentos\\TlamatiniLaTeX`` — a path whose
        creation can fail even though ``os.makedirs`` returns. That coupled this
        policy check to the real filesystem and made it pass or fail depending on
        the order the suite happened to run in. The probe itself is CORRECT
        behaviour (refusing an unwritable destination is fail-safe), so the fix
        belongs here, in the test, not in the agent.
        """
        with tempfile.TemporaryDirectory() as out_dir:
            pf = _m()._preflight('compile',
                                 {'input_text': 'hi', 'output_dir': out_dir},
                                 self._tools(distribution='texlive'))
        self.assertTrue(pf['ok'], 'unexpected fatals: %s' % pf['fatals'])
        self.assertTrue(any('MiKTeX' in w for w in pf['warnings']))

    def test_validate_and_install_never_require_an_engine(self):
        for action in ('validate', 'install'):
            pf = _m()._preflight(action, {}, self._tools(latex='', distribution='none'))
            self.assertTrue(pf['ok'], action)

    def test_edit_file_needs_an_anchor_and_a_valid_mode(self):
        m = _m()
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, 'a.tex')
            with io.open(path, 'w', encoding='utf-8') as f:
                f.write('hello')
            pf = m._preflight('edit_file', {'tex_path': path, 'edit_mode': 'replace'},
                              self._tools())
            self.assertFalse(pf['ok'])
            self.assertTrue(any('find_text' in f for f in pf['fatals']))

            pf = m._preflight('edit_file',
                              {'tex_path': path, 'edit_mode': 'teleport',
                               'find_text': 'x'}, self._tools())
            self.assertFalse(pf['ok'])
            self.assertTrue(any('edit_mode' in f for f in pf['fatals']))

    def test_unknown_template_is_refused(self):
        pf = _m()._preflight('create_from_template', {'template': 'nope'}, self._tools())
        self.assertFalse(pf['ok'])
        self.assertTrue(any('template' in f for f in pf['fatals']))

    def test_shell_escape_raises_a_security_warning(self):
        pf = _m()._preflight('compile', {'input_text': 'hi', 'shell_escape': True},
                             self._tools())
        self.assertTrue(any('write18' in w or 'arbitrary' in w for w in pf['warnings']))

    def test_clean_with_no_directory_is_refused_rather_than_guessing(self):
        pf = _m()._preflight('clean', {}, self._tools())
        self.assertFalse(pf['ok'])
        self.assertTrue(any('project_dir' in f for f in pf['fatals']))

    def test_report_formatter_is_readable_and_never_empty(self):
        m = _m()
        text = m._format_preflight_report({'fatals': ['boom'], 'warnings': ['meh']})
        self.assertIn('BLOCKERS', text)
        self.assertIn('boom', text)
        self.assertIn('WARNINGS', text)
        self.assertEqual(m._format_preflight_report({}), '(no findings)')


# =====================================================================
# ENGINE COMMAND LINE — the two flags that stop LaTeX hanging forever
# =====================================================================

class EngineArgvTests(unittest.TestCase):

    def _tools(self, distribution='miktex'):
        return {'engine': 'pdflatex', 'latex': 'pdflatex', 'latexmk': 'latexmk',
                'latexmk_usable': True, 'distribution': distribution}

    def test_nonstopmode_and_file_line_error_are_always_present(self):
        """Without -interaction=nonstopmode, LaTeX STOPS at an error and waits for
        keyboard input forever — for an unattended agent that is a hung process."""
        argv = _m()._engine_argv(self._tools(), {}, 'main.tex')
        self.assertIn('-interaction=nonstopmode', argv)
        self.assertIn('-file-line-error', argv)
        self.assertEqual(argv[-1], 'main.tex')

    def test_enable_installer_is_miktex_only(self):
        m = _m()
        self.assertIn('--enable-installer',
                      m._engine_argv(self._tools('miktex'), {}, 'main.tex'))
        self.assertNotIn('--enable-installer',
                         m._engine_argv(self._tools('texlive'), {}, 'main.tex'))

    def test_enable_installer_can_be_turned_off(self):
        argv = _m()._engine_argv(self._tools('miktex'),
                                 {'auto_install_packages': False}, 'main.tex')
        self.assertNotIn('--enable-installer', argv)

    def test_shell_escape_is_absent_by_default_and_opt_in_only(self):
        m = _m()
        self.assertNotIn('-shell-escape', m._engine_argv(self._tools(), {}, 'main.tex'))
        self.assertIn('-shell-escape',
                      m._engine_argv(self._tools(), {'shell_escape': True}, 'main.tex'))

    def test_latexmk_engine_flag_matches_the_selected_engine(self):
        m = _m()
        for engine, flag in (('pdflatex', '-pdf'), ('xelatex', '-pdfxe'),
                             ('lualatex', '-pdflua')):
            tools = self._tools()
            tools['engine'] = engine
            self.assertIn(flag, m._latexmk_argv(tools, {}, 'main.tex'))

    def test_run_cmd_always_closes_stdin(self):
        """A LaTeX tool that ignores nonstopmode must read EOF instantly rather than
        block on a console a background agent does not have."""
        source = _read(_LATEXER_DIR, 'latexer.py')
        self.assertIn('stdin=subprocess.DEVNULL', source)
        self.assertIn('shell=False', source)


# =====================================================================
# STRUCTURED OUTPUT — the Parametrizer contract
# =====================================================================

class SectionEmissionTests(unittest.TestCase):

    def test_section_is_one_atomic_record(self):
        """Concurrent writes interleave: the block MUST be a single logging call or a
        downstream Parametrizer can read a corrupted section."""
        m = _m()
        with _CaptureLog() as cap:
            m._emit_section({'action': 'compile', 'status': 'compiled'}, 'body text')
        blocks = [r for r in cap.records if 'INI_SECTION_LATEXER<<<' in r]
        self.assertEqual(len(blocks), 1)
        self.assertIn('>>>END_SECTION_LATEXER', blocks[0])

    def test_section_round_trips_through_the_parametrizer_parser(self):
        m = _m()
        with _CaptureLog() as cap:
            m._emit_section({'action': 'compile', 'page_count': 3, 'status': 'compiled'},
                            'line one\nline two')
        block = next(r for r in cap.records if 'INI_SECTION_LATEXER<<<' in r)
        fields = _parse_section(block)
        self.assertEqual(fields['action'], 'compile')
        self.assertEqual(fields['page_count'], '3')
        self.assertEqual(fields['status'], 'compiled')
        self.assertEqual(fields['response_body'], 'line one\nline two')

    def test_emitted_header_matches_the_registered_parametrizer_fields(self):
        """The three field lists (agent_contracts / views / the agent itself) must not
        drift, or a Parametrizer mapping silently addresses a field that never exists."""
        from agent.services.agent_contracts import _PARAMETRIZER_OUTPUT_FIELDS
        m = _m()
        outcome = {
            'action': 'compile', 'engine': 'pdflatex', 'distribution': 'miktex',
            'tex_path': '', 'project_dir': '', 'output_path': '', 'output_dir': '',
            'filename': '', 'page_count': 0, 'bytes': 0, 'passes': 0,
            'bibliography': 'none', 'errors': 0, 'warnings': 0, 'success': False,
            'status': 'error',
        }
        with _CaptureLog() as cap:
            m._emit_section(outcome, 'body')
        block = next(r for r in cap.records if 'INI_SECTION_LATEXER<<<' in r)
        emitted = set(_parse_section(block)) - {'response_body'}
        registered = set(_PARAMETRIZER_OUTPUT_FIELDS['latexer']) - {'response_body'}
        self.assertEqual(emitted, registered)


# =====================================================================
# REGISTRY INTEGRATION — the ~10 surfaces an agent must be wired into
# =====================================================================

class RegistryIntegrationTests(unittest.TestCase):

    def test_wrapped_chat_agent_spec_is_registered(self):
        from agent.chat_agent_registry import WRAPPED_CHAT_AGENT_BY_TOOL_NAME
        spec = WRAPPED_CHAT_AGENT_BY_TOOL_NAME.get('chat_agent_latexer')
        self.assertIsNotNone(spec, 'chat_agent_latexer is not in the wrapped registry')
        self.assertEqual(spec.key, 'latexer')
        self.assertEqual(spec.template_dir, 'latexer')
        self.assertEqual(spec.tool_description, 'Chat-Agent-LaTeXer')
        self.assertEqual(spec.display_name, 'LaTeXer')

    def test_display_name_casing_is_exactly_LaTeXer_everywhere(self):
        """⚠️ agent_paths.display_name_from_agent_type is the REAL source of truth —
        apps.ready() wipes the Agent table on every boot and re-derives from it. Without
        the override, str.title() ships this agent as "Latexer"."""
        from agent.chat_agent_registry import WRAPPED_CHAT_AGENT_BY_TOOL_NAME
        from agent.services.agent_paths import display_name_from_agent_type
        self.assertEqual(display_name_from_agent_type('latexer'), 'LaTeXer')
        spec = WRAPPED_CHAT_AGENT_BY_TOOL_NAME['chat_agent_latexer']
        self.assertEqual(spec.display_name, 'LaTeXer')
        for wrong in ('Latexer', 'LATEXER', 'LaTexer', 'latexEr'):
            self.assertNotEqual(spec.display_name, wrong)
            self.assertNotEqual(display_name_from_agent_type('latexer'), wrong)
        migration = _read(_migration_named('_add_latexer.py'))
        self.assertIn("agentDescription='LaTeXer'", migration)

    def test_agent_contract_resolves(self):
        from agent.services.agent_contracts import get_agent_contract
        contract = get_agent_contract('latexer')
        self.assertEqual(contract.display_name, 'LaTeXer')
        self.assertIn('output_path', contract.parametrizer_fields)
        self.assertIn('status', contract.parametrizer_fields)

    def test_parametrizer_field_lists_agree_across_all_three_registries(self):
        from agent.services.agent_contracts import _PARAMETRIZER_OUTPUT_FIELDS
        from agent.views import PARAMETRIZER_SOURCE_OUTPUT_FIELDS
        registered = tuple(_PARAMETRIZER_OUTPUT_FIELDS['latexer'])
        self.assertEqual(tuple(PARAMETRIZER_SOURCE_OUTPUT_FIELDS['latexer']), registered)
        parametrizer = _read(_REPO_AGENT_DIR, 'agents', 'parametrizer', 'parametrizer.py')
        self.assertIn("'latexer',", parametrizer,
                      "'latexer' is missing from SECTION_AGENT_TYPES")

    def test_exec_report_captures_latexer(self):
        from agent.mcp_agent import _EXEC_REPORT_TOOLS, _resolve_exec_report_spec
        self.assertIn('chat_agent_latexer', _EXEC_REPORT_TOOLS)
        self.assertEqual(_EXEC_REPORT_TOOLS['chat_agent_latexer'], ('latexer', 'LaTeXer'))
        self.assertEqual(_resolve_exec_report_spec('chat_agent_latexer'),
                         ('latexer', 'LaTeXer'))

    def test_ask_execs_gates_latexer_tier_a(self):
        """It writes .tex + PDF to free-form paths, edits in place, deletes aux files
        AND runs a real compiler. Tier A and a command-runner, twice over."""
        from agent.mcp_agent import _ASK_EXECS_REQUIRED_TOOLS, _MANAGEMENT_TOOLS
        self.assertIn('chat_agent_latexer', _ASK_EXECS_REQUIRED_TOOLS)
        self.assertNotIn('chat_agent_latexer', _MANAGEMENT_TOOLS)

    def test_section_fields_are_promoted_to_the_tool_result(self):
        from agent.tools import _PROMOTE_SECTION_FIELDS_BY_TEMPLATE_DIR
        promoted = _PROMOTE_SECTION_FIELDS_BY_TEMPLATE_DIR['latexer']
        for field in ('output_path', 'status', 'page_count', 'errors', 'success'):
            self.assertIn(field, promoted)

    def test_connection_url_resolves(self):
        from django.urls import reverse
        self.assertEqual(reverse('update_latexer_connection', args=['latexer-1']),
                         '/agent/update_latexer_connection/latexer-1/')

    def test_connection_view_exists(self):
        from agent import views
        self.assertTrue(hasattr(views, 'update_latexer_connection_view'))


# =====================================================================
# SOURCE CONTRACTS — the frontend + config surfaces
# =====================================================================

class SourceContractTests(unittest.TestCase):

    def test_config_yaml_parses_and_carries_every_documented_key(self):
        import yaml
        raw = _read(_LATEXER_DIR, 'config.yaml')
        cfg = yaml.safe_load(raw)
        for key in ('action', 'tex_path', 'project_dir', 'main_file', 'input_text',
                    'auto_preamble', 'documentclass', 'template', 'document_language',
                    'edit_mode', 'find_text', 'replace_text', 'engine', 'use_latexmk',
                    'auto_install_packages', 'max_passes', 'bibliography',
                    'shell_escape', 'output_dir', 'filename', 'overwrite', 'keep_aux',
                    'projects_dir', 'preflight', 'command_timeout',
                    'miktex_install_url', 'source_agents', 'target_agents'):
            self.assertIn(key, cfg, f'config.yaml is missing {key}')

    def test_config_defaults_are_safe(self):
        import yaml
        cfg = yaml.safe_load(_read(_LATEXER_DIR, 'config.yaml'))
        self.assertFalse(cfg['shell_escape'], 'shell_escape MUST default to false')
        self.assertTrue(cfg['preflight'])
        self.assertTrue(cfg['auto_install_packages'])
        self.assertEqual(cfg['source_agents'], [])
        self.assertEqual(cfg['target_agents'], [])

    def test_config_documentation_recommends_miktex(self):
        raw = _read(_LATEXER_DIR, 'config.yaml')
        self.assertIn('MiKTeX', raw)
        self.assertIn('miktex.org/download', raw)

    def test_agent_never_imports_the_django_app(self):
        """A pool subprocess has no sys.path back into agent.* — importing it is a
        runtime ModuleNotFoundError."""
        source = _read(_LATEXER_DIR, 'latexer.py')
        self.assertNotIn('from agent.', source)
        self.assertNotIn('import agent.', source)

    def test_agent_honours_the_temp_policy_and_the_orphan_guard(self):
        source = _read(_LATEXER_DIR, 'latexer.py')
        self.assertIn('TLAMATINI_TEMP', source)
        self.assertIn('_chg_guarded_init', source)
        self.assertIn("os.environ['FOR_DISABLE_CONSOLE_CTRL_HANDLER'] = '1'", source)

    def test_reanimation_marker_precedes_logging_config(self):
        source = _read(_LATEXER_DIR, 'latexer.py')
        self.assertIn("_IS_REANIMATED = os.environ.get('AGENT_REANIMATED') == '1'", source)
        self.assertLess(source.index('_IS_REANIMATED ='),
                        source.index('logging.basicConfig'),
                        'the reanimation marker must be set BEFORE basicConfig or the '
                        'log is truncated on every resume')

    def test_agent_always_triggers_downstream(self):
        source = _read(_LATEXER_DIR, 'latexer.py')
        self.assertIn('wait_for_agents_to_stop(target_agents)', source)
        self.assertLess(source.index('wait_for_agents_to_stop(target_agents)'),
                        source.rindex('start_agent(target)'),
                        'the concurrency guard must precede the start loop')

    def test_javascript_wiring_is_complete(self):
        js = os.path.join(_REPO_AGENT_DIR, 'static', 'agent', 'js')
        connectors = _read(js, 'acp-agent-connectors.js')
        self.assertIn('async function updateLatexerConnection(', connectors)
        self.assertIn('/agent/update_latexer_connection/', connectors)

        core = _read(js, 'acp-canvas-core.js')
        self.assertIn("'latexer': 'latexer-agent',", core)      # classMap (HYPHEN form)
        self.assertEqual(core.count("=== 'latexer'"), 3,
                         'acp-canvas-core.js must handle latexer in removeConnection, '
                         'removeConnectionsFor AND the mouseup handler')

        undo = _read(js, 'acp-canvas-undo.js')
        self.assertIn("updateLatexerConnection(sourceId, targetId, 'remove')", undo)
        self.assertIn("updateLatexerConnection(sourceId, targetId, 'add')", undo)

        file_io = _read(js, 'acp-file-io.js')
        self.assertIn("case 'latexer': await updateLatexerConnection(", file_io)

        chat = _read(js, 'agent_page_chat.js')
        self.assertIn("} else if (lower === 'latexer') {", chat)

    def test_flow_generator_branch_covers_the_config_keys(self):
        import yaml
        chat = _read(os.path.join(_REPO_AGENT_DIR, 'static', 'agent', 'js'),
                     'agent_page_chat.js')
        branch = chat.split("} else if (lower === 'latexer') {", 1)[1].split('} else if', 1)[0]
        cfg = yaml.safe_load(_read(_LATEXER_DIR, 'config.yaml'))
        skip = {'source_agents', 'target_agents', 'miktex_install_url',
                'latexmk_executable', 'biber_executable', 'bibtex_executable',
                'makeindex_executable'}
        for key in cfg:
            if key in skip:
                continue
            self.assertIn(f"'{key}'", branch,
                          f'{key} is missing from _mapToolArgsToAgentConfig, so a '
                          f'generated .flw would silently fall back to the default')

    def test_css_gradient_exists_and_is_unique(self):
        css = _read(os.path.join(_REPO_AGENT_DIR, 'static', 'agent', 'css'),
                    'agentic_control_panel.css')
        self.assertIn('.canvas-item.latexer-agent {', css)
        self.assertIn('.canvas-item.latexer-agent:hover {', css)
        # The four stops must not collide with another agent's palette.
        self.assertEqual(css.count('#14213D 0%, #7F5539 33%, #C9973F 66%, #F0E3C2 100%'), 1)

    def test_exec_report_css_exists(self):
        css = _read(os.path.join(_REPO_AGENT_DIR, 'static', 'agent', 'css'),
                    'agent_page.css')
        self.assertIn('.exec-report-caption-latexer {', css)
        self.assertIn('.exec-report-latexer .exec-report-cmd', css)
        self.assertIn('.exec-report-latexer thead th,', css)

    def test_migrations_exist_and_chain(self):
        add = _migration_named('_add_latexer.py')
        tool = _migration_named('_add_chat_agent_latexer_tool.py')
        prompts = _migration_named('_add_latexer_demo_prompts.py')
        for path in (add, tool, prompts):
            self.assertTrue(os.path.isfile(path), path)
        # Each link names the PREVIOUS migration's stem, whatever it is numbered.
        add_stem = os.path.splitext(os.path.basename(add))[0]
        tool_stem = os.path.splitext(os.path.basename(tool))[0]
        self.assertIn(add_stem, _read(tool))
        self.assertIn(tool_stem, _read(prompts))
        self.assertIn('Chat-Agent-LaTeXer', _read(tool))

    def test_demo_prompts_drive_the_wrapped_tool_and_mention_miktex(self):
        """MANDATORY GATE: a Multi-Turn agent without a catalog prompt is INCOMPLETE."""
        migration = _read(_migration_named('_add_latexer_demo_prompts.py'))
        self.assertGreaterEqual(migration.count('chat_agent_latexer'), 4)
        self.assertIn('miktex.org/download', migration)
        self.assertIn("'category': 'documents'", migration)
        self.assertIn("'sort_rank': rank", migration)

    def test_flowcreator_and_flowhypervisor_know_about_latexer(self):
        skill = _read(_REPO_AGENT_DIR, 'agents', 'flowcreator', 'agentic_skill.md')
        self.assertIn('LaTeXer', skill)
        self.assertIn('INI_SECTION_LATEXER', skill)
        hypervisor = _read(_REPO_AGENT_DIR, 'agents', 'flowhypervisor',
                           'monitoring-prompt.pmt')
        self.assertIn('LATEXER SPECIAL NOTES', hypervisor)
        # The watchdog must be told that repeated passes are CORRECT, not a stuck loop.
        self.assertIn('MULTIPLE COMPILER PASSES ARE CORRECT', hypervisor)


# =====================================================================
# END-TO-END — a REAL compile, when a real TeX distribution is installed
# =====================================================================

@unittest.skipUnless(_has_latex(),
                     'no TeX distribution installed — install MiKTeX '
                     '(https://miktex.org/download) to run the end-to-end tests')
class EndToEndCompileTests(unittest.TestCase):
    """These drive a REAL LaTeX engine. They are skipped (never faked) on a machine
    with no TeX distribution, because faking pdflatex would prove nothing."""

    def _compile(self, config, source, filename='doc.tex'):
        m = _m()
        tmp = tempfile.mkdtemp()
        path = os.path.join(tmp, filename)
        with io.open(path, 'w', encoding='utf-8') as f:
            f.write(source)
        tools = m._resolve_toolchain(config, dict(os.environ))
        return m._compile(path, config, tools, dict(os.environ)), path, tmp

    def test_a_minimal_document_really_compiles_to_a_pdf(self):
        result, path, _tmp = self._compile(
            {'use_latexmk': False, 'command_timeout': 300},
            '\\documentclass{article}\n\\begin{document}\n'
            'Hello from Tlamatini. $E = mc^2$.\n\\end{document}\n')
        self.assertTrue(result['produced'], f'no PDF: {result["steps"]}')
        self.assertTrue(result['ok'], f'errors: {result["diag"]["errors"]}')
        self.assertEqual(result['diag']['pages'], 1)
        self.assertTrue(os.path.isfile(result['pdf']))
        with io.open(result['pdf'], 'rb') as f:
            self.assertEqual(f.read(5), b'%PDF-')

    def test_cross_references_force_more_than_one_pass(self):
        """The convergence loop's whole reason to exist: pass 1 cannot know the
        equation's number yet."""
        result, _p, _t = self._compile(
            {'use_latexmk': False, 'command_timeout': 300},
            '\\documentclass{article}\n\\begin{document}\n'
            '\\section{A}\\label{sec:a}\n'
            'See section~\\ref{sec:a} on page~\\pageref{sec:a}.\n'
            '\\end{document}\n')
        self.assertTrue(result['produced'])
        self.assertGreaterEqual(result['passes'], 2,
                                'a \\ref must trigger at least one re-run')

    def test_a_broken_document_reports_errors_and_never_claims_success(self):
        result, _p, _t = self._compile(
            {'use_latexmk': False, 'command_timeout': 300},
            '\\documentclass{article}\n\\begin{document}\n'
            '\\thisCommandDoesNotExist\n\\end{document}\n')
        self.assertFalse(result['ok'], 'a document with a real LaTeX error is NOT ok')
        self.assertTrue(result['diag']['errors'], 'the error must be reported')

    def test_project_compile_finds_the_master_and_follows_input(self):
        m = _m()
        tmp = tempfile.mkdtemp()
        with io.open(os.path.join(tmp, 'chapter.tex'), 'w', encoding='utf-8') as f:
            f.write('\\section{Included}\nText from the child file.\n')
        with io.open(os.path.join(tmp, 'main.tex'), 'w', encoding='utf-8') as f:
            f.write('\\documentclass{article}\n\\begin{document}\n'
                    '\\input{chapter}\n\\end{document}\n')
        main, note = m._find_main_tex(tmp, '', True)
        self.assertEqual(os.path.basename(main), 'main.tex', note)
        result = m._compile(main, {'use_latexmk': False, 'command_timeout': 300},
                            m._resolve_toolchain({}, dict(os.environ)),
                            dict(os.environ))
        self.assertTrue(result['produced'], f'no PDF: {result["steps"]}')
        self.assertTrue(result['ok'])

    def test_every_template_actually_compiles(self):
        """A template that does not build is worse than no template. beamer may pull a
        package on a fresh MiKTeX — that is the on-demand installer doing its job."""
        m = _m()
        for name in m._TEMPLATES:
            with self.subTest(template=name):
                source = m._render_template(
                    name, {'title': 'T', 'author': 'A', 'content': 'Body text.'})
                result, _p, _t = self._compile(
                    {'use_latexmk': False, 'command_timeout': 420}, source)
                self.assertTrue(result['produced'],
                                f'{name} produced no PDF: {result["diag"]["errors"]}')


if __name__ == '__main__':  # pragma: no cover
    unittest.main()
