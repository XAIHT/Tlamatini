from django.db import migrations

def add_whatsapper_agent(apps, schema_editor):
    Agent = apps.get_model('agent', 'Agent')
    Agent.objects.get_or_create(
        idAgent=13,
        defaults={
            'agentName': 'agent-13',
            'agentDescription': 'Whatsapper',
            'agentContent': 'true'
        }
    )

def remove_whatsapper_agent(apps, schema_editor):
    Agent = apps.get_model('agent', 'Agent')
    Agent.objects.filter(idAgent=13).delete()

class Migration(migrations.Migration):

    dependencies = [
        ('agent', '0008_add_recmailer'),
    ]

    operations = [
        migrations.RunPython(add_whatsapper_agent, remove_whatsapper_agent),
    ]
