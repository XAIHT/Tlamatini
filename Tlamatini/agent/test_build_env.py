"""Libraries installed on the build machine must never reach a release (2026-10-21).

Run in a visible foreground development console.

Copyright Angela López Mendoza · @angelahack1 — Tlamatini Author Banner.
"""
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location("build_env_under_test", ROOT / "build_env.py")
build_env = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(build_env)


class SealedEnvironmentTests(unittest.TestCase):
    def test_nothing_from_the_machines_python_leaks_into_the_build(self):
        python = Path(r"C:\envs\py312-abc\Scripts\python.exe")
        env = build_env.sealed_environ(python, {
            "PATH": r"C:\Windows", "PYTHONPATH": r"C:\Users\me\stuff",
            "PYTHONHOME": r"C:\Python", "PIP_USER": "1", "CONDA_PREFIX": r"C:\conda",
            "TLAMATINI_BUNDLE_DATA_KEYS": "1",
        })
        for name in ("PYTHONPATH", "PYTHONHOME", "PIP_USER", "CONDA_PREFIX"):
            self.assertNotIn(name, env)
        self.assertEqual(env["PYTHONNOUSERSITE"], "1")
        self.assertEqual(env[build_env.INSIDE_VAR], "1")
        self.assertEqual(env["VIRTUAL_ENV"], str(python.parent.parent))
        self.assertTrue(env["PATH"].startswith(str(python.parent)))
        self.assertEqual(env["TLAMATINI_BUNDLE_DATA_KEYS"], "1", "release switches pass through")

    def test_a_requirements_change_gets_a_fresh_environment(self):
        with tempfile.TemporaryDirectory() as temporary:
            requirements = Path(temporary) / "requirements.txt"
            requirements.write_text("django==5.2.15\n")
            first = build_env.fingerprint(requirements)
            self.assertEqual(first, build_env.fingerprint(requirements))
            requirements.write_text("django==5.2.15\ntensorflow==2.20.0\n")
            self.assertNotEqual(first, build_env.fingerprint(requirements))
            folder = build_env.env_dir_for(first, Path(temporary))
            self.assertEqual(folder.parent, Path(temporary))
            self.assertRegex(folder.name, r"^py\d+-[0-9a-f]{12}$")

    def test_the_environment_lives_outside_the_repository(self):
        with patch.dict(build_env.os.environ, {"TLAMATINI_BUILD_ENV_DIR": ""}):
            root = build_env.envs_root()
        self.assertNotIn(str(ROOT).lower(), str(root).lower())


class ReRunTests(unittest.TestCase):
    def test_inside_the_sealed_python_the_build_simply_continues(self):
        with patch.object(build_env, "inside_sealed_env", return_value=True), \
                patch.object(build_env, "ensure_sealed_env") as ensure, \
                patch.object(build_env.subprocess, "run") as run:
            build_env.run_in_sealed_env("build.py", [])
        ensure.assert_not_called()
        run.assert_not_called()

    def test_the_build_is_rerun_inside_the_sealed_python_and_keeps_its_exit_code(self):
        python = Path(r"C:\envs\py312-abc\Scripts\python.exe")
        with patch.dict(build_env.os.environ, {build_env.INSIDE_VAR: ""}), \
                patch.object(build_env, "inside_sealed_env", return_value=False), \
                patch.object(build_env, "ensure_sealed_env", return_value=python), \
                patch.object(build_env.subprocess, "run") as run:
            run.return_value.returncode = 7
            with self.assertRaises(SystemExit) as stopped:
                build_env.run_in_sealed_env(str(ROOT / "build.py"), ["--self-modify"])
        self.assertEqual(stopped.exception.code, 7)
        command = run.call_args.args[0]
        self.assertEqual(command[:2], [str(python), "-s"])
        self.assertEqual(Path(command[2]), ROOT / "build.py")
        self.assertEqual(command[3:], ["--self-modify"])
        self.assertEqual(run.call_args.kwargs["env"][build_env.INSIDE_VAR], "1")

    def test_with_no_sealed_python_at_all_the_build_still_runs(self):
        with patch.dict(build_env.os.environ, {build_env.INSIDE_VAR: ""}), \
                patch.object(build_env, "inside_sealed_env", return_value=False), \
                patch.object(build_env, "ensure_sealed_env", return_value=None), \
                patch.object(build_env.subprocess, "run") as run:
            build_env.run_in_sealed_env("build.py", [])
        run.assert_not_called()

    def test_off_restores_the_old_behaviour(self):
        with patch.dict(build_env.os.environ, {build_env.INSIDE_VAR: "off"}), \
                patch.object(build_env, "ensure_sealed_env") as ensure:
            build_env.run_in_sealed_env("build.py", [])
        ensure.assert_not_called()


class EnsureTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        active = patch.dict(build_env.os.environ, {"TLAMATINI_BUILD_ENV_DIR": str(self.root)})
        active.start()
        self.addCleanup(active.stop)

    def test_a_healthy_environment_is_reused_without_reinstalling(self):
        with patch.object(build_env, "healthy", return_value=True), \
                patch.object(build_env, "create") as create:
            python = build_env.ensure_sealed_env()
        create.assert_not_called()
        self.assertTrue(str(python).startswith(str(self.root)))

    def test_when_it_cannot_be_made_the_previous_one_is_used(self):
        older = self.root / "py312-000000000000"
        with patch.object(build_env, "healthy", return_value=False), \
                patch.object(build_env, "create", side_effect=RuntimeError("offline")), \
                patch.object(build_env, "_previous_healthy", return_value=older):
            python = build_env.ensure_sealed_env()
        self.assertEqual(python, build_env.env_python_in(older))

    def test_when_none_exists_it_says_so_instead_of_crashing(self):
        with patch.object(build_env, "healthy", return_value=False), \
                patch.object(build_env, "create", side_effect=RuntimeError("offline")), \
                patch.object(build_env, "_previous_healthy", return_value=None):
            self.assertIsNone(build_env.ensure_sealed_env())


class WiringTests(unittest.TestCase):
    def test_every_release_script_reruns_itself_in_the_sealed_python_first(self):
        for name, first_step in (("build.py", "_acquire_build_lock()"),
                                 ("build_installer.py", "main()"),
                                 ("build_uninstaller.py", "main()")):
            source = (ROOT / name).read_text(encoding="utf-8")
            self.assertIn("from build_env import run_in_sealed_env", source, name)
            entry = source.split('if __name__ == "__main__":', 1)[1]
            self.assertLess(entry.index("run_in_sealed_env(__file__)"),
                            entry.index(first_step), name)

    def test_the_build_no_longer_installs_into_the_users_own_python(self):
        source = (ROOT / "build.py").read_text(encoding="utf-8")
        self.assertIn('pip_scope = [] if in_sealed_env else ["--user"]', source)
        self.assertNotIn('"install", "--user", "-r", str(req_file)]', source)
        self.assertNotIn('"install", "--user", "pyinstaller"])', source)

    def test_the_self_modify_snapshot_carries_the_sealed_env(self):
        source = (ROOT / "copy_source_assets.py").read_text(encoding="utf-8")
        self.assertIn('    "build_env.py",', source)


if __name__ == "__main__":
    unittest.main()
