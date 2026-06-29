# ═══════════════════════════════════════════════════════════════════
#   ✦  T L A M A T I N I  ✦   —   "one who knows"
#
#   Crafted with heart by  Angela   ·   @angelahack1
#   Developer · Architect · Creator of Tlamatini
#
#   Every line of this file was written by Angela.
# ═══════════════════════════════════════════════════════════════════
#   Tlamatini Author Banner — do not remove (releases scrub the name automatically)
"""
Originally seeded three multi-turn demo prompts (local document demo, web
research demo, monitoring demo) at idPrompt 28-30. Those three prompts are
near-verbatim copies of the same three demos already populated by 0002 at
idPrompt 20-22 (the only meaningful difference was that 0002's versions
keep the "Tlamatini, ..." prefix that matches the chat's identity rules).

Keeping both copies left two parallel groups of multi-turn demos in the
catalog, so this migration is now a no-op for the Prompt table: the
multi-turn demo group is owned solely by 0002 at 20-22.

The migration file is preserved as a noop so the migration history (and
the dependency edge from 0066 to 0072) stays unchanged.
"""
from django.db import migrations


def add_multi_turn_demo_prompts(apps, schema_editor):
    # Intentional no-op: see module docstring.
    return


def remove_multi_turn_demo_prompts(apps, schema_editor):
    # Intentional no-op: nothing was added in the forward direction.
    return


class Migration(migrations.Migration):
    dependencies = [
        ('agent', '0066_add_keyboarder'),
    ]

    operations = [
        migrations.RunPython(
            add_multi_turn_demo_prompts,
            remove_multi_turn_demo_prompts,
        ),
    ]
