# Whisperer Agent - Self-contained SPEECH-TO-TEXT (STT / voice recognition)
# Action: Triggered by upstream OR run from chat -> get audio (either RECORD it
#         straight from the microphone itself, OR read a given audio file) ->
#         run a neural speech-recognition model (faster-whisper locally by
#         default, with GPU auto-detected and an ALWAYS-PRESENT CPU fallback;
#         OR a cloud STT API) -> optionally clean the transcript with an Ollama
#         LLM -> save the transcript -> emit a Parametrizer-readable
#         INI_SECTION_WHISPERER block whose body IS the transcript text ->
#         trigger downstream agents.
#
# Speech-to-text sibling of Talker (text-to-speech). Whisperer is 100%
# SELF-SUFFICIENT for microphone input: it opens, configures (channels, sample
# rate, gain), and records the mic ENTIRELY ON ITS OWN -- it does NOT depend on
# the Recorder agent. Input = the mic (or a file). Output = a STRING of text.
#
# IMPORTANT: Ollama (local or cloud) CANNOT do speech-to-text -- it has no audio
# input. The actual transcription is therefore done by a real ASR engine
# (faster-whisper / cloud Whisper). Ollama is used here ONLY as an OPTIONAL
# post-processor that tidies the transcript (punctuation/casing). See config.

import os
import sys

# FIX: Disable Intel Fortran runtime Ctrl+C handler
os.environ['FOR_DISABLE_CONSOLE_CTRL_HANDLER'] = '1'

# Temp/Templates policy (2026-06-02): keep any scratch this agent writes inside
# <app>/Temp (inherited via TLAMATINI_TEMP), never C:\Temp / %TEMP% / a bare
# tempfile dir. Keep this an if-block (NOT a top-level def) so it sits above the
# imports without tripping ruff E402.
if (os.environ.get('TLAMATINI_TEMP') or '').strip():
    import tempfile as _tlt_tempfile
    _tlt_tempfile.tempdir = os.environ['TLAMATINI_TEMP'].strip()

import re
import json
import time
import threading
import wave
import yaml
import logging
import subprocess
import urllib.request

# -- conhost.exe orphan guard ------------------------------------------
# Default every Popen to CREATE_NO_WINDOW unless the caller explicitly asked for
# a console (CREATE_NEW_CONSOLE) or detached the child themselves -- prevents
# orphaned conhost.exe windows bearing the Tlamatini icon.
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

# Whisper's neural model expects 16 kHz mono audio. We always feed the engine at
# this rate so a raw mic buffer can be passed straight in with no resampling.
WHISPER_SAMPLE_RATE = 16000


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
    """Get the command to run a Python script (dev venv / frozen carried python)."""
    if not getattr(sys, 'frozen', False):
        return [sys.executable]

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
    system Python or a user-set ``PYTHON_HOME``.
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

    if sys.platform.startswith('win'):
        try:
            import ctypes
            if hasattr(ctypes.windll.kernel32, 'SetDllDirectoryW'):
                ctypes.windll.kernel32.SetDllDirectoryW(None)
        except Exception:
            pass

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
# WHISPERER-SPECIFIC HELPERS
# ========================================

def _coerce_float(value, default: float) -> float:
    """Best-effort numeric coercion that NEVER raises (extracts leading number)."""
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
    """Best-effort bool coercion that NEVER raises."""
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    s = str(value).strip().lower()
    if s in ('true', '1', 'yes', 'on', 'y'):
        return True
    if s in ('false', '0', 'no', 'off', 'n'):
        return False
    return default  # '' / unknown -> keep the documented default


def get_documents_dir() -> str:
    """Resolve the user's *Documents* known-folder as a real absolute path."""
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

            # FOLDERID_Documents = {FDD39AD0-238F-46AF-ADB4-6C85480369C7}
            folderid_documents = _GUID(
                0xFDD39AD0, 0x238F, 0x46AF,
                (ctypes.c_byte * 8)(0xAD, 0xB4, 0x6C, 0x85, 0x48, 0x03, 0x69, 0xC7),
            )
            path_ptr = ctypes.c_wchar_p()
            res = ctypes.windll.shell32.SHGetKnownFolderPath(
                ctypes.byref(folderid_documents), 0, None, ctypes.byref(path_ptr)
            )
            if res == 0 and path_ptr.value:
                resolved = path_ptr.value
                ctypes.windll.ole32.CoTaskMemFree(path_ptr)
                return resolved
        except Exception as e:
            logging.warning(f"⚠️ Could not resolve Documents known-folder via Win32 API: {e}")
    return os.path.join(os.path.expanduser('~'), 'Documents')


def resolve_output_dir(config: Dict) -> str:
    """Decide where to save the transcript. Default <Documents>/TlamatiniTranscripts."""
    configured = str(config.get('output_dir') or '').strip()
    if configured:
        if not os.path.isabs(configured):
            configured = os.path.join(script_dir, configured)
        return configured
    return os.path.join(get_documents_dir(), 'TlamatiniTranscripts')


def build_unique_path(output_dir: str, ext: str) -> str:
    """Build a collision-proof absolute transcript path under output_dir."""
    os.makedirs(output_dir, exist_ok=True)
    now = datetime.now()
    stamp = now.strftime("%Y%m%d_%H%M%S_") + f"{now.microsecond // 1000:03d}"
    base = f"whisperer_{stamp}"
    candidate = os.path.join(output_dir, f"{base}.{ext}")
    counter = 1
    while os.path.exists(candidate):
        candidate = os.path.join(output_dir, f"{base}_{counter}.{ext}")
        counter += 1
    return os.path.abspath(candidate)


# ---------------------------------------------------------------------------
# SELF-CONTAINED MICROPHONE CAPTURE (no dependency on the Recorder agent)
# ---------------------------------------------------------------------------

def _list_input_devices() -> List[Tuple[int, str, int, float]]:
    """Enumerate every input-capable device: (index, name, max_in_channels, default_rate)."""
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
    """Resolve which input device to record from -> (device_arg, index, name, info)."""
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

    Honesty contract: this is NOT a "we are about to record" log line. ``on()``
    is fired from the FIRST audio callback, so the light turns ON within one
    audio block (~20 ms at 16 kHz) of real samples actually arriving -- well
    inside the 50 ms budget. ``level(peak)`` is fed the true peak of every block
    so the VU bar literally dances with your voice (proof the mic is live).
    ``off()`` paints the stopped state SYNCHRONOUSLY the instant the stream is
    torn down, so the OFF edge tracks the audio edge too (~one block, not the
    animation tick). A daemon thread only blinks the dot between updates; every
    ON/OFF transition is painted inline so the visual edge never waits on it.

    Visibility contract: the pool launcher spawns Whisperer DETACHED with stdio
    to DEVNULL -- there is no console and stdout/stderr go nowhere. So ``on()``
    ACQUIRES a real console: it reuses an existing one or AllocConsole()s a fresh
    window, reveals + foregrounds it, sets its title, and paints to ``CONOUT$``
    DIRECTLY (bypassing the DEVNULL pipes). A console we allocated is freed on
    ``off()`` after a short linger so the user sees "STOPPED"; a pre-existing
    console (a foreground/visible run) is left untouched.

    Fail-safe: every method is wrapped so the indicator can NEVER raise into the
    capture path -- a broken light must not stop the recording.
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

    # -- console acquisition / release -----------------------------------
    def _acquire_console(self):
        """Ensure a VISIBLE console exists and route painting to CONOUT$."""
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
                k32.SetConsoleTitleW("\U0001f399  Tlamatini Whisperer  --  RECORDING")
            except Exception:
                pass
            # Paint straight to the console buffer (not the DEVNULL stdio).
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

    # -- public edges -----------------------------------------------------
    def on(self):
        try:
            with self._lock:
                if self._active:
                    return
                self._active = True
                self._t0 = time.perf_counter()
            self._acquire_console()                    # make a window appear
            self._paint(blink_on=True)                 # synchronous ON edge
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
            self._paint_stopped(captured_seconds)      # synchronous OFF edge
            if self._allocated:
                # Let the user actually SEE the stopped state before the window
                # we created closes (a pre-existing console is left as-is).
                time.sleep(self._LINGER_SECONDS)
            self._release_console()
        except Exception:
            pass

    # -- internals --------------------------------------------------------
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


def record_from_microphone(config: Dict):
    """
    Open, CONFIGURE and RECORD the microphone entirely on our own. Returns
    ``(audio_float32_mono_16k, meta)`` where the audio is a 1-D float32 numpy
    array at 16 kHz ready to hand straight to the recognizer, and ``meta`` carries
    the device + capture settings for the report.

    Whisperer is self-sufficient: it sets the channels, sample rate and software
    input gain, records ``record_seconds`` of audio, downmixes to mono, and
    resamples to the 16 kHz the neural model expects -- no Recorder agent needed.
    """
    import numpy as np
    import sounddevice as sd

    device_arg, device_index, device_name, info = resolve_input_device(config)

    record_seconds = _coerce_float(config.get('record_seconds', 30), 30)
    if record_seconds <= 0:
        record_seconds = 30.0

    # Capture rate: 0 == capture directly at the engine rate (16 kHz). A non-zero
    # value records at that rate and we resample to 16 kHz afterwards.
    capture_rate = _coerce_int(config.get('sample_rate', 0), 0)
    if capture_rate <= 0:
        capture_rate = WHISPER_SAMPLE_RATE
    if capture_rate <= 0:
        capture_rate = WHISPER_SAMPLE_RATE

    # Configure channels -- clamp to the device's reported maximum input channels
    # ("setting maximum input mic"): never request more than the mic provides.
    requested_channels = _coerce_int(config.get('channels', 1), 1)
    max_in = int(info.get('max_input_channels', 1) or 1)
    if max_in > 0:
        channels = max(1, min(requested_channels, max_in))
    else:
        channels = max(1, requested_channels)

    gain_percent = _coerce_float(config.get('input_gain_percent', 100), 100)
    if gain_percent < 0:
        gain_percent = 0.0

    device_tag = str(device_index) if device_index >= 0 else "default"
    logging.info(
        f"🎙️ Opening mic [{device_tag}] '{device_name}': recording {record_seconds:g}s "
        f"@ {capture_rate} Hz, {channels}ch (max_in={max_in}), gain {gain_percent:g}%..."
    )

    frames = int(round(capture_rate * record_seconds))

    # Capture via a callback InputStream (NOT sd.rec) so the console REC light
    # can be lit from the FIRST real audio block -- the indicator edge then
    # tracks the actual mic edge to within one block (~20 ms), not a log line.
    # ~20 ms blocks keep both the first-callback latency and the VU refresh snappy.
    blocksize = max(1, int(round(capture_rate * 0.02)))
    indicator = MicRecIndicator(record_seconds)
    chunks: List = []
    collected = {"n": 0}
    done = threading.Event()

    def _on_audio(indata, n_frames, time_info, status):  # noqa: ARG001 (sd contract)
        if not indicator._active:
            indicator.on()                 # ON edge == first samples in hand
        block = np.array(indata, dtype=np.float32, copy=True)
        chunks.append(block)
        collected["n"] += n_frames
        try:
            indicator.level(float(np.max(np.abs(block))) if block.size else 0.0)
        except Exception:
            pass
        if collected["n"] >= frames:
            done.set()
            raise sd.CallbackStop

    recording = None
    try:
        with sd.InputStream(
            samplerate=capture_rate,
            channels=channels,
            dtype='float32',
            device=device_arg,
            blocksize=blocksize,
            latency='low',
            callback=_on_audio,
        ):
            done.wait(timeout=record_seconds + 5.0)
        captured = collected["n"] / float(capture_rate) if capture_rate else 0.0
        indicator.off(captured)            # OFF edge == stream torn down
        if chunks:
            recording = np.concatenate(chunks, axis=0)[:frames]
    except Exception as stream_err:
        # Fall back to the simple blocking capture if the streaming path is
        # unsupported on this host/driver -- recording must still succeed
        # (the live light just won't be available in that degraded mode).
        indicator.off(collected["n"] / float(capture_rate) if capture_rate else 0.0)
        logging.warning(f"⚠️ Live-stream capture unavailable ({stream_err}); using blocking capture.")
        recording = sd.rec(
            frames, samplerate=capture_rate, channels=channels,
            dtype='float32', device=device_arg,
        )
        sd.wait()

    if recording is None or len(recording) == 0:
        raise RuntimeError("Microphone opened but returned no samples.")

    # Downmix to mono (Whisper needs mono).
    audio = np.asarray(recording, dtype=np.float32)
    if audio.ndim > 1 and audio.shape[1] > 1:
        audio = audio.mean(axis=1)
    else:
        audio = audio.reshape(-1)

    # Software input gain (no-op at 100%).
    if abs((gain_percent / 100.0) - 1.0) > 1e-9:
        audio = np.clip(audio * (gain_percent / 100.0), -1.0, 1.0).astype(np.float32)

    # Resample to 16 kHz if we captured at another rate (linear interpolation --
    # adequate for speech recognition; avoids a scipy dependency).
    if capture_rate != WHISPER_SAMPLE_RATE:
        audio = _resample_linear(audio, capture_rate, WHISPER_SAMPLE_RATE)

    meta = {
        "device_index": device_index,
        "device_name": device_name,
        "capture_sample_rate": capture_rate,
        "channels": channels,
        "gain_percent": gain_percent,
        "duration_seconds": record_seconds,
    }
    return audio.astype(np.float32), meta


def _resample_linear(audio, src_rate: int, dst_rate: int):
    """Cheap linear resample of a 1-D float32 array (no scipy needed)."""
    import numpy as np
    if src_rate == dst_rate or len(audio) == 0:
        return audio.astype(np.float32)
    duration = len(audio) / float(src_rate)
    dst_len = int(round(duration * dst_rate))
    if dst_len <= 0:
        return np.zeros(0, dtype=np.float32)
    src_idx = np.linspace(0, len(audio) - 1, num=dst_len)
    resampled = np.interp(src_idx, np.arange(len(audio)), audio)
    return resampled.astype(np.float32)


def save_capture_wav(audio, output_dir: str):
    """Persist the captured 16 kHz mono audio as a WAV (so the source is reusable)."""
    import numpy as np
    pcm16 = np.clip(np.round(np.asarray(audio, dtype=np.float32) * 32767.0), -32768, 32767).astype(np.int16)
    path = build_unique_path(output_dir, "wav")
    with wave.open(path, 'wb') as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(WHISPER_SAMPLE_RATE)
        wf.writeframes(pcm16.tobytes())
    return path


# ---------------------------------------------------------------------------
# TRANSCRIPTION ENGINES
# ---------------------------------------------------------------------------

def detect_cuda() -> bool:
    """
    Detect a usable CUDA GPU WITHOUT importing torch (faster-whisper uses
    CTranslate2, not torch). Returns True only if CTranslate2 reports >=1 CUDA
    device. Any failure -> False (fall back to CPU). This is the GPU auto-detect
    that decides the local engine's device.
    """
    try:
        import ctranslate2
        return int(ctranslate2.get_cuda_device_count()) > 0
    except Exception:
        return False


def resolve_local_device(config: Dict) -> Tuple[str, str]:
    """
    Resolve (device, compute_type) for faster-whisper.

    device: 'auto' -> 'cuda' if a GPU is detected else 'cpu'. 'cuda'/'cpu' force.
    compute_type: 'auto' -> 'float16' on cuda, 'int8' on cpu (8 GB-friendly).
    """
    requested = str(config.get('device', 'auto') or 'auto').strip().lower()
    if requested == 'cuda':
        device = 'cuda'
    elif requested == 'cpu':
        device = 'cpu'
    else:
        device = 'cuda' if detect_cuda() else 'cpu'

    compute = str(config.get('compute_type', 'auto') or 'auto').strip().lower()
    if compute in ('', 'auto'):
        compute = 'float16' if device == 'cuda' else 'int8'
    return device, compute


def transcribe_faster_whisper(audio, config: Dict) -> Dict:
    """
    Transcribe with faster-whisper. Tries the resolved device (GPU when present),
    and on ANY GPU failure (driver/cuDNN/VRAM) AUTOMATICALLY falls back to CPU so
    a machine without a working GPU ALWAYS gets a transcript.
    """
    from faster_whisper import WhisperModel

    model_name = str(config.get('model', 'base') or 'base').strip()
    language = str(config.get('language', '') or '').strip() or None
    task = str(config.get('task', 'transcribe') or 'transcribe').strip().lower()
    if task not in ('transcribe', 'translate'):
        task = 'transcribe'
    beam_size = _coerce_int(config.get('beam_size', 5), 5)
    vad_filter = _coerce_bool(config.get('vad_filter', True), True)
    word_timestamps = _coerce_bool(config.get('word_timestamps', False), False)

    device, compute_type = resolve_local_device(config)

    def _run(dev: str, comp: str) -> Dict:
        logging.info(f"🧠 Loading faster-whisper '{model_name}' on {dev} ({comp})...")
        model = WhisperModel(model_name, device=dev, compute_type=comp)
        segments, info = model.transcribe(
            audio,
            language=language,
            task=task,
            beam_size=beam_size,
            vad_filter=vad_filter,
            word_timestamps=word_timestamps,
        )
        seg_list = list(segments)  # generator -> materialise (runs the decode)
        text = "".join(s.text for s in seg_list).strip()
        return {
            "text": text,
            "language": getattr(info, 'language', language) or (language or ''),
            "segments": len(seg_list),
            "engine": "faster-whisper",
            "model": model_name,
            "device": dev,
            "compute_type": comp,
            "task": task,
        }

    try:
        return _run(device, compute_type)
    except Exception as gpu_err:
        if device == 'cuda':
            logging.warning(
                f"⚠️ GPU transcription failed ({gpu_err}); falling back to CPU (int8). "
                f"This always works on a machine without a usable GPU."
            )
            return _run('cpu', 'int8')
        raise


def transcribe_cloud(audio_path: str, config: Dict) -> Dict:
    """
    Transcribe via a cloud OpenAI-compatible Whisper endpoint (Groq / OpenAI).
    Sends the saved WAV as multipart/form-data. Key comes from config or the
    matching environment variable. stdlib-only (urllib) -- no requests/openai dep.
    """
    engine = str(config.get('engine', '') or '').strip().lower()
    if engine == 'cloud-groq':
        base_url = str(config.get('cloud_base_url') or 'https://api.groq.com/openai/v1').strip()
        default_model = 'whisper-large-v3'
        key = str(config.get('cloud_api_key') or '').strip() or os.environ.get('GROQ_API_KEY', '')
    else:  # cloud-openai
        base_url = str(config.get('cloud_base_url') or 'https://api.openai.com/v1').strip()
        default_model = 'whisper-1'
        key = str(config.get('cloud_api_key') or '').strip() or os.environ.get('OPENAI_API_KEY', '')

    if not key:
        raise RuntimeError(
            f"{engine} needs an API key. Set cloud_api_key in config.yaml or the "
            f"{'GROQ_API_KEY' if engine == 'cloud-groq' else 'OPENAI_API_KEY'} environment variable."
        )

    model_name = str(config.get('cloud_model') or default_model).strip()
    language = str(config.get('language', '') or '').strip()
    task = str(config.get('task', 'transcribe') or 'transcribe').strip().lower()
    endpoint = base_url.rstrip('/') + ('/audio/translations' if task == 'translate' else '/audio/transcriptions')

    with open(audio_path, 'rb') as f:
        wav_bytes = f.read()

    boundary = '----TlamatiniWhisperer' + datetime.now().strftime('%H%M%S%f')
    parts = []
    parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="model"\r\n\r\n{model_name}\r\n')
    if language and task != 'translate':
        parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="language"\r\n\r\n{language}\r\n')
    parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="response_format"\r\n\r\njson\r\n')
    pre = ''.join(parts).encode('utf-8')
    file_header = (
        f'--{boundary}\r\nContent-Disposition: form-data; name="file"; '
        f'filename="audio.wav"\r\nContent-Type: audio/wav\r\n\r\n'
    ).encode('utf-8')
    closing = f'\r\n--{boundary}--\r\n'.encode('utf-8')
    body = pre + file_header + wav_bytes + closing

    req = urllib.request.Request(endpoint, data=body, method='POST')
    req.add_header('Authorization', f'Bearer {key}')
    req.add_header('Content-Type', f'multipart/form-data; boundary={boundary}')
    timeout = _coerce_int(config.get('request_timeout', 300), 300)

    logging.info(f"☁️ Sending audio to {engine} ({model_name}) at {endpoint}...")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        payload = json.loads(resp.read().decode('utf-8'))
    text = str(payload.get('text', '')).strip()
    return {
        "text": text,
        "language": str(payload.get('language', language) or language or ''),
        "segments": len(payload.get('segments', []) or []),
        "engine": engine,
        "model": model_name,
        "device": "cloud",
        "compute_type": "cloud",
        "task": task,
    }


def cleanup_with_ollama(text: str, config: Dict) -> str:
    """
    OPTIONAL: tidy the transcript (punctuation/casing/obvious errors) with an
    Ollama LLM. Ollama CANNOT transcribe -- this only post-processes text that
    the ASR engine already produced. Returns the cleaned text, or the original on
    any failure (never breaks the run).
    """
    if not _coerce_bool(config.get('ollama_cleanup', False), False):
        return text
    if not text.strip():
        return text
    try:
        base_url = str(config.get('ollama_url') or 'http://localhost:11434').strip().rstrip('/')
        token = str(config.get('ollama_token') or '').strip()
        model_name = str(config.get('cleanup_model') or 'llama3.2').strip()
        instruction = str(config.get('cleanup_instruction') or
                          'Add proper punctuation and capitalization and fix obvious '
                          'transcription errors. Do NOT add, remove, summarize or '
                          'translate any content. Return ONLY the corrected text.').strip()
        prompt = f"{instruction}\n\nTRANSCRIPT:\n{text}"
        body = json.dumps({
            "model": model_name,
            "prompt": prompt,
            "stream": False,
        }).encode('utf-8')
        req = urllib.request.Request(base_url + '/api/generate', data=body, method='POST')
        req.add_header('Content-Type', 'application/json')
        if token:
            req.add_header('Authorization', f'Bearer {token}')
        timeout = _coerce_int(config.get('request_timeout', 300), 300)
        logging.info(f"🪄 Cleaning transcript with Ollama model '{model_name}'...")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            payload = json.loads(resp.read().decode('utf-8'))
        cleaned = str(payload.get('response', '')).strip()
        return cleaned or text
    except Exception as e:
        logging.warning(f"⚠️ Ollama cleanup failed ({e}); keeping the raw transcript.")
        return text


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


def save_transcript(text: str, output_dir: str) -> str:
    """Save the transcript string to a .txt file; return the path."""
    path = build_unique_path(output_dir, "txt")
    with open(path, 'w', encoding='utf-8') as f:
        f.write(text)
    return path


def emit_parametrizer_section(result: Dict):
    """
    Emit a single, atomic Parametrizer-compatible block. The BODY is the
    transcript text itself (response_body), so a downstream agent / the LLM reads
    the recognized speech verbatim. Keep this in ONE logging.info() call.
    """
    logging.info(
        "INI_SECTION_WHISPERER<<<\n"
        f"transcript_path: {result.get('transcript_path', '')}\n"
        f"audio_path: {result.get('audio_path', '')}\n"
        f"input_source: {result.get('input_source', '')}\n"
        f"engine: {result.get('engine', '')}\n"
        f"model: {result.get('model', '')}\n"
        f"device: {result.get('device', '')}\n"
        f"language: {result.get('language', '')}\n"
        f"duration_seconds: {result.get('duration_seconds', 0):g}\n"
        f"segments: {result.get('segments', 0)}\n"
        f"word_count: {result.get('word_count', 0)}\n"
        f"status: {result.get('status', '')}\n"
        "\n"
        f"{result.get('text', '')}\n"
        ">>>END_SECTION_WHISPERER"
    )


def run_whisperer(config: Dict, output_dir: str) -> Dict:
    """
    Full STT pipeline: get audio (mic or file) -> transcribe (local GPU/CPU or
    cloud) -> optional Ollama cleanup -> save -> return the result dict whose
    'text' is the recognized speech STRING.
    """
    import numpy as np  # noqa: F401  (ensures numpy present for capture/resample)

    audio_file = str(config.get('audio_file') or '').strip()
    explicit_source = str(config.get('input_source', '') or '').strip().lower()
    # Auto: a given audio_file means "file"; otherwise record the mic.
    use_file = explicit_source == 'file' or (explicit_source != 'mic' and bool(audio_file))

    engine = str(config.get('engine', 'faster-whisper') or 'faster-whisper').strip().lower()
    save_source = _coerce_bool(config.get('save_source_audio', True), True)

    result: Dict = {
        "text": "",
        "transcript_path": "",
        "audio_path": "",
        "input_source": "file" if use_file else "mic",
        "engine": engine,
        "model": "",
        "device": "",
        "language": "",
        "duration_seconds": 0.0,
        "segments": 0,
        "word_count": 0,
        "status": "error",
    }

    # --- 1. Acquire audio --------------------------------------------------
    audio_array = None
    if use_file:
        if not audio_file or not os.path.exists(audio_file):
            raise RuntimeError(f"audio_file not found: {audio_file!r}")
        result["audio_path"] = os.path.abspath(audio_file)
        logging.info(f"📄 Transcribing audio FILE: {result['audio_path']}")
    else:
        audio_array, meta = record_from_microphone(config)
        result["device"] = str(meta.get("device_index"))
        result["duration_seconds"] = float(meta.get("duration_seconds", 0) or 0)
        if save_source:
            try:
                result["audio_path"] = save_capture_wav(audio_array, output_dir)
                logging.info(f"💾 Saved captured audio: {result['audio_path']}")
            except Exception as e:
                logging.warning(f"⚠️ Could not save captured audio: {e}")

    # --- 2. Transcribe -----------------------------------------------------
    if engine in ('cloud-groq', 'cloud-openai'):
        # Cloud needs a file on disk; if we recorded, we just saved one above.
        cloud_path = result["audio_path"]
        if not cloud_path:
            cloud_path = save_capture_wav(audio_array, output_dir)
            result["audio_path"] = cloud_path
        tr = transcribe_cloud(cloud_path, config)
    else:
        # Local faster-whisper (default). Feed the file path or the raw array.
        try:
            import faster_whisper  # noqa: F401
        except Exception:
            # Graceful degradation: if a cloud key exists, use cloud; else report.
            if (str(config.get('cloud_api_key') or '').strip()
                    or os.environ.get('GROQ_API_KEY') or os.environ.get('OPENAI_API_KEY')):
                logging.warning("⚠️ faster-whisper not installed; using cloud STT instead.")
                config = dict(config)
                config['engine'] = 'cloud-groq' if (os.environ.get('GROQ_API_KEY')
                                                    or str(config.get('cloud_api_key') or '').strip()) else 'cloud-openai'
                cloud_path = result["audio_path"] or save_capture_wav(audio_array, output_dir)
                result["audio_path"] = cloud_path
                tr = transcribe_cloud(cloud_path, config)
                result["engine"] = config['engine']
                tr["engine"] = config['engine']
            else:
                result["status"] = "engine_unavailable"
                logging.error(
                    "❌ faster-whisper is not installed and no cloud STT key is set. "
                    "Install the local engine with:  python -m pip install faster-whisper  "
                    "(or set engine: cloud-groq + a GROQ_API_KEY)."
                )
                return result
        else:
            transcribe_input = result["audio_path"] if use_file else audio_array
            tr = transcribe_faster_whisper(transcribe_input, config)

    # --- 3. Merge engine result -------------------------------------------
    result["text"] = tr.get("text", "")
    result["language"] = tr.get("language", "")
    result["segments"] = tr.get("segments", 0)
    result["engine"] = tr.get("engine", result["engine"])
    result["model"] = tr.get("model", "")
    result["device"] = tr.get("device", result["device"])

    # --- 4. Optional Ollama cleanup ---------------------------------------
    result["text"] = cleanup_with_ollama(result["text"], config)
    result["word_count"] = len(result["text"].split())

    # --- 5. Save transcript -----------------------------------------------
    if _coerce_bool(config.get('save_transcript', True), True):
        try:
            result["transcript_path"] = save_transcript(result["text"], output_dir)
        except Exception as e:
            logging.warning(f"⚠️ Could not save transcript file: {e}")

    result["status"] = "transcribed" if result["text"] else "empty"
    return result


def main():
    config = load_config()

    write_pid_file()
    if _IS_REANIMATED:
        logging.info(f"🔄 {CURRENT_DIR_NAME} REANIMATED (resuming from pause)")
        logging.info("=" * 60)

    try:
        target_agents = config.get('target_agents', []) or []
        output_dir = resolve_output_dir(config)

        logging.info("🗣️ WHISPERER AGENT STARTED")
        logging.info(f"📁 Output directory: {output_dir}")
        logging.info(f"🎯 Targets: {target_agents}")

        # If we will use the mic, verify sounddevice up front and print the
        # device map (Whisperer opens the mic itself -- fully self-sufficient).
        audio_file = str(config.get('audio_file') or '').strip()
        explicit_source = str(config.get('input_source', '') or '').strip().lower()
        will_use_mic = not (explicit_source == 'file' or (explicit_source != 'mic' and bool(audio_file)))
        if will_use_mic:
            try:
                import sounddevice  # noqa: F401
            except Exception as imp_err:
                logging.error(
                    f"❌ sounddevice is not available ({imp_err}). Whisperer needs it to "
                    "open the microphone. Install:  python -m pip install sounddevice"
                )
                sys.exit(1)
            _log_input_devices()

        result = {"status": "error", "text": ""}
        try:
            result = run_whisperer(config, output_dir)
            logging.info(f"✅ STT status: {result.get('status')}  ({result.get('engine')})")
            preview = (result.get("text", "") or "")[:280]
            logging.info(f"📝 Transcript ({result.get('word_count', 0)} words): {preview}")
            if result.get("transcript_path"):
                logging.info(f"💾 Transcript saved: {result['transcript_path']}")
            emit_parametrizer_section(result)
        except Exception as e:
            logging.error(f"❌ Transcription failed: {e}")
            result = {
                "status": "error", "text": "", "engine": str(config.get('engine', '')),
                "input_source": "file" if not will_use_mic else "mic",
            }
            emit_parametrizer_section(result)

        # Trigger downstream agents (ALWAYS -- even on error, so a Forker can
        # branch on {status}).
        total_triggered = 0
        if target_agents:
            wait_for_agents_to_stop(target_agents)
            logging.info(f"🚀 Triggering {len(target_agents)} downstream agents...")
            for target in target_agents:
                if start_agent(target):
                    total_triggered += 1

        logging.info(
            f"🏁 Whisperer agent finished. "
            f"Triggered {total_triggered}/{len(target_agents)} agents."
        )

    finally:
        time.sleep(0.4)
        remove_pid_file()

    sys.exit(0)


if __name__ == "__main__":
    main()
