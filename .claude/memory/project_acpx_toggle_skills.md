---
name: ACPX toolbar toggle + Skills system
description: 2026-05-06 - acpx_enabled WebSocket flag filters the 12-tool ACPX/Skill surface per-request via agent.acpx.filter_acpx_tools(); 21 SKILL.md packages live under agent/skills_pkg/
type: project
originSessionId: a7ef3d92-e7e0-467f-b90e-d5d919750e38
---
<!--
═══════════════════════════════════════════════════════════════════
  ✦  T L A M A T I N I  ✦   —   "one who knows"
  Created by  Angela López Mendoza   ·   @angelahack1
  Developer · Architect · Creator of Tlamatini
  Tlamatini Author Banner — do not remove (Angela's name is kept in every build)
═══════════════════════════════════════════════════════════════════
-->
The chat toolbar now exposes three checkboxes side-by-side: **Multi-Turn**, **Exec Report**, **ACPX**. The third sends `acpx_enabled` on every WebSocket frame.

- `agent/acpx/__init__.py` exposes `ACPX_TOOL_NAMES` (frozenset) and `filter_acpx_tools(tools, acpx_enabled)`.
- `agent/rag/interface.py::ask_rag` reads `acpx_enabled` (defaults `True`), pipes it into the chain payload.
- `agent/rag/chains/unified.py::UnifiedAgentChain.invoke` — `acpx_enabled` MUST stay in the payload-rebuild whitelist (same drop-on-rebuild bug class as `exec_report_enabled`).
- When `acpx_enabled=False`, the planner/executor never see the 12 ACPX/Skill tools (`acp_spawn`, `acp_send`, `acp_send_and_wait`, `acp_kill`, `acp_doctor`, `acp_transcript`, `acp_session_status`, `acp_list_sessions`, `acp_relay`, `list_acp_agents`, `invoke_skill`, `list_skills`).
- `bypass_prompt_validation = multi_turn_enabled OR acpx_enabled` — so the prompt-shape validator is skipped when only ACPX is checked.

**Skills system** lives at `agent/skills_pkg/<name>/SKILL.md`:
- 21 seed packages (hello-world, skill-creator, acp-router, summarize, weather, github/gmail/jira/notion/slack/todoist/trello, 8 tlamatini-* internal helpers, **setup-new-acpx-key** added 2026-05-06).
- Discovered by `agent/skills/registry.py` (30s staleness cap, parse failures skipped with logger warning, never crashes startup).
- Validated by `agent/skills_pkg/_meta/schema.json` + `lint.py`.
- LLM invokes via `list_skills` / `invoke_skill(skill_name, args_json)` — both LIVE on the ACPX surface so the toggle gates them too.
- Adding a 22nd skill: drop a directory, no Python edits, no migration, no UI.

**Why:** the toggle was added so the user can fall back to legacy chat-agent flows mid-session without restarting Django; the Skills system was added to give the LLM procedural runbooks (e.g. `setup-new-acpx-key` end-to-end credential injection) without writing new `@tool` code.

**How to apply:** when the user says "turn off ACPX" or "use only chat-agent tools", that's the toolbar checkbox. When they ask "is there a skill for X?", grep `agent/skills_pkg/*/SKILL.md`. When they want to inject an ACPX credential, prefer `invoke_skill('setup-new-acpx-key', {...})` over hand-editing config.json.
