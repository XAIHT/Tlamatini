# Tlamatini Author Banner — Angela López Mendoza · @angelahack1
"""Installation-scoped process cleanup for the standalone Windows uninstaller.

psutil is already a Tlamatini dependency and is bundled into Uninstaller.exe.
Never kill by process name or by a stale agent.pid file. All agents, pools and
their descendants use the same path/identity checks, regardless of agent type.
"""
from __future__ import annotations

import os
import time

import psutil


def inside(path, root):
    if not path or not os.path.isabs(path):
        return False
    path, root = os.path.normcase(os.path.abspath(path)), os.path.normcase(os.path.abspath(root))
    return path == root or path.startswith(root.rstrip("\\/") + os.sep)


def command_path(argument, root):
    # An individual argv path, never a substring inside code, URLs or prose.
    value = argument.split("=", 1)[1] if argument.startswith("--") and "=" in argument else argument
    return inside(value.strip('"'), root)


def owned_processes(root):
    """Return owned identities and evidence, excluding ourselves and ancestors."""
    current = psutil.Process()
    protected = {current.pid, *(p.pid for p in current.parents())}
    records = {}
    agents = os.path.join(os.path.abspath(root), "agents")
    for proc in psutil.process_iter(["pid", "ppid", "name", "exe", "cwd", "cmdline", "create_time"], ad_value=None):
        info = proc.info
        if info["pid"] in protected or not info["create_time"]:
            continue
        if (info["name"] or "").lower() in {"explorer.exe", "system", "registry"}:
            continue
        reason = None
        if inside(info["exe"], root):
            reason = "executable inside installation"
        elif inside(info["cwd"], agents):
            reason = "working directory inside agents directory"
        elif any(command_path(arg, agents) for arg in info["cmdline"] or []):
            reason = "command path inside agents directory"
        if reason is None:
            # The product's _build_child_env already gives agent workers this
            # exact installation identity. It survives reparenting and a cwd
            # change, unlike a process-tree walk. Read only this key; never
            # retain or log the environment (which may contain credentials).
            try:
                inherited_root = proc.environ().get("TLAMATINI_AGENTS_ROOT", "")
                if inherited_root and os.path.normcase(os.path.abspath(inherited_root)) == os.path.normcase(agents):
                    reason = "inherited installation agents root"
            except (psutil.NoSuchProcess, psutil.AccessDenied, OSError):
                pass
        records[info["pid"]] = {
            "pid": info["pid"], "parent": info["ppid"],
            "name": info["name"] or "?", "created": info["create_time"],
            "path": info["exe"] or "", "evidence": reason,
        }
    # Creation-time ordering prevents an unrelated reused parent PID from
    # making a process a descendant of this installation.
    changed = True
    while changed:
        changed = False
        for row in records.values():
            parent = records.get(row["parent"])
            if not row["evidence"] and parent and parent["evidence"] and row["created"] >= parent["created"]:
                row["evidence"] = "child of installation process"
                changed = True
    return [r for r in records.values() if r["evidence"]]


def main_application(row, root):
    return os.path.normcase(row["path"]) == os.path.normcase(os.path.join(os.path.abspath(root), "Tlamatini.exe"))


def stop_owned_workers(root):
    """Stop confirmed workers and their children; refuse a running main app."""
    report = {"installation": os.path.abspath(root), "stopped": [], "survivors": []}
    known = {}
    suspended = []
    current = psutil.Process()
    protected = {current.pid, *(p.pid for p in current.parents())}
    try:
        for _ in range(3):
            rows = owned_processes(root)
            if any(main_application(row, root) for row in rows):
                raise RuntimeError("Close Tlamatini before uninstalling; the application is still running.")
            for row in rows:
                known[(row["pid"], row["created"])] = row
            if not rows:
                break
            # Freeze each proved worker before taking a second child snapshot,
            # so it cannot create more children during removal.
            for row in rows:
                try:
                    proc = psutil.Process(row["pid"])
                    if proc.create_time() != row["created"]:
                        continue
                    proc.suspend()
                    suspended.append(proc)
                    for child in proc.children(recursive=True):
                        if child.pid in protected or child.name().lower() in {"explorer.exe", "system", "registry"}:
                            continue
                        identity = (child.pid, child.create_time())
                        known[identity] = dict(pid=child.pid, created=identity[1],
                                               name=child.name(), evidence="child of installation worker")
                except psutil.NoSuchProcess:
                    continue
                except psutil.AccessDenied as exc:
                    raise RuntimeError(f"Cannot stop installation worker PID {row['pid']}. Close it and retry.") from exc
            processes = []
            for identity, row in reversed(list(known.items())):
                try:
                    proc = psutil.Process(row["pid"])
                    if proc.create_time() != row["created"]:
                        continue
                    proc.terminate()
                    processes.append(proc)
                except psutil.NoSuchProcess:
                    pass
                except psutil.AccessDenied as exc:
                    raise RuntimeError(f"Cannot terminate installation worker PID {row['pid']}.") from exc
            _, alive = psutil.wait_procs(processes, timeout=5)
            for proc in alive:
                proc.kill()
            _, alive = psutil.wait_procs(alive, timeout=5)
            if alive:
                raise RuntimeError("Installation workers are still running: " + ", ".join(str(p.pid) for p in alive))
            time.sleep(0.1)
        report["survivors"] = owned_processes(root)
        if report["survivors"]:
            raise RuntimeError("Installation workers restarted during uninstall. Close them and retry.")
        report["stopped"] = list(known.values())
        return report
    finally:
        # A denied removal must never leave another surviving worker suspended.
        for proc in suspended:
            try:
                if proc.is_running():
                    proc.resume()
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
