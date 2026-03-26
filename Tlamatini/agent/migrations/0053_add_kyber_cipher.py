from django.db import migrations


def add_kyber_cipher_agent(apps, schema_editor):
    Agent = apps.get_model('agent', 'Agent')
    max_id = 0
    for agent in Agent.objects.all():
        if agent.idAgent > max_id:
            max_id = agent.idAgent
    existing = Agent.objects.filter(agentDescription='Kyber-Cipher').first()
    if existing:
        return
    next_id = max_id + 1
    Agent.objects.create(
        idAgent=next_id,
        agentName=f'agent-{next_id}',
        agentDescription='Kyber-Cipher',
        agentContent='true'
    )


def remove_kyber_cipher_agent(apps, schema_editor):
    Agent = apps.get_model('agent', 'Agent')
    Agent.objects.filter(agentDescription='Kyber-Cipher').delete()


class Migration(migrations.Migration):
    dependencies = [
        ('agent', '0052_add_kyber_keygen'),
    ]
    operations = [
        migrations.RunPython(add_kyber_cipher_agent, remove_kyber_cipher_agent),
    ]
