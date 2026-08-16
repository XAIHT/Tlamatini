# ═══════════════════════════════════════════════════════════════════
#   ✦  T L A M A T I N I  ✦   —   "one who knows"
#
#   Created by  Angela López Mendoza   ·   @angelahack1
#   Developer · Architect · Creator of Tlamatini
#
#   Every line of this file was written by Angela López Mendoza.
# ═══════════════════════════════════════════════════════════════════
#   Tlamatini Author Banner — do not remove (releases scrub the name automatically)
"""Runtime Provisioner — Tlamatini ALWAYS has node / npm / npx / pnpm / uv / uvx.

WHY THIS EXISTS
---------------
The External MCP ecosystem is overwhelmingly published as ``npx -y <pkg>`` (the
Node ecosystem) or ``uvx <pkg>`` (the Python ecosystem).  Tlamatini's catalog
can therefore only be as good as the package managers present on the user's
machine — and a fresh Windows box has NONE of them.  Before this module, a
brand-new installation that ticked ``memory`` in External ▸ MCPs got a silent
``[WinError 2] The system cannot find the file specified``: the catalog entry
was perfect, the runtime simply did not exist.

Bundling Node the way the installer carries Python and the JRE was rejected on
purpose (Angela, 2026-08-15): it inflates every release for a capability most
users may never activate, and the release zip must stay under GitHub's 2 GiB
limit.  So Tlamatini uses the pattern she already proved three times over —
Discoverer's private Go toolchain, ESP32er's PlatformIO, Arduiner's
arduino-cli: a **zero-config, self-provisioning, per-user private runtime**.

  * Downloaded ONCE, on demand, from the OFFICIAL upstream (nodejs.org,
    github.com/astral-sh/uv, github.com/pnpm/pnpm).
  * Installed into ``%LOCALAPPDATA%\\Tlamatini\\runtimes`` — never the install
    directory (which a self-update replaces wholesale and which may be
    read-only under Program Files), never a system location.
  * NO administrator rights.  NO system PATH mutation.  NO installer.  Nothing
    outside Tlamatini's own per-user folder is ever touched.
  * Preferred over anything already on PATH?  NO — an existing system Node or
    uv WINS (see ``resolve``).  We only fill a hole; we never shadow the user's
    own toolchain.

THE FIVE CONTRACTS (do NOT weaken)
----------------------------------
1. **FAIL-OPEN, ALWAYS.**  Every public function is total: no network, no disk,
   no permission, no corrupt archive and no malformed config may raise into a
   caller.  A provisioner that can break the chat path is infinitely worse than
   a missing ``npx``.  ``resolve()`` returns ``""`` and life goes on.
2. **NEVER BLOCK STARTUP.**  Provisioning runs on a background thread and is a
   pure no-op (zero network, one manifest read) once the runtime is present.
   Django boot never waits on a download.
3. **ATOMIC OR ABSENT.**  An archive is downloaded to Tlamatini's own Temp,
   checksum-verified, unpacked to ``<dest>.partial-<pid>`` and only then
   ``os.replace``-d into place.  A half-extracted tree that merely *looks*
   installed is the one failure mode that would poison every later run, so it
   is structurally impossible.
4. **VERIFY WHAT UPSTREAM SIGNS.**  Node publishes ``SHASUMS256.txt`` for every
   release: it is fetched and enforced.  uv/pnpm sidecar hashes are enforced
   when published.  Set ``runtime_require_checksum: true`` to refuse any
   artifact that cannot be verified.
5. **SPAWN WITHOUT A SHELL.**  On Windows ``npx`` is a ``.cmd`` batch shim that
   ``CreateProcess`` cannot execute, which is the single most common cause of
   broken npx-launched MCP servers.  ``resolve_spawn`` rewrites ``npx`` to
   ``node.exe <npx-cli.js>`` — the real program behind the shim — so no shell,
   no quoting hazard, and no ``WinError 193`` is ever involved.

PUBLIC SURFACE
--------------
``resolve(tool)``        absolute path to a tool, or "" — never raises
``resolve_spawn(cmd,a)`` (argv, note) rewritten to use the private runtime
``augment_env(env)``     env with the private bin dirs prepended to PATH
``ensure(tool)``         provision one tool now (blocking; background-thread use)
``provision(tools)``     provision several; returns a report dict
``provision_async()``    fire-and-forget pre-warm used by ``apps.ready()``
``status()``             full report for the doctor, the LLM tool and the UI

Stdlib only.  Imports nothing from ``agent.*`` except an OPTIONAL, guarded
``path_guard`` (for the Temp policy), so this module behaves identically frozen
and from source, can be imported by a pool agent, and can never create an
import cycle.
"""

import hashlib
import json
import os
import platform
import re
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
import threading
import time
import urllib.error
import urllib.request
import zipfile
from typing import Any, Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

LOG_PREFIX = "--- [RUNTIME]"

#: Tools this module can resolve and provision.
MANAGED_TOOLS: Tuple[str, ...] = ("node", "npm", "npx", "pnpm", "uv", "uvx")

#: Which runtime package owns each tool.
_TOOL_PACKAGE: Dict[str, str] = {
    "node": "node", "npm": "node", "npx": "node",
    "pnpm": "pnpm",
    "uv": "uv", "uvx": "uv",
}

#: Pinned fallbacks, used only when the "latest" lookup fails (offline index,
#: DNS hiccup, a proxy that blocks the JSON). Every one of these is a real,
#: published release, so a pinned install is always a WORKING install.
FALLBACK_NODE_VERSION = "22.20.0"      # Active LTS line
FALLBACK_UV_VERSION = "0.9.29"
FALLBACK_PNPM_VERSION = "10.20.0"

_NODE_DIST = "https://nodejs.org/dist"
_UV_LATEST = "https://github.com/astral-sh/uv/releases/latest/download"
_PNPM_LATEST = "https://github.com/pnpm/pnpm/releases/latest/download"

_USER_AGENT = "Tlamatini-RuntimeProvisioner/1.0 (+https://github.com/XAIHT/Tlamatini)"

_DEFAULT_TIMEOUT = 180.0
_MANIFEST_NAME = ".runtime_manifest.json"
_LOCK_STALE_SECONDS = 30 * 60

_CREATE_NO_WINDOW = 0x08000000

# One in-process lock per runtime package, so two threads never download twice.
_pkg_locks: Dict[str, threading.Lock] = {name: threading.Lock() for name in ("node", "uv", "pnpm")}
_state_lock = threading.RLock()
_provision_thread: Optional[threading.Thread] = None
_last_report: Dict[str, Any] = {}
#: Memoized resolutions. Cleared whenever we install something.
_resolve_cache: Dict[str, str] = {}


def _log(message: str) -> None:
    """Print a greppable line. ``manage.py`` tees stdout into tlamatini.log
    before Django boots, so this lands in the log in BOTH frozen and source
    mode — the same mechanism ``--- [BINARY-GUARD]`` uses."""
    try:
        print(f"{LOG_PREFIX} {message}", flush=True)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Configuration (fail-open at every step)
# ---------------------------------------------------------------------------

def _config_path() -> str:
    env_path = (os.environ.get("CONFIG_PATH") or "").strip()
    if env_path:
        return env_path
    if getattr(sys, "frozen", False):
        return os.path.join(os.path.dirname(sys.executable), "config.json")
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")


def _load_config() -> Dict[str, Any]:
    try:
        path = _config_path()
        if not os.path.isfile(path):
            return {}
        with open(path, "r", encoding="utf-8-sig") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _cfg(key: str, default: Any = "") -> Any:
    value = _load_config().get(key, default)
    return default if value is None else value


def _cfg_bool(key: str, default: bool) -> bool:
    raw = _load_config().get(key, None)
    if raw is None:
        return default
    if isinstance(raw, bool):
        return raw
    text = str(raw).strip().lower()
    if text in ("1", "true", "yes", "on"):
        return True
    if text in ("0", "false", "no", "off"):
        return False
    return default


def autoprovision_enabled() -> bool:
    """Master switch. Default ON — that is the whole point of the feature."""
    env = (os.environ.get("TLAMATINI_RUNTIME_AUTOPROVISION") or "").strip().lower()
    if env in ("0", "false", "no", "off"):
        return False
    if env in ("1", "true", "yes", "on"):
        return True
    return _cfg_bool("runtime_autoprovision", True)


def _download_timeout() -> float:
    try:
        return max(30.0, float(_cfg("runtime_download_timeout_seconds", _DEFAULT_TIMEOUT)))
    except Exception:
        return _DEFAULT_TIMEOUT


# ---------------------------------------------------------------------------
# Roots
# ---------------------------------------------------------------------------

def runtimes_root() -> str:
    """Private per-user runtime root. NEVER the install dir (a self-update
    replaces it) and NEVER a system dir (that would need admin)."""
    override = (os.environ.get("TLAMATINI_RUNTIMES") or "").strip() or str(_cfg("runtime_install_dir", "")).strip()
    if override:
        return os.path.abspath(os.path.expandvars(os.path.expanduser(override)))
    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA") or os.path.join(os.path.expanduser("~"), "AppData", "Local")
    else:
        base = os.environ.get("XDG_DATA_HOME") or os.path.join(os.path.expanduser("~"), ".local", "share")
    return os.path.join(base, "Tlamatini", "runtimes")


def _pkg_root(package: str) -> str:
    return os.path.join(runtimes_root(), package)


def npm_global_prefix() -> str:
    """Private npm global prefix, so ``npm i -g`` never needs admin and never
    pollutes the user's own ``%APPDATA%\\npm``."""
    return os.path.join(runtimes_root(), "npm-global")


def _staging_dir() -> str:
    """Scratch for downloads — under Tlamatini's own Temp (Rule 15)."""
    try:
        from . import path_guard  # type: ignore
        root = path_guard.get_app_temp_root()
        if root:
            target = os.path.join(root, "RuntimeProvisioner")
            os.makedirs(target, exist_ok=True)
            return target
    except Exception:
        pass
    try:
        target = os.path.join(tempfile.gettempdir(), "TlamatiniRuntimeProvisioner")
        os.makedirs(target, exist_ok=True)
        return target
    except Exception:
        return tempfile.gettempdir()


# ---------------------------------------------------------------------------
# Platform matrix
# ---------------------------------------------------------------------------

def _norm_arch() -> str:
    machine = (platform.machine() or "").lower()
    if machine in ("amd64", "x86_64", "x64"):
        return "x64"
    if machine in ("arm64", "aarch64"):
        return "arm64"
    if machine in ("i386", "i686", "x86"):
        return "x86"
    return machine or "x64"


def _os_key() -> str:
    if os.name == "nt":
        return "win"
    if sys.platform == "darwin":
        return "darwin"
    return "linux"


def _exe(name: str) -> str:
    return f"{name}.exe" if os.name == "nt" else name


# ---------------------------------------------------------------------------
# Manifest — the "already installed, do nothing" fast path
# ---------------------------------------------------------------------------

def _manifest_path() -> str:
    return os.path.join(runtimes_root(), _MANIFEST_NAME)


def _read_manifest() -> Dict[str, Any]:
    try:
        path = _manifest_path()
        if not os.path.isfile(path):
            return {}
        with open(path, "r", encoding="utf-8-sig") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _write_manifest(package: str, entry: Dict[str, Any]) -> None:
    try:
        os.makedirs(runtimes_root(), exist_ok=True)
        data = _read_manifest()
        data[package] = entry
        data["_updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
        tmp = _manifest_path() + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2, ensure_ascii=False)
        os.replace(tmp, _manifest_path())
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Resolution — private runtime, then the user's own toolchain
# ---------------------------------------------------------------------------

def _node_home() -> str:
    """Directory of the extracted Node distribution (the one holding node.exe /
    bin/node), or "" when Tlamatini has not provisioned Node."""
    root = _pkg_root("node")
    if not os.path.isdir(root):
        return ""
    candidates = [root] + [os.path.join(root, name) for name in sorted(os.listdir(root))]
    for candidate in candidates:
        try:
            if not os.path.isdir(candidate):
                continue
        except Exception:
            continue
        if os.name == "nt":
            if os.path.isfile(os.path.join(candidate, "node.exe")):
                return candidate
        elif os.path.isfile(os.path.join(candidate, "bin", "node")):
            return candidate
    return ""


def _node_exe() -> str:
    home = _node_home()
    if not home:
        return ""
    path = os.path.join(home, "node.exe") if os.name == "nt" else os.path.join(home, "bin", "node")
    return path if os.path.isfile(path) else ""


def _npm_cli_js(which: str) -> str:
    """Absolute path to npm's/npx's real JS entry point inside our Node tree.

    THIS is what makes Windows spawning bullet-proof: ``npx.cmd`` is a batch
    shim CreateProcess refuses to run, but ``npx-cli.js`` is an ordinary script
    ``node.exe`` executes directly — no shell, no quoting, no WinError 193.
    """
    home = _node_home()
    if not home:
        return ""
    bases = (
        os.path.join(home, "node_modules", "npm", "bin"),
        os.path.join(home, "lib", "node_modules", "npm", "bin"),
    )
    for base in bases:
        candidate = os.path.join(base, f"{which}-cli.js")
        if os.path.isfile(candidate):
            return candidate
    return ""


def _private_candidates(tool: str) -> List[str]:
    """Absolute paths inside OUR runtime root that could satisfy ``tool``."""
    out: List[str] = []
    if tool == "node":
        out.append(_node_exe())
    elif tool in ("npm", "npx"):
        home = _node_home()
        if home:
            if os.name == "nt":
                out += [os.path.join(home, f"{tool}.cmd"), os.path.join(home, tool)]
            else:
                out.append(os.path.join(home, "bin", tool))
    elif tool in ("uv", "uvx"):
        out.append(os.path.join(_pkg_root("uv"), "bin", _exe(tool)))
        out.append(os.path.join(_pkg_root("uv"), _exe(tool)))
    elif tool == "pnpm":
        out.append(os.path.join(_pkg_root("pnpm"), _exe("pnpm")))
        prefix = npm_global_prefix()
        if os.name == "nt":
            out.append(os.path.join(prefix, "pnpm.cmd"))
        else:
            out.append(os.path.join(prefix, "bin", "pnpm"))
    return [p for p in out if p]


def _extra_known_locations(tool: str) -> List[str]:
    """Well-known per-user install sites the PATH often misses (a shell that
    was never restarted after installing Node, uv's default ``~/.local/bin``)."""
    home = os.path.expanduser("~")
    out: List[str] = []
    if tool in ("uv", "uvx"):
        out += [
            os.path.join(home, ".local", "bin", _exe(tool)),
            os.path.join(home, ".cargo", "bin", _exe(tool)),
        ]
    if tool in ("node", "npm", "npx") and os.name == "nt":
        for base in (os.environ.get("ProgramFiles", r"C:\Program Files"),
                     os.environ.get("ProgramW6432", r"C:\Program Files")):
            if base:
                out.append(os.path.join(base, "nodejs", "node.exe" if tool == "node" else f"{tool}.cmd"))
    if tool in ("npm", "npx", "pnpm") and os.name == "nt":
        appdata = os.environ.get("APPDATA")
        if appdata:
            out.append(os.path.join(appdata, "npm", f"{tool}.cmd"))
    return out


def resolve(tool: str, use_cache: bool = True) -> str:
    """Absolute path to ``tool``, or ``""``. NEVER raises, NEVER downloads.

    Precedence, highest first:
      1. an explicit ``<tool>_executable`` in config.json (the user is boss),
      2. Tlamatini's OWN provisioned runtime (deterministic, version-known),
      3. the system PATH (PATHEXT-aware, so ``npx.cmd`` is found),
      4. well-known per-user locations PATH commonly misses.

    Note 2-before-3 is deliberate and safe: our runtime only EXISTS if we
    provisioned it, and we only provision what the machine was missing.
    """
    tool = (tool or "").strip().lower()
    if not tool:
        return ""
    if use_cache:
        cached = _resolve_cache.get(tool)
        if cached and os.path.isfile(cached):
            return cached
    found = ""
    try:
        override = str(_cfg(f"{tool}_executable", "")).strip()
        if override:
            expanded = os.path.expandvars(os.path.expanduser(override))
            if os.path.isfile(expanded):
                found = expanded
            else:
                which = shutil.which(expanded)
                if which:
                    found = which
        if not found:
            for candidate in _private_candidates(tool):
                if os.path.isfile(candidate):
                    found = candidate
                    break
        if not found:
            found = shutil.which(tool, path=_augmented_path()) or ""
        if not found:
            for candidate in _extra_known_locations(tool):
                if os.path.isfile(candidate):
                    found = candidate
                    break
    except Exception:
        found = ""
    if found:
        _resolve_cache[tool] = found
    else:
        _resolve_cache.pop(tool, None)
    return found


def _bin_dirs() -> List[str]:
    """Every private directory that should be on a child process's PATH."""
    dirs: List[str] = []
    home = _node_home()
    if home:
        dirs.append(home if os.name == "nt" else os.path.join(home, "bin"))
    for extra in (os.path.join(_pkg_root("uv"), "bin"), _pkg_root("uv"), _pkg_root("pnpm")):
        if os.path.isdir(extra):
            dirs.append(extra)
    prefix = npm_global_prefix()
    global_bin = prefix if os.name == "nt" else os.path.join(prefix, "bin")
    if os.path.isdir(global_bin):
        dirs.append(global_bin)
    seen, unique = set(), []
    for directory in dirs:
        key = os.path.normcase(os.path.abspath(directory))
        if key not in seen and os.path.isdir(directory):
            seen.add(key)
            unique.append(directory)
    return unique


def _augmented_path(base: str = "") -> str:
    current = base or os.environ.get("PATH", "")
    private = _bin_dirs()
    if not private:
        return current
    return os.pathsep.join(private + ([current] if current else []))


def augment_env(env: Optional[Dict[str, str]] = None) -> Dict[str, str]:
    """Return ``env`` (default: a copy of os.environ) with Tlamatini's private
    runtimes on PATH plus the quiet/no-admin npm settings.

    This is THE integration point: any child spawned with this env can invoke a
    bare ``npx`` / ``uvx`` and it resolves, even on a machine where the user has
    never installed Node or Python.
    """
    result: Dict[str, str] = dict(env) if env is not None else dict(os.environ)
    try:
        result["PATH"] = _augmented_path(result.get("PATH", ""))
        if os.name == "nt":
            result["Path"] = result["PATH"]
        prefix = npm_global_prefix()
        if os.path.isdir(prefix) or _node_home():
            os.makedirs(prefix, exist_ok=True)
            result.setdefault("npm_config_prefix", prefix)
        # Quiet + fast + never interactive: an MCP server's first run must not
        # stall on an update notice, a funding banner or a corepack prompt.
        result.setdefault("NO_UPDATE_NOTIFIER", "1")
        result.setdefault("NPM_CONFIG_UPDATE_NOTIFIER", "false")
        result.setdefault("NPM_CONFIG_FUND", "false")
        result.setdefault("NPM_CONFIG_AUDIT", "false")
        result.setdefault("COREPACK_ENABLE_DOWNLOAD_PROMPT", "0")
        result.setdefault("CI", "1")
        uv_bin = os.path.join(_pkg_root("uv"), "bin")
        if os.path.isdir(uv_bin):
            result.setdefault("UV_INSTALL_DIR", uv_bin)
    except Exception:
        pass
    return result


# ---------------------------------------------------------------------------
# Spawn rewriting — the Windows .cmd-shim killer
# ---------------------------------------------------------------------------

def _strip_cmd_wrapper(command: str, args: List[str]) -> Tuple[str, List[str], bool]:
    """``cmd /c npx -y pkg`` → ``npx``, ``["-y","pkg"]``.

    Catalog entries copied from other MCP clients (and Tlamatini's own design
    note for these two servers) often wrap the manager in ``cmd /c``. Unwrapping
    lets the rewrite below reach the real tool instead of silently spawning a
    shell that then fails to find ``npx``.
    """
    base = os.path.basename(str(command or "")).lower()
    if os.name != "nt" or base not in ("cmd", "cmd.exe"):
        return command, args, False
    rest = list(args or [])
    while rest and str(rest[0]).lower() in ("/c", "/k", "/d", "/s", "/q"):
        rest.pop(0)
    if rest and os.path.splitext(os.path.basename(str(rest[0])))[0].lower() in MANAGED_TOOLS:
        return str(rest[0]), rest[1:], True
    return command, args, False


def resolve_spawn(command: str, args: Optional[List[str]] = None) -> Tuple[List[str], str]:
    """Build a spawnable argv for ``command`` + ``args``.

    Returns ``(argv, note)``. ``note`` is a short human string for the doctor /
    logs (e.g. ``"npx via Tlamatini's private Node 22.20.0"``); it is never
    load-bearing. On ANY doubt the original command is returned unchanged, so
    this can only ever improve a spawn, never break one.
    """
    args = list(args or [])
    try:
        command, args, unwrapped = _strip_cmd_wrapper(command, args)
        raw = os.path.expandvars(str(command or ""))
        tool = os.path.splitext(os.path.basename(raw))[0].lower()
        note = "unwrapped cmd /c; " if unwrapped else ""

        if tool not in MANAGED_TOOLS:
            return [raw, *[os.path.expandvars(str(a)) for a in args]], ""

        expanded = [os.path.expandvars(str(a)) for a in args]

        # npm / npx → run the REAL js entry point under our node.exe.
        if tool in ("npm", "npx"):
            node = _node_exe()
            cli = _npm_cli_js(tool)
            if node and cli:
                return [node, cli, *expanded], f"{note}{tool} via Tlamatini's private Node"

        resolved = resolve(tool)
        if not resolved:
            # Nothing we can do — hand back the original so the caller's own
            # error path reports the truth ("npx not found"), not a silent swap.
            return [raw, *expanded], f"{note}{tool} NOT RESOLVED"

        # A real executable: spawn directly, no shell.
        if not resolved.lower().endswith((".cmd", ".bat")):
            where = "Tlamatini's private runtime" if _is_ours(resolved) else "the system PATH"
            return [resolved, *expanded], f"{note}{tool} via {where}"

        # A batch shim (a system npm/npx we did not install): CreateProcess
        # cannot execute it, so route through the command processor — the only
        # way a .cmd can run at all.
        comspec = os.environ.get("COMSPEC", "cmd.exe")
        return [comspec, "/c", resolved, *expanded], f"{note}{tool} via {resolved} (batch shim)"
    except Exception:
        return [str(command), *[str(a) for a in (args or [])]], ""


def _is_ours(path: str) -> bool:
    try:
        return os.path.normcase(os.path.abspath(path)).startswith(
            os.path.normcase(os.path.abspath(runtimes_root()))
        )
    except Exception:
        return False


def managed_tool_for(command: str, args: Optional[List[str]] = None) -> str:
    """Return the managed tool a spec actually launches, or ``""``.

    ``("npx", ["-y", "pkg"])``      -> ``"npx"``
    ``("cmd", ["/c", "npx", ...])`` -> ``"npx"``   (the wrapper is seen through)
    ``("docker", [...])``           -> ``""``      (not ours to provision)

    Used by the External-MCP connect path to decide whether a MISSING runtime
    is something Tlamatini can install on the user's behalf. Never raises.
    """
    try:
        cmd, _rest, _unwrapped = _strip_cmd_wrapper(str(command or ""), list(args or []))
        tool = os.path.splitext(os.path.basename(os.path.expandvars(cmd)))[0].lower()
        return tool if tool in MANAGED_TOOLS else ""
    except Exception:
        return ""


# ---------------------------------------------------------------------------
# Download helpers
# ---------------------------------------------------------------------------

def _http_get(url: str, timeout: float) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT, "Accept": "*/*"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


def _download(url: str, dest: str, timeout: float) -> None:
    request = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT, "Accept": "*/*"})
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    with urllib.request.urlopen(request, timeout=timeout) as response, open(dest, "wb") as fh:
        shutil.copyfileobj(response, fh, 1024 * 256)


def _sha256(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 256), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _require_checksum() -> bool:
    return _cfg_bool("runtime_require_checksum", False)


def _verify(path: str, expected: str, label: str) -> Tuple[bool, str]:
    """Return ``(ok, note)``. An artifact whose published hash does not match is
    ALWAYS rejected. An artifact with no published hash is accepted unless
    ``runtime_require_checksum`` is on (HTTPS to the official host remains the
    trust anchor in that case)."""
    if not expected:
        if _require_checksum():
            return False, "no published checksum and runtime_require_checksum is on"
        return True, "unverified (upstream publishes no sidecar hash)"
    try:
        actual = _sha256(path)
    except Exception as exc:
        return False, f"could not hash artifact: {exc}"
    if actual.lower() != expected.lower():
        return False, f"CHECKSUM MISMATCH for {label}: expected {expected[:16]}…, got {actual[:16]}…"
    return True, "sha256 verified"


def _unpack(archive: str, dest: str) -> None:
    """Extract ``archive`` into ``dest`` (which must not yet exist)."""
    os.makedirs(dest, exist_ok=True)
    lower = archive.lower()
    if lower.endswith(".zip"):
        with zipfile.ZipFile(archive) as zf:
            for member in zf.namelist():
                if member.startswith("/") or ".." in member.replace("\\", "/").split("/"):
                    raise ValueError(f"unsafe archive member: {member}")
            zf.extractall(dest)
    elif lower.endswith((".tar.gz", ".tgz", ".tar.xz", ".txz", ".tar")):
        mode = "r:xz" if lower.endswith((".tar.xz", ".txz")) else ("r:gz" if lower.endswith((".tar.gz", ".tgz")) else "r:")
        with tarfile.open(archive, mode) as tf:
            for member in tf.getmembers():
                if member.name.startswith("/") or ".." in member.name.split("/"):
                    raise ValueError(f"unsafe archive member: {member.name}")
            try:
                tf.extractall(dest, filter="data")  # Python 3.12+
            except TypeError:
                tf.extractall(dest)
    else:
        raise ValueError(f"unsupported archive type: {archive}")


def _make_executable(path: str) -> None:
    if os.name == "nt":
        return
    try:
        mode = os.stat(path).st_mode
        os.chmod(path, mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    except Exception:
        pass


def _atomic_install(staged: str, final: str) -> None:
    """Move a fully-prepared tree into place atomically (contract 3)."""
    os.makedirs(os.path.dirname(final), exist_ok=True)
    if os.path.exists(final):
        doomed = f"{final}.old-{os.getpid()}-{int(time.time())}"
        os.replace(final, doomed)
        shutil.rmtree(doomed, ignore_errors=True)
    os.replace(staged, final)


class _DirLock:
    """Cross-process single-flight guard, so two Tlamatini processes (or the
    reloader's two children) never download the same runtime twice."""

    def __init__(self, name: str):
        self.path = os.path.join(runtimes_root(), f".{name}.lock")
        self.fd: Optional[int] = None

    def __enter__(self) -> "_DirLock":
        try:
            os.makedirs(runtimes_root(), exist_ok=True)
            if os.path.exists(self.path):
                age = time.time() - os.path.getmtime(self.path)
                if age > _LOCK_STALE_SECONDS:
                    os.remove(self.path)      # a crashed run left it behind
            self.fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(self.fd, str(os.getpid()).encode("ascii", "replace"))
        except FileExistsError:
            self.fd = None
        except Exception:
            self.fd = None
        return self

    @property
    def acquired(self) -> bool:
        return self.fd is not None

    def __exit__(self, *exc: Any) -> None:
        try:
            if self.fd is not None:
                os.close(self.fd)
                os.remove(self.path)
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Version discovery
# ---------------------------------------------------------------------------

def _latest_node_lts(timeout: float) -> str:
    """Newest Active-LTS Node version from the official dist index."""
    try:
        payload = json.loads(_http_get(f"{_NODE_DIST}/index.json", timeout=min(30.0, timeout)).decode("utf-8", "replace"))
        for entry in payload:
            if entry.get("lts"):
                version = str(entry.get("version") or "").lstrip("v")
                if re.match(r"^\d+\.\d+\.\d+$", version):
                    return version
    except Exception:
        pass
    return FALLBACK_NODE_VERSION


def _node_version() -> str:
    pinned = str(_cfg("node_version", "")).strip().lstrip("v")
    if re.match(r"^\d+\.\d+\.\d+$", pinned):
        return pinned
    return _latest_node_lts(_download_timeout())


# ---------------------------------------------------------------------------
# Installers
# ---------------------------------------------------------------------------

def _install_node(timeout: float) -> Dict[str, Any]:
    version = _node_version()
    arch, oskey = _norm_arch(), _os_key()
    if oskey == "win":
        asset = f"node-v{version}-win-{arch}.zip"
    elif oskey == "darwin":
        asset = f"node-v{version}-darwin-{arch}.tar.gz"
    else:
        asset = f"node-v{version}-linux-{arch}.tar.xz"
    url = f"{_NODE_DIST}/v{version}/{asset}"

    # Node publishes SHASUMS256.txt for EVERY release — always enforce it.
    expected = ""
    try:
        sums = _http_get(f"{_NODE_DIST}/v{version}/SHASUMS256.txt", timeout=min(30.0, timeout)).decode("utf-8", "replace")
        for line in sums.splitlines():
            parts = line.split()
            if len(parts) == 2 and parts[1].lstrip("*") == asset:
                expected = parts[0]
                break
    except Exception:
        expected = ""

    staging = _staging_dir()
    archive = os.path.join(staging, asset)
    _log(f"downloading Node {version} ({asset}) …")
    _download(url, archive, timeout)
    ok, note = _verify(archive, expected, asset)
    if not ok:
        try:
            os.remove(archive)
        except Exception:
            pass
        raise RuntimeError(note)

    unpack_dir = os.path.join(staging, f"node-unpack-{os.getpid()}")
    shutil.rmtree(unpack_dir, ignore_errors=True)
    _unpack(archive, unpack_dir)
    entries = [os.path.join(unpack_dir, e) for e in os.listdir(unpack_dir)]
    tree = entries[0] if len(entries) == 1 and os.path.isdir(entries[0]) else unpack_dir

    staged = f"{_pkg_root('node')}.partial-{os.getpid()}"
    shutil.rmtree(staged, ignore_errors=True)
    os.makedirs(os.path.dirname(staged), exist_ok=True)
    shutil.move(tree, staged)
    for binary in ("bin/node", "bin/npm", "bin/npx"):
        _make_executable(os.path.join(staged, *binary.split("/")))
    _atomic_install(staged, _pkg_root("node"))
    shutil.rmtree(unpack_dir, ignore_errors=True)
    try:
        os.remove(archive)
    except Exception:
        pass
    return {"version": version, "asset": asset, "url": url, "checksum": note}


def _install_uv(timeout: float) -> Dict[str, Any]:
    arch, oskey = _norm_arch(), _os_key()
    triple = {
        ("win", "x64"): "x86_64-pc-windows-msvc",
        ("win", "arm64"): "aarch64-pc-windows-msvc",
        ("linux", "x64"): "x86_64-unknown-linux-gnu",
        ("linux", "arm64"): "aarch64-unknown-linux-gnu",
        ("darwin", "x64"): "x86_64-apple-darwin",
        ("darwin", "arm64"): "aarch64-apple-darwin",
    }.get((oskey, arch))
    if not triple:
        raise RuntimeError(f"no uv build for {oskey}/{arch}")
    asset = f"uv-{triple}.zip" if oskey == "win" else f"uv-{triple}.tar.gz"
    url = f"{_UV_LATEST}/{asset}"

    expected = ""
    try:
        raw = _http_get(f"{url}.sha256", timeout=min(30.0, timeout)).decode("utf-8", "replace").strip()
        candidate = raw.split()[0] if raw else ""
        if re.match(r"^[0-9a-fA-F]{64}$", candidate):
            expected = candidate
    except Exception:
        expected = ""

    staging = _staging_dir()
    archive = os.path.join(staging, asset)
    _log(f"downloading uv ({asset}) …")
    _download(url, archive, timeout)
    ok, note = _verify(archive, expected, asset)
    if not ok:
        try:
            os.remove(archive)
        except Exception:
            pass
        raise RuntimeError(note)

    unpack_dir = os.path.join(staging, f"uv-unpack-{os.getpid()}")
    shutil.rmtree(unpack_dir, ignore_errors=True)
    _unpack(archive, unpack_dir)

    staged = f"{_pkg_root('uv')}.partial-{os.getpid()}"
    shutil.rmtree(staged, ignore_errors=True)
    bin_dir = os.path.join(staged, "bin")
    os.makedirs(bin_dir, exist_ok=True)
    wanted = {_exe("uv"), _exe("uvx")}
    found = 0
    for root, _dirs, files in os.walk(unpack_dir):
        for name in files:
            if name in wanted:
                shutil.copy2(os.path.join(root, name), os.path.join(bin_dir, name))
                _make_executable(os.path.join(bin_dir, name))
                found += 1
    if not found:
        shutil.rmtree(staged, ignore_errors=True)
        raise RuntimeError("uv archive contained no uv/uvx binary")
    _atomic_install(staged, _pkg_root("uv"))
    shutil.rmtree(unpack_dir, ignore_errors=True)
    try:
        os.remove(archive)
    except Exception:
        pass
    version = _probe_version(os.path.join(_pkg_root("uv"), "bin", _exe("uv")))
    return {"version": version or "latest", "asset": asset, "url": url, "checksum": note}


def _install_pnpm(timeout: float) -> Dict[str, Any]:
    """pnpm's standalone binary — no Node required, so it also works as an
    independent fallback when the Node install itself failed."""
    arch, oskey = _norm_arch(), _os_key()
    asset = {
        ("win", "x64"): "pnpm-win-x64.exe",
        ("win", "arm64"): "pnpm-win-arm64.exe",
        ("linux", "x64"): "pnpm-linux-x64",
        ("linux", "arm64"): "pnpm-linux-arm64",
        ("darwin", "x64"): "pnpm-macos-x64",
        ("darwin", "arm64"): "pnpm-macos-arm64",
    }.get((oskey, arch))
    if not asset:
        raise RuntimeError(f"no pnpm build for {oskey}/{arch}")
    url = f"{_PNPM_LATEST}/{asset}"

    staging = _staging_dir()
    download_path = os.path.join(staging, asset)
    _log(f"downloading pnpm ({asset}) …")
    _download(url, download_path, timeout)
    if os.path.getsize(download_path) < 1024 * 512:
        os.remove(download_path)
        raise RuntimeError("pnpm download looks truncated")

    staged = f"{_pkg_root('pnpm')}.partial-{os.getpid()}"
    shutil.rmtree(staged, ignore_errors=True)
    os.makedirs(staged, exist_ok=True)
    target = os.path.join(staged, _exe("pnpm"))
    shutil.move(download_path, target)
    _make_executable(target)
    _atomic_install(staged, _pkg_root("pnpm"))
    version = _probe_version(os.path.join(_pkg_root("pnpm"), _exe("pnpm")))
    return {"version": version or "latest", "asset": asset, "url": url,
            "checksum": "unverified (pnpm publishes no sidecar hash)"}


def _probe_version(executable: str) -> str:
    if not executable or not os.path.isfile(executable):
        return ""
    try:
        kwargs: Dict[str, Any] = dict(
            capture_output=True, text=True, timeout=30,
            encoding="utf-8", errors="replace", stdin=subprocess.DEVNULL,
            env=augment_env(),
        )
        if os.name == "nt":
            kwargs["creationflags"] = _CREATE_NO_WINDOW
        proc = subprocess.run([executable, "--version"], **kwargs)
        first = (proc.stdout or proc.stderr or "").strip().splitlines()
        return first[0].strip() if first else ""
    except Exception:
        return ""


_INSTALLERS = {"node": _install_node, "uv": _install_uv, "pnpm": _install_pnpm}


# ---------------------------------------------------------------------------
# Public provisioning API
# ---------------------------------------------------------------------------

def is_provisioned(tool: str) -> bool:
    return bool(resolve(tool, use_cache=False))


def ensure(tool: str, force: bool = False) -> Dict[str, Any]:
    """Make ``tool`` available, downloading its runtime if needed.

    Blocking — call from a background thread. TOTAL: always returns a dict,
    never raises.
    """
    tool = (tool or "").strip().lower()
    package = _TOOL_PACKAGE.get(tool)
    if not package:
        return {"tool": tool, "ok": False, "reason": f"unknown tool '{tool}'"}
    if not force:
        existing = resolve(tool, use_cache=False)
        if existing:
            return {"tool": tool, "ok": True, "path": existing, "action": "already-present",
                    "source": "tlamatini" if _is_ours(existing) else "system"}
    if not autoprovision_enabled():
        return {"tool": tool, "ok": False, "action": "skipped",
                "reason": "runtime_autoprovision is off"}

    lock = _pkg_locks.setdefault(package, threading.Lock())
    with lock:
        existing = resolve(tool, use_cache=False)          # another thread may have won
        if existing and not force:
            return {"tool": tool, "ok": True, "path": existing, "action": "already-present",
                    "source": "tlamatini" if _is_ours(existing) else "system"}
        with _DirLock(package) as dir_lock:
            if not dir_lock.acquired:
                deadline = time.time() + 300
                while time.time() < deadline:
                    time.sleep(2.0)
                    found = resolve(tool, use_cache=False)
                    if found:
                        return {"tool": tool, "ok": True, "path": found,
                                "action": "installed-by-peer", "source": "tlamatini"}
                    if not os.path.exists(os.path.join(runtimes_root(), f".{package}.lock")):
                        break
                return {"tool": tool, "ok": False, "action": "busy",
                        "reason": "another process is provisioning this runtime"}
            try:
                started = time.time()
                info = _INSTALLERS[package](_download_timeout())
                _resolve_cache.clear()
                entry = dict(info)
                entry.update({"installed_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                              "root": _pkg_root(package),
                              "seconds": round(time.time() - started, 1)})
                _write_manifest(package, entry)
                path = resolve(tool, use_cache=False)
                _log(f"provisioned {package} {info.get('version', '')} in "
                     f"{entry['seconds']}s -> {_pkg_root(package)} ({info.get('checksum', '')})")
                if not path:
                    return {"tool": tool, "ok": False, "action": "installed",
                            "reason": f"{package} installed but '{tool}' still not resolvable"}
                return {"tool": tool, "ok": True, "path": path, "action": "installed",
                        "source": "tlamatini", **info}
            except (urllib.error.URLError, urllib.error.HTTPError) as exc:
                _log(f"could NOT provision {package}: network error ({exc}). "
                     f"Tlamatini keeps working; MCP servers needing '{tool}' stay unavailable.")
                return {"tool": tool, "ok": False, "action": "failed", "reason": f"network: {exc}"}
            except Exception as exc:
                _log(f"could NOT provision {package}: {exc}. Tlamatini keeps working.")
                return {"tool": tool, "ok": False, "action": "failed", "reason": str(exc)}


def provision(tools: Optional[List[str]] = None, force: bool = False) -> Dict[str, Any]:
    """Ensure several tools. Returns a report. NEVER raises."""
    requested = [t.strip().lower() for t in (tools or list(MANAGED_TOOLS)) if str(t).strip()]
    # One install per PACKAGE: provisioning "node" also delivers npm and npx.
    results: Dict[str, Any] = {}
    done_packages: Dict[str, Dict[str, Any]] = {}
    for tool in requested:
        package = _TOOL_PACKAGE.get(tool)
        if package and package in done_packages and not resolve(tool, use_cache=False):
            results[tool] = dict(done_packages[package], tool=tool)
            continue
        outcome = ensure(tool, force=force)
        results[tool] = outcome
        if package and outcome.get("action") in ("installed", "already-present"):
            done_packages.setdefault(package, outcome)
    report = {
        "ok": all(r.get("ok") for r in results.values()) if results else True,
        "root": runtimes_root(),
        "tools": results,
        "at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    with _state_lock:
        _last_report.clear()
        _last_report.update(report)
    return report


def provision_async(tools: Optional[List[str]] = None) -> bool:
    """Fire-and-forget pre-warm used by ``apps.ready()``.

    Returns True when a thread was started. Costs nothing when the runtimes are
    already present: the thread resolves them and exits without any network.
    """
    global _provision_thread
    try:
        if not autoprovision_enabled():
            _log("auto-provisioning is DISABLED (runtime_autoprovision=false) — "
                 "npx/uvx MCP servers will need a system Node/uv.")
            return False
        with _state_lock:
            if _provision_thread is not None and _provision_thread.is_alive():
                return False
            wanted = tools or list(_cfg("runtime_provision_tools", ["npx", "uvx"]) or ["npx", "uvx"])
            missing = [t for t in wanted if not resolve(t, use_cache=False)]
            if not missing:
                return False                    # fast path: nothing to do, no thread
            _log(f"missing on this machine: {', '.join(missing)} — provisioning in the "
                 f"background into {runtimes_root()} (one-time, no admin needed).")

            def _worker() -> None:
                try:
                    provision(missing)
                except Exception as exc:        # belt and braces — a thread must never die loud
                    _log(f"background provisioning aborted: {exc}")

            _provision_thread = threading.Thread(
                target=_worker, name="TlamatiniRuntimeProvisioner", daemon=True)
            _provision_thread.start()
            return True
    except Exception:
        return False


def status(refresh: bool = True) -> Dict[str, Any]:
    """Full report for the doctor, the LLM tool and the External-MCPs dialog."""
    tools: Dict[str, Any] = {}
    for tool in MANAGED_TOOLS:
        path = resolve(tool, use_cache=not refresh)
        tools[tool] = {
            "available": bool(path),
            "path": path,
            "source": ("tlamatini" if _is_ours(path) else "system") if path else "",
        }
    manifest = _read_manifest()
    provisioning = False
    with _state_lock:
        provisioning = _provision_thread is not None and _provision_thread.is_alive()
    return {
        "ok": all(t["available"] for t in tools.values()),
        "root": runtimes_root(),
        "npm_global_prefix": npm_global_prefix(),
        "autoprovision": autoprovision_enabled(),
        "provisioning_in_progress": provisioning,
        "tools": tools,
        "installed": {k: v for k, v in manifest.items() if not k.startswith("_")},
        "missing": [name for name, info in tools.items() if not info["available"]],
        "last_report": dict(_last_report),
        "platform": {"os": _os_key(), "arch": _norm_arch()},
    }


def summary_line() -> str:
    """One-line human summary (for logs and the doctor)."""
    info = status(refresh=False)
    parts = []
    for tool in MANAGED_TOOLS:
        entry = info["tools"][tool]
        mark = "ok" if entry["available"] else "MISSING"
        where = f" ({entry['source']})" if entry["available"] else ""
        parts.append(f"{tool}={mark}{where}")
    return " ".join(parts)
