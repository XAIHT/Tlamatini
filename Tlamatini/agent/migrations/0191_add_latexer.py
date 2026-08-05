# ═══════════════════════════════════════════════════════════════════
#   ✦  T L A M A T I N I  ✦   —   "one who knows"
#
#   Created by  Angela López Mendoza   ·   @angelahack1
#   Developer · Architect · Creator of Tlamatini
#
#   Every line of this file was written by Angela López Mendoza.
# ═══════════════════════════════════════════════════════════════════
#   Tlamatini Author Banner — do not remove (releases scrub the name automatically)
"""Seed the LaTeXer workflow agent (Angela, 2026-08-05).

LaTeXer is Tlamatini's LaTeX TYPESETTING agent — the typesetting sibling of PDFer
(PDFer COMPOSES a PDF from Markdown/HTML/images; LaTeXer TYPESETS one from .tex
source, with real mathematics, bibliographies, cross-references and an index). It
embeds the complete capability surface of the `mcp-latex-server` MCP natively, as an
agent, with no MCP server, no sidecar and no new dependency — plus whole-PROJECT
compilation, a BibTeX/Biber + makeindex convergence loop and readable LaTeX-log
diagnostics on top.

⚠️ ``agentDescription`` here is only what a FRESH database shows before the first
boot. ``apps.py::AgentConfig.ready()`` DELETES every Agent row on each server start
and re-derives the name from ``services/agent_paths.py::display_name_from_agent_type``
— so the override ``"latexer": "LaTeXer"`` in THAT map is the real source of truth,
and it is what stops ``str.title()`` from shipping this agent as "Latexer". Both must
say exactly ``LaTeXer`` (L-a-T-e-X-e-r), and so must
``chat_agent_registry.display_name`` (it keys the fail-open ``agent_<display>_status``
enable gate). Every other surface is a documented transform: the pool dir / CSS class
/ JS classMap key are ``latexer``, the connector symbol is ``updateLatexerConnection``,
and the protocol token is the ALL-CAPS ``INI_SECTION_LATEXER`` (a separate convention
— do NOT "fix" that one).
"""
from django.db import migrations


def add_latexer_agent(apps, schema_editor):
    Agent = apps.get_model('agent', 'Agent')
    max_id = 0
    for agent in Agent.objects.all():
        if agent.idAgent > max_id:
            max_id = agent.idAgent

    existing = Agent.objects.filter(agentDescription='LaTeXer').first()
    if existing:
        return

    next_id = max_id + 1
    Agent.objects.create(
        idAgent=next_id,
        agentName=f'agent-{next_id}',
        agentDescription='LaTeXer',
        agentContent='true',
    )


def remove_latexer_agent(apps, schema_editor):
    Agent = apps.get_model('agent', 'Agent')
    Agent.objects.filter(agentDescription='LaTeXer').delete()


class Migration(migrations.Migration):
    dependencies = [
        ('agent', '0190_add_pdfer_demo_prompts'),
    ]

    operations = [
        migrations.RunPython(add_latexer_agent, remove_latexer_agent),
    ]
