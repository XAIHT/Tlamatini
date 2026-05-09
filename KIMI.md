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
- **ACPX** — Agent Communication Protocol eXtension: spawn external coding-agent CLIs (Claude Code, Cursor, Codex, Gemini, Kimi, etc.) as child processes with permission gating, NDJSON transcripts, and skill invocation
- **Skills** — Markdown-driven, budgeted, auditable capability packages (`SKILL.md` frontmatter) with OpenClaw-compatible surface
- **Flow Compiler** — Contract-driven backend compiler that transforms ACP canvas graphs into deterministic, runnable agent pool directories
- Visual Agentic Workflow Designer (ACP) with **60+** drag-and-drop agent types
- Multi-model LLM support (Ollama local, Anthropic Claude cloud, Qwen vision)
- Full PyInstaller packaging pipeline (build.py → installer → standalone .exe)
- Real-time web interface via Django Channels/WebSocket

---

## 2. Architecture Overview

### The Five Layers (plus ACPX & Flow Compiler)

```
Layer 1: Persisted Toggles (Database)
  - Mcp model rows: UI toggles for MCP context providers
  - Tool model rows: UI toggles for unified-agent tools
  - Agent model rows: Agent type registry (sidebar list)
  - AcpAgent / Skill model rows: ACPX registry and skill catalog
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

Layer 6: ACPX Multi-Agent Orchestrator
  - AcpxRuntime singleton (agent/acpx/runtime.py)
  - Spawns external CLIs over stdin/stdout with transport-aware drain loops
  - 12 LangChain tools exposed to the LLM (spawn, send, kill, relay, transcript, etc.)
  - Skills harness (agent/skills/harness.py) with budget enforcement and audit logging
  - Gated by frontend ACPX checkbox; disabled by default

Layer 7: Flow Compiler (Backend)
  - AgentContract registry (agent/services/agent_contracts.py) defines every agent's connection semantics
  - FlowSpec normalizer (agent/services/flow_spec.py) ingests schema-v2 canvas JSON
  - FlowCompiler (agent/services/flow_compiler.py) generates runnable pool configs
  - Validation and execution now go through the compiler for consistency
```

### Request Flow

1. User sends message via WebSocket (optionally with `multi_turn_enabled`, `acpx_enabled`)
2. `AgentConsumer` receives and routes
3. Context determination (RAG loaded?)
4. Internet check (classify if web search needed)
5. Chain selection (RAG / Basic / Unified Agent)
6. Multi-Turn gate: checked = planner/dynamic binding; unchecked = legacy one-shot
7. ACPX gate: when checked, ACPX/Skill tools are added to planner surface; when unchecked, they are stripped
8. Context prefetch (system/file MCP)
9. Execution loop (tool calls, wrapped agent monitoring, ACPX session management)
10. Streaming response via WebSocket

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
| ACPX | Subprocess Popen, NDJSON transcripts, ThreadPoolExecutor |

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
│   ├── agents.md                   # Agent creation, 60-type catalog, FlowCreator, FlowHypervisor
│   ├── mcp-tools.md                # Creating a new MCP or tool
│   ├── frontend.md                 # Chat + ACP modules, Canvas DOM contract
│   ├── acpx.md                     # ACPX runtime, skills, transport modes, permissions
│   └── gotchas.md                  # Claude API client, build/lint, hardcoded assumptions, recent fixes
├── README.md                       # Full user-facing documentation (very large, 4000+ lines)
├── NEW_AGENT_RECOMMENDATIONS.md    # Roadmap for new agents (Tester, Reviewer, etc.)
├── ACPX.md                         # High-level ACPX concept and vision document
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
│   │   ├── settings.py             # Django settings (Channels, WhiteNoise, logging filters)
│   │   ├── urls.py                 # Root URL routing
│   │   ├── asgi.py                 # ASGI config with WebSocket routing
│   │   ├── middleware.py           # Custom middlewares
│   │   ├── context_processors.py   # Template context processors
│   │   └── logging_filters.py      # SuppressHttpGet200 filter
│   │
│   ├── agent/                      # Core Django app (ALL business logic)
│   │   ├── prompt.pmt              # System prompt template for chat LLM
│   │   ├── config.json             # LLM and RAG configuration
│   │   ├── config_loader.py        # Frozen/source-aware config reader
│   │   ├── views.py                # 103+ HTTP endpoints
│   │   ├── consumers.py            # WebSocket consumer (async chat handler)
│   │   ├── models.py               # 17 database models
│   │   ├── urls.py                 # URL routing
│   │   ├── tools.py                # LangChain @tool definitions and wrapped chat-agent launchers
│   │   ├── mcp_agent.py            # MCP unified agent builder and multi-turn executor
│   │   ├── global_execution_planner.py  # Request-scoped DAG planner
│   │   ├── capability_registry.py  # Request-scoped capability scoring
│   │   ├── chat_agent_registry.py  # Wrapped chat-agent tool registry
│   │   ├── chat_agent_runtime.py   # Wrapped-runtime lifecycle helpers
│   │   ├── global_state.py         # Thread-safe singleton (Singleton pattern)
│   │   ├── constants.py            # Application constants and regex patterns
│   │   ├── path_guard.py           # Path validation for dangerous operations
│   │   │
│   │   ├── acpx/                   # ACPX runtime package
│   │   │   ├── __init__.py         # Public exports, ACPX_TOOL_NAMES, filter_acpx_tools
│   │   │   ├── config.py           # AcpxConfig, load_acpx_config(), backfill helper
│   │   │   ├── agent_registry.py   # DEFAULT_ACP_AGENTS (14 specs), AcpAgentSpec
│   │   │   ├── runtime.py          # AcpxRuntime, AcpSession, drain loop
│   │   │   ├── session_store.py    # FileSessionStore, transcript persistence
│   │   │   ├── permissions.py      # PermissionGate (approve-reads / approve-all / deny-all)
│   │   │   ├── windows_spawn.py    # Windows command resolution
│   │   │   ├── tools.py            # 12 LangChain @tool functions for ACPX
│   │   │   ├── service.py          # boot_acpx(), boot_skills() — Django startup hooks
│   │   │   └── tests.py            # ~60 unit tests
│   │   │
│   │   ├── skills/                 # Skills runtime package
│   │   │   ├── frontmatter.py      # YAML frontmatter + markdown body parser
│   │   │   ├── registry.py         # SkillRegistry — filesystem discovery of skills_pkg/
│   │   │   ├── io_contract.py      # Input/output validation with type coercion
│   │   │   └── harness.py          # SkillHarness — budget enforcement, audit logging, dispatch
│   │   │
│   │   ├── skills_pkg/             # Skill content packages (22+ SKILL.md files)
│   │   │   ├── hello_world/
│   │   │   ├── acp_router/
│   │   │   ├── github/
│   │   │   ├── gmail/
│   │   │   ├── jira/
│   │   │   ├── slack/
│   │   │   ├── notion/
│   │   │   ├── summarize/
│   │   │   ├── weather/
│   │   │   ├── skill_creator/
│   │   │   └── tlamatini_*/        # Internal Tlamatini skills
│   │   │
│   │   ├── rag/                    # RAG system package
│   │   │   ├── factory.py          # Chain builders, MCP context patching, ACPX filter
│   │   │   ├── interface.py        # Public API (ask_rag), acpx_enabled extraction
│   │   │   ├── chains/             # basic.py, history_aware.py, unified.py
│   │   │   └── ...
│   │   │
│   │   ├── agents/                 # 60+ workflow agent templates
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
│   │   │   ├── pser/               # Process finder (fuzzy/semantic name matching)
│   │   │   ├── prompter/           # LLM prompt execution
│   │   │   ├── summarizer/         # Log monitoring + one-shot text summarization
│   │   │   ├── crawler/            # Developer-oriented web crawler
│   │   │   ├── googler/            # Google search (Playwright + text extraction)
│   │   │   ├── file_creator/       # File creation utility
│   │   │   ├── file_extractor/     # File text extraction
│   │   │   ├── file_interpreter/   # Document parsing and text/image extraction
│   │   │   ├── image_interpreter/  # LLM vision-based image analysis
│   │   │   ├── j_decompiler/       # Java artifact decompiler (jd-cli)
│   │   │   ├── shoter/             # Screenshot capture (silent, structured output)
│   │   │   ├── mouser/             # Mouse pointer movement (7 movement types)
│   │   │   ├── keyboarder/         # Keyboard typing / hotkey automation (robust parser)
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
│   │   │   ├── asker/              # Interactive A/B path chooser (chat + canvas)
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
│   │   │   ├── kyber_decipher/     # CRYSTALS-Kyber decryption
│   │   │   ├── acpxer/             # ACPX session driver for external CLIs
│   │   │   ├── teletlamatini/      # Telegram bot bridge to Tlamatini chat
│   │   │   └── whatstlamatini/     # WhatsApp Cloud API bridge to Tlamatini chat
│   │   │
│   │   ├── services/               # Backend services
│   │   │   ├── response_parser.py  # Exec report HTML renderer, message processing
│   │   │   ├── answer_analizer.py  # SUCCESS/FAILURE classification
│   │   │   ├── flow_compiler.py    # Compile FlowSpec into runnable pool configs
│   │   │   ├── agent_contracts.py  # AgentContract registry and redaction
│   │   │   ├── agent_paths.py      # Filesystem/naming utilities for agent pools
│   │   │   ├── flow_spec.py        # FlowSpec schema-v2 normalizer
│   │   │   └── test_flow_contracts.py  # Flow compiler + contract tests
│   │   │
│   │   ├── templates/agent/        # HTML templates
│   │   ├── static/agent/           # Frontend assets
│   │   │   ├── js/                 # 26+ JS modules (8 chat + 14 ACP + 4 shared)
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
- **ACPX block** (auto-backfilled on upgrade):
  - `permissionMode`: `"approve-reads"` or `"approve-all"` or `"deny-all"`
  - `nonInteractivePermissions`: `"deny"` or `"fail"`
  - `timeoutSeconds`: 120
  - `pluginToolsMcpBridge`: false
  - Per-agent overrides under `agents.{agent_id}` for command, transport, budgets

---

## 5. Database Models (17 models in agent/models.py)

Key models:
- `AgentMessage` - Chat messages (user, conversation_user, message, timestamp)
- `LLMProgram` / `LLMSnippet` - Saved code/program content
- `Prompt` / `Omission` - Prompt templates and file omission patterns
- `ContextCache` - SHA1-hashed query to context blob caching
- `Mcp` - MCP UI toggle rows (idMcp, mcpName, mcpDescription, mcpContent)
- `Tool` - Tool UI toggle rows (idTool, toolName, toolDescription, toolContent)
- `Agent` - Agent type registry (idAgent, agentName, agentDescription, agentContent)
- `AgentProcess` - Tracked running agent processes (PID)
- `ChatAgentRun` - Wrapped chat-agent run records (runId, status, pid, etc.)
- `Asset` - Generic asset storage
- `SessionState` - Persists user session state across reconnections (24h expiry)
- `AcpAgent` - ACPX agent registry rows (mirrored from DEFAULT_ACP_AGENTS on boot)
- `Skill` - Skill catalog rows (mirrored from skills_pkg/ on boot)
- `AcpSession` - Persisted ACPX session metadata
- `SkillInvocation` - Individual skill invocation records

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
- `unified.py`: Tool-enabled agent chains (LangGraph) with `_invoke_unified_agent_with_retry` — exponential backoff (0.5s, 1s, 2s) for transient 502/503/504/socket errors. When fallback to basic LLM occurs and multi-turn was requested, a visible system notice is prepended so the user knows tools were not executed.

`factory.py` builds chains and monkey-patches `invoke()` to inject MCP context from sidecars. Now also filters ACPX tools via `filter_acpx_tools()` when `acpx_enabled` is false.

`interface.py` extracts `acpx_enabled` from requests. Both **multi-turn** and **ACPX** now bypass the `is_valid_prompt` shape validator and the access-validation security gate, because agentic flows need free-form prompts.

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
8. Frontend renders "Create Flow" button on SUCCESS, converts tool-call log into downloadable `.flw`

### When Multi-Turn is UNCHECKED:
- Legacy one-shot behavior preserved exactly
- Legacy prompt validation, legacy MCP context prefetch, full-tool binding, visible-console launch

### ACPX Gating
- `CapabilityAwareToolAgentExecutor` accepts `acpx_enabled` from payload
- When **disabled** (default), `filter_acpx_tools` strips all 12 ACPX/Skill tools from the LLM-facing surface before planning or capability selection
- When **enabled**, ACPX tools are added to planner surface and co-selection rules apply (e.g., `acp_spawn` auto-co-selects `acp_doctor` + `acp_kill`)

### Global Execution Planner (`global_execution_planner.py`)
- Builds DAG with nodes: `prefetch` to `execute` to `monitor` to `answer`
- `CapabilityRegistry` (`capability_registry.py`) scores tools/capabilities against request text
- Short follow-up scoring: 4 or fewer meaningful tokens boosts scores from last 4 chat messages (+15 max)
- Planner threshold = 6 if contexts selected, else 2
- Run-control tools (list/status/log/stop/wait/present) auto-injected when wrapped agents selected
- ACPX co-selection rules in `capability_registry.py`: selecting `acp_spawn` also selects `acp_doctor` and `acp_kill`

### MultiTurnToolAgentExecutor (`mcp_agent.py`)
- Explicit multi-turn tool loop (not opaque AgentExecutor)
- Max iterations: 256 (configurable)
- **Tool quota caps**: `_TOOL_QUOTA_SOFT_WARN` = 64, `_TOOL_QUOTA_HARD_STOP` = 256. Polling/management tools exempt. Soft cap injects planner hint nudging LLM toward specialized alternative. Hard cap short-circuits with forced final answer.
- **Repetition detection fixes**: Exempted polling/management tools from call-signature fingerprint so legitimate `run_status` loops do not trip the repetition breaker. Empty signatures reset the repeat counter.
- **Exec report enrichment**: Specialized formatters for ACPX tools and skill invocations
- Wrapped agent dedup: hashes `tool_name + sorted-JSON args` into `_wrapped_agent_signatures`
- Empty final response nudge: asks model to summarize tool results

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
- `window_present(title)` — Fast (under 100 ms) yes/no window probe via PyAutoGUI
- `chat_agent_run_wait(run_id, max_seconds, poll_interval_seconds)` — Blocking wait for a wrapped chat-agent run

**ACPX Tools** (defined in `agent/acpx/tools.py`, 12 tools):
- `acp_doctor` — Health check / enumerate available ACP agents
- `acp_spawn(agent_id, task, ...)` — Spawn external CLI session
- `acp_send(session_id, text)` — Send follow-up to existing session
- `acp_send_and_wait(session_id, text)` — Send and drain until completion
- `acp_kill(session_id)` — Terminate session
- `acp_transcript(session_id)` — Read NDJSON transcript
- `acp_session_status(session_id)` — Get session status
- `acp_list_sessions` — List active sessions
- `acp_relay(source_session_id, destination_session_id)` — Hand off transcript content
- `list_acp_agents` — List registered ACP agents
- `list_skills` — List available skills
- `invoke_skill(name, inputs)` — Execute a skill via harness

**Wrapped Chat-Agent Tools** (registered in `agent/chat_agent_registry.py`):
36 specs in `WRAPPED_CHAT_AGENT_SPECS`. Key ones:
- `chat_agent_executer`, `chat_agent_pythonxer`, `chat_agent_dockerer`, `chat_agent_kuberneter`
- `chat_agent_ssher`, `chat_agent_scper`, `chat_agent_gitter`
- `chat_agent_sqler`, `chat_agent_mongoxer`, `chat_agent_apirer`
- `chat_agent_send_email`, `chat_agent_telegramer`, `chat_agent_whatsapper`
- `chat_agent_notifier`, `chat_agent_shoter`, `chat_agent_mouser`, `chat_agent_keyboarder`
- `chat_agent_file_creator`, `chat_agent_move_file`, `chat_agent_deleter`
- `chat_agent_file_extractor`, `chat_agent_file_interpreter`, `chat_agent_image_interpreter`
- `chat_agent_summarize_text`, `chat_agent_prompter`, `chat_agent_crawler`
- `chat_agent_pser` (process finder), `chat_agent_jenkinser`
- `chat_agent_monitor_log`, `chat_agent_monitor_netstat` (long-running)
- `chat_agent_kyber_keygen`, `chat_agent_kyber_cipher`, `chat_agent_kyber_deciph`
- `chat_agent_run_list`, `chat_agent_run_status`, `chat_agent_run_log`, `chat_agent_run_stop` (management)
- `chat_agent_run_wait` (blocking wait)
- `chat_agent_sleeper` (delay helper)
- `chat_agent_asker` (interactive A/B choice)

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

**ACPX is NOT an MCP service** — it is a separate child-process orchestrator with its own runtime, registry, and tool surface.

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

## 10. ACPX System

**ACPX = Agent Communication Protocol eXtension.** Tlamatini's runtime for spawning external coding-agent CLIs as child processes.

### Transport Modes

| Transport | Agents | Mechanism | Default Budgets (timeout/idle/grace) |
|---|---|---|---|
| `oneshot-prompt` | claude, cursor, gemini, qwen, codex | Re-spawns CLI per turn with prompt as CLI arg, captures stdout/stderr to EOF | 180 s / 10 s / 2 s |
| `json-acp` | tlamatini (self-host) | Strict JSON envelope on stdin; drain until `"done": true` | 45 s / 6 s / 12 s |
| `tui-repl` | kiro, kimi, iflow, kilocode, opencode, pi, droid, copilot | Long-lived REPL over stdin/stdout. Daemon reader thread pumps stdout into queue. | 8 s / 2 s / 3 s |
| `one-shot` | (configurable) | Single task per process; stdin closes after first write | — |

The **`oneshot-prompt` transport is the critical Windows fix**: TUI CLIs detect piped stdout and refuse to flush when run as a long-lived child. By re-spawning per turn with a non-interactive flag, the runtime actually captures the answer.

### Session Lifecycle
1. **Boot** — `service.boot_acpx()` on daemon thread at Django startup: constructs `AcpxRuntime`, probes health, syncs `AcpAgent` DB rows, backfills `config.json`
2. **Spawn** — `acp_spawn()` resolves command via `windows_spawn.py`, creates `FileSessionStore` record, spawns `subprocess.Popen`
3. **Drain Loop** — Daemon reader thread pumps stdout into `queue.Queue`. Checks: JSON `"done": true`, stdout closed, hard timeout, transport-aware idle rule
4. **Kill** — `acp_kill()` terminates child (`terminate` to 3s grace to `kill`), marks record `closed=True`
5. **Transcript** — NDJSON lines with `direction`, `text`/`raw`, `ts` at `<state_dir>/<session_id>.transcript.ndjson`

### Permission Model
`PermissionGate` enforces three modes:
- **`approve-reads`** (default) — reads auto-approved; writes/shell/network need interactive prompt. Unattended non-interactive policy: `deny` = deny and continue; `fail` = hard fail
- **`approve-all`** — flagged dangerous; auto-approves everything
- **`deny-all`** — hard wall; `acp_spawn` raises `PERMISSION_DENIED`

### Skills
Skills are **markdown-driven capability packages** defined by a `SKILL.md` file with YAML frontmatter + markdown body.

Frontmatter contract:
```yaml
---
name: skill-name
description: One-line description.
metadata:
  tlamatini:
    runtime: in-process          # or acpx
    acpx_agent: claude           # required when runtime=acpx
    requires_tools: [...]
    requires_mcps:  [...]
    budget: { max_iterations: 12, max_seconds: 180, max_tokens: 30000 }
    permissions: { filesystem: {...}, shell: [...], network: deny, db: deny }
    inputs:  [{ name: x, type: string, required: true }]
    outputs: [{ name: y, type: string, required: true }]
    triggers: { keywords: [...], file_globs: [...] }
---
```

**Harness execution** (`invoke_skill`):
1. Registry lookup (auto-reloads if stale over 30s)
2. Input validation with type coercion
3. Audit open to `~/.tlamatini/skill-audit/<YYYY-MM>/...ndjson`
4. Dispatch: `in-process` = plan envelope; `acpx` = spawn child agent
5. Output validation
6. Return JSON envelope with `skill`, `output`, `iterations_used`, `tokens_used`, `elapsed_seconds`, `audit_id`

---

## 11. Agentic Workflow Designer (ACP)

Visual drag-and-drop workflow designer at `/agentic_control_panel/`.

### Frontend Modules (26+ JS files):
**Chat Interface (8)**:
- `agent_page_init.js` — WebSocket setup, app initialization
- `agent_page_chat.js` — Chat message handling, Flow-Generator mapping
- `agent_page_canvas.js` — Code canvas rendering
- `agent_page_context.js` — RAG context management
- `agent_page_dialogs.js` — Modal dialogs
- `agent_page_layout.js` — UI layout
- `agent_page_state.js` — Client state (ACPX toggle state)
- `agent_page_ui.js` — General UI utilities

**ACP Workflow Designer (14)**:
- `agentic_control_panel.js` — Entry point
- `acp-globals.js` — Shared global state, `updateCanvasContentSize()`
- `acp-canvas-core.js` — Canvas rendering, drag-and-drop, classMap, connection handlers (6 touch points per agent)
- `acp-canvas-undo.js` — Undo/redo state (1024 actions)
- `acp-agent-connectors.js` — 60+ agent connection handlers
- `acp-control-buttons.js` — Start/stop/pause/hypervisor; now calls `compileCurrentACPFlow({ mode: 'write' })` before start
- `acp-file-io.js` — .flw save/load; uses `buildACPFlowSnapshot()` for schema-v2 JSON
- `acp-running-state.js` — LED indicators, process monitoring
- `acp-session.js` — Session pool management
- `acp-layout.js` — Canvas layout utilities
- `acp-validate.js` — Flow validation engine; now calls `compileCurrentACPFlow({ mode: 'dry_run' })` first
- `acp-flow-snapshot.js` — DOM walker that builds schema-v2 JSON with `parametrizerMappings` artifact
- `acp-parametrizer-dialog.js` — Parametrizer mapping UI
- `chat_page_runtime_poller.js` — Chat runtime status polling

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
| CSS classMap key | lowercase, spaces to hyphens | `node-manager` | `shoter` |
| Sidebar visual | Same as classMap via `getAgentTypeClass()` | `node-manager` | `shoter` |
| Connection handlers | lowercase (preserves spaces) | `node manager` | `shoter` |

**For multi-word agents**, the forms DIFFER:
- classMap key and sidebar visual resolver use **hyphens**: `node-manager`
- Connection handlers use **spaces**: `node manager`

### CSS Gradient Rule
Every agent MUST have a **4-color gradient** (0%, 33%, 66%, 100%) in `agentic_control_panel.css`. The sidebar icon inherits this automatically through `applyAgentToolIconStyle()` — NEVER duplicate gradient strings in `populateAgentsList()`.

---

## 12. All 60+ Workflow Agent Types

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
- **Asker** — Interactive A/B choice for user (dialog popup or chat inline)
- **Counter** — Persistent counter, routes L (< threshold) or G (>= threshold)

### Logic Gates
- **OR** — Fires when EITHER of 2 sources completes
- **AND** — Fires when BOTH of 2 sources complete
- **Barrier** — Fires when ALL N sources complete (generalized AND)

### Action Agents
- **Executer** — Shell commands
- **Pythonxer** — Inline Python (exit code gating, Ruff validation)
- **Prompter** — LLM prompt execution
- **Summarizer** — Log monitoring + one-shot text summarization
- **Crawler** — Developer-oriented web crawler with LLM analysis
- **Googler** — Google search + text extraction (Playwright, MUST run in ThreadPoolExecutor)
- **Apirer** — HTTP REST API calls
- **Gitter** — Git operations
- **Ssher** — SSH remote commands
- **Scper** — SCP file transfer
- **Dockerer** — Docker container management
- **Kuberneter** — Kubernetes command executor
- **Pser** — Process finder (fuzzy/semantic name matching)
- **Jenkinser** — CI/CD pipeline trigger
- **Sqler** — SQL Server query execution (external window)
- **Mongoxer** — MongoDB script execution (external window)
- **Mover** — File move/copy with glob patterns
- **Deleter** — File deletion with glob patterns
- **Shoter** — Screenshot capture (silent, structured output)
- **Mouser** — Mouse pointer movement (7 movement types)
- **Keyboarder** — Keyboard typing / hotkey automation (robust parser)
- **File-Creator** — Creates files with specified content
- **File-Interpreter** — Document parsing and text/image extraction
- **File-Extractor** — Raw text extraction (PDF, DOCX, etc.)
- **Image-Interpreter** — LLM vision-based image analysis
- **J-Decompiler** — JAR/WAR decompilation (bundled jd-cli)
- **Telegramer** — Telegram message sender
- **ACPXer** — ACPX session driver for external CLIs
- **Teletlamatini** — Telegram bot bridge to Tlamatini chat
- **WhatsTlamatini** — WhatsApp Cloud API bridge to Tlamatini chat

### Cryptography Agents
- **Kyber-KeyGen** — CRYSTALS-Kyber key pair generation (post-quantum)
- **Kyber-Cipher** — CRYSTALS-Kyber encryption
- **Kyber-DeCipher** — CRYSTALS-Kyber decryption

### Utility Agents
- **Parametrizer** — Maps structured output from one agent into another's config.yaml (strict single-lane queue)
- **FlowBacker** — Session backup and cleanup handoff
- **Gatewayer** — HTTP webhook / folder-drop ingress
- **Gateway-Relayer** — Bridges provider webhooks into Gatewayer
- **Node-Manager** — Infrastructure registry and node supervision
- **FlowCreator** — AI-powered flow designer
- **FlowHypervisor** — System-managed LLM anomaly detector

### Terminal/Monitoring Agents (do NOT start downstream)
- **Monitor-Log** — LLM-powered log file monitor
- **Monitor-Netstat** — LLM-powered network port monitor
- **Emailer** — SMTP email sender on pattern detection
- **RecMailer** — IMAP email receiver/monitor
- **Notifier** — Desktop notification + sound
- **Whatsapper** — WhatsApp notifications (TextMeBot)
- **TelegramRX** — Telegram message receiver

---

## 13. Agent Creation System

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
6. Reanimation support: `_IS_REANIMATED` before `logging.basicConfig(...)`, marker log in `main()`
7. If agent polls source logs: implement `reanim*.pos` offset persistence
8. Validate dangerous paths with `path_guard.validate_tool_path()` when applicable

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

## 14. Parametrizer & Interconnection

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

## 15. Exec Report

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

### ACPX & Skill Exec Report Enrichment
`mcp_agent.py` contains specialized formatters for ACPX tools (`acp_spawn`, `acp_send`, etc.) and skill invocations (`invoke_skill`). These emit enriched `agent_key` / `Display Name` pairs so ACPX sessions and skill calls appear in the exec report alongside traditional wrapped agents.

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

Skip for read-only/monitoring agents (Crawler, Googler, Prompter, Summarizer, File-Interpreter/Extractor, Image-Interpreter, Shoter, Monitor-*, Recmailer, FlowHypervisor, ACPXer in relay mode).

---

## 16. Create Flow from Multi-Turn

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

## 17. Frontend Architecture Details

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
- Chat payload now includes `acpx_enabled` boolean alongside `multi_turn_enabled` and `exec_report_enabled`

### WebSocket Message Types (Server → Client)
- `agent_message` — main chat message
- `mcp` / `tool` / `agent` — establishment messages
- `heartbeat` — keepalive every 20s
- `session-restored`
- `context-path-set`

### ACPX Toggle State
`agent_page_state.js` manages `ACPX_STORAGE_KEY = 'acpxEnabled'` in `localStorage`. The checkbox `acpxCheckbox` (`#acpx-enabled`) is read on every WebSocket send and its state is persisted across page reloads. Same pattern as Multi-Turn and Exec Report toggles.

---

## 18. Build & Packaging

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

## 19. Skills Available in Project

### `Tlamatini/.agents/workflows/create_new_agent.md`
Complete 8-step guide for creating workflow agents. Covers: backend script + config, Django view + URL, DB migration, CSS gradient, JS integration (4 files), FlowCreator skill update, README updates, linting.

### `Tlamatini/.mcps/create_new_mcp.md`
Guide for adding MCP-backed capabilities or tools. Emphasizes classifying requests into: Tool only / Wrapped chat-agent tool / MCP context provider only / Both. Contains detailed file-scope matrices and self-check checklists.

### `Tlamatini/agent/agents/flowcreator/agentic_skill.md`
Reference for FlowCreator AI to design flows. Key principles: minimize agents, sequential chains, lean Starter, terminal agents at END.

### `Tlamatini/agent/skills_pkg/skill_creator/SKILL.md`
Guide for creating new skills: YAML frontmatter contract, input/output validation, budget enforcement, and OpenClaw-compatible surface.

### External Skills (in `.codex/skills/`)
- `full-project-pdf-dossier/SKILL.md` — Complete project PDF dossier generation
- `overlap-safe-pptx-dossier/SKILL.md` — Technical PPTX deck creation (Tlamatini-style)

---

## 20. Coding Conventions & Critical Rules

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

## 21. Common Pitfalls

1. **Naming drift** — `agentDescription` transforms differently in CSS classMap, sidebar, and connection handlers
2. **Empty-string overwrites** — backend deep-merges posted JSON over template config.yaml. Use "omit if empty" semantics
3. **Pool-name cardinal mismatch** — pool folders are `<base>_<N>` (e.g., `executer_2`). Never emit bare `"executer"` into `target_agents`
4. **Forgetting `_IS_REANIMATED`** — add marker BEFORE `logging.basicConfig(...)`
5. **Concurrency guard** — `wait_for_agents_to_stop(target_agents)` before `start_agent()` loop
6. **`_EXEC_REPORT_TOOLS` miss** — state-changing agents must be registered or they won't appear in Exec Report
7. **Flow-Generator `_mapToolArgsToAgentConfig` miss** — without it, generated `.flw` nodes have no config fields set
8. **Forgetting the 6 JS edit locations** in `acp-canvas-core.js`
9. **CSS gradient duplicated in JS** — never hard-code gradient in `populateAgentsList()`
10. **ACPX transport mismatch on Windows** — TUI CLIs (Kimi, Kiro, etc.) detect piped stdout and refuse to flush in long-lived REPL mode. Use `oneshot-prompt` transport for these agents.
11. **Skill frontmatter missing `tlamatini` block** — without it, the harness cannot validate inputs, enforce budgets, or dispatch correctly.
12. **ACPX permission mode surprise** — default is `approve-reads`; writes/shell/network in non-interactive mode will be denied or failed silently depending on `nonInteractivePermissions`.

---

## 22. Known Hardcoded Assumptions

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
16. `DEFAULT_ACP_AGENTS` in `agent_registry.py` is hardcoded (14 specs). New ACP agents require a code change and DB sync on boot.
17. `oneshot-prompt` transport is the **only** reliable Windows capture mode for TUI CLIs.
18. Skill registry auto-reloads only if stale > 30s. Rapid skill iteration requires restarting Django or waiting.

---

## 23. Recent Fixes to Remember

- **Planner statelessness on short follow-ups** — Solved by passing `chat_history_text` into planner. Preserve this argument.
- **Wrapped chat-agent dedup** — `_wrapped_agent_signatures` set in `MultiTurnToolAgentExecutor`. Do not remove.
- **Googler Playwright + async loop** — Must wrap in `ThreadPoolExecutor(max_workers=1)`. Any new sync-Playwright tool must do the same.
- **Cancel/rebuild race** — `consumers.py` now `await`s `setup_rag_chain()` during cancel. Must not use `asyncio.create_task(...)`.
- **Exec-report persistence ordering** — `save_message()` must run AFTER exec-report HTML append in `process_llm_response()`.
- **ACP canvas DOM split** — `#canvas-content` vs `#submonitor-container`. All coordinate math uses `canvasContent.getBoundingClientRect()`.
- **ACPX oneshot-prompt transport** — Critical Windows fix. TUI CLIs (Kimi, Kiro, etc.) now re-spawn per turn with prompt as CLI arg instead of long-lived REPL.
- **ACPX gating** — `filter_acpx_tools()` strips all 12 ACPX/Skill tools when `acpx_enabled=false`. Do not bypass this gate.
- **Repetition detection exemptions** — Polling/management tools (`run_status`, `run_log`, `session_status`, `list_sessions`, etc.) are exempt from call-signature fingerprinting so legitimate wait loops don't trip the repetition breaker.
- **Tool quota caps** — Soft warn at 64 calls, hard stop at 256. Polling/management tools exempt from both caps.

---

## 24. Roadmap: Recommended New Agents

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

## 25. System Prompt & LLM Identity

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
11. In ACPX mode, the LLM may spawn external child agents; it must respect permission gates and budget limits

---

## 26. Application Log (tlamatini.log)

`Tlamatini/manage.py` defines `_TeeStream` wrapper replacing `sys.stdout` and `sys.stderr` BEFORE Django initializes.

- **Source mode**: `Tlamatini/tlamatini.log`
- **Frozen mode**: next to executable
- Truncate-on-start (mode `'w'`)
- No rotation / no size cap
- Not a Django LOGGING handler — stream-level, picks up `print()` calls too

When asked to debug, `tlamatini.log` is the first artifact to consult.

---

## 27. How to Run

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

## 28. File Paths Quick Reference

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
| Flow compiler | `Tlamatini/agent/services/flow_compiler.py` |
| Flow spec normalizer | `Tlamatini/agent/services/flow_spec.py` |
| Agent contracts | `Tlamatini/agent/services/agent_contracts.py` |
| RAG factory | `Tlamatini/agent/rag/factory.py` |
| RAG interface | `Tlamatini/agent/rag/interface.py` |
| Agent models | `Tlamatini/agent/models.py` |
| Global state | `Tlamatini/agent/global_state.py` |
| Path guard | `Tlamatini/agent/path_guard.py` |
| ACPX runtime | `Tlamatini/agent/acpx/runtime.py` |
| ACPX tools | `Tlamatini/agent/acpx/tools.py` |
| ACPX config | `Tlamatini/agent/acpx/config.py` |
| ACPX registry | `Tlamatini/agent/acpx/agent_registry.py` |
| ACPX permissions | `Tlamatini/agent/acpx/permissions.py` |
| Skills harness | `Tlamatini/agent/skills/harness.py` |
| Skills registry | `Tlamatini/agent/skills/registry.py` |
| Build script | `build.py` |
| Installer builder | `build_installer.py` |
| Skill: create agent | `Tlamatini/.agents/workflows/create_new_agent.md` |
| Skill: create MCP | `Tlamatini/.mcps/create_new_mcp.md` |
| Skill: create skill | `Tlamatini/agent/skills_pkg/skill_creator/SKILL.md` |
| Agent boilerplate reference | `Tlamatini/agent/agents/shoter/shoter.py` |
| Parametrizer | `Tlamatini/agent/agents/parametrizer/parametrizer.py` |
| ACP CSS | `Tlamatini/agent/static/agent/css/agentic_control_panel.css` |
| Chat CSS (exec report) | `Tlamatini/agent/static/agent/css/agent_page.css` |
| ACP canvas core | `Tlamatini/agent/static/agent/js/acp-canvas-core.js` |
| ACP connectors | `Tlamatini/agent/static/agent/js/acp-agent-connectors.js` |
| ACP undo | `Tlamatini/agent/static/agent/js/acp-canvas-undo.js` |
| ACP file I/O | `Tlamatini/agent/static/agent/js/acp-file-io.js` |
| ACP flow snapshot | `Tlamatini/agent/static/agent/js/acp-flow-snapshot.js` |
| ACP parametrizer dialog | `Tlamatini/agent/static/agent/js/acp-parametrizer-dialog.js` |
| Chat message handler | `Tlamatini/agent/static/agent/js/agent_page_chat.js` |
| Chat state (ACPX toggle) | `Tlamatini/agent/static/agent/js/agent_page_state.js` |

---

*This KIMI.md was generated by deeply analyzing all documentation, source code, skills, and agents in the Tlamatini project. Keep it up-to-date when making architectural changes.*
