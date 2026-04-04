from django.db import migrations


def add_keyboarder_agent(apps, schema_editor):
    Agent = apps.get_model('agent', 'Agent')
    max_id = 0
    for agent in Agent.objects.all():
        if agent.idAgent > max_id:
            max_id = agent.idAgent
    existing = Agent.objects.filter(agentDescription='Keyboarder').first()
    if existing:
        return
    next_id = max_id + 1
    Agent.objects.create(
        idAgent=next_id,
        agentName=f'agent-{next_id}',
        agentDescription='Keyboarder',
        agentContent='true'
    )


def remove_keyboarder_agent(apps, schema_editor):
    Agent = apps.get_model('agent', 'Agent')
    Agent.objects.filter(agentDescription='Keyboarder').delete()


class Migration(migrations.Migration):
    dependencies = [
        ('agent', '0065_add_chat_wrapped_agent_tools'),  
    ]
    operations = [
        migrations.RunPython(add_keyboarder_agent, remove_keyboarder_agent),
    ]
