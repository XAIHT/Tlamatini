# Tlamatini Author Banner — Angela López Mendoza
"""Release version regressions; run in a verified visible foreground console.

Build processes, private-data synchronization and publication are mocked. Only
fixture files in TemporaryDirectory are mutated; no real release is built.
"""

from contextlib import ExitStack, redirect_stdout
import io
import os
import re
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import build_complete_private_release as private  # noqa: E402
import build_complete_public_release as public  # noqa: E402
import versioning  # noqa: E402


class ReleaseVersionPinningTests(unittest.TestCase):
    def run_release(self, builder, *, argv=(), ambient="", fail_stage=None):
        with tempfile.TemporaryDirectory() as temporary, ExitStack() as stack:
            root = Path(temporary)
            config = root / "config.json"
            original = b'{"fixture": "original"}\r\n'
            config.write_bytes(original)
            stages = {builder.BUILD, builder.BUILD_UNINST, builder.BUILD_INST}
            dispatched = []
            git_version = ["1.89.0"]
            output = stack.enter_context(redirect_stdout(io.StringIO()))
            stack.enter_context(patch.dict(os.environ, {
                "TLAMATINI_VERSION": ambient,
                "CHECK_PRIVATE_DATA_TARGETS": "",
            }))
            git = stack.enter_context(patch.object(
                versioning, "derive_version_from_git", side_effect=lambda: git_version[0]))

            def dispatch(command):
                script = Path(command[1])
                if script in stages:
                    child_argv = list(command[1:])
                    explicit = versioning.extract_cli_version(child_argv)
                    actual = versioning.resolve_build_version(explicit)
                    dispatched.append((script.name, actual, explicit, child_argv))
                    # A new tag appears after the application starts building.
                    git_version[0] = "1.90.0"
                    return 1 if script.name == fail_stage else 0
                self.assertEqual(script, builder.REGEN)
                if "push-able" in command:
                    config.write_bytes(b'{"fixture": "scrubbed"}')
                return 0

            replacements = {
                "REPO_ROOT": root,
                "DIST": root / "dist",
                "assert_system_python": Mock(),
                "run": Mock(side_effect=dispatch),
                "assert_self_modify_payload": Mock(),
                "newest_release_dir": Mock(return_value=root / "dist" / "Tlamatini_Release_v1.89.0"),
                "create_release_archive": Mock(return_value=root / "release.zip"),
            }
            if builder is public:
                replacements.update({
                    "REGEN_TOUCHED": [config],
                    "EXTERNAL_MCPS": root / "absent-mcps.json",
                    "VERIFY_EXTRACT": root / "absent-extraction",
                    "default_targets_file": Mock(return_value=None),
                    "load_targets_values": Mock(return_value=[]),
                    "privacy_preflight": Mock(return_value=[]),
                    "scrub_tree": Mock(return_value=0),
                    "resolve_verify_root": Mock(return_value=root),
                    "verify_clean": Mock(return_value=0),
                })
            else:
                replacements.update({
                    "CONTACTS_PRIVATE": root / "absent-contacts.json",
                    "sync_contacts_private": Mock(),
                    "_load_contacts_from_file": Mock(return_value=[]),
                    "sync_external_mcps_private": Mock(),
                    "choose_data_keys": Mock(),
                })
            stack.enter_context(patch.multiple(builder, **replacements))
            if fail_stage:
                with self.assertRaisesRegex(SystemExit, re.escape(fail_stage) + " failed"):
                    builder.main(list(argv))
                replacements["create_release_archive"].assert_not_called()
            else:
                self.assertEqual(builder.main(list(argv)), 0)
                replacements["create_release_archive"].assert_called_once()
            self.assertEqual(config.read_bytes(), original, "public restoration must retain original bytes")
            return dispatched, git.call_count, output.getvalue()

    def assert_versions(self, dispatched, expected):
        self.assertEqual([row[0] for row in dispatched],
                         ["build.py", "build_uninstaller.py", "build_installer.py"])
        self.assertEqual([row[1] for row in dispatched], [expected] * 3)
        self.assertEqual([row[2] for row in dispatched], [expected] * 3,
                         "every child must receive the parseable --version flag")

    def test_new_git_tag_during_build_cannot_split_artifact_versions(self):
        for builder in (public, private):
            with self.subTest(builder=builder.__name__):
                dispatched, resolutions, output = self.run_release(builder)
                self.assert_versions(dispatched, "1.89.0")
                self.assertEqual(resolutions, 1, "resolve Git only at release startup")
                self.assertIn("1.89.0", output)

    def test_explicit_version_beats_environment_and_survives_child_parsing(self):
        for builder in (public, private):
            for args in (("--version", "v2.0.0-rc.1"), ("--version=2.0.0-rc.1",)):
                with self.subTest(builder=builder.__name__, args=args):
                    dispatched, resolutions, _ = self.run_release(
                        builder, argv=args, ambient="1.88.0")
                    self.assert_versions(dispatched, "2.0.0-rc.1")
                    self.assertEqual(resolutions, 0)

    def test_environment_version_is_pinned_when_cli_is_absent(self):
        for builder in (public, private):
            with self.subTest(builder=builder.__name__):
                dispatched, resolutions, _ = self.run_release(builder, ambient="v1.90.0")
                self.assert_versions(dispatched, "1.90.0")
                self.assertEqual(resolutions, 0)

    def test_version_forwarding_preserves_self_modify_decision(self):
        for builder in (public, private):
            for args, expected in (((), "--no-self-modify"),
                                   (("--self-modify",), "--self-modify"),
                                   (("--self-modify", "--no-self-modify"), "--no-self-modify")):
                with self.subTest(builder=builder.__name__, args=args):
                    dispatched, _, _ = self.run_release(builder, argv=args)
                    self.assert_versions(dispatched, "1.89.0")
                    self.assertEqual(dispatched[0][3], [str(builder.BUILD), expected])

    def test_public_build_failure_restores_fixture_configuration_at_every_stage(self):
        for stage in ("build.py", "build_uninstaller.py", "build_installer.py"):
            with self.subTest(stage=stage):
                dispatched, _, output = self.run_release(public, fail_stage=stage)
                self.assertEqual(dispatched[-1][0], stage)
                self.assertIn("build did not complete", output)


if __name__ == "__main__":
    unittest.main(verbosity=2)
