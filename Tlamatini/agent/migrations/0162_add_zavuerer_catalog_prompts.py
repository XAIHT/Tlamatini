# ═══════════════════════════════════════════════════════════════════
#   ✦  T L A M A T I N I  ✦   —   "one who knows"
#
#   Created by  Angela López Mendoza   ·   @angelahack1
#   Developer · Architect · Creator of Tlamatini
#
#   Every line of this file was written by Angela López Mendoza.
# ═══════════════════════════════════════════════════════════════════
#   Tlamatini Author Banner — do not remove (releases scrub the name automatically)
"""Catalog-of-prompts examples for Zavuerer (agent #83).

Three prompts, appended contiguously after the current highest slot (the
``#prompts-catalog`` dropdown enumerates prompt-1..N and breaks at the first
gap, so each is added at the next free idPrompt):

1. A guided **Step-by-Step** setup prompt for a non-technical user. Its wording
   ("chat_agent_zavuerer" + "Tick ... step-by-step checkboxes") makes the catalog
   mode-classifier tick Multi-Turn + Exec report + Step-by-Step on click.
2-3. Two SAFE sample SEND prompts (Multi-Turn + Exec report). They use a reserved
   555 placeholder number the user replaces, and with no key configured the agent
   simply REFUSES (status: refused) - so the daily chat regression sends nothing.
"""
from django.db import migrations


SETUP_PROMPT = (
    "Tlamatini, please set up **Zavuerer** with me ONE step at a time so I can send a text / "
    "WhatsApp / email from a single key - I'm not technical, so go slowly and wait for me after "
    "each step. Tick the **Multi-Turn**, **Exec report**, and **step-by-step** checkboxes for this.\n\n"
    "Step 1: run chat_agent_zavuerer with action='health' to check whether my Zavu key is already "
    "configured, and tell me the result in plain words. Then STOP and WAIT for me to reply 'READY'.\n\n"
    "Step 2: if the health check said my key is missing, tell me to open **Config -> Access Keys "
    "Wizard**, find the **\"Unified Messaging (Zavu)\"** section, paste my Zavu key (I can get one "
    "at https://www.zavu.dev), click Save, and restart Tlamatini. Then STOP and WAIT for me to reply "
    "'READY'.\n\n"
    "Step 3: once a key is configured, send a tiny test with chat_agent_zavuerer (action='send', "
    "channel='auto', to the phone number I give you, text='Zavuerer test from Tlamatini') and tell me "
    "in plain words whether it was queued / sent.\n\n"
    "Use ONLY chat_agent_zavuerer. Do ONE step, then stop and wait for my 'READY' each time. "
    "End with END-RESPONSE."
)

SAMPLE_SMS_PROMPT = (
    "Tlamatini, use chat_agent_zavuerer to send a quick **SMS**: set action='send', channel='sms', "
    "to='+15555550100' (replace this with your own +country-code mobile number), and "
    "text='Hello from Tlamatini - Zavuerer is working!'. Tick Multi-Turn and Exec report. Tell me the "
    "channel and delivery status it returns. (If my Zavu key isn't set yet, the agent safely REFUSES "
    "and reminds me to add it via Config -> Access Keys Wizard - that's expected.) Use ONLY "
    "chat_agent_zavuerer. End with END-RESPONSE."
)

SAMPLE_AUTO_PROMPT = (
    "Tlamatini, reach me the smart way with **Zavuerer**: use chat_agent_zavuerer with action='send', "
    "channel='auto' (let Zavu's routing pick the best / cheapest channel and fall back automatically), "
    "to='+15555550100' (replace with your own number), and text='Your Tlamatini build finished'. Tick "
    "Multi-Turn and Exec report. Report which channel Zavu actually used and the delivery status. If no "
    "Zavu key is configured it will safely refuse - that's fine. Use ONLY chat_agent_zavuerer. "
    "End with END-RESPONSE."
)

_NEW_PROMPTS = (SETUP_PROMPT, SAMPLE_SMS_PROMPT, SAMPLE_AUTO_PROMPT)


def add_prompts(apps, schema_editor):
    Prompt = apps.get_model('agent', 'Prompt')
    for content in _NEW_PROMPTS:
        if Prompt.objects.filter(promptContent=content).exists():
            continue
        next_id = (Prompt.objects.order_by('-idPrompt').values_list('idPrompt', flat=True).first() or 0) + 1
        Prompt.objects.update_or_create(
            idPrompt=next_id,
            defaults={'promptName': f'prompt-{next_id}', 'promptContent': content},
        )


def remove_prompts(apps, schema_editor):
    Prompt = apps.get_model('agent', 'Prompt')
    Prompt.objects.filter(promptContent__in=list(_NEW_PROMPTS)).delete()


class Migration(migrations.Migration):
    dependencies = [('agent', '0161_add_zavuerer_demo_prompts')]
    operations = [migrations.RunPython(add_prompts, remove_prompts)]
