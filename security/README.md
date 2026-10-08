# Tlamatini Windows access and Blue-hat toolkit

Created by **Angela López Mendoza** (`@angelahack1`). Tlamatini — the one who knows.

Double-click **`enable_tlamatini_v2.bat`** when you want to apply Windows access
settings, approve its UAC prompt, read the result, and restart Tlamatini. The
launcher contains its complete PowerShell payload, so it can run without a
companion PS1. Keep it in the installation's `security` directory so discovery
can find that installation. It also discovers the installation registered for
the current user. Administrator approval remains necessary for these settings.

No Microsoft registration or paid certificate is required to use this toolkit.
These scripts do not purchase services or install missing agent dependencies.

## What enablement changes

- Finds source and frozen installations, their bundled/venv/live/PATH Python,
  and existing named toolchains such as Node, Git, LaTeX, FFmpeg, Blender and
  command shells. It prints the exact paths before configuring them.
- Adds Defender exclusions for validated Tlamatini roots, Tlamatini.exe and
  bundled Python. Adds verified Controlled Folder Access and per-program ASR
  exceptions for the discovered runtimes. It leaves CFA's global mode unchanged.
- Creates stable, owned firewall rules for outbound connections and incoming
  loopback connections. It repairs disabled owned rules and disables matching
  **exact local application blocks**. Managed rules and broad IP/port blocks are
  reported and left for review. Effective rules are read back from ActiveStore.
- Sets CurrentUser PowerShell policy to RemoteSigned, grants the elevated user
  Event Log Readers membership, and checks WMI/tasks/Run-key/service access.
  It does not rewrite the Security log's CustomSD descriptor.
- Enables the five documented audit subcategories, process command-line
  auditing and PowerShell Script Block Logging for defensive monitoring.

Shared Python, Node and shell exceptions also apply when those programs run
outside Tlamatini. Root exclusions reduce scanning inside those directories.
Defender and the firewall remain running. These settings cannot override UAC,
managed application control, Tamper Protection, every ASR rule, or another
security product. Missing tools, credentials and unavailable model services
still need their own diagnosis.

The PS1 supports explicit additional options from an elevated visible console:

```powershell
.\tlamatini_whitelist_v2.ps1 -AdditionalProgram 'C:\YourTools\tool.exe'
.\tlamatini_whitelist_v2.ps1 -AllowLan
.\tlamatini_whitelist_v2.ps1 -AuditCompatibility
```

`-AllowLan` adds incoming LocalSubnet rules only on Private/Domain profiles.
`-AuditCompatibility` additionally changes six machine-wide ASR rules to
**AuditMode (2)**: Office child processes, LSASS access, WMI persistence,
email/webmail executables, untrusted USB executables, and PSExec/WMI processes.
Action **6 is Warn**, not Audit. Global ASR changes are not the default.
See [Microsoft's ASR configuration guidance](https://learn.microsoft.com/en-us/defender-endpoint/enable-attack-surface-reduction).

## Results and recovery records

Exit **0** means the configured checks succeeded; **2** means partial results
need attention; **1** means setup failed. Read every `[ATTENTION]` item. A later
failure does not undo earlier changes. Restart Tlamatini afterward; newly added
Event Log Readers membership may require signing out and back in. If UAC uses
a different administrator account, CurrentUser settings apply to that account.

Each run saves `security_logs/enablement-<timestamp>/`: the original Defender
preferences, audit policy, execution policies, a pre-operation change journal
including firewall/registry/member changes, and the final attention list. Keep
this evidence when seeking help. There is **no automatic rollback script**;
these are recovery records for selectively restoring the prior settings, not
a complete system restore point. Protect the logs: command-line and script
auditing can record sensitive values.

## Defender: observation by default

`run_defender.bat` and an ordinary `tlamatini_defender.ps1` invocation perform a
report-only scan. They never automatically kill processes or add IP blocks.
The monitor reads Defender health, logons, networks, processes, tasks, services,
registry persistence, recent files, ransomware indicators and account events.
Findings are investigation leads; names and paths alone do not prove compromise.

```powershell
.\tlamatini_defender.ps1
.\tlamatini_defender.ps1 -Watch -IntervalSeconds 30
.\tlamatini_defender.ps1 -Armed
.\tlamatini_defender.ps1 -Armed -Aggressive
```

`-Armed` explicitly enables persistent IP blocking and process termination.
`-Aggressive` additionally permits stopping dual-use tools and requires `-Armed`.
Armed process response refuses known Tlamatini roots, unreadable paths and
changed process names. This is an availability guard, not provenance validation
or protection for every external child process. IP blocks do not expire; there
is no automatic recovery of stopped processes. `-Watch` stays in the foreground
until Ctrl+C; the interval accepts 5–86400 seconds. No service is installed.

## Visible, non-admin verification

Open a new foreground PowerShell with `-NoExit`, confirm it is visible on the
interactive desktop, then run these from the Tlamatini root. Keep it open:

```powershell
python security\automated_tests_of_security_assets.py
python security\verify_agent_execution.py
```

Both ask for confirmation before testing. `--visible-console-verified` is for
automation **only after a human has confirmed that same console is visible**.
Children inherit the visible console; nothing silently creates or closes a
test window. The asset harness checks syntax, exact embedded-source parity,
mocked Windows-policy behavior, and the real BAT `--check` path from a directory
with spaces and an apostrophe. Shoter captures all screens. JSON and an optional
viewable HTML report are saved under `security_logs/asset_tests/`.

The execution checker tests discovered Python interpreters by creating,
reading and removing its own scratch files in Temp/Desktop/Documents, executing
CMD and PowerShell, and transferring loopback bytes. Use `--python <path>` to
include an additional interpreter. It records failures without attributing
every OS error to the firewall. Neither checker applies security policy, runs
an armed sweep, calls paid models, or certifies all agent integrations.

## Files and packaging

| File | Purpose |
|---|---|
| `enable_tlamatini_v2.bat` | Standalone elevated enablement; `--check` only parses, without UAC or changes. |
| `tlamatini_whitelist_v2.ps1` | Enablement source with explicit optional switches. |
| `windows_access_helpers.ps1` | Verified permission operations and change records. |
| `sync_enable_launcher.py` | Rebuilds the BAT payload after editing the PS1/helper sources; never applies policy. |
| `run_defender.bat`, `tlamatini_defender.ps1` | Report-only launcher and optional armed monitor. |
| `test_security_syntax.ps1`, `test_windows_access.ps1` | Non-admin parser and mocked behavior checks. |
| `automated_tests_of_security_assets.py` | Visible asset harness and Shoter evidence. |
| `verify_agent_execution.py` | Actual non-admin interpreter, shell, file and loopback checks. |

`build.py` carries the whole `security/` directory but excludes `security_logs/`.
Source snapshots and public scrubbers also omit those logs. Self-update replaces
the scripts while retaining operator evidence through
`Temp/_security_logs_carryover_<unique-id>`; a failed stash stops deletion and a
failed restore retains the stash. This toolkit does not change that mechanism.
