<!-- Tlamatini Author Banner — Created by Angela López Mendoza · @angelahack1 -->
# Create an administrative Tlamatini account

> Latest released version: **[v1.92.4](changes/2026-11-08-v1.92.4.md)**.

The integrated account wizard opens this instance's real Django account console.
It returns control to the chat while you enter the account details. Passwords
belong only in that console; an accepted launch does not prove that an account
was created.

## Use the catalog wizard

1. Open **Catalog of prompts**, select the first account-creation card and fill
   in the username. Keep Multi-Turn, Exec Report and Step-by-Step enabled.
2. Send the card. With a username supplied, the integrated handler opens the
   console in the same turn. If the name is missing or invalid, it asks for the
   name and accepts your correction without sending that exchange to a model.
3. Enter the intended username, optional email, password and repeated password
   in the console. This creates an administrative superuser, not a restricted
   ordinary-user account.
4. After Django confirms success, reply **DONE**. Use **ERROR** with the non-secret
   error text if it fails, or **NOWINDOW** if the console is not visible.
   HECHO and SIN VENTANA are accepted compatibility aliases.
5. DONE checks the current instance's database for the named active superuser
   created during this wizard. Once confirmed, sign out and sign in at the same
   browser address. No server restart is required.

The shipped card does not wait for the model to become ready, including a model
rebuild triggered by toolbar changes. Ordinary chat still follows its normal
model-readiness requirements. The wizard does not generate shell scripts through
an LLM, run Image-Interpreter, take credential screenshots or poll an agent while
you type.

## Permission, conversation and process boundaries

An active signed-in account is required. **Ask Execs** still asks before launch:
denial, a missing approval broker or cancellation prevents a new console.
Cancellation is checked again after approval.

The next username or status reply belongs to the immediately preceding response
from this wizard. An unrelated conversation does not revive an old account
request. Invalid names are requested again. Completion retires this conversation
state, while the owned live process handle remains protected from the orphan
reaper and command watchdog until the console exits.

Submitting the card again while that console is alive reuses it. NOWINDOW tries
to focus the owned console; it does not create another one. If the console was
closed, sending the card again is an explicit retry. ERROR does not claim success
or automatically repeat account creation. The console stays open after the
command finishes so you can read its result; press Enter to close it.

## Runtime and database selection

The launcher uses the current process's executable and its absolute Django
project directory. It does not select a runtime through PATH, a filesystem search,
an inherited temporary-directory variable or command text supplied in chat.

| Mode | Integrated command |
| --- | --- |
| Source | Exact running Python + absolute `Tlamatini/manage.py createuserconsole` |
| Installed | This installation's `Tlamatini.exe createuserconsole` |

`createuserconsole` is a narrow subclass of Django's real `createsuperuser`.
It retains model and migration checks, duplicate-name checks and password
validation. Unrelated web URL checks do not delay account input. The username
and password are never interpolated into shell text.

The console uses this edition's own database and application-owned directories.
Its startup does not truncate the running application's `tlamatini.log`, and
interactive credential input is not copied to that log. No wizard scratch files
are created under a Windows user profile.

## Catalog compatibility and local notices

Migration **0223_create_superuser_console_handoff** replaces only the exact prior
default card and preserves customized cards and their metadata. The native
handler also recognizes the complete known historical cards with their username
field substituted. Quoted examples, explanations and otherwise customized
instructions remain ordinary requests, not implicit permission to open a console.

The integrated wizard reports waiting, errors and completion **directly in chat**.
It does not invoke Notifier, play Notifier sounds or display its historical
checkpoint pop-ups. Migration 0219 introduced those pop-ups for the old
Executer/Notifier workflow; that historical wording is not a description of the
current native path. Customized requests that explicitly invoke Notifier remain
subject to the existing tool and permission rules.

## Visible source verification — 2026-11-09

The following runs used real browsers, real Django consoles and isolated source
test databases. They created accounts interactively and authenticated the new
accounts through the real login page. They did not substitute tool responses or
inject session cookies.

| Edition | Real accounts created and authenticated | Passed checks | Send → readable username field | Send → actual foreground |
| --- | --- | --- | --- | --- |
| English | 10/10 | 130/130 | 2.351–3.961 seconds | 2.356–3.966 seconds |
| Spanish | 10/10 | 130/130 | 2.241–3.153 seconds | 2.245–3.156 seconds |

These final cohorts verified DONE/HECHO against every newly persisted account
and then authenticated it through the real login form. All 20 consoles were
already in front before any test-assisted focus request; none needed that
assistance. The final paired wizard checks had **0 differing pass/fail outcomes
out of 130 comparisons**.

See the [dated verification report](user-creation-verification-2026-11-09.md)
for per-trial timings, automatic-versus-assisted foreground measurements,
unit/lint evidence, earlier failed attempts and exact limits. Final evidence:

- `C:\Development\XAIHT\Tlamatini-Spanish\Temp\wizard-repair-20261109\visible-en-20261109-161020\result.json`
- `C:\Development\XAIHT\Tlamatini-Spanish\Temp\wizard-repair-20261109\visible-es-20261109-160742\result.json`

The 20 final accounts are distinct from earlier QA cohorts and the fixture
operator; they are not the total account count in those databases. These are
source-instance results, not frozen-build or installed-package acceptance.
Timing starts with the browser submission, not a successful launch response.
Unit cases with mocked OS operations are not additional real-account trials.

## Updating an installed copy

Changing source files or this guide does not update an existing frozen executable.
Rebuild and install a package carrying the corrected modules and migrations before
testing that installed copy. Keep its results separate from the source evidence
above. Do not infer that all other catalog prompts have been validated from this
focused account-wizard verification.

Historical note: the intent-guard correction passed 179 focused tests on
2026-10-22 without creating a real account or sending external messages. That
dated result is retained as history, not evidence for the new native handler.
