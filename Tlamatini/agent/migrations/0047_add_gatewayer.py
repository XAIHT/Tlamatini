from django.db import migrations


def add_gatewayer_agent(apps, schema_editor):
    Agent = apps.get_model('agent', 'Agent')
    max_id = 0
    for agent in Agent.objects.all():
        if agent.idAgent > max_id:
            max_id = agent.idAgent
    existing = Agent.objects.filter(agentDescription='Gatewayer').first()
    if existing:
        return
    next_id = max_id + 1
    Agent.objects.create(
        idAgent=next_id,
        agentName=f'agent-{next_id}',
        agentDescription='Gatewayer',
        agentContent='true'
    )


def remove_gatewayer_agent(apps, schema_editor):
    Agent = apps.get_model('agent', 'Agent')
    Agent.objects.filter(agentDescription='Gatewayer').delete()


class Migration(migrations.Migration):
    dependencies = [
        ('agent', '0046_add_image_interpreter'),
    ]
    operations = [
        migrations.RunPython(add_gatewayer_agent, remove_gatewayer_agent),
    ]
