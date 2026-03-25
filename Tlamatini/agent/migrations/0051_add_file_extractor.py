from django.db import migrations


def add_file_extractor_agent(apps, schema_editor):
    Agent = apps.get_model('agent', 'Agent')
    max_id = 0
    for agent in Agent.objects.all():
        if agent.idAgent > max_id:
            max_id = agent.idAgent
    existing = Agent.objects.filter(agentDescription='File-Extractor').first()
    if existing:
        return
    next_id = max_id + 1
    Agent.objects.create(
        idAgent=next_id,
        agentName=f'agent-{next_id}',
        agentDescription='File-Extractor',
        agentContent='true'
    )


def remove_file_extractor_agent(apps, schema_editor):
    Agent = apps.get_model('agent', 'Agent')
    Agent.objects.filter(agentDescription='File-Extractor').delete()


class Migration(migrations.Migration):
    dependencies = [
        ('agent', '0050_add_file_creator'),
    ]
    operations = [
        migrations.RunPython(add_file_extractor_agent, remove_file_extractor_agent),
    ]
