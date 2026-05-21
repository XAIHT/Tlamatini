# docs/claude/ — Tlamatini AI-Assistant Docs Index

This directory holds the specialized onboarding documents that back the root `CLAUDE.md`. The root file imports each of these via `@docs/claude/<name>.md` so that every assistant session loads the full set automatically.

One-line descriptions:

- **architecture.md** — Configuration, system prompt & identity, the Five Layers of the system, application log (`tlamatini.log`), doc generation pipeline, **`agent/services/` layer** (response post-processing + agent contracts + flow compiler), database models.
- **multi-turn.md** — Multi-Turn mode, short follow-up message scoring, "Create Flow" pipeline (now backend-normalized via `/agent/flow_from_tool_calls/`), unified section format used by Parametrizer.
- **exec-report.md** — The Exec Report feature end-to-end: scope map, capture/render pipeline, strict ordering contract, styling, how to add a new state-changing agent to the report.
- **agents.md** — Backend Agent Contract registry (`agent/services/agent_contracts.py`), 8-step guide for creating a new workflow agent, naming convention transforms, agent lifecycle, connection fields, catalog of all 65 agent types (including FlowCreator, TeleTlamatini, WhatsTlamatini, ACPXer, Reviewer, Analyzer, Playwrighter), FlowCreator AI skill, FlowHypervisor monitoring.
- **acpx.md** — ACPX (Agent Communication Protocol eXtension): authoritative definition, the 14-agent registry with transport profiles, all 12 LLM-facing tools, canonical flows (spawn-and-go, multi-CLI relay, harvest-transcript, skill-routing), runtime drain mechanics, permission model, the **ACPX toolbar toggle** (per-request enable/disable via `agent.acpx.filter_acpx_tools()`, defaults to OFF), and the "when the user says ACPX" decision matrix.
- **mcp-tools.md** — How to add a new MCP-backed context provider, a unified-agent tool, a wrapped chat-agent tool, **OR** a Skill (`agent/skills_pkg/<name>/SKILL.md` driven by `SkillHarness`); plus the hardcoded-assumption warnings around `factory.py` and the MCP UI; plus the **ACPX-Skills navbar dropdown** (Browse / Configure / Diagnostics / Reload — admin surface for the 23 SKILL.md packages).
- **frontend.md** — Chat interface modules, ACP workflow designer modules (now 13 incl. `acp-flow-snapshot.js`), the **ACP Canvas DOM Contract** (`#submonitor-container` vs `#canvas-content`), the **Flow Compiler Pipeline** (canvas snapshot AND chat Create-Flow → backend `/agent/compile_flow/` and `/agent/flow_from_tool_calls/`), shared modules.
- **gotchas.md** — Claude API client, build/packaging/linting commands, known hardcoded assumptions, recent fixes to remember (incl. Flow Compiler pipeline, `agents_descriptions.md` authoritative tooltip source, TeleTlamatini three-flag bridging, `SuppressHttpGet200` log filter), roadmap of recommended new agents, work-style preferences for AI assistants.

Read order when joining the project cold: root `CLAUDE.md` → `architecture.md` → `multi-turn.md` → `exec-report.md` → `agents.md` → `acpx.md` → `mcp-tools.md` → `frontend.md` → `gotchas.md`.
