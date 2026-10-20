# ═══════════════════════════════════════════════════════════════════════════════
#   ✦  T L A M A T I N I  ✦   —   "one who knows"
#
#   Created by  Angela López Mendoza   ·   @angelahack1
#   Developer · Architect · Creator of Tlamatini
#
#   Every line of this file was written by Angela López Mendoza.
# ═══════════════════════════════════════════════════════════════════════════════
#   Tlamatini Author Banner — do not remove (releases scrub the name automatically)
"""Catalog of Prompts — the three Terminater cards.

Terminater is Multi-Turn-capable, so it is INCOMPLETE without at least one catalog
prompt (``create_new_agent.md`` Step 7.8, a hard completion gate).  Three are
seeded because Terminater has three genuinely different stories and one card
cannot show them all:

  127  FIRST LOOK    — raise a terminal, watch Tlamatini type a read-only command.
  128  HAND-OVER     — Tlamatini types part of a command, the USER types the rest.
  129  GUIDED TOUR   — CMD + PowerShell side by side (tiled), then Tlamatini watches
                       what the user types and warns about a mistake.

Contract compliance:

  * APPEND-ONLY ids: the catalog's highest live id was 126, so these are 127-129.
  * ``category='run_execute'`` ("Run & Execute"): Terminater is the VISIBLE sibling
    of Executer, which already lives there.  ``sort_rank`` 62/64/66 keeps the tool
    families contiguous (Executer-style cards 20-60, then Terminater, then
    NetSpeed at 70) and ranks are unique inside the section; rank 10 stays the
    section's Step-by-Step opener.
  * Parameter grammar v1.44.0: user inputs are ``[[ ... — OPTIONAL, default: X ]]``
    at the TOP with the unfilled-guard sentence beneath, so a one-click demo runs on
    the stated defaults.  ``< >`` marks REPORT slots only.  No hardcoded scratch
    path (Rules 15/16): nothing here writes a file.
  * SAFE and repeatable: the commands only LIST, ECHO or PING; nothing is changed,
    deleted or installed.  The daily chat test may run them.
  * CLASSIFIER MODES (``tools_dialog.js::classifyPromptModes``): 127 and 128 name
    only the Multi-Turn and Exec report checkboxes (no ``acp_*`` token, no
    hyphenated step-by-step token); 129 deliberately names the hyphenated
    Step-by-Step mode, because a guided tour is exactly the cadence Step-by-Step
    exists for.  The literal ``<<USER:...>>`` marker inside 128 is the hand-over
    syntax Tlamatini must pass to the tool; it is not a REPORT slot.

Reverse deletes exactly these three rows.
"""
from django.db import migrations


FIRST_LOOK = (
    "Tlamatini, run the **TERMINATER FIRST LOOK**, please — a REAL terminal you can "
    "watch while I work in it.\n\n"
    "[[ terminal type — OPTIONAL, default: powershell (or write: cmd) ]]\n"
    "(If the value above is still unfilled, use its default and go on without asking.)\n\n"
    "Use ONLY chat_agent_terminater for this. Do NOT use Executer — the point is that I "
    "SEE the commands being typed.\n"
    "1. Raise a terminal: action='open', kind=<the type above>, title='Terminater first "
    "look'. The Terminals area appears under the canvas.\n"
    "2. In that terminal, with action='type', TYPE — key by key, like a person, never "
    "pasted — the command that lists the five most recently changed items of the current "
    "folder. For powershell: Get-ChildItem | Sort-Object LastWriteTime -Descending | "
    "Select-Object -First 5 Name, LastWriteTime — for cmd: dir /o-d\n"
    "3. Wait for it to finish, read the COMPLETE output, and report:\n"
    "   · the terminal id and its type: <terminal_id>, <kind>\n"
    "   · the exact command you typed: <typed>\n"
    "   · the status and the exit code (say plainly that CMD cannot report an exit "
    "code when it is empty): <status>, <exit_code>\n"
    "   · how long it took and the first three lines of the output: <duration>, "
    "<first_lines>\n"
    "4. Leave the terminal OPEN so I can read it.\n\n"
    "PRE-FLIGHT: tick Multi-Turn and Exec report. This command only LISTS files; it "
    "changes nothing. End with END-RESPONSE."
)

HAND_OVER = (
    "Tlamatini, run the **TERMINATER HAND-OVER**, please — you type the beginning of a "
    "command and I type the rest.\n\n"
    "[[ number of echo requests — OPTIONAL, default: 2 ]]\n"
    "(If the value above is still unfilled, use its default and go on without asking.)\n\n"
    "Use ONLY chat_agent_terminater. Do NOT use Executer.\n"
    "1. With action='run', kind='cmd', title='Hand-over demo', type this EXACT text "
    "(the <<USER:...>> marker is the syntax that hands me the keyboard — pass it "
    "literally): ping <<USER:the host to ping, e.g. 127.0.0.1>> -n <the number above>\n"
    "2. Tell me in one sentence, BEFORE the call, that you will type 'ping ' and then "
    "give me the keyboard. In the terminal I will type the host and press Enter; you "
    "then finish the line and run it.\n"
    "3. Wait for the command, read the COMPLETE output and report:\n"
    "   · what you typed and what I typed: <typed>, <user_part>\n"
    "   · the status: <status>\n"
    "   · the last two lines of the ping statistics: <statistics>\n"
    "4. If I do not finish my part in time the status is operator_required — say so "
    "instead of guessing a host. Leave the terminal OPEN.\n\n"
    "PRE-FLIGHT: tick Multi-Turn and Exec report. Ping only sends a few echo requests; "
    "nothing is changed. End with END-RESPONSE."
)

GUIDED_TOUR = (
    "Tlamatini, give me the **TERMINATER GUIDED TOUR**, please — two terminals side by "
    "side, then you watch what I type and help me.\n\n"
    "[[ the command you want me to practise — OPTIONAL, default: Get-Date ]]\n"
    "(If the value above is still unfilled, use its default and go on.)\n\n"
    "Use ONLY chat_agent_terminater, and go ONE action at a time: give me one concrete "
    "step, wait for my READY, then do the next.\n"
    "STEP 1 — open a CMD terminal titled 'Tour CMD' and a PowerShell terminal titled "
    "'Tour PS' (two separate action='open' calls).\n"
    "STEP 2 — tile them next to each other: action='layout', layout='tile-h'. Tell me what "
    "I should see.\n"
    "STEP 3 — in 'Tour CMD' type: ver — and in 'Tour PS' type: "
    "$PSVersionTable.PSVersion — then tell me which version each one reported and that "
    "CMD gives no exit code.\n"
    "STEP 4 — tell me to click into 'Tour PS' and start typing the practice command above "
    "WITHOUT pressing Enter. Then call action='watch_user' (terminal='Tour PS', "
    "until='idle') and tell me exactly what you saw me type. If it looks dangerous or "
    "mistyped, call action='warn_user' instead of running anything.\n"
    "STEP 5 — ask whether to close the tour; on my READY use action='kill' on both "
    "terminals.\n\n"
    "PRE-FLIGHT: tick Multi-Turn, Exec report and Step-by-Step. Nothing in this tour "
    "changes the machine. End with END-RESPONSE."
)

_NEW_PROMPTS = (
    (127, 62, FIRST_LOOK),
    (128, 64, HAND_OVER),
    (129, 66, GUIDED_TOUR),
)


def add_terminater_demo_prompts(apps, schema_editor):
    Prompt = apps.get_model('agent', 'Prompt')
    for prompt_id, rank, content in _NEW_PROMPTS:
        Prompt.objects.update_or_create(
            idPrompt=prompt_id,
            defaults={
                'promptName': 'prompt-%d' % prompt_id,
                'promptContent': content,
                'category': 'run_execute',
                'sort_rank': rank,
            },
        )


def remove_terminater_demo_prompts(apps, schema_editor):
    Prompt = apps.get_model('agent', 'Prompt')
    Prompt.objects.filter(
        idPrompt__in=[prompt_id for prompt_id, _rank, _content in _NEW_PROMPTS]
    ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('agent', '0216_add_chat_agent_terminater_tool'),
    ]

    operations = [
        migrations.RunPython(add_terminater_demo_prompts, remove_terminater_demo_prompts),
    ]
