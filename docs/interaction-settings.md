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
  lacks both expected strings; these failures are unrelated to this feature.
* JavaScript lint/parse checks, focused Python lint, migration consistency and
  `git diff --check` passed. The offline editor bundle was rebuilt.

The browser evidence is in `Temp/interaction-settings-visible/final-result.json`.
The regression transcript and baseline comparison are in
`Temp/interaction-settings-dev/regressions.log` and `baseline.log`.

The offline editor bundle and required runtime/source inventories include the
new dialog, speech lifecycle, migration and backend modules. Source validation
does not certify a rebuilt or installed executable. Never run the destructive
release builder solely to test this feature.
