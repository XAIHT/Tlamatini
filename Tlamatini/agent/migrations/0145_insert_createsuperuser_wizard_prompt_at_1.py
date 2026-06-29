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

# Insert the "create a new Tlamatini user" wizard as catalog slot #1 — the VERY
# FIRST request in the #prompts-catalog dropdown. That dropdown
# (static/agent/js/tools_dialog.js) enumerates prompt-1, prompt-2, … and BREAKS at
# the first gap, so a true top-of-list insert must SHIFT every existing prompt
# (idPrompt >= 1) up by one before the new row is written, and shift them back
# down on reverse. promptName stays in lock-step with idPrompt (prompt-<id>).
# Mechanics mirror 0144_insert_java17_maven_demo_prompt_at_5 (INSERT_AT was 5
# there; here it is 1 so the shift covers the whole catalog).
INSERT_AT = 1

# ---------------------------------------------------------------------------
# The wizard request (catalog slot #1).
#
# Nature: Multi-Turn + Exec-Report + STEP-BY-STEP. The catalog classifier
# (tools_dialog.js::classifyPromptModes) badges it Multi-turn / Step-by-Step /
# Exec-report from the keywords below ("Multi-Turn", "Step-by-Step setup wizard",
# "chat_agent_executer") and, on click, ticks those three toolbar checkboxes
# (applyPromptModesToToggles). It contains NO acp_* / skill tokens, so it is NOT
# badged ACPX.
#
# What it makes Tlamatini do (as a hands-on operator, one action at a time): run
# Django's `createsuperuser` in a VISIBLE forked console — chat_agent_executer
# with execute_forked_window=true + non_blocking=true — auto-detecting INSTALLED
# (frozen → "<root>\Tlamatini.exe createsuperuser") vs SOURCE
# (→ "python manage.py createsuperuser"). The app root is the parent of the Temp
# folder Tlamatini pins as %TLAMATINI_TEMP% (identical in both modes), and the
# frozen exe dispatches management commands exactly like manage.py does for the
# post-update migrate. The user types the PASSWORD only into that real console,
# never into chat, then restarts Tlamatini. Raw triple-quoted so the embedded
# Windows paths (back-slashes) and HTML/quotes need no escaping.
# ---------------------------------------------------------------------------
WIZARD_PROMPT = r"""Tlamatini, help me step by step to create a NEW user (a login account) for you, named "----<set name here>----".

This is a Step-by-Step setup wizard — keep the Multi-Turn, Exec Report AND Step-by-Step checkboxes ticked (clicking this card in the catalog already ticks all three for you). Act as a hands-on operator: do ONE action, then WAIT for me to reply before the next one. Use ONLY chat_agent_executer for every command here (do NOT use chat_agent_pythonxer). You will run Django's createsuperuser in a VISIBLE, forked foreground console window (execute_forked_window=true and non_blocking=true) opened from the correct location whether I am running an INSTALLED (frozen) build or a SOURCE build. IMPORTANT: never ask me to type my password into this chat — I will type it only into the console window you open.

Step 0 (banner and the username): open your reply with this exact HTML banner: <div style='padding:18px;border-radius:14px;background:linear-gradient(135deg,#1E1B4B 0%,#6D28D9 34%,#0E7490 68%,#34D399 100%);color:#ffffff;font-family:Inter,Segoe UI,sans-serif;text-align:center;text-shadow:0 1px 3px rgba(0,0,0,.5);'><h2 style='margin:0;letter-spacing:2px;'>&#128100; NEW TLAMATINI USER</h2><div style='opacity:.92;margin-top:4px;'>Step-by-step &middot; create a login &middot; you set your own password</div></div>. Then look at the name I put between the dashes in "----<set name here>----": if it STILL literally says "set name here", reply asking me for the username I want and STOP — wait for my answer. On the next turn, if my latest reply is a bare username such as alice, admin, or dev1, treat that reply as <USERNAME> and continue to Step 1. Otherwise greet me by that username (call it <USERNAME> below) and continue to Step 1.

Step 1 (detect my mode — one quick check): call chat_agent_executer with script='if exist "%TLAMATINI_TEMP%\..\Tlamatini.exe" (echo TLAMATINI_MODE=FROZEN) else (echo TLAMATINI_MODE=SOURCE)' and execute_forked_window=false and non_blocking=false. Read TLAMATINI_MODE (FROZEN or SOURCE) from the result — you reuse it in Step 2 and Step 4. (The app root is the parent of the Temp folder I pin as %TLAMATINI_TEMP%, the same in both modes; the frozen Tlamatini.exe runs management commands just like manage.py does.)

Step 2 (open the createsuperuser console, then WAIT): open the interactive console with chat_agent_executer, execute_forked_window=true and non_blocking=true, using the script for the mode you detected:
 - If FROZEN: script='pushd "%TLAMATINI_TEMP%\.." && "%TLAMATINI_TEMP%\..\Tlamatini.exe" createsuperuser & echo. & echo ============ When the console shows "Superuser created successfully" come back to Tlamatini and type DONE ============ & pause'
 - If SOURCE: script='pushd "%TLAMATINI_TEMP%\..\Tlamatini" && python manage.py createsuperuser & echo. & echo ============ When the console shows "Superuser created successfully" come back to Tlamatini and type DONE ============ & pause'
After you launch it, tell me — in one short, friendly block — exactly this: "A console window just opened on your desktop. In that window: (1) it shows a username prompt — press Enter to accept <USERNAME> (or type it if it is blank), (2) the email address is optional — just press Enter to skip it, (3) type a password and press Enter, then (4) type the SAME password again to confirm. When it prints 'Superuser created successfully', come back here and reply DONE. If anything went wrong, paste what the console says and reply ERROR. If NO window appeared, reply NOWINDOW." Then STOP and WAIT for my reply — do not continue on your own.

Step 3 (react to my reply):
 - If I reply DONE → go to Step 4.
 - If I reply ERROR and paste the message → tell me the one-line fix (for example: "That username is already taken" → suggest a different name; "This password is too short / too common / entirely numeric" → use a longer mixed password), then RE-OPEN the console exactly as in Step 2 and WAIT again.
 - If I reply NOWINDOW → give me this manual fallback and WAIT: "Press the Windows key + R, type cmd and press Enter. In the black window, paste this one line and press Enter:" then paste the SAME command for my mode from Step 2 but WITHOUT the trailing " & echo. & echo ... & pause" part (just the pushd && createsuperuser part). Then: "Create the user there; when you see 'Superuser created successfully', reply DONE."

Step 4 (confirm and restart — final): render a compact HTML success panel (reuse the Step 0 gradient) that shows, in big letters, "&#9989; USER <USERNAME> READY" and underneath one line: "Now restart Tlamatini so your new login is active." Then give me the restart steps for my mode:
 - If FROZEN: "Close Tlamatini (close its console window — the one titled 'Tlamatini'), then start it again from your Desktop or Start-menu shortcut. When it is back up, open http://localhost:8000/ and sign in as <USERNAME> with the password you just set."
 - If SOURCE: "Go to the terminal that is running the server and press Ctrl+C to stop it, then start it again with: python manage.py runserver. When it is back up, open http://127.0.0.1:8000/ and sign in as <USERNAME> with the password you just set."
End with END-RESPONSE.
"""


def insert_wizard_at_1(apps, schema_editor):
    Prompt = apps.get_model('agent', 'Prompt')
    # Shift highest-first so each destination id is always free (no PK clash).
    ids = list(
        Prompt.objects.filter(idPrompt__gte=INSERT_AT)
        .order_by('-idPrompt')
        .values_list('idPrompt', flat=True)
    )
    for pid in ids:
        Prompt.objects.filter(idPrompt=pid).update(
            idPrompt=pid + 1, promptName=f'prompt-{pid + 1}'
        )
    Prompt.objects.update_or_create(
        idPrompt=INSERT_AT,
        defaults={'promptName': f'prompt-{INSERT_AT}', 'promptContent': WIZARD_PROMPT},
    )


def remove_wizard_at_1(apps, schema_editor):
    Prompt = apps.get_model('agent', 'Prompt')
    Prompt.objects.filter(idPrompt=INSERT_AT).delete()
    # Shift lowest-first back down to close the gap.
    ids = list(
        Prompt.objects.filter(idPrompt__gt=INSERT_AT)
        .order_by('idPrompt')
        .values_list('idPrompt', flat=True)
    )
    for pid in ids:
        Prompt.objects.filter(idPrompt=pid).update(
            idPrompt=pid - 1, promptName=f'prompt-{pid - 1}'
        )


class Migration(migrations.Migration):
    dependencies = [('agent', '0144_insert_java17_maven_demo_prompt_at_5')]
    operations = [migrations.RunPython(insert_wizard_at_1, remove_wizard_at_1)]
