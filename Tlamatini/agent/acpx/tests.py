"""
Sanity tests for the ACPX runtime + Skill harness.

These tests are pure-python unit tests — they do NOT spawn real coding
agents. The end-to-end verification (acp_doctor against an installed
claude / cursor CLI) is the manual smoke-test gate documented in
docs/claude/acpx.md and ACPX.md.
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from unittest import TestCase

# Make `agent.*` importable when this file is run via pytest from the repo root.
HERE = Path(__file__).resolve()
PROJECT_ROOT = HERE.parents[2]   # .../Tlamatini
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from agent.acpx.config import (  # noqa: E402
    load_acpx_config,
)
from agent.acpx.permissions import (  # noqa: E402
    Action,
    PermissionGate,
    is_dangerous_config,
)
from agent.acpx.session_store import (  # noqa: E402
    AcpSessionRecord,
    FileSessionStore,
    make_session_id,
    now_epoch,
)
from agent.acpx.agent_registry import (  # noqa: E402
    DEFAULT_ACP_AGENTS,
    build_agent_registry,
)
from agent.skills.frontmatter import parse_skill_md, SkillParseError  # noqa: E402
from agent.skills.io_contract import (  # noqa: E402
    validate_inputs,
    validate_outputs,
)


class ConfigTests(TestCase):
    def test_load_default_when_no_acpx_block(self) -> None:
        cfg = load_acpx_config({})
        self.assertEqual(cfg.permission_mode, "approve-reads")
        self.assertEqual(cfg.non_interactive, "deny")
        self.assertFalse(cfg.plugin_tools_mcp_bridge)
        self.assertFalse(cfg.openclaw_tools_mcp_bridge)
        self.assertEqual(cfg.timeout_seconds, 120)
        self.assertEqual(cfg.mcp_servers, {})
        self.assertEqual(cfg.agents, {})

    def test_load_with_full_block(self) -> None:
        cfg = load_acpx_config({
            "acpx": {
                "cwd": "/tmp",
                "permissionMode": "deny-all",
                "nonInteractivePermissions": "fail",
                "timeoutSeconds": 60,
                "agents": {"claude": {"command": "/usr/local/bin/claude"}},
                "mcpServers": {
                    "files": {
                        "command": "python",
                        "args": ["-m", "files_mcp"],
                        "env": {"FOO": "1"},
                    }
                },
            }
        })
        self.assertEqual(cfg.permission_mode, "deny-all")
        self.assertEqual(cfg.non_interactive, "fail")
        self.assertEqual(cfg.timeout_seconds, 60)
        self.assertEqual(cfg.agents["claude"], "/usr/local/bin/claude")
        self.assertIn("files", cfg.mcp_servers)
        self.assertEqual(cfg.mcp_servers["files"].command, "python")
        self.assertEqual(cfg.mcp_servers["files"].args, ["-m", "files_mcp"])

    def test_invalid_permission_mode_falls_back_to_default(self) -> None:
        cfg = load_acpx_config({"acpx": {"permissionMode": "yolo"}})
        self.assertEqual(cfg.permission_mode, "approve-reads")

    def test_dangerous_config_flag(self) -> None:
        self.assertTrue(is_dangerous_config("approve-all"))
        self.assertFalse(is_dangerous_config("approve-reads"))
        self.assertFalse(is_dangerous_config("deny-all"))


class PermissionGateTests(TestCase):
    def test_deny_all_blocks_everything(self) -> None:
        gate = PermissionGate("deny-all", "deny")
        for kind in ("fs.read", "fs.write", "shell", "net", "db", "tool"):
            d = gate.decide(Action(kind=kind, detail={}), interactive=True)
            self.assertFalse(d.allowed, kind)

    def test_approve_all_allows_everything(self) -> None:
        gate = PermissionGate("approve-all", "deny")
        for kind in ("fs.read", "fs.write", "shell", "net", "db", "tool"):
            d = gate.decide(Action(kind=kind, detail={}), interactive=False)
            self.assertTrue(d.allowed, kind)

    def test_approve_reads_passes_reads_holds_writes(self) -> None:
        gate = PermissionGate("approve-reads", "deny")
        # Read auto-approved
        self.assertTrue(gate.decide(Action("fs.read", {}), False).allowed)
        # Write needs prompt; non-interactive deny applies
        d = gate.decide(Action("fs.write", {}), interactive=False)
        self.assertFalse(d.allowed)
        # When interactive, the gate asks for a prompt
        d = gate.decide(Action("fs.write", {}), interactive=True)
        self.assertTrue(d.allowed)
        self.assertTrue(d.needs_prompt)

    def test_non_interactive_fail_policy(self) -> None:
        gate = PermissionGate("approve-reads", "fail")
        d = gate.decide(Action("shell", {}), interactive=False)
        self.assertFalse(d.allowed)
        self.assertIn("fail", d.reason)


class SessionStoreTests(TestCase):
    def test_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = FileSessionStore(tmp)
            sid = make_session_id()
            rec = AcpSessionRecord(
                session_id=sid, name="t", agent_id="claude",
                cwd=tmp, state_path=str(Path(tmp) / f"{sid}.json"),
                transcript_path=str(Path(tmp) / f"{sid}.t.ndjson"),
                pid=None, created_at=now_epoch(), last_active_at=now_epoch(),
            )
            store.save(rec)
            loaded = store.load(sid)
            self.assertIsNotNone(loaded)
            self.assertEqual(loaded.agent_id, "claude")

    def test_mark_fresh_ignores_stale_record(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = FileSessionStore(tmp)
            sid = make_session_id()
            rec = AcpSessionRecord(
                session_id=sid, name="t", agent_id="claude",
                cwd=tmp, state_path=str(Path(tmp) / f"{sid}.json"),
                transcript_path="", pid=None,
                created_at=now_epoch(), last_active_at=now_epoch(),
            )
            store.save(rec)
            # After marking fresh, the *next* load returns None even though
            # the record is on disk. Once we save again, the marker drops.
            store.mark_fresh(sid)
            self.assertIsNone(store.load(sid))
            store.save(rec)
            self.assertIsNotNone(store.load(sid))

    def test_list_all(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = FileSessionStore(tmp)
            for i in range(3):
                rec = AcpSessionRecord(
                    session_id=make_session_id(),
                    name=f"t{i}", agent_id="cursor",
                    cwd=tmp, state_path="",
                    transcript_path="", pid=None,
                    created_at=now_epoch(), last_active_at=now_epoch(),
                )
                store.save(rec)
            self.assertEqual(len(store.list_all()), 3)


class AgentRegistryTests(TestCase):
    def test_default_registry_has_known_ids(self) -> None:
        registry = build_agent_registry()
        for agent_id in ("claude", "cursor", "codex", "qwen", "gemini"):
            self.assertIn(agent_id, registry)

    def test_overrides_replace_command_only(self) -> None:
        registry = build_agent_registry({"claude": "/usr/local/bin/claude"})
        self.assertEqual(registry["claude"].command, "/usr/local/bin/claude")
        # Args/env preserved from default
        self.assertEqual(registry["claude"].args,
                         DEFAULT_ACP_AGENTS["claude"].args)

    def test_overrides_can_introduce_new_agent(self) -> None:
        registry = build_agent_registry({"my-custom": "/opt/my-agent"})
        self.assertIn("my-custom", registry)
        self.assertEqual(registry["my-custom"].command, "/opt/my-agent")


class FrontmatterTests(TestCase):
    def test_parse_minimal_skill(self) -> None:
        text = (
            "---\n"
            "name: t\n"
            "description: x\n"
            "---\n"
            "# Body\nhi\n"
        )
        fm, body = parse_skill_md(text)
        self.assertEqual(fm.name, "t")
        self.assertEqual(fm.description, "x")
        self.assertEqual(fm.runtime, "in-process")
        self.assertIn("# Body", body)

    def test_runtime_acpx_requires_agent(self) -> None:
        text = (
            "---\n"
            "name: t\n"
            "description: x\n"
            "metadata:\n"
            "  tlamatini:\n"
            "    runtime: acpx\n"
            "---\n"
            "body\n"
        )
        with self.assertRaises(SkillParseError):
            parse_skill_md(text)

    def test_runtime_acpx_with_agent_parses(self) -> None:
        text = (
            "---\n"
            "name: t\n"
            "description: x\n"
            "metadata:\n"
            "  tlamatini:\n"
            "    runtime: acpx\n"
            "    acpx_agent: claude\n"
            "---\n"
            "body\n"
        )
        fm, _ = parse_skill_md(text)
        self.assertEqual(fm.runtime, "acpx")
        self.assertEqual(fm.acpx_agent, "claude")

    def test_missing_frontmatter_raises(self) -> None:
        with self.assertRaises(SkillParseError):
            parse_skill_md("just body")


class IoContractTests(TestCase):
    def test_validate_inputs_required_missing(self) -> None:
        decls = [{"name": "x", "type": "string", "required": True}]
        v = validate_inputs(decls, {})
        self.assertFalse(v.ok)
        self.assertIn("x: required input missing", v.errors[0])

    def test_validate_inputs_default_applied(self) -> None:
        decls = [{"name": "x", "type": "string", "default": "hi"}]
        v = validate_inputs(decls, {})
        self.assertTrue(v.ok)
        self.assertEqual(v.coerced["x"], "hi")

    def test_validate_inputs_enum(self) -> None:
        decls = [{"name": "k", "type": "enum", "values": ["a", "b"],
                  "required": True}]
        self.assertTrue(validate_inputs(decls, {"k": "a"}).ok)
        self.assertFalse(validate_inputs(decls, {"k": "z"}).ok)

    def test_validate_outputs_required(self) -> None:
        decls = [{"name": "answer", "type": "string", "required": True}]
        self.assertTrue(validate_outputs(decls, {"answer": "ok"}).ok)
        self.assertFalse(validate_outputs(decls, {}).ok)


class HelloWorldSkillSmokeTest(TestCase):
    """The hello-world skill must always be discoverable and parseable."""

    def test_hello_world_loads(self) -> None:
        # Avoid Django-import cycles by reading the file directly.
        path = (PROJECT_ROOT / "agent" / "skills_pkg" / "hello_world"
                / "SKILL.md")
        self.assertTrue(path.exists(), f"missing: {path}")
        fm, body = parse_skill_md(path.read_text(encoding="utf-8"),
                                  source_label=str(path))
        self.assertEqual(fm.name, "hello-world")
        self.assertEqual(fm.runtime, "in-process")
        self.assertIn("Hello World", body)
