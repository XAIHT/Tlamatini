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

def add_stopper_agent(apps, schema_editor):
    Agent = apps.get_model('agent', 'Agent')
    Agent.objects.get_or_create(
        idAgent=16,
        defaults={
            'agentName': 'agent-16',
            'agentDescription': 'Stopper',
            'agentContent': 'true'
        }
    )

def remove_stopper_agent(apps, schema_editor):
    Agent = apps.get_model('agent', 'Agent')
    Agent.objects.filter(idAgent=16).delete()

class Migration(migrations.Migration):

    dependencies = [
        ('agent', '0006_add_notifier'),
    ]

    operations = [
        migrations.RunPython(add_stopper_agent, remove_stopper_agent),
    ]
