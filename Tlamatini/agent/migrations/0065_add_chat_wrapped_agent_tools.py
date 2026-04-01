from django.db import migrations


WRAPPED_TOOL_DESCRIPTIONS = (
    "Chat-Agent-Crawler",
    "Chat-Agent-Send-Email",
    "Chat-Agent-Executer",
    "Chat-Agent-Gitter",
    "Chat-Agent-SQLer",
    "Chat-Agent-SSHer",
    "Chat-Agent-SCPer",
    "Chat-Agent-Pythonxer",
    "Chat-Agent-Dockerer",
    "Chat-Agent-Kuberneter",
    "Chat-Agent-Jenkinser",
    "Chat-Agent-Mongoxer",
    "Chat-Agent-File-Creator",
    "Chat-Agent-File-Extractor",
    "Chat-Agent-File-Interpreter",
    "Chat-Agent-Image-Interpreter",
    "Chat-Agent-Summarize-Text",
    "Chat-Agent-PSer",
    "Chat-Agent-Notifier",
    "Chat-Agent-Shoter",
    "Chat-Agent-Telegramer",
    "Chat-Agent-Whatsapper",
    "Chat-Agent-Apirer",
    "Chat-Agent-Prompter",
    "Chat-Agent-Monitor-Log",
    "Chat-Agent-Monitor-Netstat",
    "Chat-Agent-Kyber-Keygen",
    "Chat-Agent-Kyber-Cipher",
    "Chat-Agent-Kyber-Deciph",
    "Chat-Agent-Move-File",
    "Chat-Agent-Deleter",
    "Chat-Agent-Recmailer",
    "Chat-Agent-Run-List",
    "Chat-Agent-Run-Status",
    "Chat-Agent-Run-Log",
    "Chat-Agent-Run-Stop",
)


def add_wrapped_tools(apps, schema_editor):
    Tool = apps.get_model("agent", "Tool")

    for tool_description in WRAPPED_TOOL_DESCRIPTIONS:
        existing = Tool.objects.filter(toolDescription=tool_description).first()
        if existing:
            continue

        next_id = (Tool.objects.order_by("-idTool").first().idTool + 1) if Tool.objects.exists() else 1
        Tool.objects.create(
            idTool=next_id,
            toolName=f"tool-{next_id}",
            toolDescription=tool_description,
            toolContent="true",
        )


def remove_wrapped_tools(apps, schema_editor):
    Tool = apps.get_model("agent", "Tool")
    Tool.objects.filter(toolDescription__in=WRAPPED_TOOL_DESCRIPTIONS).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("agent", "0064_add_chat_agent_run_model"),
    ]

    operations = [
        migrations.RunPython(add_wrapped_tools, remove_wrapped_tools),
    ]
