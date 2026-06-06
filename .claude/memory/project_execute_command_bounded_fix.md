---
name: project_execute_command_bounded_fix
description: 2026-06-06 execute_command now bounded (timeout + stdin=DEVNULL + kill-tree); fixes the copy-con hang
metadata: 
  node_type: memory
  type: project
  originSessionId: 69c7cb6d-add6-4657-ac26-4cf93c4f765f
---

2026-06-06: Frozen C:\Tlamatini hung — Multi-Turn `execute_command` ran `cmd /c "... && copy con InputValidator.java < NUL"`. `copy con` reads the CON device (not stdin), so `< NUL` never gave EOF; with no console attached it blocked forever. `execute_command` (`tools.py`) used a bare `subprocess.run(command, shell=True)` with **no timeout and inherited stdin**, so it waited indefinitely → the Multi-Turn worker thread froze (log dead at iteration 64). cmd.exe alive 45 min; created a 0-byte file. Server itself stayed responsive (HTTP 200) — only that one request's thread wedged on a leaked stdout pipe handle (un-revivable from outside; killing the cmd did NOT release `communicate()`).

**Immediate recovery:** kill the hung cmd tree; user reloads the chat tab (new thread). Full clean state needs a Tlamatini restart.

**Permanent fix (source only — needs `python build.py` + reinstall for frozen):** added `_run_command_bounded(command, *, shell, timeout=600)` above `execute_command` in `Tlamatini/agent/tools.py` — `subprocess.Popen` with `stdin=subprocess.DEVNULL` + `communicate(timeout=600)`, and on `TimeoutExpired` calls the existing `_terminate_process_tree(psutil.Process(proc.pid))` to kill the WHOLE tree (not just the direct child — a naive `subprocess.run(timeout=)` deadlocks on grandchild-leaked pipe handles) then a 5s best-effort drain. `execute_command` rewired to use it on all 3 paths and returns a clear "timed out / avoid interactive commands, use file_creator" message when `timed_out`. ruff clean, py_compile OK. NOT committed.

Related: [[project_external_exec_safety_layer]] (the earlier `_run_bounded` work was DISCARDED — this is a fresh, minimal re-do scoped to execute_command), [[project_execute_file_foreground_fix]], [[feedback_dont_overbuild_exec_safety]].
