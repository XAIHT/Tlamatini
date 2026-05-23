from django.db import migrations


def add_kalier_agent(apps, schema_editor):
    Agent = apps.get_model('agent', 'Agent')
    max_id = 0
    for agent in Agent.objects.all():
        if agent.idAgent > max_id:
            max_id = agent.idAgent

    existing = Agent.objects.filter(agentDescription='Kalier').first()
    if existing:
        return

    next_id = max_id + 1
    Agent.objects.create(
        idAgent=next_id,
        agentName=f'agent-{next_id}',
        agentDescription='Kalier',
        agentContent='true',
    )


def remove_kalier_agent(apps, schema_editor):
    Agent = apps.get_model('agent', 'Agent')
    Agent.objects.filter(agentDescription='Kalier').delete()


class Migration(migrations.Migration):
    dependencies = [
        ('agent', '0096_add_director_virtuoso_demo_prompts'),
    ]

    operations = [
        migrations.RunPython(add_kalier_agent, remove_kalier_agent),
    ]
