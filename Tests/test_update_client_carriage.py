# Tlamatini Author Banner — Created by Angela López Mendoza · @angelahack1
"""Native filesystem checks of the actual update helpers, run in a visible console."""
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(os.name == "nt", "Windows update operations")
class NativeUpdateClientTests(unittest.TestCase):
    def test_real_removal_client_replacement_absence_and_windows_lock(self):
        executable = ROOT / "Uninstaller.exe"
        if not executable.is_file():
            self.skipTest("Build Uninstaller.exe to verify the compiled client")
        with tempfile.TemporaryDirectory() as temporary:
            case = Path(temporary)
            script = case / "check.ps1"
            script.write_text(r'''
param([string]$Updater, [string]$CaseRoot, [string]$Client)
$ErrorActionPreference = 'Stop'
$tokens=$null; $errors=$null
$ast=[Management.Automation.Language.Parser]::ParseFile($Updater,[ref]$tokens,[ref]$errors)
if($errors.Count){throw $errors[0]}
foreach($name in @('Invoke-WithRetry','Assert-NoReparseAncestors','Install-UpdateUninstaller')){
    $nodes=@($ast.FindAll({param($node) $node -is [Management.Automation.Language.FunctionDefinitionAst]},$false) | Where-Object Name -eq $name)
    if($nodes.Count -ne 1){throw "Expected the real updater function $name"}
    . ([scriptblock]::Create($nodes[0].Extent.Text))
}
$target=Join-Path $CaseRoot 'application'
$updates=Join-Path $target 'Temp\_update'
$staging=Join-Path $updates 'staging'
$null=New-Item -ItemType Directory -Path $staging
$old=Join-Path $target 'Uninstaller.exe'
$incoming=Join-Path $staging 'Uninstaller.exe'
[IO.File]::WriteAllText($old,'existing client')
Install-UpdateUninstaller -InstallDir $target -StagingDir $staging -UpdateRoot $updates
if([IO.File]::ReadAllText($old) -ne 'existing client'){throw 'Missing incoming client deleted the old one'}
Copy-Item -LiteralPath $Client -Destination $incoming
$lock=[IO.File]::Open($old,[IO.FileMode]::Open,[IO.FileAccess]::ReadWrite,[IO.FileShare]::None)
$failed=$false
try{
    try{Install-UpdateUninstaller -InstallDir $target -StagingDir $staging -UpdateRoot $updates}catch{$failed=$true}
}finally{$lock.Dispose()}
if(!$failed -or [IO.File]::ReadAllText($old) -ne 'existing client' -or !(Test-Path -LiteralPath $incoming)){throw 'Lock did not preserve both clients'}
Install-UpdateUninstaller -InstallDir $target -StagingDir $staging -UpdateRoot $updates
$sha=[Security.Cryptography.SHA256]::Create()
try{
    $actual=[BitConverter]::ToString($sha.ComputeHash([IO.File]::ReadAllBytes($old)))
    $expected=[BitConverter]::ToString($sha.ComputeHash([IO.File]::ReadAllBytes($Client)))
}finally{$sha.Dispose()}
if($actual -ne $expected -or (Test-Path -LiteralPath $incoming)){throw 'Delivered client differs from the real binary'}
Write-Output 'PASS actual Windows replacement, absent-client retention and locked-client recovery'
''', encoding="utf-8")
            subprocess.run(
                ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script),
                 "-Updater", str(ROOT / "apply_update.ps1"), "-CaseRoot", str(case), "-Client", str(executable)],
                check=True, timeout=40,
            )

    def test_staged_helper_removes_literal_cache_only(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "application"
            staging = root / "Temp/_update/staging"
            staging.mkdir(parents=True)
            helper = staging / "setup_recovery.py"
            shutil.copy2(ROOT / "setup_recovery.py", helper)
            (root / "Tlamatini.exe").write_bytes(b"installed marker")
            normal = root / "ms-playwright"
            normal.mkdir()
            (normal / "keep").write_bytes(b"normal browser")
            literal = Path("\\\\?\\" + str(root)) / "ms-playwright "
            literal.mkdir()
            (literal / "cache").write_bytes(b"old cache")
            sys.path.insert(0, str(ROOT))
            from setup_recovery import remove_tree
            self.addCleanup(remove_tree, literal)
            args = [sys.executable, "-I", "-B", "-S", str(helper), "--clean-update-browser-caches"]
            refused = subprocess.run([*args, str(Path(temporary))], capture_output=True)
            self.assertNotEqual(refused.returncode, 0)
            self.assertTrue(literal.exists())
            subprocess.run([*args, str(root)], check=True)
            self.assertFalse(literal.exists())
            self.assertEqual((normal / "keep").read_bytes(), b"normal browser")
