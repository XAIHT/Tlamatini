"""Create an offline, searchable gallery of actual PowerPoint test renders."""
import html
import json
from pathlib import Path


def write_gallery(dest, reports):
    dest = Path(dest).resolve()
    slides, rows = [], []
    frames = 0
    for report in reports:
        key = report['case']
        native = (report.get('render') or {}).get('text_bounds') or {}
        frames += len(native.get('frames', []))
        texts = {}
        for frame in native.get('frames', []):
            if frame['name'] != 'pptxer:footer':
                texts.setdefault(frame['slide'], []).append(frame['text'])
        for i, path in enumerate((report.get('render') or {}).get('images', []), 1):
            lines = texts.get(i, [])
            slides.append(dict(case=key, number=i, image=Path(path).relative_to(dest).as_posix(),
                               title=(lines[0] if lines else 'Chart or visual')[:100], text='\n'.join(lines)))
        clean = (report['audit'].get('layout_clean') and not report['content']['missing']
                 and not report['build']['placement_diagnostics'])
        rows.append(f"<tr><td>{html.escape(key)}</td><td>{report['build']['slides']}</td>"
                    f"<td>{len(native.get('frames', []))}</td><td>{report['content'].get('payloads', 0)}</td>"
                    f"<td class={'pass' if clean else 'fail'}>{'PASS' if clean else 'FINDINGS'}</td>"
                    f"<td><a href='{key}/stress.pptx'>PPTX</a> · <a href='{key}/report.json'>Measurements</a></td></tr>")
    page = PAGE.replace('__SLIDES__', str(len(slides))).replace('__FRAMES__', f'{frames:,}')
    page = page.replace('__PAYLOADS__', str(sum(r['content'].get('payloads', 0) for r in reports)))
    page = page.replace('__ROWS__', ''.join(rows))
    page = page.replace('__DATA__', json.dumps(slides, ensure_ascii=False).replace('</', '<\\/'))
    (dest / 'index.html').write_text(page, encoding='utf-8')
    write_contact_sheets(dest, reports)


def write_contact_sheets(dest, reports):
    """Keep every native image available in compact visual-review sheets."""
    from PIL import Image, ImageDraw, ImageFont
    try:
        font = ImageFont.truetype('arial.ttf', 18)
    except OSError:
        font = ImageFont.load_default(size=18)
    for report in reports:
        images = (report.get('render') or {}).get('images', [])
        if not images:
            continue
        folder = Path(dest) / report['case'] / 'contact-sheets'
        folder.mkdir(exist_ok=True)
        width, height, columns, rows = ((500, 915, 3, 2) if 'vertical' in report['case']
                                       else (600, 365, 3, 4))
        per_sheet = columns * rows
        for start in range(0, len(images), per_sheet):
            sheet = Image.new('RGB', (width * columns, height * rows), '#101827')
            draw = ImageDraw.Draw(sheet)
            for j, path in enumerate(images[start:start + per_sheet]):
                x, y = j % columns * width, j // columns * height
                draw.text((x + 7, y + 4), f"{report['case']} / {start + j + 1}", font=font, fill='white')
                with Image.open(path) as image:
                    image.thumbnail((width - 12, height - 32))
                    sheet.paste(image, (x + (width - image.width) // 2, y + 28))
            sheet.save(folder / f'contact_{start // per_sheet + 1:02d}.jpg', quality=90)


PAGE = r'''<!doctype html><html lang="en"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>PPTXer · Visibility lab</title>
<style>
:root{color-scheme:dark;font-family:Segoe UI,system-ui,sans-serif;background:#0b101b;color:#eaf0fa}*{box-sizing:border-box}
body{margin:0}main{max-width:1440px;margin:auto;padding:48px 28px}a{color:#85d9ff}h1{font-size:clamp(32px,5vw,64px);letter-spacing:-2px;margin:12px 0}h2{font-size:25px;margin-top:44px}p{line-height:1.6;color:#b8c5d9;max-width:880px}.eyebrow{color:#64e6b3;letter-spacing:3px;font-size:12px;font-weight:700}.metrics{display:grid;grid-template-columns:repeat(3,1fr);gap:14px;margin:30px 0}.metric{padding:23px;background:#131e30;border:1px solid #283950;border-radius:12px}.metric strong{display:block;font-size:38px;font-weight:600}.metric span{font-size:14px;color:#b8c5d9}.table-wrap{overflow:auto}table{border-collapse:collapse;width:100%;font-size:14px}th,td{padding:13px;text-align:left;border-bottom:1px solid #26354b}th{color:#a5b5ca}.pass{color:#64e6b3;font-weight:700}.fail{color:#ff9a9a;font-weight:700}
.toolbar{position:sticky;top:0;z-index:1;display:flex;gap:12px;align-items:center;flex-wrap:wrap;background:#0b101bf5;padding:18px 0;margin:20px 0}select,input,button{background:#172439;color:#eaf0fa;border:1px solid #3a4b63;border-radius:7px;padding:11px;font:inherit}input{flex:1;min-width:220px}button{cursor:pointer}button:hover{border-color:#85d9ff}#count{font-size:13px;color:#b8c5d9}.grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:20px}.card{padding:0;overflow:hidden;text-align:left;background:#101b2a;border:1px solid #2b3b50;border-radius:10px}.card img{width:100%;height:230px;object-fit:contain;background:#070c14;display:block}.card .copy{padding:14px}.card small{display:block;color:#83b5d3;font-size:12px;margin-bottom:6px}.card strong{display:block;font-size:14px;font-weight:500;line-height:1.45;overflow:hidden;white-space:nowrap;text-overflow:ellipsis}
dialog{padding:20px;width:min(1500px,97vw);max-height:97vh;background:#0b101b;color:#eaf0fa;border:1px solid #415c7b;border-radius:10px}dialog::backdrop{background:#000c}.viewerbar{display:flex;align-items:center;gap:12px;margin-bottom:14px}.viewerbar span{flex:1}.viewerbar a{font-size:14px}#full{display:block;max-width:100%;max-height:75vh;object-fit:contain;margin:auto}details{margin-top:16px;color:#b8c5d9}pre{white-space:pre-wrap;word-break:break-word;line-height:1.5}footer{margin-top:40px;font-size:13px;color:#8296b0}@media(max-width:850px){.grid{grid-template-columns:repeat(2,minmax(0,1fr))}.metrics{gap:8px}.metric{padding:15px}.metric strong{font-size:28px}}@media(max-width:560px){main{padding:28px 16px}.grid{grid-template-columns:1fr}.metrics{grid-template-columns:1fr}.viewerbar{flex-wrap:wrap}.viewerbar span{flex-basis:100%}}
</style><main><div class="eyebrow">PPTXER / VISIBILITY LAB</div><h1>Every character accounted for.</h1>
<p>Actual PowerPoint exports, saved-file geometry checks, and native text measurements. Each stress field contains exactly <strong>256 characters</strong>. Full strings—including their final characters—are checked in the saved presentation.</p>
<div class="metrics"><div class="metric"><strong>__SLIDES__</strong><span>slides rendered by PowerPoint</span></div><div class="metric"><strong>__FRAMES__</strong><span>native text frames measured</span></div><div class="metric"><strong>__PAYLOADS__</strong><span>complete long-text checks</span></div></div>
<p><a href="../README.md">Findings and verification scope</a> · <a href="../tests.txt">Regression test log</a> · <a href="../before/index.html">Original implementation evidence</a></p>
<h2>Results by theme and format</h2><div class="table-wrap"><table><thead><tr><th>Deck</th><th>Slides</th><th>Text frames</th><th>Long texts</th><th>Result</th><th>Files</th></tr></thead><tbody>__ROWS__</tbody></table></div>
<h2>Inspect the actual slides</h2><p>Filter the gallery, search any visible text or END marker, and select a slide to inspect its full render. Use the arrow keys to move between slides. The striped images are deterministic crop test fixtures.</p>
<div class="toolbar"><select id="case" aria-label="Deck"><option value="">All decks</option></select><input id="search" placeholder="Search content, layout, or END marker" aria-label="Search slides"><span id="count"></span></div><section id="gallery" class="grid"></section>
<footer>Verified with the installed Windows fonts and Microsoft PowerPoint. Charts are visually inspected; native frame measurements cover text boxes, diagram labels, and table cells. These results describe this test corpus, not every possible viewer or font environment.</footer></main>
<dialog id="viewer"><div class="viewerbar"><span id="caption"></span><button id="previous" aria-label="Previous slide">←</button><button id="next" aria-label="Next slide">→</button><a id="original" target="_blank">Open PNG</a><button id="close">Close</button></div><img id="full" alt="PowerPoint slide"><details><summary>Full text measured by PowerPoint</summary><pre id="transcript"></pre></details></dialog>
<script>const slides=__DATA__;const byId=id=>document.getElementById(id);let filtered=slides,selected=0;
for(const name of [...new Set(slides.map(s=>s.case))]){const option=document.createElement('option');option.value=option.textContent=name;byId('case').append(option)}
function show(index){selected=(index+filtered.length)%filtered.length;const s=filtered[selected];byId('caption').textContent=`${s.case} · Slide ${s.number}`;byId('full').src=s.image;byId('original').href=s.image;byId('transcript').textContent=s.text;if(!byId('viewer').open)byId('viewer').showModal()}
function refresh(){const query=byId('search').value.toLocaleLowerCase();filtered=slides.filter(s=>(!byId('case').value||s.case===byId('case').value)&&(`${s.title} ${s.text}`.toLocaleLowerCase().includes(query)));byId('gallery').replaceChildren();byId('count').textContent=`${filtered.length} slides`;
filtered.forEach((s,i)=>{const button=document.createElement('button');button.className='card';const img=document.createElement('img');img.loading='lazy';img.src=s.image;img.alt=`${s.case} slide ${s.number}`;const copy=document.createElement('div');copy.className='copy';const small=document.createElement('small');small.textContent=`${s.case} / ${String(s.number).padStart(3,'0')}`;const title=document.createElement('strong');title.textContent=s.title;copy.append(small,title);button.append(img,copy);button.onclick=()=>show(i);byId('gallery').append(button)})}
byId('case').onchange=refresh;byId('search').oninput=refresh;byId('close').onclick=()=>byId('viewer').close();byId('previous').onclick=()=>show(selected-1);byId('next').onclick=()=>show(selected+1);document.addEventListener('keydown',e=>{if(byId('viewer').open&&e.target.tagName!=='INPUT'){if(e.key==='ArrowLeft')show(selected-1);if(e.key==='ArrowRight')show(selected+1)}});refresh();</script></html>'''


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    args = parser.parse_args()
    write_gallery(args.directory, json.loads((args.directory / 'report.json').read_text(encoding='utf-8')))
