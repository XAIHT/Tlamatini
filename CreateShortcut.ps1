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

# Validate Tlamatini.exe — the shortcut launches via conhost.exe so the
# legacy Console Host owns the window (which honors WM_SETICON and the
# .exe's embedded icon for title bar, taskbar, and Alt-Tab). If conhost
# is unavailable the VBScript falls back to targeting Tlamatini.exe
# directly — the app still launches but the running-window icon may show
# the generic terminal glyph when Windows Terminal is the default host.
# manage.py pins the CWD to os.path.dirname(sys.executable) on startup,
# so all assets resolve relative to the .exe regardless of launch method.
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

' Resolve conhost.exe — the preferred TargetPath.  Launching via conhost
' forces the legacy Console Host to own the window even when Windows
' Terminal is the user's default terminal, which lets WM_SETICON, the
' embedded .exe icon, and the shortcut's IconLocation all take effect on
' the title bar, taskbar, and Alt-Tab.
'
' If conhost is not found (very unlikely, but possible on stripped-down
' images) the shortcut falls back to targeting Tlamatini.exe directly.
' The app still launches — manage.py pins the CWD and brands the window
' regardless — but the running-window icon may show the generic terminal
' glyph under WT.
strConhostPath = objShell.ExpandEnvironmentStrings("%SystemRoot%\System32\conhost.exe")
bUseConhost = objFSO.FileExists(strConhostPath)

Sub CreateShortcut(shortcutPath)
    Set objShortcut = objShell.CreateShortcut(shortcutPath)

    If bUseConhost Then
        objShortcut.TargetPath = strConhostPath
        objShortcut.Arguments = """" & strExePath & """"
    Else
        objShortcut.TargetPath = strExePath
        objShortcut.Arguments = ""
    End If

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
    If bUseConhost Then
        WScript.Echo "[OK] Created (via conhost): " & shortcutPath
    Else
        WScript.Echo "[OK] Created (direct exe):  " & shortcutPath
    End If
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
