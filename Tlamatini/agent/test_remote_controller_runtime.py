# Tlamatini — Created by Angela López Mendoza · @angelahack1
"""Deterministic runtime/ownership checks; no model, live account or database.

Run from an authorized visible development console. The narrow fake consumer is
the dependency boundary; production always imports the actual AgentConsumer.
"""
import asyncio
import json
import sys
import types
import unittest
import uuid
from unittest.mock import AsyncMock, patch

from . import remote_controller_guard as guard
from . import remote_controller_runtime as runtime


class GuardTests(unittest.TestCase):
    def setUp(self):
        self.uid = 74001
        self.a, self.b = object(), object()

    def tearDown(self):
        for uid in (self.uid, self.uid + 1):
            guard.release_chat(uid, self.a)
            guard.release_chat(uid, self.b)

    def test_reservation_blocks_another_owner(self):
        self.assertTrue(guard.reserve_chat(self.uid, self.a))
        self.assertFalse(guard.reserve_chat(self.uid, self.b))

    def test_reservation_becomes_one_execution(self):
        self.assertTrue(guard.reserve_chat(self.uid, self.a))
        self.assertTrue(guard.claim_chat(self.uid, self.a))
        self.assertFalse(guard.claim_chat(self.uid, self.a))

    def test_desktop_claim_needs_no_reservation(self):
        self.assertTrue(guard.claim_chat(self.uid, self.a))
        self.assertTrue(guard.owns_chat(self.uid, self.a))

    def test_wrong_owner_cannot_release(self):
        guard.claim_chat(self.uid, self.a)
        guard.release_chat(self.uid, self.b)
        self.assertTrue(guard.chat_busy(self.uid))

    def test_owner_release_admits_next_request(self):
        guard.claim_chat(self.uid, self.a)
        guard.release_chat(self.uid, self.a)
        self.assertTrue(guard.claim_chat(self.uid, self.b))

    def test_accounts_have_independent_claims(self):
        self.assertTrue(guard.claim_chat(self.uid, self.a))
        self.assertTrue(guard.claim_chat(self.uid + 1, self.b))

    def test_release_without_claim_is_idempotent(self):
        guard.release_chat(self.uid, self.a)
        guard.release_chat(self.uid, self.a)
        self.assertFalse(guard.chat_busy(self.uid))


class _State:
    def __init__(self):
        self.values = {}

    def get_state(self, key):
        return self.values.get(key)

    def set_state(self, key, value):
        self.values[key] = value


class _Layer:
    def __init__(self):
        self.sent = []

    async def group_send(self, group, event):
        self.sent.append((group, event))


class _Broker:
    def __init__(self):
        self.closed = False
        self.decisions = []

    def resolve(self, request_id, decision):
        if self.closed:
            return False
        self.decisions.append((request_id, decision))
        return True

    def close(self):
        self.closed = True


class AssistantTextTests(unittest.TestCase):
    def test_escaped_markup_is_returned_as_inert_literal_text(self):
        self.assertEqual(runtime._assistant_text('&lt;img src=x onerror=&quot;alert(1)&quot;&gt;'),
                         '<img src=x onerror="alert(1)">')

    def test_entities_are_decoded_only_once(self):
        self.assertEqual(runtime._assistant_text('&amp;lt;script&amp;gt;'), '&lt;script&gt;')

    def test_blocks_line_breaks_and_code_keep_readable_separation(self):
        source = '<p>First<br>Second</p><pre><code>x &lt; 3\n  y</code></pre><div>Last</div>'
        self.assertEqual(runtime._assistant_text(source), 'First\nSecond\nx < 3\n  y\nLast')

    def test_script_and_style_contents_are_omitted(self):
        source = '<p>Safe<script>alert("no")</script><style>body{display:none}</style>end</p>'
        self.assertEqual(runtime._assistant_text(source), 'Safeend')

    def test_attributes_and_comments_do_not_become_answer_content(self):
        self.assertEqual(runtime._assistant_text('<a href="javascript:alert(1)">Link</a><!-- hidden -->'), 'Link')


class RuntimeTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.user = types.SimpleNamespace(pk=75001, id=75001, username="runtime-test", is_authenticated=True, is_active=True)
        self.state = _State()
        self.layer = _Layer()
        self.frames = []
        self.behavior = "answer"
        self.setup_calls = 0
        self.context_calls = []
        self.session_state = None
        self.last_frame = None
        self.prepare_started = asyncio.Event()
        self.prepare_release = asyncio.Event()
        self.answer = "A real consumer fixture reply."
        self.source_answer = None
        self.system_html = ''
        from . import remote_response_files
        for name, replacement in {
            "_profile": lambda uid: types.SimpleNamespace(user_id=uid, account=uuid.UUID(int=1), binding_id="2" * 32),
            "_message": lambda uid, mid: types.SimpleNamespace(pk=mid, conversation_user_id=uid, message=self.answer, response_files=[]),
        }.items():
            patcher = patch.object(remote_response_files, name, side_effect=replacement)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.permission_id = "a" * 32
        self.broker = _Broker()
        case = self

        class Consumer:
            def __init__(self):
                self.rag_chain = None
                self._active_run = None
                self._active_broker = None
                self._rc_chat_claim_refused = False

            async def get_session_state(self, user):
                case.assertEqual(user.pk, case.user.pk)
                return case.session_state

            async def setup_rag_chain(self):
                case.setup_calls += 1
                if case.behavior == "preparation-wait":
                    case.prepare_started.set()
                    await case.prepare_release.wait()
                if case.behavior != "model-missing":
                    self.rag_chain = object()

            async def setup_contextual_rag_chain(self, path, filename=None):
                case.context_calls.append((path, filename))
                self.rag_chain = object()

            async def receive(self, frame):
                case.last_frame = json.loads(frame)
                if case.behavior == "greeting":
                    await self.channel_layer.group_send(self.room_group_name, {
                        "type": "agent_message", "username": "Tlamatini", "message": "Hello!",
                    })
                elif case.behavior == "positional":
                    asyncio.create_task(self.queue_llm_retrieval(
                        case.last_frame["message"], case.user, False, False, True, False,
                        True, "owned-client", None,
                    ))
                elif case.behavior != "silent":
                    asyncio.create_task(self.queue_llm_retrieval(case.last_frame["message"], case.user))

            async def queue_llm_retrieval(self, message, user, **flags):
                if not guard.claim_chat(user.pk, self):
                    self._rc_chat_claim_refused = True
                    return
                case.flags = flags
                self._active_broker = case.broker
                self._active_run = (user.pk, 1)
                try:
                    if case.behavior in {"permission", "large-permission", "lost-channel"}:
                        await self.channel_layer.group_send(self.room_group_name, {
                            "type": "exec_permission_request", "detail": {
                                "request_id": case.permission_id, "tool_name": "file_creator",
                                "parameters": "x" * (1700 if case.behavior == "large-permission" else 8),
                            },
                        })
                    if case.behavior in {"cancel", "cancel-race"}:
                        case.cancel_event.set()
                        if case.behavior == "cancel":
                            await asyncio.sleep(0)
                    if case.behavior == "foreign-room":
                        await self.channel_layer.group_send("chat_user_other", {
                            "type": "agent_message", "username": "Tlamatini", "message": "Private other answer", "message_id": 6,
                        })
                    if case.source_answer is not None:
                        self.channel_layer.capture_source_answer(self.room_group_name, case.source_answer, case.system_html)
                    await self.channel_layer.group_send(self.room_group_name, {
                        "type": "agent_message", "username": "Tlamatini", "message": case.answer,
                        **({} if case.behavior == "status-only" else {"message_id": 7}),
                    })
                finally:
                    self._active_run = None
                    self._active_broker = None
                    guard.release_chat(user.pk, self)

        modules = {
            "agent.consumers": types.SimpleNamespace(AgentConsumer=Consumer),
            "agent.global_state": types.SimpleNamespace(global_state=self.state),
            "channels.layers": types.SimpleNamespace(get_channel_layer=lambda: self.layer),
            "agent.constants": types.SimpleNamespace(REGEX_GREETING=r"^hello$"),
        }
        self.patch = patch.dict(sys.modules, modules)
        self.patch.start()
        # request_cancel imports real cancellation; use its existing instance's
        # global_state too if another suite has already imported it.
        from . import cancellation
        self.cancel_patch = patch.object(cancellation, "global_state", self.state)
        self.cancel_patch.start()
        self.state.set_state("llm_run_epoch::75001", 1)

    async def asyncTearDown(self):
        self.cancel_patch.stop()
        self.patch.stop()

    async def collect(self, frame):
        self.frames.append(frame)

    async def run_session(self, text="Explain this request", callback=None):
        session = runtime.RuntimeSession(self.user, callback or self.collect)
        return session, await session.run(text)

    async def test_normal_reply_uses_main_receive_flags(self):
        session, answer = await self.run_session()
        self.assertEqual(answer["text"], self.answer)
        self.assertEqual(answer["message_id"], 7)
        self.assertTrue(self.last_frame["multi_turn_enabled"])
        self.assertTrue(self.last_frame["ask_execs_enabled"])
        self.assertTrue(self.flags["ask_execs_enabled"])
        self.assertFalse(self.flags["acpx_enabled"])
        self.assertEqual(session.status, "completed")
        self.assertFalse(guard.chat_busy(self.user.pk))

    async def test_model_literal_html_survives_rich_answer_formatting(self):
        self.answer = '<b>safe</b><br>'
        self.source_answer = '<b>safe</b>\n\nEND-RESPONSE'
        _, answer = await self.run_session()
        self.assertEqual(answer['text'], '<b>safe</b>')

    async def test_model_entities_and_script_text_remain_inert_source(self):
        self.answer = '<p>Rendered</p>'
        self.source_answer = '&lt;tag&gt; <script>alert(1)</script>\nEND-RESPONSE'
        _, answer = await self.run_session()
        self.assertEqual(answer['text'], '&lt;tag&gt; <script>alert(1)</script>')

    async def test_source_answer_retains_system_report_and_denial_text(self):
        self.answer = '<b>safe</b><table><tr><td>Done</td></tr></table>'
        self.source_answer = '<b>safe</b>\nEND-RESPONSE'
        self.system_html = '<table><tr><td>Done</td></tr></table><p>Execution interrupted</p>'
        _, answer = await self.run_session()
        self.assertEqual(answer['text'], '<b>safe</b>\nDone\nExecution interrupted')

    async def test_long_plain_fallback_does_not_mark_complete_html_truncated(self):
        self.source_answer = '<>&' * 12000 + '\nEND-RESPONSE'
        _, answer = await self.run_session()
        self.assertFalse(answer['truncated'])
        self.assertEqual(answer['html'], self.answer)
        self.assertLessEqual(runtime._wire_size(answer['text']), runtime.MAX_TEXT_BYTES)

    async def test_source_answer_from_foreign_room_is_ignored(self):
        session = runtime.RuntimeSession(self.user, self.collect)
        session._capturing = True
        layer = runtime._OwnedChannelLayer(self.layer, 'chat_user_owned', session)
        layer.capture_source_answer('chat_user_other', 'Private', '')
        self.assertIsNone(session._source_answer)

    async def test_selected_modes_reach_the_main_executor(self):
        from itertools import product
        for report, acpx, ask in product((False, True), repeat=3):
            with self.subTest(report=report, acpx=acpx, ask=ask):
                options = {"multi_turn_enabled": True, "exec_report_enabled": report,
                           "acpx_enabled": acpx, "ask_execs_enabled": ask,
                           "step_by_step_enabled": True}
                session = runtime.RuntimeSession(self.user, self.collect, options)
                answer = await session.run("Check selected modes")
                for name, enabled in options.items():
                    self.assertIs(self.last_frame[name], enabled)
                    self.assertIs(self.flags[name], enabled)
                    self.assertIs(answer["options"][name], enabled)

    async def test_one_shot_does_not_silently_enable_multiturn(self):
        options = {"multi_turn_enabled": False}
        session = runtime.RuntimeSession(self.user, self.collect, options)
        await session.run("One shot")
        for name in ("multi_turn_enabled", "exec_report_enabled", "acpx_enabled", "ask_execs_enabled"):
            self.assertFalse(self.last_frame[name])
            self.assertFalse(self.flags[name])

    async def test_self_modify_uses_the_existing_application_setting(self):
        setting = types.SimpleNamespace(set_self_modify=lambda enabled, reason: {"ok": True})
        for enabled in (False, True):
            with self.subTest(enabled=enabled), patch.dict(sys.modules, {"agent.compact_mode": setting}):
                with patch.object(setting, "set_self_modify", wraps=setting.set_self_modify) as update:
                    session = runtime.RuntimeSession(self.user, self.collect, {"self_modify_enabled": enabled})
                    answer = await session.run("Check self modification choice")
                    update.assert_called_once_with(enabled, f"Remote-Controller user {self.user.pk}")
                    self.assertIs(answer["options"]["self_modify_enabled"], enabled)

    async def test_unavailable_self_modify_does_not_send_a_different_prompt(self):
        setting = types.SimpleNamespace(set_self_modify=lambda enabled, reason: {"ok": False, "refused": "too_small"})
        with patch.dict(sys.modules, {"agent.compact_mode": setting}):
            session = runtime.RuntimeSession(self.user, self.collect, {"self_modify_enabled": True})
            with self.assertRaisesRegex(runtime.RuntimeFault, "self_modify_too_small"):
                await session.run("Must not run with different settings")
        self.assertIsNone(self.last_frame)
        self.assertFalse(guard.chat_busy(self.user.pk))

    async def test_unchanged_self_modify_choice_does_not_rewrite_the_setting(self):
        for enabled in (False, True):
            writes = []
            setting = types.SimpleNamespace(
                state=lambda enabled=enabled: {"self_modify": enabled, "self_modify_available": True,
                                               "self_modify_locked": False},
                set_self_modify=lambda value, reason, writes=writes: writes.append(value) or {"ok": True},
            )
            with self.subTest(enabled=enabled), patch.dict(sys.modules, {"agent.compact_mode": setting}):
                session = runtime.RuntimeSession(self.user, self.collect, {"self_modify_enabled": enabled})
                answer = await session.run("Keep the current self modification choice")
                self.assertEqual(writes, [])
                self.assertIs(answer["options"]["self_modify_enabled"], enabled)

    async def test_changed_self_modify_choice_is_written_once(self):
        writes = []
        setting = types.SimpleNamespace(
            state=lambda: {"self_modify": False, "self_modify_available": True, "self_modify_locked": False},
            set_self_modify=lambda value, reason: writes.append((value, reason)) or {"ok": True},
        )
        with patch.dict(sys.modules, {"agent.compact_mode": setting}):
            session = runtime.RuntimeSession(self.user, self.collect, {"self_modify_enabled": True})
            await session.run("Turn self modification on")
        self.assertEqual(writes, [(True, f"Remote-Controller user {self.user.pk}")])

    def test_mode_validation_rejects_unknown_or_nonboolean_fields(self):
        for invalid in ({"command": "anything"}, {"acpx_enabled": "false"}, {"multi_turn_enabled": 1}, [], True):
            with self.subTest(invalid=invalid), self.assertRaises(runtime.RuntimeFault):
                runtime.execution_options(invalid)
        with self.assertRaisesRegex(runtime.RuntimeFault, "multiturn_required"):
            runtime.execution_options({"multi_turn_enabled": False, "acpx_enabled": True})
        # Step-by-step paces a Multi-Turn run, exactly as on the desktop.
        with self.assertRaisesRegex(runtime.RuntimeFault, "multiturn_required"):
            runtime.execution_options({"multi_turn_enabled": False, "step_by_step_enabled": True})
        self.assertFalse(runtime.execution_options({"multi_turn_enabled": False})["step_by_step_enabled"])

    async def test_original_positional_queue_api_keeps_remote_permission_flags(self):
        self.behavior = "positional"
        _, answer = await self.run_session()
        self.assertEqual(answer["text"], self.answer)
        self.assertTrue(self.flags["multi_turn_enabled"])
        self.assertTrue(self.flags["exec_report_enabled"])
        self.assertTrue(self.flags["ask_execs_enabled"])
        self.assertFalse(self.flags["acpx_enabled"])
        self.assertTrue(self.flags["step_by_step_enabled"])
        self.assertEqual(self.flags["interactor_client_id"], "owned-client")

    async def test_rendered_assistant_answer_becomes_plain_text_in_progress_and_result(self):
        self.answer = '<p>Use &lt;tag&gt; &amp; &quot;quotes&quot;.</p><script>hidden</script>'
        _, answer = await self.run_session()
        self.assertEqual(answer["text"], 'Use <tag> & "quotes".')
        message = next(frame for frame in self.frames if frame["type"] == "message")
        self.assertEqual(message["text"], answer["text"])

    async def test_anonymous_account_refused(self):
        self.user.is_authenticated = False
        with self.assertRaisesRegex(runtime.RuntimeFault, "account_unavailable"):
            await self.run_session()

    async def test_disabled_account_refused(self):
        self.user.is_active = False
        with self.assertRaisesRegex(runtime.RuntimeFault, "account_unavailable"):
            await self.run_session()

    async def test_blank_prompt_refused(self):
        with self.assertRaisesRegex(runtime.RuntimeFault, "invalid_request"):
            await self.run_session(" \t ")

    async def test_oversize_prompt_refused(self):
        with self.assertRaisesRegex(runtime.RuntimeFault, "invalid_request"):
            await self.run_session("a" * 16001)

    async def test_session_is_single_use(self):
        session, _ = await self.run_session()
        with self.assertRaisesRegex(runtime.RuntimeFault, "session_already_used"):
            await session.run("Again")

    async def test_local_account_claim_refuses_remote(self):
        local = object()
        guard.claim_chat(self.user.pk, local)
        try:
            with self.assertRaisesRegex(runtime.RuntimeFault, "account_busy"):
                await self.run_session()
            self.assertTrue(guard.owns_chat(self.user.pk, local))
        finally:
            guard.release_chat(self.user.pk, local)

    async def test_missing_model_is_not_a_success(self):
        self.behavior = "model-missing"
        with self.assertRaisesRegex(runtime.RuntimeFault, "model_unavailable"):
            await self.run_session()
        self.assertFalse(guard.chat_busy(self.user.pk))

    async def test_existing_account_chain_is_reused(self):
        self.state.set_state("rag_chain_75001", object())
        await self.run_session()
        self.assertEqual(self.setup_calls, 0)

    async def test_other_account_chain_is_not_reused(self):
        self.state.set_state("rag_chain_75002", object())
        await self.run_session()
        self.assertEqual(self.setup_calls, 1)

    async def test_saved_file_context_uses_normal_context_builder(self):
        self.session_state = types.SimpleNamespace(
            context_path="C:/Application/context", context_type="file", context_filename="owned.txt", is_expired=lambda: False,
        )
        await self.run_session()
        self.assertEqual(self.context_calls, [("C:/Application/context", "owned.txt")])

    async def test_expired_context_uses_normal_empty_builder(self):
        self.session_state = types.SimpleNamespace(context_path="C:/Application/context", is_expired=lambda: True)
        await self.run_session()
        self.assertEqual(self.setup_calls, 1)
        self.assertEqual(self.context_calls, [])

    async def test_other_room_never_reaches_remote_callback(self):
        self.behavior = "foreign-room"
        _, answer = await self.run_session()
        self.assertEqual(answer["text"], self.answer)
        self.assertNotIn("Private other answer", json.dumps(self.frames))
        self.assertTrue(any(group == "chat_user_other" for group, _ in self.layer.sent))

    async def test_status_without_saved_answer_is_not_completion(self):
        self.behavior = "status-only"
        with self.assertRaisesRegex(runtime.RuntimeFault, "chat_no_answer"):
            await self.run_session()

    async def test_silence_is_not_a_fabricated_answer(self):
        self.behavior = "silent"
        with self.assertRaisesRegex(runtime.RuntimeFault, "chat_no_answer"):
            await self.run_session()

    async def test_real_immediate_greeting_is_returned(self):
        self.behavior = "greeting"
        _, answer = await self.run_session("hello")
        self.assertEqual(answer["text"], "Hello!")

    async def test_long_answer_is_truthfully_bounded(self):
        self.answer = "á" * 16000
        _, answer = await self.run_session()
        self.assertTrue(answer["truncated"])
        self.assertLessEqual(len(answer["text"].encode("utf-8")), runtime.MAX_TEXT_BYTES)
        self.assertLessEqual(len(json.dumps(answer["text"], ensure_ascii=True)), runtime.MAX_TEXT_BYTES)

    async def test_control_character_answer_fits_native_json_budget(self):
        self.answer = "\x01" * 16000
        _, answer = await self.run_session()
        self.assertTrue(answer["truncated"])
        self.assertLessEqual(len(json.dumps(answer, ensure_ascii=True)), 32768)

    async def test_supplementary_unicode_answer_fits_native_json_budget(self):
        self.answer = "🌎" * 16000
        _, answer = await self.run_session()
        self.assertTrue(answer["truncated"])
        self.assertLessEqual(len(json.dumps(answer, ensure_ascii=True)), 32768)

    async def test_html_heavy_answer_fits_default_dotnet_encoder(self):
        self.answer = "<>&'+`\"" * 16000
        _, answer = await self.run_session()
        self.assertTrue(answer["truncated"])
        self.assertLessEqual(runtime._wire_size(answer), 32768)
        self.assertLessEqual(runtime._wire_size(answer["text"]), runtime.MAX_TEXT_BYTES)

    async def test_permission_resolves_only_current_owned_request(self):
        self.behavior = "permission"
        session = runtime.RuntimeSession(self.user, None)

        async def respond(frame):
            self.frames.append(frame)
            if frame["type"] == "permission":
                self.assertFalse(await session.respond_permission("b" * 32, "proceed"))
                self.assertFalse(await session.respond_permission(frame["request_id"], "allow"))
                self.assertTrue(await session.respond_permission(frame["request_id"], "proceed"))
                self.assertFalse(await session.respond_permission(frame["request_id"], "proceed"))

        session.on_progress = respond
        await session.run("Create a fixture file")
        self.assertEqual(self.broker.decisions, [(self.permission_id, "proceed")])
        self.assertFalse(await session.respond_permission(self.permission_id, "deny"))

    async def test_oversize_permission_details_are_denied(self):
        self.behavior = "large-permission"
        await self.run_session()
        self.assertEqual(self.broker.decisions, [(self.permission_id, "deny")])
        frame = next(frame for frame in self.frames if frame["type"] == "permission")
        self.assertTrue(frame["truncated"])
        self.assertEqual(frame["decision"], "deny")

    async def test_lost_permission_channel_closes_broker(self):
        self.behavior = "lost-channel"

        async def broken(frame):
            if frame["type"] == "permission":
                raise OSError("Disconnected")

        with self.assertRaisesRegex(runtime.RuntimeFault, "progress_unavailable"):
            await self.run_session(callback=broken)
        self.assertTrue(self.broker.closed)
        self.assertEqual(self.state.get_state("llm_cancelled_epoch::75001"), 1)
        self.assertFalse(self.state.get_state("cancel_generation"))

    async def test_cancel_event_cancels_the_owned_run(self):
        self.behavior = "cancel"
        self.cancel_event = asyncio.Event()
        session = runtime.RuntimeSession(self.user, self.collect)
        result = await session.run("Wait for cancellation", self.cancel_event)
        self.assertTrue(result["cancelled"])
        self.assertTrue(self.broker.closed)
        self.assertFalse(guard.chat_busy(self.user.pk))

    async def test_cancelled_run_suppresses_trailing_progress_without_channel_failure(self):
        self.behavior = "cancel"
        self.cancel_event = asyncio.Event()
        async def collect_before_cancel(frame):
            if self.cancel_event.is_set():
                raise OSError("The cancelled operation no longer accepts progress")
            self.frames.append(frame)
        session = runtime.RuntimeSession(self.user, collect_before_cancel)
        result = await session.run("Cancel this run", self.cancel_event)
        self.assertTrue(result["cancelled"])
        self.assertEqual(session.status, "cancelled")
        self.assertIsNone(session.error)
        self.assertEqual([frame["type"] for frame in self.frames], ["status"])
        self.assertTrue(self.broker.closed)

    async def test_worker_progress_latches_cancellation_before_event_watcher_resumes(self):
        from .remote_controller_bridge import AccountWorker
        self.behavior = "cancel-race"
        self.cancel_event = asyncio.Event()
        worker = AccountWorker(types.SimpleNamespace(user=self.user, adapter=uuid.UUID(hex="c" * 32)))
        worker.active = {"id": "d" * 32}
        worker.call = AsyncMock(return_value={})
        worker.cancel = self.cancel_event
        session = worker.session = runtime.RuntimeSession(self.user, worker.progress)
        result = await session.run("Cancel before watcher scheduling", self.cancel_event)
        self.assertEqual(result, {"text": "", "cancelled": True, "truncated": False})
        self.assertIsNone(session.error)
        self.assertEqual(worker.call.await_count, 1)
        self.assertEqual(worker.call.await_args.kwargs["progress"], {"type": "status", "status": "ready"})
        self.assertTrue(self.broker.closed)
        self.assertFalse(guard.chat_busy(self.user.pk))

    async def test_cancel_before_preparation_does_not_require_a_progress_channel(self):
        async def broken(_frame):
            raise OSError("No progress channel remains")
        session = runtime.RuntimeSession(self.user, broken)
        session.request_cancel()
        result = await session.run("Do not dispatch")
        self.assertTrue(result["cancelled"])
        self.assertIsNone(session.error)
        self.assertIsNone(self.last_frame)

    async def test_inflight_progress_failure_remains_failure_when_cancellation_arrives(self):
        session = runtime.RuntimeSession(self.user, None)
        async def broken(frame):
            if frame["type"] == "message":
                session.request_cancel()
                raise OSError("The already-started progress request failed")
        session.on_progress = broken
        with self.assertRaisesRegex(runtime.RuntimeFault, "progress_unavailable"):
            await session.run("Channel failure racing cancellation")
        self.assertEqual(session.status, "failed")
        self.assertTrue(self.broker.closed)

    async def test_cancel_before_run_never_submits(self):
        session = runtime.RuntimeSession(self.user, self.collect)
        session.request_cancel()
        result = await session.run("Do not dispatch")
        self.assertTrue(result["cancelled"])
        self.assertIsNone(self.last_frame)

    async def test_failed_ready_channel_does_not_claim_success(self):
        async def broken(frame):
            raise OSError("Disconnected")
        with self.assertRaisesRegex(runtime.RuntimeFault, "progress_unavailable"):
            await self.run_session(callback=broken)
        self.assertIsNone(self.last_frame)

    async def test_external_cancel_waits_for_owned_preparation_to_exit(self):
        self.behavior = "preparation-wait"
        session = runtime.RuntimeSession(self.user, self.collect)
        task = asyncio.create_task(session.run("Prepare only"))
        await self.prepare_started.wait()
        task.cancel()
        await asyncio.sleep(0)
        self.assertFalse(task.done())
        self.assertTrue(guard.chat_busy(self.user.pk))
        self.prepare_release.set()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertFalse(guard.chat_busy(self.user.pk))
        self.assertIsNone(self.last_frame)

    async def test_stale_epoch_cannot_cancel_a_newer_run(self):
        session = runtime.RuntimeSession(self.user, self.collect)
        consumer = types.SimpleNamespace(_active_broker=self.broker, _active_run=(self.user.pk, 1))
        session._consumer = consumer
        guard.claim_chat(self.user.pk, consumer)
        self.state.set_state("llm_run_epoch::75001", 2)
        try:
            session.request_cancel()
            self.assertIsNone(self.state.get_state("llm_cancelled_epoch::75001"))
            self.assertTrue(self.broker.closed)
        finally:
            guard.release_chat(self.user.pk, consumer)


if __name__ == "__main__":
    unittest.main()
