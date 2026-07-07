"""
Deterministic proof for the self-healing, NEVER-HANGING multi-turn redesign
(Angela, 2026-07-06). These do NOT need a real network failure — a scripted fake
model reproduces a hang / transient error on demand, so the watchdog + rotating
tactics + user-cancel behaviour is verified in seconds.

Run: python manage.py test agent.test_self_healing
"""

import threading
import time
import unittest

from langchain_core.messages import HumanMessage, SystemMessage

from agent.global_state import global_state
from agent.self_healing import (
    ModelStepUnrecoverable,
    SelfHealingInvoker,
    is_transient_error,
    recovery_preamble,
    register_status_broadcaster,
    unregister_status_broadcaster,
)


class _ScriptedLLM:
    """Fake chat model whose .invoke() follows a per-call script of behaviours:
    ('ok', payload) → returns payload; ('raise', exc) → raises exc;
    ('hang', seconds) → sleeps that long (to exercise the watchdog). The last
    scripted behaviour repeats for any further calls."""

    def __init__(self, script):
        self.script = list(script)
        self.calls = 0

    def invoke(self, messages):
        i = self.calls
        self.calls += 1
        behaviour, arg = self.script[min(i, len(self.script) - 1)]
        if behaviour == "ok":
            return arg
        if behaviour == "raise":
            raise arg
        if behaviour == "hang":
            time.sleep(arg)
            return "late-should-have-been-abandoned"
        raise AssertionError(f"unknown behaviour {behaviour}")


def _msgs():
    return [SystemMessage(content="system"), HumanMessage(content="hello")]


class SelfHealingInvokerTests(unittest.TestCase):
    def setUp(self):
        global_state.set_state("cancel_generation", None)
        self.events = []
        register_status_broadcaster("u1", lambda t: self.events.append(t))

    def tearDown(self):
        unregister_status_broadcaster("u1")
        global_state.set_state("cancel_generation", None)

    def test_transient_error_then_success_is_announced(self):
        llm = _ScriptedLLM([("raise", TimeoutError("Read timed out")), ("ok", "ANSWER")])
        inv = SelfHealingInvoker(user_id="u1", attempt_timeout=2, max_attempts=5)
        out = inv.invoke(llm, _msgs(), label="working")
        self.assertEqual(out, "ANSWER")
        self.assertTrue(inv.recovered)
        # The user was told about the transient error AND the recovery.
        self.assertTrue(any("transient" in e.lower() for e in self.events))
        self.assertTrue(any("✅" in e for e in self.events))

    def test_hang_is_abandoned_by_watchdog_and_never_hangs(self):
        # First call hangs 30s; the 2s watchdog MUST abandon it and switch
        # tactics — the whole test must finish in a handful of seconds, proving
        # Tlamatini never waits on a hung call.
        llm = _ScriptedLLM([("hang", 30), ("ok", "RECOVERED")])
        inv = SelfHealingInvoker(user_id="u1", attempt_timeout=2, max_attempts=5)
        t0 = time.time()
        out = inv.invoke(llm, _msgs(), label="working")
        elapsed = time.time() - t0
        self.assertEqual(out, "RECOVERED")
        self.assertLess(elapsed, 12, "watchdog must abandon the hang, not wait 30s")
        self.assertTrue(any(("abandon" in e.lower() or "too long" in e.lower()) for e in self.events))

    def test_user_cancel_stops_promptly_and_gracefully(self):
        llm = _ScriptedLLM([("hang", 30)])
        inv = SelfHealingInvoker(user_id="u1", attempt_timeout=5, max_attempts=5)
        threading.Timer(0.5, lambda: global_state.set_state("cancel_generation", True)).start()
        t0 = time.time()
        with self.assertRaises(ModelStepUnrecoverable) as ctx:
            inv.invoke(llm, _msgs(), label="working")
        self.assertEqual(ctx.exception.reason, "user_cancelled")
        self.assertLess(time.time() - t0, 5, "cancel must be honoured within a second, even mid-hang")

    def test_nontransient_error_is_raised_immediately_not_masked(self):
        boom = ValueError("bad tool schema")
        llm = _ScriptedLLM([("raise", boom)])
        inv = SelfHealingInvoker(user_id="u1", attempt_timeout=2, max_attempts=5)
        with self.assertRaises(ValueError):
            inv.invoke(llm, _msgs(), label="working")

    def test_escalates_to_plain_summary_tactic_when_bound_keeps_failing(self):
        # bound_llm always transient-errors; the tool-less plain_llm works. She
        # should escalate through tactics and recover via the plain-summary one.
        bad = _ScriptedLLM([("raise", TimeoutError("connection reset"))])
        good = _ScriptedLLM([("ok", "PLAIN-SUMMARY")])
        inv = SelfHealingInvoker(user_id="u1", plain_llm=good, attempt_timeout=2, max_attempts=6)
        out = inv.invoke(bad, _msgs(), label="working")
        self.assertEqual(out, "PLAIN-SUMMARY")
        self.assertTrue(any("summariz" in e.lower() for e in self.events))
        # And the user saw MULTIPLE distinct tactics announced.
        self.assertGreaterEqual(len([e for e in self.events if "Tactic" in e]), 2)

    def test_recovery_preamble_render(self):
        self.assertEqual(recovery_preamble([]), "")
        p = recovery_preamble(["hit an error", "recovered"])
        self.assertIn("SELF-HEALING NOTE", p)
        self.assertIn("- hit an error", p)

    def test_transient_classification(self):
        self.assertTrue(is_transient_error(TimeoutError("Read timed out")))
        self.assertTrue(is_transient_error(Exception("status code: 503 service unavailable")))
        self.assertTrue(is_transient_error(Exception("Connection reset by peer")))
        self.assertFalse(is_transient_error(ValueError("bad key")))
        self.assertFalse(is_transient_error(KeyError("missing")))


if __name__ == "__main__":
    unittest.main()
