from django.db import migrations


def add_kuberneter_agent(apps, schema_editor):
    Agent = apps.get_model('agent', 'Agent')
    max_id = 0
    for agent in Agent.objects.all():
        if agent.idAgent > max_id:
            max_id = agent.idAgent
    existing = Agent.objects.filter(agentDescription='Kuberneter').first()
    if existing:
        return
    next_id = max_id + 1
    Agent.objects.create(
        idAgent=next_id,
        agentName=f'agent-{next_id}',
        agentDescription='Kuberneter',
        agentContent='true'
    )


def remove_kuberneter_agent(apps, schema_editor):
    Agent = apps.get_model('agent', 'Agent')
    Agent.objects.filter(agentDescription='Kuberneter').delete()


class Migration(migrations.Migration):
    dependencies = [
        ('agent', '0035_add_pser'),
    ]
    operations = [
        migrations.RunPython(add_kuberneter_agent, remove_kuberneter_agent),
    ]
