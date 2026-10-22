<!-- Tlamatini Author Banner — Created by Angela López Mendoza · @angelahack1 -->
# Create a Tlamatini login account

Current source: **v1.90.0**, inspected at `d274f89c` on 2026-10-22.
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
