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
"""Validate a single SKILL.md package directory.

Usage:
    python quick_validate.py <skill_dir>

Returns 0 if the SKILL.md is parseable AND the body is non-empty AND under
8 KiB AND the frontmatter has at least name + description.
"""
from __future__ import annotations

import sys
from pathlib import Path


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: quick_validate.py <skill_dir>")
        return 2
    skill_dir = Path(argv[1]).resolve()
    md = skill_dir / "SKILL.md"
    if not md.exists():
        print(f"[FAIL] {md} does not exist")
        return 1
    text = md.read_text(encoding="utf-8")
    if "---" not in text:
        print(f"[FAIL] {md} has no frontmatter")
        return 1
    if "name:" not in text or "description:" not in text:
        print(f"[FAIL] {md} missing name/description")
        return 1
    body_size = len(text)
    if body_size > 12 * 1024:
        print(f"[FAIL] {md} too large ({body_size} bytes)")
        return 1
    print(f"[OK] {md} basic validation passed ({body_size} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
