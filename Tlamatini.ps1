# Tlamatini PowerShell Script
# Executes the Django development server with --noreload flag
# and automatically opens the browser to http://localhost:8000/
# Accepts an optional .flw file path as argument (e.g. from file association)

param(
    [string]$FlowFile
)

Write-Host "Starting Tlamatini Development Server..." -ForegroundColor Cyan
Write-Host "===========================================" -ForegroundColor Cyan
Write-Host ""

# Resolve paths relative to this script's directory
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$TlamatiniExe = Join-Path $scriptDir "Tlamatini.exe"

# Set working directory to the script's directory (critical for PyInstaller builds)
Set-Location $scriptDir
Write-Host "Working directory: $scriptDir" -ForegroundColor Gray

# Check if Tlamatini.exe exists
if (-not (Test-Path $TlamatiniExe)) {
    Write-Host "Error: Tlamatini.exe not found!" -ForegroundColor Red
    Write-Host "Expected location: $TlamatiniExe" -ForegroundColor Yellow
    Read-Host "Press Enter to exit"
    exit 1
}

# Build argument list depending on whether a .flw file was passed
# When a .flw file is given, pass ONLY the file path to Tlamatini.exe
# (manage.py detects the .flw and internally rewrites argv to runserver --noreload)
# When no .flw file is given, pass runserver --noreload explicitly.
if ($FlowFile) {
    if (-not (Test-Path $FlowFile)) {
        Write-Host "Warning: Flow file not found: $FlowFile" -ForegroundColor Yellow
    } else {
        $FlowFile = (Resolve-Path $FlowFile).Path
    }
    Write-Host "Opening flow file: $FlowFile" -ForegroundColor Magenta
    $serverArgs = @($FlowFile)
} else {
    $serverArgs = @('runserver', '--noreload')
}

Write-Host "Executing: Tlamatini.exe $($serverArgs -join ' ')" -ForegroundColor Green
Write-Host ""

Write-Host "Server starting..." -ForegroundColor Cyan
Write-Host "Press Ctrl+C to stop the server." -ForegroundColor Cyan
Write-Host ""

# Open browser in background 10 seconds after the server starts
$browserUrl = "http://localhost:8000/"
Write-Host "Browser will open at $browserUrl in 10 seconds..." -ForegroundColor Yellow
Start-Process powershell.exe -ArgumentList "-NoProfile -WindowStyle Hidden -Command `"Start-Sleep -Seconds 10; Start-Process '$browserUrl'`"" -WindowStyle Hidden

# Run Tlamatini.exe directly so all output and errors are visible in this console
& $TlamatiniExe $serverArgs

# If we get here, the process has exited
Write-Host ""
Write-Host "Tlamatini.exe has exited (code: $LASTEXITCODE)." -ForegroundColor Red
Read-Host "Press Enter to close this window"
