<!-- Tlamatini Author Banner — Angela López Mendoza -->
# Editing and saving canvas files

> Latest released version: **[v1.97.0](changes/2026-11-21-v1.97.0.md)**.

Introduced in v1.89.0 (2026-10-21), carried by v1.91.0 with configurable editor behavior. The tests below retain their actual dates; source verification does not certify a newly rebuilt installed executable.

Open text, source, Markdown and PDF documents in separate chat Canvas tabs.
Each tab keeps its own document, editing state and file identity. The filename
bar provides **Save**, **Save as…**, **Undo**, **Redo**, **Find** (including replace),
and **Wrap**, alongside Copy, Refresh, Clear canvas and Use as context. The status
shows unsaved changes and the text encoding/line endings. Ctrl/Cmd+S saves;
Ctrl/Cmd+Shift+S chooses another destination. Tab remains keyboard navigation;
use Ctrl+[ / Ctrl+] to change indentation. No code is executed by the editor.

The source editor is CodeMirror 6, bundled locally with its languages and
licenses. Source code, JSON, configuration files and plain text share the same
editing model. Unknown text extensions remain editable without syntax coloring.
Markdown retains sanitized **Preview** and editable **Source** views over the same
document; switching views preserves edits and undo history. Copy and Use as
context read the edited source. HTML and SVG remain source text, never an active
web page. PDF remains the complete PDF viewer: Save exports its original bytes
as a copy and preserves the viewed document and prepared context. Flow files and
images retain their existing dedicated routing.

## Work with several documents

Open or drop another supported document to add a tab without replacing the
documents already open. Up to **32 tabs** can remain open. Click a tab to return
to it; a text document retains its edits, undo history, selection and scroll
position. Markdown keeps its Preview/Source view. A PDF keeps its viewer,
navigation state and prepared context instead of becoming a plain-text editor.
The toolbar acts on the active document; **Clear canvas** closes that tab.

With focus inside the Canvas or its tab strip, **Alt+PageUp / Alt+PageDown** moves
between documents. Ctrl+Tab / Ctrl+Shift+Tab also works when the browser delivers
those keys to the page. Chrome normally reserves Ctrl+Tab for browser tabs, so
use the Alt shortcuts or click a Canvas tab there. These shortcuts do not switch
Canvas documents while focus is in chat, a terminal or an open dialog.

A tab's **asterisk (*)** means that document has changes not yet saved to disk.
Opening or switching tabs does not discard those changes. Saving one document
does not clear another document's asterisk. Wait for a pending save to finish
before switching documents; a failed or cancelled save preserves the edits.
Closing a dirty tab asks before discarding it. Page-departure protection checks
**every open tab**, including inactive ones and pending saves. The browser owns
the final warning and can still close or crash: save all work before leaving.
There is no promise to restore unsaved tabs after a reload.

Live Editor and [Interactor](interactor.md) identify the document they are
working on. Switching documents cancels an in-progress typing action instead
of letting it continue in the next tab. Interactor can select another open
document for the next part of a lesson; opening it does not select it as chat
context.

## Choose exactly which documents become context

**Open is not the same as context.** Use **Use as context** on each document you
want ordinary chat to use. For example, keep `notes.md`, `main.py` and `manual.pdf`
open, then select only `notes.md` and `manual.pdf`: `main.py` stays an editor tab
and is not included in that context set. PDF preparation still asks whether to
process images; selectable text alone remains the default.

The **Chat context** strip lists the accepted snapshots. Their tabs also carry
a **Context** badge. Selection changes take effect only after the server accepts
the complete replacement set; a rejected update keeps the previous context.
An account cannot replace context while its chat is running. The set accepts
at most 32 documents and 32 MiB of prepared UTF-8 text, including separators;
oversized context is rejected, never silently truncated. The configured model's
context capacity remains a separate limit.

Editing a selected document produces **Context · older** and changes the button
to **Update context**. The model still has the earlier snapshot until you click
that button and the replacement succeeds. **Saving does not update context;
selecting context does not save the original file.** A current selected snapshot
offers **Remove from context**, and each context chip can remove its snapshot.
Closing an editor tab retains its selected snapshot in the context strip so
that merely closing a view does not silently change what chat can read. Remove
that chip explicitly when it should no longer be context. Choosing another
file/folder context replaces the Canvas selection through the existing context
controls.

If the chat connection drops, the Canvas keeps its open documents but removes
confirmation badges and shows a reconnect notice. The server may have committed
an update whose acknowledgement was lost, so the page does not guess which
selection succeeded. Reconnect and verify context before continuing. Restoring
server context is separate from restoring editor tabs; unsaved tabs and their
browser file handles are not recovered after a page reload.

## Explain the selected text

Select one or more ranges and click **Explain selection**. Tlamatini explains
that exact click-time text, including unsaved edits. With no selected range, she
explains the current file. An existing chat draft and the editor selection stay
in place; the action does not edit or save the file.

The button works independently of Multi-Turn, Exec Report, ACPX, Ask Execs,
Step-by-Step, Compact mode, Self-modify and Add internet context. Live editor
may be paused and the Interactor tool may be disabled. The explanation uses no
tools, conversation history or previously loaded context, and does not wait for
a checkbox-triggered context rebuild. Its result appears in the ordinary chat.

A small selection is sent without the rest of a large file. Up to 64 ranges and
262,144 UTF-16 units are accepted in total, subject to the configured model's
context capacity. An oversized selection produces a clear message; it is never
silently shortened. Code outside the supplied excerpts is not available to the
explanation. See [Interactor](interactor.md) and the
[12 November verification](changes/2026-11-12-canvas-selection-explanation.md).

## Where Save writes

**Save** writes back to a browser-granted writable file handle, after permission
and a complete byte comparison with the loaded version. Otherwise it asks for a
destination. **Save as…** and the navbar **Save** open a native Windows Save As
dialog when using Tlamatini locally. Choose any writable folder, including your
project directory; the Downloads directory is not required. After native Save
As, Save writes to that destination without another picker. Refresh reads it.
PDF exports remain copies, so another export asks for a destination again.

Remote browsers with File System Access use their own Save As picker, on their
own computer. Unsupported native/browser combinations report the limitation;
the app never silently substitutes a download or claims a file was saved.

Cancellation, denied permissions and disk errors keep the document and its
unsaved marker. If another program changes a destination, Save refuses to
overwrite it; use Save as… to preserve your edits separately or Refresh to
review the disk version. Closing a tab, Clear and Refresh ask before discarding
its edits; opening another document adds a tab.
Edits made while a save is in progress remain unsaved after that snapshot is
written. Edits made during a pending load invalidate that replacement. A dirty
document in any tab also uses the browser's page-departure warning; closing a
page discards its in-memory documents, so save work before closing.

Editing context does not silently update the model's already loaded context.
Update context makes the selected document's current source available again; the pending context
replacement state survives Save. Saving under a new name does not falsely mark
that new name as already loaded context.

UTF-8, UTF-8 BOM and BOM-marked UTF-16 LE/BE decode strictly. Unsupported or
malformed encodings and binary content are refused before replacing the canvas.
Readable text with occasional non-printing controls (such as a bell or backspace
accidentally inserted by shell escaping) remains editable. Those characters are
preserved, not silently removed or repaired. A decoded NUL or control-dominated
content is still refused, regardless of the filename extension.
Unedited files retain exact bytes. Edited files retain encoding and BOM; existing
line terminators are retained by line, and additional lines use the first
original terminator (LF for a file without one). Empty files can be saved. Text
editing and native saves have a 64 MiB limit.

## Implementation and safeguards

`agent_page_canvas_tabs.js` owns tab identities, suspended document state and the
explicit selected-context set. `canvas_documents_context.py` validates each
complete selection, resolves PDF tokens for the authenticated user and writes a
separate application-owned bundle. Publication is atomic: failure preserves the
previous selection. An account-scoped execution reservation prevents a chat or
another context replacement from racing that publication.

`agent_page_canvas.js` retains document loading, refresh, context and generation
ownership. `agent_page_editing.js` owns the editable snapshot, saved baseline,
encoding, toolbar, write flow and dirty guard. The original code element remains
a hidden, synchronized compatibility mirror; CodeMirror state is the editing
authority. `agent_page_markdown.js` accepts source changes and sanitizes each
preview through the existing Marked/DOMPurify pipeline.

`canvas_file_views.py` exposes authenticated, CSRF-protected, loopback-only POSTs
at `/agent/canvas/save/` and `/agent/canvas/read/`. A first save grants a random,
expiring capability for the path chosen in the native dialog. Tokens belong to
both the account and login session; browser-supplied absolute paths are refused.
Subsequent writes require the last accepted content revision. Reading a newer
revision does not implicitly approve overwriting it. The browser adopts it only
when that refresh commits. Capabilities are bounded, expire after 12 idle hours,
and disappear at server restart; Save as… grants access again.

Writes stage a sibling file on the destination volume, flush it, recheck the
revision and replace the destination. Existing Windows files use `ReplaceFileW`
to preserve their security settings, named streams and creation time. An original
backup supports recovery from partial Windows failures; if Windows refuses
recovery, the error names the retained recovery copy. Successful saves remove
that backup. New files use `os.replace`. Failed staging preserves the original
and removes the temporary file. Native Save As uses a
new independent `native_dialogs.pick_save_file` with Windows overwrite
confirmation, sharing the existing Win32 definitions and foreground helper.
The protected database backup/restore mechanics are unchanged.

The build and source snapshot inventories carry the adapter, style, bundle,
licenses, manifest, sources and harness. Rebuild the offline bundle with
`node scripts/build_canvas_editor.mjs` in a verified foreground PowerShell
`-NoExit` console. Pinned dependencies and the lockfile reproduce the bundle;
startup and installed use require no npm or CDN.

## Research before implementation

- [CodeMirror guide](https://codemirror.net/docs/guide/) and
  [bundling example](https://codemirror.net/examples/bundle/): use a real document
  model and an offline browser bundle.
- [CodeMirror keyboard navigation](https://codemirror.net/examples/tab/): avoid
  trapping keyboard users in the source editor.
- [Chrome File System Access](https://developer.chrome.com/docs/capabilities/web-apis/file-system-access/)
  and [MDN Save picker](https://developer.mozilla.org/en-US/docs/Web/API/Window/showSaveFilePicker):
  permission, user activation and browser-availability boundaries.
- [Windows Common Item Dialog](https://learn.microsoft.com/en-us/windows/win32/shell/common-file-dialog):
  native destination selection and overwrite confirmation. The surgical
  integration reuses Tlamatini's Win32 common-dialog family.
- [Windows replacement semantics](https://learn.microsoft.com/en-us/windows/win32/api/winbase/nf-winbase-replacefilew):
  preserve existing file metadata and retain recovery data on partial failure.
- [Django CSRF](https://docs.djangoproject.com/en/5.2/howto/csrf/),
  [Python replacement semantics](https://docs.python.org/3/library/os.html#os.replace),
  [Marked sanitization warning](https://marked.js.org/): request authorization,
  same-volume write staging and safe preview rendering.

## Multi-document verification (2026-11-21)

From a visible foreground development console, run
`python -B -u scripts/canvas_tabs_visible.py` in this edition's root. The harness
uses visible Chrome, an isolated account/database, native Open/Save dialogs and
files under `Temp/canvas-tabs-visible`. Inspect `browser-waiting.png` before
creating `browser-visible-confirmed` there. Each `run-N/SUMMARY.html` contains
the checkpoints and full-desktop screenshots. Create `close.confirmed` to end
the test browser, or `rerun.confirmed` to repeat the checks.

The English full run passed 28 checkpoints; a focused follow-up also passed
Interactor opening a text file while a PDF was active. The Spanish full run
passed all 29 checkpoints. Each edition passed 46 context-transaction tests,
40 Interactor protocol/ownership tests, and targeted Python/JavaScript lint.
Checks include A+B selected with C excluded, stale/rejected context updates,
independent undo/save state, delayed-save and refresh races, inactive dirty-tab
departure protection, retained PDF state and real Windows keyboard input.

The normal chat WebSocket is captured and its context acknowledgements are
injected explicitly in browser tests. Backend routing, account ownership,
persistence and rollback are tested separately with model/network boundaries
substituted. These results do not claim live-model ingestion or acceptance of
a rebuilt installed executable. Native file writes, PDF text preparation and
authenticated Interactor actions use their actual local implementations.

## Verification

The [21 November multi-document record](changes/2026-11-21-canvas-document-tabs.md)
describes the English/Spanish browser campaigns, actual native saves and PDF
rendering, 46 context tests and 40 Interactor tests per edition. It distinguishes
captured chat acknowledgements from real backend dispatch and explicitly lists
the substituted model/network boundaries. The older runs below remain dated
evidence for their original editor, save and decoding scope.

Follow [the visible execution policy](../TestsVisiblesAndVisibleExecutionFromClaude2Codex.md).
From the verified foreground console run `python -u scripts/canvas_editing_visible.py`.
It uses real Chrome (`headless=False`), an isolated database, native file dialogs,
keyboard editing and exact disk-byte assertions. Inspect Shoter's full-desktop
`Temp/canvas-editing-visible/browser-waiting.png` before creating the visibility
gate. Monitor `live.log` every 5–15 seconds. Results and photos appear in each
`run-N/SUMMARY.html`; `final-result.json` records the outcome. Chrome remains open
for inspection until `close.confirmed`; `rerun.confirmed` repeats the checks.
Delayed-response cases are labeled fault injection. The model WebSocket is
captured; these are source editing/save checks, not model or frozen-build tests.

Verified on 2026-10-21: **29 distinct browser checkpoints passed** across focused
visible Chrome runs 7, 9, 11 and 12. They cover native Save As outside Downloads,
original browser-handle Save and Ctrl+S with Chrome's real write-permission
dialog, Rust/Python/JSON/HTML/Markdown/plain text, Unicode and encoding retention,
empty files, Undo/Redo, cancellation, external conflicts, delayed operations,
malformed/binary refusal, failed generated loads, narrow layouts, and PDF copies.
The final browser process exited 0. Earlier harness failures remain in the log;
the consolidated report selects only verified checkpoints:
`Temp/canvas-editing-visible/ACCEPTANCE.html` and `acceptance.json`.

The final Django regression run passed **93 tests, with 2 skips** across canvas
saving, native dialogs, file-drop routing and PDF context. This includes the
real Windows named-stream/creation-time preservation check and simulated partial
replacement recovery. Full JavaScript lint and parsing (99 files), targeted
Python Ruff checks and `git diff --check` passed. Collected static assets were
refreshed before the regression run. Evidence is retained in
`Temp/canvas-editing-visible/final-validation-transcript.txt`.

For the sparse-control Markdown regression, run `node --test
Tests/test_canvas_text_decoding.cjs` from a verified visible foreground console.
It covers UTF-8/UTF-16 decoding, unedited and edited Save byte retention, and
continued binary/malformed-encoding rejection. `npm test` includes these checks.
The focused browser harness is `scripts/canvas_text_decoding_visible.py --file
C:\project\README.md`: it opens the actual file through the native picker,
checks Preview/Source, Refresh, drop routing and invalid-file preservation, and
leaves Chrome open for review. It uses an isolated database and browser profile
under the repository's `Temp/canvas-text-decoding-visible`, never the user profile.

Verified on 2026-11-07: **13/13 decoder/Save regressions, 138/138 drop-router
checks and 7/7 visible browser checkpoints passed**. The browser opened
`C:\Development\XAIHT\Ruster\README.md` through the real Windows picker and
retained its exact bytes (SHA-256
`45408390f345f04f0ae91d87ebb631fea85ddd63133a88aa75a36c5b9f50dbe0`).
JavaScript errors: zero; JavaScript lint/parsing and targeted Python lint passed.
Evidence: `Temp/canvas-text-decoding-visible/results.json` and the visible
console transcript in `Temp/canvas-readme-repair/console.log`. The first browser
attempt stopped at a collapsed navigation menu; the final run handles that
layout and passed. These are source-browser results, not a new executable build.
The same day, the full Python quality gate compiled and linted 937 owned Python
sources (including the undefined-name pass); JavaScript lint and parsing of
108 source, harness and vendor files also passed. Full lint evidence:
`Temp/canvas-readme-parity/lint-results.json`.

## Editor appearance and tutoring settings (v1.91.0)

**Config → Live Editor & Terminater** and the canvas Settings button control the
real editor font (12–24 px, default 13), line numbers and wrapping. These appearance
choices persist per account in this browser and apply when a document is mounted.
They apply across Canvas documents; each tab retains its own content and view
state rather than a separate account preference profile.
They do not alter the file's contents or dirty baseline. The Live Editor tab also
configures Interactor pacing, segment pauses, suggestions and cursor following;
the Voice tab controls segment narration. Account behavior and local appearance
have separate storage. See [Interaction settings](interaction-settings.md).
