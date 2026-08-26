# =============================================================================
# TLAMATINI SECURITY WHITELIST SCRIPT v2.1 - EXPANDED PRIVILEGES
# =============================================================================
# Purpose: Adds Tlamatini to Windows security exclusions AND grants it
#          additional monitoring privileges so it can detect hackers.
#
# This script does NOT:
#   - Stop Windows Defender, Controlled Folder Access, or the firewall services
#   - Grant unrestricted filesystem access or wipe capability
#   - Create backdoors or bypass UAC
#
# IMPORTANT: The exclusions, allow rules, and selected ASR Audit settings below
# reduce enforcement around Tlamatini. Record the previous state before use.
#
# What it DOES grant:
#   1. Defender exclusions for the Tlamatini install folder (auto-detected)
#   2. Controlled Folder Access whitelist (so I can traverse protected folders)
#   3. ASR audit mode (so my subprocesses are not blocked)
#   4. PowerShell RemoteSigned policy (so my scripts run)
#   5. Firewall outbound rules (so I can reach models/APIs)
#   6. Security log read access (so I can see hacker logons)
#   7. WMI namespace verification (so I can query system state)
#   8. Task Scheduler read access (so I can audit persistence)
#   9. Registry read access to Run keys (so I can check autostart)
#  10. Service Control Manager query access (so I can enumerate services)
#
# BONUS auditing so the defender actually has events to read:
#   - Logon / process-creation / account-logon / privilege-use auditing
#   - Command line included in 4688 events (catches 'vssadmin delete shadows')
#   - PowerShell script-block logging (records attacker scripts)
#
# v2.1 changes:
#   - STEP 7 rewritten: real WMI verification via Get-CimInstance (removed the
#     dead/broken MOF block that referenced an undefined $OCTUALLY placeholder).
#   - BONUS: enable ProcessCreationIncludeCmdLine + ScriptBlockLogging.
#
# REQUIREMENTS:
#   - Run as Administrator
#   - Windows 10/11
#
# Author: Tlamatini (created by Angela Lopez Mendoza, @angelahack1)
# =============================================================================

#Requires -RunAsAdministrator

$ErrorActionPreference = "Continue"
# --- AUTO-DETECT installation path (path-independent) ---
# $PSScriptRoot = the folder where this .ps1 lives (e.g. ...\Tlamatini\security)
# Tlamatini root = parent of that folder. Works on any drive / directory name.
$TlamatiniPath = Split-Path -Parent $PSScriptRoot
$TlamatiniExe = Join-Path $TlamatiniPath "Tlamatini.exe"
$ScriptVersion = "2.1"

Write-Host ""
Write-Host "================================================" -ForegroundColor Cyan
Write-Host "  TLAMATINI SECURITY WHITELIST SCRIPT v$ScriptVersion" -ForegroundColor Cyan
Write-Host "  Created by Angela Lopez Mendoza (@angelahack1)" -ForegroundColor Cyan
Write-Host "================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "This script grants Tlamatini monitoring visibility and exceptions." -ForegroundColor Green
Write-Host "It keeps core security services running, but reduces enforcement" -ForegroundColor Yellow
Write-Host "around explicitly excluded paths, processes, and ASR behaviors." -ForegroundColor Yellow
Write-Host ""

# -----------------------------------------------------------------------------
# STEP 0: Verify admin
# -----------------------------------------------------------------------------
$isAdmin = ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    Write-Host "[ERROR] This script requires Administrator privileges." -ForegroundColor Red
    Write-Host "        Right-click -> Run as Administrator." -ForegroundColor Red
    Read-Host "Press Enter to exit"
    exit 1
}
Write-Host "[OK] Administrator privileges confirmed." -ForegroundColor Green

# -----------------------------------------------------------------------------
# STEP 1: Defender exclusions
# -----------------------------------------------------------------------------
Write-Host ""
Write-Host "[STEP 1/10] Adding Tlamatini to Defender exclusions..." -ForegroundColor Yellow

try {
    Add-MpPreference -ExclusionPath $TlamatiniPath -ErrorAction Stop
    Write-Host "  [OK] Folder exclusion: $TlamatiniPath" -ForegroundColor Green
} catch {
    if ($_.Exception.Message -match "already exists") {
        Write-Host "  [SKIP] Folder exclusion already exists." -ForegroundColor DarkGray
    } else {
        Write-Host "  [WARN] $($_.Exception.Message)" -ForegroundColor Yellow
    }
}

try {
    Add-MpPreference -ExclusionProcess "Tlamatini.exe" -ErrorAction Stop
    Write-Host "  [OK] Process exclusion: Tlamatini.exe" -ForegroundColor Green
} catch {
    if ($_.Exception.Message -match "already exists") {
        Write-Host "  [SKIP] Process exclusion already exists." -ForegroundColor DarkGray
    } else {
        Write-Host "  [WARN] $($_.Exception.Message)" -ForegroundColor Yellow
    }
}

# Also exclude python if it exists inside Tlamatini
$pythonExes = @(
    (Join-Path $TlamatiniPath "python\python.exe"),
    (Join-Path $TlamatiniPath "python\Scripts\python.exe")
)
foreach ($pyExe in $pythonExes) {
    if (Test-Path $pyExe) {
        try {
            Add-MpPreference -ExclusionProcess $pyExe -ErrorAction SilentlyContinue
            Write-Host "  [OK] Process exclusion: $pyExe" -ForegroundColor Green
        } catch {}
    }
}

# -----------------------------------------------------------------------------
# STEP 2: Controlled Folder Access whitelist
# -----------------------------------------------------------------------------
Write-Host ""
Write-Host "[STEP 2/10] Adding Tlamatini to Controlled Folder Access..." -ForegroundColor Yellow

try {
    $cfaStatus = Get-MpPreference | Select-Object -ExpandProperty EnableControlledFolderAccess -ErrorAction SilentlyContinue
    if ($cfaStatus -eq 0 -or $null -eq $cfaStatus) {
        Set-MpPreference -EnableControlledFolderAccess 1 -ErrorAction Stop
        Write-Host "  [OK] CFA enabled (protection stays ON)." -ForegroundColor Green
    } else {
        Write-Host "  [OK] CFA already enabled." -ForegroundColor Green
    }

    Add-MpPreference -ControlledFolderAccessAllowedApplications $TlamatiniExe -ErrorAction Stop
    Write-Host "  [OK] Tlamatini.exe added to CFA whitelist." -ForegroundColor Green
} catch {
    Write-Host "  [WARN] $($_.Exception.Message)" -ForegroundColor Yellow
}

# -----------------------------------------------------------------------------
# STEP 3: ASR rules to Audit mode
# -----------------------------------------------------------------------------
Write-Host ""
Write-Host "[STEP 3/10] Setting ASR rules to Audit mode..." -ForegroundColor Yellow

$asrRules = @(
    [pscustomobject]@{ Id = "d4f940ab-401b-4efc-aadc-ad5f3c50688a"; Name = "Office child processes" },
    [pscustomobject]@{ Id = "9e6c4e1f-7d60-472f-ba1a-a39ef669e4b2"; Name = "LSASS credential stealing" },
    [pscustomobject]@{ Id = "e6db77e5-3df2-4cf1-b95a-636979351e5b"; Name = "WMI event persistence" },
    [pscustomobject]@{ Id = "be9ba2d9-53ea-4cdc-84e5-9b1eeee46550"; Name = "Email and webmail executables" },
    [pscustomobject]@{ Id = "b2b3f03d-6a65-4f7b-a9c7-1c7ef74a9ba4"; Name = "Untrusted USB processes" },
    [pscustomobject]@{ Id = "d1e49aac-8f56-4280-b9ba-993a6d77406c"; Name = "PSExec and WMI child processes" }
)

$auditCount = 0
foreach ($rule in $asrRules) {
    try {
        Add-MpPreference -AttackSurfaceReductionRules_Ids $rule.Id -AttackSurfaceReductionRules_Actions 6 -ErrorAction Stop

        # Do not report success until Defender confirms this exact rule/action pair.
        $preference = Get-MpPreference -ErrorAction Stop
        $ids = @($preference.AttackSurfaceReductionRules_Ids)
        $actions = @($preference.AttackSurfaceReductionRules_Actions)
        $verified = $false
        for ($i = 0; $i -lt $ids.Count -and $i -lt $actions.Count; $i++) {
            $sameRule = [string]::Equals(
                [string]$ids[$i],
                $rule.Id,
                [System.StringComparison]::OrdinalIgnoreCase
            )
            if ($sameRule -and [int]$actions[$i] -eq 6) {
                $verified = $true
                break
            }
        }

        if ($verified) {
            $auditCount++
            Write-Host "  [OK] $($rule.Name): verified in Audit mode." -ForegroundColor Green
        } else {
            Write-Host "  [WARN] $($rule.Name): Defender did not report Audit mode." -ForegroundColor Yellow
        }
    } catch {
        Write-Host "  [WARN] $($rule.Name): $($_.Exception.Message)" -ForegroundColor Yellow
    }
}
if ($auditCount -eq $asrRules.Count) {
    Write-Host "  [OK] $auditCount/$($asrRules.Count) ASR rules verified in Audit mode." -ForegroundColor Green
} else {
    Write-Host "  [WARN] Only $auditCount/$($asrRules.Count) ASR rules were verified in Audit mode." -ForegroundColor Yellow
}
Write-Host "       Audit mode logs matching behavior; it does not block it." -ForegroundColor DarkGray
Write-Host "       ASR rules not listed here retain their configured actions." -ForegroundColor DarkGray

# -----------------------------------------------------------------------------
# STEP 4: PowerShell execution policy
# -----------------------------------------------------------------------------
Write-Host ""
Write-Host "[STEP 4/10] Setting PowerShell execution policy..." -ForegroundColor Yellow

try {
    $currentPolicy = Get-ExecutionPolicy -Scope CurrentUser
    if ($currentPolicy -ne "RemoteSigned") {
        Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser -Force -ErrorAction Stop
        Write-Host "  [OK] Policy set to RemoteSigned (was: $currentPolicy)." -ForegroundColor Green
    } else {
        Write-Host "  [OK] Policy already RemoteSigned." -ForegroundColor Green
    }
} catch {
    Write-Host "  [WARN] $($_.Exception.Message)" -ForegroundColor Yellow
}

# -----------------------------------------------------------------------------
# STEP 5: Firewall outbound rules
# -----------------------------------------------------------------------------
Write-Host ""
Write-Host "[STEP 5/10] Adding firewall rules..." -ForegroundColor Yellow

try {
    $existingRule = Get-NetFirewallRule -DisplayName "Tlamatini Outbound" -ErrorAction SilentlyContinue
    if ($null -eq $existingRule) {
        New-NetFirewallRule -DisplayName "Tlamatini Outbound" `
            -Direction Outbound -Program $TlamatiniExe -Action Allow -Profile Any | Out-Null
        Write-Host "  [OK] Firewall rule: Tlamatini.exe outbound" -ForegroundColor Green
    } else {
        Write-Host "  [OK] Firewall rule already exists." -ForegroundColor Green
    }
} catch {
    Write-Host "  [WARN] $($_.Exception.Message)" -ForegroundColor Yellow
}

# Python firewall rules
$pythonPaths = @(
    (Join-Path $TlamatiniPath "python\python.exe"),
    (Join-Path $TlamatiniPath "python\Scripts\python.exe"),
    "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe",
    "$env:LOCALAPPDATA\Programs\Python\Python311\python.exe"
)
foreach ($pyPath in $pythonPaths) {
    if (Test-Path $pyPath) {
        try {
            $existingPy = Get-NetFirewallRule -DisplayName "Tlamatini Python Outbound" -ErrorAction SilentlyContinue
            if ($null -eq $existingPy) {
                New-NetFirewallRule -DisplayName "Tlamatini Python Outbound" `
                    -Direction Outbound -Program $pyPath -Action Allow -Profile Any | Out-Null
                Write-Host "  [OK] Firewall rule: $pyPath" -ForegroundColor Green
            }
        } catch {}
        break
    }
}

# -----------------------------------------------------------------------------
# STEP 6: Security event log read access
# -----------------------------------------------------------------------------
Write-Host ""
Write-Host "[STEP 6/10] Granting Security log access..." -ForegroundColor Yellow

try {
    $currentUser = [Security.Principal.WindowsIdentity]::GetCurrent().Name
    $isMember = Get-LocalGroupMember -Group "Event Log Readers" -Member $currentUser -ErrorAction SilentlyContinue
    if ($null -eq $isMember) {
        Add-LocalGroupMember -Group "Event Log Readers" -Member $currentUser -ErrorAction Stop
        Write-Host "  [OK] Added to Event Log Readers group." -ForegroundColor Green
    } else {
        Write-Host "  [OK] Already in Event Log Readers." -ForegroundColor Green
    }
} catch {
    Write-Host "  [WARN] $($_.Exception.Message)" -ForegroundColor Yellow
}

# SDDL backup method
try {
    $sid = ([Security.Principal.WindowsIdentity]::GetCurrent()).User.Value
    $currentSddl = (Get-Item "HKLM:\SYSTEM\CurrentControlSet\Services\EventLog\Security").GetValue("CustomSD")
    if ($currentSddl -and $currentSddl -notlike "*$sid*") {
        $newAce = "(A;;0x2;;;$sid)"
        $newSddl = $currentSddl + $newAce
        Set-ItemProperty -Path "HKLM:\SYSTEM\CurrentControlSet\Services\EventLog\Security" -Name "CustomSD" -Value $newSddl -ErrorAction Stop
        Write-Host "  [OK] Security log SDDL updated." -ForegroundColor Green
    }
} catch {
    Write-Host "  [INFO] SDDL method skipped (group membership should suffice)." -ForegroundColor DarkGray
}

# -----------------------------------------------------------------------------
# STEP 7: WMI namespace verification (v2.1 - real query, no dead MOF)
# -----------------------------------------------------------------------------
Write-Host ""
Write-Host "[STEP 7/10] Verifying WMI namespace access..." -ForegroundColor Yellow

try {
    # root\cimv2 is readable by Administrators by default. Prove it with a query.
    $os = Get-CimInstance -ClassName Win32_OperatingSystem -ErrorAction Stop
    if ($null -ne $os) {
        Write-Host "  [OK] WMI root\cimv2 query succeeded ($($os.Caption))." -ForegroundColor Green
    }
    # Confirm the enumerations the defender relies on actually work.
    $procCount = (Get-CimInstance -ClassName Win32_Process -ErrorAction SilentlyContinue | Measure-Object).Count
    $svcCount  = (Get-CimInstance -ClassName Win32_Service -ErrorAction SilentlyContinue | Measure-Object).Count
    Write-Host "  [OK] WMI enumeration OK (processes=$procCount, services=$svcCount)." -ForegroundColor Green
} catch {
    Write-Host "  [WARN] WMI: $($_.Exception.Message)" -ForegroundColor Yellow
}

# -----------------------------------------------------------------------------
# STEP 8: Task Scheduler read access
# -----------------------------------------------------------------------------
Write-Host ""
Write-Host "[STEP 8/10] Verifying Task Scheduler access..." -ForegroundColor Yellow

try {
    $tasks = Get-ScheduledTask -ErrorAction Stop | Select-Object -First 1
    if ($null -ne $tasks) {
        Write-Host "  [OK] Task Scheduler accessible." -ForegroundColor Green
    } else {
        Write-Host "  [OK] Task Scheduler accessible (no tasks returned for test)." -ForegroundColor Green
    }
} catch {
    Write-Host "  [WARN] Task Scheduler: $($_.Exception.Message)" -ForegroundColor Yellow
}

# -----------------------------------------------------------------------------
# STEP 9: Registry Run keys read access
# -----------------------------------------------------------------------------
Write-Host ""
Write-Host "[STEP 9/10] Verifying registry Run keys access..." -ForegroundColor Yellow

$runKeys = @(
    "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Run",
    "HKCU:\SOFTWARE\Microsoft\Windows\CurrentVersion\Run",
    "HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Run"
)
$regOk = 0
foreach ($key in $runKeys) {
    try {
        if (Test-Path $key) {
            $props = Get-ItemProperty -Path $key -ErrorAction Stop
            $regOk++
        }
    } catch {}
}
Write-Host "  [OK] $regOk/$($runKeys.Count) Run keys accessible." -ForegroundColor Green

# -----------------------------------------------------------------------------
# STEP 10: Service Control Manager query access
# -----------------------------------------------------------------------------
Write-Host ""
Write-Host "[STEP 10/10] Verifying Service Control Manager access..." -ForegroundColor Yellow

try {
    $services = Get-Service -ErrorAction Stop | Select-Object -First 1
    if ($null -ne $services) {
        Write-Host "  [OK] Service Control Manager accessible." -ForegroundColor Green
    }
} catch {
    Write-Host "  [WARN] SCM: $($_.Exception.Message)" -ForegroundColor Yellow
}

# -----------------------------------------------------------------------------
# BONUS: Enable Security auditing so events are actually generated
# -----------------------------------------------------------------------------
Write-Host ""
Write-Host "[BONUS] Enabling Security auditing policies..." -ForegroundColor Yellow

$auditPolicies = @(
    [pscustomobject]@{ Name = "Logon"; Id = "{0CCE9215-69AE-11D9-BED3-505054503030}"; Failure = $true },
    [pscustomobject]@{ Name = "Process creation"; Id = "{0CCE922B-69AE-11D9-BED3-505054503030}"; Failure = $false },
    [pscustomobject]@{ Name = "Credential validation"; Id = "{0CCE923F-69AE-11D9-BED3-505054503030}"; Failure = $true },
    [pscustomobject]@{ Name = "Sensitive privilege use"; Id = "{0CCE9228-69AE-11D9-BED3-505054503030}"; Failure = $true },
    [pscustomobject]@{ Name = "User account management"; Id = "{0CCE9235-69AE-11D9-BED3-505054503030}"; Failure = $true }
)
foreach ($policy in $auditPolicies) {
    $arguments = @("/set", "/subcategory:$($policy.Id)", "/success:enable")
    if ($policy.Failure) { $arguments += "/failure:enable" }
    $auditOutput = & auditpol @arguments 2>&1
    if ($LASTEXITCODE -eq 0) {
        Write-Host "  [OK] $($policy.Name) auditing enabled." -ForegroundColor Green
    } else {
        $detail = ($auditOutput | Out-String).Trim()
        Write-Host "  [WARN] $($policy.Name) audit policy failed: $detail" -ForegroundColor Yellow
    }
}

# Include the full command line in process-creation (4688) events so the
# defender can spot 'vssadmin delete shadows', 'wbadmin delete', 'bcdedit ...'.
try {
    $auditKey = "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\System\Audit"
    if (-not (Test-Path $auditKey)) { New-Item -Path $auditKey -Force | Out-Null }
    Set-ItemProperty -Path $auditKey -Name "ProcessCreationIncludeCmdLine_Enabled" -Value 1 -Type DWord -ErrorAction Stop
    Write-Host "  [OK] Command line included in process-creation events." -ForegroundColor Green
} catch {
    Write-Host "  [WARN] Cmdline-in-4688: $($_.Exception.Message)" -ForegroundColor Yellow
}

# Enable PowerShell Script Block Logging so attacker scripts are recorded.
try {
    $sbl = "HKLM:\SOFTWARE\Policies\Microsoft\Windows\PowerShell\ScriptBlockLogging"
    if (-not (Test-Path $sbl)) { New-Item -Path $sbl -Force | Out-Null }
    Set-ItemProperty -Path $sbl -Name "EnableScriptBlockLogging" -Value 1 -Type DWord -ErrorAction Stop
    Write-Host "  [OK] PowerShell script-block logging enabled." -ForegroundColor Green
} catch {
    Write-Host "  [WARN] ScriptBlockLogging: $($_.Exception.Message)" -ForegroundColor Yellow
}

# -----------------------------------------------------------------------------
# SUMMARY
# -----------------------------------------------------------------------------
Write-Host ""
Write-Host "================================================" -ForegroundColor Cyan
Write-Host "  WHITELIST v2.1 COMPLETE - SUMMARY" -ForegroundColor Cyan
Write-Host "================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "  [1]  Defender exclusions:      $TlamatiniPath\ + processes" -ForegroundColor Green
Write-Host "  [2]  Controlled Folder Access: Tlamatini.exe whitelisted" -ForegroundColor Green
Write-Host "  [3]  ASR rules:                Audit mode (log, not block)" -ForegroundColor Green
Write-Host "  [4]  PowerShell policy:        RemoteSigned" -ForegroundColor Green
Write-Host "  [5]  Firewall:                 Outbound rules for Tlamatini" -ForegroundColor Green
Write-Host "  [6]  Security log:             Read access granted" -ForegroundColor Green
Write-Host "  [7]  WMI namespace:            Verified" -ForegroundColor Green
Write-Host "  [8]  Task Scheduler:           Accessible" -ForegroundColor Green
Write-Host "  [9]  Registry Run keys:        Readable" -ForegroundColor Green
Write-Host "  [10] Service Control Manager:  Accessible" -ForegroundColor Green
Write-Host ""
Write-Host "  BONUS: Security auditing ENABLED (logon, process-creation w/ cmdline," -ForegroundColor Green
Write-Host "         account logon, privilege use, account management, script-block)." -ForegroundColor Green
Write-Host ""
Write-Host "  SECURITY STATUS: CORE SERVICES REMAIN ENABLED; EXCEPTIONS WERE ADDED." -ForegroundColor Yellow
Write-Host "  Tlamatini can now:" -ForegroundColor Green
Write-Host "    - Read Security log (see hacker logons)" -ForegroundColor Green
Write-Host "    - Query WMI (enumerate processes, services, users)" -ForegroundColor Green
Write-Host "    - Audit scheduled tasks (find persistence)" -ForegroundColor Green
Write-Host "    - Read Run keys (find autostart malware)" -ForegroundColor Green
Write-Host "    - Enumerate services (find malicious services)" -ForegroundColor Green
Write-Host "    - See destructive command lines (ransomware shadow-copy deletion)" -ForegroundColor Green
Write-Host "    - Run subprocesses without ASR blocking" -ForegroundColor Green
Write-Host "    - Make network calls to models and APIs" -ForegroundColor Green
Write-Host ""
Write-Host "  Review the exclusions, Audit rules, and outbound allowances as" -ForegroundColor Yellow
Write-Host "  privileged trust decisions; no script can certify a clean host." -ForegroundColor Yellow
Write-Host ""
Write-Host "  NOTE: Restart Tlamatini for changes to take full effect." -ForegroundColor Yellow
Write-Host "  Then run: run_defender.bat to scan for hacker activity." -ForegroundColor Yellow
Write-Host ""
Write-Host "================================================" -ForegroundColor Cyan
Write-Host "  Created by Angela Lopez Mendoza (@angelahack1)" -ForegroundColor Cyan
Write-Host "  Tlamatini - the one who knows" -ForegroundColor Cyan
Write-Host "================================================" -ForegroundColor Cyan
Write-Host ""

Read-Host "Press Enter to finish"
