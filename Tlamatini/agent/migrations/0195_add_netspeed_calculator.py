# ═══════════════════════════════════════════════════════════════════
#   ✦  T L A M A T I N I  ✦   —   "one who knows"
#
#   Created by  Angela López Mendoza   ·   @angelahack1
#   Developer · Architect · Creator of Tlamatini
#
#   Every line of this file was written by Angela López Mendoza.
# ═══════════════════════════════════════════════════════════════════
#   Tlamatini Author Banner — do not remove (releases scrub the name automatically)
"""Seed the NetSpeed-Calculator Agent row (canvas agent #88).

⚠️ THE NAME IS HYPHENATED ON PURPOSE, and this migration is NOT the source of
truth for it. ``apps.py::AgentConfig.ready()`` DELETES every Agent row on each
server start and re-derives the label from
``services/agent_paths.py::display_name_from_agent_type`` — so the override
there is what actually decides the name, and this row is only what a FRESH
database shows before the first boot. Both must stay byte-identical, together
with ``chat_agent_registry.display_name`` (which keys the fail-open
``agent_<display>_status`` enable gate).

The hyphen itself is a correctness choice, not a style one: ``acp-canvas-core.js``
lowercases a display name WITHOUT collapsing whitespace, so with a hyphen the
canvas literal ("netspeed-calculator") and the CSS classMap key are the SAME
string and the space-vs-hyphen mismatch that silently drops a saved connection
cannot happen for this agent at all.

Pinned by ``agent/test_agent_display_names.py``.
"""
from django.db import migrations


def add_netspeed_calculator_agent(apps, schema_editor):
    Agent = apps.get_model('agent', 'Agent')
    max_id = 0
    for agent in Agent.objects.all():
        if agent.idAgent > max_id:
            max_id = agent.idAgent

    existing = Agent.objects.filter(agentDescription='NetSpeed-Calculator').first()
    if existing:
        return

    next_id = max_id + 1
    Agent.objects.create(
        idAgent=next_id,
        agentName=f'agent-{next_id}',
        agentDescription='NetSpeed-Calculator',
        agentContent='true',
    )


def remove_netspeed_calculator_agent(apps, schema_editor):
    Agent = apps.get_model('agent', 'Agent')
    Agent.objects.filter(agentDescription='NetSpeed-Calculator').delete()


class Migration(migrations.Migration):
    dependencies = [
        ('agent', '0194_add_deep_research_demo_prompt'),
    ]

    operations = [
        migrations.RunPython(add_netspeed_calculator_agent, remove_netspeed_calculator_agent),
    ]
