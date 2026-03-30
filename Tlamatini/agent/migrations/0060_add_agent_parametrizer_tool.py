from django.db import migrations


def add_agent_parametrizer_tool(apps, schema_editor):
    Tool = apps.get_model('agent', 'Tool')
    max_id = 0
    for tool in Tool.objects.all():
        if tool.idTool > max_id:
            max_id = tool.idTool

    existing = Tool.objects.filter(toolDescription='Agent-Parametrizer').first()
    if existing:
        return

    next_id = max_id + 1
    Tool.objects.create(
        idTool=next_id,
        toolName=f'tool-{next_id}',
        toolDescription='Agent-Parametrizer',
        toolContent='true',
    )


def remove_agent_parametrizer_tool(apps, schema_editor):
    Tool = apps.get_model('agent', 'Tool')
    Tool.objects.filter(toolDescription='Agent-Parametrizer').delete()


class Migration(migrations.Migration):
    dependencies = [
        ('agent', '0059_add_j_decompiler'),
    ]

    operations = [
        migrations.RunPython(add_agent_parametrizer_tool, remove_agent_parametrizer_tool),
    ]
