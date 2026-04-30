---
name: tlamatini-flow-from-objective
description: Turn a one-sentence objective into a downloadable .flw workflow that wires the right Tlamatini visual agents and connections.
metadata:
  openclaw:
    emoji: "🌊"
  tlamatini:
    runtime: in-process
    requires_tools: ["chat_agent_file_creator"]
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

Author a `.flw` JSON for the user's stated objective.

## Design rules (enforced by FlowCreator)

- Minimize agents. Choose the shortest sequence that accomplishes the goal.
- Prefer sequential chains over parallel fan-out unless the objective is
  explicitly parallel.
- Starter starts only the first agent; never start Emailer / Notifier from
  Starter.
- Terminal agents (Emailer, Notifier, Whatsapper, RecMailer, TelegramRX,
  Monitor-*) always sit at the END.
- Use Raisers for exception branches; do not create Raisers for both sides
  of binary checks.
- Parametrizer is a strict single-lane queue: one source -> one target.

## Procedure

1. Inspect agent names in `Tlamatini/agent/agents/` to know the available
   visual agents.
2. Compose the workflow as a list of nodes (agent type, label, position)
   and edges (`target_agents`, optionally `source_agents`).
3. Emit `.flw` JSON matching the existing format (see `acp-file-io.js`):
   ```json
   {
     "version": 1,
     "agents": [{"id":1,"type":"starter","name":"Starter","x":..., "y":..., "config":{}}, ...],
     "connections": [{"from":1,"to":2,"kind":"target_agents"}, ...]
   }
   ```
4. Write the file to `${input.out_path}`.
5. Return `{ flw_path, agent_count, connection_count }`.
