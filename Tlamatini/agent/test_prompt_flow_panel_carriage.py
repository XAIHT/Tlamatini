# Tlamatini Author Banner — Angela López Mendoza
"""Packaging omission regressions; run in a verified visible foreground console."""

import importlib.util
from pathlib import Path
import sys
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
try:
    import build_runtime_assets as assets

    spec = importlib.util.spec_from_file_location("prompt_flow_panel_build_tests", ROOT / "build.py")
    build = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(build)
finally:
    sys.path.remove(str(ROOT))


class PromptFlowPanelCarriageTests(unittest.TestCase):
    def test_frozen_archive_rejects_each_missing_execution_module(self):
        complete = set(build._FROZEN_REQUIRED_AGENT_MODULES)
        for module in (
            "agent.prompt_flow_panel_consumer",
            "agent.prompt_flow_panel_runtime",
            "agent.services.prompt_flow_panel",
            "agent.management.commands.check_prompt_flow_panel",
        ):
            with self.subTest(module=module):
                self.assertIn(module, complete)
                with patch.object(build, "_read_pyz_module_names", return_value=complete - {module}):
                    with self.assertRaises(SystemExit) as failure:
                        build.verify_frozen_agent_modules(ROOT / "Temp")
                    self.assertEqual(failure.exception.code, 1)

    def test_release_receipt_rejects_each_missing_panel_asset(self):
        # A minimally complete non-self-modify receipt; no actual release is built.
        names = set(assets.ROOT_SOURCES.values()) | {
            "Tlamatini.exe", "python/python.exe", "jre/bin/java.exe", "git/cmd/git.exe",
            "jd-cli/jd-cli.jar", "_internal/db.sqlite3", "_internal/pymupdf/_mupdf.pyd",
            "_internal/pymupdf/_extra.pyd", "_internal/pymupdf/mupdfcpp64.dll",
            "_internal/staticfiles/agent/vendor/frontend/manifest.json",
            *("_internal/staticfiles/" + name for name in assets.REQUIRED_STATIC),
        }
        document = {"schema": 1, "self_modify": False, "files": dict.fromkeys(names, {})}
        assets.validate_runtime_document(document)
        for name in (
            "_internal/agent/templates/agent/prompt_flow_panel.html",
            "_internal/staticfiles/agent/css/prompt_flow_panel.css",
            "_internal/staticfiles/agent/css/flow_canvas.css",
            "_internal/staticfiles/agent/js/flow-canvas-interactions.js",
            "_internal/staticfiles/agent/js/prompt-flow-panel-model.js",
            "_internal/staticfiles/agent/js/prompt-flow-panel.js",
            "docs/prompting-flow-designer.md",
            "docs/examples/prompting-kickoff.fpmt",
        ):
            with self.subTest(asset=name):
                incomplete = {**document, "files": {k: v for k, v in document["files"].items() if k != name}}
                with self.assertRaisesRegex(RuntimeError, "omits mandatory files"):
                    assets.validate_runtime_document(incomplete)

    def test_build_copies_every_required_root_source(self):
        # write_runtime_manifest() aborts the frozen build for any ROOT_SOURCES
        # file that build.py never copied; docs/visual-analysis-errors.md was
        # listed but not copied. Tree-carried entries are covered by SOURCE_TREES.
        text = (ROOT / "build.py").read_text(encoding="utf-8")
        for src, dst in assets.ROOT_SOURCES.items():
            if any(src.startswith(tree + "/") and dst == carried + src[len(tree):]
                   for tree, carried in assets.SOURCE_TREES):
                continue
            with self.subTest(source=src):
                named = {'"' + src + '"', '"' + src.rsplit("/", 1)[-1] + '"'}
                self.assertTrue(any(literal in text for literal in named),
                                f"build.py never copies required source {src} -> {dst}")


if __name__ == "__main__":
    unittest.main()
