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

**HEADLESS / INVISIBLE AUTOMATED TESTS ARE FORBIDDEN. This test ALWAYS runs in a VISIBLE, HEADED real Chrome on Angela's desktop — she MUST see every step live.**

`--headless` is **disabled in `run_test.py`** (it is ignored and forced back to headed). Never try to run this or any test invisibly. Launch it inside a VISIBLE foreground window (`Start-Process powershell -NoExit …`, `dangerouslyDisableSandbox:true`), never `run_in_background`. Verify steps with FULL-SCREEN screenshots (whole desktop, taskbar clock visible) and NEVER record a stale/transient/timed-out answer as a pass.

See memory `feedback_forbidden_headless_visible_tests` and the visible runners `harness/discoverer_1000.py` (Discoverer), **`harness/pdfer_nuance_visible.py`** (PDFer), **`harness/dialog_policy_visible.py`** and **`harness/voice_commands_visible.py`** (the VOICE COMMANDS catalog section).

**`harness/voice_commands_visible.py`** is the 2026-09-12 proof of the catalog's new FIRST section. In headed Chrome it opens the real Catalog of Prompts and checks what the user actually sees: VOICE COMMANDS is the first `.prompt-category-header` in the DOM and really renders in capitals; its two cards sit in rank order (#121 opener, #122 SPEAK YOUR PROMPT); #122 carries Angela's sentence **verbatim**; the badges are exactly **Multi-turn · ACPX · Exec-report**; and **clicking #122 really ticks those three toolbar checkboxes** while leaving Step-by-Step off. It then clicks #121 and asserts the toolbar flips the OTHER way (Step-by-Step on, ACPX off) — which is what proves the boxes follow the CARD rather than lingering from the previous click. Every photo is taken by **Shoter**. Two honesty guards: it asks `/agent/list_prompts/` FIRST and **stops with a distinct exit code 3** if the app answering `:8000` has no `voice_commands` section (that means the FROZEN install is serving, and the section lives in the SOURCE tree), rather than reporting a misleading fail — and it states, on screen and in its `SUMMARY.html`, that **no microphone was used**: a voice command needs a human voice, and faking it would fake the very thing under test. Measured 2026-09-12 against the source server: **23/23 checks green**.

**`harness/pdfer_nuance_visible.py`** is the 2026-09-06 proof of PDFer's nuance / typography / layout overhaul. It spawns the REAL `pdfer.py` the way the pool does (a copied runtime dir + a written `config.yaml`, never an import), renders the same content under different treatments, **audits every produced PDF against the file on disk** with PyMuPDF, opens each one on screen, and photographs the whole desktop with **Shoter**. Its seventh case deliberately renders the torture tables through the **OLD xhtml2pdf engine** so the before/after sits together rather than being a claim: measured 2026-09-06, the new engine is CLEAN and the old one shows **8 overlapping text pairs** on the same tables while reporting `err=0`. A case passes only if the PDF exists AND the audit is clean AND the reported design fields match what was asked for AND Shoter produced a photo — a missing photo is a FAILURE, never a silent pass. ⚠️ It drives the agent in the **repo** (`C:\Development\XAIHT\Tlamatini`) on purpose: the Django server on this machine runs from a DIFFERENT install (`C:\Development\Tlamatini`), so a chat-GUI route would exercise the OLD PDFer until that install is synced. The 2026-08-16 dialog-dismissal proof opens each real dialog in headed Chrome, presses Escape, and confirms it closed with the same meaning as its ✕. It also proves that the **sealed updater refuses** Escape / Ctrl+F4 / F5 while a download is in progress through a `window.__tlmSealCanary`, so "the dialog is gone" and "F5 worked" can never look identical. It never starts a real update: it calls `seal('update')` to reproduce the exact policy state.

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

## v1.48.13 regression set

When the touched surface is relevant, include visible cases for: Mover/Deleter empty, relative, legacy `C:/Temp/...`, and explicit absolute destinations; long-operation menu disable/restore; dialog dismissal (**Escape must close every dialog with the same meaning as its ✕ / Cancel; an outside click must still NOT dismiss; a sealed updater must refuse Escape and Ctrl+F4/F5 while downloading**), ✕/Cancel/Continue behavior, and that no native `alert()`/`confirm()` appears over a themed dialog; safe update release-note rendering; and per-user/request/stream/line log attribution. A movement test must prove Deleter scope was not widened.

## v1.48.14 release-target regression set

When External MCP or response rendering changes, visibly verify: the dialog lists inactive `memory` and `sequential-thinking`; the runtime strip reports node/npm/npx/pnpm/uv/uvx without blocking the page; **Install now** has honest success/failure state; activating a default is explicit; deleting it does not resurrect it after reload; and a nested explicit/auto ASCII diagram followed by Markdown `---` renders every diagram once with no `DGRM_*` or NUL leakage. Use an isolated catalog/config path for tests so a maintainer's keyed `external_mcps.json` is never modified.

## v1.48.17 release regression set

When search, wrapped-agent reporting, Kubernetes execution, build privacy, or self-update changes, add visible/focused cases for: Grepper searching BOM-marked UTF-8/16/32 and cp1252/Latin-1 while skipping binary data; all five status classes and pairwise-disjoint `KNOWN_STATUSES`; degraded output rendering red; completed diagnostics rendering green; unknown-status compatibility plus guard rejection; Kuberneter emitting numeric `returncode`, boolean `success`, and `status: ok|failed`; public builds excluding a maintainer catalog while the explicit private builder may include one; and update swaps retaining `Uninstaller.exe`. Run `agent.test_grepper_encodings`, `agent.test_status_vocabulary`, `agent.test_agent_verdict`, and `agent.test_preserved_user_state` when those surfaces are touched.

## v1.50.0 release regression set

When the current release is touched, verify NetSpeed-Calculator with `action='latency'` or `validate` by default, never a repeated `full` run; assert the full/download/upload bandwidth warning and tier-D Ask-Execs classification. Run WAL-mode Backup DB/Set DB/hot-swap tests through `sqlite_copy.py` and prove `quick_check` plus sidecar hygiene. Run `agent.test_googler_dorks` and pin preset-under-explicit-field precedence, aliases, no-space operator syntax, uppercase parenthesized `OR`, site-group same-domain handling, `links_only` file-hunt guidance, and the direct-tool versus visual/pool structured-field boundary. Also pin the two-tier order (four plain-HTTP server-rendered routes before any browser), explicit engine pins skipping Tier 0, `headless: false` for Tier 1, the seven-route browser order, tolerant string booleans, bounded retries, first-answer stopping, pinned-engine behavior, redirect unwrapping, and explicit Google-only advanced-operator semantics. The optional visible proof is `harness/googler_dork_hunt.py`: it uses the shipped builder, opens headed Chrome, targets public-domain/open-access sources, and stores JSON evidence under Tlamatini `Temp`; search-engine refusal is a failed proof run, not proof that the compiled query is wrong. Validate migration 0194's Deep Internet Research card and 0195-0197's NetSpeed rows, the `adding-external-mcp` classify/import/doctor/activate/wait/list/call lifecycle, the 88/66/108/29/197 source counts, and the private contact-sync/public-empty boundary. Verify `v1.50.0` as the annotated release and report a later `HEAD` separately rather than calling the release untagged.

> ⚠️ If the answer-complete logic ever needs adjusting, verify it against a LIVE
> server with `--count 2` before trusting a full run — a daily test that silently
> mis-detects completion is worse than no test.
