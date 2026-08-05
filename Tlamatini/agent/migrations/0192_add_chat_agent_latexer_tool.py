# ═══════════════════════════════════════════════════════════════════
#   ✦  T L A M A T I N I  ✦   —   "one who knows"
#
#   Created by  Angela López Mendoza   ·   @angelahack1
#   Developer · Architect · Creator of Tlamatini
#
#   Every line of this file was written by Angela López Mendoza.
# ═══════════════════════════════════════════════════════════════════
#   Tlamatini Author Banner — do not remove (releases scrub the name automatically)
"""Seed the ``Chat-Agent-LaTeXer`` wrapper Tool row (Angela, 2026-08-05).

This is the (a) half of the DUAL ENABLE-GATE: ``get_mcp_tools()`` binds
``chat_agent_latexer`` for the LLM only when BOTH this Tool row (Configure Mcps/Tools)
AND the ``LaTeXer`` Agent row from 0191 (Configure Agents) are enabled. Both gates fail
OPEN, so without this row the wrapper still works — the row exists so Angela has a
checkbox to turn LaTeXer OFF.
"""
from django.db import migrations


WRAPPED_TOOL_DESCRIPTION = "Chat-Agent-LaTeXer"


def add_chat_agent_latexer_tool(apps, schema_editor):
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


def remove_chat_agent_latexer_tool(apps, schema_editor):
    Tool = apps.get_model("agent", "Tool")
    Tool.objects.filter(toolDescription=WRAPPED_TOOL_DESCRIPTION).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("agent", "0191_add_latexer"),
    ]

    operations = [
        migrations.RunPython(add_chat_agent_latexer_tool, remove_chat_agent_latexer_tool),
    ]
