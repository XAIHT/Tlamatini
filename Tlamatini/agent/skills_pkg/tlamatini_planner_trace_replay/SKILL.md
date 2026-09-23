---
name: tlamatini-planner-trace-replay
description: Replay the most recent global execution planner trace from tlamatini.log and explain why each capability got the score it did.
metadata:
  openclaw:
    emoji: "🔁"
  tlamatini:
    runtime: in-process
    requires_tools: ["chat_agent_executer"]
    requires_mcps: ["Files-Search"]
    budget:
      max_iterations: 6
      max_seconds: 60
      max_tokens: 12000
    permissions:
      filesystem:
        read:  ["Tlamatini/tlamatini.log","Tlamatini/agent/global_execution_planner.py"]
        write: []
      shell:
        - "python -c \"open('Tlamatini/tlamatini.log').read()[-200000:]\""
      network: deny
      db:      deny
    inputs:
      - { name: turns, type: integer, required: false, default: 1,
          description: "How many recent planner traces to replay (1 = most recent)" }
    outputs:
      - { name: traces, type: array,  required: true }
      - { name: notes,  type: string, required: true }
    triggers:
      keywords: ["planner trace","planner replay","why did planner","planner score"]
---
<!--
═══════════════════════════════════════════════════════════════════
  ✦  T L A M A T I N I  ✦   —   "one who knows"
  Created by  Angela López Mendoza   ·   @angelahack1
  Developer · Architect · Creator of Tlamatini
  Tlamatini Author Banner — do not remove (Angela's name is kept in every build)
═══════════════════════════════════════════════════════════════════
-->

# Planner trace replay

> **HEADLESS IS FORBIDDEN. VISIBLE FOREGROUND EXECUTION ONLY.** Every command, automated test, diagnostic, script, build, agent and browser must run in a visible foreground window on Angela's real desktop. Use forked CMD/PowerShell windows, `execute_forked_window: true`, and `headless: false`. Monitor live; if visibility cannot be confirmed, do not run. Read the [mandatory execution policy](../../../../TestsVisiblesAndVisibleExecutionFromClaude2Codex.md).

Explain why a tool was, or was not, available to the model on a given turn.

## ⚠️ THE PLANNER IS ONLY THE FIRST OF FIVE STAGES

The planner's top-N cap is **not** the answer to "why was this tool missing".
Since the 2026-06 mandate Multi-Turn no longer binds a planner subset at all —
`mcp_agent.py` rank-and-budget binds the surface afterwards, and that is where
a tool is actually lost. Report every stage SEPARATELY, and when the log does
not contain a stage, **say the stage is unavailable** rather than attributing
the outcome to the one you can see.

| # | stage | what it decides | where it shows up |
|---|---|---|---|
| 1 | **Enabled surface** | which tools exist at all for this user | `Tool` / `Agent` / `Skill` rows; a disabled row is invisible to everything downstream |
| 2 | **Checkbox filtering** | ACPX on/off (`filter_acpx_tools`) strips all 12 ACPX/Skill tools; Multi-Turn off means no tools at all | request flags |
| 3 | **Planner ranking** | capability scores, keyword hits, co-selection rules, short-follow-up boost | `build_global_execution_plan` output |
| 4 | **Rank-and-budget binding** | `_budget_select_tools` — binds the WHOLE surface when it fits the token budget; otherwise keeps a guaranteed operator CORE + the planner's picks + the highest-scored tools and **drops the low-rank tail** | the drop is logged, never silent |
| 5 | **Emergency core fallback** | if the budgeter returns nothing while tools were requested, `_emergency_core_tools` restores the operator core and a notice is surfaced in the chat | a `_starved_notice` |

⚠️ **`max_selected_tools = 20` no longer removes a tool from the bind.** It
shapes capability hints and ordering only. Citing it as the reason a tool was
missing is the specific wrong answer this skill exists to stop giving.

## Procedure

1. Read the tail of `Tlamatini/tlamatini.log`. Filter to the request you care
   about — the per-line `[aN]` user/turn tag makes that exact.
2. Recover, per stage: the **enabled/requested** tool set, the ACPX checkbox
   state, the planner's **recommendations with scores**, the **final bound
   set**, the count and names dropped for token budget, and any **fallback**
   event.
3. Compare requested vs bound. A tool present in 1 and absent in 4 was dropped
   by budget, not by the planner.
4. If a stage is absent from the log, record it as `unavailable` in `stages`.
   Do NOT infer it.

Return `{ stages: {...}, traces: [...], missing_tool_explanation, notes }`.
Keep traces under 32 KB total to preserve context.
