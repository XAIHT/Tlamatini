"""No Ollama request may carry more than four stop sequences, and a failed
chat-history summary must never fail the answer (Angela, 2026-10-03).

The bug: a plain Multi-Turn prompt died before any work was done with
``too many stop sequences; maximum is 4 (status code: 400)``. The chat LLM
carried NINE stop sequences; Ollama's cloud models (measured: glm-5.2:cloud and
glm-5.3:cloud) refuse five or more. The first call that used that LLM was the
chat-history summary, and its exception killed the whole request.

Two layers are pinned here:
1. ``agent/ollama_stop.py`` caps every stop list at four, for ANY model, and a
   source-tree guard fails if any new code sends a longer list.
2. ``rag/chains/base.summarize_or_none`` - every chain's history summary - is
   FAIL-OPEN: a failed summary sends the history unsummarized (a Cancel still
   propagates).
"""
from __future__ import annotations

import ast
import os

from django.test import SimpleTestCase
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from agent import ollama_stop
from agent.rag import factory
from agent.rag.chains import base as chain_base
from agent.rag.chains.basic import BasicPromptOnlyChain
from agent.rag.chains.history_aware import HistoryAwareNoDocsChain, OptimizedHistoryAwareRAGChain
from agent.rag.chains.unified import UnifiedAgentChain, UnifiedAgentRAGChain

AGENT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(AGENT_DIR))
NINE = ["<|endoftext|>", "<|im_start|>", "<|im_end|>", "\nHuman:", "\nUser:",
        "\nAssistant:", "\nSystem:", "\nAI:", "\nEND-RESPONSE\n"]
THE_400 = ("too many stop sequences; maximum is 4 "
           "(ref: 9cfb9d95-9222-40fa-a5a5-906626692f6d) (status code: 400)")
MODELS = ("glm-5.2:cloud", "glm-5.3:cloud", "gpt-oss:120b-cloud", "qwen2.5:latest",
          "llama3.1:8b", "my-local-alias-of-a-cloud-model", "", None)
BASE_URLS = (None, "http://127.0.0.1:11434", "https://ollama.com", "http://10.0.0.5:11434")


class StopLimitTests(SimpleTestCase):

    def test_never_more_than_four_for_any_model_or_server(self):
        for model in MODELS:
            for url in BASE_URLS:
                stops = ollama_stop.fit_stop_sequences(NINE, model, url)
                self.assertLessEqual(len(stops), 4, (model, url, stops))
                self.assertEqual(stops, NINE[:4], (model, url))

    def test_order_is_kept_and_duplicates_and_empties_are_dropped(self):
        stops = ollama_stop.fit_stop_sequences(["a", "", "a", None, "b", 7, "c", "d", "e"], "glm-5.2:cloud")
        self.assertEqual(stops, ["a", "b", "c", "d"])

    def test_the_limit_can_be_lowered_but_never_raised(self):
        self.assertEqual(ollama_stop.fit_stop_sequences(NINE, limit=2), NINE[:2])
        self.assertEqual(len(ollama_stop.fit_stop_sequences(NINE, limit=99)), 4)
        self.assertEqual(len(ollama_stop.fit_stop_sequences(NINE, limit="junk")), 4)

    def test_it_never_raises(self):
        self.assertEqual(ollama_stop.fit_stop_sequences(None), [])
        self.assertEqual(ollama_stop.fit_stop_sequences(12345), [])
        self.assertLessEqual(len(ollama_stop.fit_stop_sequences("abcdefg")), 4)

    def test_cloud_models_are_recognised_for_the_log(self):
        for name in ("glm-5.2:cloud", "glm-5.3:cloud", "gpt-oss:120b-cloud", "GLM-5.2:CLOUD"):
            self.assertTrue(ollama_stop.is_cloud_model(name), name)
        self.assertTrue(ollama_stop.is_cloud_model("glm-5.2", "https://ollama.com"))
        for name in ("qwen2.5:latest", "llama3.1:8b", "", None):
            self.assertFalse(ollama_stop.is_cloud_model(name, "http://127.0.0.1:11434"), name)


class ChatLlmStopTests(SimpleTestCase):

    def test_the_chat_list_itself_has_at_most_four(self):
        self.assertLessEqual(len(factory._CHAT_STOP_TOKENS), ollama_stop.STOP_LIMIT)
        self.assertIn("\nEND-RESPONSE\n", factory._CHAT_STOP_TOKENS)
        self.assertIn("\nHuman:", factory._CHAT_STOP_TOKENS)

    def test_the_chat_llm_gets_at_most_four_on_both_test_models(self):
        for model in ("glm-5.2:cloud", "qwen2.5:latest"):
            stops = factory._chat_stop_tokens({"chained-model": model,
                                               "ollama_base_url": "http://127.0.0.1:11434"})
            self.assertLessEqual(len(stops), 4, model)
            self.assertTrue(stops, model)

    def test_the_request_ollama_receives_carries_at_most_four(self):
        """Build the LLM exactly like rag/factory.py does and read the stop list
        out of the request parameters langchain-ollama will send."""
        from langchain_ollama import OllamaLLM
        for model in ("glm-5.2:cloud", "qwen2.5:latest"):
            config = {"chained-model": model, "ollama_base_url": "http://127.0.0.1:11434"}
            llm = OllamaLLM(model=model, base_url=config["ollama_base_url"],
                            stop=factory._chat_stop_tokens(config))
            sent = list(llm.stop or [])
            params = getattr(llm, "_generate_params", None)
            if callable(params):
                try:
                    options = (params("hi") or {}).get("options") or {}
                    sent = list(options.get("stop") or sent)
                except Exception:                    # noqa: BLE001 - older wrapper shape
                    pass
            self.assertLessEqual(len(sent), 4, (model, sent))


# --------------------------------------------------------------- source guard
_SKIP_DIRS = {"python", "node_modules", "venv", ".venv", "Temp", "dist", "build", ".git",
              "staticfiles", "TlamatiniSourceCode", "Templates", "jre", "git", "Go",
              "__pycache__", "artifacts", "output"}
_FITTERS = {"fit_stop_sequences", "_chat_stop_tokens"}


def _call_name(node):
    if isinstance(node, ast.Call):
        func = node.func
        return func.id if isinstance(func, ast.Name) else getattr(func, "attr", "")
    return ""


def _problems_in(path):
    with open(path, encoding="utf-8", errors="replace") as fh:
        try:
            tree = ast.parse(fh.read())
        except SyntaxError:
            return []
    fitted_names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and _call_name(node.value) in _FITTERS:
            fitted_names.update(t.id for t in node.targets if isinstance(t, ast.Name))
    values = []
    for node in ast.walk(tree):
        if isinstance(node, ast.keyword) and node.arg in ("stop", "stop_sequences"):
            values.append(node.value)
        elif isinstance(node, ast.Dict):
            values.extend(v for k, v in zip(node.keys, node.values)
                          if isinstance(k, ast.Constant) and k.value in ("stop", "stop_sequences"))
    problems = []
    for value in values:
        if _call_name(value) in _FITTERS:
            continue
        if isinstance(value, ast.Name) and value.id in fitted_names:
            continue
        if isinstance(value, ast.Constant) and value.value is None:
            continue
        if isinstance(value, (ast.List, ast.Tuple)) and len(value.elts) <= ollama_stop.STOP_LIMIT:
            continue
        problems.append("%s:%d  stop=%s" % (os.path.relpath(path, REPO_ROOT), value.lineno,
                                            ast.unparse(value)[:90]))
    return problems


class NoLongStopListAnywhereTests(SimpleTestCase):
    """Every stop list in the source tree is fitted or has at most four entries.
    A new LLM call that sends five or more fails HERE, not in Angela's chat."""

    def test_the_whole_source_tree(self):
        problems, scanned = [], 0
        for root in (os.path.join(REPO_ROOT, "Tlamatini"), os.path.join(REPO_ROOT, "scripts")):
            for dirpath, dirnames, filenames in os.walk(root):
                dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS]
                for name in filenames:
                    if name.endswith(".py") and name != os.path.basename(__file__):
                        scanned += 1
                        problems.extend(_problems_in(os.path.join(dirpath, name)))
        for name in os.listdir(REPO_ROOT):
            if name.endswith(".py"):
                scanned += 1
                problems.extend(_problems_in(os.path.join(REPO_ROOT, name)))
        self.assertGreater(scanned, 300)
        self.assertEqual(problems, [], "stop lists that are not fitted to at most four:\n" + "\n".join(problems))

    def test_the_guard_really_catches_a_long_list(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            bad = os.path.join(tmp, "bad.py")
            with open(bad, "w", encoding="utf-8") as fh:
                fh.write("llm = Thing(stop=['a', 'b', 'c', 'd', 'e'])\n"
                         "payload = {'options': {'stop': ['1', '2', '3', '4', '5']}}\n"
                         "ok = Thing(stop=fit_stop_sequences(['a', 'b', 'c', 'd', 'e']))\n")
            self.assertEqual(len(_problems_in(bad)), 2)


# --------------------------------------------------------------- fail-open summary
class _FakeLLM:
    def __init__(self, exc=None, content="SUMMARY OF THE EARLIER TALK"):
        self.exc, self.content, self.calls = exc, content, 0

    def with_config(self, _config):
        return self

    def invoke(self, _msgs):
        self.calls += 1
        if self.exc is not None:
            raise self.exc
        return AIMessage(content=self.content)


def _long_history():
    return [HumanMessage(content="What is the CPU usage? " * 40),
            AIMessage(content="CPU 11.8%, memory 95.6%, disk 101.8 GB free. " * 40),
            HumanMessage(content="Thanks, now search my catalog. " * 40)]


CHAINS = (BasicPromptOnlyChain, HistoryAwareNoDocsChain, OptimizedHistoryAwareRAGChain,
          UnifiedAgentChain, UnifiedAgentRAGChain)


def _chain(cls, llm):
    chain = cls.__new__(cls)
    chain.history_summary_cfg = {"enable": True, "trigger_tokens": 1, "keep_last_turns": 2}
    chain.llm = llm
    return chain


class HistorySummaryFailOpenTests(SimpleTestCase):

    def test_the_helper_returns_none_on_the_real_400(self):
        self.assertIsNone(chain_base.summarize_or_none(_FakeLLM(Exception(THE_400)), []))

    def test_the_helper_lets_a_cancel_through(self):
        with self.assertRaises(chain_base.GenerationCancelledException):
            chain_base.summarize_or_none(_FakeLLM(chain_base.GenerationCancelledException("x")), [])

    def test_the_helper_returns_the_summary(self):
        self.assertEqual(chain_base.summarize_or_none(_FakeLLM(), []), "SUMMARY OF THE EARLIER TALK")

    def test_every_chain_answers_with_the_history_when_the_summary_fails(self):
        for cls in CHAINS:
            history = _long_history()
            llm = _FakeLLM(Exception(THE_400))
            out = _chain(cls, llm)._summarize_history_if_needed(history, "search my catalog")
            self.assertEqual(llm.calls, 1, cls.__name__)
            self.assertIs(out, history, cls.__name__)

    def test_every_chain_still_summarizes_when_the_model_answers(self):
        for cls in CHAINS:
            llm = _FakeLLM()
            out = _chain(cls, llm)._summarize_history_if_needed(_long_history(), "search my catalog")
            self.assertEqual(llm.calls, 1, cls.__name__)
            text = " ".join(str(getattr(m, "content", m)) for m in out)
            self.assertIn("SUMMARY OF THE EARLIER TALK", text, cls.__name__)
            self.assertTrue(any(isinstance(m, SystemMessage) for m in out), cls.__name__)

    def test_every_chain_lets_a_cancel_through(self):
        for cls in CHAINS:
            llm = _FakeLLM(chain_base.GenerationCancelledException("cancelled"))
            with self.assertRaises(chain_base.GenerationCancelledException, msg=cls.__name__):
                _chain(cls, llm)._summarize_history_if_needed(_long_history(), "q")
