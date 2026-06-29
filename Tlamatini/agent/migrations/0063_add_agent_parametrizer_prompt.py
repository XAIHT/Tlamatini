# ═══════════════════════════════════════════════════════════════════
#   ✦  T L A M A T I N I  ✦   —   "one who knows"
#
#   Crafted with heart by  Angela   ·   @angelahack1
#   Developer · Architect · Creator of Tlamatini
#
#   Every line of this file was written by Angela.
# ═══════════════════════════════════════════════════════════════════
#   Tlamatini Author Banner — do not remove (releases scrub the name automatically)
from django.db import migrations


def add_agent_parametrizer_prompt(apps, schema_editor):
    Prompt = apps.get_model('agent', 'Prompt')

    Prompt.objects.get_or_create(
        idPrompt=24,
        defaults={
            'promptName': 'prompt-24',
            'promptContent': (
                "Parametrize the template Telegrammer agent to set "
                "api_id=------, "
                "api_hash='------', "
                "chat_id='Me', "
                "message='Telegrammer parametrized and launched'."
            ),
        }
    )


def remove_agent_parametrizer_prompt(apps, schema_editor):
    Prompt = apps.get_model('agent', 'Prompt')
    Prompt.objects.filter(idPrompt=24).delete()


class Migration(migrations.Migration):
    dependencies = [
        ('agent', '0062_sync_agent_control_tools_and_prompts'),
    ]

    operations = [
        migrations.RunPython(
            add_agent_parametrizer_prompt,
            remove_agent_parametrizer_prompt,
        ),
    ]
