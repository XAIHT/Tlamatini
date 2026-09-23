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
Generate the CURRENT skill inventory + version facts from Git and disk.

WHY THIS EXISTS (R21)
---------------------
Skill counts, location lists and "current release" numbers were hand-typed
into several documents and then drifted apart: CLAUDE.md said v1.64.0 was
current, the static-version skill said v1.63.0, and `git describe` said
v1.65.5 — while CLAUDE.md's "permanent skill inventory" described TWO skill
sets when FOUR tracked locations exist. A hand-typed count is a time bomb:
it goes stale silently and then sends the reader to the wrong file.

This script is the ONE canonical facts source. Run it and paste, or run it
with ``--check`` in CI.

Usage:
    python scripts/skill_inventory.py              # human-readable report
    python scripts/skill_inventory.py --json       # machine-readable
    python scripts/skill_inventory.py --check      # non-zero if any
                                                   # location is untracked
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List

REPO = Path(__file__).resolve().parent.parent

#: The FOUR tracked skill locations and who consumes each.
LOCATIONS: List[Dict[str, str]] = [
    {
        "path": "Tlamatini/agent/skills_pkg",
        "label": "Tlamatini application skills",
        "consumer": "Tlamatini herself — loaded by agent/acpx/service.py::"
                    "boot_skills() at app start, invoked by the LLM through "
                    "list_skills / invoke_skill, administered from the "
                    "ACPX-Skills navbar dropdown. SHIPS TO USERS via build.py.",
        "owner": "canonical",
    },
    {
        "path": ".claude/skills",
        "label": "Claude Code maintainer skills",
        "consumer": "Claude Code sessions working ON this repo. Discovered at "
                    "session start. Tracked and pushed PUBLIC.",
        "owner": "canonical",
    },
    {
        "path": ".gemini/skills",
        "label": "Gemini maintainer skills (mirror)",
        "consumer": "Gemini sessions working ON this repo. MIRRORS the "
                    ".claude set — see the synchronization policy below.",
        "owner": "mirror-of:.claude/skills",
    },
    {
        "path": ".codex/skills",
        "label": "Codex documentation skills",
        "consumer": "Codex sessions. Assistant-specific by design; NOT "
                    "mirrored to the other two.",
        "owner": "canonical",
    },
]


def _git(*args: str) -> str:
    try:
        return subprocess.run(
            ["git", *args], cwd=REPO, capture_output=True, text=True,
            check=False,
        ).stdout.strip()
    except Exception:
        return ""


def _tracked_skill_files() -> List[str]:
    out = _git("ls-files", "--", "*SKILL.md")
    return [line.strip().replace("\\", "/") for line in out.splitlines()
            if line.strip()]


def _skill_name(path: Path) -> str:
    """The frontmatter name, falling back to the directory leaf."""
    try:
        for line in path.read_text(encoding="utf-8").splitlines()[:20]:
            if line.startswith("name:"):
                return line.split(":", 1)[1].strip().strip("'\"")
    except Exception:
        pass
    return path.parent.name


def collect() -> Dict[str, Any]:
    tracked = set(_tracked_skill_files())
    on_disk_untracked: List[str] = []
    locations: List[Dict[str, Any]] = []

    for loc in LOCATIONS:
        root = REPO / loc["path"]
        prefix = loc["path"].rstrip("/") + "/"
        files = sorted(f for f in tracked if f.startswith(prefix))
        names = sorted({_skill_name(REPO / f) for f in files})
        if root.exists():
            for p in sorted(root.rglob("SKILL.md")):
                rel = p.relative_to(REPO).as_posix()
                if rel not in tracked:
                    on_disk_untracked.append(rel)
        locations.append({**loc, "count": len(files), "names": names,
                          "files": files})

    described = sum(len(x["files"]) for x in locations)
    return {
        "head": _git("rev-parse", "--short", "HEAD"),
        "describe": _git("describe", "--tags"),
        "nearest_tag": _git("describe", "--tags", "--abbrev=0"),
        "tracked_skill_md_total": len(tracked),
        "described_by_this_inventory": described,
        "unaccounted_files": sorted(
            f for f in tracked
            if not any(f.startswith(x["path"].rstrip("/") + "/")
                       for x in LOCATIONS)
        ),
        "untracked_on_disk": on_disk_untracked,
        "locations": locations,
    }


def main(argv: List[str]) -> int:
    facts = collect()
    if "--json" in argv:
        print(json.dumps(facts, indent=2))
    else:
        print("=== Tlamatini skill inventory (generated) ===")
        print(f"HEAD            : {facts['head']}")
        print(f"git describe    : {facts['describe']}")
        print(f"nearest tag     : {facts['nearest_tag']}")
        print(f"tracked SKILL.md: {facts['tracked_skill_md_total']}")
        print()
        for loc in facts["locations"]:
            print(f"-- {loc['path']}  ({loc['count']})  [{loc['owner']}]")
            print(f"   {loc['label']}")
            print(f"   consumer: {loc['consumer']}")
            print(f"   names: {', '.join(loc['names'])}")
            print()
        if facts["unaccounted_files"]:
            print("!! SKILL.md OUTSIDE every known location:")
            for f in facts["unaccounted_files"]:
                print(f"   {f}")
        if facts["untracked_on_disk"]:
            print("!! UNTRACKED on disk (a skill that disappears on clone):")
            for f in facts["untracked_on_disk"]:
                print(f"   {f}")

    if "--check" in argv:
        problems = facts["unaccounted_files"] + facts["untracked_on_disk"]
        if problems:
            print(f"[skill-inventory] FAIL: {len(problems)} problem(s)",
                  file=sys.stderr)
            return 1
        print("[skill-inventory] OK: every SKILL.md is tracked and located")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
