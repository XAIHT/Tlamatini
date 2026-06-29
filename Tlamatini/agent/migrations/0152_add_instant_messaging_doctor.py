# ═══════════════════════════════════════════════════════════════════
#   ✦  T L A M A T I N I  ✦   —   "one who knows"
#
#   Crafted with heart by  Angela   ·   @angelahack1
#   Developer · Architect · Creator of Tlamatini
#
#   Every line of this file was written by Angela.
# ═══════════════════════════════════════════════════════════════════
#   Tlamatini Author Banner — do not remove (releases scrub the name automatically)
from django.db import migrations


def add_instant_messaging_doctor_agent(apps, schema_editor):
    Agent = apps.get_model('agent', 'Agent')
    if Agent.objects.filter(agentDescription='Instant Messaging Doctor').exists():
        return
    next_id = (Agent.objects.order_by('-idAgent').values_list('idAgent', flat=True).first() or 0) + 1
    Agent.objects.create(
        idAgent=next_id,
        agentName=f'agent-{next_id}',
        agentDescription='Instant Messaging Doctor',
        agentContent='true',
    )


def remove_instant_messaging_doctor_agent(apps, schema_editor):
    Agent = apps.get_model('agent', 'Agent')
    Agent.objects.filter(agentDescription='Instant Messaging Doctor').delete()


class Migration(migrations.Migration):
    dependencies = [
        ('agent', '0151_retire_old_messaging_add_telegrammer'),
    ]

    operations = [
        migrations.RunPython(add_instant_messaging_doctor_agent, remove_instant_messaging_doctor_agent),
    ]
