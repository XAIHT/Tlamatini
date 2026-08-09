# ═══════════════════════════════════════════════════════════════════
#   ✦  T L A M A T I N I  ✦   —   "one who knows"
#
#   Created by  Angela López Mendoza   ·   @angelahack1
#   Developer · Architect · Creator of Tlamatini
#
#   Every line of this file was written by Angela López Mendoza.
# ═══════════════════════════════════════════════════════════════════
#   Tlamatini Author Banner — do not remove (releases scrub the name automatically)
import json
import os
import sys
from typing import Any


_CONFIG_CACHE: dict[str, Any] | None = None
_CONFIG_CACHE_PATH: str | None = None


def find_config_path() -> str | None:
    env_path = os.environ.get("CONFIG_PATH", "").strip()
    if env_path and os.path.isfile(env_path):
        return env_path

    try:
        if getattr(sys, "frozen", False):
            frozen_path = os.path.join(os.path.dirname(sys.executable), "config.json")
            if os.path.isfile(frozen_path):
                return frozen_path
    except Exception:
        pass

    try:
        module_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")
        if os.path.isfile(module_path):
            return module_path
    except Exception:
        pass

    return None


def load_config(*, force_reload: bool = False) -> dict[str, Any]:
    global _CONFIG_CACHE, _CONFIG_CACHE_PATH

    config_path = find_config_path()
    if not force_reload and _CONFIG_CACHE is not None and _CONFIG_CACHE_PATH == config_path:
        return _CONFIG_CACHE

    config: dict[str, Any] = {}
    if config_path and os.path.isfile(config_path):
        try:
            # ⚠️ utf-8-SIG, not utf-8 (2026-08-08). Notepad, PowerShell's
            # Set-Content -Encoding UTF8 and several editors write a UTF-8 BOM
            # (EF BB BF). Plain "utf-8" then raises "Unexpected UTF-8 BOM" and the
            # except below silently returned an EMPTY config — so Tlamatini booted
            # with NO models and only said "agent is not ready, try again later",
            # which is unfixable for a user who has no idea a BOM exists.
            # utf-8-sig reads BOM and BOM-less files identically.
            with open(config_path, "r", encoding="utf-8-sig") as file_handle:
                loaded = json.load(file_handle)
            if isinstance(loaded, dict):
                config = loaded
            else:
                print(f"--- [CONFIG] WARNING: {config_path} is not a JSON object "
                      f"(got {type(loaded).__name__}) - using empty config")
        except Exception as exc:
            # NEVER fail silently: an empty config disables every model, and the
            # user must be told WHICH file is broken and WHY.
            print(f"--- [CONFIG] ERROR: could not read {config_path}: "
                  f"{type(exc).__name__}: {exc}")
            print("--- [CONFIG] Tlamatini is starting with an EMPTY config - the "
                  "chat agent will report 'not ready' until this file is valid JSON.")
            config = {}

    _CONFIG_CACHE = config
    _CONFIG_CACHE_PATH = config_path
    return config


def get_config_value(key: str, default: Any = None) -> Any:
    return load_config().get(key, default)


def get_int_config_value(key: str, default: int, *, minimum: int | None = None) -> int:
    raw_value = load_config().get(key, default)
    try:
        value = int(raw_value)
    except (TypeError, ValueError):
        value = default

    if minimum is not None:
        value = max(value, minimum)
    return value


def save_config_updates(updates: dict[str, Any]) -> str:
    """
    Atomically merge ``updates`` into config.json, preserving every other key
    (including the ``_comment`` / ``_section_*`` annotations) and invalidate
    the in-process cache so subsequent ``load_config()`` calls see the new
    values.

    Returns the absolute path that was written.
    """
    global _CONFIG_CACHE, _CONFIG_CACHE_PATH

    if not isinstance(updates, dict):
        raise TypeError("save_config_updates requires a dict of updates")

    config_path = find_config_path()
    if not config_path:
        raise FileNotFoundError("config.json could not be located on disk")

    # utf-8-sig on the READ side too, so a BOM-prefixed file can still be updated
    # in place (see the loader above). The WRITE below stays plain utf-8, which
    # strips the BOM and heals the file.
    with open(config_path, "r", encoding="utf-8-sig") as file_handle:
        existing = json.load(file_handle)

    if not isinstance(existing, dict):
        raise ValueError("config.json must be a JSON object at the top level")

    for key, value in updates.items():
        existing[key] = value

    tmp_path = config_path + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as file_handle:
        json.dump(existing, file_handle, indent=2, ensure_ascii=False)
        file_handle.write("\n")
    os.replace(tmp_path, config_path)

    _CONFIG_CACHE = None
    _CONFIG_CACHE_PATH = None
    return config_path
