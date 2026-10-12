# Tlamatini Author Banner — Angela López Mendoza · @angelahack1
"""Focused real-filesystem/Windows checks; launch from a visible -NoExit console.

No personal installation, production registry values or database is modified.
These are focused recovery checks, not complete compiled installation runs.
"""
import ctypes
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from setup_recovery import Recovery, checked_path, removal_files, removal_directories, setup_lock
from setup_windows import WindowsSnapshot, run_powershell

OUT = ROOT / "Temp/setup-lifecycle-checks"
OUT.mkdir(parents=True, exist_ok=True)


class RecoveryChecks(unittest.TestCase):
    def setUp(self):
        self.home = Path(tempfile.mkdtemp(prefix="case-", dir=OUT))
        self.target = self.home / "Tlamatini"
        self.target.mkdir()
        self.addCleanup(shutil.rmtree, self.home, True)

    def file(self, name, contents=b"original"):
        path = self.target / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(contents)
        return path

    def prepare(self, names):
        recovery = Recovery(self.target)
        recovery.prepare(names, windows=False)
        return recovery

    def test_replaced_and_new_files_roll_back(self):
        old = self.file("bin/application.exe")
        recovery = self.prepare(["bin/application.exe", "new/file.bin"])
        old.write_bytes(b"replacement")
        self.file("new/file.bin", b"new")
        recovery.rollback()
        self.assertEqual(old.read_bytes(), b"original")
        self.assertFalse((self.target / "new").exists())
        self.assertFalse(recovery.folder.exists())

    def test_interrupted_install_recovers_from_disk(self):
        old = self.file("application.exe")
        self.prepare(["application.exe"])
        old.write_bytes(b"partial replacement")
        fresh = Recovery(self.target)
        self.assertTrue(fresh.recover_previous())
        self.assertEqual(old.read_bytes(), b"original")

    def test_removed_files_roll_back(self):
        self.file("bin/áé 日本語.dat")
        recovery = self.prepare(["bin/áé 日本語.dat"])
        shutil.rmtree(self.target / "bin")
        recovery.rollback()
        self.assertEqual((self.target / "bin/áé 日本語.dat").read_bytes(), b"original")

    def test_removed_empty_directories_roll_back(self):
        (self.target / "application/empty/nested").mkdir(parents=True)
        (self.target / "agents/kept").mkdir(parents=True)
        names = removal_directories(self.target, ["agents"])
        self.assertNotIn("agents/kept", names)
        recovery = Recovery(self.target)
        recovery.prepare([], windows=False, restore_directories=names)
        shutil.rmtree(self.target / "application")
        recovery.rollback()
        self.assertTrue((self.target / "application/empty/nested").is_dir())

    def test_windows_target_casing_does_not_block_recovery(self):
        old = self.file("application.exe")
        self.prepare(["application.exe"])
        old.write_bytes(b"partial")
        self.assertTrue(Recovery(str(self.target).upper()).recover_previous())
        self.assertEqual(old.read_bytes(), b"original")

    def test_commit_keeps_replacement_and_discards_copy(self):
        old = self.file("app.exe")
        recovery = self.prepare(["app.exe"])
        old.write_bytes(b"replacement")
        self.assertEqual(recovery.commit(), "")
        self.assertEqual(old.read_bytes(), b"replacement")
        self.assertFalse(recovery.folder.exists())

    def test_corrupt_backup_stays_for_attention(self):
        old = self.file("app.exe")
        recovery = self.prepare(["app.exe"])
        (recovery.folder / "files/app.exe").write_bytes(b"damaged")
        old.unlink()
        with self.assertRaisesRegex(RuntimeError, "Recovery needs attention"):
            recovery.rollback()
        self.assertTrue(recovery.folder.exists())
        self.assertFalse(old.exists())

    def test_preserved_user_material_excluded_from_removal_plan(self):
        for name in ("agents/a/config.yaml", "Templates/code.c", "application/work.md", "Temp/scratch.txt", "app.exe"):
            self.file(name)
        names = removal_files(self.target, ["agents", "Templates", "application"])
        self.assertNotIn("agents/a/config.yaml", names)
        self.assertNotIn("Templates/code.c", names)
        self.assertIn("Temp/scratch.txt", names)
        self.assertIn("app.exe", names)

    def test_recovery_directory_cannot_be_overwritten(self):
        with self.assertRaises(RuntimeError):
            self.prepare(["Temp/.setup-recovery/journal.json"])

    def test_unsafe_paths_refused(self):
        for name in ("../other", "C:/other", "/absolute", "a\\b", "a/../b", "bad.", "a//b"):
            with self.subTest(name=name), self.assertRaises(ValueError):
                checked_path(self.target, name)

    def test_corrupt_package_stops_before_destination_mutation(self):
        from install import FancyInstaller
        package = self.home / "broken.zip"
        package.write_bytes(b"not a ZIP archive")
        destination = self.home / "never-created"
        errors = []
        class ImmediateRoot:
            def after(self, _delay, callback, *args):
                callback(*args)
        app = FancyInstaller.__new__(FancyInstaller)
        app.root = ImmediateRoot()
        app.zip_path = str(package)
        app._set_progress = lambda *_: None
        app._show_error = errors.append
        app._run_install(str(destination))
        self.assertEqual(len(errors), 1)
        self.assertIn("No installation files were changed", errors[0])
        self.assertIn("Extract the complete release again", errors[0])
        self.assertFalse(destination.exists())

    def test_recovery_progress_is_monotonic_and_finishes_after_preparation(self):
        self.file("existing.bin", b"a" * 4096)
        self.file("nested/other.bin", b"b" * 8192)
        progress = []
        recovery = Recovery(self.target, progress=progress.append)
        recovery.prepare(["existing.bin", "nested/other.bin", "new.bin"], windows=False)
        self.assertTrue(progress)
        self.assertEqual(progress, sorted(progress))
        self.assertEqual(progress[-1], 1)
        self.assertEqual(recovery.data["state"], "active")
        self.assertEqual((recovery.folder / "files/nested/other.bin").read_bytes(), b"b" * 8192)
        recovery.rollback()

    def test_insufficient_space_precedes_mutation(self):
        old = self.file("app.exe")
        with patch("setup_recovery.shutil.disk_usage", return_value=type("Disk", (), {"free": 0})()):
            with self.assertRaisesRegex(RuntimeError, "free disk space"):
                self.prepare(["app.exe"])
        self.assertEqual(old.read_bytes(), b"original")
        self.assertFalse(Recovery(self.target).folder.exists())

    def test_readonly_files_restore(self):
        old = self.file("app.exe")
        recovery = self.prepare(["app.exe"])
        old.write_bytes(b"replacement")
        old.chmod(0o444)
        recovery.rollback()
        self.assertEqual(old.read_bytes(), b"original")

    def test_file_lock_reports_error_and_retry_restores(self):
        old = self.file("app.exe")
        recovery = self.prepare(["app.exe"])
        old.write_bytes(b"replacement")
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.CreateFileW.argtypes = [ctypes.c_wchar_p, ctypes.c_ulong, ctypes.c_ulong, ctypes.c_void_p,
                                      ctypes.c_ulong, ctypes.c_ulong, ctypes.c_void_p]
        kernel.CreateFileW.restype = ctypes.c_void_p
        kernel.CloseHandle.argtypes = [ctypes.c_void_p]
        handle = kernel.CreateFileW(str(old), 0x80000000, 0, None, 3, 0, None)
        self.assertNotEqual(handle, ctypes.c_void_p(-1).value)
        try:
            with self.assertRaisesRegex(RuntimeError, "Recovery needs attention"):
                recovery.rollback()
        finally:
            kernel.CloseHandle(handle)
        Recovery(self.target).recover_previous()
        self.assertEqual(old.read_bytes(), b"original")

    def test_failed_preparation_never_changes_original(self):
        old = self.file("app.exe")
        with patch("setup_recovery.shutil.copy2", side_effect=PermissionError("test denial")), \
                patch("setup_recovery.FILE_ACCESS_RETRY_SECONDS", .1):
            with self.assertRaises(PermissionError):
                self.prepare(["app.exe"])
        self.assertEqual(old.read_bytes(), b"original")
        self.assertFalse(Recovery(self.target).folder.exists())

    def lock_file(self, path):
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.CreateFileW.argtypes = [ctypes.c_wchar_p, ctypes.c_ulong, ctypes.c_ulong, ctypes.c_void_p,
                                      ctypes.c_ulong, ctypes.c_ulong, ctypes.c_void_p]
        kernel.CreateFileW.restype = ctypes.c_void_p
        kernel.CloseHandle.argtypes = [ctypes.c_void_p]
        handle = kernel.CreateFileW(str(path), 0x80000000, 0, None, 3, 0, None)
        self.assertNotEqual(handle, ctypes.c_void_p(-1).value)
        return lambda: kernel.CloseHandle(handle)

    def test_locked_source_fails_before_any_recovery_copy(self):
        old = self.file("Temp/locked.tmp")
        release = self.lock_file(old)
        try:
            with patch("setup_recovery.FILE_ACCESS_RETRY_SECONDS", .2), \
                    patch("setup_recovery.shutil.copy2") as copied:
                started = time.monotonic()
                with self.assertRaisesRegex(PermissionError, "Close programs using this installation"):
                    self.prepare(["Temp/locked.tmp"])
                self.assertLess(time.monotonic() - started, 5)
                copied.assert_not_called()
                self.assertFalse(Recovery(self.target).folder.exists())
        finally:
            release()
        self.assertEqual(old.read_bytes(), b"original")

    def test_transient_source_lock_recovers_without_manual_retry(self):
        old = self.file("Temp/transient.tmp")
        release = self.lock_file(old)
        timer = threading.Timer(.4, release)
        timer.start()
        try:
            recovery = self.prepare(["Temp/transient.tmp"])
            self.assertEqual((recovery.folder / "files/Temp/transient.tmp").read_bytes(), b"original")
            recovery.rollback()
        finally:
            timer.join(timeout=5)

    def programs_key(self, owner):
        """Real native registry operations, scoped to this disposable test key."""
        import winreg
        from contextlib import ExitStack
        key_path = r"Software\XAIHT\Tlamatini\FileAssociationTests\SetupARP_" + self.home.name.replace("-", "_")
        product_path = r"Software\Microsoft\Windows\CurrentVersion\Uninstall\Tlamatini"
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, key_path) as key:
            if owner is not None:
                winreg.SetValueEx(key, "InstallLocation", 0, winreg.REG_SZ, owner)
        native_open, native_delete = winreg.OpenKey, winreg.DeleteKey
        def cleanup():
            try: native_delete(winreg.HKEY_CURRENT_USER, key_path)
            except FileNotFoundError: pass
        self.addCleanup(cleanup)
        stack = ExitStack()
        self.addCleanup(stack.close)
        stack.enter_context(patch("winreg.OpenKey", side_effect=lambda hive, path, *a: native_open(hive, key_path if path == product_path else path, *a)))
        stack.enter_context(patch("winreg.DeleteKey", side_effect=lambda hive, path, *a: native_delete(hive, key_path if path == product_path else path, *a)))
        return key_path

    def test_program_registration_removal_has_native_absence_postcondition(self):
        import winreg
        from uninstall import FancyUninstaller
        key_path = self.programs_key(str(self.target))
        FancyUninstaller._unregister_programs_entry(str(self.target))
        with self.assertRaises(FileNotFoundError):
            winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path)
        FancyUninstaller._unregister_programs_entry(str(self.target))

    def test_program_registration_missing_owner_is_not_false_success(self):
        import winreg
        from uninstall import FancyUninstaller
        key_path = self.programs_key(None)
        with self.assertRaisesRegex(RuntimeError, "no installation owner"):
            FancyUninstaller._unregister_programs_entry(str(self.target))
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path):
            pass

    def test_foreign_program_registration_is_preserved(self):
        import winreg
        from uninstall import FancyUninstaller
        key_path = self.programs_key(str(self.home / "other-installation"))
        FancyUninstaller._unregister_programs_entry(str(self.target))
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path) as key:
            self.assertEqual(winreg.QueryValueEx(key, "InstallLocation")[0], str(self.home / "other-installation"))

    def test_program_registration_remaining_after_delete_is_failure(self):
        from uninstall import FancyUninstaller
        self.programs_key(str(self.target))
        with patch("winreg.DeleteKey", return_value=None):
            with self.assertRaisesRegex(RuntimeError, "still reports"):
                FancyUninstaller._unregister_programs_entry(str(self.target))

    def test_journal_cannot_redirect_recovery_outside_target(self):
        recovery = self.prepare(["app.exe"])
        data = json.loads(recovery.journal.read_text())
        data["files"]["../outside.bin"] = {"existed": False}
        recovery.journal.write_text(json.dumps(data))
        with self.assertRaises(ValueError):
            Recovery(self.target).recover_previous()

    def test_mutex_refuses_concurrent_operation(self):
        outcomes = []
        def contender():
            try:
                with setup_lock():
                    outcomes.append("unsafe concurrent entry")
            except RuntimeError:
                outcomes.append("blocked")
        with setup_lock():
            thread = threading.Thread(target=contender)
            thread.start()
            thread.join(timeout=5)
            self.assertFalse(thread.is_alive())
        self.assertEqual(outcomes, ["blocked"])
        with setup_lock():
            pass

    def test_registry_and_shortcut_recovery_keeps_unrelated_values(self):
        import winreg
        base = r"Software\XAIHT\Tlamatini\FileAssociationTests\SetupRecovery_" + self.home.name.replace("-", "_")
        desktop = self.home / "test-desktop.lnk"
        desktop.write_bytes(b"old shortcut")
        class IsolatedSnapshot(WindowsSnapshot):
            TREES = (base+r"\App",)
            VALUES = [(base+r"\Shared", "Tlamatini")]
            desktop_shortcut = staticmethod(lambda: desktop)
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, base+r"\Shared") as key:
            winreg.SetValueEx(key, "OtherApplication", 0, winreg.REG_SZ, "keep")
            winreg.SetValueEx(key, "Tlamatini", 0, winreg.REG_SZ, "previous")
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, base+r"\App") as key:
            winreg.SetValueEx(key, "InstallLocation", 0, winreg.REG_SZ, "original")
        try:
            snapshot = IsolatedSnapshot(self.home)
            snapshot.capture()
            with winreg.CreateKey(winreg.HKEY_CURRENT_USER, base+r"\App\New") as key:
                winreg.SetValueEx(key, "NewValue", 0, winreg.REG_BINARY, b"binary")
            with winreg.CreateKey(winreg.HKEY_CURRENT_USER, base+r"\Shared") as key:
                winreg.SetValueEx(key, "Tlamatini", 0, winreg.REG_SZ, "replaced")
            desktop.write_bytes(b"new shortcut")
            snapshot.restore()
            self.assertEqual(snapshot._read_value(base+r"\Shared", "OtherApplication")["value"], "keep")
            self.assertEqual(snapshot._read_value(base+r"\Shared", "Tlamatini")["value"], "previous")
            self.assertEqual(snapshot._tree(base+r"\App")[""]["InstallLocation"]["value"], "original")
            self.assertNotIn("New", snapshot._tree(base+r"\App"))
            self.assertEqual(desktop.read_bytes(), b"old shortcut")
        finally:
            for leaf in (r"\App\New", r"\App", r"\Shared", ""):
                try:
                    winreg.DeleteKey(winreg.HKEY_CURRENT_USER, base+leaf)
                except FileNotFoundError:
                    pass

    def test_helper_failure_is_reported(self):
        script = self.home / "failure.ps1"
        script.write_text("Write-Error 'deliberate failure'; exit 7", encoding="utf-8")
        with self.assertRaisesRegex(RuntimeError, "failed"):
            run_powershell(script, timeout=10)

    def test_noninteractive_prompt_cannot_hang(self):
        script = self.home / "prompt.ps1"
        script.write_text("Read-Host 'must not wait'", encoding="utf-8")
        begin = time.monotonic()
        with self.assertRaises(RuntimeError):
            run_powershell(script, timeout=10)
        self.assertLess(time.monotonic()-begin, 10)

    def test_helper_timeout_stops_its_descendant(self):
        import psutil
        script = self.home / "timeout.ps1"
        pidfile = self.home / "child.pid"
        script.write_text("$p = Start-Process powershell -ArgumentList '-NoProfile -NonInteractive -Command Start-Sleep 90' -NoNewWindow -PassThru\n"
                          + "$p.Id | Set-Content -LiteralPath '" + str(pidfile).replace("'", "''") + "'\nStart-Sleep 90", encoding="utf-8")
        begin = time.monotonic()
        with self.assertRaisesRegex(RuntimeError, "exceeded"):
            run_powershell(script, timeout=4)
        self.assertLess(time.monotonic()-begin, 10)
        self.assertTrue(pidfile.is_file(), "Child fixture never started")
        pid = int(pidfile.read_text(encoding="utf-8-sig").strip())
        for _ in range(30):
            if not psutil.pid_exists(pid):
                break
            time.sleep(.1)
        self.assertFalse(psutil.pid_exists(pid), f"Helper child {pid} survived timeout")


if __name__ == "__main__":
    from markdown_canvas_visible import visible_console
    visible_console()
    unittest.main(verbosity=2)
