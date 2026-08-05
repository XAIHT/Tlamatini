---
name: project_agent_table_wiped_on_boot
description: "apps.ready() DELETES the whole Agent table every startup and re-derives names with .title() — the real source of 'Pdfer' and 6 dead canvas connections (fixed 2026-07-26)"
metadata: 
  node_type: memory
  type: project
  originSessionId: 69614274-24d6-4daa-92af-01a874c256f6
  modified: 2026-07-26T22:07:01.779Z
---

**`AgentConfig.ready()` runs `Agent.objects.all().delete()` on EVERY startup** and
rebuilds the table from the `agents/` folder listing (`agent/apps.py`, ~line 236).
So a migration's carefully cased `agentDescription` is **overwritten on the very
next launch** — the boot code, not the migration, is the effective source of truth
for every sidebar/canvas display name.

**How Angela found it (2026-07-26):** her freshly-built `C:\Tlamatini` showed
**"Pdfer"** on the canvas even though migration 0188 seeds `PDFer`.

**Every NEW agent hits this same trap.** The most recent is **LaTeXer** (#87,
2026-08-05): `'latexer'.title()` → `'Latexer'`, so migration 0191 seeding
`LaTeXer` would be silently overwritten on the next boot without
`"latexer": "LaTeXer"` in `display_name_from_agent_type`. Add the override in the
SAME pass as the migration, every time. See [[project-latexer-agent]].

Two defects the old logic (`str.title()` + 5 ad-hoc overrides) shipped:

1. **22 of 86 names mis-cased** — Pdfer, Sqler, Ssher, Pser, Scper, Acpxer,
   Esp32Er, Esphomer, Audioplayer, Videoplayer, Flowcreator, Teletlamatini, …
2. **6 canvas connections silently dead.** `acp-canvas-core.js` compares
   `targetAgentName.toLowerCase()` **without collapsing spaces**, and for
   kyber-keygen / kyber-cipher / kyber-decipher / j-decompiler / video-analyzer /
   de-compresser it only ever tests the **HYPHENATED** literal. A spaced
   "Video Analyzer" matches nothing, so the wiring was never persisted.

**FIX:** `apps.py::_canonical_agent_display_name()` routes the boot repopulate
through `services/agent_paths.py::display_name_from_agent_type` (the same map the
Flow Compiler + Agent Contracts use), fail-open to the legacy value. Added
overrides: audioplayer/videoplayer/flowcreator/flowhypervisor/flowbacker/mcp_doctor
(case) + video_analyzer/de_compresser (hyphen), and `apirer` pinned to `Apirer`
(agents.md + registry) so the sidebar label does not churn.
Pinned by **`agent/test_agent_display_names.py`** (6 tests) — it parses the JS
connection literals and fails if any display name can't match its handler.

**GAP CLOSED same day (2026-07-26, second pass — Angela asked for it).** file_creator /
file_extractor / file_interpreter / image_interpreter / monitor_log were renamed to
**File-Creator / File-Extractor / File-Interpreter / Image-Interpreter / Monitor-Log**
in `agent_paths` **AND** `chat_agent_registry.display_name` **together** (plus
`mcp_agent._TOOL_TO_AGENT_DISPLAY_NAME` Image-Interpreter ×3 and the `_EXEC_REPORT_TOOLS`
File-Creator caption — `agent_key` stays `filecreator`, so the CSS gradient still matches).
One-sided renames are forbidden: the registry name keys the FAIL-OPEN enable gate
`agent_<display>_status`, so changing only `agent_paths` silently breaks the
Configure-Agents checkbox instead of erroring. `CANVAS_HYPHEN_GAP` is gone and a new
test — `test_registry_display_names_match_the_canonical_resolver` — pins the agreement.
Live after restart: **86 rows, 32/32 expected names, 0 mis-cased, 113 prompts.**

**Docs synced the same pass:** CLAUDE.md, docs/claude/{recent-fixes,agents,architecture,
exec-report}.md, create_new_agent.md (+ checklist), the two `.claude/skills`
(agent-naming, agent-creation), Tlamatini.md self-knowledge, BookOfTlamatini.md,
agents_descriptions.md, KIMI.md, flowcreator/agentic_skill.md (21 hits — FlowCreator
emits these names into `.flw`, so it was a functional fix, not just prose).

Also note the historical `NNNN_repopulate_all_agents` migrations seed with the same
old `.title()` logic, so a FRESH `migrate` still writes mis-cased rows — the first
server boot then corrects them. Never edit those migrations (history is immutable).

Related: [[feedback_agent_naming_conventions]], [[project_pdfer_agent]],
[[project_prompt_catalog_grouping]], [[project_live_app_is_frozen_install]].
