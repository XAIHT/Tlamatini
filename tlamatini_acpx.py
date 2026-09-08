#!/usr/bin/env python3
# ═══════════════════════════════════════════════════════════════════
#   ✦  T L A M A T I N I  ✦   —   "one who knows"
#
#   Created by  Angela López Mendoza   ·   @angelahack1
#   Developer · Architect · Creator of Tlamatini
#
#   Every line of this file was written by Angela López Mendoza.
# ═══════════════════════════════════════════════════════════════════
#   Tlamatini Author Banner — do not remove (releases scrub the name automatically)
"""Self-contained ACPX runtime for the Tlamatini MCP server.

Brings the ACPX (Agent Communication Protocol eXtension) surface to an MCP
client (Claude Code, etc.) WITHOUT importing the Django app — it is a direct
port of the proven self-contained logic in
``Tlamatini/agent/agents/acpxer/acpxer.py`` (registry, command resolution,
transport-aware drain, oneshot-prompt capture) plus a small persistent-session
manager so follow-up turns / relay work across calls.

It spawns external coding-agent CLIs (claude / codex / cursor / gemini / qwen /
the tlamatini self-host / the tui-repl agents) as child processes, drains their
output, persists an NDJSON transcript per session, and exposes acp_* primitives.

Stdlib only (subprocess / threading / queue / json). ``psutil`` is used for a
clean tree-kill when present and degrades gracefully when absent.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
import uuid
from queue import Empty, Queue
from typing import Any, Dict, List, Optional, Tuple

# --------------------------------------------------------------------------- #
# ACPX agent registry mirror (kept in sync with agent/acpx/agent_registry.py
# and agent/agents/acpxer/acpxer.py)
# --------------------------------------------------------------------------- #
_DEFAULT_REGISTRY: Dict[str, Dict[str, Any]] = {
    # Oneshot-prompt agents (responses actually captured on Windows).
    "claude":    {"command": "claude", "transport": "oneshot-prompt",
                  "idle_s": 10.0, "timeout_s": 180.0, "grace_s": 2.0,
                  "prompt_flag": "-p", "prompt_subargs": []},
    "codex":     {"command": "codex", "transport": "oneshot-prompt",
                  "idle_s": 10.0, "timeout_s": 180.0, "grace_s": 2.0,
                  "prompt_flag": None, "prompt_subargs": ["exec"]},
    "cursor":    {"command": "cursor-agent", "transport": "oneshot-prompt",
                  "idle_s": 10.0, "timeout_s": 180.0, "grace_s": 2.0,
                  "prompt_flag": "-p", "prompt_subargs": []},
    "gemini":    {"command": "gemini", "transport": "oneshot-prompt",
                  "idle_s": 10.0, "timeout_s": 180.0, "grace_s": 2.0,
                  "prompt_flag": "-p", "prompt_subargs": []},
    "qwen":      {"command": "qwen-code", "transport": "oneshot-prompt",
                  "idle_s": 10.0, "timeout_s": 180.0, "grace_s": 2.0,
                  "prompt_flag": "-p", "prompt_subargs": []},
    # ACP-server self-host.
    "tlamatini": {"command": "python -m agent.acpx.self_acp_server",
                  "transport": "json-acp",
                  "idle_s": 6.0, "timeout_s": 45.0, "grace_s": 12.0,
                  "prompt_flag": None, "prompt_subargs": []},
    # Legacy TUI-REPLs (no known one-shot flag yet).
    "kiro":      {"command": "kiro", "transport": "tui-repl",
                  "idle_s": 2.0, "timeout_s": 8.0, "grace_s": 3.0,
                  "prompt_flag": None, "prompt_subargs": []},
    "kimi":      {"command": "kimi", "transport": "tui-repl",
                  "idle_s": 2.0, "timeout_s": 8.0, "grace_s": 3.0,
                  "prompt_flag": None, "prompt_subargs": []},
    "iflow":     {"command": "iflow", "transport": "tui-repl",
                  "idle_s": 2.0, "timeout_s": 8.0, "grace_s": 3.0,
                  "prompt_flag": None, "prompt_subargs": []},
    "kilocode":  {"command": "kilocode", "transport": "tui-repl",
                  "idle_s": 2.0, "timeout_s": 8.0, "grace_s": 3.0,
                  "prompt_flag": None, "prompt_subargs": []},
    "opencode":  {"command": "opencode", "transport": "tui-repl",
                  "idle_s": 2.0, "timeout_s": 8.0, "grace_s": 3.0,
                  "prompt_flag": None, "prompt_subargs": []},
    "pi":        {"command": "pi", "transport": "tui-repl",
                  "idle_s": 2.0, "timeout_s": 8.0, "grace_s": 3.0,
                  "prompt_flag": None, "prompt_subargs": []},
    "droid":     {"command": "droid", "transport": "tui-repl",
                  "idle_s": 2.0, "timeout_s": 8.0, "grace_s": 3.0,
                  "prompt_flag": None, "prompt_subargs": []},
    "copilot":   {"command": "copilot", "transport": "tui-repl",
                  "idle_s": 2.0, "timeout_s": 8.0, "grace_s": 3.0,
                  "prompt_flag": None, "prompt_subargs": []},
}

_CREATE_NO_WINDOW = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0


# --------------------------------------------------------------------------- #
# Shared child-health classifier + config.json overlay  (v1.51.2 port)
#
# Three fixes ported from Tlamatini/agent/acpx/ so this stdio surface stops
# lying the same way the Django one did:
#   1. config.json can retune a peer (args / transport / prompt flags / budgets
#      / env) instead of requiring an edit to this file and a redeploy;
#   2. doctor() can actually ASK an agent something (deep=True) instead of only
#      checking that a file exists on PATH -- measured 2026-09-07, all eight
#      installed CLIs passed a PATH/--version check while FOUR were dead;
#   3. a child that refused or produced nothing reports ok=False with a NAMED
#      code instead of a green success.
# --------------------------------------------------------------------------- #
_HERE = os.path.dirname(os.path.abspath(__file__))
_CHILD_HEALTH_PATH = os.path.join(_HERE, "Tlamatini", "agent", "acpx", "child_health.py")
_CONFIG_PATH = os.path.join(_HERE, "Tlamatini", "agent", "config.json")


def _load_child_health():
    """Load ``agent/acpx/child_health.py`` BY PATH -- ONE definition, never a copy.

    This module is deliberately Django-free, but child_health.py is stdlib-only
    and imports nothing from ``agent.*``, so it loads directly. Sharing it is the
    point: a second copy of a verdict vocabulary drifts, and a drifted copy
    mis-classifies silently -- the exact failure mode being repaired here.

    FAIL-OPEN: if the tree layout ever changes, classification degrades to the
    old behaviour ("everything delivered") and ``doctor()`` SAYS SO out loud
    instead of hiding the degradation.
    """
    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "tlamatini_child_health", _CHILD_HEALTH_PATH)
        if spec is None or spec.loader is None:
            return None, "no import spec for %s" % _CHILD_HEALTH_PATH
        module = importlib.util.module_from_spec(spec)
        sys.modules["tlamatini_child_health"] = module
        spec.loader.exec_module(module)
        return module, ""
    except Exception as exc:                                  # noqa: BLE001
        return None, repr(exc)


_CHILD_HEALTH, _CHILD_HEALTH_ERROR = _load_child_health()


def _classify(stdout, stderr, exit_code) -> Optional[Dict[str, Any]]:
    """Child-delivery verdict as a dict, or None when the classifier is absent."""
    if _CHILD_HEALTH is None:
        return None
    try:
        return _CHILD_HEALTH.classify_child_output(stdout, stderr, exit_code).as_dict()
    except Exception:                                         # noqa: BLE001
        return None


def _apply_verdict(payload: Dict[str, Any],
                   verdict: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Flip ``ok`` to False when the child demonstrably delivered nothing.

    The rest of the payload is preserved on the failure envelope on purpose: the
    caller still needs session_id / transcript_path to investigate and clean up.
    """
    if verdict and verdict.get("delivered") is False:
        payload["ok"] = False
        payload["code"] = verdict.get("code") or "NOT_DELIVERED"
        payload["reason"] = (verdict.get("failure_reason")
                             or "the agent produced no usable answer")
        if verdict.get("failure_evidence"):
            payload["evidence"] = verdict["failure_evidence"]
    return payload


_VALID_TRANSPORTS = ("oneshot-prompt", "tui-repl", "json-acp", "one-shot")
_SPEC_OVERRIDE_MAP = (
    ("transport", "transport", "transport"),
    ("args", "args", "list"),
    ("prompt_subcommand_args", "prompt_subargs", "list"),
    ("default_idle_seconds", "idle_s", "num"),
    ("default_startup_grace_seconds", "grace_s", "num"),
    ("default_timeout_seconds", "timeout_s", "num"),
)


def _build_registry() -> Dict[str, Dict[str, Any]]:
    """``_DEFAULT_REGISTRY`` overlaid with ``config.json``'s ``acpx.agents`` block.

    Mirrors ``agent_registry.build_agent_registry(spec_overrides=...)`` so ONE
    config edit repairs a peer on BOTH surfaces. FAIL-OPEN throughout: a missing
    or unreadable config, a malformed entry, a wrong-typed value, or a transport
    this runtime does not implement is dropped and the built-in value survives.
    """
    registry = {aid: dict(rec) for aid, rec in _DEFAULT_REGISTRY.items()}
    for rec in registry.values():
        rec.setdefault("args", [])
        rec.setdefault("env", {})
    try:
        with open(_CONFIG_PATH, encoding="utf-8-sig") as fh:
            agents = ((json.load(fh) or {}).get("acpx") or {}).get("agents") or {}
    except Exception:                                         # noqa: BLE001
        return registry
    if not isinstance(agents, dict):
        return registry
    for agent_id, spec in agents.items():
        if not isinstance(spec, dict):
            continue
        aid = str(agent_id)
        rec = registry.get(aid)
        if rec is None:
            rec = {"command": aid, "transport": "tui-repl", "idle_s": 2.0,
                   "timeout_s": 8.0, "grace_s": 3.0, "prompt_flag": None,
                   "prompt_subargs": [], "args": [], "env": {}}
            registry[aid] = rec
        command = spec.get("command")
        if isinstance(command, str) and command.strip():
            rec["command"] = command.strip()
        env = spec.get("env")
        if isinstance(env, dict):
            rec["env"] = {str(k): str(v) for k, v in env.items()}
        for src, dst, kind in _SPEC_OVERRIDE_MAP:
            if src not in spec:
                continue
            value = spec[src]
            if kind == "transport":
                if isinstance(value, str) and value in _VALID_TRANSPORTS:
                    rec["transport"] = value
            elif kind == "list":
                if isinstance(value, list):
                    rec[dst] = [str(item) for item in value]
            elif kind == "num":
                if (not isinstance(value, bool)
                        and isinstance(value, (int, float)) and float(value) > 0):
                    rec[dst] = float(value)
        # `null` is MEANINGFUL: codex takes its prompt positionally behind `exec`.
        if "prompt_arg_flag" in spec:
            flag = spec["prompt_arg_flag"]
            if flag is None:
                rec["prompt_flag"] = None
            elif isinstance(flag, str):
                rec["prompt_flag"] = flag.strip()
    return registry


_REGISTRY: Dict[str, Dict[str, Any]] = _build_registry()


def _child_env(rec: Dict[str, Any]) -> Optional[Dict[str, str]]:
    """``os.environ`` + the agent's configured env, or None when nothing is added.

    Before this port the stdio surface injected NOTHING, so an API key configured
    in ``acpx.agents.<id>.env`` never reached the child at all.
    """
    extra = rec.get("env") or {}
    if not extra:
        return None
    merged = dict(os.environ)
    merged.update({str(k): str(v) for k, v in extra.items()})
    return merged


def list_agent_ids() -> List[str]:
    return sorted(_REGISTRY.keys())


def resolve_command(agent_id: str, command_override: str = "") -> Dict[str, Any]:
    """Resolve a registry record for ``agent_id`` (optional command override)."""
    if agent_id in _REGISTRY:
        rec = dict(_REGISTRY[agent_id])
    else:
        rec = {"command": agent_id, "transport": "tui-repl",
               "idle_s": 2.0, "timeout_s": 8.0, "grace_s": 3.0,
               "prompt_flag": None, "prompt_subargs": [],
               "args": [], "env": {}}
    rec.setdefault("args", [])
    rec.setdefault("env", {})
    cmd_str = (command_override or rec["command"]).strip() or agent_id
    if sys.platform.startswith("win"):
        argv = cmd_str.split()
    else:
        import shlex
        argv = shlex.split(cmd_str)
    # Resolve argv[0] and decide whether it needs the shell. An npm/pnpm .cmd
    # shim is rewritten to the program it really launches whenever possible,
    # because cmd.exe truncates a multi-line prompt at the first newline. The
    # shell is the LAST resort, never the default. (agent/win_shim.py)
    if argv:
        prefix, needs_shell = _resolve_argv_prefix(argv[0])
        argv = list(prefix) + argv[1:]
    else:
        needs_shell = False
    rec["argv"] = argv
    rec["use_shell"] = bool(needs_shell)
    return rec


# Windows executable resolution -- ported from agent/acpx/windows_spawn.py.
#
# CreateProcess CANNOT run a .cmd/.bat shim directly, so a command like npm's
# `codex.cmd` must go through the shell. Before this, resolve_command() just
# split the string and Popen ran it with shell=False: measured 2026-09-07, that
# spawned NOTHING and hung for the full 180 s timeout instead of surfacing the
# error the same binary prints from a console.
#
# .exe comes FIRST on purpose. The old order tried .cmd before .exe, so a tool
# that ships BOTH (claude ships claude.exe next to a shim) was driven through
# the shell for no reason -- and the shell is the risky path, see below.
_WIN_EXTS = (".exe", ".com", ".cmd", ".bat")


# Windows command resolution has ONE definition: Tlamatini/agent/win_shim.py.
# It is stdlib-only and imports nothing from agent.*, so this Django-free
# module can load it the same way it loads child_health.py. A second copy
# would drift, and a drifted copy silently spawns the wrong thing.
_WIN_SHIM_PATH = os.path.join(_HERE, "Tlamatini", "agent", "win_shim.py")


def _load_win_shim():
    """Load the shared Windows-resolution module by path. FAIL-OPEN."""
    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "tlamatini_win_shim", _WIN_SHIM_PATH)
        if spec is None or spec.loader is None:
            return None, "no import spec for %s" % _WIN_SHIM_PATH
        module = importlib.util.module_from_spec(spec)
        sys.modules["tlamatini_win_shim"] = module
        spec.loader.exec_module(module)
        return module, ""
    except Exception as exc:                                  # noqa: BLE001
        return None, repr(exc)


_WIN_SHIM, _WIN_SHIM_ERROR = _load_win_shim()


def _resolve_argv_prefix(cmd: str) -> Tuple[List[str], bool]:
    """Return ``(argv_prefix, needs_shell)`` for a command string.

    Delegates to ``agent.win_shim.resolve_argv_prefix``: prefer a real .exe,
    rewrite an npm/pnpm .cmd shim to the program it actually launches, and
    only ask for the shell when neither is possible. cmd.exe truncates its
    command line at the first newline, so the shell must stay a last resort.

    FAIL-OPEN: with no shared module we keep the pre-fix behaviour (spawn the
    name as given, shell for a .cmd), and doctor() reports the degradation.
    """
    cmd = (cmd or "").strip()
    if not cmd:
        return [], False
    if _WIN_SHIM is not None:
        try:
            prefix, needs_shell, _why = _WIN_SHIM.resolve_argv_prefix(cmd)
            return list(prefix), bool(needs_shell)
        except Exception:                                     # noqa: BLE001
            pass
    return [cmd], cmd.lower().endswith((".cmd", ".bat"))


def _which(cmd: str) -> Optional[str]:
    """Absolute path of a command, or None. Used by doctor()/readiness."""
    prefix, _needs_shell = _resolve_argv_prefix(cmd)
    if not prefix:
        return None
    resolved = prefix[0]
    if resolved and (("/" in resolved) or ("\\" in resolved)):
        return resolved if os.path.exists(resolved) else None
    return None


# --------------------------------------------------------------------------- #
# Transcript writer (NDJSON, ACPX-compatible format)
# --------------------------------------------------------------------------- #
def _append_event(path: str, direction: str, text: str, raw: str = "") -> None:
    event = {"direction": direction, "text": text, "raw": raw or text, "ts": time.time()}
    try:
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")
    except Exception:
        pass


def extract_last_assistant_text(events: List[Dict[str, Any]]) -> str:
    assistant_chunks: List[str] = []
    log_chunks: List[str] = []
    for ev in events:
        text = (ev.get("text") or "").strip()
        if not text:
            continue
        ev_role = str(ev.get("role") or "").lower()
        ev_kind = str(ev.get("event") or "").lower()
        if ev_role in ("assistant", "model", "ai") or ev_kind in (
            "assistant_message", "assistant", "message", "completion", "answer"
        ):
            assistant_chunks.append(text)
            continue
        if str(ev.get("channel") or "").lower() == "stderr":
            continue
        try:
            payload = json.loads(text)
            role = (payload.get("role") or "").lower()
            kind = (payload.get("event") or "").lower()
            if role in ("assistant", "model", "ai") or kind in (
                "assistant_message", "assistant", "message", "completion", "answer"
            ):
                body = payload.get("text") or payload.get("content") or payload.get("message") or ""
                if isinstance(body, list):
                    body = "\n".join(str(b) for b in body)
                if body:
                    assistant_chunks.append(str(body))
                continue
        except (json.JSONDecodeError, ValueError, TypeError):
            pass
        if ev.get("direction") == "in":
            log_chunks.append(text)
    chosen = assistant_chunks if assistant_chunks else log_chunks
    return "\n".join(chosen).strip()


# --------------------------------------------------------------------------- #
# Transport-aware drain (port of acpxer.drain_session)
# --------------------------------------------------------------------------- #
def _reader_thread(stream, queue: "Queue") -> None:
    try:
        for line in iter(stream.readline, ""):
            if not line:
                break
            queue.put(line.rstrip("\r\n"))
    except Exception:
        pass
    finally:
        queue.put(None)


def _drain(process, queue: "Queue", reader: threading.Thread, transcript: str,
           transport: str, idle_s: float, timeout_s: float,
           grace_s: float) -> Tuple[List[Dict[str, Any]], str]:
    events: List[Dict[str, Any]] = []
    started_at = time.time()
    last_event_at = started_at
    settle_reason = "timeout"
    events_seen = 0
    while True:
        now = time.time()
        if now - started_at >= timeout_s:
            settle_reason = "timeout"
            break
        try:
            line = queue.get(timeout=0.1)
        except Empty:
            line = None
        if line is None:
            if not reader.is_alive() or process.poll() is not None:
                settle_reason = "child_exited"
                break
        else:
            events_seen += 1
            last_event_at = time.time()
            events.append({"direction": "in", "text": line, "raw": line, "ts": last_event_at})
            _append_event(transcript, "in", line)
            try:
                payload = json.loads(line)
                if isinstance(payload, dict) and payload.get("done") is True:
                    settle_reason = "done"
                    break
            except (json.JSONDecodeError, ValueError, TypeError):
                pass
            continue
        elapsed = now - started_at
        idle_for = now - last_event_at
        if transport == "json-acp":
            if events_seen > 0 and idle_for >= idle_s and elapsed >= grace_s:
                settle_reason = "idle"
                break
        else:
            if elapsed >= (grace_s + idle_s) and idle_for >= idle_s:
                settle_reason = "idle"
                break
    return events, settle_reason


def _run_oneshot(argv: List[str], prompt_flag, prompt_subargs: List[str],
                 task: str, cwd, transcript: str, timeout_s: float,
                 env: Optional[Dict[str, str]] = None,
                 extra_args: Optional[List[str]] = None,
                 use_shell: bool = False,
                 ) -> Tuple[List[Dict[str, Any]], str, Optional[Dict[str, Any]]]:
    # argv order mirrors agent/acpx/runtime.py::_oneshot_send_turn exactly:
    #   [exe, *args, *prompt_subcommand_args, prompt_flag, task]
    full_argv = list(argv) + list(extra_args or []) + list(prompt_subargs or [])
    flag = (prompt_flag or "").strip() if prompt_flag else ""
    if flag:
        full_argv.append(flag)
    full_argv.append(task)
    _append_event(transcript, "out", task,
                   raw=json.dumps({"argv": full_argv, "transport": "oneshot-prompt"}, ensure_ascii=False))
    shell_truncation_warning = ""
    if use_shell and "\n" in task:
        # We could not de-shim this command, so the prompt has to cross cmd.exe,
        # which stops at the first newline. Say so LOUDLY -- a silently truncated
        # prompt produces a confident answer to the wrong question.
        shell_truncation_warning = (
            "WARNING: %s is a shell shim that could not be rewritten to a direct "
            "command, and this prompt is multi-line. cmd.exe truncates the command "
            "line at the first newline, so the child may only have received the "
            "first line." % full_argv[0])
    try:
        process = subprocess.Popen(
            full_argv, cwd=cwd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace",
            creationflags=_CREATE_NO_WINDOW, env=env, shell=use_shell,
        )
    except FileNotFoundError:
        return ([{"event": "error", "text": f"command not on PATH: {full_argv[0]}",
                  "direction": "in"}], "command_not_found",
                {"delivered": False, "code": "AGENT_NOT_FOUND",
                 "failure_reason": f"command not on PATH: {full_argv[0]}"})
    except Exception as e:
        return ([{"event": "error", "text": str(e), "direction": "in"}], "spawn_failed",
                {"delivered": False, "code": "CHILD_ERROR",
                 "failure_reason": f"the child could not be spawned: {e}"})
    try:
        try:
            if process.stdin is not None:
                process.stdin.close()
        except Exception:
            pass
        try:
            stdout_text, stderr_text = process.communicate(timeout=timeout_s)
            settle = "child_exited"
        except subprocess.TimeoutExpired:
            try:
                process.kill()
            except Exception:
                pass
            try:
                stdout_text, stderr_text = process.communicate(timeout=5)
            except Exception:
                stdout_text, stderr_text = "", ""
            settle = "timeout"
    except Exception as e:
        return ([{"event": "error", "text": f"I/O failure: {e}", "direction": "in"}],
                "io_failed",
                {"delivered": False, "code": "CHILD_ERROR",
                 "failure_reason": f"I/O failure while draining the child: {e}"})
    stdout_text = stdout_text or ""
    stderr_text = stderr_text or ""
    events: List[Dict[str, Any]] = []
    if stdout_text.strip():
        _append_event(transcript, "in", stdout_text, raw=stdout_text)
        events.append({"direction": "in", "event": "assistant_message",
                       "role": "assistant", "text": stdout_text.strip()})
    if stderr_text.strip():
        _append_event(transcript, "in", stderr_text, raw=stderr_text)
        events.append({"direction": "in", "event": "log",
                       "channel": "stderr", "text": stderr_text.strip()})
    if not events:
        events.append({"direction": "in", "event": "log",
                       "text": f"(no output; exit_code={process.returncode})"})
    # An exit code is ONE BIT and it lies here: a child can report that its
    # web search was blocked for lack of permission and still exit 0. Ask what
    # it actually SAID -- agent/acpx/child_health.py, one shared definition.
    verdict = _classify(stdout_text, stderr_text, process.returncode)
    if shell_truncation_warning:
        events.insert(0, {"direction": "in", "event": "log",
                          "channel": "acpx", "text": shell_truncation_warning})
    return events, settle, verdict


def _kill_tree(process) -> None:
    if process is None:
        return
    try:
        import psutil
        try:
            parent = psutil.Process(process.pid)
        except psutil.NoSuchProcess:
            return
        for child in parent.children(recursive=True):
            try:
                child.terminate()
            except Exception:
                pass
        parent.terminate()
        _, alive = psutil.wait_procs([parent], timeout=3)
        for p in alive:
            try:
                p.kill()
            except Exception:
                pass
    except Exception:
        try:
            process.terminate()
        except Exception:
            pass


# --------------------------------------------------------------------------- #
# Session manager
# --------------------------------------------------------------------------- #
class AcpxManager:
    """Holds live ACPX sessions for the long-lived MCP server process."""

    def __init__(self, state_dir: str) -> None:
        self.state_dir = state_dir
        os.makedirs(state_dir, exist_ok=True)
        self._sessions: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.Lock()

    # -- helpers ----------------------------------------------------------- #
    def _transcript_path(self, session_id: str) -> str:
        return os.path.join(self.state_dir, f"{session_id}.transcript.ndjson")

    def _new_session_id(self, agent_id: str) -> str:
        return f"{agent_id}-{uuid.uuid4().hex[:12]}"

    # -- doctor / enumeration --------------------------------------------- #
    READINESS_PROMPT = "Reply with exactly this and nothing else: ACPX_READY"
    READINESS_CACHE_TTL_SECONDS = 600.0

    def readiness_probe(self, agent_id: str, timeout_seconds: float = 60.0,
                        use_cache: bool = True) -> Dict[str, Any]:
        """Actually ASK the agent something and report whether it answered.

        Being on PATH is not health. Measured 2026-09-07: all eight installed
        CLIs resolved and answered ``--version`` with exit 0 while FOUR were
        dead -- gemini could not authenticate, codex refused its own
        config.toml, claude had no credit, copilot printed nothing. A PATH check
        greenlit every one of them and a five-peer relay collapsed.

        Deliberately NOT run by default: a real prompt costs the user real
        quota. Results are cached for READINESS_CACHE_TTL_SECONDS.
        """
        rec = _REGISTRY.get(agent_id)
        if rec is None:
            return {"ready": False, "code": "UNKNOWN_AGENT", "probed": False,
                    "reason": f"no agent_id {agent_id!r} in the registry"}
        resolved = resolve_command(agent_id)
        exe = resolved["argv"][0] if resolved["argv"] else agent_id
        if not _which(exe):
            return {"ready": False, "code": "AGENT_NOT_FOUND", "probed": False,
                    "reason": f"command not on PATH: {exe}"}
        if resolved["transport"] != "oneshot-prompt":
            # A tui-repl / json-acp child needs a live session to answer, and
            # spawning one here would leak a process out of doctor(). Say so
            # plainly rather than inventing a verdict.
            return {"ready": None, "code": "NOT_PROBEABLE", "probed": False,
                    "reason": (f"transport {resolved['transport']!r} cannot be "
                               "probed without a session; use acp_spawn")}
        if _CHILD_HEALTH is None:
            return {"ready": None, "code": "CLASSIFIER_UNAVAILABLE", "probed": False,
                    "reason": ("child_health.py could not be loaded, so a probe "
                               "result cannot be judged: " + _CHILD_HEALTH_ERROR)}

        cache = self.__dict__.setdefault("_readiness", {})
        hit = cache.get(agent_id)
        now = time.time()
        if use_cache and hit and (now - hit[1]) < self.READINESS_CACHE_TTL_SECONDS:
            out = dict(hit[0])
            out["cached"] = True
            return out

        argv = (list(resolved["argv"]) + list(resolved.get("args") or [])
                + list(resolved.get("prompt_subargs") or []))
        flag = (resolved.get("prompt_flag") or "").strip() if resolved.get("prompt_flag") else ""
        if flag:
            argv.append(flag)
        argv.append(self.READINESS_PROMPT)
        try:
            res = subprocess.run(
                argv, cwd=None, env=_child_env(resolved),
                stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                stderr=subprocess.PIPE, text=True, encoding="utf-8",
                errors="replace", timeout=max(5.0, float(timeout_seconds)),
                creationflags=_CREATE_NO_WINDOW,
                shell=bool(resolved.get("use_shell")),
            )
            verdict = _CHILD_HEALTH.classify_child_output(
                res.stdout, res.stderr, res.returncode)
            out = _CHILD_HEALTH.summarize_for_doctor(verdict)
            out["exit_code"] = res.returncode
        except subprocess.TimeoutExpired:
            out = {"ready": False, "code": "PROBE_TIMEOUT", "evidence": "",
                   "reason": f"no answer within {timeout_seconds:.0f}s"}
        except Exception as exc:                              # noqa: BLE001
            out = {"ready": False, "code": "PROBE_FAILED", "evidence": "",
                   "reason": f"probe raised: {exc}"}
        out["probed"] = True
        out["cached"] = False
        cache[agent_id] = (dict(out), time.time())
        return out

    def doctor(self, agent_id: str = "", deep: bool = False,
               deep_timeout_seconds: float = 60.0) -> Dict[str, Any]:
        """Enumerate the ACP agents. ``resolvable`` is PATH, NOT health.

        Pass ``deep=True`` to additionally send each oneshot-prompt agent a real
        one-line prompt and get a per-agent ``readiness`` block naming the actual
        failure (AUTH_FAILED / CONFIG_INVALID / NO_CREDIT / USAGE_LIMIT /
        PERMISSION_BLOCKED / NO_OUTPUT / ...). It costs model quota, so it is
        opt-in and cached.
        """
        details = []
        ids = [agent_id] if agent_id else list_agent_ids()
        for aid in ids:
            rec = resolve_command(aid)
            exe = rec["argv"][0] if rec["argv"] else aid
            resolved = _which(exe)
            row = {
                "agent_id": aid,
                "command": rec["command"],
                "transport": rec["transport"],
                "resolvable": bool(resolved),
                "resolved_path": resolved or "",
            }
            if deep:
                row["readiness"] = self.readiness_probe(
                    aid, timeout_seconds=deep_timeout_seconds)
            details.append(row)
        n_ok = sum(1 for d in details if d["resolvable"])
        message = f"{n_ok}/{len(details)} agent(s) resolvable on PATH"
        if deep:
            ready = sum(1 for d in details
                        if (d.get("readiness") or {}).get("ready") is True)
            message += f"; {ready}/{len(details)} answered a live probe"
        else:
            message += (" (PATH only -- pass deep=true to find out which ones "
                        "actually answer)")
        if _CHILD_HEALTH is None:
            message += (" [WARNING: child_health.py unavailable, delivery "
                        "verdicts are DISABLED: " + _CHILD_HEALTH_ERROR + "]")
        return {"ok": True, "message": message, "details": details}

    def list_agents(self) -> Dict[str, Any]:
        return {"ok": True, "agents": [
            {"agent_id": aid, "transport": _REGISTRY[aid]["transport"],
             "command": _REGISTRY[aid]["command"]}
            for aid in list_agent_ids()
        ]}

    # -- spawn ------------------------------------------------------------- #
    def spawn(self, agent_id: str, task: str, cwd: str = "", mode: str = "session",
              command: str = "", timeout_seconds: float = 0, idle_seconds: float = 0,
              startup_grace_seconds: float = 0) -> Dict[str, Any]:
        agent_id = (agent_id or "claude").strip()
        task = (task or "").strip()
        cwd = (cwd or "").strip() or None
        rec = resolve_command(agent_id, command)
        argv = rec["argv"]
        transport = rec["transport"]
        idle_s = float(idle_seconds or 0) or rec["idle_s"]
        timeout_s = float(timeout_seconds or 0) or rec["timeout_s"]
        grace_s = float(startup_grace_seconds or 0) or rec["grace_s"]
        session_id = self._new_session_id(agent_id)
        transcript = self._transcript_path(session_id)
        try:
            open(transcript, "w").close()
        except Exception:
            pass
        if not task:
            return {"ok": False, "code": "NO_TASK", "reason": "task is empty",
                    "session_id": session_id, "agent_id": agent_id, "transport": transport}

        sess: Dict[str, Any] = {
            "session_id": session_id, "agent_id": agent_id, "transport": transport,
            "argv": argv, "prompt_flag": rec.get("prompt_flag"),
            "prompt_subargs": rec.get("prompt_subargs") or [], "cwd": cwd, "mode": mode,
            "args": rec.get("args") or [], "env": _child_env(rec), "verdict": None,
            "use_shell": bool(rec.get("use_shell")),
            "idle_s": idle_s, "timeout_s": timeout_s, "grace_s": grace_s,
            "transcript": transcript, "proc": None, "queue": None, "reader": None,
            "events": [], "last_assistant_text": "", "closed": False,
        }

        if transport == "oneshot-prompt":
            events, settle, verdict = _run_oneshot(
                argv, rec.get("prompt_flag"), rec.get("prompt_subargs") or [],
                task, cwd, transcript, timeout_s,
                env=_child_env(rec), extra_args=rec.get("args") or [],
                use_shell=bool(rec.get("use_shell")))
            sess["verdict"] = verdict
            sess["events"] = events
            sess["last_assistant_text"] = extract_last_assistant_text(events)
            with self._lock:
                self._sessions[session_id] = sess
            return self._spawn_result(sess, settle, events)

        # long-lived child (json-acp / tui-repl / one-shot)
        try:
            proc = subprocess.Popen(
                argv + list(rec.get("args") or []),
                cwd=cwd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT, text=True, bufsize=1, encoding="utf-8",
                errors="replace", creationflags=_CREATE_NO_WINDOW,
                env=_child_env(rec), shell=bool(rec.get("use_shell")),
            )
        except FileNotFoundError:
            return {"ok": False, "code": "AGENT_NOT_FOUND", "session_id": session_id,
                    "agent_id": agent_id, "transport": transport,
                    "reason": f"command '{argv[0]}' not resolvable on PATH"}
        except Exception as e:
            return {"ok": False, "code": "SPAWN_FAILED", "session_id": session_id,
                    "agent_id": agent_id, "transport": transport, "reason": str(e)}
        queue: "Queue" = Queue()
        reader = threading.Thread(target=_reader_thread, args=(proc.stdout, queue), daemon=True)
        reader.start()
        sess.update({"proc": proc, "queue": queue, "reader": reader})
        with self._lock:
            self._sessions[session_id] = sess
        # dispatch first turn + drain once
        events, settle = self._dispatch_and_drain(sess, task)
        return self._spawn_result(sess, settle, events)

    def _spawn_result(self, sess: Dict[str, Any], settle: str,
                      events: List[Dict[str, Any]]) -> Dict[str, Any]:
        ok = settle in ("done", "idle", "child_exited")
        return _apply_verdict({
            "ok": ok, "session_id": sess["session_id"], "agent_id": sess["agent_id"],
            "transport": sess["transport"], "transcript_path": sess["transcript"],
            "settle": settle, "events_total": len(events),
            "last_assistant_text": sess.get("last_assistant_text", ""),
            "events": _trim_events(events),
        }, sess.get("verdict"))

    # -- dispatch / send --------------------------------------------------- #
    def _dispatch_and_drain(self, sess: Dict[str, Any], text: str,
                            idle_s: float = 0, timeout_s: float = 0,
                            grace_s: float = 0) -> Tuple[List[Dict[str, Any]], str]:
        transport = sess["transport"]
        proc = sess["proc"]
        transcript = sess["transcript"]
        idle_s = idle_s or sess["idle_s"]
        timeout_s = timeout_s or sess["timeout_s"]
        grace_s = grace_s or sess["grace_s"]
        try:
            envelope = {"task": text, "mode": sess["mode"]}
            line = json.dumps(envelope) + "\n" if transport == "json-acp" else text + "\n"
            _append_event(transcript, "out", line.rstrip("\r\n"))
            proc.stdin.write(line)
            proc.stdin.flush()
            if sess["mode"] == "one-shot" or transport == "one-shot":
                try:
                    proc.stdin.close()
                except Exception:
                    pass
        except Exception as e:
            return ([{"direction": "in", "event": "error", "text": f"dispatch failed: {e}"}],
                    "dispatch_failed")
        events, settle = _drain(proc, sess["queue"], sess["reader"], transcript,
                                transport, idle_s, timeout_s, grace_s)
        sess["events"].extend(events)
        last = extract_last_assistant_text(events)
        if last:
            sess["last_assistant_text"] = last
        return events, settle

    def send(self, session_id: str, text: str, timeout_seconds: float = 0,
             idle_seconds: float = 0, startup_grace_seconds: float = 0) -> Dict[str, Any]:
        sess = self._sessions.get(session_id)
        if not sess:
            return {"ok": False, "code": "NO_SESSION", "reason": f"unknown session {session_id!r}"}
        if sess["closed"]:
            return {"ok": False, "code": "SESSION_CLOSED", "reason": "session already killed"}
        text = (text or "").strip()
        if sess["transport"] == "oneshot-prompt":
            # stateless: re-spawn a fresh process with the new prompt
            events, settle, verdict = _run_oneshot(
                sess["argv"], sess.get("prompt_flag"),
                sess.get("prompt_subargs") or [], text,
                sess["cwd"], sess["transcript"],
                float(timeout_seconds or 0) or sess["timeout_s"],
                env=sess.get("env"), extra_args=sess.get("args") or [],
                use_shell=bool(sess.get("use_shell")))
            sess["events"].extend(events)
            last = extract_last_assistant_text(events)
            if last:
                sess["last_assistant_text"] = last
            return _apply_verdict(
                {"ok": settle == "child_exited" and bool(last),
                 "session_id": session_id,
                 "agent_id": sess["agent_id"], "transport": sess["transport"],
                 "settle": settle, "events_total": len(events),
                 "last_assistant_text": last, "events": _trim_events(events)},
                verdict)
        events, settle = self._dispatch_and_drain(sess, text, idle_seconds,
                                                  timeout_seconds, startup_grace_seconds)
        return {"ok": settle in ("done", "idle", "child_exited"), "session_id": session_id,
                "agent_id": sess["agent_id"], "transport": sess["transport"],
                "settle": settle, "events_total": len(events),
                "last_assistant_text": extract_last_assistant_text(events),
                "events": _trim_events(events)}

    def send_and_wait(self, session_id: str, text: str, until_idle_seconds: float = 10,
                      max_wait_seconds: float = 180) -> Dict[str, Any]:
        res = self.send(session_id, text, timeout_seconds=max_wait_seconds,
                        idle_seconds=until_idle_seconds)
        res["settled"] = res.get("settle") in ("done", "idle", "child_exited")
        return res

    # -- relay ------------------------------------------------------------- #
    def relay(self, session_id_src: str, session_id_dst: str,
              transform: str = "last_assistant_text", prefix: str = "", suffix: str = "",
              until_idle_seconds: float = 10, max_wait_seconds: float = 180) -> Dict[str, Any]:
        src = self._sessions.get(session_id_src)
        if not src:
            return {"ok": False, "code": "NO_SESSION", "reason": f"unknown src {session_id_src!r}"}
        if transform == "full_transcript":
            payload = self.transcript(session_id_src, max_chars=20000).get("text", "")
        else:
            payload = src.get("last_assistant_text", "")
        body = f"{prefix}{payload}{suffix}"
        res = self.send_and_wait(session_id_dst, body, until_idle_seconds, max_wait_seconds)
        res["relayed_chars"] = len(payload)
        return res

    # -- reads ------------------------------------------------------------- #
    def transcript(self, session_id: str, max_chars: int = 8000,
                   direction: str = "all") -> Dict[str, Any]:
        sess = self._sessions.get(session_id)
        if not sess:
            return {"ok": False, "code": "NO_SESSION", "reason": f"unknown session {session_id!r}"}
        path = sess["transcript"]
        lines: List[Dict[str, Any]] = []
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                for raw in f:
                    raw = raw.strip()
                    if not raw:
                        continue
                    try:
                        ev = json.loads(raw)
                    except Exception:
                        continue
                    if direction in ("in", "out") and ev.get("direction") != direction:
                        continue
                    lines.append(ev)
        except FileNotFoundError:
            return {"ok": False, "code": "NO_TRANSCRIPT", "reason": "no transcript yet",
                    "transcript_path": path}
        text = "\n".join(ev.get("text", "") for ev in lines)
        truncated = len(text) > max_chars
        if truncated:
            text = text[-max_chars:]
        return {"ok": True, "session_id": session_id, "events": lines, "text": text,
                "truncated": truncated, "transcript_path": path}

    def session_status(self, session_id: str) -> Dict[str, Any]:
        sess = self._sessions.get(session_id)
        if not sess:
            return {"ok": False, "code": "NO_SESSION", "reason": f"unknown session {session_id!r}"}
        proc = sess["proc"]
        alive = bool(proc and proc.poll() is None)
        return {"ok": True, "session_id": session_id, "agent_id": sess["agent_id"],
                "transport": sess["transport"], "alive": alive, "closed": sess["closed"],
                "events_total": len(sess["events"]),
                "last_assistant_text": sess.get("last_assistant_text", "")}

    def list_sessions(self) -> Dict[str, Any]:
        out = []
        for sid, sess in self._sessions.items():
            proc = sess["proc"]
            out.append({"session_id": sid, "agent_id": sess["agent_id"],
                        "transport": sess["transport"],
                        "alive": bool(proc and proc.poll() is None),
                        "closed": sess["closed"]})
        return {"ok": True, "sessions": out}

    # -- kill -------------------------------------------------------------- #
    def kill(self, session_id: str) -> Dict[str, Any]:
        sess = self._sessions.get(session_id)
        if not sess:
            return {"ok": False, "code": "NO_SESSION", "reason": f"unknown session {session_id!r}"}
        proc = sess["proc"]
        pid = proc.pid if proc else None
        _kill_tree(proc)
        sess["closed"] = True
        return {"ok": True, "killed": True, "session_id": session_id,
                "agent_id": sess["agent_id"], "pid": pid,
                "transcript_path": sess["transcript"]}


def _trim_events(events: List[Dict[str, Any]], max_chars: int = 6000) -> List[Dict[str, Any]]:
    trimmed = []
    for ev in events:
        e = dict(ev)
        t = e.get("text") or ""
        if len(t) > max_chars:
            e["text"] = t[:max_chars] + "…(trimmed)…"
        e.pop("raw", None)
        trimmed.append(e)
    return trimmed
