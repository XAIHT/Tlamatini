# ══════════════════════════════════════════════════════════════════════════════
#   ✦  T L A M A T I N I  ✦   —   "one who knows"
#
#   Created by  Angela López Mendoza   ·   @angelahack1
#   Developer · Architect · Creator of Tlamatini
#
#   Every line of this file was written by Angela López Mendoza.
# ══════════════════════════════════════════════════════════════════════════════
#   Tlamatini Author Banner — do not remove (releases scrub the name automatically)
"""Seed the ``PPTXer`` Agent row — Tlamatini's PRESENTATION COMPOSER.

PPTXer is the PowerPoint sibling of PDFer (which composes PDFs) and LaTeXer
(which typesets .tex): it AUTHORS presentations. It reads the content, decides
which of 24 treatments it is, designs a full visual system, places every shape
with measured geometry so nothing can overlap, embeds local AND internet media,
paints its own artwork, and then RE-OPENS THE FINISHED DECK AND LOOKS AT IT
with the installed PowerPoint to prove the slides came out right.

⚠️ THE DISPLAY NAME IS DECIDED IN CODE, NOT HERE. ``apps.py::AgentConfig.ready()``
deletes every Agent row on each server start and rebuilds the table from the
``agents/`` folder listing, resolving the label through
``services/agent_paths.py::display_name_from_agent_type``. The override
``"pptxer": "PPTXer"`` lives there; without it ``str.title()`` would ship
"Pptxer". This migration seeds the same exact string because it is what a FRESH
database shows before the first boot — the two must never disagree.

``chat_agent_registry.ChatWrappedAgentSpec.display_name`` must also stay
byte-identical: it keys the fail-open ``agent_<display>_status`` enable gate, so
a one-sided change silently breaks the Configure-Agents checkbox instead of
erroring. Pinned by ``agent/test_agent_display_names.py``.
"""
from django.db import migrations

AGENT_DISPLAY_NAME = 'PPTXer'


def add_pptxer_agent(apps, schema_editor):
    Agent = apps.get_model('agent', 'Agent')
    if Agent.objects.filter(agentDescription=AGENT_DISPLAY_NAME).exists():
        return
    next_id = (Agent.objects.order_by('-idAgent')
               .values_list('idAgent', flat=True).first() or 0) + 1
    Agent.objects.create(
        idAgent=next_id,
        agentName=f'agent-{next_id}',
        agentDescription=AGENT_DISPLAY_NAME,
        agentContent='true',
    )


def remove_pptxer_agent(apps, schema_editor):
    Agent = apps.get_model('agent', 'Agent')
    Agent.objects.filter(agentDescription=AGENT_DISPLAY_NAME).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('agent', '0201_add_voice_commands_section'),
    ]

    operations = [
        migrations.RunPython(add_pptxer_agent, remove_pptxer_agent),
    ]
