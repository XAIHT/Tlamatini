---
name: project_playwrighter_agent
description: "Playwrighter (#65) scripted-browser-automation agent — canvas + Multi-Turn, added 2026-05-20"
metadata: 
  node_type: memory
  type: project
  originSessionId: d4641970-afff-43b1-a506-0b1e255a2a7e
---

2026-05-20: Added **Playwrighter** as workflow agent #65 — scripted, INTERACTIVE browser automation via Playwright (Chromium/Firefox/WebKit). It fills the gap neither Googler (web search) nor Crawler (static urllib fetch) covers: a REAL browser driven through a declarative step list (goto/click/fill/press/select/check/wait_for/wait/extract_text/extract_attr/screenshot/assert_visible/assert_text/download) for authenticated / JS-rendered / multi-step flows. Deterministic (no LLM). Emits `INI_SECTION_PLAYWRIGHTER` (fields start_url, final_url, status, steps_run, assert_result, response_body); ALWAYS triggers target_agents (success or failure) so a Forker can branch on {status}/{assert_result}. `headless` toggle + `storage_state_in`/`storage_state_out` for session reuse.

Built for BOTH surfaces (user asked for canvas + Multi-Turn):
- **Canvas**: `agent/agents/playwrighter/playwrighter.py` + `config.yaml` (self-contained subprocess, copies googler.py boilerplate, calls `sync_playwright()` directly — no ThreadPoolExecutor needed because pool agents run outside Django's event loop). YAML `steps` is the canvas authoring form.
- **Multi-Turn**: wrapped tool `chat_agent_playwrighter` in `chat_agent_registry.py`. The LLM passes the whole script as a single JSON string in `steps_json` (the flat key=value request grammar can't express a list-of-dicts; the splitter protects it because it's inside single-quotes). `playwrighter.py` json.loads `steps_json` and it WINS over YAML `steps`.

Wiring touched: views.py `update_playwrighter_connection_view` + urls.py route; migrations **0091_add_playwrighter** (Agent row) + **0092_add_chat_agent_playwrighter_tool** (Tool row); parametrizer.py SECTION_AGENT_TYPES; agent_contracts.py `_PARAMETRIZER_OUTPUT_FIELDS['playwrighter']` (auto-discovered contract, no builtin needed); mcp_agent.py `_EXEC_REPORT_TOOLS` (state-changing, agent_key `playwrighter`); capability_registry.py hints; agent_page_chat.js `_mapToolArgsToAgentConfig`; agentic_control_panel.css gradient ("Theatre Spotlight": #3D1766→#D90368→#0FA3B1→#6EE7B7, nods to Playwright's two-masks logo); agent_page.css exec-report caption+cmd+dark-header; the 4 canvas JS files (acp-agent-connectors / acp-canvas-core 6 sites / acp-canvas-undo / acp-file-io); eslint.config.mjs global `updatePlaywrighterConnection`.

Counts now: **65 agents / 72 Multi-Turn tools / 40 wrapped chat-agent tools / 23 skills**. Verified: ruff clean, npm lint 0 errors, migrate applied, 19 tests (ExecReportCaptureTests + test_flow_contracts) OK, get_mcp_tools() binds chat_agent_playwrighter (total 72). Docs updated: agents_descriptions.md, README.md, agentic_skill.md (#64, FlowCreator bumped to #65), CLAUDE.md, docs/claude/*, KIMI.md, BookOfTlamatini.md.

Follows the same canvas-counterpart-of-a-wrapped-tool pattern as [[project_acpxer_added]] and [[project_reviewer_analyzer_agents]]. Per [[feedback_update_agent_docs]] all agent docs were updated in the same pass. User must restart server / reload page to see the new sidebar agent (migrate already run).
