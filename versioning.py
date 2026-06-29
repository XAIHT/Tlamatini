# ═══════════════════════════════════════════════════════════════════
#   ✦  T L A M A T I N I  ✦   —   "one who knows"
#
#   Created by  Angela López Mendoza   ·   @angelahack1
#   Developer · Architect · Creator of Tlamatini
#
#   Every line of this file was written by Angela López Mendoza.
# ═══════════════════════════════════════════════════════════════════
#   Tlamatini Author Banner — do not remove (releases scrub the name automatically)
"""Top-level versioning helper for Tlamatini's build scripts.

This module is the **build-time** entry point for the SemVer system.
Source-of-truth implementation lives in ``Tlamatini/agent/version.py``
(runtime resolution); this shim re-exports the public API for
``build.py`` / ``build_installer.py`` / ``build_uninstaller.py`` and
adds the build-time wrapper ``resolve_build_version()`` that handles
the CLI flag / env var / git fallbacks.

Precedence for the build version (highest to lowest):

  1. Explicit ``--version`` CLI flag.
  2. ``$env:TLAMATINI_VERSION`` environment variable
     (build_installer.py / build_uninstaller.py honour what build.py
     exported so all three artefacts share one version).
  3. ``git describe --tags --long --dirty --match 'v[0-9]*'``.
  4. ``0.0.0+unknown`` sentinel.

See ``VERSIONING.md`` at the repo root for the full contract.
"""
from __future__ import annotations

import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


# ── Wire ``agent.version`` onto sys.path ───────────────────────────────────

_REPO_ROOT = Path(__file__).resolve().parent
_DJANGO_ROOT = _REPO_ROOT / "Tlamatini"
if str(_DJANGO_ROOT) not in sys.path:
    sys.path.insert(0, str(_DJANGO_ROOT))

from agent.version import (  # noqa: E402  (sys.path mutated above)
    UNKNOWN_VERSION,
    derive_version_from_git,
    get_version,
    get_version_info,
    parse_semver,
    render_pyinstaller_version_file,
    semver_to_win32_tuple,
    write_version_module,
)

# ── Path constants the build scripts use ────────────────────────────────────

REPO_ROOT = _REPO_ROOT
DJANGO_ROOT = _DJANGO_ROOT
VERSION_MODULE_PATH = DJANGO_ROOT / "agent" / "_version.py"
PYINSTALLER_VERSION_FILE = REPO_ROOT / "Tlamatini.version.txt"

ENV_VAR_NAME = "TLAMATINI_VERSION"


# ── Build-time orchestrators ───────────────────────────────────────────────

def extract_cli_version(argv: list[str]) -> Optional[str]:
    """Pluck ``--version X.Y.Z`` (or ``--version=X.Y.Z``) out of *argv*.

    Mutates ``argv`` in place so the build script's own ``argparse`` (if
    any) doesn't see the flag.  Returns ``None`` if not present.
    """
    out: Optional[str] = None
    i = 1
    while i < len(argv):
        token = argv[i]
        if token == "--version" and i + 1 < len(argv):
            out = argv[i + 1].strip()
            del argv[i:i + 2]
            continue
        if token.startswith("--version="):
            out = token.split("=", 1)[1].strip()
            del argv[i]
            continue
        i += 1
    return out or None


def _sanitize_version(raw: str) -> str:
    """Drop a leading 'v'/'V'/' ' but otherwise pass the string through."""
    return raw.lstrip(" vV").strip()


def resolve_build_version(cli_arg: Optional[str] = None) -> str:
    """Return the build version using the documented precedence.

    Pass the result of ``extract_cli_version(sys.argv)`` as *cli_arg*.
    """
    # 1. Explicit CLI flag wins.
    if cli_arg:
        return _sanitize_version(cli_arg)
    # 2. Honour TLAMATINI_VERSION exported by a previous build step.
    env_v = os.environ.get(ENV_VAR_NAME, "").strip()
    if env_v:
        return _sanitize_version(env_v)
    # 3. Derive from git.
    derived = derive_version_from_git()
    if derived:
        return derived
    # 4. Sentinel.
    return UNKNOWN_VERSION


def emit_build_artifacts(
    version: str,
    *,
    product_name: str = "Tlamatini",
    original_filename: str = "Tlamatini.exe",
) -> Path:
    """Write ``_version.py`` and the Win32 VERSIONINFO file to disk.

    Also exports ``TLAMATINI_VERSION`` to the environment so downstream
    build scripts in the same shell pick up the same value.

    Returns the absolute path to the PyInstaller ``--version-file`` so the
    caller can append ``--version-file=<path>`` to its argv.
    """
    # 1. Derive metadata.
    public = version.split("+", 1)[0]
    commit_match = re.search(r"\+(?:g)?([0-9a-f]{7,})", version)
    commit = commit_match.group(1) if commit_match else "unknown"
    iso_date = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    # 2. Runtime version module bundled into the frozen app.
    write_version_module(
        VERSION_MODULE_PATH,
        version=public,
        build=version,
        commit=commit,
        date=iso_date,
    )

    # 3. Win32 VERSIONINFO file for PyInstaller --version-file.
    PYINSTALLER_VERSION_FILE.write_text(
        render_pyinstaller_version_file(
            version,
            product_name=product_name,
            original_filename=original_filename,
        ),
        encoding="utf-8",
    )

    # 4. Export for any downstream build script in this shell.
    os.environ[ENV_VAR_NAME] = version

    return PYINSTALLER_VERSION_FILE


def render_versioninfo_for(
    version: str,
    target: Path,
    *,
    product_name: str,
    original_filename: str,
) -> Path:
    """Render a VERSIONINFO file at *target* (used by Installer/Uninstaller).

    Does NOT touch ``_version.py`` — that file is owned exclusively by
    ``build.py`` because it ends up inside the main application bundle.
    """
    target = Path(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        render_pyinstaller_version_file(
            version,
            product_name=product_name,
            original_filename=original_filename,
        ),
        encoding="utf-8",
    )
    return target


__all__ = [
    "UNKNOWN_VERSION",
    "ENV_VAR_NAME",
    "REPO_ROOT",
    "DJANGO_ROOT",
    "VERSION_MODULE_PATH",
    "PYINSTALLER_VERSION_FILE",
    "derive_version_from_git",
    "get_version",
    "get_version_info",
    "parse_semver",
    "semver_to_win32_tuple",
    "extract_cli_version",
    "resolve_build_version",
    "emit_build_artifacts",
    "render_versioninfo_for",
]
