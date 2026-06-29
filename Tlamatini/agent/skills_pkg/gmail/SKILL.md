---
name: gmail
description: Read and send Gmail messages and threads via Gmail API.
metadata:
  openclaw:
    emoji: "📧"
    requires:
      env: ["GMAIL_OAUTH_TOKEN"]
    primaryEnv: "GMAIL_OAUTH_TOKEN"
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
      - { name: action, type: enum,
          values: ["search","get","send","reply","label"], required: true }
      - { name: payload, type: object, required: true }
    outputs:
      - { name: response, type: object, required: true }
    triggers:
      keywords: ["gmail","email","mailbox","inbox"]
---
<!--
═══════════════════════════════════════════════════════════════════
  ✦  T L A M A T I N I  ✦   —   "one who knows"
  Created by  Angela López Mendoza   ·   @angelahack1
  Developer · Architect · Creator of Tlamatini
  Tlamatini Author Banner — do not remove (Angela's name is kept in every build)
═══════════════════════════════════════════════════════════════════
-->

# Gmail skill

Use the Gmail API. Acquire an OAuth token through Google's standard flow
and place in `GMAIL_OAUTH_TOKEN`.

## Endpoints

- `search` → `GET /gmail/v1/users/me/messages?q=<q>`
- `get`    → `GET /gmail/v1/users/me/messages/{id}`
- `send`   → `POST /gmail/v1/users/me/messages/send`
- `reply`  → same as send, with `threadId` set
- `label`  → `POST /gmail/v1/users/me/messages/{id}/modify`

Bodies for `send` use base64url-encoded RFC 2822 messages.
