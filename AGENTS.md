<!--
Tlamatini — "one who knows"
Created by Angela López Mendoza · @angelahack1
Tlamatini Author Banner — do not remove
-->

# Tlamatini instructions for Codex and every coding agent

## HEADLESS IS FORBIDDEN. ALL EXECUTION MUST BE VISIBLE.

Angela reaffirmed this mandatory repository rule on 2026-09-23. Read
[TestsVisiblesAndVisibleExecutionFromClaude2Codex.md](TestsVisiblesAndVisibleExecutionFromClaude2Codex.md)
before executing anything. This applies to every automated test, command,
diagnostic, script, build, agent, prompt, CMD/PowerShell session and browser.

- Run in a **visible, forked foreground window on Angela's real desktop**.
  Keep consoles and browsers visible while the work runs, and leave the console
  open afterward so its output can be read. Use PowerShell `-NoExit` or CMD `/k`.
- Browser automation must explicitly use **`headless=False` / `headless: false`**.
  Never rely on a browser library's default. Headless mode is forbidden for CI,
  smoke checks, diagnostics, long runs and all other execution too.
- With Tlamatini's Executer/Pythonxer, use `execute_forked_window: true`;
  with `execute_file`, request `foreground=True`; with Playwrighter, use
  `headless: false` and sufficient `hold_open_seconds` for inspection.
- Never use hidden/minimized windows, `run_in_background`, detached jobs,
  `CREATE_NO_WINDOW`, `DETACHED_PROCESS`, or `-WindowStyle Hidden` to perform
  the requested work. A saved log or screenshot is not a substitute for visibility.
- Verify that the actual window is visible on the interactive desktop before
  running the workload. A PID, successful launch call, or activation request
  alone does not establish that. **If visibility cannot be confirmed, do not
  execute the workload; explain the limitation to Angela.**
- Monitor long runs live. Read the live transcript every 5–15 seconds, report
  meaningful progress or failures, and inspect the first error and application
  log. Record the exit code and final result; never report unseen work as watched.
- Every new skill, runbook, harness and execution example must preserve this rule.
  Legacy headless flags must be refused loudly and must never enable a hidden
  browser. Review launch sites and fallbacks, not only default settings.

The linked policy contains the concrete launch instructions. It governs execution
even where older documentation describes background product implementation.

## Existing repository contracts

Read [CLAUDE.md](CLAUDE.md) and relevant documents indexed by
[docs/claude/INDEX.md](docs/claude/INDEX.md). Preserve unrelated local edits.
Never rewrite Git history. Do not modify the protected database backup/restore
mechanics unless Angela explicitly requests it in the current turn.
