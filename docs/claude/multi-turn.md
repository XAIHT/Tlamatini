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

## Create Flow from a Multi-Turn Answer

Every successful Multi-Turn response can be converted into a visual `.flw` workflow by clicking the **"Create Flow"** button rendered in the chat message header.

Pipeline:

1. **Tool-call log capture**: `MultiTurnToolAgentExecutor` in `mcp_agent.py` records each tool invocation into a per-request `_tool_calls_log`. Management tools (`chat_agent_stat_getter`, etc.) are excluded.
2. **Success classification**: `services/answer_analizer.py::analyze_answer_success()` asks the configured `chained-model` to classify the final answer as `SUCCESS` or `FAILURE`. It is a deliberate LLM-based classifier (no regex/keyword heuristics). On internal error it fails **open** (returns `True`) so the button is not hidden unnecessarily. Max answer length sent for classification is 4000 chars.
3. **WebSocket broadcast**: `consumers.py` attaches `tool_calls_log` and `answer_success` to the outgoing `agent_message` frame.
4. **Button gate (frontend)**: `agent_page_chat.js` renders the "Create Flow" button only when Multi-Turn was enabled, `answer_success` is true, the tool-call log is non-empty, and the user is not anonymous.
5. **Flow synthesis**: The frontend walks the tool-call log, maps each tool name to its sidebar agent display name, lays out nodes left-to-right, wires sequential `target_agents` connections, and emits a `.flw` JSON file that is downloaded by the browser.

Files involved:

- `agent/services/answer_analizer.py` — SUCCESS/FAILURE classifier
- `agent/services/response_parser.py` — strips `END-RESPONSE` sentinel and related artifacts
- `agent/mcp_agent.py` — `_tool_calls_log` accumulation and wrapped-agent dedup
- `agent/consumers.py` — broadcasts `tool_calls_log` + `answer_success`
- `agent/static/agent/js/agent_page_chat.js` — button render + `.flw` generator
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

Registered source agents: apirer, gitter, kuberneter, crawler, summarizer, prompter, flowcreator, file_interpreter, image_interpreter, file_extractor, kyber_keygen, kyber_cipher, kyber_decipher, gatewayer, gateway_relayer, googler.
