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

def add_notifier_agent(apps, schema_editor):
    Agent = apps.get_model('agent', 'Agent')
    Agent.objects.get_or_create(
        idAgent=15,
        defaults={
            'agentName': 'agent-15',
            'agentDescription': 'Notifier',
            'agentContent': 'true'
        }
    )

def remove_notifier_agent(apps, schema_editor):
    Agent = apps.get_model('agent', 'Agent')
    Agent.objects.filter(idAgent=15).delete()

class Migration(migrations.Migration):

    dependencies = [
        ('agent', '0005_add_executer'),
    ]

    operations = [
        migrations.RunPython(add_notifier_agent, remove_notifier_agent),
    ]
