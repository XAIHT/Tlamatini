from django.db import migrations


def add_multi_turn_demo_prompts(apps, schema_editor):
    Prompt = apps.get_model('agent', 'Prompt')

    Prompt.objects.get_or_create(
        idPrompt=20,
        defaults={
            'promptName': 'prompt-20',
            'promptContent': (
                "Run an end-to-end multi-turn local document demo, please: use File Creator "
                "to create the file '----\\tlamatini_multiturn_release_notes.txt' with a short "
                "fake release note for Tlamatini, then use File Extractor to read that same "
                "file, then use Summarize Text to convert it into a 5-bullet executive "
                "summary, and finally use Notifier to announce that the demo finished. If any "
                "wrapped agent returns a running run_id, keep using chat_agent_run_status and "
                "chat_agent_run_log until you have enough output to continue."
            ),
        }
    )

    Prompt.objects.get_or_create(
        idPrompt=21,
        defaults={
            'promptName': 'prompt-21',
            'promptContent': (
                "Run a multi-turn web research demo, please: use Apirer to call the URL "
                "'https://example.com' with GET, then use Crawler on that same URL to "
                "capture the page text, then use Summarize Text to produce a short "
                "comparison between the HTTP response and the crawled content, and finally "
                "use File Creator to save the final comparison into "
                "'----\\tlamatini_example_comparison.md'. If any wrapped agent returns a "
                "running run_id, keep using chat_agent_run_status and chat_agent_run_log "
                "until you have enough output to continue."
            ),
        }
    )

    Prompt.objects.get_or_create(
        idPrompt=22,
        defaults={
            'promptName': 'prompt-22',
            'promptContent': (
                "Run a multi-turn monitoring demo, please: first use File Creator to "
                "initialize '----\\tlamatini_monitor_demo.log' with a starting line, then "
                "start Monitor Log on that file watching for the keywords 'ERROR,FATAL', "
                "then use Pythonxer to append several new log lines to the same file "
                "including one line that contains the word 'ERROR', keep polling the "
                "monitor with chat_agent_run_status and chat_agent_run_log until the alert "
                "is visible, then stop that monitor with chat_agent_run_stop and summarize "
                "what happened."
            ),
        }
    )


def remove_multi_turn_demo_prompts(apps, schema_editor):
    Prompt = apps.get_model('agent', 'Prompt')
    Prompt.objects.filter(idPrompt__in=(25, 26, 27)).delete()


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