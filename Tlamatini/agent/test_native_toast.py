"""Tests for native Windows toast notifications (``agent/native_toast.py``).

A toast cannot be visually asserted in an automated test, so we mock the
``subprocess`` boundary and pin the high-risk pure logic: XML escaping, the
toast-script wrapper, powershell.exe (NOT pwsh) resolution, fail-open
behaviour, and the HKCU/non-admin registration surface. The live "does a
banner actually appear / does the icon render / does a click focus the tab"
checks are necessarily manual on a real desktop.

Run:
    python manage.py test agent.test_native_toast
"""
import os
import unittest
from unittest.mock import MagicMock, patch

from agent import native_toast

_IS_WINDOWS = os.name == "nt"


# ═══════════════════════════════════════════════════════════════════════════
# 1. Module surface / platform behaviour
# ═══════════════════════════════════════════════════════════════════════════
class ToastModuleSurfaceTests(unittest.TestCase):
    def test_is_supported_matches_platform(self):
        self.assertEqual(native_toast.is_supported(), os.name == "nt")

    def test_aumid_matches_managepy_identity(self):
        # MUST equal the AUMID manage.py sets, or the toast won't share the
        # registered identity (name/icon/Action-Center persistence).
        self.assertEqual(native_toast.AUMID, "XAIHT.Tlamatini.Server")

    def test_focus_launch_arg_uses_custom_protocol(self):
        # Click activation must go through our protocol, never an http URL
        # (an http launch can open a NEW tab — the one thing forbidden).
        self.assertTrue(native_toast.FOCUS_LAUNCH_ARG.startswith("tlamatini:"))
        self.assertNotIn("http", native_toast.FOCUS_LAUNCH_ARG)


# ═══════════════════════════════════════════════════════════════════════════
# 2. Toast XML building (escaping + structure)
# ═══════════════════════════════════════════════════════════════════════════
class ToastXmlTests(unittest.TestCase):
    def test_basic_structure(self):
        xml = native_toast.build_toast_xml("Title", "Body")
        self.assertIn("<toast", xml)
        self.assertIn('template="ToastGeneric"', xml)
        self.assertIn("<text>Title</text>", xml)
        self.assertIn("<text>Body</text>", xml)

    def test_xml_escapes_dangerous_chars_in_text(self):
        xml = native_toast.build_toast_xml('A & B <x>', 'q"z \'p\' & <b>')
        # Raw, unescaped markup must not leak into the body text.
        self.assertNotIn("<x>", xml)
        self.assertNotIn("<b>", xml)
        self.assertIn("&amp;", xml)
        self.assertIn("&lt;", xml)

    def test_clickable_adds_protocol_activation(self):
        xml = native_toast.build_toast_xml("t", "b", launch_arg="tlamatini:focus")
        self.assertIn('activationType="protocol"', xml)
        self.assertIn('launch="tlamatini:focus"', xml)

    def test_not_clickable_omits_activation(self):
        xml = native_toast.build_toast_xml("t", "b", launch_arg=None)
        self.assertNotIn("activationType", xml)
        self.assertNotIn("launch=", xml)

    def test_image_included_only_when_path_exists(self):
        with patch("os.path.exists", return_value=True):
            xml = native_toast.build_toast_xml("t", "b", image_path=r"C:\x\Tlamatini.png")
        self.assertIn('placement="appLogoOverride"', xml)
        self.assertIn("Tlamatini.png", xml)

    def test_image_omitted_when_missing(self):
        with patch("os.path.exists", return_value=False):
            xml = native_toast.build_toast_xml("t", "b", image_path=r"C:\x\nope.png")
        self.assertNotIn("appLogoOverride", xml)

    def test_sound_toggle(self):
        loud = native_toast.build_toast_xml("t", "b", sound=True)
        quiet = native_toast.build_toast_xml("t", "b", sound=False)
        self.assertIn("ms-winsoundevent", loud)
        self.assertIn('silent="true"', quiet)


# ═══════════════════════════════════════════════════════════════════════════
# 3. The PowerShell wrapper script
# ═══════════════════════════════════════════════════════════════════════════
class ToastScriptTests(unittest.TestCase):
    def test_script_embeds_aumid_and_xml(self):
        xml = native_toast.build_toast_xml("t", "b")
        script = native_toast._build_toast_script(xml, aumid="XAIHT.Tlamatini.Server")
        self.assertIn("CreateToastNotifier('XAIHT.Tlamatini.Server')", script)
        self.assertIn("ToastNotificationManager", script)
        self.assertIn("<toast", script)  # the xml here-string

    def test_script_uses_winrt_contenttype(self):
        # The WinRT projection that only Windows PowerShell 5.1 understands.
        script = native_toast._build_toast_script("<toast/>")
        self.assertIn("ContentType = WindowsRuntime", script)


# ═══════════════════════════════════════════════════════════════════════════
# 4. powershell.exe resolution — NEVER pwsh
# ═══════════════════════════════════════════════════════════════════════════
class PowerShellResolutionTests(unittest.TestCase):
    @unittest.skipUnless(_IS_WINDOWS, "Windows-only path")
    def test_resolves_windows_powershell_51(self):
        path = native_toast.resolve_powershell()
        self.assertIsNotNone(path)
        low = path.lower()
        # Must be Windows PowerShell, not PowerShell 7.
        self.assertTrue(low.endswith("powershell.exe"))
        self.assertNotIn("pwsh", low)

    def test_non_windows_returns_none(self):
        with patch.object(native_toast, "is_supported", return_value=False):
            self.assertIsNone(native_toast.resolve_powershell())


# ═══════════════════════════════════════════════════════════════════════════
# 5. show_toast — fail-open, never raises, invokes powershell not pwsh
# ═══════════════════════════════════════════════════════════════════════════
class ShowToastTests(unittest.TestCase):
    def test_non_windows_is_noop_false(self):
        with patch.object(native_toast, "is_supported", return_value=False):
            self.assertFalse(native_toast.show_toast("t", "b"))

    def test_no_powershell_returns_false(self):
        with patch.object(native_toast, "is_supported", return_value=True), \
             patch.object(native_toast, "resolve_powershell", return_value=None):
            self.assertFalse(native_toast.show_toast("t", "b"))

    def test_success_path_invokes_powershell_exe(self):
        fake = MagicMock(returncode=0, stdout=b"", stderr=b"")
        with patch.object(native_toast, "is_supported", return_value=True), \
             patch.object(native_toast, "resolve_powershell",
                          return_value=r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe"), \
             patch.object(native_toast, "resolve_toast_icon", return_value=None), \
             patch("subprocess.run", return_value=fake) as run:
            ok = native_toast.show_toast("t", "b")
        self.assertTrue(ok)
        argv = run.call_args[0][0]
        self.assertTrue(argv[0].lower().endswith("powershell.exe"))
        self.assertNotIn("pwsh", argv[0].lower())
        self.assertIn("-File", argv)

    def test_nonzero_exit_returns_false(self):
        fake = MagicMock(returncode=1, stdout=b"", stderr=b"boom")
        with patch.object(native_toast, "is_supported", return_value=True), \
             patch.object(native_toast, "resolve_powershell", return_value="powershell.exe"), \
             patch.object(native_toast, "resolve_toast_icon", return_value=None), \
             patch("subprocess.run", return_value=fake):
            self.assertFalse(native_toast.show_toast("t", "b"))

    def test_exception_is_failopen_not_raised(self):
        with patch.object(native_toast, "is_supported", return_value=True), \
             patch.object(native_toast, "resolve_powershell", return_value="powershell.exe"), \
             patch.object(native_toast, "resolve_toast_icon", return_value=None), \
             patch("subprocess.run", side_effect=RuntimeError("kaboom")):
            # Must NOT raise — a missed toast can't crash the Notifier.
            self.assertFalse(native_toast.show_toast("t", "b"))


# ═══════════════════════════════════════════════════════════════════════════
# 6. Registration — HKCU/non-admin, fail-open
# ═══════════════════════════════════════════════════════════════════════════
class RegistrationTests(unittest.TestCase):
    def test_register_identity_noop_off_windows(self):
        with patch.object(native_toast, "is_supported", return_value=False):
            self.assertFalse(native_toast.register_toast_identity())

    def test_register_protocol_noop_off_windows(self):
        with patch.object(native_toast, "is_supported", return_value=False):
            self.assertFalse(native_toast.register_focus_protocol())

    def test_register_all_completes_without_raising(self):
        # register_all() relies on its callees being fail-open. Called with the
        # registration functions stubbed to return cleanly, it must complete
        # and return None (apps.py also wraps the call in try/except as a
        # second backstop).
        with patch.object(native_toast, "register_toast_identity", return_value=True) as ri, \
             patch.object(native_toast, "register_focus_protocol", return_value=True) as rp:
            self.assertIsNone(native_toast.register_all())
            ri.assert_called_once()
            rp.assert_called_once()

    def test_register_callees_are_failopen_on_internal_error(self):
        # The fail-open layer: a winreg explosion must yield False, not raise.
        with patch.object(native_toast, "is_supported", return_value=True), \
             patch.object(native_toast, "resolve_toast_icon", side_effect=RuntimeError("x")):
            self.assertFalse(native_toast.register_toast_identity())

    @unittest.skipUnless(_IS_WINDOWS, "Windows-only registry")
    def test_identity_and_protocol_register_live(self):
        # Real HKCU writes (non-elevated). These are idempotent.
        self.assertTrue(native_toast.register_toast_identity())
        self.assertTrue(native_toast.register_focus_protocol())

    @unittest.skipUnless(_IS_WINDOWS, "Windows-only path")
    def test_focus_helper_script_is_valid_powershell_shape(self):
        # The Add-Type P/Invoke block is the riskiest piece; pin its shape.
        self.assertIn("AttachThreadInput", native_toast.FOCUS_HELPER_PS1)
        self.assertIn("SetForegroundWindow", native_toast.FOCUS_HELPER_PS1)
        self.assertIn("EnumWindows", native_toast.FOCUS_HELPER_PS1)
        # Must not clobber the $pid automatic variable.
        self.assertNotIn("$pid =", native_toast.FOCUS_HELPER_PS1)


if __name__ == "__main__":
    unittest.main()
