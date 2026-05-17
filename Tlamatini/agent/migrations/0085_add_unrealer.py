from django.db import migrations


def add_unrealer_agent(apps, schema_editor):
    Agent = apps.get_model('agent', 'Agent')
    max_id = 0
    for agent in Agent.objects.all():
        if agent.idAgent > max_id:
            max_id = agent.idAgent

    existing = Agent.objects.filter(agentDescription='Unrealer').first()
    if existing:
        return

    next_id = max_id + 1
    Agent.objects.create(
        idAgent=next_id,
        agentName=f'agent-{next_id}',
        agentDescription='Unrealer',
        agentContent='true',
    )


def remove_unrealer_agent(apps, schema_editor):
    Agent = apps.get_model('agent', 'Agent')
    Agent.objects.filter(agentDescription='Unrealer').delete()


class Migration(migrations.Migration):
    dependencies = [
        ('agent', '0084_add_chat_agent_de_compresser_tool'),
    ]

    operations = [
        migrations.RunPython(add_unrealer_agent, remove_unrealer_agent),
    ]
