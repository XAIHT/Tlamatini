# Recorder Agent - Microphone / audio-input capture agent via sounddevice
# Action: Triggered by upstream -> Open a system audio INPUT device (mic) ->
#         Record record_seconds of audio -> Save a WAV to the user's Music
#         folder under TlamatiniRecords with a collision-proof name -> Emit a
#         Parametrizer-readable INI_SECTION_RECORDER block with the full path ->
#         Trigger downstream agents.
#
# Audio sibling of Camcorder (camera) and Shoter (screen). Records SOUND.

import os
import sys

# FIX: Disable Intel Fortran runtime Ctrl+C handler
os.environ['FOR_DISABLE_CONSOLE_CTRL_HANDLER'] = '1'

import re
import time
import threading
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
from datetime import datetime
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
# RECORDER-SPECIFIC HELPERS
# ========================================

def _coerce_float(value, default: float) -> float:
    """
    Best-effort numeric coercion that NEVER raises.

    The LLM / request parser can hand us a slightly-dirty value (e.g.
    ``"1 from the default microphone"``, ``"48000 Hz"``, ``""``). Rather than
    crash the whole capture on ``float(...)``, extract the leading
    signed number and fall back to ``default`` when there is none.
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


def _apply_gain(recording, gain_percent: float):
    """
    Apply SOFTWARE (digital) gain to an int16 PCM buffer. Returns
    ``(buffer, clipped_samples)``.

    ``gain_percent`` is a percentage: 100 == unity (buffer returned unchanged,
    byte-identical), 200 == +6 dB amplify, 50 == -6 dB attenuate, 0 == silence.
    This is post-capture digital scaling — it cannot recover detail below the
    mic's noise floor (it amplifies noise too), and amplifying a hot signal can
    clip; the number of samples that hit the int16 rail is counted and returned
    so a downstream Forker / log reader can react. Multiplication is done in a
    wider float dtype, then rounded and clipped to the int16 range.
    """
    import numpy as np

    factor = max(0.0, float(gain_percent)) / 100.0
    if abs(factor - 1.0) <= 1e-9:
        return recording, 0  # unity -> untouched

    widened = recording.astype(np.float32) * factor
    clipped_samples = int(np.count_nonzero((widened > 32767) | (widened < -32768)))
    widened = np.clip(np.round(widened), -32768, 32767)
    return widened.astype(np.int16), clipped_samples


def get_music_dir() -> str:
    """
    Resolve the current user's *Music* known-folder as a real absolute path.

    On a localized Windows the folder is *displayed* as e.g. "Música" /
    "Musik", but the on-disk path is what we must write to. The Win32
    known-folder API (SHGetKnownFolderPath, FOLDERID_Music) returns the true
    path regardless of the display name. We fall back to ~/Music on any
    failure or non-Windows host.
    """
    if os.name == 'nt':
        try:
            import ctypes
            from ctypes import wintypes

            class _GUID(ctypes.Structure):
                _fields_ = [
                    ("Data1", wintypes.DWORD),
                    ("Data2", wintypes.WORD),
                    ("Data3", wintypes.WORD),
                    ("Data4", ctypes.c_byte * 8),
                ]

            # FOLDERID_Music = {4BD8D571-6D19-48D3-BE97-422220080E43}
            folderid_music = _GUID(
                0x4BD8D571, 0x6D19, 0x48D3,
                (ctypes.c_byte * 8)(0xBE, 0x97, 0x42, 0x22, 0x20, 0x08, 0x0E, 0x43),
            )

            path_ptr = ctypes.c_wchar_p()
            res = ctypes.windll.shell32.SHGetKnownFolderPath(
                ctypes.byref(folderid_music), 0, None, ctypes.byref(path_ptr)
            )
            if res == 0 and path_ptr.value:
                resolved = path_ptr.value
                ctypes.windll.ole32.CoTaskMemFree(path_ptr)
                return resolved
        except Exception as e:
            logging.warning(f"⚠️ Could not resolve Music known-folder via Win32 API: {e}")

    return os.path.join(os.path.expanduser('~'), 'Music')


def resolve_output_dir(config: Dict) -> str:
    """
    Decide where to save the recorded audio.

    - If config.output_dir is set, honor it (resolved relative to the agent
      directory when not absolute).
    - Otherwise default to <Music>/TlamatiniRecords.
    """
    configured = str(config.get('output_dir') or '').strip()
    if configured:
        if not os.path.isabs(configured):
            configured = os.path.join(script_dir, configured)
        return configured
    return os.path.join(get_music_dir(), 'TlamatiniRecords')


def build_unique_path(output_dir: str, device_tag: str, ext: str) -> str:
    """
    Build a collision-proof absolute file path under output_dir.

    Name shape:  recorder_<YYYYmmdd>_<HHMMSS>_<ms>_dev<tag>.<ext>
    The millisecond stamp + device tag makes overwrites practically
    impossible; a defensive counter suffix guarantees uniqueness even on the
    astronomically unlikely same-millisecond collision.
    """
    os.makedirs(output_dir, exist_ok=True)
    now = datetime.now()
    stamp = now.strftime("%Y%m%d_%H%M%S_") + f"{now.microsecond // 1000:03d}"
    base = f"recorder_{stamp}_dev{device_tag}"
    candidate = os.path.join(output_dir, f"{base}.{ext}")
    counter = 1
    while os.path.exists(candidate):
        candidate = os.path.join(output_dir, f"{base}_{counter}.{ext}")
        counter += 1
    return os.path.abspath(candidate)


def _list_input_devices() -> List[Tuple[int, str, int, float]]:
    """
    Enumerate every input-capable device.

    Returns a list of (index, name, max_input_channels, default_samplerate).
    """
    import sounddevice as sd
    devices = []
    for idx, dev in enumerate(sd.query_devices()):
        max_in = int(dev.get('max_input_channels', 0) or 0)
        if max_in > 0:
            devices.append((
                idx,
                str(dev.get('name', '')),
                max_in,
                float(dev.get('default_samplerate', 0) or 0),
            ))
    return devices


def _log_input_devices():
    """Log the available input devices so a user can read the right index."""
    try:
        devices = _list_input_devices()
    except Exception as e:
        logging.warning(f"⚠️ Could not enumerate input devices: {e}")
        return
    if not devices:
        logging.warning("⚠️ No audio INPUT devices were found on this system.")
        return
    logging.info(f"🎚️ Available audio input devices ({len(devices)}):")
    for idx, name, max_in, sr in devices:
        logging.info(f"     [{idx}] {name}  (max_in_channels={max_in}, default_rate={int(sr)} Hz)")


def _find_input_device_by_name(substring: str) -> int:
    """Return the first input-capable device whose name contains substring (ci)."""
    target = substring.strip().lower()
    for idx, name, _max_in, _sr in _list_input_devices():
        if target in name.lower():
            return idx
    raise RuntimeError(
        f"No audio INPUT device matching name '{substring}'. "
        f"Check the device list logged above and use a numeric device_index."
    )


def resolve_input_device(config: Dict):
    """
    Resolve which input device to record from.

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
        info = sd.query_devices(requested_index, 'input')
        return requested_index, requested_index, str(info.get('name', '')), info

    if requested_name:
        idx = _find_input_device_by_name(requested_name)
        info = sd.query_devices(idx, 'input')
        return idx, idx, str(info.get('name', '')), info

    # System default input device.
    info = sd.query_devices(kind='input')
    default_idx = -1
    try:
        dd = sd.default.device
        default_idx = int(dd[0]) if dd and dd[0] is not None else -1
    except Exception:
        default_idx = -1
    if default_idx < 0:
        try:
            default_idx = int(info.get('index', -1))
        except (TypeError, ValueError):
            default_idx = -1
    return None, default_idx, str(info.get('name', '')), info


class MicRecIndicator:
    """Zero-latency, ALWAYS-VISIBLE console REC light driven by the LIVE mic.

    Ported verbatim from the Whisperer agent (pool subprocesses cannot import
    each other, so the ~120 lines are duplicated by design -- see acpxer.py for
    the same inline-mirror pattern). Honesty contract: ``on()`` fires from the
    FIRST audio callback (light ON within one ~20 ms block of real samples --
    inside the 50 ms budget), ``level(peak)`` feeds the true per-block peak so
    the VU bar dances with your voice, and ``off()`` paints the stopped state
    SYNCHRONOUSLY the instant the stream is torn down. Because the pool launcher
    spawns this agent DETACHED with stdio to DEVNULL (no console at all), ``on()``
    AllocConsole()s its own window (or reuses an existing one), reveals it, and
    paints to CONOUT$ directly. Fail-safe: nothing here can raise into capture.
    """

    _BAR_W = 22
    _LINGER_SECONDS = 1.4

    def __init__(self, total_seconds: float):
        self._out = sys.stderr
        self._total = max(0.001, float(total_seconds))
        self._color = False
        self._allocated = False
        self._active = False
        self._peak = 0.0
        self._t0 = 0.0
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread = None

    def _acquire_console(self):
        if os.name != 'nt':
            self._out = sys.stderr
            self._color = bool(getattr(sys.stderr, 'isatty', lambda: False)())
            return
        try:
            import ctypes
            import msvcrt
            k32 = ctypes.windll.kernel32
            u32 = ctypes.windll.user32
            hwnd = k32.GetConsoleWindow()
            if not hwnd:
                if k32.AllocConsole():
                    self._allocated = True
                hwnd = k32.GetConsoleWindow()
            if hwnd:
                u32.ShowWindow(hwnd, 1)            # SW_SHOWNORMAL -> reveal it
                try:
                    u32.SetForegroundWindow(hwnd)
                except Exception:
                    pass
            try:
                k32.SetConsoleTitleW("\U0001f399  Tlamatini Recorder  --  RECORDING")
            except Exception:
                pass
            writer = open('CONOUT$', 'w', encoding='utf-8', buffering=1)
            self._out = writer
            try:
                h = msvcrt.get_osfhandle(writer.fileno())
                mode = ctypes.c_uint32()
                if k32.GetConsoleMode(h, ctypes.byref(mode)):
                    if k32.SetConsoleMode(h, mode.value | 0x0004):  # ENABLE_VT
                        self._color = True
            except Exception:
                self._color = False
        except Exception:
            self._out = sys.stderr
            self._color = False

    def _release_console(self):
        try:
            if self._out not in (sys.stderr, sys.stdout):
                try:
                    self._out.flush()
                    self._out.close()
                except Exception:
                    pass
            if self._allocated and os.name == 'nt':
                import ctypes
                ctypes.windll.kernel32.FreeConsole()
        except Exception:
            pass

    def on(self):
        try:
            with self._lock:
                if self._active:
                    return
                self._active = True
                self._t0 = time.perf_counter()
            self._acquire_console()
            self._paint(blink_on=True)
            self._thread = threading.Thread(target=self._animate, daemon=True)
            self._thread.start()
        except Exception:
            pass

    def level(self, peak: float):
        try:
            self._peak = 0.0 if peak < 0 else (1.0 if peak > 1 else float(peak))
        except Exception:
            pass

    def off(self, captured_seconds: float = 0.0):
        try:
            with self._lock:
                if not self._active:
                    return
                self._active = False
            self._stop.set()
            if self._thread is not None:
                self._thread.join(timeout=0.25)
            self._paint_stopped(captured_seconds)
            if self._allocated:
                time.sleep(self._LINGER_SECONDS)
            self._release_console()
        except Exception:
            pass

    def _animate(self):
        blink = True
        while not self._stop.wait(0.45):
            blink = not blink
            self._paint(blink_on=blink)

    def _elapsed(self) -> float:
        return max(0.0, time.perf_counter() - self._t0)

    def _vu_bar(self) -> str:
        filled = int(round(self._peak * self._BAR_W))
        if not self._color:
            return '[' + '#' * filled + '-' * (self._BAR_W - filled) + ']'
        cells = []
        for i in range(self._BAR_W):
            if i < filled:
                frac = i / max(1, self._BAR_W - 1)
                col = '\x1b[92m' if frac < 0.6 else ('\x1b[93m' if frac < 0.85 else '\x1b[91m')
                cells.append(col + '█')
            else:
                cells.append('\x1b[90m─')
        return '[' + ''.join(cells) + '\x1b[0m]'

    def _paint(self, blink_on: bool):
        try:
            el = self._elapsed()
            if self._color:
                dot = '\x1b[1;91m●\x1b[0m' if blink_on else '\x1b[2;31m●\x1b[0m'
                label = '\x1b[1;91m REC \x1b[0m'
            else:
                dot = '(*)' if blink_on else '( )'
                label = ' REC '
            line = f"\r\x1b[2K {dot}{label}{self._vu_bar()} {el:5.1f}s / {self._total:.0f}s "
            self._out.write(line)
            self._out.flush()
        except Exception:
            pass

    def _paint_stopped(self, captured_seconds: float):
        try:
            if self._color:
                tag = '\x1b[1;92m■ REC STOPPED ✓\x1b[0m'
            else:
                tag = '[#] REC STOPPED OK'
            self._out.write(f"\r\x1b[2K {tag}  captured {captured_seconds:.1f}s\n")
            self._out.flush()
        except Exception:
            pass


def record_audio(config: Dict, output_dir: str):
    """
    Record record_seconds of audio from the resolved input device and save a
    WAV file. Returns a dict describing the saved file and capture settings.
    """
    import numpy as np
    import sounddevice as sd

    device_arg, device_index, device_name, info = resolve_input_device(config)

    # --- Duration ---------------------------------------------------------
    record_seconds = _coerce_float(config.get('record_seconds', 5), 5)
    if record_seconds <= 0:
        record_seconds = 5.0

    # --- Sample rate (0 == device native default) -------------------------
    sample_rate = _coerce_int(config.get('sample_rate', 0), 0)
    if sample_rate <= 0:
        sample_rate = int(round(float(info.get('default_samplerate', 44100) or 44100)))
    if sample_rate <= 0:
        sample_rate = 44100

    # --- Channels (clamped to the device max) -----------------------------
    channels = _coerce_int(config.get('channels', 1), 1)
    max_in = int(info.get('max_input_channels', 1) or 1)
    if max_in > 0:
        channels = max(1, min(channels, max_in))
    else:
        channels = max(1, channels)

    # --- Software input gain (% ; 100 == unity) ---------------------------
    gain_percent = _coerce_float(config.get('input_gain_percent', 100), 100)
    if gain_percent < 0:
        gain_percent = 0.0

    device_tag = str(device_index) if device_index >= 0 else "default"

    logging.info(
        f"🎙️ Recording {record_seconds:g}s from device "
        f"[{device_tag}] '{device_name}' @ {sample_rate} Hz, {channels}ch (int16), "
        f"gain {gain_percent:g}%..."
    )

    frames = int(round(sample_rate * record_seconds))
    # int16 PCM == 2 bytes/sample, directly writable by the stdlib wave module.
    # Capture via a callback InputStream (NOT sd.rec) so the console REC light is
    # lit from the FIRST real audio block -- the indicator edge tracks the actual
    # mic edge to within one ~20 ms block, not a log line.
    blocksize = max(1, int(round(sample_rate * 0.02)))
    indicator = MicRecIndicator(record_seconds)
    chunks: List = []
    collected = {"n": 0}
    done = threading.Event()

    def _on_audio(indata, n_frames, time_info, status):  # noqa: ARG001 (sd contract)
        if not indicator._active:
            indicator.on()                 # ON edge == first samples in hand
        block = np.array(indata, dtype='int16', copy=True)
        chunks.append(block)
        collected["n"] += n_frames
        try:
            # int16 peak -> 0..1 for the VU bar.
            indicator.level((float(np.max(np.abs(block))) / 32768.0) if block.size else 0.0)
        except Exception:
            pass
        if collected["n"] >= frames:
            done.set()
            raise sd.CallbackStop

    recording = None
    try:
        with sd.InputStream(
            samplerate=sample_rate,
            channels=channels,
            dtype='int16',
            device=device_arg,
            blocksize=blocksize,
            latency='low',
            callback=_on_audio,
        ):
            done.wait(timeout=record_seconds + 5.0)
        captured = collected["n"] / float(sample_rate) if sample_rate else 0.0
        indicator.off(captured)            # OFF edge == stream torn down
        if chunks:
            recording = np.concatenate(chunks, axis=0)[:frames]
    except Exception as stream_err:
        # Fall back to the simple blocking capture if the streaming path is
        # unsupported on this host/driver -- recording must still succeed.
        indicator.off(collected["n"] / float(sample_rate) if sample_rate else 0.0)
        logging.warning(f"⚠️ Live-stream capture unavailable ({stream_err}); using blocking capture.")
        recording = sd.rec(
            frames, samplerate=sample_rate, channels=channels,
            dtype='int16', device=device_arg,
        )
        sd.wait()  # block until the full record_seconds has elapsed

    if recording is None or len(recording) == 0:
        raise RuntimeError("Audio device opened but returned no samples.")

    # Apply software gain BEFORE writing (no-op at the default 100%).
    recording, clipped_samples = _apply_gain(recording, gain_percent)
    if clipped_samples > 0:
        total = int(getattr(recording, 'size', 0) or 0)
        logging.warning(
            f"⚠️ Gain {gain_percent:g}% clipped {clipped_samples}/{total} samples "
            f"to the int16 rail (signal too hot for this gain)."
        )

    filepath = build_unique_path(output_dir, device_tag, "wav")
    with wave.open(filepath, 'wb') as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(2)  # int16
        wf.setframerate(sample_rate)
        wf.writeframes(recording.tobytes())

    return {
        "output_path": os.path.abspath(filepath),
        "device_index": device_index,
        "device_name": device_name,
        "sample_rate": sample_rate,
        "channels": channels,
        "duration_seconds": record_seconds,
        "gain_percent": gain_percent,
        "clipped_samples": clipped_samples,
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
    (and the Multi-Turn LLM) can read the exact saved path verbatim instead of
    guessing at the auto-stamped filename. Keep this in ONE logging.info() call
    so concurrent writes can never interleave and corrupt the block.
    """
    saved_path = result["output_path"]
    device_index = result["device_index"]
    device_name = result["device_name"]
    sample_rate = result["sample_rate"]
    channels = result["channels"]
    duration = result["duration_seconds"]
    gain_percent = result.get("gain_percent", 100)
    clipped_samples = result.get("clipped_samples", 0)
    logging.info(
        "INI_SECTION_RECORDER<<<\n"
        f"output_path: {saved_path}\n"
        f"output_dir: {os.path.dirname(saved_path)}\n"
        f"filename: {os.path.basename(saved_path)}\n"
        f"device_index: {device_index}\n"
        f"device_name: {device_name}\n"
        f"sample_rate: {sample_rate}\n"
        f"channels: {channels}\n"
        f"duration_seconds: {duration:g}\n"
        f"gain_percent: {gain_percent:g}\n"
        f"clipped_samples: {clipped_samples}\n"
        f"format: wav\n"
        "\n"
        f"Audio recording saved to {saved_path}\n"
        ">>>END_SECTION_RECORDER"
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
        output_dir = resolve_output_dir(config)

        logging.info("🎙️ RECORDER AGENT STARTED")
        logging.info(f"📁 Output directory: {output_dir}")
        logging.info(f"🎯 Targets: {target_agents}")

        # Verify sounddevice is importable BEFORE touching the mic so the error
        # is unambiguous rather than a cryptic mid-capture traceback.
        try:
            import sounddevice  # noqa: F401
        except Exception as imp_err:
            logging.error(
                "❌ sounddevice is not available in this Python "
                f"({imp_err}). Recorder needs it to access the microphone. "
                "Install it with: python -m pip install sounddevice"
            )
            sys.exit(1)

        # Help the user pick a device: always print the input-device map.
        _log_input_devices()

        try:
            result = record_audio(config, output_dir)
            logging.info(f"✅ Audio saved: {result['output_path']}")
            logging.info(
                f"   Device: [{result['device_index']}] {result['device_name']} | "
                f"Rate: {result['sample_rate']} Hz | Channels: {result['channels']} | "
                f"Duration: {result['duration_seconds']:g}s"
            )
            emit_parametrizer_section(result)
        except Exception as e:
            logging.error(f"❌ Audio recording failed: {e}")
            sys.exit(1)

        # Trigger downstream agents
        total_triggered = 0
        if target_agents:
            wait_for_agents_to_stop(target_agents)
            logging.info(f"🚀 Triggering {len(target_agents)} downstream agents...")
            for target in target_agents:
                if start_agent(target):
                    total_triggered += 1

        logging.info(
            f"🏁 Recorder agent finished. "
            f"Triggered {total_triggered}/{len(target_agents)} agents."
        )

    finally:
        # Keep LED green briefly for visual feedback
        time.sleep(0.4)
        remove_pid_file()

    sys.exit(0)


if __name__ == "__main__":
    main()
