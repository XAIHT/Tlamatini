<!-- Tlamatini Author Banner — Angela López Mendoza · @angelahack1 -->
# Canvas document tabs — behavior and verification, 21 November 2026

> Latest released version: **[v1.97.0](2026-11-21-v1.97.0.md)**.

The chat Canvas holds up to **32 independent documents**: text, source code,
Markdown and PDF. Opening a document adds a tab. Switching retains text,
undo/redo, selection, reading position, encoding, save destination and Markdown
view/resources; PDF tabs retain their viewer and page/zoom/rotation/scroll state.
Workflow files and chat image attachments keep their existing routes.

## What the user controls

| Action or indicator | Meaning |
| --- | --- |
| Active tab | The document targeted by Copy, Save, Refresh and the document toolbar. |
| Asterisk (*) | This document has work not yet saved to disk; inactive tabs count too. |
| Use as context | Add an explicit snapshot to the selected document set. Other open tabs remain excluded. |
| Context | The server accepted this document's selected snapshot. |
| Context · older / Update context | The open document changed since the accepted snapshot; update it explicitly after review. |
| Remove from context / context chip × | Remove only that snapshot from the set. |
| Close tab / Clear canvas | Close that editor/viewer, asking before discarding dirty text. A selected snapshot remains in the context strip until removed. |
| Alt+PageUp / Alt+PageDown | Switch Canvas documents when the Canvas or its tabs have focus. |

Ctrl+Tab / Ctrl+Shift+Tab is also handled when delivered to the page, but Chrome
reserves it for browser tabs. The browser owns the final page-departure warning;
the app checks all dirty tabs and pending saves, but cannot guarantee prevention
of browser exit, crashes or recovery of unsaved buffers. Save before leaving.

Saving a file and accepting context are separate actions. Refreshing or editing
a selected document leaves its previous context snapshot in place. On a lost
connection, open documents remain, while confirmation badges are cleared and a
notice asks the user to reconnect and verify context; a lost acknowledgement is
not reported as success. Browser reload does not restore open editor tabs.

## Context and tutoring boundaries

The full selected set has a 32-document / 32-MiB prepared UTF-8 limit, including
document separators. It is refused rather than silently shortened. PDF reading
remains range-backed; selecting a PDF still requires its normal preparation and
user-bound signed token. The model's context capacity remains a separate limit.
The backend stores a distinct, account-owned bundle and acknowledges the set
only after preparation and persistence succeed. Failure rolls back to the
previous selection. Legacy context changes and reconnect operations share the
same account execution reservation, including their awaited rebuilds; tracked
tasks keep WebSocket control messages responsive and release ownership on exit.

Interactor's `documents` action lists metadata without reading every document.
After a fresh `read`, `activate` uses an exact `target_document_id`, checks the
source document/revision and returns the target's verified snapshot. Further
teaching applies to that target. Switching tabs interrupts ongoing typing; an
old action is never redirected to another document. PDF activation returns
document identity, not an editable text buffer. Opening a text document from an
active PDF keeps the PDF in its own tab.

## Observed source verification

All runs below were visible development runs, not installed/frozen acceptance.

| Edition and run | Observed result |
| --- | --- |
| English full browser campaign, run-7 | 28/28 checkpoints passed. |
| English targeted follow-up, run-9 | 2/2 passed: PDF-active → Interactor open and presentation checks. |
| English PDF rendering, run-10 | 1/1 passed with actual rendered PDF pixels. |
| Spanish full browser campaign, run-1 | 29/29 passed, including PDF-active → Interactor open. |
| Spanish PDF rendering, run-2 | 1/1 passed with actual rendered PDF pixels. |
| Each edition, context backend | 46 tests passed, including actual whole-receive dispatch, selected/unselected sets, account ownership, persistence/rollback and legacy overlap. |
| Each edition, Interactor backend | 40 tests passed. |
| Each edition, targeted Python/JavaScript lint | Passed. |

Browser chat WebSocket acknowledgements were captured/injected to make the UI
checks deterministic. Backend dispatch and ownership were tested separately
with model/network boundaries substituted. Native Save and disk-byte checks,
PDF token preparation over local HTTP, the authenticated Interactor WebSocket
and native operations were exercised directly. These results do not certify
live model answers, every model provider or a newly built executable.

Evidence on the verification machine:

- `C:\Development\XAIHT\artifacts\canvas-tabs-20261121\verification.json`
- `C:\Development\XAIHT\artifacts\canvas-tabs-20261121\session.log`
- Each edition's `Temp/canvas-tabs-visible/run-N/SUMMARY.html` and full-desktop
  screenshots for the runs listed above.

See [Canvas editing](../canvas-editing.md), [Refresh](../canvas-refresh.md),
[Markdown](../markdown-canvas.md), [PDF](../pdf-canvas.md),
[Interactor](../interactor.md) and [maintainer architecture](../claude/architecture.md).
Historical verification entries elsewhere retain their original dates and scope.
