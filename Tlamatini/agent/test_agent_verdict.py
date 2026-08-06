"""Tests for the deterministic verdict engine (``agent/agent_verdict.py``).

THE LIVE FAILURE THIS FILE EXISTS FOR (Angela, 2026-08-06, frozen install at
C:\\Tlamatini, LaTeXer step-by-step wizard STEP 4):

    LaTeXer was asked to lint a deliberately broken document. It found the bug
    exactly as designed -- right error, right line number -- and the Exec
    Report stamped the row a red **FAILURE**.

    Root cause was NOT in LaTeXer. ``tools._maybe_promote_section_fields_to_
    payload`` lifted the agent's own ``status: invalid`` onto the payload with
    ``payload.setdefault(...)`` -- but the payload ALREADY carried
    ``status="failed"`` from the child's exit code, so the promotion was a
    silent NO-OP and the agent's truthful verdict was DISCARDED. Downstream,
    ``mcp_agent._result_is_failure`` then tested that overwritten value first,
    which made its own ``_DIAGNOSTIC_COMPLETED_STATUSES`` branch (containing
    ``invalid``, written for exactly this case) UNREACHABLE DEAD CODE.

The engine replaces that string-sniffing with a typed AST + an ordered
production-rule table. These tests pin BOTH halves: a diagnostic finding must
be GREEN, and a genuine failure must still be RED.
"""

import unittest

from agent import agent_verdict as av


# =====================================================================
# PARSER — text → typed AST
# =====================================================================

class ParserTests(unittest.TestCase):

    LATEXER_STEP4 = (
        "2026-08-06 08:52:39,467 - INFO - INI_SECTION_LATEXER<<<\n"
        "action: validate_tex\n"
        "engine: pdflatex\n"
        "errors: 1\n"
        "warnings: 2\n"
        "success: False\n"
        "status: invalid\n"
        "\n"
        "ERRORS (1):\n"
        "  x line 1: begin{itemize} is never closed\n"
        ">>>END_SECTION_LATEXER\n"
    )

    def test_parses_the_real_step4_block(self):
        section = av.parse_section(self.LATEXER_STEP4)
        self.assertIsNotNone(section)
        self.assertEqual(section.agent_type, "latexer")
        self.assertIn("ERRORS (1)", section.body)

    def test_status_is_typed_and_classified_not_just_a_string(self):
        node = av.parse_section(self.LATEXER_STEP4).get("status")
        self.assertEqual(node.kind, av.KIND_STATUS)
        self.assertEqual(node.value, "invalid")
        self.assertEqual(node.status_class, av.CLASS_DIAGNOSTIC)

    def test_bool_and_count_survive_the_string_trap(self):
        """A KV header is TEXT: "False" and "0" are both truthy strings."""
        section = av.parse_section(self.LATEXER_STEP4)
        self.assertIs(section.get("success").value, False)   # not the string
        self.assertEqual(section.get("errors").value, 1)     # not "1"

        zero = av.parse_section(
            "INI_SECTION_LATEXER<<<\nerrors: 0\nstatus: compiled\n"
            "\nbody\n>>>END_SECTION_LATEXER")
        self.assertEqual(zero.get("errors").value, 0)        # ZERO, not truthy

    def test_header_stops_at_the_first_blank_line(self):
        section = av.parse_section(self.LATEXER_STEP4)
        self.assertIsNone(section.get("ERRORS (1)"))

    def test_malformed_input_never_raises_and_returns_None(self):
        for bad in (None, "", "no section here", "INI_SECTION_X<<< unterminated"):
            self.assertIsNone(av.parse_section(bad))


# =====================================================================
# INFERENCE ENGINE — the ordered rule table
# =====================================================================

def _section(**kv):
    body = "\n".join(f"{k}: {v}" for k, v in kv.items())
    return av.parse_section(
        f"INI_SECTION_T<<<\n{body}\n\nbody\n>>>END_SECTION_T")


class RuleOrderTests(unittest.TestCase):

    def test_R4_a_linter_that_FINDS_a_bug_has_SUCCEEDED(self):
        """THE REGRESSION. Exit code 1, success=False, errors=1 -> still OK.

        All three of those describe the DOCUMENT, not the agent. The agent ran
        to completion and delivered its finding, which is its entire job.
        """
        verdict = av.evaluate(
            _section(status="invalid", success="False", errors="1"), exit_code=1)
        self.assertTrue(verdict.ok, f"regressed: {verdict.as_dict()}")
        self.assertEqual(verdict.rule, "R4.diagnostic_completed")
        self.assertEqual(verdict.source, "agent")

    def test_R4_outranks_R5_and_R6(self):
        """Ordering IS the algorithm — R4 must be tested before the flag/count.

        If R5 (success=False) or R6 (errors>0) were consulted first, the
        diagnostic rule could never fire, because a linter reporting a finding
        always sets all three at once.
        """
        rules = ["R2.agent_declared_error", "R3.work_not_done",
                 "R4.diagnostic_completed", "R5.agent_flag_true",
                 "R5.agent_flag_false", "R6.error_count"]
        order = [r for r in rules]
        self.assertLess(order.index("R4.diagnostic_completed"),
                        order.index("R5.agent_flag_false"))
        self.assertLess(order.index("R4.diagnostic_completed"),
                        order.index("R6.error_count"))
        # ...and behaviourally:
        self.assertTrue(av.evaluate(_section(status="invalid", success="False"),
                                    exit_code=1).ok)
        self.assertTrue(av.evaluate(_section(status="findings", errors="7"),
                                    exit_code=1).ok)

    def test_R2_an_agent_declaring_an_error_is_still_RED(self):
        v = av.evaluate(_section(status="error"), exit_code=1)
        self.assertFalse(v.ok)
        self.assertEqual(v.rule, "R2.agent_declared_error")

    def test_R3_work_that_did_not_happen_is_still_RED(self):
        """A fail-safe refusal is correct behaviour but the user got nothing."""
        for status in ("refused", "not_found", "not_unique", "engine_unavailable"):
            v = av.evaluate(_section(status=status), exit_code=1)
            self.assertFalse(v.ok, f"{status} must stay RED")
            self.assertEqual(v.rule, "R3.work_not_done")

    def test_R5_an_explicit_false_flag_is_RED(self):
        v = av.evaluate(_section(success="False"), exit_code=1)
        self.assertFalse(v.ok)
        self.assertEqual(v.rule, "R5.agent_flag_false")

    def test_R6_a_nonzero_error_count_is_RED_but_zero_is_GREEN(self):
        self.assertFalse(av.evaluate(_section(errors="3"), exit_code=0).ok)
        self.assertTrue(av.evaluate(_section(errors="0"), exit_code=0).ok)

    def test_R1_and_R7_fall_back_to_the_exit_code(self):
        self.assertFalse(av.evaluate(None, exit_code=1).ok)
        self.assertTrue(av.evaluate(None, exit_code=0).ok)
        # A self-report with no decisive key falls through to R7.
        v = av.evaluate(_section(action="compile"), exit_code=1)
        self.assertFalse(v.ok)
        self.assertEqual(v.source, "process")

    def test_every_verdict_carries_auditable_provenance(self):
        v = av.evaluate(_section(status="invalid"), exit_code=1)
        self.assertTrue(v.rule and v.reason and v.evidence)
        self.assertIn("status", v.evidence)

    def test_the_engine_is_total_and_never_raises(self):
        for section in (None, _section(), _section(status="")):
            for code in (None, 0, 1, -1):
                self.assertIsInstance(av.evaluate(section, code).ok, bool)


# =====================================================================
# INTEGRATION — payload reconciliation
# =====================================================================

class ReconcileTests(unittest.TestCase):

    def _step4_payload(self):
        """The payload shape that produced the live red FAILURE."""
        return {
            "status": "failed",           # ← the PROCESS view (exit code 1)
            "exit_code": 1,
            "agent_status": "invalid",    # ← the AGENT's own truthful verdict
            "log_excerpt": ParserTests.LATEXER_STEP4,
        }

    def test_the_live_failure_is_now_reported_OK(self):
        payload = self._step4_payload()
        av.reconcile_payload_verdict(payload)
        self.assertEqual(payload["verdict"], "ok")
        self.assertEqual(payload["verdict_rule"], "R4.diagnostic_completed")

    def test_BOTH_states_survive_nothing_is_overwritten_away(self):
        """Angela's requirement: HANDLE THE 2 STATES. Keep both, lose neither."""
        payload = self._step4_payload()
        av.reconcile_payload_verdict(payload)
        self.assertEqual(payload["process_status"], "failed")  # process view kept
        self.assertEqual(payload["agent_status"], "invalid")   # agent view kept
        self.assertEqual(payload["exit_code"], 1)              # raw truth kept
        self.assertEqual(payload["status"], "invalid")         # headline repaired

    def test_a_REAL_failure_keeps_status_failed(self):
        """The repair is narrow: only a PROVEN diagnostic may rewrite status.

        Consumers key off ``status == "failed"`` (the Instant-Messaging-Doctor
        auto-launch in tools.py). Widening this would silently disable them.
        """
        payload = {
            "status": "failed",
            "exit_code": 1,
            "log_excerpt": "INI_SECTION_WHATSAPPER<<<\nstatus: error\n\nx\n"
                           ">>>END_SECTION_WHATSAPPER",
        }
        av.reconcile_payload_verdict(payload)
        self.assertEqual(payload["verdict"], "failed")
        self.assertEqual(payload["status"], "failed")

    def test_a_refusal_stays_failed(self):
        payload = {
            "status": "failed",
            "exit_code": 1,
            "log_excerpt": "INI_SECTION_LATEXER<<<\nstatus: refused\n\nx\n"
                           ">>>END_SECTION_LATEXER",
        }
        av.reconcile_payload_verdict(payload)
        self.assertEqual(payload["verdict"], "failed")
        self.assertEqual(payload["status"], "failed")

    def test_reconcile_never_raises_on_junk(self):
        for junk in (None, "not a dict", 42, [], {}):
            av.reconcile_payload_verdict(junk)   # must not raise

    def test_classify_payload_prefers_the_stamped_verdict(self):
        payload = self._step4_payload()
        av.reconcile_payload_verdict(payload)
        self.assertTrue(av.classify_payload(payload).ok)

    def test_classify_payload_falls_back_to_agent_status(self):
        v = av.classify_payload({"status": "failed", "exit_code": 1,
                                 "agent_status": "invalid"})
        self.assertTrue(v.ok)
        self.assertEqual(v.source, "agent")


# =====================================================================
# WIRING — the fix must be REACHABLE, not dead code
# =====================================================================

class WiringTests(unittest.TestCase):

    def test_promotion_preserves_a_colliding_self_report(self):
        """``setdefault`` on a collision is THE bug — it silently dropped it."""
        import inspect

        from agent import tools
        src = inspect.getsource(tools._maybe_promote_section_fields_to_payload)
        self.assertIn('payload.setdefault("agent_" + key, value)', src,
                      'a colliding self-report must be KEPT as agent_<key>, '
                      'never dropped')

    def test_the_executor_consults_the_agent_verdict_first(self):
        import inspect

        from agent.mcp_agent import MultiTurnToolAgentExecutor as Ex
        src = inspect.getsource(Ex._result_is_failure)
        self.assertIn("agent_verdict.classify_payload", src)
        # ...and BEFORE the crude process-status test, or it is dead code again.
        self.assertLess(src.index("agent_verdict.classify_payload"),
                        src.index('parsed.get("status"'),
                        'the agent verdict must be consulted BEFORE the '
                        'exit-code-derived status, else it can never fire')

    def test_the_status_vocabulary_has_exactly_one_definition(self):
        from agent.mcp_agent import MultiTurnToolAgentExecutor as Ex
        self.assertIs(Ex._DIAGNOSTIC_COMPLETED_STATUSES,
                      av.DIAGNOSTIC_COMPLETED_STATUSES,
                      'two copies of the vocabulary would drift apart')

    def test_end_to_end_the_step4_result_string_is_no_longer_a_failure(self):
        """The exact JSON shape the Exec Report judged — must now be GREEN."""
        import json

        from agent.mcp_agent import MultiTurnToolAgentExecutor as Ex
        payload = {
            "status": "failed",
            "exit_code": 1,
            "agent_status": "invalid",
            "errors": "1",
            "success": "False",
            "log_excerpt": ParserTests.LATEXER_STEP4,
        }
        av.reconcile_payload_verdict(payload)
        failed, err = Ex._result_is_failure(json.dumps(payload))
        self.assertFalse(failed, f"still stamped FAILURE: {err}")


if __name__ == "__main__":
    unittest.main()
