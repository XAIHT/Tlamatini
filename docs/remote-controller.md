<!-- Tlamatini Author Banner — Created by Angela López Mendoza · @angelahack1 -->
# Tlamatini and Remote-Controller

> Latest released version: **[v1.93.5](changes/2026-11-12-v1.93.5.md)**.

The 13 November source integration connects your Tlamatini account to the separate
**Tlachihuani-RC Server**, managed in XT as **Remote-Controller**. It provides
account-bound text conversations, execution approvals, cancellation and an
installed-application launch path. English and Spanish use the same behavior
with separate account identities.

The current connection profile works **on this PC only**, normally at
`http://127.0.0.1:12481`. Network access, post-quantum transport, independently
trusted native client distribution and phone microphone capture remain unavailable.
Source verification does not certify an updated installed package or the complete
approved remote-access design. Use compatible builds containing both integrations.

## Enable your account and connect a device

1. Open **XT → Show panel → Services → Remote-Controller** and start the service.
   Installation leaves it Manual and stopped. Torrenter has its own controls.
2. On this PC, sign in to the desired Tlamatini account and open
   **Panels → Tlachihuani · Remote-Controller**. The account page opens in another
   tab and remains available while the main chat is busy.
3. Confirm your current Tlamatini password and select **Enable this account**.
   This makes the account available in XT; it does not approve a device or start
   a service. Your password is checked by Tlamatini and is not sent to the RC client.
4. In XT's Remote-Controller **Access** tab, select the account, choose its
   permissions and create an invitation. Open the RC client from XT, enter that
   invitation and compare the **complete device fingerprint** in both places.
   Approve the matching device in XT.

An invitation lasts five minutes and can be used once. The approved device can
reconnect using its signing key without another invitation. The account's display
name is a label; authorization uses immutable identifiers and the edition.
An English account and a Spanish account with the same name are separate.

The address above is loopback: opening it on a phone addresses the phone itself.
This implementation does not make the PC reachable over a LAN or the Internet.

## Conversation and execution control

Send text in the RC client's **Conversation** view. It uses the account's existing
Tlamatini chat engine, history and configuration. Accepted work is shown separately
from a completed answer. A busy desktop conversation and a remote conversation
cannot run overlapping model requests for the same account.

Execution settings expose **Multiturn, Exec-Report, ACPX, Self-Modify, Ask Execs
and Step by step**. Availability comes from the running edition; existing model
capacity and consent rules still apply. The receipt records the effective modes.

The full workspace adapts Chat, Canvas, Downloads, Settings and More for touch,
including Torrenter Sources and Torrenter Workspace. Only Agentic Control Panel,
Prompt Flow Panel and Admin Panel are excluded. Voice/microphone controls in that
workspace operate the host computer; they do not capture the phone microphone.

The workspace renews its approved session when opened, before expiry, and when
you return to it. Concurrent requests share one renewal; an interrupted action
is never replayed automatically. Device revocation still blocks access.

Choose **Load recent conversation** to retrieve this account's saved messages
without sending a new prompt. The response includes at most 40 messages within
a 24,000-byte JSON budget and identifies truncated content. Earlier content stays
available in Tlamatini; another account's history is never included.

When an operation needs execution approval, review the displayed details and
choose **Proceed** or **Deny**. The decision belongs only to that conversation and
that exact pending request. A later progress message does not hide the approval.
Incomplete or oversized approval details are denied; they cannot be used to
silently authorize a command. Loss of the approval channel or authorization closes
consent and requests cancellation.

Cancellation is a request to the existing running operation. Confirmation that
work has ended is a separate result; cancellation does not undo completed actions.
The adapter keeps ownership until its active work ends, so a second request cannot
take over a still-running conversation.

## Starting Tlamatini from the RC client

Grant **Start Tlamatini** when creating the device invitation. The normal XT tray
must be running in the delegated Windows account's unelevated signed-in session.
A locked desktop or disconnected session does not disable this product function.
XT does not unlock Windows or select another Windows user.

XT discovers the selected edition's installed executable and verifies its identity.
For this edition that executable is `Tlamatini.exe`; the Spanish edition uses
`Tlamatini-Spanish.exe`. The client cannot supply a command, path, process ID or
service name. A running source checkout can provide its account adapter, but the
launch broker does not search for or start source checkouts.

Process start and readiness are different observations. **Starting** means the
application process exists while its account adapter is still loading or unavailable.
Readiness requires the adapter's current heartbeat. The application keeps its normal
main console; RC's internal helpers do not open another console. Temporary launch
storage must be writable application storage outside Windows user profiles.

With the separate **Stop Tlamatini** permission, the client can request normal
shutdown of that installed edition. XT verifies the process identity and signals
its dedicated application console; it does not kill a browser-supplied PID.
An immediate restart verifies a new live process, rather than trusting the
previous process's remaining heartbeat lease.

## Disable access or stop the server

On the account page, choose **Disable remote access**. Local denial is saved first;
the adapter requests cancellation of this account's remote work and revokes its
service binding, devices and outstanding invitations. If Remote-Controller is
unreachable, the page shows pending service revocation. It retries when the service
returns; **Retry service revocation** is also available.

Deleting the local account also records durable revocation intent. It survives
both an unavailable RC service and an application restart, so removing the account
does not lose the obligation to revoke its devices when the service returns.

Re-enabling keeps the account's immutable identity, but old device grants and old
invitations do not become valid again. Enroll and approve the device again.

Use XT's Remote-Controller **Runtime** tab to stop or restart the server. Stopping
RC disconnects its clients and suspends its scheduler; Tlamatini remains open and
Torrenter remains independent. Closing the account tab or exiting XT does not stop
the RC service. A stopped server cannot be restarted by its own disconnected client.

## Implementation and verification

`RemoteControllerProfile`, `RemoteControllerRevocation` and migration
`0224_remote_controller` hold explicit account consent, separate immutable
account/adapter UUIDs and durable account-removal records. The integration
does not reuse Torrenter identities, add a workflow agent, or alter database
backup/restore mechanics.

The English migration depends on `0223_create_superuser_console_handoff`.
Spanish has its own longer migration chain and depends on `0227_create_superuser_console_handoff`.
Keep each edition's real parent; identical behavior does not require identical
migration numbers. [Build repair and verification](changes/2026-11-13-build-migration-preflight.md).

The local account page at `/agent/remote-controller/` is `remote_controller_views.py` with
`templates/agent/remote_controller.html` and `static/agent/css/remote_controller.css`.
It requires the authenticated account, loopback access, same-origin form requests
and CSRF protection. `remote_controller_bridge.py` uses only the fixed installed
native controller and bounded typed IPC. Its account worker owns an adapter lease
and cancels remote work when authorization or transport is lost.

Native transport and account polling have four concurrent slots. Active work has
a 20-second authorization watchdog, so a stalled native call cannot leave consent
valid indefinitely. The service changes a running receipt to `outcome_unknown`
after 20 seconds without its application heartbeat, or 45 seconds without the
launch broker heartbeat. This state is not proof of termination. It prevents
automatic redispatch; the owning adapter may reconcile its actual result later.

`remote_controller_runtime.py` reuses `AgentConsumer`, with the ownership guard in
`remote_controller_guard.py`. Remote chat forwards the six explicitly selected
execution modes. The owned channel retains a literal-text fallback and forwards the same prepared
HTML used by the main chat history. RC sanitizes active markup while preserving
response presentation and the separate execution report.
Only the owned consumer's output is forwarded. Runtime/source packaging must carry
these modules, `services/response_parser.py`, the profile
migration, page/styles and this guide together.

The recorded 13 November runs passed **159/159 isolated unit checks per edition**
before the latest durable-revocation/history refinements. The service's recorded
run passed 195 core checks, 54 HTTP/native-pipe checks and a 14-check isolated SCM
campaign. New checks and behavior added afterward await their own completed run;
these counts do not certify the latest changes. Actual headed main-application
and final installed end-to-end acceptance remain separate gates.
The authoritative service record is
`C:\Development\XAIHT\repo\Tlachihuani\docs\verification\2026-11-13-remote-controller.md`.

The later response-preservation run passed **242/242 source checks per edition**.
The rebuilt frozen pair `20261114-0255` was installed with all runtime hashes
verified and database/configuration bytes preserved. Current installed prompt,
mobile and lifecycle results—including answer-format failures—are tracked in
`C:\Development\XAIHT\repo\Tlachihuani\docs\verification\2026-11-13-installed-rc-acceptance.md`.

The final installed local set completed **50 English + 50 Spanish real requests**,
with **99/100 exact-answer checks**, **170/170 mobile checks**, and independent
remote restart/final stop for both editions. One Spanish answer-format failure
remains recorded. Controller build `20261114-033543-1abcb41e` was installed after
uninstall with 1,475 matching runtime files. English retains the tested `0255`
runtime; Spanish was updated to `spanish-20261114-0457` after a one-shot Spanish
instruction-recognition fix (247/247 Spanish source checks). See the installed
acceptance record above for exact build identities, provenance and deferred LAN work.

## Rich RC responses and downloads · 14 November 2026

RC uses the main chat’s formatted response for live replies and loaded history.
On RC, choose **Save file** to download a response attachment to the device using
the browser. This replaces **Load in canvas** on the mobile workspace as well.
A failed download remains retryable; loading recent conversation refreshes expired
links. The download limit is 64 MiB.

Migration 0225_remote_response_files adds trusted attachment records to saved
messages. Generated programs/snippets and supported successful file-producing
tools supply exact identities and SHA-256 snapshots. A model-written link or file
name is not permission. Legacy attachments without ownership records must be
regenerated. Files that changed after the response are refused. Neither database
backup/restore nor Torrenter lifetime is changed.

Package remote_response_files.py, the migration, response parser, tool-result
hooks and matching Tlachihuani RC assets together. Rebuild/install the main
English/Spanish applications before the matching controller. Source evidence is
in C:/Development/XAIHT/repo/Tlachihuani/docs/verification/2026-11-14-rc-rich-responses.md.
