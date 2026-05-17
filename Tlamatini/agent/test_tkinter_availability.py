"""
Tests for tkinter availability and the native file-picker infrastructure.

Covers:
- tkinter importability in both source and frozen (simulated) modes
- Tcl/Tk runtime data directory presence
- _tkinter C extension availability
- _run_native_picker() contract (threading, queue, error propagation)
- PyInstaller build.py hidden-import declarations
- build_installer.py TCL_LIBRARY / TK_LIBRARY env-var resolution
- The picker view endpoints (pick_db_sqlite_file, pick_backup_directory)
- Windows 10 / Windows 11 parity (same codepath, no OS-version branches)

Run:
    python manage.py test agent.test_tkinter_availability
"""

import importlib
import importlib.util
import os
import platform
import sys
import threading
from pathlib import Path
from unittest.mock import MagicMock, patch

from django.test import TestCase, Client
from django.contrib.auth.models import User


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_IS_WINDOWS = sys.platform == 'win32'
_WINDOWS_VERSION = ''
if _IS_WINDOWS:
    _ver = platform.version()          # e.g. '10.0.19045' or '10.0.22631'
    _build = int(_ver.split('.')[-1]) if _ver.count('.') >= 2 else 0
    # Build 22000+ is Windows 11
    _WINDOWS_VERSION = 'win11' if _build >= 22000 else 'win10'


def _build_py_path() -> Path:
    """Return the absolute path to the repository-root build.py."""
    return Path(__file__).resolve().parents[2] / 'build.py'


def _build_installer_py_path() -> Path:
    return Path(__file__).resolve().parents[2] / 'build_installer.py'


# ═══════════════════════════════════════════════════════════════════════════
# 1. Tkinter import availability
# ═══════════════════════════════════════════════════════════════════════════

class TkinterImportTests(TestCase):
    """Verify that tkinter and its C extension are importable."""

    def test_tkinter_module_importable(self):
        """The pure-Python tkinter package must be importable."""
        spec = importlib.util.find_spec('tkinter')
        self.assertIsNotNone(
            spec,
            "tkinter is not importable — on Windows this means either the "
            "'tcl/tk and IDLE' optional component was not selected during "
            "Python installation, or the frozen build is missing "
            "'--hidden-import=tkinter' in build.py.",
        )

    def test_tkinter_c_extension_importable(self):
        """_tkinter (the C extension that bridges CPython to Tcl/Tk) must
        be importable. Without it, `import tkinter` succeeds but
        `tkinter.Tk()` raises."""
        spec = importlib.util.find_spec('_tkinter')
        self.assertIsNotNone(
            spec,
            "_tkinter C extension is not importable — on frozen builds "
            "this requires '--hidden-import=_tkinter' in build.py so "
            "PyInstaller's hook-_tkinter.py fires and bundles the DLL.",
        )

    def test_tkinter_actually_imports(self):
        """Full import (not just spec lookup) must succeed."""
        try:
            import tkinter  # noqa: F401
        except ImportError as exc:
            self.fail(f"import tkinter raised ImportError: {exc}")

    def test_tkinter_filedialog_importable(self):
        """The filedialog submodule is what _run_native_picker uses."""
        try:
            from tkinter import filedialog  # noqa: F401
        except ImportError as exc:
            self.fail(f"from tkinter import filedialog raised: {exc}")

    def test_tkinter_constants_available(self):
        """Sanity-check that Tcl/Tk version constants are populated."""
        import _tkinter
        self.assertTrue(
            hasattr(_tkinter, 'TK_VERSION'),
            "_tkinter.TK_VERSION is missing — the C extension loaded "
            "but Tcl/Tk runtime data may not be bundled.",
        )
        self.assertTrue(
            hasattr(_tkinter, 'TCL_VERSION'),
            "_tkinter.TCL_VERSION is missing.",
        )


# ═══════════════════════════════════════════════════════════════════════════
# 2. Tcl/Tk runtime data directories
# ═══════════════════════════════════════════════════════════════════════════

class TclTkDataDirectoryTests(TestCase):
    """Verify that the Tcl/Tk data directories are resolvable.

    In source mode these live under the Python prefix (e.g.
    ``C:\\Python312\\tcl\\tcl8.6``). In frozen mode PyInstaller's
    hook-_tkinter places them inside ``_internal/`` next to the .exe.
    """

    def test_tcl_library_directory_exists(self):
        """The Tcl library directory must exist at runtime."""
        import tkinter
        tcl = tkinter.Tcl()
        tcl_lib = tcl.eval('info library')
        self.assertTrue(
            os.path.isdir(tcl_lib),
            f"Tcl library directory does not exist: {tcl_lib} — "
            f"tkinter.Tk() will fail with 'can't find a usable init.tcl'.",
        )

    def test_tk_library_directory_exists(self):
        """The Tk library directory (sibling of the Tcl directory) must
        exist for widgets / file dialogs to work."""
        import tkinter
        import _tkinter
        tcl = tkinter.Tcl()
        tcl_lib = Path(tcl.eval('info library'))
        tk_dir = tcl_lib.parent / f'tk{_tkinter.TK_VERSION}'
        self.assertTrue(
            tk_dir.is_dir(),
            f"Tk library directory does not exist: {tk_dir} — "
            f"file dialogs will crash.",
        )

    def test_init_tcl_present(self):
        """init.tcl must exist inside the Tcl library directory — it is
        the first file the Tcl interpreter sources on startup."""
        import tkinter
        tcl = tkinter.Tcl()
        init_tcl = Path(tcl.eval('info library')) / 'init.tcl'
        self.assertTrue(
            init_tcl.is_file(),
            f"init.tcl not found at {init_tcl}. Tcl/Tk data was not "
            f"bundled correctly.",
        )


# ═══════════════════════════════════════════════════════════════════════════
# 3. _run_native_picker contract tests (mocked — no real GUI)
# ═══════════════════════════════════════════════════════════════════════════

class NativePickerContractTests(TestCase):
    """Test the _run_native_picker helper in views.py without opening a
    real Tk window.  We mock tkinter so the tests run headless / in CI."""

    def _get_picker(self):
        from agent.views import _run_native_picker
        return _run_native_picker

    # -- directory picker --------------------------------------------------

    @patch('tkinter.Tk')
    @patch('tkinter.filedialog.askdirectory', return_value='C:/Backups')
    def test_directory_picker_returns_chosen_path(self, mock_ask, mock_tk):
        mock_tk.return_value = MagicMock()
        result = self._get_picker()('directory', 'Pick a folder')
        self.assertEqual(result, 'C:/Backups')
        mock_ask.assert_called_once()

    @patch('tkinter.Tk')
    @patch('tkinter.filedialog.askdirectory', return_value='')
    def test_directory_picker_returns_empty_on_cancel(self, mock_ask, mock_tk):
        mock_tk.return_value = MagicMock()
        result = self._get_picker()('directory', 'Pick a folder')
        self.assertEqual(result, '')

    # -- db_sqlite_file picker ---------------------------------------------

    @patch('tkinter.Tk')
    @patch('tkinter.filedialog.askopenfilename',
           return_value='D:/data/db.sqlite3')
    def test_db_file_picker_returns_chosen_path(self, mock_ask, mock_tk):
        mock_tk.return_value = MagicMock()
        result = self._get_picker()('db_sqlite_file', 'Pick db')
        self.assertEqual(result, 'D:/data/db.sqlite3')

    @patch('tkinter.Tk')
    @patch('tkinter.filedialog.askopenfilename', return_value='')
    def test_db_file_picker_returns_empty_on_cancel(self, mock_ask, mock_tk):
        mock_tk.return_value = MagicMock()
        result = self._get_picker()('db_sqlite_file', 'Pick db')
        self.assertEqual(result, '')

    # -- error propagation -------------------------------------------------

    def test_unknown_kind_raises_runtime_error(self):
        """An unknown ``kind`` must raise RuntimeError (not silently
        return empty)."""
        with self.assertRaises(RuntimeError):
            self._get_picker()('bogus_kind', 'title')

    def test_import_error_propagates_as_runtime_error(self):
        """If tkinter is not available (frozen build without the fix),
        the RuntimeError message must mention the module name so the
        frontend can show a useful alert."""
        import builtins
        _real_import = builtins.__import__

        def _fake_import(name, *args, **kwargs):
            if name == 'tkinter':
                raise ImportError("No module named 'tkinter'")
            return _real_import(name, *args, **kwargs)

        with patch('builtins.__import__', side_effect=_fake_import):
            with self.assertRaises(RuntimeError) as ctx:
                self._get_picker()('directory', 'title')
            self.assertIn('tkinter', str(ctx.exception))

    # -- threading contract ------------------------------------------------

    def test_picker_runs_in_a_dedicated_thread(self):
        """The picker MUST run in a daemon thread named
        'tlamatini-native-picker' so it doesn't block Daphne's event
        loop on Windows."""
        captured_thread = {}

        real_thread_init = threading.Thread.__init__

        def spy_init(self_t, *a, **kw):
            real_thread_init(self_t, *a, **kw)
            if self_t.name == 'tlamatini-native-picker':
                captured_thread['daemon'] = self_t.daemon
                captured_thread['name'] = self_t.name

        with patch.object(threading.Thread, '__init__', spy_init):
            with patch('tkinter.Tk') as mock_tk:
                with patch('tkinter.filedialog.askdirectory', return_value=''):
                    mock_tk.return_value = MagicMock()
                    self._get_picker()('directory', 'title')

        self.assertEqual(captured_thread.get('name'), 'tlamatini-native-picker')
        self.assertTrue(
            captured_thread.get('daemon'),
            "Picker thread must be a daemon thread.",
        )


# ═══════════════════════════════════════════════════════════════════════════
# 4. Picker view endpoint tests
# ═══════════════════════════════════════════════════════════════════════════

class PickerViewEndpointTests(TestCase):
    """Test the HTTP endpoints that the Browse buttons call."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user = User.objects.create_user(
            username='picker_test_user', password='testpass123',
        )

    def setUp(self):
        self.client = Client()
        self.client.login(username='picker_test_user', password='testpass123')

    # -- pick_db_sqlite_file -----------------------------------------------

    @patch('agent.views._run_native_picker', return_value='C:/data/db.sqlite3')
    def test_pick_db_file_returns_json_path(self, mock_picker):
        resp = self.client.get('/agent/pick_db_sqlite_file/')
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn('path', data)
        self.assertTrue(data['path'].endswith('db.sqlite3'))

    @patch('agent.views._run_native_picker', return_value='')
    def test_pick_db_file_canceled_returns_empty(self, mock_picker):
        resp = self.client.get('/agent/pick_db_sqlite_file/')
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data['path'], '')
        self.assertTrue(data.get('canceled', False))

    @patch('agent.views._run_native_picker',
           side_effect=RuntimeError("No module named 'tkinter'"))
    def test_pick_db_file_error_returns_error_field(self, mock_picker):
        resp = self.client.get('/agent/pick_db_sqlite_file/')
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn('error', data)
        self.assertIn('tkinter', data['error'])

    # -- pick_backup_directory ---------------------------------------------

    @patch('agent.views._run_native_picker', return_value='C:/Backups')
    def test_pick_backup_dir_returns_json_path(self, mock_picker):
        resp = self.client.get('/agent/pick_backup_directory/')
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn('path', data)
        self.assertIn('Backups', data['path'])

    @patch('agent.views._run_native_picker', return_value='')
    def test_pick_backup_dir_canceled(self, mock_picker):
        resp = self.client.get('/agent/pick_backup_directory/')
        data = resp.json()
        self.assertEqual(data['path'], '')
        self.assertTrue(data.get('canceled', False))

    @patch('agent.views._run_native_picker',
           side_effect=RuntimeError("tkinter unavailable"))
    def test_pick_backup_dir_error(self, mock_picker):
        resp = self.client.get('/agent/pick_backup_directory/')
        data = resp.json()
        self.assertIn('error', data)

    # -- auth required -----------------------------------------------------

    def test_pick_db_file_requires_login(self):
        anon = Client()
        resp = anon.get('/agent/pick_db_sqlite_file/')
        # Should redirect to login
        self.assertIn(resp.status_code, (301, 302))

    def test_pick_backup_dir_requires_login(self):
        anon = Client()
        resp = anon.get('/agent/pick_backup_directory/')
        self.assertIn(resp.status_code, (301, 302))


# ═══════════════════════════════════════════════════════════════════════════
# 5. build.py declares tkinter hidden-imports
# ═══════════════════════════════════════════════════════════════════════════

class BuildPyTkinterDeclarationTests(TestCase):
    """Parse build.py as an AST and verify that the PyInstaller command
    includes the mandatory tkinter hidden-import flags.

    These are the flags that make tkinter available in frozen mode.
    Without them, the Browse button crashes on any machine running the
    installed .exe — regardless of whether the host has system Python."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        build_path = _build_py_path()
        cls.build_source = build_path.read_text(encoding='utf-8')
        cls.build_exists = build_path.is_file()

    def test_build_py_exists(self):
        self.assertTrue(self.build_exists, "build.py not found at repo root")

    def test_hidden_import_tkinter_declared(self):
        self.assertIn(
            "'--hidden-import=tkinter'",
            self.build_source,
            "build.py is missing --hidden-import=tkinter — frozen builds "
            "will not bundle the tkinter Python package.",
        )

    def test_hidden_import_underscore_tkinter_declared(self):
        self.assertIn(
            "'--hidden-import=_tkinter'",
            self.build_source,
            "build.py is missing --hidden-import=_tkinter — frozen builds "
            "will not trigger PyInstaller's hook-_tkinter.py, so the "
            "Tcl/Tk DLLs and data directories will be missing.",
        )

    def test_no_exclude_tkinter(self):
        """Ensure nobody added --exclude-module=tkinter."""
        self.assertNotIn(
            'exclude-module=tkinter',
            self.build_source,
            "build.py explicitly excludes tkinter — this would break "
            "the native file picker in frozen builds.",
        )
        self.assertNotIn(
            'exclude-module=_tkinter',
            self.build_source,
            "build.py explicitly excludes _tkinter.",
        )


# ═══════════════════════════════════════════════════════════════════════════
# 6. build_installer.py sets TCL_LIBRARY / TK_LIBRARY
# ═══════════════════════════════════════════════════════════════════════════

class BuildInstallerTclEnvTests(TestCase):
    """The installer builder must set TCL_LIBRARY / TK_LIBRARY env vars
    so PyInstaller can locate the Tcl/Tk data for the Installer GUI."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        path = _build_installer_py_path()
        cls.source = path.read_text(encoding='utf-8') if path.is_file() else ''
        cls.exists = path.is_file()

    def test_build_installer_exists(self):
        self.assertTrue(self.exists, "build_installer.py not found")

    def test_tcl_library_env_set(self):
        self.assertIn(
            'TCL_LIBRARY',
            self.source,
            "build_installer.py does not set TCL_LIBRARY env var.",
        )

    def test_tk_library_env_set(self):
        self.assertIn(
            'TK_LIBRARY',
            self.source,
            "build_installer.py does not set TK_LIBRARY env var.",
        )


# ═══════════════════════════════════════════════════════════════════════════
# 7. Windows version parity — no OS-version branches
# ═══════════════════════════════════════════════════════════════════════════

class WindowsVersionParityTests(TestCase):
    """Verify that the picker code does NOT branch on Windows version.

    The bug was seen on Windows 10 but not Windows 11 — the root cause
    was a missing PyInstaller hidden-import, NOT an OS-version
    difference. This test pins that there is no ``platform.version()``
    or ``sys.getwindowsversion()`` gate inside the picker, so the
    codepath is identical on both OSes."""

    def test_no_windows_version_check_in_picker(self):
        """_run_native_picker must not branch on Windows version."""
        import inspect
        from agent.views import _run_native_picker
        source = inspect.getsource(_run_native_picker)
        for pattern in ('getwindowsversion', 'platform.version',
                        'platform.release', 'win32_ver', 'win10', 'win11'):
            self.assertNotIn(
                pattern, source,
                f"_run_native_picker contains a Windows-version check "
                f"({pattern!r}) — the picker must use the same codepath "
                f"on Windows 10 and Windows 11.",
            )

    def test_picker_views_share_same_runner(self):
        """Both pick_db_sqlite_file_view and pick_backup_directory_view
        must call _run_native_picker — no duplicated picker logic."""
        import inspect
        from agent.views import (
            pick_db_sqlite_file_view,
            pick_backup_directory_view,
        )
        for view_fn in (pick_db_sqlite_file_view, pick_backup_directory_view):
            source = inspect.getsource(view_fn)
            self.assertIn(
                '_run_native_picker',
                source,
                f"{view_fn.__name__} does not call _run_native_picker — "
                f"the picker codepath has diverged.",
            )


# ═══════════════════════════════════════════════════════════════════════════
# 8. Frozen-mode simulation tests
# ═══════════════════════════════════════════════════════════════════════════

class FrozenModeSimulationTests(TestCase):
    """Simulate the frozen-build environment (``getattr(sys, 'frozen')``
    is True) and verify tkinter-related assumptions hold.

    We can't truly run as a .exe in a Django test, but we CAN verify
    that the code paths don't have a source-only gate that would skip
    tkinter in frozen mode."""

    def test_picker_does_not_check_frozen_flag(self):
        """_run_native_picker must NOT skip tkinter when frozen."""
        import inspect
        from agent.views import _run_native_picker
        source = inspect.getsource(_run_native_picker)
        self.assertNotIn(
            'frozen',
            source,
            "_run_native_picker checks sys.frozen — tkinter must be "
            "available in BOTH source and frozen modes.",
        )

    def test_tkinter_import_succeeds_with_frozen_attr(self):
        """Even when sys.frozen is set (simulating PyInstaller), the
        tkinter import must succeed — because the hidden-import flags
        bundle it."""
        original = getattr(sys, 'frozen', None)
        try:
            sys.frozen = True
            # Re-import to verify no frozen-mode guard blocks it
            import tkinter
            importlib.reload(tkinter)
        except ImportError as exc:
            self.fail(
                f"tkinter import failed with sys.frozen=True: {exc}. "
                f"This means the frozen build will crash on Browse.",
            )
        finally:
            if original is None:
                if hasattr(sys, 'frozen'):
                    del sys.frozen
            else:
                sys.frozen = original

    def test_views_lazy_import_pattern(self):
        """The tkinter import in _run_native_picker must be lazy (inside
        the function, not at module top level).  A top-level import would
        crash Django startup if tkinter were missing for any reason,
        taking down the ENTIRE server instead of just the Browse button."""
        import inspect
        from agent.views import _run_native_picker
        source = inspect.getsource(_run_native_picker)
        # The import must be inside the _runner() inner function
        self.assertIn('import tkinter', source)
        # Verify it's NOT at module level in views.py
        from agent import views as views_mod
        module_source = inspect.getsource(views_mod)
        # Find all top-level imports (lines that start with 'import tkinter'
        # or 'from tkinter' at column 0)
        top_level_tkinter = [
            line for line in module_source.splitlines()
            if (line.startswith('import tkinter')
                or line.startswith('from tkinter'))
        ]
        self.assertEqual(
            len(top_level_tkinter), 0,
            f"tkinter is imported at module top level in views.py: "
            f"{top_level_tkinter}. This will crash the server if tkinter "
            f"is missing, instead of just failing the Browse button.",
        )


# ═══════════════════════════════════════════════════════════════════════════
# 9. Comprehensive platform report (always passes, logs diagnostics)
# ═══════════════════════════════════════════════════════════════════════════

class TkinterPlatformDiagnosticTests(TestCase):
    """Diagnostic test that always passes but logs detailed platform
    info so build failures on other machines are easier to debug."""

    def test_log_platform_info(self):
        """Log tkinter / Tcl/Tk / OS details for diagnostics."""
        info = {
            'python_version': sys.version,
            'python_executable': sys.executable,
            'platform': sys.platform,
            'os_version': platform.version(),
            'os_release': platform.release(),
            'windows_label': _WINDOWS_VERSION or 'N/A',
            'is_frozen': getattr(sys, 'frozen', False),
        }
        try:
            import tkinter
            import _tkinter
            info['tkinter_available'] = True
            info['tcl_version'] = _tkinter.TCL_VERSION
            info['tk_version'] = _tkinter.TK_VERSION
            tcl = tkinter.Tcl()
            info['tcl_library'] = tcl.eval('info library')
            info['tcl_library_exists'] = os.path.isdir(info['tcl_library'])
        except ImportError as exc:
            info['tkinter_available'] = False
            info['tkinter_error'] = str(exc)

        # Print so it shows up in test runner output with -v
        lines = [f"\n{'=' * 60}", "  Tkinter Platform Diagnostic Report", f"{'=' * 60}"]
        for k, v in info.items():
            lines.append(f"  {k:25s} = {v}")
        lines.append(f"{'=' * 60}\n")
        print('\n'.join(lines))

        # This test always passes — it exists for diagnostics only
        self.assertTrue(True)
