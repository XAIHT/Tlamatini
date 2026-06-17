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
    # Playwrighter is state-changing — it drives a real browser, submits
    # forms, logs into sites and downloads files. Read-only steps
    # (extract_text/screenshot) share the same agent_key so a mixed flow
    # renders as one "List of Playwrighter Operations" table.
    "chat_agent_playwrighter": ("playwrighter",   "Playwrighter"),
    "chat_agent_send_email":   ("emailer",        "Emailer"),
    "chat_agent_telegramer":   ("telegramer",     "Telegramer"),
    "chat_agent_whatsapper":   ("whatsapper",     "Whatsapper"),
    "chat_agent_notifier":     ("notifier",       "Notifier"),
    "chat_agent_kyber_keygen": ("kyberkeygen",    "Kyber Keygen"),
    "chat_agent_kyber_cipher": ("kybercipher",    "Kyber Cipher"),
    "chat_agent_kyber_deciph": ("kyberdecipher",  "Kyber Deciph"),
    # Keyboarder is state-changing — keystrokes target the foreground
    # window. Shoter remains read-only (it only observes the screen).
    "chat_agent_keyboarder":   ("keyboarder",     "Keyboarder"),
    # Mouser is state-changing — moving the pointer and clicking fires
    # button events at whatever window is at the target coordinates and
    # may switch the foreground window. Captured under its own agent_key.
    "chat_agent_mouser":       ("mouser",         "Mouser"),
    # Windower is state-changing — it moves / resizes / minimizes / maximizes
    # / restores / closes / pins application windows (focus-only and the
    # read-only ``list`` action share the same agent_key so a mixed flow
    # renders as one "List of Windower Operations" table).
    "chat_agent_windower":     ("windower",       "Windower"),
    # Kalier is state-changing — it drives Kali offensive-security tooling
    # (nmap / gobuster / nikto / sqlmap / metasploit / hydra / john / ...) and
    # arbitrary shell commands on a Kali box via the MCP-Kali-Server API. The
    # read-only ``health`` probe shares the ``kalier`` agent_key so a mixed
    # flow renders as one "List of Kalier Operations" table.
    "chat_agent_kalier":       ("kalier",         "Kalier"),
    # ACPX child-process launchers and the Skill harness invoker —
    # spawn / send / send_and_wait / kill / relay all share the ``acpx``
    # agent_key so they merge into one "List of ACPx Operations" table;
    # invoke_skill gets its own ``skill`` table.
    "acp_spawn":               ("acpx",           "ACPx"),
    "acp_send":                ("acpx",           "ACPx"),
    "acp_send_and_wait":       ("acpx",           "ACPx"),
    "acp_kill":                ("acpx",           "ACPx"),
    "acp_relay":               ("acpx",           "ACPx"),
    "invoke_skill":            ("skill",          "Skill"),
}
```

Direct @tool calls and wrapped `chat_agent_*` launches that correspond to the same agent share an `agent_key` on purpose — their rows merge into one "List of <Agent> Operations" table.

### ⚠️ Completeness contract (2026-06-07): EVERY Multi-Turn agent is captured — `_EXEC_REPORT_TOOLS` is no longer the gate

The map above is **no longer the gate for *whether* an agent is captured.** The Exec report must show **every agent that actually runs during a Multi-Turn request** — observational/output agents (Talker, Whisperer, Shoter, Camcorder, Recorder, AudioPlayer, VideoPlayer), read-only LLM agents (Crawler, Prompter, Summarizer, File-Interpreter/Extractor, Image-Interpreter, Monitor-*, Recmailer, Asker, Sleeper), AND any **newly-created** agent — all of them. (Previously the observational/read-only agents were intentionally absent; that produced the bug where a Talker run with Exec-report ON generated **no tables at all**.)

Capture is now driven by **`mcp_agent.py::_resolve_exec_report_spec(tool_name)`**, which resolves in order: (1) the curated `_EXEC_REPORT_TOOLS` map (still wins — for shared agent_keys that merge a direct @tool with its wrapped launch, nicer display casing, and a CSS-matched caption gradient); (2) a **generic fallback** that captures ANY wrapped `chat_agent_*` not in `_MANAGEMENT_TOOLS`, deriving `agent_key` from the registry spec key (separators stripped) and `agent_display` from `spec.display_name`. So a brand-new Multi-Turn agent is captured the instant it is wired as a `chat_agent_*` tool, with **zero** changes to `_EXEC_REPORT_TOOLS`.

The ONLY tools never captured: the management/polling helpers in `_MANAGEMENT_TOOLS` (`chat_agent_run_*`, `window_present`, `agent_stat_getter`, `get_current_time`) and direct read-only @tools (`googler`, `launch_view_image`). The visual canvas ACPXer node is not an LLM tool so it still contributes no rows. Entries in `_EXEC_REPORT_TOOLS` are therefore an **optional refinement**, not a requirement — a Multi-Turn agent with no entry there is still captured via the generic fallback and rendered with the default caption background (`.exec-report-caption` in `agent_page.css`).

**Worked example — MCP Doctor (`chat_agent_mcp_doctor`)**: the newest Multi-Turn agent has **no** `_EXEC_REPORT_TOOLS` entry, yet it is captured automatically by `_resolve_exec_report_spec` (generic fallback → `agent_key="mcpdoctor"`, display `MCP Doctor`) and renders with the default caption. This is the expected behavior for every new wrapped `chat_agent_*` — no Exec-report code is written.

**NOT captured — the External MCP surface.** The 8 External-MCP supervisor tools (`external_mcp_status` / `reconnect` / `doctor` / `list_tools` / `call` / `import` / `set_active` / `wait`) and the lazily-bound `ext__<server>__<tool>` remote tools are **not** in the Exec Report — they are not `chat_agent_*` tools and so do not hit the wrapped-agent fallback (and they are not in `_EXEC_REPORT_TOOLS`). The static **MCP Doctor agent** (`chat_agent_mcp_doctor`) IS captured (above); the live `external_mcp_*` tools are not.

**Note on the visual ACPXer agent**: ACPXer is a *canvas* workflow node, not an LLM-invoked tool, so it does NOT contribute rows to `_EXEC_REPORT_TOOLS`. The Exec Report only covers tools the LLM calls in Multi-Turn mode. When the LLM drives ACPX via `acp_spawn` / `acp_send` / `acp_send_and_wait` / `acp_kill` / `acp_relay`, those calls already merge into the "List of ACPx Operations" table under `agent_key="acpx"`. If a future wrapped chat-agent (`chat_agent_acpxer`) is added so the LLM can launch the visual ACPXer node from chat, register it as `("chat_agent_acpxer", ("acpxer", "ACPXer"))` so it gets its own table — distinct from the existing `acpx` rows, since the visual surface is a different operational concept (one canvas node = one full lifecycle, vs. the 12 tools' fine-grained primitives).

## Pipeline

1. **Capture** — `MultiTurnToolAgentExecutor._invoke_tool()` checks `_EXEC_REPORT_TOOLS.get(tool_name)` after every tool invocation. If the tool is in the map, it appends `{tool_name, agent_key, agent_display, command, success}` to `self._exec_report_entries`. Capture is **unconditional** (ignores the per-request flag) — this prevents a future whitelist-style bug from silently hiding data. **Capture also fires on the `tool.invoke(...)` exception path** with `success=False`, so ACPX/Skill rows still appear when the underlying CLI is missing on PATH, the harness raised, or the args were malformed (exactly the cases the user most needs to see). `_extract_exec_report_command(tool_input, tool_name)` is tool-name-aware: ACPX `acp_spawn` renders as `[<agent_id>] <task>`, `acp_send` as `[<session_id>] <text>`, `acp_kill` as `kill <session_id>`, and `invoke_skill` as `<skill_name>(<args>)`.
2. **Flag** — `self._exec_report_enabled` is set from `payload["exec_report_enabled"]` at the start of `invoke()`. It only gates whether the entries are surfaced in the return dict under the `exec_report_enabled` key, not whether they are captured.
3. **Return** — `_build_result_dict()` always emits `exec_report_entries` (list) and `exec_report_enabled` (bool) alongside `output` and `tool_calls_log`.
4. **Chain forward** — `UnifiedAgentChain.invoke()` (and `UnifiedAgentRAGChain.invoke()`) pick up `exec_report_entries` from the executor's result and only add it to their own `result_dict` when the incoming payload had `exec_report_enabled=True`. **Note: `exec_report_enabled` is in `UnifiedAgentChain.invoke`'s payload-rebuild whitelist — removing it silently breaks the whole feature** (see `docs/claude/recent-fixes.md`).
5. **Global state handoff** — `ask_rag()` in `rag/interface.py` stores `last_exec_report_enabled` and `last_exec_report_entries` in `global_state` after the chain returns.
6. **Consumer** — `AgentConsumer.queue_llm_retrieval()` reads from `global_state`, clears immediately (to prevent leakage into the next request), and passes both to `process_llm_response`.
7. **Render** — `_render_exec_report_html(entries)` in `services/response_parser.py` groups entries by `agent_key` in **first-appearance order** (not alphabetical) and emits one `<table class="exec-report-table exec-report-<agent_key>">` per unique agent, with caption `List of <agent_display> Operations`. Empty input returns `""`.
8. **Append (boundary-isolated)** — `process_llm_response()` joins the exec-report HTML onto `llm_response` **only when `exec_report_enabled=True`**, but it does NOT bare-concatenate: it prefixes the system section (exec tables + any denial banner) with the `EXEC_REPORT_BOUNDARY` sentinel (`<!--TLAMATINI_EXEC_REPORT_BOUNDARY-->`). The frontend (`agent_page_chat.js::buildAutomatedMessageElement`) splits on that marker and parses each half in its **own `innerHTML`**, so a malformed/unclosed HTML answer table can never foster-parent the exec tables into itself. **Keep the `EXEC_REPORT_BOUNDARY` constant byte-identical in `response_parser.py` and `agent_page_chat.js`.** See `docs/claude/recent-fixes.md` (2026-06-05).
9. **Persist (strict ordering contract)** — `save_message(bot_user, llm_response, ...)` **must run AFTER the exec-report HTML has been appended to `llm_response`**, not before. This is the only reason reloading the chat history restores the per-agent tables verbatim. The ordering inside `process_llm_response()` is therefore: (a) strip `END-RESPONSE` and artifacts, (b) run SUCCESS/FAILURE classification against the prose-only answer so exec-report tables don't bias the verdict, (c) append exec-report HTML, (c2) append the **Ask-Execs denial banner** if `exec_report_denied` is present (see below), (d) **then** `save_message`, (e) broadcast over WebSocket. Moving `save_message` back above step (c) — as an earlier revision of the file did — silently breaks exec-report persistence across chat reloads while leaving the live-broadcast path working, which makes the regression invisible in manual testing until the user reloads the page. Do not reorder these steps.

## Interplay with Ask Execs (the denial banner)

When the **Ask Execs** toggle is on (a Multi-Turn-only modifier — see `docs/claude/multi-turn.md`) and the user **denies** a tool, the executor halts the chain and emits `exec_report_denied` alongside `exec_report_entries`. Two consequences for the Exec report:

- The **denied tool never executed**, so it does **not** appear in `exec_report_entries` — only the tools that actually ran (before the denial) are captured, exactly as for any normal run.
- `services/response_parser._render_exec_denied_banner(exec_report_denied)` renders a big red "Execution interrupted" banner naming the denied Tool/MCP/Agent + its program/shell/parameters. It is appended in `process_llm_response()` **after** the exec-report tables (step c2 above) and **before** `save_message`, so the user sees what *did* run, then the stop. **The banner is independent of `exec_report_enabled`** — it always shows on a denial; only the tables are gated on the toggle. CSS lives in `agent_page.css` under `.exec-denied-*`.

## Success/failure classification

The verdict on each row comes from the existing `call_success` variable computed at the top of `_invoke_tool()` — `status ∈ ("error", "failed")` in JSON result → False, plain-string `"Error"` prefix or `"failed with return code"` → False, otherwise True. Do **not** introduce a separate classifier; the row verdict must match the tool-call verdict that Multi-Turn already uses for dedup, repetition detection, and the `tool_calls_log`.

## Styling contract

Each `agent_key` needs a matching `.exec-report-caption-<agent_key>` CSS rule in `agent/static/agent/css/agent_page.css`. The gradient must **mirror the `.canvas-item.<agent_key>-agent` rule in `agentic_control_panel.css`** so the table feels native to the agentic UI. Also add a `.exec-report-<agent_key> .exec-report-cmd { border-left: 3px solid <primary>; }` accent. Dark-captioned tables additionally need an entry in the selector list of the `thead th` dark-tinted override rule.

## Adding an agent to the report (MANDATORY: every Multi-Turn agent must appear)

**Capture is now automatic.** Any agent you make Multi-Turn-callable (a wrapped `chat_agent_<name>` tool — see `create_new_agent.md` Step 7.5) is captured by `_resolve_exec_report_spec` with **no Exec-report code at all**, and rendered with the default caption background. So the baseline requirement is simply:

0. **(MANDATORY) Verify** your new Multi-Turn agent shows up: run it in Multi-Turn with **Exec report ON** and confirm a "List of <Agent> Operations" table appears. A Multi-Turn agent that produces no Exec-report row is a defect (this was the Talker bug). `python manage.py test agent.tests.ExecReportCaptureTests` includes an AUDIT test (`test_every_multiturn_agent_is_capturable_including_observational`) that fails if ANY wrapped chat-agent resolves to no row — so a regression is caught automatically.

**Optional refinement** (nicer styling / shared keys) — only if you want a native caption gradient or to merge a direct @tool with its wrapped launch:

1. `agent/mcp_agent.py` → add one entry to `_EXEC_REPORT_TOOLS` — `"<tool_name>": ("<agent_key>", "<Display Name>")` (use this to share an `agent_key` between a direct @tool and its `chat_agent_*` launch, or to fix the display casing the generic fallback derives).
2. `agent/static/agent/css/agent_page.css` → add `.exec-report-caption-<agent_key>` + `.exec-report-<agent_key> .exec-report-cmd` rules using the canvas-item gradient (otherwise the readable default `.exec-report-caption` background is used).
3. If the caption background is dark, also add `.exec-report-<agent_key> thead th` to the `color: #f5f5f5; background: rgba(0, 0, 0, 0.55)` selector list.

Then run `python manage.py test agent.tests.ExecReportCaptureTests` — the set exercises capture + grouping + render-order + flag-gating + the all-agents audit generically, so no per-agent test is needed.

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
