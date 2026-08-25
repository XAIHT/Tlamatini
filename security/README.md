# Tlamatini Security Arsenal (`security/`)

Angela's hacker-combat toolkit for **this machine** — for a CTF contest, or a real
ransomware / attacker scenario. Everything here is **DEFENSIVE**: it grants Tlamatini
the visibility to *see* an intruder and the response power to *isolate* one, while
leaving every Windows protection (Defender, firewall, ASR, Controlled Folder Access)
fully ON. It disables nothing, wipes nothing, and creates no backdoor.

> Created by **Angela López Mendoza** (@angelahack1). Tlamatini — *the one who knows*.

## Files

| File | What it does |
|---|---|
| `tlamatini_whitelist_v2.ps1` | Grants Tlamatini monitoring visibility (Defender/CFA/ASR-audit/firewall/Security-log/WMI/Task-Scheduler/Run-keys/SCM) **and turns on the auditing the defender needs** (logon, process-creation *with command line*, account management, script-block logging). Protections stay active. |
| `tlamatini_defender.ps1` | **Active Defender.** Scans for intruders and auto-isolates threats. |
| `enable_tlamatini_v2.bat` | Double-click → UAC-elevates → runs the whitelist. |
| `run_defender.bat` | Double-click → UAC-elevates → runs the defender. |
| `automated_tests_of_security_assets.py` | **Persistent visible regression test** for all of the above. |

## Run order (one time, then whenever you want to hunt)

1. **`enable_tlamatini_v2.bat`** (once) — grants visibility + turns on auditing. Restart Tlamatini afterwards.
2. **`run_defender.bat`** — scan now. Or run the defender continuously (see below).
3. Review `security_logs/alerts.log` — every `CRITICAL` / `ALERT` line is a lead.

## Defender modes

```powershell
.\tlamatini_defender.ps1                 # one-shot armed scan
.\tlamatini_defender.ps1 -Watch          # continuous, every 60s (Ctrl+C to stop)
.\tlamatini_defender.ps1 -Watch -IntervalSeconds 30
.\tlamatini_defender.ps1 -DetectOnly     # report only — never block/kill
.\tlamatini_defender.ps1 -Aggressive     # also kill dual-use offensive tools
```

### What the defender watches
Microsoft Defender health/tamper · suspicious & brute-force logons (auto-blocks the IP
inbound **and** outbound) · suspicious/backdoor network ports and listeners · malicious
processes · scheduled-task / service / registry (`Run`, Winlogon, IFEO, AppInit)
persistence · new files in critical directories · **ransomware indicators** (shadow-copy
deletion, `wbadmin`/`bcdedit` recovery tampering, ransom notes, encrypted-extension
bursts) · **account/privilege abuse** (new accounts, additions to admin groups).

### Self-safe (important)
The defender **never kills Tlamatini's own processes or her own dual-use tools**
(Nmapper/Kalier/Discoverer legitimately run `nmap`/`nc`/`john`/`hashcat`). Those are
**ALERTED**, not killed, unless you pass `-Aggressive`. Unambiguous attacker tooling
(`mimikatz`, `rubeus`, `responder`, …) is auto-killed. Processes under the Tlamatini
install/dev tree are recognised as "self" and never touched.

## The persistent test

`automated_tests_of_security_assets.py` proves the arsenal stays correct. It honours the
mandatory **visible-test** rules: a **forked foreground PowerShell window**, **Shoter**
full-desktop screenshots (never PIL), and a **headed Chrome** (Playwright, real Chrome
preferred) showing a pass/fail `SUMMARY.html`.

```
python automated_tests_of_security_assets.py     # exit 0 = all pass, 1 = a failure
```

It checks: both scripts parse with **0 errors**; the self-safe classifier
(`nmap→dualuse`, `mimikatz→malware`, self-path recognised); the new combat modules are
present; the whitelist's WMI/cmdline/script-block fixes are in; and the launchers point
at the right scripts. Artifacts land in `security_logs/asset_tests/` (git-ignored).

## Shipping

- **Self-update**: `build.py` ships this whole `security/` folder next to the executable,
  and `apply_update.ps1` replaces it on update — so every install (and every updated
  install) gets the current, fixed scripts. Runtime `security_logs/` are not shipped.
- **Self-modify**: `copy_source_assets.py` includes `security/*.ps1|*.bat|*.py` in the
  `--self-modify` source snapshot, so Tlamatini carries her own combat toolkit in her
  rebuildable source (logs excluded).

## Authorization

Use only on machines you own or are authorised to defend. The offensive-tool detections
exist to spot an intruder's tooling — not to attack anyone.
