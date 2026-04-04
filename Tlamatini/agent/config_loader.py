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
            with open(config_path, "r", encoding="utf-8") as file_handle:
                loaded = json.load(file_handle)
            if isinstance(loaded, dict):
                config = loaded
        except Exception:
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
