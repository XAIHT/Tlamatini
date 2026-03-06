"""
path_guard.py — Centralized path validation for LLM-exposed tools.

Resolves the ``allowed_paths`` list from ``config.json`` (same logic used by
``mcp_files_search_server.py``) and exposes helpers that every @tool function
calls before touching the filesystem.
"""

import os
import sys
import json
import logging

# ── Rejection message (single source of truth) ──────────────────────────────
REJECTION_MESSAGE = (
    "Not allowed path to be resolved for prompt answering, "
    "user must be aware of the only allowed paths in configuration, "
    "this request will be rejected."
)

# ── Known-folder resolution (Windows only) ───────────────────────────────────
_KNOWN_FOLDER_MAP: dict = {}

try:
    from win32com.shell import shellcon  # type: ignore[import-untyped]

    _KNOWN_FOLDER_MAP = {
        "application": None,           # special: resolves to APPLICATION_ROOT
        "docs":      shellcon.FOLDERID_Documents,
        "downloads": shellcon.FOLDERID_Downloads,
        "desktop":   shellcon.FOLDERID_Desktop,
        "pictures":  shellcon.FOLDERID_Pictures,
        "videos":    shellcon.FOLDERID_Videos,
        "music":     shellcon.FOLDERID_Music,
    }
except ImportError:
    logging.warning("pywin32 not available — only raw filesystem paths will be honoured in allowed_paths.")


def _get_known_folder_path(folder_id):
    """Resolve a Windows KNOWNFOLDERID to its filesystem path."""
    try:
        from win32com.shell import shell as _shell  # type: ignore[import-untyped]
        return _shell.SHGetKnownFolderPath(folder_id, 0, None)
    except Exception as exc:
        logging.error("Failed to resolve known folder %s: %s", folder_id, exc)
        return None


def _get_application_root() -> str:
    """Same logic as ``mcp_files_search_server.get_application_root``."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    script_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.dirname(os.path.dirname(script_dir))


# ── Config loading ───────────────────────────────────────────────────────────
def _find_config_path() -> str | None:
    """Locate config.json (same search order as other modules)."""
    env_path = os.environ.get("CONFIG_PATH", "").strip()
    if env_path and os.path.isfile(env_path):
        return env_path
    if getattr(sys, "frozen", False):
        p = os.path.join(os.path.dirname(sys.executable), "config.json")
        if os.path.isfile(p):
            return p
    module_dir = os.path.dirname(os.path.abspath(__file__))
    p2 = os.path.join(module_dir, "config.json")
    if os.path.isfile(p2):
        return p2
    return None


def _load_config() -> dict:
    path = _find_config_path()
    if path:
        try:
            with open(path, "r", encoding="utf-8") as fh:
                return json.load(fh)
        except Exception as exc:
            logging.error("path_guard: failed to load config.json: %s", exc)
    return {}


# ── Build the set of allowed directory roots ─────────────────────────────────
def _build_allowed_dirs(config: dict) -> list[str]:
    """
    Return a list of **normalised, real** directory paths that are allowed.

    Each entry in ``config["allowed_paths"]`` can be:
    * A well-known key  (``"docs"``, ``"downloads"``, ``"application"``, …)
    * A raw filesystem path  (``"d:\\\\devenv"``)
    """
    entries = config.get("allowed_paths", [])
    if not entries:
        return []

    app_root = _get_application_root()
    result: list[str] = []

    for entry in entries:
        entry_lower = entry.strip().lower() if isinstance(entry, str) else ""
        if not entry_lower:
            continue

        if entry_lower in _KNOWN_FOLDER_MAP:
            if entry_lower == "application":
                resolved = app_root
            else:
                resolved = _get_known_folder_path(_KNOWN_FOLDER_MAP[entry_lower])
            if resolved and os.path.isdir(resolved):
                result.append(os.path.realpath(resolved).lower())
        else:
            raw = entry.strip()
            if os.path.isdir(raw):
                result.append(os.path.realpath(raw).lower())
            else:
                logging.warning("path_guard: configured allowed_path is not a valid directory: %s", raw)

    return result


# Module-level cache (built once at import time)
_CONFIG = _load_config()
_ALLOWED_DIRS: list[str] = _build_allowed_dirs(_CONFIG)


# ── Public API ───────────────────────────────────────────────────────────────
def is_path_allowed(path: str) -> bool:
    """
    Return ``True`` if *path* resolves to a location inside (or equal to)
    any of the directories listed in ``config.json["allowed_paths"]``.

    Uses ``os.path.realpath`` to collapse symlinks and ``..`` sequences,
    preventing any traversal bypass.
    """
    if not path or not path.strip():
        return False
    try:
        resolved = os.path.realpath(os.path.abspath(path.strip())).lower()
        for allowed in _ALLOWED_DIRS:
            try:
                common = os.path.commonpath([allowed, resolved])
                if common == allowed:
                    return True
            except ValueError:
                # Different drive letters on Windows → can't share a common path
                continue
        return False
    except Exception:
        return False


def validate_tool_path(path: str) -> str | None:
    """
    Convenience wrapper for ``@tool`` functions.

    Returns ``None`` if the path is allowed (tool may proceed).
    Returns the ``REJECTION_MESSAGE`` string if the path is **not** allowed
    (tool must return this string immediately).
    """
    if is_path_allowed(path):
        return None
    return REJECTION_MESSAGE


def get_allowed_dirs_display() -> list[str]:
    """Return the list of allowed directories for informational display."""
    return list(_ALLOWED_DIRS)
