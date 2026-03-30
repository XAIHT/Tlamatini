from django.db import migrations


def _next_integer_pk(model_class, pk_field_name):
    max_id = 0
    for row in model_class.objects.all():
        current_id = getattr(row, pk_field_name, 0) or 0
        if current_id > max_id:
            max_id = current_id
    return max_id + 1


def sync_agent_control_tools_and_prompts(apps, schema_editor):
    Tool = apps.get_model('agent', 'Tool')
    Prompt = apps.get_model('agent', 'Prompt')

    legacy_tool_descriptions = (
        'Execute-Agent',
        'Stop-Agent',
        'Agent-Status',
    )
    Tool.objects.filter(toolDescription__in=legacy_tool_descriptions).delete()

    for tool_description in ('Agent-Stopper', 'Agent-Stat-Getter'):
        existing = Tool.objects.filter(toolDescription=tool_description).first()
        if existing:
            continue

        next_id = _next_integer_pk(Tool, 'idTool')
        Tool.objects.create(
            idTool=next_id,
            toolName=f'tool-{next_id}',
            toolDescription=tool_description,
            toolContent='true',
        )

    Prompt.objects.get_or_create(
        idPrompt=21,
        defaults={
            'promptName': 'prompt-21',
            'promptContent': 'Start-up the agent "------", please.',
        }
    )

    Prompt.objects.get_or_create(
        idPrompt=22,
        defaults={
            'promptName': 'prompt-22',
            'promptContent': 'Stop the agent "------", please.',
        }
    )

    Prompt.objects.get_or_create(
        idPrompt=23,
        defaults={
            'promptName': 'prompt-23',
            'promptContent': 'Get the status of the agent "------", please.',
        }
    )


def revert_agent_control_tools_and_prompts(apps, schema_editor):
    Tool = apps.get_model('agent', 'Tool')
    Prompt = apps.get_model('agent', 'Prompt')

    Tool.objects.filter(
        toolDescription__in=('Agent-Stopper', 'Agent-Stat-Getter')
    ).delete()

    for tool_description in ('Execute-Agent', 'Stop-Agent', 'Agent-Status'):
        existing = Tool.objects.filter(toolDescription=tool_description).first()
        if existing:
            continue

        next_id = _next_integer_pk(Tool, 'idTool')
        Tool.objects.create(
            idTool=next_id,
            toolName=f'tool-{next_id}',
            toolDescription=tool_description,
            toolContent='true',
        )

    Prompt.objects.filter(idPrompt__in=(21, 22, 23)).delete()


class Migration(migrations.Migration):
    dependencies = [
        ('agent', '0061_add_agent_starter_tool'),
    ]

    operations = [
        migrations.RunPython(
            sync_agent_control_tools_and_prompts,
            revert_agent_control_tools_and_prompts,
        ),
    ]
