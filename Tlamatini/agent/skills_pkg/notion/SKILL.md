---
name: notion
description: Use the Notion API to create, read, update Notion pages, data sources (databases), and blocks.
metadata:
  openclaw:
    emoji: "📝"
    requires:
      env: ["NOTION_API_KEY"]
    primaryEnv: "NOTION_API_KEY"
  tlamatini:
    runtime: in-process
    requires_tools: ["chat_agent_apirer","chat_agent_executer"]
    requires_mcps: []
    budget:
      max_iterations: 6
      max_seconds: 90
      max_tokens: 12000
    permissions:
      filesystem:
        read:  ["~/.config/notion/api_key"]
        write: []
      shell:
        - "curl -X * https://api.notion.com/v1/*"
      network: allow
      db:      deny
    inputs:
      - { name: action, type: enum,   required: true,
          values: ["search","page-create","page-update","db-query","block-append"] }
      - { name: payload, type: object, required: true }
    outputs:
      - { name: response, type: object, required: true }
    triggers:
      keywords: ["notion","page","database","data source"]
---

# Notion skill

## Setup

1. Create an integration at https://notion.so/my-integrations.
2. Save the API key under `~/.config/notion/api_key` (no newline).
3. Share the target pages/databases with the integration.

## API basics

All requests:
```
Authorization: Bearer $NOTION_KEY
Notion-Version: 2025-09-03
Content-Type: application/json
```

## Procedure

Map `${input.action}` to the right endpoint:

- `search`       → `POST /v1/search`
- `page-create`  → `POST /v1/pages`
- `page-update`  → `PATCH /v1/pages/{page_id}`
- `db-query`     → `POST /v1/data_sources/{id}/query`
- `block-append` → `PATCH /v1/blocks/{block_id}/children`

Compose the JSON body from `${input.payload}`. Issue with
`chat_agent_apirer`. Return the parsed JSON response.
