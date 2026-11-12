<!-- Tlamatini Author Banner — Angela López Mendoza · @angelahack1 -->
# Canvas selection explanation — 12 November 2026

The Explain selection button now explains the exact selected, unsaved canvas
text independently of the chat toolbar. The English fix was verified first;
the Spanish edition then received the same behavior with localized messages.

## Cause and correction

The installed log at C:\Tlamatini\tlamatini.log records an Interactor read
refused by the 24,000-character tool-result budget. The old button sent a generic
chat request that read the entire approximately 46,855-character buffer. It
also required Multi-Turn and Live editor, refused an existing chat draft, and
used a chat route that could reject requests while checkbox changes rebuilt RAG.
The selected text never reached the model when that whole-buffer receipt failed.

The editor now captures all selected ranges at click time (or the complete file
when nothing is selected). An authenticated, validated canvas-explain request
sends those exact excerpts to the configured model without tools, loaded context,
history, internet, compacting, or self-modification instructions. Normal cancellation,
recovery, chat delivery, context measurement and usage accounting remain available.
Explanation code blocks are displayed without creating program/snippet records.
The draft, selection, file, and checkbox settings are preserved.

Selection size is bounded to 262,144 UTF-16 units across 64 ranges, subject to
the configured model's actual context capacity. The rest of the file does not
consume that selection limit. No excerpt is silently truncated. Existing
Interactor tutoring reads keep their complete-document contract and limits.

## Source verification

- 58 Django regressions passed in each edition, including all 32 backend mode
  combinations, Unicode and multiple ranges, a small selection in a five-million-
  character document, invalid input, readiness bypass, and read-only persistence.
- Targeted JavaScript and Python lint passed. Both offline editor bundles were
  regenerated; each carries 40 licensed packages. Static collection verified
  459 source files against their collected bytes in each edition.
- Visible Chrome checked all 256 combinations of the eight chat checkboxes in
  each edition, with Live editor paused and an existing draft. All sent the exact
  unsaved selection and preserved the draft and switches. Eleven checkpoints
  passed per edition, including no-selection whole-file delivery.
- The actual configured deepseek-v4.1-flash:cloud model explained an unsaved
  1536 value selected from a 52,049-unit file whose saved fixture still contained
  1280. English and Spanish replies used the unsaved value. Each production
  consumer/model run used zero tools with RAG deliberately marked not ready.
  The final English call used 370 prompt tokens; Spanish used 419.
- The browser harness captures the chat transport for deterministic checkbox
  testing, then passes the captured packet through the production consumer and
  configured model and delivers its response through the ordinary chat renderer.
  It uses isolated accounts/databases and real foreground, non-headless Chrome.
  Evidence: Temp/canvas-explanation-visible/final-result.json and run-*/ under
  each checkout. English final run: 7; Spanish final run: 1.
- One existing Spanish program-link test still expected the English label;
  its assertion now matches the existing translated label. Production link
  behavior was not changed.

These are source-run results. Installed executables were not rebuilt or replaced;
no release version, database backup/restore mechanism, or user configuration was
changed. Frozen-module and self-source inclusion lists carry the new service.
