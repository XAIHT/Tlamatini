from django.db import migrations


def add_whatstlamatini_agent(apps, schema_editor):
    Agent = apps.get_model('agent', 'Agent')
    max_id = 0
    for agent in Agent.objects.all():
        if agent.idAgent > max_id:
            max_id = agent.idAgent

    existing = Agent.objects.filter(agentDescription='WhatsTlamatini').first()
    if existing:
        return

    next_id = max_id + 1
    Agent.objects.create(
        idAgent=next_id,
        agentName=f'agent-{next_id}',
        agentDescription='WhatsTlamatini',
        agentContent='true',
    )


def remove_whatstlamatini_agent(apps, schema_editor):
    Agent = apps.get_model('agent', 'Agent')
    Agent.objects.filter(agentDescription='WhatsTlamatini').delete()


class Migration(migrations.Migration):
    dependencies = [
        ('agent', '0076_add_acpxer'),
    ]

    operations = [
        migrations.RunPython(add_whatstlamatini_agent, remove_whatstlamatini_agent),
    ]
