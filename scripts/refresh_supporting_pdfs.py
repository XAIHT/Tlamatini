# Tlamatini Author Banner — Created by Angela López Mendoza · @angelahack1
"""Regenerate the lifecycle note and the existing PDF renderer fixture visibly."""
from pathlib import Path
from xml.sax.saxutils import escape
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak, Table, TableStyle

ROOT = Path(__file__).resolve().parents[1]
pdfmetrics.registerFont(TTFont("Doc", "C:/Windows/Fonts/segoeui.ttf"))
pdfmetrics.registerFont(TTFont("DocBold", "C:/Windows/Fonts/segoeuib.ttf"))
BODY = ParagraphStyle("body", fontName="Doc", fontSize=10.5, leading=15, spaceAfter=12,
                      textColor=colors.HexColor("#23354b"))
TITLE = ParagraphStyle("title", parent=BODY, fontName="DocBold", fontSize=24, leading=29, spaceAfter=18)
H2 = ParagraphStyle("section", parent=TITLE, fontSize=18, leading=23)
def footer(canvas, doc):
    canvas.setStrokeColor(colors.HexColor("#3aa6a0"))
    canvas.line(42, 46, A4[0]-42, 46)
    canvas.setFont("Doc", 8)
    canvas.setFillColor(colors.HexColor("#53657b"))
    canvas.drawString(42, 31, "Tlamatini v1.90.0 | Angela López Mendoza | source review 2026-10-22")
    canvas.drawRightString(A4[0]-42, 31, str(doc.page))
def main():
    text = (ROOT/"docs/oob-namu-lifecycle.md").read_text(encoding="utf-8")
    parts = text.split("\n## ")
    story = [Paragraph(escape(parts[0].splitlines()[0].removeprefix("# ")), TITLE),
             Paragraph("Lifecycle, ownership and current implementation limits", BODY), Spacer(1, 8)]
    for index, part in enumerate(parts[1:]):
        if index:
            story.append(PageBreak())
        heading, body = part.split("\n", 1)
        story.append(Paragraph(escape(heading), H2))
        for para in body.strip().split("\n\n"):
            story.append(Paragraph(escape(" ".join(para.splitlines())), BODY))
    path = ROOT/"OOB_shift_reaper-and-NAMU-Design.pdf"
    SimpleDocTemplate(str(path), pagesize=A4, leftMargin=42, rightMargin=42,
                      topMargin=42, bottomMargin=64, title="OOB and NAMU - v1.90.0",
                      author="Angela López Mendoza").build(story, onFirstPage=footer, onLaterPages=footer)
    print(f"Regenerated {path}", flush=True)
    # Keep this file a small renderer fixture, not another product guide.
    fixture = ROOT/"Tlamatini/agent/doc_generation/test_output.pdf"
    table = Table([["Col A", "Col B"], ["1", "2"]], colWidths=[160,160])
    table.setStyle(TableStyle([("FONTNAME",(0,0),(-1,-1),"Doc"),
                               ("BACKGROUND",(0,0),(-1,0),colors.HexColor("#e5f4f2")),
                               ("GRID",(0,0),(-1,-1),0.5,colors.HexColor("#9aaec1")),
                               ("TOPPADDING",(0,0),(-1,-1),8),
                               ("BOTTOMPADDING",(0,0),(-1,-1),8)]))
    SimpleDocTemplate(str(fixture), pagesize=A4, title="Test Document", author="Angela López Mendoza").build([
        Paragraph("Test Document", TITLE), Paragraph("This is a test paragraph.", BODY),
        Paragraph("Table", H2), table, Spacer(1,20),
        Paragraph("CREATED BY ANGELA LÓPEZ MENDOZA · @angelahack1", BODY)])
    print(f"Regenerated renderer fixture {fixture}", flush=True)
if __name__ == "__main__":
    main()
