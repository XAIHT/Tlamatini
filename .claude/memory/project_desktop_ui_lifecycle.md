---
name: Desktop-UI lifecycle contract (close + save-dialog handling)
description: 2026-05-07 fix — Keyboarder/Mouser/Shoter purposes + prompt.pmt rule 11 codify open→focus→interact→close→handle-save-dialog→verify
type: project
originSessionId: 1ee89777-fd83-41c5-abca-8fda542e7e6f
---
2026-05-07: Tlamatini left a Notepad window open after typing into it (image.png evidence) because no rule told the LLM to close the window or handle Notepad's "Save changes?" prompt. Fix codifies the lifecycle in two layers:

1. **`chat_agent_registry.py`** — three `purpose` enrichments (the `purpose` field is concatenated verbatim into the LLM-visible tool description in `tools.py:1605`):
   - `keyboarder.purpose` gained a "WINDOW CLEANUP" paragraph: `alt+f4` to close, `alt+n`/`alt+s`/`alt+c`/`escape` for English Save dialogs, `tab`+`enter` for non-English/custom dialogs, then `chat_agent_shoter` to verify.
   - `mouser.purpose` gained a "prefer keyboarder alt+f4 over hunting the X by pixel" paragraph (locale-independent, focused-window-targeted).
   - `shoter.purpose` extended to mention post-close verification ("confirm window is gone, no residual dialog").
   - 12 new `security_hints` on `keyboarder` ("close window", "alt+f4", "don't save", "save dialog", "dismiss dialog", ...) so the planner picks Keyboarder when the LLM internally decides "close the window".
2. **`agent/prompt.pmt`** — rule 11 gained a "**Desktop-UI lifecycle rule**" sub-bullet making the open→focus→interact→close→handle-save-dialog→verify chain explicit, with default-discard policy (`alt+n`) when the typed content does NOT need to be kept.

**Why:** the user explicitly asked for the LLM to *infer* this cleanup behavior — the previous prompt had no language about lifecycles, only about individual tool capabilities. Codifying it in both the tool purposes (where the planner reads) and the system prompt (where the executor reads each turn) gives layered coverage.

**How to apply:** when adding any new desktop-UI tool (e.g. browser-automation, paint, screen-recorder), follow the same pattern — close-and-verify is part of the tool's contract, not optional. If a future agent has a save dialog with non-standard buttons, add the alt-letter map to that agent's `purpose` (do NOT bury it in code).
