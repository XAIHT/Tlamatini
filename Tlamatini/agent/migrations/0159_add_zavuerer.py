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


def add_zavuerer_agent(apps, schema_editor):
    Agent = apps.get_model('agent', 'Agent')
    if Agent.objects.filter(agentDescription='Zavuerer').exists():
        return
    next_id = (Agent.objects.order_by('-idAgent').values_list('idAgent', flat=True).first() or 0) + 1
    Agent.objects.create(
        idAgent=next_id,
        agentName=f'agent-{next_id}',
        agentDescription='Zavuerer',
        agentContent='true',
    )


def remove_zavuerer_agent(apps, schema_editor):
    Agent = apps.get_model('agent', 'Agent')
    Agent.objects.filter(agentDescription='Zavuerer').delete()


class Migration(migrations.Migration):
    dependencies = [
        ('agent', '0158_redesign_messaging_demo_prompts'),
    ]

    operations = [
        migrations.RunPython(add_zavuerer_agent, remove_zavuerer_agent),
    ]
