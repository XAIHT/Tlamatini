"""Tests for the REAL context gauge (Angela, 2026-09-28).

*"make that gauge counter to be real, NOT FAKE ... this is going to be metered
by NVIDIA/INTEL/CISCO systems in real executions, SO BETTER YOU DONT LIE!"*

What is proven here, without a model server:

* Ollama's own ``prompt_eval_count`` is read out of every result shape
  LangChain hands back, and a missing count is NEVER invented.
* A real count lands on the EXACT request that produced it (``seq``) - early,
  late, or for a request that is no longer on screen - and never overwrites a
  newer frame.
* Only Tlamatini's MAIN inference reaches the ring: a side call is logged and
  never shown; the question rewriter / history summarizer are not metered.
* The denominator comes from Ollama's own ``/api/show`` (a real HTTP server
  stands in for Ollama), with the cloud / local ``num_ctx`` rules.
* The context block is found by the chain's OWN markers, and the refactored
  preambles are byte-identical to the literals they replaced.
* A self-healer retry that sent a DIFFERENT request is not paired with the
  frame it does not describe.
* The at-rest gauge rebuilds the next request with the main chain's own code,
  probes Ollama once, reuses the count for a byte-identical request, and
  stands aside while a request is in flight.
* Everything is kept per connected user.
"""

from __future__ import annotations

import http.server
import json
import threading
import time
import uuid
from types import SimpleNamespace
from unittest import mock

from django.test import SimpleTestCase

from agent import context_baseline as cb
from agent import context_governor as cg


class _Msg:
    def __init__(self, content, type_="human"):
        self.content = content
        self.type = type_
        self.tool_calls = []


def _user():
    return "real-test-" + uuid.uuid4().hex[:8]


class _Sink:
    """Collects every frame the governor publishes for one user."""

    def __init__(self, user_id):
        self.user_id = user_id
        self.frames = []
        cg.register_gauge_sink(user_id, self.frames.append)

    def close(self):
        cg.unregister_gauge_sink(self.user_id)

    def last(self):
        return self.frames[-1] if self.frames else None


def _wait(predicate, timeout=5.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return False


class UsageExtractionTests(SimpleTestCase):
    def test_reads_prompt_eval_count_from_an_llm_result(self):
        gen = SimpleNamespace(generation_info={"prompt_eval_count": 90206, "eval_count": 3,
                                               "model": "glm-5.3:cloud"}, message=None)
        usage = cg.usage_from_llm_result(SimpleNamespace(generations=[[gen]]))
        self.assertEqual(usage["prompt_tokens"], 90206)
        self.assertEqual(usage["completion_tokens"], 3)
        self.assertEqual(usage["model"], "glm-5.3:cloud")
        self.assertEqual(usage["field"], "prompt_eval_count")

    def test_reads_it_from_a_chat_models_ai_message(self):
        msg = SimpleNamespace(response_metadata={"prompt_eval_count": 1234, "eval_count": 7},
                              usage_metadata=None)
        self.assertEqual(cg.usage_from_llm_result(msg)["prompt_tokens"], 1234)

    def test_falls_back_to_usage_metadata(self):
        msg = SimpleNamespace(response_metadata={}, usage_metadata={"input_tokens": 55,
                                                                    "output_tokens": 2})
        usage = cg.usage_from_llm_result(msg)
        self.assertEqual(usage["prompt_tokens"], 55)
        self.assertEqual(usage["field"], "usage_metadata.input_tokens")

    def test_a_missing_count_is_never_invented(self):
        for obj in (None, "text", 5, SimpleNamespace(), {"eval_count": 3},
                    SimpleNamespace(response_metadata={"prompt_eval_count": None})):
            self.assertIsNone(cg.usage_from_llm_result(obj))


class PairingTests(SimpleTestCase):
    def setUp(self):
        self.user = _user()
        self.sink = _Sink(self.user)
        self.meter = cg.ContextMeter(min_interval=0.0)

    def tearDown(self):
        self.sink.close()

    def _measure(self, seq, text="payload " * 400):
        self.assertTrue(cg.measure_async(self.user, [_Msg(text)], label="step", seq=seq,
                                         meter=self.meter))
        self.assertTrue(self.meter.drain(timeout=5))
        self.assertTrue(_wait(lambda: any(f.get("seq") == seq for f in self.sink.frames)))

    def test_the_real_count_replaces_the_estimate_on_its_own_request(self):
        seq = cg.next_seq()
        self._measure(seq)
        est = self.sink.last()
        self.assertFalse(est["ratio_is_real"])
        self.assertIsNone(est["tokens_real"])

        self.assertTrue(cg.report_real_usage(self.user, seq, 777, 3, model="m"))
        real = self.sink.last()
        self.assertEqual(real["seq"], seq)
        self.assertTrue(real["ratio_is_real"])
        self.assertEqual(real["tokens_real"], 777)
        self.assertEqual(real["completion_tokens_real"], 3)
        self.assertAlmostEqual(real["ratio"], 777 / real["ceiling_tokens"], places=6)
        # The estimate is kept beside it, with the error, so anyone can check it.
        self.assertEqual(real["tokens_estimated"], est["tokens_estimated"])
        expected = round((est["tokens_estimated"] - 777) * 100.0 / 777, 2)
        self.assertEqual(real["estimate_error_pct"], expected)

    def test_a_count_that_arrives_before_its_measurement_is_merged_later(self):
        seq = cg.next_seq()
        self.assertTrue(cg.report_real_usage(self.user, seq, 4321, 1))
        self._measure(seq)
        self.assertTrue(self.sink.last()["ratio_is_real"])
        self.assertEqual(self.sink.last()["tokens_real"], 4321)

    def test_an_older_count_never_overwrites_a_newer_frame(self):
        old, new = cg.next_seq(), cg.next_seq()
        self._measure(new)
        self.assertTrue(cg.report_real_usage(self.user, old, 999, 1))
        last = self.sink.last()
        self.assertEqual(last["seq"], new)
        self.assertFalse(last["ratio_is_real"])          # still honestly an estimate
        self.assertEqual(last["last_real"]["tokens"], 999)

    def test_an_older_frame_never_replaces_a_newer_one(self):
        old, new = cg.next_seq(), cg.next_seq()
        self._measure(new)
        before = len(self.sink.frames)
        self.assertFalse(cg._remember_and_publish(self.user, {"seq": old, "ok": True}))
        self.assertEqual(len(self.sink.frames), before)

    def test_side_calls_are_logged_but_never_reach_the_ring(self):
        seq = cg.next_seq()
        self.assertTrue(cg.measure_async(self.user, "a prompt for another CLI",
                                         label="acpx claude", source="acpx",
                                         kind=cg.KIND_SIDE, seq=seq, meter=self.meter))
        self.assertTrue(self.meter.drain(timeout=5))
        time.sleep(0.2)
        self.assertEqual(self.sink.frames, [])
        self.assertIsNone(cg.latest_frame(self.user))

    def test_users_never_see_each_others_numbers(self):
        other = _user()
        other_sink = _Sink(other)
        try:
            seq = cg.next_seq()
            self._measure(seq)
            cg.report_real_usage(self.user, seq, 1111, 1)
            self.assertEqual(other_sink.frames, [])
            self.assertIsNone(cg.latest_frame(other))
        finally:
            other_sink.close()

    def test_bad_input_is_refused_not_raised(self):
        for args in ((self.user, 0, 5), (self.user, 5, None), (None, 5, 5),
                     (self.user, "x", 5), (self.user, 5, -1)):
            self.assertFalse(cg.report_real_usage(*args))


class TurnTotalsTests(SimpleTestCase):
    def test_an_answers_main_calls_are_totalled_in_ollamas_numbers(self):
        user = _user()
        cg.begin_turn(user, label="hello")
        self.assertTrue(cg.record_call_usage(100, 5, user_id=user, model="a"))
        self.assertTrue(cg.record_call_usage(300, 7, user_id=user, model="a"))
        totals = cg.turn_totals(user)
        self.assertTrue(totals["open"])
        self.assertEqual((totals["calls"], totals["prompt_tokens"],
                          totals["completion_tokens"], totals["largest_prompt"]),
                         (2, 400, 12, 300))
        self.assertEqual(totals["models"]["a"]["calls"], 2)
        done = cg.end_turn(user)
        self.assertFalse(done["open"])

    def test_a_call_with_no_user_is_not_attributed_to_anyone(self):
        self.assertIsNone(cg.current_user())
        self.assertFalse(cg.record_call_usage(10, 1))


class _ShowHandler(http.server.BaseHTTPRequestHandler):
    calls = 0
    context_length = 1048576

    def do_POST(self):  # noqa: N802 - http.server API
        type(self).calls += 1
        length = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(length) or b"{}")
        payload = {"model_info": {"arch.context_length": self.context_length},
                   "details": {"family": "arch"}, "remote_host": None,
                   "echo_model": body.get("model")}
        data = json.dumps(payload).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *args):  # silence
        pass


class CeilingTests(SimpleTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.server = http.server.HTTPServer(("127.0.0.1", 0), _ShowHandler)
        cls.base = "http://127.0.0.1:%d" % cls.server.server_address[1]
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        super().tearDownClass()

    def setUp(self):
        with cg._SHOW_LOCK:
            cg._SHOW_CACHE.clear()
        _ShowHandler.calls = 0

    def test_the_denominator_comes_from_ollamas_own_api_show(self):
        ceiling, source = cg.resolve_ceiling_tokens(
            {"ollama_base_url": self.base, "ollama_num_ctx": 8192}, model="glm-5.3:cloud")
        # Cloud: num_ctx is a proven no-op, so the model's own length wins.
        self.assertEqual((ceiling, source), (1048576, "ollama /api/show"))

    def test_a_local_model_is_bounded_by_the_num_ctx_it_was_loaded_with(self):
        ceiling, source = cg.resolve_ceiling_tokens(
            {"ollama_base_url": self.base, "ollama_num_ctx": 8192}, model="llama3:8b")
        self.assertEqual(ceiling, 8192)
        self.assertIn("< /api/show 1048576", source)

    def test_it_is_asked_once_then_cached(self):
        for _ in range(3):
            cg.ollama_context_length("m:cloud", self.base)
        self.assertEqual(_ShowHandler.calls, 1)

    def test_an_explicit_ceiling_still_wins_and_no_model_means_no_network(self):
        self.assertEqual(cg.resolve_ceiling_tokens({"context_ceiling_tokens": 32000},
                                                   model="x"), (32000, "config"))
        self.assertEqual(cg.resolve_ceiling_tokens({"ollama_num_ctx": 8192}),
                         (8192, "ollama_num_ctx"))
        self.assertEqual(_ShowHandler.calls, 0)

    def test_a_dead_server_falls_back_and_says_so(self):
        ceiling, source = cg.resolve_ceiling_tokens(
            {"ollama_base_url": "http://127.0.0.1:9", "ollama_num_ctx": 1048576},
            model="glm-5.3:cloud")
        self.assertEqual(ceiling, 1048576)
        self.assertIn("unverified", source)

    def test_cloud_tags_are_recognised(self):
        for name in ("glm-5.3:cloud", "qwen3.5:397b-cloud", "gpt-oss:120b-cloud"):
            self.assertTrue(cg.is_cloud_model(name), name)
        for name in ("llama3:8b", "Nomic-Embed-Text:latest", ""):
            self.assertFalse(cg.is_cloud_model(name), name)


class ContextMarkerTests(SimpleTestCase):
    def test_the_fallback_context_block_is_measured_exactly(self):
        from agent.rag.chains.unified import wrap_loaded_context
        body = "def main():\n    return 'á'\n"
        text = wrap_loaded_context(body, "what does it do?")
        self.assertEqual(cg._context_span(text), (len(body), len(body.encode("utf-8"))))

    def test_the_retrieved_context_block_is_measured_exactly(self):
        from agent.rag.chains.unified import wrap_retrieved_context
        body = "FILE MANIFEST\n- a.py\n\nchunk text"
        self.assertEqual(cg._context_span(wrap_retrieved_context(body, "q"))[0], len(body))

    def test_the_one_shot_prompt_context_block_is_measured(self):
        text = "rules...\n<context>\nPROJECT\n</context>\nmore rules"
        self.assertEqual(cg._context_span(text)[0], len("PROJECT"))

    def test_no_block_means_zero_not_a_guess(self):
        self.assertEqual(cg._context_span("just a question"), (0, 0))

    def test_the_refactored_preambles_are_byte_identical_to_the_old_literals(self):
        """The model reads this text - moving it into helpers must change nothing."""
        from agent.rag.chains.unified import wrap_loaded_context, wrap_retrieved_context
        loaded, question = "CTX", "Q?"
        old_loaded = (
            "Loaded Context from Knowledge Base Fallback:\n"
            f"{loaded}\n\n"
            "IMPORTANT: The loaded context above is the USER'S OWN project/files (NOT Tlamatini's own "
            "source code or self-knowledge), already provided even though vector retrieval is unavailable. "
            "Use it directly to answer the user's question; for any request to summarize, explain, or analyze "
            "\"the project\", \"the source code\", or \"the provided context\", answer from THIS content — never "
            "with a description of Tlamatini herself.\n\n"
            f"User Question: {question}"
        )
        self.assertEqual(wrap_loaded_context(loaded, question), old_loaded)
        old_retrieved = f"Retrieved Context from Knowledge Base:\n{loaded}\n\nUser Question: {question}"
        self.assertEqual(wrap_retrieved_context(loaded, question), old_retrieved)

    def test_a_measured_request_reports_its_context_bytes(self):
        from agent.rag.chains.unified import wrap_loaded_context
        body = "x" * 5000
        m = cg.measure([_Msg("system", "system"), _Msg(wrap_loaded_context(body, ""))],
                       prefix_message_count=1, loop_start_index=2)
        self.assertEqual(m.context_bytes, 5000)
        payload = cg.gauge_payload(m)
        self.assertEqual(payload["bytes_context"], 5000)
        self.assertFalse(payload["ratio_is_real"])


class HistorySummaryDecisionTests(SimpleTestCase):
    def test_short_history_is_sent_as_is(self):
        from agent.rag.chains.unified import history_summary_tail
        hist = [_Msg("hi"), _Msg("hello", "ai")]
        self.assertIsNone(history_summary_tail({"enable": True, "trigger_tokens": 800}, hist))
        self.assertIsNone(history_summary_tail({"enable": False}, hist))

    def test_long_history_keeps_its_tail_verbatim(self):
        from agent.rag.chains.unified import history_summary_tail, summarized_history
        hist = [_Msg("word " * 400) for _ in range(8)]
        tail = history_summary_tail({"enable": True, "trigger_tokens": 800,
                                     "keep_last_turns": 6}, hist)
        self.assertEqual(tail, hist[-6:])
        sent = summarized_history("S", tail)
        self.assertEqual(sent[0].content, "CHAT HISTORY SUMMARY:\nS")
        self.assertEqual(sent[1:], hist[-6:])


class SelfHealerPairingTests(SimpleTestCase):
    """A trimmed / tool-less retry sent a DIFFERENT request: its count must not
    be pinned on the frame of the request that was measured."""

    def _fake_executor(self, user, tactic):
        from agent.self_healing import SelfHealingInvoker
        healer = SimpleNamespace(last_tactic=tactic,
                                 UNCHANGED_REQUEST_TACTICS=SelfHealingInvoker.UNCHANGED_REQUEST_TACTICS)
        return SimpleNamespace(_ask_execs_user_id=user, _healer=healer, _context_config={})

    def test_an_unchanged_request_is_paired(self):
        from agent.mcp_agent import MultiTurnToolAgentExecutor
        user = _user()
        seq = cg.next_seq()
        cg.begin_turn(user)
        response = SimpleNamespace(response_metadata={"prompt_eval_count": 500, "eval_count": 9})
        # Patched where mcp_agent looks it up (it imported the name at load).
        with mock.patch("agent.mcp_agent._context_report_real",
                        wraps=cg.report_real_usage) as spy:
            MultiTurnToolAgentExecutor._report_real_step_usage(
                self._fake_executor(user, "retry"), response, seq, "m", "working on step 1")
        spy.assert_called_once()
        self.assertEqual(spy.call_args.args[1], seq)
        self.assertEqual(cg.turn_totals(user)["prompt_tokens"], 500)

    def test_a_trimmed_request_is_logged_and_totalled_but_not_paired(self):
        from agent.mcp_agent import MultiTurnToolAgentExecutor
        user = _user()
        cg.begin_turn(user)
        response = SimpleNamespace(response_metadata={"prompt_eval_count": 200, "eval_count": 4})
        with mock.patch("agent.mcp_agent._context_report_real") as report:
            MultiTurnToolAgentExecutor._report_real_step_usage(
                self._fake_executor(user, "trim-context"), response, cg.next_seq(), "m", "step")
        report.assert_not_called()
        self.assertEqual(cg.turn_totals(user)["calls"], 1)

    def test_the_ring_names_the_mode_the_request_is_really_in(self):
        # ONE executor serves Multi-Turn and one-shot; the ring used to say
        # "multi-turn" on every one-shot answer (seen live 2026-09-28).
        from agent.global_state import scoped_request_state
        from agent.mcp_agent import MultiTurnToolAgentExecutor
        response = SimpleNamespace(response_metadata={})
        fake = SimpleNamespace(
            _context_governor_settings=cg.GovernorSettings(),
            _tool_schema_prefix_bytes=lambda: (0, 0),
            _llm_identity=lambda llm: ("m", ""),
            _ask_execs_user_id=_user(),
            _healer=SimpleNamespace(invoke=lambda llm, messages, label="": response),
            _report_real_step_usage=lambda *a, **k: None,
        )
        seen = []
        with mock.patch("agent.mcp_agent._context_measure_async",
                        side_effect=lambda *a, **k: seen.append(k["source"])):
            for multi_turn in (True, False):
                with scoped_request_state(multi_turn_enabled=multi_turn):
                    self.assertIs(MultiTurnToolAgentExecutor._model_step(fake, None, [_Msg("q")], "s"),
                                  response)
        self.assertEqual(seen, ["multi-turn", "one-shot"])

    def test_the_healer_names_the_tactics_that_resend_the_same_request(self):
        from agent.self_healing import SelfHealingInvoker
        self.assertEqual(SelfHealingInvoker.UNCHANGED_REQUEST_TACTICS,
                         frozenset({"normal", "retry", "patient-retry"}))


class MainChainOnlyTests(SimpleTestCase):
    def test_a_side_callback_measures_nothing(self):
        from agent.rag.chains.base import Callbacks
        with mock.patch("agent.rag.chains.base._context_measure_async") as measure:
            Callbacks().on_chat_model_start({}, [[_Msg("rewrite this")]], run_id=uuid.uuid4())
        measure.assert_not_called()

    def test_the_main_answer_is_measured_and_paired_by_run_id(self):
        from agent.rag.chains.base import Callbacks
        user = _user()
        token = cg.bind_user(user)
        try:
            cg.begin_turn(user)
            run_id = uuid.uuid4()
            cb_main = Callbacks(main=True)
            with mock.patch("agent.rag.chains.base._ollama_config", return_value={}):
                cb_main.on_chat_model_start({}, [[_Msg("answer me")]], run_id=run_id,
                                            invocation_params={"model": "m:cloud"})
            gen = SimpleNamespace(generation_info={"prompt_eval_count": 42, "eval_count": 1},
                                  message=None)
            cb_main.on_llm_end(SimpleNamespace(generations=[[gen]]), run_id=run_id)
            self.assertEqual(cg._LAST_REAL[user]["tokens"], 42)
            self.assertEqual(cg.turn_totals(user)["prompt_tokens"], 42)
        finally:
            cg.unbind_user(token)


# ── The gauge AT REST ─────────────────────────────────────────────────────────
class _FakeClient:
    def __init__(self):
        self.calls = []

    def chat(self, **body):
        self.calls.append(body)
        return {"prompt_eval_count": 90206, "eval_count": 1}


class _FakeChat:
    model = "glm-5.3:cloud"
    base_url = "http://127.0.0.1:9"

    def __init__(self):
        self._client = _FakeClient()

    def _chat_params(self, messages, tools=None, **_kw):
        body = {"model": self.model, "stream": True, "options": {"num_ctx": 1048576},
                "messages": [{"role": getattr(m, "type", "user"), "content": m.content}
                             for m in messages]}
        if tools:
            body["tools"] = tools
        return body


class _FakeExecutor:
    def __init__(self):
        chat = _FakeChat()
        self.bound_llm = SimpleNamespace(bound=chat, kwargs={"tools": [{"name": "t"}]})
        self.llm = chat
        self.system_prompt = "SYSTEM " * 50

    def build_request_messages(self, input_text, chat_history, planner_summary=""):
        msgs = [_Msg(self.system_prompt, "system")] + list(chat_history) + [_Msg(input_text)]
        return msgs, 1

    def _tool_schema_prefix_bytes(self):
        return (120, 110)

    @staticmethod
    def _llm_identity(llm):
        target = getattr(llm, "bound", None) or llm
        return target.model, target.base_url


class _FakeAgent:
    def __init__(self):
        self.tools = [SimpleNamespace(name="chat_agent_executer")]
        self.preeliminary_prompt = "prompt"
        self.executor = _FakeExecutor()

    def _refresh_external_mcp_tool_surface(self):
        pass

    def _get_executor_for_tools(self, tools, step_by_step_enabled=False):
        return self.executor


class AtRestTests(SimpleTestCase):
    def setUp(self):
        self.user = _user()
        self.sink = _Sink(self.user)
        self.chain = SimpleNamespace(unified_agent=_FakeAgent(), history_summary_cfg=None,
                                     loaded_context="PROJECT SOURCE " * 100)
        self.cfg = {"context_gauge_probe_enable": True, "context_ceiling_from_ollama": False}

    def tearDown(self):
        self.sink.close()
        cb.forget_user(self.user)

    def _refresh(self, reason="history cleared"):
        with mock.patch.object(cb, "_load_config", return_value=self.cfg):
            out = cb.refresh(self.user, self.chain, [_Msg("q1"), _Msg("a1", "ai")],
                             cb.RefreshFlags(), reason)
        cg.METER.drain(timeout=5)
        return out

    def test_the_next_request_is_rebuilt_measured_and_made_real(self):
        out = self._refresh()
        self.assertTrue(out["probed"])
        self.assertEqual(out["prompt_tokens"], 90206)
        self.assertTrue(_wait(lambda: (self.sink.last() or {}).get("ratio_is_real")))
        frame = self.sink.last()
        self.assertEqual(frame["kind"], "rest")
        self.assertEqual(frame["tokens_real"], 90206)
        self.assertGreater(frame["bytes_context"], 1000)          # the loaded project
        self.assertIn("not included yet", frame["note"])
        body = self.chain.unified_agent.executor.llm._client.calls[0]
        self.assertEqual(body["options"]["num_predict"], 1)     # one output token
        self.assertFalse(body["stream"])
        self.assertEqual(body["tools"], [{"name": "t"}])        # the real tool JSON

    def test_a_byte_identical_request_is_not_paid_for_twice(self):
        self._refresh("history cleared")
        second = self._refresh("toolbar changed")
        self.assertTrue(second["cached"])
        self.assertEqual(len(self.chain.unified_agent.executor.llm._client.calls), 1)

    def test_a_request_in_flight_owns_the_ring(self):
        cg.begin_turn(self.user)
        try:
            self.assertIsNone(self._refresh())
            self.assertEqual(self.chain.unified_agent.executor.llm._client.calls, [])
        finally:
            cg.end_turn(self.user)

    def test_the_probe_can_be_switched_off(self):
        self.cfg["context_gauge_probe_enable"] = False
        out = self._refresh()
        self.assertFalse(out["probed"])
        self.assertEqual(self.chain.unified_agent.executor.llm._client.calls, [])

    def test_a_chain_that_is_not_the_unified_agent_is_not_guessed_at(self):
        with mock.patch.object(cb, "_load_config", return_value=self.cfg):
            self.assertIsNone(cb.refresh(self.user, SimpleNamespace(), [], cb.RefreshFlags(), "x"))

    def _next_input(self, *, multi_turn, loaded=""):
        seen = {}
        executor = self.chain.unified_agent.executor
        original = executor.build_request_messages

        def spy(input_text, chat_history, planner_summary=""):
            seen["input"] = input_text
            return original(input_text, chat_history, planner_summary)

        self.chain.loaded_context = loaded
        with mock.patch.object(executor, "build_request_messages", side_effect=spy):
            self.assertIsNotNone(cb._next_request(self.chain, [], cb.RefreshFlags(multi_turn=multi_turn)))
        return seen["input"]

    def test_at_rest_the_empty_question_is_wrapped_as_the_chain_wraps_it(self):
        # No system placeholder any more (Angela, 2026-09-28), so one-shot and
        # Multi-Turn wrap an empty question the same way - only the loaded
        # context, with the chain's own wrapper.
        from agent.rag.chains.unified import wrap_loaded_context
        for multi_turn in (True, False):
            with self.subTest(multi_turn=multi_turn):
                self.assertEqual(self._next_input(multi_turn=multi_turn), "")
                self.assertEqual(self._next_input(multi_turn=multi_turn, loaded="SRC"),
                                 wrap_loaded_context("SRC", ""))


# ── The request itself: no preamble drift, the question never sent twice ────
class OneQuestionOnceTests(SimpleTestCase):
    """The live lab found the one-shot request carrying the question TWICE."""

    def _messages(self, history, input_text):
        from agent.mcp_agent import MultiTurnToolAgentExecutor
        executor = MultiTurnToolAgentExecutor.__new__(MultiTurnToolAgentExecutor)
        executor.system_prompt = "SYSTEM"
        messages, prefix = executor.build_request_messages(input_text, history)
        self.assertEqual(prefix, 1)
        return [m.content for m in messages[1:]]

    def test_the_system_preamble_is_byte_identical_to_the_old_literal(self):
        from agent.rag.chains.unified import with_system_context
        for sc, text in (("cpu 3%", "Q?"), ("mem 41%", ""), ("x", "a\nb")):
            self.assertEqual(with_system_context(sc, text), f"System Context: {sc}\n\n{text}")

    def test_the_sidecar_sends_nothing_when_no_metrics_are_needed(self):
        # Angela, 2026-09-28: "stop sending that placeholder line". It was
        # "System Context: No system context required for this question." on
        # EVERY one-shot question while System-Metrics was on.
        import asyncio
        from agent.chain_system_lcel import SystemRAGChain

        async def decide_no(_question):
            return False

        async def decide_yes(_question):
            return True

        async def live_metrics():
            return "cpu 3%"

        fake = SimpleNamespace(should_fetch_system_context=decide_no,
                               fetch_system_context=live_metrics)
        out = asyncio.run(SystemRAGChain.intelligent_context_fetch(fake, {"question": "2+2?"}))
        self.assertEqual(out["context"], "")
        fake.should_fetch_system_context = decide_yes
        out = asyncio.run(SystemRAGChain.intelligent_context_fetch(fake, {"question": "cpu?"}))
        self.assertEqual(out["context"], "cpu 3%")

    def test_both_chains_skip_an_empty_system_context(self):
        # So "" really means NOTHING is sent: no "System Context: " prefix.
        import inspect
        from agent.rag.chains import unified
        src = inspect.getsource(unified)
        self.assertIn('if payload.get("system_context"):\n'
                      "            enhanced_input = with_system_context(", src.replace("\r\n", "\n"))
        self.assertIn("if sys_ctx:\n            enhanced_input = with_system_context(sys_ctx",
                      src.replace("\r\n", "\n"))

    def test_a_bare_question_is_not_sent_twice(self):
        from langchain_core.messages import AIMessage, HumanMessage
        history = [HumanMessage(content="hi"), AIMessage(content="hello"), HumanMessage(content="Q?")]
        self.assertEqual(self._messages(history, "Q?"), ["hi", "hello", "Q?"])

    def test_a_wrapped_question_is_not_sent_twice(self):
        from langchain_core.messages import AIMessage, HumanMessage
        from agent.rag.chains.unified import (with_system_context, wrap_loaded_context,
                                              wrap_retrieved_context)
        history = [HumanMessage(content="hi"), AIMessage(content="hello"),
                   HumanMessage(content="What is 2 plus 2?")]
        q = "What is 2 plus 2?"
        for wrapped in (with_system_context("cpu 3%", q),
                        wrap_loaded_context("SRC", q),
                        wrap_retrieved_context("DOCS", q),
                        wrap_loaded_context("SRC", with_system_context("cpu", q)),
                        "Files Context (file system search results):\nf.py\n\nUser Question: " + q,
                        "Web Context: w\n\n" + q):
            with self.subTest(wrapped=wrapped[:40]):
                self.assertEqual(self._messages(history, wrapped), ["hi", "hello", wrapped])

    def test_the_planners_plan_is_measured_on_its_own(self):
        # So the lab can account for EVERY byte between the at-rest prediction
        # (no plan yet) and the live Multi-Turn request (plan included).
        system, plan, question = _Msg("S" * 100, "system"), _Msg("P" * 50, "system"), _Msg("Q?")
        with_plan = cg.measure([system, plan, question], prefix_message_count=2,
                               config={"context_ceiling_from_ollama": False})
        without = cg.measure([system, question], prefix_message_count=1,
                             config={"context_ceiling_from_ollama": False})
        self.assertGreater(with_plan.plan_bytes, 50)
        self.assertEqual(without.plan_bytes, 0)
        self.assertEqual(with_plan.prefix_bytes - without.prefix_bytes, with_plan.plan_bytes)
        self.assertEqual(with_plan.history_bytes, without.history_bytes)
        self.assertEqual(cg.gauge_payload(with_plan)["bytes_plan"], with_plan.plan_bytes)

    def test_a_different_earlier_message_is_never_dropped(self):
        from langchain_core.messages import AIMessage, HumanMessage
        # "say ok" merely ENDS WITH "ok": that is not the same question.
        history = [HumanMessage(content="ok")]
        self.assertEqual(self._messages(history, "say ok"), ["ok", "say ok"])
        # An assistant message is only dropped on an exact match, as before.
        history = [AIMessage(content="Q?")]
        wrapped = "System Context: s\n\nQ?"
        self.assertEqual(self._messages(history, wrapped), ["Q?", wrapped])
