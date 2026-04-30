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

# Exec Report row adder

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
   Report the pass/fail status.

Return `{ rows_added, tests_pass }`.
