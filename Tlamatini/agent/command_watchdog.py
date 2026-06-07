"""
Autonomous command watchdog for Tlamatini.

Why this exists
---------------
A Multi-Turn tool call that shells out (``execute_command``, the Executer /
Pythonxer / PSer wrapped agents, ...) runs the child **synchronously on the
worker thread**. If that child wedges — the classic case is a malformed
``cmd /c "powershell -Command "...""`` whose mangled quotes drop PowerShell to
its ``>>`` continuation prompt where it sits forever waiting on stdin — the
worker thread blocks behind it and the whole chat appears "hanged".

The existing safety nets cannot rescue this situation:

  * ``tools._run_command_bounded`` starves stdin to DEVNULL and applies a hard
    600 s timeout, but (a) it only protects code paths that go through it, and
    (b) 600 s is a *very* long time to stare at a frozen chat.
  * ``orphan_reaper`` Tier 1 runs *after* each tool call returns — but a
    blocked tool call never returns, so Tier 1 never runs. Tier 2 runs *after*
    the answer is broadcast — which never happens while we are blocked.

Both of those run on the very thread that is stuck. This module closes the gap
with a process that **cannot itself be blocked by the hang**: a daemon thread,
started once at app boot, that periodically looks for console interpreters we
spawned (``cmd.exe`` / ``powershell.exe`` / ``pwsh.exe``) and kills only the
ones that are **making no progress at all**.

How "is it actually working?" is decided (the important part)
------------------------------------------------------------
The watchdog NEVER kills on elapsed time. A command may run for hours and is
perfectly safe as long as it is *making progress*. Progress is measured across
the **entire process subtree** (the shell PLUS every descendant), using two
independent signals sampled every tick:

  * **CPU time consumed** — ``cpu_times().user + .system`` summed over the
    subtree. A real build / pip install / compile / test run burns CPU.
  * **I/O bytes moved** — ``io_counters()`` read+write+other summed over the
    subtree. A download / ``git clone`` / large file write moves bytes even at
    ~0 % CPU.

A tick counts as "idle" ONLY if, since the previous tick, the subtree consumed
less than ``progress_cpu_seconds`` of CPU **and** moved less than
``progress_io_bytes`` of I/O. A process is killed only when it has been:

  * alive longer than ``hang_grace_seconds``, **and**
  * idle (by the subtree rule above) for ``required_idle_ticks`` *consecutive*
    ticks.

Consequences — why a long-but-working process is safe:

  * A CPU-bound job (any length) keeps incrementing CPU time → never idle.
  * An I/O-bound / network job (slow download, clone) keeps moving bytes →
    never idle, even though its own CPU is ~0 %.
  * A launcher shell whose *child* does the work (``cmd.exe`` → ``python.exe``)
    is judged by the SUBTREE, so the busy child keeps the whole tree "working".
  * A process we cannot sample at all (AccessDenied) is treated as *working*
    (fail safe — we never kill what we cannot measure).

Only a tree that burns no CPU and moves no bytes for the full grace+streak
window — the signature of a shell stuck at a prompt waiting on input that will
never come — is reaped.

Safety contract (mirrors ``orphan_reaper``)
-------------------------------------------
* The watchdog **must never raise** into anything — it runs on its own daemon
  thread and swallows every error.
* It hard-protects our own process, every ancestor PID, and the console-window
  owner — exactly the set ``orphan_reaper`` protects — so it can never close
  our own window or kill the terminal that launched us.
* It only ever kills a *console interpreter* (and that interpreter's
  descendants). It never touches the Python agent runtimes themselves, the
  Daphne worker, or the MCP/gRPC sidecar threads' processes.
* psutil missing → it degrades to a silent no-op.

Tunables (read from ``config.json`` at boot, all optional — safe defaults):
    command_watchdog_enabled              (bool,  default True)
    command_watchdog_tick_seconds         (float, default 15)
    command_watchdog_hang_grace_seconds   (float, default 180)
    command_watchdog_required_idle_ticks  (int,   default 4)
    command_watchdog_progress_cpu_seconds (float, default 0.10)
    command_watchdog_progress_io_bytes    (int,   default 65536)
"""
from __future__ import annotations

import logging
import os
import threading
import time
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)

try:
    import psutil
    _PSUTIL_AVAILABLE = True
except ImportError:  # pragma: no cover - psutil is in requirements.txt
    psutil = None  # type: ignore
    _PSUTIL_AVAILABLE = False


# Console interpreters whose presence-while-making-no-progress is the signature
# of a hung shell command. We deliberately do NOT include conhost.exe /
# openconsole.exe here: those are reaped via the tree-kill of their owning
# interpreter (and the standing orphan_reaper handles genuinely orphaned ones).
# We also never list python.exe — the agent runtimes manage their own lifecycle.
_SHELL_NAMES = frozenset({"cmd.exe", "powershell.exe", "pwsh.exe"})

_DEFAULTS = {
    "command_watchdog_enabled": True,
    "command_watchdog_tick_seconds": 15.0,
    "command_watchdog_hang_grace_seconds": 180.0,
    "command_watchdog_required_idle_ticks": 4,
    "command_watchdog_progress_cpu_seconds": 0.10,
    "command_watchdog_progress_io_bytes": 65536,
}


def _cfg(config, key):
    """Read a watchdog key from the loaded config dict, falling back to the
    documented default. Never raises."""
    try:
        if config and key in config and config.get(key) is not None:
            return config.get(key)
    except Exception:
        pass
    return _DEFAULTS[key]


@dataclass
class _Tracked:
    """Per-child bookkeeping carried across ticks."""
    proc: object                      # psutil.Process for the shell (root of the subtree)
    first_seen: float                 # time.monotonic() of first sighting
    last_cpu: float = -1.0            # subtree cumulative CPU seconds at last tick (-1 = unset)
    last_io: float = -1.0             # subtree cumulative I/O bytes at last tick (-1 = unset)
    idle_ticks: int = 0               # consecutive ticks observed making no progress
    name: str = "?"


# ── protected-PID resolution (reuse orphan_reaper, fall back if unavailable) ──

def _protected_pids(our_pid: int) -> Set[int]:
    """{our pid} ∪ ancestors ∪ console-window owner — the set that must never
    be killed (killing any of these strands or closes our own server)."""
    protected: Set[int] = {our_pid}
    try:
        from . import orphan_reaper as _r
        try:
            protected |= _r._ancestor_pids(our_pid)
        except Exception:
            pass
        try:
            owner = _r._console_owner_pid()
            if owner:
                protected.add(owner)
        except Exception:
            pass
        return protected
    except Exception:
        pass
    # Fallback: walk ancestors directly via psutil.
    if _PSUTIL_AVAILABLE:
        try:
            cur = psutil.Process(our_pid)
            for _ in range(64):
                cur = cur.parent()
                if cur is None:
                    break
                protected.add(cur.pid)
        except Exception:
            pass
    return protected


def _kill_tree(proc, errors: List[str]) -> int:
    """Kill *proc* and every descendant (descendants first so handle holders
    die before the root). Returns the count actually reaped. Never raises."""
    reaped = 0
    try:
        from .orphan_reaper import _terminate_then_kill as _tk
    except Exception:
        def _tk(p, errs):  # minimal fallback: terminate, wait, kill
            try:
                p.terminate()
                try:
                    p.wait(timeout=1.0)
                except Exception:
                    p.kill()
                return True
            except Exception as exc:  # noqa: BLE001
                errs.append(f"kill failed: {exc}")
                return False

    victims = []
    try:
        victims = list(proc.children(recursive=True))
    except Exception:
        victims = []
    victims.append(proc)  # root last
    for v in victims:
        try:
            if _tk(v, errors):
                reaped += 1
        except Exception as exc:  # noqa: BLE001
            errors.append(f"kill {getattr(v, 'pid', '?')} failed: {exc}")
    return reaped


class CommandWatchdog:
    """Stateful, testable watchdog. ``scan_and_reap`` is pure enough to unit
    test: inject ``descendant_provider`` (→ iterable of psutil-like processes)
    and ``killer`` (→ callable) and it never sleeps or touches real psutil."""

    def __init__(
        self,
        *,
        our_pid: Optional[int] = None,
        tick_seconds: float = _DEFAULTS["command_watchdog_tick_seconds"],
        hang_grace_seconds: float = _DEFAULTS["command_watchdog_hang_grace_seconds"],
        required_idle_ticks: int = _DEFAULTS["command_watchdog_required_idle_ticks"],
        progress_cpu_seconds: float = _DEFAULTS["command_watchdog_progress_cpu_seconds"],
        progress_io_bytes: int = _DEFAULTS["command_watchdog_progress_io_bytes"],
        descendant_provider: Optional[Callable[[], list]] = None,
        killer: Optional[Callable[[object, List[str]], int]] = None,
        clock: Callable[[], float] = time.monotonic,
    ):
        self.our_pid = our_pid if our_pid is not None else os.getpid()
        self.tick_seconds = max(2.0, float(tick_seconds))
        self.hang_grace_seconds = max(10.0, float(hang_grace_seconds))
        self.required_idle_ticks = max(1, int(required_idle_ticks))
        self.progress_cpu_seconds = max(0.0, float(progress_cpu_seconds))
        self.progress_io_bytes = max(0, int(progress_io_bytes))
        self._descendant_provider = descendant_provider or self._default_descendants
        self._killer = killer or _kill_tree
        self._clock = clock
        self._tracked: Dict[int, _Tracked] = {}
        self._protected: Set[int] = _protected_pids(self.our_pid)
        self._stop = threading.Event()
        self._tick_count = 0

    # -- real-psutil descendant enumeration (overridable in tests) --
    def _default_descendants(self) -> list:
        if not _PSUTIL_AVAILABLE:
            return []
        try:
            me = psutil.Process(self.our_pid)
            return list(me.children(recursive=True))
        except Exception:
            return []

    @staticmethod
    def _proc_name(proc) -> str:
        try:
            return (proc.name() or "?").lower()
        except Exception:
            return "?"

    @staticmethod
    def _proc_pid(proc) -> int:
        try:
            return int(proc.pid)
        except Exception:
            return -1

    def _subtree_metrics(self, root) -> Optional[Tuple[float, float]]:
        """Return ``(cumulative_cpu_seconds, cumulative_io_bytes)`` summed over
        ``root`` and every descendant — a monotonically increasing "work done"
        counter for the whole tree.

        Returns ``None`` if NOTHING in the tree could be sampled (e.g. every
        process denied access). The caller treats ``None`` as "made progress"
        so we never kill a tree we cannot measure. A *partial* sample (some
        descendants unreadable) still counts — any movement spares the tree.
        """
        procs = [root]
        try:
            procs.extend(root.children(recursive=True))
        except Exception:
            pass

        cpu_total = 0.0
        io_total = 0.0
        sampled_any = False
        for p in procs:
            try:
                ct = p.cpu_times()
                cpu_total += float(getattr(ct, "user", 0.0)) + float(getattr(ct, "system", 0.0))
                sampled_any = True
            except Exception:
                pass
            try:
                io = p.io_counters()
                io_total += (
                    float(getattr(io, "read_bytes", 0))
                    + float(getattr(io, "write_bytes", 0))
                    + float(getattr(io, "other_bytes", 0))
                )
                sampled_any = True
            except Exception:
                # io_counters can be unavailable/denied on some processes; that
                # is fine — CPU alone still gauges progress.
                pass

        if not sampled_any:
            return None
        return cpu_total, io_total

    def scan_and_reap(self) -> List[int]:
        """One tick. Returns the list of root PIDs whose tree was killed."""
        killed: List[int] = []
        self._tick_count += 1
        try:
            current = self._descendant_provider() or []
        except Exception:
            current = []

        seen: Set[int] = set()
        for proc in current:
            pid = self._proc_pid(proc)
            if pid < 0 or pid in self._protected or pid == self.our_pid:
                continue
            name = self._proc_name(proc)
            if name not in _SHELL_NAMES:
                continue
            seen.add(pid)

            metrics = self._subtree_metrics(proc)

            entry = self._tracked.get(pid)
            if entry is None:
                # First sighting: record birth time + a progress baseline. No
                # judgment this tick (we need a delta).
                cpu0, io0 = metrics if metrics is not None else (-1.0, -1.0)
                self._tracked[pid] = _Tracked(
                    proc=proc, first_seen=self._clock(),
                    last_cpu=cpu0, last_io=io0, idle_ticks=0, name=name,
                )
                continue

            if metrics is None:
                # Cannot measure the tree at all → assume it is working.
                entry.idle_ticks = 0
                continue

            cpu, io = metrics
            if entry.last_cpu < 0 or entry.last_io < 0:
                # Baseline was not captured at birth (transient sample miss);
                # capture it now and judge from the next tick.
                entry.last_cpu, entry.last_io = cpu, io
                entry.idle_ticks = 0
                continue

            cpu_delta = cpu - entry.last_cpu
            io_delta = io - entry.last_io
            entry.last_cpu, entry.last_io = cpu, io

            made_progress = (cpu_delta > self.progress_cpu_seconds) or (io_delta > self.progress_io_bytes)
            if made_progress:
                entry.idle_ticks = 0  # it is doing real work — leave it alone
            else:
                entry.idle_ticks += 1

            age = self._clock() - entry.first_seen
            if age >= self.hang_grace_seconds and entry.idle_ticks >= self.required_idle_ticks:
                errors: List[str] = []
                self._log_kill_banner(name, pid, age, cpu_delta, io_delta)
                try:
                    self._killer(entry.proc, errors)
                except Exception as exc:  # noqa: BLE001
                    errors.append(f"killer raised: {exc}")
                if errors:
                    logger.warning("[command_watchdog] kill issues for PID %s: %s", pid, "; ".join(errors))
                killed.append(pid)
                self._tracked.pop(pid, None)
                seen.discard(pid)

        # Drop bookkeeping for children that have gone away on their own.
        for pid in list(self._tracked.keys()):
            if pid not in seen:
                self._tracked.pop(pid, None)

        # Visible per-tick heartbeat. Uses print() (NOT logger.info) on purpose:
        # the manage.py stdout tee captures print into tlamatini.log, whereas
        # agent.* logger INFO records are not emitted to that stream — so this is
        # the line that proves the watchdog is alive and actively scanning every
        # tick. Lists the tracked shells (the "instances" it is watching) so a
        # hung cmd/powershell shows up here before it is reaped.
        try:
            tracked_desc = ", ".join(
                f"{t.name}#{pid}(idle={t.idle_ticks})" for pid, t in self._tracked.items()
            ) or "none"
            print(
                f"--- [WATCHDOG] tick #{self._tick_count}: scanned {len(current)} "
                f"descendant proc(es), watching {len(self._tracked)} shell(s) "
                f"[{tracked_desc}], killed {len(killed)} this tick",
                flush=True,
            )
        except Exception:
            pass
        return killed

    @staticmethod
    def _log_kill_banner(name: str, pid: int, age: float, cpu_delta: float, io_delta: float) -> None:
        banner = (
            "\n!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!\n"
            "  *** TLAMATINI COMMAND WATCHDOG ***\n"
            f"  HUNG SHELL DETECTED: {name} (PID {pid})\n"
            f"  NO CPU/IO PROGRESS IN ITS PROCESS TREE FOR {age:.0f}s "
            f"(last tick: {cpu_delta:.3f} cpu-s, {io_delta:.0f} bytes) — KILLING IT\n"
            "  (a command was waiting on input that never came; the chat is now unblocked)\n"
            "!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!"
        )
        try:
            logger.warning(banner)
        except Exception:
            pass
        # Also print so the kill is visible in tlamatini.log (the stdout tee).
        try:
            print(banner, flush=True)
        except Exception:
            pass

    # -- daemon-thread loop --
    def run_forever(self) -> None:
        logger.info(
            "[command_watchdog] started: tick=%.0fs grace=%.0fs idle=%d ticks "
            "(progress = >%.2f cpu-s OR >%d bytes per tick across the subtree)",
            self.tick_seconds, self.hang_grace_seconds, self.required_idle_ticks,
            self.progress_cpu_seconds, self.progress_io_bytes,
        )
        # print() so it lands in tlamatini.log (logger.info from agent.* is not
        # emitted to the stdout tee). This is the boot proof that the watchdog
        # daemon thread is up.
        try:
            print(
                f"--- [WATCHDOG] STARTED: tick={self.tick_seconds:.0f}s "
                f"grace={self.hang_grace_seconds:.0f}s idle={self.required_idle_ticks} ticks "
                "(kills a shell only after no CPU/IO progress in its whole tree "
                "for the grace+idle window)",
                flush=True,
            )
        except Exception:
            pass
        while not self._stop.is_set():
            try:
                self.scan_and_reap()
            except Exception:
                logger.exception("[command_watchdog] tick failed (non-fatal)")
            self._stop.wait(self.tick_seconds)

    def stop(self) -> None:
        self._stop.set()


# ── module-level singleton boot (idempotent) ──
_started = False
_start_lock = threading.Lock()
_instance: Optional[CommandWatchdog] = None


def start_in_background(config=None) -> Optional[CommandWatchdog]:
    """Start the watchdog daemon thread exactly once. Safe to call from
    ``AppConfig.ready``. Returns the instance (or None if disabled / psutil
    missing). Never raises."""
    global _started, _instance
    try:
        if not _PSUTIL_AVAILABLE:
            logger.warning("[command_watchdog] psutil unavailable — watchdog disabled")
            return None
        if not bool(_cfg(config, "command_watchdog_enabled")):
            logger.info("[command_watchdog] disabled via config")
            return None
        with _start_lock:
            if _started:
                return _instance
            wd = CommandWatchdog(
                tick_seconds=float(_cfg(config, "command_watchdog_tick_seconds")),
                hang_grace_seconds=float(_cfg(config, "command_watchdog_hang_grace_seconds")),
                required_idle_ticks=int(_cfg(config, "command_watchdog_required_idle_ticks")),
                progress_cpu_seconds=float(_cfg(config, "command_watchdog_progress_cpu_seconds")),
                progress_io_bytes=int(_cfg(config, "command_watchdog_progress_io_bytes")),
            )
            t = threading.Thread(target=wd.run_forever, name="CommandWatchdog", daemon=True)
            t.start()
            _started = True
            _instance = wd
            return wd
    except Exception:
        logger.exception("[command_watchdog] failed to start (non-fatal)")
        return None
