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


# MANDATORY catalog-of-prompts example for the Multi-Turn agent
# `chat_agent_instant_messaging_doctor` (create_new_agent.md Step 7.8).
# SAFE by design: mode='diagnose' + retry_send=false => the agent only validates
# readiness (tokens / contacts / reachability / templates / webhook) and sends
# NOTHING, so the daily chat regression can run it without messaging anyone.
DEMO = (
    "Tlamatini, run the **INSTANT MESSAGING DOCTOR** demo, please: use ONLY the "
    "chat_agent_instant_messaging_doctor tool to run a SAFE, read-only diagnosis of my "
    "messaging readiness. Set platform='both', mode='diagnose', and retry_send=false so "
    "NOTHING is actually sent - just check the Telegrammer and Whatsapper setup (bot token, "
    "Meta access token, contacts book, recipient reachability, the WhatsApp 24-hour window / "
    "approved templates, and webhook config), then summarize what is healthy and what still "
    "needs fixing. Tick ONLY the Multi-Turn checkbox; use ONLY "
    "chat_agent_instant_messaging_doctor. End with END-RESPONSE."
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
    dependencies = [('agent', '0153_add_chat_agent_instant_messaging_doctor_tool')]
    operations = [migrations.RunPython(add_demo_prompt, remove_demo_prompt)]
