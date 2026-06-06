# AudioPlayer Agent - Plays an audio FILE through a system OUTPUT device.
# Action: Triggered by upstream -> Read an audio file (soundfile) -> Resolve a
#         system audio OUTPUT device (speakers / audio out) -> Apply a software
#         volume gain -> Play for `time_played` seconds (truncating a long file
#         or looping a short one with a streaming callback) -> Emit a
#         Parametrizer-readable INI_SECTION_AUDIOPLAYER block with the full path
#         of the played file and the time played -> Trigger downstream agents.
#
# The PLAYBACK counterpart of the media-I/O family:
#   Shoter = screen, Camcorder = camera, Recorder = microphone-IN,
#   AudioPlayer = speakers-OUT. Observational/output (mutates no persistent
#   state), so — like Shoter/Recorder/Camcorder — it is NOT in the Exec Report.

import os
import sys

# FIX: Disable Intel Fortran runtime Ctrl+C handler
os.environ['FOR_DISABLE_CONSOLE_CTRL_HANDLER'] = '1'

import re
import time
import yaml
import logging
import threading
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
# AUDIOPLAYER-SPECIFIC HELPERS
# ========================================

def _coerce_float(value, default: float) -> float:
    """
    Best-effort numeric coercion that NEVER raises.

    The LLM / request parser can hand us a slightly-dirty value (e.g.
    ``"10 seconds"``, ``"48000 Hz"``, ``""``). Rather than crash playback on
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


def resolve_audio_file(config: Dict) -> str:
    """
    Resolve the configured audio file path to an absolute path.

    An absolute path is honored as-is; a relative path is resolved against the
    agent's runtime directory. ``~`` is expanded. Does NOT check existence —
    that is done by the caller so it can produce a precise error message.
    """
    raw = str(config.get('audio_file') or '').strip().strip('"').strip("'")
    if not raw:
        return ''
    expanded = os.path.expanduser(raw)
    if not os.path.isabs(expanded):
        expanded = os.path.join(script_dir, expanded)
    return os.path.abspath(expanded)


def _list_output_devices() -> List[Tuple[int, str, int, float]]:
    """
    Enumerate every OUTPUT-capable device.

    Returns a list of (index, name, max_output_channels, default_samplerate).
    """
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
    Resolve which OUTPUT device (speakers / audio out) to play through.

    Returns (device_arg, device_index, device_name, device_info):
      - device_arg   : value to pass to sounddevice (None == system default)
      - device_index : resolved numeric index (or -1 when unknown/default)
      - device_name  : human-readable device name
      - device_info  : the PortAudio device-info dict (for samplerate/channels)
    """
    import sounddevice as sd

    requested_index = _coerce_int(config.get('device_index', -1), -1)
    requested_name = str(config.get('device_name') or '').strip()

    if requested_index >= 0:
        info = sd.query_devices(requested_index, 'output')
        return requested_index, requested_index, str(info.get('name', '')), info

    if requested_name:
        idx = _find_output_device_by_name(requested_name)
        info = sd.query_devices(idx, 'output')
        return idx, idx, str(info.get('name', '')), info

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
    return None, default_idx, str(info.get('name', '')), info


def _downmix(data, target_channels: int):
    """
    Reduce ``data`` (shape ``(frames, channels)``) to ``target_channels``.

    - target == source  -> returned unchanged.
    - target == 1        -> average all channels into mono (so a stereo file on
                            a mono speaker plays both channels, not just left).
    - 1 < target < source-> keep the first ``target`` channels.
    Never UP-mixes (the caller only calls this when source > target).
    """
    import numpy as np
    src_channels = data.shape[1]
    if target_channels >= src_channels:
        return data
    if target_channels == 1:
        return np.mean(data, axis=1, keepdims=True).astype(np.float32)
    return np.ascontiguousarray(data[:, :target_channels])


def _apply_volume(data, volume_percent: float):
    """
    Apply SOFTWARE (digital) volume to a float32 buffer in [-1, 1]. Returns
    ``(buffer, clipped_samples)``.

    ``volume_percent`` is a percentage: 100 == unity (buffer returned
    unchanged), 200 == +6 dB louder, 50 == -6 dB quieter, 0 == silence.
    Amplifying a hot file pushes samples past the [-1, 1] rail; those are
    counted (so a downstream Forker / log reader can react) and then clipped.
    """
    import numpy as np

    factor = max(0.0, float(volume_percent)) / 100.0
    if abs(factor - 1.0) <= 1e-9:
        return data, 0

    scaled = data.astype(np.float32) * factor
    clipped_samples = int(np.count_nonzero((scaled > 1.0) | (scaled < -1.0)))
    scaled = np.clip(scaled, -1.0, 1.0)
    return np.ascontiguousarray(scaled, dtype=np.float32), clipped_samples


def play_audio(config: Dict) -> Dict:
    """
    Play the configured audio file through the resolved output device for
    ``time_played`` seconds (whole-file-once when 0, truncated when the file is
    longer, looped when shorter). Returns a dict describing the playback.
    """
    import numpy as np
    import sounddevice as sd
    import soundfile as sf

    audio_path = resolve_audio_file(config)
    if not audio_path:
        raise RuntimeError("No audio_file configured — set audio_file to the path of the file to play.")
    if not os.path.exists(audio_path):
        raise RuntimeError(f"Audio file not found: {audio_path}")

    # --- Read the file (always 2-D: frames x channels), float32 in [-1, 1] ---
    try:
        data, file_sample_rate = sf.read(audio_path, dtype='float32', always_2d=True)
    except Exception as e:
        raise RuntimeError(
            f"Could not decode audio file '{audio_path}': {e}. "
            f"Supported formats depend on the installed libsndfile "
            f"(WAV / FLAC / OGG / AIFF always; MP3 needs a recent libsndfile)."
        )
    file_sample_rate = int(file_sample_rate)
    file_frames = int(data.shape[0])
    if file_frames <= 0:
        raise RuntimeError(f"Audio file '{audio_path}' contains no samples.")
    file_channels = int(data.shape[1])
    file_duration = file_frames / float(file_sample_rate)

    # --- Output device --------------------------------------------------------
    device_arg, device_index, device_name, info = resolve_output_device(config)
    max_out = int(info.get('max_output_channels', 2) or 2)
    if max_out <= 0:
        max_out = 2

    # --- Channels (downmix to the device's capability if needed) -------------
    channels = file_channels
    if file_channels > max_out:
        data = _downmix(data, max_out)
        channels = max_out

    # --- Playback sample rate (0 == the file's own native rate) --------------
    requested_rate = _coerce_int(config.get('sample_rate', 0), 0)
    if requested_rate > 0:
        play_sample_rate = requested_rate
        if play_sample_rate != file_sample_rate:
            logging.warning(
                f"⚠️ sample_rate={play_sample_rate} Hz differs from the file's native "
                f"{file_sample_rate} Hz — the audio is NOT resampled, so pitch/tempo "
                f"will be altered. Set sample_rate: 0 to play at the correct pitch."
            )
    else:
        play_sample_rate = file_sample_rate

    # --- Software volume (% ; 100 == unity) ----------------------------------
    volume_percent = _coerce_float(config.get('volume_percent', 100), 100)
    if volume_percent < 0:
        volume_percent = 0.0
    data, clipped_samples = _apply_volume(data, volume_percent)
    if clipped_samples > 0:
        total = int(getattr(data, 'size', 0) or 0)
        logging.warning(
            f"⚠️ Volume {volume_percent:g}% clipped {clipped_samples}/{total} samples "
            f"to the [-1, 1] rail (file too hot for this volume)."
        )
    data = np.ascontiguousarray(data, dtype=np.float32)

    # --- How many frames to emit (the truncate / loop math) ------------------
    time_played = _coerce_float(config.get('time_played', 0), 0)
    if time_played <= 0:
        target_frames = file_frames           # whole file, exactly once
        play_mode = "full"
    else:
        target_frames = max(1, int(round(time_played * play_sample_rate)))
        if target_frames < file_frames:
            play_mode = "truncated"
        elif target_frames == file_frames:
            play_mode = "full"
        else:
            play_mode = "looped"

    full_loops = target_frames // file_frames
    has_partial = (target_frames % file_frames) != 0
    played_seconds = target_frames / float(play_sample_rate)

    device_tag = str(device_index) if device_index >= 0 else "default"
    logging.info(
        f"🔊 Playing '{audio_path}'\n"
        f"     device [{device_tag}] '{device_name}' | file {file_sample_rate} Hz "
        f"{file_channels}ch, {file_duration:g}s | out {play_sample_rate} Hz {channels}ch | "
        f"volume {volume_percent:g}% | mode={play_mode} | "
        f"time_played={time_played:g}s -> playing {played_seconds:g}s "
        f"(loops={full_loops}{'+partial' if has_partial else ''})"
    )

    # --- Stream the output with a wrap-around callback -----------------------
    # A single callback handles all three modes: it copies frames from the
    # decoded buffer with wrap-around and stops after exactly target_frames.
    #   * full / truncated -> target_frames <= file_frames, never wraps.
    #   * looped           -> target_frames  > file_frames, wraps to repeat.
    # Streaming means a huge time_played over a tiny file never allocates a
    # giant buffer.
    state = {"read_idx": 0, "emitted": 0}
    done = threading.Event()

    def _callback(outdata, frames, _time_info, status):
        if status:
            logging.warning(f"⚠️ Output stream status: {status}")
        remaining = target_frames - state["emitted"]
        if remaining <= 0:
            raise sd.CallbackStop()
        n = min(frames, remaining)
        filled = 0
        while filled < n:
            chunk = min(n - filled, file_frames - state["read_idx"])
            outdata[filled:filled + chunk] = data[state["read_idx"]:state["read_idx"] + chunk]
            state["read_idx"] += chunk
            if state["read_idx"] >= file_frames:
                state["read_idx"] = 0
            filled += chunk
        if n < frames:
            outdata[n:] = 0
        state["emitted"] += n
        if state["emitted"] >= target_frames:
            raise sd.CallbackStop()

    stream = sd.OutputStream(
        samplerate=play_sample_rate,
        channels=channels,
        dtype='float32',
        device=device_arg,
        callback=_callback,
        finished_callback=done.set,
    )
    # Fail-safe wait bound: the playback length plus a margin. If the device
    # wedges, we stop rather than hang the agent (and its downstream) forever.
    wait_timeout = played_seconds + 10.0
    with stream:
        if not done.wait(timeout=wait_timeout):
            logging.warning(
                f"⚠️ Playback did not finish within {wait_timeout:g}s — stopping the "
                f"stream (emitted {state['emitted']}/{target_frames} frames)."
            )

    return {
        "input_path": audio_path,
        "device_index": device_index,
        "device_name": device_name,
        "file_sample_rate": file_sample_rate,
        "play_sample_rate": play_sample_rate,
        "channels": channels,
        "volume_percent": volume_percent,
        "clipped_samples": clipped_samples,
        "file_duration_seconds": round(file_duration, 3),
        "time_played_requested": time_played,
        "played_seconds": round(played_seconds, 3),
        "play_mode": play_mode,
        "loops": full_loops,
        "partial_segment": has_partial,
        "format": os.path.splitext(audio_path)[1].lstrip('.').lower() or "unknown",
    }


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
    (and the Multi-Turn LLM) can read the exact played path + time played
    verbatim. Keep this in ONE logging.info() call so concurrent writes can
    never interleave and corrupt the block.
    """
    input_path = result["input_path"]
    logging.info(
        "INI_SECTION_AUDIOPLAYER<<<\n"
        f"input_path: {input_path}\n"
        f"input_dir: {os.path.dirname(input_path)}\n"
        f"filename: {os.path.basename(input_path)}\n"
        f"device_index: {result['device_index']}\n"
        f"device_name: {result['device_name']}\n"
        f"file_sample_rate: {result['file_sample_rate']}\n"
        f"play_sample_rate: {result['play_sample_rate']}\n"
        f"channels: {result['channels']}\n"
        f"volume_percent: {result['volume_percent']:g}\n"
        f"clipped_samples: {result['clipped_samples']}\n"
        f"file_duration_seconds: {result['file_duration_seconds']:g}\n"
        f"time_played_requested: {result['time_played_requested']:g}\n"
        f"played_seconds: {result['played_seconds']:g}\n"
        f"play_mode: {result['play_mode']}\n"
        f"loops: {result['loops']}\n"
        f"partial_segment: {str(result['partial_segment']).lower()}\n"
        f"format: {result['format']}\n"
        f"status: played\n"
        "\n"
        f"Played {input_path} for {result['played_seconds']:g}s "
        f"(mode={result['play_mode']}, file {result['file_duration_seconds']:g}s, "
        f"{result['play_sample_rate']} Hz {result['channels']}ch, "
        f"volume {result['volume_percent']:g}%).\n"
        ">>>END_SECTION_AUDIOPLAYER"
    )


def emit_parametrizer_error_section(input_path: str, error_message: str, time_played_requested: float):
    """
    Emit an INI_SECTION_AUDIOPLAYER block describing a FAILED playback so the
    error is still Parametrizer-readable (status: error) and a downstream Forker
    can branch on it. Single atomic logging.info() call, same as the success path.
    """
    safe_path = input_path or "(unresolved)"
    one_line_error = " ".join(str(error_message).splitlines()).strip()
    logging.info(
        "INI_SECTION_AUDIOPLAYER<<<\n"
        f"input_path: {safe_path}\n"
        f"input_dir: {os.path.dirname(safe_path) if input_path else ''}\n"
        f"filename: {os.path.basename(safe_path) if input_path else ''}\n"
        f"device_index: -1\n"
        f"device_name: \n"
        f"file_sample_rate: 0\n"
        f"play_sample_rate: 0\n"
        f"channels: 0\n"
        f"volume_percent: 0\n"
        f"clipped_samples: 0\n"
        f"file_duration_seconds: 0\n"
        f"time_played_requested: {time_played_requested:g}\n"
        f"played_seconds: 0\n"
        f"play_mode: error\n"
        f"loops: 0\n"
        f"partial_segment: false\n"
        f"format: unknown\n"
        f"status: error\n"
        "\n"
        f"AudioPlayer FAILED for {safe_path}: {one_line_error}\n"
        ">>>END_SECTION_AUDIOPLAYER"
    )


def main():
    config = load_config()

    # Write PID file immediately
    write_pid_file()
    if _IS_REANIMATED:
        logging.info(f"🔄 {CURRENT_DIR_NAME} REANIMATED (resuming from pause)")
        logging.info("=" * 60)

    try:
        target_agents = config.get('target_agents', []) or []
        time_played_requested = _coerce_float(config.get('time_played', 0), 0)

        logging.info("🔊 AUDIOPLAYER AGENT STARTED")
        logging.info(f"🎯 Targets: {target_agents}")

        # Verify the audio stack is importable BEFORE touching a device so the
        # error is unambiguous rather than a cryptic mid-playback traceback.
        try:
            import sounddevice  # noqa: F401
            import soundfile    # noqa: F401
        except Exception as imp_err:
            logging.error(
                "❌ The audio playback stack is not available in this Python "
                f"({imp_err}). AudioPlayer needs both 'sounddevice' and 'soundfile'. "
                "Install them with: python -m pip install sounddevice soundfile"
            )
            emit_parametrizer_error_section(
                resolve_audio_file(config), str(imp_err), time_played_requested)
            sys.exit(1)

        # Help the user pick a device: always print the output-device map.
        _log_output_devices()

        playback_ok = True
        try:
            result = play_audio(config)
            logging.info(f"✅ Playback finished: {result['input_path']}")
            logging.info(
                f"   Device: [{result['device_index']}] {result['device_name']} | "
                f"Out: {result['play_sample_rate']} Hz {result['channels']}ch | "
                f"Played: {result['played_seconds']:g}s (mode={result['play_mode']}, "
                f"loops={result['loops']})"
            )
            emit_parametrizer_section(result)
        except Exception as e:
            playback_ok = False
            logging.error(f"❌ Audio playback failed: {e}")
            emit_parametrizer_error_section(
                resolve_audio_file(config), str(e), time_played_requested)

        # Trigger downstream agents — ALWAYS, success or failure (so a Forker can
        # branch on {status}). This matches Recorder/Camcorder's contract.
        total_triggered = 0
        if target_agents:
            wait_for_agents_to_stop(target_agents)
            logging.info(f"🚀 Triggering {len(target_agents)} downstream agents...")
            for target in target_agents:
                if start_agent(target):
                    total_triggered += 1

        logging.info(
            f"🏁 AudioPlayer agent finished ({'OK' if playback_ok else 'with errors'}). "
            f"Triggered {total_triggered}/{len(target_agents)} agents."
        )

    finally:
        # Keep LED green briefly for visual feedback
        time.sleep(0.4)
        remove_pid_file()

    sys.exit(0)


if __name__ == "__main__":
    main()
