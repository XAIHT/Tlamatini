from django.db import migrations

def add_cleaner_agent(apps, schema_editor):
    Agent = apps.get_model('agent', 'Agent')
    Agent.objects.get_or_create(
        idAgent=12,
        defaults={
            'agentName': 'agent-12',
            'agentDescription': 'Cleaner',
            'agentContent': 'true'
        }
    )

class Migration(migrations.Migration):

    dependencies = [
        ('agent', '0002_populate_db'),
    ]

    operations = [
        migrations.RunPython(add_cleaner_agent),
    ]
