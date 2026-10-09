# ═══════════════════════════════════════════════════════════════════════════
#   ✦  T L A M A T I N I  ✦   —   "one who knows"
#
#   Created by  Angela López Mendoza   ·   @angelahack1
#   Developer · Architect · Creator of Tlamatini
# ═══════════════════════════════════════════════════════════════════════════
#   Tlamatini Author Banner — do not remove (releases scrub the name automatically)
"""MODEL BRAIN - every decision is formal, per model, and fail-open (Angela, 2026-10-08).

Covers agent/model_brain.py (knowledge base, decisions, research), agent/model_brain_chat.py
(the reasoning of a thinking model kept and returned inside the tool loop - proved against
a REAL local HTTP server speaking Ollama's API), the wiring into mcp_agent.py and
rag/factory.py, and the Auto-tuning dialog's endpoints.
"""
from __future__ import annotations

import http.server
import json
import os
import re
import shutil
import tempfile
import threading
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase

from agent import model_brain
from agent.model_brain import ModelFacts

AGENT_DIR = os.path.dirname(os.path.abspath(model_brain.__file__))


def _facts(model, caps=("completion", "tools"), values=(), default=None, ctx=0, params=None, known=True):
    return ModelFacts(model=model, known=known, capabilities=list(caps), thinking_values=list(values),
                      thinking_default=default, context_length=ctx, parameters=dict(params or {}))


GLM_FACTS = _facts("glm-5.3:cloud", ("completion", "thinking", "tools"), ("low", "high", "max"), "max", 1048576)


class _NoLearned(SimpleTestCase):
    """Every test starts from the shipped knowledge base only."""

    def setUp(self):
        model_brain.reset_caches()
        patcher = mock.patch.object(model_brain, "learned_profiles", return_value=[])
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(model_brain.reset_caches)


# ── the knowledge base ───────────────────────────────────────────────────────
class KnowledgeBaseTests(_NoLearned):
    def _kb(self):
        with open(os.path.join(AGENT_DIR, "model_profiles.json"), encoding="utf-8") as fh:
            return json.load(fh)

    def test_the_shipped_knowledge_base_is_valid_and_every_entry_is_sourced(self):
        ids = set()
        for profile in self._kb()["profiles"]:
            self.assertNotIn(profile["id"], ids)
            ids.add(profile["id"])
            re.compile(profile["match"])
            self.assertTrue(profile["sources"], profile["id"])
            for url in profile["sources"]:
                self.assertTrue(url.startswith("https://"), url)
            for key in list(profile["sampling"]) + list(profile.get("sampling_no_thinking", {})):
                self.assertIn(key, model_brain.SAMPLING_KEYS, profile["id"])

    def test_every_family_angela_runs_has_a_formal_profile(self):
        expected = {
            "glm-5.3:cloud": "glm-5", "glm-5.2:cloud": "glm-5", "kimi-k3:cloud": "kimi",
            "kimi-k2.7-code:cloud": "kimi", "kimi-k2.6:cloud": "kimi", "deepseek-v4-pro:cloud": "deepseek-v4",
            "minimax-m3:cloud": "minimax-m3", "mistral-large-3:675b-cloud": "mistral-large-3",
            "gemma4:31b-cloud": "gemma-4", "gemma4:cloud": "gemma-4", "nemotron-3-ultra:cloud": "nemotron-3",
            "qwen3.5:397b-cloud": "qwen-3.5", "jcyhsiao/qwen3.5cloud:latest": "qwen-3.5",
            "gpt-oss:120b-cloud": "gpt-oss", "gpt-oss:20b-cloud": "gpt-oss", "qwen2.5:latest": "qwen-2.5",
        }
        for model, profile_id in expected.items():
            found = model_brain.match_profile(model)
            self.assertIsNotNone(found, model)
            self.assertEqual(found["id"], profile_id, model)

    def test_the_values_are_the_vendors_published_ones(self):
        def sampling(model):
            return model_brain.match_profile(model)["sampling"]
        self.assertEqual(sampling("glm-5.3:cloud"), {"temperature": 1.0, "top_p": 0.95, "repeat_penalty": 1.0})
        self.assertEqual(sampling("gpt-oss:120b-cloud")["temperature"], 1.0)
        self.assertEqual(sampling("gpt-oss:120b-cloud")["top_p"], 1.0)
        self.assertEqual(sampling("gemma4:31b-cloud")["top_k"], 64)
        self.assertEqual(sampling("qwen2.5:latest")["repeat_penalty"], 1.05)
        self.assertEqual(sampling("kimi-k3:cloud"), {}, "Moonshot: do not send temperature")
        self.assertLess(sampling("mistral-large-3:675b-cloud")["temperature"], 0.1)
        self.assertEqual(sampling("deepseek-v4-pro:cloud")["top_p"], 1.0)

    def test_no_profile_uses_the_old_fixed_values(self):
        for profile in self._kb()["profiles"]:
            self.assertNotEqual(profile["sampling"].get("repeat_penalty"), 1.2, profile["id"])
            self.assertNotEqual(profile["sampling"].get("temperature"), 0.0, profile["id"])

    def test_an_unknown_model_has_no_profile(self):
        self.assertIsNone(model_brain.match_profile("totally-new-model:cloud"))
        self.assertIsNone(model_brain.match_profile(""))

    def test_base_name(self):
        self.assertEqual(model_brain.base_name("jcyhsiao/Qwen3.5cloud:latest"), "qwen3.5cloud")
        self.assertEqual(model_brain.base_name("glm-5.3:cloud"), "glm-5.3")
        self.assertEqual(model_brain.base_name(None), "")


# ── what Ollama says ─────────────────────────────────────────────────────────
class DescribeTests(SimpleTestCase):
    def test_show_payload_is_read(self):
        data = {"capabilities": ["completion", "tools", "thinking"],
                "thinking": {"values": ["low", "medium", "high"], "default": "medium"},
                "model_info": {"gptoss.context_length": 131072, "gptoss.block_count": 36},
                "parameters": 'temperature 0.7\nstop "<|end|>"\ntop_k 40'}
        facts = model_brain._facts_from_show("gpt-oss:120b-cloud", data)
        self.assertTrue(facts.thinks)
        self.assertEqual(facts.thinking_default, "medium")
        self.assertEqual(facts.context_length, 131072)
        self.assertEqual(facts.parameters, {"temperature": 0.7, "top_k": 40.0})

    def test_a_failed_lookup_is_an_unknown_model_never_an_error(self):
        model_brain.reset_caches()
        with mock.patch.object(model_brain, "_fetch_show", side_effect=OSError("down")):
            facts = model_brain.describe("x:cloud", "http://127.0.0.1:9")
        self.assertFalse(facts.known)
        model_brain.reset_caches()


# ── the decision ─────────────────────────────────────────────────────────────
class PlanTests(_NoLearned):
    def _plan(self, model, facts, config=None):
        with mock.patch.object(model_brain, "describe", return_value=facts):
            return model_brain.plan(model, "http://127.0.0.1:9", config or {"ollama_num_ctx": 1048576})

    def test_the_formal_profile_replaces_the_fixed_values(self):
        plan = self._plan("glm-5.3:cloud", GLM_FACTS)
        self.assertTrue(plan.enabled)
        self.assertEqual(plan.sampling, {"temperature": 1.0, "top_p": 0.95, "repeat_penalty": 1.0})
        self.assertIsNone(plan.think, "the model's own default thinking level is kept")
        self.assertTrue(plan.keep_reasoning)
        self.assertIn("huggingface.co/zai-org/GLM-5.3", " ".join(plan.sources))

    def test_off_restores_the_legacy_behaviour(self):
        plan = self._plan("glm-5.3:cloud", GLM_FACTS, {"model_brain": "off"})
        self.assertFalse(plan.enabled)

    def test_an_explicit_override_always_wins(self):
        config = {"model_brain_overrides": {"glm-5.3:cloud": {"temperature": 0.3, "think": "high"}}}
        plan = self._plan("glm-5.3:cloud", GLM_FACTS, config)
        self.assertEqual(plan.sampling["temperature"], 0.3)
        self.assertEqual(plan.think, "high")

    def test_a_regex_override_key(self):
        config = {"model_brain_overrides": {"re:^glm": {"top_p": 0.9}}}
        self.assertEqual(self._plan("glm-5.3:cloud", GLM_FACTS, config).sampling["top_p"], 0.9)

    def test_a_thinking_level_the_model_does_not_publish_is_refused(self):
        config = {"model_brain_overrides": {"glm-5.3:cloud": {"think": "medium"}}}
        plan = self._plan("glm-5.3:cloud", GLM_FACTS, config)
        self.assertIsNone(plan.think)
        self.assertIn("not published", plan.think_note)

    def test_num_ctx_is_never_above_the_published_context(self):
        local = _facts("qwen2.5:latest", ctx=32768)
        self.assertEqual(self._plan("qwen2.5:latest", local).num_ctx, 32768)
        self.assertEqual(self._plan("glm-5.3:cloud", GLM_FACTS).num_ctx, 1048576)

    def test_only_a_thinking_model_gets_its_reasoning_back(self):
        self.assertFalse(self._plan("qwen2.5:latest", _facts("qwen2.5:latest")).keep_reasoning)
        config = {"model_brain_keep_reasoning": "off"}
        self.assertFalse(self._plan("glm-5.3:cloud", GLM_FACTS, config).keep_reasoning)

    def test_a_model_that_does_not_think_by_default_keeps_nothing(self):
        gemma = _facts("gemma4:31b-cloud", ("completion", "thinking", "tools", "vision"), (False, True), False)
        self.assertFalse(self._plan("gemma4:31b-cloud", gemma).keep_reasoning)
        config = {"model_brain_overrides": {"gemma4:31b-cloud": {"think": True}}}
        self.assertTrue(self._plan("gemma4:31b-cloud", gemma, config).keep_reasoning)

    def test_thinking_switched_off_uses_the_non_thinking_values(self):
        qwen = _facts("qwen3.5:397b-cloud", ("completion", "thinking", "tools"), (False, True), True)
        thinking = self._plan("qwen3.5:397b-cloud", qwen).sampling
        self.assertEqual(thinking["temperature"], 0.6)
        config = {"model_brain_overrides": {"qwen3.5:397b-cloud": {"think": False}}}
        plain = self._plan("qwen3.5:397b-cloud", qwen, config).sampling
        self.assertEqual((plain["temperature"], plain["presence_penalty"]), (0.7, 1.5))

    def test_an_unknown_model_uses_what_ollama_publishes(self):
        facts = _facts("brand-new:latest", params={"temperature": 0.4, "top_k": 30.0})
        with mock.patch.object(model_brain, "start_research") as research:
            plan = self._plan("brand-new:latest", facts)
        self.assertEqual(plan.sampling, {"temperature": 0.4, "top_k": 30.0})
        research.assert_not_called()

    def test_an_unknown_model_with_nothing_published_is_researched_in_the_background(self):
        with mock.patch.object(model_brain, "start_research") as research:
            plan = self._plan("brand-new:latest", _facts("brand-new:latest"))
        self.assertEqual(plan.sampling, {})
        research.assert_called_once_with("brand-new:latest")

    def test_a_failed_lookup_still_uses_the_formal_profile(self):
        plan = self._plan("glm-5.3:cloud", _facts("glm-5.3:cloud", caps=(), known=False))
        self.assertEqual(plan.sampling["temperature"], 1.0)

    def test_plan_never_raises(self):
        with mock.patch.object(model_brain, "describe", side_effect=RuntimeError("boom")):
            plan = model_brain.plan("glm-5.3:cloud", "", {})
        self.assertFalse(plan.enabled)


# ── research ─────────────────────────────────────────────────────────────────
class ResearchTests(SimpleTestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        patcher = mock.patch.dict(os.environ, {"TLAMATINI_MODEL_BRAIN_DIR": self.tmp})
        patcher.start()
        self.addCleanup(patcher.stop)
        model_brain.reset_caches()
        self.addCleanup(model_brain.reset_caches)

    def test_research_learns_from_the_vendor_generation_config(self):
        def fake_get(url):
            if "ollama.com" in url:
                return '<a href="https://huggingface.co/acme/Foo-1">model card</a>'
            if url.endswith("generation_config.json"):
                return json.dumps({"temperature": 0.8, "top_p": 0.9, "do_sample": True})
            raise OSError(url)
        with mock.patch.object(model_brain, "_http_get", side_effect=fake_get):
            entry = model_brain.research("foo-1:cloud")
        self.assertEqual(entry["sampling"], {"temperature": 0.8, "top_p": 0.9, "repeat_penalty": 1.0})
        self.assertIn("https://huggingface.co/acme/Foo-1/raw/main/generation_config.json", entry["sources"])
        found = model_brain.match_profile("foo-1:cloud")
        self.assertEqual(found["origin"], "learned")
        self.assertTrue(os.path.isfile(os.path.join(self.tmp, model_brain.LEARNED_FILENAME)))

    def test_a_miss_is_remembered_so_nothing_is_hammered(self):
        with mock.patch.object(model_brain, "_http_get", return_value="<html>no links</html>"):
            self.assertIsNone(model_brain.research("ghost:cloud"))
        self.assertIsNone(model_brain.match_profile("ghost:cloud"))
        self.assertTrue(model_brain._already_researched("ghost:cloud"))

    def test_research_never_raises(self):
        with mock.patch.object(model_brain, "_http_get", side_effect=OSError("offline")):
            self.assertIsNone(model_brain.research("x:cloud"))

    def test_only_model_repositories_are_followed(self):
        html = ('https://huggingface.co/datasets/a/b https://huggingface.co/spaces/c/d '
                'https://huggingface.co/zai-org/GLM-5.3 https://huggingface.co/zai-org/GLM-5.3')
        self.assertEqual(model_brain._hf_repos(html), ["zai-org/GLM-5.3"])

    def test_the_learned_file_lives_outside_the_install_folder(self):
        with mock.patch.dict(os.environ, {"TLAMATINI_MODEL_BRAIN_DIR": "", "LOCALAPPDATA": r"C:\Users\x\AppData\Local"}):
            self.assertEqual(model_brain._learned_dir(), os.path.join(r"C:\Users\x\AppData\Local", "Tlamatini", "model_brain"))


# ── the reasoning, over a REAL HTTP round trip ───────────────────────────────
class _FakeOllama:
    """A local HTTP server speaking Ollama's /api/chat; records every request body."""

    def __init__(self, replies):
        self.replies = list(replies)
        self.bodies = []
        fake = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))
                fake.bodies.append(body)
                reply = fake.replies.pop(0)
                if body.get("stream"):
                    payload = "".join(json.dumps(chunk) + "\n" for chunk in reply).encode()
                    self.send_response(200)
                    self.send_header("Content-Type", "application/x-ndjson")
                else:
                    payload = json.dumps(reply).encode()
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

        self.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = "http://127.0.0.1:%d" % self.server.server_address[1]
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()


def _done(message, **extra):
    reply = {"model": "fake", "created_at": "2026-10-08T00:00:00Z", "message": message, "done": True,
             "done_reason": "stop", "prompt_eval_count": 10, "eval_count": 5}
    reply.update(extra)
    return reply


class BrainChatOllamaTests(SimpleTestCase):
    def _tool(self):
        from langchain_core.tools import tool

        @tool
        def read_file(path: str) -> str:
            """Read a text file."""
            return "data"
        return read_file

    def test_the_reasoning_is_kept_and_returned_inside_the_tool_loop(self):
        from langchain_core.messages import HumanMessage, ToolMessage
        from agent.model_brain_chat import BrainChatOllama, REASONING_KEY
        fake = _FakeOllama([
            _done({"role": "assistant", "content": "", "thinking": "plan: read /a first",
                   "tool_calls": [{"function": {"name": "read_file", "arguments": {"path": "/a"}}}]}),
            _done({"role": "assistant", "content": "DONE"}),
        ])
        self.addCleanup(fake.close)
        llm = BrainChatOllama(model="fake:cloud", base_url=fake.url, keep_reasoning=True).bind_tools([self._tool()])
        messages = [HumanMessage(content="read /a")]
        first = llm.invoke(messages)
        self.assertEqual(first.additional_kwargs.get(REASONING_KEY), "plan: read /a first")
        self.assertEqual(first.content, "", "the reasoning never reaches the visible answer")
        self.assertEqual(first.tool_calls[0]["name"], "read_file")
        call_id = first.tool_calls[0]["id"]
        second = llm.invoke(messages + [first, ToolMessage(content="data", tool_call_id=call_id)])
        self.assertEqual(second.content, "DONE")
        assistant = [m for m in fake.bodies[1]["messages"] if m["role"] == "assistant"][0]
        self.assertEqual(assistant.get("thinking"), "plan: read /a first")

    def test_with_keep_reasoning_off_nothing_is_returned(self):
        from langchain_core.messages import AIMessage, HumanMessage
        from agent.model_brain_chat import BrainChatOllama, REASONING_KEY
        fake = _FakeOllama([[_done({"role": "assistant", "content": "ok"})]])   # no tools: a stream
        self.addCleanup(fake.close)
        llm = BrainChatOllama(model="fake:cloud", base_url=fake.url, keep_reasoning=False)
        llm.invoke([HumanMessage(content="hi"), AIMessage(content="x", additional_kwargs={REASONING_KEY: "why"}),
                    HumanMessage(content="again")])
        self.assertNotIn("thinking", [m for m in fake.bodies[0]["messages"] if m["role"] == "assistant"][0])

    def test_think_level_and_extra_options_are_sent(self):
        from langchain_core.messages import HumanMessage
        from agent.model_brain_chat import BrainChatOllama
        fake = _FakeOllama([[_done({"role": "assistant", "content": "ok"})]])
        self.addCleanup(fake.close)
        llm = BrainChatOllama(model="fake:cloud", base_url=fake.url, think="high", temperature=1.0,
                              extra_options={"presence_penalty": 1.5, "min_p": 0.0})
        llm.invoke([HumanMessage(content="hi")])
        body = fake.bodies[0]
        self.assertEqual(body.get("think"), "high")
        self.assertEqual(body["options"].get("presence_penalty"), 1.5)
        self.assertEqual(body["options"].get("temperature"), 1.0)

    def test_a_level_the_installed_client_cannot_send_is_never_sent(self):
        from langchain_core.messages import HumanMessage
        from agent.model_brain_chat import BrainChatOllama, client_accepts_think
        self.assertTrue(client_accepts_think("high"))
        self.assertTrue(client_accepts_think(None))
        fake = _FakeOllama([[_done({"role": "assistant", "content": "ok"})]])
        self.addCleanup(fake.close)
        llm = BrainChatOllama(model="fake:cloud", base_url=fake.url, think="not-a-level")
        llm.invoke([HumanMessage(content="hi")])
        self.assertNotIn("think", fake.bodies[0])

    def test_streamed_reasoning_is_accumulated(self):
        from langchain_core.messages import HumanMessage
        from agent.model_brain_chat import BrainChatOllama, REASONING_KEY
        chunks = [
            {"model": "fake", "created_at": "2026-10-08T00:00:00Z",
             "message": {"role": "assistant", "content": "", "thinking": "first, "}, "done": False},
            {"model": "fake", "created_at": "2026-10-08T00:00:00Z",
             "message": {"role": "assistant", "content": "", "thinking": "then answer"}, "done": False},
            _done({"role": "assistant", "content": "42"}),
        ]
        fake = _FakeOllama([chunks])
        self.addCleanup(fake.close)
        reply = BrainChatOllama(model="fake:cloud", base_url=fake.url).invoke([HumanMessage(content="?")])
        self.assertEqual(reply.content, "42")
        self.assertEqual(reply.additional_kwargs[REASONING_KEY], "first, then answer")


    def test_a_reply_keeps_its_reasoning_only_when_it_will_be_sent(self):
        from langchain_core.messages import HumanMessage
        from agent.model_brain_chat import BrainChatOllama, REASONING_KEY
        chunks = [{"model": "fake", "created_at": "2026-10-08T00:00:00Z",
                   "message": {"role": "assistant", "content": "", "thinking": "why"}, "done": False},
                  _done({"role": "assistant", "content": "ok"})]
        fake = _FakeOllama([chunks])
        self.addCleanup(fake.close)
        reply = BrainChatOllama(model="fake:cloud", base_url=fake.url, keep_reasoning=False).invoke(
            [HumanMessage(content="?")])
        self.assertNotIn(REASONING_KEY, reply.additional_kwargs)


# ── the context-window gauge counts exactly what is sent ────────────────────
class GaugePrecisionTests(SimpleTestCase):
    def test_the_gauge_counts_the_reasoning_that_is_sent_back(self):
        from langchain_core.messages import AIMessage
        from agent import context_governor
        plain = AIMessage(content="ok")
        with_reasoning = AIMessage(content="ok", additional_kwargs={"reasoning_content": "x" * 1000})
        wire0, chars0 = context_governor._message_wire(plain)
        wire1, chars1 = context_governor._message_wire(with_reasoning)
        self.assertEqual(chars1 - chars0, 1000, "the reasoning is prompt text the model reads")
        self.assertGreaterEqual(wire1 - wire0, 1000, "and bytes on the wire")

    def test_an_ollama_style_dict_message_is_counted_the_same_way(self):
        from agent import context_governor
        _, chars = context_governor._message_wire({"role": "assistant", "content": "ok", "thinking": "y" * 50})
        self.assertEqual(chars, 52)


# ── the wiring ───────────────────────────────────────────────────────────────
class WiringTests(_NoLearned):
    CONFIG = {"unified_agent_model": "glm-5.3:cloud", "unified_agent_base_url": "http://127.0.0.1:9",
              "unified_agent_temperature": 0.0, "ollama_num_ctx": 1048576}

    def _model(self, config):
        from langchain_ollama.llms import OllamaLLM
        from agent import mcp_agent
        with mock.patch.object(mcp_agent, "_load_config", return_value=dict(config)), \
                mock.patch.object(model_brain, "describe", return_value=GLM_FACTS):
            return mcp_agent._ensure_chat_tool_model(
                OllamaLLM(model="glm-5.3:cloud", base_url="http://127.0.0.1:9", repeat_penalty=1.2,
                          repeat_last_n=256, top_k=20, top_p=0.8))

    def test_the_executor_model_is_configured_by_the_brain(self):
        from agent.model_brain_chat import BrainChatOllama
        chat = self._model(self.CONFIG)
        self.assertIsInstance(chat, BrainChatOllama)
        self.assertEqual((chat.temperature, chat.top_p, chat.repeat_penalty), (1.0, 0.95, 1.0))
        self.assertIsNone(chat.top_k, "a value the vendor does not publish is not sent")
        self.assertIsNone(chat.repeat_last_n)
        self.assertTrue(chat.keep_reasoning)

    def test_model_brain_off_keeps_the_legacy_model_exactly(self):
        from agent.model_brain_chat import BrainChatOllama
        chat = self._model(dict(self.CONFIG, model_brain="off"))
        self.assertNotIsInstance(chat, BrainChatOllama)
        self.assertEqual((chat.temperature, chat.repeat_penalty, chat.top_k), (0.0, 1.2, 20))

    def test_the_chat_chains_use_the_brain_too(self):
        from agent.rag import factory
        config = {"chained-model": "glm-5.3:cloud", "ollama_base_url": "http://127.0.0.1:9", "ollama_num_ctx": 1048576}
        with mock.patch.object(model_brain, "describe", return_value=GLM_FACTS):
            chosen = factory._model_sampling_kwargs(config, {})
        self.assertEqual((chosen["temperature"], chosen["top_p"], chosen["repeat_penalty"]), (1.0, 0.95, 1.0))
        self.assertIsNone(chosen["top_k"])
        legacy = factory._model_sampling_kwargs(dict(config, model_brain="off"), {})
        self.assertEqual((legacy["temperature"], legacy["top_k"], legacy["top_p"]), (0.0, 20, 0.8))


# ── the Auto-tuning dialog's endpoints ──────────────────────────────────────
class TuningEndpointTests(TestCase):
    CONFIG = {"unified_agent_model": "glm-5.3:cloud", "chained-model": "glm-5.3:cloud",
              "access_aimed_prompt_model": "glm-5.2:cloud", "embeding-model": "Nomic-Embed-Text:latest",
              "ollama_base_url": "http://127.0.0.1:9", "ollama_num_ctx": 1048576}

    def setUp(self):
        user = get_user_model().objects.create_user("brain", password="pw")
        self.client.force_login(user)
        model_brain.reset_caches()
        self.addCleanup(model_brain.reset_caches)
        for target in ("agent.model_brain_views.load_config",):
            patcher = mock.patch(target, return_value=dict(self.CONFIG))
            patcher.start()
            self.addCleanup(patcher.stop)
        learned = mock.patch.object(model_brain, "learned_profiles", return_value=[])
        learned.start()
        self.addCleanup(learned.stop)

    def test_the_brain_models_come_first(self):
        data = self.client.get("/agent/model_brain/models/").json()
        self.assertTrue(data["success"])
        self.assertEqual(data["models"][0]["model"], "glm-5.3:cloud")
        self.assertTrue(data["models"][0]["applied"])
        self.assertIn("glm-5.2:cloud", [row["model"] for row in data["models"]])

    def test_tuning_reports_every_step_with_real_values(self):
        with mock.patch.object(model_brain, "_fetch_show", return_value={
                "capabilities": ["completion", "thinking", "tools"],
                "thinking": {"values": ["low", "high", "max"], "default": "max"},
                "model_info": {"glm.context_length": 1048576}}):
            data = self.client.post("/agent/model_brain/tune/", json.dumps({"model": "glm-5.3:cloud"}),
                                    content_type="application/json").json()
        self.assertTrue(data["success"])
        self.assertEqual([s["step"] for s in data["steps"]], ["ollama", "profile"])
        self.assertEqual(data["sampling"]["temperature"], 1.0)
        self.assertTrue(data["keep_reasoning"])
        self.assertTrue(data["sources"])

    def test_an_embedding_model_is_reported_as_nothing_to_tune(self):
        with mock.patch.object(model_brain, "_fetch_show", return_value={"capabilities": ["embedding"]}):
            data = self.client.post("/agent/model_brain/tune/", json.dumps({"model": "Nomic-Embed-Text:latest"}),
                                    content_type="application/json").json()
        self.assertFalse(data["tunable"])

    def test_only_configured_models_can_be_tuned(self):
        response = self.client.post("/agent/model_brain/tune/", json.dumps({"model": "evil:cloud"}),
                                    content_type="application/json")
        self.assertEqual(response.status_code, 400)

    def test_login_is_required(self):
        self.client.logout()
        self.assertNotEqual(self.client.get("/agent/model_brain/models/").status_code, 200)
