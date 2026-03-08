from django.db import migrations


def add_dockerer_agent(apps, schema_editor):
    Agent = apps.get_model('agent', 'Agent')
    max_id = 0
    for agent in Agent.objects.all():
        if agent.idAgent > max_id:
            max_id = agent.idAgent
    existing = Agent.objects.filter(agentDescription='Dockerer').first()
    if existing:
        return
    next_id = max_id + 1
    Agent.objects.create(
        idAgent=next_id,
        agentName=f'agent-{next_id}',
        agentDescription='Dockerer',
        agentContent='true'
    )


def remove_dockerer_agent(apps, schema_editor):
    Agent = apps.get_model('agent', 'Agent')
    Agent.objects.filter(agentDescription='Dockerer').delete()


class Migration(migrations.Migration):
    dependencies = [
        ('agent', '0033_add_gitter'),
    ]
    operations = [
        migrations.RunPython(add_dockerer_agent, remove_dockerer_agent),
    ]
