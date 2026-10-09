# ═══════════════════════════════════════════════════════════════════════════
#   ✦  T L A M A T I N I  ✦   —   "one who knows"
#
#   Created by  Angela López Mendoza   ·   @angelahack1
#   Developer · Architect · Creator of Tlamatini
# ═══════════════════════════════════════════════════════════════════════════
#   Tlamatini Author Banner — do not remove (releases scrub the name automatically)
"""CONSOLE COLOURS - the window is painted by level, the log file never is (Angela, 2026-10-08).

Angela: "make the log to be rendered with multicolor depending on debug, info, warn,
error, fatals". Three pieces of manage.py are under test:

  * ``_ConsoleColorizer`` paints the CONSOLE copy, on the console drain thread;
  * ``_TeeStream._plain`` keeps every colour code out of tlamatini.log, including the
    codes Django prints into its own access log;
  * ``_enable_console_colors`` / ``_console_vt_on`` decide whether a console can render
    colour at all, and never take anything away from it.

manage.py cannot be imported in a test (it installs the log tee at import time), so
the classes are lifted out of it with ``ast`` - the same trick test_console_shield.py
uses - and the two functions are checked as source.

Run:
    python Tlamatini/manage.py test agent.test_console_colors
    python -m unittest agent.test_console_colors      # Django-free too
"""
import ast
import collections
import json
import os
import sys
import tempfile
import threading
import time
import unittest

#   <repo>/Tlamatini/agent/test_console_colors.py  ->  <repo>/Tlamatini
_PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_MANAGE_PY = os.path.join(_PROJECT_DIR, 'manage.py')
_CONFIG_JSON = os.path.join(_PROJECT_DIR, 'agent', 'config.json')

ESC = chr(27)
CROSS = chr(0x274C)           # red cross mark
WARNING_SIGN = chr(0x26A0)
TICK = chr(0x2705)            # green check mark


def _read(path):
    with open(path, 'r', encoding='utf-8') as fh:
        return fh.read()


def _lift():
    """Exec ONLY the three console classes out of manage.py - never import it."""
    tree = ast.parse(_read(_MANAGE_PY), filename=_MANAGE_PY)
    picked = [
        node for node in tree.body
        if isinstance(node, ast.ClassDef)
        and node.name in ('_ConsoleWriter', '_ConsoleColorizer', '_TeeStream')
    ]
    namespace = {
        'collections': collections, 'threading': threading, 'time': time,
        'os': os, 'sys': sys, '_USER_TAG_HOOK': None,
    }
    exec(compile(ast.Module(body=picked, type_ignores=[]), _MANAGE_PY, 'exec'), namespace)  # noqa: S102
    return namespace


_NS = _lift()
Colorizer = _NS['_ConsoleColorizer']
ConsoleWriter = _NS['_ConsoleWriter']
TeeStream = _NS['_TeeStream']

RESET = Colorizer.RESET
RED = Colorizer.STYLES['error']
FATAL = Colorizer.STYLES['fatal']
YELLOW = Colorizer.STYLES['warning']
GREEN = Colorizer.STYLES['success']
GREY = Colorizer.STYLES['debug']
CYAN = Colorizer.TAG_STYLE
MAGENTA = Colorizer.USER_STYLE


def strip_codes(text):
    """Remove every ESC[...m code (written without a regex on purpose)."""
    out = []
    i = 0
    while i < len(text):
        if text[i] == ESC:
            i = text.index('m', i) + 1
            continue
        out.append(text[i])
        i += 1
    return ''.join(out)


class _Console:
    """A console window that answers instantly and records what it was given."""

    def __init__(self):
        self.written = []

    def write(self, text):
        self.written.append(text)
        return len(text)

    def flush(self):
        pass

    def text(self):
        return ''.join(self.written)


# A realistic slice of a Tlamatini console, used by the whole-corpus tests.
CORPUS = [
    '--- [CONSOLE-SHIELD] Console writes are queued on a drain thread',
    '2026-10-08 18:47:13 [django.channels.server] INFO ' + ESC + '[32mHTTP POST / 302 [0.68, 127.0.0.1:49905]' + ESC + '[0m',
    '[a3] --- [MODEL-BRAIN] model=glm-5.3:cloud | sampling: temperature=1.0, top_p=0.95',
    '[a3] --- [CONTEXT-REAL] prompt_eval_count=98870 eval_count=3277 | estimate 104683 (+5.88%)',
    '2026-10-08 18:49:19,347 - INFO - ' + TICK + ' 25 match(es) across 1 file(s)',
    '2026-10-08 18:49:19,347 - ERROR - boom',
    '2026-10-08 18:49:19,347 - WARNING - careful',
    '2026-10-08 18:49:19,347 - DEBUG - detail',
    '2026-10-08 18:49:19,347 - CRITICAL - disk full',
    'Traceback (most recent call last):',
    '  File "C:/x/y.py", line 3, in <module>',
    '    boom()',
    'ValueError: bad value',
    "--- Message parsed: 'fix the ERROR in my code' **** to be sent to LLM",
    'HTTP GET /agent/x 500 [0.36, 127.0.0.1:1]',
    'HTTP GET /missing 404 [0.01, 127.0.0.1:1]',
    'Watching for file changes with StatReloader',
    '',
    'OK',
]


class PaintTests(unittest.TestCase):
    """What each kind of line looks like in the window."""

    def setUp(self):
        self.console = _Console()
        self.painter = Colorizer([self.console])

    def paint(self, *chunks):
        return ''.join(self.painter.paint(self.console, chunk) for chunk in chunks)

    def assertWholeLine(self, line, style):
        painted = self.paint(line + '\n')
        self.assertEqual(painted, style + line + RESET + '\n', repr(painted))

    def test_errors_are_red(self):
        for line in (
            '2026-10-08 18:49:19,347 - ERROR - boom',
            '2026-10-08 18:47:13 [django.request] ERROR Internal Server Error: /x',
            'ERROR:root:boom',
            '[ERROR] boom',
            '--- ERROR: could not open the file',
            '--- Error loading config.json',
            '--- [MODEL-BRAIN] Failed to read the profile',
            'ValueError: bad value',
            '--- [LATEXER] ' + CROSS + ' compile failed',
            'FAIL: test_x (agent.test_y.Case)',
            'FAILED (failures=1)',
        ):
            with self.subTest(line=line):
                self.assertWholeLine(line, RED)

    def test_fatals_are_white_on_red(self):
        for line in (
            '2026-10-08 18:49:19,347 - CRITICAL - disk full',
            '--- FATAL: cannot start the server',
            '[CRITICAL] out of memory',
        ):
            with self.subTest(line=line):
                self.assertWholeLine(line, FATAL)

    def test_warnings_are_yellow(self):
        for line in (
            '2026-10-08 18:49:19,347 - WARNING - careful',
            'WARNING:django.request:Not Found: /x',
            '--- [CONTEXT] WARNING: near the limit',
            '--- Warning: the model is slow',
            'C:/x/y.py:12: DeprecationWarning: old API',
            '--- [MODEL-BRAIN] ' + WARNING_SIGN + ' think is not supported here',
            'UserWarning: careful',
        ):
            with self.subTest(line=line):
                self.assertWholeLine(line, YELLOW)

    def test_debug_is_grey(self):
        for line in (
            '2026-10-08 18:49:19,347 - DEBUG - detail',
            '[DEBUG] x',
            'DEBUG:asyncio:Using selector',
        ):
            with self.subTest(line=line):
                self.assertWholeLine(line, GREY)

    def test_successes_are_green(self):
        for line in (
            '--- [GREPPER] ' + TICK + ' 25 match(es)',
            '2026-10-08 18:49:19,347 - INFO - ' + TICK + ' done',
            'OK',
            'OK (skipped=2)',
        ):
            with self.subTest(line=line):
                self.assertWholeLine(line, GREEN)

    def test_info_keeps_the_console_colour_with_the_tag_in_cyan(self):
        line = '--- [MODEL-BRAIN] model=glm-5.3:cloud | sampling: temperature=1.0'
        painted = self.paint(line + '\n')
        self.assertEqual(
            painted,
            '--- ' + CYAN + '[MODEL-BRAIN]' + RESET
            + ' model=glm-5.3:cloud | sampling: temperature=1.0\n',
        )

    def test_a_plain_line_without_a_tag_is_untouched(self):
        line = 'Watching for file changes with StatReloader'
        self.assertEqual(self.paint(line + '\n'), line + '\n')

    def test_the_user_tag_is_magenta_and_the_line_keeps_its_own_level(self):
        self.assertEqual(
            self.paint('[a3] --- [CONTEXT-REAL] tokens\n'),
            MAGENTA + '[a3]' + RESET + ' --- ' + CYAN + '[CONTEXT-REAL]' + RESET + ' tokens\n',
        )
        self.assertEqual(
            self.paint('[angela#3] --- ERROR: x\n'),
            MAGENTA + '[angela#3]' + RESET + ' ' + RED + '--- ERROR: x' + RESET + '\n',
        )

    def test_a_word_deep_inside_a_sentence_never_repaints_the_line(self):
        """The level is read from the START of a line. A user asking to "fix
        the ERROR" must not turn the console red."""
        for line in (
            "--- Message parsed: 'fix the ERROR in my code' **** to be sent to LLM",
            '--- [CONTEXT] the model said WARNING twice in its answer',
        ):
            with self.subTest(line=line):
                painted = self.paint(line + '\n')
                for style in (RED, FATAL, YELLOW, GREY, GREEN):
                    self.assertNotIn(style, painted)
                self.assertEqual(strip_codes(painted), line + '\n')

    def test_a_whole_traceback_is_red_and_it_ends_at_the_exception_line(self):
        lines = [
            'Traceback (most recent call last):',
            '  File "C:/x/y.py", line 3, in <module>',
            '    boom()',
            'KeyError: 1',
            '',
            'During handling of the above exception, another exception occurred:',
            '',
            'Traceback (most recent call last):',
            '  File "C:/x/z.py", line 9, in run',
            'django.db.utils.OperationalError: no such table: auth_user',
            '--- [NEXT] the server keeps going',
        ]
        painted = self.paint('\n'.join(lines) + '\n').split('\n')
        for original, shown in zip(lines, painted):
            with self.subTest(line=original):
                if original == '':
                    self.assertEqual(shown, '')
                elif original.startswith('--- [NEXT]'):
                    self.assertNotIn(RED, shown, 'the traceback colour leaked past its end')
                else:
                    self.assertEqual(shown, RED + original + RESET)

    def test_a_line_written_in_several_pieces_keeps_one_colour(self):
        """``print('--- Error:', exc)`` reaches the tee as several writes."""
        self.assertEqual(
            self.paint('--- Error:', ' disk', ' full', '\n', 'next line\n'),
            RED + '--- Error:' + RESET + RED + ' disk' + RESET + RED + ' full' + RESET
            + '\n' + 'next line\n',
        )

    def test_a_line_coloured_by_its_author_is_left_exactly_as_is(self):
        line = ('2026-10-08 18:47:13 [django.channels.server] INFO '
                + ESC + '[32mHTTP POST / 302 [0.68, 127.0.0.1:49905]' + ESC + '[0m')
        self.assertEqual(self.paint(line + '\n'), line + '\n')

    def test_http_status_5xx_red_4xx_yellow_others_plain(self):
        self.assertWholeLine('HTTP GET /agent/x 500 [0.36, 127.0.0.1:1]', RED)
        self.assertWholeLine('HTTP GET /missing 404 [0.01, 127.0.0.1:1]', YELLOW)
        self.assertWholeLine('"GET /x HTTP/1.1" 503 12', RED)
        for line in ('"GET /x HTTP/1.1" 200 12',
                     'WebSocket HANDSHAKING /ws/agent/ [127.0.0.1:1]'):
            with self.subTest(line=line):
                self.assertEqual(self.paint(line + '\n'), line + '\n')

    def test_a_stream_that_is_not_a_painted_console_is_never_touched(self):
        other = _Console()
        self.assertEqual(self.painter.paint(other, 'ERROR: boom\n'), 'ERROR: boom\n')

    def test_the_TEXT_is_never_changed_only_coloured(self):
        original = '\n'.join(CORPUS) + '\n'
        painted = self.paint(original)
        # Both sides lose ALL codes: the corpus already holds Django's own.
        self.assertEqual(strip_codes(painted), strip_codes(original))
        # ...and every character of the text is still there, in order.
        self.assertEqual(painted.replace(RESET, '').count('boom'), original.count('boom'))

    def test_every_colour_is_closed_on_its_own_line_so_nothing_bleeds(self):
        """A colour left open would paint the NEXT stream's text, or the shell
        prompt after Tlamatini exits."""
        painted = self.paint('\n'.join(CORPUS) + '\n')
        for line in painted.split('\n'):
            opened = line.count(ESC) - line.count(RESET)
            with self.subTest(line=line):
                self.assertEqual(opened, line.count(RESET), 'an opened colour is never reset')

    def test_each_chunk_closes_its_own_colour(self):
        """The writer may interleave stdout and stderr chunks in the window, so a
        colour must never be left open at the end of a write."""
        for chunk in ('--- Error:', '2026-10-08 - ERROR - half of a line'):
            with self.subTest(chunk=chunk):
                painter = Colorizer([self.console])
                painted = painter.paint(self.console, chunk)
                self.assertTrue(painted.endswith(RESET), repr(painted))


class TeeAndWriterTests(unittest.TestCase):
    """The file stays plain; the window gets the colour; a broken painter is harmless."""

    def setUp(self):
        TeeStream._CONSOLE_WRITER = None
        _NS['_USER_TAG_HOOK'] = None
        self.handle = tempfile.NamedTemporaryFile(
            mode='w', encoding='utf-8', suffix='.log', delete=False)
        self.writer = None

    def tearDown(self):
        if self.writer is not None:
            self.writer.close(timeout=5.0)
        TeeStream._CONSOLE_WRITER = None
        try:
            self.handle.close()
            os.unlink(self.handle.name)
        except OSError:
            pass

    def log_text(self):
        self.handle.flush()
        with open(self.handle.name, 'r', encoding='utf-8') as fh:
            return fh.read()

    def test_the_log_file_never_receives_a_colour_code_but_the_window_does(self):
        console = _Console()
        self.writer = ConsoleWriter()
        self.writer.set_colorizer(Colorizer([console]))
        self.writer.start()
        TeeStream._CONSOLE_WRITER = self.writer
        tee = TeeStream(console, self.handle)

        django_line = ('2026-10-08 18:47:13 [django.channels.server] INFO '
                       + ESC + '[32mHTTP POST / 302 [0.68, 127.0.0.1:1]' + ESC + '[0m\n')
        tee.write('--- ERROR: boom\n')
        tee.write(django_line)
        tee.flush_log_only()
        self.writer.close(timeout=5.0)

        log = self.log_text()
        self.assertNotIn(ESC, log, 'a colour code reached tlamatini.log')
        self.assertIn('--- ERROR: boom\n', log)
        self.assertIn('INFO HTTP POST / 302 [0.68, 127.0.0.1:1]\n', log,
                      "Django's own colour codes must be stripped from the file")
        window = console.text()
        self.assertIn(RED + '--- ERROR: boom' + RESET, window)
        self.assertIn(ESC + '[32mHTTP POST', window, "the window keeps Django's colours")

    def test_a_broken_painter_costs_the_colour_never_the_text(self):
        class _Broken:
            def paint(self, stream, text):
                raise RuntimeError('painter bug')

        console = _Console()
        self.writer = ConsoleWriter()
        self.writer.set_colorizer(_Broken())
        self.writer.start()
        self.writer.submit(console, 'still shown\n')
        self.writer.close(timeout=5.0)
        self.assertEqual(console.text(), 'still shown\n')

    def test_without_a_painter_the_window_gets_exactly_the_log_text(self):
        console = _Console()
        self.writer = ConsoleWriter()
        self.writer.start()
        TeeStream._CONSOLE_WRITER = self.writer
        TeeStream(console, self.handle).write('--- ERROR: boom\n')
        self.writer.close(timeout=5.0)
        self.assertEqual(console.text(), '--- ERROR: boom\n')

    def test_plain_strips_codes_and_costs_nothing_without_them(self):
        self.assertEqual(TeeStream._plain('a' + ESC + '[91mb' + ESC + '[0m'), 'ab')
        text = 'no codes here\n'
        self.assertIs(TeeStream._plain(text), text)

    def test_a_non_text_write_never_raises_out_of_the_tee(self):
        # _plain runs OUTSIDE the file write's try, so it must hand anything
        # that is not text back unchanged; the tee then swallows it exactly as
        # it did before the colours existed (Angela, 2026-10-08).
        data = b'--- bytes, not text\n'
        self.assertIs(TeeStream._plain(data), data)
        self.assertIsNone(TeeStream._plain(None))
        tee = TeeStream(_Console(), self.handle)
        tee.write(data)                       # must not raise
        tee.write('--- text after\n')
        tee.flush_log_only()
        self.assertIn('--- text after\n', self.log_text())


class SourceContractTests(unittest.TestCase):
    """Contracts a future edit could quietly undo. Read from the source text."""

    @classmethod
    def setUpClass(cls):
        cls.source = _read(_MANAGE_PY)
        cls.tree = ast.parse(cls.source, filename=_MANAGE_PY)

    def _source_of(self, name):
        for node in ast.walk(self.tree):
            if isinstance(node, (ast.FunctionDef, ast.ClassDef)) and node.name == name:
                return ast.get_source_segment(self.source, node)
        self.fail(f'{name} not found in manage.py')

    def test_virtual_terminal_is_only_ever_ADDED_and_read_back(self):
        body = self._source_of('_console_vt_on')
        self.assertIn('ENABLE_VIRTUAL_TERMINAL_PROCESSING = 0x0004', body)
        self.assertNotIn('& ~', body, 'this function may add bits, never clear one')
        self.assertLess(
            body.index('kernel32.SetConsoleMode('),
            body.index('ctypes.byref(check)'),
            'the mode must be READ BACK after it is set',
        )

    def test_colour_is_off_for_pipes_files_NO_COLOR_and_the_config_switch(self):
        body = self._source_of('_enable_console_colors')
        self.assertIn("os.environ.get('NO_COLOR')", body)
        self.assertIn("'console_colors', True", body)
        self.assertIn('.isatty()', body)
        self.assertLess(body.index('.isatty()'), body.index('writer.set_colorizer('))
        self.assertLess(body.index('_console_vt_on('), body.index('writer.set_colorizer('))

    def test_main_enables_colour_in_BOTH_modes(self):
        body = self._source_of('main')
        line = [ln for ln in body.splitlines() if '_enable_console_colors()' in ln][0]
        self.assertEqual(len(line) - len(line.lstrip()), 4,
                         'the colour switch is nested inside a condition')

    def test_painting_happens_only_on_the_drain_thread(self):
        self.assertIn('painter.paint(stream, text)', self._source_of('_emit'))
        self.assertNotIn('_colorizer', self._source_of('write'))

    def test_the_file_gets_the_plain_copy_and_the_window_the_original(self):
        body = self._source_of('write')
        self.assertLess(body.index('plain = self._plain(payload)'),
                        body.index('self._log_file.write(plain)'))
        self.assertIn('writer.submit(self._original, payload)', body)

    def test_the_console_TYPE_is_measured_from_the_window_class(self):
        """Angela: "make sure the type of console is assured". conhost and a
        pseudo-console (Windows Terminal, the IDE terminal) are told apart by
        the console handle's window CLASS, not by guessing."""
        body = self._source_of('_console_host')
        for needle in ('GetConsoleWindow', 'GetClassNameW', "'ConsoleWindowClass'",
                       "'PseudoConsoleWindow'", "'WT_SESSION'", "'TERM_PROGRAM'"):
            self.assertIn(needle, body)

    def test_the_console_type_is_announced_before_anything_else(self):
        body = self._source_of('_enable_console_colors')
        self.assertIn('host = _console_host()', body)
        self.assertIn('--- [CONSOLE] host:', body)
        self.assertLess(body.index('host = _console_host()'), body.index("os.environ.get('NO_COLOR')"),
                        'the console type must be reported even when colour is off')

    def test_utf8_code_page_is_FROZEN_ONLY_and_read_back(self):
        """The code page belongs to the console: from source it is the
        developer's terminal and a change would outlive the server."""
        body = self._source_of('_console_utf8')
        self.assertLess(body.index("getattr(sys, 'frozen', False)"),
                        body.index('SetConsoleOutputCP(65001)'))
        self.assertLess(body.index('SetConsoleOutputCP(65001)'),
                        body.rindex('GetConsoleOutputCP()'),
                        'the code page must be READ BACK after it is set')

    def test_the_console_type_probe_runs_here_and_never_raises(self):
        """Lift ``_console_host`` (and the owner probe it uses) and run it on
        THIS machine's console. Whatever the host is, the answer is a name."""
        nodes = [n for n in self.tree.body if isinstance(n, ast.FunctionDef)
                 and n.name in ('_console_host', '_owner_process_name')]
        self.assertEqual(len(nodes), 2)
        namespace = {'os': os, 'sys': sys}
        exec(compile(ast.Module(body=nodes, type_ignores=[]), _MANAGE_PY, 'exec'), namespace)  # noqa: S102
        host = namespace['_console_host']()
        self.assertIsInstance(host, str)
        self.assertTrue(host)
        self.assertNotEqual(host, 'unknown console', 'the probe itself failed')

    def test_the_terminal_is_named_by_its_PROCESS_not_by_inherited_env(self):
        """An IDE-launched program inherits TERM_PROGRAM=vscode even when its
        window is Windows Terminal's; the owner process is the measurement."""
        body = self._source_of('_console_host')
        self.assertLess(body.index('_owner_process_name(hwnd)'), body.index("'WT_SESSION'"))
        owner = self._source_of('_owner_process_name')
        self.assertIn("ctypes.WinDLL('user32')", owner, 'argtypes must not leak into ctypes.windll')
        self.assertIn('QueryFullProcessImageNameW', owner)

    def test_config_json_ships_colours_ON_and_documents_them(self):
        with open(_CONFIG_JSON, 'r', encoding='utf-8-sig') as fh:
            config = json.load(fh)
        self.assertIs(config.get('console_colors'), True)
        self.assertIn('_section_console_colors', config)


if __name__ == '__main__':
    unittest.main(verbosity=2)
