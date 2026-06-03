from django.db import migrations


def add_arduiner_agent(apps, schema_editor):
    Agent = apps.get_model('agent', 'Agent')
    max_id = 0
    for agent in Agent.objects.all():
        if agent.idAgent > max_id:
            max_id = agent.idAgent

    existing = Agent.objects.filter(agentDescription='Arduiner').first()
    if existing:
        return

    next_id = max_id + 1
    Agent.objects.create(
        idAgent=next_id,
        agentName=f'agent-{next_id}',
        agentDescription='Arduiner',
        agentContent='true',
    )


def remove_arduiner_agent(apps, schema_editor):
    Agent = apps.get_model('agent', 'Agent')
    Agent.objects.filter(agentDescription='Arduiner').delete()


class Migration(migrations.Migration):
    dependencies = [
        ('agent', '0108_add_flow_making_demo_prompt'),
    ]

    operations = [
        migrations.RunPython(add_arduiner_agent, remove_arduiner_agent),
    ]
