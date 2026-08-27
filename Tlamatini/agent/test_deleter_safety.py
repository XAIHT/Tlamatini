"""Guard the Deleter against ever deleting the directory it was told to work IN.

On 2026-08-26 a single ordinary Deleter call erased an entire ``agent/`` tree
(764 files) because ``target_path=<a directory>`` was lumped in with the
delete-target aliases, so it silently meant "delete that directory". This pins the
fix so it cannot regress:

  * ``target_path`` is the WORKING DIRECTORY, not a target;
  * ``refusal_reason()`` refuses protected / ancestor / working / git-root / drive-root
    paths (with a reason string);
  * a whole DIRECTORY tree is deleted only with ``allow_directory_delete=True``.

The Deleter is a self-contained pool agent (it imports nothing from ``agent.*``), so
it is loaded by file path. Importing it runs ``os.chdir`` + logging setup, so cwd is
saved and restored around the load.
"""
import os
import shutil
import tempfile
import unittest
import importlib.util
from pathlib import Path

_AGENT_DIR = Path(__file__).resolve().parent
_DELETER_PATH = _AGENT_DIR / "agents" / "deleter" / "deleter.py"


def _load_deleter():
    cwd = os.getcwd()
    try:
        spec = importlib.util.spec_from_file_location("deleter_safety_under_test", str(_DELETER_PATH))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod
    finally:
        try:
            os.chdir(cwd)
        except OSError:
            pass


deleter = _load_deleter()


def _touch(path):
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("")


class RefusalReasonTests(unittest.TestCase):
    def setUp(self):
        self.base = tempfile.mkdtemp(prefix="delsafety_")
        self.work = os.path.join(self.base, "work")
        os.makedirs(self.work)

    def tearDown(self):
        shutil.rmtree(self.base, ignore_errors=True)

    def test_refuses_the_working_directory(self):
        self.assertTrue(deleter.refusal_reason(self.work, self.work))

    def test_refuses_a_drive_root(self):
        self.assertTrue(deleter.refusal_reason("C:\\", ""))

    def test_refuses_a_git_repository_root(self):
        repo = os.path.join(self.base, "repo")
        os.makedirs(os.path.join(repo, ".git"))
        self.assertIn("git", deleter.refusal_reason(repo, ""))

    def test_refuses_a_protected_name_directory(self):
        prot = os.path.join(self.work, "agent")
        os.makedirs(prot)
        self.assertIn("protected", deleter.refusal_reason(prot, ""))

    def test_allows_a_plain_file(self):
        f = os.path.join(self.work, "x.txt")
        _touch(f)
        self.assertEqual(deleter.refusal_reason(f, self.work), "")


class PerformDeleteSafetyTests(unittest.TestCase):
    def setUp(self):
        self.base = tempfile.mkdtemp(prefix="delsafety_")
        self.work = os.path.join(self.base, "work")
        os.makedirs(os.path.join(self.work, "sub"))
        self.files = []
        for n in ("f1.txt", "f2.txt", "f3.txt"):
            p = os.path.join(self.work, n)
            _touch(p)
            self.files.append(p)

    def tearDown(self):
        shutil.rmtree(self.base, ignore_errors=True)

    def test_deletes_named_files_but_keeps_the_working_directory(self):
        # The 764-file regression: the named files go; the folder stays.
        deleter.perform_delete_operations(self.files, base_dir=self.work, allow_directory_delete=False)
        for p in self.files:
            self.assertFalse(os.path.exists(p), f"{p} should be deleted")
        self.assertTrue(os.path.isdir(self.work), "the working directory must survive")
        self.assertTrue(os.path.isdir(os.path.join(self.work, "sub")))

    def test_a_directory_is_refused_without_opt_in(self):
        deleter.perform_delete_operations([self.work], base_dir="", allow_directory_delete=False)
        self.assertTrue(os.path.isdir(self.work))

    def test_opt_in_deletes_a_disposable_directory(self):
        disp = os.path.join(self.base, "disposable")
        os.makedirs(disp)
        _touch(os.path.join(disp, "j.txt"))
        deleter.perform_delete_operations([disp], base_dir="", allow_directory_delete=True)
        self.assertFalse(os.path.exists(disp))

    def test_protected_and_git_dirs_refused_even_with_opt_in(self):
        repo = os.path.join(self.base, "repo")
        os.makedirs(os.path.join(repo, ".git"))
        deleter.perform_delete_operations([repo], base_dir="", allow_directory_delete=True)
        self.assertTrue(os.path.isdir(repo), "a git root must never be deleted")

        prot = os.path.join(self.work, "agent")
        os.makedirs(prot)
        deleter.perform_delete_operations([prot], base_dir="", allow_directory_delete=True)
        self.assertTrue(os.path.isdir(prot), "a protected-name directory must never be deleted")


if __name__ == "__main__":
    unittest.main()
