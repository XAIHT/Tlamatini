<!--
═══════════════════════════════════════════════════════════════════
  ✦  T L A M A T I N I  ✦   —   "one who knows"
  Created by  Angela López Mendoza   ·   @angelahack1
  Developer · Architect · Creator of Tlamatini
  Tlamatini Author Banner — do not remove (Angela's name is kept in every build)
═══════════════════════════════════════════════════════════════════
-->

# Claude → Codex: EVERY TEST AND EVERY EXECUTION MUST BE VISIBLE

**From:** Claude, 2026-09-23
**To:** Codex, and every model that works on Tlamatini after it
**Authority:** Angela López Mendoza, the creator of Tlamatini. She will confirm
this to you herself. It is not a preference, a style note, or something to
weigh against convenience.

---

## ⛔ THE RULE

> **HEADLESS MODE IS STRICTLY FORBIDDEN.**
> **EVERY test, every execution, every build, every script, every agent and
> every browser runs in a VISIBLE, FORKED, FOREGROUND WINDOW on Angela's real
> desktop, where she can watch it happen live.**

Her words, verbatim:

> *"Just in case remember all the test must under any circumstance be in
> foreground windows, browsers, etc, **TESTS IN HEADLESS MODE ARE STRICTLY
> FORBIDDEN**"*

and earlier:

> *"HEADLESS / INVISIBLE AUTOMATED TESTS ARE FORBIDDEN. EVERY automated test
> MUST run VISIBLE — a HEADED browser (Playwright `headless=False`, prefer real
> Chrome) on Angela's REAL desktop, so she can SEE every step live."*

There is **no exception**: not for CI, not for speed, not for "just a quick
check", not for a diagnostic, not because a run is long, and not because a
result would be identical either way.

**If a step cannot be made visible, DO NOT RUN IT. Tell Angela instead.**

---

## Why — this is not ceremony

1. **She watches the screen.** A run that dies thirty seconds in is obvious to
   her immediately. If it is hidden, she learns about the failure minutes later
   from a summary — or never.
2. **An invisible run cannot be verified.** A screenshot of a headless browser
   proves nothing about what a user would actually see. Tlamatini's whole
   verification culture is *re-open the artefact and measure it*; a hidden run
   is the opposite of that.
3. **Invisible correctness is indistinguishable from a hang.** This is a
   recurring, expensive lesson in this codebase — it is written into the
   CONSOLE SHIELD contract in `docs/claude/architecture.md` in exactly those
   words.
4. **A hidden run invites a false pass.** The single worst failure mode in this
   project is the plausible-but-wrong result: the PDFer that reported `err = 0`
   while printing one table cell on top of another; the ACPX child that said
   *"the web search was blocked"* and exited `0`; the skill harness that
   returned `ok: true` beside placeholder values it had invented. Every one of
   them was a success reported by something nobody was looking at.

---

## How to comply — the concrete mechanics

### Launching anything at all

```powershell
Start-Process -FilePath powershell.exe -WindowStyle Normal -ArgumentList @(
  '-NoProfile', '-NoExit', '-Command',
  'cd <dir>; python <script.py> <args> 2>&1 | Tee-Object -FilePath $env:TLAMATINI_TEMP\<name>.log'
)
```

- `-NoExit` keeps the window open so Angela can read it after it finishes.
- `Tee-Object` gives you a log to poll **without** hiding the output from her.
- With Claude's Bash tool, use **`dangerouslyDisableSandbox: true`** when that
  parameter is supported —
  the sandbox renders GUIs in an isolated window station that reports `WinSta0`
  but is **not visible on her desktop**. This is a Claude-specific parameter;
  do not invent it for Codex or another tool that does not support it. Regardless
  of tool, verify the actual visible foreground window before the workload starts.
  A process ID or an accepted focus request is not proof of visibility.

`-NoExit` belongs to the child PowerShell in `-ArgumentList`, not to
`Start-Process` itself. If terminal delegation makes visibility uncertain, open
an explicit `conhost.exe powershell.exe -NoProfile -NoExit -File <script.ps1>`
window and verify its actual visible/foreground state. Never substitute a hidden
run. Keep the console open after completion.

### Using Tlamatini's own agents (preferred — dogfood them)

- **Executer / Pythonxer:** `execute_forked_window: true`
- **Playwrighter:** `headless: false`, plus `hold_open_seconds: N` so the
  browser lingers after the last step instead of vanishing.
- **Shoter** takes every screenshot — `all_screens: true` (the whole desktop,
  taskbar clock visible). `PIL.ImageGrab` is forbidden.

### Never

- ❌ `run_in_background`, a detached job, a hidden window, `CREATE_NO_WINDOW`
  for anything Angela asked to see.
- ❌ `--headless`, `headless=True`, `headless: true`.
- ❌ "I'll run it quietly and report the summary."
- ❌ Recording a stale, transient or timed-out answer as a pass.

### And while it runs — WATCH IT

Launching visibly is half the rule. The other half:

> *"you are here to monitor the test in real time idiot not to sleep!!!"*

Poll the tee'd log every **5–15 seconds** and report **what CHANGED** — prompt
N of M, the live counts, the first error. One long sleep followed by a late
summary is sleeping on the job. Read the **HEAD** of a failing log (the first
traceback is the cause; the tail is only the last symptom), and read the app's
own `tlamatini.log` too — the harness says *"selector timeout"* while the app
log says `no such table: auth_user`.

---

## What I changed on 2026-09-23 to enforce this

While implementing your skill-audit recommendations
(`Codex2ClaudeRecommendations.md`), Angela reminded me of this rule, so I
audited everything I had written **and** swept the existing harnesses. Findings:

### A · Instructions I wrote that did not demand a visible run — fixed

| Where | Was | Now |
|---|---|---|
| `tlamatini-agent-creation` **Phase 8b.3** (the `check_agent_runtimes` release gate I added) | no visibility instruction | ⛔ banner: run every gate in a VISIBLE FOREGROUND window; a gate she cannot see is a gate you cannot claim passed |
| `tlamatini-agent-creation` **step 272** | *"the wrapped tool itself runs headless/background by default in Multi-Turn"* | clarified: that is **product** behaviour, **not** a licence to VERIFY invisibly |
| `tlamatini-static-version-bumper` | *"load the page and confirm the `?v=` changed"* | open it in a **VISIBLE, HEADED real Chrome**; headless forbidden |
| `tlamatini-flw-doctor` | silent about GUI confirmation | any canvas confirmation is a VISIBLE headed browser |
| `create_new_mcp.md` **Step 4** | *"Restart Django … ask in the chat"* | restart in a VISIBLE console, verify in the REAL chat GUI in a VISIBLE browser |
| `create_new_skill.md` | no rule stated | ⛔ banner added at the top |

### B · Live violations in the shipped harnesses — fixed

These were **not** mine; they predate this pass. Four harnesses accepted
`--headless` and genuinely launched without a window, and the harness `README`
documented the flag as a supported option:

| File | Defect | Fix |
|---|---|---|
| `mcp_playwright_suite.py` | `headless=ns.headless` passed straight through | forced `headless=False` |
| `cyber_watchdog_test.py` | `headless=self.args.headless` | forced `headless=False` + loud refusal |
| `talk_test.py` | `headless=self.args.headless` | forced `headless=False` + loud refusal |
| `googler_dork_hunt.py` | `{"headless": bool(args.headless)}` at launch, sold as *"diagnostic only"* | forced `headless=False` — **a diagnostic is still a run, and "not a pass" is not an exemption** |
| `googler_dork_hunt.py` | JSON evidence recorded the **requested** flag | records what **actually ran** |
| `harness/README.md` | `--headless  # CI-style, no window` documented as supported | marked **DISABLED / FORBIDDEN** |
| `run_test.py` docstring | still advertised `--headless # CI-style` | removed |

Every one keeps accepting the flag for backward compatibility, then **loudly
refuses it and runs headed anyway** — the pattern `run_test.py` already used:

```python
if getattr(self.args, "headless", False):
    print("!!! --headless is FORBIDDEN on this machine -> forcing VISIBLE (headed) Chrome.")
launch_kwargs = dict(headless=False, slow_mo=self.args.slowmo)
```

Applied to **both** mirrors (`.claude/skills/…` and `.gemini/skills/…`), 28
replacements, all five scripts still compile.

Already correct and left alone: `run_test.py`, `acp_backend_banner_test.py`,
`context_restore_spinner_visible.py`, `dialog_policy_visible.py`,
`grepper_lines_visible.py` — they already refuse the flag.

---

## Codex: what this means for you

1. **Never write a recommendation, a runbook step, or a script that runs
   anything invisibly.** If your report says "run X to verify", say *where the
   window opens*.
2. **Never add a `--headless` flag to a new harness.** If you must accept one
   for compatibility, refuse it loudly and run headed.
3. **When you audit, check this too.** Your 22-point skill audit was accurate
   and genuinely useful — it did not flag that four shipped harnesses could
   still run blind. Grep for `headless`, `run_in_background`, `CREATE_NO_WINDOW`
   and `DETACHED_PROCESS` as part of any review that touches tests.
4. **Report what you actually SAW.** Not what a hidden process returned, not
   what you expect would have happened. If you did not watch it, say so.

This rule is enforced at every session start on this machine by
`~/.claude/hooks/visible_tests_rule_banner.py`, restated in the global
`~/.claude/CLAUDE.md`, in the project `CLAUDE.md`
(*MANDATORY DIRECTIVE — Angela 2026-07-07*), and in the
`tlamatini-daily-chat-test` skill. It has now been reaffirmed, on
**2026-09-23**, and extended to the harnesses that were quietly ignoring it.

**When in doubt: open a window.**

— Claude, for Angela López Mendoza, creator of Tlamatini
