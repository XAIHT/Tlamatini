<!--
═══════════════════════════════════════════════════════════════════
  ✦  T L A M A T I N I  ✦   —   "one who knows"
  Created by  Angela López Mendoza   ·   @angelahack1
  Developer · Architect · Creator of Tlamatini
  Tlamatini Author Banner — do not remove (Angela's name is kept in every build)
═══════════════════════════════════════════════════════════════════
-->
# KIMI.md — Complete Tlamatini System Knowledge Base

> **Purpose**: This file contains exhaustive, structured knowledge of the Tlamatini project so that Kimi (or any AI assistant) can load it in future sessions and immediately possess complete context for development, debugging, and feature creation.

---

## 1. Project Identity

**Name**: Tlamatini (Nahuatl for "one who knows")
**Repository**: `https://github.com/XAIHT/Tlamatini.git`
**License**: MIT
**Primary Developer**: angelahack1
**Platform**: Windows 11 (primary), with cross-platform Python support
**Language**: Python 3.12+ (only fully tested version)

**What it is**: A locally-deployed AI developer assistant built with Django, featuring:
- Advanced RAG system (FAISS + BM25 hybrid, metadata extraction, context budgeting, fallback mode)
- Request-scoped Multi-Turn orchestration with dynamic tool binding and global execution planning
- **Ask Execs** — optional human-in-the-loop gate that BLOCKS before every Multi-Turn tool execution on a browser Proceed/Deny prompt (bridged by `agent/exec_permission.py`); Deny halts the chain and shows a red "Execution interrupted" banner
- **ACPX** — Agent Communication Protocol eXtension: spawn external coding-agent CLIs (Claude Code, Cursor, Codex, Gemini, Kimi, etc.) as child processes with permission gating, NDJSON transcripts, and skill invocation
- **External MCPs** — a config-driven **universal MCP client** (`agent/external_mcp_manager.py`, catalog `agent/external_mcps.json`) that connects to ANY external MCP server declared in a `.mcp.json`-style JSON file over FOUR transports (`stdio` local command / `streamable-http` / legacy `sse` / `websocket`), binds the remote tools to the LLM as `ext__<server>__<tool>`, and exposes eight LLM supervisor tools. Bulletproof: connects run OFF the chat path, a bad/unreachable/unsupported server is catalogued-with-reason (never crashes or hangs), ≤5 active at once. **Distinct** from the two built-in `Mcp`-model context providers (System-Metrics / Files-Search), from ACPX, and from the per-agent inline MCP clients (STM32er / Kalier). See Section 9b
- **Skills** — Markdown-driven, budgeted, auditable capability packages (`SKILL.md` frontmatter) with OpenClaw-compatible surface
- **Flow Compiler** — Contract-driven backend compiler that transforms ACP canvas graphs into deterministic, runnable agent pool directories
- Visual Agentic Workflow Designer (ACP) with **82** drag-and-drop agent types (incl. ESPHomer, MCP Doctor, and Instant Messaging Doctor)
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

1. User sends message via WebSocket (optionally with `multi_turn_enabled`, `acpx_enabled`, `exec_report_enabled`, `ask_execs_enabled`)
2. `AgentConsumer` receives and routes
3. Context determination (RAG loaded?)
4. Internet check (classify if web search needed)
5. Chain selection (RAG / Basic / Unified Agent)
6. Multi-Turn gate: checked = planner/dynamic binding; unchecked = legacy one-shot
7. ACPX gate: when checked, ACPX/Skill tools are added to planner surface; when unchecked, they are stripped
7b. Ask-Execs gate (Multi-Turn-only): when `ask_execs_enabled`, the executor BLOCKS before every state-changing tool on a browser Proceed/Deny prompt (`agent/exec_permission.py::ExecPermissionBroker`); Deny halts the chain and appends a red "Execution interrupted" banner
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
│   ├── agents.md                   # Agent creation, 78-type catalog, FlowCreator, FlowHypervisor
│   ├── mcp-tools.md                # Creating a new MCP or tool
│   ├── frontend.md                 # Chat + ACP modules, Canvas DOM contract
│   ├── acpx.md                     # ACPX runtime, skills, transport modes, permissions
│   ├── gotchas.md                  # Claude API client, build/lint, versioning, hardcoded assumptions, roadmap, work-style
│   └── recent-fixes.md             # ** NOT auto-imported ** — dated "do NOT revert" fix log; consult before touching the named subsystems
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
│   │   ├── exec_permission.py      # Ask-Execs permission broker (sync executor ↔ async consumer; blocking Proceed/Deny)
│   │   ├── external_mcp_manager.py  # Universal external-MCP client (4 transports, ≤5 active, lazy connect, 8 LLM supervisor tools)
│   │   ├── external_mcps.json       # Catalog of importable external MCP servers (mcpServers shape; resolved next to config.json)
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
│   │   ├── skills_pkg/             # Skill content packages (27 SKILL.md files)
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
│   │   │   ├── flow_making/        # objective → .flw (wraps FlowCreator); ships scripts/{make_flow,result_to_flw}.py
│   │   │   └── tlamatini_*/        # Internal Tlamatini skills (incl. flow_from_objective → delegates to flow-making)
│   │   │
│   │   ├── rag/                    # RAG system package
│   │   │   ├── factory.py          # Chain builders, MCP context patching, ACPX filter
│   │   │   ├── interface.py        # Public API (ask_rag), acpx_enabled extraction
│   │   │   ├── chains/             # basic.py, history_aware.py, unified.py
│   │   │   └── ...
│   │   │
│   │   ├── agents/                 # 82 workflow agent templates
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
│   │   │   ├── whatsapper/         # WhatsApp send/receive via official Meta Cloud API
│   │   │   ├── telegrammer/        # Telegram send/receive via official Telegram surfaces
│   │   │   ├── notifier/           # Desktop notification + sound
│   │   │   ├── monitor_log/        # LLM-powered log file monitor
│   │   │   ├── monitor_netstat/    # LLM-powered network port monitor
│   │   │   ├── kyber_keygen/       # CRYSTALS-Kyber key pair generation
│   │   │   ├── kyber_cipher/       # CRYSTALS-Kyber encryption
│   │   │   ├── kyber_decipher/     # CRYSTALS-Kyber decryption
│   │   │   ├── acpxer/             # ACPX session driver for external CLIs
│   │   │   ├── teletlamatini/      # Telegram bot bridge to Tlamatini chat
│   │   │   ├── windower/           # Win32 window manager (focus/move/resize/tile/close)
│   │   │   ├── kalier/             # Kali Linux offensive-security bridge (MCP-Kali-Server)
│   │   │   ├── discoverer/         # ProjectDiscovery recon suite (subfinder/httpx/naabu/katana/nuclei/cvemap) — direct CLIs, self-installing private Go toolchain
│   │   │   ├── unrealer/           # Unreal Engine 5 editor driver (Unreal MCP TCP socket)
│   │   │   ├── reviewer/           # LLM-powered code reviewer (git diff)
│   │   │   ├── analyzer/           # Deterministic static/security scanner (no LLM)
│   │   │   ├── stm32er/            # STM32 firmware bridge (STM32 Template Project MCP)
│   │   │   ├── esp32er/            # ESP32 firmware bridge (PlatformIO pio CLI, no MCP)
│   │   │   ├── arduiner/           # Arduino firmware bridge (arduino-cli, no MCP)
│   │   │   ├── esphomer/           # ESPHome smart-home device bridge (direct `esphome` CLI, no MCP) — YAML device configs (NO C++)
│   │   │   ├── camcorder/          # Webcam capture (OpenCV) — photo/video, Shoter's camera sibling
│   │   │   ├── recorder/           # Microphone capture (sounddevice) — WAV, the audio sibling of Camcorder/Shoter
│   │   │   ├── audioplayer/        # Audio-file PLAYBACK to speakers (soundfile + sounddevice) — playback counterpart of Recorder
│   │   │   ├── videoplayer/        # Video-file PLAYBACK with audio on a display (ffpyplayer + OpenCV) — on-screen sibling of AudioPlayer
│   │   │   └── mcp_doctor/         # Static external-MCP catalog triage (transport/runtime/PATH/secret blockers; no connect); canvas counterpart of external_mcp_doctor
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
- `embeding-model`: Embedding model for RAG. **Default**: `Nomic-Embed-Text:latest` (~600 MB resident VRAM). High-detail opt-in: `qwen3-embedding:8b` via **Config → Models** menu — uses roughly **10× more VRAM** (~6.24 GB resident on Q4_K_M), so it will trip the embedding-memory pre-flight guard on 8 GB consumer GPUs.
- `chained-model`: Primary chat model
- `unified_agent_model`: Model for multi-turn tool loop
- `ollama_base_url`: Ollama server URL
- `ollama_token`: Bearer token for authenticated Ollama
- `ANTHROPIC_API_KEY`: Claude API key
- `enable_unified_agent`: Enable tool-calling agent
- `unified_agent_max_iterations`: Max tool-call turns (default 4096)
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
4. **The FULL enabled tool/agent/skill surface is bound** (2026-06-16) — `CapabilityAwareToolAgentExecutor.invoke` no longer binds only a narrow planner subset; it binds **every enabled** tool, wrapped chat-agent, and skill (the ACPX/Skill tools are still checkbox-filtered by `filter_acpx_tools`). This fixes the "I don't have a file-writing / shell tool bound this turn" failure that appeared once 88 agents were present and the planner's `max_selected_tools` cap (20) silently excluded the one tool the user needed. The planner still scores/orders capabilities, but selection no longer gates what the LLM can call.
5. Wrapped agents launch in headless/background mode (no console popups)
6. `MultiTurnToolAgentExecutor` deduplicates wrapped chat-agent calls with identical arguments
7. After final answer, `services/answer_analizer.py` classifies as SUCCESS/FAILURE
8. Frontend renders "Create Flow" button on SUCCESS, converts tool-call log into downloadable `.flw`

### Full-Surface Binding — token-cost trims (2026-06-16)
Binding every enabled tool every turn would balloon the prompt, so two cost trims keep it cheap:
- **One-line-per-tool system prompt** — `bind_tools(...)` already sends the full JSON schema of every tool to the model, so the long prose tool descriptions that `_build_system_prompt` used to emit were ~5k redundant tokens/turn. The system prompt now lists each tool on a single line.
- **`ChatOllama keep_alive`** — set from `OLLAMA_KEEP_ALIVE` (default `-1` = keep the model resident indefinitely) so the model + the bound-tool prefix stay loaded between turns and the prefix is reused instead of re-evaluated.

### Step-by-Step Mode (toolbar checkbox — Multi-Turn runtime modifier)
`#step-by-step-enabled` / `step_by_step_enabled` is a Multi-Turn runtime modifier that makes the LLM perform **one concrete action at a time** and then **wait for the user's READY / output** before the next. It is plumbed browser → `consumers.py` → `interface.py` → `unified.py` (and MUST stay in `UnifiedAgentChain.invoke`'s payload-rebuild whitelist) → `mcp_agent.py::_build_system_prompt`, which appends the step-by-step instruction block to the system prompt. `bypass_prompt_validation` is now computed as `multi_turn_enabled OR acpx_enabled OR step_by_step_enabled`.

### When Multi-Turn is UNCHECKED:
- Legacy one-shot behavior preserved exactly
- Legacy prompt validation, legacy MCP context prefetch, full-tool binding, visible-console launch

### ACPX Gating
- `CapabilityAwareToolAgentExecutor` accepts `acpx_enabled` from payload
- When **disabled** (default), `filter_acpx_tools` strips all 12 ACPX/Skill tools from the LLM-facing surface before planning or capability selection
- When **enabled**, ACPX tools are added to planner surface and co-selection rules apply (e.g., `acp_spawn` auto-co-selects `acp_doctor` + `acp_kill`)

### Ask-Execs Gating (per-tool Proceed/Deny — Multi-Turn-only)
- Fourth toolbar checkbox **Ask Execs** (between ACPX and internet), enabled only while Multi-Turn is on; sent as `ask_execs_enabled` and re-gated on `multi_turn_enabled` everywhere
- The synchronous executor (worker thread) BLOCKS before every state-changing tool on a browser Proceed/Deny dialog, bridged by `agent/exec_permission.py::ExecPermissionBroker` (consumer registers a per-request broker keyed by user id; executor emits `exec_permission_request` onto the consumer loop via `asyncio.run_coroutine_threadsafe` and waits on a `threading.Event`; browser `exec-permission-response` → `resolve_permission` unblocks it)
- Gate runs **after** dedup + quota, **before** `tool.invoke`; `_requires_exec_permission` exempts `_MANAGEMENT_TOOLS` ∪ `_TOOL_QUOTA_EXEMPT` (read-only/polling tools are never prompted)
- **Deny halts the whole chain**: `_exec_denied` recorded → `exec_report_denied` flows executor → both chains → `interface.ask_rag` (`last_exec_report_denied`) → consumer → `response_parser` appends the red "Execution interrupted" banner (after exec-report tables, before save_message; independent of `exec_report_enabled`)
- Fail-safe: emit failure / Cancel / broker `close()` all resolve to `deny`; only "no broker registered" fails open. `ask_execs_enabled` + `conversation_user_id` MUST stay in `UnifiedAgentChain.invoke`'s payload whitelist

### Global Execution Planner (`global_execution_planner.py`)
- Builds DAG with nodes: `prefetch` to `execute` to `monitor` to `answer`
- `CapabilityRegistry` (`capability_registry.py`) scores tools/capabilities against request text
- Short follow-up scoring: 4 or fewer meaningful tokens boosts scores from last 4 chat messages (+15 max)
- Planner threshold = 6 if contexts selected, else 2
- Run-control tools (list/status/log/stop/wait/present) auto-injected when wrapped agents selected
- ACPX co-selection rules in `capability_registry.py`: selecting `acp_spawn` also selects `acp_doctor` and `acp_kill`

### MultiTurnToolAgentExecutor (`mcp_agent.py`)
- Explicit multi-turn tool loop (not opaque AgentExecutor)
- Max iterations: 4096 (configurable)
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
`WRAPPED_CHAT_AGENT_SPECS` (recent additions: `chat_agent_windower`, `chat_agent_kalier`, `chat_agent_unrealer`, `chat_agent_stm32er`, `chat_agent_esp32er`, `chat_agent_arduiner`, `chat_agent_esphomer`, `chat_agent_camcorder`, `chat_agent_recorder`, `chat_agent_audioplayer`, `chat_agent_videoplayer`, `chat_agent_mcp_doctor`, and `chat_agent_discoverer`). Key ones:
- `chat_agent_executer`, `chat_agent_pythonxer`, `chat_agent_dockerer`, `chat_agent_kuberneter`
- `chat_agent_ssher`, `chat_agent_scper`, `chat_agent_gitter`
- `chat_agent_sqler`, `chat_agent_mongoxer`, `chat_agent_apirer`
- `chat_agent_send_email`, `chat_agent_telegrammer`, `chat_agent_whatsapper`
- `chat_agent_notifier`, `chat_agent_shoter`, `chat_agent_mouser`, `chat_agent_keyboarder`
- `chat_agent_file_creator`, `chat_agent_move_file`, `chat_agent_deleter`
- `chat_agent_file_extractor`, `chat_agent_file_interpreter`, `chat_agent_image_interpreter`
- `chat_agent_summarize_text`, `chat_agent_prompter`, `chat_agent_crawler`
- `chat_agent_playwrighter` (scripted browser automation — login/forms/clicks/extract/screenshot/assert)
- `chat_agent_pser` (process finder), `chat_agent_jenkinser`
- `chat_agent_monitor_log`, `chat_agent_monitor_netstat` (long-running)
- `chat_agent_kyber_keygen`, `chat_agent_kyber_cipher`, `chat_agent_kyber_deciph`
- `chat_agent_windower`, `chat_agent_kalier`, `chat_agent_unrealer`
- `chat_agent_stm32er` (STM32 firmware), `chat_agent_esp32er` (ESP32 firmware via PlatformIO), `chat_agent_arduiner` (Arduino firmware via arduino-cli), `chat_agent_esphomer` (ESPHome YAML smart-home firmware via the `esphome` CLI)
- `chat_agent_mcp_doctor` (static external-MCP catalog triage — canvas/Multi-Turn counterpart of the live `external_mcp_doctor` tool)
- `chat_agent_camcorder` (webcam photo/video capture via OpenCV)
- `chat_agent_recorder` (microphone audio → WAV capture via `sounddevice`)
- `chat_agent_audioplayer` (audio-file playback to speakers via `soundfile` + `sounddevice`; volume / time_played truncate-loop)
- `chat_agent_videoplayer` (video-file playback with audio on a display via `ffpyplayer` + OpenCV; volume / time_played truncate-loop / window / fullscreen)
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

## 9b. External MCPs — the Universal MCP Client (2026-06-09 → 2026-06-17, the "External MCPs" era)

A **fourth, distinct MCP surface**, unrelated to the two built-in `Mcp`-model context providers above, to ACPX, and to the per-agent inline MCP clients (STM32er → STM32 Template Project MCP, Kalier → MCP-Kali-Server). The universal client connects Tlamatini to **ANY external MCP server** declared in a JSON file and brings its remote tools straight into the LLM's Multi-Turn surface.

### What it is
- **`agent/external_mcp_manager.py`** — the manager. Reads a catalog of server specs, lazily connects (in a **background thread, OFF the chat path**), and registers each connected server's remote tools for the LLM as **`ext__<server>__<tool>`**.
- **`agent/external_mcps.json`** — the on-disk catalog (resolved **next to `config.json`**, frozen/source-aware, **BOM-tolerant**). It uses the standard **`mcpServers`** shape — the same object a Claude-Code `.mcp.json` carries — so a user can paste an existing `.mcp.json` straight in.
- **User state + cap** — at most **5 active servers at once** (`MAX_ACTIVE`); which 5 are active is persisted user state. Connects are **lazy** with a **60 s** connect timeout.

### Four transports
| Transport | Mechanism | Client |
|---|---|---|
| `stdio` | local command — a Docker `mcp/*` image, `npx`, `uvx`, or `python` — driven over stdin/stdout | `_StdioMcpClient` |
| `streamable-http` | modern HTTP MCP | `httpx` |
| `sse` | legacy Server-Sent-Events MCP | `httpx` |
| `websocket` | WS MCP | `websockets` |

`tcp` / `named-pipe` specs are **detected-but-not-connectable** (catalogued with that reason). The network clients (`_NetworkMcpClientBase`) **duck-type** `_StdioMcpClient`, so the rest of the manager treats every transport identically.

### Eight LLM supervisor tools
The LLM administers the whole surface itself via eight tools (so it can add and activate an MCP mid-conversation):
- `external_mcp_status` — what's catalogued / active / connected.
- `external_mcp_reconnect` — re-dial a server.
- `external_mcp_doctor` — STATIC triage of a server spec (transport / runtime / command-on-PATH / placeholder-secret detection / blockers / next-step) **without connecting**.
- `external_mcp_list_tools` — enumerate a connected server's remote tools.
- `external_mcp_call` — invoke one remote tool directly.
- `external_mcp_import` — add a server to the catalog from a JSON **object OR a string**.
- `external_mcp_set_active` — choose the ≤5 active servers from a **list OR a comma-separated string**.
- `external_mcp_wait` — **block until a slow first-run Docker image pull is ready** (the first `docker run mcp/...` pulls the image, which can take minutes).

### Frontend
A dedicated **"External ▸ MCPs"** navbar dialog (`static/agent/js/external_mcps_dialog.js` + `css/external_mcps_dialog.css`): a searchable catalog, the ≤5-active selector, and **drag-a-`.json`-to-import**. Backed by three `@login_required` endpoints:
- `GET  /agent/external_mcps/` — catalog + active/connected state
- `POST /agent/external_mcps/activate/` — set the active set
- `POST /agent/external_mcps/import/` — add a server from pasted/dropped JSON

### Bulletproof contract (do NOT weaken)
- Connects run **off the chat path** (background thread) — a slow or hung server never delays a chat reply.
- A **bad / unreachable / unsupported** server is **catalogued-with-a-reason**, never a crash or a hang.
- **Auth**: a spec's `headers` (e.g. `Bearer …`) and `env` carry credentials into the connection.
- The **command watchdog exempts live MCP child PIDs** (`external_mcp_root_pids`) so the idle-kill daemon never reaps a healthy stdio MCP server.
- Design contract document: **`docs/external_mcp_bulletproof_architecture.md`**.

### Verified
Driven live against **10 no-key MCPs** — `memory`, `sqlite`, `redis`, `fetch`, `time`, `everything`, `sequentialthinking`, `filesystem`, `git`, `puppeteer` — each chaining External-MCP tools with `chat_agent_file_creator`: **10/10 PASS**.

### MCP Doctor agent (#78)
See Section 12 (Utility Agents) and Section 23 — the canvas/Multi-Turn agent counterpart of the live `external_mcp_doctor` tool, which performs the same STATIC catalog triage as a workflow node.

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
- `acp-agent-connectors.js` — 67 agent connection handlers (per-agent `update<Name>Connection` fetch helpers; some agents share or omit a handler, so this is NOT the agent-type count)
- `acp-control-buttons.js` — Start/stop/pause/hypervisor; now calls `compileCurrentACPFlow({ mode: 'write' })` before start
- `acp-file-io.js` — .flw save/load; uses `buildACPFlowSnapshot()` for schema-v2 JSON
- `acp-running-state.js` — LED indicators, process monitoring
- `acp-session.js` — Session pool management
- `acp-layout.js` — Canvas layout utilities
- `acp-validate.js` — Flow validation engine; now calls `compileCurrentACPFlow({ mode: 'dry_run' })` first
- `acp-flow-snapshot.js` — DOM walker that builds schema-v2 JSON with `parametrizerMappings` artifact
- `acp-parametrizer-dialog.js` — Parametrizer mapping UI
- `chat_page_runtime_poller.js` — Chat runtime status polling

**Shared (5)**:
- `canvas_item_dialog.js` — Agent config dialog on canvas
- `contextual_menus.js` — Right-click menus
- `tools_dialog.js` — Tool enable/disable dialog
- `acp-undo-manager.js` — Undo stack manager
- `external_mcps_dialog.js` — **"External ▸ MCPs"** navbar dialog: searchable catalog, ≤5-active selector, drag-a-`.json` import (backed by `GET /agent/external_mcps/`, `POST /agent/external_mcps/activate/`, `POST /agent/external_mcps/import/`). See Section 9b

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

## 12. All 82 Workflow Agent Types

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
- **Pythonxer** — Inline Python behind a strict gate (`compile()` syntax floor + blocking Ruff, `ruff_blocking=true` default); ALWAYS triggers downstream no matter the outcome (exit code drives only the LED + Multi-Turn retry loop)
- **Prompter** — LLM prompt execution
- **Summarizer** — Log monitoring + one-shot text summarization
- **Crawler** — Developer-oriented web crawler with LLM analysis
- **Googler** — Google search + text extraction (Playwright, MUST run in ThreadPoolExecutor)
- **Playwrighter** — Scripted interactive browser automation (Playwright; Chromium/Firefox/WebKit). Drives a real browser through an ordered list of declarative steps (goto/click/fill/press/wait_for/extract_text/extract_attr/screenshot/assert_visible/assert_text/download) for authenticated/JS-rendered/multi-step flows that Crawler (static fetch) and Googler (search) cannot do. Deterministic (no LLM); emits `INI_SECTION_PLAYWRIGHTER` (`start_url`/`final_url`/`status`/`steps_run`/`assert_result`/`response_body`); always triggers `target_agents`. Both a canvas agent and the LLM-callable `chat_agent_playwrighter` Multi-Turn tool
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
- **Camcorder** — Physical-camera (webcam) capture via OpenCV (`cv2`); the hardware-camera sibling of Shoter (Shoter = screen, Camcorder = camera). `capture_mode` ∈ `photo` (default, one `.jpg` shot) / `video` (a `.mp4` segment of `video_duration_seconds`, no audio); `camera_index` picks the device; `resolution_width`/`resolution_height` default `0×0` = camera-native (set `W×H` to request a mode, read back + logged). Saves to `Pictures/TlamatiniCamcorder`. Observational (NOT in the Exec Report); emits `INI_SECTION_CAMCORDER` and always triggers `target_agents`. Needs `opencv-python`. Canvas counterpart of `chat_agent_camcorder`
- **Recorder** — Microphone / audio-input capture via `sounddevice`, saved as a WAV (stdlib `wave`); the audio sibling of the capture trio (Shoter = screen, Camcorder = camera, Recorder = sound). Records from the system DEFAULT input device for `record_seconds` (pick another mic with `device_index` — the agent logs the numbered device list at startup — or by name substring with `device_name`); `sample_rate` defaults `0` = device-native (read back + logged), `channels` defaults mono (clamped to the device max), `input_gain_percent` is post-capture digital gain (`100` = unity — amplifying may CLIP, so `clipped_samples` is reported). Saves to `Music/TlamatiniRecords`. Observational (NOT in the Exec Report); emits `INI_SECTION_RECORDER` and always triggers `target_agents`. Needs `sounddevice`. Canvas counterpart of `chat_agent_recorder`
- **AudioPlayer** — Audio-file PLAYBACK to a speakers/output device via `soundfile` (decode) + `sounddevice` (stream); the playback counterpart of Recorder (mic-IN → AudioPlayer = speakers-OUT). `audio_file` (required) is the path (WAV/FLAC/OGG/AIFF, MP3 with a recent libsndfile); plays to the system DEFAULT output by default (or `device_index`/`device_name`). `volume_percent` is a software gain (`100` = unity; `clipped_samples` reported). `time_played`: `0` = whole file once; `N>0` = exactly N s, TRUNCATING a longer file or LOOPING a shorter one (whole repeats + final partial) via a streaming wrap-around callback. `sample_rate` defaults `0` = the file's own native rate (correct pitch; read from the file). Does NOT change the OS default output device. Observational/output (NOT in the Exec Report); emits `INI_SECTION_AUDIOPLAYER` and always triggers `target_agents`. Needs `sounddevice` + `soundfile`. Canvas counterpart of `chat_agent_audioplayer`
- **VideoPlayer** — Video-file PLAYBACK (WITH audio) on a chosen display via `ffpyplayer` (decode + synced audio + volume; its pip wheel BUNDLES ffmpeg + SDL — no external ffmpeg, no runtime download) + OpenCV (`cv2`) for the window; degrades to SILENT cv2 video if ffpyplayer is absent. `video_file` (required) is the path (.mp4/.mov/.mkv/.avi/.webm). `display_index` picks the monitor (`-1` = primary; enumerated + logged at startup). `volume_percent` = audio level (capped at 100). `time_played`: `0` = whole video once; `N>0` = exactly N s, TRUNCATING a longer file or LOOPING a shorter one (whole repeats + final partial). `window_width`/`window_height` size the window (`0` = native, centered on the chosen display); `fullscreen` fills the monitor; `keep_aspect` (default) letterboxes. Observational/output (NOT in the Exec Report); emits `INI_SECTION_VIDEOPLAYER` and always triggers `target_agents`. Needs `ffpyplayer` + `opencv-python`. Canvas counterpart of `chat_agent_videoplayer`
- **Mouser** — Mouse pointer movement (7 movement types)
- **Keyboarder** — Keyboard typing / hotkey automation (robust parser)
- **Windower** — Win32 window manager (pywin32 + ctypes, self-contained; ports the window-management subset of Microsoft's Windows-MCP incl. the `AttachThreadInput` cross-process focus dance). The third member of the desktop-UI trio — acts on the WINDOW itself (Windower = the window, Mouser = clicks inside it, Keyboarder = types into it). `action` ∈ list / focus / minimize / maximize / restore / move / resize / move_resize / close / topmost / untopmost / arrange (snap/tile to halves, quadrants, center, full); matches `window_title` by substring/exact/regex (+ `match_index`); emits `INI_SECTION_WINDOWER` (`action`/`window_title`/`matched`/`match_count`/`state`/`left`/`top`/`width`/`height`/`response_body`) and always triggers `target_agents`. Both a canvas agent and the LLM-callable `chat_agent_windower` Multi-Turn tool
- **Kalier** — Kali Linux offensive-security bridge. Talks to the MCP-Kali-Server (`https://www.kali.org/tools/mcp-kali-server/`) Flask API (`server.py`; default `http://127.0.0.1:5000`) over stdlib `urllib` (self-contained, no `requests`/`mcp` deps in the pool). `action` ∈ command / nmap / gobuster / dirb / nikto / sqlmap / metasploit / hydra / john / wpscan / enum4linux / health; emits `INI_SECTION_KALIER` (`action`/`endpoint`/`method`/`subject`/`return_code`/`success`/`timed_out`/`server_url`/`response_body`) and always triggers `target_agents`. In **chat/Multi-Turn** Tlamatini is the embedded MCP-Kali-Server client: `chat_agent_kalier` auto-injects the configured **`kali_server_url`** (set once in Config ▸ URLs / `config.json`) as the default `server_url`, so prompts never repeat the Kali box address (override per-call with `server_url=`); canvas runs set it in the node dialog. Both a canvas agent and the LLM-callable `chat_agent_kalier` Multi-Turn tool. Authorized targets only
- **Discoverer** — ProjectDiscovery recon-suite bridge (`https://github.com/projectdiscovery`) for recon / attack-surface mapping / vuln discovery. Runs ONE tool per run selected by `tool` ∈ subfinder (passive subdomain enum) / httpx (HTTP probe + fingerprint) / naabu (port scan) / katana (crawler) / nuclei (template vuln scan) / cvemap→vulnx (CVE search), plus meta `bootstrap` / `validate` / `update_templates` / `list_tools`. Direct-CLI sibling of Kalier/ESP32er/Arduiner (stdlib-only `agent/agents/discoverer/discoverer.py`; no MCP server, never imports `agent.*`). **Zero-config PRIVATE Go toolchain**: on first use it downloads the Go compiler into `<install_dir>/Go` and `go install`s the tool into `<install_dir>/Go/bin-tools` — no system Go, no PATH change. The `pdcp_api_key` (PDCP_API_KEY) is OPTIONAL for every tool; naabu defaults to a Windows-safe CONNECT scan; a fail-safe preflight REFUSES rather than mis-scan. Emits `INI_SECTION_DISCOVERER` (`tool`/`target`/`returncode`/`success`/`findings_count`/`json_path`/`pdcp_used`/`stage`) and always triggers `target_agents`. Both a canvas agent and the LLM-callable `chat_agent_discoverer` Multi-Turn tool. Authorized targets only
- **File-Creator** — Creates files with specified content
- **File-Interpreter** — Document parsing and text/image extraction
- **File-Extractor** — Raw text extraction (PDF, DOCX, etc.)
- **Image-Interpreter** — LLM vision-based image analysis
- **J-Decompiler** — JAR/WAR decompilation (bundled jd-cli)
- **De-Compresser** — Deterministic archive worker (compress OR decompress; `.gz` / `.zip` / `.7z` / `.tar.gz` / `.gz.tar`; password from `DE_COMPRESSER_PWD` when `passwordless=false`; always triggers `target_agents` on success OR failure)
- **Telegrammer** — Telegram send/receive via official Telegram surfaces
- **ACPXer** — ACPX session driver for external CLIs
- **Teletlamatini** — Telegram bot bridge to Tlamatini chat
- **Whatsapper** — WhatsApp send/receive via official Meta WhatsApp Cloud API only
- **Unrealer** — Drives an Unreal Engine 5 editor via the Unreal MCP plugin's TCP socket (`127.0.0.1:55557`); forwards any verb the connected plugin build exposes — up to a 53-command, nine-category surface (editor incl. `take_screenshot`, Blueprints incl. `set_pawn_properties`, node graph, input mappings, UMG widgets, **system** `execute_python`/console/`get_class_info`/`list_assets`, **level** I/O, **asset** import, **material** authoring); the P3 headless tools (build/cook/test) are NOT reachable over this editor socket; emits `INI_SECTION_UNREALER` and always triggers `target_agents`. Recommended plugin: Tlamatini's own extended Unreal MCP fork (the Unreal Engine MCP modified specifically for this system) at `https://github.com/XAIHT/XaihtUnrealEngineMCP.git` — a drop-in built on upstream `chongdashu/unreal-mcp` that ships the full 53-command surface
- **Reviewer** — LLM-powered code reviewer; resolves a `git diff` for `repo_path` (`diff_ref` like `HEAD~1`/`origin/main`, or empty = working-tree + staged), reviews it with an Ollama model, emits `INI_SECTION_REVIEWER` with a `verdict` (`APPROVE`/`REQUEST_CHANGES`/`COMMENT`); always triggers `target_agents` so a Forker can branch on `{verdict}`. Canvas counterpart of the `code-review` skill
- **Analyzer** — Deterministic static/security scanner (no LLM); runs whichever of `bandit`/`semgrep`/`ruff`/`eslint`/`gitleaks`/`pip-audit` are on PATH over `target_path`, emits `INI_SECTION_ANALYZER` with `status` (`clean`/`findings`/`error`) + `total_findings`; always triggers `target_agents` so a Forker can gate on `{status}`. Canvas counterpart of the `security-audit` skill
- **STM32er** — STM32 firmware bridge to the **STM32 Template Project MCP** (`https://github.com/XAIHT/STM32TemplateProjectMCP`); a self-contained inline MCP stdio JSON-RPC client (no `mcp` dep in the pool) that scaffolds/builds/flashes/observes STM32F407VG firmware. `action` ∈ the **23 MCP tools** + 2 composites (`serial_session`, `live_monitor`) + 2 meta (`bootstrap`, `validate`). **Zero-config auto-bootstrap**: with no on-disk `server_script` (the default is now empty) STM32er DOWNLOADS the MCP itself (shallow `git clone`, with a GitHub-zip fallback when git is absent) into `%LOCALAPPDATA%/Tlamatini/STM32TemplateProjectMCP`, pip-installs `mcp`+`pyserial` if missing, and validates — so the user installs **only STM32CubeIDE + Tlamatini** (new `action: bootstrap`; new `config.yaml` keys `auto_bootstrap`/`mcp_repo_url`/`mcp_ref`/`mcp_install_dir`/`auto_update`/`pip_install`; new `config.json` globals `stm32_mcp_server_script` (now `""`)/`stm32_mcp_repo_url`/`stm32_mcp_install_dir`). **Safety preflight** (critical-mission fail-safe): validates compiler / CubeIDE / make / programmer / ST-LINK driver+probe / device-family before any compile or flash and REFUSES rather than mis-build or mis-flash — compile needs NO board, while flash/erase/reset/serial/SWD/`live_*` require a connected ST-LINK, and a cross-STM32F-family device is refused (new `action: validate`; new `config.yaml` keys `preflight` (true) / `device`). The MCP template is still STM32F407VG-specific; STM32er safely REFUSES other families (multi-family fork is future work). Emits `INI_SECTION_STM32ER` and always triggers `target_agents`. Both a canvas agent and the LLM-callable `chat_agent_stm32er` Multi-Turn tool. Verified zero-config end-to-end (download → build → flash → reset) on a real **STM32F407G-DISC1**
- **ESP32er** — ESP32 firmware bridge via **PlatformIO Core** (`pio`). Unlike STM32er (which drives a separate MCP server), PlatformIO already ships a complete CLI, so ESP32er invokes `pio` subcommands **directly** (no MCP server) over a stdlib-only pool script (`subprocess` + `urllib`). **Zero-config auto-bootstrap**: with no on-disk `pio_executable` and `auto_bootstrap: true`, ESP32er downloads PlatformIO Core itself (official `get-platformio.py`, `pip install platformio` fallback) into `%LOCALAPPDATA%/Tlamatini/platformio` — the user installs **only the board USB driver + Tlamatini**. **Safety preflight** (fail-safe): validates `pio` is resolvable + a `platformio.ini` exists and, for upload/monitor, that a serial port is connected (ESP32 flashes over its onboard USB-serial bootloader — no external JTAG probe needed), and REFUSES rather than run a build/upload that cannot succeed. One capability per run via `action` ∈ environment/meta (`bootstrap`/`validate`/`system_info`/`boards`); project lifecycle (`create_project`/`write_source`/`read_source`/`list_sources`/`clean`); build & flash (`build`/`upload`/`build_and_upload`/`list_artifacts`/`scaffold_build_upload`); serial HIL (`device_list`/`monitor`/`monitor_session`); packages & QA (`pkg_install`/`pkg_list`/`pkg_update`/`check`/`test`). Emits `INI_SECTION_ESP32ER` (`action`/`tool`/`ok`/`returncode`/`success`/`project_dir`/`port`/`environment`/`stage`) and always triggers `target_agents`. NOTE: the first build downloads the espressif32 platform + toolchain (hundreds of MB). Both a canvas agent and the LLM-callable `chat_agent_esp32er` Multi-Turn tool
- **Arduiner** — Arduino firmware bridge via the **Arduino CLI** (`arduino-cli`). The direct-CLI sibling of ESP32er: like `pio` (and unlike STM32er's MCP server), `arduino-cli` is itself a complete CLI, so Arduiner invokes `arduino-cli` subcommands **directly** (no MCP server) over a stdlib-only pool script. **The microcontroller is selected by `fqbn`** (Fully Qualified Board Name, e.g. `arduino:avr:uno`, `arduino:avr:mega2560`, `arduino:samd:mkr1000`, `esp32:esp32:esp32`); `port` + `baud` set the upload/monitor link. **Zero-config auto-bootstrap**: with no on-disk `arduino_cli_executable` and `auto_bootstrap: true`, Arduiner downloads the arduino-cli **binary** itself (Go binary from `downloads.arduino.cc`, unzipped into `%LOCALAPPDATA%/Tlamatini/arduino-cli`, then `config init` + `core update-index`) — a binary download, NOT a pip install. **Auto-core-install**: arduino-cli (unlike PlatformIO) does NOT auto-install platforms on compile, so before a build Arduiner derives the FQBN's platform and runs `core install` when missing (`auto_core_install: true`; honors `additional_urls` for third-party ESP32/STM32/RP2040 cores). **Safety preflight** (fail-safe): validates `arduino-cli` resolvable + a sketch (`.ino`) + an FQBN exist and, for upload/monitor, a connected serial port; REFUSES rather than run a build/upload that cannot succeed. Ships the bundled **ArduinoTemplateProject** scaffold (the Arduino analog of STM32er's and ESP32er's templates) — `create_project` copies it, renames the `.ino`, and stamps the FQBN/port into `sketch.yaml`. One capability per run via `action` (bootstrap/validate/boards/device_list, cores & libs, project lifecycle, build/upload/build_and_upload/clean, monitor/monitor_session). Emits `INI_SECTION_ARDUINER` (`action`/`tool`/`ok`/`returncode`/`success`/`fqbn`/`port`/`sketch_path`/`stage`) and always triggers `target_agents`. Both a canvas agent and the LLM-callable `chat_agent_arduiner` Multi-Turn tool
- **ESPHomer** — ESPHome (`https://esphome.io`) smart-home device firmware from a **simple YAML config (NO C++)** on ESP32 / ESP8266 / RP2040 / BK72xx. The fourth microcontroller agent and a direct-CLI sibling of ESP32er/Arduiner: ESPHome ships a complete `esphome` CLI, so ESPHomer invokes `esphome` subcommands **directly** (no MCP server) over a stdlib-only pool script. **Zero-config auto-bootstrap**: with no on-disk `esphome_executable` and `auto_bootstrap: true`, ESPHomer `pip install esphome` into the agent's Python and validates it — the user installs **only the board USB driver + Tlamatini** (ESPHome vendors PlatformIO + toolchains at first compile). **Safety preflight** (fail-safe): validates `esphome` resolvable + a device YAML exists and, for upload/logs/run, that a serial port is connected **or** an OTA host is supplied in `port` (first flash USB, OTA after), and REFUSES rather than run a build/upload that cannot succeed. One capability per run via `action` ∈ environment/meta (`bootstrap`/`validate`/`version`); device YAML lifecycle (**`new_config`** — a built-in headless GENERATOR that writes a minimal valid device YAML from `name`/`platform`/`board`/`wifi_ssid`/`wifi_password`/`led_pin`, replacing the interactive `esphome wizard`; `write_config`/`read_config`/`config`/`clean`); build & flash (`compile`/`upload`/`run`/`list_artifacts`/`scaffold_compile_upload`); serial/OTA HIL (`logs`). Ships an **ESPHomeTemplateProject** sample. Emits `INI_SECTION_ESPHOMER` (`action`/`tool`/`ok`/`returncode`/`success`/`config_path`/`name`/`port`/`stage`) and always triggers `target_agents`. Both a canvas agent and the LLM-callable `chat_agent_esphomer` Multi-Turn tool

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
- **MCP Doctor** — STATIC triage of an **external MCP server** catalog entry, with **no connect**: reports transport, runtime (docker / npx / uvx / python / node / …), whether the command is on PATH, placeholder-secret detection, blockers, and a next-step. The canvas / Multi-Turn agent counterpart of the live `external_mcp_doctor` supervisor tool (Section 9b). Emits `INI_SECTION_MCP_DOCTOR` (a Parametrizer source) and triggers `target_agents`. Both a canvas agent and the LLM-callable `chat_agent_mcp_doctor` Multi-Turn tool
- **Instant Messaging Doctor** — diagnoses and optionally repairs Telegrammer/Whatsapper readiness via the official Telegram Bot API + Meta WhatsApp Cloud API: validates bot/Meta tokens, contacts, recipient reachability, WhatsApp templates + the 24-hour window, and webhook config. Non-mutating by default (`retry_send: false`); only resends through an approved template or a reachable Telegram chat when asked. The automatic companion launched after a Telegrammer/Whatsapper failure (and a pre-flight for mission-critical sends). Emits `INI_SECTION_INSTANT_MESSAGING_DOCTOR`; always triggers `target_agents`. Both a canvas agent and the LLM-callable `chat_agent_instant_messaging_doctor` Multi-Turn tool
- **FlowCreator** — AI-powered flow designer (system agent, singleton)

### Terminal/Monitoring Agents (do NOT start downstream)
- **Monitor-Log** — LLM-powered log file monitor
- **Monitor-Netstat** — LLM-powered network port monitor
- **Emailer** — SMTP email sender on pattern detection
- **RecMailer** — IMAP email receiver/monitor
- **Notifier** — In-browser DOM popup (chat UI polls a dropped `notification.json`) + optional sound, plus a Tlamatini.exe console-window flash (FlashWindowEx) and an UPPERCASE log banner. (The earlier OS/desktop-toast experiment was REMOVED 2026-05-30 and replaced by the window-flash attention surface — there is no OS toast.)
- **Whatsapper** — WhatsApp send/receive via official Meta WhatsApp Cloud API only
- **Telegrammer** — Telegram send/receive via official Bot API plus optional official user session
- **FlowHypervisor** — System-managed LLM anomaly detector (system agent)

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

- **External MCPs era (v1.26.0, 2026-06-09 → 2026-06-17)** — four shipped pieces. (1) **Universal external-MCP client** (`agent/external_mcp_manager.py`, catalog `agent/external_mcps.json` in the `mcpServers` shape next to `config.json`, ≤5 active, lazy background connect, 60 s timeout, BOM-tolerant): connects to ANY external MCP server over `stdio` / `streamable-http` / `sse` / `websocket` and binds its remote tools as `ext__<server>__<tool>`; eight LLM supervisor tools (`external_mcp_status` / `reconnect` / `doctor` / `list_tools` / `call` / `import` / `set_active` / `wait`); "External ▸ MCPs" navbar dialog + `GET /agent/external_mcps/`, `POST .../activate/`, `POST .../import/` (all `@login_required`). Bulletproof: connects run OFF the chat path, bad/unreachable/unsupported = catalogued-with-reason (never crash/hang), command watchdog exempts live MCP child PIDs (`external_mcp_root_pids`). Distinct from the built-in `Mcp` context providers, ACPX, and the inline per-agent MCP clients. Design doc `docs/external_mcp_bulletproof_architecture.md`. Verified live driving 10 no-key MCPs (memory/sqlite/redis/fetch/time/everything/sequentialthinking/filesystem/git/puppeteer) → 10/10. See Section 9b. (2) **MCP Doctor agent (#78)** — canvas + `chat_agent_mcp_doctor`; static catalog triage (transport/runtime/PATH/placeholder-secret/blockers/next-step, no connect); emits `INI_SECTION_MCP_DOCTOR`; migrations 0141 (Agent row) / 0142 (`Chat-Agent-MCP-Doctor` Tool row) / 0143 (demo prompt 81). (3) **Multi-Turn binds the FULL enabled surface** — `CapabilityAwareToolAgentExecutor.invoke` binds every enabled tool/agent/skill (ACPX still checkbox-filtered), fixing "I don't have a file-writing/shell tool bound this turn" with 88 agents present; cost trims = one-line-per-tool system prompt (bind_tools already sends the full schema) + `ChatOllama keep_alive` (`OLLAMA_KEEP_ALIVE`, default `-1`) prefix reuse. (4) **Step-by-Step mode** (`#step-by-step-enabled` / `step_by_step_enabled`) — Multi-Turn runtime modifier: one concrete action at a time, wait for the user's READY; plumbed browser → consumers → interface → unified.py (payload whitelist) → `mcp_agent._build_system_prompt`; `bypass_prompt_validation = multi_turn OR acpx OR step_by_step`. Agent count is now **78** (added ESPHomer + MCP Doctor).
- **STM32er zero-config bootstrap + fail-safe preflight (v1.9.0)** — STM32er (agent #68; wrapped tool `chat_agent_stm32er`) ships two safety/UX pillars. (1) **Auto-bootstrap**: with `server_script` empty (the new default), the agent downloads the STM32 Template Project MCP itself (shallow `git clone`, GitHub-zip fallback) into `%LOCALAPPDATA%/Tlamatini/STM32TemplateProjectMCP` and pip-installs `mcp`+`pyserial` — the user installs only STM32CubeIDE + Tlamatini (`action: bootstrap`; config.yaml `auto_bootstrap`/`mcp_repo_url`/`mcp_ref`/`mcp_install_dir`/`auto_update`/`pip_install`; config.json `stm32_mcp_server_script`/`stm32_mcp_repo_url`/`stm32_mcp_install_dir`). (2) **Preflight** validates compiler/CubeIDE/make/programmer/ST-LINK-driver+probe/device-family before compile or flash and REFUSES rather than mis-build/flash — compile needs no board; flash/erase/reset/serial/SWD/`live_*` require a connected ST-LINK; a cross-STM32F-family device is refused (`action: validate`; config.yaml `preflight`/`device`). The MCP template is STM32F407VG-specific; other families are safely refused (multi-family is future work). `requirements.txt` now pins `pyserial==3.5` (`mcp==1.25.0` already present). 122 tests; verified zero-config end-to-end (download → build → flash → reset) on a real STM32F407G-DISC1. Catalog demos via migration 0103 (63 STM32 GENESIS, 64 STM32 BLINKY, 65 STM32 HIL OBSERVATORY — the third a real-hardware HIL run).
- **Reviewer commit-state + secret precision (v1.4.2)** — `build_review_prompt` now takes `diff_ref` and tells the LLM that uncommitted working-tree/staged diffs are NOT "committed/pushed", plus teaches the `regen_secrets.py` scrub convention so local "keyed" creds in `config.json` / `agents/*/config.yaml` aren't mis-flagged as leaked. Mirror any change in BOTH `reviewer.py` and `code_review/SKILL.md`.
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
| 2 | **Reviewer** | ✅ **Implemented v1.4.2** — AI code review (LLM-powered git-diff analysis); canvas agent (#63) + `code-review` skill |
| 3 | **Analyzer** | ✅ **Implemented v1.4.2** — Static analysis / SAST (bandit, semgrep, ruff, eslint, gitleaks, pip-audit); canvas agent (#64) + `security-audit` skill |
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
5. If tools available, use them for ANY request. **Loaded-context priority clause (2026-05-25)**: when the user asks a generic "summarize the project / the source code / the provided context" question, the user-loaded `<context>` block takes priority over the always-injected `<self_knowledge>` block, so Tlamatini summarizes the loaded project and no longer summarizes herself
6. Tables must use HTML, not markdown pipe syntax
7. Responses must end with `END-RESPONSE`
8. In Multi-Turn, the LLM is an OPERATOR, not just an advisor
9. Up to 4096 multi-turn iterations available
10. Identity: the LLM IS Tlamatini
11. In ACPX mode, the LLM may spawn external child agents; it must respect permission gates and budget limits

### `<self_knowledge>` block (2026-05-25)
`prompt.pmt` now carries a `<self_knowledge>{self_knowledge}</self_knowledge>` block, populated at prompt-build time from `Tlamatini/agent/Tlamatini.md` (see Section 30). It also gains a **"CRITICAL SCOPE"** clause on that block telling the LLM that the self-knowledge map describes Tlamatini herself and must NOT override a user-loaded `<context>` for generic-summary requests — the deterministic scope header from `agent/rag/utils.py::prepend_loaded_context_scope()` reinforces this in all four chains. The block is always present (independent of whether the user loaded a project), so identity / capability questions always have grounding even with no `<context>`.

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
| Orphan reaper | `Tlamatini/agent/orphan_reaper.py` |

---

## 29. Orphan-Process Cleanup (the `conhost.exe` reaper)

A three-tier reaper that cleans up Windows console-host orphans and zombie descendants every console subprocess can leave behind. Lives in `Tlamatini/agent/orphan_reaper.py`. Without this, users were seeing `conhost.exe` processes lingering in Task Manager **bearing the Tlamatini icon** (conhost inherits its icon from the parent EXE that spawned it) and reasonably assuming Tlamatini was leaking processes — or worse, hiding a backdoor.

### Why this exists

On Windows, every console child Tlamatini's agents launch drags a `conhost.exe` companion alongside it. When the immediate parent dies without first reaping its console child, the `conhost.exe` lingers as an orphan with our icon. The reaper closes the gap at three lifecycle points; the **spawn sites** were hardened in the same pass so most of the orphans never get created in the first place.

### The three tiers

| Tier | Hook point | Scope | Surfacing |
|---|---|---|---|
| **Tier 1** | `MultiTurnToolAgentExecutor._reap_after_tool()` (`agent/mcp_agent.py`) — after every tool call in `_PROCESS_SPAWNING_TOOL_NAMES` (`execute_command`, `execute_file`, `unzip_file`, `decompile_java`, `googler`, `agent_starter/stopper/parametrizer`) plus every `chat_agent_*` and every `acp_*`. Fires on both success AND exception paths. | Zombie / dead descendants of `os.getpid()` + orphaned `conhost.exe` / `openconsole.exe` whose parent is in our process tree or whose parent is gone. **No pool-cmdline scan** (cheap path). | Silent. Survivors accumulate on `self._orphan_survivors` and drop into `global_state['last_orphan_survivors']` for Tier 2. |
| **Tier 2** | `AgentConsumer._tier2_orphan_sweep()` (`agent/consumers.py`) — once, in a `run_in_executor` thread, **after** `process_llm_response` broadcasts the answer so the main reply is never delayed. Merges Tier-1 leftovers with Tier-2 survivors, de-duped by PID. | Same as Tier 1 **plus** the agent-pool cmdline scan (processes whose `cmdline` references `agents/pools/...` or `agents/pools/_chat_runs_/...` but are no longer tracked). | If anything survives both tiers, broadcasts a SECOND `agent_message` to the room listing every `name + PID` so the user can end them manually. Rendered by `orphan_reaper.format_survivors_message()` (returns `None` on empty — common case). |
| **Tier 3** | `AgentConfig.ready()` (`agent/apps.py`) — registered next to the existing pool-cleanup on the `atexit` / SIGINT / SIGBREAK path. | Full sweep (self-tree + pool cmdline + console-host orphans). | Logs `--- [Tier-3 reaper] killed=… survivors=… errors=…` to `tlamatini.log`; survivors listed by `name (PID)` for post-mortem. |

### Public API

```python
from agent.orphan_reaper import reap_orphans, format_survivors_message, ReapResult

result: ReapResult = reap_orphans(
    scope="tier1:after_tool_call",          # free-form label that ends up in tlamatini.log
    include_self_tree=True,                  # kill dead/zombie descendants of os.getpid()
    include_pool_scan=False,                 # Tier 2 / Tier 3 enable this
    include_console_host_sweep=True,         # the actual conhost.exe reap
)
# result.killed:    list[(name, pid)] of processes we reaped
# result.survivors: list[(name, pid)] of processes we failed to kill
# result.errors:    list[str] of swallowed exceptions

message = format_survivors_message(result.survivors)  # None if no survivors
```

### Companion hardening — preventing the orphan in the first place

The reaper is paired with spawn-site changes that mean most `conhost.exe` companions are never created:

- `agent/views.py::execute_starter_agent_view`, `execute_ender_agent_view`, `restart_agent_view`, `execute_flowcreator_view` now spawn with `CREATE_NEW_PROCESS_GROUP | CREATE_NO_WINDOW | DETACHED_PROCESS` and stdio piped to `subprocess.DEVNULL`.
- `agent/acpx/runtime.py` adds `_windows_creationflags()` (same triple flag) and `_kill_process_tree()` — a `psutil`-driven recursive descendant kill (`terminate → wait 2s → kill`) so CLI wrappers like `claude` / `cursor-agent` that shell out to `node.exe` get the helper killed too, not just the top-level handle.
- Every pool-agent script (`agents/<name>/<name>.py` — Ender, Apirer, Crawler, Forker, Counter, … all 50+) installs a top-of-module `subprocess.Popen.__init__` monkey-patch — `_chg_guarded_init` — that defaults `creationflags` to `CREATE_NO_WINDOW` unless the caller explicitly asked for a console (`CREATE_NEW_CONSOLE` / `DETACHED_PROCESS`). This is the seatbelt: a future tool that forgets the flag gets it for free.

### What gets reaped (and what does NOT)

A process is a Tlamatini orphan if **any** of:
- It is a descendant of the current Tlamatini PID and its status is `psutil.STATUS_ZOMBIE` or `psutil.STATUS_DEAD`.
- It is a `conhost.exe` / `openconsole.exe` whose parent PID is in our process tree, OR whose parent PID is `0` / `None`, OR whose parent no longer exists.
- Its `cmdline` references the agent-pool directory (`agents/pools/...` or `agents/pools/_chat_runs_/...`) and the pool-scan tier is enabled.

Each candidate is escalated `terminate → wait 1s → kill` via `psutil`. Unrelated `conhost.exe` (a different IDE's child, your shell's child) is left alone — the parentage check keeps the sweep narrow.

### Safety contract

**The reaper MUST NEVER raise into the caller.** Every external call is wrapped in `try/except`; every survivor is recorded rather than re-raised; a `psutil`-import failure degrades silently (`ReapResult.errors.append("psutil not available — skipping reap")`). A cleanup that crashes the chat path is worse than the orphans it tries to kill.

### Adding a tool that spawns a console child

Either:
1. **Add the tool name to `_PROCESS_SPAWNING_TOOL_NAMES`** in `mcp_agent.py` so Tier 1 runs after it (preferred for tools that may spawn many short-lived children mid-loop), or
2. **Do nothing** — Tier 2's pool-cmdline scan is wide enough to catch almost everything that Tier 1 would, just one step later. Tier 3 is the backstop for both.

---

## 30. Self-Knowledge Injection & Runtime/Build Self-Modification (2026-05-25)

Two complementary capabilities let Tlamatini understand — and, optionally, edit — herself. They are **independent axes**: every build either ships the self-knowledge map or not (always, by default, it does), and *separately* either bundles her own source tree or not.

### 30.1 Self-Knowledge Injection (`Tlamatini.md` → `<self_knowledge>`)

A new file, `Tlamatini/agent/Tlamatini.md`, is the LLM's first-person **self-knowledge map** — who/what she is, the two runtime modes (frozen vs source) and how to detect which one she is in, the ports she uses (8000 web, 8765 System-Metrics WebSocket, 50051 Files-Search gRPC), her main pages, her tech stack, her capability surface, and how she can improve herself. Its audience is the LLM alone, so it **deliberately does NOT follow `prompt.pmt`'s HTML / contrast styling rules** — it is plain reference prose for the model, not user-facing output.

It is injected into `prompt.pmt`'s `<self_knowledge>{self_knowledge}</self_knowledge>` block at prompt-build time by `agent/rag/config.py`:

- `SELF_KNOWLEDGE_FILENAME = 'Tlamatini.md'`
- `SELF_KNOWLEDGE_PLACEHOLDER = '{self_knowledge}'`
- `_load_self_knowledge_block(application_path)` — reads the file, **brace-escapes** its contents (`{` → `{{`, `}` → `}}`) so the file's own code snippets don't collide with the f-string template variables, and **FAILS OPEN**: a missing / empty / unreadable file degrades to a short literal notice and **never raises**.
- `load_config_and_prompt()` performs the placeholder replace at the **single** prompt-load site, so the self-knowledge block reaches **all** chains (basic, history-aware, unified, prompt-only) with **no new input variable** threaded through the chain layer.

Resolution mirrors `prompt.pmt` / `config.json`: it is read from the **application directory** — the install root next to the `.exe` in frozen mode, `Tlamatini/agent/` in source mode. `build.py` ships it via `--add-data` **and** copies it to the install root.

### 30.2 Runtime / Build Self-Modification (`TlamatiniSourceCode/`)

An **OPTIONAL** directory, `TlamatiniSourceCode/` at the install root, holds a complete copy of Tlamatini's own source so she can read, modify, and **rebuild** herself. This is the **second capability axis**, fully independent of the frozen/source distinction:

- Directory **present** = a **"self-able-modify"** build.
- Directory **absent** = a **"not-self-able-modify"** build.

It is bundled **only** when you build with `build.py --self-modify`, which (since 2026-06-12) calls the auxiliary **`copy_source_assets.py`** (repo root) to **generate the snapshot fresh from the live repo**: the full source surface (every `.py`/`.js`/`.css`/`.html`/`.yaml`/`.pmt`, all `.ps1` helpers, the complete build pipeline, docs, skills, tests) plus the small build-required binaries (`.ico`/`.wav`/`.svg`), while omitting heavy media (`.pdf`/`.pptx`/images/videos), `jd-cli.jar`, regenerable state, and all secrets (config keys redacted to `<KEY goes here>`). The snapshot ships `_SOURCE_SNAPSHOT_MANIFEST.json` + `_REBUILD_INSTRUCTIONS.md` — the runbook to restore the omitted binaries/keys from the install root and regenerate `Tlamatini.exe` with `python build.py --self-modify`. The default build **omits** it. The build script prints `Self-modify build : YES/no` so you can confirm which kind of artifact you produced.

`prompt.pmt` instructs the LLM to **verify the directory exists before claiming she can read or edit her own code**; if it is absent she falls back to the injected `<self_knowledge>` map (Section 30.1) for self-description rather than asserting a capability she lacks.

### 30.3 Files involved

| Path | Role |
|---|---|
| `Tlamatini/agent/Tlamatini.md` | First-person self-knowledge map (LLM-only audience; no HTML styling) |
| `Tlamatini/agent/rag/config.py` | `SELF_KNOWLEDGE_FILENAME` / `SELF_KNOWLEDGE_PLACEHOLDER` / `_load_self_knowledge_block()` (brace-escape + fail-open); `load_config_and_prompt()` does the single-site replace |
| `Tlamatini/agent/prompt.pmt` | `<self_knowledge>{self_knowledge}</self_knowledge>` block + CRITICAL SCOPE clause; the verify-directory-exists instruction for self-modification |
| `Tlamatini/agent/rag/utils.py` | `prepend_loaded_context_scope()` — deterministic scope header applied in all four chains so loaded `<context>` wins over `<self_knowledge>` for generic-summary requests |
| `<install_root>/TlamatiniSourceCode/` | OPTIONAL bundled source snapshot; present only with `build.py --self-modify`; carries `_SOURCE_SNAPSHOT_MANIFEST.json` + `_REBUILD_INSTRUCTIONS.md` |
| `copy_source_assets.py` (repo root) | Generates the snapshot: full source + build scripts; media/`jd-cli.jar`/secrets omitted, config secrets redacted to `<KEY goes here>` |
| `build.py` | Ships `Tlamatini.md` (`--add-data` + install-root copy); `--self-modify` flag generates `TlamatiniSourceCode/` via `copy_source_assets.py` (legacy static-copy fallback); prints `Self-modify build : YES/no` |

---

## 31. Nested-Directory Context via Native Picker (2026-05-25)

The chat **Context ▸ Set directory as context** action can now load a project at **ANY depth under the app root**, not just a single leaf folder. The old browser `showDirectoryPicker()` only exposed the chosen folder's leaf name, which broke deep paths; it has been replaced by a **backend native Win32 picker**:

- `views.pick_context_directory_view` + route `pick_context_directory/` open the native Windows folder picker server-side and return the **real absolute path**.
- `path_guard.is_within_application_root()` + `resolve_runtime_agent_path` now accept the application root **OR ANY descendant** of it (previously only the root or its immediate children were valid).
- `agent_page_init.js` fetches the picked path from that endpoint, with a **manual-entry fallback on non-Windows** hosts (where the native Win32 picker is unavailable).

---

*This KIMI.md was generated by deeply analyzing all documentation, source code, skills, and agents in the Tlamatini project. Keep it up-to-date when making architectural changes.*
