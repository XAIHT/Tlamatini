"""Guard the Blue-hat security toolkit's CARRIAGE + EVIDENCE-carryover contracts.

`security/automated_tests_of_security_assets.py` exists, but nothing runs it and
nothing guards the contracts AROUND it. This test pins those contracts so they
cannot rot silently:

  * ``build.py`` still ships ``security/`` and still omits ``security_logs``
  * ``copy_source_assets.py`` still prunes ``security_logs``
  * ``.gitignore`` still excludes ``/security/security_logs/``
  * the release scrubber + private-data scanner both SKIP ``security_logs`` (G2)
  * the self-update stash/restore pair stays a PAIR and never adds ``security``
    to ``$Preserve`` (G1)
  * the launchers still point at the right ``.ps1`` files
  * the docs describe behaviour that actually exists (the carryover, G4)

Ported (not copied) from the Tlamatini-Spanish tree. English specifics: the harness
helper is ``take_shot`` (Spanish uses ``toma_foto``); doc assertions use the English
"Blue-hat" wording. The Spanish-only ``SpanishEditionAdaptationTests`` is dropped.
"""
import re
import unittest
from pathlib import Path

# <repo>/Tlamatini/agent/<thisfile>  ->  parents[2] == repo root
REPO_ROOT = Path(__file__).resolve().parents[2]
SECURITY = REPO_ROOT / "security"


def _read(path) -> str:
    return Path(path).read_text(encoding="utf-8", errors="replace")


class AssetsPresentTests(unittest.TestCase):
    ASSETS = (
        "tlamatini_defender.ps1",
        "tlamatini_whitelist_v2.ps1",
        "run_defender.bat",
        "enable_tlamatini_v2.bat",
        "automated_tests_of_security_assets.py",
        "README.md",
    )

    def test_security_dir_exists(self):
        self.assertTrue(SECURITY.is_dir(), f"missing security/ at {SECURITY}")

    def test_all_assets_present(self):
        for name in self.ASSETS:
            self.assertTrue((SECURITY / name).is_file(), f"missing security/{name}")

    def test_launchers_point_at_the_right_scripts(self):
        self.assertIn("tlamatini_defender.ps1", _read(SECURITY / "run_defender.bat"))
        self.assertIn("tlamatini_whitelist_v2.ps1", _read(SECURITY / "enable_tlamatini_v2.bat"))

    def test_harness_uses_take_shot_not_toma_foto(self):
        # English keeps take_shot; toma_foto is the Spanish tree's helper name.
        h = _read(SECURITY / "automated_tests_of_security_assets.py")
        self.assertIn("take_shot", h)
        self.assertNotIn("toma_foto", h)

    def test_harness_forbids_real_PIL_use(self):
        # TRAP (inherited from the Spanish tree): the harness NAMES ImageGrab in
        # order to FORBID it, so assert on real USE, never on the bare word.
        h = _read(SECURITY / "automated_tests_of_security_assets.py")
        self.assertNotIn("from PIL", h)
        self.assertNotIn("import PIL", h)
        self.assertNotIn("ImageGrab.grab(", h)
        self.assertIn("Shoter", h, "the harness must screenshot through Shoter")


class BuildCarriageTests(unittest.TestCase):
    def test_build_ships_security_and_omits_logs(self):
        b = _read(REPO_ROOT / "build.py")
        self.assertIn('Path("security")', b)
        self.assertRegex(b, r'ignore_patterns\([^)]*"security_logs"')

    def test_copy_source_assets_prunes_security_logs(self):
        c = _read(REPO_ROOT / "copy_source_assets.py")
        self.assertIn("EXCLUDED_DIR_NAMES", c)
        self.assertIn('"security_logs"', c)

    def test_gitignore_excludes_security_logs(self):
        self.assertIn("/security/security_logs/", _read(REPO_ROOT / ".gitignore"))

    def test_scrubbers_skip_security_logs(self):
        # G2: neither the public-release scrubber nor the private-data scanner
        # should walk the operator's own forensic evidence.
        for fname in ("build_complete_public_release.py", "check_private_data.py"):
            self.assertIn('"security_logs"', _read(REPO_ROOT / fname),
                          f"{fname} SKIP_DIRS is missing security_logs")


class SelfUpdateEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.apply = _read(REPO_ROOT / "apply_update.ps1")

    def test_security_is_NOT_in_preserve(self):
        # security\ is application code and MUST be replaced; only the EVIDENCE
        # is carried. Adding 'security' to $Preserve would freeze the defender.
        m = re.search(r"\$Preserve\s*=\s*@\((.*?)\)", self.apply, re.S)
        self.assertIsNotNone(m, "could not locate the $Preserve block")
        block = m.group(1)
        self.assertNotIn("'security'", block)
        self.assertNotIn('"security"', block)

    def test_stash_and_restore_are_a_pair(self):
        # Both halves or neither: a stash with no restore is worse than the bug.
        self.assertIn("# 3c)", self.apply, "missing the stash step (before delete)")
        self.assertIn("# 5b)", self.apply, "missing the restore step (after move-in)")
        self.assertIn("_security_logs_carryover", self.apply)

    def test_self_update_docstring_documents_the_carryover(self):
        s = _read(REPO_ROOT / "Tlamatini" / "agent" / "self_update.py")
        self.assertIn("_security_logs_carryover", s)


class DocumentationTests(unittest.TestCase):
    def test_security_readme_names_the_scripts(self):
        r = _read(SECURITY / "README.md")
        self.assertIn("tlamatini_defender.ps1", r)
        self.assertIn("tlamatini_whitelist_v2.ps1", r)

    def test_blue_hat_section_exists(self):
        for f in (REPO_ROOT / "README.md", REPO_ROOT / "BookOfTlamatini.md"):
            self.assertIn("Enable Tlamatini as a Blue-hat agent", _read(f))

    def test_docs_describe_the_evidence_carryover(self):
        # After G1+G4 the docs describe evidence PRESERVATION, not "logs not shipped".
        for f in (REPO_ROOT / "README.md", REPO_ROOT / "BookOfTlamatini.md", SECURITY / "README.md"):
            self.assertIn("_security_logs_carryover", _read(f),
                          f"{f.name} must describe the self-update evidence carryover")


if __name__ == "__main__":
    unittest.main()
