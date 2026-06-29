# ═══════════════════════════════════════════════════════════════════
#   ✦  T L A M A T I N I  ✦   —   "one who knows"
#
#   Created by  Angela López Mendoza   ·   @angelahack1
#   Developer · Architect · Creator of Tlamatini
#
#   Every line of this file was written by Angela López Mendoza.
# ═══════════════════════════════════════════════════════════════════
#   Tlamatini Author Banner — do not remove (releases scrub the name automatically)
"""Tests for ``agent/windows_app_registration.py`` (Installed-apps / ARP entry).

The registry writes can only be exercised live on Windows, so the platform
behaviour, the gating (no Uninstaller.exe → no entry), the source-mode no-op,
and a full live write→read→delete round-trip are pinned here. Everything is
HKCU/non-admin and idempotent.

Run:
    python manage.py test agent.test_windows_app_registration
"""
import os
import sys
import tempfile
import unittest
from unittest.mock import patch

from agent import windows_app_registration as war

_IS_WINDOWS = os.name == "nt"


class SurfaceTests(unittest.TestCase):
    def test_is_supported_matches_platform(self):
        self.assertEqual(war.is_supported(), os.name == "nt")

    def test_key_name_and_root_are_stable(self):
        # The uninstaller deletes this exact path — keep them in lockstep.
        self.assertEqual(war.ARP_KEY_NAME, "Tlamatini")
        self.assertIn(r"CurrentVersion\Uninstall", war.ARP_UNINSTALL_ROOT)


class GatingTests(unittest.TestCase):
    def test_noop_off_windows(self):
        with patch.object(war, "is_supported", return_value=False):
            self.assertFalse(war.register_uninstall_entry(r"C:\whatever"))
            self.assertFalse(war.unregister_uninstall_entry())

    def test_register_skips_when_no_uninstaller_present(self):
        # An empty dir has no Uninstaller.exe → must NOT advertise a dead entry.
        with tempfile.TemporaryDirectory() as d, \
             patch.object(war, "is_supported", return_value=True):
            self.assertFalse(war.register_uninstall_entry(d))

    def test_self_heal_noop_when_not_frozen(self):
        # Source mode (sys.frozen unset) → always a no-op.
        with patch.object(sys, "frozen", False, create=True):
            self.assertFalse(war.self_heal_for_frozen())

    def test_self_heal_noop_when_frozen_but_no_uninstaller(self):
        with tempfile.TemporaryDirectory() as d, \
             patch.object(war, "is_supported", return_value=True), \
             patch.object(sys, "frozen", True, create=True), \
             patch.object(sys, "executable", os.path.join(d, "Tlamatini.exe")):
            self.assertFalse(war.self_heal_for_frozen())


class RegisterFailOpenTests(unittest.TestCase):
    def test_register_is_failopen_on_internal_error(self):
        # A blow-up below the is_supported / file-present guards must yield
        # False, never raise into the installer / Django startup.
        with tempfile.TemporaryDirectory() as d, \
             patch.object(war, "is_supported", return_value=True), \
             patch.object(war.os.path, "isfile", side_effect=RuntimeError("boom")):
            self.assertFalse(war.register_uninstall_entry(d))


@unittest.skipUnless(_IS_WINDOWS, "Windows-only registry round-trip")
class LiveRoundTripTests(unittest.TestCase):
    def test_register_then_unregister_live(self):
        import winreg
        with tempfile.TemporaryDirectory() as d:
            # Minimal "install": an Uninstaller.exe + an exe so DisplayIcon
            # resolves. Contents are irrelevant to the registry write.
            open(os.path.join(d, "Uninstaller.exe"), "wb").close()
            open(os.path.join(d, "Tlamatini.exe"), "wb").close()

            self.assertTrue(
                war.register_uninstall_entry(d, version="9.9.9", compute_size=False)
            )
            key_path = rf"{war.ARP_UNINSTALL_ROOT}\{war.ARP_KEY_NAME}"
            try:
                with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path) as key:
                    name, _ = winreg.QueryValueEx(key, "DisplayName")
                    self.assertEqual(name, "Tlamatini")
                    ver, _ = winreg.QueryValueEx(key, "DisplayVersion")
                    self.assertEqual(ver, "9.9.9")
                    uninst, _ = winreg.QueryValueEx(key, "UninstallString")
                    self.assertIn("Uninstaller.exe", uninst)
                    nomod, _ = winreg.QueryValueEx(key, "NoModify")
                    self.assertEqual(nomod, 1)
            finally:
                self.assertTrue(war.unregister_uninstall_entry())
            # Second delete is idempotent (already gone → success).
            self.assertTrue(war.unregister_uninstall_entry())


if __name__ == "__main__":
    unittest.main()
