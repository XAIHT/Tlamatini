"""The release build must not die on the build machine's clutter (2026-10-21).

Run in a visible foreground development console.

Copyright Angela López Mendoza · @angelahack1 — Tlamatini Author Banner.
"""
import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location("guard_under_test", ROOT / "pyinstaller_guard.py")
guard = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(guard)


def _locked(*_args, **_kwargs):
    raise PermissionError(13, "Permission denied (held by another program)")


class HermeticProfileTests(unittest.TestCase):
    def test_every_profile_variable_points_at_an_empty_build_folder(self):
        with tempfile.TemporaryDirectory() as temporary:
            env = {"JUPYTER_PATH": r"C:\Users\someone\jupyter", "JUPYTER_CONFIG_PATH": "x"}
            root = guard.apply_hermetic_profile(env, Path(temporary) / "profile")
            for var in guard.PROFILE_DIR_VARS:
                folder = Path(env[var])
                self.assertTrue(folder.is_dir(), var)
                self.assertEqual(list(folder.iterdir()), [], var)
                self.assertEqual(folder.parent, root)
            for var in guard.PROFILE_PATH_VARS:
                self.assertNotIn(var, env)
            self.assertEqual(env["JUPYTER_NO_CONFIG"], "1")


class LockedFileGuardTests(unittest.TestCase):
    def setUp(self):
        guard._skipped.clear()
        self.temporary = tempfile.TemporaryDirectory()
        base = Path(self.temporary.name)
        self.trusted = base / "trusted"
        self.foreign = base / "foreign"
        self.dist = base / "dist"
        for folder in (self.trusted, self.foreign, self.dist):
            folder.mkdir()
        patches = (
            patch.object(guard, "trusted_roots", lambda: (guard._norm(self.trusted),)),
            patch.object(guard.time, "sleep", lambda _seconds: None),
        )
        for active in patches:
            active.start()
            self.addCleanup(active.stop)
        self.addCleanup(self.temporary.cleanup)
        self.addCleanup(guard._skipped.clear)

    def test_a_locked_foreign_file_is_skipped_named_and_never_shipped(self):
        src = self.foreign / "jpserver-11572-open.html"
        src.write_text("live server page")
        dst = self.dist / "share" / "jupyter" / "runtime" / src.name
        with patch.object(guard, "_ORIGINAL_COPYFILE", _locked):
            self.assertEqual(guard.guarded_copyfile(src, dst), dst)
        self.assertTrue(dst.is_file(), "PyInstaller chmods what it copied: a stand-in must exist")
        self.assertEqual([entry[0] for entry in guard._skipped], [str(src)])
        guard.remove_placeholders()
        self.assertFalse(dst.exists(), "the empty stand-in must not ship")

    def test_a_locked_file_the_build_needs_fails_loudly_and_names_itself(self):
        src = self.trusted / "templates" / "agent_page.html"
        src.parent.mkdir()
        src.write_text("needed")
        calls = []

        def locked(*args, **kwargs):
            calls.append(args)
            _locked()

        with patch.object(guard, "_ORIGINAL_COPYFILE", locked):
            with self.assertRaises(PermissionError) as raised:
                guard.guarded_copyfile(src, self.dist / "agent_page.html")
        self.assertIn(str(src), str(raised.exception))
        self.assertEqual(len(calls), guard.LOCK_RETRIES, "a lock is waited out first")
        self.assertEqual(guard._skipped, [])

    def test_a_brief_lock_is_waited_out_and_the_file_is_copied(self):
        src = self.trusted / "data.json"
        src.write_text("{}")
        dst = self.dist / "data.json"
        attempts = []
        original = guard._ORIGINAL_COPYFILE

        def flaky(source, destination, *args, **kwargs):
            attempts.append(source)
            if len(attempts) < 3:
                _locked()
            return original(source, destination, *args, **kwargs)

        with patch.object(guard, "_ORIGINAL_COPYFILE", flaky):
            guard.guarded_copyfile(src, dst)
        self.assertEqual(dst.read_text(), "{}")
        self.assertEqual(len(attempts), 3)

    def test_errors_that_are_not_locks_are_never_retried_or_hidden(self):
        missing = self.foreign / "gone.txt"
        attempts = []
        original = guard._ORIGINAL_COPYFILE

        def counting(*args, **kwargs):
            attempts.append(args)
            return original(*args, **kwargs)

        with patch.object(guard, "_ORIGINAL_COPYFILE", counting):
            with self.assertRaises(FileNotFoundError):
                guard.guarded_copyfile(missing, self.dist / "gone.txt")
        self.assertEqual(len(attempts), 1)
        self.assertEqual(guard._skipped, [])


class WiringTests(unittest.TestCase):
    def test_every_release_pyinstaller_run_goes_through_the_guard(self):
        for name in ("build.py", "build_installer.py", "build_uninstaller.py"):
            source = (ROOT / name).read_text(encoding="utf-8")
            self.assertIn("from pyinstaller_guard import pyinstaller_command", source, name)
            self.assertIn("*pyinstaller_command(),", source, name)
            self.assertNotIn("'-m', 'PyInstaller'", source, name)
            self.assertNotIn('"-m", "PyInstaller"', source, name)

    def test_the_jupyter_family_is_excluded_from_the_frozen_app(self):
        source = (ROOT / "build.py").read_text(encoding="utf-8")
        self.assertIn(
            "*(f'--exclude-module={module}' for module in _FROZEN_JUPYTER_MODULES),", source)
        for module in ("notebook", "nbconvert", "jupyter_server", "jupyterlab"):
            self.assertIn(f'"{module}"', source.split("_FROZEN_JUPYTER_MODULES = (", 1)[1]
                          .split(")", 1)[0], module)

    def test_the_guard_runs_pyinstaller_from_its_own_file(self):
        command = guard.pyinstaller_command()
        self.assertEqual(command[0], sys.executable)
        self.assertEqual(Path(command[1]), ROOT / "pyinstaller_guard.py")

    def test_the_self_modify_snapshot_can_rebuild_with_the_guard(self):
        source = (ROOT / "copy_source_assets.py").read_text(encoding="utf-8")
        self.assertIn('    "pyinstaller_guard.py",', source)


if __name__ == "__main__":
    unittest.main()
