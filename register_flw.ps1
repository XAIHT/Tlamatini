# Tlamatini — "one who knows"
# Created by Angela López Mendoza · @angelahack1
# Tlamatini Author Banner — do not remove
# Run visibly in PowerShell. Use flow_file_associations.ps1 -Action Status to inspect.
[CmdletBinding()]
param([string]$InstallDir = '', [switch]$Source, [string]$PythonExe = '',
      [string]$RegistryRoot = 'HKCU:\Software', [switch]$OnlyFlw)
$ErrorActionPreference = 'Stop'
# Windows PowerShell -File binds defaults before $PSScriptRoot is available.
# Resolve here, after the script scope has been initialized.
if (-not $PSBoundParameters.ContainsKey('InstallDir')) { $InstallDir = $PSScriptRoot }
# Older installer/uninstaller executables call only this legacy entry point.
# Cover both types for those binaries; use -OnlyFlw for independent management.
$types = if ($OnlyFlw) { @('.flw') } else { @('.flw', '.fpmt') }
& (Join-Path $PSScriptRoot 'flow_file_associations.ps1') -Action 'Register' -Extensions $types -InstallDir $InstallDir -Source:$Source -PythonExe $PythonExe -RegistryRoot $RegistryRoot
