# Non-admin behavior tests: every Windows-policy mutation below is a mock.
# Created by Angela Lopez Mendoza · @angelahack1 — Tlamatini Author Banner.
param([string]$SecurityDir = '')
if (-not $SecurityDir) { $SecurityDir = $PSScriptRoot }
$ErrorActionPreference = 'Stop'
. (Join-Path $SecurityDir 'windows_access_helpers.ps1')
$script:checks = 0
$script:failed = 0
function Assert-True($condition, [string]$message) { if (-not $condition) { throw $message } }
function Assert-Throws([scriptblock]$action) { $threw=$false; try { & $action } catch { $threw=$true }; Assert-True $threw 'Expected an error' }
function Test-Case([string]$name, [scriptblock]$action) {
    $script:checks++
    try { Reset-Mocks; & $action; Write-Host "PASS $name" -ForegroundColor Green }
    catch { $script:failed++; Write-Host "FAIL $name : $($_.Exception.Message)" -ForegroundColor Red }
}
function Reset-Mocks {
    $script:EnablementFailures = [Collections.Generic.List[string]]::new()
    $script:entries = @(); $script:journal = @(); $script:created=0; $script:disabled=@(); $script:killed=@()
    $script:ignoreDefender=$false; $script:ignoreFirewall=$false; $script:wrongAddress=$false
    $script:rules=@{}; $script:lookupProcess=$null; $script:Respond=$false
}
function Save-EnablementChange { param($Kind,$Name,$Previous); $script:journal += "$Kind|$Name|$Previous" }
function Get-MpPreference { [CmdletBinding()]param(); return [pscustomobject]@{ControlledFolderAccessAllowedApplications=@($script:entries)} }
function Add-MpPreference { [CmdletBinding()]param($ControlledFolderAccessAllowedApplications); if (-not $script:ignoreDefender) { $script:entries += $ControlledFolderAccessAllowedApplications } }
function Get-NetFirewallRule {
    [CmdletBinding()]param($PolicyStore,$Name)
    if ($script:rules.ContainsKey($Name)) { return $script:rules[$Name] }
}
function New-NetFirewallRule {
    [CmdletBinding()]param($PolicyStore,$Name,$Direction,$Program,$Action,$Enabled,$Profile,$RemoteAddress,$Protocol,$Group,$DisplayName)
    $script:created++
    $script:rules[$Name]=[pscustomobject]@{Name=$Name;Direction=$Direction;Program=$Program;Action=$Action;Enabled=$Enabled;Profile=($Profile -join ', ');RemoteAddress=@($RemoteAddress);Protocol=$Protocol;Group=$Group;DisplayName=$DisplayName;PolicyStoreSourceType='Local'}
    if ($script:ignoreFirewall) { $script:rules[$Name].Enabled='False' }
}
function Set-NetFirewallRule {
    [CmdletBinding()]param($PolicyStore,$Name,$Direction,$Program,$Action,$Enabled,$Profile,$RemoteAddress,$Protocol)
    $r=$script:rules[$Name];$r.Direction=$Direction;$r.Program=$Program;$r.Action=$Action;$r.Enabled=$Enabled
    $r.Profile=$Profile -join ', ';$r.RemoteAddress=@($RemoteAddress);$r.Protocol=$Protocol
    if ($script:ignoreFirewall) { $r.Enabled='False' }
}
function Get-NetFirewallApplicationFilter {
    [CmdletBinding()]param([Parameter(ValueFromPipeline)]$InputObject)
    process { [pscustomobject]@{Program=$InputObject.Program} }
}
function Get-NetFirewallAddressFilter {
    [CmdletBinding()]param([Parameter(ValueFromPipeline)]$InputObject)
    process { if ($script:wrongAddress) { [pscustomobject]@{RemoteAddress=@('Any')} } else { [pscustomobject]@{RemoteAddress=@($InputObject.RemoteAddress)} } }
}
function Get-NetFirewallPortFilter {
    [CmdletBinding()]param([Parameter(ValueFromPipeline)]$InputObject)
    process { [pscustomobject]@{Protocol=$InputObject.Protocol} }
}
function Disable-NetFirewallRule { [CmdletBinding()]param($PolicyStore,$Name);$script:disabled += $Name;if (-not $script:ignoreFirewall) { $script:rules[$Name].Enabled='False' } }
function Add-Block($name,$program,$origin='Local') {
    $r=[pscustomobject]@{Name=$name;DisplayName=$name;Program=$program;Action='Block';Enabled='True';PolicyStoreSourceType=$origin}
    $script:rules[$name]=$r;return $r
}

Test-Case 'CFA allowance is added and read back' { Add-VerifiedDefenderEntry 'ControlledFolderAccessAllowedApplications' 'C:\App\python.exe'; Assert-True ($script:entries.Count -eq 1 -and $script:journal.Count -eq 1) 'Missing permission or recovery entry' }
Test-Case 'Existing CFA allowance is idempotent' { $script:entries=@('C:\App\python.exe');Add-VerifiedDefenderEntry 'ControlledFolderAccessAllowedApplications' 'C:\App\python.exe';Assert-True ($script:journal.Count -eq 0) 'Existing permission changed' }
Test-Case 'Silently ignored Defender changes are failures' { $script:ignoreDefender=$true;Assert-Throws { Add-VerifiedDefenderEntry 'ControlledFolderAccessAllowedApplications' 'C:\App\python.exe' } }
Test-Case 'Outbound rules are stable and do not duplicate' { Set-VerifiedFirewallAllowance 'C:\App\python.exe' 'Outbound';Set-VerifiedFirewallAllowance 'C:\App\python.exe' 'Outbound';Assert-True ($script:created -eq 1) 'Duplicate rule' }
Test-Case 'Disabled existing owned rule is repaired' { Set-VerifiedFirewallAllowance 'C:\App\python.exe' 'Outbound';$script:rules[(Get-EnablementRuleName 'C:\App\python.exe' 'Outbound')].Enabled='False';Set-VerifiedFirewallAllowance 'C:\App\python.exe' 'Outbound' }
Test-Case 'Missing effective firewall permission fails' { $script:ignoreFirewall=$true;Assert-Throws { Set-VerifiedFirewallAllowance 'C:\App\python.exe' 'Outbound' } }
Test-Case 'Loopback rules restrict incoming remote addresses' { Set-VerifiedFirewallAllowance 'C:\App\python.exe' 'Loopback';$r=$script:rules[(Get-EnablementRuleName 'C:\App\python.exe' 'Loopback')];Assert-True ($r.RemoteAddress -contains '127.0.0.1' -and $r.RemoteAddress -contains '::1' -and $r.RemoteAddress -notcontains 'Any') 'Too broad' }
Test-Case 'Unexpected broadening of loopback rule fails verification' { $script:wrongAddress=$true;Assert-Throws { Set-VerifiedFirewallAllowance 'C:\App\python.exe' 'Loopback' } }
Test-Case 'Opt-in LAN access is subnet and private/domain only' { Set-VerifiedFirewallAllowance 'C:\App\python.exe' 'LAN';$r=$script:rules[(Get-EnablementRuleName 'C:\App\python.exe' 'LAN')];Assert-True ($r.Profile -eq 'Domain, Private' -and $r.RemoteAddress[0] -eq 'LocalSubnet') 'LAN rule too broad' }
Test-Case 'Unrelated rule-name collisions cannot be overwritten' { Set-VerifiedFirewallAllowance 'C:\App\python.exe' 'Outbound';$script:rules[(Get-EnablementRuleName 'C:\App\python.exe' 'Outbound')].Group='Other';Assert-Throws { Set-VerifiedFirewallAllowance 'C:\App\python.exe' 'Outbound' } }
Test-Case 'Exact local program block is disabled with recovery record' { $r=Add-Block 'local' 'C:\App\python.exe';Repair-ExactApplicationBlocks @($r) @('C:\App\python.exe');Assert-True ($script:disabled.Count -eq 1 -and $script:journal.Count -eq 1) 'Block not repaired and journaled' }
Test-Case 'Managed program block is reported and preserved' { $r=Add-Block 'managed' 'C:\App\python.exe' 'GroupPolicy';Repair-ExactApplicationBlocks @($r) @('C:\App\python.exe');Assert-True ($script:disabled.Count -eq 0 -and $script:EnablementFailures.Count -eq 1) 'Managed policy modified or hidden' }
Test-Case 'Broad IP/port block is reported and preserved' { $r=Add-Block 'broad' 'Any';Repair-ExactApplicationBlocks @($r) @('C:\App\python.exe');Assert-True ($script:disabled.Count -eq 0 -and $script:EnablementFailures.Count -eq 1) 'Broad rule modified or hidden' }
Test-Case 'Sibling application block is preserved' { $r=Add-Block 'other' 'C:\App-old\python.exe';Repair-ExactApplicationBlocks @($r) @('C:\App\python.exe');Assert-True ($script:disabled.Count -eq 0) 'Sibling block modified' }
Test-Case 'A block that remains effective cannot pass' { $r=Add-Block 'local' 'C:\App\python.exe';$script:ignoreFirewall=$true;Assert-Throws { Repair-ExactApplicationBlocks @($r) @('C:\App\python.exe') } }
Test-Case 'Path matching handles case without wildcard expansion' { Assert-True (Test-ExactProgram 'C:\APP\python.exe' 'c:\app\python.exe') 'Case mismatch';Assert-True (-not (Test-ExactProgram 'C:\App\*' 'C:\App\python.exe')) 'Wildcard trusted' }

# Reproduce the actual source-checkout CFA omission without applying policy.
$tokens=$null;$errors=$null
$whitelistAst=[Management.Automation.Language.Parser]::ParseFile((Join-Path $SecurityDir 'tlamatini_whitelist_v2.ps1'),[ref]$tokens,[ref]$errors)
if ($errors.Count) { throw ($errors | Out-String) }
$addPath=$whitelistAst.FindAll({param($node) $node -is [Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -eq 'Add-UniqueExistingPath'},$false)[0]
. ([scriptblock]::Create($addPath.Extent.Text))
$discovery=$whitelistAst.FindAll({param($node) $node -is [Management.Automation.Language.ForEachStatementAst] -and $node.Extent.Text.Contains('$frozenExe =')},$false)[0]
Test-Case 'Source checkout discovers its bundled Python, even without a frozen EXE' {
    $existingPaths=@('C:\Source\python\python.exe','C:\Source\Tlamatini\manage.py')
    function Test-Path { param($LiteralPath,$PathType);return $existingPaths -contains $LiteralPath }
    $TlamatiniRoots=@('C:\Source')
    $TlamatiniCarriedPythons=[Collections.Generic.List[string]]::new()
    $TlamatiniDevPythons=[Collections.Generic.List[string]]::new()
    $TlamatiniPrograms=[Collections.Generic.List[string]]::new()
    $TlamatiniRouteReport=[Collections.Generic.List[string]]::new()
    $sourceRouteFound=$false
    . ([scriptblock]::Create($discovery.Extent.Text))
    Assert-True ($TlamatiniCarriedPythons -contains 'C:\Source\python\python.exe') 'Bundled source Python missed'
    Assert-True $sourceRouteFound 'Source route not recognized'
}

# Load ONLY function definitions. Never run the defender's top-level monitors.
$tokens=$null;$errors=$null
$ast=[Management.Automation.Language.Parser]::ParseFile((Join-Path $SecurityDir 'tlamatini_defender.ps1'),[ref]$tokens,[ref]$errors)
if ($errors.Count) { throw ($errors | Out-String) }
foreach ($fn in $ast.FindAll({param($node) $node -is [Management.Automation.Language.FunctionDefinitionAst]},$false)) { . ([scriptblock]::Create($fn.Extent.Text)) }
function Write-Alert { param($Message,$Severity) }
function Send-DesktopNotification { param($Title,$Message) }
function Get-Process { [CmdletBinding()]param($Id);return $script:lookupProcess }
function Stop-Process { [CmdletBinding()]param($InputObject,[switch]$Force);$script:killed += $InputObject }
function Test-NotificationPolicy($armed,$detectOnly) {
    $Armed=$armed;$DetectOnly=$detectOnly
    $assignment=$ast.FindAll({param($node) $node -is [Management.Automation.Language.AssignmentStatementAst] -and $node.Left.Extent.Text -eq '$script:Respond'},$true)[0]
    . ([scriptblock]::Create($assignment.Extent.Text))
}
Test-Case 'Defender defaults to report-only' { Test-NotificationPolicy $false $false;Assert-True (-not $script:Respond) 'Default is armed';Stop-SuspiciousProcess 123 'nmap' 'test';Assert-True ($script:killed.Count -eq 0) 'Default scan stopped a process' }
Test-Case 'DetectOnly wins over containment' { Test-NotificationPolicy $true $true;Assert-True (-not $script:Respond) 'DetectOnly can kill' }
Test-Case 'Self-path boundaries do not trust siblings or wildcards' { $script:SelfRoots=@('C:\App[1]');Assert-True (Test-IsSelf 'C:\App[1]\python.exe') 'Self not recognized';Assert-True (-not (Test-IsSelf 'C:\App1\python.exe')) 'Wildcard root trusted';Assert-True (-not (Test-IsSelf 'C:\App[1]-old\python.exe')) 'Sibling trusted' }
Test-Case 'Armed response refuses unreadable process paths' { $script:Respond=$true;$script:lookupProcess=[pscustomobject]@{Id=123;ProcessName='nmap';Path=$null};Stop-SuspiciousProcess 123 'nmap' 'test';Assert-True ($script:killed.Count -eq 0) 'Unknown identity killed' }
Test-Case 'Armed response refuses a PID now owned by another process name' { $script:Respond=$true;$script:SelfRoots=@('C:\App');$script:lookupProcess=[pscustomobject]@{Id=123;ProcessName='editor';Path='C:\Tools\editor.exe'};Stop-SuspiciousProcess 123 'nmap' 'test';Assert-True ($script:killed.Count -eq 0) 'Reused process identity killed' }
Test-Case 'Armed response preserves Tlamatini-owned executables' { $script:Respond=$true;$script:SelfRoots=@('C:\App');$script:lookupProcess=[pscustomobject]@{Id=123;ProcessName='nmap';Path='C:\App\tools\nmap.exe'};Stop-SuspiciousProcess 123 'nmap' 'test';Assert-True ($script:killed.Count -eq 0) 'Self process killed' }
Write-Host "WINDOWS ACCESS TESTS: $($script:checks - $script:failed)/$script:checks passed; $script:failed failed"
if ($script:failed) { exit 1 }
exit 0
