---
name: full-project-pdf-dossier
description: Use when asked to create or update a complete project PDF dossier, app summary, architecture report, or repository documentation PDF that must describe the whole system, how it works, how to use it, the complete tracked file tree, effective line counts by language excluding comments/blanks/docstrings, latest changes, and validation evidence.
---
<!--
═══════════════════════════════════════════════════════════════════
  ✦  T L A M A T I N I  ✦   —   "one who knows"
  Created by  Angela López Mendoza   ·   @angelahack1
  Developer · Architect · Creator of Tlamatini
  Tlamatini Author Banner — do not remove (Angela's name is kept in every build)
═══════════════════════════════════════════════════════════════════
-->

# Full Project PDF Dossier

Use this skill when the requested PDF must be a complete project artifact, not only a recent-change addendum.

## Required Output

The PDF must include:

- Product/system description: what the system is, what it does, and who uses it.
- Architecture: major runtime layers, request flow, important modules, and how subsystems cooperate.
- Usage guide: source-mode setup, daily chat usage, Multi-Turn guidance, workflow designer usage, and release/package path.
- Repository facts: current HEAD, tracked file count, agent count, frontend module counts, dependency count, and recent commits.
- Effective line inventory by language: file count, total physical lines, effective lines, and share of total effective lines.
- Effective line methodology: exclude blank lines, comment-only lines, and Python module/class/function docstrings.
- Largest effective source files.
- Complete tracked repository file tree, split across pages if needed.
- Clear generation timestamp and validation notes.

## Preferred Tlamatini Workflow

When working in the Tlamatini repo, prefer the deterministic generator:

```powershell
python Tlamatini\agent\doc_generation\refresh_project_docs.py
```

That script delegates to `complete_project_docs.py` and rebuilds both the full PDF and the matching no-overlap PPTX. If only the PDF is needed, it is still acceptable to run the full generator because the shared context prevents PDF/PPT drift.

## Mandatory Three-Pass Consistency Sweep

1. **Discover:** compare the last committed dossier revision with local HEAD, the current annotated version tag, and the worktree; inventory every tracked type with `git ls-files`; read README, BookOfTlamatini, current self-knowledge, prompts, agent catalogs, frontend assets, and recent source commits.
2. **Reconcile:** build a release-feature matrix mapping every recent behavior to its source implementation, public documentation, maintainer guidance, prompt rule, and relevant skill. Correct active counts from source, but preserve explicitly dated historical counts as history.
3. **Prove:** rerun searches for old active versions/counts/claims, run `python -m ruff check`, execute focused tests, regenerate artifacts, and verify text extraction, page count, complete-tree parity, and current-release coverage.

For the v1.48.15 release target and later, verify Grepper's BOM-first UTF-8/16/32 plus cp1252/Latin-1 search, the guarded five-class Exec Report vocabulary, Kuberneter's `returncode`/`success`/semantic-status shape, `Uninstaller.exe` preservation, and source-derived public/private build tests. Carry forward the v1.48.14 private External-MCP runtime, ten supervisor tools, inactive Memory/Sequential-Thinking defaults, tombstones, persistent Memory path, public/private catalog separation, nested-diagram restoration, and design-only transactional-updater label, plus the v1.48.13 placement/dialog/logging foundations.

## Inventory Rules

- Use `git ls-files` for the complete tracked source tree.
- Do not include `.git`, virtualenvs, `node_modules`, build output, caches, or generated local-only folders in the primary tree unless the user explicitly asks for local inventory.
- Count text files only for line inventory. Skip binary/media artifacts.
- For Python, use AST/tokenization when possible so docstrings and comments do not inflate effective lines.
- For JS/CSS/HTML/YAML/PowerShell/Batch/proto, strip normal block or line comments and then count nonblank lines.
- For Markdown, count nonblank authored documentation lines after stripping HTML comments.

## Quality Bar

- The PDF should read as an executive/technical dossier, not a dump.
- The complete tree can be an appendix, but it must be present.
- Tables should be readable and paginated safely.
- Include exact dates and commit ids when discussing current state.
- When generating or modifying Python source code for the dossier workflow, run `python -m ruff check` from the project root and fix reported errors before handing off.
- Verify by extracting PDF text or checking page count after generation.
- Confirm the complete tree in the PDF has exact path parity with `git ls-files`, not only the same total count.
