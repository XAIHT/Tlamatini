---
description: How to create a new Tlamatini agent
---

# Creating a New Agent in Tlamatini

Step-by-step guide for a new workflow agent. Follow all 8 steps in order. Replace `<agent_name>` (lowercase, underscored, e.g. `shoter`) and `<AgentName>` (PascalCase, e.g. `Shoter`) throughout.

> **Reference implementations** — read these first:
> - Simple agent with outputs: `agent/agents/shoter/shoter.py` + `config.yaml`
> - Source-log monitor: use a current short-lived agent such as `agent/agents/telegrammer/telegrammer.py` as the scaffolding reference, not the retired Telegramer path.
> - No downstream: `agent/agents/emailer/emailer.py`
> - Inline-mirrored Tlamatini runtime (ACPX): `agent/agents/acpxer/acpxer.py`. Pool subprocesses have no `sys.path` back into `agent.*`, so anything needing Tlamatini runtime mechanics must be ported inline, not imported.

## Common Pitfalls (read first)

1. **Naming drift** — `agentDescription` in the migration is the single source of truth. The CSS class, classMap key, `chat_agent_*` tool name, `_EXEC_REPORT_TOOLS` key, and Flow-Generator branch each use a **different transform** of it. Fix the name in the migration first; don't rename later. See Naming Convention below.
2. **Empty-string overwrites of template defaults** — `save_agent_config_view` **deep-merges** posted JSON over the template's `config.yaml`. Writing `config.my_field = ''` (connection update, flow generator, canvas dialog) **destroys** the default. Always omit-if-empty. The Flow-Generator enforces this via a `set(key, value)` helper (Step 7.7).
3. **Pool-name cardinal mismatch** — pool folders are `<base>_<N>` (e.g. `executer_2`). Emitting bare `"executer"` into `target_agents` makes the Starter fail on first hop. Underscores, not hyphens.
4. **Forgetting `_IS_REANIMATED`** — without the marker, the log truncates on every resume. Add the marker **before** `logging.basicConfig(...)`.
5. **Concurrency guard on looping flows** — if your agent starts downstream agents, call `wait_for_agents_to_stop(target_agents)` **before** the `start_agent(...)` loop, or re-entrant loops spawn duplicates.
6. **`_EXEC_REPORT_TOOLS` miss for state-changing agents** — skip Step 7.6 and Multi-Turn users see no table for your agent. Silent data loss.
7. **Flow-Generator `_mapToolArgsToAgentConfig` miss** — if the LLM can launch your agent (Step 7.5) but you skip Step 7.7, the generated `.flw` node has no config fields set and the runtime silently uses template defaults.
8. **6 JS edit locations** — `acp-canvas-core.js` touches connections in 6 separate places. Missing any one breaks creation, removal, undo, redo, or `.flw` load.
9. **CSS gradient duplicated in JS** — never type a gradient string inside `populateAgentsList()`. Use `applyAgentToolIconStyle()` so the sidebar icon inherits from CSS.
10. **Importing `agent.*` from a pool subprocess** — `ModuleNotFoundError` at runtime. Port the needed ~100-200 lines inline instead. See `acpxer.py`.
11. **Temp / Templates outside Tlamatini** — an agent that writes temp files to `C:\Temp` / `%TEMP%` / a bare `tempfile.gettempdir()`, or scaffolds a project dir to an arbitrary location, violates the 2026-06-02 directory policy. Temp → `<app>/Temp` (`TLAMATINI_TEMP`); scaffolded project/template dirs → `<app>/Templates` (`TLAMATINI_TEMPLATES`) unless the user gives a path. See Step 1b and `agent/path_guard.py` / `prompt.pmt` Rules 15/16.

---

## Step 1 · Backend: Agent Directory and Script

Create `agent/agents/<agent_name>/<agent_name>.py` + `config.yaml`.

### 1a. `config.yaml`

```yaml
# <AgentName> Agent Configuration
my_param: "default_value"

# Connection fields — include ONLY the ones that apply:
source_agents: []       # If this agent monitors upstream logs
target_agents: []       # If this agent starts downstream agents
# output_agents: []     # ONLY for Stopper/Ender/Cleaner (canvas wiring, NOT for starting)
```

**Connection-field rules:**
- Starts downstream → `target_agents: []`
- Monitors upstream logs → `source_agents: []`
- Stopper/Cleaner-style (no downstream) → `output_agents: []` instead of `target_agents`
- **Ender** is special: `target_agents` = agents to KILL, `output_agents` = Cleaners to launch after, `source_agents` = graphical only. On resolve, Ender deletes the target's `reanim*` files.
- OR/AND gates use `source_agent_1`, `source_agent_2` (scalars).
- Asker/Forker use `target_agents_a`, `target_agents_b`.

### 1b. `<agent_name>.py`

**Copy the full boilerplate from `agent/agents/shoter/shoter.py`** — module preamble, all helpers (`load_config`, `get_python_command`, `get_user_python_home`, `get_agent_env`, `get_pool_path`, `get_agent_directory`, `get_agent_script_path`, `is_agent_running`, `wait_for_agents_to_stop`, `start_agent`, `write_pid_file`, `remove_pid_file`), and the `main()` shape. Do not modify the helpers.

Critical requirements (do not skip any):
- `os.environ['FOR_DISABLE_CONSOLE_CTRL_HANDLER'] = '1'` MUST be the first statement after `import os, sys`.
- Log file name MUST be `{directory_name}.log` (the canvas reads this).
- `_IS_REANIMATED` (see Reanimation below) MUST be set **before** `logging.basicConfig(...)`.
- PID file written immediately, removed in a `finally` block.
- Concurrency guard: if `target_agents`, call `wait_for_agents_to_stop(target_agents)` **before** the `start_agent` loop.
- If the agent persists restart state (offsets, counters, checkpoints), name those files `reanim*` so Ender can reset them on shutdown.
- **Temp/Templates directory policy (2026-06-02).** If the agent creates **temporary** files, write them under `<app>/Temp`, never `C:\Temp` / `%TEMP%` / a bare `tempfile.gettempdir()`. The parent exports `TLAMATINI_TEMP` + `TEMP`/`TMP` and pins `tempfile.tempdir`, all inherited by the pool, so `tempfile.*` already lands correctly — but for standalone correctness copy the module-top guard from `executer.py` verbatim: `if (os.environ.get('TLAMATINI_TEMP') or '').strip(): import tempfile as _tlt_tempfile; _tlt_tempfile.tempdir = os.environ['TLAMATINI_TEMP'].strip(); …` (keep it an `if`-block, NOT a top-level `def`, so it sits above the imports without tripping ruff **E402**). If the agent **scaffolds a project/template directory** (firmware/engine style — STM32er/ESP32er/Arduiner/Unrealer), default its parent to `<app>/Templates` (`TLAMATINI_TEMPLATES`) unless the user supplies a path. Resolvers: `agent/path_guard.py` (`get_app_temp_root` / `get_app_templates_root`). LLM-facing: `prompt.pmt` Rules 15/16.

The agent's `main()` skeleton:

```python
def main():
    config = load_config()
    write_pid_file()
    try:
        if _IS_REANIMATED:
            logging.info(f"🔄 {CURRENT_DIR_NAME} REANIMATED (resuming from pause)")
            logging.info("=" * 60)
        target_agents = config.get('target_agents', [])
        logging.info("🚀 <AGENT_NAME> AGENT STARTED")

        # ===== YOUR CORE LOGIC HERE =====

        if target_agents:
            wait_for_agents_to_stop(target_agents)
            for target in target_agents:
                start_agent(target)
        logging.info("🏁 <AgentName> agent finished.")
    finally:
        time.sleep(0.4)  # Keep LED green briefly
        remove_pid_file()
    sys.exit(0)
```

### Reanimation Support

Two lifecycle modes:
- **Fresh start**: no `AGENT_REANIMATED` env var → log truncated → `"STARTED"` → reanim files ignored (Ender cleaned them).
- **Reanimation** (pause/resume): `AGENT_REANIMATED=1` → log NOT truncated → `"REANIMATED"` → reanim files restore state.
- `paused_agents.reanim` in the pool dir tracks who was running when paused.

**Detection (required, every agent)** — right after `LOG_FILE_PATH` is set, **before** `logging.basicConfig(...)`:

```python
_IS_REANIMATED = os.environ.get('AGENT_REANIMATED') == '1'
if not _IS_REANIMATED:
    open(LOG_FILE_PATH, 'w').close()
```

**Offset persistence (only agents that poll source logs)** — track offsets in `reanim.pos` (or `reanim_<source>.pos` per source):

```python
REANIM_FILE = "reanim.pos"
def save_reanim_offset(offset):
    with open(REANIM_FILE, 'w') as f: f.write(str(offset))
def get_reanim_offset(log_file_path):
    if os.path.exists(REANIM_FILE):
        with open(REANIM_FILE, 'r') as f: return int(f.read().strip())
    return 0
```

Load at startup, call `save_reanim_offset(offset)` after each read.

### Structured Output Sections (REQUIRED if Parametrizer consumes the output)

Use the unified section format — the only format Parametrizer parses:

```
INI_SECTION_<AGENT_TYPE><<<
field1: value1
field2: value2

multi-line body content (becomes 'response_body')
>>>END_SECTION_<AGENT_TYPE>
```

Rules:
1. `<AGENT_TYPE>` = UPPERCASE base name (`APIRER`, `CRAWLER`, `GOOGLER`).
2. KV header before the first blank line (split on first `: `).
3. Body after first blank line → stored as `response_body`. Arbitrary size, multi-line.
4. No blank line = no body (KV only).
5. **Single atomic `logging.info()` call per section** — never split, concurrent writes can interleave and corrupt.
6. N results = N separate sections.

```python
logging.info(
    f"INI_SECTION_MY_AGENT<<<\n"
    f"url: {url}\n"
    f"status: {status_code}\n"
    f"\n"
    f"{response_content}\n"
    f">>>END_SECTION_MY_AGENT"
)
```

**Register in 3 places:**
1. `parametrizer.py` → add base name to `SECTION_AGENT_TYPES` (the unified parser handles the rest).
2. `views.py` → add field list to `PARAMETRIZER_SOURCE_OUTPUT_FIELDS` (KV header fields + `response_body` if present).
3. `README.md` → add a row to the **Supported Source Agents** table.

---

## Step 2 · Backend: Django View for Connection Updates

### 2a. Add to `agent/views.py` (copy `update_shoter_connection_view`):

```python
@csrf_exempt
@require_POST
def update_<agent_name>_connection_view(request, agent_name):
    """Update a <AgentName> agent's config.yaml on canvas connect/disconnect."""
    try:
        data = json.loads(request.body.decode('utf-8'))
        target_agent = data.get('target_agent')
        action = data.get('action', 'add')
        connection_type = data.get('type', 'target')  # 'source' | 'target'
        if not target_agent:
            return HttpResponse(json.dumps({"success": False, "message": "Missing target_agent"}),
                                content_type='application/json', status=400)

        # agent-N → agent_N
        parts = agent_name.split('-')
        cardinal = parts.pop() if parts[-1].isdigit() else None
        base = "_".join(parts)
        pool_name = f"{base}_{cardinal}" if cardinal else base
        if '..' in pool_name or '/' in pool_name or '\\' in pool_name:
            return HttpResponse(json.dumps({"success": False, "message": "Invalid agent name"}),
                                content_type='application/json', status=400)

        config_path = os.path.join(get_pool_path(request), pool_name, 'config.yaml')
        if not os.path.exists(config_path):
            return HttpResponse(json.dumps({"success": False, "message": f"Config not found: {config_path}"}),
                                content_type='application/json', status=404)
        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f) or {}

        # Target → pool name
        tparts = target_agent.split('-')
        tcard = tparts.pop() if tparts[-1].isdigit() else None
        tbase = "_".join(tparts)
        target_pool = f"{tbase}_{tcard}" if tcard else tbase

        list_name = 'source_agents' if connection_type == 'source' else 'target_agents'
        if not isinstance(config.get(list_name), list):
            config[list_name] = []
        if action == 'add' and target_pool not in config[list_name]:
            config[list_name].append(target_pool)
        elif action == 'remove' and target_pool in config[list_name]:
            config[list_name].remove(target_pool)

        with open(config_path, 'w', encoding='utf-8') as f:
            yaml.dump(config, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
        return HttpResponse(json.dumps({"success": True, "message": f"{action} {target_pool} in {list_name}"}),
                            content_type='application/json')
    except Exception as e:
        return HttpResponse(json.dumps({"error": str(e)}), content_type='application/json', status=500)
```

### 2b. Register URL in `agent/urls.py`:

```python
path('update_<agent_name>_connection/<str:agent_name>/', views.update_<agent_name>_connection_view, name='update_<agent_name>_connection'),
```

---

## Step 3 · Backend: Database Migration

Create `agent/migrations/<NNNN>_add_<agent_name>.py` (next sequential number after the highest existing migration):

```python
from django.db import migrations

def add_<agent_name>_agent(apps, schema_editor):
    Agent = apps.get_model('agent', 'Agent')
    if Agent.objects.filter(agentDescription='<AgentName>').exists():
        return
    next_id = (Agent.objects.order_by('-idAgent').values_list('idAgent', flat=True).first() or 0) + 1
    Agent.objects.create(idAgent=next_id, agentName=f'agent-{next_id}',
                         agentDescription='<AgentName>', agentContent='true')

def remove_<agent_name>_agent(apps, schema_editor):
    apps.get_model('agent', 'Agent').objects.filter(agentDescription='<AgentName>').delete()

class Migration(migrations.Migration):
    dependencies = [('agent', '<previous_migration_name>')]
    operations = [migrations.RunPython(add_<agent_name>_agent, remove_<agent_name>_agent)]
```

`agentDescription` is the **display name** in the sidebar and the **single source of truth** for naming downstream. See Naming Convention.

Run `python Tlamatini/manage.py migrate`.

---

## CRITICAL: Agent Naming Convention

`agentDescription` (e.g. `"Shoter"`, `"Monitor Log"`, `"Node Manager"`, `"Gateway Relayer"`) gets transformed three different ways in three contexts. Mixing them breaks colors, connections, or sidebar icons.

| Context | Transform | `"Node Manager"` | `"Shoter"` |
|---|---|---|---|
| CSS classMap key | `name.toLowerCase().replace(/\s+/g, '-')` | `'node-manager'` | `'shoter'` |
| Sidebar visual resolver | same as classMap via `getAgentTypeClass()` / `applyAgentToolIconStyle()` | `'node-manager'` | `'shoter'` |
| Connection handlers | `name.toLowerCase()` (keeps spaces) | `'node manager'` | `'shoter'` |

Single-word agents: all 3 forms identical. Multi-word agents: classMap/sidebar use **hyphens**, connection code uses **spaces**.

### Sidebar Color Rule — never duplicate gradients in JS

```javascript
const iconDiv = document.createElement('div');
iconDiv.classList.add('agent-tool-icon');
applyAgentToolIconStyle(iconDiv, description);   // ✅ inherits from canvas CSS
```

NOT:
```javascript
else if (lowerDesc === 'node manager') iconDiv.style.background = 'linear-gradient(...)';   // ❌ drift
```

---

## Step 4 · Frontend: CSS Styling

Edit `agent/static/agent/css/agentic_control_panel.css`.

### 4a. Pick a UNIQUE 4-color gradient

`0%, 33%, 66%, 100%`, visually distinct from every existing agent. Scan the file first for collisions. Sidebar icons inherit through `applyAgentToolIconStyle()` — define the gradient once, here only.

### 4b. Add the rules

```css
/* <AgentName> Agent */
.canvas-item.<css_class_name> {
    background-color: #<color1>;
    background: linear-gradient(135deg, #<c1> 0%, #<c2> 33%, #<c3> 66%, #<c4> 100%);
    color: white;
    font-size: smaller;
}
.canvas-item.<css_class_name>:hover {
    background: linear-gradient(135deg, #<c1_light> 0%, #<c2_light> 33%, #<c3_light> 66%, #<c4_light> 100%);
    box-shadow: 0 6px 15px rgba(<r>, <g>, <b>, 0.5);
}
```

### 4c. Verify visual parity

Gradient must exist in **CSS only**. Sidebar resolves through `applyAgentToolIconStyle()`. After implementation, manually confirm sidebar icon matches the deployed canvas node, both for newly dragged and `.flw`-loaded diagrams.

---

## Step 5 · Frontend: JavaScript Integration

Four files. The two pitfalls are **using the wrong name form** (table above) and **duplicating the CSS gradient**.

### 5a. `acp-agent-connectors.js` — fetch connector

```javascript
async function update<AgentName>Connection(agentId, targetAgentId, action, type = 'target') {
    try {
        const response = await fetch(`/agent/update_<agent_name>_connection/${agentId}/`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', ...getHeaders() },
            credentials: 'same-origin',
            body: JSON.stringify({ target_agent: targetAgentId, action, type })
        });
        if (!response.ok) {
            console.error(`--- Failed to update <AgentName> ${agentId}:`, response.statusText);
        }
    } catch (error) {
        console.error(`--- Error updating <AgentName> ${agentId}:`, error);
    }
}
```

### 5b. `acp-canvas-core.js` — 6 locations

1. **`applyAgentTypeClass()` classMap** (~line 32) — KEY is the **hyphenated** form:
   ```javascript
   'shoter': 'shoter-agent',
   'node-manager': 'nodemanager-agent',
   ```
2. **`AGENTS_NEVER_START_OTHERS`** (~line 94) — hyphenated form if the agent does NOT start downstream.
3. **`populateAgentsList()`** (~line 830) — keep the shared helper; do NOT add a per-agent gradient branch:
   ```javascript
   applyAgentToolIconStyle(iconDiv, description);
   ```
4. **`removeConnection()`** (~line 600) — SPACED form:
   ```javascript
   if (targetAgentName.toLowerCase() === 'node manager') updateNodeManagerConnection(targetId, sourceId, 'remove', 'source');
   if (sourceAgentName.toLowerCase() === 'node manager') updateNodeManagerConnection(sourceId, targetId, 'remove', 'target');
   ```
5. **`removeConnectionsFor()`** (~line 740) — SPACED form, with deletion guards (`!targetBeingDeleted` / `!sourceBeingDeleted`).
6. **mouseup handler** (~line 1200) — SPACED form, `'add'` instead of `'remove'`.

### 5c. `acp-canvas-undo.js` — undo/redo

Search for an existing pattern (e.g. `updateGatewayRelayerConnection`); mirror it in both undo and redo. SPACED form. Redo section uses `'remove'`, undo section uses `'add'`.

### 5d. `acp-file-io.js` — `.flw` load

In `restoreAgentConnection`'s two switch statements (source side + target side), add cases with the SPACED form, `'add'` action:

```javascript
// SOURCE-SIDE switch:
case 'node manager': await updateNodeManagerConnection(sourceId, targetId, 'add', 'target'); break;
// TARGET-SIDE switch:
case 'node manager': await updateNodeManagerConnection(targetId, sourceId, 'add', 'source'); break;
```

### 5e. `/* global */` declarations

Top of `acp-canvas-core.js`, `acp-canvas-undo.js`, `acp-file-io.js` — add `update<AgentName>Connection` to each, so the linter knows.

---

## Step 6 · Documentation: `agentic_skill.md`

Edit `agent/agents/flowcreator/agentic_skill.md` — register the new agent so FlowCreator AI can use it:

```markdown
### <N>. <AgentName>
- **Purpose**: <One-line description>.
- **Pool name pattern**: `<agent_name>_<n>`
- **Starts other agents**: YES/NO
- **Config parameters**:
  - `<param1>`: <default> (<description>)
  - `source_agents`: [] (upstream agents — canvas connection tracking)
  - `target_agents`: [] (downstream agents to start after execution)
```

Also touch: **Connection Rules**, **Agent Categories** (Active/Terminal-Monitoring), and **Output Format Rules** if special handling is needed.

---

## Step 7 · Documentation: `README.md`

7a. **Agent count** — increment in 3 places: Overview (~L65), Key Features > Visual Workflow Designer (~L157), Workflow Agents header (~L963).
7b. **Project Structure tree** — add `│   │   │   ├── <agent_name>/          # <brief description>`.
7c. **Agent Architecture** — add the agent to either **Deterministic** or **LLM-powered** list.
7d. **Workflow Agents table** — add a row to the appropriate category (Control/Monitoring/Notification/Action/Logic-Gates/Routing/Utility):
   ```markdown
   | **<agent_name>** | <Description / Purpose> | `<key>`: value<br>`target_agents`: ... |
   ```
   **The `Purpose` cell is what the canvas Description menu AND the sidebar tooltip display verbatim.** Skip this row and both surfaces fall back to empty. The ACP lookup normalizes case, spaces, hyphens, and underscores.
7e. **Glossary** — `| **<AgentName>** | <One-line definition> |`.
7f. **Changelog (Recent Updates)** — prepend `- **Added <AgentName> Agent** - <brief>`.
7g. **Connection Endpoints API table** — `| /update_<agent_name>_connection/<agent_name>/ | POST | Update <agent_name> connections |`.

---

## Step 7.5 · OPTIONAL: Wrapped Chat-Agent Tool (LLM-callable)

Skip if the agent is canvas-only. Do this if Multi-Turn LLM should launch the agent as a sub-process tool ("Hey Tlamatini, SSH into 10.0.0.1 ...").

Append to `WRAPPED_CHAT_AGENT_SPECS` in `agent/chat_agent_registry.py`:

```python
ChatWrappedAgentSpec(
    key="myagent",
    template_dir="myagent",                        # MUST match agent/agents/<dir>
    tool_name="chat_agent_myagent",                # MUST start with "chat_agent_"
    tool_description="Chat-Agent-MyAgent",
    display_name="MyAgent",                        # MUST match DB agentDescription
    purpose="Do the thing. Use when the user asks about X.",
    example_request="Run MyAgent with param1='value', param2='value2'",
    aliases=("myagent", "my agent"),
    security_hints=("myagent", "keyword"),
    # poll_window_seconds=3,                       # optional, default 8
    # long_running=True,                           # for watch-loop agents
),
```

The unified agent picks it up via `WRAPPED_CHAT_AGENT_BY_TOOL_NAME` — no edits in `mcp_agent.py` or `tools.py`. The tool returns JSON: `run_id`, `status`, `log_excerpt`, `runtime_dir`, `log_path`.

**Seed the wrapper `Tool` row (so it is toggleable in Configure Mcps/Tools).** Add a tiny migration mirroring `migrations/0121_add_chat_agent_talker_tool.py` that creates a `Tool` row with `toolDescription="Chat-Agent-MyAgent"` (the same `tool_description` as the spec). Without it the wrapper still defaults ON (fail-open) but the user has no checkbox to disable it.

**Dual enable-gate (do NOT bypass).** `get_mcp_tools()` binds your `chat_agent_<name>` for the LLM ONLY when BOTH (a) the wrapper Tool row `Chat-Agent-<Name>` is enabled (Configure Mcps/Tools) AND (b) the Agent row `<Name>` is enabled (Configure Agents). Disabling EITHER makes the agent invisible to the LLM (reported as unknown). This is exactly why `display_name` MUST equal the DB `agentDescription` — the Agent-row gate is keyed on `agent_<display>_status`. Verify: uncheck the agent in Configure Agents (or the wrapper in Configure Mcps), ask the LLM to use it, and confirm it reports the agent as unavailable.

---

## Step 7.6 · MANDATORY for EVERY Multi-Turn agent: Exec Report capture

> ⚠️ **MANDATORY DIRECTIVE — NON-NEGOTIABLE (Ángela López Mendoza, 2026-06-07):** EVERY agent that can run in Multi-Turn (anything with a wrapped `chat_agent_<name>` tool from Step 7.5) **MUST be captured and shown in the Exec Report** — **observational/output agents** (Talker, Shoter, Camcorder, Recorder, AudioPlayer, VideoPlayer) and **read-only LLM agents** (Crawler, Prompter, Summarizer, File/Image interpreters, Monitor-*, Recmailer, …) **INCLUDED**, plus every newly-created agent. A Multi-Turn agent that produces **no** Exec-report row when Exec report is ON is a **defect** (this was the Talker bug: a run showed zero tables). The "state-changing only" rule is **gone**.

**Good news — capture is AUTOMATIC.** `agent/mcp_agent.py::_resolve_exec_report_spec` captures ANY wrapped `chat_agent_*` (except the management/polling helpers in `_MANAGEMENT_TOOLS`) by deriving `agent_key`/display from the wrapped chat-agent registry. **So if you did Step 7.5, your agent is already captured — you write NO Exec-report code.** The mandatory work is just to VERIFY it.

**0. (MANDATORY) Verify capture.** Run the agent in Multi-Turn with **Exec report ON** and confirm a "List of <Display> Operations" table appears. The audit test `agent.tests.ExecReportCaptureTests.test_every_multiturn_agent_is_capturable_including_observational` fails if ANY wrapped chat-agent resolves to no row — run `python manage.py test agent.tests.ExecReportCaptureTests` and keep it green.

**OPTIONAL refinement** — only for a native caption gradient or to merge a direct @tool with its wrapped launch (otherwise the readable default `.exec-report-caption` background is used and the display comes from the registry `display_name`):

**1. `agent/mcp_agent.py`** — one line in `_EXEC_REPORT_TOOLS` (to share an `agent_key` between a direct @tool and its wrapped launch, or to fix display casing):
```python
"chat_agent_myagent": ("myagent", "MyAgent"),
```
`agent_key` (lowercase, no spaces) SHOULD match the canvas-item CSS class root.

**2. `agent/static/agent/css/agent_page.css`** — two rules mirroring the canvas gradient (purely cosmetic; skip and the default caption applies):
```css
.exec-report-caption-<agent_key> {
    background: linear-gradient(135deg, #<c1> 0%, #<c2> 100%);
    color: #ffffff;  /* or #1b1b1b on light backgrounds */
}
.exec-report-<agent_key> .exec-report-cmd { border-left: 3px solid #<primary>; }
```

**3.** Dark caption → add `agent_key` to the dark-header `thead th` selector list (sets `color: #f5f5f5; background: rgba(0,0,0,0.55)`).

Verification: `python manage.py test agent.tests.ExecReportCaptureTests` is generic (incl. the all-agents audit); no per-agent test needed.

> **Ask Execs (automatic — no wiring needed).** If your wrapped tool is state-changing, it is **automatically** gated by the "Ask Execs" toggle: when the user enables it, the Multi-Turn executor prompts Proceed/Deny before your `chat_agent_<key>` runs. `MultiTurnToolAgentExecutor._requires_exec_permission` prompts for **every** tool except those in `_MANAGEMENT_TOOLS` ∪ `_TOOL_QUOTA_EXEMPT`. So: a state-changing or action tool needs **no** Ask-Execs code. A **read-only / polling** tool (status/log/inspection that should NOT be prompted) must be added to `_MANAGEMENT_TOOLS` and/or `_TOOL_QUOTA_EXEMPT` in `mcp_agent.py` (and is likely already absent from `_EXEC_REPORT_TOOLS` anyway). The permission dialog's "shell" line comes from `_infer_execution_shell(tool_name, args)` — add a branch there if your tool runs through an unusual shell/interpreter (else it falls back to the platform shell). See `docs/claude/multi-turn.md` → *Ask Execs*.

---

## Step 7.7 · REQUIRED if Step 7.5 done: Flow-Generator Mapping

`agent_page_chat.js` → `_mapToolArgsToAgentConfig(canonicalName, rawArgs, _toolName)` — add a branch:

```javascript
// ── MyAgent ──
} else if (lower === 'myagent') {
    set('param1', pairs.param1);
    set('param2', pairs.param2 || pairs.alt_name);
    const nested = collectDotted('nested');
    if (Object.keys(nested).length > 0) config.nested = nested;
```

Rules:
- Use `set(key, value)` — it refuses empty strings, protecting template defaults from the deep-merge.
- Field names MUST match `config.yaml` keys EXACTLY (mismatch = silent default-fallback).
- Dotted nested keys (`smtp.host=...`) → `collectDotted('smtp')`.
- Never set `config.target_agents` / `config.source_agents` here — `_generateAndDownloadFlow` does that with cardinal-suffixed pool names.

Test by dragging the agent into the ACP once and noting the dialog field names verbatim.

---

## Step 7.8 · MANDATORY for Multi-Turn agents: a Catalog-of-Prompts example

> ⚠️ **MANDATORY DIRECTIVE — NON-NEGOTIABLE (Ángela López Mendoza, 2026-06-07).** If you did Step 7.5 (the agent is **Multi-Turn-capable** via a wrapped `chat_agent_<name>` tool), you **MUST** seed **at least ONE** example prompt for it into the **Catalog of Prompts**. This is a hard completion gate: a Multi-Turn agent shipped **without** a catalog prompt is **INCOMPLETE** and the task is **not done**. (A canvas-only agent with NO wrapped tool is exempt.) Do NOT skip this.

Add a migration `agent/migrations/<NNNN>_add_<agent_name>_demo_prompts.py` that seeds rows into the **`Prompt`** model (`idPrompt`, `promptName='prompt-<N>'`, `promptContent`):

```python
from django.db import migrations

# At least ONE demo prompt for a Multi-Turn agent (1 minimum; tiered basic/medium/hard is the gold standard).
DEMO = (
    "Tlamatini, run the **<AGENTNAME> DEMO**, please — <one realistic, SAFE task that drives "
    "chat_agent_<agent_name> end to end>. Tick ONLY the Multi-Turn checkbox; use ONLY "
    "chat_agent_<agent_name>. ... End with END-RESPONSE."
)
_NEW_PROMPTS = ((<next_free_slot>, DEMO),)   # e.g. (76, DEMO)

def add_demo_prompts(apps, schema_editor):
    Prompt = apps.get_model('agent', 'Prompt')
    for pid, content in _NEW_PROMPTS:
        Prompt.objects.update_or_create(
            idPrompt=pid,
            defaults={'promptName': f'prompt-{pid}', 'promptContent': content},
        )

def remove_demo_prompts(apps, schema_editor):
    Prompt = apps.get_model('agent', 'Prompt')
    Prompt.objects.filter(idPrompt__in=[pid for pid, _ in _NEW_PROMPTS]).delete()

class Migration(migrations.Migration):
    dependencies = [('agent', '<previous_migration_name>')]
    operations = [migrations.RunPython(add_demo_prompts, remove_demo_prompts)]
```

Rules (do not break the catalog):
- **CONTIGUITY contract (relaxed to fallback-only in v1.38.1)** — the `#prompts-catalog` primary load is now ONE **`GET /agent/list_prompts/`** call returning ALL `Prompt` rows ordered by `idPrompt` (a gap no longer hides later prompts), but the legacy `prompt-1, prompt-2, …` probe loop in `static/agent/js/tools_dialog.js` is KEPT as the offline fallback and **still BREAKS at the first missing slot**, so `idPrompt` / `promptName` suffixes MUST stay a contiguous, gap-free `prompt-1..N`. **Find the current highest `idPrompt`** (read the latest `*_demo_prompts.py` migration) and **APPEND** at the next free slot with no renumber. `MAX_PROMPTS=256` (bumped from 100 on 2026-06-29 when the wizard filled slot 100; keep the JS const + CLAUDE.md + this guide + the `tlamatini-agent-creation` skill byte-coherent).
- The prompt must drive the new agent via `chat_agent_<agent_name>`, with a **realistic, SAFE** task (the daily chat test may run it — no destructive ops).
- Phrase it so the prompt-catalog **mode badges** infer the right toggles (Multi-Turn ON for operator prompts); style the HTML banner to mirror the agent's CSS gradient (copy a recent sibling's prompt migration).
- Implement the reverse migration (delete the seeded rows) and set `dependencies` on the previous migration. Then `python manage.py migrate` and confirm the prompt shows in the `#prompts-catalog` modal.

---

## Step 8 · Lint

```bash
python -m ruff check           # fix ALL issues
npm run lint                   # fix errors only (ignore warnings)
```

---

## Step 9 · Self-Update & Self-Modify Carriage (ship the agent to users + Tlamatini's own source)

A new agent must reach (a) existing users via **self-update**, and (b) Tlamatini's own
rebuildable source tree via **self-modify**. The good news: an agent built exactly as above
is carried **AUTOMATICALLY** by both — but you MUST verify, and a new *dependency* is the one
manual case.

**Automatic — no action needed:**
- **Self-update release** — `build.py` ships the whole `agent/agents/` tree via
  `optional_dir_copies` (carrier mechanism 3) plus the PyInstaller import graph, so
  `agents/<agent_name>/` auto-ships. On update, `apply_update.ps1` does `agents -> agents_backup`
  then drops the new version in, so your agent lands.
- **Self-modify snapshot** — `copy_source_assets.py`'s generic walk carries every new `.py` /
  `config.yaml` (the `config.yaml` is auto-**redacted**). Nothing to add.
- **Your migration's rows reach EXISTING users** — the new `Agent` row, the
  `Chat-Agent-<Name>` `Tool` row (Step 7.5), and the demo `Prompt` rows (Step 7.8) are applied
  to the user's existing database by the self-update's **post-update migrate**: the updater
  stages the user's DB through `DB/ToLoad` and `manage.py::_run_post_update_migrate_if_flagged`
  runs `migrate` on the next launch (see `apply_update.ps1` step 3b + `manage.py`). So just ship
  the migration normally — the user keeps their chat history + toggles AND gets your new agent.

**MANUAL — only if your agent imports a NEW third-party library** (the numpy/opencv-class case;
a pool agent runs under the **carried Python**, NOT the frozen exe, so its libs must be present
there): it must be
1. pinned in `requirements.txt`,
2. asserted in `build.py` — add the import name to `_CARRIED_PYTHON_REQUIRED_IMPORTS` (carried-
   Python probe) AND the frozen-asset `_agent_libs` verify list, so the build ABORTS LOUDLY if
   the lib is missing instead of shipping a pool agent that crashes at runtime, and
3. if PyInstaller's import graph can't see it (it's only imported by the out-of-process pool
   agent), add a `--collect-all <pkg>` / `--hidden-import` to the PyInstaller command in
   `build.py` so it is embedded in the frozen `_internal` too.

**(MANDATORY) Verify carriage with the two inclusion sweeps — both must exit CLEAN:**
```bash
python .claude/skills/tlamatini-self-modify-inclusion/scripts/sweep_self_modify.py
python .claude/skills/tlamatini-self-update-inclusion/scripts/sweep_self_update.py
```
They confirm the new agent source ships, secrets are redacted, every `build.py` input survives,
the updater preserve lists stay coherent, and new migrations reach users. Full runbooks: the
**`tlamatini-self-modify-inclusion`** and **`tlamatini-self-update-inclusion`** skills.

---

## Summary Checklist

```
[ ] 1. agent/agents/<agent_name>/<agent_name>.py + config.yaml
    [ ] _IS_REANIMATED set BEFORE logging.basicConfig
    [ ] Reanimation marker in main() after write_pid_file()
    [ ] If polls source logs: reanim offset save/load
    [ ] If feeds Parametrizer: INI_SECTION_<TYPE><<<...>>>END_SECTION_<TYPE>
        with a SINGLE atomic logging.info() call per section, registered in
        SECTION_AGENT_TYPES (parametrizer.py) + PARAMETRIZER_SOURCE_OUTPUT_FIELDS (views.py) + README table
[ ] 2. update_<agent_name>_connection_view in views.py + URL in urls.py
[ ] 3. Migration → `python manage.py migrate`
    [ ] Decide single-word vs multi-word display name (drives all name forms)
[ ] 4. agentic_control_panel.css: UNIQUE 4-color gradient + .canvas-item.<class>-agent
       normal + hover (no per-agent gradient in JS — sidebar inherits)
[ ] 5. JS (CORRECT NAME FORM PER CONTEXT):
    [ ] 5a connector in acp-agent-connectors.js
    [ ] 5b acp-canvas-core.js × 6: classMap HYPHENATED, AGENTS_NEVER_START_OTHERS
        HYPHENATED, populateAgentsList = shared helper (no per-agent gradient),
        removeConnection/removeConnectionsFor/mouseup all SPACED
    [ ] 5c acp-canvas-undo.js undo+redo SPACED
    [ ] 5d acp-file-io.js BOTH switches SPACED
    [ ] 5e /* global */ updated in all 3 files
[ ] 6. agentic_skill.md entry
[ ] 7. README.md: count, structure, classification, Workflow table (Purpose = ACP
       Description menu + sidebar tooltip text), Glossary, Changelog, API endpoint
[ ] 7.5 (OPTIONAL) ChatWrappedAgentSpec in chat_agent_registry.py
       (tool_name starts with chat_agent_, display_name matches DB agentDescription)
[ ] 7.6 (MANDATORY for EVERY Multi-Turn agent) Exec-report capture is AUTOMATIC
       (no code if Step 7.5 done — observational agents INCLUDED) — VERIFY a
       "List of <Agent> Operations" table appears with Exec report ON, and keep
       ExecReportCaptureTests (incl. the all-agents audit) green. Optional:
       _EXEC_REPORT_TOOLS entry + CSS caption gradient for native styling.
[ ] 7.7 (REQUIRED if 7.5) Flow-Generator branch in _mapToolArgsToAgentConfig
       (set() helper, no empty strings, no target/source_agents)
[ ] 7.8 (MANDATORY if 7.5 — Multi-Turn agent) ≥1 Catalog-of-Prompts example seeded
       via a Prompt-model migration (contiguous idPrompt/prompt-N, SAFE task driving
       chat_agent_<name>) → migrate → appears in #prompts-catalog. A Multi-Turn agent
       WITHOUT a catalog prompt is INCOMPLETE.
[ ] 8. ruff check (fix all) + npm run lint (fix errors); manual sidebar/canvas color parity
[ ] 9. Self-update/self-modify carriage: agent source + migration rows auto-ship AND reach
       EXISTING users via the post-update migrate (DB/ToLoad + manage.py). A NEW third-party
       dependency is the only manual case: add it to requirements.txt + build.py
       (_CARRIED_PYTHON_REQUIRED_IMPORTS, _agent_libs verify list, and a --collect-all/hidden-import
       if PyInstaller can't see it). VERIFY both inclusion sweeps exit CLEAN:
       sweep_self_modify.py + sweep_self_update.py
```
