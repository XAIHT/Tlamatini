<!-- Tlamatini — Created by Angela López Mendoza · @angelahack1
     Tlamatini Author Banner — do not remove -->
# Docked avatar resizing from the composer divider

> Current release: **[v1.88.0](2026-10-20-v1.88.0.md)**. Dated records below retain their original evidence dates.


Date: 2026-10-13. Commit `63a62cc1`; shipped in `v1.83.0` (2026-10-14).

The vertical divider previously reserved the avatar's current width as the
composer's minimum height. A wide portrait therefore prevented the message box
and portrait from shrinking vertically, although the chat/canvas divider could
make the portrait narrower.

The composer now reserves a 120 px portrait plus its measured controls and
spacing. The square dock fits both dimensions:

`side = max(120, floor(min(form width × 0.25, available portrait height)))`

Available portrait height excludes the top inset and the measured Send/Mic row
plus the existing 18 px clearance. The 120 px outer square retains a 106 px face
inside its border/padding and a 22 px resize handle. It follows the established
avatar minimum rather than introducing a separate threshold.

The initial quarter-width portrait remains until the composer divider is moved.
Dragging down shrinks it; dragging up restores it up to the width of its original
column. Home/double-click minimizes, End expands, arrows move 1%, Shift+arrows
move 5%, and Escape ends a drag. Floating sizes/presets, draft contents, attachment
and dictation rows retain their behavior. Short windows still scroll the composer
to keep its controls reachable.

Implementation: `agent_page_layout.js` measures the independent minimum and sets
the form's `--tlm-avatar-docked-size`; `avatar.css` applies it only to the docked
portrait. `avatar_size.js` retains floating geometry and persistence. The cache
suffix at that change was `-avatar-divider-1` (the live suffix is `-file-drop-router-1`).

## Verification

The real source page ran in foreground, explicitly headed Chrome from a verified
visible PowerShell console. Only an isolated database under
`Temp/avatar-divider-20261013/browser/` was used. Inference and microphone
WebSockets were isolated; attachment/dictation rows were labelled layout fixtures.

- 19 docked-avatar checkpoints passed, including real pointer shrinking through
  200, 160 and 120 px, both dividers, keyboard controls, cancellation, redocking,
  transient rows, narrow windows, measured native 125% Chrome zoom and stable
  ResizeObserver geometry.
- All 18 existing composer checkpoints passed, including the floating minimum,
  Send/Mic containment, short-window scrolling, saved floating size, source asset
  byte parity and no JavaScript errors.
- At the initial 1440 CSS px window width, the portrait went from 282 px to
  120 px and returned about 162 px of vertical space to chat history.
- Seven focused divider/JavaScript-gate source tests passed. JavaScript lint had
  zero errors and 650 existing warnings; all 58 application scripts parsed.
  Ruff passed for the three affected Python harness files. Static collection
  refreshed the three modified assets; `git diff --check` passed.

Evidence: `Temp/avatar-divider-20261013/browser/verified-results.json`,
`browser-live.log`, the visible console transcript and Shoter desktop images.
The reusable headed runner `scripts/chat_composer_resize_visible.py` now includes
`scripts/docked_avatar_resize_checks.py` before its existing composer/viewport checks.

An initial harness attempt correctly refused to execute after the console lost
foreground focus. Native keyboard injection and measured device-pixel ratio were
used for the final zoom check; a Playwright shortcut alone did not change Chrome zoom.
