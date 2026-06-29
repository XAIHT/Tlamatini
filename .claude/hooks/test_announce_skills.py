#!/usr/bin/env python3
# ═══════════════════════════════════════════════════════════════════
#   ✦  T L A M A T I N I  ✦   —   "one who knows"
#
#   Created by  Angela López Mendoza   ·   @angelahack1
#   Developer · Architect · Creator of Tlamatini
#
#   Every line of this file was written by Angela López Mendoza.
# ═══════════════════════════════════════════════════════════════════
#   Tlamatini Author Banner — do not remove (releases scrub the name automatically)
"""Automated tests for the SessionStart hook (`announce_skills.py`).

Run from the repo root:
    python .claude/hooks/test_announce_skills.py

Covers BOTH halves of the user's directive (2026-05-28):
  - Happy path: when Claude Code skills, Tlamatini SKILL.md packages, and the
    two mandatory @-imports in CLAUDE.md are all present, the hook prints the
    full banner AND exits 0.
  - Fail-CLOSED path: when ANY of those prerequisites is missing (zero
    discoverable skills, missing CLAUDE.md, unwired @-import, empty target
    file, or catastrophic exception inside `main()`), the hook prints a
    SESSION ABORTED block to stderr AND exits 2 -- so Claude Code surfaces
    the failure instead of starting with a half-loaded skill set.

Pure stdlib (unittest + tempfile + mock); no pytest dep, no Tlamatini app
imports, safe to run from any clean checkout.
"""
import contextlib
import importlib.util
import io
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

HOOK_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'announce_skills.py')
_spec = importlib.util.spec_from_file_location('announce_skills', HOOK_PATH)
announce = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(announce)


class _Base(unittest.TestCase):
    """Shared scaffolding: a temp 'repo' + a temp '~' so the hook's discovery
    paths are fully isolated from the real machine."""

    def setUp(self):
        self.tmp_repo = tempfile.mkdtemp(prefix='tlamatini_repo_')
        self.tmp_home = tempfile.mkdtemp(prefix='tlamatini_home_')
        self.addCleanup(shutil.rmtree, self.tmp_repo, ignore_errors=True)
        self.addCleanup(shutil.rmtree, self.tmp_home, ignore_errors=True)
        self._orig_repo = announce.REPO
        announce.REPO = self.tmp_repo
        self._expand = mock.patch('os.path.expanduser', return_value=self.tmp_home)
        self._expand.start()

    def tearDown(self):
        self._expand.stop()
        announce.REPO = self._orig_repo

    # ---- fixture helpers -------------------------------------------------

    def make_skill(self, parent_rel, name, root=None):
        root = root or self.tmp_repo
        d = os.path.join(root, *parent_rel.split('/'), name)
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, 'SKILL.md'), 'w', encoding='utf-8') as f:
            f.write(f'# {name}\nbody.\n')

    def make_target(self, relpath, size=100):
        full = os.path.join(self.tmp_repo, relpath.replace('/', os.sep))
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, 'w', encoding='utf-8') as f:
            f.write('x' * size)

    def make_claude_md(self, body):
        with open(os.path.join(self.tmp_repo, 'CLAUDE.md'), 'w', encoding='utf-8') as f:
            f.write(body)

    def make_full_happy_layout(self):
        self.make_skill('.claude/skills', 'tlamatini-agent-naming')
        for pkg in ('acp_router', 'code_review', 'kali_pentest'):
            self.make_skill('Tlamatini/agent/skills_pkg', pkg)
        # `_meta` is an underscore-prefixed dir -- the hook must NOT count it
        self.make_skill('Tlamatini/agent/skills_pkg', '_meta')
        self.make_target('Tlamatini/.agents/workflows/create_new_agent.md', size=24811)
        self.make_target('Tlamatini/.mcps/create_new_mcp.md', size=33541)
        self.make_claude_md(
            'top\n'
            '@Tlamatini/.agents/workflows/create_new_agent.md\n'
            '@Tlamatini/.mcps/create_new_mcp.md\n'
            'tail\n'
        )

    def run_hook(self):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            rc = announce.main()
        return rc, out.getvalue(), err.getvalue()


class HappyPath(_Base):
    """Everything in place -> exit 0, full banner, no stderr."""

    def setUp(self):
        super().setUp()
        self.make_full_happy_layout()

    def test_exits_zero(self):
        rc, out, err = self.run_hook()
        self.assertEqual(rc, 0, msg=f'stdout=\n{out}\nstderr=\n{err}')

    def test_stderr_silent_on_success(self):
        _, _, err = self.run_hook()
        self.assertEqual('', err)

    def test_banner_lists_claude_code_skills(self):
        _, out, _ = self.run_hook()
        self.assertIn('Claude Code skills (1)', out)
        self.assertIn('tlamatini-agent-naming', out)

    def test_banner_lists_tlamatini_skills_and_excludes_meta(self):
        _, out, _ = self.run_hook()
        self.assertIn('Tlamatini SKILL.md packages (3)', out)
        for pkg in ('acp_router', 'code_review', 'kali_pentest'):
            self.assertIn(pkg, out)
        # `_meta` is an internal dir, never a user-facing skill
        self.assertNotIn('_meta', out)

    def test_imports_reported_ok(self):
        _, out, _ = self.run_hook()
        self.assertIn('OK @Tlamatini/.agents/workflows/create_new_agent.md', out)
        self.assertIn('OK @Tlamatini/.mcps/create_new_mcp.md', out)
        # 24,811 bytes -> well under the 40 KB performance ceiling
        self.assertIn('(24,811 bytes', out)
        # The banner's tail mentions the literal "!! ERROR" string as an
        # instruction ("If you ever see \"!! ERROR\" above..."), so we cannot
        # naively `assertNotIn`. Verify there is no actual status line:
        # "  !! ERROR @Tlamatini/..." (leading indent + marker + @-token).
        for line in out.splitlines():
            self.assertFalse(
                line.startswith('  !! ERROR @'),
                msg=f'unexpected error status line in happy-path banner: {line!r}')


class UserHomeSkillsAccepted(_Base):
    """A user-level Claude Code skill (under ~/.claude/skills) satisfies the
    'at least one CC skill' check even if the repo's .claude/skills is empty."""

    def setUp(self):
        super().setUp()
        # Skill is in ~/.claude/skills, NOT in the repo
        self.make_skill('.claude/skills', 'globally-installed', root=self.tmp_home)
        self.make_skill('Tlamatini/agent/skills_pkg', 'acp_router')
        self.make_target('Tlamatini/.agents/workflows/create_new_agent.md')
        self.make_target('Tlamatini/.mcps/create_new_mcp.md')
        self.make_claude_md(
            '@Tlamatini/.agents/workflows/create_new_agent.md\n'
            '@Tlamatini/.mcps/create_new_mcp.md\n'
        )

    def test_exits_zero_with_user_home_skill(self):
        rc, out, err = self.run_hook()
        self.assertEqual(rc, 0, msg=f'stdout=\n{out}\nstderr=\n{err}')
        self.assertIn('globally-installed', out)


class FailsClosedWhenNoCodeSkills(_Base):
    """Zero Claude Code skills (neither repo nor home) -> exit 2."""

    def setUp(self):
        super().setUp()
        self.make_skill('Tlamatini/agent/skills_pkg', 'acp_router')
        self.make_target('Tlamatini/.agents/workflows/create_new_agent.md')
        self.make_target('Tlamatini/.mcps/create_new_mcp.md')
        self.make_claude_md(
            '@Tlamatini/.agents/workflows/create_new_agent.md\n'
            '@Tlamatini/.mcps/create_new_mcp.md\n'
        )

    def test_exits_non_zero(self):
        rc, out, err = self.run_hook()
        self.assertEqual(rc, 2)
        self.assertIn('SESSION ABORTED', err)
        self.assertIn('No Claude Code skills', err)


class FailsClosedWhenNoTlamatiniSkills(_Base):
    """Zero Tlamatini SKILL.md packages -> exit 2."""

    def setUp(self):
        super().setUp()
        self.make_skill('.claude/skills', 'tlamatini-agent-naming')
        # No skills_pkg/ entries at all
        self.make_target('Tlamatini/.agents/workflows/create_new_agent.md')
        self.make_target('Tlamatini/.mcps/create_new_mcp.md')
        self.make_claude_md(
            '@Tlamatini/.agents/workflows/create_new_agent.md\n'
            '@Tlamatini/.mcps/create_new_mcp.md\n'
        )

    def test_exits_non_zero(self):
        rc, _, err = self.run_hook()
        self.assertEqual(rc, 2)
        self.assertIn('SESSION ABORTED', err)
        self.assertIn('No Tlamatini SKILL.md packages', err)


class FailsClosedWhenOnlyMetaPackage(_Base):
    """A skills_pkg/ dir containing ONLY underscore-prefixed dirs (e.g. _meta)
    is treated as empty -> exit 2."""

    def setUp(self):
        super().setUp()
        self.make_skill('.claude/skills', 'tlamatini-agent-naming')
        self.make_skill('Tlamatini/agent/skills_pkg', '_meta')
        self.make_skill('Tlamatini/agent/skills_pkg', '_drafts')
        self.make_target('Tlamatini/.agents/workflows/create_new_agent.md')
        self.make_target('Tlamatini/.mcps/create_new_mcp.md')
        self.make_claude_md(
            '@Tlamatini/.agents/workflows/create_new_agent.md\n'
            '@Tlamatini/.mcps/create_new_mcp.md\n'
        )

    def test_exits_non_zero(self):
        rc, _, err = self.run_hook()
        self.assertEqual(rc, 2)
        self.assertIn('No Tlamatini SKILL.md packages', err)


class FailsClosedWhenClaudeMdMissing(_Base):
    """CLAUDE.md absent -> the @-import check cannot pass -> exit 2."""

    def setUp(self):
        super().setUp()
        self.make_skill('.claude/skills', 'tlamatini-agent-naming')
        self.make_skill('Tlamatini/agent/skills_pkg', 'acp_router')
        self.make_target('Tlamatini/.agents/workflows/create_new_agent.md')
        self.make_target('Tlamatini/.mcps/create_new_mcp.md')
        # NO CLAUDE.md

    def test_exits_non_zero(self):
        rc, out, err = self.run_hook()
        self.assertEqual(rc, 2)
        self.assertIn('SESSION ABORTED', err)
        # Banner still mentions the failure for the user
        self.assertIn('!! ERROR reading CLAUDE.md', out)


class FailsClosedWhenImportNotWired(_Base):
    """CLAUDE.md exists but is missing one of the required @-import tokens."""

    def setUp(self):
        super().setUp()
        self.make_skill('.claude/skills', 'tlamatini-agent-naming')
        self.make_skill('Tlamatini/agent/skills_pkg', 'acp_router')
        self.make_target('Tlamatini/.agents/workflows/create_new_agent.md')
        self.make_target('Tlamatini/.mcps/create_new_mcp.md')
        # Wire only the FIRST import; second is missing
        self.make_claude_md('@Tlamatini/.agents/workflows/create_new_agent.md\n')

    def test_exits_non_zero(self):
        rc, out, err = self.run_hook()
        self.assertEqual(rc, 2)
        self.assertIn('is NOT @-imported by CLAUDE.md', err)
        self.assertIn('@Tlamatini/.mcps/create_new_mcp.md', err)
        # The other import is still reported OK in the banner
        self.assertIn('OK @Tlamatini/.agents/workflows/create_new_agent.md', out)


class FailsClosedWhenTargetFileEmpty(_Base):
    """@-import wired in CLAUDE.md, but target file is 0 bytes -> exit 2."""

    def setUp(self):
        super().setUp()
        self.make_skill('.claude/skills', 'tlamatini-agent-naming')
        self.make_skill('Tlamatini/agent/skills_pkg', 'acp_router')
        self.make_target('Tlamatini/.agents/workflows/create_new_agent.md', size=0)
        self.make_target('Tlamatini/.mcps/create_new_mcp.md')
        self.make_claude_md(
            '@Tlamatini/.agents/workflows/create_new_agent.md\n'
            '@Tlamatini/.mcps/create_new_mcp.md\n'
        )

    def test_exits_non_zero(self):
        rc, _, err = self.run_hook()
        self.assertEqual(rc, 2)
        self.assertIn('is missing or empty', err)


class FailsClosedWhenTargetFileMissing(_Base):
    """@-import wired, but target file does not exist at all."""

    def setUp(self):
        super().setUp()
        self.make_skill('.claude/skills', 'tlamatini-agent-naming')
        self.make_skill('Tlamatini/agent/skills_pkg', 'acp_router')
        # Only ONE of the two target files exists
        self.make_target('Tlamatini/.mcps/create_new_mcp.md')
        self.make_claude_md(
            '@Tlamatini/.agents/workflows/create_new_agent.md\n'
            '@Tlamatini/.mcps/create_new_mcp.md\n'
        )

    def test_exits_non_zero(self):
        rc, out, err = self.run_hook()
        self.assertEqual(rc, 2)
        self.assertIn('is missing or empty', err)
        self.assertIn('create_new_agent.md', err)


class CatastrophicExceptionStillFailsClosed(_Base):
    """If `main()` raises before completing, the hook must still exit 2."""

    def test_internal_crash_returns_two(self):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            with mock.patch.object(announce, '_discover_skills',
                                   side_effect=RuntimeError('disk on fire')):
                rc = announce.main()
        self.assertEqual(rc, 2)
        self.assertIn('SessionStart hook crashed', err.getvalue())
        self.assertIn('disk on fire', err.getvalue())


class BannerContractStable(_Base):
    """Pin a few literal strings the banner promises, so a careless refactor
    that drops the NAMING CONVENTION line (or the STM32er mission-critical
    line) trips this test instead of shipping silently."""

    def setUp(self):
        super().setUp()
        self.make_full_happy_layout()

    def test_banner_contains_required_lines(self):
        _, out, _ = self.run_hook()
        for fragment in (
            'MANDATORY OPERATING RULE -- TLAMATINI AGENTS',
            'SESSION SKILLS LOADED (Tlamatini)',
            'Agent NAMING CONVENTION active',
            'STM32er is MISSION-CRITICAL',
            'MANDATORY @-IMPORTS',
        ):
            self.assertIn(fragment, out, msg=f'banner is missing: {fragment!r}')


if __name__ == '__main__':
    # Force verbose output and propagate the exit code so CI can rely on it.
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__]))
    sys.exit(0 if result.wasSuccessful() else 1)
