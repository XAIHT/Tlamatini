from django.db import migrations

# Insert a new catalog request at slot #5 (between the current 4th and 5th
# requests). The #prompts-catalog dropdown enumerates prompt-1, prompt-2, … and
# breaks at the first gap, so a true mid-list insert must SHIFT every prompt
# whose id is >= 5 up by one before the new row is written, and shift them back
# down on reverse. promptName stays in lock-step with idPrompt (prompt-<id>).
INSERT_AT = 5

# A Multi-Turn operator request (Java 1.8 -> 17 + Maven project migration). The
# trailing directive line makes the catalog classifier badge it Multi-turn AND
# Exec-report, and clicking the card ticks the Multi-Turn + Exec Report toggles.
NEW_PROMPT_CONTENT = (
    'Tlamatini, starting from the project located in the directory '
    '"Tlamatini/applications/<CurrentProjectFolderName>", **You must create a new project located in '
    '"Tlamatini/applications/<NewProjectFolderName>**" strictly following these REQUIREMENTS:\n'
    '- Migrate from Java 1.8 to Java 17\n'
    '- Migrate to use Maven (- ...\n'
    '- ...----... \n'
    '**You must create the new project directory as '
    '"Tlamatini/applications/<NewProjectFolderName>", as you already know: the Tlamatini '
    'directory is intended for applications; therefore, from each element of the original '
    'resources, you must create/copy/etc. (as appropriate in each case) from '
    '"Tlamatini/applications/<CurrentProjectFolderName>" into '
    '"Tlamatini/applications/<NewProjectFolderName>" to meet the requirements. REQUIREMENTS '
    'listed.**\n'
    '\n'
    '(Multi-Turn mode — keep the Multi-Turn and Exec Report checkboxes ticked; this request '
    'requires execution-report verification.) End with END-RESPONSE.'
)


def insert_at_5(apps, schema_editor):
    Prompt = apps.get_model('agent', 'Prompt')
    # Shift highest-first so each destination id is always free (no PK clash).
    ids = list(
        Prompt.objects.filter(idPrompt__gte=INSERT_AT)
        .order_by('-idPrompt')
        .values_list('idPrompt', flat=True)
    )
    for pid in ids:
        Prompt.objects.filter(idPrompt=pid).update(
            idPrompt=pid + 1, promptName=f'prompt-{pid + 1}'
        )
    Prompt.objects.update_or_create(
        idPrompt=INSERT_AT,
        defaults={'promptName': f'prompt-{INSERT_AT}', 'promptContent': NEW_PROMPT_CONTENT},
    )


def remove_at_5(apps, schema_editor):
    Prompt = apps.get_model('agent', 'Prompt')
    Prompt.objects.filter(idPrompt=INSERT_AT).delete()
    # Shift lowest-first back down to close the gap.
    ids = list(
        Prompt.objects.filter(idPrompt__gt=INSERT_AT)
        .order_by('idPrompt')
        .values_list('idPrompt', flat=True)
    )
    for pid in ids:
        Prompt.objects.filter(idPrompt=pid).update(
            idPrompt=pid - 1, promptName=f'prompt-{pid - 1}'
        )


class Migration(migrations.Migration):
    dependencies = [('agent', '0143_add_mcp_doctor_demo_prompt')]
    operations = [migrations.RunPython(insert_at_5, remove_at_5)]
