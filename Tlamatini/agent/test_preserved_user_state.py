# Tlamatini Author Banner - do not remove (releases scrub the name automatically)
"""USER STATE MUST SURVIVE A REINSTALL  (Angela, 2026-08-12)

Angela: *"check why everytime I reinstall all external MCPs go fucked"*.

The answer was not in the MCP subsystem at all. `install.py` extracted EVERY
member of `pkg.zip` over the target directory, unconditionally - so installing
over an existing Tlamatini overwrote:

  * `config.json`         every provider key and every setting she chose
  * `external_mcps.json`  the whole External-MCP catalog AND its active set
  * `contacts.json`       the people the messaging agents resolve by name
  * `DB`                  chat history and the enable/disable toggles

Meanwhile `apply_update.ps1` had a `$Preserve` array and kept all of them.
Two code paths, two different answers to the same question - and the gap only
showed on the path nobody tests, because reinstalling is what you do when
something is ALREADY wrong.

A SECOND defect sat next to it: `build.py` copied the DEV TREE's
`external_mcps.json` into the release. That file holds real provider secrets
in its `env` blocks (a GitHub PAT, a Snyk API key), so every release built
from a working tree shipped those keys inside `pkg.zip` - the exact leak
`contacts.json` was already excluded for. Its content was wrong for a user
anyway: the build machine's own servers with `"active": []`, which is why a
reinstall left every MCP switched off.

These tests pin both fixes and, above all, pin that the ONE list stays one.
"""
from __future__ import annotations

import json
import os
import re

from django.test import SimpleTestCase

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.dirname(os.path.dirname(_HERE))
_SHARED = os.path.join(_REPO_ROOT, "preserved_user_state.json")

# The items whose loss the user would actually feel. A future edit may ADD to
# the preserved set; removing one of these is a data-loss regression.
MUST_PRESERVE = {
    "config.json", "external_mcps.json", "contacts.json", "DB",
    "Temp", "Templates", "Uninstaller.exe",
}


def _read(path: str) -> str:
    with open(path, encoding="utf-8-sig") as fh:
        return fh.read()


def _shared_list() -> set:
    doc = json.loads(_read(_SHARED))
    return {str(n).strip().lower() for n in doc["preserve"]}


class SharedPreserveListTests(SimpleTestCase):
    """One list, read by everything that can delete the user's data."""

    def test_the_shared_list_exists_and_covers_what_matters(self):
        self.assertTrue(os.path.isfile(_SHARED),
                        "preserved_user_state.json is THE list - without it "
                        "the installer and the updater go back to guessing.")
        names = _shared_list()
        for needed in MUST_PRESERVE:
            self.assertIn(
                needed.lower(), names,
                "%s dropped out of the preserved set. A reinstall would "
                "delete it." % needed)

    def test_updater_preserve_array_matches_the_shared_list(self):
        """apply_update.ps1 keeps a PowerShell copy; it must not drift."""
        ps1 = _read(os.path.join(_REPO_ROOT, "apply_update.ps1"))
        block = ps1.split("$Preserve = @(", 1)[1].split(")", 1)[0]
        in_ps1 = {m.group(1).strip().lower()
                  for m in re.finditer(r"'([^']+)'", block)}
        missing = _shared_list() - in_ps1
        self.assertEqual(
            missing, set(),
            "apply_update.ps1 $Preserve is missing %s. The self-update would "
            "delete what a reinstall now keeps - the two paths must agree."
            % sorted(missing))

    def test_installer_reads_the_shared_list_and_fails_safe(self):
        src = _read(os.path.join(_REPO_ROOT, "install.py"))
        self.assertIn("preserved_user_state.json", src,
                      "install.py no longer reads the shared list.")
        self.assertIn("_PRESERVE_FALLBACK", src,
                      "install.py must keep a built-in fallback: erring "
                      "towards KEEPING the user's data is the only "
                      "acceptable direction when the list cannot be read.")
        fallback = src.split("_PRESERVE_FALLBACK = (", 1)[1].split(")", 1)[0]
        in_fallback = {m.group(1).strip().lower()
                       for m in re.finditer(r'"([^"]+)"', fallback)}
        missing = _shared_list() - in_fallback
        self.assertEqual(
            missing, set(),
            "install.py's fallback is missing %s" % sorted(missing))

    def test_installer_skips_preserved_members_only_when_they_exist(self):
        """A FRESH install must still receive its seed files."""
        src = _read(os.path.join(_REPO_ROOT, "install.py"))
        fn = src.split("def _is_preserved_member", 1)[1].split("\n    def ", 1)[0]
        self.assertIn("os.path.exists", fn,
                      "a preserved name must be skipped ONLY when it is "
                      "already on disk, or a first install ships without "
                      "config.json at all.")
        self.assertIn("split(\"/\")[0]", fn,
                      "matching is on the TOP-LEVEL name so `DB/db.sqlite3` "
                      "is protected by the entry `DB`.")

    def test_extraction_actually_honours_the_skip(self):
        src = _read(os.path.join(_REPO_ROOT, "install.py"))
        block = src.split("with zipfile.ZipFile(self.zip_path", 1)[1][:1200]
        self.assertIn("_is_preserved_member", block,
                      "the extraction loop extracts every member again - "
                      "this is the exact line that wiped the MCP catalog.")


class ReleaseNeverShipsTheDevCatalogTests(SimpleTestCase):
    """A PUBLIC release must never carry the maintainer's MCP servers or keys."""

    def setUp(self):
        self.build = _read(os.path.join(_REPO_ROOT, "build.py"))
        self.public_builder = _read(
            os.path.join(_REPO_ROOT, "build_complete_public_release.py")
        )
        self.private_builder = _read(
            os.path.join(_REPO_ROOT, "build_complete_private_release.py")
        )

    def test_dev_catalog_is_not_copied_into_the_package(self):
        copied = re.search(
            r'Path\("Tlamatini"\)\s*/\s*"agent"\s*/\s*"external_mcps\.json"\s*:',
            self.build)
        self.assertIsNone(
            copied,
            "build.py copies the DEV TREE's external_mcps.json into the "
            "release again. That file holds real provider secrets in its "
            "`env` blocks - shipping it leaks them into every pkg.zip, and "
            "hands the user the build machine's servers with active=[].")

    def test_code_seeded_defaults_have_a_safe_empty_fallback(self):
        self.assertIn("shipped_catalog_document()", self.build,
                      "the release must derive its inactive public defaults "
                      "from external_mcp_defaults.py.")
        self.assertIn("external_mcps_doc", self.build,
                      "the release must still SHIP a valid catalog, so a "
                      "fresh install has a file to write into.")
        # ⚠️ Read a fixed WINDOW, never `.split("}", 1)`. The original cut the
        # text at the first `}` — which is the closing brace of the very
        # `{}` being looked for, so `"mcpServers": {}` could never survive
        # into the slice. The assertion was unsatisfiable by construction and
        # failed against correct code in BOTH editions.
        start = self.build.index("external_mcps_doc = {")
        block = self.build[start:start + 600]
        self.assertIn('"mcpServers": {}', block,
                      "the shipped catalog must start EMPTY - a release that "
                      "carries servers is carrying the build machine's.")
        self.assertIn('"active": []', block,
                      "nothing may be pre-activated in a fresh install.")

    def test_public_builder_clears_private_catalog_opt_in(self):
        """An inherited shell variable must never contaminate a public build."""
        self.assertIn(
            'env.pop("TLAMATINI_BUNDLE_EXTERNAL_MCPS", None)',
            self.public_builder,
        )

    def test_private_catalog_opt_in_is_owned_only_by_private_builder(self):
        """The keyed catalog is allowed only on the explicit private path."""
        self.assertIn(
            'env["TLAMATINI_BUNDLE_EXTERNAL_MCPS"]',
            self.private_builder,
        )
        self.assertIn(
            'os.environ.get("TLAMATINI_BUNDLE_EXTERNAL_MCPS")',
            self.build,
        )


class DevCatalogIsNotTrackedTests(SimpleTestCase):
    """The working copy holds real keys - git must never see it."""

    def test_catalog_is_gitignored(self):
        ignored = _read(os.path.join(_REPO_ROOT, ".gitignore"))
        self.assertIn("external_mcps.json", ignored,
                      "the live catalog holds real API keys in its env "
                      "blocks and must stay untracked.")
