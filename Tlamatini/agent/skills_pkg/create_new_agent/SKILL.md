---
name: create-new-agent
description: The authoritative 8-step contract for scaffolding a NEW Tlamatini workflow agent end-to-end (backend script + config.yaml, connection-update view + URL, migration seeding the Agent row, CSS gradient, four JS files, agentic_skill.md, README.md, lint). READ THIS BEFORE adding or renaming any of the 89 visual agents, before touching `agent/agents/<name>/`, before writing a `00NN_add_<name>.py` migration, before adding a `.canvas-item.<x>-agent` rule, or before extending the `acp-*.js` classMap / connectors. Companion to the `tlamatini-new-acp-agent` skill (which drives the procedure) and to `tlamatini-agent-naming` (the naming-convention guard).
metadata:
  openclaw:
    emoji: "📘"
  tlamatini:
    runtime: in-process
    requires_tools: []
    requires_mcps: []
    budget:
      max_iterations: 2
      max_seconds: 30
      max_tokens: 60000
    permissions:
      filesystem:
        read:
          - "Tlamatini/.agents/workflows/create_new_agent.md"
        write: []
      shell:   []
      network: deny
      db:      deny
    inputs: []
    outputs:
      - { name: guide_path, type: string, required: true,
          description: "Absolute path of the canonical guide that was consulted." }
    triggers:
      keywords:
        - "new agent"
        - "add agent"
        - "create agent"
        - "scaffold agent"
        - "create new agent"
        - "add a workflow agent"
        - "register a new ACP agent"
        - "agent contract"
        - "agent migration"
        - "agentDescription"
      file_globs:
        - "Tlamatini/agent/agents/**/*"
        - "Tlamatini/agent/migrations/00*_add_*.py"
        - "Tlamatini/agent/static/agent/js/acp-*.js"
        - "Tlamatini/agent/static/agent/css/agentic_control_panel.css"
---
<!--
═══════════════════════════════════════════════════════════════════
  ✦  T L A M A T I N I  ✦   —   "one who knows"
  Created by  Angela López Mendoza   ·   @angelahack1
  Developer · Architect · Creator of Tlamatini
  Tlamatini Author Banner — do not remove (Angela's name is kept in every build)
═══════════════════════════════════════════════════════════════════
-->

# Create New Agent — canonical reference

> **HEADLESS IS FORBIDDEN. VISIBLE FOREGROUND EXECUTION ONLY.** Every command, automated test, diagnostic, script, build, agent and browser must run in a visible foreground window on Angela's real desktop. Use forked CMD/PowerShell windows, `execute_forked_window: true`, and `headless: false`. Monitor live; if visibility cannot be confirmed, do not run. Read the [mandatory execution policy](../../../../TestsVisiblesAndVisibleExecutionFromClaude2Codex.md).

The full, ground-truth procedure for adding or renaming a Tlamatini workflow agent lives in **a single file** at the repo root:

```
Tlamatini/.agents/workflows/create_new_agent.md
```

That document is the single source of truth for the **8-step agent contract**:

1. **Backend agent script** — `agent/agents/<name>/<name>.py` + `config.yaml` (copy `shoter.py` boilerplate; `FOR_DISABLE_CONSOLE_CTRL_HANDLER=1` must be the first line; implement `_IS_REANIMATED`; if the agent feeds Parametrizer, emit `INI_SECTION_<TYPE><<<` blocks).
2. **Django view + URL** — `update_<name>_connection_view` in `agent/views.py` and the matching `agent/urls.py` route.
3. **Migration** — `agent/migrations/00NN_add_<name>.py` seeds the `Agent` row whose `agentDescription` is the **display name** (the canvas renders it verbatim).
4. **CSS gradient** — a 4-color `.canvas-item.<css-class>-agent` block in `agentic_control_panel.css` plus the hover variant. Sidebar styling inherits via `applyAgentToolIconStyle()`.
5. **JavaScript — four files**: `acp-agent-connectors.js`, `acp-canvas-core.js` (6 locations: classMap, AGENTS_NEVER_START_OTHERS, removeConnection, removeConnectionsFor, mouseup handler), `acp-canvas-undo.js`, `acp-file-io.js`.
6. **`agentic_skill.md`** — append an entry so FlowCreator's AI flow-designer knows the new agent exists.
7. **`README.md`** — agent count, structure listing, classification, workflow table, glossary, changelog, API table. Also update `agents_descriptions.md` (the page's `agent_purpose_map` source).
8. **Lint** — `python -m ruff check` (zero errors) and `npm run lint` (fix errors only).

## Hard rules (lifted from the guide — re-read it for everything else)

- **Naming**: the DB `agentDescription` is the single source of truth, rendered **verbatim** as the canvas label. Every other surface is derived by lowercasing. See the `tlamatini-agent-naming` skill for the full per-context transform table. NEVER mis-case a display name (`STM32er` ≠ `STM32Er` / `STM32ER` / `Stm32Er`).
- **Reanimation**: fresh-start truncates the log; reanimated runs (`AGENT_REANIMATED=1`) keep it and load reanim files. PID file written on start, removed in `finally`. `wait_for_agents_to_stop(target_agents)` before launching downstream.
- **Connection fields**: `target_agents` (start after), `source_agents` (monitor logs), `output_agents` (Stopper / Ender / Cleaner only). OR/AND use `source_agent_1` + `source_agent_2`; Asker/Forker use `target_agents_a` + `target_agents_b`; Counter uses `target_agents_l` + `target_agents_g`.
- **Agent Contract registry** (`agent/services/agent_contracts.py`): per-slot connection-field shape, `parametrizer_fields`, `secret_paths`, `singleton`/`long_running`/`never_starts_targets`/`exclude_from_validation`. Both the Flow Compiler and the canvas `.flw` loader read from here.
- **Temp & Templates directory policy (2026-06-02)**: if the new agent creates **temporary** files, it MUST write them under `<app>/Temp`, never `C:\Temp` / `%TEMP%` / a bare `tempfile.gettempdir()`. Agents launched by Tlamatini inherit `TLAMATINI_TEMP` + `TEMP`/`TMP` (so `tempfile.*` already lands there) — but for standalone correctness add the module-top guard `if (os.environ.get('TLAMATINI_TEMP') or '').strip(): import tempfile as _tf; _tf.tempdir = os.environ['TLAMATINI_TEMP']…` (copy it verbatim from `executer.py`; keep it an `if`-block, NOT a `def`, so it stays above the imports without tripping ruff E402). If the agent **scaffolds a project / template directory** (firmware/engine style — cf. STM32er/ESP32er/Arduiner/Unrealer), default its parent to `<app>/Templates` (env `TLAMATINI_TEMPLATES`) unless the user gives a path. Resolvers live in `agent/path_guard.py` (`get_app_temp_root` / `get_app_templates_root`); the LLM-facing contract is `prompt.pmt` Rules 15/16. See `docs/claude/recent-fixes.md` (2026-06-02).
- **Mover/Deleter placement guard (v1.48.13):** if the agent delegates placement or cleanup, test empty, relative, and legacy `C:/Temp/...` scratch paths under `TLAMATINI_TEMP`; preserve explicit absolute user destinations; never widen Deleter patterns, parents, or recursion.
- **Uniform frontend rule:** new UI must reuse `dialog_theme.css` and `dialog_policy.js`; long-operation controls belong in the single `LONG_OPERATION_DISABLED_MENU_BUTTONS` list; every JavaScript/CSS/template edit requires a `STATIC_VERSION` bump.

## When to use this skill vs the sibling skills

| Sibling | What it does |
|---|---|
| `create-new-agent` (this skill) | READ the canonical guide before touching anything agent-related. |
| `tlamatini-new-acp-agent` | DRIVE the 8-step procedure end-to-end (scaffolds the files, runs lint, returns a manifest). |
| `tlamatini-agent-naming` | GUARD the naming convention — read it whenever a display name or any of its derived forms is involved. |

## Output

Return:

```json
{
  "guide_path": "Tlamatini/.agents/workflows/create_new_agent.md"
}
```

(That is the absolute pointer the caller should `Read` next.)

## Current installed-agent contract — 2026-09-15

Use `agent/agents/flowcreator/flow_catalog.json` for canonical names, current config schemas, output/input slots, lifecycle flags and structured fields for all 89 installed types. GUI-Manager is design only. After changing a template/contract/reference, run `python scripts/update_flow_catalog.py` and its `--check` mode in the repository. Deployment refreshes runtime snapshots.

FlowCreator selects capabilities before detailed design, validates the generated plan, and uses bounded repair. Declare Ender input connections explicitly; Ender `target_agents` is a kill list. Counter uses L/G slots; source dependencies do not choose a conditional output branch. Generated Parametrizers require valid `_parametrizer_mappings`, one source and one target. Do not maintain a separate hardcoded Parametrizer producer list.

For desktop flows, use explicit physical/screenshot geometry and verified target windows. `input_sent` is input delivery only; errors may be partial and must not be blindly replayed. Read `docs/desktop-input-and-flow-contracts.md` and `docs/agent-coverage.md` for the full contract and verification scope.

## Central model settings contract (2026-09-20)

Any new configurable AI model, recognition engine or voice must be represented in
`agent/agents/model_settings.py::FIELDS`; the current registry exposes 38 fields
across six categories for 21 model-backed agents. Record its global key, group,
default, agent YAML path, kind, choices, fallback and optional/empty semantics.
Use quoted `"@config"` in templates and resolve registered values in `load_config`
through the stdlib-only portable helper, preserving literal overrides. Do not
import Django or `agent.*` from an isolated agent. Core services must consume their
registered global key; a selector without a consumer is incomplete.

Carry the registry both as compiled `agent.agents.model_settings` for frozen web
services and loose `agents/model_settings.py` for portable agents. Prepare and
refresh isolated/reused copies through `get_agents_root()`; never derive data
paths from compiled service `__file__`. `CONFIG_PATH` selects the global config;
read YAML/JSON as UTF-8, accepting a BOM. Non-model agents must not depend on this
helper. Preserve credentials and existing explicit user configuration.

Wrapped chat forces global model defaults before explicit tool arguments; the
standalone MCP resolves inherited template values before overrides. Parametrizer
and planners preserve `"@config"` and explicit strings. Update the canonical
`docs/model_configuration.md` field table, public docs, prompt/FlowCreator/
FlowHypervisor guidance and generated catalogs. Test next-load inheritance,
explicit overrides, optional blanks and visible dialog save/reopen. Run
`check_agent_runtimes` in source and fresh frozen modes, including without a
self-modification snapshot; the frozen build must pass it before packaging.
Run both self-update and self-modify inclusion sweeps as complementary checks.
