---
name: tlamatini-planner-trace-replay
description: Replay the most recent global execution planner trace from tlamatini.log and explain why each capability got the score it did.
metadata:
  openclaw:
    emoji: "🔁"
  tlamatini:
    runtime: in-process
    requires_tools: ["chat_agent_executer"]
    requires_mcps: ["Files-Search"]
    budget:
      max_iterations: 6
      max_seconds: 60
      max_tokens: 12000
    permissions:
      filesystem:
        read:  ["Tlamatini/tlamatini.log","Tlamatini/agent/global_execution_planner.py"]
        write: []
      shell:
        - "python -c \"open('Tlamatini/tlamatini.log').read()[-200000:]\""
      network: deny
      db:      deny
    inputs:
      - { name: turns, type: integer, required: false, default: 1,
          description: "How many recent planner traces to replay (1 = most recent)" }
    outputs:
      - { name: traces, type: array,  required: true }
      - { name: notes,  type: string, required: true }
    triggers:
      keywords: ["planner trace","planner replay","why did planner","planner score"]
---
<!--
═══════════════════════════════════════════════════════════════════
  ✦  T L A M A T I N I  ✦   —   "one who knows"
  Created by  Angela López Mendoza   ·   @angelahack1
  Developer · Architect · Creator of Tlamatini
  Tlamatini Author Banner — do not remove (Angela's name is kept in every build)
═══════════════════════════════════════════════════════════════════
-->

# Planner trace replay

Read the tail of `Tlamatini/tlamatini.log`. Locate the most recent
`build_global_execution_plan` invocation and the per-capability scoring
output.

For each capability the planner scored:
- record its score and the keywords that contributed
- record whether it was selected (top-N cap, see
  `max_selected_tools = 20` per gotchas.md #11)
- if a capability that "should" have been selected was not, explain why

Return `{ traces: [...], notes }`. Keep traces under 32 KB total to
preserve context.
