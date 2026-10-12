<!-- Tlamatini Author Banner — Angela López Mendoza -->
# Markdown in the chat canvas

Local source change, 2026-10-11; not a published release.

Open, Reopen, dropping a file onto the canvas, generated-file links, and
Context → Set file as context recognize `.md` and `.markdown`, including
uppercase extensions. Both extensions were already in the shared file filter.
Markdown opens in Preview; Source shows the full original text with line numbers.
The preview uses the existing Tlamatini fonts, colors, surfaces and splitter.

The renderer supports CommonMark and GitHub-flavored Markdown: headings,
paragraphs, emphasis, strikethrough, links, images, nested lists, task lists,
blockquotes, fenced/indented code, tables, rules, escapes and safe embedded HTML
such as expandable details. Known code languages use the existing highlighter.
Tables and code scroll within their own frames; long documents are not truncated.
Math, Mermaid and other Markdown dialect extensions are not added by this change.

Choose folder resolves relative images and links to other Markdown files using
the browser's selected files. Select the document folder or a common parent;
the renderer finds the document's directory when its filename is unique. Files
remain on the device. Linked Markdown retains that folder selection, including
parent-relative paths. External web links open separately. Relative URLs never
navigate to application endpoints. Remote images load with no referrer.

Copy and Use as context take the Markdown source, not flattened preview text.
Save preserves the original local file bytes, including UTF-8 BOM and CRLF.
Generated Markdown saves as UTF-8. Loading another file or clearing the canvas
releases image object URLs. Plain text, source code, PDF and flow routing retain
their dedicated behavior.

`agent_page_markdown.js` uses locally vendored Marked 18.1.0 and DOMPurify 3.4.16.
The sanitizer allowlists HTML and attributes, scopes IDs, removes document classes
and active markup, and restricts resource protocols. Parsing does not depend on a
CDN. `scripts/vendor_frontend.py` pins archive integrity, licenses and per-file
receipts; runtime and self-modify snapshot contracts include both libraries.
The static cache suffix is `-markdown-canvas-1`.

## Visible verification

Follow [the visible-execution policy](../TestsVisiblesAndVisibleExecutionFromClaude2Codex.md).
From a verified visible foreground PowerShell `-NoExit` console titled
`Tlamatini Markdown Canvas - Visible Development`, run
`python -u scripts/markdown_canvas_visible.py`. Headless flags are refused.

The harness uses an isolated database/account in `Temp/markdown-canvas-visible`,
collects static assets, verifies every collected source byte, starts the real
source page on port 8875, and launches Chrome with `headless=False`.
It pauses at `browser-waiting.png`: inspect that full-desktop Shoter capture and
confirm the actual browser is visible before creating `browser-visible-confirmed`.
Monitor console output live throughout the run.

The suite exercises formatting, local resources, keyboard view switching,
clipboard, byte-exact downloads, long/empty files, drag/drop, unsafe markup,
text/code/PDF transitions, clearing, stale reads, linked documents, generated
content, native resizing/zoom and both context actions. Only the model WebSocket
transport is captured; this suite does not invoke a model or certify RAG ingestion.

Each checkpoint writes a full-desktop screenshot and updates
`Temp/markdown-canvas-visible/run-N/SUMMARY.html`. `final-result.json` records the
latest outcome. Chrome stays open for live review. `rerun.confirmed` repeats the
checks after a repair; `close.confirmed` ends the harness and reports its exit code.
The console remains open. This source validation does not certify a frozen build.

Verified on 2026-10-11: **30/30 visible browser checkpoints passed** in `run-7`.
The final run measured native Chrome zoom from devicePixelRatio 1.5 to 1.875
(125%) and verified its reset. Browser JavaScript errors: zero. JavaScript lint
reported zero errors (650 existing warnings); all 58 scripts parsed. Python
syntax and `git diff --check` passed. All 438 source static assets matched the
collected bytes. Full evidence: `Temp/markdown-canvas-visible/run-7/SUMMARY.html`;
live transcript: `Temp/markdown-canvas-work/10-checks-and-visual.log`.
