from django.db import migrations


def add_parametrizer_agent(apps, schema_editor):
    Agent = apps.get_model('agent', 'Agent')
    max_id = 0
    for agent in Agent.objects.all():
        if agent.idAgent > max_id:
            max_id = agent.idAgent
    existing = Agent.objects.filter(agentDescription='Parametrizer').first()
    if existing:
        return
    next_id = max_id + 1
    Agent.objects.create(
        idAgent=next_id,
        agentName=f'agent-{next_id}',
        agentDescription='Parametrizer',
        agentContent='true'
    )


def remove_parametrizer_agent(apps, schema_editor):
    Agent = apps.get_model('agent', 'Agent')
    Agent.objects.filter(agentDescription='Parametrizer').delete()


class Migration(migrations.Migration):
    dependencies = [
        ('agent', '0055_fix_kyber_cipher_names'),
    ]
    operations = [
        migrations.RunPython(add_parametrizer_agent, remove_parametrizer_agent),
    ]
