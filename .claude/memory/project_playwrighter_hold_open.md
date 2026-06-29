---
name: project_playwrighter_hold_open
description: "Playwrighter hold_open_seconds/hold_open_ms linger knob — fixes \"browser closes before I can see it\""
metadata: 
  node_type: memory
  type: project
  originSessionId: b54d4c7b-a292-4ec1-817c-8e09c3c0cf89
---
<!--
═══════════════════════════════════════════════════════════════════
  ✦  T L A M A T I N I  ✦   —   "one who knows"
  Created by  Angela López Mendoza   ·   @angelahack1
  Developer · Architect · Creator of Tlamatini
  Tlamatini Author Banner — do not remove (Angela's name is kept in every build)
═══════════════════════════════════════════════════════════════════
-->

2026-05-21: Playwrighter closed the browser the instant the last step returned
(its `run_browser_flow` `finally` block tears the browser down with no delay),
so a user's "PLEASE WAIT 10 SECONDS BEFORE CLOSE THE BROWSER" was ignored — the
LLM also didn't append a trailing `{"action":"wait"}` step.

**Fix**: added a dedicated linger knob honored AFTER the last step, BEFORE close
(success OR mid-flow error). `hold_open_seconds` is the natural unit;
`hold_open_ms` is the finer alias and wins when both > 0. New `_coerce_int`
helper (never raises on bad value). Files (source):
- `agent/agents/playwrighter/playwrighter.py` — `_coerce_int`, read both keys in
  `run_browser_flow`, `page.wait_for_timeout(hold_open_total_ms)` before finally
- `agent/agents/playwrighter/config.yaml` — `hold_open_seconds: 0` / `hold_open_ms: 0`
  (must exist as keys so the wrapped-tool `_apply_requested_assignments_to_config`
  can resolve `hold_open_seconds=10` — unknown keys are silently ignored)
- `agent/chat_agent_registry.py` — Playwrighter `purpose` now tells the LLM to
  pass `hold_open_seconds=<N>` on "wait before closing / let me watch it"
- `agent/static/agent/js/agent_page_chat.js` — Flow-Generator branch maps both keys
- `agent/migrations/0095_*` — BROWSER SPOTLIGHT (#53) + BROWSER WIZARD demos now
  include `hold_open_seconds=10`
- `agent/agents/flowcreator/agentic_skill.md` — entry 64 config-param list
- `agent/test_playwrighter_agent.py` — 6 new tests (60 total pass); ruff + eslint clean

Docs aligned in a follow-up pass (counts unchanged 66/23): `docs/claude/gotchas.md`
(Recent Fixes entry), `docs/claude/agents.md` (catalog entry), `README.md` §3.13,
`agents_descriptions.md` line 67, `BookOfTlamatini.md` (bestiary row + glossary +
new Recent-Updates changelog entry). Frozen mirrors of the two RUNTIME-READ docs
also patched: `C:\Tlamatini\agents_descriptions.md` (tooltips) +
`C:\Tlamatini\agents\flowcreator\agentic_skill.md` (FlowCreator).

**Also patched the running frozen install** `C:\Tlamatini\agents\playwrighter\{playwrighter.py,config.yaml}`
(byte-identical templates; wrapped tool copies them per-run) so the capability
works NOW. CAVEAT: the registry `purpose` + demo-prompt migration are baked into
the frozen executable, so without a REBUILD the LLM won't auto-translate
natural-language "wait 10 seconds" → `hold_open_seconds`; the user must either
put `hold_open_seconds=10` explicitly in the chat_agent_playwrighter call, or
rebuild. See [[feedback_update_agent_docs]] and [[project_playwrighter_agent]].
