$ErrorActionPreference = 'Continue'

# Result log — <install>\Temp when this ships next to Tlamatini.exe (the Temp
# directory policy), else the user's %TEMP%. Never a developer-specific path.
$appTemp = Join-Path $PSScriptRoot 'Temp'
if (Test-Path $appTemp) { $out = Join-Path $appTemp 'portfix_result.txt' }
else { $out = Join-Path $env:TEMP 'Tlamatini_portfix_result.txt' }
if (Test-Path $out) { Remove-Item $out -Force }

# Port to test — config.json's django_port when present (config.json ships next
# to the exe), else Tlamatini's default 8000. Fail-open: anything odd keeps 8000.
$port = 8000
try {
    $cfg = Join-Path $PSScriptRoot 'config.json'
    if (Test-Path $cfg) {
        $v = (Get-Content $cfg -Raw -Encoding UTF8 | ConvertFrom-Json).django_port
        if ($null -ne $v -and [int]$v -ge 1 -and [int]$v -le 65535) { $port = [int]$v }
    }
} catch { $port = 8000 }

function Log($m) { $m | Tee-Object -FilePath $out -Append | Out-Null; Write-Host $m }

Log "=== Tlamatini port-$port fix @ $(Get-Date) ==="
Log "Log file: $out"
Log "Admin: $([bool](([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltinRole]::Administrator)))"

Log ""
Log "--- STEP 1: reset TCP dynamic port range to Windows default (49152/16384) ---"
Log (netsh int ipv4 set dynamicport tcp start=49152 num=16384 2>&1 | Out-String)
Log "--- STEP 1b: reset UDP dynamic port range to default too ---"
Log (netsh int ipv4 set dynamicport udp start=49152 num=16384 2>&1 | Out-String)

Log ""
Log "--- STEP 2: restart WinNAT so it releases any stale low-port reservation ---"
$deps = @()
try { $deps = (Get-Service winnat -ErrorAction Stop).DependentServices | Where-Object { $_.Status -eq 'Running' } | Select-Object -ExpandProperty Name } catch {}
Log ("Running dependents to restore after: " + ($deps -join ', '))
Stop-Service winnat -Force -ErrorAction Continue
Start-Sleep -Seconds 1
Start-Service winnat -ErrorAction Continue
foreach ($d in $deps) { try { Start-Service $d -ErrorAction Stop; Log "  restarted dependent: $d" } catch { Log "  could not restart dependent ${d}: $_" } }
Log "WinNAT status: $((Get-Service winnat).Status)"

Log ""
Log "--- STEP 3: verify excluded ranges no longer cover $port ---"
Log (netsh interface ipv4 show excludedportrange protocol=tcp 2>&1 | Out-String)
Log "--- dynamic port range now ---"
Log (netsh int ipv4 show dynamicport tcp 2>&1 | Out-String)

Log ""
Log "--- STEP 4: bind test on 127.0.0.1:$port (pure PowerShell, no python) ---"
try {
    $listener = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Loopback, $port)
    $listener.Start()
    $listener.Stop()
    Log "BIND OK - port $port is FREE"
} catch {
    $msg = if ($_.Exception.InnerException) { $_.Exception.InnerException.Message } else { $_.Exception.Message }
    Log ("BIND STILL FAILS -> " + $msg)
    Log "TIP: you can also move Tlamatini to another port - set 'django_port' in config.json (next to Tlamatini.exe) and restart."
}

Log "=== DONE - you can close this window ==="
Write-Host ""
Write-Host "Result saved. This window will stay open so you can read it." -ForegroundColor Green