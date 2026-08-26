# =============================================================================
# TLAMATINI ACTIVE DEFENDER - SECURITY MONITORING & AUTO-RESPONSE  (v2.1)
# =============================================================================
# Purpose: Real-time intrusion detection and automated defensive response.
#          This is NOT malware. This is a DEFENDER that:
#          - Monitors Defender health, logons, network, processes, tasks,
#            services, registry persistence, ransomware indicators and
#            account/privilege abuse
#          - Detects hacker activity in real-time
#          - Auto-isolates threats (blocks IPs inbound+outbound, kills malware)
#          - Alerts the user via log + desktop notification
#
# This script does NOT:
#   - Disable any security feature
#   - Wipe or destroy data
#   - Bypass Windows protections
#   - Grant god-mode or unrestricted access
#
# SELF-SAFE: it NEVER auto-kills Tlamatini's own processes or her own
#            dual-use security tools (Nmapper/Kalier/Discoverer run
#            nmap/nc/john/hashcat legitimately). Those are ALERTED, not killed,
#            unless you pass -Aggressive.
#
# USAGE:
#   .\tlamatini_defender.ps1                 # one-shot armed scan
#   .\tlamatini_defender.ps1 -Watch          # continuous scan every 60s
#   .\tlamatini_defender.ps1 -Watch -IntervalSeconds 30
#   .\tlamatini_defender.ps1 -DetectOnly     # report only, never block/kill
#   .\tlamatini_defender.ps1 -Aggressive     # also kill dual-use offensive tools
#
# REQUIREMENTS:
#   - Run as Administrator
#   - Windows 10/11
#   - Run tlamatini_whitelist_v2.ps1 first (grants log/WMI/audit visibility)
#
# Author: Tlamatini (created by Angela Lopez Mendoza, @angelahack1)
# =============================================================================

#Requires -RunAsAdministrator

[CmdletBinding()]
param(
    [switch]$Watch,
    [ValidateRange(5, 86400)]
    [int]$IntervalSeconds = 60,
    [switch]$DetectOnly,
    [switch]$Aggressive
)

$ErrorActionPreference = "Continue"
$ScriptVersion = "2.1"
$script:Respond = -not $DetectOnly

# --- AUTO-DETECT: logs go next to this .ps1 (in <script-dir>\security_logs) ---
$LogDir = Join-Path $PSScriptRoot "security_logs"
$AlertLog = Join-Path $LogDir "alerts.log"
$MonitorLog = Join-Path $LogDir "monitor.log"
if (-not (Test-Path $LogDir)) {
    New-Item -ItemType Directory -Path $LogDir -Force | Out-Null
}

# --- Tlamatini's OWN footprint - never auto-kill her own tools/processes ---
# Parent of this \security folder = the install/dev root (works from either).
$script:SelfRoots = @(
    (Split-Path -Parent $PSScriptRoot),
    (Join-Path $env:LOCALAPPDATA "Tlamatini")
) | Where-Object { $_ -and (Test-Path $_) }

function Test-IsSelf {
    param([string]$Path)
    if ([string]::IsNullOrWhiteSpace($Path)) { return $false }
    foreach ($root in $script:SelfRoots) {
        if ($Path -like "$root\*") { return $true }
    }
    return $false
}

function Write-Alert {
    param([string]$Message, [string]$Severity = "INFO")
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $line = "[$timestamp] [$Severity] $Message"
    Add-Content -Path $AlertLog -Value $line
    Add-Content -Path $MonitorLog -Value $line
    switch ($Severity) {
        "CRITICAL" { Write-Host $line -ForegroundColor Red }
        "WARNING"  { Write-Host $line -ForegroundColor Yellow }
        "ALERT"    { Write-Host $line -ForegroundColor Magenta }
        default    { Write-Host $line -ForegroundColor Cyan }
    }
}

function Send-DesktopNotification {
    param([string]$Title, [string]$Message)
    try {
        Add-Type -AssemblyName System.Windows.Forms
        Add-Type -AssemblyName System.Drawing
        $notify = New-Object System.Windows.Forms.NotifyIcon
        $notify.Icon = [System.Drawing.SystemIcons]::Warning
        $notify.Visible = $true
        $notify.ShowBalloonTip(10000, $Title, $Message, [System.Windows.Forms.ToolTipIcon]::Warning)
        Start-Sleep -Seconds 2
        $notify.Dispose()
    } catch {
        Write-Alert "Desktop notification failed: $($_.Exception.Message)" "WARNING"
    }
}

function Block-SuspiciousIP {
    param([string]$IPAddress, [string]$Reason)
    if (-not $script:Respond) {
        Write-Alert "WOULD BLOCK IP $IPAddress (detect-only) - $Reason" "ALERT"
        return
    }
    try {
        # Block BOTH directions - inbound access and outbound C2 beaconing.
        foreach ($dir in @("Inbound", "Outbound")) {
            $ruleName = "Tlamatini Block $IPAddress $dir"
            $existing = Get-NetFirewallRule -DisplayName $ruleName -ErrorAction SilentlyContinue
            if ($null -eq $existing) {
                New-NetFirewallRule -DisplayName $ruleName `
                    -Direction $dir -Action Block -RemoteAddress $IPAddress -Profile Any | Out-Null
            }
        }
        Write-Alert "BLOCKED IP $IPAddress (in+out) - $Reason" "CRITICAL"
        Send-DesktopNotification "TLAMATINI: Threat Blocked" "Blocked IP $IPAddress - $Reason"
    } catch {
        Write-Alert "Failed to block IP $IPAddress : $($_.Exception.Message)" "WARNING"
    }
}

function Stop-SuspiciousProcess {
    param([int]$ProcessId, [string]$ProcessName, [string]$Reason)
    if (-not $script:Respond) {
        Write-Alert "WOULD KILL $ProcessName (PID $ProcessId) (detect-only) - $Reason" "ALERT"
        return
    }
    try {
        $proc = Get-Process -Id $ProcessId -ErrorAction SilentlyContinue
        if ($null -ne $proc) {
            if (Test-IsSelf $proc.Path) {
                Write-Alert "REFUSED to kill Tlamatini's own process $ProcessName (PID $ProcessId)" "INFO"
                return
            }
            Stop-Process -Id $ProcessId -Force -ErrorAction Stop
            Write-Alert "KILLED process $ProcessName (PID $ProcessId) - $Reason" "CRITICAL"
            Send-DesktopNotification "TLAMATINI: Process Killed" "Killed $ProcessName (PID $ProcessId) - $Reason"
        }
    } catch {
        Write-Alert "Failed to kill process $ProcessName (PID $ProcessId) : $($_.Exception.Message)" "WARNING"
    }
}

# --- Threat classification ---------------------------------------------------
# Unambiguous ATTACKER tooling -> auto-kill (finding one locally is a red flag).
$script:MalwarePatterns = @(
    "*mimikatz*", "*pypykatz*", "*safetykatz*", "*cobaltstrike*", "*rubeus*",
    "*responder*", "*seatbelt*", "*lazagne*", "*sharphound*", "*bloodhound*",
    "*powersploit*", "*kerberoast*", "*winpeas*", "*mimikittenz*", "*koadic*"
)
# DUAL-USE tools Tlamatini herself runs -> ALERT only (kill only if -Aggressive).
$script:DualUseNames = @(
    "nc", "ncat", "nmap", "hydra", "john", "hashcat", "psexec", "psexec64",
    "netcat", "socat", "chisel"
)

function Get-ThreatTier {
    param($Proc)
    $name = $Proc.ProcessName.ToLower()
    foreach ($p in $script:MalwarePatterns) { if ($name -like $p) { return "malware" } }
    foreach ($n in $script:DualUseNames)   { if ($name -eq $n)   { return "dualuse" } }
    return $null
}

# =============================================================================
# MONITOR 0: Microsoft Defender health / tamper detection
# =============================================================================
function Monitor-DefenderHealth {
    Write-Alert "Checking Microsoft Defender health..." "INFO"
    try {
        $mp = Get-MpComputerStatus -ErrorAction Stop
        if (-not $mp.RealTimeProtectionEnabled) {
            Write-Alert "DEFENDER TAMPER: Real-time protection is OFF" "CRITICAL"
            Send-DesktopNotification "TLAMATINI: Defender OFF" "Real-time protection disabled - possible attacker tampering"
        } else {
            Write-Alert "Defender real-time protection: ON" "INFO"
        }
        if (-not $mp.AntivirusEnabled) { Write-Alert "DEFENDER TAMPER: Antivirus engine is OFF" "CRITICAL" }
        if (($mp.PSObject.Properties.Name -contains "IsTamperProtected") -and (-not $mp.IsTamperProtected)) {
            Write-Alert "Defender Tamper Protection is OFF" "WARNING"
        }
        if ($mp.AntivirusSignatureAge -gt 3) {
            Write-Alert "Defender signatures are $($mp.AntivirusSignatureAge) days old" "WARNING"
        }
        $threats = Get-MpThreatDetection -ErrorAction SilentlyContinue | Where-Object {
            $_.InitialDetectionTime -gt (Get-Date).AddHours(-24)
        }
        foreach ($t in $threats) {
            Write-Alert "DEFENDER DETECTION: ThreatID=$($t.ThreatID) at $($t.InitialDetectionTime)" "ALERT"
        }
    } catch {
        Write-Alert "Defender health check error: $($_.Exception.Message)" "WARNING"
    }
}

# =============================================================================
# MONITOR 1: Suspicious Logon Detection (brute force / RDP / network)
# =============================================================================
function Monitor-Logons {
    Write-Alert "Starting logon monitor..." "INFO"
    $query = @"
<QueryList>
  <Query Id="0" Path="Security">
    <Select Path="Security">*[System[(EventID=4624 or EventID=4625)]]</Select>
  </Query>
</QueryList>
"@
    try {
        $events = Get-WinEvent -FilterXml $query -MaxEvents 100 -ErrorAction SilentlyContinue
        if ($null -eq $events) { Write-Alert "No recent logon events found." "INFO"; return }

        $suspiciousLogonTypes = @(3, 4, 5, 7, 8, 9, 10)  # network, batch, service, unlock, cleartext, newcreds, RDP
        $failedAttempts = @{}

        foreach ($event in $events) {
            $xml = [xml]$event.ToXml()
            $eventData = $xml.Event.EventData.Data
            $logonType = ($eventData | Where-Object { $_.Name -eq "LogonType" }).'#text'
            $userName  = ($eventData | Where-Object { $_.Name -eq "TargetUserName" }).'#text'
            $sourceIP  = ($eventData | Where-Object { $_.Name -eq "IpAddress" }).'#text'

            if ($event.Id -eq 4625) {
                if ($sourceIP) {
                    if ($failedAttempts.ContainsKey($sourceIP)) { $failedAttempts[$sourceIP]++ }
                    else { $failedAttempts[$sourceIP] = 1 }
                }
            }

            if ($event.Id -eq 4624 -and ($suspiciousLogonTypes -contains [int]$logonType)) {
                if ($sourceIP -and $sourceIP -ne "-" -and $sourceIP -ne "::1" -and $sourceIP -ne "127.0.0.1") {
                    Write-Alert "SUSPICIOUS LOGON: User=$userName Type=$logonType IP=$sourceIP" "ALERT"
                }
            }
        }

        foreach ($ip in $failedAttempts.Keys) {
            $n = $failedAttempts[$ip]
            if ($n -ge 5 -and $ip -ne "-" -and $ip -ne "::1" -and $ip -ne "127.0.0.1") {
                Write-Alert "BRUTE FORCE DETECTED: $n failed attempts from $ip" "CRITICAL"
                Block-SuspiciousIP -IPAddress $ip -Reason "Brute force logon attempts ($n failures)"
            }
        }

        Write-Alert "Logon scan complete. Events analyzed: $($events.Count)" "INFO"
    } catch {
        Write-Alert "Logon monitor error: $($_.Exception.Message)" "WARNING"
    }
}

# =============================================================================
# MONITOR 2: Suspicious Network Connections + backdoor listeners
# =============================================================================
function Monitor-Network {
    Write-Alert "Starting network connection monitor..." "INFO"
    $suspiciousPorts = @(4444, 5555, 6666, 7777, 8888, 9999, 1337, 31337, 1234, 4443, 8443, 9994, 9995, 9996)
    $suspiciousIPs = @()   # add known-bad IPs here
    $suspiciousCount = 0

    try {
        $connections = Get-NetTCPConnection -State Established -ErrorAction SilentlyContinue
        foreach ($conn in $connections) {
            $remotePort = $conn.RemotePort
            $remoteIP   = $conn.RemoteAddress
            $owningPid  = $conn.OwningProcess
            $procName = "Unknown"
            if ($owningPid -gt 0) {
                $proc = Get-Process -Id $owningPid -ErrorAction SilentlyContinue
                if ($proc) { $procName = $proc.ProcessName }
            }

            if ($suspiciousPorts -contains $remotePort) {
                Write-Alert "SUSPICIOUS CONNECTION: ${remoteIP}:${remotePort} (PID $owningPid/$procName)" "ALERT"
                $suspiciousCount++
            }
            if ($suspiciousIPs -contains $remoteIP) {
                Write-Alert "KNOWN BAD IP: $remoteIP connected (PID $owningPid/$procName)" "CRITICAL"
                Block-SuspiciousIP -IPAddress $remoteIP -Reason "Connection to known malicious IP"
                $suspiciousCount++
            }
        }

        # Backdoor listeners are a SEPARATE query (Established was filtered above).
        $listeners = Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue
        foreach ($lc in $listeners) {
            if ($suspiciousPorts -contains $lc.LocalPort) {
                $owningPid = $lc.OwningProcess
                $procName = "Unknown"
                if ($owningPid -gt 0) {
                    $proc = Get-Process -Id $owningPid -ErrorAction SilentlyContinue
                    if ($proc) { $procName = $proc.ProcessName }
                }
                Write-Alert "BACKDOOR LISTENER: port $($lc.LocalPort) (PID $owningPid/$procName)" "CRITICAL"
                $suspiciousCount++
            }
        }

        Write-Alert "Network scan complete. Suspicious: $suspiciousCount" "INFO"
    } catch {
        Write-Alert "Network monitor error: $($_.Exception.Message)" "WARNING"
    }
}

# =============================================================================
# MONITOR 3: Suspicious Process Detection (self-safe)
# =============================================================================
function Monitor-Processes {
    Write-Alert "Starting process monitor..." "INFO"
    $suspiciousPaths = @(
        "$env:TEMP", "$env:APPDATA", "$env:LOCALAPPDATA\Temp",
        "C:\Users\Public", "C:\Windows\Temp"
    )
    $suspiciousCount = 0

    try {
        $processes = Get-Process -ErrorAction SilentlyContinue
        foreach ($proc in $processes) {
            $procName = $proc.ProcessName.ToLower()

            # Never touch Tlamatini's own processes.
            if (Test-IsSelf $proc.Path) { continue }

            $tier = Get-ThreatTier $proc
            if ($tier -eq "malware") {
                Write-Alert "MALWARE PROCESS: $($proc.ProcessName) (PID $($proc.Id)) path=$($proc.Path)" "CRITICAL"
                Stop-SuspiciousProcess -ProcessId $proc.Id -ProcessName $proc.ProcessName -Reason "Known attacker tool"
                $suspiciousCount++
            } elseif ($tier -eq "dualuse") {
                if ($Aggressive) {
                    Write-Alert "OFFENSIVE TOOL (aggressive): $($proc.ProcessName) (PID $($proc.Id)) - killing" "CRITICAL"
                    Stop-SuspiciousProcess -ProcessId $proc.Id -ProcessName $proc.ProcessName -Reason "Dual-use offensive tool (-Aggressive)"
                } else {
                    Write-Alert "OFFENSIVE TOOL RUNNING: $($proc.ProcessName) (PID $($proc.Id)) - dual-use, NOT killed (Tlamatini may use it). Path=$($proc.Path)" "ALERT"
                }
                $suspiciousCount++
            }

            # Processes running from temp/user directories (excluding self + explorer).
            try {
                $path = $proc.Path
                if ($path -and (-not (Test-IsSelf $path))) {
                    foreach ($suspPath in $suspiciousPaths) {
                        if ($path -like "$suspPath\*" -and $procName -ne "explorer") {
                            Write-Alert "SUSPICIOUS PATH: $($proc.ProcessName) (PID $($proc.Id)) running from $path" "WARNING"
                            $suspiciousCount++
                            break
                        }
                    }
                }
            } catch { }
        }

        Write-Alert "Process scan complete. Processes: $($processes.Count) | Suspicious: $suspiciousCount" "INFO"
    } catch {
        Write-Alert "Process monitor error: $($_.Exception.Message)" "WARNING"
    }
}

# =============================================================================
# MONITOR 4: Suspicious Scheduled Tasks (persistence)
# =============================================================================
function Monitor-ScheduledTasks {
    Write-Alert "Starting scheduled task audit..." "INFO"
    try {
        $tasks = Get-ScheduledTask -ErrorAction SilentlyContinue | Where-Object {
            $_.State -ne "Disabled" -and $_.TaskPath -notlike "\Microsoft\*" -and $_.TaskPath -notlike "\Tlamatini*"
        }
        if ($null -eq $tasks) { Write-Alert "No non-system scheduled tasks found." "INFO"; return }

        $suspiciousCount = 0
        foreach ($task in $tasks) {
            foreach ($action in $task.Actions) {
                $execPath  = $action.Execute
                $arguments = $action.Arguments
                if ($arguments -match "-enc|-encodedcommand|-e ") {
                    Write-Alert "SUSPICIOUS TASK: $($task.TaskName) - encoded PowerShell command" "CRITICAL"
                    Write-Alert "  Execute: $execPath | Args: $arguments" "CRITICAL"
                    $suspiciousCount++
                }
                if ($execPath -match "Temp|AppData|Users\\Public") {
                    Write-Alert "SUSPICIOUS TASK: $($task.TaskName) - executes from temp/user path: $execPath" "WARNING"
                    $suspiciousCount++
                }
                if ($arguments -match "DownloadFile|Invoke-WebRequest|iex|Invoke-Expression|Net.WebClient|certutil|bitsadmin") {
                    Write-Alert "SUSPICIOUS TASK: $($task.TaskName) - download/execute command" "CRITICAL"
                    Write-Alert "  Args: $arguments" "CRITICAL"
                    $suspiciousCount++
                }
            }
        }
        Write-Alert "Scheduled task scan complete. Tasks: $($tasks.Count) | Suspicious: $suspiciousCount" "INFO"
    } catch {
        Write-Alert "Scheduled task monitor error: $($_.Exception.Message)" "WARNING"
    }
}

# =============================================================================
# MONITOR 5: Suspicious Service Detection
# =============================================================================
function Monitor-Services {
    Write-Alert "Starting service audit..." "INFO"
    try {
        $services = Get-CimInstance -ClassName Win32_Service -ErrorAction SilentlyContinue | Where-Object {
            $_.State -eq "Running" -and $_.PathName -notlike "*\Windows\*" -and $_.PathName -notlike "*\Program Files*"
        }
        if ($null -eq $services) { Write-Alert "No suspicious services found." "INFO"; return }

        $suspiciousCount = 0
        foreach ($svc in $services) {
            $pathName = $svc.PathName
            $svcName  = $svc.Name
            if (Test-IsSelf $pathName) { continue }
            if ($pathName -match "Temp|AppData|Users\\Public") {
                Write-Alert "SUSPICIOUS SERVICE: $svcName - path: $pathName" "CRITICAL"
                $suspiciousCount++
            }
            if ([string]::IsNullOrWhiteSpace($svc.Description) -and $svcName -notlike "tlamatini*") {
                Write-Alert "SUSPICIOUS SERVICE: $svcName - no description, path: $pathName" "WARNING"
                $suspiciousCount++
            }
        }
        Write-Alert "Service scan complete. Suspicious: $suspiciousCount" "INFO"
    } catch {
        Write-Alert "Service monitor error: $($_.Exception.Message)" "WARNING"
    }
}

# =============================================================================
# MONITOR 6: Registry persistence (Run keys + Winlogon + IFEO + AppInit)
# =============================================================================
function Monitor-RegistryPersistence {
    Write-Alert "Starting registry persistence check..." "INFO"
    $runKeys = @(
        "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Run",
        "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\RunOnce",
        "HKCU:\SOFTWARE\Microsoft\Windows\CurrentVersion\Run",
        "HKCU:\SOFTWARE\Microsoft\Windows\CurrentVersion\RunOnce",
        "HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Run",
        "HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon",
        "HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Windows"
    )
    $suspiciousCount = 0
    foreach ($key in $runKeys) {
        try {
            if (Test-Path $key) {
                $properties = Get-ItemProperty -Path $key -ErrorAction SilentlyContinue
                if ($null -ne $properties) {
                    $properties.PSObject.Properties | ForEach-Object {
                        if ($_.Name -notlike "PS*") {
                            $value = "$($_.Value)"
                            $name  = $_.Name
                            if ($value -match "Temp|AppData|Users\\Public|powershell.*-enc|DownloadFile|certutil|mshta|rundll32.*javascript") {
                                Write-Alert "SUSPICIOUS REGKEY: $key\$name = $value" "CRITICAL"
                                $suspiciousCount++
                            }
                            # Winlogon Shell/Userinit hijack
                            if (($name -eq "Shell" -and $value -notmatch "explorer\.exe") -or
                                ($name -eq "Userinit" -and $value -notmatch "userinit\.exe") -or
                                ($name -eq "AppInit_DLLs" -and -not [string]::IsNullOrWhiteSpace($value))) {
                                Write-Alert "PERSISTENCE HIJACK: $key\$name = $value" "CRITICAL"
                                $suspiciousCount++
                            }
                        }
                    }
                }
            }
        } catch { }
    }
    # Image File Execution Options debugger hijack
    try {
        $ifeo = "HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Image File Execution Options"
        if (Test-Path $ifeo) {
            Get-ChildItem $ifeo -ErrorAction SilentlyContinue | ForEach-Object {
                $dbg = (Get-ItemProperty $_.PSPath -Name "Debugger" -ErrorAction SilentlyContinue).Debugger
                if ($dbg) {
                    Write-Alert "IFEO DEBUGGER HIJACK: $($_.PSChildName) -> $dbg" "CRITICAL"
                    $suspiciousCount++
                }
            }
        }
    } catch { }
    Write-Alert "Registry persistence check complete. Suspicious: $suspiciousCount" "INFO"
}

# =============================================================================
# MONITOR 7: New files in critical directories (last 24h)
# =============================================================================
function Monitor-CriticalDirectories {
    Write-Alert "Starting critical directory check..." "INFO"
    $criticalPaths = @(
        "C:\Windows\Temp",
        "C:\Users\Public",
        "$env:TEMP",
        "$env:APPDATA\Microsoft\Windows\Start Menu\Programs\Startup",
        "$env:ProgramData\Microsoft\Windows\Start Menu\Programs\StartUp"
    )
    $badExt = @(".exe", ".dll", ".ps1", ".bat", ".cmd", ".vbs", ".js", ".scr", ".hta", ".lnk")
    $suspiciousCount = 0
    foreach ($path in $criticalPaths) {
        if (Test-Path $path) {
            try {
                $recentFiles = Get-ChildItem -Path $path -Recurse -File -ErrorAction SilentlyContinue | Where-Object {
                    $_.LastWriteTime -gt (Get-Date).AddHours(-24) -and ($badExt -contains $_.Extension.ToLower())
                }
                foreach ($file in $recentFiles) {
                    if (Test-IsSelf $file.FullName) { continue }
                    Write-Alert "RECENT FILE in $path : $($file.Name) (modified $($file.LastWriteTime))" "WARNING"
                    $suspiciousCount++
                }
            } catch { }
        }
    }
    Write-Alert "Critical directory check complete. Recent suspicious files: $suspiciousCount" "INFO"
}

# =============================================================================
# MONITOR 8: Ransomware / destructive-action indicators
# =============================================================================
function Monitor-Ransomware {
    Write-Alert "Checking for ransomware / destructive indicators..." "INFO"
    $count = 0

    # (a) Shadow-copy deletion / backup / recovery tampering via process creation (4688).
    $q = @"
<QueryList>
  <Query Id="0" Path="Security">
    <Select Path="Security">*[System[(EventID=4688)]]</Select>
  </Query>
</QueryList>
"@
    try {
        $evts = Get-WinEvent -FilterXml $q -MaxEvents 300 -ErrorAction SilentlyContinue | Where-Object {
            $_.TimeCreated -gt (Get-Date).AddHours(-2)
        }
        foreach ($e in $evts) {
            $x = [xml]$e.ToXml()
            $cmd = ($x.Event.EventData.Data | Where-Object { $_.Name -eq "CommandLine" }).'#text'
            $np  = ($x.Event.EventData.Data | Where-Object { $_.Name -eq "NewProcessName" }).'#text'
            $line = "$np $cmd"
            if ($line -match "vssadmin.*delete.*shadow" -or
                $line -match "wmic.*shadowcopy.*delete" -or
                $line -match "wbadmin.*delete" -or
                $line -match "bcdedit.*(recoveryenabled\s+no|bootstatuspolicy\s+ignoreallfailures)" -or
                $line -match "cipher\s+/w" -or
                $line -match "wevtutil\s+(cl|clear-log)" -or
                $line -match "fsutil\s+usn\s+deletejournal") {
                Write-Alert "RANSOMWARE/DESTRUCTIVE INDICATOR: $line" "CRITICAL"
                Send-DesktopNotification "TLAMATINI: Ransomware indicator" "$np was seen destroying backups/recovery"
                $count++
            }
        }
    } catch { }

    # (b) Ransom notes + encrypted-extension bursts in user data (last 24h).
    $watch = @("$env:USERPROFILE\Desktop", "$env:USERPROFILE\Documents", "$env:USERPROFILE\Pictures", "$env:PUBLIC")
    $noteNames = @("*DECRYPT*", "*_readme*", "*HOW*TO*DECRYPT*", "*RECOVER*FILES*", "*RANSOM*", "*restore*files*", "*!!!*")
    $badExt = @(".locked", ".encrypted", ".crypt", ".enc", ".crypto", ".wncry", ".lockbit", ".ryk", ".conti", ".hive", ".akira", ".basta", ".onion", ".pay")
    foreach ($p in $watch) {
        if (Test-Path $p) {
            try {
                $recent = Get-ChildItem $p -Recurse -File -ErrorAction SilentlyContinue | Where-Object {
                    $_.LastWriteTime -gt (Get-Date).AddHours(-24)
                }
                $encHits = $recent | Where-Object { $badExt -contains $_.Extension.ToLower() }
                if (@($encHits).Count -ge 5) {
                    Write-Alert "RANSOMWARE: $(@($encHits).Count) files with encryption extensions in $p" "CRITICAL"
                    Send-DesktopNotification "TLAMATINI: Files being encrypted" "$(@($encHits).Count) encrypted-extension files in $p"
                    $count++
                }
                foreach ($n in $noteNames) {
                    foreach ($nf in ($recent | Where-Object { $_.Name -like $n })) {
                        Write-Alert "RANSOM NOTE: $($nf.FullName)" "CRITICAL"
                        $count++
                    }
                }
            } catch { }
        }
    }
    Write-Alert "Ransomware check complete. Indicators: $count" "INFO"
}

# =============================================================================
# MONITOR 9: Account / privilege abuse (attacker persistence & escalation)
# =============================================================================
function Monitor-AccountThreats {
    Write-Alert "Checking for account/privilege abuse..." "INFO"
    $count = 0
    $q = @"
<QueryList>
  <Query Id="0" Path="Security">
    <Select Path="Security">*[System[(EventID=4720 or EventID=4728 or EventID=4732 or EventID=4756)]]</Select>
  </Query>
</QueryList>
"@
    try {
        $evts = Get-WinEvent -FilterXml $q -MaxEvents 50 -ErrorAction SilentlyContinue | Where-Object {
            $_.TimeCreated -gt (Get-Date).AddHours(-24)
        }
        foreach ($e in $evts) {
            $m = switch ($e.Id) {
                4720 { "NEW LOCAL ACCOUNT CREATED" }
                4728 { "USER ADDED TO GLOBAL ADMIN GROUP" }
                4732 { "USER ADDED TO LOCAL ADMIN GROUP" }
                4756 { "USER ADDED TO UNIVERSAL ADMIN GROUP" }
                default { "ACCOUNT EVENT $($e.Id)" }
            }
            Write-Alert "$m (event $($e.Id) at $($e.TimeCreated))" "ALERT"
            $count++
        }
    } catch { }
    try {
        $admins = Get-LocalGroupMember -Group "Administrators" -ErrorAction SilentlyContinue
        if ($admins) {
            $names = ($admins | ForEach-Object { $_.Name }) -join ", "
            Write-Alert "Current local administrators: $names" "INFO"
        }
    } catch { }
    Write-Alert "Account/privilege check complete. Events: $count" "INFO"
}

# =============================================================================
# MAIN EXECUTION
# =============================================================================
function Invoke-AllMonitors {
    Monitor-DefenderHealth
    Monitor-Logons
    Monitor-Network
    Monitor-Processes
    Monitor-ScheduledTasks
    Monitor-Services
    Monitor-RegistryPersistence
    Monitor-CriticalDirectories
    Monitor-Ransomware
    Monitor-AccountThreats
}

Write-Host ""
Write-Host "================================================" -ForegroundColor Cyan
Write-Host "  TLAMATINI ACTIVE DEFENDER v$ScriptVersion" -ForegroundColor Cyan
Write-Host "  Created by Angela Lopez Mendoza (@angelahack1)" -ForegroundColor Cyan
Write-Host "================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "This is a DEFENSIVE monitoring script." -ForegroundColor Green
Write-Host "It detects hackers and isolates threats." -ForegroundColor Green
Write-Host "It does NOT disable security or destroy data." -ForegroundColor Green
if ($DetectOnly) { Write-Host "MODE: DETECT-ONLY (no auto-block/kill)." -ForegroundColor Yellow }
elseif ($Aggressive) { Write-Host "MODE: ARMED + AGGRESSIVE (kills dual-use tools too)." -ForegroundColor Yellow }
else { Write-Host "MODE: ARMED (auto-kills known malware; alerts on dual-use)." -ForegroundColor Yellow }
Write-Host ""

Write-Alert "=== TLAMATINI DEFENDER START (v$ScriptVersion) ===" "INFO"
Write-Alert "Host: $env:COMPUTERNAME | User: $env:USERNAME | Respond=$($script:Respond) | Aggressive=$([bool]$Aggressive)" "INFO"

if ($Watch) {
    Write-Alert "WATCH MODE: scanning every $IntervalSeconds s. Press Ctrl+C to stop." "INFO"
    try {
        while ($true) {
            $s = Get-Date
            Invoke-AllMonitors
            $d = ((Get-Date) - $s).TotalSeconds
            Write-Alert "--- Sweep complete in $([math]::Round($d,1))s. Sleeping $IntervalSeconds s. ---" "INFO"
            Start-Sleep -Seconds $IntervalSeconds
        }
    } finally {
        Write-Alert "=== TLAMATINI DEFENDER WATCH STOPPED ===" "INFO"
    }
} else {
    $startTime = Get-Date
    Invoke-AllMonitors
    $duration = ((Get-Date) - $startTime).TotalSeconds
    Write-Alert "=== TLAMATINI DEFENDER COMPLETE ===" "INFO"
    Write-Alert "Duration: $([math]::Round($duration,1)) seconds" "INFO"
    Write-Alert "Alerts logged to: $AlertLog" "INFO"

    Write-Host ""
    Write-Host "================================================" -ForegroundColor Cyan
    Write-Host "  DEFENDER SCAN COMPLETE" -ForegroundColor Cyan
    Write-Host "================================================" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "  Alerts log:  $AlertLog" -ForegroundColor Green
    Write-Host "  Full log:    $MonitorLog" -ForegroundColor Green
    Write-Host ""
    Write-Host "  Review CRITICAL and ALERT entries as investigation leads." -ForegroundColor Yellow
    Write-Host "  Corroborate the evidence before containment or attribution." -ForegroundColor Yellow
    Write-Host ""
    Write-Host "================================================" -ForegroundColor Cyan
    Write-Host "  Created by Angela Lopez Mendoza (@angelahack1)" -ForegroundColor Cyan
    Write-Host "  Tlamatini - the one who knows" -ForegroundColor Cyan
    Write-Host "================================================" -ForegroundColor Cyan
    Write-Host ""
    Read-Host "Press Enter to finish"
}
