"""Ctrl+C MUST ALWAYS QUIT — source contract for the shutdown path.

THE INCIDENT (Angela, 2026-08-29). The installed C:\\Tlamatini hung forever on
Ctrl+C. A py-spy dump of the live wedged process (PID 27308, 80 threads, all in
Wait, 0 progress) showed the MainThread carrying an ELEVEN-DEEP tower of
``signal_handler -> cleanup_pool_on_shutdown`` frames — one per Ctrl+C press
recorded in ``tlamatini.log`` — whose top was parked forever in::

    start (threading.py:999)          <- Thread.start()
    wait  (threading.py:655)          <- self._started.wait()   *** FOREVER ***

Two independent defects produced it:

1. ``signal_handler`` called ``cleanup_pool_on_shutdown()`` DIRECTLY. A Python
   signal handler runs ON THE MAIN THREAD, interrupting whatever it was doing,
   and that cleanup's first act is ``psutil.process_iter(['cmdline'])`` — it
   opens and reads the PEB of every process on the machine. Ctrl+C therefore
   looked dead for seconds, the user pressed again, and NOTHING guarded
   re-entry: each signal stacked a new cleanup on top of one already part way
   through NON-REENTRANT ``threading``/``psutil`` internals. The interrupted
   ``Thread.start()`` still held threading's global ``_active_limbo_lock`` (a
   plain, non-reentrant Lock), so the nested one could never complete —
   self-deadlock on the one thread that had to survive. ``os._exit(0)`` sat at
   the END of the handler and was never reached.

2. ``with ThreadPoolExecutor(max_workers=1) as executor:`` around a
   ``future.result(timeout=5)``. The context manager's ``__exit__`` calls
   ``shutdown(wait=True)`` — an UNBOUNDED join that silently defeats the very
   timeout written beside it.

These tests pin the fix. They read SOURCE (the shutdown path lives inside
``AgentConfig.ready()`` and cannot be imported and signalled in a unit test), so
they are cheap, deterministic, and fail loudly the moment someone "simplifies"
the handler back into the deadlock.
"""

import ast
import os
import re
import unittest


_APPS_PY = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'apps.py')


def _source():
    with open(_APPS_PY, 'r', encoding='utf-8') as handle:
        return handle.read()


def _strip_comments_and_docstrings(source):
    """Return source with comments removed, so a WARNING mentioning a forbidden
    pattern is never mistaken for the pattern itself.

    The fix's own comments quote ``with ThreadPoolExecutor(...)`` and
    ``cleanup_pool_on_shutdown()`` on purpose — that is the explanation a future
    reader needs. A naive substring scan would flag the very documentation that
    prevents the regression.
    """
    return '\n'.join(
        re.sub(r'#.*$', '', line) for line in source.splitlines()
    )


def _find_function(tree, name):
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return node
    return None


class SignalHandlerDoesNotDoTheWorkTests(unittest.TestCase):
    """Defect 1 — the handler must delegate, never execute."""

    def setUp(self):
        self.source = _source()
        self.code = _strip_comments_and_docstrings(self.source)
        self.tree = ast.parse(self.source)
        self.handler = _find_function(self.tree, 'signal_handler')

    def test_signal_handler_exists(self):
        self.assertIsNotNone(
            self.handler,
            "apps.py must still install a signal_handler for SIGINT/SIGBREAK.")

    def test_signal_handler_does_not_call_cleanup_directly(self):
        """The deadlock itself: real work executed on the interrupted thread."""
        called = {
            node.func.id
            for node in ast.walk(self.handler)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        }
        self.assertNotIn(
            'cleanup_pool_on_shutdown', called,
            "signal_handler must NOT call cleanup_pool_on_shutdown() directly - "
            "that runs psutil.process_iter() on the interrupted MAIN thread and "
            "is exactly the 2026-08-29 Ctrl+C deadlock. Set the shutdown Event "
            "and let the pre-started worker thread do it.")

    def test_signal_handler_starts_no_thread(self):
        """A signal handler must never create a thread: Thread.start() takes
        threading's non-reentrant global _active_limbo_lock, which the frame it
        interrupted may already hold."""
        for node in ast.walk(self.handler):
            if isinstance(node, ast.Call):
                func = node.func
                name = getattr(func, 'attr', None) or getattr(func, 'id', None)
                self.assertNotIn(
                    name, ('Thread', 'submit', 'ThreadPoolExecutor'),
                    "signal_handler must not start threads or submit work - "
                    "Thread.start() from a signal context self-deadlocks.")

    def test_second_signal_exits_immediately(self):
        """Re-entrancy guard: press two must terminate, not stack another
        cleanup on top of the first."""
        handler_src = ast.get_source_segment(self.source, self.handler) or ''
        self.assertIn(
            'is_set()', handler_src,
            "signal_handler must check the shutdown Event first so a SECOND "
            "Ctrl+C exits instead of re-entering cleanup.")
        self.assertIn(
            '_exit(1)', handler_src,
            "A second Ctrl+C must hard-exit (os._exit) - the user is telling us "
            "they are done waiting.")

    def test_event_is_set_before_any_printing(self):
        """Order matters: releasing the worker must not sit behind a print that
        could block on the buffered log tee's cross-thread lock."""
        handler_src = ast.get_source_segment(self.source, self.handler) or ''
        set_at = handler_src.find('_shutdown_event.set()')
        # the announcement print, i.e. the one carrying the signal number
        print_at = handler_src.find('Received signal')
        self.assertGreater(set_at, -1, "handler must set the shutdown Event")
        self.assertGreater(print_at, -1, "handler should still announce the signal")
        self.assertLess(
            set_at, print_at,
            "_shutdown_event.set() must come BEFORE the announcement print, so a "
            "blocked log write can never delay the shutdown itself.")


class ShutdownIsBoundedTests(unittest.TestCase):
    """Defect 2 — nothing in the shutdown path may wait without a deadline."""

    def setUp(self):
        self.source = _source()
        self.code = _strip_comments_and_docstrings(self.source)

    def test_no_context_managed_thread_pool_executor(self):
        """``with ThreadPoolExecutor(...)`` joins its workers with NO timeout on
        __exit__, defeating any timeout inside the block."""
        self.assertNotRegex(
            self.code, r'with\s+ThreadPoolExecutor\s*\(',
            "`with ThreadPoolExecutor(...)` is FORBIDDEN in apps.py: __exit__ "
            "calls shutdown(wait=True), an unbounded join that silently "
            "defeated the future.result(timeout=5) beside it and hung shutdown. "
            "Use a daemon threading.Thread with join(timeout).")

    def test_tracked_process_killer_is_a_daemon_thread_with_a_join_timeout(self):
        self.assertRegex(
            self.code, r'target=kill_tracked_processes',
            "the tracked-process kill must still run off the calling thread")
        self.assertRegex(
            self.code, r'name="TlamatiniKillTracked",\s*daemon=True',
            "the tracked-process killer must be a DAEMON thread, so the "
            "interpreter never joins it at exit")
        self.assertRegex(
            self.code, r'killer\.join\(\s*\d',
            "the tracked-process killer must be joined WITH A TIMEOUT")

    def test_watchdog_guarantees_exit(self):
        """Cleanup gets a deadline, not a blank cheque."""
        self.assertIn(
            '_SHUTDOWN_GRACE_SECONDS', self.code,
            "a shutdown grace period must be defined")
        self.assertRegex(
            self.code, r'name="TlamatiniShutdownWatchdog",\s*daemon=True',
            "a watchdog thread must exit the process if cleanup overruns")
        self.assertRegex(
            self.code, r'_exit\(3\)',
            "the watchdog must hard-exit when the grace period elapses")


class ShutdownThreadsAreStartedAtBootTests(unittest.TestCase):
    """The worker/watchdog must be created in NORMAL context, never from a
    signal — that creation is precisely what deadlocked."""

    def setUp(self):
        self.code = _strip_comments_and_docstrings(_source())

    def test_worker_thread_is_started_and_daemon(self):
        self.assertRegex(
            self.code, r'name="TlamatiniShutdown",\s*daemon=True',
            "the shutdown worker thread must exist and be a daemon")
        self.assertRegex(
            self.code, r'target=_shutdown_worker',
            "the shutdown worker must run cleanup_pool_on_shutdown off-signal")

    def test_worker_waits_on_the_event_then_exits(self):
        self.assertRegex(
            self.code, r'_shutdown_event\.wait\(\)',
            "the shutdown threads must block on the Event until a signal fires")
        self.assertRegex(
            self.code, r'_exit\(0\)',
            "the worker must os._exit(0) after cleanup so the atexit copy of the "
            "same cleanup does not repeat every kill")

    def test_atexit_cleanup_is_still_registered(self):
        """A normal (non-signal) shutdown must still clean the pools."""
        self.assertRegex(
            self.code, r'atexit\.register\(cleanup_pool_on_shutdown\)',
            "the normal-shutdown atexit cleanup must not be lost in the fix")


if __name__ == '__main__':
    unittest.main()
