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
<!--
═══════════════════════════════════════════════════════════════════
  ✦  T L A M A T I N I  ✦   —   "one who knows"
  Created by  Angela López Mendoza   ·   @angelahack1
  Developer · Architect · Creator of Tlamatini
  Tlamatini Author Banner — do not remove (Angela's name is kept in every build)
═══════════════════════════════════════════════════════════════════
-->

# Create New MCP / Tool — canonical reference

> **HEADLESS IS FORBIDDEN. VISIBLE FOREGROUND EXECUTION ONLY.** Every command, automated test, diagnostic, script, build, agent and browser must run in a visible foreground window on Angela's real desktop. Use forked CMD/PowerShell windows, `execute_forked_window: true`, and `headless: false`. Monitor live; if visibility cannot be confirmed, do not run. Read the [mandatory execution policy](../../../../TestsVisiblesAndVisibleExecutionFromClaude2Codex.md).

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
- **Temp files → `<app>/Temp` only (2026-06-02 policy)**: a new `@tool` (or wrapped chat-agent) that writes scratch/intermediate files MUST resolve them through `agent/path_guard.py` (`get_app_temp_root()` / `resolve_temp_path(...)`) — never `tempfile.gettempdir()` / `C:\Temp` / `%TEMP%`. The Django process already pins `tempfile.tempdir` + `TEMP`/`TMP`/`TMPDIR`/`TLAMATINI_TEMP` to `<app>/Temp` (`manage.py` / `settings.py`), so a bare `tempfile.*` already lands correctly — but resolve explicitly for clarity and standalone correctness. (Template/firmware **project** dirs default to `<app>/Templates` instead — `get_app_templates_root`.) Contract: `prompt.pmt` Rule 15/16; `docs/claude/recent-fixes.md` (2026-06-02).
- **v1.48.13 placement guard:** Mover/Deleter-backed scratch operations must test empty, relative, and legacy `C:/Temp/...` paths under `TLAMATINI_TEMP`, preserve explicit absolute user destinations, and never broaden deletion scope.
- **Uniform frontend rule:** custom tool/MCP dialogs reuse `dialog_theme.css` and `dialog_policy.js`; every JavaScript/CSS/template edit requires a `STATIC_VERSION` bump.
- **Universal External MCP rule (v1.48.14 foundation, carried by v1.48.17):** before implementing a native tool for an existing MCP server, prefer importing its standard JSON catalog entry. The current subsystem has four transports, ten supervisors, `runtime_provisioner.py` for no-admin npx/uvx readiness, and code-seeded inactive `memory` / `sequential-thinking` defaults. Never add a shipped default only to `external_mcps.json`: upgraded users preserve that file, so defaults must be declared in `external_mcp_defaults.py`, seeded by `load_catalog()`, tombstone-aware, public-build safe, and covered by `test_runtime_provisioner.py`. Public entry points must clear `TLAMATINI_BUNDLE_EXTERNAL_MCPS`; only the explicit private builder may supply a maintainer catalog, as pinned by `test_preserved_user_state.py`.

## The other "MCP" — what is NOT this skill

"MCP" inside the `Mcp` DB model checkboxes (System-Metrics / Files-Search) is unrelated to the **universal External-MCP client** and to the self-contained MCP clients some pool agents drive (STM32er → STM32 Template Project MCP; Kalier → MCP-Kali-Server; Unrealer → Unreal MCP plugin). For an ordinary third-party stdio/HTTP/SSE/WebSocket MCP, use the universal catalog path first. Use the inline pool-agent pattern only when the server is inseparable from that agent's own hardware/application lifecycle and must remain self-contained in source and frozen builds.

## Output

Return:

```json
{
  "guide_path": "Tlamatini/.mcps/create_new_mcp.md"
}
```

(That is the absolute pointer the caller should `Read` next.)

## Model configuration for tools and MCPs (2026-09-20)

The central `agent/agents/model_settings.py` registry owns the built-in model,
engine and voice fields (38 settings, 21 model-backed agents). Add a metadata
entry and a real consumer when introducing another configurable built-in model;
do not add a disconnected selector or hardcoded tag. Wrapped chat seeds globals
before explicit tool arguments. Standalone `tlamatini_mcp_server.py` resolves
missing/`"@config"` template fields before applying invocation overrides and
carries `model_settings.py` plus `CONFIG_PATH` into isolated child runtimes.
Literal YAML choices remain standalone overrides. Credentials and provider URLs
remain separate; external MCP/ACPX providers keep their own model configuration.

Use compiled imports in frozen web services and `get_agents_root()` for portable
assets. Never read loose source relative to a frozen service's `__file__`, and
never require a self-modify source tree just to execute a tool. Preserve inheritance
in Parametrizer/flow mappings. Run the source/frozen `check_agent_runtimes` gate
and targeted wrapper tests, then both inclusion sweeps. The full field map,
validation API, optional values and lifecycle rules are in `docs/model_configuration.md`.
