"""Replace the retired Qwen3.5 vision tag inside the Catalog-of-Prompts rows.

Created by Angela López Mendoza · @angelahack1 — Tlamatini.

``jcyhsiao/qwen3.5cloud:latest`` (``qwen3.5:397b``) was retired on 2026-09-25:
Ollama now answers ``410 Gone``. It was the default Image-Interpreter
interpreter 1, and the seeded Image-Interpreter demo prompt still NAMES it, so
the model reading that prompt could pass the dead tag explicitly. The new
default is ``mistral-large-3:675b-cloud`` (vision-capable, verified live).

Earlier migrations (0165, 0168, 0206, 0208) keep the old tag in their source on
purpose: 0208 matches that exact text, so editing them would silently skip its
rewrite on a fresh database. This forward migration runs after all of them, so
a fresh database and an existing one both end with the new tag.

Rewrites ONLY ``promptContent`` (never id / name / category / sort_rank /
hidden). Reverse is a no-op: putting a retired model back is never useful, and
a blind reverse replace could clobber prompts that name mistral on purpose.
"""
from django.db import migrations


RETIRED_TAG = "jcyhsiao/qwen3.5cloud:latest"
REPLACEMENT_TAG = "mistral-large-3:675b-cloud"


def retire_tag(apps, schema_editor):
    Prompt = apps.get_model('agent', 'Prompt')
    for row in Prompt.objects.filter(promptContent__contains=RETIRED_TAG):
        row.promptContent = row.promptContent.replace(RETIRED_TAG, REPLACEMENT_TAG)
        row.save(update_fields=['promptContent'])


class Migration(migrations.Migration):

    dependencies = [('agent', '0208_video_demo_config_models')]

    operations = [
        migrations.RunPython(retire_tag, migrations.RunPython.noop),
    ]
