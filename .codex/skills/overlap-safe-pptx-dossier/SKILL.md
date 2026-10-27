---
name: overlap-safe-pptx-dossier
description: Use when asked to create or update a complete technical PPTX deck, especially a Tlamatini-style presentation, where slides must describe the whole system, architecture, usage, line inventory, complete file tree, and must never contain overlapping text, images, cards, tables, or diagrams.
---
<!--
═══════════════════════════════════════════════════════════════════
  ✦  T L A M A T I N I  ✦   —   "one who knows"
  Created by  Angela López Mendoza   ·   @angelahack1
  Developer · Architect · Creator of Tlamatini
  Tlamatini Author Banner — do not remove (Angela's name is kept in every build)
═══════════════════════════════════════════════════════════════════
-->

# Overlap-Safe PPTX Dossier

> Current release: **[v1.91.1](../../../docs/changes/2026-10-27-v1.91.1.md)**. Dated records below retain their original evidence dates.


> **HEADLESS IS FORBIDDEN. VISIBLE FOREGROUND EXECUTION ONLY.** Every command, automated test, diagnostic, script, build, agent and browser must run in a visible foreground window on Angela's real desktop. Use forked CMD/PowerShell windows, `execute_forked_window: true`, and `headless: false`. Monitor live; if visibility cannot be confirmed, do not run. Read the [mandatory execution policy](../../../TestsVisiblesAndVisibleExecutionFromClaude2Codex.md).

Use this skill when a deck must be complete, polished, and layout-safe.

## Non-Negotiable Layout Rules

- Never cram dense content onto one slide. Split into more slides.
- Track every intentional content rectangle: title, subtitle, panels, cards, diagrams, tables, images, and tree text.
- Validate that every tracked rectangle stays within slide bounds.
- Validate that tracked rectangles do not overlap unless the overlap is deliberate containment, such as text inside its own card.
- Use `TextFrame.fit_text()` or conservative font sizes, but do not rely on auto-fit to rescue overloaded slides.
- For file-tree appendix slides, chunk the tree into small fixed-size line groups; keep one monospaced text box per slide.
- For tables, prefer monospaced text or pre-sized rows over huge PowerPoint tables.

## Visual Style Guidance

When the user supplies a reference presentation:

- Inspect the deck with `python-pptx`; if slides are image-only, extract media from `ppt/media/` and use the images as style references or cover backgrounds.
- Match the visual language rather than copying old content blindly.
- For the Tlamatini reference style, prefer obsidian/dark stone backgrounds, copper and jade accents, thin ornamental lines, translucent cards, geometric diagrams, and light display typography.
- Use icons as simple labeled glyphs, line shapes, or small cards when assets are not available.
- Keep contrast high enough for extracted text and projected viewing.

## Required Deck Content

The deck must include:

- What the system is and what it does.
- How the system works end to end.
- How to use it from source, in chat, in Multi-Turn mode, and in the workflow designer.
- Packaging/build path.
- Agent catalog overview.
- Repository facts and current HEAD.
- Effective line counts by language, total effective lines, and methodology.
- Largest files by effective lines.
- Complete tracked file tree, split across appendix slides.
- Latest changes or optimizations as a section, not as the whole deck.

## Preferred Tlamatini Workflow

In the Tlamatini repo, run:

```powershell
python Tlamatini\agent\doc_generation\refresh_project_docs.py
```

The generator builds the full PPTX and performs an internal geometry audit while building slides. If it fails, fix layout by adding slides, shortening bullet groups, or reducing line chunks. Do not ignore audit failures.

## Mandatory Three-Pass Consistency Sweep

1. **Discover:** compare the previous deck commit with local HEAD/version tag; inventory tracked files, agents, tools, skills, languages, JavaScript/CSS assets, README, BookOfTlamatini, prompts, and recent implementation commits.
2. **Reconcile:** map each current release behavior to source plus documentation and update active counts from source. Preserve dated historical material, but never let it drive the cover, facts, architecture, usage, or current-release slides.
3. **Prove:** repeat stale-version/count searches, lint/test, regenerate, extract slide text, prove complete-tree parity, run geometry checks, and render every slide for visual inspection.

For the v1.48.17 release and later, include Grepper's multi-encoding search, the guarded five-class Exec Report vocabulary, Kuberneter's canonical result fields, `Uninstaller.exe` preservation, source-derived public/private build checks, the standardized Escape-closes-every-dialog policy with its sealed-updater exception, the themed `tlmAlert`/`tlmConfirm` popups, and the frozen-bundle carriage proof. Retain the v1.48.14 private External-MCP runtime flow, ten supervisors, inactive defaults, catalog tombstones, persistent Memory state, secret-separated builds, nested-diagram repair, and explicit "proposal, not shipped behavior" updater label, plus the v1.48.13 placement/dialog/logging foundations.

For the v1.50.0 release and later, include separate, readable slides for NetSpeed-Calculator and its metered-bandwidth warning; WAL-safe SQLite backup/set/hot-swap; Googler's structured dork compiler, syntax/preset contract, `links_only` file workflow, and responsible-use boundary; a separate Googler resilience slide covering four plain-HTTP server-rendered routes before browser launch, visible installed Chrome, bundled-browser fallback, seven browser routes, explicit-engine Tier-0 bypass, bounded retries, answer attribution, and Google-only advanced operators; the External MCP Adder lifecycle; Deep Internet Research prompt; Ollama Pro-or-higher setup; private contact synchronization/public PII exclusion; and the source-derived 86/67/110/29/220 counts. Show the annotated `v1.50.0` tag commit separately from a later `HEAD` when needed. Split these topics rather than shrinking type or allowing dense panels to overlap.

## Validation Checklist

Public file-tree slides summarize the database migration directory by count.
Verify exact application-path parity while retaining the migration files in the
source inventory and upgrade chain.

- If Python source code was generated or modified, run `python -m ruff check` from the project root and fix all reported issues.
- Open the PPTX with `python-pptx` and confirm slide count.
- Extract text from the first content slides and at least one tree appendix slide.
- Confirm the line-inventory slide contains the total effective line count.
- Confirm the tree appendix count covers the complete tracked file tree.
- Confirm no audit exceptions were raised during generation.
- When Microsoft PowerPoint is available, render every slide through native PowerPoint and inspect text bounds, out-of-bounds shapes, and unintended text-to-text intersections.

## Prompt Flow graphical editing and layout gate (2026-10-04)

Keep eight executable operations (including Terminater) separate from static User Commentary. Explain the floating mixed-style text toolbar, direct border/corner resizing, full-text containment without internal scrollbars, and absence of a commentary configuration dialog. Document version 2 rich runs plus literal text, plain-note normalization and version 1 User Input migration. Give Run output its own readable section: 5–95% of usable pane height, independent scrolling at unchanged content scale, keyboard controls and separate per-user layout storage. Date the 23-check commentary/file-fidelity evidence and 14-check divider evidence; do not present historical browser tests as rerun during a document refresh. Use v1.91.1 as the current version; its tag and inspected source are 9915938a (v1.91.0 was a771d27c). Keep source, GitHub publication and installed-package acceptance separate. Include the Live Editor & Terminater settings, migration 0220, shared narration receipts and the dated October 23 evidence. Include canvas editing, native saving, Interactor and the account-wizard intent guards. Keep test evidence attributed to its actual run and do not build an executable merely to regenerate these documents.

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
