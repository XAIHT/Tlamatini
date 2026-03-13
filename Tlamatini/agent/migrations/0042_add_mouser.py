from django.db import migrations


def add_mouser_agent(apps, schema_editor):
    Agent = apps.get_model('agent', 'Agent')
    max_id = 0
    for agent in Agent.objects.all():
        if agent.idAgent > max_id:
            max_id = agent.idAgent
    existing = Agent.objects.filter(agentDescription='Mouser').first()
    if existing:
        return
    next_id = max_id + 1
    Agent.objects.create(
        idAgent=next_id,
        agentName=f'agent-{next_id}',
        agentDescription='Mouser',
        agentContent='true'
    )


def remove_mouser_agent(apps, schema_editor):
    Agent = apps.get_model('agent', 'Agent')
    Agent.objects.filter(agentDescription='Mouser').delete()


class Migration(migrations.Migration):
    dependencies = [
        ('agent', '0041_add_flowhypervisor'),
    ]
    operations = [
        migrations.RunPython(add_mouser_agent, remove_mouser_agent),
    ]
