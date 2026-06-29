---
name: Doc refresh 2026-05-08
description: Cross-cutting doc audit and surgical fixes to CLAUDE.md, docs/claude/exec-report.md, docs/claude/frontend.md, and README.md to align with the last 2 weeks of code changes (ACPX oneshot-prompt, ACPXer, summarizer one-shot, ACPX toolbar toggle, Keyboarder/Mouser/Shoter wraps, desktop-UI lifecycle, sleeper/run_wait/window_present, BEGIN-DIAGRAM rule, HTTP-GET log filter)
type: project
originSessionId: 9c2429cb-a648-4a50-bb58-be921153b678
---
<!--
═══════════════════════════════════════════════════════════════════
  ✦  T L A M A T I N I  ✦   —   "one who knows"
  Created by  Angela López Mendoza   ·   @angelahack1
  Developer · Architect · Creator of Tlamatini
  Tlamatini Author Banner — do not remove (Angela's name is kept in every build)
═══════════════════════════════════════════════════════════════════
-->
User asked for a thorough re-audit of CLAUDE.md and README.md vs actual code state on 2026-05-08, after a sequence of surgical changes landed across the last 2 weeks. Findings + fixes:

**Why:** Docs had drifted in several measurable ways (counts, lists, latest migration, JS module count, missing wrapped-tool entries) and the "Recent Updates" changelog was not capturing the latest 5 commits.

**How to apply:** When the user asks for a doc-refresh pass, the canonical drift-points to check first are:

1. **Counts** — `_EXEC_REPORT_TOOLS` map entries (currently includes `chat_agent_keyboarder`, `chat_agent_mouser`, `acp_send_and_wait`, `acp_relay`); skills count (now 21 incl. `setup-new-acpx-key`); wrapped chat-agent count (now 36 in `chat_agent_registry.py`); JS module count (now 26 — 8 chat + 12 ACP + 1 ACP entry + 5 shared); follow-up runtime tools (now 6 — added `chat_agent_run_wait` + `window_present`).
2. **Latest migration** — currently `0081_add_window_present_and_run_wait_tools.py` (was `0077_add_whatstlamatini` in CLAUDE.md tree).
3. **README "Recent Updates" changelog** — prepend new entries above the existing topmost one (which is "ACPX Toolbar Toggle").
4. **README wrapped chat-agent list** (line ~1685) was missing `chat_agent_asker`, `chat_agent_keyboarder`, `chat_agent_mouser`, `chat_agent_sleeper`.
5. **README "wrapped 32" inside the ACPX ASCII diagram** at line ~3559 → bumped to 36 + listed all 12 ACPX tools.
6. **README "Tools" tables (Available Tools section ~line 1990)** were missing the new wrapped families and follow-up tools.

Files I edited this pass:
- `CLAUDE.md` (latest-migration line, JS module count, agents.md count "57-type" → "59-type")
- `docs/claude/exec-report.md` (added `chat_agent_mouser`, `acp_send_and_wait`, `acp_relay` to the map block + state-changing comment update)
- `docs/claude/frontend.md` (12 ACP modules + restructured shared module list + "Total: 26 JS modules" footer)
- `README.md` (multiple count fixes + 5 prepended changelog entries for the May 2026 surgical changes + Multi-Turn toolbar description bumped from "two modifiers" to "four modifiers" with the ACPX checkbox + ACPX block + new desktop-UI tools table + 6 lifecycle tools table + skill count 20 → 21 in five places)

What was NOT changed and why:
- Historical changelog entries that mention "32 wrapped" or "11 ACPX tools" — those describe the state at the time of that commit and falsifying them would corrupt the changelog as a historical record.
- `pools/` is an empty placeholder directory inside `agent/agents/` — the count remains 59 actual workflow-agent types (not 60).
