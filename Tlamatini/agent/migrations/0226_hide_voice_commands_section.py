# Tlamatini Author Banner — Created by Angela López Mendoza · @angelahack1
"""Remove the VOICE COMMANDS section from the Catalog of Prompts (2026-11-21).

Angela: the microphone button beside Send now does what these two cards did,
so the section is no longer necessary.

The two rows seeded by 0201 (prompt-121 and prompt-122) are HIDDEN, not
deleted: the catalog serves only ``hidden=False`` rows, and keeping the rows
preserves the seeded ``idPrompt`` identity that
``test_prompt_catalog_contiguous`` pins. Reversing this migration shows them
again.
"""
from django.db import migrations

_VOICE_COMMAND_IDS = (121, 122)


def hide_voice_commands(apps, schema_editor):
    Prompt = apps.get_model('agent', 'Prompt')
    Prompt.objects.filter(
        idPrompt__in=_VOICE_COMMAND_IDS, category='voice_commands'
    ).update(hidden=True)


def show_voice_commands(apps, schema_editor):
    Prompt = apps.get_model('agent', 'Prompt')
    Prompt.objects.filter(
        idPrompt__in=_VOICE_COMMAND_IDS, category='voice_commands'
    ).update(hidden=False)


class Migration(migrations.Migration):

    dependencies = [
        ('agent', '0225_response_files'),
    ]

    operations = [
        migrations.RunPython(hide_voice_commands, show_voice_commands),
    ]
