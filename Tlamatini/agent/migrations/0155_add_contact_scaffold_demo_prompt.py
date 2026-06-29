# ═══════════════════════════════════════════════════════════════════
#   ✦  T L A M A T I N I  ✦   —   "one who knows"
#
#   Created by  Angela López Mendoza   ·   @angelahack1
#   Developer · Architect · Creator of Tlamatini
#
#   Every line of this file was written by Angela López Mendoza.
# ═══════════════════════════════════════════════════════════════════
#   Tlamatini Author Banner — do not remove (releases scrub the name automatically)
from django.db import migrations


# Catalog-of-prompts SCAFFOLD: lets a user ADD A NEW PERSON to contacts.json by filling
# the [[ ... ]] markers, then sending the prompt. Tlamatini (Multi-Turn) locates
# contacts.json next to config.json (works in BOTH the frozen install and the dev source)
# and appends/updates the contact, preserving existing entries. SAFE for the daily chat
# test: if any marker is still unfilled it changes NOTHING and just asks the user to fill
# it in. Markers use [[ ]] (no angle brackets) so an HTML card preview can't eat them.
DEMO = (
    "Tlamatini, ADD A NEW CONTACT to my contacts book. I filled in the fields below. "
    "A new contact needs a NAME plus at least a Telegram @username OR a WhatsApp number.\n"
    "\n"
    "NEW CONTACT\n"
    "- name:     [[ TYPE THE FULL NAME HERE ]]\n"
    "- aliases:  [[ OTHER NAMES I MAY USE, COMMA-SEPARATED - OPTIONAL ]]\n"
    "- telegram: [[ THEIR @username, e.g. @maria_lopez - OPTIONAL ]]\n"
    "- whatsapp: [[ PHONE WITH COUNTRY CODE, e.g. +5215555555555 - OPTIONAL ]]\n"
    "- email:    [[ THEIR EMAIL - OPTIONAL ]]\n"
    "\n"
    "FIRST, a safety check: if ANY line above still shows a [[ ... ]] marker (so I have "
    "not filled it), do NOT change any file - just tell me which fields to fill and stop. "
    "Only continue when the name is filled AND at least one of telegram or whatsapp is "
    "filled. For any OPTIONAL field I leave as a marker or blank, simply skip it.\n"
    "\n"
    "THEN, in Multi-Turn, using your own tools:\n"
    "1) Find my contacts file: use Globber for contacts.json and choose the ONE next to my "
    "config.json at the application root (NOT a copy inside any TlamatiniSourceCode "
    "folder). This way it works the same in the installed app and in the dev source.\n"
    "2) Add this person to the contacts array WITHOUT removing or altering any existing "
    "contact. Save telegram exactly as @username, and whatsapp as a plus sign, the country "
    "code, then the number (for example +5215555555555). If a contact with the same name "
    "already exists, UPDATE that one instead of duplicating. Edit safely: load the JSON, "
    "append or update, then write it back with indent=2 so it stays valid JSON.\n"
    "3) Read the file back and show me the new contact entry to confirm it was saved.\n"
    "\n"
    "Tick ONLY the Multi-Turn checkbox. End with END-RESPONSE."
)


def add_demo_prompt(apps, schema_editor):
    Prompt = apps.get_model('agent', 'Prompt')
    if Prompt.objects.filter(promptContent=DEMO).exists():
        return
    next_id = (Prompt.objects.order_by('-idPrompt').values_list('idPrompt', flat=True).first() or 0) + 1
    Prompt.objects.update_or_create(
        idPrompt=next_id,
        defaults={'promptName': f'prompt-{next_id}', 'promptContent': DEMO},
    )


def remove_demo_prompt(apps, schema_editor):
    Prompt = apps.get_model('agent', 'Prompt')
    Prompt.objects.filter(promptContent=DEMO).delete()


class Migration(migrations.Migration):
    dependencies = [('agent', '0154_add_instant_messaging_doctor_demo_prompt')]
    operations = [migrations.RunPython(add_demo_prompt, remove_demo_prompt)]
