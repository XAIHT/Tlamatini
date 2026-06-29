"""Tlamatini self-update — "About ▸ Check for updates".

Checks the latest GitHub release of ``XAIHT/Tlamatini``, and (in a frozen
install) downloads it, stages the new build, and hands control to the
external PowerShell updater (``apply_update.ps1``) which does a full file
swap and relaunches the app.

Why an external script does the swap
------------------------------------
A running Windows application cannot replace its own files — ``Tlamatini.exe``,
``python\\``, ``jre\\``, ``git\\`` and ``ms-playwright\\`` are all locked while
the process is alive. So this module only does the *safe-while-running* part
(check → download → unzip → stage) and then launches a copy of
``apply_update.ps1`` placed OUTSIDE the install directory. That script waits
for this process to die, swaps the files, and relaunches Tlamatini.

Preserved across the swap (everything else is replaced)::

    config.json  external_mcps.json  contacts.json  DB  application  applications  content_generated
    Temp  context_files  doc_generated  documentation  Templates
    Uninstaller.exe

    (Uninstaller.exe is built separately and is never inside pkg.zip, so the
    update swap keeps the user's existing one instead of deleting it.)

``agents`` is the one exception: it is renamed to ``agents_backup`` (one
generation kept) and then replaced by the new version's ``agents``.

The DATABASE is handled specially (not in the preserve list above, because the
live ``db.sqlite3`` lives inside ``_internal\\`` which IS replaced). Instead
``apply_update.ps1`` copies the user's DB into the preserved ``DB/ToLoad``
folder and drops ``DB/post_update_migrate.flag``; on the next launch
``manage.py`` swaps that DB back into place and runs ``migrate``. So the user's
chat history and custom Tool/Mcp/Agent toggles are KEPT while new migrations
(new agents, ``chat_agent_*`` tools, demo prompts) are applied to their data.

The download runs on a background thread; the browser polls
:func:`get_status` for progress. The module is import-safe (no Django
dependency at import time) and never raises into its callers — every public
function returns a plain dict.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import threading
import time
import urllib.request
import zipfile
from typing import Optional

# ── Constants ───────────────────────────────────────────────────────────────

GITHUB_OWNER = "XAIHT"
GITHUB_REPO = "Tlamatini"
GITHUB_API_LATEST = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/releases/latest"
RELEASES_PAGE = f"https://github.com/{GITHUB_OWNER}/{GITHUB_REPO}/releases"
_USER_AGENT = "Tlamatini-Updater"

# Approx. free space we want before downloading (release zip + extracted
# bundle + staged pkg ≈ 4×1.35 GB). Soft check — only warns.
_MIN_FREE_BYTES = 6 * 1024 * 1024 * 1024

_UPDATER_SCRIPT = "apply_update.ps1"

# ── Progress state (shared between the worker thread and the status view) ───

_lock = threading.Lock()
_STATE: dict = {
    "running": False,
    "phase": "idle",        # idle|checking|downloading|extracting|staging|handoff|done|error
    "percent": 0,
    "message": "",
    "error": "",
    "downloaded": 0,
    "total": 0,
    "version": "",
}
_worker: Optional[threading.Thread] = None


def _set_state(**kw) -> None:
    with _lock:
        _STATE.update(kw)


def get_status() -> dict:
    """Return a snapshot of the current update progress (for polling)."""
    with _lock:
        return dict(_STATE)


# ── Environment / paths ─────────────────────────────────────────────────────

def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def install_dir() -> Optional[str]:
    """The install root (the folder that holds ``Tlamatini.exe``).

    Only meaningful in a frozen build; returns ``None`` in source mode.
    """
    if not is_frozen():
        return None
    return os.path.dirname(os.path.abspath(sys.executable))


def _install_temp() -> str:
    """``<install>/Temp`` — a preserved, same-volume scratch area for staging."""
    root = install_dir() or os.getcwd()
    return os.path.join(root, "Temp")


def _update_root() -> str:
    return os.path.join(_install_temp(), "_update")


def _updater_home() -> str:
    """A directory OUTSIDE the install dir to run the updater from.

    Uses ``%LOCALAPPDATA%/Tlamatini/updater`` (same convention as the
    STM32er/ESP32er bootstraps) so the running updater never locks a file
    that the swap is about to replace.
    """
    base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA") or os.path.expanduser("~")
    return os.path.join(base, "Tlamatini", "updater")


def _current_version() -> str:
    try:
        from .version import get_version
        return get_version()
    except Exception:
        return "0.0.0+unknown"


# ── Version comparison ──────────────────────────────────────────────────────

def _version_tuple(version: str):
    """Best-effort (major, minor, patch, has_no_prerelease) tuple for compare."""
    try:
        from .version import parse_semver, _public_version
        parsed = parse_semver(_public_version(version.lstrip("vV")))
    except Exception:
        parsed = None
    if parsed:
        # A release WITHOUT a prerelease tag outranks the same with one.
        return (parsed["major"], parsed["minor"], parsed["patch"], 0 if parsed["prerelease"] else 1)
    # Fallback: crude numeric split so we never crash on a weird tag.
    nums = []
    for part in str(version).lstrip("vV").replace("-", ".").split("."):
        if part.isdigit():
            nums.append(int(part))
        else:
            break
    while len(nums) < 3:
        nums.append(0)
    return (nums[0], nums[1], nums[2], 1)


def is_newer(latest: str, current: str) -> bool:
    """True when ``latest`` is a strictly newer version than ``current``."""
    return _version_tuple(latest) > _version_tuple(current)


# ── GitHub release query ────────────────────────────────────────────────────

def _github_latest(timeout: int = 15) -> dict:
    request = urllib.request.Request(
        GITHUB_API_LATEST,
        headers={"User-Agent": _USER_AGENT, "Accept": "application/vnd.github+json"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8", "replace"))


def _select_asset(assets: list) -> Optional[dict]:
    """Pick the downloadable release-bundle zip from a release's assets.

    Prefers a ``.zip`` whose name looks like the release bundle
    (``Tlamatini_Release_*`` / contains ``win``); otherwise the largest zip.
    """
    zips = [a for a in (assets or []) if str(a.get("name", "")).lower().endswith(".zip")]
    if not zips:
        return None
    for asset in zips:
        name = str(asset.get("name", "")).lower()
        if "release" in name or "win" in name or "pkg" in name:
            return asset
    return max(zips, key=lambda a: a.get("size", 0))


def check_for_update(timeout: int = 15) -> dict:
    """Compare the running version with the latest GitHub release.

    Returns a dict the frontend renders directly. Never raises.
    """
    current = _current_version()
    result = {
        "ok": True,
        "current": current,
        "latest": "",
        "update_available": False,
        "release_name": "",
        "release_url": RELEASES_PAGE,
        "notes": "",
        "asset_name": "",
        "asset_size": 0,
        "frozen": is_frozen(),
        "busy": get_status().get("running", False),
        "error": "",
    }
    try:
        data = _github_latest(timeout=timeout)
    except Exception as exc:
        result["ok"] = False
        result["error"] = f"Could not reach GitHub: {exc}"
        return result

    tag = str(data.get("tag_name", "")).strip()
    latest = tag.lstrip("vV")
    asset = _select_asset(data.get("assets", []))
    result.update(
        latest=latest,
        release_name=str(data.get("name", "") or tag).strip(),
        release_url=str(data.get("html_url", "") or RELEASES_PAGE),
        notes=(str(data.get("body", "") or "")[:1800]),
        update_available=bool(latest) and is_newer(latest, current),
        asset_name=str(asset.get("name", "")) if asset else "",
        asset_size=int(asset.get("size", 0)) if asset else 0,
        _asset_url=str(asset.get("browser_download_url", "")) if asset else "",
    )
    if result["update_available"] and not asset:
        result["ok"] = False
        result["error"] = "A newer release exists but it has no downloadable .zip asset."
    return result


# ── Update execution (background) ───────────────────────────────────────────

def start_update() -> dict:
    """Kick off the download → stage → hand-off flow on a background thread."""
    global _worker
    if not is_frozen():
        return {"ok": False, "error": "Self-update is only available in the installed (frozen) build."}
    with _lock:
        if _STATE["running"]:
            return {"ok": False, "error": "An update is already in progress."}
        _STATE.update(running=True, phase="checking", percent=0, message="Checking latest release…",
                      error="", downloaded=0, total=0, version="")
    _worker = threading.Thread(target=_run_update, name="tlamatini-self-update", daemon=True)
    _worker.start()
    return {"ok": True, "started": True}


def _run_update() -> None:
    try:
        info = check_for_update()
        if not info.get("ok"):
            raise RuntimeError(info.get("error") or "Update check failed.")
        if not info.get("update_available"):
            _set_state(running=False, phase="done", percent=100,
                       message=f"Already on the latest version ({info.get('current')}).")
            return
        asset_url = info.get("_asset_url") or ""
        if not asset_url:
            raise RuntimeError("Latest release has no downloadable asset.")

        _set_state(version=info.get("latest", ""))
        root = _update_root()
        _reset_dir(root)
        _free_space_warning(root)

        # 1) Download the release bundle zip.
        bundle = os.path.join(root, info.get("asset_name") or "release.zip")
        _set_state(phase="downloading", percent=0, message=f"Downloading {info.get('latest')}…",
                   total=int(info.get("asset_size") or 0))
        _download(asset_url, bundle)

        # 2) Extract the bundle (it contains Installer.exe / Uninstaller.exe / pkg.zip).
        _set_state(phase="extracting", percent=0, message="Extracting release bundle…")
        bundle_dir = os.path.join(root, "bundle")
        _reset_dir(bundle_dir)
        with zipfile.ZipFile(bundle) as zf:
            zf.extractall(bundle_dir)

        pkg_zip = _locate_pkg_zip(bundle_dir)
        if not pkg_zip:
            raise RuntimeError("Release bundle did not contain pkg.zip (the install payload).")

        # 3) Extract pkg.zip into the staging dir — this IS the new install tree.
        _set_state(phase="staging", percent=0, message="Preparing the new version…")
        staging = os.path.join(root, "staging")
        _reset_dir(staging)
        with zipfile.ZipFile(pkg_zip) as zf:
            zf.extractall(staging)
        staging = _flatten_to_exe(staging)

        # Reclaim the ~1.35 GB download + bundle now that staging exists, so
        # peak disk use during the swap stays as low as possible.
        for spare in (bundle, bundle_dir):
            try:
                if os.path.isdir(spare):
                    shutil.rmtree(spare, ignore_errors=True)
                elif os.path.isfile(spare):
                    os.remove(spare)
            except OSError:
                pass

        if not os.path.isfile(os.path.join(staging, "Tlamatini.exe")):
            raise RuntimeError("Staged build is invalid — Tlamatini.exe missing after extraction.")

        # 4) Hand off to the external PowerShell updater and let it swap + relaunch.
        log_path = _launch_updater(install_dir(), staging)
        _set_state(running=False, phase="handoff", percent=100,
                   message="Update staged. Tlamatini will now close and reopen on the new version.",
                   error="", **{"log_path": log_path})
    except Exception as exc:  # never let the worker thread die silently
        _set_state(running=False, phase="error", message="Update failed.", error=str(exc))


def _launch_updater(target_install: str, staging: str) -> str:
    """Copy ``apply_update.ps1`` outside the install and launch it (visible)."""
    home = _updater_home()
    os.makedirs(home, exist_ok=True)
    script_src = _resolve_updater_script()
    script_dst = os.path.join(home, _UPDATER_SCRIPT)
    shutil.copy2(script_src, script_dst)
    log_path = os.path.join(home, "update.log")

    relaunch_exe = os.path.join(target_install, "Tlamatini.exe")
    args = [
        "powershell", "-ExecutionPolicy", "Bypass", "-NoProfile", "-File", script_dst,
        "-InstallDir", target_install,
        "-StagingDir", staging,
        "-ParentPid", str(os.getpid()),
        "-RelaunchExe", relaunch_exe,
        "-LogPath", log_path,
    ]
    # Visible console window (<REDACTED>'s choice) that survives this process's
    # death: a new console + breakaway from any job object we may live in.
    flags = 0
    if os.name == "nt":
        flags = (
            getattr(subprocess, "CREATE_NEW_CONSOLE", 0)
            | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
            | getattr(subprocess, "CREATE_BREAKAWAY_FROM_JOB", 0)
        )
    try:
        subprocess.Popen(args, cwd=home, close_fds=True, creationflags=flags)
    except OSError:
        # Breakaway can fail if the job forbids it — retry without that flag.
        flags2 = getattr(subprocess, "CREATE_NEW_CONSOLE", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        subprocess.Popen(args, cwd=home, close_fds=True, creationflags=flags2)
    return log_path


def _resolve_updater_script() -> str:
    """Find ``apply_update.ps1`` in both frozen (next to exe) and source mode."""
    candidates = []
    root = install_dir()
    if root:
        candidates.append(os.path.join(root, _UPDATER_SCRIPT))
    # Source mode: repo root is three levels up from this file
    # (agent/ -> Tlamatini/ -> repo root).
    here = os.path.dirname(os.path.abspath(__file__))
    candidates.append(os.path.join(here, "..", "..", _UPDATER_SCRIPT))
    candidates.append(os.path.join(here, _UPDATER_SCRIPT))
    for c in candidates:
        if c and os.path.isfile(c):
            return os.path.abspath(c)
    raise FileNotFoundError(f"{_UPDATER_SCRIPT} not found (looked in: {candidates})")


# ── Helpers ─────────────────────────────────────────────────────────────────

def _download(url: str, dest: str) -> None:
    request = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    with urllib.request.urlopen(request, timeout=60) as resp:
        total = int(resp.headers.get("Content-Length") or _STATE.get("total") or 0)
        _set_state(total=total)
        done = 0
        last = 0.0
        with open(dest, "wb") as out:
            while True:
                chunk = resp.read(1024 * 256)
                if not chunk:
                    break
                out.write(chunk)
                done += len(chunk)
                now = time.time()
                if now - last >= 0.25:  # throttle status writes
                    last = now
                    pct = int(done * 100 / total) if total else 0
                    _set_state(downloaded=done, percent=pct,
                               message=f"Downloading… {_human(done)} / {_human(total)}")
        _set_state(downloaded=done, percent=100 if total else 0)


def _locate_pkg_zip(folder: str) -> Optional[str]:
    for dirpath, _dirs, files in os.walk(folder):
        for name in files:
            if name.lower() == "pkg.zip":
                return os.path.join(dirpath, name)
    return None


def _flatten_to_exe(folder: str) -> str:
    """Return the directory that directly contains ``Tlamatini.exe``.

    pkg.zip normally extracts the install tree flat, but tolerate a single
    wrapping folder just in case.
    """
    if os.path.isfile(os.path.join(folder, "Tlamatini.exe")):
        return folder
    entries = [os.path.join(folder, n) for n in os.listdir(folder)]
    subdirs = [p for p in entries if os.path.isdir(p)]
    if len(subdirs) == 1 and os.path.isfile(os.path.join(subdirs[0], "Tlamatini.exe")):
        return subdirs[0]
    return folder


def _reset_dir(path: str) -> None:
    shutil.rmtree(path, ignore_errors=True)
    os.makedirs(path, exist_ok=True)


def _free_space_warning(path: str) -> None:
    try:
        free = shutil.disk_usage(path).free
        if free < _MIN_FREE_BYTES:
            _set_state(message=f"Warning: low free disk space ({_human(free)}). The update may fail.")
    except Exception:
        pass


def _human(num: int) -> str:
    value = float(num or 0)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024 or unit == "TB":
            return f"{value:.1f} {unit}" if unit != "B" else f"{int(value)} {unit}"
        value /= 1024
    return f"{value:.1f} TB"
