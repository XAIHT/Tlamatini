---
name: acp-router
description: Route plain-language requests for Claude Code, Cursor, Codex, Gemini, Qwen, Pi, Kiro, Kimi, iFlow, Factory Droid, Kilocode, OpenCode, Copilot into ACPX child sessions via acp_spawn. Pick the right agentId for the user's intent.
metadata:
  openclaw:
    emoji: "🧭"
  tlamatini:
    runtime: in-process
    requires_tools: ["acp_spawn", "acp_send", "acp_kill", "list_acp_agents", "acp_doctor"]
    requires_mcps: []
    budget:
      max_iterations: 4
      max_seconds: 30
      max_tokens: 6000
    permissions:
      filesystem: { read: [], write: [] }
      shell:     []
      network:   deny
      db:        deny
    inputs:
      - { name: harness, type: enum, required: true,
          values: ["claude","cursor","codex","copilot","gemini","qwen","pi","droid","iflow","kilocode","kimi","kiro","opencode","tlamatini"] }
      - { name: task,    type: string, required: true }
      - { name: cwd,     type: string, required: false }
      - { name: mode,    type: enum,   required: false,
          values: ["session","one-shot"], default: "session" }
    outputs:
      - { name: session_id,      type: string, required: true }
      - { name: agent_id,        type: string, required: true }
      - { name: transcript_path, type: string, required: true }
    triggers:
      keywords: ["claude code","cursor","codex","copilot","gemini","qwen","kiro","kimi","iflow","droid","kilocode","opencode","run in","spawn","acp"]
---

# ACP Router

Route a plain-language request to the right ACPX harness.

## Decision rules

1. If the user's wording names a harness explicitly ("run this in Claude
   Code", "ask Cursor to..."), use that as `harness` directly.
2. If the user wants Codex chat conversation, prefer the native Codex
   binding (a separate skill); use ACPX Codex only when ACP/`/acp`/acpx
   is named explicitly or when background spawn is needed.
3. Default `mode` to `session` so follow-up turns can be added with
   `acp_send`. Use `one-shot` only when the user asked for a single
   non-interactive task.

## Procedure

1. Call `list_acp_agents` to confirm the chosen agentId is `resolvable`.
   If not, call `acp_doctor` and surface the doctor message to the user.
2. Call `acp_spawn(agent_id=harness, task=<task>, cwd=<cwd>, mode=<mode>)`.
3. Return `{session_id, agent_id, transcript_path}` from the spawn result.

## Failure handling

- If `acp_spawn` returns `code: AGENT_NOT_FOUND`, do NOT silently fall
  back to a different harness. Report the missing CLI to the user, name
  the install instruction (e.g. "install the Claude Code CLI"), and ask
  whether they want to retry with a different harness.
- If `acp_spawn` returns `code: PERMISSION_DENIED`, the runtime is in
  `deny-all` mode. Report this to the user; do not try to bypass.
