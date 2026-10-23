<!-- Tlamatini Author Banner — Angela López Mendoza · @angelahack1 -->
# Live Editor and Terminater settings

Open **Config → Live Editor & Terminater**, the canvas Settings button, or the
terminal Settings button. Live Editor, Terminater and Voice share one dialog.
Save applies behavior to the next action; Cancel and Escape discard the draft.
Opening settings stops an active editor teaching action. Live editor access is
an explicitly immediate tab permission, matching the canvas checkbox.

Standard and Guided learning presets fill the draft. Reset restores the current
tab's defaults. Preview types a harmless sample in the dialog and can speak it;
it never runs a command, edits a file, or saves settings.

## Settings and ownership

Account preferences use `InteractionSettings` (migration 0220), strict validation
and optimistic revisions at authenticated, CSRF-protected
`/agent/interaction-settings/`. Concurrent saves require reloading the dialog.

* Editor: 40–160 WPM, pause 0–3 seconds after a segment, teaching detail, initial
  field suggestions, ghost text versus choices, and following the typed cursor.
  Scrolling manually suspends following for that segment. Saved speed overrides
  the model's suggested speed. Teaching detail is included in the tool's read
  response as an instruction; the language model determines the final wording.
* Terminal: 20–160 WPM, default available shell, task-controlled or user-only
  Enter, advisor for new terminals, command wait, no-output threshold and user
  handoff wait. There is no paste or instant mode. Linked speeds use 40–160 WPM.
  User-only Enter rejects line breaks/control characters and automated Enter,
  including base64 commands and action aliases. It does not restrict user input.
* Voice: editor and terminal narration, explanation/literal/both, before/during/
  after, optional completion before typing, and command-action result notices.
  Uses the existing browser voice choice, rate, volume and pitch. Global mute
  and microphone listening take precedence. Escape stops speech.
* Browser/account appearance: editor font, line numbers and wrapping; terminal
  font, cursor shape/blink and preferred layout. Stored separately from account
  behavior and flow files, with live changes to existing views.

## Runtime contracts

The Django process's one TerminalHub resolves account preferences on dispatch
for chat, ACP, Prompt Flow and browser actions. New agent configurations and new
Prompt Flow nodes use `use_my_defaults`. Older flow files normalize this flag to
false and retain explicit settings. When enabled it overrides speed, shell,
advisor and waits. Manual Enter and narration remain account choices in either
mode. Shell/advisor affect newly opened terminals; waiting windows are applied
to each typing action. A wait timeout does not kill a process.
Typed chat calls preserve an explicitly requested shell. Their account pacing
and omitted shell are resolved at the authenticated launcher, where an explicit
model field can be distinguished from the template's default. Ask Execs uses
the same account shell when the task does not choose one.

The editor carries a settings snapshot through its existing authenticated tool
and receipt path. Typing retains document/revision checks, bounded visibility
pause, user takeover, fresh reads and small tutor mutations. No new Agent or
tool registration is required.

Terminal narration selects one visible, focused account tab. A receipt belongs
to that exact connection. Waiting before typing is bounded to 120 seconds and
cancellable; a missing listener cancels the step rather than silently running it.
An unavailable voice offers Continue without voice or Stop. No command is
replayed on reconnect. Secret-marked content and handoff values never enter
speech. Result notices describe status without reading command output aloud.
The shared speech queue prevents overlapping chat and interaction utterances.

## Validation

Run development commands only in a verified visible foreground console and
leave it open. `scripts/interaction_settings_visible.py` launches real Chrome
with `headless=False`, creates a disposable database, and requires visual
confirmation before exercising the UI. It uses the actual editor, WebSockets,
TerminalHub and CMD; it separates real OS voice receipts from deliberate voice
failure injection. Evidence is kept in `Temp/interaction-settings-visible`.
Backend tests cover account isolation, validation, concurrent saves, manual
Enter enforcement, settings delivery and narration ownership/cancellation.

Source verification on 2026-10-23 completed in a verified foreground console
and headed Chrome:

* All 17 browser acceptance checks passed, including real OS speech, narration
  finishing before the first terminal key, real CMD read-back, manual Enter,
  editor timing and appearance, saved preferences, draft cancellation, presets,
  validation, a narrow viewport, and access from both control panels.
* The focused regression run executed 931 tests: 929 passed and two existing
  README documentation assertions failed (`test_blue_hat_section_exists` and
  `test_docs_describe_the_evidence_carryover`). The unchanged HEAD README also
  lacked both expected strings; these failures were unrelated to this feature.
  The later v1.91.0 documentation sweep restored both sections and both assertions
  passed in its separate 94-check validation run.
* JavaScript lint/parse checks, focused Python lint, migration consistency and
  `git diff --check` passed. The offline editor bundle was rebuilt.

The browser evidence is in `Temp/interaction-settings-visible/final-result.json`.
The regression transcript and baseline comparison are in
`Temp/interaction-settings-dev/regressions.log` and `baseline.log`.

The offline editor bundle and required runtime/source inventories include the
new dialog, speech lifecycle, migration and backend modules. Source validation
does not certify a rebuilt or installed executable. Never run the destructive
release builder solely to test this feature.

## Live Editor parameter reference — v1.91.0

| Parameter | Default | Allowed values | Stored for |
|---|---|---|---|
| Typing speed (WPM) (`editor_wpm`) | 100 | 40–160 | Account |
| Use the same typing speed for both (`link_speeds`) | Off | On / Off | Account |
| Pause after each segment (seconds) (`segment_pause`) | 0 | 0–3 | Account |
| Teaching detail (`teaching_detail`) | Balanced | Brief, Balanced, Detailed | Account |
| Offer suggestions for each new field (`suggestions`) | On | On / Off | Account |
| Suggestion presentation (`suggestion_display`) | Ghost text and choices | Ghost text and choices, Choices only | Account |
| Follow Tlamatini’s typing (`follow_typing`) | On | On / Off | Account |
| Editor font size (px) (`editor_font`) | 13 | 12–24 | This account/browser |
| Show line numbers (`line_numbers`) | On | On / Off | This account/browser |
| Wrap long lines (`wrap`) | Off | On / Off | This account/browser |

## Terminater parameter reference — v1.91.0

| Parameter | Default | Allowed values | Stored for |
|---|---|---|---|
| Typing speed (WPM) (`terminal_wpm`) | 50 | 20–160 | Account |
| Default shell (`shell`) | PowerShell | PowerShell, CMD, PowerShell 7 | Account |
| Command execution (`execution`) | Follow the task’s instructions | Follow the task’s instructions, I always press Enter | Account |
| Enable advisor in new terminals (`advisor`) | On | On / Off | Account |
| Command wait window (seconds) (`wait_seconds`) | 120 | 1–3600 | Account |
| No-output threshold (seconds) (`hang_seconds`) | 45 | 3–3600 | Account |
| User handoff wait (seconds) (`user_wait_seconds`) | 300 | 5–3600 | Account |
| Terminal font size (px) (`terminal_font`) | 13 | 12–24 | This account/browser |
| Cursor style (`cursor_style`) | Block | Block, Bar, Underline | This account/browser |
| Blink terminal cursor (`cursor_blink`) | On | On / Off | This account/browser |
| Preferred terminal layout (`terminal_layout`) | Tabs | Tabs, Tile, Side by side, Stacked, Grid | This account/browser |

## Voice parameter reference — v1.91.0

| Parameter | Default | Allowed values | Stored for |
|---|---|---|---|
| Narrate every Terminater command (`narrate_terminal`) | Off | On / Off | Account |
| Narrate each Live Editor teaching segment (`narrate_editor`) | Off | On / Off | Account |
| What to say (`narration_content`) | Brief explanation | Brief explanation, Command or code, Both | Account |
| When to speak (`narration_when`) | Before typing | Before typing, While typing, After typing | Account |
| Wait for narration before typing (`narration_wait`) | On | On / Off | Account |
| Announce command outcomes (`announce_outcomes`) | Errors and user-input requests | Errors and user-input requests, All results, Off | Account |

## Using voice and recovering from a refused save

Voice selection, rate, pitch and volume reuse **Config → Voice**. On a control
panel without that voice picker, choose the voice in the main chat in the same
browser. Ctrl+Shift+M toggles global mute; Escape stops speech. The wait-for-narration
setting applies when timing is Before typing. An explanation uses the optional tool
`explanation`; absent one, a generic step notice is spoken. Choose Command or code
to hear literal non-secret text. A muted or listening browser skips narration.

If another tab saved newer settings, reopen the dialog to load them before saving
your choices again. Invalid values reveal their tab and field. Save failure retains
the draft; it does not silently report success. Behavioral settings affect subsequent
actions, shell/advisor defaults affect new terminals, and appearance updates existing
views. See [the v1.91.0 release record](changes/2026-10-23-v1.91.0.md).
