# Shortcut Creator for Tlamatini
# Reads the installation directory from CreateShortcut.json

param(
    [switch]$DesktopOnly,
    [switch]$LocalOnly
)

$scriptDir = $PSScriptRoot
$configPath = Join-Path $scriptDir "CreateShortcut.json"

Write-Host "Tlamatini Shortcut Creator" -ForegroundColor Cyan
Write-Host "============================" -ForegroundColor Cyan
Write-Host ""

# Read install directory from CreateShortcut.json
if (-not (Test-Path $configPath)) {
    Write-Host "Error: CreateShortcut.json not found at: $configPath" -ForegroundColor Red
    Write-Host "Please create it with content like:" -ForegroundColor Yellow
    Write-Host '  { "InstallDir": "D:\\Tlamatini" }' -ForegroundColor Yellow
    Read-Host "Press Enter to exit"
    exit 1
}

try {
    $config = Get-Content $configPath -Raw | ConvertFrom-Json
} catch {
    Write-Host "Error: Failed to parse CreateShortcut.json: $_" -ForegroundColor Red
    Read-Host "Press Enter to exit"
    exit 1
}

if (-not $config.InstallDir) {
    Write-Host 'Error: "InstallDir" key not found in CreateShortcut.json' -ForegroundColor Red
    Read-Host "Press Enter to exit"
    exit 1
}

$installDir = $config.InstallDir

if (-not (Test-Path $installDir)) {
    Write-Host "Error: Installation directory not found: $installDir" -ForegroundColor Red
    Read-Host "Press Enter to exit"
    exit 1
}

$installDir = (Resolve-Path $installDir).Path
$exePath = Join-Path $installDir "Tlamatini.exe"
$iconPath = Join-Path $installDir "Tlamatini.ico"

Write-Host "Install directory: $installDir" -ForegroundColor White

# Validate Tlamatini.exe -- the shortcut targets Tlamatini.exe directly.
# manage.py handles console branding (title + icon) via _brand_console_window()
# and _set_app_user_model_id() on startup, so no conhost.exe wrapper is needed.
# Previous versions used conhost.exe as the shortcut target to force the legacy
# Console Host, but conhost.exe does not reliably accept arbitrary executables
# as arguments on modern Windows -- especially under restrictive Group Policy /
# AppLocker / WDAC configurations -- causing the shortcut to silently do nothing.
if (-not (Test-Path $exePath)) {
    Write-Host "Error: Tlamatini.exe not found at: $exePath" -ForegroundColor Red
    Read-Host "Press Enter to exit"
    exit 1
}
Write-Host "[OK] Tlamatini.exe found: $exePath" -ForegroundColor Green

# Check icon
if (Test-Path $iconPath) {
    Write-Host "[OK] Icon found: $iconPath" -ForegroundColor Green
} else {
    Write-Host "[!] Warning: Tlamatini.ico not found at $iconPath" -ForegroundColor Yellow
    Write-Host "    Shortcut will fall back to the .exe's embedded icon." -ForegroundColor Yellow
}

Write-Host ""
Write-Host "Creating shortcuts using VBScript helper..." -ForegroundColor White
Write-Host ""

# Create a temporary VBScript to create the shortcut
# Pass installDir as a command-line argument to the VBScript
$vbsScript = @"
Set objShell = CreateObject("WScript.Shell")
Set objFSO = CreateObject("Scripting.FileSystemObject")

' Read install directory from command-line argument
If WScript.Arguments.Count < 1 Then
    WScript.Echo "Error: install directory argument required."
    WScript.Quit 1
End If

strInstallDir = WScript.Arguments(0)
strExePath = objFSO.BuildPath(strInstallDir, "Tlamatini.exe")
strIconPath = objFSO.BuildPath(strInstallDir, "Tlamatini.ico")

' Target Tlamatini.exe directly.  manage.py brands the console window
' (title + icon) via _brand_console_window() and _set_app_user_model_id()
' on startup, so no conhost.exe wrapper is needed.  Previous versions
' wrapped via conhost.exe but that fails silently on machines with
' restrictive Group Policy / AppLocker / WDAC.

Sub CreateShortcut(shortcutPath)
    Set objShortcut = objShell.CreateShortcut(shortcutPath)

    objShortcut.TargetPath = strExePath
    objShortcut.Arguments = ""
    objShortcut.WorkingDirectory = strInstallDir
    objShortcut.Description = "Tlamatini Development Server"
    objShortcut.WindowStyle = 1

    ' Set icon: prefer the standalone .ico (sharper at all sizes for the
    ' .lnk file in Explorer/Desktop); fall back to the .exe's embedded icon.
    If objFSO.FileExists(strIconPath) Then
        objShortcut.IconLocation = strIconPath & ",0"
    Else
        objShortcut.IconLocation = strExePath & ",0"
    End If

    objShortcut.Save
    WScript.Echo "[OK] Created: " & shortcutPath
End Sub

' Create desktop shortcut
strDesktop = objShell.SpecialFolders("Desktop")
Call CreateShortcut(objFSO.BuildPath(strDesktop, "Tlamatini.lnk"))

' Create local shortcut in install directory
Call CreateShortcut(objFSO.BuildPath(strInstallDir, "Tlamatini.lnk"))

WScript.Echo ""
WScript.Echo "Shortcuts created successfully!"
"@

# Save the VBScript to a temporary file
$vbsPath = Join-Path $scriptDir "CreateShortcut_Temp.vbs"
$vbsScript | Out-File -FilePath $vbsPath -Encoding ASCII

# Try VBScript first, fall back to pure PowerShell COM if cscript is blocked
$vbsSuccess = $false
try {
    $output = & cscript.exe //NoLogo $vbsPath "$installDir" 2>&1
    if ($LASTEXITCODE -eq 0) {
        $output | ForEach-Object { Write-Host $_ -ForegroundColor Green }
        $vbsSuccess = $true
    }
} catch {
    Write-Host "[!] cscript.exe failed or is blocked by policy -- using PowerShell fallback." -ForegroundColor Yellow
}

# Clean up the temporary VBS file regardless
Remove-Item $vbsPath -ErrorAction SilentlyContinue

# PowerShell COM fallback -- works even when cscript/wscript are blocked by
# AppLocker / WDAC / Group Policy, because WScript.Shell COM is still
# accessible from PowerShell running under -ExecutionPolicy Bypass.
if (-not $vbsSuccess) {
    Write-Host "Creating shortcuts via PowerShell COM fallback..." -ForegroundColor White
    try {
        $shell = New-Object -ComObject WScript.Shell

        function New-TlamatiniShortcut($lnkPath) {
            $sc = $shell.CreateShortcut($lnkPath)
            $sc.TargetPath = $exePath
            $sc.Arguments = ""
            $sc.WorkingDirectory = $installDir
            $sc.Description = "Tlamatini Development Server"
            $sc.WindowStyle = 1
            if (Test-Path $iconPath) {
                $sc.IconLocation = "$iconPath,0"
            } else {
                $sc.IconLocation = "$exePath,0"
            }
            $sc.Save()
            Write-Host "[OK] Created: $lnkPath" -ForegroundColor Green
        }

        # Desktop shortcut
        $desktopPath = [Environment]::GetFolderPath("Desktop")
        New-TlamatiniShortcut (Join-Path $desktopPath "Tlamatini.lnk")

        # Local shortcut in install directory
        New-TlamatiniShortcut (Join-Path $installDir "Tlamatini.lnk")

        Write-Host ""
        Write-Host "Shortcuts created successfully!" -ForegroundColor Green
    } catch {
        Write-Host "Error creating shortcuts via PowerShell: $_" -ForegroundColor Red
    }
}

Write-Host ""
Write-Host "You can now:" -ForegroundColor Cyan
Write-Host "  1. Double-click the shortcut on your desktop" -ForegroundColor White
Write-Host "  2. Double-click 'Tlamatini.lnk' in $installDir" -ForegroundColor White
Write-Host "  3. Pin the shortcut to the taskbar or Start menu" -ForegroundColor White
