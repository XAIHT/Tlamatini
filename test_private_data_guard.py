#!/usr/bin/env python3
"""Automated tests for the PRIVATE DATA GUARD mechanism.

Two mechanisms are verified:

  A. GIT-HISTORY INTEGRITY GUARD
     The promise is: sensitive data is removed ONLY in new forward commits,
     and history / tags / pushes are NEVER rewritten. These tests fail loudly
     if anyone ever rebases, amends, resets, filter-repos, or force-pushes:
       - the ROOT commit SHA is immutable,
       - the commit count only ever grows,
       - every previously-published tag still exists,
       - the forward-only scrub still holds (no private PII in tracked files).

  B. GLOBAL BANNER GUARD
     A SessionStart hook prints the guard IN CAPS for EVERY Claude Code session
     of this user, in any directory on this machine:
       - the banner script exists,
       - ~/.claude/settings.json wires it as a SessionStart hook,
       - running it prints the required CAPS keywords and exits 0.

NO private data is hardcoded in this file. The deep PII scan is DELEGATED to
``check_private_data.py`` (which takes targets at runtime) and is SKIPPED unless
a local, gitignored targets file / env var is present.

Run:  python -m unittest test_private_data_guard -v
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent

# --- Git invariants captured when the guard was installed (2026-06-27) --------
# The root (very first) commit. Rewriting history necessarily changes this SHA.
ROOT_COMMIT = "137a0d70e1466fc69b50a8c3ac1740cf5b57c41d"
# History only ever grows; it must never be shorter than this floor.
MIN_COMMITS = 523
# Anchor tags that must never disappear (first, and the privacy-scrub releases).
REQUIRED_TAGS = ("v1.0.0", "v1.30.1", "v1.31.0", "v1.31.1")
MIN_TAG_COUNT = 49

# Placeholders the forward-only scrub wrote (positive, PII-free assertions).
PLACEHOLDER_CHECKS = (
    (REPO / "Tlamatini/agent/agents/telegrammer/config.yaml", "@your_telegram_username"),
    (REPO / "Tlamatini/agent/agents/emailer/config.yaml", "you@example.com"),
    (REPO / "Tlamatini/agent/Tlamatini.md", "The project maintainer"),
)

# A structural (NOT personal) shape: Meta/WhatsApp access tokens. Must be absent
# from tracked files. This is a regex for a token format, not anyone's data.
META_TOKEN_RE = re.compile(r"EAA[A-Za-z0-9]{30,}")

USER_CLAUDE = Path.home() / ".claude"
BANNER_SCRIPT = USER_CLAUDE / "hooks" / "private_data_guard_banner.py"
USER_SETTINGS = USER_CLAUDE / "settings.json"


def _git(*args: str) -> str:
    out = subprocess.run(
        ["git", "-C", str(REPO), *args],
        capture_output=True, text=True, timeout=30,
    )
    if out.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {out.stderr.strip()}")
    return out.stdout.strip()


def _tracked_files() -> list[str]:
    return [p for p in _git("ls-files").splitlines() if p]


class GitHistoryIntegrityGuardTests(unittest.TestCase):
    """The history must only ever move FORWARD — never be rewritten."""

    def test_root_commit_is_immutable(self):
        root = _git("rev-list", "--max-parents=0", "HEAD")
        # There may be more than one root in theory; ours is single.
        self.assertIn(
            ROOT_COMMIT, root.split(),
            "ROOT COMMIT CHANGED -> history was rewritten. This is forbidden.",
        )

    def test_history_only_grows(self):
        count = int(_git("rev-list", "--count", "HEAD"))
        self.assertGreaterEqual(
            count, MIN_COMMITS,
            f"Commit count {count} < {MIN_COMMITS} -> commits were dropped "
            "(reset/rebase/filter). Forbidden.",
        )

    def test_all_published_tags_still_exist(self):
        tags = set(_git("tag").splitlines())
        for t in REQUIRED_TAGS:
            self.assertIn(t, tags, f"Tag {t} disappeared -> a pushed tag was deleted. Forbidden.")
        self.assertGreaterEqual(
            len(tags), MIN_TAG_COUNT,
            f"Only {len(tags)} tags (< {MIN_TAG_COUNT}) -> tags were deleted. Forbidden.",
        )

    def test_scrub_holds_placeholders_present(self):
        for path, placeholder in PLACEHOLDER_CHECKS:
            self.assertTrue(path.exists(), f"missing file {path}")
            text = path.read_text(encoding="utf-8", errors="replace")
            self.assertIn(
                placeholder, text,
                f"placeholder {placeholder!r} missing from {path} -> scrub regressed.",
            )

    def test_no_meta_token_shape_in_tracked_files(self):
        offenders = []
        for rel in _tracked_files():
            p = REPO / rel
            try:
                if p.stat().st_size > 5_000_000:
                    continue
                data = p.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            if META_TOKEN_RE.search(data):
                offenders.append(rel)
        self.assertEqual([], offenders, f"Meta/WhatsApp token shape in tracked files: {offenders}")

    def test_deep_pii_scan_delegated_to_auditor(self):
        """Run check_private_data.py against a LOCAL targets file if one exists.

        Targets are NEVER stored in the repo. Provide them via the gitignored
        file ``.private_targets.json`` or env ``CHECK_PRIVATE_DATA_TARGETS`` to
        activate this check; otherwise it is skipped (so the committed test
        carries no private data).
        """
        auditor = REPO / "check_private_data.py"
        targets_file = REPO / ".private_targets.json"
        has_env = bool(os.environ.get("CHECK_PRIVATE_DATA_TARGETS"))
        if not auditor.exists():
            self.skipTest("check_private_data.py not present")
        if not (targets_file.exists() or has_env):
            self.skipTest(
                "no local targets (.private_targets.json / env) -> deep scan skipped by design"
            )
        cmd = [sys.executable, str(auditor), "--local", "--no-llm", "--repo", str(REPO)]
        if targets_file.exists():
            cmd += ["--targets-file", str(targets_file)]
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=600, cwd=str(REPO))
        # exit 0 = clean, 1 = leaks found, 2 = no targets.
        self.assertEqual(
            res.returncode, 0,
            f"check_private_data.py reported private-data leaks (rc={res.returncode}).\n"
            f"{res.stdout[-1500:]}",
        )


class GlobalBannerGuardTests(unittest.TestCase):
    """The CAPS banner must fire for every Claude Code session on this machine."""

    def test_banner_script_exists(self):
        self.assertTrue(
            BANNER_SCRIPT.exists(),
            f"banner script missing at {BANNER_SCRIPT} -> the global hook target is gone.",
        )

    def test_user_settings_wires_sessionstart_hook(self):
        self.assertTrue(USER_SETTINGS.exists(), f"{USER_SETTINGS} missing")
        cfg = json.loads(USER_SETTINGS.read_text(encoding="utf-8"))
        sessionstart = (cfg.get("hooks") or {}).get("SessionStart") or []
        commands = [
            h.get("command", "")
            for group in sessionstart
            for h in (group.get("hooks") or [])
        ]
        self.assertTrue(
            any("private_data_guard_banner" in c for c in commands),
            "no SessionStart hook references private_data_guard_banner in user settings.json",
        )

    def test_banner_prints_caps_keywords(self):
        if not BANNER_SCRIPT.exists():
            self.skipTest("banner script missing")
        res = subprocess.run(
            [sys.executable, str(BANNER_SCRIPT)],
            capture_output=True, text=True, timeout=30,
        )
        self.assertEqual(res.returncode, 0, "banner must exit 0 so it can't break a session")
        out = res.stdout
        for needle in (
            "PRIVATE DATA GUARD: ON",
            "NEVER REWRITE GIT HISTORY",
            "TAGS, PUSHES",
        ):
            self.assertIn(needle, out, f"banner output missing required CAPS line: {needle!r}")
        # The headline must actually be uppercase.
        headline = next((ln for ln in out.splitlines() if "PRIVATE DATA GUARD" in ln), "")
        self.assertEqual(headline, headline.upper(), "headline banner line must be ALL CAPS")


if __name__ == "__main__":
    unittest.main(verbosity=2)
