# =============================================================================
# TLAMATINI SECURITY WHITELIST SCRIPT v2.3 - VERIFIED APPLICATION ACCESS
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
#   3. Per-program ASR exceptions; global AuditMode only with -AuditCompatibility
#   4. PowerShell RemoteSigned policy (so my scripts run)
#   5. Verified outbound/loopback rules; LAN access only with -AllowLan
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
[CmdletBinding()]
param(
    [switch]$NoPause,
    [switch]$AuditCompatibility,
    [switch]$AllowLan,
    [string[]]$AdditionalProgram = @()
)

$securityDir = if ($PSScriptRoot) { $PSScriptRoot } else { $env:TLAMATINI_SECURITY_DIR }
if (-not $securityDir) { throw 'Cannot locate the security directory.' }
# The standalone BAT injects the same helpers before this payload.
if (-not (Get-Command Add-VerifiedDefenderEntry -ErrorAction SilentlyContinue)) {
    . (Join-Path $securityDir 'windows_access_helpers.ps1')
}
$script:EnablementFailures = New-Object 'System.Collections.Generic.List[string]'

$ErrorActionPreference = "Continue"
# --- AUTO-DETECT installation path (path-independent) ---
# $PSScriptRoot = the folder where this .ps1 lives (e.g. ...\Tlamatini\security)
# Tlamatini root = parent of that folder. Works on any drive / directory name.
$TlamatiniPath = Split-Path -Parent $securityDir
$TlamatiniExe = Join-Path $TlamatiniPath "Tlamatini.exe"
$ScriptVersion = "2.3"

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
    if (-not $NoPause) { Read-Host "Press Enter to exit" | Out-Null }
    exit 1
}
Write-Host "[OK] Administrator privileges confirmed." -ForegroundColor Green
# Stop before changing policy if the recovery baseline cannot be saved.
$runDir = Join-Path $securityDir ('security_logs\enablement-' + (Get-Date -Format 'yyyyMMdd-HHmmss-fff'))
try {
    New-Item -ItemType Directory -Path $runDir -Force -ErrorAction Stop | Out-Null
    Get-MpPreference -ErrorAction Stop | Export-Clixml -LiteralPath (Join-Path $runDir 'defender-before.xml') -ErrorAction Stop
    $auditBackup = Join-Path $runDir 'audit-before.csv'
    $backupOutput = & "$env:SystemRoot\System32\auditpol.exe" /backup "/file:$auditBackup" 2>&1
    if ($LASTEXITCODE -ne 0) { throw "Could not save audit policy: $backupOutput" }
    $script:ChangesPath = Join-Path $runDir 'changes.jsonl'
    [IO.File]::WriteAllText($script:ChangesPath, '')
    Write-Host "Recovery baseline and change journal: $runDir" -ForegroundColor Cyan
} catch {
    Write-Host "[ERROR] Could not save the pre-change baseline: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}

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

# Never exclude an arbitrary directory or drive merely because it exists.
for ($i = $TlamatiniRoots.Count - 1; $i -ge 0; $i--) {
    $candidate = $TlamatiniRoots[$i]
    if (-not (Test-Path -LiteralPath (Join-Path $candidate 'Tlamatini.exe') -PathType Leaf) -and
        -not (Test-Path -LiteralPath (Join-Path $candidate 'Tlamatini\manage.py') -PathType Leaf)) {
        $TlamatiniRoots.RemoveAt($i)
    }
}
if (-not $TlamatiniRoots.Count) { Write-Host '[ERROR] No valid installation found; no settings changed.' -ForegroundColor Red; exit 1 }

foreach ($root in $TlamatiniRoots) {
    # A source checkout can carry the same embedded Python as a frozen install.
    # It is not a venv and may have different CFA permissions from PATH Python.
    foreach ($pyName in @('python.exe', 'pythonw.exe')) {
        Add-UniqueExistingPath -List $TlamatiniCarriedPythons -Path (Join-Path $root ("python\" + $pyName))
    }
    $frozenExe = Join-Path $root "Tlamatini.exe"
    if (Test-Path -LiteralPath $frozenExe) {
        $TlamatiniRouteReport.Add("FROZEN  $root")
        Add-UniqueExistingPath -List $TlamatiniPrograms -Path $frozenExe
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

# Agents launch these runtimes too; an allowance for Tlamatini.exe is not inherited.
# Named, existing executable paths only. No recursive trust of arbitrary programs.
foreach ($name in @('node.exe','git.exe','ffmpeg.exe','ffprobe.exe','pdflatex.exe',
    'xelatex.exe','lualatex.exe','latexmk.exe','biber.exe','bibtex.exe','makeindex.exe',
    'perl.exe','blender.exe','ollama.exe','powershell.exe','pwsh.exe','cmd.exe')) {
    foreach ($command in @(Get-Command $name -CommandType Application -ErrorAction SilentlyContinue)) {
        if ($command.Source -notmatch '\\WindowsApps\\') {
            Add-UniqueExistingPath -List $TlamatiniPrograms -Path $command.Source
        }
    }
}
foreach ($root in $TlamatiniRoots) {
    foreach ($relative in @('node\node.exe','nodejs\node.exe','Git\cmd\git.exe')) {
        Add-UniqueExistingPath -List $TlamatiniPrograms -Path (Join-Path $root $relative)
    }
}
foreach ($program in $AdditionalProgram) {
    if (-not (Test-Path -LiteralPath $program -PathType Leaf) -or [IO.Path]::GetExtension($program) -ine '.exe') {
        throw "AdditionalProgram must be an existing .exe: $program"
    }
    Add-UniqueExistingPath -List $TlamatiniPrograms -Path $program
}


Write-Host ""
Write-Host "[DISCOVERY] Tlamatini installation routes:" -ForegroundColor Yellow
if ($TlamatiniRouteReport.Count -eq 0) {
    Write-EnablementWarning "No Tlamatini installation was found."
}
foreach ($line in $TlamatiniRouteReport) { Write-Host "  $line" -ForegroundColor Cyan }
Write-Host "  Programs that run Tlamatini and save its files:" -ForegroundColor Yellow
foreach ($prog in $TlamatiniPrograms) { Write-Host "    $prog" -ForegroundColor Cyan }
if ($TlamatiniDevPythons.Count -gt 0) {
    Write-Host "  [NOTE] Development Python(s) are in this list (source mode): any script" -ForegroundColor Yellow
    Write-Host "         they run may also save into protected folders." -ForegroundColor Yellow
}
if ($TlamatiniPrograms.Count -eq 0) {
    Write-EnablementWarning "No Tlamatini program was found - nothing will be allowed."
}

# -----------------------------------------------------------------------------
# STEP 1: Defender exclusions
# -----------------------------------------------------------------------------
Write-Host ""
Write-Host "[STEP 1/10] Adding Tlamatini to Defender exclusions..." -ForegroundColor Yellow

foreach ($root in $TlamatiniRoots) {
    try { Add-VerifiedDefenderEntry 'ExclusionPath' $root }
    catch { Write-EnablementWarning $_.Exception.Message }
}
foreach ($prog in @($TlamatiniPrograms | Where-Object { [IO.Path]::GetFileName($_) -ieq 'Tlamatini.exe' }) + @($TlamatiniCarriedPythons)) {
    try { Add-VerifiedDefenderEntry 'ExclusionProcess' $prog }
    catch { Write-EnablementWarning $_.Exception.Message }
}

# STEP 2: Allow actual writers through CFA, without changing CFA's global mode.
Write-Host '[STEP 2/10] Verifying protected-folder access for agents and their runtimes...' -ForegroundColor Yellow
Write-Host 'Shared shells/interpreters also run commands outside Tlamatini. Their exact paths are listed above.' -ForegroundColor Yellow
foreach ($app in $TlamatiniPrograms) {
    try { Add-VerifiedDefenderEntry 'ControlledFolderAccessAllowedApplications' $app }
    catch { Write-EnablementWarning $_.Exception.Message }
}

# -----------------------------------------------------------------------------
# STEP 3: Per-program ASR exceptions; optional machine-wide Audit mode
# -----------------------------------------------------------------------------
Write-Host ""
Write-Host "[STEP 3/10] Verifying application-specific ASR exceptions..." -ForegroundColor Yellow

# Per-program exceptions first. Global policy changes require an explicit switch.
foreach ($app in $TlamatiniPrograms) {
    try { Add-VerifiedDefenderEntry 'AttackSurfaceReductionOnlyExclusions' $app }
    catch { Write-EnablementWarning $_.Exception.Message }
}
if ($AuditCompatibility) {
    Write-Host 'Explicit compatibility mode: six machine-wide ASR rules will use AuditMode (2), not Warn (6).' -ForegroundColor Yellow
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
        Add-MpPreference -AttackSurfaceReductionRules_Ids $rule.Id -AttackSurfaceReductionRules_Actions AuditMode -ErrorAction Stop

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
            if ($sameRule -and [int]$actions[$i] -eq 2) {
                $verified = $true
                break
            }
        }

        if ($verified) {
            $auditCount++
            Write-Host "  [OK] $($rule.Name): verified in Audit mode." -ForegroundColor Green
        } else {
            Write-EnablementWarning "$($rule.Name): Defender did not report Audit mode."
        }
    } catch {
        Write-EnablementWarning "$($rule.Name): $($_.Exception.Message)"
    }
}
if ($auditCount -eq $asrRules.Count) {
    Write-Host "  [OK] $auditCount/$($asrRules.Count) ASR rules verified in Audit mode." -ForegroundColor Green
} else {
    Write-EnablementWarning "Only $auditCount/$($asrRules.Count) ASR rules were verified in Audit mode."
}
Write-Host "       Audit mode logs matching behavior; it does not block it." -ForegroundColor DarkGray
Write-Host "       ASR rules not listed here retain their configured actions." -ForegroundColor DarkGray

}

# -----------------------------------------------------------------------------
# STEP 4: PowerShell execution policy
# -----------------------------------------------------------------------------
Write-Host ""
Write-Host "[STEP 4/10] Setting PowerShell execution policy..." -ForegroundColor Yellow

try {
    Import-Module (Join-Path $PSHOME 'Modules\Microsoft.PowerShell.Security\Microsoft.PowerShell.Security.psd1') -ErrorAction Stop
    Get-ExecutionPolicy -List | Export-Clixml -LiteralPath (Join-Path $runDir 'powershell-before.xml') -ErrorAction Stop
    $currentPolicy = Get-ExecutionPolicy -Scope CurrentUser
    if ($currentPolicy -ne "RemoteSigned") {
        Save-EnablementChange 'ExecutionPolicy' 'CurrentUser' $currentPolicy
        Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser -Force -ErrorAction Stop
        Write-Host "  [OK] Policy set to RemoteSigned (was: $currentPolicy)." -ForegroundColor Green
    } else {
        Write-Host "  [OK] Policy already RemoteSigned." -ForegroundColor Green
    }
    if ((Get-ExecutionPolicy -Scope CurrentUser) -ne 'RemoteSigned') { throw 'CurrentUser execution policy was not retained.' }
    if ((Get-ExecutionPolicy) -in @('Restricted','AllSigned')) { throw 'A higher-priority PowerShell policy still restricts scripts; inspect MachinePolicy/UserPolicy.' }
} catch {
    Write-EnablementWarning "$($_.Exception.Message)"
}

# -----------------------------------------------------------------------------
# STEP 5: Firewall outbound rules
# -----------------------------------------------------------------------------
Write-Host ""
Write-Host "[STEP 5/10] Adding firewall rules..." -ForegroundColor Yellow

foreach ($prog in $TlamatiniPrograms) {
    foreach ($kind in @('Outbound','Loopback')) {
        try { Set-VerifiedFirewallAllowance $prog $kind }
        catch { Write-EnablementWarning $_.Exception.Message }
    }
    if ($AllowLan) {
        try { Set-VerifiedFirewallAllowance $prog 'LAN' }
        catch { Write-EnablementWarning $_.Exception.Message }
    }
}
try {
    $blocks = @(Get-NetFirewallRule -PolicyStore ActiveStore -Enabled True -Action Block -ErrorAction Stop)
    Repair-ExactApplicationBlocks $blocks $TlamatiniPrograms.ToArray()
    foreach ($profile in Get-NetFirewallProfile -PolicyStore ActiveStore -ErrorAction Stop) {
        if ($profile.AllowLocalFirewallRules -eq 'False') {
            Write-EnablementWarning "Profile $($profile.Name) ignores local firewall rules. Managed policy must allow them."
        }
    }
} catch { Write-EnablementWarning $_.Exception.Message }

# -----------------------------------------------------------------------------
# STEP 6: Security event log read access
# -----------------------------------------------------------------------------
Write-Host ""
Write-Host "[STEP 6/10] Granting Security log access..." -ForegroundColor Yellow

try {
    $currentUser = [Security.Principal.WindowsIdentity]::GetCurrent().Name
    $isMember = Get-LocalGroupMember -SID ([Security.Principal.SecurityIdentifier]::new('S-1-5-32-573')) -Member $currentUser -ErrorAction SilentlyContinue
    if ($null -eq $isMember) {
        Save-EnablementChange 'EventLogReadersMembership' $currentUser $false
        Add-LocalGroupMember -SID ([Security.Principal.SecurityIdentifier]::new('S-1-5-32-573')) -Member $currentUser -ErrorAction Stop
        if (-not (Get-LocalGroupMember -SID ([Security.Principal.SecurityIdentifier]::new('S-1-5-32-573')) -Member $currentUser -ErrorAction Stop)) {
            throw 'Event Log Readers membership was not retained.'
        }
        Write-Host "  [OK] Added to Event Log Readers group." -ForegroundColor Green
    } else {
        Write-Host "  [OK] Already in Event Log Readers." -ForegroundColor Green
    }
} catch {
    Write-EnablementWarning "$($_.Exception.Message)"
}

# Group membership is the supported access route. Appending an ACE to CustomSD
# can corrupt the descriptor or grant write access, so never rewrite it here.
Write-Host '  Sign out/in if Event Log Readers membership was newly added.' -ForegroundColor DarkGray

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
    $procCount = (Get-CimInstance -ClassName Win32_Process -ErrorAction Stop | Measure-Object).Count
    $svcCount  = (Get-CimInstance -ClassName Win32_Service -ErrorAction Stop | Measure-Object).Count
    Write-Host "  [OK] WMI enumeration OK (processes=$procCount, services=$svcCount)." -ForegroundColor Green
} catch {
    Write-EnablementWarning "WMI: $($_.Exception.Message)"
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
    Write-EnablementWarning "Task Scheduler: $($_.Exception.Message)"
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
    } catch { Write-EnablementWarning "Cannot read Run key $key : $($_.Exception.Message)" }
}
Write-Host "  Read $regOk of $($runKeys.Count) candidate Run keys (absent keys are normal)." -ForegroundColor Cyan

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
    Write-EnablementWarning "SCM: $($_.Exception.Message)"
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
    $auditOutput = & "$env:SystemRoot\System32\auditpol.exe" @arguments 2>&1
    if ($LASTEXITCODE -eq 0) {
        Write-Host "  [OK] $($policy.Name) auditing enabled." -ForegroundColor Green
    } else {
        $detail = ($auditOutput | Out-String).Trim()
        Write-EnablementWarning "$($policy.Name) audit policy failed: $detail"
    }
}

# Include the full command line in process-creation (4688) events so the
# defender can spot 'vssadmin delete shadows', 'wbadmin delete', 'bcdedit ...'.
try {
    $auditKey = "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\System\Audit"
    Set-VerifiedLoggingValue $auditKey 'ProcessCreationIncludeCmdLine_Enabled'
    Write-Host "  [OK] Command line included in process-creation events." -ForegroundColor Green
} catch {
    Write-EnablementWarning "Cmdline-in-4688: $($_.Exception.Message)"
}

# Enable PowerShell Script Block Logging so attacker scripts are recorded.
try {
    $sbl = "HKLM:\SOFTWARE\Policies\Microsoft\Windows\PowerShell\ScriptBlockLogging"
    Set-VerifiedLoggingValue $sbl 'EnableScriptBlockLogging'
    Write-Host "  [OK] PowerShell script-block logging enabled." -ForegroundColor Green
} catch {
    Write-EnablementWarning "ScriptBlockLogging: $($_.Exception.Message)"
}

# Summary derives from observed failures, never from optimistic fixed text.
Write-Host ''
Write-Host '================================================' -ForegroundColor Cyan
if ($script:EnablementFailures.Count) {
    Write-Host "ENABLEMENT NEEDS ATTENTION: $($script:EnablementFailures.Count) item(s)." -ForegroundColor Yellow
    foreach ($failure in $script:EnablementFailures) { Write-Host "  - $failure" -ForegroundColor Yellow }
} else {
    Write-Host 'ENABLEMENT SETTINGS VERIFIED.' -ForegroundColor Green
}
Write-Host "Recovery evidence: $runDir"
Write-Host 'Restart Tlamatini, then run the non-admin execution check described in security/README.md.'
Write-Host 'Windows access does not install missing tools, bypass UAC/domain policy, or repair an unavailable model service.'
Write-Host 'run_defender.bat now reports findings without automatically killing tools or blocking IPs.'
ConvertTo-Json -InputObject @($script:EnablementFailures.ToArray()) | Set-Content -LiteralPath (Join-Path $runDir 'attention.json') -Encoding UTF8
if (-not $NoPause) { Read-Host 'Press Enter to finish' | Out-Null }
if ($script:EnablementFailures.Count) { exit 2 }
exit 0
