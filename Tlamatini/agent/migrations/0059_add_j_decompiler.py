from django.db import migrations


def add_j_decompiler_agent(apps, schema_editor):
    Agent = apps.get_model('agent', 'Agent')
    max_id = 0
    for agent in Agent.objects.all():
        if agent.idAgent > max_id:
            max_id = agent.idAgent
    existing = Agent.objects.filter(agentDescription='J-Decompiler').first()
    if existing:
        return
    next_id = max_id + 1
    Agent.objects.create(
        idAgent=next_id,
        agentName=f'agent-{next_id}',
        agentDescription='J-Decompiler',
        agentContent='true'
    )


def remove_j_decompiler_agent(apps, schema_editor):
    Agent = apps.get_model('agent', 'Agent')
    Agent.objects.filter(agentDescription='J-Decompiler').delete()


class Migration(migrations.Migration):
    dependencies = [
        ('agent', '0058_add_barrier'),
    ]
    operations = [
        migrations.RunPython(add_j_decompiler_agent, remove_j_decompiler_agent),
    ]
