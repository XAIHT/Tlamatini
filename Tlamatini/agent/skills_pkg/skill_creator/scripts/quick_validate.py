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

⚠️ This is the SAME validator the catalog lint runs
(``agent/skills/validation.py``) — it is "quick" only because it checks one
package instead of all of them, never because it checks less.

It used to be a different validator: it substring-matched ``name:`` and
``description:`` without parsing YAML (despite its docstring claiming
otherwise) and applied a 12,288-character WHOLE-FILE ceiling where the linter
applied an 8 KiB body cap. A package could therefore pass here and fail there,
or vice versa. **Never reintroduce a local rule in this file.**

Exit codes:
    0  valid (warnings may still be printed)
    1  invalid — the registry would refuse it
    2  usage error
"""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
# .../agent/skills_pkg/skill_creator/scripts -> .../Tlamatini (the app root)
APP_ROOT = HERE.parent.parent.parent.parent
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

from agent.skills.validation import validate_skill_dir  # noqa: E402


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: quick_validate.py <skill_dir>")
        return 2
    result = validate_skill_dir(Path(argv[1]).resolve())
    for f in result.warnings:
        print(f"[WARN] {result.path}: {f.code}: {f.message}")
    if result.errors:
        for f in result.errors:
            print(f"[FAIL] {result.path}: {f.code}: {f.message}")
        return 1
    print(f"[OK] {result.path}: name={result.name!r} "
          f"runtime={result.runtime} "
          f"body={result.body_bytes}B ({result.body_chars} chars)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
