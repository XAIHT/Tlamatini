from django.db import migrations


def add_stm32er_agent(apps, schema_editor):
    Agent = apps.get_model('agent', 'Agent')
    max_id = 0
    for agent in Agent.objects.all():
        if agent.idAgent > max_id:
            max_id = agent.idAgent

    existing = Agent.objects.filter(agentDescription='STM32er').first()
    if existing:
        return

    next_id = max_id + 1
    Agent.objects.create(
        idAgent=next_id,
        agentName=f'agent-{next_id}',
        agentDescription='STM32er',
        agentContent='true',
    )


def remove_stm32er_agent(apps, schema_editor):
    Agent = apps.get_model('agent', 'Agent')
    Agent.objects.filter(agentDescription='STM32er').delete()


class Migration(migrations.Migration):
    dependencies = [
        ('agent', '0100_add_unrealer_extended_demo_prompts'),
    ]

    operations = [
        migrations.RunPython(add_stm32er_agent, remove_stm32er_agent),
    ]
