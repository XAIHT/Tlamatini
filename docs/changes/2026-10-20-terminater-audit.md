<!--
Tlamatini — "one who knows"
Created by Angela López Mendoza · @angelahack1
Tlamatini Author Banner — do not remove
-->

# Terminater audit — 2026-10-20

This is a source-checkout audit and a set of demonstrated corrections, not a
certificate that Tlamatini has no bugs. The checkout started clean at
`3129e0b8d7bd2aa46b01aeef99854f413d68bb52` on `main` (v1.88.0).
The changes described here are local, uncommitted audit work. No release build,
installation, database-preservation change or Git-history rewrite was performed.

## Scope and conclusion

Repository-wide Python compilation/lint and JavaScript lint/parsing were combined
with manual review of Terminater's engine, ConPTY transport, terminal text model,
Django hub/API/WebSocket, browser dock, wrapped chat caller, Prompt Flow runner,
reapers/watchdog and release carriage. This is not a manual line-by-line review of
every unrelated subsystem, nor a full application/release acceptance campaign.

The tested source implementation can operate real CMD and Windows PowerShell
terminals, observe ordinary user commands, run independent terminals concurrently,
and retain their IDs, processes and screen output across page reloads. Real process
tokens confirmed that both shells inherit elevation from their parent process.
It does **not** meet an unconditional claim of lossless monitoring and exact
attribution of every possible terminal interaction. The remaining gaps below
matter even when the automated suites pass.

Terminater controls the ConPTY sessions created by its hub. Other execution
routes such as Executer and Pythonxer launch their own subprocesses; they do not
become hub terminal sessions automatically. There is no application-wide or
machine-wide monitor that gives Terminater every command from every execution
route or an existing external desktop terminal.

## Demonstrated corrections

Each behavioral change had a failing regression or an observed browser failure
before the correction. New focused coverage is in
`Tlamatini/agent/test_terminater_regressions.py`; the existing Prompt Flow suite
and shared visible browser battery also gained regression checks.

| Defect demonstrated | Correction |
| --- | --- |
| A fast user command could finish before its record was created, leaving monitoring stuck on a command that already ended. | Create the command record before delivering Enter to ConPTY. |
| Shell exit captured only the last 200 screen lines and could include earlier commands. | Use the same command-bounded capture for exit and prompt completion; preserve truncation information. |
| A shell exiting with code 7 was reported as successful. | Return `command_failed` for a known nonzero exit, retaining successful zero exits and aborted outcomes. |
| Live reads ignored offset when `read_chars=0`, omitted truncation/more, and dropped an extra retained line after scrollback overflow. | Share bounded extraction and report pagination/retention accurately, including timeout responses. |
| Simultaneous opens could both pass the maximum-terminal check. | Reserve capacity while a shell is being constructed; release the reservation on construction failure. |
| Duplicate or partially matching titles selected the first terminal silently. | Require a unique match or an exact terminal ID; return `ambiguous_terminal` with matching IDs. |
| An automatic user selection could switch while shell creation was in progress. | Resolve and pin the user once per action/job. |
| Wrapped chat left `user` empty or accepted a model-assigned different user. | Set the runtime config from the authenticated chat context after model assignments. |
| A second AI `send_key` could interleave Enter with an AI command being typed. | Use the terminal's existing typing lock for named-key sequences too. |
| A 201st pending job evicted a still-running job and could break its completion update. | Evict completed jobs only; refuse overload when all 200 slots are pending. |
| Prompt Flow Stop targeted whichever terminal happened to be active. | Remember the operation's selected ID, cancel only that terminal, and prevent typing after cancellation during creation. |
| Shell exit during typing could be overwritten with `prompt`; failed Enter delivery was not marked aborted. | Preserve terminal lifecycle state and check the final write result. |
| `layout(show=False)` updated the hub but left the browser dock visible. | Apply both boolean visibility values in the dock; advance the static cache suffix to `-terminater-2`. |

No public agent setting, typing-speed default, status vocabulary or handover timing
was added. FlowCreator defaults and FlowHypervisor timing remain applicable. The
wrapped-agent purpose now tells the model to use exact IDs for ambiguous names.

## Identity, concurrency and Administrator level

Terminal IDs are scoped to a hub user namespace; `t1` is not a machine-global ID.
Authenticated WebSockets choose their own user's namespace. Chat now pins the
caller before its pool-agent configuration is written, and direct Prompt Flow
terminal operations supply their user's primary key. The trusted loopback API
still accepts an explicit user under its per-run token; callers without a user
retain the existing automatic-selection behavior, pinned for that operation.
This is not a security boundary against another process already holding that
local hub token.

Separate sessions have separate shells and typing locks. The live browser test
ran PowerShell to completion while CMD was still executing a ping. Capacity
reservation and the pending-job refusal address two independently reproduced
concurrency defects. These checks do not establish fairness or stability under
unbounded output or arbitrary simultaneous clients.

The real-shell audit queried Windows `TokenElevation` on the parent and both
ConPTY shell processes; it did not infer elevation from a window title:

| Audit parent | Parent PID | CMD PID / elevated | Windows PowerShell PID / elevated |
| --- | --- | --- | --- |
| Standard user | 18612 / false | 41776 / false | 13808 / false |
| Administrator | 18480 / true | 35040 / true | 40032 / true |

Both runs also checked parallel commands and a PowerShell shell producing 250
numbered lines before `exit 7`; all 250 lines were retained and failure was
reported. The code uses `CreateProcessW`, whose documented default is the calling
process's primary security context ([Microsoft reference](https://learn.microsoft.com/en-us/windows/desktop/api/processthreadsapi/nf-processthreadsapi-createprocessw)).
This verifies the same ConPTY engine used by the application. It does not certify
an already-running non-elevated server as elevated merely because another launcher
was subsequently elevated, or certify a newly built installed release.

## Verification evidence

All workloads ran in visible development consoles; Chrome was explicitly headed
and released only after its desktop image was inspected. The user identified the
active audit console, and the native foreground check passed. Transcripts were
read during execution. The Administrator run used a separate verified elevated
console. Consoles are left open for inspection.

Evidence is retained locally under `Temp/terminater-audit-20261020/` (gitignored):

| Check | Result / evidence |
| --- | --- |
| Original six Terminater suites, before corrections | 688 passed, 221.095 s; `active/03-baseline.job.ps1.log`. Passing old coverage did not expose the newly reproduced defects. |
| Focused before-fix reproductions | `active/04-regressions-before*`, `active/05-confirm-user-race*`, `active/12-caller-regressions-before*`, `active2/03-typing-exit-before*`, `active2/04-enter-before*`. |
| Final Terminater + regression + watchdog/reaper suites | **776 passed**, 256.693 s, exit 0; `active2/09-final-python-tests.job.ps1.log`. Includes the source `check_terminater` integration gate. |
| Python quality over the repository-owned sources | **884 compiled**; default Ruff and unsuppressed E9/F821/F822/F823 checks clean, exit 0; `active2/10-review-and-quality.job.ps1.log`. |
| JavaScript quality | ESLint with zero warnings; **95** source/harness/vendor files parsed, exit 0; `active2/08-javascript-quality.job.ps1.log`. |
| Standard and Administrator real-shell probes | Both exit 0; `real-shell-standard.json`, `real-shell-elevated.json`, `elevated-audit.log`. |
| Browser before visibility fix | 13/14 checks passed; `visible/audit-results-before-ui-fix.json`. The failing check was API hide. |
| Browser after visibility fix | **16/16 passed**, exit 0; `active2/12-browser-final.job.ps1.log`, `visible/audit-results.json`; separate limitation probes in `visible/limitations.json`. |

One intermediate retest stopped because the temporary audit harness omitted the
shared battery constructor's `prefix` argument. That harness error was corrected
before the final run; `visible/audit-results-harness-error.json` retains it. The
16 final checks cover authenticated WebSocket attachment, real user input and
watching, AI command/output, API hide/show with PID preservation, tiling, parallel
execution, reload/replay, JavaScript exceptions and shell cleanup on the chat page.
The shared visibility regression is also part of the existing ACP/PFP battery,
but those full browser batteries were not rerun in this campaign.

The real Windows tests and controlled bookkeeping/race tests serve different
purposes. The new fake transport tests deliberately force otherwise intermittent
ordering; they do not stand in for the real-shell or browser evidence.

## Remaining limits and open findings

These are not waived product requirements. They prevent declaring the five
terminal contracts universally satisfied.

1. **Bounded, in-memory observation.** Per-command output and raw browser replay
   are capped at 400,000 characters, screen scrollback at 20,000 rows, command history
   at 300 entries, and user key/submission history at 4,000/200 entries. `commands`
   returns the last 50. Truncation is now more honest, but no durable, lossless
   command audit exists.
2. **User input delivery.** Ordinary keys during AI typing are refused with an
   Esc-takeover notice. Browser sends while the WebSocket is disconnected are not
   queued for acknowledged delivery. This does not meet a literal “no user key is
   ever lost” claim. Blindly replaying disconnected keys would itself risk sending
   them to a different prompt, so this audit does not introduce such replay.
3. **Command boundaries and completion.** CMD prompt completion does not establish
   an ordinary command's exit code; unknown remains unknown. Prompt markers and
   regexes, browser line snapshots and a limited VT screen model cannot guarantee
   exact reconstruction of nested shells, custom prompts, arbitrary interactive
   programs, multiline input, history/completion edits or terminal-control output.
   A program printing prompt-like markers can also mislead completion tracking.
   The live browser results also contain prompt/echo lines and blank lines inside
   some command `output` fields after dock layout changes. Thus retained text is
   not guaranteed to be clean stdout; the precise redraw cause was not isolated.
4. **Privacy and handover attribution.** The source suppresses secret key/command
   metadata but does not redact echoed shell output from the screen/read path.
   Handover bookkeeping also reuses an assembled command as `typed` when the AI
   continues after the handover, and loses a final user part after Enter clears
   the line tracker. The real browser probe requested `echo <<USER:a sample word>>`
   and typed `audit-user-part`. The shell correctly printed `audit-user-part`, but
   the result recorded `command: "echo echo audit-user-part"` and `user_part: ""`.
   A separate `run` with `secret: true` and the harmless text
   `echo audit-dummy-secret` returned `command: "<hidden>"` alongside
   `output: "audit-dummy-secret"`. These are **confirmed open defects**, recorded
   in `visible/limitations.json`, not passing acceptance assertions. This audit
   does not silently discard output or redefine what a private handover means to
   make them appear solved. Dedicated fixes must preserve the output and user
   editing contracts as well as actor attribution/privacy.
5. **Stress and lifecycle scope.** The audit did not establish bounds for outgoing
   WebSocket queues, global ordering between separate browser clients, shell-open
   versus shutdown races, or blocked pipe writers under arbitrary load. These are
   unverified risks, not claimed reproduced failures. PowerShell 7, other Windows
   versions and a newly compiled/frozen installed application were not accepted
   by this campaign.

The safe conclusion is narrower than “100% control”: the demonstrated failures
above are corrected and covered, ordinary source-mode operation and elevation
inheritance passed the recorded checks, and the remaining observation/privacy
gaps are explicitly open.
