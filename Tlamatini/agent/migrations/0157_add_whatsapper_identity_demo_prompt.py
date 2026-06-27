from django.db import migrations


# Catalog-of-prompts example for the Multi-Turn agent `chat_agent_whatsapper`
# (create_new_agent.md Step 7.8). It showcases the new `provider` knob, which
# chooses WHICH NUMBER sends the WhatsApp message:
#   * provider='me' (== web) -> sent from the user's OWN personal number via
#     WhatsApp Web (no templates / no System User; one-time QR login).
#   * provider='cloud'       -> sent from the business number via the Meta Cloud API.
# This demo targets contact_name='me' so it only ever messages the operator, and
# it instructs Tlamatini to STOP (not loop / not reopen a browser) if personal
# mode isn't set up yet -- SAFE for the daily chat regression.
DEMO_WA_AS_ME = (
    "Tlamatini, run the **WHATSAPP 'AS ME' demo**: send ONE short WhatsApp message "
    "to MYSELF, FROM MY OWN number (not the business number). Use ONLY the "
    "chat_agent_whatsapper tool with mode='send', provider='me' (so it goes out via "
    "WhatsApp Web from my own personal number), contact_name='me' (so it reaches only "
    "me), and message='Hi from my own WhatsApp - Whatsapper personal-mode test'.\n"
    "\n"
    "Safety: provider='me' uses WhatsApp Web and needs a one-time QR login. If my "
    "WhatsApp Web personal mode is NOT set up yet (no login, or no 'me' contact), do "
    "NOT keep retrying and do NOT reopen anything - just tell me it could not send "
    "because personal mode isn't set up, and stop. Do not message anyone other than me.\n"
    "\n"
    "Tick ONLY the Multi-Turn checkbox; use ONLY chat_agent_whatsapper. "
    "End with END-RESPONSE."
)

_NEW_PROMPTS = (DEMO_WA_AS_ME,)


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
    dependencies = [('agent', '0156_add_telegrammer_identity_demo_prompts')]
    operations = [migrations.RunPython(add_demo_prompts, remove_demo_prompts)]
