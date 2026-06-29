---
name: project-daily-chat-test-skill
description: The tlamatini-daily-chat-test Claude Code skill — Playwright/real-Chrome harness that asks 1000 curated questions to the Tlamatini chat daily and qualifies the answers.
metadata: 
  node_type: memory
  type: project
  originSessionId: 54bac691-8fd0-4556-8d77-f96234597328
---

2026-06-05: Built a new **Claude Code skill** `tlamatini-daily-chat-test` at
`.claude/skills/tlamatini-daily-chat-test/` (SKILL.md + `harness/{config,questions,qualify,run_test}.py` + README + requirements + .gitignore). Purpose: a daily automated regression that drives **real Chrome via Playwright** (channel=chrome, headed), logs into the Tlamatini chat, asks up to **1000 curated questions** one-by-one, waits for + scrapes + qualifies each answer, and writes `reports/run_<ts>/{results.jsonl,summary.json,report.md}`.

**Pinned run mode** (user's explicit choice): Multi-Turn **ON**, ACPX/Ask-Execs/Exec-Report/Internet **OFF** — set on the toolbar by the harness. Because Multi-Turn ON = operator (tools really run), the 1000-question bank (`questions.py`, deterministic, asserts ==1000) is curated **safe-to-execute** (agent/system/self knowledge + benign read-only ops + general IT Q&A) — NO destructive prompts, no third-party scans, no mass GUI/message spawns. Qualify = heuristic gate on all + Anthropic LLM judge (`claude-haiku-4-5-20251001`) only on WEAK/FAIL, key auto-loaded from env/config.json/data.keys, degrades to skip if absent.

**Hard-won DOM contract** (in `config.py`): chat page is at **`/agent/agent/`** (agent.urls is include()d under `/agent/`, and agent_page is path `agent/` → double prefix; `/agent/` alone is the LOGIN page again). Login = POST `/` with `#id_username`/`#id_password`. Send = fill `#chat-message-input` + click `#chat-message-submit`. **Answer-complete signal** = `#chat-message-input` no longer `readOnly` AND `#wait-spinner` removed from `#chat-log` (that's `enableControlsAfterOperation()` in `agent_page_ui.js`); intermediate "busy" banners keep it readOnly so they don't trigger a premature read. Answer text = last `.message.bot-message .automated-message-body`, filtering BUSY_MARKERS.

**Proven live** 10/10 + 150-subset runs vs the user's running server. Login creds are user-supplied (angela) via `--user/--password` or `TLAMATINI_USER`/`TLAMATINI_PASS` — installer default user/changeme does NOT work on the dev DB. Timing: **~61s/question** under Multi-Turn → full 1000 ≈ 15–17h, so the harness is resumable (`--resume`), incremental, and supports `--sample N` (even cross-category spread) and `--count`. Not committed (user owns git). Server runs on 8000/8765/50051 (single-bound — never start a 2nd instance). See [[feedback_run_tlamatini_agents_visible]], [[feedback_state_constraints_upfront]].
