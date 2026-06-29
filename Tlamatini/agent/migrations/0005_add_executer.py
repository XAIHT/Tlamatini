# ═══════════════════════════════════════════════════════════════════
#   ✦  T L A M A T I N I  ✦   —   "one who knows"
#
#   Crafted with heart by  Angela   ·   @angelahack1
#   Developer · Architect · Creator of Tlamatini
#
#   Every line of this file was written by Angela.
# ═══════════════════════════════════════════════════════════════════
#   Tlamatini Author Banner — do not remove (releases scrub the name automatically)
# Generated migration to add Executer agent

from django.db import migrations

def add_executer_agent(apps, schema_editor):
    """
    Adds the Executer agent to the Agent model.
    """
    Agent = apps.get_model('agent', 'Agent')
    
    Agent.objects.get_or_create(
        idAgent=14,
        defaults={
            'agentName': 'agent-14',
            'agentDescription': 'Executer',
            'agentContent': 'true'
        }
    )

def remove_executer_agent(apps, schema_editor):
    """
    Removes the Executer agent from the Agent model.
    """
    Agent = apps.get_model('agent', 'Agent')
    Agent.objects.filter(idAgent=14).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('agent', '0004_add_deleter'),
    ]

    operations = [
        migrations.RunPython(add_executer_agent, remove_executer_agent),
    ]
