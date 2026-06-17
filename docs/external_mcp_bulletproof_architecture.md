# Tlamatini External MCP Bulletproof Architecture

This document is the design contract for making External MCP support durable
across marketplace servers, source builds, frozen installs, and Step-by-Step
human setup workflows.

## Why External MCPs Failed

The Roblox and Redis debugging exposed several independent failure classes:

1. Studio/host-side enablement was incomplete. Roblox Studio had the Assistant
   panel open, but Studio still needed its own MCP server toggle enabled.
2. Docker MCP examples can be entrypoint-sensitive. `docker run mcp/redis
   redis://host.docker.internal:6379` tried to execute the Redis URL as a
   binary; the correct form needed the redis MCP server entrypoint plus `--url`.
3. Tlamatini's global planner capped External MCP tools too aggressively. Redis
   had useful tools beyond the first visible slice, so `set`/`get` style tools
   could disappear even while the server was connected.
4. JSON Schema unions were flattened too hard. MCP tool schemas using `anyOf`,
   `oneOf`, enum, const, or type arrays could be wrapped incorrectly.
5. BOM-bearing JSON could break installed catalogs. Marketplace/client JSON is
   often copied from Windows tools and must be read with `utf-8-sig`.
6. Single-server JSON was treated like an `mcpServers` map. A block containing
   `command`/`args` could be split into fake servers named `command` and `args`.
7. The model had no stable diagnostic tool. It could see active status and call
   tools, but it lacked a first-class way to investigate a new MCP before
   telling the user what to do.

## Implemented Control Plane

External MCPs now have eight supervisor tools:

- `external_mcp_status`: health, active state, tool count, stderr tail.
- `external_mcp_reconnect`: force reconnect one active server.
- `external_mcp_doctor`: diagnose catalog entries before/after activation.
- `external_mcp_list_tools`: inspect exact raw MCP tool names and schemas.
- `external_mcp_call`: call any raw MCP tool through the generic dispatcher.
- `external_mcp_import`: add one or more servers to the catalog from JSON.
- `external_mcp_set_active`: choose the active set, capped at five servers.
- `external_mcp_wait`: block until an active server becomes ready or times out.

The doctor does not replace normal MCP calls. It is the preflight brain:

1. Normalize imported config.
2. Infer transport.
3. Infer runtime.
4. Check command/PATH.
5. Detect placeholder secrets.
6. Preserve source/docs URLs.
7. Report blockers and the next user-facing step.

## MCP Doctor Agent

`MCP Doctor` is also a real Tlamatini agent:

- Template: `agent/agents/mcp_doctor/`
- Wrapped tool: `chat_agent_mcp_doctor`
- Canvas label: `MCP Doctor`
- Tool row: `Chat-Agent-MCP-Doctor`
- Prompt catalog demo: prompt 81
- Structured output: `INI_SECTION_MCP_DOCTOR`

This lets Tlamatini use the same capability in two ways:

- Multi-Turn chat can call the supervisor tool for live catalog/process state.
- Canvas/Multi-Turn workflows can launch `chat_agent_mcp_doctor` as a visible,
  reusable agent node.

The agent is self-contained and does not import `agent.*`, so copied pool
runtime folders and frozen installs do not need Django import paths.

## Step-by-Step Mode

The new `Step-by-Step` checkbox is a chat runtime modifier. When enabled:

1. The browser sends `step_by_step_enabled` with the chat payload.
2. `consumers.py` forwards the flag to RAG.
3. `rag/interface.py` allows the mode to select the unified agent path.
4. `rag/chains/unified.py` preserves the payload key through its whitelist.
5. `mcp_agent.py` injects Step-by-Step system guidance.

Behavior contract:

- Give one concrete action at a time.
- Wait for the user's `READY`, screenshot, log, or command output.
- For new MCPs, call `external_mcp_doctor` first.
- For large/hidden MCPs, call `external_mcp_list_tools` before declaring a
  tool unavailable.
- Use `external_mcp_call` when a direct wrapped tool was not selected.

## Drag And Drop Import Contract

Dropped JSON can be:

- Full client config: `{ "mcpServers": { ... } }`
- Alternate wrapper: `{ "servers": { ... } }`
- Single-server block: `{ "command": "...", "args": [...] }`
- URL transport block: `{ "url": "https://..." }`
- Host/port transport block: `{ "host": "...", "port": 1234 }`

All text is BOM-stripped before parse. Backend catalog reads use `utf-8-sig`.

Imported specs normalize:

- `args` to a string list
- `env` to a string map
- `cwd` trimming
- URL aliases: `endpoint`, `sseUrl`, `streamableHttpUrl`, `wsUrl`,
  `websocketUrl`
- transport aliases: `http` and `streamable_http` to `streamable-http`, `ws` to
  `websocket`, `socket`/`raw` to `tcp`, `pipe` to `named-pipe`
- command-based servers to explicit `stdio`

## Transport Strategy

MCP is JSON-RPC. The transport is the carrier. Tlamatini now recognizes these
families:

- `stdio`: implemented live connector.
- `streamable-http`: implemented live connector for already-running HTTP MCP endpoints.
- `sse`: implemented live connector for legacy HTTP+SSE MCP endpoints.
- `websocket`: implemented live connector for WebSocket JSON-RPC MCP endpoints.
- `tcp` / raw socket: detected and diagnosed; adapter still future.
- `named-pipe`: detected and diagnosed; adapter still future.

Unsupported transports must never look like random failure. They are surfaced as
explicit blockers explaining which carrier needs a stdio bridge or future adapter.

## Universal Onboarding Pipeline

For every new MCP:

1. Import JSON.
2. Normalize config.
3. Run MCP Doctor.
4. If docs/source URLs exist, use them to clarify runtime-specific setup.
5. Verify runtime prerequisite: Docker, Node/NPX, UV/UVX, Python, Java, .NET,
   etc.
6. Ask for missing secrets without printing stored secrets.
7. Activate only after the preflight is understandable.
8. Warm-connect.
9. Inspect initialize/tools/list.
10. List raw tools and schemas.
11. Run one safe smoke test.
12. Explain the next user action one READY-gated step at a time.

## Error Forest

Tlamatini must diagnose these layers separately:

- File layer: missing catalog, BOM JSON, invalid JSON, wrong shape.
- Import layer: no command/url, single-server block, URL alias drift.
- Runtime layer: command missing, Docker daemon down, package pull, bad cwd.
- Transport layer: stdio vs HTTP/SSE/WebSocket/TCP/named-pipe.
- MCP handshake layer: initialize timeout, server exits, stderr-only failure.
- Tool layer: zero tools, tool list changed notification, hidden direct wrapper.
- Schema layer: required fields, unions, enum/const, optional fields.
- Planner layer: global cap hiding useful tools.
- User workflow layer: setup needs one explicit step, not a giant vague plan.

## Frozen And Source Compatibility

New code must work in both modes:

- Catalog path checks `CONFIG_PATH` first.
- Source mode resolves next to `agent/` or app parents.
- Frozen mode resolves beside `sys.executable`.
- MCP Doctor also checks the installed `C:\Tlamatini\external_mcps.json`
  fallback on Windows.
- Pool agents are self-contained and do not import `agent.*`.
- File reads use UTF-8 with BOM tolerance where catalog JSON is involved.

## Automated Verification

The External MCP verification suite contains loopback and full-pipeline tests:

- transport detection
- real stdio, Streamable HTTP, legacy SSE, and WebSocket round trips
- drag/drop import, activate, bind, call, diagnose, reconnect, and watchdog PID protection
- hosted/auth-header success and failure paths
- runtime inference
- import normalization
- secret placeholder detection
- schema union/enum/const handling
- BOM catalog reads
- supervisor tool exposure, including import/set-active/wait
- Step-by-Step prompt plumbing
- MCP Doctor registry/contract/prompt/canvas files
- frozen/source path literals and self-contained agent import boundaries

Run:

```powershell
python Tlamatini\manage.py test agent.test_external_mcp_universal agent.test_external_mcp_transports agent.test_external_mcp_e2e agent.test_external_mcp_add_flow agent.test_step_by_step_mode agent.test_parametrizer_mcp_doctor --verbosity 1
```
