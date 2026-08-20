# Transport Configuration Reference

## Supported Transports

Tlamatini supports four MCP transport types via `_SUPPORTED_TRANSPORTS`:

| Transport | Constant | Use Case |
|---|---|---|
| stdio | `_StdioMcpClient` | Local child process (npx, uvx, docker, python) |
| streamable-http | `_StreamableHttpMcpClient` | Modern HTTP MCP servers |
| sse | `_SseMcpClient` | Legacy Server-Sent Events |
| websocket | `_WebSocketMcpClient` | WebSocket-based MCP servers |

## stdio Transport

### How it works
Spawns a local child process, communicates via stdin/stdout JSON-RPC.

### Configuration
```json
{
  "command": "npx",
  "args": ["-y", "@modelcontextprotocol/server-memory"],
  "env": { "API_KEY": "your-key" },
  "transport": "stdio"
}
```

### Common commands
| Command | Example args | Notes |
|---|---|---|
| npx | ["-y", "@some/mcp-server"] | Auto-installs package |
| uvx | ["mcp-server-name"] | Python UV package runner |
| docker | ["run", "-i", "--rm", "mcp/redis"] | Requires Docker Desktop |
| python | ["-m", "mcp_server"] | Direct Python module |

### Windows npx handling
Tlamatini rewrites `npx.cmd` to `node.exe <npx-cli.js>` automatically,
avoiding shell spawning issues on Windows. No manual intervention needed.

### Runtime provisioning
If npx/npm/node or uv/uvx are not installed, Tlamatini downloads them into
her private per-user runtime directory. No admin rights, no PATH change.

## streamable-http Transport

### How it works
Opens an HTTP connection to the MCP server, sends JSON-RPC over HTTP POST.

### Configuration
```json
{
  "url": "https://mcp-server.example.com/mcp",
  "transport": "streamable-http",
  "headers": {
    "Authorization": "Bearer your-token"
  }
}
```

### When to use
- Modern MCP servers exposed over HTTP
- Cloud-hosted MCP services
- Servers behind a reverse proxy

## sse Transport (Legacy)

### How it works
Uses Server-Sent Events for server-to-client communication, HTTP POST for
client-to-server.

### Configuration
```json
{
  "url": "https://mcp-server.example.com/sse",
  "transport": "sse",
  "headers": {
    "Authorization": "Bearer your-token"
  }
}
```

### When to use
- Legacy MCP servers that only support SSE
- Servers that have not yet migrated to streamable-http

## websocket Transport

### How it works
Opens a WebSocket connection for bidirectional JSON-RPC communication.

### Configuration
```json
{
  "url": "wss://mcp-server.example.com/ws",
  "transport": "websocket",
  "headers": {
    "Authorization": "Bearer your-token"
  }
}
```

### When to use
- MCP servers that use WebSocket for real-time communication
- Servers that need persistent bidirectional connections

## Transport Auto-Detection

If `transport` is omitted from the config:
1. `command` field present -> **stdio**
2. `url` starts with `ws://` or `wss://` -> **websocket**
3. `url` starts with `http://` or `https://` -> **streamable-http**
4. Fallback: **streamable-http** for URLs, **stdio** for commands

## Adding a New Transport

To add a new transport (e.g. `tcp`, `named-pipe`):

1. Write a client class subclassing `_NetworkMcpClientBase`
2. Implement `_open()`, `_rpc()`, `_notify()`, `close()`
3. Wire it into `_make_client()` in `external_mcp_manager.py`
4. Add the transport name to `_SUPPORTED_TRANSPORTS`
5. Write loopback round-trip tests in `test_external_mcp_transports.py`

## Connection Lifecycle

1. **Activate** (`external_mcp_set_active`) -> marks server as active
2. **Connect** (on next chat build) -> spawns process / opens connection
3. **Initialize** -> MCP `initialize` handshake
4. **List tools** -> `tools/list` -> wrap each as `ext__<server>__<tool>`
5. **Ready** -> tools available in Multi-Turn tool surface
6. **Cooldown** (on failure) -> 60s negative cache, auto-retry after
7. **Disconnect** (on deactivate) -> kill process / close connection

## Timeout Handling

- Connection timeout: built into each transport client
- First-run Docker pulls: can take minutes (use `external_mcp_wait` with 120s+)
- Cold npx/uvx downloads: can take 30-60s
- Failed connection: 60s cooldown (negative cache) before auto-retry
