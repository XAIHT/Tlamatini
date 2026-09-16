# PDF canvas and document context

The Agent Page **Open** and **Reopen** native file pickers accept `.pdf` and
`application/pdf`. A PDF opens inside the existing canvas with its original
filename in the existing header. The original Copy, Reopen, Clear canvas and
Use as context buttons keep their markup, colors and styles.

The chat/canvas divider keeps pointer capture while resizing across the PDF
frame. Release, cancelled touch input, lost capture and window focus loss end
the drag and restore normal PDF interaction. Both layout dividers retain their
keyboard controls and support mouse, pen and touch input.

## Reading and canvas actions

The embedded Mozilla PDF.js viewer provides every page, text selection, page
navigation, zoom, fit width/page, rotation and continuous/single-page scrolling.
It includes fonts, character maps, annotation display, image decoders and XFA
support. Password entry happens inside the viewer. Invalid files and incorrect
passwords produce visible errors. PDF scripts are not executed.

- **Copy** reads selectable text from every page. Scans without selectable text
  explain that OCR is required; Use as context can perform visual interpretation
  when Process images is enabled.
- **Save As** downloads the original PDF bytes with a PDF extension.
- **Use as context** processes the complete original document as described below.
  Its existing toggle removes the selected context normally.
- **Reopen** replaces the file and, if the canvas was already context, prepares
  the replacement before rebuilding context. Cancelling preparation leaves the
  previous backend context available.
- **Clear canvas**, text-file selection and generated text remove the PDF frame,
  terminate its worker and invalidate outstanding reads. Generation checks stop
  an earlier asynchronous file read from overwriting a newer selection.

Opening and reading use local browser file ranges and do not upload the PDF.
There is no application file-size or page-count cutoff. The viewer reads
`File.slice()` ranges instead of copying the complete file into an ArrayBuffer;
streaming and automatic prefetch are disabled. PDF.js renders visible/nearby
pages and recycles old canvases. Individual canvases have a bounded pixel budget
with detail rendering for zoomed regions. Above 10,000 pages, upstream PDF.js
switches to single-page scrolling to avoid browser scroll-height limits; all
pages remain reachable. Available memory, disk space and document complexity
still determine practical capacity. Copying complete text necessarily allocates
that text in memory.

## Use as context and progress

Clicking Use as context opens a native modal with the filename, input size,
elapsed time and a notice that large PDFs and image analysis can take a while.
**Process images** starts unchecked every time. No upload, extraction or model
work starts until the user presses **Continue**. Unchecked means selectable text
only: page rendering, image extraction and Image-Interpreter are all skipped.
Checked enables the full text/image workflow below. Text-only mode needs no
Image-Interpreter configuration or vision service. A PDF without selectable text
shows an explanation to retry with Process images enabled instead of loading an
empty document. On mixed documents, pages without selectable text are marked in
the index. Cached context packages are kept separately for each mode, so changing
the checkbox cannot reuse a result prepared with the other option.

Its four progress rows show real upload bytes, extracted pages, analyzed images,
and final context loading; the image-analysis row says Skipped in text-only mode.
The timer and hourglass begin on Continue, rather than while awaiting a choice.
The final row is indeterminate until the server
confirms completion; it does not invent a completion percentage or time estimate.
The rotating browser title displays its existing hourglass throughout PDF work,
including upload and image analysis. PDF and chat activities own their busy
indicators independently so an unrelated chat message cannot clear PDF activity.
Successful context loading automatically closes the dialog; failures remain
visible with their error message. Image-analysis warnings remain in the PDF
viewer status and saved reports after the dialog closes.

1. An authenticated, CSRF-protected multipart request uploads the original PDF
   to the local Tlamatini server. Django spools large uploads to disk.
2. A background worker uses the existing PyMuPDF dependency to extract all pages'
   selectable text. With Process images enabled, it also extracts every unique
   embedded image and renders a preview of every page. Previews also preserve
   scans, vectors, annotations and inline images.
3. When enabled, the existing **Image-Interpreter** engine analyzes every preview and extracted
   image using its saved configuration: two vision models followed by its merger.
   Its engineered prompts remain in place, with a PDF-specific request for OCR,
   chart/table/diagram interpretation and explicit uncertainty. Processing uses
   the configured model services and can require network access or running Ollama.
4. Full extracted text, plus artifact paths and complete reports when images were enabled, are written
   to a UTF-8 index. A user-bound signed token passes that index to the existing
   contextual RAG setup. The normal session/context path is saved for restoration.
   Model responses use normal retrieval and model context limits; the complete
   index is retained without a PDF-specific text cutoff.

This uses File-Interpreter-equivalent complete text/image extraction without
importing that executable's process setup. Image-Interpreter itself is reused,
not duplicated: its reusable pipeline builder is import-safe, while its executable
still performs its original logging/cwd/process initialization in `main()`.

Vision failures and partial results are kept in per-image reports and the index.
The dialog reports incomplete analyses instead of claiming all images succeeded.
A failed RAG load is reported separately and permits retry. No live model calls
are made merely by opening a PDF.

**Cancel** during preparation aborts browser requests and signals the backend.
Before Continue, Cancel, Escape and native dialog closure simply dismiss the
options without any upload, extraction, analysis, backend job or RAG change.
A user-scoped request UUID handles cancellation even before the upload's job
response arrives. The worker checks cancellation between upload chunks, pages
and image calls. An already running Image-Interpreter model request may finish
before cancellation takes effect; its configured engine has a request timeout.
After context loading starts, **Close** dismisses the dialog while the normal
chat status continues to show the operation.

## Organization and storage

Frontend code is under `Tlamatini/agent/static/agent/`:

- `js/agent_page_pdf.js`: file/frame lifecycle, authenticated message bridge,
  upload progress, job polling and cancellation.
- `pdf/canvas.html`, `js/pdf_canvas_viewer.js`, `css/pdf_canvas.css`: isolated
  PDF viewer. Its stylesheet does not affect chat or canvas header buttons.
- `js/pdf_context_progress.js`, `css/pdf_context_progress.css`: modal behavior
  and styling. The Agent Page template contains markup and external references,
  with no new inline JavaScript.
- Existing canvas/context/chat modules coordinate the established actions.

Backend code is under `Tlamatini/agent/`:

- `pdf_context.py`: complete extraction, private artifact packages and signed
  context-token validation.
- `pdf_image_analysis.py`: adapter to the actual Image-Interpreter engine.
- `pdf_context_jobs.py`: a serial background job queue with cancellation and
  authenticated status snapshots. Each image engine invocation runs its two
  configured vision requests in parallel, as before.
- `pdf_context_views.py`: prepare/status/cancel endpoints, wrapped by the existing
  login/CSRF/method protections in `urls.py`.
- `consumers.py`: validates ownership and hands the prepared index to normal RAG,
  then confirms completion to the progress dialog.

Packages live below the runtime agent root at
`context_files/pdf_canvas/<user-id>/<document-uuid>/`. Each contains `source.pdf`,
`document.txt` and, when enabled, page previews, embedded images and `.analysis.txt` reports.
Successful packages persist for session context restoration. Failed/cancelled
preparations remove their own incomplete package; staging uploads under the app
Temp directory are removed when the job ends. In-memory job status is local to
this desktop server process; restarting during preparation requires retrying.
Completed status entries expire after one hour during subsequent job activity.
Passwords are used in memory for parsing and are not saved in localStorage,
context text or application logs.

## Dependencies and distribution

[Mozilla PDF.js](https://github.com/mozilla/pdf.js) **6.3.289** is vendored under
`static/agent/vendor/pdfjs` with its unmodified Apache-2.0 license, API, worker,
viewer, character maps, standard fonts, annotation images, ICC profile and WASM
decoders. Reproduce the pinned npm distribution with:

```powershell
python scripts/vendor_pdfjs.py
```

The script verifies SHA-512 integrity before extracting an explicit subset.
Rendering needs neither npm nor a CDN at runtime. No new Python package is
required: `requirements.txt` documents use of the existing `pymupdf==1.26.5`,
PyYAML and Image-Interpreter dependencies. Existing collectstatic/build.py
packaging includes the assets. Django and WhiteNoise explicitly serve `.mjs`
as JavaScript and `.wasm` as WebAssembly, including on Windows hosts with
conflicting registry MIME associations.

Frozen builds explicitly collect the PDF backend, its Image-Interpreter adapter
and reusable engine, and PyMuPDF in the web application's Python archive. The
existing archive check requires those modules. `pyinstaller_hooks/hook-pymupdf.py`
also collects MuPDF's native libraries beside its extension modules; the carried
Python used by pool agents is a separate runtime and does not supply these imports
to `Tlamatini.exe`. The editable image configuration is read from
`<install>/agents/image_interpreter/config.yaml`, and PDF context packages and
upload staging use `<install>/context_files` and `<install>/Temp`, respectively.

Job IDs use cryptographic UUIDs with a `getRandomValues` fallback when
`crypto.randomUUID` is unavailable, so context preparation also works when the
installed server is accessed through a plain-HTTP LAN address. This creates no
upload or backend job before Continue.

## Validation

```powershell
python -m pytest Tests/test_pdf_canvas_browser.py Tests/test_pdf_canvas_assets.py -q
python Tlamatini/manage.py test agent.test_pdf_context agent.test_image_interpreter_agent agent.test_js_gates --noinput
node scripts/check_js_parse.mjs
```

The browser suite uses real Chromium, actual application markup/modules and PDF.js,
an isolated HTTP server, generated PDF fixtures and real extraction/background
jobs. It covers first/middle/last pages, zoom/rotation/resize, original-byte saves,
copy, context handoff, PDF/text switching, scanned and password-protected files,
a sparse 256 MB PDF read in ranges, navigation to page 10,001, progress,
cancellation and retry. It rejects external asset requests. Set
`PDF_CANVAS_HEADED=1` to watch; `PDF_CANVAS_SCREENSHOT` and
`PDF_PROGRESS_SCREENSHOT` optionally save screenshots; `PDF_OPTIONS_SCREENSHOT`
captures the unchecked option and Continue button before processing.

Backend tests verify signed-token ownership, login/CSRF/method checks, package
cleanup, pre-upload cancellation and the actual consumer handoff. Integration
checks run the real Image-Interpreter pipeline against an isolated fake HTTP
model server, exercising both vision requests and the merger without using the
user's model services. Static distribution is checked with real collectstatic
and Django/WhiteNoise responses. Application JavaScript parsing, ESLint and Ruff
are checked separately.

Validated on 2026-09-16: the latest PDF UI regression run passes **12 browser/
static-asset tests**, including frame-crossing drag/release, touch cancellation,
focus loss, keyboard resizing, title-busy ownership, automatic dialog closure,
waiting for Continue, default text-only processing and independent caches for
each processing option. **32 Django backend, Image-Interpreter and JavaScript-gate
tests** also pass, including explicit opt-in validation and skipping all image
work by default. All **43** application JS files parse; ESLint and Ruff
pass for the changed application JS and Python tests.
The progress dialog was visually inspected, and all four original canvas buttons
retain their exact markup and styles. Live configured model services and a full
frozen executable build were not exercised; the model HTTP integration and
collected static distribution were tested in isolation.

A subsequent frozen-mode review on 2026-09-16 used only source/dependency reads
and comparisons. It added explicit frozen PDF dependency collection and the LAN
UUID fallback described above. No tests, application, build or background jobs
were started during that review; the earlier test results predate these changes.
An already-running build must be restarted from the updated sources to guarantee
that it includes them.

Broader pre-existing checks are not all green: the mutable-state suite flags
`canvas` in unchanged `acp-globals.js` / `avatar_presence.js` (the latter is
function-scoped), and the authorship sweep reports 195 existing source files
without its required banner. New authored PDF files carry the banner; unmodified
Mozilla assets are exempted to preserve upstream attribution and license.
