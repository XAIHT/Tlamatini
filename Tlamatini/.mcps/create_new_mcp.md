---
description: How to add a new MCP-backed context provider or unified-agent tool to Tlamatini without confusing the transport, DB, UI, and chain layers. Use when creating or updating MCP-style capabilities, LangChain tools, or both.
---

# Create a New MCP or Tool in Tlamatini

Follow this guide when adding:

- a real MCP-style runtime service
- a context preprocessor that injects prompt context
- a LangChain `@tool` used by the unified agent
- a **Skill** (`SKILL.md` package run by `SkillHarness`)
- or a combination of those pieces

Use the word "MCP" carefully. In this codebase it can mean three different things:

1. A real runtime service such as `System-Metrics` or `Files-Search`
2. A persisted UI toggle stored in the `Mcp` database table
3. A LangChain tool returned by `agent/tools.py:get_mcp_tools()`

If you do not separate those three layers before coding, you will probably modify the wrong files.

A **Skill** is a fourth, distinct surface — it is NOT an MCP, NOT a `Tool` row, and NOT a `@tool` function. Skills are markdown packages discovered at runtime by `agent/skills/registry.py` and invoked by the LLM through the two stable tools `list_skills` / `invoke_skill`. Adding a skill is much lighter weight than adding a tool: drop a new `agent/skills_pkg/<name>/SKILL.md` file with a YAML frontmatter, and the registry picks it up on next reload. No migrations, no UI checkboxes, no chain-rebuilding wiring. Use this surface when the capability is procedural ("here is how to do X step-by-step") rather than imperative ("here is a knob that does X").

## Mandatory First Decision

Before editing anything, classify the request into exactly one of these buckets:

### `Tool only` (direct @tool)

Choose this when the model must perform an action on demand during unified-agent execution, **implemented inline in the Django process**.

Examples:

- run a command
- execute a script
- launch or stop an agent
- unzip an archive
- decompile a binary
- parametrize a template agent

### `Wrapped chat-agent tool` (LLM launches an isolated subprocess agent)

Choose this when the model must perform a **longer-running, subprocess-style action** by spawning an isolated runtime copy of an existing template agent (from `agent/agents/<name>/`) and returning a `run_id` the LLM can later poll with `chat_agent_run_status` / `chat_agent_run_log` / `chat_agent_run_stop`.

Examples:

- SSH into a remote host and run a command
- send an email via SMTP
- trigger a Jenkins job
- run a PowerShell command
- call an API
- monitor a log file or netstat continuously

This bucket is served by `ChatWrappedAgentSpec` entries in `agent/chat_agent_registry.py`. The tool name is always `chat_agent_<key>` and the tool's body is a fixed launcher (`_launch_wrapped_chat_agent` in `tools.py`) — you almost never write runner code in `tools.py` for this bucket; instead you add/modify the underlying template agent under `agent/agents/<name>/` and register its spec.

### `MCP-backed context provider only`

Choose this when the system must fetch context before the main answer chain responds.

Examples:

- system metrics
- file search context
- local service health
- inventory summary
- environment snapshot

### `Skill` (markdown-defined SKILL.md package)

Choose this when the capability is **procedural** — a documented runbook the LLM can call by name, where the body of the skill is the instruction set rather than the implementation. The LLM invokes the skill via the always-on `invoke_skill(skill_name, args_json)` tool; the body of `SKILL.md` is fed back to the LLM as the runbook to follow, and `requires_tools` in the frontmatter declares which Tlamatini tools the skill expects to call along the way.

Examples:

- `acp-router` — picks the best `agent_id` for a stated intent (claude / cursor / gemini / qwen / ...). Pure routing decision, no implementation surface.
- `summarize` — instruct the LLM how to compress a transcript, with target word counts and tone guidance.
- `setup-new-acpx-key` — multi-step procedure to inject a credential into `data.keys`, `config.json` (top-level + `acpx.agents.<id>.env`), and verify via `acp_doctor`.
- `flow-making` — turn a plain objective into a canvas-loadable `.flw` by driving the FlowCreator engine (a runbook that shells out to the skill's own `scripts/make_flow.py` via `execute_command`). A skill MAY ship helper scripts under its directory and call them.
- `tlamatini_csrf_exempt_audit` / `tlamatini_planner_trace_replay` / `tlamatini_flw_doctor` — internal audit-and-fix runbooks the LLM can invoke when working ON the Tlamatini codebase itself.
- `gmail` / `slack` / `github` / `jira` / `notion` / `todoist` / `trello` / `weather` — integration stubs that document how to call the corresponding chat.ai-style MCPs once they are connected.

A skill is implemented as a single file: `agent/skills_pkg/<skill_name>/SKILL.md`. The frontmatter is YAML and declares `name`, `description`, `metadata.tlamatini.{requires_tools,requires_mcps,budget,permissions,inputs,outputs,triggers}`. The body is the runbook the LLM follows. The registry validates against `agent/skills_pkg/_meta/schema.json` and tolerates parse failures (a bad skill is skipped with a warning, not a startup error).

### `Both`

Choose this only when the model needs both:

- pre-fetched context for reasoning
- and a separate imperative action later

Do not choose `Both` unless you can point to one concrete context payload and one concrete action tool. Most requests are only one of the four action buckets above OR an MCP context provider.

## Stop And Correct Yourself If

- You are adding a tool and you start editing `agent/mcp_system_server.py` or another runtime MCP server. You are probably on the wrong path.
- You are adding an MCP context provider and you only edited `agent/tools.py`. You are not done.
- You added a new `Mcp` database row and expected the feature to work automatically. It will not.
- You changed `agent/migrations/0002_populate_db.py` in an existing project instead of adding a new migration for new rows. That is usually the wrong migration strategy.
- You added a new tool and started editing the MCP checkbox UI. Tool UI is already dynamic in the current frontend.
- You added a new MCP context provider and skipped frontend MCP checkbox work. MCP UI is still hardcoded.

## Read These Files First

Always read these files:

- `agent/tools.py`
- `agent/rag/factory.py`
- `agent/rag/interface.py`
- `agent/consumers.py`
- `agent/models.py`
- `agent/migrations/0002_populate_db.py`
- `agent/rag/chains/basic.py`
- `agent/rag/chains/history_aware.py`
- `agent/rag/chains/unified.py`

Read these when adding an MCP-backed context provider:

- `agent/chain_system_lcel.py`
- `agent/chain_files_search_lcel.py`
- `agent/mcp_system_server.py`
- `agent/mcp_system_client.py`
- `agent/mcp_files_search_server.py`
- `agent/mcp_files_search_client.py`
- `agent/apps.py`
- `agent/management/commands/startserver.py`
- `agent/static/agent/js/agent_page_init.js`
- `agent/static/agent/js/agent_page_chat.js`
- `agent/static/agent/js/agent_page_dialogs.js`
- `agent/templates/agent/agent_page.html`

Read these when adding a direct @tool:

- `agent/mcp_agent.py` — capture point for the Exec Report (`_EXEC_REPORT_TOOLS`, `_invoke_tool`)
- `agent/static/agent/js/agent_page_init.js`
- `agent/static/agent/js/agent_page_chat.js` — Flow-Generator mapping (`_mapToolArgsToAgentConfig`)
- `agent/static/agent/js/agent_page_dialogs.js`

Read these when adding a wrapped chat-agent tool:

- `agent/chat_agent_registry.py` — the `ChatWrappedAgentSpec` dataclass and the registry
- `agent/tools.py` — `_launch_wrapped_chat_agent`, `_build_wrapped_chat_agent_tool`, the Parametrizer-style request parser
- `agent/mcp_agent.py` — `_EXEC_REPORT_TOOLS`, `_MANAGEMENT_TOOLS`, wrapped-agent dedup logic
- `agent/static/agent/js/agent_page_chat.js` — Flow-Generator mapping

## Understand The Real Layers

### Layer 1: Persisted toggles

`agent/models.py` stores:

- `Mcp` rows for MCP UI toggles
- `Tool` rows for unified-agent tool toggles

Those rows are loaded by `agent/consumers.py`, converted into status flags in `agent/rag/factory.py`, and later consumed by `agent/tools.py:get_mcp_tools()` or by the patched MCP context logic in `factory.py`.

Important:

- `Mcp` rows do not create runtime services
- `Tool` rows do not create tool code
- DB rows only provide persisted enable/disable state

### Layer 2: Runtime MCP services

Current real services are:

- `System-Metrics`
  - server: `agent/mcp_system_server.py`
  - client: `agent/mcp_system_client.py`
  - transport: WebSocket JSON
- `Files-Search`
  - server: `agent/mcp_files_search_server.py`
  - practical app-side caller: `agent/chain_files_search_lcel.py`
  - transport: gRPC

These services are started from:

- `agent/apps.py`
- `agent/management/commands/startserver.py`

### Layer 3: Context fetcher chains

The main answer chains do not call the runtime services directly. Tlamatini wraps them in sidecar chains:

- `SystemRAGChain` in `agent/chain_system_lcel.py`
- `FileSearchRAGChain` in `agent/chain_files_search_lcel.py`

These decide whether extra context is needed and return payload fragments such as `system_context` or `files_context`.

### Layer 4: Main answer chains

The main answering logic lives in:

- `agent/rag/chains/basic.py`
- `agent/rag/chains/history_aware.py`
- `agent/rag/chains/unified.py`

`agent/rag/factory.py` monkey-patches `invoke()` so these chains receive context from the sidecar fetchers before answering.

### Layer 5: Unified-agent tools

`agent/tools.py` defines local synchronous `@tool` functions such as:

- `execute_command`
- `agent_parametrizer`
- `agent_starter`
- `agent_stopper`
- `agent_stat_getter`
- `launch_view_image`
- `unzip_file`
- `decompile_java`

Those are returned by `get_mcp_tools()`.

Important:

- `get_mcp_tools()` is misnamed
- it returns LangChain tools, not runtime MCP services
- these tools matter only when unified-agent execution is enabled

## File-Scope Matrix

Use this as a hard boundary guide.

### If adding a direct @tool only

Must usually touch:

- `agent/tools.py`
- `agent/rag/factory.py`
- a new migration that seeds the `Tool` row
- `agent/mcp_agent.py` → `_EXEC_REPORT_TOOLS` (only if the tool changes system state)
- `agent/static/agent/css/agent_page.css` → exec-report CSS rules (only if state-changing)
- `agent/static/agent/js/agent_page_chat.js` → Flow-Generator mapping branch (only if the LLM uses it in Multi-Turn and the resulting `.flw` must carry the tool args)

May need to touch:

- files that define supporting helpers used by the tool

Usually must not touch:

- `agent/mcp_*_server.py`
- `agent/chain_*_lcel.py`
- MCP checkbox HTML or MCP-specific frontend logic
- `Mcp` seed rows
- `agent/chat_agent_registry.py` (that's for wrapped chat-agent tools, a different bucket)

### If adding a wrapped chat-agent tool

Must usually touch:

- `agent/chat_agent_registry.py` → append `ChatWrappedAgentSpec`
- `agent/mcp_agent.py` → `_EXEC_REPORT_TOOLS` (only if state-changing)
- `agent/static/agent/css/agent_page.css` → exec-report CSS rules (only if state-changing)
- `agent/static/agent/js/agent_page_chat.js` → Flow-Generator mapping branch

May need to touch:

- the underlying `agent/agents/<name>/` template agent if it doesn't exist yet (follow `create_new_agent.md` first in that case)

Usually must not touch:

- `agent/tools.py` (the wrapped-agent runner is already implemented)
- `agent/rag/factory.py`
- `Tool` or `Mcp` seed rows

### If adding an MCP-backed context provider only

Must usually touch:

- `agent/mcp_<name>_server.py`
- `agent/mcp_<name>_client.py` or equivalent adapter if needed
- `agent/chain_<name>_lcel.py`
- `agent/rag/factory.py`
- main chain files that must consume the new payload field
- a new migration that seeds the `Mcp` row
- MCP frontend checkbox code
- startup wiring in `agent/apps.py` and `agent/management/commands/startserver.py`

Usually must not touch:

- `agent/tools.py`
- `Tool` seed rows

### If adding both

Do both workflows on purpose. Do not blur them into one implementation.

## How Requests Really Flow

Read this sequence before touching code:

1. `AgentConsumer` loads MCP rows, tool rows, and agent rows from the database.
2. `setup_llm()` or `setup_llm_with_context()` in `agent/rag/factory.py` maps those rows into `global_state` status flags.
3. `factory.py` builds one main chain.
4. `factory.py` patches that chain's `invoke()` to optionally fetch:
   - `system_context` from `SystemRAGChain`
   - `files_context` from `FileSearchRAGChain`
5. `ask_rag()` in `agent/rag/interface.py` finally calls `rag_chain.invoke(payload)`.
6. The patched `invoke()` injects context into the payload.
7. The main chain answers.
8. Only if the unified-agent path is active does the chain call tools from `agent/tools.py`.

Memorize the boundary: context providers enrich payloads before answering; tools are actions available during unified-agent reasoning.

## Tool-Only Workflow

Follow these steps when the requested feature is an action tool and not a context provider.

### Step 1: Implement the `@tool` function in `agent/tools.py`

Match the existing patterns:

- keep the function synchronous
- return plain strings
- validate dangerous paths with `path_guard` when filesystem access is involved
- write any temp/scratch/intermediate file under `<app>/Temp` via `path_guard.get_app_temp_root()` / `resolve_temp_path(...)` — never `tempfile.gettempdir()` / `C:\Temp` / `%TEMP%` (2026-06-02 policy; the Django process already pins `tempfile.tempdir` + `TEMP`/`TMP`/`TLAMATINI_TEMP` to `<app>/Temp`)
- keep side effects explicit
- include a docstring with several call examples so the LLM can invoke it correctly

### Step 2: Resolve bundled paths for both source and frozen runs

If the tool touches bundled assets, template agents, helper executables, or sibling directories, explicitly support both modes:

- non-frozen development mode
- frozen packaged mode

Typical pattern already used in `tools.py`:

- frozen: `os.path.dirname(sys.executable)`
- source: `os.path.dirname(os.path.abspath(__file__))` or its parent

Do not hardcode only the source-tree location if the feature must also work from a packaged build.

### Step 3: Register the tool in `get_mcp_tools()`

Append the tool under a `global_state` gate.

This is a manual mapping. Treat it as fragile.

Current effective convention is:

- `tool_` + `<toolDescription>.lower()` + `_status`

But the project already contains a mismatch:

- seeded description: `Monitor-Netstat`
- checked status key: `tool_execute-netstat_status`

That mismatch proves the naming is not self-healing. Verify the actual `Tool.toolDescription`, the `factory.py` mapping, and the `get_mcp_tools()` gate all agree exactly.

### Step 4: Seed a `Tool` row with a new migration

If the tool must be toggleable in the UI, create a new migration that inserts the new `Tool` row.

Prefer a new migration over editing `0002_populate_db.py` in an existing codebase. Editing old seed migrations does not safely update already-created databases.

### Step 5: Verify whether frontend edits are actually required

For tools, the answer is usually no.

The current tool UI path is dynamic:

- `agent_page_chat.js` stores incoming tool rows
- `agent_page_init.js` emits `set-tools` based on the `tools` array
- `agent_page_dialogs.js` renders tool checkboxes dynamically
- `agent_page.html` already exposes `<ul id="tool-mcps-list"></ul>`

Therefore:

- adding a new tool usually does not require HTML changes
- adding a new tool usually does not require new JS checkbox markup
- only add frontend changes if the new tool needs custom UX beyond the normal dynamic list

### Step 6: Verify the execution scope

A new tool is only usable when the main chain is:

- `UnifiedAgentChain`
- `UnifiedAgentRAGChain`

If unified-agent mode is disabled, the tool is effectively dead code from the chat path.

## Wrapped Chat-Agent Tool Workflow

Follow these steps when the feature is an imperative action best served by **launching an isolated template-agent runtime copy**, and you want the unified agent to drive it during chat.

### Step 1: Decide whether the underlying template agent already exists

Browse `agent/agents/`. If a template agent exists that does what the user wants (SSHer, Dockerer, Apirer, Gitter, Sqler, ...), you are **configuring** that agent, not writing a new runner.

If the underlying capability is new, go through the full `create_new_agent.md` skill first to create the template agent (including `config.yaml`, migration, canvas CSS, etc.). Then come back here.

### Step 2: Append a `ChatWrappedAgentSpec` to `agent/chat_agent_registry.py`

Append a new entry to `WRAPPED_CHAT_AGENT_SPECS`:

```python
ChatWrappedAgentSpec(
    key="myagent",                           # short identifier
    template_dir="myagent",                  # MUST match agent/agents/<dir>
    tool_name="chat_agent_myagent",          # MUST start with "chat_agent_"
    tool_description="Chat-Agent-MyAgent",
    display_name="MyAgent",                  # MUST match DB agentDescription
    purpose="One-sentence description of when to use this.",
    example_request="Run MyAgent with param1='value', param2='value2'",
    aliases=("myagent", "my agent"),
    security_hints=("myagent", "keyword"),
    # poll_window_seconds=3,                 # optional
    # long_running=True,                     # optional
),
```

No further wiring is needed inside `mcp_agent.py` or `tools.py`. The registry drives `WRAPPED_CHAT_AGENT_BY_TOOL_NAME`, `get_mcp_tools()` auto-returns a `Tool.from_function(..., name=spec.tool_name, ...)` wrapper, and the unified agent picks up the tool on its next chain build.

### Step 3: Ensure the template agent accepts Parametrizer-style key=value input

The LLM will call your tool with a free-form `request` string like:

```
Run MyAgent with param1='value1', nested.param='value2'
```

`_launch_wrapped_chat_agent()` in `tools.py` parses that string into `config.yaml` overrides using the same Parametrizer grammar. Your template agent's `config.yaml` must have top-level (or dotted-nested) keys matching the names you advertise in the `example_request`, or the overrides silently fall through.

### Step 4: Register in the Exec Report if state-changing

If the action changes system state (filesystem, DB, remote host, container, cluster, repo, GUI, external messages), add a one-line entry to `_EXEC_REPORT_TOOLS` in `agent/mcp_agent.py`:

```python
_EXEC_REPORT_TOOLS: Dict[str, Tuple[str, str]] = {
    # ... existing entries ...
    "chat_agent_myagent":  ("myagent",  "MyAgent"),
}
```

Plus the two matching CSS rules in `agent/static/agent/css/agent_page.css` (caption gradient + command-cell accent). See the "Exec Report" section in `CLAUDE.md` for the full pattern.

**Skip** this step for read-only / monitoring agents (Crawler, Summarizer, Prompter, File-Interpreter, File-Extractor, Image-Interpreter, Shoter, Monitor-Log, Monitor-Netstat, Recmailer).

### Step 5: Register in the Flow-Generator mapping

Add an agent-specific branch in `_mapToolArgsToAgentConfig` (in `agent/static/agent/js/agent_page_chat.js`) that translates the LLM's raw tool-call args into your template's `config.yaml` fields. Use the `set(key, value)` helper — it refuses empty strings so template defaults stay intact. See `create_new_agent.md` Step 7.7 for the full pattern.

Without this branch, the "Create Flow" button produces a `.flw` whose node for your agent has **no config fields set**, and the runtime silently falls back to template defaults.

### Step 6: No `Tool` DB row is needed

Wrapped chat-agent tools are not managed through the `Tool` table. They are enabled whenever the unified agent is active. The `Tool` table is for the dynamic tool-toggle UI of direct @tool functions in `tools.py` — wrapped chat-agents are always-on when the unified agent runs.

### Step 7: No management-tools treatment unless it is truly management

The set `_MANAGEMENT_TOOLS` in `agent/mcp_agent.py` excludes specific tools from `.flw` generation and other UI integrations. It is for lifecycle bookkeeping (`chat_agent_run_list`, `chat_agent_run_status`, `chat_agent_run_log`, `chat_agent_run_stop`), NOT for ordinary state-changing agents. Don't add your agent here.

### Verification checklist

- `WRAPPED_CHAT_AGENT_BY_TOOL_NAME["chat_agent_myagent"]` returns the spec
- `get_mcp_tools()` includes a tool with `name == "chat_agent_myagent"`
- Launching produces a new runtime copy under `agents/pools/_chat_runs_/<key>_<N>_<id>/`
- The tool returns a JSON string with `run_id`, `status`, `log_excerpt`, `runtime_dir`, `log_path`
- If state-changing: the agent appears in the Exec Report table when Multi-Turn + Exec Report are both on
- The "Create Flow" button produces a `.flw` in which your node carries the expected `config.yaml` overrides (not empty defaults)

---

## MCP-Backed Context Provider Workflow

Follow these steps when the requested feature must enrich prompts before the main answer chain responds.

### Step 1: Create the runtime service

Create the server and any dedicated client or adapter.

Recommended layout:

- `agent/mcp_<name>_server.py`
- `agent/mcp_<name>_client.py`
- `agent/chain_<name>_lcel.py`

### Step 2: Create the sidecar context-fetch chain

Match the existing shape:

- a decision function such as `should_fetch_<name>_context(question)`
- a fetcher such as `fetch_<name>_context()`
- an orchestrator such as `intelligent_context_fetch(input_data)`

This chain is the practical bridge used by the app. Do not assume the main app will talk to the runtime client directly.

### Step 3: Start the service automatically

Wire startup into:

- `agent/apps.py`
- `agent/management/commands/startserver.py`

If you skip this, the code may look correct but the service will never be reachable in normal app startup.

### Step 4: Add config that is actually consumed

Update `agent/config.json` only for keys that your runtime path truly reads.

Do not repeat the existing `Files-Search` drift where some config values exist but the main request path ignores them.

### Step 5: Extend `agent/rag/factory.py`

Add all required wiring:

- guarded import of the sidecar chain
- sync wrapper such as `get_<name>_context_sync(payload)`
- mapping from `Mcp` row description to a `global_state` status key
- branching inside every relevant patched `invoke()` path

Current code only recognizes these MCP descriptions:

- `System-Metrics`
- `Files-Search`

Adding a new `Mcp` row without extending `factory.py` does nothing.

### Step 6: Choose a payload field and make chains consume it

Examples:

- `system_context`
- `files_context`
- `service_context`
- `inventory_context`

Then update every main chain that should consume it:

- `agent/rag/chains/basic.py`
- `agent/rag/chains/history_aware.py`
- `agent/rag/chains/unified.py`

### Step 7: Seed the `Mcp` row and wire the MCP UI

Create a new migration that inserts the `Mcp` row.

Then update the MCP checkbox path:

- `agent/templates/agent/agent_page.html`
- `agent/static/agent/js/agent_page_init.js`
- `agent/static/agent/js/agent_page_chat.js`
- `agent/static/agent/js/agent_page_dialogs.js`

Important: MCP UI is still hardcoded for two checkboxes. MCP rows are not rendered dynamically the way tool rows are.

### Step 8: Confirm persistence and reconnect behavior

`agent/consumers.py` already persists generic `Mcp` rows, but the frontend message structure around MCP toggles is still shaped around the existing hardcoded controls. Verify that enabling and disabling the new MCP survives reconnects.

### Step 9: Verify all chain modes that should see the new context

At minimum test:

- prompt-only mode
- history-aware mode
- retrieval mode
- unified-agent mode
- contextual file or directory mode if relevant

## Combined Workflow

Choose this only when both halves are real.

Use this pattern:

- sidecar MCP chain fetches summary, snapshot, or grounding context
- unified-agent tool performs mutation or targeted action later

Keep responsibilities separate. Do not try to simulate a context provider with a tool or simulate a tool by stuffing imperative instructions into a prompt context field.

## Deep Notes About `tools.py`

Remember these facts when designing a new tool:

- tools are synchronous `@tool` functions
- most tools return plain strings
- several tools validate paths through `validate_tool_path`
- `get_mcp_tools()` is the actual registration point
- the gating keys are handwritten and can drift
- packaged-path resolution is already a recurring concern

Representative implementation facts:

- the template-agent control tools resolve the template-agent directory differently depending on `sys.frozen`
- `decompile_java()` resolves `jd-cli.bat` from a packaged build or from the source tree

Use those patterns when building tools that touch bundled assets or template-agent folders.

## Current Hardcoded Assumptions You Must Not Miss

1. `factory.py` recognizes only `System-Metrics` and `Files-Search` by description.
2. The frontend MCP dialog is hardcoded for two checkboxes.
3. Tool UI is dynamic, unlike MCP UI.
4. `get_mcp_tools()` returns tools, not runtime MCP services.
5. `ask_rag()` does not fetch MCP data itself; it only calls `rag_chain.invoke(payload)`.
6. The main app path for `Files-Search` uses `FileSearchRAGChain`, not `mcp_files_search_client.py`.
7. `mcp_files_search_client_uri` exists in `config.json` but is not used by the main chain path.
8. `FileSearchRAGChain` reads `mcp_files_search_grpc_target`, but that key is not currently present in `config.json`, so the chain falls back to `localhost:50051`.
9. `mcp_files_search_server.py` currently hardcodes gRPC port and worker count instead of reading the config keys already present.
10. Tool status keys are handwritten and can drift from seeded DB descriptions.
11. `mcpContent` is stored as string text, not a boolean.
12. **Wrapped chat-agent tools are NOT in the `Tool` DB table.** They are always-on whenever the unified agent is active. The `Tool` table and its toggle UI only gate direct @tool functions defined in `tools.py`.
13. **`UnifiedAgentChain.invoke()` rebuilds the payload with a hardcoded key whitelist** (around line 138 of `rag/chains/unified.py`). Any new payload key (`multi_turn_enabled`, `exec_report_enabled`, future flags) MUST be added to that whitelist or it is silently dropped at the chain boundary. This has already caused one production bug — see the Exec Report section in `CLAUDE.md`.
14. **The Exec Report capture point in `mcp_agent.py` is `_invoke_tool()`, not the chain layer.** Capture is unconditional (ignores the per-request flag). The flag only gates rendering. This separation is deliberate to prevent whitelist-style bugs from silently hiding data again.
15. **Flow-Generator emits cardinal-suffixed pool names** (`executer_1`, `executer_2`, …) in `target_agents` / `source_agents` lists. A wrapped chat-agent tool whose Flow-Generator branch emits bare names like `"executer"` will produce a `.flw` whose Starter cannot find the agent and the chain dies on the first hop.
16. **"Ask Execs" gates EVERY tool by default — exempt only read-only/polling tools.** When the user ticks the **Ask Execs** toolbar checkbox, the Multi-Turn executor BLOCKS on a browser Proceed/Deny prompt before running each tool — and `MultiTurnToolAgentExecutor._requires_exec_permission` prompts for **every** tool that is NOT in `_MANAGEMENT_TOOLS` ∪ `_TOOL_QUOTA_EXEMPT` (in `mcp_agent.py`). So any new direct `@tool`, wrapped `chat_agent_*`, `acp_*` tool, or Skill is **automatically** prompted with no extra wiring. If your new tool is **read-only / inspection / polling** and should NOT interrupt the user with a prompt (the same role as `chat_agent_run_status` / `get_current_time` / `window_present`), add its name to `_MANAGEMENT_TOOLS` and/or `_TOOL_QUOTA_EXEMPT`. The dialog's "shell" line comes from `_infer_execution_shell(tool_name, args)` — extend it if your tool runs through an unusual shell/interpreter. See `docs/claude/multi-turn.md` → *Ask Execs* and `docs/claude/recent-fixes.md` (2026-05-29).

17. **Temp files live ONLY under `<app>/Temp`; scaffolded project dirs under `<app>/Templates` (2026-06-02 policy).** A new `@tool` / wrapped chat-agent that writes scratch must resolve it through `agent/path_guard.py` (`get_app_temp_root()` / `resolve_temp_path()`), NEVER `tempfile.gettempdir()` / `C:\Temp` / `%TEMP%`. The Django process pins `tempfile.tempdir` + `TEMP`/`TMP`/`TMPDIR`/`TLAMATINI_TEMP` to `<app>/Temp` (`manage.py` / `settings.py`) and exports `TLAMATINI_TEMPLATES` for the firmware-style agents' default scaffold parent. LLM-facing contract: `prompt.pmt` Rules 15/16 (absolute paths injected as `{temp_directory}` / `{templates_directory}` by `rag/config.py`). Full notes: `docs/claude/recent-fixes.md` (2026-06-02).

## Self-Check Before Saying It Is Done

If you added a direct @tool, verify:

- the `@tool` exists
- `get_mcp_tools()` returns it
- the status key matches the seeded `Tool` row and `factory.py` mapping
- bundled paths work in both frozen and non-frozen modes if applicable
- the tool is reachable in unified-agent mode
- if state-changing: entry in `_EXEC_REPORT_TOOLS` + matching CSS rules
- if Multi-Turn may call it: branch in `_mapToolArgsToAgentConfig`
- no unnecessary MCP server or MCP UI edits were made

If you added a wrapped chat-agent tool, verify:

- `WRAPPED_CHAT_AGENT_BY_TOOL_NAME["chat_agent_<key>"]` returns the spec
- `get_mcp_tools()` includes it (auto via registry)
- launching creates a runtime copy under `agents/pools/_chat_runs_/<key>_<N>_<id>/`
- the tool returns a JSON string with `run_id`, `status`, `log_excerpt`, `runtime_dir`, `log_path`
- the underlying `agent/agents/<name>/` template exists and accepts the advertised `example_request` fields
- if state-changing: entry in `_EXEC_REPORT_TOOLS` + matching CSS rules
- branch in `_mapToolArgsToAgentConfig` so `.flw` generation produces populated config fields
- NO new `Tool` DB row (wrapped chat-agents are always-on, not in the `Tool` toggle UI)

If you added an MCP context provider, verify:

- the runtime server exists
- startup wiring exists
- the sidecar chain exists
- `factory.py` imports and invokes it
- the payload field is consumed by the intended main chains
- the `Mcp` row exists
- the frontend MCP toggle is visible and persists
- the feature works in every intended chain mode
- **`UnifiedAgentChain.invoke()`'s payload whitelist includes any new flag** your provider reads (assumption #13)

If you added multiple buckets, verify each checklist independently.

## Skill Workflow (SKILL.md package)

Follow these steps when the requested feature is a **procedural runbook** rather than an imperative tool or context provider.

> **Dedicated guide**: `Tlamatini/.skills/create_new_skill.md` is the full, standalone authoring reference for a `SKILL.md` (the two runtimes `in-process` vs `acpx`, the frontmatter schema ranges, discovery + the 30 s staleness cache, lint/validate, ACPX-surface gotchas). The steps below are the short version. The `flow-making` skill (`agent/skills_pkg/flow_making/`) is a good worked example of an in-process skill that ships and shells out to `scripts/*.py`.

### Step 1: Decide whether a skill is the right surface

A skill is the right choice when:

- the capability is mostly *instructions* the LLM should follow, not new code that needs to run inside Tlamatini
- the capability composes existing tools (`acp_*`, `chat_agent_*`, `execute_command`, MCP fetches) into a documented sequence
- the capability is internal-tooling (audit / lint / refactor / replay) that the LLM should be able to invoke by name when asked
- you would otherwise be writing a long inline prompt every time you wanted the LLM to do this thing

A skill is NOT the right choice when:

- the capability needs new Python that the LLM cannot supply at runtime (write a `@tool` instead)
- the capability needs to spawn a long-running subprocess (write a wrapped chat-agent tool instead)
- the capability needs to inject context into the prompt before the LLM answers (write an MCP context provider instead)

### Step 2: Drop a new SKILL.md package under `agent/skills_pkg/`

Create one directory per skill:

```
agent/skills_pkg/<skill_name>/SKILL.md
```

The `<skill_name>` is the leaf directory name. The frontmatter `name` must match it (or the frontmatter wins if both are set). Use `kebab-case` for the directory and the `name` field; convert to `snake_case` only inside Python imports.

Minimal frontmatter shape (mirror an existing skill — `acp_router/SKILL.md` is the canonical example):

```yaml
---
name: my-skill
description: One-sentence purpose of this skill.
metadata:
  openclaw:
    emoji: "🛠️"
  tlamatini:
    runtime: in-process
    requires_tools: ["acp_doctor", "chat_agent_file_creator"]
    requires_mcps: []
    budget:
      max_iterations: 10
      max_seconds: 180
      max_tokens: 16000
    permissions:
      filesystem:
        read:  ["path/glob"]
        write: ["path/glob"]
      shell: []
      network: deny
      db: deny
    inputs:
      - { name: input_arg,  type: string, required: true,  description: "..." }
    outputs:
      - { name: result,     type: string, required: true }
    triggers:
      keywords:   ["...", "..."]
      file_globs: ["..."]
---

# Skill Name

The body of the skill is the runbook the LLM will follow when it calls
`invoke_skill('my-skill', {...})`. Write it like a procedure, not like documentation:

1. First do X.
2. Then do Y.
3. If Z is true, do W; else do V.
```

### Step 3: Validate against the schema

`agent/skills_pkg/_meta/schema.json` defines the frontmatter contract; `agent/skills_pkg/_meta/lint.py` is the linter the registry uses internally. The skill_creator skill ships `scripts/quick_validate.py` for ad-hoc validation:

```bash
python Tlamatini/agent/skills_pkg/skill_creator/scripts/quick_validate.py \
    Tlamatini/agent/skills_pkg/<skill_name>/SKILL.md
```

A skill that fails to parse is skipped on startup with a logger warning — it does NOT crash Django. But it also will not be invokable. Always validate before assuming the skill is registered.

### Step 4: Verify discovery and invocation

Restart Django (the registry caches discoveries with a 30-second freshness window). In the chat with **Multi-Turn + ACPX both enabled** (since `list_skills` / `invoke_skill` live on the ACPX surface), ask:

1. "List the available skills." — `list_skills` should return the new entry with the description and runtime fields.
2. "Invoke the `<skill_name>` skill with `<args>`." — the LLM picks `invoke_skill(...)`, the harness validates inputs against the frontmatter contract, runs the skill body, and returns the structured outputs.

### Step 5: NO database migration, NO frontend wiring, NO `@tool` registration

Skills are intentionally lightweight: they have no `Tool` row, no `Mcp` row, no checkbox in the UI, no entry in `chat_agent_registry.py`, no `_EXEC_REPORT_TOOLS` mapping. They are markdown packages that the LLM picks up via `list_skills` / `invoke_skill`. If you find yourself editing any of the above files, you are doing too much — back out and reconfirm whether you actually need a skill or one of the heavier surfaces.

### Step 6: Keep the skill in sync with reality

Skills are read-once at registration; the body is what the LLM follows. If the underlying tools the skill calls change shape (renamed `acp_*` tool, new required arg on `chat_agent_*`, removed MCP), update the skill body. The `tlamatini_csrf_exempt_audit` / `tlamatini_planner_trace_replay` / `tlamatini_flw_doctor` skills are particularly sensitive to this — they are runbooks against the Tlamatini codebase itself and will silently misfire if a referenced file path moves.

## Final Rule

Answer this question explicitly before coding:

"Am I adding a direct @tool, a wrapped chat-agent tool, an MCP context provider, a Skill (`SKILL.md` package), or more than one of those?"

If that answer is not written down first, the implementation will usually end up in the wrong files.
