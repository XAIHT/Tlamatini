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

# Validate Tlamatini.exe — the shortcut now targets the executable directly
# (instead of going through powershell.exe + Tlamatini.ps1) so the running
# console window picks up the .exe's embedded icon. Windows Terminal does
# not honor a shortcut's IconLocation for its hosted tab, so the only way
# to brand the running window is to launch the iconned .exe itself.
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

' Resolve %SystemRoot% explicitly. WScript.Shell.ExpandEnvironmentStrings
' avoids depending on %WINDIR% being present in the spawning environment.
strConhostPath = objShell.ExpandEnvironmentStrings("%SystemRoot%\System32\conhost.exe")

' Function to create shortcut.
'
' Why conhost.exe is the TargetPath (and NOT powershell.exe or Tlamatini.exe):
'   - On Windows 11 24H2+ Microsoft made Windows Terminal the default
'     terminal application. WT does NOT honor a child .exe's embedded icon,
'     does NOT honor the shortcut's IconLocation for the hosted tab, and
'     does NOT honor SetConsoleIcon / WM_SETICON. So a shortcut targeting
'     Tlamatini.exe directly STILL shows the cmd ">_" icon when WT hosts.
'   - Explicitly invoking conhost.exe with Tlamatini.exe as its argument
'     forces the legacy Windows Console Host to own the window, REGARDLESS
'     of the user's "Default terminal application" setting. Conhost honors
'     embedded .exe icons, IconLocation, AND the SetConsoleTitle/WM_SETICON
'     calls Tlamatini's manage.py issues at startup.
'   - This is the only single-shortcut design that survives every Windows
'     11 default-terminal permutation we have observed.
Sub CreateShortcut(shortcutPath)
    Set objShortcut = objShell.CreateShortcut(shortcutPath)
    objShortcut.TargetPath = strConhostPath
    objShortcut.Arguments = """" & strExePath & """"
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

# Execute the VBScript, passing the install directory as argument
try {
    $output = & cscript.exe //NoLogo $vbsPath "$installDir" 2>&1
    $output | ForEach-Object { Write-Host $_ -ForegroundColor Green }

    # Clean up the temporary VBS file
    Remove-Item $vbsPath -ErrorAction SilentlyContinue

    Write-Host ""
    Write-Host "You can now:" -ForegroundColor Cyan
    Write-Host "  1. Double-click the shortcut on your desktop" -ForegroundColor White
    Write-Host "  2. Double-click 'Tlamatini.lnk' in $installDir" -ForegroundColor White
    Write-Host "  3. Pin the shortcut to the taskbar or Start menu" -ForegroundColor White

} catch {
    Write-Host "Error creating shortcuts: $_" -ForegroundColor Red
    Write-Host ""
    Write-Host "Please check that the installation directory is writable." -ForegroundColor Yellow
}
