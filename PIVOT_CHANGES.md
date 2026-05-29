# Tlamatini — Change Pivot / Rollback Log

A dated, append-only log of surgical changes with the verbatim request and the
exact before/after, so any single change can be rolled back precisely without
relying on git diffs.

(Fresh start 2026-05-29: the previous follow-up #1–#7 "external-exec hardening"
series was discarded by the user — "nothing you did worked" — and this file was
removed with it. It now begins clean with only the change that survived a real,
evidence-backed diagnosis.)

---

## 2026-05-29 — REAL root cause of "the window never opened": Multi-Turn force-headlessed `execute_file`. Fix = user-driven foreground + parse-gate

### Background
The earlier #1–#7 hardening (syntax gate / watcher daemon / Job-Object containment)
was discarded as not-working. We re-diagnosed the actual incident ("create cat-art.py
then execute it in a foreground window" → window never opened, Tlamatini reported OK)
from the live `tlamatini.log`, not from theory.

### Verbatim user requests
- "ok implement 1 and 2"
- "But remember the desicion of being foregorund or background depends only in the
  user!, and if the user says nothing about foreground or nothing about forked window
  the wwindow must stay in background"

### REAL root cause (evidence-backed, from the last run in tlamatini.log)
1. **No window** — `mcp_agent.py:1096` wraps every Multi-Turn request in
   `scoped_request_state(..., suppress_visible_consoles=multi_turn_enabled)`. With
   Multi-Turn ON, `_suppress_visible_console_launches()` returns True, so
   `launch_in_new_terminal` (tools.py:100) took the `_launch_python_in_background`
   branch (`CREATE_NO_WINDOW | DETACHED_PROCESS`, stdio→DEVNULL). The
   `start "Tlamatini Console" cmd /k` foreground path was NEVER reached. The user's
   "foreground window" was silently run HEADLESS.
2. **False "OK"** — `execute_file` returned `"executed successfully in a new terminal
   window"` unconditionally (no exit-code check; background launch is fire-and-forget
   into DEVNULL).
3. **Broken file** — content passed to file_creator had escaping bugs; on-disk
   `cat-art.py` does not parse (`SyntaxError: unexpected character after line
   continuation` at line 32, `COLORS[\"cyan\"]`; an earlier attempt wrote the whole
   file as one 5337-char line with literal `\n`).
   None of this was what #1–#7 fixed — wrong layer.

### Files changed (production): `Tlamatini/agent/tools.py` ONLY (two functions)

**1. `launch_in_new_terminal(...)`** — added `force_foreground=False`:
- BEFORE: `def launch_in_new_terminal(script_pathfilename, arguments=None):`
  … `if _suppress_visible_console_launches(): return _launch_python_in_background(...)`
- AFTER:  `def launch_in_new_terminal(script_pathfilename, arguments=None, force_foreground=False):`
  … `if _suppress_visible_console_launches() and not force_foreground: return _launch_python_in_background(...)`
  (the foreground `start … cmd /k` path is otherwise unchanged.)

**2. `execute_file(command)` → `execute_file(command, foreground=False)`**:
- **User-driven window (fix #1, per the correction):** the foreground/background
  choice is the USER'S. New `foreground: bool = False`; docstring instructs the LLM to
  set it True ONLY when the user explicitly asks for a visible/foreground/forked
  window, else leave False. Passes `force_foreground=foreground`. **Default =
  background (no window)** when the user is silent (under Multi-Turn suppression). A
  window opens iff `foreground=True` OR suppression is off (legacy non-Multi-Turn).
  Honest result string for BOTH cases.
- **Parse-gate (fix #2):** before launching, if the resolved file ends `.py`/`.pyw`,
  `compile()`-check it; on `SyntaxError` return an actionable `Error:` (line+col+
  snippet, "rewrite IN FULL with file_creator") and do NOT launch. Fail-open on
  NUL/unreadable (`ValueError`/`OSError`).
- **No more false "OK":** return text says "Launched … (confirms the launch, not that
  the script ran to completion)", never "executed successfully".

Minimal, right-layer version of the one idea worth keeping from the discarded work
(a compile() check) — NO watcher daemon, NO containment, NO executer.py mirror, NO
config toggles, NO prompt.pmt edit (guidance lives in the tool docstring the LLM sees).

### Verification (window-safe — `launch_in_new_terminal` mocked; no real console opened)
- `python -m ruff check agent/tools.py` → All checks passed.
- `manage.py test agent.tests.MultiTurnBackgroundLaunchTests` → the 6 launch/console
  tests PASS. The 2 failures in that class (`…allows_context_only_global_plan_with_no_tools`,
  `…ignores_global_plan_when_multi_turn_disabled`) are PRE-EXISTING planner/selector
  tests that never touch `launch_in_new_terminal`/`execute_file` — unrelated.
- Hermetic shell proof (real broken `cat-art.py` + a temp valid file):
  - SILENT + Multi-Turn suppression ON → `force_foreground=False`, "background (no window)".
  - EXPLICIT `foreground=True` + suppression ON → `force_foreground=True`, window message.
  - BROKEN file (`foreground=True`) → parse-gate fires, `launch` NOT called, returns SyntaxError.

### NOT done (decisive proof is a live before/after on the running instance)
- Redo the cat-art scenario in Multi-Turn on the console-attached daphne: with
  "foreground window" a real window now opens; the broken file now returns a
  SyntaxError to fix, not "success". The sandbox can't reproduce the console-stdin path.
- `execute_command`'s analogous `start …` false-OK was NOT touched (out of scope).
  Frozen `c:\Tlamatini` needs `python build.py` to pick this up.

### Rollback
Revert `tools.py`: drop `force_foreground` from `launch_in_new_terminal` (restore the
plain `if _suppress_visible_console_launches():`), and restore `execute_file(command)`
(remove the `foreground` param + parse-gate + honest messages; restore the unconditional
`launch_in_new_terminal(script_path, arguments)` + the old success strings).
