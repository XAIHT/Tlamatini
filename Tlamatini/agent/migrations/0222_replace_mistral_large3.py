# Tlamatini Author Banner — Created by Angela López Mendoza · @angelahack1
"""Update model selections in existing and freshly seeded catalogs.

The old tag below is a migration input, never a runtime default. Earlier
migrations retain their original literals so compare-and-swap repairs still
match on fresh databases. Preserve all row metadata and unrelated model choices.
"""
from django.db import migrations

RETIRED_TAG = 'mistral-large-3:675b-cloud'
REPLACEMENT_TAG = 'mistral-large-4:cloud'
MODEL_REPLACEMENTS = {
    RETIRED_TAG: REPLACEMENT_TAG,
    'glm-5.3:cloud': 'deepseek-v4.1-flash:cloud',
}


def replace_tag(apps, schema_editor):
    Prompt = apps.get_model('agent', 'Prompt')
    for retired, replacement in MODEL_REPLACEMENTS.items():
        for row in Prompt.objects.using(schema_editor.connection.alias).filter(
                promptContent__contains=retired):
            row.promptContent = row.promptContent.replace(retired, replacement)
            row.save(using=schema_editor.connection.alias, update_fields=['promptContent'])


class Migration(migrations.Migration):
    dependencies = [('agent', '0221_torrenter')]
    operations = [migrations.RunPython(replace_tag, migrations.RunPython.noop)]
