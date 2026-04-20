# Tlamatini — Exec Report (Per-Agent Execution Tables on the Final Answer)

When the **"Exec Report"** toolbar checkbox is ticked alongside Multi-Turn, the final answer gets a sequence of HTML tables appended to it — one table per kind of state-changing agent that actually fired, each row = one real tool call + SUCCESS/FAILURE verdict. It is the ground-truth "show-your-work" counterpart to the LLM's prose summary.

## Scope — what gets captured

Captured tools live in a single module-level map in `agent/mcp_agent.py`:

```python
_EXEC_REPORT_TOOLS: Dict[str, Tuple[str, str]] = {
    # (tool_name): (agent_key, agent_display)
    "execute_command":         ("executer",       "Executer"),
    "execute_file":            ("pythonxer",      "Pythonxer"),
    "unzip_file":              ("unzip",          "Unzip"),
    "decompile_java":          ("jdecompiler",    "J-Decompiler"),
    "chat_agent_executer":     ("executer",       "Executer"),
    "chat_agent_pythonxer":    ("pythonxer",      "Pythonxer"),
    "chat_agent_dockerer":     ("dockerer",       "Dockerer"),
    "chat_agent_kuberneter":   ("kuberneter",     "Kuberneter"),
    "chat_agent_ssher":        ("ssher",          "SSHer"),
    "chat_agent_scper":        ("scper",          "SCPer"),
    "chat_agent_pser":         ("pser",           "PSer"),
    "chat_agent_sqler":        ("sqler",          "SQLer"),
    "chat_agent_mongoxer":     ("mongoxer",       "Mongoxer"),
    "chat_agent_jenkinser":    ("jenkinser",      "Jenkinser"),
    "chat_agent_gitter":       ("gitter",         "Gitter"),
    "chat_agent_file_creator": ("filecreator",    "File Creator"),
    "chat_agent_move_file":    ("mover",          "Mover"),
    "chat_agent_deleter":      ("deleter",        "Deleter"),
    "chat_agent_apirer":       ("apirer",         "Apirer"),
    "chat_agent_send_email":   ("emailer",        "Emailer"),
    "chat_agent_telegramer":   ("telegramer",     "Telegramer"),
    "chat_agent_whatsapper":   ("whatsapper",     "Whatsapper"),
    "chat_agent_notifier":     ("notifier",       "Notifier"),
    "chat_agent_kyber_keygen": ("kyberkeygen",    "Kyber Keygen"),
    "chat_agent_kyber_cipher": ("kybercipher",    "Kyber Cipher"),
    "chat_agent_kyber_deciph": ("kyberdecipher",  "Kyber Deciph"),
}
```

Direct @tool calls and wrapped `chat_agent_*` launches that correspond to the same agent share an `agent_key` on purpose — their rows merge into one "List of <Agent> Operations" table. Read-only tools (Crawler, Googler, Prompter, Summarizer, File-Interpreter/Extractor, Image-Interpreter, Shoter, Monitor-*, Recmailer) and everything in `_MANAGEMENT_TOOLS` are intentionally absent.

## Pipeline

1. **Capture** — `MultiTurnToolAgentExecutor._invoke_tool()` checks `_EXEC_REPORT_TOOLS.get(tool_name)` after every tool invocation. If the tool is in the map, it appends `{tool_name, agent_key, agent_display, command, success}` to `self._exec_report_entries`. Capture is **unconditional** (ignores the per-request flag) — this prevents a future whitelist-style bug from silently hiding data.
2. **Flag** — `self._exec_report_enabled` is set from `payload["exec_report_enabled"]` at the start of `invoke()`. It only gates whether the entries are surfaced in the return dict under the `exec_report_enabled` key, not whether they are captured.
3. **Return** — `_build_result_dict()` always emits `exec_report_entries` (list) and `exec_report_enabled` (bool) alongside `output` and `tool_calls_log`.
4. **Chain forward** — `UnifiedAgentChain.invoke()` (and `UnifiedAgentRAGChain.invoke()`) pick up `exec_report_entries` from the executor's result and only add it to their own `result_dict` when the incoming payload had `exec_report_enabled=True`. **Note: `exec_report_enabled` is in `UnifiedAgentChain.invoke`'s payload-rebuild whitelist — removing it silently breaks the whole feature** (see Recent Fixes / Gotchas).
5. **Global state handoff** — `ask_rag()` in `rag/interface.py` stores `last_exec_report_enabled` and `last_exec_report_entries` in `global_state` after the chain returns.
6. **Consumer** — `AgentConsumer.queue_llm_retrieval()` reads from `global_state`, clears immediately (to prevent leakage into the next request), and passes both to `process_llm_response`.
7. **Render** — `_render_exec_report_html(entries)` in `services/response_parser.py` groups entries by `agent_key` in **first-appearance order** (not alphabetical) and emits one `<table class="exec-report-table exec-report-<agent_key>">` per unique agent, with caption `List of <agent_display> Operations`. Empty input returns `""`.
8. **Append** — `process_llm_response()` concatenates the HTML to `llm_response` before broadcasting over WebSocket, but only when `exec_report_enabled=True`.
9. **Persist (strict ordering contract)** — `save_message(bot_user, llm_response, ...)` **must run AFTER the exec-report HTML has been appended to `llm_response`**, not before. This is the only reason reloading the chat history restores the per-agent tables verbatim. The ordering inside `process_llm_response()` is therefore: (a) strip `END-RESPONSE` and artifacts, (b) run SUCCESS/FAILURE classification against the prose-only answer so exec-report tables don't bias the verdict, (c) append exec-report HTML, (d) **then** `save_message`, (e) broadcast over WebSocket. Moving `save_message` back above step (c) — as an earlier revision of the file did — silently breaks exec-report persistence across chat reloads while leaving the live-broadcast path working, which makes the regression invisible in manual testing until the user reloads the page. Do not reorder these steps.

## Success/failure classification

The verdict on each row comes from the existing `call_success` variable computed at the top of `_invoke_tool()` — `status ∈ ("error", "failed")` in JSON result → False, plain-string `"Error"` prefix or `"failed with return code"` → False, otherwise True. Do **not** introduce a separate classifier; the row verdict must match the tool-call verdict that Multi-Turn already uses for dedup, repetition detection, and the `tool_calls_log`.

## Styling contract

Each `agent_key` needs a matching `.exec-report-caption-<agent_key>` CSS rule in `agent/static/agent/css/agent_page.css`. The gradient must **mirror the `.canvas-item.<agent_key>-agent` rule in `agentic_control_panel.css`** so the table feels native to the agentic UI. Also add a `.exec-report-<agent_key> .exec-report-cmd { border-left: 3px solid <primary>; }` accent. Dark-captioned tables additionally need an entry in the selector list of the `thead th` dark-tinted override rule.

## Adding a state-changing agent to the report

Three edits (no JS, no backend plumbing, no tests to re-wire):

1. `agent/mcp_agent.py` → add one entry to `_EXEC_REPORT_TOOLS` — `("<tool_name>": ("<agent_key>", "<Display Name>"))`.
2. `agent/static/agent/css/agent_page.css` → add `.exec-report-caption-<agent_key>` + `.exec-report-<agent_key> .exec-report-cmd` rules using the canvas-item gradient.
3. If the caption background is dark, also add `.exec-report-<agent_key> thead th` to the `color: #f5f5f5; background: rgba(0, 0, 0, 0.55)` selector list.

Then run `python manage.py test agent.tests.ExecReportCaptureTests` — the existing test set exercises capture + grouping + render-order + flag-gating generically, so no per-agent test is needed.

## Files involved

- `agent/mcp_agent.py` — `_EXEC_REPORT_TOOLS`, `_extract_exec_report_command`, `_invoke_tool` capture, `_build_result_dict` emission
- `agent/rag/chains/unified.py` — payload whitelist **must** include `exec_report_enabled`; forward `exec_report_entries` on the way back
- `agent/rag/interface.py` — `global_state` handoff (`last_exec_report_enabled`, `last_exec_report_entries`)
- `agent/consumers.py` — `queue_llm_retrieval` reads state, passes to parser
- `agent/services/response_parser.py` — `_render_exec_report_html(entries)` + append-to-answer in `process_llm_response`
- `agent/static/agent/css/agent_page.css` — per-agent caption gradient and command-cell accent rules
- `agent/static/agent/js/agent_page_state.js`, `agent_page_init.js` — checkbox state + `exec_report_enabled` in WebSocket send
- `agent/templates/agent/agent_page.html` — **Exec Report** toolbar checkbox
- `agent/tests.py` — `ExecReportCaptureTests` (6 tests) + regression guards in `LoadedContextFallbackTests`
