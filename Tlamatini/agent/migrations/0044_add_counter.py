from django.db import migrations


def add_counter_agent(apps, schema_editor):
    Agent = apps.get_model('agent', 'Agent')
    max_id = 0
    for agent in Agent.objects.all():
        if agent.idAgent > max_id:
            max_id = agent.idAgent
    existing = Agent.objects.filter(agentDescription='Counter').first()
    if existing:
        return
    next_id = max_id + 1
    Agent.objects.create(
        idAgent=next_id,
        agentName=f'agent-{next_id}',
        agentDescription='Counter',
        agentContent='true'
    )


def remove_counter_agent(apps, schema_editor):
    Agent = apps.get_model('agent', 'Agent')
    Agent.objects.filter(agentDescription='Counter').delete()


class Migration(migrations.Migration):

    dependencies = [
        ('agent', '0043_agentmessage_conversation_user'),
    ]
    operations = [
        migrations.RunPython(add_counter_agent, remove_counter_agent),
    ]
