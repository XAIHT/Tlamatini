---
name: project-latexer-agent
description: "LaTeXer (#87) — LaTeX typesetting agent embedding mcp-latex-server natively; needs MiKTeX; latexmk-needs-Perl trap."
metadata: 
  node_type: memory
  type: project
  originSessionId: b00b2424-75f3-4d5e-a470-90bfb886bb53
  modified: 2026-08-05T06:35:49.469Z
---

**LaTeXer** (agent #87, 2026-08-05) — Tlamatini's LaTeX typesetting agent, the sibling of
[[project-pdfer-agent]]: **PDFer COMPOSES** a PDF from Markdown/HTML/images, **LaTeXer
TYPESETS** one from `.tex` (maths, bibliographies, cross-refs, index).

**It embeds the whole `mcp-latex-server` MCP NATIVELY as an agent** — no MCP server, no
FastMCP/pydantic/uv, no stdio child, no catalog entry. Stdlib-only pool script
(`subprocess`+`shutil`+`glob`+`re`+`urllib`), **zero new dependencies**, so the <2 GB
release budget is untouched and both inclusion sweeps were CLEAN with no manual work.

**THE ONE PREREQUISITE IS MiKTeX** (https://miktex.org/download). Tlamatini bundles no TeX
distribution (several GB). MiKTeX specifically, because `--enable-installer`
(`auto_install_packages`, default true) makes it **install a missing `.sty` on demand
mid-compile** — that is what makes LaTeXer work out of the box. TeX Live/MacTeX are used
if present but cannot self-heal. No LaTeX → `status: refused` naming MiKTeX;
`action: install` fetches the official installer (Nmapper's "use, not redistribution").

## Three real bugs found by testing it live — do NOT reintroduce

1. **⚠️ `latexmk` NEEDS PERL.** `latexmk.exe` ships with EVERY MiKTeX install so
   `shutil.which()` always finds it — but it is a **Perl script**, and most Windows boxes
   (Angela's included) have no Perl. Presence proves nothing. Fixed with
   `_latexmk_usable()` (a `-v` probe, fails CLOSED) + automatic fallback to LaTeXer's own
   convergence loop. Pinned by `LatexmkUsabilityTests`.
2. **Missing-package extraction was dead code.** `_parse_latex_log` ran the
   ``File `x.sty' not found`` regexes AFTER the `! ...` / `file:line:` branches, both of
   which `continue`. In a real log that message is ALWAYS on such a line, so the most
   actionable diagnostic (and the whole MiKTeX auto-install story) never fired. The
   extraction must stay FIRST in the loop body.
3. **"0 errors" with no PDF and no explanation.** When the log parser finds no
   LaTeX-shaped error the failure came from OUTSIDE LaTeX, so the raw tool output is now
   quoted. Never report a failure the user cannot act on.

## Contracts
- Display name **`LaTeXer`** — `str.title()` gives "Latexer", so the
  `agent_paths.display_name_from_agent_type` override is MANDATORY (see
  [[project_agent_table_wiped_on_boot]], [[feedback_agent_naming_conventions]]).
- `-interaction=nonstopmode` + `stdin=DEVNULL` are non-negotiable — they are what stop
  LaTeX hanging forever waiting for keyboard input.
- `shell_escape` OFF by default (`\write18` = arbitrary code execution).
- Ask-Execs **tier A twice over** (writes .tex+PDF to free-form paths, edits in place,
  `clean` deletes, and runs a real compiler) — see [[project_ask_execs_policy]].
- `clean` never touches a `.tex`, `.bib` or `.pdf`; `_work_base()` returns `""` when
  nothing is configured so an empty config can't sweep the live agent pool.

## Verified live (2026-08-05, source instance)
MiKTeX 26.2 at `%LOCALAPPDATA%\Programs\MiKTeX` (per-user install — the path that had to
be added explicitly). Hard multi-file project (biblatex+biber, makeindex, `\input`,
Spanish babel): master auto-detected, 3 passes, 0 errors, 2 pages. One-call fragment →
PDF. `scaffold_compile` beamer → 2-page deck. **96/96 agent tests**, 209 cross-cutting
tests OK, ruff+eslint clean, both inclusion sweeps CLEAN.

**Not committed / not pushed. The FROZEN `C:\Tlamatini` install needs `python build.py`
+ reinstall; the source instance needs a restart for `mcp__tlamatini__latexer` to appear.**
Catalog prompts 114-117 (`documents`, ranks 60-90). Migrations 0191/0192/0193.
Agent count 86 → 87.
