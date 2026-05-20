"""Regression tests for ``agent.orphan_reaper``.

The headline contract these tests pin is the **console-window safety
contract**: the reaper must NEVER kill the ``conhost.exe`` that owns
Tlamatini's own console window. The previous revision reaped any console
host whose parent PID was in our process tree — and in frozen (onedir)
builds the main window's ``conhost.exe`` is a direct child of
``os.getpid()``, so the post-answer sweep closed the window on every
request and stranded the server (users reported "the console window
closed unexpectedly and the process hung").

Most of the policy lives in the pure, side-effect-free
``_console_host_reap_decision`` so it can be exercised without mocking
psutil at all.
"""
from __future__ import annotations

import os
import unittest

from agent import orphan_reaper as orphan
from agent.orphan_reaper import (
    _ancestor_pids,
    _console_host_reap_decision,
    _console_owner_pid,
    _is_reapable_console_orphan,
    format_survivors_message,
    reap_orphans,
)

try:
    import psutil  # noqa: F401
    _HAVE_PSUTIL = True
except ImportError:  # pragma: no cover
    _HAVE_PSUTIL = False


def _decide(name="conhost.exe", *, pid=4242, ppid=1000, parent_exists=True,
            parent_is_zombie=False, protected_pids=None, our_pid=999,
            our_ancestors=None):
    """Thin wrapper around the pure decision fn with sensible defaults."""
    return _console_host_reap_decision(
        name=name,
        pid=pid,
        ppid=ppid,
        parent_exists=parent_exists,
        parent_is_zombie=parent_is_zombie,
        protected_pids=protected_pids if protected_pids is not None else set(),
        our_pid=our_pid,
        our_ancestors=our_ancestors if our_ancestors is not None else set(),
    )


class ConsoleHostReapDecisionTests(unittest.TestCase):
    """The pure policy that decides whether a console host is reapable."""

    # ── The headline regression: our own window's host ───────────────
    def test_conhost_parented_to_our_pid_is_never_reaped(self):
        """conhost whose parent IS the current process == our own window.

        This is the exact case that closed the console window before the
        fix. It MUST be protected.
        """
        self.assertFalse(_decide(ppid=999, our_pid=999))

    def test_pid_in_protected_set_is_never_reaped(self):
        """The GetConsoleWindow owner PID is added to protected_pids."""
        self.assertFalse(_decide(pid=7777, protected_pids={7777}))

    def test_conhost_parented_to_ancestor_is_never_reaped(self):
        """Terminal / shell-wrapper / bootloader own the console — leave it."""
        self.assertFalse(_decide(ppid=500, our_ancestors={500, 4}))

    def test_conhost_whose_parent_pid_is_protected_is_never_reaped(self):
        self.assertFalse(_decide(ppid=8888, protected_pids={8888}))

    # ── Genuine orphans SHOULD still be reaped ───────────────────────
    def test_orphan_with_missing_parent_is_reaped(self):
        self.assertTrue(_decide(ppid=31337, parent_exists=False))

    def test_orphan_with_zero_ppid_is_reaped(self):
        self.assertTrue(_decide(ppid=0))

    def test_orphan_with_none_ppid_is_reaped(self):
        self.assertTrue(_decide(ppid=None))

    def test_console_host_of_zombie_parent_is_reaped(self):
        self.assertTrue(_decide(ppid=2222, parent_exists=True,
                                parent_is_zombie=True))

    # ── Live, unrelated parents are left alone ───────────────────────
    def test_console_host_of_live_unrelated_parent_is_not_reaped(self):
        self.assertFalse(_decide(ppid=2222, parent_exists=True,
                                 parent_is_zombie=False))

    # ── Name gating ──────────────────────────────────────────────────
    def test_non_console_host_name_is_never_reaped(self):
        # Even a genuinely orphaned non-conhost process is not the
        # console sweep's concern (the pool-cmdline scan handles those).
        self.assertFalse(_decide(name="node.exe", ppid=0))
        self.assertFalse(_decide(name="python.exe", parent_exists=False))

    def test_openconsole_is_treated_like_conhost(self):
        self.assertTrue(_decide(name="openconsole.exe", ppid=0))
        self.assertFalse(_decide(name="OpenConsole.exe", ppid=999, our_pid=999))

    def test_name_match_is_case_insensitive(self):
        self.assertTrue(_decide(name="CONHOST.EXE", ppid=0))


class FactGatheringTests(unittest.TestCase):
    """``_is_reapable_console_orphan`` collects psutil facts then defers
    to the pure policy. We feed it fake processes to confirm the wiring."""

    class _FakeProc:
        def __init__(self, name, pid, ppid):
            self._name = name
            self.pid = pid
            self._ppid = ppid

        def name(self):
            return self._name

        def ppid(self):
            return self._ppid

    @unittest.skipUnless(_HAVE_PSUTIL, "psutil required")
    def test_own_console_host_not_reaped_end_to_end(self):
        """A conhost child of our PID is not reapable, even though the
        parent process clearly exists."""
        our_pid = os.getpid()
        proc = self._FakeProc("conhost.exe", pid=4242, ppid=our_pid)
        self.assertFalse(_is_reapable_console_orphan(
            proc, protected_pids={our_pid}, our_pid=our_pid, our_ancestors=set(),
        ))

    @unittest.skipUnless(_HAVE_PSUTIL, "psutil required")
    def test_orphan_with_dead_parent_is_reapable_end_to_end(self):
        """A conhost whose parent PID does not resolve is a true orphan."""
        # Pick a PID that is overwhelmingly unlikely to exist.
        dead_ppid = 4_000_000_123
        proc = self._FakeProc("conhost.exe", pid=4242, ppid=dead_ppid)
        self.assertTrue(_is_reapable_console_orphan(
            proc, protected_pids=set(), our_pid=os.getpid(), our_ancestors=set(),
        ))


class HelperResilienceTests(unittest.TestCase):
    """The protection helpers must never raise and must satisfy basic
    invariants on any platform."""

    def test_console_owner_pid_never_raises(self):
        owner = _console_owner_pid()
        self.assertTrue(owner is None or isinstance(owner, int))
        if os.name != "nt":
            self.assertIsNone(owner)

    @unittest.skipUnless(_HAVE_PSUTIL, "psutil required")
    def test_ancestor_pids_excludes_self_and_is_bounded(self):
        ancestors = _ancestor_pids(os.getpid())
        self.assertIsInstance(ancestors, set)
        self.assertNotIn(os.getpid(), ancestors)
        # The chain is hard-capped at 64; a real chain is far shorter.
        self.assertLessEqual(len(ancestors), 64)

    def test_ancestor_pids_of_bogus_pid_is_empty(self):
        self.assertEqual(_ancestor_pids(4_000_000_123), set())


class ReapOrphansSelfProtectionTests(unittest.TestCase):
    """Smoke test: a real sweep must never report our own PID or our
    console owner as killed/surviving, and must never raise."""

    def test_reap_never_targets_self_or_console_owner(self):
        result = reap_orphans(scope="unit-test:self-protection")
        targeted = {pid for _, pid in result.killed + result.survivors}
        self.assertNotIn(os.getpid(), targeted)
        owner = _console_owner_pid()
        if owner:
            self.assertNotIn(owner, targeted)

    def test_reap_disabled_sweeps_is_noop(self):
        result = reap_orphans(
            scope="unit-test:noop",
            include_self_tree=False,
            include_pool_scan=False,
            include_console_host_sweep=False,
        )
        self.assertEqual(result.killed, [])


class FormatSurvivorsMessageTests(unittest.TestCase):
    def test_empty_survivors_returns_none(self):
        self.assertIsNone(format_survivors_message([]))
        self.assertIsNone(format_survivors_message([("conhost.exe", 0)]))

    def test_survivors_render_name_and_pid(self):
        msg = format_survivors_message([("conhost.exe", 1234)])
        self.assertIsNotNone(msg)
        self.assertIn("conhost.exe", msg)
        self.assertIn("1234", msg)

    def test_module_no_longer_defines_reapable_helpers(self):
        """The dead powershell/cmd 'reap on sight' set was a footgun and
        must stay removed."""
        self.assertFalse(hasattr(orphan, "_REAPABLE_HELPERS"))


if __name__ == "__main__":
    unittest.main()
