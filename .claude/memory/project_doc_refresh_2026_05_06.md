---
name: Doc refresh 2026-05-06
description: Comprehensive doc-refresh pass covering the last week of changes - ACPX toggle, Skills system, WhatsTlamatini, ACPXer, summarizer one-shot mode, setup-new-acpx-key, regen_secrets, console-window polish
type: project
originSessionId: a7ef3d92-e7e0-467f-b90e-d5d919750e38
---
On 2026-05-06 ran a deep doc-refresh pass mapping all changes since 2026-04-29 into documentation deltas.

**Files updated:**
- `CLAUDE.md` — agent count 57+ → 59; added Skills system + ACPX runtime + ACPX toggle to project identity; expanded project structure tree with `acpx/`, `skills/`, `skills_pkg/`, `teletlamatini/`, `whatstlamatini/`, `acpxer/`; bumped JS module count to 25; updated request flow with ACPX gate step; refreshed @ imports.
- `docs/claude/INDEX.md` — agent count 57 → 59; added Skills mention to mcp-tools.md description; added ACPX toggle to acpx.md description.
- `docs/claude/agents.md` — header "All 60" → "All 59"; added clarifying note that TeleTlamatini/WhatsTlamatini are Action agents (active), not Terminal/Monitoring.
- `docs/claude/acpx.md` — added "ACPX toolbar toggle (per-request enable/disable)" subsection under Definition explaining `ACPX_TOOL_NAMES`, `filter_acpx_tools`, `acpx_enabled` payload flow, and the payload-whitelist requirement.
- `docs/claude/gotchas.md` — added 4 new entries: ACPX toolbar toggle, Summarizer one-shot mode, `setup-new-acpx-key` skill, `regen_secrets.py` two-mode scrubber.
- `Tlamatini/.agents/workflows/create_new_agent.md` — already current.
- `Tlamatini/.mcps/create_new_mcp.md` — added Skill bucket as fourth implementation choice (alongside @tool / wrapped chat-agent / MCP context provider); added `Skill Workflow (SKILL.md package)` section with 6 steps; updated final rule.
- `Tlamatini/agent/agents/flowcreator/agentic_skill.md` — Summarizer entry (#38) now documents both polling and one-shot modes with full config-param details.
- `Tlamatini/agent/agents/flowhypervisor/monitoring-prompt.pmt` — added ACPXer to the structured-output sources list.
- `README.md` — fixed `agents/` tree comment 58 → 59; added `setup-new-acpx-key` as skill #21 in catalog; appended 5 new "Recent Updates" entries (ACPX toolbar toggle, Summarizer one-shot mode, setup-new-acpx-key skill, regen_secrets.py, console-window/icon/restrictive-policy shortcut polish).

**What was already current and required no changes:**
- monitoring-prompt.pmt already had WhatsTlamatini and ACPXer special-notes blocks.
- agentic_skill.md already had entries for TeleTlamatini (#57), ACPXer (#58), WhatsTlamatini (#59).
- README.md "Recent Updates" already had ACPX `oneshot-prompt`, ACPXer, ACPX Reliability Pass, WhatsTlamatini, TeleTlamatini entries.
- create_new_agent.md already covered the ACPXer self-contained-pattern pitfall (#10).

**Why:** user explicitly asked for a deep doc-refresh covering the past week's changes. Documentation as a graph for AI assistants — every surface a less-clever AI in the project might consult should be in sync with the current source.

**How to apply:** when the user asks for "deep update of docs", first audit `git log --since="N days ago"` and check the working tree, then map each change to the doc(s) that own it. Don't paraphrase commits — reference real file paths and behavior.
