<!-- Tlamatini Author Banner — Created by Angela López Mendoza · @angelahack1 -->
# Create a Tlamatini login account

Current source: **v1.91.0**, inspected at `a771d27c` on `main` on 2026-10-23
(tag `ebc5c3b4`; migration 0219 lands after it).
This guide describes the existing catalog wizard and the corrected intent
guards; it does not assert that a particular installed binary has been updated.

## Use the catalog wizard

1. Open Catalog of prompts and choose the NEW user/login-account wizard. Enter
   the desired username in its placeholder. The card enables Multi-Turn,
   Exec Report and Step-by-Step.
2. Tlamatini uses **Executer** to determine source versus installed mode, then
   opens Django's interactive `createsuperuser` command in a visible console.
   The launch uses `execute_forked_window=true` and `non_blocking=true`.
3. Read the username shown by the actual console. Enter the intended username
   if its default differs; email is optional. Type and confirm the password
   only in that console, never in chat. The command creates an administrative
   superuser account; this is not a restricted ordinary-user invitation.
4. Wait for the console's actual success message, then reply **DONE** in chat.
   Reply **ERROR** with the non-secret error text if it fails, or **NOWINDOW**
   if no console appeared. Tlamatini should wait at this boundary.
5. Follow the wizard's restart/login instructions for the detected runtime and
   configured web port. Do not infer success merely because a command was typed
   or a window opened.

The frozen command is `<install>/Tlamatini.exe createsuperuser`; source uses
`python manage.py createsuperuser` from the Django project directory. The
catalog derives its location from the parent of `TLAMATINI_TEMP`. It retains
a manual fallback when a window cannot be opened. It does not ask a model to
collect, generate or transmit the password through chat.

## Local pop-up checkpoints (migration 0219)

Migration 0219 (commit `939acf6b`, on `main` after the `v1.90.0` tag) adds one
explicit request to the catalog card: Tlamatini shows a **local Notifier
pop-up** (an in-browser dialog with sound) at each checkpoint. These are not
email, Telegram, WhatsApp or any other external message, and the optional
email field still authorizes none. The card's own explicit sentence is what
permits these pop-ups; the guard rules below still apply to every other wording.

| Checkpoint | When it appears |
| --- | --- |
| Username needed | The card still shows `[[ ]]` instead of a username. |
| Console input needed | The console launch succeeded; finish the prompts there. |
| Error creating user | You reply ERROR, or the launch tool reports an error. |
| Warning: console not visible | You reply NOWINDOW. |
| User ready | You reply DONE after seeing `Superuser created successfully`. |

Each checkpoint shows one pop-up; a later Continue does not repeat it. No
success pop-up appears before you confirm the console's success message. A
Notifier error is reported in chat, without claiming delivery and without
re-running the account command. After an ERROR the wizard no longer reopens a
console by itself: it checks whether the existing one still accepts input and
offers one retry only after you confirm.

The pop-ups need the Notifier agent enabled in Config ▸ Configure Agents (and
ticked, while Compact mode is on). The migration replaces the card only while
it still matches the shipped text, so a card you edited is left alone;
reversing the migration restores the previous text. Tests in
`agent/test_wizard_intent_guards.py` cover the card, the migration in both
directions and one Notifier call per wizard reply.

## The two guard corrections

The installed log on 2026-10-22 showed Executer selected correctly and then
blocked. “I will type it” referred to the password, but enabled a sticky mode
that reserved all command execution for the user. Tlamatini consequently
switched to Terminater with Enter disabled. The second guard combined
completion wording anywhere in the request with the optional email field and
forced a notification, diverting the answer again.

The corrected terminal guard requires a command object for typing/entering
ownership; ambiguous typing alone is neutral. An explicit instruction to have
Tlamatini run a named program lifts a prior terminal lesson. Real “I will run
the commands” requests still block general runners and force Terminater to
type without pressing Enter.

The notification guard now requires an affirmative outbound instruction in
the same sentence as the completion condition. Email fields, explanations in
chat, quoted examples, negative requests and the user's DONE reply do not
authorize a notification. These runtime rules are also stated in `prompt.pmt`.

## Diagnose an older installation

If the execution report says `NOT run - live-tutorial mode` during this wizard,
inspect the matched phrase in the application log. If the response claims a
completion notification was requested, check for `Notification-debt guard
fired`. Preserve the request and non-secret error evidence. Updating only a
Markdown guide or copying a `.py` file beside an EXE does not replace its frozen
modules; delivery needs a package containing the corrected source.

The focused correction passed 179 tests on 2026-10-22. It includes the real
migrated catalog row, previous tutorial history, source/frozen command choices,
real executor-loop checks with controlled tools, and a replay of the exact
installed request. These tests created no real user and sent no message.
