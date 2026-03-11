from django.db import migrations


def add_summarizer_agent(apps, schema_editor):
    Agent = apps.get_model('agent', 'Agent')
    max_id = 0
    for agent in Agent.objects.all():
        if agent.idAgent > max_id:
            max_id = agent.idAgent
    existing = Agent.objects.filter(agentDescription='Summarizer').first()
    if existing:
        return
    next_id = max_id + 1
    Agent.objects.create(
        idAgent=next_id,
        agentName=f'agent-{next_id}',
        agentDescription='Summarizer',
        agentContent='true'
    )


def remove_summarizer_agent(apps, schema_editor):
    Agent = apps.get_model('agent', 'Agent')
    Agent.objects.filter(agentDescription='Summarizer').delete()


class Migration(migrations.Migration):
    dependencies = [
        ('agent', '0039_add_crawler'),
    ]
    operations = [
        migrations.RunPython(add_summarizer_agent, remove_summarizer_agent),
    ]
