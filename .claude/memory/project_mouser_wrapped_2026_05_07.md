---
name: Mouser wrapped as chat_agent_mouser; Shoter no-popup contract
description: 2026-05-07 — Mouser usable from Multi-Turn; chat_agent_mouser added to registry, _EXEC_REPORT_TOOLS, CSS, prompt; migration 0079. Shoter purpose strengthened to forbid launch_view_image follow-ups so workflow target window keeps focus.
type: project
originSessionId: f7480c2f-defb-4ab7-86cc-1d5a60ff9c71
---
2026-05-07: Added `chat_agent_mouser` so Multi-Turn can move the pointer and click — needed to focus a target window (e.g. Notepad) before chat_agent_keyboarder types into it.

Changes (all on `main`):

- `agent/chat_agent_registry.py`: new `ChatWrappedAgentSpec(key="mouser", template_dir="mouser", tool_name="chat_agent_mouser", ...)` covering `movement_type` ('localized'|'random'), `actual_position`, `ini_posx`/`ini_posy`, `end_posx`/`end_posy`, `button_click` (none|left|right|middle|double-left|double-right|double-middle), `total_time`. Example: `Move mouse with movement_type='localized' and end_posx=600 and end_posy=400 and button_click='left'`. Also strengthened the Shoter spec purpose: "the file is NEVER opened in a viewer (no popup, no focus stolen) ... NEVER follow chat_agent_shoter with launch_view_image — that would pop a viewer window and steal focus from the workflow's target app".
- `agent/mcp_agent.py`: added `"chat_agent_mouser": ("mouser", "Mouser")` to `_EXEC_REPORT_TOOLS` (state-changing — moving + clicking reroutes desktop focus). Also added a Mouser line to the in-prompt TOOL SELECTION GUIDE and rewrote the Shoter line to forbid `launch_view_image` follow-ups.
- `agent/migrations/0079_add_chat_agent_mouser_tool.py`: seeds `Tool` row with `toolDescription="Chat-Agent-Mouser"`.
- `agent/static/agent/css/agent_page.css`: added `.exec-report-caption-mouser` (red→violet→green gradient mirroring `.canvas-item.mouser-agent`), added `.exec-report-mouser thead th` to the dark-captioned override list, added `.exec-report-mouser .exec-report-cmd` left-border accent (`#FF1744`).

**Why:** User's prompt: "open the notepad, verify it is opened and waiting for input and then write 'Hi, I'm Tlamatini'". After wrapping Keyboarder earlier today, Mouser was the missing piece — a freshly-launched Notepad may not be the foreground window, so Keyboarder's strokes could land in the wrong window. Mouser now lets the LLM click into the edit area first.

**How to apply:** The canonical "type into a desktop app" recipe under Multi-Turn is now:
1. `chat_agent_executer` to launch the app (e.g. `notepad`).
2. `chat_agent_shoter` (silent — no viewer pops) → `chat_agent_image_interpreter` to find the edit-area coordinates.
3. `chat_agent_mouser` with `movement_type='localized' and end_posx=... and end_posy=... and button_click='left'` to focus the window.
4. `chat_agent_keyboarder` with `input_sequence=...` to type.

The Shoter tool **never** opens the saved PNG (the agent itself only saves; no `os.startfile`/`webbrowser.open`/`Image.show()` in `agents/shoter/shoter.py`). The popup risk lived only in the LLM reflexively calling `launch_view_image` after a screenshot — that risk is now closed off in the Shoter purpose string + the in-prompt routing line in `mcp_agent.py`.

Lint: `python -m ruff check` clean; `npm run lint` 0 errors (203 pre-existing warnings, none from this change). Tests: `agent.tests.ExecReportCaptureTests` (9 tests) + `agent.tests.AssignmentParserRobustnessTests` (14 tests, includes the sweep that scans every WRAPPED_CHAT_AGENT_SPECS example for conjunction leaks) all pass.
