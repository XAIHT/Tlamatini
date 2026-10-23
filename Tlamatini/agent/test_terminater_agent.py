# Tlamatini — Created by Angela López Mendoza · @angelahack1
# Tlamatini Author Banner — do not remove
"""The ``terminater`` pool agent, exactly as a flow or the chat launches it.

A pool agent is a SCRIPT: importing it changes the working directory, truncates its log and
installs logging handlers, so it is never imported into the test process.  Every check runs it
in a throw-away copy of the template folder, in a child process -- the same isolation a real
pool run has:

* ``probe`` runs   -- the pure helpers (``build_params``, ``_deadline``, ``emit_section`` ...),
* a stub hub       -- an HTTP server speaking the hub's protocol, for ``HubClient``,
* real runs        -- ``python terminater.py`` against a real shell (standalone mode).
"""
from __future__ import annotations

import ast
import http.server
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path

import yaml
from django.test import SimpleTestCase

from . import terminater_testkit as kit
from .services import agent_contracts

TEMPLATE = Path(__file__).resolve().parent / "agents" / "terminater"
AGENT_PY = TEMPLATE / "terminater.py"


def _clean_env(**extra):
    env = {k: v for k, v in os.environ.items() if not k.startswith("TLAMATINI_TERMINATER_")}
    env["PYTHONIOENCODING"] = "utf-8"
    env.update(extra)
    return env


def _copy_template():
    root = Path(tempfile.mkdtemp(prefix="termagent_"))
    folder = root / "terminater"
    shutil.copytree(TEMPLATE, folder, ignore=shutil.ignore_patterns("*.log", "__pycache__", "*.pid"))
    return root, folder


def _literal(name):
    """A module-level literal of terminater.py, read by AST (the module has import side effects)."""
    tree = ast.parse(AGENT_PY.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(getattr(t, "id", None) == name for t in node.targets):
            return ast.literal_eval(node.value)
    raise AssertionError(f"{name} not found in terminater.py")


# --------------------------------------------------------------------------- #
# The template                                                                 #
# --------------------------------------------------------------------------- #

class TemplateTests(SimpleTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.config = yaml.safe_load((TEMPLATE / "config.yaml").read_text(encoding="utf-8"))

    def test_the_flat_siblings_travel_with_the_template(self):
        for name in ("terminater.py", "terminater_engine.py", "terminater_conpty.py", "terminater_text.py", "config.yaml"):
            self.assertTrue((TEMPLATE / name).is_file(), name)

    def test_the_config_parses_and_is_a_mapping(self):
        self.assertIsInstance(self.config, dict)

    def test_connection_fields_exist_and_are_lists(self):
        self.assertEqual(self.config["source_agents"], [])
        self.assertEqual(self.config["target_agents"], [])

    def test_defaults(self):
        for key, value in {"action": "run", "kind": "powershell", "submit": True, "secret": False, "wait": True,
                           "typing_wpm": 50, "wait_seconds": 120, "hang_seconds": 45, "user_wait_seconds": 300,
                           "mode": "auto", "severity": "warning", "which": "last", "read_chars": 20000,
                           "close_after": False, "load_profile": True, "advisor": True, "idle_seconds": 2}.items():
            self.assertEqual(self.config[key], value, key)

    def test_every_parameter_the_agent_forwards_is_in_the_config(self):
        for key in _literal("PARAM_KEYS"):
            self.assertIn(key, self.config, f"{key} would be silently dropped by the pool's config merge")

    def test_agent_plumbing_keys_are_in_the_config_too(self):
        for key in ("action", "mode", "hub_url", "user", "source_agents", "target_agents"):
            self.assertIn(key, self.config)

    def test_there_is_no_instant_or_paste_mode(self):
        for key in self.config:
            self.assertNotIn("paste", key.lower())
            self.assertNotIn("instant", key.lower())

    def test_typing_speed_default_is_inside_the_allowed_range(self):
        self.assertTrue(20 <= self.config["typing_wpm"] <= 160)

    def test_the_section_fields_equal_the_parametrizer_contract(self):
        declared = tuple(_literal("SECTION_FIELDS"))
        contract = tuple(agent_contracts._PARAMETRIZER_OUTPUT_FIELDS["terminater"])
        self.assertEqual(contract[:len(declared)], declared)
        self.assertEqual(contract[len(declared):], ("response_body",))

    def test_the_rendezvous_contract_matches_the_django_side(self):
        from . import terminal_hub

        self.assertEqual(_literal("ENV_TOKEN"), terminal_hub.ENV_TOKEN)
        self.assertEqual(_literal("ENV_URL"), terminal_hub.ENV_URL)
        self.assertEqual(_literal("RENDEZVOUS_NAME"), terminal_hub.RENDEZVOUS_NAME)

    def test_the_agent_calls_the_same_route_the_view_serves(self):
        source = AGENT_PY.read_text(encoding="utf-8")
        self.assertIn("/agent/terminater/api/", source)
        self.assertIn("X-Terminater-Token", source)

    def test_the_agent_script_has_the_standard_boilerplate(self):
        source = AGENT_PY.read_text(encoding="utf-8")
        for needle in ("FOR_DISABLE_CONSOLE_CTRL_HANDLER", "_IS_REANIMATED", "write_pid_file", "remove_pid_file",
                       "wait_for_agents_to_stop", "start_agent", "CREATE_NO_WINDOW", "TLAMATINI_TEMP"):
            self.assertIn(needle, source, needle)

    def test_the_banner_is_present(self):
        self.assertIn("Angela López Mendoza", AGENT_PY.read_text(encoding="utf-8")[:900])


# --------------------------------------------------------------------------- #
# Pure helpers, in a child process                                             #
# --------------------------------------------------------------------------- #

_PROBE = r'''
import json, logging, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import terminater as T

records = []
class _H(logging.Handler):
    def emit(self, record):
        records.append(record.getMessage())
logging.getLogger().addHandler(_H())

def section(action, res, backend="hub"):
    before = len(records)
    T.emit_section(action, res, backend, None)
    return [r for r in records[before:] if "INI_SECTION_TERMINATER" in r]

out = {}
out["truthy"] = [[repr(v), T._truthy(v)] for v in (None, "", "  ", "0", "false", "No", "OFF", "none", "null", "1", "yes", "x", 0, 1, True, False)]
out["truthy_default_false"] = [T._truthy(None, False), T._truthy("", False), T._truthy("yes", False)]
out["params_empty"] = T.build_params({})
out["params_mixed"] = T.build_params({
    "terminal": "t1", "kind": "cmd", "text": "dir", "submit": "false", "wait": "no", "secret": "yes",
    "typing_wpm": 80, "wait_seconds": 5, "unknown": "x", "action": "run", "mode": "standalone",
    "hub_url": "http://x", "source_agents": ["a"], "target_agents": ["b"], "title": "", "cwd": None,
    "layout": "grid", "advisor": False, "close_after": "true", "load_profile": "0"})
out["params_booleans_native"] = T.build_params({"submit": True, "wait": False})
out["deadline_run"] = T._deadline("run", {"wait_seconds": 10, "text": "abcd"})
out["deadline_read"] = T._deadline("read", {})
out["deadline_handover"] = T._deadline("handover", {"text": "x", "user_wait_seconds": 7})
out["deadline_user_marker"] = T._deadline("run", {"text": "a<<USER:b>>"})
out["deadline_type_default"] = T._deadline("type", {"text": ""})
out["deadline_inherited"] = T._deadline("run", {"text_b64": "YTw8VVNFUjpiPj4=", "use_my_defaults": True})
out["sanitize"] = [T._sanitize_value("a\r\nb\nc  "), T._sanitize_value(None), T._sanitize_value(5), T._sanitize_value("  x  ")]

out["s_completed"] = section("run", {
    "ok": True, "status": "completed", "success": True, "terminal_id": "t1", "kind": "powershell",
    "title": "build", "terminal_state": "prompt", "command": "Get-Date", "exit_code": 0, "duration_seconds": 1.5,
    "output_chars": 12, "truncated": False, "hung": False, "aborted_by": "", "typed": "Get-Date",
    "output": "Monday\nTuesday", "message": ""})
out["s_exit_none"] = section("run", {"ok": True, "status": "completed", "success": True, "command": "dir", "exit_code": None})
out["s_nested_terminal"] = section("open", {"ok": True, "status": "opened", "terminal": {"id": "t9", "kind": "cmd", "title": "CMD 9", "state": "prompt"}})
out["s_list"] = section("list", {"ok": True, "status": "listed", "terminals": [
    {"id": "t1", "kind": "cmd", "state": "prompt", "pid": 11, "title": "one", "cwd": "C:\\"},
    {"id": "t2", "kind": "powershell", "state": "running", "pid": 12, "title": "two", "cwd": "C:\\x", "running_command": "ping x"}],
    "ui": {"layout": "grid", "area": "full"}})
out["s_list_empty"] = section("list", {"ok": True, "status": "listed", "terminals": []})
out["s_commands"] = section("commands", {"ok": True, "status": "listed", "commands": [
    {"id": 1, "source": "tlamatini", "state": "completed", "exit_code": 0, "command": "dir"}]})
out["s_watch"] = section("watch_user", {"ok": True, "status": "observed", "line": "git sta", "keys": "git sta", "cursor": 7,
    "watch_reason": "idle", "submitted": [{"line": "dir"}], "advice": [{"severity": "danger", "message": "Dangerous", "suggestion": "Do not"}]})
out["s_refused"] = section("type", {"ok": False, "status": "refused", "code": "no_terminal", "message": "No terminal named 'x'."})
out["s_no_status_ok"] = section("run", {"ok": True})
out["s_no_status_bad"] = section("run", {"ok": False})
out["s_success_default_hung"] = section("run", {"ok": True, "status": "hung"})
out["s_success_default_failed"] = section("run", {"ok": True, "status": "command_failed"})
out["s_success_default_done"] = section("run", {"ok": True, "status": "completed"})
out["s_message_newlines"] = section("warn_user", {"ok": True, "status": "warned", "message": "line one\nline two"})
out["s_secret"] = section("run", {"ok": True, "status": "completed", "command": "<hidden>", "typed": "", "user_part": "<hidden>"})
print("@@JSON@@" + json.dumps(out))
'''


class _ProbeBase(SimpleTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.root, folder = _copy_template()
        (folder / "_probe.py").write_text(_PROBE, encoding="utf-8")
        proc = subprocess.run([sys.executable, "-u", str(folder / "_probe.py")], cwd=str(folder),
                              capture_output=True, text=True, encoding="utf-8", timeout=120, env=_clean_env())
        marker = [ln for ln in proc.stdout.splitlines() if ln.startswith("@@JSON@@")]
        if not marker:
            raise AssertionError(f"probe failed (rc={proc.returncode}):\n{proc.stderr[-3000:]}")
        cls.out = json.loads(marker[0][len("@@JSON@@"):])

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.root, ignore_errors=True)
        super().tearDownClass()

    @staticmethod
    def parse(records):
        assert len(records) == 1, "a section must be ONE atomic logging call"
        text = records[0]
        assert text.startswith("INI_SECTION_TERMINATER<<<\n") and text.endswith("\n>>>END_SECTION_TERMINATER"), text
        inner = text[len("INI_SECTION_TERMINATER<<<\n"):-len("\n>>>END_SECTION_TERMINATER")]
        head, _, body = inner.partition("\n\n")
        fields = {}
        for line in head.split("\n"):
            key, _, value = line.partition(": ")
            fields[key] = value
        return fields, body


class ProbeHelperTests(_ProbeBase):
    def test_truthy_matrix(self):
        got = dict(self.out["truthy"])
        for key in ("'0'", "'false'", "'No'", "'OFF'", "'none'", "'null'", "0", "False"):
            self.assertFalse(got[key], key)
        for key in ("'1'", "'yes'", "'x'", "1", "True"):
            self.assertTrue(got[key], key)

    def test_truthy_blank_means_the_default(self):
        got = dict(self.out["truthy"])
        self.assertTrue(got["None"])
        self.assertTrue(got["''"])
        self.assertTrue(got["'  '"])
        self.assertEqual(self.out["truthy_default_false"], [False, False, True])

    def test_params_of_an_empty_config_are_empty(self):
        self.assertEqual(self.out["params_empty"], {})

    def test_params_keep_only_the_hub_parameters(self):
        params = self.out["params_mixed"]
        for key in ("unknown", "action", "mode", "hub_url", "source_agents", "target_agents"):
            self.assertNotIn(key, params)

    def test_params_drop_empty_and_none_values(self):
        params = self.out["params_mixed"]
        self.assertNotIn("title", params)
        self.assertNotIn("cwd", params)

    def test_params_coerce_the_booleans(self):
        params = self.out["params_mixed"]
        self.assertIs(params["submit"], False)
        self.assertIs(params["wait"], False)
        self.assertIs(params["secret"], True)
        self.assertIs(params["advisor"], False)
        self.assertIs(params["close_after"], True)
        self.assertIs(params["load_profile"], False)

    def test_params_keep_numbers_and_text(self):
        params = self.out["params_mixed"]
        self.assertEqual(params["typing_wpm"], 80)
        self.assertEqual(params["wait_seconds"], 5)
        self.assertEqual(params["terminal"], "t1")
        self.assertEqual(params["kind"], "cmd")
        self.assertEqual(params["text"], "dir")
        self.assertEqual(params["layout"], "grid")

    def test_native_booleans_pass_through(self):
        self.assertEqual(self.out["params_booleans_native"], {"submit": True, "wait": False})

    def test_deadline_covers_typing_waiting_and_a_margin(self):
        self.assertAlmostEqual(self.out["deadline_run"], 10 + (0.24 * 4 + 5) + 210, places=3)

    def test_deadline_of_a_plain_read(self):
        self.assertEqual(self.out["deadline_read"], 120 + 210)

    def test_deadline_waits_for_the_user_on_a_handover(self):
        self.assertAlmostEqual(self.out["deadline_handover"], 120 + (0.24 * 1 + 5) + 7 + 210, places=3)

    def test_deadline_waits_for_the_user_when_the_text_has_a_marker(self):
        self.assertAlmostEqual(self.out["deadline_user_marker"], 120 + (0.24 * 11 + 5) + 300 + 210, places=3)

    def test_deadline_for_type_adds_typing_overhead(self):
        self.assertAlmostEqual(self.out["deadline_type_default"], 120 + 5 + 210, places=3)

    def test_inherited_deadline_covers_slowest_speed_longest_waits_and_base64_handoff(self):
        self.assertGreaterEqual(self.out['deadline_inherited'], 3600 + 3600 + .6 * 11 + 120)

    def test_sanitize_value(self):
        self.assertEqual(self.out["sanitize"], ["a  b c", "", "5", "x"])


class SectionTests(_ProbeBase):
    def test_a_completed_run_section(self):
        fields, body = self.parse(self.out["s_completed"])
        self.assertEqual(fields["action"], "run")
        self.assertEqual(fields["status"], "completed")
        self.assertEqual(fields["success"], "True")
        self.assertEqual(fields["terminal_id"], "t1")
        self.assertEqual(fields["kind"], "powershell")
        self.assertEqual(fields["title"], "build")
        self.assertEqual(fields["terminal_state"], "prompt")
        self.assertEqual(fields["command"], "Get-Date")
        self.assertEqual(fields["exit_code"], "0")
        self.assertEqual(fields["duration_seconds"], "1.5")
        self.assertEqual(fields["hub"], "hub")
        self.assertEqual(body, "Monday\nTuesday")

    def test_the_header_has_exactly_the_declared_fields_in_order(self):
        fields, _ = self.parse(self.out["s_completed"])
        self.assertEqual(tuple(fields), tuple(_literal("SECTION_FIELDS")))

    def test_an_unknown_exit_code_is_blank_not_zero(self):
        fields, _ = self.parse(self.out["s_exit_none"])
        self.assertEqual(fields["exit_code"], "")

    def test_the_nested_terminal_fills_the_id_kind_title_and_state(self):
        fields, _ = self.parse(self.out["s_nested_terminal"])
        self.assertEqual((fields["terminal_id"], fields["kind"], fields["title"], fields["terminal_state"]),
                         ("t9", "cmd", "CMD 9", "prompt"))

    def test_a_listing_counts_the_terminals_and_lists_them(self):
        fields, body = self.parse(self.out["s_list"])
        self.assertEqual(fields["terminals"], "2")
        self.assertEqual(fields["layout"], "grid")
        self.assertEqual(fields["area"], "full")
        self.assertIn("t1  cmd", body)
        self.assertIn("pid=12", body)
        self.assertIn("RUNNING: ping x", body)

    def test_an_empty_listing_says_so(self):
        fields, body = self.parse(self.out["s_list_empty"])
        self.assertEqual(fields["terminals"], "0")
        self.assertEqual(body, "(no terminals open)")

    def test_the_history_body(self):
        _, body = self.parse(self.out["s_commands"])
        self.assertIn("#1 [tlamatini] completed exit=0 dir", body)

    def test_watching_the_user_reports_the_line_keys_submissions_and_advice(self):
        fields, body = self.parse(self.out["s_watch"])
        self.assertEqual(fields["user_line"], "git sta")
        self.assertEqual(fields["user_keys"], "git sta")
        self.assertEqual(fields["cursor"], "7")
        self.assertEqual(fields["watch_reason"], "idle")
        self.assertIn("USER SUBMITTED:", body)
        self.assertIn("  dir", body)
        self.assertIn("ADVICE:", body)
        self.assertIn("[danger] Dangerous Do not", body)

    def test_a_refusal_is_not_a_success(self):
        fields, body = self.parse(self.out["s_refused"])
        self.assertEqual(fields["status"], "refused")
        self.assertEqual(fields["success"], "False")
        self.assertEqual(body, "No terminal named 'x'.")

    def test_a_missing_status_defaults_from_ok(self):
        self.assertEqual(self.parse(self.out["s_no_status_ok"])[0]["status"], "completed")
        self.assertEqual(self.parse(self.out["s_no_status_bad"])[0]["status"], "error")
        self.assertEqual(self.parse(self.out["s_no_status_bad"])[0]["success"], "False")

    def test_success_is_derived_from_the_status_when_absent(self):
        self.assertEqual(self.parse(self.out["s_success_default_hung"])[0]["success"], "False")
        self.assertEqual(self.parse(self.out["s_success_default_failed"])[0]["success"], "False")
        self.assertEqual(self.parse(self.out["s_success_default_done"])[0]["success"], "True")

    def test_newlines_in_header_values_are_flattened(self):
        fields, _ = self.parse(self.out["s_message_newlines"])
        self.assertEqual(fields["message"], "line one line two")

    def test_a_hidden_command_stays_hidden(self):
        fields, _ = self.parse(self.out["s_secret"])
        self.assertEqual(fields["command"], "<hidden>")
        self.assertEqual(fields["typed"], "")
        self.assertEqual(fields["user_part"], "<hidden>")

    def test_every_section_is_one_atomic_logging_call(self):
        for key in self.out:
            if key.startswith("s_"):
                self.assertEqual(len(self.out[key]), 1, key)

    def test_every_status_the_agent_can_emit_is_known_to_the_verdict_engine(self):
        from .agent_verdict import KNOWN_STATUSES

        for status in ("completed", "command_failed", "hung", "operator_required", "timeout", "aborted", "opened",
                       "listed", "typed", "started", "read", "killed", "focused", "warned", "observed", "refused",
                       "error", "unavailable"):
            self.assertIn(status, KNOWN_STATUSES, status)


# --------------------------------------------------------------------------- #
# HubClient against a stub hub                                                 #
# --------------------------------------------------------------------------- #

class _StubHub(http.server.ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, token="tok-stub"):
        super().__init__(("127.0.0.1", 0), _StubHandler)
        self.token = token
        self.requests = []
        self.polls = {}
        self.lock = threading.Lock()


class _StubHandler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *args):  # noqa: D401 - silence
        pass

    def _send(self, code, payload):
        data = json.dumps(payload).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):  # noqa: N802
        body = self.rfile.read(int(self.headers.get("Content-Length") or 0))
        with self.server.lock:
            self.server.requests.append({"path": self.path, "token": self.headers.get("X-Terminater-Token"),
                                         "body": json.loads(body or b"{}"), "ctype": self.headers.get("Content-Type")})
        if self.headers.get("X-Terminater-Token") != self.server.token:
            return self._send(401, {"ok": False, "status": "refused", "code": "bad_token"})
        payload = json.loads(body or b"{}")
        action = payload.get("action")
        params = payload.get("params") or {}
        if action == "ping":
            return self._send(200, {"ok": True, "pong": True})
        if action == "quick":
            return self._send(200, {"ok": True, "status": "listed", "echo": params})
        if action in ("run", "lost", "slow"):
            return self._send(200, {"ok": True, "job": action + "-1", "job_state": "running", "status": "started"})
        if action == "job":
            job = params.get("id")
            with self.server.lock:
                n = self.server.polls[job] = self.server.polls.get(job, 0) + 1
            if job == "lost-1":
                return self._send(200, {"ok": True, "job_state": "unknown", "status": "started"})
            if job == "slow-1":
                return self._send(200, {"ok": True, "job_state": "running", "status": "started"})
            if n < 2:
                return self._send(200, {"ok": True, "job_state": "running", "status": "started"})
            return self._send(200, {"ok": True, "job_state": "done", "status": "completed", "output": "hello",
                                    "terminal_id": "t1"})
        return self._send(200, {"ok": False, "status": "refused", "code": "unknown_action"})


_CLIENT_PROBE = r'''
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import terminater as T
cfg = json.loads(os.environ.get("PROBE_CONFIG") or "{}")
c = T.HubClient(cfg)
out = {"url": c.url, "token": c.token}
for step in json.loads(os.environ.get("PROBE_STEPS") or "[]"):
    if step == "reachable":
        out["reachable"] = c.reachable()
    elif step.startswith("call:"):
        _, action, deadline = step.split(":")
        out["call_" + action] = c.call(action, {"x": 1}, float(deadline))
    out["token_after"] = c.token
print("@@JSON@@" + json.dumps(out))
'''


class HubClientTests(SimpleTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.root, cls.folder = _copy_template()
        (cls.folder / "_client_probe.py").write_text(_CLIENT_PROBE, encoding="utf-8")
        cls.hub = _StubHub()
        cls.port = cls.hub.server_address[1]
        cls.url = f"http://127.0.0.1:{cls.port}"
        threading.Thread(target=cls.hub.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.hub.shutdown()
        cls.hub.server_close()
        shutil.rmtree(cls.root, ignore_errors=True)
        super().tearDownClass()

    def setUp(self):
        self.hub.requests.clear()
        self.hub.polls.clear()

    def probe(self, config=None, steps=(), **env):
        full = _clean_env(PROBE_CONFIG=json.dumps(config or {}), PROBE_STEPS=json.dumps(list(steps)), **env)
        proc = subprocess.run([sys.executable, "-u", str(self.folder / "_client_probe.py")], cwd=str(self.folder),
                              capture_output=True, text=True, encoding="utf-8", timeout=120, env=full)
        marker = [ln for ln in proc.stdout.splitlines() if ln.startswith("@@JSON@@")]
        self.assertTrue(marker, f"probe failed: {proc.stderr[-2000:]}")
        return json.loads(marker[0][len("@@JSON@@"):])

    def rendezvous(self, token="tok-stub", url=None):
        temp = Path(tempfile.mkdtemp(prefix="termrdv_", dir=str(self.root)))
        (temp / ".terminater_hub.json").write_text(json.dumps({"url": url or self.url, "token": token}), encoding="utf-8")
        return str(temp)

    def test_url_and_token_come_from_the_environment(self):
        out = self.probe(steps=["reachable"], TLAMATINI_TERMINATER_URL=self.url, TLAMATINI_TERMINATER_TOKEN="tok-stub")
        self.assertEqual(out["url"], self.url)
        self.assertEqual(out["token"], "tok-stub")
        self.assertTrue(out["reachable"])

    def test_the_ping_carries_the_token_header_and_json_type(self):
        self.probe(steps=["reachable"], TLAMATINI_TERMINATER_URL=self.url, TLAMATINI_TERMINATER_TOKEN="tok-stub")
        request = self.hub.requests[0]
        self.assertEqual(request["path"], "/agent/terminater/api/")
        self.assertEqual(request["token"], "tok-stub")
        self.assertEqual(request["ctype"], "application/json")
        self.assertEqual(request["body"], {"action": "ping"})

    def test_a_configured_hub_url_beats_the_environment(self):
        out = self.probe(config={"hub_url": self.url}, TLAMATINI_TERMINATER_URL="http://127.0.0.1:1",
                         TLAMATINI_TERMINATER_TOKEN="tok-stub", steps=["reachable"])
        self.assertEqual(out["url"], self.url)
        self.assertTrue(out["reachable"])

    def test_the_rendezvous_file_is_the_fallback_for_both_url_and_token(self):
        out = self.probe(steps=["reachable"], TLAMATINI_TEMP=self.rendezvous())
        self.assertEqual(out["url"], self.url)
        self.assertEqual(out["token"], "tok-stub")
        self.assertTrue(out["reachable"])

    def test_a_stale_token_is_replaced_from_the_rendezvous_file_and_retried(self):
        out = self.probe(steps=["call:quick:30"], TLAMATINI_TERMINATER_URL=self.url,
                         TLAMATINI_TERMINATER_TOKEN="stale", TLAMATINI_TEMP=self.rendezvous())
        self.assertEqual(out["call_quick"]["status"], "listed")
        self.assertEqual(out["token_after"], "tok-stub")
        self.assertEqual([r["token"] for r in self.hub.requests], ["stale", "tok-stub"])

    def test_a_wrong_token_with_no_file_returns_the_hubs_refusal(self):
        out = self.probe(steps=["call:quick:30"], TLAMATINI_TERMINATER_URL=self.url, TLAMATINI_TERMINATER_TOKEN="nope")
        self.assertFalse(out["call_quick"]["ok"])
        self.assertEqual(out["call_quick"]["code"], "bad_token")

    def test_no_url_means_unreachable_without_trying(self):
        out = self.probe(steps=["reachable"])
        self.assertFalse(out["reachable"])
        self.assertEqual(self.hub.requests, [])

    def test_no_token_means_unreachable_without_trying(self):
        out = self.probe(steps=["reachable"], TLAMATINI_TERMINATER_URL=self.url)
        self.assertFalse(out["reachable"])
        self.assertEqual(self.hub.requests, [])

    def test_a_closed_port_is_unreachable(self):
        out = self.probe(steps=["reachable"], TLAMATINI_TERMINATER_URL="http://127.0.0.1:1",
                         TLAMATINI_TERMINATER_TOKEN="tok-stub")
        self.assertFalse(out["reachable"])

    def test_a_quick_action_is_one_request(self):
        out = self.probe(steps=["call:quick:30"], TLAMATINI_TERMINATER_URL=self.url, TLAMATINI_TERMINATER_TOKEN="tok-stub")
        self.assertEqual(out["call_quick"]["echo"], {"x": 1})
        self.assertEqual(len(self.hub.requests), 1)
        self.assertEqual(self.hub.requests[0]["body"], {"action": "quick", "params": {"x": 1}})

    def test_a_slow_action_is_polled_until_the_job_is_done(self):
        out = self.probe(steps=["call:run:60"], TLAMATINI_TERMINATER_URL=self.url, TLAMATINI_TERMINATER_TOKEN="tok-stub")
        self.assertEqual(out["call_run"]["status"], "completed")
        self.assertEqual(out["call_run"]["output"], "hello")
        polls = [r for r in self.hub.requests if r["body"].get("action") == "job"]
        self.assertGreaterEqual(len(polls), 2)
        self.assertEqual(polls[0]["body"]["params"], {"id": "run-1"})

    def test_a_forgotten_job_is_reported_as_lost(self):
        out = self.probe(steps=["call:lost:60"], TLAMATINI_TERMINATER_URL=self.url, TLAMATINI_TERMINATER_TOKEN="tok-stub")
        self.assertEqual(out["call_lost"]["code"], "job_lost")
        self.assertEqual(out["call_lost"]["status"], "error")

    def test_the_agent_stops_waiting_at_its_deadline(self):
        out = self.probe(steps=["call:slow:1"], TLAMATINI_TERMINATER_URL=self.url, TLAMATINI_TERMINATER_TOKEN="tok-stub")
        self.assertEqual(out["call_slow"]["code"], "agent_deadline")
        self.assertEqual(out["call_slow"]["status"], "timeout")
        self.assertFalse(out["call_slow"]["success"])
        self.assertIn("may still be working", out["call_slow"]["message"])


# --------------------------------------------------------------------------- #
# Real runs (standalone: terminals live and die inside the agent)               #
# --------------------------------------------------------------------------- #

@unittest.skipUnless(kit.conpty_ok(), "ConPTY is not available on this machine")
class StandaloneRunTests(SimpleTestCase):
    def run_agent(self, overrides=None, timeout=150, **env):
        root, folder = _copy_template()
        try:
            config = yaml.safe_load((folder / "config.yaml").read_text(encoding="utf-8"))
            config.update({"mode": "standalone", "load_profile": False, "typing_wpm": 160})
            config.update(overrides or {})
            (folder / "config.yaml").write_text(yaml.safe_dump(config, allow_unicode=True), encoding="utf-8")
            proc = subprocess.run([sys.executable, "-u", str(folder / "terminater.py")], cwd=str(folder),
                                  capture_output=True, text=True, encoding="utf-8", errors="replace",
                                  timeout=timeout, env=_clean_env(**env))
            log = (folder / "terminater.log").read_text(encoding="utf-8", errors="replace") \
                if (folder / "terminater.log").exists() else ""
            match = re.search(r"INI_SECTION_TERMINATER<<<\n(.*?)\n>>>END_SECTION_TERMINATER", log, re.S)
            fields, body = {}, ""
            if match:
                head, _, body = match.group(1).partition("\n\n")
                for line in head.split("\n"):
                    key, _, value = line.partition(": ")
                    fields[key] = value
            leftovers = [p.name for p in folder.iterdir() if p.suffix == ".pid"]
            return {"rc": proc.returncode, "fields": fields, "body": body, "log": log, "stderr": proc.stderr,
                    "pids": leftovers, "stdout": proc.stdout}
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_a_cmd_command_runs_and_its_output_is_in_the_section(self):
        res = self.run_agent({"kind": "cmd", "text": "echo agent-standalone-ok"})
        self.assertEqual(res["rc"], 0, res["stderr"][-1500:])
        self.assertEqual(res["fields"]["status"], "completed", res["log"][-2000:])
        self.assertEqual(res["fields"]["success"], "True")
        self.assertEqual(res["fields"]["hub"], "standalone")
        self.assertEqual(res["fields"]["command"], "echo agent-standalone-ok")
        self.assertIn("agent-standalone-ok", res["body"])

    def test_a_failing_powershell_command_reports_its_exit_code(self):
        res = self.run_agent({"kind": "powershell", "text": "cmd /c exit 4"})
        self.assertEqual(res["rc"], 0)
        self.assertEqual(res["fields"]["status"], "command_failed", res["log"][-2000:])
        self.assertEqual(res["fields"]["exit_code"], "4")
        self.assertEqual(res["fields"]["success"], "False")

    def test_the_log_announces_the_run_and_the_standalone_warning(self):
        res = self.run_agent({"kind": "cmd", "text": "echo x"})
        self.assertIn("TERMINATER AGENT STARTED", res["log"])
        self.assertIn("STANDALONE", res["log"])
        self.assertIn("will type: echo x", res["log"])

    def test_a_secret_is_not_logged(self):
        res = self.run_agent({"kind": "cmd", "text": "echo secret-token-9d2", "secret": True})
        self.assertNotIn("will type", res["log"])
        self.assertNotIn("secret-token-9d2", res["log"].split("INI_SECTION_TERMINATER")[0])
        self.assertEqual(res["fields"]["command"], "<hidden>")
        self.assertEqual(res["fields"]["typed"], "")

    def test_no_pid_file_is_left_behind(self):
        res = self.run_agent({"kind": "cmd", "text": "echo x"})
        self.assertEqual(res["pids"], [])

    def test_listing_with_nothing_open(self):
        res = self.run_agent({"action": "list"})
        self.assertEqual(res["fields"]["status"], "listed")
        self.assertEqual(res["fields"]["terminals"], "0")
        self.assertEqual(res["body"], "(no terminals open)")

    def test_status_reports_the_engine(self):
        res = self.run_agent({"action": "status"})
        self.assertEqual(res["fields"]["status"], "listed")

    def test_opening_a_terminal(self):
        res = self.run_agent({"action": "open", "kind": "cmd", "title": "agent opened"})
        self.assertEqual(res["fields"]["status"], "opened", res["log"][-1500:])
        self.assertEqual(res["fields"]["kind"], "cmd")
        self.assertEqual(res["fields"]["title"], "agent opened")

    def test_an_unknown_action_is_refused_not_crashed(self):
        res = self.run_agent({"action": "dance"})
        self.assertEqual(res["rc"], 0)
        self.assertEqual(res["fields"]["status"], "refused")

    def test_a_bad_kind_is_refused(self):
        res = self.run_agent({"kind": "zsh", "text": "echo x"})
        self.assertEqual(res["fields"]["status"], "refused")

    def test_hub_mode_without_a_hub_refuses_instead_of_going_standalone(self):
        res = self.run_agent({"mode": "hub", "kind": "cmd", "text": "echo x"})
        self.assertEqual(res["rc"], 0)
        self.assertEqual(res["fields"]["status"], "unavailable")
        self.assertEqual(res["fields"]["success"], "False")
        self.assertEqual(res["fields"]["hub"], "none")
        self.assertIn("mode='hub' forbids", res["log"])

    def test_a_hand_over_nobody_answers_ends_as_operator_required(self):
        res = self.run_agent({"kind": "cmd", "text": "echo <<USER:anyone>>", "user_wait_seconds": 5})
        self.assertEqual(res["fields"]["status"], "operator_required", res["log"][-2000:])
        self.assertEqual(res["fields"]["success"], "False")

    def test_a_missing_terminal_is_refused(self):
        res = self.run_agent({"action": "type", "terminal": "nope", "text": "x"})
        self.assertEqual(res["fields"]["status"], "refused")

    def test_the_agent_finishes_with_the_standard_closing_line(self):
        res = self.run_agent({"action": "list"})
        self.assertIn("Terminater agent finished", res["log"])
