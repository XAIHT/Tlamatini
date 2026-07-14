# ═══════════════════════════════════════════════════════════════════
#   ✦  T L A M A T I N I  ✦   —   "one who knows"
#
#   Created by  Angela López Mendoza   ·   @angelahack1
#   Developer · Architect · Creator of Tlamatini
#
#   Every line of this file was written by Angela López Mendoza.
# ═══════════════════════════════════════════════════════════════════
#   Tlamatini Author Banner — do not remove
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

    # ── THE 2026-07-14 BUG: a Cancel that the cancel handler itself un-does ──
    # consumers.py's `cancel-current` sets the flag (Step 1) and CLEARS it again a few
    # ms later (Step 8, so the chain rebuild is not aborted). Before the per-run epoch
    # latch, the still-running healer then read False forever, never raised
    # user_cancelled, and kept announcing "🔁 Tactic #N" — each of which put the
    # browser back into its busy state, flipping the Send button back to "Cancel" by
    # itself, over and over, until the end of time.

    def _latch_cancel_then_clear_like_consumers_does(self, uid):
        """Reproduce Step 1 → Step 8 VERBATIM."""
        from .cancellation import clear_cancel_generation, request_cancel_generation
        request_cancel_generation(uid)   # Step 1: latch this user's current run
        clear_cancel_generation()        # Step 8: lower the boolean (rebuild needs it)

    def test_cancel_survives_the_step8_clear_and_stops_the_ladder(self):
        from .cancellation import begin_llm_run, reset_for_tests
        uid = "cancel-user"
        reset_for_tests(uid)
        epoch = begin_llm_run(uid)
        try:
            llm = _ScriptedLLM([("hang", 30)])
            inv = SelfHealingInvoker(
                user_id="u1", run_user_id=uid, run_epoch=epoch,
                attempt_timeout=5, max_attempts=5,
            )
            threading.Timer(
                0.5, lambda: self._latch_cancel_then_clear_like_consumers_does(uid)
            ).start()
            t0 = time.time()
            with self.assertRaises(ModelStepUnrecoverable) as ctx:
                inv.invoke(llm, _msgs(), label="working")
            self.assertEqual(ctx.exception.reason, "user_cancelled")
            self.assertLess(time.time() - t0, 5,
                            "cancel must be honoured within a second even though Step 8 "
                            "already lowered the legacy boolean")
        finally:
            reset_for_tests(uid)

    def test_watchdog_timeout_after_a_cancel_does_not_announce_another_tactic(self):
        """The classification-free `timeout` branch was the real engine of the storm:
        it announced a new tactic and continued WITHOUT ever consulting cancellation."""
        from .cancellation import begin_llm_run, request_cancel_generation, reset_for_tests
        uid = "cancel-user-2"
        reset_for_tests(uid)
        epoch = begin_llm_run(uid)
        try:
            llm = _ScriptedLLM([("hang", 30)])
            inv = SelfHealingInvoker(
                user_id="u1", run_user_id=uid, run_epoch=epoch,
                attempt_timeout=2, max_attempts=8,
            )
            request_cancel_generation(uid)   # already cancelled before the step runs
            with self.assertRaises(ModelStepUnrecoverable) as ctx:
                inv.invoke(llm, _msgs(), label="working")
            self.assertEqual(ctx.exception.reason, "user_cancelled")
            self.assertFalse(
                any("Tactic" in e for e in inv.recovery_events),
                "a cancelled run must NEVER emit another 'Tactic' status frame — that "
                "frame is what re-armed the Cancel button in the browser",
            )
        finally:
            reset_for_tests(uid)

    def test_transient_error_after_a_cancel_is_not_retried_as_a_network_blip(self):
        from .cancellation import begin_llm_run, request_cancel_generation, reset_for_tests
        uid = "cancel-user-3"
        reset_for_tests(uid)
        epoch = begin_llm_run(uid)
        try:
            llm = _ScriptedLLM([("raise", TimeoutError("Read timed out")), ("ok", "SHOULD-NOT-GET-HERE")])
            inv = SelfHealingInvoker(
                user_id="u1", run_user_id=uid, run_epoch=epoch,
                attempt_timeout=2, max_attempts=8,
            )
            request_cancel_generation(uid)
            with self.assertRaises(ModelStepUnrecoverable) as ctx:
                inv.invoke(llm, _msgs(), label="working")
            self.assertEqual(ctx.exception.reason, "user_cancelled")
        finally:
            reset_for_tests(uid)

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
