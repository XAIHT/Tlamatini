# Tlamatini Author Banner — Angela López Mendoza · @angelahack1
"""Uninstall regressions; run in a verified visible foreground console."""
import ctypes
from pathlib import Path
import shutil
import sys
import tempfile
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
        (self.temp / 'CreateShortcut.json').write_text('{}', encoding='utf-8')
        (self.temp / 'Uninstaller.exe').write_bytes(b'fixture')
        with patch.object(uninstall.os, 'remove', side_effect=PermissionError('locked')):
            with self.assertRaisesRegex(RuntimeError, 'Uninstaller.exe'):
                self.app()._remove_uninstall_support(str(self.temp))
        self.assertEqual(self.validate(self.temp), str(self.temp))

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
