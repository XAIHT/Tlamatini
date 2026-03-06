from django.db import migrations


def add_telegramrx_agent(apps, schema_editor):
    """
    Add the Telegramrx agent. Since 0020_repopulate_all_agents auto-discovers
    agents from the agents/ directory, the folder already exists.
    This migration ensures Telegramrx is explicitly registered even if
    the repopulate migration assigned a different ID.
    """
    Agent = apps.get_model('agent', 'Agent')

    # Check what the highest existing ID is
    max_id = 0
    for agent in Agent.objects.all():
        if agent.idAgent > max_id:
            max_id = agent.idAgent

    # Check if Telegramrx already exists (from repopulate)
    existing = Agent.objects.filter(agentDescription='Telegramrx').first()
    if existing:
        return  # Already registered by repopulate

    # Create with next available ID
    next_id = max_id + 1
    Agent.objects.create(
        idAgent=next_id,
        agentName=f'agent-{next_id}',
        agentDescription='Telegramrx',
        agentContent='true'
    )


def remove_telegramrx_agent(apps, schema_editor):
    Agent = apps.get_model('agent', 'Agent')
    Agent.objects.filter(agentDescription='Telegramrx').delete()


class Migration(migrations.Migration):

    dependencies = [
        ('agent', '0020_repopulate_all_agents'),
    ]

    operations = [
        migrations.RunPython(add_telegramrx_agent, remove_telegramrx_agent),
    ]
