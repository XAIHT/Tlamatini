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


def list_agent_ids() -> List[str]:
    return sorted(_DEFAULT_REGISTRY.keys())


def resolve_command(agent_id: str, command_override: str = "") -> Dict[str, Any]:
    """Resolve a registry record for ``agent_id`` (optional command override)."""
    if agent_id in _DEFAULT_REGISTRY:
        rec = dict(_DEFAULT_REGISTRY[agent_id])
    else:
        rec = {"command": agent_id, "transport": "tui-repl",
               "idle_s": 2.0, "timeout_s": 8.0, "grace_s": 3.0,
               "prompt_flag": None, "prompt_subargs": []}
    cmd_str = (command_override or rec["command"]).strip() or agent_id
    if sys.platform.startswith("win"):
        argv = cmd_str.split()
    else:
        import shlex
        argv = shlex.split(cmd_str)
    rec["argv"] = argv
    return rec


def _which(cmd: str) -> Optional[str]:
    import shutil
    found = shutil.which(cmd)
    if found:
        return found
    if sys.platform.startswith("win"):
        for ext in (".cmd", ".exe", ".bat"):
            found = shutil.which(cmd + ext)
            if found:
                return found
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
                 task: str, cwd, transcript: str, timeout_s: float) -> Tuple[List[Dict[str, Any]], str]:
    full_argv = list(argv) + list(prompt_subargs or [])
    flag = (prompt_flag or "").strip() if prompt_flag else ""
    if flag:
        full_argv.append(flag)
    full_argv.append(task)
    _append_event(transcript, "out", task,
                   raw=json.dumps({"argv": full_argv, "transport": "oneshot-prompt"}, ensure_ascii=False))
    try:
        process = subprocess.Popen(
            full_argv, cwd=cwd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace",
            creationflags=_CREATE_NO_WINDOW,
        )
    except FileNotFoundError:
        return ([{"event": "error", "text": f"command not on PATH: {full_argv[0]}",
                  "direction": "in"}], "command_not_found")
    except Exception as e:
        return ([{"event": "error", "text": str(e), "direction": "in"}], "spawn_failed")
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
        return ([{"event": "error", "text": f"I/O failure: {e}", "direction": "in"}], "io_failed")
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
    return events, settle


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
    def doctor(self, agent_id: str = "") -> Dict[str, Any]:
        details = []
        ids = [agent_id] if agent_id else list_agent_ids()
        for aid in ids:
            rec = resolve_command(aid)
            exe = rec["argv"][0] if rec["argv"] else aid
            resolved = _which(exe)
            details.append({
                "agent_id": aid,
                "command": rec["command"],
                "transport": rec["transport"],
                "resolvable": bool(resolved),
                "resolved_path": resolved or "",
            })
        n_ok = sum(1 for d in details if d["resolvable"])
        return {"ok": True, "message": f"{n_ok}/{len(details)} agent(s) resolvable on PATH",
                "details": details}

    def list_agents(self) -> Dict[str, Any]:
        return {"ok": True, "agents": [
            {"agent_id": aid, "transport": _DEFAULT_REGISTRY[aid]["transport"],
             "command": _DEFAULT_REGISTRY[aid]["command"]}
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
            "idle_s": idle_s, "timeout_s": timeout_s, "grace_s": grace_s,
            "transcript": transcript, "proc": None, "queue": None, "reader": None,
            "events": [], "last_assistant_text": "", "closed": False,
        }

        if transport == "oneshot-prompt":
            events, settle = _run_oneshot(argv, rec.get("prompt_flag"),
                                          rec.get("prompt_subargs") or [], task, cwd,
                                          transcript, timeout_s)
            sess["events"] = events
            sess["last_assistant_text"] = extract_last_assistant_text(events)
            with self._lock:
                self._sessions[session_id] = sess
            return self._spawn_result(sess, settle, events)

        # long-lived child (json-acp / tui-repl / one-shot)
        try:
            proc = subprocess.Popen(
                argv, cwd=cwd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT, text=True, bufsize=1, encoding="utf-8",
                errors="replace", creationflags=_CREATE_NO_WINDOW,
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
        return {
            "ok": ok, "session_id": sess["session_id"], "agent_id": sess["agent_id"],
            "transport": sess["transport"], "transcript_path": sess["transcript"],
            "settle": settle, "events_total": len(events),
            "last_assistant_text": sess.get("last_assistant_text", ""),
            "events": _trim_events(events),
        }

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
            events, settle = _run_oneshot(sess["argv"], sess.get("prompt_flag"),
                                          sess.get("prompt_subargs") or [], text,
                                          sess["cwd"], sess["transcript"],
                                          float(timeout_seconds or 0) or sess["timeout_s"])
            sess["events"].extend(events)
            last = extract_last_assistant_text(events)
            if last:
                sess["last_assistant_text"] = last
            return {"ok": settle == "child_exited" and bool(last), "session_id": session_id,
                    "agent_id": sess["agent_id"], "transport": sess["transport"],
                    "settle": settle, "events_total": len(events),
                    "last_assistant_text": last, "events": _trim_events(events)}
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
