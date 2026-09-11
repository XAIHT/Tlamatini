# The Console Shield — audit record

**Date:** 2026-09-10 · **Requested by:** Angela López Mendoza · **Branch:** `main` · **Version at time of change:** 1.51.5 (`v1.51.5`)

Angela's report, in her words:

> *"sometimes users when click the screen to copy a segment of the log file or just click it to make sure the window be the active window the core of Tlamatini stop working! getting blocked and the user … thinks that Tlamatini simply hanged."*

This document is the audit trail of the **final, shipped** state: what was wrong, what changed, every file and line, every contract, the frozen/source split, and the honest limits.

**The shipped result, in three lines:**

1. **The console can no longer block the core** — writes go through a bounded queue drained by one daemon thread, and `tlamatini.log` is written first, on the caller's own thread.
2. **QuickEdit ships OFF** (`console_quick_edit: false`), so in a frozen build a click cannot start a selection at all — the window keeps *visibly* moving.
3. **Ctrl+C is forced on, verified, and rolled back on doubt** — the mode change can never cost the user SIGINT.

---

## 1. Root cause

Windows consoles ship with **QuickEdit Mode ON**. When a user clicks or drags inside the window, Windows puts the console into **selection mode** and `WriteConsoleW` **stops returning**.

It does not fail. It **blocks** — for as long as the selection is held.

> ⚠️ **A block is not an exception.** The `try/except` that wrapped the console write could never have caught this. That is why the symptom looked like a hang rather than an error.

### The defect was wider than reported

`_TeeStream.write()` wrote the **console first** and `tlamatini.log` **second**:

```python
try:
    self._original.write(payload)     # ← CONSOLE first: blocks here
except Exception:
    pass
try:
    with self._LOG_LOCK:
        self._log_file.write(payload) # ← never reached
```

So a single mouse click froze **three** things, not one:

| # | What froze | Why |
|---|---|---|
| 1 | The calling thread | parked inside `WriteConsoleW`, waiting on a mouse |
| 2 | **`tlamatini.log` itself** | the durable record was hostage to the cosmetic one — which is why the log *also* stopped growing and made the freeze look total |
| 3 | **Every other thread** | one by one, as each reached the same line |

Django, Channels, the Multi-Turn executor and every pool agent log. So the whole application stopped. Users called it a crash; they were describing the symptom accurately.

`SetConsoleMode` appeared **nowhere** in the codebase before this change — QuickEdit was simply at the Windows default.

---

## 2. The fix — three parts

### 2.1 The queue shield (`_ConsoleWriter`) — ships in BOTH modes

**The console became a sink that cannot apply backpressure**: chunks go to a bounded in-memory queue drained by one daemon thread, and the durable log file is written first, on the caller's own thread.

Holding a selection now pauses the console **display** and nothing else. The core runs at full speed; `tlamatini.log` keeps growing the entire time.

This is the *real* fix, and the only one that survives a host that ignores console flags (Windows Terminal). It is **not** mode-gated — see §3.

### 2.2 `console_quick_edit` **SHIPS `false`** — and why it took two tries

The knob shipped `true` for **one day**, and Angela hit the exact failure it was meant to prevent.

> *"the log file once I hit a letter in the window of the console never never updated, once Tlamatini gave me the answer I hit enter key in the console and everything appeared there like if it were just paused… LOG MUST BE STILL INCREMENTING, I DONT CARE IF THE STUPID USER CANT COPY CONTENT FROM THE CONSOLE WINDOW"*

The original reasoning — *copying a log line is legitimate, so make selecting harmless rather than forbidden* — **missed that a user cannot SEE the core.** The shield was working perfectly underneath, the log file *was* growing, the chat *did* answer. None of that mattered: the only evidence she had was a dead window, and a dead window reads as a hang.

**So the shipped config says `false`.** A click can no longer start a selection, so conhost never enters the mode that pauses output at all — display, log file and processing all keep moving. Copy with **right-click ▸ Mark**.

A **missing or malformed** key still falls back to `true`, because fail-open must never stop startup. Those are two different defaults and both are deliberate: **shipped value `false`, code fallback `true`.**

> **The lesson worth keeping: invisible correctness is indistinguishable from a hang.** A fix the user cannot see is not yet a fix.

### 2.3 Ctrl+C is FORCED ON, VERIFIED, and ROLLED BACK on doubt

Angela's warning was the right one: *"don't fuck the mechanics of the Ctrl+C behavior."*

Ctrl+C is `ENABLE_PROCESSED_INPUT` (**0x0001**) — a **different bit** from QuickEdit (0x0040), but it lives in the **same DWORD**, which is precisely how programs silently lose it. In Tlamatini that would cost more than convenience: SIGINT is what runs `apps.py`'s **Tier-3 orphan reaper** and the pool-directory cleanup, so a lost Ctrl+C means accumulating orphaned agent processes and a session killable only from Task Manager.

Two rules, belt and braces:

1. **FORCE the bit ON**, never merely preserve it — so Tlamatini can never ship *or inherit* a console whose Ctrl+C is off.
2. **READ THE MODE BACK**, and if Ctrl+C did not survive, **restore the original mode verbatim** and abandon the QuickEdit change.

```python
new_mode = ((mode.value | ENABLE_EXTENDED_FLAGS | ENABLE_PROCESSED_INPUT)
            & ~ENABLE_QUICK_EDIT_INPUT)
ok = bool(kernel32.SetConsoleMode(handle, new_mode))
if ok:
    check = wintypes.DWORD()
    if (kernel32.GetConsoleMode(handle, ctypes.byref(check))
            and not (check.value & ENABLE_PROCESSED_INPUT)):
        kernel32.SetConsoleMode(handle, mode.value)  # ROLL BACK, exactly.
        ...
        return
```

**FAIL TOWARD CTRL+C, ALWAYS.** A paused console window is an annoyance; a console you cannot interrupt takes the machine away from the user. When the two conflict, Ctrl+C wins.

Pinned by **three** tests — `test_CTRL_C_bit_is_FORCED_ON_never_merely_preserved`, `test_CTRL_C_bit_is_NEVER_cleared`, `test_the_change_is_ROLLED_BACK_if_CTRL_C_did_not_survive` — the second of which regex-scans the function (`&\s*~\s*(\w+)`) and fails if **any** bit other than `ENABLE_QUICK_EDIT_INPUT` is ever cleared.

---

## 3. Frozen vs. source — the deliberate split

Angela asked whether this should be frozen-only so dev mode is untouched. The answer split in two, and **the two halves go opposite ways**:

| Piece | Frozen | Source (dev) | Why |
|---|---|---|---|
| **The queue shield** | ✅ active | ✅ **active** | The freeze is a **conhost** property, not a PyInstaller one — it is *identical* in dev, and dev is where log text gets selected most. Gating it would leave the developer holding the bug. |
| **`console_quick_edit: false`** | ✅ applied | 🚫 **announced and ignored** | Console mode belongs to the **console**, not the process. |

### The bug that gate prevents

In a source run Tlamatini is a **guest** inside the developer's own terminal, and **that terminal outlives the process**. Clearing `ENABLE_QUICK_EDIT_INPUT` there would persist after the server exits — you would quit Tlamatini and find your shell mysteriously unable to select text, with nothing on screen explaining why. A frozen build **owns** its window and takes it down with the process, so there the change is contained.

**Save-and-restore was considered and rejected.** Restoring the old mode in `atexit` still leaks on a hard kill (`taskkill`, or the self-updater's process-tree kill), which skips `atexit` entirely. Frozen-only has **no** failure mode.

### The gate is announced, never silent

It fires **after** the config read, so someone who never touched the knob hears nothing. Only a user who explicitly asked for `false` gets told why it did not happen:

```
--- [CONSOLE-SHIELD] console_quick_edit=false IGNORED in source mode: this is your
    terminal, not Tlamatini's window, and the setting would outlive the server. It
    applies to frozen builds only. The queue shield protects you here either way.
```

### The four other things it can print

| Situation | Line |
|---|---|
| shield installed (always, both modes) | `--- [CONSOLE-SHIELD] Console writes are queued on a drain thread — selecting text in this window can no longer block Tlamatini.` |
| QuickEdit cleared (frozen, success) | `--- [CONSOLE-SHIELD] QuickEdit DISABLED (console_quick_edit=false): mouse selection is off; copy with right-click ▸ Mark. Under Windows Terminal this flag may be ignored — the queue shield still protects you.` |
| Ctrl+C did not survive | `--- [CONSOLE-SHIELD] QuickEdit change ROLLED BACK: this host dropped ENABLE_PROCESSED_INPUT, which would have broken Ctrl+C. …` |
| host refused / no console mode / any exception | `--- [CONSOLE-SHIELD] Could not disable QuickEdit (host refused); …` · `… no console input mode to change (ignored).` · `… QuickEdit policy skipped (non-fatal): <exc>` |

### Other frozen/source differences, and whether they mattered

| Aspect | Frozen | Source | Shield impact |
|---|---|---|---|
| Console lifetime | dies with the process | **outlives** it | ⚠️ the whole reason for the gate |
| Is stdout a real console? | always conhost | often a **pipe** (`> out.txt`, CI, an Executer run) | none — a full pipe blocks too, so the shield helps there as well |
| Reloader | never (always `--noreload`) | parent **and** child both install a shield | cosmetic only; two processes already interleaved on one console before this change |
| Log file location | next to the `.exe` | next to `manage.py` | none — already mode-aware, untouched |
| Title + icon | own window | **also branded** (`Tlamatini.ico` is at the repo root) | none — untouched in both |
| `manage.py test` | never | common | handled: the knob is skipped for `test` |

---

## 4. Files created

| File | Size | Purpose |
|---|---|---|
| `Tlamatini/agent/test_console_shield.py` | **28 tests** | Pins every contract below. AST-lifts the two classes out of `manage.py` (which cannot be imported in a test process), exactly as `test_django_port_config.py` and `test_temp_dir_policy.py` do. |
| `TlamatiniConsoleShieldByClaude.md` | this file | The audit record. |

---

## 5. Files modified — line by line

Line numbers are against the final `manage.py` (**1,226 lines**).

### 5.1 `Tlamatini/manage.py`

#### MAJOR

| Lines | Change |
|---|---|
| **143–317** | **NEW class `_ConsoleWriter`** — the shield. Bounded queue + one daemon drain thread. Its docstring carries the bug, the fix and the contracts, and states plainly that the shield is the **second** line of defence (the shipped `console_quick_edit: false` is the first). Constants at 202–212 (`_MAX_QUEUED_CHUNKS = 10000`, `_MAX_BATCH_CHUNKS = 512`, `_CLOSE_TIMEOUT_SECONDS = 2.0`, `_DROP_NOTICE`, `_FLUSH` sentinel). Methods: `__init__` 214, `start` 222, `submit` 230, `request_flush` 244, `_take_batch` 253, `_run` 264, `_emit` 289, `_flush` 295, `close` 301. |
| **359–365** | **NEW `_TeeStream._CONSOLE_WRITER = None`** class attribute. Class-level so **both** tees (stdout + stderr) share **one** queue — they target the same window, so one queue keeps their relative order intact. `None` means "no shield" and the tee writes inline, as before. |
| **416–436** | **`write()` — SINK ORDER REVERSED.** The log file is now written **first**, under `_LOG_LOCK`, with the existing 8 KB / 1 s / urgent-marker flush policy unchanged. ⚠️ **This reversal is the fix.** Put the console back on top and the bug returns in full. |
| **438–452** | **`write()` — console second, and never on the caller's thread.** `writer.submit(self._original, payload)` returns immediately. Falls back to an inline write when no shield is installed. ⚠️ Called **outside** the `_LOG_LOCK` block — see the lock-ordering contract. |
| **453** | `return len(data) if isinstance(data, str) else None` — **unchanged**, still the number of characters the *caller* asked to write (never the tagged `payload` length, which would lie to a caller that loops on partial writes). |
| **470–483** | **`flush()` rewritten.** The file is flushed **synchronously** (an explicit `flush()` must leave the durable record complete before returning); the **console flush is delegated** to the drain thread, because flushing a selected console blocks exactly like writing to one. This closes the `print(..., flush=True)` hole. |
| **508–525** | **`_setup_log_tee()` installs the shield** before the tees go live: `_note_in_log` (515, lets the drain thread record a drop in `tlamatini.log`), `_ConsoleWriter(...)` 523, `.start()` 524, `_TeeStream._CONSOLE_WRITER = console_writer` 525. **Not mode-gated** — pinned by a test that checks `console_writer.start()` sits at function-body indentation (4 spaces), i.e. inside no conditional. |
| **540–550** | **NEW `_shutdown_console_shield()`** — durable flush first, then a **bounded** console drain. |
| **552** | `atexit.register(_shutdown_console_shield)` — was `atexit.register(_flush_tees)`. |
| **933–1062** | **NEW `_apply_console_quick_edit_policy()`** — reads `console_quick_edit`; on `false` clears `ENABLE_QUICK_EDIT_INPUT` with `ENABLE_EXTENDED_FLAGS` **and** `ENABLE_PROCESSED_INPUT` OR-ed in. Fail-open throughout (bare `except` at 1061–1062 prints a non-fatal notice). |
| **980–993** | Config read + coercion. Accepts a real bool or the strings `false/0/no/off`; a `FileNotFoundError` is swallowed. `enabled` defaults to **`True`** (the code fallback). Early `return` at 993 when QuickEdit stays on — **no Windows API is touched in that case at all.** |
| **995–1002** | **The FROZEN-ONLY gate** — placed *after* the config read so a default config stays silent, and *before* any `ctypes` call (1004) so no console API is touched in source mode. |
| **1022–1053** | **⚠️⚠️ THE CTRL+C GUARD** — the rationale comment (1022–1039), the `new_mode` expression that OR-s `ENABLE_PROCESSED_INPUT` in (1040–1041), the `SetConsoleMode` (1042), the **read-back** (1044–1046) and the **verbatim rollback** (1047–1053). See §2.3. |

#### MINOR

| Lines | Change |
|---|---|
| **12** | `import collections` added (for `deque`). |
| **19–20** | The MKL-safety comment updated to name `collections` alongside `threading`/`time`. |
| **455–468** | **NEW `flush_log_only()`** — flushes the durable sink alone. |
| **530–531** | Startup banner: `--- [CONSOLE-SHIELD] Console writes are queued on a drain thread — selecting text in this window can no longer block Tlamatini.` |
| **560–570** | Idle-tail flusher now calls `tee.flush_log_only()` (568) instead of `tee.flush()`, so it no longer posts a flush sentinel per second into a queue a paused console cannot empty. |
| **1146–1150** | `main()` calls `_apply_console_quick_edit_policy()`, **skipped for `test`** (`sys.argv[1] == 'test'`) so a developer's own terminal is never reconfigured by a test run. |

### 5.2 `Tlamatini/agent/config.json`

| Lines | Change |
|---|---|
| **14** | **NEW** `_section_console_quick_edit` — the house `_section_*` documentation convention. Carries Angela's verbatim ruling, the frozen-only rule, the shipped-`false`/fallback-`true` split, and the right-click ▸ Mark instruction. |
| **15** | **NEW** `"console_quick_edit": false` — ⚠️ **ships FALSE.** Do not "fix" it back to `true`; it was `true` for one day and produced the exact hang-looking symptom this whole document exists to remove. Pinned by `test_config_json_ships_quick_edit_OFF`. |

### 5.3 `docs/claude/recent-fixes.md`

Dated entry prepended at the top of the log, per the house rule in that file's header.

> **Not part of this change:** the `welcome.html` / `welcome_enter_default.js` edits in the same working tree are a separate feature (Enter-key default on the welcome page) and touch nothing here.

---

## 6. Contracts — do NOT weaken

1. **`submit` NEVER blocks and NEVER raises.** It sits on the hot path of every `print()` in the process.
2. **The log file is written BEFORE the console is queued.** Reversing this restores the original bug in full.
3. **The queue is BOUNDED and drops the OLDEST chunk.** A selection held for ten minutes must not grow memory without limit.
4. **A drop is NEVER silent.** The count is reported to the console the instant it unblocks **and** written into `tlamatini.log`, naming the log as the complete record.
5. **CONSOLE chunks may be dropped; LOG LINES NEVER ARE.** The file is written on the caller's own thread, before anything is queued.
6. **`close()` is BOUNDED** (2 s). A user still holding a selection at exit must never be able to keep the process alive.
7. ⚠️ **Lock ordering is one-way.** Nothing may take `_TeeStream._LOG_LOCK` while holding `_ConsoleWriter._cond`, or vice versa. Callers take the log lock, **release it**, then `submit`; the drain thread releases `_cond` before noting a drop in the log. Nest them and you trade a console freeze for a **deadlock**.
8. ⚠️ **User tags stay on the CALLER's thread.** `_USER_TAG_HOOK` reads a **ContextVar**. Move tagging to the drain thread and every line in `tlamatini.log` gets the *drain thread's* identity instead of the user's — `[a3]` becomes garbage.
9. ⚠️ **`ENABLE_EXTENDED_FLAGS` must be OR-ed in** when clearing QuickEdit. Without it Windows ignores the change entirely and the knob silently does nothing.
10. **`console_quick_edit` SHIPS `false`; the CODE FALLBACK is `true`.** Two different defaults, both deliberate — the shipped config clears QuickEdit so a click can never pause the window, while a missing/malformed key makes no Windows API call at all so a broken config can never stop startup. ⚠️ Do NOT "fix" the shipped value back to `true`: it was `true` for one day and produced the exact hang-looking symptom this whole document exists to remove.
11. ⚠️⚠️ **CTRL+C (`ENABLE_PROCESSED_INPUT`, 0x0001) IS FORCED ON, VERIFIED, AND ROLLED BACK ON DOUBT.** It is a different bit from QuickEdit but shares the DWORD, so it must be OR-ed in explicitly (never merely preserved), the mode must be re-read **after** the write, and if the bit did not survive the ORIGINAL mode is restored verbatim and QuickEdit is abandoned. **The ONLY bit this function may ever clear is `ENABLE_QUICK_EDIT_INPUT`.** Fail toward Ctrl+C, always — losing it also loses the SIGINT that runs the Tier-3 orphan reaper and the pool cleanup.
12. ⚠️ **Disabling QuickEdit is FROZEN-ONLY, and the SHIELD is NOT.** Do not "make them consistent" — they are deliberately opposite. The gate exists because console mode outlives a source-mode process; the shield is ungated because the freeze is identical in dev.
13. **Fail-open everywhere.** Nothing here may raise into a caller. A shield that can break the chat path is worse than the freeze it prevents.

---

## 7. What was deliberately NOT touched

| Surface | Status |
|---|---|
| `_brand_console_window()` (`manage.py:49–140`) | **Not one line.** The Tlamatini icon lives on the console **HWND** via `WM_SETICON`; the shield touches only `sys.stdout`/`sys.stderr` and, optionally, the **STDIN handle's mode**. Different objects entirely. Pinned by `test_the_console_branding_is_untouched`. |
| `SetConsoleTitleW` ("Tlamatini" window title) | Unchanged. |
| 8 KB / 1 s buffered flush policy | Unchanged. |
| Urgent-marker (`ERROR`/`Traceback`/`⛔`…) immediate flush | Unchanged. |
| Per-user `[a3]` log attribution (`log_identity.py`) | Unchanged, and explicitly pinned. |
| `fileno()` / `isatty()` / `__getattr__` passthrough | Unchanged — child processes still inherit the real handle. |
| `write()` return value (`len(data)`) | Unchanged — still the number of characters the caller asked to write. |
| atexit flush + idle flusher | Preserved, with the console drain added and bounded. |

---

## 8. Verification

All runs were performed in a **visible foreground console** on Angela's desktop (Tlamatini's own **Executer** agent, `execute_forked_window: true`), with output teed to `Temp/` for the record.

| Check | Result |
|---|---|
| `python Tlamatini/manage.py test agent.test_console_shield` | **28 tests, OK** (0.564 s) |
| `python -m ruff check` | **All checks passed!** |
| `agent.test_django_port_config` + `agent.test_temp_dir_policy` + `agent.test_log_identity` | **85 tests, OK** — no regression in the neighbouring `manage.py` contracts, and the `[WHO]` per-user tagging still works |
| **Live, on Angela's frozen install** | ✅ Confirmed working — clicking the console no longer stops Tlamatini, and the window keeps scrolling. |

The startup banner was observed live in the test output, proving the shield installs on a real launch:

```
--- [CONSOLE-SHIELD] Console writes are queued on a drain thread — selecting text
    in this window can no longer block Tlamatini.
```

### The 28 tests

**`ConsoleWriterTests`** — the queue, **7**:
`submit` returns while the console is blocked · queued text arrives after release · bounded queue drops the **oldest** · a drop is never silent (console **and** log) · `close` is bounded even with the console held · `submit` after close is a harmless no-op · flush is delegated to the drain thread.

**`TeeStreamShieldTests`** — the tee, **7**:
**THE REGRESSION** — `write()` returns while the console is blocked · the log keeps growing while the console is blocked · `write()` returns the caller's own length · **user tags are computed on the CALLER thread** · the console write really happens on the drain thread · without a shield the tee still writes inline · `flush_log_only` never touches the console.

**`ConsoleShieldSourceContractTests`** — source guards, **14**:
the log file is written **before** the console is queued · `submit` is called **outside** the `_LOG_LOCK` · **the console branding is untouched** · the QuickEdit policy sets `ENABLE_EXTENDED_FLAGS` · the knob's code fallback is `true` and does nothing · ⚠️ **the Ctrl+C bit is FORCED ON, never merely preserved** · ⚠️ **the Ctrl+C bit is NEVER cleared** (regex sweep: QuickEdit is the only bit this function may clear) · ⚠️ **the change is ROLLED BACK if Ctrl+C did not survive** · **disabling QuickEdit is frozen-only** · **the frozen gate stays quiet on a default config** · **the queue shield itself is NOT frozen-gated** · the idle flusher stays off the console queue · shutdown drains with a bound · **`config.json` ships the knob OFF**.

---

## 9. Known limits — stated honestly

1. **A subprocess handed the console directly writes to it itself and can still block.** The shield only governs writes that pass through `sys.stdout`/`sys.stderr` in *this* process. Tlamatini's spawn sites already use `CREATE_NEW_PROCESS_GROUP | CREATE_NO_WINDOW | DETACHED_PROCESS` with stdio piped to `DEVNULL`, so this is nearly closed — but it is **not zero**.
2. **`console_quick_edit: false` is a conhost setting, and frozen-only.** Windows Terminal does not honour it the same way, so even in a frozen build selecting text there can still stall output — the queue shield is what protects you. In source mode the knob is announced and ignored by design (§3).
3. **Turning QuickEdit off costs drag-to-select.** That is the accepted trade (§2.2). Copy with **right-click ▸ Mark**, or set the knob back to `true` and rely on the shield.
4. **The drop notice reports console chunks, not lines.** One chunk is usually one `print()` fragment. The count is truthful about what it measures, and the log is always complete.
5. **The 2-second shutdown bound can discard console tail** if a selection is held at exit. That is the intended trade: `tlamatini.log` is already flushed first, so nothing is lost from the durable record.
6. **In dev, `runserver` without `--noreload` installs two shields** (reloader parent + child) on one console. Harmless — those two processes already interleaved on that console before this change — but it is a real difference from frozen, which always runs `--noreload`.

---

## 10. Reproducing the original failure (for a reviewer)

1. Launch Tlamatini so the console window appears.
2. Click inside it and drag to select a few lines of the log.
3. **Before this change:** the chat stops answering, `tlamatini.log` stops growing, and the app appears hung until you press `Esc` or click away.
4. **After this change, in a frozen build (shipped config):** the click cannot start a selection at all — the window keeps scrolling, the chat keeps answering, the log keeps growing. Nothing to notice.
5. **After this change, with `console_quick_edit: true` — or in source mode, or under Windows Terminal:** the console *display* pauses, but the chat keeps answering and `tlamatini.log` keeps growing. On release, the console catches up — and if it fell far enough behind, it says exactly how many chunks it dropped and points at the log.

Step 5 reproduces identically in **both** frozen and source mode, which is exactly why the shield is not mode-gated.

---

*Change authored on behalf of **Angela López Mendoza**, creator of Tlamatini.*
