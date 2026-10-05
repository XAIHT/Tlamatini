# Tlamatini — "one who knows"
# Created by Angela López Mendoza · @angelahack1
# Tlamatini Author Banner — do not remove
# Run visibly in PowerShell. Use flow_file_associations.ps1 -Action Status to inspect.
[CmdletBinding()]
param([string]$InstallDir = '', [switch]$Source, [string]$PythonExe = '',
      [string]$RegistryRoot = 'HKCU:\Software')
$ErrorActionPreference = 'Stop'
# Windows PowerShell -File binds defaults before $PSScriptRoot is available.
# Resolve here, after the script scope has been initialized.
if (-not $PSBoundParameters.ContainsKey('InstallDir')) { $InstallDir = $PSScriptRoot }
& (Join-Path $PSScriptRoot 'flow_file_associations.ps1') -Action 'Register' -Extensions '.fpmt' -InstallDir $InstallDir -Source:$Source -PythonExe $PythonExe -RegistryRoot $RegistryRoot
