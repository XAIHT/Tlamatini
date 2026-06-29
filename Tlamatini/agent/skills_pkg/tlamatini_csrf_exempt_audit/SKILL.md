---
name: tlamatini-csrf-exempt-audit
description: Enumerate every @csrf_exempt-decorated view in Tlamatini/agent/views.py and classify whether each one really needs the exemption.
metadata:
  openclaw:
    emoji: "🛡"
  tlamatini:
    runtime: in-process
    requires_tools: ["chat_agent_executer"]
    requires_mcps: ["Files-Search"]
    budget:
      max_iterations: 4
      max_seconds: 60
      max_tokens: 12000
    permissions:
      filesystem:
        read:  ["Tlamatini/agent/views.py","Tlamatini/agent/urls.py"]
        write: []
      shell:   []
      network: deny
      db:      deny
    inputs: []
    outputs:
      - { name: total,            type: integer, required: true }
      - { name: classifications,  type: array,   required: true }
      - { name: recommendations,  type: array,   required: true }
    triggers:
      keywords: ["csrf","csrf_exempt","csrf audit"]
---
<!--
═══════════════════════════════════════════════════════════════════
  ✦  T L A M A T I N I  ✦   —   "one who knows"
  Created by  Angela López Mendoza   ·   @angelahack1
  Developer · Architect · Creator of Tlamatini
  Tlamatini Author Banner — do not remove (Angela's name is kept in every build)
═══════════════════════════════════════════════════════════════════
-->

# CSRF-exempt audit

The TlamatiniVsOpenClaw report counted 60+ `@csrf_exempt` decorators in
`Tlamatini/agent/views.py`. Most are necessary for WebSocket-adjacent
JSON endpoints, but the wholesale exemption is a security smell.

## Procedure

1. Grep `Tlamatini/agent/views.py` for `@csrf_exempt`.
2. For each match, inspect the view above it and classify:
   - `unsafe-without-csrf`: state-changing POST that should NOT be exempt.
   - `safe-because-websocket`: feeds a WebSocket session-restore path.
   - `safe-because-internal-tool`: only callable by Tlamatini's own JS;
     a CSRF token would be appropriate.
   - `unknown`: needs human review.
3. For each non-`safe-because-websocket` row, propose the smallest fix
   (token tag, middleware exception, view rewrite).

Return `{ total, classifications: [{view_name, kind}], recommendations: [...] }`.
