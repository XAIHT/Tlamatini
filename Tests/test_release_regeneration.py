# Tlamatini Author Banner — Angela López Mendoza · @angelahack1
"""Release regeneration must preserve credential values and contact updates.

Run from a verified visible foreground console. Fixtures contain no real keys.
"""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import build_complete_private_release as private  # noqa: E402
import regen_secrets as regen  # noqa: E402


class RegenerationRoundTripTests(unittest.TestCase):
    def test_keys_file_accepts_utf8_bom(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "fixture.keys"
            path.write_text("FIXTURE_KEY=example-value\n", encoding="utf-8-sig")
            self.assertEqual(regen.parse_keys_file(path), {"FIXTURE_KEY": "example-value"})

    def test_yaml_values_retain_their_exact_string_content(self):
        values = ["'example'", '"example"', "00123", "12345", "1.25", "2026-10-18",
                  "example\\value", "example\tvalue", "line one\nline two",
                  "example # value", "Unicode Ñ 🔧", "yes", "null"]
        for value in values:
            with self.subTest(value=value):
                text, _ = regen._patch_yaml_text(
                    "password: old\n", [(["password"], "FIXTURE_KEY")],
                    "keyed", {"FIXTURE_KEY": value}, "fixture.yaml")
                self.assertEqual(yaml.safe_load(text)["password"], value)

    def test_force_quoted_values_escape_line_and_unicode_separators(self):
        for value in ("line one\nline two", "one\r\ntwo", "tab\tvalue",
                      "one\u0085two", "one\u2028two", "Unicode 🔧"):
            with self.subTest(value=value):
                self.assertEqual(yaml.safe_load("value: " + regen._force_quote(value))["value"], value)

    def test_real_inline_comments_survive_but_quoted_secret_fragments_do_not(self):
        for old in ('"example # fragment"', "'example # fragment'", "'example '' # fragment'"):
            with self.subTest(old=old):
                text, _ = regen._patch_yaml_text(
                    "password: " + old + " # keep this comment\n",
                    [(["password"], "FIXTURE_KEY")], "push-able", {}, "fixture.yaml")
                self.assertNotIn("fragment", text)
                self.assertIn("# keep this comment", text)
                self.assertEqual(yaml.safe_load(text)["password"], regen.placeholder("FIXTURE_KEY"))

    def test_dry_run_leaves_yaml_bytes_unchanged(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            path = root / "fixture.yaml"
            original = b'# comment\r\npassword: "example"\r\n'
            path.write_bytes(original)
            with patch.object(regen, "REPO_ROOT", root):
                regen.patch_yaml(path, [(["password"], "FIXTURE_KEY")], "push-able", {}, True)
            self.assertEqual(path.read_bytes(), original)


class PrivateContactsRegenerationTests(unittest.TestCase):
    def test_updates_to_existing_contacts_are_saved_without_a_new_name(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            saved, source = root / "contacts.private.json", root / "contacts.json"
            saved.write_text(json.dumps({"_README": "keep", "contacts": [
                {"name": "Fixture Person", "aliases": ["first"]}]}), encoding="utf-8")
            source.write_text(json.dumps({"contacts": [{"name": "Fixture Person",
                "aliases": ["second"], "email": "fixture@example.invalid"}]}), encoding="utf-8")
            with patch.object(private, "CONTACTS_PRIVATE", saved), \
                    patch.object(private, "CONTACTS_DEV_TREE", source), \
                    patch.object(private, "_CONTACTS_RUNNING_CANDIDATES", []):
                private.sync_contacts_private()
                first = saved.read_bytes()
                private.sync_contacts_private()
            document = json.loads(saved.read_text(encoding="utf-8"))
            self.assertEqual(document["_README"], "keep")
            self.assertEqual(document["contacts"][0]["email"], "fixture@example.invalid")
            self.assertEqual(set(document["contacts"][0]["aliases"]), {"first", "second"})
            self.assertEqual(saved.read_bytes(), first, "Repeated synchronization must be idempotent")


if __name__ == "__main__":
    unittest.main(verbosity=2)
