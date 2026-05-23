from django.db import migrations


WRAPPED_TOOL_DESCRIPTION = "Chat-Agent-Kalier"


def add_chat_agent_kalier_tool(apps, schema_editor):
    Tool = apps.get_model("agent", "Tool")

    if Tool.objects.filter(toolDescription=WRAPPED_TOOL_DESCRIPTION).exists():
        return

    next_id = (Tool.objects.order_by("-idTool").first().idTool + 1) if Tool.objects.exists() else 1
    Tool.objects.create(
        idTool=next_id,
        toolName=f"tool-{next_id}",
        toolDescription=WRAPPED_TOOL_DESCRIPTION,
        toolContent="true",
    )


def remove_chat_agent_kalier_tool(apps, schema_editor):
    Tool = apps.get_model("agent", "Tool")
    Tool.objects.filter(toolDescription=WRAPPED_TOOL_DESCRIPTION).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("agent", "0097_add_kalier"),
    ]

    operations = [
        migrations.RunPython(add_chat_agent_kalier_tool, remove_chat_agent_kalier_tool),
    ]
