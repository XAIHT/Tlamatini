# Tlamatini Author Banner — Angela López Mendoza · @angelahack1
"""Release regeneration must preserve credential values and contact updates.

Run from a verified visible foreground console. Fixtures contain no real keys.
"""
import contextlib
import io
import json
import os
from pathlib import Path
import re
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


def _server(command="fixture-command", **env):
    spec = {"command": command, "args": []}
    if env:
        spec["env"] = dict(env)
    return spec


class PrivateExternalMcpsTests(unittest.TestCase):
    """The private release carries every External > MCPs server of the install."""

    def test_servers_only_the_install_has_are_added_and_dev_values_win(self):
        dev = {"mcpServers": {
            "memory": _server(MEMORY_FILE_PATH="dev-value"),
            "octocode": _server(GITHUB_TOKEN="<GITHUB_TOKEN goes here>"),
        }, "active": []}
        running = {"mcpServers": {
            "memory": _server(MEMORY_FILE_PATH="install-value"),
            "octocode": _server(GITHUB_TOKEN="fixture-not-a-secret"),
            "youtube": _server(API_VALUE="fixture-two"),
        }, "active": ["youtube", "memory", "ghost"]}
        merged, added, filled = private.merge_external_mcps(dev, running)
        self.assertEqual(sorted(merged["mcpServers"]), ["memory", "octocode", "youtube"])
        self.assertEqual(added, ["youtube"])
        self.assertEqual(merged["mcpServers"]["memory"]["env"]["MEMORY_FILE_PATH"], "dev-value",
                         "the tracked dev spec wins for a server both catalogs have")
        self.assertEqual(merged["mcpServers"]["octocode"]["env"]["GITHUB_TOKEN"], "fixture-not-a-secret",
                         "a placeholder in the dev catalog is filled from the install")
        self.assertEqual(filled, ["octocode.env.GITHUB_TOKEN"])
        self.assertEqual(merged["active"], ["youtube", "memory"],
                         "the install's own selection, without servers that do not exist")

    def test_inputs_are_never_modified(self):
        dev = {"mcpServers": {"a": _server(TOKEN_VALUE="")}, "active": []}
        running = {"mcpServers": {"a": _server(TOKEN_VALUE="fixture-value")}, "active": ["a"]}
        before = json.dumps([dev, running], sort_keys=True)
        private.merge_external_mcps(dev, running)
        self.assertEqual(json.dumps([dev, running], sort_keys=True), before)

    def test_active_selection_is_capped_like_the_manager(self):
        servers = {f"s{i}": _server() for i in range(8)}
        merged, _, _ = private.merge_external_mcps(
            {"mcpServers": {}, "active": []}, {"mcpServers": servers, "active": list(servers)})
        self.assertEqual(len(merged["active"]), private._MAX_ACTIVE_MCPS)
        manager = (ROOT / "Tlamatini" / "agent" / "external_mcp_manager.py").read_text(encoding="utf-8")
        cap = int(re.search(r"^MAX_ACTIVE\s*=\s*(\d+)", manager, re.M).group(1))
        self.assertEqual(private._MAX_ACTIVE_MCPS, cap, "keep the builder's cap equal to the manager's")

    def test_dev_active_is_used_when_the_install_has_none(self):
        merged, _, _ = private.merge_external_mcps(
            {"mcpServers": {"a": _server(), "b": _server()}, "active": ["b"]},
            {"mcpServers": {}, "active": []})
        self.assertEqual(merged["active"], ["b"])

    def _patched(self, root, *, running):
        return (patch.object(private, "EXTERNAL_MCPS_DEV", root / "dev.json"),
                patch.object(private, "EXTERNAL_MCPS_PRIVATE", root / "private.json"),
                patch.object(private, "_EXTERNAL_MCPS_RUNNING_CANDIDATES", running))

    def test_sync_writes_the_private_catalog_once_and_is_idempotent(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "dev.json").write_text(json.dumps(
                {"mcpServers": {"memory": _server()}, "active": []}), encoding="utf-8")
            (root / "install.json").write_text(json.dumps(
                {"mcpServers": {"memory": _server(), "youtube": _server(API_VALUE="fixture-two")},
                 "active": ["youtube"]}), encoding="utf-8")
            first_patch, second_patch, third_patch = self._patched(root, running=[root / "install.json"])
            with first_patch, second_patch, third_patch, contextlib.redirect_stdout(io.StringIO()) as out:
                private.sync_external_mcps_private()
                first = (root / "private.json").read_bytes()
                private.sync_external_mcps_private()
            document = json.loads((root / "private.json").read_text(encoding="utf-8"))
            self.assertEqual(sorted(document["mcpServers"]), ["memory", "youtube"])
            self.assertEqual(document["active"], ["youtube"])
            self.assertEqual((root / "private.json").read_bytes(), first)
            self.assertFalse((root / "private.json.tmp").exists())
            self.assertNotIn("fixture-two", out.getvalue(), "values must never be printed")

    def test_previous_snapshot_stands_in_when_no_install_is_found(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "dev.json").write_text(json.dumps(
                {"mcpServers": {"memory": _server()}, "active": []}), encoding="utf-8")
            (root / "private.json").write_text(json.dumps(
                {"mcpServers": {"memory": _server(), "youtube": _server()}, "active": ["youtube"]}),
                encoding="utf-8")
            first_patch, second_patch, third_patch = self._patched(root, running=[root / "missing.json"])
            with first_patch, second_patch, third_patch, contextlib.redirect_stdout(io.StringIO()):
                private.sync_external_mcps_private()
            document = json.loads((root / "private.json").read_text(encoding="utf-8"))
            self.assertEqual(sorted(document["mcpServers"]), ["memory", "youtube"],
                             "a build on a machine without the install must not drop servers")
            self.assertEqual(document["active"], ["youtube"])


class PrivateVaultCarriageTests(unittest.TestCase):
    """data.keys travels in the private release only, and builds must keep it that way."""

    def _env(self):
        with patch.dict(os.environ, {"TLAMATINI_BUNDLE_DATA_KEYS": "ambient"}, clear=False):
            return private._utf8_env()

    def test_environment_carries_the_vault_and_the_private_catalog(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            vault, catalog, dev = root / "data.keys", root / "private.json", root / "dev.json"
            vault.write_text("FIXTURE_KEY=fixture-value\n", encoding="utf-8")
            catalog.write_text("{}", encoding="utf-8")
            dev.write_text("{}", encoding="utf-8")
            with patch.object(private, "_BUNDLE_DATA_KEYS", vault), \
                    patch.object(private, "EXTERNAL_MCPS_PRIVATE", catalog), \
                    patch.object(private, "EXTERNAL_MCPS_DEV", dev):
                env = self._env()
            self.assertEqual(env["TLAMATINI_BUNDLE_DATA_KEYS"], str(vault))
            self.assertEqual(env["TLAMATINI_BUNDLE_EXTERNAL_MCPS"], str(catalog),
                             "the private catalog wins over the tracked dev one")

    def test_environment_falls_back_to_the_dev_catalog_and_drops_a_stale_vault_variable(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            dev = root / "dev.json"
            dev.write_text("{}", encoding="utf-8")
            with patch.object(private, "_BUNDLE_DATA_KEYS", None), \
                    patch.object(private, "EXTERNAL_MCPS_PRIVATE", root / "absent.json"), \
                    patch.object(private, "EXTERNAL_MCPS_DEV", dev):
                env = self._env()
            self.assertEqual(env["TLAMATINI_BUNDLE_EXTERNAL_MCPS"], str(dev))
            self.assertNotIn("TLAMATINI_BUNDLE_DATA_KEYS", env,
                             "an ambient value must not leak into a build that chose no vault")

    def test_choose_data_keys_reports_counts_only(self):
        with tempfile.TemporaryDirectory() as temporary:
            vault = Path(temporary) / "data.keys"
            vault.write_text("# comment\nFIXTURE_ONE=fixture-secret-value\nFIXTURE_TWO=\n",
                             encoding="utf-8-sig")
            with patch.object(private, "_BUNDLE_DATA_KEYS", None), \
                    contextlib.redirect_stdout(io.StringIO()) as out:
                private.choose_data_keys(str(vault))
                chosen = private._BUNDLE_DATA_KEYS
            self.assertEqual(chosen, vault)
            self.assertIn("2 entr", out.getvalue())
            self.assertNotIn("fixture-secret-value", out.getvalue())
            self.assertNotIn("FIXTURE_ONE", out.getvalue())

    def test_a_missing_vault_is_reported_not_shipped(self):
        with tempfile.TemporaryDirectory() as temporary:
            with patch.object(private, "_BUNDLE_DATA_KEYS", Path("stale")), \
                    contextlib.redirect_stdout(io.StringIO()):
                private.choose_data_keys(str(Path(temporary) / "nope.keys"))
                self.assertIsNone(private._BUNDLE_DATA_KEYS)

    def test_build_ships_the_vault_only_on_the_keyed_path(self):
        build = (ROOT / "build.py").read_text(encoding="utf-8")
        self.assertIn('os.environ.get("TLAMATINI_BUNDLE_DATA_KEYS")', build)
        self.assertIn('dist_manage / "data.keys"', build)
        self.assertIn("ABORT: TLAMATINI_BUNDLE_DATA_KEYS is set but the External-MCP catalog is the", build,
                      "the vault must never ride along with the PUBLIC catalog")
        self.assertLess(build.index('_mcps_flavor = "PUBLIC"'), build.index("TLAMATINI_BUNDLE_DATA_KEYS"),
                        "the catalog flavour has to be decided before the vault is considered")

    def test_public_builder_clears_the_vault_switch_and_private_builder_sets_it(self):
        public = (ROOT / "build_complete_public_release.py").read_text(encoding="utf-8")
        owner = (ROOT / "build_complete_private_release.py").read_text(encoding="utf-8")
        self.assertIn('env.pop("TLAMATINI_BUNDLE_DATA_KEYS", None)', public)
        self.assertIn('env["TLAMATINI_BUNDLE_DATA_KEYS"]', owner)
        self.assertNotIn('env["TLAMATINI_BUNDLE_DATA_KEYS"]', public)

    def test_the_private_catalog_is_gitignored_and_never_snapshotted(self):
        ignore = (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
        self.assertIn("external_mcps.private.json", [line.strip() for line in ignore])
        snapshot = (ROOT / "copy_source_assets.py").read_text(encoding="utf-8")
        self.assertIn('"external_mcps.private.json"', snapshot)
        public = (ROOT / "build_complete_public_release.py").read_text(encoding="utf-8")
        self.assertIn('REPO_ROOT / "external_mcps.private.json"', public,
                      "a tree holding the private catalog must count as keyed for the public build")


if __name__ == "__main__":
    unittest.main(verbosity=2)
