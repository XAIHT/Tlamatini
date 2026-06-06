---
name: Keyboarder wrapped as chat_agent_keyboarder
description: 2026-05-07 — Keyboarder + Shoter usable from Multi-Turn; chat_agent_keyboarder added to registry, _EXEC_REPORT_TOOLS, CSS, prompt; migration 0078
type: project
originSessionId: 63bc7c5f-89b5-4e8f-910d-9a3a70bdb9a3
---
2026-05-07: Added `chat_agent_keyboarder` so Multi-Turn can drive desktop UI (open notepad → screenshot/verify → type via Keyboarder).

Changes (all on `main`):

- `agent/chat_agent_registry.py`: new `ChatWrappedAgentSpec(key="keyboarder", template_dir="keyboarder", tool_name="chat_agent_keyboarder", ...)` with rich security_hints around typing/keystrokes/hotkeys; also enriched the existing Shoter spec with verification-step hints.
- `agent/mcp_agent.py`: added `"chat_agent_keyboarder": ("keyboarder", "Keyboarder")` to `_EXEC_REPORT_TOOLS` (state-changing — keystrokes target foreground window). Shoter stays out of the report on purpose (read-only). Also added a Keyboarder line to the in-prompt TOOL SELECTION GUIDE.
- `agent/migrations/0078_add_chat_agent_keyboarder_tool.py`: seeds `Tool` row with `toolDescription="Chat-Agent-Keyboarder"`.
- `agent/static/agent/css/agent_page.css`: added `.exec-report-caption-keyboarder` (red→orange→yellow→green gradient mirroring `.canvas-item.keyboarder-agent`), added `.exec-report-keyboarder thead th` to the dark-captioned override list, added `.exec-report-keyboarder .exec-report-cmd` left-border accent (`#F44336`).
- Docs: `docs/claude/exec-report.md` (registry + read-only-list note), `docs/claude/gotchas.md` (new entry above the "Wrapped-agent assignment parser" entry).

**Why:** The user's prompt was "Tlamatini, open the notepad, verify it is opened and waiting for input and then write just If I were typing: 'Hi, I'm Tlamatini'". Without Keyboarder being wrapped, the LLM had no way to drive the keyboard from Multi-Turn.

**How to apply:** When the user wants Multi-Turn to type into a real desktop window, hit a hotkey, or replay a key sequence, use `chat_agent_keyboarder` with `input_sequence="..."` (literal text in single/double quotes; key names and `+`-joined chords go bare; comma-separated tokens) and optional `stride_delay=<ms>`. Pair with `execute_command` to launch the target app and `chat_agent_shoter` (+ `chat_agent_image_interpreter`) to verify it's ready before typing. Keyboarder normalizes pyautogui key names via `get_pyautogui_key()` (`escape→esc`, `windows→win`, `altgr→altright`, `mayus/caps→capslock`).

Lint: `python -m ruff check` clean; `npm run lint` 0 errors (203 pre-existing warnings, none from this change).
