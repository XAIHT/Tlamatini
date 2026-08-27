"""Pin the ENGLISH version-metadata + update-detection expectations.

Both failure modes below are invisible from the UI, so a small guard is cheap
insurance against a future tag shape (``v2.0.0-rc.1``, a ``+build`` local part, a
date-stamped tag) silently zeroing the ``.exe`` VERSIONINFO or breaking update
detection:

  * ``version.semver_to_win32_tuple`` must map a real SemVer to a correct 4-tuple
    (a bad parse falls open to ``(0, 0, 0, 0)`` -> ProductVersion 0.0.0.0);
  * ``self_update.is_newer`` must detect a PATCH-level bump (a crude numeric split
    that stops at the first non-digit field makes ``1.50.1`` compare equal to
    ``1.50.0`` and a patch release is never offered).

English tags are plain SemVer, so ``strip_edition_suffix`` (the Spanish tree's
``vX.Y.Zs`` edition-letter workaround) is DELIBERATELY ABSENT here and must stay so
-- porting it would be dead code that also masks a genuinely malformed tag.
"""
import unittest

from agent import version, self_update


class Win32VersionTupleTests(unittest.TestCase):
    def test_plain_semver(self):
        self.assertEqual(version.semver_to_win32_tuple("1.50.0"), (1, 50, 0, 0))

    def test_prerelease_keeps_core_numbers(self):
        self.assertEqual(version.semver_to_win32_tuple("2.0.0-rc.1"), (2, 0, 0, 0))

    def test_build_metadata_keeps_core_numbers(self):
        self.assertEqual(version.semver_to_win32_tuple("1.50.0+build.491"), (1, 50, 0, 0))

    def test_parse_semver_accepts_current_tag_shapes(self):
        for tag in ("1.50.0", "1.49.1", "1.48.17", "2.0.0-rc.1"):
            self.assertIsNotNone(version.parse_semver(tag), f"parse_semver rejected {tag}")


class UpdateDetectionTests(unittest.TestCase):
    def test_patch_bump_is_newer(self):
        self.assertTrue(self_update.is_newer("1.50.1", "1.50.0"))

    def test_minor_bump_is_newer(self):
        self.assertTrue(self_update.is_newer("1.50.0", "1.49.1"))

    def test_equal_is_not_newer(self):
        self.assertFalse(self_update.is_newer("1.50.0", "1.50.0"))

    def test_older_is_not_newer(self):
        self.assertFalse(self_update.is_newer("1.49.1", "1.50.0"))


class EnglishTreeStaysCleanSemverTests(unittest.TestCase):
    def test_no_spanish_edition_suffix_helper(self):
        # The English tree must NOT carry the Spanish edition-letter workaround.
        from pathlib import Path
        src = Path(version.__file__).read_text(encoding="utf-8", errors="replace")
        self.assertNotIn("strip_edition_suffix", src)


if __name__ == "__main__":
    unittest.main()
