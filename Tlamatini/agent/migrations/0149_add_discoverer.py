from django.db import migrations


def add_discoverer_agent(apps, schema_editor):
    Agent = apps.get_model('agent', 'Agent')
    if Agent.objects.filter(agentDescription='Discoverer').exists():
        return
    max_id = 0
    for agent in Agent.objects.all():
        if agent.idAgent > max_id:
            max_id = agent.idAgent
    next_id = max_id + 1
    Agent.objects.create(
        idAgent=next_id,
        agentName=f'agent-{next_id}',
        agentDescription='Discoverer',
        agentContent='true',
    )


def remove_discoverer_agent(apps, schema_editor):
    Agent = apps.get_model('agent', 'Agent')
    Agent.objects.filter(agentDescription='Discoverer').delete()


class Migration(migrations.Migration):
    dependencies = [
        ('agent', '0148_add_discoverer_demo_prompts'),
    ]
    operations = [
        migrations.RunPython(add_discoverer_agent, remove_discoverer_agent),
    ]
