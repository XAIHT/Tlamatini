---
name: Flow Compiler — dialog edits always win over canvas wires
description: Reverses the canvas-as-source-of-truth contract for connection fields; user-edited source_agents/target_agents/etc. survive Start.
type: project
originSessionId: 5b46eeaf-e53d-4b54-86fc-dc587a138e19
---
`Tlamatini/agent/services/flow_compiler.py::_compiled_configs` no longer clears connection fields before re-deriving them from canvas wires. As of 2026-05-09, dialog edits to `source_agents` / `target_agents` / `output_agents` / singleton fields (`source_agent`, `target_agent`, `source_agent_1/2`) always win.

**Why:** User reported that reconfiguring `source_agents` on raiser_1 via the Configure dialog was being silently overwritten by the canvas-wiring derivation on Start. They explicitly chose "Dialog edits always win" via AskUserQuestion. The canvas-as-truth contract introduced in commit `0bea21d` made the editable connection fields in the Configure dialog deceptive — they accepted edits but the compiler clobbered them.

**How to apply:**
- `_clear_managed_connections` is now `_snapshot_managed_connections` — pure read, no mutation.
- `_set_connection_field` for singleton fields now only writes when the field is empty (`if not config.get(key)`).
- List fields keep using `_add_unique`, which means canvas wires *append* to dialog-set entries instead of replacing them.
- Ender's kill-list special case: a non-empty user-set `target_agents` is kept verbatim; the upstream-traversal kill list only fires when the field was empty pre-canvas-pass.
- **Trade-off the user accepted**: removing a canvas wire does NOT remove a previously-compiled entry from the YAML — they have to delete it in the dialog manually. This is the price of dialog-wins.
- Coverage: `agent/test_flow_contracts.py` adds three regression guards (`test_dialog_edited_source_agents_survive_canvas_compile`, `test_dialog_edited_ender_kill_list_is_preserved`, `test_dialog_edited_source_agent_singleton_is_preserved`).
- Do NOT revert to the old wipe-and-rebuild without revisiting the user's stated preference.
