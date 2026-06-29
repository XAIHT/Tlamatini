# ═══════════════════════════════════════════════════════════════════
#   ✦  T L A M A T I N I  ✦   —   "one who knows"
#
#   Created by  Angela López Mendoza   ·   @angelahack1
#   Developer · Architect · Creator of Tlamatini
#
#   Every line of this file was written by Angela López Mendoza.
# ═══════════════════════════════════════════════════════════════════
#   Tlamatini Author Banner — do not remove (releases scrub the name automatically)
# VideoPlayer Agent - Plays a video FILE (with audio) on a chosen DISPLAY.
# Action: Triggered by upstream -> Open a video file (ffpyplayer, falling back to
#         OpenCV) -> Resolve a target display (monitor) -> Open a cv2 window
#         (sized / fullscreened / placed on that display) -> Set the audio volume
#         -> Play for `time_played` seconds (truncating a long video or looping a
#         short one) -> Emit a Parametrizer-readable INI_SECTION_VIDEOPLAYER block
#         with the full path of the played file and the time played -> Trigger
#         downstream agents.
#
# The on-screen sibling of AudioPlayer: AudioPlayer drives the speakers,
# VideoPlayer drives a screen window (with sound). Observational/output (mutates
# no persistent state), so — like Shoter/Recorder/Camcorder/AudioPlayer — it is
# NOT in the Exec Report.
#
# Backend: ffpyplayer (pip wheel bundles ffmpeg + SDL -> audio + video + volume,
# no external ffmpeg / no runtime download) decodes + plays the audio; OpenCV
# (cv2, already bundled) draws the window. If ffpyplayer is unavailable the agent
# degrades to silent OpenCV-only video (volume becomes a no-op, logged).

import os
import sys

# FIX: Disable Intel Fortran runtime Ctrl+C handler
os.environ['FOR_DISABLE_CONSOLE_CTRL_HANDLER'] = '1'

import re
import time
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
from typing import Dict, List

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
# VIDEOPLAYER-SPECIFIC HELPERS
# ========================================

def _coerce_float(value, default: float) -> float:
    """Best-effort numeric coercion that NEVER raises (extracts a leading number)."""
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
    """Best-effort truthiness for YAML/string/Multi-Turn values; never raises."""
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    text = str(value).strip().lower()
    if text in ('true', '1', 'yes', 'on', 'y'):
        return True
    if text in ('false', '0', 'no', 'off', 'n', ''):
        return False
    return default


def resolve_video_file(config: Dict) -> str:
    """Resolve the configured video file path to an absolute path (no existence check)."""
    raw = str(config.get('video_file') or '').strip().strip('"').strip("'")
    if not raw:
        return ''
    expanded = os.path.expanduser(raw)
    if not os.path.isabs(expanded):
        expanded = os.path.join(script_dir, expanded)
    return os.path.abspath(expanded)


def enumerate_monitors() -> List[Dict]:
    """
    Enumerate the system monitors as a list of dicts:
        {index, left, top, width, height, primary}
    Uses the Win32 EnumDisplayMonitors API via ctypes. Fails open to a single
    primary monitor derived from GetSystemMetrics (or a 1920x1080 default) so a
    headless / non-Windows host never crashes the agent.
    """
    if os.name != 'nt':
        return [{'index': 0, 'left': 0, 'top': 0, 'width': 1920, 'height': 1080, 'primary': True}]
    try:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        MONITORINFOF_PRIMARY = 1

        class RECT(ctypes.Structure):
            _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long),
                        ("right", ctypes.c_long), ("bottom", ctypes.c_long)]

        class MONITORINFO(ctypes.Structure):
            _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", RECT),
                        ("rcWork", RECT), ("dwFlags", wintypes.DWORD)]

        monitors: List[Dict] = []
        MonitorEnumProc = ctypes.WINFUNCTYPE(
            ctypes.c_int, ctypes.c_void_p, ctypes.c_void_p,
            ctypes.POINTER(RECT), ctypes.c_double)

        def _cb(hmon, _hdc, _lprc, _lparam):
            mi = MONITORINFO()
            mi.cbSize = ctypes.sizeof(MONITORINFO)
            if user32.GetMonitorInfoW(hmon, ctypes.byref(mi)):
                r = mi.rcMonitor
                monitors.append({
                    'index': len(monitors),
                    'left': int(r.left), 'top': int(r.top),
                    'width': int(r.right - r.left), 'height': int(r.bottom - r.top),
                    'primary': bool(mi.dwFlags & MONITORINFOF_PRIMARY),
                })
            return 1

        user32.EnumDisplayMonitors(None, None, MonitorEnumProc(_cb), 0)
        if monitors:
            return monitors
    except Exception as e:
        logging.warning(f"⚠️ Monitor enumeration failed ({e}); falling back to a single display.")

    try:
        import ctypes
        w = int(ctypes.windll.user32.GetSystemMetrics(0)) or 1920
        h = int(ctypes.windll.user32.GetSystemMetrics(1)) or 1080
    except Exception:
        w, h = 1920, 1080
    return [{'index': 0, 'left': 0, 'top': 0, 'width': w, 'height': h, 'primary': True}]


def _log_monitors(monitors: List[Dict]):
    logging.info(f"🖥️ Available displays ({len(monitors)}):")
    for m in monitors:
        tag = " (PRIMARY)" if m.get('primary') else ""
        logging.info(
            f"     [{m['index']}] {m['width']}x{m['height']} @ "
            f"({m['left']},{m['top']}){tag}"
        )


def resolve_display(config: Dict, monitors: List[Dict]) -> Dict:
    """
    Pick the target monitor. display_index == -1 -> the primary monitor (or the
    first). A valid index selects that monitor; an out-of-range index falls back
    to the primary with a warning.
    """
    if not monitors:
        return {'index': 0, 'left': 0, 'top': 0, 'width': 1920, 'height': 1080, 'primary': True}

    requested = _coerce_int(config.get('display_index', -1), -1)
    if requested >= 0:
        if requested < len(monitors):
            return monitors[requested]
        logging.warning(
            f"⚠️ display_index {requested} out of range (have {len(monitors)} "
            f"display(s)); using the primary display."
        )

    for m in monitors:
        if m.get('primary'):
            return m
    return monitors[0]


def compute_window_geometry(config: Dict, video_w: int, video_h: int, monitor: Dict) -> Dict:
    """
    Pure geometry resolver (no cv2). Returns
        {fullscreen, win_w, win_h, pos_x, pos_y}
    The window is centered on the chosen monitor; window_width/height default to
    the video's native size (0) and are clamped to the monitor. In fullscreen the
    window fills the monitor.
    """
    mon_left = int(monitor.get('left', 0))
    mon_top = int(monitor.get('top', 0))
    mon_w = int(monitor.get('width', 1920)) or 1920
    mon_h = int(monitor.get('height', 1080)) or 1080

    fullscreen = _coerce_bool(config.get('fullscreen', False), False)
    if fullscreen:
        return {'fullscreen': True, 'win_w': mon_w, 'win_h': mon_h,
                'pos_x': mon_left, 'pos_y': mon_top}

    req_w = _coerce_int(config.get('window_width', 0), 0)
    req_h = _coerce_int(config.get('window_height', 0), 0)
    win_w = req_w if req_w > 0 else (video_w if video_w > 0 else mon_w)
    win_h = req_h if req_h > 0 else (video_h if video_h > 0 else mon_h)
    win_w = max(1, min(win_w, mon_w))
    win_h = max(1, min(win_h, mon_h))

    pos_x = mon_left + max(0, (mon_w - win_w) // 2)
    pos_y = mon_top + max(0, (mon_h - win_h) // 2)
    return {'fullscreen': False, 'win_w': win_w, 'win_h': win_h,
            'pos_x': pos_x, 'pos_y': pos_y}


def classify_play_mode(time_played: float, file_duration: float) -> str:
    """Deterministic play-mode label from the requested time vs the file length."""
    if time_played <= 0:
        return "full"
    if file_duration <= 0:
        return "looped" if time_played > 0 else "full"
    if time_played < file_duration - 1e-3:
        return "truncated"
    if time_played <= file_duration + 1e-3:
        return "full"
    return "looped"


# ---------------------------------------------------------------------------
# Decode backends — both expose: width, height, duration, has_audio, backend_name
#   next_frame() -> (kind, frame_bgr, delay)   kind in {'frame','eof','wait'}
#   seek_start(), close()
# ---------------------------------------------------------------------------


class _FfpyplayerBackend:
    """ffpyplayer decode + synchronized audio + volume; frames handed to cv2."""

    backend_name = "ffpyplayer"
    has_audio = True

    def __init__(self, path: str, volume_factor: float):
        import numpy as np  # noqa: F401  (imported for next_frame)
        from ffpyplayer.player import MediaPlayer

        self._np = np
        self.player = MediaPlayer(
            path, ff_opts={'out_fmt': 'rgb24', 'sync': 'audio', 'paused': False})
        try:
            self.player.set_volume(max(0.0, min(1.0, float(volume_factor))))
        except Exception as e:
            logging.warning(f"⚠️ Could not set volume on the player: {e}")

        # Resolve geometry + duration from metadata (poll briefly — it populates
        # a beat after the player starts).
        self.width = 0
        self.height = 0
        self.duration = 0.0
        for _ in range(40):
            md = self.player.get_metadata() or {}
            size = md.get('src_vid_size') or (0, 0)
            dur = md.get('duration')
            if size and size[0]:
                self.width, self.height = int(size[0]), int(size[1])
            if dur:
                self.duration = float(dur)
            if self.width and self.duration:
                break
            time.sleep(0.02)

    def next_frame(self):
        frame, val = self.player.get_frame()
        if frame is None:
            if val == 'eof':
                return ('eof', None, 0.0)
            return ('wait', None, 0.005)
        img, _pts = frame
        w, h = img.get_size()
        data = bytes(img.to_bytearray()[0])
        expected = w * h * 3
        np = self._np
        if h > 0 and len(data) % h == 0 and (len(data) // h) >= w * 3:
            stride = len(data) // h
            flat = np.frombuffer(data, dtype=np.uint8)
            rgb = flat.reshape(h, stride)[:, :w * 3].reshape(h, w, 3) if stride != w * 3 \
                else flat.reshape(h, w, 3)
        else:
            rgb = np.frombuffer(data[:expected], dtype=np.uint8).reshape(h, w, 3)
        bgr = np.ascontiguousarray(rgb[:, :, ::-1])
        if not self.width:
            self.height, self.width = bgr.shape[0], bgr.shape[1]
        return ('frame', bgr, float(val) if val else 0.0)

    def seek_start(self):
        try:
            self.player.seek(0, relative=False)
            self.player.set_pause(False)
        except Exception as e:
            logging.warning(f"⚠️ Loop seek failed: {e}")

    def close(self):
        try:
            self.player.close_player()
        except Exception:
            pass


class _OpenCvBackend:
    """OpenCV-only video decode (NO audio) — the graceful fallback."""

    backend_name = "opencv"
    has_audio = False

    def __init__(self, path: str):
        import cv2
        self._cv2 = cv2
        self.cap = cv2.VideoCapture(path)
        if not self.cap.isOpened():
            raise RuntimeError(f"OpenCV could not open the video file: {path}")
        self.width = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
        self.height = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
        fps = float(self.cap.get(cv2.CAP_PROP_FPS) or 0.0)
        self.fps = fps if fps > 0 else 25.0
        frame_count = float(self.cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0.0)
        self.duration = (frame_count / self.fps) if (frame_count > 0 and self.fps > 0) else 0.0
        self._delay = 1.0 / self.fps

    def next_frame(self):
        ret, frame = self.cap.read()
        if not ret or frame is None:
            return ('eof', None, 0.0)
        return ('frame', frame, self._delay)

    def seek_start(self):
        self.cap.set(self._cv2.CAP_PROP_POS_FRAMES, 0)

    def close(self):
        try:
            self.cap.release()
        except Exception:
            pass


def open_backend(path: str, volume_factor: float):
    """
    Prefer ffpyplayer (video + AUDIO + volume). Fall back to OpenCV-only (silent)
    if ffpyplayer is unavailable or fails to open the file.
    """
    try:
        import ffpyplayer.player  # noqa: F401
    except Exception as e:
        logging.warning(
            f"⚠️ ffpyplayer unavailable ({e}); playing SILENTLY via OpenCV "
            f"(volume_percent has no effect). Install ffpyplayer for audio."
        )
        return _OpenCvBackend(path)
    try:
        return _FfpyplayerBackend(path, volume_factor)
    except Exception as e:
        logging.warning(
            f"⚠️ ffpyplayer could not open the file ({e}); falling back to "
            f"silent OpenCV playback."
        )
        return _OpenCvBackend(path)


def drive_playback(backend, display, pump, time_played: float,
                   clock=time.monotonic, sleep=time.sleep) -> Dict:
    """
    The truncate / loop / full streaming driver (backend-agnostic, injectable
    clock + sleep + display + pump for testing).

      time_played <= 0 -> play the whole file ONCE.
      time_played  > 0 -> play for exactly that long: a longer file is cut
                          (truncated), a shorter one is looped (whole repeats +
                          a final partial segment).

    ``display(frame_bgr)`` shows a frame; ``pump()`` returns True when the user
    asked to stop (window closed / ESC). Returns run stats.
    """
    start = clock()
    loops_completed = 0
    frames_shown = 0
    frames_since_eof = 0
    partial = False
    stopped_by_user = False

    while True:
        if pump():
            stopped_by_user = True
            partial = frames_since_eof > 0
            break
        elapsed = clock() - start
        if time_played > 0 and elapsed >= time_played:
            partial = frames_since_eof > 0
            break

        kind, frame, delay = backend.next_frame()
        if kind == 'eof':
            loops_completed += 1
            frames_since_eof = 0
            if time_played <= 0:
                break                                  # whole file, once
            if (clock() - start) >= time_played:
                break
            backend.seek_start()                       # loop again
            continue
        if kind == 'wait':
            sleep(delay if delay > 0 else 0.005)
            continue

        display(frame)
        frames_shown += 1
        frames_since_eof += 1
        if delay > 0:
            sleep(delay)

    return {
        'loops_completed': loops_completed,
        'partial_segment': partial,
        'frames_shown': frames_shown,
        'played_seconds': round(clock() - start, 3),
        'stopped_by_user': stopped_by_user,
    }


def play_video(config: Dict) -> Dict:
    """Resolve everything, open the window, drive playback, return a result dict."""
    import cv2

    video_path = resolve_video_file(config)
    if not video_path:
        raise RuntimeError("No video_file configured — set video_file to the path of the file to play.")
    if not os.path.exists(video_path):
        raise RuntimeError(f"Video file not found: {video_path}")

    volume_percent = _coerce_float(config.get('volume_percent', 100), 100)
    if volume_percent < 0:
        volume_percent = 0.0
    volume_capped = volume_percent > 100
    if volume_capped:
        logging.warning(f"⚠️ volume_percent {volume_percent:g} capped at 100% (file's full level).")
    volume_factor = min(1.0, volume_percent / 100.0)

    backend = open_backend(video_path, volume_factor)
    try:
        video_w = int(getattr(backend, 'width', 0) or 0)
        video_h = int(getattr(backend, 'height', 0) or 0)
        file_duration = float(getattr(backend, 'duration', 0.0) or 0.0)

        monitors = enumerate_monitors()
        _log_monitors(monitors)
        monitor = resolve_display(config, monitors)
        geom = compute_window_geometry(config, video_w, video_h, monitor)

        keep_aspect = _coerce_bool(config.get('keep_aspect', True), True)
        time_played = _coerce_float(config.get('time_played', 0), 0)

        window_title = f"Tlamatini VideoPlayer — {os.path.basename(video_path)}"
        flags = cv2.WINDOW_NORMAL | (cv2.WINDOW_KEEPRATIO if keep_aspect else 0)
        cv2.namedWindow(window_title, flags)
        if geom['fullscreen']:
            cv2.moveWindow(window_title, geom['pos_x'], geom['pos_y'])
            cv2.waitKey(1)
            cv2.setWindowProperty(window_title, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)
        else:
            cv2.resizeWindow(window_title, geom['win_w'], geom['win_h'])
            cv2.moveWindow(window_title, geom['pos_x'], geom['pos_y'])

        win_desc = "fullscreen" if geom['fullscreen'] else f"window {geom['win_w']}x{geom['win_h']}"
        logging.info(
            f"🎬 Playing '{video_path}'\n"
            f"     backend={backend.backend_name} (audio={'yes' if backend.has_audio else 'NO'}) | "
            f"video {video_w}x{video_h}, {file_duration:g}s | "
            f"display [{monitor['index']}] {monitor['width']}x{monitor['height']}@"
            f"({monitor['left']},{monitor['top']}) | "
            f"{win_desc} | "
            f"volume {volume_percent:g}% | time_played={time_played:g}s | "
            f"mode={classify_play_mode(time_played, file_duration)}"
        )

        def _display(frame_bgr):
            cv2.imshow(window_title, frame_bgr)

        def _pump():
            key = cv2.waitKey(1) & 0xFF
            if key == 27:                              # ESC
                return True
            try:
                if cv2.getWindowProperty(window_title, cv2.WND_PROP_VISIBLE) < 1:
                    return True                        # window closed
            except cv2.error:
                return True
            return False

        stats = drive_playback(backend, _display, _pump, time_played)

        try:
            cv2.destroyWindow(window_title)
            cv2.waitKey(1)
        except Exception:
            pass
    finally:
        backend.close()

    play_mode = classify_play_mode(time_played, file_duration)
    return {
        "input_path": video_path,
        "display_index": int(monitor['index']),
        "display_geometry": f"{monitor['width']}x{monitor['height']}@({monitor['left']},{monitor['top']})",
        "video_width": video_w,
        "video_height": video_h,
        "window_width": geom['win_w'],
        "window_height": geom['win_h'],
        "fullscreen": geom['fullscreen'],
        "volume_percent": volume_percent,
        "backend": backend.backend_name,
        "has_audio": backend.has_audio,
        "file_duration_seconds": round(file_duration, 3),
        "time_played_requested": time_played,
        "played_seconds": stats['played_seconds'],
        "play_mode": play_mode,
        "loops": stats['loops_completed'],
        "partial_segment": stats['partial_segment'],
        "stopped_by_user": stats['stopped_by_user'],
        "format": os.path.splitext(video_path)[1].lstrip('.').lower() or "unknown",
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
    Emit a single, atomic Parametrizer-compatible block with the exact played
    path + time played. ONE logging.info() call so concurrent writes can never
    interleave and corrupt the block.
    """
    input_path = result["input_path"]
    logging.info(
        "INI_SECTION_VIDEOPLAYER<<<\n"
        f"input_path: {input_path}\n"
        f"input_dir: {os.path.dirname(input_path)}\n"
        f"filename: {os.path.basename(input_path)}\n"
        f"display_index: {result['display_index']}\n"
        f"display_geometry: {result['display_geometry']}\n"
        f"video_width: {result['video_width']}\n"
        f"video_height: {result['video_height']}\n"
        f"window_width: {result['window_width']}\n"
        f"window_height: {result['window_height']}\n"
        f"fullscreen: {str(result['fullscreen']).lower()}\n"
        f"volume_percent: {result['volume_percent']:g}\n"
        f"backend: {result['backend']}\n"
        f"has_audio: {str(result['has_audio']).lower()}\n"
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
        f"{result['video_width']}x{result['video_height']}, backend={result['backend']}, "
        f"audio={'yes' if result['has_audio'] else 'no'}, volume {result['volume_percent']:g}%).\n"
        ">>>END_SECTION_VIDEOPLAYER"
    )


def emit_parametrizer_error_section(input_path: str, error_message: str, time_played_requested: float):
    """Emit an INI_SECTION_VIDEOPLAYER block describing a FAILED playback (status: error)."""
    safe_path = input_path or "(unresolved)"
    one_line_error = " ".join(str(error_message).splitlines()).strip()
    logging.info(
        "INI_SECTION_VIDEOPLAYER<<<\n"
        f"input_path: {safe_path}\n"
        f"input_dir: {os.path.dirname(safe_path) if input_path else ''}\n"
        f"filename: {os.path.basename(safe_path) if input_path else ''}\n"
        f"display_index: -1\n"
        f"display_geometry: \n"
        f"video_width: 0\n"
        f"video_height: 0\n"
        f"window_width: 0\n"
        f"window_height: 0\n"
        f"fullscreen: false\n"
        f"volume_percent: 0\n"
        f"backend: none\n"
        f"has_audio: false\n"
        f"file_duration_seconds: 0\n"
        f"time_played_requested: {time_played_requested:g}\n"
        f"played_seconds: 0\n"
        f"play_mode: error\n"
        f"loops: 0\n"
        f"partial_segment: false\n"
        f"format: unknown\n"
        f"status: error\n"
        "\n"
        f"VideoPlayer FAILED for {safe_path}: {one_line_error}\n"
        ">>>END_SECTION_VIDEOPLAYER"
    )


def main():
    config = load_config()

    write_pid_file()
    if _IS_REANIMATED:
        logging.info(f"🔄 {CURRENT_DIR_NAME} REANIMATED (resuming from pause)")
        logging.info("=" * 60)

    try:
        target_agents = config.get('target_agents', []) or []
        time_played_requested = _coerce_float(config.get('time_played', 0), 0)

        logging.info("🎬 VIDEOPLAYER AGENT STARTED")
        logging.info(f"🎯 Targets: {target_agents}")

        # Verify OpenCV (the display layer; ALWAYS required) is importable BEFORE
        # touching a file so the error is unambiguous. ffpyplayer (audio) is
        # optional — open_backend() degrades to silent cv2 playback without it.
        try:
            import cv2  # noqa: F401
        except Exception as imp_err:
            logging.error(
                "❌ OpenCV (cv2) is not available in this Python "
                f"({imp_err}). VideoPlayer needs it to draw the video window. "
                "Install it with: python -m pip install opencv-python"
            )
            emit_parametrizer_error_section(
                resolve_video_file(config), str(imp_err), time_played_requested)
            sys.exit(1)

        playback_ok = True
        try:
            result = play_video(config)
            win_desc = ("fullscreen" if result['fullscreen']
                        else f"window {result['window_width']}x{result['window_height']}")
            logging.info(f"✅ Playback finished: {result['input_path']}")
            logging.info(
                f"   Display: [{result['display_index']}] {result['display_geometry']} | "
                f"{win_desc} | "
                f"backend={result['backend']} | Played: {result['played_seconds']:g}s "
                f"(mode={result['play_mode']}, loops={result['loops']})"
            )
            emit_parametrizer_section(result)
        except Exception as e:
            playback_ok = False
            logging.error(f"❌ Video playback failed: {e}")
            emit_parametrizer_error_section(
                resolve_video_file(config), str(e), time_played_requested)

        # Trigger downstream agents — ALWAYS, success or failure.
        total_triggered = 0
        if target_agents:
            wait_for_agents_to_stop(target_agents)
            logging.info(f"🚀 Triggering {len(target_agents)} downstream agents...")
            for target in target_agents:
                if start_agent(target):
                    total_triggered += 1

        logging.info(
            f"🏁 VideoPlayer agent finished ({'OK' if playback_ok else 'with errors'}). "
            f"Triggered {total_triggered}/{len(target_agents)} agents."
        )

    finally:
        time.sleep(0.4)
        remove_pid_file()

    sys.exit(0)


if __name__ == "__main__":
    main()
