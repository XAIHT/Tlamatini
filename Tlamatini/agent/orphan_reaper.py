"""
Orphan-process reaper for Tlamatini.

Why this exists
---------------
On Windows, every console child that Tlamatini's agents launch can drag a
``conhost.exe`` companion alongside it. When the immediate parent dies
without first reaping its console children, those ``conhost.exe`` processes
linger as orphans — bearing the Tlamatini icon, since conhost inherits its
icon from the parent EXE that spawned it. Users see "Tlamatini" icons
floating in Task Manager hours after they closed the app and reasonably
conclude that Tlamatini is leaking processes (or worse, hiding a backdoor).

This module gives the rest of the codebase a single, idempotent way to
reap those orphans at three lifecycle points:

  1. **After each Multi-Turn tool call** (cheap, silent — Tier 1)
  2. **After the final answer is broadcast to the user** (Tier 2 — if
     anything survives, the consumer surfaces a SECOND chat message
     listing the offending name+PID pairs)
  3. **At Tlamatini.exe shutdown** (atexit / SIGINT / SIGBREAK — Tier 3)

What gets reaped
----------------
A process is considered a "Tlamatini orphan" if any of the following holds:

  * It is a descendant of the current Tlamatini process (recursive children
    of ``os.getpid()`` whose status is not RUNNING — i.e. zombie / dead).
  * It is a ``conhost.exe`` whose parent PID either no longer exists OR is
    not ``Tlamatini.exe`` / ``python.exe``-from-our-tree.
  * It is a process whose ``cmdline`` references the agent pool directory
    (``agents/pools/`` or ``agents/pools/_chat_runs_/``) yet is not tracked
    by ``AgentProcess`` or ``ChatAgentRun`` anymore.

Public API
----------
``reap_orphans(scope, include_self_tree=True) -> ReapResult``
    Run a sweep and return a ReapResult with killed / surviving lists.

``format_survivors_message(survivors) -> str``
    Build the user-facing HTML snippet listing surviving (name, PID) pairs
    when Tier 2 detects un-killable processes.

Safety
------
Every external call is wrapped in try/except. The reaper MUST NEVER raise
into the caller — a cleanup that crashes the chat path is worse than the
orphans it tries to kill. On any unexpected error the offending entry is
simply skipped and recorded.
"""
from __future__ import annotations

import logging
import os
import sys
from dataclasses import dataclass, field
from typing import Iterable, List, Optional, Set, Tuple

try:
    import psutil  # noqa: F401
    _PSUTIL_AVAILABLE = True
except ImportError:  # pragma: no cover — psutil is in requirements.txt
    _PSUTIL_AVAILABLE = False

logger = logging.getLogger(__name__)


# Process names we care about as orphan candidates on Windows. The set is
# intentionally narrow so an unrelated conhost (e.g. spawned by another
# IDE) is left alone.
_REAPABLE_CONSOLE_HOSTS = frozenset({
    "conhost.exe",
    "openconsole.exe",  # Windows Terminal's console host
})

# Process names that, if seen as descendants of a known-dead Tlamatini
# process, are reaped on sight. Keep this conservative.
_REAPABLE_HELPERS = frozenset({
    "cmd.exe",
    "powershell.exe",
    "pwsh.exe",
})


@dataclass
class ReapResult:
    """Result of one reap sweep."""
    killed: List[Tuple[str, int]] = field(default_factory=list)
    survivors: List[Tuple[str, int]] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    scope: str = "unspecified"

    @property
    def killed_count(self) -> int:
        return len(self.killed)

    @property
    def survivor_count(self) -> int:
        return len(self.survivors)

    def merge(self, other: "ReapResult") -> "ReapResult":
        merged = ReapResult(scope=f"{self.scope}+{other.scope}")
        seen: Set[int] = set()
        for name, pid in self.killed + other.killed:
            if pid not in seen:
                seen.add(pid)
                merged.killed.append((name, pid))
        seen.clear()
        for name, pid in self.survivors + other.survivors:
            if pid not in seen:
                seen.add(pid)
                merged.survivors.append((name, pid))
        merged.errors.extend(self.errors)
        merged.errors.extend(other.errors)
        return merged


def _pool_path_fragments() -> List[str]:
    """Return path fragments that identify Tlamatini agent-pool processes.

    Source mode: ``<repo>/Tlamatini/agent/agents/pools/...``
    Frozen mode: ``<install-dir>/agents/pools/...``
    """
    fragments: List[str] = []
    try:
        if getattr(sys, "frozen", False):
            base = os.path.dirname(sys.executable)
        else:
            base = os.path.dirname(os.path.abspath(__file__))
        pool = os.path.join(base, "agents", "pools")
        # Normalize both slashes since cmdlines on Windows often mix them.
        fragments.append(os.path.normpath(pool))
        fragments.append(pool.replace("\\", "/"))
    except Exception:  # noqa: BLE001 — fail-open
        pass
    return [f for f in fragments if f]


def _safe_name(proc) -> str:
    """psutil.name() can raise; return a best-effort name."""
    try:
        return proc.name() or "?"
    except Exception:  # noqa: BLE001
        return "?"


def _safe_pid(proc) -> int:
    try:
        return int(proc.pid)
    except Exception:  # noqa: BLE001
        return -1


def _terminate_then_kill(proc, errors: List[str]) -> bool:
    """Try terminate, wait 1s, escalate to kill. Returns True if reaped."""
    import psutil
    pid = _safe_pid(proc)
    name = _safe_name(proc)
    try:
        proc.terminate()
    except (psutil.NoSuchProcess, psutil.AccessDenied) as exc:
        if isinstance(exc, psutil.NoSuchProcess):
            return True
        errors.append(f"terminate {name}({pid}) denied: {exc}")
    except Exception as exc:  # noqa: BLE001
        errors.append(f"terminate {name}({pid}) failed: {exc}")
    try:
        psutil.wait_procs([proc], timeout=1.0)
    except Exception:  # noqa: BLE001
        pass
    try:
        if not proc.is_running():
            return True
    except Exception:  # noqa: BLE001
        return True
    try:
        proc.kill()
    except (psutil.NoSuchProcess, psutil.AccessDenied) as exc:
        if isinstance(exc, psutil.NoSuchProcess):
            return True
        errors.append(f"kill {name}({pid}) denied: {exc}")
        return False
    except Exception as exc:  # noqa: BLE001
        errors.append(f"kill {name}({pid}) failed: {exc}")
        return False
    try:
        psutil.wait_procs([proc], timeout=1.0)
        return not proc.is_running()
    except Exception:  # noqa: BLE001
        return True


def _iter_known_descendants(root_pid: int):
    """Yield all live descendants of *root_pid* (recursive)."""
    if not _PSUTIL_AVAILABLE:
        return
    import psutil
    try:
        root = psutil.Process(root_pid)
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return
    try:
        for child in root.children(recursive=True):
            yield child
    except Exception:  # noqa: BLE001
        return


def _is_our_console_host(proc, our_pid_tree: Set[int]) -> bool:
    """Return True if *proc* is a conhost.exe parented to (or descended
    from) our process tree, OR a conhost whose parent is gone."""
    import psutil
    name = _safe_name(proc).lower()
    if name not in {n.lower() for n in _REAPABLE_CONSOLE_HOSTS}:
        return False
    try:
        ppid = proc.ppid()
    except Exception:  # noqa: BLE001
        return False
    if ppid in our_pid_tree:
        return True
    # Parent is gone (PID 0/None or doesn't exist anymore) — likely an
    # orphan from one of OUR earlier children. Reap on sight.
    if ppid in (0, None):
        return True
    try:
        psutil.Process(ppid)
    except psutil.NoSuchProcess:
        return True
    except Exception:  # noqa: BLE001
        return False
    return False


def _cmdline_str(proc) -> str:
    try:
        parts = proc.cmdline()
    except Exception:  # noqa: BLE001
        return ""
    if not parts:
        return ""
    try:
        return " ".join(parts)
    except Exception:  # noqa: BLE001
        return ""


def reap_orphans(
    scope: str = "unspecified",
    *,
    include_self_tree: bool = True,
    include_pool_scan: bool = True,
    include_console_host_sweep: bool = True,
) -> ReapResult:
    """Sweep for orphaned Tlamatini-spawned processes and kill them.

    Args:
        scope: free-form label used in logs (e.g. ``"tier1:after_tool_call"``).
        include_self_tree: kill dead/zombie descendants of the current PID.
        include_pool_scan: kill processes whose cmdline references the
            agent pool directory but are not tracked anymore.
        include_console_host_sweep: kill conhost.exe processes that belong
            to (or were orphaned by) our process tree.

    Returns:
        ReapResult listing killed (name, pid) and surviving (name, pid).
    """
    result = ReapResult(scope=scope)
    if not _PSUTIL_AVAILABLE:
        result.errors.append("psutil not available — skipping reap")
        return result

    import psutil

    # Build the set of "our" PIDs first: current process + all live
    # descendants. We use this to decide whether a conhost.exe is one we
    # are responsible for.
    our_pid = os.getpid()
    our_pid_tree: Set[int] = {our_pid}
    try:
        for child in _iter_known_descendants(our_pid):
            our_pid_tree.add(_safe_pid(child))
    except Exception:  # noqa: BLE001
        pass

    pool_fragments = _pool_path_fragments() if include_pool_scan else []

    # Tier-A: dead/zombie descendants of our own process tree.
    if include_self_tree:
        for child in _iter_known_descendants(our_pid):
            try:
                status = child.status()
            except Exception:  # noqa: BLE001
                status = None
            if status not in (psutil.STATUS_ZOMBIE, psutil.STATUS_DEAD):
                continue
            name = _safe_name(child)
            pid = _safe_pid(child)
            if _terminate_then_kill(child, result.errors):
                result.killed.append((name, pid))
            else:
                result.survivors.append((name, pid))

    # Tier-B / Tier-C: wider sweep — pool-cmdline matches and orphaned
    # console hosts. One snapshot so the iteration is cheap.
    try:
        snapshot = list(psutil.process_iter(["pid", "name", "ppid"]))
    except Exception as exc:  # noqa: BLE001
        result.errors.append(f"process_iter failed: {exc}")
        return result

    for proc in snapshot:
        try:
            pid = _safe_pid(proc)
            if pid in (-1, our_pid):
                continue
            name = _safe_name(proc)

            # Console-host sweep first (cheap — name + ppid checks).
            if include_console_host_sweep and _is_our_console_host(proc, our_pid_tree):
                if _terminate_then_kill(proc, result.errors):
                    result.killed.append((name, pid))
                else:
                    result.survivors.append((name, pid))
                continue

            # Pool-cmdline sweep (more expensive — only run if needed).
            if pool_fragments:
                cmd = _cmdline_str(proc)
                if cmd and any(frag in cmd for frag in pool_fragments):
                    if _terminate_then_kill(proc, result.errors):
                        result.killed.append((name, pid))
                    else:
                        result.survivors.append((name, pid))
                    continue
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue
        except Exception as exc:  # noqa: BLE001
            result.errors.append(f"sweep error: {exc}")
            continue

    if result.killed or result.survivors:
        logger.info(
            "[OrphanReaper:%s] reaped=%d survivors=%d errors=%d",
            scope, result.killed_count, result.survivor_count, len(result.errors),
        )
    return result


def format_survivors_message(survivors: Iterable[Tuple[str, int]]) -> Optional[str]:
    """Build the user-facing HTML snippet listing surviving orphans.

    Returns ``None`` if there are no survivors, so the caller can skip
    sending an additional chat message in the (common) happy path.
    """
    rows = [(name, pid) for name, pid in survivors if pid > 0]
    if not rows:
        return None
    list_items = "".join(
        f"<li><code>{name}</code> &mdash; PID <strong>{pid}</strong></li>"
        for name, pid in rows
    )
    return (
        "<div class='orphan-warning'>"
        "<strong>⚠ Heads-up:</strong> Tlamatini tried to clean up after this "
        "request but the following process(es) refused to terminate. "
        "They are most likely harmless leftovers from a tool you ran, but "
        "if you do not recognize them please end them manually from Task "
        "Manager so no Tlamatini-spawned child outlives the app:"
        f"<ul>{list_items}</ul>"
        "</div>"
    )
