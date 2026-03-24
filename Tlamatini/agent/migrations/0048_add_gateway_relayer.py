from django.db import migrations


def add_gateway_relayer_agent(apps, schema_editor):
    Agent = apps.get_model('agent', 'Agent')
    max_id = 0
    for agent in Agent.objects.all():
        if agent.idAgent > max_id:
            max_id = agent.idAgent
    existing = Agent.objects.filter(agentDescription='GatewayRelayer').first()
    if existing:
        return
    next_id = max_id + 1
    Agent.objects.create(
        idAgent=next_id,
        agentName=f'agent-{next_id}',
        agentDescription='GatewayRelayer',
        agentContent='true'
    )


def remove_gateway_relayer_agent(apps, schema_editor):
    Agent = apps.get_model('agent', 'Agent')
    Agent.objects.filter(agentDescription='GatewayRelayer').delete()


class Migration(migrations.Migration):
    dependencies = [
        ('agent', '0047_add_gatewayer'),
    ]
    operations = [
        migrations.RunPython(add_gateway_relayer_agent, remove_gateway_relayer_agent),
    ]
