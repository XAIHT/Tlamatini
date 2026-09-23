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
"""
Lint every SKILL.md in agent/skills_pkg/.

⚠️ This script owns NO validation rules of its own. Every check lives in
``agent/skills/validation.py`` so the catalog lint, the skill-creator's quick
validation and the Skills Diagnostics surface can never disagree about what a
valid package is — they used to, and a package could pass one while failing
another. Add a rule THERE, not here.

Exits 0 when nothing would make the registry refuse a package (warnings are
printed and do not fail), 1 otherwise.

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

from agent.skills.frontmatter import find_skill_files  # noqa: E402
from agent.skills.validation import (  # noqa: E402
    SEVERITY_ERROR,
    check_duplicate_names,
    validate_skill_file,
)


def main() -> int:
    files = find_skill_files(PKG_ROOT)
    if not files:
        print(f"[skill-lint] no SKILL.md found under {PKG_ROOT}")
        return 0

    results = []
    failed = 0
    warned = 0
    for path in files:
        rel = path.relative_to(PROJECT_ROOT)
        result = validate_skill_file(path)
        result.path = rel
        results.append(result)
        if result.errors:
            failed += 1
            for f in result.errors:
                print(f"[FAIL] {rel}: {f.code}: {f.message}")
            continue
        for f in result.warnings:
            warned += 1
            print(f"[WARN] {rel}: {f.code}: {f.message}")
        print(f"[OK]   {rel}: name={result.name!r} "
              f"runtime={result.runtime} "
              f"body={result.body_bytes}B ({result.body_chars} chars)")

    # A duplicate name WITHIN this one tree is a real collision (distinct from
    # the deliberate install-copy-shadows-bundled-copy override across roots).
    for f in check_duplicate_names(results):
        if f.severity == SEVERITY_ERROR:
            failed += 1
        print(f"[FAIL] {f.code}: {f.message}")

    print(f"[skill-lint] {len(results) - failed} skills passed, "
          f"{failed} failed, {warned} warning(s)")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
