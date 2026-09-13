"""Regression guard: ``chat_agent_run_wait`` must return AS SOON AS the child exits.

THE BUG THIS PINS (measured live on Angela's install, 2026-09-12)
----------------------------------------------------------------
The wait loop used to be::

    while elapsed < max_s:
        run.refresh_from_db()
        if str(run.status or "").lower() != "running":
            break

``refresh_from_db()`` merely re-reads the ``ChatAgentRun`` row -- and **nothing
writes that row while the child is running**. The status is only ever updated by
``chat_agent_runtime.reconcile_chat_agent_run()``, which is the one place that
actually asks the operating system (``_is_live_process`` / ``handle.poll()``).
So the loop re-read a stale ``"running"`` on every single tick and this tool
could **never** return early: it ALWAYS burned the full ``max_seconds``.

Live evidence: Whisperer transcribed an 87-second recording and logged
``status: transcribed`` at 18:55:40 -- 13 seconds after it started. Tlamatini
then sat blocked in this tool until 19:00:37, the exact 300-second ceiling she
had passed. Worse, the delay was INVISIBLE in the record: ``finishedAt`` is
stamped by ``reconcile`` at the moment it first looks, so the run was filed as
having "finished" at 19:00:37 rather than 18:55:40.

That is the silent-plausible-WRONG class this codebase exists to refuse: no
error, no crash, a green row, an answer that eventually arrives -- and five
minutes of dead wait on every wrapped agent Tlamatini ever waits on (the
default ``max_seconds`` is 120, so the floor was two minutes per call).

The second, quieter defect fixed in the same pass: the loop broke on
``!= "running"``, but ``RUNNING_STATUSES`` is ``{"created", "running"}``. A run
still in ``created`` had not finished either, yet the old comparison reported it
as done the instant it was polled.
"""

from __future__ import annotations

import ast
import json
import os
import time
import unittest
from unittest import mock

TOOLS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tools.py")


def _wait_function_node() -> ast.FunctionDef:
    """AST-lift ``chat_agent_run_wait`` straight from the source file.

    Read from disk rather than via ``inspect.getsource`` because the function is
    wrapped as a LangChain tool object, whose ``__wrapped__`` chain is not
    guaranteed to survive every LangChain version.
    """
    with open(TOOLS_PATH, "r", encoding="utf-8") as handle:
        tree = ast.parse(handle.read(), filename=TOOLS_PATH)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "chat_agent_run_wait":
            return node
    raise AssertionError("chat_agent_run_wait() not found in tools.py")


class WaitLoopSourceContractTests(unittest.TestCase):
    """The loop must poll the PROCESS, never just re-read the row."""

    def test_the_wait_loop_never_calls_refresh_from_db(self):
        node = _wait_function_node()
        offenders = [
            child.func.attr
            for child in ast.walk(node)
            if isinstance(child, ast.Call)
            and isinstance(child.func, ast.Attribute)
            and child.func.attr == "refresh_from_db"
        ]
        self.assertEqual(
            offenders,
            [],
            "chat_agent_run_wait() calls refresh_from_db(). That only re-reads a "
            "row nothing updates while the child runs, so the wait can never "
            "return early and always burns the full max_seconds. Call "
            "reconcile_chat_agent_run(run) instead -- it polls the real process.",
        )

    def test_the_wait_loop_reconciles_against_the_real_process(self):
        node = _wait_function_node()
        called = {
            child.func.id
            for child in ast.walk(node)
            if isinstance(child, ast.Call) and isinstance(child.func, ast.Name)
        }
        self.assertIn(
            "reconcile_chat_agent_run",
            called,
            "chat_agent_run_wait() must call reconcile_chat_agent_run(run) inside "
            "its poll loop -- that is the ONLY function that asks the OS whether "
            "the child is still alive.",
        )

    def test_a_created_run_is_still_treated_as_unfinished(self):
        node = _wait_function_node()
        names = {
            child.id for child in ast.walk(node) if isinstance(child, ast.Name)
        }
        self.assertIn(
            "RUNNING_STATUSES",
            names,
            "The loop must break on NOT-IN RUNNING_STATUSES ({'created', "
            "'running'}), not on != 'running'. A run still in 'created' has not "
            "finished, and the old comparison reported it as done immediately.",
        )


class WaitReturnsEarlyTests(unittest.TestCase):
    """Behavioural proof: a child that finishes fast is not waited on for 300 s."""

    @staticmethod
    def _callable():
        from agent import tools

        target = tools.chat_agent_run_wait
        # Unwrap the LangChain tool object if the decorator produced one.
        return tools, getattr(target, "func", target)

    def test_returns_as_soon_as_the_child_exits(self):
        tools, wait = self._callable()

        class _FakeRun:
            def __init__(self):
                self.runId = "aa2af28aa8d24b14a9cbe1876b5244ea"
                self.status = "running"
                self.polls = 0

            def refresh_from_db(self):  # pragma: no cover - must never be reached
                raise AssertionError(
                    "refresh_from_db() re-reads a stale row; the wait must poll "
                    "the real process via reconcile_chat_agent_run()."
                )

        run = _FakeRun()

        def fake_reconcile(subject):
            subject.polls += 1
            if subject.polls >= 2:          # the child exits on the 2nd look
                subject.status = "completed"
            return subject

        with mock.patch.object(tools, "get_chat_agent_run", return_value=run), \
             mock.patch.object(tools, "reconcile_chat_agent_run", side_effect=fake_reconcile), \
             mock.patch.object(
                 tools,
                 "serialize_chat_agent_run",
                 side_effect=lambda subject, **_kwargs: {"status": subject.status},
             ):
            started = time.monotonic()
            raw = wait("aa2af28aa8d24b14a9cbe1876b5244ea", max_seconds=300,
                       poll_interval_seconds=1)
            elapsed = time.monotonic() - started

        payload = json.loads(raw)
        self.assertEqual(payload["status"], "completed")
        self.assertLess(
            elapsed,
            30.0,
            "The wait burned {0:.0f}s for a child that exited on the second "
            "poll. This is the 2026-09-12 stall.".format(elapsed),
        )
        self.assertLess(
            payload["waited_seconds"],
            30,
            "waited_seconds must report the REAL wait, not the ceiling.",
        )

    def test_a_child_that_never_finishes_still_honours_the_ceiling(self):
        """Fail-safe: the timeout must still bound a genuinely stuck child."""
        tools, wait = self._callable()

        class _StuckRun:
            runId = "stuck"
            status = "running"

        with mock.patch.object(tools, "get_chat_agent_run", return_value=_StuckRun()), \
             mock.patch.object(tools, "reconcile_chat_agent_run", side_effect=lambda s: s), \
             mock.patch.object(
                 tools,
                 "serialize_chat_agent_run",
                 side_effect=lambda subject, **_kwargs: {"status": subject.status},
             ):
            started = time.monotonic()
            raw = wait("stuck", max_seconds=2, poll_interval_seconds=1)
            elapsed = time.monotonic() - started

        payload = json.loads(raw)
        self.assertEqual(payload["status"], "running")
        self.assertLess(elapsed, 15.0, "the ceiling must still bound the wait")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
