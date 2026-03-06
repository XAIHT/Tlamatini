
from django.db import migrations

def add_sqler_agent(apps, schema_editor):
    """
    Add the Sqler agent.
    """
    Agent = apps.get_model('agent', 'Agent')

    max_id = 0
    for agent in Agent.objects.all():
        if agent.idAgent > max_id:
            max_id = agent.idAgent

    existing = Agent.objects.filter(agentDescription='Sqler').first()
    if existing:
        return

    next_id = max_id + 1
    Agent.objects.create(
        idAgent=next_id,
        agentName=f'agent-{next_id}',
        agentDescription='Sqler',
        agentContent='true'
    )


def remove_sqler_agent(apps, schema_editor):
    Agent = apps.get_model('agent', 'Agent')
    Agent.objects.filter(agentDescription='Sqler').delete()


class Migration(migrations.Migration):

    dependencies = [
        ('agent', '0026_repopulate_all_agents'),
    ]

    operations = [
        migrations.RunPython(add_sqler_agent, remove_sqler_agent),
    ]
