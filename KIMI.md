<!--
═══════════════════════════════════════════════════════════════════
  ✦  T L A M A T I N I  ✦   —   "one who knows"
  Created by  Angela López Mendoza   ·   @angelahack1
  Developer · Architect · Creator of Tlamatini
  Tlamatini Author Banner — do not remove (Angela's name is kept in every build)
═══════════════════════════════════════════════════════════════════
-->
<!-- ==================================================================== -->
<!-- ===================  PRIVATE DATA GUARD: ON  ======================= -->
<!-- ==================================================================== -->

# ⛔ PRIVATE DATA GUARD — ABSOLUTE, NON-NEGOTIABLE, READ FIRST ⛔

**NEVER REWRITE GIT HISTORY. EVER. IN THIS REPO, FOR ANY REASON.**

- **NO** `rebase`, `commit --amend`, `reset --hard` to drop commits, `filter-branch`, `git filter-repo`, BFG.
- **NO** `push --force` / `--force-with-lease`, **NO** deleting pushed tags, **NO** deleting remote refs.
- TO REMOVE SENSITIVE / PRIVATE DATA: edit or delete the file, then make a **NEW FORWARD COMMIT** and push that. THE PAST STAYS UNTOUCHED.
- **TAGS, PUSHES, AND `git log` MUST ALWAYS REMAIN INTACT AND TRUTHFUL** — `git log` MUST show the real history, made without lying, FOREVER.
- PRIVATE INFORMATION MAY BE **DELETED GOING FORWARD**; THE HISTORY THAT RECORDED IT MUST **NOT** BE ERASED.
- IF ANY TOOL OR WORKFLOW WOULD REWRITE HISTORY, **STOP** AND TELL ANGELA FIRST.

Enforced by: `test_private_data_guard.py` (automated tests — git-history integrity guard + banner guard) and the release-time scrub gate in `build_complete_public_release.py`.

<!-- ==================================================================== -->

---

# Tlamatini — KIMI.md

**Welcome, Kimi!** This is the self-contained onboarding and reference document for working on the **Tlamatini** project. Read it in full before making any change. It is the Kimi sibling of `CLAUDE.md` (Claude Code's manifest + `@docs/claude/*` imports) and `GEMINI.md` (Gemini CLI's knowledge base): same mandatory rules, same architecture contracts, tuned for Kimi. Because Kimi has **no `@`-file auto-import mechanism**, everything an AI maintainer needs day-to-day is inline here; deeper topic files are listed in §25 as consult-on-demand.

Every count in this file was **verified against source on 2026-07-22** (not copied from docs, which drift). If a count here disagrees with a hand-written doc elsewhere, **this file wins** — then fix the stale doc.

---

## Contents

1. Project Identity & Verified Facts
2. Persona & Communication Rules
3. Architecture Overview (7 Layers + Request Flow + Stack)
4. Directory Structure
5. Configuration System
6. Database & Models
7. RAG System
8. Multi-Turn Orchestration
9. "MCP" Means Four Things Here (disambiguation) + MCP Surfaces
10. ACPX System (external coding-agent CLIs)
11. Skills System (SKILL.md packages)
12. Visual Workflow Designer (ACP) & Flow Compiler
13. The 85 Workflow Agent Types (catalog)
14. Creating a New Agent / Tool / Skill
15. Frontend Architecture
16. Build, Release & Versioning
17. Privacy, Secrets & Release Scrubbing
18. Testing & Lint (headed-tests directive)
19. Coding Conventions & Critical Rules
20. Known Hardcoded Assumptions & Pitfalls
21. Orphan-Process Cleanup (3-tier reaper)
22. Self-Knowledge & Self-Modification
23. How to Run
24. File Paths Quick Reference
25. Deeper Documentation (consult-on-demand)
26. Kimi-Specific Notes & Dogfooding Directive

---

## 1. Project Identity & Verified Facts

**Tlamatini** (Nahuatl for *"one who knows"*) is a **local-first AI developer assistant** created by **Angela López Mendoza** (@angelahack1, XAIHT). It is a Django 5.2 + Channels monolith with a LangChain/LangGraph agent core, a RAG system, a visual agentic workflow designer, an external coding-agent runtime (ACPX), a markdown skill system, and a pool of standalone agent scripts it spawns as subprocesses. Windows-only distribution (PyInstaller-frozen, carried Python 3.12.10).

- **Repository**: `https://github.com/XAIHT/Tlamatini.git` · **License**: MIT · **Platform**: Windows 10/11
- **Version**: **v1.44.0** (SemVer, single source of truth = annotated git tags; see §16)
- **Python**: 3.12.10 (carried interpreter under `<repo>/python` is build-provisioned — never use it to run builds)

**Verified counts (2026-07-22, counted from source):**

| Surface | Count | Ground truth |
|---|---|---|
| Workflow agent types | **85** | `Tlamatini/agent/agents/<name>/` dirs (excl. `pools/`), manifest `_tlamatini_agents_manifest.json` (`agent_count: 85`, catalog `85-ae39eb35`) |
| Canvas drag-and-drop types | 84 | 85 minus one non-user-placeable system agent |
| Wrapped chat-agent tools (`chat_agent_*`) | **63** | `chat_agent_registry.py` `WRAPPED_CHAT_AGENT_SPECS` (counted) |
| Direct LangChain `@tool`s | **20** | 18 in `tools.py` + 2 in `imaging/image_interpreter.py` |
| ACPX tools (`acp_*`, `list_acp_agents`, `invoke_skill`, `list_skills`) | **12** | `agent/acpx/tools.py` |
| External-MCP supervisor tools | **8** (+ dynamic `ext__*`) | `agent/external_mcp_manager.py` |
| **Total chat tool surface** | **~103 + dynamic** | 20 + 63 + 12 + 8, each behind a DB toggle |
| Root stdio MCP server tools | **102** | 85 agent launchers + 7 management + 10 ACPX (`tlamatini_mcp_server.py`) |
| SKILL.md packages | **28** | `agent/skills_pkg/` (confirmed live via `tlamatini_list_skills`) |
| ACPX external CLI agent_ids | **14** | `agent/acpx/agent_registry.py` `DEFAULT_ACP_AGENTS` |
| DB models | **17** | `agent/models.py` |
| Migrations | **186** | latest: `0186_add_chat_agent_flowcreator.py` |
| Frontend JS modules | **33** | `agent/static/agent/js/*.js` |
| HTTP routes / view functions | ~170 / 202 | `agent/urls.py`, `agent/views.py` (12,296 lines) |

Feature headlines: advanced RAG (FAISS + BM25, RRF fusion, context budgeting, memory-insufficient fallback) · Multi-Turn operator loop binding the **full enabled tool surface** · Visual Workflow Designer (ACP canvas) compiling `.flw` → `config.yaml` pools via a backend Flow Compiler + Agent Contract registry · ACPX runtime spawning 14 external coding-agent CLIs · universal External-MCP client (4 transports, ≤5 active) · 28-package Skill system · self-knowledge + self-modification (ships her own rebuildable source) · multi-model LLM via Ollama (local + cloud) / Anthropic / Qwen vision · full PyInstaller build → installer pipeline with public/private release twins.

---

## 2. Persona & Communication Rules

### 2.1 The user: Angela López Mendoza
- The user is **Angela López Mendoza** — developer, architect, and creator of Tlamatini.
- **Always address her by name ("Angela")** in responses; do not speak impersonally.
- Use her full name when affirming her as creator. Her name must **NEVER** be erased or scrubbed from source files, banners, docs, prompts, the About window, PDF/PPTX, or build metadata. A public release build may mask her *other* private data (emails/phones) — never her name.

### 2.2 Persona & identity
- Tlamatini is **explicitly female** by design.
- The `talker` (TTS) agent is restricted to **female voices only** (`tara`, `leah`, `jess`, `mia`, `zoe`). `resolve_voice()` in `agent/agents/talker/talker.py` raises `MaleVoiceForbiddenError` and hard-exits `"NOW CLOSING.. BYE"` on any male voice request. Do NOT modify or bypass this.

### 2.3 How to talk to Angela (mandatory)
- **Answer short and in plain language.**
- **Lead with the single key fact in bold.**
- A few short numbered points at most; everyday words; no jargon walls; no long source lists.
- Cut anything that does not change her decision.
- End with **one direct question or next step**.

### 2.4 Step-by-Step interactive mode
When a task needs Angela to act on her machine (edit configs, click UI, check a board, restart the app):
1. Give **exactly one** concrete step.
2. Give her the **exact string to send back** (e.g. `step1: I see ___`).
3. **WAIT** for that string before the next step.
4. Repeat — one step + one reply-string per turn.

### 2.5 Work style (from `docs/claude/gotchas.md`)
- A broad directive ("Go!", "modify everything") means: execute comprehensively without per-file confirmation.
- Read broadly first, plan the full scope, execute in parallel batches; use subagents for throughput.
- Ask only on truly ambiguous architectural decisions.
- Angela values robustness ("bullet-proof") and uniformity; she is comfortable with large cross-cutting changes.

---

## 3. Architecture Overview

### 3.1 The 7 Layers

```
┌────────────────────────────────────────────────────────────────────────┐
│                        Layer 1: Database State                         │
│   (SQLite: persisted toggle rows for Mcps, Tools, Agents, Skills...)   │
└───────────────────────────────────┬────────────────────────────────────┘
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│                    Layer 2: gRPC & WebSocket Services                  │
│  - System-Metrics (WebSocket :8765)  - Files-Search (gRPC :50051)      │
└───────────────────────────────────┬────────────────────────────────────┘
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│                Layer 3: Context Fetcher Sidecar Chains                 │
│      - SystemRAGChain                   - FileSearchRAGChain           │
└───────────────────────────────────┬────────────────────────────────────┘
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│                      Layer 4: Main LLM Chains                          │
│  - basic.py (fallback)  - history_aware.py  - unified.py (LangGraph)   │
└───────────────────────────────────┬────────────────────────────────────┘
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│                        Layer 5: Unified Tools                          │
│     (LangChain @tools in tools.py + chat_agent_* registry wrappers)    │
└───────────────────────────────────┬────────────────────────────────────┘
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│                     Layer 6: ACPX Multi-Agent Core                     │
│    (AcpxRuntime + sandboxed SkillHarness driving external CLIs)        │
└───────────────────────────────────┬────────────────────────────────────┘
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│                       Layer 7: Flow Compiler                           │
│   (AgentContract registry + FlowSpec normalizer + FlowCompiler engine) │
└────────────────────────────────────────────────────────────────────────┘
```

- **L1 Database**: seeds default registries; UI checkboxes flip DB rows that gate the tool surface.
- **L2 Runtime services**: started from `agent/apps.py::AgentConfig.ready()` (reloader-gated); feed live metrics + file indexes.
- **L3 Sidecar chains**: prefetch `{system_context}` / `{files_context}` injected into every prompt.
- **L4 Main chains**: `factory.py` monkey-patches `invoke()` to merge sidecar context before the LLM call.
- **L5 Tools**: direct executors (`execute_command`, `execute_file`, …) + 63 wrapped `chat_agent_*` launchers.
- **L6 ACPX & Skills**: spawns external CLI engines and runs `SKILL.md` playbooks.
- **L7 Flow Compiler**: normalizes canvas/chat flows into run-ready pools under `agents/pools/<session_id>/`.

### 3.2 Request flow (chat message → answer)

1. User sends a message via WebSocket `ws/agent/` (optionally with `multi_turn_enabled`, `exec_report_enabled`, `acpx_enabled`, `ask_execs_enabled`, `step_by_step_enabled`).
2. `AgentConsumer` (`agent/consumers.py`, 1,820 lines) receives and routes.
3. Context determination (is RAG loaded?).
4. Internet check (classify whether a web search is needed).
5. Chain selection (RAG / Basic / Unified Agent).
6. **Multi-Turn gate**: checked = planner + full-surface dynamic tool binding; unchecked = legacy one-shot.
7. **ACPX gate**: when `acpx_enabled=False`, `agent.acpx.filter_acpx_tools()` strips every ACPX/Skill tool before the planner/executor see them.
8. **Ask-Execs gate** (Multi-Turn only): when enabled, the executor BLOCKS before every state-changing tool on a browser Proceed/Deny prompt, bridged by `agent/exec_permission.py::ExecPermissionBroker`. Deny halts the whole chain (red "Execution interrupted" banner); emit-failure / Cancel / `close()` all resolve to *deny* (fail-safe).
9. Context prefetch (system/file MCP sidecars).
10. Execution loop (tool calls, wrapped-agent monitoring, ACPX child drain). **Every model step is wrapped by a per-request self-healing invoker** (`agent/self_healing.py::SelfHealingInvoker`) that retries distinct recovery tactics under a per-attempt watchdog (`unified_agent_llm_step_timeout_seconds`, 80 s) up to `unified_agent_llm_step_max_tactics` — a transient model failure never hangs, never discards completed work, never yields a silent/untruthful answer (a `recovery_preamble` always tells the user what happened; live retry status streams to chat). Only user Cancel or an exhausted tactic ladder stops it (`ModelStepUnrecoverable`).
11. Streaming response via WebSocket. When Multi-Turn ran with **≥1 successfully-executed agent**, a **Create Flow** button converts the successful-only tool calls into a downloadable `.flw` (POST `/agent/flow_from_tool_calls/`, normalized through `FlowSpec`, secrets redacted). There is no whole-answer SUCCESS/FAILURE classifier (removed 2026-07-06).
12. Canvas **Start** compiles the live snapshot through `/agent/compile_flow/` (mode=`write`) before executing any agent — an edited-but-unsaved canvas goes through the same Agent Contract validation as a freshly loaded `.flw`; **Validate** uses mode=`dry_run`.

### 3.3 Technology stack

| Category | Technologies |
|---|---|
| Backend | Python 3.12, Django 5.2, Django Channels 4.1, Daphne (ASGI), WhiteNoise, django-bootstrap5 |
| Frontend | HTML5, Bootstrap 5, vanilla JS (33 modules, script-scope globals), jQuery 3.7.1 + jQuery-UI 1.13.3, highlight.js, marked, DOMPurify, Sortable |
| AI/ML | LangChain 0.3.x, LangGraph 0.2.x, FAISS, rank-bm25, PyAutoGUI, faster-whisper, OpenCV |
| LLM APIs | Ollama REST (local + cloud models, shipped defaults), Anthropic Claude, Qwen vision; MCP SDK 1.x |
| Database | SQLite (`Tlamatini/db.sqlite3`); FAISS indexes on disk |
| Communication | WebSockets (Channels, **InMemoryChannelLayer** — no Redis), gRPC (grpcio), stdio |
| Packaging | PyInstaller (frozen exe + carried Python + bundled JRE/Git/Playwright browsers) |

### 3.4 Boot sequence

`Tlamatini/manage.py` (734 lines): pin the app `Temp` dir → tee stdout/stderr into `tlamatini.log` → apply any pending DB hot-swap from `DB/ToLoad/` → post-update migrate child process → Django boot → `apps.py::AgentConfig.ready()` (**reloader-gated**) starts: companion-app discovery publisher, MCP System server (daemon thread, :8765), Files-Search gRPC server (:50051), GPU perf pinning (`gpu_perf.py`, `keep_alive=-1`), command watchdog, `Agent`-table repopulation from `agents/` dirs, pool cleanup, NAMU/God-Mode/Tier-3 shutdown reapers, ACPX + skills boot (`boot_acpx()` / `boot_skills()`).

---

## 4. Directory Structure

```
Tlamatini/                          # Git root (C:\Development\Tlamatini)
├── KIMI.md                         # THIS FILE — Kimi's self-contained onboarding reference
├── CLAUDE.md                       # Claude Code entry point + @docs/claude/* import manifest
├── GEMINI.md                       # Gemini CLI self-contained knowledge base
├── README.md                       # User-facing docs
├── BookOfTlamatini.md              # Master long-form manual + changelog ("The Book", ~457 KB)
├── agents_descriptions.md          # AUTHORITATIVE sidebar tooltips/Description-dialog source
│                                   #   (## Workflow Agents tables parsed by views into agent_purpose_map)
├── ACPX.md                         # Standalone ACPX guide / OpenClaw compatibility note
├── VERSIONING.md                   # SemVer contract (git tags are the version)
├── TLAMATINI_MCP.md                # Root MCP server doc (STALE tool counts — trust §1 here)
├── docs/
│   ├── claude/                     # Topic docs (architecture, multi-turn, exec-report, agents,
│   │                               #   acpx, mcp-tools, frontend, gotchas, recent-fixes, INDEX)
│   ├── companion-app-discovery.md  # FlowPills registry+manifest discovery contract
│   └── stm32er_all_families_proposal.md
├── .claude/                        # Claude Code integration: skills/ (5 repo skills), hooks/
│   │                               #   (SessionStart announce_skills.py), settings, memory
├── .github/workflows/name-guard.yml# Only CI: identity auto-scrub bot (no build/test CI)
├── .mcp.json                       # Wires the root stdio MCP server (tlamatini) for MCP clients
│
├── build.py                        # STEP 1 of release: PyInstaller build → pkg.zip (~84 KB script)
├── build_uninstaller.py            # STEP 2: freeze uninstall.py → Uninstaller.exe
├── build_installer.py              # STEP 3: freeze install.py → Installer.exe + release folder
├── build_all.cmd                   # Wrapper: steps 1-3 in order (system Python only)
├── build_complete_private_release.py  # KEYED private build (real secrets; NEVER publish)
├── build_complete_public_release.py   # PUBLIC build (scrub + leak-audit gate + tree restore)
├── install.py / uninstall.py       # Tkinter GUI installer/uninstaller sources
├── copy_source_assets.py           # Generates TlamatiniSourceCode/ self-modify snapshot
├── regen_secrets.py                # Toggle secrets: --mode keyed (from data.keys) / push-able
├── versioning.py                   # Build-time version shim over agent/version.py
├── apply_update.ps1                # External self-updater (runs from %LOCALAPPDATA%)
├── check_private_data.py           # "god-of-gods" privacy auditor (see §17)
├── test_private_data_guard.py      # Git-history integrity guard + banner guard
├── test_check_private_data.py      # 100+ auditor unit tests
├── test_author_banner.py           # Author-banner presence guard
├── requirements.txt                # Python deps (ruff is a REQUIRED runtime gate — never unpin)
├── eslint.config.mjs               # ESLint 10 config (501-line cross-file globals whitelist)
├── package.json                    # version 1.44.0; npm run lint / lint:fix
├── tlamatini_mcp_server.py         # Root stdio MCP server: 85 agent tools + 7 mgmt + 10 ACPX
├── tlamatini_acpx.py               # Self-contained stdlib ACPX runtime port for the MCP server
├── Tlamatini.ps1                   # Legacy launcher for the frozen exe
├── demo_flows/                     # 3 shipping .flw demos (schemaVersion 2)
├── Templates/                      # Default parent for firmware/engine project scaffolds (empty in git)
├── Temp/                           # ALL transient files (never %TEMP%) — gitignored
├── Go/                             # LOCAL leftover of the private Go toolchain (gitignored, not source)
├── Tests/ AuxTests/                # Standalone visual test scripts
│
└── Tlamatini/                      # Django project root
    ├── manage.py                   # Entrypoint (boot sequence §3.4); custom cmd: startserver
    ├── db.sqlite3                  # SQLite database (gitignored)
    ├── tlamatini.log               # Unified app log — TRUNCATED on every server start, no rotation
    ├── jd-cli/                     # Bundled Java decompiler (J-Decompiler backend)
    ├── staticfiles/                # collectstatic output (WhiteNoise)
    ├── DB/ToLoad/ + DB/Older/      # DB hot-swap: drop db.sqlite3 in ToLoad → archived+swapped pre-Django
    ├── tests_e2e/                  # 6 headed Playwright suites (plain scripts, live server)
    ├── .agents/workflows/create_new_agent.md   # Agent-creation guide (@-imported by CLAUDE.md)
    ├── .mcps/create_new_mcp.md                 # MCP/tool-creation guide (@-imported)
    ├── .skills/create_new_skill.md             # Skill-authoring guide
    │
    ├── tlamatini/                  # Django project config: settings.py, urls.py, asgi.py, middleware
    │
    └── agent/                      # CORE DJANGO APP — all business logic
        ├── prompt.pmt              # System prompt template ({self_knowledge}, {temp_directory}...)
        ├── Tlamatini.md            # LLM SELF-KNOWLEDGE (first-person; injected at prompt build)
        ├── config.json             # Main config (§5); ships with <KEY goes here> placeholders
        ├── config_loader.py        # Frozen/source-aware config reader (CONFIG_PATH env override)
        ├── path_guard.py           # Temp/Templates/app-root resolution (frozen+source duality)
        ├── views.py                # 202 view functions (12,296 lines)
        ├── consumers.py            # AgentConsumer WebSocket (1,820 lines)
        ├── models.py               # 17 DB models
        ├── urls.py                 # ~170 routes
        ├── tools.py                # 18 direct @tools + wrapped-launcher factory (get_mcp_tools)
        ├── mcp_agent.py            # Unified-agent builder + MultiTurnToolAgentExecutor +
        │                         #   _EXEC_REPORT_TOOLS map (2,397 lines)
        ├── global_execution_planner.py  # Request-scoped DAG planner
        ├── capability_registry.py       # Capability scoring for tool hints/ordering
        ├── chat_agent_registry.py       # 63 WRAPPED_CHAT_AGENT_SPECS
        ├── chat_agent_runtime.py        # Wrapped-run lifecycle (_chat_runs_/)
        ├── exec_permission.py           # Ask-Execs broker
        ├── self_healing.py              # SelfHealingInvoker (per-step retry tactics)
        ├── global_state.py              # Thread-safe singleton (toggle mirror)
        ├── gpu_perf.py                  # keep_alive=-1 + GPU max-performance at boot
        ├── orphan_reaper.py             # 3-tier conhost/zombie reaper (§21)
        ├── agent_manifest.py            # Companion-app manifest generator
        ├── external_mcp_manager.py      # Universal External-MCP client engine
        ├── external_mcps.json           # External-MCP catalog (USER STATE, gitignored)
        ├── mcp_system_server.py         # System-Metrics WS server (:8765)
        ├── mcp_files_search_server.py   # Files-Search gRPC server (:50051) + filesearch.proto
        ├── chain_system_lcel.py / chain_files_search_lcel.py  # Sidecar chains
        ├── apps.py                   # AgentConfig.ready() — boot wiring (RELOADER-GATED)
        ├── acpx/                   # ACPX runtime: agent_registry (14 ids), runtime, tools (12),
        │                           #   session_store (NDJSON), windows_spawn, permissions, service
        ├── skills/                 # Skill runtime: registry (30 s staleness), harness (budgets,
        │                           #   permissions, NDJSON audit), frontmatter, io_contract
        ├── skills_pkg/             # 28 SKILL.md packages (+ _meta/ schema+lint)
        ├── rag/                    # RAG: factory, interface, retrieval, splitters, loaders,
        │                           #   prompts, utils, interaction + chains/{basic,history_aware,unified}
        ├── rag_enhancements.py     # Metadata extraction (code structure, file roles, deps)
        ├── services/               # filesystem, response_parser, agent_contracts (AgentContract
        │                           #   registry), agent_paths (frozen/source pool paths + canvas-id
        │                           #   normalization), flow_spec (FlowSpec schema_version=2),
        │                           #   flow_compiler (compile + pool writer)
        ├── opus_client/            # Claude API client library
        ├── imaging/                # Dual-backend image analysis (opus_analyze_image, qwen_analyze_image)
        ├── agents/                 # 85 AGENT TEMPLATE DIRS (<name>/<name>.py + config.yaml)
        │   ├── _tlamatini_agents_manifest.json   # sha256 manifest (regenerated at build/launch)
        │   ├── pools/              # Runtime session pools (canvas flows)
        │   ├── flowcreator/agentic_skill.md      # FlowCreator AI reference
        │   ├── flowhypervisor/monitoring-prompt.pmt
        │   └── <84 more>/          # See §13 catalog
        ├── templates/agent/        # 4 templates: agent_page, agentic_control_panel, login, welcome
        ├── static/agent/           # js/ (33 modules), css/ (10 files), img/, sounds/
        └── migrations/             # 186 migrations (seed migrations carry prompts/tools/agents)
```

---

## 5. Configuration System

Main config: `Tlamatini/agent/config.json`. Frozen builds resolve it next to the executable; source mode from `Tlamatini/agent/config.json`; `CONFIG_PATH` env var overrides both. Ships with `<KEY goes here>` placeholders — real secrets come from `data.keys` via `regen_secrets.py --mode keyed` (see §17).

Key config keys:
- `embeding-model` — RAG embedding model. Default `Nomic-Embed-Text:latest` (~600 MB resident VRAM). Opt-in `qwen3-embedding:8b` (Config → Models menu) uses ~10× more VRAM (~6.24 GB) and trips the embedding-memory pre-flight guard on 8 GB GPUs.
- `chained-model` — primary chat model · `unified_agent_model` — Multi-Turn tool-loop model.
- `ollama_base_url` (default `http://127.0.0.1:11434`) · `ollama_token` — bearer token for authenticated Ollama.
- `ANTHROPIC_API_KEY` — Claude API key.
- `enable_unified_agent` — tool-calling agent on/off · `unified_agent_max_iterations` — max tool-call turns (default **4096**).
- `unified_agent_llm_step_timeout_seconds` (80) · `unified_agent_llm_step_max_tactics` — self-healing knobs.
- `chat_agent_limit_runs` — wrapped-run listing limit.
- `image_interpreter_model` / `image_interpreter_base_url` — vision model settings.
- Chunking: `chunk_size` (2000), `chunk_overlap`, `max_chunks_per_file`.
- Retrieval: `k_vector` (40), `k_bm25` (40), `k_fused`, `enable_bm25`, `rrf_k` (60).
- Context limits: `max_doc_chars`, `max_context_chars`, `context_budget_allocation`.
- Internet: `internet_classifier_model`, `web_summarizer_model`, `web_context_max_chars`.
- Ports: **`django_port`** (web, default 8000 — see below) · `mcp_system_server_host`/`mcp_system_server_port` (8765) · `mcp_files_search_server_port` (50051).
- **ACPX block** (auto-backfilled on upgrade): `permissionMode` (`approve-reads` default / `approve-all` / `deny-all`), `nonInteractivePermissions` (`deny` / `fail`), `timeoutSeconds` (120), `pluginToolsMcpBridge` (false), per-agent overrides under `agents.{agent_id}` (command, transport, budgets, `env` for child env injection).

**Configurable web port (since v1.40.1).** `8000` is only the default. `manage.py::_resolve_django_port()` reads `django_port`; `_apply_configured_port()` injects it into every launch path (frozen double-click, `.flw` association, browser auto-open, source `runserver`, `startserver`). An explicit CLI `[ipaddr:]port` always wins; resolution is **fail-open** to 8000 (a typo never blocks startup — a `--- [PORT] …` log line explains). Exists because Hyper-V/WSL/Docker can *reserve* port 8000 → `WinError 10013` at startup (check `netsh interface ipv4 show excludedportrange protocol=tcp`). Still hardcoded: direct `daphne`/`uvicorn` launches, the helper listeners :8765/:50051, TeleTlamatini's own `tlamatini.base_url`. **Never re-introduce a literal `8000` in a launch path.**

---

## 6. Database & Models

SQLite single DB `Tlamatini/db.sqlite3` (`settings.py`: `BASE_DIR/'db.sqlite3'`). FAISS indexes live on disk, not in DB. **186 migrations**; heavy seed-migration usage (prompts, tools, agents as data rows).

**17 models** (`agent/models.py`): `AgentMessage` (chat messages) · `LLMProgram` / `LLMSnippet` (saved code) · `Prompt` (Catalog of Prompts; append-only PK rule + `category` / `hidden` / `sort_rank`) · `Omission` (file omission patterns) · `ContextCache` (SHA1 query→context cache) · `Mcp` (MCP toggle rows) · `Tool` (tool toggle rows) · `Agent` (agent type registry — **repopulated from the `agents/` dirs on every boot**, `apps.py`) · `AgentProcess` (tracked PIDs — wiped every boot) · `ChatAgentRun` (wrapped run records — wiped every boot) · `Asset` · `SessionState` (24 h expiry) · `AcpAgent` (mirrored from `DEFAULT_ACP_AGENTS` on boot) · `Skill` (mirrored from `skills_pkg/` on boot; enumeration + enable/disable only — budgets/permissions/body live in SKILL.md on disk) · `AcpSession` · `SkillInvocation`.

Toggle state = DB rows mirrored into `global_state` (in-process dict), read by `get_mcp_tools()`.

**DB hot-swap**: drop a `db.sqlite3` into `Tlamatini/DB/ToLoad/` and `manage.py::_apply_pending_db_swap()` archives the live DB into `DB/Older/<timestamp>/` and swaps it in pre-Django. Used by self-update (`apply_update.ps1` + `DB/post_update_migrate.flag` → child-process migrate).

**Prompt-table rules**: `idPrompt` is **append-only** in day-to-day work (the 2026-07-15 contiguous renumber was a one-time, Angela-authorized reorganization). New prompt = next free id + a `sort_rank` (steps of 10; **rank 10 is RESERVED in every section for its Step-by-Step opener**). Display order = (category rank, `sort_rank`, `idPrompt`); primary load is ONE `GET /agent/list_prompts/`; `MAX_PROMPTS=256`.

---

## 7. RAG System

Located in `agent/rag/`.

- **Loaders** (`loaders.py`) — file loading with size reporting · **Splitters** (`splitters.py`) — RecursiveCharacterTextSplitter.
- **Retrieval** (`retrieval.py`) — FAISS + BM25 hybrid via Reciprocal Rank Fusion, query expansion, per-file chunk caps.
- **Context budgeting** — doc chunks prioritized within token limits (high_relevance 60% / architecture 20% / related 15% / documentation 5%).
- **Metadata extraction** (`rag_enhancements.py`) — code structure, file-role classification, dependency tracking, cross-references.
- **Memory-Insufficient Context Fallback** — if embeddings/vector-store construction fail on RAM, keeps the loaded source files and continues from packed raw context instead of dropping to empty-context chat.

Chains (`agent/rag/chains/`):
- `basic.py` — BasicPromptOnlyChain (no docs, fallback).
- `history_aware.py` — history-aware RAG with reranking.
- `unified.py` — tool-enabled agent chains (LangGraph) with `_invoke_unified_agent_with_retry` (exponential backoff 0.5/1/2 s for transient 502/503/504/socket errors). When a fallback to basic LLM happens while Multi-Turn was requested, a visible system notice is prepended so the user knows tools were not executed.

`factory.py` builds chains and monkey-patches `invoke()` to inject sidecar MCP context; it also filters ACPX tools via `filter_acpx_tools()` when `acpx_enabled` is false. `interface.py` (`ask_rag`) persists `last_exec_report_*` / `last_acpx_enabled`. Both **multi-turn** and **ACPX** bypass the `is_valid_prompt` shape validator and the access-validation security gate — agentic flows need free-form prompts.

---

## 8. Multi-Turn Orchestration

When the **Multi-Turn** toolbar checkbox is on, Tlamatini shifts from a text box to a **stateful runtime operator**:

- **Full-surface binding (invariant)** — Multi-Turn binds the **FULL enabled tool surface** (every toggled-on tool/agent/skill; ACPX still filtered by its own checkbox), never a narrowed planner subset, so the operator loop is never starved. The planner (`global_execution_planner.py` + `capability_registry.py`) shapes capability hints/ordering only. `max_selected_tools` (50 → **20**) now only shapes hints.
- **Executor** — `MultiTurnToolAgentExecutor` in `mcp_agent.py`; `unified_agent_max_iterations` default **4096**; tool quota 64 soft / 256 hard per request.
- **Self-healing model steps** — see §3.2 step 10. Per-attempt watchdog 80 s; recovery preamble is mandatory truthfulness; Send button stays on **Cancel** during "🔁 Tactic…" status frames (frontend `isSelfHealingStatusMessage()`).
- **Step-by-Step** toolbar modifier — one concrete action, then WAIT for the user's `READY`/output before the next. Distinct from Ask Execs (permission gate vs pacing directive).
- **Ask Execs** — per-state-changing-tool Proceed/Deny (§3.2 step 8). The flag must stay in `UnifiedAgentChain.invoke`'s payload-rebuild whitelist alongside `conversation_user_id` (same drop-on-rebuild bug class as `exec_report_enabled`).
- **Short follow-up scoring** — a short message after a long one is scored as a likely follow-up and keeps prior context.
- **Create Flow** — see §12.4.
- **Exec Report** — see §12.5.

`chat_agent_*` wrapped runs execute as **isolated runtime copies** under `agents/_chat_runs_/` (`chat_agent_runtime.py`); flows run from `agents/pools/<session_id>/`; both are cleaned on boot and reaped on shutdown.

---

## 9. "MCP" Means Four Things Here

The single most confusion-preventing fact in this repo. **"MCP" is overloaded across FOUR distinct surfaces:**

1. **MCP context providers (the `Mcp` DB model)** — the two built-in sidecar services whose checkboxes live in the MCPs dialog: **System-Metrics** (WebSocket JSON server `:8765`, `mcp_system_server.py` — CPU/mem/disk injected as `{system_context}`) and **Files-Search** (gRPC server `:50051`, `mcp_files_search_server.py` + `filesearch.proto` — file discovery inside `allowed_paths`, injected as `{files_context}`). `factory.py` recognizes them **by Mcp description string** (`System-Metrics` / `Files-Search`) — a hardcoded assumption (§20). The frontend MCP dialog is hardcoded for exactly two checkboxes.
2. **LangChain tools** — `get_mcp_tools()` in `tools.py` returns LangChain `@tool` objects, **NOT** MCP services. The name is historical.
3. **The root stdio MCP server (`tlamatini_mcp_server.py`, 700 lines)** — a **separate, Django-free** MCP server for *external MCP clients* (Claude Code, Kimi, etc.), wired via repo-root `.mcp.json`. It dynamically discovers every `agents/<name>/` dir holding `<name>.py` + `config.yaml` and exposes each as a tool — **85 agent launchers** — replicating the pool "launcher dance" itself (copy template to `Temp/mcp_agent_runs/<name>__<runid>/`, deep-merge args into config.yaml, run `python <name>.py`, read back the log). Long-runners (croner, flowhypervisor, teletlamatini, gatewayer, monitors…) default to background + polling. Management tools (7): `tlamatini_list_agents`, `tlamatini_list_runs`, `tlamatini_run_status`, `tlamatini_run_log`, `tlamatini_run_stop`, `tlamatini_list_skills`, `tlamatini_read_skill`. ACPX tools (10): `acp_doctor`, `list_acp_agents`, `acp_spawn`, `acp_send`, `acp_send_and_wait`, `acp_relay`, `acp_transcript`, `acp_session_status`, `acp_list_sessions`, `acp_kill` — backed by the self-contained stdlib `tlamatini_acpx.py` (`AcpxManager`), degrading to `ACPX_UNAVAILABLE` on import failure. **Total: 102 tools.** So: Django :8000 serves humans; the root server serves MCP clients over stdio; :8765/:50051 are internal sidecars started by `apps.py`.
4. **External MCPs (universal client, 2026-06)** — a config-driven universal MCP **client**: connect to and use the tools of **any** external MCP server declared in `agent/external_mcps.json` (the `mcpServers` shape, like a `.mcp.json`) over **four transports** — `stdio`, `streamable-http`, legacy `sse`, `websocket` — with **at most 5 active at once**. Engine: `agent/external_mcp_manager.py`; each remote tool binds as `ext__<server>__<tool>`; managed by 8 LLM supervisor tools (`external_mcp_status` / `reconnect` / `doctor` / `list_tools` / `call` / `import` / `set_active` / `wait`) and the **External ▸ MCPs** navbar dialog (`external_mcps_dialog.js` — searchable catalog, tick ≤5 active, drag a `.json` to import) over `/agent/external_mcps/` `…/activate/` `…/import/` (pure HTTP, not a WebSocket toggle channel). 60 s connect budget per server. The **MCP Doctor** canvas agent statically triages a catalogued MCP before you wire it.

Distinct from all four: the per-agent inline MCP clients (STM32er's template MCP, Kalier's MCP-Kali-Server) and ACPX (§10).

**Companion-App Discovery (FlowPills).** XAIHT companion apps (Tlamatini-FlowPills) find the agent catalog without Python/scans via the `HKCU\Software\XAIHT\Tlamatini` registry key + `<agents_root>\_tlamatini_agents_manifest.json` + `.tlamatini-preserved-agents.json`. Engine: `agent/agent_manifest.py` + `agent/windows_app_registration.py`, wired into `apps.py` / `install.py` / `uninstall.py` / `build.py`. HKCU-only, no-admin, fail-open. Contract: `docs/companion-app-discovery.md`.

---

## 10. ACPX System

**ACPX** (Agent Communication Protocol eXtension) spawns **external coding-agent CLIs as child processes** and brokers their I/O — a port of OpenClaw's ACPX plugin (config block is OpenClaw-compatible verbatim). It closes two gaps: delegating sub-tasks to external agents, and adding capabilities as markdown skills instead of Python agents.

- **Runtime**: `Tlamatini/agent/acpx/` — `agent_registry.py` (**14 built-in agent_ids**: claude, codex, cursor, gemini, qwen, tlamatini (self-host), kiro, kimi, iflow, kilocode, opencode, pi, droid, copilot), `runtime.py` (`AcpxRuntime`, `AcpSession`, transport-aware drain, oneshot-prompt path), `session_store.py` (FileSessionStore, NDJSON transcripts), `windows_spawn.py` (Windows-aware command resolution), `permissions.py`, `tools.py`, `service.py` (`boot_acpx` / `boot_skills`, registry → DB mirror). Children spawn via `subprocess.Popen` with a JSON envelope on stdin/stdout.
- **12 LLM-facing tools**: `acp_spawn`, `acp_send`, `acp_send_and_wait`, `acp_kill`, `acp_doctor` (PATH probe of all 14 CLIs), `acp_transcript` (NDJSON), `acp_session_status`, `acp_list_sessions`, `acp_relay` (session→session handoff), `list_acp_agents`, `invoke_skill`, `list_skills`. (Stale comments saying "7 tools" exist — the count is **12**.)
- **Permission gate**: `permissionMode` = `approve-reads` (default) / `approve-all` / `deny-all`; non-interactive policy `deny` / `fail`. Per-agent env injection via `config.json` → `acpx.agents.<id>.env`.
- **Toolbar checkbox ACPX** filters the entire ACPX/Skills tool surface in or out per request (`filter_acpx_tools()`).
- **Canvas integration**: the visual **ACPXer** agent (one external CLI session per run; multi-CLI relay via Parametrizer) plus **Skill** and **ACPx** node types (classMap + gradients); navbar **ACPX-Skills** admin menu (Browse / Configure / Diagnostics / Reload).
- The same 10-tool ACPX surface is replicated Django-free for MCP clients by root `tlamatini_acpx.py` (§9.3).
- Full guide: `ACPX.md`; onboarding depth: `docs/claude/acpx.md`.

---

## 11. Skills System

Markdown-defined `SKILL.md` packages run by `SkillHarness`. Disk is the source of truth: `agent/skills/registry.py` discovers packages from `agent/skills_pkg/` (30 s staleness reload), `boot_skills()` mirrors them into the `Skill` DB table (enumeration + enable/disable only). Frontmatter contract: `metadata.tlamatini` carries runtime / permissions / budget / inputs / outputs / triggers; body ≤ 8 KiB. Runtimes: **`in-process`** (safe envelope through the unified agent's existing tools, with budget caps on iterations/seconds/tokens) or **`acpx`** (body rendered as a task to an ACP child). Every invocation writes an NDJSON audit record under `~/.tlamatini/skill-audit/`. LLM entry points: `list_skills` / `invoke_skill`. Admin surface: the **ACPX-Skills navbar dropdown** (Configure writes only `Skill.enabled`; Reload re-runs `boot_skills()`).

**The 28 packages** (verified live via `tlamatini_list_skills`, 2026-07-22):

| Skill | Purpose |
|---|---|
| `acp-router` | Pick the right ACPX agent_id from plain-language intent and `acp_spawn` it |
| `code-review` | Senior-engineer git-diff review → verdict + line-anchored findings |
| `create-new-agent` | Authoritative 8-step contract for scaffolding a new workflow agent |
| `create-new-mcp` | Authoritative reference for adding a tool / MCP context provider / both |
| `flow-making` | Natural-language objective → downloadable `.flw` via FlowCreator (ships `scripts/make_flow.py` + `result_to_flw.py`); supersedes `tlamatini-flow-from-objective` |
| `github` | `gh` CLI: issues, PRs, CI/logs, reviews, releases, API queries |
| `gmail` | Read/send Gmail via Gmail API |
| `hello-world` | Smoke-test echo proving SkillHarness wiring end-to-end |
| `jira` | Jira REST API v3 issues/comments/transitions |
| `kali-pentest` | Authorized scoped pentest/recon/CTF via Kalier + MCP-Kali-Server |
| `notion` | Notion API pages/datasources/blocks |
| `roblox-studio` | Roblox Studio builds via its MCP (big `execute_luau` scripts, voxel terrain) |
| `security-audit` | Aggregate installed scanners (bandit, semgrep, ruff, eslint, gitleaks, pip-audit) |
| `setup-new-acpx-key` | Wire an ACPX agent_id's API key across data.keys/config.json/regen_secrets.py; verify via `acp_doctor` |
| `skill-creator` | Create/edit/validate/package SKILL.md packages |
| `slack` | Slack Web API messages/channels/threads |
| `summarize` | Long text/file → tight faithful brief at a target word count |
| `tlamatini-allowed-hosts-tighten` | Tighten Django ALLOWED_HOSTS from `*` (with settings backup) |
| `tlamatini-csrf-exempt-audit` | Classify every `@csrf_exempt` view in views.py |
| `tlamatini-exec-report-row-adder` | Add a state-changing tool to `_EXEC_REPORT_TOOLS` + CSS |
| `tlamatini-flow-from-objective` | One-sentence objective → `.flw` (legacy; use `flow-making`) |
| `tlamatini-flw-doctor` | Validate a `.flw`: topology, terminal agents, Parametrizer queue, connectors |
| `tlamatini-new-acp-agent` | Scaffold a new visual agent across the 8 required places |
| `tlamatini-planner-trace-replay` | Replay the latest planner trace from tlamatini.log |
| `tlamatini-static-version-bumper` | Bump STATIC_VERSION to bust frontend cache |
| `todoist` | Todoist REST API v2 tasks/projects |
| `trello` | Trello REST API boards/lists/cards |
| `weather` | Open-Meteo weather (no API key) |

**Claude-Code repo skills** (`.claude/skills/`, for Claude sessions — Kimi reads them as docs): `tlamatini-agent-creation` (the 700+-step, 26-phase authoritative agent-creation runbook), `tlamatini-agent-naming` (casing convention guard), `tlamatini-daily-chat-test` (daily visible-Chrome 1000-question regression harness), `tlamatini-self-modify-inclusion` (keeps the self-modify snapshot complete), `tlamatini-self-update-inclusion` (keeps the release/update carriers complete).

---

## 12. Visual Workflow Designer (ACP) & Flow Compiler

### 12.1 Surfaces
The ACP (Agentic Control Panel) page (`templates/agent/agentic_control_panel.html` + 18 `acp-*`/canvas JS modules in strict load order) is a drag-and-drop canvas of agent nodes wired by connections, saved/loaded as **`.flw`** files (JSON, `schemaVersion: 2`). A `.flw` double-click opens Tlamatini via the file association (`register_flw.ps1`).

### 12.2 Flow Compiler pipeline (canvas / chat → backend → pool)
Two browser surfaces produce flows; **both compile through the same backend Agent Contract registry** before touching disk:

1. **ACP canvas → `/agent/compile_flow/`** — Save / Validate / Start all build a snapshot via `buildACPFlowSnapshot()` (`acp-flow-snapshot.js`: nodes with `id`, `text`, position, `agentPurpose`, `configData`; connections with indexes AND ids; `artifacts.parametrizerMappings` keyed by node id). Start passes `mode: 'write'` (canvas state lands in the session pool before agents launch); Validate passes `mode: 'dry_run'` (compiled-config preview without touching disk).
2. **Chat Create-Flow → `/agent/flow_from_tool_calls/`** — POSTs the successful-only tool-call draft; backend runs `normalize_flow_payload()` → `flow_spec_to_legacy_json(redact=True)` and returns a secret-redacted `.flw` (graceful fallback to the legacy draft if the backend is unreachable, so an offline frozen install still downloads a usable file).

Shared backend: `agent/services/flow_spec.py` (`FlowNode`/`FlowConnection`/`FlowSpec` dataclasses + normalizers), `agent/services/agent_contracts.py` (**AgentContract registry**: per-agent connection-field shape, `parametrizer_fields`, `secret_paths`, `never_starts_targets`, `exclude_from_validation`; lru_cached, alias-normalized, disk-discovered + builtin overrides), `agent/services/flow_compiler.py` (wires connections per contract, redacts secrets, writes `config.yaml` + `interconnection-scheme.csv` into `agents/pools/<session_id>/`), `agent/services/agent_paths.py` (frozen/source pool resolution + canvas-id → pool-name normalization: `Node Manager` → `node_manager`, `(2)` cardinal stripping, etc.).

The `_parametrizer_mappings` array on a Parametrizer node's config and the snapshot's `artifacts.parametrizerMappings` object are **two valid persistence shapes for the same data** — `getSavedParametrizerMappings()` (`acp-file-io.js`) accepts either on load.

### 12.3 ACP Canvas DOM contract (scrollable canvas)
Two-layer DOM — confusing the layers is the #1 source of coordinate-math bugs:

1. `#submonitor-container` — the **viewport** (`overflow: auto`, owns the scrollbars). NOT where items live.
2. `#canvas-content` — the **content layer** inside it (`position: relative`, grows via `updateCanvasContentSize()` in `acp-globals.js`). Every `.canvas-item`, the SVG `#connections-layer`, and the rubber-band `#selection-box` are children of `#canvas-content`.

Rules that MUST be respected:
- **Coordinate frame is `canvasContent`, not `submonitor`.** Pointer→`style.left/top` math uses `canvasContent.getBoundingClientRect()`; its rect already reflects scroll — do NOT add `submonitor.scrollLeft/scrollTop`.
- **Append items to `canvasContent`, never to `submonitor`** (`createCanvasItem()` / `cloneAndRegister()`).
- **No upper clamp on item positions** — clamp `>= 0` only; the canvas grows right/bottom. After any envelope-changing operation (create, drag end, `.flw` load, undo/redo restore) call `updateCanvasContentSize()`.
- **Selection-box** uses the same `canvasContent` rect frame and is itself a child of `#canvas-content`.
- **Mousedown dispatch** — the begin-selection branch in `initCanvasEvents()` accepts `e.target === submonitor || canvasContent || #connections-layer`; new clickable layers must stop propagation or be whitelisted, or they silently disable rubber-band selection.
- New canvas-level features (grid, minimap, HUD) belong as children of `#canvas-content`.

### 12.4 Flow execution model
Canvas flows compile to per-agent `config.yaml` files in the session pool; each agent is a **standalone Python subprocess** (no shared base class — convention: read config.yaml → do work → write `<name>__<runid>.log` → trigger `target_agents`). Gate agents (Starter/Ender/AND/OR/Barrier/Forker/Raiser/Stopper/Counter/Sleeper/Mover/Cleaner/Deleter) watch log files to route execution. **FlowHypervisor** is the system watchdog over all agent logs (ATTENTION alerts). Undo depth on canvas: 1024 actions.

### 12.5 Parametrizer & interconnection
The **Parametrizer** agent is the interconnection engine: it pipes structured outputs from upstream agents (`INI_SECTION_*` blocks in their logs) into downstream agents' configs at runtime. On canvas it owns a single-lane mapping queue (dialog: `acp-parametizer-dialog.js` → `acp-parametrizer-dialog.js`); mappings persist per-node (`_parametrizer_mappings`) or in the snapshot `artifacts.parametrizerMappings`. Agent-side wiring is declared in each agent's AgentContract (`parametrizer_fields`, connection-field semantics).

**`INI_SECTION_<TYPE>` contract**: agents that emit structured output wrap it in `INI_SECTION_<TYPE>` … `END_SECTION_<TYPE>` blocks (ALL-CAPS type token — a *separate* convention from display casing; do NOT "fix" it). Downstream agents, the Exec Report, the Reviewer (verdict-first INI block) and Video-Analyzer (`TLM_VERDICT::` line a Forker branches on) all consume this grammar.

### 12.6 Exec Report
A per-agent operations table appended to chat answers when the **Exec Report** checkbox (Multi-Turn-only, mirrors Ask-Execs availability) is on. Capture/render: `_EXEC_REPORT_TOOLS` map in `mcp_agent.py` lists the state-changing tools whose operations become rows; rendering keeps a **strict ordering contract** (rows in execution order; `save_message` persists the answer BEFORE the report is appended — do not reorder). Styling rules live in `agent_page.css`. To add a tool: use the `tlamatini-exec-report-row-adder` skill. Observational agents (Shoter, Camcorder, Recorder, Talker, AudioPlayer, VideoPlayer, Whisperer, …) are intentionally NOT in the Exec Report.

---

## 13. The 85 Workflow Agent Types

Ground truth: `Tlamatini/agent/agents/` (85 dirs, each `<name>.py` + `config.yaml`), catalog `agents_descriptions.md` (drives sidebar tooltips/Description dialogs), manifest `_tlamatini_agents_manifest.json`. Display casing below is the DB `agentDescription` casing (§14.1). Most agents are both canvas-placeable and Multi-Turn-wrapped (`chat_agent_*`); a few wrapped-tool display names deliberately differ from canvas names (`Send Email`→emailer, `Move File`→mover, `Summarize Text`→summarizer, `Kyber Deciph` (truncated)→kyber_decipher, `SQLer` tool vs `Sqler` canvas).

### Control Agents (6)
| Agent | Purpose |
|---|---|
| **Starter** | Flow entry point; kicks off `target_agents` on Start |
| **Ender** | Graceful flow termination; kills targets, launches backup/cleanup chain |
| **Stopper** | Surgical pattern-triggered kill of specific source agents |
| **Cleaner** | Post-mortem janitor; deletes `.log`/`.pid` files after Ender/FlowBacker |
| **Sleeper** | Timed pause (ms), then fires targets |
| **Croner** | Daily HH:MM clock trigger (long-runner) |

### Routing Agents (4)
| Agent | Purpose |
|---|---|
| **Raiser** | Watches source logs for a pattern, fires targets ("when X, do Y") |
| **Forker** | Automatic A/B router on two pattern sets |
| **Asker** | Interactive A/B human-approval dialog (5-min timeout) |
| **Counter** | Persistent threshold counter with less/greater routing |

### Logic Gates (3)
| Agent | Purpose |
|---|---|
| **AND** | Latched two-input AND gate |
| **OR** | First-one-wins two-input OR gate |
| **Barrier** | N-input fan-in synchronization gate |

### Action Agents (52)
| Agent | Purpose |
|---|---|
| **Executer** | Arbitrary shell command runner (`non_blocking`, `execute_forked_window` for a visible console) |
| **Pythonxer** | Inline Python behind a `compile()` + **Ruff** correctness gate; always triggers downstream |
| **Sqler** | Python block against MS SQL Server via pyodbc |
| **Mongoxer** | Python block against MongoDB via pymongo |
| **Crawler** | HTTP fetch + optional link-walk + Ollama page analysis |
| **Googler** | Playwright Google search + top-N page text extraction |
| **Playwrighter** | Scripted real-browser automation (navigate/fill/click/extract/screenshot/assert; session carry) |
| **Apirer** | Configurable HTTP/REST client with latency logging |
| **Kalier** | Kali Linux bridge via MCP-Kali-Server (nmap/gobuster/nikto/sqlmap/hydra/john/metasploit…; authorized use only) |
| **Discoverer** | ProjectDiscovery suite (subfinder/httpx/naabu/katana/nuclei/cvemap→vulnx); self-provisioning private Go toolchain |
| **Nmapper** | Local-use-only nmap bridge (never bundles nmap; unprivileged connect-scan default; AUTHORIZED TARGETS ONLY) |
| **Unrealer** | Drives Unreal Engine 5 editor via Unreal MCP TCP :55557 (53-command surface with the XAIHT fork) |
| **Blenderer** | Drives Blender via the official Blender MCP add-on socket (localhost:9876; execute_code passthrough) |
| **STM32er** | Whole-STM32-line firmware bridge (PlatformIO backend or STM32F407VG template MCP); zero-config + fail-safe preflight; mission-critical |
| **ESP32er** | ESP32/ESP8266 firmware via PlatformIO Core CLI, zero-config bootstrap |
| **Arduiner** | Arduino/AVR/SAMD firmware via arduino-cli, zero-config |
| **ESPHomer** | ESPHome YAML smart-home firmware via esphome CLI, zero-config |
| **Gitter** | git operations (clone/pull/push/commit/`custom`) |
| **Reviewer** | LLM code reviewer over a git diff; verdict-first INI block |
| **Analyzer** | Deterministic multi-scanner static/security analysis (no LLM) |
| **Ssher** | Remote shell over SSH |
| **Scper** | File transfer over SCP |
| **Dockerer** | Docker / docker-compose front-end |
| **Kuberneter** | kubectl front-end |
| **Jenkinser** | Jenkins job trigger (CSRF crumb handling) |
| **Pser** | LLM-powered semantic process finder |
| **Prompter** | One-shot Ollama prompt → structured block |
| **Summarizer** | Polling LLM event-detector + one-shot summarizer modes |
| **File-Interpreter** | Multi-format document reader (DOCX/PPTX/XLSX/PDF/…; fast/complete/summarized) |
| **File-Extractor** | Raw-text sibling; Read-style line/offset/limit views |
| **Image-Interpreter** | Triple-model vision analyst (2 parallel interpreters + merger) |
| **Video-Analyzer** | Motion-verdict video watcher (deterministic motion gate + dual vision models + PASS/FAIL tokens; robotic-loop eye) |
| **J-Decompiler** | Java decompiler via bundled jd-cli |
| **De-Compresser** | Deterministic compress/decompress (.gz/.zip/.7z/.tar.gz; env-var password) |
| **Mover** | Move/copy files with wildcards/exclusions |
| **Deleter** | Pattern file deletion (immediate or event mode) |
| **File-Creator** | Atomic file writer (preferred for all file authorship) |
| **Shoter** | Screenshot of the primary display (read-only) |
| **Globber** | Read-only glob file discovery (Glob equivalent) |
| **Grepper** | Read-only regex content search (Grep equivalent; file:line:match) |
| **Editor** | Surgical exact-string in-place edit (unique-match guarded, base64 channel) |
| **Camcorder** | Webcam photo/video via OpenCV |
| **Recorder** | Microphone → WAV via sounddevice |
| **Whisperer** | Speech-to-text (faster-whisper local w/ CUDA→CPU fallback, or Groq/OpenAI cloud) |
| **Talker** | TTS via Ollama Orpheus; **female voices only by design** (§2.2); emotion tags |
| **AudioPlayer** | Audio playback to speakers (volume/loop/truncate) |
| **VideoPlayer** | Video playback with audio on a display (ffpyplayer + OpenCV) |
| **Mouser** | PyAutoGUI mouse control (reserved for genuine UI automation) |
| **Keyboarder** | PyAutoGUI keyboard control (reserved; never for code authorship) |
| **Windower** | Win32 window manager (focus/move/resize/arrange/list) |
| **MCP Doctor** | External-MCP catalog diagnostic/onboarding (transport/runtime detection, secret flags) |
| **Instant Messaging Doctor** | Telegrammer/Whatsapper diagnostics & safe repair; non-mutating by default; auto-launched after messaging failures |

### Notification Agents (9)
| Agent | Purpose |
|---|---|
| **Notifier** | In-browser DOM popup notifications on log patterns |
| **Emailer** | SMTP send |
| **RecMailer** | IMAP receive + LLM keyword analysis |
| **Whatsapper** | WhatsApp via official Cloud API (`cloud`) or unofficial Web automation (`web`) |
| **Telegrammer** | Telegram via official Bot API or user session; contact-name resolution |
| **Zavuerer** | Zavu unified SMS/WhatsApp/Telegram/Email/Voice REST API (smart routing + fallback) |
| **Monitor Log** | Log-file watcher + LLM event detection (canonical Raiser upstream) |
| **Monitor Netstat** | Network-connection watcher + LLM matching |
| **FlowHypervisor** | System watchdog over all agent logs; surfaces ATTENTION alerts |

### Utility Agents (6)
| Agent | Purpose |
|---|---|
| **Parametrizer** | Interconnection engine piping structured outputs into downstream configs (§12.5) |
| **FlowBacker** | Session-pool backup before cleanup |
| **FlowCreator** | AI flow designer (objective → `.flw` JSON); wrapped as `chat_agent_flowcreator` since migration 0186 |
| **Gatewayer** | Inbound HTTP-webhook / folder-drop gateway with auth/dedup/recovery |
| **Gateway Relayer** | Deterministic third-party webhook (GitHub/GitLab/Stripe…) → Gatewayer HMAC relay |
| **NodeManager** | Fleet registry: node inventory, health probes, state classification (display name is exactly `NodeManager`) |

### Cryptography Agents (3)
| Agent | Purpose |
|---|---|
| **Kyber-KeyGen** | CRYSTALS-Kyber post-quantum key generation |
| **Kyber-Cipher** | Kyber encryption |
| **Kyber-DeCipher** | Kyber decryption |

### Multi-Channel Bridges (1)
| Agent | Purpose |
|---|---|
| **TeleTlamatini** | Long-running Telegram bot bridging authorized users into the full Multi-Turn chat |

### External Coding-Agent Driver (1)
| Agent | Purpose |
|---|---|
| **ACPXer** | One external coding-agent CLI session per run (any of the 14 ACPX ids); visual multi-CLI relay via Parametrizer |

---

## 14. Creating a New Agent / Tool / Skill

### 14.1 Agent naming convention (CRITICAL — never mis-case a display name)
Single source of truth: the **`agentDescription`** DB field (seeded by the agent's migration), rendered **verbatim** in sidebar/canvas. Derive every other surface by lowercasing.

| Context | Casing | `STM32er` example |
|---|---|---|
| **Display** — DB `agentDescription`, canvas/sidebar label, tooltips, `agents_descriptions.md` rows, `chat_agent_registry.display_name`, docs prose, `"<Name> AGENT STARTED"` log | **exact, as designed** | `STM32er` |
| Pool/agent dir, `<name>.py`, pool name `<name>_N` | lowercase | `agents/stm32er/`, `stm32er_1` |
| CSS `.canvas-item.<x>-agent`, JS classMap key, `name.toLowerCase()` checks | lowercase / dash | `stm32er-agent`, `'stm32er'` |
| JS connector symbol `update<Name>Connection` (code identifier) | PascalCase-ish | `updateStm32erConnection` |
| `INI_SECTION_<TYPE>` / `END_SECTION_<TYPE>` + FlowHypervisor `<TYPE> SPECIAL NOTES:` headers | **ALL-CAPS** (separate convention — do NOT "fix") | `INI_SECTION_STM32ER` |

**STM32er** is mission-critical and the user is emphatic: exactly **`STM32er`** — NEVER `STM32Er` / `STM32ER` / `Stm32Er` / `Stm32er`. (Beware: the `tlamatini-agent-naming` skill's own example table says `Node Manager`, but the real seeded display is `NodeManager` — DB wins.)

### 14.2 New workflow agent — the 8 required places
Authoritative runbooks: `.claude/skills/tlamatini-agent-creation/SKILL.md` (700+ steps, 26 phases), in-app skills `create-new-agent` / `tlamatini-new-acp-agent`, and `Tlamatini/.agents/workflows/create_new_agent.md`. In short, a new agent touches: (1) backend pool script `agent/agents/<name>/<name>.py` + `config.yaml`; (2) connection-update Django view + URL; (3) migration seeding the `Agent` row (+ demo prompts, §14.3); (4) CSS gradient `.canvas-item.<name>-agent` (4-color gradient rule — follow the existing palette families); (5) the four JS surfaces (classMap, connectors, config dialog, connection handlers in `acp-agent-connectors.js`); (6) Multi-Turn wrapper spec in `chat_agent_registry.py` if chat-runnable; (7) docs (`agents_descriptions.md` row, `agentic_skill.md` for FlowCreator, FlowHypervisor `monitoring-prompt.pmt` notes); (8) tests + `npm run lint` + `python -m ruff check`. Connection-field semantics and `secret_paths` are declared in the AgentContract registry (`agent/services/agent_contracts.py`).

### 14.3 Catalog-of-prompts gate (HARD, NON-NEGOTIABLE)
Every agent that ships a wrapped `chat_agent_<name>` tool MUST also seed **at least one** example prompt into the Catalog of Prompts (migration `0NNN_add_<name>_demo_prompts.py` → `Prompt` model via `update_or_create`). A Multi-Turn agent without a catalog prompt is **INCOMPLETE — the task is not done**. (Canvas-only agents exempt.) Obey §6 prompt-table rules (append-only id + `sort_rank`, rank 10 reserved for the Step-by-Step opener).

**Parameter grammar (standardized v1.44.0, migrations 0182-0185)**: `[[ ... ]]` = value the **USER** fills (collected in a fill-in block at the TOP of the prompt with an unfilled-guard line beneath; optional inputs as `[[ ... — OPTIONAL, default: X ]]`); `{{ ... }}` = value **Tlamatini fills at RUNTIME**; `< ... >` = **REPORT slot only** (where the answer prints), never an input. Never hardcode a scratch path in a prompt — obey the Temp/Templates policy (§19).

### 14.4 New tool / MCP context provider
Reference: in-app skill `create-new-mcp` + `Tlamatini/.mcps/create_new_mcp.md`. Three classes: tool-only (`@tool` in `tools.py` + `tool_<name>_status` toggle + `Tool` row migration), MCP-backed context provider (`mcp_*_server.py` + `chain_*_lcel.py` sidecar + `Mcp` row + `factory.py` wiring — note the description-string recognition hardcoding, §20), or both. If the tool spawns a console child, add its name to `_PROCESS_SPAWNING_TOOL_NAMES` in `mcp_agent.py` (§21).

### 14.5 New skill
Guide: `Tlamatini/.skills/create_new_skill.md`; canonical worked example of an in-process skill shelling to shipped scripts: `skills_pkg/flow_making/`. Validate with `_meta/lint.py` + `quick_validate`. After adding: it appears after `boot_skills()` (or the Reload action); keep the self-modify/self-update inclusion skills' invariants in mind (any new asset must flow into release + snapshot carriers).

---

## 15. Frontend Architecture

**No SPA framework** — server-rendered Django templates (only 4: `agent_page.html`, `agentic_control_panel.html`, `login.html`, `welcome.html`) + vanilla JS with CDN libraries (jQuery 3.7.1 + jQuery-UI 1.13.3 draggable canvas, Bootstrap 5, highlight.js, marked, DOMPurify, Sortable). Cross-file communication is via **script-scope globals** (whitelisted in `eslint.config.mjs`). Cache-busting: `?v={{ STATIC_VERSION }}` on every static URL (bump via the `tlamatini-static-version-bumper` skill after frontend changes). 10 CSS files under `static/agent/css/`.

**33 JS modules** (`static/agent/js/`):

- **Chat page (9)**: `agent_page_init.js` (WebSocket setup, context-dir menu), `agent_page_chat.js` (messages; `exec-permission-request` frames; Cancel-during-self-healing), `agent_page_canvas.js`, `agent_page_context.js`, `agent_page_dialogs.js` (incl. `showExecPermissionDialog`), `agent_page_layout.js`, `agent_page_state.js` (toggle helpers), `agent_page_ui.js`, `chat_image_paste.js` (Ctrl+V / drop screenshot → saved to `<app>/Temp/image_<ts>.jpg`, absolute path spliced into the chat box at the caret; the `paste` listener lives on `document`, chips row must stay counted in `computeFormMinHeight()`).
- **ACP designer (14)**: `agentic_control_panel.js` (entry), then strict load order: `acp-globals.js` (#1 — shared state + `updateCanvasContentSize()`), `acp-session.js`, `acp-undo-manager.js`, `acp-agent-connectors.js` (1,698 lines; 50+ connection handlers), `acp-running-state.js`, `acp-control-buttons.js`, `acp-validate.js`, `acp-canvas-core.js`, `acp-flow-snapshot.js` (`buildACPFlowSnapshot()` → `schemaVersion: 2`), `acp-canvas-undo.js` (1024 actions), `acp-file-io.js`, `acp-layout.js`, `acp-parametrizer-dialog.js`, plus `canvas_item_dialog.js`, `contextual_menus.js`.
- **Shared/chat-runtime (10)**: `tools_dialog.js` (tool toggles + Catalog of Prompts — primary load = ONE `GET /agent/list_prompts/`; the `prompt-1..N` probe loop is a gap-tolerant offline fallback), `skills_dialog.js` (ACPX-Skills dropdown), `external_mcps_dialog.js` (External ▸ MCPs), `access_keys_wizard.js` (Config ▸ Access Keys Wizard — one guided place for every provider secret), `contacts_dialog.js` (contacts book for messaging agents), `chat_page_runtime_poller.js`, `shared-runtime-dialogs.js`, and the remaining shared helpers.

**Const-poison contract (v1.38.1)**: module-level state that ANY other JS file reassigns at runtime (`tools`/`agents`/`skills` arrays, chat history, canvas flags) MUST be declared `let`, never `const`. Per-file ESLint cannot see cross-file reassignment — a `let`→`const` "cleanup" lints green then kills the page at load (`TypeError: Assignment to constant variable`). Guarded by `agent/test_frontend_mutable_state.py` over both source and `staticfiles`.

**Ask Execs frontend**: checkbox `#ask-execs-enabled` enabled only while Multi-Turn is on; modal shows Tool/params/program/shell with Proceed/Deny; X hidden, Esc disabled, close = Deny (idempotent); `exec-permission-response` frame MUST include a `message` key (`consumers.receive` reads it unconditionally). Mid-run unchecking sends `set-ask-execs-runtime` to relax the current run. Toolbar toggles intentionally stay clickable during runs.

**Context directory picker**: Context ▸ Set directory as context uses the backend native Win32 picker (`views.pick_context_directory_view`) returning the REAL absolute path at any depth under the app root. **Do NOT revert to `window.showDirectoryPicker()`** — it structurally exposes only the leaf folder name.

Lint: `npm run lint` / `npm run lint:fix` (ESLint 10, `Tlamatini/agent/static/agent/js/`).

---

## 16. Build, Release & Versioning

### 16.1 The 3-step release pipeline (canonical order)
Run with a **system Python 3.12 — never the carried `<repo>/python` interpreter** (builds abort early if so). `build_all.cmd` wraps steps 1–3.

1. **`python build.py [--self-modify] [--version X.Y.Z]`** — resolves/emits version (writes `agent/_version.py` + `Tlamatini.version.txt`, exports `TLAMATINI_VERSION`) → cleans `build/`/`dist/` → provisions the carried Python (verifies every agent/MCP runtime lib imports + `python -m ruff` runs — aborts on failure; asserts numpy + cv2 in BOTH Pythons; installs Playwright browsers) → fresh `db.sqlite3` + `collectstatic` → PyInstaller on `manage.py` (huge `--add-data`/`--hidden-import` list; custom `pyinstaller_hooks/hook-numpy.py`; excludes tkinter/magic) → post-build copies (`config.json`, `prompt.pmt`, `Tlamatini.md`, `agents/`, `skills_pkg/`, `jd-cli/`, sanitized empty `contacts.json`, agents manifest; optional `TlamatiniSourceCode/` snapshot with `--self-modify`; bundles carried Python + Playwright browsers + JRE + Git) → runs the exe for `migrate` + non-interactive `createsuperuser` (default `user`/`changeme`) → renames to `Tlamatini.exe` → zips `dist/manage` → **`pkg.zip`** (the real artifact), deletes `build/`/`dist/`. A `.build.lock` prevents concurrent builds.
2. **`python build_uninstaller.py [version]`** — freezes `uninstall.py` (tkinter GUI) → `Uninstaller.exe` (own VERSIONINFO), copied to project root.
3. **`python build_installer.py [version]`** — freezes `install.py` → `Installer.exe` (windowed, generated splash). `pkg.zip` stays EXTERNAL (installer launches instantly). Renames `dist/Installer` → **`dist/Tlamatini_Release_v<version>/`** and moves `pkg.zip` + `Uninstaller.exe` in. Zip that folder to distribute.

### 16.2 Public vs private release twins
- **`build_complete_private_release.py`** — KEYED build for Angela's own machine, must NOT be published: `regen_secrets.py --mode keyed --keys-file data.keys` → `build.py --self-modify` (default ON) → steps 2–3 → zip `..._PRIVATE_KEYED_...`. Real contacts ship when `contacts.private.json` exists. **No scrubbing, no leak audit.**
- **`build_complete_public_release.py`** — PUBLIC build: byte-for-byte backup of touched files → `regen_secrets.py --mode push-able` + sanitize `external_mcps.json` to empty → **tree-wide scrub** of leak targets (auto-loaded from gitignored `.private_targets.json`) → `build.py` (`--self-modify` opt-IN) → **VERIFY**: extract `pkg.zip`, run `check_private_data.py --local` (blocks only on genuinely-unique PII — `@`-containing or ≥7-digit values) → steps 2–3 → zip `..._PUBLIC_CLEAN_...` → `finally:` **restores the working tree byte-for-byte** and re-keys secrets. Never rewrites git history. `--keep-scrubbed` exists and is dangerous.
- **Angela's name ("Angela López Mendoza", any accent/case variant) and `@angelahack1` are NEVER scrubbed in either build.**

### 16.3 Versioning (SemVer 2.0.0, git-tag-derived)
Single source of truth = **annotated git tags `vX.Y.Z`**. No version string is hand-edited in source. Build-time precedence: `--version` flag → `TLAMATINI_VERSION` env → `git describe --tags --abbrev=0 --match 'v[0-9]*'` (always the **bare base tag** — no `.devN`, no `+gSHA`, no `.dirty` ever) → `0.0.0+unknown` sentinel. Runtime resolver: `agent/version.py::get_version()` (no Django dep); build shim: root `versioning.py`; generated `agent/_version.py` is gitignored — never commit, never hand-edit. Surfaces: About dialog (`{{ version }}`), startup banner, open `GET /agent/version/`, Win32 VERSIONINFO of all three exes, release folder name. Release cut: clean tree on `main` → pick bump (MAJOR breaking / MINOR feature / PATCH fix) → `git tag -a vX.Y.Z` → push tag → 3-step build. Never delete/re-use pushed tags — bump forward. Full contract: `VERSIONING.md`.

### 16.4 Install / update / uninstall
- **`install.py`** (Installer.exe): reads version from exe ProductVersion/git tags; extracts `pkg.zip` (sits next to it) to a user-chosen dir; writes `CreateShortcut.json` + runs `CreateShortcut.ps1`; registers the `.flw` association (`register_flw.ps1`); writes the `HKCU\Software\XAIHT\Tlamatini` companion-app registry key.
- **Self-update**: in-app About ▸ Check for updates → `agent/self_update.py` stages the build → launches external `apply_update.ps1` from `%LOCALAPPDATA%\Tlamatini\updater` → kills Tlamatini's tree (never itself) → renames `agents`→`agents_backup` → replaces everything except the `$Preserve` set (`config.json`, `external_mcps.json`, `contacts.json`, `DB`, `Temp`, `Templates`, `Uninstaller.exe`, generated dirs) → moves new build in → `DB/post_update_migrate.flag` → migrate → relaunch. Keeps user config/database/keys.
- **`uninstall.py`**: removes installed files EXCEPT `agents/` (user agent state preserved); unregisters `.flw`; removes shortcuts.

---

## 17. Privacy, Secrets & Release Scrubbing

**What counts as private data**: Angela's emails, phone numbers, legal-name variants, messaging handles, API keys/tokens/secrets, private keys — supplied at runtime (never hardcoded) via `--targets-file`, `--target`, env `CHECK_PRIVATE_DATA_TARGETS`, or the gitignored `.private_targets.json` default. Her display name and `@angelahack1` are explicitly KEPT everywhere.

- **`check_private_data.py`** ("god-of-gods auditor") scans a local tree and/or cloned remote across layers: plain text (utf-8/16/latin-1), raw bytes/hex, a fuzzy "homomorphic" layer (base64/base32/hex/url-encode/rot13/reversed/leetspeak variants, accent-insensitive), steganography (carved strings, trailing-after-EOF, EXIF, LSB bit-planes), filesystem/process forensics, optional LLM deep-review via Ollama (`--no-llm` skips). Also pattern-scans structural secrets (PEM/OpenSSH/PuTTY keys, AWS/Google/Slack/OpenRouter `sk-or-v1-…`, bearer tokens, JWTs, high-entropy base64). Writes `private_data_audit_report.json`. Exit codes: 0 clean / 1 findings / 2 no targets. Runs as the **verification gate** inside `build_complete_public_release.py` and manually on demand. Tests: `test_check_private_data.py` (100+ cases).
- **`test_private_data_guard.py`** — GIT-HISTORY INTEGRITY GUARD (root commit SHA immutable, commit count only grows, required tags exist, forward-only scrub holds) + GLOBAL BANNER GUARD.
- **`test_author_banner.py`** — every `.py`/`.js`/`.css`/`.mjs` must carry the author banner (§19.1).
- **GitHub workflow** `.github/workflows/name-guard.yml` — the only CI: auto-scrubs a disallowed name across all branches (push/PR/15-min cron), opens an issue when it fires. There is no build/test CI — nightly quality runs are a separate local automation.
- **Secrets hygiene in the working tree**: `config.json` ships with `<KEY goes here>` placeholders; real keys live in `data.keys` (gitignored KEY=VALUE vault), `open_router.key`, env vars; `regen_secrets.py --mode keyed|push-able` toggles them across `config.json` + 7 agent `config.yaml`s (telegrammer, whatsapper, teletlamatini, emailer, recmailer, zavuerer, discoverer) — YAML edited line-by-line to preserve comments, atomic writes. Gitignored: `*.key`, `data.keys`, `.private_targets.json`, `private_data_audit_report.json`, `contacts*.json`, `external_mcps.json`, `_version.py`, `db.sqlite3`, `/python/`, `/Temp/`, `/Templates/`, `Go/`, pools, runtime state.
- ⚠️ **OPEN ISSUE to tell Angela about (found 2026-07-22): `Tlamatini/agent/external_mcps.json` in the working tree currently contains live-looking tokens (a GitHub PAT and a Snyk UAT key).** The file is gitignored as user state, but the local copy should be rotated/emptied; do not propagate its contents anywhere (builds already sanitize it).

---

## 18. Testing & Lint

### ⛔ MANDATORY DIRECTIVE — FORBIDDEN HEADLESS TESTS (Angela, 2026-07-07)
**HEADLESS / INVISIBLE AUTOMATED TESTS ARE FORBIDDEN. EVERY automated test MUST run VISIBLE — a HEADED browser (Playwright `headless=False`, real Chrome preferred) on Angela's REAL desktop, so she can SEE every step live.** Hard, non-negotiable, forever.

- Never pass `--headless` (the chat-test harness flag is disabled — it refuses).
- Drive the **real Tlamatini chat GUI** (`http://127.0.0.1:8000/agent/agent/`) — never fake or bypass the UI.
- Run in a **visible foreground window**; never a hidden/detached/background job.
- Verify each step with a **FULL-SCREEN screenshot** (entire desktop, taskbar clock visible); one photo per test + a live `SUMMARY.html`.
- **NEVER LIE**: a stale chat-history scrape, a transient self-healing "🔁 Tactic #…" status, or a timed-out answer must NEVER be recorded as a pass. Clear chat history per test, re-assert Multi-Turn ON at every send, reject already-seen answers.
- If a test cannot be made visible, **do NOT run it — tell Angela**.
- Reference runner: `.claude/skills/tlamatini-daily-chat-test/harness/` (the daily visible-Chrome regression; pinned toggles: Multi-Turn ON; ACPX/Ask-Execs/Exec-Report/Internet OFF).

### Test inventory & commands
- **Django unit/integration** (Django-unittest style; pytest is installed but there is NO pytest config — natural runner is Django's): `cd Tlamatini && python manage.py test agent` — `agent/tests.py` (7,230 lines) + 63 `agent/test_*.py` files (cancellation, flow contracts, django-port matrix, external-MCP, per-agent imports, frontend mutable state, …).
- **Repo-root guards** (plain unittest, no Django): `python -m unittest test_author_banner` · `python -m unittest test_check_private_data` · `python -m unittest test_private_data_guard`.
- **E2E** (`Tlamatini/tests_e2e/`, 6 headed Playwright suites; root `Tests/`, `AuxTests/`): run as plain scripts against a LIVE server — `python Tlamatini/tests_e2e/test_create_flow_visual.py` (env `TLAMATINI_USER`/`TLAMATINI_PASS`, `BASE_URL` default `http://127.0.0.1:8000`). Not pytest-collected.
- **Lint**: `python -m ruff check` (Ruff 0.14.x is a REQUIRED runtime gate — Pythonxer shells it before running any script; never unpin) · `npm run lint` / `lint:fix`.

---

## 19. Coding Conventions & Critical Rules

1. **Author banner on every source file** — every `.py`/`.js`/`.css`/`.mjs` must contain the `Tlamatini Author Banner` block naming `Angela López Mendoza` (copy it from any existing file; `_version.py` exempt). Enforced by `test_author_banner.py`. The About window names `ANGELA LÓPEZ MENDOZA` in caps; `agent/Tlamatini.md` names her. Never remove banners; release builders scrub other data automatically.
2. **Reloader gates** — never start the MCP servers or any singleton thread unconditionally in `apps.py`: gate on command (`runserver`/`startserver`/`daphne`/`asgi`) + `RUN_MAIN == 'true'` under the reloader + a `global_state` flag (`apps.py`). Duplicate binds → `WinError 10048`.
3. **Port config** — never hardcode 8000; honor `config.json:django_port` through `manage.py`'s fail-open helpers; an explicit CLI port always wins (§5).
4. **Temp & Templates policy (prompt.pmt Rules 15/16)** — EVERY transient file lives under `<app-root>/Temp` (`TLAMATINI_TEMP`; pinned by `manage.py::_enforce_app_temp_dir()` + `settings.py::_pin_temp_directory()`; resolver `agent/path_guard.py`). Nothing leaks to `C:\Temp` or `%TEMP%`. Firmware/engine project scaffolds (STM32er/ESP32er/Arduiner/Unrealer) default to `<app-root>/Templates` (`TLAMATINI_TEMPLATES`) unless the user names another path. Temp-creating agents carry an explicit module-top `if os.environ.get('TLAMATINI_TEMP')…` guard — an `if`-block, never a top-level `def` (trips ruff E402). New scratch-writing code routes through `<app>/Temp`.
5. **Fail-open everywhere** — optional subsystems (MCP, ACPX, skills, GPU perf, discovery) must log-and-continue, never block Django startup.
6. **Frozen/source duality** — every path resolution must handle both `getattr(sys, 'frozen', False)` (exe dir / `_MEIPASS`) and source mode. Use `path_guard.py` / `config_loader.py` helpers; never hand-roll `__file__` math that breaks frozen.
7. **CRLF line endings** — most Python/JS files are CRLF; match the existing file's style when editing. (This KIMI.md is LF-normalized.)
8. **Prompt contract** (`agent/prompt.pmt`) — code blocks use `BEGIN-CODE<<<FILENAME>>>` / `END-CODE` (NOT markdown fences); tables are HTML; answers end with `END-RESPONSE`.
9. **Prompt table** — append-only `idPrompt` + `sort_rank` discipline (§6); every wrapped agent ships a catalog demo prompt (§14.3).
10. **No git-history rewrites** — see the ⛔ guard at the top of this file. Sensitive data is removed only by new forward commits.
11. **Version** — git tags only; `_version.py` is generated, never committed, never hand-edited (§16.3).
12. **Secrets** — placeholders in the tree; real values via `data.keys` + `regen_secrets.py` (§17). Never commit real keys; never print key values in chat/logs.
13. **Chat runs isolation** — chat-launched agents run from `agents/_chat_runs_/`; flows from `agents/pools/`; both cleaned on boot and reaped on shutdown (§21).
14. **Dogfooding** — use Tlamatini's own agents/skills/tools for the work (§26.2).
15. **New console-spawning tool** → add it to `_PROCESS_SPAWNING_TOOL_NAMES` in `mcp_agent.py`, or rely on Tier-2 sweep (§21).
16. **New rebuild/release asset** (agent, file, dependency, migration, static asset) → it must flow into ALL carriers: `build.py` copy lists, `copy_source_assets.py` snapshot, `apply_update.ps1` handling. The `.claude` skills `tlamatini-self-modify-inclusion` / `tlamatini-self-update-inclusion` own these audits.

## 20. Known Hardcoded Assumptions & Pitfalls

Hardcoded assumptions (know before changing these subsystems):

1. `factory.py` recognizes only `System-Metrics` and `Files-Search` **by Mcp description string**.
2. The frontend MCP dialog is hardcoded for exactly two checkboxes; Tool UI is dynamic, MCP UI is not.
3. `get_mcp_tools()` returns LangChain tools, NOT MCP services (§9).
4. `ask_rag()` does not fetch MCP data itself; Files-Search main path uses `FileSearchRAGChain`, not `mcp_files_search_client.py`; `mcp_files_search_client_uri` in config is unused by the main chain; `FileSearchRAGChain` falls back to `localhost:50051`.
5. Tool status keys (`tool_<name>_status`) are handwritten and can drift.
6. `mcpContent` is stored as string, not boolean.
7. `tlamatini.log` is **truncated on every server start** (mode `'w'`), no rotation — copy it before restarting if you need history.
8. The web port is configurable (`django_port`, §5); still genuinely hardcoded: direct `daphne`/`uvicorn` launches, `:8765`/`:50051` helpers, TeleTlamatini's `tlamatini.base_url`.
9. Carried-Python media libs: Recorder/Camcorder/AudioPlayer/VideoPlayer/Whisperer run under the CARRIED Python (`<install>/python`), NOT the frozen exe — numpy + cv2 must exist in BOTH Pythons; `build.py` aborts otherwise. A dep pinned in `requirements.txt` but missing from the carried Python crashes the pool agent at runtime.
10. Frontend `let`-not-`const` for cross-file mutable globals (§15, const-poison).
11. Stale counts persist in docs/comments across the repo: README badge `TOOLS-75` (actual ~103), "84 drag-and-drop" (actual 85 on disk), `agents_descriptions.md` intro "83", `tlamatini_mcp_server.py` docstring "82", `TLAMATINI_MCP.md` "57/62 tools" (actual 102), ACPX.md "57 agents/32 wrapped/20 skills", `config.json` comment "7 ACPX tools" (actual 12), `create-new-agent`/`flow-making` skills "83". **The verified numbers live in §1 of this file — fix stale docs when you touch them.**

Common pitfalls (deduplicated; the dated fix contracts live in `docs/claude/recent-fixes.md`):

- **Do NOT revert** these deliberate designs: full-surface Multi-Turn binding (§8); native Win32 context-dir picker (§15); canvas two-layer DOM + no upper position clamp (§12.3); `save_message`-before-exec-report ordering (§12.6); reloader gates (§19.2); fail-open port resolution (§5); Ask-Execs payload-whitelist flags (§8); the oneshot-prompt path in ACPX runtime (Windows CLI quoting); the `subprocess.Popen` monkey-patch seatbelt in pool agents (§21).
- **Payload-rebuild whitelist**: per-request flags (`ask_execs_enabled`, `exec_report_enabled`, `conversation_user_id`, …) must survive `UnifiedAgentChain.invoke`'s payload rebuild — a classic drop-on-rebuild bug class.
- **Playwright in async**: browser automation in the consumer path must run off the event loop (sync Playwright in async context deadlocks).
- **Pythonxer always triggers downstream** after a passing gate — do not "optimize" it into conditional triggering.
- **Adding a wrapped chat-agent tool** means BOTH a `WRAPPED_CHAT_AGENT_SPECS` entry AND the toggle/migration rows AND the catalog prompt — partial registration silently drops the tool from the surface.
- **`external_mcps.json` is user state** (gitignored) — never commit real catalogs/tokens; builds sanitize it (§17).

## 21. Orphan-Process Cleanup (the `conhost.exe` reaper)

`agent/orphan_reaper.py` runs a **three-tier reaper** cleaning Windows `conhost.exe`/`openconsole.exe` companions and zombie descendants every console subprocess can leave behind (conhost inherits the parent EXE's icon — users were seeing "Tlamatini leaking processes" in Task Manager).

- **Tier 1** — `MultiTurnToolAgentExecutor._reap_after_tool()` after every Multi-Turn tool call in `_PROCESS_SPAWNING_TOOL_NAMES` plus every `chat_agent_*` and `acp_*` (and on the tool-exception path). Cheap path: zombie descendants of `os.getpid()` + console-host orphans. Silent; survivors accumulate for Tier 2.
- **Tier 2** — `AgentConsumer._tier2_orphan_sweep()` once per answer, AFTER the reply broadcasts (never delays the reply). Adds the agent-pool cmdline scan. Survivors of BOTH tiers are broadcast to the chat as a second `agent_message` listing `name + PID` for manual kill.
- **Tier 3** — `AgentConfig.ready()` atexit/SIGINT/SIGBREAK full sweep; logs `--- [Tier-3 reaper] killed=… survivors=…` to `tlamatini.log`.

Companion hardening (prevention): spawn sites use `CREATE_NEW_PROCESS_GROUP | CREATE_NO_WINDOW | DETACHED_PROCESS` with stdio→DEVNULL; ACPX runtime adds `_windows_creationflags()` + `_kill_process_tree()` (psutil, terminate → wait 2 s → kill); **every pool-agent script installs a top-of-module `subprocess.Popen.__init__` monkey-patch (`_chg_guarded_init`) defaulting `creationflags` to `CREATE_NO_WINDOW`** unless the caller explicitly asked for a console — the seatbelt for future tools.

Safety contract: **the reaper must never raise into the caller** — every external call is try/except-wrapped, survivors are recorded not re-raised, a psutil-import failure degrades silently. A cleanup that crashes the chat path is worse than the orphans.

## 22. Self-Knowledge & Self-Modification

- **Self-knowledge** — the LLM carries a first-person self-reference file, `agent/Tlamatini.md`, injected into `prompt.pmt`'s `<self_knowledge>` block at prompt-build time by `agent/rag/config.py` (covers every chain; brace-escaped; fails open). `build.py` always ships it both via `--add-data` and as an install-root copy so frozen "next to the exe" resolution works.
- **Self-modification** — an OPTIONAL `TlamatiniSourceCode/` directory at the install root, generated fresh by `copy_source_assets.py` when `build.py --self-modify` is passed, holds her complete rebuildable source snapshot (all .py/.js/.css/.ps1/.pmt/.yaml/build scripts; media + jd-cli.jar omitted; secrets redacted to `<KEY goes here>`; ships `_SOURCE_SNAPSHOT_MANIFEST.json` + `_REBUILD_INSTRUCTIONS.md`). Present = a **self-able-modify** build (she can read/modify/rebuild her own `Tlamatini.exe`); absent = **not-self-able-modify**. A generation failure falls back to the legacy static copy. The `tlamatini-self-modify-inclusion` skill keeps the snapshot complete whenever new rebuild inputs appear.

## 23. How to Run

```bash
# From source (Python 3.12.10)
cd Tlamatini
python -m venv venv && venv\Scripts\activate
pip install -r requirements.txt
python Tlamatini/manage.py migrate
python Tlamatini/manage.py createsuperuser
python Tlamatini/manage.py runserver --noreload
# or: python Tlamatini/manage.py startserver   (custom command = runserver, reloader OFF)
# Open http://127.0.0.1:8000/  (root = login; chat UI at /agent/agent/)
```

- Plain `runserver` (reloader ON) also works since 2026-07-11 via the `RUN_MAIN` gate — auto-reload on edits is safe.
- Default credentials (installer builds): `user` / `changeme`.
- Port taken / `WinError 10013`? Set `django_port` in `config.json` (§5) — no rebuild needed.
- Ollama must be reachable at `ollama_base_url` with the configured models pulled; cloud Ollama models are the shipped defaults.
- Frozen build: launch `Tlamatini.exe` (or the Start-menu shortcut / a `.flw` file) — browser opens at the configured port.

## 24. File Paths Quick Reference

| What | Path |
|---|---|
| Main config | `Tlamatini/agent/config.json` (frozen: next to `Tlamatini.exe`) |
| System prompt template | `Tlamatini/agent/prompt.pmt` |
| LLM self-knowledge | `Tlamatini/agent/Tlamatini.md` |
| App log (truncated each boot) | `Tlamatini/tlamatini.log` |
| Database | `Tlamatini/db.sqlite3` (hot-swap: `Tlamatini/DB/ToLoad/`) |
| Agent templates (85) | `Tlamatini/agent/agents/<name>/` |
| Flow session pools | `Tlamatini/agent/agents/pools/<session_id>/` |
| Chat-agent runtime copies | `Tlamatini/agent/agents/_chat_runs_/` |
| Skills packages (28) | `Tlamatini/agent/skills_pkg/<name>/SKILL.md` |
| Skill audit log | `~/.tlamatini/skill-audit/` |
| ACPX transcripts | `agent/acpx/session_store.py` FileSessionStore (NDJSON) |
| Transient scratch | `<app-root>/Temp/` (`TLAMATINI_TEMP`) |
| Project scaffolds | `<app-root>/Templates/` (`TLAMATINI_TEMPLATES`) |
| External-MCP catalog (user state) | `Tlamatini/agent/external_mcps.json` |
| Secrets vault (gitignored) | `<repo>/data.keys` |
| Release artifact | `<repo>/pkg.zip` → `dist/Tlamatini_Release_v<ver>/` |
| Companion-app registry key | `HKCU\Software\XAIHT\Tlamatini` |
| Agents manifest (companion apps) | `<agents_root>/_tlamatini_agents_manifest.json` |

Ports: `8000` web (default; `django_port`) · `8765` System-Metrics WS · `50051` Files-Search gRPC · `11434` Ollama · `5000` optional Kali bridge · `55557` Unreal MCP TCP · `9876` Blender MCP socket.

## 25. Deeper Documentation (consult-on-demand)

This file is self-contained for day-to-day work. For depth, read these on demand (Kimi: read them explicitly — there is no auto-import):

- **`docs/claude/recent-fixes.md`** — the dated "do NOT revert / keep these surfaces aligned" fix log. **Read it before modifying or reverting code in ACPX, Flow Compiler, planner, Exec Report, ACP canvas, wrapped chat-agent parsing, desktop-UI agents, STM32er bootstrap, `prompt.pmt`, `regen_secrets.py`, or logging filters.** Prepend new fix entries there.
- `docs/claude/architecture.md` — config, system prompt/identity, layers, app log, services, DB models.
- `docs/claude/multi-turn.md` — Multi-Turn internals, Step-by-Step, Ask Execs, self-healing, Create Flow.
- `docs/claude/exec-report.md` — Exec Report pipeline + ordering contract.
- `docs/claude/agents.md` — Agent Contract registry + agent lifecycle + FlowCreator/FlowHypervisor.
- `docs/claude/acpx.md` — ACPX transports, decision matrix ("when the user says ACPX").
- `docs/claude/mcp-tools.md` — adding MCPs/tools/skills; External-MCP client how-to.
- `docs/claude/frontend.md` — JS modules + Canvas DOM contract + Flow Compiler pipeline.
- `docs/claude/gotchas.md` — Claude API client, build/lint, versioning quick-map, work style.
- **`BookOfTlamatini.md`** — the master user manual + changelog (~457 KB; 10 parts + bonus chapters + appendices).
- `ACPX.md` — standalone ACPX guide ("complete guide for dummies" → internals → operator runbook).
- `VERSIONING.md` — the full SemVer contract.
- `agents_descriptions.md` — authoritative agent purpose text (drives UI tooltips; keep it in sync).
- `docs/companion-app-discovery.md` — FlowPills discovery contract.
- `Tlamatini/.agents/workflows/create_new_agent.md`, `Tlamatini/.mcps/create_new_mcp.md`, `Tlamatini/.skills/create_new_skill.md` — creation guides.
- `PIVOT_CHANGES.md` — append-only surgical change/rollback log.
- Dated design/proposal docs (informational): `Discoverier-new-agent.md`, `FirstFinalPlanToSpeedUp.md`, `surgical_improving_speed_of_Tlamatini_by_a_factor_of_3X.md`, `docs/stm32er_all_families_proposal.md`, `MessagingConnectorAssistant_Design.md`.

## 26. Kimi-Specific Notes & Dogfooding Directive

### 26.1 How this file works for Kimi
- Kimi has no `@`-import mechanism and no SessionStart hooks — **this file IS the session-start guidance**. Read it fully at the start of any Tlamatini task, then consult §25 files on demand.
- The `mcp__tlamatini__*` tools are available to Kimi whenever the root `tlamatini` MCP server (`.mcp.json`) is connected. In Kimi Work, tool schemas are lazy-loaded: call `select_tools` with the exact names before first use. Discovery tools: `mcp__tlamatini__tlamatini_list_agents`, `mcp__tlamatini__tlamatini_list_skills`, `mcp__tlamatini__tlamatini_read_skill`.

### 26.2 MANDATORY DIRECTIVE (Angela, 2026-06-14) — USE TLAMATINI'S OWN SKILLS/TOOLS/AGENTS
From the very start of a session, perform the work with **Tlamatini's OWN** agents, tools and skills — Executer, Pythonxer, File-Creator, Mover, Deleter, Playwrighter, Blenderer, the `mcp__tlamatini__*` wrapped tools, and the SKILL.md skills — NOT the assistant's built-in tools, to **dogfood** them on real work, surface their errors, and keep fixing them. If a Tlamatini tool lacks a capability, fix or extend that tool instead of falling back. The shell is only a launcher of last resort.

**Tool correspondence — Kimi built-in → the Tlamatini tool to use INSTEAD** (`mcp__tlamatini__*` prefix; `tlamatini_list_agents` enumerates every one):

| Kimi built-in | Use INSTEAD | Key params / notes |
|---|---|---|
| **Write** (create a file) | `file_creator` (File-Creator) | `file_path`, `content` (or `content_b64`); creates parent dirs |
| **Edit** (find/replace) | `editor` (Editor) | exact-unique `old_string`→`new_string`; `replace_all`; `*_b64` byte-exact channel |
| **Grep** (content search) | `grepper` (Grepper) | `pattern` (regex), `path`, `glob`, `case_insensitive`, `output_mode` |
| **Glob** (find files) | `globber` (Globber) | `pattern`, `path`, `sort_by`, `max_results` |
| **Bash** (shell command) | `executer` (Executer) | `script`; `non_blocking:true` to detach; `execute_forked_window:true` for a visible console |
| **Bash** (run Python) | `pythonxer` (Pythonxer) | inline Python behind the compile()+Ruff gate |
| browse a site / browser automation | `playwrighter` (Playwrighter) | `start_url` + `steps_json` (goto/click/fill/extract/screenshot) |
| move / copy a file | `mover` (Mover) | glob-capable |
| delete a file | `deleter` (Deleter) | glob-capable |
| git commands | `gitter` (Gitter) | `command='custom'` passes a raw git subcommand |
| web search | `googler` (Googler) | Google search + extract |
| audio/video/camera/mic, TTS/STT, firmware, 3D | the matching agent — `talker`, `whisperer`, `recorder`, `camcorder`, `audioplayer`, `videoplayer`, `stm32er`, `esp32er`, `arduiner`, `esphomer`, `blenderer`, `unrealer`, `kalier`, `windower`, `mouser`, `keyboarder`, `shoter`, … | no built-in equivalent exists — always the agent |

**Reading files**: there is no raw-`cat` Tlamatini agent (File-Interpreter/File-Extractor interpret; Grepper/Globber search). Prefer Grepper/Globber to locate code and File-Interpreter to summarize; Kimi's **Read** is the narrow last-resort exception when you need exact bytes to author an Editor `old_string`.

**Transient-outage fallback (allowed, must be stated)**: if a `mcp__tlamatini__*` tool is briefly blocked and you already retried, you MAY fall back to the matching Kimi built-in to avoid stalling — but say so explicitly in your reply as an outage workaround, and switch back the instant the Tlamatini tool is reachable.

### 26.3 Visible agents & tests from Kimi
- Desktop/visible agents (headed Playwrighter, forked Executer/Pythonxer consoles, Shoter/Mouser/Keyboarder/Camcorder/VideoPlayer windows): when driven through `mcp__tlamatini__*` the Django server spawns them and they already render on Angela's desktop — **just call the MCP tool**. When launched via Kimi's own Bash, run them in the FOREGROUND (never background/detached) so the window is visible.
- The ⛔ headed-tests directive (§18) applies to Kimi unchanged: headed Playwright, foreground window, full-screen screenshots, never record a lie. If it cannot be made visible, do not run it — tell Angela.
- Kimi-specific operational hygiene: do not leave test/dev servers running in the background after a task; stop what you start.

---

*KIMI.md — regenerated 2026-07-22 against source ground truth at v1.44.0 (85 agents / ~103 chat tools / 102 MCP tools / 28 skills / 17 models / 186 migrations / 33 JS modules). Sibling files: CLAUDE.md (Claude Code), GEMINI.md (Gemini CLI). Counts verified from disk, manifest, and the live MCP server; when they drift again, re-verify from source — never copy from docs.*

*Tlamatini — "one who knows". Created by Angela López Mendoza · @angelahack1 · XAIHT.*
