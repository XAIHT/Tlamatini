---
name: jira
description: Read and write Jira issues, comments, transitions via the Jira REST API v3.
metadata:
  openclaw:
    emoji: "🟦"
    requires:
      env: ["JIRA_BASE_URL","JIRA_EMAIL","JIRA_API_TOKEN"]
    primaryEnv: "JIRA_API_TOKEN"
  tlamatini:
    runtime: in-process
    requires_tools: ["chat_agent_apirer"]
    requires_mcps: []
    budget:
      max_iterations: 4
      max_seconds: 60
      max_tokens: 10000
    permissions:
      filesystem: { read: [], write: [] }
      shell:     []
      network:   allow
      db:        deny
    inputs:
      - { name: action, type: enum,   required: true,
          values: ["search","get","create","comment","transition"] }
      - { name: payload, type: object, required: true }
    outputs:
      - { name: response, type: object, required: true }
    triggers:
      keywords: ["jira","issue","ticket"]
---
<!--
═══════════════════════════════════════════════════════════════════
  ✦  T L A M A T I N I  ✦   —   "one who knows"
  Created by  Angela López Mendoza   ·   @angelahack1
  Developer · Architect · Creator of Tlamatini
  Tlamatini Author Banner — do not remove (Angela's name is kept in every build)
═══════════════════════════════════════════════════════════════════
-->

# Jira skill

Use the Jira REST API v3 for issues / comments / transitions.

## Setup

`JIRA_BASE_URL` (e.g. `https://your-domain.atlassian.net`),
`JIRA_EMAIL` and `JIRA_API_TOKEN` must be in env.

## Procedure

- `search` → `POST /rest/api/3/search` with JQL in payload.
- `get`    → `GET /rest/api/3/issue/{key}`.
- `create` → `POST /rest/api/3/issue` with `{ fields: {...} }`.
- `comment`→ `POST /rest/api/3/issue/{key}/comment`.
- `transition`→ `POST /rest/api/3/issue/{key}/transitions`.

Use Basic Auth: `base64(JIRA_EMAIL:JIRA_API_TOKEN)`.

Return the parsed JSON.
