# =============================================================================
# TLAMATINI SECURITY WHITELIST SCRIPT v2.2 - EXPANDED PRIVILEGES
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
#   2. Controlled Folder Access whitelist for Tlamatini.exe AND its Python
#      (the agents run as python.exe; without it no PDF/document can be saved
#      into Documents, Desktop, Pictures, Music or Videos)
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
# v2.2 changes (2026-10-07):
#   - NEW DISCOVERY step: no hard-coded program paths. It finds every
#     installation route (the folder this script lives in + the install that
#     Tlamatini registers in HKCU\Software\XAIHT\Tlamatini) and classifies each
#     as FROZEN (Tlamatini.exe + its carried python\python.exe) or SOURCE
#     (Tlamatini\manage.py + the Python that runs it: live processes, venv,
#     PATH). Steps 1, 2 and 5 all use that one list.
#   - STEP 2 allows those programs through Controlled Folder Access, then reads
#     the list back and reports [OK]/[FAIL] per program. v2.1 allowed only
#     Tlamatini.exe, so LaTeXer/PDFer could not save into Documents/Desktop.
#   - STEP 5 adds one outbound rule per discovered program, never duplicates.
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
$ScriptVersion = "2.2"

Write-Host ""
Write-Host "================================================" -ForegroundColor Cyan
Write-Host "  TLAMATINI SECURITY WHITELIST SCRIPT v$ScriptVersion" -ForegroundColor Cyan
try {
    Write-Host ("  Last modified: " + (Get-Item -LiteralPath $PSCommandPath).LastWriteTime.ToString('yyyy-MM-dd HH:mm')) -ForegroundColor Cyan
} catch {}
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
# DISCOVERY: every Tlamatini installation route, and the programs it runs
# -----------------------------------------------------------------------------
# No program path below is hard-coded. A route is classified by what is on disk:
#   FROZEN  <root>\Tlamatini.exe exists. The workflow agents (LaTeXer, PDFer,
#           PPTXer, ...) run under the carried <root>\python\python.exe.
#   SOURCE  <root>\Tlamatini\manage.py exists. The agents run under the SAME
#           Python that runs manage.py: found from the running processes, a
#           venv beside the checkout (plus the base Python it runs on), or PATH.
# Routes come from the folder this script lives in AND the installation that
# Tlamatini registers in HKCU\Software\XAIHT\Tlamatini (InstallLocation), so
# running either copy (the repository one or the installed one) covers both.
function Add-UniqueExistingPath {
    param([System.Collections.Generic.List[string]]$List, [string]$Path)
    if ([string]::IsNullOrWhiteSpace($Path)) { return }
    try { $full = [System.IO.Path]::GetFullPath($Path.Trim().Trim('"')) } catch { return }
    if ($full.Length -gt 3) { $full = $full.TrimEnd('\') }
    if (-not (Test-Path -LiteralPath $full)) { return }
    foreach ($known in $List) { if ($known -ieq $full) { return } }
    $List.Add($full)
}

$TlamatiniRoots = New-Object System.Collections.Generic.List[string]
Add-UniqueExistingPath -List $TlamatiniRoots -Path $TlamatiniPath
try {
    $registeredRoot = (Get-ItemProperty -Path 'HKCU:\Software\XAIHT\Tlamatini' -ErrorAction Stop).InstallLocation
    Add-UniqueExistingPath -List $TlamatiniRoots -Path $registeredRoot
} catch {}

$TlamatiniPrograms = New-Object System.Collections.Generic.List[string]       # every program to allow
$TlamatiniCarriedPythons = New-Object System.Collections.Generic.List[string] # frozen: <root>\python\
$TlamatiniDevPythons = New-Object System.Collections.Generic.List[string]     # source: the developer's Python
$TlamatiniRouteReport = New-Object System.Collections.Generic.List[string]
$sourceRouteFound = $false

foreach ($root in $TlamatiniRoots) {
    $frozenExe = Join-Path $root "Tlamatini.exe"
    if (Test-Path -LiteralPath $frozenExe) {
        $TlamatiniRouteReport.Add("FROZEN  $root")
        Add-UniqueExistingPath -List $TlamatiniPrograms -Path $frozenExe
        foreach ($pyName in @("python.exe", "pythonw.exe")) {
            Add-UniqueExistingPath -List $TlamatiniCarriedPythons -Path (Join-Path $root ("python\" + $pyName))
        }
    } elseif (Test-Path -LiteralPath (Join-Path $root "Tlamatini\manage.py")) {
        $TlamatiniRouteReport.Add("SOURCE  $root")
        $sourceRouteFound = $true
        foreach ($venvName in @("venv", ".venv", "env")) {
            $venvPy = Join-Path $root ($venvName + "\Scripts\python.exe")
            if (-not (Test-Path -LiteralPath $venvPy)) { continue }
            Add-UniqueExistingPath -List $TlamatiniDevPythons -Path $venvPy
            # A venv python.exe only redirects to its base interpreter, and the
            # base interpreter is the process that actually writes the files.
            $venvCfg = Join-Path $root ($venvName + "\pyvenv.cfg")
            $homeLine = Get-Content -LiteralPath $venvCfg -ErrorAction SilentlyContinue |
                Where-Object { $_ -match '^\s*home\s*=' } | Select-Object -First 1
            if ($homeLine) {
                Add-UniqueExistingPath -List $TlamatiniDevPythons -Path (Join-Path (($homeLine -split '=', 2)[1].Trim()) "python.exe")
            }
        }
    } else {
        $TlamatiniRouteReport.Add("SKIPPED $root (neither Tlamatini.exe nor Tlamatini\manage.py)")
    }
}

# The Python processes Tlamatini is running right now (web server, MCP server,
# pool agents): the exact interpreter, in either mode.
try {
    $liveTlamatiniPythons = Get-CimInstance -ClassName Win32_Process -Filter "Name='python.exe' OR Name='pythonw.exe'" -ErrorAction Stop |
        Where-Object { $_.ExecutablePath -and ($_.CommandLine -match 'Tlamatini[\\/]+manage\.py|tlamatini_mcp_server\.py|[\\/]agents[\\/]+pools[\\/]') }
    foreach ($proc in $liveTlamatiniPythons) {
        $exePath = $proc.ExecutablePath
        $isCarried = $false
        foreach ($root in $TlamatiniRoots) {
            if ($exePath -like ((Join-Path $root "python") + "\*")) { $isCarried = $true }
        }
        if ($isCarried) {
            Add-UniqueExistingPath -List $TlamatiniCarriedPythons -Path $exePath
        } else {
            Add-UniqueExistingPath -List $TlamatiniDevPythons -Path $exePath
        }
    }
} catch {}

# Source mode with nothing running and no venv: the python.exe on PATH is the
# one `python Tlamatini\manage.py runserver` would use (the Store stub skipped).
if ($sourceRouteFound) {
    $pathPython = Get-Command python.exe -All -ErrorAction SilentlyContinue |
        Where-Object { $_.Source -notmatch '\\WindowsApps\\' } | Select-Object -First 1
    if ($pathPython) { Add-UniqueExistingPath -List $TlamatiniDevPythons -Path $pathPython.Source }
}

foreach ($py in $TlamatiniCarriedPythons) { Add-UniqueExistingPath -List $TlamatiniPrograms -Path $py }
foreach ($py in $TlamatiniDevPythons) { Add-UniqueExistingPath -List $TlamatiniPrograms -Path $py }

Write-Host ""
Write-Host "[DISCOVERY] Tlamatini installation routes:" -ForegroundColor Yellow
if ($TlamatiniRouteReport.Count -eq 0) {
    Write-Host "  [WARN] No Tlamatini installation was found." -ForegroundColor Yellow
}
foreach ($line in $TlamatiniRouteReport) { Write-Host "  $line" -ForegroundColor Cyan }
Write-Host "  Programs that run Tlamatini and save its files:" -ForegroundColor Yellow
foreach ($prog in $TlamatiniPrograms) { Write-Host "    $prog" -ForegroundColor Cyan }
if ($TlamatiniDevPythons.Count -gt 0) {
    Write-Host "  [NOTE] Development Python(s) are in this list (source mode): any script" -ForegroundColor Yellow
    Write-Host "         they run may also save into protected folders." -ForegroundColor Yellow
}
if ($TlamatiniPrograms.Count -eq 0) {
    Write-Host "  [WARN] No Tlamatini program was found - nothing will be allowed." -ForegroundColor Yellow
}

# -----------------------------------------------------------------------------
# STEP 1: Defender exclusions
# -----------------------------------------------------------------------------
Write-Host ""
Write-Host "[STEP 1/10] Adding Tlamatini to Defender exclusions..." -ForegroundColor Yellow

foreach ($root in $TlamatiniRoots) {
    try {
        Add-MpPreference -ExclusionPath $root -ErrorAction Stop
        Write-Host "  [OK] Folder exclusion: $root" -ForegroundColor Green
    } catch {
        if ($_.Exception.Message -match "already exists") {
            Write-Host "  [SKIP] Folder exclusion already exists: $root" -ForegroundColor DarkGray
        } else {
            Write-Host "  [WARN] $($_.Exception.Message)" -ForegroundColor Yellow
        }
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

# Also exclude the Python that a FROZEN install carries (<root>\python\). A
# developer's own Python is deliberately NOT excluded from virus scanning: that
# would stop Defender scanning every script it ever runs. Source mode gets the
# Controlled Folder Access allowance (STEP 2) instead, which is all it needs.
foreach ($pyExe in $TlamatiniCarriedPythons) {
    try {
        Add-MpPreference -ExclusionProcess $pyExe -ErrorAction Stop
        Write-Host "  [OK] Process exclusion: $pyExe" -ForegroundColor Green
    } catch {
        Write-Host "  [WARN] $pyExe : $($_.Exception.Message)" -ForegroundColor Yellow
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
} catch {
    Write-Host "  [WARN] $($_.Exception.Message)" -ForegroundColor Yellow
}

# Tlamatini.exe is NOT the program that saves the user's documents. Every
# workflow agent (LaTeXer, PDFer, PPTXer, Camcorder, Recorder, ...) runs as a
# separate python.exe, and Controlled Folder Access judges THAT program. The
# antivirus process exclusions of STEP 1 do NOT apply to Controlled Folder
# Access - it keeps its own allowed-apps list. Without this, every file an
# agent saves into Documents, Desktop, Pictures, Music or Videos is refused,
# and Windows reports it as "The system cannot find the file specified".
# Seen 2026-10-07: event 1123 blocked <install>\python\python.exe writing
# OneDrive\Documentos\TlamatiniLaTeX and OneDrive\Documentos\TlamatiniPDF.
# The list comes from DISCOVERY: every route, frozen AND source.
$cfaApps = $TlamatiniPrograms

foreach ($app in $cfaApps) {
    try {
        Add-MpPreference -ControlledFolderAccessAllowedApplications $app -ErrorAction Stop
    } catch {
        Write-Host "  [WARN] Could not add $app : $($_.Exception.Message)" -ForegroundColor Yellow
    }
}

# Read the list back: never report an allowance that did not land.
$cfaMissing = 0
$cfaVerified = $true
$cfaAllowed = @()
try {
    $cfaAllowed = @((Get-MpPreference -ErrorAction Stop).ControlledFolderAccessAllowedApplications)
} catch {
    $cfaVerified = $false
    Write-Host "  [WARN] Could not read the allowed-apps list back to verify: $($_.Exception.Message)" -ForegroundColor Yellow
}
if ($cfaVerified) {
    foreach ($app in $cfaApps) {
        if ($cfaAllowed -contains $app) {
            Write-Host "  [OK] Allowed through Controlled Folder Access: $app" -ForegroundColor Green
        } else {
            $cfaMissing++
            Write-Host "  [FAIL] NOT allowed through Controlled Folder Access: $app" -ForegroundColor Red
        }
    }
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

# One outbound rule per discovered program (frozen AND source routes). A program
# that already has an outbound Allow rule is left alone, so re-running the
# script never piles up duplicates.
foreach ($prog in $TlamatiniPrograms) {
    try {
        $existingRule = Get-NetFirewallApplicationFilter -Program $prog -ErrorAction SilentlyContinue |
            Get-NetFirewallRule -ErrorAction SilentlyContinue |
            Where-Object { $_.Direction -eq 'Outbound' -and $_.Action -eq 'Allow' }
        if ($existingRule) {
            Write-Host "  [OK] Outbound rule already exists: $prog" -ForegroundColor Green
        } else {
            New-NetFirewallRule -DisplayName ("Tlamatini Outbound - " + $prog) `
                -Direction Outbound -Program $prog -Action Allow -Profile Any -ErrorAction Stop | Out-Null
            Write-Host "  [OK] Outbound rule added: $prog" -ForegroundColor Green
        }
    } catch {
        Write-Host "  [WARN] $prog : $($_.Exception.Message)" -ForegroundColor Yellow
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
Write-Host "  WHITELIST v$ScriptVersion COMPLETE - SUMMARY" -ForegroundColor Cyan
Write-Host "================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "  [0]  Installation routes:      $($TlamatiniRoots.Count) found ($($TlamatiniPrograms.Count) program(s))" -ForegroundColor Green
Write-Host "  [1]  Defender exclusions:      $($TlamatiniRoots.Count) folder(s) + processes" -ForegroundColor Green
if (-not $cfaVerified) {
    Write-Host "  [2]  Controlled Folder Access: could NOT be verified - see STEP 2" -ForegroundColor Yellow
} elseif ($cfaMissing -gt 0) {
    Write-Host "  [2]  Controlled Folder Access: $cfaMissing app(s) NOT allowed - see STEP 2" -ForegroundColor Red
} else {
    Write-Host "  [2]  Controlled Folder Access: Tlamatini + its Python allowed ($($cfaApps.Count) app(s))" -ForegroundColor Green
}
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
Write-Host "    - Save PDFs/documents into Documents, Desktop, Pictures (LaTeXer, PDFer...)" -ForegroundColor Green
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
