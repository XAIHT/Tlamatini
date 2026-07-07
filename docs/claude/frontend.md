<!--
═══════════════════════════════════════════════════════════════════
  ✦  T L A M A T I N I  ✦   —   "one who knows"
  Created by  Angela López Mendoza   ·   @angelahack1
  Developer · Architect · Creator of Tlamatini
  Tlamatini Author Banner — do not remove (Angela's name is kept in every build)
═══════════════════════════════════════════════════════════════════
-->
# Tlamatini — Frontend Architecture

## Chat Interface (8 modules)
- `agent_page_init.js` - WebSocket setup, app initialization, **Context-menu "Set directory as context"** handler (see *Context directory picker* below)
- `agent_page_chat.js` - Chat message handling; handles the `exec-permission-request` frame (Ask Execs — see below) by opening the permission dialog
- `agent_page_canvas.js` - Code canvas rendering
- `agent_page_context.js` - RAG context management
- `agent_page_dialogs.js` - Modal dialogs (incl. `showExecPermissionDialog(detail)` — the Ask-Execs Proceed/Deny prompt)
- `agent_page_layout.js` - UI layout
- `agent_page_state.js` - Client state (incl. the Ask-Execs checkbox helpers `isAskExecsEnabled` / `applyStoredAskExecsState` / `syncAskExecsAvailability`, and `syncExecReportAvailability` which disables+greys the **Exec report** checkbox whenever Multi-Turn is off — mirrors Ask-Execs)
- `agent_page_ui.js` - General UI utilities

### Ask Execs — per-tool permission prompt (toolbar checkbox + modal dialog)

The toolbar checkbox **Ask Execs** (`#ask-execs-enabled`, between **ACPX** and **Step-by-Step**) is **enabled only while Multi-Turn is checked** — `syncAskExecsAvailability()` in `agent_page_state.js` toggles its `disabled` attribute and the `.toolbar-toggle-disabled` class, called on load and on every Multi-Turn change (`agent_page_init.js`). `agent_page_init.js` sends `ask_execs_enabled: isAskExecsEnabled()` on every chat submit. When the backend blocks before a state-changing tool it broadcasts an `exec_permission_request` group frame; `agent_page_chat.js`'s `onmessage` catches `data.type === 'exec-permission-request'` and calls `showExecPermissionDialog(data.detail)` (`agent_page_dialogs.js`). That modal shows the Tool/MCP/Agent, parameters, program (textarea), and shell (textarea), with **Proceed** (green) / **Deny** (red); the titlebar X is hidden and Esc is disabled, and closing without a button choice counts as **Deny** (decision is idempotent). It POSTs an `exec-permission-response` frame (which **must** include a `message` key — `consumers.receive` reads `text_data_json['message']` unconditionally) carrying `request_id` + `decision`. CSS: `.exec-perm-*` (dialog) and `.exec-denied-*` (the red "Execution interrupted" banner appended to a denied answer) in `agent_page.css`. Backend contract: `docs/claude/multi-turn.md` → *Ask Execs*. **Runtime relax (2026-05-29):** the checkbox `change` handler also sends a `set-ask-execs-runtime` frame (`ask_execs_runtime_enabled`) **while `inLongOperation === true`**, so unchecking Ask Execs mid-run stops the prompts for the rest of that run (and re-checking resumes them); when relaxing it calls `dismissExecPermissionDialogForRuntimeProceed()` to silently close any open prompt (sets `_execPermDecisionSent` so the close handler doesn't fire a stale Deny). The toolbar toggles are intentionally left clickable during a run (`disableControlsDuringOperation()` does not touch them).

### Step-by-Step — one-action-at-a-time toolbar modifier

The toolbar checkbox **Step-by-Step** (`#step-by-step-enabled`, between **Ask Execs** and **Add internet context**) is a **Multi-Turn runtime modifier** that puts the LLM into a guided, one-action-at-a-time cadence: it performs a single action, then WAITS for the user's `READY` before doing the next — the hands-on setup/debugging style. Like the other toggles it is sent per-request on every chat submit. Distinct from **Ask Execs**, which is a per-tool Proceed/Deny *permission* gate; Step-by-Step is a *pacing* directive (one step, then wait for the user to drive the next).

### Context directory picker — native, nested-dir-capable (2026-05-25)

The chat **Context ▸ Set directory as context** menu loads a project at **any depth** under the app root. The browser `window.showDirectoryPicker()` was dropped because its `FileSystemDirectoryHandle.name` exposes only the **leaf folder name** (a browser-security limitation), which broke every directory that wasn't a direct child of the runtime root. `agent_page_init.js`'s `setDirContextMenu` handler now `fetch`es the backend native folder picker — `views.pick_context_directory_view` (route `pick_context_directory/`), which drives the Win32 dialog and returns the **real absolute path** — then sends that full path in `set-directory-as-context`. A `_promptForContextDirectory()` manual-entry fallback covers non-Windows hosts. The backend accepts the path because `path_guard.is_within_application_root()` + `resolve_runtime_agent_path` now allow the application root or **any descendant** at any depth. **Do NOT revert to `showDirectoryPicker()`** — it structurally cannot send the full path (see `docs/claude/recent-fixes.md`, 2026-05-25).

## ACP Workflow Designer (13 modules + 1 entry point)
- `agentic_control_panel.js` - Entry point
- `acp-globals.js` - Shared global state, plus `updateCanvasContentSize()` (canvas-growth helper — see ACP Canvas DOM Contract below)
- `acp-canvas-core.js` - Canvas rendering, drag-and-drop, classMap, connection handlers
- `acp-canvas-undo.js` - Undo/redo state (1024 actions)
- `acp-undo-manager.js` - Undo stack manager (works with `acp-canvas-undo.js`)
- `acp-agent-connectors.js` - 50+ agent connection handlers
- `acp-control-buttons.js` - Start/stop/pause/hypervisor
- `acp-file-io.js` - .flw save/load (calls `buildACPFlowSnapshot()` for save; calls `getSavedParametrizerMappings()` on load to re-hydrate Parametrizer artifacts whether they were persisted in `_parametrizer_mappings` per-node or in the snapshot's `artifacts.parametrizerMappings` map)
- `acp-flow-snapshot.js` - **Canvas-snapshot bridge to the backend Flow Compiler** — `buildACPFlowSnapshot()` produces the `schemaVersion: 2` JSON the backend understands (nodes with `id`, `text`, position, `agentPurpose`, `configData`; connections with both indexes AND ids; `artifacts.parametrizerMappings` keyed by node id). `compileCurrentACPFlow({mode})` POSTs it to `/agent/compile_flow/`; called by Save (mode=dry-run via Validate) and by the Start sequence (mode=`write`) so the live canvas is recompiled into `config.yaml` files before any agent runs
- `acp-running-state.js` - LED indicators, process monitoring
- `acp-session.js` - Session pool management
- `acp-layout.js` - Canvas layout utilities
- `acp-parametrizer-dialog.js` - Parametrizer's interconnection-mapping dialog
- `acp-validate.js` - Flow validation engine (POSTs the snapshot to `/agent/compile_flow/` mode=`dry_run` and renders the returned warnings + per-agent compiled config — same path Start uses with mode=`write`)

## ACP Canvas DOM Contract (scrollable canvas)

The ACP canvas is a **two-layer DOM**. Confusing the two layers is the single most common source of coordinate-math bugs in ACP code, so the contract is called out explicitly here:

1. `#submonitor-container` — the **viewport**. `overflow: auto`, fixed to the available panel size, owns the themed scrollbars. It is NOT where canvas items live; it is only the window you look through.
2. `#canvas-content` — the **content layer** that lives inside `#submonitor-container`. `position: relative`, `min-width: 100%`, `min-height: 100%`, and grows in pixel width/height whenever items extend past the viewport (managed by `updateCanvasContentSize()` in `acp-globals.js`). Every `.canvas-item`, the SVG `#connections-layer`, and the rubber-band `#selection-box` are all children of `#canvas-content`.

Consequences that MUST be respected by any new canvas code:

- **Coordinate reference frame is `canvasContent`, not `submonitor`.** All math that translates pointer events into `style.left` / `style.top` on a canvas item must use `canvasContent.getBoundingClientRect()`. `canvasContent`'s rect already reflects the current scroll offset, so you do NOT manually add `submonitor.scrollLeft` / `scrollTop`. Mixing `submonitor.getBoundingClientRect()` with a `canvasContent`-positioned child (or vice versa) produces items that jump under the cursor as soon as the user has scrolled.
- **Appending items goes to `canvasContent`, never to `submonitor`.** `createCanvasItem()` and `cloneAndRegister()` both call `canvasContent.appendChild(newItem)`. Appending to `submonitor` places the item above the scrollable layer and out of the coordinate frame used by connections.
- **No upper clamp on item positions.** Item positions are clamped `>= 0` only. The canvas intentionally grows to the right and bottom — do not re-add `rect.width - width` / `rect.height - height` upper bounds. After any position or size change that could extend the content envelope (item creation, drag end, `.flw` load, undo/redo item restoration) call `updateCanvasContentSize()` so the viewport's scrollbars stay in sync.
- **Selection-box rect frame.** `startSelectionBox()` uses `canvasContent.getBoundingClientRect()` and does NOT add `submonitor.scrollLeft/scrollTop` — the rect already carries the scroll offset. The selection box is itself a child of `#canvas-content`, so it scrolls with the content.
- **Mousedown dispatch.** The "begin selection box" branch in `initCanvasEvents()` accepts `e.target === submonitor || e.target === canvasContent || e.target.id === 'connections-layer'`. New clickable layers added on top of the canvas must either stop propagation or be whitelisted here explicitly, otherwise they silently disable rubber-band selection.

If you add a new canvas-level feature (layout grid, minimap, overlay HUD, etc.), it almost always belongs as a child of `#canvas-content`, not `#submonitor-container`, so it shares the coordinate frame with the items it visualizes.

## Shared / chat-runtime auxiliary (7 modules)
- `canvas_item_dialog.js` - Agent config dialog on canvas
- `contextual_menus.js` - Right-click menus
- `tools_dialog.js` - Tool enable/disable dialog
- `skills_dialog.js` - **ACPX-Skills navbar dropdown** dialogs (Configure checkbox grid mirroring the Mcps/Tools/Agents pattern + Browse list-and-detail + Diagnostics cross-check report + Reload single-action). Backed by `GET /agent/skills/` / `GET /agent/skills/<name>/` / `GET /agent/skills/_/diagnostics/` / `POST /agent/skills/_/reload/` plus the WebSocket `set-skills` channel for the toggle persistence. Per-skill state cached in the module-level `skills = []` array populated by `type: 'skill'` system messages — see `agent_page_chat.js`. The Configure dialog only ever writes `Skill.enabled`; everything else (description, runtime, frontmatter, sha256) is owned by `agent/acpx/service.py::boot_skills()` and reloaded from SKILL.md on disk.
- `chat_page_runtime_poller.js` - Chat-side wrapped-runtime poller (status / log / wait helpers)
- `shared-runtime-dialogs.js` - Shared modal dialog widgets used by chat + ACP runtime views
- `external_mcps_dialog.js` - **External ▸ MCPs navbar dialog** (entry point `OpenExternalMcpsDialog`, navbar item `#external-mcps`). The user-facing surface of the universal External MCP CLIENT (see `docs/claude/architecture.md` → *External MCPs*): a searchable catalog of every server in `external_mcps.json`, an **at-most-5-active** selection, and **drag-a-`.json`-onto-the-dialog import**. Backed by three endpoints — `GET /agent/external_mcps/` (list catalog + active set), `POST /agent/external_mcps/activate/` (set the active ≤5), `POST /agent/external_mcps/import/` (add a server from a dropped/pasted `mcpServers` JSON). Pure HTTP (NOT a WebSocket toggle channel like Mcps/Tools/Agents/Skills); CSS in `external_mcps_dialog.css` (`.emx-*` classes). This is a SEPARATE surface from the two `Mcp`-model context-provider checkboxes — see the architecture doc.

**Total: 29 JS modules** (8 chat + 13 ACP + 1 ACP entry-point + 7 shared/chat-runtime auxiliary).

## Flow Compiler Pipeline (canvas / chat → backend → pool)

Two browser surfaces produce flows; both compile through the **same** backend Agent Contract registry before they ever reach disk:

1. **ACP canvas → `/agent/compile_flow/`** — Save / Validate / Start all build a snapshot via `buildACPFlowSnapshot()` (`acp-flow-snapshot.js`) and POST it. Start passes `mode: 'write'` so the canvas state lands in the session pool before agents launch (this is why an edited-but-unsaved canvas now behaves identically to a freshly loaded `.flw`); Validate passes `mode: 'dry_run'` and renders the returned compiled-config preview without touching disk.
2. **Chat Create-Flow → `/agent/flow_from_tool_calls/`** — The button appears whenever Multi-Turn ran with **≥1 successfully-executed agent** (no whole-answer classifier — removed 2026-07-06). When it fires, `_normalizeChatFlowBeforeDownload()` in `agent_page_chat.js` POSTs the draft (built from **only the successfully-executed** entries of `tool_calls_log`) to the backend, which runs it through `normalize_flow_payload()` → `flow_spec_to_legacy_json(redact=True)` and returns a `.flw` JSON whose secrets are redacted and whose canonical agent / pool names match the registry. The browser then downloads that normalized blob (with a graceful fallback to the legacy un-normalized draft if the backend is unreachable, so an offline frozen install still produces a usable `.flw`).

Both surfaces share `agent/services/flow_spec.py` (the in-memory `FlowSpec` representation), `agent/services/agent_contracts.py` (per-agent connection-field shape and `parametrizer_fields`), and `agent/services/flow_compiler.py` (the compile + write pipeline). The `_parametrizer_mappings` array on a Parametrizer node's config and the `artifacts.parametrizerMappings` object on the snapshot are **two valid persistence shapes for the same data** — `getSavedParametrizerMappings()` in `acp-file-io.js` accepts either when a `.flw` is loaded, so older files keep working.
