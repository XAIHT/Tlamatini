# Stage the 2x2 test desktop for Angela.
# Runs INSIDE her session (launched by Tlamatini's Executer), so every window
# it opens is a real window on her real desktop.
param(
    [string]$Action = "clean"
)

$HARNESS = 'C:\Development\XAIHT\Tlamatini\.claude\skills\tlamatini-daily-chat-test\harness'
$SERVER  = 'C:\Development\XAIHT\Tlamatini\Tlamatini'
$LOG     = 'C:\Development\XAIHT\Tlamatini\Temp\gauge200.txt'

function Kill-Ours {
    $pat = 'window-test-screen|context_gauge_100|monitor\.py|manage\.py runserver'
    Get-CimInstance Win32_Process -Filter "Name='python.exe'" -ErrorAction SilentlyContinue |
        Where-Object { $_.CommandLine -and $_.CommandLine -match $pat } |
        ForEach-Object {
            Write-Output ("closing pid {0}" -f $_.ProcessId)
            Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
        }
    # ⚠️ NEVER kill a powershell by MainWindowTitle.
    # These shells are TABS of one Windows Terminal process, and a tab's
    # MainWindowTitle is the TERMINAL's title - whichever tab happens to be
    # active. Matching on it can kill the whole terminal, which takes the
    # server, the panel and the runner down together, silently, with no
    # traceback anywhere. That is exactly how the server "died" three times
    # on 2026-09-21 while its own log simply stopped mid-line.
    # Python processes are identified by their command line instead, which
    # names the script and can never be mistaken for a different window.
}

if ($Action -eq "clean") {
    Kill-Ours
    Write-Output "CLEAN DONE"
    exit 0
}

if ($Action -eq "wait") {
    # The login page is served at "/" (project urls: path('', login_view)).
    # Polling /agent/login/ returns 404 forever, which made a perfectly healthy
    # server look dead and wasted three minutes per attempt.
    $ok = $false
    for ($i = 0; $i -lt 90; $i++) {
        try {
            $r = Invoke-WebRequest -Uri 'http://127.0.0.1:8000/' -UseBasicParsing -TimeoutSec 3
            if ($r.StatusCode -eq 200) { $ok = $true; break }
        } catch { }
        Start-Sleep -Seconds 2
    }
    if ($ok) { Write-Output "SERVER READY" } else { Write-Output "SERVER NOT READY" }
    exit 0
}

if ($Action -eq "server") {
    Start-Process conhost.exe -ArgumentList 'powershell','-NoExit','-Command',
        ("`$host.UI.RawUI.WindowTitle='1 - TLAMATINI SERVER'; Set-Location '{0}'; python manage.py runserver --noreload 127.0.0.1:8000" -f $SERVER)
    Write-Output "SERVER WINDOW OPENED"
    exit 0
}

if ($Action -eq "panel") {
    Start-Process conhost.exe -ArgumentList 'powershell','-NoExit','-Command',
        ("`$host.UI.RawUI.WindowTitle='2 - WINDOW TEST SCREEN'; Set-Location '{0}'; python -u 'window-test-screen.py' --port 8791 --target-port 8000 --log '{1}\tlamatini.log' --total 200" -f $HARNESS, $SERVER)
    Write-Output "PANEL WINDOW OPENED"
    exit 0
}

if ($Action -eq "test") {
    Start-Process conhost.exe -ArgumentList 'powershell','-NoExit','-Command',
        ("`$host.UI.RawUI.WindowTitle='3 - TEST RUNNER 200 PROMPTS'; Set-Location '{0}'; `$env:TLAMATINI_BASE_URL='http://127.0.0.1:8000'; `$env:TLAMATINI_USER='user'; `$env:TLAMATINI_PASS='changeme'; `$env:GAUGE_PROMPTS='200'; `$env:GAUGE_ANSWER_TIMEOUT='150'; python -u context_gauge_100.py 2>&1 | Tee-Object -FilePath '{1}'" -f $HARNESS, $LOG)
    Write-Output "TEST WINDOW OPENED"
    exit 0
}

Write-Output ("unknown action: " + $Action)
exit 1
