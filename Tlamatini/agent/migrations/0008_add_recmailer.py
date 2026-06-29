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

def add_recmailer_agent(apps, schema_editor):
    Agent = apps.get_model('agent', 'Agent')
    Agent.objects.get_or_create(
        idAgent=17,
        defaults={
            'agentName': 'agent-17',
            'agentDescription': 'Recmailer',
            'agentContent': 'true'
        }
    )

def remove_recmailer_agent(apps, schema_editor):
    Agent = apps.get_model('agent', 'Agent')
    Agent.objects.filter(idAgent=17).delete()

class Migration(migrations.Migration):

    dependencies = [
        ('agent', '0007_add_stopper'),
    ]

    operations = [
        migrations.RunPython(add_recmailer_agent, remove_recmailer_agent),
    ]
