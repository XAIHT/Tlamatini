# Tlamatini - CLAUDE.md

This is the authoritative onboarding document for any AI assistant (Claude Code, Cursor, Gemini CLI, Antigravity IDE, etc.) working on the Tlamatini project. Read this file in full before making any changes, then follow the `@docs/claude/*.md` imports below — each specialized file is automatically included in your context.

---

## Project Identity

**Tlamatini** is a locally-deployed AI developer assistant built with Django, featuring:

- An advanced **RAG system** (FAISS + BM25, metadata extraction, context budgeting, fallback mode)
- A request-scoped **Multi-Turn orchestration layer** with dynamic tool binding and global execution planning
- A **Visual Agentic Workflow Designer** (ACP) with 74 drag-and-drop agent types
- A **backend Flow Compiler + Agent Contract registry** (`agent/services/flow_compiler.py`, `agent/services/agent_contracts.py`) that turns the live ACP canvas snapshot OR a Chat-generated Create-Flow draft into validated, redacted, source-and-frozen-portable `config.yaml` files in the session pool — exposed over `/agent/compile_flow/`, `/agent/flow_from_tool_calls/`, and `/agent/agent_contracts/`
- **ACPX runtime** (Agent Communication Protocol eXtension) — spawns external coding-agent CLIs (Claude Code, Codex, Cursor, Gemini, Qwen, Kiro/Kimi/iFlow/Kilocode/OpenCode/Pi/Droid/Copilot, and a Tlamatini self-host) as out-of-process children, brokered to the LLM as 12 `acp_*` tools and to the canvas as the visual **ACPXer** agent. Toolbar checkbox **ACPX** filters the entire ACPX/Skills tool surface in or out per-request
- **Skills system** — markdown-defined `SKILL.md` packages run by `SkillHarness`. The LLM invokes them through `list_skills` / `invoke_skill`. Built-in skills include `acp-router`, `summarize`, `setup-new-acpx-key`, `skill-creator`, `flow-making` (turn a plain objective into a canvas-loadable `.flw` by wrapping the FlowCreator engine — ships `scripts/make_flow.py` + `scripts/result_to_flw.py`; supersedes the legacy `tlamatini-flow-from-objective`), `code-review`, `security-audit`, `kali-pentest` (authorized Kali Linux / MCP-Kali-Server assessment runbook driving the Kalier agent), `tlamatini_*` (audit / lint / refactor helpers), and integration stubs (gmail, slack, github, jira, notion, todoist, trello, weather). Administered through the **ACPX-Skills navbar dropdown** (Browse / Configure / Diagnostics / Reload — 2026-05-17): Browse and Diagnostics are HTTP-backed read-only inspection; Configure mirrors the existing Mcps/Agents/Tools WebSocket toggle pattern (`set-skills` → `Skill.enabled`); Reload re-runs `boot_skills()` so disk edits show up without a server restart. The DB stays at "enumeration + enable/disable" only — permissions/budgets/body live in SKILL.md on disk
- **Self-Knowledge & Self-Modification** (2026-05-25) — the LLM carries a first-person self-reference file, `agent/Tlamatini.md`, injected into `prompt.pmt`'s `<self_knowledge>` block at prompt-build time by `agent/rag/config.py` (covers every chain; brace-escaped; fails open). An OPTIONAL `agent/TlamatiniSourceCode/` directory — bundled only by `build.py --self-modify` — holds her own source so she can read/modify herself: present = a "self-able-modify" build, absent = "not-self-able-modify". See `docs/claude/architecture.md`
- **Multi-model LLM support** (Ollama local, Anthropic Claude cloud, Qwen vision)
- A full **PyInstaller packaging pipeline** (build.py -> installer -> standalone .exe; `--self-modify` ships the self-source tree)

**Repository**: `https://github.com/XAIHT/Tlamatini.git`
**License**: GPL-3.0
**Primary developer**: angelahack1
**Platform**: Windows 11 (primary), bash shell in Claude Code

**Demo videos** (linked from README.md):
- First system-usage walkthrough: `https://www.youtube.com/watch?v=CkvDPSd_c-g`
- Loading a complete project and summarizing its source code: `https://www.youtube.com/watch?v=Lrpbt_dPIXw`
- Installing OpenCV end-to-end in Multi-Turn: `https://www.youtube.com/watch?v=bBlqbZVK-Wk`

---

## ⚠️ Agent Naming Convention (CRITICAL — never mis-case a display name)

The single source of truth for an agent's name is its **`agentDescription`** DB field (seeded by the agent's migration). `agentic_control_panel.html` renders it **verbatim** as the sidebar/canvas label (via `consumers.agent_establishment(...)`), so the **display name must keep its exact intended casing**. Derive every other surface by lowercasing.

| Context | Casing | `STM32er` example |
|---|---|---|
| **Display** — DB `agentDescription`, canvas/sidebar label, tooltips, `agents_descriptions.md` `\| **Name** \|`, `chat_agent_registry.display_name`, docs prose, the agent's `"<Name> AGENT STARTED"` log | **exact, as designed** | `STM32er` |
| Pool/agent dir, `<name>.py`, pool name `<name>_N` | lowercase | `agents/stm32er/`, `stm32er_1` |
| CSS `.canvas-item.<x>-agent`, JS classMap key, `name.toLowerCase()` connection checks | lowercase / dash | `stm32er-agent`, `'stm32er'` |
| JS connector symbol `update<Name>Connection` (code identifier, not a label) | PascalCase-ish | `updateStm32erConnection` |
| `INI_SECTION_<TYPE>` / `END_SECTION_<TYPE>` tokens + FlowHypervisor `<TYPE> SPECIAL NOTES:` headers | **ALL-CAPS** (separate convention — do NOT "fix") | `INI_SECTION_STM32ER` |

**STM32er** is mission-critical (robot firmware) and the user is emphatic: its display name is exactly `S T M 3 2 e r` → **`STM32er`**, NEVER `STM32Er` / `STM32ER` / `Stm32Er` / `Stm32er`. Full reference: the project skill **`tlamatini-agent-naming`** (`.claude/skills/tlamatini-agent-naming/SKILL.md`) and `Tlamatini/.agents/workflows/create_new_agent.md`. Tlamatini's own `SKILL.md` packages auto-load at app start via `agent/acpx/service.py::boot_skills()` (called from `apps.AgentConfig.ready()`); the `tlamatini-agent-naming` Claude Code skill is discovered at session start from `.claude/skills/`.

---

## ⚠️ Use ONLY Tlamatini's Agents When Asked (MANDATORY)

When the user asks to **"use Tlamatini's agents"** — or names any pool agent (**Executer, Pythonxer, Playwrighter, Shoter, Mouser, Keyboarder, Kalier, STM32er**, … any of the 70) — you **MUST** perform the work with **only Tlamatini's pool agents**, never Claude Code's own built-in tools. Your shell is **only the launcher**: copy the agent to an isolated runtime dir, write a tailored `config.yaml`, run `python <agent>.py`; the agent does the work and writes its result to `<agent_dir_basename>.log`. For **visible / desktop** agents (a headed Playwrighter browser, an Executer/Pythonxer `execute_forked_window` console, Shoter/Mouser/Keyboarder) launch in the **foreground with `dangerouslyDisableSandbox: true`** so the window renders on the user's real desktop — the Bash sandbox otherwise hides the GUI in an isolated window station (it reports `WinSta0` but isn't visible), and `run_in_background` detaches it entirely. Do **NOT** substitute your own Bash / Read / Write / Playwright for the agents' job. This rule is re-injected at **every session start** by `.claude/hooks/announce_skills.py` (the SessionStart hook wired in `.claude/settings.json`). Full mechanics: memory `feedback_run_tlamatini_agents_visible`.

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
│   ├── agents.md                   # Agent creation, 72-type catalog, FlowCreator, FlowHypervisor
│   ├── mcp-tools.md                # Creating a new MCP or tool
│   ├── frontend.md                 # Chat + ACP modules, Canvas DOM contract
│   ├── gotchas.md                  # Claude API client, build/lint, versioning, hardcoded assumptions, roadmap, work-style
│   └── recent-fixes.md             # ** NOT auto-imported ** — dated "do NOT revert" fix log; consult before touching the named subsystems
├── README.md                       # Full user-facing documentation (very large)
├── agents_descriptions.md          # ** Authoritative source for sidebar agent tooltips & canvas Description dialogs ** — Django view parses the `## Workflow Agents` tables and injects them into the page as `agent_purpose_map`. README.md is kept as a legacy fallback only
├── ACPX.md                         # Standalone ACPX overview / OpenClaw compatibility note
├── BookOfTlamatini.md              # Long-form narrative changelog / "Recent Updates" book (separate from README.md since 16b789a)
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
│   │   ├── prompt.pmt              # System prompt template for the chat LLM (has the {self_knowledge} placeholder)
│   │   ├── Tlamatini.md            # ** LLM SELF-KNOWLEDGE ** — injected into prompt.pmt's <self_knowledge> block at prompt-build time (rag/config.py); resolved beside prompt.pmt in both modes
│   │   ├── TlamatiniSourceCode/    # ** OPTIONAL self-modify source tree ** — bundled only by `build.py --self-modify`; present = self-able-modify build, absent = not-self-able-modify
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
│   │   ├── exec_permission.py      # Ask-Execs permission broker (sync executor ↔ async consumer bridge; blocking Proceed/Deny)
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
│   │   │   ├── flow_making/SKILL.md  # objective → .flw (wraps FlowCreator); ships scripts/{make_flow,result_to_flw}.py + references/flw_schema.md
│   │   │   ├── tlamatini_*/SKILL.md  # Audit / lint / refactor helpers (planner trace replay, csrf audit, flow_from_objective → delegates to flow-making, ...)
│   │   │   └── github|gmail|slack|jira|notion|todoist|trello|weather/SKILL.md
│   │   │
│   │   ├── rag/                    # RAG system package
│   │   │   ├── factory.py          # Chain builders, MCP context patching
│   │   │   ├── interface.py        # Public API (ask_rag); persists last_exec_report_*, last_acpx_enabled
│   │   │   ├── chains/             # basic.py, history_aware.py, unified.py
│   │   │   └── ...
│   │   │
│   │   ├── agents/                 # 74 workflow agent templates
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
│   │   │   ├── playwrighter/       # Scripted interactive browser automation (Playwright; canvas + chat_agent_playwrighter)
│   │   │   ├── windower/           # Window manager (Win32 focus/move/resize/min/max/close/tile/list; canvas + chat_agent_windower)
│   │   │   ├── kalier/             # Kali Linux offensive-security bridge (MCP-Kali-Server HTTP API; canvas + chat_agent_kalier)
│   │   │   ├── stm32er/            # STM32 firmware bridge — zero-config auto-bootstrap of the STM32 Template Project MCP + fail-safe hardware preflight (canvas + chat_agent_stm32er)
│   │   │   ├── esp32er/            # ESP32 firmware bridge — direct PlatformIO `pio` CLI (no MCP server), zero-config get-platformio.py auto-bootstrap + fail-safe preflight (canvas + chat_agent_esp32er)
│   │   │   ├── arduiner/           # Arduino firmware bridge — direct `arduino-cli` CLI (no MCP server), zero-config binary auto-bootstrap + auto-core-install + fail-safe preflight; ships ArduinoTemplateProject scaffold (canvas + chat_agent_arduiner)
│   │   │   ├── camcorder/          # Webcam capture (OpenCV) — photo (default) / video; native-resolution-by-default; saves to Pictures/TlamatiniCamcorder; observational sibling of Shoter (canvas + chat_agent_camcorder)
│   │   │   ├── recorder/           # Microphone / audio-input capture (sounddevice) — WAV; native-sample-rate-by-default (sample_rate:0); default mic with optional device_index/device_name; saves to Music/TlamatiniRecords; observational audio sibling of Camcorder/Shoter (canvas + chat_agent_recorder)
│   │   │   ├── audioplayer/        # Audio-file PLAYBACK to speakers (soundfile decode + sounddevice stream) — volume_percent, time_played truncate/loop via streaming callback, sample_rate:0=file-native; playback counterpart of Recorder; observational/output → not in Exec Report (canvas + chat_agent_audioplayer)
│   │   │   ├── videoplayer/        # Video-file PLAYBACK WITH audio on a chosen display (ffpyplayer [bundles ffmpeg+SDL via pip] + OpenCV window; silent-cv2 fallback) — display_index, volume_percent, time_played truncate/loop, window size/fullscreen/keep_aspect; on-screen sibling of AudioPlayer; observational/output → not in Exec Report (canvas + chat_agent_videoplayer)
│   │   │   └── ... (74 total agent directories)
│   │   │
│   │   ├── opus_client/            # Claude API client library
│   │   │   └── claude_opus_client.py
│   │   │
│   │   ├── imaging/                # Dual-backend image analysis (Claude + Qwen)
│   │   ├── services/               # filesystem.py, response_parser.py, answer_analizer.py, agent_contracts.py, agent_paths.py, flow_spec.py, flow_compiler.py
│   │   │   ├── agent_contracts.py  # AgentContract registry — per-agent connection-field shape, parametrizer source-fields, secret_paths, never_starts_targets, exclude_from_validation; lru_cached, alias-normalized, disk-discovered + builtin overrides
│   │   │   ├── agent_paths.py      # Frozen/source-aware agent-pool path resolution + canvas-id → pool-name normalization (handles `Node Manager` → `node_manager`, `Gateway-Relayer` → `gateway_relayer`, `(2)` cardinal stripping)
│   │   │   ├── flow_spec.py        # `FlowNode` / `FlowConnection` / `FlowSpec` dataclasses + `normalize_flow_payload()` / `flow_spec_to_legacy_json()` — schema_version=2 in-memory representation that both surfaces (canvas snapshot AND chat tool-call log) compile through
│   │   │   └── flow_compiler.py    # `compile_flow_spec()` / `compile_flow_payload()` / `list_pool_agents_for_validation()` — wires connections per contract, redacts secrets, writes `config.yaml` + `interconnection-scheme.csv` to the session pool, used by both the Start sequence (mode='write') and the Validate dialog (mode='dry_run')
│   │   ├── doc_generation/         # refresh_project_docs.py, mardown_to_pdf.py
│   │   ├── templates/agent/        # HTML templates (toolbar has Multi-Turn / Exec-Report / ACPX / Ask-Execs checkboxes)
│   │   ├── static/agent/
│   │   │   ├── css/                # agentic_control_panel.css, agent_page.css, tools_dialog.css, etc.
│   │   │   ├── js/                 # 27 JS modules (8 chat + 13 ACP incl. acp-flow-snapshot.js + 1 ACP entry + 5 shared incl. chat_page_runtime_poller.js, shared-runtime-dialogs.js, canvas_item_dialog.js, contextual_menus.js, tools_dialog.js)
│   │   │   ├── img/Tlamatini.ico   # App icon (web pages + console window + .exe)
│   │   │   └── sounds/             # notification.wav, hypervisor_alert.wav
│   │   └── migrations/             # Django migrations (latest: 0103_add_stm32er_demo_prompts; 0101/0102 add the STM32er agent + chat_agent_stm32er tool)
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
1. User sends message via WebSocket (optionally with `multi_turn_enabled`, `exec_report_enabled`, `acpx_enabled`, `ask_execs_enabled`)
2. `AgentConsumer` receives and routes
3. Context determination (RAG loaded?)
4. Internet check (classify if web search needed)
5. Chain selection (RAG / Basic / Unified Agent)
6. Multi-Turn gate: checked = planner/dynamic binding; unchecked = legacy one-shot
7. ACPX gate: when `acpx_enabled=False`, `agent.acpx.filter_acpx_tools()` strips every ACPX/Skill tool name from the bound tool list before the planner / executor see them, forcing the system back onto its legacy Multi-Turn / one-shot behavior
7b. Ask-Execs gate (Multi-Turn-only): when `ask_execs_enabled=True`, the executor BLOCKS before every state-changing tool on a browser Proceed/Deny prompt, bridged by `agent/exec_permission.py::ExecPermissionBroker` (consumer registers a per-request broker keyed by user id; executor thread emits `exec_permission_request` onto the consumer loop via `run_coroutine_threadsafe` and waits on a `threading.Event`; the browser's `exec-permission-response` → `resolve_permission` unblocks it). **Deny halts the whole chain** and surfaces a red "Execution interrupted" banner; the round-trip is fail-safe (emit failure / Cancel / `close()` all resolve to *deny*). The flag must stay in `UnifiedAgentChain.invoke`'s payload-rebuild whitelist alongside `conversation_user_id` (same drop-on-rebuild bug class as `exec_report_enabled`). See `docs/claude/multi-turn.md` → *Ask Execs* and `docs/claude/recent-fixes.md` (2026-05-29)
8. Context prefetch (system/file MCP)
9. Execution loop (tool calls, wrapped agent monitoring, ACPX child-process drain)
10. Streaming response via WebSocket; on success, the chat header renders a **Create Flow** button that converts the executed tool-call log into a downloadable `.flw` (the browser POSTs the legacy draft to `/agent/flow_from_tool_calls/`, which normalizes it through `FlowSpec` and redacts known secret fields before download)
11. Start sequence (canvas Start button) compiles the live snapshot through `/agent/compile_flow/` (mode=`write`) before it executes any agent — so a flow that was edited or loaded since the last write goes through the **same** Agent Contract validation as a `.flw` saved fresh, and Validate uses mode=`dry_run` to preview the same agent/config shape without touching disk

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

## Orphan-Process Cleanup (the `conhost.exe` reaper)

Tlamatini runs a three-tier reaper (`Tlamatini/agent/orphan_reaper.py`) that cleans up Windows `conhost.exe` companions and zombie descendants every console subprocess can leave behind. Without this, users were seeing `conhost.exe` processes lingering in Task Manager **bearing the Tlamatini icon** (conhost inherits the parent EXE's icon) and reasonably assuming Tlamatini was leaking processes.

| Tier | Hook point | Scope | Surfacing |
|---|---|---|---|
| **Tier 1** | `MultiTurnToolAgentExecutor._reap_after_tool()` in `mcp_agent.py` — after every Multi-Turn tool call in `_PROCESS_SPAWNING_TOOL_NAMES` (`execute_command`, `execute_file`, `unzip_file`, `decompile_java`, `googler`, `agent_starter/stopper/parametrizer`) plus every `chat_agent_*` and every `acp_*`. Also fires on the tool-exception path. | Zombie/dead descendants of `os.getpid()` + orphaned `conhost.exe` / `openconsole.exe` whose parent is in our tree or is gone. **No pool-cmdline scan** (cheap path). | Silent. Survivors accumulate on `self._orphan_survivors` and drop into `global_state['last_orphan_survivors']` for Tier 2 to surface. |
| **Tier 2** | `AgentConsumer._tier2_orphan_sweep()` in `consumers.py` — once, in a thread, **after** `process_llm_response` broadcasts the answer so the main reply is never delayed. Merges Tier 1 leftovers with Tier 2 survivors, de-duped by PID. | Same as Tier 1 **plus** the agent-pool cmdline scan (processes whose `cmdline` references `agents/pools/...` but are no longer tracked). | If anything survives **both** tiers, a SECOND `agent_message` is broadcast to the room listing every `name + PID` so the user can end them manually. Renderer: `orphan_reaper.format_survivors_message()` (returns `None` when survivors list is empty — common case). |
| **Tier 3** | `AgentConfig.ready()` in `apps.py` — registered next to the existing pool-directory cleanup on the `atexit` / SIGINT / SIGBREAK path. | Full sweep (self-tree + pool cmdline + console-host orphans). | Logs `--- [Tier-3 reaper] killed=… survivors=… errors=…` to `tlamatini.log`; survivors listed by `name (PID)` for post-mortem. |

Companion hardening — the reaper is paired with **spawn-site changes** that prevent most orphans from existing in the first place:
- `views.py::execute_starter_agent_view`, `execute_ender_agent_view`, `restart_agent_view`, `execute_flowcreator_view` now spawn with `CREATE_NEW_PROCESS_GROUP | CREATE_NO_WINDOW | DETACHED_PROCESS` and stdio piped to `DEVNULL`.
- `agent/acpx/runtime.py` adds `_windows_creationflags()` (same triple flag) and `_kill_process_tree()` (recursive descendant kill via psutil, terminate → wait 2s → kill).
- Every pool-agent script (`ender.py` and all 50+ siblings in `agents/<name>/<name>.py`) installs a top-of-module `subprocess.Popen.__init__` monkey-patch — `_chg_guarded_init` — that defaults `creationflags` to `CREATE_NO_WINDOW` unless the caller explicitly asked for a console (`CREATE_NEW_CONSOLE` / `DETACHED_PROCESS`). This is the seatbelt: even a future tool that forgets to pass the flag manually gets it for free.

Safety contract: **the reaper must never raise into the caller** — every external call is wrapped in `try/except`, every survivor is recorded rather than re-raised, and a `psutil`-import failure degrades silently. A cleanup that crashes the chat path is worse than the orphans it tries to kill.

When adding a new tool that spawns a console child: either (a) add the tool name to `_PROCESS_SPAWNING_TOOL_NAMES` in `mcp_agent.py` so Tier 1 runs after it, or (b) just rely on Tier 2 catching it (the pool-cmdline scan is wide enough that most cases are covered). Tier 3 is the backstop for either way.

---

## Temp & Templates Directory Policy (2026-06-02)

Every **transient** file Tlamatini writes lives under ONE directory — `Temp` at the application root (`<exe-dir>/Temp` frozen, `<repo-root>/Temp` source) — and **never** outside Tlamatini (no `C:\Temp`, no `%TEMP%`, no system temp). `Tlamatini/manage.py::_enforce_app_temp_dir()` (before Django) and `tlamatini/settings.py::_pin_temp_directory()` (covers a direct `daphne`/`asgi` launch) pin `TMP`/`TEMP`/`TMPDIR` + Python's `tempfile.tempdir` to it and export `TLAMATINI_TEMP`, which every spawned pool agent inherits (`get_agent_env` does `os.environ.copy()`). The resolver is `agent/path_guard.py` (`get_app_temp_root` / `enforce_app_temp_dir` / `is_within_app_temp` / `resolve_temp_path`). The 6 temp-creating agents (executer, de_compresser, esp32er, stm32er, arduiner, telegramrx) also carry an explicit module-top `if (os.environ.get('TLAMATINI_TEMP')…)` guard (an `if`-block, never a top-level `def` — that trips ruff E402 before the imports).

Separately, the **default parent for the project trees the firmware/engine agents (STM32er / ESP32er / Arduiner / Unrealer) scaffold** is `Templates` at the application root (`TLAMATINI_TEMPLATES`; `path_guard.get_app_templates_root`), **unless the user names another path**. `Temp` = throwaway scratch; `Templates` = deliverable project trees (so it never touches `tempfile`).

The LLM is told this in `prompt.pmt` **Rule 15** (Temp) and **Rule 16** (Templates), with the absolute paths injected as `{temp_directory}` / `{templates_directory}` by `agent/rag/config.py`. `build.py` ships both dirs empty next to the `.exe`; `.gitignore` ignores both. **When you author a new agent/tool/skill that writes scratch, route it through `<app>/Temp`; a new firmware/engine agent that scaffolds projects defaults to `<app>/Templates`.** Full "do-NOT-revert" contract: `docs/claude/recent-fixes.md` (2026-06-02). The `create-new-agent` / `create-new-mcp` / `skill-creator` skills and the two `@`-imported workflow guides carry the same indication.

---

## Specialized Docs (auto-imported)

The rest of the onboarding material is split into topic files under `docs/claude/`. Each `@` line below is imported by Claude Code into your context automatically, so treat the full set as a single document. See `docs/claude/INDEX.md` for one-line descriptions of each file.

- **Architecture & core systems** — config, system prompt & identity, the Five Layers, application log, doc generation, database models: @docs/claude/architecture.md
- **Multi-Turn, Create Flow, Parametrizer** — Multi-Turn mode, short follow-up scoring, Create-Flow pipeline, `INI_SECTION_*` format: @docs/claude/multi-turn.md
- **Exec Report** — per-agent execution tables, capture/render pipeline, strict ordering contract, styling, adding new agents: @docs/claude/exec-report.md
- **Agents** — creating a new agent (8-step), naming conventions, lifecycle, all 74 agent types, FlowCreator, FlowHypervisor: @docs/claude/agents.md
- **ACPX** — definition, agent registry, 12 LLM-facing tools, transport profiles, canonical flows, runtime mechanics, ACPX toolbar toggle, "when the user says ACPX" decision matrix: @docs/claude/acpx.md
- **MCPs & Tools** — tool-only vs MCP context provider workflows, Skills system (SKILL.md packages), key warnings: @docs/claude/mcp-tools.md
- **Frontend** — chat modules, ACP modules, ACP Canvas DOM Contract: @docs/claude/frontend.md
- **Gotchas & reference** — Claude API client, build/lint, versioning, hardcoded assumptions, roadmap, work-style preferences: @docs/claude/gotchas.md
- **Creating a new agent (full 8-step guide)** — backend script + view + migration + CSS gradient + 4 JS files + docs + lint; naming-convention table; lifecycle; connection-field semantics: @Tlamatini/.agents/workflows/create_new_agent.md
- **Creating a new MCP or tool (full guide)** — tool-only vs MCP context-provider vs both; per-workflow checklists; `factory.py` / sidecar chain / `Mcp` row wiring; hardcoded-assumption warnings: @Tlamatini/.mcps/create_new_mcp.md

**Consult-on-demand (deliberately NOT `@`-imported, to keep the auto-loaded context lean):**

- **Recent Fixes / fix log** — `docs/claude/recent-fixes.md`. The dated chronological log of surgical fixes and "do NOT revert this / keep these surfaces aligned" contracts (ACPX, Flow Compiler, planner, Exec Report, ACP canvas, wrapped chat-agent parsing, desktop-UI agents, the STM32er zero-config bootstrap + fail-safe hardware preflight, `prompt.pmt`, `regen_secrets.py`, logging filters). **Read it before modifying or reverting code in any of those subsystems**, and prepend new fix entries there rather than to `gotchas.md`.
- **Creating a new Skill (SKILL.md package)** — `Tlamatini/.skills/create_new_skill.md`. The dedicated authoring guide for a `SKILL.md` (the two runtimes — `in-process` vs `acpx`; the frontmatter contract + schema ranges; discovery / 30 s staleness cache; lint + `quick_validate`; ACPX-surface gotchas). NOT auto-imported — read it when adding or editing a skill. The `flow-making` skill (`agent/skills_pkg/flow_making/`) is the canonical worked example of an in-process skill that shells out to a shipped `scripts/*.py`.
