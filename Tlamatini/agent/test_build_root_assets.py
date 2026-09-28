# Tlamatini Author Banner — Angela López Mendoza
"""Physical packaging regressions; run in a verified visible foreground console."""

import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
try:
    import build_runtime_assets as assets
finally:
    sys.path.remove(str(ROOT))


class RootCarrierTests(unittest.TestCase):
    def test_new_inventory_entry_is_copied_without_another_build_list(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source, stage = root / "source", root / "stage"
            source.mkdir()
            (source / "new_helper.py").write_bytes(b"# new helper\n")
            with patch.dict(assets.ROOT_SOURCES, {"new_helper.py": "tools/new_helper.py"}, clear=True):
                assets.copy_root_sources(source, stage)
            self.assertEqual((stage / "tools/new_helper.py").read_bytes(), b"# new helper\n")

    def test_missing_or_empty_input_refuses_before_copying_any_file(self):
        for empty in (False, True):
            with self.subTest(empty=empty), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                (root / "present.py").write_bytes(b"new")
                if empty:
                    (root / "absent.py").touch()
                stage = root / "stage"
                stage.mkdir()
                (stage / "present.py").write_bytes(b"old")
                with patch.dict(assets.ROOT_SOURCES, {"present.py": "present.py", "absent.py": "absent.py"}, clear=True):
                    with self.assertRaisesRegex(RuntimeError, "missing or empty"):
                        assets.copy_root_sources(root, stage)
                self.assertEqual((stage / "present.py").read_bytes(), b"old")

    def test_post_freeze_source_drift_still_fails_the_receipt(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "helper.py").write_bytes(b"baseline")
            with patch.dict(assets.ROOT_SOURCES, {"helper.py": "helper.py"}, clear=True), patch.object(assets, "SOURCE_TREES", ()):
                baseline = assets.capture_source_payload(root)
                (root / "helper.py").write_bytes(b"changed during build")
                assets.copy_root_sources(root, root / "stage")
                with self.assertRaisesRegex(RuntimeError, "lost or changed.*helper.py"):
                    assets.write_runtime_manifest(root / "stage", baseline, version="1.0.0", self_modify=False)


class ReleaseIntegrityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.stage = self.root / "stage"
        assets.copy_root_sources(ROOT, self.stage)
        # Synthetic runtime binaries: these tests exercise package/staging
        # integrity, not whether an executable can launch.
        required = {
            "Tlamatini.exe", "python/python.exe", "jre/bin/java.exe", "git/cmd/git.exe",
            "jd-cli/jd-cli.jar", "_internal/db.sqlite3", "_internal/pymupdf/_mupdf.pyd",
            "_internal/pymupdf/_extra.pyd", "_internal/pymupdf/mupdfcpp64.dll",
            "_internal/staticfiles/agent/vendor/frontend/manifest.json",
            "ms-playwright/chromium-1/chrome-win/chrome.exe",
            "ms-playwright/chromium_headless_shell-1/chrome-win/headless_shell.exe",
            *("_internal/staticfiles/" + name for name in assets.REQUIRED_STATIC),
        }
        for name in required:
            target = self.stage / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(b"fixture runtime asset")
        self.expected = {dst: assets.file_record(ROOT / src) for src, dst in assets.ROOT_SOURCES.items()}
        assets.write_runtime_manifest(self.stage, self.expected, version="1.0.0", self_modify=False)

    def package(self):
        archive = self.root / "pkg.zip"
        with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as bundle:
            for path in self.stage.rglob("*"):
                if path.is_file():
                    bundle.write(path, path.relative_to(self.stage).as_posix())
        return archive

    def test_required_voice_helpers_survive_zip_and_extracted_update(self):
        archive = self.package()
        assets.verify_package(archive, expected_version="1.0.0")
        extracted = self.root / "extracted"
        with zipfile.ZipFile(archive) as bundle:
            bundle.extractall(extracted)
        assets.verify_staged_payload(extracted, expected_version="1.0.0")
        for name in ("chat_voice_settings.py", "agents/whisperer/chat_worker.py"):
            self.assertEqual(assets.file_record(extracted / name), self.expected[name])

    def test_packaged_worker_resolves_its_carried_settings_helper(self):
        worker_path = self.stage / "agents/whisperer/chat_worker.py"
        spec = importlib.util.spec_from_file_location("packaged_chat_worker", worker_path)
        worker = importlib.util.module_from_spec(spec)
        with patch.object(sys, "path", list(sys.path)), patch.dict(sys.modules):
            sys.modules.pop("chat_voice_settings", None)
            spec.loader.exec_module(worker)
            helper = sys.modules["chat_voice_settings"]
            self.assertEqual(Path(helper.__file__), self.stage / "chat_voice_settings.py")
            self.assertIs(worker.validate_capture_settings, helper.validate_capture_settings)

    def test_every_root_asset_is_mandatory_even_in_a_self_consistent_receipt(self):
        document = json.loads((self.stage / assets.MANIFEST_NAME).read_text(encoding="utf-8"))
        for name in assets.ROOT_SOURCES.values():
            with self.subTest(asset=name):
                incomplete = {**document, "files": {k: v for k, v in document["files"].items() if k != name}}
                with self.assertRaisesRegex(RuntimeError, "omits mandatory files"):
                    assets.validate_runtime_document(incomplete)

    def test_update_rejects_voice_omission_even_when_removed_from_receipt(self):
        (self.stage / "chat_voice_settings.py").unlink()
        receipt = self.stage / assets.MANIFEST_NAME
        document = json.loads(receipt.read_text(encoding="utf-8"))
        del document["files"]["chat_voice_settings.py"]
        receipt.write_text(json.dumps(document), encoding="utf-8")
        with self.assertRaisesRegex(RuntimeError, "omits mandatory files.*chat_voice_settings"):
            assets.verify_package(self.package())
        with self.assertRaisesRegex(RuntimeError, "omits mandatory files.*chat_voice_settings"):
            assets.verify_staged_payload(self.stage)

    def test_tampered_helper_rejected_in_archive_and_staging(self):
        (self.stage / "chat_voice_settings.py").write_bytes(b"corrupted helper")
        with self.assertRaisesRegex(RuntimeError, "SHA-256 receipt"):
            assets.verify_package(self.package())
        with self.assertRaisesRegex(RuntimeError, "differs from its receipt"):
            assets.verify_staged_payload(self.stage)

    def test_unmanifested_extra_rejected_in_archive_and_staging(self):
        (self.stage / "unexpected.py").write_bytes(b"unexpected")
        with self.assertRaisesRegex(RuntimeError, "membership differs"):
            assets.verify_package(self.package())
        with self.assertRaisesRegex(RuntimeError, "membership differs"):
            assets.verify_staged_payload(self.stage)

    def test_self_modify_requires_snapshot_and_both_identity_copies(self):
        with self.assertRaisesRegex(RuntimeError, "missing or empty"):
            assets.write_runtime_manifest(self.stage, self.expected, version="1.0.0", self_modify=True)
        for name in ("Tlamatini.md", "_internal/agent/Tlamatini.md", *(
            "TlamatiniSourceCode/" + value for value in (
                "build.py", "build_runtime_assets.py", "copy_source_assets.py",
                "_SOURCE_SNAPSHOT_MANIFEST.json", "_REBUILD_INSTRUCTIONS.md"))):
            target = self.stage / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(b"self-modify fixture")
        assets.write_runtime_manifest(self.stage, self.expected, version="1.0.0", self_modify=True)
        assets.verify_package(self.package())
        assets.verify_staged_payload(self.stage)


class InclusionSweepTests(unittest.TestCase):
    def test_update_sweep_resolves_shared_carrier_and_detects_its_removal(self):
        spec = importlib.util.spec_from_file_location("root_asset_sweep", ROOT / ".claude/skills/tlamatini-self-update-inclusion/scripts/sweep_self_update.py")
        sweep = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(sweep)
        source = (ROOT / "build.py").read_text(encoding="utf-8")
        self.assertEqual(sweep.required_file_sources(source, assets.ROOT_SOURCES), set(assets.ROOT_SOURCES))
        self.assertEqual(sweep.required_file_sources("pass", assets.ROOT_SOURCES), set())

    def test_no_git_source_validation_checks_files_without_launching_a_process(self):
        with patch.object(assets.subprocess, "run", side_effect=AssertionError("Git/process forbidden")):
            assets.validate_source_assets(ROOT, check_tracked=False)


if __name__ == "__main__":
    unittest.main()
