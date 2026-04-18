---
description: How to create a new Tlamatini agent
---

# Creating a New Agent in Tlamatini

This is a step-by-step guide for creating a new workflow agent. Follow ALL 8 steps in order. Each step includes exact code templates — adapt them by replacing `<agent_name>` (lowercase, underscore-separated, e.g. `shoter`) and `<AgentName>` (PascalCase, e.g. `Shoter`) with your agent's name.

> **Reference implementations**: Study these files before starting:
> - Simple agent with outputs: `agent/agents/shoter/shoter.py` + `config.yaml`
> - Agent with source monitoring: `agent/agents/telegramer/telegramer.py` + `config.yaml`
> - Agent with NO downstream: `agent/agents/emailer/emailer.py` + `config.yaml`

## Common Pitfalls (Read Before You Start)

Most broken agents are broken in one of these exact ways. Pre-commit your brain to checking each one:

1. **Naming drift** — `agentDescription` in the DB migration, the CSS class, the classMap key, the `chat_agent_*` tool name, the `_EXEC_REPORT_TOOLS` key, and the Flow-Generator branch all derive from the display name but use **different transforms**. Fix the name in the migration first; don't rename later. See the "Naming Convention" section below — the single table there is the single source of truth.
2. **Empty-string overwrites of template defaults** — the backend's `save_agent_config_view` **deep-merges** posted JSON over the template's `config.yaml`. Writing `config.my_field = ''` in any wiring code (connection update, flow generator, canvas dialog) **destroys** the template's default value. Always use "omit if empty" semantics. The Flow-Generator now enforces this via a `set(key, value)` helper (Step 7.7).
3. **Pool-name cardinal mismatch** — pool folders on disk are always `<base>_<N>` (e.g. `executer_2`). If your code emits bare `"executer"` into a `target_agents` list, the Starter tries to launch a folder that does not exist and the chain dies on the first hop. Underscores, not hyphens, in pool names.
4. **Forgetting `_IS_REANIMATED`** — an agent without the reanimation marker truncates its log on every resume, destroying the pause/resume observability. Add the marker **before** `logging.basicConfig(...)`, not after.
5. **Concurrency guard on looping flows** — if your agent starts downstream agents, you MUST call `wait_for_agents_to_stop(target_agents)` **before** the `start_agent(...)` loop. Without it, re-entrant loops spawn duplicate processes.
6. **`_EXEC_REPORT_TOOLS` miss for state-changing agents** — if the agent mutates the system and you forget Step 7.6, Multi-Turn users will see no table for your agent in the Exec Report. Silent data loss, no error message.
7. **Flow-Generator `_mapToolArgsToAgentConfig` miss** — if the LLM can launch your agent (Step 7.5) but you skip Step 7.7, the generated `.flw` puts the tool call's args into a node with **no config fields set**, and the runtime silently falls back to template defaults. The flow loads visually fine but runs the wrong behavior.
8. **Forgetting the 6 JS edit locations** — `acp-canvas-core.js` touches connections in 6 separate places. Missing any one breaks either creation, removal, undo, redo, or `.flw` load for that agent.
9. **CSS gradient duplicated in JS** — never type a hard-coded gradient string inside `populateAgentsList()`. Let `applyAgentToolIconStyle()` resolve the sidebar icon color from the same CSS class the canvas uses. If you duplicate, the sidebar and canvas drift over time.

---

## Step 1 · Backend: Create Agent Directory and Script

Create two files inside a new directory:

```
agent/agents/<agent_name>/
├── <agent_name>.py     # Main Python script
└── config.yaml         # Default configuration
```

### 1a. Create `config.yaml`

Define ALL configurable parameters with sensible defaults. Every agent MUST have either `target_agents` or `output_agents` (see rules below):

```yaml
# <AgentName> Agent Configuration

# Custom parameters for this agent
my_param: "default_value"

# Connection fields (include ONLY the ones that apply):
source_agents: []       # If this agent monitors upstream logs
target_agents: []       # If this agent starts downstream agents
# output_agents: []     # ONLY for Stopper/Ender/Cleaner (canvas wiring only, NOT for starting agents)
```

**Rules for connection fields:**
- If the agent **starts downstream agents** → use `target_agents: []`
- If the agent **monitors upstream logs** → use `source_agents: []`
- If the agent is like Stopper/Cleaner (does NOT start downstream) → use `output_agents: []` instead of `target_agents`
- The **Ender** agent is special: it uses `target_agents: []` (agents to KILL), `output_agents: []` (Cleaners to launch after killing), and `source_agents: []` (graphical input connections only — never killed, never started). When Ender resolves a target successfully or finds it already stopped, it also deletes that target's `reanim*` restart-state files.
- OR/AND gates use `source_agent_1`, `source_agent_2` (not a list)
- Asker/Forker use `target_agents_a`, `target_agents_b` (not `target_agents`)

### 1b. Create `<agent_name>.py`

Copy the **exact boilerplate** from `agent/agents/shoter/shoter.py`. The required structure is:

```python
# <AgentName> Agent - <brief description>

import os
import sys

# FIX: Disable Intel Fortran runtime Ctrl+C handler
os.environ['FOR_DISABLE_CONSOLE_CTRL_HANDLER'] = '1'

import time
import yaml
import logging
import subprocess

# Set working directory to script location
try:
    script_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(script_dir)
except Exception as e:
    sys.stderr.write(f"Critical Error: Failed to set working directory: {e}\n")

# Use directory name for log file
CURRENT_DIR_NAME = os.path.basename(os.path.dirname(os.path.abspath(__file__)))
LOG_FILE_PATH = f"{CURRENT_DIR_NAME}.log"
logging.basicConfig(
    filename=LOG_FILE_PATH, level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s', encoding='utf-8'
)
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
console_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
logging.getLogger().addHandler(console_handler)

# --- Copy ALL helper functions from shoter.py ---
# REQUIRED: load_config, get_python_command, get_user_python_home,
#           get_agent_env, get_pool_path, get_agent_directory,
#           get_agent_script_path, is_agent_running, wait_for_agents_to_stop,
#           start_agent, write_pid_file, remove_pid_file
# Copy them EXACTLY — do not modify these utility functions.

PID_FILE = "agent.pid"

def main():
    config = load_config()
    write_pid_file()

    try:
        target_agents = config.get('target_agents', [])
        logging.info("🚀 <AGENT_NAME> AGENT STARTED")

        # ===== YOUR CORE LOGIC HERE =====
        # Implement the agent's primary task
        # =================================

        # Trigger downstream agents (only if this agent starts others)
        if target_agents:
            wait_for_agents_to_stop(target_agents)
            logging.info(f"🚀 Triggering {len(target_agents)} downstream agents...")
            for target in target_agents:
                start_agent(target)

        logging.info("🏁 <AgentName> agent finished.")
    finally:
        time.sleep(0.4)  # Keep LED green briefly for visual feedback
        remove_pid_file()

    sys.exit(0)

if __name__ == "__main__":
    main()
```

**Critical requirements:**
- `os.environ['FOR_DISABLE_CONSOLE_CTRL_HANDLER'] = '1'` MUST be set before any other imports
- PID file MUST be written immediately on start and removed in `finally` block
- Log file name MUST be `{directory_name}.log` (the canvas reads this)
- Copy ALL helper functions (`get_python_command`, `get_agent_env`, `get_pool_path`, `is_agent_running`, `wait_for_agents_to_stop`, etc.) exactly from `shoter.py`
- **Concurrency guard**: If the agent starts downstream agents, it MUST call `wait_for_agents_to_stop(target_agents)` BEFORE the loop that calls `start_agent()`. This prevents duplicate/orphaned processes in looping flows. The wait checks each target's PID file and blocks until all targets have exited, logging an ERROR every 10 seconds while waiting.
- If the agent persists restart/reanimation state (offsets, counters, checkpoints), store it in files named `reanim*` so Ender can reset that state on flow shutdown (examples: `reanim.pos`, `reanim.counter`, `reanim_<source>.pos`). Manual per-agent restart from the contextual menu must preserve these files.

### Reanimation Support

Every agent must support reanimation (pause/resume). There are two lifecycle modes:

- **Fresh start**: No `AGENT_REANIMATED` env var → log truncated → `"STARTED"` logged → reanim files ignored (Ender cleaned them)
- **Reanimation** (pause/resume): `AGENT_REANIMATED=1` → log NOT truncated → `"REANIMATED"` logged → reanim files loaded to restore state
- The `paused_agents.reanim` file in the pool dir stores which agents were running when paused

**1. Reanimation detection (REQUIRED for all agents)**

Add this at module level, right after the `LOG_FILE_PATH` definition and **before** `logging.basicConfig(...)`:

```python
# Reanimation detection: AGENT_REANIMATED=1 means resume from pause
_IS_REANIMATED = os.environ.get('AGENT_REANIMATED') == '1'
if not _IS_REANIMATED:
    open(LOG_FILE_PATH, 'w').close()
```

This ensures the log is only truncated on fresh starts, preserving log continuity across pause/resume cycles.

**2. Reanimation marker in main() (REQUIRED for all agents)**

Add this in `main()` right after `write_pid_file()`:

```python
if _IS_REANIMATED:
    logging.info(f"🔄 {CURRENT_DIR_NAME} REANIMATED (resuming from pause)")
    logging.info("=" * 60)
```

**3. Offset persistence (REQUIRED only for agents that poll source logs)**

Agents that track file offsets (e.g., monitor upstream log files) must also implement reanim offset storage so they resume reading from where they left off:

```python
REANIM_FILE = "reanim.pos"

def save_reanim_offset(offset):
    with open(REANIM_FILE, 'w') as f:
        f.write(str(offset))

def get_reanim_offset(log_file_path):
    if os.path.exists(REANIM_FILE):
        with open(REANIM_FILE, 'r') as f:
            return int(f.read().strip())
    return 0
```

At startup, load the offset from the reanim file. In the polling loop, call `save_reanim_offset(offset)` after each read. For agents monitoring multiple sources, use per-source files: `reanim_<source>.pos`.

### Structured Output Sections (REQUIRED if agent generates data for Parametrizer)

If the new agent produces structured output that Parametrizer can consume (i.e., it generates results, responses, or data blocks that should flow into another agent's `config.yaml`), it **must** emit sections using the **unified section format**. This is the only format Parametrizer knows how to parse.

**Format:**

```
INI_SECTION_<AGENT_TYPE><<<
field1: value1
field2: value2

multi-line body content (becomes 'response_body')
>>>END_SECTION_<AGENT_TYPE>
```

**Rules (mandatory, no exceptions):**

1. `<AGENT_TYPE>` = the UPPERCASE base name of the agent (e.g., `APIRER`, `CRAWLER`, `GOOGLER`).
2. Start marker: `INI_SECTION_<AGENT_TYPE><<<` followed by a newline.
3. End marker: `>>>END_SECTION_<AGENT_TYPE>`.
4. **KV header** (before the first blank line): key-value metadata lines, split on the first `: `.
5. **Body** (after the first blank line): stored as `response_body`. Can be arbitrarily large and multi-line.
6. **No blank line = no body**: if there are no blank lines, the content is parsed as KV fields only.
7. **Single atomic call**: The entire section MUST be emitted in a single `logging.info()` call. Never split across multiple calls — concurrent log writes could interleave and corrupt the block.
8. **One section per output unit**: if the agent produces N results, emit N separate sections.

**Example — agent with KV metadata and body:**

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

**Example — agent with KV fields only (no body):**

```python
logging.info(
    f"INI_SECTION_MY_AGENT<<<\n"
    f"public_key: {pub_key}\n"
    f"private_key: {priv_key}\n"
    f">>>END_SECTION_MY_AGENT"
)
```

**Registration (3 locations):**

After adding the section output to the agent's Python code, you must register it in 3 places:

1. **`parametrizer.py`** — Add the agent's base name to the `SECTION_AGENT_TYPES` list:
   ```python
   SECTION_AGENT_TYPES = [
       ...existing agents...,
       'my_agent',
   ]
   ```
   No per-agent parser code is needed — the unified parser handles all agents automatically.

2. **`views.py`** — Add the agent's field list to `PARAMETRIZER_SOURCE_OUTPUT_FIELDS`:
   ```python
   PARAMETRIZER_SOURCE_OUTPUT_FIELDS = {
       ...existing agents...,
       'my_agent': ['url', 'status', 'response_body'],
   }
   ```
   List only the KV header field names plus `response_body` if the agent has a body section.

3. **`README.md`** — Add a row to the **Supported Source Agents** table in the Parametrizer section.

---

## Step 2 · Backend: Django View for Connection Updates

Add a connection update view to `agent/views.py`. This is called by the frontend when canvas connections are drawn/removed.

### 2a. Add the view function

Add this function to `agent/views.py` (copy the exact pattern from `update_shoter_connection_view`):

```python
@csrf_exempt
@require_POST
def update_<agent_name>_connection_view(request, agent_name):
    """Update a <AgentName> agent's config.yaml when connections are made/removed."""
    try:
        data = json.loads(request.body.decode('utf-8'))
        target_agent = data.get('target_agent')
        action = data.get('action', 'add')
        connection_type = data.get('type', 'target')  # 'source' or 'target'

        if not target_agent:
            return HttpResponse(json.dumps({"success": False, "message": "Missing target_agent"}),
                                content_type='application/json', status=400)

        # Parse agent_name to pool folder name: 'agent-1' -> 'agent_1'
        parts = agent_name.split('-')
        cardinal = None
        if parts[-1].isdigit():
            cardinal = parts.pop()
        base_folder_name = "_".join(parts)
        pool_folder_name = f"{base_folder_name}_{cardinal}" if cardinal else base_folder_name

        if '..' in pool_folder_name or '/' in pool_folder_name or '\\' in pool_folder_name:
            return HttpResponse(json.dumps({"success": False, "message": "Invalid agent name"}),
                                content_type='application/json', status=400)

        pool_base_path = get_pool_path(request)
        config_path = os.path.join(pool_base_path, pool_folder_name, 'config.yaml')

        if not os.path.exists(config_path):
            return HttpResponse(json.dumps({"success": False, "message": f"Config not found: {config_path}"}),
                                content_type='application/json', status=404)

        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f) or {}

        # Parse target_agent to pool name
        target_parts = target_agent.split('-')
        target_cardinal = None
        if target_parts[-1].isdigit():
            target_cardinal = target_parts.pop()
        target_base = "_".join(target_parts)
        target_pool_name = f"{target_base}_{target_cardinal}" if target_cardinal else target_base

        # Determine which config list to modify
        list_name = 'source_agents' if connection_type == 'source' else 'target_agents'
        if list_name not in config or not isinstance(config[list_name], list):
            config[list_name] = []

        if action == 'add':
            if target_pool_name not in config[list_name]:
                config[list_name].append(target_pool_name)
            message = f"Added {target_pool_name} to {list_name}"
        elif action == 'remove':
            if target_pool_name in config[list_name]:
                config[list_name].remove(target_pool_name)
            message = f"Removed {target_pool_name} from {list_name}"
        else:
            message = f"Unknown action: {action}"

        with open(config_path, 'w', encoding='utf-8') as f:
            yaml.dump(config, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

        return HttpResponse(json.dumps({"success": True, "message": message}), content_type='application/json')
    except Exception as e:
        print(f"Error updating <AgentName> connection: {e}")
        return HttpResponse(json.dumps({"error": str(e)}), content_type='application/json', status=500)
```

### 2b. Register the URL in `agent/urls.py`

Add this line to the `urlpatterns` list:

```python
path('update_<agent_name>_connection/<str:agent_name>/', views.update_<agent_name>_connection_view, name='update_<agent_name>_connection'),
```

---

## Step 3 · Backend: Database Migration

Create a Django migration to register the agent in the database so it appears in the sidebar.

Create file: `agent/migrations/<NNNN>_add_<agent_name>.py`

Where `<NNNN>` is the next sequential number after the last existing migration. Check `agent/migrations/` to find the highest number.

```python
from django.db import migrations


def add_<agent_name>_agent(apps, schema_editor):
    Agent = apps.get_model('agent', 'Agent')
    max_id = 0
    for agent in Agent.objects.all():
        if agent.idAgent > max_id:
            max_id = agent.idAgent
    existing = Agent.objects.filter(agentDescription='<AgentName>').first()
    if existing:
        return
    next_id = max_id + 1
    Agent.objects.create(
        idAgent=next_id,
        agentName=f'agent-{next_id}',
        agentDescription='<AgentName>',
        agentContent='true'
    )


def remove_<agent_name>_agent(apps, schema_editor):
    Agent = apps.get_model('agent', 'Agent')
    Agent.objects.filter(agentDescription='<AgentName>').delete()


class Migration(migrations.Migration):
    dependencies = [
        ('agent', '<previous_migration_name>'),  # e.g., '0026_repopulate_all_agents'
    ]
    operations = [
        migrations.RunPython(add_<agent_name>_agent, remove_<agent_name>_agent),
    ]
```

**Important:** The `agentDescription` field value is the **display name** shown in the sidebar. It is the **single source of truth** for all naming across the system. It flows into `dataset.agentName` on canvas items and gets transformed differently in each context. See the Naming Convention below.

After creating the migration, run:
```bash
python Tlamatini/manage.py migrate
```

---

## CRITICAL: Agent Naming Convention (READ THIS FIRST)

The `agentDescription` from the database is the agent's display name (e.g., `"Shoter"`, `"Monitor Log"`, `"Node Manager"`, `"Gateway Relayer"`). This single value gets used in **two naming contexts plus one shared visual resolver**. Getting any of these wrong causes broken colors, broken connections, or invisible sidebar icons.

### The 3 Resolution Contexts

| Context | Transform | Example for `"Node Manager"` | Example for `"Shoter"` |
|---|---|---|---|
| **CSS classMap key** | `name.toLowerCase().replace(/\s+/g, '-')` | `'node-manager'` | `'shoter'` |
| **Sidebar visual resolver** | Uses the SAME normalized form as the classMap via `getAgentTypeClass()` / `applyAgentToolIconStyle()` | `'node-manager'` | `'shoter'` |
| **Connection handlers** (`agentName.toLowerCase()`) | `name.toLowerCase()` (preserves spaces) | `'node manager'` | `'shoter'` |

**For single-word agents** (e.g., `"Shoter"`, `"Emailer"`), all 3 forms are identical: `'shoter'`.

**For multi-word agents** (e.g., `"Node Manager"`, `"Gateway Relayer"`), the forms DIFFER:
- classMap key and sidebar visual resolver use **hyphens**: `'node-manager'`
- connection handlers use **spaces**: `'node manager'`

> **WHY THIS MATTERS**: `applyAgentTypeClass()` and the shared sidebar visual helper normalize with `replace(/\s+/g, '-')` before looking up the classMap. Connection code still keeps spaces via `agentName.toLowerCase()`. If you mix these forms, the canvas may render but the sidebar icon may be wrong, or the connections may stop auto-configuring.

### Sidebar Color Rule — NEVER Duplicate Gradients In JavaScript

The sidebar icon color is **NOT** a second palette definition. It must be resolved from the canvas CSS through the shared helper in `acp-canvas-core.js`.

Do this:

```javascript
const iconDiv = document.createElement('div');
iconDiv.classList.add('agent-tool-icon');
applyAgentToolIconStyle(iconDiv, description);
```

Do **NOT** do this:

```javascript
else if (lowerDesc === 'node manager' || lowerDesc === 'node-manager') iconDiv.style.background = 'linear-gradient(...)';
```

If you type a gradient string directly inside `populateAgentsList()` for a specific agent, you are reintroducing the bug this skill is trying to prevent.

---

## Step 4 · Frontend: CSS Styling and Color Gradient

Edit `agent/static/agent/css/agentic_control_panel.css` and add gradient rules.

### 4a. Choose a UNIQUE 4-color gradient

Every new agent MUST use a **4-color gradient** (`0%, 33%, 66%, 100%`) that is visually distinct from ALL existing agents. Before choosing colors, review the existing gradients in `agent/static/agent/css/agentic_control_panel.css` to avoid collisions. The sidebar icon will inherit this same style automatically through the shared helper in `acp-canvas-core.js`.

**Existing 4-color gradients (DO NOT reuse these color families):**
- Gatewayer: `#FF006E → #8338EC → #3A86FF → #00F5D4` (Pink → Purple → Blue → Cyan)
- Gateway Relayer: `#264653 → #2A9D8F → #E9C46A → #E76F51` (Dark Teal → Teal → Gold → Orange)
- Node Manager: `#0D4F4F → #00ACC1 → #76FF03 → #FFB300` (Dark Teal → Cyan → Lime → Amber)

**Existing 3-color gradients:**
- FlowHypervisor: `#FFD600 → #E91E63 → #00BCD4` (Yellow → Magenta → Cyan)
- FlowCreator: `#1565C0 → #C62828 → #2E7D32` (Blue → Red → Green)
- Mouser: `#FF1744 → #651FFF → #00E676` (Red → Purple → Green)
- File Interpreter: `#FF9A00 → #1B1464 → #00FFC8` (Orange → Navy → Mint)
- Image Interpreter: `#C2185B → #FFC107 → #009688` (Crimson → Amber → Teal)

Pick 4 colors that form a visually pleasing gradient across distinct hue ranges. The hover state should use **lighter/brighter** versions of the same 4 colors.

### 4b. Add the CSS rules

Use the CSS class name from the classMap value (typically `<agent_name_no_spaces>-agent`):

```css
/* <AgentName> Agent */
.canvas-item.<css_class_name> {
    background-color: #<color1>;
    background: linear-gradient(135deg, #<color1> 0%, #<color2> 33%, #<color3> 66%, #<color4> 100%);
    color: white;
    font-size: smaller;
}
.canvas-item.<css_class_name>:hover {
    background: linear-gradient(135deg, #<color1_light> 0%, #<color2_light> 33%, #<color3_light> 66%, #<color4_light> 100%);
    box-shadow: 0 6px 15px rgba(<r>, <g>, <b>, 0.5);
}
```

**Example for a multi-word agent "Node Manager" (CSS class `nodemanager-agent`):**
```css
/* NodeManager Agent */
.canvas-item.nodemanager-agent {
    background-color: #0D4F4F;
    background: linear-gradient(135deg, #0D4F4F 0%, #00ACC1 33%, #76FF03 66%, #FFB300 100%);
    color: white;
    font-size: smaller;
}
.canvas-item.nodemanager-agent:hover {
    background: linear-gradient(135deg, #15696A 0%, #26C6DA 33%, #9EFF5A 66%, #FFC93C 100%);
    box-shadow: 0 6px 15px rgba(0, 172, 193, 0.5);
}
```

### 4c. Verify visual parity

The gradient must exist in **one place only**: the CSS rule for `.canvas-item.<css_class_name>`.

The sidebar icon must be resolved automatically from that canvas class through `applyAgentToolIconStyle()`. There must be **no second hard-coded gradient string** for that agent inside `populateAgentsList()`.

Manual verification is REQUIRED after implementation:
- confirm the agent icon in the left Agents sidebar matches the deployed canvas node
- confirm the match holds for both newly dragged nodes and loaded `.flw` diagrams

---

## Step 5 · Frontend: JavaScript Integration

You must edit **4 JavaScript files**. The most error-prone parts are **getting the agent name form right** and **preserving sidebar/canvas visual parity**. Refer to the Naming Convention table above for EVERY code snippet below.

### 5a. `acp-agent-connectors.js` — Add fetch connector function

Add this function (follow the exact pattern from `updateShoterConnection`):

```javascript
async function update<AgentName>Connection(agentId, targetAgentId, action, type = 'target') {
    try {
        const response = await fetch(`/agent/update_<agent_name>_connection/${agentId}/`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', ...getHeaders() },
            credentials: 'same-origin',
            body: JSON.stringify({ target_agent: targetAgentId, action: action, type: type })
        });
        if (response.ok) {
            const result = await response.json();
            console.log(`--- <AgentName> ${agentId} config updated:`, result.message);
        } else {
            console.error(`--- Failed to update <AgentName> ${agentId}:`, response.statusText);
        }
    } catch (error) {
        console.error(`--- Error updating <AgentName> ${agentId}:`, error);
    }
}
```

### 5b. `acp-canvas-core.js` — Register agent in 6 places

**Location 1: `applyAgentTypeClass()` classMap** (~line 32)

Add entry to the `classMap` object. The KEY must use the **hyphenated form** (how `replace(/\s+/g, '-')` normalizes the name):
```javascript
// Single-word example:
'shoter': 'shoter-agent',
// Multi-word example (KEY is hyphenated, VALUE is the CSS class):
'node-manager': 'nodemanager-agent',
```

**Location 2: `AGENTS_NEVER_START_OTHERS` array** (~line 94)
If the agent does NOT start downstream agents, add the **hyphenated form** to this array.

**Location 3: `populateAgentsList()` visual parity rule** (~line 830)

Do **NOT** add a new per-agent `else if` gradient branch here.

The sidebar icon must keep using the shared helper so it inherits the computed background from the same CSS class used by the canvas node:

```javascript
const iconDiv = document.createElement('div');
iconDiv.classList.add('agent-tool-icon');
applyAgentToolIconStyle(iconDiv, description);
```

> **CRITICAL**: `agentic_control_panel.css` is the single source of truth for agent colors. `populateAgentsList()` must never become a second palette registry.

**Location 4: `removeConnection()` function** (~line 600)

Add connection removal handlers. Use the **spaced lowercase form** (how `agentName.toLowerCase()` works):
```javascript
// Single-word:
if (targetAgentName.toLowerCase() === 'shoter') update...
// Multi-word — use SPACES, not hyphens:
if (targetAgentName.toLowerCase() === 'node manager') updateNodeManagerConnection(targetId, sourceId, 'remove', 'source');
if (sourceAgentName.toLowerCase() === 'node manager') updateNodeManagerConnection(sourceId, targetId, 'remove', 'target');
```

**Location 5: `removeConnectionsFor()` function** (~line 740)

Same as Location 4, but with the deletion guards. Use **spaced lowercase form**:
```javascript
if (targetAgentName.toLowerCase() === 'node manager' && !targetBeingDeleted) updateNodeManagerConnection(targetId, sourceId, 'remove', 'source');
if (sourceAgentName.toLowerCase() === 'node manager' && !sourceBeingDeleted) updateNodeManagerConnection(sourceId, targetId, 'remove', 'target');
```

**Location 6: `mouseup` event handler (connection finalize)** (~line 1200)

Add connection creation handlers. Use **spaced lowercase form**:
```javascript
if (targetAgentName.toLowerCase() === 'node manager') updateNodeManagerConnection(targetId, sourceId, 'add', 'source');
if (sourceAgentName.toLowerCase() === 'node manager') updateNodeManagerConnection(sourceId, targetId, 'add', 'target');
```

### 5c. `acp-canvas-undo.js` — Add undo/redo handlers

Search for existing agent patterns (e.g., `updateGatewayRelayerConnection`) in this file. Add matching lines for your new agent in BOTH the undo and redo sections. Use the **spaced lowercase form** for name comparisons:
```javascript
// In redo section (removeConnection undo):
if (targetAgentName.toLowerCase() === 'node manager') {
    await updateNodeManagerConnection(targetId, sourceId, 'remove', 'source');
}
if (sourceAgentName.toLowerCase() === 'node manager') {
    await updateNodeManagerConnection(sourceId, targetId, 'remove', 'target');
}

// In undo section (recreateConnection):
if (targetAgentName === 'node manager') {
    await updateNodeManagerConnection(targetId, sourceId, 'add', 'source');
}
if (sourceAgentName === 'node manager') {
    await updateNodeManagerConnection(sourceId, targetId, 'add', 'target');
}
```

### 5d. `acp-file-io.js` — Add `.flw` file load handler

In the `restoreAgentConnection` function's switch statements that restore connections, add cases using the **spaced lowercase form** (since `sourceAgentName` = `dataset.agentName.toLowerCase()`):
```javascript
// In the SOURCE-SIDE switch:
case 'node manager': await updateNodeManagerConnection(sourceId, targetId, 'add', 'target'); break;

// In the TARGET-SIDE switch:
case 'node manager': await updateNodeManagerConnection(targetId, sourceId, 'add', 'source'); break;
```

### 5e. Verify `/* global */` declarations

At the top of `acp-canvas-core.js`, `acp-canvas-undo.js`, and `acp-file-io.js`, there is a `/* global ... */` comment that declares imported functions. Add `update<AgentName>Connection` to each of these declarations so the linter knows the function exists.

---

## Step 6 · Documentation: Update `agentic_skill.md`

Edit `agent/agents/flowcreator/agentic_skill.md` to register the new agent so the FlowCreator AI can use it in generated flows.

Add a new numbered section in the **Available Agents** list following the exact format:

```markdown
### <N>. <AgentName>
- **Purpose**: <Clear one-line description of what the agent does>.
- **Pool name pattern**: `<agent_name>_<n>`
- **Starts other agents**: YES/NO
- **Config parameters**:
  - `<param1>`: <default> (<description>)
  - `source_agents`: [] (upstream agents — for canvas connection tracking)
  - `target_agents`: [] (downstream agents to start after execution)
```

Also update these sections if applicable:
- **Connection Rules** — if the agent has special connection behavior
- **Agent Categories** — add to Active or Terminal/Monitoring list
- **Rules** in Output Format — if special handling needed

---

## Step 7 · Documentation: Update `README.md`

After creating the agent, update `README.md` in the project root with these changes:

### 7a. Update agent count
Search for the current agent count (e.g., "30 pre-built agent types") and increment it by 1. This appears in 3 places:
- **Overview** section (~line 65)
- **Key Features > Visual Workflow Designer** section (~line 157)
- **Workflow Agents** header (~line 963)

### 7b. Add to Project Structure tree
Add the new agent directory in the `agents/` section of the project structure:
```
│   │   │   ├── <agent_name>/          # <brief description>
```

### 7c. Add to agent classification
In the **Agent Architecture** section, add the agent name to either:
- **Deterministic** list (if no LLM)
- **LLM-powered** list (if uses LLM)

### 7d. Add to Workflow Agents table
Add a row to the appropriate category table (Control, Monitoring, Notification, Action, Logic Gates, Routing, or Utility):
```markdown
| **<agent_name>** | <Description> | `<key_config>`: value<br>`target_agents`: Downstream agents |
```

> **CRITICAL: ACP Description + Tooltip integration**
> The ACP now exposes the same agent description in two UI surfaces:
> - the canvas contextual menu action `Description`
> - the hover tooltip shown in the left **Agents** sidebar for each `.agent-tool-item`
>
> Both texts are resolved automatically from the **`Purpose` column of this README table row**. That means:
> - The `Purpose` sentence you write here is the exact user-facing description shown in both the canvas dialog and the sidebar tooltip.
> - Keep it concise, accurate, and aligned with the real runtime behavior of the agent.
> - Do **not** skip this row: if the row is missing, both the `Description` dialog and the sidebar tooltip will be empty/fallback-only for that agent.
> - Use the normal agent identifier in the first column (`<agent_name>` with underscores if the folder uses underscores). The UI lookup normalizes case, spaces, hyphens, and underscores automatically.

### 7e. Add to Glossary
Add a row to the Glossary table:
```markdown
| **<AgentName>** | <One-line definition of the agent> |
```

### 7f. Add to Changelog
Add an entry at the top of the **Recent Updates** section:
```markdown
- **Added <AgentName> Agent** - <Brief description of capabilities>
```

### 7g. Update Connection Endpoints table
Add a row to the **Connection Updates** API table:
```markdown
| `/update_<agent_name>_connection/<agent_name>/` | POST | Update <agent_name> connections |
```

---

## Step 7.5 · OPTIONAL: Register as a Wrapped Chat-Agent Tool (LLM-callable)

Skip this step if the agent is **only** used from the Agentic Control Panel canvas. Do this step if the Multi-Turn LLM should be able to **launch your agent as a sub-process tool** during a chat conversation (e.g., "Hey Tlamatini, SSH into 10.0.0.1 and check uptime").

Edit `agent/chat_agent_registry.py` and append a new `ChatWrappedAgentSpec(...)` entry to `WRAPPED_CHAT_AGENT_SPECS`. Example:

```python
ChatWrappedAgentSpec(
    key="myagent",                                 # short identifier
    template_dir="myagent",                        # MUST match agent/agents/<dir> folder
    tool_name="chat_agent_myagent",                # MUST start with "chat_agent_"
    tool_description="Chat-Agent-MyAgent",
    display_name="MyAgent",                        # MUST match the DB agentDescription
    purpose="Do the thing the agent does. Use when the user asks about X.",
    example_request="Run MyAgent with param1='value', param2='value2'",
    aliases=("myagent", "my agent", "friendly name"),
    security_hints=("myagent", "the keyword", "alternate phrasing"),
    # poll_window_seconds=3,                       # optional, default 8
    # long_running=True,                           # optional, for watch-loop agents
),
```

The unified agent picks this up automatically via `WRAPPED_CHAT_AGENT_BY_TOOL_NAME` — no further wiring is needed inside `mcp_agent.py` or `tools.py`. The LLM will see your tool in the bound-tools list and can invoke it with a free-form `request` string that your template agent's `config.yaml` fields will absorb through the Parametrizer-style key=value syntax.

**Verification:** `get_mcp_tools()` returns one `Tool.from_function(..., name="chat_agent_myagent", ...)` wrapper. Launching creates an isolated pool runtime copy; the tool returns a JSON string with `run_id`, `status`, `log_excerpt`, `runtime_dir`, `log_path`.

---

## Step 7.6 · REQUIRED for state-changing agents: Register in the Exec Report

If the new agent **changes system state** (runs commands, mutates files/databases/containers/clusters, sends external messages, etc.), it MUST appear in the Exec Report tables that are appended to the final multi-turn answer when the user toggles "Exec Report" on.

Read the "Exec Report" section of `CLAUDE.md` for background. Registration is a **three-spot edit**:

**1. `agent/mcp_agent.py` — add one line to `_EXEC_REPORT_TOOLS`:**

```python
_EXEC_REPORT_TOOLS: Dict[str, Tuple[str, str]] = {
    # ... existing entries ...
    "chat_agent_myagent":   ("myagent",   "MyAgent"),
}
```

The tuple is `(agent_key, agent_display)`:
- `agent_key` — lowercase, no spaces, MUST match the canvas-item CSS class you chose in Step 4 (e.g., `nodemanager`, `gateway-relayer`, `filecreator`). This keys all the Exec Report CSS rules below.
- `agent_display` — exactly the caption text ("List of <Display> Operations"). Typically the DB `agentDescription`.

If the agent has BOTH a direct @tool call AND a wrapped chat-agent launch, list both tool names mapping to the **same** `agent_key` so their rows merge into one table.

**2. `agent/static/agent/css/agent_page.css` — add two CSS rules:**

```css
.exec-report-caption-<agent_key> {
    background: linear-gradient(135deg, #<color1> 0%, #<color2> 100%);  /* mirror the canvas gradient */
    color: #ffffff;  /* or #1b1b1b for light backgrounds */
}

.exec-report-<agent_key> .exec-report-cmd {
    border-left: 3px solid #<primary-color>;
}
```

Copy the gradient colors from your Step 4b `.canvas-item.<css_class>-agent` rule so the Exec Report table feels like an extension of the agent's canvas tile.

**3. If the caption background is dark, add the agent_key to the dark-header selector list** in the same CSS file (the rule that sets `color: #f5f5f5; background: rgba(0, 0, 0, 0.55)` for `thead th`). Skip this if your caption is a light/pastel gradient.

**Verification:** `python manage.py test agent.tests.ExecReportCaptureTests` covers capture + grouping + render-order + flag-gating generically, so **no per-agent test is needed**. Run a Multi-Turn with Exec Report ticked that fires the new agent, and confirm a "List of <Display> Operations" table appears in the browser.

**Skip this step** for read-only / monitoring agents (Crawler, Summarizer, Prompter, File-Interpreter, File-Extractor, Image-Interpreter, Shoter, Monitor-Log, Monitor-Netstat, Recmailer, FlowHypervisor, TelegramRX). They never enter the Exec Report, by design.

---

## Step 7.7 · REQUIRED if LLM-callable: Flow-Generator Mapping

If you did Step 7.5 (wrapped chat-agent tool), you must also teach the **"Create Flow" button** how to turn a successful multi-turn call on your agent into a well-formed node in the downloaded `.flw` file.

Edit `agent/static/agent/js/agent_page_chat.js` — find `_mapToolArgsToAgentConfig(canonicalName, rawArgs, _toolName)` and add a new branch:

```javascript
// ── MyAgent ──────────────────────────────────────────────────────
// Template fields: param1, param2, nested.field
} else if (lower === 'myagent') {
    set('param1', pairs.param1);
    set('param2', pairs.param2 || pairs.alt_name);
    const nested = collectDotted('nested');
    if (Object.keys(nested).length > 0) config.nested = nested;
```

Rules:
- Use the `set(key, value)` helper (defined at the top of the function). It **refuses** to write empty strings, which protects the template's default values from being overwritten by the backend's deep-merge.
- Field names MUST match the `config.yaml` keys of your template agent EXACTLY. Mismatch = backend deep-merges an unknown key, template default survives, and the runtime uses the default instead of the LLM's intent.
- For dotted nested keys (`smtp.host=...`), use `collectDotted('smtp')`.
- Never set `config.target_agents` / `config.source_agents` here — those are set by `_generateAndDownloadFlow` with cardinal-suffixed pool names (`myagent_1`, `myagent_2`, ...).

Test: drag the agent onto the canvas once in the ACP, open its config dialog, note the exact field names; they MUST appear verbatim in your mapping branch.

---

## Step 8 · Quality: Lint and Fix All Modified Files

After completing all previous steps, run the linting tools to ensure code quality.

### 8a. Python linting with Ruff

Run the Ruff linter against the project:

```bash
python -m ruff check
```

Review the output and **fix all reported issues** (unused imports, formatting errors, style violations, etc.). Re-run the command until no issues remain.

### 8b. JavaScript/CSS linting with ESLint

Run the JavaScript/CSS linter:

```bash
npm run lint
```

Review the output and **fix only the errors** (ignore warnings). Re-run the command until no errors remain.

---

## Summary Checklist

```
[ ] Step 1: Create agent/agents/<agent_name>/<agent_name>.py and config.yaml
    [ ] Add _IS_REANIMATED detection before logging setup
    [ ] Add reanimation marker log in main() after write_pid_file()
    [ ] If agent polls source logs: implement reanim offset save/load
    [ ] If agent produces structured output for Parametrizer:
        [ ] Emit INI_SECTION_<AGENT_TYPE><<< ... >>>END_SECTION_<AGENT_TYPE> sections
        [ ] Use a SINGLE atomic logging.info() call per section (NEVER split)
        [ ] Register base name in SECTION_AGENT_TYPES (parametrizer.py)
        [ ] Register field list in PARAMETRIZER_SOURCE_OUTPUT_FIELDS (views.py)
        [ ] Add row to Supported Source Agents table (README.md)
[ ] Step 2: Add update_<agent_name>_connection_view in views.py + URL in urls.py
[ ] Step 3: Create database migration and run `python manage.py migrate`
    [ ] Decide: is agentDescription single-word (e.g., "Shoter") or multi-word (e.g., "Node Manager")?
    [ ] This choice determines ALL naming forms — see Naming Convention section
[ ] Step 4: CSS gradient styling in agentic_control_panel.css
    [ ] 4a: Choose a UNIQUE 4-color gradient (0%, 33%, 66%, 100%) — check existing gradients first!
    [ ] 4b: Add .canvas-item.<css_class>-agent rules (normal + hover)
    [ ] 4c: VERIFY: the gradient exists only in CSS and the sidebar icon inherits it from `applyAgentToolIconStyle()`
[ ] Step 5: JavaScript integration (USE CORRECT NAME FORM FOR EACH CONTEXT!):
    [ ] 5a: Add fetch connector in acp-agent-connectors.js
    [ ] 5b-1: classMap key in acp-canvas-core.js → HYPHENATED form (e.g., 'node-manager')
    [ ] 5b-2: AGENTS_NEVER_START_OTHERS → HYPHENATED form (if applicable)
    [ ] 5b-3: Sidebar icon visual parity → keep `applyAgentToolIconStyle(iconDiv, description)` and do NOT add a new hard-coded gradient branch
    [ ] 5b-4: removeConnection() → SPACED form (e.g., 'node manager')
    [ ] 5b-5: removeConnectionsFor() → SPACED form with deletion guards
    [ ] 5b-6: mouseup handler → SPACED form
    [ ] 5c: Undo/redo in acp-canvas-undo.js → SPACED form
    [ ] 5d: .flw load cases in acp-file-io.js → SPACED form (BOTH source + target switch)
    [ ] 5e: /* global */ declarations updated in all 3 JS files
[ ] Step 6: Add agent entry in agentic_skill.md (for FlowCreator AI)
[ ] Step 7: Update README.md (count, structure, tables, glossary, changelog, API)
    [ ] 7d: Workflow Agents table row added with the final `Purpose` text that both the ACP `Description` menu and the sidebar tooltip will display
[ ] Step 7.5: OPTIONAL — if LLM should be able to launch this agent during Multi-Turn chat:
    [ ] Add ChatWrappedAgentSpec entry to WRAPPED_CHAT_AGENT_SPECS in chat_agent_registry.py
    [ ] tool_name MUST start with "chat_agent_"
    [ ] display_name MUST match the DB agentDescription
    [ ] Provide a good example_request — the LLM reads this to format its call
[ ] Step 7.6: REQUIRED if agent changes system state (filesystem, DB, remote host, container, cluster,
    repo, GUI, external messages):
    [ ] Add tool_name → (agent_key, agent_display) entry to _EXEC_REPORT_TOOLS in mcp_agent.py
    [ ] Add .exec-report-caption-<agent_key> CSS rule mirroring the canvas-item gradient
    [ ] Add .exec-report-<agent_key> .exec-report-cmd { border-left: ... } accent rule
    [ ] If caption is dark, add agent_key to the dark-header thead th selector list
    [ ] SKIP for read-only / monitoring agents
[ ] Step 7.7: REQUIRED if Step 7.5 done — Flow-Generator mapping:
    [ ] Add agent-specific branch in _mapToolArgsToAgentConfig (agent_page_chat.js)
    [ ] Use the set(key, value) helper — never write empty strings
    [ ] Field names MUST match the template's config.yaml keys EXACTLY
    [ ] Never set target_agents / source_agents inside the branch
[ ] Step 8: Lint and fix:
    [ ] 8a: Run `python -m ruff check` and fix all issues
    [ ] 8b: Run `npm run lint` and fix only errors
    [ ] 8c: Manual ACP check: sidebar icon color matches the deployed canvas node color for the new agent
```
