from django.db import migrations


def add_flowhypervisor_agent(apps, schema_editor):
    Agent = apps.get_model('agent', 'Agent')
    max_id = 0
    for agent in Agent.objects.all():
        if agent.idAgent > max_id:
            max_id = agent.idAgent
    existing = Agent.objects.filter(agentDescription='FlowHypervisor').first()
    if existing:
        return
    next_id = max_id + 1
    Agent.objects.create(
        idAgent=next_id,
        agentName=f'agent-{next_id}',
        agentDescription='FlowHypervisor',
        agentContent='true'
    )


def remove_flowhypervisor_agent(apps, schema_editor):
    Agent = apps.get_model('agent', 'Agent')
    Agent.objects.filter(agentDescription='FlowHypervisor').delete()


class Migration(migrations.Migration):
    dependencies = [
        ('agent', '0040_add_summarizer'),
    ]
    operations = [
        migrations.RunPython(add_flowhypervisor_agent, remove_flowhypervisor_agent),
    ]
