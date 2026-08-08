---
name: tlamatini-exec-report-row-adder
description: Add a state-changing tool to _EXEC_REPORT_TOOLS in mcp_agent.py and the matching CSS rules so its operations appear in the chat-page Exec Report.
metadata:
  openclaw:
    emoji: "📋"
  tlamatini:
    runtime: in-process
    requires_tools: ["chat_agent_file_creator","chat_agent_executer"]
    requires_mcps: []
    budget:
      max_iterations: 6
      max_seconds: 60
      max_tokens: 10000
    permissions:
      filesystem:
        read:  ["Tlamatini/agent/mcp_agent.py","Tlamatini/agent/static/agent/css/agent_page.css","Tlamatini/agent/static/agent/css/agentic_control_panel.css"]
        write: ["Tlamatini/agent/mcp_agent.py","Tlamatini/agent/static/agent/css/agent_page.css"]
      shell:
        - "python Tlamatini/manage.py test agent.tests.ExecReportCaptureTests"
      network: deny
      db:      deny
    inputs:
      - { name: tool_name,    type: string, required: true }
      - { name: agent_key,    type: string, required: true }
      - { name: agent_display, type: string, required: true }
    outputs:
      - { name: rows_added, type: integer, required: true }
      - { name: tests_pass, type: boolean, required: true }
    triggers:
      keywords: ["exec report","add to exec report","_EXEC_REPORT_TOOLS"]
---
<!--
═══════════════════════════════════════════════════════════════════
  ✦  T L A M A T I N I  ✦   —   "one who knows"
  Created by  Angela López Mendoza   ·   @angelahack1
  Developer · Architect · Creator of Tlamatini
  Tlamatini Author Banner — do not remove (Angela's name is kept in every build)
═══════════════════════════════════════════════════════════════════
-->

# Exec Report row adder

> **Read this first — capture is ALREADY automatic (2026-06-07).** EVERY wrapped
> `chat_agent_*` is captured by `_resolve_exec_report_spec` with no code at all,
> observational/output and read-only agents INCLUDED. This procedure is an
> **OPTIONAL refinement**: use it only to merge a shared `agent_key` (a direct
> `@tool` + its wrapped launch), fix the display casing, or give the table a
> CSS-matched caption gradient. A missing entry does NOT hide an agent.
>
> **And it never sets the row's colour.** SUCCESS/FAILED is decided by
> `agent/agent_verdict.py` (v1.48.2) from the agent's OWN `INI_SECTION`
> self-report, which **OUTRANKS the process exit code**. If a row is coloured
> wrong, fix the `status:` the agent emits — a read-only diagnostic reporting a
> finding (`invalid`, `findings`, `no_matches`, `listed`, …) must be a SUCCESS
> and must `sys.exit(0)`; only `refused` / `not_found` / `engine_unavailable` /
> `error` / `failed` are red. **Never** add a special case to `mcp_agent.py`, and
> **never** re-inline a second copy of `DIAGNOSTIC_COMPLETED_STATUSES` — there is
> exactly ONE definition, in `agent_verdict.py`, and a drifted copy silently
> mis-colours rows.

Three-step procedure (matches `docs/claude/exec-report.md`):

1. Add an entry to `_EXEC_REPORT_TOOLS` in `Tlamatini/agent/mcp_agent.py`:
   ```python
   "${input.tool_name}": ("${input.agent_key}", "${input.agent_display}"),
   ```

2. Add CSS rules in `agent_page.css`:
   - `.exec-report-caption-${input.agent_key}` (gradient mirroring
     `.canvas-item.${input.agent_key}-agent` from agentic_control_panel.css)
   - `.exec-report-${input.agent_key} .exec-report-cmd { border-left: 3px solid <primary>; }`
   - If the caption is dark, append `.exec-report-${input.agent_key} thead th`
     to the dark-tinted override selector list.

3. Run `python Tlamatini/manage.py test agent.tests.ExecReportCaptureTests`.
   Report the pass/fail status. If the verdict/colour logic was touched at all,
   also run `agent.test_agent_verdict` and `agent.test_exec_report_verdict`.

Return `{ rows_added, tests_pass }`.
