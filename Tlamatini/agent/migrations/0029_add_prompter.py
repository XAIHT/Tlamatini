
from django.db import migrations

def add_prompter_agent(apps, schema_editor):
    """
    Add the Prompter agent.
    """
    Agent = apps.get_model('agent', 'Agent')

    max_id = 0
    for agent in Agent.objects.all():
        if agent.idAgent > max_id:
            max_id = agent.idAgent

    existing = Agent.objects.filter(agentDescription='Prompter').first()
    if existing:
        return

    next_id = max_id + 1
    Agent.objects.create(
        idAgent=next_id,
        agentName=f'agent-{next_id}',
        agentDescription='Prompter',
        agentContent='true'
    )


def remove_prompter_agent(apps, schema_editor):
    Agent = apps.get_model('agent', 'Agent')
    Agent.objects.filter(agentDescription='Prompter').delete()


class Migration(migrations.Migration):

    dependencies = [
        ('agent', '0028_repopulate_all_agents'),
    ]

    operations = [
        migrations.RunPython(add_prompter_agent, remove_prompter_agent),
    ]
