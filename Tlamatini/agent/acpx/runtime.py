"""
ACPX runtime — Python port of OpenClaw's BaseAcpxRuntime + AcpRuntime
(extensions/acpx/src/runtime.ts).

Lifecycle
---------
    1. AcpxRuntime is constructed once at Django startup by service.py.
    2. probe_availability() spawns the probe agent with --version to confirm
       at least one ACP CLI is reachable. is_healthy() reflects the result.
    3. spawn(agent_id, task, ...) creates an AcpSession that owns a child
       process. The session's lifetime is tracked in FileSessionStore.
    4. send(session_id, text) feeds a follow-up turn to an existing child.
    5. kill(session_id) terminates the child.
    6. doctor() returns a {ok, message, details[]} health report.

Transport
---------
For this revision, communication with the child is line-oriented JSON over
stdin/stdout — the standard ACP-over-stdio shape that all listed agents
support. Each turn sends one JSON line `{"task": "..."}` to stdin and
collects child stdout lines until either:
    - a JSON line with `"done": true` appears, OR
    - the child closes stdout, OR
    - timeout_ms elapses.

This is intentionally minimal. The full ACP protocol (capability discovery,
Permission events, tool-call relay, etc.) is the next step; the contract
is shaped so it can be added without changing the public surface.
"""
from __future__ import annotations

import json
import logging
import os
import subprocess
import threading
import time
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional

from .agent_registry import AcpAgentSpec, build_agent_registry
from .config import AcpxConfig, load_acpx_config, load_tlamatini_config_json
from .permissions import PermissionGate
from .session_store import (
    AcpSessionRecord,
    FileSessionStore,
    make_session_id,
    now_epoch,
)
from .windows_spawn import is_executable_resolvable, resolve_command

logger = logging.getLogger(__name__)


class AcpRuntimeError(Exception):
    """Mirrors OpenClaw's AcpRuntimeError. .code carries the error code."""
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


class AcpSession:
    """
    One ACP child-process session. Created via AcpxRuntime.spawn().

    Public methods
    --------------
    - send_turn(text) -> Iterator[dict]
    - close()
    - to_record() -> AcpSessionRecord
    """

    def __init__(self, *,
                 runtime: "AcpxRuntime",
                 spec: AcpAgentSpec,
                 cwd: Path,
                 mode: str,
                 record: AcpSessionRecord):
        self.runtime = runtime
        self.spec = spec
        self.cwd = cwd
        self.mode = mode
        self.record = record
        self.proc: Optional[subprocess.Popen] = None
        self._reader_lock = threading.Lock()

    # ── Lifecycle ────────────────────────────────────────────────────
    def spawn_child(self) -> None:
        resolved = resolve_command(self.spec.command)
        if not resolved.executable:
            raise AcpRuntimeError("AGENT_NOT_FOUND",
                                  f"agent '{self.spec.agent_id}': empty command")
        if not is_executable_resolvable(self.spec.command):
            # Surface a clean error instead of letting Popen raise raw.
            raise AcpRuntimeError(
                "AGENT_NOT_FOUND",
                f"agent '{self.spec.agent_id}' command '{self.spec.command}' "
                f"not found on PATH. Install it or override "
                f"acpx.agents.{self.spec.agent_id}.command in config.json.",
            )
        argv = [resolved.executable, *resolved.extra_args, *self.spec.args]
        env = {**os.environ, **self.spec.env}
        try:
            self.proc = subprocess.Popen(
                argv,
                cwd=str(self.cwd),
                env=env,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
                shell=resolved.use_shell,
            )
            self.record.pid = self.proc.pid
            self.record.last_active_at = now_epoch()
            self.runtime.session_store.save(self.record)
            logger.info("[ACPX] spawned %s (pid=%s) in %s",
                        self.spec.agent_id, self.proc.pid, self.cwd)
        except FileNotFoundError as e:
            raise AcpRuntimeError("AGENT_NOT_FOUND", str(e))
        except Exception as e:
            raise AcpRuntimeError("SPAWN_FAILED", str(e))

    def close(self) -> None:
        if self.proc is None:
            return
        try:
            try:
                self.proc.terminate()
                self.proc.wait(timeout=3)
            except Exception:
                try:
                    self.proc.kill()
                except Exception:
                    pass
        finally:
            self.record.closed = True
            self.record.last_active_at = now_epoch()
            self.runtime.session_store.save(self.record)
            logger.info("[ACPX] closed session %s (agent=%s pid=%s)",
                        self.record.session_id, self.spec.agent_id,
                        self.record.pid)

    # ── I/O ──────────────────────────────────────────────────────────
    def send_turn(self, text: str, timeout_seconds: float) -> Iterator[Dict[str, Any]]:
        """
        Send one ACP-over-stdio turn and yield events (dicts) until the
        child reports `done: true`, closes stdout, or timeout elapses.

        The yielded events are the raw JSON lines emitted by the child,
        plus one final {"done": True, "_synthetic": "<reason>"} event.
        Non-JSON lines from the child are wrapped as
        {"event": "log", "text": "<line>"}.
        """
        if self.proc is None or self.proc.stdin is None or self.proc.stdout is None:
            yield {"done": True, "_synthetic": "no_proc"}
            return

        with self._reader_lock:
            envelope = json.dumps({"task": text, "mode": self.mode}, ensure_ascii=False)
            try:
                self.proc.stdin.write(envelope + "\n")
                self.proc.stdin.flush()
            except Exception as e:
                yield {"done": True, "_synthetic": "stdin_write_failed",
                       "error": str(e)}
                return

            deadline = time.time() + max(1.0, float(timeout_seconds))
            transcript_path = Path(self.record.transcript_path)
            transcript_path.parent.mkdir(parents=True, exist_ok=True)
            with transcript_path.open("a", encoding="utf-8") as transcript:
                transcript.write(json.dumps({"direction": "out", "text": text,
                                             "ts": now_epoch()}) + "\n")
                while True:
                    if time.time() > deadline:
                        yield {"done": True, "_synthetic": "timeout"}
                        return
                    if self.proc.poll() is not None:
                        # Drain remaining stdout if any
                        for residual in (self.proc.stdout.readlines() or []):
                            ev = self._parse_line(residual)
                            transcript.write(
                                json.dumps({"direction": "in", "raw": residual,
                                            "ts": now_epoch()}) + "\n")
                            yield ev
                        yield {"done": True, "_synthetic": "child_exited",
                               "exit_code": self.proc.returncode}
                        return
                    line = self.proc.stdout.readline()
                    if not line:
                        time.sleep(0.05)
                        continue
                    ev = self._parse_line(line)
                    transcript.write(json.dumps({"direction": "in", "raw": line,
                                                 "ts": now_epoch()}) + "\n")
                    yield ev
                    if isinstance(ev, dict) and ev.get("done") is True:
                        return

    @staticmethod
    def _parse_line(line: str) -> Dict[str, Any]:
        s = line.rstrip("\n")
        if not s:
            return {"event": "log", "text": ""}
        try:
            obj = json.loads(s)
            if isinstance(obj, dict):
                return obj
            return {"event": "log", "text": s}
        except Exception:
            return {"event": "log", "text": s}

    def to_record(self) -> AcpSessionRecord:
        return self.record


class AcpxRuntime:
    """
    Singleton ACP runtime. One instance per Django process.
    """

    def __init__(self, *, config: Optional[AcpxConfig] = None):
        self.config = config or load_acpx_config(load_tlamatini_config_json())
        self.session_store = FileSessionStore(self.config.state_dir)
        self.agent_registry = build_agent_registry(self.config.agents)
        self.permission_gate = PermissionGate(
            self.config.permission_mode, self.config.non_interactive
        )
        self._sessions: Dict[str, AcpSession] = {}
        self._healthy: Optional[bool] = None
        self._last_doctor: Optional[Dict[str, Any]] = None

    # ── Health ────────────────────────────────────────────────────────
    def probe_availability(self) -> None:
        """
        Lightweight health probe. Tries to invoke the configured probe
        agent (or the first registered, healthy-looking one) with --version.
        Sets self._healthy.
        """
        target = self._pick_probe_agent()
        if target is None:
            self._healthy = False
            self._last_doctor = {
                "ok": False,
                "message": "no probe agent could be selected",
                "details": ["agent_registry empty or no resolvable command"],
            }
            return
        spec = self.agent_registry[target]
        if not is_executable_resolvable(spec.command):
            self._healthy = False
            self._last_doctor = {
                "ok": False,
                "message": f"probe agent '{target}' not on PATH",
                "details": [f"command={spec.command}"],
            }
            return
        try:
            res = subprocess.run(
                [resolve_command(spec.command).executable, "--version"],
                cwd=self.config.cwd or None,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=5,
                shell=resolve_command(spec.command).use_shell,
                text=True,
            )
            self._healthy = res.returncode == 0
            self._last_doctor = {
                "ok": self._healthy,
                "message": f"probe '{target}' --version exited {res.returncode}",
                "details": [
                    (res.stdout or "").strip()[:200],
                    (res.stderr or "").strip()[:200],
                ],
            }
        except subprocess.TimeoutExpired:
            self._healthy = False
            self._last_doctor = {
                "ok": False, "message": f"probe '{target}' timed out",
                "details": [],
            }
        except Exception as e:
            self._healthy = False
            self._last_doctor = {
                "ok": False, "message": f"probe '{target}' raised: {e}",
                "details": [],
            }

    def _pick_probe_agent(self) -> Optional[str]:
        if self.config.probe_agent and self.config.probe_agent in self.agent_registry:
            return self.config.probe_agent
        for agent_id, spec in self.agent_registry.items():
            if agent_id == "tlamatini":
                continue  # self-host shouldn't be the probe target
            if is_executable_resolvable(spec.command):
                return agent_id
        return None

    def is_healthy(self) -> bool:
        return bool(self._healthy)

    def doctor(self) -> Dict[str, Any]:
        if self._last_doctor is None:
            self.probe_availability()
        return self._last_doctor or {"ok": False, "message": "no doctor data",
                                     "details": []}

    # ── Spawn / send / kill ──────────────────────────────────────────
    def list_agents(self) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        for agent_id, spec in self.agent_registry.items():
            resolvable = is_executable_resolvable(spec.command)
            out.append({
                "agent_id": agent_id,
                "command": spec.command,
                "description": spec.description,
                "resolvable": resolvable,
            })
        return out

    def spawn(self, *, agent_id: str, task: str,
              cwd: Optional[str] = None,
              mode: str = "session",
              session_label: str = "") -> AcpSession:
        if agent_id not in self.agent_registry:
            raise AcpRuntimeError("UNKNOWN_AGENT",
                                  f"agent_id '{agent_id}' is not registered")
        spec = self.agent_registry[agent_id]

        # Permission gate on the spawn itself: spawn is a write-class action
        # because the child can do anything the user can. In approve-reads,
        # we still allow spawn (it's the equivalent of opening a shell), but
        # the child's *actions* are gated turn-by-turn.
        if self.config.permission_mode == "deny-all":
            raise AcpRuntimeError("PERMISSION_DENIED",
                                  "permission_mode=deny-all blocks all spawns")

        session_id = make_session_id()
        cwd_path = Path(cwd or self.config.cwd or os.getcwd()).resolve()
        cwd_path.mkdir(parents=True, exist_ok=True)
        transcript_path = (Path(self.config.state_dir) /
                           f"{session_id}.transcript.ndjson")
        record = AcpSessionRecord(
            session_id=session_id,
            name=session_label or f"{agent_id}-{session_id[:8]}",
            agent_id=agent_id,
            cwd=str(cwd_path),
            state_path=str(Path(self.config.state_dir) / f"{session_id}.json"),
            transcript_path=str(transcript_path),
            pid=None,
            created_at=now_epoch(),
            last_active_at=now_epoch(),
        )
        self.session_store.mark_fresh(session_id)
        self.session_store.save(record)
        session = AcpSession(
            runtime=self, spec=spec, cwd=cwd_path, mode=mode, record=record
        )
        session.spawn_child()
        # Send the initial task and consume a transcript chunk; we deliberately
        # don't wait for `done: true` here — the caller calls send/collect.
        self._sessions[session_id] = session
        return session

    def send(self, session_id: str, text: str,
             timeout_seconds: Optional[float] = None) -> List[Dict[str, Any]]:
        sess = self._sessions.get(session_id)
        if sess is None:
            raise AcpRuntimeError("UNKNOWN_SESSION",
                                  f"session '{session_id}' not found")
        timeout = float(timeout_seconds or self.config.timeout_seconds)
        events: List[Dict[str, Any]] = []
        for ev in sess.send_turn(text, timeout):
            events.append(ev)
            if ev.get("done"):
                break
        return events

    def kill(self, session_id: str) -> None:
        sess = self._sessions.pop(session_id, None)
        if sess is None:
            return
        sess.close()


# ── Singleton ─────────────────────────────────────────────────────────
_runtime_singleton: Optional[AcpxRuntime] = None
_runtime_lock = threading.Lock()


def get_acpx_runtime() -> AcpxRuntime:
    global _runtime_singleton
    if _runtime_singleton is None:
        with _runtime_lock:
            if _runtime_singleton is None:
                _runtime_singleton = AcpxRuntime()
    return _runtime_singleton
