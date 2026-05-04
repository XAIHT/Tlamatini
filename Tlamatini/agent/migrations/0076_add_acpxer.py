from django.db import migrations


def add_acpxer_agent(apps, schema_editor):
    Agent = apps.get_model('agent', 'Agent')
    max_id = 0
    for agent in Agent.objects.all():
        if agent.idAgent > max_id:
            max_id = agent.idAgent

    existing = Agent.objects.filter(agentDescription='ACPXer').first()
    if existing:
        return

    next_id = max_id + 1
    Agent.objects.create(
        idAgent=next_id,
        agentName=f'agent-{next_id}',
        agentDescription='ACPXer',
        agentContent='true',
    )


def remove_acpxer_agent(apps, schema_editor):
    Agent = apps.get_model('agent', 'Agent')
    Agent.objects.filter(agentDescription='ACPXer').delete()


class Migration(migrations.Migration):
    dependencies = [
        ('agent', '0075_add_acpx_tool_surface'),
    ]

    operations = [
        migrations.RunPython(add_acpxer_agent, remove_acpxer_agent),
    ]
