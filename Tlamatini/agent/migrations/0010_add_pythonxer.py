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

def add_pythonxer_agent(apps, schema_editor):
    Agent = apps.get_model('agent', 'Agent')
    Agent.objects.get_or_create(
        idAgent=18,
        defaults={
            'agentName': 'agent-18',
            'agentDescription': 'Pythonxer',
            'agentContent': 'true'
        }
    )

def remove_pythonxer_agent(apps, schema_editor):
    Agent = apps.get_model('agent', 'Agent')
    Agent.objects.filter(idAgent=18).delete()

class Migration(migrations.Migration):

    dependencies = [
        ('agent', '0009_add_whatsapper'),
    ]

    operations = [
        migrations.RunPython(add_pythonxer_agent, remove_pythonxer_agent),
    ]
