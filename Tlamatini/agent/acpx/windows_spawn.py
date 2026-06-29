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
Windows spawn helpers — Python port of OpenClaw's
applyWindowsSpawnProgramPolicy() / materializeWindowsSpawnProgram() /
resolveWindowsSpawnProgramCandidate() helpers.

Why this exists
---------------
On Windows, a "command" can refer to:
    1. A bare executable name on PATH    (e.g. "claude")
    2. A .cmd / .bat shim                (e.g. "claude.cmd")
    3. An absolute path to a .exe        (e.g. "C:/.../claude.exe")
    4. A PowerShell-only command         (e.g. "pwsh -c claude.ps1")

The OpenClaw runtime resolves each agent_id's command into one of those
forms before spawning, so child-process spawning works the same way the
user types the command into a shell. Tlamatini needs the same behavior
because the project is Windows-first.

This module is intentionally small and dependency-free; it only touches
os.environ, os.path, and shutil.which.
"""
from __future__ import annotations

import os
import shutil
import sys
from dataclasses import dataclass
from typing import List

WIN_EXTS = (".exe", ".cmd", ".bat", ".com")


@dataclass
class ResolvedSpawn:
    """
    A spawn-ready triple: (executable, args, shell?).

    On Windows, .cmd / .bat must be invoked via a shell — we set shell=True
    in that case. .exe / .com can be invoked directly.
    """
    executable: str
    extra_args: List[str]
    use_shell: bool


def _is_windows() -> bool:
    return sys.platform.startswith("win")


def _has_path_separator(s: str) -> bool:
    return ("/" in s) or ("\\" in s)


def _looks_executable_with_ext(path: str) -> bool:
    p = path.lower()
    return any(p.endswith(ext) for ext in WIN_EXTS)


def resolve_command(command: str) -> ResolvedSpawn:
    """
    Resolve a `command` string into a spawn-ready ResolvedSpawn.

    Behavior on Windows
    -------------------
    1. If `command` is an absolute path that exists, use it as-is.
       - If it ends in .cmd / .bat, mark use_shell=True.
    2. If `command` contains a path separator but the file doesn't exist,
       still return it unchanged (let the spawn raise FileNotFoundError —
       the caller turns that into an AcpRuntimeError("AGENT_NOT_FOUND")).
    3. Otherwise, search PATH:
         - shutil.which(command)         (exact)
         - shutil.which(command + ".cmd")
         - shutil.which(command + ".bat")
         - shutil.which(command + ".exe")
       Use the first hit. If none match, fall back to `command` (unresolved).

    On non-Windows platforms, just return the command unchanged with
    use_shell=False.
    """
    cmd = (command or "").strip()
    if not cmd:
        return ResolvedSpawn(executable="", extra_args=[], use_shell=False)

    if not _is_windows():
        return ResolvedSpawn(executable=cmd, extra_args=[], use_shell=False)

    # Case 1/2: explicit path
    if _has_path_separator(cmd):
        exists = os.path.exists(cmd)
        use_shell = _looks_executable_with_ext(cmd) and cmd.lower().endswith((".cmd", ".bat"))
        return ResolvedSpawn(
            executable=cmd if exists else cmd,
            extra_args=[],
            use_shell=use_shell,
        )

    # Case 3: PATH search across Windows extensions
    candidates = [cmd]
    base_lower = cmd.lower()
    for ext in WIN_EXTS:
        if not base_lower.endswith(ext):
            candidates.append(cmd + ext)

    for cand in candidates:
        hit = shutil.which(cand)
        if hit:
            use_shell = hit.lower().endswith((".cmd", ".bat"))
            return ResolvedSpawn(executable=hit, extra_args=[], use_shell=use_shell)

    # Unresolved — return original; caller will get a clean error.
    return ResolvedSpawn(executable=cmd, extra_args=[], use_shell=False)


def is_executable_resolvable(command: str) -> bool:
    """Return True iff resolve_command(command) found a real file on disk."""
    r = resolve_command(command)
    if not r.executable:
        return False
    if _has_path_separator(r.executable):
        return os.path.exists(r.executable)
    # On Windows, a bare name returned from resolve_command means the PATH
    # search came up empty — return False in that case.
    if _is_windows():
        return False
    # On POSIX, shutil.which already validated PATH-resolution.
    return shutil.which(r.executable) is not None
