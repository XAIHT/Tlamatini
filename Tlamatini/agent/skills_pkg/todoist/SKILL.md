---
name: todoist
description: Manage Todoist tasks and projects via the Todoist REST API v2.
metadata:
  openclaw:
    emoji: "✅"
    requires:
      env: ["TODOIST_API_TOKEN"]
    primaryEnv: "TODOIST_API_TOKEN"
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
          values: ["list-tasks","add-task","close-task","reopen-task","list-projects","add-project"],
          required: true }
      - { name: payload, type: object, required: false }
    outputs:
      - { name: response, type: object, required: true }
    triggers:
      keywords: ["todoist","task","todo"]
---

# Todoist skill

Base URL: `https://api.todoist.com/rest/v2/`. Token goes in
`Authorization: Bearer $TODOIST_API_TOKEN`.

Endpoints:
- `list-tasks`     → `GET /tasks`
- `add-task`       → `POST /tasks`
- `close-task`     → `POST /tasks/{id}/close`
- `reopen-task`    → `POST /tasks/{id}/reopen`
- `list-projects`  → `GET /projects`
- `add-project`    → `POST /projects`
