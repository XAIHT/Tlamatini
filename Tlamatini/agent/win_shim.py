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
Windows command resolution — the ONE definition of "how do we spawn this?".

Why this module exists
----------------------
On Windows a great many tools are NOT executables. `npx`, `npm`, `pnpm`, and
every CLI installed by npm or pnpm are **batch shims** (`.cmd`), and
`CreateProcess` cannot execute a `.cmd` at all. Tlamatini has hit that wall in
three separate subsystems, and each one grew its own half-answer:

* **External MCPs** — `[WinError 2] The system cannot find the file specified`
  on any npm/pnpm-installed server with a bare command name (measured
  2026-09-07 on `deepwebresearch`). `external_mcp_manager._resolve_argv` HAD a
  correct `.cmd`→COMSPEC fallback, but `runtime_provisioner.resolve_spawn`
  returned a non-empty pass-through argv for every command outside
  `MANAGED_TOOLS`, so that fallback was **unreachable dead code**.
* **ACPX** — `agent/acpx/windows_spawn.py` set `use_shell=True` for a `.cmd`.
* **The stdio MCP server** — `tlamatini_acpx.py` did nothing at all and hung.

⚠️ AND THE OBVIOUS ANSWER — "just run it through cmd.exe" — IS A TRAP.
**cmd.exe stops reading its command line at the first newline.** Measured
2026-09-07: a 2,205-character multi-line ACPX research prompt reached the child
as **40 characters**, cut at the first line break, SILENTLY — and the child
answered that fragment as if it were the whole task. Re-measured on a real
npm-shaped shim: 40 of 2,647 bytes. `shell=True` and an explicit
`cmd.exe /d /s /c` fail identically; the limit is cmd.exe itself, not Python's
quoting. So the shell is a LAST RESORT, acceptable only for short arguments,
and never the default.

The right answer is to **bypass the shim**. An npm/pnpm wrapper is a thin
launcher whose real payload is a JavaScript file::

    npm:   "%_prog%"  "%dp0%\\node_modules\\<pkg>\\bin\\<tool>.js" %*
    pnpm:  "%~dp0\\node.exe"  "%~dp0\\..\\global\\v11\\<hash>\\...\\<tool>.js" %*

so the real command is simply ``node.exe <that script>``, which spawns directly
with ``shell=False`` and keeps every byte. That is the same trick
``runtime_provisioner.resolve_spawn`` already used for `npx` — this module just
makes it available to EVERY caller instead of six hard-coded tool names.

Contract (do NOT weaken)
------------------------
1. **Never widen the shell.** `needs_shell` may only be True when a `.cmd`/
   `.bat` could not be rewritten. Callers that pass long or multi-line
   arguments must warn on that path (ACPX does).
2. **A real `.exe` always beats a shim** — `_WIN_EXTS` puts `.exe` first. An
   earlier `_which` tried `.cmd` first, so `claude` went through the shell even
   though `claude.exe` sits right beside it.
3. **FAIL-OPEN, and never lie about resolution.** Anything unrecognised is
   handed back unchanged so the caller's own error path reports the truth
   ("command not found") rather than a silent substitution. Nothing here raises.
4. **Never point at a script that is not on disk** — a rewrite is only returned
   when both the interpreter and the payload exist.
5. Stdlib-only; imports nothing from ``agent.*`` so it can be used from the
   Django app, from a pool agent, and from the Django-free stdio MCP server
   alike, and can never create an import cycle.
"""
from __future__ import annotations

import os
import re
import shutil
from typing import List, Optional, Tuple

#: Extension search order. `.exe` FIRST — a real binary always beats a shim.
WIN_EXTS: Tuple[str, ...] = (".exe", ".com", ".cmd", ".bat")

#: The extensions CreateProcess cannot start on its own.
SHIM_EXTS: Tuple[str, ...] = (".cmd", ".bat")


def is_shim(path: str) -> bool:
    """True when ``path`` is a batch shim CreateProcess cannot execute."""
    return bool(path) and path.lower().endswith(SHIM_EXTS)


def find_on_path(command: str) -> str:
    """Resolve a bare command name to a real file, preferring a true executable.

    Returns "" when nothing is found. ``shutil.which`` is tried first (it
    honours PATHEXT, which already lists `.EXE` before `.CMD`), then each
    extension explicitly for the cases PATHEXT does not cover.
    """
    cmd = (command or "").strip()
    if not cmd:
        return ""
    hit = shutil.which(cmd)
    if hit:
        return hit
    for ext in WIN_EXTS:
        hit = shutil.which(cmd + ext)
        if hit:
            return hit
    return ""


# npm writes "%dp0%\..."; pnpm writes "%~dp0\...". Both point at the .js payload.
_SHIM_SCRIPT_RE = re.compile(
    '"' + chr(37) + '~?dp0' + chr(37) + r'?\\+([^"]+?\.(?:js|mjs|cjs))"', re.I)


def _node_for(shim_dir: str) -> str:
    """The node.exe that should run a shim's payload: sibling first, then PATH."""
    local = os.path.join(shim_dir, "node.exe")
    if os.path.exists(local):
        return local
    return shutil.which("node") or ""


def deshim(shim_path: str) -> Optional[List[str]]:
    """Rewrite an npm/pnpm ``.cmd`` shim into the direct argv it wraps.

    Returns ``[node_exe, script_path]``, or None when the file is not a shape we
    recognise — the caller then falls back to the shell, which still works for
    short arguments.
    """
    try:
        body = open(shim_path, encoding="utf-8", errors="replace").read()
    except Exception:                                         # noqa: BLE001
        return None
    match = _SHIM_SCRIPT_RE.search(body)
    if not match:
        return None
    shim_dir = os.path.dirname(os.path.abspath(shim_path))
    script = os.path.normpath(os.path.join(shim_dir, match.group(1)))
    if not os.path.exists(script):
        # Never point at a payload that is not there: a clean "not found" from
        # the real command is far more useful than a confident wrong argv.
        return None
    node = _node_for(shim_dir)
    if not node:
        return None
    return [node, script]


def resolve_argv_prefix(command: str) -> Tuple[List[str], bool, str]:
    """Resolve ``command`` into ``(argv_prefix, needs_shell, note)``.

    ``argv_prefix`` is everything that goes BEFORE the caller's own arguments,
    so a caller builds ``[*argv_prefix, *its_args]``. ``needs_shell`` is True
    only for a shim that could not be rewritten. ``note`` is a short human
    string for logs and doctors; it is never load-bearing.

    On POSIX this is a pass-through: there are no batch shims to unwrap.
    """
    cmd = (command or "").strip()
    if not cmd:
        return [], False, ""
    if os.name != "nt":
        return [cmd], False, ""

    has_sep = ("/" in cmd) or ("\\" in cmd)
    if has_sep:
        if not os.path.exists(cmd):
            # Hand it back untouched so the spawn raises a truthful
            # FileNotFoundError instead of us guessing.
            return [cmd], is_shim(cmd), "path does not exist"
        resolved = cmd
    else:
        resolved = find_on_path(cmd)
        if not resolved:
            return [cmd], False, "not found on PATH"

    if not is_shim(resolved):
        return [resolved], False, ""

    direct = deshim(resolved)
    if direct:
        return direct, False, "de-shimmed to %s" % os.path.basename(direct[0])
    return [resolved], True, "batch shim, could not be rewritten (shell required)"


__all__ = [
    "WIN_EXTS",
    "SHIM_EXTS",
    "is_shim",
    "find_on_path",
    "deshim",
    "resolve_argv_prefix",
]
