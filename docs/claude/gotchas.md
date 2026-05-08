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

- **ACPX `oneshot-prompt` is the only path that captures TUI agents on Windows** — `claude`, `gemini`, `cursor`, `qwen`, and `codex` are all configured with `transport="oneshot-prompt"` in `agent/acpx/agent_registry.py::DEFAULT_ACP_AGENTS`. They were previously `json-acp` (claude/codex) or `tui-repl` (the others), and the transcript only contained the OUTBOUND prompt — the answer was lost because TUI CLIs detect a piped stdout and refuse to flush. The fix re-spawns the CLI fresh per turn with the prompt as a CLI argument behind `prompt_arg_flag` (`-p` for claude/cursor/gemini/qwen) or `prompt_subcommand_args` (`["exec"]` for codex), closes stdin immediately, and captures stdout to EOF via `proc.communicate(timeout=180)`. Inter-turn session state inside the child does NOT persist (each turn is a brand-new process) — caller must include prior context in the next prompt if continuity is required. Implementation: `AcpSession._oneshot_send_turn` in `agent/acpx/runtime.py` and the mirrored `run_oneshot_prompt` in `agent/agents/acpxer/acpxer.py` (the canvas counterpart). DO NOT revert these to long-lived stdin-fed children; the only thing you'll capture is the outbound prompt, and the user will report responses like "the transcript only shows the outbound prompts, not the inbound responses." Coverage: `OneshotPromptCaptureTests` in `agent/acpx/tests.py` (4 tests) plus `AgentRegistryTransportProfileTests.test_oneshot_prompt_agents_have_capture_path` pin the contract.

- **ACPXer self-contained (do NOT import `agent.acpx.runtime` in pool agents)** — The ACPXer workflow agent (`agent/agents/acpxer/acpxer.py`) is a visual-canvas counterpart of the 12 LLM-facing `acp_*` tools, BUT it does not — and must not — import from `agent.acpx`. Workflow agents in the pool run as separate Python subprocesses started via the user's system Python (or a bundled python.exe in frozen builds); they have no `sys.path` back into the Django app, so `from agent.acpx import AcpxRuntime` would `ModuleNotFoundError`. The agent therefore mirrors the runtime's transport-aware drain (4 completion rules: `done:true` envelope / child exit / hard timeout / transport-aware idle), the `agent_id` registry (claude/codex/tlamatini = json-acp, gemini/cursor/qwen/etc = tui-repl), and the NDJSON transcript format inline in ~120 lines. The transcript format is byte-identical to what `agent.acpx.runtime.AcpSession.send_turn` writes, so transcripts produced by ACPXer are interchangeable with those produced by `acp_spawn`. If you ever consolidate the two implementations into a shared package, the package must NOT live under `agent.*` — extract it to a top-level path that's importable from a fresh subprocess (or vendor it as a wheel that ships with the agent pool).
- **ACPX toolbar toggle filters the entire ACPX/Skill tool surface per-request — and now defaults to OFF** — `agent/acpx/__init__.py` exposes `ACPX_TOOL_NAMES` (the 12 LLM-facing ACPX/Skill tool names) and `filter_acpx_tools(tools, acpx_enabled)`. The chat toolbar's third checkbox (`#acpx-enabled` in `templates/agent/agent_page.html`) **starts unchecked** on a fresh session — JS hydration in `agent_page_state.js::applyStoredAcpxState` falls back to `false` when sessionStorage has no prior value — and every backend read site defaults `acpx_enabled` to `False` (`rag/interface.py::ask_rag` for both dict and raw-string payloads, `rag/factory.py`, `rag/chains/unified.py` payload-rebuild whitelist in three places, `mcp_agent.py::CapabilityAwareToolAgentExecutor.invoke`, and `consumers.py::receive` plus the `queue_llm_retrieval` signature). When the user explicitly ticks the box the planner / executor get the ACPX/Skill tools; otherwise those tool names are filtered out. **Do NOT remove the `acpx_enabled` key from `UnifiedAgentChain.invoke`'s payload-rebuild whitelist** in `rag/chains/unified.py` — it lives next to `multi_turn_enabled` and `exec_report_enabled` and the same drop-on-rebuild bug class applies. When the flag is unticked, `bypass_prompt_validation` is computed as `multi_turn_enabled OR acpx_enabled`, which means a request with neither flag set still goes through the normal prompt-shape validator.

- **Summarizer one-shot mode (`input_text` + `target_words`)** — `agent/agents/summarizer/summarizer.py` now accepts a one-shot path: when `input_text` is non-empty AND `source_agents` is empty, the agent skips the polling loop entirely, sends `input_text` directly to the LLM, emits exactly one `INI_SECTION_SUMMARIZER<<<` block (so Parametrizer / Exec Report consume the result the same way they consume a polling-mode summary), and triggers `target_agents` whenever the summary is non-empty. The chat tool `chat_agent_summarize_text` (registered in `chat_agent_registry.py`, `template_dir="summarizer"`) is the canonical caller — its `example_request` is `input_text='<full text>' and target_words=40`. Pre-existing canvas behavior (polling `source_agents` for `[EVENT_TRIGGERED]`) is unchanged when `input_text` is left at its default empty string. Coverage: the agent's own log shows `One-shot input_text length: <N> chars; target_words=<M>` so a quick grep of `summarizer_<n>.log` confirms which path fired.

- **`setup-new-acpx-key` skill is the canonical key-injection path** — When the user wants to plug a new credential into an ACPX `agent_id` (claude/codex/cursor/gemini/qwen/...), prefer `invoke_skill('setup-new-acpx-key', {...})` over hand-editing config.json. The skill's SKILL.md (`agent/skills_pkg/setup_new_acpx_key/SKILL.md`) is the single source of truth for the canonical env-var map (claude → `ANTHROPIC_API_KEY`, gemini → `GEMINI_API_KEY` + `GOOGLE_API_KEY` alias, codex → `OPENAI_API_KEY`, qwen → `DASHSCOPE_API_KEY`) and the two-layer config.json wiring (top-level for callers like `image_interpreter.py` / `opus_client.py`; `acpx.agents.<id>.env` for the spawned child). The merge order is `{**os.environ, **spec.env}`, so explicit `acpx.agents.<id>.env` wins over an exported shell variable. The skill also patches `regen_secrets.py` when introducing a brand-new key, keeping the push-able / keyed toggle accurate.

- **`regen_secrets.py` is a two-mode scrubber/restorer for config.json** — `python regen_secrets.py --mode push-able` rewrites real secrets in `Tlamatini/agent/config.json` (top-level `ANTHROPIC_API_KEY` / `GEMINI_API_KEY` / `OLLAMA_TOKEN` and the `acpx.agents.<id>.env` blocks) into placeholders like `<ANTHROPIC_API_KEY goes here>` so the file is safe to commit. `--mode keyed` restores the values from `data.keys` (gitignored, `KEY=VALUE` format) so the local working tree stays usable. The same script is the splat target after editing `data.keys`. **Never commit `data.keys`** — line 265 of `.gitignore` already excludes it but a `git add -A` could accidentally stage it from a fresh checkout if the line drifts; verify with `git status` before pushing.

- **Keyboarder + Shoter usable from Multi-Turn (`chat_agent_keyboarder` / `chat_agent_shoter`)** — Both desktop-UI agents are wrapped chat-agent tools. Shoter (`chat_agent_shoter`) was already registered (read-only screenshot capture). Keyboarder (`chat_agent_keyboarder`) is now wrapped too — it accepts `input_sequence` (literal text in single/double quotes; key names and `+`-joined chords go bare; comma-separated tokens) and `stride_delay` (ms between strokes), exactly mirroring `agents/keyboarder/config.yaml`. This unblocks the canonical "open notepad → verify → type into it" flow: `execute_command(notepad)` → `chat_agent_shoter` (+ optional `chat_agent_image_interpreter` to confirm the window is ready) → `chat_agent_keyboarder` to type. Keyboarder is state-changing (keystrokes target the foreground window), so it lives in `_EXEC_REPORT_TOOLS` under `agent_key="keyboarder"` with its own caption gradient (`#F44336 → #FF9800 → #FFEB3B → #4CAF50`, mirroring `.canvas-item.keyboarder-agent`). Shoter remains read-only and stays out of the report on purpose. **Tool row** is seeded by migration `0078_add_chat_agent_keyboarder_tool.py` (description `Chat-Agent-Keyboarder`); without that row the registry's `_tool_status_key()` lookup falls back to "enabled" so the tool still binds, but the Tools dialog cannot toggle it. Quirk: pyautogui hotkey names — Keyboarder normalizes via `get_pyautogui_key()` (`escape→esc`, `windows→win`, `altgr→altright`, `mayus/caps→capslock`); pass `'win+r'`, `'ctrl+alt+t'`, etc. lowercase.

- **Wrapped-agent assignment parser must split on `and`/`with`, not just `,`/`;`** — Every `example_request` string in `chat_agent_registry.py` separates parameters with the natural-language conjunction `and` (occasionally `with`): `filepath='X' and content='Y'`, `url='X' with system_prompt='Y' and content_mode='Z'`. The LLM reliably copies that style. Before the fix, `_split_assignment_segments` only split on `,` and `;`, and `_closes_outer_quote` only closed a single-line quote on `,`/`;`/EOF — so multi-arg calls collapsed into one swollen segment whose first value absorbed the entire tail (`file_path='X' and content='Y'` → file_path became `X' and content='Y`). Evidence: six consecutive `file_creator_00N` runs with paths like `C:\Development\AngysBackInCUDA\drone_knap.h' and content='/*...`, each failing with WinError 123 and one leaving a literal directory named `drone_knapsack.h' and content='`. The fix (in `agent/tools.py`) adds a `_looks_like_conjunction_assignment_start(text, pos)` helper matching `(and|with) <ident>=`, and plugs it into both `_closes_outer_quote` (as an additional closer in both single-line AND multi-line mode) and `_split_assignment_segments` (as a top-level segment boundary whenever a whitespace char outside quotes/brackets is followed by the conjunction pattern). Coverage: the new `AssignmentParserRobustnessTests.test_and_conjunction_splits_file_creator_pair`, `test_with_conjunction_also_splits`, `test_parametric_file_creator_example_request_parses`, and the sweep `test_no_registry_example_leaks_conjunction_into_a_value` pin the contract — the sweep scans every `WRAPPED_CHAT_AGENT_SPECS` example and fails if any resulting value contains a leaked conjunction pattern. Do NOT narrow the close-heuristic back to `,;EOF` only — it will silently re-break every multi-arg wrapped chat-agent call.

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
