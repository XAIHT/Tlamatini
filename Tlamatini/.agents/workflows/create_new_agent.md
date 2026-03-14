---
description: How to create a new Tlamatini agent
---

# Creating a New Agent in Tlamatini

This is a step-by-step guide for creating a new workflow agent. Follow ALL 8 steps in order. Each step includes exact code templates — adapt them by replacing `<agent_name>` (lowercase, underscore-separated, e.g. `shoter`) and `<AgentName>` (PascalCase, e.g. `Shoter`) with your agent's name.

> **Reference implementations**: Study these files before starting:
> - Simple agent with outputs: `agent/agents/shoter/shoter.py` + `config.yaml`
> - Agent with source monitoring: `agent/agents/telegramer/telegramer.py` + `config.yaml`
> - Agent with NO downstream: `agent/agents/emailer/emailer.py` + `config.yaml`

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
- The **Ender** agent is special: it uses `target_agents: []` (agents to KILL), `output_agents: []` (Cleaners to launch after killing), and `source_agents: []` (graphical input connections only — never killed, never started)
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
#           get_agent_script_path, start_agent, write_pid_file, remove_pid_file
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
- Copy ALL helper functions (`get_python_command`, `get_agent_env`, `get_pool_path`, etc.) exactly from `shoter.py`

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

**Important:** The `agentDescription` field value (e.g., `'Shoter'`) is what the frontend uses as the agent's display name and CSS class name. It MUST match exactly (case-sensitive) in all places.

After creating the migration, run:
```bash
python Tlamatini/manage.py migrate
```

---

## Step 4 · Frontend: CSS Styling

Edit `agent/static/agent/css/agentic_control_panel.css` and add these CSS rules:

```css
/* <AgentName> Agent */
.canvas-item.<agent_name>-agent {
    background-color: #<base_color>;
    background: linear-gradient(135deg, #<color1> 0%, #<color2> 100%);
    color: white;
}
.canvas-item.<agent_name>-agent:hover {
    background: linear-gradient(135deg, #<lighter1> 0%, #<lighter2> 100%);
    box-shadow: 0 6px 15px rgba(<r>, <g>, <b>, 0.5);
}
```

The user will specify the desired gradient colors. Choose complementary colors that look premium.

---

## Step 5 · Frontend: JavaScript Integration

You must edit **4 JavaScript files**. Here are the exact locations and patterns:

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

### 5b. `acp-canvas-core.js` — Register agent in 4 places

**Location 1: `applyAgentTypeClass()` classMap** (~line 32)
Add entry to the `classMap` object:
```javascript
'<agent_name>': '<agent_name>-agent',
```

**Location 2: `AGENTS_NEVER_START_OTHERS` array** (~line 94)
If the agent does NOT start downstream agents, add `'<agent_name>'` to this array. If it DOES start downstream agents, do NOT add it.

**Location 3: `populateAgentsList()` icon color** (~line 684)
Add an `else if` line to set the sidebar icon color:
```javascript
else if (lowerDesc === '<agent_name>') iconDiv.style.background = 'linear-gradient(135deg, #<color1> 0%, #<color2> 100%)';
```

**Location 4: `removeConnection()` function** (~line 517)
Add connection removal handlers. For a standard agent with source+target:
```javascript
if (targetAgentName.toLowerCase() === '<agent_name>') update<AgentName>Connection(targetId, sourceId, 'remove', 'source');
if (sourceAgentName.toLowerCase() === '<agent_name>') update<AgentName>Connection(sourceId, targetId, 'remove', 'target');
```

**Location 5: `removeConnectionsFor()` function** (~line 580)
Add the same lines but with the `!targetBeingDeleted` / `!sourceBeingDeleted` guards:
```javascript
if (targetAgentName.toLowerCase() === '<agent_name>' && !targetBeingDeleted) update<AgentName>Connection(targetId, sourceId, 'remove', 'source');
if (sourceAgentName.toLowerCase() === '<agent_name>' && !sourceBeingDeleted) update<AgentName>Connection(sourceId, targetId, 'remove', 'target');
```

**Location 6: `mouseup` event handler (connection finalize)** (~line 930)
Add connection creation handlers in the `// Auto-configure all agent types` section:
```javascript
if (targetAgentName.toLowerCase() === '<agent_name>') update<AgentName>Connection(targetId, sourceId, 'add', 'source');
if (sourceAgentName.toLowerCase() === '<agent_name>') update<AgentName>Connection(sourceId, targetId, 'add', 'target');
```

### 5c. `acp-canvas-undo.js` — Add undo/redo handlers

Search for existing agent patterns (e.g., `updateShoterConnection`) in this file and add matching lines for your new agent in both the undo and redo sections.

### 5d. `acp-file-io.js` — Add `.flw` file load handler

In the `loadDiagram` function's switch statement that restores connections, add:
```javascript
case '<agent_name>': await update<AgentName>Connection(sourceId, targetId, 'add'); break;
```

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
[ ] Step 2: Add update_<agent_name>_connection_view in views.py + URL in urls.py
[ ] Step 3: Create database migration and run `python manage.py migrate`
[ ] Step 4: Add CSS classes in agentic_control_panel.css
[ ] Step 5: JavaScript integration:
    [ ] 5a: Add fetch connector in acp-agent-connectors.js
    [ ] 5b: Register in acp-canvas-core.js (classMap, NEVER_START array, icon color, removeConnection, removeConnectionsFor, mouseup)
    [ ] 5c: Add undo/redo handlers in acp-canvas-undo.js
    [ ] 5d: Add .flw load case in acp-file-io.js
[ ] Step 6: Add agent entry in agentic_skill.md (for FlowCreator AI)
[ ] Step 7: Update README.md (count, structure, tables, glossary, changelog, API)
[ ] Step 8: Lint and fix:
    [ ] 8a: Run `python -m ruff check` and fix all issues
    [ ] 8b: Run `npm run lint` and fix only errors
```