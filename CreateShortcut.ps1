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
$conhostPath = Join-Path $env:SystemRoot "System32\conhost.exe"

Write-Host "Install directory: $installDir" -ForegroundColor White

# Two launch strategies:
#   * conhost.exe wrapper -- the shortcut target is conhost.exe and the
#     argument is Tlamatini.exe.  Forces the legacy Console Host to own the
#     window even when Windows Terminal is the default host, so WM_SETICON
#     and the embedded .exe icon take effect on the title bar.
#   * Direct Tlamatini.exe -- the shortcut targets the .exe straight.  Works
#     on machines with restrictive Group Policy / AppLocker / WDAC where
#     conhost.exe is allowed to run but is silently prevented from launching
#     arbitrary child executables, which made earlier "always wrap" versions
#     produce shortcuts that did nothing when clicked.
# We probe end-to-end at install time and pick the right one for THIS host.
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

function Test-ConhostWrapperUsable {
    # Returns $true only when `conhost.exe <child.exe>` can actually launch
    # its child end-to-end.  On AppLocker / WDAC / restrictive-Group-Policy
    # machines the conhost binary itself is allowed (it's system-essential)
    # but the parent->child launch is silently blocked, which is the exact
    # failure mode that made the unconditional wrapper produce dead
    # shortcuts.  We exercise the same chain with a benign, fast,
    # always-available probe: cmd.exe /c exit 0.
    if (-not (Test-Path $conhostPath)) {
        Write-Host "[probe] conhost.exe not found; using direct exe target." -ForegroundColor Gray
        return $false
    }
    try {
        $proc = Start-Process -FilePath $conhostPath `
            -ArgumentList @('cmd.exe', '/c', 'exit 0') `
            -PassThru -WindowStyle Hidden -ErrorAction Stop
        $exited = $proc.WaitForExit(5000)
        if (-not $exited) {
            try { $proc.Kill() } catch {}
            Write-Host "[probe] conhost.exe wrapper probe timed out; treating host as restricted." -ForegroundColor Gray
            return $false
        }
        if ($proc.ExitCode -eq 0) {
            return $true
        }
        Write-Host "[probe] conhost.exe wrapper probe exited with code $($proc.ExitCode); treating host as restricted." -ForegroundColor Gray
        return $false
    } catch {
        Write-Host "[probe] conhost.exe wrapper probe threw: $_" -ForegroundColor Gray
        return $false
    }
}

$useConhost = Test-ConhostWrapperUsable
if ($useConhost) {
    Write-Host "[OK] conhost.exe wrapper is usable -- shortcut will force legacy console host (icon shows correctly under Windows Terminal default)." -ForegroundColor Green
} else {
    Write-Host "[!] conhost.exe wrapper is NOT usable on this machine -- shortcut will target Tlamatini.exe directly." -ForegroundColor Yellow
    Write-Host "    Title bar will read 'Tlamatini' but the running-window icon may show the host's default glyph." -ForegroundColor Yellow
}
$useConhostFlag = if ($useConhost) { '1' } else { '0' }

Write-Host ""
Write-Host "Creating shortcuts using VBScript helper..." -ForegroundColor White
Write-Host ""

# Create a temporary VBScript to create the shortcut
# Pass installDir as a command-line argument to the VBScript
$vbsScript = @"
Set objShell = CreateObject("WScript.Shell")
Set objFSO = CreateObject("Scripting.FileSystemObject")

' Args: 0 = install directory, 1 = useConhost flag ("1" or "0")
If WScript.Arguments.Count < 2 Then
    WScript.Echo "Error: install directory and useConhost flag arguments required."
    WScript.Quit 1
End If

strInstallDir = WScript.Arguments(0)
bUseConhost = (WScript.Arguments(1) = "1")
strExePath = objFSO.BuildPath(strInstallDir, "Tlamatini.exe")
strIconPath = objFSO.BuildPath(strInstallDir, "Tlamatini.ico")
strConhostPath = objShell.ExpandEnvironmentStrings("%SystemRoot%\System32\conhost.exe")

' Two strategies, decided by the PowerShell-side probe:
'   bUseConhost = True  -> wrap with conhost.exe so the running-window icon
'                          is the .exe's embedded Tlamatini icon under any
'                          terminal host (Windows Terminal ignores
'                          WM_SETICON, so the wrapper is the only way).
'   bUseConhost = False -> target Tlamatini.exe directly; required on
'                          AppLocker / WDAC / restrictive-policy machines
'                          where the wrapper produces dead shortcuts.

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
    ' This is independent of TargetPath -- it controls the .lnk's icon in
    ' Explorer/Desktop, not the running console-window icon.
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

# Try VBScript first, fall back to pure PowerShell COM if cscript is blocked
$vbsSuccess = $false
try {
    $output = & cscript.exe //NoLogo $vbsPath "$installDir" "$useConhostFlag" 2>&1
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
            if ($script:useConhost) {
                $sc.TargetPath = $script:conhostPath
                $sc.Arguments = "`"$script:exePath`""
            } else {
                $sc.TargetPath = $script:exePath
                $sc.Arguments = ""
            }
            $sc.WorkingDirectory = $script:installDir
            $sc.Description = "Tlamatini Development Server"
            $sc.WindowStyle = 1
            if (Test-Path $script:iconPath) {
                $sc.IconLocation = "$script:iconPath,0"
            } else {
                $sc.IconLocation = "$script:exePath,0"
            }
            $sc.Save()
            $tag = if ($script:useConhost) { "via conhost" } else { "direct exe" }
            Write-Host "[OK] Created ($tag): $lnkPath" -ForegroundColor Green
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
