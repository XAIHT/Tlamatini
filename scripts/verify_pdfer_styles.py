# Created by Angela López Mendoza · @angelahack1
# Tlamatini Author Banner — do not remove (releases scrub the name automatically)
"""Build, measure and render every PDFer style, plus a browsable gallery and atlas."""
from __future__ import annotations

import argparse
import html
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "Tlamatini" / "agent" / "agents" / "pdfer"))
os.environ.setdefault("TLAMATINI_TEMP", str(ROOT / "Temp"))

import fitz
from PIL import Image, ImageDraw, ImageFont
import pdfer_atelier
import pdfer_audit
import pdfer_docmodel
import pdfer_nuance
import pdfer_ornament
import pdfer_styles
import pdfer_theme
import pdfer_typography


COPY = {
    "playful": ("Small wonders.\nBeautiful beginnings.", "A little room for a very big imagination.",
                "Make room for wonder", "Every small discovery deserves a beautiful home. Gentle colors, generous space and clear lettering turn a collection of little moments into something worth keeping."),
    "cyberpunk": ("After dark.\nBeyond ordinary.", "Signals, skylines and electric possibilities.",
                 "Light up the next idea", "A luminous city of ideas begins with a single signal. Sharp geometry and confident typography bring the energy of the night into a document designed to be explored."),
    "cosmic": ("A universe\nof possibilities.", "An invitation to look a little further.",
               "Follow your curiosity", "Beyond the familiar horizon lies a field of beautiful questions. Orbital lines and celestial color give each idea a place in a wider story, with room to breathe and space to discover."),
    "electronics": ("Ideas into\ninstruments.", "A clear signal from imagination to invention.",
                    "Build the next possibility", "Every invention begins with a connection. Precise traces and measured typography celebrate the craft of making something work, from the first sketch to the final instrument."),
    "tlamatini": ("Knowledge\nbeyond the stars.", "Ancient geometry. Unbounded imagination.",
                  "Imagine beyond this world", "Step into a universe where luminous jade, obsidian and celestial gold meet. Original geometric artwork carries the spirit of discovery through a document made for ideas beyond the ordinary."),
}


def gallery(dest, records):
    cards = []
    for row in records:
        esc = html.escape
        cards.append(f'''<article data-family="{esc(row['family'])}" data-label="{esc(row['label'].lower())}">
<a href="{row['id']}/sample.pdf"><img loading="lazy" src="{row['id']}/page-1.png" alt="{esc(row['label'])} cover"></a>
<div class="copy"><small>{esc(row['family'])}</small><h2>{esc(row['label'])}</h2>
<code>style: {row['id']}</code><p><a href="{row['id']}/sample.pdf">Open PDF</a> <a href="{row['id']}/page-2.png">Read body page</a></p>
<span class="status">{'Verified' if row['audit']['clean'] else 'Needs attention'} · {row['pages']} pages</span></div></article>''')
    page = '''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>PDFer | The signature collection</title><style>
*{box-sizing:border-box}body{margin:0;background:#0b1420;color:#eef3f8;font:16px/1.6 system-ui,sans-serif}
main{max-width:1480px;margin:auto;padding:64px 36px}header{max-width:980px;margin-bottom:38px}
.eyebrow{letter-spacing:.2em;text-transform:uppercase;color:#88dacd;font-size:12px}h1{font-size:clamp(38px,6vw,80px);line-height:1.06;font-weight:600;letter-spacing:-.045em;margin:24px 0}
.intro{font-size:20px;color:#aab9ca;max-width:750px}a{color:#9ce4d6;text-underline-offset:4px}nav{display:flex;flex-wrap:wrap;gap:12px;margin:32px 0}input,select{border:1px solid #3a4b60;background:#172535;color:white;padding:12px 16px;border-radius:8px;font:inherit}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(255px,1fr));gap:24px}article{border:1px solid #26394e;border-radius:12px;overflow:hidden;background:#121f2f}article img{width:100%;display:block;aspect-ratio:595/842;object-fit:contain;background:#0b1420}.copy{padding:20px}small{text-transform:uppercase;letter-spacing:.15em;color:#91abbf;font-size:10px}h2{margin:6px 0 8px;font-size:21px}code{font-size:12px;color:#c3d4e5}article p{display:flex;gap:18px;font-size:13px}.status{font-size:12px;color:#9fd2bd}footer{margin-top:40px;color:#9aaec1;font-size:13px}[hidden]{display:none}input:focus,select:focus,a:focus{outline:2px solid #8cdcca;outline-offset:3px}
</style><main><header><div class="eyebrow">Tlamatini / PDFer / Signature collection</div><h1>Every idea deserves<br>a beautiful document.</h1><p class="intro">24 new identities. From gentle beginnings to worlds beyond the stars. Explore real PDF covers, then open each document to inspect its typography, tables and reading experience.</p>
<p><a href="../../output/pdf/pdfer-style-atlas.pdf">Open the complete style atlas</a> &nbsp; <a href="report.json">View measured results</a></p></header>
<nav aria-label="Filter styles"><input id="search" aria-label="Search styles" placeholder="Find a style..."><select id="family" aria-label="Style family"><option value="">All collections</option><option>playful</option><option>cyberpunk</option><option>cosmic</option><option>electronics</option><option>tlamatini</option></select></nav>
<section class="grid">CARDS</section><footer>All previews were rendered from the generated PDFs with Poppler. Source text, palette contrast and page geometry are checked independently. Original vector artwork; no external images or font downloads.</footer>
<script>const search=document.querySelector('#search'),family=document.querySelector('#family');function filter(){for(const card of document.querySelectorAll('article'))card.hidden=!!((family.value&&card.dataset.family!==family.value)||!card.textContent.toLowerCase().includes(search.value.toLowerCase()));}search.addEventListener('input',filter);family.addEventListener('change',filter);</script></main></html>'''
    (dest / "index.html").write_text(page.replace("CARDS", "\n".join(cards)), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "artifacts" / "pdfer-styles")
    args = parser.parse_args()
    dest = args.output.resolve()
    dest.mkdir(parents=True, exist_ok=True)
    poppler = shutil.which("pdftoppm")
    if not poppler:
        raise SystemExit("pdftoppm (Poppler) is required to independently render the previews")
    book = pdfer_typography.FontBook()
    verdict = pdfer_nuance.classify("Discover the next beautiful idea!", hint="marketing")
    records, atlas = [], fitz.open()
    bookmarks = []
    for key, spec in pdfer_styles.STYLES.items():
        out = dest / key
        out.mkdir(exist_ok=True)
        title, subtitle, heading, prose = COPY[spec["family"]]
        source = (f"# {heading}\n\n{prose}\n\n## Details make the difference\n\n"
                  "A clear hierarchy makes a page easy to explore. Important ideas have space, "
                  "supporting details stay close, and every paragraph has a comfortable rhythm.\n\n"
                  "| Element | What you can expect |\n|---|---|\n"
                  "| Typography | Distinct headings, comfortable body text and a deliberate rhythm. |\n"
                  "| Color | A coordinated palette with measured contrast across text and tables. |\n"
                  "| Artwork | Original vector geometry, crisp at every scale and separate from the text. |\n\n"
                  "> Beauty begins with care: the care to make every word readable and every idea easy to find.\n\n"
                  "### A small invitation\n\n- Explore a new perspective.\n- Give a good idea room to grow.\n- Make something worth sharing.\n")
        design = pdfer_theme.build_design_system(verdict, {"style": key}, book)
        factory = pdfer_ornament.OrnamentFactory(design, seed_text=key)
        renderer = pdfer_atelier.Atelier(design, book, ornament=factory)
        path = out / "sample.pdf"
        report = renderer.build(pdfer_docmodel.parse(source, "markdown"), str(path),
                                title=title.replace("\n", " "), subtitle=subtitle,
                                author="TLAMATINI / " + spec["label"].upper(),
                                footer_note=spec["label"])
        result = pdfer_audit.audit_pdf(str(path), page_background=design.palette.background.hex)
        row = dict(id=key, label=spec["label"], family=spec["family"], pages=report["pages"],
                   audit=result.as_dict(), design=design.as_dict())
        records.append(row)
        with fitz.open(path) as pdf:
            bookmarks.append([1, spec["label"], atlas.page_count + 1])
            atlas.insert_pdf(pdf)
        subprocess.run([poppler, "-scale-to", "1150", "-png", str(path), str(out / "page")],
                       check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        print("%s: %s" % (key, result.summary()), flush=True)
    atlas.set_toc(bookmarks)
    atlas.set_metadata(dict(title="PDFer - The signature collection", author="Tlamatini",
                            subject="24 visual identities with cover and reading samples"))
    atlas_path = ROOT / "output" / "pdf" / "pdfer-style-atlas.pdf"
    atlas_path.parent.mkdir(parents=True, exist_ok=True)
    atlas.save(atlas_path, garbage=4, deflate=True)
    atlas.close()
    (dest / "report.json").write_text(json.dumps(records, indent=2, ensure_ascii=False), encoding="utf-8")
    gallery(dest, records)
    # Contact sheets cover both the artwork and the actual reading pages.
    try:
        font = ImageFont.truetype(str(Path(os.environ.get("WINDIR", "C:/Windows"))
                                      / "Fonts" / "segoeui.ttf"), 17)
    except OSError:
        font = ImageFont.load_default()
    for page_number in (1, 2):
        for group in range((len(records) + 5) // 6):
            sheet = Image.new("RGB", (1080, 1120), "#172333")
            draw = ImageDraw.Draw(sheet)
            for i, row in enumerate(records[group * 6:group * 6 + 6]):
                with Image.open(dest / row["id"] / ("page-%d.png" % page_number)) as im:
                    im.thumbnail((340, 480))
                    x, y = (i % 3) * 360 + 10, (i // 3) * 560 + 10
                    sheet.paste(im, (x, y))
                    draw.text((x, y + 490), row["label"], fill="white", font=font)
            name = ("contact-%d.png" if page_number == 1 else "body-%d.png") % (group + 1)
            sheet.save(dest / name)
    print("Atlas: %s" % atlas_path)
    return 0 if all(row["audit"]["clean"] for row in records) else 1


if __name__ == "__main__":
    raise SystemExit(main())
