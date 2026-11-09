# Tlamatini Author Banner — Created by Angela López Mendoza · @angelahack1
"""A rebuilding model chain must not block the closed interactive account wizard."""

import asyncio
from importlib import import_module
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from django.test import SimpleTestCase

from agent.consumers import AgentConsumer
from agent.exec_permission import get_broker
from agent.global_state import global_state


class UserCreationConsumerTests(SimpleTestCase):
    def setUp(self):
        self.consumer = AgentConsumer()
        self.user = SimpleNamespace(
            id=986701, pk=986701, username="wizard_consumer_test", is_authenticated=True,
        )
        self.consumer.scope = {"user": self.user}
        self.consumer.channel_layer = SimpleNamespace(group_send=AsyncMock())
        self.consumer.room_group_name = "wizard-consumer-test"
        self.consumer.rag_chain = None
        self.consumer._say = lambda text: text
        self.consumer.load_recent_chat_history = AsyncMock(return_value=[])
        self.consumer.save_message = AsyncMock(return_value=101)
        self.consumer.get_or_create_bot_user = AsyncMock(return_value=(object(), False))
        self.consumer.setup_rag_chain = AsyncMock()
        self.previous_ready = global_state.get_state("rag_chain_ready")
        global_state.set_state("rag_chain_ready", False)
        self.card = import_module(
            "agent.migrations.0223_create_superuser_console_handoff"
        ).WIZARD_PROMPT

    def tearDown(self):
        global_state.set_state("rag_chain_ready", self.previous_ready)

    def receive_message(self, text, *, multi_turn=True):
        queued = []

        def capture_task(coroutine):
            queued.append(coroutine)
            coroutine.close()
            return Mock()

        payload = json.dumps({
            "message": text, "multi_turn_enabled": multi_turn, "step_by_step_enabled": True,
        })
        with patch("agent.consumers.asyncio.create_task", side_effect=capture_task):
            asyncio.run(self.consumer.receive(payload))
        return queued

    def test_receive_accepts_shipped_card_while_model_chain_is_rebuilding(self):
        self.consumer.queue_llm_retrieval = AsyncMock()
        queued = self.receive_message(self.card)
        self.assertEqual(len(queued), 1)
        self.consumer.queue_llm_retrieval.assert_called_once()
        self.consumer.setup_rag_chain.assert_not_called()
        self.consumer.save_message.assert_awaited_once()
        self.assertFalse(global_state.get_state("rag_chain_ready"))

    def test_receive_still_rejects_unrelated_prompt_when_model_is_not_ready(self):
        self.consumer.queue_llm_retrieval = AsyncMock()
        self.receive_message("Explain the composition of the moon.")
        self.consumer.queue_llm_retrieval.assert_not_called()
        self.consumer.setup_rag_chain.assert_called_once()
        self.consumer.save_message.assert_not_called()

    def test_receive_does_not_bypass_authentication_for_the_card(self):
        self.consumer.scope["user"] = SimpleNamespace(
            id=None, pk=None, username="", is_authenticated=False,
        )
        self.consumer.queue_llm_retrieval = AsyncMock()
        self.receive_message(self.card)
        self.consumer.queue_llm_retrieval.assert_not_called()
        self.consumer.save_message.assert_not_called()

    def test_receive_does_not_start_wizard_without_multiturn(self):
        self.consumer.queue_llm_retrieval = AsyncMock()
        self.receive_message(self.card, multi_turn=False)
        self.consumer.queue_llm_retrieval.assert_not_called()

    def run_native_queue(self, *, ask_execs=False, handler=None):
        reply = {"output": "Waiting for private console input.\nEND-RESPONSE", "metadata": {
            "tool_calls_log": [], "exec_report_entries": [], "exec_report_denied": None,
        }}
        calls = []

        def dispatch(*args, **kwargs):
            calls.append(kwargs)
            self.assertEqual(get_broker(self.user.id) is not None, ask_execs)
            return handler(*args, **kwargs) if handler else reply

        with (
            patch("agent.user_creation_wizard.handle_request", side_effect=dispatch),
            patch("agent.consumers.process_llm_response", new_callable=AsyncMock) as process,
            patch("agent.consumers.ask_rag", side_effect=AssertionError("Model route must not run")) as model,
            patch("agent.interactor.context.bind", return_value=object()),
            patch("agent.interactor.context.current"),
        ):
            asyncio.run(self.consumer.queue_llm_retrieval(
                self.card, self.user, multi_turn_enabled=True, ask_execs_enabled=ask_execs,
            ))
            model.assert_not_called()
        return calls, process

    def test_queue_dispatches_and_broadcasts_without_a_model_chain(self):
        calls, process = self.run_native_queue()
        self.assertEqual(len(calls), 1)
        process.assert_awaited_once()
        self.assertIsNone(process.await_args.args[1])
        self.assertEqual(process.await_args.kwargs["conversation_user"], self.user)
        self.assertFalse(global_state.get_state("rag_chain_ready"))

    def test_native_queue_has_real_ask_execs_broker_and_removes_it_afterward(self):
        calls, process = self.run_native_queue(ask_execs=True)
        self.assertTrue(calls[0]["ask_execs_enabled"])
        process.assert_awaited_once()
        self.assertIsNone(get_broker(self.user.id))
        self.assertIsNone(self.consumer._active_broker)

    def test_nonmatching_native_candidate_does_not_fall_into_model_while_not_ready(self):
        calls, process = self.run_native_queue(handler=lambda *args, **kwargs: None)
        self.assertEqual(len(calls), 1)
        process.assert_not_awaited()
        self.assertFalse(global_state.get_state("rag_chain_ready"))

    def test_declined_native_candidate_does_not_use_old_chain_during_rebuild(self):
        self.consumer.rag_chain = object()
        calls, process = self.run_native_queue(handler=lambda *args, **kwargs: None)
        self.assertEqual(len(calls), 1)
        process.assert_not_awaited()
        self.assertFalse(global_state.get_state("rag_chain_ready"))

    def test_real_response_parser_persists_and_broadcasts_native_answer_without_chain(self):
        from agent.services.response_parser import process_llm_response

        reply = "<p>The private account console is open. Enter the password there.</p>\nEND-RESPONSE"
        with (
            patch("agent.services.response_parser.get_or_create_bot_user", new_callable=AsyncMock,
                  return_value=(object(), False)),
            patch("agent.services.response_parser.save_message", new_callable=AsyncMock,
                  return_value=102) as save,
            patch("agent.services.response_parser.save_program", new_callable=AsyncMock) as program,
            patch("agent.services.response_parser.save_snippet", new_callable=AsyncMock) as snippet,
        ):
            answer = asyncio.run(process_llm_response(
                reply, None, self.consumer.channel_layer, self.consumer.room_group_name,
                conversation_user=self.user, multi_turn_used=True,
            ))
        save.assert_awaited_once()
        program.assert_not_awaited()
        snippet.assert_not_awaited()
        self.assertNotIn("END-RESPONSE", answer)
        frame = self.consumer.channel_layer.group_send.await_args.args[1]
        self.assertEqual(frame["message"], answer)
        self.assertEqual(frame["message_id"], 102)
        self.assertEqual(frame["type"], "agent_message")
        self.assertTrue(frame["multi_turn_used"])
        self.assertFalse(global_state.get_state("rag_chain_ready"))
