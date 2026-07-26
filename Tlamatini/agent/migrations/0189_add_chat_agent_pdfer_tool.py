# ═══════════════════════════════════════════════════════════════════
#   ✦  T L A M A T I N I  ✦   —   "one who knows"
#
#   Created by  Angela López Mendoza   ·   @angelahack1
#   Developer · Architect · Creator of Tlamatini
#
#   Every line of this file was written by Angela López Mendoza.
# ═══════════════════════════════════════════════════════════════════
#   Tlamatini Author Banner — do not remove (releases scrub the name automatically)
"""Seed the ``Chat-Agent-PDFer`` wrapper Tool row (Angela, 2026-07-26).

This is the (a) half of the DUAL ENABLE-GATE: ``get_mcp_tools()`` binds
``chat_agent_pdfer`` for the LLM only when BOTH this Tool row (Configure Mcps/Tools)
AND the ``PDFer`` Agent row from 0188 (Configure Agents) are enabled. Both gates fail
OPEN, so without this row the wrapper still works — the row exists so Angela has a
checkbox to turn PDFer OFF.
"""
from django.db import migrations


WRAPPED_TOOL_DESCRIPTION = "Chat-Agent-PDFer"


def add_chat_agent_pdfer_tool(apps, schema_editor):
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


def remove_chat_agent_pdfer_tool(apps, schema_editor):
    Tool = apps.get_model("agent", "Tool")
    Tool.objects.filter(toolDescription=WRAPPED_TOOL_DESCRIPTION).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("agent", "0188_add_pdfer"),
    ]

    operations = [
        migrations.RunPython(add_chat_agent_pdfer_tool, remove_chat_agent_pdfer_tool),
    ]
