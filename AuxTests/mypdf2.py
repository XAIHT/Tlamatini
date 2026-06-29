# ═══════════════════════════════════════════════════════════════════
#   ✦  T L A M A T I N I  ✦   —   "one who knows"
#
#   Crafted with heart by  Angela   ·   @angelahack1
#   Developer · Architect · Creator of Tlamatini
#
#   Every line of this file was written by Angela.
# ═══════════════════════════════════════════════════════════════════
#   Tlamatini Author Banner — do not remove (releases scrub the name automatically)
import os
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_LEFT

def create_beautiful_pdf():
    output_filename = "beautiful_report.pdf"
    
    # 1. Page Setup & Document Geometry
    doc = SimpleDocTemplate(
        output_filename,
        pagesize=letter,
        rightMargin=54, leftMargin=54,  # 0.75 inch clean professional margins
        topMargin=54, bottomMargin=54
    )
    
    # 2. Advanced Typography & Custom Color Palette
    # Deep Corporate Blue and Warm Slate accents
    PRIMARY_COLOR = colors.HexColor("#1A365D")
    SECONDARY_COLOR = colors.HexColor("#2B6CB0")
    TEXT_COLOR = colors.HexColor("#2D3748")
    BG_LIGHT = colors.HexColor("#F7FAFC")
    BORDER_COLOR = colors.HexColor("#E2E8F0")

    styles = getSampleStyleSheet()
    
    # Create custom typography overrides for crisp presentation
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=24,
        leading=28,
        textColor=PRIMARY_COLOR,
        alignment=TA_LEFT,
        spaceAfter=6
    )
    
    subtitle_style = ParagraphStyle(
        'CustomSubtitle',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=12,
        leading=16,
        textColor=SECONDARY_COLOR,
        spaceAfter=20
    )
    
    h2_style = ParagraphStyle(
        'CustomH2',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=14,
        leading=18,
        textColor=PRIMARY_COLOR,
        spaceBefore=14,
        spaceAfter=8,
        keepWithNext=True # Prevents orphan headings at the bottom of pages
    )
    
    body_style = ParagraphStyle(
        'CustomBody',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=10.5,
        leading=15,
        textColor=TEXT_COLOR,
        spaceAfter=10
    )
    
    table_text = ParagraphStyle(
        'TableText',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=9.5,
        leading=12,
        textColor=TEXT_COLOR
    )

    # 3. Build the Document "Story" (Flowable elements stack sequentially)
    story = []
    
    # Header Section
    story.append(Paragraph("Project Architecture Specifications", title_style))
    story.append(Paragraph("System Environment Deployment Profile | June 2026", subtitle_style))
    
    # Thin decorative rule using an empty text block with a border
    story.append(Spacer(1, 10))
    
    # Section 1
    story.append(Paragraph("1. Executive Summary", h2_style))
    story.append(Paragraph(
        "By migrating away from fragile asynchronous network loops and adopting a native, high-tier "
        "typesetting engine, your PDF generation system remains completely robust against external operating "
        "system socket locks. The document layout stream runs fully contained within memory.",
        body_style
    ))
    
    story.append(Spacer(1, 10))
    
    # Section 2: Data Presentation (Beautiful Styled Table)
    story.append(Paragraph("2. Technical Engine Comparison Matrix", h2_style))
    
    table_data = [
        [Paragraph("<b>Engine</b>", table_text), Paragraph("<b>Dependencies</b>", table_text), Paragraph("<b>Visual Quality</b>", table_text)],
        [Paragraph("fpdf2", table_text), Paragraph("None (Pure Python)", table_text), Paragraph("Basic / Raw Text", table_text)],
        [Paragraph("WeasyPrint", table_text), Paragraph("Heavy (GTK+, Pango, C-Libs)", table_text), Paragraph("Excellent (HTML/CSS)", table_text)],
        [Paragraph("ReportLab Core", table_text), Paragraph("None (Pure Python)", table_text), Paragraph("Professional / Tailored", table_text)]
    ]
    
    # 504 points total width available between 0.75-inch margins on letter paper
    metrics_table = Table(table_data, colWidths=[124, 200, 180])
    
    metrics_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), BG_LIGHT),
        ('TEXTCOLOR', (0, 0), (-1, 0), PRIMARY_COLOR),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
        ('LEFTPADDING', (0, 0), (-1, -1), 10),
        ('RIGHTPADDING', (0, 0), (-1, -1), 10),
        ('LINEBELOW', (0, 0), (-1, 0), 1.5, SECONDARY_COLOR),  # Header accent line
        ('LINEBELOW', (0, 1), (-1, -1), 0.5, BORDER_COLOR),     # Row separators
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, BG_LIGHT]) # Clean alternating rows
    ]))
    
    story.append(metrics_table)
    story.append(Spacer(1, 15))
    
    # Section 3
    story.append(Paragraph("3. Layout Capabilities", h2_style))
    story.append(Paragraph(
        "Unlike coordinate-based mapping scripts, the PLATYPUS document flow manager automatically handles "
        "complex calculation properties such as text-wrapping inside structural elements, page boundaries, "
        "multi-column scaling, and paragraph distribution properties gracefully.",
        body_style
    ))
    
    # 4. Compile document elements cleanly 
    print("Compiling ReportLab flowables into polished typography layout...")
    doc.build(story)
    print(f"\nSUCCESS: Beautiful PDF compiled seamlessly at:\n{os.path.abspath(output_filename)}")

if __name__ == "__main__":
    create_beautiful_pdf()