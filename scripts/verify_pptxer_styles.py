"""Render the twelve new PPTXer styles with complete 256-character fields."""
import argparse
import html
import json
import os

import verify_pptxer_layout as lab
from pptxer_visibility_gallery import write_gallery


def style_deck(key):
    lab.PAYLOADS.clear()
    p, slide = lab.payload, lab.model.Slide
    spec = lab.nuance.STYLE_PRESETS[key]
    return lab.model.Deck([
        slide(kind="title_slide", title=spec["label"], subtitle=spec["note"], kicker="PPTXER / STYLE COLLECTION"),
        slide(kind="stats", title="Every detail stays visible", stats=[
            {"value": f"{i+1}42%", "label": p(f"CARD{i}")} for i in range(3)]),
        slide(kind="two_column", title="Ideas with room to breathe", columns=[
            {"title": title, "bullets": [p(f"COLUMN{i}_{j}") for j in range(2)]}
            for i, title in enumerate(("The observation", "The next step"))]),
        slide(kind="table", title="Evidence in every cell", table={"headers": ["Area", "Evidence"],
            "rows": [["Typography", p("CELL0")], ["Layout", p("CELL1")]]}),
        slide(kind="timeline", title="A clear path forward", timeline=[
            {"when": title, "what": p(f"PHASE{i}")} for i, title in enumerate(("Discover", "Design", "Deliver"))]),
        slide(kind="chart", title="Where the effort goes", chart={"kind": "doughnut",
            "categories": ["Research", "Design", "Delivery"],
            "series": [{"name": "Effort", "values": [25, 45, 30]}]}),
        slide(kind="diagram", title="From idea to delivery", diagram={"kind": "flow",
            "nodes": [p(f"NODE{i}") for i in range(3)]}),
        slide(kind="bullets", title=p("HEADING"), body=p("BODY")),
        slide(kind="code", title="Code keeps its structure", code="def evidence():\n    value = '" + p("CODE", "token") + "'\n    return value"),
        slide(kind="bullets", title="A complete identifier", body="W" * 256),
        slide(kind="quote", quote=p("QUOTE"), attribution="PPTXer visibility study"),
        slide(kind="bullets", title="Text without word spaces", body=p("CJK", "cjk")),
    ], title=spec["label"])


def write_style_gallery(dest, reports):
    write_gallery(dest, reports)
    gallery = dest / "index.html"
    page = gallery.read_text(encoding="utf-8")
    page = page.replace("Every character accounted for.", "Twelve new ways to present.")
    page = page.replace("Each stress field contains exactly", "Each long-text stress field contains exactly")
    page = page.replace('The striped images are deterministic crop test fixtures.',
                        'Decorative backgrounds are enabled in these style decks.')
    page = page.replace('../README.md', 'README.md').replace('../tests.txt', 'tests.txt')
    page = page.replace('../before/index.html', '../pptxer-visibility/verified/index.html').replace('Original implementation evidence', 'Original visibility test matrix')
    cards, covers = [], []
    for key, spec in lab.nuance.STYLE_PRESETS.items():
        examples = [r for r in reports if r['case'].startswith(key + '-') and (r.get('render') or {}).get('images')]
        if not examples:
            continue
        example = next((r for r in examples if r['case'].endswith('-16-9')), examples[0])
        case = example['case']
        covers.append((spec["label"], key, example["render"]["images"][0]))
        cards.append(f'<button class="card" onclick="byId(\'case\').value=\'{case}\';byId(\'search\').value=\'\';refresh();byId(\'gallery\').scrollIntoView()">'
                     f'<img src="{case}/slides/slide_001.png" alt="{html.escape(spec["label"])} preview">'
                     f'<div class="copy"><strong>{html.escape(spec["label"])}</strong><small>{html.escape(spec["note"])}</small></div></button>')
    page = page.replace('<h2>Results by theme and format</h2>',
        '<h2>Choose a style</h2><p>Select a cover to inspect that style’s full test deck. '
        'Use its name in PPTXer’s <code>nuance</code> setting.</p><section class="grid">'
        + ''.join(cards) + '</section><h2>Results by theme and format</h2>')
    gallery.write_text(page, encoding="utf-8")
    write_style_covers(dest, covers)


def write_style_covers(dest, covers):
    """A shareable overview assembled from the actual native slide exports."""
    from PIL import Image, ImageDraw, ImageFont
    if not covers:
        return
    width, height, columns = 600, 390, 3
    sheet = Image.new("RGB", (width * columns, height * ((len(covers) + columns - 1) // columns)), "#0B101B")
    draw = ImageDraw.Draw(sheet)
    try:
        label_font = ImageFont.truetype("arialbd.ttf", 20)
        key_font = ImageFont.truetype("arial.ttf", 15)
    except OSError:
        label_font = ImageFont.load_default(size=20)
        key_font = ImageFont.load_default(size=15)
    for index, (label, key, path) in enumerate(covers):
        x, y = index % columns * width, index // columns * height
        draw.text((x + 10, y + 9), label, font=label_font, fill="#EAF0FA")
        draw.text((x + 10, y + 34), key, font=key_font, fill="#83B5D3")
        with Image.open(path) as cover:
            cover.thumbnail((width - 20, height - 60))
            sheet.paste(cover, (x + (width - cover.width) // 2, y + 59))
    sheet.save(dest / "style-covers.jpg", quality=93)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--styles", nargs="+", default=list(lab.nuance.STYLE_PRESETS), choices=list(lab.nuance.STYLE_PRESETS))
    parser.add_argument("--sizes", nargs="+", default=["16:9", "4:3", "vertical"])
    parser.add_argument("--render", action="store_true")
    parser.add_argument("--flat", action="store_true", help="Disable decorative backgrounds")
    args = parser.parse_args()
    dest = lab.ROOT / "artifacts/pptxer-styles"
    dest.mkdir(parents=True, exist_ok=True)
    os.environ["TLAMATINI_TEMP"] = str(lab.ROOT / "Temp")
    reports = []
    for key in args.styles:
        for size in args.sizes:
            name = key + "-" + size.replace(":", "-")
            folder = dest / name
            folder.mkdir(exist_ok=True)
            deck = style_deck(key)
            theme = lab.themes.build_theme(lab.nuance.classify("", requested=key))
            result = lab.build.build_deck(deck, theme, str(folder / "stress.pptx"),
                {"slide_size": size, "generate_art": not args.flat})
            rr = lab.render.render_slides(result.path, str(folder / "slides"), prefer="powerpoint", timeout=180) if args.render and result.ok else None
            audit = lab.audit.audit_pptx(result.path, rr, text_boxes=result.text_boxes).as_dict() if result.ok else {}
            content = lab.check_content(result.path) if result.ok else {"payloads": 0, "missing": ["build failed"]}
            report = {"case": name, "build": result.as_dict(), "audit": audit, "render": rr,
                      "content": content, "theme": theme.as_dict()}
            reports.append(report)
            (folder / "report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
            print(json.dumps({"case": name, "slides": result.slide_count, "ok": result.ok,
                "defects": audit.get("defects"), "missing": content["missing"],
                "native": audit.get("ground_truth"), "error": result.error}), flush=True)
    # Keep completed cases when rerunning a subset.
    reports = [json.loads(p.read_text(encoding="utf-8")) for p in sorted(dest.glob("*/report.json"))]
    (dest / "report.json").write_text(json.dumps(reports, indent=2, ensure_ascii=False), encoding="utf-8")
    write_style_gallery(dest, reports)
    if any(not r["build"]["ok"] or r["build"]["placement_diagnostics"] or not r["audit"].get("layout_clean")
           or r["content"]["missing"] or (args.render and not r["audit"].get("ground_truth")) for r in reports):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
