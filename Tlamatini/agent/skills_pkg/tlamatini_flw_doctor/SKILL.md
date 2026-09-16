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
<!--
═══════════════════════════════════════════════════════════════════
  ✦  T L A M A T I N I  ✦   —   "one who knows"
  Created by  Angela López Mendoza   ·   @angelahack1
  Developer · Architect · Creator of Tlamatini
  Tlamatini Author Banner — do not remove (Angela's name is kept in every build)
═══════════════════════════════════════════════════════════════════
-->

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

## Current installed-agent contract — 2026-09-15

Use `agent/agents/flowcreator/flow_catalog.json` for canonical names, current config schemas, output/input slots, lifecycle flags and structured fields for all 89 installed types. GUI-Manager is design only. After changing a template/contract/reference, run `python scripts/update_flow_catalog.py` and its `--check` mode in the repository. Deployment refreshes runtime snapshots.

FlowCreator selects capabilities before detailed design, validates the generated plan, and uses bounded repair. Declare Ender input connections explicitly; Ender `target_agents` is a kill list. Counter uses L/G slots; source dependencies do not choose a conditional output branch. Generated Parametrizers require valid `_parametrizer_mappings`, one source and one target. Do not maintain a separate hardcoded Parametrizer producer list.

For desktop flows, use explicit physical/screenshot geometry and verified target windows. `input_sent` is input delivery only; errors may be partial and must not be blindly replayed. Read `docs/desktop-input-and-flow-contracts.md` and `docs/agent-coverage.md` for the full contract and verification scope.
