# ═══════════════════════════════════════════════════════════════════
#   ✦  T L A M A T I N I  ✦   —   "one who knows"
#
#   Created by  Angela López Mendoza   ·   @angelahack1
#   Developer · Architect · Creator of Tlamatini
#
#   Every line of this file was written by Angela López Mendoza.
# ═══════════════════════════════════════════════════════════════════
#   Tlamatini Author Banner — do not remove (releases scrub the name automatically)
"""External MCP universal hardening tests.

This suite intentionally uses many generated test methods. The point is not a
single happy-path assertion; it is a broad matrix over the failure forest that
hurt External MCPs: config variants, BOM JSON, transport naming, command
runtime inference, placeholder secrets, schema unions, Step-by-Step plumbing,
and the MCP Doctor wrapped/canvas-agent registration.
"""

from __future__ import annotations

import importlib.util
import json
import logging
import os
import tempfile
from pathlib import Path
from typing import Any
from unittest.mock import patch

import yaml
from django.test import SimpleTestCase

from agent import external_mcp_manager as em
from agent.chat_agent_registry import WRAPPED_CHAT_AGENT_BY_TOOL_NAME
from agent.global_execution_planner import _external_mcp_force_names
from agent.mcp_agent import _build_system_prompt, _is_external_mcp_tool_name
from agent.services.agent_contracts import get_agent_contract, get_parametrizer_source_fields


_AGENT_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _AGENT_DIR.parents[1]


def _read_repo_text(*parts: str) -> str:
    path = _REPO_ROOT.joinpath(*parts)
    if not path.exists() and parts:
        first = parts[0]
        if first.startswith("agent/") or first.startswith("agent\\"):
            path = _REPO_ROOT / "Tlamatini" / first
    return path.read_text(encoding="utf-8")


def _load_mcp_doctor_module():
    module_path = _AGENT_DIR / "agents" / "mcp_doctor" / "mcp_doctor.py"
    spec = importlib.util.spec_from_file_location("agent_mcp_doctor_module_for_tests", module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load MCP Doctor module from {module_path}")
    module = importlib.util.module_from_spec(spec)
    root = logging.getLogger()
    handlers_before = list(root.handlers)
    cwd = os.getcwd()
    try:
        spec.loader.exec_module(module)
    finally:
        os.chdir(cwd)
        for handler in list(root.handlers):
            if handler not in handlers_before:
                root.removeHandler(handler)
    return module


MCP_DOCTOR = _load_mcp_doctor_module()


def _method_name(prefix: str, idx: int, label: str) -> str:
    cleaned = "".join(ch.lower() if ch.isalnum() else "_" for ch in label).strip("_")
    return f"test_{prefix}_{idx:03d}_{cleaned[:48]}"


TRANSPORT_CASES: list[tuple[str, dict[str, Any], str]] = [
    ("command_defaults_to_stdio", {"command": "docker"}, "stdio"),
    ("declared_stdio", {"transport": "stdio"}, "stdio"),
    ("declared_ws_alias", {"transport": "ws"}, "websocket"),
    ("declared_websocket", {"transport": "websocket"}, "websocket"),
    ("declared_socket_alias", {"transport": "socket"}, "tcp"),
    ("declared_raw_alias", {"transport": "raw"}, "tcp"),
    ("declared_tcp", {"transport": "tcp"}, "tcp"),
    ("declared_pipe_alias", {"transport": "pipe"}, "named-pipe"),
    ("declared_named_pipe", {"transport": "named-pipe"}, "named-pipe"),
    ("declared_http_alias", {"transport": "http"}, "streamable-http"),
    ("declared_streamable_http", {"transport": "streamable-http"}, "streamable-http"),
    ("declared_streamable_http_underscore", {"transport": "streamable_http"}, "streamable-http"),
    ("type_ws_alias", {"type": "ws"}, "websocket"),
    ("type_http_alias", {"type": "http"}, "streamable-http"),
    ("wss_url", {"url": "wss://example.test/mcp"}, "websocket"),
    ("ws_url", {"url": "ws://example.test/mcp"}, "websocket"),
    ("https_url", {"url": "https://example.test/mcp"}, "streamable-http"),
    ("http_url", {"url": "http://example.test/mcp"}, "streamable-http"),
    ("https_sse_url", {"url": "https://example.test/sse"}, "sse"),
    ("explicit_sse_flag", {"url": "https://example.test/mcp", "sse": True}, "sse"),
    ("tcp_url", {"url": "tcp://127.0.0.1:9911"}, "tcp"),
    ("socket_url", {"url": "socket://127.0.0.1:9911"}, "tcp"),
    ("raw_url", {"url": "raw://127.0.0.1:9911"}, "tcp"),
    ("pipe_url", {"url": "pipe://tlamatini"}, "named-pipe"),
    ("npipe_url", {"url": "npipe://./pipe/tlamatini"}, "named-pipe"),
    ("unix_socket_url", {"url": "unix:///tmp/mcp.sock"}, "named-pipe"),
    ("host_port", {"host": "127.0.0.1", "port": 9911}, "tcp"),
    ("socket_path", {"socketPath": "/tmp/mcp.sock"}, "named-pipe"),
    ("named_pipe_field", {"namedPipe": r"\\.\pipe\tlamatini"}, "named-pipe"),
    ("pipe_field", {"pipe": "mcp.pipe"}, "named-pipe"),
]


RUNTIME_CASES: list[tuple[str, str, list[str], str]] = [
    ("docker_command", "docker", ["run", "mcp/redis"], "docker"),
    ("docker_exe", "docker.exe", ["run"], "docker"),
    ("docker_in_args", "cmd", ["/c", "docker run x"], "docker"),
    ("npx", "npx", ["-y", "pkg"], "node/npm"),
    ("npm", "npm.cmd", ["exec", "pkg"], "node/npm"),
    ("node", "node.exe", ["server.js"], "node/npm"),
    ("uvx", "uvx", ["pkg"], "uv/uvx"),
    ("uv", "uv.exe", ["run", "pkg"], "uv/uvx"),
    ("python", "python", ["server.py"], "python"),
    ("py_launcher", "py.exe", ["-m", "server"], "python"),
    ("bun", "bun", ["run", "server"], "bun"),
    ("deno", "deno.exe", ["run", "server.ts"], "deno"),
    ("cargo", "cargo", ["run"], "rust/cargo"),
    ("dotnet", "dotnet.exe", ["run"], ".NET"),
    ("java", "java.exe", ["-jar", "server.jar"], "java"),
    ("cmd", "cmd.exe", ["/c", "server.bat"], "shell wrapper"),
    ("powershell", "powershell", ["-File", "server.ps1"], "shell wrapper"),
    ("pwsh", "pwsh.exe", ["-File", "server.ps1"], "shell wrapper"),
    ("unknown", "custom-mcp", ["serve"], "custom-mcp"),
]


NORMALIZE_CASES: list[tuple[str, dict[str, Any], dict[str, Any]]] = [
    ("string_args", {"command": "npx", "args": "-y pkg"}, {"args": ["-y pkg"], "transport": "stdio"}),
    ("list_args_stringified", {"command": "python", "args": ["-m", 42]}, {"args": ["-m", "42"]}),
    ("env_stringified", {"command": "python", "env": {"PORT": 6379, "TOKEN": None}}, {"env": {"PORT": "6379"}}),
    ("cwd_trimmed", {"command": "python", "cwd": "  C:/Work  "}, {"cwd": "C:/Work"}),
    ("endpoint_to_url", {"endpoint": "https://example/mcp"}, {"url": "https://example/mcp"}),
    ("sse_url", {"sseUrl": "https://example/sse"}, {"url": "https://example/sse", "transport": "sse"}),
    ("sse_url_snake", {"sse_url": "https://example/sse"}, {"url": "https://example/sse", "transport": "sse"}),
    ("streamable_url", {"streamableHttpUrl": "https://example/mcp"}, {"transport": "streamable-http"}),
    ("streamable_url_snake", {"streamable_http_url": "https://example/mcp"}, {"transport": "streamable-http"}),
    ("ws_url", {"wsUrl": "wss://example/ws"}, {"transport": "websocket"}),
    ("ws_url_snake", {"ws_url": "wss://example/ws"}, {"transport": "websocket"}),
    ("websocket_url", {"websocketUrl": "wss://example/ws"}, {"transport": "websocket"}),
    ("web_socket_url", {"webSocketUrl": "wss://example/ws"}, {"transport": "websocket"}),
    ("host_port_url", {"host": "localhost", "port": 1234}, {"url": "tcp://localhost:1234", "transport": "tcp"}),
    ("socket_path_url", {"socketPath": "/tmp/x.sock"}, {"url": "/tmp/x.sock", "transport": "named-pipe"}),
    ("named_pipe_url", {"namedPipe": "mcp.pipe"}, {"url": "mcp.pipe", "transport": "named-pipe"}),
    ("pipe_url", {"pipe": "mcp.pipe"}, {"url": "mcp.pipe", "transport": "named-pipe"}),
    ("preserve_extra_fields", {"command": "docker", "alwaysAllow": ["x"]}, {"alwaysAllow": ["x"]}),
    ("reject_empty", {"args": []}, {"reject": True}),
]


SECRET_CASES: list[tuple[str, dict[str, Any], list[str]]] = [
    ("env_api_key_empty", {"env": {"API_KEY": ""}}, ["API_KEY"]),
    ("env_token_your", {"env": {"TOKEN": "<REDACTED>"}}, ["TOKEN"]),
    ("env_secret_changeme", {"env": {"CLIENT_SECRET": "<REDACTED>"}}, ["CLIENT_SECRET"]),
    ("env_password_placeholder", {"env": {"PASSWORD": "<REDACTED>"}}, ["PASSWORD"]),
    ("env_auth_replace_me", {"env": {"AUTH_HEADER": "replace_me"}}, ["AUTH_HEADER"]),
    ("env_bearer_dollar", {"env": {"BEARER": "<REDACTED>"}}, ["BEARER"]),
    ("env_non_secret_ignored", {"env": {"PORT": "6379"}}, []),
    ("env_secret_real_value", {"env": {"TOKEN": "<REDACTED>"}}, []),
    ("arg_api_key", {"args": ["--api_key=TOKEN_HERE"]}, ["args[0]"]),
    ("arg_apikey", {"args": ["--apikey=api_key_here"]}, ["args[0]"]),
    ("arg_token", {"args": ["--token=xxx"]}, ["args[0]"]),
    ("arg_secret", {"args": ["--secret=<value>"]}, ["args[0]"]),
    ("arg_password", {"args": ["--password=TODO"]}, ["args[0]"]),
    ("arg_normal_ignored", {"args": ["--port=6379"]}, []),
    ("env_mixed", {"env": {"API_TOKEN": "token_here", "HOST": "localhost"}}, ["API_TOKEN"]),
    ("arg_mixed", {"args": ["--host=localhost", "--password=replace_me"]}, ["args[1]"]),
]


SCHEMA_CASES: list[tuple[str, dict[str, Any], dict[str, Any]]] = [
    ("string_required", {"type": "object", "properties": {"value": {"type": "string"}}, "required": ["value"]}, {"value": "hello"}),
    ("integer_required", {"type": "object", "properties": {"value": {"type": "integer"}}, "required": ["value"]}, {"value": 7}),
    ("number_required", {"type": "object", "properties": {"value": {"type": "number"}}, "required": ["value"]}, {"value": 1.5}),
    ("boolean_required", {"type": "object", "properties": {"value": {"type": "boolean"}}, "required": ["value"]}, {"value": True}),
    ("array_required", {"type": "object", "properties": {"value": {"type": "array"}}, "required": ["value"]}, {"value": ["a"]}),
    ("object_required", {"type": "object", "properties": {"value": {"type": "object"}}, "required": ["value"]}, {"value": {"a": 1}}),
    ("type_array", {"type": "object", "properties": {"value": {"type": ["integer", "string"]}}, "required": ["value"]}, {"value": 8}),
    ("anyof", {"type": "object", "properties": {"value": {"anyOf": [{"type": "integer"}, {"type": "string"}]}}, "required": ["value"]}, {"value": "8"}),
    ("oneof", {"type": "object", "properties": {"value": {"oneOf": [{"type": "boolean"}, {"type": "string"}]}}, "required": ["value"]}, {"value": False}),
    ("allof", {"type": "object", "properties": {"value": {"allOf": [{"type": "string"}]}}, "required": ["value"]}, {"value": "x"}),
    ("const", {"type": "object", "properties": {"value": {"const": "fixed"}}, "required": ["value"]}, {"value": "fixed"}),
    ("enum", {"type": "object", "properties": {"value": {"enum": ["a", "b"]}}, "required": ["value"]}, {"value": "a"}),
    ("optional_empty", {"type": "object", "properties": {"value": {"type": "string"}}}, {}),
]


STATIC_EXPECTATIONS: list[tuple[str, tuple[str, ...], tuple[str, ...]]] = [
    ("agent/templates/agent/agent_page.html", ("step-by-step-enabled", "Step-by-Step"), ()),
    ("agent/static/agent/js/agent_page_state.js", ("STEP_BY_STEP_STORAGE_KEY", "isStepByStepEnabled", "applyStoredStepByStepState"), ()),
    ("agent/static/agent/js/agent_page_init.js", ("step_by_step_enabled", "applyStoredStepByStepState", "stepByStepCheckbox"), ()),
    ("agent/static/agent/js/external_mcps_dialog.js", ("replace(/^\\uFEFF/", "mcpServers", "streamableHttpUrl"), ()),
    ("agent/static/agent/js/agent_page_chat.js", ("mcp doctor", "server_key", "source_url"), ()),
    ("agent/static/agent/js/acp-agent-connectors.js", ("updateMcpDoctorConnection", "update_mcp_doctor_connection"), ()),
    ("agent/static/agent/js/acp-canvas-core.js", ("mcp-doctor", "mcpdoctor-agent", "updateMcpDoctorConnection"), ()),
    ("agent/static/agent/js/acp-canvas-undo.js", ("mcp doctor", "updateMcpDoctorConnection"), ()),
    ("agent/static/agent/js/acp-file-io.js", ("mcp-doctor", "updateMcpDoctorConnection"), ()),
    ("agent/static/agent/css/agentic_control_panel.css", ("mcpdoctor-agent", "#0F3D3E", "#E0A83A"), ()),
    ("agent/agents/mcp_doctor/config.yaml", ("server_key", "catalog_path", "target_agents"), ()),
    ("agent/agents/mcp_doctor/mcp_doctor.py", ("INI_SECTION_MCP_DOCTOR", "CONFIG_PATH", r"C:\Tlamatini\external_mcps.json"), ("from agent",)),
    ("agent/chat_agent_registry.py", ("chat_agent_mcp_doctor", "Chat-Agent-MCP-Doctor", "MCP Doctor"), ()),
    ("agent/migrations/0141_add_mcp_doctor.py", ("agentDescription='MCP Doctor'", "0140_add_esphomer_demo_prompts"), ()),
    ("agent/migrations/0142_add_chat_agent_mcp_doctor_tool.py", ("Chat-Agent-MCP-Doctor", "0141_add_mcp_doctor"), ()),
    ("agent/migrations/0143_add_mcp_doctor_demo_prompt.py", ("(81, MCP_DOCTOR_DEMO)", "chat_agent_mcp_doctor", "Multi-Turn"), ()),
    ("agent/agents/flowcreator/agentic_skill.md", ("MCP Doctor", "mcp_doctor_<n>", "External MCP"), ()),
    ("agent/agents/flowhypervisor/monitoring-prompt.pmt", ("MCP Doctor", "INI_SECTION_MCP_DOCTOR", "MCP DOCTOR AGENT STARTED"), ()),
    ("agents_descriptions.md", ("MCP Doctor", "INI_SECTION_MCP_DOCTOR", "READY-gated"), ()),
    ("docs/external_mcp_bulletproof_architecture.md", ("eight supervisor tools", "external_mcp_wait", "`streamable-http`: implemented live connector", "`websocket`: implemented live connector"), ("`streamable-http`: detected and diagnosed; adapter still future", "`websocket`: detected and diagnosed; adapter still future")),
    ("Tlamatini/agent/Tlamatini.md", ("external_mcps.json", "eight always-on tools", "external_mcp_wait"), ("five always-on tools",)),
]


class ExternalMcpCatalogTests(SimpleTestCase):
    def test_load_catalog_accepts_utf8_bom(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "external_mcps.json")
            with open(path, "w", encoding="utf-8-sig") as handle:
                json.dump({"mcpServers": {"Redis": {"command": "docker"}}, "active": ["Redis"]}, handle)
            with patch.object(em, "catalog_path", return_value=path):
                data = em.load_catalog()
        self.assertEqual(data["active"], ["Redis"])
        self.assertIn("Redis", data["mcpServers"])

    def test_import_servers_accepts_full_mcpservers_object(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "external_mcps.json")
            with patch.object(em, "catalog_path", return_value=path):
                result = em.import_servers({"mcpServers": {"Redis": {"command": "docker", "args": ["run"]}}})
                data = em.load_catalog()
        self.assertTrue(result["ok"])
        self.assertIn("Redis", data["mcpServers"])

    def test_import_servers_wraps_single_server_object(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "external_mcps.json")
            with patch.object(em, "catalog_path", return_value=path):
                result = em.import_servers({"name": "Single Server", "command": "npx", "args": ["pkg"]})
                data = em.load_catalog()
        self.assertTrue(result["ok"])
        self.assertIn("Single_Server", data["mcpServers"])

    def test_doctor_tool_is_bound_in_supervisor_tools(self):
        names = {tool.name for tool in em._build_supervisor_tools()}
        self.assertIn("external_mcp_doctor", names)
        self.assertIn("external_mcp_list_tools", names)
        self.assertIn("external_mcp_call", names)

    def test_external_mcp_tool_name_fallback_knows_all_supervisor_tools(self):
        for name in (
            "external_mcp_status",
            "external_mcp_reconnect",
            "external_mcp_doctor",
            "external_mcp_list_tools",
            "external_mcp_call",
        ):
            self.assertTrue(_is_external_mcp_tool_name(name))

    def test_planner_forces_doctor_for_mcp_requests(self):
        tools = [type("Tool", (), {"name": name})() for name in (
            "external_mcp_status",
            "external_mcp_reconnect",
            "external_mcp_doctor",
            "external_mcp_list_tools",
            "external_mcp_call",
        )]
        forced = _external_mcp_force_names("diagnose a new mcp.so redis mcp", tools)
        self.assertIn("external_mcp_doctor", forced)
        self.assertIn("external_mcp_list_tools", forced)

    def test_step_by_step_prompt_includes_mcp_doctor(self):
        prompt = _build_system_prompt("base", [], step_by_step_enabled=True)
        self.assertIn("STEP-BY-STEP MODE", prompt)
        self.assertIn("external_mcp_doctor", prompt)
        self.assertIn("wait for the user's READY", prompt)

    def test_wrapped_agent_registry_exposes_mcp_doctor(self):
        spec = WRAPPED_CHAT_AGENT_BY_TOOL_NAME["chat_agent_mcp_doctor"]
        self.assertEqual(spec.display_name, "MCP Doctor")
        self.assertEqual(spec.template_dir, "mcp_doctor")

    def test_agent_contract_discovers_mcp_doctor_template(self):
        contract = get_agent_contract("mcp doctor")
        self.assertEqual(contract.agent_type, "mcp_doctor")
        self.assertIn("target_agents", contract.connection_fields)

    def test_parametrizer_fields_include_mcp_doctor(self):
        fields = get_parametrizer_source_fields()
        self.assertIn("mcp_doctor", fields)
        self.assertIn("response_body", fields["mcp_doctor"])

    def test_mcp_doctor_config_is_valid_yaml(self):
        config_path = _AGENT_DIR / "agents" / "mcp_doctor" / "config.yaml"
        config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        self.assertEqual(config["mode"], "diagnose")
        self.assertEqual(config["target_agents"], [])

    def test_mcp_doctor_diagnose_reads_temp_catalog(self):
        with tempfile.TemporaryDirectory() as tmp:
            catalog = os.path.join(tmp, "external_mcps.json")
            with open(catalog, "w", encoding="utf-8") as handle:
                json.dump({"mcpServers": {"Redis": {"command": "docker", "args": ["run"]}}, "active": []}, handle)
            result = MCP_DOCTOR.diagnose({"catalog_path": catalog, "server_key": "Redis"})
        self.assertEqual(result["server_key"], "Redis")
        self.assertEqual(result["transport"], "stdio")
        self.assertIn("Catalog path:", result["body"])


class ExternalMcpTransportTests(SimpleTestCase):
    pass


def _add_transport_test(idx: int, label: str, spec: dict[str, Any], expected: str) -> None:
    def test(self):
        self.assertEqual(em._server_transport(dict(spec)), expected)
        self.assertEqual(MCP_DOCTOR._server_transport(dict(spec)), expected)

    setattr(ExternalMcpTransportTests, _method_name("transport", idx, label), test)


for _idx, (_label, _spec, _expected) in enumerate(TRANSPORT_CASES, 1):
    _add_transport_test(_idx, _label, _spec, _expected)


class ExternalMcpRuntimeInferenceTests(SimpleTestCase):
    pass


def _add_runtime_test(idx: int, label: str, command: str, args: list[str], expected: str) -> None:
    def test(self):
        self.assertEqual(em._infer_runtime(command, args), expected)
        self.assertEqual(MCP_DOCTOR._infer_runtime(command, args), expected)

    setattr(ExternalMcpRuntimeInferenceTests, _method_name("runtime", idx, label), test)


for _idx, (_label, _command, _args, _expected) in enumerate(RUNTIME_CASES, 1):
    _add_runtime_test(_idx, _label, _command, _args, _expected)


class ExternalMcpNormalizationTests(SimpleTestCase):
    pass


def _add_normalize_test(idx: int, label: str, spec: dict[str, Any], expected: dict[str, Any]) -> None:
    def test(self):
        normalized = em._normalize_imported_server_spec(label, dict(spec))
        if expected.get("reject"):
            self.assertIsNone(normalized)
            return
        self.assertIsNotNone(normalized)
        assert normalized is not None
        for key, value in expected.items():
            self.assertEqual(normalized.get(key), value)

    setattr(ExternalMcpNormalizationTests, _method_name("normalize", idx, label), test)


for _idx, (_label, _spec, _expected) in enumerate(NORMALIZE_CASES, 1):
    _add_normalize_test(_idx, _label, _spec, _expected)


class ExternalMcpSecretDetectionTests(SimpleTestCase):
    pass


def _add_secret_test(idx: int, label: str, spec: dict[str, Any], expected: list[str]) -> None:
    def test(self):
        self.assertEqual(em._missing_secret_hints(dict(spec)), expected)
        self.assertEqual(MCP_DOCTOR._missing_secret_hints(dict(spec)), expected)

    setattr(ExternalMcpSecretDetectionTests, _method_name("secret", idx, label), test)


for _idx, (_label, _spec, _expected) in enumerate(SECRET_CASES, 1):
    _add_secret_test(_idx, _label, _spec, _expected)


class ExternalMcpSchemaTests(SimpleTestCase):
    pass


def _add_schema_test(idx: int, label: str, schema: dict[str, Any], values: dict[str, Any]) -> None:
    def test(self):
        model = em._args_model_from_schema(f"TestModel_{idx}_{label}", schema)
        instance = model(**values)
        for key, value in values.items():
            self.assertEqual(getattr(instance, key), value)
        if "value" not in values:
            self.assertIsNone(getattr(instance, "value"))

    setattr(ExternalMcpSchemaTests, _method_name("schema", idx, label), test)


for _idx, (_label, _schema, _values) in enumerate(SCHEMA_CASES, 1):
    _add_schema_test(_idx, _label, _schema, _values)


class ExternalMcpStaticIntegrationTests(SimpleTestCase):
    pass


def _add_static_test(idx: int, path: str, required: tuple[str, ...], forbidden: tuple[str, ...]) -> None:
    def test(self):
        text = _read_repo_text(path)
        for needle in required:
            self.assertIn(needle, text, f"{needle!r} missing from {path}")
        for needle in forbidden:
            self.assertNotIn(needle, text, f"{needle!r} should not appear in {path}")

    label = path.replace("/", "_").replace("\\", "_")
    setattr(ExternalMcpStaticIntegrationTests, _method_name("static", idx, label), test)


for _idx, (_path, _required, _forbidden) in enumerate(STATIC_EXPECTATIONS, 1):
    _add_static_test(_idx, _path, _required, _forbidden)


class ExternalMcpToolResultFormatTests(SimpleTestCase):
    """`_format_mcp_tool_result` must surface `structuredContent` (Angela, 2026-07-15).

    THE BUG: octocode (and any structured-output MCP server) returns its real data
    in `structuredContent` and puts only a short POINTER in the text `content`.
    The old reader took only the text pointer, so the LLM never got the data and
    re-called the tool until the repetition-breaker force-stopped the run. These
    tests pin that the formatter now includes the structured data.
    """

    def test_octocode_pointer_plus_structuredContent_is_surfaced(self):
        # Exactly the shape octocode returned in Angela's live run.
        result = {
            "content": [{"type": "text",
                         "text": "structuredContent available · results=1. "
                                 "Read structuredContent for full data."}],
            "structuredContent": {"repos": [
                {"owner_repo": "openbci/OpenBCI_GUI", "stars": 4200, "description": "BCI GUI"},
            ]},
        }
        out = em._format_mcp_tool_result(result)
        # The ACTUAL data must be present now (this was missing before the fix).
        self.assertIn("OpenBCI_GUI", out)
        self.assertIn("4200", out)
        self.assertIn("structuredContent", out)

    def test_plain_text_result_unchanged(self):
        result = {"content": [{"type": "text", "text": "just a plain answer"}]}
        self.assertEqual(em._format_mcp_tool_result(result), "just a plain answer")

    def test_single_result_envelope_is_unwrapped(self):
        result = {"content": [], "structuredContent": {"result": {"ok": True, "n": 3}}}
        out = em._format_mcp_tool_result(result)
        self.assertIn('"ok": true', out)
        self.assertIn('"n": 3', out)
        self.assertNotIn('"result"', out)  # the sole {"result": ...} wrapper is stripped

    def test_isError_still_reported_as_error(self):
        result = {"isError": True, "content": [{"type": "text", "text": "boom"}]}
        self.assertEqual(em._format_mcp_tool_result(result), "Error: boom")

    def test_error_with_only_structuredContent_still_surfaces_it(self):
        result = {"isError": True, "content": [], "structuredContent": {"reason": "rate_limited"}}
        out = em._format_mcp_tool_result(result)
        self.assertTrue(out.startswith("Error:"))
        self.assertIn("rate_limited", out)

    def test_huge_structuredContent_is_capped(self):
        big = {"blob": "x" * 100000}
        out = em._format_mcp_tool_result({"content": [], "structuredContent": big}, max_chars=5000)
        self.assertIn("truncated", out)
        self.assertLess(len(out), 6000)

    def test_non_dict_result_is_stringified_safely(self):
        self.assertEqual(em._format_mcp_tool_result("raw string"), "raw string")
