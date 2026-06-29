# ═══════════════════════════════════════════════════════════════════
#   ✦  T L A M A T I N I  ✦   —   "one who knows"
#
#   Crafted with heart by  Angela   ·   @angelahack1
#   Developer · Architect · Creator of Tlamatini
#
#   Every line of this file was written by Angela.
# ═══════════════════════════════════════════════════════════════════
#   Tlamatini Author Banner — do not remove (releases scrub the name automatically)
"""
Sanity tests for the ACPX runtime + Skill harness.

These tests are pure-python unit tests — they do NOT spawn real coding
agents. The end-to-end verification (acp_doctor against an installed
claude / cursor CLI) is the manual smoke-test gate documented in
docs/claude/acpx.md and ACPX.md.
"""
from __future__ import annotations

import json
import sys
import tempfile
import time
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch

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


# ── Section A: ACPX tool surface ──────────────────────────────────────
# These tests cover the expanded ACPX tool surface: per-event trimming,
# transcript reads, session status / listing, the relay helper, and the
# enriched acp_doctor envelope. They never spawn a real CLI; runtime
# behavior is exercised by inserting fake AcpSession objects directly
# into the runtime's in-memory _sessions dict.


from agent.acpx.runtime import (  # noqa: E402
    DEFAULT_MAX_EVENT_CHARS,
    extract_last_assistant_text,
    trim_event_payload,
    trim_events,
)
from agent.acpx import tools as acpx_tools  # noqa: E402
from agent.acpx.config import AcpxConfig  # noqa: E402
from agent.acpx.runtime import AcpxRuntime, AcpSession  # noqa: E402


def _make_runtime(state_dir: Path) -> AcpxRuntime:
    """Build an AcpxRuntime that doesn't read config.json from disk."""
    cfg = AcpxConfig(state_dir=str(state_dir),
                     cwd=str(state_dir),
                     timeout_seconds=5)
    return AcpxRuntime(config=cfg)


class _FakeProc:
    """Minimal subprocess.Popen stand-in for tests."""

    def __init__(self, alive: bool = True, pid: int = 4242):
        self._alive = alive
        self.pid = pid
        self.returncode = None if alive else 0

    def poll(self):
        return None if self._alive else 0

    def terminate(self):
        self._alive = False
        self.returncode = 0

    def wait(self, timeout=None):  # noqa: ARG002
        self._alive = False
        return 0

    def kill(self):
        self._alive = False
        self.returncode = -9


def _install_fake_session(runtime: AcpxRuntime, session_id: str,
                           agent_id: str = "claude",
                           transcript_text: str = "",
                           alive: bool = True) -> AcpSession:
    """Place a fake AcpSession into the runtime so transcript/list/kill
    paths can be exercised without spawning a real child."""
    from agent.acpx.session_store import AcpSessionRecord, now_epoch

    transcript_path = Path(runtime.config.state_dir) / f"{session_id}.transcript.ndjson"
    transcript_path.parent.mkdir(parents=True, exist_ok=True)
    transcript_path.write_text(transcript_text, encoding="utf-8")
    record = AcpSessionRecord(
        session_id=session_id,
        name=f"{agent_id}-{session_id[:6]}",
        agent_id=agent_id,
        cwd=runtime.config.cwd or str(runtime.config.state_dir),
        state_path=str(Path(runtime.config.state_dir) / f"{session_id}.json"),
        transcript_path=str(transcript_path),
        pid=4242,
        created_at=now_epoch(),
        last_active_at=now_epoch(),
    )
    runtime.session_store.save(record)
    spec = next(iter(runtime.agent_registry.values()))  # any spec works for tests
    sess = AcpSession(runtime=runtime, spec=spec,
                      cwd=Path(record.cwd), mode="session", record=record)
    sess.proc = _FakeProc(alive=alive)
    record.pid = sess.proc.pid
    runtime._sessions[session_id] = sess
    return sess


class EventTrimmingTests(TestCase):
    """Item 9 — trim oversized event payloads at the tool boundary."""

    def test_trim_event_payload_clips_each_known_key(self) -> None:
        big = "x" * 5000
        ev = {"event": "log", "text": big, "raw": big, "role": "assistant"}
        out = trim_event_payload(ev, max_event_chars=100)
        self.assertEqual(len(out["text"]), 100)
        self.assertEqual(len(out["raw"]), 100)
        self.assertTrue(out.get("_truncated"))
        # Envelope fields are preserved verbatim.
        self.assertEqual(out["event"], "log")
        self.assertEqual(out["role"], "assistant")

    def test_trim_event_payload_no_op_when_under_cap(self) -> None:
        ev = {"event": "log", "text": "short"}
        out = trim_event_payload(ev, max_event_chars=100)
        self.assertEqual(out, {"event": "log", "text": "short"})
        self.assertNotIn("_truncated", out)

    def test_trim_events_applies_to_each(self) -> None:
        events = [
            {"event": "log", "text": "a" * 200},
            {"event": "log", "text": "b" * 50},
            {"done": True, "_synthetic": "idle"},
        ]
        out = trim_events(events, max_event_chars=100)
        self.assertEqual(len(out[0]["text"]), 100)
        self.assertTrue(out[0]["_truncated"])
        self.assertEqual(out[1]["text"], "b" * 50)
        self.assertNotIn("_truncated", out[1])
        self.assertEqual(out[2], {"done": True, "_synthetic": "idle"})

    def test_default_cap_is_two_kib(self) -> None:
        self.assertEqual(DEFAULT_MAX_EVENT_CHARS, 2048)


class LastAssistantExtractionTests(TestCase):
    """Heuristic that powers acp_relay(transform='last_assistant_text')."""

    def test_prefers_role_assistant(self) -> None:
        events = [
            {"event": "log", "text": "user: hi"},
            {"role": "assistant", "content": "Trade-off paragraph."},
            {"event": "log", "text": "trailing log noise"},
        ]
        text = extract_last_assistant_text(events)
        self.assertEqual(text, "Trade-off paragraph.")

    def test_falls_back_to_log_text_when_no_role(self) -> None:
        events = [
            {"event": "log", "text": "Line 1"},
            {"event": "log", "text": "Line 2"},
            {"done": True, "_synthetic": "idle"},
        ]
        text = extract_last_assistant_text(events)
        self.assertEqual(text, "Line 1\nLine 2")

    def test_drops_empty_payloads(self) -> None:
        events = [
            {"event": "log", "text": ""},
            {"event": "log", "text": "real content"},
            {"event": "log", "text": "   "},
        ]
        self.assertEqual(extract_last_assistant_text(events), "real content")

    def test_empty_input_returns_empty(self) -> None:
        self.assertEqual(extract_last_assistant_text([]), "")
        self.assertEqual(extract_last_assistant_text([{"event": "log"}]), "")


class TranscriptReadTests(TestCase):
    """Item 2 — acp_transcript / runtime.read_transcript."""

    def test_reads_and_parses_ndjson(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            runtime = _make_runtime(Path(tmp))
            transcript = (
                json.dumps({"direction": "out", "text": "task", "ts": 1.0}) + "\n"
                + json.dumps({"direction": "in", "raw": "hello", "ts": 2.0}) + "\n"
                + json.dumps({"direction": "in", "raw": "world", "ts": 3.0}) + "\n"
            )
            _install_fake_session(runtime, "s1",
                                   transcript_text=transcript)
            result = runtime.read_transcript("s1", max_chars=8000)
            self.assertEqual(len(result["events"]), 3)
            self.assertIn("hello", result["text"])
            self.assertIn("world", result["text"])
            self.assertFalse(result["truncated"])
            self.assertGreater(result["total_size"], 0)

    def test_direction_filter_in(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            runtime = _make_runtime(Path(tmp))
            transcript = (
                json.dumps({"direction": "out", "text": "task"}) + "\n"
                + json.dumps({"direction": "in", "raw": "answer"}) + "\n"
            )
            _install_fake_session(runtime, "s2", transcript_text=transcript)
            result = runtime.read_transcript("s2", direction="in")
            self.assertEqual(len(result["events"]), 1)
            self.assertEqual(result["events"][0]["raw"], "answer")

    def test_max_chars_truncates_text(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            runtime = _make_runtime(Path(tmp))
            big = "z" * 5000
            transcript = json.dumps({"direction": "in", "raw": big}) + "\n"
            _install_fake_session(runtime, "s3", transcript_text=transcript)
            result = runtime.read_transcript("s3", max_chars=100)
            self.assertTrue(result["truncated"])
            self.assertLessEqual(len(result["text"]), 100)

    def test_unknown_session_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            runtime = _make_runtime(Path(tmp))
            from agent.acpx.runtime import AcpRuntimeError
            with self.assertRaises(AcpRuntimeError) as ctx:
                runtime.read_transcript("does-not-exist")
            self.assertEqual(ctx.exception.code, "UNKNOWN_SESSION")

    def test_acp_transcript_tool_returns_envelope(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            runtime = _make_runtime(Path(tmp))
            _install_fake_session(
                runtime, "s4",
                transcript_text=json.dumps({"direction": "in",
                                            "raw": "ok"}) + "\n",
            )
            with patch.object(acpx_tools, "get_acpx_runtime",
                              return_value=runtime):
                raw = acpx_tools.acp_transcript.invoke({"session_id": "s4"})
            envelope = json.loads(raw)
            self.assertTrue(envelope["ok"])
            self.assertEqual(envelope["session_id"], "s4")
            self.assertEqual(len(envelope["events"]), 1)


class SessionStatusAndListTests(TestCase):
    """Items 4 & 5 — acp_session_status + acp_list_sessions."""

    def test_list_sessions_reports_alive_and_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            runtime = _make_runtime(Path(tmp))
            _install_fake_session(runtime, "alive-1", agent_id="claude",
                                   transcript_text="x" * 10, alive=True)
            _install_fake_session(runtime, "dead-1", agent_id="gemini",
                                   transcript_text="y" * 50, alive=False)
            sessions = runtime.list_sessions()
            self.assertEqual(len(sessions), 2)
            ids = {s["session_id"]: s for s in sessions}
            self.assertTrue(ids["alive-1"]["alive"])
            self.assertFalse(ids["dead-1"]["alive"])
            self.assertEqual(ids["alive-1"]["agent_id"], "claude")
            self.assertGreater(ids["dead-1"]["transcript_size"], 0)

    def test_session_status_unknown_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            runtime = _make_runtime(Path(tmp))
            from agent.acpx.runtime import AcpRuntimeError
            with self.assertRaises(AcpRuntimeError) as ctx:
                runtime.session_status("missing")
            self.assertEqual(ctx.exception.code, "UNKNOWN_SESSION")

    def test_session_status_alive_session(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            runtime = _make_runtime(Path(tmp))
            _install_fake_session(runtime, "live", alive=True,
                                   transcript_text="data")
            status = runtime.session_status("live")
            self.assertTrue(status["alive"])
            self.assertEqual(status["session_id"], "live")
            self.assertGreater(status["transcript_size"], 0)
            self.assertFalse(status["closed"])

    def test_acp_list_sessions_tool_envelope(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            runtime = _make_runtime(Path(tmp))
            _install_fake_session(runtime, "a", alive=True)
            _install_fake_session(runtime, "b", alive=False)
            with patch.object(acpx_tools, "get_acpx_runtime",
                              return_value=runtime):
                raw = acpx_tools.acp_list_sessions.invoke({})
            envelope = json.loads(raw)
            self.assertTrue(envelope["ok"])
            self.assertEqual(envelope["count"], 2)


class KillReturnsTranscriptPathTests(TestCase):
    """Item 8 — acp_kill always includes transcript_path in its return."""

    def test_kill_returns_transcript_path_and_pid(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            runtime = _make_runtime(Path(tmp))
            _install_fake_session(runtime, "k1", agent_id="claude")
            with patch.object(acpx_tools, "get_acpx_runtime",
                              return_value=runtime):
                raw = acpx_tools.acp_kill.invoke({"session_id": "k1"})
            envelope = json.loads(raw)
            self.assertTrue(envelope["ok"])
            self.assertEqual(envelope["killed"], "k1")
            self.assertIn("transcript_path", envelope)
            self.assertEqual(envelope["agent_id"], "claude")
            self.assertEqual(envelope["pid"], 4242)

    def test_kill_already_gone_still_returns_transcript_path_when_on_disk(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            runtime = _make_runtime(Path(tmp))
            sess = _install_fake_session(runtime, "k2", agent_id="claude")
            # Drop the in-memory session but keep the on-disk record.
            runtime._sessions.pop("k2", None)
            with patch.object(acpx_tools, "get_acpx_runtime",
                              return_value=runtime):
                raw = acpx_tools.acp_kill.invoke({"session_id": "k2"})
            envelope = json.loads(raw)
            self.assertTrue(envelope["ok"])
            self.assertTrue(envelope.get("already_gone"))
            self.assertEqual(envelope["transcript_path"],
                             sess.record.transcript_path)


class DoctorEnumeratesAgentsTests(TestCase):
    """Item 7 — acp_doctor exposes per-agent resolvable + cli_version."""

    def test_doctor_details_is_per_agent_list_with_resolvable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            runtime = _make_runtime(Path(tmp))
            # Force every agent to look unresolvable so we don't spawn anything.
            with patch("agent.acpx.runtime.is_executable_resolvable",
                       return_value=False):
                runtime.probe_availability()
                report = runtime.doctor()
            self.assertIn("details", report)
            self.assertIsInstance(report["details"], list)
            self.assertGreater(len(report["details"]), 0)
            for entry in report["details"]:
                self.assertIn("agent_id", entry)
                self.assertIn("command", entry)
                self.assertIn("resolvable", entry)
                self.assertIn("cli_version", entry)
                self.assertFalse(entry["resolvable"])
                self.assertEqual(entry["cli_version"], "")
            self.assertIn("probe", report)

    def test_cli_version_cache_used_on_repeat(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            runtime = _make_runtime(Path(tmp))
            # First call seeds the cache; second must NOT re-run subprocess.
            spec = next(iter(runtime.agent_registry.values()))
            with patch("agent.acpx.runtime.is_executable_resolvable",
                       return_value=True), \
                 patch("agent.acpx.runtime.subprocess.run") as mock_run:
                mock_run.return_value.stdout = "v1.2.3\n"
                mock_run.return_value.stderr = ""
                v1 = runtime._capture_cli_version(spec)
                v2 = runtime._capture_cli_version(spec)
                self.assertEqual(v1, "v1.2.3")
                self.assertEqual(v2, "v1.2.3")
                self.assertEqual(mock_run.call_count, 1)


class AcpSpawnDrainKnobsTests(TestCase):
    """Item 1 — acp_spawn exposes timeout/idle/grace/max_event_chars kwargs."""

    @staticmethod
    def _make_fake_spawned(tmp: str, *, agent_id: str, transport: str,
                           spawn_returns_immediately: bool):
        """Build a _FakeSpawned stub whose ``.spec`` exposes the new
        agent_registry fields acp_spawn now consults."""
        from agent.acpx.agent_registry import AcpAgentSpec

        spec = AcpAgentSpec(
            agent_id=agent_id, command=agent_id,
            description=f"fake {agent_id}",
            transport=transport,
            spawn_returns_immediately=spawn_returns_immediately,
        )

        class _FakeSpawned:
            pass

        _FakeSpawned.spec = spec
        _FakeSpawned.record = type("R", (), {
            "session_id": f"spawned-{agent_id}",
            "agent_id": agent_id,
            "transcript_path": str(Path(tmp) / f"spawned-{agent_id}.transcript.ndjson"),
        })
        return _FakeSpawned

    def test_spawn_passes_overrides_to_runtime_send(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            runtime = _make_runtime(Path(tmp))
            captured = {}

            # JSON-ACP agent → caller overrides force a drain.
            fake_spawned = self._make_fake_spawned(
                tmp, agent_id="claude", transport="json-acp",
                spawn_returns_immediately=False,
            )

            def fake_spawn(**kwargs):
                Path(fake_spawned.record.transcript_path).touch()
                return fake_spawned

            def fake_send(session_id, text,
                          timeout_seconds=None,
                          idle_seconds=None,
                          startup_grace_seconds=None):
                captured["timeout_seconds"] = timeout_seconds
                captured["idle_seconds"] = idle_seconds
                captured["startup_grace_seconds"] = startup_grace_seconds
                return [{"event": "log", "text": "ok"},
                        {"done": True, "_synthetic": "idle"}]

            with patch.object(acpx_tools, "get_acpx_runtime",
                              return_value=runtime), \
                 patch.object(runtime, "spawn", side_effect=fake_spawn), \
                 patch.object(runtime, "send", side_effect=fake_send):
                raw = acpx_tools.acp_spawn.invoke({
                    "agent_id": "claude",
                    "task": "go",
                    "timeout_seconds": 90,
                    "idle_seconds": 12,
                    "startup_grace_seconds": 20,
                })
            envelope = json.loads(raw)
            self.assertTrue(envelope["ok"])
            self.assertEqual(captured["timeout_seconds"], 90.0)
            self.assertEqual(captured["idle_seconds"], 12.0)
            self.assertEqual(captured["startup_grace_seconds"], 20.0)
            self.assertFalse(envelope["spawned_immediately"])

    def test_spawn_zero_overrides_use_defaults(self) -> None:
        # JSON-ACP agent with spawn_returns_immediately=False, no
        # caller overrides — runtime.send is called with the historic
        # 45/6/12 defaults that the tool layer applies for the JSON-ACP
        # path.
        with tempfile.TemporaryDirectory() as tmp:
            runtime = _make_runtime(Path(tmp))
            captured = {}

            fake_spawned = self._make_fake_spawned(
                tmp, agent_id="claude", transport="json-acp",
                spawn_returns_immediately=False,
            )

            def fake_send(session_id, text,
                          timeout_seconds=None,
                          idle_seconds=None,
                          startup_grace_seconds=None):
                captured["timeout_seconds"] = timeout_seconds
                captured["idle_seconds"] = idle_seconds
                captured["startup_grace_seconds"] = startup_grace_seconds
                return [{"done": True, "_synthetic": "idle"}]

            with patch.object(acpx_tools, "get_acpx_runtime",
                              return_value=runtime), \
                 patch.object(runtime, "spawn",
                              side_effect=lambda **_: fake_spawned), \
                 patch.object(runtime, "send", side_effect=fake_send):
                Path(fake_spawned.record.transcript_path).touch()
                acpx_tools.acp_spawn.invoke({"agent_id": "claude", "task": "go"})
            self.assertEqual(captured["timeout_seconds"], 45.0)
            self.assertEqual(captured["idle_seconds"], 6.0)
            self.assertEqual(captured["startup_grace_seconds"], 12.0)


class AcpSpawnImmediateReturnTests(TestCase):
    """Fast-path: TUI agents (gemini/cursor/qwen/...) skip the drain on
    acp_spawn so the LLM gets back the session_id sub-second instead of
    waiting the full timeout. Caller can force a drain by passing any
    of the timeout/idle/grace knobs explicitly."""

    def test_tui_agent_returns_immediately_without_calling_send(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            runtime = _make_runtime(Path(tmp))
            send_called = {"count": 0}

            fake_spawned = AcpSpawnDrainKnobsTests._make_fake_spawned(
                tmp, agent_id="gemini", transport="tui-repl",
                spawn_returns_immediately=True,
            )

            def fake_send(*args, **kwargs):
                send_called["count"] += 1
                return [{"done": True, "_synthetic": "idle"}]

            with patch.object(acpx_tools, "get_acpx_runtime",
                              return_value=runtime), \
                 patch.object(runtime, "spawn",
                              side_effect=lambda **_: fake_spawned), \
                 patch.object(runtime, "send", side_effect=fake_send):
                Path(fake_spawned.record.transcript_path).touch()
                raw = acpx_tools.acp_spawn.invoke({
                    "agent_id": "gemini", "task": "go",
                })
            envelope = json.loads(raw)
            self.assertTrue(envelope["ok"])
            self.assertTrue(envelope["spawned_immediately"])
            self.assertEqual(envelope["events"], [])
            self.assertEqual(envelope["events_total"], 0)
            self.assertEqual(envelope["transport"], "tui-repl")
            # Critical: runtime.send was NOT called. This is the speedup.
            self.assertEqual(send_called["count"], 0)

    def test_tui_agent_drains_when_caller_forces_timeout(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            runtime = _make_runtime(Path(tmp))
            send_called = {"count": 0}

            fake_spawned = AcpSpawnDrainKnobsTests._make_fake_spawned(
                tmp, agent_id="gemini", transport="tui-repl",
                spawn_returns_immediately=True,
            )

            def fake_send(*args, **kwargs):
                send_called["count"] += 1
                return [{"event": "log", "text": "drained"},
                        {"done": True, "_synthetic": "idle"}]

            with patch.object(acpx_tools, "get_acpx_runtime",
                              return_value=runtime), \
                 patch.object(runtime, "spawn",
                              side_effect=lambda **_: fake_spawned), \
                 patch.object(runtime, "send", side_effect=fake_send):
                Path(fake_spawned.record.transcript_path).touch()
                raw = acpx_tools.acp_spawn.invoke({
                    "agent_id": "gemini", "task": "go",
                    "timeout_seconds": 60,  # caller forces drain
                })
            envelope = json.loads(raw)
            self.assertTrue(envelope["ok"])
            self.assertFalse(envelope["spawned_immediately"])
            self.assertEqual(send_called["count"], 1)

    def test_json_acp_agent_drains_on_spawn_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            runtime = _make_runtime(Path(tmp))
            send_called = {"count": 0}

            fake_spawned = AcpSpawnDrainKnobsTests._make_fake_spawned(
                tmp, agent_id="claude", transport="json-acp",
                spawn_returns_immediately=False,
            )

            def fake_send(*args, **kwargs):
                send_called["count"] += 1
                return [{"done": True, "_synthetic": "idle"}]

            with patch.object(acpx_tools, "get_acpx_runtime",
                              return_value=runtime), \
                 patch.object(runtime, "spawn",
                              side_effect=lambda **_: fake_spawned), \
                 patch.object(runtime, "send", side_effect=fake_send):
                Path(fake_spawned.record.transcript_path).touch()
                raw = acpx_tools.acp_spawn.invoke({
                    "agent_id": "claude", "task": "go",
                })
            envelope = json.loads(raw)
            self.assertTrue(envelope["ok"])
            self.assertFalse(envelope["spawned_immediately"])
            self.assertEqual(send_called["count"], 1)


class OneshotPromptCaptureTests(TestCase):
    """The transport that actually grabs Claude / Gemini answers on
    Windows: re-spawn the CLI per turn with the prompt as a CLI arg
    behind ``prompt_arg_flag``, close stdin, and capture stdout to EOF.

    We exercise it without touching real CLIs by overriding the spec to
    point at a tiny ``python -c`` that prints a known string, so the
    test runs identically on any platform with Python on PATH.
    """

    def _install_oneshot_session(self, runtime, *, agent_id: str,
                                 prompt_flag, prompt_subargs,
                                 stdout_text: str = "hello from claude\n",
                                 stderr_text: str = "",
                                 exit_code: int = 0) -> "AcpSession":
        from agent.acpx.agent_registry import AcpAgentSpec
        from agent.acpx.runtime import AcpSession
        from agent.acpx.session_store import AcpSessionRecord, now_epoch

        sid = f"oneshot-{agent_id}"
        transcript_path = Path(runtime.config.state_dir) / f"{sid}.transcript.ndjson"
        transcript_path.parent.mkdir(parents=True, exist_ok=True)
        # Build a python -c snippet that emulates ``claude -p "<task>"``:
        # prints stdout_text, optionally stderr_text, then exits.
        snippet = (
            "import sys; "
            f"sys.stdout.write({stdout_text!r}); sys.stdout.flush(); "
            f"sys.stderr.write({stderr_text!r}); sys.stderr.flush(); "
            f"sys.exit({exit_code})"
        )
        spec = AcpAgentSpec(
            agent_id=agent_id, command=sys.executable,
            args=["-c", snippet],
            description=f"oneshot fake {agent_id}",
            transport="oneshot-prompt",
            prompt_arg_flag=prompt_flag,
            prompt_subcommand_args=list(prompt_subargs or []),
            default_idle_seconds=10.0,
            default_startup_grace_seconds=2.0,
            default_timeout_seconds=30.0,
        )
        record = AcpSessionRecord(
            session_id=sid, name=sid, agent_id=agent_id,
            cwd=str(runtime.config.state_dir),
            state_path=str(Path(runtime.config.state_dir) / f"{sid}.json"),
            transcript_path=str(transcript_path),
            pid=None, created_at=now_epoch(), last_active_at=now_epoch(),
        )
        runtime.session_store.save(record)
        sess = AcpSession(runtime=runtime, spec=spec,
                           cwd=Path(record.cwd), mode="session", record=record)
        runtime._sessions[sid] = sess
        return sess

    def test_send_turn_captures_stdout_as_assistant_message(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            runtime = _make_runtime(Path(tmp))
            sess = self._install_oneshot_session(
                runtime, agent_id="claude",
                prompt_flag="-p", prompt_subargs=[],
                stdout_text="hello from claude\n",
            )
            events = runtime.send(sess.record.session_id, "what's up?",
                                  timeout_seconds=15.0)
            assistant = [e for e in events if e.get("event") == "assistant_message"]
            self.assertEqual(len(assistant), 1)
            self.assertEqual(assistant[0]["text"], "hello from claude")
            self.assertEqual(assistant[0]["role"], "assistant")
            self.assertEqual(assistant[0]["exit_code"], 0)
            self.assertEqual(events[-1]["_synthetic"], "child_exited")
            self.assertEqual(events[-1]["transport"], "oneshot-prompt")

    def test_send_turn_writes_transcript_in_and_out(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            runtime = _make_runtime(Path(tmp))
            sess = self._install_oneshot_session(
                runtime, agent_id="gemini",
                prompt_flag="-p", prompt_subargs=[],
                stdout_text="grok from gemini\n",
            )
            runtime.send(sess.record.session_id, "ping?",
                         timeout_seconds=15.0)
            transcript_lines = Path(sess.record.transcript_path).read_text(
                encoding="utf-8"
            ).strip().splitlines()
            entries = [json.loads(ln) for ln in transcript_lines]
            directions = [e.get("direction") for e in entries]
            self.assertIn("out", directions)
            self.assertIn("in", directions)
            in_payloads = [e for e in entries if e.get("direction") == "in"]
            self.assertTrue(any("grok from gemini" in (e.get("text") or "")
                                for e in in_payloads))

    def test_extract_last_assistant_text_picks_up_oneshot_event(self) -> None:
        from agent.acpx.runtime import extract_last_assistant_text
        events = [
            {"event": "assistant_message", "role": "assistant",
             "text": "the answer is 42"},
            {"event": "log", "channel": "stderr", "text": "noisy warning"},
            {"done": True, "_synthetic": "child_exited",
             "transport": "oneshot-prompt"},
        ]
        self.assertEqual(extract_last_assistant_text(events),
                          "the answer is 42")

    def test_command_not_on_path_returns_clean_error_event(self) -> None:
        from agent.acpx.agent_registry import AcpAgentSpec
        from agent.acpx.runtime import AcpSession
        from agent.acpx.session_store import AcpSessionRecord, now_epoch

        with tempfile.TemporaryDirectory() as tmp:
            runtime = _make_runtime(Path(tmp))
            sid = "oneshot-missing"
            transcript_path = Path(tmp) / f"{sid}.transcript.ndjson"
            spec = AcpAgentSpec(
                agent_id="missing-cli",
                command="this-binary-does-not-exist-12345",
                description="missing", transport="oneshot-prompt",
                prompt_arg_flag="-p",
                default_idle_seconds=10.0,
                default_startup_grace_seconds=2.0,
                default_timeout_seconds=10.0,
            )
            record = AcpSessionRecord(
                session_id=sid, name=sid, agent_id="missing-cli",
                cwd=str(tmp),
                state_path=str(Path(tmp) / f"{sid}.json"),
                transcript_path=str(transcript_path),
                pid=None, created_at=now_epoch(), last_active_at=now_epoch(),
            )
            sess = AcpSession(runtime=runtime, spec=spec,
                               cwd=Path(tmp), mode="session", record=record)
            runtime._sessions[sid] = sess
            events = runtime.send(sid, "task", timeout_seconds=10.0)
            # First event = error, last = synthetic done with command_not_found
            self.assertEqual(events[-1]["_synthetic"], "command_not_found")
            self.assertTrue(any(e.get("event") == "error" for e in events))


class AgentRegistryTransportProfileTests(TestCase):
    """The default registry's transport assignments encode the only way
    we know to actually capture each CLI's output:

    - ``oneshot-prompt`` for claude/codex/cursor/gemini/qwen — these
      CLIs render a TUI when run interactively (so a long-lived child
      fed via stdin captures NOTHING on Windows). The fix is to
      re-spawn per turn with the prompt as a CLI arg behind
      ``prompt_arg_flag`` (or ``prompt_subcommand_args`` for codex)
      and capture stdout to EOF.
    - ``tui-repl`` for kiro/kimi/iflow/kilocode/opencode/pi/droid/
      copilot — kept on the legacy fast-path because we don't yet
      know each CLI's one-shot flag. Users override per-agent in
      ``config.json.acpx.agents.<id>``.
    - ``json-acp`` for ``tlamatini`` — the self-host server speaks
      JSON-ACP natively so the blocking drain still applies.
    """

    def test_legacy_tui_agents_keep_fast_path_defaults(self) -> None:
        from agent.acpx.agent_registry import build_agent_registry

        reg = build_agent_registry()
        for agent_id in ("kiro", "kimi", "iflow", "kilocode", "opencode",
                         "pi", "droid", "copilot"):
            spec = reg[agent_id]
            self.assertEqual(spec.transport, "tui-repl",
                              f"{agent_id} should be tui-repl")
            self.assertTrue(spec.spawn_returns_immediately,
                             f"{agent_id} should spawn immediately")
            # TUI defaults: short hard cap so a silent REPL returns fast.
            self.assertLessEqual(spec.default_timeout_seconds or 99, 10)

    def test_oneshot_prompt_agents_have_capture_path(self) -> None:
        from agent.acpx.agent_registry import build_agent_registry

        reg = build_agent_registry()
        # Each entry: (agent_id, expected_flag, expected_subargs_prefix).
        expectations = [
            ("claude", "-p", []),
            ("cursor", "-p", []),
            ("gemini", "-p", []),
            ("qwen",   "-p", []),
            ("codex",  None, ["exec"]),
        ]
        for agent_id, flag, subargs in expectations:
            spec = reg[agent_id]
            self.assertEqual(spec.transport, "oneshot-prompt",
                              f"{agent_id} should be oneshot-prompt")
            self.assertFalse(spec.spawn_returns_immediately,
                              f"{agent_id} drains in spawn (no immediate return)")
            self.assertEqual(spec.prompt_arg_flag, flag,
                              f"{agent_id} prompt_arg_flag mismatch")
            self.assertEqual(list(spec.prompt_subcommand_args), subargs,
                              f"{agent_id} prompt_subcommand_args mismatch")
            # Generous timeout: LLM answers can take >2 minutes.
            self.assertGreaterEqual(spec.default_timeout_seconds or 0, 60)

    def test_json_acp_self_host_keeps_blocking_drain(self) -> None:
        from agent.acpx.agent_registry import build_agent_registry

        reg = build_agent_registry()
        spec = reg["tlamatini"]
        self.assertEqual(spec.transport, "json-acp")
        self.assertFalse(spec.spawn_returns_immediately)

    def test_user_defined_unknown_agent_defaults_to_fast_path(self) -> None:
        from agent.acpx.agent_registry import build_agent_registry

        reg = build_agent_registry(overrides={"my_custom_cli": "/usr/bin/foo"})
        spec = reg["my_custom_cli"]
        self.assertEqual(spec.transport, "tui-repl")
        self.assertTrue(spec.spawn_returns_immediately)


class TransportAwareIdleRuleTests(TestCase):
    """The idle-rule fix: TUI/one-shot transports must allow the idle
    rule to fire even when the child has produced ZERO events. JSON-ACP
    keeps the original "needs ≥1 event" gate (because a JSON-ACP child
    is contractually expected to emit at least one event per turn)."""

    def _spawn_silent_session(self, runtime, transport: str):
        """Install a fake session whose stdin/stdout are wired to a
        SpooledTemporaryFile pair — the child never produces output."""
        from agent.acpx.agent_registry import AcpAgentSpec
        from agent.acpx.session_store import AcpSessionRecord, now_epoch

        sid = f"silent-{transport}"
        transcript_path = Path(runtime.config.state_dir) / f"{sid}.transcript.ndjson"
        transcript_path.parent.mkdir(parents=True, exist_ok=True)
        record = AcpSessionRecord(
            session_id=sid,
            name=sid,
            agent_id="silent",
            cwd=str(runtime.config.state_dir),
            state_path=str(Path(runtime.config.state_dir) / f"{sid}.json"),
            transcript_path=str(transcript_path),
            pid=4242,
            created_at=now_epoch(),
            last_active_at=now_epoch(),
        )
        runtime.session_store.save(record)
        spec = AcpAgentSpec(agent_id="silent", command="silent",
                            transport=transport)

        class _SilentProc:
            stdin_buf: list = []
            returncode = None

            class _Stdin:
                @staticmethod
                def write(s):
                    _SilentProc.stdin_buf.append(s)

                @staticmethod
                def flush():
                    pass

                @staticmethod
                def close():
                    pass

            class _Stdout:
                # Block forever — simulates a TUI REPL that never emits.
                @staticmethod
                def readline():
                    import time as _t
                    _t.sleep(60)
                    return ""

            stdin = _Stdin
            stdout = _Stdout

            @staticmethod
            def poll():
                return None

        sess = AcpSession(runtime=runtime, spec=spec,
                          cwd=Path(record.cwd), mode="session", record=record)
        sess.proc = _SilentProc
        # We deliberately don't start the reader thread here so the
        # queue stays empty for the duration of the test (faster).
        runtime._sessions[sid] = sess
        return sess

    def test_tui_idle_rule_fires_with_zero_events(self) -> None:
        """The fix: a TUI child that emits nothing must still complete
        on the idle rule within startup_grace + idle, instead of waiting
        the full timeout."""
        with tempfile.TemporaryDirectory() as tmp:
            runtime = _make_runtime(Path(tmp))
            sess = self._spawn_silent_session(runtime, transport="tui-repl")
            t0 = time.time()
            events = list(sess.send_turn(
                "go", timeout_seconds=30.0,
                idle_seconds=0.5, startup_grace_seconds=0.5,
            ))
            elapsed = time.time() - t0
            self.assertGreaterEqual(len(events), 1)
            self.assertEqual(events[-1]["_synthetic"], "idle")
            self.assertEqual(events[-1]["events_seen"], 0)
            self.assertEqual(events[-1]["transport"], "tui-repl")
            # Must complete in ≤ grace+idle+slack, NOT timeout.
            self.assertLess(elapsed, 5.0,
                             f"TUI idle rule too slow: {elapsed:.2f}s")

    def test_json_acp_still_requires_event_for_idle(self) -> None:
        """Regression guard: JSON-ACP keeps the strict idle rule that
        requires ≥1 event before completion."""
        with tempfile.TemporaryDirectory() as tmp:
            runtime = _make_runtime(Path(tmp))
            sess = self._spawn_silent_session(runtime, transport="json-acp")
            t0 = time.time()
            events = list(sess.send_turn(
                "go", timeout_seconds=2.0,
                idle_seconds=0.3, startup_grace_seconds=0.3,
            ))
            elapsed = time.time() - t0
            self.assertGreaterEqual(len(events), 1)
            # JSON-ACP with no events must hit the timeout, not idle.
            self.assertEqual(events[-1]["_synthetic"], "timeout")
            self.assertGreaterEqual(elapsed, 1.5)


class AcpSendAndWaitTests(TestCase):
    """Item 3 — acp_send_and_wait reports settled=True on idle drain."""

    def test_returns_settled_true_on_idle(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            runtime = _make_runtime(Path(tmp))

            def fake_send(*args, **kwargs):
                return [{"event": "log", "text": "answer"},
                        {"done": True, "_synthetic": "idle"}]

            with patch.object(acpx_tools, "get_acpx_runtime",
                              return_value=runtime), \
                 patch.object(runtime, "send", side_effect=fake_send):
                raw = acpx_tools.acp_send_and_wait.invoke({
                    "session_id": "s",
                    "text": "next",
                })
            envelope = json.loads(raw)
            self.assertTrue(envelope["ok"])
            self.assertTrue(envelope["settled"])
            self.assertEqual(envelope["events_total"], 2)

    def test_returns_settled_false_on_timeout(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            runtime = _make_runtime(Path(tmp))

            def fake_send(*args, **kwargs):
                return [{"event": "log", "text": "partial"},
                        {"done": True, "_synthetic": "timeout",
                         "events_seen": 1}]

            with patch.object(acpx_tools, "get_acpx_runtime",
                              return_value=runtime), \
                 patch.object(runtime, "send", side_effect=fake_send):
                raw = acpx_tools.acp_send_and_wait.invoke({
                    "session_id": "s",
                    "text": "next",
                })
            envelope = json.loads(raw)
            self.assertTrue(envelope["ok"])
            self.assertFalse(envelope["settled"])


class AcpRelayTests(TestCase):
    """Item 6 — acp_relay copies last assistant text from src → dst."""

    def test_relay_passes_extracted_text_to_dst_with_wrapping(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            runtime = _make_runtime(Path(tmp))
            transcript = (
                json.dumps({"direction": "out", "text": "go"}) + "\n"
                + json.dumps({"direction": "in",
                               "raw": json.dumps({"role": "assistant",
                                                  "content": "Trade-offs paragraph."})}) + "\n"
            )
            _install_fake_session(runtime, "src",
                                   transcript_text=transcript)
            _install_fake_session(runtime, "dst")

            captured = {}

            def fake_send(session_id, text, **kwargs):
                captured["session_id"] = session_id
                captured["text"] = text
                return [{"event": "log", "text": "leg-b answer"},
                        {"done": True, "_synthetic": "idle"}]

            with patch.object(acpx_tools, "get_acpx_runtime",
                              return_value=runtime), \
                 patch.object(runtime, "send", side_effect=fake_send):
                raw = acpx_tools.acp_relay.invoke({
                    "session_id_src": "src",
                    "session_id_dst": "dst",
                    "transform": "last_assistant_text",
                    "prefix": "Analysis: ",
                })
            envelope = json.loads(raw)
            self.assertTrue(envelope["ok"], envelope)
            self.assertEqual(envelope["session_id_src"], "src")
            self.assertEqual(envelope["session_id_dst"], "dst")
            self.assertTrue(envelope["settled"])
            self.assertEqual(captured["session_id"], "dst")
            self.assertIn("Analysis: ", captured["text"])
            self.assertIn("Trade-offs paragraph.", captured["text"])

    def test_relay_full_transcript_transform(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            runtime = _make_runtime(Path(tmp))
            _install_fake_session(
                runtime, "src",
                transcript_text=(
                    json.dumps({"direction": "in", "raw": "leg-a-payload"}) + "\n"
                ),
            )
            _install_fake_session(runtime, "dst")

            sent = {}

            def fake_send(session_id, text, **kwargs):
                sent["text"] = text
                return [{"done": True, "_synthetic": "idle"}]

            with patch.object(acpx_tools, "get_acpx_runtime",
                              return_value=runtime), \
                 patch.object(runtime, "send", side_effect=fake_send):
                raw = acpx_tools.acp_relay.invoke({
                    "session_id_src": "src",
                    "session_id_dst": "dst",
                    "transform": "full_transcript",
                })
            envelope = json.loads(raw)
            self.assertTrue(envelope["ok"], envelope)
            self.assertIn("leg-a-payload", sent["text"])

    def test_relay_unknown_transform_returns_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            runtime = _make_runtime(Path(tmp))
            with patch.object(acpx_tools, "get_acpx_runtime",
                              return_value=runtime):
                raw = acpx_tools.acp_relay.invoke({
                    "session_id_src": "x",
                    "session_id_dst": "y",
                    "transform": "bogus",
                })
            envelope = json.loads(raw)
            self.assertFalse(envelope["ok"])
            self.assertEqual(envelope["code"], "BAD_TRANSFORM")

    def test_relay_empty_source_returns_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            runtime = _make_runtime(Path(tmp))
            _install_fake_session(runtime, "src",
                                   transcript_text="")
            _install_fake_session(runtime, "dst")
            with patch.object(acpx_tools, "get_acpx_runtime",
                              return_value=runtime):
                raw = acpx_tools.acp_relay.invoke({
                    "session_id_src": "src",
                    "session_id_dst": "dst",
                })
            envelope = json.loads(raw)
            self.assertFalse(envelope["ok"])
            self.assertEqual(envelope["code"], "EMPTY_RELAY")
