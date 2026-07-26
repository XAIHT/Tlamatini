---
name: project_pdfer_agent
description: "PDFer (agent #86) — the document composer; zero new deps, Ask-Execs tier A, new \"Documents & PDF\" prompts section"
metadata: 
  node_type: memory
  type: project
  originSessionId: 4403893e-b0ec-4196-b259-1acb8b155a39
  modified: 2026-07-26T21:45:11.901Z
---

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
