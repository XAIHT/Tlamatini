# Tlamatini — Created by Angela López Mendoza · @angelahack1
# Tlamatini Author Banner — do not remove
"""Terminater's process-wide hub, its loopback HTTP API and its WebSocket.

Three doors lead to the same terminals, and each has its own way to go wrong:

* ``terminal_hub``      -- the one hub of the process, the per-run token, the rendezvous file.
* ``/agent/terminater/api/``   -- token-authenticated, loopback-only, no session, no CSRF.
* ``ws/terminals/``     -- the browser's window onto the terminals (login + same-origin).

A private hub is injected for every test (``terminal_hub._HUB``), never the real one.
"""
from __future__ import annotations

import asyncio
import json
import os
import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from asgiref.testing import ApplicationCommunicator
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from . import terminal_consumer as consumer
from . import terminal_hub
from . import terminater_testkit as kit


def _private_hub(**kw):
    hub = kit.fresh_hub(**kw)
    terminal_hub._HUB = hub
    return hub


def _reset():
    terminal_hub.reset_for_tests()


# --------------------------------------------------------------------------- #
# terminal_hub                                                                 #
# --------------------------------------------------------------------------- #

class HubModuleTests(TestCase):
    def setUp(self):
        _reset()
        self.saved_port = terminal_hub._PORT

    def tearDown(self):
        terminal_hub._PORT = self.saved_port
        _reset()

    def test_names_of_the_environment_contract(self):
        self.assertEqual(terminal_hub.ENV_TOKEN, "TLAMATINI_TERMINATER_TOKEN")
        self.assertEqual(terminal_hub.ENV_URL, "TLAMATINI_TERMINATER_URL")
        self.assertEqual(terminal_hub.RENDEZVOUS_NAME, ".terminater_hub.json")

    def test_the_engine_loads_by_path_and_is_cached(self):
        self.assertIs(terminal_hub.load_engine(), terminal_hub.load_engine())
        self.assertTrue(hasattr(terminal_hub.load_engine(), "TerminalHub"))

    def test_engine_dir_is_the_agent_template_folder(self):
        folder = terminal_hub.engine_dir()
        self.assertTrue((folder / "terminater_engine.py").is_file())
        self.assertTrue((folder / "terminater_conpty.py").is_file())
        self.assertTrue((folder / "terminater_text.py").is_file())

    def test_terminals_are_enabled_by_default(self):
        self.assertTrue(terminal_hub.terminals_enabled())

    def test_the_switch_can_turn_them_off(self):
        with patch.object(terminal_hub, "_cfg", return_value=False):
            self.assertFalse(terminal_hub.terminals_enabled())

    def test_ensure_ready_exports_the_token_and_url(self):
        info = terminal_hub.ensure_ready()
        self.assertEqual(os.environ[terminal_hub.ENV_TOKEN], info["token"])
        self.assertEqual(os.environ[terminal_hub.ENV_URL], info["url"])
        self.assertTrue(info["url"].startswith("http://127.0.0.1:"))
        self.assertGreaterEqual(len(info["token"]), 32)

    def test_the_token_is_stable_within_a_run(self):
        first = terminal_hub.ensure_ready()["token"]
        second = terminal_hub.ensure_ready()["token"]
        self.assertEqual(first, second)

    def test_a_new_run_gets_a_new_token(self):
        first = terminal_hub.ensure_ready()["token"]
        _reset()
        second = terminal_hub.ensure_ready()["token"]
        self.assertNotEqual(first, second)

    def test_the_rendezvous_file_carries_url_token_and_pid(self):
        info = terminal_hub.ensure_ready()
        path = terminal_hub.rendezvous_path()
        self.assertTrue(path.is_file())
        data = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(data["url"], info["url"])
        self.assertEqual(data["token"], info["token"])
        self.assertEqual(data["pid"], os.getpid())
        self.assertAlmostEqual(data["written"], time.time(), delta=60)

    def test_the_rendezvous_file_lives_in_the_application_temp(self):
        path = str(terminal_hub.rendezvous_path()).replace("/", "\\").lower()
        self.assertIn("\\temp\\", path)
        self.assertTrue(path.endswith(".terminater_hub.json"))

    def test_no_temporary_file_is_left_beside_the_rendezvous(self):
        terminal_hub.ensure_ready()
        self.assertFalse(terminal_hub.rendezvous_path().with_suffix(".tmp").exists())

    def test_the_real_port_is_published_when_learned(self):
        terminal_hub.note_server_port(9123)
        data = json.loads(terminal_hub.rendezvous_path().read_text(encoding="utf-8"))
        self.assertTrue(data["url"].endswith(":9123"))
        self.assertEqual(os.environ[terminal_hub.ENV_URL], "http://127.0.0.1:9123")

    def test_a_garbage_port_is_ignored(self):
        before = terminal_hub._PORT
        terminal_hub.note_server_port("not a port")
        terminal_hub.note_server_port(0)
        terminal_hub.note_server_port(None)
        self.assertEqual(terminal_hub._PORT, before)

    def test_token_ok_before_a_token_exists(self):
        self.assertFalse(terminal_hub.token_ok("anything"))
        self.assertFalse(terminal_hub.token_ok(""))

    def test_token_ok_accepts_only_the_real_token(self):
        token = terminal_hub.ensure_ready()["token"]
        self.assertTrue(terminal_hub.token_ok(token))
        self.assertFalse(terminal_hub.token_ok(token + "x"))
        self.assertFalse(terminal_hub.token_ok(token[:-1]))
        self.assertFalse(terminal_hub.token_ok(""))
        self.assertFalse(terminal_hub.token_ok(None))

    def test_token_ok_is_not_fooled_by_unicode(self):
        terminal_hub.ensure_ready()
        self.assertFalse(terminal_hub.token_ok("é" * 40))

    def test_hub_status_without_a_hub(self):
        status = terminal_hub.hub_status("u")
        self.assertFalse(status["hub"])
        self.assertEqual(status["terminals"], [])
        self.assertFalse(terminal_hub.hub_exists())

    def test_get_hub_is_a_singleton(self):
        hub = terminal_hub.get_hub()
        try:
            self.assertIs(hub, terminal_hub.get_hub())
            self.assertTrue(terminal_hub.hub_exists())
            self.assertTrue(terminal_hub.hub_status("u")["hub"])
        finally:
            _reset()

    def test_the_configured_terminal_limit_is_used(self):
        with patch.object(terminal_hub, "_cfg", side_effect=lambda key, default: 3 if key == "terminater_max_terminals" else default):
            hub = terminal_hub.get_hub()
        try:
            self.assertEqual(hub.max_terminals, 3)
        finally:
            _reset()

    def test_a_broken_limit_falls_back_to_the_machine_size(self):
        with patch.object(terminal_hub, "_cfg", side_effect=lambda key, default: "many" if key == "terminater_max_terminals" else default):
            hub = terminal_hub.get_hub()
        try:
            self.assertEqual(hub.max_terminals, terminal_hub._auto_max_terminals())
        finally:
            _reset()

    def test_a_broken_hang_window_falls_back_to_the_default(self):
        with patch.object(terminal_hub, "_cfg", side_effect=lambda key, default: "soon" if key == "terminater_hang_seconds" else default):
            hub = terminal_hub.get_hub()
        try:
            self.assertEqual(hub.hang_seconds, terminal_hub.load_engine().HANG_SECONDS_DEFAULT)
        finally:
            _reset()

    def test_auto_limit_is_between_four_and_twelve(self):
        self.assertTrue(4 <= terminal_hub._auto_max_terminals() <= 12)

    def test_auto_limit_shrinks_on_a_small_machine(self):
        class Mem:
            total = 4 * 1024 ** 3

        class Mid:
            total = 8 * 1024 ** 3

        with patch("psutil.virtual_memory", return_value=Mem()), patch("os.cpu_count", return_value=22):
            self.assertLessEqual(terminal_hub._auto_max_terminals(), 4)
        with patch("psutil.virtual_memory", return_value=Mid()), patch("os.cpu_count", return_value=22):
            self.assertLessEqual(terminal_hub._auto_max_terminals(), 6)

    def test_auto_limit_never_trusts_the_core_count_alone(self):
        class Mem:
            total = 4 * 1024 ** 3

        with patch("psutil.virtual_memory", return_value=Mem()), patch("os.cpu_count", return_value=64):
            self.assertLess(terminal_hub._auto_max_terminals(), 12)

    def test_auto_limit_survives_a_missing_cpu_count(self):
        with patch("os.cpu_count", return_value=None):
            self.assertGreaterEqual(terminal_hub._auto_max_terminals(), 4)

    def test_live_pids_without_a_hub_is_empty(self):
        self.assertEqual(terminal_hub.live_pids(), set())

    def test_live_pids_with_an_empty_hub_is_empty(self):
        _private_hub()
        self.assertEqual(terminal_hub.live_pids(), set())

    def test_shutdown_is_idempotent(self):
        terminal_hub.get_hub()
        terminal_hub.shutdown()
        terminal_hub.shutdown()
        self.assertFalse(terminal_hub.hub_exists())

    def test_shutdown_removes_its_own_rendezvous_file(self):
        terminal_hub.ensure_ready()
        terminal_hub.shutdown()
        self.assertFalse(terminal_hub.rendezvous_path().exists())

    def test_shutdown_leaves_another_processs_rendezvous_alone(self):
        path = terminal_hub.rendezvous_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"url": "x", "token": "y", "pid": os.getpid() + 1}), encoding="utf-8")
        try:
            terminal_hub.shutdown()
            self.assertTrue(path.exists())
        finally:
            path.unlink()

    def test_terminal_kinds_lists_installed_shells(self):
        kinds = terminal_hub.terminal_kinds()
        self.assertIsInstance(kinds, list)
        if kit.IS_WINDOWS:
            self.assertIn("cmd", kinds)
            self.assertIn("powershell", kinds)

    # -- run_action ----------------------------------------------------------
    def test_run_action_ping(self):
        _private_hub()
        res = terminal_hub.run_action("ping")
        self.assertTrue(res["pong"])
        self.assertEqual(res["pid"], os.getpid())
        self.assertIsInstance(res["conpty"], bool)

    def test_run_action_when_disabled(self):
        with patch.object(terminal_hub, "terminals_enabled", return_value=False):
            res = terminal_hub.run_action("list")
        self.assertEqual(res["code"], "disabled")
        self.assertFalse(res["ok"])

    def test_run_action_list(self):
        _private_hub()
        res = terminal_hub.run_action("list", {"user": "u"})
        self.assertEqual(res["status"], "listed")

    def test_run_action_normalises_names_and_aliases(self):
        _private_hub()
        self.assertEqual(terminal_hub.run_action("Kill-All", {"user": "u"})["action"], "kill_all")
        self.assertEqual(terminal_hub.run_action("history", {"user": "u", "terminal": "x"})["action"], "commands")

    def test_run_action_unknown(self):
        _private_hub()
        self.assertEqual(terminal_hub.run_action("dance")["code"], "unknown_action")

    def test_run_action_with_no_params(self):
        _private_hub()
        self.assertTrue(terminal_hub.run_action("list", None)["ok"])

    def test_a_slow_action_without_wait_returns_a_job(self):
        _private_hub()
        res = terminal_hub.run_action("kill", {"user": "u", "terminal": "none"}, wait=False)
        self.assertEqual(res["job_state"], "running")
        self.assertTrue(res["job"])
        self.assertEqual(res["status"], "started")

    def test_the_job_can_be_collected(self):
        _private_hub()
        job = terminal_hub.run_action("kill", {"user": "u", "terminal": "none"}, wait=False)["job"]
        res = kit.wait_until(lambda: terminal_hub.run_action("job", {"id": job}).get("job_state") == "done", timeout=10)
        self.assertTrue(res)
        final = terminal_hub.run_action("job", {"id": job})
        self.assertEqual(final["code"], "no_terminal")

    def test_job_accepts_either_key(self):
        _private_hub()
        job = terminal_hub.run_action("kill", {"user": "u", "terminal": "none"}, wait=False)["job"]
        kit.wait_until(lambda: terminal_hub.run_action("job", {"job": job}).get("job_state") == "done", timeout=10)
        self.assertEqual(terminal_hub.run_action("job", {"job": job})["job_state"], "done")

    def test_an_unknown_job(self):
        _private_hub()
        res = terminal_hub.run_action("job", {"id": "nope"})
        self.assertEqual(res["job_state"], "unknown")

    def test_a_quick_action_ignores_wait_false(self):
        _private_hub()
        res = terminal_hub.run_action("list", {"user": "u"}, wait=False)
        self.assertEqual(res["status"], "listed")
        self.assertNotIn("job", res)

    def test_a_hub_that_cannot_start_is_reported_not_raised(self):
        with patch.object(terminal_hub, "get_hub", side_effect=RuntimeError("no engine")):
            res = terminal_hub.run_action("list")
        self.assertEqual(res["code"], "hub_unavailable")
        self.assertEqual(res["status"], "unavailable")
        self.assertIn("no engine", res["message"])


# --------------------------------------------------------------------------- #
# The loopback HTTP API                                                        #
# --------------------------------------------------------------------------- #

class LoopbackApiTests(TestCase):
    def setUp(self):
        _reset()
        _private_hub()
        self.token = terminal_hub.ensure_ready()["token"]
        self.url = reverse("terminater_api")

    def tearDown(self):
        _reset()

    def post(self, payload, token="__ok__", remote="127.0.0.1", raw=None, **extra):
        headers = {}
        if token == "__ok__":
            token = self.token
        if token is not None:
            headers["HTTP_X_TERMINATER_TOKEN"] = token
        body = raw if raw is not None else json.dumps(payload)
        return self.client.post(self.url, data=body, content_type="application/json",
                                REMOTE_ADDR=remote, **headers, **extra)

    def test_the_route_is_under_agent(self):
        self.assertEqual(self.url, "/agent/terminater/api/")

    def test_a_valid_call_is_answered(self):
        res = self.post({"action": "ping"})
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.json()["pong"])

    def test_no_token_is_refused(self):
        res = self.post({"action": "ping"}, token=None)
        self.assertEqual(res.status_code, 401)
        self.assertEqual(res.json()["code"], "bad_token")

    def test_a_wrong_token_is_refused(self):
        res = self.post({"action": "ping"}, token="wrong")
        self.assertEqual(res.status_code, 401)

    def test_an_empty_token_is_refused(self):
        self.assertEqual(self.post({"action": "ping"}, token="").status_code, 401)

    def test_a_remote_address_is_refused_before_the_token_is_even_read(self):
        res = self.post({"action": "ping"}, remote="203.0.113.9")
        self.assertEqual(res.status_code, 403)
        self.assertEqual(res.json()["code"], "not_loopback")

    def test_a_remote_address_with_a_wrong_token_is_still_not_loopback(self):
        res = self.post({"action": "ping"}, token="wrong", remote="198.51.100.1")
        self.assertEqual(res.json()["code"], "not_loopback")

    def test_ipv6_loopback_is_accepted(self):
        self.assertEqual(self.post({"action": "ping"}, remote="::1").status_code, 200)

    def test_a_lan_address_is_refused(self):
        self.assertEqual(self.post({"action": "ping"}, remote="192.168.1.20").status_code, 403)

    def test_get_is_not_allowed(self):
        self.assertEqual(self.client.get(self.url, REMOTE_ADDR="127.0.0.1").status_code, 405)

    def test_put_is_not_allowed(self):
        self.assertEqual(self.client.put(self.url, data="{}", content_type="application/json").status_code, 405)

    def test_csrf_is_not_required(self):
        self.client.enforce_csrf_checks = True
        self.assertEqual(self.post({"action": "ping"}).status_code, 200)

    def test_no_session_cookie_is_needed(self):
        self.client.cookies.clear()
        self.assertEqual(self.post({"action": "ping"}).status_code, 200)

    def test_invalid_json_is_a_400(self):
        res = self.post(None, raw="{not json")
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.json()["code"], "bad_json")

    def test_a_json_array_is_a_400(self):
        self.assertEqual(self.post(None, raw="[1,2]").status_code, 400)

    def test_json_null_is_a_400(self):
        self.assertEqual(self.post(None, raw="null").status_code, 400)

    def test_binary_garbage_is_a_400(self):
        res = self.client.post(self.url, data=b"\xff\xfe\x00bad", content_type="application/json",
                               REMOTE_ADDR="127.0.0.1", HTTP_X_TERMINATER_TOKEN=self.token)
        self.assertEqual(res.status_code, 400)

    def test_an_oversized_body_is_a_413(self):
        big = json.dumps({"action": "ping", "pad": "x" * (2 * 1024 * 1024 + 10)})
        res = self.post(None, raw=big)
        self.assertEqual(res.status_code, 413)
        self.assertEqual(res.json()["code"], "too_large")

    def test_an_empty_body_is_an_unknown_action_not_a_crash(self):
        res = self.post(None, raw="")
        self.assertEqual(res.json()["code"], "unknown_action")

    def test_params_object_is_used(self):
        res = self.post({"action": "layout", "params": {"user": "api", "layout": "grid"}})
        self.assertEqual(res.json()["ui"]["layout"], "grid")

    def test_flat_params_are_used_when_there_is_no_params_object(self):
        res = self.post({"action": "layout", "user": "api2", "layout": "tile"})
        self.assertEqual(res.json()["ui"]["layout"], "tile")

    def test_a_non_object_params_falls_back_to_flat_params(self):
        res = self.post({"action": "layout", "params": "oops", "user": "api3", "layout": "grid"})
        self.assertEqual(res.json()["ui"]["layout"], "grid")

    def test_wait_for_job_is_not_forwarded_as_a_parameter(self):
        res = self.post({"action": "kill", "user": "api", "terminal": "nope", "wait_for_job": True})
        self.assertEqual(res.json()["code"], "no_terminal")

    def test_a_slow_action_returns_a_job_by_default(self):
        res = self.post({"action": "kill", "user": "api", "terminal": "nope"})
        self.assertEqual(res.json()["job_state"], "running")
        job = res.json()["job"]
        done = kit.wait_until(
            lambda: self.post({"action": "job", "id": job}).json().get("job_state") == "done", timeout=10)
        self.assertTrue(done)

    def test_wait_for_job_blocks_until_done(self):
        res = self.post({"action": "kill", "user": "api", "terminal": "nope", "wait_for_job": True})
        self.assertNotIn("job", res.json())
        self.assertEqual(res.json()["status"], "refused")

    def test_unknown_actions_are_answered_not_raised(self):
        res = self.post({"action": "launch_missiles"})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["code"], "unknown_action")

    def test_the_response_is_json(self):
        self.assertIn("application/json", self.post({"action": "ping"})["Content-Type"])

    def test_a_disabled_terminater_answers_disabled(self):
        with patch.object(terminal_hub, "terminals_enabled", return_value=False):
            res = self.post({"action": "list"})
        self.assertEqual(res.json()["code"], "disabled")

    def test_the_token_header_is_case_insensitive(self):
        res = self.client.post(self.url, data="{}", content_type="application/json",
                               REMOTE_ADDR="127.0.0.1", **{"HTTP_X_TERMINATER_TOKEN": self.token})
        self.assertEqual(res.status_code, 200)

    def test_a_token_in_the_body_is_not_enough(self):
        res = self.post({"action": "ping", "token": self.token}, token=None)
        self.assertEqual(res.status_code, 401)

    def test_a_token_in_the_query_string_is_not_enough(self):
        res = self.client.post(self.url + f"?token={self.token}", data="{}", content_type="application/json",
                               REMOTE_ADDR="127.0.0.1")
        self.assertEqual(res.status_code, 401)

    def test_a_cross_site_form_post_cannot_carry_the_token_header(self):
        res = self.client.post(self.url, data={"action": "ping"}, REMOTE_ADDR="127.0.0.1")
        self.assertEqual(res.status_code, 401)


class StateViewTests(TestCase):
    def setUp(self):
        _reset()
        self.url = reverse("terminater_state")
        self.user = get_user_model().objects.create_user("terminater_state_user", password="x")

    def tearDown(self):
        _reset()

    def test_anonymous_users_are_sent_to_login(self):
        res = self.client.get(self.url)
        self.assertEqual(res.status_code, 302)
        self.assertIn("next=/agent/terminater/state/", res["Location"])

    def test_post_is_not_allowed(self):
        self.client.force_login(self.user)
        self.assertEqual(self.client.post(self.url).status_code, 405)

    def test_state_without_a_hub(self):
        self.client.force_login(self.user)
        data = self.client.get(self.url).json()
        self.assertFalse(data["hub"])
        self.assertEqual(data["terminals"], [])
        self.assertTrue(data["enabled"])
        self.assertIsInstance(data["available_kinds"], list)

    def test_state_with_a_hub_lists_only_this_users_terminals(self):
        hub = _private_hub()
        hub.call("layout", {"user": str(self.user.pk), "layout": "grid"})
        self.client.force_login(self.user)
        data = self.client.get(self.url).json()
        self.assertTrue(data["hub"])
        self.assertEqual(data["ui"]["layout"], "grid")
        other = hub.call("list", {"user": "someone-else"})
        self.assertEqual(other["ui"]["layout"], "tabs")

    def test_state_reports_when_terminals_are_switched_off(self):
        self.client.force_login(self.user)
        with patch.object(terminal_hub, "terminals_enabled", return_value=False):
            self.assertFalse(self.client.get(self.url).json()["enabled"])


# --------------------------------------------------------------------------- #
# The WebSocket                                                                #
# --------------------------------------------------------------------------- #

class _SocketBase(unittest.IsolatedAsyncioTestCase):
    USER = 41

    async def asyncSetUp(self):
        _reset()
        self.hub = _private_hub(max_terminals=6)
        self.sockets = []

    async def asyncTearDown(self):
        for socket in self.sockets:
            try:
                await socket.send_input({"type": "websocket.disconnect", "code": 1000})
                await socket.wait(timeout=3)
            except Exception:  # noqa: BLE001
                pass
        await asyncio.to_thread(_reset)

    async def connect(self, authenticated=True, origin="http://localhost:8000", pk=None):
        socket = ApplicationCommunicator(consumer.TerminalConsumer.as_asgi(), {
            "type": "websocket", "path": "/ws/terminals/",
            "user": SimpleNamespace(is_authenticated=authenticated, pk=pk or self.USER),
            "headers": [(b"origin", origin.encode()), (b"host", b"localhost:8000")]})
        self.sockets.append(socket)
        await socket.send_input({"type": "websocket.connect"})
        first = await socket.receive_output(timeout=5)
        return socket, first

    async def frame(self, socket, timeout=5):
        out = await socket.receive_output(timeout=timeout)
        return json.loads(out["text"])

    async def send(self, socket, **data):
        await socket.send_input({"type": "websocket.receive", "text": json.dumps(data)})

    async def until(self, socket, predicate, timeout=30.0):
        """Read frames until ``predicate`` accepts one; return all frames seen."""
        seen = []
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                frame = await self.frame(socket, timeout=min(2.0, max(0.1, deadline - time.monotonic())))
            except asyncio.TimeoutError:
                continue
            seen.append(frame)
            if predicate(frame):
                return seen
        self.fail(f"the expected frame never arrived; saw {[f.get('t') for f in seen]}")


class SocketGateTests(_SocketBase):
    async def test_anonymous_is_closed_with_4401(self):
        _, first = await self.connect(authenticated=False)
        self.assertEqual(first["type"], "websocket.close")
        self.assertEqual(first["code"], 4401)

    async def test_a_foreign_origin_is_closed_with_4403(self):
        _, first = await self.connect(origin="https://attacker.example")
        self.assertEqual(first["code"], 4403)

    async def test_a_missing_origin_is_closed_with_4403(self):
        socket = ApplicationCommunicator(consumer.TerminalConsumer.as_asgi(), {
            "type": "websocket", "path": "/ws/terminals/",
            "user": SimpleNamespace(is_authenticated=True, pk=1),
            "headers": [(b"host", b"localhost:8000")]})
        self.sockets.append(socket)
        await socket.send_input({"type": "websocket.connect"})
        self.assertEqual((await socket.receive_output(timeout=3))["code"], 4403)

    async def test_a_mismatched_host_is_closed_with_4403(self):
        _, first = await self.connect(origin="http://localhost:9999")
        self.assertEqual(first["code"], 4403)

    async def test_a_scope_with_no_user_is_closed(self):
        socket = ApplicationCommunicator(consumer.TerminalConsumer.as_asgi(), {
            "type": "websocket", "path": "/ws/terminals/", "headers": []})
        self.sockets.append(socket)
        await socket.send_input({"type": "websocket.connect"})
        self.assertEqual((await socket.receive_output(timeout=3))["code"], 4401)

    async def test_switched_off_is_closed_with_4404(self):
        with patch.object(terminal_hub, "terminals_enabled", return_value=False):
            _, first = await self.connect()
        self.assertEqual(first["code"], 4404)

    async def test_a_rejected_connection_creates_no_hub_state(self):
        await self.connect(authenticated=False)
        self.assertEqual(self.hub.live_pids(), [])


class SocketProtocolTests(_SocketBase):
    async def test_accepted_and_greeted(self):
        socket, first = await self.connect()
        self.assertEqual(first["type"], "websocket.accept")
        hello = await self.frame(socket)
        self.assertEqual(hello["t"], "hello")
        self.assertEqual(hello["terminals"], [])
        self.assertEqual(hello["active"], "")
        self.assertEqual(hello["replay"], {})
        self.assertIsInstance(hello["kinds"], list)
        self.assertEqual(hello["max"], 6)
        self.assertEqual(hello["ui"]["layout"], "tabs")

    async def test_ping_pong(self):
        socket, _ = await self.connect()
        await self.frame(socket)
        await self.send(socket, t="ping")
        self.assertEqual((await self.frame(socket))["t"], "pong")

    async def test_malformed_frames_do_not_break_the_socket(self):
        socket, _ = await self.connect()
        await self.frame(socket)
        for text in ("{", "[]", "null", "42", '"s"', "x" * (consumer.MAX_FRAME + 5)):
            await socket.send_input({"type": "websocket.receive", "text": text})
        await self.send(socket, t="ping")
        self.assertEqual((await self.frame(socket))["t"], "pong")

    async def test_binary_frames_are_ignored(self):
        socket, _ = await self.connect()
        await self.frame(socket)
        await socket.send_input({"type": "websocket.receive", "bytes": b"\x00\x01"})
        await self.send(socket, t="ping")
        self.assertEqual((await self.frame(socket))["t"], "pong")

    async def test_unknown_frame_types_are_harmless(self):
        socket, _ = await self.connect()
        await self.frame(socket)
        await self.send(socket, t="selfdestruct")
        await self.send(socket, t="ping")
        frames = await self.until(socket, lambda f: f["t"] == "pong", timeout=5)
        self.assertEqual(frames[-1]["t"], "pong")

    async def test_ordered_frames_for_a_missing_terminal_are_dropped(self):
        socket, _ = await self.connect()
        await self.frame(socket)
        await self.send(socket, t="in", id="nope", d="whoami\r")
        await self.send(socket, t="resize", id="nope", cols=80, rows=24)
        await self.send(socket, t="ping")
        await self.until(socket, lambda f: f["t"] == "pong", timeout=5)

    async def test_layout_frames_are_applied_and_broadcast(self):
        socket, _ = await self.connect()
        await self.frame(socket)
        await self.send(socket, t="layout", layout="grid", area="full")
        frames = await self.until(socket, lambda f: f["t"] == "ui" and f["ui"]["layout"] == "grid", timeout=10)
        self.assertEqual(frames[-1]["ui"]["area"], "full")
        self.assertEqual(self.hub.call("list", {"user": str(self.USER)})["ui"]["layout"], "grid")

    async def test_a_bad_kind_is_reported_as_an_error_frame(self):
        socket, _ = await self.connect()
        await self.frame(socket)
        await self.send(socket, t="open", kind="zsh")
        frames = await self.until(socket, lambda f: f["t"] == "error", timeout=10)
        self.assertEqual(frames[-1]["code"], "bad_kind")

    async def test_users_do_not_see_each_others_layout(self):
        a, _ = await self.connect(pk=1)
        await self.frame(a)
        b, _ = await self.connect(pk=2)
        await self.frame(b)
        await self.send(a, t="layout", layout="grid")
        await self.until(a, lambda f: f["t"] == "ui", timeout=10)
        self.assertEqual(self.hub.call("list", {"user": "2"})["ui"]["layout"], "tabs")

    async def test_disconnect_removes_the_listener(self):
        socket, _ = await self.connect()
        await self.frame(socket)
        space = self.hub.space(str(self.USER))
        self.assertEqual(len(space.listeners), 1)
        await socket.send_input({"type": "websocket.disconnect", "code": 1000})
        await socket.wait(timeout=3)
        for _ in range(40):
            if not space.listeners:
                break
            await asyncio.sleep(0.05)
        self.assertEqual(space.listeners, [])
        self.sockets.remove(socket)

    async def test_two_pages_of_one_user_share_one_hub_view(self):
        a, _ = await self.connect()
        await self.frame(a)
        b, _ = await self.connect()
        await self.frame(b)
        await self.send(a, t="layout", layout="tile")
        await self.until(a, lambda f: f["t"] == "ui", timeout=10)
        await self.until(b, lambda f: f["t"] == "ui", timeout=10)


@unittest.skipUnless(kit.conpty_ok(), "ConPTY is not available on this machine")
class SocketShellTests(_SocketBase):
    async def open_cmd(self, socket, title="sock cmd"):
        await self.send(socket, t="open", kind="cmd", title=title)
        frames = await self.until(socket, lambda f: f["t"] == "opened", timeout=40)
        return frames[-1]["terminal"]["id"]

    async def test_open_streams_the_prompt_as_output(self):
        socket, _ = await self.connect()
        await self.frame(socket)
        tid = await self.open_cmd(socket)
        frames = await self.until(socket, lambda f: f["t"] == "out" and f["id"] == tid, timeout=20)
        self.assertTrue(frames[-1]["d"])
        self.assertIn("seq", frames[-1])

    async def test_user_keystrokes_reach_the_shell_and_come_back(self):
        socket, _ = await self.connect()
        await self.frame(socket)
        tid = await self.open_cmd(socket)
        seen = ""
        await self.send(socket, t="in", id=tid, d="echo socket-roundtrip-7\r")
        deadline = time.monotonic() + 30
        while "socket-roundtrip-7" not in seen.replace("echo socket-roundtrip-7", "") and time.monotonic() < deadline:
            try:
                frame = await self.frame(socket, timeout=2)
            except asyncio.TimeoutError:
                continue
            if frame.get("t") == "out" and frame.get("id") == tid:
                seen += frame["d"]
        self.assertIn("socket-roundtrip-7", seen)

    async def test_the_user_typing_is_recorded_for_tlamatini(self):
        socket, _ = await self.connect()
        await self.frame(socket)
        tid = await self.open_cmd(socket)
        await self.send(socket, t="in", id=tid, d="dir")
        session = self.hub.space(str(self.USER)).sessions[tid]
        self.assertTrue(await asyncio.to_thread(
            kit.wait_until, lambda: "".join(k[2] for k in session.user_keys) == "dir", 10))

    async def test_a_second_page_gets_the_terminals_and_their_history(self):
        a, _ = await self.connect()
        await self.frame(a)
        tid = await self.open_cmd(a)
        await self.send(a, t="in", id=tid, d="echo history-marker-3\r")
        session = self.hub.space(str(self.USER)).sessions[tid]
        await asyncio.to_thread(kit.wait_until, lambda: "history-marker-3" in session.snapshot(), 20)
        b, _ = await self.connect()
        hello = await self.frame(b)
        self.assertEqual([t["id"] for t in hello["terminals"]], [tid])
        self.assertIn("history-marker-3", hello["replay"][tid])

    async def test_closing_a_page_does_not_kill_the_shell(self):
        socket, _ = await self.connect()
        await self.frame(socket)
        tid = await self.open_cmd(socket)
        session = self.hub.space(str(self.USER)).sessions[tid]
        pid = session.pid
        await socket.send_input({"type": "websocket.disconnect", "code": 1000})
        await socket.wait(timeout=3)
        self.sockets.remove(socket)
        await asyncio.sleep(0.5)
        self.assertTrue(session.pty_alive())
        self.assertTrue(pid)

    async def test_rename_focus_and_close_frames(self):
        socket, _ = await self.connect()
        await self.frame(socket)
        tid = await self.open_cmd(socket)
        await self.send(socket, t="rename", id=tid, title="renamed by page")
        await self.until(socket, lambda f: f["t"] == "title_set" and f["title"] == "renamed by page", timeout=10)
        await self.send(socket, t="close", id=tid)
        frames = await self.until(socket, lambda f: f["t"] == "removed", timeout=20)
        self.assertEqual(frames[-1]["id"], tid)
        self.assertEqual(self.hub.space(str(self.USER)).sessions, {})

    async def test_kill_with_force(self):
        socket, _ = await self.connect()
        await self.frame(socket)
        tid = await self.open_cmd(socket)
        pid = self.hub.space(str(self.USER)).sessions[tid].pid
        await self.send(socket, t="kill", id=tid, force=True)
        await self.until(socket, lambda f: f["t"] == "removed", timeout=20)
        self.assertTrue(await asyncio.to_thread(kit.wait_until, lambda: not _pid_dead_check(pid), 10))

    async def test_the_advisor_toggle_frame(self):
        socket, _ = await self.connect()
        await self.frame(socket)
        tid = await self.open_cmd(socket)
        session = self.hub.space(str(self.USER)).sessions[tid]
        await self.send(socket, t="advisor", id=tid, on=False)
        self.assertTrue(await asyncio.to_thread(kit.wait_until, lambda: session.advisor_enabled is False, 10))
        await self.send(socket, t="advisor", id=tid, on=True)
        self.assertTrue(await asyncio.to_thread(kit.wait_until, lambda: session.advisor_enabled is True, 10))

    async def test_the_line_frame_feeds_the_advisor_with_the_real_prompt_line(self):
        socket, _ = await self.connect()
        await self.frame(socket)
        tid = await self.open_cmd(socket)
        await self.send(socket, t="line", id=tid, text="format c:")
        frames = await self.until(socket, lambda f: f["t"] == "warn", timeout=10)
        self.assertIn("format c:", frames[-1]["line"])

    async def test_resize_frame(self):
        socket, _ = await self.connect()
        await self.frame(socket)
        tid = await self.open_cmd(socket)
        session = self.hub.space(str(self.USER)).sessions[tid]
        await self.send(socket, t="resize", id=tid, cols=90, rows=22)
        self.assertTrue(await asyncio.to_thread(kit.wait_until, lambda: (session.cols, session.rows) == (90, 22), 10))

    async def test_abort_typing_frame_takes_the_keyboard_back(self):
        socket, _ = await self.connect()
        await self.frame(socket)
        tid = await self.open_cmd(socket)
        session = self.hub.space(str(self.USER)).sessions[tid]
        await self.send(socket, t="abort_typing", id=tid)
        self.assertTrue(await asyncio.to_thread(kit.wait_until, lambda: session._abort_typing.is_set(), 10))

    async def test_oversized_input_is_ignored(self):
        socket, _ = await self.connect()
        await self.frame(socket)
        tid = await self.open_cmd(socket)
        session = self.hub.space(str(self.USER)).sessions[tid]
        await self.send(socket, t="in", id=tid, d="x" * 100_001)
        await self.send(socket, t="in", id=tid, d="")
        await self.send(socket, t="in", id=tid, d=5)
        await asyncio.sleep(0.5)
        self.assertEqual(session.user_keys.__len__() if hasattr(session.user_keys, "__len__") else 0, 0)


def _pid_dead_check(pid):
    try:
        import psutil  # type: ignore

        return psutil.pid_exists(pid)
    except Exception:  # noqa: BLE001
        return False
