---
name: tlamatini-flow-from-objective
description: Turn a one-sentence objective into a downloadable .flw workflow that wires the right Tlamatini visual agents and connections.
metadata:
  openclaw:
    emoji: "🌊"
  tlamatini:
    runtime: in-process
    # DIRECT + DELEGATED. This skill is a compatibility entry point that
    # hands off to `flow-making` via invoke_skill, so invoke_skill/list_skills
    # are requirements, not incidentals.
    requires_tools: ["invoke_skill", "list_skills",
                     "execute_command", "chat_agent_file_creator"]
    requires_mcps: []
    budget:
      max_iterations: 12
      max_seconds: 180
      max_tokens: 30000
    permissions:
      filesystem:
        read:  ["Tlamatini/agent/agents/**/*"]
        write: ["Tlamatini/**/*.flw"]
      # The scripted fallback really does run these; an empty list here was a
      # scope the documented procedure could not execute within.
      shell:
        - "python Tlamatini/agent/skills_pkg/flow_making/scripts/make_flow.py"
        - "python Tlamatini/agent/skills_pkg/flow_making/scripts/result_to_flw.py"
      # DOWNSTREAM: FlowCreator may call a model. This skill opens no socket.
      network: deny
      db:      deny
    inputs:
      - { name: objective, type: string, required: true,
          description: "One-sentence high-level goal" }
      - { name: out_path,  type: string, required: true,
          description: "Where to write the .flw file. With no user-given folder, default it under the Tlamatini Templates directory (TLAMATINI_TEMPLATES) — never C:\\Temp / %TEMP%." }
    outputs:
      - { name: flw_path,        type: string, required: true }
      - { name: agent_count,     type: integer, required: true }
      - { name: connection_count, type: integer, required: true }
    triggers:
      keywords: ["flow from","make a flow","build a flow","scaffold flow",".flw"]
---
<!--
═══════════════════════════════════════════════════════════════════
  ✦  T L A M A T I N I  ✦   —   "one who knows"
  Created by  Angela López Mendoza   ·   @angelahack1
  Developer · Architect · Creator of Tlamatini
  Tlamatini Author Banner — do not remove (Angela's name is kept in every build)
═══════════════════════════════════════════════════════════════════
-->

# Flow from objective

> **HEADLESS IS FORBIDDEN. VISIBLE FOREGROUND EXECUTION ONLY.** Every command, automated test, diagnostic, script, build, agent and browser must run in a visible foreground window on Angela's real desktop. Use forked CMD/PowerShell windows, `execute_forked_window: true`, and `headless: false`. Monitor live; if visibility cannot be confirmed, do not run. Read the [mandatory execution policy](../../../../TestsVisiblesAndVisibleExecutionFromClaude2Codex.md).

Produce a canvas-loadable `.flw` for the user's stated objective.

> **Superseded by the `flow-making` skill.** Prefer `flow-making`: it drives the
> FlowCreator engine (full 89-agent catalog + connection contracts) and emits a
> validated, schemaVersion-2 `.flw`. This skill is kept as an alias/entry point —
> do NOT hand-author the `.flw` JSON, because you do not carry the agent catalog
> in context and a hand-written flow hallucinates agent types and will not load.

## Procedure (delegate)

1. Invoke the `flow-making` skill with the same inputs:
   `invoke_skill('flow-making', { "objective": "${input.objective}", "out_path": "${input.out_path}" })`.
2. Return its result verbatim: `{ flw_path, agent_count, connection_count }`.

## If you must run it directly

Use the shipped driver — it copies the FlowCreator template to an isolated dir,
runs it, and writes the `.flw`:

```
python Tlamatini/agent/skills_pkg/flow_making/scripts/make_flow.py \
  --objective "${input.objective}" --out "${input.out_path}"
```

The last stdout line is `agent_count=<N> connection_count=<M> flw_path=<path>`.

## Correct `.flw` shape (schemaVersion 2)

If you ever emit `.flw` JSON by hand, it MUST match the loader contract
(`acp-file-io.js::loadDiagram` / `flow_spec.py`) — NOT a `{version, agents,
connections:[{from,to,kind}]}` shape (that is obsolete and will not load):

```json
{
  "schemaVersion": 2,
  "nodes": [
    {"id": "starter-1", "text": "Starter", "left": "50px", "top": "50px",
     "agentPurpose": "", "configData": {"target_agents": ["monitor_log_1"]}}
  ],
  "connections": [
    {"sourceIndex": 0, "targetIndex": 1, "inputSlot": 0, "outputSlot": 0}
  ],
  "artifacts": {}
}
```

See `agent/skills_pkg/flow_making/references/flw_schema.md` for the full contract.

## Current installed-agent contract — 2026-09-15

Use `agent/agents/flowcreator/flow_catalog.json` for canonical names, current config schemas, output/input slots, lifecycle flags and structured fields for all 89 installed types. GUI-Manager is design only. After changing a template/contract/reference, run `python scripts/update_flow_catalog.py` and its `--check` mode in the repository. Deployment refreshes runtime snapshots.

FlowCreator selects capabilities before detailed design, validates the generated plan, and uses bounded repair. Declare Ender input connections explicitly; Ender `target_agents` is a kill list. Counter uses L/G slots; source dependencies do not choose a conditional output branch. Generated Parametrizers require valid `_parametrizer_mappings`, one source and one target. Do not maintain a separate hardcoded Parametrizer producer list.

For desktop flows, use explicit physical/screenshot geometry and verified target windows. `input_sent` is input delivery only; errors may be partial and must not be blindly replayed. Read `docs/desktop-input-and-flow-contracts.md` and `docs/agent-coverage.md` for the full contract and verification scope.

## Model choices in generated flows

Preserve quoted `"@config"` and missing registered model fields so generated agents
follow Config → Models. Keep a literal model/engine/voice only when an explicit
override is intended; never fill inheritance with a guessed tag. The registry in
`agent/agents/model_settings.py` maps all 21 model-backed agents to 38 global
settings. Wrapped-chat globals are seeded before explicit tool arguments, so do
not manufacture model arguments when translating a request into a flow. Optional
empty Whisperer cloud model and LaTeXer repair model values have distinct meanings.
Video `analysis_type` remains a per-agent task choice; its local audio model is
separate from Whisperer's engine. See `docs/model_configuration.md` and the current
generated flow catalog for exact field paths and defaults.
