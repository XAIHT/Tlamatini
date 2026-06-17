"""Verify the Parametrizer change Codex made for MCP Doctor works end to end.

Codex registered ``'mcp_doctor'`` in ``parametrizer.SECTION_AGENT_TYPES`` and
gave the agent contract matching ``parametrizer_fields``. This test proves the
WHOLE source->parse chain: the MCP Doctor agent's REAL emitted
``INI_SECTION_MCP_DOCTOR`` block is parsed by the REAL Parametrizer parser, and
every field the contract advertises as addressable (the ones a downstream
``{marker}`` mapping can reference) actually appears in the parsed output.

Both agent scripts are standalone pool modules with import-time side effects
(chdir + log truncation), so they are loaded in isolation with cwd / root-logger
handlers restored afterward.
"""

from __future__ import annotations

import importlib.util
import json
import logging
import os
import tempfile
from pathlib import Path

from django.test import SimpleTestCase

from agent.services.agent_contracts import get_parametrizer_source_fields

_AGENT_DIR = Path(__file__).resolve().parent


def _load_agent_module(rel_parts, mod_name):
    path = _AGENT_DIR.joinpath(*rel_parts)
    spec = importlib.util.spec_from_file_location(mod_name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    root = logging.getLogger()
    before = list(root.handlers)
    cwd = os.getcwd()
    try:
        spec.loader.exec_module(module)
    finally:
        os.chdir(cwd)
        for handler in list(root.handlers):
            if handler not in before:
                root.removeHandler(handler)
    return module


PARAM = _load_agent_module(["agents", "parametrizer", "parametrizer.py"], "param_mod_for_param_test")
MCP_DOCTOR = _load_agent_module(["agents", "mcp_doctor", "mcp_doctor.py"], "mcpdoc_mod_for_param_test")


def _emit_and_capture(result):
    """Run the agent's real _emit_section and capture the logged section text."""
    captured = []

    class _Cap(logging.Handler):
        def emit(self, record):
            captured.append(record.getMessage())

    handler = _Cap()
    root = logging.getLogger()
    root.addHandler(handler)
    try:
        MCP_DOCTOR._emit_section(result)
    finally:
        root.removeHandler(handler)
    for message in captured:
        if "INI_SECTION_MCP_DOCTOR" in message:
            return message
    raise AssertionError("MCP Doctor did not emit an INI_SECTION_MCP_DOCTOR block")


class ParametrizerMcpDoctorRoundTripTests(SimpleTestCase):
    def test_mcp_doctor_is_registered_source_type(self):
        self.assertIn("mcp_doctor", PARAM.SECTION_AGENT_TYPES)

    def test_agent_section_parses_through_real_parametrizer(self):
        with tempfile.TemporaryDirectory() as tmp:
            catalog = os.path.join(tmp, "external_mcps.json")
            with open(catalog, "w", encoding="utf-8") as fh:
                json.dump({"mcpServers": {"Proxy": {
                    "command": "python", "args": ["-m", "some_server"],
                    "env": {"API_KEY": "YOUR_KEY_HERE"}}}, "active": ["Proxy"]}, fh)
            result = MCP_DOCTOR.diagnose({"catalog_path": catalog, "server_key": "Proxy"})

        section = _emit_and_capture(result)

        # The REAL Parametrizer parser extracts the block.
        blocks = PARAM.parse_unified_output(section, "mcp_doctor")
        self.assertEqual(len(blocks), 1)
        fields = blocks[0]
        self.assertEqual(fields.get("server_key"), "Proxy")
        self.assertEqual(fields.get("transport"), "stdio")
        for key in ("server_key", "transport", "runtime", "supported", "status", "catalog_path"):
            self.assertIn(key, fields, f"header field {key!r} missing after parse")
        self.assertIn("response_body", fields)
        self.assertTrue(fields["response_body"])

    def test_contract_fields_all_resolve_against_real_emission(self):
        """Every field the contract advertises (minus response_body) must appear in
        the parsed section — otherwise a downstream {marker} mapping silently fails."""
        with tempfile.TemporaryDirectory() as tmp:
            catalog = os.path.join(tmp, "external_mcps.json")
            with open(catalog, "w", encoding="utf-8") as fh:
                json.dump({"mcpServers": {"Proxy": {"command": "python", "args": ["x.py"]}},
                           "active": []}, fh)
            result = MCP_DOCTOR.diagnose({"catalog_path": catalog, "server_key": "Proxy"})

        fields = PARAM.parse_unified_output(_emit_and_capture(result), "mcp_doctor")[0]
        advertised = set(get_parametrizer_source_fields()["mcp_doctor"]) - {"response_body"}
        missing = advertised - set(fields.keys())
        self.assertEqual(missing, set(), f"contract advertises unparseable fields: {missing}")

    def test_single_lane_next_parser_also_works(self):
        with tempfile.TemporaryDirectory() as tmp:
            catalog = os.path.join(tmp, "external_mcps.json")
            with open(catalog, "w", encoding="utf-8") as fh:
                json.dump({"mcpServers": {"Proxy": {"command": "python"}}, "active": []}, fh)
            result = MCP_DOCTOR.diagnose({"catalog_path": catalog, "server_key": "Proxy"})

        nxt = PARAM.parse_next_unified_output(_emit_and_capture(result), "mcp_doctor")
        self.assertIsNotNone(nxt)
        parsed, end_offset = nxt
        self.assertEqual(parsed.get("server_key"), "Proxy")
        self.assertGreater(end_offset, 0)
