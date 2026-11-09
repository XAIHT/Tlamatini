# Tlamatini Author Banner — Created by Angela López Mendoza · @angelahack1
"""Use the exact instance's interactive account command, without model polling."""

from importlib import import_module

from django.db import migrations


_previous = import_module('agent.migrations.0219_user_wizard_graphical_notifications')
OLD_WIZARD_PROMPT = _previous.WIZARD_PROMPT
WIZARD_PROMPT = """Tlamatini, help me create a NEW ADMINISTRATIVE user with your integrated account wizard.
Username: [[ TYPE THE USERNAME HERE, e.g. alice ]]
This is a Step-by-Step setup wizard. Keep Multi-Turn, Exec Report and Step-by-Step enabled. I will enter the password only in the console, never in chat.

Open the console as the first operational step. With the username supplied, launch in this same turn; do not ask me to confirm the runtime or wait for screenshot analysis. The complete shipped card is handled directly by this instance, without asking a model to build a command or invoking auxiliary agents.
If the username is missing, ask only for that name and wait. Treat my next bare username as the answer and continue with the console opening. Explain that createsuperuser creates an administrative account.

Use this running instance's canonical executable and Django project directory. In a source run, use the exact running Python and absolute manage.py path. In an installed run, use this instance's executable. Run the integrated createuserconsole command: it uses Django's real createsuperuser interaction, model and migration checks, duplicate-name checks and password validation. Never select another installation using PATH, inherited temporary-directory variables or a global filesystem search. Never interpolate a username or password into shell text.

Open one visible interactive console and return control to me immediately. I enter the username, optional email, password and repeated password there. Wait for DONE, ERROR or NOWINDOW. Do not capture the credentials console, run Image-Interpreter, poll agents, or open another console while this one is active. A requested launch alone does not confirm that a window appeared or that an account was created.

DONE: verify that the named administrative account was actually created in this instance during this wizard. If it is not confirmed, explain that and wait; never claim success from a launch result.
ERROR: keep the existing console if it is accepting input; report the non-secret error and wait. Never send a password through chat.
NOWINDOW: try to bring the owned console forward; do not repeatedly create windows. If it closed, I may send this card again to retry.

Once creation is confirmed, show USER READY and tell me to sign out and sign in using the SAME browser address. A newly created Django account works without restarting the server. Never close the Spanish edition or another application's processes.
End with END-RESPONSE.
"""


def repair(apps, schema_editor):
    rows = apps.get_model('agent', 'Prompt').objects.using(schema_editor.connection.alias)
    rows.filter(pk=1, promptContent=OLD_WIZARD_PROMPT).update(promptContent=WIZARD_PROMPT)


def reverse(apps, schema_editor):
    rows = apps.get_model('agent', 'Prompt').objects.using(schema_editor.connection.alias)
    rows.filter(pk=1, promptContent=WIZARD_PROMPT).update(promptContent=OLD_WIZARD_PROMPT)


class Migration(migrations.Migration):
    dependencies = [('agent', '0222_replace_mistral_large3')]
    operations = [migrations.RunPython(repair, reverse)]
