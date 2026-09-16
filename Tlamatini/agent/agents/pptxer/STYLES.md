# PPTXer presentation styles

PPTXer provides 36 named treatments: the original 24 content treatments and 12 additional visual styles.

## Select a style

Set the existing `nuance` option to a style key. Display names also work, such as `Swiss Editorial` or `Midnight Luxe`.

```yaml
nuance: botanical
slide_size: "16:9"
generate_art: true
```

In chat: **Create a PPTXer presentation using the Blueprint style.**

Leave `nuance` empty to retain the existing automatic content classification. The new visual styles are explicit choices and do not change which treatment an ordinary business, technical, gaming, or safety document receives automatically.

## New styles

| Key | Style | Typography and composition |
|---|---|---|
| `swiss_editorial` | Swiss Editorial | White ground, red rules, neutral sans serif, uppercase headings, square cards |
| `warm_editorial` | Warm Editorial | Warm paper, brown accents, editorial serifs, fine rules, generous margins |
| `midnight_luxe` | Midnight Luxe | Midnight blue, gold highlights, didone headings, fine rules |
| `botanical` | Botanical | Sage ground, leaf green, organic serif type, rounded cards |
| `oceanic` | Oceanic | Deep ocean blue, aqua, technical sans serif, subtle waves |
| `blueprint` | Blueprint | Drafting blue, monospaced headings, square cards, restrained grid details |
| `terracotta` | Terracotta | Sand ground, clay accents, sculptural serif headings, warm panels |
| `nordic_frost` | Nordic Frost | Cool white, slate blue, quiet sans serif, open spacing |
| `bauhaus` | Bauhaus | Cream ground, heavy black type, red and blue accents, thick rules |
| `lavender_studio` | Lavender Studio | Pale lavender, plum accents, friendly rounded type, soft cards |
| `monochrome_ink` | Monochrome Ink | Black and white, heavy grotesque headings, square panels, strong rules |
| `sunset_coral` | Sunset Coral | Aubergine ground, apricot highlights, geometric sans serif, rounded panels |

Fonts resolve to installed candidates and are measured before writing the slides. There are 17 font pairings, including the dedicated `swiss` and `blueprint` pairings; other styles reuse the existing font families with their own palette, shape, spacing, and background defaults.

## Customization

Existing options still take priority: `predominant_color`, `background_color`, `background_mode`, `font_pairing`, `density`, and individual color overrides. A new predominant color replaces the preset palette family. Changing the background mode chooses a compatible derived ground. Text colors are validated after overrides.

Set `generate_art: false` for flat backgrounds or lower `decorations` to reduce ornament. Long content uses the same measurement and pagination rules as the original styles. Dense cards may continue onto additional slides while preserving their complete text.

## Complete text and layout

The 256-character cases are a stress-test length, not an input limit. Text fitting accounts for the installed font, bold/italic face, tracking, line spacing, and text-frame insets. Widths are sampled at 1152 dpi (1/16 point) to reduce rounding errors in long lines, including Courier New. Font discovery keeps width variants separate: Arial Narrow and Bodoni MT Poster Compressed must not silently replace their regular families.

The builder measures a trial layout before placing dense cards, columns, bullets, timelines, and tables. Content can continue onto additional slides instead of being clipped to the first card. Long identifiers, indentation, combining marks, and Unicode fallback are covered by regressions. Diagram/chart keys preserve full labels when they cannot fit next to a node or series. Quote attribution and footers have reserved space; portrait statistic values retain their single-line layout. Configured corner radii and chart series colors are applied to the saved deck.

Palette correction runs after overrides, and the visual audit samples text contrast against the rendered background, including decorative gradients. A failed build preserves an existing output file through an atomic save. Native PowerPoint rendering runs in a bounded worker; cleanup can terminate only a process attributable to that worker and never a pre-existing Office process.

## Read the result

`INI_SECTION_PPTXER` exposes `status`, `success`, `output_path`, `nuance`, `font_display`, `font_body`, `render_tier`, `slides_rendered`, `ground_truth`, `layout_clean`, `overlaps`, and `text_overflows`, alongside media and slide counts.

- `created` means a deck was written. Check the audit fields and report before claiming visual verification; `layout_audit: false` leaves the layout verdict unavailable.
- `created_with_findings` means the file exists but the audit found defects or measurement errors. Route it to review.
- `layout_clean` describes the checks that ran. Read the report's `confidence`, skipped levels, and measurement errors to understand its scope.
- `ground_truth` identifies PowerPoint rendering evidence. LibreOffice and the geometric preview are reported separately; the preview is approximate. Native measurement errors and an incomplete rendered slide set prevent a clean native verification claim.

Style selection uses `nuance`; supported actions remain `create`, `outline`, `render`, `audit`, `info`, `fonts`, and `validate`. Use this guide as the style catalogue.

## Visual verification

From the repository root:

```powershell
.\python\python.exe Tlamatini/manage.py test agent.test_pptxer_agent agent.test_pptxer_visibility agent.test_pptxer_styles --noinput
.\python\python.exe scripts/verify_pptxer_styles.py --render --sizes 16:9
```

The second command regenerates the twelve-style 16:9 corpus with decorative backgrounds. Omit `--sizes 16:9` to generate all three formats (16:9, 4:3, and portrait via `vertical`). This broader native matrix was not part of the recorded new-style run below. The verifier checks complete 256-character content, saved geometry, native PowerPoint text bounds, and sampled rendered contrast. It writes an offline gallery, editable decks, PNGs, and JSON reports under `artifacts/pptxer-styles`.

To regenerate the extended corporate/cyberpunk visibility corpus in all three formats:

```powershell
.\python\python.exe scripts/verify_pptxer_layout.py --label verified --extended --render
```

The saved-geometry audit uses a 0.75-point tolerance per edge; native glyph bounds use 1 point. The corpus text-presence checks normalize whitespace and case to allow wrapping and styled capitalization. Separate regression tests cover exact identifier and indentation preservation.

Results depend on the installed fonts and PowerPoint version. Native frame measurements cover text boxes, diagram labels, and table cells; chart-internal labels require visual review.

### Recorded validation (2026-09-15)

These are the completed implementation runs at their respective revisions, not a fresh test result from the documentation update. Native verification used Microsoft PowerPoint 16.0.20326.20144.

- 126 regression tests passed, including the native PowerPoint regression.
- Long-card tests covered all twelve new styles in 16:9, 4:3, and portrait (36 style/format cases).
- The twelve new style decks were rendered in 16:9 with decorative backgrounds: 151 slides, 700 native text frames, and 252 complete 256-character payload checks, with zero audit findings.
- The earlier visibility audit covered corporate and cyberpunk treatments in all three formats: 424 slides and 870 complete long-text checks, with zero findings at that revision.

## Generated output and cleanup

Generated decks, images, galleries, and reports under `artifacts/pptxer-styles/` and `artifacts/pptxer-visibility/` are disposable and ignored by Git. The earlier generated corpus and scratch images were removed from the working tree after verification; the old local preview servers were stopped. Run the commands above to recreate the evidence. No live gallery is required to use PPTXer or run the regression suite.

Keep the implementation, this guide, `test_pptxer_agent.py`, `test_pptxer_visibility.py`, `test_pptxer_styles.py`, and the reusable scripts `verify_pptxer_layout.py`, `verify_pptxer_styles.py`, and `pptxer_visibility_gallery.py`. Clean only the known generated output directories when they are no longer needed; unrelated user decks and runtime data are outside that cleanup scope.
