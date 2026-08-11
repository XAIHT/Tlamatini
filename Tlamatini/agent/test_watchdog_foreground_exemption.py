# ═══════════════════════════════════════════════════════════════════
#   ✦  T L A M A T I N I  ✦   —   "one who knows"
#
#   Created by  Angela López Mendoza   ·   @angelahack1
#   Developer · Architect · Creator of Tlamatini
#
#   Every line of this file was written by Angela López Mendoza.
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


class ForkedWindowCarriesTheKeepAliveMarkerTests(unittest.TestCase):
    """Every forked window must survive, and must ANNOUNCE itself to the reaper.

    TWO agents open a console the user is meant to read: **Executer** and
    **Pythonxer**. Both had the same three defects, and both are pinned here.

    1. ``@pause`` - a pool agent's stdin is NOT an interactive console, so
       ``pause`` sees EOF and returns INSTANTLY: the window flashed and
       vanished while the log claimed success. Replaced by a BOUNDED
       PowerShell ``Start-Sleep`` (needs no stdin).
    2. The hold then looks exactly like a HUNG SHELL to the command watchdog -
       zero CPU, zero I/O - and under the MCP host the console lives on a
       window station ``EnumWindows`` cannot see, so the "owns a visible
       window" exemption does not rescue it. The only thing left is the
       command-line marker in ``orphan_reaper.INTERACTIVE_CONSOLE_MARKERS``.
       The reaper honoured it and this file already MODELLED it, but for a
       while NO production code emitted it.
    3. Waiting on the window instead of on the WORK: Pythonxer blocked on an
       unbounded ``process.wait()``, so a window that really stayed open would
       hang the agent until somebody closed it by hand.

    Source-level on purpose: no Django, no psutil, nothing spawned.
    """

    MARKER = "TLAMATINI_KEEP_CONSOLE_ALIVE"
    AGENTS = ("executer", "pythonxer")

    @classmethod
    def setUpClass(cls):
        cls.here = os.path.dirname(os.path.abspath(__file__))
        cls.reaper_src = os.path.join(cls.here, "orphan_reaper.py")

    def _agent_source(self, agent):
        path = os.path.join(self.here, "agents", agent, agent + ".py")
        if not os.path.isfile(path):
            self.skipTest("not in this tree: %s" % path)
        with open(path, "r", encoding="utf-8") as fh:
            return fh.read()

    def test_every_forked_console_carries_the_marker(self):
        """The cmd.exe that owns the window carries the marker in its argv."""
        import ast
        for agent in self.AGENTS:
            with self.subTest(agent=agent):
                tree = ast.parse(self._agent_source(agent))
                found = False
                for node in ast.walk(tree):
                    if not isinstance(node, ast.List):
                        continue
                    parts = [e.value for e in node.elts
                             if isinstance(e, ast.Constant)
                             and isinstance(e.value, str)]
                    if "cmd.exe" in parts and "/c" in parts:
                        found = found or (self.MARKER in parts)
                self.assertTrue(
                    found,
                    "%s launches its forked console WITHOUT %s - the reaper "
                    "cannot tell it from a hung shell and may kill the window"
                    % (agent, self.MARKER))

    def test_every_hold_carries_the_marker(self):
        """The sleeping grandchild carries it too, in its own command line."""
        for agent in self.AGENTS:
            with self.subTest(agent=agent):
                src = self._agent_source(agent)
                holds = [ln for ln in src.splitlines()
                         if "Start-Sleep -Seconds" in ln]
                self.assertTrue(
                    holds, "%s has no bounded hold - do NOT go back to @pause"
                    % agent)
                self.assertTrue(
                    any(self.MARKER in ln for ln in holds),
                    "%s's PowerShell hold does not carry %s in its own command "
                    "line; a 900s zero-CPU sleep is exactly the hung-shell "
                    "signature" % (agent, self.MARKER))

    def test_no_agent_went_back_to_pause(self):
        """`@pause` must never be WRITTEN into a wrapper again.

        Only the emitted code counts - both files legitimately mention
        ``@pause`` inside the warning comment that explains why it is gone.
        """
        for agent in self.AGENTS:
            with self.subTest(agent=agent):
                src = self._agent_source(agent)
                for bad in ("wf.write('@pause", 'wf.write("@pause'):
                    self.assertNotIn(
                        bad, src,
                        "%s writes @pause again: in a pool agent stdin is not a "
                        "console, so the window will flash and vanish" % agent)

    def test_every_agent_waits_on_the_work_not_on_the_window(self):
        """Learn the result from the SENTINEL, not from a human closing the window.

        That was the actual hang: with the window deliberately held open, an
        agent that blocks until the console disappears waits for a person. The
        wrapper writes the exit code the moment the script ends, so the agent
        can continue while the console stays on screen.

        Note this does NOT demand a timeout. Pythonxer waits unbounded ON
        PURPOSE - a long build may legitimately take hours - and the wrapper's
        own BOUNDED hold is what guarantees the console eventually exits.
        """
        for agent in self.AGENTS:
            with self.subTest(agent=agent):
                src = self._agent_source(agent)
                self.assertIn(
                    "temp_forked_exitcode.txt", src,
                    "%s has no exit-code sentinel, so it can only learn the "
                    "result by waiting for the window to close" % agent)
                self.assertIn(
                    "process.poll()", src,
                    "%s never polls the child, so it cannot notice the console "
                    "going away" % agent)
                self.assertNotIn(
                    "Wait indefinitely for the user to close", src,
                    "%s is back to blocking until a human closes the window"
                    % agent)

    def test_a_bounded_wait_never_reports_a_timeout_as_success(self):
        """If an agent DOES cap its wait, the cap must fail - never succeed.

        Applies only to agents that bound the wait (Executer). Pythonxer waits
        unbounded by design, so it has no timeout branch to get wrong; the
        assertion below would be vacuous there and is skipped rather than
        faked.
        """
        checked = 0
        for agent in self.AGENTS:
            src = self._agent_source(agent)
            if "timed out (300s limit)" not in src:
                continue          # unbounded on purpose - nothing to assert
            with self.subTest(agent=agent):
                checked += 1
                lines = src.splitlines()
                idx = [i for i, ln in enumerate(lines)
                       if "timed out (300s limit)" in ln]
                for i in idx:
                    # Walk forward to the FIRST `return` after the log line and
                    # require it to be False. Proximity would be too naive: one
                    # handler kills the process first, so `return False` is
                    # several lines below - correct code that a "within N
                    # lines" check wrongly reddened.
                    verdict = None
                    for ln in lines[i + 1:i + 25]:
                        stripped = ln.strip()
                        if stripped.startswith("def ") or stripped.startswith("class "):
                            break
                        if stripped.startswith("return"):
                            verdict = stripped
                            break
                    self.assertIsNotNone(
                        verdict,
                        "%s logs a timeout and then falls through without "
                        "returning a verdict" % agent)
                    self.assertEqual(
                        verdict, "return False",
                        "%s logs a timeout but then returns %r - a script that "
                        "never finished would be reported as SUCCESS"
                        % (agent, verdict))
        self.assertGreater(
            checked, 0,
            "no agent bounds its wait any more; if that is deliberate, delete "
            "this test instead of leaving it silently vacuous")

    def test_the_marker_actually_satisfies_the_reaper(self):
        """The marker is not a magic string: it must MATCH the reaper.

        The reaper lowercases the command line and looks for a substring, so
        this asserts the real relation instead of repeating a literal - if
        INTERACTIVE_CONSOLE_MARKERS is ever renamed, this goes red.
        """
        import ast
        with open(self.reaper_src, "r", encoding="utf-8") as fh:
            tree = ast.parse(fh.read())
        markers = None
        for node in ast.walk(tree):
            if not isinstance(node, ast.Assign):
                continue
            names = [t.id for t in node.targets if isinstance(t, ast.Name)]
            if "INTERACTIVE_CONSOLE_MARKERS" not in names:
                continue
            if isinstance(node.value, (ast.Tuple, ast.List)):
                markers = [e.value for e in node.value.elts
                           if isinstance(e, ast.Constant)]
        self.assertTrue(markers, "INTERACTIVE_CONSOLE_MARKERS not found")
        self.assertTrue(
            any(m in self.MARKER.lower() for m in markers),
            "%r does not match any reaper marker %r - the exemption would "
            "never fire" % (self.MARKER, markers))



class LongRunningMarkerExemptionTests(unittest.TestCase):
    """A declared long-running job must outlive the hang test, and an
    undeclared one must still be reaped."""

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

    @staticmethod
    def _executer_source():
        import os
        p = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                         "agents", "executer", "executer.py")
        with open(p, encoding="utf-8") as fh:
            return fh.read()

    # ── the watchdog honours the declaration ────────────────────────────────
    def test_a_declared_long_job_survives_far_past_the_grace(self):
        killed = []
        shell = FakeProc(8100, "cmd.exe",
                         cmdline=["cmd.exe", "/c", "job.bat", "TLAMATINI_LONG_RUNNING"])
        wd = self._watchdog([shell], killed)
        with mock.patch.object(command_watchdog, "_visible_window_pids",
                               return_value=set()):
            wd.scan_and_reap()                                   # baseline
            self.clock.advance(wd.hang_grace_seconds * 50)       # way past 8 minutes
            for _ in range(20):                                  # and idle throughout
                wd.scan_and_reap()
        self.assertEqual(killed, [],
                         "a DECLARED long-running job must never be reaped as a hang")

    def test_an_undeclared_idle_shell_is_still_reaped(self):
        # The exemption must stay a declaration, never a blanket amnesty -
        # otherwise the watchdog stops protecting anything at all.
        killed = []
        shell = FakeProc(8101, "cmd.exe", cmdline=["cmd.exe", "/c", "job.bat"])
        wd = self._watchdog([shell], killed)
        with mock.patch.object(command_watchdog, "_visible_window_pids",
                               return_value=set()):
            wd.scan_and_reap()
            self.clock.advance(wd.hang_grace_seconds + wd.tick_seconds + 1)
            wd.scan_and_reap()
        self.assertEqual(killed, [8101],
                         "an UNDECLARED hung shell must still be reaped")

    def test_detection_is_case_insensitive_and_fails_safe(self):
        self.assertTrue(command_watchdog._carries_long_running_marker(
            FakeProc(1, "cmd.exe",
                     cmdline=["cmd.exe", "/c", "x", "tlamatini_LONG_running"])))
        self.assertFalse(command_watchdog._carries_long_running_marker(
            FakeProc(2, "cmd.exe", cmdline=["cmd.exe", "/c", "x"])))

        class _Unreadable(FakeProc):
            def cmdline(self):
                raise RuntimeError("access denied")

        self.assertFalse(command_watchdog._carries_long_running_marker(_Unreadable(3)),
                         "an unreadable command line must FAIL SAFE to 'not declared', "
                         "so a genuinely hung shell is still reaped")

    # ── the launcher actually sends it ──────────────────────────────────────
    def test_executer_declares_its_headless_job(self):
        lines = [ln for ln in self._executer_source().splitlines()
                 if ln.strip().startswith("cmd = [script_path")]
        self.assertTrue(lines, "could not find Executer's script-mode command")
        for ln in lines:
            self.assertIn("TLAMATINI_LONG_RUNNING", ln,
                          "Executer's headless job must DECLARE itself long-running "
                          "or the watchdog reaps it after ~4 idle minutes")

    def test_the_users_own_python_argv_is_left_alone(self):
        lines = [ln for ln in self._executer_source().splitlines()
                 if "get_python_command() + [script_path" in ln]
        self.assertTrue(lines, "could not find Executer's python-file command")
        for ln in lines:
            self.assertNotIn("TLAMATINI_LONG_RUNNING", ln,
                             "never inject an argv element into the USER's script")

    def test_the_token_sent_is_the_token_honoured(self):
        """Closes the loop so the two sides can never drift apart."""
        import re as _re
        m = _re.search(r"cmd = \[script_path,\s*['\"]([^'\"]+)['\"]\]",
                       self._executer_source())
        self.assertIsNotNone(m, "Executer's script-mode command carries no token")
        token = m.group(1)
        self.assertTrue(
            command_watchdog._carries_long_running_marker(
                FakeProc(4242, "cmd.exe", cmdline=["cmd.exe", "/c", "j.bat", token])),
            "the token the launcher SENDS (%r) is not one the watchdog HONOURS (%r) "
            "- the two halves of the contract have drifted apart" % (
                token, command_watchdog.LONG_RUNNING_MARKERS))

if __name__ == "__main__":
    unittest.main(verbosity=2)
