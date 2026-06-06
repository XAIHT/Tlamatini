---
name: project_pythonxer_strict_ruff_gate
description: STRICT Pythonxer correctness gate (compile() floor + blocking Ruff) + LLM fix→re-ruff→retry loop — the sanctioned minimal subset re-added 2026-05-29 after the broader fork-bomb work was discarded
metadata: 
  node_type: memory
  type: project
  originSessionId: 1e984263-7cb7-4f48-a806-931aeb417374
---

2026-05-29: After the user discarded the whole #1–#7 exec hardening, he explicitly asked for the Ruff gate + an LLM fix→re-ruff→retry loop ("...up to having a python script correct!" / "Strict"). Re-implemented ONLY that subset, strict and minimal (NOT the discarded containment/watcher/executer-mirror). Supersedes the relevant part of [[project_pythonxer_forkbomb_fix]].

**Files (3):**
- `agent/agents/pythonxer/pythonxer.py`: module global `_RUFF_BLOCKING=True`; `execute_python_script` now gates BEFORE any execution — (1) `compile(script_content, path, "exec")` syntax floor → SyntaxError logs + `return False` (works even if Ruff absent); (2) `ruff_ok = validate_with_ruff(...)`; `if _RUFF_BLOCKING and not ruff_ok:` → log "⛔ RUFF FAILED - refusing to execute" + `return False`. `main()` reads `_RUFF_BLOCKING = bool(config.get('ruff_blocking', True))`. validate_with_ruff still fails OPEN when Ruff is missing/timeout (the compile() floor still guarantees syntax).
- `agent/agents/pythonxer/config.yaml`: `ruff_blocking: true` + rewritten BEHAVIOR header.
- `agent/tools.py` `_launch_wrapped_chat_agent`: failed-state now `retryable=True` + a message telling the LLM to read log_excerpt (SyntaxError / "RUFF FAILED" + [Ruff] findings), rewrite the script (in full if truncated), call the SAME tool again, and loop until syntax OK + Ruff clean + exit 0; never re-send identical. Generic to ALL wrapped agents.

**Loop is end-to-end:** Pythonxer exits non-zero → `chat_agent_runtime.reconcile_chat_agent_run` (pre-existing, ~line 383) maps non-zero → status="failed" + forwards `log_excerpt` (tail w/ the gate banner + [Ruff] findings) → tools.py message drives fix+retry. Multi-Turn repetition breaker blocks IDENTICAL re-sends → only a corrected script proceeds.

**Verified HARD hermetically** (real pythonxer.py as a subprocess, isolated `pythonxer/` dir so log=pythonxer.log, config via yaml.safe_dump, no windows): a) syntax-broken→exit1, syntax gate, not executed; b) valid+ruffFAIL(strict)→exit1, ruff gate, not executed; c) clean→exit0, executed; d) valid+ruffFAIL with ruff_blocking=false→exit1, ruff did NOT block, executed (advisory escape works). ruff clean.

**Caveats:** canvas Pythonxer is strict-by-default now (set node `ruff_blocking:false` for advisory). prompt.pmt NOT edited (the tools.py failed message + repetition breaker drive the loop). Decisive proof = a live Multi-Turn run; frozen c:\Tlamatini needs `python build.py`. Recorded in repo PIVOT_CHANGES.md.

**UPDATE 2026-05-29 (same day, two follow-ups):**
1. **Downstream is now ALWAYS triggered.** Per explicit user demand ("MUST ALWAYS ALWAYS NO MATTER WHAT: STARTUP THE AGENTS CONNECTED TO ITS OUTPUT"), `main()` triggers `target_agents` UNCONDITIONALLY — success, Ruff/syntax gate refusal, OR runtime failure. The documented "exit-code != 0 → skip downstream" Pythonxer primitive is intentionally DROPPED; downstream agents do any validation the user wires. Exit code (0/1) still drives the LED + chat retry loop but NEVER gates downstream. Errors are always logged. (Chat loop intact: chat wrapped runs have empty target_agents, so the always-trigger is a no-op there; exit 1 still → status=failed → LLM retry.) FLAGGED: this contradicts agentic_skill.md/README "exit code gating" docs — FlowCreator docs need updating (not yet done).
2. **Ruff forced present:** `requirements.txt` has `ruff==0.14.5` (+REQUIRED comment); `build.py` now runs `[target_python,'-m','ruff','--version']` for BOTH the build python AND PYTHON_HOME python and ABORTS the build if Ruff isn't runnable → guarantees Ruff in frozen + non-frozen, every OS (OS-agnostic command). Runtime fallback: validate_with_ruff fails OPEN if Ruff absent, compile() floor still enforces syntax.
