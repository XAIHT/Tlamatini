"""The SEALED build Python: what you install on this machine can never reach a release.

Angela, 2026-10-21: "everytime I uninstall/install a ... lib like tensorflow, or
jupyter lab Tlamatini must not get [broken]".

Until now every release was frozen by the EVERYDAY Python of the build machine
(C:\\Program Files\\Python312 plus the per-user site-packages). PyInstaller
follows the import graph through whatever happens to be installed there, so
each `pip install` / `pip uninstall` changed what a release contained:
tensorflow and Jupyter rode into the build, a running Jupyter's locked file
killed it after 20 minutes, and the build itself wrote back into that Python
(`pip install --user`, a numpy purge) - so building could break the user's own
projects as well.

Now build.py, build_uninstaller.py and build_installer.py re-run themselves
inside ONE dedicated virtual environment:

* it lives OUTSIDE the repository, in ``%LOCALAPPDATA%\\Tlamatini\\build-env``
  (``TLAMATINI_BUILD_ENV_DIR`` overrides), so no clean, snapshot, git or
  context load ever touches it;
* it sees NO system and NO user site-packages - only what requirements.txt
  installs into it (PyInstaller and its hooks are pinned there too);
* it is named after a fingerprint of requirements.txt and the base Python, so
  editing requirements.txt builds a fresh one, and an unchanged one is reused
  in seconds;
* it is published only after it installed AND imported cleanly - a half-made
  environment is never used.

If the sealed environment cannot be made (for instance, no internet the very
first time), the build does NOT stop: it uses the newest sealed environment
that still works, and only when none exists it builds with the current Python
and says so in capitals. ``TLAMATINI_BUILD_ENV=off`` forces the old behaviour.

Stdlib only; nothing here imports Tlamatini.
"""
from __future__ import annotations

import datetime
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
REQUIREMENTS = REPO_ROOT / "requirements.txt"
#: Bump when the way the environment is made changes; it rebuilds every env.
SCHEMA = "1"
#: Set in the re-run child; ``off`` in the caller's environment disables sealing.
INSIDE_VAR = "TLAMATINI_BUILD_ENV"
MARKER_NAME = "tlamatini-build-env.json"
#: Imports that prove the environment can freeze Tlamatini.
HEALTH_IMPORTS = ("PyInstaller", "django", "numpy")
PIP_ATTEMPTS = 3

#: Variables that would let the machine's own Python leak back into the build.
_LEAKY_VARS = (
    "PYTHONPATH", "PYTHONHOME", "PYTHONSTARTUP", "PYTHONUSERBASE",
    "PYTHONEXECUTABLE", "__PYVENV_LAUNCHER__", "VIRTUAL_ENV", "CONDA_PREFIX",
    "PIP_USER", "PIP_TARGET", "PIP_PREFIX", "PIP_REQUIRE_VIRTUALENV",
)


def say(message: str) -> None:
    print(f"--- [BUILD-ENV] {message}", flush=True)


def envs_root() -> Path:
    override = os.environ.get("TLAMATINI_BUILD_ENV_DIR", "").strip()
    if override:
        return Path(override)
    local = os.environ.get("LOCALAPPDATA", "").strip()
    base = Path(local) if local else Path.home() / "AppData" / "Local"
    return base / "Tlamatini" / "build-env"


def base_python() -> str:
    """The real interpreter under any venv the caller may be in."""
    return getattr(sys, "_base_executable", "") or sys.executable


def fingerprint(requirements: Path = REQUIREMENTS, base: str | None = None) -> str:
    digest = hashlib.sha256()
    digest.update(f"schema={SCHEMA}\n".encode())
    digest.update(f"python={sys.version}\n".encode())
    digest.update(f"base={os.path.normcase(base or base_python())}\n".encode())
    digest.update(Path(requirements).read_bytes())
    return digest.hexdigest()


def env_dir_for(fp: str, root: Path | None = None) -> Path:
    tag = f"py{sys.version_info[0]}{sys.version_info[1]}"
    return (root or envs_root()) / f"{tag}-{fp[:12]}"


def env_python_in(env_dir: Path) -> Path:
    if os.name == "nt":
        return Path(env_dir) / "Scripts" / "python.exe"
    return Path(env_dir) / "bin" / "python"


def inside_sealed_env() -> bool:
    return os.environ.get(INSIDE_VAR) == "1" and sys.prefix != sys.base_prefix


def sealed_environ(env_python: Path, base_env=None) -> dict:
    """The environment the build runs in: the sealed Python first, nothing leaking in."""
    env = dict(os.environ if base_env is None else base_env)
    for name in _LEAKY_VARS:
        env.pop(name, None)
    env_dir = Path(env_python).parent.parent
    env["VIRTUAL_ENV"] = str(env_dir)
    env["PATH"] = str(Path(env_python).parent) + os.pathsep + env.get("PATH", "")
    env["PYTHONNOUSERSITE"] = "1"
    env["PIP_DISABLE_PIP_VERSION_CHECK"] = "1"
    env[INSIDE_VAR] = "1"
    return env


def _run(command, env, timeout=None) -> subprocess.CompletedProcess:
    return subprocess.run([str(part) for part in command], env=env, timeout=timeout)


def healthy(env_dir: Path) -> bool:
    python = env_python_in(env_dir)
    if not python.is_file() or not (Path(env_dir) / MARKER_NAME).is_file():
        return False
    probe = "import " + ", ".join(HEALTH_IMPORTS)
    try:
        result = subprocess.run(
            [str(python), "-c", probe], env=sealed_environ(python),
            capture_output=True, text=True, timeout=180,
        )
    except Exception:
        return False
    return result.returncode == 0


def _remove(path: Path) -> None:
    def _writable(func, target, _exc):
        try:
            os.chmod(target, 0o700)
            func(target)
        except Exception:
            pass
    if sys.version_info >= (3, 12):
        shutil.rmtree(path, onexc=_writable)
    else:
        shutil.rmtree(path, onerror=_writable)


def create(env_dir: Path, requirements: Path = REQUIREMENTS) -> Path:
    """Make the environment from scratch; publish it only when it imports cleanly."""
    env_dir = Path(env_dir)
    marker = env_dir / MARKER_NAME
    if env_dir.exists():
        _remove(env_dir)
    env_dir.parent.mkdir(parents=True, exist_ok=True)
    plain = dict(os.environ)
    for name in _LEAKY_VARS:
        plain.pop(name, None)
    plain["PYTHONNOUSERSITE"] = "1"
    say(f"creating the sealed build Python (one time per requirements.txt): {env_dir}")
    made = _run([base_python(), "-m", "venv", "--clear", env_dir], plain)
    if made.returncode != 0:
        raise RuntimeError(f"python -m venv failed with exit code {made.returncode}")
    python = env_python_in(env_dir)
    env = sealed_environ(python)
    install = [python, "-m", "pip", "install", "--no-warn-script-location",
               "--retries", "5", "--timeout", "60", "-r", requirements]
    for attempt in range(1, PIP_ATTEMPTS + 1):
        say(f"installing requirements.txt into it (attempt {attempt}/{PIP_ATTEMPTS}) ...")
        if _run(install, env).returncode == 0:
            break
        if attempt == PIP_ATTEMPTS:
            raise RuntimeError("pip could not install requirements.txt into the sealed build Python")
    marker.write_text(json.dumps({
        "fingerprint": fingerprint(requirements),
        "base_python": base_python(),
        "created": datetime.datetime.now().isoformat(timespec="seconds"),
    }, indent=2), encoding="utf-8")
    if not healthy(env_dir):
        marker.unlink(missing_ok=True)
        raise RuntimeError("the sealed build Python was made but cannot import "
                           + ", ".join(HEALTH_IMPORTS))
    return python


def _previous_healthy(exclude: Path, root: Path | None = None) -> Path | None:
    root = root or envs_root()
    if not root.is_dir():
        return None
    candidates = sorted(
        (path for path in root.iterdir()
         if path.is_dir() and path != exclude and (path / MARKER_NAME).is_file()),
        key=lambda path: (path / MARKER_NAME).stat().st_mtime, reverse=True,
    )
    for path in candidates:
        if healthy(path):
            return path
    return None


def _forget_old(keep: Path) -> None:
    root = keep.parent
    tag = keep.name.split("-", 1)[0] + "-"
    for path in root.iterdir():
        if path.is_dir() and path != keep and path.name.startswith(tag):
            _remove(path)  # best effort: a locked old one is simply left behind


def ensure_sealed_env(requirements: Path = REQUIREMENTS) -> Path | None:
    """The sealed Python to build with, or None when there is none at all."""
    env_dir = env_dir_for(fingerprint(requirements))
    if healthy(env_dir):
        say(f"reusing the sealed build Python: {env_dir}")
        return env_python_in(env_dir)
    try:
        python = create(env_dir, requirements)
    except Exception as exc:
        say(f"WARNING: could not make the sealed build Python: {exc}")
        older = _previous_healthy(env_dir)
        if older is not None:
            say(f"WARNING: building with the PREVIOUS sealed Python {older} "
                "(requirements.txt changed since it was made)")
            return env_python_in(older)
        return None
    _forget_old(env_dir)
    return python


def run_in_sealed_env(script: str, argv=None) -> None:
    """Re-run ``script`` inside the sealed build Python; returns only when it must not."""
    if inside_sealed_env():
        say(f"running in the sealed build Python: {sys.executable}")
        return
    if os.environ.get(INSIDE_VAR, "").strip().lower() in ("off", "0", "false", "no"):
        say(f"{INSIDE_VAR}=off - building with this machine's Python: {sys.executable}")
        return
    python = None
    try:
        python = ensure_sealed_env()
    except Exception as exc:
        say(f"WARNING: sealed build Python unavailable: {exc}")
    if python is None:
        print("=" * 74, flush=True)
        print("  WARNING: NO SEALED BUILD PYTHON - building with this machine's Python.\n"
              "  Libraries installed on this machine can leak into this release.\n"
              "  Run the build again with internet access to make the sealed one.", flush=True)
        print("=" * 74, flush=True)
        return
    args = list(sys.argv[1:] if argv is None else argv)
    say(f"re-running {Path(script).name} inside the sealed build Python: {python}")
    try:
        code = subprocess.run([str(python), "-s", str(Path(script).resolve()), *args],
                              env=sealed_environ(python)).returncode
    except KeyboardInterrupt:
        code = 130
    sys.exit(code)
