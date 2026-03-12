from django.db import migrations


def add_crawler_agent(apps, schema_editor):
    Agent = apps.get_model('agent', 'Agent')
    max_id = 0
    for agent in Agent.objects.all():
        if agent.idAgent > max_id:
            max_id = agent.idAgent
    existing = Agent.objects.filter(agentDescription='Crawler').first()
    if existing:
        return
    next_id = max_id + 1
    Agent.objects.create(
        idAgent=next_id,
        agentName=f'agent-{next_id}',
        agentDescription='Crawler',
        agentContent='true'
    )


def remove_crawler_agent(apps, schema_editor):
    Agent = apps.get_model('agent', 'Agent')
    Agent.objects.filter(agentDescription='Crawler').delete()


class Migration(migrations.Migration):
    dependencies = [
        ('agent', '0038_add_jenkinser'),
    ]
    operations = [
        migrations.RunPython(add_crawler_agent, remove_crawler_agent),
    ]
