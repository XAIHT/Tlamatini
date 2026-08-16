# ═══════════════════════════════════════════════════════════════════
#   ✦  T L A M A T I N I  ✦   —   "one who knows"
#
#   Created by  Angela López Mendoza   ·   @angelahack1
#   Developer · Architect · Creator of Tlamatini
#
#   Every line of this file was written by Angela López Mendoza.
# ═══════════════════════════════════════════════════════════════════
#   Tlamatini Author Banner — do not remove (releases scrub the name automatically)
"""Behavioural guards for the Runtime Provisioner and the shipped default MCPs.

These are BEHAVIOURAL tests, not narrative ones: each pins a contract that, if
broken, produces a specific real-world failure Angela would otherwise hit on a
fresh machine — a shadowed system Node, an npx that dies with WinError 193, a
Remove button that undoes itself, a default that never reaches an existing
install, or a download that blocks Django startup.

Run:  python Tlamatini/manage.py test agent.test_runtime_provisioner
"""

import json
import os
import unittest
from pathlib import Path

from agent import external_mcp_defaults as defaults
from agent import runtime_provisioner as rp

_REPO_ROOT = Path(__file__).resolve().parents[2]
_AGENT_DIR = Path(__file__).resolve().parent
_IS_WINDOWS = os.name == "nt"


class _PrivateRuntimeFixture(unittest.TestCase):
    """Base class that points the provisioner at a throwaway runtime root."""

    def setUp(self) -> None:
        import tempfile
        self._tmp = tempfile.mkdtemp(prefix="tlm-runtime-test-")
        self._saved_env = dict(os.environ)
        os.environ["TLAMATINI_RUNTIMES"] = self._tmp
        rp._resolve_cache.clear()

    def tearDown(self) -> None:
        import shutil
        os.environ.clear()
        os.environ.update(self._saved_env)
        rp._resolve_cache.clear()
        shutil.rmtree(self._tmp, ignore_errors=True)

    def _fake_node_tree(self, version: str = "22.20.0") -> str:
        """Create a minimal but STRUCTURALLY REAL extracted Node distribution."""
        root = os.path.join(self._tmp, "node")
        if _IS_WINDOWS:
            os.makedirs(root, exist_ok=True)
            bin_dir = root
            npm_bin = os.path.join(root, "node_modules", "npm", "bin")
            node_exe = os.path.join(root, "node.exe")
        else:
            bin_dir = os.path.join(root, "bin")
            os.makedirs(bin_dir, exist_ok=True)
            npm_bin = os.path.join(root, "lib", "node_modules", "npm", "bin")
            node_exe = os.path.join(bin_dir, "node")
        os.makedirs(npm_bin, exist_ok=True)
        Path(node_exe).write_text("", encoding="utf-8")
        for which in ("npm", "npx"):
            Path(os.path.join(npm_bin, f"{which}-cli.js")).write_text("", encoding="utf-8")
            shim = os.path.join(bin_dir, f"{which}.cmd" if _IS_WINDOWS else which)
            Path(shim).write_text("", encoding="utf-8")
        return root


# ---------------------------------------------------------------------------
# Resolution
# ---------------------------------------------------------------------------

class ResolutionTests(_PrivateRuntimeFixture):

    def test_unknown_tool_resolves_empty_and_never_raises(self):
        self.assertEqual(rp.resolve("definitely-not-a-tool"), "")
        self.assertEqual(rp.resolve(""), "")
        self.assertEqual(rp.resolve(None), "")

    def test_private_node_is_discovered(self):
        self._fake_node_tree()
        rp._resolve_cache.clear()
        self.assertTrue(rp._node_home(), "the extracted Node tree must be discovered")
        self.assertTrue(os.path.isfile(rp._node_exe()))
        self.assertTrue(rp._npm_cli_js("npx").endswith("npx-cli.js"))

    def test_a_system_install_is_never_shadowed_when_we_have_nothing(self):
        """We only FILL a hole. With no private runtime the answer must come
        from the user's own PATH, byte-identical to shutil.which."""
        import shutil as _sh
        for tool in ("node", "npx", "uv"):
            system = _sh.which(tool)
            if system:
                self.assertEqual(os.path.normcase(rp.resolve(tool)),
                                 os.path.normcase(system))

    def test_status_is_total_and_lists_missing(self):
        report = rp.status()
        self.assertIn("tools", report)
        self.assertIn("missing", report)
        self.assertEqual(set(report["tools"]), set(rp.MANAGED_TOOLS))
        self.assertIsInstance(report["ok"], bool)


# ---------------------------------------------------------------------------
# Spawn rewriting — the Windows .cmd-shim killer
# ---------------------------------------------------------------------------

class SpawnRewriteTests(_PrivateRuntimeFixture):

    def test_npx_is_rewritten_to_node_plus_cli_js(self):
        """THE contract that kills WinError 193: never spawn the .cmd shim when
        we own the Node tree — spawn node.exe with npx's real entry point."""
        self._fake_node_tree()
        rp._resolve_cache.clear()
        argv, note = rp.resolve_spawn("npx", ["-y", "@modelcontextprotocol/server-memory"])
        self.assertEqual(len(argv), 4)
        self.assertTrue(argv[0].endswith("node.exe") or argv[0].endswith(os.sep + "node"))
        self.assertTrue(argv[1].endswith("npx-cli.js"))
        self.assertEqual(argv[2:], ["-y", "@modelcontextprotocol/server-memory"])
        self.assertNotIn("cmd.exe", " ".join(argv).lower())
        self.assertIn("private Node", note)

    def test_cmd_slash_c_wrapper_is_seen_through(self):
        """Catalog entries copied from other clients wrap the manager in
        `cmd /c`. Unwrapping is what lets the rewrite above reach the real npx
        instead of spawning a shell that then cannot find it."""
        self._fake_node_tree()
        rp._resolve_cache.clear()
        argv, note = rp.resolve_spawn("cmd", ["/c", "npx", "-y", "pkg"])
        self.assertTrue(argv[1].endswith("npx-cli.js"))
        self.assertEqual(argv[2:], ["-y", "pkg"])
        self.assertIn("unwrapped", note)

    def test_unmanaged_command_passes_through_untouched(self):
        argv, note = rp.resolve_spawn("docker", ["run", "-i", "--rm", "mcp/redis"])
        self.assertEqual(argv, ["docker", "run", "-i", "--rm", "mcp/redis"])
        self.assertEqual(note, "")

    def test_missing_tool_returns_original_so_the_real_error_surfaces(self):
        """A silent swap would hide the truth. When nothing resolves we hand
        back the original command so the caller reports 'npx not found'."""
        argv, note = rp.resolve_spawn("pnpm", ["dlx", "thing"])
        self.assertEqual(argv[-2:], ["dlx", "thing"])
        self.assertIsInstance(note, str)

    def test_resolve_spawn_never_raises_on_garbage(self):
        for command, args in ((None, None), ("", []), (123, [None]), ("npx", "notalist")):
            argv, _note = rp.resolve_spawn(command, args if isinstance(args, list) else None)
            self.assertIsInstance(argv, list)

    def test_managed_tool_for_matrix(self):
        self.assertEqual(rp.managed_tool_for("npx", ["-y", "pkg"]), "npx")
        self.assertEqual(rp.managed_tool_for("uvx", ["pkg"]), "uvx")
        self.assertEqual(rp.managed_tool_for("docker", ["run"]), "")
        self.assertEqual(rp.managed_tool_for("", []), "")
        if _IS_WINDOWS:
            self.assertEqual(rp.managed_tool_for("cmd", ["/c", "npx", "-y", "p"]), "npx")


# ---------------------------------------------------------------------------
# Environment injection
# ---------------------------------------------------------------------------

class EnvironmentTests(_PrivateRuntimeFixture):

    def test_private_bin_is_prepended_and_existing_path_survives(self):
        self._fake_node_tree()
        rp._resolve_cache.clear()
        env = rp.augment_env({"PATH": "/original/path"})
        self.assertTrue(env["PATH"].endswith("/original/path"),
                        "the caller's PATH must never be destroyed")
        self.assertIn(os.path.normcase(self._tmp), os.path.normcase(env["PATH"]))

    def test_quiet_npm_flags_are_set(self):
        """A first npx run must not stall on an update notice or a corepack
        prompt — an interactive child would hang the MCP handshake forever."""
        env = rp.augment_env({})
        for key in ("NO_UPDATE_NOTIFIER", "NPM_CONFIG_UPDATE_NOTIFIER",
                    "NPM_CONFIG_FUND", "NPM_CONFIG_AUDIT",
                    "COREPACK_ENABLE_DOWNLOAD_PROMPT"):
            self.assertIn(key, env)

    def test_augment_env_never_raises_and_returns_a_dict(self):
        self.assertIsInstance(rp.augment_env(None), dict)
        self.assertIsInstance(rp.augment_env({}), dict)


# ---------------------------------------------------------------------------
# Fail-open + no-startup-block contracts
# ---------------------------------------------------------------------------

class FailOpenTests(_PrivateRuntimeFixture):

    def test_ensure_unknown_tool_reports_instead_of_raising(self):
        outcome = rp.ensure("not-a-real-tool")
        self.assertFalse(outcome["ok"])
        self.assertIn("unknown tool", outcome["reason"])

    def test_autoprovision_can_be_disabled_by_env(self):
        os.environ["TLAMATINI_RUNTIME_AUTOPROVISION"] = "0"
        self.assertFalse(rp.autoprovision_enabled())
        self.assertFalse(rp.provision_async(), "must not start a thread when disabled")

    def test_provision_async_is_a_noop_when_everything_resolves(self):
        """Zero network, zero thread on the overwhelmingly common launch."""
        present = [t for t in ("node", "npx") if rp.resolve(t, use_cache=False)]
        if not present:
            self.skipTest("no system Node on this machine to prove the fast path")
        self.assertFalse(rp.provision_async(present))

    def test_ensure_respects_the_disabled_switch(self):
        os.environ["TLAMATINI_RUNTIME_AUTOPROVISION"] = "false"
        rp._resolve_cache.clear()
        if rp.resolve("pnpm", use_cache=False):
            self.skipTest("pnpm already present; cannot observe the skip path")
        outcome = rp.ensure("pnpm")
        self.assertFalse(outcome["ok"])
        self.assertEqual(outcome["action"], "skipped")


# ---------------------------------------------------------------------------
# The two shipped default servers
# ---------------------------------------------------------------------------

class DefaultServerTests(unittest.TestCase):

    def test_exactly_the_two_servers_angela_asked_for(self):
        self.assertEqual(defaults.default_keys(), ["memory", "sequential-thinking"])

    def test_both_use_npx_with_the_official_packages(self):
        servers = defaults.default_servers()
        self.assertEqual(servers["memory"]["command"], "npx")
        self.assertIn("@modelcontextprotocol/server-memory", servers["memory"]["args"])
        self.assertEqual(servers["sequential-thinking"]["command"], "npx")
        self.assertIn("@modelcontextprotocol/server-sequential-thinking",
                      servers["sequential-thinking"]["args"])
        for spec in servers.values():
            self.assertEqual(spec["transport"], "stdio")

    def test_seeding_adds_both_and_activates_neither(self):
        """ACTIVATING spawns a child and burns one of the five slots. That is
        the user's decision, never ours."""
        catalog, added = defaults.seed_defaults({"mcpServers": {}, "active": []})
        self.assertEqual(sorted(added), ["memory", "sequential-thinking"])
        self.assertEqual(catalog["active"], [], "defaults MUST ship INACTIVE")

    def test_seeding_is_idempotent(self):
        catalog, _ = defaults.seed_defaults({"mcpServers": {}, "active": []})
        _catalog, added_again = defaults.seed_defaults(catalog)
        self.assertEqual(added_again, [])

    def test_a_user_edit_is_never_overwritten(self):
        mine = {"command": "node", "args": ["my-own-memory-server.js"], "env": {}}
        catalog = {"mcpServers": {"memory": dict(mine)}, "active": []}
        catalog, added = defaults.seed_defaults(catalog)
        self.assertNotIn("memory", added)
        self.assertEqual(catalog["mcpServers"]["memory"], mine)

    def test_a_removed_default_stays_removed(self):
        """A Remove button that silently undoes itself is a bug."""
        catalog, _ = defaults.seed_defaults({"mcpServers": {}, "active": []})
        catalog = defaults.record_removal(catalog, ["memory"])
        catalog["mcpServers"].pop("memory")
        catalog, added = defaults.seed_defaults(catalog)
        self.assertEqual(added, [], "a tombstoned default must NOT be resurrected")
        self.assertNotIn("memory", catalog["mcpServers"])

    def test_reimporting_clears_the_tombstone(self):
        """Full round trip: seed -> remove -> stays removed -> re-import -> back."""
        catalog, _ = defaults.seed_defaults({"mcpServers": {}, "active": []})
        catalog = defaults.record_removal(catalog, ["memory"])
        catalog["mcpServers"].pop("memory")
        catalog, added = defaults.seed_defaults(catalog)
        self.assertEqual(added, [], "still tombstoned, must not come back on its own")
        catalog = defaults.clear_tombstones(catalog, ["memory"])
        catalog, added = defaults.seed_defaults(catalog)
        self.assertEqual(added, ["memory"], "an explicit re-import must restore it")

    def test_seeding_survives_a_malformed_catalog(self):
        for junk in ({}, {"mcpServers": "not-a-dict"}, {"active": "nope"}):
            catalog, _added = defaults.seed_defaults(dict(junk))
            self.assertIsInstance(catalog.get("mcpServers"), dict)
            self.assertIsInstance(catalog.get("active"), list)

    def test_memory_store_lives_outside_the_install_dir(self):
        """A self-update replaces the install directory wholesale, so Angela's
        memories must not live there."""
        path = defaults.memory_store_path()
        self.assertTrue(path.endswith("memory.json"))
        self.assertIn("Tlamatini", path)

    def test_shipped_document_is_clean_and_inactive(self):
        doc = defaults.shipped_catalog_document()
        self.assertEqual(doc["active"], [])
        self.assertEqual(sorted(doc["mcpServers"]), ["memory", "sequential-thinking"])
        blob = json.dumps(doc).lower()
        for leak in ("github_pat", "snyk_uat", "api_key\": \"s", "ghp_"):
            self.assertNotIn(leak, blob, "a shipped catalog must carry NO secrets")


# ---------------------------------------------------------------------------
# Wiring contracts — the surfaces that must stay aligned
# ---------------------------------------------------------------------------

class WiringContractTests(unittest.TestCase):

    def _read(self, path: Path) -> str:
        return path.read_text(encoding="utf-8", errors="replace")

    def test_manager_spawns_through_the_provisioner(self):
        source = self._read(_AGENT_DIR / "external_mcp_manager.py")
        self.assertIn("runtime_provisioner.resolve_spawn", source)
        self.assertIn("runtime_provisioner.augment_env", source)
        self.assertIn("_ensure_runtime_for_spec", source)

    def test_manager_seeds_defaults_on_the_read_path(self):
        source = self._read(_AGENT_DIR / "external_mcp_manager.py")
        self.assertIn("_seed_defaults_once", source)
        self.assertIn("return _seed_defaults_once(data)", source,
                      "load_catalog MUST seed, or existing installs never get the defaults")

    def test_manager_tombstones_removed_defaults(self):
        source = self._read(_AGENT_DIR / "external_mcp_manager.py")
        self.assertIn("record_removal", source)
        self.assertIn("clear_tombstones", source)

    def test_both_new_supervisor_tools_are_registered(self):
        source = self._read(_AGENT_DIR / "external_mcp_manager.py")
        for name in ("external_mcp_runtime_status", "external_mcp_runtime_install"):
            self.assertGreaterEqual(
                source.count(name), 2,
                f"{name} must be in _SUPERVISOR_TOOL_NAMES AND built as a tool",
            )

    def test_apps_prewarms_and_seeds_at_boot(self):
        source = self._read(_AGENT_DIR / "apps.py")
        self.assertIn("runtime_provisioner.provision_async", source)
        self.assertIn("external_mcp_manager.load_catalog", source)

    def test_build_ships_the_defaults_from_the_same_module(self):
        source = self._read(_REPO_ROOT / "build.py")
        self.assertIn("external_mcp_defaults", source)
        self.assertIn("shipped_catalog_document", source)

    def test_build_NAMES_the_provisioner_so_it_cannot_be_dropped(self):
        """Angela's review, 2026-08-16: `runtime_provisioner.py` had NO mention
        in build.py at all, while its sibling `external_mcp_defaults.py` was
        explicitly named (the test above).

        It did ship - the module graph followed
        `external_mcp_manager.py`'s `from . import runtime_provisioner` - but
        that import is inside a `try/except ImportError` that sets the module to
        None. So carriage rested entirely on graph analysis, and the failure
        mode was SILENT: Tlamatini would boot perfectly and simply never
        provision node/npx/uv/uvx again, leaving every `npx -y <pkg>` MCP server
        dead with [WinError 2] on exactly the fresh machine the provisioner was
        written to rescue. Name it explicitly.
        """
        source = self._read(_REPO_ROOT / "build.py")
        self.assertIn("--hidden-import=agent.runtime_provisioner", source,
                      "build.py must NAME agent.runtime_provisioner, not rely "
                      "on PyInstaller following a fail-open import")

    def test_build_proves_the_fail_open_modules_landed_in_the_bundle(self):
        """A --hidden-import is an instruction, not evidence.

        `verify_frozen_agent_modules()` opens the archive the build just
        produced and asserts each module is really in it, aborting otherwise.
        Verified against the shipped install: its PYZ holds 15,075 modules and
        every required agent module is present.
        """
        source = self._read(_REPO_ROOT / "build.py")
        self.assertIn("_FROZEN_REQUIRED_AGENT_MODULES", source)
        self.assertIn("def verify_frozen_agent_modules(", source)
        self.assertIn("verify_frozen_agent_modules(Path(\"dist\") / \"manage\")",
                      source,
                      "the proof must actually RUN on the successful-build path")
        # PyInstaller 6 onedir keeps the PYZ INSIDE the exe's CArchive; a reader
        # that only globs for a loose PYZ-*.pyz can never prove anything.
        self.assertIn("CArchiveReader", source,
                      "the verifier must read the PYZ embedded in the exe")

    def test_self_update_preserves_the_user_catalog(self):
        source = self._read(_REPO_ROOT / "apply_update.ps1")
        self.assertIn("external_mcps.json", source,
                      "the catalog is USER STATE and must survive an update")

    def test_provisioner_imports_nothing_from_agent_at_module_level(self):
        """It must load standalone (build.py and a pool agent both do this) and
        can never create an import cycle."""
        source = self._read(_AGENT_DIR / "runtime_provisioner.py")
        head = source.split("def _log(")[0]
        self.assertNotIn("from agent", head)
        self.assertNotIn("import agent", head)

    def test_defaults_module_is_stdlib_only(self):
        source = self._read(_AGENT_DIR / "external_mcp_defaults.py")
        self.assertNotIn("from agent", source)
        self.assertNotIn("from .", source)


class TrackedCatalogTests(unittest.TestCase):
    """The catalog is TRACKED in git (2026-08-15) — these guard the safety net."""

    def _regen(self):
        import importlib.util
        path = _REPO_ROOT / "regen_secrets.py"
        spec = importlib.util.spec_from_file_location("_tlm_regen", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    def _read(self, path: Path) -> str:
        return path.read_text(encoding="utf-8", errors="replace")

    def test_catalog_is_no_longer_gitignored(self):
        text = self._read(_REPO_ROOT / ".gitignore")
        for line in text.splitlines():
            self.assertNotEqual(
                line.strip(), "Tlamatini/agent/external_mcps.json",
                "the catalog must be TRACKED so the repo shows every MCP server",
            )

    def test_a_location_is_never_treated_as_a_secret(self):
        """THE regression: 'MEMORY_FILE_PATH' contains 'PAT', which once made a
        harmless file path get scrubbed to a placeholder and vaulted — and
        `keyed` would then stamp the build machine's path onto another install."""
        regen = self._regen()
        for field in ("MEMORY_FILE_PATH", "KEY_FILE", "SECRET_PATH", "AUTH_URL",
                      "TOKEN_DIR", "API_ENDPOINT"):
            self.assertFalse(regen._extmcp_is_secretish(field),
                             f"{field} names a LOCATION, not a credential")

    def test_real_credentials_are_still_caught(self):
        regen = self._regen()
        for field in ("GITHUB_TOKEN", "API_KEY", "CLIENT_SECRET", "PASSWORD",
                      "AUTHORIZATION", "BEARER", "APIKEY"):
            self.assertTrue(regen._extmcp_is_secretish(field), field)

    def test_catalog_patcher_is_wired_into_regen_main(self):
        text = self._read(_REPO_ROOT / "regen_secrets.py")
        self.assertIn("EXTERNAL_MCPS_JSON", text)
        self.assertIn("patch_external_mcps_json(args.mode", text,
                      "the catalog patcher must run in main(), not just be defined")
        self.assertIn("AUTO-VAULTED", text,
                      "push-able must vault a secret BEFORE redacting it (lossless)")

    def test_derived_vault_names_are_stable_and_safe(self):
        regen = self._regen()
        self.assertEqual(regen._extmcp_data_key("Snyk Security Scanner", "API_KEY"),
                         "EXTMCP_SNYK_SECURITY_SCANNER_API_KEY")
        self.assertEqual(regen._extmcp_data_key("octocode", "GITHUB_TOKEN"),
                         "EXTMCP_OCTOCODE_GITHUB_TOKEN")

    def test_build_has_both_catalog_flavours_and_the_seatbelt(self):
        text = self._read(_REPO_ROOT / "build.py")
        self.assertIn("TLAMATINI_BUNDLE_EXTERNAL_MCPS", text)
        self.assertIn("shipped_catalog_document", text)
        self.assertIn("seed_defaults", text, "private build must MERGE the defaults in")
        self.assertIn("ABORT: a PUBLIC build would ship live MCP secret(s)", text)

    def test_public_builder_clears_the_private_catalog_switch(self):
        text = self._read(_REPO_ROOT / "build_complete_public_release.py")
        self.assertIn('env.pop("TLAMATINI_BUNDLE_EXTERNAL_MCPS", None)', text)

    def test_private_builder_sets_the_private_catalog_switch(self):
        text = self._read(_REPO_ROOT / "build_complete_private_release.py")
        self.assertIn("EXTERNAL_MCPS_DEV", text)
        self.assertIn('env["TLAMATINI_BUNDLE_EXTERNAL_MCPS"]', text)


if __name__ == "__main__":
    unittest.main()
