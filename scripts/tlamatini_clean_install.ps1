# Tlamatini Author Banner — Angela López Mendoza · @angelahack1
# Destructive reset for an explicitly authorized CLEAN INSTALL test.
# Run from a verified visible foreground PowerShell -NoExit console.
[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][string]$InstallDir,
    [Parameter(Mandatory=$true)][string]$EvidenceDir,
    [switch]$Execute
)
$ErrorActionPreference = 'Stop'
Add-Type @'
using System;
using System.Runtime.InteropServices;
public static class CleanInstallVisibility {
 [DllImport("kernel32.dll")] public static extern IntPtr GetConsoleWindow();
 [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr h);
 [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
 [DllImport("shell32.dll")] public static extern void SHChangeNotify(uint e,uint f,IntPtr a,IntPtr b);
}
'@
$hwnd = [CleanInstallVisibility]::GetConsoleWindow()
if ($hwnd -eq [IntPtr]::Zero -or -not [CleanInstallVisibility]::IsWindowVisible($hwnd) -or [CleanInstallVisibility]::GetForegroundWindow() -ne $hwnd) {
    throw 'Cleanup requires a verified visible foreground console.'
}
$target = [IO.Path]::GetFullPath($InstallDir).TrimEnd('\')
$repo = [IO.Path]::GetFullPath((Split-Path -Parent $PSScriptRoot)).TrimEnd('\')
if ((Split-Path -Leaf $target) -ine 'Tlamatini' -or $target -ieq $repo -or $repo.StartsWith($target + '\', [StringComparison]::OrdinalIgnoreCase) -or (Test-Path -LiteralPath (Join-Path $target '.git'))) {
    throw "Refusing unsafe installation cleanup target: $target"
}
if (Test-Path -LiteralPath $target) {
    $item = Get-Item -LiteralPath $target
    if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'Installation root is a reparse point.' }
    if (-not (Test-Path -LiteralPath (Join-Path $target 'Tlamatini.exe')) -or -not (Test-Path -LiteralPath (Join-Path $target 'runtime-assets.json'))) {
        throw 'Target is not an identified Tlamatini installation.'
    }
    $links = @(Get-ChildItem -LiteralPath $target -Recurse -Force -Attributes ReparsePoint)
    if ($links.Count) { throw 'Reparse points require inspection before recursive cleanup.' }
}
$evidence = [IO.Path]::GetFullPath($EvidenceDir).TrimEnd('\')
if ($evidence -ieq $target -or $evidence.StartsWith($target + '\', [StringComparison]::OrdinalIgnoreCase)) {
    throw 'Evidence must live outside the installation being removed.'
}
$ownedKeys = @(
 'HKCU:\Software\Classes\Tlamatini.FlowFile',
 'HKCU:\Software\Classes\Tlamatini.PromptFlowFile',
 'HKCU:\Software\Classes\SystemAgent.FlowFile',
 'HKCU:\Software\Tlamatini',
 'HKCU:\Software\XAIHT\Tlamatini',
 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\Tlamatini'
)
$progIds = @('Tlamatini.FlowFile','Tlamatini.PromptFlowFile','SystemAgent.FlowFile')
Write-Host "CLEAN INSTALL TARGET: $target" -ForegroundColor Yellow
Write-Host 'This removes the entire selected installation, including its local user data.'
Write-Host 'This resets the per-user Tlamatini registrations; other applications and Windows UserChoice remain untouched.'
$ownedKeys | ForEach-Object { Write-Host $_ }
if (-not $Execute) { Write-Host 'PREVIEW ONLY: pass -Execute after explicit user authorization.'; return }
$null = New-Item -ItemType Directory -Path $evidence -Force
foreach ($key in $ownedKeys) {
    if (Test-Path -LiteralPath $key) {
        $file = Join-Path $evidence (($key -replace '[\\:]','_') + '.reg')
        & reg.exe export ($key -replace '^HKCU:', 'HKEY_CURRENT_USER') $file /y
        if ($LASTEXITCODE -ne 0) { throw "Could not record registry key before cleanup: $key" }
    }
}
# Stop only executables located inside the explicitly selected installed directory.
foreach ($process in Get-Process) {
    try { $exe = $process.Path } catch { continue }
    if ($exe -and $exe.StartsWith($target + '\', [StringComparison]::OrdinalIgnoreCase)) {
        Write-Host "Stopping installed process $($process.Id): $($process.ProcessName)"
        Stop-Process -Id $process.Id -Force
    }
}
$shell = New-Object -ComObject WScript.Shell
$shortcut = Join-Path ([Environment]::GetFolderPath('Desktop')) 'Tlamatini.lnk'
if (Test-Path -LiteralPath $shortcut) {
    $link = $shell.CreateShortcut($shortcut)
    if ($link.WorkingDirectory.TrimEnd('\') -ieq $target -or $link.Arguments -like ('*' + $target + '\*') -or $link.TargetPath.StartsWith($target + '\', [StringComparison]::OrdinalIgnoreCase)) {
        Copy-Item -LiteralPath $shortcut -Destination (Join-Path $evidence 'Tlamatini.before-clean.lnk')
        Remove-Item -LiteralPath $shortcut -Force
    }
}
foreach ($ext in @('.flw','.fpmt')) {
    $extensionKey = "HKCU:\Software\Classes\$ext"
    if (Test-Path -LiteralPath $extensionKey) {
        $key = [Microsoft.Win32.Registry]::CurrentUser.OpenSubKey("Software\Classes\$ext", $true)
        try { if ($key.GetValue('') -in $progIds) { $key.DeleteValue('', $false) } } finally { $key.Close() }
    }
    foreach ($path in @("Software\Classes\$ext\OpenWithProgids", "Software\Microsoft\Windows\CurrentVersion\Explorer\FileExts\$ext\OpenWithProgids")) {
        $key = [Microsoft.Win32.Registry]::CurrentUser.OpenSubKey($path, $true)
        if ($key) { try { foreach ($id in $progIds) { $key.DeleteValue($id, $false) } } finally { $key.Close() } }
    }
}
$apps = [Microsoft.Win32.Registry]::CurrentUser.OpenSubKey('Software\RegisteredApplications', $true)
if ($apps) { try { $apps.DeleteValue('TlamatiniFlows', $false) } finally { $apps.Close() } }
foreach ($key in $ownedKeys) { if (Test-Path -LiteralPath $key) { Remove-Item -LiteralPath $key -Recurse -Force } }
# Resolve immediately before deletion; the only recursive filesystem target is this exact directory.
if (Test-Path -LiteralPath $target) {
    $resolved = (Resolve-Path -LiteralPath $target).ProviderPath.TrimEnd('\')
    if ($resolved -ine $target -or (Get-Item -LiteralPath $target).Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'Cleanup target changed.' }
    Remove-Item -LiteralPath $target -Recurse -Force
}
if (Test-Path -LiteralPath $target) { throw 'Installation directory still exists.' }
foreach ($key in $ownedKeys) { if (Test-Path -LiteralPath $key) { throw "Registry cleanup incomplete: $key" } }
[CleanInstallVisibility]::SHChangeNotify(0x08000000, 0, [IntPtr]::Zero, [IntPtr]::Zero)
[pscustomobject]@{ InstallDir=$target; DirectoryAbsent=$true; TlamatiniRegistryKeysAbsent=$true; ExplorerRestarted=$false } | ConvertTo-Json | Tee-Object -FilePath (Join-Path $evidence 'clean-baseline.json')
Write-Host 'CLEAN_INSTALL_BASELINE_PASSED' -ForegroundColor Green
