# Tlamatini — Created by Angela López Mendoza · @angelahack1
# Tlamatini Author Banner — do not remove
"""Small, dependency-free contract shared by Django and carried dictation Python."""
import math
import re

DEFAULTS = {
    "input_gain_percent": 100, "silence_timeout_seconds": 3.5,
    "max_record_seconds": 300, "silence_threshold_db": 0,
    "sample_rate": 0, "channels": 1, "language": "", "task": "transcribe",
    "beam_size": 5, "vad_filter": True,
}
RANGES = {
    "input_gain_percent": (0, 300), "silence_timeout_seconds": (.3, 20),
    "max_record_seconds": (5, 600), "beam_size": (1, 10),
    "device_index": (-1, 65535),
}
RATES = {0, 8000, 16000, 22050, 24000, 32000, 44100, 48000}
ALLOWED = set(DEFAULTS) | {"device_index", "device_name", "device_hostapi"}


def validate_capture_settings(value):
    """Return a new, bounded allowlist; never accept worker/engine/secret settings."""
    if not isinstance(value, dict) or set(value) - ALLOWED:
        raise ValueError("Unsupported microphone settings.")
    result = {}
    for key, item in value.items():
        if key in RANGES or key == "silence_threshold_db":
            if isinstance(item, bool) or not isinstance(item, (int, float)) or not math.isfinite(item):
                raise ValueError(f"Invalid {key}.")
            if key == "silence_threshold_db":
                valid = item == 0 or -90 <= item <= -10
            else:
                low, high = RANGES[key]
                valid = low <= item <= high
            if not valid or (key in {"beam_size", "device_index"} and int(item) != item):
                raise ValueError(f"Invalid {key}.")
        elif key in {"sample_rate", "channels"}:
            allowed = RATES if key == "sample_rate" else {1, 2}
            if type(item) is not int or item not in allowed:
                raise ValueError(f"Invalid {key}.")
        elif key == "vad_filter":
            if type(item) is not bool:
                raise ValueError("Invalid voice activity filter.")
        elif key == "task":
            if item not in ("transcribe", "translate"):
                raise ValueError("Invalid recognition task.")
        elif key == "language":
            if not isinstance(item, str) or not re.fullmatch(r"[a-z]{2,3}|", item):
                raise ValueError("Use a two/three-letter language code or automatic detection.")
        elif key in {"device_name", "device_hostapi"}:
            limit = 128 if key == "device_name" else 80
            if not isinstance(item, str) or len(item) > limit or any(ord(c) < 32 for c in item):
                raise ValueError("Invalid microphone identity.")
        result[key] = item
    if result.get("device_index", -1) >= 0 and not (
            result.get("device_name") and result.get("device_hostapi")):
        raise ValueError("Select a microphone from the current input list.")
    return result


def public_defaults(config):
    """Expose only editable values, never provider keys or unrelated configuration."""
    defaults = DEFAULTS.copy()
    for key in DEFAULTS:
        try:
            defaults.update(validate_capture_settings({key: config.get(key, DEFAULTS[key])}))
        except ValueError:
            pass
    return defaults
