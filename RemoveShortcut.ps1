# Shortcut Remover for Tlamatini
# Removes the desktop and local shortcuts created by CreateShortcut.ps1
# and forces Windows Explorer to refresh so the icons disappear immediately.

$scriptDir = $PSScriptRoot
$ErrorActionPreference = 'Stop'

# SHChangeNotify C# interop code (may fail in Constrained Language Mode)
$csharpCode = 'using System; using System.Runtime.InteropServices; public class ShellNotify { [DllImport("shell32.dll", CharSet = CharSet.Auto, SetLastError = true)] public static extern void SHChangeNotify(int wEventId, int uFlags, IntPtr dwItem1, IntPtr dwItem2); }'

Write-Host "Tlamatini Shortcut Remover" -ForegroundColor Cyan
Write-Host "============================" -ForegroundColor Cyan
Write-Host ""

# ── Remove desktop shortcut ──────────────────────────────────────────────────
$desktopPath = [Environment]::GetFolderPath("Desktop")
$desktopShortcut = Join-Path $desktopPath "Tlamatini.lnk"

if (Test-Path $desktopShortcut) {
    $shell = New-Object -ComObject WScript.Shell
    $shortcut = $shell.CreateShortcut($desktopShortcut)
    $owned = $shortcut.WorkingDirectory.TrimEnd('\') -ieq $scriptDir.TrimEnd('\')
    if ($owned) {
        Remove-Item -LiteralPath $desktopShortcut -Force -ErrorAction Stop
        Write-Host "[OK] Removed desktop shortcut: $desktopShortcut" -ForegroundColor Green
    } else {
        Write-Host '[--] Kept desktop shortcut belonging to another installation.'
    }
} else {
    Write-Host "[--] Desktop shortcut not found: $desktopShortcut" -ForegroundColor DarkGray
}

# ── Remove local shortcut in the install directory ───────────────────────────
$localShortcut = Join-Path $scriptDir "Tlamatini.lnk"

if (Test-Path $localShortcut) {
        Remove-Item -LiteralPath $localShortcut -Force -ErrorAction Stop
        Write-Host "[OK] Removed local shortcut: $localShortcut" -ForegroundColor Green
} else {
    Write-Host "[--] Local shortcut not found: $localShortcut" -ForegroundColor DarkGray
}

# ── Notify Windows Shell of the change ───────────────────────────────────────
Write-Host ""
Write-Host "Refreshing Windows Shell..." -ForegroundColor Cyan

try {
    Add-Type -TypeDefinition $csharpCode -ErrorAction Stop
    [ShellNotify]::SHChangeNotify(0x08000000, 0x0000, [IntPtr]::Zero, [IntPtr]::Zero)
    Write-Host "  [OK] Notified Windows Shell (SHChangeNotify)" -ForegroundColor Green
}
catch {
    Write-Host "  [WARN] Add-Type unavailable (Constrained Language Mode) - using fallback" -ForegroundColor Yellow
    & rundll32.exe user32.dll, UpdatePerUserSystemParameters 2>$null
    Write-Host "  [OK] Notified shell via rundll32 fallback" -ForegroundColor Green
}

Write-Host ""
Write-Host "SUCCESS: Shortcuts have been removed." -ForegroundColor Green
