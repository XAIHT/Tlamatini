# Architecture atlas — how to rebuild `Tlamatini-Architecture.pdf`

`Tlamatini-Architecture.pdf` (repository root) is a multi-sheet A3 architecture
atlas of Tlamatini. **Every file tracked in git** appears twice: as a clickable
tile on an atlas sheet, grouped by architectural cluster, and as an entry in the
file index with a description read from the file itself. The overview sheets
(runtime topology, request lifecycle, intelligence core, agent ecosystem,
integration surfaces, frontend map, data model, build pipeline, quality and the
Python dependency matrix) are derived from the source on every run, not typed
by hand.

## Rebuild it after any change

```
git add <your new or renamed files>
python scripts/architecture_atlas/build_architecture_pdf.py
```

The atlas lists exactly what `git ls-files` returns, so stage new files first.
The script then runs three steps:

1. `gen_architecture.py` writes `Temp/architecture/Tlamatini-Architecture.tex`
   and `Temp/architecture/generator_report.txt` (standard library only).
2. A private copy of Tlamatini's own **LaTeXer** agent typesets it with
   `pdflatex` into `Tlamatini-Architecture.pdf` at the repository root.
3. The PDF is checked with PyMuPDF: the file index must list every tracked
   path and the atlas sheets must show every file name.

Exit codes: `0` done and verified · `1` typesetting failed · `2` the generator
could not place a tracked file (see `generator_report.txt`) · `3` the PDF is
missing files.

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

Part of Tlamatini, created by Angela López Mendoza.
