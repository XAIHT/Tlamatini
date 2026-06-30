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


# MANDATORY catalog-of-prompts example for the Multi-Turn agent
# `chat_agent_zavuerer` (create_new_agent.md Step 7.8 / agent-creation Phase 19).
# SAFE by design: action='health' only PROBES the Zavu API (a GET) and sends
# NO message to anyone, so the daily chat regression can run it freely even
# without a configured API key (it then reports the one step to fix).
DEMO = (
    "Tlamatini, run the **ZAVUERER** demo, please: use ONLY the chat_agent_zavuerer tool to "
    "run a SAFE health check of my Zavu unified-messaging setup. Set action='health' so "
    "NOTHING is sent to anyone - just probe whether the Zavu API (https://www.zavu.dev) is "
    "reachable and whether my API key is configured, then tell me the status and, if it is "
    "not set up yet, the single step to fix it (get a Zavu API key at https://www.zavu.dev (free sign-up; pay-as-you-go to send) "
    "and paste it into the Zavuerer config). Tick ONLY the Multi-Turn checkbox; use ONLY "
    "chat_agent_zavuerer. End with END-RESPONSE."
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
    dependencies = [('agent', '0160_add_chat_agent_zavuerer_tool')]
    operations = [migrations.RunPython(add_demo_prompt, remove_demo_prompt)]
