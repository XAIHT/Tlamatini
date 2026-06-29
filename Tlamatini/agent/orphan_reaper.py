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
  * It is a ``conhost.exe`` / ``openconsole.exe`` that is a *genuine orphan*
    — its owning parent process no longer exists (or is a dead/zombie
    remnant of something we spawned).
  * It is a process whose ``cmdline`` references the agent pool directory
    (``agents/pools/`` or ``agents/pools/_chat_runs_/``) yet is not tracked
    by ``AgentProcess`` or ``ChatAgentRun`` anymore.

What is NEVER reaped (the console-window safety contract)
---------------------------------------------------------
The console host that owns *our own* Tlamatini window is sacrosanct. Killing
it closes the visible console and strands the daphne server running headless
— users perceive this as "the window closed unexpectedly and the process
hung". So the reaper hard-protects:

  * the PID returned by ``GetConsoleWindow`` → ``GetWindowThreadProcessId``
    (the host of our own window),
  * ``os.getpid()`` and every ancestor PID (the terminal / PowerShell / cmd
    wrapper / PyInstaller bootloader / Explorer that launched us), and
  * any console host whose parent is still alive — i.e. one in active use.

Crucially, a ``conhost.exe`` whose parent PID is *ours* is our OWN window's
host and must be left alone — the previous revision reaped exactly this and
closed the window on every post-answer sweep in frozen (onedir) builds.

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
import time
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

# NOTE: there is deliberately NO "reapable shell helpers" list here. An
# earlier revision defined one naming ``cmd.exe`` / ``powershell.exe`` /
# ``pwsh.exe`` as reap-on-sight; it was never wired into ``reap_orphans``
# but it is a footgun — when Tlamatini is launched through a PowerShell or
# cmd wrapper (e.g. the legacy ``Tlamatini.ps1``), that shell OWNS the
# console window, so reaping it would close the window. Shell hosts must
# only ever be cleaned via the pool-cmdline scan (which matches the agent
# pool path), never by name.


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


def _runtime_agent_pid(runtime_dir: str) -> Optional[int]:
    """Best-effort read of a run's on-disk ``agent.pid`` (None on any error)."""
    try:
        pid_path = os.path.join(runtime_dir, "agent.pid")
        with open(pid_path, "r", encoding="utf-8") as fh:
            return int((fh.read() or "").strip())
    except Exception:  # noqa: BLE001 — fail-open
        return None


def _tracked_running_pids() -> Set[int]:
    """PIDs of agent processes that are still TRACKED and RUNNING.

    The pool-cmdline sweep in ``reap_orphans`` kills any process whose
    cmdline references the agent-pool directory. That is correct for a real
    *orphan* (a pool process no record owns anymore) but catastrophic for a
    pool process that is deliberately STILL RUNNING. The media agents are
    the canonical case: **Talker / AudioPlayer / VideoPlayer block inside
    their ``main()`` until playback finishes** and can legitimately run for
    hours (a long Talker narration, a looped video). Those runs stay
    ``status='running'`` in ``ChatAgentRun`` (and canvas-launched pool
    agents are tracked in ``AgentProcess``) the whole time they play.

    Without this guard, the Tier-2 post-answer sweep fires the instant the
    Multi-Turn request finishes classifying the answer and reaps the running
    media agent — truncating the audio mid-sentence. That is exactly the bug
    this helper prevents: it returns the set of live, tracked PIDs so the
    caller can add them to ``protected_pids`` and let the playback run to its
    natural end.

    Lazy-imports the Django models and FAILS OPEN (empty set) — a reaper
    that crashes the chat path is worse than one orphan it failed to skip.
    """
    pids: Set[int] = set()
    # status values that mean "this run is still live" — kept in lockstep
    # with ``chat_agent_runtime.RUNNING_STATUSES`` (duplicated locally to
    # avoid importing that chatty module from the reaper hot path).
    running_statuses = ("created", "running")
    try:
        from .models import AgentProcess, ChatAgentRun
    except Exception:  # noqa: BLE001 — Django not ready / import cycle
        return pids
    try:
        for run in ChatAgentRun.objects.filter(
            status__in=running_statuses,
        ).only("pid", "runtimeDir"):
            if run.pid:
                pids.add(int(run.pid))
            # A reanimated / re-parented run can have a different live PID
            # recorded in its on-disk agent.pid — protect that one too.
            runtime_pid = _runtime_agent_pid(run.runtimeDir or "")
            if runtime_pid:
                pids.add(int(runtime_pid))
    except Exception:  # noqa: BLE001 — fail-open
        pass
    try:
        for proc in AgentProcess.objects.all().only("agentProcessPid"):
            if proc.agentProcessPid:
                pids.add(int(proc.agentProcessPid))
    except Exception:  # noqa: BLE001 — fail-open
        pass
    return pids


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


def _console_owner_pid() -> Optional[int]:
    """PID of the process that owns Tlamatini's OWN console window.

    On a classic conhost console this is the ``conhost.exe`` hosting our
    window; under Windows Terminal it is the terminal process. Either way,
    killing it closes (or detaches) the window the user is looking at and
    leaves the server running headless — which users perceive as "the
    window closed and Tlamatini hung". We resolve it via
    ``GetConsoleWindow`` → ``GetWindowThreadProcessId`` and treat it as
    sacrosanct. Returns ``None`` off-Windows, when there is no console, or
    on any failure (the policy guards in ``_console_host_reap_decision``
    still protect ``os.getpid()`` and ancestors in that case).
    """
    if os.name != "nt":
        return None
    try:
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.windll.kernel32
        user32 = ctypes.windll.user32
        kernel32.GetConsoleWindow.restype = wintypes.HWND
        hwnd = kernel32.GetConsoleWindow()
        if not hwnd:
            return None
        pid = wintypes.DWORD(0)
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        return int(pid.value) or None
    except Exception:  # noqa: BLE001 — fail-open; never block cleanup
        return None


def _ancestor_pids(pid: int) -> Set[int]:
    """Return the ancestor PIDs of *pid* (parent, grandparent, ...).

    Used so we never reap a console host that belongs to a process that
    LAUNCHED us — a terminal, a PowerShell/cmd wrapper, the PyInstaller
    bootloader, or Explorer. The walk is bounded and cycle-guarded so a
    pathological parent table cannot loop forever.
    """
    ancestors: Set[int] = set()
    if not _PSUTIL_AVAILABLE:
        return ancestors
    import psutil
    try:
        proc = psutil.Process(pid)
    except Exception:  # noqa: BLE001
        return ancestors
    for _ in range(64):  # hard cap — guards against cycles / bad tables
        try:
            parent = proc.parent()
        except Exception:  # noqa: BLE001
            break
        if parent is None:
            break
        ppid = _safe_pid(parent)
        if ppid in (-1, 0) or ppid in ancestors:
            break
        ancestors.add(ppid)
        proc = parent
    return ancestors


def _console_host_reap_decision(
    *,
    name: str,
    pid: int,
    ppid: Optional[int],
    parent_exists: bool,
    parent_is_zombie: bool,
    protected_pids: Set[int],
    our_pid: int,
    our_ancestors: Set[int],
) -> bool:
    """Pure, side-effect-free policy: should this console host be reaped?

    Returns True ONLY for a console host that is a *genuine orphan* — its
    owning parent process no longer exists, or is a dead/zombie remnant —
    AND that is provably neither our own window's host nor an ancestor's.

    The cardinal rule encoded here, and the reason this lives as an
    isolated, unit-testable unit, is: **never reap a console host whose
    parent is still alive, and never reap our own window's host.** Killing
    such a host closes the visible Tlamatini console and strands the
    server process — the exact failure this module previously caused on
    every post-answer sweep in frozen (onedir) builds, where the main
    window's ``conhost.exe`` is a direct child of ``os.getpid()``.
    """
    if name.lower() not in {n.lower() for n in _REAPABLE_CONSOLE_HOSTS}:
        return False
    # Our own window's host (or anything pre-marked protected) is sacred.
    if pid in protected_pids or pid == our_pid:
        return False
    # A console host owned by us, or by a process that launched us, is in
    # active use — never touch it, even though its parent is "in our tree".
    if ppid == our_pid or ppid in our_ancestors or ppid in protected_pids:
        return False
    # Empty parent slot => the owning process is gone => true orphan.
    if ppid in (0, None):
        return True
    if not parent_exists:
        return True
    # Parent PID still resolves but the process is a dead/zombie remnant of
    # something we spawned => its console host is an orphan too.
    if parent_is_zombie:
        return True
    # Parent is a live, unrelated process — leave its console alone.
    return False


def _is_reapable_console_orphan(
    proc,
    *,
    protected_pids: Set[int],
    our_pid: int,
    our_ancestors: Set[int],
) -> bool:
    """Collect psutil facts about *proc* and apply ``_console_host_reap_decision``."""
    import psutil
    name = _safe_name(proc)
    if name.lower() not in {n.lower() for n in _REAPABLE_CONSOLE_HOSTS}:
        return False
    pid = _safe_pid(proc)
    try:
        ppid = proc.ppid()
    except Exception:  # noqa: BLE001
        return False

    parent_exists = True
    parent_is_zombie = False
    if ppid not in (0, None):
        try:
            parent = psutil.Process(ppid)
            try:
                parent_is_zombie = parent.status() in (
                    psutil.STATUS_ZOMBIE, psutil.STATUS_DEAD,
                )
            except Exception:  # noqa: BLE001
                parent_is_zombie = False
        except psutil.NoSuchProcess:
            parent_exists = False
        except Exception:  # noqa: BLE001
            # Cannot introspect the parent — be conservative, do not reap.
            return False

    return _console_host_reap_decision(
        name=name,
        pid=pid,
        ppid=ppid,
        parent_exists=parent_exists,
        parent_is_zombie=parent_is_zombie,
        protected_pids=protected_pids,
        our_pid=our_pid,
        our_ancestors=our_ancestors,
    )


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


# ── Generalized "eagle eye": spare every FORKED FOREGROUND window ───────────
# A forked foreground window opened by ANY agent (the Telegrammer one-time login,
# an execute_forked_window console, a Sqler / Mongoxer window, ...) owns a VISIBLE
# console window. Whether it is WAITING ON THE USER'S KEYBOARD or actively showing
# output, the user can see and deal with it — so neither the orphan reaper nor the
# command watchdog may ever kill it, however long it sits. (A process that is
# "working, not halted" is already spared by the watchdog's CPU/IO progress test;
# this adds the missing "waiting on the user" case.) The visible-window test is the
# primary, AGENT-AGNOSTIC signal; an explicit cmdline marker is a belt-and-braces
# fallback for the windows we open ourselves.
INTERACTIVE_CONSOLE_MARKERS = ("tlamatini_keep_console", "_tg_login")


def _visible_window_owner_pids() -> Set[int]:
    """PIDs that own a VISIBLE top-level window right now (Windows only). For a
    console window that is the conhost.exe hosting it. Empty set off Windows or on
    any error, so callers fall back to the marker / normal rules."""
    pids: Set[int] = set()
    if os.name != "nt":
        return pids
    try:
        import ctypes
        from ctypes import wintypes
        user32 = ctypes.windll.user32
        enum_proc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

        def _cb(hwnd, _lparam):
            try:
                if user32.IsWindowVisible(hwnd):
                    pid = wintypes.DWORD(0)
                    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                    if pid.value:
                        pids.add(int(pid.value))
            except Exception:  # noqa: BLE001
                pass
            return True

        user32.EnumWindows(enum_proc(_cb), 0)
    except Exception:  # noqa: BLE001
        pass
    return pids


# ── O(N) process-index fast path (replaces per-process psutil.children() rescans) ──
# The previous reap loop called is_protected_foreground_console() — and through it
# psutil's proc.children() / proc.parent() — once per process in the snapshot. Each
# of those re-walks the WHOLE process table, making a sweep O(N^2): on a busy box
# (300+ processes, memory pressure) one sweep pegged a CPU core for ~90s holding the
# GIL and froze the whole server (no chat answer, no catalog) until it finished. We
# now build a parent->children index ONCE from the single process_iter() snapshot
# and answer every parent/child question from the dict, and run the (still
# psutil-backed) protection check ONLY on actual kill-candidates.

def _build_proc_index(snapshot):
    """From one ``process_iter(['pid','name','ppid'])`` snapshot build
    ``(name_by_pid, ppid_by_pid, children_by_ppid)`` in O(N)."""
    name_by_pid: dict = {}
    ppid_by_pid: dict = {}
    children_by_ppid: dict = {}
    for p in snapshot:
        try:
            info = p.info
        except Exception:  # noqa: BLE001
            continue
        pid = info.get("pid")
        if pid is None:
            continue
        name_by_pid[pid] = info.get("name") or ""
        ppid = info.get("ppid")
        ppid_by_pid[pid] = ppid
        if ppid is not None:
            children_by_ppid.setdefault(ppid, []).append(pid)
    return name_by_pid, ppid_by_pid, children_by_ppid


def _owns_visible_window_fast(pid, visible_pids, children_by_ppid) -> bool:
    """Map-based twin of ``_owns_visible_window``: True if *pid* itself, or one of
    its direct children (its conhost console host), owns a visible window — using the
    precomputed child index instead of a psutil.children() table rescan."""
    if not visible_pids:
        return False
    if pid in visible_pids:
        return True
    for ch in children_by_ppid.get(pid, ()):  # direct children (the conhost host)
        if ch in visible_pids:
            return True
    return False


def _is_protected_foreground_fast(proc, pid, ppid, *, visible_pids,
                                  protected_pids, children_by_ppid) -> bool:
    """Map-based, candidate-only twin of ``is_protected_foreground_console``. Spare a
    FORKED FOREGROUND window (the Telegram login, an execute_forked_window console, a
    Sqler/Mongoxer window) or the process inside it when:

      * it (or its conhost child) owns a visible window, OR
      * its parent shell owns one and the parent is not our own/ancestor PID, OR
      * [belt-and-braces] it or a direct child carries an explicit keep-console marker.

    Fail-safe False so a genuinely headless orphan is never accidentally spared."""
    try:
        if _owns_visible_window_fast(pid, visible_pids, children_by_ppid):
            return True
        if (ppid is not None and ppid not in protected_pids
                and _owns_visible_window_fast(ppid, visible_pids, children_by_ppid)):
            return True
        targets = [proc]
        try:
            import psutil
            for ch_pid in children_by_ppid.get(pid, ()):
                try:
                    targets.append(psutil.Process(ch_pid))
                except Exception:  # noqa: BLE001
                    continue
        except Exception:  # noqa: BLE001
            pass
        for tgt in targets:
            cl = (_cmdline_str(tgt) or "").lower()
            if cl and any(m in cl for m in INTERACTIVE_CONSOLE_MARKERS):
                return True
    except Exception:  # noqa: BLE001
        return False
    return False


# Pool agents always run under the carried Python, so only these names can match a
# pool-cmdline fragment. Gating the (handle-opening) cmdline read to them means the
# sweep never reads the command line of unrelated processes on the box.
_POOLISH_PROCESS_NAMES = frozenset({"python.exe", "pythonw.exe", "python", "pythonw"})


def _is_poolish_name(name: str) -> bool:
    return (name or "").lower() in _POOLISH_PROCESS_NAMES


# Monotonic timestamp of the last full snapshot scan, used to COALESCE rapid full
# sweeps (the per-tool Tier-1 path can fire many times a second during a Multi-Turn
# burst). reap_orphans skips the snapshot loop when called again within
# ``min_full_scan_interval`` seconds of the last full scan.
_LAST_FULL_SCAN_MONO: float = 0.0


def _owns_visible_window(proc, visible_pids: Set[int]) -> bool:
    """True if *proc* itself, or a direct child (its conhost console host), owns a
    visible window — i.e. *proc* is a foreground console root. A CREATE_NEW_CONSOLE
    shell's window belongs to a conhost child, so the child check is what catches a
    forked foreground console."""
    if not visible_pids:
        return False
    try:
        if int(proc.pid) in visible_pids:
            return True
    except Exception:  # noqa: BLE001
        return False
    try:
        for ch in proc.children():
            try:
                if int(ch.pid) in visible_pids:
                    return True
            except Exception:  # noqa: BLE001
                continue
    except Exception:  # noqa: BLE001
        pass
    return False


def is_protected_foreground_console(proc, visible_pids=None, protected_pids=None) -> bool:
    """THE shared, generalized detector both reapers use. Spare *proc* when it is a
    forked foreground window — or the process running inside one — opened by any
    agent, so it is never killed while it waits on the user or shows output:

      * it (or its conhost child) owns a visible window, OR
      * its PARENT shell owns one and that parent is NOT our own console/ancestor
        (this protects the inner python/login process, a sibling of the conhost,
        without blanket-sparing ordinary children of the app), OR
      * [belt-and-braces] its command line carries an explicit keep-console marker.

    Fail-safe: False (eligible for the normal idle/orphan rules) on any error, so an
    ordinary HEADLESS hung shell is never accidentally spared."""
    try:
        if visible_pids is None:
            visible_pids = _visible_window_owner_pids()
        protected_pids = protected_pids or set()
        if _owns_visible_window(proc, visible_pids):
            return True
        try:
            parent = proc.parent()
        except Exception:  # noqa: BLE001
            parent = None
        if parent is not None:
            try:
                ppid = int(parent.pid)
            except Exception:  # noqa: BLE001
                ppid = -1
            if ppid not in protected_pids and _owns_visible_window(parent, visible_pids):
                return True
        procs = [proc]
        try:
            procs.extend(proc.children(recursive=True))
        except Exception:  # noqa: BLE001
            pass
        for p in procs:
            cl = (_cmdline_str(p) or "").lower()
            if cl and any(m in cl for m in INTERACTIVE_CONSOLE_MARKERS):
                return True
    except Exception:  # noqa: BLE001
        pass
    return False


# Back-compat alias (older call sites / tests).
def is_protected_interactive_console(proc) -> bool:
    return is_protected_foreground_console(proc)


def reap_orphans(
    scope: str = "unspecified",
    *,
    include_self_tree: bool = True,
    include_pool_scan: bool = True,
    include_console_host_sweep: bool = True,
    protect_running_tracked: bool = True,
    min_full_scan_interval: float = 0.0,
) -> ReapResult:
    """Sweep for orphaned Tlamatini-spawned processes and kill them.

    Args:
        scope: free-form label used in logs (e.g. ``"tier1:after_tool_call"``).
        include_self_tree: kill dead/zombie descendants of the current PID.
        include_pool_scan: kill processes whose cmdline references the
            agent pool directory but are not tracked anymore.
        include_console_host_sweep: kill conhost.exe processes that were
            *orphaned* by our process tree (parent gone / zombie). Our own
            window's console host and any live-parent host are protected.
        protect_running_tracked: when True (the default — used by the
            per-tool Tier-1 and post-answer Tier-2 sweeps), pool processes
            that are still tracked + RUNNING (a playing Talker / AudioPlayer
            / VideoPlayer, a live canvas agent) are NEVER reaped, so their
            playback runs to its natural end no matter how long it takes.
            Pass False ONLY for the shutdown sweep (Tier-3), where every
            spawned child must die so nothing is left orphaned after the app
            exits.

    Returns:
        ReapResult listing killed (name, pid) and surviving (name, pid).
    """
    result = ReapResult(scope=scope)
    if not _PSUTIL_AVAILABLE:
        result.errors.append("psutil not available — skipping reap")
        return result

    import psutil

    our_pid = os.getpid()

    # Processes that must NEVER be reaped under any circumstance: our own
    # PID, every ancestor that launched us (terminal / shell wrapper /
    # bootloader / Explorer), and the host of our own console WINDOW
    # (resolved from GetConsoleWindow). Killing any of these closes the
    # visible Tlamatini console and hangs the server — the exact bug this
    # guard prevents. Computed once, applied to every sweep below.
    our_ancestors = _ancestor_pids(our_pid)
    protected_pids: Set[int] = {our_pid} | our_ancestors
    owner_pid = _console_owner_pid()
    if owner_pid:
        protected_pids.add(owner_pid)

    # Pool processes that are still tracked + RUNNING (most importantly a
    # Talker / AudioPlayer / VideoPlayer playback that legitimately runs for
    # hours) must survive every sweep below — reaping one truncates the audio
    # the instant the Multi-Turn request finishes. The shutdown sweep opts
    # out (protect_running_tracked=False) so nothing is orphaned at app exit.
    if protect_running_tracked:
        protected_pids |= _tracked_running_pids()

    pool_fragments = _pool_path_fragments() if include_pool_scan else []

    # PIDs owning a visible window THIS sweep (computed once — EnumWindows is not
    # free). Used to spare every FORKED FOREGROUND window opened by any agent (the
    # Telegram login, an execute_forked_window console, a Sqler/Mongoxer window)
    # and the process running inside it — they wait on the user or show output.
    foreground_visible_pids = _visible_window_owner_pids()

    # Tier-A: dead/zombie descendants of our own process tree.
    if include_self_tree:
        for child in _iter_known_descendants(our_pid):
            cpid = _safe_pid(child)
            if cpid in protected_pids:
                continue
            try:
                status = child.status()
            except Exception:  # noqa: BLE001
                status = None
            if status not in (psutil.STATUS_ZOMBIE, psutil.STATUS_DEAD):
                continue
            name = _safe_name(child)
            if _terminate_then_kill(child, result.errors):
                result.killed.append((name, cpid))
            else:
                result.survivors.append((name, cpid))

    # Tier-B / Tier-C: wider sweep — pool-cmdline matches and orphaned console
    # hosts. Skipped entirely when neither is requested (Tier-1's cheap path), and
    # COALESCED when ``min_full_scan_interval`` says a full scan ran too recently (a
    # Multi-Turn burst fires the per-tool reaper many times a second).
    global _LAST_FULL_SCAN_MONO
    _want_full = include_console_host_sweep or include_pool_scan
    _recent = (
        min_full_scan_interval > 0
        and (time.monotonic() - _LAST_FULL_SCAN_MONO) < min_full_scan_interval
    )
    if _want_full and not _recent:
        _LAST_FULL_SCAN_MONO = time.monotonic()
        try:
            snapshot = list(psutil.process_iter(["pid", "name", "ppid"]))
        except Exception as exc:  # noqa: BLE001
            result.errors.append(f"process_iter failed: {exc}")
            return result

        # Build the parent->children index ONCE (O(N)). Every parent/child question
        # below is then an O(1) dict lookup, so the sweep is O(N) — not O(N^2) as it
        # was when each process triggered a psutil.children() table rescan (that made
        # one sweep peg a core for ~90s on a 300-process box and froze the server).
        _names, _ppids, _children = _build_proc_index(snapshot)

        for proc in snapshot:
            try:
                info = getattr(proc, "info", None) or {}
                pid = info.get("pid", _safe_pid(proc))
                if pid in (-1, our_pid) or pid in protected_pids:
                    continue
                name = info.get("name") or _safe_name(proc)
                ppid = info.get("ppid")

                # CHEAP candidate detection FIRST. Only a genuine kill-candidate pays
                # for the (now bounded) forked-window protection check — the old code
                # ran that check, and its psutil.children() rescans, on EVERY process.
                # Console-host check is name+ppid (cheap); the pool cmdline read is
                # gated to python-named processes (only those can be a pool agent), so
                # we never open a handle for unrelated processes on the box.
                conhost_orphan = bool(
                    include_console_host_sweep
                    and _is_reapable_console_orphan(
                        proc,
                        protected_pids=protected_pids,
                        our_pid=our_pid,
                        our_ancestors=our_ancestors,
                    )
                )
                pool_match = False
                if not conhost_orphan and pool_fragments and _is_poolish_name(name):
                    cmd = _cmdline_str(proc)
                    pool_match = bool(cmd and any(frag in cmd for frag in pool_fragments))

                if not (conhost_orphan or pool_match):
                    continue

                # A FORKED FOREGROUND window (any agent's visible console — the
                # Telegram login, an execute_forked_window, a Sqler/Mongoxer window),
                # or the process running inside one, is waiting on the user or showing
                # output — never reap it, however long it sits. Checked ONLY on
                # candidates now (map-based; was every process — the O(N^2) cost).
                if _is_protected_foreground_fast(
                    proc, pid, ppid,
                    visible_pids=foreground_visible_pids,
                    protected_pids=protected_pids,
                    children_by_ppid=_children,
                ):
                    continue

                if _terminate_then_kill(proc, result.errors):
                    result.killed.append((name, pid))
                else:
                    result.survivors.append((name, pid))
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
