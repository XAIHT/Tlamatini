from django.db import migrations


def add_pser_agent(apps, schema_editor):
    Agent = apps.get_model('agent', 'Agent')
    max_id = 0
    for agent in Agent.objects.all():
        if agent.idAgent > max_id:
            max_id = agent.idAgent
    existing = Agent.objects.filter(agentDescription='Pser').first()
    if existing:
        return
    next_id = max_id + 1
    Agent.objects.create(
        idAgent=next_id,
        agentName=f'agent-{next_id}',
        agentDescription='Pser',
        agentContent='true'
    )


def remove_pser_agent(apps, schema_editor):
    Agent = apps.get_model('agent', 'Agent')
    Agent.objects.filter(agentDescription='Pser').delete()


class Migration(migrations.Migration):
    dependencies = [
        ('agent', '0034_add_dockerer'),
    ]
    operations = [
        migrations.RunPython(add_pser_agent, remove_pser_agent),
    ]
