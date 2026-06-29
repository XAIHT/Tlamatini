---
name: slack
description: Post messages, read channels, and manage threads via Slack Web API.
metadata:
  openclaw:
    emoji: "💬"
    requires:
      env: ["SLACK_BOT_TOKEN"]
    primaryEnv: "SLACK_BOT_TOKEN"
  tlamatini:
    runtime: in-process
    requires_tools: ["chat_agent_apirer"]
    requires_mcps: []
    budget:
      max_iterations: 4
      max_seconds: 60
      max_tokens: 8000
    permissions:
      filesystem: { read: [], write: [] }
      shell:     []
      network:   allow
      db:        deny
    inputs:
      - { name: action, type: enum,
          values: ["post","reply","read-history","react","upload"], required: true }
      - { name: payload, type: object, required: true }
    outputs:
      - { name: response, type: object, required: true }
    triggers:
      keywords: ["slack","channel","dm","thread"]
---
<!--
═══════════════════════════════════════════════════════════════════
  ✦  T L A M A T I N I  ✦   —   "one who knows"
  Created by  Angela López Mendoza   ·   @angelahack1
  Developer · Architect · Creator of Tlamatini
  Tlamatini Author Banner — do not remove (Angela's name is kept in every build)
═══════════════════════════════════════════════════════════════════
-->

# Slack skill

Use the Slack Web API. `SLACK_BOT_TOKEN` must be in env.

## Endpoints

- `post`         → `chat.postMessage`
- `reply`        → `chat.postMessage` with `thread_ts`
- `read-history` → `conversations.history`
- `react`        → `reactions.add`
- `upload`       → `files.upload` (or `files.uploadV2` for >5MB)

Endpoints are at `https://slack.com/api/<method>`. Token goes in
`Authorization: Bearer ...`. Body is `application/json` for most modern
methods.
