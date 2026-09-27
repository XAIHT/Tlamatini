<!-- Tlamatini — "one who knows"
     Created by Angela López Mendoza · @angelahack1
     Tlamatini Author Banner — do not remove -->

# Prompt Flow Panel

Open **Panels → Prompt Flow Panel** from chat, or **File → Prompt Flow Panel** from the Agentic Control Panel. The authenticated page is `/agent/prompt_flow_panel/`.

The Operations bar follows the Agentic Control Panel layout. Drag a figure onto the canvas, or click its palette entry. All figures share a 200 × 128 coordinate box; their outlines match the prompting-operation reference.

[Open the complete kickoff example](examples/prompting-kickoff.fpmt) with **File → Open .fpmt** to try all seven operation types. It requires the configured model and embedding provider. The built-in **File → Open example** is a shorter branching introduction.

| Operation | Figure | Playback behavior |
| --- | --- | --- |
| Prompt | Rectangle | Sends its text to the configured Tlamatini model. Multi-Turn and ACPX can be enabled in its settings. |
| Programmed Prompt | Rectangle with clock | Waits until an optional local scheduled time, then waits its configured active seconds, then sends its prompt. |
| Decision | Diamond | Chooses Yes or No from a string comparison against the last output, or asks the user to choose. |
| Feed embeddings | Upward triangle | Adds its text to the current run's retrieval context, rebuilding embeddings with the existing model stack. |
| Flush embeddings | Downward triangle | Clears the run's retrieval context, retaining its conversation. |
| Clean History | Trapezoid | Clears the run's conversation and last output, retaining its retrieval context. |
| User Commentary | Speech bubble | Opens a reply dialog and appends the reply to the run's conversation. |

Double-click a figure, choose **Configure** from its right-click menu, press Enter on a selected figure, or use the **Configure** toolbar button. `{{last_output}}` in a prompt, embedding text, or user message inserts the previous model answer or commentary. Decisions support contains, does-not-contain, equality, and empty-output comparisons, with optional case matching. They never execute expressions from files.

Selected figures use the Agentic Control Panel's gold outline and soft yellow glow, following each figure's shape. Selected connections use the same gold highlight. Ctrl+click or marquee selection highlights every selected figure; Escape clears selection. During playback, status colors remain visible alongside the selection glow. Selection and zoom do not mark the diagram as modified.

Connect exactly as in the Agentic Control Panel: press a white output triangle on the right of a figure, drag the live curve to a white input triangle on the left of another figure, and release. Ports keep their gold highlight during connection; releasing on empty canvas or pressing Escape cancels. Decision figures have two right-side outputs, Y above N. The Operations bar contains only the seven operations; no Connection tool is needed. Each output has one destination; reconnecting it replaces its destination. Double-click a connection to edit its destination or branch. Keyboard users can activate an output, Tab to an input, and activate it.

Select the **Start** operation, then **Validate** and **Play**. Both Decision branches must connect, and every operation must be reachable from Start. An unconnected ordinary output ends playback. Cycles are allowed and bounded by **Flow settings → Maximum executed operations per run** (default 500, maximum 5,000).

The running figure and traversed connections are highlighted. **Run output** displays step activity, model answers, user replies, waits and errors. Pause allows the current operation to finish and holds the next one. Scheduled times are absolute; relative delays count active playback time. Stop requests model cancellation and waits for the current worker to drain before allowing another run. Closing a reply dialog by Cancel, X or Escape stops the flow; an outside click does not dismiss it. Closing or disconnecting the page also requests a stop. Keep the page and Tlamatini open for scheduled prompts; this is not a persistent background scheduler.

Each run has its own model chain, conversation, context files and cancellation identity. It starts with empty history and embeddings and uses the existing configured model, enabled tools and agents. Feed embeddings requires a functioning embedding provider and fails explicitly if context setup falls back to a non-retrieving chain. The run cleans up its own temporary context directory after completion. Chat history and global embedding configuration are not edited.

## Files and editing

**File → Save as .fpmt** downloads a portable JSON document. **File → Open .fpmt** or dropping a `.fpmt` file onto the canvas restores the diagram. The extension is case-insensitive. Saving adds `.fpmt` when needed and replaces a trailing `.pmt` in the entered file name. Opening never executes the diagram. Files are limited to 5 MiB, 500 operations and 1,000 connections. Invalid files leave the current diagram intact. A local draft is also saved in browser storage, scoped to the signed-in user. Save a file to retain a portable copy; browser drafts may be cleared by browser settings.

To open an older **JSON flow diagram** saved with `.pmt`, rename that file to `.fpmt`; its contents do not need conversion. The panel rejects files still named `.pmt`. Existing browser drafts remain available, and their old flow file names are normalized to `.fpmt` when restored. Do not rename Tlamatini's plain-text `prompt.pmt` or `monitoring-prompt.pmt` files: those retain their existing names and purposes.

The versioned format is `tlamatini-prompting-flow`, version `1`, with `name`, `start`, `max_steps`, `nodes` and `edges`. Node types are the seven lowercase operation names shown in the implementation; edges use `next`, `yes` or `no`. The backend independently validates the document before playback. The pre-existing plain-text system `prompt.pmt` is a different format and is deliberately rejected by this diagram editor. `.flw` Agentic Control Panel files remain separate.

| Shortcut | Action |
| --- | --- |
| Ctrl+S / Ctrl+O | Save / open |
| Ctrl+Z / Ctrl+Shift+Z or Ctrl+Y | Undo / redo |
| Ctrl+click / drag empty canvas | Select multiple figures / marquee selection |
| Ctrl+drag | Copy selected figures, settings and internal connections with new IDs and numbered labels; one-step Undo/Redo |
| Double-click / Enter | Configure the clicked / selected figure |
| Ctrl+A / Ctrl+D | Select all / duplicate selected figures and their internal connections |
| Delete or Backspace | Delete selection and related connections |
| Arrow keys / Shift+arrows | Move selection 10 / 40 canvas units |
| Ctrl+mouse wheel / Fit | Zoom / fit diagram |
| Escape | Cancel the top dialog, connection or node drag; otherwise clear selection |

## Maintenance and validation

The template `agent/templates/agent/prompt_flow_panel.html`, `prompt_flow_panel.css`, `prompt-flow-panel-model.js` and `prompt-flow-panel.js` use the existing local frontend dependencies, shared dark canvas styles and shared dialog policy/theme. Both panels load `flow-canvas-interactions.js` for shared connection gestures, geometry, Fit/zoom, menu placement and divider mechanics. `flow_canvas.css` owns shared interaction styling; load it after panel styles and keep `dialog_theme.css` last. Both editors use free dragging without grid snapping, Ctrl-drag copying, live marquee selection of figures and wires, and matching shortcuts. Native double-click opens every node’s existing configuration dialog. Node movement and copy-drag share a four-screen-pixel threshold, keeping click targets stable and originals stationary. Copy intent is retained until release; Escape cancels a pending move/copy. Copies retain settings, acquire distinct IDs and numbered labels, and form one undoable action even when backend deployment finishes after release. The route is login-protected; the websocket is `/ws/prompt-flow-panel/`, authenticated and scoped to its connection. The graph interpreter lives in `agent/services/prompt_flow_panel.py`; `prompt_flow_panel_runtime.py` adapts it to the existing RAG stack.

Run `python Tlamatini/agent/test_prompt_flow_panel.py`, `python Tlamatini/manage.py test agent.test_prompt_flow_panel_runtime agent.test_chain_readiness --noinput`, the targeted Python lint check, and `npm.cmd run lint` in a **verified visible foreground PowerShell console left open with `-NoExit`**. The adapter tests use fake providers to check history, embedding rebuilds, cleanup and cancellation isolation. Run browser checks in visible Chrome with explicit `headless=False`, verify its actual desktop visibility before the workload, monitor live output, and leave the browser open afterward. Never substitute a hidden run. UI checks should cover `.fpmt` file round trips, rejection of unrelated `.pmt` files, draft recovery, shape/port alignment after zoom and drag, both decision branches, reply cancellation, pause/resume/stop and backend failure. Model and embedding checks require the user's configured providers to be available.

The complete regression set: `agent/test_prompt_flow_panel.py` (validator and interpreter, no model or database), `agent/test_prompt_flow_panel_runtime.py` (model adapter with fake providers), `agent/test_prompt_flow_panel_websocket.py` (the real ASGI route and consumer, with a deterministic adapter), `agent/test_prompt_flow_panel_carriage.py` (every panel module must be in the frozen archive and every panel asset in the release receipt), and `agent/test_chain_readiness.py::ContextFreeChainTests` (`include_application_context=False` skips the shared `application/` corpus while the chat default still loads it). The visible browser scripts, each launched from a verified foreground `-NoExit` console with Shoter photographing the whole desktop, are `scripts/prompt_flow_extension_visible.py` (15 `.fpmt` checkpoints), `scripts/panel_search_title_visible.py` (14 checkpoints: the Agentic Control Panel's agent search, and the unsaved-changes `•` in both panels' titles through save, edit, undo and reopen) and `scripts/run_menu_state_checks.py`, which drives `scripts/menu_browser_checks.py` (including the panel's play/pause/stop and stale-event states) and `scripts/menu_live_checks.py`.

When editing static files, preserve the `STATIC_VERSION` environment/timestamp expression, update its suffix, and run collectstatic in the verified visible console.

`scripts/prompt_flow_selection_visible.py` checks all seven selected shapes, Ctrl-click and select-all, zoom, deselection, selected connections, and selection during real User Commentary playback. It uses the separate normal port-8001 installation and an authenticated headed Chrome session, checks the actual served CSS, and records full-desktop Shoter captures under `Temp/prompt-selection-docs-visible/`. Its visibility gates must be confirmed from the desktop before proceeding. Its 2026-09-25 run passed all 14 checks with exit code 0.

`scripts/prompt_flow_connections_visible.py` compares triangles and wires with a live Agentic Control Panel and checks dragging, cancellation, Y/N branches, reconnecting, zoom, undo, keyboard connections, save/reopen and real commentary playback. It uses the same separate port-8001 installation, verifies the served assets, and writes Shoter captures under `Temp/prompt-connections-visible/`. Launch it from a verified foreground `-NoExit` console; confirm its desktop visibility gates before proceeding. The harness pauses when its verified Chrome window loses the foreground.

## Release and self-modification carriage

`build.py` explicitly includes the three prompt-flow-panel backend modules and verifies their presence inside the frozen executable's PYZ archive. The existing template and static tree carriers include the page, both JavaScript modules and its CSS; `build_runtime_assets.py` requires these assets, verifies collected-static bytes and records them in the release receipt. The guide and kickoff example are required copies at `docs/prompting-flow-designer.md` and `docs/examples/prompting-kickoff.fpmt` in the installed application. These application assets are replaced by updates.

Self-modify snapshots explicitly require the backend, page, JavaScript, CSS, execution and packaging regression modules, guide and example. The generic snapshot walk also carries the modified routing, views, RAG adapter integration, navigation templates and settings. Browser drafts remain browser storage; saved `.fpmt` files remain at the location chosen by the user. Test consoles, logs, screenshots and temporary test databases under `Temp` are verification evidence, not release assets.

Run both `.claude/skills/tlamatini-self-update-inclusion/scripts/sweep_self_update.py` and `.claude/skills/tlamatini-self-modify-inclusion/scripts/sweep_self_modify.py --keep` in the verified visible foreground console. Inspect every finding and advisory, then verify this feature's files against the retained snapshot and release receipt. Source-carriage checks do not prove that a fresh executable or installer was built.

`python Tlamatini/manage.py check_prompt_flow_panel` checks the source page and its local assets, validates all seven operation types in the kickoff example, exercises the real WebSocket consumer through a commentary/history-clear flow, and checks a UTF-8 context-file round trip under the application Temp directory. Run it in the same verified visible console. The build runs `manage.exe check_prompt_flow_panel` inside the freshly frozen application after collecting static files and aborts packaging on failure. The command is explicitly bundled and checked in the frozen archive. It does not call a live model or embedding provider; those integrations require separate live playback verification. Adapter regression tests also exercise the actual Temp resolver under source and frozen layouts, including installation paths with spaces and Unicode.
