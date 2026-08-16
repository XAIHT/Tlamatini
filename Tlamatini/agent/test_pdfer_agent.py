# ═══════════════════════════════════════════════════════════════════
#   ✦  T L A M A T I N I  ✦   —   "one who knows"
#
#   Created by  Angela López Mendoza   ·   @angelahack1
#   Developer · Architect · Creator of Tlamatini
#
#   Every line of this file was written by Angela López Mendoza.
# ═══════════════════════════════════════════════════════════════════
#   Tlamatini Author Banner — do not remove (releases scrub the name automatically)
"""Automated tests for the PDFer workflow agent and its surrounding infrastructure.

PDFer is Tlamatini's DOCUMENT COMPOSER — the WRITE side of the document family
(File-Extractor / File-Interpreter READ documents; PDFer AUTHORS them). It is a
standalone pool agent under ``agent/agents/pdfer/`` loaded here through
``importlib.util.spec_from_file_location`` with a cwd + logging-handler save/restore so
its module-level ``os.chdir`` / ``open(LOG_FILE_PATH)`` / ``logging.basicConfig`` side
effects do not leak.

**These tests drive the REAL renderers, not fakes.** PDFer's whole premise is "zero new
dependencies" — markdown + xhtml2pdf + PyMuPDF + reportlab + Pillow + pypdf already ship
with Tlamatini — so faking them would test nothing and would hide exactly the failure
that matters (a backend missing from the carried Python). Every render test therefore
produces a REAL PDF in a temp dir and re-reads it with pypdf to assert the page count.
The only stubbed thing is the network: ``_ollama_polish`` is exercised against an
unreachable URL to prove the documented "never lose the document" fallback.

Covers:
- Coercion: _as_int (the "18 mm margins" wrapped-parser string class of bug), _as_bool,
  _as_list (real list / comma string / bracketed literal / empty)
- Sniffing: _looks_like_html (Tlamatini's own HTML-table answers), _sniff_mode matrix
- Output: _resolve_output_path default + honored dir, collision-proof _2/_3 sequence,
  overwrite=true reuse, and basename sanitization (a filename cannot escape output_dir)
- REAL rendering: markdown (incl. a real table + cover + page numbers), html, text,
  images (all three layouts, via a real PIL-generated PNG), merge, info, validate
- Fail-safe preflight: unknown mode, empty content, no images, no pdfs, missing
  input_file, unwritable output_dir — each REFUSES and writes no file
- emit: INI_SECTION_PDFER is ONE atomic record and round-trips through a parser that
  mirrors parametrizer's contract
- main() end-stage: section emitted AND target_agents triggered on success AND on a
  fail-safe refusal (so a downstream Forker can always branch on {status})
- Reanimation: AGENT_REANIMATED=1 does not truncate the log
- Ollama polish: an unreachable endpoint keeps the ORIGINAL text and says so
- Registry integration: ChatWrappedAgentSpec, agent contract + parametrizer fields (all
  three lists identical), Exec-Report MEMBERSHIP (state-changing), Ask-Execs tier-A
  MEMBERSHIP, promote-fields, config.yaml defaults, CSS gradient (unique), URL route,
  view, JS wiring (all 6 canvas-core spots + connector + undo + redo + .flw load +
  flow-generator branch), eslint global, parametrizer SECTION_AGENT_TYPES, migrations,
  the new 'documents' prompt category, and the requirements pins that make PDFer
  dependency-free
"""

import importlib.util
import logging
import os
import re
import tempfile
import unittest
from functools import lru_cache

import yaml
from django.test import SimpleTestCase

_REPO_AGENT_DIR = os.path.dirname(__file__)
_REPO_ROOT = os.path.dirname(os.path.dirname(_REPO_AGENT_DIR))


# ---------------------------------------------------------------------------
# Module loading + helpers
# ---------------------------------------------------------------------------


def _load_pdfer_module():
    module_path = os.path.join(_REPO_AGENT_DIR, 'agents', 'pdfer', 'pdfer.py')
    spec = importlib.util.spec_from_file_location(
        'agent_pdfer_module_for_tests', module_path,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f'Unable to load PDFer module from {module_path}')

    module = importlib.util.module_from_spec(spec)
    root = logging.getLogger()
    handlers_before = list(root.handlers)
    current_dir = os.getcwd()
    try:
        spec.loader.exec_module(module)
    finally:
        os.chdir(current_dir)
        for handler in list(root.handlers):
            if handler not in handlers_before:
                root.removeHandler(handler)
    return module


@lru_cache(maxsize=1)
def _pdfer():
    return _load_pdfer_module()


class _LogCapture:
    """Capture root-logger messages. Forces level NOTSET so INFO records arrive.

    (The level pin is deliberate — a previously-shipped copy of this helper silently
    dropped every INFO record when another test had raised the root level, which made
    an INI_SECTION assertion pass vacuously.)
    """

    def __init__(self):
        self.records = []

    def __enter__(self):
        outer = self

        class _H(logging.Handler):
            def emit(self, record):
                outer.records.append(record.getMessage())

        self._handler = _H()
        self._handler.setLevel(logging.NOTSET)
        self._root = logging.getLogger()
        self._level_before = self._root.level
        self._root.setLevel(logging.INFO)
        self._root.addHandler(self._handler)
        return self

    def __exit__(self, *_a):
        self._root.removeHandler(self._handler)
        self._root.setLevel(self._level_before)
        return False


def _parse_section(text, agent_type='PDFER'):
    """Parser mirroring parametrizer's INI_SECTION contract (KV header, blank line, body)."""
    tag = re.escape(agent_type.upper())
    match = re.search(
        r'INI_SECTION_' + tag + r'<<<\s*\n(?P<content>.*?)\n\s*>>>END_SECTION_' + tag,
        text, re.DOTALL,
    )
    if not match:
        return None
    content = match.group('content')
    header, _, body = content.partition('\n\n')
    fields = {}
    for line in header.splitlines():
        if ': ' in line:
            key, _, value = line.partition(': ')
            fields[key.strip()] = value.strip()
        elif line.strip().endswith(':'):
            fields[line.strip()[:-1]] = ''
    fields['response_body'] = body
    return fields


def _write_png(path, size=(120, 90), color=(200, 40, 40)):
    """Write a REAL png with Pillow (already a hard dependency of Tlamatini)."""
    from PIL import Image
    Image.new('RGB', size, color).save(path, 'PNG')
    return path


def _page_count(path):
    from pypdf import PdfReader
    return len(PdfReader(path).pages)


def _run_main(module, config, cwd):
    """Run main() in *cwd* against *config*, returning (records, SystemExit code)."""
    config_path = os.path.join(cwd, 'config.yaml')
    with open(config_path, 'w', encoding='utf-8') as f:
        yaml.dump(config, f, allow_unicode=True, sort_keys=False)
    before = os.getcwd()
    os.chdir(cwd)
    try:
        with _LogCapture() as cap:
            try:
                module.main()
                code = 0
            except SystemExit as exc:
                code = exc.code
        return cap.records, code
    finally:
        os.chdir(before)


# ---------------------------------------------------------------------------
# Coercion helpers
# ---------------------------------------------------------------------------


class PdferCoercionTests(SimpleTestCase):

    def test_as_int_extracts_leading_number_from_wrapped_parser_strings(self):
        m = _pdfer()
        # This is the real bug class that bit Recorder's record_seconds: the wrapped
        # Multi-Turn parser hands a sentence where the canvas hands an int.
        self.assertEqual(m._as_int('18 mm margins', 99), 18)
        self.assertEqual(m._as_int('  1600px  ', 0), 1600)
        self.assertEqual(m._as_int(-4, 0), -4)
        self.assertEqual(m._as_int('grid of 2 columns', 5), 2)

    def test_as_int_never_raises_and_falls_back(self):
        m = _pdfer()
        for junk in (None, '', 'no digits here', object(), [], {}):
            self.assertEqual(m._as_int(junk, 7), 7)
        # A bool must NOT be silently read as 0/1 page margins.
        self.assertEqual(m._as_int(True, 7), 7)

    def test_as_bool_matrix(self):
        m = _pdfer()
        for truthy in (True, 'true', 'TRUE', ' Yes ', '1', 'on'):
            self.assertIs(m._as_bool(truthy, False), True, truthy)
        for falsy in (False, 'false', 'No', '0', 'off', ''):
            self.assertIs(m._as_bool(falsy, True), False, falsy)
        self.assertIs(m._as_bool('maybe', True), True)
        self.assertIs(m._as_bool(None, False), False)

    def test_as_list_accepts_every_shape_the_two_surfaces_produce(self):
        m = _pdfer()
        # canvas writes a real YAML list; the wrapped chat tool writes one string
        self.assertEqual(m._as_list(['a.png', 'b.png']), ['a.png', 'b.png'])
        self.assertEqual(m._as_list('a.png, b.png'), ['a.png', 'b.png'])
        self.assertEqual(m._as_list('a.png;b.png\nc.png'), ['a.png', 'b.png', 'c.png'])
        self.assertEqual(m._as_list('["a.png", "b.png"]'), ['a.png', 'b.png'])
        self.assertEqual(m._as_list('solo.png'), ['solo.png'])
        for empty in (None, '', '   ', [], '[]'):
            self.assertEqual(m._as_list(empty), [], empty)


# ---------------------------------------------------------------------------
# Content sniffing (what makes mode='auto' work)
# ---------------------------------------------------------------------------


class PdferSniffTests(SimpleTestCase):

    def test_looks_like_html_recognizes_tlamatini_own_answers(self):
        m = _pdfer()
        # prompt.pmt Rule 6 makes Tlamatini emit HTML tables — that is the exact
        # shape "turn your last answer into a PDF" has to detect.
        answer = '<table><thead><tr><th>Agent</th></tr></thead><tbody></tbody></table>'
        self.assertTrue(m._looks_like_html(answer))
        self.assertTrue(m._looks_like_html('<h1>Title</h1><p>Body</p>'))

    def test_looks_like_html_is_not_fooled_by_markdown_or_prose(self):
        m = _pdfer()
        self.assertFalse(m._looks_like_html('# Title\n\n| a | b |\n|---|---|\n'))
        self.assertFalse(m._looks_like_html('use a <b> tag'))   # one tag is not a doc
        self.assertFalse(m._looks_like_html('2 < 3 and 5 > 4'))
        self.assertFalse(m._looks_like_html(''))

    def test_sniff_mode_matrix(self):
        m = _pdfer()
        cfg = {}
        self.assertEqual(m._sniff_mode(cfg, '# md', '', [], []), 'markdown')
        self.assertEqual(m._sniff_mode(cfg, '<h1>x</h1><p>y</p>', '', [], []), 'html')
        self.assertEqual(m._sniff_mode(cfg, 'text', '', ['a.png'], []), 'mixed')
        self.assertEqual(m._sniff_mode(cfg, '', '', ['a.png'], []), 'images')
        self.assertEqual(m._sniff_mode(cfg, 'x', '', [], ['a.pdf']), 'merge')
        # an .html input_file wins even when the body has few tags
        self.assertEqual(m._sniff_mode(cfg, 'plain', 'html', [], []), 'html')
        self.assertEqual(m._sniff_mode(cfg, '', '', [], []), 'markdown')


# ---------------------------------------------------------------------------
# Output path resolution
# ---------------------------------------------------------------------------


class PdferOutputPathTests(SimpleTestCase):

    def test_default_output_dir_is_documents_tlamatinipdf(self):
        m = _pdfer()
        resolved = m._default_output_dir({})
        self.assertTrue(resolved.endswith(os.path.join('Documents', 'TlamatiniPDF'))
                        or resolved.endswith('TlamatiniPDF'),
                        f'unexpected default output dir: {resolved}')

    def test_explicit_output_dir_is_honored_and_absolute(self):
        m = _pdfer()
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(m._default_output_dir({'output_dir': tmp}), os.path.abspath(tmp))

    def test_generated_filename_is_timestamped_pdf(self):
        m = _pdfer()
        with tempfile.TemporaryDirectory() as tmp:
            path = m._resolve_output_path({'output_dir': tmp})
            self.assertTrue(path.lower().endswith('.pdf'))
            self.assertRegex(os.path.basename(path), r'^pdfer_\d{8}_\d{6}_\d{3}\.pdf$')

    def test_pdf_extension_is_appended_when_missing(self):
        m = _pdfer()
        with tempfile.TemporaryDirectory() as tmp:
            path = m._resolve_output_path({'output_dir': tmp, 'filename': 'report'})
            self.assertEqual(os.path.basename(path), 'report.pdf')

    def test_collision_proof_sequence_never_clobbers(self):
        m = _pdfer()
        with tempfile.TemporaryDirectory() as tmp:
            cfg = {'output_dir': tmp, 'filename': 'r.pdf'}
            first = m._resolve_output_path(cfg)
            open(first, 'wb').close()
            second = m._resolve_output_path(cfg)
            open(second, 'wb').close()
            third = m._resolve_output_path(cfg)
            self.assertEqual(os.path.basename(first), 'r.pdf')
            self.assertEqual(os.path.basename(second), 'r_2.pdf')
            self.assertEqual(os.path.basename(third), 'r_3.pdf')

    def test_overwrite_true_reuses_the_same_path(self):
        m = _pdfer()
        with tempfile.TemporaryDirectory() as tmp:
            cfg = {'output_dir': tmp, 'filename': 'r.pdf', 'overwrite': True}
            first = m._resolve_output_path(cfg)
            open(first, 'wb').close()
            self.assertEqual(m._resolve_output_path(cfg), first)

    def test_filename_cannot_escape_the_output_dir(self):
        m = _pdfer()
        with tempfile.TemporaryDirectory() as tmp:
            for evil in ('../../escaped.pdf', r'..\..\escaped.pdf',
                         os.path.join('sub', 'nested.pdf')):
                path = m._resolve_output_path({'output_dir': tmp, 'filename': evil})
                self.assertEqual(
                    os.path.dirname(os.path.abspath(path)), os.path.abspath(tmp),
                    f'{evil!r} escaped the output dir -> {path}',
                )


# ---------------------------------------------------------------------------
# REAL rendering (no fakes — these produce genuine PDFs)
# ---------------------------------------------------------------------------


class PdferRealRenderTests(SimpleTestCase):

    def test_every_backend_imports(self):
        # PDFer's core promise is "zero new dependencies". If this fails on a build
        # machine, the carried Python is missing a lib and pool runs would degrade.
        backends = _pdfer()._probe_backends()
        missing = sorted(name for name, ok in backends.items() if not ok)
        self.assertEqual(missing, [], f'PDF backends missing from this interpreter: {missing}')

    def test_markdown_render_produces_a_readable_pdf_with_a_cover(self):
        m = _pdfer()
        with tempfile.TemporaryDirectory() as tmp:
            out = os.path.join(tmp, 'md.pdf')
            body = m._markdown_to_html_body(
                '# Title\n\nSome **bold** text.\n\n| a | b |\n|---|---|\n| 1 | 2 |\n', False)
            self.assertIn('<table>', body)       # the markdown `tables` extension ran
            doc = m._build_html_document(body, {'title': 'Cover', 'page_size': 'A4'})
            # 3-tuple since 2026-08-12: the third value is how many images the
            # FINISHED pdf contains (see PdferLocalAssetResolutionTests).
            ok, message, _embedded = m._render_html_to_pdf(doc, out)
            self.assertTrue(ok, message)
            self.assertTrue(os.path.isfile(out))
            # cover page forces a break, so a titled document is at least 2 pages
            self.assertGreaterEqual(_page_count(out), 2)

    def test_text_mode_escapes_and_never_reinterprets_markup(self):
        m = _pdfer()
        raw = '<script>alert(1)</script> & 5 < 6'
        escaped = m._text_to_html_body(raw)
        self.assertIn('&lt;script&gt;', escaped)
        self.assertNotIn('<script>', escaped)

    def test_page_css_honors_size_orientation_margin_and_page_numbers(self):
        m = _pdfer()
        css = m._page_css({'page_size': 'Letter', 'orientation': 'landscape',
                           'margins_mm': 25, 'page_numbers': True})
        self.assertIn('size: letter landscape;', css)
        self.assertIn('margin: 25mm;', css)
        self.assertIn('tlm_footer_frame', css)
        no_numbers = m._page_css({'page_numbers': False})
        self.assertNotIn('tlm_footer_frame', no_numbers)
        # an unknown page size must degrade to A4, not blow up
        self.assertIn('size: A4', m._page_css({'page_size': 'Tabloid'}))

    def test_images_render_all_three_layouts(self):
        m = _pdfer()
        with tempfile.TemporaryDirectory() as tmp:
            imgs = [_write_png(os.path.join(tmp, f'i{n}.png')) for n in range(3)]
            for layout, expected_pages in (('one-per-page', 3), ('fit', 3), ('grid', 1)):
                out = os.path.join(tmp, f'{layout}.pdf')
                ok, message, used = m._render_images_to_pdf(
                    imgs, out, {'image_layout': layout, 'grid_columns': 2})
                self.assertTrue(ok, message)
                self.assertEqual(used, 3)
                self.assertEqual(_page_count(out), expected_pages,
                                 f'{layout} produced the wrong page count')

    def test_fit_layout_sizes_each_page_to_its_own_image(self):
        # Regression guard: an earlier draft opened the raster with fitz.open() and read
        # [0].rect, which silently produced A4-shaped pages for every image.
        m = _pdfer()
        with tempfile.TemporaryDirectory() as tmp:
            wide = _write_png(os.path.join(tmp, 'wide.png'), size=(400, 100))
            out = os.path.join(tmp, 'fit.pdf')
            ok, _msg, _used = m._render_images_to_pdf(
                [wide], out, {'image_layout': 'fit', 'max_image_px': 0})
            self.assertTrue(ok)
            import fitz
            with fitz.open(out) as doc:
                rect = doc[0].rect
            self.assertGreater(rect.width, rect.height, 'a wide image must yield a wide page')

    def test_images_skips_missing_paths_but_still_renders_the_rest(self):
        m = _pdfer()
        with tempfile.TemporaryDirectory() as tmp:
            good = _write_png(os.path.join(tmp, 'good.png'))
            out = os.path.join(tmp, 'partial.pdf')
            ok, message, used = m._render_images_to_pdf(
                [good, os.path.join(tmp, 'ghost.png')], out, {})
            self.assertTrue(ok)
            self.assertEqual(used, 1)
            self.assertIn('missing', message)

    def test_images_refuses_when_nothing_exists(self):
        m = _pdfer()
        with tempfile.TemporaryDirectory() as tmp:
            ok, message, used = m._render_images_to_pdf(
                [os.path.join(tmp, 'ghost.png')], os.path.join(tmp, 'x.pdf'), {})
            self.assertFalse(ok)
            self.assertEqual(used, 0)
            self.assertIn('exist', message)

    def test_normalize_image_downscales_into_the_temp_root(self):
        m = _pdfer()
        with tempfile.TemporaryDirectory() as tmp:
            big = _write_png(os.path.join(tmp, 'big.png'), size=(900, 600))
            os.environ['TLAMATINI_TEMP'] = tmp
            try:
                staged = m._normalize_image(big, 100)
            finally:
                os.environ.pop('TLAMATINI_TEMP', None)
            self.assertNotEqual(staged, big)
            from PIL import Image
            with Image.open(staged) as im:
                self.assertLessEqual(max(im.size), 100)
            # Temp policy: the staged file must live under <app>/Temp, never elsewhere
            self.assertTrue(os.path.abspath(staged).startswith(os.path.abspath(tmp)))

    def test_normalize_image_is_a_noop_when_disabled_or_unreadable(self):
        m = _pdfer()
        with tempfile.TemporaryDirectory() as tmp:
            img = _write_png(os.path.join(tmp, 'a.png'))
            self.assertEqual(m._normalize_image(img, 0), img)
            ghost = os.path.join(tmp, 'ghost.png')
            self.assertEqual(m._normalize_image(ghost, 100), ghost)

    def test_merge_appends_every_readable_pdf(self):
        m = _pdfer()
        with tempfile.TemporaryDirectory() as tmp:
            sources = []
            for n in range(2):
                src = os.path.join(tmp, f's{n}.pdf')
                m._render_images_to_pdf([_write_png(os.path.join(tmp, f'p{n}.png'))],
                                        src, {'image_layout': 'one-per-page'})
                sources.append(src)
            out = os.path.join(tmp, 'merged.pdf')
            ok, message = m._merge_pdfs(sources, out)
            self.assertTrue(ok, message)
            self.assertEqual(_page_count(out), 2)

    def test_merge_reports_and_survives_a_bad_source(self):
        m = _pdfer()
        with tempfile.TemporaryDirectory() as tmp:
            good = os.path.join(tmp, 'g.pdf')
            m._render_images_to_pdf([_write_png(os.path.join(tmp, 'p.png'))], good, {})
            junk = os.path.join(tmp, 'junk.pdf')
            with open(junk, 'w', encoding='utf-8') as f:
                f.write('not a pdf at all')
            ok, message = m._merge_pdfs([good, junk, os.path.join(tmp, 'ghost.pdf')],
                                        os.path.join(tmp, 'out.pdf'))
            self.assertTrue(ok, 'one good source must still produce a merge')
            self.assertIn('skipped', message)

    def test_merge_fails_cleanly_when_nothing_is_readable(self):
        m = _pdfer()
        with tempfile.TemporaryDirectory() as tmp:
            ok, message = m._merge_pdfs([os.path.join(tmp, 'ghost.pdf')],
                                        os.path.join(tmp, 'out.pdf'))
            self.assertFalse(ok)
            self.assertIn('no readable PDF', message)

    def test_metadata_is_stamped_and_readable_back(self):
        m = _pdfer()
        with tempfile.TemporaryDirectory() as tmp:
            out = os.path.join(tmp, 'meta.pdf')
            m._render_images_to_pdf([_write_png(os.path.join(tmp, 'p.png'))], out, {})
            m._stamp_metadata(out, {'title': 'My Doc', 'author': 'Angela López Mendoza'})
            from pypdf import PdfReader
            meta = PdfReader(out).metadata
            self.assertEqual(meta.get('/Title'), 'My Doc')
            self.assertEqual(meta.get('/Author'), 'Angela López Mendoza')
            self.assertEqual(meta.get('/Producer'), 'Tlamatini PDFer')

    def test_pdf_info_reports_pages_bytes_and_metadata(self):
        m = _pdfer()
        with tempfile.TemporaryDirectory() as tmp:
            out = os.path.join(tmp, 'i.pdf')
            m._render_images_to_pdf([_write_png(os.path.join(tmp, 'p.png'))], out, {})
            ok, body = m._pdf_info(out)
            self.assertTrue(ok)
            self.assertIn('pages      : 1', body)
            self.assertIn('bytes', body)

    def test_pdf_info_on_a_missing_file_is_reported_not_raised(self):
        m = _pdfer()
        ok, body = m._pdf_info(os.path.join(tempfile.gettempdir(), 'definitely_absent.pdf'))
        self.assertFalse(ok)
        self.assertIn('No such PDF', body)

    def test_page_count_returns_zero_for_a_non_pdf(self):
        m = _pdfer()
        with tempfile.TemporaryDirectory() as tmp:
            junk = os.path.join(tmp, 'junk.pdf')
            with open(junk, 'w', encoding='utf-8') as f:
                f.write('nope')
            self.assertEqual(m._pdf_page_count(junk), 0)


# ---------------------------------------------------------------------------
# Fail-safe preflight
# ---------------------------------------------------------------------------


class PdferPreflightTests(SimpleTestCase):

    def setUp(self):
        self.backends = _pdfer()._probe_backends()

    def _pf(self, mode, config=None, text='', images=(), pdfs=()):
        return _pdfer()._preflight(mode, config or {}, text, list(images), list(pdfs),
                                   self.backends)

    def test_unknown_mode_is_refused(self):
        pf = self._pf('teleport')
        self.assertFalse(pf['ok'])
        self.assertIn('Unknown mode', pf['fatals'][0])

    def test_empty_content_is_refused_rather_than_writing_an_empty_pdf(self):
        with tempfile.TemporaryDirectory() as tmp:
            for mode in ('markdown', 'html', 'text'):
                pf = self._pf(mode, {'output_dir': tmp}, text='   ')
                self.assertFalse(pf['ok'], mode)
                self.assertTrue(any('needs content' in f for f in pf['fatals']), mode)

    def test_images_and_merge_need_their_inputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertFalse(self._pf('images', {'output_dir': tmp})['ok'])
            self.assertFalse(self._pf('merge', {'output_dir': tmp})['ok'])
            self.assertFalse(self._pf('mixed', {'output_dir': tmp})['ok'])

    def test_info_needs_an_existing_file(self):
        self.assertFalse(self._pf('info')['ok'])
        self.assertFalse(self._pf('info', {'input_file': '/nope/none.pdf'})['ok'])

    def test_validate_always_passes_and_writes_nothing(self):
        self.assertTrue(self._pf('validate')['ok'])

    def test_missing_input_file_is_fatal_when_there_is_no_inline_text(self):
        with tempfile.TemporaryDirectory() as tmp:
            pf = self._pf('markdown', {'output_dir': tmp, 'input_file': '/nope/x.md'})
            self.assertFalse(pf['ok'])

    def test_unwritable_output_dir_is_refused(self):
        # A path whose parent is a FILE can never be created as a directory.
        #
        # ⚠️ ASSERT THE CONTRACT, NOT THE SENTENCE (Angela, 2026-08-16). This
        # used to require the literal words 'not writable'. The OneDrive fix
        # then rewrote the blocker to say what the user can DO about it
        # ("output_dir cannot accept a new file (...) — a paused or erroring
        # OneDrive ... does exactly that"), because "the directory exists" and
        # os.access both LIE and only a real create proves anything. The
        # message got strictly better and the test went red: a FALSE failure on
        # a fixed subsystem. What actually matters is that the refusal is
        # ATTRIBUTED to output_dir, so the user knows which knob to turn.
        with tempfile.TemporaryDirectory() as tmp:
            blocker = os.path.join(tmp, 'blocker')
            with open(blocker, 'w', encoding='utf-8') as f:
                f.write('x')
            pf = self._pf('markdown', {'output_dir': os.path.join(blocker, 'sub')},
                          text='# hi')
            self.assertFalse(pf['ok'])
            self.assertTrue(
                any('output_dir' in f for f in pf['fatals']),
                f"the blocker must name output_dir so the user knows what to "
                f"change; got {pf['fatals']!r}")

    def test_missing_paths_and_odd_page_size_are_warnings_not_blockers(self):
        with tempfile.TemporaryDirectory() as tmp:
            good = _write_png(os.path.join(tmp, 'g.png'))
            pf = self._pf('images', {'output_dir': tmp, 'page_size': 'Tabloid'},
                          images=[good, os.path.join(tmp, 'ghost.png')])
            self.assertTrue(pf['ok'])
            self.assertTrue(any('image not found' in w for w in pf['warnings']))
            self.assertTrue(any('page_size' in w for w in pf['warnings']))

    def test_report_formatter_lists_blockers_and_warnings(self):
        text = _pdfer()._format_preflight_report({'fatals': ['boom'], 'warnings': ['meh']})
        self.assertIn('BLOCKERS:', text)
        self.assertIn('boom', text)
        self.assertIn('WARNINGS:', text)
        self.assertEqual(_pdfer()._format_preflight_report({}), '(no findings)')


# ---------------------------------------------------------------------------
# INI_SECTION emission + main() end-stage
# ---------------------------------------------------------------------------


class PdferSectionTests(SimpleTestCase):

    def test_section_is_one_atomic_record_and_round_trips(self):
        m = _pdfer()
        fields = {'mode': 'markdown', 'status': 'created', 'page_count': 3}
        with _LogCapture() as cap:
            m._emit_section(fields, 'the body\nspans lines')
        blocks = [r for r in cap.records if 'INI_SECTION_PDFER<<<' in r]
        # ATOMIC: exactly ONE logging record carries the whole block, so concurrent
        # writers cannot interleave and corrupt it.
        self.assertEqual(len(blocks), 1)
        self.assertIn('>>>END_SECTION_PDFER', blocks[0])
        parsed = _parse_section(blocks[0])
        self.assertEqual(parsed['mode'], 'markdown')
        self.assertEqual(parsed['status'], 'created')
        self.assertEqual(parsed['page_count'], '3')
        self.assertEqual(parsed['response_body'], 'the body\nspans lines')

    def test_section_field_names_match_the_registered_parametrizer_contract(self):
        from agent.services.agent_contracts import _PARAMETRIZER_OUTPUT_FIELDS
        m = _pdfer()
        with tempfile.TemporaryDirectory() as tmp:
            records, _ = _run_main(m, {
                'mode': 'markdown', 'input_text': '# hi', 'output_dir': tmp,
                'filename': 'a.pdf', 'target_agents': [],
            }, tmp)
        block = next(r for r in records if 'INI_SECTION_PDFER<<<' in r)
        emitted = set(_parse_section(block)) - {'response_body'}
        registered = set(_PARAMETRIZER_OUTPUT_FIELDS['pdfer']) - {'response_body'}
        self.assertEqual(
            emitted, registered,
            'the emitted KV header drifted from _PARAMETRIZER_OUTPUT_FIELDS["pdfer"]\n'
            f'  emitted not registered : {sorted(emitted - registered)}\n'
            f'  registered not emitted : {sorted(registered - emitted)}',
        )


class PdferMainTests(SimpleTestCase):

    def test_main_creates_the_pdf_and_reports_created(self):
        m = _pdfer()
        with tempfile.TemporaryDirectory() as tmp:
            records, code = _run_main(m, {
                'mode': 'markdown',
                'input_text': '# Report\n\n| a | b |\n|---|---|\n| 1 | 2 |\n',
                'title': 'T', 'output_dir': tmp, 'filename': 'r.pdf',
                'target_agents': [],
            }, tmp)
            # NOTE: assert INSIDE the with — the temp dir (and the PDF) is gone after it.
            self.assertEqual(code, 0)
            fields = _parse_section(next(r for r in records if 'INI_SECTION_PDFER<<<' in r))
            self.assertEqual(fields['status'], 'created')
            self.assertEqual(fields['engine'], 'xhtml2pdf')
            self.assertEqual(fields['source_type'], 'text')
            self.assertTrue(os.path.isfile(fields['output_path']))
            self.assertGreater(int(fields['page_count']), 0)
            self.assertGreater(int(fields['bytes']), 0)

    def test_main_auto_mode_resolves_html_for_a_tlamatini_answer(self):
        m = _pdfer()
        with tempfile.TemporaryDirectory() as tmp:
            records, _ = _run_main(m, {
                'mode': 'auto',
                'input_text': '<h2>Answer</h2><table><tr><td>x</td></tr></table>',
                'output_dir': tmp, 'filename': 'a.pdf', 'target_agents': [],
            }, tmp)
        fields = _parse_section(next(r for r in records if 'INI_SECTION_PDFER<<<' in r))
        self.assertEqual(fields['mode'], 'html')
        self.assertEqual(fields['status'], 'created')

    def test_main_validate_writes_no_file(self):
        m = _pdfer()
        with tempfile.TemporaryDirectory() as tmp:
            records, _ = _run_main(m, {'mode': 'validate', 'output_dir': tmp,
                                       'target_agents': []}, tmp)
            self.assertEqual([f for f in os.listdir(tmp) if f.endswith('.pdf')], [])
        fields = _parse_section(next(r for r in records if 'INI_SECTION_PDFER<<<' in r))
        self.assertEqual(fields['status'], 'validated')
        self.assertIn('xhtml2pdf', fields['response_body'])

    def test_main_refuses_empty_content_and_still_emits_a_routable_section(self):
        m = _pdfer()
        with tempfile.TemporaryDirectory() as tmp:
            records, code = _run_main(m, {'mode': 'markdown', 'input_text': '',
                                          'output_dir': tmp, 'target_agents': []}, tmp)
            self.assertEqual([f for f in os.listdir(tmp) if f.endswith('.pdf')], [])
        self.assertEqual(code, 0, 'a refusal must exit cleanly, never crash')
        fields = _parse_section(next(r for r in records if 'INI_SECTION_PDFER<<<' in r))
        self.assertEqual(fields['status'], 'refused')
        self.assertIn('PREFLIGHT REFUSED', fields['response_body'])

    def test_main_triggers_targets_on_success_AND_on_refusal(self):
        # The contract a downstream Forker relies on: target_agents fire either way,
        # so {status} can be branched on.
        m = _pdfer()
        for cfg_extra, expected in (({'input_text': '# ok'}, 'created'),
                                    ({'input_text': ''}, 'refused')):
            with tempfile.TemporaryDirectory() as tmp:
                calls = []
                real_start, real_wait = m.start_agent, m.wait_for_agents_to_stop
                m.start_agent = lambda name: (calls.append(name), True)[1]
                m.wait_for_agents_to_stop = lambda names: None
                try:
                    cfg = {'mode': 'markdown', 'output_dir': tmp, 'filename': 'x.pdf',
                           'target_agents': ['ender_1']}
                    cfg.update(cfg_extra)
                    records, _ = _run_main(m, cfg, tmp)
                finally:
                    m.start_agent, m.wait_for_agents_to_stop = real_start, real_wait
            fields = _parse_section(next(r for r in records if 'INI_SECTION_PDFER<<<' in r))
            self.assertEqual(fields['status'], expected)
            self.assertEqual(calls, ['ender_1'],
                             f'target_agents must fire on status={expected}')

    def test_main_images_mode_end_to_end(self):
        m = _pdfer()
        with tempfile.TemporaryDirectory() as tmp:
            imgs = ', '.join(_write_png(os.path.join(tmp, f'i{n}.png')) for n in range(2))
            records, _ = _run_main(m, {'mode': 'images', 'images': imgs,
                                       'output_dir': tmp, 'filename': 'al.pdf',
                                       'target_agents': []}, tmp)
        fields = _parse_section(next(r for r in records if 'INI_SECTION_PDFER<<<' in r))
        self.assertEqual(fields['status'], 'created')
        self.assertEqual(fields['engine'], 'pymupdf')
        self.assertEqual(fields['images_used'], '2')
        self.assertEqual(fields['source_type'], 'images')

    def test_main_info_mode_inspects_without_writing(self):
        m = _pdfer()
        with tempfile.TemporaryDirectory() as tmp:
            target = os.path.join(tmp, 'src.pdf')
            m._render_images_to_pdf([_write_png(os.path.join(tmp, 'p.png'))], target, {})
            records, _ = _run_main(m, {'mode': 'info', 'input_file': target,
                                       'target_agents': []}, tmp)
        fields = _parse_section(next(r for r in records if 'INI_SECTION_PDFER<<<' in r))
        self.assertEqual(fields['status'], 'inspected')
        self.assertEqual(fields['page_count'], '1')

    def test_main_reads_a_markdown_input_file(self):
        m = _pdfer()
        with tempfile.TemporaryDirectory() as tmp:
            src = os.path.join(tmp, 'doc.md')
            with open(src, 'w', encoding='utf-8') as f:
                f.write('# From a file\n\nHello.\n')
            records, _ = _run_main(m, {'mode': 'auto', 'input_file': src,
                                       'output_dir': tmp, 'filename': 'f.pdf',
                                       'target_agents': []}, tmp)
        fields = _parse_section(next(r for r in records if 'INI_SECTION_PDFER<<<' in r))
        self.assertEqual(fields['status'], 'created')
        self.assertEqual(fields['source_type'], 'file')
        self.assertEqual(fields['mode'], 'markdown')

    def test_main_unknown_mode_is_refused_not_crashed(self):
        m = _pdfer()
        with tempfile.TemporaryDirectory() as tmp:
            records, code = _run_main(m, {'mode': 'teleport', 'input_text': 'x',
                                          'output_dir': tmp, 'target_agents': []}, tmp)
        self.assertEqual(code, 0)
        fields = _parse_section(next(r for r in records if 'INI_SECTION_PDFER<<<' in r))
        self.assertEqual(fields['status'], 'refused')


class PdferOllamaPolishTests(SimpleTestCase):

    def test_unreachable_ollama_keeps_the_original_text(self):
        # The documented guarantee: a failed polish NEVER loses the document.
        m = _pdfer()
        original = '# Keep me\n\nEvery word.'
        polished, note = m._ollama_polish(original, {
            'ollama_url': 'http://127.0.0.1:9',      # discard port — always refused
            'ollama_model': 'nope', 'ollama_timeout': 2,
        })
        self.assertEqual(polished, original)
        self.assertIn('kept the raw content', note)

    def test_polish_is_skipped_when_unconfigured(self):
        m = _pdfer()
        polished, note = m._ollama_polish('body', {'ollama_url': '', 'ollama_model': ''})
        self.assertEqual(polished, 'body')
        self.assertIn('skipped', note)


class PdferReanimationTests(SimpleTestCase):

    def test_reanimated_flag_does_not_truncate_the_log(self):
        # Fresh start truncates; a resume must append. The marker is read at import
        # time, so the env var has to be set before the module is loaded.
        with tempfile.TemporaryDirectory() as tmp:
            agent_dir = os.path.join(tmp, 'pdfer_1')
            os.makedirs(agent_dir)
            src = os.path.join(_REPO_AGENT_DIR, 'agents', 'pdfer', 'pdfer.py')
            with open(src, 'r', encoding='utf-8') as f:
                source = f.read()
            copy = os.path.join(agent_dir, 'pdfer.py')
            with open(copy, 'w', encoding='utf-8') as f:
                f.write(source)
            log_path = os.path.join(agent_dir, 'pdfer_1.log')
            with open(log_path, 'w', encoding='utf-8') as f:
                f.write('PREVIOUS RUN LINE\n')

            os.environ['AGENT_REANIMATED'] = '1'
            root = logging.getLogger()
            handlers_before = list(root.handlers)
            before_cwd = os.getcwd()
            try:
                spec = importlib.util.spec_from_file_location('pdfer_reanim_test', copy)
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                self.assertTrue(module._IS_REANIMATED)
            finally:
                os.chdir(before_cwd)
                os.environ.pop('AGENT_REANIMATED', None)
                for h in list(root.handlers):
                    if h not in handlers_before:
                        root.removeHandler(h)
            with open(log_path, 'r', encoding='utf-8') as f:
                self.assertIn('PREVIOUS RUN LINE', f.read(),
                              'a reanimated start must NOT truncate the log')


# ---------------------------------------------------------------------------
# Registry / wiring integration
# ---------------------------------------------------------------------------


def _read(*parts):
    with open(os.path.join(*parts), 'r', encoding='utf-8') as f:
        return f.read()


class PdferRegistryIntegrationTests(SimpleTestCase):

    def test_wrapped_chat_agent_spec_is_registered(self):
        from agent.chat_agent_registry import WRAPPED_CHAT_AGENT_BY_TOOL_NAME
        spec = WRAPPED_CHAT_AGENT_BY_TOOL_NAME.get('chat_agent_pdfer')
        self.assertIsNotNone(spec, 'chat_agent_pdfer is not in the wrapped registry')
        self.assertEqual(spec.key, 'pdfer')
        self.assertEqual(spec.template_dir, 'pdfer')
        self.assertEqual(spec.tool_description, 'Chat-Agent-PDFer')
        # display_name MUST equal the DB agentDescription — the Agent-row enable gate
        # is keyed on agent_<display>_status.
        self.assertEqual(spec.display_name, 'PDFer')

    def test_display_name_casing_is_exactly_PDFer_everywhere_it_shows(self):
        from agent.chat_agent_registry import WRAPPED_CHAT_AGENT_BY_TOOL_NAME
        spec = WRAPPED_CHAT_AGENT_BY_TOOL_NAME['chat_agent_pdfer']
        for wrong in ('PDFEr', 'Pdfer', 'PDFER', 'pdfEr'):
            self.assertNotEqual(spec.display_name, wrong)
        migration = _read(_REPO_AGENT_DIR, 'migrations', '0188_add_pdfer.py')
        self.assertIn("agentDescription='PDFer'", migration)

    def test_agent_contract_resolves_with_the_right_display_name(self):
        from agent.services.agent_contracts import get_agent_contract
        contract = get_agent_contract('pdfer')
        self.assertEqual(contract.display_name, 'PDFer')

    def test_parametrizer_source_lists_are_identical_across_all_three_surfaces(self):
        from agent.services.agent_contracts import _PARAMETRIZER_OUTPUT_FIELDS
        from agent.views import PARAMETRIZER_SOURCE_OUTPUT_FIELDS
        registered = tuple(_PARAMETRIZER_OUTPUT_FIELDS['pdfer'])
        self.assertEqual(tuple(PARAMETRIZER_SOURCE_OUTPUT_FIELDS['pdfer']), registered)
        parametrizer = _read(_REPO_AGENT_DIR, 'agents', 'parametrizer', 'parametrizer.py')
        self.assertIn("'pdfer',", parametrizer,
                      "'pdfer' is missing from SECTION_AGENT_TYPES")
        for field in ('output_path', 'status', 'page_count', 'response_body'):
            self.assertIn(field, registered)

    def test_exec_report_membership_state_changing(self):
        # PDFer WRITES a file, so it must appear in the Exec Report.
        from agent.mcp_agent import _EXEC_REPORT_TOOLS, _resolve_exec_report_spec
        self.assertIn('chat_agent_pdfer', _EXEC_REPORT_TOOLS)
        self.assertEqual(_EXEC_REPORT_TOOLS['chat_agent_pdfer'], ('pdfer', 'PDFer'))
        self.assertEqual(_resolve_exec_report_spec('chat_agent_pdfer'), ('pdfer', 'PDFer'))

    def test_ask_execs_gates_pdfer_because_it_can_overwrite_a_file(self):
        from agent.mcp_agent import _ASK_EXECS_REQUIRED_TOOLS, _MANAGEMENT_TOOLS
        self.assertIn('chat_agent_pdfer', _ASK_EXECS_REQUIRED_TOOLS)
        self.assertNotIn('chat_agent_pdfer', _MANAGEMENT_TOOLS)

    def test_promote_section_fields_surface_the_output_path(self):
        from agent.tools import _PROMOTE_SECTION_FIELDS_BY_TEMPLATE_DIR
        promoted = _PROMOTE_SECTION_FIELDS_BY_TEMPLATE_DIR['pdfer']
        for field in ('output_path', 'status', 'page_count'):
            self.assertIn(field, promoted)

    def test_config_yaml_parses_and_carries_every_documented_key(self):
        raw = _read(_REPO_AGENT_DIR, 'agents', 'pdfer', 'config.yaml')
        config = yaml.safe_load(raw)
        for key in ('mode', 'input_text', 'input_file', 'images', 'input_pdfs', 'title',
                    'subtitle', 'author', 'page_size', 'orientation', 'margins_mm', 'css',
                    'toc', 'page_numbers', 'image_layout', 'image_caption', 'grid_columns',
                    'max_image_px', 'ollama_polish', 'ollama_url', 'ollama_model',
                    'ollama_token', 'output_dir', 'filename', 'overwrite', 'preflight',
                    'command_timeout', 'source_agents', 'target_agents'):
            self.assertIn(key, config, f'config.yaml is missing {key}')
        self.assertEqual(config['mode'], 'auto')
        self.assertIs(config['ollama_polish'], False, 'polish must default OFF')
        self.assertIs(config['overwrite'], False, 'PDFer must never clobber by default')
        self.assertEqual(config['output_dir'], '')
        self.assertEqual(config['ollama_token'], '', 'secrets default to an empty string')
        self.assertIsInstance(config['margins_mm'], int)
        self.assertEqual(config['target_agents'], [])

    def test_agent_never_imports_the_django_app(self):
        # Line-anchored on purpose: prose in the module docstring legitimately SAYS
        # "must never import agent.*", and a plain substring check would flag it.
        source = _read(_REPO_AGENT_DIR, 'agents', 'pdfer', 'pdfer.py')
        offenders = [
            line for line in source.splitlines()
            if re.match(r'\s*(from|import)\s+agent(\.|\s|$)', line)
        ]
        self.assertEqual(
            offenders, [],
            'a pool subprocess has no sys.path back into the Django app: ' f'{offenders}',
        )

    def test_agent_honors_the_temp_directory_policy(self):
        source = _read(_REPO_AGENT_DIR, 'agents', 'pdfer', 'pdfer.py')
        self.assertIn('TLAMATINI_TEMP', source)
        for forbidden in (r'C:\\Temp', 'gettempdir()'):
            self.assertNotIn(forbidden, source, f'{forbidden} violates the Temp policy')

    def test_css_gradient_exists_and_is_unique(self):
        css = _read(_REPO_AGENT_DIR, 'static', 'agent', 'css', 'agentic_control_panel.css')
        self.assertIn('.canvas-item.pdfer-agent {', css)
        self.assertIn('.canvas-item.pdfer-agent:hover {', css)
        gradient = 'linear-gradient(135deg, #2B0A0A 0%, #C1272D 33%, #E8A33D 66%, #FDF6E3 100%)'
        self.assertEqual(css.count(gradient), 1, 'the PDFer gradient collides with another agent')

    def test_exec_report_css_is_wired(self):
        css = _read(_REPO_AGENT_DIR, 'static', 'agent', 'css', 'agent_page.css')
        self.assertIn('.exec-report-caption-pdfer {', css)
        self.assertIn('.exec-report-pdfer thead th,', css)
        self.assertIn('.exec-report-pdfer .exec-report-cmd', css)

    def test_url_route_and_view_exist(self):
        from django.urls import reverse
        from agent import views
        self.assertTrue(hasattr(views, 'update_pdfer_connection_view'))
        self.assertEqual(reverse('update_pdfer_connection', args=['pdfer-1']),
                         '/agent/update_pdfer_connection/pdfer-1/')

    def test_every_javascript_surface_is_wired(self):
        js_dir = os.path.join(_REPO_AGENT_DIR, 'static', 'agent', 'js')
        connectors = _read(js_dir, 'acp-agent-connectors.js')
        self.assertIn('async function updatePdferConnection(', connectors)
        self.assertIn('/agent/update_pdfer_connection/', connectors)

        core = _read(js_dir, 'acp-canvas-core.js')
        self.assertIn("'pdfer': 'pdfer-agent',", core)          # classMap (HYPHEN form)
        # removeConnection / removeConnectionsFor / mouseup — all three SPACED-form spots
        self.assertEqual(core.count("=== 'pdfer'"), 3,
                         'acp-canvas-core.js must touch pdfer in exactly 3 connection spots')
        self.assertIn("updatePdferConnection(sourceId, targetId, 'add')", core)
        self.assertIn("updatePdferConnection(sourceId, targetId, 'remove')", core)

        undo = _read(js_dir, 'acp-canvas-undo.js')
        self.assertIn("updatePdferConnection(sourceId, targetId, 'remove')", undo)
        self.assertIn("updatePdferConnection(sourceId, targetId, 'add')", undo)

        file_io = _read(js_dir, 'acp-file-io.js')
        self.assertIn("case 'pdfer': await updatePdferConnection(", file_io)

        chat = _read(js_dir, 'agent_page_chat.js')
        self.assertIn("} else if (lower === 'pdfer') {", chat)
        for field in ('mode', 'input_text', 'images', 'title', 'output_dir', 'filename'):
            self.assertIn(f"set('{field}'", chat, f'flow-generator drops {field}')

    def test_eslint_knows_the_new_global(self):
        self.assertIn('updatePdferConnection: "readonly"',
                      _read(_REPO_ROOT, 'eslint.config.mjs'))

    def test_flow_generator_never_writes_connection_fields(self):
        chat = _read(_REPO_AGENT_DIR, 'static', 'agent', 'js', 'agent_page_chat.js')
        branch = chat.split("} else if (lower === 'pdfer') {", 1)[1].split('} else if', 1)[0]
        # _generateAndDownloadFlow owns these (with cardinal-suffixed pool names).
        self.assertNotIn('target_agents', branch)
        self.assertNotIn('source_agents', branch)

    def test_migrations_exist_and_chain(self):
        mig = os.path.join(_REPO_AGENT_DIR, 'migrations')
        for name in ('0188_add_pdfer.py', '0189_add_chat_agent_pdfer_tool.py',
                     '0190_add_pdfer_demo_prompts.py'):
            self.assertTrue(os.path.isfile(os.path.join(mig, name)), f'missing {name}')
        self.assertIn("'0187_add_flowcreator_end_to_end_wizard_prompt'",
                      _read(mig, '0188_add_pdfer.py'))
        self.assertIn('"0188_add_pdfer"', _read(mig, '0189_add_chat_agent_pdfer_tool.py'))
        self.assertIn("'0189_add_chat_agent_pdfer_tool'",
                      _read(mig, '0190_add_pdfer_demo_prompts.py'))
        self.assertIn('Chat-Agent-PDFer', _read(mig, '0189_add_chat_agent_pdfer_tool.py'))

    def test_new_documents_prompt_category_is_registered(self):
        from agent.views import PROMPT_CATEGORY_ORDER
        keys = [key for key, _label in PROMPT_CATEGORY_ORDER]
        self.assertIn('documents', keys)
        self.assertEqual(dict(PROMPT_CATEGORY_ORDER)['documents'], 'Documents & PDF')
        # 'other' must stay last so unranked/unknown categories still fall through it.
        self.assertEqual(keys[-1], 'other')

    def test_demo_prompts_cover_the_wizard_plus_at_least_three_samples(self):
        migration = _read(_REPO_AGENT_DIR, 'migrations', '0190_add_pdfer_demo_prompts.py')
        self.assertGreaterEqual(migration.count('chat_agent_pdfer'), 4)
        self.assertIn("'category': 'documents'", migration)
        self.assertIn("(109, 10, WIZARD)", migration)   # reserved rank-10 opener slot
        for pid in (110, 111, 112, 113):
            self.assertIn(f'({pid}, ', migration)

    def test_pdf_backends_are_pinned_and_build_verifies_them(self):
        requirements = _read(_REPO_ROOT, 'requirements.txt')
        for pin in ('markdown==', 'xhtml2pdf==', 'pymupdf==', 'reportlab==',
                    'pillow==', 'pypdf=='):
            self.assertIn(pin, requirements, f'{pin} is not pinned — PDFer would break')
        # The carried Python runs the pool agents, so the build must FAIL LOUDLY when a
        # backend is missing there (the numpy/cv2 lesson).
        build = _read(_REPO_ROOT, 'build.py')
        # Slice to the closing paren of the tuple ITSELF — an inline comment such as
        # "(all media agents)" contains a ')' that a naive split would stop at.
        agent_imports = build.split('_AGENT_RUNTIME_IMPORTS', 1)[1].split('\n)', 1)[0]
        for module in ('"markdown"', '"xhtml2pdf"', '"reportlab"', '"PIL"',
                       '"pypdf"', '"fitz"'):
            self.assertIn(module, agent_imports,
                          f'{module} missing from build.py _AGENT_RUNTIME_IMPORTS')


class PdferLocalAssetResolutionTests(unittest.TestCase):
    """A document that references a local image must CONTAIN that image.

    Angela, 2026-08-12. PDFer rendered a 4-diagram design document into a PDF
    with ZERO diagrams, logged ``Could not get image data from src attribute``
    as a warning, reported ``status: created`` — and handed over an
    illustrated report with every illustration missing. Silent, plausible and
    WRONG: the worst thing a document composer can do.

    Cause: ``pisa.CreatePDF`` was called with no ``link_callback``, so
    xhtml2pdf had no way to turn any of the three shapes a human actually
    writes — a ``file:///`` URL, a Windows absolute path, or a path relative
    to the Markdown file — into something it could open.

    These tests use REAL PNGs and re-read the REAL PDF with PyMuPDF, because
    the only trustworthy answer to "did the picture make it in?" is the file
    on disk.
    """

    @staticmethod
    def _png(path, size=(240, 160), color=(200, 40, 60)):
        from PIL import Image
        Image.new('RGB', size, color).save(path)
        return path

    def _render(self, md_text, workdir, name='doc.md'):
        pdfer = _pdfer()
        src = os.path.join(workdir, name)
        with open(src, 'w', encoding='utf-8') as handle:
            handle.write(md_text)
        out = os.path.join(workdir, 'out.pdf')
        body = pdfer._markdown_to_html_body(md_text, False)
        html = pdfer._build_html_document(body, {'title': 'T'}, '')
        ok, message, embedded = pdfer._render_html_to_pdf(
            html, out, base_dir=workdir)
        return ok, message, embedded, out

    def test_relative_absolute_and_file_url_all_resolve(self):
        pdfer = _pdfer()
        with tempfile.TemporaryDirectory() as workdir:
            png = self._png(os.path.join(workdir, 'fig.png'))
            forms = {
                'relative': 'fig.png',
                'absolute': png,
                'file-url': 'file:///' + png.replace('\\', '/'),
            }
            for label, ref in forms.items():
                resolved = pdfer._resolve_asset_uri(ref, workdir)
                self.assertTrue(
                    os.path.isfile(resolved),
                    f'{label} reference {ref!r} did not resolve to a real file '
                    f'(got {resolved!r}). This is exactly how the diagrams '
                    f'vanished from the design PDF.')
                self.assertEqual(os.path.normcase(resolved),
                                 os.path.normcase(png))

    def test_remote_and_data_uris_are_left_alone(self):
        """xhtml2pdf handles these natively — rewriting them would break them."""
        pdfer = _pdfer()
        for ref in ('https://example.com/a.png', 'http://x/y.png',
                    'data:image/png;base64,AAAA'):
            self.assertEqual(pdfer._resolve_asset_uri(ref, ''), ref)

    def test_missing_asset_degrades_and_never_raises(self):
        pdfer = _pdfer()
        with tempfile.TemporaryDirectory() as workdir:
            ref = 'does-not-exist.png'
            self.assertEqual(pdfer._resolve_asset_uri(ref, workdir), ref)
        for junk in ('', None, 'file:///nope/none.png'):
            pdfer._resolve_asset_uri(junk, '')      # must not raise

    def test_markdown_with_a_local_image_produces_a_pdf_containing_it(self):
        with tempfile.TemporaryDirectory() as workdir:
            self._png(os.path.join(workdir, 'fig.png'))
            ok, message, embedded, out = self._render(
                '# Title\n\nSome prose.\n\n![a figure](fig.png)\n', workdir)
            self.assertTrue(ok, message)
            self.assertTrue(os.path.isfile(out))
            self.assertEqual(
                embedded, 1,
                'the rendered PDF does not contain the referenced image')
            import fitz
            doc = fitz.open(out)
            try:
                found = sum(len(p.get_images(full=True)) for p in doc)
            finally:
                doc.close()
            self.assertEqual(found, 1, 'PyMuPDF found no image in the PDF')

    def test_reported_images_used_is_measured_from_the_pdf(self):
        """``images_used`` must describe the FILE, not our intentions.

        Reporting 0 for a document that had four diagrams is what let a broken
        render pass for a good one — the same 'the self-report must be true'
        rule the Exec-Report verdict engine enforces.
        """
        pdfer = _pdfer()
        with tempfile.TemporaryDirectory() as workdir:
            self._png(os.path.join(workdir, 'a.png'), color=(10, 90, 200))
            self._png(os.path.join(workdir, 'b.png'), color=(20, 160, 90))
            _ok, _msg, embedded, out = self._render(
                '# T\n\n![a](a.png)\n\n![b](b.png)\n', workdir)
            self.assertEqual(embedded, 2)
            self.assertGreaterEqual(pdfer._count_pdf_images(out), 2)

    def test_count_pdf_images_is_fail_open(self):
        pdfer = _pdfer()
        self.assertEqual(pdfer._count_pdf_images('C:\\nope\\missing.pdf'), -1)

    def test_render_passes_a_link_callback(self):
        """The source contract: without it, nothing above can work."""
        source = _read(_REPO_AGENT_DIR, 'agents', 'pdfer', 'pdfer.py')
        block = source.split('def _render_html_to_pdf', 1)[1].split('\ndef ', 1)[0]
        self.assertIn('link_callback=link_callback', block,
                      'pisa.CreatePDF lost its link_callback — every local '
                      'image in every generated document silently disappears.')


if __name__ == '__main__':
    unittest.main()
