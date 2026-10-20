# ═══════════════════════════════════════════════════════════════════════════════
#   ✦  T L A M A T I N I  ✦   —   "one who knows"
#
#   Created by  Angela López Mendoza   ·   @angelahack1
#   Developer · Architect · Creator of Tlamatini
#
#   Every line of this file was written by Angela López Mendoza.
# ═══════════════════════════════════════════════════════════════════════════════
#   Tlamatini Author Banner — do not remove (releases scrub the name automatically)
"""Seed the ``Terminater`` Agent row — VISIBLE, USER-SUPERVISED TERMINALS.

Terminater raises real cmd.exe / PowerShell terminals inside Tlamatini's
Terminals area, types into them like a person (never a paste), reads every
result in full, detects and aborts hung commands, hands part of a command to the
user, watches what the user types in real time and warns about dangerous or
mistyped commands.  It is the visible, supervised sibling of Executer.

⚠️ THE DISPLAY NAME IS DECIDED IN CODE, NOT HERE. ``apps.py::AgentConfig.ready()``
deletes every Agent row on each server start and rebuilds the table from the
``agents/`` folder listing, resolving the label through
``services/agent_paths.py::display_name_from_agent_type`` (``"terminater":
"Terminater"``).  This migration seeds the same exact string because it is what
a FRESH database shows before the first boot — the two must never disagree.
``chat_agent_registry.ChatWrappedAgentSpec.display_name`` must stay
byte-identical too (it keys the fail-open ``agent_<display>_status`` gate).
Pinned by ``agent/test_agent_display_names.py``.
"""
from django.db import migrations

AGENT_DISPLAY_NAME = 'Terminater'


def add_terminater_agent(apps, schema_editor):
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


def remove_terminater_agent(apps, schema_editor):
    Agent = apps.get_model('agent', 'Agent')
    Agent.objects.filter(agentDescription=AGENT_DISPLAY_NAME).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('agent', '0214_prune_agent_catalog'),
    ]

    operations = [
        migrations.RunPython(add_terminater_agent, remove_terminater_agent),
    ]
