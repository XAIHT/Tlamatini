---
name: adding-external-mcp
description: >
  The authoritative reference for adding a NEW external MCP server to Tlamatini
  universal MCP client layer. Covers the full lifecycle: catalog import, transport
  selection, activation, runtime provisioning, diagnosis, verification, and
  troubleshooting. READ THIS BEFORE calling external_mcp_import, before editing
  external_mcps.json, or before activating a new server.
metadata:
  openclaw:
    emoji: "🔌"
  tlamatini:
    runtime: in-process
    requires_tools:
      - "external_mcp_import"
      - "external_mcp_set_active"
      - "external_mcp_status"
      - "external_mcp_doctor"
      - "external_mcp_wait"
      - "external_mcp_list_tools"
      - "external_mcp_call"
      - "external_mcp_reconnect"
      - "external_mcp_runtime_status"
      - "external_mcp_runtime_install"
      - "chat_agent_mcp_doctor"
    requires_mcps: []
    budget:
      max_iterations: 15
      max_seconds: 300
      max_tokens: 32000
    permissions:
      filesystem:
        read:
          - "Tlamatini/agent/external_mcps.json"
          - "Tlamatini/agent/external_mcp_manager.py"
          - "Tlamatini/agent/external_mcp_defaults.py"
          - "Tlamatini/agent/runtime_provisioner.py"
        write:
          - "Tlamatini/agent/external_mcps.json"
      shell: []
      network: allow
      db: deny
    inputs:
      - { name: server_key, type: string, required: true,
          description: "Unique catalog key for the server (kebab-case or snake_case)." }
      - { name: server_config, type: object, required: true,
          description: "The mcpServers JSON spec for the server (command/args/env/transport/url/headers)." }
      - { name: activate, type: boolean, required: false,
          description: "Whether to activate the server immediately after import (default: false)." }
      - { name: verify, type: boolean, required: false,
          description: "Whether to run external_mcp_doctor + external_mcp_wait + external_mcp_list_tools after activation (default: true)." }
    outputs:
      - { name: import_status, type: string, required: true,
          description: "Result of the import operation (imported/updated/already_exists/error)." }
      - { name: activation_status, type: string, required: true,
          description: "Result of the activation operation (activated/capped/failed/skipped)." }
      - { name: doctor_report, type: object, required: false,
          description: "The external_mcp_doctor diagnostic report if verify=true." }
      - { name: tools_discovered, type: array, required: false,
          description: "List of tool names exposed by the server if verify=true." }
    triggers:
      keywords:
        - "add external mcp"
        - "new external mcp"
        - "import mcp"
        - "add mcp server"
        - "external mcp"
        - "mcp catalog"
        - "activate mcp"
        - "mcp server"
        - "external_mcps.json"
        - "mcp transport"
        - "stdio mcp"
        - "http mcp"
        - "sse mcp"
        - "websocket mcp"
        - "npx mcp"
        - "uvx mcp"
        - "docker mcp"
      file_globs:
        - "Tlamatini/agent/external_mcps.json"
        - "Tlamatini/agent/external_mcp_manager.py"
        - "Tlamatini/agent/external_mcp_defaults.py"
        - "Tlamatini/agent/runtime_provisioner.py"
        - "**/.mcp.json"
        - "**/mcp*.json"
---

# Adding External MCP — canonical reference

The full, ground-truth procedure for adding a NEW external MCP server to
Tlamatini universal MCP client layer. This skill makes Tlamatini
autonomously capable of adding, configuring, activating, and verifying any
external MCP server — robustly and bullet-proof.

## What this skill does

Enables Tlamatini to add ANY external MCP server to her universal MCP client
layer — the system that lets her use tools from arbitrary MCP servers
declared in a JSON catalog (external_mcps.json), with no code per server.

## Architecture overview

```
external_mcps.json (catalog) --> external_mcp_manager.py --> ext__<server>__<tool>
      |
      |-- _StdioMcpClient (local child)
      |-- _StreamableHttpMcpClient (HTTP)
      |-- _SseMcpClient (legacy SSE)
      |-- _WebSocketMcpClient (WS)
      |
      |-- external_mcp_defaults.py (code-owned defaults: memory, sequential-thinking)
      |-- runtime_provisioner.py (private npx/uvx/node provisioning)
```

**Key constants:** MAX_ACTIVE = 5 | _SUPPORTED_TRANSPORTS = {stdio, streamable-http, sse, websocket}

## Procedure — adding a new external MCP server

### Step 1 — Classify the server transport

Determine which transport the MCP server uses:

| Transport | When to use | Config key |
|---|---|---|
| stdio | Local child process (npx, uvx, docker, python) | command + args |
| streamable-http | HTTP endpoint (modern MCP servers) | url |
| sse | Legacy Server-Sent Events endpoint | url |
| websocket | WebSocket endpoint | url |

If the server provides a .mcp.json or equivalent config, copy it directly —
the catalog uses the same mcpServers shape as Claude Code.

### Step 2 — Build the server config

The server config is a JSON object with these fields:

```json
{
  "command": "npx",
  "args": ["-y", "@some/mcp-server"],
  "env": { "API_KEY": "your-key-here" },
  "transport": "stdio",
  "description": "Optional human-readable description"
}
```

For network transports:

```json
{
  "url": "https://mcp-server.example.com/mcp",
  "transport": "streamable-http",
  "headers": { "Authorization": "Bearer your-token" },
  "description": "Remote MCP server"
}
```

### Step 3 — Import the server into the catalog

Call external_mcp_import with the server config:

```
external_mcp_import(servers_json={"mcpServers": {"my-server": <config>}})
```

Or pass a JSON string. The server is ADDED to the catalog but NOT activated.
If the key already exists, it is UPDATED (not duplicated).

### Step 4 — (Optional) Diagnose before activating

Call external_mcp_doctor(server_key="my-server") to run a static triage:
- Detects transport type
- Checks if command is on PATH
- Identifies placeholder secrets
- Reports blockers and next steps

Alternatively, use chat_agent_mcp_doctor for the canvas-agent version.

### Step 5 — Activate the server

Call external_mcp_set_active(server_keys=["my-server"]) or pass a
comma-separated string. This:
- Caps at MAX_ACTIVE=5 (silently drops excess, reports capped: true)
- Spawns the child process (stdio) or opens the network connection
- Performs the MCP initialize handshake -> tools/list
- Wraps each remote tool as ext__<server>__<tool>

### Step 6 — Wait for the server to be ready

Call external_mcp_wait(server_key="my-server", timeout_seconds=120) to
BLOCK until the server is connected and exposing tools. This is essential
for:
- First-run Docker image pulls (can take minutes)
- Cold npx/uvx downloads
- Slow network servers

### Step 7 — Verify the server

Call external_mcp_status() to confirm the server shows status: ready and
tool_count > 0. Then call external_mcp_list_tools(server_key="my-server")
to enumerate the exposed tools.

### Step 8 — Test a tool call

Call external_mcp_call(server_key="my-server", tool_name="<tool>",
arguments={...}) to test one tool directly. Or, in a Multi-Turn run, call
the bound ext__my-server__<tool> tool directly.

## Runtime provisioning (zero-config)

Tlamatini automatically provisions the package managers an MCP server needs:
- npx/npm/node — downloaded into Tlamatini private per-user runtime
- uv/uvx — same private provisioning
- pnpm — same

No administrator rights, no system PATH change. Check with
external_mcp_runtime_status(). Install manually with
external_mcp_runtime_install(tools=["npx"]).

## Shipped defaults (do NOT re-add)

Two servers ship with every installation, INACTIVE by design:
- memory — persistent knowledge graph (9 tools)
- sequential-thinking — structured reasoning (1 tool)

If a user deleted one, it stays deleted (tombstone). Re-importing explicitly
clears the tombstone.

## Common pitfalls

- **MAX_ACTIVE=5**: the 6th server is silently dropped. Deactivate one first.
- **Secrets in env**: external_mcps.json holds real secrets. Never commit
  it. Run regen_secrets.py --mode push-able before pushing.
- **Transport mismatch**: a stdio server needs command+args; a network
  server needs url. Mixing them fails at connect time.
- **npx on Windows**: Tlamatini rewrites npx.cmd to node.exe <npx-cli.js>
  automatically — no shell needed.
- **Docker MCP**: docker run -i --rm mcp/redis works but requires Docker
  Desktop running.
- **Zero tools after connect**: the server connected but exposed 0 tools.
  The system auto-relists it. Call external_mcp_reconnect to force a retry.
- **Cooldown**: a failed server enters a 60s negative cache. Wait or call
  external_mcp_reconnect to force-retry immediately.

## LLM Reflection connection

This skill was created as part of a research task on **LLM Reflection** — the
technique where language models evaluate and improve their own outputs through
iterative self-correction. Tlamatini self-healing layer (agent/self_healing.py)
is itself an implementation of LLM Reflection: it retries failed model calls
with different tactics, narrates recovery live, and never hangs or discards
work. See references/llm_reflection_research.md for the full research findings.

## References

- references/llm_reflection_research.md — LLM Reflection research findings
- references/external_mcp_catalog_format.md — detailed catalog format guide
- references/transport_guide.md — transport configuration reference
- references/troubleshooting.md — troubleshooting and diagnostics

## Output

```json
{
  "import_status": "imported|updated|already_exists|error",
  "activation_status": "activated|capped|failed|skipped",
  "doctor_report": {},
  "tools_discovered": []
}
```
