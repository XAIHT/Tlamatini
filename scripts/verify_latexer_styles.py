# Created by Angela López Mendoza · @angelahack1
# Tlamatini Author Banner — do not remove (releases scrub the name automatically)
"""Compile real LaTeX, audit content/geometry, render with Poppler, build an atlas.

python scripts/verify_latexer_styles.py --matrix
The matrix covers all 30 styles with all three engines, print mode, all templates,
long multilingual metadata, multi-page content, and compact/decoration controls.
No mocked compiler, repair ladder, model calls, or shell escape.
"""
import argparse
import html
import importlib.util
import json
import logging
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
AGENT = ROOT / 'Tlamatini' / 'agent' / 'agents' / 'latexer'
sys.path.insert(0, str(AGENT))
os.environ.setdefault('TLAMATINI_TEMP', str(ROOT / 'Temp'))

import fitz
from PIL import Image, ImageDraw, ImageFont
import latexer_styles as styles


COPY = {
    'editorial': ('Ideas worth keeping.', 'A thoughtful home for the next great idea.'),
    'playful': ('Small wonders. Beautiful beginnings.', 'A little room for a very big imagination.'),
    'cyberpunk': ('After dark. Beyond ordinary.', 'Electric possibilities, written in light.'),
    'cosmic': ('A universe of possibilities.', 'An invitation to look a little further.'),
    'electronics': ('Ideas into instruments.', 'From the first signal to the next invention.'),
    'tlamatini': ('Knowledge beyond the stars.', 'Ancient geometry. Unbounded imagination.'),
}

BODY = r"""A beautiful document invites discovery. Clear typography and generous spacing
give each idea a place to grow, from a small observation to a new understanding.

\subsection{A language for discovery}
Mathematics keeps its precision inside every visual identity:
\begin{equation}\label{eq:energy}
 E=mc^{2},\qquad \int_0^1 x^2\,\mathrm{d}x=\frac{1}{3}.
\end{equation}
Equation~\ref{eq:energy} remains selectable, searchable and beautifully typeset.

\begin{TLcallout}{Make room for wonder}
Good design gives the reader a clear path through an idea. The artwork has its
own space; every word has room to breathe.
\end{TLcallout}

\subsection{Details that belong together}
\begin{tabularx}{\linewidth}{@{}lX@{}}
\TLtablehead\TLcellhead{Element} & \TLcellhead{Purpose} \\
Typography & A deliberate rhythm for comfortable reading. \\
\rowcolor{TLSurface}\textcolor{TLSurfaceInk}{Color} & \textcolor{TLSurfaceInk}{A coordinated palette with checked text contrast.} \\
Geometry & Original vector artwork, crisp at every scale. \\
\bottomrule
\end{tabularx}

\begin{lstlisting}[language=Python]
def discover(curiosity):
    return curiosity * 2
\end{lstlisting}
"""


def load_agent():
    cwd, handlers = os.getcwd(), list(logging.getLogger().handlers)
    level = logging.getLogger().level
    try:
        spec = importlib.util.spec_from_file_location('latexer_verifier_agent', AGENT / 'latexer.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        os.chdir(cwd)
        logging.getLogger().handlers[:] = handlers
        logging.getLogger().setLevel(level)


def audit(pdf_path, required):
    findings = []
    with fitz.open(pdf_path) as pdf:
        text = '\n'.join(page.get_text() for page in pdf)
        normalized = re.sub(r'\s+', ' ', text)
        for phrase in required:
            if phrase not in normalized:
                findings.append('Missing source text: ' + phrase)
        for number, page in enumerate(pdf, 1):
            if not page.get_text().strip():
                findings.append('Empty page %d' % number)
            for block in page.get_text('dict')['blocks']:
                for line in block.get('lines', []):
                    for span in line['spans']:
                        x0, y0, x1, y1 = span['bbox']
                        if span['text'].strip() and (x0 < 8 or y0 < 8 or x1 > page.rect.width - 8 or y1 > page.rect.height - 8):
                            findings.append('Page %d: text leaves safe page bounds: %s' % (number, span['text']))
        return dict(pages=len(pdf), clean=not findings, findings=findings)


def gallery(dest, records):
    cards = []
    for row in records:
        esc = html.escape
        key = row['id']
        cards.append(f'''<article data-family="{esc(row['family'])}"><a href="{key}/sample.pdf"><img loading="lazy" src="{key}/page-1.png" alt="{esc(row['label'])} cover"></a><div><small>{esc(row['family'])}</small><h2>{esc(row['label'])}</h2><code>style: {key}</code><p><a href="{key}/sample.pdf">Open PDF</a> · <a href="{key}/sample.tex">LaTeX source</a> · <a href="{key}/page-2.png">Body page</a></p></div></article>''')
    page = '''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>LaTeXer | Beyond the ordinary</title><style>
*{box-sizing:border-box}body{margin:0;background:#0b1821;color:#edf4f7;font:16px/1.6 system-ui}main{max-width:1500px;margin:auto;padding:64px 36px}header{max-width:1000px}small{color:#9be2d2;text-transform:uppercase;letter-spacing:.16em;font-size:11px}h1{font-size:clamp(38px,6vw,82px);line-height:1.06;letter-spacing:-.04em;margin:24px 0}header p{color:#b1c1ce;font-size:20px;max-width:760px}a{color:#a3e8d7}nav{display:flex;gap:14px;margin:32px 0;flex-wrap:wrap}input,select{font:inherit;padding:10px 16px;background:#182c39;border:1px solid #416070;border-radius:6px;color:#edf4f7}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(265px,1fr));gap:24px}article{border:1px solid #2c4352;border-radius:10px;background:#112431;overflow:hidden}article img{width:100%;display:block}article div{padding:20px}h2{font-size:22px;margin:5px 0}code,article p{font-size:12px}[hidden]{display:none}:focus-visible{outline:2px solid #a3e8d7;outline-offset:4px}footer{margin:40px 0;color:#adbfcc}</style>
<main><header><small>Tlamatini / LaTeXer / Signature collection</small><h1>Knowledge,<br>beautifully typeset.</h1><p>Thirty worlds for your ideas. Gentle beginnings, neon horizons, celestial discoveries and geometry beyond this planet. Real LaTeX. Original vector art. A complete reading experience.</p><p><a href="../../output/pdf/latexer-style-atlas.pdf">Explore the style atlas</a> · <a href="report.json">Validation report</a></p></header><nav aria-label="Filter styles"><input id="search" aria-label="Search styles" placeholder="Find a style..."><select id="family" aria-label="Family"><option value="">All collections</option><option>editorial</option><option>playful</option><option>cyberpunk</option><option>cosmic</option><option>electronics</option><option>tlamatini</option></select></nav><section class="grid">CARDS</section><footer>Previews rendered independently with Poppler from actual TeX-engine output. Text, page bounds and TeX overflow diagnostics are checked. Print mode and compact titles are available in every identity.</footer><script>const search=document.querySelector('#search'),family=document.querySelector('#family');function filter(){for(const c of document.querySelectorAll('article'))c.hidden=!!((family.value&&c.dataset.family!==family.value)||!c.textContent.toLowerCase().includes(search.value.toLowerCase()));}search.addEventListener('input',filter);family.addEventListener('change',filter);</script></main></html>'''
    (dest / 'index.html').write_text(page.replace('CARDS', '\n'.join(cards)), encoding='utf-8')


def contact_sheets(dest, records):
    try:
        font = ImageFont.truetype('C:/Windows/Fonts/segoeui.ttf', 18)
    except OSError:
        font = ImageFont.load_default()
    for page in (1, 2):
        for start in range(0, len(records), 6):
            sheet = Image.new('RGB', (1080, 1120), '#142632')
            draw = ImageDraw.Draw(sheet)
            for i, row in enumerate(records[start:start + 6]):
                with Image.open(dest / row['id'] / ('page-%d.png' % page)) as im:
                    im.thumbnail((340, 480))
                    x, y = i % 3 * 360 + 10, i // 3 * 560 + 10
                    sheet.paste(im, (x, y))
                    draw.text((x, y + 492), row['label'], font=font, fill='white')
            sheet.save(dest / ('%s-%d.png' % ('covers' if page == 1 else 'bodies', start // 6 + 1)))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / 'artifacts' / 'latexer-styles')
    parser.add_argument('--styles', default='', help='Comma-separated style IDs; empty means all')
    parser.add_argument('--matrix', action='store_true')
    parser.add_argument('--reuse', action='store_true',
                        help='Re-audit prior successful verifier PDFs when their emitted source is unchanged')
    args = parser.parse_args()
    dest = args.output.resolve()
    dest.mkdir(parents=True, exist_ok=True)
    prior = {}
    if args.reuse and (dest / 'report.json').is_file():
        prior = {row['variant']: row for row in json.loads((dest / 'report.json').read_text(encoding='utf-8'))
                 if row.get('compiled') and row.get('clean')}
    poppler = shutil.which('pdftoppm')
    if not poppler:
        raise SystemExit('pdftoppm (Poppler) is required for independent rendering')
    agent = load_agent()
    keys = [styles.normalise_style(k) for k in args.styles.split(',')] if args.styles else list(styles.STYLES)
    engines = ('pdflatex', 'xelatex', 'lualatex') if args.matrix else ('pdflatex',)
    chains = {engine: agent._resolve_toolchain({'engine': engine}, dict(os.environ)) for engine in engines}
    for engine, chain in chains.items():
        if not chain['latex']:
            raise SystemExit('Required matrix engine unavailable: ' + engine)
    checks, records, atlas = [], [], fitz.open()
    bookmarks = []

    def compile_one(key, engine='pdflatex', mode='screen', template='article', suffix='', **overrides):
        title, subtitle = COPY[styles.STYLES[key]['family']]
        cfg = dict(style=key, style_mode=mode, title=title, subtitle=subtitle, author='Tlamatini',
                   date='THE SIGNATURE COLLECTION', content=BODY, engine=engine,
                   use_latexmk=False, repair=False, shell_escape=False, command_timeout=180, max_passes=5)
        cfg.update(overrides)
        name = key if not suffix else key + '-' + suffix
        folder = dest / name
        folder.mkdir(exist_ok=True)
        source = agent._render_template(template, cfg)
        path = folder / 'sample.tex'
        previous = prior.get(name, {})
        reusable = (previous.get('engine') == engine and previous.get('mode') == mode
                    and previous.get('template') == template and path.is_file()
                    and path.read_text(encoding='utf-8') == source
                    and (folder / 'sample.pdf').is_file() and (folder / 'sample.log').is_file())
        if reusable:
            # This explicitly reuses earlier real compilation evidence; it never
            # substitutes a fake engine result for a source that has changed.
            result = dict(ok=True, passes=previous['passes'], diag={'errors': previous['errors']})
        else:
            path.write_text(source, encoding='utf-8')
            # Remove only a stale verifier-owned PDF so failed compilation cannot pass by reuse.
            (folder / 'sample.pdf').unlink(missing_ok=True)
            result = agent._compile(str(path), cfg, chains[engine], dict(os.environ))
        row = dict(id=key, variant=name, engine=engine, mode=mode, template=template,
                   compiled=result['ok'], errors=result['diag']['errors'], passes=result['passes'],
                   reused=bool(reusable))
        if result['ok']:
            row.update(audit(folder / 'sample.pdf', ['A beautiful document invites discovery.'] if cfg['content'] == BODY else ['SENTINEL']))
            log = (folder / 'sample.log').read_text(encoding='utf-8', errors='replace')
            row['overflows'] = re.findall(r'Overfull \\[hv]box[^\n]*', log)
            row['clean'] = row['clean'] and not row['overflows']
        else:
            row.update(clean=False, pages=0, findings=['Compile failed'])
        checks.append(row)
        (dest / 'report.json').write_text(json.dumps(checks, indent=2, ensure_ascii=False), encoding='utf-8')
        print('%s / %s: %s (%d pages)' % (name, engine, 'PASS' if row['clean'] else 'FAIL', row['pages']), flush=True)
        if not row['clean']:
            raise RuntimeError(json.dumps(row, indent=2, ensure_ascii=False))
        return folder, row

    for key in keys:
        folder, row = compile_one(key)
        spec = styles.STYLES[key]
        records.append(dict(id=key, label=spec['label'], family=spec['family'], pages=row['pages']))
        with fitz.open(folder / 'sample.pdf') as pdf:
            bookmarks.append([1, spec['label'], atlas.page_count + 1])
            atlas.insert_pdf(pdf)
        subprocess.run([poppler, '-scale-to', '1150', '-png', str(folder / 'sample.pdf'), str(folder / 'page')],
                       check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        if args.matrix:
            compile_one(key, mode='print', suffix='print')
            for engine in engines[1:]:
                compile_one(key, engine=engine, suffix=engine)
    if args.matrix:
        for template in agent._TEMPLATES:
            compile_one('tlamatini_celestial', template=template, suffix=template,
                        content='SENTINEL: Ciencia, tecnología, imaginación. $E=mc^2$.', document_language='es')
        compile_one('baby_sky', suffix='long', title='A long title about curiosity, discovery and the beautiful possibilities that grow when we give every small idea room to become something extraordinary',
                    subtitle='A multilingual journey: ciencia, tecnología, imaginación y conocimiento.',
                    content=('\\section{SENTINEL}\n' + ('A thoughtful paragraph about discovery and imagination. ' * 20) + '\n\n') * 14)
        compile_one('circuit_board', suffix='compact', style_cover=False, style_decoration='none', predominant_color='#FFFFFF')
        compile_one('aztec_obsidian', suffix='restrained', style_decoration='restrained')
        compile_one('cosmic_nebula', template='beamer', suffix='beamer-body')
    atlas.set_toc(bookmarks)
    atlas.set_metadata(dict(title='LaTeXer - The signature collection', author='Tlamatini', subject='30 visual identities, with real typeset reading samples'))
    target = ROOT / 'output' / 'pdf' / 'latexer-style-atlas.pdf'
    target.parent.mkdir(parents=True, exist_ok=True)
    atlas.save(target, garbage=4, deflate=True)
    atlas.close()
    gallery(dest, records)
    contact_sheets(dest, records)
    print('Verified %d real builds. Atlas: %s' % (len(checks), target))


if __name__ == '__main__':
    main()
