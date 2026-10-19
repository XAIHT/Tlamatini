"""Packaging regressions; run in a visible foreground development console.

Copyright Angela López Mendoza · @angelahack1 — Tlamatini Author Banner.
"""
import ast
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
try:
    spec = importlib.util.spec_from_file_location("release_ownership_build", ROOT / "build.py")
    build = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(build)
finally:
    sys.path.pop(0)


class PayloadOwnershipTests(unittest.TestCase):
    def test_caches_are_removed_only_when_source_is_present(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            files = {
                "python/Lib/example.py": b"value = 42\n",
                "python/Lib/__pycache__/example.cpython-312.pyc": b"cache",
                "python/Lib/__pycache__/example.cpython-312.opt-1.pyc": b"optimized",
                "python/Lib/__pycache__/only_bytecode.cpython-312.pyc": b"keep",
                "_internal/library.py": b"pass\n",
                "_internal/library.pyc": b"legacy-cache",
                "_internal/only_bytecode.pyc": b"keep",
                "_internal/PYZ.pyz": b"keep-pyz",
                "_internal/base_library.zip": b"keep-stdlib",
                "agents/example.pyc": b"outside-cleanup-scope",
            }
            for name, content in files.items():
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(content)
            result = build.prune_regenerable_bytecode(root)
            removed = {"python/Lib/__pycache__/example.cpython-312.pyc",
                       "python/Lib/__pycache__/example.cpython-312.opt-1.pyc",
                       "_internal/library.pyc"}
            self.assertEqual(result["files"], len(removed))
            self.assertEqual(result["bytes"], sum(len(files[name]) for name in removed))
            for name, content in files.items():
                if name in removed:
                    self.assertFalse((root / name).exists())
                else:
                    self.assertEqual((root / name).read_bytes(), content)

    def test_frozen_boundary_refuses_uninspectable_or_present_libraries(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "_internal").mkdir()
            for names in (None, {"django", "av.container", "playwright.sync_api"}):
                with patch.object(build, "_read_pyz_module_names", return_value=names):
                    with self.assertRaises(RuntimeError):
                        build.verify_frozen_pool_libraries_absent(root)
            with patch.object(build, "_read_pyz_module_names", return_value={"django", "pymupdf"}):
                (root / "_internal/cv2").mkdir()
                with self.assertRaises(RuntimeError):
                    build.verify_frozen_pool_libraries_absent(root)
                (root / "_internal/cv2").rmdir()
                self.assertIsNone(build.verify_frozen_pool_libraries_absent(root))

    def test_web_sources_do_not_import_pool_libraries(self):
        offenders = []
        for source in (ROOT / "Tlamatini").rglob("*.py"):
            relative = source.relative_to(ROOT / "Tlamatini")
            if {"agents", "__pycache__", "tests", "tests_e2e"}.intersection(relative.parts):
                continue
            if source.name.startswith("test_") or source.name == "tests.py":
                continue
            for node in ast.walk(ast.parse(source.read_text(encoding="utf-8-sig"))):
                names = []
                if isinstance(node, ast.Import):
                    names = [alias.name for alias in node.names]
                elif isinstance(node, ast.ImportFrom) and not node.level:
                    names = [node.module or ""]
                elif isinstance(node, ast.Call) and node.args:
                    function = node.func
                    loader = (isinstance(function, ast.Name) and function.id == "__import__"
                              or isinstance(function, ast.Attribute) and function.attr == "import_module")
                    if loader and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
                        names = [node.args[0].value]
                if any(name.split(".", 1)[0] in build._FROZEN_POOL_ONLY_MODULES for name in names):
                    offenders.append(f"{relative}:{node.lineno}")
        self.assertEqual(offenders, [], "A new web-process use needs its own frozen dependency: " + ", ".join(offenders))

    def test_git_runtime_and_custom_commands_survive_installer_cleanup(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source"
            retained = ("cmd/git.exe", "usr/bin/bash.exe", "usr/bin/perl.exe",
                        "usr/share/man/git.html", "hooks/unins001.exe", "COPYING")
            omitted = ("unins001.exe", "unins001.dat", "unins001.msg")
            for name in (*retained, *omitted):
                path = source / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(name.encode())
            with patch.object(build, "_git_install_root_for_bundle", return_value=source):
                build.bundle_git(root / "output")
            for name in retained:
                self.assertEqual((root / "output/git" / name).read_bytes(), name.encode())
            for name in omitted:
                self.assertFalse((root / "output/git" / name).exists())
                self.assertTrue((source / name).exists())


class BrowserRevisionTests(unittest.TestCase):
    def test_carried_manifest_selects_exact_browsers_and_ffmpeg(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = root / "output"
            manifest = output / "python/Lib/site-packages/playwright/driver/package/browsers.json"
            manifest.parent.mkdir(parents=True)
            manifest.write_text(json.dumps({"browsers": [
                {"name": "chromium", "revision": "111", "installByDefault": True},
                {"name": "chromium-headless-shell", "revision": "111", "installByDefault": True},
                {"name": "ffmpeg", "revision": "222", "installByDefault": True},
            ]}), encoding="utf-8")
            cache = root / "ms-playwright"
            kept = {"chromium-111", "chromium_headless_shell-111", "ffmpeg-222", "winldd-1007"}
            stale = {"chromium-999", "chromium_headless_shell-999", "ffmpeg-999", "firefox-999"}
            for name in kept | stale:
                (cache / name).mkdir(parents=True)
                (cache / name / "runtime.bin").write_bytes(name.encode())
            with patch.dict(os.environ, {"LOCALAPPDATA": str(root), "TLAMATINI_BUNDLE_ALL_BROWSERS": ""}):
                build.bundle_playwright_browsers(output)
                self.assertEqual({path.name for path in (output / "ms-playwright").iterdir()}, kept)
                self.assertEqual({path.name for path in cache.iterdir()}, kept | stale)
                (cache / "ffmpeg-222/runtime.bin").unlink()
                (cache / "ffmpeg-222").rmdir()
                with self.assertRaisesRegex(RuntimeError, "ffmpeg-222"):
                    build.bundle_playwright_browsers(output)


if __name__ == "__main__":
    unittest.main()
