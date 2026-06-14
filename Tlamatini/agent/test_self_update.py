"""Tests for the self-update module (About ▸ Check for updates).

Covers the pure, side-effect-free logic: version comparison, release-asset
selection, the ``check_for_update`` JSON shape (with GitHub mocked), the
frozen-only guard on ``start_update``, and the staging helpers
(``_locate_pkg_zip`` / ``_flatten_to_exe``). The actual file swap lives in
``apply_update.ps1`` and is exercised manually.
"""
import os
import tempfile
import unittest
import zipfile
from unittest import mock

from agent import self_update


class VersionCompareTests(unittest.TestCase):
    def test_newer_patch_minor_major(self):
        self.assertTrue(self_update.is_newer("1.19.6", "1.19.5"))
        self.assertTrue(self_update.is_newer("1.20.0", "1.19.5"))
        self.assertTrue(self_update.is_newer("2.0.0", "1.19.5"))

    def test_same_or_older_is_not_newer(self):
        self.assertFalse(self_update.is_newer("1.19.5", "1.19.5"))
        self.assertFalse(self_update.is_newer("1.19.4", "1.19.5"))
        self.assertFalse(self_update.is_newer("1.9.9", "1.19.5"))  # 9 < 19, not string compare

    def test_v_prefix_tolerated(self):
        self.assertTrue(self_update.is_newer("v1.19.6", "1.19.5"))

    def test_prerelease_outranked_by_release(self):
        self.assertTrue(self_update.is_newer("1.19.5", "1.19.5-rc1"))
        self.assertFalse(self_update.is_newer("1.19.5-rc1", "1.19.5"))

    def test_garbage_does_not_crash(self):
        # Must return a bool, never raise.
        self.assertIsInstance(self_update.is_newer("not-a-version", "1.0.0"), bool)


class AssetSelectionTests(unittest.TestCase):
    def test_picks_release_bundle_zip(self):
        assets = [
            {"name": "source.tar.gz", "size": 10, "browser_download_url": "u1"},
            {"name": "Tlamatini_Release_v1.19.5_win11x64.zip", "size": 99, "browser_download_url": "u2"},
        ]
        chosen = self_update._select_asset(assets)
        self.assertEqual(chosen["name"], "Tlamatini_Release_v1.19.5_win11x64.zip")

    def test_falls_back_to_largest_zip(self):
        assets = [
            {"name": "a.zip", "size": 5, "browser_download_url": "u1"},
            {"name": "b.zip", "size": 50, "browser_download_url": "u2"},
        ]
        self.assertEqual(self_update._select_asset(assets)["name"], "b.zip")

    def test_no_zip_returns_none(self):
        self.assertIsNone(self_update._select_asset([{"name": "x.exe", "size": 1}]))
        self.assertIsNone(self_update._select_asset([]))


class CheckForUpdateTests(unittest.TestCase):
    _RELEASE = {
        "tag_name": "v1.19.5",
        "name": "Tlamatini v1.19.5 Win11x64",
        "html_url": "https://github.com/XAIHT/Tlamatini/releases/tag/v1.19.5",
        "body": "Release notes here.",
        "assets": [{
            "name": "Tlamatini_Release_v1.19.5_win11x64.zip",
            "browser_download_url": "https://example/dl.zip",
            "size": 1347004856,
        }],
    }

    def test_update_available_when_remote_is_newer(self):
        with mock.patch.object(self_update, "_github_latest", return_value=self._RELEASE), \
             mock.patch.object(self_update, "_current_version", return_value="1.19.4"):
            info = self_update.check_for_update()
        self.assertTrue(info["ok"])
        self.assertTrue(info["update_available"])
        self.assertEqual(info["latest"], "1.19.5")
        self.assertEqual(info["asset_name"], "Tlamatini_Release_v1.19.5_win11x64.zip")
        self.assertEqual(info["asset_size"], 1347004856)
        self.assertEqual(info["_asset_url"], "https://example/dl.zip")

    def test_no_update_when_same_version(self):
        with mock.patch.object(self_update, "_github_latest", return_value=self._RELEASE), \
             mock.patch.object(self_update, "_current_version", return_value="1.19.5"):
            info = self_update.check_for_update()
        self.assertTrue(info["ok"])
        self.assertFalse(info["update_available"])

    def test_network_error_is_reported_not_raised(self):
        with mock.patch.object(self_update, "_github_latest", side_effect=OSError("no net")):
            info = self_update.check_for_update()
        self.assertFalse(info["ok"])
        self.assertIn("GitHub", info["error"])


class StartUpdateGuardTests(unittest.TestCase):
    def test_source_mode_refuses(self):
        with mock.patch.object(self_update, "is_frozen", return_value=False):
            result = self_update.start_update()
        self.assertFalse(result["ok"])
        self.assertIn("frozen", result["error"].lower())


class StagingHelperTests(unittest.TestCase):
    def test_locate_pkg_zip_nested(self):
        with tempfile.TemporaryDirectory() as d:
            nested = os.path.join(d, "Tlamatini_Release_v1", "inner")
            os.makedirs(nested)
            target = os.path.join(nested, "pkg.zip")
            with open(target, "wb") as f:
                f.write(b"x")
            found = self_update._locate_pkg_zip(d)
            self.assertEqual(os.path.normcase(found), os.path.normcase(target))

    def test_locate_pkg_zip_absent(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertIsNone(self_update._locate_pkg_zip(d))

    def test_flatten_to_exe_flat(self):
        with tempfile.TemporaryDirectory() as d:
            open(os.path.join(d, "Tlamatini.exe"), "wb").close()
            self.assertEqual(self_update._flatten_to_exe(d), d)

    def test_flatten_to_exe_single_wrapper(self):
        with tempfile.TemporaryDirectory() as d:
            inner = os.path.join(d, "manage")
            os.makedirs(inner)
            open(os.path.join(inner, "Tlamatini.exe"), "wb").close()
            self.assertEqual(self_update._flatten_to_exe(d), inner)

    def test_select_and_extract_roundtrip(self):
        # Build a fake release bundle (release.zip -> pkg.zip -> Tlamatini.exe)
        with tempfile.TemporaryDirectory() as d:
            inner_exe = os.path.join(d, "Tlamatini.exe")
            open(inner_exe, "wb").close()
            pkg = os.path.join(d, "pkg.zip")
            with zipfile.ZipFile(pkg, "w") as zf:
                zf.write(inner_exe, "Tlamatini.exe")
            self.assertTrue(os.path.isfile(pkg))
            self.assertEqual(self_update._locate_pkg_zip(d), pkg)


if __name__ == "__main__":
    unittest.main()
