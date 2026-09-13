"""Guards for the Tlamatini Uninstaller's two safety mechanics (2026-09-13).

1. THE STILL-RUNNING GATE.  Uninstalling while Tlamatini is up leaves half an
   installation behind — Windows will not delete a running .exe, a loaded .dll,
   or a file a pool agent still holds — so the uninstaller refuses to start
   while any process is running out of the directory it is about to erase, and
   offers exactly two ways out: Retry (re-check) and Exit (close the
   uninstaller).  There is deliberately no "continue anyway".

2. THE PRESERVE RULES.  ``agents/`` is always kept.  ``application``,
   ``applications``, ``content_generated``, ``context_files`` and ``Temp`` are
   kept too, but only when they actually hold a file at some depth — and the
   completion dialog then names exactly those, by directory name only.

Both directions matter.  A gate that cannot be satisfied locks a user out of
removing her own software; a preserve rule that fires on an empty folder leaves
litter behind; one that fails to fire deletes the user's own work.

Run:  python Tlamatini/manage.py test agent.test_uninstaller_mechanics
"""

import ast
import os
import shutil
import subprocess
import sys
import tempfile
import textwrap
import time
import tkinter as tk
from pathlib import Path

from django.test import SimpleTestCase

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import uninstall  # noqa: E402  (path must be set up first)

UNINSTALL_SOURCE = (REPO_ROOT / "uninstall.py").read_text(encoding="utf-8")


def _stub_app():
    """A FancyUninstaller with no GUI behind it.

    ``__new__`` skips ``__init__`` so the real ``_remove_files`` /
    ``_preserved_content_note`` run against plain attributes — the shipping
    code, no Tk, no window.
    """
    app = uninstall.FancyUninstaller.__new__(uninstall.FancyUninstaller)
    app.preserved_dirs = []
    app._gate_attempts = 0
    app._set_progress = lambda *a, **k: None
    app._write_preserved_agents_marker = lambda *a, **k: None
    return app


def _function_source(name: str) -> str:
    """The source text of one top-level function or method of uninstall.py."""
    tree = ast.parse(UNINSTALL_SOURCE)
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return ast.get_source_segment(UNINSTALL_SOURCE, node) or ""
    raise AssertionError(f"uninstall.py has no function named {name!r}")


def _code_only(name: str) -> str:
    """The source of a function with its DOCSTRING removed.

    A contract test that scans for a forbidden word must not trip over the
    comment explaining why that word is forbidden.
    """
    tree = ast.parse(UNINSTALL_SOURCE)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            body = node.body
            if (body and isinstance(body[0], ast.Expr)
                    and isinstance(body[0].value, ast.Constant)
                    and isinstance(body[0].value.value, str)):
                body = body[1:]
            return "\n".join(
                ast.get_source_segment(UNINSTALL_SOURCE, stmt) or ""
                for stmt in body
            )
    raise AssertionError(f"uninstall.py has no function named {name!r}")


# ─────────────────────────────────────────────────────────────────────────────
class DirectoryContentDetectionTests(SimpleTestCase):
    """``directory_has_content`` — is there anything of the user's in here?"""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="tlm_uninst_content_"))
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def test_empty_directory_has_no_content(self):
        empty = self.tmp / "empty"
        empty.mkdir()
        self.assertFalse(uninstall.directory_has_content(str(empty)))

    def test_one_file_is_content(self):
        d = self.tmp / "one"
        d.mkdir()
        (d / "note.txt").write_text("x", encoding="utf-8")
        self.assertTrue(uninstall.directory_has_content(str(d)))

    def test_a_file_buried_three_levels_down_is_still_content(self):
        deep = self.tmp / "deep" / "a" / "b" / "c"
        deep.mkdir(parents=True)
        (deep / "buried.bin").write_bytes(b"\x00\x01")
        self.assertTrue(uninstall.directory_has_content(str(self.tmp / "deep")))

    def test_a_tree_of_empty_folders_is_not_content(self):
        """Installer scaffolding: folders, no files.  Nothing of the user's."""
        scaffold = self.tmp / "scaffold" / "sub" / "subsub"
        scaffold.mkdir(parents=True)
        self.assertFalse(uninstall.directory_has_content(str(self.tmp / "scaffold")))

    def test_missing_path_and_plain_file_are_not_content(self):
        self.assertFalse(uninstall.directory_has_content(str(self.tmp / "nope")))
        plain = self.tmp / "plain.txt"
        plain.write_text("x", encoding="utf-8")
        self.assertFalse(uninstall.directory_has_content(str(plain)))
        self.assertFalse(uninstall.directory_has_content(""))

    def test_an_unreadable_directory_counts_AS_content(self):
        """FAIL-SAFE: what we cannot read, we do not delete.

        ``os.walk`` swallows permission errors silently, which would otherwise
        read as "empty" and destroy the user's material.  The onerror hook is
        the whole point, so this pins it.
        """
        source = _function_source("directory_has_content")
        self.assertIn("onerror", source,
                      "os.walk must pass onerror or an unreadable subtree "
                      "silently reads as empty")
        self.assertIn("return True", source.split("except Exception:")[-1],
                      "the except branch must resolve to 'has content'")


# ─────────────────────────────────────────────────────────────────────────────
class PreserveSetTests(SimpleTestCase):
    """The five user-content directories, exactly as Angela named them."""

    def test_the_five_names(self):
        self.assertEqual(
            uninstall.PRESERVED_WHEN_NOT_EMPTY,
            ("application", "applications", "content_generated",
             "context_files", "Temp"),
        )

    def test_matching_is_case_insensitive(self):
        for name in uninstall.PRESERVED_WHEN_NOT_EMPTY:
            self.assertIn(name.lower(), uninstall._PRESERVED_WHEN_NOT_EMPTY_LOWER)
        self.assertIn("temp", uninstall._PRESERVED_WHEN_NOT_EMPTY_LOWER)

    def test_agents_is_not_in_this_set(self):
        """agents/ is preserved ALWAYS — empty or not — by its own branch."""
        self.assertNotIn("agents", uninstall._PRESERVED_WHEN_NOT_EMPTY_LOWER)


# ─────────────────────────────────────────────────────────────────────────────
class RemoveFilesTests(SimpleTestCase):
    """The real ``_remove_files`` against a real throw-away installation."""

    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="tlm_uninst_remove_"))
        self.addCleanup(shutil.rmtree, self.root, True)
        self.install = self.root / "install"

        def touch(rel):
            p = self.install / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text("x", encoding="utf-8")

        def mkdir(rel):
            (self.install / rel).mkdir(parents=True, exist_ok=True)

        touch("agents/shoter/shoter.py")
        touch("application/MyProject/main.py")     # preserved: has content
        touch("content_generated/report.md")       # preserved: has content
        touch("Temp/scratch.tmp")                  # preserved: has content
        mkdir("applications")                      # removed: empty
        mkdir("context_files/empty_sub")           # removed: no file anywhere
        touch("config.json")                       # removed: ordinary file
        touch("_internal/agent/prompt.pmt")        # removed: ordinary tree

        self.app = _stub_app()
        uninstall.FancyUninstaller._remove_files(
            self.app, str(self.install), 0.0, 1.0,
        )

    def test_agents_survives(self):
        self.assertTrue((self.install / "agents" / "shoter" / "shoter.py").exists())

    def test_directories_holding_content_survive_whole(self):
        self.assertTrue((self.install / "application" / "MyProject" / "main.py").exists())
        self.assertTrue((self.install / "content_generated" / "report.md").exists())
        self.assertTrue((self.install / "Temp" / "scratch.tmp").exists())

    def test_empty_candidate_directories_are_removed(self):
        self.assertFalse((self.install / "applications").exists())
        self.assertFalse((self.install / "context_files").exists())

    def test_ordinary_installation_files_are_removed(self):
        self.assertFalse((self.install / "config.json").exists())
        self.assertFalse((self.install / "_internal").exists())

    def test_only_the_directories_actually_kept_are_reported(self):
        self.assertEqual(
            sorted(self.app.preserved_dirs),
            ["Temp", "application", "content_generated"],
        )

    def test_agents_is_not_reported_in_the_content_legend(self):
        """agents/ already has its own sentence in the completion dialog."""
        self.assertNotIn("agents", self.app.preserved_dirs)


class RemoveFilesCaseTests(SimpleTestCase):
    """A directory the user renamed to TEMP is still the same directory."""

    def test_uppercase_directory_name_is_preserved_too(self):
        root = Path(tempfile.mkdtemp(prefix="tlm_uninst_case_"))
        self.addCleanup(shutil.rmtree, root, True)
        install = root / "install"
        (install / "TEMP").mkdir(parents=True)
        (install / "TEMP" / "kept.txt").write_text("x", encoding="utf-8")

        app = _stub_app()
        uninstall.FancyUninstaller._remove_files(app, str(install), 0.0, 1.0)

        self.assertTrue((install / "TEMP" / "kept.txt").exists())
        self.assertEqual(app.preserved_dirs, ["TEMP"])


# ─────────────────────────────────────────────────────────────────────────────
class PreservedContentLegendTests(SimpleTestCase):
    """The legend on the final dialog: dynamic, names only."""

    def _note(self, dirs):
        app = _stub_app()
        app.preserved_dirs = list(dirs)
        return uninstall.FancyUninstaller._preserved_content_note(app)

    def test_nothing_preserved_says_nothing(self):
        self.assertEqual(self._note([]), "")

    def test_one_directory_reads_as_one(self):
        note = self._note(["Temp"])
        self.assertIn("Temp", note)
        self.assertIn("the directory below", note)
        self.assertIn("left untouched", note)

    def test_several_directories_are_all_named(self):
        note = self._note(["application", "content_generated", "Temp"])
        self.assertIn("the directories below", note)
        for name in ("application", "content_generated", "Temp"):
            self.assertIn(name, note)

    def test_the_list_is_NOT_the_static_set_of_candidates(self):
        """Angela's requirement: name the ones detected, not all five."""
        note = self._note(["Temp"])
        self.assertNotIn("context_files", note)
        self.assertNotIn("applications", note)
        self.assertNotIn("content_generated", note)

    def test_a_repeated_name_is_listed_once(self):
        note = self._note(["Temp", "Temp"])
        self.assertEqual(note.count("Temp"), 1)

    def test_file_names_are_never_disclosed(self):
        """Only directory names — what is inside them is the user's business."""
        source = _function_source("_preserved_content_note")
        self.assertNotIn("listdir", source)
        self.assertNotIn("walk", source)


# ─────────────────────────────────────────────────────────────────────────────
class RunningProcessDetectionTests(SimpleTestCase):
    """``find_running_tlamatini`` — against real processes, not mocks."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="tlm_uninst_proc_"))
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def test_a_directory_with_nothing_running_in_it_is_clear(self):
        self.assertEqual(uninstall.find_running_tlamatini(str(self.tmp)), [])

    def test_a_missing_directory_is_clear(self):
        self.assertEqual(uninstall.find_running_tlamatini(str(self.tmp / "nope")), [])
        self.assertEqual(uninstall.find_running_tlamatini(""), [])

    def test_iter_processes_sees_this_very_test_run(self):
        pids = {pid for pid, _name, _path in uninstall.iter_processes()}
        self.assertIn(os.getpid(), pids)

    def test_a_REAL_process_running_from_the_directory_is_detected(self):
        """The whole point: a live image inside the tree we would erase."""
        if sys.platform != "win32":
            self.skipTest("Windows-only detector")
        comspec = os.environ.get("COMSPEC", r"C:\Windows\System32\cmd.exe")
        if not os.path.isfile(comspec):
            self.skipTest("no cmd.exe to copy")

        fake_exe = self.tmp / "Tlamatini.exe"
        shutil.copy2(comspec, fake_exe)

        proc = subprocess.Popen(
            [str(fake_exe), "/k", "rem tlamatini uninstaller gate test"],
            cwd=str(self.tmp),
            stdin=subprocess.PIPE,
            creationflags=subprocess.CREATE_NEW_CONSOLE,
        )
        try:
            found = []
            for _ in range(40):          # up to 4 s for the child to appear
                found = uninstall.find_running_tlamatini(str(self.tmp))
                if found:
                    break
                time.sleep(0.1)
            self.assertTrue(found, "a process running inside the install "
                                   "directory must be detected")
            mine = [rec for rec in found if rec["pid"] == proc.pid]
            self.assertEqual(len(mine), 1, f"child {proc.pid} not in {found}")
            self.assertEqual(mine[0]["name"].lower(), "tlamatini.exe")
            self.assertIn("installation directory", mine[0]["evidence"])
        finally:
            proc.kill()
            proc.wait(timeout=10)

        for _ in range(40):              # and it clears once the child is gone
            if not uninstall.find_running_tlamatini(str(self.tmp)):
                break
            time.sleep(0.1)
        self.assertEqual(uninstall.find_running_tlamatini(str(self.tmp)), [],
                         "the gate must clear once the process is closed")

    def test_the_uninstaller_never_detects_itself(self):
        """Uninstaller.exe lives INSIDE the installation it removes.

        Without the self-exclusion the gate would find its own process and
        nobody could ever uninstall anything.
        """
        own_dir = os.path.dirname(sys.executable)
        found = uninstall.find_running_tlamatini(own_dir)
        self.assertNotIn(os.getpid(), [rec["pid"] for rec in found])

    def test_detection_failure_falls_OPEN(self):
        """A detector that cannot run must never block the uninstallation."""
        source = _function_source("find_running_tlamatini")
        tail = source.split("except Exception:")[-1]
        self.assertIn("return []", tail,
                      "a failed scan must report 'nothing found', never block")


# ─────────────────────────────────────────────────────────────────────────────
class RunningGateFlowTests(SimpleTestCase):
    """The gate's decision logic, without opening a window."""

    def setUp(self):
        self.real_finder = uninstall.find_running_tlamatini
        self.addCleanup(setattr, uninstall, "find_running_tlamatini",
                        self.real_finder)

    def test_a_clear_machine_proceeds_without_any_dialog(self):
        uninstall.find_running_tlamatini = lambda _d: []
        app = _stub_app()
        app._show_running_gate = lambda *a: self.fail("dialog must not open")
        self.assertTrue(
            uninstall.FancyUninstaller._ensure_tlamatini_not_running(app, "C:/x"),
        )

    def test_retry_until_clear_proceeds(self):
        uninstall.find_running_tlamatini = lambda _d: [
            {"pid": 1, "name": "Tlamatini.exe", "path": "", "evidence": "e"},
        ]
        app = _stub_app()
        app._show_running_gate = lambda *a: True      # user retried, it cleared
        app._shutdown = lambda: self.fail("must not shut down after a clear retry")
        self.assertTrue(
            uninstall.FancyUninstaller._ensure_tlamatini_not_running(app, "C:/x"),
        )

    def test_exit_shuts_the_uninstaller_down_completely(self):
        uninstall.find_running_tlamatini = lambda _d: [
            {"pid": 1, "name": "Tlamatini.exe", "path": "", "evidence": "e"},
        ]
        closed = []
        app = _stub_app()
        app._show_running_gate = lambda *a: False     # user pressed Exit
        app._shutdown = lambda: closed.append(True)
        self.assertFalse(
            uninstall.FancyUninstaller._ensure_tlamatini_not_running(app, "C:/x"),
        )
        self.assertEqual(closed, [True], "Exit must close the uninstaller")

    def test_shutdown_destroys_the_root_window(self):
        class FakeRoot:
            def __init__(self):
                self.destroyed = False

            def destroy(self):
                self.destroyed = True

        app = _stub_app()
        app.root = FakeRoot()
        uninstall.FancyUninstaller._shutdown(app)
        self.assertTrue(app.root.destroyed)


# ─────────────────────────────────────────────────────────────────────────────
class GateWiringContractTests(SimpleTestCase):
    """Source-level contracts that a careless edit must not break."""

    def test_the_gate_runs_BEFORE_the_confirmation(self):
        """Never make the user confirm something we are about to refuse."""
        source = textwrap.dedent(_function_source("_start_uninstall"))
        gate = source.index("_ensure_tlamatini_not_running")
        confirm = source.index("_confirm_removal")
        self.assertLess(gate, confirm)

    def test_the_gate_runs_before_anything_is_deleted(self):
        source = _function_source("_start_uninstall")
        self.assertLess(source.index("_ensure_tlamatini_not_running"),
                        source.index("_uninstalling = True"))

    def test_retry_re_runs_the_detection(self):
        """Retry must ask the machine again, not replay the first answer."""
        source = _function_source("_show_running_gate")
        retry = source[source.index("def _retry"):source.index("def _exit")]
        self.assertIn("find_running_tlamatini", retry)

    def test_the_gate_offers_exactly_retry_and_exit(self):
        source = _code_only("_show_running_gate")
        self.assertIn('"⟳  Retry"', source)
        self.assertIn('"Exit"', source)
        for forbidden in ("continue anyway", "Continue Anyway", "Ignore",
                          "Skip", "Force"):
            self.assertNotIn(forbidden, source,
                             "a bypass would walk the user into the broken "
                             "half-deleted installation this gate prevents")

    def test_closing_the_gate_window_counts_as_exit(self):
        source = _function_source("_show_running_gate")
        self.assertIn('dlg.protocol("WM_DELETE_WINDOW", _exit)', source)

    def test_the_gate_is_modal(self):
        source = _function_source("_show_running_gate")
        self.assertIn("grab_set", source)
        self.assertIn("wait_window", source)

    def test_the_preserved_list_is_reset_per_run(self):
        """A second uninstallation must not inherit the first one's legend."""
        source = _function_source("_start_uninstall")
        self.assertIn("self.preserved_dirs = []", source)

    def test_the_uninstaller_stays_dependency_free(self):
        """It is packaged alone by build_uninstaller.py — stdlib + tkinter."""
        tree = ast.parse(UNINSTALL_SOURCE)
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(a.name.split(".")[0] for a in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".")[0])
        allowed = {
            "ctypes", "json", "os", "re", "shutil", "stat", "subprocess", "sys",
            "threading", "time", "tkinter", "winreg", "datetime", "hashlib",
        }
        self.assertTrue(imported <= allowed, f"unexpected import: {imported - allowed}")

    def test_the_warning_on_screen_matches_what_the_code_does(self):
        """The card must not still promise that everything else is removed."""
        self.assertNotIn("All other application files will be removed",
                         UNINSTALL_SOURCE)
        warning = UNINSTALL_SOURCE[UNINSTALL_SOURCE.index("⚠  agents/"):]
        warning = warning[:warning.index("justify=")]
        for name in uninstall.PRESERVED_WHEN_NOT_EMPTY:
            self.assertIn(name, warning,
                          f"the on-screen warning never mentions {name}")


# ─────────────────────────────────────────────────────────────────────────────
class VisibleHarnessContractTests(SimpleTestCase):
    """The visible end-to-end runner must stay honest and non-destructive."""

    HARNESS = (REPO_ROOT / ".claude" / "skills" / "tlamatini-daily-chat-test" /
               "harness" / "uninstaller_visible.py")

    def test_the_harness_ships(self):
        self.assertTrue(self.HARNESS.is_file(), f"missing {self.HARNESS}")

    def test_it_never_touches_the_real_machine(self):
        source = self.HARNESS.read_text(encoding="utf-8")
        self.assertIn("_unregister_programs_entry = staticmethod", source)
        self.assertIn("_restart_explorer = staticmethod", source)
        self.assertIn("guard_path", source)

    def test_it_says_what_it_stubbed(self):
        """A test that hides what it faked is a test that lies."""
        source = self.HARNESS.read_text(encoding="utf-8")
        self.assertIn("[STUBBED]", source)

    def test_it_keeps_its_scratch_inside_the_app_temp(self):
        source = self.HARNESS.read_text(encoding="utf-8")
        self.assertIn('REPO_ROOT / "Temp"', source)
        self.assertNotIn("gettempdir", source)

    def test_it_parses(self):
        ast.parse(self.HARNESS.read_text(encoding="utf-8"))


# ─────────────────────────────────────────────────────────────────────────────
class WindowIsCompleteWithoutAVersionTests(SimpleTestCase):
    """The window must be WHOLE even when the version cannot be resolved.

    Regression for the badge-swallows-the-window bug: the entire body of the
    window — path field, warning, progress section, Uninstall and Cancel — used
    to be built inside ``_build_version_badge``, BELOW its own
    ``if not self.version: return``.  A build whose version did not resolve
    would therefore have painted a header over an empty card, with no way to do
    anything at all.  It never fired only because the version always resolves.
    """

    def test_the_badge_method_builds_only_the_badge(self):
        badge = _function_source("_build_version_badge")
        for control in ("path_entry", "uninstall_btn", "cancel_btn",
                        "browse_btn", "progress_bar", "check_labels"):
            self.assertNotIn(control, badge,
                             "the window's controls must live in _build_ui, "
                             "never behind the badge's version guard")

    def test_build_ui_owns_every_control(self):
        build = _function_source("_build_ui")
        for control in ("self.path_entry", "self.browse_btn",
                        "self.uninstall_btn", "self.cancel_btn",
                        "self.progress_frame", "self.step_label"):
            self.assertIn(control, build)

    def test_a_versionless_window_still_has_its_buttons(self):
        """Built for real and SHOWN on the desktop — never a hidden window."""
        try:
            root = tk.Tk()
        except Exception as exc:                      # no display at all
            self.skipTest(f"Tk is unavailable here: {exc}")
        try:
            real_resolver = uninstall.resolve_version
            uninstall.resolve_version = lambda: ""    # the exact failure mode
            try:
                app = uninstall.FancyUninstaller(root)
            finally:
                uninstall.resolve_version = real_resolver

            self.assertEqual(app.version, "")
            root.deiconify()
            root.update()

            for name in ("path_entry", "browse_btn", "uninstall_btn",
                         "cancel_btn", "progress_frame", "step_label"):
                self.assertTrue(hasattr(app, name),
                                f"{name} was never built without a version")
            self.assertTrue(app.uninstall_btn.winfo_ismapped(),
                            "the Uninstall button never reached the screen")
            self.assertTrue(app.cancel_btn.winfo_ismapped(),
                            "the Cancel button never reached the screen")
            self.assertTrue(app.path_entry.winfo_ismapped(),
                            "the path field never reached the screen")
        finally:
            try:
                root.destroy()
            except Exception:
                pass
