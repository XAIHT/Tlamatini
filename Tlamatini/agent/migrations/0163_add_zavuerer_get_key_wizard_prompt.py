# ═══════════════════════════════════════════════════════════════════
#   ✦  T L A M A T I N I  ✦   —   "one who knows"
#
#   Created by  Angela López Mendoza   ·   @angelahack1
#   Developer · Architect · Creator of Tlamatini
#
#   Every line of this file was written by Angela López Mendoza.
# ═══════════════════════════════════════════════════════════════════
#   Tlamatini Author Banner — do not remove (releases scrub the name automatically)
"""One Catalog-of-Prompts example: a Step-by-Step, hold-your-hand wizard that walks
a NON-technical (first-time) user through the WHOLE Zavuerer journey in SIX beats,
exactly as Angela framed it:

  1. OBTAIN the Zavu API key (with the clickable https://www.zavu.dev link),
  2. PUT it in the Config -> Access Keys Wizard -> "Unified Messaging (Zavu)" dialog,
  3. RUN THE DOCTOR (chat_agent_zavuerer action='health') to confirm the key works,
  4. WRITE THE MESSAGE (collect who + what, read it back, send nothing yet),
  5. RUN A TEST send to the user's OWN number first,
  6. SEND the first little "mensajito" for real.

Appended at idPrompt=100 (the #prompts-catalog dropdown enumerates prompt-1..N and
breaks at the first gap, so we take MAX+1). Its wording ("chat_agent_zavuerer" +
"step-by-step" + "Tick ... checkboxes" + "Wizard") makes the catalog mode-classifier
light up Multi-Turn + Exec report + Step-by-Step on click.
"""
from django.db import migrations


GET_KEY_WIZARD_PROMPT = (
    "Tlamatini, hold my hand and set up **Zavuerer** with me from zero so I can text / WhatsApp / "
    "email someone from ONE single key. I am NOT technical, so do EXACTLY ONE step at a time, in the "
    "simplest possible words, then STOP and WAIT until I reply 'READY' before the next step. Tick the "
    "**Multi-Turn**, **Exec report** and **step-by-step** checkboxes for this.\n\n"
    "STEP 1 — OBTAIN YOUR KEY (just click): tell me to open this link in my browser and click "
    "**Sign up** — sign-up is free and needs no card (but Zavu charges a small fee per message you send):  https://www.zavu.dev  . Then have me sign in, "
    "open my **Dashboard → API Keys**, click **Create key**, and **Copy** the key. Tell me to paste "
    "that key here in the chat so we keep it handy. Then STOP and WAIT for me to reply 'READY'.\n\n"
    "STEP 2 — PUT THE KEY IN THE DIALOG: walk me click-by-click — open the top menu **Config → Access "
    "Keys Wizard**, find the **\"Unified Messaging (Zavu)\"** box, paste my key into it, and click "
    "**Save**. Then tell me to fully close and reopen Tlamatini so it loads the new key. Then STOP and "
    "WAIT for me to reply 'READY'.\n\n"
    "STEP 3 — RUN THE DOCTOR: run chat_agent_zavuerer with action='health' and tell me in plain words "
    "**YES, the key works** or **NO, it is still missing**. If it is still missing, gently send me back "
    "to STEP 2. Then STOP and WAIT for me to reply 'READY'.\n\n"
    "STEP 4 — WRITE THE MESSAGE: ask me WHO I want to reach (a phone number, or an email) and WHAT I "
    "want to say. Collect both, read them back to me so I can confirm, and do NOT send anything yet. "
    "Then STOP and WAIT for me to reply 'READY'.\n\n"
    "STEP 5 — RUN A TEST (to me first, so nothing embarrassing goes out): send my message to MY OWN "
    "number first with chat_agent_zavuerer (action='send', channel='auto', to=<my own number>, "
    "text=<my message>). Tell me which channel Zavu used and whether it arrived. Then STOP and WAIT "
    "for me to reply 'READY'.\n\n"
    "STEP 6 — SEND THE LITTLE MENSAJITO: now send the same message for real to the person I named in "
    "STEP 4, with chat_agent_zavuerer (action='send', channel='auto', to=<their number or email>, "
    "text=<my message>), tell me it is on its way, and celebrate with me. 🎉\n\n"
    "Rules: ONE step, then wait for my 'READY' — never skip ahead, never dump everything at once. Use "
    "ONLY chat_agent_zavuerer for the agent work. No code, no jargon — just the click, the link, and "
    "the plain-words result. End with END-RESPONSE."
)

_NEW_PROMPTS = (GET_KEY_WIZARD_PROMPT,)


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
    dependencies = [('agent', '0162_add_zavuerer_catalog_prompts')]
    operations = [migrations.RunPython(add_prompts, remove_prompts)]
