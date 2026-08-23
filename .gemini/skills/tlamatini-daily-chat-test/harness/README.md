<!--
═══════════════════════════════════════════════════════════════════
  ✦  T L A M A T I N I  ✦   —   "one who knows"
  Created by  Angela López Mendoza   ·   @angelahack1
  Developer · Architect · Creator of Tlamatini
  Tlamatini Author Banner — do not remove (Angela's name is kept in every build)
═══════════════════════════════════════════════════════════════════
-->
# Tlamatini Daily Chat Test — harness

A Playwright harness that drives **real Chrome**, logs into Tlamatini, and asks
up to **1000 curated, safe-to-execute questions** to the chat one at a time —
typing each, sending, waiting for the answer to finish rendering, scraping it,
and qualifying it (heuristic + LLM judge on the failures). It produces a dated
Markdown report and JSON summary.

## Files

| File | Role |
|---|---|
| `config.py` | Target URL, credentials, **DOM selectors + the answer-complete signal**, pinned run mode |
| `questions.py` | Generates exactly **1000** deterministic, safe questions (run it directly to inspect) |
| `qualify.py` | `heuristic_qualify(...)` (all answers) + `LLMJudge` (Anthropic, failures only) |
| `run_test.py` | The Playwright harness + report writer (entry point) |
| `reports/run_<timestamp>/` | `results.jsonl`, `report.md`, `summary.json` per run |

## Pinned run mode

Multi-Turn **ON**, ACPX **OFF**, Ask-Execs **OFF**, Exec-Report **OFF**,
Internet **OFF** — set automatically by the harness on the toolbar toggles.
Because Multi-Turn is ON the LLM is an *operator* (tools really run), so the
1000-question bank is curated to be **safe to execute** (knowledge /
introspection / benign read-only ops / general Q&A). It contains nothing
destructive.

## Prerequisites

```bash
pip install -r requirements.txt
python -m playwright install chrome      # real Google Chrome; or: install chromium
```

The Tlamatini server must be running and reachable (default `http://127.0.0.1:8000`):

```bash
cd Tlamatini && python manage.py runserver 127.0.0.1:8000 --noreload
```

## Credentials

The installer default is `user` / `changeme`, but a dev instance uses whatever
superuser you created. Provide them one of these ways (CLI flags win):

```bash
# env vars
set TLAMATINI_USER=youruser
set TLAMATINI_PASS=yourpass
# or CLI flags
python run_test.py --user youruser --password yourpass
```

## Usage

```bash
# from this directory
python run_test.py                       # full 1000, visible Chrome
python run_test.py --count 10            # quick smoke
python run_test.py --count 5 --headless  # CI-style, no window
python run_test.py --resume reports/run_2026-06-05_22-00-00   # continue a crashed run
python questions.py                      # print the bank distribution (no browser)

# Run ONE specific wrapped-agent test (e.g. the Emailer):
python run_test.py --bank wrapped --select emailer
python run_test.py --bank wrapped --list           # discover --select tokens (no browser)
python run_test.py --bank wrapped --select emailer,recmailer   # run a few
```

### Useful flags

| Flag | Default | Meaning |
|---|---|---|
| `--bank {full,wrapped}` | full | `full` = 1000-question bank; `wrapped` = one functional test per wrapped chat-agent, plus an email-attachment scenario (50) |
| `--select TOKENS` | — | run ONLY questions matching these comma-separated tokens — matches a question's **id** (`W041`), **category** (`wrapped:send_email`), wrapped **key** (`send_email`), or **display name** (`Send Email`), case-insensitive/substring, with aliases (`emailer`→`send_email`, `imap`→`recmailer`, …). Overrides `--start/--count/--sample`. |
| `--list` | off | print every question in the chosen `--bank` (id / category / key / text) and exit, so you can find `--select` tokens (no browser) |
| `--count N` | 1000 | how many questions (from `--start` offset) |
| `--start K` | 0 | 0-based offset into the bank |
| `--timeout S` | 240 | per-question hard cap in **seconds** (Multi-Turn tool loops can be slow) |
| `--headless` | off | run without a visible window |
| `--slowmo MS` | 0 | Playwright `slow_mo` — slows actions so you can watch |
| `--clear-every N` | 0 | clear chat history every N questions (0 = never; a clear runs once at start unless `--no-fresh-start`) |
| `--no-judge` | off | skip the Anthropic judge on failures |
| `--base-url URL` | `http://127.0.0.1:8000` | target |
| `--hold S` | 0 | keep the browser open S seconds at the end |
| `--resume DIR` | — | skip ids already in `DIR/results.jsonl` |

## Output

`reports/run_<timestamp>/`:
- `results.jsonl` — one line per answered question (incremental & crash-safe)
- `summary.json` — totals, pass-rate, per-category breakdown, timings
- `report.md` — human-readable report; lists every WEAK/FAIL with the answer excerpt

## Verdicts

- **PASS** — answered, no error signal, long enough, expected keywords present
- **PASS\*** — heuristic was WEAK/FAIL but the LLM judge rated it acceptable
- **WEAK** — answered but thin / missing expected keywords (judged if a key is set)
- **FAIL** — empty, errored (traceback / error banner), or timed out

The **answer-complete signal** the harness waits on: the chat input stops being
`readOnly` **and** the `#wait-spinner` is removed from `#chat-log`
(`enableControlsAfterOperation()` in `agent_page_ui.js`). Intermediate "busy"
banners keep the input `readOnly`, so they don't trigger a premature read.
