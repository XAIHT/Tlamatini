# Tlamatini — Created by Angela López Mendoza · @angelahack1
# Tlamatini Author Banner — do not remove
"""Exercise the real selective Ask-Execs gate, not a hand-emitted dialog.

Only model selection and tool effects are deterministic test boundaries. The
production executor loop, permission classifier, broker and tool dispatch run.
The approved command boundary writes one marker inside application-owned test
storage; no shell, network monitor or wrapped-agent process is launched here.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
import uuid
from unittest.mock import patch

from django.test import SimpleTestCase
from langchain_core.messages import AIMessage
from langchain_core.tools import StructuredTool

from .exec_permission import ExecPermissionBroker, register_broker, unregister_broker
from .mcp_agent import MultiTurnToolAgentExecutor


class ScriptedToolSelection:
    """Two model turns; never contacts a model provider."""

    def __init__(self, calls):
        self.calls = calls
        self.turns = 0

    def bind_tools(self, _tools):
        return self

    def invoke(self, _messages, *args, **kwargs):
        self.turns += 1
        if self.turns == 1:
            return AIMessage(content="", tool_calls=[
                {"id": f"qa-{index}", "name": name, "args": arguments}
                for index, (name, arguments) in enumerate(self.calls)
            ])
        return AIMessage(content="QA dispatch completed.")


class RemoteAskExecsDispatchTests(SimpleTestCase):
    def setUp(self):
        root = Path(os.environ.get("TLAMATINI_TEST_SCRATCH") or
                    Path(__file__).resolve().parents[2] / "artifacts" / "ask-execs-tests")
        profile = Path(os.environ.get("USERPROFILE", "C:/Users"))
        if root.resolve().is_relative_to(profile.resolve()):
            raise RuntimeError("Test scratch must be outside Windows user profiles")
        root.mkdir(parents=True, exist_ok=True)
        self.storage = tempfile.TemporaryDirectory(prefix="dispatch-", dir=root)
        self.addCleanup(self.storage.cleanup)
        self.marker = Path(self.storage.name) / "approved-tool.txt"
        self.owner = "qa-ask-execs-" + uuid.uuid4().hex
        self.requests = []
        self.executions = []
        self.reaper = patch.object(MultiTurnToolAgentExecutor, "_reap_after_tool")
        self.reaper.start()
        self.addCleanup(self.reaper.stop)

    def exercise(self, names, *, decision="deny", enabled=True, closed=False, emit_fails=False, aliases=None):
        def emit(detail):
            self.requests.append(detail)
            self.assertFalse(self.marker.exists(), "Tool executed before permission")
            self.assertEqual(self.executions, [], "Tool executed before permission")
            if emit_fails:
                raise RuntimeError("QA transport closed")
            self.assertTrue(broker.resolve(detail["request_id"], decision))

        broker = ExecPermissionBroker(emit, run_user_id=self.owner)
        register_broker(self.owner, broker)
        self.addCleanup(unregister_broker, self.owner, broker)
        if closed:
            broker.close()

        tools = []
        def make_effect(name):
            def effect(command: str = "ver") -> str:
                if command != "ver":
                    raise ValueError("Only the fixed QA command is accepted")
                self.executions.append(name)
                self.marker.write_text("QA bounded dispatch reached", encoding="utf-8")
                return json.dumps({"status": "completed", "fixture": True})
            return effect

        for name in dict.fromkeys(names):
            effect = make_effect(name)
            tools.append(StructuredTool.from_function(effect, name=name, description="Inert QA tool boundary"))
        model = ScriptedToolSelection([(name, {"command": "ver"}) for name in (aliases or names)])
        executor = MultiTurnToolAgentExecutor(model, "QA permission dispatch", tools, max_iterations=3)
        result = executor.invoke({"input": "QA permission dispatch", "ask_execs_enabled": enabled,
                                  "ask_execs_user_id": self.owner, "exec_report_enabled": True})
        return executor, model, result

    def test_direct_command_denied_before_dispatch(self):
        executor, model, _ = self.exercise(["execute_command"])
        self.assertEqual(len(self.requests), 1)
        self.assertEqual(self.requests[0]["tool_name"], "execute_command")
        self.assertIsNotNone(executor._exec_denied)
        self.assertEqual(model.turns, 1)
        self.assertEqual(self.executions, [])
        self.assertFalse(self.marker.exists())

    def test_direct_command_proceeds_once_after_resolution(self):
        executor, _, _ = self.exercise(["execute_command"], decision="proceed")
        self.assertEqual(len(self.requests), 1)
        self.assertIsNone(executor._exec_denied)
        self.assertEqual(self.executions, ["execute_command"])
        self.assertTrue(self.marker.exists())

    def test_wrapped_executer_denied_before_dispatch(self):
        executor, _, _ = self.exercise(["chat_agent_executer"])
        self.assertEqual(len(self.requests), 1)
        self.assertIsNotNone(executor._exec_denied)
        self.assertEqual(self.executions, [])
        self.assertFalse(self.marker.exists())

    def test_wrapped_executer_proceeds_once_after_resolution(self):
        self.exercise(["chat_agent_executer"], decision="proceed")
        self.assertEqual(len(self.requests), 1)
        self.assertEqual(self.executions, ["chat_agent_executer"])

    def test_direct_netstat_is_observational_and_does_not_ask(self):
        self.exercise(["execute_netstat"])
        self.assertEqual(self.requests, [])
        self.assertEqual(self.executions, ["execute_netstat"])

    def test_wrapped_netstat_is_observational_and_does_not_ask(self):
        self.exercise(["chat_agent_monitor_netstat"])
        self.assertEqual(self.requests, [])
        self.assertEqual(self.executions, ["chat_agent_monitor_netstat"])

    def test_disabled_ask_execs_retains_normal_command_dispatch(self):
        self.exercise(["execute_command"], enabled=False)
        self.assertEqual(self.requests, [])
        self.assertEqual(self.executions, ["execute_command"])

    def test_denial_stops_later_observational_tools_in_same_turn(self):
        self.exercise(["execute_command", "execute_netstat"])
        self.assertEqual(len(self.requests), 1)
        self.assertEqual(self.executions, [])

    def test_closed_registered_broker_denies_without_dispatch(self):
        executor, _, _ = self.exercise(["execute_command"], closed=True)
        self.assertIsNotNone(executor._exec_denied)
        self.assertEqual(self.requests, [])
        self.assertEqual(self.executions, [])

    def test_broken_permission_transport_denies_without_dispatch(self):
        executor, _, _ = self.exercise(["execute_command"], emit_fails=True)
        self.assertIsNotNone(executor._exec_denied)
        self.assertEqual(len(self.requests), 1)
        self.assertEqual(self.executions, [])

    def test_bare_executer_alias_cannot_bypass_permission(self):
        self.exercise(["chat_agent_executer"], aliases=["executer"])
        self.assertEqual(len(self.requests), 1)
        self.assertEqual(self.requests[0]["tool_name"], "chat_agent_executer")
        self.assertEqual(self.executions, [])

    def test_case_variant_direct_command_cannot_bypass_permission(self):
        self.exercise(["execute_command"], aliases=["Execute_Command"])
        self.assertEqual(len(self.requests), 1)
        self.assertEqual(self.requests[0]["tool_name"], "execute_command")
        self.assertEqual(self.executions, [])
