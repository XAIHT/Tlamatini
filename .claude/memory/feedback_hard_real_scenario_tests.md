---
name: feedback_hard_real_scenario_tests
description: "User demands HARD, real-scenario automated tests — soft happy-path tests are unacceptable"
metadata: 
  node_type: memory
  type: feedback
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

When asked for automated tests, the user wants them HARD and REAL: cover **with-errors AND without-errors AND overflows** (fork-bomb / mass-spawn / huge-output), drive the REAL code (run the actual agent as a subprocess / call the real functions — do NOT mock the thing under test), and reproduce the ACTUAL incident byte-faithfully (e.g. the truncated `cat-art.py` ending in an unterminated f-string). Verbatim: "make the testing harder, cause your test usually dont catch real scenarios, work harder, till beyond excelence, beyond perfection, beyond god."

**Why:** soft happy-path tests pass while real bugs ship. Proof it works: the hard suite in `test_external_exec_safety.py` immediately caught a REAL bug a soft test never would — a child printing 🐱 crashed with `UnicodeEncodeError` (cp1252 captured pipe on Windows) until `PYTHONIOENCODING=utf-8` + `env=get_agent_env()` were forced on the exec child of both Executer and Pythonxer.

**How to apply:** include negative cases (must refuse + NO window/wrapper written), positive cases (must run, no false positives), unicode/emoji output, huge-valid vs huge-broken, pipe-buffer-overflow (>256 KB stdout+stderr → no deadlock), and Windows Job-Object containment (mass-spawn → cap rejects some + KILL_ON_JOB_CLOSE → psutil-verified zero survivors). Probe extractor weak spots (`python3.12 x.py`, `.pyw`, `py -3`, `start cmd /k`, chained `&&`, quoted paths) AND the must-NOT-fire forms (`-m`/`-c`/non-python/nonexistent/valid-but-runtime-error). Where a test exposes a real gap, FIX the code so it passes (true TDD). Mirror the hermetic-subprocess convention of `test_pythonxer_agent.py`. See [[project_pythonxer_forkbomb_fix]] and [[feedback_track_changes_pivot_file]].
