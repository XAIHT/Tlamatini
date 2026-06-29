# ═══════════════════════════════════════════════════════════════════
#   ✦  T L A M A T I N I  ✦   —   "one who knows"
#
#   Created by  Angela López Mendoza   ·   @angelahack1
#   Developer · Architect · Creator of Tlamatini
#
#   Every line of this file was written by Angela López Mendoza.
# ═══════════════════════════════════════════════════════════════════
#   Tlamatini Author Banner — do not remove (releases scrub the name automatically)
from django.db import migrations


# Two direct @tool helpers added to keep desktop-UI flows fast and
# the run-status polling loop short:
#   - Window-Present: <100 ms yes/no replacement for the
#     Shoter+Image-Interpreter "is X open?" pattern.
#   - Chat-Agent-Run-Wait: server-side blocking helper that replaces a
#     5+ iteration polling loop on a long-running wrapped chat-agent.
TOOL_DESCRIPTIONS = (
    "Window-Present",
    "Chat-Agent-Run-Wait",
)


def add_helper_tools(apps, schema_editor):
    Tool = apps.get_model("agent", "Tool")
    for description in TOOL_DESCRIPTIONS:
        if Tool.objects.filter(toolDescription=description).exists():
            continue
        next_id = (
            Tool.objects.order_by("-idTool").first().idTool + 1
            if Tool.objects.exists()
            else 1
        )
        Tool.objects.create(
            idTool=next_id,
            toolName=f"tool-{next_id}",
            toolDescription=description,
            toolContent="true",
        )


def remove_helper_tools(apps, schema_editor):
    Tool = apps.get_model("agent", "Tool")
    Tool.objects.filter(toolDescription__in=TOOL_DESCRIPTIONS).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("agent", "0080_add_chat_agent_sleeper_tool"),
    ]

    operations = [
        migrations.RunPython(add_helper_tools, remove_helper_tools),
    ]
