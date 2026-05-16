from django.db import migrations


def add_de_compresser_agent(apps, schema_editor):
    Agent = apps.get_model('agent', 'Agent')
    max_id = 0
    for agent in Agent.objects.all():
        if agent.idAgent > max_id:
            max_id = agent.idAgent

    existing = Agent.objects.filter(agentDescription='De-Compresser').first()
    if existing:
        return

    next_id = max_id + 1
    Agent.objects.create(
        idAgent=next_id,
        agentName=f'agent-{next_id}',
        agentDescription='De-Compresser',
        agentContent='true',
    )


def remove_de_compresser_agent(apps, schema_editor):
    Agent = apps.get_model('agent', 'Agent')
    Agent.objects.filter(agentDescription='De-Compresser').delete()


class Migration(migrations.Migration):
    dependencies = [
        ('agent', '0082_add_chat_agent_j_decompiler_tool'),
    ]

    operations = [
        migrations.RunPython(add_de_compresser_agent, remove_de_compresser_agent),
    ]
