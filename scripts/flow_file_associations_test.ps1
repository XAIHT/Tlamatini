# Tlamatini Author Banner — Angela López Mendoza
# Run in a verified visible foreground PowerShell -NoExit console.
$ErrorActionPreference = 'Stop'
Add-Type @'
using System;
using System.Runtime.InteropServices;
public static class FlowRegistryTestWindow {
    [DllImport("kernel32.dll")] public static extern IntPtr GetConsoleWindow();
    [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr h);
    [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
}
'@
$window = [FlowRegistryTestWindow]::GetConsoleWindow()
if ($window -eq [IntPtr]::Zero -or -not [FlowRegistryTestWindow]::IsWindowVisible($window) -or [FlowRegistryTestWindow]::GetForegroundWindow() -ne $window) {
    throw 'A verified visible foreground console is required.'
}
$repo = Split-Path -Parent $PSScriptRoot
$id = [Guid]::NewGuid().ToString('N')
$testRoot = "HKCU:\Software\XAIHT\Tlamatini\FileAssociationTests\$id"
$fixture = Join-Path $repo "Temp\flow-registry-tests\$id\Install with spaces"
$helper = Join-Path $repo 'flow_file_associations.ps1'
$null = New-Item -ItemType Directory -Path $fixture -Force
$null = New-Item -ItemType File -Path (Join-Path $fixture 'Tlamatini.exe')
Copy-Item -LiteralPath (Join-Path $repo 'Tlamatini.ico') -Destination $fixture
$passed = 0
function Assert-True($Condition, $Message) {
    if (-not $Condition) { throw "FAIL: $Message" }
    $script:passed++
    Write-Host "PASS $script:passed - $Message" -ForegroundColor Green
}
function Value($Path, $Name = '') {
    if (Test-Path -LiteralPath $Path) { return (Get-Item -LiteralPath $Path).GetValue($Name, $null) }
    return $null
}
try {
    # Seed third-party ownership and Windows defaults. None may be deleted.
    foreach ($extension in @('.flw', '.fpmt')) {
        $null = New-Item -Path "$testRoot\Classes\$extension\OpenWithProgids" -Force
        Set-Item -LiteralPath "$testRoot\Classes\$extension" -Value 'OtherApp.Flow'
        New-ItemProperty -Path "$testRoot\Classes\$extension\OpenWithProgids" -Name 'OtherApp.Flow' -Value '' | Out-Null
        $choice = "$testRoot\Microsoft\Windows\CurrentVersion\Explorer\FileExts\$extension\UserChoice"
        $null = New-Item -Path $choice -Force
        New-ItemProperty -Path $choice -Name 'ProgId' -Value 'OtherApp.Flow' | Out-Null
        New-ItemProperty -Path $choice -Name 'Hash' -Value 'do-not-touch' | Out-Null
    }
    $legacy = "$testRoot\Classes\SystemAgent.FlowFile\shell\open\command"
    $null = New-Item -Path $legacy -Force
    Set-Item -LiteralPath $legacy -Value ('powershell.exe -File "' + (Join-Path $fixture 'Tlamatini.ps1') + '" "%1"')
    & $helper -Action Register -InstallDir $fixture -RegistryRoot $testRoot
    Assert-True ((Value $legacy) -match 'conhost.exe') 'Owned legacy ProgID is repaired without rewriting UserChoice'
    & $helper -Action Register -InstallDir $fixture -RegistryRoot $testRoot
    $status = & $helper -Action Status -InstallDir $fixture -RegistryRoot $testRoot | ConvertFrom-Json
    Assert-True ($status.Count -eq 2 -and @($status | Where-Object Registered).Count -eq 2) 'Both formats register idempotently'
    foreach ($row in $status) {
        Assert-True ($row.OwnedByThisInstallation) "$($row.Extension) owner is recorded"
        Assert-True ($row.Command -match '^".+conhost.exe" ".+Tlamatini.exe" "%1"$') 'Executable and file arguments are quoted'
        Assert-True ($row.UserChoice -eq 'OtherApp.Flow' -and $row.DefaultProgId -eq 'OtherApp.Flow') 'Other application defaults survive'
    }
    Assert-True ((Value "$testRoot\Tlamatini\FlowCapabilities\FileAssociations" '.fpmt') -eq 'Tlamatini.PromptFlowFile') 'Default Apps capabilities include prompting flows'
    Assert-True ((Value "$testRoot\RegisteredApplications" 'TlamatiniFlows') -eq 'Software\Tlamatini\FlowCapabilities') 'Application is discoverable in Default Apps'
    # Old uninstallers cannot remove a newer installation registration.
    & $helper -Action Unregister -InstallDir ($fixture + ' old') -RegistryRoot $testRoot
    Assert-True ([bool](Value "$testRoot\Classes\Tlamatini.PromptFlowFile\shell\open\command")) 'A different installation cannot unregister this one'
    & $helper -Action Unregister -InstallDir $fixture -Extensions '.fpmt' -RegistryRoot $testRoot
    Assert-True (-not (Test-Path "$testRoot\Classes\Tlamatini.PromptFlowFile")) 'Prompt flow registration removed'
    Assert-True ([bool](Value "$testRoot\Classes\Tlamatini.FlowFile\shell\open\command")) 'Removing prompt flows preserves agent flows'
    & $helper -Action Repair -InstallDir $fixture -RegistryRoot $testRoot
    Assert-True (-not (Test-Path "$testRoot\Classes\Tlamatini.PromptFlowFile")) 'Update repair respects explicit unregistration'
    & $helper -Action Unregister -InstallDir $fixture -RegistryRoot $testRoot
    & $helper -Action Unregister -InstallDir $fixture -RegistryRoot $testRoot
    foreach ($extension in @('.flw', '.fpmt')) {
        $choice = "$testRoot\Microsoft\Windows\CurrentVersion\Explorer\FileExts\$extension\UserChoice"
        Assert-True ((Value $choice 'Hash') -eq 'do-not-touch') 'Uninstall preserves the Windows UserChoice hash'
        Assert-True ($null -ne (Value "$testRoot\Classes\$extension\OpenWithProgids" 'OtherApp.Flow')) 'Uninstall preserves other Open With candidates'
    }
    Assert-True (-not (Test-Path "$testRoot\Classes\SystemAgent.FlowFile")) 'Owned legacy ProgID is removed'
    Assert-True ($null -eq (Value "$testRoot\RegisteredApplications" 'TlamatiniFlows')) 'Empty application capability entry removed'
    # Extensions without a default receive our ProgID; removal prunes only ours.
    $key = [Microsoft.Win32.Registry]::CurrentUser.OpenSubKey(($testRoot + '\Classes\.fpmt').Substring(6), $true)
    try { $key.DeleteValue('', $false) } finally { $key.Close() }
    & $helper -Action Register -InstallDir $fixture -Extensions '.fpmt' -RegistryRoot $testRoot
    Assert-True ((Value "$testRoot\Classes\.fpmt") -eq 'Tlamatini.PromptFlowFile') 'Unclaimed extension gets its own default'
    & $helper -Action Unregister -InstallDir $fixture -Extensions '.fpmt' -RegistryRoot $testRoot
    Assert-True ($null -eq (Value "$testRoot\Classes\.fpmt")) 'Removal clears only our default'
    & (Join-Path $repo 'register_fpmt.ps1') -InstallDir $repo -Source -PythonExe (Get-Command python.exe).Source -RegistryRoot $testRoot
    Assert-True ((Value "$testRoot\Classes\Tlamatini.PromptFlowFile\shell\open\command") -match '".+python.exe" ".+Tlamatini\\manage.py" "%1"$') 'Source registration targets manage.py without a shell command string'
    & (Join-Path $repo 'unregister_fpmt.ps1') -InstallDir $repo -RegistryRoot $testRoot
    & (Join-Path $repo 'register_flw.ps1') -InstallDir $fixture -RegistryRoot $testRoot
    Assert-True ([bool](Value "$testRoot\Classes\Tlamatini.PromptFlowFile\shell\open\command")) 'Legacy installer entry point registers both formats'
    & (Join-Path $repo 'unregister_flw.ps1') -InstallDir $fixture -RegistryRoot $testRoot
    Assert-True (-not (Test-Path "$testRoot\Classes\Tlamatini.PromptFlowFile")) 'Legacy uninstaller entry point removes both formats'
    # Exercise the real installer invocation: a fresh Windows PowerShell process,
    # -File, no InstallDir argument, and an unrelated current directory.
    foreach ($name in @('flow_file_associations.ps1', 'register_flw.ps1', 'register_fpmt.ps1', 'unregister_flw.ps1', 'unregister_fpmt.ps1')) {
        Copy-Item -LiteralPath (Join-Path $repo $name) -Destination $fixture
    }
    Push-Location $env:SystemRoot
    try {
        foreach ($name in @('register_flw.ps1', 'unregister_flw.ps1', 'register_fpmt.ps1', 'unregister_fpmt.ps1')) {
            & powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $fixture $name) -RegistryRoot $testRoot
            Assert-True ($LASTEXITCODE -eq 0) "$name works with the installer's -File/default-directory invocation"
            $id = if ($name -match 'fpmt') { 'Tlamatini.PromptFlowFile' } else { 'Tlamatini.FlowFile' }
            $actual = Value "$testRoot\Classes\$id" 'TlamatiniInstallDir'
            if ($name.StartsWith('unregister')) {
                Assert-True ($null -eq $actual) "$name actually removes the owned registration"
            } else {
                Assert-True ($actual -eq $fixture) "$name resolves its own script directory, not cwd"
            }
        }
        $defaultStatus = & powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $fixture 'flow_file_associations.ps1') -Action Status -RegistryRoot $testRoot
        $defaultExit = $LASTEXITCODE
        $defaultRows = $defaultStatus | ConvertFrom-Json
        Assert-True ($defaultExit -eq 0 -and $defaultRows.Count -eq 2) 'Direct helper -File invocation resolves its directory'
    } finally { Pop-Location }
    Write-Host "ALL $passed WINDOWS REGISTRY CHECKS PASSED" -ForegroundColor Cyan
} finally {
    # Exact isolated test key, never Classes or Explorer in the live registry.
    if ($testRoot -notmatch '^HKCU:\\Software\\XAIHT\\Tlamatini\\FileAssociationTests\\[a-f0-9]{32}$') { throw 'Unsafe test cleanup path.' }
    if (Test-Path -LiteralPath $testRoot) { Remove-Item -LiteralPath $testRoot -Recurse }
}
