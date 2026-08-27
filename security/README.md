# Tlamatini Blue-hat Security Toolkit (`security/`)

This directory contains Tlamatini's **operator-controlled defensive Windows toolkit**.
Use it only on a Windows 10/11 machine you own or are explicitly authorised to
defend. It is not a new chat/canvas Agent, antivirus, EDR, SIEM, forensic product, or
substitute for Microsoft Defender and a real incident-response process.

> Created by **Angela López Mendoza** (`@angelahack1`). Tlamatini - *the one who
> knows*.

## Read this before elevation

`tlamatini_whitelist_v2.ps1` makes persistent host changes. Defender and firewall
services remain running, but the script adds Defender path/process exclusions,
allows Tlamatini through Controlled Folder Access, changes six selected ASR rules
to **Audit** instead of Block, creates broad outbound allow rules, changes the
current user's PowerShell execution policy, grants Security-log visibility, and
enables additional auditing/logging. These exceptions reduce enforcement around
Tlamatini and can become a blind spot if an attacker writes into the excluded tree.

There is currently **no bundled rollback script**. Record the existing Defender,
ASR, CFA, execution-policy, firewall, audit-policy, and Security-log state before
running the whitelist, and protect the Tlamatini directory as a privileged trust
boundary.

## Assets

| File | Purpose |
|---|---|
| `enable_tlamatini_v2.bat` | Self-elevates and runs the one-time whitelist/visibility setup. |
| `tlamatini_whitelist_v2.ps1` | Applies persistent Windows exceptions, audit settings, and Security-log access; verifies WMI/task/registry/service visibility. |
| `run_defender.bat` | Self-elevates and runs one **default armed** defender sweep. |
| `tlamatini_defender.ps1` | Ten-family monitor with detect-only, armed, watch, and aggressive modes. |
| `automated_tests_of_security_assets.py` | Non-destructive visible syntax/classifier/configuration/launcher regression harness. It does not apply the whitelist or run an armed sweep. |
| `README.md` | This operator quick reference. |

## Safest deployment sequence

1. Read and diff every asset in this directory.
2. Run the non-destructive visible test:

   ```powershell
   python security\automated_tests_of_security_assets.py
   ```

   It opens a foreground PowerShell window and headed Chrome/Chromium, captures the
   whole desktop through Shoter, and stores proof under
   `security_logs\asset_tests\`. The generated screenshots can contain sensitive
   desktop information.

3. Record the current Windows security-policy baseline or create a restore point.
4. Run `enable_tlamatini_v2.bat`, approve UAC, review every `[WARN]`, and restart
   Tlamatini/a fresh PowerShell session.
5. Establish false positives with an elevated detect-only scan:

   ```powershell
   cd <Tlamatini-root>\security
   powershell -NoProfile -ExecutionPolicy Bypass -File .\tlamatini_defender.ps1 -DetectOnly
   ```

6. Review `security_logs\alerts.log` and `security_logs\monitor.log`. Findings are
   leads, not proof of compromise.
7. Arm response only after the baseline is understood.

## Enablement details

The whitelist puts these six Microsoft ASR behaviors into action `6` (Audit):

1. Office applications creating child processes.
2. LSASS credential stealing.
3. WMI event-subscription persistence.
4. Executable content from email and webmail.
5. Untrusted or unsigned processes running from USB.
6. Process creation through PSExec and WMI.

The script reads Defender's effective rule/action arrays back after each write and
prints `[OK]` only when the exact GUID is verified in Audit mode. Audit records a
matching behavior; it does not block it. The identifiers are checked by the test
harness and can be compared with the
[Microsoft ASR rules reference](https://learn.microsoft.com/en-us/defender-endpoint/attack-surface-reduction-rules-reference).

Audit-policy setup uses stable Windows subcategory GUIDs instead of English display
names. It enables success/failure Logon, Credential Validation, Sensitive Privilege
Use, and User Account Management, plus success Process Creation, and checks each
`auditpol` exit code. Process command-line and Script Block Logging can preserve
sensitive arguments in Windows event logs.

The batch launchers preserve paths containing spaces during UAC elevation and return
the companion PowerShell process's exit code. A launcher can still partially apply
the whitelist because the PowerShell script continues after individual warnings;
always read the console output.

## Defender modes

```powershell
.\tlamatini_defender.ps1 -DetectOnly
.\tlamatini_defender.ps1 -Watch -DetectOnly
.\tlamatini_defender.ps1 -Watch -IntervalSeconds 30 -DetectOnly
.\tlamatini_defender.ps1                 # one-shot armed response
.\tlamatini_defender.ps1 -Watch          # armed sweeps every 60 seconds
.\tlamatini_defender.ps1 -Aggressive     # also kills dual-use names outside self roots
```

Press `Ctrl+C` to stop watch mode. `-Watch` is a foreground process, not an
installed service or scheduled task. `run_defender.bat` always selects the one-shot
armed mode; use the PowerShell script directly for other switches.
`-IntervalSeconds` accepts values from `5` through `86400`.

## What is monitored

The defender reads ten families of signals:

1. Microsoft Defender health, tamper state, signature age, and recent detections.
2. Security-log success/failure logons and brute-force source-IP counts.
3. Established TCP connections and suspicious listening ports.
4. Process names, paths, known attacker-tool patterns, and dual-use utilities.
5. Non-Microsoft scheduled-task actions and arguments.
6. Running services outside ordinary Windows/Program Files paths.
7. Run/RunOnce, Winlogon, AppInit, and IFEO persistence values.
8. Recently changed executable/script files in Temp, Public, and Startup locations.
9. Ransomware/recovery-tampering command lines, ransom notes, and encrypted-extension bursts.
10. New accounts, administrator-group additions, and current local administrators.

## Response boundaries

- Detect-only mode logs `WOULD BLOCK` and `WOULD KILL`; it never performs those
  actions.
- Armed logon response creates persistent inbound and outbound Windows Firewall
  rules after at least five failed events from one non-local source IP in the
  inspected sample. Rules are named `Tlamatini Block <IP> Inbound|Outbound` and
  do not expire automatically.
- Armed process response force-stops basename patterns classified as known attacker
  tooling. Recognised Tlamatini paths are refused; dual-use names (`nmap`, `nc`,
  `john`, `hashcat`, and others) alert by default and are stopped only with
  `-Aggressive`.
- Suspicious ports, tasks, services, registry entries, recent files, ransomware
  indicators, and account events normally alert only.
- Name/path/port/extension heuristics can produce false positives and false
  negatives. "Self" is a path check, not a signature or provenance guarantee.

Inspect persistent blocks with:

```powershell
Get-NetFirewallRule -DisplayName "Tlamatini Block *"
```

Remove only a validated IP-specific rule pair after incident review; do not delete
all Tlamatini rules blindly.

## Logs and privacy

Both `alerts.log` and `monitor.log` are append-only runtime streams under
`security_logs/`; watch mode can repeat findings. There is no built-in rotation,
retention, deduplication database, automatic unblock, or SIEM forwarding. Logs and
Windows auditing can expose usernames, IPs, administrator membership, process paths,
registry/task arguments, script blocks, and full command lines. Restrict access and
redact before sharing.

`security_logs/` is git-ignored, excluded from public builds, and pruned from
self-modify snapshots. `build.py` ships the remaining `security/` assets beside the
executable; `copy_source_assets.py` carries their source into rebuildable snapshots.
A self-update replaces the `security/` scripts as application code but PRESERVES this
evidence: `apply_update.ps1` stashes `security_logs/` to `Temp/_security_logs_carryover`
before the swap (step 3c) and restores it into the new `security/` afterward (step 5b),
failing open so the evidence is never silently lost.

For the complete threat model, baseline commands, monitor/action matrix, packaging
behavior, and deployment checklist, read **"Enable Tlamatini as a Blue-hat agent"**
in `README.md` and `BookOfTlamatini.md`.
