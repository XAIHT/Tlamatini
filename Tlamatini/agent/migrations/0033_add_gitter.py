from django.db import migrations


def add_gitter_agent(apps, schema_editor):
    Agent = apps.get_model('agent', 'Agent')
    max_id = 0
    for agent in Agent.objects.all():
        if agent.idAgent > max_id:
            max_id = agent.idAgent
    existing = Agent.objects.filter(agentDescription='Gitter').first()
    if existing:
        return
    next_id = max_id + 1
    Agent.objects.create(
        idAgent=next_id,
        agentName=f'agent-{next_id}',
        agentDescription='Gitter',
        agentContent='true'
    )


def remove_gitter_agent(apps, schema_editor):
    Agent = apps.get_model('agent', 'Agent')
    Agent.objects.filter(agentDescription='Gitter').delete()


class Migration(migrations.Migration):
    dependencies = [
        ('agent', '0032_repopulate_all_agents'),
    ]
    operations = [
        migrations.RunPython(add_gitter_agent, remove_gitter_agent),
    ]
