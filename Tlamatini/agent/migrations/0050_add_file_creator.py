from django.db import migrations


def add_file_creator_agent(apps, schema_editor):
    Agent = apps.get_model('agent', 'Agent')
    max_id = 0
    for agent in Agent.objects.all():
        if agent.idAgent > max_id:
            max_id = agent.idAgent
    existing = Agent.objects.filter(agentDescription='File-Creator').first()
    if existing:
        return
    next_id = max_id + 1
    Agent.objects.create(
        idAgent=next_id,
        agentName=f'agent-{next_id}',
        agentDescription='File-Creator',
        agentContent='true'
    )


def remove_file_creator_agent(apps, schema_editor):
    Agent = apps.get_model('agent', 'Agent')
    Agent.objects.filter(agentDescription='File-Creator').delete()


class Migration(migrations.Migration):
    dependencies = [
        ('agent', '0049_add_node_manager'),
    ]
    operations = [
        migrations.RunPython(add_file_creator_agent, remove_file_creator_agent),
    ]
