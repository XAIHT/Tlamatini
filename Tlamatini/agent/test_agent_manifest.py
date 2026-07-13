# ═══════════════════════════════════════════════════════════════════
#   ✦  T L A M A T I N I  ✦   —   "one who knows"
#
#   Created by  Angela López Mendoza   ·   @angelahack1
#   Developer · Architect · Creator of Tlamatini
#
#   Every line of this file was written by Angela López Mendoza.
# ═══════════════════════════════════════════════════════════════════
#   Tlamatini Author Banner — do not remove (releases scrub the name automatically)
"""Tests for the companion-app discovery surface (Tlamatini-FlowPills PROP-001…003):

  * ``agent/agent_manifest.py`` — manifest generation, EXCLUSIONS, and FRESHNESS
    (the regression for the "stale hashes" gap: a content edit to an existing
    agent file must refresh its sha256 even though the set of names is unchanged).
  * ``agent/windows_app_registration.py`` — the ``HKCU\\Software\\XAIHT\\Tlamatini``
    discovery key (fail-open off Windows; a NON-DESTRUCTIVE live round-trip on it).
  * ``uninstall.py`` — the ``.tlamatini-preserved-agents.json`` marker now carries a
    ``manifest_sha256`` checksum and re-stamps the manifest kind to ``preserved``.

Second-sprint coverage (Tlamatini-FlowPills-Lookup-2nd-Sprint.md):
  * ``agent/apps.py`` — discovery is scheduled FIRST in ``ready()``, import-
    independent, and idempotent via a dedicated gate (REQ-S2-TEST-001/002).
  * ``register_discovery_entry`` clears STALE optional values (REQ-S2-TEST-004).
  * ``read_manifest`` accepts a UTF-8 BOM (REQ-S2-TEST-005).
  * ``install.py`` companion registration is independent of ARP / Uninstaller.exe
    and writes all six values, empty when unknown (REQ-S2-TEST-003).

SECRET-SAFE (REQ-S2-TEST-007): every test here is a plain ``unittest.TestCase`` that
imports only Django-FREE modules and touches only temp dirs + the backed-up HKCU
key. It never hydrates secrets, so it can run WITHOUT booting the config stack:

    python -m unittest agent.test_agent_manifest          # secret-safe, no Django boot
    python manage.py test agent.test_agent_manifest        # also works
"""
import hashlib
import inspect
import json
import os
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

from agent import agent_manifest as am
from agent import windows_app_registration as war

_IS_WINDOWS = os.name == "nt"


def _make_agent(root, name, script_body="print('x')\n", config_body="a: 1\n"):
    """Create a complete ``<root>/<name>/{<name>.py,config.yaml}`` template."""
    d = os.path.join(root, name)
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, name + ".py"), "w", encoding="utf-8") as f:
        f.write(script_body)
    with open(os.path.join(d, "config.yaml"), "w", encoding="utf-8") as f:
        f.write(config_body)


class ManifestGenerationTests(unittest.TestCase):
    def test_counts_complete_and_excludes_noise(self):
        with tempfile.TemporaryDirectory() as root:
            _make_agent(root, "starter")
            _make_agent(root, "ender")
            os.makedirs(os.path.join(root, "broken"))  # missing config.yaml
            with open(os.path.join(root, "broken", "broken.py"), "w") as f:
                f.write("x = 1\n")
            os.makedirs(os.path.join(root, "pools"))
            os.makedirs(os.path.join(root, "__pycache__"))
            self.assertEqual(am.count_complete_agents(root), 2)
            types = [t for t, _, _ in am.iter_complete_agents(root)]
            self.assertEqual(types, ["ender", "starter"])  # sorted, complete only

    def test_manifest_fields_and_sha256(self):
        with tempfile.TemporaryDirectory() as root:
            _make_agent(root, "starter")
            m = am.build_manifest(root, kind="source", version="9.9.9")
            self.assertEqual(m["product"], "Tlamatini")
            self.assertEqual(m["agent_count"], 1)
            self.assertEqual(m["agents_root_kind"], "source")
            self.assertEqual(m["version"], "9.9.9")
            entry = m["agents"][0]
            self.assertEqual(entry["type"], "starter")
            self.assertIn("script", entry["sha256"])
            self.assertIn("config", entry["sha256"])

    def test_catalog_version_changes_on_set_change(self):
        with tempfile.TemporaryDirectory() as root:
            _make_agent(root, "starter")
            v1 = am.compute_agent_catalog_version(root)
            _make_agent(root, "ender")
            v2 = am.compute_agent_catalog_version(root)
            self.assertNotEqual(v1, v2)
            self.assertTrue(v2.startswith("2-"))

    def test_read_manifest_accepts_utf8_bom(self):
        # REQ-S2-TEST-005: a manifest written WITH a UTF-8 BOM must still load.
        with tempfile.TemporaryDirectory() as root:
            _make_agent(root, "starter")
            m = am.build_manifest(root, kind="source", version="1.0.0")
            path = os.path.join(root, am.MANIFEST_FILENAME)
            with open(path, "w", encoding="utf-8-sig") as f:  # writes a BOM
                json.dump(m, f)
            data = am.read_manifest(root)
            self.assertIsNotNone(data)
            self.assertEqual(data["product"], "Tlamatini")
            self.assertEqual(data["agent_count"], 1)


class ManifestFreshnessTests(unittest.TestCase):
    """Regression for the Codex "stale hashes" High finding."""

    def test_content_edit_refreshes_sha256(self):
        with tempfile.TemporaryDirectory() as root:
            _make_agent(root, "starter", script_body="print('v1')\n")
            path = am.ensure_manifest(root, kind="source", version="1.0.0")
            sha1 = json.load(open(path, encoding="utf-8"))["agents"][0]["sha256"]["script"]

            # Edit the SAME agent's script — the SET of names is unchanged.
            _make_agent(root, "starter", script_body="print('v2 CHANGED')\n")
            am.ensure_manifest(root, kind="source", version="1.0.0")
            sha2 = json.load(open(path, encoding="utf-8"))["agents"][0]["sha256"]["script"]

            self.assertNotEqual(sha1, sha2, "sha256 must refresh after a content edit")

    def test_version_and_kind_changes_refresh(self):
        with tempfile.TemporaryDirectory() as root:
            _make_agent(root, "starter")
            path = am.ensure_manifest(root, kind="installed", version="1.0.0")
            self.assertEqual(json.load(open(path, encoding="utf-8"))["version"], "1.0.0")
            am.ensure_manifest(root, kind="preserved", version="2.0.0")
            m = json.load(open(path, encoding="utf-8"))
            self.assertEqual(m["version"], "2.0.0")
            self.assertEqual(m["agents_root_kind"], "preserved")

    def test_no_change_does_not_churn_generated_at(self):
        with tempfile.TemporaryDirectory() as root:
            _make_agent(root, "starter")
            path = am.ensure_manifest(root, kind="source", version="1.0.0")
            gen1 = json.load(open(path, encoding="utf-8"))["generated_at"]
            am.ensure_manifest(root, kind="source", version="1.0.0")  # identical inputs
            gen2 = json.load(open(path, encoding="utf-8"))["generated_at"]
            self.assertEqual(gen1, gen2, "unchanged catalog must not rewrite the file")


class DiscoveryRegistryFailOpenTests(unittest.TestCase):
    def test_noop_off_windows(self):
        with patch.object(war, "is_supported", return_value=False):
            self.assertFalse(war.register_discovery_entry(agents_root="x"))
            self.assertFalse(war.unregister_discovery_entry())

    def test_key_path_is_stable(self):
        # uninstall.py / installer read these exact paths — keep them in lockstep.
        self.assertEqual(war.XAIHT_DISCOVERY_KEY, r"Software\XAIHT\Tlamatini")
        self.assertEqual(war.XAIHT_PARENT_KEY, r"Software\XAIHT")


def _read_all_values(key_path):
    """Snapshot every REG value under ``key_path``, or ``None`` if absent."""
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path) as k:
            out = {}
            i = 0
            while True:
                try:
                    name, data, typ = winreg.EnumValue(k, i)
                except OSError:
                    break
                out[name] = (data, typ)
                i += 1
            return out
    except FileNotFoundError:
        return None


@unittest.skipUnless(_IS_WINDOWS, "Windows-only registry round-trip")
class DiscoveryRegistryLiveTests(unittest.TestCase):
    """Live HKCU round-trip that RESTORES any pre-existing real discovery key, so a
    developer's actual `HKCU\\Software\\XAIHT\\Tlamatini` is never clobbered."""

    def setUp(self):
        self._backup = _read_all_values(war.XAIHT_DISCOVERY_KEY)

    def tearDown(self):
        import winreg

        war.unregister_discovery_entry()
        if self._backup is not None:
            with winreg.CreateKey(winreg.HKEY_CURRENT_USER, war.XAIHT_DISCOVERY_KEY) as k:
                for name, (data, typ) in self._backup.items():
                    winreg.SetValueEx(k, name, 0, typ, data)

    def test_register_read_unregister(self):
        import winreg

        self.assertTrue(
            war.register_discovery_entry(
                install_location=r"C:\TlmTest",
                agents_root=r"C:\TlmTest\agents",
                agent_manifest_path=r"C:\TlmTest\agents\_tlamatini_agents_manifest.json",
                version="9.9.9",
                agent_catalog_version="85-deadbeef",
            )
        )
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, war.XAIHT_DISCOVERY_KEY) as k:
            self.assertEqual(winreg.QueryValueEx(k, "AgentsRoot")[0], r"C:\TlmTest\agents")
            self.assertEqual(winreg.QueryValueEx(k, "Version")[0], "9.9.9")
            self.assertEqual(
                winreg.QueryValueEx(k, "AgentCatalogVersion")[0], "85-deadbeef"
            )
        self.assertTrue(war.unregister_discovery_entry())
        self.assertTrue(war.unregister_discovery_entry())  # idempotent

    def test_empty_optional_values_clear_stale(self):
        # REQ-S2-TEST-004: a re-registration with empty Version / AgentCatalogVersion
        # must OVERWRITE any pre-existing value with an empty REG_SZ — never leave
        # stale metadata from a previous install/source root.
        import winreg

        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, war.XAIHT_DISCOVERY_KEY) as k:
            winreg.SetValueEx(k, "Version", 0, winreg.REG_SZ, "OLD-9.9.9")
            winreg.SetValueEx(k, "AgentCatalogVersion", 0, winreg.REG_SZ, "OLD-cat")

        self.assertTrue(
            war.register_discovery_entry(
                install_location=r"C:\TlmTest",
                agents_root=r"C:\TlmTest\agents",
                version="",
                agent_catalog_version="",
            )
        )
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, war.XAIHT_DISCOVERY_KEY) as k:
            v, vt = winreg.QueryValueEx(k, "Version")
            c, ct = winreg.QueryValueEx(k, "AgentCatalogVersion")
        self.assertEqual(v, "")  # cleared, not stale
        self.assertEqual(c, "")
        self.assertEqual(vt, winreg.REG_SZ)
        self.assertEqual(ct, winreg.REG_SZ)


class PreservedMarkerTests(unittest.TestCase):
    """The uninstaller's preserved marker must carry manifest path + checksum, and
    re-stamp the manifest's kind to 'preserved' (Codex Medium finding)."""

    def _uninstaller_cls(self):
        import importlib
        import sys

        repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
        if repo_root not in sys.path:
            sys.path.insert(0, repo_root)
        try:
            mod = importlib.import_module("uninstall")
        except Exception as exc:  # noqa: BLE001
            self.skipTest("uninstall.py not importable here: %s" % exc)
        return mod.FancyUninstaller

    def test_marker_carries_manifest_checksum_and_restamps(self):
        cls = self._uninstaller_cls()
        with tempfile.TemporaryDirectory() as root:
            agents = os.path.join(root, "agents")
            _make_agent(agents, "starter")
            am.write_manifest(agents, kind="installed", version="1.0.0")

            inst = cls.__new__(cls)
            inst.version = "1.0.0"
            inst._write_preserved_agents_marker(agents, root)

            marker_path = os.path.join(agents, ".tlamatini-preserved-agents.json")
            marker = json.load(open(marker_path, encoding="utf-8"))
            self.assertTrue(marker["preserved"])
            self.assertEqual(marker["agent_count"], 1)
            self.assertTrue(marker["manifest_path"])
            self.assertEqual(len(marker["manifest_sha256"]), 64)  # sha256 hex digest

            mpath = os.path.join(agents, "_tlamatini_agents_manifest.json")
            manifest = json.load(open(mpath, encoding="utf-8"))
            self.assertEqual(manifest["agents_root_kind"], "preserved")
            # The recorded checksum matches the FINAL (re-stamped) on-disk manifest.
            with open(mpath, "rb") as f:
                self.assertEqual(marker["manifest_sha256"], hashlib.sha256(f.read()).hexdigest())


class DiscoverySchedulingTests(unittest.TestCase):
    """REQ-S2-PUB / REQ-S2-TEST-001/002: discovery publication is scheduled FIRST in
    ``ready()``, import-independent, and idempotent via a dedicated gate that is
    separate from ``mcp_server_running``."""

    def _apps(self):
        try:
            from agent import apps as apps_mod
        except Exception as exc:  # noqa: BLE001
            self.skipTest("agent.apps not importable here: %s" % exc)
        return apps_mod

    def test_eligibility_predicate_modes(self):
        f = self._apps()._discovery_publish_eligible
        # Application-server modes publish (REQ-S2-PUB-004):
        self.assertTrue(f("manage.py runserver --noreload", None))
        self.assertTrue(f("manage.py startserver", None))
        self.assertTrue(f("daphne -b 0.0.0.0 tlamatini.asgi:application", None))
        self.assertTrue(f("python -m uvicorn tlamatini.asgi:application", None))
        # runserver WITH the autoreloader: only the worker child publishes.
        self.assertFalse(f("manage.py runserver", None))
        self.assertTrue(f("manage.py runserver", "true"))
        # Ordinary management commands never publish.
        self.assertFalse(f("manage.py test agent.test_agent_manifest", None))
        self.assertFalse(f("manage.py migrate", None))

    def test_schedules_import_independently_and_idempotently(self):
        apps_mod = self._apps()
        from agent import agent_manifest as am_mod
        from agent import version as ver_mod

        calls = []
        apps_mod._discovery_thread_started = False  # reset the dedicated gate
        try:
            with patch.object(ver_mod, "get_version", return_value="9.9.9"), \
                 patch.object(am_mod, "publish_discovery",
                              side_effect=lambda **kw: calls.append(kw)), \
                 patch.object(sys, "argv", ["manage.py", "startserver"]):
                started1 = apps_mod._schedule_companion_discovery()
                for t in threading.enumerate():
                    if t.name == "DiscoveryPublish":
                        t.join(timeout=5)
                started2 = apps_mod._schedule_companion_discovery()
        finally:
            apps_mod._discovery_thread_started = False
        self.assertTrue(started1, "an eligible launch must schedule discovery")
        self.assertFalse(started2, "the dedicated gate must block a 2nd publisher")
        self.assertEqual(len(calls), 1, "publish_discovery must run exactly once")

    def test_scheduled_before_heavy_imports_in_ready(self):
        # REQ-S2-PUB-001: the scheduling call must precede the optional-subsystem
        # imports so an import failure below cannot prevent publication.
        src = inspect.getsource(self._apps().AgentConfig.ready)
        call_at = src.index("_schedule_companion_discovery()")
        self.assertLess(call_at, src.index("mcp_system_server"))
        self.assertLess(call_at, src.index("global_state"))
        self.assertLess(call_at, src.index("from .models import"))


@unittest.skipUnless(_IS_WINDOWS, "Windows-only registry round-trip")
class InstallerCompanionRegistrationTests(unittest.TestCase):
    """REQ-S2-TEST-003 / REQ-S2-INSTALL-*: the installer registers companion
    discovery INDEPENDENTLY of ARP / Uninstaller.exe and writes all six values
    (empty when unknown). Backs up + restores the real HKCU key."""

    def setUp(self):
        self._backup = _read_all_values(war.XAIHT_DISCOVERY_KEY)

    def tearDown(self):
        import winreg

        war.unregister_discovery_entry()
        if self._backup is not None:
            with winreg.CreateKey(winreg.HKEY_CURRENT_USER, war.XAIHT_DISCOVERY_KEY) as k:
                for name, (data, typ) in self._backup.items():
                    winreg.SetValueEx(k, name, 0, typ, data)

    def _installer(self, version="1.2.3"):
        import importlib

        repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
        if repo_root not in sys.path:
            sys.path.insert(0, repo_root)
        try:
            mod = importlib.import_module("install")
        except Exception as exc:  # noqa: BLE001 (tkinter may be unavailable)
            self.skipTest("install.py not importable here: %s" % exc)
        inst = mod.FancyInstaller.__new__(mod.FancyInstaller)
        inst.version = version
        return inst

    def test_registers_with_manifest_and_no_uninstaller(self):
        import winreg

        inst = self._installer(version="1.2.3")
        with tempfile.TemporaryDirectory() as target:
            agents = os.path.join(target, "agents")
            _make_agent(agents, "starter")
            am.write_manifest(agents, kind="installed", version="1.2.3")
            # No Uninstaller.exe and no ARP entry exist here — registration must
            # still happen (REQ-S2-INSTALL-002/003).
            inst._register_companion_discovery(target)
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, war.XAIHT_DISCOVERY_KEY) as k:
                self.assertEqual(winreg.QueryValueEx(k, "AgentsRoot")[0], agents)
                self.assertEqual(winreg.QueryValueEx(k, "Version")[0], "1.2.3")
                self.assertTrue(winreg.QueryValueEx(k, "AgentCatalogVersion")[0])
                self.assertEqual(winreg.QueryValueEx(k, "SourceAgentsRoot")[0], "")
                self.assertTrue(winreg.QueryValueEx(k, "AgentManifestPath")[0])

    def test_registers_all_six_when_manifest_absent(self):
        import winreg

        inst = self._installer(version="")
        with tempfile.TemporaryDirectory() as target:
            os.makedirs(os.path.join(target, "agents"))  # agents dir, but NO manifest
            inst._register_companion_discovery(target)
            names = set(_read_all_values(war.XAIHT_DISCOVERY_KEY) or {})
            for req in ("InstallLocation", "AgentsRoot", "SourceAgentsRoot",
                        "AgentManifestPath", "Version", "AgentCatalogVersion"):
                self.assertIn(req, names)  # all six present even with no manifest
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, war.XAIHT_DISCOVERY_KEY) as k:
                self.assertEqual(winreg.QueryValueEx(k, "AgentManifestPath")[0], "")
                self.assertEqual(winreg.QueryValueEx(k, "AgentCatalogVersion")[0], "")
                self.assertEqual(winreg.QueryValueEx(k, "Version")[0], "")


if __name__ == "__main__":
    unittest.main()
