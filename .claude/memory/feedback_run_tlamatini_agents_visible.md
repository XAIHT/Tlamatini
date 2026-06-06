---
name: feedback_run_tlamatini_agents_visible
description: "To show Tlamatini's desktop agents (Playwrighter headed, forked windows, Shoter/Mouser/Keyboarder) on the user's real screen, launch FOREGROUND with dangerouslyDisableSandbox; the sandbox hides the GUI."
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 434332c6-6b89-4961-8110-df04b2046f17
---

The user strongly prefers DOGFOODING Tlamatini's own pool agents (Executer, Pythonxer, Playwrighter, Shoter, Mouser, Keyboarder, ...) to run/verify things, and wants to SEE them on screen — not Claude Code's built-in tools.

**Why / the gotcha:** the Claude Code Bash tool runs **sandboxed**, which renders any spawned GUI (a headed Playwright browser, an Executer/Pythonxer `execute_forked_window` console, Shoter/Mouser targets) in an **isolated window station the user cannot see** — even though `GetProcessWindowStation()` reports `WinSta0`/session-3/`SESSIONNAME=Console`. `run_in_background: true` is worse (fully detached/non-interactive: forked windows' `@pause` hits EOF and closes instantly). Two failed attempts (background, then plain foreground) showed nothing; the THIRD — **foreground + `dangerouslyDisableSandbox: true`** — made the real Chrome appear on the user's desktop. The user explicitly authorized "run it in my session," which is what justifies disabling the sandbox here.

**How to apply:** when the user asks to WATCH a Tlamatini desktop/visible agent run, launch the pool agent (`python <tmp>/<agent>_1/<agent>.py` from an isolated runtime copy + a tailored `config.yaml`) **in the FOREGROUND with `dangerouslyDisableSandbox: true`**. Use `headless: false` + a generous `hold_open_seconds` for Playwrighter, and `execute_forked_window: true` for Executer/Pythonxer (use `non_blocking: true` to avoid blocking on the window's `@pause`, or accept the block with a timeout). Fallback if even that fails: tell the user to launch it themselves via the prompt's `! <command>` prefix (runs in THEIR terminal session). Read the agent's `<agent>_1.log` for the verdict. See [[feedback_agent_naming_conventions]].
