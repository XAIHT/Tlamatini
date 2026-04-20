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

## ACP Workflow Designer (11 modules)
- `agentic_control_panel.js` - Entry point
- `acp-globals.js` - Shared global state, plus `updateCanvasContentSize()` (canvas-growth helper — see ACP Canvas DOM Contract below)
- `acp-canvas-core.js` - Canvas rendering, drag-and-drop, classMap, connection handlers
- `acp-canvas-undo.js` - Undo/redo state (1024 actions)
- `acp-agent-connectors.js` - 50+ agent connection handlers
- `acp-control-buttons.js` - Start/stop/pause/hypervisor
- `acp-file-io.js` - .flw save/load
- `acp-running-state.js` - LED indicators, process monitoring
- `acp-session.js` - Session pool management
- `acp-layout.js` - Canvas layout utilities
- `acp-validate.js` - Flow validation engine

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

## Shared
- `canvas_item_dialog.js` - Agent config dialog on canvas
- `contextual_menus.js` - Right-click menus
- `tools_dialog.js` - Tool enable/disable dialog
- `acp-undo-manager.js` - Undo stack manager
