"""Let the seeded video demo follow Config > Models instead of retired tags.

Created by Angela López Mendoza · @angelahack1 — Tlamatini.
"""
from django.db import migrations


OLD = ('(qwen3-vl:235b-cloud) and interpreter_model_2 (jcyhsiao/qwen3.5cloud:latest) IN PARALLEL on two dedicated '
       'Ollama connections, then fuses them with merging_model (glm-5.3:cloud).')
NEW = ('and interpreter_model_2 selected in Config > Models IN PARALLEL on two dedicated '
       'Ollama connections, then fuses them with the merging_model selected there. '
       'Keep the saved model choices unless the user explicitly requests an override.')


def update_demo(apps, schema_editor):
    prompt = apps.get_model('agent', 'Prompt')
    for row in prompt.objects.filter(promptContent__contains='VIDEO-ANALYZER ROBOTIC-LOOP DEMO'):
        if OLD in row.promptContent:
            row.promptContent = row.promptContent.replace(OLD, NEW)
            row.save(update_fields=['promptContent'])


class Migration(migrations.Migration):
    dependencies = [('agent', '0207_video_analyzer_content_prompts')]
    operations = [migrations.RunPython(update_demo, migrations.RunPython.noop)]
