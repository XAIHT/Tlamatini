from django.db import migrations


def add_mcp_doctor_agent(apps, schema_editor):
    Agent = apps.get_model('agent', 'Agent')
    if Agent.objects.filter(agentDescription='MCP Doctor').exists():
        return
    next_id = (Agent.objects.order_by('-idAgent').values_list('idAgent', flat=True).first() or 0) + 1
    Agent.objects.create(
        idAgent=next_id,
        agentName=f'agent-{next_id}',
        agentDescription='MCP Doctor',
        agentContent='true',
    )


def remove_mcp_doctor_agent(apps, schema_editor):
    Agent = apps.get_model('agent', 'Agent')
    Agent.objects.filter(agentDescription='MCP Doctor').delete()


class Migration(migrations.Migration):
    dependencies = [
        ('agent', '0140_add_esphomer_demo_prompts'),
    ]

    operations = [
        migrations.RunPython(add_mcp_doctor_agent, remove_mcp_doctor_agent),
    ]
