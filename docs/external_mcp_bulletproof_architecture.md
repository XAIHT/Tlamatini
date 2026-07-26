<!--
═══════════════════════════════════════════════════════════════════
  ✦  T L A M A T I N I  ✦   —   "one who knows"
  Created by  Angela López Mendoza   ·   @angelahack1
  Developer · Architect · Creator of Tlamatini
  Tlamatini Author Banner — do not remove (Angela's name is kept in every build)
═══════════════════════════════════════════════════════════════════
-->
# External MCPs — the bulletproof architecture

The design contract for Tlamatini's **universal MCP _client_**: the layer that lets her
use the tools of **any** external MCP server declared in a JSON catalog, with **no code
per server**.

Engine: `agent/external_mcp_manager.py` · Catalog: `agent/external_mcps.json` ·
UI: **External ▸ MCPs** navbar dialog (`static/agent/js/external_mcps_dialog.js`).

> **This is NOT one of the other three "MCP" things.** It is not the two `Mcp`-model
> context providers (System-Metrics / Files-Search, wired through `rag/factory.py`), it is
> not **ACPX** (which spawns external coding-agent CLIs), and it is not the per-agent
> inline MCP clients some pool agents bundle (STM32er → STM32 Template Project MCP,
> Kalier → MCP-Kali-Server). See `docs/claude/mcp-tools.md` for the four-way contrast.

---

## 1. The catalog is USER STATE

`agent/external_mcps.json` holds the standard `mcpServers` shape — byte-identical to a
Claude Code / Claude Desktop `.mcp.json` — plus an `active` list. A server config copied
from another tool drops straight in.

- Resolved **next to `config.json`** with the same precedence (`CONFIG_PATH` env > the
  frozen install root > source `agent/`), so it is user state that **survives a
  self-update** exactly like `config.json` and the DB.
- Read with **`utf-8-sig`** — a BOM (what Notepad writes) must never break the catalog.
- **`MAX_ACTIVE = 5`.** The catalog may hold hundreds of servers; at most five are
  connected at a time, so the LLM's bound tool surface stays small and affordable.
  `set_active` silently caps and reports `capped: true` rather than failing.

## 2. Transports

`_SUPPORTED_TRANSPORTS = {stdio, streamable-http, sse, websocket}`. All four network
clients share one `_NetworkMcpClientBase` (a single MCP handshake) and duck-type the
`_StdioMcpClient`, so every supervisor tool treats all transports uniformly.

| Transport | Status | Backing |
|---|---|---|
| `stdio` | implemented live connector | a local child process (Docker `mcp/*` image, `npx`, `uvx`, `python`, …) |
| `streamable-http`: implemented live connector | — | `httpx`, imported lazily |
| `sse` | implemented live connector (legacy servers) | `httpx`, imported lazily |
| `websocket`: implemented live connector | — | `websockets`, imported lazily |
| `tcp` | detected and diagnosed; adapter still future | normalizer recognises the label so the doctor can explain the blocker |
| `named-pipe` | detected and diagnosed; adapter still future | same |

The normalizer also accepts the aliases `http` / `streamable_http` → `streamable-http`,
`ws` → `websocket`, `socket` / `raw` → `tcp`, `pipe` → `named-pipe`, and infers a
transport from `url` / `sseUrl` / `wsUrl` / `websocketUrl` when none is declared.

## 3. The LLM surface — eight supervisor tools

`_SUPERVISOR_TOOL_NAMES` binds **eight supervisor tools**; every one returns a JSON
envelope and never raises:

| Tool | Role |
|---|---|
| `external_mcp_status` | catalog + active set + per-server connection state |
| `external_mcp_reconnect` | force a reconnect of one server, or all |
| `external_mcp_doctor` | per-server triage: transport, runtime, command-on-PATH, placeholder secrets, blockers, next step |
| `external_mcp_list_tools` | enumerate the tools a connected server exposes |
| `external_mcp_call` | call one remote tool directly |
| `external_mcp_import` | add server(s) from a JSON object **or** a JSON string |
| `external_mcp_set_active` | set the active set (list **or** comma-string), capped at ≤5 |
| `external_mcp_wait` | **BLOCK** until a slow server is ready — the answer to a first-run Docker image pull, instead of polling and giving up |

Each active server's remote tools are then bound lazily as **`ext__<server>__<tool>`**
(e.g. `ext__octocode__ghSearchRepos`). The executor refreshes that slice per request via
`mcp_agent._refresh_external_mcp_tool_surface`.

**Gating:** these tools are gated by **Multi-Turn only**. They are NOT in
`agent.acpx.ACPX_TOOL_NAMES`, are NOT stripped by `filter_acpx_tools`, and the ACPX
checkbox has no effect on them.

## 4. The bulletproof rules (do NOT weaken any of these)

1. **Connects run OFF the chat-build path.** Connection happens lazily on a background
   thread, so a slow or hung server can never delay an answer. Timeout 60 s, override with
   `TLAMATINI_EXTERNAL_MCP_CONNECT_TIMEOUT`.
2. **A bad server degrades, never crashes.** Unreachable / unsupported / mis-declared
   servers become a *catalogued-with-reason* entry carrying the doctor's blocker and
   next-step. The chain always answers.
3. **Negative cache + supervisor.** A dead server is not retried every turn (cooldown), and
   a server that connected but reported zero tools is relisted / reconnected.
4. **BOM-tolerant catalog read** (`utf-8-sig`).
5. **Auth** via the spec's `headers` (e.g. `Bearer …`) and `env` injection.
6. **The command watchdog exempts live external-MCP child PIDs** (`external_mcp_root_pids`)
   so its idle-child reaper can never kill a healthy MCP server.
7. **Never in the Exec Report.** The supervisor tools and the `ext__*` wrappers are not
   `chat_agent_*` tools, so they do not hit the wrapped-agent fallback.

## 5. Static, offline triage: the MCP Doctor agent

**MCP Doctor** (canvas agent #78, wrapped as `chat_agent_mcp_doctor`) reads the same
catalog **without connecting** — the on-paper sibling of the live `external_mcp_doctor`
tool. It is stdlib-only (`agent/agents/mcp_doctor/mcp_doctor.py` never imports `agent.*`),
emits `INI_SECTION_MCP_DOCTOR` for Parametrizer, and always triggers `target_agents` so a
Forker can branch on `{supported}` / `{status}`.

Use `chat_agent_mcp_doctor` to triage a catalogued server before wiring it;
use `external_mcp_doctor` once you want a live connect-and-probe.

## 6. Coverage

`agent/test_external_mcp_universal.py` (schema matrix, catalog, transport normalisation and
the static integration expectations that pin this file), plus
`test_external_mcp_transports.py`, `test_external_mcp_add_flow.py`, and
`test_external_mcp_e2e.py`.
