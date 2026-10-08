# Created by Angela Lopez Mendoza · @angelahack1 — Tlamatini Author Banner.
# Pure helper definitions. Dot-sourcing does not change Windows settings.

function Write-EnablementWarning {
    param([string]$Message)
    $script:EnablementFailures.Add($Message)
    Write-Host "  [ATTENTION] $Message" -ForegroundColor Yellow
}

function Add-VerifiedDefenderEntry {
    param([string]$Property, [string]$Value)
    $before = @((Get-MpPreference -ErrorAction Stop).$Property)
    if ($before -notcontains $Value) {
        Save-EnablementChange 'DefenderEntry' $Property $Value
        $arguments = @{ErrorAction='Stop'}
        $arguments[$Property] = $Value
        Add-MpPreference @arguments
    }
    if (@((Get-MpPreference -ErrorAction Stop).$Property) -notcontains $Value) {
        throw "Windows did not retain $Property : $Value (check Tamper Protection or managed policy)."
    }
    Write-Host "  [OK] Verified $Property : $Value" -ForegroundColor Green
}

function Save-EnablementChange {
    param([string]$Kind, [string]$Name, $Previous)
    # Persist intent before the operation so partial runs have recovery evidence.
    $entry = [pscustomobject]@{time=(Get-Date).ToString('o'); kind=$Kind; name=$Name; previous=$Previous}
    $entry | ConvertTo-Json -Depth 8 -Compress | Add-Content -LiteralPath $script:ChangesPath -Encoding UTF8 -ErrorAction Stop
}

function Set-VerifiedLoggingValue {
    param([string]$Path, [string]$Name)
    $key = Get-Item -LiteralPath $Path -ErrorAction SilentlyContinue
    $exists = $key -and $key.GetValueNames() -contains $Name
    $previous = @{path=$Path; keyExisted=[bool]$key; valueExisted=[bool]$exists}
    if ($exists) { $previous.value=$key.GetValue($Name); $previous.type=[string]$key.GetValueKind($Name) }
    Save-EnablementChange 'RegistryValue' $Name $previous
    if (-not $key) { New-Item -Path $Path -Force -ErrorAction Stop | Out-Null }
    Set-ItemProperty -LiteralPath $Path -Name $Name -Value 1 -Type DWord -ErrorAction Stop
    if ((Get-ItemPropertyValue -LiteralPath $Path -Name $Name -ErrorAction Stop) -ne 1) {
        throw "Windows did not retain the logging setting $Path\$Name"
    }
}

function Get-EnablementRuleName {
    param([string]$Program, [string]$Direction)
    $sha = [Security.Cryptography.SHA256]::Create()
    try { $hash = [BitConverter]::ToString($sha.ComputeHash([Text.Encoding]::UTF8.GetBytes($Program.ToLowerInvariant()))).Replace('-','').Substring(0,24) }
    finally { $sha.Dispose() }
    return "Tlamatini-Access-$Direction-$hash"
}

function Test-ExactProgram {
    param([string]$Left, [string]$Right)
    if (-not $Left -or -not $Right -or $Left -eq 'Any' -or $Right -eq 'Any') { return $false }
    try {
        return [IO.Path]::GetFullPath([Environment]::ExpandEnvironmentVariables($Left.Trim('"'))) -ieq
            [IO.Path]::GetFullPath([Environment]::ExpandEnvironmentVariables($Right.Trim('"')))
    } catch { return $false }
}

function Set-VerifiedFirewallAllowance {
    param([string]$Program, [ValidateSet('Outbound','Loopback','LAN')][string]$Kind)
    $name = Get-EnablementRuleName $Program $Kind
    $group = 'Tlamatini Windows Access'
    $direction = if ($Kind -eq 'Outbound') { 'Outbound' } else { 'Inbound' }
    $remote = if ($Kind -eq 'Loopback') { @('127.0.0.1','::1') } elseif ($Kind -eq 'LAN') { @('LocalSubnet') } else { @('Any') }
    $profile = if ($Kind -eq 'LAN') { @('Domain','Private') } else { @('Any') }
    $existing = Get-NetFirewallRule -PolicyStore PersistentStore -Name $name -ErrorAction SilentlyContinue
    if ($existing -and $existing.Group -ne $group) { throw "Unrelated firewall rule owns $name; left unchanged." }
    $ruleArgs = @{PolicyStore='PersistentStore';Name=$name;Direction=$direction;Program=$Program;Action='Allow';Enabled='True';Profile=$profile;RemoteAddress=$remote;Protocol='Any';ErrorAction='Stop'}
    if ($existing) {
        $previous = @{
            rule=($existing | Select-Object Name,Enabled,Action,Direction,Profile)
            application=($existing | Get-NetFirewallApplicationFilter | Select-Object Program,Package)
            address=($existing | Get-NetFirewallAddressFilter | Select-Object LocalAddress,RemoteAddress)
            port=($existing | Get-NetFirewallPortFilter | Select-Object Protocol,LocalPort,RemotePort)
        }
        Save-EnablementChange 'ExistingFirewallRule' $name $previous
        Set-NetFirewallRule @ruleArgs | Out-Null
    } else {
        Save-EnablementChange 'NewFirewallRule' $name $Program
        New-NetFirewallRule @ruleArgs -Group $group -DisplayName "Tlamatini $Kind - $Program" | Out-Null
    }
    $effective = Get-NetFirewallRule -PolicyStore ActiveStore -Name $name -ErrorAction SilentlyContinue
    if (-not $effective -or $effective.Enabled -ne 'True' -or $effective.Action -ne 'Allow' -or $effective.Direction -ne $direction) {
        throw "Firewall rule is not effective: $name. Check local-policy merging and domain policy."
    }
    $app = $effective | Get-NetFirewallApplicationFilter -ErrorAction Stop
    $address = $effective | Get-NetFirewallAddressFilter -ErrorAction Stop
    $port = $effective | Get-NetFirewallPortFilter -ErrorAction Stop
    if (-not (Test-ExactProgram $app.Program $Program) -or $port.Protocol -ne 'Any' -or
        @(Compare-Object @($address.RemoteAddress) $remote).Count -gt 0 -or
        ([string]$effective.Profile -replace '\s','') -ne (($profile -join ',') -replace '\s','')) {
        throw "Firewall rule filters do not match requested access: $name"
    }
    Write-Host "  [OK] Effective $Kind allowance: $Program" -ForegroundColor Green
}

function Repair-ExactApplicationBlocks {
    param([object[]]$Rules, [string[]]$Programs)
    foreach ($rule in $Rules) {
        $app = $rule | Get-NetFirewallApplicationFilter -ErrorAction Stop
        $matched = @($Programs | Where-Object { Test-ExactProgram $app.Program $_ })
        if ($matched.Count -eq 0) {
            if ($app.Program -eq 'Any' -or -not $app.Program) {
                Write-EnablementWarning "Broad block '$($rule.DisplayName)' ($($rule.Name)) remains; allow rules cannot override a matching block. Review its address/port scope if networking fails."
            }
            continue
        }
        if ($rule.PolicyStoreSourceType -ne 'Local') {
            Write-EnablementWarning "Managed block '$($rule.Name)' for $($app.Program) requires your policy administrator; it was not changed."
            continue
        }
        $local = Get-NetFirewallRule -PolicyStore PersistentStore -Name $rule.Name -ErrorAction SilentlyContinue
        if (-not $local -or $local.Action -ne 'Block') { throw "Cannot identify a persistent local block: $($rule.Name)" }
        $localApp = $local | Get-NetFirewallApplicationFilter -ErrorAction Stop
        if (-not (Test-ExactProgram $localApp.Program $app.Program)) {
            throw "Local block changed since discovery: $($rule.Name); left unchanged."
        }
        Save-EnablementChange 'DisabledAppBlock' $rule.Name $app.Program
        Disable-NetFirewallRule -PolicyStore PersistentStore -Name $rule.Name -ErrorAction Stop | Out-Null
        $after = Get-NetFirewallRule -PolicyStore ActiveStore -Name $rule.Name -ErrorAction SilentlyContinue
        if ($after -and $after.Enabled -eq 'True') { throw "Block remains effective: $($rule.Name)" }
        Write-Host "  [OK] Disabled exact local app block: $($rule.Name) -> $($app.Program)" -ForegroundColor Green
    }
}
