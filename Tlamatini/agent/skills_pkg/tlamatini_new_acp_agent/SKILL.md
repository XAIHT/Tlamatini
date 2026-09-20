---
name: tlamatini-new-acp-agent
description: Scaffold a new Tlamatini visual agent end-to-end across the 8 places the agent contract requires (script + config.yaml, view + url, migration, CSS gradient, 4 JS files, agentic_skill.md, README.md, lint).
metadata:
  openclaw:
    emoji: "🧱"
  tlamatini:
    runtime: in-process
    requires_tools: ["chat_agent_file_creator","chat_agent_executer","chat_agent_pythonxer"]
    requires_mcps: ["Files-Search"]
    budget:
      max_iterations: 30
      max_seconds: 600
      max_tokens: 80000
    permissions:
      filesystem:
        read:  ["Tlamatini/agent/**/*"]
        write:
          - "Tlamatini/agent/agents/${input.agent_name}/**/*"
          - "Tlamatini/agent/views.py"
          - "Tlamatini/agent/urls.py"
          - "Tlamatini/agent/static/agent/css/agentic_control_panel.css"
          - "Tlamatini/agent/static/agent/js/acp-*.js"
          - "Tlamatini/agent/migrations/*.py"
          - "Tlamatini/agent/agents/flowcreator/agentic_skill.md"
          - "README.md"
      shell:
        - "python -m ruff check Tlamatini/agent"
        - "npm run lint"
      network: deny
      db:      ["read", "write-via-migrations-only"]
    inputs:
      - { name: agent_name, type: string, required: true,
          description: "snake_case folder name; display name derived as title-case" }
      - { name: category,   type: enum,
          values: ["control","routing","gates","action","crypto","utility","terminal"],
          required: true }
      - { name: gradient,   type: string, required: false,
          description: "4 hex colors comma-separated (#aabbcc,...)" }
    outputs:
      - { name: files_changed, type: array, required: true }
      - { name: migration_id,  type: string, required: true }
      - { name: lint_summary,  type: string, required: true }
    triggers:
      keywords: ["new agent","add agent","scaffold agent","create acp agent"]
      file_globs: ["Tlamatini/agent/agents/**/*"]
---
<!--
═══════════════════════════════════════════════════════════════════
  ✦  T L A M A T I N I  ✦   —   "one who knows"
  Created by  Angela López Mendoza   ·   @angelahack1
  Developer · Architect · Creator of Tlamatini
  Tlamatini Author Banner — do not remove (Angela's name is kept in every build)
═══════════════════════════════════════════════════════════════════
-->

# New ACP agent

Read `Tlamatini/.agents/workflows/create_new_agent.md` first. It is the
ground truth for the 8-step contract. This skill drives that procedure
end-to-end.

## Steps

1. Validate `agent_name` is snake_case ASCII; reject collisions with
   existing agents in `Tlamatini/agent/agents/`.
2. Copy `shoter.py` boilerplate into the new directory; rename references.
   **Temp/Templates policy (2026-06-02):** if the agent creates temp files, add
   the module-top `if (os.environ.get('TLAMATINI_TEMP') or '').strip(): …
   tempfile.tempdir = …` guard (verbatim from `executer.py` — an `if`-block, not
   a `def`, so ruff E402 stays clean); if it scaffolds a project/template dir
   (firmware/engine style), default the parent to `<app>/Templates`
   (`TLAMATINI_TEMPLATES`). See `prompt.pmt` Rules 15/16 + `agent/path_guard.py`.
3. Add a Django view + URL pair for the connection-update endpoint.
4. Create the migration that seeds an `Agent` row with the display name.
5. Add the CSS gradient block in `agentic_control_panel.css` and the
   hover variant.
6. Update the four JS files: connector, classMap (6 locations), undo/redo,
   .flw load.
7. Update `agentic_skill.md` and `README.md` (agent count, table,
   classification, glossary, changelog, API table).
8. Run `python -m ruff check` and `npm run lint`. Stop on any error and
   report.

## Output

Return:
```json
{
  "files_changed": ["..."],
  "migration_id": "00NN_add_<agent_name>",
  "lint_summary": "ruff: 0 errors; eslint: 0 errors"
}
```

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
