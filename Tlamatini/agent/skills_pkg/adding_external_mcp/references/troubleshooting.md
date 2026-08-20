# Troubleshooting and Diagnostics

## Diagnostic Tools

### external_mcp_doctor
Run a static triage BEFORE activating a server:
```
external_mcp_doctor(server_key="my-server")
```
Checks:
- Transport type detection
- Command availability on PATH
- Placeholder secret identification
- Runtime prerequisites (npx/uvx/node)
- Reports blockers and recommended next steps

### external_mcp_status
Check the current state of all active servers:
```
external_mcp_status()
```
Returns per-server: status (ready/connecting/error/cooldown), tool_count, pid

### external_mcp_list_tools
Enumerate tools exposed by a connected server:
```
external_mcp_list_tools(server_key="my-server")
```

### chat_agent_mcp_doctor
The canvas-agent version of the doctor, for workflow flows:
```
chat_agent_mcp_doctor(server_key="my-server", source_url="...")
```

## Common Issues and Solutions

### 1. Server fails to connect

**Symptoms**: `status: error` in external_mcp_status

**Diagnosis**:
- Run `external_mcp_doctor(server_key="my-server")`
- Check if command exists: `external_mcp_runtime_status()`
- Check if URL is reachable (for network transports)

**Solutions**:
- **Missing npx**: `external_mcp_runtime_install(tools=["npx"])`
- **Missing uvx**: `external_mcp_runtime_install(tools=["uvx"])`
- **Docker not running**: start Docker Desktop
- **Wrong URL**: verify the URL in external_mcps.json
- **Auth failure**: check headers/env for valid tokens
- **Cooldown active**: wait 60s or call `external_mcp_reconnect(server_key="my-server")`

### 2. Zero tools after successful connection

**Symptoms**: `status: ready` but `tool_count: 0`

**Cause**: The server connected but exposed no tools in tools/list.

**Solutions**:
- The system auto-relists every turn — wait for the next chat build
- Force immediate retry: `external_mcp_reconnect(server_key="my-server")`
- Check server logs for errors during tool registration
- Some servers need environment variables to enable tools

### 3. MAX_ACTIVE cap reached

**Symptoms**: 6th server returns `capped: true`

**Solution**:
- Deactivate an existing server first
- Call `external_mcp_set_active(server_keys=["server1","server2"])` with a
  list of 5 or fewer keys
- The system silently drops servers beyond the 5th

### 4. Transport mismatch

**Symptoms**: Connection fails immediately

**Cause**: A stdio server config has `url` instead of `command`, or vice versa.

**Solution**:
- stdio servers need: `command` + `args` (no `url`)
- Network servers need: `url` (no `command`/`args`)
- Check the transport field matches the config shape

### 5. Secrets exposed in catalog

**Symptoms**: Real API keys visible in external_mcps.json

**Solution**:
- NEVER commit external_mcps.json with real secrets
- Run `regen_secrets.py --mode push-able` before pushing
- Public builds regenerate the catalog with placeholder secrets
- Use environment variables instead of hardcoded values when possible

### 6. npx fails on Windows

**Symptoms**: `npx.cmd` spawning errors

**Solution**:
- Tlamatini automatically rewrites npx.cmd to `node.exe <npx-cli.js>`
- If this fails, check that node.exe is in the private runtime
- Run `external_mcp_runtime_status()` to verify node/npx availability
- Install if needed: `external_mcp_runtime_install(tools=["npx"])`

### 7. Server enters cooldown

**Symptoms**: Server shows `status: cooldown` for 60 seconds

**Cause**: The server failed to connect and entered the negative cache.

**Solutions**:
- Wait 60 seconds for the cooldown to expire
- Force immediate retry: `external_mcp_reconnect(server_key="my-server")`
- Fix the underlying issue first (missing runtime, wrong URL, etc.)

### 8. Shipped default reappears after deletion

**Symptoms**: A deleted `memory` or `sequential-thinking` server reappears

**Cause**: The tombstone in `_removed_defaults` was cleared.

**Solution**:
- This should not happen unless the tombstone was explicitly cleared
- Re-importing a server explicitly clears its tombstone
- To re-delete: remove from catalog and ensure it is in `_removed_defaults`

### 9. Docker MCP server fails

**Symptoms**: `docker run -i --rm mcp/redis` fails

**Solutions**:
- Ensure Docker Desktop is running
- Check Docker has enough resources (memory, CPU)
- Verify the image exists: `docker pull mcp/redis`
- Some Docker MCP servers need volume mounts

### 10. Server connects but tools do not appear in Multi-Turn

**Symptoms**: Server is `ready` with tools, but `ext__<server>__<tool>` not available

**Solutions**:
- The tools are bound on the NEXT chat build, not the current one
- Start a new message — the tools will be available
- Check `external_mcp_status()` to confirm `tool_count > 0`
- Verify the server is in the `_active` list

## Debug Checklist

1. [ ] Run `external_mcp_doctor(server_key="...")` — any blockers?
2. [ ] Run `external_mcp_runtime_status()` — are npx/uvx/node available?
3. [ ] Run `external_mcp_status()` — what is the server state?
4. [ ] Check `external_mcps.json` — is the config correct?
5. [ ] Check transport matches config shape (stdio=command, network=url)
6. [ ] Check for placeholder secrets (`<KEY goes here>`)
7. [ ] Is the server in the `_active` list? (max 5)
8. [ ] Is the server in cooldown? (wait 60s or reconnect)
9. [ ] Check `tlamatini.log` for `[EXTERNAL-MCP]` entries
10. [ ] Try `external_mcp_reconnect(server_key="...")` as last resort
