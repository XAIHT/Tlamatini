# Tlamatini — Creating a New MCP or Tool

**Full guide**: `Tlamatini/.mcps/create_new_mcp.md`

## First Decision: Classify the request

| Type | Description | Example |
|------|-------------|---------|
| **Tool only** | Model performs an action on demand during unified-agent execution | run command, start agent, unzip, decompile |
| **MCP-backed context provider only** | System fetches context before the main chain responds | system metrics, file search, inventory |
| **Both** | Needs pre-fetched context AND a separate action tool | Rare - most are one or the other |

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
