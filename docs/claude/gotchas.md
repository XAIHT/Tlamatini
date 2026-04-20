# Tlamatini — Gotchas, Build/Lint, Roadmap, Work Style

## Claude API Client (opus_client)

Located in `agent/opus_client/claude_opus_client.py`. Features:
- Text chat, image analysis, PDF analysis, streaming
- Multi-turn conversations with `create_conversation()`
- Tool/function calling with auto-execution
- Models: `Model.OPUS_4_5`, `Model.SONNET_4_5`, `Model.HAIKU_4_5`

```python
from claude_opus_client import ClaudeClient
client = ClaudeClient()
response = client.chat("Hello")
```

---

## Building & Packaging

```bash
# Step 1: Build the app
python build.py

# Step 2: Build the uninstaller
python build_uninstaller.py

# Step 3: Build the installer
python build_installer.py
```

The frozen build resolves paths via `os.path.dirname(sys.executable)` vs source mode `os.path.dirname(os.path.abspath(__file__))`. Both modes must be supported in any new tool.

---

## Linting

```bash
# Python
python -m ruff check

# JavaScript/CSS
npm run lint
```

---

## Known Hardcoded Assumptions

1. `factory.py` recognizes only `System-Metrics` and `Files-Search` by Mcp description
2. Frontend MCP dialog is hardcoded for two checkboxes
3. Tool UI is dynamic; MCP UI is not
4. `get_mcp_tools()` returns LangChain tools, not MCP services
5. `ask_rag()` does not fetch MCP data itself
6. Files-Search main path uses `FileSearchRAGChain`, not `mcp_files_search_client.py`
7. `mcp_files_search_client_uri` in config is unused by the main chain
8. `FileSearchRAGChain` falls back to `localhost:50051` for gRPC
9. Tool status keys are handwritten and can drift
10. `mcpContent` is stored as string, not boolean
11. Planner default `max_selected_tools` was lowered from 50 → **20** to prevent keyword inflation from selecting every tool on a single request
12. `tlamatini.log` is truncated on every server start (mode `'w'`) and has no rotation

---

## Recent Fixes / Gotchas (keep these in mind)

- **Planner statelessness on short follow-ups** — Solved by passing `chat_history_text` into the planner and boosting capability scores. If you touch `_select_planner_tool_names()` or `build_global_execution_plan()`, preserve this argument.
- **Wrapped chat-agent dedup** — `MultiTurnToolAgentExecutor` hashes `tool_name + sorted-JSON args` into `_wrapped_agent_signatures` and short-circuits duplicates with a `ToolMessage` explaining the skip. Do not remove this without replacing it; the LLM reliably launches the same sub-agent twice otherwise.
- **Googler Playwright + async loop** — `sync_playwright()` raises `NotImplementedError` inside Django Channels' running asyncio loop. The Googler tool wraps its Playwright work in a `ThreadPoolExecutor(max_workers=1)` with a 120s timeout. Any new sync-Playwright tool must do the same.
- **Cancel/rebuild race** — `consumers.py` now `await`s `setup_rag_chain()` during cancel-current instead of `asyncio.create_task(...)`. Otherwise the client receives `MSG_LLM_REESTABLISHED` while the httpx client is still torn down, and the next request hits "Cannot send a request, as the client has been closed." All `getHttpxClientInstance()` callers must also guard against `None`.
- **Exec-report persistence ordering** — In `services/response_parser.py::process_llm_response()`, `save_message(bot_user, llm_response, ...)` must run AFTER the exec-report HTML is appended to `llm_response`, otherwise the tables live only in the broadcast and vanish from chat history on page reload. An earlier revision saved the message before the append step; the fix (commit `e99d2b8`) reorders the operations to: classify → append exec-report HTML → save → broadcast. See the "Exec Report" pipeline step 9 in `docs/claude/exec-report.md` for the full contract. Do not reorder these steps.
- **ACP canvas DOM split (`#canvas-content` vs `#submonitor-container`)** — The ACP canvas is scrollable (commit `9249349`). `#submonitor-container` is the viewport with scrollbars; `#canvas-content` is the content layer where items, the SVG connections layer, and the rubber-band selection box live. All coordinate math (`createCanvasItem`, `makeDraggable`, `startSelectionBox`, `getCenter`, tempPath drawing in `initCanvasEvents`) must use `canvasContent.getBoundingClientRect()`, which already reflects scroll offset — do NOT add `submonitor.scrollLeft/scrollTop` manually, and do NOT append new items to `submonitor`. Item positions are clamped `>= 0` only; the canvas grows to the right/bottom via `updateCanvasContentSize()` in `acp-globals.js`, which must be called after item creation, drag end, .flw load, and undo/redo restoration. Full contract in "ACP Canvas DOM Contract" section of `docs/claude/frontend.md`.

---

## Recommended New Agents (Roadmap)

From `NEW_AGENT_RECOMMENDATIONS.md`:

| Priority | Agent | Purpose |
|----------|-------|---------|
| 1 | **Tester** | Test runner (pytest, jest, junit) with pass/fail routing |
| 2 | **Reviewer** | AI code review (LLM-powered diff analysis) |
| 3 | **Analyzer** | Static analysis (Ruff, ESLint, Bandit) |
| 4 | **Jiraer** | Issue tracker integration (Jira/GitHub Issues) |
| 5 | **Logger** | Structured log writer / report aggregator |
| 6 | **Vaulter** | Secrets / environment injection |
| 7 | **Webhooker** | Webhook listener (inbound HTTP endpoint) |
| 8 | **Terraformer** | Infrastructure as Code (Terraform/Pulumi) |
| 9 | **Metrixer** | Metrics collector (Prometheus/Grafana) |
| 10 | **Diffr** | File/content comparison |
| 11 | **Zipper** | Archive creation (ZIP/TAR) |

---

## Work Style Preferences (for AI assistants)

- When given a broad directive ("Go!", "modify everything"), execute comprehensively across all relevant files without asking for confirmation at each step
- Use parallel subagents to maximize throughput
- Read broadly first, plan the full scope, then execute in parallel batches
- Only ask for confirmation on truly ambiguous architectural decisions
- The developer values robustness ("bullet-proof") and uniformity in system design
- Comfortable with large cross-cutting changes (16+ files in one session)
