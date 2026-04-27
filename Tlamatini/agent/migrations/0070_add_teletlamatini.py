from django.db import migrations


def add_teletlamatini_agent(apps, schema_editor):
    Agent = apps.get_model('agent', 'Agent')
    max_id = 0
    for agent in Agent.objects.all():
        if agent.idAgent > max_id:
            max_id = agent.idAgent

    existing = Agent.objects.filter(agentDescription='TeleTlamatini').first()
    if existing:
        return

    next_id = max_id + 1
    Agent.objects.create(
        idAgent=next_id,
        agentName=f'agent-{next_id}',
        agentDescription='TeleTlamatini',
        agentContent='true',
    )


def remove_teletlamatini_agent(apps, schema_editor):
    Agent = apps.get_model('agent', 'Agent')
    Agent.objects.filter(agentDescription='TeleTlamatini').delete()


class Migration(migrations.Migration):
    dependencies = [
        ('agent', '0069_add_googler_agent'),
    ]

    operations = [
        migrations.RunPython(add_teletlamatini_agent, remove_teletlamatini_agent),
    ]
