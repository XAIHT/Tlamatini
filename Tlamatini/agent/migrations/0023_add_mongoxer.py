# ═══════════════════════════════════════════════════════════════════
#   ✦  T L A M A T I N I  ✦   —   "one who knows"
#
#   Created by  Angela López Mendoza   ·   @angelahack1
#   Developer · Architect · Creator of Tlamatini
#
#   Every line of this file was written by Angela López Mendoza.
# ═══════════════════════════════════════════════════════════════════
#   Tlamatini Author Banner — do not remove (releases scrub the name automatically)

from django.db import migrations


def add_mongoxer_agent(apps, schema_editor):
    """
    Add the Mongoxer agent.
    """
    Agent = apps.get_model('agent', 'Agent')

    max_id = 0
    for agent in Agent.objects.all():
        if agent.idAgent > max_id:
            max_id = agent.idAgent

    existing = Agent.objects.filter(agentDescription='Mongoxer').first()
    if existing:
        return

    next_id = max_id + 1
    Agent.objects.create(
        idAgent=next_id,
        agentName=f'agent-{next_id}',
        agentDescription='Mongoxer',
        agentContent='true'
    )


def remove_mongoxer_agent(apps, schema_editor):
    Agent = apps.get_model('agent', 'Agent')
    Agent.objects.filter(agentDescription='Mongoxer').delete()


class Migration(migrations.Migration):

    dependencies = [
        ('agent', '0022_repopulate_all_agents'),
    ]

    operations = [
        migrations.RunPython(add_mongoxer_agent, remove_mongoxer_agent),
    ]
