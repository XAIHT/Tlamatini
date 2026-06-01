---
name: tlamatini-flow-from-objective
description: Turn a one-sentence objective into a downloadable .flw workflow that wires the right Tlamatini visual agents and connections.
metadata:
  openclaw:
    emoji: "🌊"
  tlamatini:
    runtime: in-process
    requires_tools: ["execute_command", "chat_agent_file_creator"]
    requires_mcps: []
    budget:
      max_iterations: 12
      max_seconds: 180
      max_tokens: 30000
    permissions:
      filesystem:
        read:  ["Tlamatini/agent/agents/**/*"]
        write: ["Tlamatini/**/*.flw"]
      shell:   []
      network: deny
      db:      deny
    inputs:
      - { name: objective, type: string, required: true,
          description: "One-sentence high-level goal" }
      - { name: out_path,  type: string, required: true,
          description: "Where to write the .flw file" }
    outputs:
      - { name: flw_path,        type: string, required: true }
      - { name: agent_count,     type: integer, required: true }
      - { name: connection_count, type: integer, required: true }
    triggers:
      keywords: ["flow from","make a flow","build a flow","scaffold flow",".flw"]
---

# Flow from objective

Produce a canvas-loadable `.flw` for the user's stated objective.

> **Superseded by the `flow-making` skill.** Prefer `flow-making`: it drives the
> FlowCreator engine (full 69-agent catalog + connection contracts) and emits a
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
