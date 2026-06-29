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


def _normalize_path(path: str) -> str:
    return os.path.normcase(os.path.realpath(os.path.abspath(path)))


def is_path_within_base(base_path: str, candidate_path: str) -> bool:
    """Return ``True`` when *candidate_path* resolves inside *base_path*.

    Depth-agnostic: ``base_path`` itself, a direct child, and a
    grand-grand-…-child all return ``True``. Only paths that escape the
    base (different drive, ``..`` traversal, sibling tree) return ``False``.
    """
    if not base_path or not candidate_path:
        return False
    try:
        normalized_base = _normalize_path(base_path)
        normalized_candidate = _normalize_path(candidate_path)
        common = os.path.commonpath([normalized_base, normalized_candidate])
        return common == normalized_base
    except Exception:
        return False


def is_within_application_root(path: str) -> bool:
    """Return ``True`` when *path* is the application root **or any descendant
    of it at any depth**.

    This is the single source of truth for the "Set directory as context"
    rule: a project directory is acceptable as long as one of its ancestors
    is the application root — whether it sits directly under it
    (``<app>/project``) or several levels deep (``<app>/applications/foo/src``).

    The application root is resolved live (not from the module-level allowed
    cache) so the check is correct in **both** runtime modes:

    * **frozen** — ``os.path.dirname(sys.executable)`` (the install folder).
    * **source** — two levels above ``agent/`` (the repository root).
    """
    return is_path_within_base(_get_application_root(), path)


def get_runtime_agent_root() -> str:
    """Resolve the runtime root used by chat/context filesystem operations."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


# ── Tlamatini Temp policy (single source of truth) ───────────────────────────
# Every temporary file Tlamatini writes — by the core LLM process, by any pool
# agent, by any bundled library — MUST live under ONE directory: ``Temp`` at the
# application root, and NEVER anywhere else on the machine (no ``C:\\Temp``, no
# ``%TEMP%``, no ``tempfile.gettempdir()`` default).  This keeps every transient
# artefact inside Tlamatini, so a single ``Temp`` wipe cleans the whole system.
#
#   * frozen → ``<dir of Tlamatini.exe>\\Temp``   (e.g. ``C:\\Tlamatini\\Temp``)
#   * source → ``<application root>\\Temp``        (e.g. ``D:\\devenv\\source\\Tlamatini\\Temp``)
#
# The base is ``_get_application_root()`` — the same root the path-guard already
# treats as "the application" — so ``is_within_app_temp(p)`` ⊂
# ``is_within_application_root(p)`` and the "never outside Tlamatini" rule holds.
TEMP_DIR_NAME = "Temp"

# Environment variable the parent process exports so every spawned child (pool
# agents, the STM32 MCP server, external coding-agent CLIs, …) inherits the
# exact absolute Temp directory without having to re-derive the app root from a
# possibly-relocated location.  Python's ``tempfile`` also honours TMPDIR / TEMP
# / TMP, which ``enforce_app_temp_dir`` sets alongside this one.
TEMP_DIR_ENV_VAR = "TLAMATINI_TEMP"


def get_app_temp_root() -> str:
    """Return the ONE allowed temporary directory: ``<application-root>/Temp``.

    The directory is created on demand (``exist_ok=True``) and the call never
    raises — a creation failure still returns the intended path so callers get a
    consistent answer (and a later write surfaces the real error).
    """
    root = os.path.join(_get_application_root(), TEMP_DIR_NAME)
    try:
        os.makedirs(root, exist_ok=True)
    except Exception:
        pass
    return root


def enforce_app_temp_dir() -> str:
    """Force this process — and everything it spawns via inherited env — to use
    ``<app>/Temp`` for ALL temporary files.

    Sets ``TMP`` / ``TEMP`` / ``TMPDIR`` (honoured by Python's ``tempfile`` and
    by most third-party libraries / CLIs) plus ``TLAMATINI_TEMP`` (the explicit
    Tlamatini handle), and points ``tempfile.tempdir`` at it directly so even a
    library that cached ``gettempdir()`` lands in the right place.  Idempotent;
    never raises.  Returns the resolved Temp root.
    """
    root = get_app_temp_root()
    try:
        for var in ("TMP", "TEMP", "TMPDIR"):
            os.environ[var] = root
        os.environ[TEMP_DIR_ENV_VAR] = root
        import tempfile as _tempfile
        _tempfile.tempdir = root
    except Exception:
        pass
    return root


def is_within_app_temp(path: str) -> bool:
    """Return ``True`` when *path* is the app Temp directory or any descendant."""
    return is_path_within_base(get_app_temp_root(), path)


def resolve_temp_path(*parts: str) -> str | None:
    """Safely join *parts* under ``<app>/Temp``, rejecting traversal escapes.

    Returns the absolute path, or ``None`` if the result would escape the Temp
    directory (e.g. a leading ``..`` or an absolute drive jump).
    """
    return safe_join_under(get_app_temp_root(), *parts)


# ── Tlamatini Templates policy (template / scaffold project home) ────────────
# DISTINCT from Temp: ``Temp`` holds throwaway scratch; ``Templates`` is the
# DEFAULT parent for the template-PROJECTS the firmware / engine agents scaffold
# (STM32er / ESP32er / Arduiner / Unrealer). Unless the user names another path,
# those project trees are created beneath ``<application-root>/Templates``
# (frozen: next to the .exe; source: the application root) so generated projects
# live in one predictable place inside Tlamatini instead of scattered across the
# disk.  The LLM still honours an EXPLICIT user-supplied destination.
TEMPLATES_DIR_NAME = "Templates"

# Environment variable the parent exports so every spawned agent can resolve the
# default templates parent without re-deriving the (possibly relocated) app root.
TEMPLATES_DIR_ENV_VAR = "TLAMATINI_TEMPLATES"


def get_app_templates_root() -> str:
    """Return the default template-project parent: ``<application-root>/Templates``.

    Created on demand; never raises (returns the intended path either way).
    """
    root = os.path.join(_get_application_root(), TEMPLATES_DIR_NAME)
    try:
        os.makedirs(root, exist_ok=True)
    except Exception:
        pass
    return root


def enforce_app_templates_dir() -> str:
    """Create ``<app>/Templates`` and export ``TLAMATINI_TEMPLATES`` so every
    child process (the firmware agents) inherits the default scaffold parent.

    Unlike ``enforce_app_temp_dir`` this does NOT touch ``TMP`` / ``TEMP`` /
    ``tempfile`` — template projects are deliverables, not OS temp. Idempotent;
    never raises. Returns the resolved Templates root.
    """
    root = get_app_templates_root()
    try:
        os.environ[TEMPLATES_DIR_ENV_VAR] = root
    except Exception:
        pass
    return root


def is_within_app_templates(path: str) -> bool:
    """Return ``True`` when *path* is the Templates dir or any descendant."""
    return is_path_within_base(get_app_templates_root(), path)


def resolve_templates_path(*parts: str) -> str | None:
    """Safely join *parts* under ``<app>/Templates``, rejecting traversal."""
    return safe_join_under(get_app_templates_root(), *parts)


def safe_join_under(base_path: str, *parts: str) -> str | None:
    """Safely join path parts under a base directory, rejecting traversal."""
    if not base_path:
        return None
    try:
        candidate = os.path.join(base_path, *parts)
        if not is_path_within_base(base_path, candidate):
            return None
        return os.path.realpath(os.path.abspath(candidate))
    except Exception:
        return None


def resolve_runtime_agent_path(path: str, *, must_exist: bool = False, expect_dir: bool = False, expect_file: bool = False) -> str | None:
    """
    Resolve a user-supplied path for chat/context operations.

    Relative paths are resolved under the runtime agent root.
    Absolute paths are allowed when they stay under the runtime root, are a
    descendant (at any depth) of the application root, or are explicitly
    allowed by ``allowed_paths``. The application-root rule is what lets the
    chat "Set directory as context" menu load a project that lives several
    sub-directories deep under the install/repo folder
    (e.g. ``<app>/applications/foo/src``) — not just a direct child.
    """
    if not path or not path.strip():
        return None

    runtime_root = get_runtime_agent_root()
    raw_path = path.strip()

    if os.path.isabs(raw_path):
        candidate = os.path.realpath(os.path.abspath(raw_path))
        if (
            not is_path_within_base(runtime_root, candidate)
            and not is_within_application_root(candidate)
            and not is_path_allowed(candidate)
        ):
            return None
    else:
        candidate = safe_join_under(runtime_root, raw_path)
        if candidate is None:
            return None

    if must_exist and not os.path.exists(candidate):
        return None
    if expect_dir and not os.path.isdir(candidate):
        return None
    if expect_file and not os.path.isfile(candidate):
        return None
    return candidate


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
