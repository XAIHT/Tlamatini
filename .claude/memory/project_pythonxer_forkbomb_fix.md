---
name: project_pythonxer_forkbomb_fix
description: "Pythonxer crash (thousands of flashing console windows, machine restart) — fix = blocking syntax gate + blocking Ruff (non-zero on lint fail) + Job-Object fork-bomb containment + Multi-Turn fix-and-retry"
metadata: 
  node_type: memory
  type: project
  originSessionId: 79ff5edf-0e90-413b-a16d-6483bea7c3a2
---
<!--
═══════════════════════════════════════════════════════════════════
  ✦  T L A M A T I N I  ✦   —   "one who knows"
  Created by  Angela López Mendoza   ·   @angelahack1
  Developer · Architect · Creator of Tlamatini
  Tlamatini Author Banner — do not remove (Angela's name is kept in every build)
═══════════════════════════════════════════════════════════════════
-->

**⚠️ DISCARDED 2026-05-29, then PARTIALLY re-added (strict) the same day per explicit request.** The user first reverted ALL of this ("nothing you did worked"). Later he explicitly asked for the Ruff gate + the LLM fix→re-ruff→retry loop ("...up to having a python script correct!" / "Strict"), so the SUBSET below was re-implemented — STRICT and minimal — see [[project_pythonxer_strict_ruff_gate]]. Re-added: compile() syntax floor + BLOCKING Ruff in pythonxer.py (config `ruff_blocking` default True) + `retryable=True` fix-and-retry message in tools.py `_launch_wrapped_chat_agent`. STILL discarded / do NOT reconstruct: the Job-Object containment, the `_watch_script_completion` watcher daemon, the executer.py mirror. See also [[feedback_dont_overbuild_exec_safety]]. Everything below is the ORIGINAL (over-built) write-up — HISTORY.

2026-05-28: Pythonxer (c:\Tlamatini frozen) opened thousands of console windows that flashed open/closed and survived killing Tlamatini.exe + Ollama → user had to restart the machine.

**Root cause** (crash log gone — live tlamatini.log truncates on start; install reinstalled): NOT an external relauncher. Multi-Turn chat is hard-capped (`mcp_agent.py`: 256-call quota + dedup + stop-after-3-identical); nothing external loops `execute_forked_window` (only pythonxer.py/executer.py reference it). Amplifier = an IN-SCRIPT fork bomb (valid-syntax script spawning console subprocesses in a loop), orphaned grandchildren outlive Tlamatini. Ruff was invoked pre-exec but ADVISORY (return ignored); Ruff can't catch a valid-syntax fork bomb anyway.

**Fix — 4 files:**
1. `agent/agents/pythonxer/pythonxer.py` (TRACKED):
   - `validate_syntax()` = BLOCKING `compile()` gate BEFORE any spawn → broken script refused, no window, return False. (E2E test D: `def f(:` + forked → 0 windows, exit 1, Ruff never reached.)
   - Ruff now BLOCKING: consume `validate_with_ruff` bool; if `_RUFF_BLOCKING` (config `ruff_blocking`, default True) and Ruff found issues → log banner + return False (non-zero). Ruff missing/timeout/error fails OPEN. Findings already logged as `[Ruff] …`. (E2E test B: F401+F821 → exit 1, not executed; test C ruff_blocking=false → executed, advisory.)
   - `_contain_process_tree()` = Windows Job Object (active-proc cap 64 + KILL_ON_JOB_CLOSE) on BOTH exec paths (non-forked refactored subprocess.run→Popen+communicate). Gated by config `contain_runaway_processes` (default True). Fail-open, Windows-only.
2. `config.yaml` (git-TRACKED): added `contain_runaway_processes: true` + `ruff_blocking: true`. Runtime defaults both to True via `config.get(...,True)`, so safety is active even without the keys / on a fresh config.
3. `agent/tools.py` (TRACKED) `_launch_wrapped_chat_agent`: failed-state message rewritten to instruct fix-and-retry + `retryable=True` (was `retryable=False` + "inspect the log"). Generic to ALL wrapped agents. The non-zero→`status="failed"` mapping + `log_excerpt` forwarding ALREADY existed in `chat_agent_runtime.reconcile_chat_agent_run` (exitCode!=0→failed) — that's why the chain works end-to-end once Pythonxer exits non-zero.
4. `agent/prompt.pmt` (TRACKED): added bullet (~L165) — a `status:"failed"` wrapped result is actionable: read log_excerpt, fix script/command, retry same tool with corrected input (never identical).

**Why:** a runaway/broken Pythonxer script can no longer flood the desktop or orphan processes, AND Tlamatini self-corrects lint/syntax/runtime failures via the Multi-Turn loop.

**Gotchas / follow-ups:**
- Both pythonxer.py AND pythonxer/config.yaml are git-TRACKED (verified `git ls-files --error-unmatch` + `git check-ignore` finds no rule). config.yaml change carries no secret (just the 2 toggles) so committing it is fine.
- Frozen c:\Tlamatini needs `python build.py` rebuild to pick this up.
- `executer.py` has the SAME forked-window fork-bomb hole — mirror `_contain_process_tree` there (DEFERRED; executer's `start X`+detach is a plausible legit pattern KILL_ON_JOB_CLOSE would change). tools.py+prompt.pmt retry fix already covers Executer.
- `ruff_blocking` default True changes CANVAS Pythonxer too (refuses lint-failing scripts); set false per-node for old advisory behaviour.
- Test log filename = directory basename + ".log" (so an isolated copy in a temp dir named `pythonxer` writes `pythonxer.log`; a dir named `px_v` writes `px_v.log`). Bit me twice during E2E.
- TESTS: new `agent/test_pythonxer_agent.py` = 20 tests, all green, ruff clean (`manage.py test agent.test_pythonxer_agent`). Hermetic — drives REAL pythonxer.py as a subprocess in a temp dir named `pythonxer` (log = dir basename) + static source-contract checks (test_build_scripts.py convention). Covers syntax-gate/no-window, ruff blocking+advisory+default+findings-logged, clean/runtime-error exit codes, Windows-only containment (incl. 40-child mass-spawn), validate_syntax unit, config toggles, and the tools.py(retryable=True/FIX)+prompt.pmt plumbing. GOTCHA: build config.yaml in tests via yaml.safe_dump from a dict — NOT f"{script!r}" (repr quoting is inconsistent and YAML single-quotes don't expand \n → multi-line scripts collapse to one broken line). Forked-window cases ALWAYS use a refused broken-syntax script so no real console opens/blocks on @pause. Runtime-error test sets ruff_blocking=False (a bare module-level `raise` trips ruff B/F otherwise).
- PRE-EXISTING FAILING TEST (not mine; NOT pythonxer): `agent.tests.AssignmentParserRobustnessTests.test_every_registry_example_resolves_against_its_template` fails STANDALONE on pristine code (verified by stashing all 4 of my files — identical FAILED). `AssertionError: ['[stm32er] Parameter 'then action' was not found ... Did you mean: action?']` — the stm32er `example_request` splits on "then action" instead of "action". Genuine pre-existing bug in chat_agent_registry stm32er example/parser, unrelated to this task. My test_pythonxer_agent passes fully (20/20); existing pythonxer unit tests still pass (3/3). Flagged for owner; left unfixed (outside scope).
- Not committed (user owns git). Recorded in repo-root PIVOT_CHANGES.md per [[feedback_track_changes_pivot_file]].
