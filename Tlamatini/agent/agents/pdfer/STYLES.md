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

The agent reports `style` and `style_family` in its output, alongside `nuance`,
`palette`, `layout_clean` and `repairs`. Existing field names remain available
to saved flows and Parametrizer.

## Reproduce validation and previews

From the repository root:

```powershell
python scripts/verify_pdfer_styles.py
```

This renders every style, creates a browser gallery with both cover and body
previews, writes a combined style atlas to `output/pdf/pdfer-style-atlas.pdf`,
and saves measured layout/contrast results to `artifacts/pdfer-styles/report.json`.
The script exits unsuccessfully if any rendered document fails its audit.

Regression tests in `agent.test_pdfer_styles` exercise all styles on A4
portrait and A5 landscape with 256-character titles, unbroken table tokens,
long footer notes, palette overrides, semantic safety, repeatable artwork and
cross-process randomness. Existing PDFer tests cover the surrounding agent
contract and legacy rendering paths.
