# -*- coding: utf-8 -*-
# ═══════════════════════════════════════════════════════════════════
#   ✦  T L A M A T I N I  ✦   —   "one who knows"
#
#   Created by  Angela López Mendoza   ·   @angelahack1
#   Developer · Architect · Creator of Tlamatini
# ═══════════════════════════════════════════════════════════════════
#   Tlamatini Author Banner — do not remove
"""
Regression pins for the PERMANENT CHAT WEDGE (found 2026-07-29, Angela).

THE BUG
    ``rag_chain_ready`` is the PROCESS-GLOBAL busy/free latch for Tlamatini's
    ONE chat lane. Three functions lowered it on entry and raised it again only
    on their ORDINARY exits:

      * ``rag/interface.py::ask_rag``            — its ``except … raise`` skipped it
      * ``rag/factory.py::setup_llm``            — every `return None` + any raise
      * ``rag/factory.py::setup_llm_with_context`` — same

    So ONE failed chain call, or ONE failed rebuild, left the latch DOWN for
    the rest of the process. Worse, ``consumers.py``'s rebuild then set
    ``self.rag_chain = None`` on failure — so the self-heal ATTEMPT is what
    finished killing the chat.

WHAT THAT LOOKED LIKE
    Server alive and answering HTTP. Ollama healthy. GPU idle at 0 %. Nothing
    computing anywhere. And the chat DEAD FOREVER: every message answered with
    "Agent is not ready". Refreshing the browser did NOT help — the latch is
    process-global while the rebuild lock is per-connection, so a new consumer
    inherited the dead latch and never rebuilt. Only killing the process cured
    it.

THE FIX
    Each of the three is now a thin wrapper whose ``finally`` restores the
    latch unconditionally (bodies moved to ``_*_impl``), the last-resort
    ``build_prompt_only_chain`` degrades to ``None`` instead of raising, and
    both consumer rebuilds are non-destructive: they keep the last working
    chain and restate the latch truthfully on every exit.

These tests fail on the OLD code and pass on the new. Do not weaken them: the
exception tests are the ones that actually reproduce the outage.
"""
import unittest

from django.test import SimpleTestCase

from agent.rag import interface as I


READY = "rag_chain_ready"


class _FakeChain:
    """Minimal stand-in for the real chain object."""

    def __init__(self, behaviour="ok"):
        self.behaviour = behaviour
        self.calls = 0

    def invoke(self, payload):
        self.calls += 1
        if self.behaviour == "raise":
            raise RuntimeError("simulated model failure")
        if self.behaviour == "dict":
            return {"answer": "done", "multi_turn_used": True}
        return "done"

    def getHttpxClientInstance(self):      # noqa: N802 (mirrors the real API)
        return None


def _question(text="hello"):
    """A Multi-Turn question, so prompt-shape/access validation is bypassed."""
    return {
        "input": text,
        "conversation_user_id": 1,
        "multi_turn_enabled": True,
        "exec_report_enabled": False,
        "acpx_enabled": False,
        "ask_execs_enabled": False,
        "step_by_step_enabled": False,
    }


class ChainReadinessLatchTests(SimpleTestCase):
    """ask_rag must release the latch on EVERY exit path."""

    def setUp(self):
        # Start each test from a known-bad state so a test that never touches
        # the flag cannot accidentally pass.
        I.global_state.set_state(READY, False)

    def _ready(self):
        return I.global_state.get_state(READY)

    def test_latch_released_after_a_normal_answer(self):
        out = I.ask_rag(_FakeChain("ok"), _question())
        self.assertTrue(self._ready(), "a normal answer must release the chain")
        self.assertIn("done", str(out))

    def test_latch_released_after_a_dict_answer(self):
        out = I.ask_rag(_FakeChain("dict"), _question())
        self.assertTrue(self._ready(), "a dict answer must release the chain")
        self.assertIn("done", str(out))

    def test_latch_released_when_the_chain_RAISES(self):
        """*** THE OUTAGE ***  Fails on the old code: the latch stayed down."""
        with self.assertRaises(RuntimeError):
            I.ask_rag(_FakeChain("raise"), _question())
        self.assertTrue(
            self._ready(),
            "an exception must NOT leave the chain latched shut — that is "
            "exactly the bug that killed the chat permanently",
        )

    def test_the_error_still_propagates(self):
        """The fix must not SWALLOW the failure — a silent success is worse."""
        with self.assertRaises(RuntimeError) as ctx:
            I.ask_rag(_FakeChain("raise"), _question())
        self.assertIn("simulated model failure", str(ctx.exception))

    def test_chat_still_works_after_a_failure(self):
        """The real user-visible contract: one bad request must not kill the chat."""
        with self.assertRaises(RuntimeError):
            I.ask_rag(_FakeChain("raise"), _question("this one breaks"))
        self.assertTrue(self._ready())
        out = I.ask_rag(_FakeChain("ok"), _question("and this one works"))
        self.assertIn("done", str(out))
        self.assertTrue(self._ready())

    def test_repeated_failures_never_latch_it_down(self):
        for _ in range(5):
            with self.assertRaises(RuntimeError):
                I.ask_rag(_FakeChain("raise"), _question())
            self.assertTrue(self._ready())


class ChainReadinessSourceContractTests(SimpleTestCase):
    """Pin the STRUCTURE, so a future refactor cannot quietly undo the fix."""

    def _source(self):
        import inspect

        return inspect.getsource(I)

    def test_ask_rag_is_a_wrapper_with_a_finally(self):
        src = self._source()
        self.assertIn("def _ask_rag_impl(", src,
                      "the body must live in _ask_rag_impl")
        wrapper = src.split("def _ask_rag_impl(")[0].split("def ask_rag(")[-1]
        self.assertIn("finally:", wrapper,
                      "ask_rag MUST release the chain in a finally")
        self.assertIn("rag_chain_ready", wrapper)

    def test_the_finally_is_unconditional(self):
        """No `if` may guard the release — that reintroduces the outage."""
        src = self._source()
        wrapper = src.split("def _ask_rag_impl(")[0].split("def ask_rag(")[-1]
        tail = wrapper.split("finally:", 1)[1]
        release = [ln.strip() for ln in tail.splitlines()
                   if "rag_chain_ready" in ln]
        self.assertTrue(release, "the finally must restore rag_chain_ready")
        for line in release:
            self.assertTrue(
                line.startswith("global_state.set_state("),
                "the release must be unconditional, not inside an if: %r" % line,
            )
        self.assertNotIn("if ", tail.split("global_state.set_state(")[0],
                         "nothing may gate the release of the chain")


class ChainBuildLatchTests(SimpleTestCase):
    """The REBUILD path — this is what actually caused the outage.

    ``ask_rag`` had been hardened long ago; ``setup_llm`` /
    ``setup_llm_with_context`` never were. They lowered the same process-global
    latch on entry and raised it only on SUCCESS, so a failed or raising
    rebuild stranded it. And because the latch is process-global while the
    rebuild lock is per-connection, refreshing the browser inherited the dead
    latch — which is why only killing the process fixed it.
    """

    def setUp(self):
        from agent.rag import factory as F

        self.F = F
        F.global_state.set_state(READY, False)

    def _ready(self):
        return self.F.global_state.get_state(READY)

    def test_setup_llm_releases_the_latch_when_the_build_RAISES(self):
        F = self.F
        original = F._setup_llm_impl

        def _boom(*a, **k):
            F.global_state.set_state(READY, False)     # what the real impl does
            raise RuntimeError("build blew up")

        F._setup_llm_impl = _boom
        try:
            with self.assertRaises(RuntimeError):
                F.setup_llm()
            self.assertTrue(self._ready(),
                            "a build that raises must NOT leave the chat dead")
        finally:
            F._setup_llm_impl = original

    def test_setup_llm_releases_the_latch_when_the_build_returns_None(self):
        F = self.F
        original = F._setup_llm_impl

        def _fails(*a, **k):
            F.global_state.set_state(READY, False)
            return None                                 # the `return None` paths

        F._setup_llm_impl = _fails
        try:
            self.assertIsNone(F.setup_llm())
            self.assertTrue(self._ready(),
                            "a failed build must leave the lane OPEN to retry")
        finally:
            F._setup_llm_impl = original

    def test_setup_llm_with_context_releases_the_latch_when_it_RAISES(self):
        F = self.F
        original = F._setup_llm_with_context_impl

        def _boom(*a, **k):
            F.global_state.set_state(READY, False)
            raise RuntimeError("contextual build blew up")

        F._setup_llm_with_context_impl = _boom
        try:
            with self.assertRaises(RuntimeError):
                F.setup_llm_with_context("some/path")
            self.assertTrue(self._ready())
        finally:
            F._setup_llm_with_context_impl = original

    def test_both_builders_are_wrappers_with_an_unconditional_finally(self):
        import inspect

        src = inspect.getsource(self.F)
        for public, impl in (("setup_llm", "_setup_llm_impl"),
                             ("setup_llm_with_context", "_setup_llm_with_context_impl")):
            self.assertIn("def %s(" % impl, src,
                          "%s must delegate to %s" % (public, impl))
            wrapper = src.split("def %s(" % impl)[0].split("\ndef %s(" % public)[-1]
            self.assertIn("finally:", wrapper,
                          "%s MUST release the chain in a finally" % public)
            self.assertIn("rag_chain_ready", wrapper)

    def test_prompt_only_fallback_returns_None_instead_of_raising(self):
        """The last-resort builder must degrade, never explode."""
        F = self.F
        original = F._build_prompt_only_chain_impl

        def _boom(*a, **k):
            raise RuntimeError("fallback blew up")

        F._build_prompt_only_chain_impl = _boom
        try:
            self.assertIsNone(F.build_prompt_only_chain({}, "template"))
        finally:
            F._build_prompt_only_chain_impl = original


class RebuildIsNonDestructiveTests(SimpleTestCase):
    """A failed self-heal must not destroy a chain that was working."""

    def test_consumer_never_nulls_the_chain_on_failure(self):
        import inspect

        from agent import consumers

        src = inspect.getsource(consumers)

        # Scope to the two REBUILD methods only. `self.rag_chain = None` is
        # legitimate in __init__ (initial value) and appears in a comment.
        rebuilds = {
            "setup_rag_chain":
                src.split("async def setup_rag_chain")[1]
                   .split("async def setup_contextual_rag_chain")[0],
            "setup_contextual_rag_chain":
                src.split("async def setup_contextual_rag_chain")[1]
                   .split("async def heartbeat")[0],
        }
        for name, body in rebuilds.items():
            self.assertNotIn(
                "self.rag_chain = None", body,
                "%s: a failed rebuild must NOT discard the chain that was "
                "already serving — that is what made the self-heal leave the "
                "chat WORSE than it found it" % name,
            )
            self.assertIn("_prev_chain", body,
                          "%s must keep the previous chain" % name)
            self.assertIn(
                "global_state.set_state('rag_chain_ready', self.rag_chain is not None)",
                body,
                "%s must restate the latch truthfully in its finally" % name,
            )


if __name__ == "__main__":
    unittest.main()
