# Tlamatini Author Banner — Created by Angela López Mendoza · @angelahack1
"""Make the account wizard explicitly request its local graphical checkpoints."""

import base64
import importlib
import json

from django.db import migrations


# Compare with the exact shipped text, so an installation's edited catalog card
# is never silently replaced. Keep historical migrations immutable.
_previous = importlib.import_module(
    "agent.migrations.0185_standardize_prompt_params_batch3"
)
OLD_WIZARD_PROMPT = json.loads(base64.b64decode(_previous._NEW_B64).decode("utf-8"))["1"]

LOCAL_ALERTS = """Graphical checkpoints: I explicitly request local graphical Notifier alerts during this wizard. Use chat_agent_notifier for the checkpoint alerts below, in addition to chat_agent_executer for commands. Each alert must be a real tool call with target.mode='oneshot', target.search_strings set to the checkpoint label, target.outcome_detail set to its short non-secret instruction, and target.sound_enabled=true. These are local in-browser dialogs, not email, Telegram, WhatsApp or other external messages. Never substitute an HTML chat panel for the graphical Notifier. The optional account email field authorizes no external message. Report an actual Notifier tool error in chat without claiming delivery or repeating the account-creation command. Only one alert per checkpoint occurrence; a new Continue or unrelated reply does not repeat it. The wizard is incomplete while waiting for my input, and no success alert is permitted before the success confirmation described in Step 3.

"""


def _replace_once(text, old, new):
    if text.count(old) != 1:
        raise ValueError("The shipped user-wizard checkpoint no longer matches its migration baseline")
    return text.replace(old, new, 1)


WIZARD_PROMPT = _replace_once(
    OLD_WIZARD_PROMPT, "Step 0 (banner and the username):",
    LOCAL_ALERTS + "Step 0 (banner and the username):",
)
WIZARD_PROMPT = _replace_once(
    WIZARD_PROMPT,
    "if it STILL shows the [[ ]] brackets, reply asking me for the username I want and STOP",
    "if it STILL shows the [[ ]] brackets, call chat_agent_notifier with "
    "target.mode='oneshot' and target.search_strings='Username needed' and "
    "target.outcome_detail='Choose the username for the new Tlamatini account in chat. "
    "Keep passwords in the console only.' and target.sound_enabled=true, "
    "then reply asking me for the username I want and STOP",
)
WIZARD_PROMPT = _replace_once(
    WIZARD_PROMPT,
    "After you launch it, tell me — in one short, friendly block — exactly this:",
    "If the launch tool reports an error, follow the ERROR branch below and do not "
    "announce that a console opened. After a successful launch result, call "
    "chat_agent_notifier with target.mode='oneshot' and "
    "target.search_strings='Console input needed' and "
    "target.outcome_detail='Complete the account prompts in the console. Keep your "
    "password there. Reply DONE in chat only after the console reports success; "
    "reply ERROR for a failure or NOWINDOW if the console did not appear.' and "
    "target.sound_enabled=true. Then tell me — in one short, friendly block — this:",
)
WIZARD_PROMPT = _replace_once(
    WIZARD_PROMPT,
    "A console window just opened on your desktop. In that window: (1) it shows a "
    "username prompt — press Enter to accept {{ the username }} (or type it if it is blank)",
    "The console launch was requested. In that window: (1) read the username "
    "prompt and type {{ the username }} if its shown default differs; press Enter "
    "only when the intended username is selected",
)
WIZARD_PROMPT = _replace_once(
    WIZARD_PROMPT,
    " - If I reply DONE → go to Step 4.",
    " - If I reply DONE after seeing the actual console message 'Superuser created "
    "successfully' → call chat_agent_notifier with target.mode='oneshot' and "
    "target.search_strings='User ready' and target.outcome_detail='You confirmed "
    "that the console created the account successfully. Follow the restart and "
    "login instructions in chat.' and target.sound_enabled=true, then go to Step 4. "
    "If DONE is ambiguous or I did not see that success message, ask for that "
    "confirmation and WAIT; a launched window or a typed command is not success.",
)
WIZARD_PROMPT = _replace_once(
    WIZARD_PROMPT,
    " - If I reply ERROR and paste the message → tell me the one-line fix",
    " - If I reply ERROR and paste the non-secret message, or the launch tool "
    "reports an error → call chat_agent_notifier with target.mode='oneshot' and "
    "target.search_strings='Error creating user' and "
    "target.outcome_detail='Account setup needs attention. Read the non-secret "
    "error and the next step in chat; account creation is not confirmed.' and "
    "target.sound_enabled=true. Then tell me the one-line fix",
)
WIZARD_PROMPT = _replace_once(
    WIZARD_PROMPT,
    "then RE-OPEN the console exactly as in Step 2 and WAIT again.",
    "then check whether the existing console is still accepting input. If it is, "
    "guide me there and WAIT. Otherwise offer one retry of Step 2 after my "
    "confirmation; do not repeatedly open consoles or recreate an account.",
)
WIZARD_PROMPT = _replace_once(
    WIZARD_PROMPT,
    " - If I reply NOWINDOW → give me this manual fallback and WAIT:",
    " - If I reply NOWINDOW → call chat_agent_notifier with target.mode='oneshot' "
    "and target.search_strings='Warning: console not visible' and "
    "target.outcome_detail='The account console did not appear. Follow the manual "
    "console instructions in chat; account creation is not confirmed.' and "
    "target.sound_enabled=true. Then give me this manual fallback and WAIT:",
)


def apply_update(apps, schema_editor):
    Prompt = apps.get_model("agent", "Prompt")
    Prompt.objects.filter(idPrompt=1, promptContent=OLD_WIZARD_PROMPT).update(
        promptContent=WIZARD_PROMPT
    )


def reverse_update(apps, schema_editor):
    Prompt = apps.get_model("agent", "Prompt")
    Prompt.objects.filter(idPrompt=1, promptContent=WIZARD_PROMPT).update(
        promptContent=OLD_WIZARD_PROMPT
    )


class Migration(migrations.Migration):
    dependencies = [("agent", "0218_add_interactor_tool")]
    operations = [migrations.RunPython(apply_update, reverse_update)]
