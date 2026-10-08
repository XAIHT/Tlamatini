<!-- Created by Angela López Mendoza · @angelahack1 — Tlamatini. -->
# Windows access scripts and non-admin execution checks — 2026-10-07

The `security/` changes prepare Windows exceptions for the operator to apply.
No elevated policy changes, UAC approvals, live defender sweeps, purchases,
builds or commits were performed during this work.

## Confirmed failure and correction

The real execution probe reproduced a Documents write failure with the
checkout's `python/python.exe`: Windows returned `WinError 2` while creating a
unique scratch directory. Defender Operational event **1123** at
**2026-10-07 16:40:29 America/Mexico_City** explicitly attributes this operation
to **Controlled Folder Access**. The directory exists; this is not a missing
folder or proof of a firewall problem.

Discovery previously included bundled Python only in frozen installations.
Source checkouts can carry that interpreter too. The enablement script now
includes it in the verified CFA/ASR/firewall program list, with a regression
test for a source tree containing `manage.py` and bundled Python but no EXE.
The host restriction remains until the operator applies the prepared script;
post-application verification has not been performed.

## Other changes

- Exact executable discovery includes shared Python, named toolchains and
  shells, with an explicit additional-program option.
- CFA mode stays unchanged; ASR uses per-program exceptions by default.
  Global compatibility mode is explicit and correctly uses AuditMode **2**.
- Firewall allowances have stable owned names, readback from ActiveStore,
  loopback-only incoming defaults and optional Private/Domain LAN access.
  Exact local application blocks can be disabled with a recovery record;
  broad and managed blocks remain visible warnings.
- Before/after records and attention-based exit codes replace optimistic
  completion text. Security-log group access uses its locale-neutral SID;
  the invalid CustomSD string-appending fallback was removed.
- Defender defaults to report-only. Process/IP response requires `-Armed`;
  `-Aggressive` also requires `-Armed`. Process response refuses self paths,
  unreadable paths and changed process names.
- The standalone BAT is generated from the PS1/helper sources. Its `--check`
  path parses without elevation. The harness verifies payload parity and
  exercises CMD quoting from paths with spaces and an apostrophe.
- The visible test harness and real execution checker do not apply policy,
  start paid model jobs, or automatically close their parent console.

## Results and limits

Commands ran in the user's confirmed persistent desktop console, with live
transcripts read during the checks. Shoter captured all screens. Later captures
showed Codex covering the console; further commands were paused for renewed
visibility confirmation. Angela reconfirmed visibility before the final
`job-043` run, which passed with exit 0; its Shoter capture visibly shows the
test console. A final harness rerun (`job-044`, exit 0) routes Shoter's normal
INFO stream to stdout so PowerShell's transcript does not label it as a native
command error. Screenshots alone are not claimed as continuous foreground proof.

| Check | Observed result |
|---|---|
| Windows-policy/defender behavior tests | 23/23 passed, including source bundled-Python discovery |
| Asset harness | Python/PowerShell parsing, payload parity, mocked behavior, BAT syntax and Shoter capture passed |
| Django security asset carriage | 15/15 passed |
| Source agent runtime preparation | 89 runtime copies, 21 model loaders, 3 planner catalogs passed; actual File-Creator bytes verified |
| System Python execution | All 6 checks passed |
| Installed bundled Python execution | All 6 checks passed |
| Checkout bundled Python execution | 5/6 passed; Documents write blocked by CFA, confirmed by event 1123 |
| Administrative application / UAC | Not executed; remains operator action |
| Full installer/release acceptance | Not performed; no frozen build made |

Evidence is local and ignored by Git:
`Temp/codex-latexer-20261007/job-038.ps1.log` (actual execution),
`job-039.ps1.log` (Defender event and carriage), `job-040.ps1.log` (runtime
preparation), `job-043.ps1.log` (asset/carriage checks), `job-044.ps1.log`
(final harness), and
`security/security_logs/asset_tests/` plus `security_logs/execution-*/`.

Runtime preparation does not execute every agent's external integration.
Credentials, network services, hardware and dependencies remain agent-specific.
The separately recorded real-chat LaTeXer PDF result remains valid; see
[LaTeXer verification](2026-10-07-latexer-verification.md).
