# ═══════════════════════════════════════════════════════════════════
#   ✦  T L A M A T I N I  ✦   —   "one who knows"
#
#   Created by  Angela López Mendoza   ·   @angelahack1
#   Developer · Architect · Creator of Tlamatini
#
#   Every line of this file was written by Angela López Mendoza.
# ═══════════════════════════════════════════════════════════════════
#   Tlamatini Author Banner — do not remove (releases scrub the name automatically)
"""Tests for the tkinter-free native file/folder picker.

The server's Browse buttons now use Win32 common dialogs via ctypes
(``agent/native_dialogs.py``) instead of tkinter, so the frozen build no
longer bundles Tcl/Tk and the old "Can't find a usable init.tcl" failure
is impossible.

We cannot click a modal dialog in an automated test, so the GUI happy
path is covered by mocking. The highest-risk part of the ctypes approach —
the Win32 struct layout — is pinned via ``ctypes.sizeof`` so a field
mistake fails the suite without ever opening a window. The Browse-button
endpoints, the dispatch wiring, and the graceful-degradation payload are
all exercised directly.

Run:
    python manage.py test agent.test_native_dialogs
"""
import os
import sys
import threading
import unittest
from unittest.mock import patch

from django.test import TestCase, Client
from django.contrib.auth.models import User

from agent import native_dialogs
from agent import views as views_mod

_IS_WINDOWS = os.name == "nt"
_IS_64BIT = sys.maxsize > 2**32


# ═══════════════════════════════════════════════════════════════════════════
# 1. Module surface / platform behavior
# ═══════════════════════════════════════════════════════════════════════════
class NativeDialogModuleTests(unittest.TestCase):
    def test_is_supported_matches_platform(self):
        self.assertEqual(native_dialogs.is_supported(), os.name == "nt")

    @unittest.skipIf(_IS_WINDOWS, "non-Windows behavior")
    def test_pickers_raise_unavailable_off_windows(self):
        with self.assertRaises(native_dialogs.NativeDialogUnavailable):
            native_dialogs.pick_open_file("t")
        with self.assertRaises(native_dialogs.NativeDialogUnavailable):
            native_dialogs.pick_folder("t")

    @unittest.skipIf(_IS_WINDOWS, "non-Windows behavior")
    def test_struct_sizes_unavailable_off_windows(self):
        with self.assertRaises(native_dialogs.NativeDialogUnavailable):
            native_dialogs._struct_sizes()


# ═══════════════════════════════════════════════════════════════════════════
# 2. Win32 struct layout (the real ctypes risk) — Windows only
# ═══════════════════════════════════════════════════════════════════════════
@unittest.skipUnless(_IS_WINDOWS, "Win32 structs are Windows-only")
class Win32StructLayoutTests(unittest.TestCase):
    def test_struct_sizes_match_win32_abi(self):
        sizes = native_dialogs._struct_sizes()
        if _IS_64BIT:
            self.assertEqual(sizes["OPENFILENAMEW"], 152,
                             "OPENFILENAMEW x64 layout drifted from the Win32 ABI")
            self.assertEqual(sizes["BROWSEINFOW"], 64,
                             "BROWSEINFOW x64 layout drifted from the Win32 ABI")
        else:
            self.assertEqual(sizes["OPENFILENAMEW"], 88)
            self.assertEqual(sizes["BROWSEINFOW"], 32)

    def test_win32_dialog_symbols_resolve(self):
        """The DLL entry points the pickers call must exist on this host
        (they ship with every Windows install — nothing to bundle)."""
        import ctypes
        self.assertTrue(hasattr(ctypes.windll.comdlg32, "GetOpenFileNameW"))
        self.assertTrue(hasattr(ctypes.windll.shell32, "SHBrowseForFolderW"))
        self.assertTrue(hasattr(ctypes.windll.shell32, "SHGetPathFromIDListW"))
        self.assertTrue(hasattr(ctypes.windll.ole32, "CoTaskMemFree"))
        # Foreground helper relies on these too.
        self.assertTrue(hasattr(ctypes.windll.user32, "AttachThreadInput"))
        self.assertTrue(hasattr(ctypes.windll.user32, "SetForegroundWindow"))
        self.assertTrue(hasattr(ctypes.windll.user32, "EnumThreadWindows"))


class ForceForegroundHelperTests(unittest.TestCase):
    """The taskbar-only fix: _force_window_foreground must be safe to call
    (it never raises) — actual focus behavior needs a real window/GUI."""

    def test_no_hwnd_is_a_safe_noop(self):
        # Must not raise on any platform for falsy handles.
        native_dialogs._force_window_foreground(None)
        native_dialogs._force_window_foreground(0)

    @unittest.skipUnless(_IS_WINDOWS, "Win32 only")
    def test_bogus_hwnd_does_not_raise(self):
        # A non-existent HWND must be swallowed, not propagated.
        native_dialogs._force_window_foreground(0x7FFFFFFF)


# ═══════════════════════════════════════════════════════════════════════════
# 3. _run_native_picker dispatch (mocked — no real dialog)
# ═══════════════════════════════════════════════════════════════════════════
class RunNativePickerDispatchTests(TestCase):
    def _picker(self):
        return views_mod._run_native_picker

    @patch("agent.native_dialogs.pick_open_file", return_value="D:/data/db.sqlite3")
    def test_db_file_kind_calls_pick_open_file(self, mock_file):
        result = self._picker()("db_sqlite_file", "Pick db")
        self.assertEqual(result, "D:/data/db.sqlite3")
        mock_file.assert_called_once()
        # The db filter must be forwarded.
        _, kwargs = mock_file.call_args
        labels = [lbl for lbl, _pat in kwargs.get("filter_pairs", [])]
        self.assertTrue(any("db.sqlite3" in lbl for lbl in labels))

    @patch("agent.native_dialogs.pick_folder", return_value="C:/Backups")
    def test_directory_kind_calls_pick_folder(self, mock_dir):
        result = self._picker()("directory", "Pick folder")
        self.assertEqual(result, "C:/Backups")
        mock_dir.assert_called_once()

    @patch("agent.native_dialogs.pick_open_file", return_value="")
    def test_cancel_returns_empty_string(self, _mock):
        self.assertEqual(self._picker()("db_sqlite_file", "t"), "")

    def test_unknown_kind_raises_runtime_error(self):
        with self.assertRaises(RuntimeError):
            self._picker()("bogus", "t")

    @patch("agent.native_dialogs.pick_folder",
           side_effect=native_dialogs.NativeDialogUnavailable("requires Windows"))
    def test_unavailable_propagates_as_runtime_error(self, _mock):
        with self.assertRaises(RuntimeError) as ctx:
            self._picker()("directory", "t")
        self.assertIn("Windows", str(ctx.exception))

    def test_picker_runs_in_named_daemon_thread(self):
        captured = {}
        real_init = threading.Thread.__init__

        def spy_init(self_t, *a, **kw):
            real_init(self_t, *a, **kw)
            if self_t.name == "tlamatini-native-picker":
                captured["daemon"] = self_t.daemon

        with patch.object(threading.Thread, "__init__", spy_init):
            with patch("agent.native_dialogs.pick_folder", return_value=""):
                self._picker()("directory", "t")
        self.assertTrue(captured.get("daemon"), "picker must run on a daemon thread")


# ═══════════════════════════════════════════════════════════════════════════
# 4. No tkinter import anywhere in the server picker path
# ═══════════════════════════════════════════════════════════════════════════
class NoTkinterInServerTests(TestCase):
    """Pin that no tkinter is actually IMPORTED or USED on the server path.
    (Prose/comments may still mention the word "tkinter" to explain the
    migration — so we look for real import/usage patterns, not the word.)"""

    @staticmethod
    def _uses_tkinter(src: str) -> list:
        """AST scan for REAL tkinter imports / `filedialog` usage. Docstrings
        and comments that merely mention the word are ignored (they're
        Constant nodes / stripped tokens, never Name/Import nodes)."""
        import ast
        import textwrap
        offenders = []
        tree = ast.parse(textwrap.dedent(src))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for a in node.names:
                    if a.name.split(".")[0] in ("tkinter", "_tkinter"):
                        offenders.append(f"import {a.name}")
            elif isinstance(node, ast.ImportFrom):
                if node.module and node.module.split(".")[0] in ("tkinter", "_tkinter"):
                    offenders.append(f"from {node.module}")
            elif isinstance(node, ast.Name) and node.id == "filedialog":
                offenders.append("filedialog")
            elif isinstance(node, ast.Attribute) and node.attr == "filedialog":
                offenders.append(".filedialog")
        return offenders

    def test_run_native_picker_does_not_use_tkinter(self):
        import inspect
        offenders = self._uses_tkinter(inspect.getsource(views_mod._run_native_picker))
        self.assertEqual(offenders, [], f"tkinter usage in _run_native_picker: {offenders}")

    def test_native_dialogs_module_does_not_use_tkinter(self):
        import inspect
        offenders = self._uses_tkinter(inspect.getsource(native_dialogs))
        self.assertEqual(offenders, [], f"tkinter usage in native_dialogs: {offenders}")

    def test_views_module_has_no_tkinter_import(self):
        import inspect
        module_src = inspect.getsource(views_mod)
        offenders = [
            ln for ln in module_src.splitlines()
            if ln.strip().startswith(("import tkinter", "from tkinter"))
        ]
        self.assertEqual(offenders, [], f"tkinter import found in views.py: {offenders}")


# ═══════════════════════════════════════════════════════════════════════════
# 5. Picker view endpoints (mock the runner; no real dialog)
# ═══════════════════════════════════════════════════════════════════════════
class PickerViewEndpointTests(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user = User.objects.create_user(username="picker_u", password="pw123456")

    def setUp(self):
        self.client = Client()
        self.client.login(username="picker_u", password="pw123456")

    @patch("agent.views._run_native_picker", return_value="C:/data/db.sqlite3")
    def test_db_file_returns_path(self, _m):
        data = self.client.get("/agent/pick_db_sqlite_file/").json()
        self.assertTrue(data["path"].endswith("db.sqlite3"))

    @patch("agent.views._run_native_picker", return_value="")
    def test_db_file_cancel(self, _m):
        data = self.client.get("/agent/pick_db_sqlite_file/").json()
        self.assertEqual(data["path"], "")
        self.assertTrue(data.get("canceled"))

    @patch("agent.views._run_native_picker", return_value="C:/Backups")
    def test_backup_dir_returns_path(self, _m):
        data = self.client.get("/agent/pick_backup_directory/").json()
        self.assertIn("Backups", data["path"])

    def test_endpoints_require_login(self):
        anon = Client()
        self.assertIn(anon.get("/agent/pick_db_sqlite_file/").status_code, (301, 302))
        self.assertIn(anon.get("/agent/pick_backup_directory/").status_code, (301, 302))


# ═══════════════════════════════════════════════════════════════════════════
# 6. Graceful-degradation payload (manual entry fallback)
# ═══════════════════════════════════════════════════════════════════════════
class PickerFailurePayloadTests(TestCase):
    def _payload(self, exc):
        from agent.views import _picker_failure_payload
        return _picker_failure_payload(exc)

    def test_non_windows_is_unavailable(self):
        payload = self._payload(RuntimeError("native file dialog requires Windows"))
        self.assertTrue(payload["picker_unavailable"])
        self.assertIn("type", payload["message"].lower())

    def test_generic_error_is_not_unavailable(self):
        payload = self._payload(RuntimeError("disk on fire"))
        self.assertFalse(payload["picker_unavailable"])
        self.assertIn("disk on fire", payload["message"])

    def test_payload_json_serializable(self):
        import json
        json.dumps(self._payload(RuntimeError("requires Windows")))


# ═══════════════════════════════════════════════════════════════════════════
# 7. build.py no longer pulls in tkinter / Tcl-Tk for the SERVER build
# ═══════════════════════════════════════════════════════════════════════════
class BuildPyNoTkinterTests(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        from pathlib import Path
        cls.src = (Path(__file__).resolve().parents[2] / "build.py").read_text(encoding="utf-8")

    def test_no_tkinter_hidden_import(self):
        self.assertNotIn("--hidden-import=tkinter", self.src)
        self.assertNotIn("--hidden-import=_tkinter", self.src)

    def test_excludes_tkinter(self):
        self.assertIn("--exclude-module=tkinter", self.src)
        self.assertIn("--exclude-module=_tkinter", self.src)

    def test_no_tcl_data_bundling(self):
        self.assertNotIn("_tcl_data", self.src.replace("init.tcl", ""))
        self.assertNotIn("tcl_data_args", self.src)


if __name__ == "__main__":
    unittest.main()
