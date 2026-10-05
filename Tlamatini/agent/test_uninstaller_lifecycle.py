# Tlamatini Author Banner — Angela López Mendoza · @angelahack1
"""Uninstall regressions; run in a verified visible foreground console."""
import ctypes
import os
from pathlib import Path
import shutil
import sys
import tempfile
import time
import unittest
from unittest.mock import patch, Mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import uninstall  # noqa: E402 — the standalone release module is at the repository root.


class UninstallerLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.temp = Path(tempfile.mkdtemp(prefix="tlamatini-uninstall-test-"))
        self.addCleanup(shutil.rmtree, self.temp, True)

    def app(self):
        app = uninstall.FancyUninstaller.__new__(uninstall.FancyUninstaller)
        app._set_progress = lambda *args: None
        app.preserved_dirs = []
        return app

    @unittest.skipUnless(sys.platform == "win32", "Real Windows file locking")
    def test_locked_file_fails_then_retry_removes_it(self):
        file = self.temp / "locked.bin"
        file.write_bytes(b"release fixture")
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.CreateFileW.argtypes = [ctypes.c_wchar_p, ctypes.c_ulong,
                                     ctypes.c_ulong, ctypes.c_void_p,
                                     ctypes.c_ulong, ctypes.c_ulong, ctypes.c_void_p]
        kernel.CreateFileW.restype = ctypes.c_void_p
        kernel.CloseHandle.argtypes = [ctypes.c_void_p]
        handle = kernel.CreateFileW(str(file), 0x80000000, 0, None, 3, 0, None)
        self.assertNotEqual(handle, ctypes.c_void_p(-1).value)
        try:
            with self.assertRaisesRegex(RuntimeError, "could not be removed"):
                self.app()._remove_files(str(self.temp), 0, 1)
            self.assertTrue(file.exists())
        finally:
            kernel.CloseHandle(handle)
        self.app()._remove_files(str(self.temp), 0, 1)
        self.assertFalse(file.exists())

    def test_explicit_worker_target_is_used(self):
        with patch.object(sys, "argv", ["Uninstaller.exe", "--install-dir", str(self.temp)]):
            self.assertEqual(uninstall.FancyUninstaller._detect_install_path(), str(self.temp))

    def test_source_run_never_relocates(self):
        with patch.object(sys, "frozen", False, create=True):
            self.assertFalse(uninstall.relocate_installed_uninstaller())

    def validate(self, path):
        app = self.app()
        app.install_path = Mock(get=lambda: str(path))
        with patch.object(uninstall.messagebox, 'showerror'), patch.object(uninstall.messagebox, 'askyesno') as confirm:
            result = app._validate_path()
        confirm.assert_not_called()
        return result

    def test_unknown_folder_cannot_be_confirmed_for_deletion(self):
        self.assertIsNone(self.validate(self.temp))

    def test_drive_root_and_source_checkout_are_rejected(self):
        self.assertIsNone(self.validate(self.temp.anchor))
        (self.temp / 'Tlamatini.exe').touch()
        (self.temp / '.git').mkdir()
        self.assertIsNone(self.validate(self.temp))

    def test_installed_folder_is_accepted(self):
        (self.temp / 'Tlamatini.exe').touch()
        self.assertEqual(self.validate(self.temp), str(self.temp))

    def test_removal_keeps_retry_support_until_registry_cleanup_succeeds(self):
        (self.temp / 'CreateShortcut.json').write_text('{}', encoding='utf-8')
        (self.temp / 'Uninstaller.exe').write_bytes(b'fixture')
        (self.temp / 'unregister_flw.ps1').write_text('# fixture', encoding='utf-8')
        (self.temp / 'application.bin').write_bytes(b'fixture')
        app = self.app()
        app._remove_files(str(self.temp), 0, 1, keep_support=True)
        self.assertFalse((self.temp / 'application.bin').exists())
        self.assertTrue((self.temp / 'unregister_flw.ps1').exists())
        self.assertEqual(self.validate(self.temp), str(self.temp))
        app._remove_uninstall_support(str(self.temp))
        self.assertEqual(list(self.temp.iterdir()), [])

    def test_failed_worker_removal_keeps_installation_marker_for_retry(self):
        """Only a file Windows refuses to delete AND to move stops the run."""
        (self.temp / 'CreateShortcut.json').write_text('{}', encoding='utf-8')
        (self.temp / 'Uninstaller.exe').write_bytes(b'fixture')
        with patch.object(uninstall, 'SUPPORT_DELETE_RETRY_SECONDS', 0), \
             patch.object(uninstall.os, 'remove', side_effect=PermissionError('locked')), \
             patch.object(uninstall.os, 'replace', side_effect=PermissionError('locked')):
            with self.assertRaisesRegex(RuntimeError, 'Uninstaller.exe'):
                self.app()._remove_uninstall_support(str(self.temp))
        self.assertEqual(self.validate(self.temp), str(self.temp))

    # ── A file Windows still holds is moved aside, not reported as an error ──
    @staticmethod
    def _map_as_image(path):
        """Hold *path* the way Explorer/Settings do to show an EXE's icon.

        LoadLibraryEx(AS_IMAGE_RESOURCE | AS_DATAFILE) maps it as an image:
        DeleteFile then fails with WinError 5 while a rename still works.
        """
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.LoadLibraryExW.argtypes = [ctypes.c_wchar_p, ctypes.c_void_p, ctypes.c_ulong]
        kernel.LoadLibraryExW.restype = ctypes.c_void_p
        kernel.FreeLibrary.argtypes = [ctypes.c_void_p]
        handle = kernel.LoadLibraryExW(str(path), None, 0x20 | 0x02)
        return kernel, handle

    @unittest.skipUnless(sys.platform == "win32", "Real Windows image mapping")
    def test_uninstaller_held_by_windows_is_moved_aside_not_an_error(self):
        exe = self.temp / "Uninstaller.exe"
        shutil.copy2(sys.executable, exe)          # a real PE image
        (self.temp / "CreateShortcut.json").write_text("{}", encoding="utf-8")
        kernel, handle = self._map_as_image(exe)
        self.assertTrue(handle, "could not map the fixture as an image")
        app = self.app()
        try:
            with self.assertRaises(PermissionError):
                os.remove(exe)                     # the real lock is in place
            with patch.object(uninstall, "SUPPORT_DELETE_RETRY_SECONDS", 0.3):
                app._remove_uninstall_support(str(self.temp))
            self.assertFalse(exe.exists(), "the original name must be free now")
            self.assertEqual(app.deferred_files, ["Uninstaller.exe"])
            pending = Path(app.pending_dir)
            self.assertTrue(pending.name.startswith(uninstall.PENDING_PREFIX))
            self.assertTrue((pending / "Uninstaller.exe").exists())
            self.assertFalse((self.temp / "CreateShortcut.json").exists())
            self.assertIn("Uninstaller.exe", app._deferred_note())
        finally:
            kernel.FreeLibrary(handle)

    def test_running_image_is_never_moved(self):
        """A PyInstaller program re-reads its own EXE for every import."""
        exe = self.temp / "Uninstaller.exe"
        exe.write_bytes(b"fixture")
        own = os.path.normcase(os.path.abspath(exe))
        app = self.app()
        with patch.object(uninstall, "own_image_path", return_value=own), \
             patch.object(uninstall.os, "replace") as move:
            app._remove_uninstall_support(str(self.temp))
        move.assert_not_called()
        self.assertTrue(exe.exists())
        self.assertEqual(app.deferred_in_place, [str(exe)])
        self.assertEqual(getattr(app, "pending_dir", ""), "")

    def test_nothing_deferred_says_nothing(self):
        app = self.app()
        app.deferred_files, app.deferred_in_place = [], []
        self.assertEqual(app._deferred_note(), "")

    # ── The hidden cleanup that runs after the uninstaller closes ───────────
    def test_cleanup_refuses_anything_it_cannot_prove_is_ours(self):
        build = uninstall.build_cleanup_command
        self.assertEqual(build(trees=[str(self.temp)]), "")
        self.assertEqual(build(trees=["relative/" + uninstall.STAGING_PREFIX + "x"]), "")
        self.assertEqual(build(trees=[str(self.temp / (uninstall.STAGING_PREFIX + "%x%"))]), "")
        self.assertEqual(build(files=[str(self.temp / "config.json")]), "")

    def test_cleanup_deletes_recursively_only_its_own_folders(self):
        staging = self.temp / (uninstall.STAGING_PREFIX + "abc")
        pending = self.temp / "install" / (uninstall.PENDING_PREFIX + "def")
        install = self.temp / "install"
        line = uninstall.build_cleanup_command([str(staging), str(pending)], [], [str(install)])
        self.assertIn(f'rd /s /q "{staging}"', line)
        self.assertIn(f'rd /s /q "{pending}"', line)
        self.assertIn(f'rd "{install}"', line)
        self.assertNotIn(f'rd /s /q "{install}"', line)
        self.assertIn(f'if not exist "{staging}" if not exist "{pending}" exit', line)
        self.assertIn("ping -n 3 127.0.0.1", line)

    @unittest.skipUnless(sys.platform == "win32", "Real hidden cmd.exe cleanup")
    def test_cleanup_waits_for_the_lock_then_removes_everything(self):
        install = self.temp / "install"
        install.mkdir()
        pending = Path(tempfile.mkdtemp(prefix=uninstall.PENDING_PREFIX, dir=install))
        staging = Path(tempfile.mkdtemp(prefix=uninstall.STAGING_PREFIX, dir=self.temp))
        held = pending / "Uninstaller.exe"
        shutil.copy2(sys.executable, held)
        (staging / "Uninstaller.exe").write_bytes(b"temp copy")
        kernel, handle = self._map_as_image(held)
        self.assertTrue(handle)
        try:
            line = uninstall.build_cleanup_command(
                [str(staging), str(pending)], [], [str(install)], attempts=15)
            self.assertTrue(uninstall.schedule_cleanup(line))
            time.sleep(5)
            self.assertTrue(held.exists(), "a held file must survive until released")
            self.assertFalse(staging.exists(), "the free Temp copy goes at once")
        finally:
            kernel.FreeLibrary(handle)
        deadline = time.monotonic() + 20
        while install.exists() and time.monotonic() < deadline:
            time.sleep(0.5)
        self.assertFalse(pending.exists())
        self.assertFalse(install.exists(), "the emptied installation folder goes too")

    def test_relocation_failure_runs_in_place_instead_of_crashing(self):
        exe = self.temp / "Uninstaller.exe"
        exe.write_bytes(b"test binary")
        (self.temp / "Tlamatini.exe").write_bytes(b"test application")
        stage = self.temp.parent / (self.temp.name + "-failed-worker")
        stage.mkdir()
        self.addCleanup(shutil.rmtree, stage, True)
        with patch.object(sys, "frozen", True, create=True), \
             patch.object(sys, "platform", "win32"), \
             patch.object(sys, "executable", str(exe)), \
             patch.object(uninstall.tempfile, "mkdtemp", return_value=str(stage)), \
             patch.object(uninstall.shutil, "copy2", side_effect=OSError("disk full")):
            self.assertFalse(uninstall.relocate_installed_uninstaller())
        self.assertFalse(stage.exists(), "a failed relocation leaves no Temp folder")

    def test_only_the_relocated_copy_recognises_its_temp_folder(self):
        temp = Path(tempfile.gettempdir())
        inside = temp / (uninstall.STAGING_PREFIX + "zz") / "Uninstaller.exe"
        with patch.object(sys, "frozen", True, create=True), \
             patch.object(sys, "executable", str(inside)):
            self.assertEqual(os.path.normcase(uninstall.relocated_staging_dir()),
                             os.path.normcase(os.path.realpath(inside.parent)))
        with patch.object(sys, "frozen", True, create=True), \
             patch.object(sys, "executable", str(self.temp / "Uninstaller.exe")):
            self.assertEqual(uninstall.relocated_staging_dir(), "")
        with patch.object(sys, "frozen", False, create=True):
            self.assertEqual(uninstall.relocated_staging_dir(), "")

    def test_sweep_removes_only_old_leftover_temp_copies(self):
        old = self.temp / (uninstall.STAGING_PREFIX + "old")
        new = self.temp / (uninstall.STAGING_PREFIX + "new")
        other = self.temp / "someone-elses-folder"
        for folder in (old, new, other):
            folder.mkdir()
            (folder / "Uninstaller.exe").write_bytes(b"x")
        ancient = time.time() - 2 * uninstall.STALE_STAGING_SECONDS
        os.utime(old, (ancient, ancient))
        os.utime(other, (ancient, ancient))
        with patch.object(uninstall.tempfile, "gettempdir", return_value=str(self.temp)):
            uninstall.sweep_stale_staging()
        self.assertFalse(old.exists())
        self.assertTrue(new.exists(), "a copy that may still be running is kept")
        self.assertTrue(other.exists(), "never anything without our prefix")

    @unittest.skipUnless(sys.platform == 'win32', 'Windows registry')
    def test_denied_registry_removal_reports_incomplete_uninstall(self):
        import winreg
        with patch.object(winreg, 'OpenKey'), \
             patch.object(winreg, 'QueryValueEx', return_value=(str(self.temp), winreg.REG_SZ)), \
             patch.object(winreg, 'DeleteKey', side_effect=PermissionError('denied')):
            with self.assertRaisesRegex(RuntimeError, 'Installed-apps entry'):
                uninstall.FancyUninstaller._unregister_programs_entry(str(self.temp))

    def test_frozen_worker_uses_independent_bootloader_and_original_target(self):
        exe = self.temp / "Uninstaller.exe"
        exe.write_bytes(b"test binary")
        (self.temp / "Tlamatini.exe").write_bytes(b"test application")
        stage = self.temp.parent / (self.temp.name + "-worker")
        stage.mkdir()
        self.addCleanup(shutil.rmtree, stage, True)
        with patch.object(sys, "frozen", True, create=True), \
             patch.object(sys, "platform", "win32"), \
             patch.object(sys, "executable", str(exe)), \
             patch.object(uninstall.tempfile, "mkdtemp", return_value=str(stage)), \
             patch.object(uninstall.subprocess, "Popen") as launch:
            self.assertTrue(uninstall.relocate_installed_uninstaller())
        self.assertEqual((stage / exe.name).read_bytes(), exe.read_bytes())
        self.assertEqual(launch.call_args.args[0], [str(stage / exe.name), "--install-dir", str(self.temp)])
        self.assertEqual(launch.call_args.kwargs["env"]["PYINSTALLER_RESET_ENVIRONMENT"], "1")

    @unittest.skipUnless(sys.platform == "win32", "Windows registry")
    def test_foreign_installed_apps_owner_is_not_removed(self):
        import winreg
        with patch.object(winreg, "OpenKey"), \
             patch.object(winreg, "QueryValueEx", return_value=("C:/Another Tlamatini", winreg.REG_SZ)), \
             patch.object(winreg, "DeleteKey") as remove:
            uninstall.FancyUninstaller._unregister_programs_entry(str(self.temp))
        remove.assert_not_called()

    @unittest.skipUnless(sys.platform == "win32", "Windows registry")
    def test_own_installed_apps_owner_is_removed(self):
        import winreg
        with patch.object(winreg, "OpenKey"), \
             patch.object(winreg, "QueryValueEx", return_value=(str(self.temp), winreg.REG_SZ)), \
             patch.object(winreg, "DeleteKey") as remove:
            uninstall.FancyUninstaller._unregister_programs_entry(str(self.temp))
        remove.assert_called_once()
