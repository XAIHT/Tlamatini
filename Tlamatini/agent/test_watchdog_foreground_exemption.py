# ═══════════════════════════════════════════════════════════════════
#   ✦  T L A M A T I N I  ✦   —   "one who knows"
#
#   Crafted with heart by  Angela   ·   @angelahack1
#   Developer · Architect · Creator of Tlamatini
#
#   Every line of this file was written by Angela.
# ═══════════════════════════════════════════════════════════════════
#   Tlamatini Author Banner — do not remove (releases scrub the name automatically)
"""Complete automated tests for the generalized "eagle-eye" foreground-console
exemption shared by ``command_watchdog`` and ``orphan_reaper``.

The contract under test:
  * A FORKED FOREGROUND window — a shell that owns a VISIBLE console (so it is
    either WAITING ON THE USER'S KEYBOARD or showing output the user can see),
    opened by ANY agent — is NEVER reaped/killed, however long it sits idle.
  * The process running INSIDE such a window (sibling of the conhost) is spared
    too, via its parent shell.
  * A genuinely HEADLESS, HALTED shell (no window, no progress) is STILL killed.
  * A process making CPU/IO progress is never killed (existing rule).
  * A NON-shell process (e.g. a python agent waiting on stdin with no window) is
    not a watchdog target at all — the watchdog only judges cmd/powershell/pwsh.

Coverage is two-layered: deterministic fakes for the decision logic, plus REAL
spawned processes (a real CREATE_NEW_CONSOLE window vs a real headless shell) so
the detector is exercised against actual Windows windows, not just mocks.
"""
import os
import subprocess
import sys
import time
import unittest
from unittest import mock

from agent import command_watchdog, orphan_reaper

IS_WINDOWS = sys.platform.startswith("win")


class _Clock:
    """Manually-advanced monotonic clock so grace/idle windows are crossed
    instantly instead of sleeping through real seconds."""

    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t

    def advance(self, dt):
        self.t += dt


class _CpuTimes:
    def __init__(self, user):
        self.user = user
        self.system = 0.0


class _IoCounters:
    def __init__(self, total):
        self.read_bytes = total
        self.write_bytes = 0
        self.other_bytes = 0


class FakeProc:
    """Duck-typed psutil.Process good enough for the detector and the watchdog's
    subtree-progress sampling."""

    def __init__(self, pid, name="cmd.exe", cmdline=None, children=None,
                 parent=None, cpu=0.0, io=0.0):
        self.pid = pid
        self._name = name
        self._cmdline = list(cmdline) if cmdline is not None else [name]
        self._children = children or []
        self._parent = parent
        self.cpu = cpu
        self.io = io

    def name(self):
        return self._name

    def cmdline(self):
        return list(self._cmdline)

    def parent(self):
        return self._parent

    def children(self, recursive=False):
        if not recursive:
            return list(self._children)
        out, stack = [], list(self._children)
        while stack:
            c = stack.pop()
            out.append(c)
            stack.extend(c.children())
        return out

    def cpu_times(self):
        return _CpuTimes(self.cpu)

    def io_counters(self):
        return _IoCounters(self.io)


def _recording_killer(sink):
    def killer(proc, errors):
        sink.append(int(proc.pid))
        return 1
    return killer


# ───────────────────────── detector unit tests ─────────────────────────────

class ForegroundConsoleDetectorTests(unittest.TestCase):
    OUR = 1000
    PROT = {1000}

    def _det(self, proc, visible):
        return orphan_reaper.is_protected_foreground_console(proc, visible, self.PROT)

    def test_forked_window_cmd_owns_console_via_conhost(self):
        conhost = FakeProc(9001, "conhost.exe")
        cmd = FakeProc(9000, "cmd.exe", cmdline=["cmd.exe", "/c", "x.bat"], children=[conhost])
        conhost._parent = cmd
        self.assertTrue(self._det(cmd, {9001}))

    def test_inner_process_spared_via_parent_window(self):
        conhost = FakeProc(9001, "conhost.exe")
        inner = FakeProc(9002, "python.exe", cmdline=["python.exe", "run.py"])
        cmd = FakeProc(9000, "cmd.exe", children=[conhost, inner])
        conhost._parent = inner._parent = cmd
        self.assertTrue(self._det(inner, {9001}))

    def test_generic_forked_window_no_marker(self):
        # Any agent's forked window: no Tlamatini marker, recognised purely by the
        # visible console it owns.
        conhost = FakeProc(8001, "conhost.exe")
        cmd = FakeProc(8000, "cmd.exe", cmdline=["cmd.exe", "/c", "temp_forked_wrapper.bat"],
                       children=[conhost])
        conhost._parent = cmd
        self.assertTrue(self._det(cmd, {8001}))

    def test_headless_hung_shell_not_spared(self):
        hung = FakeProc(7000, "cmd.exe", cmdline=["cmd.exe", "/c", "powershell", "-Command", "x"],
                        parent=FakeProc(self.OUR, "python.exe"))
        self.assertFalse(self._det(hung, set()))

    def test_app_child_with_protected_parent_window_not_spared(self):
        # Parent owns the app window but parent IS our pid -> must NOT blanket-spare.
        appkid = FakeProc(6000, "cmd.exe", parent=FakeProc(self.OUR, "Tlamatini.exe"))
        self.assertFalse(self._det(appkid, {self.OUR}))

    def test_marker_fallback_runner(self):
        p = FakeProc(5000, "python.exe", cmdline=["python.exe", "_tg_login_runner.py"])
        self.assertTrue(self._det(p, set()))

    def test_marker_fallback_keep_console_token(self):
        p = FakeProc(5001, "cmd.exe", cmdline=["cmd.exe", "/c", "w.bat", "TLAMATINI_KEEP_CONSOLE_ALIVE"])
        self.assertTrue(self._det(p, set()))

    def test_failsafe_false_when_proc_unreadable(self):
        class Bad:
            pid = 1

            def cmdline(self):
                raise RuntimeError("boom")

            def children(self, recursive=False):
                raise RuntimeError("boom")

            def parent(self):
                raise RuntimeError("boom")

        self.assertFalse(orphan_reaper.is_protected_foreground_console(Bad(), set(), self.PROT))

    def test_no_visible_pids_and_no_marker_is_false(self):
        plain = FakeProc(4000, "cmd.exe", cmdline=["cmd.exe", "/c", "build"])
        self.assertFalse(self._det(plain, set()))


# ─────────────────── watchdog integration (mocked windows) ──────────────────

class WatchdogForegroundExemptionTests(unittest.TestCase):
    """Drives the REAL ``CommandWatchdog.scan_and_reap`` with an injected
    descendant list + recording killer + a manual clock, mocking only the
    EnumWindows snapshot so the visible/headless distinction is deterministic."""

    def _watchdog(self, descendants, killed):
        return command_watchdog.CommandWatchdog(
            our_pid=1,
            tick_seconds=2.0,
            hang_grace_seconds=10.0,
            required_idle_ticks=1,
            descendant_provider=lambda: list(descendants),
            killer=_recording_killer(killed),
            clock=self.clock,
        )

    def setUp(self):
        self.clock = _Clock()

    def test_visible_foreground_console_is_never_killed(self):
        killed = []
        shell = FakeProc(9000, "cmd.exe", cmdline=["cmd.exe", "/c", "x.bat", "TLAMATINI_KEEP_CONSOLE_ALIVE"])
        wd = self._watchdog([shell], killed)
        with mock.patch.object(command_watchdog, "_visible_window_pids", return_value={9000}):
            wd.scan_and_reap()                                  # baseline
            self.clock.advance(wd.hang_grace_seconds + wd.tick_seconds + 1)
            for _ in range(6):                                  # many idle ticks
                wd.scan_and_reap()
        self.assertEqual(killed, [], "a visible foreground console must never be reaped")

    def test_headless_halted_shell_is_killed(self):
        killed = []
        shell = FakeProc(7000, "cmd.exe", cmdline=["cmd.exe", "/c", "hang"])
        wd = self._watchdog([shell], killed)
        with mock.patch.object(command_watchdog, "_visible_window_pids", return_value=set()):
            wd.scan_and_reap()                                  # baseline
            self.clock.advance(wd.hang_grace_seconds + wd.tick_seconds + 1)
            wd.scan_and_reap()                                  # idle + past grace -> kill
        self.assertEqual(killed, [7000], "a headless halted shell must be reaped")

    def test_working_shell_is_never_killed(self):
        killed = []
        shell = FakeProc(7001, "cmd.exe", cmdline=["cmd.exe", "/c", "build"], cpu=0.0)
        wd = self._watchdog([shell], killed)
        with mock.patch.object(command_watchdog, "_visible_window_pids", return_value=set()):
            wd.scan_and_reap()                                  # baseline cpu=0
            shell.cpu = 5.0                                     # it burned CPU between ticks
            self.clock.advance(wd.hang_grace_seconds + wd.tick_seconds + 1)
            wd.scan_and_reap()                                  # progress -> not idle -> spared
        self.assertEqual(killed, [], "a process making progress must never be reaped")

    def test_non_shell_waiting_on_input_is_ignored(self):
        # A python agent waiting on stdin with NO window: not cmd/powershell, so the
        # watchdog never judges it at all (it only reaps console interpreters).
        killed = []
        py = FakeProc(7002, "python.exe", cmdline=["python.exe", "agent.py"])
        wd = self._watchdog([py], killed)
        with mock.patch.object(command_watchdog, "_visible_window_pids", return_value=set()):
            wd.scan_and_reap()
            self.clock.advance(wd.hang_grace_seconds + wd.tick_seconds + 1)
            wd.scan_and_reap()
        self.assertEqual(killed, [], "the watchdog only targets cmd/powershell/pwsh")


# ───────────────────── real spawned-process tests (Windows) ─────────────────

@unittest.skipUnless(IS_WINDOWS, "console-window behaviour is Windows-only")
class WatchdogRealForegroundWindowTests(unittest.TestCase):
    """Spawn REAL processes so the EnumWindows-based detector is exercised against
    actual windows, not mocks."""

    def _term(self, proc):
        try:
            import psutil
            p = psutil.Process(proc.pid)
            for c in p.children(recursive=True):
                try:
                    c.kill()
                except Exception:
                    pass
            p.kill()
        except Exception:
            pass
        try:
            proc.kill()
        except Exception:
            pass
        try:
            proc.wait(timeout=5)
        except Exception:
            pass

    def test_real_forked_console_window_is_detected_as_foreground(self):
        import psutil
        proc = subprocess.Popen(
            ["cmd.exe", "/k", "echo TLAMATINI_TEST_WINDOW & pause"],
            creationflags=subprocess.CREATE_NEW_CONSOLE,
        )
        try:
            time.sleep(1.5)  # let the console + its conhost come up
            visible = orphan_reaper._visible_window_owner_pids()
            self.assertTrue(visible, "EnumWindows should see at least one visible window")
            self.assertTrue(
                orphan_reaper.is_protected_foreground_console(
                    psutil.Process(proc.pid), visible, {os.getpid()}),
                "a real CREATE_NEW_CONSOLE window must be recognised as a foreground console",
            )
        finally:
            self._term(proc)

    def test_real_headless_shell_is_not_foreground(self):
        import psutil
        proc = subprocess.Popen(
            ["cmd.exe", "/c", "pause"],
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            stdin=subprocess.PIPE,
        )
        try:
            time.sleep(1.0)
            visible = orphan_reaper._visible_window_owner_pids()
            self.assertFalse(
                orphan_reaper.is_protected_foreground_console(
                    psutil.Process(proc.pid), visible, {os.getpid()}),
                "a headless CREATE_NO_WINDOW shell must NOT look like a foreground console",
            )
        finally:
            self._term(proc)

    def test_real_forked_window_survives_a_full_watchdog_scan(self):
        import psutil
        proc = subprocess.Popen(
            ["cmd.exe", "/k", "echo TLAMATINI_TEST_WINDOW & pause"],
            creationflags=subprocess.CREATE_NEW_CONSOLE,
        )
        killed = []
        try:
            time.sleep(1.5)
            clock = _Clock()
            wd = command_watchdog.CommandWatchdog(
                our_pid=os.getpid(),
                tick_seconds=2.0,
                hang_grace_seconds=10.0,
                required_idle_ticks=1,
                descendant_provider=lambda: [psutil.Process(proc.pid)],
                killer=_recording_killer(killed),
                clock=clock,
            )
            wd.scan_and_reap()                              # real EnumWindows runs here
            clock.advance(wd.hang_grace_seconds + wd.tick_seconds + 1)
            for _ in range(3):
                wd.scan_and_reap()
            self.assertEqual(killed, [], "the watchdog must not kill a real visible forked console")
        finally:
            self._term(proc)


if __name__ == "__main__":
    unittest.main(verbosity=2)
