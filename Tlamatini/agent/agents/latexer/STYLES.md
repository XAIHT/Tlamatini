# LaTeXer: the signature collection

30 explicit visual identities, independent of the eight document templates.
Original TikZ illustrations, coordinated reading pages, portable Latin Modern
fonts, mathematical typesetting, tables, code, links and flowing callouts.
No external artwork, font downloads, Python graphics dependencies or shell escape
are needed by the agent. The generated `.tex` is a standalone deliverable.
Standard LaTeX title/author declarations and PDF metadata are retained, so the
existing `structure` action can inspect styled documents normally.

## One-call styled PDF

```yaml
action: scaffold_compile
template: article
style: tlamatini_celestial
title: Knowledge beyond the stars
subtitle: Ancient geometry. Unbounded imagination.
author: Tlamatini
content: |
  Every discovery begins with a question.
  \subsection{A precise language}
  \[ E=mc^2 \]
  \begin{TLcallout}{Look a little further}
  Give the next idea room to grow.
  \end{TLcallout}
filename: celestial.pdf
```

For chat tool calls, use `content_b64` for multiline LaTeX; it wins over `content`.
`input_text_b64` is the equivalent for fragment compilation. Title, subtitle,
author, date and content are **LaTeX**, consistent with the original agent:
escape literal `&`, `%`, `_`, `#`, etc. This layer does not translate prose.

## Explore the collection

`action: list_styles` returns a JSON catalogue in `response_body`, including
stable IDs, labels, families, exact aliases, artwork motifs, font roles, supported
modes and engines. It does not probe or require a TeX installation.

| Collection | Style IDs | Original artwork |
|---|---|---|
| Editorial | `scholarly`, `swiss`, `atelier` | Folios, modernist geometry, architectural arches |
| Cute and nursery | `cute_candy`, `baby_blush`, `baby_sky`, `storybook`, `lullaby` | Candy, clouds, balloons, garden, moon mobile |
| Cyberpunk | `cyberpunk`, `neon_noir`, `holographic`, `synthwave` | City skyline, neon tunnel, prism, sunset grid |
| Astronomy | `cosmic_nebula`, `astral_atlas`, `lunar_minimal`, `solar_flare`, `aurora`, `deep_space` | Nebula, orbital atlas, eclipses, solar rays, aurora ribbons, constellation |
| Electronics | `circuit_board`, `blueprint`, `quantum_chip`, `oscilloscope` | PCB traces, measured schematic, chip, waveforms |
| Beyond-planet Tlamatini | `aztec_obsidian`, `quetzal_jade`, `tlamatini_celestial`, `xeno_codex`, `alien_biolume`, `solar_codex`, `obsidian_portal`, `quetzal_supernova` | Stepped temple, feather fan, celestial temple, invented glyphs, bioluminescent forms, solar geometry, octagonal portal, radiant feather geometry |

Tlamatini artwork is a contemporary geometric interpretation; it does not claim
to reproduce archaeological artifacts or historical writing.

IDs, labels and aliases ignore case, accents, spaces and punctuation. Examples:
`cute`, `baby`, `astronomical`, `electronics`, `electrónica`, `extraterrestrial`,
`tlamatini`, `extraterrestrial aztec`. Selection is exact: prose content never
activates a style. Unknown names produce a clear refusal with catalogue guidance.

## Design controls

| Parameter | Default | Effect |
|---|---|---|
| `style` | empty | Opt in to a named identity; empty/none/plain/default preserve legacy generation |
| `subtitle` | empty | Supporting LaTeX text below the title |
| `style_mode` | `screen` | Curated light/dark ground; `print` uses white paper and recalculates readable inks |
| `style_decoration` | `rich` | `restrained` scales the signature artwork down; `none` removes it |
| `style_cover` | `true` | Full document cover; false uses a compact title |
| `predominant_color` | empty | Optional six-digit hex primary seed, e.g. `#238D87` |

Text colors are adjusted after print mode and seed overrides to reach at least
4.5:1 against their assigned ground. This covers body, headings, links, secondary
text, table headers, shaded table cells and listing colors. It is a palette
invariant, not a claim of tagged-PDF accessibility or of contrast in arbitrary
user-provided images, colors or custom LaTeX.

Artwork is vector geometry inside its own clipped region in the page flow.
Covers and body text occupy separate pages. Regular TeX pagination handles body
text; artwork never sits behind it. Long titles flow naturally and use a smaller
display size. Arbitrarily large user content still needs the normal LaTeX layout
review; see overflow diagnostics.

## Structures, packages and compatibility

- Styles work with `create_file`, `create_from_template`, `scaffold_compile`, and
  `compile` with a fragment and `auto_preamble: true`.
- The eight scaffolds remain: article, report, book, beamer, letter, cv, homework,
  spanish-article. `create_file` supports article/report/book/letter/beamer.
- Report/book include a table of contents. CV and homework use compact headings.
  Letters use conventional opening/signature layout without cover art.
- Beamer uses its own colors, columns, frame titles and blocks; it does not load
  document-only heading/header packages. Supplied content is a **frame body**;
  complex presentations that define their own frames should use complete sources.
- `style_cover: false` keeps the Beamer title frame and omits its illustration.
- `class_options`, `geometry` and additional `packages` are honored. Geometry is
  controlled by Beamer for slides. Extra packages must be package names, not
  option-bearing commands. Class-specific conflicting packages remain the
  caller's responsibility.
- pdfLaTeX uses T1 Latin Modern; XeLaTeX/LuaLaTeX use the corresponding OpenType
  fonts through fontspec. Spanish scaffolds disable babel's active punctuation
  so it cannot alter TikZ paths.
- Common TeX packages include TikZ, xcolor/colortbl, booktabs, tabularx, listings,
  fancyhdr, titlesec and enumitem. MiKTeX's existing on-demand installer can fetch
  missing packages; other distributions must have them installed.
- Existing complete `.tex` sources/projects retain their own preamble. An explicit
  style on those routes is refused with instructions to use a scaffold/fragment or
  omit the style. Source files are never automatically restyled.
- The compiler, bibliography convergence, repair ladder and byte-exact channels
  are retained. Style choices do not enable shell escape or model calls.

## Body components

Ordinary LaTeX still works. These optional helpers use the current palette:

```latex
\begin{TLcallout}{A useful observation}
This flows across pages and keeps its title with the surrounding reading rhythm.
\end{TLcallout}

\begin{tabularx}{\linewidth}{lX}
\TLtablehead\TLcellhead{Element} & \TLcellhead{Purpose} \\
Signal & An idea made measurable. \\
\bottomrule
\end{tabularx}

\begin{lstlisting}[language=Python]
def discover(curiosity):
    return curiosity * 2
\end{lstlisting}
```

Wrap **every table header cell** with `\TLcellhead`; TeX cell grouping does not
carry the foreground color to later cells. Optional shaded rows use
`\rowcolor{TLSurface}` and `\textcolor{TLSurfaceInk}{cell text}` in each cell.
The text form also preserves the first baseline in paragraph (`X`/`p`) columns.
Palette names are
`TLBackground`, `TLInk`, `TLPrimary`, `TLSecondary`, `TLMuted`, `TLSurface`,
`TLSurfaceInk`, `TLSurfaceAccent`, `TLOnPrimary`, and `TLRule`.

## Result fields and flow routing

`INI_SECTION_LATEXER` exposes 21 contract fields including `response_body`:

```text
action, engine, distribution, tex_path, project_dir, output_path, output_dir,
filename, page_count, bytes, passes, bibliography, errors, warnings, success,
status, style, style_family, style_mode, style_count, response_body
```

`list_styles` reports `status: listed`, `success: true`, `style_count: 30`,
`distribution: not_probed`, and the JSON catalogue in `response_body`. It creates
no PDF. Applied styles report their canonical ID, family and mode. Inspect
`status`/`success` before forwarding `output_path`; `compiled_with_errors` and
degraded repairs are not clean builds. Design metadata does not establish layout
quality, and the normal agent result has no `layout_clean` field. The developer
verifier below performs the rendered bounds checks separately.

The root MCP connector exposes `latexer`; Multi-Turn uses `chat_agent_latexer`.
Both run the same native agent. [Connector examples](../../../../TLAMATINI_MCP.md#latexer-discover-and-apply-styles)
and [FlowCreator routing](../flowcreator/agentic_skill.md#87-latexer) explain those surfaces.

## Workflow integration and validation

The chat agent description, generated canvas-flow parameter mapping, Parametrizer
contract and tool-result promotion include the new settings/results. Successful
styled generation reports canonical `style`, `style_family`, `style_mode`;
catalogue responses also report `style_count`. All new modules stay inside the
agent template and travel with ordinary pool copies.

```powershell
python Tlamatini/agent/test_latexer_styles.py
python scripts/verify_latexer_styles.py --matrix
```

The verifier runs actual engines with repair disabled, checks source-text
preservation, page bounds and overfull boxes, then renders previews independently
with Poppler. The matrix includes all identities on all three engines, all print
variants, all eight templates, Spanish, long metadata, multi-page content,
compact titles, restrained decoration and a deliberately low-contrast seed.
It fails if an engine is missing or a build does not meet the checks.
Run these commands from the repository root. The matrix requires pdfLaTeX,
XeLaTeX and LuaLaTeX, plus the developer dependencies listed below. For iterative
development, `--reuse` re-audits previously successful PDFs only when emitted
source is unchanged; that is reuse of prior evidence, not a fresh compilation.
Omit it for a fresh matrix.

### Verified snapshot — 2026-09-15

- **483 automated tests passed** across the agent, suite, repair ladder, verbatim
  channel and style tests.
- **132 fresh real-engine builds passed**: 30 styles × three engines in screen
  mode (90), 30 pdfLaTeX print builds, eight template cases with Spanish content,
  and four stress cases covering long/multipage content, compact titles with a
  white seed, restrained artwork, and a Beamer body with math/table/code.
- No overfull boxes or out-of-bounds PDF text were measured in that matrix.
  All 60 atlas pages were rendered with Poppler and visually reviewed, alongside
  special layouts. This verifies the tested examples, not arbitrary user content.
- Copied-pool subprocess checks covered engine-free `list_styles` and styled
  base64 input through the default repair pipeline.

The aggregate regression command below runs from `Tlamatini/` (the directory
containing `manage.py`) after installing the application's development dependencies:

```powershell
$env:DJANGO_SETTINGS_MODULE = 'tlamatini.settings'
python -c "import django, unittest, sys; django.setup(); names=['agent.test_latexer_agent','agent.test_latexer_suite','agent.test_latexer_repair_ladder','agent.test_latexer_verbatim_channel','agent.test_latexer_styles']; result=unittest.TextTestRunner(verbosity=1).run(unittest.defaultTestLoader.loadTestsFromNames(names)); sys.exit(not result.wasSuccessful())"
```

These counts record the implementation verification on that date. Rerun the
checks after code changes before claiming the same result for a later revision.

Reproducible local outputs (excluded from Git):

- `artifacts/latexer-styles/index.html`: searchable gallery, PDFs and editable TeX.
- `artifacts/latexer-styles/report.json`: measured build results.
- `output/pdf/latexer-style-atlas.pdf`: cover and reading samples for all styles.

Runtime imports are standard-library-only beyond the existing agent's YAML
dependency. The developer verifier additionally uses PyMuPDF, Pillow and Poppler.
