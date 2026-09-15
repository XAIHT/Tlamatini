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

Fonts resolve to installed candidates and are measured before writing the slides. Swiss and Blueprint add dedicated font pairings; other styles reuse the existing font families with their own palette, shape, spacing, and background defaults.

## Customization

Existing options still take priority: `predominant_color`, `background_color`, `background_mode`, `font_pairing`, `density`, and individual color overrides. A new predominant color replaces the preset palette family. Changing the background mode chooses a compatible derived ground. Text colors are validated after overrides.

Set `generate_art: false` for flat backgrounds or lower `decorations` to reduce ornament. Long content uses the same measurement and pagination rules as the original styles. Dense cards may continue onto additional slides while preserving their complete text.

## Visual verification

From the repository root:

```powershell
.\python\python.exe Tlamatini/manage.py test agent.test_pptxer_agent agent.test_pptxer_visibility agent.test_pptxer_styles --noinput
.\python\python.exe scripts/verify_pptxer_styles.py --render
```

The second command generates every new style in 16:9, 4:3, and portrait, with decorative backgrounds enabled. It checks complete 256-character content, saved geometry, native PowerPoint text bounds, and sampled rendered contrast. Evidence is saved under `artifacts/pptxer-styles`, including an offline gallery, editable decks, PNGs, and JSON reports.

Results depend on the installed fonts and PowerPoint version. Native frame measurements cover text boxes, diagram labels, and table cells; chart-internal labels require visual review.

### Recorded validation (2026-09-15)

- 126 regression tests passed, including the native PowerPoint regression.
- Long-card tests covered all twelve new styles in 16:9, 4:3, and portrait (36 style/format cases).
- The twelve new style decks were rendered in 16:9 with decorative backgrounds: 151 slides, 700 native text frames, and 252 complete 256-character payload checks, with zero audit findings.
- The earlier visibility audit covered corporate and cyberpunk treatments in all three formats: 424 slides and 870 complete long-text checks, with zero findings at that revision.

Generated decks, images, galleries, and reports are disposable and ignored by Git. Run the verification scripts above to regenerate them; they are not required to use PPTXer or run the regression suite.
