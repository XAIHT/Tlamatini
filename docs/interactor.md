<!-- Tlamatini Author Banner — Angela López Mendoza · @angelahack1 -->
# Interactor: teaching in the live canvas editor

Interactor is a module, not a workflow agent. It connects the existing chat and
CodeMirror editor without another process or terminal. Enable **Multi-Turn** and
the **Interactor** tool in Configure; leave **Live editor** enabled above the
canvas. Ask, for example:

> Help me create a Dockerfile for a Java servlet application with a landing page,
> using your text editor. Teach one step at a time and let me choose the values.

Tlamatini reads the exact open buffer, including unsaved edits. With no requested
path, `new` creates an empty, exclusively named file under
`Temp/interactor/<account>/<random>/Dockerfile`. She visibly types a short known
segment and uses `guide` to hand one field to the learner. The teaching card and
ordinary chat explain the field. A ghost suggestion appears only after a matching
prefix is typed. **Tab** accepts it, **Ctrl+Right** accepts a word, and **Esc**
dismisses it. Suggestions can be disabled; alternative values are welcome.
**Continue** sends an ordinary chat message requesting a fresh read and review.
**Another hint** and **Explain selection** also use normal chat. A chat draft is
never replaced by these buttons.

User input, selection, Escape, Stop, chat cancellation, and disconnect interrupt
AI typing. The typed prefix remains editable and undoable. Switching tabs,
minimizing, or covering the browser temporarily pauses the same action instead
of refusing it. Returning resumes from the exact next character, without another
chat request or duplicated text. Each visual action has up to two additional
minutes for visibility pauses; expiry cancels it without replay. Stop remains
available while paused. Changing the document cancels pending work; the document
and revision are checked again before an action starts. Explicitly switching
Markdown to Preview or hiding the canvas during typing still hands control back.
The model must finish its chat turn after a guide; further tool mutations in that
turn are refused. Continue starts a new turn. A changed document/revision refuses
an outdated edit instead of moving the user's caret or overwriting new text.

## Files and saving

Text/code, JSON, Dockerfile and Markdown use the same literal source buffer.
Markdown switches to Source for typing; its existing sanitized Preview remains
available. PDF and binary documents are not editable text. Live tutoring has an
explicit 262,144 UTF-16-unit limit; larger content is refused, never truncated.
Selections and ranges are UTF-16 offsets, including correct emoji boundaries.
The model's configured tool-result/context budget also applies: an oversized
receipt ends editing with an explicit refusal rather than delivering a partial file.

Typing does not save or execute anything. Save writes through the canvas's native
file capability, with its existing encoding, line-ending and disk-conflict
protection. No browser permission is fabricated. Manually opened browser files
need the user's existing Save/Save As destination before a model save. Ask Execs
gates Interactor `new` and `save`; visible buffer actions remain immediate.
Host-file open/create is restricted to a loopback chat and uses the existing
model path guard. Existing files are never overwritten by `new`.

## Design and research

Research was conducted before implementation, using primary documentation:

| Source | Useful feature | Applied here |
| --- | --- | --- |
| [Khanmigo](https://www.khanacademy.org/khan-labs) | Guided questions that build understanding | One learner decision at a time; explain and wait |
| [Codecademy AI features](https://help.codecademy.com/hc/en-us/articles/23400751016859-AI-Features-available-on-Codecademy) and [assistant design](https://www.codecademy.com/resources/blog/behind-the-build-ai-learning-assistant) | Exercise-aware help, hints and optional completion | Exact current buffer, selection explanation, another hint, optional suggestions |
| [CodeAid study](https://arxiv.org/abs/2401.11314) | Educational assistance with learner control | No hidden completion of the exercise; explicit handoff and editable work |
| [VS Code suggestions](https://code.visualstudio.com/docs/editing/ai-powered-suggestions) | Ghost text, partial acceptance and dismissal | Tab, Ctrl+Right, Escape and suggestion toggle |
| [Continue autocomplete](https://docs.continue.dev/ide-extensions/autocomplete/how-it-works) and [model roles](https://docs.continue.dev/customize/model-roles/autocomplete) | Debouncing, caching, contextual filtering and specialized completion models | Cache only the tutor's current field choices; no main-model request per keystroke |
| [Cursor Tab research](https://www.cursor.com/blog/tab-update) and [Instant Apply](https://cursor.com/blog/instant-apply) | Reduce model/pipeline latency and separate planning from application | Separate chat planning from local display/acceptance; do not imitate or claim vendor latency figures |
| [Copilot inline model design](https://code.visualstudio.com/blogs/2026/09/16/building-the-github-copilot-inline-suggestions-model-part-one) | Fewer serial model calls, selective suggestions | Immediate matching of already prepared choices; no suggestion when the prefix does not match |

This implementation deliberately does not send every keystroke to an AI. The
ordinary model prepares bounded field choices once; matching and acceptance are
local. Chat/model latency still applies when asking a new question or continuing.
No vendor's benchmark is presented as Tlamatini's performance.

## Internal contract

`agent/interactor/` owns the protocol, request context, bounded hub, authenticated
consumer, file bridge, structured tool and CodeMirror extension. The small static
bridge and CSS live in `static/agent/interactor/`; `interactor.html` owns its UI.
`prompt.pmt` documents the English/Spanish editor aliases and tutoring contract.
Migration 0218 seeds a Tool row and catalog example, with no Agent row.
`tools.tool_gate_table()` remains the single Configure/Compact/cost gate.

`/ws/interactor/` requires login, the exact Origin/Host pair, and a session key.
The server issues a random tab identity. Every chat request binds that identity
to its authenticated account/session through a ContextVar, including synchronous
tool workers. There is no global active editor and no cached disk substitute for
`read`. The browser sends receipts/access/stop only, never host-path commands.
Commands have unique IDs, deadlines, bounded queues, revision checks and receipts.
The server retains only the last observed document ID/revision within each chat
turn, so the model can omit those fields without weakening stale-edit checks.
An explicit mismatch requires another read and review; user takeover ends the turn.
Typing verification compares the entire returned buffer with the intended edit.
Timeouts do not replay a partially completed action.

New source/runtime assets are listed in the existing carriage checks. No new
third-party dependency is introduced; CodeMirror's existing Dockerfile mode is
included in the locally bundled editor.

## Verification

### Source and existing frozen package — 2026-10-21

The focused recheck uses `scripts/interactor_runtime_visible.py` and its
test-only `interactor_runtime_server.py`. They start the real source process or
the existing compiled executable, use an isolated database and normal browser
login, and exercise the production tool, hub, authenticated WebSocket, editor
and native Save dialogs. No responses or editor state are mocked. Source/frozen
loader identity and served asset hashes are recorded. Both browsers run visibly
with `headless=False`, a verified desktop gate and Shoter photos.

- 138 focused Django tests ran: **136 passed, two skipped**. These cover
  Interactor, canvas file access, native dialogs, Ask Execs, source carriage and
  Self-modify. The added mode regression checks the real application Temp path
  and session-bound save capability in both source and frozen configurations;
  this unit test alone is not proof of an actual frozen runtime.
- **Final DEV run: 19/19 visible checks passed.** It covers new Temp files,
  one-step Undo, local completion, exact unsaved reads, stale-edit protection,
  Dockerfile/Python/JSON/Java/HTML/Rust/Markdown/YAML, native Save As, menu Save,
  Ctrl+S, Stop, real 30-second tab absence and exact once-only `kind: ` typing,
  narrow layout, manual split preservation on resize, and read-only PDFs.
  At the narrow checkpoint the canvas was 320 pixels wide and the editable
  surface 439 pixels high, with all checked controls contained. Python and
  JavaScript lint passed.
- The existing `dist/Tlamatini_Release_v1.89.0/pkg.zip` was completely extracted
  into `Temp/interactor-modes/existing-runtime/`, including its carried Python
  and self-modify source. Its real `Tlamatini.exe` ran with `sys.frozen=True`,
  `PyiFrozenLoader` and `DEBUG=False`. Its executable hash matches the installed
  `C:\Tlamatini\Tlamatini.exe`:
  `aeb60efe030976d963790f1f1b409a1f8ecaf184bb4ea90dda427be9578c86dd`.
- **The existing frozen package fails this regression.** After a real
  30-second tab absence it refuses the first `kind: ` character with
  `Bring this chat tab into view before Tlamatini types.` and `retryable:false`.
  It contains the old bridge and a hub without visibility grace. Seventeen
  automated checks passed, but visual review rejected one of those passes:
  automatic sizing collapsed the narrow canvas, clipped controls and pushed
  the editor below the viewport. The combined verdict is **16 passed, two
  failed**; see `frozen/visual-review.json` alongside the original raw results.
- The narrow-layout defect was fixed in DEV by reserving 320 CSS pixels for
  the canvas during automatic sizing, allowing chat controls to wrap. Manual
  divider behavior stays unchanged. The editable container also fills the
  remaining height when no terminal is open, rather than stopping at the last
  line of text. The visible test now measures canvas
  width, editor height and containment of Save, Live editor, Clear canvas and
  Use as context, rather than trusting `is_visible()` alone.

Evidence lives in `Temp/interactor-modes/`: `source/` and `frozen/` retain
`final-result.json`, `SUMMARY.html`, desktop photos and application logs.
`source-before-layout-fix/` preserves the initial overly permissive check and
the visual rejection; `source-before-height-fix/` preserves the subsequent
40-pixel editor-height failure. `source-unit-application-final.log` holds the Django test
summary. This is focused editor/runtime validation, not full installer/release
acceptance or a new real-model planning benchmark. Angela requested checking
the existing package only: **no executable was rebuilt and the installed
application was not changed**.

### Visibility regression — 2026-10-21 (DEV)

- 61 focused Django tests passed (Interactor, native canvas file operations and
  Ask Execs), including bounded visibility grace and unchanged read timeouts.
- 15 source-carriage tests and JavaScript/Python lint passed. The owned browser
  harness and isolated server exited; no listener remained on port 8883.
- 42/42 visible checks passed in `Temp/interactor-visible/run-17/`. Real Chrome
  tab switches verified hidden-before-new/type/guide, a 30-second absence before
  typing the exact `kind: ` segment, mid-segment pause/resume, one-step Undo,
  cancellation while paused and document replacement while paused. Existing
  file-format, saving, completion and user-takeover cases also passed.
- `scripts/playwright_real_visibility.cjs` disables Playwright's forced-focus
  command in the test driver's memory only. No installed dependency is changed.
  The harness requires real `document.hidden` before starting its checks, so a
  driver change cannot silently turn these cases into fake visibility coverage.
- Shoter desktop photos and the results are in that run's `SUMMARY.html` and
  `results.json`. These are source/browser regressions; the installed release and
  real-model benchmark were not rerun for this fix.

Run `python manage.py test agent.test_interactor agent.test_canvas_file_views
agent.test_ask_execs_allowlist --noinput` from a verified visible PowerShell
`-NoExit` console. `scripts/interactor_visible.py` uses explicit
`headless=False`, an isolated database, real editor WebSockets and Shoter desktop
photos. Its visibility gate must be confirmed before checks proceed. Keep the
console/browser visible, watch the live transcript, and close via its owned
`close.confirmed` sentinel. Source tests do not certify a frozen release.

Create `Temp/interactor-visible/include-model.confirmed` before launching to add
the configured real model through the production multi-turn executor and Interactor
tool. Other tools are deliberately unavailable in that check; the ordinary chat
socket is captured and final answers use the normal chat renderer. This verifies
real model planning and editor interaction, not a complete production RAG startup.
`model-only.confirmed` selects just those checks. `rebuild.confirmed` before a
rerun rebuilds the editor in the same visible console and refreshes source assets.

### Source verification — 2026-10-21

- 229 Django tests passed: Interactor, native canvas saving, Ask Execs, Compact
  mode, context accounting, tool-failure recovery and asset-carriage suites.
- 35/35 visible checkpoints passed in `Temp/interactor-visible/run-9/`: 32 UI
  checks plus three real-model checks using the configured `glm-5.3-flash:cloud`.
  The model created Dockerfile in Temp, typed `FROM `, handed off the image field,
  provided local completion choices, then read and explained the learner's exact
  unsaved answer. This model is test evidence, never a hard-coded product choice.
- The browser checks cover Dockerfile, Python, JSON, Java, HTML, Rust, Markdown
  and a read-only PDF; native save bytes; Unicode; fresh reads; stale revisions;
  whole-step Undo; completion Undo/Redo; Escape, Stop and user takeover;
  suggestion buttons/toggle; selection explanation; normal Continue messages;
  draft preservation; tab identity invalidation; paused access; and narrow layout.
- A final 33/33 UI run in `Temp/interactor-visible/run-10/` additionally verifies
  that switching Markdown to Preview interrupts typing immediately. Together
  with the three real-model cases, 36 distinct visible checkpoints passed.
- Full-desktop Shoter photos, `results.json`, `model-evidence.json` and
  `SUMMARY.html` are retained in that run directory. No screenshot substitutes for
  the actual browser checks. The isolated browser and server were stopped after
  the run. No release build or installed-release acceptance is claimed.

The visible campaign found and repaired dismissed suggestions staying suppressed,
model identifier-copy fragility, and AI characters creating separate Undo groups.
The latter now uses one isolated CodeMirror typing event per teaching segment.
The final review also added interruption whenever the source view becomes hidden.

### Activation

Migration 0218 must be applied before Interactor appears in Configure tools and
the catalog. Restart the source server and reload the chat after applying the
normal migration chain from a verified visible PowerShell `-NoExit` console.
During the October 21 verification, the source database also had pending migrations 0214–0217. Those checks used isolated databases; they did not apply that chain to the existing source DB or replace an installed application. For v1.91.0 activation, migrations through 0220 (Interactor registration in 0218 and interaction preferences in 0220) must be applied through the normal startup/migration path.

## Live Editor preferences in v1.91.0

The canvas Settings button and **Config → Live Editor & Terminater** expose real
editor speed (default 100 WPM, range 40–160), a 0–3 s post-segment pause, teaching
detail, field suggestions, ghost text versus choices, and cursor following.
Manual scrolling suspends following for that segment. Font size, line numbers and
wrap configure CodeMirror itself; newly mounted documents reuse the saved appearance.

The tool read returns teaching-detail guidance for the model; exact wording remains
model-dependent. Each action carries an account preference snapshot through the
authenticated bridge. Saved speed overrides a model-supplied speed. Existing
document/revision checks, one-turn learner handoff and interruption rules remain.
Opening settings stops the active teaching action; Live editor access is an immediate
tab permission, while Save applies preference drafts to subsequent actions.

The Voice tab can speak an explanation, literal segment or both before/during/after
typing. A required before-typing narration can be stopped before any mutation. Missing
voice support offers explicit Continue without voice or Stop. Shared speech respects
mute/listening, excludes secret-marked content, and never replays a cancelled edit.
See [the full reference](interaction-settings.md) for defaults, storage and evidence.
