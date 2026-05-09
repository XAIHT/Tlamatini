import csv
import tempfile
from pathlib import Path
from unittest.mock import patch

from django.test import SimpleTestCase

from agent.services.agent_contracts import get_agent_contract, redact_config_for_export
from agent.services.agent_paths import get_agents_root, normalize_agent_type
from agent.services.flow_compiler import compile_flow_spec
from agent.services.flow_spec import FlowConnection, FlowNode, FlowSpec, normalize_flow_payload


class FlowContractTests(SimpleTestCase):
    def test_source_mode_agents_root_uses_agent_package(self):
        root = get_agents_root()
        self.assertTrue(str(root).replace("\\", "/").endswith("Tlamatini/agent/agents"))
        self.assertTrue((root / "starter" / "config.yaml").exists())

    def test_alias_normalization_keeps_gateway_names_compatible(self):
        self.assertEqual(normalize_agent_type("Gateway Relayer"), "gateway_relayer")
        self.assertEqual(get_agent_contract("gateway-relayer").agent_type, "gateway_relayer")
        self.assertEqual(get_agent_contract("node manager").agent_type, "node_manager")

    def test_dry_run_compiles_canvas_connections_and_ender_kill_list(self):
        spec = FlowSpec(
            nodes=[
                FlowNode(id="starter-1", text="Starter"),
                FlowNode(id="executer-1", text="Executer", config={"script": "echo hi"}),
                FlowNode(id="ender-1", text="Ender"),
            ],
            connections=[
                FlowConnection(source_id="starter-1", target_id="executer-1"),
                FlowConnection(source_id="executer-1", target_id="ender-1"),
            ],
        )

        result = compile_flow_spec(spec, write=False)
        by_name = {agent["folder_name"]: agent for agent in result["agents"]}

        self.assertEqual(by_name["starter_1"]["config"]["target_agents"], ["executer_1"])
        self.assertEqual(by_name["executer_1"]["config"]["source_agents"], ["starter_1"])
        self.assertEqual(by_name["executer_1"]["config"]["target_agents"], ["ender_1"])
        self.assertEqual(by_name["ender_1"]["config"]["source_agents"], ["executer_1"])
        self.assertEqual(by_name["ender_1"]["config"]["target_agents"], ["executer_1", "starter_1"])

    def test_parametrizer_mappings_are_written_as_csv_artifact(self):
        spec = FlowSpec(
            nodes=[
                FlowNode(id="apirer-1", text="APIrer"),
                FlowNode(
                    id="parametrizer-1",
                    text="Parametrizer",
                    config={
                        "_parametrizer_mappings": [
                            {
                                "source_field": "response_body",
                                "target_param": "script",
                                "target_marker": "content",
                            }
                        ]
                    },
                ),
                FlowNode(id="executer-1", text="Executer"),
            ],
            connections=[
                FlowConnection(source_id="apirer-1", target_id="parametrizer-1"),
                FlowConnection(source_id="parametrizer-1", target_id="executer-1"),
            ],
        )

        with tempfile.TemporaryDirectory() as tmp:
            pool_path = Path(tmp) / "pools" / "session"
            with patch("agent.services.flow_compiler.get_session_pool_path", return_value=pool_path):
                result = compile_flow_spec(spec, write=True)

            self.assertTrue(result["success"])
            scheme_path = pool_path / "parametrizer_1" / "interconnection-scheme.csv"
            self.assertTrue(scheme_path.exists())
            with scheme_path.open("r", encoding="utf-8") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(rows[0]["source_field"], "response_body")
            self.assertEqual(rows[0]["target_param"], "script")
            self.assertEqual(rows[0]["target_marker"], "content")

    def test_monitor_log_pool_logfile_path_is_rewritten(self):
        spec = FlowSpec(
            nodes=[
                FlowNode(id="starter-1", text="Starter"),
                FlowNode(id="monitor-log-1", text="Monitor Log"),
            ],
            connections=[
                FlowConnection(source_id="starter-1", target_id="monitor-log-1"),
            ],
        )

        result = compile_flow_spec(spec, write=False)
        by_name = {agent["folder_name"]: agent for agent in result["agents"]}
        self.assertEqual(
            by_name["monitor_log_1"]["config"]["target"]["logfile_path"],
            "monitor_log_1.log",
        )

    def test_legacy_flow_payload_normalizes_without_absolute_paths(self):
        spec = normalize_flow_payload(
            {
                "nodes": [
                    {"text": "Starter", "left": "1px", "top": "2px", "configData": {}},
                    {"text": "Executer", "left": "3px", "top": "4px", "configData": {"script": "echo ok"}},
                ],
                "connections": [{"sourceIndex": 0, "targetIndex": 1}],
            }
        )

        self.assertEqual(spec.nodes[0].id, "starter-1")
        self.assertEqual(spec.nodes[1].pool_name, "executer_1")
        self.assertEqual(spec.connections[0].source_id, "starter-1")
        self.assertEqual(spec.connections[0].target_id, "executer-1")

    def test_teletlamatini_export_redacts_known_secrets(self):
        config = {
            "telegram": {"api_hash": "secret-hash", "bot_token": "secret-token"},
            "password": "remote-password",
            "tlamatini": {"password": "local-password", "username": "user"},
        }

        redacted = redact_config_for_export("teletlamatini", config)
        self.assertEqual(redacted["telegram"]["api_hash"], "__REDACTED__")
        self.assertEqual(redacted["telegram"]["bot_token"], "__REDACTED__")
        self.assertEqual(redacted["password"], "__REDACTED__")
        self.assertEqual(redacted["tlamatini"]["password"], "__REDACTED__")
        self.assertEqual(redacted["tlamatini"]["username"], "user")
