---
name: github
description: Use the gh CLI for GitHub issues, PR status, CI/logs, comments, reviews, releases, and API queries.
metadata:
  openclaw:
    emoji: "🐙"
    requires:
      bins: ["gh"]
    install:
      - { id: "winget", kind: "winget", package: "GitHub.cli" }
      - { id: "brew",   kind: "brew",   formula: "gh" }
      - { id: "apt",    kind: "apt",    package: "gh" }
  tlamatini:
    runtime: in-process
    requires_tools: ["chat_agent_executer"]
    requires_mcps: []
    budget:
      max_iterations: 6
      max_seconds: 90
      max_tokens: 12000
    permissions:
      filesystem: { read: [], write: [] }
      shell:
        - "gh auth status"
        - "gh pr *"
        - "gh issue *"
        - "gh run *"
        - "gh release *"
        - "gh api *"
      network: allow
      db:      deny
    inputs:
      - { name: action, type: string, required: true,
          description: "PR list, PR view, issue create, run logs, etc." }
      - { name: repo,   type: string, required: false }
    outputs:
      - { name: result, type: string, required: true }
    triggers:
      keywords: ["github","pr","pull request","gh","issue","run logs","release"]
---

# GitHub skill

Use the `gh` CLI for GitHub-side operations.

## When to use
- Checking PR status, reviews, merge readiness
- Viewing CI / workflow run status and logs
- Creating, closing, commenting on issues
- Querying GitHub API for repository data

## When NOT to use
- Local git operations (commit, push, pull, branch) -> use `git` directly.
- Non-GitHub repos -> use that platform's CLI.

## Setup
- Run `gh auth login` once (interactive — do not attempt from this skill).
- Confirm with `gh auth status`.

## Procedure
1. Construct the `gh` command from `${input.action}` and optional
   `${input.repo}`.
2. Run via `chat_agent_executer`.
3. Capture stdout. Truncate to ~12000 chars before returning.
4. Return `{ result: <stdout> }`.
