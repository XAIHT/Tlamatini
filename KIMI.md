# KIMI.md — Complete Tlamatini System Knowledge Base

> **Purpose**: This file contains exhaustive, structured knowledge of the Tlamatini project so that Kimi (or any AI assistant) can load it in future sessions and immediately possess complete context for development, debugging, and feature creation.

---

## 1. Project Identity

**Name**: Tlamatini (Nahuatl for "one who knows")
**Repository**: `https://github.com/XAIHT/Tlamatini.git`
**License**: GPL-3.0
**Primary Developer**: angelahack1
**Platform**: Windows 11 (primary), with cross-platform Python support
**Language**: Python 3.12+ (only fully tested version)

**What it is**: A locally-deployed AI developer assistant built with Django, featuring:
- Advanced RAG system (FAISS + BM25 hybrid, metadata extraction, context budgeting, fallback mode)
- Request-scoped Multi-Turn orchestration with dynamic tool binding and global execution planning
- Visual Agentic Workflow Designer (ACP) with 57+ drag-and-drop agent types
- Multi-model LLM support (Ollama local, Anthropic Claude cloud, Qwen vision)
- Full PyInstaller packaging pipeline (build.py → installer → standalone .exe)
- Real-time web interface via Django Channels/WebSocket

---

## 2. Architecture Overview

### The Five Layers

```
Layer 1: Persisted Toggles (Database)
  - Mcp model rows: UI toggles for MCP context providers
  - Tool model rows: UI toggles for unified-agent tools
  - Agent model rows: Agent type registry (sidebar list)
  - Loaded by consumers.py, converted to status flags in factory.py

Layer 2: Runtime MCP Services
  - System-Metrics: mcp_system_server.py (WebSocket JSON)
  - Files-Search: mcp_files_search_server.py (gRPC)
  - Started from apps.py and management/commands/startserver.py

Layer 3: Context Fetcher Chains (Sidecars)
  - SystemRAGChain in chain_system_lcel.py
  - FileSearchRAGChain in chain_files_search_lcel.py
  - These inject system_context / files_context into the payload

Layer 4: Main Answer Chains
  - basic.py: BasicPromptOnlyChain (no docs)
  - history_aware.py: History-aware RAG with reranking
  - unified.py: Tool-enabled agent chains (LangGraph)
  - factory.py monkey-patches invoke() to inject context from sidecars

Layer 5: Unified-Agent Tools
  - Defined in tools.py as synchronous @tool functions
  - Returned by get_mcp_tools() (misnamed — returns LangChain tools, NOT MCP services)
  - Only active when unified-agent chain is selected
```

### Request Flow

1. User sends message via WebSocket (optionally with `multi_turn_enabled`)
2. `AgentConsumer` receives and routes
3. Context determination (RAG loaded?)
4. Internet check (classify if web search needed)
5. Chain selection (RAG / Basic / Unified Agent)
6. Multi-Turn gate: checked = planner/dynamic binding; unchecked = legacy one-shot
7. Context prefetch (system/file MCP)
8. Execution loop (tool calls, wrapped agent monitoring)
9. Streaming response via WebSocket

### Technology Stack

| Category | Technologies |
|----------|-------------|
| Backend | Python 3.12+, Django 5.2.4, Django Channels 4.1, Daphne (ASGI) |
| Frontend | HTML5, Bootstrap 5, JavaScript (modular), jQuery, jQuery UI |
| AI/ML | LangChain 0.3.27, LangGraph 0.2.74, FAISS, rank-bm25, PyAutoGUI |
| LLM APIs | Anthropic Claude (anthropic 0.74.1), Ollama REST API, MCP 1.25.0 |
| Database | SQLite |
| Communication | WebSockets, gRPC (grpcio 1.76.0) |
| Packaging | PyInstaller, NSIS installer |

---

## 3. Directory Structure

```
Tlamatini/                          # Git root
├── CLAUDE.md                       # Root onboarding doc (imports docs/claude/*.md)
├── docs/claude/                    # Specialized onboarding docs
│   ├── INDEX.md                    # Map of what lives in each file
│   ├── architecture.md             # Config, Five Layers, app log, DB models
│   ├── multi-turn.md               # Multi-Turn mode, Create Flow, Parametrizer sections
│   ├── exec-report.md              # Exec Report pipeline + ordering contract
│   ├── agents.md                   # Agent creation, 57-type catalog, FlowCreator, FlowHypervisor
│   ├── mcp-tools.md                # Creating a new MCP or tool
│   ├── frontend.md                 # Chat + ACP modules, Canvas DOM contract
│   └── gotchas.md                  # Claude API client, build/lint, hardcoded assumptions, recent fixes
├── README.md                       # Full user-facing documentation (very large, 4000+ lines)
├── NEW_AGENT_RECOMMENDATIONS.md    # Roadmap for new agents (Tester, Reviewer, etc.)
├── build.py                        # PyInstaller build script
├── build_installer.py              # NSIS-based installer builder
├── build_uninstaller.py            # Uninstaller builder
├── install.py / uninstall.py       # Tkinter GUI installer/uninstaller
├── requirements.txt                # Python deps
├── eslint.config.mjs               # ESLint config
│
├── Tlamatini/                      # Django project root
│   ├── manage.py                   # Django entrypoint; tees stdout/stderr into tlamatini.log
│   ├── db.sqlite3                  # SQLite database
│   ├── .agents/workflows/
│   │   └── create_new_agent.md     # ** SKILL: Step-by-step agent creation guide **
│   ├── .mcps/
│   │   └── create_new_mcp.md       # ** SKILL: MCP/tool creation guide **
│   │
│   ├── tlamatini/                  # Django project config
│   │   ├── settings.py             # Django settings (Channels, WhiteNoise)
│   │   ├── urls.py                 # Root URL routing
│   │   ├── asgi.py                 # ASGI config with WebSocket routing
│   │   ├── middleware.py           # Custom middlewares
│   │   └── context_processors.py   # Template context processors
│   │
│   ├── agent/                      # Core Django app (ALL business logic)
│   │   ├── prompt.pmt              # System prompt template for chat LLM
│   │   ├── config.json             # LLM and RAG configuration
│   │   ├── config_loader.py        # Frozen/source-aware config reader
│   │   ├── views.py                # 103+ HTTP endpoints
│   │   ├── consumers.py            # WebSocket consumer (async chat handler)
│   │   ├── models.py               # 13 database models
│   │   ├── urls.py                 # URL routing
│   │   ├── tools.py                # LangChain @tool definitions and wrapped chat-agent launchers
│   │   ├── mcp_agent.py            # MCP unified agent builder and multi-turn executor
│   │   ├── global_execution_planner.py  # Request-scoped DAG planner
│   │   ├── capability_registry.py  # Request-scoped capability scoring
│   │   ├── chat_agent_registry.py  # Wrapped chat-agent tool registry
│   │   ├── chat_agent_runtime.py   # Wrapped-runtime lifecycle helpers
│   │   ├── global_state.py         # Thread-safe singleton (Singleton pattern)
│   │   ├── constants.py            # Application constants and regex patterns
│   │   │
│   │   ├── rag/                    # RAG system package
│   │   │   ├── factory.py          # Chain builders, MCP context patching
│   │   │   ├── interface.py        # Public API (ask_rag)
│   │   │   ├── chains/             # basic.py, history_aware.py, unified.py
│   │   │   └── ...
│   │   │
│   │   ├── agents/                 # 57+ workflow agent templates
│   │   │   ├── starter/            # Flow initiator
│   │   │   ├── ender/              # Flow terminator
│   │   │   ├── stopper/            # Pattern-based agent terminator
│   │   │   ├── cleaner/            # Post-termination cleanup
│   │   │   ├── raiser/             # Event-driven launcher
│   │   │   ├── executer/           # Shell command executor
│   │   │   ├── pythonxer/          # Python script executor with Ruff validation
│   │   │   ├── sqler/              # SQL Server query execution
│   │   │   ├── mongoxer/           # MongoDB script execution
│   │   │   ├── ssher/              # SSH remote commands
│   │   │   ├── scper/              # SCP file transfer
│   │   │   ├── dockerer/           # Docker container management
│   │   │   ├── kuberneter/         # Kubernetes command executor
│   │   │   ├── apirer/             # HTTP/REST API request agent
│   │   │   ├── jenkinser/          # CI/CD pipeline trigger
│   │   │   ├── gitter/             # Git operations
│   │   │   ├── pser/               # PowerShell commands
│   │   │   ├── prompter/           # LLM prompt execution
│   │   │   ├── summarizer/         # Log monitoring with LLM event detection
│   │   │   ├── crawler/            # Developer-oriented web crawler
│   │   │   ├── googler/            # Google search (Playwright + text extraction)
│   │   │   ├── file_creator/       # File creation utility
│   │   │   ├── file_extractor/     # File text extraction
│   │   │   ├── file_interpreter/   # Document parsing and text/image extraction
│   │   │   ├── image_interpreter/  # LLM vision-based image analysis
│   │   │   ├── j_decompiler/       # Java artifact decompiler (jd-cli)
│   │   │   ├── shoter/             # Screenshot capture
│   │   │   ├── mouser/             # Mouse pointer movement (PyAutoGUI)
│   │   │   ├── keyboarder/         # Keyboard typing / hotkey automation
│   │   │   ├── mover/              # File move/copy with glob patterns
│   │   │   ├── deleter/            # File deletion with glob patterns
│   │   │   ├── gatewayer/          # HTTP webhook / folder-drop ingress
│   │   │   ├── gateway_relayer/    # Bridges provider webhooks into Gatewayer
│   │   │   ├── node_manager/       # Infrastructure registry and node supervision
│   │   │   ├── parametrizer/       # Interconnection engine (maps outputs to inputs)
│   │   │   ├── flowbacker/         # Session backup and cleanup handoff
│   │   │   ├── flowcreator/        # AI-powered flow designer
│   │   │   ├── flowhypervisor/     # System-managed LLM anomaly detector
│   │   │   ├── barrier/            # Synchronization barrier for flow control
│   │   │   ├── and/                # AND logic gate
│   │   │   ├── or/                 # OR logic gate
│   │   │   ├── forker/             # Automatic A/B path router
│   │   │   ├── asker/              # Interactive A/B path chooser
│   │   │   ├── counter/            # Persistent counter with threshold routing
│   │   │   ├── croner/             # Scheduled trigger
│   │   │   ├── sleeper/            # Delay agent
│   │   │   ├── emailer/            # SMTP email sender
│   │   │   ├── recmailer/          # IMAP email receiver/monitor
│   │   │   ├── whatsapper/         # WhatsApp notifications (TextMeBot)
│   │   │   ├── telegramer/         # Telegram message sender
│   │   │   ├── telegramrx/         # Telegram message receiver
│   │   │   ├── notifier/           # Desktop notification + sound
│   │   │   ├── monitor_log/        # LLM-powered log file monitor
│   │   │   ├── monitor_netstat/    # LLM-powered network port monitor
│   │   │   ├── kyber_keygen/       # CRYSTALS-Kyber key pair generation
│   │   │   ├── kyber_cipher/       # CRYSTALS-Kyber encryption
│   │   │   └── kyber_decipher/     # CRYSTALS-Kyber decryption
│   │   │
│   │   ├── templates/agent/        # HTML templates
│   │   ├── static/agent/           # Frontend assets
│   │   │   ├── js/                 # 23 JS modules (8 chat + 11 ACP + 4 shared)
│   │   │   ├── css/                # Stylesheets
│   │   │   └── sounds/             # Audio alerts
│   │   └── migrations/             # Django migrations
│   │
│   ├── jd-cli/                     # Bundled Java decompiler
│   └── staticfiles/                # Collected static files (WhiteNoise)
```

---

## 4. Configuration System

Main config: `Tlamatini/agent/config.json`

Frozen builds resolve config from install directory next to executable. Source mode resolves from `Tlamatini/agent/config.json`. `CONFIG_PATH` env var overrides both.

Key config keys:
- `embeding-model`: Embedding model for RAG
- `chained-model`: Primary chat model
- `unified_agent_model`: Model for multi-turn tool loop
- `ollama_base_url`: Ollama server URL
- `ollama_token`: Bearer token for authenticated Ollama
- `ANTHROPIC_API_KEY`: Claude API key
- `enable_unified_agent`: Enable tool-calling agent
- `unified_agent_max_iterations`: Max tool-call turns (default 100-256)
- `chat_agent_limit_runs`: Wrapped-run listing limit
- `image_interpreter_model`, `image_interpreter_base_url`: Vision model settings
- Chunking: `chunk_size`, `chunk_overlap`, `max_chunks_per_file`
- Retrieval: `k_vector`, `k_bm25`, `k_fused`, `enable_bm25`, `rrf_k`
- Context limits: `max_doc_chars`, `max_context_chars`, `context_budget_allocation`
- Internet search: `internet_classifier_model`, `web_summarizer_model`, `web_context_max_chars`
- MCP services: `mcp_system_server_host`, `mcp_system_server_port`, `mcp_files_search_server_port`

---

## 5. Database Models (13 models in agent/models.py)

Key models:
- `AgentMessage` - Chat messages (user, conversation_user, message, timestamp)
- `LLMProgram` / `LLMSnippet` - Saved code/program content
- `Prompt` / `Omission` - Prompt templates and file omission patterns
- `ContextCache` - SHA1-hashed query → context blob caching
- `Mcp` - MCP UI toggle rows (idMcp, mcpName, mcpDescription, mcpContent)
- `Tool` - Tool UI toggle rows (idTool, toolName, toolDescription, toolContent)
- `Agent` - Agent type registry (idAgent, agentName, agentDescription, agentContent)
- `AgentProcess` - Tracked running agent processes (PID)
- `ChatAgentRun` - Wrapped chat-agent run records (runId, status, pid, etc.)
- `Asset` - Generic asset storage
- `SessionState` - Persists user session state across reconnections (24h expiry)

---

## 6. RAG System

Located in `agent/rag/`. Advanced custom pipeline:

- **Document loaders**: `loaders.py` — loads files with size reporting
- **Text splitters**: `splitters.py` — RecursiveCharacterTextSplitter
- **Retrieval**: `retrieval.py` — FAISS + BM25 hybrid via Reciprocal Rank Fusion
- **Context budgeting**: Prioritizes doc chunks within token limits (high_relevance 60%, architecture 20%, related 15%, documentation 5%)
- **Metadata extraction**: `rag_enhancements.py` — code structure, file role classification, dependency tracking, cross-references
- **Memory-Insufficient Context Fallback**: If embeddings/vector-store construction fail due to RAM, preserves loaded source files and continues from packed raw context instead of dropping to empty-context chat

Chain types in `agent/rag/chains/`:
- `basic.py`: BasicPromptOnlyChain (no docs, fallback)
- `history_aware.py`: History-aware RAG with reranking
- `unified.py`: Tool-enabled agent chains (LangGraph)

`factory.py` builds chains and monkey-patches `invoke()` to inject MCP context from sidecars.

---

## 7. Multi-Turn Orchestration

### When Multi-Turn is CHECKED:
1. Prompt-shape validation is skipped
2. Request-scoped global execution plan/DAG is built (`global_execution_planner.py`)
3. MCP contexts are prefetched selectively (not indiscriminately)
4. Only planned tool subset is bound (default cap: **20 tools**, configurable via `max_selected_tools`)
5. Wrapped agents launch in headless/background mode (no console popups)
6. `MultiTurnToolAgentExecutor` deduplicates wrapped chat-agent calls with identical arguments
7. After final answer, `services/answer_analizer.py` classifies as SUCCESS/FAILURE
8. Frontend renders "Create Flow" button on SUCCESS → converts tool-call log into downloadable `.flw`

### When Multi-Turn is UNCHECKED:
- Legacy one-shot behavior preserved exactly
- Legacy prompt validation, legacy MCP context prefetch, full-tool binding, visible-console launch

### Global Execution Planner (`global_execution_planner.py`)
- Builds DAG with nodes: `prefetch` → `execute` → `monitor` → `answer`
- `CapabilityRegistry` (`capability_registry.py`) scores tools/capabilities against request text
- Short follow-up scoring: ≤4 meaningful tokens boosts scores from last 4 chat messages (+15 max)
- Planner threshold = 6 if contexts selected, else 2
- Run-control tools (list/status/log/stop) auto-injected when wrapped agents selected

### MultiTurnToolAgentExecutor (`mcp_agent.py`)
- Explicit multi-turn tool loop (not opaque AgentExecutor)
- Max iterations: 256 (configurable)
- Repetition detection: `_REPEAT_LIMIT = 3` consecutive identical tool-call rounds → injects stop nudge
- Empty final response nudge: asks model to summarize tool results
- Wrapped agent dedup: hashes `tool_name + sorted-JSON args` into `_wrapped_agent_signatures`

---

## 8. Unified Agent & Tools

### Tool Categories

**Direct @tools** (defined in `agent/tools.py`):
- `execute_command` — shell command execution
- `execute_file` — run Python script file
- `agent_parametrizer` — configure template agent config.yaml
- `agent_starter` — start template agent
- `agent_stopper` — stop template agent
- `agent_stat_getter` — check template agent status
- `launch_view_image` — open image viewer
- `unzip_file` — extract ZIP archives
- `decompile_java` — JAR/WAR decompilation (bundled jd-cli)
- `googler` — Google search via Playwright (MUST run in ThreadPoolExecutor due to Django Channels async loop)
- `execute_netstat` — network connections
- `get_current_time` — current time

**Wrapped Chat-Agent Tools** (registered in `agent/chat_agent_registry.py`):
32+ specs in `WRAPPED_CHAT_AGENT_SPECS`. Key ones:
- `chat_agent_executer`, `chat_agent_pythonxer`, `chat_agent_dockerer`, `chat_agent_kuberneter`
- `chat_agent_ssher`, `chat_agent_scper`, `chat_agent_gitter`
- `chat_agent_sqler`, `chat_agent_mongoxer`, `chat_agent_apirer`
- `chat_agent_send_email`, `chat_agent_telegramer`, `chat_agent_whatsapper`
- `chat_agent_notifier`, `chat_agent_shoter`
- `chat_agent_file_creator`, `chat_agent_move_file`, `chat_agent_deleter`
- `chat_agent_file_extractor`, `chat_agent_file_interpreter`, `chat_agent_image_interpreter`
- `chat_agent_summarize_text`, `chat_agent_prompter`, `chat_agent_crawler`
- `chat_agent_pser` (PowerShell), `chat_agent_jenkinser`
- `chat_agent_monitor_log`, `chat_agent_monitor_netstat` (long-running)
- `chat_agent_kyber_keygen`, `chat_agent_kyber_cipher`, `chat_agent_kyber_deciph`
- `chat_agent_run_list`, `chat_agent_run_status`, `chat_agent_run_log`, `chat_agent_run_stop` (management)

Each `ChatWrappedAgentSpec` has: key, template_dir, tool_name (must start with `chat_agent_`), display_name, purpose, example_request, aliases, security_hints, poll_window_seconds, long_running.

### Tool Return Format
Wrapped chat-agent tools return JSON string with: `run_id`, `status`, `log_excerpt`, `runtime_dir`, `log_path`

### Tool Status Keys
`factory.py` maps `Tool.toolDescription` to status keys like `tool_{description.lower()}_status`. These are handwritten and CAN DRIFT from DB descriptions. Always verify the actual mapping.

---

## 9. MCP Services

**IMPORTANT**: In this codebase, "MCP" can mean THREE different things:
1. A real runtime service (System-Metrics, Files-Search)
2. A persisted UI toggle stored in the `Mcp` database table
3. A LangChain tool returned by `get_mcp_tools()` (misnamed!)

### Current Real Runtime Services:
- **System-Metrics**: `mcp_system_server.py` (WebSocket JSON) + `mcp_system_client.py`
- **Files-Search**: `mcp_files_search_server.py` (gRPC) + `mcp_files_search_client.py`
- Practical caller for Files-Search: `chain_files_search_lcel.py` (NOT the gRPC client directly)

### Critical Hardcoded Assumptions:
- `factory.py` recognizes ONLY `System-Metrics` and `Files-Search` by Mcp description
- Frontend MCP dialog is hardcoded for two checkboxes (unlike dynamic tool UI)
- `mcp_files_search_client_uri` in config is UNUSED by main chain path
- `FileSearchRAGChain` falls back to `localhost:50051` for gRPC
- Adding a new `Mcp` row without extending `factory.py` does NOTHING

---

## 10. Agentic Workflow Designer (ACP)

Visual drag-and-drop workflow designer at `/agentic_control_panel/`.

### Frontend Modules (23 JS files):
**Chat Interface (8)**:
- `agent_page_init.js` — WebSocket setup, app initialization
- `agent_page_chat.js` — Chat message handling, Flow-Generator mapping
- `agent_page_canvas.js` — Code canvas rendering
- `agent_page_context.js` — RAG context management
- `agent_page_dialogs.js` — Modal dialogs
- `agent_page_layout.js` — UI layout
- `agent_page_state.js` — Client state
- `agent_page_ui.js` — General UI utilities

**ACP Workflow Designer (11)**:
- `agentic_control_panel.js` — Entry point
- `acp-globals.js` — Shared global state, `updateCanvasContentSize()`
- `acp-canvas-core.js` — Canvas rendering, drag-and-drop, classMap, connection handlers (6 touch points per agent)
- `acp-canvas-undo.js` — Undo/redo state (1024 actions)
- `acp-agent-connectors.js` — 50+ agent connection handlers
- `acp-control-buttons.js` — Start/stop/pause/hypervisor
- `acp-file-io.js` — .flw save/load
- `acp-running-state.js` — LED indicators, process monitoring
- `acp-session.js` — Session pool management
- `acp-layout.js` — Canvas layout utilities
- `acp-validate.js` — Flow validation engine

**Shared (4)**:
- `canvas_item_dialog.js` — Agent config dialog on canvas
- `contextual_menus.js` — Right-click menus
- `tools_dialog.js` — Tool enable/disable dialog
- `acp-undo-manager.js` — Undo stack manager

### ACP Canvas DOM Contract (CRITICAL)
The canvas is a **two-layer DOM**:
1. `#submonitor-container` — the **viewport** with `overflow: auto`
2. `#canvas-content` — the **content layer** inside `#submonitor-container` where ALL items live

**Rules**:
- Coordinate reference frame is `canvasContent`, NOT `submonitor`
- All math must use `canvasContent.getBoundingClientRect()` (already reflects scroll offset)
- NEVER manually add `submonitor.scrollLeft/scrollTop`
- Append items to `canvasContent`, NEVER to `submonitor`
- Item positions clamped `>= 0` only (no upper bounds)
- Call `updateCanvasContentSize()` after: item creation, drag end, .flw load, undo/redo restoration
- Selection box uses `canvasContent.getBoundingClientRect()`

### Agent Naming Convention (CRITICAL — most common source of bugs)
The `agentDescription` from DB is the single source of truth. It transforms differently per context:

| Context | Transform | "Node Manager" | "Shoter" |
|---|---|---|---|
| CSS classMap key | `name.toLowerCase().replace(/\s+/g, '-')` | `'node-manager'` | `'shoter'` |
| Sidebar visual | Same as classMap via `getAgentTypeClass()` | `'node-manager'` | `'shoter'` |
| Connection handlers | `name.toLowerCase()` (preserves spaces) | `'node manager'` | `'shoter'` |

**For multi-word agents**, the forms DIFFER:
- classMap key and sidebar visual resolver use **hyphens**: `'node-manager'`
- Connection handlers use **spaces**: `'node manager'`

### CSS Gradient Rule
Every agent MUST have a **4-color gradient** (0%, 33%, 66%, 100%) in `agentic_control_panel.css`. The sidebar icon inherits this automatically through `applyAgentToolIconStyle()` — NEVER duplicate gradient strings in `populateAgentsList()`.

---

## 11. All 57 Workflow Agent Types

### Control Agents
- **Starter** — Entry point, launches first agents
- **Ender** — Terminates all agents, launches Cleaners. `target_agents` = agents to KILL, `output_agents` = Cleaners to LAUNCH after, `source_agents` = graphical only
- **Stopper** — Kills specific agents based on log patterns
- **Cleaner** — Deletes logs/PIDs after Ender
- **Sleeper** — Waits N ms then starts next
- **Croner** — Scheduled trigger (HH:MM format)

### Routing Agents
- **Raiser** — Watches source log for pattern, starts downstream when found
- **Forker** — Auto-routes to Path A or B based on two patterns
- **Asker** — Interactive A/B choice for user (dialog popup)
- **Counter** — Persistent counter, routes L (< threshold) or G (>= threshold)

### Logic Gates
- **OR** — Fires when EITHER of 2 sources completes
- **AND** — Fires when BOTH of 2 sources complete
- **Barrier** — Fires when ALL N sources complete (generalized AND)

### Action Agents
- **Executer** — Shell commands
- **Pythonxer** — Inline Python (exit code gating)
- **Prompter** — LLM prompt execution
- **Summarizer** — LLM text/log summarization
- **Crawler** — Web crawling with LLM analysis
- **Googler** — Google search + text extraction (Playwright)
- **Apirer** — HTTP REST API calls
- **Gitter** — Git operations
- **Ssher** — SSH remote commands
- **Scper** — SCP file transfer
- **Dockerer** — Docker commands
- **Kuberneter** — kubectl commands
- **Pser** — PowerShell commands
- **Jenkinser** — Jenkins job triggers
- **Sqler** — SQL queries (external window)
- **Mongoxer** — MongoDB operations (external window)
- **Mover** — File move/copy with glob patterns
- **Deleter** — File deletion with glob patterns
- **Shoter** — Screenshot capture
- **Mouser** — Mouse/keyboard simulation (PyAutoGUI)
- **Keyboarder** — Keyboard typing / hotkey automation
- **File-Creator** — Creates files with specified content
- **File-Interpreter** — LLM reads and interprets file contents
- **File-Extractor** — Raw text extraction (PDF, DOCX, etc.)
- **Image-Interpreter** — LLM vision analysis
- **J-Decompiler** — JAR/WAR decompilation (bundled jd-cli)
- **Telegramer** — Sends Telegram messages

### Cryptography Agents
- **Kyber-KeyGen** — CRYSTALS-Kyber key pair generation (post-quantum)
- **Kyber-Cipher** — Kyber encryption
- **Kyber-DeCipher** — Kyber decryption

### Utility Agents
- **Parametrizer** — Maps structured output from one agent into another's config.yaml (strict single-lane queue)
- **FlowBacker** — Backs up session logs/configs
- **Gatewayer** — HTTP webhook ingress + folder-drop watcher
- **Gateway-Relayer** — Bridges GitHub/GitLab webhooks into Gatewayer
- **Node-Manager** — Infrastructure registry and node supervision

### Terminal/Monitoring Agents (do NOT start downstream)
- **Monitor-Log** — LLM-powered log file monitor
- **Monitor-Netstat** — LLM-powered network port monitor
- **Emailer** — SMTP email on pattern detection
- **RecMailer** — IMAP email receiver/monitor
- **Notifier** — Desktop notification + sound
- **Whatsapper** — WhatsApp messages (TextMeBot)
- **TelegramRX** — Telegram message receiver
- **FlowHypervisor** — LLM-powered flow health monitor (system agent)

---

## 12. Agent Creation System

Every agent follows the **exact same 8-step process** documented in `Tlamatini/.agents/workflows/create_new_agent.md`.

### Agent Directory Structure
```
agent/agents/<agent_name>/
├── <agent_name>.py     # Main Python script
└── config.yaml         # Default configuration
```

### Critical Boilerplate Requirements
1. `os.environ['FOR_DISABLE_CONSOLE_CTRL_HANDLER'] = '1'` MUST be first import
2. PID file written immediately on start, removed in `finally` block
3. Log file name MUST be `{directory_name}.log`
4. Copy ALL helper functions from `shoter.py` exactly:
   - `load_config`, `get_python_command`, `get_user_python_home`, `get_agent_env`
   - `get_pool_path`, `get_agent_directory`, `get_agent_script_path`
   - `is_agent_running`, `wait_for_agents_to_stop`, `start_agent`
   - `write_pid_file`, `remove_pid_file`
5. **Concurrency guard**: `wait_for_agents_to_stop(target_agents)` BEFORE `start_agent()` loop
6. Reanimation support: `_IS_REANIMATED` before `logging.basicConfig`, marker log in `main()`
7. If agent polls source logs: implement `reanim*.pos` offset persistence

### Connection Fields Rules
- `target_agents: []` — if agent starts downstream agents
- `source_agents: []` — if agent monitors upstream logs
- `output_agents: []` — ONLY for Stopper/Ender/Cleaner (canvas wiring, NOT for starting)
- Ender is special: `target_agents` (kill), `output_agents` (launch Cleaners), `source_agents` (graphical only)
- OR/AND use `source_agent_1`, `source_agent_2`
- Asker/Forker use `target_agents_a`, `target_agents_b`
- Counter uses `target_agents_l`, `target_agents_g`

### Structured Output for Parametrizer
If agent produces structured output for Parametrizer, emit using **unified section format**:
```
INI_SECTION_<AGENT_TYPE><<<
field1: value1
field2: value2

multi-line body content (becomes 'response_body')
>>>END_SECTION_<AGENT_TYPE>
```
Rules:
- `<AGENT_TYPE>` = UPPERCASE base name (e.g., `APIRER`, `CRAWLER`)
- Must be single atomic `logging.info()` call
- Register in 3 places: `parametrizer.py` → `SECTION_AGENT_TYPES`, `views.py` → `PARAMETRIZER_SOURCE_OUTPUT_FIELDS`, README.md table

---

## 13. Parametrizer & Interconnection

Parametrizer (`agent/agents/parametrizer/parametrizer.py`) maps structured outputs from source agents into target agents' `config.yaml`.

### Key Concepts
- Reads `interconnection-scheme.csv` to know field mappings
- Strict **single-lane queue**: one source, one target, one-at-a-time
- Iterative execution: if source produces N output blocks, target runs N times
- Progress state persisted in `reanim_{source}.pos` files
- Config backup/restore cycle: backup → apply mappings → start target → wait → restore → commit cursor

### Reanimation States
- `idle` → `backup_ready` → `config_applied` → `waiting_target` → `target_finished_restore_pending` → back to `idle`

---

## 14. Exec Report

When "Exec Report" toolbar checkbox is ticked alongside Multi-Turn, final answer gets HTML tables appended — one per kind of state-changing agent that fired.

### Capture Pipeline
1. `MultiTurnToolAgentExecutor._invoke_tool()` checks `_EXEC_REPORT_TOOLS.get(tool_name)` after EVERY tool invocation
2. Capture is **unconditional** (ignores per-request flag). Flag only gates rendering.
3. `_build_result_dict()` always emits `exec_report_entries`
4. `UnifiedAgentChain.invoke()` forwards entries when `exec_report_enabled=True`
5. `ask_rag()` stores in `global_state`
6. `AgentConsumer.queue_llm_retrieval()` reads state, passes to `process_llm_response`
7. `_render_exec_report_html()` in `services/response_parser.py` groups by `agent_key` in **first-appearance order**
8. Appended to `llm_response` before WebSocket broadcast

### CRITICAL ORDERING CONTRACT
In `process_llm_response()`, `save_message()` MUST run AFTER exec-report HTML is appended. Order:
1. Strip `END-RESPONSE` and artifacts
2. Run SUCCESS/FAILURE classification against prose-only answer
3. Append exec-report HTML
4. **THEN** `save_message`
5. Broadcast over WebSocket

### Adding a State-Changing Agent to Exec Report (3 edits)
1. `agent/mcp_agent.py` → add to `_EXEC_REPORT_TOOLS`: `"tool_name": ("agent_key", "Display Name")`
2. `agent/static/agent/css/agent_page.css` → add `.exec-report-caption-<agent_key>` + `.exec-report-<agent_key> .exec-report-cmd`
3. If caption background dark, add to `thead th` dark-tinted selector list

Skip for read-only/monitoring agents (Crawler, Googler, Prompter, Summarizer, File-Interpreter/Extractor, Image-Interpreter, Shoter, Monitor-*, Recmailer, FlowHypervisor).

---

## 15. Create Flow from Multi-Turn

Successful Multi-Turn responses can become `.flw` workflows via the "Create Flow" button.

Pipeline:
1. Tool-call log capture in `mcp_agent.py` (`_tool_calls_log`)
2. Success classification via `services/answer_analizer.py::analyze_answer_success()` (LLM-based, fails open)
3. WebSocket broadcast from `consumers.py`
4. Frontend button render gate in `agent_page_chat.js`
5. Flow synthesis: maps tool names → agent display names, lays out nodes left-to-right, wires sequential `target_agents`

### Flow-Generator Mapping
If a wrapped chat-agent tool should produce populated `.flw` nodes, add branch in `_mapToolArgsToAgentConfig()` in `agent_page_chat.js`:
- Use `set(key, value)` helper (refuses empty strings)
- Field names MUST match template `config.yaml` keys EXACTLY
- Never set `target_agents` / `source_agents` here
- For dotted nested keys, use `collectDotted('smtp')`

---

## 16. Frontend Architecture Details

### WebSocket Message Types (Client → Server)
- `set-canvas-as-context` / `unset-canvas-as-context`
- `set-directory-as-context` / `set-file-as-context`
- `cancel-current` — aggressive cancel with chain rebuild
- `reconnect-llm-agent`
- `clean-history-and-reconnect`
- `clear-context`
- `save-files-from-db`
- `enable-llm-internet-access` / `disable-llm-internet-access`
- `view-context-dir-in-canvas`
- `set-file-omissions`
- `set-mcps`
- `set-tools`
- `set-agents`
- `run-flow` / `pause-flow` / `stop-flow`

### WebSocket Message Types (Server → Client)
- `agent_message` — main chat message
- `mcp` / `tool` / `agent` — establishment messages
- `heartbeat` — keepalive every 20s
- `session-restored`
- `context-path-set`

---

## 17. Build & Packaging

```bash
# Step 1: Build the app
python build.py

# Step 2: Build the uninstaller
python build_uninstaller.py

# Step 3: Build the installer
python build_installer.py
```

Frozen build resolves paths via `os.path.dirname(sys.executable)` vs source mode `os.path.dirname(os.path.abspath(__file__))`. Both modes MUST be supported in any new tool.

### Linting
```bash
# Python
python -m ruff check

# JavaScript/CSS
npm run lint
```

---

## 18. Skills Available in Project

### `Tlamatini/.agents/workflows/create_new_agent.md`
Complete 8-step guide for creating workflow agents. Covers: backend script + config, Django view + URL, DB migration, CSS gradient, JS integration (4 files), FlowCreator skill update, README updates, linting.

### `Tlamatini/.mcps/create_new_mcp.md`
Guide for adding MCP-backed capabilities or tools. Emphasizes classifying requests into: Tool only / Wrapped chat-agent tool / MCP context provider only / Both. Contains detailed file-scope matrices and self-check checklists.

### `Tlamatini/agent/agents/flowcreator/agentic_skill.md`
Reference for FlowCreator AI to design flows. Key principles: minimize agents, sequential chains, lean Starter, terminal agents at END.

### External Skills (in `.codex/skills/`)
- `full-project-pdf-dossier/SKILL.md` — Complete project PDF dossier generation
- `overlap-safe-pptx-dossier/SKILL.md` — Technical PPTX deck creation (Tlamatini-style)

---

## 19. Coding Conventions & Critical Rules

### Python
- Synchronous `@tool` functions in `tools.py`
- Return plain strings (or JSON strings for wrapped agents)
- Validate dangerous paths with `path_guard.validate_tool_path`
- Support both frozen and non-frozen path resolution
- Use `os.environ['FOR_DISABLE_CONSOLE_CTRL_HANDLER'] = '1'` in agent scripts

### JavaScript
- **NEVER** duplicate CSS gradient strings in `populateAgentsList()`
- Use `applyAgentToolIconStyle(iconDiv, description)` for sidebar icons
- Connection handlers use **spaced lowercase** form (`'node manager'`)
- classMap keys use **hyphenated** form (`'node-manager'`)
- `/* global */` declarations must be updated in all 3 JS files when adding connectors

### CSS
- 4-color gradients for agents (0%, 33%, 66%, 100%)
- Must be unique — check existing gradients before choosing
- Hover state uses lighter/brighter versions
- Exec report caption gradients must mirror canvas-item gradients

### Database Migrations
- Always create NEW migration file (do NOT edit `0002_populate_db.py` in existing projects)
- `agentDescription` is the single source of truth for all naming

---

## 20. Common Pitfalls (from create_new_agent.md)

1. **Naming drift** — `agentDescription` transforms differently in CSS classMap, sidebar, and connection handlers
2. **Empty-string overwrites** — backend deep-merges posted JSON over template config.yaml. Use "omit if empty" semantics
3. **Pool-name cardinal mismatch** — pool folders are `<base>_<N>` (e.g., `executer_2`). Never emit bare `"executer"` into `target_agents`
4. **Forgetting `_IS_REANIMATED`** — add marker BEFORE `logging.basicConfig(...)`
5. **Concurrency guard** — `wait_for_agents_to_stop(target_agents)` before `start_agent()` loop
6. **`_EXEC_REPORT_TOOLS` miss** — state-changing agents must be registered or they won't appear in Exec Report
7. **Flow-Generator `_mapToolArgsToAgentConfig` miss** — without it, generated `.flw` nodes have no config fields set
8. **Forgetting the 6 JS edit locations** in `acp-canvas-core.js`
9. **CSS gradient duplicated in JS** — never hard-code gradient in `populateAgentsList()`

---

## 21. Known Hardcoded Assumptions

1. `factory.py` recognizes only `System-Metrics` and `Files-Search` by description
2. Frontend MCP dialog is hardcoded for two checkboxes
3. Tool UI is dynamic; MCP UI is not
4. `get_mcp_tools()` returns LangChain tools, not MCP services
5. `ask_rag()` does not fetch MCP data itself
6. Files-Search main path uses `FileSearchRAGChain`, not `mcp_files_search_client.py`
7. `mcp_files_search_client_uri` in config is unused by main chain
8. `FileSearchRAGChain` falls back to `localhost:50051`
9. Tool status keys are handwritten and can drift
10. `mcpContent` is stored as string text, not boolean
11. Planner default `max_selected_tools` = 20 (lowered from 50)
12. `tlamatini.log` is truncated on every server start (mode `'w'`) and has no rotation
13. `UnifiedAgentChain.invoke()` has hardcoded payload key whitelist — new flags MUST be added or silently dropped
14. Exec Report capture point is `_invoke_tool()`, not chain layer
15. Flow-Generator emits cardinal-suffixed pool names (`executer_1`, `executer_2`)

---

## 22. Recent Fixes to Remember

- **Planner statelessness on short follow-ups** — Solved by passing `chat_history_text` into planner. Preserve this argument.
- **Wrapped chat-agent dedup** — `_wrapped_agent_signatures` set in `MultiTurnToolAgentExecutor`. Do not remove.
- **Googler Playwright + async loop** — Must wrap in `ThreadPoolExecutor(max_workers=1)`. Any new sync-Playwright tool must do the same.
- **Cancel/rebuild race** — `consumers.py` now `await`s `setup_rag_chain()` during cancel. Must not use `asyncio.create_task(...)`.
- **Exec-report persistence ordering** — `save_message()` must run AFTER exec-report HTML append in `process_llm_response()`.
- **ACP canvas DOM split** — `#canvas-content` vs `#submonitor-container`. All coordinate math uses `canvasContent.getBoundingClientRect()`.

---

## 23. Roadmap: Recommended New Agents

From `NEW_AGENT_RECOMMENDATIONS.md`:

| Priority | Agent | Purpose |
|----------|-------|---------|
| 1 | **Tester** | Test runner (pytest, jest, junit) with pass/fail routing |
| 2 | **Reviewer** | AI code review (LLM-powered diff analysis) |
| 3 | **Analyzer** | Static analysis (Ruff, ESLint, Bandit) |
| 4 | **Jiraer** | Issue tracker integration (Jira/GitHub Issues) |
| 5 | **Logger** | Structured log writer / report aggregator |
| 6 | **Vaulter** | Secrets / environment injection |
| 7 | **Webhooker** | Webhook listener (inbound HTTP endpoint) |
| 8 | **Terraformer** | Infrastructure as Code (Terraform/Pulumi) |
| 9 | **Metrixer** | Metrics collector (Prometheus/Grafana) |
| 10 | **Diffr** | File/content comparison |
| 11 | **Zipper** | Archive creation (ZIP/TAR) |

---

## 24. System Prompt & LLM Identity

The chat LLM system prompt lives in `Tlamatini/agent/prompt.pmt`. The LLM identity is **"Tlamatini"** (Nahuatl for "one who knows"). Key rules in prompt:
1. Referenced rephrases must be ignored
2. System context (MCP metrics) is real-time
3. Files context (MCP file search) is real-time
4. Code blocks use `BEGIN-CODE<<<FILENAME>>>` / `END-CODE` format (NOT markdown fences)
5. If tools available, use them for ANY request
6. Tables must use HTML, not markdown pipe syntax
7. Responses must end with `END-RESPONSE`
8. In Multi-Turn, the LLM is an OPERATOR, not just an advisor
9. Up to 256 multi-turn iterations available
10. Identity: the LLM IS Tlamatini

---

## 25. Application Log (tlamatini.log)

`Tlamatini/manage.py` defines `_TeeStream` wrapper replacing `sys.stdout` and `sys.stderr` BEFORE Django initializes.

- **Source mode**: `Tlamatini/tlamatini.log`
- **Frozen mode**: next to executable
- Truncate-on-start (mode `'w'`)
- No rotation / no size cap
- Not a Django LOGGING handler — stream-level, picks up `print()` calls too

When asked to debug, `tlamatini.log` is the first artifact to consult.

---

## 26. How to Run

```bash
cd Tlamatini
python -m venv venv && venv\Scripts\activate
pip install -r requirements.txt
python Tlamatini/manage.py migrate
python Tlamatini/manage.py createsuperuser
python Tlamatini/manage.py runserver --noreload
# Visit http://127.0.0.1:8000/
```

Default credentials (installer builds): `user` / `changeme`

---

## 27. File Paths Quick Reference

| Purpose | Path |
|---------|------|
| Main config | `Tlamatini/agent/config.json` |
| System prompt | `Tlamatini/agent/prompt.pmt` |
| Core tools | `Tlamatini/agent/tools.py` |
| Unified agent / multi-turn executor | `Tlamatini/agent/mcp_agent.py` |
| Chat agent registry | `Tlamatini/agent/chat_agent_registry.py` |
| Global execution planner | `Tlamatini/agent/global_execution_planner.py` |
| Capability registry | `Tlamatini/agent/capability_registry.py` |
| WebSocket consumer | `Tlamatini/agent/consumers.py` |
| HTTP views | `Tlamatini/agent/views.py` |
| Response parser / exec report | `Tlamatini/agent/services/response_parser.py` |
| Answer analyzer | `Tlamatini/agent/services/answer_analizer.py` |
| RAG factory | `Tlamatini/agent/rag/factory.py` |
| RAG interface | `Tlamatini/agent/rag/interface.py` |
| Agent models | `Tlamatini/agent/models.py` |
| Global state | `Tlamatini/agent/global_state.py` |
| Path guard | `Tlamatini/agent/path_guard.py` |
| Build script | `build.py` |
| Installer builder | `build_installer.py` |
| Skill: create agent | `Tlamatini/.agents/workflows/create_new_agent.md` |
| Skill: create MCP | `Tlamatini/.mcps/create_new_mcp.md` |
| Agent boilerplate reference | `Tlamatini/agent/agents/shoter/shoter.py` |
| Parametrizer | `Tlamatini/agent/agents/parametrizer/parametrizer.py` |
| ACP CSS | `Tlamatini/agent/static/agent/css/agentic_control_panel.css` |
| Chat CSS (exec report) | `Tlamatini/agent/static/agent/css/agent_page.css` |
| ACP canvas core | `Tlamatini/agent/static/agent/js/acp-canvas-core.js` |
| ACP connectors | `Tlamatini/agent/static/agent/js/acp-agent-connectors.js` |
| ACP undo | `Tlamatini/agent/static/agent/js/acp-canvas-undo.js` |
| ACP file I/O | `Tlamatini/agent/static/agent/js/acp-file-io.js` |
| Chat message handler | `Tlamatini/agent/static/agent/js/agent_page_chat.js` |

---

*This KIMI.md was generated by deeply analyzing all documentation, source code, skills, and agents in the Tlamatini project. Keep it up-to-date when making architectural changes.*
