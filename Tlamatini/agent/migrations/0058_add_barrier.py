from django.db import migrations


def add_barrier_agent(apps, schema_editor):
    Agent = apps.get_model('agent', 'Agent')
    max_id = 0
    for agent in Agent.objects.all():
        if agent.idAgent > max_id:
            max_id = agent.idAgent
    existing = Agent.objects.filter(agentDescription='Barrier').first()
    if existing:
        return
    next_id = max_id + 1
    Agent.objects.create(
        idAgent=next_id,
        agentName=f'agent-{next_id}',
        agentDescription='Barrier',
        agentContent='true'
    )


def remove_barrier_agent(apps, schema_editor):
    Agent = apps.get_model('agent', 'Agent')
    Agent.objects.filter(agentDescription='Barrier').delete()


class Migration(migrations.Migration):
    dependencies = [
        ('agent', '0057_add_flowbacker'),
    ]
    operations = [
        migrations.RunPython(add_barrier_agent, remove_barrier_agent),
    ]
