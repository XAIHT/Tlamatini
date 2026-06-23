---
name: tlamatini-flw-doctor
description: "Validate a .flw workflow file: check connection topology, terminal agents, Parametrizer single-lane queue, missing connectors, dangling target_agents."
metadata:
  openclaw:
    emoji: "🩺"
  tlamatini:
    runtime: in-process
    requires_tools: []
    requires_mcps: []
    budget:
      max_iterations: 4
      max_seconds: 30
      max_tokens: 8000
    permissions:
      filesystem:
        read:  ["**/*.flw", "Tlamatini/agent/agents/**/*"]
        write: []
      shell:   []
      network: deny
      db:      deny
    inputs:
      - { name: flw_path, type: string, required: true }
    outputs:
      - { name: ok,        type: boolean, required: true }
      - { name: problems,  type: array,   required: true }
      - { name: summary,   type: string,  required: true }
    triggers:
      keywords: [".flw doctor", "validate flow", "check flow", "lint flw"]
      file_globs: ["**/*.flw"]
---

# .flw doctor

Statically validate a .flw file.

Checks:

1. JSON parses; required keys present (`version`, `agents`, `connections`).
2. Every node's `type` is a known agent type (mirrors the agent-folder list).
3. Every connection's `from` and `to` reference real node ids.
4. No `target_agents` connection points at Stopper / Ender / Cleaner —
   those use `output_agents` per the agent contract.
5. Parametrizer nodes have at most one inbound and one outbound
   `target_agents` edge (single-lane queue invariant).
6. Terminal agents (Emailer / Notifier / RecMailer / Monitor-*)
   have NO outbound `target_agents`.
7. Logic gates: OR / AND have exactly 2 inbound source connections;
   Barrier has N>=2; Asker / Forker have exactly 2 outbound branches
   (`target_agents_a` / `target_agents_b`); Counter has 2
   (`target_agents_l` / `target_agents_g`).

Return `{ ok, problems: [{node_id, kind, message}, ...], summary }`.
