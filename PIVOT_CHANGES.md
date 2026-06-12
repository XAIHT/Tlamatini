# Tlamatini — Change Pivot / Rollback Log

A dated, append-only log of surgical changes with the verbatim request and the
exact before/after, so any single change can be rolled back precisely without
relying on git diffs.

(Fresh start 2026-05-29: the previous follow-up #1–#7 "external-exec hardening"
series was discarded by the user — "nothing you did worked" — and this file was
removed with it. It now begins clean with only the change that survived a real,
evidence-backed diagnosis.)

---

## 2026-05-29 — Pythonxer ALWAYS triggers its downstream/output agents (no dead-end), ALWAYS reports errors

### Verbatim user request
- "Change Pythonxer to always trigger the downstrean agent wether fail by ruff or runtime! ... the
  agents in the output of Pythonxer must check if Pythonxer run ok (it depends on the user if put
  something to validate...) but the important Pythonxer **MUST ALWAYS ALWAYS REPPORT THE ERRORS,
  AND ALWYAS ALWAYS ALWAYS NO MATTER WHAT: IT MUST STARTUP THE AGENTS CONNECTED TO ITS OUTPUT!**"
  (preceded by a narrower "log + trigger on ruff failure" request, then widened to ALL outcomes.)

### Change (`agent/agents/pythonxer/pythonxer.py` + `config.yaml`)
- `main()` now triggers `target_agents` UNCONDITIONALLY — on success, Ruff/syntax gate refusal,
  AND runtime failure. Removed the old `if script_result:` gate around the downstream-trigger loop
  (the documented "exit code != 0 → skip downstream" behaviour is intentionally dropped for
  Pythonxer per the user: downstream agents do any result-checking the user wires).
- Errors are ALWAYS logged (the syntax/Ruff gate banners + [Ruff] findings + stderr already log;
  the FALSE result line now says "(errors are logged above)").
- Exit code is unchanged (`0 success / 1 any failure`) — it still drives the LED and the Multi-Turn
  chat fix→re-ruff→retry loop, but NO LONGER gates whether downstream agents start.
- An interim `_GATE_BLOCKED` flag (added to trigger downstream only on gate failures) was removed
  again once the requirement widened to "always" — no leftover cruft.
- `config.yaml` BEHAVIOR header rewritten: steps 4-5 now say "ALWAYS trigger downstream NO MATTER
  WHAT; exit code drives LED/retry only, never gates downstream."

### Verification (hermetic — real pythonxer.py as a subprocess, target_agents=['dummy_1'], no windows)
ruff clean. All four outcomes → `downstream_triggered=True` + error/result reported:
- a) syntax-broken → exit 1, downstream triggered.
- b) Ruff-fail     → exit 1, downstream triggered.
- c) clean         → exit 0, downstream triggered.
- d) runtime-fail  → exit 1, downstream triggered.

### Caveat / follow-up (FLAGGED, not done)
This changes a DOCUMENTED Pythonxer primitive ("exit-code gates downstream"). `agentic_skill.md`
(FlowCreator's reference) and `README.md` still describe the old gating → FlowCreator may design
flows assuming downstream is skipped on failure. Recommend updating those docs + the agents
catalog to "Pythonxer always triggers downstream; validate via a downstream agent." Awaiting OK.

### Rollback
Restore the `if script_result:` guard around the downstream-trigger loop in `main()` and the old
config.yaml BEHAVIOR steps 4-5.

---

## 2026-05-29 — Force Ruff to ALWAYS be present (build.py verification + requirements.txt)

### Verbatim user requests
- "Now, make a verification in build.py and in requirements.txt in order to make DAMN SURE RUFF
  WILL ALWAYS BE PRESENT IN FROZEN AND NOT FROZEN MODES! PLEASE!."
- "And continue checking the alwways forcefully prescence of Ruff in every mode of operation in
  every SO, in every every!"

### Findings
`ruff==0.14.5` was already in requirements.txt; build.py already installs requirements.txt into
BOTH the build Python and the PYTHON_HOME (frozen-agent) Python and has a post-install import
verify — but Ruff was NOT in that verify, so a broken/missing Ruff install could ship silently and
the strict gate would fail open. Frozen Pythonxer runs Ruff via the PYTHON_HOME python
(`get_python_command`), so Ruff must live there.

### Changes
- `requirements.txt`: added a REQUIRED comment above `ruff==0.14.5` (do-not-remove; the gate needs it).
- `build.py`: after the agent-libs import verify, added a dedicated check that runs the EXACT
  invocation the agent uses — `[target_python, "-m", "ruff", "--version"]` — and `sys.exit(1)`
  (aborts the build) if it fails. The enclosing loop runs for BOTH the build Python AND the
  PYTHON_HOME Python, so a green build guarantees Ruff in frozen AND non-frozen modes. The command
  form is OS-agnostic (works on every OS the build runs on). Runtime fallback unchanged: if Ruff is
  ever absent at runtime, `validate_with_ruff` fails OPEN and the compile() syntax floor still runs.

### Verification
`build.py` compiles (py_compile OK); `python -m ruff --version` → `ruff 0.14.5` (exit 0) — the exact
command the new check runs.

### Rollback
`build.py`: remove the `-m ruff --version` verification block. `requirements.txt`: remove the comment
(keep the `ruff==0.14.5` pin).

---

## 2026-05-29 — STRICT Pythonxer correctness gate + LLM fix→re-ruff→retry loop

### Verbatim user requests
- "Claude check that ruff implementation along the code really help to detect if the code is
  right before starting the Pythonxer agent at all, and the LLM must recodify the program and
  then re-ruff and then if agin wrong then make the program again and then re-ruff up to having a
  python script correct!"
- "Strict"

### Check finding (the gap)
At HEAD (after the #1–#7 discard) Pythonxer ran Ruff but IGNORED it — `# Validate with Ruff
(non-blocking)` / `validate_with_ruff(script_path)` with the return value discarded — so a
wrong script ran anyway; there was no compile() floor; and a failed wrapped run told the LLM
`retryable=False, "inspect the log"` (give up). Empirically confirmed Ruff itself works
(detects invalid-syntax + F401/F821, exit 1) and is installed.

### Files changed (production) — re-adds ONLY the ruff-gate + retry-loop subset of the discarded
work; deliberately NOT the discarded containment / watcher / executer mirror.

**1. `agent/agents/pythonxer/pythonxer.py`**
- New module global `_RUFF_BLOCKING = True`.
- `execute_python_script` now runs a STRICT gate BEFORE any execution:
  - (1) `compile(script_content, script_path, "exec")` syntax floor — `SyntaxError` → log the
    error (line/col/snippet) + `return False`, never executes. Works even if Ruff is absent.
  - (2) `ruff_ok = validate_with_ruff(...)`; `if _RUFF_BLOCKING and not ruff_ok:` → log
    `⛔ RUFF FAILED - refusing to execute` + `return False`. (Ruff absent/timeout fails open.)
  - BEFORE was just `validate_with_ruff(script_path)` (return ignored, "non-blocking").
- `main()` reads `_RUFF_BLOCKING = bool(config.get('ruff_blocking', True))` + logs it.
- `validate_with_ruff` line wording: "proceeding anyway" → "see [Ruff] findings above".

**2. `agent/agents/pythonxer/config.yaml`** — added `ruff_blocking: true` (with comment) +
rewrote the BEHAVIOR header to describe the strict parse→ruff→run gate.

**3. `agent/tools.py` `_launch_wrapped_chat_agent`** — failed-state (generic to ALL wrapped
agents) BEFORE: `"finished with a failure state. Inspect the log excerpt."` + `retryable=False`.
AFTER: instructs the LLM to read `log_excerpt` (SyntaxError / "RUFF FAILED" + [Ruff] findings /
traceback), REWRITE the script (in full if truncated), call the SAME tool again, and repeat
fix→re-run→re-check until it passes (syntax OK + Ruff clean + exit 0); never re-send identical;
don't report failure until a corrected retry was attempted. `retryable=True`.

### Why this closes the loop end-to-end
Pythonxer exits non-zero on a bad script → `chat_agent_runtime.reconcile_chat_agent_run`
(pre-existing, line 383) maps non-zero → `status="failed"` and forwards `log_excerpt` (tail of
the agent log, which now carries the SYNTAX/RUFF banner + [Ruff] findings) → tools.py failed-state
tells the LLM to fix & retry. The Multi-Turn repetition breaker blocks IDENTICAL re-sends, so only
a CORRECTED script proceeds — naturally enforcing "remake the program", not "re-send the same".

### Verification (HARD hermetic test — real pythonxer.py as a subprocess, no windows)
ruff clean (pythonxer.py + tools.py). Drove the real agent in an isolated `pythonxer/` dir
(log = `pythonxer.log`), config built via `yaml.safe_dump`:
- a) syntax-broken (strict)    → exit 1, syntax gate fired, NOT executed.
- b) valid + Ruff-fail (strict) → exit 1, RUFF gate fired, NOT executed (compile passed, ruff blocked).
- c) clean (strict)            → exit 0, executed.
- d) valid + Ruff-fail, ruff_blocking=false → exit 1, ruff did NOT block, executed (advisory escape works).

### NOT done / notes
- prompt.pmt was deliberately NOT edited — the tools.py failed-state message (returned to the LLM
  on every failed call) + the repetition breaker drive the loop. Can add a prompt rule if a
  stronger nudge is wanted.
- Canvas Pythonxer is now strict-by-default too (a lint-failing node refuses to run); set
  `ruff_blocking: false` in the node config for the old advisory behaviour.
- Decisive proof is a live Multi-Turn run; frozen `c:\Tlamatini` needs `python build.py`.

### Rollback
`pythonxer.py`: remove `_RUFF_BLOCKING`, the compile()+ruff gate block (restore the single
`validate_with_ruff(script_path)`), the `main()` flag read, and the wording change.
`config.yaml`: remove `ruff_blocking` + restore the old BEHAVIOR header.
`tools.py`: restore the failed-state message + `retryable=False`.

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

---

## 2026-06-12 — `copy_source_assets.py`: generated self-modify source snapshot (build.py --self-modify)

### Verbatim user request
- "make a deep analysis of all of the assets to be neccessary to be included into the source code
  directory of Tlamatini 'C:<installed-dir usually 'Tlamatini'>\TlamatiniSourceCode' when it is
  build throgh build.py script option --self-modify, once finished then create an auxiliary script
  named 'copy_source_assets.py' to be run from build.py, the main goal is to provide the runtime
  with **all the source code assets neccesary** including from the bulding script, all of the
  .pss1 files, etc. to the last .py, .css, .js, (all of the source Tlamaitni may need to modify),
  and omiting the .pdf, .pptx, and all of the images, video files from images directory (ommit the
  files that may be repeated and allready in the Tlamatini's installed directory tree), this
  source is aimed to be the codebase to be taken->modified->integrate->regenerate-the-building-
  Tlamatini.exe: to be executed completely by Tlamatini if the prompt of the user may instruct
  Tlamatini to be modified in any funcionality and regenerate itself."

### Change
- NEW `copy_source_assets.py` (repo root): walks the repo and builds a complete, rebuildable
  source snapshot. Denylist approach (unknown future text types are included by default):
  EXCLUDES media (.pdf/.pptx/.png/.jpg/.gif/.mp4/...), jd-cli.jar, archives/exes, secrets
  (data.keys, db.sqlite3, settings.local.json, key/cookie/crumb), generated state (_version.py,
  *.version.txt, .build.lock, *.log/.pos/.session), derived trees (.git, __pycache__,
  node_modules, venv, build/, dist/, staticfiles/, agents/pools/, Temp/, Templates/,
  TlamatiniSourceCode itself). KEEPS build-required small binaries: *.ico, *.wav, *.svg.
  Secret REDACTION (regen_secrets "<KEY goes here>" style) for agent/config.json (JSON deep-walk)
  + agents/*/config.yaml (line regex; never touches max_tokens/sample_rate-style keys).
  Writes `_SOURCE_SNAPSHOT_MANIFEST.json` + `_REBUILD_INSTRUCTIONS.md` (restore jd-cli.jar +
  XAIHT-Tlamatini.mp4 + live config.json from the install root, collectstatic, then
  `python build.py --self-modify`).
- `build.py` (self_modify branch, ~line 1022): BEFORE = copytree of the static placeholder tree
  `Tlamatini/agent/TlamatiniSourceCode` (README-only) into dist/manage. AFTER = imports
  copy_source_assets and GENERATES the snapshot fresh into `dist/manage/TlamatiniSourceCode`;
  on any exception falls back to the legacy static-tree copy verbatim.

### Rollback
- Delete `copy_source_assets.py`; in build.py restore the old 11-line `if self_modify:` block
  (the fallback branch inside the new block IS that old code, verbatim).

### Verification
- Live run to Temp scratch: 685 files / 9.84 MB / 0 errors; build assets present (build.py,
  all 5 .ps1, .ico, .wav, prompt.pmt, jd-cli.bat, pyinstaller_hooks); zero
  .png/.jpg/.mp4/.pdf/.pptx/.jar/db.sqlite3/data.keys in output; config.json placeholders intact.
- Unit checks: JSON+YAML redactors scrub live-style keys, leave max_tokens/sample_rate alone.
- `ruff check` + `py_compile` clean on both files.

---

## 2026-06-12 — Documentation sweep for copy_source_assets.py (incl. prompt.pmt + Tlamatini.md)

### Verbatim user request
- "please update all of the markdown documentation to include the last improvement about a new
  script to include all of the source code into the location TlamatiniSourceCode, make sure all of
  your skills and assets (Claude) in general contains the description or indications to include
  the new feature, go!"

### Files updated (besides the four already updated in the prior entry: CLAUDE.md,
### docs/claude/architecture.md, docs/claude/gotchas.md, PIVOT_CHANGES.md)
- `README.md` — 4 spots: features table (L56), §1 "Self-aware" bullet (L270), §7.2 self-modify
  build paragraph (full rewrite describing generation + contents + omissions + rebuild runbook),
  §9.6 self-modification paragraph (generation + take→modify→integrate→regenerate runbook).
- `BookOfTlamatini.md` — new top "Recent Updates" entry: "The Self-Modify Snapshot Grows Teeth —
  copy_source_assets.py Generates a Complete, Rebuildable Source Tree — 2026-06-12".
- `KIMI.md` §30.2 + §30.3 table — generation via copy_source_assets.py + new table row.
- `docs/claude/INDEX.md` — architecture.md line now mentions the generated snapshot.
- `docs/claude/recent-fixes.md` — NEW top entry "2026-06-12 — build.py --self-modify now GENERATES
  the TlamatiniSourceCode snapshot via copy_source_assets.py — do NOT revert to the static
  copytree" (denylist contract, kept binaries, RESTORE_FROM_INSTALL, redaction suffix-match,
  recursion guard).
- `.claude/skills/tlamatini-agent-creation/SKILL.md` — new Phase-21 step **382b** (when a new
  agent must touch EXCLUDED_EXTENSIONS / RESTORE_FROM_INSTALL / _SECRET_KEY_RE).
- `Tlamatini/agent/Tlamatini.md` — §2 second-capability-axis bullet AND §9 first bullet extended
  (snapshot contents); NEW §9 bullet "You can REBUILD yourself from that snapshot" (follow
  _REBUILD_INSTRUCTIONS.md: restore jd-cli.jar + demo video + live keys from install root,
  pip install, collectstatic, `python build.py --self-modify`; ~18 min; .build.lock guard).

### prompt.pmt change (identity rules, the TlamatiniSourceCode bullet)
- BEFORE (single sentence in the middle of the bullet): "If it exists, you are a
  **self-able-modify** version — you may read it to inspect your own implementation and to plan
  or apply changes to yourself." ... and the closing clause read "...before claiming you can read
  or edit your own code".
- AFTER: same bullet, with the middle expanded to: "If it exists, you are a **self-able-modify**
  version — it is a COMPLETE, rebuildable source snapshot (generated by `copy_source_assets.py`
  at build time: all source + build scripts; heavy media and secrets omitted, config keys shown
  as `<KEY goes here>` placeholders). You may read it to inspect your own implementation, apply
  changes to yourself, and — when the user asks you to modify your own functionality and
  regenerate yourself — **rebuild your own `Tlamatini.exe`** by following
  `TlamatiniSourceCode/_REBUILD_INSTRUCTIONS.md` exactly (restore the omitted binaries and live
  keys from your install root per `_SOURCE_SNAPSHOT_MANIFEST.json`, then run
  `python build.py --self-modify`)." — and the closing clause now reads "...before claiming you
  can read, edit, or rebuild your own code". Everything else in the bullet is byte-identical.

### Rollback
- prompt.pmt: restore the BEFORE sentence + closing clause above (single bullet, line ~12).
- All other files: remove the quoted additions; they are additive (no existing text deleted
  except the sentences quoted as BEFORE in this and the prior entry).
