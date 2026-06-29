# ═══════════════════════════════════════════════════════════════════
#   ✦  T L A M A T I N I  ✦   —   "one who knows"
#
#   Created by  Angela López Mendoza   ·   @angelahack1
#   Developer · Architect · Creator of Tlamatini
#
#   Every line of this file was written by Angela López Mendoza.
# ═══════════════════════════════════════════════════════════════════
#   Tlamatini Author Banner — do not remove (releases scrub the name automatically)
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
import queue
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


def _kill_process_tree(proc) -> None:
    """Kill ``proc`` and every descendant it spawned.

    Why: CLI wrappers like ``claude`` / ``cursor-agent`` / ``gemini``
    typically shell out to node.exe or a helper.exe; killing only the
    top-level Popen handle leaves the helper alive and its conhost.exe
    orphaned with our icon. We escalate from terminate → kill on each
    descendant and finally on the parent.
    """
    if proc is None:
        return
    pid = getattr(proc, "pid", None)
    descendants = []
    try:
        import psutil  # local import: optional dep
        try:
            parent = psutil.Process(pid)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            parent = None
        if parent is not None:
            try:
                descendants = parent.children(recursive=True)
            except Exception:  # noqa: BLE001
                descendants = []
            for child in descendants:
                try:
                    child.terminate()
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
                except Exception:  # noqa: BLE001
                    pass
            psutil.wait_procs(descendants, timeout=2)
            for child in descendants:
                if child.is_running():
                    try:
                        child.kill()
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        pass
                    except Exception:  # noqa: BLE001
                        pass
    except ImportError:
        pass
    except Exception as exc:  # noqa: BLE001
        logger.debug("[ACPX] _kill_process_tree(pid=%s) descendant sweep failed: %s",
                     pid, exc)
    try:
        proc.terminate()
        try:
            proc.wait(timeout=2)
        except Exception:  # noqa: BLE001
            pass
    except Exception:  # noqa: BLE001
        pass
    if proc.poll() is None:
        try:
            proc.kill()
        except Exception:  # noqa: BLE001
            pass


def _windows_creationflags() -> int:
    """Suppress conhost.exe orphans for every ACPX child on Windows.

    Why: Tlamatini's child Python agents run with DETACHED_PROCESS / no
    console attached. When THAT process calls Popen without
    CREATE_NO_WINDOW, Windows allocates a brand-new console for the
    child — which leaves a conhost.exe behind even after the child
    exits. Stacking CREATE_NO_WINDOW + CREATE_NEW_PROCESS_GROUP gives us
    both no-window guarantees and the ability to send Ctrl+Break-style
    signals to the group without bleeding into our own console.
    """
    if os.name != "nt":
        return 0
    return subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP


# ── Event trimming ─────────────────────────────────────────────────────
# Cap each event body so a chatty REPL (e.g. gemini paste-back of a long
# document) cannot blow the LLM context on the next iteration. The trim
# is structural: only a fixed set of payload keys is shortened, the
# event envelope (event/role/done/etc.) is preserved verbatim.
_EVENT_BODY_KEYS = ("text", "content", "message", "raw", "delta", "data")
DEFAULT_MAX_EVENT_CHARS = 2048


def trim_event_payload(event: Dict[str, Any],
                       max_event_chars: int = DEFAULT_MAX_EVENT_CHARS,
                       ) -> Dict[str, Any]:
    """Return a copy of `event` with each known body key truncated to
    `max_event_chars`. Adds ``event["_truncated"] = True`` if anything
    was clipped."""
    if not isinstance(event, dict) or max_event_chars <= 0:
        return event
    out = dict(event)
    truncated = False
    for key in _EVENT_BODY_KEYS:
        v = out.get(key)
        if isinstance(v, str) and len(v) > max_event_chars:
            out[key] = v[:max_event_chars]
            truncated = True
    if truncated:
        out["_truncated"] = True
    return out


def trim_events(events: List[Dict[str, Any]],
                max_event_chars: int = DEFAULT_MAX_EVENT_CHARS,
                ) -> List[Dict[str, Any]]:
    """Apply :func:`trim_event_payload` to every event in `events`."""
    if not events:
        return events
    return [trim_event_payload(e, max_event_chars) for e in events]


# ── Last-assistant extraction ──────────────────────────────────────────
# Used by acp_relay to hand off output from one ACP child to another.
# Heuristic, because non-JSON-ACP REPLs (gemini/cursor/qwen/codex) just
# stream plain log lines without role markers. The strategy is:
#   1. If any event has role=='assistant' or event=='assistant_message',
#      collect ONLY those events' text/content/message fields.
#   2. Otherwise, fall back to all event=='log' text bodies (this is the
#      common case for the bundled CLIs).
# Empty/whitespace-only payloads are dropped. The result is the joined
# string, trimmed.
_ASSISTANT_ROLE_VALUES = ("assistant", "model", "ai")
_ASSISTANT_EVENT_VALUES = ("assistant_message", "assistant", "message",
                           "completion", "answer")


def _event_text(ev: Dict[str, Any]) -> str:
    if not isinstance(ev, dict):
        return ""
    for key in ("content", "text", "message", "raw", "delta", "data"):
        v = ev.get(key)
        if isinstance(v, str) and v.strip():
            return v
    return ""


def extract_last_assistant_text(events: List[Dict[str, Any]]) -> str:
    """Extract the assistant-side text from a list of ACP events. See
    module docstring for the heuristic."""
    if not events:
        return ""
    role_hits: List[str] = []
    log_hits: List[str] = []
    for ev in events:
        if not isinstance(ev, dict):
            continue
        role = str(ev.get("role") or "").lower()
        kind = str(ev.get("event") or "").lower()
        text = _event_text(ev)
        if not text:
            continue
        if role in _ASSISTANT_ROLE_VALUES or kind in _ASSISTANT_EVENT_VALUES:
            role_hits.append(text)
        elif kind == "log" or kind == "":
            log_hits.append(text)
    chosen = role_hits if role_hits else log_hits
    return "\n".join(s.rstrip() for s in chosen if s.strip()).strip()


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
        # Cross-platform non-blocking line reader. The blocking
        # `proc.stdout.readline()` we used to call inside the drain loop
        # could not be interrupted on Windows even when the parent had
        # already concluded the turn was idle — so a TUI REPL that
        # produced zero events would burn the full timeout every time.
        # A daemon thread now pumps stdout lines into a Queue, and the
        # drain loop reads from the queue with a short timeout. The
        # thread terminates when stdout closes (process exit).
        self._stdout_queue: "queue.Queue[Optional[str]]" = queue.Queue()
        self._stdout_reader: Optional[threading.Thread] = None

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
        # ``oneshot-prompt`` does NOT keep a long-lived child. Each
        # send_turn re-spawns the CLI with the prompt as a CLI arg, so
        # the spawn step here is a no-op aside from recording the
        # session as "alive logically" so list_sessions / kill behave
        # consistently. The actual capture happens in
        # _oneshot_send_turn.
        if self.spec.transport == "oneshot-prompt":
            self.proc = None
            self.record.last_active_at = now_epoch()
            self.runtime.session_store.save(self.record)
            logger.info("[ACPX] logical session %s ready (agent=%s, "
                        "transport=oneshot-prompt, no persistent child)",
                        self.record.session_id, self.spec.agent_id)
            return
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
                creationflags=_windows_creationflags(),
            )
            self.record.pid = self.proc.pid
            self.record.last_active_at = now_epoch()
            self.runtime.session_store.save(self.record)
            logger.info("[ACPX] spawned %s (pid=%s, transport=%s) in %s",
                        self.spec.agent_id, self.proc.pid,
                        self.spec.transport, self.cwd)
            # Start the daemon reader so subsequent send_turn drains
            # don't block on readline().
            self._start_stdout_reader()
        except FileNotFoundError as e:
            raise AcpRuntimeError("AGENT_NOT_FOUND", str(e))
        except Exception as e:
            raise AcpRuntimeError("SPAWN_FAILED", str(e))

    def _start_stdout_reader(self) -> None:
        if self.proc is None or self.proc.stdout is None:
            return
        if self._stdout_reader is not None and self._stdout_reader.is_alive():
            return
        stdout = self.proc.stdout

        def _pump() -> None:
            try:
                for line in iter(stdout.readline, ""):
                    if line == "":
                        break
                    self._stdout_queue.put(line)
            except Exception as e:  # noqa: BLE001
                logger.debug("[ACPX] stdout reader exit (%s): %s",
                             self.record.session_id, e)
            finally:
                # Sentinel so the drain loop knows the stream closed.
                self._stdout_queue.put(None)

        t = threading.Thread(target=_pump, daemon=True,
                             name=f"acpx-reader-{self.record.session_id[:8]}")
        t.start()
        self._stdout_reader = t

    def close(self) -> None:
        if self.proc is None:
            # oneshot-prompt or never-spawned: just mark closed.
            self.record.closed = True
            self.record.last_active_at = now_epoch()
            self.runtime.session_store.save(self.record)
            logger.info("[ACPX] closed logical session %s (agent=%s)",
                        self.record.session_id, self.spec.agent_id)
            return
        try:
            # Tree-kill: terminate the child AND every descendant it
            # spawned (CLI wrappers like ``claude`` often launch a
            # node.exe/cmd.exe helper that owns its own conhost). Only
            # killing self.proc leaves the helper + conhost orphaned.
            _kill_process_tree(self.proc)
        finally:
            self.record.closed = True
            self.record.last_active_at = now_epoch()
            self.runtime.session_store.save(self.record)
            logger.info("[ACPX] closed session %s (agent=%s pid=%s)",
                        self.record.session_id, self.spec.agent_id,
                        self.record.pid)

    # ── I/O ──────────────────────────────────────────────────────────
    def send_turn(self, text: str, timeout_seconds: float,
                  idle_seconds: float = 6.0,
                  startup_grace_seconds: float = 12.0) -> Iterator[Dict[str, Any]]:
        """
        Send one turn and yield events until completion. Completion fires
        on the FIRST of these conditions:

          1. The child emits a JSON line with ``"done": true`` (strict ACP).
          2. The child closes stdout (process exit).
          3. ``timeout_seconds`` elapses (hard backstop).
          4. The idle rule fires:
             - For ``transport="json-acp"``: the child has produced at
               least one event AND has been silent for ``idle_seconds``
               AND we are past ``startup_grace_seconds``.
             - For ``transport="tui-repl"`` and ``"one-shot"``: the child
               has been silent for ``idle_seconds`` AND we are past
               ``startup_grace_seconds`` — even with **zero events**.

        For ``transport="oneshot-prompt"``, the entire model is
        different: each turn re-spawns the CLI with the prompt as a CLI
        argument behind ``spec.prompt_arg_flag``, closes stdin
        immediately, and captures the full stdout to EOF. This is
        delegated to :meth:`_oneshot_send_turn`. It is the ONLY
        transport that reliably captures responses from TUI agents
        (claude / gemini / cursor / qwen) on Windows.

        The transport-aware idle rule on the legacy path is what
        unhangs ``tui-repl`` agents that produce zero events: they used
        to burn the full ``timeout_seconds`` on every spawn (~45 s);
        now they return within
        ``startup_grace_seconds + idle_seconds`` (default ~5 s).

        The drain reads from a ``queue.Queue`` populated by a daemon
        reader thread instead of calling blocking ``readline()`` inline.
        This keeps the loop responsive on Windows where ``readline()`` on
        a pipe cannot be interrupted by a signal.
        """
        if self.spec.transport == "oneshot-prompt":
            yield from self._oneshot_send_turn(text, timeout_seconds)
            return
        if self.proc is None or self.proc.stdin is None or self.proc.stdout is None:
            yield {"done": True, "_synthetic": "no_proc"}
            return

        with self._reader_lock:
            envelope = json.dumps({"task": text, "mode": self.mode}, ensure_ascii=False)
            try:
                self.proc.stdin.write(envelope + "\n")
                self.proc.stdin.flush()
                # For one-shot transports, close stdin so the child
                # observes EOF and proceeds to its single turn.
                if self.spec.transport == "one-shot":
                    try:
                        self.proc.stdin.close()
                    except Exception:
                        pass
            except Exception as e:
                yield {"done": True, "_synthetic": "stdin_write_failed",
                       "error": str(e)}
                return

            transport = self.spec.transport or "tui-repl"
            requires_event_for_idle = (transport == "json-acp")

            started_at = time.time()
            deadline = started_at + max(1.0, float(timeout_seconds))
            last_event_at: Optional[float] = None
            event_count = 0
            stream_closed = False
            transcript_path = Path(self.record.transcript_path)
            transcript_path.parent.mkdir(parents=True, exist_ok=True)
            with transcript_path.open("a", encoding="utf-8") as transcript:
                transcript.write(json.dumps({"direction": "out", "text": text,
                                             "ts": now_epoch()}) + "\n")
                transcript.flush()
                while True:
                    now = time.time()
                    if now > deadline:
                        yield {"done": True, "_synthetic": "timeout",
                               "events_seen": event_count,
                               "transport": transport}
                        return

                    # Idle-rule completion. The transport-aware variant is
                    # what unhangs TUI REPLs that produce zero output.
                    past_grace = (now - started_at) >= startup_grace_seconds
                    silent_long_enough = (
                        last_event_at is None
                        and past_grace
                        and (now - started_at) >= (startup_grace_seconds + idle_seconds)
                    ) or (
                        last_event_at is not None
                        and (now - last_event_at) >= idle_seconds
                        and past_grace
                    )
                    if silent_long_enough and (
                        not requires_event_for_idle or event_count > 0
                    ):
                        yield {"done": True, "_synthetic": "idle",
                               "idle_seconds": idle_seconds,
                               "events_seen": event_count,
                               "transport": transport}
                        return

                    # Pull the next line from the reader thread with a
                    # short blocking wait. 100 ms keeps the loop snappy
                    # while still letting CPython sleep most of the time.
                    try:
                        line = self._stdout_queue.get(timeout=0.1)
                    except queue.Empty:
                        # Check whether the child exited while we were
                        # waiting for output; the reader thread will have
                        # pushed a None sentinel if so.
                        if self.proc.poll() is not None and not stream_closed:
                            # Drain any final residual lines that the
                            # reader thread already buffered.
                            stream_closed = True
                        continue

                    if line is None:
                        # Reader thread signalled stdout closed. Drain
                        # remaining queued lines first.
                        while True:
                            try:
                                residual = self._stdout_queue.get_nowait()
                            except queue.Empty:
                                break
                            if residual is None:
                                continue
                            ev = self._parse_line(residual)
                            transcript.write(
                                json.dumps({"direction": "in", "raw": residual,
                                            "ts": now_epoch()}) + "\n")
                            transcript.flush()
                            yield ev
                            event_count += 1
                        yield {"done": True, "_synthetic": "child_exited",
                               "exit_code": self.proc.returncode,
                               "events_seen": event_count,
                               "transport": transport}
                        return

                    ev = self._parse_line(line)
                    transcript.write(json.dumps({"direction": "in", "raw": line,
                                                 "ts": now_epoch()}) + "\n")
                    transcript.flush()
                    yield ev
                    event_count += 1
                    last_event_at = time.time()
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

    def _oneshot_send_turn(self, text: str,
                           timeout_seconds: float) -> Iterator[Dict[str, Any]]:
        """
        Re-spawn the CLI fresh with ``text`` as the prompt argument,
        close stdin immediately, and capture the full stdout/stderr
        to EOF. Yields one ``assistant_message`` event holding the
        captured text plus a synthetic ``done`` event.

        This is the only path that actually grabs answers from TUI
        agents (claude/gemini/cursor/qwen) on Windows. Each call is a
        fresh process invocation so there is no inter-turn session
        state inside the child — continuity, when needed, must be
        included by the caller in the next prompt.
        """
        with self._reader_lock:
            transcript_path = Path(self.record.transcript_path)
            transcript_path.parent.mkdir(parents=True, exist_ok=True)

            # Persist the outbound prompt up-front so a crash in the
            # spawn still leaves evidence in the transcript.
            with transcript_path.open("a", encoding="utf-8") as transcript:
                transcript.write(json.dumps({
                    "direction": "out",
                    "text": text,
                    "ts": now_epoch(),
                    "transport": "oneshot-prompt",
                }) + "\n")
                transcript.flush()

            resolved = resolve_command(self.spec.command)
            if not resolved.executable or not is_executable_resolvable(self.spec.command):
                yield {"event": "error", "text":
                       f"command '{self.spec.command}' not on PATH"}
                yield {"done": True, "_synthetic": "command_not_found",
                       "transport": "oneshot-prompt"}
                return

            argv: List[str] = [resolved.executable, *resolved.extra_args,
                               *self.spec.args, *self.spec.prompt_subcommand_args]
            flag = (self.spec.prompt_arg_flag or "").strip()
            if flag:
                argv.append(flag)
            argv.append(text)
            env = {**os.environ, **self.spec.env}

            started_at = time.time()
            deadline_seconds = max(5.0, float(timeout_seconds))

            try:
                proc = subprocess.Popen(
                    argv,
                    cwd=str(self.cwd),
                    env=env,
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    shell=resolved.use_shell,
                    creationflags=_windows_creationflags(),
                )
            except FileNotFoundError as e:
                yield {"event": "error", "text": str(e)}
                yield {"done": True, "_synthetic": "command_not_found",
                       "transport": "oneshot-prompt"}
                return
            except Exception as e:
                yield {"event": "error", "text": str(e)}
                yield {"done": True, "_synthetic": "spawn_failed",
                       "transport": "oneshot-prompt"}
                return

            self.record.pid = proc.pid
            self.record.last_active_at = now_epoch()
            self.runtime.session_store.save(self.record)

            stdout_text = ""
            stderr_text = ""
            timed_out = False
            try:
                # Close stdin so the CLI sees EOF — most non-interactive
                # CLIs need this to start producing output.
                try:
                    if proc.stdin is not None:
                        proc.stdin.close()
                except Exception:
                    pass
                stdout_text, stderr_text = proc.communicate(
                    timeout=deadline_seconds
                )
            except subprocess.TimeoutExpired:
                timed_out = True
                # Tree-kill so any helper process the CLI forked dies
                # too — otherwise its conhost is left as an orphan.
                _kill_process_tree(proc)
                try:
                    stdout_text, stderr_text = proc.communicate(timeout=5)
                except Exception:
                    stdout_text = stdout_text or ""
                    stderr_text = stderr_text or ""
            except Exception as e:
                # Unexpected I/O failure; treat as a captured error.
                stderr_text = (stderr_text or "") + f"\n[ACPX I/O error: {e}]"

            stdout_text = stdout_text or ""
            stderr_text = stderr_text or ""
            elapsed = time.time() - started_at
            exit_code = proc.returncode

            # Persist captured output. We write one transcript line per
            # non-empty channel so acp_transcript / acp_relay see them
            # as distinct ``in`` events. Both ``raw`` and ``text`` are
            # set so the existing readers behave identically.
            with transcript_path.open("a", encoding="utf-8") as transcript:
                if stdout_text.strip():
                    transcript.write(json.dumps({
                        "direction": "in",
                        "channel": "stdout",
                        "raw": stdout_text,
                        "text": stdout_text,
                        "ts": now_epoch(),
                    }) + "\n")
                if stderr_text.strip():
                    transcript.write(json.dumps({
                        "direction": "in",
                        "channel": "stderr",
                        "raw": stderr_text,
                        "text": stderr_text,
                        "ts": now_epoch(),
                    }) + "\n")
                transcript.flush()

            # Surface the response as a single assistant_message event
            # so extract_last_assistant_text picks it up verbatim and
            # so trim_event_payload can cap it for the LLM payload.
            answer = stdout_text.strip()
            yield {
                "event": "assistant_message",
                "role": "assistant",
                "text": answer,
                "exit_code": exit_code,
                "elapsed_seconds": round(elapsed, 3),
            }
            if stderr_text.strip():
                yield {
                    "event": "log",
                    "channel": "stderr",
                    "text": stderr_text.strip(),
                }
            if timed_out:
                yield {"done": True, "_synthetic": "timeout",
                       "exit_code": exit_code,
                       "elapsed_seconds": round(elapsed, 3),
                       "transport": "oneshot-prompt"}
            else:
                yield {"done": True, "_synthetic": "child_exited",
                       "exit_code": exit_code,
                       "elapsed_seconds": round(elapsed, 3),
                       "transport": "oneshot-prompt"}

    def to_record(self) -> AcpSessionRecord:
        return self.record


class AcpxRuntime:
    """
    Singleton ACP runtime. One instance per Django process.
    """

    def __init__(self, *, config: Optional[AcpxConfig] = None):
        self.config = config or load_acpx_config(load_tlamatini_config_json())
        self.session_store = FileSessionStore(self.config.state_dir)
        self.agent_registry = build_agent_registry(
            self.config.agents, self.config.agents_env,
        )
        self.permission_gate = PermissionGate(
            self.config.permission_mode, self.config.non_interactive
        )
        self._sessions: Dict[str, AcpSession] = {}
        self._session_last_event_at: Dict[str, float] = {}
        self._healthy: Optional[bool] = None
        self._last_doctor: Optional[Dict[str, Any]] = None
        # Per-spec.command -> (cli_version_string, captured_at_epoch). Keeps
        # acp_doctor's per-agent enumeration cheap on repeat calls.
        self._cli_version_cache: Dict[str, tuple[str, float]] = {}

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
            resolved = resolve_command(spec.command)
            res = subprocess.run(
                [resolved.executable, "--version"],
                cwd=self.config.cwd or None,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=5,
                shell=resolved.use_shell,
                text=True,
            )
            self._healthy = res.returncode == 0
            self._last_doctor = {
                "ok": self._healthy,
                "message": f"probe '{target}' --version exited {res.returncode}",
                "probe": {
                    "agent_id": target,
                    "stdout": (res.stdout or "").strip()[:200],
                    "stderr": (res.stderr or "").strip()[:200],
                },
            }
        except subprocess.TimeoutExpired:
            self._healthy = False
            self._last_doctor = {
                "ok": False, "message": f"probe '{target}' timed out",
                "probe": {"agent_id": target, "stdout": "", "stderr": "timeout"},
            }
        except Exception as e:
            self._healthy = False
            self._last_doctor = {
                "ok": False, "message": f"probe '{target}' raised: {e}",
                "probe": {"agent_id": target, "stdout": "", "stderr": str(e)},
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

    def _capture_cli_version(self, spec: AcpAgentSpec,
                             cache_ttl_seconds: float = 300.0,
                             timeout_seconds: float = 3.0) -> str:
        """Run ``<command> --version`` and return its trimmed stdout/stderr.
        Returns ``""`` when the command is unresolvable or the probe fails.
        Result is cached per ``spec.command`` for ``cache_ttl_seconds`` to
        keep ``acp_doctor`` cheap when it enumerates the whole registry."""
        if not is_executable_resolvable(spec.command):
            return ""
        cached = self._cli_version_cache.get(spec.command)
        now = time.time()
        if cached and (now - cached[1]) < cache_ttl_seconds:
            return cached[0]
        try:
            resolved = resolve_command(spec.command)
            res = subprocess.run(
                [resolved.executable, "--version"],
                cwd=self.config.cwd or None,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=timeout_seconds,
                shell=resolved.use_shell,
                text=True,
            )
            text = (res.stdout or res.stderr or "").strip()
            # Take only the first non-empty line and cap length so a chatty
            # `--version` (banners, deprecation notices) doesn't bloat the
            # doctor payload.
            first_line = next((ln for ln in text.splitlines() if ln.strip()), "")
            version = first_line.strip()[:120]
        except Exception:
            version = ""
        self._cli_version_cache[spec.command] = (version, now)
        return version

    def doctor(self) -> Dict[str, Any]:
        """Return a structured health report.

        Shape::
            {
              "ok": bool,
              "message": str,
              "details": [
                {"agent_id", "command", "description",
                 "resolvable": bool, "cli_version": str},
                ...
              ],
              "probe": {"agent_id", "stdout", "stderr"},
            }

        Note: this is a richer shape than the original (``details`` was
        formerly ``[stdout, stderr]``). The probe stdout/stderr now lives
        under ``probe`` so the LLM can branch on per-agent ``resolvable``
        values for hand-off decisions.
        """
        if self._last_doctor is None:
            self.probe_availability()
        base = self._last_doctor or {
            "ok": False, "message": "no doctor data",
            "details": [], "probe": {},
        }
        per_agent: List[Dict[str, Any]] = []
        for agent_id, spec in self.agent_registry.items():
            resolvable = is_executable_resolvable(spec.command)
            per_agent.append({
                "agent_id": agent_id,
                "command": spec.command,
                "description": spec.description,
                "resolvable": resolvable,
                "cli_version": self._capture_cli_version(spec) if resolvable else "",
            })
        return {
            "ok": bool(base.get("ok")),
            "message": base.get("message", ""),
            "details": per_agent,
            "probe": base.get("probe") or {
                "stdout": (base.get("details") or [None, None])[0]
                if isinstance(base.get("details"), list) else "",
                "stderr": (base.get("details") or [None, None])[1]
                if isinstance(base.get("details"), list)
                and len(base.get("details") or []) > 1 else "",
            },
        }

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
             timeout_seconds: Optional[float] = None,
             idle_seconds: Optional[float] = None,
             startup_grace_seconds: Optional[float] = None,
             ) -> List[Dict[str, Any]]:
        sess = self._sessions.get(session_id)
        if sess is None:
            raise AcpRuntimeError("UNKNOWN_SESSION",
                                  f"session '{session_id}' not found")
        # Resolve drain budgets: caller override → per-spec default →
        # global runtime default. Per-spec defaults are what make TUI
        # REPLs (gemini/cursor/qwen) return in seconds instead of the
        # 45 s global timeout.
        timeout = float(
            timeout_seconds
            if timeout_seconds is not None and timeout_seconds > 0
            else (sess.spec.default_timeout_seconds
                  if sess.spec.default_timeout_seconds is not None
                  else self.config.timeout_seconds)
        )
        idle = float(
            idle_seconds
            if idle_seconds is not None and idle_seconds > 0
            else (sess.spec.default_idle_seconds
                  if sess.spec.default_idle_seconds is not None
                  else 6.0)
        )
        grace = float(
            startup_grace_seconds
            if startup_grace_seconds is not None and startup_grace_seconds > 0
            else (sess.spec.default_startup_grace_seconds
                  if sess.spec.default_startup_grace_seconds is not None
                  else 12.0)
        )
        events: List[Dict[str, Any]] = []
        for ev in sess.send_turn(text, timeout,
                                 idle_seconds=idle,
                                 startup_grace_seconds=grace):
            events.append(ev)
            self._session_last_event_at[session_id] = time.time()
            if ev.get("done"):
                break
        return events

    def kill(self, session_id: str) -> Optional[AcpSessionRecord]:
        """Terminate a session. Returns the closed :class:`AcpSessionRecord`
        so callers can surface ``transcript_path`` / ``pid`` in their tool
        return envelope, or ``None`` when the session was already gone."""
        sess = self._sessions.pop(session_id, None)
        if sess is None:
            return None
        sess.close()
        self._session_last_event_at.pop(session_id, None)
        return sess.record

    # ── Read-side helpers (used by the new ACPX tool surface) ─────────
    def _is_alive(self, sess: AcpSession) -> bool:
        if sess.proc is not None:
            try:
                return sess.proc.poll() is None
            except Exception:
                return False
        # oneshot-prompt sessions never keep a long-lived child between
        # turns; they are "alive" as long as the logical record is open.
        if sess.spec.transport == "oneshot-prompt":
            return not sess.record.closed
        return False

    def list_sessions(self) -> List[Dict[str, Any]]:
        """Enumerate live in-memory sessions with status metadata."""
        out: List[Dict[str, Any]] = []
        now = time.time()
        for session_id, sess in list(self._sessions.items()):
            transcript_size = 0
            try:
                p = Path(sess.record.transcript_path)
                if p.exists():
                    transcript_size = p.stat().st_size
            except Exception:
                transcript_size = 0
            out.append({
                "session_id": session_id,
                "agent_id": sess.record.agent_id,
                "pid": sess.record.pid,
                "alive": self._is_alive(sess),
                "cwd": sess.record.cwd,
                "transcript_path": sess.record.transcript_path,
                "transcript_size": transcript_size,
                "created_at": sess.record.created_at,
                "last_active_at": sess.record.last_active_at,
                "last_event_at": self._session_last_event_at.get(session_id),
                "closed": sess.record.closed,
                "label": sess.record.name,
                "age_seconds": max(0.0, now - sess.record.created_at),
            })
        return out

    def session_status(self, session_id: str) -> Dict[str, Any]:
        sess = self._sessions.get(session_id)
        if sess is None:
            # The on-disk record may still be valid for a closed session.
            rec = self.session_store.load(session_id)
            if rec is None:
                raise AcpRuntimeError("UNKNOWN_SESSION",
                                      f"session '{session_id}' not found")
            transcript_size = 0
            try:
                p = Path(rec.transcript_path)
                if p.exists():
                    transcript_size = p.stat().st_size
            except Exception:
                transcript_size = 0
            return {
                "session_id": session_id,
                "agent_id": rec.agent_id,
                "pid": rec.pid,
                "alive": False,
                "transcript_path": rec.transcript_path,
                "transcript_size": transcript_size,
                "last_event_at": None,
                "closed": True,
            }
        transcript_size = 0
        try:
            p = Path(sess.record.transcript_path)
            if p.exists():
                transcript_size = p.stat().st_size
        except Exception:
            transcript_size = 0
        return {
            "session_id": session_id,
            "agent_id": sess.record.agent_id,
            "pid": sess.record.pid,
            "alive": self._is_alive(sess),
            "transcript_path": sess.record.transcript_path,
            "transcript_size": transcript_size,
            "last_event_at": self._session_last_event_at.get(session_id),
            "closed": sess.record.closed,
        }

    def get_session_record(self, session_id: str) -> Optional[AcpSessionRecord]:
        """Return the in-memory record (preferred) or the on-disk record."""
        sess = self._sessions.get(session_id)
        if sess is not None:
            return sess.record
        return self.session_store.load(session_id)

    def read_transcript(self, session_id: str,
                        max_chars: int = 8000,
                        direction: str = "all",
                        ) -> Dict[str, Any]:
        """Read the on-disk transcript for ``session_id`` and return a dict
        with the parsed events, raw text, total size, and a truncated flag.

        ``direction`` is one of ``"all"``, ``"in"`` (child → Tlamatini), or
        ``"out"`` (Tlamatini → child). ``max_chars`` is applied to the raw
        text after the direction filter; the full event list is returned
        regardless so the LLM can still count turns.
        """
        rec = self.get_session_record(session_id)
        if rec is None:
            raise AcpRuntimeError("UNKNOWN_SESSION",
                                  f"session '{session_id}' not found")
        path = Path(rec.transcript_path)
        if not path.exists():
            return {
                "session_id": session_id,
                "transcript_path": str(path),
                "events": [],
                "text": "",
                "total_size": 0,
                "truncated": False,
            }
        try:
            total_size = path.stat().st_size
        except Exception:
            total_size = 0
        events: List[Dict[str, Any]] = []
        try:
            with path.open("r", encoding="utf-8", errors="replace") as fh:
                for line in fh:
                    line = line.rstrip("\n")
                    if not line:
                        continue
                    try:
                        obj = json.loads(line)
                    except Exception:
                        continue
                    if not isinstance(obj, dict):
                        continue
                    if direction in ("in", "out") and obj.get("direction") != direction:
                        continue
                    events.append(obj)
        except Exception as e:
            raise AcpRuntimeError("TRANSCRIPT_READ_FAILED", str(e))
        # Build a compact text dump for the LLM. Each line is "<dir>: <body>".
        body_lines: List[str] = []
        for ev in events:
            d = str(ev.get("direction") or "?")
            body = ev.get("raw") if isinstance(ev.get("raw"), str) else ev.get("text")
            if not isinstance(body, str):
                body = json.dumps(ev, ensure_ascii=False)
            body_lines.append(f"{d}: {body.rstrip()}")
        text = "\n".join(body_lines)
        truncated = False
        if max_chars > 0 and len(text) > max_chars:
            text = text[-max_chars:]
            truncated = True
        return {
            "session_id": session_id,
            "transcript_path": str(path),
            "events": events,
            "text": text,
            "total_size": total_size,
            "truncated": truncated,
        }


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
