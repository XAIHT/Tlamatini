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
import unicodedata
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent

# --- Git invariants captured when the guard was installed (2026-06-27) --------
# The root (very first) commit. Rewriting history necessarily changes this SHA.
ROOT_COMMIT = "137a0d70e1466fc69b50a8c3ac1740cf5b57c41d"
# History only ever grows; it must never be shorter than this floor.
MIN_COMMITS = 523
# Anchor tags that must never disappear (first, and the privacy-scrub releases).
# NOTE: v1.31.0 was NEVER published — the release sequence skipped that patch
# (v1.30.1 -> v1.31.1), verified absent both locally AND on origin and never in
# the reflog. Removing it is a correction of a phantom entry, NOT a dropped
# pushed tag (which would be forbidden).
REQUIRED_TAGS = ("v1.0.0", "v1.30.1", "v1.31.1")
MIN_TAG_COUNT = 49

# Placeholders the forward-only scrub wrote (positive, PII-free assertions).
PLACEHOLDER_CHECKS = (
    (REPO / "Tlamatini/agent/agents/telegrammer/config.yaml", "@your_telegram_username"),
    (REPO / "Tlamatini/agent/agents/emailer/config.yaml", "you@example.com"),
    # Angela's directive REVERSED the old "hide the maintainer" scrub — her name
    # must be NAMED in the self-knowledge doc, not replaced by a generic phrase.
    # So this sentinel now asserts her authorship is PRESENT, not that it's hidden.
    (REPO / "Tlamatini/agent/Tlamatini.md", "Ángela López Mendoza"),
)

# A structural (NOT personal) shape: Meta/WhatsApp access tokens. Must be absent
# from tracked files. This is a regex for a token format, not anyone's data.
# A token stands ALONE: "EAA..." inside a longer base64 run (an embedded PNG, font or wasm blob) is
# image data that merely contains those letters, so the run must not continue on either side.
META_TOKEN_RE = re.compile(r"(?<![A-Za-z0-9+/=_-])EAA[A-Za-z0-9]{30,}(?![A-Za-z0-9+/=_-])")
# Third-party code vendored under these paths is minified and ships base64 data blobs line by line;
# it is not ours to scrub and holds no token of ours.
TOKEN_SCAN_EXCLUDED_PREFIXES = ("Tlamatini/agent/static/agent/vendor/",)

# The deep scan looks for PRIVATE TARGETS (a person's name, e-mail, phone, handle) in TRACKED files.
# The maintainer is credited BY NAME in this repository on purpose (see PLACEHOLDER_CHECKS above), so
# her own name is never a leak, whatever the local targets file lists.
PUBLIC_MAINTAINER_NAMES = frozenset({"angela lopez mendoza"})

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


def _fold(text: str) -> str:
    """Lower-case, accent-free, single-spaced: 'Ángela  López' == 'angela lopez'."""
    decomposed = unicodedata.normalize("NFKD", str(text))
    plain = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return " ".join(plain.lower().split())


def _mask(value: str) -> str:
    """Never print a private value, not even in a failing test's message."""
    value = str(value)
    return f"{value[:2]}***{value[-2:]}" if len(value) > 6 else "***"


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
            if rel.startswith(TOKEN_SCAN_EXCLUDED_PREFIXES):
                continue
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
        # The report goes under the gitignored Temp/ (never the repo root) and is removed afterwards.
        report_dir = REPO / "Temp"
        report_dir.mkdir(exist_ok=True)
        report_path = report_dir / "private_data_audit_guard.json"
        report_path.unlink(missing_ok=True)
        cmd = [sys.executable, str(auditor), "--local", "--no-llm", "--repo", str(REPO),
               "--output", str(report_path)]
        if targets_file.exists():
            cmd += ["--targets-file", str(targets_file)]
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=600, cwd=str(REPO))
        # The auditor exits 0 = nothing found, 1 = findings, 2 = no targets. Its findings also count
        # structural noise (high-entropy strings, "kyber" keywords) that says nothing about PRIVATE
        # TARGETS, so the verdict is read from the report: a TARGET found in a TRACKED file.
        try:
            self.assertIn(res.returncode, (0, 1), f"check_private_data.py did not run (rc={res.returncode}).\n{res.stderr[-800:]}")
            self.assertTrue(report_path.is_file(), "check_private_data.py wrote no report")
            report = json.loads(report_path.read_text(encoding="utf-8"))
        finally:
            report_path.unlink(missing_ok=True)
        tracked = set(_tracked_files())
        offenders = set()
        for scan in report.get("scans", []):
            for finding in (scan.get("result") or {}).get("findings", []):
                rel = str((finding.get("forensics") or {}).get("relpath") or "").replace("\\", "/")
                if rel not in tracked:   # gitignored / untracked local files never reach the repository
                    continue
                for match in finding.get("matches", []):
                    target = match.get("target")
                    if not target or _fold(target) in PUBLIC_MAINTAINER_NAMES:
                        continue
                    offenders.add((rel, str(match.get("category") or "target"), _mask(target)))
        self.assertEqual(
            [], sorted(offenders),
            "a private target (masked here) is present in tracked files: (path, category, target). "
            "Remove it going forward (edit the file, then a NEW forward commit); never rewrite history.",
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
        # The hook prints ONE JSON line ("systemMessage" reaches Angela's screen, "additionalContext"
        # reaches Claude): judge the banner TEXT inside it, never the JSON line with its lowercase keys.
        try:
            payload = json.loads(out)
        except ValueError:
            payload = None
        if isinstance(payload, dict):
            on_screen = str(payload.get("systemMessage") or "")
            to_claude = str((payload.get("hookSpecificOutput") or {}).get("additionalContext") or "")
            for channel, text in (("systemMessage", on_screen), ("additionalContext", to_claude)):
                for needle in ("PRIVATE DATA GUARD: ON", "NEVER REWRITE GIT HISTORY", "TAGS, PUSHES"):
                    self.assertIn(needle, text, f"the {channel} channel lost the required line: {needle!r}")
            banner = on_screen
        else:
            banner = out   # an older plain-text banner
        # The headline must actually be uppercase.
        headline = next((ln for ln in banner.splitlines() if "PRIVATE DATA GUARD" in ln), "")
        self.assertTrue(headline, "no headline line carries PRIVATE DATA GUARD")
        self.assertEqual(headline, headline.upper(), "headline banner line must be ALL CAPS")


if __name__ == "__main__":
    unittest.main(verbosity=2)
