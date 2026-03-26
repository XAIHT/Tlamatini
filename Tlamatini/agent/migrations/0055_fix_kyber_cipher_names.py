from django.db import migrations


def fix_kyber_names(apps, schema_editor):
    Agent = apps.get_model('agent', 'Agent')
    Agent.objects.filter(agentDescription='Kyber-Cypher').update(agentDescription='Kyber-Cipher')
    Agent.objects.filter(agentDescription='Kyber-DeCypher').update(agentDescription='Kyber-DeCipher')


def revert_kyber_names(apps, schema_editor):
    Agent = apps.get_model('agent', 'Agent')
    Agent.objects.filter(agentDescription='Kyber-Cipher').update(agentDescription='Kyber-Cypher')
    Agent.objects.filter(agentDescription='Kyber-DeCipher').update(agentDescription='Kyber-DeCypher')


class Migration(migrations.Migration):
    dependencies = [
        ('agent', '0054_add_kyber_decipher'),
    ]
    operations = [
        migrations.RunPython(fix_kyber_names, revert_kyber_names),
    ]
