"""Regression guards for the Exec Report SUCCESS/FAILURE verdict.

Every case here is a REAL payload observed in Angela's live install, and every
one of them was reported WRONGLY by an earlier revision. The column answers one
question and one only:

    "Did the tool do its job?"   -- NOT "was the input clean?"

Those are different questions, and conflating them is what made a LaTeXer
wizard show a wall of red while doing everything correctly.
"""
import json
import unittest

from agent.mcp_agent import MultiTurnToolAgentExecutor as EX


def verdict(payload):
    failed, why = EX._result_is_failure(json.dumps(payload))
    return ("FAILURE" if failed else "SUCCESS"), why


class LiveWizardPayloadTests(unittest.TestCase):
    """The six LaTeXer runs from the live wizard, 2026-08-05."""

    def test_zero_errors_as_a_string_is_not_a_failure(self):
        """THE original bug: ``bool("0")`` is True in Python.

        LaTeXer is the only agent that reports an ``errors`` COUNT, and the
        INI_SECTION header arrives as strings -- so a flawless build carrying
        ``errors: "0"`` was stamped FAILURE every single time.
        """
        got, _ = verdict({"action": "compile", "status": "compiled",
                          "success": "True", "errors": "0", "page_count": "1"})
        self.assertEqual(got, "SUCCESS")

    def test_a_linter_reporting_a_broken_document_succeeded(self):
        """Wizard STEP 4: validate_tex on a DELIBERATELY broken document.

        It found the 2 errors it was asked to find. The linter did its job
        perfectly; a red row here says the tool malfunctioned, which is false.
        """
        got, _ = verdict({"action": "validate_tex", "status": "invalid",
                          "success": "False", "errors": "2", "warnings": "3"})
        self.assertEqual(got, "SUCCESS")

    def test_a_failsafe_refusal_is_still_reported_as_not_done(self):
        """Wizard STEP 5: compile with no source at all.

        Refusing is CORRECT behaviour -- but the work the user asked for
        genuinely did not happen and no PDF exists, so red is the honest
        answer. This one is deliberately NOT whitewashed.
        """
        got, _ = verdict({"action": "compile", "status": "refused",
                          "success": "False", "errors": "0"})
        self.assertEqual(got, "FAILURE")

    def test_validate_and_compile_project_are_successes(self):
        for payload in (
            {"action": "validate", "status": "validated", "success": "True", "errors": "0"},
            {"action": "compile_project", "status": "compiled", "success": "True",
             "errors": "0", "page_count": "2"},
        ):
            self.assertEqual(verdict(payload)[0], "SUCCESS", payload)


class RealFailuresStayRedTests(unittest.TestCase):
    """The fix must not whitewash anything that genuinely went wrong."""

    def test_build_with_errors_stays_red(self):
        self.assertEqual(verdict({"status": "compiled_with_errors",
                                  "success": "False", "errors": "7"})[0], "FAILURE")

    def test_missing_engine_stays_red(self):
        self.assertEqual(verdict({"status": "engine_unavailable",
                                  "success": "False"})[0], "FAILURE")

    def test_editor_anchor_not_found_stays_red(self):
        """The requested edit did not happen -- that is a real failure."""
        self.assertEqual(verdict({"status": "not_found", "success": "False"})[0], "FAILURE")

    def test_success_as_the_string_False_is_caught(self):
        """``"False" is False`` evaluates False, so a real failure used to read
        as a success. The detector was broken in BOTH directions."""
        self.assertEqual(verdict({"status": "compiled", "success": "False"})[0], "FAILURE")

    def test_explicit_error_status_stays_red(self):
        for status in ("error", "failed", "failure"):
            self.assertEqual(verdict({"status": status})[0], "FAILURE", status)


class DiagnosticAgentsTests(unittest.TestCase):
    """Every read-only agent whose deliverable IS an adverse finding."""

    def test_analyzer_reporting_findings_succeeded(self):
        """Analyzer finding 12 security issues did its job."""
        self.assertEqual(verdict({"status": "findings", "total_findings": "12",
                                  "success": "False"})[0], "SUCCESS")

    def test_grepper_finding_nothing_succeeded(self):
        self.assertEqual(verdict({"status": "no_matches", "matches": "0"})[0], "SUCCESS")

    def test_grepper_finding_matches_succeeded(self):
        self.assertEqual(verdict({"status": "matches", "matches": "31"})[0], "SUCCESS")

    def test_structure_and_listing_succeed(self):
        for status in ("structure", "listed", "read", "analyzed", "clean", "valid"):
            self.assertEqual(verdict({"status": status})[0], "SUCCESS", status)


class ShapeRobustnessTests(unittest.TestCase):
    """Other result shapes must keep behaving."""

    def test_error_message_string_is_a_failure(self):
        got, why = verdict({"status": "ok", "error": "Missing package amsmath"})
        self.assertEqual(got, "FAILURE")
        self.assertIn("amsmath", why)

    def test_error_list_counts_its_members(self):
        got, why = verdict({"status": "ok", "errors": ["a", "b"]})
        self.assertEqual(got, "FAILURE")
        self.assertIn("2", why)

    def test_empty_error_list_is_not_a_failure(self):
        self.assertEqual(verdict({"status": "ok", "errors": []})[0], "SUCCESS")

    def test_plain_text_result_starting_with_error_is_a_failure(self):
        failed, _ = EX._result_is_failure("Error: the tool blew up")
        self.assertTrue(failed)

    def test_prose_merely_mentioning_error_is_not_a_failure(self):
        failed, _ = EX._result_is_failure("The build finished; no error was reported.")
        self.assertFalse(failed)

    def test_empty_result_is_not_a_failure(self):
        self.assertFalse(EX._result_is_failure("")[0])
        self.assertFalse(EX._result_is_failure(None)[0])


if __name__ == "__main__":
    unittest.main(verbosity=2)
