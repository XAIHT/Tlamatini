$ErrorActionPreference = 'Continue'
$out = 'C:\Users\angel\AppData\Local\Temp\claude\C--Development-Tlamatini\9eac967b-9b4e-4a5e-9a2f-af89acb43f84\scratchpad\portfix_result.txt'
if (Test-Path $out) { Remove-Item $out -Force }

function Log($m) { $m | Tee-Object -FilePath $out -Append | Out-Null; Write-Host $m }

Log "=== Tlamatini port-8000 fix @ $(Get-Date) ==="
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
Log "--- STEP 3: verify excluded ranges no longer cover 8000 ---"
Log (netsh interface ipv4 show excludedportrange protocol=tcp 2>&1 | Out-String)
Log "--- dynamic port range now ---"
Log (netsh int ipv4 show dynamicport tcp 2>&1 | Out-String)

Log ""
Log "--- STEP 4: bind test on 127.0.0.1:8000 (pure PowerShell, no python) ---"
try {
    $listener = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Loopback, 8000)
    $listener.Start()
    $listener.Stop()
    Log "BIND OK - port 8000 is FREE"
} catch {
    $msg = if ($_.Exception.InnerException) { $_.Exception.InnerException.Message } else { $_.Exception.Message }
    Log ("BIND STILL FAILS -> " + $msg)
}

Log "=== DONE - you can close this window ==="
Write-Host ""
Write-Host "Result saved. This window will stay open so you can read it." -ForegroundColor Green