---
name: feedback_forbidden_headless_visible_tests
description: All automated tests and diagnostics must remain visible on Angela's real desktop, with no headless exception.
type: feedback
---

# Headless tests are forbidden — Angela, reaffirmed 2026-09-23

**HEADLESS IS FORBIDDEN. ALL EXECUTION MUST BE VISIBLE.** Run every test and
diagnostic in a visible forked foreground console. Browser automation must
explicitly use `headless=False` / `headless: false`, including fallback launches.
Legacy flags and environment variables must never enable a hidden browser.
Keep the browser visible and monitor the live log every 5–15 seconds during
long runs. A stale answer, timeout or unseen run is never a watched pass.

Read [the mandatory policy](../../TestsVisiblesAndVisibleExecutionFromClaude2Codex.md)
and [AGENTS.md](../../AGENTS.md). If visibility cannot be confirmed, do not run.
