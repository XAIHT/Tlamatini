# ═══════════════════════════════════════════════════════════════════
#   ✦  T L A M A T I N I  ✦   —   "one who knows"
#
#   Created by  Angela López Mendoza   ·   @angelahack1
#   Developer · Architect · Creator of Tlamatini
#
#   Every line of this file was written by Angela López Mendoza.
# ═══════════════════════════════════════════════════════════════════
#   Tlamatini Author Banner — do not remove
"""Regression tests for the PER-RUN cancellation latch (agent/cancellation.py).

THE BUG (Angela, 2026-07-14): cancelling a Multi-Turn run did not cancel it. A few
seconds later Tlamatini resumed, flipped the Send button back to "Cancel" by itself,
and did that forever. Cancellation was a process-global BOOLEAN that the cancel
handler itself lowered again ~20 ms after raising it (consumers Step 8, which the
chain rebuild needs), and that ``ask_rag`` lowered a second time on the next request.

Every test below pins one leg of the fix. ``test_step8_race_*`` and
``test_new_request_race_*`` reproduce the two clears VERBATIM.
"""

from django.test import SimpleTestCase

from .cancellation import (
    begin_llm_run,
    cancelled_run_epoch,
    clear_cancel_generation,
    current_run_epoch,
    is_generation_cancelled,
    is_run_cancelled,
    request_cancel_generation,
    reset_for_tests,
)

ALICE = 4242
BOB = 9999


class CancellationLatchTests(SimpleTestCase):
    def setUp(self):
        reset_for_tests(ALICE)
        reset_for_tests(BOB)

    def tearDown(self):
        # MANDATORY: the latch is a permanent high-water mark. A test that cancels
        # without resetting would leave every later test's run born-cancelled.
        reset_for_tests(ALICE)
        reset_for_tests(BOB)

    # ── epochs ──────────────────────────────────────────────────────────────
    def test_epochs_increase_per_user(self):
        self.assertEqual(begin_llm_run(ALICE), 1)
        self.assertEqual(begin_llm_run(ALICE), 2)
        self.assertEqual(current_run_epoch(ALICE), 2)
        # Bob's counter is independent.
        self.assertEqual(begin_llm_run(BOB), 1)

    def test_a_fresh_run_is_not_cancelled(self):
        epoch = begin_llm_run(ALICE)
        self.assertFalse(is_run_cancelled(ALICE, epoch))

    # ── the cancel latches THIS run ─────────────────────────────────────────
    def test_cancel_latches_the_running_run(self):
        epoch = begin_llm_run(ALICE)
        request_cancel_generation(ALICE)
        self.assertTrue(is_run_cancelled(ALICE, epoch))
        self.assertEqual(cancelled_run_epoch(ALICE), epoch)

    def test_step8_race__clearing_the_boolean_does_NOT_uncancel_the_run(self):
        """THE BUG, verbatim: consumers cancel-current Step 1 → Step 8.

        Step 8 lowers the boolean a few ms later so the chain rebuild can proceed.
        Before the fix, that lower was a full un-cancel and the still-running
        executor never saw the Cancel again.
        """
        epoch = begin_llm_run(ALICE)
        request_cancel_generation(ALICE)   # Step 1
        clear_cancel_generation()          # Step 8 (a few milliseconds later)
        self.assertTrue(
            is_run_cancelled(ALICE, epoch),
            "the cancelled run MUST stay cancelled after Step 8 lowers the boolean",
        )

    def test_new_request_race__a_later_run_does_NOT_uncancel_the_old_one(self):
        """THE OTHER CLEAR: ask_rag used to clear the boolean at the top of every
        request, so the user simply typing again resurrected the zombie run."""
        old = begin_llm_run(ALICE)
        request_cancel_generation(ALICE)
        clear_cancel_generation()
        new = begin_llm_run(ALICE)         # the user sends a new message
        self.assertGreater(new, old)
        self.assertTrue(is_run_cancelled(ALICE, old), "the OLD run stays cancelled")
        self.assertFalse(is_run_cancelled(ALICE, new), "the NEW run must run normally")

    def test_cancel_is_permanent(self):
        epoch = begin_llm_run(ALICE)
        request_cancel_generation(ALICE)
        for _ in range(5):
            clear_cancel_generation()
        self.assertTrue(is_run_cancelled(ALICE, epoch))

    # ── no collateral damage across users (TeleTlamatini + a browser) ────────
    def test_cancelling_alice_never_cancels_bob__bob_started_first(self):
        bob = begin_llm_run(BOB)
        alice = begin_llm_run(ALICE)
        request_cancel_generation(ALICE)
        self.assertTrue(is_run_cancelled(ALICE, alice))
        self.assertFalse(is_run_cancelled(BOB, bob),
                         "a browser Cancel must NEVER kill a concurrent TeleTlamatini run")

    def test_cancelling_alice_never_cancels_bob__bob_started_last(self):
        alice = begin_llm_run(ALICE)
        bob = begin_llm_run(BOB)
        request_cancel_generation(ALICE)
        self.assertTrue(is_run_cancelled(ALICE, alice))
        self.assertFalse(is_run_cancelled(BOB, bob))

    # ── fail-open: a DROPPED epoch must mean "not cancelled" ────────────────
    def test_missing_epoch_is_never_cancelled(self):
        """If cancel_run_epoch is ever dropped by a payload whitelist, a missing epoch
        MUST read as NOT cancelled. The opposite (treating it as cancelled) would make
        EVERY request after the first-ever cancel self-cancel on arrival."""
        begin_llm_run(ALICE)
        request_cancel_generation(ALICE)
        self.assertFalse(is_run_cancelled(ALICE, None))
        self.assertFalse(is_run_cancelled(ALICE, 0))
        self.assertFalse(is_run_cancelled(ALICE, "not-a-number"))

    def test_unknown_user_is_never_cancelled(self):
        self.assertFalse(is_run_cancelled("nobody", 1))

    # ── the legacy boolean still works for the identity-less callers ────────
    def test_is_generation_cancelled_falls_back_to_the_boolean(self):
        request_cancel_generation(None)      # no user id → boolean only
        self.assertTrue(is_generation_cancelled(None, None))
        clear_cancel_generation()
        self.assertFalse(is_generation_cancelled(None, None))

    def test_begin_llm_run_lowers_the_boolean(self):
        request_cancel_generation(None)
        self.assertTrue(is_generation_cancelled())
        begin_llm_run(ALICE)
        self.assertFalse(is_generation_cancelled())


class CancelEpochPlumbingContractTests(SimpleTestCase):
    """``cancel_run_epoch`` must survive EVERY payload hop.

    Drop it at any one of them and the executor's run_epoch is None, every cancel
    guard silently no-ops, and the never-ending "it starts again by itself" loop is
    back. Source-level assertions, in the same style as the existing
    ``exec_report_enabled`` drop-on-rebuild guard.
    """

    def _source(self, *parts) -> str:
        import os
        here = os.path.dirname(os.path.abspath(__file__))
        with open(os.path.join(here, *parts), "r", encoding="utf-8") as fh:
            return fh.read()

    def test_interface_puts_the_epoch_in_the_payload(self):
        src = self._source("rag", "interface.py")
        self.assertIn('payload["cancel_run_epoch"] = _run_epoch', src)

    def test_unified_chain_rebuild_whitelist_keeps_the_epoch(self):
        src = self._source("rag", "chains", "unified.py")
        self.assertIn('"cancel_run_epoch": payload.get("cancel_run_epoch")', src)
        # BOTH chains' executor sub-payloads + the rebuild whitelist = 3 occurrences.
        self.assertGreaterEqual(
            src.count('"cancel_run_epoch": payload.get("cancel_run_epoch")'), 3,
            "the epoch must be in the rebuild whitelist AND both executor sub-payloads",
        )

    def test_capability_executor_forwards_the_epoch(self):
        src = self._source("mcp_agent.py")
        self.assertIn('executor_payload["cancel_run_epoch"] = payload.get("cancel_run_epoch")', src)

    def test_executor_checks_cancellation_in_its_loops(self):
        src = self._source("mcp_agent.py")
        self.assertIn("def _run_cancelled(self)", src)
        # loop-top + per-tool + pre-invoke guards.
        self.assertGreaterEqual(
            src.count("if self._run_cancelled():"), 3,
            "the tool loop must check cancellation between steps AND before each tool",
        )

    def test_consumer_mints_and_forwards_the_epoch(self):
        src = self._source("consumers.py")
        self.assertIn("run_epoch = begin_llm_run(broker_key)", src)
        self.assertIn('"cancel_run_epoch": run_epoch,', src)

    def test_cancel_handler_latches_per_user_and_revokes_the_emitter(self):
        src = self._source("consumers.py")
        self.assertIn("request_cancel_generation(_cancel_key)", src)
        self.assertIn("unregister_status_broadcaster(_cancel_key, self._status_emit)", src)

    def test_retry_wrapper_is_cancel_aware(self):
        """_invoke_unified_agent_with_retry re-runs the WHOLE executor (re-executing
        tools) on a transient error — it must never do that for a cancelled run."""
        src = self._source("rag", "chains", "unified.py")
        self.assertIn("if is_run_cancelled(_uid, _epoch):", src)

    def test_frontend_latch_exists_and_is_let(self):
        src = self._source("static", "agent", "js", "agent_page_state.js")
        self.assertIn("let userCancelledRun = false;", src)
        self.assertNotIn("const userCancelledRun", src)

    def test_frontend_ignores_late_tactic_frames_after_a_cancel(self):
        src = self._source("static", "agent", "js", "agent_page_chat.js")
        self.assertIn("isSelfHealingStatusMessage(message) && userCancelledRun", src)

    def test_frontend_sets_and_clears_the_latch(self):
        src = self._source("static", "agent", "js", "agent_page_init.js")
        self.assertIn("userCancelledRun = true;", src)
        self.assertIn("userCancelledRun = false;", src)
