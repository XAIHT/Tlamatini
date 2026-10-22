<!-- Tlamatini Author Banner — Created by Angela López Mendoza · @angelahack1 -->
# Documentation refresh - v1.90.0 (2026-10-22)

## Baseline and scope

Requested after Angela tagged, committed and pushed the implementation. The annotated
v1.90.0 tag resolves to ebc5c3b4; the inspected main/origin/main follow-up is d274f89c.
Documentation-only generators do not build or install an executable, migrate the
working database, change private configuration, or certify an installed package.

The review covers tracked Markdown, text, PDF and PPTX paths. Active guidance is
updated; dated implementation records retain their dates and original test scope.
Vendor license text, dependency requirements and test inputs retain their meaning.
The PDF renderer fixture is regenerated as a fixture, not mislabeled as a user guide.

## Content reconciliation

- README and Book explain editing by file type, native Save/Save As, dirty state,
  disk conflicts, encoding/BOM/line endings and the difference between context snapshots
  and the live unsaved editor.
- Interactor is a module/tool, not a workflow agent. Documentation covers activation,
  Temp creation without a path, exact reads, revision checks, incremental typing,
  learner-field handoff, local completion, interruptions and bounded visibility recovery.
- Self-knowledge and maintainer guides connect the prompt/tool/browser/hub/native-file
  contracts, Compact-mode gate, migration 0218 and offline/frozen carriage.
- The account wizard is documented separately: createsuperuser is administrative;
  password input is not command ownership and an email field is not notification consent.
- Current counts are derived from source: 86 workflow agents, 67 wrapped tools,
  110 built-ins (21 + 67 + 12 + 10), 218 migrations, 61 JS modules and 28 stylesheets
  in the counted js/css directories, plus the separate Interactor bridge/style files.
- The OOB/NAMU note is regenerated from current source. Historical line references
  and universal instantaneous/remote cleanup claims are replaced with actual boundaries.

## Regenerated artifacts

| Artifact | Purpose | Verification |
|---|---|---|
| tlamatini_app_summary.pdf | Complete system, usage, architecture, release, line counts and file tree | 151 pages; bounds and complete-tree checks passed |
| Tlamatini_eXtended_Artificial_Intelligence_Humanly_Tempered.pptx | Editable technical deck from the same content model | 185 slides; geometry and complete-tree checks passed |
| Tlamatini-Architecture.pdf | Tracked-file atlas, topology and live-editor architecture | 30 pages; all 1,585 application paths accounted for |
| OOB_shift_reaper-and-NAMU-Design.pdf | Current lifecycle review with local/remote limitations | 4 pages; page bounds passed |
| Tlamatini/agent/doc_generation/test_output.pdf | Small renderer fixture | 1 page; page bounds passed |

## Reproduction and evidence

Run development commands in a verified visible foreground console and keep it open.
Use Tlamatini/agent/doc_generation/refresh_project_docs.py for the PDF/deck,
scripts/architecture_atlas/build_architecture_pdf.py for the atlas, and
scripts/refresh_supporting_pdfs.py for the lifecycle note and fixture.
No application build is needed.

Local generated evidence is under build/documentation_refresh and
Temp/docs-refresh-2026-10-22. The dossier verifies complete tracked application-tree
parity (database-history files are summarized), glyph/page bounds and slide geometry.
Visual review uses numbered render sheets plus full-size images of dense or changed
pages. `scripts/review_documentation_visuals.py` regenerates every PDF image and the
review sheets. Render hashes track unchanged images through the final pass.

Corrections from review: chapter contents now fit above the PDF footer ornament;
the atlas no longer has an empty final index page; long agent names wrap at word
boundaries; Prompt Flow shows all eight executable operations and static commentary,
with the Terminater parallelogram. Unsigned chart axis IDs keep PPTX import valid.
Current release claims, source-tag identity, saving behavior and historical test
evidence were reconciled against the source.

Installed PowerPoint could not start (Office error `0x3-0x0`; COM server execution
failure). All 185 slides were rendered with bundled `@oai/artifact-tool` 2.8.99 and
checked alongside the original PPTX geometry. This is not native PowerPoint layout
certification. No global Office repair was attempted.

All 186 PDF pages and 185 slides were visually reviewed; all 27 changed final renders were reinspected.

Final result: documentation verification complete. Historical implementation tests were not rerun
or relabeled as documentation tests. No new frozen-package acceptance is claimed.
