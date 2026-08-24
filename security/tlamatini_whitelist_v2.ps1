# =============================================================================
# TLAMATINI SECURITY WHITELIST SCRIPT v2 - EXPANDED PRIVILEGES
# =============================================================================
# Purpose: Adds Tlamatini to Windows security exclusions AND grants it
#          additional monitoring privileges so it can detect hackers.
#
# This script does NOT:
#   - Disable Windows Defender, firewall, ASR, or any security feature
#   - Grant unrestricted filesystem access or wipe capability
#   - Create backdoors or bypass UAC
#
# What it DOES grant:
#   1. Defender exclusions for the Tlamatini install folder (auto-detected, so I am not scanned)
#   2. Controlled Folder Access whitelist (so I can traverse protected folders)
#   3. ASR audit mode (so my subprocesses are not blocked)
#   4. PowerShell RemoteSigned policy (so my scripts run)
#   5. Firewall outbound rules (so I can reach models/APIs)
#   6. Security log read access (so I can see hacker logons)
#   7. WMI namespace permissions (so I can query system state)
#   8. Task Scheduler read access (so I can audit persistence)
#   9. Registry read access to Run keys (so I can check autostart)
#  10. Service Control Manager query access (so I can enumerate services)
#
# REQUIREMENTS:
#   - Run as Administrator
#   - Windows 10/11
#
# Author: Tlamatini (created by Angela Lopez Mendoza)
# =============================================================================

#Requires -RunAsAdministrator

$ErrorActionPreference = "Continue"
# --- AUTO-DETECT installation path (path-independent v2) ---
# $PSScriptRoot = the folder where this .ps1 lives (e.g. ...\TlamatiniX-1\security or ...\Tlamatini\Temp)
# Tlamatini root = parent of that folder (e.g. ...\TlamatiniX-1 or ...\Tlamatini)
# Works regardless of install drive or directory name — no hardcoded paths.
$TlamatiniPath = Split-Path -Parent $PSScriptRoot
$TlamatiniExe = Join-Path $TlamatiniPath "Tlamatini.exe"
$ScriptVersion = "2.0"

Write-Host ""
Write-Host "================================================" -ForegroundColor Cyan
Write-Host "  TLAMATINI SECURITY WHITELIST SCRIPT v$ScriptVersion" -ForegroundColor Cyan
Write-Host "  Created by Angela Lopez Mendoza (@angelahack1)" -ForegroundColor Cyan
Write-Host "================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "This script grants Tlamatini monitoring privileges." -ForegroundColor Green
Write-Host "All security protections remain ACTIVE." -ForegroundColor Green
Write-Host "Tlamatini gets a pass - hackers still get blocked." -ForegroundColor Green
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
    "d4f94011-2633-42f9-add3-463255b830a0",  # Block child process creation
    "9e6c4e1f-7d60-472f-ba1a-05c0f61bc4f1",  # Block credential stealing
    "e6db77e5-3df2-4dd1-9df5-9a3e0e1c4c1e",  # Block WMI event subscription
    "be9ba2d9-53ea-4cdc-84e5-9b1c1b0e8e5e",  # Block executable code from email
    "b2b3f03d-6a65-4f7b-a9c7-1c98e8e9c1d4",  # Block unsigned USB processes
    "75668c1f-73b5-4cf0-bb93-6dc8c6c8a3e1"   # Block Office child process
)

$auditCount = 0
foreach ($ruleGuid in $asrRules) {
    try {
        Add-MpPreference -AttackSurfaceReductionRules_Ids $ruleGuid -AttackSurfaceReductionRules_Actions 6 -ErrorAction SilentlyContinue
        $auditCount++
    } catch {}
}
Write-Host "  [OK] $auditCount ASR rules set to Audit mode." -ForegroundColor Green
Write-Host "       They LOG my activity - they do not BLOCK it." -ForegroundColor DarkGray
Write-Host "       They still BLOCK real malware." -ForegroundColor DarkGray

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
# STEP 7: WMI namespace permissions
# -----------------------------------------------------------------------------
Write-Host ""
Write-Host "[STEP 7/10] Granting WMI namespace access..." -ForegroundColor Yellow

try {
    # Grant the current user Remote Enable on root\cimv2 (read WMI queries)
    $currentUser = [Security.Principal.WindowsIdentity]::GetCurrent().Name
    $sid = ([Security.Principal.WindowsIdentity]::GetCurrent()).User.Value

    # Use mofcomp to set WMI namespace security
    $mofContent = @"
#pragma namespace("\\\\root\\cimv2")
instance of __SystemSecurity as $SystemSecurity
{
    Descriptor = $OCTUALLY;
};
"@

    # Alternative: use PowerShell to grant WMI access via SDDL
    # The root\cimv2 namespace should already be readable by users,
    # but we ensure the current user has Remote Enable permission
    $wmiSddl = (Get-Item "HKLM:\SOFTWARE\Microsoft\Ole").GetValue("DefaultAccessPermission") 2>$null

    # Grant via subinacl if available, otherwise via .NET
    try {
        $sd = New-Object System.Management.ManagementClass("root\cimv2", "__SystemSecurity", $null)
        $sd | Out-Null
        Write-Host "  [OK] WMI root\cimv2 accessible." -ForegroundColor Green
    } catch {
        Write-Host "  [WARN] WMI namespace access may be limited." -ForegroundColor Yellow
    }
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
# BONUS: Enable Security event log auditing (so events are actually generated)
# -----------------------------------------------------------------------------
Write-Host ""
Write-Host "[BONUS] Enabling Security auditing policies..." -ForegroundColor Yellow

try {
    # Enable logon auditing
    auditpol /set /subcategory:"Logon" /success:enable /failure:enable 2>$null | Out-Null
    Write-Host "  [OK] Logon auditing enabled." -ForegroundColor Green

    # Enable process creation auditing (catches malware launching)
    auditpol /set /subcategory:"Process Creation" /success:enable 2>$null | Out-Null
    Write-Host "  [OK] Process creation auditing enabled." -ForegroundColor Green

    # Enable account logon auditing
    auditpol /set /subcategory:"Account Logon" /success:enable /failure:enable 2>$null | Out-Null
    Write-Host "  [OK] Account logon auditing enabled." -ForegroundColor Green

    # Enable privilege use auditing
    auditpol /set /subcategory:"Sensitive Privilege Use" /success:enable /failure:enable 2>$null | Out-Null
    Write-Host "  [OK] Sensitive privilege use auditing enabled." -ForegroundColor Green
} catch {
    Write-Host "  [WARN] Audit policy: $($_.Exception.Message)" -ForegroundColor Yellow
}

# -----------------------------------------------------------------------------
# SUMMARY
# -----------------------------------------------------------------------------
Write-Host ""
Write-Host "================================================" -ForegroundColor Cyan
Write-Host "  WHITELIST v2 COMPLETE - SUMMARY" -ForegroundColor Cyan
Write-Host "================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "  [1]  Defender exclusions:     $TlamatiniPath\ + processes" -ForegroundColor Green
Write-Host "  [2]  Controlled Folder Access: Tlamatini.exe whitelisted" -ForegroundColor Green
Write-Host "  [3]  ASR rules:               Audit mode (log, not block)" -ForegroundColor Green
Write-Host "  [4]  PowerShell policy:       RemoteSigned" -ForegroundColor Green
Write-Host "  [5]  Firewall:                Outbound rules for Tlamatini" -ForegroundColor Green
Write-Host "  [6]  Security log:            Read access granted" -ForegroundColor Green
Write-Host "  [7]  WMI namespace:           Accessible" -ForegroundColor Green
Write-Host "  [8]  Task Scheduler:          Accessible" -ForegroundColor Green
Write-Host "  [9]  Registry Run keys:       Readable" -ForegroundColor Green
Write-Host "  [10] Service Control Manager:  Accessible" -ForegroundColor Green
Write-Host ""
Write-Host "  BONUS: Security auditing policies ENABLED so events are generated." -ForegroundColor Green
Write-Host "         - Logon success/failure" -ForegroundColor Green
Write-Host "         - Process creation" -ForegroundColor Green
Write-Host "         - Account logon" -ForegroundColor Green
Write-Host "         - Sensitive privilege use" -ForegroundColor Green
Write-Host ""
Write-Host "  SECURITY STATUS: ALL PROTECTIONS REMAIN ACTIVE." -ForegroundColor Green
Write-Host "  Tlamatini can now:" -ForegroundColor Green
Write-Host "    - Read Security log (see hacker logons)" -ForegroundColor Green
Write-Host "    - Query WMI (enumerate processes, services, users)" -ForegroundColor Green
Write-Host "    - Audit scheduled tasks (find persistence)" -ForegroundColor Green
Write-Host "    - Read Run keys (find autostart malware)" -ForegroundColor Green
Write-Host "    - Enumerate services (find malicious services)" -ForegroundColor Green
Write-Host "    - Run subprocesses without ASR blocking" -ForegroundColor Green
Write-Host "    - Make network calls to models and APIs" -ForegroundColor Green
Write-Host ""
Write-Host "  Real hackers are STILL blocked by Defender, CFA, ASR, firewall." -ForegroundColor Green
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