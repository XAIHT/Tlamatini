<!--
═══════════════════════════════════════════════════════════════════
  ✦  T L A M A T I N I  ✦   —   "one who knows"
  Created by  Angela López Mendoza   ·   @angelahack1
  Developer · Architect · Creator of Tlamatini
  Tlamatini Author Banner — do not remove (Angela's name is kept in every build)
═══════════════════════════════════════════════════════════════════
-->
# Tlamatini — Creating a New MCP or Tool

**Full guide**: `Tlamatini/.mcps/create_new_mcp.md`

## First Decision: Classify the request

| Type | Description | Example |
|------|-------------|---------|
| **Tool only** | Model performs an action on demand during unified-agent execution | run command, start agent, unzip, decompile |
| **MCP-backed context provider only** | System fetches context before the main chain responds | system metrics, file search, inventory |
| **Both** | Needs pre-fetched context AND a separate action tool | Rare - most are one or the other |

> **Not in this table: External MCPs.** The config-driven **universal MCP client** (the "External MCPs" era, 2026-06) is a fourth, clearly-separate surface — it lets Tlamatini use the tools of ANY external MCP server declared in a JSON catalog, with no per-server code. It is NOT one of the two `Mcp`-model context-provider checkboxes, NOT a `@tool`, NOT a wrapped chat-agent, and NOT ACPX. See **External MCPs (config-driven universal MCP client)** below.

## Tool-Only Workflow
1. Implement `@tool` function in `tools.py` (sync, returns strings)
2. Resolve bundled paths for both frozen and source modes
3. Register in `get_mcp_tools()` under a `global_state` gate
4. Seed a `Tool` row via new migration
5. Frontend: usually NO changes needed (tool UI is dynamic)
6. Only usable in unified-agent mode

## MCP Context Provider Workflow
1. Create `mcp_<name>_server.py` + `mcp_<name>_client.py`
2. Create sidecar chain `chain_<name>_lcel.py`
3. Wire startup in `apps.py` + `startserver.py`
4. Extend `factory.py` (import, sync wrapper, status key mapping, patched invoke)
5. Choose payload field and update all main chains
6. Seed `Mcp` row + update frontend MCP checkboxes (hardcoded, not dynamic!)
7. Verify persistence and reconnect behavior

## Key Warnings
- `factory.py` recognizes ONLY `System-Metrics` and `Files-Search` by description
- MCP UI is hardcoded for two checkboxes (unlike dynamic tool UI)
- `get_mcp_tools()` returns LangChain tools, NOT MCP services
- Tool status keys are handwritten and can drift from seeded DB descriptions
- Adding `Mcp` row without extending `factory.py` does NOTHING
- "MCP" in the two `Mcp`-model checkboxes is unrelated to the **external MCP servers** that some pool agents drive (e.g. STM32er → STM32 Template Project MCP, Kalier → MCP-Kali-Server). Those agents bundle a **self-contained inline MCP/JSON-RPC client** in `agents/<name>/<name>.py` (stdlib-only, no `mcp` dep in the pool) so they work identically in source and frozen builds — they do NOT go through `factory.py` or the `Mcp` toggle rows. STM32er additionally **self-provisions** its server: with an empty `stm32_mcp_server_script` it auto-bootstraps the MCP (git clone → GitHub-zip fallback → pip-install `mcp`+`pyserial`) on first use.

---

## External MCPs (config-driven universal MCP client)

A separate, config-driven runtime — added in the **"External MCPs" era** (week of 2026-06-09 → 2026-06-17) — that lets Tlamatini use the tools of **ANY external MCP server** declared in a JSON file, with **no hardcoding**. The catalog uses the same `mcpServers` shape Claude Code's `.mcp.json` uses, so a server config copied from Claude Code drops straight in.

This is **distinct from all three of the surfaces above** — see the contrast block at the end of this section.

### Engine & catalog

- **Engine**: `agent/external_mcp_manager.py`.
- **Catalog**: `agent/external_mcps.json`, resolved **next to `config.json`** (install root in frozen mode, `agent/` in source). It is **USER STATE** — preserved across self-update (like `config.json` / the DB) and **redacted** in the self-modify snapshot.
- **Active set is capped at 5** (`MAX_ACTIVE`) — only the active servers' tools are bound for the LLM; the rest stay catalogued but dormant.
- **Connects LAZILY on a background thread**, so building the chat chain never stalls waiting on a slow server. 60 s connect timeout (override via env `TLAMATINI_EXTERNAL_MCP_CONNECT_TIMEOUT`), a **negative-cache cooldown** so a dead server isn't retried every turn, and a **supervisor** that relists/reconnects servers that came up reporting zero tools.

### Transports (4 connectable, 2 diagnosed-only)

All four connectable transports share a single `_NetworkMcpClientBase` (one MCP handshake) and expose the same public surface; `_make_client` / `_connect` dispatch by the spec's transport:

| Transport | For | Backed by |
|---|---|---|
| `stdio` | a local child process (the original transport) | subprocess |
| `streamable-http` | an already-running HTTP MCP server | `httpx` |
| `sse` | a legacy SSE MCP server | `httpx` |
| `websocket` | an already-running WebSocket MCP server | `websockets` |

`tcp` / `named-pipe` are **detected and diagnosed** (the doctor explains why) but are **NOT yet connectable** — a clear blocker, not a silent failure. Each remote tool is wrapped as a LangChain tool named **`ext__<server>__<tool>`**.

### The 8 LLM-facing supervisor tools

Defined in `external_mcp_manager.py::_SUPERVISOR_TOOL_NAMES`. All return a JSON envelope (they never raise):

| Tool | What it does |
|---|---|
| `external_mcp_status` | current catalog + active set + per-server connection state |
| `external_mcp_reconnect` | force a reconnect of a server (or all) |
| `external_mcp_doctor` | per-server triage (transport, runtime, command-on-PATH, placeholder secrets, blockers, next step) |
| `external_mcp_list_tools` | enumerate the tools a connected server exposes |
| `external_mcp_call` | call one external tool directly |
| `external_mcp_import` | add server(s) to the catalog from a JSON object **OR** a JSON string |
| `external_mcp_set_active` | set the active set (a list **OR** a comma-string), capped at ≤5 |
| `external_mcp_wait` | **BLOCKS** until a slow server is ready (e.g. a first-run Docker image pull) instead of polling-and-giving-up |

These are **force-bound and capability-hinted** for MCP-setup intents (`global_execution_planner._external_mcp_force_names`, `capability_registry._EXTRA_HINTS_BY_TOOL_NAME`), so the LLM reliably reaches for them when the user asks to add/activate/troubleshoot an external MCP. The executor refreshes the `ext__*` tool slice per request via `mcp_agent._refresh_external_mcp_tool_surface`.

> **NOT ACPX tools.** The 8 supervisor tools (and the `ext__*` wrappers) are **NOT** in `agent.acpx.ACPX_TOOL_NAMES` and are **NOT** gated by the ACPX toolbar checkbox. They are only gated by Multi-Turn, exactly like any other unified-agent tool.

### Frontend — "External ▸ MCPs" navbar dialog

A navbar dialog (`static/agent/js/external_mcps_dialog.js` + `css/external_mcps_dialog.css`): a searchable catalog, tick ≤5 to activate, a summary table, and **drag-a-`.json`-onto-the-dialog to import** servers. Three endpoints (all `@login_required`):

| Endpoint | Method | Role |
|---|---|---|
| `/agent/external_mcps/` | GET | catalog + active set + per-server state |
| `/agent/external_mcps/activate/` | POST | set the active set (≤5) |
| `/agent/external_mcps/import/` | POST | import server(s) from posted JSON |

### Bulletproof contract (do NOT weaken)

- **Connects run OFF the chat-build path** (background thread) — a slow or hung server can never delay the answer.
- A **bad / unreachable / unsupported** server degrades to a **catalogued-with-reason** entry (the doctor's blocker/next-step). It never crashes the chain and never hangs the build.
- **Auth**: spec `headers` (e.g. `Bearer …`) + env injection.
- **BOM-tolerant** catalog read (`utf-8-sig`).
- The **command watchdog exempts the live external-MCP child PIDs** (`external_mcp_root_pids`) so its idle-child reaper never kills a healthy MCP server.
- Full design contract: `docs/external_mcp_bulletproof_architecture.md` (consult-on-demand, not auto-imported).

### Static triage from chat: the MCP Doctor agent (#78)

The **MCP Doctor** workflow agent (canvas + wrapped `chat_agent_mcp_doctor`) does **STATIC catalog triage with no live connect**: transport, runtime (docker / npx / uvx / python / node / …), command-on-PATH, placeholder-secret detection, blockers, and a next-step. It emits `INI_SECTION_MCP_DOCTOR` (a Parametrizer source) and is captured automatically in the Exec Report. Seeded by migrations 0141/0142/0143 (Agent row / `Chat-Agent-MCP-Doctor` Tool row / demo prompt 81). See `docs/claude/agents.md` (MCP Doctor entry).

### Contrast: External MCPs vs the other MCP-ish surfaces

| Surface | What it is | Wiring |
|---|---|---|
| **External MCPs (this)** | Universal client — use ANY external MCP server from a JSON catalog | `external_mcp_manager.py` + `external_mcps.json` + 8 supervisor tools + the `ext__*` wrappers; **no** `factory.py` / `Mcp`-row / `@tool` edits |
| **The two `Mcp`-model checkboxes** | The built-in context providers `System-Metrics` / `Files-Search` that inject `system_context` / `files_context` **before** the chain answers | `Mcp` rows + hardcoded `factory.py` recognition + the hardcoded two-checkbox UI |
| **ACPX** | Spawns external **coding-agent CLIs** (claude / codex / gemini / …) as child processes, brokered as the 12 `acp_*` tools | `agent/acpx/*`; gated by the **ACPX** toolbar checkbox |
| **Per-agent inline MCP clients** (STM32er / Kalier) | A single pool agent drives ONE specific external MCP server via a stdlib-only inline client | inline in `agents/<name>/<name>.py`; no `factory.py` / `Mcp` rows |

---

## ACPX-Skills admin menu (navbar dropdown)

The chat navbar has a dedicated **ACPX-Skills** dropdown (between **Agents** and **Config**) that admins every SKILL.md package under `agent/skills_pkg/`. Four entries:

| Entry | Backing endpoint | What it does |
|---|---|---|
| **Browse Skills** | `GET /agent/skills/` + `GET /agent/skills/<name>/` | List + detail pane with frontmatter, requires, inputs/outputs, permissions, body. Search/filter included. |
| **Configure Skills** | WebSocket `set-skills` (mirrors `set-mcps` / `set-agents`) | Checkbox grid toggling `Skill.enabled` per row. Payload encoding: comma-separated `name=description=true/false`. |
| **Diagnostics** | `GET /agent/skills/_/diagnostics/` | Cross-checks every skill's `requires_tools` / `requires_mcps` against disabled `Tool` / `Mcp` rows; flags `runtime: acpx` skills whose `acpx_agent` isn't a known `AcpAgent`; surfaces orphan DB rows. |
| **Reload Registry** | `POST /agent/skills/_/reload/` | Re-runs `agent.acpx.service.boot_skills()` — re-scans `skills_pkg/`, refreshes Skill rows, prunes deleted ones. No server restart needed. |

### Persistence shape — minimal by design

The DB stays at "enumeration + enable/disable" only (mirrors `Tool` / `Mcp` / `Agent`). No per-user overrides of permissions, budgets, or descriptions live in the DB — the SKILL.md frontmatter on disk is the only source of truth. The pre-existing `Skill` model (created in migration `0071_acpx_skills.py`) has vestigial cache fields (`frontmatter_json`, `body_sha256`) that `boot_skills()` keeps in sync, but the admin UI deliberately ignores them and reads fresh from `skill_registry`.

### Tool-surface gating

When `Skill.enabled = False`:
- `list_skills` (`agent/acpx/tools.py`) filters the row out of its output.
- `invoke_skill` returns `{"ok": false, "code": "SKILL_DISABLED"}`.

Implemented via `_disabled_skill_names()` in `agent/acpx/tools.py` — fails open (empty set on any DB exception) so a broken admin layer never silently hides skills.

### WebSocket wiring (mirrors Mcps / Agents / Tools)

- `consumers.AgentConsumer.skill_establishment()` sends one `type: 'skill'` system message per skill on connect (both rebuild and session-restore paths).
- The frontend (`agent_page_chat.js`) catches those and pushes into the module-level `skills = []` array (declared in `agent_page_state.js`).
- The Configure dialog (`skills_dialog.js::preRenderSkillsConfigureDialog`) reads from that array; Continue dispatches `set-skills` via `sendChatSocketMessage`.
- Backend `set-skills` handler in `consumers.receive()` parses the payload and calls `save_skill(name, enabled)` which touches only `Skill.enabled` (other fields owned by `boot_skills()`).

### Files

| Path | Role |
|---|---|
| `agent/views.py` (`list_skills_view`, `skill_detail_view`, `reload_skills_view`, `skills_diagnostics_view`) | HTTP endpoints |
| `agent/urls.py` | Routes: `/agent/skills/`, `/agent/skills/<name>/`, `/agent/skills/_/reload/`, `/agent/skills/_/diagnostics/` |
| `agent/consumers.py` (`skill_establishment`, `get_all_skills`, `save_skill`, `set-skills` handler) | WebSocket layer |
| `agent/acpx/tools.py` (`_disabled_skill_names`) | Tool-surface gating |
| `agent/templates/agent/agent_page.html` | Navbar dropdown + 3 dialog containers + asset includes |
| `agent/static/agent/js/skills_dialog.js` | jQuery-UI dialogs (Configure / Browse / Diagnostics / Reload) |
| `agent/static/agent/js/agent_page_init.js` | `OpenSkillsXyzDialog` + `ReloadSkillRegistry` entry points |
| `agent/static/agent/js/agent_page_chat.js` | `type: 'skill'` system-message handler |
| `agent/static/agent/js/agent_page_state.js` | `let skills = []` global |
| `agent/static/agent/css/skills_dialog.css` | Styling |
| `agent/tests.py` (`SkillsAdminEndpointTests`, `SkillsToolSurfaceGatingTests`, `SkillsNavbarTemplateContractTests`) | 14 regression tests |
