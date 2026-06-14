# Tlamatini Auto-Updater
# =====================================================================
# Runs OUTSIDE the install directory (a copy is placed under
# %LOCALAPPDATA%\Tlamatini\updater by self_update.py) so it can safely
# replace the whole install — including python\, jre\, git\ and
# Tlamatini.exe — without locking the files it is overwriting.
#
# Sequence:
#   1. Validate the staged new build (must contain Tlamatini.exe).
#   2. Close the running Tlamatini (and its child processes).
#   3. Rename agents -> agents_backup (keeping ONE backup generation).
#   4. Delete the old install EXCEPT the preserved user-data set.
#   5. Move the new build in EXCEPT the preserved set (so the user's
#      config.json / DB / etc. are never overwritten).
#   6. Relaunch the new Tlamatini.
#
# It is launched by agent/self_update.py — do not run it by hand.
# =====================================================================

param(
    [Parameter(Mandatory = $true)][string]$InstallDir,
    [Parameter(Mandatory = $true)][string]$StagingDir,
    [Parameter(Mandatory = $true)][int]$ParentPid,
    [string]$RelaunchExe = "",
    [string]$LogPath = ""
)

$ErrorActionPreference = "Stop"
try { $Host.UI.RawUI.WindowTitle = "Tlamatini Updater" } catch {}

# Top-level names in the install root that must NEVER be deleted or
# overwritten. 'agents' is intentionally NOT here: it is renamed to
# 'agents_backup' (step 3) and then replaced by the new version (step 5).
$Preserve = @(
    'config.json', 'DB', 'application', 'applications', 'content_generated',
    'Temp', 'context_files', 'doc_generated', 'documentation', 'Templates'
)

function Write-Log {
    param([string]$Message, [string]$Color = "Gray")
    $line = "[{0}] {1}" -f (Get-Date -Format "HH:mm:ss"), $Message
    try { Write-Host $line -ForegroundColor $Color } catch { Write-Host $line }
    if ($LogPath) { try { Add-Content -Path $LogPath -Value $line -Encoding UTF8 } catch {} }
}

function Invoke-WithRetry {
    # Windows can hold file handles for a moment after a process dies, so
    # delete/rename/move operations are retried instead of failing outright.
    param([scriptblock]$Action, [int]$Attempts = 15, [int]$DelayMs = 600)
    for ($i = 1; $i -le $Attempts; $i++) {
        try { & $Action; return }
        catch {
            if ($i -eq $Attempts) { throw }
            Start-Sleep -Milliseconds $DelayMs
        }
    }
}

function Test-Preserved {
    param([string]$Name)
    foreach ($p in $Preserve) { if ($Name -ieq $p) { return $true } }
    return $false
}

Write-Host ""
Write-Host "  ==================================================" -ForegroundColor Cyan
Write-Host "         TLAMATINI  --  APPLYING UPDATE" -ForegroundColor Cyan
Write-Host "  ==================================================" -ForegroundColor Cyan
Write-Host ""
Write-Log "Install dir : $InstallDir"
Write-Log "Staging dir : $StagingDir"
Write-Log "Parent PID  : $ParentPid"
Write-Host ""

try {
    # 1) Validate the staged new version BEFORE touching anything.
    $newExe = Join-Path $StagingDir "Tlamatini.exe"
    if (-not (Test-Path -LiteralPath $newExe)) {
        throw "Staged update is invalid -- Tlamatini.exe not found at '$newExe'. Aborting; nothing was changed."
    }
    if (-not (Test-Path -LiteralPath $InstallDir)) {
        throw "Install directory '$InstallDir' does not exist. Aborting."
    }
    Write-Log "Staged build validated (Tlamatini.exe present)." "Green"

    # 2) Close the running Tlamatini and its whole process tree.
    Write-Log "Closing Tlamatini (PID $ParentPid) and its child processes..."
    Start-Sleep -Seconds 2
    try { & taskkill.exe /PID $ParentPid /T /F 2>&1 | Out-Null } catch {}
    # Let Windows release the file handles (python\, git\, jre\, exe).
    Start-Sleep -Seconds 3
    Write-Log "Tlamatini closed." "Green"

    # 3) Back up the old agents directory: agents -> agents_backup.
    $agentsDir = Join-Path $InstallDir "agents"
    $agentsBak = Join-Path $InstallDir "agents_backup"
    if (Test-Path -LiteralPath $agentsDir) {
        if (Test-Path -LiteralPath $agentsBak) {
            Write-Log "Removing previous agents_backup..."
            Invoke-WithRetry { Remove-Item -LiteralPath $agentsBak -Recurse -Force }
        }
        Write-Log "Renaming agents -> agents_backup ..."
        Invoke-WithRetry { Rename-Item -LiteralPath $agentsDir -NewName "agents_backup" }
        Write-Log "Old agents backed up to 'agents_backup'." "Green"
    }
    else {
        Write-Log "No existing 'agents' directory to back up." "Yellow"
    }

    # 4) Delete the old install -- everything except the preserved set and
    #    the agents_backup we just created.
    Write-Log "Removing old application files (keeping your data)..."
    Get-ChildItem -LiteralPath $InstallDir -Force | ForEach-Object {
        $name = $_.Name
        if ($name -ieq "agents_backup") { return }
        if (Test-Preserved $name) { Write-Log "  keep    $name"; return }
        $full = $_.FullName
        Write-Log "  remove  $name"
        Invoke-WithRetry { Remove-Item -LiteralPath $full -Recurse -Force }
    }

    # 5) Move the new version in -- everything except the preserved set, so
    #    the user's config.json / DB / runtime dirs are never overwritten.
    Write-Log "Installing the new version..."
    Get-ChildItem -LiteralPath $StagingDir -Force | ForEach-Object {
        $name = $_.Name
        if (Test-Preserved $name) { Write-Log "  skip    $name (kept yours)"; return }
        $src = $_.FullName
        $dest = Join-Path $InstallDir $name
        if (Test-Path -LiteralPath $dest) {
            Invoke-WithRetry { Remove-Item -LiteralPath $dest -Recurse -Force }
        }
        Write-Log "  install $name"
        Invoke-WithRetry { Move-Item -LiteralPath $src -Destination $dest -Force }
    }

    # 6) Clean up the staging area (best effort).
    try {
        $updateRoot = Split-Path -Parent $StagingDir
        if ($updateRoot -and (Test-Path -LiteralPath $updateRoot)) {
            Remove-Item -LiteralPath $updateRoot -Recurse -Force -ErrorAction SilentlyContinue
        }
    }
    catch {}

    Write-Host ""
    Write-Log "UPDATE COMPLETE." "Green"

    # 7) Relaunch Tlamatini.
    if (-not $RelaunchExe) { $RelaunchExe = Join-Path $InstallDir "Tlamatini.exe" }
    if (Test-Path -LiteralPath $RelaunchExe) {
        Write-Log "Starting the new Tlamatini..." "Cyan"
        Start-Process -FilePath $RelaunchExe -WorkingDirectory $InstallDir
    }
    else {
        Write-Log "Tlamatini.exe not found after update -- please start it manually." "Yellow"
    }
    Start-Sleep -Seconds 4
    exit 0
}
catch {
    Write-Host ""
    Write-Log "UPDATE FAILED: $($_.Exception.Message)" "Red"
    Write-Log "Your previous agents are preserved in 'agents_backup'." "Yellow"
    if ($LogPath) { Write-Log "Full log: $LogPath" "Yellow" }
    Write-Host ""
    try { Read-Host "Press Enter to close" } catch {}
    exit 1
}
