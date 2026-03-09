from django.db import migrations


def add_jenkinser_agent(apps, schema_editor):
    Agent = apps.get_model('agent', 'Agent')
    max_id = 0
    for agent in Agent.objects.all():
        if agent.idAgent > max_id:
            max_id = agent.idAgent
    existing = Agent.objects.filter(agentDescription='Jenkinser').first()
    if existing:
        return
    next_id = max_id + 1
    Agent.objects.create(
        idAgent=next_id,
        agentName=f'agent-{next_id}',
        agentDescription='Jenkinser',
        agentContent='true'
    )


def remove_jenkinser_agent(apps, schema_editor):
    Agent = apps.get_model('agent', 'Agent')
    Agent.objects.filter(agentDescription='Jenkinser').delete()


class Migration(migrations.Migration):
    dependencies = [
        ('agent', '0037_add_apirer'),
    ]
    operations = [
        migrations.RunPython(add_jenkinser_agent, remove_jenkinser_agent),
    ]
