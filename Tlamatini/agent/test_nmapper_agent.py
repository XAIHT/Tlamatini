# ═══════════════════════════════════════════════════════════════════
#   ✦  T L A M A T I N I  ✦   —   "one who knows"
#
#   Created by  Angela López Mendoza   ·   @angelahack1
#   Developer · Architect · Creator of Tlamatini
#
#   Every line of this file was written by Angela López Mendoza.
# ═══════════════════════════════════════════════════════════════════
#   Tlamatini Author Banner — do not remove (releases scrub the name automatically)
"""Hard, real-code tests for the Nmapper agent (LOCAL, use-only nmap bridge) and its
registration across the Tlamatini surfaces.

The unit tests drive the REAL argv builder / preflight / XML parser / section emitter
(no mocking of the code under test) with nmap ABSENT — proving the fail-safe refusals,
the Windows raw-socket downgrade, and that the DEFAULT is an unprivileged connect scan.
The registration tests pin the wrapped-tool spec, the Parametrizer source fields, the
connection view, the CSS gradient and the config.yaml keys so a careless edit is caught.
"""
import importlib.util
import logging
import os
import tempfile
import unittest

from django.test import SimpleTestCase

_AGENT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "agents", "nmapper")
_MODULE_PATH = os.path.join(_AGENT_DIR, "nmapper.py")


def _load_nmapper():
    """Import the pool script with cwd + root-logger handlers saved and restored (the
    module chdir's to its own dir and calls logging.basicConfig at import time)."""
    cwd = os.getcwd()
    handlers = logging.getLogger().handlers[:]
    level = logging.getLogger().level
    try:
        spec = importlib.util.spec_from_file_location("nmapper_under_test", _MODULE_PATH)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod
    finally:
        os.chdir(cwd)
        logging.getLogger().handlers[:] = handlers
        logging.getLogger().setLevel(level)


nm = _load_nmapper()


SAMPLE_XML = """<?xml version="1.0"?>
<nmaprun>
 <host>
  <status state="up"/>
  <address addr="45.33.32.156" addrtype="ipv4"/>
  <ports>
   <port protocol="tcp" portid="22"><state state="open"/><service name="ssh" product="OpenSSH" version="6.6.1p1"/></port>
   <port protocol="tcp" portid="80"><state state="open"/><service name="http" product="Apache httpd"/></port>
   <port protocol="tcp" portid="443"><state state="closed"/><service name="https"/></port>
  </ports>
 </host>
</nmaprun>"""


class NmapperUnitTests(unittest.TestCase):
    # ── config coercion (wrapped Multi-Turn passes everything as strings) ──
    def test_coercion(self):
        self.assertEqual(nm._as_int("top 1000 ports", 5), 1000)
        self.assertEqual(nm._as_int("", 5), 5)
        self.assertEqual(nm._as_int(None, 7), 7)
        self.assertTrue(nm._as_bool("true", False))
        self.assertTrue(nm._as_bool("on", False))
        self.assertFalse(nm._as_bool("no", True))
        self.assertFalse(nm._as_bool("", True) is True)  # empty -> False branch

    def test_timing_flag(self):
        self.assertEqual(nm._timing_flag({"timing": "T4"}), "-T4")
        self.assertEqual(nm._timing_flag({"timing": "4"}), "-T4")
        self.assertEqual(nm._timing_flag({"timing": "-T2"}), "-T2")
        self.assertEqual(nm._timing_flag({"timing": "bogus"}), "-T4")

    def test_port_args(self):
        self.assertEqual(nm._port_args("full", "", 1000), ["-p-"])
        self.assertEqual(nm._port_args("quick", "", 500), ["--top-ports", "500"])
        self.assertEqual(nm._port_args("quick", "22,80", 500), ["-p", "22,80"])
        self.assertEqual(nm._port_args("version", "", 1000), [])

    # ── argv builder: the DEFAULT is an unprivileged connect scan ──
    def test_build_argv_quick_connect_default(self):
        argv = nm._build_argv("quick", "nmap", {"target": "scanme.nmap.org"}, "o.xml", "o.nmap", {})
        self.assertEqual(argv[0], "nmap")
        for flag in ("-sT", "-sV", "-sC", "-Pn", "-T4", "--top-ports", "-oX", "-oN"):
            self.assertIn(flag, argv)
        self.assertNotIn("-sS", argv)  # never SYN by default
        self.assertEqual(argv[-1], "scanme.nmap.org")

    def test_build_argv_syn_when_requested(self):
        argv = nm._build_argv("quick", "nmap", {"target": "h", "scan_technique": "syn"}, "o.xml", "o.nmap", {})
        self.assertIn("-sS", argv)
        self.assertNotIn("-sT", argv)

    def test_build_argv_downgrade_forces_connect(self):
        # the preflight downgrade dict wins over the requested syn technique
        argv = nm._build_argv("quick", "nmap", {"target": "h", "scan_technique": "syn"},
                              "o.xml", "o.nmap", {"technique": "connect"})
        self.assertIn("-sT", argv)
        self.assertNotIn("-sS", argv)

    def test_build_argv_host_discovery(self):
        argv = nm._build_argv("host_discovery", "nmap", {"target": "10.0.0.0/24"}, "o.xml", "o.nmap", {})
        self.assertIn("-sn", argv)
        self.assertNotIn("-Pn", argv)
        self.assertNotIn("-sT", argv)

    def test_build_argv_scripts(self):
        argv = nm._build_argv("scripts", "nmap", {"target": "h", "nse_scripts": "http-title,banner", "ports": "80"},
                              "o.xml", "o.nmap", {})
        self.assertIn("--script", argv)
        self.assertIn("http-title,banner", argv)
        self.assertIn("-p", argv)
        self.assertIn("80", argv)

    def test_build_argv_targets_file(self):
        argv = nm._build_argv("quick", "nmap", {"targets_file": "hosts.txt"}, "o.xml", "o.nmap", {})
        self.assertIn("-iL", argv)
        self.assertIn("hosts.txt", argv)

    # ── custom_args safety (shell metacharacters rejected) ──
    def test_reject_custom_args_metachars(self):
        self.assertTrue(nm._reject_custom_args("--script vuln; rm -rf /"))
        self.assertTrue(nm._reject_custom_args("-p 80 && evil"))
        self.assertTrue(nm._reject_custom_args("`whoami`"))
        self.assertEqual(nm._reject_custom_args("--script vuln -p 80 --open"), "")

    def test_wide_cidr_note(self):
        self.assertTrue(nm._wide_cidr_note("10.0.0.0/8"))
        self.assertTrue(nm._wide_cidr_note("0.0.0.0/0"))
        self.assertFalse(nm._wide_cidr_note("10.0.0.0/24"))
        self.assertFalse(nm._wide_cidr_note("scanme.nmap.org"))

    # ── fail-safe preflight (REFUSE, never crash) ──
    def test_preflight_refuses_when_nmap_missing(self):
        pf = nm._preflight("quick", {"target": "h", "auto_install": False}, "", True)
        self.assertFalse(pf["ok"])
        self.assertTrue(any("not installed" in f for f in pf["fatals"]))

    def test_preflight_refuses_missing_target(self):
        pf = nm._preflight("quick", {"target": "", "auto_install": False}, "nmap.exe", True)
        self.assertFalse(pf["ok"])
        self.assertTrue(any("needs a target" in f for f in pf["fatals"]))

    def test_preflight_rejects_custom_metachars(self):
        pf = nm._preflight("custom", {"target": "h", "custom_args": "-p 80; id"}, "nmap.exe", True)
        self.assertFalse(pf["ok"])
        self.assertTrue(any("metacharacter" in f for f in pf["fatals"]))

    def test_preflight_ready_connect_default(self):
        pf = nm._preflight("quick", {"target": "scanme.nmap.org"}, "nmap.exe", True)
        self.assertTrue(pf["ok"])

    @unittest.skipUnless(os.name == "nt", "Windows-specific raw-socket downgrade")
    def test_preflight_downgrades_syn_without_npcap(self):
        pf = nm._preflight("quick", {"target": "h", "scan_technique": "syn"}, "nmap.exe", False)
        self.assertTrue(pf["ok"])  # a warning + downgrade, NOT a fatal
        self.assertEqual(pf["downgrade"].get("technique"), "connect")
        self.assertTrue(pf["warnings"])

    @unittest.skipUnless(os.name == "nt", "Windows-specific raw-socket path")
    def test_preflight_udp_without_npcap_refused(self):
        pf = nm._preflight("udp", {"target": "h"}, "nmap.exe", False)
        self.assertFalse(pf["ok"])

    # ── output parsing + structured section ──
    def test_parse_xml(self):
        fd, path = tempfile.mkstemp(suffix=".xml")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(SAMPLE_XML)
        try:
            hosts_up, open_ports = nm._parse_xml(path)
        finally:
            os.remove(path)
        self.assertEqual(hosts_up, 1)
        joined = " ; ".join(open_ports)
        self.assertIn("22/tcp", joined)
        self.assertIn("ssh", joined)
        self.assertIn("80/tcp", joined)
        self.assertNotIn("443", joined)  # a closed port is excluded

    def test_parse_xml_missing_file_never_raises(self):
        hosts_up, open_ports = nm._parse_xml(os.path.join(tempfile.gettempdir(), "nope_nmapper.xml"))
        self.assertEqual(hosts_up, 0)
        self.assertEqual(open_ports, [])

    def test_emit_section_shape(self):
        with self.assertLogs(level="INFO") as cm:
            nm._emit_section({"action": "quick", "success": "true"}, "body text")
        out = "\n".join(cm.output)
        self.assertIn("INI_SECTION_NMAPPER<<<", out)
        self.assertIn(">>>END_SECTION_NMAPPER", out)
        self.assertIn("action: quick", out)
        self.assertIn("body text", out)

    def test_install_url_default(self):
        url = nm._install_url({})
        self.assertTrue(url.startswith("https://nmap.org/dist/nmap-"))
        self.assertTrue(url.endswith("-setup.exe"))
        self.assertIn("7.99", nm._install_url({"nmap_version": "7.99"}))
        self.assertEqual(nm._install_url({"nmap_install_url": "https://example/x.exe"}), "https://example/x.exe")


class NmapperRegistrationTests(SimpleTestCase):
    def test_wrapped_spec(self):
        from agent.chat_agent_registry import WRAPPED_CHAT_AGENT_BY_TOOL_NAME
        spec = WRAPPED_CHAT_AGENT_BY_TOOL_NAME.get("chat_agent_nmapper")
        self.assertIsNotNone(spec)
        self.assertEqual(spec.display_name, "Nmapper")
        self.assertEqual(spec.template_dir, "nmapper")
        self.assertEqual(spec.tool_description, "Chat-Agent-Nmapper")

    def test_parametrizer_output_fields_match_section_header(self):
        from agent.services.agent_contracts import _PARAMETRIZER_OUTPUT_FIELDS
        fields = _PARAMETRIZER_OUTPUT_FIELDS.get("nmapper")
        self.assertIsNotNone(fields)
        # the INI_SECTION_NMAPPER KV header (main()'s outcome dict) + response_body
        expected = {
            "action", "target", "scan_technique", "ports", "return_code", "success",
            "hosts_up", "open_ports", "npcap_present", "xml_path", "output_path", "stage",
            "response_body",
        }
        self.assertEqual(set(fields), expected)

    def test_contract_resolves(self):
        from agent.services.agent_contracts import get_agent_contract
        contract = get_agent_contract("nmapper")
        self.assertIsNotNone(contract)
        self.assertEqual(contract.agent_type, "nmapper")

    def test_connection_view_exists(self):
        from agent import views
        self.assertTrue(callable(getattr(views, "update_nmapper_connection_view", None)))

    def test_section_agent_type_registered(self):
        # static text check: parametrizer.py is a pool script (importing it has side
        # effects), so assert membership by reading the source, like the JS contract tests.
        pmod = os.path.join(_AGENT_DIR, "..", "parametrizer", "parametrizer.py")
        with open(os.path.abspath(pmod), "r", encoding="utf-8") as f:
            src = f.read()
        self.assertIn("'nmapper',", src)

    def test_css_gradient_present_and_unique(self):
        css = os.path.join(os.path.dirname(_AGENT_DIR), "..", "static", "agent", "css", "agentic_control_panel.css")
        with open(os.path.abspath(css), "r", encoding="utf-8") as f:
            src = f.read()
        self.assertIn(".canvas-item.nmapper-agent {", src)
        self.assertEqual(src.count(".canvas-item.nmapper-agent {"), 1)

    def test_config_yaml_keys(self):
        import yaml
        with open(os.path.join(_AGENT_DIR, "config.yaml"), "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f)
        for key in ("action", "target", "ports", "top_ports", "timing", "scan_technique",
                    "version_detect", "default_scripts", "nse_scripts", "os_detect",
                    "skip_host_discovery", "custom_args", "nmap_executable", "auto_install",
                    "nmap_version", "preflight", "command_timeout", "output_dir",
                    "source_agents", "target_agents"):
            self.assertIn(key, cfg)
        self.assertEqual(cfg["action"], "quick")
        self.assertEqual(cfg["scan_technique"], "connect")


if __name__ == "__main__":
    unittest.main()
