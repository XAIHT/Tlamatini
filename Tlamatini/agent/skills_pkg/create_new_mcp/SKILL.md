---
name: create-new-mcp
description: The authoritative reference for adding a NEW tool, MCP context provider, or BOTH to Tlamatini. READ THIS BEFORE registering a `@tool` in `tools.py`, before creating an `mcp_*_server.py` + `chain_*_lcel.py` pair, before seeding a `Tool` or `Mcp` row in a migration, before extending `factory.py`, or before touching the MCP/Tool checkboxes. Covers the three classes (tool-only / MCP-backed context provider / both), the tool-vs-MCP terminology distinction (`get_mcp_tools()` returns LangChain tools, NOT MCP services), and the known hardcoded assumptions in `factory.py` and the frontend.
metadata:
  openclaw:
    emoji: "🧩"
  tlamatini:
    runtime: in-process
    requires_tools: []
    requires_mcps: []
    budget:
      max_iterations: 2
      max_seconds: 30
      max_tokens: 60000
    permissions:
      filesystem:
        read:
          - "Tlamatini/.mcps/create_new_mcp.md"
        write: []
      shell:   []
      network: deny
      db:      deny
    inputs: []
    outputs:
      - { name: guide_path, type: string, required: true,
          description: "Absolute path of the canonical guide that was consulted." }
    triggers:
      keywords:
        - "new tool"
        - "add tool"
        - "new mcp"
        - "add mcp"
        - "create new mcp"
        - "create mcp"
        - "register tool"
        - "context provider"
        - "system metrics tool"
        - "file search tool"
        - "tools.py"
        - "factory.py"
        - "mcp checkbox"
      file_globs:
        - "Tlamatini/agent/tools.py"
        - "Tlamatini/agent/mcp_*_server.py"
        - "Tlamatini/agent/mcp_*_client.py"
        - "Tlamatini/agent/rag/chains/*.py"
        - "Tlamatini/agent/rag/chain_*_lcel.py"
        - "Tlamatini/agent/rag/factory.py"
        - "Tlamatini/agent/migrations/00*_*tool*.py"
        - "Tlamatini/agent/migrations/00*_*mcp*.py"
---

# Create New MCP / Tool — canonical reference

The full, ground-truth procedure for adding a tool, an MCP context provider, or both lives at:

```
Tlamatini/.mcps/create_new_mcp.md
```

## First decision — classify the request before writing anything

| Type | The request looks like... | Path to follow |
|---|---|---|
| **Tool only** | "let the LLM do X on demand" — run a command, start an agent, unzip, decompile, summarize. | Tool-only workflow (below). |
| **MCP-backed context provider only** | "every chat turn, prefetch X and inject it as context" — system metrics, files search, repo inventory. | MCP context-provider workflow (below). |
| **Both** | Pre-fetched context **and** a separate action tool. Rare; most are one or the other. | Do both halves. |

## Tool-only workflow (most common)

1. Implement an `@tool` function in `agent/tools.py` (sync, returns strings).
2. Resolve any bundled paths for **both** source and frozen modes (`os.path.dirname(sys.executable)` vs `os.path.dirname(os.path.abspath(__file__))`).
3. Register the tool in `get_mcp_tools()` under a `global_state` gate.
4. Seed a `Tool` row via a new migration so the UI toggle row exists.
5. Frontend usually needs **NO** changes — the tool checkbox UI is dynamic.
6. The tool is only usable when the unified-agent / Multi-Turn chain is selected.

## MCP context-provider workflow

1. Create `mcp_<name>_server.py` + `mcp_<name>_client.py`.
2. Create a sidecar chain `chain_<name>_lcel.py`.
3. Wire startup in `apps.py` + `management/commands/startserver.py`.
4. Extend `rag/factory.py`: import the chain, add the sync wrapper, map the status key, patch `invoke()` to inject the new payload field.
5. Choose a payload field and update **all** main chains (basic / history-aware / unified).
6. Seed an `Mcp` row **and** update the frontend MCP checkboxes (they are hardcoded, NOT dynamic — unlike Tool checkboxes).
7. Verify persistence and reconnect behavior end-to-end.

## Key warnings (from the gotchas log — re-read the full guide for the rest)

- `factory.py` recognizes ONLY `System-Metrics` and `Files-Search` by `Mcp.description`. Adding an `Mcp` row without extending `factory.py` **does nothing**.
- The MCP UI is hardcoded for two checkboxes; tool UI is dynamic. Don't expect symmetry.
- `get_mcp_tools()` returns **LangChain tools, NOT MCP services** — the name is historical.
- Tool status keys in `factory.py` are handwritten and can drift from seeded `Tool` descriptions — watch for typos.
- `mcpContent` is stored as **string**, not boolean.
- Files-Search main path uses `FileSearchRAGChain`; `mcp_files_search_client_uri` from config is unused by the main chain.

## The other "MCP" — what is NOT this skill

"MCP" inside the `Mcp` DB model checkboxes (System-Metrics / Files-Search) is unrelated to the **external MCP servers** that some pool agents drive (STM32er → STM32 Template Project MCP; Kalier → MCP-Kali-Server; Unrealer → Unreal MCP plugin). Those agents bundle a **self-contained inline MCP / JSON-RPC client** inside `agents/<name>/<name>.py` (stdlib-only, no `mcp` dep in the pool) so they work identically in source and frozen builds — they do NOT go through `factory.py` or the `Mcp` toggle rows. If the user wants you to add a new EXTERNAL MCP bridge of that kind, read the `create-new-agent` skill and base the implementation on the STM32er or Kalier pattern instead.

## Output

Return:

```json
{
  "guide_path": "Tlamatini/.mcps/create_new_mcp.md"
}
```

(That is the absolute pointer the caller should `Read` next.)
