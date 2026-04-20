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
