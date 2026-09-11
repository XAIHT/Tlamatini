# ═══════════════════════════════════════════════════════════════════
#   ✦  T L A M A T I N I  ✦   —   "one who knows"
#   Created by  Angela López Mendoza   ·   @angelahack1
# ═══════════════════════════════════════════════════════════════════
#   Tlamatini Author Banner — do not remove
#
# ONE COMMAND, ONE VISIBLE WINDOW, ONE REPORT.
#
#     powershell -ExecutionPolicy Bypass -File Tests\run_presence_tests.ps1
#
# The avatar presence regression is ALWAYS visible — headed Chrome on Angela's
# real desktop, photographed by Shoter. There is no headless switch, by design
# and by her standing rule of 2026-07-07.
#
# ⚠️ IT NEVER TOUCHES THE REAL DATABASE OR THE PORT-8000 APP.
#   It delegates to `Tests\run_avatar_tests.py --presence-only`, which stands up
#   an ISOLATED Django on port 8001 with its own fixture database and a
#   user/changeme login. That is the same isolated server the existing avatar
#   test already uses, so there is exactly one way this repository serves a
#   test app — not two that can drift.

$ErrorActionPreference = 'Stop'
$Root   = Split-Path -Parent $PSScriptRoot
$Runner = Join-Path $PSScriptRoot 'run_avatar_tests.py'
$Report = Join-Path $Root 'Temp\avatar_presence\SUMMARY.html'
$Log    = Join-Path $Root 'Temp\avatar_presence\run.log'

Write-Host ''
Write-Host '  TLAMATINI - AVATAR PRESENCE REGRESSION' -ForegroundColor Cyan
Write-Host '  Visible by design. Never headless. Isolated database.' -ForegroundColor DarkCyan
Write-Host ''

# ── interpreter: prefer the project's carried Python, then whatever has both
#    Django (to stand the server up) and Playwright (to drive the browser).
$candidates = @(
    (Join-Path $Root 'python\python.exe'),
    (Join-Path $Root 'venv\Scripts\python.exe'),
    'python',
    'py'
)
$py = $null
foreach ($c in $candidates) {
    try {
        $probe = & $c -c "import django, playwright, sys; sys.stdout.write('ok')" 2>$null
        if ($probe -eq 'ok') { $py = $c; break }
    } catch { continue }
}
if (-not $py) {
    Write-Host '  No interpreter here has BOTH Django and Playwright.' -ForegroundColor Red
    Write-Host '  Install Playwright once, into the interpreter that already runs Tlamatini:' -ForegroundColor Yellow
    Write-Host '      python -m pip install playwright'
    Write-Host '      python -m playwright install chromium'
    exit 3
}
Write-Host "  Interpreter : $py" -ForegroundColor Green
Write-Host '  Server      : isolated Django on 127.0.0.1:8001 (fixture DB, user/changeme)' -ForegroundColor Green
Write-Host ''
Write-Host '  Chrome opens on your desktop with the GPU DISABLED - the same way it' -ForegroundColor Yellow
Write-Host '  will run on a machine with no graphics card. Watch her blink, speak,' -ForegroundColor Yellow
Write-Host '  resize, and survive a 6x CPU throttle. Shoter photographs each stage.' -ForegroundColor Yellow
Write-Host ''

New-Item -ItemType Directory -Force -Path (Split-Path $Log) | Out-Null
& $py $Runner --presence-only 2>&1 | Tee-Object -FilePath $Log
$code = $LASTEXITCODE

Write-Host ''
if ($code -eq 0) {
    Write-Host '  ALL CHECKS PASSED.' -ForegroundColor Green
} else {
    Write-Host "  FAILURES (exit $code)." -ForegroundColor Red
}
Write-Host "  Report : $Report" -ForegroundColor Cyan
Write-Host "  Log    : $Log" -ForegroundColor DarkCyan
Write-Host ''
exit $code
