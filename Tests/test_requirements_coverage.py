# Tlamatini - Created by Angela Lopez Mendoza - @angelahack1
# Tlamatini Author Banner - do not remove
"""Run visibly: python -m unittest discover -s Tests -p test_requirements_coverage.py -v"""
from pathlib import Path
import tempfile
import unittest

from scripts.check_requirements_coverage import ROOT, audit, extract_references


class DependencyCoverageTests(unittest.TestCase):
    def setUp(self):
        (ROOT / "Temp").mkdir(exist_ok=True)
        self.scratch = tempfile.TemporaryDirectory(dir=ROOT / "Temp")
        self.addCleanup(self.scratch.cleanup)
        self.root = Path(self.scratch.name)
        self.files = []

    def write(self, name, content):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        if name.endswith(".py"):
            self.files.append(Path(name))

    def run_audit(self, declared=""):
        self.write("requirements.txt", declared)
        return audit(self.root, self.files)

    def test_optional_imports_outside_agents_are_required(self):
        self.write("app/report.py", "try:\n    from lxml import etree\nexcept ImportError:\n    pass\n")
        result = self.run_audit()
        self.assertIn("lxml", result["missing"])
        self.assertEqual(result["missing"]["lxml"][0]["file"], "app/report.py")

    def test_import_aliases_do_not_depend_on_installed_distribution_metadata(self):
        self.write("worker.py", "from google.protobuf import descriptor\nimport win32con\nfrom PIL import Image\n")
        self.assertEqual(self.run_audit("protobuf==6.31.1\npywin32==312\npillow==12.3.0\n")["missing"], {})

    def test_build_inventories_literal_dynamic_and_generated_code_are_scanned(self):
        self.write("build_probe.py", 'hiddenimports = ["six"]\n'
                   'args=["--collect-all", "autobahn"]\n'
                   'import importlib\nimportlib.import_module("lxml")\n'
                   'code="import sounddevice\\nprint(1)"\n'
                   'for label, module in (("audio", "av"),):\n    __import__(module)\n')
        result = self.run_audit()
        self.assertEqual(set(result["missing"]), {"six", "autobahn", "lxml", "sounddevice", "av"})
        self.assertEqual(result["unreviewed_dynamic_imports"], [])

    def test_local_and_application_supplied_modules_are_not_pypi_names(self):
        self.write("helper.py", "")
        self.write("namespace/leaf.py", "")
        self.write("worker.py", "import helper\nimport namespace.leaf\nimport bpy\n")
        result = self.run_audit()
        self.assertEqual(result["missing"], {})
        self.assertEqual(result["host_modules"][0]["provided_by"], "Blender's embedded Python")

    def test_unknown_computed_import_needs_review(self):
        self.write("worker.py", "import importlib\ndef load(name):\n    return importlib.import_module(name)\n")
        self.assertEqual(len(self.run_audit()["unreviewed_dynamic_imports"]), 1)

    def test_managed_sdk_must_have_a_real_declaration(self):
        self.write("worker.py", 'command=["python","-m","esphome"]\n')
        self.assertIn("esphome", self.run_audit()["missing"])
        self.write("requirements-esphome.txt", "esphome==2026.9.0\n")
        result = self.run_audit()
        self.assertEqual(result["missing"], {})
        self.assertEqual(result["managed_runtimes"][0]["manifest"], "requirements-esphome.txt")

    def test_syntax_errors_cannot_silently_skip_a_source_file(self):
        self.write("broken.py", "from somewhere import (\n")
        self.assertEqual(len(self.run_audit()["syntax_errors"]), 1)

    def test_test_fixture_strings_are_not_dependencies_but_real_test_imports_are(self):
        self.write("test_transport.py", 'import pytest\nshape=["-m","fake_server"]\nexample="import fake_lib\\n"\n')
        self.assertEqual(set(self.run_audit()["missing"]), {"pytest"})

    def test_cli_modules_are_dependencies_in_real_agent_code(self):
        refs, unresolved = extract_references('cmd=["-m","platformio"]\n', Path("agent.py"))
        self.assertEqual([r["module"] for r in refs], ["platformio"])
        self.assertEqual(unresolved, [])

    def test_different_google_namespaces_do_not_hide_behind_protobuf(self):
        self.write("worker.py", "from google.cloud import storage\n")
        self.assertIn("google", self.run_audit("protobuf==6.31.1\n")["missing"])


if __name__ == "__main__":
    unittest.main()
