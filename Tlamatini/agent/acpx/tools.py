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

from .runtime import (
    AcpRuntimeError,
    DEFAULT_MAX_EVENT_CHARS,
    extract_last_assistant_text,
    get_acpx_runtime,
    trim_events,
)

logger = logging.getLogger(__name__)


def _ok(payload: Dict[str, Any]) -> str:
    out = {"ok": True}
    out.update(payload)
    return json.dumps(out, ensure_ascii=False)


def _err(reason: str, code: str = "ERROR", **extra: Any) -> str:
    payload = {"ok": False, "reason": reason, "code": code}
    payload.update(extra)
    return json.dumps(payload, ensure_ascii=False)


def _coerce_positive_float(v: Any, default: float) -> float:
    """LangChain serializes args through JSON; numeric kwargs may arrive as
    strings. Treat any non-positive value as "use default" to keep the
    contract simple for the LLM."""
    try:
        f = float(v)
    except (TypeError, ValueError):
        return default
    return f if f > 0 else default


@tool
def acp_spawn(agent_id: str, task: str, cwd: str = "",
              mode: str = "session", session_label: str = "",
              timeout_seconds: float = 0.0,
              idle_seconds: float = 0.0,
              startup_grace_seconds: float = 0.0,
              max_event_chars: int = 0) -> str:
    """
    Spawn an external coding-agent CLI (claude / cursor / codex / gemini /
    qwen / kiro / kimi / iflow / kilocode / opencode / pi / droid /
    copilot / tlamatini self-host) as an ACP child and dispatch ``task``
    to it.

    Behavior depends on the registered agent's transport profile:

    - ``oneshot-prompt`` (claude / cursor / gemini / qwen / codex):
      re-spawns the CLI fresh with the prompt as a CLI argument
      (``claude -p "<task>"``, ``codex exec "<task>"``, etc.), closes
      stdin, captures stdout to EOF. The first turn runs synchronously
      and returns the answer in ``events`` as an ``assistant_message``
      event with ``role:"assistant"`` and the captured text. Default
      hard cap 180 s; LLM answers can take >2 min.
    - ``json-acp`` (tlamatini self-host): drains the child until a
      ``"done": true`` envelope. Default 45 s timeout.
    - ``tui-repl`` (kiro / kimi / iflow / kilocode / opencode / pi /
      droid / copilot): returns ``session_id`` sub-second with
      ``spawned_immediately:true`` and an empty ``events`` array; harvest
      content via the next ``acp_send`` / ``acp_send_and_wait`` /
      ``acp_transcript``.

    Args:
        agent_id: registered agent id. Use list_acp_agents to see options.
        task: the prompt the child should start working on.
        cwd: working directory for the child (default: ACPX config cwd).
        mode: controls follow-up continuity ONLY, NOT the transport (the
              transport is fixed per agent_id by the registry, regardless of
              this value). "session" (long-lived, follow-up turns possible
              via acp_send) or "one-shot" (single-turn). Note: ``mode`` is
              effectively ignored by ``oneshot-prompt`` agents because
              every turn is its own fresh process — there is no in-child
              session state between calls.
        session_label: optional human-readable label for the session.
        timeout_seconds: hard cap on the drain. Default depends on the
            transport: 180 s for oneshot-prompt, 45 s for json-acp, 8 s
            for tui-repl. Override when you need a longer answer.
        idle_seconds: how long the child must stay silent before the drain
            ends with a synthetic "idle" event. Default 6 s for json-acp,
            2 s for tui-repl, 10 s for oneshot-prompt (largely unused for
            the latter — it drains until child exit).
        startup_grace_seconds: how long the idle rule is suppressed after
            spawn. Default 12 s json-acp / 3 s tui-repl / 2 s oneshot-prompt.
        max_event_chars: cap on the size of each event's text/content body
            in the response (default 2048). Use 0 to keep the runtime default.

    Returns: JSON {"ok": true, "session_id": "...", "agent_id": "...",
                   "transport": "...", "transcript_path": "...",
                   "events": [...], "events_total": N,
                   "spawned_immediately": bool} or
             {"ok": false, "reason": "...", "code": "..."}.
    """
    try:
        runtime = get_acpx_runtime()
        sess = runtime.spawn(
            agent_id=agent_id, task=task, cwd=cwd or None,
            mode=mode, session_label=session_label,
        )
        cap = int(max_event_chars) if max_event_chars and int(max_event_chars) > 0 else DEFAULT_MAX_EVENT_CHARS
        # Honor the per-spec spawn_returns_immediately flag: TUI REPLs
        # (gemini/cursor/qwen) decouple spawn latency from content
        # latency by returning the session_id immediately. The actual
        # drain happens on the next acp_send / acp_send_and_wait /
        # acp_transcript. The LLM still receives a usable session
        # sub-second instead of waiting the full timeout. Caller can
        # force a drain by passing any of the timeout/idle/grace knobs
        # explicitly (>0), which are read as a strong "drain on spawn"
        # signal.
        caller_forced_drain = (
            (timeout_seconds and timeout_seconds > 0)
            or (idle_seconds and idle_seconds > 0)
            or (startup_grace_seconds and startup_grace_seconds > 0)
        )
        if sess.spec.spawn_returns_immediately and not caller_forced_drain:
            return _ok({
                "session_id": sess.record.session_id,
                "agent_id": sess.record.agent_id,
                "transport": sess.spec.transport,
                "transcript_path": sess.record.transcript_path,
                "events": [],
                "events_total": 0,
                "spawned_immediately": True,
                "hint": ("Spawn returned immediately for TUI agent. "
                         "Call acp_send_and_wait or acp_transcript to "
                         "harvest content, or pass timeout_seconds>0 to "
                         "force a drain on this acp_spawn call."),
            })
        # Drain path: caller forced it OR the agent is JSON-ACP. Use the
        # caller's overrides if present; otherwise the per-spec defaults
        # in runtime.send() will kick in.
        events = runtime.send(
            sess.record.session_id, task,
            timeout_seconds=_coerce_positive_float(timeout_seconds, 45.0),
            idle_seconds=_coerce_positive_float(idle_seconds, 6.0),
            startup_grace_seconds=_coerce_positive_float(startup_grace_seconds, 12.0),
        )
        trimmed = trim_events(events[-32:], max_event_chars=cap)
        return _ok({
            "session_id": sess.record.session_id,
            "agent_id": sess.record.agent_id,
            "transport": sess.spec.transport,
            "transcript_path": sess.record.transcript_path,
            "events": trimmed,
            "events_total": len(events),
            "spawned_immediately": False,
        })
    except AcpRuntimeError as e:
        return _err(e.message, code=e.code)
    except Exception as e:
        logger.exception("[acp_spawn] unexpected error")
        return _err(str(e), code="EXCEPTION", traceback=traceback.format_exc()[-2000:])


@tool
def acp_send(session_id: str, text: str, timeout_seconds: float = 0.0,
             idle_seconds: float = 0.0,
             startup_grace_seconds: float = 0.0,
             max_event_chars: int = 0) -> str:
    """
    Send a follow-up turn to an existing ACP session.

    For ``oneshot-prompt`` sessions (claude / cursor / gemini / qwen /
    codex), each call re-spawns the CLI from scratch — the child has no
    memory of previous turns. If you need conversation continuity,
    include the prior context in ``text`` yourself.

    Args:
        session_id: id returned by acp_spawn.
        text: the next prompt for the ACP child.
        timeout_seconds: optional override; 0 means use the per-spec
            default (180 s for oneshot-prompt, 45 s for json-acp, 8 s
            for tui-repl).
        idle_seconds: how long the child must stay silent before the drain
            ends. Default 6 s (json-acp), 2 s (tui-repl), 10 s
            (oneshot-prompt — largely unused).
        startup_grace_seconds: idle suppression window after spawn.
        max_event_chars: per-event body cap (default 2048).

    Returns: JSON {"ok": true, "events": [...]} or error envelope. For
    ``oneshot-prompt`` sessions, the events array contains one
    ``assistant_message`` event with the captured stdout.
    """
    try:
        runtime = get_acpx_runtime()
        events = runtime.send(
            session_id, text,
            timeout_seconds=timeout_seconds if timeout_seconds and timeout_seconds > 0 else None,
            idle_seconds=_coerce_positive_float(idle_seconds, 6.0),
            startup_grace_seconds=_coerce_positive_float(startup_grace_seconds, 4.0),
        )
        cap = int(max_event_chars) if max_event_chars and int(max_event_chars) > 0 else DEFAULT_MAX_EVENT_CHARS
        trimmed = trim_events(events[-64:], max_event_chars=cap)
        return _ok({"events": trimmed, "events_total": len(events)})
    except AcpRuntimeError as e:
        return _err(e.message, code=e.code)
    except Exception as e:
        logger.exception("[acp_send] unexpected error")
        return _err(str(e), code="EXCEPTION")


@tool
def acp_send_and_wait(session_id: str, text: str,
                      until_idle_seconds: float = 10.0,
                      max_wait_seconds: float = 180.0,
                      max_event_chars: int = 0) -> str:
    """
    Send a follow-up turn and wait for the child to settle (no output for
    ``until_idle_seconds``). Use this when you need a complete answer for
    hand-off (e.g. before passing the result to another ACP agent).

    For ``oneshot-prompt`` sessions, this is equivalent to a normal
    ``acp_send`` with the same timeout — the child always exits when its
    one-shot turn completes, so ``settled`` reflects ``child_exited``
    rather than the idle rule.

    Args:
        session_id: id returned by acp_spawn.
        text: the next prompt.
        until_idle_seconds: drain ends when the child stays silent this
            long after producing at least one event (default 10s).
        max_wait_seconds: hard cap on wall-clock wait (default 180s).
        max_event_chars: per-event body cap (default 2048).

    Returns: JSON {"ok": true, "events": [...], "events_total": N,
                   "settled": true|false} or error envelope.
            ``settled`` is True iff the drain ended on the idle rule or
            on a clean child exit (not on the timeout backstop).
    """
    try:
        runtime = get_acpx_runtime()
        events = runtime.send(
            session_id, text,
            timeout_seconds=_coerce_positive_float(max_wait_seconds, 180.0),
            idle_seconds=_coerce_positive_float(until_idle_seconds, 10.0),
            startup_grace_seconds=2.0,
        )
        # Inspect the trailing synthetic event (if any) to tell the caller
        # whether the drain ended on the idle rule or on the timeout
        # backstop. Both are valid; only the idle rule guarantees the
        # child finished its turn cleanly.
        settled = False
        if events and isinstance(events[-1], dict):
            settled = events[-1].get("_synthetic") in ("idle", "child_exited")
        cap = int(max_event_chars) if max_event_chars and int(max_event_chars) > 0 else DEFAULT_MAX_EVENT_CHARS
        trimmed = trim_events(events[-64:], max_event_chars=cap)
        return _ok({
            "events": trimmed,
            "events_total": len(events),
            "settled": settled,
        })
    except AcpRuntimeError as e:
        return _err(e.message, code=e.code)
    except Exception as e:
        logger.exception("[acp_send_and_wait] unexpected error")
        return _err(str(e), code="EXCEPTION")


@tool
def acp_kill(session_id: str) -> str:
    """
    Terminate an ACP session and its child process. Always returns the
    session's transcript_path (when known) so the caller can cite it as
    evidence in downstream Exec Report rows.

    Returns: JSON {"ok": true, "killed": "<session_id>",
                   "transcript_path": "...", "agent_id": "...",
                   "pid": <int|null>} or error envelope.
    """
    try:
        runtime = get_acpx_runtime()
        record = runtime.kill(session_id)
        if record is None:
            # Best-effort fall back to the on-disk record so the LLM still
            # gets a transcript path it can hand to acp_transcript.
            on_disk = runtime.get_session_record(session_id)
            if on_disk is None:
                return _ok({"killed": session_id, "already_gone": True})
            return _ok({
                "killed": session_id,
                "already_gone": True,
                "transcript_path": on_disk.transcript_path,
                "agent_id": on_disk.agent_id,
                "pid": on_disk.pid,
            })
        return _ok({
            "killed": session_id,
            "transcript_path": record.transcript_path,
            "agent_id": record.agent_id,
            "pid": record.pid,
        })
    except AcpRuntimeError as e:
        return _err(e.message, code=e.code)
    except Exception as e:
        logger.exception("[acp_kill] unexpected error")
        return _err(str(e), code="EXCEPTION")


@tool
def acp_doctor() -> str:
    """
    Run a health probe of the ACPX runtime AND enumerate every registered
    ACP agent with its on-PATH resolvability and CLI version.

    Returns: JSON {"ok": <bool>, "message": "...",
                   "details": [{"agent_id","command","description",
                                "resolvable","cli_version"}, ...],
                   "probe": {"agent_id","stdout","stderr"}}.

    Note: ``ok`` reflects the probe outcome; ``details`` is now the
    per-agent enumeration so downstream "pick first non-X resolvable
    agent" logic can work off a single tool call.
    """
    try:
        runtime = get_acpx_runtime()
        runtime.probe_availability()
        report = runtime.doctor()
        return json.dumps({
            "ok": bool(report.get("ok")),
            "message": report.get("message", ""),
            "details": report.get("details", []),
            "probe": report.get("probe", {}),
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


@tool
def acp_list_sessions() -> str:
    """
    Enumerate live ACP sessions in this runtime with status metadata
    (alive, pid, transcript_size, agent_id, age_seconds, ...).

    Returns: JSON {"ok": true, "sessions": [{...}, ...], "count": N}.
    """
    try:
        runtime = get_acpx_runtime()
        sessions = runtime.list_sessions()
        return _ok({"sessions": sessions, "count": len(sessions)})
    except Exception as e:
        logger.exception("[acp_list_sessions] unexpected error")
        return _err(str(e), code="EXCEPTION")


@tool
def acp_session_status(session_id: str) -> str:
    """
    Return the current status of one ACP session.

    Returns: JSON {"ok": true, "session_id", "agent_id", "pid", "alive",
                   "transcript_path", "transcript_size", "last_event_at",
                   "closed"} or error envelope.
    """
    try:
        runtime = get_acpx_runtime()
        status = runtime.session_status(session_id)
        return _ok(status)
    except AcpRuntimeError as e:
        return _err(e.message, code=e.code)
    except Exception as e:
        logger.exception("[acp_session_status] unexpected error")
        return _err(str(e), code="EXCEPTION")


@tool
def acp_transcript(session_id: str, max_chars: int = 8000,
                   direction: str = "all") -> str:
    """
    Read the on-disk transcript for an ACP session. Use this to harvest
    the full conversation for hand-off, summarization, or evidence-citing
    in Exec Report rows — without resorting to execute_command tricks.

    Args:
        session_id: id returned by acp_spawn.
        max_chars: cap on the returned ``text`` field (default 8000).
            The full ``events`` list is always returned regardless.
        direction: ``"all"`` (default), ``"in"`` (child → Tlamatini), or
            ``"out"`` (Tlamatini → child).

    Returns: JSON {"ok": true, "session_id", "transcript_path", "events":
                   [{...}, ...], "text", "total_size", "truncated"} or
             error envelope.
    """
    try:
        runtime = get_acpx_runtime()
        result = runtime.read_transcript(
            session_id,
            max_chars=int(max_chars) if isinstance(max_chars, (int, float)) and max_chars >= 0 else 8000,
            direction=str(direction or "all").lower(),
        )
        return _ok(result)
    except AcpRuntimeError as e:
        return _err(e.message, code=e.code)
    except Exception as e:
        logger.exception("[acp_transcript] unexpected error")
        return _err(str(e), code="EXCEPTION")


@tool
def acp_relay(session_id_src: str, session_id_dst: str,
              transform: str = "last_assistant_text",
              prefix: str = "",
              suffix: str = "",
              until_idle_seconds: float = 10.0,
              max_wait_seconds: float = 180.0,
              max_event_chars: int = 0) -> str:
    """
    Hand off content from one ACP session to another in a single tool
    call. Reads the source transcript, extracts the relevant text per
    ``transform``, optionally wraps it with ``prefix`` / ``suffix``, and
    sends it as the next turn to ``session_id_dst`` — waiting for the
    destination to settle before returning.

    Args:
        session_id_src: id of the session whose output should be relayed.
        session_id_dst: id of the session that should receive the relay.
        transform: ``"last_assistant_text"`` (default; collects the
            assistant-side text from the source transcript) or
            ``"full_transcript"`` (raw transcript text).
        prefix / suffix: wrapping text (e.g. ``"Analysis: "`` / ``""``).
        until_idle_seconds: idle rule for the destination drain (default 10s).
        max_wait_seconds: hard cap on the destination drain (default 180s).
        max_event_chars: per-event body cap (default 2048).

    Returns: JSON {"ok": true, "session_id_src", "session_id_dst",
                   "transform", "relayed_chars", "preview", "events": [...],
                   "events_total", "settled"} or error envelope.
    """
    try:
        runtime = get_acpx_runtime()
        kind = str(transform or "last_assistant_text").strip().lower()
        if kind not in ("last_assistant_text", "full_transcript"):
            return _err(
                f"unknown transform '{transform}'; "
                "expected 'last_assistant_text' or 'full_transcript'",
                code="BAD_TRANSFORM",
            )
        src_dump = runtime.read_transcript(session_id_src, max_chars=0,
                                           direction="in")
        if kind == "last_assistant_text":
            payload = extract_last_assistant_text(src_dump.get("events") or [])
        else:
            payload = src_dump.get("text") or ""
        payload = payload.strip()
        if not payload:
            return _err(
                f"source session '{session_id_src}' produced no relayable text "
                f"(transform={kind})",
                code="EMPTY_RELAY",
            )
        message = (str(prefix) + payload + str(suffix)).strip()
        events = runtime.send(
            session_id_dst, message,
            timeout_seconds=_coerce_positive_float(max_wait_seconds, 180.0),
            idle_seconds=_coerce_positive_float(until_idle_seconds, 10.0),
            startup_grace_seconds=2.0,
        )
        settled = False
        if events and isinstance(events[-1], dict):
            settled = events[-1].get("_synthetic") in ("idle", "child_exited")
        cap = int(max_event_chars) if max_event_chars and int(max_event_chars) > 0 else DEFAULT_MAX_EVENT_CHARS
        trimmed = trim_events(events[-64:], max_event_chars=cap)
        # Preview is a truncated view of what we relayed, capped so the LLM
        # context isn't blown by re-pasting the full hand-off content.
        preview = message if len(message) <= 400 else message[:400] + "…"
        return _ok({
            "session_id_src": session_id_src,
            "session_id_dst": session_id_dst,
            "transform": kind,
            "relayed_chars": len(message),
            "preview": preview,
            "events": trimmed,
            "events_total": len(events),
            "settled": settled,
        })
    except AcpRuntimeError as e:
        return _err(e.message, code=e.code)
    except Exception as e:
        logger.exception("[acp_relay] unexpected error")
        return _err(str(e), code="EXCEPTION")


# ── Skills tools ──────────────────────────────────────────────────────
def _disabled_skill_names() -> set[str]:
    """
    Return the set of skill names whose Skill DB row has enabled=False.
    Best-effort: returns empty set on any failure so the tool surface
    degrades open (a broken admin layer never silently hides skills).
    The Skill DB table is the same toggle layer the ACPX-Skills menu
    writes to via the WebSocket `set-skills` channel.
    """
    try:
        from agent.models import Skill as SkillRow
        return {
            row.name for row in SkillRow.objects.filter(enabled=False).only("name")
        }
    except Exception:
        return set()


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
        disabled = _disabled_skill_names()
        if disabled:
            listing = [s for s in listing if s.get("name") not in disabled]
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
        if skill_name in _disabled_skill_names():
            return _err(
                f"skill '{skill_name}' is disabled in the ACPX-Skills "
                "Configure dialog; re-enable it to invoke",
                code="SKILL_DISABLED",
            )
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
