# Tlamatini Author Banner — Created by Angela López Mendoza · @angelahack1
"""Render every documentation PDF and produce numbered review sheets visibly.

Run in a verified foreground console. This is a document renderer, not a browser
or application build. Review the individual images as well as these contact sheets.
"""
from pathlib import Path
import json
import re
import fitz
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT/"build/documentation_refresh/visual-review"
PDFS = {
    "summary": ROOT/"tlamatini_app_summary.pdf",
    "atlas": ROOT/"Tlamatini-Architecture.pdf",
    "lifecycle": ROOT/"OOB_shift_reaper-and-NAMU-Design.pdf",
    "fixture": ROOT/"Tlamatini/agent/doc_generation/test_output.pdf",
}
def sheets(paths, kind, columns=3, rows=2, width=670):
    target = OUT/"sheets"
    target.mkdir(parents=True, exist_ok=True)
    font = ImageFont.truetype("C:/Windows/Fonts/segoeuib.ttf", 22)
    for offset in range(0, len(paths), columns*rows):
        group = paths[offset:offset+columns*rows]
        thumbs = []
        for path in group:
            im = Image.open(path).convert("RGB")
            im.thumbnail((width, 950))
            thumbs.append(im)
        height = max(im.height for im in thumbs)+38
        sheet = Image.new("RGB",(columns*(width+12),rows*height),(215,220,225))
        draw = ImageDraw.Draw(sheet)
        for i,(im,path) in enumerate(zip(thumbs,group)):
            x=(i%columns)*(width+12)
            y=(i//columns)*height
            draw.text((x+8,y+4), f"{kind} {offset+i+1}", font=font, fill="black")
            sheet.paste(im,(x,y+34))
        sheet.save(target/f"{kind}-{offset+1:03d}-{offset+len(group):03d}.jpg",quality=94)
    print(f"Review sheets: {kind}, {len(paths)} items",flush=True)
def main():
    report={}
    for old in (OUT/"sheets").glob("*.jpg"):
        old.unlink()
    for kind,path in PDFS.items():
        folder=OUT/kind
        folder.mkdir(parents=True,exist_ok=True)
        for old in folder.glob("p*.png"):
            old.unlink()
        document=fitz.open(path)
        paths=[]
        bounds=[]
        text=[]
        for i,page in enumerate(document):
            image=folder/f"p{i+1:03d}.png"
            page.get_pixmap(dpi=110).save(image)
            paths.append(image)
            content=page.get_text()
            text.append(f"\nPAGE {i+1}\n{content}")
            for block in page.get_text("dict")["blocks"]:
                for line in block.get("lines",[]):
                    x0,y0,x1,y1=line["bbox"]
                    if min(x0,y0)<-0.5 or x1>page.rect.width+0.5 or y1>page.rect.height+0.5:
                        bounds.append({"page":i+1,"bbox":[x0,y0,x1,y1]})
            if (i+1)%10==0 or i+1==len(document):
                print(f"{kind}: rendered {i+1}/{len(document)}",flush=True)
        full="\n".join(text)
        (OUT/f"{kind}-text.txt").write_text(full,encoding="utf-8")
        stale=re.findall(r".{0,70}(?:latest released version|current release|CURRENT RELEASE).{0,120}",full,re.I)
        report[kind]={"pages":len(document),"outside_page":bounds,"current_claims":stale}
        sheets(paths,kind)
    slides=sorted((ROOT/"build/documentation_refresh/renders/ppt-fallback").glob("s*.png"))
    if slides:
        sheets(slides,"slides",columns=2,rows=3,width=1000)
        verification_path = ROOT/"build/documentation_refresh/dossier_verification.json"
        verification = json.loads(verification_path.read_text(encoding="utf-8"))
        native = verification.get("pptx_native", {}).get("available", False)
        report["slides"]={"rendered":len(slides), "nativePowerPoint":native,
                          "renderer":"Microsoft PowerPoint" if native else "bundled artifact-tool; native Office unavailable"}
    (OUT/"visual-audit.json").write_text(json.dumps(report,indent=2),encoding="utf-8")
    print("All render sheets ready for human visual inspection.",flush=True)
if __name__=="__main__":
    main()
