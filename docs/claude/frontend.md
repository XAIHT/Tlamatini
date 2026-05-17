# Tlamatini — Frontend Architecture

## Chat Interface (8 modules)
- `agent_page_init.js` - WebSocket setup, app initialization
- `agent_page_chat.js` - Chat message handling
- `agent_page_canvas.js` - Code canvas rendering
- `agent_page_context.js` - RAG context management
- `agent_page_dialogs.js` - Modal dialogs
- `agent_page_layout.js` - UI layout
- `agent_page_state.js` - Client state
- `agent_page_ui.js` - General UI utilities

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

## Shared / chat-runtime auxiliary (6 modules)
- `canvas_item_dialog.js` - Agent config dialog on canvas
- `contextual_menus.js` - Right-click menus
- `tools_dialog.js` - Tool enable/disable dialog
- `skills_dialog.js` - **ACPX-Skills navbar dropdown** dialogs (Configure checkbox grid mirroring the Mcps/Tools/Agents pattern + Browse list-and-detail + Diagnostics cross-check report + Reload single-action). Backed by `GET /agent/skills/` / `GET /agent/skills/<name>/` / `GET /agent/skills/_/diagnostics/` / `POST /agent/skills/_/reload/` plus the WebSocket `set-skills` channel for the toggle persistence. Per-skill state cached in the module-level `skills = []` array populated by `type: 'skill'` system messages — see `agent_page_chat.js`. The Configure dialog only ever writes `Skill.enabled`; everything else (description, runtime, frontmatter, sha256) is owned by `agent/acpx/service.py::boot_skills()` and reloaded from SKILL.md on disk.
- `chat_page_runtime_poller.js` - Chat-side wrapped-runtime poller (status / log / wait helpers)
- `shared-runtime-dialogs.js` - Shared modal dialog widgets used by chat + ACP runtime views

**Total: 28 JS modules** (8 chat + 13 ACP + 1 ACP entry-point + 6 shared/chat-runtime auxiliary).

## Flow Compiler Pipeline (canvas / chat → backend → pool)

Two browser surfaces produce flows; both compile through the **same** backend Agent Contract registry before they ever reach disk:

1. **ACP canvas → `/agent/compile_flow/`** — Save / Validate / Start all build a snapshot via `buildACPFlowSnapshot()` (`acp-flow-snapshot.js`) and POST it. Start passes `mode: 'write'` so the canvas state lands in the session pool before agents launch (this is why an edited-but-unsaved canvas now behaves identically to a freshly loaded `.flw`); Validate passes `mode: 'dry_run'` and renders the returned compiled-config preview without touching disk.
2. **Chat Create-Flow → `/agent/flow_from_tool_calls/`** — When the toolbar Create-Flow button fires, `_normalizeChatFlowBeforeDownload()` in `agent_page_chat.js` POSTs the legacy draft (built from `tool_calls_log`) to the backend, which runs it through `normalize_flow_payload()` → `flow_spec_to_legacy_json(redact=True)` and returns a `.flw` JSON whose secrets are redacted and whose canonical agent / pool names match the registry. The browser then downloads that normalized blob (with a graceful fallback to the legacy un-normalized draft if the backend is unreachable, so an offline frozen install still produces a usable `.flw`).

Both surfaces share `agent/services/flow_spec.py` (the in-memory `FlowSpec` representation), `agent/services/agent_contracts.py` (per-agent connection-field shape and `parametrizer_fields`), and `agent/services/flow_compiler.py` (the compile + write pipeline). The `_parametrizer_mappings` array on a Parametrizer node's config and the `artifacts.parametrizerMappings` object on the snapshot are **two valid persistence shapes for the same data** — `getSavedParametrizerMappings()` in `acp-file-io.js` accepts either when a `.flw` is loaded, so older files keep working.
