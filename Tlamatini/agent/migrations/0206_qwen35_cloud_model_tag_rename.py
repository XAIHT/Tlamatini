"""Rename the Qwen3.5 vision-model tag inside the seeded Catalog-of-Prompts rows.

The Image-Interpreter (interpreter 1) and Video-Analyzer (interpreter 2) default
vision model moved from the Ollama tag ``qwen3.5:cloud`` to
``jcyhsiao/qwen3.5cloud:latest``. It is the SAME cloud model -- ``ollama list``
reports the same digest and a blank SIZE column for both tags -- only republished
under a community namespace, so no behaviour changes, only the name to pull.

Migrations 0165 (Image-Interpreter triple-model demo) and 0168 (Video-Analyzer
demo) seeded prompt rows that NAME the old tag. Their source text was updated in
the same pass, which fixes a database created from scratch -- but ``Prompt`` rows
are user state that survives a self-update, so an EXISTING database would keep
showing the old tag forever. This forward migration fixes those databases.

It rewrites ONLY ``promptContent`` -- never ``idPrompt`` / ``promptName`` /
``category`` / ``sort_rank`` / ``hidden`` -- so the catalog's ordering and
contiguity contracts are untouched. Same shape as the 0182-0185 batch rewrites.

Idempotent in both directions: the new tag does not contain the old one as a
substring, so re-running either direction is a no-op.
"""
from django.db import migrations


OLD_TAG = "qwen3.5:cloud"
NEW_TAG = "jcyhsiao/qwen3.5cloud:latest"


def _retag_prompts(apps, old, new):
    Prompt = apps.get_model('agent', 'Prompt')
    for row in Prompt.objects.filter(promptContent__contains=old):
        row.promptContent = row.promptContent.replace(old, new)
        row.save(update_fields=['promptContent'])


def rename_tag_forward(apps, schema_editor):
    _retag_prompts(apps, OLD_TAG, NEW_TAG)


def rename_tag_backward(apps, schema_editor):
    _retag_prompts(apps, NEW_TAG, OLD_TAG)


class Migration(migrations.Migration):

    dependencies = [('agent', '0205_silence_window_default_3_5_seconds')]

    operations = [
        migrations.RunPython(rename_tag_forward, rename_tag_backward),
    ]
