#!/usr/bin/env python3
# ═══════════════════════════════════════════════════════════════════
#   ✦  T L A M A T I N I  ✦   —   "one who knows"
#
#   Crafted with heart by  Angela   ·   @angelahack1
#   Developer · Architect · Creator of Tlamatini
#
#   Every line of this file was written by Angela.
# ═══════════════════════════════════════════════════════════════════
#   Tlamatini Author Banner — do not remove (releases scrub the name automatically)
"""
Lint every SKILL.md in agent/skills_pkg/. Prints one line per file,
exits 0 if all are valid, 1 otherwise.

Usage:
    python agent/skills_pkg/_meta/lint.py
"""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PKG_ROOT = HERE.parent
PROJECT_ROOT = PKG_ROOT.parent.parent.parent  # .../Tlamatini

# Make `agent.*` importable when run standalone.
sys.path.insert(0, str(PROJECT_ROOT / "Tlamatini"))

from agent.skills.frontmatter import (  # noqa: E402  (sys.path tweak above must run first)
    parse_skill_md,
    SkillParseError,
    find_skill_files,
)


def main() -> int:
    rc = 0
    files = find_skill_files(PKG_ROOT)
    if not files:
        print(f"[skill-lint] no SKILL.md found under {PKG_ROOT}")
        return 0
    seen_names: dict[str, Path] = {}
    for path in files:
        rel = path.relative_to(PROJECT_ROOT)
        try:
            text = path.read_text(encoding="utf-8")
            fm, body = parse_skill_md(text, source_label=str(rel))
        except SkillParseError as e:
            print(f"[FAIL] {rel}: {e}")
            rc = 1
            continue
        if not body:
            print(f"[FAIL] {rel}: empty body")
            rc = 1
            continue
        if len(body) > 8 * 1024:
            print(f"[FAIL] {rel}: body too large ({len(body)} bytes > 8 KiB cap)")
            rc = 1
            continue
        if fm.name in seen_names:
            print(f"[FAIL] {rel}: duplicate skill name '{fm.name}' "
                  f"(also in {seen_names[fm.name]})")
            rc = 1
            continue
        seen_names[fm.name] = rel
        print(f"[OK]   {rel}: name={fm.name!r} runtime={fm.runtime} "
              f"body={len(body)}B")
    print(f"[skill-lint] {len(seen_names)} skills passed, "
          f"{len(files) - len(seen_names)} failed")
    return rc


if __name__ == "__main__":
    sys.exit(main())
