# ═══════════════════════════════════════════════════════════════════
#   ✦  T L A M A T I N I  ✦   —   "one who knows"
#
#   Crafted with heart by  Angela   ·   @angelahack1
#   Developer · Architect · Creator of Tlamatini
#
#   Every line of this file was written by Angela.
# ═══════════════════════════════════════════════════════════════════
#   Tlamatini Author Banner — do not remove (releases scrub the name automatically)
"""Hard regression tests for the bounded ``execute_command`` (2026-06-06).

Incident replayed here: a Multi-Turn run issued

    cd "...\\util" && copy con InputValidator.java < NUL

through ``execute_command``. ``copy con`` reads the CON device (not stdin), so
``< NUL`` never delivered EOF; with no console attached the child blocked
forever, and because ``execute_command`` used a bare
``subprocess.run(command, shell=True)`` with **no timeout and inherited stdin**,
the call waited indefinitely and froze the Multi-Turn worker thread for ~45 min.
Killing the child by hand did NOT release it (a grandchild had leaked the stdout
pipe write-handle, so ``communicate()`` never reached EOF).

These tests drive the REAL code (``_run_command_bounded`` and the ``@tool``
``execute_command``) against REAL subprocesses — nothing about the unit under
test is mocked. They assert the three guarantees the fix must hold for every
future execution:

1. a command that would run longer than the timeout is forcibly bounded and
   reports ``timed_out`` (it never hangs forever);
2. the ENTIRE process tree is killed — not just the direct shell child — so a
   grandchild can't leak a pipe handle and re-deadlock the drain, and no orphan
   process survives;
3. stdin is starved to DEVNULL, so an interactive read (``copy con`` /
   ``set /p`` / ``read``) gets immediate EOF instead of blocking.

Plus the ordinary clean / non-zero-exit paths, and the tool-level timeout
message that steers the LLM toward ``file_creator``.
"""
from __future__ import annotations

import os
import sys
import tempfile
import time
import unittest

import psutil

from agent import tools as tools_mod
from agent.tools import _run_command_bounded, execute_command

_IS_WIN = sys.platform.startswith("win")


def _long_running_tree_command() -> str:
    """A shell command whose shell spawns a grandchild running ~30 s.

    Under ``shell=True`` the runner launches ``cmd /c <cmd>`` (Windows) or
    ``/bin/sh -c <cmd>`` (POSIX); the ``ping`` / ``sleep`` is the grandchild
    that inherits the shell's stdout pipe. Killing only the direct child would
    leave that grandchild alive holding the pipe open — the exact deadlock the
    whole-tree kill exists to prevent.
    """
    if _IS_WIN:
        return "ping -n 30 127.0.0.1 > NUL"
    return "sleep 30"


class RunCommandBoundedTests(unittest.TestCase):
    """Exercise the real ``_run_command_bounded`` engine against real processes."""

    def _descendant_pids(self) -> set:
        try:
            return {p.pid for p in psutil.Process(os.getpid()).children(recursive=True)}
        except Exception:
            return set()

    def _assert_no_orphans(self, before: set, context: str) -> None:
        # Give the OS a beat to finish reaping the killed tree.
        time.sleep(1.0)
        leaked = [pid for pid in (self._descendant_pids() - before) if psutil.pid_exists(pid)]
        self.assertEqual(leaked, [], f"{context}: orphan processes survived -> {leaked}")

    # ── clean / failure paths ────────────────────────────────────────────
    def test_clean_command_succeeds(self):
        rc, out, err, timed_out = _run_command_bounded("echo hello-bounded", shell=True, timeout=30)
        self.assertFalse(timed_out)
        self.assertEqual(rc, 0)
        self.assertIn("hello-bounded", out)

    def test_nonzero_exit_is_reported_not_treated_as_timeout(self):
        cmd = "cmd /c exit 7" if _IS_WIN else "exit 7"
        rc, out, err, timed_out = _run_command_bounded(cmd, shell=True, timeout=30)
        self.assertFalse(timed_out)
        self.assertEqual(rc, 7)

    def test_clean_command_leaves_no_orphans(self):
        before = self._descendant_pids()
        rc, out, err, timed_out = _run_command_bounded("echo done", shell=True, timeout=30)
        self.assertFalse(timed_out)
        self.assertEqual(rc, 0)
        self._assert_no_orphans(before, "clean path")

    # ── THE INCIDENT: bounded + whole-tree kill, no hang, no orphan ───────
    def test_timeout_bounds_and_kills_whole_tree(self):
        before = self._descendant_pids()
        start = time.monotonic()
        rc, out, err, timed_out = _run_command_bounded(
            _long_running_tree_command(), shell=True, timeout=4
        )
        elapsed = time.monotonic() - start

        self.assertTrue(timed_out, "a ~30s command under a 4s timeout must report timed_out")
        # Bounded: nowhere near the full 30s and certainly not forever. timeout(4)
        # + tree-kill wait(3) + drain(5) gives plenty of headroom under 20s.
        self.assertLess(elapsed, 20, f"timeout path took {elapsed:.1f}s — it was NOT bounded")
        # Whole-tree-kill guarantee: a direct-child-only kill would strand the
        # grandchild (ping/sleep). Nothing we spawned may survive.
        self._assert_no_orphans(before, "timeout path")

    @unittest.skipUnless(_IS_WIN, "copy con is a Windows console builtin")
    def test_incident_copy_con_is_bounded_and_leaves_no_orphan(self):
        """Byte-faithful replay of the 2026-06-06 hang command."""
        before = self._descendant_pids()
        with tempfile.TemporaryDirectory() as d:
            target = os.path.join(d, "InputValidator.java")
            cmd = f'cd /d "{d}" && copy con "{target}" < NUL'
            start = time.monotonic()
            rc, out, err, timed_out = _run_command_bounded(cmd, shell=True, timeout=6)
            elapsed = time.monotonic() - start
        # Whether DEVNULL gives copy con immediate EOF (completes) or it has to be
        # timed-out-and-killed, the only thing that must NEVER happen is the 45-min
        # hang. Assert it returned bounded and left nothing behind.
        self.assertLess(elapsed, 18, f"copy con replay took {elapsed:.1f}s — it HUNG instead of being bounded")
        self._assert_no_orphans(before, "copy con incident")

    # ── stdin starvation ─────────────────────────────────────────────────
    def test_stdin_starved_so_interactive_read_gets_eof(self):
        if _IS_WIN:
            cmd = 'set /p X=Prompt: & echo GOT_MARKER'
        else:
            cmd = "read X; echo GOT_MARKER"
        start = time.monotonic()
        rc, out, err, timed_out = _run_command_bounded(cmd, shell=True, timeout=10)
        elapsed = time.monotonic() - start
        self.assertFalse(timed_out, "stdin-reading command blocked — stdin is NOT starved to DEVNULL")
        self.assertIn("GOT_MARKER", out)
        self.assertLess(elapsed, 8)


class ExecuteCommandToolTests(unittest.TestCase):
    """Drive the real ``@tool`` ``execute_command`` through its public ``.invoke``."""

    def test_success_message_wraps_output(self):
        res = execute_command.invoke({"command": "echo tool-bounded-ok"})
        self.assertIn("executed successfully", res)
        self.assertIn("tool-bounded-ok", res)

    def test_timeout_message_steers_to_file_creator(self):
        original = tools_mod._EXECUTE_COMMAND_TIMEOUT_SECONDS
        tools_mod._EXECUTE_COMMAND_TIMEOUT_SECONDS = 3  # shrink the REAL ceiling, no mocking the runner
        try:
            start = time.monotonic()
            res = execute_command.invoke({"command": _long_running_tree_command()})
            elapsed = time.monotonic() - start
        finally:
            tools_mod._EXECUTE_COMMAND_TIMEOUT_SECONDS = original

        self.assertIn("timed out", res.lower())
        self.assertIn("file_creator", res)
        self.assertLess(elapsed, 20, f"tool timeout path took {elapsed:.1f}s — not bounded")


if __name__ == "__main__":
    unittest.main()
