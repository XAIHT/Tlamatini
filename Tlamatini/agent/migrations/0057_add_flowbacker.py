from django.db import migrations


def add_flowbacker_agent(apps, schema_editor):
    Agent = apps.get_model('agent', 'Agent')
    max_id = 0
    for agent in Agent.objects.all():
        if agent.idAgent > max_id:
            max_id = agent.idAgent
    existing = Agent.objects.filter(agentDescription='FlowBacker').first()
    if existing:
        return
    next_id = max_id + 1
    Agent.objects.create(
        idAgent=next_id,
        agentName=f'agent-{next_id}',
        agentDescription='FlowBacker',
        agentContent='true'
    )


def remove_flowbacker_agent(apps, schema_editor):
    Agent = apps.get_model('agent', 'Agent')
    Agent.objects.filter(agentDescription='FlowBacker').delete()


class Migration(migrations.Migration):
    dependencies = [
        ('agent', '0056_add_parametrizer'),
    ]
    operations = [
        migrations.RunPython(add_flowbacker_agent, remove_flowbacker_agent),
    ]
