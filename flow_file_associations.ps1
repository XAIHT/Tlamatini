# Tlamatini — "one who knows"
# Created by Angela López Mendoza · @angelahack1
# Tlamatini Author Banner — do not remove
# Per-user registration. Never modify UserChoice, its hash, or other applications.
[CmdletBinding()]
param(
    [ValidateSet('Register', 'Repair', 'Unregister', 'Status', 'DefaultApps')][string]$Action = 'Status',
    [ValidateSet('.flw', '.fpmt')][string[]]$Extensions = @('.flw', '.fpmt'),
    [string]$InstallDir = '',
    [switch]$Source,
    [string]$PythonExe = '',
    [string]$RegistryRoot = 'HKCU:\Software'
)
$ErrorActionPreference = 'Stop'
# Windows PowerShell -File binds defaults before $PSScriptRoot is available.
# Resolve here, after the script scope has been initialized.
if (-not $PSBoundParameters.ContainsKey('InstallDir')) { $InstallDir = $PSScriptRoot }
if ($RegistryRoot -ne 'HKCU:\Software' -and $RegistryRoot -notmatch '^HKCU:\\Software\\XAIHT\\Tlamatini\\FileAssociationTests\\[a-zA-Z0-9_-]+$') {
    throw 'RegistryRoot must be HKCU:\Software or an isolated Tlamatini FileAssociationTests key.'
}
if ([string]::IsNullOrWhiteSpace($InstallDir)) { throw 'InstallDir must identify the Tlamatini installation directory.' }
$InstallDir = [IO.Path]::GetFullPath($InstallDir)
if ($InstallDir -ne [IO.Path]::GetPathRoot($InstallDir)) { $InstallDir = $InstallDir.TrimEnd('\') }
$classes = "$RegistryRoot\Classes"
$capabilities = "$RegistryRoot\Tlamatini\FlowCapabilities"
$registered = "$RegistryRoot\RegisteredApplications"
$preferences = "$RegistryRoot\Tlamatini\FileTypes"
$definitions = @{
    '.flw' = @{ ProgId = 'Tlamatini.FlowFile'; Name = 'Tlamatini Agent Flow' }
    '.fpmt' = @{ ProgId = 'Tlamatini.PromptFlowFile'; Name = 'Tlamatini Prompting Flow' }
}
function Read-Value([string]$Path, [string]$Name = '') {
    if (Test-Path -LiteralPath $Path) { return (Get-Item -LiteralPath $Path).GetValue($Name, $null) }
    return $null
}
function Set-Value([string]$Path, [string]$Name, [object]$Value, [Microsoft.Win32.RegistryValueKind]$Kind = 'String') {
    $key = [Microsoft.Win32.Registry]::CurrentUser.CreateSubKey($Path.Substring(6))
    try { $key.SetValue($Name, $Value, $Kind) } finally { $key.Close() }
}
function Remove-Value([string]$Path, [string]$Name) {
    if (Test-Path -LiteralPath $Path) {
        $key = [Microsoft.Win32.Registry]::CurrentUser.OpenSubKey($Path.Substring(6), $true)
        try { $key.DeleteValue($Name, $false) } finally { $key.Close() }
    }
}
function Remove-EmptyKey([string]$Path) {
    if (Test-Path -LiteralPath $Path) {
        $key = Get-Item -LiteralPath $Path
        $empty = $key.SubKeyCount -eq 0 -and $key.ValueCount -eq 0
        $key.Close()
        if ($empty) { Remove-Item -LiteralPath $Path }
    }
}
function Test-Owned([string]$ProgPath) {
    $owner = Read-Value $ProgPath 'TlamatiniInstallDir'
    if ($owner) { return $owner -ieq $InstallDir }
    # Upgrade compatibility with the old registration that lacked owner metadata.
    $oldCommand = Read-Value "$ProgPath\shell\open\command"
    return $oldCommand -and ($oldCommand.Contains('"' + (Join-Path $InstallDir 'Tlamatini.exe') + '"') -or
                            $oldCommand.Contains('"' + (Join-Path $InstallDir 'Tlamatini.ps1') + '"'))
}
if ($Action -eq 'DefaultApps') {
    if ($RegistryRoot -ne 'HKCU:\Software') { throw 'DefaultApps is unavailable for a test registry.' }
    Start-Process 'ms-settings:defaultapps?registeredAppUser=TlamatiniFlows'
    return
}
if ($Action -in @('Register', 'Repair')) {
    $executable = Join-Path $InstallDir 'Tlamatini.exe'
    if ($Source) {
        $entry = Join-Path $InstallDir 'Tlamatini\manage.py'
        if (-not $PythonExe) { $PythonExe = (Get-Command python.exe -ErrorAction Stop).Source }
        $PythonExe = (Resolve-Path -LiteralPath $PythonExe).Path
        if (-not (Test-Path -LiteralPath $entry -PathType Leaf)) { throw "Source entry point missing: $entry" }
        $targetCommand = '"' + $PythonExe + '" "' + $entry + '" "%1"'
    } else {
        if (-not (Test-Path -LiteralPath $executable -PathType Leaf)) { throw "Application missing: $executable" }
        $targetCommand = '"' + $executable + '" "%1"'
    }
    $console = Join-Path $env:SystemRoot 'System32\conhost.exe'
    if (-not (Test-Path -LiteralPath $console -PathType Leaf)) { throw 'Windows console host is unavailable.' }
    $command = '"' + $console + '" ' + $targetCommand
    $icon = Join-Path $InstallDir 'Tlamatini.ico'
    if (-not (Test-Path -LiteralPath $icon -PathType Leaf)) { throw "Application icon missing: $icon" }
    foreach ($extension in $Extensions) {
        if ($Action -eq 'Repair' -and (Read-Value "$preferences\$extension" 'Disabled') -eq 1) { continue }
        $definition = $definitions[$extension]
        $progId = $definition.ProgId
        $progPath = "$classes\$progId"
        # Repair cannot take another installation's registration. Explicit Register can.
        if ($Action -eq 'Repair' -and (Test-Path -LiteralPath $progPath) -and -not (Test-Owned $progPath)) { continue }
        Set-Value $progPath '' $definition.Name
        Set-Value $progPath 'TlamatiniInstallDir' $InstallDir
        Set-Value "$progPath\DefaultIcon" '' ('"' + $icon + '",0')
        Set-Value "$progPath\shell\open" 'FriendlyAppName' 'Tlamatini'
        Set-Value "$progPath\shell\open\command" '' $command
        # Retain a user-selected legacy ProgID only when it belongs to this install.
        $legacyPath = "$classes\SystemAgent.FlowFile"
        if ($extension -eq '.flw' -and (Test-Owned $legacyPath)) {
            Set-Value $legacyPath 'TlamatiniInstallDir' $InstallDir
            Set-Value "$legacyPath\DefaultIcon" '' ('"' + $icon + '",0')
            Set-Value "$legacyPath\shell\open\command" '' $command
        }
        $extensionPath = "$classes\$extension"
        $current = Read-Value $extensionPath
        if (-not $current -or $current -eq $progId) { Set-Value $extensionPath '' $progId }
        Set-Value "$extensionPath\OpenWithProgids" $progId ([byte[]]@()) 'None'
        Set-Value $capabilities 'ApplicationName' 'Tlamatini'
        Set-Value $capabilities 'ApplicationDescription' 'Edit agent flows and prompting flows in Tlamatini.'
        Set-Value $capabilities 'ApplicationIcon' ('"' + $icon + '",0')
        Set-Value "$capabilities\FileAssociations" $extension $progId
        Set-Value $registered 'TlamatiniFlows' 'Software\Tlamatini\FlowCapabilities'
        Remove-Value "$preferences\$extension" 'Disabled'
        Write-Host "Registered $extension - $($definition.Name)" -ForegroundColor Green
    }
} elseif ($Action -eq 'Unregister') {
    foreach ($extension in $Extensions) {
        $progId = $definitions[$extension].ProgId
        $progPath = "$classes\$progId"
        if ((Test-Path -LiteralPath $progPath) -and -not (Test-Owned $progPath)) {
            Write-Host "Kept $extension registration belonging to another installation."
            continue
        }
        $extensionPath = "$classes\$extension"
        $legacyPath = "$classes\SystemAgent.FlowFile"
        if ($extension -eq '.flw' -and (Test-Owned $legacyPath)) {
            if ((Read-Value $extensionPath) -eq 'SystemAgent.FlowFile') { Remove-Value $extensionPath '' }
            Remove-Value "$extensionPath\OpenWithProgids" 'SystemAgent.FlowFile'
            Remove-Value "$RegistryRoot\Microsoft\Windows\CurrentVersion\Explorer\FileExts\.flw\OpenWithProgids" 'SystemAgent.FlowFile'
            Remove-Item -LiteralPath $legacyPath -Recurse
        }
        if ((Read-Value $extensionPath) -eq $progId) { Remove-Value $extensionPath '' }
        Remove-Value "$extensionPath\OpenWithProgids" $progId
        Remove-EmptyKey "$extensionPath\OpenWithProgids"
        Remove-EmptyKey $extensionPath
        # Remove only our old Explorer candidate, never UserChoice or OpenWithList.
        $explorer = "$RegistryRoot\Microsoft\Windows\CurrentVersion\Explorer\FileExts\$extension\OpenWithProgids"
        Remove-Value $explorer $progId
        Remove-EmptyKey $explorer
        if (Test-Path -LiteralPath $progPath) { Remove-Item -LiteralPath $progPath -Recurse }
        if ((Read-Value "$capabilities\FileAssociations" $extension) -eq $progId) {
            Remove-Value "$capabilities\FileAssociations" $extension
        }
        Set-Value "$preferences\$extension" 'Disabled' 1 'DWord'
        Write-Host "Unregistered $extension for this installation." -ForegroundColor Green
    }
    $remaining = @('.flw', '.fpmt') | Where-Object { Read-Value "$capabilities\FileAssociations" $_ }
    if (-not $remaining) {
        Remove-EmptyKey "$capabilities\FileAssociations"
        foreach ($name in @('ApplicationName', 'ApplicationDescription', 'ApplicationIcon')) { Remove-Value $capabilities $name }
        Remove-EmptyKey $capabilities
        if ((Read-Value $registered 'TlamatiniFlows') -eq 'Software\Tlamatini\FlowCapabilities') { Remove-Value $registered 'TlamatiniFlows' }
    }
} elseif ($Action -eq 'Status') {
    @($Extensions | ForEach-Object {
        $id = $definitions[$_].ProgId
        [pscustomobject]@{
            Extension = $_; Name = $definitions[$_].Name
            Registered = [bool](Read-Value "$classes\$id\shell\open\command")
            OwnedByThisInstallation = [bool](Test-Owned "$classes\$id")
            Command = Read-Value "$classes\$id\shell\open\command"
            DefaultProgId = Read-Value "$classes\$_"
            UserChoice = Read-Value "$RegistryRoot\Microsoft\Windows\CurrentVersion\Explorer\FileExts\$_\UserChoice" 'ProgId'
            RepairDisabled = (Read-Value "$preferences\$_" 'Disabled') -eq 1
        }
    }) | ConvertTo-Json -Depth 3
    return
}
if ($RegistryRoot -eq 'HKCU:\Software') {
    if (-not ('Tlamatini.FlowAssociationNotify' -as [type])) {
        Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
namespace Tlamatini {
    public static class FlowAssociationNotify {
        [DllImport("shell32.dll")] public static extern void SHChangeNotify(uint e, uint f, IntPtr a, IntPtr b);
    }
}
'@
    }
    [Tlamatini.FlowAssociationNotify]::SHChangeNotify(0x08000000, 0, [IntPtr]::Zero, [IntPtr]::Zero)
}
