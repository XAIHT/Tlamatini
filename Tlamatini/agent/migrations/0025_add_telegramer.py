from django.db import migrations


def add_telegramer_agent(apps, schema_editor):
    """
    Add the Telegramer agent. Since repopulate auto-discovers agents from the
    agents/ directory, the folder already exists. This migration ensures
    Telegramer is explicitly registered even if the repopulate migration
    assigned a different ID.
    """
    Agent = apps.get_model('agent', 'Agent')

    # Check what the highest existing ID is
    max_id = 0
    for agent in Agent.objects.all():
        if agent.idAgent > max_id:
            max_id = agent.idAgent

    # Check if Telegramer already exists (from repopulate)
    existing = Agent.objects.filter(agentDescription='Telegramer').first()
    if existing:
        return  # Already registered by repopulate

    # Create with next available ID
    next_id = max_id + 1
    Agent.objects.create(
        idAgent=next_id,
        agentName=f'agent-{next_id}',
        agentDescription='Telegramer',
        agentContent='true'
    )


def remove_telegramer_agent(apps, schema_editor):
    Agent = apps.get_model('agent', 'Agent')
    Agent.objects.filter(agentDescription='Telegramer').delete()


class Migration(migrations.Migration):

    dependencies = [
        ('agent', '0024_repopulate_all_agents'),
    ]

    operations = [
        migrations.RunPython(add_telegramer_agent, remove_telegramer_agent),
    ]
