<!--
═══════════════════════════════════════════════════════════════════
  ✦  T L A M A T I N I  ✦   —   "one who knows"
  Created by  Angela López Mendoza   ·   @angelahack1
  Developer · Architect · Creator of Tlamatini
  Tlamatini Author Banner — do not remove (Angela's name is kept in every build)
═══════════════════════════════════════════════════════════════════
-->

# GEMINI.md — Complete Tlamatini System Knowledge Base & Onboarding Reference

> **Welcome, Gemini!** This is the definitive onboarding document and reference manual for working on the **Tlamatini** project. Read this file in full before performing any coding tasks. It combines architecture details, tool behaviors, visual agent catalogs, security policies, and Windows-specific design patterns gathered from across the codebase.

---

# ⛔ PRIVATE DATA GUARD — ABSOLUTE, NON-NEGOTIABLE ⛔

**NEVER REWRITE GIT HISTORY. EVER. IN THIS REPO, FOR ANY REASON.**

- **NO** `rebase`, `commit --amend`, `reset --hard` to drop commits, `filter-branch`, `git filter-repo`, BFG, or history-rewriting tools.
- **NO** `push --force` / `--force-with-lease`, **NO** deleting pushed tags, and **NO** deleting remote branches/refs.
- **TO REMOVE SENSITIVE/PRIVATE DATA**: Edit or delete the file, then make a **NEW FORWARD COMMIT** and push that. The past commits MUST stay untouched.
- **TRUTHFUL HISTORY**: Git logs, tags, and commit lines must always remain intact and completely truthful.
- This policy is enforced by `test_private_data_guard.py` (automated tests) and a global hooks script that runs in the developer environment.

---

## 1. Project Identity, Persona & Communication Rules

### 1.1 The User: Angela López Mendoza
- The user is **Angela López Mendoza** — the developer, architect, and creator of Tlamatini.
- **ALWAYS address her by name ("Angela") in your responses.** Do not speak to her impersonally. Open or weave "Angela" into your replies.
- Use her full name **"Angela López Mendoza"** when affirming her as the creator of Tlamatini.
- Her name must **NEVER** be erased/scrubbed from the source files, banners, docs, prompts, About window, PDF/PPTX, or build metadata. Only a public release build may mask her other private data (emails/phones), never her name.

### 1.2 Persona & Identity
- Tlamatini (Nahuatl for "one who knows") is **explicitly female** by design.
- The `talker` (Text-to-Speech) agent is restricted to **female voices only** (`tara`, `leah`, `jess`, `mia`, `zoe`).
- The internal voice resolver `resolve_voice()` in `agent/agents/talker/talker.py` enforces this. If a male voice is requested, it throws `MaleVoiceForbiddenError` and exits the agent with a hard error: `"NOW CLOSING.. BYE"`. Do NOT modify or bypass this constraint.

### 1.3 How to talk to Angela (Mandatory Rules)
- **Answer short and in plain language.**
- **Lead with the single key fact in bold.**
- Use a few short numbered points at most. Use everyday words, **no jargon**, **no giant multi-section walls of text**, and **no long source lists**.
- Cut anything that does not change her decision.
- End with **one direct question or next step**.

### 1.4 Step-by-Step Interactive Mode
When solving a problem that needs Angela to do things on her machine (Rethinking configs, clicking browser/UI, checking board output, restarting the app):
- **Go one step at a time**:
  1. Give **exactly one** concrete step.
  2. Give her the **exact string to send back** — a token carrying what she sees (e.g. `step1: I see ___`).
  3. **WAIT**. Only when she sends that string do you give the next step.
  4. Repeat — one step + one reply-string per turn.

---

## 2. Strict Casing & Naming Conventions

The single source of truth for any visual workflow agent is its **`agentDescription`** database field (seeded via Django migrations). It is rendered **verbatim** in the sidebar and canvas. If you mismatch casing, the JavaScript class map or Django views will fail to load the agent.

| Context | Case Convention | Example (STM32er) |
| :--- | :--- | :--- |
| **Display Name (DB)** | Exact Case (as designed) | `STM32er` (NEVER `Stm32er` or `STM32Er`) |
| **Database `agentName`** | Lowercase / Hyphen | `stm32er` |
| **Agent Folder** | Lowercase / Underscore | `agent/agents/stm32er/` |
| **Agent script** | Lowercase / Underscore | `agents/stm32er/stm32er.py` |
| **JS classMap key** | Lowercase / Hyphen | `'stm32er'` |
| **CSS selector** | Lowercase / Hyphen | `.canvas-item.stm32er-agent` |
| **Connector symbol** | PascalCase-ish | `updateStm32erConnection` |
| **Token block (Logs)** | ALL-CAPS | `INI_SECTION_STM32ER` / `END_SECTION_STM32ER` |

---

## 3. The 7-Layer Architecture

Tlamatini consists of seven distinct layers spanning from the database up to the backend workflow compiler and out-of-process multi-agent controllers:

```
┌────────────────────────────────────────────────────────────────────────┐
│                        Layer 1: Database State                         │
│   (SQLite: Persisted toggles for Mcps, Tools, Agents, Skills, etc.)    │
└───────────────────────────────────┬────────────────────────────────────┘
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│                    Layer 2: gRPC & WebSocket Services                  │
│  - System-Metrics (WS: port 8765)  - Files-Search (gRPC: port 50051)   │
└───────────────────────────────────┬────────────────────────────────────┘
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│                Layer 3: Context Fetcher Sidecar Chains                 │
│      - SystemRAGChain                   - FileSearchRAGChain           │
└───────────────────────────────────┬────────────────────────────────────┘
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│                      Layer 4: Main LLM Chains                          │
│  - basic.py (Fallback)  - history_aware.py  - unified.py (LangGraph)   │
└───────────────────────────────────┬────────────────────────────────────┘
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│                        Layer 5: Unified Tools                          │
│     (LangChain @tools defined in tools.py and registry wrappers)       │
└───────────────────────────────────┬────────────────────────────────────┘
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│                     Layer 6: ACPX Multi-Agent Core                     │
│    (AcpxRuntime + Sandboxed Skills Harness driving external CLIs)     │
└───────────────────────────────────┬────────────────────────────────────┘
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│                       Layer 7: Flow Compiler                           │
│   (AgentContract registry + FlowSpec normalizer + FlowCompiler engine) │
└────────────────────────────────────────────────────────────────────────┘
```

- **Layer 1 (Database)**: Seeds default registries. Toggles on the UI enable/disable tools and agents which update database rows.
- **Layer 2 (Runtime Services)**: Started from `apps.py` on Django boot. They feed real-time metrics and file indexes to the app.
- **Layer 3 (Sidecar Chains)**: Prefetch files and system data to inject into the LLM context.
- **Layer 4 (Main Chains)**: Monkey-patched at execution time by `factory.py` to merge context before calling the LLM.
- **Layer 5 (LangChain Tools)**: Bound to the model. Includes direct shell executors (`execute_command`, `execute_file`) and wrapped `chat_agent_*` controllers.
- **Layer 6 (ACPX & Skills)**: Spawns external CLI engines (Claude Code, Qwen, Gemini, etc.) and executes local `SKILL.md` playbooks.
- **Layer 7 (Flow Compiler)**: Normalizes canvas schemas into run-ready pools on disk under `agents/pools/<session_id>/`.

---

## 4. Multi-Turn Orchestration & the Operator Loop

When **Multi-Turn** is checked in the toolbar, Tlamatini shifts from a "text answering box" to a **stateful runtime operator**:

1. **Planner Gating**: Prompt-shape validation is bypassed. The system constructs a request-scoped plan using the `GlobalExecutionPlanner`.
2. **Full-Surface Binding**: The executor binds **every enabled tool, wrapped agent, and skill** to the LLM. It does NOT restrict the LLM to a small planner subset.
3. **Execution Limits**:
   - **Soft Warning**: Fires if iterations exceed **64**. It injects a warning into the prompt encouraging the LLM to choose cleaner paths.
   - **Hard Stop**: Enforced at **256** iterations. It terminates the loop and forces a final response.
   - **Repetition Breaker**: Detects if the LLM calls the same tool with identical signatures. Polling and management tools (`run_status`, `session_status`, etc.) are explicitly exempt from fingerprinting to avoid tripping this guard during normal wait loops.

### 4.1 Cost Trimming Measures
To avoid ballooning LLM token counts with up to 89 tools bound:
- **One-line Tool Summaries**: Standard LangChain JSON schemas are fed to the model, but the textual system prompt lists each tool on a single line.
- **Ollama Keep-Alive**: The `ChatOllama` connection is instantiated with `keep_alive: -1` (or from `OLLAMA_KEEP_ALIVE`) so the model context cache is preserved between turns on the Ollama daemon.

### 4.2 Step-by-Step Mode
- Controlled by the `#step-by-step-enabled` checkbox.
- Appends instructions forcing the LLM to execute exactly **one tool call at a time**, return a progress statement, and wait for the user to submit a `READY` input before continuing.

### 4.3 Self-Healing Model Steps (`agent/self_healing.py`, 2026-07-06)
Every model `.invoke()` inside `MultiTurnToolAgentExecutor` is wrapped by a per-request `SelfHealingInvoker`. Its contract is **never hang, never discard work, never lie**:
- **Never hang** — each attempt runs under a per-attempt watchdog (`_run_with_watchdog`, worker thread) of `unified_agent_llm_step_timeout_seconds` (default 80 s): an over-deadline model call is ABANDONED, never awaited. On a transient failure it retries DISTINCT tactics (retry, back-off, message-tail trim, plain-LLM fallback) up to `unified_agent_llm_step_max_tactics` (default 4096). Only the USER (Cancel) or an exhausted ladder stops it, raising `ModelStepUnrecoverable`.
- **Never discard work** — if it fails after ≥1 agent already ran, the executor finishes GRACEFULLY from that real work (`_degraded_answer_from_results`), preserving the Create-Flow button + Exec report. Only a pure-Q&A re-raises, and `rag/chains/unified.py::_invoke_unified_agent_with_retry` short-circuits it straight to the fallback.
- **Never lie** — `recovery_preamble(recovery_events)` is prepended to the final persisted answer on every exit path, and `consumers.py` streams live retry status to the user's chat (`register_status_broadcaster`, per Multi-Turn request, independent of Ask-Execs).

---

## 5. Human-in-the-Loop: "Ask Execs" Gating

The **Ask Execs** gate runs inside the worker thread of the Multi-Turn executor (`MultiTurnToolAgentExecutor` in `agent/mcp_agent.py`):

```
[Unified Agent Loop] 
         │
         ▼
State-Changing Tool Call? ───(No)───► Execute Tool
         │ (Yes)
         ▼
Is Ask Execs Checked? ───(No)───► Execute Tool
         │ (Yes)
         ▼
[ExecPermissionBroker]
  - Register request UUID
  - Emit WS 'exec_permission_request' to browser
  - Thread Blocks on threading.Event()
         │
         ▼ (User responds in browser modal)
[WebSocket Receive]
  - Resolves broker event with 'Proceed' or 'Deny'
         │
         ├───► Proceed ──► Unblocks Thread ──► Execute Tool
         │
         └───► Deny ──► Unblocks Thread ──► Record Interrupted State ──► Halt Chain
```

- **Exemptions**: Read-only, polling, and status tools (`execute_netstat`, `chat_agent_run_status`, `acp_list_sessions`, etc.) are marked in `_requires_exec_permission()` and never block.
- **Fail-Safe**: If a browser session disconnects, the broker is closed, or a WebSocket error occurs, the permission defaults to **Deny**.
- **Deny Behavior**: Halts the entire execution. The backend sets `last_exec_report_denied = True`. The frontend appends a red `"Execution interrupted"` banner to the message output.

---

## 6. The Universal External-MCP Client

Tlamatini features a universal, config-driven MCP client managed by `agent/external_mcp_manager.py`:

- **Decoupled Lifecycle**: MCP server connections are established in a **background thread, off the main chat path**. A slow, failing, or offline server will never freeze the chat page.
- **Config file**: Lives at `agent/external_mcps.json` next to `config.json` in the `mcpServers` format.
- **Entitlements**: Allows up to **5 active servers** at a time.
- **Transports**:
  - `stdio`: Spawns a local executable (e.g. `npx`, `uvx`, `python`, `docker run`).
  - `streamable-http`: Modern HTTP endpoint.
  - `sse`: Legacy server-sent events.
  - `websocket`: Standard WebSockets.
- **LLM Supervisor Tools**: The LLM manages imports and activations using 8 dedicated tools:
  - `external_mcp_status`, `external_mcp_reconnect`, `external_mcp_doctor`, `external_mcp_list_tools`, `external_mcp_call`, `external_mcp_import`, `external_mcp_set_active`, and `external_mcp_wait`.
- **MCP Doctor (Agent #78)**: A static triage node that inspects server configurations (validates executable paths, detects missing environment tokens or placeholder secrets) **without establishing a live socket connection**.

---

## 7. ACPX CLI Runtime & Skills System

**ACPX** manages the integration of external coding-agent CLIs (Claude Code, Cursor, Codex, Gemini, Qwen, etc.) running as out-of-process subprocesses.

### 7.1 Transport Modes
- `oneshot-prompt` (**Critical Windows Fix**): Standard terminal TUIs refuse to flush output when stdin/stdout are piped in a long-running process. To bypass this, Tlamatini spawns the CLI fresh on each turn, passes the prompt as a CLI argument, and captures the stdout/stderr stream upon EOF.
- `json-acp`: Strict JSON messaging over stdin/stdout (e.g., used by `tlamatini` self-host).
- `tui-repl`: Long-lived REPL shell. Uses reader threads to pump console stdout to queues.
- `one-shot`: Single task, closes stdin immediately after write.

### 7.2 Skills Runtime & HARNESS
- Skills are defined in directories under `agent/skills_pkg/` containing a `SKILL.md` file with a YAML frontmatter block.
- **Validation**: Inputs and outputs are strictly coerced and validated against the skill's declared schema by `agent/skills/io_contract.py`.
- **Budgets**: Each skill has a `Budget` dataclass enforcing `max_iterations`, `max_seconds`, and `max_tokens` (accumulated from ACPX event streams).
- **Security**: The `PermissionGate` manages capabilities (`approve-reads`, `approve-all`, `deny-all`). In unattended runs, the policy dictates whether to `deny` (return permission-denied to the LLM) or `fail` (hard exit).
- **Admin UI**: Surfaced in the chat navbar under **ACPX-Skills** (Browse / Configure / Diagnostics / Reload).
  - *Browse*: Inspector modal.
  - *Configure*: Toggles `Skill.enabled` in the DB.
  - *Diagnostics*: Audits missing tool/MCP dependencies.
  - *Reload*: Runs `boot_skills()` to reload disk modifications without restarting Django.

---

## 8. Windows-Specific Hardening

Tlamatini is designed primarily for Windows, featuring deep integrations that require strict fallback rules.

### 8.1 Native Directory Picker
- Web browsers' standard `showDirectoryPicker()` cannot browse folders outside the client sandbox or handle nested paths under application roots.
- Tlamatini bypasses this by using a backend Win32 folder picker (`views.pick_context_directory_view`).
- **Non-Windows Fallback**: If the OS is not Windows, the view returns a flag instructing the frontend to fall back to a manual text-entry field.

### 8.2 The conhost.exe Reaper
To prevent task manager pollution (where companion `conhost.exe` processes would linger bearing the Tlamatini icon), the app runs a three-tier reaper (`agent/orphan_reaper.py`):

| Tier | Run Location | Scope |
| :--- | :--- | :--- |
| **Tier 1 (After Tool)** | `MultiTurnToolAgentExecutor._reap_after_tool()` | Zombie/dead child PIDs of `os.getpid()` + parentless `conhost.exe` / `openconsole.exe` whose command line matches our tree. (Cheap check) |
| **Tier 2 (After Chat)** | `AgentConsumer._tier2_orphan_sweep()` (Background thread) | Same as Tier 1 + full command line scan of active/dead pools under `agents/pools/` or `_chat_runs_`. Broadcasts a WS alert warning the user if zombies survive. |
| **Tier 3 (Shutdown)** | `AgentConfig.ready()` (Atexit/SIGINT hooks) | Complete sweep of the entire application space. Kills all remaining console-host orphans. |

- **Monkeypatch Seatbelt**: Every visual agent python script inherits a monkey-patch on `subprocess.Popen.__init__` (`_chg_guarded_init`) that defaults `creationflags` to `CREATE_NO_WINDOW` to prevent console windows from spawning at all unless explicitly requested.

---

## 9. Complete Visual Agent Catalog (84 Agents)

Visual agents are designed to run out of process. The backend compiler generates their config, spawns them, and inspects their logs. Below is the complete catalog of all 84 visual agents:

1. **starter**: Flow initiator.
2. **ender**: Flow terminator; kills targeted processes.
3. **stopper**: Pattern-based agent execution stopper.
4. **cleaner**: Cleans up active process IDs and logs.
5. **raiser**: Spawns files/commands upon trigger events.
6. **executer**: Runs commands/scripts in a shell.
7. **pythonxer**: Executes Python scripts through a strict syntax/Ruff compiler gate.
8. **sqler**: Runs queries on SQL Server databases.
9. **mongoxer**: Executes MongoDB scripts.
10. **ssher**: Executes commands on remote servers via SSH.
11. **scper**: Moves files to remote directories via SCP.
12. **dockerer**: Manages Docker containers.
13. **kuberneter**: Manages Kubernetes pods and services.
14. **apirer**: Emits REST HTTP calls; outputs to `response_body` / `INI_SECTION_APIRER`.
15. **jenkinser**: Triggers Jenkins CI/CD pipeline runs.
16. **gitter**: Executes Git commands and subcommands.
17. **pser**: Processes finder; looks up active process trees.
18. **prompter**: Prompts the LLM with log files or system states.
19. **summarizer**: Synthesizes and condenses large log dumps.
20. **crawler**: Developer-oriented web crawler.
21. **googler**: Headless Playwright Google search + text extract.
22. **file_creator**: Creates files and necessary parent directories.
23. **file_extractor**: Extracts text content from files.
24. **file_interpreter**: Parses heavy docs (.pdf, .docx, .xlsx, .csv).
25. **image_interpreter**: Dual-backend (Claude/Qwen) visual image analysis.
26. **j_decompiler**: Decompiles Java artifacts (JAR/WAR) using bundled `jd-cli`.
27. **shoter**: Takes desk screenshots (silent; returns output_path).
28. **mouser**: Automates mouse clicking and pointer moves (7 patterns).
29. **keyboarder**: Key typing simulator with a robust hotkey parser.
30. **mover**: Moves/copies files with glob matching.
31. **deleter**: Deletes files with glob patterns.
32. **gatewayer**: Receives inbound webhooks and files.
33. **gateway_relayer**: Relays third-party webhooks (GitHub/GitLab) into gatewayer.
34. **node_manager**: Supervises node registries and statuses.
35. **parametrizer**: Core connector. Maps upstream log fields into downstream config keys.
36. **flowbacker**: System backup and cleanup director.
37. **flowcreator**: AI designer that plans and writes canvas-ready `.flw` files.
38. **flowhypervisor**: Log-monitoring anomaly detector.
39. **barrier**: Synchronization gate; blocks until all upstream logs complete.
40. **and**: AND logic decision gate.
41. **or**: OR logic decision gate.
42. **forker**: A/B path conditional router.
43. **asker**: In-canvas / in-chat A/B user confirmation gate.
44. **counter**: Iteration threshold loop controller.
45. **croner**: Cron-style scheduled workflow trigger.
46. **sleeper**: Pauses workflow execution for a set duration.
47. **emailer**: Sends emails via SMTP.
48. **recmailer**: Monitors inbound emails via IMAP.
49. **whatsapper**: Double-identity WhatsApp agent (`cloud` official API vs `web` automated browser).
50. **telegrammer**: Double-identity Telegram agent (`bot` Bot API vs `user` account automation).
51. **notifier**: Pops up DOM alerts and flashes the parent console window.
52. **monitor_log**: Active log watcher; triggers alerts on patterns.
53. **monitor_netstat**: Network port traffic monitor.
54. **kyber_keygen**: CRYSTALS-Kyber key pair generator.
55. **kyber_cipher**: CRYSTALS-Kyber encryption engine.
56. **kyber_decipher**: CRYSTALS-Kyber decryption engine.
57. **acpxer**: Counterpart to the ACPX command runner.
58. **teletlamatini**: Telegram-bridge bot controller.
59. **windower**: Win32 window position/focus supervisor.
60. **kalier**: Kali Linux offensive-security scanner bridge.
61. **discoverer**: ProjectDiscovery recon bridge (subfinder, httpx, naabu, Katana, nuclei, vulnx).
62. **unrealer**: Unreal Engine 5 socket connector (port 9876).
63. **reviewer**: AI code reviewer (analyzes git diff).
64. **analyzer**: Offline static/security SAST scanner.
65. **stm32er**: Compile & flash manager for STM32 microcontrollers.
66. **esp32er**: PlatformIO compiler and flash manager for ESP32.
67. **arduiner**: arduino-cli compiler and manager for Arduino.
68. **esphomer**: ESPHome smart-home firmware configurations manager.
69. **camcorder**: Webcam photo and video capturer via OpenCV.
70. **recorder**: Sound card / microphone capture utility via sounddevice.
71. **audioplayer**: Audio files player. Volume and loop control.
72. **videoplayer**: Video files player via ffpyplayer + OpenCV.
73. **mcp_doctor**: Static external-MCP configuration validator.
74. **de_compresser**: Extract zip and tar archives.
75. **sqler**: Runs queries on SQL database servers.
76. **mongoxer**: Runs MongoDB scripts.
77. **dockerer**: Manages Docker containers.
78. **kuberneter**: Manages Kubernetes pods.
79. **ssher**: Executes commands on remote servers via SSH.
80. **scper**: Moves files to remote directories.
81. **gitter**: Executes Git commands.
82. **pser**: Processes finder; looks up active process trees.
83. **zavuerer**: Multi-channel Zavu messaging gateway (SMS, WhatsApp, Email, Telegram, Voice).
84. **video_analyzer**: The MOTION-VERDICT "eye" of Robotic-Loop-Training — watches a recorded video and rules `PASS_OK` / `FAIL_NO_MOTION` / `FAIL_WRONG_MOTION` / `UNCLEAR` via a deterministic OpenCV motion gate + triple-model Ollama CLOUD vision (`qwen3-vl:235b-cloud` ∥ `qwen3.5:cloud` → `glm-5.2:cloud` merge; PASS only when both interpreters agree). Emits `INI_SECTION_VIDEO_ANALYZER` + a substring-safe `TLM_VERDICT::<TOKEN>` line a Forker branches on.

---

## 11. Core Skills Catalog (27 Skills)

Skills are registered in `agent/skills/` and cataloged in `agent/skills_pkg/`. They are markdown playbooks containing YAML frontmatter contracts.

1. **hello_world**: Simple check on harness functions.
2. **skill_creator**: Scaffolds a new skill directory + `SKILL.md`.
3. **acp_router**: Chooses the appropriate external CLI for ACPX spawns.
4. **tlamatini_new_acp_agent**: Step-by-step developer wizard to create new visual agents.
5. **tlamatini_flow_from_objective**: Compiles a prompt objective into a visual flow.
6. **tlamatini_flw_doctor**: Checks visual workflow topologies.
7. **tlamatini_exec_report_row_adder**: Registers a tool to the Exec Report pipeline.
8. **tlamatini_planner_trace_replay**: Replays the LLM execution planner's steps.
9. **tlamatini_allowed_hosts_tighten**: Configures Django's `ALLOWED_HOSTS` dynamically.
10. **tlamatini_csrf_exempt_audit**: Audits `@csrf_exempt` decorators in the codebase.
11. **tlamatini_static_version_bumper**: Bumps Django's static cache version.
12. **github**: Drives the Github CLI tool for PRs and issues.
13. **notion**: Accesses Notion database/block endpoints.
14. **jira**: Triggers transitions on Jira boards.
15. **slack**: Sends slack updates and grabs channel histories.
16. **gmail**: Manages inbox threads via the Gmail API.
17. **todoist**: Syncs tasks to Todoist.
18. **trello**: Manages cards and lists on Trello.
19. **summarize**: Summarizes input text within token caps.
20. **weather**: Gets coordinates forecasts from Open-Meteo.
21. **code_review**: Deep AI reviews of git diffs.
22. **security_audit**: Local vulnerability static scanner (ruff, semgrep).
23. **kali_pentest**: Penetration testing helper using Kalier.
24. **create_new_agent**: Developer onboarding skill (alias for tlamatini_new_acp_agent).
25. **create_new_mcp**: Developer onboarding guide for adding new MCP tools.
26. **flow_making**: Helper script delegator for `make_flow.py`.
27. **tlamatini_flow_from_objective**: Delegates flow objectives to flow_making.

---

## 12. Coding Rules & Recent Fix Contracts

Ensure all future edits strictly adhere to these locked contracts:

### 12.1 Ruff and Parse-Gate
- `pythonxer.py` runs a syntax parse gate `compile()` followed by `validate_with_ruff()`.
- If Ruff reports an error and `ruff_blocking: true` is set, execution is aborted, returning `False`.
- Failure is passed back to `tools.py` with `retryable=True` so the LLM must fix the code and try again.

### 12.2 Pythonxer Downstream Trigger
- **Unconditional downstream trigger**: Pythonxer MUST always start its target downstream agents in a flow, regardless of exit status (0 or 1). Downstream agents do any result-checking.

### 12.3 Secret Key Precision (Reviewer)
- The Reviewer agent must verify git status and treat unstaged changes as uncommitted.
- The `regen_secrets.py` scrub pattern must be respected so local developer keys in `config.json` are not accidentally flagged as leaks.

### 12.4 Playwright in Async Channels Loop
- Any Playwright script executed synchronously must wrap its execution inside a `ThreadPoolExecutor` to avoid ASGI block errors.

---

*This GEMINI.md is the authoritative project knowledge bank. Do not edit the core rules without confirmation from Angela López Mendoza.*
