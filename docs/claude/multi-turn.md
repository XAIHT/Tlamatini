# Tlamatini — Multi-Turn Mode, Create Flow, Parametrizer Sections

## Multi-Turn Mode

When **Multi-Turn is checked** in the toolbar:
1. Prompt-shape validation is skipped
2. Request-scoped global execution plan/DAG is built
3. MCP contexts are prefetched selectively
4. Only planned tool subset is bound (default cap: **20 tools**, configurable via `max_selected_tools`)
5. Wrapped agents launch in headless/background mode
6. The MultiTurnToolAgentExecutor **deduplicates wrapped chat-agent calls** with identical arguments (prevents the LLM from launching the same sub-agent twice in a single request)
7. After the final answer, `services/answer_analizer.py` classifies the answer as SUCCESS/FAILURE and the frontend renders a **"Create Flow"** button on SUCCESS that converts the executed tool-call log into a downloadable `.flw` workflow

When **unchecked**: legacy one-shot behavior is preserved exactly.

The toggle is per-browser-session, sent as `multi_turn_enabled` with each request.

### Short Follow-Up Message Scoring

`global_execution_planner._select_planner_tool_names()` accepts a `chat_history_text` argument. When the current request is a short follow-up (≤4 meaningful tokens, e.g. "continue", "go ahead"), it boosts each capability's score with up to +15 points derived from the last 4 chat messages. This keeps tool context from evaporating on terse follow-ups and is wired in `rag/factory.py::_extract_chat_history_text()`.

---

## Ask Execs — per-tool permission prompt (Multi-Turn-only modifier)

The chat toolbar's fourth checkbox, **Ask Execs** (between **ACPX** and **Add internet context**), makes the Multi-Turn executor **BLOCK on a browser Proceed/Deny dialog before every state-changing Tool/MCP/Agent runs**. A **Deny halts the whole chain**. It is sent per-request as `ask_execs_enabled` and, like Exec report, is **only honoured while Multi-Turn is on** (the checkbox is disabled+greyed otherwise; every backend read re-gates it on `multi_turn_enabled`). Unchecked → byte-for-byte the legacy Multi-Turn flow.

### The bridge (sync executor ↔ async consumer)

The tool executor is synchronous and runs in a worker thread (`sync_to_async(ask_rag, thread_sensitive=False)`), so it cannot `await`. `agent/exec_permission.py::ExecPermissionBroker` bridges it:

1. `consumers.queue_llm_retrieval` registers one broker per request (keyed by `conversation_user.id`) when `ask_execs_enabled`, and unregisters it in a `finally`. Its emit callback schedules an `exec_permission_request` group frame onto the consumer's event loop via `asyncio.run_coroutine_threadsafe`.
2. In `MultiTurnToolAgentExecutor.invoke`'s per-tool loop — **after** the dedup + quota checks, **before** `tool.invoke` — if `_requires_exec_permission(tool_name)` (i.e. not in `_MANAGEMENT_TOOLS` ∪ `_TOOL_QUOTA_EXEMPT`), it calls `broker.request_permission(detail)` which emits the frame and **blocks on a `threading.Event`**.
3. The browser shows the modal (`showExecPermissionDialog`) and replies with an `exec-permission-response` frame → `consumers.receive` → `resolve_permission(user_id, request_id, decision)` sets the event.
4. **Proceed** → the tool runs. **Deny** → `self._exec_denied` is recorded and the executor returns immediately (no further tools, this turn or later).

The detail dict shown in the dialog: `tool_name`, `agent_display`, `kind` (Tool / Agent / MCP-ACPX / Skill via `_classify_tool_kind`), `program` (`_extract_exec_report_command`), `shell` (`_infer_execution_shell`), and pretty-printed `parameters`.

### Fail-safe contract (do NOT weaken)

- Emit failure / mid-flight Cancel / broker `close()` (browser disconnected) all resolve to **`deny`** — never run an unconfirmed state-changing tool. The wait loop polls `cancel_generation` on a short tick so a Cancel never deadlocks the thread.
- The **only** fail-OPEN case is "no broker registered" (unit tests / detached browser) — the consumer always registers one when `ask_execs_enabled`, so production never hits it.

### Runtime relax — unchecking Ask Execs mid-run (2026-05-29)

The flag captured at submit decides whether a broker is **registered** for the run; it cannot be un-captured. But the user CAN relax (or re-arm) an already-registered broker mid-flight by toggling the **Ask Execs** checkbox while a Multi-Turn run is executing:

1. The checkbox `change` handler (`agent_page_init.js`) sends a `set-ask-execs-runtime` frame (`{message, type, ask_execs_runtime_enabled}`) **only when `inLongOperation === true`**. The toolbar toggle checkboxes are deliberately NOT disabled by `disableControlsDuringOperation()`, so the box stays clickable during a run.
2. `consumers.receive` routes it to `exec_permission.set_broker_auto_proceed(user_id, auto_proceed=not enabled)`. Unchecked → `auto_proceed=True`; re-checked → `auto_proceed=False`. Returns `applied=False` (harmless no-op) if no broker is registered (run started with Ask Execs off — nothing to relax).
3. `ExecPermissionBroker.set_auto_proceed(True)` (a) makes every **future** `request_permission` return `"proceed"` immediately without emitting a prompt, and (b) resolves any **currently-blocking** prompt to `"proceed"` (mirrors `close()`, which resolves pending to `"deny"`). `set_auto_proceed(False)` re-arms prompting. It is a **no-op after `close()`** — a torn-down request never springs back to life.
4. When relaxing mid-run, the frontend also calls `dismissExecPermissionDialogForRuntimeProceed()` (`agent_page_dialogs.js`) to silently close any open prompt — it sets `_execPermDecisionSent = true` first so the dialog's close handler does NOT fire a stale `deny`.

Direction asymmetry by design: relaxing a run that **started** with Ask Execs **on** works (broker exists). Turning Ask Execs **on** mid-run for a run that started with it **off** does nothing that run (no broker was registered) — it takes effect on the next submit. Coverage: `ExecPermissionBrokerTests` (5 auto-proceed tests).

### Denial propagation + banner

`exec_report_denied` flows executor `_build_result_dict` → both chains' `result_dict` (independent of `exec_report_enabled`) → `interface.ask_rag` stores `last_exec_report_denied` in `global_state` → consumer reads+clears it → `services/response_parser.process_llm_response(..., exec_report_denied=...)` appends `_render_exec_denied_banner(...)` **after** the Exec report tables but **before** `save_message` (so a chat reload restores it). The banner (big red ⛔ "Execution interrupted") is NOT gated on the Exec report toggle.

### Whitelist contract (critical)

`ask_execs_enabled` **and** `conversation_user_id` (the executor finds its broker by user id) MUST stay in `UnifiedAgentChain.invoke`'s payload-rebuild whitelist — same drop-on-rebuild bug class that once broke `exec_report_enabled`. Both `UnifiedAgentChain` and `UnifiedAgentRAGChain` forward `ask_execs_enabled` + `ask_execs_user_id=conversation_user_id` into the executor sub-payload and return `exec_report_denied`. Adding a new payload flag here needs the same care. Both JS `exec-permission-response` frames include a `message` key because `consumers.receive` reads `text_data_json['message']` unconditionally. Full contract + coverage list in `docs/claude/recent-fixes.md` (2026-05-29).

---

## Create Flow from a Multi-Turn Answer

Every successful Multi-Turn response can be converted into a visual `.flw` workflow by clicking the **"Create Flow"** button rendered in the chat message header.

Pipeline:

1. **Tool-call log capture**: `MultiTurnToolAgentExecutor` in `mcp_agent.py` records each tool invocation into a per-request `_tool_calls_log`. Management tools (`chat_agent_stat_getter`, etc.) are excluded.
2. **Success classification**: `services/answer_analizer.py::analyze_answer_success()` asks the configured `chained-model` to classify the final answer as `SUCCESS` or `FAILURE`. It is a deliberate LLM-based classifier (no regex/keyword heuristics). On internal error it fails **open** (returns `True`) so the button is not hidden unnecessarily. Max answer length sent for classification is 4000 chars.
3. **WebSocket broadcast**: `consumers.py` attaches `tool_calls_log` and `answer_success` to the outgoing `agent_message` frame.
4. **Button gate (frontend)**: `agent_page_chat.js` renders the "Create Flow" button only when Multi-Turn was enabled, `answer_success` is true, the tool-call log is non-empty, and the user is not anonymous.
5. **Flow synthesis (frontend draft)**: The frontend walks the tool-call log, maps each tool name to its sidebar agent display name, lays out nodes left-to-right, wires sequential `target_agents` connections, and assembles a legacy-shaped `flowData` object.
6. **Backend normalization (`/agent/flow_from_tool_calls/`)**: `_normalizeChatFlowBeforeDownload()` POSTs the draft (plus the original `tool_calls_log`) to `flow_from_tool_calls_view`, which runs it through `flow_spec.normalize_flow_payload()` and returns `flow_spec_to_legacy_json(spec, redact=True)` — a registry-canonical `.flw` whose agent names match the contracts and whose `secret_paths` are stripped. **Failure mode**: if the request fails (offline frozen install, backend down) the browser falls back to the original legacy draft so the user still gets a usable file.
7. **Download**: Whichever shape comes back is `Blob`-wrapped and downloaded under a timestamped filename.

Files involved:

- `agent/services/answer_analizer.py` — SUCCESS/FAILURE classifier
- `agent/services/response_parser.py` — strips `END-RESPONSE` sentinel and related artifacts
- `agent/services/flow_spec.py` — `normalize_flow_payload` / `flow_spec_to_legacy_json` (called by `flow_from_tool_calls_view`)
- `agent/services/flow_compiler.py` — shared `compile_flow_payload` so chat-generated flows produce the same registry-canonical artifacts as canvas-generated ones
- `agent/mcp_agent.py` — `_tool_calls_log` accumulation and wrapped-agent dedup
- `agent/consumers.py` — broadcasts `tool_calls_log` + `answer_success`
- `agent/views.py::flow_from_tool_calls_view` — backend normalizer endpoint
- `agent/static/agent/js/agent_page_chat.js` — button render + `_generateAndDownloadFlow` (now `async`) + `_normalizeChatFlowBeforeDownload`
- `agent/static/agent/css/agent_page.css` — `.create-flow` button styling

---

## Unified Section Format (Parametrizer)

All 16+ section-generating agents use a single output format:

```
INI_SECTION_<AGENT_TYPE><<<
key1: value1
key2: value2

multi-line body content (becomes 'response_body')
>>>END_SECTION_<AGENT_TYPE>
```

Rules:
- `<AGENT_TYPE>` = UPPERCASE base name (e.g., APIRER, CRAWLER, GOOGLER)
- KV header before first blank line; body after first blank line
- Each section MUST be emitted in a **single `logging.info()` call** (atomic)
- One section per output unit (N results = N sections)

Registration (3 places):
1. `parametrizer.py` → `SECTION_AGENT_TYPES` list
2. `views.py` → `PARAMETRIZER_SOURCE_OUTPUT_FIELDS` dict
3. `README.md` → Supported Source Agents table

The generic parser (`_parse_section_content` + `_section_regex`) in `parametrizer.py` handles all agents with ~90 lines. No per-agent parser code needed.

Registered source agents: apirer, gitter, kuberneter, crawler, summarizer, prompter, flowcreator, file_interpreter, image_interpreter, file_extractor, kyber_keygen, kyber_cipher, kyber_decipher, gatewayer, gateway_relayer, googler, acpxer, shoter, camcorder, mouser, windower, unrealer, reviewer, analyzer, playwrighter, kalier.
