from django.db import migrations


def add_kyber_decipher_agent(apps, schema_editor):
    Agent = apps.get_model('agent', 'Agent')
    max_id = 0
    for agent in Agent.objects.all():
        if agent.idAgent > max_id:
            max_id = agent.idAgent
    existing = Agent.objects.filter(agentDescription='Kyber-DeCipher').first()
    if existing:
        return
    next_id = max_id + 1
    Agent.objects.create(
        idAgent=next_id,
        agentName=f'agent-{next_id}',
        agentDescription='Kyber-DeCipher',
        agentContent='true'
    )


def remove_kyber_decipher_agent(apps, schema_editor):
    Agent = apps.get_model('agent', 'Agent')
    Agent.objects.filter(agentDescription='Kyber-DeCipher').delete()


class Migration(migrations.Migration):
    dependencies = [
        ('agent', '0053_add_kyber_cipher'),
    ]
    operations = [
        migrations.RunPython(add_kyber_decipher_agent, remove_kyber_decipher_agent),
    ]
