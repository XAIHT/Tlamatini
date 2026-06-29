---
name: project_reaper_console_window_fix
description: "Orphan reaper was killing Tlamatini's own console-window conhost (frozen onedir builds), closing the window and hanging the server; fixed + tests"
metadata: 
  node_type: memory
  type: project
  originSessionId: bcca9652-ff3d-42a9-8039-7ceaa0b68d3b
---
<!--
═══════════════════════════════════════════════════════════════════
  ✦  T L A M A T I N I  ✦   —   "one who knows"
  Created by  Angela López Mendoza   ·   @angelahack1
  Developer · Architect · Creator of Tlamatini
  Tlamatini Author Banner — do not remove (Angela's name is kept in every build)
═══════════════════════════════════════════════════════════════════
-->

2026-05-20: Fixed a serious bug where the main Tlamatini console window closed unexpectedly and the process stayed hung on a user's machine.

**Root cause:** `agent/orphan_reaper.py::_is_our_console_host()` returned True (→ reap) for any `conhost.exe` whose parent PID was in `our_pid_tree`, and `our_pid_tree` included `our_pid` itself. The build is PyInstaller **onedir** (no `--onefile` in `build.py`), so the installed `Tlamatini.exe` is a single process that owns its console window; that window's `conhost.exe` is a direct child of `os.getpid()` → `conhost.ppid == our_pid` → reaped. Tier 2 (`consumers.py::_tier2_orphan_sweep`, after **every** answer) and Tier 1 (`mcp_agent.py::_reap_after_tool`) both run `include_console_host_sweep=True`, so the window got closed on normal requests. Devs don't see it because source mode / Windows Terminal hosts the conhost under the terminal, not our PID.

**Fix (orphan_reaper.py):**
- New `_console_owner_pid()` resolves our window's host via `GetConsoleWindow` → `GetWindowThreadProcessId` and protects it.
- New `_ancestor_pids(pid)` (bounded/cycle-guarded) protects the launching chain (terminal / shell wrapper / bootloader / Explorer).
- `reap_orphans()` builds `protected_pids = {our_pid} | ancestors | {console_owner}`, skips them in every sweep (Tier-A + snapshot loop).
- Replaced `_is_our_console_host` with pure, unit-testable `_console_host_reap_decision(...)` + fact-gatherer `_is_reapable_console_orphan(...)`: reap a console host ONLY when it's a genuine orphan (parent gone / zombie). NEVER reap a host whose parent is us, an ancestor, or any live process. Defense in depth: even if the ctypes call fails, the `ppid == our_pid` policy guard still protects our window.
- Removed dead `_REAPABLE_HELPERS` frozenset (named powershell.exe/cmd.exe "reap on sight" — never wired in but a footgun for `.ps1`-wrapped launches).

**Secondary hardening (manage.py):** `_TeeStream.write`/`flush` now wrap the original-console write in try/except so a dead/invalid console handle can't raise into a logging thread (a secondary "hang" vector).

**Tests:** new `agent/test_orphan_reaper.py` (22 tests, all pass) pins the contract — esp. `test_conhost_parented_to_our_pid_is_never_reaped`. Verified `_kill_process_tree` in `agent/acpx/runtime.py` only descends from a child Popen (never walks up to our PID). Ruff clean.

See [[feedback_main_branch_only]] — committed/pushed only on explicit request.
