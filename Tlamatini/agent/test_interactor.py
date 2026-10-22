# Tlamatini Author Banner — Angela López Mendoza · @angelahack1
"""Interactor protocol, ownership, cancellation and persistence regressions.

Run with manage.py test from a verified visible PowerShell -NoExit console.
Browser behavior is exercised separately by scripts/interactor_visible.py.
"""
import asyncio
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import tempfile
import time
import sys
from types import SimpleNamespace
from unittest.mock import patch

from asgiref.sync import async_to_sync, sync_to_async
from channels.testing import WebsocketCommunicator
from django.test import SimpleTestCase

from .interactor import context
from .interactor.consumer import InteractorConsumer
from .interactor.files import prepare_file
from .interactor.hub import Hub
from .interactor.protocol import InteractorError, MAX_UNITS, expect, snapshot, splice, units
from .interactor.tool import build_tool, perform


def document(text="FROM ", revision=1):
    return {"document_id": "document-one", "revision": revision, "text": text,
            "active": True, "dirty": False, "selection": {"from": units(text), "to": units(text)}}


def request(client_id="test", owner=("7", "session")):
    return context.Request(owner, client_id, int(owner[0]), 1)


class ProtocolTests(SimpleTestCase):
    def test_utf16_offsets_preserve_emoji(self):
        self.assertEqual(units("a😀b"), 4)
        self.assertEqual(splice("a😀b", 1, 3, "é"), "aéb")
        for start, end in ((1, 2), (2, 3), (-1, 1), (0, 9), (False, 1)):
            with self.subTest(start=start, end=end), self.assertRaises(InteractorError):
                splice("a😀b", start, end, "")

    def test_snapshot_is_exact_and_never_truncates(self):
        source = "# unsaved\n😀 café\n"
        result = snapshot(document(source))
        self.assertEqual(result["text"], source)
        self.assertFalse(result["truncated"])
        self.assertEqual(result["source"], "live_editor")
        with self.assertRaises(InteractorError):
            snapshot(document("x" * (MAX_UNITS + 1)))

    def test_malformed_and_stale_snapshots_are_refused(self):
        for value in (None, {}, document(revision=True), {**document(), "selection": []}):
            with self.subTest(value=value), self.assertRaises(InteractorError):
                snapshot(value)
        for doc, revision in (("other", 1), ("document-one", 0)):
            with self.assertRaises(InteractorError):
                expect(snapshot(document()), doc, revision)

    def test_context_survives_async_worker_and_resets(self):
        async def run():
            scope = {"user": SimpleNamespace(pk=7, is_authenticated=True),
                     "session": SimpleNamespace(session_key="session")}
            token = context.bind(scope, "tab", 12)
            try:
                found = await sync_to_async(context.current.get, thread_sensitive=False)()
                self.assertEqual((found.client_id, found.run_epoch, found.owner), ("tab", 12, ("7", "session")))
            finally:
                context.current.reset(token)
            self.assertIsNone(context.current.get())
        async_to_sync(run)()


class HubTests(SimpleTestCase):
    def setUp(self):
        self.hub = Hub()
        self.cancel = patch("agent.interactor.context.cancelled", return_value=False)
        self.cancel.start()
        self.addCleanup(self.cancel.stop)

    def attach(self, reply=None):
        def emit(message):
            if reply and message["t"] == "command":
                self.hub.receive(client, {"t": "receipt", "id": message["id"], "result": reply(message)})
        client = self.hub.connect(("7", "session"), emit, True)
        return request(client)

    def test_each_read_is_a_new_round_trip(self):
        values = iter(["disk", "fresh unsaved"])
        req = self.attach(lambda _: {"ok": True, "snapshot": document(next(values))})
        self.assertEqual(self.hub.call(req, "read")["snapshot"]["text"], "disk")
        self.assertEqual(self.hub.call(req, "read")["snapshot"]["text"], "fresh unsaved")

    def test_account_session_and_tab_isolation(self):
        req = self.attach()
        for owner, client in ((("8", "session"), req.client_id), (("7", "other"), req.client_id), (req.owner, "missing")):
            with self.subTest(owner=owner, client=client), self.assertRaises(InteractorError):
                self.hub.call(request(client, owner), "read")

    def test_stop_and_disable_abort_current_turn(self):
        for frame in ({"t": "stop"}, {"t": "access", "enabled": False}):
            req = self.attach()
            self.hub.endpoint(req)
            self.hub.receive(req.client_id, frame)
            with self.assertRaises(InteractorError):
                self.hub.call(req, "type")

    def test_disconnect_wakes_pending_call_and_cleans_it(self):
        req = self.attach()
        endpoint = self.hub.endpoint(req)
        endpoint.emit = lambda message: self.hub.disconnect(req.client_id)
        with self.assertRaisesRegex(InteractorError, "disconnected"):
            self.hub.call(req, "type", timeout=2)
        self.assertFalse(endpoint.pending)
        self.assertFalse(endpoint.mutation.locked())

    def test_timeout_cancels_and_never_replays(self):
        req = self.attach()
        messages = []
        endpoint = self.hub.endpoint(req)
        endpoint.emit = messages.append
        with self.assertRaisesRegex(InteractorError, "timed out"):
            self.hub.call(req, "type", timeout=.01)
        self.assertEqual([item["t"] for item in messages], ["command", "cancel"])
        self.assertFalse(endpoint.pending)

    def test_visibility_grace_is_bounded_and_does_not_change_read_timeout(self):
        frames = []
        def reply(message):
            frames.append(message)
            return {"ok": True}
        req = self.attach(reply)
        for action, grace, expected in (("type", 120, 130), ("type", 999, 130), ("read", 0, 10)):
            started = time.time() * 1000
            self.hub.call(req, action, visibility_grace=grace)
            self.assertAlmostEqual((frames[-1]["deadline"] - started) / 1000, expected, delta=1)

    def test_concurrent_mutations_refused(self):
        req = self.attach()
        endpoint = self.hub.endpoint(req)
        endpoint.mutation.acquire()
        try:
            with self.assertRaisesRegex(InteractorError, "already running"):
                self.hub.call(req, "type")
        finally:
            endpoint.mutation.release()


class ToolTests(SimpleTestCase):
    def setUp(self):
        self.req = request()
        token = context.current.set(self.req)
        self.addCleanup(context.current.reset, token)

    def invoke(self, **kwargs):
        return json.loads(perform(**kwargs))

    def test_stale_read_refuses_before_mutation(self):
        with patch("agent.interactor.tool.hub.call", return_value={"ok": True, "snapshot": document(revision=2)}) as call:
            result = self.invoke(action="type", document_id="document-one", revision=1, text="x")
        self.assertEqual(result["status"], "conflict")
        self.assertEqual(call.call_count, 1)

    def test_implicit_revision_uses_previous_read_not_the_internal_refresh(self):
        with patch("agent.interactor.tool.hub.call", side_effect=[
                {"ok": True, "snapshot": document()},
                {"ok": True, "snapshot": document(revision=2)}]) as call:
            self.assertTrue(self.invoke(action="read")["ok"])
            result = self.invoke(action="type", text="x")
        self.assertEqual(result["status"], "conflict")
        self.assertEqual(call.call_count, 2)
        self.assertFalse(self.req.handed_off)

    def test_read_then_edit_can_omit_identifiers(self):
        with patch("agent.interactor.tool.hub.call", side_effect=[
                {"ok": True, "snapshot": document()},
                {"ok": True, "snapshot": document()},
                {"ok": True, "snapshot": document("FROM x", 2)}]):
            self.invoke(action="read")
            result = self.invoke(action="type", text="x")
        self.assertTrue(result["verified"])
        self.assertEqual(self.req.revision, 2)

    def test_malformed_receipt_is_a_structured_refusal(self):
        with patch("agent.interactor.tool.hub.call", return_value={"ok": True}):
            self.assertEqual(self.invoke(action="read")["status"], "invalid_reply")

    def test_context_cap_refuses_whole_snapshot_and_ends_editing(self):
        from .mcp_agent import _cap_tool_message_content
        text = json.dumps({"ok": True, "text": "private source" * 200})
        self.assertEqual(_cap_tool_message_content(text, len(text), tool_name="interactor"), text)
        result = json.loads(_cap_tool_message_content(text, 2000, tool_name="interactor"))
        self.assertEqual(result["status"], "context_limit")
        self.assertNotIn("text", result)
        self.assertTrue(self.req.handed_off)

    def test_guide_handoff_blocks_further_edits(self):
        with patch("agent.interactor.tool.hub.call", side_effect=[
                {"ok": True, "snapshot": document()}, {"ok": True, "snapshot": document()}]) as call:
            result = self.invoke(action="guide", document_id="document-one", revision=1,
                                 label="Java image", hint="Choose your Java version.", choices=[{"text": "tomcat:10"}])
            self.assertTrue(result["ok"])
            self.assertTrue(self.req.handed_off)
            self.assertEqual(self.invoke(action="save")["status"], "operator_required")
            self.assertEqual(call.call_count, 2)

    def test_type_receipt_must_match_exact_text(self):
        for actual, good in (("FROM tomcat", True), ("FROM tomcatUSER", False)):
            self.req.handed_off = False
            with patch("agent.interactor.tool.hub.call", side_effect=[
                    {"ok": True, "snapshot": document()}, {"ok": True, "snapshot": document(actual, 7)}]):
                result = self.invoke(action="type", document_id="document-one", revision=1, text="tomcat")
            self.assertEqual(result["ok"], good)

    def test_unsaved_document_and_remote_host_refuse_new(self):
        for dirty, local in ((True, True), (False, False)):
            with patch("agent.interactor.tool.hub.call", return_value={"ok": True, "snapshot": {**document(), "dirty": dirty}}), \
                    patch("agent.interactor.tool.hub.endpoint", return_value=SimpleNamespace(local=local)), \
                    patch("agent.interactor.tool.prepare_file") as create:
                self.assertFalse(self.invoke(action="new", document_id="document-one", revision=1, filename="Dockerfile")["ok"])
                create.assert_not_called()

    def test_schema_rejects_unknown_actions_and_large_segments(self):
        from pydantic import ValidationError
        for args in ({"action": "run"}, {"action": "type", "text": "x" * 2001}):
            with self.assertRaises(ValidationError):
                build_tool().invoke(args)

    def test_only_native_new_and_save_obey_ask_execs(self):
        from .mcp_agent import MultiTurnToolAgentExecutor
        for action in ("new", "save"):
            self.assertTrue(MultiTurnToolAgentExecutor._requires_exec_permission(None, "interactor", {"action": action}))
        for action in ("read", "open", "type", "guide", "select", "stop"):
            self.assertFalse(MultiTurnToolAgentExecutor._requires_exec_permission(None, "interactor", {"action": action}))


class FilesTests(SimpleTestCase):
    def test_source_and_frozen_temp_files_share_real_save_capabilities(self):
        from . import canvas_file_views as saves
        source_root = Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory() as directory:
            install = Path(directory) / "installed"
            for frozen, app_root in ((False, source_root), (True, install)):
                with self.subTest(frozen=frozen), patch.object(sys, "frozen", frozen, create=True), \
                        patch.object(sys, "executable", str(install / "Tlamatini.exe")), \
                        patch.object(sys, "_MEIPASS", str(install / "_internal"), create=True):
                    opened = prepare_file(request(), "new", "Dockerfile", "")
                    target = Path(opened["path"])
                    try:
                        self.assertTrue(target.is_relative_to(app_root / "Temp" / "interactor"))
                        self.assertNotIn("_internal", target.parts)
                        capability = saves._capability(opened["native"]["token"], request().owner)
                        self.assertEqual(capability.path, target)
                        content = "FROM tomcat:10.1-jdk21-temurin\n# café 😀\n".encode()
                        revision = saves._commit(target, content, opened["native"]["revision"])
                        self.assertEqual(saves._snapshot(target), (content, revision))
                    finally:
                        saves._CAPABILITIES.pop(opened["native"]["token"], None)
                        target.unlink()
                        target.parent.rmdir()

    def test_temp_creation_and_existing_file_preservation(self):
        with tempfile.TemporaryDirectory() as directory, patch("agent.interactor.files.get_app_temp_root", return_value=directory):
            first = prepare_file(request(), "new", "Dockerfile", "")
            path = Path(first["path"])
            self.assertTrue(path.is_relative_to(Path(directory)))
            self.assertEqual(path.name, "Dockerfile")
            self.assertEqual(path.read_bytes(), b"")
            path.write_text("keep me", encoding="utf-8")
            with patch("agent.interactor.files.validate_tool_path", return_value=None), self.assertRaises(InteractorError):
                prepare_file(request(), "new", "", str(path))
            self.assertEqual(path.read_text(), "keep me")

    def test_invalid_temp_names_never_create(self):
        for name in ("../file", "a/b", "NUL", "a.", "a:", ""):
            with self.subTest(name=name), self.assertRaises(InteractorError):
                prepare_file(request(), "new", name, "")


class SocketTests(SimpleTestCase):
    def socket(self, authenticated=True, origin=b"http://localhost", session="session"):
        ws = WebsocketCommunicator(InteractorConsumer.as_asgi(), "/ws/interactor/", headers=[(b"host", b"localhost"), (b"origin", origin)])
        ws.scope.update(user=SimpleNamespace(pk=7, is_authenticated=authenticated),
                        session=SimpleNamespace(session_key=session), client=("127.0.0.1", 123))
        return ws

    def test_auth_origin_and_session_required(self):
        async def run():
            for kwargs in ({"authenticated": False}, {"origin": b"http://evil.example"}, {"session": None}):
                ws = self.socket(**kwargs)
                self.assertFalse((await ws.connect())[0])
                await ws.disconnect()
        async_to_sync(run)()

    def test_real_socket_round_trip_and_no_browser_commands(self):
        async def run():
            from .interactor.hub import hub
            ws = self.socket()
            self.assertTrue((await ws.connect())[0])
            hello = await ws.receive_json_from()
            self.assertTrue(hello["local"])
            req = request(hello["client_id"])
            with patch("agent.interactor.context.cancelled", return_value=False), ThreadPoolExecutor(max_workers=1) as pool:
                future = asyncio.get_running_loop().run_in_executor(pool, hub.call, req, "read")
                command = await ws.receive_json_from()
                await ws.send_json_to({"t": "receipt", "id": command["id"], "result": {"ok": True, "snapshot": document("unsaved")}})
                self.assertEqual((await future)["snapshot"]["text"], "unsaved")
            await ws.send_json_to({"t": "command", "action": "save", "path": "forbidden"})
            self.assertEqual((await ws.receive_output())["type"], "websocket.close")
            await ws.disconnect()
            self.assertNotIn(req.client_id, hub.clients)
        async_to_sync(run)()
