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

> Current release: **[v1.90.0](../../../docs/changes/2026-10-22-v1.90.0.md)**. Dated records below retain their original evidence dates.


> **HEADLESS IS FORBIDDEN. VISIBLE FOREGROUND EXECUTION ONLY.** Every command, automated test, diagnostic, script, build, agent and browser must run in a visible foreground window on Angela's real desktop. Use forked CMD/PowerShell windows, `execute_forked_window: true`, and `headless: false`. Monitor live; if visibility cannot be confirmed, do not run. Read the [mandatory execution policy](../../../TestsVisiblesAndVisibleExecutionFromClaude2Codex.md).

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

For the v1.48.17 release and later, verify Grepper's BOM-first UTF-8/16/32 plus cp1252/Latin-1 search, the guarded five-class Exec Report vocabulary, Kuberneter's `returncode`/`success`/semantic-status shape, `Uninstaller.exe` preservation, source-derived public/private build tests, the standardized dialog dismissal (Escape closes every dialog with the meaning of its ✕, an outside click never does, and only a sealed downloading updater refuses), the themed `tlmAlert`/`tlmConfirm` popups replacing native browser pop-ups, and the post-build proof that the fail-open `agent.*` modules really landed in the frozen archive. Carry forward the v1.48.14 private External-MCP runtime, ten supervisor tools, inactive Memory/Sequential-Thinking defaults, tombstones, persistent Memory path, public/private catalog separation, nested-diagram restoration, and design-only transactional-updater label, plus the v1.48.13 placement/dialog/logging foundations.

For the v1.50.0 release and later, verify NetSpeed-Calculator's full source/wiring and metered-bandwidth contract; WAL-safe Backup DB, Set DB, and pre-Django hot-swap through `sqlite_copy.py`; Googler's structured dork compiler, presets/aliases, syntax normalization, grouped site/filetype alternatives, lawful-source boundary, `links_only` downstream workflow, four plain-HTTP server-rendered routes before browser launch, visible installed-Chrome default, bundled-browser fallback, seven browser routes, explicit-engine Tier-0 bypass, bounded retry/answer-attribution contract, Google-only advanced-operator caveat, live harness, and `test_googler_dorks.py`; the `adding-external-mcp` classify/import/doctor/activate/wait/list/call lifecycle; migration 0194's Deep Internet Research starter and migrations 0195-0197; the Ollama Pro-or-higher complete-operation requirement; private contact synchronization with public/snapshot PII exclusion; and the live 85 agents / 66 wrapped / 108 built-ins / 29 skills / 214 migrations counts. ⚠️ Those five numbers move with almost every release, so treat the figures written here as a stale-detector, not as truth: RE-DERIVE each one from source before publishing (count `agent/agents/*/<name>.py` dirs, `tool_name="chat_agent_*"` in `chat_agent_registry.py`, 20 core + wrapped + 12 ACPX/Skill + 10 External-MCP supervisors, `agent/skills_pkg/*/SKILL.md`, and `agent/migrations/0*.py`) and update this line in the same pass when they disagree. Verify the annotated `v1.50.0` tag and report its commit separately from a later `HEAD` when the worktree is ahead; never relabel a real release as an untagged target.

## Inventory Rules

Public dossier appendices list the application files and summarize the database
migration directory by count. Keep migration code intact for upgrade compatibility;
do not republish its historical product descriptions in the public documentation.
Verify exact path parity within that declared application scope.

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

## Prompt Flow graphical editing and layout gate (2026-10-04)

Keep eight executable operations (including Terminater) separate from static User Commentary. Explain the floating mixed-style text toolbar, direct border/corner resizing, full-text containment without internal scrollbars, and absence of a commentary configuration dialog. Document version 2 rich runs plus literal text, plain-note normalization and version 1 User Input migration. Give Run output its own readable section: 5–95% of usable pane height, independent scrolling at unchanged content scale, keyboard controls and separate per-user layout storage. Date the 23-check commentary/file-fidelity evidence and 14-check divider evidence; do not present historical browser tests as rerun during a document refresh. Use v1.90.0 as the current released version; document tag ebc5c3b4 and source baseline d274f89c separately from installed-package acceptance. Include canvas editing, native saving, Interactor and the account-wizard intent guards. Keep test evidence attributed to its actual run and do not build an executable merely to regenerate these documents.

## Usage documentation gate (2026-10-10)

Carry `docs/usage-dashboard.md` into the user, architecture and release sections.
Distinguish authoritative `/api/balance` credits/refill from rolling `/api/usage`
and per-user measured main-chat/model activity. Describe response-driven monthly,
legacy and purchased-only layouts without guessed quotas or unlimited-cloud claims.
State the website-only per-model API gap, UTC scopes, at-most-two-decimal displays,
under-60% dialog size and normal fonts. Keep account observations/screenshots out
of public artifacts. Date the 220 source tests and 24 visible browser checks to
October 10; label other-plan fixtures synthetic.
Derive current counts. The page-wide file-drop router, the docked avatar that follows both composer dividers and the not-fatal wrongly worded request (`91ff8453`) ship in v1.83.0 (tag at `a2914019`); the setup windows and the Markdown canvas shipped in v1.82.0 (tag at `880a335e`), the GUI standardization in v1.80.0 and Video-Analyzer's web links in v1.79.0 (both tags without a published release); Usage, the message-box resize and the Image-Interpreter list ship in v1.78.0 (its tag sits one commit before the Usage commit; the published zip matches `113eddc4`).

## v1.87.0 — Leaner catalog, safer removal, smaller release (carried)

**v1.87.0** (tagged 2026-10-18; it also carries
v1.86.0, tagged 2026-10-17) came before v1.88.0. Its catalog was **85 workflow agents, 66 wrapped
chat agents and 108 built-in tools**: Gatewayer, Gateway-Relayer, Node-Manager
and Zavuerer were removed, and migration **0214** deletes their rows and the
Zavuerer prompts without renumbering. Removal moves application entries into a
same-drive recovery folder (schema 2 journal, **Retry cleanup**,
`.tlamatini-removal.json`) instead of copying the payload. `build.py` keeps the
carried-Python-only media and browser packages out of the frozen interpreter
(`test_release_payload_ownership.py`). About ▸ Usage waits for real data and
sends a bodyless `POST /api/me`. `npm run lint:python` runs
`scripts/check_python_quality.py`. From v1.86.0: Mover creates a missing
destination name as a folder (`_names_a_file()`), and `scripts/architecture_atlas/`
rebuilds `Tlamatini-Architecture.pdf` with LaTeXer. The static suffix for that release was
`-agent-catalog-1-quality-cleanup-1-usage-status-2`.

See [the v1.87.0 release record](../../../docs/changes/2026-10-18-v1.87.0.md).

## v1.85.0 — Refresh, Views and centered avatar (carried)

**v1.85.0** (2026-10-16) added Refresh, Views and the centered avatar. `agent_page_canvas.js` owns Refresh
source access, complete-text comparison, cancellation and status. Retain browser
file handles during the drop event; snapshot-only access cannot refresh a path.
PDF replacement stages a ready viewer and keeps its iframe attached at commit.

`agent_page_layout.js` exposes `TlamatiniViews.setCanvasVisible`,
`isCanvasVisible` and `resetLayout`. Hiding toggles `tlm-canvas-hidden`, preserves
the canvas DOM and context, cancels divider gestures and moves focus only when
its current region disappears. The account/browser preference is
`tlamatini.chat.views.v1.<user id>`. `avatar_size.js::setDockedOnly` enforces the
hidden-canvas docking rule in pointer, keyboard and public API paths. Reset shows
both panes, resets their sizes and docks the portrait without clearing content.

The docked frame uses `--tlm-avatar-docked-right` measured from the full Mic/Send
row. Its square size and 120 px minimum stay independent of floating geometry.
v1.85.0's static suffix was `-avatar-center-1`; Views scripts retain `_views1`.
`build_runtime_assets.py` and `copy_source_assets.py` require the Views template,
scripts and snapshot harnesses. No migration or dependency was added.

See [the release implementation and evidence matrix](../../../docs/changes/2026-10-16-v1.85.0.md),
[Refresh](../../../docs/canvas-refresh.md) and [carriage](../../../docs/self-management-carriage.md).
