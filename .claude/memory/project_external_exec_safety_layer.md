---
name: project_external_exec_safety_layer
description: "The Python-launch syntax gate + Job-Object containment safety layer, its coverage, and the outstanding Sqler/Mongoxer gap"
metadata: 
  node_type: memory
  type: project
  originSessionId: d3eb9dd6-907c-45de-ba86-0002286d0e70
---
<!--
═══════════════════════════════════════════════════════════════════
  ✦  T L A M A T I N I  ✦   —   "one who knows"
  Created by  Angela López Mendoza   ·   @angelahack1
  Developer · Architect · Creator of Tlamatini
  Tlamatini Author Banner — do not remove (Angela's name is kept in every build)
═══════════════════════════════════════════════════════════════════
-->

**⚠️ DISCARDED 2026-05-29 — the user reverted ALL of this (git discard of the uncommitted tree).** "nothing you did worked." Despite passing tests, this whole external-exec hardening series (gates, containment, `_run_bounded`, the f/u#7 watcher daemon) did NOT solve the real live problem (the `start cmd /k python` window still hung Tlamatini / gave a false "OK"). Treat the description below as HISTORY, not current code — none of it is in the tree. Do NOT reconstruct it or trust the PIVOT_CHANGES.md entries as live. See [[feedback_dont_overbuild_exec_safety]].

2026-05-28 (follow-ups #2/#3 to [[project_pythonxer_forkbomb_fix]]). After a truncated `cat-art.py` flashed a SyntaxError console via `execute_command` (`start "" cmd /k python …`), the Pythonxer-only fix was generalized:

- **`tools.py execute_command`** + **`executer.py`** now run a BLOCKING Python `compile()` gate before launching any `.py`/`.pyw` (helpers `_extract_python_script_paths` / `_gate_python_syntax_in_command` in tools.py; `validate_referenced_python_syntax` in executer.py). Interpreter match is a regex `^(?:python|pythonw|py|pyw)[0-9.]*(?:\.exe)?$` so `python3.12 x.py` / `pythonw x.pyw` / `py -3 x.py` are caught; `-m`/`-c`/nonexistent/non-python are not gated; fail-open. Refusal returns an `Error:` string → Multi-Turn fix-and-retry.
- **`executer.py`** got `_contain_process_tree` (Job Object: active-process cap 64 + KILL_ON_JOB_CLOSE) on its blocking + forked-window paths + `contain_runaway_processes` config toggle.
- **UTF-8 fix** (both executer.py + pythonxer.py): exec child now gets `env=get_agent_env()` with `PYTHONIOENCODING=utf-8`, so emoji/box-drawing output no longer crashes with UnicodeEncodeError.
- **prompt.pmt**: bullet steering to run Python via Pythonxer / bare `python file.py`, NEVER `start cmd /k python file` to pop a console; rewrite truncated files in full.
- Tests: `agent/test_external_exec_safety.py` (27) + `agent/test_pythonxer_agent.py` (21). ruff clean.

**Coverage boundary (known limits):** the gate is Python-FILE-specific — broken `.bat`/PowerShell/`-c` inline is NOT caught; the executer non_blocking PowerShell `Start-Process` path is intentionally uncontained; `execute_command`'s own `subprocess.run` capture has no `encoding=`/containment.

**OUTSTANDING REAL GAP (not yet fixed, awaiting user OK):** `sqler.py` and `mongoxer.py` hardcode `creationflags=CREATE_NEW_CONSOLE` in their `start_agent` (visible window per downstream launch) AND `exec()` arbitrary Python from `config.script` with no containment. Minimal fix: `CREATE_NEW_CONSOLE`→`CREATE_NO_WINDOW` + add `_contain_process_tree`. Full audit of browser/CLI-spawner/MCP agents (googler/playwrighter/acpxer/stm32er/unrealer) + tools.py @tools (execute_file/unzip/decompile/googler) was NOT completed. All of this needs `python build.py` to reach frozen `c:\Tlamatini`.
