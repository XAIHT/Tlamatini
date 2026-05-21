from django.db import migrations


def add_windower_agent(apps, schema_editor):
    Agent = apps.get_model('agent', 'Agent')
    max_id = 0
    for agent in Agent.objects.all():
        if agent.idAgent > max_id:
            max_id = agent.idAgent

    existing = Agent.objects.filter(agentDescription='Windower').first()
    if existing:
        return

    next_id = max_id + 1
    Agent.objects.create(
        idAgent=next_id,
        agentName=f'agent-{next_id}',
        agentDescription='Windower',
        agentContent='true',
    )


def remove_windower_agent(apps, schema_editor):
    Agent = apps.get_model('agent', 'Agent')
    Agent.objects.filter(agentDescription='Windower').delete()


class Migration(migrations.Migration):
    dependencies = [
        ('agent', '0092_add_chat_agent_playwrighter_tool'),
    ]

    operations = [
        migrations.RunPython(add_windower_agent, remove_windower_agent),
    ]
