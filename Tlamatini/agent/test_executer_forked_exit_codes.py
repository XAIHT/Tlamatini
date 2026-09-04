# ═══════════════════════════════════════════════════════════════════
#   ✦  T L A M A T I N I  ✦   —   "one who knows"
#
#   Created by  Angela López Mendoza   ·   @angelahack1
#   Developer · Architect · Creator of Tlamatini
# ═══════════════════════════════════════════════════════════════════
#   Tlamatini Author Banner — do not remove (releases scrub the name automatically)
"""A forked-window failure must SAY WHAT IT WAS.

THE INCIDENT (Angela, 2026-08-30). `npm run lint` was launched through the
Executer with `execute_forked_window: true`. The agent came back after ~2 s
with one line:

    ❌ Script execution failed with exit code: 3221225786

That number is **0xC000013A — STATUS_CONTROL_C_EXIT**: the status Windows gives
a process whose CONSOLE received Ctrl+C or was closed. The command was not
wrong; something interrupted the console. But the log said "Script execution
failed" and nothing else, so the reader went hunting for a bug in npm/eslint
that was never there and lost a debugging session to a false premise.

The interruption itself did NOT reproduce — the byte-identical command passed
on every later run. So this file does not pretend to fix a phantom. It fixes
the thing that was genuinely, reproducibly broken: **the report**. Two defects,
both real:

1. **An NTSTATUS was printed as a bare decimal.** Nobody decodes 3221225786 by
   hand. `_describe_exit_code` now names it.
2. **Two different outcomes were collapsed into one sentence.** The exit code
   can come from the SENTINEL (the wrapper wrote it *after* the script ran — so
   it is the script's own verdict) or from `process.poll()` (the console died
   FIRST — the script never reported, and its real result is UNKNOWN). Calling
   the second one "Script execution failed" blames a command for a window
   someone closed. `code_source` keeps them apart.

FAIL-SAFE IS UNCHANGED: every non-zero code is still a FAILURE. Being clearer
about *which* failure must never become "and therefore it is fine".

This is the same lesson as the db_guard removal: before you build a fix, read
the mechanism and be sure the premise is real. A misleading message is a bug
worth fixing; an imaginary root cause is not.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

from django.test import SimpleTestCase

_EXECUTER_PY = Path(__file__).resolve().parent / "agents" / "executer" / "executer.py"
_LIFTED_NAMES = ("_WINDOWS_STATUS_NAMES", "_STATUS_CONTROL_C_EXIT",
                 "_describe_exit_code", "_is_console_interruption")

CTRL_C = 3221225786          # 0xC000013A


def _lift_exit_code_helpers() -> dict:
    """AST-lift the helpers out of executer.py WITHOUT importing the agent.

    A pool agent is a standalone SCRIPT, not a module: importing it truncates
    its log file and installs a ``subprocess.Popen`` monkey-patch. Same trick
    ``test_grepper_encodings.py`` and ``test_temp_dir_policy.py`` use.
    """
    tree = ast.parse(_EXECUTER_PY.read_text(encoding="utf-8"))
    picked: list = []
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name in _LIFTED_NAMES:
            picked.append(node)
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id in _LIFTED_NAMES:
                    picked.append(node)
                    break
    namespace: dict = {}
    block = ast.Module(body=picked, type_ignores=[])
    exec(compile(block, "<executer-exit-codes>", "exec"), namespace)  # noqa: S102
    return namespace


_NS = _lift_exit_code_helpers()
_describe_exit_code = _NS["_describe_exit_code"]
_is_console_interruption = _NS["_is_console_interruption"]
_SOURCE = _EXECUTER_PY.read_text(encoding="utf-8")


class ExitCodeIsReadableTests(SimpleTestCase):
    """The number a human reads must carry its own meaning."""

    def test_the_ctrl_c_status_is_named_not_left_as_a_decimal(self):
        described = _describe_exit_code(CTRL_C)
        self.assertIn("3221225786", described,
                      "the raw code must still be shown - it is what the user sees "
                      "elsewhere and what they will search for")
        self.assertIn("0xC000013A", described)
        self.assertIn("STATUS_CONTROL_C_EXIT", described)
        self.assertIn("Ctrl+C", described,
                      "the line must say IN WORDS what happened, not just name a "
                      "constant nobody knows either")

    def test_both_decimal_forms_are_shown_for_a_signed_status(self):
        # cmd.exe reported this one SIGNED live, while npm and the original
        # incident report showed it UNSIGNED. If the log prints only one form,
        # grepping for the number you actually saw finds nothing.
        described = _describe_exit_code(-1073741510)
        self.assertIn("-1073741510", described)
        self.assertIn("3221225786", described,
                      "the unsigned form must appear too, or a search for the "
                      "number the user saw elsewhere will miss this line")

    def test_a_positive_code_is_not_printed_twice(self):
        described = _describe_exit_code(CTRL_C)
        self.assertNotIn("3221225786 / 3221225786", described)

    def test_success_is_labelled(self):
        self.assertEqual(_describe_exit_code(0), "0 (success)")

    def test_an_ordinary_failure_stays_a_plain_number(self):
        # Exit 1 from a linter means "it found problems". Dressing that up as an
        # NTSTATUS would be its own kind of lying.
        self.assertEqual(_describe_exit_code(1), "1")
        self.assertEqual(_describe_exit_code(2), "2")

    def test_an_unlisted_ntstatus_is_still_flagged_as_one(self):
        described = _describe_exit_code(0xC0000022)      # ACCESS_DENIED
        self.assertIn("0xC0000022", described)
        self.assertIn("NTSTATUS", described)

    def test_common_crash_statuses_are_named(self):
        self.assertIn("ACCESS_VIOLATION", _describe_exit_code(0xC0000005))
        self.assertIn("STACK_BUFFER_OVERRUN", _describe_exit_code(0xC0000409))

    def test_the_describer_never_raises(self):
        # It only ever builds a log line. A helper that can raise into the very
        # result path it is describing would destroy the report it exists to
        # improve.
        for junk in (None, "", "abc", object(), [1], 3.5):
            try:
                _describe_exit_code(junk)
            except Exception as exc:                     # noqa: BLE001
                self.fail("_describe_exit_code raised on %r: %s" % (junk, exc))


class ConsoleInterruptionIsRecognisedTests(SimpleTestCase):

    def test_the_ctrl_c_status_is_recognised(self):
        self.assertTrue(_is_console_interruption(CTRL_C))
        self.assertTrue(_is_console_interruption(-1073741510))   # signed form

    def test_an_ordinary_failure_is_not_an_interruption(self):
        for code in (0, 1, 2, 255, 0xC0000005):
            self.assertFalse(_is_console_interruption(code),
                             "%r must not be read as a console interruption" % code)

    def test_it_never_raises(self):
        for junk in (None, "", "abc", object()):
            try:
                _is_console_interruption(junk)
            except Exception as exc:                     # noqa: BLE001
                self.fail("_is_console_interruption raised on %r: %s" % (junk, exc))


class ForkedWindowReportContractTests(SimpleTestCase):
    """The wiring the helpers above are useless without."""

    def test_the_code_source_is_recorded_on_both_paths(self):
        # Sentinel present  -> the SCRIPT reported. poll() returned -> the
        # CONSOLE died first. Losing that distinction is the whole defect.
        self.assertIn('code_source = "script"', _SOURCE)
        self.assertIn('code_source = "console"', _SOURCE)

    def test_a_dead_console_is_not_reported_as_a_failed_script(self):
        self.assertIn('if code_source == "console":', _SOURCE)
        self.assertIn("result is UNKNOWN", _SOURCE,
                      "when the window dies first the script's result is unknown "
                      "and the log must say exactly that")

    def test_an_interruption_is_not_reported_as_a_rejection(self):
        self.assertIn("INTERRUPTED, not rejected", _SOURCE)
        self.assertIn("NOT evidence that the command is wrong", _SOURCE)

    def test_every_non_zero_code_still_fails(self):
        # FAIL-SAFE. Clarity must never become leniency: a nicer message about a
        # failure is still a failure.
        tail = _SOURCE[_SOURCE.index("described = _describe_exit_code(exit_code)"):]
        tail = tail[:tail.index("# PID Management")]
        self.assertNotIn("return True", tail,
                         "the non-zero branch must never return success")
        self.assertIn("return False", tail)

    def test_the_failure_lines_go_through_the_describer(self):
        raw = re.findall(r"failed with exit code: \{[a-z_.]*returncode\}", _SOURCE)
        self.assertEqual(raw, [],
                         "a bare f-string exit code is back: %r - route it "
                         "through _describe_exit_code()" % raw)

    def test_the_stale_cmd_k_comment_is_gone(self):
        # The comment claimed the window is held open by `cmd /k` while the code
        # three lines below spawns `cmd /c` plus a bounded Start-Sleep. A comment
        # that contradicts its own code is how the next reader is misled.
        self.assertNotIn("held open by `cmd /k`", _SOURCE)
