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
Keep `.gemini/skills/` in step with `.claude/skills/`.

WHY THIS EXISTS (R15)
---------------------
The five maintainer skills exist twice, once per assistant. Three pairs were
byte-identical; **agent-creation and daily-chat-test had silently drifted**,
with the Gemini copies missing Claude-side additions about modifying an
existing agent, Whisperer's sentinel default and monitoring bounds, the
corrected Parametrizer prose, the PDFer rendering/measurement lessons and the
style guidance. Nothing enforced the mirror, so the drift was invisible.

THE POLICY
----------
* **`.claude/skills/` is the SOURCE.** `.gemini/skills/` is a MIRROR.
* ⚠️ **Correct a shared mistake in the SOURCE before syncing.** Blind copying
  propagates stale instructions — that is how this drift accumulated.
* Only the SKILL.md bodies are mirrored. Harness helper scripts under
  `.claude/skills/tlamatini-daily-chat-test/harness/` are Claude-session
  tooling and are deliberately NOT copied.
* A few literals are assistant-specific and are rewritten on the way across —
  see ``PATH_REWRITES``. Everything else must match byte for byte.

Usage:
    python scripts/sync_assistant_skills.py            # report drift
    python scripts/sync_assistant_skills.py --check    # non-zero on drift (CI)
    python scripts/sync_assistant_skills.py --write    # propagate source->mirror
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import List, Tuple

REPO = Path(__file__).resolve().parent.parent
SOURCE_ROOT = REPO / ".claude" / "skills"
MIRROR_ROOT = REPO / ".gemini" / "skills"

#: The five mirrored maintainer skills.
MIRRORED: Tuple[str, ...] = (
    "tlamatini-agent-creation",
    "tlamatini-agent-naming",
    "tlamatini-daily-chat-test",
    "tlamatini-self-modify-inclusion",
    "tlamatini-self-update-inclusion",
)

#: Literals that are legitimately assistant-specific. Applied source -> mirror.
#: Keep this list SHORT: every entry is a place the two copies may differ, and
#: an entry added carelessly hides real drift.
PATH_REWRITES: Tuple[Tuple[str, str], ...] = (
    (".claude/skills/", ".gemini/skills/"),
    (".claude\\skills\\", ".gemini\\skills\\"),
)


def _expected_mirror_text(source_text: str) -> str:
    out = source_text
    for old, new in PATH_REWRITES:
        out = out.replace(old, new)
    return out


def _normalize(text: str) -> str:
    """Compare content, not line endings (a CRLF-only diff is not drift)."""
    return text.replace("\r\n", "\n").replace("\r", "\n")


def collect() -> List[dict]:
    rows: List[dict] = []
    for name in MIRRORED:
        src = SOURCE_ROOT / name / "SKILL.md"
        dst = MIRROR_ROOT / name / "SKILL.md"
        if not src.exists():
            rows.append({"skill": name, "state": "source_missing",
                         "src": src, "dst": dst})
            continue
        source_text = src.read_text(encoding="utf-8")
        expected = _expected_mirror_text(source_text)
        if not dst.exists():
            rows.append({"skill": name, "state": "mirror_missing",
                         "src": src, "dst": dst, "expected": expected})
            continue
        actual = dst.read_text(encoding="utf-8")
        state = ("in_sync" if _normalize(actual) == _normalize(expected)
                 else "drifted")
        rows.append({"skill": name, "state": state, "src": src, "dst": dst,
                     "expected": expected})
    return rows


def main(argv: List[str]) -> int:
    write = "--write" in argv
    check = "--check" in argv
    rows = collect()
    drift = 0

    for row in rows:
        state = row["state"]
        if state == "in_sync":
            print(f"[OK]     {row['skill']}")
            continue
        if state == "source_missing":
            print(f"[FAIL]   {row['skill']}: source missing ({row['src']})")
            drift += 1
            continue
        drift += 1
        if write:
            row["dst"].parent.mkdir(parents=True, exist_ok=True)
            # ⚠️ newline="" — do NOT use Path.write_text here. On Windows it
            # translates every "\n" to "\r\n", which rewrites every line of an
            # LF file and buries the real change under thousands of lines of
            # pure line-ending churn.
            with open(row["dst"], "w", encoding="utf-8", newline="") as fp:
                fp.write(row["expected"])
            print(f"[SYNCED] {row['skill']}: mirror updated from source")
        else:
            print(f"[DRIFT]  {row['skill']}: {state} "
                  f"— run with --write to propagate")

    if write:
        print(f"[sync-skills] {drift} mirror(s) written")
        return 0
    if check and drift:
        print(f"[sync-skills] FAIL: {drift} skill(s) out of sync",
              file=sys.stderr)
        return 1
    print(f"[sync-skills] {len(rows) - drift}/{len(rows)} in sync")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
