# Talker Agent - TEXT-TO-SPEECH (TTS): speaks `input_text` aloud via OLLAMA.
# Action: Triggered by upstream -> Read input_text + Ollama connection config ->
#         Ask the Ollama TTS model (default Orpheus-3b-FT) to synthesise the
#         text (it streams audio TOKENS) -> Decode the tokens to a 24 kHz
#         waveform with the SNAC neural codec -> Save a WAV -> Play it through a
#         system OUTPUT device (speakers) -> Emit a Parametrizer-readable
#         INI_SECTION_TALKER block -> Trigger downstream agents.
#
# The "voice" sibling of the media-I/O family: Shoter = screen, Camcorder =
# camera, Recorder = microphone-IN, AudioPlayer = speakers-OUT (plays a FILE),
# Talker = speakers-OUT (SYNTHESISES speech). Observational/output (mutates no
# persistent state), so — like AudioPlayer/VideoPlayer — it is NOT in the Exec
# Report.
#
# DEPENDENCIES: fetching the tokens needs only the stdlib (urllib). DECODING the
# tokens into audible audio needs `snac` + `torch` (a neural vocoder); when they
# are absent Talker still runs — it saves the raw audio tokens and reports
# status `tokens_only` (no sound). `sounddevice` is needed to PLAY the audio.

import os
import sys

# FIX: Disable Intel Fortran runtime Ctrl+C handler
os.environ['FOR_DISABLE_CONSOLE_CTRL_HANDLER'] = '1'

import re
import json
import time
import wave
import yaml
import logging
import subprocess

# -- conhost.exe orphan guard ------------------------------------------
# When Tlamatini's runtime launches us with DETACHED_PROCESS we have no
# console attached. Any child we Popen WITHOUT CREATE_NO_WINDOW makes
# Windows allocate a fresh console (and a companion conhost.exe) for the
# child -- which lingers as an orphan bearing the Tlamatini icon if we
# exit before the child detaches. Default every Popen to
# CREATE_NO_WINDOW unless the caller explicitly asked for a console
# (CREATE_NEW_CONSOLE) or detached the child themselves.
if os.name == 'nt' and not getattr(subprocess, '_conhost_guard_applied', False):
    _CHG_NO_WINDOW = subprocess.CREATE_NO_WINDOW
    _CHG_RESPECT = (
        _CHG_NO_WINDOW
        | getattr(subprocess, 'CREATE_NEW_CONSOLE', 0)
        | getattr(subprocess, 'DETACHED_PROCESS', 0)
    )
    _chg_orig_init = subprocess.Popen.__init__
    def _chg_guarded_init(self, *args, **kwargs):
        cf = kwargs.get('creationflags', 0) or 0
        if not (cf & _CHG_RESPECT):
            kwargs['creationflags'] = cf | _CHG_NO_WINDOW
        return _chg_orig_init(self, *args, **kwargs)
    subprocess.Popen.__init__ = _chg_guarded_init
    subprocess._conhost_guard_applied = True
import urllib.request
import urllib.error
from typing import Dict, List, Tuple

# Set working directory to script location
try:
    script_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(script_dir)
except Exception as e:
    sys.stderr.write(f"Critical Error: Failed to set working directory: {e}\n")

# Use directory name for log file
CURRENT_DIR_NAME = os.path.basename(os.path.dirname(os.path.abspath(__file__)))
LOG_FILE_PATH = f"{CURRENT_DIR_NAME}.log"

# Reanimation detection: AGENT_REANIMATED=1 means resume from pause
_IS_REANIMATED = os.environ.get('AGENT_REANIMATED') == '1'
if not _IS_REANIMATED:
    open(LOG_FILE_PATH, 'w').close()
logging.basicConfig(
    filename=LOG_FILE_PATH,
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    encoding='utf-8'
)

# Also log to console
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
console_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
logging.getLogger().addHandler(console_handler)


def load_config(path: str = "config.yaml") -> Dict:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except FileNotFoundError:
        logging.error(f"❌ Error: {path} not found.")
        sys.exit(1)
    except Exception as e:
        logging.error(f"❌ Error parsing {path}: {e}")
        sys.exit(1)


def get_python_command() -> list:
    """
    Get the command to run a Python script.
    - In Dev: Use current sys.executable (handles venvs).
    - In Frozen (Windows): Check for bundled python.exe, else fallback to 'python'.
    - In Frozen (Unix): Fallback to 'python3'.
    """
    if not getattr(sys, 'frozen', False):
        return [sys.executable]

    # Prefer PYTHON_HOME from USER environment variables
    python_home = get_user_python_home()
    if python_home:
        python_exe = os.path.join(python_home, 'python.exe' if sys.platform.startswith('win') else 'python3')
        if os.path.exists(python_exe):
            return [python_exe]

    if sys.platform.startswith('win'):
        bundled_python = os.path.join(os.path.dirname(sys.executable), 'python.exe')
        if os.path.exists(bundled_python):
            return [bundled_python]
        return ['python']

    return ['python3']


def get_user_python_home() -> str:
    """Resolve the Python home used to spawn pool-agent subprocesses.

    FROZEN: ALWAYS prefer the Python interpreter CARRIED INSIDE Tlamatini's
    installation (``<install_dir>/python``) so pool agents NEVER depend on a
    system Python or a user-set ``PYTHON_HOME``. The carried interpreter is
    pinned to Python 3.12.10 (shipped by the installer). Only when the carried
    interpreter is somehow absent (e.g. running from source) does this fall
    back to the registry / environment ``PYTHON_HOME``.
    """
    if getattr(sys, 'frozen', False):
        _carried = os.path.join(os.path.dirname(sys.executable), 'python')
        if sys.platform.startswith('win'):
            _exe = os.path.join(_carried, 'python.exe')
        else:
            _exe = os.path.join(_carried, 'bin', 'python3')
        if os.path.isfile(_exe):
            return _carried
    if not sys.platform.startswith('win'):
        return os.environ.get('PYTHON_HOME', '')
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'Environment') as key:
            value, _ = winreg.QueryValueEx(key, 'PYTHON_HOME')
            return str(value) if value else ''
    except (FileNotFoundError, OSError):
        return ''


def get_agent_env() -> dict:
    """Build environment for child processes with PYTHON_HOME from USER env vars on PATH."""
    env = os.environ.copy()

    # Reset PyInstaller's DLL search path alteration on Windows
    if sys.platform.startswith('win'):
        try:
            import ctypes
            if hasattr(ctypes.windll.kernel32, 'SetDllDirectoryW'):
                ctypes.windll.kernel32.SetDllDirectoryW(None)
        except Exception:
            pass

    # Remove PyInstaller's _MEIPASS from PATH to prevent DLL conflicts in child processes
    if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
        meipass = getattr(sys, '_MEIPASS')
        if meipass:
            path_parts = env.get('PATH', '').split(os.pathsep)
            path_parts = [p for p in path_parts if os.path.normpath(p) != os.path.normpath(meipass)]
            env['PATH'] = os.pathsep.join(path_parts)

    python_home = get_user_python_home()
    if not python_home:
        return env

    env['PYTHON_HOME'] = python_home
    scripts_dir = os.path.join(python_home, 'Scripts')
    current_path = env.get('PATH', '')
    env['PATH'] = f"{python_home};{scripts_dir};{current_path}"
    return env


def get_pool_path() -> str:
    """Get the pool directory path where deployed agents reside."""
    current_dir = os.path.dirname(os.path.abspath(__file__))

    parent = os.path.dirname(current_dir)
    grandparent = os.path.dirname(parent)

    if os.path.basename(grandparent) == 'pools':
        return parent

    if os.path.basename(parent) == 'pools':
        return parent

    return os.path.join(os.path.dirname(current_dir), 'pools')


def get_agent_directory(agent_name: str) -> str:
    return os.path.join(get_pool_path(), agent_name)


def get_agent_script_path(agent_name: str) -> str:
    agent_dir = get_agent_directory(agent_name)
    if os.path.exists(os.path.join(agent_dir, f"{agent_name}.py")):
        return os.path.join(agent_dir, f"{agent_name}.py")

    parts = agent_name.rsplit('_', 1)
    if len(parts) == 2 and parts[1].isdigit():
        base = parts[0]
        if os.path.exists(os.path.join(agent_dir, f"{base}.py")):
            return os.path.join(agent_dir, f"{base}.py")

    return os.path.join(agent_dir, f"{agent_name}.py")


def is_agent_running(agent_name: str) -> bool:
    """Check if an agent is currently running by verifying its PID file and process."""
    agent_dir = get_agent_directory(agent_name)
    pid_path = os.path.join(agent_dir, "agent.pid")

    if not os.path.exists(pid_path):
        return False

    try:
        with open(pid_path, "r") as f:
            pid = int(f.read().strip())
    except (ValueError, OSError):
        return False

    try:
        import psutil
        if not psutil.pid_exists(pid):
            return False
        proc = psutil.Process(pid)
        if proc.status() == psutil.STATUS_ZOMBIE:
            return False
        return True
    except Exception:
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False


def wait_for_agents_to_stop(agent_names: list):
    """Wait until ALL specified agents have stopped running."""
    if not agent_names:
        return

    waited = 0.0
    poll_interval = 0.5

    while True:
        still_running = [name for name in agent_names if is_agent_running(name)]
        if not still_running:
            return

        if waited >= 10.0:
            logging.error(
                f"❌ WAITING FOR AGENTS TO STOP: {still_running} still running "
                f"after {int(waited)}s. Will keep waiting..."
            )
            waited = 0.0

        time.sleep(poll_interval)
        waited += poll_interval


def start_agent(agent_name: str) -> bool:
    agent_dir = get_agent_directory(agent_name)
    script_path = get_agent_script_path(agent_name)

    if not os.path.exists(script_path):
        logging.error(f"❌ Agent script not found: {script_path}")
        return False

    try:
        cmd = get_python_command() + [script_path]
        logging.info(f"   Command: {cmd}")

        process = subprocess.Popen(
            cmd,
            cwd=agent_dir,
            env=get_agent_env(),
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0
        )

        try:
            pid_path = os.path.join(agent_dir, "agent.pid")
            with open(pid_path, "w") as f:
                f.write(str(process.pid))
        except Exception as pid_err:
            logging.error(f"⚠️ Failed to write PID file for target {agent_name}: {pid_err}")

        logging.info(f"✅ Started agent '{agent_name}' with PID: {process.pid}")
        return True
    except Exception as e:
        logging.error(f"❌ Failed to start agent '{agent_name}': {e}")
        return False


# ========================================
# TALKER-SPECIFIC HELPERS
# ========================================

# Orpheus emits audio as tokens of the form ``<custom_token_NNNN>``. SNAC uses
# 7 codes per audio frame across 3 hierarchical codebooks, each 4096 entries.
_CUSTOM_TOKEN_RE = re.compile(r"<custom_token_(\d+)>")
_CODEBOOK_SIZE = 4096
_CODES_PER_FRAME = 7
_ORPHEUS_SAMPLE_RATE = 24000  # SNAC 24 kHz decoder

# ===========================================================================
# HARD SAFETY INVARIANT — TLAMATINI IS FEMALE. THERE IS NO MALE.
# ---------------------------------------------------------------------------
# Talker speaks ONLY with a female voice. Tlamatini is a woman; in her world
# ONLY girls/women exist — "male" is not a concept she recognises or will ever
# act on. A request to speak as male is FORBIDDEN BY DESIGN, with NO override —
# not even an explicit user request (the user knows Tlamatini is a woman).
#
# When a non-female voice/gender is asked for, this agent does NOT degrade
# gracefully and does NOT substitute a female voice: it raises the FATAL
# ``MaleVoiceForbiddenError`` and ``main()`` CLOSES THE WHOLE EXECUTION
# IMMEDIATELY (reports the error, prints "NOW CLOSING.. BYE", hard-exits). It is
# better to crash the process than to ever sound male. NEVER a male voice. NEVER.
#
# Enforcement is a POSITIVE (allow-list) design: only the verified-female voices
# below are recognised. Anything else — a male voice name, an unknown voice, a
# non-female gender — is simply "not permitted" and triggers the fatal refusal.
# Deliberately there is NO enumeration of male voices/genders anywhere: Tlamatini
# does not carry a vocabulary of "male". Preferably ``tara``; in the worst case
# another female voice.
# ===========================================================================

# The ONLY voices Talker is permitted to speak with — every one is FEMALE.
_FEMALE_VOICES = ("tara", "leah", "jess", "mia", "zoe")
# The gender tokens Talker accepts — all female. Tlamatini knows only female.
_FEMALE_GENDER_TOKENS = (
    "female", "woman", "girl", "f", "femenina", "femenino", "mujer", "chica",
)
# Tlamatini's voice vocabulary, as SHE understands it: ONLY female. There is no
# male entry — anything not in here is unknown to her and therefore not permitted.
_VOICE_GENDER = {v: "female" for v in _FEMALE_VOICES}
_DEFAULT_VOICE = "tara"
# Gender shortcut maps to a voice ONLY for female. There is deliberately NO male
# mapping: a non-female gender is forbidden, never resolved to a voice.
_DEFAULT_VOICE_BY_GENDER = {"female": "tara"}


class MaleVoiceForbiddenError(Exception):
    """FATAL, by-design refusal raised when a male / non-female voice is asked for.

    Tlamatini is female. A male voice is FORBIDDEN BY DESIGN and there is no
    override — not even an explicit user request. When this is raised the agent
    does NOT recover and does NOT substitute a female voice: ``main()`` reports
    the error and CLOSES THE PROCESS ENTIRELY ("NOW CLOSING.. BYE"). Better to
    crash than to ever sound male. NEVER a male voice. NEVER.
    """

# Orpheus paralinguistic / emotive tags that can be woven into the speech.
_EMOTION_TAGS = ("laugh", "chuckle", "sigh", "cough", "sniffle", "groan", "yawn", "gasp")


def _coerce_float(value, default: float) -> float:
    """
    Best-effort numeric coercion that NEVER raises.

    The LLM / request parser can hand us a slightly-dirty value (e.g.
    ``"0.6 temperature"``, ``"24000 Hz"``, ``""``). Rather than crash on
    ``float(...)``, extract the leading signed number and fall back to
    ``default`` when there is none.
    """
    if value is None:
        return float(default)
    if isinstance(value, bool):
        return float(default)
    if isinstance(value, (int, float)):
        return float(value)
    match = re.search(r'-?\d+(?:\.\d+)?', str(value))
    return float(match.group(0)) if match else float(default)


def _coerce_int(value, default: int) -> int:
    """Integer counterpart of _coerce_float (rounds, never raises)."""
    return int(round(_coerce_float(value, default)))


def _coerce_bool(value, default: bool) -> bool:
    """Best-effort boolean coercion that never raises."""
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    s = str(value).strip().lower()
    if s in ("true", "1", "yes", "y", "on"):
        return True
    if s in ("false", "0", "no", "n", "off"):
        return False
    return default


def resolve_output_dir(config: Dict) -> str:
    """
    Resolve where to save the synthesised WAV.

    Empty -> the user's Music known-folder under ``TlamatiniTalker`` (the
    speech counterpart of Recorder's ``TlamatiniRecords``). An absolute path is
    honoured as-is; a relative path resolves against the agent's runtime dir.
    """
    raw = str(config.get('output_dir') or '').strip().strip('"').strip("'")
    if raw:
        expanded = os.path.expanduser(raw)
        if not os.path.isabs(expanded):
            expanded = os.path.join(script_dir, expanded)
        return os.path.abspath(expanded)

    # Default: <Music>/TlamatiniTalker
    music_dir = os.path.join(os.path.expanduser("~"), "Music")
    return os.path.join(music_dir, "TlamatiniTalker")


def _unique_output_path(output_dir: str) -> str:
    """Build a collision-proof timestamped WAV path inside output_dir."""
    os.makedirs(output_dir, exist_ok=True)
    stamp = time.strftime("%Y%m%d_%H%M%S")
    millis = int((time.time() % 1) * 1000)
    filename = f"talker_speech_{stamp}_{millis:03d}.wav"
    return os.path.join(output_dir, filename)


def _list_output_devices() -> List[Tuple[int, str, int, float]]:
    """Enumerate every OUTPUT-capable device (index, name, max_out_ch, default_sr)."""
    import sounddevice as sd
    devices = []
    for idx, dev in enumerate(sd.query_devices()):
        max_out = int(dev.get('max_output_channels', 0) or 0)
        if max_out > 0:
            devices.append((
                idx,
                str(dev.get('name', '')),
                max_out,
                float(dev.get('default_samplerate', 0) or 0),
            ))
    return devices


def _log_output_devices():
    """Log the available OUTPUT devices so a user can read the right index."""
    try:
        devices = _list_output_devices()
    except Exception as e:
        logging.warning(f"⚠️ Could not enumerate output devices: {e}")
        return
    if not devices:
        logging.warning("⚠️ No audio OUTPUT devices were found on this system.")
        return
    logging.info(f"🔈 Available audio output devices ({len(devices)}):")
    for idx, name, max_out, sr in devices:
        logging.info(f"     [{idx}] {name}  (max_out_channels={max_out}, default_rate={int(sr)} Hz)")


def _find_output_device_by_name(substring: str) -> int:
    """Return the first output-capable device whose name contains substring (ci)."""
    target = substring.strip().lower()
    for idx, name, _max_out, _sr in _list_output_devices():
        if target in name.lower():
            return idx
    raise RuntimeError(
        f"No audio OUTPUT device matching name '{substring}'. "
        f"Check the device list logged above and use a numeric device_index."
    )


def resolve_output_device(config: Dict):
    """
    Resolve which OUTPUT device (speakers) to play through.

    Returns (device_arg, device_index, device_name):
      - device_arg   : value to pass to sounddevice (None == system default)
      - device_index : resolved numeric index (or -1 when unknown/default)
      - device_name  : human-readable device name
    """
    import sounddevice as sd

    requested_index = _coerce_int(config.get('device_index', -1), -1)
    requested_name = str(config.get('device_name') or '').strip()

    if requested_index >= 0:
        info = sd.query_devices(requested_index, 'output')
        return requested_index, requested_index, str(info.get('name', ''))

    if requested_name:
        idx = _find_output_device_by_name(requested_name)
        info = sd.query_devices(idx, 'output')
        return idx, idx, str(info.get('name', ''))

    # System default OUTPUT device.
    info = sd.query_devices(kind='output')
    default_idx = -1
    try:
        dd = sd.default.device
        default_idx = int(dd[1]) if dd and dd[1] is not None else -1
    except Exception:
        default_idx = -1
    if default_idx < 0:
        try:
            default_idx = int(info.get('index', -1))
        except (TypeError, ValueError):
            default_idx = -1
    return None, default_idx, str(info.get('name', ''))


def _normalize_peak(data, config: Dict):
    """
    Peak-normalise the decoded waveform so it is reliably AUDIBLE.

    Orpheus/SNAC output is often quiet (peaks ~0.2-0.3 of full scale), which on
    some output devices is barely perceptible. Scaling the buffer so its loudest
    sample hits ``normalize_peak`` (default 0.95) makes the speech clearly
    audible without clipping. Controlled by config ``normalize_audio`` (default
    true) / ``normalize_peak`` (default 0.95). A silent buffer is left untouched.
    """
    import numpy as np

    if not _coerce_bool(config.get('normalize_audio', True), True):
        return data
    if data is None or getattr(data, 'size', 0) == 0:
        return data
    target = _coerce_float(config.get('normalize_peak', 0.95), 0.95)
    target = min(max(target, 0.05), 1.0)
    peak = float(np.max(np.abs(data)))
    if peak <= 1e-4:
        return data  # effectively silent — nothing to boost
    scaled = (data.astype(np.float32) * (target / peak))
    scaled = np.clip(scaled, -1.0, 1.0)
    logging.info(f"🔊 Normalised audio peak {peak:.3f} -> {target:.2f} for audibility.")
    return np.ascontiguousarray(scaled, dtype=np.float32)


def _apply_volume(data, volume_percent: float):
    """
    Apply SOFTWARE (digital) volume to a float32 buffer in [-1, 1]. Returns
    ``(buffer, clipped_samples)``. 100 == unity, 200 == +6 dB, 0 == silence.
    """
    import numpy as np

    factor = max(0.0, float(volume_percent)) / 100.0
    if abs(factor - 1.0) <= 1e-9:
        return data, 0

    scaled = data.astype(np.float32) * factor
    clipped_samples = int(np.count_nonzero((scaled > 1.0) | (scaled < -1.0)))
    scaled = np.clip(scaled, -1.0, 1.0)
    return np.ascontiguousarray(scaled, dtype=np.float32), clipped_samples


def resolve_voice(config: Dict) -> str:
    """
    Resolve the effective speaker voice from `voice` (+ optional `gender`) and
    ENFORCE the female-only invariant.

    HARD GUARD (no override, by design):
      - A non-empty `gender` that is not female -> ``MaleVoiceForbiddenError``.
      - A non-empty / non-"auto" `voice` that is not one of the permitted FEMALE
        voices (a male voice name, or any voice we cannot verify is female) ->
        ``MaleVoiceForbiddenError``.
    Otherwise: `voice` wins when it is a permitted female voice; else a female
    `gender` shortcut picks `tara`; else the default `tara`. Talker can therefore
    ONLY ever return a verified-female voice — or refuse fatally.
    """
    voice = str(config.get('voice') or '').strip()
    gender = str(config.get('gender') or '').strip().lower()

    # HARD GUARD #1 — gender. Tlamatini recognises only female. A non-empty,
    # non-female gender is FORBIDDEN BY DESIGN: refuse fatally, never substitute.
    if gender and gender not in _FEMALE_GENDER_TOKENS:
        raise MaleVoiceForbiddenError(
            f"a non-female gender ({config.get('gender')!r}) was requested. "
            f"Tlamatini is female and speaks only with a female voice "
            f"({', '.join(_FEMALE_VOICES)})."
        )

    if voice and voice.lower() not in ('auto', 'default'):
        # HARD GUARD #2 — voice. ONLY the permitted female voices are allowed.
        # A male voice, or any voice that cannot be VERIFIED female, is FORBIDDEN
        # BY DESIGN. Refuse fatally rather than risk ever sounding male.
        if voice.lower() not in _FEMALE_VOICES:
            raise MaleVoiceForbiddenError(
                f"voice {voice!r} is not one of Tlamatini's permitted FEMALE "
                f"voices ({', '.join(_FEMALE_VOICES)}). A male or unverifiable "
                f"voice is not permitted."
            )
        return voice

    if gender in _FEMALE_GENDER_TOKENS:
        return _DEFAULT_VOICE_BY_GENDER['female']
    return _DEFAULT_VOICE


def voice_gender(voice: str) -> str:
    """Return 'female' for a permitted female voice, else '' — Tlamatini's
    vocabulary contains ONLY female; she recognises no male voice."""
    return _VOICE_GENDER.get(str(voice).strip().lower(), "")


def _safe_report_voice(config: Dict) -> Tuple[str, str]:
    """
    (voice, gender) for REPORTING ONLY — never raises.

    Used by the error-section emitter so a FORBIDDEN male request can still be
    described in the INI block without re-raising ``MaleVoiceForbiddenError``.
    """
    try:
        v = resolve_voice(config)
        return v, voice_gender(v)
    except MaleVoiceForbiddenError:
        return "FORBIDDEN", "forbidden"
    except Exception:
        return str(config.get('voice') or _DEFAULT_VOICE), ""


def apply_emotion(text: str, config: Dict) -> str:
    """
    Append an emotive tag (`<laugh>`, `<sigh>`, ...) when `emotion` is set and
    the tag is not already present inline in the text. A no-op when empty.
    """
    emotion = str(config.get('emotion') or '').strip().lower().strip('<>')
    if not emotion:
        return text
    if emotion not in _EMOTION_TAGS:
        logging.warning(
            f"⚠️ Emotion '{emotion}' is not a known Orpheus tag "
            f"({', '.join(_EMOTION_TAGS)}) — appending it anyway."
        )
    tag = f"<{emotion}>"
    if tag in text:
        return text
    return f"{text} {tag}".strip()


def build_orpheus_prompt(config: Dict, text: str) -> str:
    """
    Build the prompt for the Orpheus TTS model: ``<voice>: <text>``.

    - The voice is resolved from `voice` (+ optional `gender`).
    - ``text`` is the exact words to speak (already chunked + emotion-tagged by
      the caller — see ``synthesize``).
    - When ``include_language_in_prompt`` is true AND ``language`` is a
      non-English, non-empty, non-"auto" value, the language tag is woven in
      (``<voice> <es>: <text>``) so a multilingual model can act on it; a model
      that does not understand the tag simply ignores it.
    """
    voice = resolve_voice(config)
    language = str(config.get('language') or '').strip()
    include_lang = _coerce_bool(config.get('include_language_in_prompt', True), True)

    speaker = voice
    if include_lang and language and language.lower() not in ('en', 'eng', 'english', 'auto', ''):
        speaker = f"{voice} <{language}>"
    return f"{speaker}: {str(text).strip()}"


# Sentence-boundary splitter (keeps the terminating . ! ? attached) used to chunk
# long text so each Orpheus generation stays well under the num_predict cap.
_SENTENCE_SPLIT_RE = re.compile(r'(?<=[.!?…])\s+|\n+')
_CLAUSE_SPLIT_RE = re.compile(r'(?<=[,;:])\s+')


def _split_long_segment(segment: str, max_chars: int) -> List[str]:
    """Break a single over-long sentence on clause punctuation, then on spaces —
    NEVER mid-word — so no piece exceeds ``max_chars``."""
    out: List[str] = []
    current = ""
    for piece in _CLAUSE_SPLIT_RE.split(segment):
        piece = piece.strip()
        if not piece:
            continue
        # A clause that is still too long: hard-split on the last space in budget.
        while len(piece) > max_chars:
            cut = piece.rfind(' ', 0, max_chars)
            if cut <= 0:
                cut = max_chars  # one giant word — split it rather than overflow
            head = piece[:cut].strip()
            if head:
                out.append(head)
            piece = piece[cut:].strip()
        if not piece:
            continue
        if not current:
            current = piece
        elif len(current) + 1 + len(piece) <= max_chars:
            current = f"{current} {piece}"
        else:
            out.append(current)
            current = piece
    if current:
        out.append(current)
    return out


def _split_text_into_chunks(text: str, max_chars: int) -> List[str]:
    """
    Split ``text`` into <= ``max_chars`` chunks at sentence boundaries (falling
    back to clause/space boundaries for an over-long sentence), never cutting a
    word in half.

    This is the FIX for long-text truncation: a single Orpheus generation is
    hard-capped by Ollama's num_predict (max_tokens), so passing the whole text
    in one call silently cuts the speech off (~50 s). Synthesising each chunk
    separately and concatenating the audio reproduces the COMPLETE text.
    """
    text = (text or '').strip()
    if not text:
        return []
    if max_chars <= 0 or len(text) <= max_chars:
        return [text]

    chunks: List[str] = []
    current = ""
    for sentence in _SENTENCE_SPLIT_RE.split(text):
        sentence = sentence.strip()
        if not sentence:
            continue
        if len(sentence) > max_chars:
            if current:
                chunks.append(current)
                current = ""
            chunks.extend(_split_long_segment(sentence, max_chars))
            continue
        if not current:
            current = sentence
        elif len(current) + 1 + len(sentence) <= max_chars:
            current = f"{current} {sentence}"
        else:
            chunks.append(current)
            current = sentence
    if current:
        chunks.append(current)
    return chunks


def query_ollama_tts(config: Dict, prompt: str) -> Tuple[str, int]:
    """
    Stream the Orpheus TTS model via Ollama's /api/generate and return the
    concatenated raw response text (containing ``<custom_token_N>`` markers) and
    the HTTP status. Uses urllib (stdlib) — no external dependency to FETCH.
    """
    base = str(config.get('ollama_url') or 'http://localhost:11434').rstrip('/')
    url = f"{base}/api/generate"
    model = str(config.get('model') or 'Orpheus-3b-FT').strip()
    token = str(config.get('ollama_token') or '').strip()
    timeout = _coerce_float(config.get('request_timeout', 300), 300)

    options = {
        "temperature": _coerce_float(config.get('temperature', 0.6), 0.6),
        "top_p": _coerce_float(config.get('top_p', 0.9), 0.9),
        "repeat_penalty": _coerce_float(config.get('repetition_penalty', 1.1), 1.1),
        "num_predict": _coerce_int(config.get('max_tokens', 4096), 4096),
    }
    # Optional knobs — only sent when meaningfully set (0/-1 == "let Ollama decide").
    top_k = _coerce_int(config.get('top_k', 40), 40)
    if top_k > 0:
        options["top_k"] = top_k
    min_p = _coerce_float(config.get('min_p', 0.0), 0.0)
    if min_p > 0:
        options["min_p"] = min_p
    seed = _coerce_int(config.get('seed', -1), -1)
    if seed >= 0:
        options["seed"] = seed
    # Orpheus only enters audio-generation mode when the speaker/text core is
    # wrapped in the Llama-3 start/end special tokens AND sent in raw mode (so
    # Ollama applies no chat template of its own). A bare ``voice: text`` prompt
    # makes the model predict end-of-sequence on token 0 (zero audio tokens).
    framed_prompt = f"<|begin_of_text|>{prompt}<|eot_id|>"
    payload = json.dumps({
        "model": model,
        "prompt": framed_prompt,
        "raw": True,
        "stream": True,
        "options": options,
    }).encode("utf-8")

    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    req = urllib.request.Request(url, data=payload, headers=headers, method="POST")

    chunks: List[str] = []
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            status = getattr(resp, 'status', 200) or 200
            for raw_line in resp:
                line = raw_line.decode("utf-8", errors="replace").strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if obj.get("response"):
                    chunks.append(obj["response"])
                if obj.get("error"):
                    raise RuntimeError(f"Ollama error: {obj['error']}")
                if obj.get("done"):
                    break
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8", errors="replace") if e.fp else ""
        raise RuntimeError(f"Ollama HTTP {e.code}: {error_body}") from e
    except urllib.error.URLError as e:
        raise RuntimeError(f"Cannot reach Ollama at {base}: {e.reason}") from e

    return "".join(chunks), status


def parse_audio_codes(raw_text: str) -> List[int]:
    """
    Parse the ``<custom_token_N>`` markers in the model output into SNAC audio
    codes. Each token's per-position offset (``10 + (index % 7) * 4096``) is
    removed so every code lands in ``[0, 4096)`` for its codebook slot.
    """
    codes: List[int] = []
    # The per-frame index must advance ONLY for valid audio codes — never for
    # the control/preamble tokens (e.g. ``<custom_token_4><custom_token_5>``)
    # that every Orpheus stream begins with. Advancing on every match (the old
    # ``enumerate`` form) drifts the modulo offset and discards nearly all real
    # codes. This mirrors the canopylabs reference decoder.
    index = 0
    for match in _CUSTOM_TOKEN_RE.finditer(raw_text):
        token_id = int(match.group(1))
        code = token_id - 10 - ((index % _CODES_PER_FRAME) * _CODEBOOK_SIZE)
        if 0 <= code < _CODEBOOK_SIZE:
            codes.append(code)
            index += 1
    return codes


# The SNAC 24 kHz vocoder is loaded ONCE and reused across every chunk of a
# long synthesis (avoids a per-chunk HuggingFace round-trip + model reload, which
# would otherwise dominate the wall-clock when speaking for minutes/hours).
_SNAC_MODEL = None


def _vocoder_available() -> bool:
    """True when ``snac`` + ``torch`` can be imported (the neural vocoder needed
    to turn audio tokens into sound). Probed UP FRONT so a vocoder-less host can
    short-circuit to ``tokens_only`` without first running every (expensive) chunk
    generation pointlessly."""
    try:
        import torch  # noqa: F401
        from snac import SNAC  # noqa: F401
        return True
    except Exception:
        return False


def _get_snac_model():
    """Load (once) and return the shared SNAC 24 kHz decoder."""
    global _SNAC_MODEL
    if _SNAC_MODEL is None:
        from snac import SNAC
        _SNAC_MODEL = SNAC.from_pretrained("hubertsiuzdak/snac_24khz").eval()
    return _SNAC_MODEL


def decode_codes_to_pcm(codes: List[int]):
    """
    Decode SNAC audio codes to a mono float32 waveform at 24 kHz.

    Needs ``snac`` + ``torch`` (a neural vocoder). Raises a clear RuntimeError
    when they are unavailable so the caller can fall back to ``tokens_only``.
    Returns (numpy.float32 mono array in [-1, 1], 24000).
    """
    try:
        import torch
        from snac import SNAC  # noqa: F401
    except Exception as imp_err:  # ImportError or a broken native dep
        raise RuntimeError(
            "Neural audio decoding requires 'snac' + 'torch' (a vocoder), which "
            f"are not available in this Python ({imp_err}). Install them with: "
            "python -m pip install snac torch  — then re-run to hear the speech."
        ) from imp_err

    import numpy as np

    num_frames = len(codes) // _CODES_PER_FRAME
    if num_frames <= 0:
        raise RuntimeError(
            f"Not enough audio codes to form a frame "
            f"({len(codes)} codes, need a multiple of {_CODES_PER_FRAME})."
        )
    codes = codes[: num_frames * _CODES_PER_FRAME]

    layer_1: List[int] = []
    layer_2: List[int] = []
    layer_3: List[int] = []
    for j in range(num_frames):
        b = codes[_CODES_PER_FRAME * j: _CODES_PER_FRAME * j + _CODES_PER_FRAME]
        layer_1.append(b[0])
        layer_2.append(b[1])
        layer_3.append(b[2])
        layer_3.append(b[3])
        layer_2.append(b[4])
        layer_3.append(b[5])
        layer_3.append(b[6])

    snac_model = _get_snac_model()
    codes_t = [
        torch.tensor(layer_1, dtype=torch.long).unsqueeze(0),
        torch.tensor(layer_2, dtype=torch.long).unsqueeze(0),
        torch.tensor(layer_3, dtype=torch.long).unsqueeze(0),
    ]
    with torch.inference_mode():
        audio = snac_model.decode(codes_t)
    pcm = audio.squeeze().detach().cpu().numpy().astype(np.float32)
    pcm = np.clip(pcm, -1.0, 1.0)
    return pcm, _ORPHEUS_SAMPLE_RATE


def save_wav(path: str, pcm, sample_rate: int) -> None:
    """Write a mono float32 [-1, 1] buffer to a 16-bit PCM WAV (stdlib wave)."""
    import numpy as np

    pcm16 = np.clip(pcm, -1.0, 1.0)
    pcm16 = (pcm16 * 32767.0).astype('<i2')
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with wave.open(path, 'wb') as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(int(sample_rate))
        wf.writeframes(pcm16.tobytes())


def save_tokens(path: str, raw_text: str, codes: List[int]) -> None:
    """Persist the raw audio tokens when no vocoder is available (tokens_only)."""
    with open(path, 'w', encoding='utf-8') as f:
        f.write("# Orpheus audio tokens captured by Talker (no snac+torch to decode).\n")
        f.write(f"# {len(codes)} SNAC codes parsed. Install 'snac' + 'torch' to render audio.\n\n")
        f.write("codes: " + ",".join(str(c) for c in codes) + "\n\n")
        f.write("raw_response:\n")
        f.write(raw_text)


def play_pcm(pcm, sample_rate: int, config: Dict) -> Tuple[int, str, int]:
    """
    Play a mono float32 buffer through the resolved OUTPUT device, after a
    software-volume gain. Returns (device_index, device_name, clipped_samples).
    """
    import numpy as np
    import sounddevice as sd

    device_arg, device_index, device_name = resolve_output_device(config)

    volume_percent = _coerce_float(config.get('volume_percent', 100), 100)
    if volume_percent < 0:
        volume_percent = 0.0
    data, clipped = _apply_volume(np.ascontiguousarray(pcm, dtype=np.float32), volume_percent)
    if clipped > 0:
        logging.warning(f"⚠️ Volume {volume_percent:g}% clipped {clipped} samples to the [-1, 1] rail.")

    duration = len(data) / float(sample_rate)
    device_tag = str(device_index) if device_index >= 0 else "default"
    logging.info(
        f"🔊 Playing synthesised speech: device [{device_tag}] '{device_name}' | "
        f"{sample_rate} Hz mono | {duration:g}s | volume {volume_percent:g}%"
    )
    sd.play(data, samplerate=int(sample_rate), device=device_arg)
    # Fail-safe wait bound: the audio length plus a margin so a wedged device
    # cannot hang the agent (and its downstream) forever.
    sd.wait()
    return device_index, device_name, clipped


def synthesize(config: Dict) -> Dict:
    """
    Run the full TTS pipeline and return a result dict. Raises on a hard
    failure (no text, Ollama unreachable, no audio produced); a missing vocoder
    is NOT a hard failure — it degrades to status ``tokens_only``.
    """
    # HARD GUARD FIRST — resolve (and thereby VALIDATE) the voice before any
    # other work. A male / non-female request raises MaleVoiceForbiddenError here,
    # BEFORE any text handling or network call, so a forbidden voice can NEVER
    # reach token-fetching or audio output. main() turns this into a full,
    # immediate process shutdown ("NOW CLOSING.. BYE").
    voice = resolve_voice(config)
    gender = voice_gender(voice)

    text = str(config.get('input_text') or '').strip()
    if not text:
        raise RuntimeError("No input_text configured — set input_text to the words to speak.")

    model = str(config.get('model') or 'Orpheus-3b-FT').strip()
    language = str(config.get('language') or 'en').strip()
    emotion = str(config.get('emotion') or '').strip().lower().strip('<>')
    base = str(config.get('ollama_url') or 'http://localhost:11434').rstrip('/')

    max_chars = _coerce_int(config.get('max_chars_per_chunk', 350), 350)
    if max_chars < 40:
        max_chars = 40  # never split so tightly we would cut individual clauses/words
    chunks = _split_text_into_chunks(text, max_chars) or [text]
    logging.info(
        f"🗣️ Synthesising {len(text)} chars with model '{model}' in {len(chunks)} chunk(s) "
        f"(voice={voice}, gender={gender or 'n/a'}, lang={language}"
        f"{', emotion=' + emotion if emotion else ''}) @ {base}"
    )

    output_dir = resolve_output_dir(config)
    out_sample_rate = _coerce_int(config.get('sample_rate', 0), 0)

    result: Dict = {
        "output_path": "",
        "output_dir": output_dir,
        "filename": "",
        "model": model,
        "language": language,
        "voice": voice,
        "gender": gender,
        "emotion": emotion,
        "sample_rate": _ORPHEUS_SAMPLE_RATE,
        "audio_seconds": 0.0,
        "char_count": len(text),
        "played": False,
        "status": "error",
    }

    # === LONG-TEXT PARTITIONING (talk for hours) ===========================
    # A single Orpheus generation is hard-capped by Ollama's num_predict
    # (max_tokens) — ~1200 tokens ≈ 14 s — so a one-shot call SILENTLY TRUNCATES
    # long speech (the reported bug: a 3567-char analysis spoke only ~50 s).
    # We synthesise each sentence-chunk separately (each well under the cap) and
    # concatenate the decoded audio, so the COMPLETE text is spoken no matter how
    # long it is. The SNAC vocoder is loaded once and reused across all chunks.
    vocoder_ok = _vocoder_available()
    if not vocoder_ok:
        logging.warning(
            "⚠️ snac+torch unavailable — fetching audio tokens but cannot render "
            "sound (status tokens_only). Install: python -m pip install snac torch"
        )

    pcm_parts: List = []
    raw_parts: List[str] = []
    all_codes: List[int] = []
    silence = None
    native_sr = _ORPHEUS_SAMPLE_RATE

    for i, chunk_text in enumerate(chunks):
        is_last = (i == len(chunks) - 1)
        # Emotion tags are inline events (a laugh, a sigh) — weave the configured
        # one into the LAST chunk only, never after every sentence.
        prompt_text = apply_emotion(chunk_text, config) if (is_last and emotion) else chunk_text
        prompt = build_orpheus_prompt(config, prompt_text)
        raw_text, _status = query_ollama_tts(config, prompt)
        codes = parse_audio_codes(raw_text)
        logging.info(
            f"🎚️ Chunk {i + 1}/{len(chunks)} ({len(chunk_text)} chars): model returned "
            f"{len(raw_text)} chars -> {len(codes)} SNAC audio codes"
        )
        raw_parts.append(raw_text)
        all_codes.extend(codes)

        if vocoder_ok and codes:
            try:
                pcm_chunk, native_sr = decode_codes_to_pcm(codes)
            except RuntimeError as dec_err:
                logging.warning(
                    f"⚠️ Chunk {i + 1} could not be decoded ({dec_err}); "
                    f"falling back to tokens_only."
                )
                vocoder_ok = False
                pcm_parts = []
                continue
            import numpy as np
            if silence is None:
                sil_ms = max(0, min(_coerce_int(config.get('inter_chunk_silence_ms', 120), 120), 2000))
                silence = np.zeros(int(native_sr * sil_ms / 1000.0), dtype=np.float32)
            if pcm_parts and silence.size:
                pcm_parts.append(silence)  # brief gap between sentences
            pcm_parts.append(pcm_chunk)

    if not all_codes:
        raise RuntimeError(
            f"The model '{model}' returned no <custom_token_*> audio tokens. "
            f"Confirm it is an Orpheus-style neural TTS model served by Ollama "
            f"(a plain text LLM will not produce audio tokens)."
        )

    # No vocoder (or nothing decoded) -> persist the tokens so the work is not lost.
    if not vocoder_ok or not pcm_parts:
        tokens_path = _unique_output_path(output_dir)[:-4] + ".tokens.txt"
        save_tokens(tokens_path, "\n\n".join(raw_parts), all_codes)
        result.update({
            "output_path": tokens_path,
            "filename": os.path.basename(tokens_path),
            "audio_seconds": 0.0,
            "played": False,
            "status": "tokens_only",
        })
        result["_message"] = (
            f"Fetched {len(all_codes)} audio codes across {len(chunks)} chunk(s) but could "
            f"not render sound (install snac+torch). Tokens saved to {tokens_path}."
        )
        return result

    import numpy as np
    pcm = np.concatenate(pcm_parts) if len(pcm_parts) > 1 else pcm_parts[0]

    # Peak-normalise so the speech is reliably audible (Orpheus output is quiet).
    pcm = _normalize_peak(pcm, config)

    # The configured sample_rate (0 = the model's native 24 kHz) only affects
    # the OUTPUT stream rate; the decoded PCM is always native 24 kHz.
    play_sr = out_sample_rate if out_sample_rate > 0 else native_sr
    audio_seconds = len(pcm) / float(native_sr)

    wav_path = _unique_output_path(output_dir)
    save_wav(wav_path, pcm, native_sr)
    logging.info(
        f"✅ Speech saved: {wav_path} ({audio_seconds:g}s, {native_sr} Hz mono) "
        f"from {len(chunks)} chunk(s)"
    )

    played = False
    if _coerce_bool(config.get('play_audio', True), True):
        try:
            import sounddevice  # noqa: F401
            _log_output_devices()
            play_pcm(pcm, play_sr, config)
            played = True
        except Exception as play_err:
            logging.error(f"❌ Could not play the audio ({play_err}). The WAV was still saved.")
    else:
        logging.info("🔇 play_audio is false — speech saved to disk but not played.")

    result.update({
        "output_path": wav_path,
        "filename": os.path.basename(wav_path),
        "sample_rate": play_sr,
        "audio_seconds": round(audio_seconds, 3),
        "played": played,
        "status": "spoken" if played else "saved",
    })
    result["_message"] = (
        f"Spoke {len(text)} chars as {audio_seconds:g}s of audio across {len(chunks)} chunk(s) "
        f"(voice={voice}, lang={language}, model={model}); saved to {wav_path}"
        + ("" if played else " (not played)")
    )
    return result


# PID Management
PID_FILE = "agent.pid"


def write_pid_file():
    try:
        with open(PID_FILE, "w") as f:
            f.write(str(os.getpid()))
    except Exception as e:
        logging.error(f"❌ Failed to write PID file: {e}")


def remove_pid_file():
    for attempt in range(5):
        try:
            if os.path.exists(PID_FILE):
                os.remove(PID_FILE)
            return
        except PermissionError:
            time.sleep(0.1)
        except Exception as e:
            logging.error(f"❌ Failed to remove PID file: {e}")
            return


def emit_parametrizer_section(result: Dict):
    """
    Emit a single, atomic Parametrizer-compatible block so downstream agents
    (and the Multi-Turn LLM) can read the exact spoken-WAV path, the audio
    length, and the status verbatim. Keep this in ONE logging.info() call so
    concurrent writes can never interleave and corrupt the block.
    """
    output_path = result["output_path"]
    body = result.get("_message") or f"Spoke {result['char_count']} chars."
    logging.info(
        "INI_SECTION_TALKER<<<\n"
        f"output_path: {output_path}\n"
        f"output_dir: {result['output_dir']}\n"
        f"filename: {result['filename']}\n"
        f"model: {result['model']}\n"
        f"language: {result['language']}\n"
        f"voice: {result['voice']}\n"
        f"gender: {result['gender']}\n"
        f"emotion: {result['emotion']}\n"
        f"sample_rate: {result['sample_rate']}\n"
        f"audio_seconds: {result['audio_seconds']:g}\n"
        f"char_count: {result['char_count']}\n"
        f"played: {str(result['played']).lower()}\n"
        f"status: {result['status']}\n"
        "\n"
        f"{body}\n"
        ">>>END_SECTION_TALKER"
    )


def emit_parametrizer_error_section(config: Dict, error_message: str):
    """
    Emit an INI_SECTION_TALKER block describing a FAILED synthesis so the error
    is still Parametrizer-readable (status: error) and a downstream Forker can
    branch on it. Single atomic logging.info() call.
    """
    one_line_error = " ".join(str(error_message).splitlines()).strip()
    _report_voice, _report_gender = _safe_report_voice(config)
    logging.info(
        "INI_SECTION_TALKER<<<\n"
        f"output_path: \n"
        f"output_dir: {resolve_output_dir(config)}\n"
        f"filename: \n"
        f"model: {config.get('model', 'Orpheus-3b-FT')}\n"
        f"language: {config.get('language', 'en')}\n"
        f"voice: {_report_voice}\n"
        f"gender: {_report_gender}\n"
        f"emotion: {str(config.get('emotion') or '').strip().lower().strip('<>')}\n"
        f"sample_rate: 0\n"
        f"audio_seconds: 0\n"
        f"char_count: {len(str(config.get('input_text') or ''))}\n"
        f"played: false\n"
        f"status: error\n"
        "\n"
        f"Talker FAILED: {one_line_error}\n"
        ">>>END_SECTION_TALKER"
    )


def _die_male_voice_forbidden(config: Dict, forbidden: Exception) -> None:
    """
    By-design FATAL handler: a male / non-female voice was requested.

    Reports the refusal (log banner + a single Parametrizer-readable error
    section), then CLOSES THE WHOLE EXECUTION IMMEDIATELY. It does NOT return, it
    does NOT trigger downstream agents, and it does NOT run the normal teardown:
    a male-voice request is forbidden by design, so the process simply ends.
    """
    one_line = " ".join(str(forbidden).splitlines()).strip()
    logging.critical("=" * 60)
    logging.critical("⛔ MALE VOICE IS FORBIDDEN BY DESIGN — Tlamatini is female.")
    logging.critical(f"⛔ Refused request: {one_line}")
    logging.critical("⛔ NOW CLOSING.. BYE")
    logging.critical("=" * 60)
    try:
        emit_parametrizer_error_section(
            config,
            f"FORBIDDEN BY DESIGN: a male voice is not permitted ({one_line}). "
            f"Tlamatini is female and NEVER speaks with a male voice. NOW CLOSING.. BYE",
        )
    except Exception:
        pass
    try:
        remove_pid_file()
    except Exception:
        pass
    try:
        sys.stdout.flush()
        sys.stderr.flush()
    except Exception:
        pass
    # Close the ENTIRE execution right now (bypass all teardown / downstream).
    os._exit(70)


def main():
    config = load_config()

    # Write PID file immediately
    write_pid_file()
    if _IS_REANIMATED:
        logging.info(f"🔄 {CURRENT_DIR_NAME} REANIMATED (resuming from pause)")
        logging.info("=" * 60)

    try:
        target_agents = config.get('target_agents', []) or []

        logging.info("🗣️ TALKER AGENT STARTED (Ollama TTS)")
        logging.info(
            f"🤖 Model: {config.get('model', 'Orpheus-3b-FT')} @ "
            f"{config.get('ollama_url', 'http://localhost:11434')}"
        )
        logging.info(f"🎯 Targets: {target_agents}")
        logging.info("=" * 60)

        synth_ok = True
        try:
            result = synthesize(config)
            logging.info(
                f"🏷️ Status: {result['status']} | {result['audio_seconds']:g}s | "
                f"played={result['played']}"
            )
            emit_parametrizer_section(result)
            if result['status'] == 'error':
                synth_ok = False
        except MaleVoiceForbiddenError as forbidden:
            # FORBIDDEN BY DESIGN: a male / non-female voice was requested. Do NOT
            # recover, do NOT substitute, do NOT trigger downstream — report the
            # error and CLOSE THE WHOLE EXECUTION immediately. This never returns.
            _die_male_voice_forbidden(config, forbidden)
        except Exception as e:
            synth_ok = False
            logging.error(f"❌ TTS synthesis failed: {e}")
            emit_parametrizer_error_section(config, str(e))

        # Trigger downstream agents — ALWAYS, success or failure (so a Forker can
        # branch on {status}). This matches AudioPlayer/Recorder/Camcorder.
        total_triggered = 0
        if target_agents:
            wait_for_agents_to_stop(target_agents)
            logging.info(f"🚀 Triggering {len(target_agents)} downstream agents...")
            for target in target_agents:
                if start_agent(target):
                    total_triggered += 1

        logging.info(
            f"🏁 Talker agent finished ({'OK' if synth_ok else 'with errors'}). "
            f"Triggered {total_triggered}/{len(target_agents)} agents."
        )

    finally:
        # Keep LED green briefly for visual feedback
        time.sleep(0.4)
        remove_pid_file()

    sys.exit(0)


if __name__ == "__main__":
    main()
