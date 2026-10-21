# Tlamatini — Created by Angela López Mendoza · @angelahack1
# Tlamatini Author Banner — do not remove
"""Deterministic scheduling/output regressions found by the October 20 audit.

These exercise engine bookkeeping without substituting for the real-shell suite.
The fake transport lets a prompt arrive before a write returns, a valid scheduling
order that is otherwise difficult to reproduce consistently on Windows.
"""
import threading
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from . import terminater_testkit as kit

eng = kit.engine()


class TerminalAuditRegressions(unittest.TestCase):
    def session(self):
        with mock.patch.object(eng._cp, "ConPty"), mock.patch.object(threading.Thread, "start"):
            session = eng.TerminalSession("t1", "cmd", "audit", "", lambda event: None)
        session.pty.alive.return_value = True
        session._on_output("\x1b]133;A\x07C:\\>\x1b]133;B\x07")
        return session

    def hub(self, **kwargs):
        hub = eng.TerminalHub(**kwargs)
        self.addCleanup(hub.shutdown)
        return hub

    def running_output(self, count=3):
        session = self.session()
        session._begin_command("user", "echo output")
        session._on_output("echo output\r\n" + "\r\n".join(f"line-{n:03d}" for n in range(count)))
        return session

    def test_fast_user_command_finishes_before_input_write_returns(self):
        session = self.session()
        def immediate_output(data):
            session._on_output("echo hello\r\nhello\r\n\x1b]133;A\x07C:\\>\x1b]133;B\x07")
            return len(data)
        session._write = immediate_output
        session.user_input("echo hello\r")
        self.assertEqual(session.state, eng.ST_PROMPT)
        self.assertIsNone(session.current)
        self.assertEqual(session.last_command().output, "hello")
        self.assertEqual(session.last_command().source, "user")

    def test_live_output_limit_discloses_more(self):
        result = self.running_output().read(limit=4)
        self.assertEqual(result["output"], "line")
        self.assertTrue(result["more"])
        self.assertTrue(result["truncated"])

    def test_live_output_unlimited_read_honours_offset(self):
        session = self.running_output()
        complete = session.read(limit=0)["output"]
        self.assertEqual(session.read(limit=0, offset=5)["output"], complete[5:])

    def test_scrolled_out_output_is_flagged_without_dropping_another_line(self):
        session = self.session()
        session.screen.max_scrollback = 30
        session._begin_command("user", "echo output")
        session._on_output("echo output\r\n" + "\r\n".join(f"line-{n:03d}" for n in range(150)))
        self.assertGreater(session.screen.dropped, 0)
        result = session.read(limit=0)
        self.assertTrue(result["truncated"])
        first_retained = session.screen._row_text(session.screen.dropped)[0].strip()
        self.assertEqual(result["output"].splitlines()[0], first_retained)
        self.assertTrue(session.read("all", limit=0)["truncated"])

    def test_shell_exit_preserves_the_whole_command_output(self):
        session = self.running_output(250)
        session.pty.exit_code.return_value = 7
        session._on_exit()
        result = session.read(limit=0)
        self.assertIn("line-000", result["output"])
        self.assertIn("line-249", result["output"])
        self.assertNotIn("echo output", result["output"])
        self.assertFalse(result["truncated"])

    def test_nonzero_shell_exit_is_failure(self):
        session = self.running_output()
        session.pty.exit_code.return_value = 7
        session._on_exit()
        result = self.hub()._finish_wait(session, session.last_command(), {"reason": "exited"}, {}, 0)
        self.assertEqual(result["status"], "command_failed")
        self.assertFalse(result["success"])
        self.assertEqual(result["exit_code"], 7)

    def test_ambiguous_title_cannot_select_a_terminal(self):
        hub = self.hub()
        space = hub.space("audit")
        for sid in ("t1", "t2"):
            space.sessions[sid] = SimpleNamespace(id=sid, title="build", state=eng.ST_CLOSED)
        for title in ("build", "bui"):
            with self.subTest(title=title):
                with self.assertRaises(eng.TerminaterError) as caught:
                    hub._get(space, title)
                self.assertEqual(caught.exception.code, "ambiguous_terminal")
        self.assertEqual(hub._get(space, "t2").id, "t2")

    def test_simultaneous_open_reserves_capacity_before_starting_shell(self):
        hub = self.hub(max_terminals=1)
        entered, release = threading.Event(), threading.Event()
        results = []
        def construct(sid, kind, title, cwd, emit, **kwargs):
            entered.set()
            release.wait(5)
            return SimpleNamespace(id=sid, state=eng.ST_PROMPT, cv=threading.Condition(),
                                   info=lambda: {"id": sid}, close=lambda **kw: None)
        with mock.patch.object(eng, "TerminalSession", side_effect=construct), \
                mock.patch.object(eng._cp, "conpty_available", return_value=True):
            first = threading.Thread(target=lambda: results.append(hub.call("open", {"user": "audit"})))
            first.start()
            self.assertTrue(entered.wait(2))
            try:
                second = hub.call("open", {"user": "audit"})
            finally:
                release.set()
                first.join(6)
            self.assertEqual(second.get("code"), "too_many", second)
            self.assertEqual(len(hub.space("audit").sessions), 1)

    def test_named_keys_cannot_interrupt_another_ai_typing_operation(self):
        session = self.session()
        session._type_lock.acquire()
        try:
            with self.assertRaises(eng.TerminaterError) as caught:
                session.send_keys("enter")
            self.assertEqual(caught.exception.code, "busy")
            session.pty.write.assert_not_called()
        finally:
            session._type_lock.release()

    def test_pending_jobs_are_not_evicted_to_admit_more_jobs(self):
        hub = self.hub()
        with mock.patch.object(threading.Thread, "start"):
            first = hub.submit("wait", {"user": "audit"})
            for _ in range(199):
                hub.submit("wait", {"user": "audit"})
            with self.assertRaises(eng.TerminaterError) as caught:
                hub.submit("wait", {"user": "audit"})
            self.assertEqual(caught.exception.code, "too_many_jobs")
        self.assertEqual(hub.job(first)["state"], "running")

    def test_action_pins_the_automatic_user_before_opening(self):
        hub = self.hub()
        hub.space("alice")
        hub.add_listener("alice", lambda event: None)
        def opening(*args, **kwargs):
            hub.add_listener("bob", lambda event: None)
            hub.space("bob").last_used = hub.space("alice").last_used + 1
            return {"terminal": {"id": "t1"}}
        with mock.patch.object(hub, "open", side_effect=opening), \
                mock.patch.object(hub, "_a_type", side_effect=lambda params: {"selected": hub.resolve_user(params.get("user"))}):
            result = hub.call("run", {"text": "echo hello"})
        self.assertEqual(result["selected"], "alice")

    def test_failed_shell_start_releases_capacity(self):
        hub = self.hub(max_terminals=1)
        with mock.patch.object(eng, "TerminalSession", side_effect=OSError("launch failed")):
            for _ in range(2):
                result = hub.call("open", {"user": "audit"})
                self.assertEqual(result["code"], "internal")
        self.assertEqual(hub.space("audit").opening, 0)

    def test_completed_jobs_can_be_replaced_without_evicting_running_jobs(self):
        hub = self.hub()
        with mock.patch.object(threading.Thread, "start"):
            first = hub.submit("wait", {"user": "audit"})
            second = hub.submit("wait", {"user": "audit"})
            for _ in range(198):
                hub.submit("wait", {"user": "audit"})
            hub.jobs[second]["state"] = "done"
            newest = hub.submit("wait", {"user": "audit"})
        self.assertEqual(hub.job(first)["state"], "running")
        self.assertEqual(hub.job(newest)["state"], "running")
        self.assertEqual(hub.job(second)["state"], "unknown")

    def test_successful_shell_exit_stays_successful(self):
        session = self.running_output()
        session.pty.exit_code.return_value = 0
        session._on_exit()
        result = self.hub()._finish_wait(session, session.last_command(), {"reason": "exited"}, {}, 0)
        self.assertEqual(result["status"], "completed")
        self.assertTrue(result["success"])

    def test_shell_exit_during_typing_is_not_changed_back_to_prompt(self):
        session = self.session()
        def exit_while_writing(data):
            session._set_state(eng.ST_EXITED)
            return 0
        session._write = exit_while_writing
        with kit.FastTyping():
            session.type_text("echo hello")
        self.assertEqual(session.state, eng.ST_EXITED)

    def test_stop_before_typing_writes_no_keys(self):
        session = self.session()
        cancelled = threading.Event()
        cancelled.set()
        with self.assertRaises(eng.TerminaterError):
            session.type_text("echo hello", cancel_event=cancelled)
        session.pty.write.assert_not_called()

    def test_failed_enter_write_is_not_reported_as_a_submitted_command(self):
        session = self.session()
        def transport(data):
            if data == "\r":
                session._set_state(eng.ST_EXITED)
                return 0
            return len(data)
        session._write = transport
        with kit.FastTyping():
            result = session.type_text("echo hello")
        self.assertTrue(result["aborted"])
        self.assertEqual(session.state, eng.ST_EXITED)


class TerminalCallerRegressions(unittest.TestCase):
    def test_flow_stop_targets_its_terminal_even_after_focus_changes(self):
        from . import terminal_hub
        from .prompt_flow_panel_runtime import PromptFlowPanelRuntime

        runtime = PromptFlowPanelRuntime.__new__(PromptFlowPanelRuntime)
        runtime.user = SimpleNamespace(pk=7)
        runtime._terminal_id = "t1"
        with mock.patch.object(terminal_hub, "run_action") as action:
            runtime._abort_terminal()
        action.assert_called_once_with("abort", {"user": "7", "terminal": "t1"}, True)

    def test_wrapped_chat_pins_the_authenticated_user_after_model_assignments(self):
        from . import context_governor, terminal_hub, tools
        from .chat_agent_registry import WRAPPED_CHAT_AGENT_BY_TOOL_NAME
        import yaml

        spec = WRAPPED_CHAT_AGENT_BY_TOOL_NAME["chat_agent_terminater"]
        token = context_governor.bind_user(7)
        try:
            with tempfile.TemporaryDirectory() as directory:
                config = Path(directory) / "config.yaml"
                template = Path(__file__).parent / "agents/terminater/config.yaml"
                for assigned in ("", "; user='999'"):
                    config.write_bytes(template.read_bytes())
                    with mock.patch.object(tools, "_find_template_agent_by_dir_name", return_value={"agent_dir": str(template.parent)}), \
                            mock.patch.object(tools, "create_isolated_runtime_copy", return_value=("audit", directory, str(Path(directory) / "agent.log"))), \
                            mock.patch.object(terminal_hub, "ensure_ready"), \
                            mock.patch.object(tools, "resolve_runtime_script_path", return_value=None):
                        tools._launch_wrapped_chat_agent(spec, "action='list'" + assigned)
                    with self.subTest(assigned=assigned):
                        self.assertEqual(str(yaml.safe_load(config.read_text(encoding="utf-8"))["user"]), "7")
        finally:
            context_governor.unbind_user(token)
