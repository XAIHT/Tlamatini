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


def add_googler_tool(apps, schema_editor):
    Tool = apps.get_model('agent', 'Tool')
    max_id = 0
    for tool in Tool.objects.all():
        if tool.idTool > max_id:
            max_id = tool.idTool

    existing = Tool.objects.filter(toolDescription='Googler').first()
    if existing:
        return

    next_id = max_id + 1
    Tool.objects.create(
        idTool=next_id,
        toolName=f'tool-{next_id}',
        toolDescription='Googler',
        toolContent='true',
    )


def remove_googler_tool(apps, schema_editor):
    Tool = apps.get_model('agent', 'Tool')
    Tool.objects.filter(toolDescription='Googler').delete()


class Migration(migrations.Migration):
    dependencies = [
        ('agent', '0067_add_multi_turn_demo_prompts'),
    ]

    operations = [
        migrations.RunPython(add_googler_tool, remove_googler_tool),
    ]
