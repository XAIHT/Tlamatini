from django.db import migrations


def add_node_manager_agent(apps, schema_editor):
    Agent = apps.get_model('agent', 'Agent')
    max_id = 0
    for agent in Agent.objects.all():
        if agent.idAgent > max_id:
            max_id = agent.idAgent
    existing = Agent.objects.filter(agentDescription='NodeManager').first()
    if existing:
        return
    next_id = max_id + 1
    Agent.objects.create(
        idAgent=next_id,
        agentName=f'agent-{next_id}',
        agentDescription='NodeManager',
        agentContent='true'
    )


def remove_node_manager_agent(apps, schema_editor):
    Agent = apps.get_model('agent', 'Agent')
    Agent.objects.filter(agentDescription='NodeManager').delete()


class Migration(migrations.Migration):
    dependencies = [
        ('agent', '0048_add_gateway_relayer'),
    ]
    operations = [
        migrations.RunPython(add_node_manager_agent, remove_node_manager_agent),
    ]
