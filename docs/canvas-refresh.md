<!-- Tlamatini Author Banner — Angela López Mendoza -->
# Refresh the open canvas file

> Current release: **[v1.91.0](changes/2026-10-23-v1.91.0.md)**. Dated records below retain their original evidence dates.


## Canvas, Views and avatar in v1.85.0

**Open** chooses a document. **Refresh** reads that same document again without a
file picker. It reports unchanged content, reloads changed content and retains
the previous document when a read fails. Markdown keeps Preview/Source and its
resources; PDF keeps page, zoom, rotation and scroll mode. Snapshot-only sources
explain why Refresh is unavailable. See [Canvas Refresh](canvas-refresh.md).

**Views → Canvas** hides or shows the canvas. Hiding makes chat full width while
keeping the document, refresh handle, PDF viewer, draft, chat history and context.
The setting is saved per account in this browser and synchronized between tabs.
Open, file drops and generated-document links reveal the canvas when needed.
While the canvas is hidden, the avatar is docked and its floating resize handle
is disabled. Showing it again enables the handle and keeps the avatar docked.

**Views → Reset layout** shows both panes, restores the initial divider positions
and docks the avatar, without clearing content. Shrinking the message box keeps
the portrait and its frame horizontally centered between Mic's left edge and
Send's right edge. The portrait remains square with a 120 px minimum.



Released in **v1.85.0**; implemented 2026-10-15. **Refresh** replaces **Reopen**. **Open** selects a
document; Refresh reads that same document again without a file-selection dialog.
Refresh itself writes nothing to the original file. Since the 2026-10-21 source
change, [canvas editing](canvas-editing.md) adds Save and native Save As; Refresh
asks before discarding unsaved edits and follows a newly saved destination.

| Situation | Button and feedback |
| --- | --- |
| No file | Disabled; asks the user to open a file. |
| File with retained read access | Enabled; reads the latest file content. |
| Reading or preparing a replacement PDF | `Refreshing…`, disabled, `aria-busy`; Cancel refresh is available. Duplicate requests are ignored. |
| Unchanged text or Markdown | `Up to date`, with the time checked. The button remains enabled because another program may change the file at any time. No rerender or context rebuild occurs. |
| Changed document | Complete content is replaced; feedback gives the time checked. |
| Chat/context operation in progress | Disabled with an explanation; normal completion restores its correct source-dependent state. |
| Read permission lost | `Allow refresh` requests read access to the retained handle. No file chooser opens. |
| File moved, deleted, locked, or unreadable | Previous displayed content is retained, the error is explained, and Refresh retries. Open can select a different file. |
| Snapshot-only browser or context-tree summary | Disabled with an explanation; there is no refreshable original source. |

Open uses the File System Access picker when supported (Chrome/Edge on localhost
or HTTPS). The granted handle lives only in this tab's memory. A real dropped
file keeps its file handle or file entry; the drop router captures access during
the original drop event, including drops relayed from the PDF frame. A browser
that supplies only a File snapshot can still display it but cannot reread its
original path. Browser page reloads discard the canvas and its handle.

Text and Markdown are compared by their complete decoded content, including
empty files; equal size or modification time is never proof of equal content.
Markdown refresh rerenders through the existing sanitizer, preserves Preview /
Source, reading position and explicitly selected resource files, and updates the
original bytes used by Save. Folder-selected resources remain browser snapshots;
choose the folder again to update those separate assets. Generated code/Markdown
links refresh their authenticated saved-content endpoint with `cache: no-store`;
they do not infer a disk path from a filename.

PDF refresh reads a fresh File and stages a new PDF.js viewer before replacing
the old one. A bad PDF leaves the old viewer visible. The page (clamped to the
new page count), zoom, rotation and scroll mode are preserved. Password changes
use the existing viewer's password form; cancellation keeps the prior viewer.
PDFs remain range-backed with no whole-file scan/hash, page-count cutoff or
automatic whole-document prefetch. A PDF is always reloaded on Refresh; an
unchanged-content claim is only made for text/Markdown, where it was compared.

When the canvas is already chat context, a changed document follows the existing
context replacement path, after the new content is ready. There is no intervening
empty-context rebuild. PDF context retains its existing text/image options and
cancellation. An unavailable connection or cancelled preparation leaves the old
backend context intact and explains that the displayed version still needs
**Use as context**. Clear, opening another document, a new chat operation and
Cancel invalidate pending reads so late results cannot resurrect a document.

## Verification

Follow [the visible-execution policy](../TestsVisiblesAndVisibleExecutionFromClaude2Codex.md).
Run `python -u scripts/canvas_refresh_visible.py` from a verified foreground
PowerShell `-NoExit` console. It opens real Chrome with `headless=False`, uses an
isolated database and fixture files under `Temp/canvas-refresh-visible`, and
requires inspection of its full-desktop Shoter `browser-waiting.png` before
creating `browser-visible-confirmed`. Monitor `live.log` every 5–15 seconds.
Each checkpoint has a Shoter photo and a `run-N/SUMMARY.html` entry. The native
Windows picker grants a real local handle; the harness changes its disk file and
clicks Refresh. Fault-injection cases are explicitly identified in the harness.
The model WebSocket is captured: these are source UI/transport checks, not live
model ingestion or frozen-release acceptance. Chrome stays open for inspection;
`rerun.confirmed` retries and `close.confirmed` ends with the recorded exit code.

2026-10-15 verification: **20/20 visible Chrome acceptance checkpoints passed**
(`Temp/canvas-refresh-visible/run-9/SUMMARY.html`, `final-result.json`; harness
exit 0). They cover real native-picker access, unchanged content, same-size and
same-timestamp edits, atomic saves, empty files, deletion/recovery, permission
recovery, single-flight cancellation, stale reads after Clear, Markdown views and
sanitization, context replacement and connection retry, operation locks, real
JSON drops, complete PDF replacement with page/zoom preservation, corrupt-PDF
recovery, PDF context connection failure, saved-content refresh/session refusal,
snapshot-only browsers and context summaries. Permission/connection failures are
injected; real file reads, edits, drops, rendering and PDF parsing are exercised.

Final `npm run lint` passed with zero errors (650 warnings); all 59 JavaScript
modules parsed. The 138 router cases and 39 focused Django tests
(`agent.test_file_drop_router`, `agent.test_pdf_context`) passed. The harness
compiled and `git diff --check` passed. Source/collected static bytes were checked
by the regression suite. The initial visibility refusals stopped workloads;
acceptance resumed only after verified foreground access. These checks exercised the Refresh behavior now included in v1.85.0.
