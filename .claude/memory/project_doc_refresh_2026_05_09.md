---
name: Doc refresh 2026-05-09
description: CLAUDE.md + docs/claude/* updated for Flow Compiler / Agent Contracts (commit 0bea21d), agents_descriptions.md authoritative tooltip source (88dd99b), TeleTlamatini three-flag bridging (1287e56), SuppressHttpGet200 log filter (8bb4047), and FlowCreator added to the 60-agent catalog
type: project
originSessionId: ee628161-0643-45df-ad17-1919d3121c35
---
On 2026-05-09 the assistant updated the AI-onboarding doc set to capture five surgical changes that landed between 2026-05-07 and 2026-05-09 and were not yet documented:

1. **Flow Compiler + Agent Contracts pipeline (commit `0bea21d`, 2026-05-09)**
   - New backend services: `agent/services/agent_contracts.py`, `agent/services/agent_paths.py`, `agent/services/flow_spec.py`, `agent/services/flow_compiler.py`
   - New JS bridge: `agent/static/agent/js/acp-flow-snapshot.js` (`buildACPFlowSnapshot()` + `compileCurrentACPFlow()`)
   - New endpoints: `POST /agent/compile_flow/`, `POST /agent/flow_from_tool_calls/`, `GET /agent/agent_contracts/`
   - Start sequence (`acp-control-buttons.js`) now calls `compileCurrentACPFlow({mode:'write'})` before launching agents — so an edited-but-unsaved canvas now compiles through the same Agent Contract pass as a fresh `.flw` load
   - Chat Create-Flow (`agent_page_chat.js`) now POSTs the legacy draft to `/agent/flow_from_tool_calls/` for backend normalization + secret redaction; falls back to legacy if backend unreachable
   - Validate dialog (`acp-validate.js`) uses `mode='dry_run'` and renders the same compiled-config preview without writing
   - Coverage: `Tlamatini/agent/test_flow_contracts.py`

2. **agents_descriptions.md authoritative tooltip source (commit `88dd99b`, 2026-05-08)**
   - New file at repo root parsing the `## Workflow Agents` markdown tables
   - `agent/views.py::_load_agent_purpose_map()` now resolves `agents_descriptions.md` first, then falls back to `README.md`
   - `build.py` ships `agents_descriptions.md` next to the executable in frozen mode
   - `acp-canvas-core.js::showAgentPurposeTooltip` and `contextual_menus.js::openDescriptionDialog` updated to mention `agents_descriptions.md` instead of `README.md` in their fallback strings
   - `regen_secrets.py` extended to scrub `emailer/config.yaml` (`smtp.username/password`) and `recmailer/config.yaml` (`imap.username/password`) — Gmail app-password fields

3. **TeleTlamatini three-flag bridging (commit `1287e56`, 2026-05-08)**
   - `agent/agents/teletlamatini/teletlamatini.py` `TlamatiniBridge.__init__` now accepts `acpx_enabled`, includes it in the request envelope, and logs it
   - `agent/agents/teletlamatini/config.yaml` ships `acpx_enabled: true` (resolver default stays `False` for legacy-deploy backstop)
   - WhatsTlamatini is the next mirror candidate — same wiring needed when user requests it

4. **SuppressHttpGet200 generalized log filter (commit `8bb4047`, 2026-05-07)**
   - `Tlamatini/tlamatini/logging_filters.py` renamed `SuppressRuntimePollerOk` → `SuppressHttpGet200` (drops any GET/200, not just `/agent/check_chat_runtimes_status/`)
   - `Tlamatini/tlamatini/settings.py` filter rebound: `suppress_runtime_poller_ok` → `suppress_http_get_200`

5. **60-agent catalog (was 59)**
   - The catalog in `docs/claude/agents.md` listed 59 because **FlowCreator was never present in the catalog** (only mentioned in the FlowCreator AI Skill section)
   - On-disk count is 60 directories. agents_descriptions.md correctly lists 60. CLAUDE.md / agents.md / INDEX.md now updated to 60 across the board

Files touched in this doc refresh:
- `CLAUDE.md` — agent count 59→60, Flow Compiler bullet under Project Identity, agents_descriptions.md/BookOfTlamatini.md added to repo-root tree, services/ subitems expanded, JS module count 26→27, request-flow steps 10/11 expanded with Create-Flow normalization + Start sequence compile, doc index `Agents` description updated to 60
- `docs/claude/INDEX.md` — agent count 60, Flow Compiler / agents_descriptions.md / 13 ACP modules / SuppressHttpGet200 / TeleTlamatini three-flag descriptions added per file
- `docs/claude/architecture.md` — new "Services Layer" section listing the 7 service files with their roles and the 3 new endpoints
- `docs/claude/agents.md` — new top section "Backend Agent Contract Registry" documenting the AgentContract dataclass; FlowCreator added to Utility Agents catalog; "All 59" → "All 60" with a note pointing to agents_descriptions.md
- `docs/claude/multi-turn.md` — Create-Flow pipeline expanded from 5 steps to 7 steps to capture the backend-normalization round-trip
- `docs/claude/frontend.md` — `acp-flow-snapshot.js` documented in ACP modules list; `acp-file-io.js` and `acp-validate.js` descriptions updated; total module count 26→27; new "Flow Compiler Pipeline" section explaining the canvas-and-chat dual entrypoint
- `docs/claude/gotchas.md` — 4 new "Recent Fixes / Gotchas" bullets: Flow Compiler + Agent Contracts, agents_descriptions.md, TeleTlamatini three-flag, SuppressHttpGet200, plus a Whatsapper-vs-WhatsTlamatini disambiguation reminder

The user invoked this update on the worktree branch `claude/wizardly-khorana-4dd9a3` (harness-created); per `feedback_main_branch_only.md` the changes need to be collapsed into `main` and the branch deleted before session end, but per `feedback_user_owns_git.md` state-mutating git operations require explicit user request — so the assistant left commits / merges / pushes to the user.
