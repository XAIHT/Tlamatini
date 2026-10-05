"""The context sidecars' own Ollama calls are bounded (Angela, 2026-10-05).

Her installed build sat for about five minutes on "Fetching file search
context ..." because the Files-Search planning call to Ollama had no time
limit and logged nothing while it waited. These tests pin the fix: each
sidecar call ends at the time limit or at the user's Cancel, the sidecar then
skips its context so the answer goes ahead, and the log says why.
"""
import asyncio
import io
import json
import os
import tempfile
import time
import unittest
from contextlib import redirect_stdout
from unittest.mock import AsyncMock, patch

from langchain_core.runnables import RunnableLambda

from agent import cancellation
from agent import context_sidecar_timeout as cst

# Far below any limit a hung call could reach; generous for a slow machine.
_FAST_ENOUGH_SECONDS = 10.0


class _Hang:
    """A runnable whose call never answers, like the stuck Ollama call."""

    def __init__(self):
        self.cancelled = False

    async def ainvoke(self, _inputs):
        try:
            await asyncio.sleep(3600)
        except asyncio.CancelledError:
            self.cancelled = True
            raise


class _Answer:
    def __init__(self, value):
        self.value = value

    async def ainvoke(self, _inputs):
        await asyncio.sleep(0.01)
        return self.value


class _Fail:
    async def ainvoke(self, _inputs):
        raise RuntimeError("ollama said no")


async def _hang_forever(_prompt):
    await asyncio.sleep(3600)


async def _route_yes_then_hang(prompt):
    """Answers the YES/NO routing question, then never answers the planning one."""
    text = prompt.to_string() if hasattr(prompt, "to_string") else str(prompt)
    if "Answer ONLY with YES or NO" in text:
        return "YES"
    await asyncio.sleep(3600)


def _fake_llm(afunc):
    return RunnableLambda(lambda _prompt: "", afunc=afunc)


def _write_config(folder, limit=0.5):
    path = os.path.join(folder, "config.json")
    config = {
        "ollama_base_url": "http://127.0.0.1:9",
        "chained-model": "sidecar-test-model",
        cst.CONFIG_KEY: limit,
    }
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(config, handle)
    return path


class ResolveTimeoutTests(unittest.TestCase):
    def test_default_when_missing(self):
        self.assertEqual(cst.resolve_timeout({}), cst.DEFAULT_TIMEOUT_SECONDS)
        self.assertEqual(cst.resolve_timeout(None), cst.DEFAULT_TIMEOUT_SECONDS)

    def test_an_explicit_value_is_obeyed_exactly(self):
        self.assertEqual(cst.resolve_timeout({cst.CONFIG_KEY: 7}), 7.0)
        self.assertEqual(cst.resolve_timeout({cst.CONFIG_KEY: "2.5"}), 2.5)
        self.assertEqual(cst.resolve_timeout({cst.CONFIG_KEY: 900}), 900.0)

    def test_bad_values_fall_back_to_the_default(self):
        for bad in (0, -3, "abc", None, True, float("nan"), float("inf"), [], {}):
            with self.subTest(bad=bad):
                self.assertEqual(cst.resolve_timeout({cst.CONFIG_KEY: bad}),
                                 cst.DEFAULT_TIMEOUT_SECONDS)

    def test_the_http_backstop_is_longer_and_keeps_the_headers(self):
        kwargs = cst.client_kwargs_with_timeout({"headers": {"Authorization": "Bearer x"}}, 60)
        self.assertEqual(kwargs["headers"], {"Authorization": "Bearer x"})
        self.assertGreater(kwargs["timeout"], 60)
        self.assertEqual(cst.client_kwargs_with_timeout({"timeout": 9}, 60)["timeout"], 9)

    def test_the_shipped_config_declares_the_setting(self):
        path = os.path.join(os.path.dirname(os.path.abspath(cst.__file__)), "config.json")
        with open(path, "r", encoding="utf-8-sig") as handle:
            shipped = json.load(handle)
        self.assertEqual(shipped.get(cst.CONFIG_KEY), cst.DEFAULT_TIMEOUT_SECONDS)


class TimeLimitTests(unittest.TestCase):
    def test_a_fast_answer_is_returned(self):
        result = asyncio.run(cst.ainvoke_with_time_limit(_Answer("YES"), {}, timeout=5, label="t"))
        self.assertEqual(result, "YES")

    def test_an_error_from_ollama_is_raised_unchanged(self):
        with self.assertRaisesRegex(RuntimeError, "ollama said no"):
            asyncio.run(cst.ainvoke_with_time_limit(_Fail(), {}, timeout=5, label="t"))

    def test_a_hung_call_ends_at_the_limit_is_cancelled_and_says_why(self):
        hang = _Hang()
        out = io.StringIO()
        started = time.monotonic()
        with redirect_stdout(out), self.assertRaises(cst.SidecarLLMTimeout):
            asyncio.run(cst.ainvoke_with_time_limit(
                hang, {}, timeout=0.5, label="Files-Search planning", model="m"))
        self.assertLess(time.monotonic() - started, _FAST_ENOUGH_SECONDS)
        self.assertTrue(hang.cancelled)
        log = out.getvalue()
        self.assertIn("[CONTEXT-SIDECAR] Files-Search planning", log)
        self.assertIn("model=m", log)
        self.assertIn(cst.CONFIG_KEY, log)

    def test_cancel_ends_the_wait_at_once(self):
        hang = _Hang()
        pressed = {"cancel": False}

        async def scenario():
            async def press_cancel():
                await asyncio.sleep(0.3)
                pressed["cancel"] = True

            presser = asyncio.ensure_future(press_cancel())
            try:
                await cst.ainvoke_with_time_limit(
                    hang, {}, timeout=60, label="t", cancelled=lambda: pressed["cancel"])
            finally:
                await presser

        started = time.monotonic()
        with redirect_stdout(io.StringIO()), self.assertRaises(cst.SidecarLLMCancelled):
            asyncio.run(scenario())
        self.assertLess(time.monotonic() - started, _FAST_ENOUGH_SECONDS)
        self.assertTrue(hang.cancelled)


class CancelCheckTests(unittest.TestCase):
    USER = "sidecar-timeout-test-user"

    def tearDown(self):
        cancellation.reset_for_tests(self.USER)

    def test_it_follows_the_users_cancel_for_this_request(self):
        epoch = cancellation.begin_llm_run(self.USER)
        check = cst.make_cancel_check(self.USER, epoch)
        self.assertFalse(check())
        cancellation.request_cancel_generation(self.USER)
        self.assertTrue(check())

    def test_a_broken_cancel_check_reads_not_cancelled(self):
        with patch("agent.cancellation.is_generation_cancelled", side_effect=RuntimeError("boom")):
            self.assertFalse(cst.make_cancel_check(self.USER, 1)())


class FilesSearchSidecarTests(unittest.TestCase):
    USER = "sidecar-files-test-user"

    def tearDown(self):
        cancellation.reset_for_tests(self.USER)

    def _chain(self, folder, afunc, limit=0.5):
        from agent.chain_files_search_lcel import FileSearchRAGChain
        chain = FileSearchRAGChain(_write_config(folder, limit))
        chain.llm = _fake_llm(afunc)
        return chain

    def test_the_chain_reads_the_limit_and_logs_its_ollama_calls(self):
        from agent.chain_files_search_lcel import FileSearchRAGChain
        from agent.llm_timing import OLLAMA_TIMER
        with tempfile.TemporaryDirectory() as folder:
            chain = FileSearchRAGChain(_write_config(folder))
        self.assertEqual(chain.llm_time_limit, 0.5)
        self.assertIn(OLLAMA_TIMER, chain.llm.callbacks)
        self.assertGreater(chain.llm.client_kwargs["timeout"], 0.5)

    def test_a_hung_planning_call_skips_the_file_search(self):
        # The exact 2026-10-05 case: routing said YES, planning never answered.
        out = io.StringIO()
        with tempfile.TemporaryDirectory() as folder:
            chain = self._chain(folder, _route_yes_then_hang)
            started = time.monotonic()
            with redirect_stdout(out):
                result = asyncio.run(chain.intelligent_context_fetch(
                    {"question": "find every file of the PC App Store program"}))
        self.assertLess(time.monotonic() - started, _FAST_ENOUGH_SECONDS)
        self.assertEqual(result["files_context"], "")
        self.assertIn("[CONTEXT-SIDECAR] Files-Search planning", out.getvalue())

    def test_a_hung_routing_call_skips_the_file_search(self):
        out = io.StringIO()
        with tempfile.TemporaryDirectory() as folder:
            chain = self._chain(folder, _hang_forever)
            with redirect_stdout(out):
                result = asyncio.run(chain.intelligent_context_fetch({"question": "find my notes"}))
        self.assertEqual(result["files_context"], "")
        self.assertIn("[CONTEXT-SIDECAR] Files-Search routing", out.getvalue())

    def test_the_users_cancel_ends_the_wait_long_before_the_limit(self):
        epoch = cancellation.begin_llm_run(self.USER)
        cancellation.request_cancel_generation(self.USER)
        with tempfile.TemporaryDirectory() as folder:
            chain = self._chain(folder, _hang_forever, limit=60)
            started = time.monotonic()
            with redirect_stdout(io.StringIO()):
                result = asyncio.run(chain.intelligent_context_fetch({
                    "question": "find my notes",
                    "conversation_user_id": self.USER,
                    "cancel_run_epoch": epoch,
                }))
        self.assertLess(time.monotonic() - started, _FAST_ENOUGH_SECONDS)
        self.assertEqual(result["files_context"], "")


class SystemMetricsSidecarTests(unittest.TestCase):
    def test_a_hung_routing_call_skips_system_metrics(self):
        from agent.chain_system_lcel import SystemRAGChain
        from agent.llm_timing import OLLAMA_TIMER
        with tempfile.TemporaryDirectory() as folder:
            chain = SystemRAGChain(_write_config(folder))
        self.assertEqual(chain.llm_time_limit, 0.5)
        self.assertIn(OLLAMA_TIMER, chain.llm.callbacks)
        chain.llm = _fake_llm(_hang_forever)
        chain.get_available_resources = AsyncMock(return_value=["cpu_usage"])
        out = io.StringIO()
        started = time.monotonic()
        with redirect_stdout(out):
            # No metric keyword and no general-knowledge keyword: the LLM decides.
            needs = asyncio.run(chain.should_fetch_system_context("tell me about the weather in my house"))
        self.assertLess(time.monotonic() - started, _FAST_ENOUGH_SECONDS)
        self.assertFalse(needs)
        self.assertIn("[CONTEXT-SIDECAR] System-Metrics routing", out.getvalue())


if __name__ == "__main__":
    unittest.main()
