# Tlamatini — Architecture & Core Systems

## Configuration

Main config: `Tlamatini/agent/config.json`

Key settings:
- `embeding-model`: Embedding model for RAG. **Default**: `Nomic-Embed-Text:latest` (~600 MB resident VRAM, low-footprint baseline that works on 8 GB consumer GPUs). For higher-detail retrieval on dense technical corpora, users can switch to `qwen3-embedding:8b` from the **Config → Models** menu — **with caution**, since that model needs roughly **10× more VRAM** (~6.24 GB resident on Q4_K_M) and will trip the embedding-memory pre-flight guard on smaller GPUs.
- `chained-model`: Primary chat model
- `unified_agent_model`: Model for multi-turn tool loop
- `ollama_base_url`: Ollama server URL
- `ANTHROPIC_API_KEY`: Claude API key
- `enable_unified_agent`: Enable tool-calling agent
- `unified_agent_max_iterations`: Max tool-call turns (default 100)
- `chat_agent_limit_runs`: Wrapped-run listing limit

Frozen builds resolve config from the install directory next to the executable. Source mode resolves from `Tlamatini/agent/config.json`. `CONFIG_PATH` env var overrides both.

---

## System Prompt & Identity

The chat LLM system prompt lives in `Tlamatini/agent/prompt.pmt`. The LLM is given the identity **"Tlamatini"** (Nahuatl for "one who knows"). When users address "Tlamatini" in their prompts, the LLM understands they are speaking to the system itself. The bot username in chat messages and DB records is `Tlamatini`.

Key rules:

1. Referenced rephrases must be ignored
2. System context (MCP metrics) is real-time
3. Files context (MCP file search) is real-time
4. Code blocks use `BEGIN-CODE<<<FILENAME>>>` / `END-CODE` format (NOT markdown fences)
5. Context usage: if tools are available (Multi-Turn), use them for ANY request
6. Tables must use HTML, not markdown pipe syntax
7. Responses must end with `END-RESPONSE`
8. Tool-usage rule: in Multi-Turn, the LLM is an OPERATOR, not just an advisor
9. Up to 256 multi-turn iterations available
10. Identity rule: the LLM IS Tlamatini — it responds to its name and can describe its own capabilities

---

## The Five Layers of the System

### Layer 1: Persisted Toggles (Database)
- `Mcp` model rows: UI toggles for MCP context providers
- `Tool` model rows: UI toggles for unified-agent tools
- `Agent` model rows: Agent type registry (sidebar list)
- Loaded by `consumers.py`, converted to status flags in `factory.py`

### Layer 2: Runtime MCP Services
- **System-Metrics**: `mcp_system_server.py` (WebSocket JSON)
- **Files-Search**: `mcp_files_search_server.py` (gRPC)
- Started from `apps.py` and `management/commands/startserver.py`

### Layer 3: Context Fetcher Chains (Sidecars)
- `SystemRAGChain` in `chain_system_lcel.py`
- `FileSearchRAGChain` in `chain_files_search_lcel.py`
- These inject `system_context` / `files_context` into the payload

### Layer 4: Main Answer Chains
- `basic.py`: BasicPromptOnlyChain (no docs)
- `history_aware.py`: History-aware RAG with reranking
- `unified.py`: Tool-enabled agent chains (LangGraph)
- `factory.py` monkey-patches `invoke()` to inject context from sidecars

### Layer 5: Unified-Agent Tools
- Defined in `tools.py` as synchronous `@tool` functions
- Returned by `get_mcp_tools()` (misnamed - returns LangChain tools, NOT MCP services)
- Only active when unified-agent chain is selected
- Includes: execute_command, agent_parametrizer, agent_starter, agent_stopper, agent_stat_getter, launch_view_image, unzip_file, decompile_java, googler, + 42 wrapped chat-agent launchers (see `chat_agent_registry.CHAT_AGENT_TOOLS`)
- Googler tool must run Playwright inside a `ThreadPoolExecutor` — `sync_playwright()` is incompatible with Django Channels' running event loop

---

## Application Log (tlamatini.log)

`Tlamatini/manage.py` defines a `_TeeStream` wrapper that replaces `sys.stdout` and `sys.stderr` **before Django initializes**. Every print, every Django logger (they all use `StreamHandler`), and every tool's stdout/stderr lands in both the console and a single file:

- **Source mode**: `Tlamatini/tlamatini.log` (next to `manage.py`)
- **Frozen mode**: next to the executable (e.g. `C:\Program Files\Tlamatini\tlamatini.log`)

Characteristics:

- **Truncate-on-start**: the file is opened with mode `'w'`, so each run begins with a fresh log
- **No rotation / no size cap**: long sessions grow unbounded — copy or rename before restart if you need to preserve the history
- **Not a Django LOGGING handler**: the tee is stream-level, upstream of Django's logging config, so it picks up print() calls and third-party stdout as well

When asked to debug an issue, `Tlamatini/tlamatini.log` is the first artifact to consult.

---

## Doc Generation (agent/doc_generation)

- `refresh_project_docs.py` — Pipeline that regenerates `tlamatini_app_summary.pdf` (the repository-root PDF overview) from the current source tree. Invoked manually during documentation passes
- `mardown_to_pdf.py` *(sic, typo preserved)* — Markdown → PDF helper used by `refresh_project_docs.py`

Output artifact: `tlamatini_app_summary.pdf` in the repository root.

---

## Services Layer (agent/services)

The `agent/services/` package owns cross-cutting backend logic that does not fit cleanly into a chain, a tool, or an agent script. As of May 2026 it groups three concerns:

**Answer / response post-processing**
- `response_parser.py` — strips the `END-RESPONSE` sentinel and miscellaneous LLM-output artifacts; renders the per-agent **Exec Report** HTML and appends it to the answer in the order documented in `docs/claude/exec-report.md`
- `answer_analizer.py` *(sic, typo preserved)* — LLM-based SUCCESS/FAILURE classifier used by Multi-Turn's Create-Flow gate; fails open on internal errors
- `filesystem.py` — filesystem helpers shared across views and tools

**Agent contracts & flow compilation** (commit `0bea21d`, May 2026)
- `agent_paths.py` — Frozen/source-aware resolution of `agents/` root and the per-session pool, plus canvas-id ↔ pool-name normalization (handles `Node Manager` → `node_manager`, `Gateway-Relayer` → `gateway_relayer`, `(2)` cardinal stripping)
- `agent_contracts.py` — `AgentContract` registry: per-agent connection-field shape (`input_field_by_slot` / `output_field_by_slot`), `parametrizer_fields`, `secret_paths`, plus `singleton` / `long_running` / `never_starts_targets` / `exclude_from_validation` flags. Discovers contracts from disk and merges builtin overrides; lru-cached and alias-normalized
- `flow_spec.py` — `FlowNode` / `FlowConnection` / `FlowSpec` dataclasses + `normalize_flow_payload()` / `flow_spec_to_legacy_json()`. The `schemaVersion: 2` in-memory representation that both surfaces (canvas snapshot from `acp-flow-snapshot.js` AND chat tool-call log from `agent_page_chat.js`) compile through
- `flow_compiler.py` — `compile_flow_spec()` / `compile_flow_payload()` (called from `views.compile_flow_view` and `views.flow_from_tool_calls_view`) and `list_pool_agents_for_validation()` (the new ground-truth replacement for the legacy `os.listdir` loop in Validate). Wires every connection per its contract, clears stale connection fields before re-writing, redacts `secret_paths` from `.flw` exports, and writes both `config.yaml` and `interconnection-scheme.csv` to the session pool when called with `write=True`. Coverage: `agent/test_flow_contracts.py`

The frontend reaches this layer over three new endpoints: `POST /agent/compile_flow/`, `POST /agent/flow_from_tool_calls/`, and `GET /agent/agent_contracts/` — all wired in `agent/urls.py`.

---

## Database Models (13 models in agent/models.py)

Key models:
- `Agent` - Agent type registry (idAgent, agentName, agentDescription, agentContent)
- `Mcp` - MCP UI toggle rows (enable/disable context providers)
- `Tool` - Tool UI toggle rows (enable/disable unified-agent tools)
- `Skill` - SKILL.md registry mirror (name, description, runtime, acpx_agent, **enabled**, frontmatter_json, body_sha256, last_loaded_at). Created in migration `0071_acpx_skills.py`; auto-seeded from `agent/skills_pkg/*/SKILL.md` by `agent/acpx/service.py::boot_skills()` (called on a background thread from `apps.AgentConfig.ready()`). The **ACPX-Skills navbar dropdown** (Browse / Configure / Diagnostics / Reload — added 2026-05-17) is the only user-facing edit surface and only ever touches the `enabled` boolean; all other fields are owned by `boot_skills()` and refreshed from disk on every reload. The disk-derived cache fields are NOT used by the admin UI (it reads fresh from `skill_registry`); they exist so historical revisions could surface frontmatter snapshots without an extra disk read.
- `AcpAgent` - Mirror of the ACPX agent registry (agent_id, command, description, enabled, healthy)
- `AcpSession` - One row per ACP child-process session
- `SkillInvocation` - Append-only audit row for each `SkillHarness.invoke()` call
- `ChatHistory` - Chat message history
- Plus session, context, and configuration models
