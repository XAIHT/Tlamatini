# Architecture atlas — how to rebuild `Tlamatini-Architecture.pdf`

> Latest released version: **[v1.97.0](../../docs/changes/2026-11-21-v1.97.0.md)**.

`Tlamatini-Architecture.pdf` (repository root) is a multi-sheet A3 architecture
atlas of Tlamatini. **Every application file in its declared inventory** appears twice: as a clickable
tile on an atlas sheet, grouped by architectural cluster, and as an entry in the
file index with a description read from the file itself. The overview sheets
(runtime topology, request lifecycle, intelligence core, agent ecosystem,
integration surfaces, frontend map, data model, build pipeline, quality and the
Python dependency matrix) are derived from the source on every run. The Canvas
overview also explains independent document state, explicit context snapshots
and Interactor's document identity handoff.

## Rebuild it after any change

```
python scripts/architecture_atlas/build_architecture_pdf.py
```

The inventory contains every path returned by `git ls-files`, including migration
history. During documentation work, it also includes these exact Canvas source
paths when they exist as unignored additions:

- `Tlamatini/agent/canvas_documents_context.py`
- `Tlamatini/agent/static/agent/css/canvas_tabs.css`
- `Tlamatini/agent/static/agent/js/agent_page_canvas_tabs.js`

The cover and generation report state the added-file count. Once tracked, these
paths appear only once. Other untracked files, caches and private data are not
silently included. Generation does not stage, commit or change Git metadata.
The same inventory is used by the generator and final PDF verification.
The script then runs three steps:

1. `gen_architecture.py` writes `Temp/architecture/Tlamatini-Architecture.tex`
   and `Temp/architecture/generator_report.txt` (standard library only).
2. A private copy of Tlamatini's own **LaTeXer** agent typesets it with
   `pdflatex` into `Tlamatini-Architecture.pdf` at the repository root.
3. The PDF is checked with PyMuPDF: the file index must list every inventoried
   path and the atlas sheets must show every file name.

Exit codes: `0` done and verified · `1` typesetting failed · `2` the generator
could not place a tracked file (see `generator_report.txt`) · `3` the PDF is
missing files.

The new Canvas sheet illustrates three open documents, `notes.md`, `main.py`
and `manual.pdf`, with only `notes.md` and `manual.pdf` selected as context.
It separates the browser connection from document IDs, retains dirty state and
describes explicit context acknowledgement, updates and removal. The existing
editor sheet covers native persistence and tutoring; the new sheet extends it.

Options: `--output <path>` writes the PDF elsewhere; `--skip-verify` skips
step 3. Set `TLAMATINI_REPO` to build the atlas of another checkout.

## Requirements

- `git` on PATH.
- A TeX distribution; **MiKTeX** is recommended (it installs missing packages
  on demand, so the first build can take several minutes).
- PyYAML and PyMuPDF, both already in `requirements.txt`.

## When the generator stops with exit code 2

A new top-level folder or file type has no cluster yet. Add a rule to
`assign()` in `gen_architecture.py` (and, for a new cluster, an entry in `META`
and `ORDER`), then run the build again. Only `Temp/` receives intermediate
files; nothing else in the repository is written except the PDF.

## Regenerate the companion guide and slides

From this edition's root, run the following in the visible development console:

```powershell
python Tlamatini/agent/doc_generation/refresh_project_docs.py
```

It rewrites the existing `tlamatini_app_summary.pdf` and
`Tlamatini_eXtended_Artificial_Intelligence_Humanly_Tempered.pptx`. Shared chapter
content keeps their 1.97.0 Canvas behavior aligned. The dossier inventories tracked
files plus all unignored working additions, a broader scope than this atlas's
explicit three-file allowance. Reports, inventories and page renders remain in
`build/documentation_refresh`; atlas intermediate files stay in `Temp/architecture`.

Inspect every page/slide after generation. The dossier checks PDF page bounds and
tree parity, plus PPTX geometry and text bounds. Native PowerPoint verification
requires PowerPoint/COM; an unavailable renderer is reported as skipped and must
not be described as a native pass. A supplemental non-native render can provide
visual evidence, with that renderer and limitation recorded.

Part of Tlamatini, created by Angela López Mendoza.
