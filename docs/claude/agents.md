# Tlamatini — Agents (Creation, Catalog, FlowCreator, FlowHypervisor)

## Backend Agent Contract Registry (`agent/services/agent_contracts.py`)

Since the Flow Compiler / Contracts pass (May 2026), every connection-shape decision the canvas, the `.flw` loader, the Validate dialog, and the Start sequence make is funneled through a single backend registry: `get_agent_contracts()` in `agent/services/agent_contracts.py`. Each agent is described by an immutable `AgentContract` dataclass:

| Field | Meaning |
|---|---|
| `agent_type` | Canonical normalized id, e.g. `node_manager`, `gateway_relayer`, `kyber_keygen` |
| `display_name` | Human-readable name, e.g. `Node Manager`, `ACPXer`, `SSHer` (capitalization quirks centralized in `agent_paths.display_name_from_agent_type`) |
| `aliases` | Extra names that resolve to this agent type (gives "Node Manager" → `node_manager` for free) |
| `input_field_by_slot` / `output_field_by_slot` | Per-slot connection-field shape: which YAML key a connection on slot 0/1/2 of the canvas writes into. Forker/Asker put slot 2 into `target_agents_b`, Counter puts slot 2 into `target_agents_g`, AND/OR put slot 2 into `source_agent_2`, and so on |
| `connection_fields` | Every field name the registry treats as a connection (`source_agents`, `target_agents`, `output_agents`, `source_agent_1/2`, `target_agents_a/b/l/g`) — used to clear stale wiring before recompiling |
| `parametrizer_fields` | Tuple of fields a downstream Parametrizer can address. Centralizes what used to live in `views.PARAMETRIZER_SOURCE_OUTPUT_FIELDS` (e.g. `apirer` exposes `url`, `response_body`; `acpxer` exposes `agent_id`, `session_id`, `transport`, `settle`, `transcript_path`, `response_body`) |
| `secret_paths` | Dotted paths inside `config.yaml` that must be redacted from `.flw` exports (e.g. `tlamatini.password`) |
| `no_input` / `no_output` | True for endpoints (Starter has no input; FlowCreator/FlowHypervisor have neither) |
| `exclude_from_validation` | True for FlowCreator and FlowHypervisor (system agents that never appear in the validation list) |
| `singleton` | True when only one instance is allowed on the canvas (FlowCreator, FlowHypervisor) — affects pool naming (`flowcreator` instead of `flowcreator_1`) |
| `long_running` | True for FlowHypervisor / TeleTlamatini / WhatsTlamatini — informs the watchdog and the Start sequence |
| `never_starts_targets` | True for Stopper / Cleaner — the canvas wiring still draws but the agent does not auto-launch its `target_agents` |
| `special` | Marker for Ender (`output_agents` = launch list, `target_agents` = kill list) and Parametrizer (artifact-driven mappings) |

`get_agent_contract(value)` resolves an agent name through the alias map and returns the contract; unknown names get a synthesized default contract. The registry is `lru_cache(maxsize=1)`'d so the disk-discovery + builtin-overrides pass runs exactly once per process.

The registry is exposed to the frontend via `GET /agent/agent_contracts/` (returns `list_contract_summaries()`), to the Validate button via `list_pool_agents_for_validation()` in `flow_compiler.py`, and to both `.flw` save/load and Start via `compile_flow_payload()`.

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

## All 68 Workflow Agent Types

> **Single source of truth for descriptions**: `agents_descriptions.md` at the repo root. The Django view `agent.views.agentic_control_panel` parses the `## Workflow Agents` tables in that file (with `README.md` as a legacy fallback for older deployments) and injects the `Description` column into the page as `agent_purpose_map` JSON. The frontend uses each entry as the **hover tooltip** over the sidebar agent and as the **canvas Description dialog body** on right-click. Editing a row's `Description` cell there changes both human docs AND the live UI text. `build.py` ships `agents_descriptions.md` next to the executable in frozen mode so the resolution works in both modes. The lookup is case- and punctuation-insensitive (`re.sub(r'[^a-z0-9]+', '', name.lower())`), so `Kyber-KeyGen`, `Kyber KeyGen`, and `kyberkeygen` all map to the same entry.

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
- **Pythonxer** - Inline Python behind a STRICT correctness gate (`compile()` syntax floor + blocking Ruff when `ruff_blocking=true`, the default). **ALWAYS triggers `target_agents` afterwards — no matter what** (success, gate refusal, or runtime failure); the exit code drives only the LED and the Multi-Turn fix→re-ruff→retry loop, never whether downstream starts. (2026-05-29 — was "exit-code gates downstream"; see `docs/claude/recent-fixes.md`)
- **Prompter** - LLM prompt execution
- **Summarizer** - LLM text/log summarization
- **Crawler** - Web crawling with LLM analysis
- **Googler** - Google search + text extraction (Playwright)
- **Playwrighter** - Scripted interactive browser automation (Playwright). Drives a real browser through declarative steps (goto/click/fill/wait_for/extract/screenshot/assert/download) for authenticated/JS/multi-step flows that Crawler (static fetch) and Googler (search) cannot do. Deterministic; emits INI_SECTION_PLAYWRIGHTER; always triggers target_agents. Set `headless: false` to watch it drive and `hold_open_seconds: N` (alias `hold_open_ms`) to keep the browser visible N seconds AFTER the last step BEFORE it closes — this is the "wait before closing so I can see it" knob the LLM should pass on such requests. Canvas counterpart of the chat_agent_playwrighter Multi-Turn tool.
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
- **Windower** - Window manager (Win32/pywin32, self-contained, ports the window-management subset of Microsoft's Windows-MCP incl. the AttachThreadInput focus dance). Acts on the WINDOW itself (peer of Mouser=clicks-inside, Keyboarder=types-into): `action` ∈ `list` / `focus` / `minimize` / `maximize` / `restore` / `move` / `resize` / `move_resize` / `close` / `topmost` / `untopmost` / `arrange` (snap/tile). Matches `window_title` by `substring`/`exact`/`regex` (+ `match_index`); emits `INI_SECTION_WINDOWER` (`action`, `window_title`, `matched`, `match_count`, `state`, `left`, `top`, `width`, `height`); always triggers `target_agents`. State-changing → in the Exec Report. Canvas counterpart of the wrapped `chat_agent_windower` Multi-Turn tool.
- **File-Creator** - Creates files with specified content
- **File-Interpreter** - LLM reads and interprets file contents
- **File-Extractor** - Raw text extraction (PDF, DOCX, etc.)
- **Image-Interpreter** - LLM vision analysis
- **J-Decompiler** - JAR/WAR decompilation (bundled jd-cli)
- **De-Compresser** - Deterministic short-running archive worker (compress OR decompress). Direction inferred from extensions; supports `.gz` / `.zip` / `.7z` / `.tar.gz` / `.gz.tar`; password from `DE_COMPRESSER_PWD` env var when `passwordless=false`. Always triggers `target_agents` at end-stage, even on failure.
- **Telegramer** - Sends Telegram messages
- **TeleTlamatini** - Long-running Telegram bot that bridges authorized users into the full Multi-Turn + Exec Report Tlamatini chat
- **WhatsTlamatini** - Long-running WhatsApp bot (Meta WhatsApp Cloud API) that bridges authorized users into the full Multi-Turn + Exec Report Tlamatini chat. Mirror of TeleTlamatini swapping Telethon for a stdlib webhook listener (inbound) + Graph-API HTTP POSTs (outbound)
- **ACPXer** - Visual ACPX session driver: invokes one external coding-agent CLI (Claude/Codex/Gemini/Cursor/Qwen/etc.) per turn — for `oneshot-prompt` agents (claude/cursor/gemini/qwen/codex) the prompt is passed as a CLI arg and stdout is captured to EOF; for `tui-repl`/`json-acp` agents stdin/stdout is drained by the transport-aware idle rule. Captures last-assistant text, kills child. Canvas-driven counterpart of the 12 LLM-facing `acp_*` tools; emits Parametrizer-compatible `INI_SECTION_ACPXER` so multi-CLI relay flows can be drawn visually
- **Unrealer** - Drives an Unreal Engine 5 editor via the Unreal MCP plugin's TCP socket (default `127.0.0.1:55557`). Each run sends ONE JSON command (`{"type": <verb>, "params": {...}}`) and forwards whatever the connected plugin build exposes — the extended surface is 53 commands across nine categories: editor (actors + `focus_viewport`/`take_screenshot`), blueprint (authoring + `set_pawn_properties`), node (graph wiring + `find_blueprint_nodes`), project (input mappings), umg (widgets), **system** (`execute_python`/`execute_console_command`/`get_class_info`/`list_assets`), **level** (open/save/new/get_current_level), **asset** (import/duplicate/rename/delete/save/create_folder), **material** (create/instance/set_parameter/assign). The P3 headless tools (build_project/run_automation_tests/run_macro) are NOT bridge commands — they shell out to UnrealEditor-Cmd and are unreachable over this socket; chain Unrealer nodes via Parametrizer for the run_macro equivalent. Captures the engine response verbatim into an `INI_SECTION_UNREALER` block (so a downstream Forker / Raiser can branch on `status` / `error`) and ALWAYS triggers `target_agents` on success or failure. Visual canvas counterpart of the wrapped `chat_agent_unrealer` Multi-Turn tool. The recommended plugin is Tlamatini's own extended Unreal MCP fork (the Unreal Engine MCP modified specifically for this system) at `https://github.com/XAIHT/XaihtUnrealEngineMCP.git` — a drop-in built on upstream `chongdashu/unreal-mcp` that ships the full 53-command surface.
- **Reviewer** - LLM-powered code reviewer. Resolves a `git diff` for the configured `repo_path` (`diff_ref` like `HEAD~1` / `origin/main`, or empty = uncommitted working-tree + staged changes), sends it to an Ollama model with a senior-engineer review prompt, parses a `verdict` (`APPROVE` / `REQUEST_CHANGES` / `COMMENT`), and emits an `INI_SECTION_REVIEWER` block (fields `repo_path`, `diff_ref`, `verdict`, `model`, `status`; body = review). ALWAYS triggers `target_agents` so a downstream Forker can branch on `{verdict}`. Visual canvas counterpart of the `code-review` SKILL.md.
- **Analyzer** - Deterministic static-analysis / security scanner (no LLM). Runs whichever of `bandit`, `semgrep`, `ruff`, `eslint`, `gitleaks`, `pip-audit` are on PATH over `target_path`, aggregates findings, and emits an `INI_SECTION_ANALYZER` block (fields `target_path`, `tools_run`, `tools_skipped`, `total_findings`, `status` ∈ `clean`/`findings`/`error`; body = combined output). ALWAYS triggers `target_agents` so a downstream Forker can gate on `{status}` / `{total_findings}`. Visual canvas counterpart of the `security-audit` SKILL.md.
- **Kalier** - Bridge to **Kali Linux** offensive-security tooling via the MCP-Kali-Server (`https://www.kali.org/tools/mcp-kali-server/`). POSTs to the MCP-Kali-Server Flask API (`server.py`; default `http://127.0.0.1:5000`) over the stdlib `urllib` (no `requests`/`mcp` deps in the pool) and runs ONE capability per run selected by `action` ∈ `command` / `nmap` / `gobuster` / `dirb` / `nikto` / `sqlmap` / `metasploit` / `hydra` / `john` / `wpscan` / `enum4linux` / `health`. Captures the tool's stdout/stderr into an `INI_SECTION_KALIER` block (fields `action`, `endpoint`, `method`, `subject`, `return_code`, `success`, `timed_out`, `server_url`; body = output) and ALWAYS triggers `target_agents` so a downstream Forker can branch on `{success}` / `{return_code}`. For a remote Kali box use an SSH tunnel (or a LAN IP). **Embedded-client UX**: the wrapped `chat_agent_kalier` auto-injects the global `kali_server_url` (set once in **Config ▸ URLs** / `config.json`, default `http://127.0.0.1:5000`) as the default `server_url`, so chat prompts never repeat the Kali box address — the LLM may still pass `server_url=` to override for a one-off box; canvas/.flw runs set `server_url` in the node dialog. Authorized targets only. Visual canvas counterpart of the wrapped `chat_agent_kalier` Multi-Turn tool.
- **STM32er** - Bridge to **STM32 firmware** development via the STM32 Template Project MCP (`https://github.com/XAIHT/STM32TemplateProjectMCP`) — a FastMCP stdio server driven over a self-contained inline MCP stdio JSON-RPC client (no `mcp` dep in the pool; stdlib-only `agent/agents/stm32er/stm32er.py`). Runs ONE capability per run selected by `action`; the surface is **27 actions** = the **23 MCP tools** (firmware scaffold / build / flash / observe — incl. serial + SWD) + **2 composites** (`serial_session`, `live_monitor`) + **2 meta** (`bootstrap`, `validate`). **ZERO-CONFIG AUTO-BOOTSTRAP** (`_bootstrap_mcp`): with no on-disk `server_script` (the default `stm32_mcp_server_script` is now empty) and `auto_bootstrap: true`, STM32er downloads the MCP itself — shallow `git clone` with a GitHub-zip fallback when git is absent — into `%LOCALAPPDATA%/Tlamatini/STM32TemplateProjectMCP`, pip-installs `mcp` + `pyserial` if missing (`pip_install: true`), and validates it, so a user installs **only STM32CubeIDE + Tlamatini**. **SAFETY PREFLIGHT** (`_preflight`, fail-safe): before any compile/flash it validates compiler / CubeIDE / make / programmer / ST-LINK driver + probe (`_probe_stlink`) / device family (`_device_family`) and **REFUSES** rather than mis-build or mis-flash — compile-only actions need no board, hardware actions (flash / erase / reset / `serial_*` / SWD / `live_*`) require a connected ST-LINK, and a cross-STM32F-family target is refused (the MCP template is STM32F407VG-specific; multi-family support is future work via an MCP fork). Config keys: `auto_bootstrap`, `mcp_repo_url`, `mcp_ref`, `mcp_install_dir`, `auto_update`, `pip_install`, `preflight` (all default true where boolean), `device`. Emits an `INI_SECTION_STM32ER` block and ALWAYS triggers `target_agents` so a downstream Forker can branch on the result. Global `config.json` defaults `stm32_mcp_server_script` (now `""`), `stm32_mcp_repo_url`, `stm32_mcp_install_dir` are seeded by `tools._seed_global_agent_defaults`. Visual canvas counterpart of the wrapped `chat_agent_stm32er` Multi-Turn tool.

### Cryptography Agents
- **Kyber-KeyGen** - CRYSTALS-Kyber key pair generation (post-quantum)
- **Kyber-Cipher** - Kyber encryption
- **Kyber-DeCipher** - Kyber decryption

### Utility Agents
- **Parametrizer** - Maps structured output from one agent into another's config.yaml (strict single-lane queue)
- **FlowBacker** - Backs up session logs/configs
- **FlowCreator** - LLM-powered flow designer (system agent, singleton, no canvas connections); reads `agentic_skill.md` and emits a `.flw` JSON
- **Gatewayer** - HTTP webhook ingress + folder-drop watcher
- **Gateway-Relayer** - Bridges GitHub/GitLab webhooks into Gatewayer
- **Node-Manager** - Infrastructure registry and node supervision

### Terminal/Monitoring Agents (do NOT start downstream)
- **Monitor-Log** - LLM-powered log file monitor
- **Monitor-Netstat** - LLM-powered network port monitor
- **Emailer** - SMTP email on pattern detection
- **RecMailer** - IMAP email receiver/monitor
- **Notifier** - Notification on pattern match (or oneshot from chat). Two surfaces, both fire together: (1) the legacy **in-browser DOM popup** (writes `notification.json`, polled by the frontend) + optional `.wav`; (2) a **native Windows toast** (OS banner, bottom-right, persists in Action Center) via `agent/native_toast.py`'s mechanism mirrored inline (pool subprocesses can't import `agent.*`). The toast shells out to **Windows PowerShell 5.1** (`powershell.exe`, NOT `pwsh` — PowerShell 7 can't load the WinRT toast types) using the registered AUMID `XAIHT.Tlamatini.Server`, shows the Tlamatini PNG logo, and on click focuses the **existing** Tlamatini browser tab via the `tlamatini:` URL protocol + a Win32 focus helper (opens nothing new). **Non-admin/HKCU only** — an elevated process gets its toasts suppressed and the focus dance fails across integrity levels. Config keys (`notifier/config.yaml` → `target`): `native_toast` (default true), `toast_title`, `toast_image` (empty → registered HKCU IconUri), `toast_click` (`focus`/`none`), reuses `sound_enabled`. Identity + protocol are registered once at Django startup (`apps.py` → `native_toast.register_all()`).
- **Whatsapper** - WhatsApp messages (TextMeBot)
- **TelegramRX** - Telegram message receiver
- **FlowHypervisor** - LLM-powered flow health monitor (system agent)

> **Note**: TeleTlamatini and WhatsTlamatini are **active** agents (they DO start `target_agents` after each completed user request cycle), so they are listed under Action Agents above — not here. Their long-running listener nature is documented as a "long-running" trait in the FlowHypervisor monitoring contract.

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
