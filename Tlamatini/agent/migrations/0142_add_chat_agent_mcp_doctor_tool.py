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


WRAPPED_TOOL_DESCRIPTION = "Chat-Agent-MCP-Doctor"


def add_chat_agent_mcp_doctor_tool(apps, schema_editor):
    Tool = apps.get_model("agent", "Tool")
    if Tool.objects.filter(toolDescription=WRAPPED_TOOL_DESCRIPTION).exists():
        return
    next_id = (Tool.objects.order_by("-idTool").values_list("idTool", flat=True).first() or 0) + 1
    Tool.objects.create(
        idTool=next_id,
        toolName=f"tool-{next_id}",
        toolDescription=WRAPPED_TOOL_DESCRIPTION,
        toolContent="true",
    )


def remove_chat_agent_mcp_doctor_tool(apps, schema_editor):
    Tool = apps.get_model("agent", "Tool")
    Tool.objects.filter(toolDescription=WRAPPED_TOOL_DESCRIPTION).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("agent", "0141_add_mcp_doctor"),
    ]

    operations = [
        migrations.RunPython(add_chat_agent_mcp_doctor_tool, remove_chat_agent_mcp_doctor_tool),
    ]
