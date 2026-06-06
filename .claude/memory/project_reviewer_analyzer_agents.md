---
name: project-reviewer-analyzer-agents
description: "2026-05-19 — added Reviewer + Analyzer workflow agents (#63/#64) and code-review + security-audit SKILL.md packages, on both surfaces"
metadata: 
  node_type: memory
  type: project
  originSessionId: 02c4c443-42ee-4432-aa42-df6619db6e34
---

2026-05-19: Added "powerful skills" the user requested, scoped to **Code Review + Security Audit** on **both surfaces** (their explicit choices via AskUserQuestion). Split into the roadmap's Reviewer (LLM review) + Analyzer (static/security scan).

Delivered 4 artifacts:
- **SKILL.md packages** (now 23 total, was 21): `agent/skills_pkg/code_review/SKILL.md` (name `code-review`, requires chat_agent_executer + chat_agent_gitter, outputs verdict/findings/summary) and `agent/skills_pkg/security_audit/SKILL.md` (name `security-audit`, multi-scanner bandit/semgrep/ruff/eslint/gitleaks/pip-audit). Skills auto-discover from disk via `skill_registry`; no migration needed; `_disabled_skill_names()` fails open so they're enabled by default.
- **Workflow agents** (#63 Reviewer, #64 Analyzer; now 64 total): `agent/agents/reviewer/` (LLM git-diff review → `INI_SECTION_REVIEWER` with a `verdict` APPROVE/REQUEST_CHANGES/COMMENT; uses query_ollama like prompter.py) and `agent/agents/analyzer/` (deterministic, no LLM → `INI_SECTION_ANALYZER` with `status` clean/findings/error + `total_findings`). Both ALWAYS trigger target_agents so a Forker can branch on the verdict/status. Migrations `0088_add_reviewer.py` / `0089_add_analyzer.py`.

Deliberately **canvas-only** — skipped the wrapped-chat-agent path (Step 7.5/7.6/7.7) because the two SKILL.md packages already cover the LLM/chat surface; a wrapped tool would be a redundant third surface.

Wiring touched: views.py (update_reviewer/analyzer_connection_view), urls.py (secure_post routes), agent_contracts._PARAMETRIZER_OUTPUT_FIELDS, parametrizer.py SECTION_AGENT_TYPES, agentic_control_panel.css (reviewer = teal→indigo→violet, analyzer = dark-red→amber→yellow heatmap), 4 JS files (acp-agent-connectors / acp-canvas-core [classMap + 3 call-site pairs] / acp-canvas-undo [undo+redo] / acp-file-io [both switch cases]), and **eslint.config.mjs globals** (the real source of truth for cross-file connector fns — NOT the per-file `/* global */` comments; mirror [[project-acpxer-added]]'s Unrealer pattern). Docs: CLAUDE.md, docs/claude/{INDEX,agents,multi-turn,acpx}.md, README.md, BookOfTlamatini.md, agentic_skill.md, agents_descriptions.md — all 62→64 / 21→23 counts.

**Remaining manual step for the user**: run `python Tlamatini/manage.py migrate` to seed the two Agent rows (I did not run it — it mutates the tracked db.sqlite3; see [[feedback-user-owns-git]]). Validated without it via test-DB builds.

2026-05-20 follow-up: shipped as **v1.4.0** (commit `efb8c13` "Analyzer and Reviewer agents!!!", tagged `v1.4.0` — minor bump from v1.3.2). Did a full version+doc pass: README version badge v1.3.2→v1.4.0; added v1.4.0 entries to BookOfTlamatini "Recent Updates" + gotchas "Recent Fixes"; marked roadmap Reviewer(#2)/Analyzer(#3) implemented in gotchas.md + KIMI.md; added Reviewer/Analyzer to KIMI.md catalog + BookOfTlamatini Bestiary; added REVIEWER/ANALYZER SPECIAL NOTES to flowhypervisor `monitoring-prompt.pmt` (key rule: verdict `REQUEST_CHANGES` and status `findings` are routable content, NOT flow errors). All current-state counts now 64 agents / 23 skills across every doc. Note: `NEW_AGENT_RECOMMENDATIONS.md` referenced by gotchas/KIMI no longer exists (pre-existing dangling ref, left alone). Historical changelog "62"/"21" mentions (Book 2299 Unreal narrative, 2405 admin-menu entry) left as-is on purpose — don't rewrite dated history.
