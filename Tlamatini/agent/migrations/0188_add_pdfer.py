# ═══════════════════════════════════════════════════════════════════
#   ✦  T L A M A T I N I  ✦   —   "one who knows"
#
#   Created by  Angela López Mendoza   ·   @angelahack1
#   Developer · Architect · Creator of Tlamatini
#
#   Every line of this file was written by Angela López Mendoza.
# ═══════════════════════════════════════════════════════════════════
#   Tlamatini Author Banner — do not remove (releases scrub the name automatically)
"""Seed the PDFer workflow agent (Angela, 2026-07-26).

PDFer is Tlamatini's DOCUMENT COMPOSER — the WRITE side of the document family
(File-Extractor and File-Interpreter READ documents; PDFer AUTHORS them). It turns
Tlamatini's own answer, Markdown, HTML, plain text, images and/or existing PDFs into
ONE styled PDF, with ZERO new dependencies (markdown + xhtml2pdf + PyMuPDF +
reportlab + Pillow + pypdf already ship with Tlamatini).

``agentDescription`` is the SINGLE SOURCE OF TRUTH for the display name and MUST stay
exactly ``PDFer`` — never ``PDFEr`` / ``Pdfer`` / ``PDFER``. Every other surface is a
documented transform of it: the pool dir / CSS class / JS classMap key are ``pdfer``,
the connector symbol is ``updatePdferConnection``, and the protocol token is the
ALL-CAPS ``INI_SECTION_PDFER`` (a separate convention — do NOT "fix" that one).
"""
from django.db import migrations


def add_pdfer_agent(apps, schema_editor):
    Agent = apps.get_model('agent', 'Agent')
    max_id = 0
    for agent in Agent.objects.all():
        if agent.idAgent > max_id:
            max_id = agent.idAgent

    existing = Agent.objects.filter(agentDescription='PDFer').first()
    if existing:
        return

    next_id = max_id + 1
    Agent.objects.create(
        idAgent=next_id,
        agentName=f'agent-{next_id}',
        agentDescription='PDFer',
        agentContent='true',
    )


def remove_pdfer_agent(apps, schema_editor):
    Agent = apps.get_model('agent', 'Agent')
    Agent.objects.filter(agentDescription='PDFer').delete()


class Migration(migrations.Migration):
    dependencies = [
        ('agent', '0187_add_flowcreator_end_to_end_wizard_prompt'),
    ]

    operations = [
        migrations.RunPython(add_pdfer_agent, remove_pdfer_agent),
    ]
