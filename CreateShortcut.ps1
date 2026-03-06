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
$ps1Path = Join-Path $installDir "Tlamatini.ps1"
$iconPath = Join-Path $installDir "Tlamatini.ico"

Write-Host "Install directory: $installDir" -ForegroundColor White

# Validate Tlamatini.ps1
if (-not (Test-Path $ps1Path)) {
    Write-Host "Error: Tlamatini.ps1 not found at: $ps1Path" -ForegroundColor Red
    Read-Host "Press Enter to exit"
    exit 1
}
Write-Host "[OK] Tlamatini.ps1 found: $ps1Path" -ForegroundColor Green

# Check icon
if (Test-Path $iconPath) {
    Write-Host "[OK] Icon found: $iconPath" -ForegroundColor Green
} else {
    Write-Host "[!] Warning: Tlamatini.ico not found at $iconPath" -ForegroundColor Yellow
    Write-Host "    Shortcuts will use default PowerShell icon." -ForegroundColor Yellow
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
strPowerShellScript = objFSO.BuildPath(strInstallDir, "Tlamatini.ps1")
strIconPath = objFSO.BuildPath(strInstallDir, "Tlamatini.ico")

' Function to create shortcut
Sub CreateShortcut(shortcutPath)
    Set objShortcut = objShell.CreateShortcut(shortcutPath)
    objShortcut.TargetPath = "powershell.exe"
    objShortcut.Arguments = "-ExecutionPolicy Bypass -NoProfile -File """ & strPowerShellScript & """"
    objShortcut.WorkingDirectory = strInstallDir
    objShortcut.Description = "Tlamatini Development Server"
    objShortcut.WindowStyle = 1

    ' Set icon if it exists
    If objFSO.FileExists(strIconPath) Then
        objShortcut.IconLocation = strIconPath & ",0"
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
