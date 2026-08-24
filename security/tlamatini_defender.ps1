# =============================================================================
# TLAMATINI ACTIVE DEFENDER - SECURITY MONITORING & AUTO-RESPONSE
# =============================================================================
# Purpose: Real-time intrusion detection and automated defensive response.
#          This is NOT malware. This is a DEFENDER that:
#          - Monitors logons, network, processes, tasks, services
#          - Detects hacker activity in real-time
#          - Auto-isolates threats (blocks IPs, kills processes)
#          - Alerts the user via event log + desktop notification
#
# This script does NOT:
#   - Disable any security feature
#   - Wipe or destroy data
#   - Bypass Windows protections
#   - Grant god-mode or unrestricted access
#
# REQUIREMENTS:
#   - Run as Administrator
#   - Windows 10/11
#   - Tlamatini whitelist script should be run first
#
# Author: Tlamatini (created by Angela Lopez Mendoza)
# =============================================================================

#Requires -RunAsAdministrator

$ErrorActionPreference = "Continue"
$ScriptVersion = "2.0"
# --- AUTO-DETECT: logs go next to this .ps1 (in <script-dir>\security_logs) ---
# Path-independent v2: works from any install directory on any drive.
$LogDir = Join-Path $PSScriptRoot "security_logs"
$AlertLog = "$LogDir\alerts.log"
$MonitorLog = "$LogDir\monitor.log"

# Create log directory
if (-not (Test-Path $LogDir)) {
    New-Item -ItemType Directory -Path $LogDir -Force | Out-Null
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
        # Use Windows toast notification via BurntToast-style raw approach
        Add-Type -AssemblyName System.Windows.Forms
        $notify = New-Object System.Windows.Forms.NotifyIcon
        $notify.Icon = [System.Drawing.SystemIcons]::Warning
        $notify.Visible = $true
        $notify.ShowBalloonTip(10000, $Title, $Message, [System.Windows.Forms.ToolTipIcon]::Warning)
        Start-Sleep -Seconds 2
        $notify.Dispose()
    } catch {
        # Non-critical - log instead
        Write-Alert "Desktop notification failed: $($_.Exception.Message)" "WARNING"
    }
}

function Block-SuspiciousIP {
    param([string]$IPAddress, [string]$Reason)
    try {
        $ruleName = "Tlamatini Block $IPAddress"
        $existing = Get-NetFirewallRule -DisplayName $ruleName -ErrorAction SilentlyContinue
        if ($null -eq $existing) {
            New-NetFirewallRule -DisplayName $ruleName `
                -Direction Inbound `
                -Action Block `
                -RemoteAddress $IPAddress `
                -Profile Any | Out-Null
            Write-Alert "BLOCKED IP $IPAddress - $Reason" "CRITICAL"
            Send-DesktopNotification "TLAMATINI: Threat Blocked" "Blocked IP $IPAddress - $Reason"
        }
    } catch {
        Write-Alert "Failed to block IP $IPAddress : $($_.Exception.Message)" "WARNING"
    }
}

function Kill-SuspiciousProcess {
    param([int]$ProcessId, [string]$ProcessName, [string]$Reason)
    try {
        $proc = Get-Process -Id $ProcessId -ErrorAction SilentlyContinue
        if ($null -ne $proc) {
            Stop-Process -Id $ProcessId -Force -ErrorAction Stop
            Write-Alert "KILLED process $ProcessName (PID $ProcessId) - $Reason" "CRITICAL"
            Send-DesktopNotification "TLAMATINI: Process Killed" "Killed $ProcessName (PID $ProcessId) - $Reason"
        }
    } catch {
        Write-Alert "Failed to kill process $ProcessName (PID $ProcessId) : $($_.Exception.Message)" "WARNING"
    }
}

# =============================================================================
# MONITOR 1: Suspicious Logon Detection
# =============================================================================
function Monitor-Logons {
    Write-Alert "Starting logon monitor..." "INFO"

    # Query recent logon events (Event ID 4624 = successful logon, 4625 = failed)
    $query = @"
<QueryList>
  <Query Id="0" Path="Security">
    <Select Path="Security">*[System[(EventID=4624 or EventID=4625)]]</Select>
  </Query>
</QueryList>
"@

    try {
        $events = Get-WinEvent -FilterXml $query -MaxEvents 50 -ErrorAction SilentlyContinue
        if ($null -eq $events) {
            Write-Alert "No recent logon events found." "INFO"
            return
        }

        $suspiciousLogonTypes = @(4, 5, 7, 8, 9, 10)  # Remote, service, unlock, networkcleartext, newcredentials, remoteinteractive
        $failedAttempts = @{}

        foreach ($event in $events) {
            $xml = [xml]$event.ToXml()
            $eventData = $xml.Event.EventData.Data

            $logonType = ($eventData | Where-Object { $_.Name -eq "LogonType" }).'#text'
            $userName = ($eventData | Where-Object { $_.Name -eq "TargetUserName" }).'#text'
            $sourceIP = ($eventData | Where-Object { $_.Name -eq "IpAddress" }).'#text'
            $status = ($eventData | Where-Object { $_.Name -eq "Status" }).'#text'

            # Event 4625 = failed logon - track for brute force
            if ($event.Id -eq 4625) {
                if ($failedAttempts.ContainsKey($sourceIP)) {
                    $failedAttempts[$sourceIP]++
                } else {
                    $failedAttempts[$sourceIP] = 1
                }
            }

            # Alert on suspicious logon types (RDP, network, service)
            if ($event.Id -eq 4624 -and $suspiciousLogonTypes -contains [int]$logonType) {
                if ($sourceIP -and $sourceIP -ne "-" -and $sourceIP -ne "::1" -and $sourceIP -ne "127.0.0.1") {
                    Write-Alert "SUSPICIOUS LOGON: User=$userName Type=$logonType IP=$sourceIP" "ALERT"
                }
            }
        }

        # Check for brute force (5+ failed attempts from same IP)
        foreach ($ip in $failedAttempts.Keys) {
            if ($failedAttempts[$ip] -ge 5 -and $ip -ne "-" -and $ip -ne "::1" -and $ip -ne "127.0.0.1") {
                Write-Alert "BRUTE FORCE DETECTED: $failedAttempts[$ip] failed attempts from $ip" "CRITICAL"
                Block-SuspiciousIP -IPAddress $ip -Reason "Brute force logon attempts ($($failedAttempts[$ip]) failures)"
            }
        }

        Write-Alert "Logon scan complete. Events analyzed: $($events.Count)" "INFO"
    } catch {
        Write-Alert "Logon monitor error: $($_.Exception.Message)" "WARNING"
    }
}

# =============================================================================
# MONITOR 2: Suspicious Network Connections
# =============================================================================
function Monitor-Network {
    Write-Alert "Starting network connection monitor..." "INFO"

    try {
        # Get all established TCP connections
        $connections = Get-NetTCPConnection -State Established -ErrorAction SilentlyContinue
        if ($null -eq $connections) {
            Write-Alert "No established connections found." "INFO"
            return
        }

        # Known suspicious ports (C2, backdoors, etc.)
        $suspiciousPorts = @(4444, 5555, 6666, 7777, 8888, 9999, 1337, 31337, 1234, 4443, 8443, 9994, 9995, 9996)

        # Known suspicious external IPs (add more as discovered)
        $suspiciousIPs = @()

        $suspiciousCount = 0
        foreach ($conn in $connections) {
            $remotePort = $conn.RemotePort
            $remoteIP = $conn.RemoteAddress
            $localPort = $conn.LocalPort
            $owningPid = $conn.OwningProcess

            # Check for connections to suspicious ports
            if ($suspiciousPorts -contains $remotePort) {
                $procName = "Unknown"
                if ($owningPid -gt 0) {
                    $proc = Get-Process -Id $owningPid -ErrorAction SilentlyContinue
                    if ($proc) { $procName = $proc.ProcessName }
                }
                Write-Alert "SUSPICIOUS CONNECTION: $remoteIP:$remotePort (PID $owningPid/$procName)" "ALERT"
                $suspiciousCount++
            }

            # Check for connections to known bad IPs
            if ($suspiciousIPs -contains $remoteIP) {
                Write-Alert "KNOWN BAD IP: $remoteIP connected (PID $owningPid)" "CRITICAL"
                Block-SuspiciousIP -IPAddress $remoteIP -Reason "Connection to known malicious IP"
                $suspiciousCount++
            }

            # Check for listening on unexpected ports (potential backdoor)
            if ($conn.State -eq "Listen" -and $suspiciousPorts -contains $localPort) {
                $procName = "Unknown"
                if ($owningPid -gt 0) {
                    $proc = Get-Process -Id $owningPid -ErrorAction SilentlyContinue
                    if ($proc) { $procName = $proc.ProcessName }
                }
                Write-Alert "BACKDOOR LISTENER: Port $localPort (PID $owningPid/$procName)" "CRITICAL"
                $suspiciousCount++
            }
        }

        Write-Alert "Network scan complete. Connections: $($connections.Count) | Suspicious: $suspiciousCount" "INFO"
    } catch {
        Write-Alert "Network monitor error: $($_.Exception.Message)" "WARNING"
    }
}

# =============================================================================
# MONITOR 3: Suspicious Process Detection
# =============================================================================
function Monitor-Processes {
    Write-Alert "Starting process monitor..." "INFO"

    try {
        $processes = Get-Process -ErrorAction SilentlyContinue
        if ($null -eq $processes) { return }

        # Suspicious process name patterns
        $suspiciousPatterns = @(
            "*mimikatz*", "*psexec*", "*cobalt*", *metasploit*, *nc.exe*,
            *ncat*, *nmap*, *hydra*, *john*, *hashcat*, *responder*,
            *powersploit*, *rubeus*, *seatbelt*, *sharp*, *kerberoast*
        )

        # Suspicious paths (processes running from temp/user directories)
        $suspiciousPaths = @(
            "$env:TEMP", "$env:APPDATA", "$env:LOCALAPPDATA\Temp",
            "C:\Users\Public", "C:\Windows\Temp"
        )

        $suspiciousCount = 0
        foreach ($proc in $processes) {
            $procName = $proc.ProcessName.ToLower()

            # Check against suspicious name patterns
            foreach ($pattern in $suspiciousPatterns) {
                if ($procName -like $pattern) {
                    Write-Alert "MALWARE PROCESS: $($proc.ProcessName) (PID $($proc.Id)) - matches pattern $pattern" "CRITICAL"
                    Kill-SuspiciousProcess -ProcessId $proc.Id -ProcessName $proc.ProcessName -Reason "Matches malware pattern: $pattern"
                    $suspiciousCount++
                    break
                }
            }

            # Check for processes running from suspicious paths
            try {
                $path = $proc.Path
                if ($path) {
                    foreach ($suspPath in $suspiciousPaths) {
                        if ($path -like "$suspPath\*" -and $procName -notlike "tlamatini*" -and $procName -ne "explorer") {
                            Write-Alert "SUSPICIOUS PATH: $($proc.ProcessName) (PID $($proc.Id)) running from $path" "WARNING"
                            $suspiciousCount++
                            break
                        }
                    }
                }
            } catch {
                # Some processes dont expose Path - skip
            }
        }

        Write-Alert "Process scan complete. Processes: $($processes.Count) | Suspicious: $suspiciousCount" "INFO"
    } catch {
        Write-Alert "Process monitor error: $($_.Exception.Message)" "WARNING"
    }
}

# =============================================================================
# MONITOR 4: Suspicious Scheduled Tasks (Persistence Detection)
# =============================================================================
function Monitor-ScheduledTasks {
    Write-Alert "Starting scheduled task audit..." "INFO"

    try {
        $tasks = Get-ScheduledTask -ErrorAction SilentlyContinue | Where-Object {
            $_.State -ne "Disabled" -and $_.TaskPath -notlike "\Microsoft\*" -and $_.TaskPath -notlike "\Tlamatini*"
        }

        if ($null -eq $tasks) {
            Write-Alert "No non-system scheduled tasks found." "INFO"
            return
        }

        $suspiciousCount = 0
        foreach ($task in $tasks) {
            $taskName = $task.TaskName
            $taskPath = $task.TaskPath
            $actions = $task.Actions

            foreach ($action in $actions) {
                $execPath = $action.Execute
                $arguments = $action.Arguments

                # Check for PowerShell encoded commands (common persistence technique)
                if ($arguments -match "-enc|-encodedcommand|-e ") {
                    Write-Alert "SUSPICIOUS TASK: $taskName - uses encoded PowerShell command" "CRITICAL"
                    Write-Alert "  Execute: $execPath" "CRITICAL"
                    Write-Alert "  Args: $arguments" "CRITICAL"
                    $suspiciousCount++
                }

                # Check for tasks running from temp/user directories
                if ($execPath -match "Temp|AppData|Users\\Public") {
                    Write-Alert "SUSPICIOUS TASK: $taskName - executes from temp/user path: $execPath" "WARNING"
                    $suspiciousCount++
                }

                # Check for tasks that download content
                if ($arguments -match "DownloadFile|Invoke-WebRequest|iex|Invoke-Expression|Net.WebClient") {
                    Write-Alert "SUSPICIOUS TASK: $taskName - contains download/execute command" "CRITICAL"
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
        $services = Get-WmiObject -Class Win32_Service -ErrorAction SilentlyContinue | Where-Object {
            $_.State -eq "Running" -and $_.PathName -notlike "*\Windows\*" -and $_.PathName -notlike "*\Program Files\*"
        }

        if ($null -eq $services) {
            Write-Alert "No suspicious services found." "INFO"
            return
        }

        $suspiciousCount = 0
        foreach ($svc in $services) {
            $pathName = $svc.PathName
            $svcName = $svc.Name

            # Check for services running from temp/user directories
            if ($pathName -match "Temp|AppData|Users\\Public") {
                Write-Alert "SUSPICIOUS SERVICE: $svcName - path: $pathName" "CRITICAL"
                $suspiciousCount++
            }

            # Check for services with no description (common for malware)
            if ([string]::IsNullOrWhiteSpace($svc.Description) -and $svcName -notlike "tlamatini*") {
                Write-Alert "SUSPICIOUS SERVICE: $svcName - no description, path: $pathName" "WARNING"
                $suspiciousCount++
            }
        }

        Write-Alert "Service scan complete. Services checked | Suspicious: $suspiciousCount" "INFO"
    } catch {
        Write-Alert "Service monitor error: $($_.Exception.Message)" "WARNING"
    }
}

# =============================================================================
# MONITOR 6: Registry Run Keys (Persistence Detection)
# =============================================================================
function Monitor-RegistryPersistence {
    Write-Alert "Starting registry persistence check..." "INFO"

    $runKeys = @(
        "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Run",
        "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\RunOnce",
        "HKCU:\SOFTWARE\Microsoft\Windows\CurrentVersion\Run",
        "HKCU:\SOFTWARE\Microsoft\Windows\CurrentVersion\RunOnce",
        "HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Run"
    )

    $suspiciousCount = 0
    foreach ($key in $runKeys) {
        try {
            if (Test-Path $key) {
                $properties = Get-ItemProperty -Path $key -ErrorAction SilentlyContinue
                if ($null -ne $properties) {
                    $properties.PSObject.Properties | ForEach-Object {
                        if ($_.Name -notlike "PS*") {
                            $value = $_.Value
                            $name = $_.Name

                            # Check for suspicious entries
                            if ($value -match "Temp|AppData|Users\\Public|powershell.*-enc|DownloadFile") {
                                Write-Alert "SUSPICIOUS REGKEY: $key\$name = $value" "CRITICAL"
                                $suspiciousCount++
                            }
                        }
                    }
                }
            }
        } catch {
            # Skip inaccessible keys
        }
    }

    Write-Alert "Registry persistence check complete. Suspicious: $suspiciousCount" "INFO"
}

# =============================================================================
# MONITOR 7: New File Detection in Critical Directories
# =============================================================================
function Monitor-CriticalDirectories {
    Write-Alert "Starting critical directory check..." "INFO"

    $criticalPaths = @(
        "C:\Windows\Temp",
        "C:\Users\Public",
        "$env:TEMP",
        "$env:APPDATA\Microsoft\Windows\Start Menu\Programs\Startup"
    )

    $suspiciousCount = 0
    foreach ($path in $criticalPaths) {
        if (Test-Path $path) {
            try {
                # Find files modified in the last 24 hours
                $recentFiles = Get-ChildItem -Path $path -Recurse -ErrorAction SilentlyContinue | Where-Object {
                    $_.LastWriteTime -gt (Get-Date).AddHours(-24) -and $_.Extension -in @(".exe", ".dll", ".ps1", ".bat", ".cmd", ".vbs", ".js")
                }

                if ($null -ne $recentFiles) {
                    foreach ($file in $recentFiles) {
                        Write-Alert "RECENT FILE in $path : $($file.Name) (modified $($file.LastWriteTime))" "WARNING"
                        $suspiciousCount++
                    }
                }
            } catch {
                # Skip inaccessible
            }
        }
    }

    Write-Alert "Critical directory check complete. Recent suspicious files: $suspiciousCount" "INFO"
}

# =============================================================================
# MAIN EXECUTION
# =============================================================================
Write-Host ""
Write-Host "================================================" -ForegroundColor Cyan
Write-Host "  TLAMATINI ACTIVE DEFENDER v$ScriptVersion" -ForegroundColor Cyan
Write-Host "  Created by Angela Lopez Mendoza (@angelahack1)" -ForegroundColor Cyan
Write-Host "================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "This is a DEFENSIVE monitoring script." -ForegroundColor Green
Write-Host "It detects hackers and isolates threats." -ForegroundColor Green
Write-Host "It does NOT disable security or destroy data." -ForegroundColor Green
Write-Host ""

$startTime = Get-Date
Write-Alert "=== TLAMATINI DEFENDER START ===" "INFO"
Write-Alert "Host: $env:COMPUTERNAME | User: $env:USERNAME | Time: $startTime" "INFO"

# Run all monitors
Monitor-Logons
Monitor-Network
Monitor-Processes
Monitor-ScheduledTasks
Monitor-Services
Monitor-RegistryPersistence
Monitor-CriticalDirectories

$endTime = Get-Date
$duration = ($endTime - $startTime).TotalSeconds

Write-Alert "=== TLAMATINI DEFENDER COMPLETE ===" "INFO"
Write-Alert "Duration: $duration seconds" "INFO"
Write-Alert "Alerts logged to: $AlertLog" "INFO"

Write-Host ""
Write-Host "================================================" -ForegroundColor Cyan
Write-Host "  DEFENDER SCAN COMPLETE" -ForegroundColor Cyan
Write-Host "================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "  Alerts log:  $AlertLog" -ForegroundColor Green
Write-Host "  Full log:    $MonitorLog" -ForegroundColor Green
Write-Host ""
Write-Host "  Review the alerts log for any CRITICAL or ALERT entries." -ForegroundColor Yellow
Write-Host "  Those are your hackers." -ForegroundColor Yellow
Write-Host ""
Write-Host "================================================" -ForegroundColor Cyan
Write-Host "  Created by Angela Lopez Mendoza (@angelahack1)" -ForegroundColor Cyan
Write-Host "  Tlamatini - the one who knows" -ForegroundColor Cyan
Write-Host "================================================" -ForegroundColor Cyan
Write-Host ""

Read-Host "Press Enter to finish"