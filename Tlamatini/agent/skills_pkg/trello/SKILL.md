---
name: trello
description: Manage Trello boards, lists, and cards via the Trello REST API.
metadata:
  openclaw:
    emoji: "🟦"
    requires:
      env: ["TRELLO_KEY","TRELLO_TOKEN"]
    primaryEnv: "TRELLO_TOKEN"
  tlamatini:
    runtime: in-process
    requires_tools: ["chat_agent_apirer"]
    requires_mcps: []
    budget:
      max_iterations: 4
      max_seconds: 30
      max_tokens: 6000
    permissions:
      filesystem: { read: [], write: [] }
      shell:     []
      network:   allow
      db:        deny
    inputs:
      - { name: action, type: enum,
          values: ["list-boards","list-cards","add-card","move-card","comment-card"],
          required: true }
      - { name: payload, type: object, required: false }
    outputs:
      - { name: response, type: object, required: true }
    triggers:
      keywords: ["trello","board","card","kanban"]
---

# Trello skill

Base URL: `https://api.trello.com/1/`. Append
`?key=$TRELLO_KEY&token=$TRELLO_TOKEN` to every URL.

Endpoints:
- `list-boards` → `GET /members/me/boards`
- `list-cards`  → `GET /boards/{boardId}/cards`
- `add-card`    → `POST /cards` with `idList`, `name`, `desc`
- `move-card`   → `PUT /cards/{id}` with `idList`
- `comment-card`→ `POST /cards/{id}/actions/comments` with `text`
