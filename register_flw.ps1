#Requires -Version 5.1
<#
.SYNOPSIS
    Registers the .flw file extension to open with Tlamatini via Tlamatini.ps1.

.DESCRIPTION
    Reads the installation directory from CreateShortcut.json and creates
    Windows Shell file association entries under HKCU (no admin required)
    so that double-clicking a .flw file launches Tlamatini.ps1 (which in turn
    starts Tlamatini.exe properly). The icon is set to Tlamatini.ico.

.EXAMPLE
    .\register_flw.ps1
#>

# Read install directory from CreateShortcut.json
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$configPath = Join-Path $scriptDir "CreateShortcut.json"

if (-not (Test-Path $configPath)) {
    Write-Error "CreateShortcut.json not found at: $configPath"
    exit 1
}

try {
    $config = Get-Content $configPath -Raw | ConvertFrom-Json
}
catch {
    Write-Error ("Failed to parse CreateShortcut.json: " + $_.Exception.Message)
    exit 1
}

if (-not $config.InstallDir) {
    Write-Error '"InstallDir" key not found in CreateShortcut.json'
    exit 1
}

$installDir = $config.InstallDir

if (-not (Test-Path $installDir)) {
    Write-Error "Installation directory not found: $installDir"
    exit 1
}

$installDir = (Resolve-Path $installDir).Path
$ps1Path = Join-Path $installDir "Tlamatini.ps1"
$icoPath = Join-Path $installDir "Tlamatini.ico"

# Validate required files
if (-not (Test-Path $ps1Path)) {
    Write-Error "Tlamatini.ps1 not found at: $ps1Path"
    exit 1
}

if (-not (Test-Path $icoPath)) {
    Write-Warning "Tlamatini.ico not found at $icoPath - icon will not be set."
}

$ps1Path = (Resolve-Path $ps1Path).Path
if (Test-Path $icoPath) {
    $icoPath = (Resolve-Path $icoPath).Path
}

# --- Registry Keys ---
$progId = "Tlamatini.FlowFile"
$friendlyName = "Tlamatini Flow File"
$extKey = "HKCU:\Software\Classes\.flw"
$progIdKey = "HKCU:\Software\Classes\$progId"
$explorerExtKey = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Explorer\FileExts\.flw"

# Known stale ProgIds from before the app was renamed
$staleProgIds = @("SystemAgent.FlowFile")

# SHChangeNotify C# interop code (may fail in Constrained Language Mode)
$csharpCode = 'using System; using System.Runtime.InteropServices; public class ShellNotify { [DllImport("shell32.dll", CharSet = CharSet.Auto, SetLastError = true)] public static extern void SHChangeNotify(int wEventId, int uFlags, IntPtr dwItem1, IntPtr dwItem2); }'

# ============================================================
# PHASE 1: UNREGISTER — Remove all existing .flw associations
# ============================================================
Write-Host "Unregistering existing .flw file associations..." -ForegroundColor Yellow

# 1a. Remove the .flw extension key and all subkeys (OpenWithProgids, etc.)
if (Test-Path $extKey) {
    Remove-Item -Path $extKey -Recurse -Force -ErrorAction SilentlyContinue
    Write-Host "  [OK] Removed $extKey" -ForegroundColor Green
} else {
    Write-Host "  [--] $extKey not present" -ForegroundColor DarkGray
}

# 1b. Remove the current Tlamatini.FlowFile ProgId and all subkeys
if (Test-Path $progIdKey) {
    Remove-Item -Path $progIdKey -Recurse -Force -ErrorAction SilentlyContinue
    Write-Host "  [OK] Removed $progIdKey" -ForegroundColor Green
} else {
    Write-Host "  [--] $progIdKey not present" -ForegroundColor DarkGray
}

# 1c. Remove any stale ProgIds from previous app names
foreach ($stale in $staleProgIds) {
    $staleKey = "HKCU:\Software\Classes\$stale"
    if (Test-Path $staleKey) {
        Remove-Item -Path $staleKey -Recurse -Force -ErrorAction SilentlyContinue
        Write-Host "  [OK] Removed stale ProgId: $stale" -ForegroundColor Green
    }
}

# 1d. Remove Explorer's cached .flw state (UserChoice, OpenWithList, OpenWithProgids)
#     UserChoice holds the user's "always open with" selection and is hash-protected,
#     but the entire key tree can still be deleted by the owning user.
if (Test-Path $explorerExtKey) {
    # Remove UserChoice (the hash-protected "default app" selection)
    $userChoiceKey = "$explorerExtKey\UserChoice"
    if (Test-Path $userChoiceKey) {
        Remove-Item -Path $userChoiceKey -Force -ErrorAction SilentlyContinue
        Write-Host "  [OK] Removed Explorer UserChoice for .flw" -ForegroundColor Green
    }
    # Remove OpenWithList (cached MRU list — e.g. msedge.exe)
    $owlKey = "$explorerExtKey\OpenWithList"
    if (Test-Path $owlKey) {
        Remove-Item -Path $owlKey -Recurse -Force -ErrorAction SilentlyContinue
        Write-Host "  [OK] Removed Explorer OpenWithList for .flw" -ForegroundColor Green
    }
    # Remove OpenWithProgids
    $feOwpKey = "$explorerExtKey\OpenWithProgids"
    if (Test-Path $feOwpKey) {
        Remove-Item -Path $feOwpKey -Recurse -Force -ErrorAction SilentlyContinue
        Write-Host "  [OK] Removed Explorer OpenWithProgids for .flw" -ForegroundColor Green
    }
} else {
    Write-Host "  [--] $explorerExtKey not present" -ForegroundColor DarkGray
}

Write-Host "  Unregistration complete." -ForegroundColor Yellow
Write-Host ""

# ============================================================
# PHASE 2: REGISTER — Create fresh .flw associations
# ============================================================
Write-Host "Registering .flw file association..." -ForegroundColor Cyan
Write-Host "  InstallDir: $installDir" -ForegroundColor Cyan
Write-Host "  Script:     $ps1Path" -ForegroundColor Cyan
Write-Host "  Icon:       $icoPath" -ForegroundColor Cyan

try {
    # 2a. Create .flw extension mapping -> Tlamatini.FlowFile
    New-Item -Path $extKey -Force | Out-Null
    Set-ItemProperty -Path $extKey -Name "(Default)" -Value $progId
    Write-Host "  [OK] Created $extKey -> $progId" -ForegroundColor Green

    # 2b. Create OpenWithProgids under .flw (required by Windows 10/11)
    $owpKey = "$extKey\OpenWithProgids"
    New-Item -Path $owpKey -Force | Out-Null
    New-ItemProperty -Path $owpKey -Name $progId -PropertyType None -Value ([byte[]]@()) -Force | Out-Null
    Write-Host "  [OK] Created OpenWithProgids -> $progId" -ForegroundColor Green

    # 2c. Create ProgID with friendly name
    New-Item -Path $progIdKey -Force | Out-Null
    Set-ItemProperty -Path $progIdKey -Name "(Default)" -Value $friendlyName
    Write-Host "  [OK] Created $progIdKey -> $friendlyName" -ForegroundColor Green

    # 2d. Set default icon to Tlamatini.ico
    $iconKey = "$progIdKey\DefaultIcon"
    New-Item -Path $iconKey -Force | Out-Null
    if (Test-Path $icoPath) {
        Set-ItemProperty -Path $iconKey -Name "(Default)" -Value "`"$icoPath`",0"
        Write-Host "  [OK] Set DefaultIcon -> $icoPath,0" -ForegroundColor Green
    }

    # 2e. Set open command: launch via cmd.exe /k -> powershell -> Tlamatini.ps1
    $commandKey = "$progIdKey\shell\open\command"
    New-Item -Path $commandKey -Force | Out-Null
    $openCmd = "cmd.exe /k powershell.exe -ExecutionPolicy Bypass -NoProfile -File `"$ps1Path`" -FlowFile `"%1`""
    Set-ItemProperty -Path $commandKey -Name "(Default)" -Value $openCmd
    Write-Host "  [OK] Set open command -> $openCmd" -ForegroundColor Green

    # 2f. Set Explorer's OpenWithProgids for .flw
    $feOwpKey2 = "$explorerExtKey\OpenWithProgids"
    New-Item -Path $feOwpKey2 -Force | Out-Null
    New-ItemProperty -Path $feOwpKey2 -Name $progId -PropertyType None -Value ([byte[]]@()) -Force | Out-Null
    Write-Host "  [OK] Set Explorer OpenWithProgids -> $progId" -ForegroundColor Green

    # 2g. Notify Windows Shell of the change
    try {
        Add-Type -TypeDefinition $csharpCode -ErrorAction Stop
        [ShellNotify]::SHChangeNotify(0x08000000, 0x0000, [IntPtr]::Zero, [IntPtr]::Zero)
        Write-Host "  [OK] Notified Windows Shell (SHChangeNotify)" -ForegroundColor Green
    }
    catch {
        # Fallback: Constrained Language Mode blocks Add-Type.
        Write-Host "  [WARN] Add-Type unavailable (Constrained Language Mode) - using fallback" -ForegroundColor Yellow
        & rundll32.exe user32.dll, UpdatePerUserSystemParameters 2>$null
        Write-Host "  [OK] Notified shell via rundll32 fallback" -ForegroundColor Green
    }

    # 2h. Force icon cache rebuild (no admin required)
    Write-Host "  Rebuilding Windows icon cache..." -ForegroundColor Cyan
    try {
        & ie4uinit.exe -ClearIconCache 2>$null
        & ie4uinit.exe -show 2>$null
        $iconCacheDb = Join-Path $env:LOCALAPPDATA "IconCache.db"
        if (Test-Path $iconCacheDb) { Remove-Item $iconCacheDb -Force -ErrorAction SilentlyContinue }
    }
    catch {
        Write-Host "  [INFO] Could not rebuild icon cache - you may need to log off/on to see icon changes" -ForegroundColor Yellow
    }

    Write-Host ""
    Write-Host "SUCCESS: .flw files are now associated with Tlamatini!" -ForegroundColor Green
    Write-Host "Double-clicking a .flw file will launch Tlamatini.ps1 (not Tlamatini.exe directly)." -ForegroundColor Cyan

}
catch {
    Write-Error ("Failed to register file association: " + $_.Exception.Message)
    exit 1
}
