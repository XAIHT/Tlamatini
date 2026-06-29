# ═══════════════════════════════════════════════════════════════════
#   ✦  T L A M A T I N I  ✦   —   "one who knows"
#
#   Crafted with heart by  Angela   ·   @angelahack1
#   Developer · Architect · Creator of Tlamatini
#
#   Every line of this file was written by Angela.
# ═══════════════════════════════════════════════════════════════════
#   Tlamatini Author Banner — do not remove (releases scrub the name automatically)
"""
Hard, real-scenario tests for agent/command_watchdog.py.

The watchdog never kills on elapsed time — only on lack of PROGRESS, measured
as CPU-time + I/O bytes across the whole process subtree. These tests pin that
contract, with special attention to the false-positive cases that matter:

  * a long-running CPU-bound job → spared (CPU keeps climbing),
  * an I/O-bound job at ~0 % CPU → spared (bytes keep moving),
  * a launcher shell whose CHILD does the work → spared (subtree is busy),
  * a process we cannot sample → spared (fail safe),
and only a genuinely stuck (no CPU, no I/O) shell is reaped.

Two layers: deterministic fake-process unit ticks driving the REAL decision
logic, plus real-process tests that spawn actual PowerShell and prove the real
watchdog (real psutil enumeration + real tree-kill) behaves correctly.
"""
from __future__ import annotations

import os
import subprocess
import sys
import time
import types
import unittest
from typing import List

from agent.command_watchdog import CommandWatchdog, _SHELL_NAMES


class _FakeProc:
    """Minimal psutil.Process stand-in with monotonic CPU / I/O counters.

    ``cpu_rate`` = CPU seconds added per cpu_times() call (per tick).
    ``io_rate``  = bytes added per io_counters() call (per tick).
    A flat (rate 0) counter == an idle/stuck process; a positive rate == work.
    """

    def __init__(self, pid, name, cpu_rate=0.0, io_rate=0, children=None):
        self.pid = pid
        self._name = name
        self._cpu = 0.0
        self._cpu_rate = float(cpu_rate)
        self._io = 0.0
        self._io_rate = float(io_rate)
        self._children = children or []
        self.killed = False
        self.terminated = False

    def name(self):
        return self._name

    def cpu_times(self):
        v = self._cpu
        self._cpu += self._cpu_rate
        return types.SimpleNamespace(user=v, system=0.0)

    def io_counters(self):
        v = self._io
        self._io += self._io_rate
        return types.SimpleNamespace(read_bytes=v, write_bytes=0.0, other_bytes=0.0)

    def children(self, recursive=False):
        return list(self._children)

    def terminate(self):
        self.terminated = True

    def kill(self):
        self.killed = True

    def wait(self, timeout=None):
        return 0


class _Unsampleable(_FakeProc):
    def cpu_times(self):
        raise RuntimeError("access denied")

    def io_counters(self):
        raise RuntimeError("access denied")


class _Clock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t

    def advance(self, dt):
        self.t += dt


def _make_wd(provider, clock, **kw):
    killed_roots: List[int] = []

    def killer(proc, errors):
        proc.killed = True
        killed_roots.append(proc.pid)
        return 1

    defaults = dict(
        our_pid=999999,
        tick_seconds=10.0,
        hang_grace_seconds=100.0,
        required_idle_ticks=2,
        progress_cpu_seconds=0.10,
        progress_io_bytes=65536,
        descendant_provider=provider,
        killer=killer,
        clock=clock,
    )
    defaults.update(kw)
    wd = CommandWatchdog(**defaults)
    # Neutralize real ancestor/console protection for deterministic unit tests
    # (the real protection set is exercised by test_protected_pid_never_killed).
    wd._protected = {wd.our_pid}
    return wd, killed_roots


def _run_ticks(wd, clock, n, dt=40):
    """Advance the clock and tick n times; return all killed pids."""
    killed = []
    for _ in range(n):
        clock.advance(dt)
        killed += wd.scan_and_reap()
    return killed


class CommandWatchdogUnitTests(unittest.TestCase):
    def test_stuck_shell_no_cpu_no_io_is_killed(self):
        """The incident: a shell making zero CPU and zero I/O progress past the
        grace window gets its tree killed."""
        clock = _Clock()
        ps = _FakeProc(101, "powershell.exe", cpu_rate=0.0, io_rate=0)
        wd, killed = _make_wd(lambda: [ps], clock,
                              hang_grace_seconds=30.0, required_idle_ticks=2)
        wd.scan_and_reap()                 # birth/baseline tick — no judgment
        killed += _run_ticks(wd, clock, 3, dt=20)
        self.assertIn(101, killed)
        self.assertTrue(ps.killed)

    def test_long_cpu_bound_job_is_never_killed(self):
        """A real build/install/compile (CPU climbing) is spared no matter how
        long it runs."""
        clock = _Clock()
        ps = _FakeProc(102, "cmd.exe", cpu_rate=5.0, io_rate=0)  # busy
        wd, killed = _make_wd(lambda: [ps], clock,
                              hang_grace_seconds=10.0, required_idle_ticks=2)
        wd.scan_and_reap()
        killed += _run_ticks(wd, clock, 10, dt=60)
        self.assertEqual(killed, [])
        self.assertFalse(ps.killed)

    def test_io_bound_low_cpu_job_is_never_killed(self):
        """A download / clone / big write: ~0 % CPU but bytes keep moving →
        spared. This is the case a CPU-only check would wrongly kill."""
        clock = _Clock()
        ps = _FakeProc(103, "powershell.exe", cpu_rate=0.0, io_rate=5_000_000)
        wd, killed = _make_wd(lambda: [ps], clock,
                              hang_grace_seconds=10.0, required_idle_ticks=2)
        wd.scan_and_reap()
        killed += _run_ticks(wd, clock, 10, dt=60)
        self.assertEqual(killed, [])
        self.assertFalse(ps.killed)

    def test_idle_shell_with_busy_child_is_never_killed(self):
        """A launcher shell at 0 % CPU whose CHILD does the real work is judged
        by the SUBTREE, so the busy child keeps the whole tree alive. This is
        the exact 'cmd.exe → python.exe' false-positive the subtree rule fixes."""
        clock = _Clock()
        busy_child = _FakeProc(2001, "python.exe", cpu_rate=7.0, io_rate=0)
        shell = _FakeProc(104, "cmd.exe", cpu_rate=0.0, io_rate=0, children=[busy_child])
        wd, killed = _make_wd(lambda: [shell], clock,
                              hang_grace_seconds=10.0, required_idle_ticks=2)
        wd.scan_and_reap()
        killed += _run_ticks(wd, clock, 10, dt=60)
        self.assertEqual(killed, [])
        self.assertFalse(shell.killed)

    def test_busy_then_stuck_is_spared_while_working_then_killed(self):
        """A job that works for a long time then truly stalls: spared for the
        entire working phase, reaped only after it stops making progress."""
        clock = _Clock()
        ps = _FakeProc(105, "powershell.exe", cpu_rate=5.0, io_rate=0)
        wd, killed = _make_wd(lambda: [ps], clock,
                              hang_grace_seconds=10.0, required_idle_ticks=3)
        wd.scan_and_reap()                          # baseline
        busy_phase = _run_ticks(wd, clock, 5, dt=40)  # working → never killed
        self.assertEqual(busy_phase, [])
        self.assertFalse(ps.killed)

        ps._cpu_rate = 0.0                          # now it stalls for good
        stalled_phase = _run_ticks(wd, clock, 8, dt=40)
        self.assertIn(105, stalled_phase)
        self.assertTrue(ps.killed)

    def test_not_killed_before_grace_even_if_idle(self):
        """Idle but still within the grace window → never killed yet."""
        clock = _Clock()
        ps = _FakeProc(106, "powershell.exe", cpu_rate=0.0, io_rate=0)
        wd, killed = _make_wd(lambda: [ps], clock,
                              hang_grace_seconds=1000.0, required_idle_ticks=1)
        wd.scan_and_reap()
        killed += _run_ticks(wd, clock, 5, dt=30)   # age maxes ~150s < 1000s
        self.assertEqual(killed, [])

    def test_non_shell_child_is_ignored(self):
        clock = _Clock()
        py = _FakeProc(107, "python.exe", cpu_rate=0.0, io_rate=0)
        wd, killed = _make_wd(lambda: [py], clock,
                              hang_grace_seconds=10.0, required_idle_ticks=1)
        wd.scan_and_reap()
        killed += _run_ticks(wd, clock, 5, dt=60)
        self.assertFalse(py.killed)

    def test_protected_pid_never_killed(self):
        clock = _Clock()
        ps = _FakeProc(108, "powershell.exe", cpu_rate=0.0, io_rate=0)
        wd, killed = _make_wd(lambda: [ps], clock,
                              hang_grace_seconds=10.0, required_idle_ticks=1)
        wd._protected = {wd.our_pid, 108}
        wd.scan_and_reap()
        killed += _run_ticks(wd, clock, 6, dt=60)
        self.assertFalse(ps.killed)

    def test_unsampleable_process_is_treated_as_working(self):
        """If we cannot read CPU or I/O at all, assume it is working — never
        kill what we cannot measure."""
        clock = _Clock()
        ps = _Unsampleable(109, "powershell.exe")
        wd, killed = _make_wd(lambda: [ps], clock,
                              hang_grace_seconds=10.0, required_idle_ticks=1)
        wd.scan_and_reap()
        killed += _run_ticks(wd, clock, 6, dt=60)
        self.assertFalse(ps.killed)

    def test_child_that_disappears_drops_bookkeeping(self):
        clock = _Clock()
        ps = _FakeProc(110, "powershell.exe", cpu_rate=0.0, io_rate=0)
        present = [ps]
        wd, killed = _make_wd(lambda: list(present), clock,
                              hang_grace_seconds=10.0, required_idle_ticks=5)
        wd.scan_and_reap()
        self.assertIn(110, wd._tracked)
        present.clear()
        wd.scan_and_reap()
        self.assertNotIn(110, wd._tracked)

    def test_provider_exception_is_swallowed(self):
        clock = _Clock()

        def boom():
            raise RuntimeError("psutil exploded")

        wd, killed = _make_wd(boom, clock)
        self.assertEqual(wd.scan_and_reap(), [])

    def test_shell_name_set_is_sane(self):
        self.assertIn("powershell.exe", _SHELL_NAMES)
        self.assertIn("cmd.exe", _SHELL_NAMES)
        self.assertNotIn("python.exe", _SHELL_NAMES)
        self.assertNotIn("conhost.exe", _SHELL_NAMES)


@unittest.skipUnless(sys.platform.startswith("win"), "real PowerShell behaviour is Windows-specific")
class CommandWatchdogRealProcessTests(unittest.TestCase):
    """Prove the real watchdog (real psutil enumeration + real tree-kill)
    reaps a stuck shell but spares a working one."""

    def _spawn(self, ps_command, stdin=subprocess.DEVNULL):
        try:
            return subprocess.Popen(
                ["powershell", "-NoProfile", "-Command", ps_command],
                stdin=stdin, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
        except FileNotFoundError:
            self.skipTest("powershell not on PATH")

    def _watchdog(self):
        return CommandWatchdog(
            our_pid=os.getpid(),
            tick_seconds=0.05,
            hang_grace_seconds=0.5,
            required_idle_ticks=2,
            progress_cpu_seconds=0.05,
            progress_io_bytes=65536,
        )

    def test_real_stuck_powershell_is_killed(self):
        # An idle sleep: zero CPU, zero I/O — the stuck-shell signature.
        proc = self._spawn("Start-Sleep -Seconds 600")
        self.addCleanup(lambda: proc.poll() is None and proc.kill())
        time.sleep(1.0)
        self.assertIsNone(proc.poll(), "setup: shell should still be running")

        wd = self._watchdog()
        deadline = time.time() + 25.0
        while time.time() < deadline and proc.poll() is None:
            wd.scan_and_reap()
            time.sleep(0.2)
        self.assertIsNotNone(proc.poll(), "watchdog failed to kill the stuck shell within 25s")

    def test_real_cpu_bound_powershell_survives(self):
        # A tight CPU loop: high CPU → must be spared.
        proc = self._spawn("$x=0; while($true){ $x=($x+1)%2147483647 }")
        self.addCleanup(lambda: proc.poll() is None and proc.kill())
        time.sleep(1.0)
        self.assertIsNone(proc.poll())

        wd = self._watchdog()
        end = time.time() + 4.0
        while time.time() < end:
            wd.scan_and_reap()
            time.sleep(0.2)
        self.assertIsNone(proc.poll(), "watchdog wrongly killed a CPU-bound shell")
        proc.kill()

    def test_real_io_bound_powershell_survives(self):
        # Low CPU but continuous disk I/O (append to a temp file in a loop):
        # bytes keep moving → must be spared even though CPU stays low.
        import tempfile
        from agent import path_guard  # respect the app-Temp policy
        try:
            tmp_root = path_guard.get_app_temp_root()
        except Exception:
            tmp_root = tempfile.gettempdir()
        target = os.path.join(tmp_root, "watchdog_io_probe.txt")
        cmd = (
            f"$p='{target}'; while($true) "
            "{ Add-Content -Path $p -Value ('x'*4096); Start-Sleep -Milliseconds 50 }"
        )
        proc = self._spawn(cmd)

        def _cleanup():
            if proc.poll() is None:
                proc.kill()
            try:
                os.remove(target)
            except OSError:
                pass
        self.addCleanup(_cleanup)

        time.sleep(1.0)
        self.assertIsNone(proc.poll())

        wd = self._watchdog()
        end = time.time() + 4.0
        while time.time() < end:
            wd.scan_and_reap()
            time.sleep(0.2)
        self.assertIsNone(proc.poll(), "watchdog wrongly killed an I/O-bound shell")
        proc.kill()


if __name__ == "__main__":
    unittest.main()
