<!-- Tlamatini Author Banner — Created by Angela López Mendoza · @angelahack1 -->
# Account-wizard verification — 2026-11-09

Latest released version: **1.92.4**. [Account-wizard usage](user-creation-wizard.md).

## Final visible acceptance cohort

The final run created **10 real English accounts and 10 real Spanish accounts**,
then authenticated each through the application's actual login page. All
**260 acceptance assertions passed**. Each edition ran the same 13 checks for
each of its 10 accounts: **0 differing pass/fail outcomes across the 130 paired
checks**. This is a bounded account-wizard comparison, not a claim about all
127 catalog prompts or the complete products.

| Edition | Final cohort | Real accounts created and authenticated | Assertions | Send → readable username prompt | Send → confirmed foreground |
| --- | --- | --- | --- | --- | --- |
| English | `visible-en-20261109-161020` | 10/10 | 130/130 | 2.351–3.961 s | 2.356–3.966 s |
| Spanish | `visible-es-20261109-160742` | 10/10 | 130/130 | 2.241–3.153 s | 2.245–3.156 s |

All 20 owned consoles were already in front when the harness checked:
`foreground_before_test_focus=true`, `test_focus_requested=false` in every
record. Therefore none of these final launch measurements depended on the
test bringing a hidden console forward. Readable-window readiness and actual
foreground exposure were measured separately, both from the browser's real
Send action and both below the 30-second limit.

These are the **final cohorts**, not the total number of accounts in the test
databases. Earlier QA cohorts and the separately prepared test operator remain
separate. The operator was fixture setup; it is not counted among the 20
interactively created accounts.

## English measurements

Account names are `qa_wiz_en_20261109161020_01` through
`qa_wiz_en_20261109161020_10`. Times below are seconds.

| Trial | Username prompt ready | Actual foreground | DONE verification | Test-assisted focus | Result |
| --- | --- | --- | --- | --- | --- |
| 1 | 3.034 | 3.036 | 0.138 | No | PASS |
| 2 | 2.724 | 2.726 | 0.083 | No | PASS |
| 3 | 2.412 | 2.415 | 0.091 | No | PASS |
| 4 | 2.796 | 2.798 | 0.101 | No | PASS |
| 5 | 3.047 | 3.050 | 0.080 | No | PASS |
| 6 | 3.894 | 3.898 | 0.093 | No | PASS |
| 7 | 3.961 | 3.966 | 0.142 | No | PASS |
| 8 | 2.633 | 2.637 | 0.128 | No | PASS |
| 9 | 3.880 | 3.885 | 0.198 | No | PASS |
| 10 | 2.351 | 2.356 | 0.098 | No | PASS |

Every Spanish HECHO verification also completed in
0.077–0.227 seconds. Both editions verified the newly
persisted account before reporting completion.

## What was exercised

1. Select the actual catalog card and its execution modes in the visible browser.
2. Send it through the real application WebSocket.
3. Observe the owned Django username prompt within 30 seconds.
4. Confirm its window is visible, unminimized and actually in the foreground.
5. Confirm chat has yielded while the console waits for human input.
6. Enter a username and observe Django's email field.
7. Enter an email and observe the real password field.
8. Observe Django's repeated-password field.
9. Observe Django's actual account-creation success message.
10. Check that the password was not echoed into console text.
11. Read the fixture database to verify the account, administrative flags and
    stored password hash.
12. Send DONE/HECHO through chat and verify the actual newly created account.
13. Authenticate that account through the normal browser login form.

No session cookies were injected and no tool responses were substituted.
The test typed into the owned real console and used real password validation,
database persistence and browser authentication. Database inspection verified
the result; it did not create the 20 acceptance accounts.

The closed wizard path calls no model or vision agent to construct or execute
its command. Ordinary application startup and context-gauge model requests can
still occur elsewhere; this report does not claim the entire server made no
background model calls. The account password was entered only in the console
and normal login form, never as chat content or a command argument.

## Corrections covered

- Replaced the shipped-card model-generated command sequence with a closed,
  exact-card native handler. It uses this running instance's executable,
  project directory and Django database, with `shell=False`.
- Removed the PowerShell-versus-CMD ambiguity and the subsequent model/vision
  polling loop from this operation.
- Added `createuserconsole`, a narrow subclass of Django's real
  `createsuperuser`. Model, migration, duplicate-name and password checks
  remain; unrelated web/LLM startup checks do not delay the console.
- Prevented account child processes from truncating the server log or recording
  private interactive input through the shared log tee.
- Routed known account requests before model-readiness/context planning while
  preserving authentication, Ask Execs and cancellation. A declined stale
  candidate cannot fall into an old model chain during a rebuild.
- Scoped username/status followups to the preceding owned wizard reply.
  Completion retires that conversation state. Owned live handles protect
  intentional console input from orphan and watchdog cleanup.
- Preserved customized catalog cards; migration 0223 repairs only known defaults.
  The native path reports directly in chat and does not claim historical
  Notifier pop-ups occurred.
- Added explicit frozen hidden imports and archive-presence requirements for
  the handler, command and dynamically imported current/historical catalog
  modules. These source contracts do not constitute a new frozen build.

## Unit tests and lint

| Verification | English | Spanish |
| --- | --- | --- |
| Focused regression suite | 218 passed; 7.138 s | 252 passed; 6.972 s |
| Python compilation | 948 owned sources | 976 owned sources |
| Python Ruff default rules | Passed; exit 0 | Passed; exit 0 |
| JavaScript ESLint | Passed; exit 0 | Passed; exit 0 |
| JavaScript parse checks | 108 files; exit 0 | 110 files; exit 0 |
| Scoped source whitespace check | Passed; exit 0 | Passed; exit 0 |

The unit suites include native intent/state/authorization/cancellation guards,
consumer routing during model rebuilds, Django-command dispatch/privacy/frozen
carriage contracts, catalog-card contracts and previous wizard-intent guards.
Spanish additionally checks its catalog execution-parity migrations. These
edition-specific cases explain the different totals. Cases that mock launch
or OS behavior are **not** additional real-account or visual trials.

Receipts under the evidence root: `unit-en-proof.log` and
`unit-es-proof.log`; `lint-python-en-proof.log` and
`lint-python-es-proof.log`; `lint-js-en-final.log` and
`lint-js-es-final.log`. Their corresponding `.exit` files all contain 0.
`source-diff-en-proof.exit` and `source-diff-es-proof.exit` also contain 0;
that check scopes this repair's source files and honors Windows CRLF through
`cr-at-eol`. No JavaScript source changed after its recorded checks.

The final visible batch completed at **2026-11-09 16:14:36 -06:00**, recorded in
`final-verification-complete.txt`. Its final inventory found **0 test-port
listeners and 0 fixture processes**. The visible developer console was left
open with the results; evidence and fixture databases were retained.

## Evidence and limits

Machine-local evidence root:

`C:\Development\XAIHT\Tlamatini-Spanish\Temp\wizard-repair-20261109`

- English: `visible-en-20261109-161020\result.json`.
- Spanish: `visible-es-20261109-160742\result.json`.
- Each cohort contains per-account console screenshots, success screenshots,
  authenticated-browser screenshots, verified-chat screenshots and console text.
- Runner logs: `visible-proof-en.log` and `visible-proof-es.log`.

English ran the current source copied into `source-instance-en` on
`http://127.0.0.1:18058`; Spanish used `source-instance` on
`http://127.0.0.1:18059`. Each fixture had its own database. The existing
installed applications and their user databases were not acceptance targets.
Evidence lives in application-owned development storage, not Windows user-profile
temporary directories; it is not bundled into end-user installations.

The stronger Spanish attempt at 16:04 is retained separately as
`visible-es-20261109-160409`, marked FAIL. Its fifth assertion selected the last
bot card, which was an asynchronous model-ready notice after the real wizard
handoff. The corrected assertion checks the current submission's handoff and
chat readiness. Its failure is not counted as a pass or folded into the final
20-account cohort.

No new executable build or installed-package acceptance was performed here.
The source correction requires a rebuild and installation before it can be
claimed for an existing frozen installation. No commits or pushes were made
as part of this repair and verification.

