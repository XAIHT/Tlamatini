# 2026-10-07: installed PDF delivery and Desktop deletion incident

## Evidence

The installed application's log records LaTeXer delivering
`C:\Users\angel\OneDrive\Desktop\docker-cheatsheet_2.pdf` at 22:20:25 local time.
It was a 255,666-byte, three-page PDF. At 22:20:35 Mover received that path as a
scalar string, with the same Desktop as its destination and `operation: copy`.

Mover iterated the string as characters. A backslash resolved to the drive root,
whose empty basename resolved the target to Desktop itself. Its old directory
overwrite branch called `shutil.rmtree` before copying. The log records the
attempt and the eventual access-denied failure at Desktop; inspection then found
Desktop empty. The run reported zero successes and six failures, but exited zero
without a structured failure receipt. The chat subsequently claimed delivery.

Evidence was preserved under `Temp/pdf-mover-repair-20261007`: the installed log,
original Mover template, entire failed Mover runtime, original generated PDF,
and installed LaTeXer template before the layout-verdict patch. The historical
Mover runtime script was patched only after its original directory was copied.

## Changes

- Normalize scalar source paths; validate malformed inputs and operations.
- Reject filesystem-root sources, links/junctions at transfer endpoints, and
  ancestor/descendant directory transfers. Same-file copy/move leaves bytes intact.
- Merge directories without recursively deleting destinations. Regular files
  are staged, checked for matching byte count, then atomically published; moves
  remove the source only after publication. This preserves unrelated destination
  files; existing same-name regular files retain replacement semantics.
- Emit explicit Mover success/failure receipts and nonzero immediate failure
  exits. Failure summaries no longer display a success check mark.
- Preserve delivered PDFs while classifying TeX overflows above 5 pt as
  `created_with_findings`, with `success: False`, rather than clean completion.
  This does not substitute for rendered-page inspection.

Source and loose installed agent templates were patched. No executable rebuild,
installer run, database modification, or commit was performed. Existing unrelated
workspace edits were preserved. This is not full release acceptance or a new
live-chat end-to-end test.

## Validation

Development ran in a persistent foreground PowerShell console whose visibility
Angela explicitly confirmed. Transcripts are in
`C:\Users\angel\AppData\Local\Temp\tlamatini-pdf-repair-20261007`.

- Job 010: 126 Django tests passed across Mover safety, LaTeXer layout/delivery/
  model-repair/repair-ladder, verdict engine, and status vocabulary.
- Job 014: final 14 Mover safety tests passed after log-summary cleanup;
  five installed-agent cases also passed using bundled Python. They cover scalar
  copy, same-file copy, same-file move, missing source, and root refusal, with
  unrelated sentinel bytes preserved. Scoped `git diff --check` passed.
- Real installed LaTeXer first preserved a five-page PDF while reporting a
  36.5-pt overflow and exiting nonzero (job 011). After repairing the layout,
  compilation reported `compiled`, verified the delivered file, and exited zero
  (job 013). Poppler reopened and rendered every page for visual inspection.
- Job 015: final command/typography corrections compiled successfully; the
  delivered PDF is five pages and 282,627 bytes. Every final page was rendered
  and inspected, with no overlapping tables or clipped text found.
- Earlier harness attempts are retained: one assertion used the wrong verdict
  attribute, two verification jobs encountered unavailable `Get-FileHash`, and a
  direct unittest invocation lacked Django settings. Corrected runs and separate
  byte/hash verification supersede those failures; they are not counted as passes.

## Recovery and limits

The original generated PDF survived under the installed LaTeXer template project.
It was copied back to Desktop as `docker-cheatsheet_2.pdf`; its SHA-256 matched
`AA3C66218657BFCD04B9759910B396C754550DC4E82888CD0B591C7BD8EBBB23`.
A matching-name `tutorial_2.pdf` was recovered from `Downloads\Documents`; no
preincident hash is available to establish whether it was the same revision.

A repaired Docker document is delivered separately as `docker-cheatsheet.pdf`,
using a copy of the retained source, bounded wrapping tables and explicit page
groups. Original sources and recovered bytes remain preserved. Obvious malformed
Docker/Git commands were corrected against linked official references in the PDF.
Project-specific image/JAR examples were not executed against the user's project.

`maven-cheatsheet.pdf` was not found in the searched local locations. No affected
Desktop entries were found in the local Recycle Bin. There is no complete
preincident Desktop inventory, so complete recovery cannot be claimed. Online
OneDrive recovery remains uninspected: native Computer Use stopped because it
could not verify Chrome's current URL, and no further UI input was attempted.
