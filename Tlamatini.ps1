# Tlamatini PowerShell Script
# Executes the Django development server with --noreload flag
# and automatically opens the browser on the configured web port
# Accepts an optional .flw or .fpmt file path as argument (e.g. from file association)

param(
    [string]$FlowFile
)

Write-Host "Starting Tlamatini Development Server..." -ForegroundColor Cyan
Write-Host "===========================================" -ForegroundColor Cyan
Write-Host ""

# Resolve paths relative to this script's directory
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$TlamatiniExe = Join-Path $scriptDir "Tlamatini.exe"

# Resolve an incoming relative path BEFORE changing the working directory.
if ($FlowFile) {
    if ([IO.Path]::GetExtension($FlowFile) -notin @('.flw', '.fpmt')) { throw 'Choose a .flw or .fpmt flow file.' }
    $FlowFile = (Resolve-Path -LiteralPath $FlowFile -ErrorAction Stop).Path
}

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

# Build argument list depending on whether a flow file was passed
# When a flow file is given, pass ONLY the file path to Tlamatini.exe
# (manage.py detects either flow format and internally rewrites argv to runserver --noreload)
# When no flow file is given, pass runserver --noreload explicitly.
if ($FlowFile) {
    if (-not (Test-Path $FlowFile)) {
        Write-Host "Warning: Flow file not found: $FlowFile" -ForegroundColor Yellow
    }
    else {
        $FlowFile = (Resolve-Path $FlowFile).Path
    }
    Write-Host "Opening flow file: $FlowFile" -ForegroundColor Magenta
    $serverArgs = @($FlowFile)
}
else {
    $serverArgs = @('runserver', '--noreload')
}

Write-Host "Executing: Tlamatini.exe $($serverArgs -join ' ')" -ForegroundColor Green
Write-Host ""

Write-Host "Server starting..." -ForegroundColor Cyan
Write-Host "Press Ctrl+C to stop the server." -ForegroundColor Cyan
Write-Host ""

# manage.py opens the correct editor once, using the configured web port.

# Run Tlamatini.exe directly so all output and errors are visible in this console
& $TlamatiniExe $serverArgs

# If we get here, the process has exited
Write-Host ""
Write-Host "Tlamatini.exe has exited (code: $LASTEXITCODE)." -ForegroundColor Red
Read-Host "Press Enter to close this window"
