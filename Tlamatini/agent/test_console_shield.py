# ═══════════════════════════════════════════════════════════════════
#   ✦  T L A M A T I N I  ✦   —   "one who knows"
#
#   Created by  Angela López Mendoza   ·   @angelahack1
#   Developer · Architect · Creator of Tlamatini
# ═══════════════════════════════════════════════════════════════════
#   Tlamatini Author Banner — do not remove (releases scrub the name automatically)
"""Contract tests for the CONSOLE SHIELD (Angela, 2026-09-10).

THE BUG. Windows consoles ship with QuickEdit Mode ON. When a user clicks or
drags inside Tlamatini's console window — to copy a line of the log, or just to
focus the window — Windows enters SELECTION mode and ``WriteConsoleW`` **stops
returning**. It blocks; it does not raise, so no ``try/except`` can catch it.

``_TeeStream.write`` used to write the CONSOLE FIRST and ``tlamatini.log``
SECOND, so a single click froze the calling thread, froze the log file, and then
froze every other thread that logged anything. The app looked hung. It wasn't —
it was parked in a Win32 call, waiting for a mouse.

THE FIX under test: ``manage.py::_ConsoleWriter`` — a bounded queue drained by
ONE daemon thread — plus a reversed sink order so the durable record is written
before the cosmetic one, plus the ``console_quick_edit`` config knob.

WHAT THESE TESTS PIN:
  1. A blocked console can NEVER block ``_TeeStream.write``.
  2. ``tlamatini.log`` keeps receiving text while the console is blocked.
  3. The queue is bounded, drops the OLDEST, and NEVER drops silently.
  4. Shutdown is bounded — a held selection cannot keep the process alive.
  5. Per-user tags are still computed on the CALLER's thread (they read a
     ContextVar; computing them on the drain thread would mis-attribute EVERY
     line in the log).
  6. The console branding — title + Tlamatini icon — is untouched.

``manage.py`` CANNOT be imported in a test process (module-level side effects:
console branding, the stdout/stderr tee, the Temp-dir pin), so exactly like
``test_django_port_config.py`` and ``test_temp_dir_policy.py`` we treat its
source as the contract and exec the lifted nodes in a clean namespace.

Run:
    python Tlamatini/manage.py test agent.test_console_shield
    python -m unittest agent.test_console_shield          # Django-free too
"""
import ast
import json
import os
import re
import sys
import tempfile
import threading
import time
import unittest
import collections

#   <repo>/Tlamatini/agent/test_console_shield.py  ->  <repo>/Tlamatini
_PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_MANAGE_PY = os.path.join(_PROJECT_DIR, 'manage.py')
_CONFIG_JSON = os.path.join(_PROJECT_DIR, 'agent', 'config.json')

_WANTED_CLASSES = ('_ConsoleWriter', '_TeeStream')

# Any real block here means the shield is broken; keep the ceiling generous
# enough for a loaded CI box but far below "a human is holding the mouse".
_NON_BLOCKING_CEILING_SECONDS = 3.0


def _read(path):
    with open(path, 'r', encoding='utf-8') as fh:
        return fh.read()


def _load_console_classes():
    """Exec ONLY the two console classes out of manage.py — never import it."""
    tree = ast.parse(_read(_MANAGE_PY), filename=_MANAGE_PY)
    picked = [
        node for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name in _WANTED_CLASSES
    ]
    namespace = {
        'collections': collections,
        'threading': threading,
        'time': time,
        'os': os,
        'sys': sys,
        '_USER_TAG_HOOK': None,
    }
    exec(compile(ast.Module(body=picked, type_ignores=[]), _MANAGE_PY, 'exec'), namespace)  # noqa: S102
    return namespace


class _BlockingStream:
    """A console window with a mouse selection held in it.

    ``write`` parks until ``release()`` is called — the exact behaviour of
    ``WriteConsoleW`` on a console in selection mode. It never raises, because
    the real thing never does either: that is the whole point.
    """

    def __init__(self):
        self.entered = threading.Event()
        self._released = threading.Event()
        self.written = []
        self.flushes = 0
        self.writer_threads = []

    def write(self, text):
        self.entered.set()
        self.writer_threads.append(threading.current_thread().name)
        self._released.wait(30)
        self.written.append(text)
        return len(text)

    def flush(self):
        self._released.wait(30)
        self.flushes += 1

    def release(self):
        self._released.set()

    def text(self):
        return ''.join(self.written)


class _RecordingStream:
    """A console that answers instantly — the normal, unselected case."""

    def __init__(self):
        self.written = []
        self.flushes = 0
        self.writer_threads = []

    def write(self, text):
        self.writer_threads.append(threading.current_thread().name)
        self.written.append(text)
        return len(text)

    def flush(self):
        self.flushes += 1

    def text(self):
        return ''.join(self.written)


class _ConsoleShieldCase(unittest.TestCase):
    """Base: lifts the classes once, and guarantees nothing is left blocked."""

    @classmethod
    def setUpClass(cls):
        ns = _load_console_classes()
        cls.ConsoleWriter = ns['_ConsoleWriter']
        cls.TeeStream = ns['_TeeStream']
        cls.namespace = ns

    def setUp(self):
        self._streams = []
        self._writers = []
        self._files = []
        # The shield slot is a CLASS attribute — never let it leak between tests.
        self.TeeStream._CONSOLE_WRITER = None
        self.namespace['_USER_TAG_HOOK'] = None

    def tearDown(self):
        for stream in self._streams:
            try:
                stream.release()
            except AttributeError:
                pass
        for writer in self._writers:
            writer.close(timeout=2.0)
        for handle, path in self._files:
            try:
                handle.close()
                os.unlink(path)
            except OSError:
                pass
        self.TeeStream._CONSOLE_WRITER = None
        self.namespace['_USER_TAG_HOOK'] = None

    # -- helpers ---------------------------------------------------------
    def make_blocking(self):
        stream = _BlockingStream()
        self._streams.append(stream)
        return stream

    def make_writer(self, note_sink=None, max_chunks=None):
        writer = self.ConsoleWriter(note_sink=note_sink)
        if max_chunks is not None:
            writer._MAX_QUEUED_CHUNKS = max_chunks
        writer.start()
        self._writers.append(writer)
        return writer

    def make_log(self):
        handle = tempfile.NamedTemporaryFile(
            mode='w', encoding='utf-8', suffix='.log', delete=False
        )
        self._files.append((handle, handle.name))
        return handle

    def log_text(self, handle):
        handle.flush()
        with open(handle.name, 'r', encoding='utf-8') as fh:
            return fh.read()


class ConsoleWriterTests(_ConsoleShieldCase):
    """The queue itself: never blocks, bounded, honest about drops."""

    def test_submit_returns_immediately_while_the_console_is_blocked(self):
        stream = self.make_blocking()
        writer = self.make_writer()

        writer.submit(stream, 'first\n')
        self.assertTrue(stream.entered.wait(5), 'drain thread never reached the console')

        started = time.monotonic()
        for i in range(200):
            writer.submit(stream, f'line {i}\n')
        elapsed = time.monotonic() - started

        self.assertLess(
            elapsed, _NON_BLOCKING_CEILING_SECONDS,
            'submit() blocked while the console was held — the shield is broken',
        )

    def test_queued_text_arrives_once_the_selection_is_released(self):
        stream = self.make_blocking()
        writer = self.make_writer()
        writer.submit(stream, 'alpha\n')
        self.assertTrue(stream.entered.wait(5))
        writer.submit(stream, 'beta\n')

        stream.release()
        writer.close(timeout=5.0)

        self.assertIn('alpha', stream.text())
        self.assertIn('beta', stream.text())

    def test_the_queue_is_bounded_and_drops_the_OLDEST_chunk(self):
        stream = self.make_blocking()
        writer = self.make_writer(max_chunks=3)

        writer.submit(stream, 'taken-by-drain\n')
        self.assertTrue(stream.entered.wait(5))
        for i in range(20):
            writer.submit(stream, f'chunk-{i}\n')

        stream.release()
        writer.close(timeout=5.0)

        text = stream.text()
        # Newest survive, oldest were evicted — drop-OLDEST, not drop-newest.
        self.assertIn('chunk-19', text)
        self.assertNotIn('chunk-0\n', text)

    def test_a_drop_is_never_silent(self):
        stream = self.make_blocking()
        notes = []
        writer = self.make_writer(note_sink=notes.append, max_chunks=2)

        writer.submit(stream, 'taken-by-drain\n')
        self.assertTrue(stream.entered.wait(5))
        for i in range(10):
            writer.submit(stream, f'chunk-{i}\n')

        stream.release()
        writer.close(timeout=5.0)

        self.assertIn('CONSOLE-SHIELD', stream.text())
        self.assertIn('dropped', stream.text())
        self.assertTrue(notes, 'the drop was never recorded in tlamatini.log')
        self.assertIn('tlamatini.log', notes[0])

    def test_close_is_bounded_even_with_the_console_still_held(self):
        stream = self.make_blocking()
        writer = self.ConsoleWriter()
        writer.start()
        self._writers.append(writer)

        writer.submit(stream, 'held\n')
        self.assertTrue(stream.entered.wait(5))

        started = time.monotonic()
        writer.close(timeout=0.5)
        elapsed = time.monotonic() - started

        self.assertLess(
            elapsed, _NON_BLOCKING_CEILING_SECONDS,
            'close() waited on a held console — exit could hang',
        )

    def test_submit_after_close_is_a_harmless_no_op(self):
        stream = _RecordingStream()
        writer = self.make_writer()
        writer.close(timeout=2.0)
        writer.submit(stream, 'ignored\n')   # must not raise
        self.assertEqual(stream.text(), '')

    def test_flush_is_delegated_to_the_drain_thread(self):
        stream = _RecordingStream()
        writer = self.make_writer()
        writer.request_flush(stream)
        writer.close(timeout=5.0)
        self.assertGreaterEqual(stream.flushes, 1)


class TeeStreamShieldTests(_ConsoleShieldCase):
    """The tee: the log must survive — and outrun — a frozen console."""

    def test_THE_REGRESSION_write_returns_while_the_console_is_blocked(self):
        stream = self.make_blocking()
        writer = self.make_writer()
        self.TeeStream._CONSOLE_WRITER = writer
        log = self.make_log()
        tee = self.TeeStream(stream, log)

        tee.write('priming\n')
        self.assertTrue(stream.entered.wait(5), 'drain thread never reached the console')

        started = time.monotonic()
        for i in range(100):
            tee.write(f'work {i}\n')
        elapsed = time.monotonic() - started

        self.assertLess(
            elapsed, _NON_BLOCKING_CEILING_SECONDS,
            'a selected console blocked the caller — THE bug this shield exists to kill',
        )

    def test_the_log_keeps_growing_while_the_console_is_blocked(self):
        stream = self.make_blocking()
        writer = self.make_writer()
        self.TeeStream._CONSOLE_WRITER = writer
        log = self.make_log()
        tee = self.TeeStream(stream, log)

        tee.write('priming\n')
        self.assertTrue(stream.entered.wait(5))
        tee.write('written-while-frozen\n')
        tee.flush_log_only()

        # The console has received NOTHING yet; the durable record has it all.
        self.assertEqual(stream.written, [])
        self.assertIn('written-while-frozen', self.log_text(log))

    def test_write_returns_the_caller_s_own_length(self):
        stream = _RecordingStream()
        writer = self.make_writer()
        self.TeeStream._CONSOLE_WRITER = writer
        tee = self.TeeStream(stream, self.make_log())
        self.assertEqual(tee.write('hello'), len('hello'))

    def test_user_tags_are_computed_on_the_CALLER_thread(self):
        """The tag reads a ContextVar — computing it on the drain thread would
        stamp EVERY line with the drain thread's identity instead of the user's.
        """
        stream = _RecordingStream()
        writer = self.make_writer()
        self.TeeStream._CONSOLE_WRITER = writer
        tee = self.TeeStream(stream, self.make_log())

        self.namespace['_USER_TAG_HOOK'] = (
            lambda: '[' + threading.current_thread().name + '] '
        )

        def _caller():
            tee.write('payload\n')

        thread = threading.Thread(target=_caller, name='CALLER-THREAD')
        thread.start()
        thread.join(5)
        writer.close(timeout=5.0)

        self.assertIn('[CALLER-THREAD] payload', stream.text())
        self.assertNotIn('tlamatini-console-writer', stream.text())

    def test_the_console_write_really_happens_on_the_drain_thread(self):
        stream = _RecordingStream()
        writer = self.make_writer()
        self.TeeStream._CONSOLE_WRITER = writer
        tee = self.TeeStream(stream, self.make_log())

        tee.write('payload\n')
        writer.close(timeout=5.0)

        self.assertTrue(stream.writer_threads)
        self.assertNotIn(
            threading.current_thread().name, stream.writer_threads,
            'the console was written on the caller thread — the shield is bypassed',
        )

    def test_without_a_shield_the_tee_still_writes_inline(self):
        """Backwards compatibility: a tee built alone must keep working."""
        stream = _RecordingStream()
        self.TeeStream._CONSOLE_WRITER = None
        tee = self.TeeStream(stream, self.make_log())
        tee.write('inline\n')
        self.assertEqual(stream.text(), 'inline\n')

    def test_flush_log_only_never_touches_the_console(self):
        stream = _RecordingStream()
        writer = self.make_writer()
        self.TeeStream._CONSOLE_WRITER = writer
        tee = self.TeeStream(stream, self.make_log())
        tee.flush_log_only()
        writer.close(timeout=5.0)
        self.assertEqual(stream.flushes, 0)


class ConsoleShieldSourceContractTests(unittest.TestCase):
    """Contracts a future edit could quietly undo. Read from the source text."""

    @classmethod
    def setUpClass(cls):
        cls.source = _read(_MANAGE_PY)
        cls.tree = ast.parse(cls.source, filename=_MANAGE_PY)

    def _function_source(self, name, parent=None):
        for node in ast.walk(self.tree):
            if isinstance(node, (ast.FunctionDef, ast.ClassDef)) and node.name == name:
                if parent is None or parent in ast.get_source_segment(self.source, node):
                    return ast.get_source_segment(self.source, node)
        self.fail(f'{name} not found in manage.py')

    def test_the_log_file_is_written_BEFORE_the_console_is_queued(self):
        """The reversal is the fix. Put the console back on top and the bug
        returns in full: a held selection freezes tlamatini.log too."""
        body = self._function_source('write')
        file_at = body.index('self._log_file.write(payload)')
        console_at = body.index('writer.submit(self._original, payload)')
        self.assertLess(
            file_at, console_at,
            'the console is queued before the log file is written — sink order reversed',
        )

    def test_submit_is_called_outside_the_log_lock(self):
        """Lock ordering: callers take _LOG_LOCK then release it, THEN submit.
        Nesting them trades a console freeze for a deadlock."""
        body = self._function_source('write')
        lock_line = [ln for ln in body.splitlines() if 'with self._LOG_LOCK' in ln][0]
        lock_indent = len(lock_line) - len(lock_line.lstrip())
        submit_line = [ln for ln in body.splitlines()
                       if 'writer.submit(self._original, payload)' in ln][0]
        submit_indent = len(submit_line) - len(submit_line.lstrip())
        self.assertLessEqual(
            submit_indent, lock_indent + 4,
            'submit() appears nested inside the _LOG_LOCK block — deadlock risk',
        )

    def test_the_console_branding_is_untouched(self):
        """The icon must survive this change. It lives on the console HWND;
        the shield only ever touches sys.stdout/stderr and the STDIN mode."""
        branding = self._function_source('_brand_console_window')
        self.assertIn('SetConsoleTitleW', branding)
        self.assertIn('WM_SETICON', branding)
        self.assertIn('Tlamatini.ico', branding)
        self.assertIn('ICON_SMALL', branding)
        self.assertIn('ICON_BIG', branding)

    def test_quick_edit_policy_sets_extended_flags(self):
        """Without ENABLE_EXTENDED_FLAGS, Windows IGNORES the QuickEdit change
        and the knob would silently do nothing."""
        policy = self._function_source('_apply_console_quick_edit_policy')
        self.assertIn('ENABLE_EXTENDED_FLAGS', policy)
        self.assertIn('ENABLE_QUICK_EDIT_INPUT', policy)
        self.assertIn('| ENABLE_EXTENDED_FLAGS', policy)
        self.assertIn('& ~ENABLE_QUICK_EDIT_INPUT', policy)

    def test_quick_edit_defaults_to_true_and_does_nothing(self):
        policy = self._function_source('_apply_console_quick_edit_policy')
        self.assertIn("'console_quick_edit', True", policy)
        self.assertIn('if enabled:', policy)
        self.assertIn('return', policy)

    # ------------------------------------------------------------------ #
    # CTRL+C — Angela, 2026-09-10. These three tests are the whole point. #
    # ------------------------------------------------------------------ #

    def test_CTRL_C_bit_is_FORCED_ON_never_merely_preserved(self):
        """⚠️ Ctrl+C is ENABLE_PROCESSED_INPUT (0x0001) — DO NOT WEAKEN THIS.

        It is a different bit from QuickEdit but lives in the SAME DWORD, which
        is exactly how programs silently lose Ctrl+C. Preserving whatever was
        already there is NOT good enough: if Tlamatini ever inherits a console
        with the bit already off, she would hand the user a window they cannot
        interrupt. So the bit is OR-ed in unconditionally.
        """
        policy = self._function_source('_apply_console_quick_edit_policy')
        self.assertIn('ENABLE_PROCESSED_INPUT = 0x0001', policy)
        self.assertIn('| ENABLE_PROCESSED_INPUT', policy)

    def test_CTRL_C_bit_is_NEVER_cleared(self):
        """No form of `& ~ENABLE_PROCESSED_INPUT` may ever appear here."""
        policy = self._function_source('_apply_console_quick_edit_policy')
        self.assertNotIn('~ENABLE_PROCESSED_INPUT', policy)
        self.assertNotIn('& ~ENABLE_PROCESSED_INPUT', policy)
        # ...and the only bit ever cleared is QuickEdit itself.
        cleared = re.findall(r'&\s*~\s*(\w+)', policy)
        self.assertEqual(
            set(cleared), {'ENABLE_QUICK_EDIT_INPUT'},
            f'this function may clear QuickEdit and nothing else; it clears {cleared}',
        )

    def test_the_change_is_ROLLED_BACK_if_CTRL_C_did_not_survive(self):
        """FAIL TOWARD CTRL+C. A paused console window is an annoyance; a
        console you cannot interrupt takes the machine away from the user —
        and takes the SIGINT that runs the Tier-3 orphan reaper with it.

        So the mode is read BACK after being set, and if ENABLE_PROCESSED_INPUT
        did not survive, the ORIGINAL mode is restored verbatim and QuickEdit is
        left alone.
        """
        policy = self._function_source('_apply_console_quick_edit_policy')
        self.assertIn('SetConsoleMode(handle, new_mode)', policy)
        # a read-back of the mode must happen AFTER the write
        self.assertLess(
            policy.index('SetConsoleMode(handle, new_mode)'),
            policy.rindex('GetConsoleMode(handle, ctypes.byref(check))'),
            'the mode must be verified AFTER it is changed, not before',
        )
        self.assertIn('check.value & ENABLE_PROCESSED_INPUT', policy)
        self.assertIn('SetConsoleMode(handle, mode.value)', policy)
        self.assertLess(
            policy.index('check.value & ENABLE_PROCESSED_INPUT'),
            policy.index('SetConsoleMode(handle, mode.value)'),
            'the rollback must be guarded by the Ctrl+C check',
        )

    def test_disabling_quick_edit_is_FROZEN_ONLY(self):
        """Console mode belongs to the CONSOLE, not the process that sets it.

        From source, that console is the DEVELOPER'S terminal and it OUTLIVES
        Tlamatini — clearing QuickEdit there would leave their shell unable to
        select text after the server exits, with nothing on screen explaining
        why. A frozen build owns its window and takes it down with the process.
        """
        policy = self._function_source('_apply_console_quick_edit_policy')
        self.assertIn("getattr(sys, 'frozen', False)", policy)
        self.assertLess(
            policy.index("getattr(sys, 'frozen', False)"),
            policy.index('import ctypes'),
            'the frozen gate must run BEFORE any console API is touched',
        )

    def test_the_frozen_gate_stays_quiet_on_a_default_config(self):
        """Someone who never set the knob must hear nothing about it."""
        policy = self._function_source('_apply_console_quick_edit_policy')
        self.assertLess(
            policy.index('if enabled:'),
            policy.index("getattr(sys, 'frozen', False)"),
            'the source-mode notice would print even when the knob was left alone',
        )

    def test_the_QUEUE_SHIELD_itself_is_NOT_frozen_gated(self):
        """The freeze is identical in dev — where log text gets selected most.
        Gating the shield by mode would leave the developer holding the bug."""
        setup = self._function_source('_setup_log_tee')
        line = [ln for ln in setup.splitlines() if 'console_writer.start()' in ln][0]
        indent = len(line) - len(line.lstrip())
        self.assertEqual(
            indent, 4,
            'the shield install is nested inside a conditional — it must run in '
            'BOTH frozen and source mode',
        )
        self.assertIn('_TeeStream._CONSOLE_WRITER = console_writer', setup)

    def test_the_idle_flusher_stays_off_the_console_queue(self):
        setup = self._function_source('_setup_log_tee')
        self.assertIn('tee.flush_log_only()', setup)

    def test_shutdown_drains_the_console_with_a_bound(self):
        setup = self._function_source('_setup_log_tee')
        self.assertIn('atexit.register(_shutdown_console_shield)', setup)
        self.assertIn('console_writer.close()', setup)

    def test_config_json_ships_quick_edit_OFF(self):
        """Angela, 2026-09-10: QuickEdit SHIPS DISABLED. Do NOT flip this back.

        The knob shipped ``true`` for one day and Angela hit the exact failure it
        was supposed to prevent: she clicked the console, the window stopped
        showing new lines, and Tlamatini *looked* hung until she pressed Enter
        and the whole backlog flooded in. Her ruling, verbatim: *"LOG MUST BE
        STILL INCREMENTING, I DONT CARE IF THE STUPID USER CANT COPY CONTENT
        FROM THE CONSOLE WINDOW"*.

        So the trade is settled the other way round: a visibly-live console beats
        drag-to-select. With QuickEdit cleared a click cannot start a selection,
        so conhost never enters the mode that pauses output at all — the display,
        the log file and the processing all keep going. Copying is still possible
        via right-click ▸ Mark. The queue shield stays as the second line of
        defence for hosts that ignore the flag (Windows Terminal).
        """
        with open(_CONFIG_JSON, 'r', encoding='utf-8-sig') as fh:
            config = json.load(fh)
        self.assertIn('console_quick_edit', config)
        self.assertIs(config['console_quick_edit'], False)
        self.assertIn('_section_console_quick_edit', config)


if __name__ == '__main__':
    unittest.main(verbosity=2)
