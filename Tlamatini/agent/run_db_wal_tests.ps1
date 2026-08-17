# Tlamatini — VISIBLE test runner for the DB Backup / Set DB (WAL) fix.
# Angela's rule: every automated test runs in a VISIBLE foreground window.
# Created for Angela Lopez Mendoza.
$ErrorActionPreference = 'Continue'
$proj = 'C:\Development\Tlamatini\Tlamatini'
$out  = 'C:\Development\Tlamatini\Temp\db_wal_test_result.txt'
Set-Location $proj

$py = 'python'
foreach ($cand in @('C:\Development\Tlamatini\venv\Scripts\python.exe',
                    'C:\Development\Tlamatini\Tlamatini\venv\Scripts\python.exe')) {
    if (Test-Path $cand) { $py = $cand; break }
}

$lines = New-Object System.Collections.Generic.List[string]
function Say($t) { Write-Host $t; $script:lines.Add($t) }

Say "==================================================================="
Say "  TLAMATINI - DB Backup database / Set DB  (WAL) - VISIBLE TESTS"
Say "  $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')   python: $py"
Say "==================================================================="

Say ""
Say "--- [1/3] ruff on the changed files ---------------------------------"
$ruff = & $py -m ruff check agent/sqlite_copy.py agent/views.py agent/test_db_backup_restore_wal.py manage.py tests_e2e/test_db_backup_set_visible.py 2>&1 | Out-String
Say $ruff
Say "ruff exit: $LASTEXITCODE"
$ruffOk = ($LASTEXITCODE -eq 0)

Say ""
Say "--- [2/3] NEW suite: agent.test_db_backup_restore_wal ----------------"
$new = & $py -m unittest -v agent.test_db_backup_restore_wal 2>&1 | Out-String
Say $new
$newOk = ($LASTEXITCODE -eq 0)
Say "new-suite exit: $LASTEXITCODE"

Say ""
Say "--- [3/3] REGRESSION: manage.py helpers + temp policy ----------------"
$other = & $py manage.py test agent.test_django_port_config agent.test_temp_dir_policy --verbosity 1 2>&1 | Out-String
Say $other
$otherOk = ($LASTEXITCODE -eq 0)
Say "other exit: $LASTEXITCODE"

Say ""
Say "==================================================================="
Say ("  ruff .............. " + $(if ($ruffOk)  {'PASS'} else {'FAIL'}))
Say ("  new WAL suite ..... " + $(if ($newOk)   {'PASS'} else {'FAIL'}))
Say ("  port + temp ....... " + $(if ($otherOk) {'PASS'} else {'FAIL'}))
Say ("  OVERALL ........... " + $(if ($ruffOk -and $newOk -and $otherOk) {'ALL GREEN'} else {'SOMETHING FAILED'}))
Say "==================================================================="

$lines -join "`r`n" | Set-Content -Path $out -Encoding UTF8
Write-Host ""
Write-Host "Result written to: $out"
