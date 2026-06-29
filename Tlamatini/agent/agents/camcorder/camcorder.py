# Camcorder Agent - Camera capture agent (photo or video) via OpenCV
# Action: Triggered by upstream -> Open a system camera -> Take ONE photo
#         (default) or record a video segment -> Save to the user's Pictures
#         folder under TlamatiniCamcorder with a collision-proof name ->
#         Emit a Parametrizer-readable INI_SECTION_CAMCORDER block with the
#         full path -> Trigger downstream agents.

import os
import sys

# FIX: Disable Intel Fortran runtime Ctrl+C handler
os.environ['FOR_DISABLE_CONSOLE_CTRL_HANDLER'] = '1'

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
from datetime import datetime
from typing import Dict, Optional, Tuple

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
# CAMCORDER-SPECIFIC HELPERS
# ========================================

def _default_temp_output_dir() -> str:
    """Resolve the DEFAULT save location: ``<where-Tlamatini-lives>/Temp`` —
    robust across frozen / source / installed builds.

    Temp/Templates policy (<REDACTED>, 2026-06-09): every asset this agent writes is
    a TEMPORARY asset and must live under ``<app>/Temp``, never the user's
    Pictures folder. Order: (1) the ``TLAMATINI_TEMP`` env var the Django process
    pins to ``<app>/Temp`` and every pool agent inherits; (2) walk up from this
    script to the Tlamatini app dir (the one holding ``manage.py``) and use its
    ``Temp``; (3) the executable's directory ``Temp`` when frozen; (4) a final
    fallback under the user's home so a save is always possible. Never raises.
    """
    env = (os.environ.get('TLAMATINI_TEMP') or '').strip().strip('"').strip("'")
    if env:
        return env

    if getattr(sys, 'frozen', False):
        return os.path.join(os.path.dirname(sys.executable), 'Temp')

    probe = script_dir
    for _ in range(10):
        if os.path.exists(os.path.join(probe, 'manage.py')):
            return os.path.join(probe, 'Temp')
        parent = os.path.dirname(probe)
        if parent == probe:
            break
        probe = parent

    return os.path.join(os.path.expanduser("~"), "Tlamatini", "Temp")


def resolve_output_dir(config: Dict) -> str:
    """
    Decide where to save the captured media.

    - If config.output_dir is set, honor it (resolved relative to the agent
      directory when not absolute).
    - Otherwise default to ``<app>/Temp`` (TEMPORARY asset, per <REDACTED> 2026-06-09).
    """
    configured = str(config.get('output_dir') or '').strip()
    if configured:
        if not os.path.isabs(configured):
            configured = os.path.join(script_dir, configured)
        return configured
    return os.path.abspath(_default_temp_output_dir())


def build_unique_path(output_dir: str, media_type: str, camera_index: int, ext: str) -> str:
    """
    Build a collision-proof absolute file path under output_dir.

    Name shape:  camcorder_<media>_<YYYYmmdd>_<HHMMSS>_<ms>_cam<idx>.<ext>
    The millisecond stamp + camera index makes overwrites practically
    impossible; a defensive counter suffix guarantees uniqueness even on the
    astronomically unlikely same-millisecond collision.
    """
    os.makedirs(output_dir, exist_ok=True)
    now = datetime.now()
    stamp = now.strftime("%Y%m%d_%H%M%S_") + f"{now.microsecond // 1000:03d}"
    base = f"camcorder_{media_type}_{stamp}_cam{camera_index}"
    candidate = os.path.join(output_dir, f"{base}.{ext}")
    counter = 1
    while os.path.exists(candidate):
        candidate = os.path.join(output_dir, f"{base}_{counter}.{ext}")
        counter += 1
    return os.path.abspath(candidate)


def open_camera(camera_index: int, req_width: int, req_height: int, warmup_seconds: float):
    """
    Open the requested camera and (optionally) request a resolution.

    Returns (cap, applied_width, applied_height). Raises RuntimeError if the
    camera cannot be opened. The caller MUST release the returned capture.
    """
    import cv2  # local import so a missing OpenCV yields a clear message in main()

    # CAP_DSHOW opens far faster and more reliably than the default MSMF
    # backend on Windows; use the default backend elsewhere.
    if os.name == 'nt':
        cap = cv2.VideoCapture(camera_index, cv2.CAP_DSHOW)
    else:
        cap = cv2.VideoCapture(camera_index)

    if not cap.isOpened():
        cap.release()
        raise RuntimeError(
            f"Camera index {camera_index} could not be opened. "
            f"Check that a camera is connected, not in use by another app, "
            f"and that camera_index is valid (0 = default)."
        )

    if req_width > 0 and req_height > 0:
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, req_width)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, req_height)

    # Warm up: cheap webcams return dark/garbage first frames while they
    # auto-expose. Read frames for warmup_seconds so the capture is usable.
    warmup_seconds = max(0.0, float(warmup_seconds or 0.0))
    warm_deadline = time.time() + warmup_seconds
    while time.time() < warm_deadline:
        cap.read()

    applied_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
    applied_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
    return cap, applied_width, applied_height


def capture_photo(config: Dict, output_dir: str) -> Tuple[str, str]:
    """
    Take ONE photo and save it. Returns (absolute_path, "WxH" resolution).
    """
    import cv2

    camera_index = int(config.get('camera_index', 0) or 0)
    req_width = int(config.get('resolution_width', 0) or 0)
    req_height = int(config.get('resolution_height', 0) or 0)
    warmup_seconds = float(config.get('warmup_seconds', 1.0) or 0.0)

    cap, applied_w, applied_h = open_camera(camera_index, req_width, req_height, warmup_seconds)
    try:
        ok, frame = cap.read()
        if not ok or frame is None:
            raise RuntimeError("Camera opened but returned no frame (read failed).")

        filepath = build_unique_path(output_dir, "photo", camera_index, "jpg")
        if not cv2.imwrite(filepath, frame):
            raise RuntimeError(f"cv2.imwrite failed to write {filepath}")
        resolution = f"{applied_w}x{applied_h}"
        return filepath, resolution
    finally:
        cap.release()


def capture_video(config: Dict, output_dir: str) -> Tuple[str, str, float, int]:
    """
    Record a video segment. Returns (absolute_path, "WxH", fps, duration_s).
    """
    import cv2

    camera_index = int(config.get('camera_index', 0) or 0)
    req_width = int(config.get('resolution_width', 0) or 0)
    req_height = int(config.get('resolution_height', 0) or 0)
    warmup_seconds = float(config.get('warmup_seconds', 1.0) or 0.0)
    duration_seconds = float(config.get('video_duration_seconds', 10) or 0)
    if duration_seconds <= 0:
        duration_seconds = 10.0
    requested_fps = float(config.get('video_fps', 20.0) or 0.0)

    cap, applied_w, applied_h = open_camera(camera_index, req_width, req_height, warmup_seconds)
    writer = None
    try:
        if applied_w <= 0 or applied_h <= 0:
            raise RuntimeError("Camera reported an invalid frame size; cannot record video.")

        # Use the camera's reported FPS when it gives a sane one, else the
        # configured request, else a safe default.
        cam_fps = float(cap.get(cv2.CAP_PROP_FPS) or 0.0)
        fps = cam_fps if cam_fps and cam_fps > 1.0 else (requested_fps if requested_fps > 1.0 else 20.0)

        filepath = build_unique_path(output_dir, "video", camera_index, "mp4")
        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        writer = cv2.VideoWriter(filepath, fourcc, fps, (applied_w, applied_h))
        if not writer.isOpened():
            raise RuntimeError(
                f"cv2.VideoWriter could not open {filepath} (codec/container unsupported)."
            )

        frames_written = 0
        deadline = time.time() + duration_seconds
        while time.time() < deadline:
            ok, frame = cap.read()
            if not ok or frame is None:
                logging.warning("⚠️ Frame read failed during recording; stopping early.")
                break
            writer.write(frame)
            frames_written += 1

        if frames_written == 0:
            raise RuntimeError("No frames were captured during recording.")

        resolution = f"{applied_w}x{applied_h}"
        return os.path.abspath(filepath), resolution, fps, int(round(duration_seconds))
    finally:
        if writer is not None:
            writer.release()
        cap.release()


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


def emit_parametrizer_section(
    saved_path: str,
    media_type: str,
    camera_index: int,
    resolution: str,
    duration_seconds: int,
    fps: Optional[float],
):
    """
    Emit a single, atomic Parametrizer-compatible block so downstream agents
    (and the Multi-Turn LLM) can read the exact saved path verbatim instead of
    guessing at the auto-stamped filename. Keep this in ONE logging.info() call
    so concurrent writes can never interleave and corrupt the block.
    """
    fps_line = f"fps: {fps:.3f}\n" if fps else "fps: \n"
    logging.info(
        "INI_SECTION_CAMCORDER<<<\n"
        f"output_path: {saved_path}\n"
        f"output_dir: {os.path.dirname(saved_path)}\n"
        f"filename: {os.path.basename(saved_path)}\n"
        f"media_type: {media_type}\n"
        f"camera_index: {camera_index}\n"
        f"duration_seconds: {duration_seconds}\n"
        f"resolution: {resolution}\n"
        f"{fps_line}"
        "\n"
        f"{media_type.capitalize()} saved to {saved_path}\n"
        ">>>END_SECTION_CAMCORDER"
    )


def main():
    config = load_config()

    # Write PID file immediately
    write_pid_file()
    if _IS_REANIMATED:
        logging.info(f"🔄 {CURRENT_DIR_NAME} REANIMATED (resuming from pause)")
        logging.info("=" * 60)

    try:
        camera_index = int(config.get('camera_index', 0) or 0)
        capture_mode = str(config.get('capture_mode', 'photo') or 'photo').strip().lower()
        if capture_mode not in ('photo', 'video'):
            logging.warning(f"⚠️ Unknown capture_mode '{capture_mode}', defaulting to 'photo'.")
            capture_mode = 'photo'
        target_agents = config.get('target_agents', []) or []
        output_dir = resolve_output_dir(config)

        logging.info("📸 CAMCORDER AGENT STARTED")
        logging.info(f"🎥 Mode: {capture_mode} | Camera index: {camera_index}")
        logging.info(f"📁 Output directory: {output_dir}")
        logging.info(f"🎯 Targets: {target_agents}")

        # Verify OpenCV is importable BEFORE touching the camera so the error
        # is unambiguous rather than a cryptic mid-capture traceback.
        try:
            import cv2  # noqa: F401
        except ImportError:
            logging.error(
                "❌ OpenCV (opencv-python) is not installed in this Python. "
                "Camcorder needs it to access the camera. Install it with: "
                "python -m pip install opencv-python"
            )
            sys.exit(1)

        try:
            if capture_mode == 'video':
                saved_path, resolution, fps, duration = capture_video(config, output_dir)
                logging.info(f"✅ Video saved: {saved_path}")
                logging.info(f"   Resolution: {resolution} | FPS: {fps:.3f} | Duration: ~{duration}s")
                emit_parametrizer_section(
                    saved_path, "video", camera_index, resolution, duration, fps
                )
            else:
                saved_path, resolution = capture_photo(config, output_dir)
                logging.info(f"✅ Photo saved: {saved_path}")
                logging.info(f"   Resolution: {resolution}")
                emit_parametrizer_section(
                    saved_path, "photo", camera_index, resolution, 0, None
                )
        except Exception as e:
            logging.error(f"❌ Camera capture failed: {e}")
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
            f"🏁 Camcorder agent finished. "
            f"Triggered {total_triggered}/{len(target_agents)} agents."
        )

    finally:
        # Keep LED green briefly for visual feedback
        time.sleep(0.4)
        remove_pid_file()

    sys.exit(0)


if __name__ == "__main__":
    main()
