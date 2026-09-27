"""Update obsolete seeded visual-result wording without replacing user prompts.

Created by Angela López Mendoza · @angelahack1 — Tlamatini.

Keep historical migrations intact: later migrations match their exact text.
Only known literal fragments change; prompt identity, ordering and other text
remain intact. The live database is updated by the normal migration lifecycle.
"""
from django.db import migrations


REPLACEMENTS = (
    (
        'merged / partial_interpreter_1_only / partial_interpreter_2_only / merge_fallback_concat',
        'merged / error; failed configured models accumulate a visible fatal error; '
        'preserve Tlamatini retries and configured recovery routes with the same models; '
        'never accept partial observers or raw concatenation as success',
    ),
    (
        'Report missing audio or partial results honestly; link the saved report.',
        'Report legitimate missing audio honestly; link a completed report. '
        'Any failed configured observer or merger rejects that attempt and accumulates '
        'a visible fatal error. Preserve Tlamatini retries and flow recovery with the '
        'configured models; never substitute a model or incomplete summary.',
    ),
)


def update_prompts(apps, schema_editor):
    prompt = apps.get_model('agent', 'Prompt')
    for old, new in REPLACEMENTS:
        for row in prompt.objects.filter(promptContent__contains=old):
            row.promptContent = row.promptContent.replace(old, new)
            row.save(update_fields=['promptContent'])


class Migration(migrations.Migration):
    dependencies = [('agent', '0209_retire_qwen35_vision_model')]
    operations = [migrations.RunPython(update_prompts, migrations.RunPython.noop)]
