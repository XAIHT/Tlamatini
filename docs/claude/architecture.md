# Tlamatini — Architecture & Core Systems

## Configuration

Main config: `Tlamatini/agent/config.json`

Key settings:
- `embeding-model`: Embedding model for RAG
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
- Includes: execute_command, agent_parametrizer, agent_starter, agent_stopper, agent_stat_getter, launch_view_image, unzip_file, decompile_java, googler, + 32 wrapped chat-agent launchers (see `chat_agent_registry.CHAT_AGENT_TOOLS`)
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

## Database Models (13 models in agent/models.py)

Key models:
- `Agent` - Agent type registry (idAgent, agentName, agentDescription, agentContent)
- `Mcp` - MCP UI toggle rows (enable/disable context providers)
- `Tool` - Tool UI toggle rows (enable/disable unified-agent tools)
- `ChatHistory` - Chat message history
- Plus session, context, and configuration models
