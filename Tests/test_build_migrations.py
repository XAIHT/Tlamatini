# Tlamatini Author Banner — Created by Angela López Mendoza · @angelahack1
"""Visible release-input checks. Fixtures stay under this checkout's Temp."""
from contextlib import redirect_stdout
import ast
import io
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import build_complete_private_release as private  # noqa: E402
import build_complete_public_release as public  # noqa: E402
from build_runtime_assets import validate_migration_dependencies  # noqa: E402


class BuildMigrationTests(unittest.TestCase):
    def setUp(self):
        scratch = ROOT / "Temp"
        scratch.mkdir(exist_ok=True)
        self.temporary = tempfile.TemporaryDirectory(prefix="migration-inputs-", dir=scratch)
        self.addCleanup(self.temporary.cleanup)
        self.repo = Path(self.temporary.name)
        self.migrations = self.repo / "Tlamatini/agent/migrations"
        self.migrations.mkdir(parents=True)
        self.write("0001_initial", "[]")

    def write(self, name, dependencies, *, prefix=""):
        path = self.migrations / (name + ".py")
        path.write_text(prefix + f"class Migration:\n    dependencies = {dependencies}\n",
                        encoding="utf-8")
        return path

    def test_valid_chain_does_not_require_contiguous_numbers(self):
        self.write("0027_catalog", "[('agent', '0001_initial')]")
        self.write("0004_remote", "[('agent', '0027_catalog')]")
        self.assertEqual(validate_migration_dependencies(self.repo), 3)

    def test_missing_edition_parent_names_both_nodes(self):
        self.write("0227_create_superuser_console_handoff", "[('agent', '0001_initial')]")
        self.write("0224_remote_controller", "[('agent', '0223_create_superuser_console_handoff')]")
        with self.assertRaisesRegex(RuntimeError, "0224_remote_controller requires missing agent.0223_"):
            validate_migration_dependencies(self.repo)

    def test_external_and_swappable_dependencies_are_not_guessed(self):
        self.write("0002_auth", "[('auth', '0012_user'), migrations.swappable_dependency(settings.AUTH_USER_MODEL)]",
                   prefix="raise RuntimeError('must never execute source')\n")
        self.assertEqual(validate_migration_dependencies(self.repo), 2)

    def test_django_special_local_nodes_are_allowed(self):
        self.write("0002_special", "[('agent', '__first__'), ('agent', '__latest__')]")
        self.assertEqual(validate_migration_dependencies(self.repo), 2)

    def test_bom_and_annotated_dependencies(self):
        (self.migrations / "0002_bom.py").write_text(
            "class Migration:\n    dependencies: list = [('agent', '0001_initial')]\n",
            encoding="utf-8-sig")
        self.assertEqual(validate_migration_dependencies(self.repo), 2)

    def test_syntax_error_names_the_source(self):
        (self.migrations / "0002_broken.py").write_text("class Migration:\n invalid !!!\n")
        with self.assertRaisesRegex(RuntimeError, "0002_broken.py"):
            validate_migration_dependencies(self.repo)

    def test_missing_migration_class_is_reported(self):
        (self.migrations / "0002_empty.py").write_text("# No class\n")
        with self.assertRaisesRegex(RuntimeError, "Migration class missing"):
            validate_migration_dependencies(self.repo)

    def test_missing_migration_directory_is_reported(self):
        with self.assertRaisesRegex(RuntimeError, "No application migration sources"):
            validate_migration_dependencies(self.repo / "absent")

    def test_check_is_read_only(self):
        self.write("0002_next", "[('agent', '0001_initial')]")
        before = {p: p.read_bytes() for p in self.repo.rglob("*") if p.is_file()}
        validate_migration_dependencies(self.repo)
        self.assertEqual(before, {p: p.read_bytes() for p in self.repo.rglob("*") if p.is_file()})

    def test_real_checkout_has_no_missing_local_parent(self):
        self.assertGreater(validate_migration_dependencies(ROOT), 220)

    def test_both_wrappers_reject_before_side_effects(self):
        self.write("0002_bad", "[('agent', 'missing_parent')]")
        for builder in (private, public):
            with self.subTest(builder=builder.__name__), patch.object(builder, "REPO_ROOT", self.repo), \
                    patch.object(builder, "assert_system_python") as python_check, \
                    patch.object(builder, "run") as run, redirect_stdout(io.StringIO()) as output:
                self.assertEqual(builder.main(["--version", "1.93.5", "--self-modify"]), 1)
                self.assertIn("missing_parent", output.getvalue())
                python_check.assert_not_called()
                run.assert_not_called()

    def test_direct_build_checks_dependencies_before_cleaning(self):
        tree = ast.parse((ROOT / "build.py").read_text(encoding="utf-8-sig"))
        main = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "main")
        steps = [n for n in ast.walk(main) if isinstance(n, ast.Call)
                 and isinstance(n.func, ast.Name) and n.func.id == "run_step"]
        check = next(n for n in steps if len(n.args) > 1 and isinstance(n.args[1], ast.Name)
                     and n.args[1].id == "validate_migration_dependencies")
        cleanup = next(n for n in steps if isinstance(n.args[0], ast.Constant)
                       and n.args[0].value == "Cleaning previous build artifacts")
        self.assertLess(check.lineno, cleanup.lineno)

    def test_direct_entry_checks_before_environment_provisioning(self):
        tree = ast.parse((ROOT / "build.py").read_text(encoding="utf-8-sig"))
        entry = next(n for n in tree.body if isinstance(n, ast.If)
                     and ast.unparse(n.test) == "__name__ == '__main__'")
        calls = [n for n in ast.walk(entry) if isinstance(n, ast.Call)
                 and isinstance(n.func, ast.Name)]
        check = next(n for n in calls if n.func.id == "validate_migration_dependencies")
        provision = next(n for n in calls if n.func.id == "run_in_sealed_env")
        self.assertLess(check.lineno, provision.lineno)


if __name__ == "__main__":
    unittest.main(verbosity=2)
