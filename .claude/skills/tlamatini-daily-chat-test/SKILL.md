---
name: tlamatini-daily-chat-test
description: Run the daily automated Tlamatini chat regression — drive a visible Chrome via Playwright, log into agent_page.html, ask up to 1000 curated safe questions one-by-one (Multi-Turn ON, ACPX/Ask-Execs/Exec-Report/Internet OFF), wait for and qualify each answer (heuristic + LLM judge on failures), then write a dated report + summary. Invoke when the user says "run the daily chat test", "test Tlamatini with the 1000 questions", "daily Tlamatini regression", or schedules this test.
---
<!--
═══════════════════════════════════════════════════════════════════
  ✦  T L A M A T I N I  ✦   —   "one who knows"
  Created by  Angela López Mendoza   ·   @angelahack1
  Developer · Architect · Creator of Tlamatini
  Tlamatini Author Banner — do not remove (Angela's name is kept in every build)
═══════════════════════════════════════════════════════════════════
-->

# Tlamatini Daily Chat Test

A self-contained Playwright harness lives in `harness/` next to this file. It opens
**real Chrome**, logs into Tlamatini, and asks up to **1000 curated questions** to
the chat one at a time — typing, sending, waiting for the answer to finish, scraping
it, and qualifying it — then writes a Markdown report + JSON summary.

This is the operator-mode regression the user wants run **daily**.

## ⛔ FORBIDDEN: headless tests — ALL TESTS MUST BE VISIBLE (Angela, HARD RULE, 2026-07-07)

**HEADLESS / INVISIBLE AUTOMATED TESTS ARE FORBIDDEN. This test ALWAYS runs in a VISIBLE, HEADED real Chrome on Angela's desktop — she MUST see every step live.** `--headless` is **disabled in `run_test.py`** (it is ignored and forced back to headed). Never try to run this or any test invisibly. Launch it inside a VISIBLE foreground window (`Start-Process powershell -NoExit …`, `dangerouslyDisableSandbox:true`), never `run_in_background`. Verify steps with FULL-SCREEN screenshots (whole desktop, taskbar clock visible) and NEVER record a stale/transient/timed-out answer as a pass. See memory `feedback_forbidden_headless_visible_tests` and the Discoverer visible-runner `harness/discoverer_1000.py`.

## Pinned run mode (do not change without being told)

| Toggle | State |
|---|---|
| Multi-Turn | **ON** |
| ACPX | **OFF** |
| Ask-Execs | **OFF** |
| Exec-Report | **OFF** |
| Add internet context | **OFF** |

The harness sets these on the toolbar automatically. Because Multi-Turn is ON the
LLM is an **operator** (tools really execute), so the 1000-question bank in
`harness/questions.py` is deliberately **safe to execute 1000×/day**
(knowledge / introspection / benign read-only ops / general Q&A). **Never** load
the bank with destructive prompts. ACPX/skill *execution* is excluded (ACPX is OFF,
so `acp_*` tools are filtered out); ACPX appears only as knowledge questions.

## How to run it (the daily procedure)

1. **Confirm the Tlamatini server is up** at `http://127.0.0.1:8000` (the user
   normally runs it). Quick check:
   ```bash
   curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8000/
   ```
   If it's down, ask the user to start it (`cd Tlamatini && python manage.py runserver 127.0.0.1:8000 --noreload`) — do **not** silently start a second instance (ports 8000/8765/50051 are single-bound and a second copy just crashes on bind).

2. **Ensure credentials.** The installer default `user`/`changeme` is usually wrong
   on a dev box. Get them from the user once and pass via env or flags:
   ```bash
   set TLAMATINI_USER=<user>
   set TLAMATINI_PASS=<pass>
   ```
   (Or store them in `harness/.creds.env` — gitignored — and source it.)

3. **First-time setup only:**
   ```bash
   cd .claude/skills/tlamatini-daily-chat-test/harness
   pip install -r requirements.txt
   python -m playwright install chrome
   ```

4. **Run the test.** Visible Chrome is the default (the user wants to *see* it).
   The full 1000-question run is long (Multi-Turn tool loops take seconds-to-minutes
   each) — run it in the **background** and report when done:
   ```bash
   cd .claude/skills/tlamatini-daily-chat-test/harness
   python run_test.py --user "$TLAMATINI_USER" --password "$TLAMATINI_PASS"
   ```
   - For a quick health check first, use `--count 10`.
   - **To run ONE specific test** (e.g. when the user says "run the Emailer test"),
     use the `wrapped` bank + `--select`:
     ```bash
     python run_test.py --bank wrapped --select emailer   # just the Send-Email agent
     python run_test.py --bank wrapped --list             # discover --select tokens (no browser)
     ```
     `--select` matches a question's id (`W041`), category (`wrapped:send_email`),
     wrapped key (`send_email`), or display name (`Send Email`) — case-insensitive,
     substring, with aliases (`emailer`→`send_email`, `imap`→`recmailer`). Pass a
     comma-separated list to run several (`--select emailer,recmailer`). A single
     `--select` run is short, so run it in the **foreground**.
   - **Question order is RANDOMIZED by default** — each run asks the selected
     questions in a fresh random sequence so order-dependent / state-leakage bugs
     surface instead of being masked by an always-identical run. The seed is logged
     (and saved in `summary.json` / `report.md`); replay a failing order with
     `--seed <N>`. Use `--no-shuffle` to force the bank's fixed sequential order.
   - On a crash, resume with `--resume reports/run_<timestamp>` (it skips answered ids).
   - `results.jsonl` is written incrementally, so progress is never lost.

5. **Report the outcome.** Read `harness/reports/run_<timestamp>/summary.json` and
   relay: total asked, pass / weak / fail counts, pass-rate %, average response
   time, and the per-category breakdown. Then surface the top WEAK/FAIL items from
   `report.md` (each lists the question, the heuristic reason, the judge verdict,
   and the answer excerpt) so regressions are visible at a glance.

## Verdicts

- **PASS** — answered, no error, long enough, expected keywords present.
- **PASS\*** — heuristic flagged it but the Anthropic judge rated it acceptable.
- **WEAK** — answered but thin / off expectation (sent to the judge).
- **FAIL** — empty, errored (traceback / error banner), or timed out.

The LLM judge (Anthropic, failures only) auto-loads its key from
`ANTHROPIC_API_KEY` / `Tlamatini/agent/config.json` / `data.keys`; if none is
present it degrades to `skip` and the run still completes on heuristics alone.

## Scheduling it daily

This is a Claude Code skill, so the daily cadence is driven by the harness's CLI,
not by the skill itself. Two options for the user:
- Use the Claude Code **`/schedule`** (routine) or **`/loop`** mechanism to invoke
  this skill once a day.
- Or a Windows Task Scheduler job that runs `python run_test.py ...` directly and
  drops the report under `harness/reports/`.

## How it works (contract, for maintenance)

- **Login:** POST `/` (`#id_username`, `#id_password`, submit) → chat at `/agent/`.
- **Send:** fill `#chat-message-input`, click `#chat-message-submit`.
- **Answer complete:** the input stops being `readOnly` **and** `#wait-spinner` is
  removed from `#chat-log` (`enableControlsAfterOperation()` in `agent_page_ui.js`).
  Intermediate "busy" banners keep it `readOnly`, so they don't cause an early read.
- **Answer text:** the last `.message.bot-message .automated-message-body` in
  `#chat-log`, after filtering the known busy/system banners.

If the chat UI changes, fix `harness/config.py` (selectors + the ready/started JS in
`run_test.py`) — everything else keys off that single contract.

> ⚠️ If the answer-complete logic ever needs adjusting, verify it against a LIVE
> server with `--count 2` before trusting a full run — a daily test that silently
> mis-detects completion is worse than no test.
