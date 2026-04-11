# Tlamatini - CLAUDE.md

This is the authoritative onboarding document for any AI assistant (Claude Code, Cursor, Gemini CLI, Antigravity IDE, etc.) working on the Tlamatini project. Read this file in full before making any changes.

---

## Project Identity

**Tlamatini** is a locally-deployed AI developer assistant built with Django, featuring:

- An advanced **RAG system** (FAISS + BM25, metadata extraction, context budgeting, fallback mode)
- A request-scoped **Multi-Turn orchestration layer** with dynamic tool binding and global execution planning
- A **Visual Agentic Workflow Designer** (ACP) with 57+ drag-and-drop agent types
- **Multi-model LLM support** (Ollama local, Anthropic Claude cloud, Qwen vision)
- A full **PyInstaller packaging pipeline** (build.py -> installer -> standalone .exe)

**Repository**: `https://github.com/XAIHT/Tlamatini.git`
**License**: GPL-3.0
**Primary developer**: Mike (angelahack1)
**Platform**: Windows 11 (primary), bash shell in Claude Code

---

## Quick Orientation

```
Tlamatini/                          # Git root
├── CLAUDE.md                       # THIS FILE
├── README.md                       # Full user-facing documentation (very large)
├── NEW_AGENT_RECOMMENDATIONS.md    # Roadmap for new agents (Tester, Reviewer, etc.)
├── build.py                        # PyInstaller build script
├── build_installer.py              # NSIS-based installer builder
├── build_uninstaller.py            # Uninstaller builder
├── install.py / uninstall.py       # Tkinter GUI installer/uninstaller
├── requirements.txt                # Python deps
├── eslint.config.mjs               # ESLint config
│
├── Tlamatini/                      # Django project root
│   ├── manage.py
│   ├── db.sqlite3
│   ├── .agents/workflows/
│   │   └── create_new_agent.md     # ** SKILL: Step-by-step agent creation guide **
│   ├── .mcps/
│   │   └── create_new_mcp.md       # ** SKILL: MCP/tool creation guide **
│   │
│   ├── tlamatini/                  # Django project config (settings, urls, asgi, middleware)
│   │
│   ├── agent/                      # Core Django app (ALL business logic lives here)
│   │   ├── prompt.pmt              # System prompt template for the chat LLM
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
│   │   │
│   │   ├── rag/                    # RAG system package
│   │   │   ├── factory.py          # Chain builders, MCP context patching
│   │   │   ├── interface.py        # Public API (ask_rag)
│   │   │   ├── chains/             # basic.py, history_aware.py, unified.py
│   │   │   └── ...
│   │   │
│   │   ├── agents/                 # 57+ workflow agent templates
│   │   │   ├── flowcreator/
│   │   │   │   └── agentic_skill.md  # ** SKILL: FlowCreator AI reference **
│   │   │   ├── flowhypervisor/
│   │   │   │   └── monitoring-prompt.pmt  # Flow health monitor prompt
│   │   │   ├── parametrizer/       # Interconnection engine
│   │   │   ├── gatewayer/          # HTTP webhook / folder-drop ingress
│   │   │   ├── gateway_relayer/    # GitHub/GitLab webhook relay
│   │   │   ├── node_manager/       # Infrastructure registry
│   │   │   └── ... (57 total agent directories)
│   │   │
│   │   ├── opus_client/            # Claude API client library
│   │   │   └── claude_opus_client.py
│   │   │
│   │   ├── imaging/                # Dual-backend image analysis (Claude + Qwen)
│   │   ├── services/               # filesystem.py, response_parser.py
│   │   ├── templates/agent/        # HTML templates
│   │   ├── static/agent/
│   │   │   ├── css/                # agentic_control_panel.css, agent_page.css, etc.
│   │   │   ├── js/                 # 23 JS modules (8 chat + 11 ACP + 4 shared)
│   │   │   └── sounds/             # notification.wav, hypervisor_alert.wav
│   │   └── migrations/             # Django migrations
│   │
│   ├── jd-cli/                     # Bundled Java decompiler
│   └── staticfiles/                # Collected static files (WhiteNoise)
```

---

## Architecture Overview

```
Browser (Chat UI / ACP Workflow Designer)
    │ WebSocket (ws://)
    ▼
Django Channels (Daphne ASGI)
    │
    ├── RAG Pipeline (FAISS + BM25 hybrid retrieval, context budgeting)
    ├── Unified Agent (multi-turn tool loop, wrapped agent runtimes)
    └── MCP Services (System-Metrics via WebSocket, Files-Search via gRPC)
    │
    ▼
LLM Backends: Ollama (local) | Anthropic Claude (cloud) | Qwen (vision)
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

---

## Technology Stack

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

## How to Run

```bash
# From source
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

## System Prompt

The chat LLM system prompt lives in `Tlamatini/agent/prompt.pmt`. Key rules:

1. Referenced rephrases must be ignored
2. System context (MCP metrics) is real-time
3. Files context (MCP file search) is real-time
4. Code blocks use `BEGIN-CODE<<<FILENAME>>>` / `END-CODE` format (NOT markdown fences)
5. Context usage: if tools are available (Multi-Turn), use them for ANY request
6. Tables must use HTML, not markdown pipe syntax
7. Responses must end with `END-RESPONSE`
8. Tool-usage rule: in Multi-Turn, the LLM is an OPERATOR, not just an advisor
9. Up to 100 multi-turn iterations available

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
- Includes: execute_command, agent_parametrizer, agent_starter, agent_stopper, agent_stat_getter, launch_view_image, unzip_file, decompile_java, + 32 wrapped chat-agent launchers

---

## Multi-Turn Mode

When **Multi-Turn is checked** in the toolbar:
1. Prompt-shape validation is skipped
2. Request-scoped global execution plan/DAG is built
3. MCP contexts are prefetched selectively
4. Only planned tool subset is bound
5. Wrapped agents launch in headless/background mode

When **unchecked**: legacy one-shot behavior is preserved exactly.

The toggle is per-browser-session, sent as `multi_turn_enabled` with each request.

---

## Unified Section Format (Parametrizer)

All 16+ section-generating agents use a single output format:

```
INI_SECTION_<AGENT_TYPE><<<
key1: value1
key2: value2

multi-line body content (becomes 'response_body')
>>>END_SECTION_<AGENT_TYPE>
```

Rules:
- `<AGENT_TYPE>` = UPPERCASE base name (e.g., APIRER, CRAWLER, GOOGLER)
- KV header before first blank line; body after first blank line
- Each section MUST be emitted in a **single `logging.info()` call** (atomic)
- One section per output unit (N results = N sections)

Registration (3 places):
1. `parametrizer.py` → `SECTION_AGENT_TYPES` list
2. `views.py` → `PARAMETRIZER_SOURCE_OUTPUT_FIELDS` dict
3. `README.md` → Supported Source Agents table

The generic parser (`_parse_section_content` + `_section_regex`) in `parametrizer.py` handles all agents with ~90 lines. No per-agent parser code needed.

Registered source agents: apirer, gitter, kuberneter, crawler, summarizer, prompter, flowcreator, file_interpreter, image_interpreter, file_extractor, kyber_keygen, kyber_cipher, kyber_decipher, gatewayer, gateway_relayer, googler.

---

## Creating a New Agent (Step-by-Step)

**Full guide**: `Tlamatini/.agents/workflows/create_new_agent.md`

### Summary Checklist (8 Steps)

1. **Backend: Agent directory and script**
   - Create `agent/agents/<agent_name>/<agent_name>.py` + `config.yaml`
   - Copy boilerplate from `shoter.py` (PID management, reanimation, helpers)
   - `os.environ['FOR_DISABLE_CONSOLE_CTRL_HANDLER'] = '1'` MUST be first
   - Implement reanimation detection (`_IS_REANIMATED`)
   - If agent generates data for Parametrizer: emit `INI_SECTION_<TYPE><<<` blocks

2. **Backend: Django view for connection updates**
   - Add `update_<agent_name>_connection_view` in `views.py`
   - Register URL in `urls.py`

3. **Backend: Database migration**
   - Create `agent/migrations/<NNNN>_add_<agent_name>.py`
   - Seeds an `Agent` row with `agentDescription` as display name
   - Run `python Tlamatini/manage.py migrate`

4. **Frontend: CSS gradient**
   - Add 4-color gradient in `agentic_control_panel.css`
   - `.canvas-item.<css_class>` normal + hover rules
   - Gradient exists ONLY in CSS (sidebar inherits via `applyAgentToolIconStyle()`)

5. **Frontend: JavaScript (4 files)**
   - `acp-agent-connectors.js`: Add fetch connector function
   - `acp-canvas-core.js`: 6 locations (classMap, AGENTS_NEVER_START_OTHERS, removeConnection, removeConnectionsFor, mouseup handler)
   - `acp-canvas-undo.js`: Undo/redo handlers
   - `acp-file-io.js`: .flw load handlers

6. **Documentation: Update `agentic_skill.md`**
   - Add agent entry so FlowCreator AI can use it

7. **Documentation: Update `README.md`**
   - Agent count, project structure, classification, workflow table, glossary, changelog, API table

8. **Quality: Lint**
   - `python -m ruff check` (fix all)
   - `npm run lint` (fix errors only)

### Critical Naming Convention

The `agentDescription` from DB is the single source of truth. It transforms differently per context:

| Context | Transform | "Node Manager" | "Shoter" |
|---|---|---|---|
| CSS classMap key | `name.toLowerCase().replace(/\s+/g, '-')` | `'node-manager'` | `'shoter'` |
| Sidebar visual | Same as classMap via `getAgentTypeClass()` | `'node-manager'` | `'shoter'` |
| Connection handlers | `name.toLowerCase()` (preserves spaces) | `'node manager'` | `'shoter'` |

### Agent Lifecycle

- **Fresh start**: No `AGENT_REANIMATED` env var -> log truncated -> "STARTED"
- **Reanimation** (pause/resume): `AGENT_REANIMATED=1` -> log NOT truncated -> "REANIMATED" -> reanim files loaded
- PID file written on start, removed in `finally` block
- Concurrency guard: `wait_for_agents_to_stop(target_agents)` before starting downstream
- Ender clears all `reanim*` files on stop

### Connection Fields

- `target_agents: []` - agents to START after finishing (active agents)
- `source_agents: []` - agents whose logs to MONITOR
- `output_agents: []` - only for Stopper/Ender/Cleaner (canvas wiring, not starting)
- Special: OR/AND use `source_agent_1`, `source_agent_2`; Asker/Forker use `target_agents_a`, `target_agents_b`; Counter uses `target_agents_l`, `target_agents_g`

---

## Creating a New MCP or Tool

**Full guide**: `Tlamatini/.mcps/create_new_mcp.md`

### First Decision: Classify the request

| Type | Description | Example |
|------|-------------|---------|
| **Tool only** | Model performs an action on demand during unified-agent execution | run command, start agent, unzip, decompile |
| **MCP-backed context provider only** | System fetches context before the main chain responds | system metrics, file search, inventory |
| **Both** | Needs pre-fetched context AND a separate action tool | Rare - most are one or the other |

### Tool-Only Workflow
1. Implement `@tool` function in `tools.py` (sync, returns strings)
2. Resolve bundled paths for both frozen and source modes
3. Register in `get_mcp_tools()` under a `global_state` gate
4. Seed a `Tool` row via new migration
5. Frontend: usually NO changes needed (tool UI is dynamic)
6. Only usable in unified-agent mode

### MCP Context Provider Workflow
1. Create `mcp_<name>_server.py` + `mcp_<name>_client.py`
2. Create sidecar chain `chain_<name>_lcel.py`
3. Wire startup in `apps.py` + `startserver.py`
4. Extend `factory.py` (import, sync wrapper, status key mapping, patched invoke)
5. Choose payload field and update all main chains
6. Seed `Mcp` row + update frontend MCP checkboxes (hardcoded, not dynamic!)
7. Verify persistence and reconnect behavior

### Key Warnings
- `factory.py` recognizes ONLY `System-Metrics` and `Files-Search` by description
- MCP UI is hardcoded for two checkboxes (unlike dynamic tool UI)
- `get_mcp_tools()` returns LangChain tools, NOT MCP services
- Tool status keys are handwritten and can drift from seeded DB descriptions
- Adding `Mcp` row without extending `factory.py` does NOTHING

---

## All 57 Workflow Agent Types

### Control Agents
- **Starter** - Entry point, launches first agents
- **Ender** - Terminates all agents, launches Cleaners. `target_agents` = agents to KILL, `output_agents` = agents to LAUNCH after, `source_agents` = graphical only
- **Stopper** - Kills specific agents based on log patterns
- **Cleaner** - Deletes logs/PIDs after Ender
- **Sleeper** - Waits N ms then starts next
- **Croner** - Scheduled trigger (HH:MM format)

### Routing Agents
- **Raiser** - Watches source log for pattern, starts downstream when found
- **Forker** - Auto-routes to Path A or B based on two patterns
- **Asker** - Interactive A/B choice for user
- **Counter** - Persistent counter, routes L (< threshold) or G (>= threshold)

### Logic Gates
- **OR** - Fires when EITHER of 2 sources completes (2 inputs, 1 output)
- **AND** - Fires when BOTH of 2 sources complete (2 inputs, 1 output)
- **Barrier** - Fires when ALL N sources complete (generalized AND)

### Action Agents
- **Executer** - Shell commands
- **Pythonxer** - Inline Python (exit code gating)
- **Prompter** - LLM prompt execution
- **Summarizer** - LLM text/log summarization
- **Crawler** - Web crawling with LLM analysis
- **Googler** - Google search + text extraction (Playwright)
- **Apirer** - HTTP REST API calls
- **Gitter** - Git operations
- **Ssher** - SSH remote commands
- **Scper** - SCP file transfer
- **Dockerer** - Docker commands
- **Kuberneter** - kubectl commands
- **Pser** - PowerShell commands
- **Jenkinser** - Jenkins job triggers
- **Sqler** - SQL queries (external window)
- **Mongoxer** - MongoDB operations (external window)
- **Mover** - File move/copy with glob patterns
- **Deleter** - File deletion with glob patterns
- **Shoter** - Screenshot capture
- **Mouser** - Mouse/keyboard simulation (PyAutoGUI)
- **Keyboarder** - Keyboard typing / hotkey automation
- **File-Creator** - Creates files with specified content
- **File-Interpreter** - LLM reads and interprets file contents
- **File-Extractor** - Raw text extraction (PDF, DOCX, etc.)
- **Image-Interpreter** - LLM vision analysis
- **J-Decompiler** - JAR/WAR decompilation (bundled jd-cli)
- **Telegramer** - Sends Telegram messages

### Cryptography Agents
- **Kyber-KeyGen** - CRYSTALS-Kyber key pair generation (post-quantum)
- **Kyber-Cipher** - Kyber encryption
- **Kyber-DeCipher** - Kyber decryption

### Utility Agents
- **Parametrizer** - Maps structured output from one agent into another's config.yaml (strict single-lane queue)
- **FlowBacker** - Backs up session logs/configs
- **Gatewayer** - HTTP webhook ingress + folder-drop watcher
- **Gateway-Relayer** - Bridges GitHub/GitLab webhooks into Gatewayer
- **Node-Manager** - Infrastructure registry and node supervision

### Terminal/Monitoring Agents (do NOT start downstream)
- **Monitor-Log** - LLM-powered log file monitor
- **Monitor-Netstat** - LLM-powered network port monitor
- **Emailer** - SMTP email on pattern detection
- **RecMailer** - IMAP email receiver/monitor
- **Notifier** - Desktop notification + sound
- **Whatsapper** - WhatsApp messages (TextMeBot)
- **TelegramRX** - Telegram message receiver
- **FlowHypervisor** - LLM-powered flow health monitor (system agent)

---

## FlowCreator AI Skill

The FlowCreator agent uses `agentic_skill.md` to design flows. Key design principles:

1. **Minimize agents** - Fewest agents to accomplish the objective
2. **Sequential chains over parallel fan-out** - Chain agents one-by-one
3. **Starter should be lean** - Only start first agent(s)
4. **Terminal agents at END** - Never start Emailer/Notifier from Starter
5. **Raiser for exceptions** - Don't create Raisers for both sides of binary checks
6. **Parametrizer is a strict single-lane queue** - One source, one target, one-at-a-time

### Common Flow Patterns

```
# Linear chain
Starter -> A -> B -> C -> Ender

# Polling loop with exception
Starter -> A -> Sleeper -> A (loop)
           └-> Raiser (watches for exit condition) -> Alert -> Ender

# Parametrized pipeline
Starter -> Source_Agent -> Parametrizer -> Target_Agent -> Ender

# Fork-join
Starter -> A -> AND_Gate -> C -> Ender
       └-> B ----┘

# Conditional branching
Starter -> A -> Forker -> [path A] B -> Ender
                       -> [path B] C -> Ender

# Clean shutdown with backup
... -> Ender -> FlowBacker -> Cleaner
```

---

## FlowHypervisor Monitoring

The FlowHypervisor (`monitoring-prompt.pmt`) is a watchdog that outputs exactly:
- `OK` - flow is healthy
- `ATTENTION NEEDED { explanation }` - problem detected

Diagnostic checks (in order):
1. User timing constraints vs FLOW ELAPSED TIME
2. Critical errors (FATAL, CRASH, Failed to start agent)
3. Stuck agents (short-lived > 5min with no output)
4. Broken chains (agent finished but downstream never started)
5. Previous alert still valid?

Normal things NOT to flag: FlowHypervisor/FlowCreator activity, Sqler/Mongoxer missing logs, long-running agents running long, "REANIMATED" markers, Parametrizer queue progress messages.

---

## Claude API Client (opus_client)

Located in `agent/opus_client/claude_opus_client.py`. Features:
- Text chat, image analysis, PDF analysis, streaming
- Multi-turn conversations with `create_conversation()`
- Tool/function calling with auto-execution
- Models: `Model.OPUS_4_5`, `Model.SONNET_4_5`, `Model.HAIKU_4_5`

```python
from claude_opus_client import ClaudeClient
client = ClaudeClient()
response = client.chat("Hello")
```

---

## Building & Packaging

```bash
# Step 1: Build the app
python build.py

# Step 2: Build the uninstaller
python build_uninstaller.py

# Step 3: Build the installer
python build_installer.py
```

The frozen build resolves paths via `os.path.dirname(sys.executable)` vs source mode `os.path.dirname(os.path.abspath(__file__))`. Both modes must be supported in any new tool.

---

## Linting

```bash
# Python
python -m ruff check

# JavaScript/CSS
npm run lint
```

---

## Database Models (13 models in agent/models.py)

Key models:
- `Agent` - Agent type registry (idAgent, agentName, agentDescription, agentContent)
- `Mcp` - MCP UI toggle rows (enable/disable context providers)
- `Tool` - Tool UI toggle rows (enable/disable unified-agent tools)
- `ChatHistory` - Chat message history
- Plus session, context, and configuration models

---

## Frontend Architecture

### Chat Interface (8 modules)
- `agent_page_init.js` - WebSocket setup, app initialization
- `agent_page_chat.js` - Chat message handling
- `agent_page_canvas.js` - Code canvas rendering
- `agent_page_context.js` - RAG context management
- `agent_page_dialogs.js` - Modal dialogs
- `agent_page_layout.js` - UI layout
- `agent_page_state.js` - Client state
- `agent_page_ui.js` - General UI utilities

### ACP Workflow Designer (11 modules)
- `agentic_control_panel.js` - Entry point
- `acp-globals.js` - Shared global state
- `acp-canvas-core.js` - Canvas rendering, drag-and-drop, classMap, connection handlers
- `acp-canvas-undo.js` - Undo/redo state (1024 actions)
- `acp-agent-connectors.js` - 50+ agent connection handlers
- `acp-control-buttons.js` - Start/stop/pause/hypervisor
- `acp-file-io.js` - .flw save/load
- `acp-running-state.js` - LED indicators, process monitoring
- `acp-session.js` - Session pool management
- `acp-layout.js` - Canvas layout utilities
- `acp-validate.js` - Flow validation engine

### Shared
- `canvas_item_dialog.js` - Agent config dialog on canvas
- `contextual_menus.js` - Right-click menus
- `tools_dialog.js` - Tool enable/disable dialog
- `acp-undo-manager.js` - Undo stack manager

---

## Known Hardcoded Assumptions

1. `factory.py` recognizes only `System-Metrics` and `Files-Search` by Mcp description
2. Frontend MCP dialog is hardcoded for two checkboxes
3. Tool UI is dynamic; MCP UI is not
4. `get_mcp_tools()` returns LangChain tools, not MCP services
5. `ask_rag()` does not fetch MCP data itself
6. Files-Search main path uses `FileSearchRAGChain`, not `mcp_files_search_client.py`
7. `mcp_files_search_client_uri` in config is unused by the main chain
8. `FileSearchRAGChain` falls back to `localhost:50051` for gRPC
9. Tool status keys are handwritten and can drift
10. `mcpContent` is stored as string, not boolean

---

## Recommended New Agents (Roadmap)

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

## Work Style Preferences (for AI assistants)

- When given a broad directive ("Go!", "modify everything"), execute comprehensively across all relevant files without asking for confirmation at each step
- Use parallel subagents to maximize throughput
- Read broadly first, plan the full scope, then execute in parallel batches
- Only ask for confirmation on truly ambiguous architectural decisions
- The developer values robustness ("bullet-proof") and uniformity in system design
- Comfortable with large cross-cutting changes (16+ files in one session)
