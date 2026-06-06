---
name: feedback_dont_overbuild_exec_safety
description: "The whole multi-day external-exec safety hardening (gates/containment/_run_bounded/watcher daemon) was discarded by the user as not-working — don't rebuild it; prove the real fix on a running instance first"
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 1e984263-7cb7-4f48-a806-931aeb417374
---

2026-05-29: The user discarded the ENTIRE ~2-day external-exec hardening series in one `git discard` — "nothing you did worked." That series = [[project_pythonxer_forkbomb_fix]] + [[project_external_exec_safety_layer]] (7 follow-ups logged in PIVOT_CHANGES.md): blocking `compile()` syntax gate, blocking Ruff, Windows Job-Object containment, `_run_bounded`/`_kill_process_tree` anti-freeze, and the f/u#7 `_watch_script_completion`/`_kill_script_window_remnants` watcher daemon.

**Why it was rejected:** it passed its own tests but did NOT fix the real live symptom — `start "" cmd /k python file.py` still hung Tlamatini and still returned a false "OK". The tests used stand-ins (`ping`) that never reproduced the actual detached-`cmd /k` console, so green tests gave false confidence. The work was also over-built (heuristic process-name + path-match killing daemons) relative to the problem.

**How to apply:**
1. Do NOT reconstruct or re-propose that safety layer. The PIVOT_CHANGES.md entries for it describe discarded code.
2. The underlying incidents are still real (fork-bomb window flood needing a machine restart; the cat-art.py SyntaxError window; chat hanging on a popped console). But the fix has to be PROVEN on a running instance against the REAL failing construct before it's worth keeping — not validated by a `ping`-stand-in test.
3. Aligns with [[feedback_hard_real_scenario_tests]]: a test that doesn't reproduce the actual incident byte-faithfully is worthless here. And with the user's "don't fuck more Tlamatini, she was working somehow stable" — prefer the smallest change that demonstrably fixes the live behavior, likely PROMPT STEERING (keep the model off `start cmd /k python`) over runtime process-killing machinery.
4. When in doubt about whether something "works," the user is the source of truth — he watches it live; my passing tests are not proof.
