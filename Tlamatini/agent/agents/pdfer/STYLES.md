# PDFer: the signature collection

PDFer now offers **24 selectable visual identities alongside its 20 existing
document themes**. A style specifies a complete palette, type pairing, spacing
rhythm and original vector artwork. No font download, image service or extra
dependency is required.

## Choose a look

Set `style` in PDFer's configuration or a Chat-Agent-PDFer request. Use
`mode: styles` for a read-only catalogue with names and aliases.

| Family | Style IDs | Character |
|---|---|---|
| Playful | `kawaii_cloud`, `baby_dream`, `baby_peach` | Clouds, soft rainbows, nursery moons; raspberry, blue and peach |
| Playful | `candy_pop`, `storybook_garden`, `pastel_sorbet` | Confetti, botanical forms, pastel ribbons; friendly or literary typography |
| Cyberpunk | `cyberpunk`, `neon_noir`, `holographic`, `synthwave` | Neon skylines, geometric prisms, retro horizons; cyan, magenta and violet |
| Cosmic | `cosmic_nebula`, `astral_atlas`, `lunar_minimal`, `solar_flare`, `aurora` | Nebula ribbons, orbital instruments, eclipses and auroras |
| Electronics | `circuit_board`, `blueprint`, `quantum_chip`, `oscilloscope` | Traces, pads, dimension marks, chip geometry and signal waves |
| Tlamatini | `aztec_obsidian`, `quetzal_jade`, `tlamatini_celestial`, `xeno_codex`, `alien_biolume` | Stepped temples, feather-like geometry, celestial rings, alien portals and luminous flora |

Aliases include `cute`, `baby`, `bébé`, `space`, `astronomy`, `electronics`,
`PCB`, `aztec`, `tlamatini`, and `alien`. Matching ignores case, accents,
spaces and hyphens. Unknown names retain the document theme and produce an
explicit diagnostic. The Aztec-inspired imagery is original abstract artwork,
not a reproduction or translation of historical glyphs.

## Configuration at a glance

| Control | Default | Meaning |
|---|---|---|
| `style` | `auto` | A visual ID or exact normalized alias; automatic semantic design when empty/auto |
| `nuance` | empty | Detect document purpose, or choose one of the existing 20 semantic treatments |
| `predominant_color` | empty | Recolor the complete palette while keeping the selected motif and type pairing |
| `background_mode` | `auto` | Keep the design's ground or request `dark`/`light` |
| Per-role color controls | empty | Override the style/seed before final contrast repair |
| `font_pairing`, `font_size`, `scale_ratio` | empty, 0, 0 | Use the design defaults unless explicitly set |
| `justify` | null | Use the resolved design's alignment unless explicitly set |
| `decorations` | `auto` | Keep or lower the semantic decoration ceiling |
| `cover` | true | Use a cover when a title is available; rich decoration may add vector art |
| `engine` | `auto` | Atelier by default; custom `css` selects legacy xhtml2pdf |
| `layout_audit` | true | Reopen the atelier output and measure layout/contrast |
| `ollama_polish`, `ollama_design` | false | Optional content/design consultation with fallback on failure |

The per-role controls are `accent_color`, `text_color`, `background_color`,
`heading_color`, `link_color`, `table_header_color` and `rule_color`. Palette
validation runs last, so an unreadable requested color may be repaired.

All modes remain available: `auto`, `markdown`, `html`, `text`, `images`,
`mixed`, `merge`, `info`, `validate`, plus `styles`. Discovery needs no
document content:

```yaml
mode: styles
```

This returns IDs, display names, families and aliases in the response body,
with `status: inspected`, empty output paths and zero pages. It does not create
an atlas or sample PDF.

## Examples

```yaml
mode: markdown
title: "Tlamatini: beyond the horizon"
subtitle: "A celestial journey through ideas and invention"
input_text: |
  ## Welcome to the future
  Discover a new universe of beautiful ideas and creative possibilities.
  Share your imagination, explore our collection, and start your journey!
nuance: marketing
style: tlamatini_celestial
cover: true
```

In chat: “Make a cute PDF brochure using `style=kawaii_cloud`”, or
“Export this electronics guide with `style=circuit_board`”.

Use `style: baby_dream` for a soft nursery look, `style: cosmic_nebula` for a
deep-space palette, or `style: cyberpunk` for neon city artwork.

## Style and content are separate

- `nuance` describes the document: paper, manual, marketing, science, legal,
  and so on. Leave it empty for content detection.
- `style` selects the visual identity. `auto` preserves the existing automatic
  theme. It does not reclassify a contract as a brochure.
- The content's existing decoration ceiling still applies. Rich content
  permits cover art; restrained content uses the same colors and typography
  with quieter decoration. Legal, clinical and financial documents retain
  their no-ornament behavior. `decorations` can lower that ceiling.
- `predominant_color` recolors the palette while keeping the motif and type.
  Per-role colors, font settings and page settings take precedence.
- Styles apply to the **atelier** renderer (Markdown, text, HTML or mixed
  documents). The legacy CSS renderer, image-only composition, and merged
  source PDFs retain their respective layouts.

### Alias compatibility and overrides

Prefer `style` for appearance and `nuance` for purpose. For compatibility,
a visual-only name in `nuance` can select a style when `style` is empty/auto,
but an existing semantic alias always wins. For example:

| Setting | Result |
|---|---|
| `style: astronomy` | Visual identity `astral_atlas`; semantic detection still runs |
| `nuance: astronomy` | Existing semantic treatment `scientific_dark` |
| `nuance: legal`, `style: cyberpunk` | Legal semantic treatment with the chosen palette/type and no ornament |
| Unknown explicit `style` | Semantic theme retained; diagnostic explains the fallback |

Matching normalizes a supplied name; it does not infer a signature style from
words in the document. A specific role color overrides the seed palette, and
an explicit font/page setting overrides the design default. Host fonts are
resolved locally, with fallback faces when absent, so typography can vary
between machines.

## Layout improvements

Cover text is measured before placement and given an opaque reading area;
artwork never supplies the background behind a title. Display text can scale
down to a readable floor, and longer content flows onto additional pages
instead of being cut off. Cover subtitles use opaque contrast-checked ink.

Footer notes reserve the measured width of the page number, shortening only
the repeated note with an ellipsis when needed. Document content is retained.
Small heading, quote, caption, footer and alternating table roles are checked
at the normal-text contrast floor. Vector art remains sharp when zoomed or
printed. Legacy raster artwork now uses stable hashes across processes and
its cache includes every palette role and raster resolution.

Table measurements include a 0.75-point allowance after cell padding, avoiding
ordinary-word splits caused by differences in floating-point rounding. Sparse
Franklin Gothic and Segoe UI family mappings select the proper upright bold
face. Smaller page sizes retain a usable content frame.

## Read the result

The `INI_SECTION_PDFER` output preserves all previous fields and adds
`style` and `style_family`. The complete header is `mode`, `source_type`, `output_path`, `output_dir`, `filename`, `page_count`, `bytes`, `images_used`, `engine`, `nuance`, `nuance_confidence`, `nuance_source`, `style`, `style_family`, `palette`, `predominant_color`, `background_mode`, `font_pairing`, `decorations`, `overlaps`, `layout_clean`, `repairs`, `status`;
the body is available as `response_body`.

| Field | Interpretation |
|---|---|
| `style` | Resolved signature ID, or `auto` on the semantic atelier path |
| `style_family` | playful, cyberpunk, cosmic, electronics, tlamatini, or semantic |
| `nuance`, `nuance_confidence`, `nuance_source` | Semantic classification and its basis |
| `palette`, `predominant_color`, `background_mode`, `font_pairing` | Resolved design metadata |
| `decorations` | Effective decoration budget after semantic limits |
| `layout_clean` | `true`/`false` when an atelier audit ran; empty is not a pass |
| `overlaps` | Count reported by the audit; alone it does not cover other findings |
| `repairs` | Layout repairs applied, if any; not proof that every issue is resolved |
| `status`, `output_path`, `page_count` | Operation result and document location/size |
| `response_body` | Design explanation, fallback diagnostics, audit details, or catalog |

Catalog, legacy and non-atelier operations may leave design/audit fields empty.
`status: created` establishes that a PDF was created; it does not establish a
clean audit. Check the actual `layout_clean` value and the detailed findings,
including overlaps, off-sheet ink, blank pages and contrast. Disabled or absent
audits provide no measured layout verdict.

In a flow, Parametrizer can map `{style}` and `{predominant_color}` into
another PDFer. Forker can route an unclean audit to review. Existing output
keys, downstream triggering, Exec Report and Ask-Execs integration remain.

## Source map

| Files | Responsibility |
|---|---|
| [pdfer_styles.py](pdfer_styles.py) | 24 identities, exact aliases and palette/type defaults |
| [pdfer_artwork.py](pdfer_artwork.py) | Original deterministic vector cover artwork |
| [pdfer_nuance.py](pdfer_nuance.py), [pdfer_theme.py](pdfer_theme.py) | Semantic classification, style resolution, overrides and decoration limits |
| [pdfer_color.py](pdfer_color.py), [pdfer_typography.py](pdfer_typography.py) | Contrast validation, color derivation and local font resolution |
| [pdfer_docmodel.py](pdfer_docmodel.py), [pdfer_tables.py](pdfer_tables.py), [pdfer_atelier.py](pdfer_atelier.py) | Content model, measured table widths and page composition |
| [pdfer_ornament.py](pdfer_ornament.py) | Existing generated raster motifs and deterministic cache |
| [pdfer_audit.py](pdfer_audit.py), [pdfer_consult.py](pdfer_consult.py) | Finished-file audit and optional design consultation |
| [pdfer.py](pdfer.py), [config.yaml](config.yaml) | Agent modes, configuration, rendering and structured results |

The twelve helpers are flat siblings copied with the pool template. The style
extension adds no runtime libraries, external image services or font downloads.

## Reproduce validation and previews

Use the repository's Python environment with its installed dependencies. From
the repository root, the optional preview verifier is:

```powershell
python scripts/verify_pdfer_styles.py
```

The [generator](../../../../scripts/verify_pdfer_styles.py) needs the existing
ReportLab, PyMuPDF and Pillow environment, plus Poppler's `pdftoppm` on PATH to
render independent PNG previews. Poppler is not needed by the runtime style
renderer.

It creates the following **regenerable, ignored outputs**:

- `artifacts/pdfer-styles/<style>/sample.pdf` and page PNGs.
- `artifacts/pdfer-styles/index.html`, contact sheets and `report.json`.
- `output/pdf/pdfer-style-atlas.pdf`, the combined bookmarked atlas.

The script exits unsuccessfully if any rendered sample fails its audit.
These outputs were removed after the development review; they are not shipped
runtime assets. Keep the generator, source, tests and this guide in development.
Only regenerate previews when needed, and leave generated PDFs, PNGs, reports
and task logs out of source changes.

Run the three PDFer suites from the Django project directory:

```powershell
Push-Location Tlamatini
python manage.py test agent.test_pdfer_agent agent.test_pdfer_nuance_layout agent.test_pdfer_styles --noinput
Pop-Location
```

Regression tests in `agent.test_pdfer_styles` exercise all styles on A4
portrait and A5 landscape with 256-character titles, unbroken table tokens,
long footer notes, palette overrides, semantic safety, repeatable artwork and
cross-process randomness. Existing PDFer tests cover the surrounding agent
contract and legacy rendering paths. They also cover complete title/subtitle
continuation beyond 2,000 characters and preservation of ordinary table words.

### Recorded evidence — 2026-09-15

During implementation, the three suites passed **130 tests**. All **24
two-page style samples (48 pages)** passed their layout audits, with zero
overlaps, bleeds, blank pages or contrast findings. Cover/body contact sheets
and representative full pages were visually inspected.

Those results describe the tested fixtures and environment. They do not
guarantee every possible input or establish that a separate frozen installation
contains this source update. PDFer reports per-document audit evidence so each
new deliverable can be assessed on its own.

Related references: [agent catalog](../../../../agents_descriptions.md),
[FlowCreator's PDFer section](../flowcreator/agentic_skill.md#86-pdfer), and
[dated implementation notes](../../../../docs/claude/recent-fixes.md).
