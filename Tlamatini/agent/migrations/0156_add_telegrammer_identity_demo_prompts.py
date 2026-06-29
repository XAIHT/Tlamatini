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


# Catalog-of-prompts examples for the Multi-Turn agent `chat_agent_telegrammer`
# (create_new_agent.md Step 7.8). They showcase the ONE new knob: `provider`,
# which chooses WHICH IDENTITY sends the Telegram message.
#   * DEMO_AS_ME  -> provider='me'  -> sent AS the user's OWN Telegram account.
#   * DEMO_AS_BOT -> provider='bot' -> sent BY the bot via the Bot API.
# Both target contact_name='me' (the configured default chat = yourself), so the
# message goes to YOU and to nobody else -- SAFE for the daily chat regression.
# If no Telegram credentials are configured (dev box has placeholders), the agent
# reports it could not send and exits cleanly; it never crashes.
DEMO_AS_ME = (
    "Tlamatini, run the **TELEGRAM 'AS ME' demo**: send ONE short Telegram message "
    "to MYSELF, sent FROM MY OWN account (not the bot). Use ONLY the "
    "chat_agent_telegrammer tool with mode='send', provider='me' (so it goes out as "
    "my own logged-in Telegram account), contact_name='me' (my configured default "
    "chat, so it reaches only me), and "
    "message='Hi from my own account - Telegrammer dual-identity test'.\n"
    "\n"
    "Safety: if my Telegram credentials are not set up yet, do NOT treat that as a "
    "failure to fix - just tell me it could not send because the account/session "
    "isn't configured, and stop. Do not message anyone other than me.\n"
    "\n"
    "Tick ONLY the Multi-Turn checkbox; use ONLY chat_agent_telegrammer. "
    "End with END-RESPONSE."
)

DEMO_AS_BOT = (
    "Tlamatini, run the **TELEGRAM 'AS THE BOT' demo**: send ONE short Telegram "
    "message to MYSELF, sent BY THE BOT (not from my own account). Use ONLY the "
    "chat_agent_telegrammer tool with mode='send', provider='bot' (so it goes out "
    "from the bot via the official Bot API), contact_name='me' (my configured "
    "default chat, so it reaches only me), and "
    "message='Hi from the bot - Telegrammer dual-identity test'.\n"
    "\n"
    "Safety: a bot can only message me if I have pressed Start / messaged the bot "
    "before. If the bot token isn't set or the bot cannot reach me, do NOT keep "
    "retrying - just tell me why it could not send and stop. Do not message anyone "
    "other than me.\n"
    "\n"
    "Tick ONLY the Multi-Turn checkbox; use ONLY chat_agent_telegrammer. "
    "End with END-RESPONSE."
)

_NEW_PROMPTS = (DEMO_AS_ME, DEMO_AS_BOT)


def add_demo_prompts(apps, schema_editor):
    Prompt = apps.get_model('agent', 'Prompt')
    for content in _NEW_PROMPTS:
        if Prompt.objects.filter(promptContent=content).exists():
            continue
        next_id = (Prompt.objects.order_by('-idPrompt').values_list('idPrompt', flat=True).first() or 0) + 1
        Prompt.objects.update_or_create(
            idPrompt=next_id,
            defaults={'promptName': f'prompt-{next_id}', 'promptContent': content},
        )


def remove_demo_prompts(apps, schema_editor):
    Prompt = apps.get_model('agent', 'Prompt')
    Prompt.objects.filter(promptContent__in=list(_NEW_PROMPTS)).delete()


class Migration(migrations.Migration):
    dependencies = [('agent', '0155_add_contact_scaffold_demo_prompt')]
    operations = [migrations.RunPython(add_demo_prompts, remove_demo_prompts)]
