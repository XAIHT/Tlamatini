# Tlamatini — Agents (Creation, Catalog, FlowCreator, FlowHypervisor)

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
