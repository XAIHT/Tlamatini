# Tlamatini — Created by Angela López Mendoza · @angelahack1
# Tlamatini Author Banner — do not remove
"""Terminater engine: the pure logic AND the real shells it hosts.

Two layers, kept apart on purpose:

* **Pure logic** -- kind aliases, the launch command lines, ``<<USER:...>>`` splitting, the
  action table, layout bookkeeping, the job API.  No shell is started, so these run anywhere.
* **Real shells** -- a ConPTY hosting real ``cmd.exe`` / ``powershell.exe`` processes: typing
  one key at a time, exit codes, hung-command detection, hand-over to the user, the advisor,
  watching the user's keys, force-kill of a whole process tree.  Skipped (never faked) on a
  machine without ConPTY.

Typing is sped up with the test-only ``TEST_TIME_SCALE`` of ``terminater_text`` so a large
suite does not take an hour; the latency test turns it back to 1.0 to prove a real delay.
"""
from __future__ import annotations

import base64
import json
import os
import tempfile
import threading
import time
import unittest

from django.test import SimpleTestCase

from . import terminater_testkit as kit

eng = kit.engine()
tx = kit.tx()

U = "engine-test"


def _pid_alive(pid: int) -> bool:
    try:
        import psutil  # type: ignore

        return psutil.pid_exists(int(pid)) and psutil.Process(int(pid)).status() != psutil.STATUS_ZOMBIE
    except Exception:  # noqa: BLE001
        return False


# --------------------------------------------------------------------------- #
# Pure logic                                                                   #
# --------------------------------------------------------------------------- #

class KindTests(SimpleTestCase):
    def test_cmd_aliases(self):
        for value in ("cmd", "CMD", "cmd.exe", "Command Prompt", "commandprompt", "dos", "  cmd  "):
            self.assertEqual(eng.normalize_kind(value), "cmd", value)

    def test_powershell_aliases(self):
        for value in ("powershell", "PS", "powershell.exe", "Windows PowerShell", "posh"):
            self.assertEqual(eng.normalize_kind(value), "powershell", value)

    def test_pwsh_aliases(self):
        for value in ("pwsh", "PWSH.EXE", "PowerShell 7", "powershell7"):
            self.assertEqual(eng.normalize_kind(value), "pwsh", value)

    def test_empty_gives_the_default(self):
        self.assertEqual(eng.normalize_kind(""), "powershell")
        self.assertEqual(eng.normalize_kind(None), "powershell")
        self.assertEqual(eng.normalize_kind("   "), "powershell")

    def test_default_can_be_overridden(self):
        self.assertEqual(eng.normalize_kind("", default="cmd"), "cmd")

    def test_unknown_kind_is_refused_with_a_code(self):
        with self.assertRaises(eng.TerminaterError) as ctx:
            eng.normalize_kind("zsh")
        self.assertEqual(ctx.exception.code, "bad_kind")
        self.assertIn("cmd | powershell | pwsh", str(ctx.exception))

    def test_inner_whitespace_collapses(self):
        self.assertEqual(eng.normalize_kind("command    prompt"), "cmd")

    def test_every_alias_targets_a_known_kind(self):
        self.assertTrue(set(eng.KIND_ALIASES.values()) <= set(eng.KINDS))

    def test_kinds_are_exactly_the_three_documented(self):
        self.assertEqual(eng.KINDS, ("cmd", "powershell", "pwsh"))

    def test_layouts_and_areas(self):
        self.assertEqual(eng.AREAS, ("dock", "full"))
        for name in ("tabs", "tile", "tile-h", "tile-v", "grid"):
            self.assertIn(name, eng.LAYOUTS)


class LaunchTests(SimpleTestCase):
    @unittest.skipUnless(kit.IS_WINDOWS, "needs Windows")
    def test_cmd_launch_line_and_prompt_markers(self):
        line, env = eng.build_shell_launch("cmd")
        self.assertIn("cmd.exe", line.lower())
        self.assertIn("/D /K chcp 65001", line)
        prompt = env["PROMPT"]
        self.assertIn("]133;A", prompt)
        self.assertIn("]133;B", prompt)
        self.assertIn("]9;9;$P", prompt)

    @unittest.skipUnless(kit.IS_WINDOWS, "needs Windows")
    def test_powershell_launch_flags(self):
        line, env = eng.build_shell_launch("powershell", load_profile=False)
        self.assertEqual(env, {})
        self.assertIn("-NoProfile", line)
        self.assertIn("-NoExit", line)
        self.assertIn("-EncodedCommand", line)
        self.assertIn("Bypass", line)

    @unittest.skipUnless(kit.IS_WINDOWS, "needs Windows")
    def test_profile_is_loaded_by_default(self):
        line, _ = eng.build_shell_launch("powershell")
        self.assertNotIn("-NoProfile", line)

    @unittest.skipUnless(kit.IS_WINDOWS, "needs Windows")
    def test_encoded_setup_installs_the_prompt_hook(self):
        line, _ = eng.build_shell_launch("powershell")
        blob = line.rsplit("-EncodedCommand ", 1)[1].strip()
        script = base64.b64decode(blob).decode("utf-16-le")
        self.assertIn("function global:prompt", script)
        self.assertIn("133;D", script)
        self.assertIn("133;A", script)
        self.assertIn("133;B", script)
        self.assertIn("9;9", script)
        # the user's own prompt must be kept and called, never replaced
        self.assertIn("__tl_prev", script)

    @unittest.skipUnless(kit.IS_WINDOWS, "needs Windows")
    def test_setup_turns_off_psreadline_prediction(self):
        self.assertIn("PredictionSource None", eng._PS_SETUP)

    def test_unknown_kind_cannot_launch(self):
        with self.assertRaises(eng.TerminaterError) as ctx:
            eng.build_shell_launch("nosuchshell")
        self.assertEqual(ctx.exception.code, "kind_unavailable")

    def test_unknown_shell_does_not_resolve(self):
        self.assertIsNone(eng._resolve_shell("nosuchshell"))

    def test_available_kinds_is_a_subset(self):
        self.assertTrue(set(eng.available_kinds()) <= set(eng.KINDS))

    @unittest.skipUnless(kit.IS_WINDOWS, "needs Windows")
    def test_windows_always_has_cmd_and_powershell(self):
        self.assertTrue(eng.kind_available("cmd"))
        self.assertTrue(eng.kind_available("powershell"))

    def test_prompt_regexes(self):
        self.assertTrue(eng.PROMPT_RE["cmd"].match("C:\\Users\\angel>"))
        self.assertTrue(eng.PROMPT_RE["cmd"].match("D:\\x y\\z> "))
        self.assertIsNone(eng.PROMPT_RE["cmd"].match("hello>"))
        self.assertTrue(eng.PROMPT_RE["powershell"].match("PS C:\\Windows> "))
        self.assertIsNone(eng.PROMPT_RE["powershell"].match("C:\\Windows>"))

    def test_scrubbed_environment_names_the_secrets(self):
        self.assertIn("TLAMATINI_TERMINATER_TOKEN", eng._SCRUBBED_ENV)
        self.assertIn("DJANGO_SECRET_KEY", eng._SCRUBBED_ENV)


class SplitUserSegmentsTests(SimpleTestCase):
    def test_plain_text_is_one_typed_segment(self):
        self.assertEqual(eng.split_user_segments("dir C:\\"), [("type", "dir C:\\")])

    def test_docstring_example(self):
        self.assertEqual(
            eng.split_user_segments("ping <<USER:host>> -n 2"),
            [("type", "ping "), ("user", "host"), ("type", " -n 2")])

    def test_bare_marker_gets_a_default_hint(self):
        self.assertEqual(eng.split_user_segments("echo <<USER>>"),
                         [("type", "echo "), ("user", "your part")])

    def test_empty_and_none(self):
        self.assertEqual(eng.split_user_segments(""), [("type", "")])
        self.assertEqual(eng.split_user_segments(None), [("type", "")])

    def test_marker_only(self):
        self.assertEqual(eng.split_user_segments("<<USER:who>>"), [("user", "who")])

    def test_two_markers(self):
        out = eng.split_user_segments("scp <<USER:src>> <<USER:dst>>")
        self.assertEqual([k for k, _ in out], ["type", "user", "type", "user"])
        self.assertEqual(out[1][1], "src")
        self.assertEqual(out[3][1], "dst")

    def test_hint_is_stripped(self):
        self.assertEqual(eng.split_user_segments("x <<USER:  host name  >>")[1], ("user", "host name"))

    def test_adjacent_markers_leave_no_empty_typed_segment(self):
        out = eng.split_user_segments("<<USER:a>><<USER:b>>")
        self.assertEqual(out, [("user", "a"), ("user", "b")])

    def test_overlong_hint_is_not_a_marker(self):
        text = "x <<USER:" + "h" * 81 + ">> y"
        self.assertEqual(eng.split_user_segments(text), [("type", text)])

    def test_unclosed_marker_stays_text(self):
        self.assertEqual(eng.split_user_segments("echo <<USER:oops"), [("type", "echo <<USER:oops")])

    def test_text_after_the_last_marker_is_kept(self):
        out = eng.split_user_segments("a <<USER:b>> c d")
        self.assertEqual(out[-1], ("type", " c d"))


class CommandRecordTests(SimpleTestCase):
    def _record(self, output="", **kw):
        rec = eng.CommandRecord(7, "tlamatini")
        rec.text = "echo hi"
        rec.output = output
        for key, value in kw.items():
            setattr(rec, key, value)
        return rec

    def test_a_fresh_record_is_running_with_no_exit_code(self):
        data = self._record().public()
        self.assertEqual(data["state"], "running")
        self.assertIsNone(data["exit_code"])
        self.assertFalse(data["exit_known"])
        self.assertEqual(data["id"], 7)
        self.assertEqual(data["source"], "tlamatini")
        self.assertEqual(data["command"], "echo hi")

    def test_exit_code_shows_once_known(self):
        data = self._record(exit_code=3, exit_known=True).public()
        self.assertEqual(data["exit_code"], 3)

    def test_unknown_exit_code_is_hidden_even_if_set(self):
        data = self._record(exit_code=3, exit_known=False).public()
        self.assertIsNone(data["exit_code"])

    def test_limit_truncates_and_flags_more(self):
        data = self._record("abcdefghij").public(limit=4)
        self.assertEqual(data["output"], "abcd")
        self.assertTrue(data["more"])
        self.assertTrue(data["truncated"])
        self.assertEqual(data["output_chars"], 10)

    def test_offset_skips(self):
        self.assertEqual(self._record("abcdefghij").public(offset=3)["output"], "defghij")

    def test_offset_and_limit(self):
        data = self._record("abcdefghij").public(offset=2, limit=3)
        self.assertEqual(data["output"], "cde")
        self.assertTrue(data["more"])

    def test_no_more_when_it_fits(self):
        data = self._record("abc").public(limit=10)
        self.assertFalse(data["more"])
        self.assertFalse(data["truncated"])

    def test_without_output(self):
        self.assertNotIn("output", self._record("abc").public(with_output=False))

    def test_truncated_flag_is_kept(self):
        self.assertTrue(self._record("abc", truncated=True).public()["truncated"])

    def test_duration_uses_the_end_time(self):
        rec = self._record()
        rec.started = 100.0
        rec.ended = 102.5
        self.assertEqual(rec.duration(), 2.5)

    def test_hung_and_aborted_by_are_reported(self):
        data = self._record(hung=True, aborted_by="ctrl_c").public()
        self.assertTrue(data["hung"])
        self.assertEqual(data["aborted_by"], "ctrl_c")


class ActionTableTests(SimpleTestCase):
    def test_every_action_has_a_handler(self):
        hub = kit.fresh_hub()
        try:
            for name in eng.ACTIONS:
                self.assertTrue(callable(getattr(hub, f"_a_{name}", None)), name)
        finally:
            hub.shutdown()

    def test_no_duplicate_actions(self):
        self.assertEqual(len(eng.ACTIONS), len(set(eng.ACTIONS)))

    def test_every_alias_targets_a_real_action(self):
        hub = kit.fresh_hub()
        try:
            for alias, target in eng._ACTION_ALIASES.items():
                self.assertTrue(callable(getattr(hub, f"_a_{target}", None)), f"{alias}->{target}")
        finally:
            hub.shutdown()

    def test_the_documented_capabilities_exist(self):
        for name in ("run", "open", "type", "send_key", "wait", "read", "abort", "kill", "force_kill",
                     "kill_all", "layout", "watch_user", "warn_user", "handover", "list", "status",
                     "focus", "rename", "clear", "resize", "commands"):
            self.assertIn(name, eng.ACTIONS)

    def test_every_slow_action_has_a_handler(self):
        hub = kit.fresh_hub()
        try:
            for name in hub.SLOW:
                self.assertTrue(callable(getattr(hub, f"_a_{name}", None)), name)
        finally:
            hub.shutdown()

    def test_the_vocabulary_models_use_resolves(self):
        expect = {"execute": "run", "raise": "open", "interrupt": "abort", "ctrl_c": "abort",
                  "terminate": "kill", "destroy": "force_kill", "tile": "layout",
                  "watch": "watch_user", "warn": "warn_user", "ask_user": "handover",
                  "history": "commands", "killall": "kill_all"}
        for alias, target in expect.items():
            self.assertEqual(eng._ACTION_ALIASES[alias], target, alias)


class TruthyAndPrintableTests(SimpleTestCase):
    def test_truthy_strings(self):
        for value in ("", "0", "false", "False", "no", "off", "none", "null", "  FALSE "):
            self.assertFalse(eng._truthy(value), repr(value))
        for value in ("1", "true", "yes", "on", "anything"):
            self.assertTrue(eng._truthy(value), repr(value))

    def test_truthy_non_strings(self):
        self.assertTrue(eng._truthy(True))
        self.assertFalse(eng._truthy(False))
        self.assertFalse(eng._truthy(None))
        self.assertFalse(eng._truthy(0))
        self.assertTrue(eng._truthy(2))

    def test_printable_names_the_special_keys(self):
        self.assertEqual(eng._printable("ls\r"), "ls<Enter>")
        self.assertEqual(eng._printable("\x03"), "<Ctrl+C>")
        self.assertEqual(eng._printable("\x1b[A\x1b[B"), "<Up><Down>")
        self.assertEqual(eng._printable("\x1b[C\x1b[D"), "<Right><Left>")
        self.assertEqual(eng._printable("\x1b[3~"), "<Del>")
        self.assertEqual(eng._printable("\x7f"), "<Backspace>")
        self.assertEqual(eng._printable("\t"), "<Tab>")
        self.assertEqual(eng._printable("\x1b"), "<Esc>")

    def test_printable_leaves_text_alone(self):
        self.assertEqual(eng._printable("héllo ñ"), "héllo ñ")

    def test_printable_shows_unknown_controls_as_hex(self):
        self.assertEqual(eng._printable("\x01"), "<0x01>")


class HubLogicTests(SimpleTestCase):
    """The hub's bookkeeping, with no shell started."""

    def setUp(self):
        self.hub = kit.fresh_hub()

    def tearDown(self):
        self.hub.shutdown()

    def test_max_terminals_never_drops_below_one(self):
        hub = eng.TerminalHub(max_terminals=0)
        try:
            self.assertEqual(hub.max_terminals, 1)
        finally:
            hub.shutdown()

    def test_an_empty_hub_lists_nothing(self):
        res = self.hub.call("list", {"user": U})
        self.assertTrue(res["ok"])
        self.assertEqual(res["status"], "listed")
        self.assertEqual(res["terminals"], [])
        self.assertEqual(res["max_terminals"], 6)
        self.assertIsInstance(res["available_kinds"], list)

    def test_the_default_ui_state(self):
        ui = self.hub.call("list", {"user": U})["ui"]
        self.assertEqual(ui["layout"], "tabs")
        self.assertEqual(ui["area"], "dock")
        self.assertFalse(ui["visible"])
        self.assertEqual(ui["focus"], "")

    def test_status_reports_conpty(self):
        res = self.hub.call("status", {"user": U})
        self.assertIn("conpty", res)
        self.assertIsInstance(res["conpty"], bool)

    def test_unknown_action_is_refused_and_lists_the_valid_ones(self):
        res = self.hub.call("dance", {"user": U})
        self.assertFalse(res["ok"])
        self.assertEqual(res["status"], "refused")
        self.assertEqual(res["code"], "unknown_action")
        self.assertIn("watch_user", res["message"])

    def test_empty_or_none_action_is_refused(self):
        self.assertEqual(self.hub.call("", {})["code"], "unknown_action")
        self.assertEqual(self.hub.call(None, None)["code"], "unknown_action")

    def test_action_names_are_normalised(self):
        res = self.hub.call("Kill-All", {"user": U})
        self.assertTrue(res["ok"])
        self.assertEqual(res["action"], "kill_all")
        res = self.hub.call("  KILL ALL ", {"user": U})
        self.assertEqual(res["action"], "kill_all")

    def test_aliases_are_applied(self):
        self.assertEqual(self.hub.call("ctrl_c", {"user": U})["action"], "abort")
        self.assertEqual(self.hub.call("Force Kill", {"user": U})["action"], "force_kill")

    def test_acting_on_a_missing_terminal_is_refused_not_raised(self):
        for action in ("type", "send_key", "wait", "read", "commands", "abort", "kill", "force_kill",
                       "focus", "rename", "clear", "resize", "watch_user", "warn_user", "handover"):
            with self.subTest(action=action):
                res = self.hub.call(action, {"user": U, "terminal": "nope", "text": "x", "message": "m"})
                self.assertFalse(res["ok"], res)
                self.assertEqual(res["status"], "refused")
                self.assertEqual(res["code"], "no_terminal")

    def test_call_never_raises_on_garbage_params(self):
        for params in (None, {}, {"terminal": object()}, {"wait_seconds": "abc"}):
            res = self.hub.call("read", params)
            self.assertIn("ok", res)

    def test_kill_all_on_an_empty_hub(self):
        res = self.hub.call("kill_all", {"user": U})
        self.assertTrue(res["ok"])
        self.assertEqual(res["closed"], [])

    def test_layout_names_and_synonyms(self):
        for given, stored in (("tabs", "tabs"), ("tile", "tile"), ("grid", "grid"),
                              ("horizontal", "tile-h"), ("vertical", "tile-v"), ("tiled", "tile"),
                              ("tabbed", "tabs"), ("tab", "tabs"), ("side-by-side", "tile-h"),
                              ("stacked", "tile-v")):
            res = self.hub.call("layout", {"user": U, "layout": given})
            self.assertTrue(res["ok"], given)
            self.assertEqual(res["ui"]["layout"], stored, given)

    def test_a_bad_layout_is_refused(self):
        res = self.hub.call("layout", {"user": U, "layout": "spiral"})
        self.assertEqual(res["code"], "bad_layout")

    def test_area_names_and_synonyms(self):
        for given, stored in (("dock", "dock"), ("full", "full"), ("canvas", "full"), ("whole", "full"),
                              ("fill", "full"), ("lower", "dock"), ("bottom", "dock")):
            res = self.hub.call("layout", {"user": U, "area": given})
            self.assertEqual(res["ui"]["area"], stored, given)

    def test_a_bad_area_is_refused(self):
        self.assertEqual(self.hub.call("layout", {"user": U, "area": "moon"})["code"], "bad_area")

    def test_changing_layout_shows_the_dock(self):
        res = self.hub.call("layout", {"user": U, "layout": "grid"})
        self.assertTrue(res["ui"]["visible"])

    def test_show_false_hides_it(self):
        self.hub.call("layout", {"user": U, "layout": "grid"})
        for value in (False, "false", "hide", "off", "no", "0"):
            self.hub.call("layout", {"user": U, "show": True})
            res = self.hub.call("layout", {"user": U, "show": value})
            self.assertFalse(res["ui"]["visible"], value)

    def test_show_true_shows_it(self):
        res = self.hub.call("layout", {"user": U, "show": "yes"})
        self.assertTrue(res["ui"]["visible"])

    def test_layout_is_per_user(self):
        self.hub.call("layout", {"user": "a", "layout": "grid"})
        self.assertEqual(self.hub.call("list", {"user": "b"})["ui"]["layout"], "tabs")

    def test_layout_broadcasts_to_listeners(self):
        seen = []
        self.hub.add_listener(U, seen.append)
        self.hub.call("layout", {"user": U, "layout": "tile", "area": "full"})
        events = [e for e in seen if e.get("t") == "ui"]
        self.assertTrue(events)
        self.assertEqual(events[-1]["ui"]["layout"], "tile")
        self.assertEqual(events[-1]["ui"]["area"], "full")

    def test_resolve_user_keeps_an_explicit_name(self):
        self.assertEqual(self.hub.resolve_user("alice"), "alice")

    def test_resolve_user_defaults_to_local(self):
        self.assertEqual(self.hub.resolve_user("auto"), "local")
        self.assertEqual(self.hub.resolve_user(None), "local")

    def test_resolve_user_follows_the_only_connected_user(self):
        self.hub.add_listener("alice", lambda e: None)
        self.assertEqual(self.hub.resolve_user("auto"), "alice")
        self.assertEqual(self.hub.resolve_user(""), "alice")
        self.assertEqual(self.hub.resolve_user("active"), "alice")

    def test_resolve_user_prefers_the_most_recently_used_connected_user(self):
        self.hub.add_listener("alice", lambda e: None)
        self.hub.add_listener("bob", lambda e: None)
        time.sleep(0.02)
        self.hub.space("alice")
        self.assertEqual(self.hub.resolve_user("auto"), "alice")
        time.sleep(0.02)
        self.hub.space("bob")
        self.assertEqual(self.hub.resolve_user("auto"), "bob")

    def test_space_is_created_once_and_isolated(self):
        a1, a2, b = self.hub.space("a"), self.hub.space("a"), self.hub.space("b")
        self.assertIs(a1, a2)
        self.assertIsNot(a1, b)

    def test_space_without_create_raises(self):
        with self.assertRaises(eng.TerminaterError) as ctx:
            self.hub.space("ghost", create=False)
        self.assertEqual(ctx.exception.code, "no_space")

    def test_listeners_add_and_remove(self):
        seen = []
        self.hub.add_listener(U, seen.append)
        self.hub.broadcast(U, {"t": "x"})
        self.hub.remove_listener(U, seen.append)
        self.hub.broadcast(U, {"t": "y"})
        self.assertEqual([e["t"] for e in seen], ["x"])

    def test_removing_a_listener_of_an_unknown_user_is_harmless(self):
        self.hub.remove_listener("nobody", lambda e: None)

    def test_a_failing_listener_does_not_stop_the_others(self):
        seen = []

        def boom(_event):
            raise RuntimeError("listener failure")

        self.hub.add_listener(U, boom)
        self.hub.add_listener(U, seen.append)
        self.hub.broadcast(U, {"t": "z"})
        self.assertEqual(seen, [{"t": "z"}])

    def test_num_clamps_and_defaults(self):
        num = eng.TerminalHub._num
        self.assertEqual(num({"x": "abc"}, "x", 5, 1, 10), 5)
        self.assertEqual(num({"x": 99}, "x", 5, 1, 10), 10)
        self.assertEqual(num({"x": -3}, "x", 5, 1, 10), 1)
        self.assertEqual(num({}, "x", 5, 1, 10), 5)
        self.assertEqual(num({"x": "7"}, "x", 5, 1, 10), 7)
        self.assertEqual(num({"x": None}, "x", 5, 1, 10), 5)

    def test_text_prefers_base64(self):
        text = eng.TerminalHub._text
        self.assertEqual(text({"text": "plain"}), "plain")
        self.assertEqual(text({"text": "plain", "text_b64": base64.b64encode("héllo".encode()).decode()}), "héllo")
        self.assertEqual(text({}), "")
        self.assertEqual(text({"text": None}), "")

    def test_bad_base64_is_refused_with_a_code(self):
        with self.assertRaises(eng.TerminaterError) as ctx:
            eng.TerminalHub._text({"text_b64": "@@@not base64@@@"})
        self.assertEqual(ctx.exception.code, "bad_text")

    def test_live_pids_of_an_empty_hub(self):
        self.assertEqual(self.hub.live_pids(), [])

    def test_shutdown_twice_is_harmless(self):
        self.hub.shutdown()
        self.hub.shutdown()

    def test_job_api_runs_an_action_off_thread(self):
        job = self.hub.submit("list", {"user": U})
        self.assertTrue(job)
        done = kit.wait_until(lambda: self.hub.job(job)["state"] == "done", timeout=10)
        self.assertTrue(done)
        result = self.hub.job(job)["result"]
        self.assertEqual(result["status"], "listed")

    def test_job_unknown_id(self):
        self.assertEqual(self.hub.job("nope"), {"state": "unknown"})

    def test_job_ids_are_unique(self):
        ids = {self.hub.submit("list", {"user": U}) for _ in range(5)}
        self.assertEqual(len(ids), 5)
        kit.wait_until(lambda: all(self.hub.job(i)["state"] == "done" for i in ids), timeout=10)

    def test_a_job_reports_a_refusal_as_its_result(self):
        job = self.hub.submit("type", {"user": U, "terminal": "nope", "text": "x"})
        kit.wait_until(lambda: self.hub.job(job)["state"] == "done", timeout=10)
        self.assertEqual(self.hub.job(job)["result"]["code"], "no_terminal")


# --------------------------------------------------------------------------- #
# Real shells                                                                  #
# --------------------------------------------------------------------------- #

@unittest.skipUnless(kit.conpty_ok(), "ConPTY is not available on this machine")
class RealShellTests(SimpleTestCase):
    """One hub, two long-lived shells (PowerShell + cmd), and a lot of real commands."""

    hub = None
    fast = None
    events: list = []
    ps_id = ""
    cmd_id = ""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.fast = kit.FastTyping(0.04)
        cls.fast.__enter__()
        cls.hub = kit.fresh_hub(max_terminals=10, hang_seconds=6.0)
        cls.events = []
        cls._lock = threading.Lock()

        def sink(event):
            with cls._lock:
                cls.events.append(event)

        cls.hub.add_listener(U, sink)
        ps = cls.hub.call("open", {"user": U, "kind": "powershell", "title": "ps main", "load_profile": False})
        cmd = cls.hub.call("open", {"user": U, "kind": "cmd", "title": "cmd main"})
        cls.ps_open, cls.cmd_open = ps, cmd
        cls.ps_id = ps.get("terminal_id", "")
        cls.cmd_id = cmd.get("terminal_id", "")

    @classmethod
    def tearDownClass(cls):
        try:
            cls.hub.shutdown()
        finally:
            cls.fast.__exit__(None, None, None)
            super().tearDownClass()

    def setUp(self):
        self._recover(self.ps_id, "powershell")
        self._recover(self.cmd_id, "cmd")
        # The prompt marker arrives a moment before PSReadLine starts reading: real typing has a
        # human lead-in, but this suite types ~25x faster, so it lets the shell settle first.
        time.sleep(0.25)

    # -- helpers ------------------------------------------------------------
    def _recover(self, tid, kind):
        """Bring a shared terminal back to an idle prompt, whatever a failed test left behind."""
        sp = self.hub.space(U)
        session = sp.sessions.get(tid)
        if session is None or session.state in (eng.ST_EXITED, eng.ST_CLOSED):
            res = self.hub.call("open", {"user": U, "kind": kind, "title": f"{kind} main",
                                         "load_profile": False})
            new = res.get("terminal_id", "")
            if kind == "cmd":
                type(self).cmd_id = new
            else:
                type(self).ps_id = new
            return
        if session.state != eng.ST_PROMPT:
            session.abort()
            session.send_keys("ctrl+c")
            session.wait(timeout=6)
        session.user_input("\x03") if session.state == eng.ST_PROMPT and session.user_line() else None

    def run_in(self, text, terminal=None, **kw):
        params = {"user": U, "terminal": terminal or self.ps_id, "text": text, "wait_seconds": 40}
        params.update(kw)
        return self.hub.call("run", params)

    def ps(self, text, **kw):
        return self.run_in(text, self.ps_id, **kw)

    def cmd(self, text, **kw):
        return self.run_in(text, self.cmd_id, **kw)

    def session(self, tid=None):
        return self.hub.space(U).sessions[tid or self.ps_id]

    def seen(self, kind):
        with self._lock:
            return [e for e in self.events if e.get("t") == kind]

    def cursor(self, tid=None):
        """The watch_user cursor that means 'nothing before now' (keys are numbered per terminal)."""
        session = self.session(tid)
        return max([k[0] for k in session.user_keys] + [s[0] for s in session.user_submitted] + [0])

    def new_terminal(self, kind="powershell", **kw):
        res = self.hub.call("open", {"user": U, "kind": kind, **kw})
        self.assertEqual(res.get("status"), "opened", res)
        return res["terminal_id"]

    def close_quietly(self, tid):
        try:
            self.hub.call("force_kill", {"user": U, "terminal": tid})
        except Exception:  # noqa: BLE001
            pass

    # -- opening ------------------------------------------------------------
    def test_powershell_opens_at_a_prompt(self):
        info = self.ps_open["terminal"]
        self.assertEqual(self.ps_open["status"], "opened")
        self.assertEqual(info["kind"], "powershell")
        self.assertEqual(info["title"], "ps main")
        self.assertGreater(info["pid"], 0)
        self.assertTrue(self.session().pty_alive())
        self.assertEqual(self.session().state, eng.ST_PROMPT)

    def test_cmd_opens_at_a_prompt(self):
        info = self.cmd_open["terminal"]
        self.assertEqual(info["kind"], "cmd")
        self.assertEqual(info["title"], "cmd main")
        self.assertGreater(info["pid"], 0)
        self.assertEqual(self.session(self.cmd_id).state, eng.ST_PROMPT)

    def test_the_two_shells_are_different_processes(self):
        self.assertNotEqual(self.session().pid, self.session(self.cmd_id).pid)

    def test_terminal_lookup_by_id_title_partial_title_and_active(self):
        sp = self.hub.space(U)
        self.assertIs(self.hub._get(sp, self.ps_id), self.session())
        self.assertIs(self.hub._get(sp, "ps main"), self.session())
        self.assertIs(self.hub._get(sp, "PS MAIN"), self.session())
        self.assertIs(self.hub._get(sp, "ps ma"), self.session())
        self.assertIs(self.hub._get(sp, "active"), sp.sessions[sp.active])

    def test_list_reports_both_terminals(self):
        res = self.hub.call("list", {"user": U})
        ids = [t["id"] for t in res["terminals"]]
        self.assertIn(self.ps_id, ids)
        self.assertIn(self.cmd_id, ids)
        for info in res["terminals"]:
            for key in ("id", "kind", "title", "cwd", "pid", "state", "alive", "cols", "rows",
                        "commands", "suspected_hung", "awaiting_input", "advisor"):
                self.assertIn(key, info)

    def test_status_reports_conpty_true(self):
        self.assertTrue(self.hub.call("status", {"user": U})["conpty"])

    def test_opening_announces_itself_to_listeners(self):
        self.assertTrue(self.seen("opened"))

    def test_open_with_a_working_directory(self):
        folder = tempfile.mkdtemp(prefix="termtest_")
        tid = self.new_terminal(cwd=folder, load_profile=False, title="cwd probe")
        try:
            res = self.run_in("(Get-Location).Path", tid)
            self.assertEqual(res["status"], "completed", res)
            self.assertIn(os.path.basename(folder), res["output"])
        finally:
            self.close_quietly(tid)

    def test_a_missing_working_directory_falls_back_to_home(self):
        tid = self.new_terminal(cwd=r"C:\this\path\does\not\exist", load_profile=False)
        try:
            self.assertEqual(self.hub.space(U).sessions[tid].state, eng.ST_PROMPT)
        finally:
            self.close_quietly(tid)

    def test_an_unknown_kind_is_refused_when_opening(self):
        res = self.hub.call("open", {"user": U, "kind": "zsh"})
        self.assertEqual(res["code"], "bad_kind")

    def test_the_terminal_limit_is_enforced(self):
        hub = kit.fresh_hub(max_terminals=2)
        try:
            ids = []
            for n in range(2):
                res = hub.call("open", {"user": U, "kind": "cmd", "title": f"c{n}"})
                self.assertEqual(res["status"], "opened")
                ids.append(res["terminal_id"])
            res = hub.call("open", {"user": U, "kind": "cmd"})
            self.assertEqual(res["code"], "too_many")
            hub.call("kill", {"user": U, "terminal": ids[0]})
            res = hub.call("open", {"user": U, "kind": "cmd"})
            self.assertEqual(res["status"], "opened")
        finally:
            hub.shutdown()

    # -- PowerShell commands --------------------------------------------------
    def test_powershell_echo(self):
        res = self.ps('Write-Output "hello world"')
        self.assertEqual(res["status"], "completed", res)
        self.assertTrue(res["success"])
        self.assertIn("hello world", res["output"])
        self.assertEqual(res["command"], 'Write-Output "hello world"')

    def test_powershell_success_has_a_known_zero_exit_code(self):
        res = self.ps("Get-Date | Out-Null")
        self.assertEqual(res["status"], "completed", res)
        self.assertTrue(res["exit_known"])
        self.assertEqual(res["exit_code"], 0)

    def test_powershell_native_exit_code_is_reported(self):
        res = self.ps("cmd /c exit 3")
        self.assertEqual(res["status"], "command_failed", res)
        self.assertFalse(res["success"])
        self.assertEqual(res["exit_code"], 3)

    def test_powershell_another_exit_code(self):
        res = self.ps("cmd /c exit 7")
        self.assertEqual(res["exit_code"], 7)

    def test_powershell_error_stream_is_a_failure(self):
        res = self.ps('Write-Error "boom"')
        self.assertEqual(res["status"], "command_failed", res)
        self.assertIn("boom", res["output"])

    def test_powershell_multiline_output(self):
        res = self.ps('1..5 | ForEach-Object { "row$_" }')
        for n in range(1, 6):
            self.assertIn(f"row{n}", res["output"])

    def test_powershell_unicode_round_trip(self):
        res = self.ps('Write-Output "héllo ñandú"')
        self.assertIn("héllo ñandú", res["output"])

    def test_powershell_special_characters(self):
        res = self.ps("Write-Output 'a\"b $x & | ; c'")
        self.assertIn('a"b $x & | ; c', res["output"])

    def test_powershell_tracks_the_working_directory(self):
        self.ps(r"Set-Location C:\Windows")
        self.assertEqual(self.session().cwd.lower().rstrip("\\"), r"c:\windows")
        self.ps("Set-Location ~")

    def test_a_long_output_is_cut_and_the_rest_can_be_read(self):
        res = self.ps('1..6000 | ForEach-Object { "line$_" }', read_chars=20000, wait_seconds=90)
        self.assertEqual(res["status"], "completed", res)
        self.assertTrue(res["truncated"])
        self.assertTrue(res["more"])
        self.assertGreater(res["output_chars"], 20000)
        rest = self.hub.call("read", {"user": U, "terminal": self.ps_id, "offset": 20000,
                                      "read_chars": 100000})
        self.assertIn("line6000", rest["output"])

    def test_text_b64_runs_like_text(self):
        blob = base64.b64encode(b'Write-Output "from base64"').decode()
        res = self.hub.call("run", {"user": U, "terminal": self.ps_id, "text_b64": blob, "wait_seconds": 30})
        self.assertIn("from base64", res["output"])

    def test_empty_text_is_refused(self):
        res = self.hub.call("type", {"user": U, "terminal": self.ps_id, "text": "   "})
        self.assertEqual(res["code"], "empty_text")

    def test_bad_base64_is_refused_on_a_real_terminal(self):
        res = self.hub.call("type", {"user": U, "terminal": self.ps_id, "text_b64": "@@@"})
        self.assertEqual(res["code"], "bad_text")

    def test_secret_input_is_never_recorded(self):
        res = self.ps("Write-Output 'visible-output'", secret=True)
        self.assertEqual(res["status"], "completed", res)
        self.assertEqual(res["typed"], "")
        self.assertEqual(res["command"], "<hidden>")
        listing = self.hub.call("commands", {"user": U, "terminal": self.ps_id})
        self.assertEqual(listing["commands"][-1]["command"], "<hidden>")

    # -- cmd commands --------------------------------------------------------
    def test_cmd_echo(self):
        res = self.cmd("echo hi from cmd")
        self.assertEqual(res["status"], "completed", res)
        self.assertIn("hi from cmd", res["output"])

    def test_cmd_directory_listing(self):
        res = self.cmd(r"dir C:\Windows\*.ini")
        self.assertEqual(res["status"], "completed", res)
        self.assertIn("win.ini", res["output"].lower())

    def test_cmd_metacharacters_inside_quotes(self):
        res = self.cmd('echo "pipe | amp & ok"')
        self.assertIn("pipe | amp & ok", res["output"])

    def test_cmd_tracks_the_working_directory(self):
        self.cmd(r"cd /d C:\Windows")
        self.assertEqual(self.session(self.cmd_id).cwd.lower().rstrip("\\"), r"c:\windows")
        self.cmd("cd /d %USERPROFILE%")

    def test_cmd_says_honestly_that_it_cannot_know_the_exit_code(self):
        # cmd.exe's prompt cannot carry %ERRORLEVEL%, so the engine never invents one:
        # exit_code stays null and exit_known says so (the tool description tells the model).
        res = self.cmd(r"dir C:\nonexistent_zzz_path")
        self.assertEqual(res["status"], "completed", res)
        self.assertIsNone(res["exit_code"])
        self.assertFalse(res["exit_known"])
        self.assertIn("File Not Found", res["output"])

    def test_cmd_native_exit_code_is_unknown_too(self):
        res = self.cmd("cmd /c exit 5")
        self.assertIsNone(res["exit_code"], res)
        self.assertFalse(res["exit_known"])
        self.assertEqual(res["status"], "completed")

    def test_cmd_runs_a_batch_style_chain(self):
        res = self.cmd("echo one && echo two")
        self.assertIn("one", res["output"])
        self.assertIn("two", res["output"])

    # -- the transcript ----------------------------------------------------
    def test_commands_are_numbered_in_order(self):
        self.ps("Write-Output a1")
        self.ps("Write-Output a2")
        items = self.hub.call("commands", {"user": U, "terminal": self.ps_id})["commands"]
        ids = [c["id"] for c in items]
        self.assertEqual(ids, sorted(ids))
        self.assertEqual(items[-1]["command"], "Write-Output a2")
        self.assertEqual(items[-2]["command"], "Write-Output a1")
        self.assertEqual(items[-1]["source"], "tlamatini")

    def test_read_last_returns_the_last_commands_output(self):
        self.ps("Write-Output readme-1")
        res = self.hub.call("read", {"user": U, "terminal": self.ps_id})
        self.assertIn("readme-1", res["output"])
        self.assertEqual(res["scope"], "command")

    def test_read_a_command_by_number(self):
        self.ps("Write-Output first-one")
        first = self.session().last_command().id
        self.ps("Write-Output second-one")
        res = self.hub.call("read", {"user": U, "terminal": self.ps_id, "which": str(first)})
        self.assertIn("first-one", res["output"])
        self.assertNotIn("second-one", res["output"])

    def test_read_the_visible_screen(self):
        self.ps("Write-Output screen-marker-xyz")
        res = self.hub.call("read", {"user": U, "terminal": self.ps_id, "which": "screen"})
        self.assertIn("screen-marker-xyz", res["output"])
        self.assertEqual(res["scope"], "screen")

    def test_read_everything(self):
        self.ps("Write-Output transcript-marker-abc")
        res = self.hub.call("read", {"user": U, "terminal": self.ps_id, "which": "all", "read_chars": 2_000_000})
        self.assertIn("transcript-marker-abc", res["output"])

    def test_read_with_a_limit(self):
        self.ps('Write-Output ("x" * 500)')
        res = self.hub.call("read", {"user": U, "terminal": self.ps_id, "read_chars": 100})
        self.assertLessEqual(len(res["output"]), 100)
        self.assertTrue(res["more"])

    def test_read_a_missing_command_is_empty_not_an_error(self):
        res = self.hub.call("read", {"user": U, "terminal": self.ps_id, "which": "99999"})
        self.assertEqual(res["output"], "")
        self.assertTrue(res["ok"])

    # -- typing like a person ------------------------------------------------
    def test_typed_text_is_returned_exactly(self):
        res = self.ps("Write-Output 'typed exactly'")
        self.assertEqual(res["typed"], "Write-Output 'typed exactly'")

    def test_text_goes_to_the_shell_one_key_at_a_time(self):
        session = self.session()
        writes = []
        original = session._write

        def spy(data):
            writes.append(data)
            return original(data)

        session._write = spy
        try:
            text = "Write-Output 'one key at a time'"
            res = self.ps(text)
        finally:
            session._write = original
        self.assertEqual(res["status"], "completed", res)
        self.assertGreaterEqual(len(writes), len(text), "typing must not be a paste")
        self.assertLessEqual(max(len(w) for w in writes), 4, "no chunk may carry a whole word")

    def test_typing_takes_real_time_at_the_default_scale(self):
        saved = tx.TEST_TIME_SCALE
        tx.TEST_TIME_SCALE = 1.0
        try:
            started = time.monotonic()
            res = self.ps("echo hi", typing_wpm=160)
            elapsed = time.monotonic() - started
        finally:
            tx.TEST_TIME_SCALE = saved
        self.assertEqual(res["status"], "completed", res)
        self.assertGreater(elapsed, 0.35, "a typist cannot finish 'echo hi' + Enter in a blink")

    def test_a_slower_typist_takes_longer(self):
        saved = tx.TEST_TIME_SCALE
        tx.TEST_TIME_SCALE = 1.0
        try:
            t0 = time.monotonic()
            self.ps("echo abcdef", typing_wpm=160)
            fast = time.monotonic() - t0
            t0 = time.monotonic()
            self.ps("echo abcdef", typing_wpm=30)
            slow = time.monotonic() - t0
        finally:
            tx.TEST_TIME_SCALE = saved
        self.assertGreater(slow, fast)

    def test_typing_without_enter_leaves_the_line_for_the_user(self):
        res = self.hub.call("type", {"user": U, "terminal": self.ps_id, "text": "Write-Output pending",
                                     "submit": False})
        try:
            self.assertEqual(res["status"], "typed", res)
            self.assertTrue(res["success"])
            self.assertIn("pending", res["typed"])
        finally:
            self.session().user_input("\x03")
            self.session().wait(timeout=5)

    def test_typing_without_waiting_returns_immediately(self):
        started = time.monotonic()
        res = self.ps("Start-Sleep 4", wait=False)
        self.assertEqual(res["status"], "started", res)
        self.assertLess(time.monotonic() - started, 3.0)
        self.hub.call("abort", {"user": U, "terminal": self.ps_id})

    def test_a_second_command_while_one_runs_is_refused_as_busy(self):
        self.ps("Start-Sleep 20", wait=False)
        try:
            res = self.hub.call("type", {"user": U, "terminal": self.ps_id, "text": "Write-Output nope"})
            self.assertEqual(res["code"], "busy", res)
        finally:
            self.hub.call("abort", {"user": U, "terminal": self.ps_id})

    # -- waiting, hanging, aborting ---------------------------------------------
    def test_a_silent_command_is_flagged_as_hung(self):
        res = self.ps("Start-Sleep 30", hang_seconds=3, wait_seconds=25)
        try:
            self.assertEqual(res["status"], "hung", res)
            self.assertFalse(res["success"])
            self.assertTrue(self.session().suspected_hung)
        finally:
            self.hub.call("abort", {"user": U, "terminal": self.ps_id})

    def test_abort_after_a_hang_returns_the_prompt(self):
        self.ps("Start-Sleep 30", hang_seconds=3, wait_seconds=25)
        res = self.hub.call("abort", {"user": U, "terminal": self.ps_id})
        self.assertEqual(res["status"], "aborted", res)
        self.assertTrue(res["success"])
        self.assertIn("ctrl_c", res["aborted_by"])
        self.assertEqual(self.session().state, eng.ST_PROMPT)
        again = self.ps("Write-Output 'alive after abort'")
        self.assertIn("alive after abort", again["output"])

    def test_abort_marks_the_command_record(self):
        self.ps("Start-Sleep 30", hang_seconds=3, wait_seconds=25)
        self.hub.call("abort", {"user": U, "terminal": self.ps_id})
        rec = self.session().last_command()
        self.assertEqual(rec.state, "aborted")
        self.assertTrue(rec.aborted_by)

    def test_abort_with_nothing_running(self):
        res = self.hub.call("abort", {"user": U, "terminal": self.ps_id})
        self.assertEqual(res["aborted_by"], "nothing_running")

    def test_wait_times_out_without_killing_the_command(self):
        self.ps("Start-Sleep 12", wait=False)
        try:
            res = self.hub.call("wait", {"user": U, "terminal": self.ps_id, "wait_seconds": 1})
            self.assertEqual(res["status"], "timeout", res)
            self.assertEqual(self.session().state, eng.ST_RUNNING)
        finally:
            self.hub.call("abort", {"user": U, "terminal": self.ps_id})

    def test_wait_returns_when_the_command_finishes(self):
        self.ps("Start-Sleep 2; Write-Output waited-done", wait=False)
        res = self.hub.call("wait", {"user": U, "terminal": self.ps_id, "wait_seconds": 30})
        self.assertEqual(res["status"], "completed", res)
        self.assertIn("waited-done", res["output"])

    def test_wait_for_a_pattern(self):
        self.ps('1..4 | ForEach-Object { "tick$_"; Start-Sleep 1 }', wait=False)
        res = self.hub.call("wait", {"user": U, "terminal": self.ps_id, "wait_seconds": 30,
                                     "pattern": "tick2"})
        try:
            self.assertEqual(res["status"], "completed", res)
            self.assertEqual(res["wait_reason"], "pattern")
        finally:
            self.hub.call("wait", {"user": U, "terminal": self.ps_id, "wait_seconds": 30})

    def test_wait_for_idle_output(self):
        self.ps('"burst"; Start-Sleep 5; "late"', wait=False)
        res = self.hub.call("wait", {"user": U, "terminal": self.ps_id, "until": "idle",
                                     "idle_seconds": 1.5, "wait_seconds": 20})
        try:
            self.assertEqual(res["wait_reason"], "idle", res)
        finally:
            self.hub.call("abort", {"user": U, "terminal": self.ps_id})

    def test_a_program_asking_a_question_is_detected(self):
        res = self.ps("Read-Host 'Continue? (y/n)'", wait_seconds=25)
        try:
            self.assertEqual(res["status"], "operator_required", res)
            self.assertFalse(res["success"])
            self.assertTrue(res.get("awaiting_input"))
            answer = self.hub.call("type", {"user": U, "terminal": self.ps_id, "text": "y",
                                            "wait_seconds": 20})
            self.assertEqual(answer["status"], "completed", answer)
        finally:
            self.hub.call("abort", {"user": U, "terminal": self.ps_id})

    # -- named keys -----------------------------------------------------------
    def test_ctrl_c_stops_a_running_command(self):
        self.ps("Start-Sleep 30", wait=False)
        res = self.hub.call("send_key", {"user": U, "terminal": self.ps_id, "keys": "ctrl+c"})
        self.assertEqual(res["status"], "typed")
        self.assertEqual(res["sent"], 1)
        end = self.hub.call("wait", {"user": U, "terminal": self.ps_id, "wait_seconds": 15})
        self.assertIn(end["status"], ("completed", "command_failed"), end)

    def test_send_key_accepts_sequences(self):
        res = self.hub.call("send_key", {"user": U, "terminal": self.ps_id, "keys": "a b ctrl+c"})
        self.assertEqual(res["sent"], 3)

    def test_unknown_key_names_are_refused(self):
        res = self.hub.call("send_key", {"user": U, "terminal": self.ps_id, "keys": "hyperspace"})
        self.assertEqual(res["code"], "bad_key")

    def test_no_keys_is_refused(self):
        res = self.hub.call("send_key", {"user": U, "terminal": self.ps_id, "keys": ""})
        self.assertEqual(res["code"], "bad_key")

    # -- handing the keyboard to the user --------------------------------------
    def test_handover_waits_for_the_user_then_finishes_the_line(self):
        session = self.session()

        def user_side():
            kit.wait_until(lambda: session.state == eng.ST_AWAITING_USER, timeout=20)
            time.sleep(0.4)
            for ch in "WORLD":
                session.user_input(ch)
                time.sleep(0.05)
            time.sleep(0.3)
            session.user_input("\r")

        thread = threading.Thread(target=user_side, daemon=True)
        thread.start()
        res = self.hub.call("type", {"user": U, "terminal": self.ps_id, "text": 'Write-Output "hello <<USER:who>> tail"',
                                     "wait_seconds": 40, "user_wait_seconds": 30})
        thread.join(timeout=5)
        self.assertEqual(res["status"], "completed", res)
        self.assertIn("WORLD", res["user_part"])
        self.assertIn("hello WORLD tail", res["output"])
        self.assertEqual(res["handover"], "handed_back")

    def test_handover_announces_the_hint(self):
        session = self.session()
        before = len(self.seen("handover"))

        def user_side():
            kit.wait_until(lambda: session.state == eng.ST_AWAITING_USER, timeout=20)
            session.user_input("\r")

        thread = threading.Thread(target=user_side, daemon=True)
        thread.start()
        self.hub.call("handover", {"user": U, "terminal": self.ps_id, "text": "Write-Output <<USER:name please>>",
                                   "hint": "name please", "wait_seconds": 20, "user_wait_seconds": 20})
        thread.join(timeout=5)
        events = self.seen("handover")[before:]
        self.assertTrue(events)
        self.assertEqual(events[0]["hint"], "name please")

    def test_handover_that_nobody_answers_times_out(self):
        res = self.hub.call("handover", {"user": U, "terminal": self.ps_id, "text": "Write-Output <<USER:anyone>>",
                                         "hint": "anyone", "user_wait_seconds": 5, "wait_seconds": 20})
        try:
            self.assertEqual(res["status"], "operator_required", res)
            self.assertEqual(res["reason"], "timeout")
            self.assertFalse(res["success"])
        finally:
            self.session().user_input("\x03")
            self.session().wait(timeout=5)

    # -- watching the user -----------------------------------------------------
    def test_user_keys_are_visible_to_tlamatini_in_real_time(self):
        session = self.session()
        start = self.cursor()
        for ch in "git status":
            session.user_input(ch)
        res = self.hub.call("watch_user", {"user": U, "terminal": self.ps_id, "until": "idle",
                                           "idle_seconds": 0.3, "wait_seconds": 10, "cursor": start})
        try:
            self.assertEqual(res["status"], "observed")
            self.assertEqual(res["watch_reason"], "idle", res)
            self.assertIn("git status", res["keys"])
            self.assertEqual(res["key_count"], len("git status"))
            self.assertEqual(res["submitted"], [])
        finally:
            session.user_input("\x03")

    def test_watch_times_out_when_the_user_is_quiet(self):
        started = time.monotonic()
        res = self.hub.call("watch_user", {"user": U, "terminal": self.ps_id, "wait_seconds": 1,
                                           "cursor": self.session()._key_seq.__next__()})
        self.assertEqual(res["watch_reason"], "timeout")
        self.assertLess(time.monotonic() - started, 4.0)

    def test_watch_cursor_only_returns_new_keys(self):
        session = self.session()
        session.user_input("a")
        first = self.hub.call("watch_user", {"user": U, "terminal": self.ps_id, "until": "key", "wait_seconds": 5})
        session.user_input("b")
        second = self.hub.call("watch_user", {"user": U, "terminal": self.ps_id, "until": "key",
                                              "wait_seconds": 5, "cursor": first["cursor"]})
        try:
            self.assertIn("a", first["keys"])
            self.assertEqual(second["keys"], "b")
            self.assertGreater(second["cursor"], first["cursor"])
        finally:
            session.user_input("\x03")

    def test_a_submitted_user_line_is_seen_and_recorded(self):
        session = self.session()
        start = self.cursor()
        for ch in "Write-Output from-the-user":
            session.user_input(ch)
        session.user_input("\r")
        res = self.hub.call("watch_user", {"user": U, "terminal": self.ps_id, "until": "submit", "wait_seconds": 10,
                                           "cursor": start})
        self.assertEqual(res["watch_reason"], "submitted", res)
        self.assertTrue(res["submitted"])
        self.assertIn("from-the-user", res["submitted"][0]["line"])
        end = self.hub.call("wait", {"user": U, "terminal": self.ps_id, "wait_seconds": 20})
        self.assertIn("from-the-user", end.get("output", ""))
        self.assertEqual(self.session().last_command().source, "user")

    def test_watch_shows_special_keys_by_name(self):
        session = self.session()
        start = self.cursor()
        session.user_input("\x1b[A")
        res = self.hub.call("watch_user", {"user": U, "terminal": self.ps_id, "until": "key", "wait_seconds": 5,
                                           "cursor": start})
        self.assertEqual(res["keys"], "<Up>")
        session.user_input("\x03")

    def test_the_advisor_warns_about_a_dangerous_line_before_enter(self):
        session = self.session()
        before = len(self.seen("warn"))
        for ch in "format c:":
            session.user_input(ch)
        try:
            warned = kit.wait_until(lambda: len(self.seen("warn")) > before, timeout=5)
            self.assertTrue(warned, "typing 'format c:' must raise a warning without pressing Enter")
            item = self.seen("warn")[-1]
            self.assertIn("format c:", item["line"])
            self.assertTrue(item["message"])
            self.assertTrue(session.warnings)
        finally:
            session.user_input("\x03")

    def test_the_advisor_does_not_repeat_itself(self):
        session = self.session()
        for ch in "format c:":
            session.user_input(ch)
        count = len([w for w in session.warnings if w.get("code") != "tlamatini"])
        session._advise()
        session._advise()
        self.assertEqual(len([w for w in session.warnings if w.get("code") != "tlamatini"]), count)
        session.user_input("\x03")

    def test_the_advisor_can_be_turned_off_per_terminal(self):
        tid = self.new_terminal(load_profile=False, advisor=False, title="quiet")
        try:
            session = self.hub.space(U).sessions[tid]
            for ch in "format c:":
                session.user_input(ch)
            time.sleep(0.5)
            self.assertEqual(list(session.warnings), [])
        finally:
            self.close_quietly(tid)

    def test_tlamatini_can_warn_the_user(self):
        before = len(self.seen("warn"))
        res = self.hub.call("warn_user", {"user": U, "terminal": self.ps_id,
                                          "message": "That path looks wrong.", "severity": "danger",
                                          "suggestion": "Use C:\\Users"})
        self.assertEqual(res["status"], "warned")
        events = self.seen("warn")[before:]
        self.assertEqual(events[-1]["severity"], "danger")
        self.assertEqual(events[-1]["source"], "tlamatini")
        self.assertEqual(events[-1]["suggestion"], "Use C:\\Users")

    def test_an_unknown_severity_becomes_a_warning(self):
        self.hub.call("warn_user", {"user": U, "terminal": self.ps_id, "message": "careful", "severity": "critical"})
        self.assertEqual(self.seen("warn")[-1]["severity"], "warning")

    def test_a_warning_needs_a_message(self):
        res = self.hub.call("warn_user", {"user": U, "terminal": self.ps_id, "message": "  "})
        self.assertEqual(res["code"], "empty_text")

    def test_a_warning_shows_the_dock(self):
        self.hub.call("layout", {"user": U, "show": False})
        self.hub.call("warn_user", {"user": U, "terminal": self.ps_id, "message": "look here"})
        self.assertTrue(self.hub.call("list", {"user": U})["ui"]["visible"])

    def test_a_warning_brings_its_terminal_to_the_front(self):
        # a warning in a hidden tab is no warning: the warned terminal becomes the active one
        self.hub.call("focus", {"user": U, "terminal": self.cmd_id})
        self.assertEqual(self.hub.call("list", {"user": U})["active"], self.cmd_id)
        self.hub.call("warn_user", {"user": U, "terminal": self.ps_id, "message": "look here"})
        listed = self.hub.call("list", {"user": U})
        self.assertEqual(listed["active"], self.ps_id)
        self.assertEqual(listed["ui"].get("focus"), self.ps_id)

    # -- the user and Tlamatini sharing the keyboard ------------------------------
    def test_the_user_cannot_type_over_tlamatini_but_can_take_over(self):
        saved = tx.TEST_TIME_SCALE
        tx.TEST_TIME_SCALE = 1.0
        session = self.session()
        outcome = {}

        def typist():
            outcome["res"] = self.hub.call("type", {
                "user": U, "terminal": self.ps_id, "typing_wpm": 20,
                "text": "Write-Output 'this line is long enough to be interrupted by the user'",
                "wait_seconds": 20})

        thread = threading.Thread(target=typist, daemon=True)
        try:
            thread.start()
            self.assertTrue(kit.wait_until(lambda: session.state == eng.ST_TYPING, timeout=10))
            blocked = session.user_input("a")
            self.assertFalse(blocked["accepted"])
            self.assertEqual(blocked["reason"], "tlamatini_typing")
            took = session.user_input("\x1b")
            self.assertTrue(took.get("took_over"))
            thread.join(timeout=15)
            res = outcome.get("res") or {}
            self.assertTrue(res.get("aborted_typing"), res)
            self.assertEqual(res["status"], "aborted")
        finally:
            tx.TEST_TIME_SCALE = saved
            thread.join(timeout=5)
            self.session().user_input("\x03")
            self.session().wait(timeout=5)

    def test_ctrl_c_from_the_user_also_stops_the_typing(self):
        saved = tx.TEST_TIME_SCALE
        tx.TEST_TIME_SCALE = 1.0
        session = self.session()
        outcome = {}

        def typist():
            outcome["res"] = self.hub.call("type", {
                "user": U, "terminal": self.ps_id, "typing_wpm": 20,
                "text": "Write-Output 'typing that the user will cancel with control c'", "wait_seconds": 20})

        thread = threading.Thread(target=typist, daemon=True)
        try:
            thread.start()
            self.assertTrue(kit.wait_until(lambda: session.state == eng.ST_TYPING, timeout=10))
            self.assertTrue(session.user_input("\x03").get("took_over"))
            thread.join(timeout=15)
            self.assertTrue((outcome.get("res") or {}).get("aborted_typing"))
        finally:
            tx.TEST_TIME_SCALE = saved
            thread.join(timeout=5)
            self.session().wait(timeout=5)

    def test_two_typing_requests_cannot_overlap(self):
        saved = tx.TEST_TIME_SCALE
        tx.TEST_TIME_SCALE = 1.0
        session = self.session()
        thread = threading.Thread(target=lambda: self.hub.call("type", {
            "user": U, "terminal": self.ps_id, "typing_wpm": 20, "submit": False,
            "text": "Write-Output 'first typist keeps going for a while'"}), daemon=True)
        try:
            thread.start()
            self.assertTrue(kit.wait_until(lambda: session.state == eng.ST_TYPING, timeout=10))
            with self.assertRaises(eng.TerminaterError) as ctx:
                session.type_text("Write-Output second", wpm=160)
            self.assertEqual(ctx.exception.code, "busy")
        finally:
            session._abort_typing.set()
            thread.join(timeout=15)
            tx.TEST_TIME_SCALE = saved
            self.session().user_input("\x03")

    # -- layout, titles, size ----------------------------------------------------
    def test_resize_changes_the_pseudo_console(self):
        res = self.hub.call("resize", {"user": U, "terminal": self.ps_id, "cols": 100, "rows": 25})
        self.assertTrue(res["success"], res)
        self.assertEqual((res["cols"], res["rows"]), (100, 25))
        self.hub.call("resize", {"user": U, "terminal": self.ps_id, "cols": 120, "rows": 30})

    def test_resize_is_clamped(self):
        res = self.hub.call("resize", {"user": U, "terminal": self.ps_id, "cols": 5, "rows": 1})
        self.assertEqual((res["cols"], res["rows"]), (20, 5))
        res = self.hub.call("resize", {"user": U, "terminal": self.ps_id, "cols": 9999, "rows": 9999})
        self.assertEqual((res["cols"], res["rows"]), (400, 120))
        self.hub.call("resize", {"user": U, "terminal": self.ps_id, "cols": 120, "rows": 30})

    def test_rename_sets_and_announces_the_title(self):
        tid = self.new_terminal(load_profile=False, title="before")
        try:
            res = self.hub.call("rename", {"user": U, "terminal": tid, "title": "after rename"})
            self.assertEqual(res["title"], "after rename")
            self.assertTrue([e for e in self.seen("title_set") if e.get("title") == "after rename"])
            self.assertEqual(self.hub.space(U).sessions[tid].title, "after rename")
        finally:
            self.close_quietly(tid)

    def test_focus_makes_a_terminal_active_and_shows_the_dock(self):
        self.hub.call("layout", {"user": U, "show": False})
        res = self.hub.call("focus", {"user": U, "terminal": self.cmd_id})
        self.assertEqual(res["status"], "focused")
        self.assertEqual(self.hub.space(U).active, self.cmd_id)
        self.assertTrue(res["ui"]["visible"])
        self.hub.call("focus", {"user": U, "terminal": self.ps_id})

    def test_running_in_a_terminal_brings_it_forward(self):
        self.hub.call("focus", {"user": U, "terminal": self.cmd_id})
        self.ps("Write-Output forward")
        self.assertEqual(self.hub.space(U).active, self.ps_id)

    def test_clear_asks_the_browser_to_clear(self):
        before = len(self.seen("clear"))
        self.hub.call("clear", {"user": U, "terminal": self.ps_id})
        self.assertGreater(len(self.seen("clear")), before)

    # -- run opens or reuses -----------------------------------------------------
    def test_run_opens_a_terminal_when_none_matches(self):
        res = self.hub.call("run", {"user": U, "terminal": "brand new one", "kind": "cmd",
                                    "text": "echo opened-by-run", "wait_seconds": 30})
        try:
            self.assertEqual(res["status"], "completed", res)
            self.assertEqual(res["kind"], "cmd")
            self.assertEqual(res["title"], "brand new one")
            self.assertIn("opened-by-run", res["output"])
        finally:
            self.close_quietly(res.get("terminal_id", ""))

    def test_run_with_no_terminal_opens_one(self):
        hub = kit.fresh_hub()
        try:
            res = hub.call("run", {"user": U, "kind": "powershell", "load_profile": False,
                                   "text": "Write-Output fresh", "wait_seconds": 30})
            self.assertEqual(res["status"], "completed", res)
            self.assertEqual(len(hub.call("list", {"user": U})["terminals"]), 1)
        finally:
            hub.shutdown()

    def test_handover_with_no_terminal_opens_one(self):
        # a hand-over is often the first step of a flow: it raises a terminal, as run does
        hub = kit.fresh_hub()
        try:
            res = hub.call("handover", {"user": U, "kind": "powershell", "load_profile": False,
                                        "text": "Write-Output 'hi <<USER:x>>'", "typing_wpm": 160,
                                        "user_wait_seconds": 5, "wait_seconds": 10})
            self.assertNotEqual(res.get("code"), "no_terminal", res)
            self.assertEqual(len(hub.call("list", {"user": U})["terminals"]), 1)
        finally:
            hub.shutdown()

    def test_handover_into_a_terminal_that_does_not_exist_is_still_refused(self):
        hub = kit.fresh_hub()
        try:
            res = hub.call("handover", {"user": U, "terminal": "nope", "text": "x", "user_wait_seconds": 5})
            self.assertEqual(res["code"], "no_terminal", res)
            self.assertEqual(len(hub.call("list", {"user": U})["terminals"]), 0)
        finally:
            hub.shutdown()

    def test_close_after_removes_the_terminal(self):
        res = self.hub.call("run", {"user": U, "terminal": "one shot", "kind": "cmd", "text": "echo bye",
                                    "close_after": True, "wait_seconds": 30})
        self.assertTrue(res.get("closed_after"), res)
        titles = [t["title"] for t in self.hub.call("list", {"user": U})["terminals"]]
        self.assertNotIn("one shot", titles)

    def test_run_replaces_an_exited_terminal(self):
        tid = self.new_terminal(kind="cmd", title="will exit")
        try:
            res = self.run_in("exit", tid, wait_seconds=20)
            self.assertIn(res["status"], ("completed", "command_failed"), res)
            self.assertTrue(kit.wait_until(lambda: self.hub.space(U).sessions[tid].state == eng.ST_EXITED, timeout=10))
            again = self.hub.call("run", {"user": U, "terminal": tid, "kind": "cmd",
                                          "text": "echo reborn", "wait_seconds": 30})
            self.assertEqual(again["status"], "completed", again)
            self.assertNotEqual(again["terminal_id"], tid)
        finally:
            self.close_quietly(tid)

    def test_typing_into_a_dead_shell_is_refused(self):
        tid = self.new_terminal(kind="cmd", title="dead end")
        try:
            self.run_in("exit", tid, wait_seconds=20)
            kit.wait_until(lambda: self.hub.space(U).sessions[tid].state == eng.ST_EXITED, timeout=10)
            res = self.hub.call("type", {"user": U, "terminal": tid, "text": "echo hello"})
            self.assertEqual(res["code"], "terminal_dead", res)
        finally:
            self.close_quietly(tid)

    # -- closing and killing ------------------------------------------------------
    def test_kill_closes_the_shell_and_removes_it(self):
        tid = self.new_terminal(load_profile=False, title="to kill")
        pid = self.hub.space(U).sessions[tid].pid
        res = self.hub.call("kill", {"user": U, "terminal": tid})
        self.assertEqual(res["status"], "killed", res)
        self.assertEqual(res["method"], "graceful")
        self.assertTrue(kit.wait_until(lambda: not _pid_alive(pid), timeout=10), "the shell must be gone")
        self.assertNotIn(tid, [t["id"] for t in self.hub.call("list", {"user": U})["terminals"]])
        self.assertTrue([e for e in self.seen("removed") if e.get("id") == tid])

    def test_kill_interrupts_a_running_command_first(self):
        tid = self.new_terminal(load_profile=False, title="kill busy")
        pid = self.hub.space(U).sessions[tid].pid
        self.run_in("Start-Sleep 60", tid, wait=False)
        res = self.hub.call("kill", {"user": U, "terminal": tid})
        self.assertEqual(res["status"], "killed")
        self.assertTrue(kit.wait_until(lambda: not _pid_alive(pid), timeout=10))

    def test_force_kill_takes_the_whole_process_tree(self):
        tid = self.new_terminal(load_profile=False, title="force me")
        session = self.hub.space(U).sessions[tid]
        pid = session.pid
        self.run_in("ping -n 60 127.0.0.1", tid, wait=False)
        children = kit.wait_until(lambda: session.pty.child_pids(), timeout=15)
        self.assertTrue(children, "the command's own process must exist before the kill")
        res = self.hub.call("force_kill", {"user": U, "terminal": tid})
        self.assertEqual(res["method"], "force")
        self.assertTrue(res["tree_kill_atomic"])
        self.assertTrue(kit.wait_until(lambda: not _pid_alive(pid), timeout=10))
        for child in children:
            self.assertTrue(kit.wait_until(lambda c=child: not _pid_alive(c), timeout=10), f"child {child} survived")

    def test_kill_all_closes_every_terminal_of_the_user(self):
        hub = kit.fresh_hub()
        try:
            ids = [hub.call("open", {"user": U, "kind": "cmd", "title": f"k{n}"})["terminal_id"] for n in range(3)]
            pids = [hub.space(U).sessions[i].pid for i in ids]
            res = hub.call("kill_all", {"user": U})
            self.assertEqual(sorted(res["closed"]), sorted(ids))
            self.assertEqual(hub.call("list", {"user": U})["terminals"], [])
            for pid in pids:
                self.assertTrue(kit.wait_until(lambda p=pid: not _pid_alive(p), timeout=10))
        finally:
            hub.shutdown()

    def test_closing_announces_itself(self):
        tid = self.new_terminal(load_profile=False)
        before = len(self.seen("closed"))
        self.hub.call("kill", {"user": U, "terminal": tid})
        self.assertGreater(len(self.seen("closed")), before)

    def test_shutdown_leaves_no_shell_behind(self):
        hub = kit.fresh_hub()
        ids = [hub.call("open", {"user": U, "kind": kind, "title": kind})["terminal_id"]
               for kind in ("cmd", "powershell")]
        pids = [hub.space(U).sessions[i].pid for i in ids]
        self.assertEqual(sorted(hub.live_pids()), sorted(pids))
        hub.shutdown()
        for pid in pids:
            self.assertTrue(kit.wait_until(lambda p=pid: not _pid_alive(p), timeout=15), f"{pid} survived shutdown")

    # -- independence ---------------------------------------------------------------
    def test_two_terminals_run_at_the_same_time_on_their_own_threads(self):
        results = {}

        def go(name, tid, text):
            results[name] = self.run_in(text, tid)

        threads = [
            threading.Thread(target=go, args=("ps", self.ps_id, "Start-Sleep 2; Write-Output ps-done")),
            threading.Thread(target=go, args=("cmd", self.cmd_id, "ping -n 3 127.0.0.1 >nul & echo cmd-done")),
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=60)
        self.assertIn("ps-done", results["ps"]["output"])
        self.assertIn("cmd-done", results["cmd"]["output"])

    def test_a_blocked_terminal_does_not_block_the_other(self):
        self.ps("Start-Sleep 30", wait=False)
        try:
            res = self.cmd("echo still responsive")
            self.assertIn("still responsive", res["output"])
        finally:
            self.hub.call("abort", {"user": U, "terminal": self.ps_id})

    def test_users_cannot_see_each_others_terminals(self):
        other = self.hub.call("list", {"user": "someone-else"})
        self.assertEqual(other["terminals"], [])
        res = self.hub.call("read", {"user": "someone-else", "terminal": self.ps_id})
        self.assertEqual(res["code"], "no_terminal")

    def test_the_job_api_runs_a_real_command(self):
        job = self.hub.submit("run", {"user": U, "terminal": self.ps_id, "text": "Write-Output job-output",
                                      "wait_seconds": 30})
        self.assertTrue(kit.wait_until(lambda: self.hub.job(job)["state"] == "done", timeout=40))
        self.assertIn("job-output", self.hub.job(job)["result"]["output"])

    # -- secrets of the host process never reach a shell -------------------------------
    def test_internal_credentials_are_not_inherited_by_the_shell(self):
        os.environ["TLAMATINI_TERMINATER_TOKEN"] = "must-not-leak-9f3"
        try:
            tid = self.new_terminal(load_profile=False, title="env probe")
        finally:
            os.environ.pop("TLAMATINI_TERMINATER_TOKEN", None)
        try:
            res = self.run_in("Write-Output ('tok=[' + $env:TLAMATINI_TERMINATER_TOKEN + ']')", tid)
            self.assertIn("tok=[]", res["output"], res)
            self.assertNotIn("must-not-leak-9f3", res["output"])
        finally:
            self.close_quietly(tid)

    # -- pwsh (only when installed) ------------------------------------------------------
    # -- regressions found by this suite (each one was a real engine bug) ------------
    def test_the_advisor_warns_again_when_the_same_mistake_is_typed_after_clearing_the_line(self):
        session = self.session()
        for round_number in (1, 2, 3):
            before = len(self.seen("warn"))
            for ch in "format c:":
                session.user_input(ch)
            warned = kit.wait_until(lambda: len(self.seen("warn")) > before, timeout=5)
            self.assertTrue(warned, f"round {round_number}: the same dangerous line must be warned about every time")
            session.user_input("\x03")

    def test_the_advisor_does_not_nag_while_the_line_is_unchanged(self):
        session = self.session()
        before = len(self.seen("warn"))
        for ch in "format c:":
            session.user_input(ch)
        kit.wait_until(lambda: len(self.seen("warn")) > before, timeout=5)
        count = len(self.seen("warn"))
        for _ in range(5):
            session.set_user_line("format c:")
        time.sleep(0.3)
        try:
            self.assertEqual(len(self.seen("warn")), count)
        finally:
            session.user_input("\x03")
            session.user_line_screen = None     # the browser's line report goes away with the page

    def test_a_short_label_ending_in_a_colon_is_recognised_as_a_question(self):
        res = self.ps("Read-Host 'Username'", wait_seconds=25)
        try:
            self.assertEqual(res["status"], "operator_required", res)
            self.assertEqual(res["awaiting_input"], "Username:")
        finally:
            self.hub.call("abort", {"user": U, "terminal": self.ps_id})


    def test_a_line_typed_without_enter_returns_the_terminal_to_the_prompt(self):
        res = self.hub.call("type", {"user": U, "terminal": self.ps_id, "text": "Write-Output reviewed-by-user",
                                     "submit": False})
        self.assertEqual(res["status"], "typed", res)
        session = self.session()
        self.assertEqual(session.state, eng.ST_PROMPT, "the user must be able to press Enter on a line left for review")
        before = len(session.commands)
        self.assertTrue(session.user_input("\r")["accepted"])
        end = self.hub.call("wait", {"user": U, "terminal": self.ps_id, "wait_seconds": 20})
        self.assertEqual(end["status"], "completed", end)
        self.assertIn("reviewed-by-user", end["output"])
        self.assertEqual(len(session.commands), before + 1)
        self.assertEqual(session.last_command().source, "user")

    def test_answering_a_program_leaves_the_terminal_at_its_prompt(self):
        res = self.ps("Read-Host 'Name'", wait_seconds=25)
        self.assertEqual(res["status"], "operator_required", res)
        answer = self.hub.call("type", {"user": U, "terminal": self.ps_id, "text": "Ada", "wait_seconds": 20})
        self.assertEqual(answer["status"], "completed", answer)
        self.assertEqual(self.session().state, eng.ST_PROMPT)
        self.assertIn("Ada", answer["output"])
        again = self.ps("Write-Output 'usable afterwards'")
        self.assertIn("usable afterwards", again["output"])

    def test_a_hand_over_whose_last_part_is_the_users_enter_presses_enter_once(self):
        session = self.session()
        before = len(session.commands)

        def user_side():
            kit.wait_until(lambda: session.state == eng.ST_AWAITING_USER, timeout=20)
            time.sleep(0.4)
            for ch in "single":
                session.user_input(ch)
                time.sleep(0.04)
            time.sleep(0.2)
            session.user_input("\r")

        thread = threading.Thread(target=user_side, daemon=True)
        thread.start()
        res = self.hub.call("handover", {"user": U, "terminal": self.ps_id, "text": "Write-Output <<USER:one word>>",
                                         "hint": "one word", "wait_seconds": 40, "user_wait_seconds": 30})
        thread.join(timeout=5)
        self.assertEqual(res["status"], "completed", res)
        self.assertEqual(res["handover"], "submitted_by_user")
        self.assertIn("single", res["output"])
        self.assertEqual(len(session.commands), before + 1, "one line was run, so one record exists")
        self.assertEqual(session.last_command().text, "Write-Output single")
        screen = self.hub.call("read", {"user": U, "terminal": self.ps_id, "which": "all", "read_chars": 2_000_000})["output"]
        self.assertEqual(screen.count("Write-Output single"), 1, "Tlamatini must not press Enter a second time")

    def test_a_secret_hand_over_that_the_user_runs_is_recorded_as_hidden(self):
        session = self.session()

        def user_side():
            kit.wait_until(lambda: session.state == eng.ST_AWAITING_USER, timeout=20)
            time.sleep(0.4)
            for ch in "pw1":
                session.user_input(ch)
            session.user_input("\r")

        thread = threading.Thread(target=user_side, daemon=True)
        thread.start()
        res = self.hub.call("handover", {"user": U, "terminal": self.ps_id, "text": "Write-Output <<USER:a password>>",
                                         "secret": True, "wait_seconds": 40, "user_wait_seconds": 30})
        thread.join(timeout=5)
        self.assertEqual(res["command"], "<hidden>", res)
        self.assertNotIn("pw1", json.dumps({k: v for k, v in res.items() if k != "output"}))

    def test_esc_during_a_hand_over_is_reported_as_the_user_taking_over(self):
        session = self.session()

        def user_side():
            kit.wait_until(lambda: session.state == eng.ST_AWAITING_USER, timeout=20)
            time.sleep(0.3)
            session._abort_typing.set()

        thread = threading.Thread(target=user_side, daemon=True)
        thread.start()
        res = self.hub.call("handover", {"user": U, "terminal": self.ps_id, "text": "Write-Output <<USER:x>> y",
                                         "user_wait_seconds": 30, "wait_seconds": 30})
        thread.join(timeout=5)
        try:
            self.assertEqual(res["status"], "aborted", res)
            self.assertEqual(res["reason"], "user_took_over")
        finally:
            self.session().user_input("\x03")
            self.session().wait(timeout=5)

    def test_text_b64_must_be_real_base64(self):
        for blob in ("@@@", "!!!!", "abc", "====", "not base64 at all"):
            with self.subTest(blob=blob):
                res = self.hub.call("type", {"user": U, "terminal": self.ps_id, "text_b64": blob})
                self.assertIn(res["code"], ("bad_text", "empty_text"), res)

    def test_text_b64_tolerates_line_wrapping_and_spaces(self):
        raw = base64.b64encode(b"Write-Output 'wrapped base64 works'").decode()
        wrapped = raw[:10] + "\r\n" + raw[10:20] + " " + raw[20:]
        res = self.hub.call("run", {"user": U, "terminal": self.ps_id, "text_b64": wrapped, "wait_seconds": 30})
        self.assertIn("wrapped base64 works", res["output"])

    @unittest.skipUnless("pwsh" in eng.available_kinds(), "PowerShell 7 is not installed")
    def test_pwsh_runs_a_command(self):
        tid = self.new_terminal(kind="pwsh", load_profile=False, title="seven")
        try:
            res = self.run_in("$PSVersionTable.PSVersion.Major", tid)
            self.assertEqual(res["status"], "completed", res)
            self.assertRegex(res["output"], r"\b7\b|\b[89]\b")
        finally:
            self.close_quietly(tid)
