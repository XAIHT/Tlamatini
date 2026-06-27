from django.db import migrations


# REDESIGN of the messaging demo prompts (Telegrammer + Whatsapper).
#
# The first version hardcoded `contact_name='me'`, which confused users: they
# edited the story ("send to Cosapi") but the actual recipient stayed 'me', so
# the message went to themselves. These rewrites put a CLEAR, fill-in-the-blank
# [[ ... ]] placeholder for the TARGET CONTACT NAME, and state plainly that the
# name must already be saved in the contacts book (contacts.json).
#
# Style mirrors the proven 0155 contact-scaffold prompt: while the [[ ... ]]
# brackets are still present (unfilled), the agent STOPS and sends nothing — so
# these remain SAFE for the daily chat regression. [[ ]] (no angle brackets) so
# an HTML card preview can't eat the markers.

TG_AS_ME = (
    "Tlamatini, send ONE Telegram message FROM MY OWN account (as me, NOT the bot).\n"
    "\n"
    "FILL THESE IN — replace the text inside the [[ ]] brackets:\n"
    "- SEND TO:  [[ TYPE THE CONTACT NAME HERE — this person MUST already be saved in my "
    "contacts book (contacts.json) with a Telegram @username ]]\n"
    "- MESSAGE:  [[ TYPE THE MESSAGE TO SEND HERE ]]\n"
    "\n"
    "SAFETY CHECK FIRST: if the SEND TO line still shows the [[ ]] brackets (I have not filled "
    "it in), do NOT send anything — just tell me to type a contact name that exists in my "
    "contacts book, and stop. If I typed a name that is NOT in contacts.json, do NOT guess or "
    "invent a handle — tell me that name isn't in my contacts so I can add it first, and stop.\n"
    "\n"
    "THEN send it using ONLY the chat_agent_telegrammer tool with mode='send', provider='me' "
    "(so it goes out from MY OWN Telegram account — the very first time this opens a one-time "
    "phone-login window), contact_name = the name I typed in SEND TO, and message = the text I "
    "typed in MESSAGE.\n"
    "\n"
    "Tick ONLY the Multi-Turn checkbox; use ONLY chat_agent_telegrammer. End with END-RESPONSE."
)

TG_AS_BOT = (
    "Tlamatini, send ONE Telegram message AS THE BOT (NOT from my own account).\n"
    "\n"
    "FILL THESE IN — replace the text inside the [[ ]] brackets:\n"
    "- SEND TO:  [[ TYPE THE CONTACT NAME HERE — this person MUST already be saved in my "
    "contacts book (contacts.json) with a Telegram @username, AND must have pressed Start / "
    "messaged my bot at least once (a bot cannot message a stranger) ]]\n"
    "- MESSAGE:  [[ TYPE THE MESSAGE TO SEND HERE ]]\n"
    "\n"
    "SAFETY CHECK FIRST: if the SEND TO line still shows the [[ ]] brackets (I have not filled "
    "it in), do NOT send anything — just tell me to type a contact name that exists in my "
    "contacts book, and stop. If I typed a name that is NOT in contacts.json, do NOT guess or "
    "invent a handle — tell me that name isn't in my contacts so I can add it first, and stop.\n"
    "\n"
    "THEN send it using ONLY the chat_agent_telegrammer tool with mode='send', provider='bot' "
    "(so it goes out FROM THE BOT via the official Bot API), contact_name = the name I typed in "
    "SEND TO, and message = the text I typed in MESSAGE.\n"
    "\n"
    "Tick ONLY the Multi-Turn checkbox; use ONLY chat_agent_telegrammer. End with END-RESPONSE."
)

WA_AS_ME = (
    "Tlamatini, send ONE WhatsApp message FROM MY OWN number (as me, WhatsApp Web personal mode).\n"
    "\n"
    "FILL THESE IN — replace the text inside the [[ ]] brackets:\n"
    "- SEND TO:  [[ TYPE THE CONTACT NAME HERE — this person MUST already be saved in my "
    "contacts book (contacts.json) with a WhatsApp number ]]\n"
    "- MESSAGE:  [[ TYPE THE MESSAGE TO SEND HERE ]]\n"
    "\n"
    "SAFETY CHECK FIRST: if the SEND TO line still shows the [[ ]] brackets (I have not filled "
    "it in), do NOT send anything — just tell me to type a contact name that exists in my "
    "contacts book, and stop. If I typed a name that is NOT in contacts.json, do NOT guess or "
    "invent a number — tell me that name isn't in my contacts so I can add it first, and stop.\n"
    "\n"
    "THEN send it using ONLY the chat_agent_whatsapper tool with mode='send', provider='me' "
    "(so it goes out from MY OWN number via WhatsApp Web — the very first time this needs the "
    "one-time QR login), contact_name = the name I typed in SEND TO, and message = the text I "
    "typed in MESSAGE.\n"
    "\n"
    "Tick ONLY the Multi-Turn checkbox; use ONLY chat_agent_whatsapper. End with END-RESPONSE."
)

# old distinctive marker (from migrations 0156/0157) -> the redesigned content.
_REWRITES = (
    ("**TELEGRAM 'AS ME' demo**", TG_AS_ME),
    ("**TELEGRAM 'AS THE BOT' demo**", TG_AS_BOT),
    ("**WHATSAPP 'AS ME' demo**", WA_AS_ME),
)


def redesign_prompts(apps, schema_editor):
    Prompt = apps.get_model('agent', 'Prompt')
    for marker, new_text in _REWRITES:
        # Update the row 0156/0157 seeded (matched by its old title marker),
        # preserving its idPrompt / promptName so the catalog stays contiguous.
        for row in Prompt.objects.filter(promptContent__contains=marker):
            row.promptContent = new_text
            row.save(update_fields=['promptContent'])


def noop(apps, schema_editor):
    # No need to restore the old, confusing text on reverse.
    pass


class Migration(migrations.Migration):
    dependencies = [('agent', '0157_add_whatsapper_identity_demo_prompt')]
    operations = [migrations.RunPython(redesign_prompts, noop)]
