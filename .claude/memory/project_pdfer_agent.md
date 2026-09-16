---
name: project_pdfer_agent
description: "PDFer document composer — 24 visual styles, 20 semantic themes, measured layouts, catalog mode and flow outputs"
metadata: 
  node_type: memory
  type: project
  originSessionId: 4403893e-b0ec-4196-b259-1acb8b155a39
  modified: 2026-09-16T02:08:43.000Z
---

## Current source behavior — 2026-09-15

PDFer composes PDFs from text/Markdown/HTML/images and merges or inspects PDFs. Its **24 explicit styles** span playful/nursery, cyberpunk, cosmic, electronics and Tlamatini families, independently of the **20 semantic `nuance` themes**. `style: auto` keeps automatic design; `mode: styles` returns the catalog with `status: inspected` and no PDF. Exact normalized aliases are supported; unknown styles retain the semantic theme with a diagnostic.

`pdfer_styles.py` and `pdfer_artwork.py` join ten existing flat helper siblings. Atelier uses measured cover/table layouts, an opaque cover reading area, title/subtitle continuation, fitted footer notes, contrast-checked small text and original deterministic vector artwork. Styles never raise the content's decoration ceiling. Legal, clinical and financial themes keep no ornament. Custom CSS with `engine: auto` selects legacy rendering; image-only layouts and existing merged PDFs keep their own appearance.

`style` and `style_family` join existing `INI_SECTION_PDFER` fields for Parametrizer. Check `layout_clean` and the diagnostic body before claiming an audit pass: `created` alone and blank audit fields do not establish one. No new runtime dependencies; optional model polish/design remain off. Output still defaults to the Documents known-folder/TlamatiniPDF, with collision-safe naming and Ask-Execs tier A.

Implementation validation on 2026-09-15: **130 PDFer tests passed**, and **24 two-page style samples (48 pages)** had clean audits. Generated previews/atlas and task logs were then removed. The gallery and atlas paths are ignored and reproducible with `scripts/verify_pdfer_styles.py`; no sample assets are runtime requirements. [Canonical guide, controls and commands](../../Tlamatini/agent/agents/pdfer/STYLES.md).

The dated record below describes the original 2026-07-26 implementation and that session's deployment state. Its 74-test count, commit/worktree status, prompt totals, installation paths and policy question are historical, not current checks. The current style extension has not established the state of a separate frozen installation.

## Historical implementation notes — 2026-07-26

**PDFer = agent #86, Tlamatini's DOCUMENT COMPOSER** — the WRITE side of the document family
(File-Extractor / File-Interpreter READ documents; PDFer AUTHORS them). Built 2026-07-26.

**ZERO new dependencies** — markdown + xhtml2pdf + pymupdf + reportlab + pillow + pypdf were
already pinned and already used by `agent/doc_generation`. The md→HTML→PDF pipeline + DEFAULT_CSS
are ported **INLINE** from `agent/doc_generation/mardown_to_pdf.py` (a pool agent can never
`import agent.*`). Backends import LAZILY → a missing lib gives `status: engine_unavailable`,
not a crash. `build.py::_AGENT_RUNTIME_IMPORTS` gained markdown/xhtml2pdf/reportlab/PIL so a
carried-Python regression FAILS THE BUILD (the numpy/cv2 lesson).

`mode` ∈ auto|markdown|html|text|images|mixed|merge|info|validate. `auto` sniffs (≥2 HTML tags →
html) which is what makes *"turn your last answer into a PDF"* one call. Saves to the **Documents
known-folder** — verified live that it correctly resolves Angela's **OneDrive-redirected, Spanish
"Documentos"** path, so never hardcode `%USERPROFILE%\Documents`.

**Three do-NOT-revert contracts** (full text: `docs/claude/recent-fixes.md` 2026-07-26):
1. Inline port + lazy imports + the build-verify list.
2. **Ask-Execs tier A** — it only *writes*, but `output_dir`+`filename` are free-form so it can
   clobber like File-Creator. The media agents stay ungated because they write collision-proof
   names into ONE fixed folder. Pinned by `test_ask_execs_allowlist.py`.
3. **`agent_paths.display_name_from_agent_type` needs `"pdfer": "PDFer"`** — `.title()` renders
   "Pdfer", violating the naming convention. Real bug the tests caught.

**New catalog section** — `views.PROMPT_CATEGORY_ORDER` gained `('documents', 'Documents & PDF')`
(position 4/15). Migration 0190 appends ids **109-113**, `sort_rank` 10/20/30/40/50; rank 10 is the
reserved Step-by-Step opener. `test_prompt_catalog_contiguous.expected_first['documents'] = 109`.
Catalog verified contiguous 1..113, no gaps.

**Migrations 0188** (Agent row 109) / **0189** (Tool row 258 `Chat-Agent-PDFer`) / **0190** (prompts).
Applied to the SOURCE DB. Tests: `agent/test_pdfer_agent.py` **74 tests, all green** — they drive
the REAL renderers (faking them would hide a missing carried-Python backend); they caught the
"Pdfer" naming bug AND a `fit`-layout bug (fitz.open on a raster gave A4 pages for every image).

**Status:** COMMITTED as `6207181f` "Implemented PDFer, a powerfull PDF maker agent" (working tree clean
for `agents/pdfer` + `migrations`). **Frozen `C:\Tlamatini` still needs `python build.py` + reinstall.**
Pre-existing suite failures proven unrelated by a `git stash` baseline — see
[[project_live_app_is_frozen_install]].

**Pre-launch preview backlog CLEARED (same session, Angela asked).** The 9 older uncategorized
wrapped agents were audited IN THE DEV TREE line-by-line (she pushed back on inferring from
config keys — she was right): PREVIEW = editor (writes file_path 'w'), nmapper + discoverer
(scan artifacts + packets at target), zavuerer (POST /v1/messages, costs money),
instant_messaging_doctor (retry_send=true really POSTs WhatsApp/Telegram);
OBSERVATIONAL = globber, grepper, mcp_doctor (STATIC triage — never connects), video_analyzer.
Preview keys verified to render with NO `<MISSING>` against each real config.yaml.
Now **64 wrapped agents, 0 uncategorized, 0 in both sets**; full suite 28F→27F.
**Open policy question for Angela:** instant_messaging_doctor can message a human via
retry_send but is NOT on the Ask-Execs tier-B allowlist — same gap class as the 2026-07-14
Deleter/Whatsapper one; left alone because it is her call. See [[project_ask_execs_policy]].
Related: [[feedback_agent_naming_conventions]], [[project_ask_execs_policy]],
[[project_prompt_catalog_grouping]], [[project_temp_templates_policy]].
