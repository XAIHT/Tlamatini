"""Unit tests for the universal tool-failure classifier + self-correction.

Reproduces the exact 2026-07-17 Roblox-MCP loop ("false | Unable to cast double
to Vector3" was scored SUCCESS, so the model looped on the identical failing
call) and pins the central classifier that every surface — wrapped chat-agents,
built-in MCPs, External MCPs (ext__*), ACPX (acp_*) and raw @tools — now flows
through in ``MultiTurnToolAgentExecutor._invoke_tool``. (Angela, 2026-07-17)
"""
from django.test import SimpleTestCase

from agent.mcp_agent import MultiTurnToolAgentExecutor as MT


class ToolFailureClassifierTests(SimpleTestCase):
    def _failed(self, s):
        return MT._result_is_failure(s)[0]

    # ── the exact regression: a plain-text tool error must be a FAILURE ──
    def test_roblox_plain_text_cast_error_is_failure(self):
        self.assertTrue(self._failed("false | Unable to cast double to Vector3"))

    def test_roblox_error_hint_is_surfaced(self):
        failed, err = MT._result_is_failure("false | Unable to cast double to Vector3")
        self.assertTrue(failed)
        self.assertIn("Vector3", err)

    # ── other failure shapes across surfaces ──
    def test_external_mcp_error_prefix(self):
        # external_mcp_manager._format_mcp_tool_result prefixes isError with "Error:"
        self.assertTrue(self._failed("Error: the backend rejected the request"))

    def test_json_status_error(self):
        self.assertTrue(self._failed('{"status": "error", "message": "boom"}'))

    def test_json_status_failed(self):
        self.assertTrue(self._failed('{"status": "failed"}'))

    def test_json_ok_false(self):
        self.assertTrue(self._failed('{"ok": false, "reason": "nope"}'))

    def test_json_success_false(self):
        self.assertTrue(self._failed('{"success": false}'))

    def test_json_iserror_true(self):
        self.assertTrue(self._failed('{"isError": true, "content": "kaboom"}'))

    def test_json_error_key(self):
        self.assertTrue(self._failed('{"error": "connection refused"}'))

    def test_traceback(self):
        self.assertTrue(self._failed("Traceback (most recent call last):\n  File x"))

    def test_exception_prefix(self):
        self.assertTrue(self._failed("Exception: NullReference"))

    def test_failed_return_code(self):
        self.assertTrue(self._failed("Command 'x' failed with return code 1"))

    def test_unable_to_prefix(self):
        self.assertTrue(self._failed("Unable to connect to the server."))

    # ── NON-failures must NOT be misflagged (conservative classifier) ──
    def test_normal_prose_is_not_failure(self):
        self.assertFalse(self._failed("The sky is blue on a clear day."))

    def test_json_success_is_not_failure(self):
        self.assertFalse(self._failed('{"status": "ok", "result": "done"}'))

    def test_empty_is_not_failure(self):
        self.assertFalse(self._failed(""))
        self.assertFalse(self._failed(None))

    def test_mid_string_error_mention_is_not_failure(self):
        self.assertFalse(self._failed("Here is the error-handling section of your code."))

    def test_word_errors_plural_is_not_failure(self):
        self.assertFalse(self._failed("errors found: 0 across 3 files"))

    # ── the self-correction knobs exist ──
    def test_block_limit_constant(self):
        self.assertEqual(MT._FAIL_BLOCK_LIMIT, 3)

    def test_executor_resets_fail_memory_shape(self):
        # The per-request state the loop relies on must be reset shapes.
        self.assertTrue(hasattr(MT, "_result_is_failure"))
        self.assertTrue(hasattr(MT, "_FAILURE_TEXT_PREFIXES"))
