---
name: 8 fixes for desktop-UI Multi-Turn flow
description: 2026-05-07 batch fixing the "open notepad → type → wait → close" failure mode (15 iterations got force-stopped before Keyboarder ran)
type: project
originSessionId: 161aebfa-f2df-4d28-bcdf-e79b7579c58e
---
<!--
═══════════════════════════════════════════════════════════════════
  ✦  T L A M A T I N I  ✦   —   "one who knows"
  Created by  Angela López Mendoza   ·   @angelahack1
  Developer · Architect · Creator of Tlamatini
  Tlamatini Author Banner — do not remove (Angela's name is kept in every build)
═══════════════════════════════════════════════════════════════════
-->
The 2026-05-07 desktop-UI Multi-Turn run (`open notepad, type "Hi!, I'm Tlamatini", wait 30s, close`) got force-stopped at iteration 15 before reaching Keyboarder. Root cause was a stack of bugs; all 8 are now fixed in one batch on `main`.

**Why:** the user said "make a better Tlamatini, 'cause at this moment is so dumb". The failure trace was: `chat_agent_executer` ✅ → `chat_agent_shoter` ✅ → `chat_agent_image_interpreter` ❌×3 (`filetype_exclusions` false-positive) → status polling ⏳×4 → repetition breaker fired on 3 identical `chat_agent_run_status` calls → force stop. Keyboarder/Mouser were planner-selected but never reached.

**How to apply:** if these bugs reappear in a future trace, this commit is the reference for the fix set. Test suite (266 tests) shows zero regressions vs. baseline (5 pre-existing failures unrelated to this change).

## The 8 fixes (all on `main`)

1. **#2 Repetition breaker now ignores polling tools** — `mcp_agent.py::_call_signature` skips tools in `_TOOL_QUOTA_EXEMPT`; empty signature short-circuits the breaker. Polling `chat_agent_run_status` 5+ times while a child is `status=running` no longer trips the 3-call limit.
2. **#1 `_ConfigRequirementAnalyzer` no longer flags keys with explicit defaults as required** — `tools.py`. Track `keys_with_explicit_default` from `config.get(key, default)` calls; subtract them from `required_keys`. Fixes the `filetype_exclusions: ""` false-positive for image_interpreter, mover, deleter, file_extractor.
3. **#3 `prompt.pmt` rule 11 tightened** — desktop-UI lifecycle no longer recommends Image-Interpreter as a "did the window open?" gate. Adds explicit "DO NOT" + canonical 5-call pattern (`executer → keyboarder → sleeper → keyboarder alt+f4 → keyboarder alt+n`). Calls out `chat_agent_window_present` for fast yes/no checks.
4. **#7 Capability boost** — `capability_registry.py`. Added signal tokens for `chat_agent_keyboarder` (type, typed, keystrokes, press the keys, like I were typing, ...), `chat_agent_mouser` (click, double-click, drag, ...), `chat_agent_shoter`, `window_present`, `chat_agent_sleeper`, `chat_agent_run_wait`.
5. **#5 Shoter emits `INI_SECTION_SHOTER<<< output_path: ...>>>END_SECTION_SHOTER`** — `agents/shoter/shoter.py` + `parametrizer.py SECTION_AGENT_TYPES` + `views.py PARAMETRIZER_SOURCE_OUTPUT_FIELDS['shoter']`. Wrapped `chat_agent_shoter` now also surfaces `output_path` at the top of its result via the new generic `_maybe_promote_section_fields_to_payload` helper in `tools.py` (template_dir → field-tuple map). Canvas Shoter behavior unchanged.
6. **#6 `chat_agent_sleeper` wrapped tool** — registry entry + migration `0080_add_chat_agent_sleeper_tool.py`. `example_request="Sleep with duration_ms=30000"`. Canonical waiter — replaces "spin pythonxer for time.sleep" / "execute_command timeout /t".
7. **#4 `window_present(title)` direct @tool** — `tools.py`. Uses `pyautogui.getAllWindows()` + case-insensitive substring match. <100 ms yes/no helper. Returns `{present, matches[], match_count, title_query}`. Migration `0081` seeds the `Window-Present` Tool row.
8. **#8 `chat_agent_run_wait(run_id, max_seconds, poll_interval_seconds)` direct @tool** — `tools.py`. Server-side blocking poller; returns the same JSON as `chat_agent_run_status` once the run finishes (or `max_seconds` elapses). Replaces 5+ iteration polling loops on long-running wrapped agents (image_interpreter, crawler). Added to `_TOOL_QUOTA_EXEMPT`, `_RUN_CONTROL_TOOL_NAMES`, and `_EXTRA_HINTS_BY_TOOL_NAME`. Migration `0081` seeds the `Chat-Agent-Run-Wait` Tool row.

## Files touched (12 + 2 new migrations)

- `agent/mcp_agent.py` — repetition breaker (#2), `_TOOL_QUOTA_EXEMPT` adds `chat_agent_run_wait`/`window_present`
- `agent/tools.py` — `_ConfigRequirementAnalyzer` (#1), `_maybe_promote_section_fields_to_payload` (#5), `window_present` (#4), `chat_agent_run_wait` (#8), bind both into `get_mcp_tools`
- `agent/prompt.pmt` — rule 11 (#3)
- `agent/capability_registry.py` — signal tokens (#7), `_RUN_CONTROL_TOOL_NAMES` adds run_wait
- `agent/chat_agent_registry.py` — Shoter purpose rewrite (#5), `chat_agent_sleeper` spec (#6)
- `agent/agents/shoter/shoter.py` — emit `INI_SECTION_SHOTER<<<` block (#5)
- `agent/agents/parametrizer/parametrizer.py` — add `'shoter'` to SECTION_AGENT_TYPES (#5)
- `agent/views.py` — `PARAMETRIZER_SOURCE_OUTPUT_FIELDS['shoter']` (#5)
- `agent/migrations/0080_add_chat_agent_sleeper_tool.py` (new) — Tool row
- `agent/migrations/0081_add_window_present_and_run_wait_tools.py` (new) — Tool rows for `Window-Present` + `Chat-Agent-Run-Wait`

## Canvas / agentic control panel impact

None. All canvas behavior is preserved:
- Sleeper canvas template unchanged; the new wrapper is purely additive.
- Shoter canvas template still saves to `shoter_<n>` numbered subdirs and triggers `target_agents` identically; the only change is one extra log line (the INI_SECTION block). Parametrizer can now consume Shoter output (was previously incompatible).
- New direct @tools (`window_present`, `chat_agent_run_wait`) only appear in Tools dialog as toggleable rows.
