---
name: feedback_foreground_visible_windows
description: Every Tlamatini execution must run in a visible forked foreground window; headless is forbidden.
type: feedback
---

# All execution must be visible — Angela, reaffirmed 2026-09-23

> Current version: **[v1.92.3](../../docs/changes/2026-11-01-v1.92.3.md)**.


**HEADLESS IS FORBIDDEN.** Every command, automated test, diagnostic, script,
build, agent, prompt, CMD/PowerShell session and browser must run in a visible,
forked foreground window on Angela's real desktop. Keep consoles open afterward.
No hidden/background jobs, no minimized windows, no headless browser, no CI or
quick-check exception. If visibility cannot be confirmed, do not execute.

Read [the mandatory policy](../../TestsVisiblesAndVisibleExecutionFromClaude2Codex.md)
and [AGENTS.md](../../AGENTS.md). Monitor live and report only observed evidence.
