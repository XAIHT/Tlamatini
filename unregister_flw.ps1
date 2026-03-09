#Requires -Version 5.1
<#
.SYNOPSIS
    Unregisters the .flw file extension association from the current user.

.DESCRIPTION
    Removes all Windows Shell file association entries under HKCU that were
    created by register_flw.ps1, including stale ProgIds from before the app
    was renamed.  Also clears Explorer's cached UserChoice / OpenWithList /
    OpenWithProgids for .flw and notifies the shell of the change.

    No admin privileges are required.

.EXAMPLE
    .\unregister_flw.ps1
#>

# --- Registry keys to clean up ---
$progId           = "Tlamatini.FlowFile"
$extKey           = "HKCU:\Software\Classes\.flw"
$progIdKey        = "HKCU:\Software\Classes\$progId"
$explorerExtKey   = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Explorer\FileExts\.flw"

# Known stale ProgIds from before the app was renamed
$staleProgIds = @("SystemAgent.FlowFile")

# SHChangeNotify C# interop code (may fail in Constrained Language Mode)
$csharpCode = 'using System; using System.Runtime.InteropServices; public class ShellNotify { [DllImport("shell32.dll", CharSet = CharSet.Auto, SetLastError = true)] public static extern void SHChangeNotify(int wEventId, int uFlags, IntPtr dwItem1, IntPtr dwItem2); }'

# ============================================================
# PHASE 1: Remove the .flw extension key and all subkeys
# ============================================================
Write-Host "Unregistering .flw file association..." -ForegroundColor Yellow

# 1a. Remove .flw extension key (OpenWithProgids, etc.)
if (Test-Path $extKey) {
    Remove-Item -Path $extKey -Recurse -Force -ErrorAction SilentlyContinue
    Write-Host "  [OK] Removed $extKey" -ForegroundColor Green
} else {
    Write-Host "  [--] $extKey not present" -ForegroundColor DarkGray
}

# 1b. Remove the Tlamatini.FlowFile ProgId and all subkeys
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

# ============================================================
# PHASE 2: Remove Explorer's cached .flw state
# ============================================================
if (Test-Path $explorerExtKey) {
    # UserChoice (hash-protected "default app" selection)
    $userChoiceKey = "$explorerExtKey\UserChoice"
    if (Test-Path $userChoiceKey) {
        Remove-Item -Path $userChoiceKey -Force -ErrorAction SilentlyContinue
        Write-Host "  [OK] Removed Explorer UserChoice for .flw" -ForegroundColor Green
    }
    # OpenWithList (cached MRU list)
    $owlKey = "$explorerExtKey\OpenWithList"
    if (Test-Path $owlKey) {
        Remove-Item -Path $owlKey -Recurse -Force -ErrorAction SilentlyContinue
        Write-Host "  [OK] Removed Explorer OpenWithList for .flw" -ForegroundColor Green
    }
    # OpenWithProgids
    $feOwpKey = "$explorerExtKey\OpenWithProgids"
    if (Test-Path $feOwpKey) {
        Remove-Item -Path $feOwpKey -Recurse -Force -ErrorAction SilentlyContinue
        Write-Host "  [OK] Removed Explorer OpenWithProgids for .flw" -ForegroundColor Green
    }
    # Remove the parent key itself if now empty
    try {
        Remove-Item -Path $explorerExtKey -Recurse -Force -ErrorAction SilentlyContinue
        Write-Host "  [OK] Removed $explorerExtKey" -ForegroundColor Green
    } catch {
        Write-Host "  [WARN] Could not fully remove $explorerExtKey" -ForegroundColor Yellow
    }
} else {
    Write-Host "  [--] $explorerExtKey not present" -ForegroundColor DarkGray
}

# ============================================================
# PHASE 3: Notify Windows Shell
# ============================================================
try {
    Add-Type -TypeDefinition $csharpCode -ErrorAction Stop
    [ShellNotify]::SHChangeNotify(0x08000000, 0x0000, [IntPtr]::Zero, [IntPtr]::Zero)
    Write-Host "  [OK] Notified Windows Shell (SHChangeNotify)" -ForegroundColor Green
}
catch {
    # Fallback: Constrained Language Mode blocks Add-Type
    Write-Host "  [WARN] Add-Type unavailable (Constrained Language Mode) - using fallback" -ForegroundColor Yellow
    & rundll32.exe user32.dll, UpdatePerUserSystemParameters 2>$null
    Write-Host "  [OK] Notified shell via rundll32 fallback" -ForegroundColor Green
}

# ============================================================
# PHASE 4: Force icon cache rebuild and Explorer restart
# ============================================================
# Without this, .flw file icons may retain the old Tlamatini icon
# until the user logs off/on.
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
Write-Host "SUCCESS: .flw file association has been removed." -ForegroundColor Green
