# Parser only: no enablement or defender workloads are executed.
# Created by Angela Lopez Mendoza · @angelahack1 — Tlamatini Author Banner.
param([string]$SecurityDir = '')
if (-not $SecurityDir) { $SecurityDir = $PSScriptRoot }
$ErrorActionPreference = 'Stop'
$failed = 0
foreach ($file in Get-ChildItem -LiteralPath $SecurityDir -Filter '*.ps1') {
    $tokens=$null; $errors=$null
    [void][Management.Automation.Language.Parser]::ParseFile($file.FullName,[ref]$tokens,[ref]$errors)
    Write-Host "$($file.Name): $(@($errors).Count) parse errors"
    if ($errors.Count) { $errors | Out-String | Write-Host; $failed++ }
}
exit ([int]($failed -gt 0))
