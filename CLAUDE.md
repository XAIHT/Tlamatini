# Tlamatini - CLAUDE.md

This is the authoritative onboarding document for any AI assistant (Claude Code, Cursor, Gemini CLI, Antigravity IDE, etc.) working on the Tlamatini project. Read this file in full before making any changes, then follow the `@docs/claude/*.md` imports below — each specialized file is automatically included in your context.

---

## Project Identity

**Tlamatini** is a locally-deployed AI developer assistant built with Django, featuring:

- An advanced **RAG system** (FAISS + BM25, metadata extraction, context budgeting, fallback mode)
- A request-scoped **Multi-Turn orchestration layer** with dynamic tool binding and global execution planning
- A **Visual Agentic Workflow Designer** (ACP) with 59 drag-and-drop agent types
- **ACPX runtime** (Agent Communication Protocol eXtension) — spawns external coding-agent CLIs (Claude Code, Codex, Cursor, Gemini, Qwen, Kiro/Kimi/iFlow/Kilocode/OpenCode/Pi/Droid/Copilot, and a Tlamatini self-host) as out-of-process children, brokered to the LLM as 12 `acp_*` tools and to the canvas as the visual **ACPXer** agent. Toolbar checkbox **ACPX** filters the entire ACPX/Skills tool surface in or out per-request
- **Skills system** — markdown-defined `SKILL.md` packages run by `SkillHarness`. The LLM invokes them through `list_skills` / `invoke_skill`. Built-in skills include `acp-router`, `summarize`, `setup-new-acpx-key`, `skill-creator`, `tlamatini_*` (audit / lint / refactor helpers), and integration stubs (gmail, slack, github, jira, notion, todoist, trello, weather)
- **Multi-model LLM support** (Ollama local, Anthropic Claude cloud, Qwen vision)
- A full **PyInstaller packaging pipeline** (build.py -> installer -> standalone .exe)

**Repository**: `https://github.com/XAIHT/Tlamatini.git`
**License**: GPL-3.0
**Primary developer**: angelahack1
**Platform**: Windows 11 (primary), bash shell in Claude Code

**Demo videos** (linked from README.md):
- First system-usage walkthrough: `https://www.youtube.com/watch?v=CkvDPSd_c-g`
- Loading a complete project and summarizing its source code: `https://www.youtube.com/watch?v=Lrpbt_dPIXw`
- Installing OpenCV end-to-end in Multi-Turn: `https://www.youtube.com/watch?v=bBlqbZVK-Wk`

---

## Quick Orientation

```
Tlamatini/                          # Git root
├── CLAUDE.md                       # THIS FILE (short entry point + import manifest)
├── docs/claude/                    # Specialized onboarding docs (auto-imported below)
│   ├── INDEX.md                    # Map of what lives in each file
│   ├── architecture.md             # Config, Five Layers, app log, DB models
│   ├── multi-turn.md               # Multi-Turn mode, Create Flow, Parametrizer sections
│   ├── exec-report.md              # Exec Report pipeline + ordering contract
│   ├── agents.md                   # Agent creation, 59-type catalog, FlowCreator, FlowHypervisor
│   ├── mcp-tools.md                # Creating a new MCP or tool
│   ├── frontend.md                 # Chat + ACP modules, Canvas DOM contract
│   └── gotchas.md                  # Claude API client, build/lint, hardcoded assumptions, recent fixes
├── README.md                       # Full user-facing documentation (very large)
├── ACPX.md                         # Standalone ACPX overview / OpenClaw compatibility note
├── build.py                        # PyInstaller build script
├── build_installer.py              # NSIS-based installer builder
├── build_uninstaller.py            # Uninstaller builder
├── install.py / uninstall.py       # Tkinter GUI installer/uninstaller
├── regen_secrets.py                # Toggle config.json between push-able placeholders and keyed values via data.keys
├── data.keys                       # Gitignored secrets vault (KEY=VALUE lines)
├── CreateShortcut.ps1              # User-Start-Menu shortcut helper (works under restrictive policies)
├── register_flw.ps1                # .flw file association helper
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
│   │   ├── config.json             # LLM and RAG configuration (acpx.agents.<id>.env injects child env)
│   │   ├── config_loader.py        # Frozen/source-aware config reader
│   │   ├── views.py                # 100+ HTTP endpoints
│   │   ├── consumers.py            # WebSocket consumer (async chat handler)
│   │   ├── models.py               # 13 database models
│   │   ├── urls.py                 # URL routing
│   │   ├── tools.py                # LangChain @tool definitions and wrapped chat-agent launchers
│   │   ├── mcp_agent.py            # MCP unified agent builder and multi-turn executor; _EXEC_REPORT_TOOLS map
│   │   ├── global_execution_planner.py  # Request-scoped DAG planner (ACPX co-selection rules)
│   │   ├── capability_registry.py  # Request-scoped capability scoring (ACPX signal tokens)
│   │   ├── chat_agent_registry.py  # Wrapped chat-agent tool registry (chat_agent_summarize_text, ...)
│   │   ├── chat_agent_runtime.py   # Wrapped-runtime lifecycle helpers
│   │   ├── global_state.py         # Thread-safe singleton (Singleton pattern)
│   │   │
│   │   ├── acpx/                   # ACPX runtime — agent_registry, runtime, tools, session_store, permissions
│   │   │   ├── agent_registry.py   # DEFAULT_ACP_AGENTS (claude/codex/cursor/gemini/qwen/tlamatini/...) + transports
│   │   │   ├── runtime.py          # AcpxRuntime, AcpSession, transport-aware drain, oneshot-prompt path
│   │   │   ├── tools.py            # 12 LangChain @tool functions (acp_spawn / acp_send / acp_relay / ...)
│   │   │   ├── session_store.py    # FileSessionStore (NDJSON transcripts)
│   │   │   ├── windows_spawn.py    # Windows-aware command resolution
│   │   │   └── tests.py            # 60+ unit tests
│   │   │
│   │   ├── skills/                 # Skill harness, registry, frontmatter parser, IO contract
│   │   │   ├── registry.py         # Discovers SKILL.md packages from skills_pkg/
│   │   │   ├── harness.py          # Sandboxed runner for invoke_skill(...)
│   │   │   └── io_contract.py      # Skill input/output contract validators
│   │   │
│   │   ├── skills_pkg/             # SKILL.md packages (acp_router, summarize, setup_new_acpx_key, ...)
│   │   │   ├── _meta/              # JSON schema + lint helpers
│   │   │   ├── acp_router/SKILL.md
│   │   │   ├── summarize/SKILL.md
│   │   │   ├── setup_new_acpx_key/SKILL.md
│   │   │   ├── skill_creator/SKILL.md
│   │   │   ├── tlamatini_*/SKILL.md  # Audit / lint / refactor helpers (planner trace replay, csrf audit, ...)
│   │   │   └── github|gmail|slack|jira|notion|todoist|trello|weather/SKILL.md
│   │   │
│   │   ├── rag/                    # RAG system package
│   │   │   ├── factory.py          # Chain builders, MCP context patching
│   │   │   ├── interface.py        # Public API (ask_rag); persists last_exec_report_*, last_acpx_enabled
│   │   │   ├── chains/             # basic.py, history_aware.py, unified.py
│   │   │   └── ...
│   │   │
│   │   ├── agents/                 # 59 workflow agent templates
│   │   │   ├── flowcreator/
│   │   │   │   └── agentic_skill.md  # ** SKILL: FlowCreator AI reference **
│   │   │   ├── flowhypervisor/
│   │   │   │   └── monitoring-prompt.pmt  # Flow health monitor prompt
│   │   │   ├── parametrizer/       # Interconnection engine
│   │   │   ├── gatewayer/          # HTTP webhook / folder-drop ingress
│   │   │   ├── gateway_relayer/    # GitHub/GitLab webhook relay
│   │   │   ├── node_manager/       # Infrastructure registry
│   │   │   ├── teletlamatini/      # Telegram bridge into the full Multi-Turn Tlamatini chat
│   │   │   ├── whatstlamatini/     # WhatsApp Cloud API bridge into the full Multi-Turn Tlamatini chat
│   │   │   ├── acpxer/             # Visual canvas counterpart of the 12 ACPX tools
│   │   │   └── ... (59 total agent directories)
│   │   │
│   │   ├── opus_client/            # Claude API client library
│   │   │   └── claude_opus_client.py
│   │   │
│   │   ├── imaging/                # Dual-backend image analysis (Claude + Qwen)
│   │   ├── services/               # filesystem.py, response_parser.py, answer_analizer.py
│   │   ├── doc_generation/         # refresh_project_docs.py, mardown_to_pdf.py
│   │   ├── templates/agent/        # HTML templates (toolbar has Multi-Turn / Exec-Report / ACPX checkboxes)
│   │   ├── static/agent/
│   │   │   ├── css/                # agentic_control_panel.css, agent_page.css, tools_dialog.css, etc.
│   │   │   ├── js/                 # 26 JS modules (8 chat + 12 ACP + 1 ACP entry + 5 shared incl. chat_page_runtime_poller.js, shared-runtime-dialogs.js, canvas_item_dialog.js, contextual_menus.js, tools_dialog.js)
│   │   │   ├── img/Tlamatini.ico   # App icon (web pages + console window + .exe)
│   │   │   └── sounds/             # notification.wav, hypervisor_alert.wav
│   │   └── migrations/             # Django migrations (latest: 0081_add_window_present_and_run_wait_tools)
│   │
│   ├── manage.py                   # Django entrypoint; tees stdout/stderr into tlamatini.log; sets console window title + icon
│   ├── tlamatini.log               # Unified application log (console + Django loggers)
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
1. User sends message via WebSocket (optionally with `multi_turn_enabled`, `exec_report_enabled`, `acpx_enabled`)
2. `AgentConsumer` receives and routes
3. Context determination (RAG loaded?)
4. Internet check (classify if web search needed)
5. Chain selection (RAG / Basic / Unified Agent)
6. Multi-Turn gate: checked = planner/dynamic binding; unchecked = legacy one-shot
7. ACPX gate: when `acpx_enabled=False`, `agent.acpx.filter_acpx_tools()` strips every ACPX/Skill tool name from the bound tool list before the planner / executor see them, forcing the system back onto its legacy Multi-Turn / one-shot behavior
8. Context prefetch (system/file MCP)
9. Execution loop (tool calls, wrapped agent monitoring, ACPX child-process drain)
10. Streaming response via WebSocket; on success, the chat header renders a **Create Flow** button that converts the executed tool-call log into a downloadable `.flw`

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

## Specialized Docs (auto-imported)

The rest of the onboarding material is split into topic files under `docs/claude/`. Each `@` line below is imported by Claude Code into your context automatically, so treat the full set as a single document. See `docs/claude/INDEX.md` for one-line descriptions of each file.

- **Architecture & core systems** — config, system prompt & identity, the Five Layers, application log, doc generation, database models: @docs/claude/architecture.md
- **Multi-Turn, Create Flow, Parametrizer** — Multi-Turn mode, short follow-up scoring, Create-Flow pipeline, `INI_SECTION_*` format: @docs/claude/multi-turn.md
- **Exec Report** — per-agent execution tables, capture/render pipeline, strict ordering contract, styling, adding new agents: @docs/claude/exec-report.md
- **Agents** — creating a new agent (8-step), naming conventions, lifecycle, all 59 agent types, FlowCreator, FlowHypervisor: @docs/claude/agents.md
- **ACPX** — definition, agent registry, 12 LLM-facing tools, transport profiles, canonical flows, runtime mechanics, ACPX toolbar toggle, "when the user says ACPX" decision matrix: @docs/claude/acpx.md
- **MCPs & Tools** — tool-only vs MCP context provider workflows, Skills system (SKILL.md packages), key warnings: @docs/claude/mcp-tools.md
- **Frontend** — chat modules, ACP modules, ACP Canvas DOM Contract: @docs/claude/frontend.md
- **Gotchas & reference** — Claude API client, build/lint, hardcoded assumptions, recent fixes, roadmap, work-style preferences: @docs/claude/gotchas.md
