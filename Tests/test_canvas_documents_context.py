# Tlamatini Author Banner — Angela López Mendoza
"""Canvas context-set regression tests; run in the visible verification console."""
import asyncio
import json
from pathlib import Path
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "Tlamatini"))
from agent import canvas_documents_context as context  # noqa: E402
from agent.global_state import global_state  # noqa: E402


def text_doc(identity="a" * 32, filename="example.txt", content="selected text", revision=0):
    return dict(document_id=identity, filename=filename, content=content, revision=revision)


class BundleTests(unittest.TestCase):
    def setUp(self):
        scratch = ROOT / "Temp"
        scratch.mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(prefix="canvas-context-tests-", dir=scratch)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def build(self, documents, user_id=9, **kwargs):
        return context.build_canvas_context(documents, user_id, root=self.root, **kwargs)

    def test_two_selected_documents_keep_boundaries_and_unicode(self):
        bundle = self.build([text_doc(content="first unsaved revision 🦋"),
                             text_doc("b" * 32, "segundo.py", "print('á')", 7)])
        text = (bundle.directory / bundle.filename).read_text(encoding="utf-8")
        self.assertIn("example.txt", text)
        self.assertIn("segundo.py", text)
        self.assertIn("first unsaved revision 🦋", text)
        self.assertIn("print('á')", text)
        self.assertEqual([d["revision"] for d in bundle.documents], [0, 7])
        self.assertEqual(text.count("===== END CANVAS DOCUMENT ====="), 2)

    def test_unselected_open_document_is_not_read_or_included(self):
        unrelated = self.root / "not-selected.txt"
        unrelated.write_text("DO NOT SEND THIS OPEN TAB", encoding="utf-8")
        bundle = self.build([text_doc()])
        text = (bundle.directory / bundle.filename).read_text(encoding="utf-8")
        self.assertNotIn("DO NOT SEND", text)
        self.assertNotIn("not-selected.txt", text)

    def test_account_and_request_paths_are_separate(self):
        first = self.build([text_doc()])
        second = self.build([text_doc()])
        other = self.build([text_doc()], 10)
        self.assertNotEqual(first.directory, second.directory)
        self.assertEqual(first.directory.parent.name, "9")
        self.assertEqual(other.directory.parent.name, "10")
        self.assertTrue(first.directory.is_relative_to(self.root))
        self.assertEqual((first.directory / first.filename).read_bytes(),
                         (second.directory / second.filename).read_bytes())

    def test_duplicate_basenames_keep_distinct_documents(self):
        bundle = self.build([text_doc(content="one"), text_doc("b" * 32, content="two")])
        self.assertEqual(len(bundle.documents), 2)
        content = (bundle.directory / bundle.filename).read_text(encoding="utf-8")
        self.assertIn("one", content)
        self.assertIn("two", content)

    def test_duplicate_identity_is_refused_before_writing(self):
        with self.assertRaisesRegex(context.CanvasContextError, "twice"):
            self.build([text_doc(), text_doc()])
        self.assertEqual(list(self.root.iterdir()), [])

    def test_paths_and_control_names_are_refused(self):
        for name in ("../secret.txt", "sub\\secret.txt", "C:secret.txt", "", ".", "..",
                     "bad\nname.txt", "bad\x00name.txt"):
            with self.subTest(name=name), self.assertRaises(context.CanvasContextError):
                self.build([text_doc(filename=name)])

    def test_identity_revision_and_payload_types_are_validated(self):
        for change in ({"document_id": "../"}, {"revision": True}, {"revision": -1},
                       {"revision": 9007199254740992}, {"content": 7}, {"context_token": "both"}):
            with self.subTest(change=change), self.assertRaises(context.CanvasContextError):
                self.build([dict(text_doc(), **change)])

    def test_document_and_byte_limits_do_not_write_partial_context(self):
        with self.assertRaises(context.CanvasContextError):
            self.build([text_doc(str(i)) for i in range(33)])
        with patch.object(context, "MAX_CONTEXT_BYTES", 100):
            with self.assertRaisesRegex(context.CanvasContextError, "32 MiB"):
                self.build([text_doc(content="x" * 101)])
        self.assertEqual(list(self.root.iterdir()), [])

    def test_pdf_resolver_receives_authenticated_owner_and_text_is_combined(self):
        pdf = self.root / "prepared"
        pdf.mkdir()
        (pdf / "document.txt").write_text("PDF all pages: Ω", encoding="utf-8")
        calls = []
        def resolve(token, owner):
            calls.append((token, owner))
            return pdf, "document.txt"
        selected_pdf = dict(document_id="p" * 32, filename="paper.pdf", revision=2,
                            context_token="signed-for-account-9")
        bundle = self.build([text_doc(), selected_pdf], pdf_resolver=resolve)
        self.assertEqual(calls, [("signed-for-account-9", 9)])
        output = (bundle.directory / bundle.filename).read_text(encoding="utf-8")
        self.assertIn("PDF all pages: Ω", output)
        self.assertIn("selected text", output)

    def test_foreign_pdf_refusal_preserves_existing_bundle(self):
        original = self.build([text_doc()])
        old = (original.directory / original.filename).read_bytes()
        def refuse(_token, _owner):
            raise ValueError("PDF belongs to another account.")
        selected_pdf = dict(document_id="p" * 32, filename="paper.pdf", revision=0,
                            context_token="foreign-account-token")
        with self.assertRaisesRegex(ValueError, "another account"):
            self.build([selected_pdf], pdf_resolver=refuse)
        self.assertEqual((original.directory / original.filename).read_bytes(), old)
        self.assertEqual(len(list((self.root / "context_files/canvas_tabs/9").iterdir())), 1)

    def test_failed_write_removes_its_partial_file(self):
        with patch.object(context.os, "fsync", side_effect=OSError("disk full")):
            with self.assertRaisesRegex(OSError, "disk full"):
                self.build([text_doc()])
        self.assertEqual(list((self.root / "context_files/canvas_tabs/9").iterdir()), [])


class FakeConsumer:
    def __init__(self):
        self.rag_lock = asyncio.Lock()
        self.rag_chain = object()
        self.sent = []
        self.saved = []
        self.cleared = False
        self.succeed = True
        self.started = asyncio.Event()
        self.wait_for_release = None

    async def send(self, *, text_data):
        self.sent.append(json.loads(text_data))

    async def setup_contextual_rag_chain(self, directory, filename):
        self.started.set()
        if self.wait_for_release:
            await self.wait_for_release.wait()
        self.rag_chain = object()
        global_state.set_state("rag_chain_9", self.rag_chain)
        global_state.set_state("context_path_9", directory)
        return self.succeed

    async def setup_rag_chain(self):
        self.rag_chain = object()
        return self.succeed

    async def save_session_state(self, _user, directory, kind, filename):
        self.saved.append((directory, kind, filename))

    async def clear_session_state(self, _user):
        self.cleared = True


class ContextCommitTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        scratch = ROOT / "Temp"
        scratch.mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(prefix="canvas-context-commit-", dir=scratch)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.consumer = FakeConsumer()
        self.user = SimpleNamespace(pk=9)
        self.previous_chain = self.consumer.rag_chain
        global_state.set_state("rag_chain_9", self.previous_chain)
        global_state.set_state("context_path_9", "previous-context")
        self.payload = {"request_id": "request-1", "documents": [text_doc()]}
        original = context.build_canvas_context
        self.patch = patch.object(context, "build_canvas_context",
                                  side_effect=lambda docs, user: original(docs, user, root=self.root))
        self.patch.start()
        self.addCleanup(self.patch.stop)

    async def apply(self, payload=None):
        await context.apply_canvas_documents(self.consumer, self.user, payload or self.payload)

    async def test_commit_then_ack_contains_only_metadata(self):
        await self.apply()
        self.assertEqual(len(self.consumer.saved), 1)
        self.assertEqual([frame["type"] for frame in self.consumer.sent],
                         ["context-path-set", "canvas-documents-context-result"])
        result = self.consumer.sent[-1]
        self.assertTrue(result["success"])
        self.assertEqual(result["request_id"], "request-1")
        self.assertEqual(result["documents"], [{"document_id": "a" * 32,
                                              "filename": "example.txt", "revision": 0}])
        self.assertNotIn("content", json.dumps(result))

    async def test_failed_prepare_keeps_previous_chain_and_session(self):
        self.consumer.succeed = False
        await self.apply()
        self.assertFalse(self.consumer.sent[-1]["success"])
        self.assertEqual(self.consumer.saved, [])
        self.assertIs(self.consumer.rag_chain, self.previous_chain)
        self.assertIs(global_state.get_state("rag_chain_9"), self.previous_chain)
        self.assertEqual(global_state.get_state("context_path_9"), "previous-context")
        self.assertEqual(list(self.root.rglob("documents.txt")), [])

    async def test_invalid_document_never_calls_context_rebuild(self):
        await self.apply({"request_id": "request-2", "documents": [text_doc(filename="../x")]})
        self.assertFalse(self.consumer.started.is_set())
        self.assertFalse(self.consumer.sent[-1]["success"])
        self.assertEqual(self.consumer.saved, [])

    async def test_persistence_failure_restores_previous_state(self):
        async def fail(*_args):
            raise OSError("database unavailable")
        self.consumer.save_session_state = fail
        await self.apply()
        self.assertFalse(self.consumer.sent[-1]["success"])
        self.assertIs(self.consumer.rag_chain, self.previous_chain)
        self.assertEqual(global_state.get_state("context_path_9"), "previous-context")
        self.assertEqual(list(self.root.rglob("documents.txt")), [])

    async def test_clear_waits_for_successful_default_chain(self):
        await self.apply({"request_id": "clear-1", "documents": []})
        self.assertTrue(self.consumer.cleared)
        self.assertTrue(self.consumer.sent[-1]["success"])
        self.assertEqual(self.consumer.sent[-1]["documents"], [])
        self.assertIsNone(global_state.get_state("context_path_9"))

    async def test_failed_clear_does_not_discard_previous_context(self):
        self.consumer.succeed = False
        await self.apply({"request_id": "clear-1", "documents": []})
        self.assertFalse(self.consumer.cleared)
        self.assertIs(self.consumer.rag_chain, self.previous_chain)
        self.assertEqual(global_state.get_state("context_path_9"), "previous-context")

    async def test_new_request_refused_while_previous_is_preparing(self):
        self.consumer.wait_for_release = asyncio.Event()
        await context.begin_canvas_documents(self.consumer, self.user, self.payload)
        await self.consumer.started.wait()
        await context.begin_canvas_documents(self.consumer, self.user,
                                             {"request_id": "second", "documents": []})
        self.assertFalse(self.consumer.sent[-1]["success"])
        self.assertEqual(self.consumer.sent[-1]["request_id"], "second")
        self.consumer.wait_for_release.set()
        await self.consumer._canvas_documents_task
        self.assertTrue(self.consumer.sent[-1]["success"])

    async def test_cancellation_keeps_previous_context_and_cleans_bundle(self):
        self.consumer.wait_for_release = asyncio.Event()
        await context.begin_canvas_documents(self.consumer, self.user, self.payload)
        await self.consumer.started.wait()
        self.consumer._canvas_documents_task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await self.consumer._canvas_documents_task
        self.assertIs(self.consumer.rag_chain, self.previous_chain)
        self.assertEqual(self.consumer.saved, [])
        self.assertEqual(list(self.root.rglob("documents.txt")), [])

    async def test_running_chat_refuses_context_change(self):
        self.consumer._active_run = (9, "chat")
        await self.apply()
        self.assertFalse(self.consumer.sent[-1]["success"])
        self.assertEqual(self.consumer.saved, [])
        self.assertFalse(self.consumer.started.is_set())



class ExecutionOwnershipTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = ContextCommitTests.asyncSetUp
    apply = ContextCommitTests.apply

    async def test_chat_cannot_start_between_ready_and_persistence(self):
        from agent.remote_controller_guard import claim_chat, release_chat
        checked = []
        async def persist(*args):
            caller = object()
            accepted = claim_chat(9, caller)
            if accepted:
                release_chat(9, caller)
            checked.append(accepted)
            self.consumer.saved.append(args)
        self.consumer.save_session_state = persist
        await self.apply()
        self.assertEqual(checked, [False])
        caller = object()
        self.assertTrue(claim_chat(9, caller))
        release_chat(9, caller)

    async def test_other_account_is_not_locked_by_context_update(self):
        from agent.remote_controller_guard import claim_chat, release_chat
        self.consumer.wait_for_release = asyncio.Event()
        await context.begin_canvas_documents(self.consumer, self.user, self.payload)
        await self.consumer.started.wait()
        caller = object()
        self.assertTrue(claim_chat(10, caller))
        release_chat(10, caller)
        self.consumer.wait_for_release.set()
        await self.consumer._canvas_documents_task

    async def test_second_browser_cannot_replace_same_accounts_context(self):
        self.consumer.wait_for_release = asyncio.Event()
        await context.begin_canvas_documents(self.consumer, self.user, self.payload)
        await self.consumer.started.wait()
        other = FakeConsumer()
        await context.apply_canvas_documents(other, self.user, self.payload)
        self.assertFalse(other.sent[-1]["success"])
        self.assertFalse(other.started.is_set())
        self.consumer.wait_for_release.set()
        await self.consumer._canvas_documents_task

    async def test_cancellation_releases_account_execution_lane(self):
        from agent.remote_controller_guard import claim_chat, release_chat
        self.consumer.wait_for_release = asyncio.Event()
        await context.begin_canvas_documents(self.consumer, self.user, self.payload)
        await self.consumer.started.wait()
        self.consumer._canvas_documents_task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await self.consumer._canvas_documents_task
        caller = object()
        self.assertTrue(claim_chat(9, caller))
        release_chat(9, caller)


class ReconnectContextGuardTests(unittest.IsolatedAsyncioTestCase):
    """Execute the actual decorator around isolated legacy receive operations."""

    async def asyncSetUp(self):
        await ContextCommitTests.asyncSetUp(self)
        import ast
        source = ROOT / "Tlamatini/agent/consumers.py"
        tree = ast.parse(source.read_text(encoding="utf-8-sig"))
        consumer = next(node for node in tree.body if isinstance(node, ast.ClassDef)
                        and node.name == "AgentConsumer")
        receive = next(node for node in consumer.body if isinstance(node, ast.AsyncFunctionDef)
                       and node.name == "receive")
        self.assertTrue(any(isinstance(node, ast.Name) and node.id == "serialize_context_mutations"
                            for node in receive.decorator_list))
        self.receive_source = receive
        self.user.is_authenticated = True
        self.consumer.scope = {"user": self.user}
        self.consumer._say = lambda message: message
        self.messages = []
        async def message(event):
            self.messages.append(event)
        self.consumer.agent_message = message
        self.legacy_started = asyncio.Event()
        self.legacy_release = None
        self.legacy_error = None
        self.legacy_hook = None
        self.controls = []
        async def legacy_receive(consumer, text_data):
            kind = json.loads(text_data)["type"]
            if kind not in context.LEGACY_CONTEXT_MESSAGES:
                self.controls.append(kind)
                return
            self.legacy_started.set()
            if self.legacy_hook:
                await self.legacy_hook(consumer)
            if self.legacy_release:
                await self.legacy_release.wait()
            if self.legacy_error:
                raise self.legacy_error
        self.dispatch = context.serialize_context_mutations(legacy_receive)
        self.addAsyncCleanup(context.cancel_canvas_context_tasks, self.consumer)

    async def start_legacy(self, kind="reconnect-llm-agent", consumer=None):
        await self.dispatch(consumer or self.consumer, json.dumps({"type": kind, "message": ""}))

    async def test_reconnect_waits_for_pending_context_rollback(self):
        self.consumer.wait_for_release = asyncio.Event()
        self.consumer._canvas_documents_metadata = [{"filename": "previous.txt"}]
        await context.begin_canvas_documents(self.consumer, self.user, self.payload)
        await self.consumer.started.wait()
        await self.start_legacy()
        await self.consumer._canvas_legacy_context_task
        self.assertTrue(self.consumer._canvas_documents_task.cancelled())
        self.assertIs(self.consumer.rag_chain, self.previous_chain)
        self.assertIs(global_state.get_state("rag_chain_9"), self.previous_chain)
        self.assertEqual(global_state.get_state("context_path_9"), "previous-context")
        self.assertEqual(list(self.root.rglob("documents.txt")), [])
        self.assertEqual(self.consumer._canvas_documents_metadata, [])

    async def test_clear_history_reconnect_also_waits_for_pending_context(self):
        self.consumer.wait_for_release = asyncio.Event()
        await context.begin_canvas_documents(self.consumer, self.user, self.payload)
        await self.consumer.started.wait()
        await self.start_legacy("clean-history-and-reconnect")
        await self.consumer._canvas_legacy_context_task
        self.assertTrue(self.consumer._canvas_documents_task.cancelled())
        self.assertIs(self.consumer.rag_chain, self.previous_chain)
        self.assertEqual(self.consumer.saved, [])

    async def test_reconnect_from_other_browser_does_not_disturb_context_owner(self):
        self.consumer.wait_for_release = asyncio.Event()
        await context.begin_canvas_documents(self.consumer, self.user, self.payload)
        await self.consumer.started.wait()
        other = FakeConsumer()
        other.scope = {"user": self.user}
        other._say = self.consumer._say
        other.agent_message = self.consumer.agent_message
        await self.start_legacy(consumer=other)
        self.assertEqual(len(self.messages), 1)
        self.assertFalse(hasattr(other, "_canvas_legacy_context_task"))
        self.assertFalse(self.consumer._canvas_documents_task.done())
        self.consumer.wait_for_release.set()
        await self.consumer._canvas_documents_task
        self.assertTrue(self.consumer.sent[-1]["success"])

    async def test_pending_rollback_then_legacy_await_reserves_whole_operation(self):
        from agent.remote_controller_guard import claim_chat, release_chat
        self.consumer.wait_for_release = asyncio.Event()
        await context.begin_canvas_documents(self.consumer, self.user, self.payload)
        await self.consumer.started.wait()
        self.legacy_release = asyncio.Event()
        await self.start_legacy()
        await self.legacy_started.wait()
        other = FakeConsumer()
        await context.apply_canvas_documents(other, self.user, self.payload)
        self.assertFalse(other.sent[-1]["success"])
        self.assertFalse(other.started.is_set())
        other_account = object()
        self.assertTrue(claim_chat(10, other_account))
        release_chat(10, other_account)
        self.legacy_release.set()
        await self.consumer._canvas_legacy_context_task
        await context.apply_canvas_documents(other, self.user, self.payload)
        self.assertTrue(other.sent[-1]["success"])

    async def test_legacy_error_releases_reservation(self):
        from agent.remote_controller_guard import chat_busy
        self.legacy_error = RuntimeError("controlled legacy failure")
        with self.assertLogs(context._LOG, level="ERROR"):
            await self.start_legacy()
            await self.consumer._canvas_legacy_context_task
        self.assertFalse(chat_busy(9))
        self.assertIsNone(self.consumer._canvas_mutation_owner)

    async def test_disconnect_cancels_legacy_and_releases_reservation(self):
        from agent.remote_controller_guard import chat_busy
        self.legacy_release = asyncio.Event()
        await self.start_legacy()
        await self.legacy_started.wait()
        await context.cancel_canvas_context_tasks(self.consumer)
        self.assertTrue(self.consumer._canvas_legacy_context_task.cancelled())
        self.assertFalse(chat_busy(9))

    async def test_cancel_before_task_starts_still_releases_reservation(self):
        from agent.remote_controller_guard import chat_busy
        await self.start_legacy()
        self.consumer._canvas_legacy_context_task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await self.consumer._canvas_legacy_context_task
        self.assertFalse(chat_busy(9))

    async def test_control_messages_remain_responsive_during_legacy_rebuild(self):
        self.legacy_release = asyncio.Event()
        await self.start_legacy()
        await self.legacy_started.wait()
        await self.dispatch(self.consumer, json.dumps({"type": "cancel-current"}))
        self.assertEqual(self.controls, ["cancel-current"])
        self.assertFalse(self.consumer._canvas_legacy_context_task.done())
        self.legacy_release.set()
        await self.consumer._canvas_legacy_context_task

    async def test_disconnect_called_inside_legacy_task_does_not_await_itself(self):
        from agent.remote_controller_guard import chat_busy
        self.legacy_hook = context.cancel_canvas_context_tasks
        await self.start_legacy()
        await self.consumer._canvas_legacy_context_task
        self.assertFalse(chat_busy(9))

    def test_actual_legacy_branches_await_rebuilds_inside_owned_task(self):
        import ast
        found = set()
        for branch in ast.walk(self.receive_source):
            if not isinstance(branch, ast.If) or not isinstance(branch.test, ast.Compare):
                continue
            if not isinstance(branch.test.left, ast.Name) or branch.test.left.id != "type":
                continue
            kinds = {part.value for part in ast.walk(branch.test)
                     if isinstance(part, ast.Constant) and isinstance(part.value, str)}
            kinds &= context.LEGACY_CONTEXT_MESSAGES
            if not kinds:
                continue
            found.update(kinds)
            for statement in branch.body:
                self.assertFalse(any(isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                                     and node.func.attr == "create_task" for node in ast.walk(statement)), kinds)
        self.assertEqual(found, context.LEGACY_CONTEXT_MESSAGES)


class ActualReceiveEntryTests(unittest.IsolatedAsyncioTestCase):
    """Run the entire actual receive method, including its real dispatch path."""

    async def asyncSetUp(self):
        await ContextCommitTests.asyncSetUp(self)
        import ast
        source = ROOT / "Tlamatini/agent/consumers.py"
        tree = ast.parse(source.read_text(encoding="utf-8-sig"))
        consumer = next(node for node in tree.body if isinstance(node, ast.ClassDef)
                        and node.name == "AgentConsumer")
        receive = next(node for node in consumer.body if isinstance(node, ast.AsyncFunctionDef)
                       and node.name == "receive")
        constants = SimpleNamespace(ERROR_AGENT_NOT_READY="not ready", ERROR_DETAIL_PREFIX="error: ",
                                    ERROR_NOT_AUTHENTICATED="not authenticated")
        namespace = {"__package__": "agent", "asyncio": asyncio, "json": json, "_WS_TRACE": False,
                     "log_identity": SimpleNamespace(bind=lambda *_args: None),
                     "constants": constants, "serialize_context_mutations": context.serialize_context_mutations}
        exec(compile(ast.Module(body=[receive], type_ignores=[]), str(source), "exec"), namespace)
        self.receive = namespace["receive"].__get__(self.consumer)
        self.user.id = self.user.pk
        self.user.username = "canvas-context-test"
        self.user.is_authenticated = True
        self.consumer.scope = {"user": self.user}
        self.consumer._say = lambda message: message
        self.consumer.room_group_name = "canvas-context-test"
        self.events = []
        async def broadcast(_room, event):
            self.events.append(event)
        self.consumer.channel_layer = SimpleNamespace(group_send=broadcast)
        self.addAsyncCleanup(context.cancel_canvas_context_tasks, self.consumer)

    async def test_actual_receive_accepts_selection_without_chat_message_and_acks(self):
        payload = {"type": "set-canvas-documents-as-context", **self.payload}
        self.assertNotIn("message", payload)
        await self.receive(json.dumps(payload))
        self.assertIsNotNone(getattr(self.consumer, "_canvas_documents_task", None), self.events)
        await self.consumer._canvas_documents_task
        self.assertEqual(self.events, [])
        self.assertTrue(self.consumer.sent[-1]["success"])
        self.assertEqual(self.consumer.sent[-1]["request_id"], payload["request_id"])
        self.assertEqual(self.consumer.sent[-1]["documents"][0]["document_id"], "a" * 32)
        self.assertEqual(len(self.consumer.saved), 1)

    async def test_actual_receive_clears_selection_without_chat_message(self):
        await self.receive(json.dumps({"type": "set-canvas-documents-as-context",
                                       "request_id": "clear-from-receive", "documents": []}))
        self.assertIsNotNone(getattr(self.consumer, "_canvas_documents_task", None), self.events)
        await self.consumer._canvas_documents_task
        self.assertTrue(self.consumer.cleared)
        self.assertEqual(self.consumer.sent[-1]["documents"], [])
        self.assertTrue(self.consumer.sent[-1]["success"])

    async def test_actual_receive_refuses_unauthenticated_selection(self):
        self.user.is_authenticated = False
        await self.receive(json.dumps({"type": "set-canvas-documents-as-context", **self.payload}))
        self.assertFalse(hasattr(self.consumer, "_canvas_documents_task"))
        self.assertEqual(self.events[-1]["message"], "not authenticated")
        self.assertEqual(self.consumer.saved, [])

    async def test_other_control_frames_retain_existing_message_requirement(self):
        await self.receive(json.dumps({"type": "context-gauge-refresh"}))
        self.assertFalse(hasattr(self.consumer, "_canvas_documents_task"))
        self.assertEqual(self.events[-1]["message"], "error: 'message'")


class ActualConsumerMethodsTests(unittest.IsolatedAsyncioTestCase):
    """Execute the real consumer methods; substitute only DB/model/network edges."""

    apply = ContextCommitTests.apply

    async def asyncSetUp(self):
        await ContextCommitTests.asyncSetUp(self)
        import ast
        source = ROOT / "Tlamatini/agent/consumers.py"
        tree = ast.parse(source.read_text(encoding="utf-8-sig"))
        consumer = next(node for node in tree.body if isinstance(node, ast.ClassDef)
                        and node.name == "AgentConsumer")
        methods = [node for node in consumer.body if isinstance(node, ast.AsyncFunctionDef)
                   and node.name in {"setup_rag_chain", "setup_contextual_rag_chain"}]
        self.assertEqual(len(methods), 2)
        class Constants:
            def __getattr__(self, name):
                return name
        class Basic:
            pass
        class Optimized:
            def getDetectedOversizedDocs(self):
                return False
        self.basic_type = Basic
        self.next_chain = object()
        namespace = {"__package__": "agent", "asyncio": asyncio, "global_state": global_state,
                     "constants": Constants(), "BasicPromptOnlyChain": Basic,
                     "OptimizedHistoryAwareRAGChain": Optimized,
                     "setup_llm": lambda *_args: self.next_chain,
                     "setup_llm_with_context": lambda *_args: self.next_chain}
        exec(compile(ast.Module(body=methods, type_ignores=[]), str(source), "exec"), namespace)
        self.namespace = namespace
        for name in ("setup_rag_chain", "setup_contextual_rag_chain"):
            setattr(self.consumer, name, namespace[name].__get__(self.consumer))
        async def empty(*_args):
            return []
        async def no_omission(*_args):
            return None
        async def broadcast(_room, _event):
            pass
        self.consumer.get_omission_by_name = no_omission
        for name in ("get_all_mcps", "get_all_tools", "get_all_agents", "get_all_skills"):
            setattr(self.consumer, name, empty)
        self.consumer.scope = {"user": SimpleNamespace(id=9, pk=9, is_authenticated=True)}
        self.consumer.channel_layer = SimpleNamespace(group_send=broadcast)
        self.consumer.room_group_name = "test-user-9"
        self.consumer._say = lambda text: text
        self.consumer._take_gauge_reason = lambda reason: reason
        self.consumer._schedule_context_gauge_refresh = lambda _reason: None
        global_state.set_state("cancel_generation", False)
        self.addCleanup(global_state.set_state, "cancel_generation", False)
        modules = patch.dict(sys.modules, {
            "agent.embedding_memory_guard": SimpleNamespace(
                check_embedding_memory_for_directory=lambda *_args: None,
                format_warning_message=lambda _warning: ""),
            "agent.config_loader": SimpleNamespace(load_config=lambda: {}),
        })
        modules.start()
        self.addCleanup(modules.stop)

    # These scenarios exercise the current source methods, not FakeConsumer's
    # context preparation substitutes used in the separate commit tests.
    async def test_real_context_success_commits_same_chain_to_cache(self):
        await self.apply()
        self.assertTrue(self.consumer.sent[-1]["success"])
        self.assertIs(self.consumer.rag_chain, self.next_chain)
        self.assertIs(global_state.get_state("rag_chain_9"), self.next_chain)
        self.assertEqual(global_state.get_state("context_path_9"), self.consumer.saved[0][0])

    async def test_real_context_basic_fallback_does_not_claim_selected_context(self):
        self.next_chain = self.basic_type()
        await self.apply()
        self.assertFalse(self.consumer.sent[-1]["success"])
        self.assertIs(self.consumer.rag_chain, self.previous_chain)
        self.assertIs(global_state.get_state("rag_chain_9"), self.previous_chain)
        self.assertEqual(global_state.get_state("context_path_9"), "previous-context")
        self.assertEqual(self.consumer.saved, [])

    async def test_real_context_none_restores_previous_chain(self):
        self.next_chain = None
        await self.apply()
        self.assertFalse(self.consumer.sent[-1]["success"])
        self.assertIs(self.consumer.rag_chain, self.previous_chain)
        self.assertEqual(self.consumer.saved, [])

    async def test_real_context_cancel_flag_refuses_without_committing(self):
        global_state.set_state("cancel_generation", True)
        await self.apply()
        self.assertFalse(self.consumer.sent[-1]["success"])
        self.assertIs(self.consumer.rag_chain, self.previous_chain)
        self.assertEqual(self.consumer.saved, [])

    async def test_real_default_chain_success_is_explicit(self):
        await self.apply({"request_id": "clear-real", "documents": []})
        self.assertTrue(self.consumer.sent[-1]["success"])
        self.assertIs(self.consumer.rag_chain, self.next_chain)
        self.assertIs(global_state.get_state("rag_chain_9"), self.next_chain)
        self.assertIsNone(global_state.get_state("context_path_9"))

    async def test_real_default_chain_failure_does_not_clear_context(self):
        self.next_chain = None
        await self.apply({"request_id": "clear-real", "documents": []})
        self.assertFalse(self.consumer.sent[-1]["success"])
        self.assertFalse(self.consumer.cleared)
        self.assertEqual(global_state.get_state("context_path_9"), "previous-context")

    async def test_real_ready_broadcast_cannot_admit_chat_before_commit(self):
        from agent.remote_controller_guard import claim_chat, release_chat
        attempts = []
        async def broadcast(_room, event):
            if event["message"] == "MSG_AGENT_READY":
                self.assertIs(global_state.get_state("rag_chain_9"), self.previous_chain)
                self.assertEqual(global_state.get_state("context_path_9"), "previous-context")
                caller = object()
                accepted = claim_chat(9, caller)
                attempts.append(accepted)
                if accepted:
                    release_chat(9, caller)
        self.consumer.channel_layer.group_send = broadcast
        await self.apply()
        self.assertTrue(self.consumer.sent[-1]["success"])
        self.assertEqual(attempts, [False])

    async def test_real_reconnect_cache_stays_previous_until_database_commit(self):
        checked = []
        async def persist(*args):
            checked.append((global_state.get_state("rag_chain_9"),
                            global_state.get_state("context_path_9")))
            self.consumer.saved.append(args)
        self.consumer.save_session_state = persist
        await self.apply()
        self.assertEqual(checked, [(self.previous_chain, "previous-context")])
        self.assertIs(global_state.get_state("rag_chain_9"), self.next_chain)
        self.assertEqual(global_state.get_state("context_path_9"), self.consumer.saved[0][1])


if __name__ == "__main__":
    unittest.main(verbosity=2)
