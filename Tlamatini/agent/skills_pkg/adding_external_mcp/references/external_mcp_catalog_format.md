# External MCP Catalog Format — Detailed Guide

## Overview

The external MCP catalog lives in `external_mcps.json` next to `config.json`.
It uses the same `mcpServers` shape as Claude Code `.mcp.json` files, making
it trivially portable between systems.

## File Location

- **Frozen/installed**: `<install_root>/external_mcps.json` (next to Tlamatini.exe)
- **Source/dev**: `Tlamatini/agent/external_mcps.json` (next to config.json)
- The file is **preserved user state** — self-update keeps it intact.

## JSON Structure

```json
{
  "mcpServers": {
    "server-key-1": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-memory"],
      "env": {
        "API_KEY": "<KEY goes here>"
      },
      "transport": "stdio",
      "description": "Persistent knowledge graph"
    },
    "server-key-2": {
      "url": "https://mcp.example.com/sse",
      "transport": "sse",
      "headers": {
        "Authorization": "Bearer <TOKEN goes here>"
      },
      "description": "Remote MCP server"
    }
  },
  "_removed_defaults": ["some-deleted-server"],
  "_active": ["server-key-1"]
}
```

## Fields

### Server-level fields

| Field | Required | Type | Description |
|---|---|---|---|
| `command` | stdio only | string | Executable to run (e.g. npx, uvx, docker, python) |
| `args` | stdio only | array | Arguments passed to the command |
| `env` | optional | object | Environment variables for the child process |
| `url` | network only | string | HTTP/HTTPS/WS URL of the MCP server |
| `transport` | optional | string | One of: stdio, streamable-http, sse, websocket (auto-detected if omitted) |
| `headers` | optional | object | HTTP headers for network transports |
| `description` | optional | string | Human-readable description |

### Catalog-level fields

| Field | Type | Description |
|---|---|---|
| `mcpServers` | object | Map of server-key -> server config |
| `_removed_defaults` | array | Tombstones for deleted shipped defaults |
| `_active` | array | Currently activated server keys (max 5) |

## Transport Auto-Detection

If `transport` is omitted, the system auto-detects:
- `command` present -> `stdio`
- `url` starts with `ws://` or `wss://` -> `websocket`
- `url` starts with `http://` or `https://` -> `streamable-http` (or `sse` if flagged)

## Secret Hygiene

- **Never commit** `external_mcps.json` with real secrets
- Run `regen_secrets.py --mode push-able` before any git push
- Public builds regenerate the catalog with only inactive defaults
- Keyed/private builds may include the maintainer catalog
- Secret-shaped values in `env` are scrubbed to `<KEY goes here>` placeholders

## Shipped Defaults

Two servers ship with every installation (both INACTIVE by default):

### memory
```json
{
  "command": "npx",
  "args": ["-y", "@modelcontextprotocol/server-memory"],
  "transport": "stdio"
}
```
- 9 tools: create_entities, create_relations, add_observations, delete_entities,
  delete_observations, delete_relations, read_graph, search_nodes, open_nodes
- Persists to `%LOCALAPPDATA%\Tlamatini\memory\memory.json`

### sequential-thinking
```json
{
  "command": "npx",
  "args": ["-y", "@modelcontextprotocol/server-sequential-thinking"],
  "transport": "stdio"
}
```
- 1 tool: sequentialthinking
- Structured reasoning with step-by-step thought process

## Tombstones

When a user deletes a shipped default, it is added to `_removed_defaults`.
This prevents `load_catalog()` from re-seeding it on next startup.
To restore: call `external_mcp_import` explicitly (clears the tombstone).

## Active Set

- Maximum 5 active servers (`MAX_ACTIVE = 5`)
- The 6th server is silently dropped with a `capped: true` warning
- Active servers are spawned/connected on chat build
- Inactive servers stay catalog-only (no process, no connection)

## Drag-and-Drop Import

Dropping an MCP `.json` file anywhere on the page merges it into the catalog
after a user confirmation dialog. The file carries an executable `command`,
so it is never imported silently.
