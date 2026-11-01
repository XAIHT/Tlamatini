# Tlamatini Author Banner — Created by Angela López Mendoza · @angelahack1
"""Real Python-cache lifecycle tests; run from a visible foreground console.

These use small stdlib-only venv fixtures, not fake Python executables. Children
inherit the console. No release is rebuilt and no real build cache is modified.
"""
from pathlib import Path
import os
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

import build_env

ROOT = Path(__file__).resolve().parents[1]

HOLDER = r"""
import sys, time
from pathlib import Path
import build_env
folder, ready, release, outcome = map(Path, sys.argv[1:])
with build_env.environment_lock(folder):
    ready.write_text("leased")
    while not release.exists():
        time.sleep(0.05)
    # Exactly the failing boundary: a long-running build launches Python again.
    import subprocess
    child = subprocess.run([str(build_env.env_python_in(folder)), "-c",
                            "import sys; print('Nested build Python is alive:', sys.executable)"],
                           env=build_env.sealed_environ(build_env.env_python_in(folder)))
    outcome.write_text(str(child.returncode))
sys.exit(child.returncode)
"""

CONTENDER = r"""
import sys
from pathlib import Path
import build_env
try:
    with build_env.environment_lock(Path(sys.argv[1]), timeout=0.5):
        print("ERROR: acquired an environment used by another process")
        sys.exit(3)
except TimeoutError:
    print("PASS: concurrent environment repair was blocked")
    sys.exit(0)
"""


class BuildEnvironmentLifecycleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="tlamatini-build-env-test-")
        cls.root = Path(cls.temp.name)
        cls.req_a = cls.root / "english.txt"
        cls.req_b = cls.root / "spanish.txt"
        cls.req_a.write_text("# English dependency fixture\n", encoding="utf-8")
        cls.req_b.write_text("# Spanish dependency fixture\n", encoding="utf-8")
        cls.cache = cls.root / "cache"
        cls.settings = patch.dict(os.environ, {"TLAMATINI_BUILD_ENV_DIR": str(cls.cache)})
        cls.settings.start()
        cls.imports = patch.object(build_env, "HEALTH_IMPORTS", ("json",))
        cls.imports.start()
        try:
            cls.python_a = build_env.ensure_sealed_env(cls.req_a)
            if cls.python_a is None:
                raise RuntimeError("Could not prepare the real venv test fixture")
        except BaseException:
            cls.tearDownClass()
            raise

    @classmethod
    def tearDownClass(cls):
        cls.imports.stop()
        cls.settings.stop()
        cls.temp.cleanup()

    def start_holder(self):
        work = Path(tempfile.mkdtemp(dir=self.root))
        ready, release, outcome = (work / name for name in ("ready", "release", "outcome"))
        holder = subprocess.Popen(
            [sys.executable, "-u", "-c", HOLDER, str(self.python_a.parent.parent),
             str(ready), str(release), str(outcome)], cwd=ROOT)
        self.addCleanup(self.finish_holder, holder, release)
        deadline = time.monotonic() + 15
        while not ready.exists():
            if holder.poll() is not None or time.monotonic() >= deadline:
                self.fail("The real child did not acquire its environment lease")
            time.sleep(0.05)
        return holder, release, outcome

    @staticmethod
    def finish_holder(holder, release):
        release.touch()
        try:
            holder.wait(timeout=15)
        except subprocess.TimeoutExpired:
            holder.kill()
            holder.wait(timeout=5)

    def test_other_edition_cannot_delete_a_running_build_python(self):
        holder, release, outcome = self.start_holder()
        print("Creating a second fingerprint while the first Python is leased.", flush=True)
        python_b = build_env.ensure_sealed_env(self.req_b)
        self.assertIsNotNone(python_b)
        self.assertNotEqual(self.python_a, python_b)
        self.assertTrue((self.python_a.parent.parent / "pyvenv.cfg").is_file())
        self.assertTrue(build_env.healthy(self.python_a.parent.parent))
        self.assertTrue(build_env.healthy(python_b.parent.parent))
        release.touch()
        self.assertEqual(holder.wait(timeout=15), 0)
        self.assertEqual(outcome.read_text(), "0")

    def test_same_environment_cannot_be_repaired_while_a_build_uses_it(self):
        holder, release, _ = self.start_holder()
        folder = self.python_a.parent.parent
        cfg = (folder / "pyvenv.cfg").read_bytes()
        result = subprocess.run(
            [sys.executable, "-u", "-c", CONTENDER, str(folder)],
            cwd=ROOT, timeout=10)
        self.assertEqual(result.returncode, 0)
        self.assertEqual((folder / "pyvenv.cfg").read_bytes(), cfg)
        release.touch()
        self.assertEqual(holder.wait(timeout=15), 0)
        with build_env.environment_lock(folder, timeout=1):
            self.assertTrue(build_env.healthy(folder))

    def test_os_releases_the_environment_lease_after_holder_terminates(self):
        holder, _, _ = self.start_holder()
        holder.terminate()
        holder.wait(timeout=10)
        with build_env.environment_lock(self.python_a.parent.parent, timeout=1):
            self.assertTrue(build_env.healthy(self.python_a.parent.parent))

    def test_missing_venv_configuration_is_rejected_before_a_launch(self):
        with tempfile.TemporaryDirectory(dir=self.root) as temporary:
            folder = Path(temporary)
            python = build_env.env_python_in(folder)
            python.parent.mkdir()
            python.write_bytes(b"not launched")
            (folder / build_env.MARKER_NAME).write_text("{}")
            with patch.object(build_env.subprocess, "run") as run:
                self.assertFalse(build_env.healthy(folder))
            run.assert_not_called()

    def test_busy_cache_must_not_fall_back_to_the_machine_python(self):
        with patch.dict(os.environ, {build_env.INSIDE_VAR: ""}), \
                patch.object(build_env, "inside_sealed_env", return_value=False), \
                patch.object(build_env, "ensure_sealed_env", side_effect=TimeoutError("busy")), \
                patch.object(build_env.subprocess, "run") as run:
            with self.assertRaisesRegex(SystemExit, "busy"):
                build_env.run_in_sealed_env("build.py", [])
        run.assert_not_called()


if __name__ == "__main__":
    unittest.main(verbosity=2)

