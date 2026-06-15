from django.db import migrations


def add_editor_agent(apps, schema_editor):
    Agent = apps.get_model('agent', 'Agent')
    max_id = 0
    for agent in Agent.objects.all():
        if agent.idAgent > max_id:
            max_id = agent.idAgent

    existing = Agent.objects.filter(agentDescription='Editor').first()
    if existing:
        return

    next_id = max_id + 1
    Agent.objects.create(
        idAgent=next_id,
        agentName=f'agent-{next_id}',
        agentDescription='Editor',
        agentContent='true',
    )


def remove_editor_agent(apps, schema_editor):
    Agent = apps.get_model('agent', 'Agent')
    Agent.objects.filter(agentDescription='Editor').delete()


class Migration(migrations.Migration):
    dependencies = [
        ('agent', '0128_add_blenderer_demo_prompts'),
    ]

    operations = [
        migrations.RunPython(add_editor_agent, remove_editor_agent),
    ]
