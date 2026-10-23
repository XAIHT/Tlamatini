<!-- Tlamatini Author Banner — Created by Angela López Mendoza · @angelahack1 -->
# Composer resizing and viewport containment — 2026-10-10

> Current release: **[v1.91.0](2026-10-23-v1.91.0.md)**. Dated records below retain their original evidence dates.


Status: shipped in the published `v1.78.0` release (commit `113eddc4`, 2026-10-10).
At verification time no build, commit, push or installed-release acceptance had
been performed; the record below is that dated verification.

## Behavior

- With the avatar floating, the input form can shrink to its actual action
  controls plus a 6px guard. Toolbar, context gauge, attachment and dictation
  rows contribute their measured heights. The old 30% floor is removed.
- Docking restores space for the portrait above the action buttons. Undocking
  restores the requested compact size. Arrow keys, Shift+arrows, Home, End,
  double-click and Escape have explicit divider behavior and accessible values.
- Short windows scroll the composer internally while preserving chat history.
- The page occupies the real viewport. Collapsed navigation opens over the
  workspace without pushing it down. Canvas buttons wrap within their pane.
- A 640px minimum workspace preserves both panes on narrow screens. The
  workspace pans horizontally; the page and its dialogs stay anchored. At
  narrow widths the floating avatar stays over the canvas and retains keyboard
  focus without panning to her new position.
- jQuery UI dialogs are bounded after opening, dragging and viewport changes.
  Short/narrow native dialogs scroll as complete cards when fixed headers and
  footers would otherwise leave no usable body. Colors and typography remain
  on the existing theme. The avatar does not cover modal dialogs.
- Static cache suffix: `-composer-resize-1`.

## Observed verification

The real source template and assets ran with an isolated SQLite database in a
verified foreground Chrome window (`headless=False`). Whole-desktop evidence
was captured with Shoter. Native window bounds, foreground state, DPI and actual
client size were checked; there was no oversized emulated viewport. Initial
harness failures involving Windows logical/physical pixels and foreground focus
were corrected before the final passing runs.

- 18 composer checks passed, including real pointer dragging, keyboard focus,
  redocking, transient rows, a short window, reload, asset parity and JavaScript
  errors.
- 38 viewport checks passed: normal zoom, native 400%, native 25%, a phone-sized
  window, return to 100%, and eight dialogs at each test size. Dialogs covered
  Omissions, Models, External MCPs, Contacts, Mic, Usage, About and the prompt
  catalog. Form fields were scrolled into view and checked for obstruction.
- Actual CSS viewports included 1440×900 at 100%, 360×225 at 400%,
  5760×3600 at 25%, and 473×727 in the phone-sized campaign. A further
  400×757 check passed keyboard focus retention, zero page/workspace displacement,
  Send hit testing, canvas panning and Usage opening. This was a desktop browser
  at phone-sized dimensions, not physical mobile-device certification.
- Chrome stopped at 25% after repeated native zoom-out commands. **20% native
  zoom was unavailable and was not claimed as tested.**
- Final `npm run lint`: exit 0, 56 JavaScript files parsed, zero errors and
  650 existing warnings. Ruff for the four harness modules and
  `git diff --check` passed. The isolated browser/server exited with code 0.

Inference and microphone WebSockets were isolated. Attachment, gauge and voice
status rows in the composer checks were explicit layout fixtures. These tests
certify layout behavior, not model inference, audio capture, billing accuracy,
installation or every dialog in the application.

Local evidence is in `Temp/composer-resize-browser/`: `summary.json`,
`viewport-summary.json`, `phone-minimum-summary.json`,
`final-source-ready.png`, `phone-400-undocked.png`, and the named dialog photos.
The visible console transcripts and exit-code records are in
`Temp/composer-resize/`. Earlier failed iterations remain in the transcript;
the final markers and summary files identify the passing runs.

## Repeatable visible harness

Use `scripts/chat_composer_resize_visible.py` only from a verified visible
foreground console retained with PowerShell `-NoExit`. It uses
`chat_composer_visible_window.py`, `chat_composer_resize_checks.py` and
`chat_viewport_visible_checks.py`. Inspect its whole-desktop waiting capture
before releasing `Temp/composer-resize-browser/browser-visible-confirmed`.
The browser stays open for inspection until `close.confirmed` is created.
Headless arguments are refused. Follow
`TestsVisiblesAndVisibleExecutionFromClaude2Codex.md` for launching and watching.
