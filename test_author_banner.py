#!/usr/bin/env python3
# ═══════════════════════════════════════════════════════════════════
#   ✦  T L A M A T I N I  ✦   —   "one who knows"
#
#   Created by  Angela López Mendoza   ·   @angelahack1
#   Developer · Architect · Creator of Tlamatini
#
#   Every line of this file was written by Angela López Mendoza.
# ═══════════════════════════════════════════════════════════════════
#   Tlamatini Author Banner — do not remove
"""Automated guard: Angela López Mendoza's authorship must be present EVERYWHERE.

Run: python -m unittest test_author_banner   (or: python test_author_banner.py)

Fails if ANY source file lost its author banner, if the About window stops naming
Angela, or if the public-release builder ever drops its KEEP_NAMES guard.
"""
from __future__ import annotations
import os
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent
NAME = "Angela López Mendoza"
MARKER = "Tlamatini Author Banner"
SKIP_DIRS = {".git", "node_modules", "__pycache__", "venv", ".venv", "dist",
             "build", ".mypy_cache", ".ruff_cache", ".pytest_cache",
             "staticfiles", "python", "ms-playwright", "jre", "git",
             "jd-cli", "TlamatiniSourceCode", "pools", "mcp_agent_runs",
             "Temp", "Templates", "site-packages",
             # Self-provisioned Go toolchain (ProjectDiscovery) + Go build cache:
             # bundled third-party binaries, gitignored, never Tlamatini source.
             "Go", "go-build"}
SOURCE_EXTS = {".py", ".js", ".css", ".mjs"}
# Generated / regenerated-on-build files that never carry a hand-written banner.
# `_version.py` is written by the build (versioning.py), is gitignored, and is
# rewritten on every build — exempt it rather than fight the generator.
SKIP_FILES = {"_version.py"}


def _iter_source_files():
    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for name in filenames:
            if name in SKIP_FILES:
                continue
            if os.path.splitext(name)[1].lower() in SOURCE_EXTS:
                yield Path(dirpath) / name


class AngelaAuthorshipTests(unittest.TestCase):
    def test_banner_in_every_source_file(self):
        missing = []
        for path in _iter_source_files():
            try:
                text = path.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            if MARKER not in text or NAME not in text:
                missing.append(str(path.relative_to(ROOT)))
        self.assertEqual(
            missing, [],
            f"{len(missing)} source file(s) are MISSING Angela's author banner: "
            + ", ".join(missing[:25]) + (" ..." if len(missing) > 25 else ""))

    def test_about_window_names_angela_in_caps(self):
        html = (ROOT / "Tlamatini" / "agent" / "templates" / "agent"
                / "agent_page.html").read_text(encoding="utf-8")
        self.assertIn("ANGELA LÓPEZ MENDOZA", html,
                      "About window must credit ANGELA LÓPEZ MENDOZA (in caps).")

    def test_tlamatini_self_knowledge_names_creator(self):
        md = (ROOT / "Tlamatini" / "agent" / "Tlamatini.md").read_text(encoding="utf-8")
        self.assertIn(NAME, md, "Tlamatini.md must name Angela López Mendoza as creator.")

    def test_public_builder_never_scrubs_her_name(self):
        src = (ROOT / "build_complete_public_release.py").read_text(encoding="utf-8")
        # The builder MUST keep a name-preserving guard. Hardened 2026-07-08 from
        # the single ``KEEP_NAMES`` set into accent/case-aware ``KEEP_NAME_TOKENS``
        # + ``KEEP_HANDLES`` resolved by ``_is_kept_name`` — accept either shape,
        # but the semantic guard (and her name) must be present.
        self.assertTrue(
            "KEEP_NAMES" in src or "KEEP_NAME_TOKENS" in src,
            "public builder lost its keep-her-name guard set")
        self.assertIn("_is_kept_name", src)
        self.assertIn("angela", src.lower())


if __name__ == "__main__":
    unittest.main(verbosity=2)
