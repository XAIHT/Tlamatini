from django.db import migrations


def add_googler_agent(apps, schema_editor):
    Agent = apps.get_model('agent', 'Agent')
    max_id = 0
    for agent in Agent.objects.all():
        if agent.idAgent > max_id:
            max_id = agent.idAgent

    existing = Agent.objects.filter(agentDescription='Googler').first()
    if existing:
        return

    next_id = max_id + 1
    Agent.objects.create(
        idAgent=next_id,
        agentName=f'agent-{next_id}',
        agentDescription='Googler',
        agentContent='true',
    )


def remove_googler_agent(apps, schema_editor):
    Agent = apps.get_model('agent', 'Agent')
    Agent.objects.filter(agentDescription='Googler').delete()


class Migration(migrations.Migration):
    dependencies = [
        ('agent', '0068_add_googler_tool'),
    ]

    operations = [
        migrations.RunPython(add_googler_agent, remove_googler_agent),
    ]
