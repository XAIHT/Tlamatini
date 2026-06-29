# ═══════════════════════════════════════════════════════════════════
#   ✦  T L A M A T I N I  ✦   —   "one who knows"
#
#   Created by  Angela López Mendoza   ·   @angelahack1
#   Developer · Architect · Creator of Tlamatini
#
#   Every line of this file was written by Angela López Mendoza.
# ═══════════════════════════════════════════════════════════════════
#   Tlamatini Author Banner — do not remove (releases scrub the name automatically)
"""
Migration for the expanded ACPX tool surface.

Seeds five new Tool rows so the existing tool-toggle UI exposes the new
ACPX tools added in section A of the ACPX-focused enhancement set:

    - acpx-send-and-wait   (synchronous send that waits for child idle)
    - acpx-transcript      (read on-disk transcript for hand-off / evidence)
    - acpx-session-status  (per-session alive/pid/transcript_size status)
    - acpx-list-sessions   (enumerate live sessions in this runtime)
    - acpx-relay           (single-call hand-off between two ACP sessions)

The existing seven ACPX rows from migration 0071 are left untouched.
"""
from django.db import migrations


def seed_acpx_tool_surface(apps, schema_editor):
    Tool = apps.get_model("agent", "Tool")
    base_seed = [
        ("acpx-send-and-wait",  "ACP send and wait",  "true"),
        ("acpx-transcript",     "ACP transcript",     "true"),
        ("acpx-session-status", "ACP session status", "true"),
        ("acpx-list-sessions",  "ACP list sessions",  "true"),
        ("acpx-relay",          "ACP relay",          "true"),
    ]
    next_id = (Tool.objects.order_by("-idTool").first().idTool + 1) if Tool.objects.exists() else 1
    next_id = max(next_id, 220)
    for name, desc, content in base_seed:
        if not Tool.objects.filter(toolName=name).exists():
            Tool.objects.create(
                idTool=next_id, toolName=name,
                toolDescription=desc, toolContent=content,
            )
            next_id += 1


def unseed_acpx_tool_surface(apps, schema_editor):
    Tool = apps.get_model("agent", "Tool")
    Tool.objects.filter(toolName__in=[
        "acpx-send-and-wait",
        "acpx-transcript",
        "acpx-session-status",
        "acpx-list-sessions",
        "acpx-relay",
    ]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("agent", "0074_simplify_demo_prompts"),
    ]

    operations = [
        migrations.RunPython(seed_acpx_tool_surface, unseed_acpx_tool_surface),
    ]
