# Generated migration to add Deleter agent

from django.db import migrations

def add_deleter_agent(apps, schema_editor):
    """
    Adds the Deleter agent to the Agent model.
    """
    Agent = apps.get_model('agent', 'Agent')
    
    Agent.objects.get_or_create(
        idAgent=13,
        defaults={
            'agentName': 'agent-13',
            'agentDescription': 'Deleter',
            'agentContent': 'true'
        }
    )

def remove_deleter_agent(apps, schema_editor):
    """
    Removes the Deleter agent from the Agent model.
    """
    Agent = apps.get_model('agent', 'Agent')
    Agent.objects.filter(idAgent=13).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('agent', '0003_add_cleaner'),
    ]

    operations = [
        migrations.RunPython(add_deleter_agent, remove_deleter_agent),
    ]
