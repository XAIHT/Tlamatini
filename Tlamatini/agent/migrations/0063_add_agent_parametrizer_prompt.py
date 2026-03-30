from django.db import migrations


def add_agent_parametrizer_prompt(apps, schema_editor):
    Prompt = apps.get_model('agent', 'Prompt')

    Prompt.objects.get_or_create(
        idPrompt=24,
        defaults={
            'promptName': 'prompt-24',
            'promptContent': (
                "Parametrize the template Telegrammer agent to set "
                "api_id=123456, api_hash='adcb5adcbbad6676adc98112345678910', "
                "chat_id='Angela-Bennet', message='Telegrammer parametrized and launched'."
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
