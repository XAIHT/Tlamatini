<!-- Tlamatini Author Banner — Angela López Mendoza -->
# Editing and saving canvas files

Implemented in source on 2026-10-21; this is not a claim about a published build.

Open a text or source file in the chat canvas and edit it directly. The filename
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
review the disk version. Open, Clear and Refresh ask before discarding edits.
Edits made while a save is in progress remain unsaved after that snapshot is
written. Edits made during a pending load invalidate that replacement. A dirty
document also uses the browser's page-departure warning; closing a page discards
its in-memory document, so save work before closing.

Editing context does not silently update the model's already loaded context.
Use as context makes the current source available again; the pending context
replacement state survives Save. Saving under a new name does not falsely mark
that new name as already loaded context.

UTF-8, UTF-8 BOM and BOM-marked UTF-16 LE/BE decode strictly. Unsupported or
malformed encodings and binary content are refused before replacing the canvas.
Unedited files retain exact bytes. Edited files retain encoding and BOM; existing
line terminators are retained by line, and additional lines use the first
original terminator (LF for a file without one). Empty files can be saved. Text
editing and native saves have a 64 MiB limit.

## Implementation and safeguards

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

## Verification

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
