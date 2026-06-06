---
name: project_temp_templates_policy
description: Temp + Templates dirs must live ONLY under the Tlamatini app root; never outside Tlamatini
metadata: 
  node_type: memory
  type: project
  originSessionId: 5011672b-c235-4302-bc25-6c7ed7ab85ad
---

2026-06-02: Forceful "files stay inside Tlamatini" policy, two dirs at the **application root** (`path_guard._get_application_root()` → frozen: exe dir e.g. `C:\Tlamatini`; source: repo root e.g. `D:\devenv\source\Tlamatini`).

**Temp** (throwaway scratch) — ALL temp files go under `<app>/Temp`, never `C:\Temp`/`%TEMP%`/system temp.
- Resolver/enforcer in `agent/path_guard.py`: `get_app_temp_root` / `enforce_app_temp_dir` (sets `TMP/TEMP/TMPDIR` + `tempfile.tempdir` + exports `TLAMATINI_TEMP`) / `is_within_app_temp` / `resolve_temp_path`.
- Process-wide: `manage.py::_enforce_app_temp_dir()` (before Django) AND `tlamatini/settings.py::_pin_temp_directory()` (covers direct daphne/asgi). Children inherit via `get_agent_env`'s `os.environ.copy()`.
- 6 temp-creating agents (executer, de_compresser, esp32er, stm32er, arduiner, telegramrx) have a module-top **`if (os.environ.get('TLAMATINI_TEMP')…):`** block (NOT a top-level `def` — that trips ruff E402 before imports; mirror the conhost-guard `if` shape). executer non-blocking script now uses `TLAMATINI_TEMP`.
- LLM: `prompt.pmt` **Rule 15** + fixed the old `C:\Temp\hello.py` example; absolute path injected via `{temp_directory}` placeholder resolved in `rag/config.py`.

**Templates** (DEFAULT scaffold home) — STM32er/ESP32er/Arduiner/Unrealer create template/firmware/engine PROJECTS under `<app>/Templates` UNLESS the user names another path.
- `path_guard`: `get_app_templates_root` / `enforce_app_templates_dir` (exports `TLAMATINI_TEMPLATES`, does NOT touch TMP/tempfile). manage.py/settings.py create+export it.
- LLM: `prompt.pmt` **Rule 16** (pushed Conflict-resolution → Rule 17; updated the one "Rule 16/17" cross-ref in the Prime-Directive) + `{templates_directory}` placeholder + per-agent registry `purpose` lines. STM32er `_build_arguments('create_project')` defaults blank `dest_parent` → `TLAMATINI_TEMPLATES` (gated on env, so unit tests w/o it keep old behavior; manage.py test DOES set it).

`build.py` ships `Temp` + `Templates` empty next to the .exe (added to `empty_dirs`). `.gitignore` ignores both. **Frozen needs `python build.py`** to ship (manage.py/settings.py/prompt.pmt live in the PYZ).

**Skill/guide indications (2026-06-02 follow-up):** propagated the policy as authoring indications into the runbooks so future agent/tool/skill/flow creation honors it — `create_new_agent` / `create_new_mcp` / `skill_creator` / `flow_making` / `tlamatini_new_acp_agent` / `tlamatini_flow_from_objective` SKILL.md + the 2 @-imported guides (`.agents/workflows/create_new_agent.md` pitfall #11 + Step 1b, `.mcps/create_new_mcp.md` tool-only bullet + assumption #17) + a `## Temp & Templates Directory Policy` section in CLAUDE.md + a sibling-convention clause in `.claude/skills/tlamatini-agent-naming` + the recent-fixes.md 2026-06-02 entry. Deliberately SKIPPED (no file-scratch / would be noise): the integration stubs (gmail/slack/github/jira/notion/todoist/trello/weather/hello_world) + read-only/audit utility skills (acp_router/summarize/code_review/security_audit/kali_pentest/setup_new_acpx_key/tlamatini_* audit ones). All 27 skills pass `_meta/lint.py`.

Tests: `agent/test_temp_dir_policy.py` (33 hard tests — real resolution/enforcement, extracts+execs each agent's actual block, real prompt.pmt injection, static wiring). All green; ruff clean. Also greened a PRE-EXISTING red (`AssignmentParserRobustnessTests` — the 3 firmware example_requests had multi-step `"; then action="` that the parser mis-read; rewrote them single-step). NOT committed. Related: [[feedback_state_constraints_upfront]] [[feedback_hard_real_scenario_tests]] [[project_arduiner_agent]] [[project_stm32er_agent]].

Pre-existing failures in the dev working tree (NOT mine — untouched subsystems, present due to uncommitted config.json/config.yaml): AcpxConfigSourceMode (local config.json codex cmd), PreLaunchScriptPreview (esp32er/arduiner absent from tools.py preview SETS though they have branches), AgentDescriptionsCoverage (stray `.ruff_cache` under agent/agents/ + reviewer/), ParametrizerSequentialExecution (NoneType), MultiTurnBackgroundLaunch (mock `object` has no `bind_tools`), PromptValidationDecision.
