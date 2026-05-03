"""
ACPX-related LangChain @tool functions exposed to the unified agent.

These tools are registered in agent.tools.get_mcp_tools() through the
existing toggle pattern (a `Tool` row + a global_state status key).

The @tool functions return JSON strings so the LLM can parse them
deterministically. They never raise — every error is surfaced as
{"ok": false, "reason": "...", "code": "..."} on a successful return.
"""
from __future__ import annotations

import json
import logging
import traceback
from typing import Any, Dict, Union

from langchain.tools import tool

from .runtime import AcpRuntimeError, get_acpx_runtime

logger = logging.getLogger(__name__)


def _ok(payload: Dict[str, Any]) -> str:
    out = {"ok": True}
    out.update(payload)
    return json.dumps(out, ensure_ascii=False)


def _err(reason: str, code: str = "ERROR", **extra: Any) -> str:
    payload = {"ok": False, "reason": reason, "code": code}
    payload.update(extra)
    return json.dumps(payload, ensure_ascii=False)


@tool
def acp_spawn(agent_id: str, task: str, cwd: str = "",
              mode: str = "session", session_label: str = "") -> str:
    """
    Spawn an external coding-agent CLI (claude / cursor / codex / qwen / etc.)
    as an ACP child process and dispatch `task` to it. The child runs
    out-of-process; this tool returns immediately with the session_id.

    Args:
        agent_id: registered agent id. Use list_acp_agents to see options.
        task: the prompt the child should start working on.
        cwd: working directory for the child (default: ACPX config cwd).
        mode: "session" (long-lived, follow-up turns possible via acp_send)
              or "one-shot" (single-turn).
        session_label: optional human-readable label for the session.

    Returns: JSON {"ok": true, "session_id": "...", "agent_id": "...",
                   "transcript_path": "...", "events": [...]} or
             {"ok": false, "reason": "...", "code": "..."}.
    """
    try:
        runtime = get_acpx_runtime()
        sess = runtime.spawn(
            agent_id=agent_id, task=task, cwd=cwd or None,
            mode=mode, session_label=session_label,
        )
        # Drain the initial turn output. Use a tight initial-drain budget
        # so non-JSON-ACP REPLs (gemini/cursor/qwen/codex) surface fast
        # via the idle-completion rule instead of burning the full
        # configured timeout on the very first call.
        events = runtime.send(
            sess.record.session_id, task,
            timeout_seconds=45.0,
            idle_seconds=6.0,
            startup_grace_seconds=12.0,
        )
        return _ok({
            "session_id": sess.record.session_id,
            "agent_id": sess.record.agent_id,
            "transcript_path": sess.record.transcript_path,
            "events": events[-32:],  # last 32 events to keep the response small
        })
    except AcpRuntimeError as e:
        return _err(e.message, code=e.code)
    except Exception as e:
        logger.exception("[acp_spawn] unexpected error")
        return _err(str(e), code="EXCEPTION", traceback=traceback.format_exc()[-2000:])


@tool
def acp_send(session_id: str, text: str, timeout_seconds: float = 0.0) -> str:
    """
    Send a follow-up turn to an existing ACP session.

    Args:
        session_id: id returned by acp_spawn.
        text: the next prompt for the ACP child.
        timeout_seconds: optional override; 0 means use the runtime default.

    Returns: JSON {"ok": true, "events": [...]} or error envelope.
    """
    try:
        runtime = get_acpx_runtime()
        events = runtime.send(
            session_id, text,
            timeout_seconds=timeout_seconds if timeout_seconds > 0 else None,
            idle_seconds=6.0,
            startup_grace_seconds=4.0,
        )
        return _ok({"events": events[-64:]})
    except AcpRuntimeError as e:
        return _err(e.message, code=e.code)
    except Exception as e:
        logger.exception("[acp_send] unexpected error")
        return _err(str(e), code="EXCEPTION")


@tool
def acp_kill(session_id: str) -> str:
    """
    Terminate an ACP session and its child process.
    Returns: JSON {"ok": true, "killed": "<session_id>"} or error envelope.
    """
    try:
        runtime = get_acpx_runtime()
        runtime.kill(session_id)
        return _ok({"killed": session_id})
    except AcpRuntimeError as e:
        return _err(e.message, code=e.code)
    except Exception as e:
        logger.exception("[acp_kill] unexpected error")
        return _err(str(e), code="EXCEPTION")


@tool
def acp_doctor() -> str:
    """
    Run a health probe of the ACPX runtime.
    Returns: JSON {"ok": <bool>, "message": "...", "details": [...]}.
    Note: this returns ok=False when the probe agent is unhealthy; the
    envelope's outer "ok" reflects probe health, not tool execution.
    """
    try:
        runtime = get_acpx_runtime()
        runtime.probe_availability()
        report = runtime.doctor()
        return json.dumps({
            "ok": bool(report.get("ok")),
            "message": report.get("message", ""),
            "details": report.get("details", []),
        }, ensure_ascii=False)
    except Exception as e:
        logger.exception("[acp_doctor] unexpected error")
        return _err(str(e), code="EXCEPTION")


@tool
def list_acp_agents() -> str:
    """
    List all registered ACP agents and whether each command resolves on PATH.
    Returns: JSON {"ok": true, "agents": [{"agent_id", "command",
                                           "description", "resolvable"}, ...]}.
    """
    try:
        runtime = get_acpx_runtime()
        return _ok({"agents": runtime.list_agents()})
    except Exception as e:
        logger.exception("[list_acp_agents] unexpected error")
        return _err(str(e), code="EXCEPTION")


# ── Skills tools ──────────────────────────────────────────────────────
@tool
def list_skills(filter_keywords: str = "") -> str:
    """
    List all registered Tlamatini skills with name + 1-line description.
    Optionally filter by space-separated keywords.

    Returns: JSON {"ok": true, "skills":[{"name","description","runtime"}]}.
    """
    try:
        from agent.skills.registry import skill_registry
        skill_registry.reload_if_stale()
        listing = skill_registry.list(filter_keywords)
        return _ok({"skills": listing})
    except Exception as e:
        logger.exception("[list_skills] unexpected error")
        return _err(str(e), code="EXCEPTION")


@tool
def invoke_skill(skill_name: str,
                 args_json: Union[str, Dict[str, Any], None] = "{}") -> str:
    """
    Invoke a registered Tlamatini skill by name. The skill runs inside the
    SkillHarness, which enforces the skill's permissions, budget, and
    input/output contract.

    Args:
        skill_name: registered skill name (see list_skills).
        args_json: skill input args. Either a JSON string (preferred,
            e.g. '{"who":"angel"}') OR an already-parsed JSON object
            ({"who": "angel"}). Both shapes are accepted because some
            LLMs parse the example before emitting the tool call.

    Returns: JSON {"ok": true, "skill": "...", "output": {...},
                   "iterations_used": N, "audit_id": "..."} or error envelope.
    """
    try:
        from agent.skills.registry import skill_registry
        from agent.skills.harness import SkillHarness
        skill_registry.reload_if_stale()
        skill = skill_registry.get(skill_name)
        if skill is None:
            return _err(f"unknown skill '{skill_name}'", code="UNKNOWN_SKILL")
        # Coerce args_json to a dict, accepting:
        #   - dict        → use directly
        #   - JSON string → parse
        #   - None / ""   → empty dict
        #   - anything else → BAD_ARGS
        if args_json is None or args_json == "":
            args = {}
        elif isinstance(args_json, dict):
            args = args_json
        elif isinstance(args_json, str):
            try:
                args = json.loads(args_json)
            except Exception as e:
                return _err(f"args_json invalid JSON: {e}", code="BAD_JSON")
            if not isinstance(args, dict):
                return _err("args_json must encode a JSON object",
                            code="BAD_ARGS")
        else:
            return _err(
                f"args_json must be a JSON string or object, got "
                f"{type(args_json).__name__}",
                code="BAD_ARGS",
            )
        harness = SkillHarness(skill)
        result = harness.invoke(args)
        return json.dumps(result, ensure_ascii=False)
    except Exception as e:
        logger.exception("[invoke_skill] unexpected error")
        return _err(str(e), code="EXCEPTION", traceback=traceback.format_exc()[-2000:])
