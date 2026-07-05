# ═══════════════════════════════════════════════════════════════════
#   ✦  T L A M A T I N I  ✦   —   "one who knows"
#
#   Created by  Angela López Mendoza   ·   @angelahack1
#   Developer · Architect · Creator of Tlamatini
#
#   Every line of this file was written by Angela López Mendoza.
# ═══════════════════════════════════════════════════════════════════
#   Tlamatini Author Banner — do not remove (releases scrub the name automatically)
# Video-Analyzer Agent - TRIPLE-MODEL video verdict via LLM vision models,
#                        gated by a deterministic OpenCV motion check.
# Non-deterministic agent (uses LLMs) — the "eye" of Robotic-Loop-Training.
# Action: Resolve a video path (direct / wildcard / dir-newest / Camcorder pool)
#         -> extract N timestamped frames with OpenCV (in memory)
#         -> DETERMINISTIC MOTION GATE (no LLM if nothing moved -> FAIL_NO_MOTION)
#         -> interpreter 1 + interpreter 2 judge the frames IN PARALLEL, each on
#            its OWN dedicated Ollama connection
#         -> BARRIER: wait for BOTH -> merging_model fuses them into one report
#            AND a final verdict (PASS_OK only if BOTH agree — no false PASS)
#         -> emit INI_SECTION_VIDEO_ANALYZER + a SUBSTRING-SAFE TLM_VERDICT:: line
#         -> ALWAYS start downstream agents (so a Forker can branch on the verdict)

import os
import sys

# FIX: Disable Intel Fortran runtime Ctrl+C handler
os.environ['FOR_DISABLE_CONSOLE_CTRL_HANDLER'] = '1'

import re
import glob
import json
import time
import yaml
import base64
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
import urllib.request
import urllib.error
from typing import Dict, List, Optional, Tuple

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

# Supported video extensions
VIDEO_EXTENSIONS = {
    '.mp4', '.mov', '.mkv', '.avi', '.webm', '.m4v', '.wmv', '.flv', '.mpg', '.mpeg',
}

# ── Substring-safe verdict token contract ─────────────────────────────
# The Forker matches a case-sensitive SUBSTRING in this agent's log. The token
# stems are chosen so that PASS_OK is NEVER a substring of any FAIL token — a
# downstream Forker uses pattern_a="TLM_VERDICT::PASS_OK" (-> success/Ender) and
# pattern_b="TLM_VERDICT::FAIL" (-> reprogram loop, matches both FAIL tokens).
# UNCLEAR / ANALYSIS_ERROR match neither, so a third route (Raiser/HALT) can
# catch "couldn't look" instead of mis-routing it as a firmware failure.
TLM_PREFIX = "TLM_VERDICT::"
VERDICT_PASS = "PASS_OK"
VERDICT_FAIL_NO_MOTION = "FAIL_NO_MOTION"
VERDICT_FAIL_WRONG_MOTION = "FAIL_WRONG_MOTION"
VERDICT_UNCLEAR = "UNCLEAR"
VERDICT_ANALYSIS_ERROR = "ANALYSIS_ERROR"
VALID_VERDICTS = {
    VERDICT_PASS, VERDICT_FAIL_NO_MOTION, VERDICT_FAIL_WRONG_MOTION,
    VERDICT_UNCLEAR, VERDICT_ANALYSIS_ERROR,
}

# ── Triple-model pipeline defaults ────────────────────────────────────
# The template config.yaml carries the FULL engineered prompts; these compact
# fallbacks only kick in when a stale pool config.yaml predates a field.
DEFAULT_INTERPRETER_MODEL_1 = "qwen3-vl:235b-cloud"
DEFAULT_INTERPRETER_MODEL_2 = "qwen3.5:cloud"
DEFAULT_MERGING_MODEL = "glm-5.2:cloud"
DEFAULT_EXPECTED_MOTION = (
    "The servo/actuator performs its programmed motion — it sweeps between its "
    "commanded positions and repeats the sequence continuously."
)
DEFAULT_PROMPT_INTERPRETER_1 = (
    'You are a video motion-verification engine. You are given chronological, '
    'timestamped frames from the video "{filename}". The system should do this: '
    '{expected_motion}. Track the moving part across the timestamps, rule out '
    'shadows/hands/camera-shake, and end with EXACTLY one line: '
    'FRAME_VERDICT: PASS_OK | FAIL_NO_MOTION | FAIL_WRONG_MOTION | UNCLEAR.'
)
DEFAULT_PROMPT_INTERPRETER_2 = (
    'You independently double-check a physical test from timestamped frames of '
    '"{filename}". Expected behavior: {expected_motion}. Decide whether the '
    'actuator performed it, be skeptical, and end with EXACTLY one line: '
    'FRAME_VERDICT: PASS_OK | FAIL_NO_MOTION | FAIL_WRONG_MOTION | UNCLEAR.'
)
DEFAULT_PROMPT_MERGING = (
    'You judge a video motion test of "{filename}" from TWO analyses. The test '
    'passes only if: {expected_motion}. Output PASS_OK ONLY IF both analyses '
    'independently agree it happened; disagreement/uncertainty -> UNCLEAR. End '
    'with exactly two lines: "FINAL_VERDICT: PASS_OK | FAIL_NO_MOTION | '
    'FAIL_WRONG_MOTION | UNCLEAR" then "CONFIDENCE: <0.00-1.00>".'
)
DEFAULT_PROMPT_USER = (
    'These are chronological frames from "{filename}". Did the hardware perform '
    'this motion: {expected_motion}? A false PASS is the worst outcome — only '
    'pass when the evidence is unambiguous.'
)


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
    system Python or a user-set ``PYTHON_HOME``. Only when the carried
    interpreter is absent (e.g. running from source) does this fall back to the
    registry / environment ``PYTHON_HOME``.
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
# ROBUST NUMERIC COERCION
# ========================================

def _coerce_int(value, default: int) -> int:
    """Extract a leading integer from a wrapped-parser value like '12 frames'."""
    try:
        return int(value)
    except (TypeError, ValueError):
        pass
    m = re.search(r'-?\d+', str(value or ''))
    return int(m.group(0)) if m else default


def _coerce_float(value, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        pass
    m = re.search(r'-?\d+(?:\.\d+)?', str(value or ''))
    return float(m.group(0)) if m else default


# ========================================
# VIDEO RESOLUTION + FRAME EXTRACTION
# ========================================

def _newest_video_in(paths: List[str]) -> Optional[str]:
    vids = [p for p in paths if os.path.isfile(p) and os.path.splitext(p)[1].lower() in VIDEO_EXTENSIONS]
    if not vids:
        return None
    return max(vids, key=lambda p: os.path.getmtime(p))


def _read_camcorder_output_path(pool_name: str) -> Optional[str]:
    """If ``pool_name`` is a Camcorder-style pool, read the most recent
    ``output_path`` from its log's last INI_SECTION_CAMCORDER block.
    """
    log_path = os.path.join(get_pool_path(), pool_name, f"{pool_name}.log")
    base = pool_name.rsplit('_', 1)[0]
    alt_log = os.path.join(get_pool_path(), pool_name, f"{base}.log")
    for candidate in (log_path, alt_log):
        if not os.path.exists(candidate):
            continue
        try:
            with open(candidate, 'r', encoding='utf-8', errors='ignore') as f:
                text = f.read()
        except Exception:
            continue
        matches = re.findall(r'output_path:\s*(.+)', text)
        for raw in reversed(matches):
            p = raw.strip()
            if p and os.path.isfile(p):
                return p
    return None


def resolve_video_path(video_pathfilenames: str) -> Optional[str]:
    """Resolve the config value to ONE concrete video file path.

    Supports a direct file, a wildcard (newest match), a directory (newest video
    inside), or a Camcorder pool name (reads its last recorded output_path).
    """
    if not video_pathfilenames:
        return None
    resolved = str(video_pathfilenames).strip().strip('"').strip("'")

    # A Camcorder (or any) pool name whose log carries an output_path
    pool_dir = os.path.join(get_pool_path(), resolved)
    if os.path.isdir(pool_dir) and os.path.exists(os.path.join(pool_dir, 'config.yaml')):
        cam_path = _read_camcorder_output_path(resolved)
        if cam_path:
            logging.info(f"🔗 Resolved pool '{resolved}' → recorded video: {cam_path}")
            return cam_path
        logging.warning(f"⚠️ Pool '{resolved}' has no recorded output_path yet.")
        return None

    # Direct file
    if os.path.isfile(resolved):
        if os.path.splitext(resolved)[1].lower() in VIDEO_EXTENSIONS:
            return resolved
        logging.warning(f"⚠️ '{resolved}' is not a recognized video format.")
        return None

    # Directory → newest video inside
    if os.path.isdir(resolved):
        candidates = [os.path.join(resolved, n) for n in os.listdir(resolved)]
        newest = _newest_video_in(candidates)
        if newest:
            logging.info(f"📁 Newest video in '{resolved}': {newest}")
        return newest

    # Wildcard → newest match
    if '*' in resolved or '?' in resolved:
        newest = _newest_video_in(glob.glob(resolved))
        if newest:
            logging.info(f"🔎 Newest video matching '{resolved}': {newest}")
        return newest

    logging.error(f"❌ Could not resolve video_pathfilenames: {resolved}")
    return None


def _parse_roi(roi: str, width: int, height: int) -> Optional[Tuple[int, int, int, int]]:
    """Parse an 'x,y,w,h' PERCENT ROI into a pixel box, clamped to the frame."""
    if not roi or not str(roi).strip():
        return None
    nums = re.findall(r'-?\d+(?:\.\d+)?', str(roi))
    if len(nums) < 4:
        return None
    x = max(0, min(width - 1, int(float(nums[0]) / 100.0 * width)))
    y = max(0, min(height - 1, int(float(nums[1]) / 100.0 * height)))
    w = max(1, min(width - x, int(float(nums[2]) / 100.0 * width)))
    h = max(1, min(height - y, int(float(nums[3]) / 100.0 * height)))
    return (x, y, w, h)


def extract_frames(video_path: str, num_frames: int) -> Tuple[List[Dict], float, int]:
    """Extract ``num_frames`` evenly-spaced frames from the video (in memory).

    Returns (frames, fps, total_frames), where each frame dict has
    ``index``, ``timestamp`` (seconds), ``b64`` (JPEG) and ``gray`` (numpy uint8
    grayscale, for the motion gate). Never raises for a missing frame; skips it.
    """
    import cv2  # local import so a missing OpenCV yields a clear message in main()

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        cap.release()
        raise RuntimeError(f"Could not open video: {video_path}")

    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    fps = float(cap.get(cv2.CAP_PROP_FPS) or 0.0)
    frames: List[Dict] = []

    def _grab(idx: int):
        cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
        ok, frame = cap.read()
        if not ok or frame is None:
            return None
        ts = (idx / fps) if fps and fps > 1.0 else float(idx)
        ok2, buf = cv2.imencode('.jpg', frame, [int(cv2.IMWRITE_JPEG_QUALITY), 85])
        if not ok2:
            return None
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        return {
            'index': int(idx),
            'timestamp': round(ts, 3),
            'b64': base64.b64encode(buf.tobytes()).decode('utf-8'),
            'gray': gray,
        }

    if total and total > 0:
        n = max(1, min(num_frames, total))
        if n == 1:
            indices = [total // 2]
        else:
            step = (total - 1) / float(n - 1)
            indices = [int(round(i * step)) for i in range(n)]
        for idx in indices:
            fr = _grab(idx)
            if fr is not None:
                frames.append(fr)
    else:
        # Unknown length: read sequentially and keep every k-th frame.
        collected = []
        idx = 0
        while True:
            ok, frame = cap.read()
            if not ok or frame is None:
                break
            collected.append((idx, frame))
            idx += 1
            if idx > 100000:
                break
        total = len(collected)
        if collected:
            n = max(1, min(num_frames, total))
            step = max(1, total // n)
            for i in range(0, total, step):
                fidx, frame = collected[i]
                ts = (fidx / fps) if fps and fps > 1.0 else float(fidx)
                ok2, buf = cv2.imencode('.jpg', frame, [int(cv2.IMWRITE_JPEG_QUALITY), 85])
                if not ok2:
                    continue
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                frames.append({
                    'index': int(fidx), 'timestamp': round(ts, 3),
                    'b64': base64.b64encode(buf.tobytes()).decode('utf-8'), 'gray': gray,
                })
                if len(frames) >= num_frames:
                    break
    cap.release()
    return frames, fps, total


def compute_motion_score(frames: List[Dict], roi: str) -> float:
    """Peak mean absolute inter-frame difference in the ROI, as a PERCENT of
    full-scale (0-100). A still scene ~= sensor noise (< ~1); a real servo sweep
    is several percent or more. Deterministic — no LLM, no hallucination.
    """
    import numpy as np

    grays = [f['gray'] for f in frames if f.get('gray') is not None]
    if len(grays) < 2:
        return 0.0
    h, w = grays[0].shape[:2]
    box = _parse_roi(roi, w, h)
    peak = 0.0
    for a, b in zip(grays[:-1], grays[1:]):
        if a.shape != b.shape:
            continue
        ga, gb = a, b
        if box is not None:
            x, y, bw, bh = box
            ga = a[y:y + bh, x:x + bw]
            gb = b[y:y + bh, x:x + bw]
        diff = np.abs(ga.astype(np.int16) - gb.astype(np.int16))
        pct = float(diff.mean()) / 255.0 * 100.0
        if pct > peak:
            peak = pct
    return round(peak, 3)


# ========================================
# LLM PIPELINE
# ========================================

def inject_tokens(text: str, filename: str, expected_motion: str, num_frames: int) -> str:
    """Substitute {filename} / {expected_motion} / {num_frames}; append clues when
    the placeholders are absent so the prompt always carries the context.
    """
    text = (text or '').strip()
    had = '{filename}' in text or '{expected_motion}' in text
    text = (text
            .replace('{filename}', filename)
            .replace('{expected_motion}', expected_motion)
            .replace('{num_frames}', str(num_frames)))
    if not had:
        text = (
            f"{text}\n\n"
            f"VIDEO FILE NAME: \"{filename}\". EXPECTED MOTION: {expected_motion}"
        )
    return text


def _sanitize_model_text(text: str) -> str:
    """Defang any literal ``TLM_VERDICT`` a model might echo, so ONLY the verdict
    line this agent emits itself can ever be matched by a downstream Forker.
    """
    return (text or '').replace('TLM_VERDICT', 'TLM-VERDICT')


def _call_ollama_chat(host: str, token: str, model: str, messages: list,
                      conn_label: str, timeout: int = 600,
                      temperature: float = 0.1) -> str:
    """POST one /api/chat request on its OWN, dedicated HTTP connection.

    ``urllib.request.urlopen`` opens a FRESH TCP connection per call, so two
    threads calling this concurrently really do talk to Ollama over TWO separate
    sockets — the effective-parallelism contract of the dual-interpreter pipeline.
    A single user message may carry MANY images (the whole frame sequence).
    """
    host = (host or 'http://localhost:11434').rstrip('/')
    payload = {
        "model": model,
        "messages": messages,
        "stream": True,
        "options": {
            "temperature": temperature,
            "num_ctx": 32768,
            "top_p": 0.95,
        },
    }
    headers = {'Content-Type': 'application/json'}
    if token:
        headers['Authorization'] = f'Bearer {token}'
    url = f"{host}/api/chat"
    logging.info(f"   [{conn_label}] Opening dedicated connection to {url} (model {model})...")
    req = urllib.request.Request(url, data=json.dumps(payload).encode('utf-8'),
                                 headers=headers, method='POST')
    chunks = []
    with urllib.request.urlopen(req, timeout=timeout) as response:
        for line in response:
            if not line:
                continue
            try:
                json_chunk = json.loads(line.decode('utf-8'))
            except json.JSONDecodeError:
                continue
            content = ""
            if "message" in json_chunk:
                content = json_chunk["message"].get("content", "")
            elif "response" in json_chunk:
                content = json_chunk.get("response", "")
            if content:
                chunks.append(content)
            if json_chunk.get("done", False):
                break
    return "".join(chunks).strip()


def _is_error_result(text: str) -> bool:
    return (not text) or text.startswith("Error")


def _frames_timeline(frames: List[Dict]) -> str:
    return ", ".join(f"frame {i + 1} @ {f['timestamp']}s" for i, f in enumerate(frames))


def analyze_frames_with_model(frames: List[Dict], host: str, token: str, model: str,
                              engineered_prompt: str, user_prompt: str,
                              filename: str, expected_motion: str,
                              conn_label: str) -> str:
    """Run ONE vision interpreter over the WHOLE frame sequence in a single
    /api/chat call (Ollama accepts multiple images per message). Never raises.
    """
    try:
        num_frames = len(frames)
        system_context = inject_tokens(engineered_prompt, filename, expected_motion, num_frames)
        timeline = _frames_timeline(frames)
        user_content = (
            inject_tokens(user_prompt, filename, expected_motion, num_frames)
            + f"\n\nThe {num_frames} attached images are the frames in chronological order: {timeline}."
        )
        images = [f['b64'] for f in frames]
        messages = [
            {"role": "system", "content": system_context},
            {"role": "user", "content": user_content, "images": images},
        ]
        return _call_ollama_chat(host, token, model, messages, conn_label)
    except urllib.error.URLError as e:
        return f"Error: Could not connect to LLM at {host} on {conn_label}. ({e})"
    except Exception as e:
        return f"Error analyzing frames with {model}: {e}"


def merge_interpretations(host: str, token: str, model: str, merge_prompt: str,
                          user_prompt: str, model_1: str, interp_1: str,
                          model_2: str, interp_2: str, filename: str,
                          expected_motion: str, num_frames: int) -> str:
    """The BARRIER is already past. Fuse both interpretations into one report +
    a final verdict. Text-only (the merger never sees the pixels). Never raises.
    """
    try:
        user_block = (
            f"USER REQUEST:\n{inject_tokens(user_prompt, filename, expected_motion, num_frames)}\n\n"
            f"=== ANALYSIS A (from {model_1}) ===\n{interp_1}\n\n"
            f"=== ANALYSIS B (from {model_2}) ===\n{interp_2}\n\n"
            f"Produce the definitive report and the final verdict now."
        )
        messages = [
            {"role": "system", "content": inject_tokens(merge_prompt, filename, expected_motion, num_frames)},
            {"role": "user", "content": user_block},
        ]
        return _call_ollama_chat(host, token, model, messages, 'CONNECTION-MERGE', temperature=0.2)
    except urllib.error.URLError as e:
        return f"Error: Could not connect to merging model at {host}. ({e})"
    except Exception as e:
        return f"Error merging interpretations with {model}: {e}"


def _extract_verdict(text: str, key: str) -> Optional[str]:
    """Pull a FRAME_VERDICT/FINAL_VERDICT token out of a model response."""
    if not text:
        return None
    m = re.search(rf'{key}\s*[:=]\s*([A-Z_]+)', text)
    if not m:
        return None
    tok = m.group(1).strip().upper()
    return tok if tok in VALID_VERDICTS else None


def _extract_confidence(text: str) -> float:
    if not text:
        return 0.5
    m = re.search(r'CONFIDENCE\s*[:=]\s*([01](?:\.\d+)?|\.\d+)', text)
    if not m:
        return 0.5
    try:
        return max(0.0, min(1.0, float(m.group(1))))
    except ValueError:
        return 0.5


def analyze_video_dual(frames: List[Dict], pipeline: dict) -> Tuple[str, str, float, str]:
    """The TRIPLE-MODEL video pipeline. Interpreter 1 and 2 judge the frames in
    PARALLEL (two dedicated connections), a BARRIER waits for both, then the
    merging model fuses them and rules.

    Returns ``(report, verdict, confidence, status)`` where verdict is one of the
    substring-safe token STEMS (e.g. PASS_OK) and status describes the pipeline
    outcome (analyzed / partial_* / merge_fallback_concat / error).
    """
    host = pipeline['host']
    token = pipeline['token']
    filename = pipeline['filename']
    expected_motion = pipeline['expected_motion']
    num_frames = len(frames)
    results = {}

    def _run(slot, model, engineered_prompt, conn_label):
        started = time.time()
        logging.info(f"🔀 [{conn_label}] Interpreter {slot} STARTED — model '{model}' over {num_frames} frames")
        results[slot] = analyze_frames_with_model(
            frames, host, token, model, engineered_prompt,
            pipeline['prompt_user'], filename, expected_motion, conn_label,
        )
        verdict = 'FAILED' if _is_error_result(results[slot]) else 'OK'
        logging.info(f"🔀 [{conn_label}] Interpreter {slot} FINISHED ({verdict}) in {time.time() - started:.1f}s")

    thread_1 = threading.Thread(target=_run, args=(1, pipeline['model_1'], pipeline['prompt_1'], 'CONNECTION-A'), daemon=True)
    thread_2 = threading.Thread(target=_run, args=(2, pipeline['model_2'], pipeline['prompt_2'], 'CONNECTION-B'), daemon=True)
    thread_1.start()
    thread_2.start()
    logging.info("🧱 BARRIER: waiting for BOTH interpretations to arrive...")
    thread_1.join()
    thread_2.join()
    logging.info("🧱 BARRIER RELEASED: both interpretations arrived — invoking the merging model.")

    interp_1 = results.get(1) or "Error: interpreter 1 produced no result"
    interp_2 = results.get(2) or "Error: interpreter 2 produced no result"
    ok_1 = not _is_error_result(interp_1)
    ok_2 = not _is_error_result(interp_2)

    if not ok_1 and not ok_2:
        logging.error("❌ BOTH interpreters failed — cannot judge the video.")
        report = (
            f"Error: both interpreters failed.\n"
            f"[{pipeline['model_1']}] {interp_1}\n[{pipeline['model_2']}] {interp_2}"
        )
        return report, VERDICT_ANALYSIS_ERROR, 0.0, "error"

    v1 = _extract_verdict(interp_1, 'FRAME_VERDICT') if ok_1 else None
    v2 = _extract_verdict(interp_2, 'FRAME_VERDICT') if ok_2 else None

    if ok_1 and ok_2:
        status = "analyzed"
    elif ok_1:
        status = "partial_interpreter_1_only"
        interp_2 = f"(Interpreter 2 '{pipeline['model_2']}' FAILED: {interp_2})"
        logging.warning("⚠️ Interpreter 2 failed — the merger must not PASS from one witness alone.")
    else:
        status = "partial_interpreter_2_only"
        interp_1 = f"(Interpreter 1 '{pipeline['model_1']}' FAILED: {interp_1})"
        logging.warning("⚠️ Interpreter 1 failed — the merger must not PASS from one witness alone.")

    merged = merge_interpretations(
        host, token, pipeline['merging_model'], pipeline['prompt_merge'],
        pipeline['prompt_user'], pipeline['model_1'], interp_1,
        pipeline['model_2'], interp_2, filename, expected_motion, num_frames,
    )

    if _is_error_result(merged):
        logging.warning(f"⚠️ Merging model failed ({merged}) — falling back to the raw interpretations.")
        merged_report = (
            f"[MERGE FALLBACK — the merging model failed: {merged}]\n\n"
            f"=== ANALYSIS A ({pipeline['model_1']}) ===\n{interp_1}\n\n"
            f"=== ANALYSIS B ({pipeline['model_2']}) ===\n{interp_2}"
        )
        final = _reconcile_without_merger(v1, v2)
        confidence = 0.3
        return merged_report, final, confidence, "merge_fallback_concat"

    final = _extract_verdict(merged, 'FINAL_VERDICT')
    confidence = _extract_confidence(merged)

    # SAFETY OVERRIDE (a false PASS is the worst outcome): only accept PASS_OK
    # when BOTH interpreters were healthy AND neither independently disagreed.
    if final == VERDICT_PASS:
        if status != "analyzed":
            logging.warning("⚠️ Downgrading PASS_OK -> UNCLEAR: only one interpreter succeeded.")
            final = VERDICT_UNCLEAR
        elif (v1 and v1 != VERDICT_PASS) or (v2 and v2 != VERDICT_PASS):
            logging.warning(f"⚠️ Downgrading PASS_OK -> UNCLEAR: interpreters disagreed (A={v1}, B={v2}).")
            final = VERDICT_UNCLEAR
    if final not in VALID_VERDICTS:
        final = _reconcile_without_merger(v1, v2)

    return merged, final, confidence, status


def _reconcile_without_merger(v1: Optional[str], v2: Optional[str]) -> str:
    """Fallback verdict when the merger didn't give a parseable one: PASS only on
    unanimous PASS; agree-on-a-fail wins; anything else is UNCLEAR.
    """
    if v1 == VERDICT_PASS and v2 == VERDICT_PASS:
        return VERDICT_PASS
    if v1 and v1 == v2:
        return v1
    for fail in (VERDICT_FAIL_NO_MOTION, VERDICT_FAIL_WRONG_MOTION):
        if v1 == fail or v2 == fail:
            return fail
    return VERDICT_UNCLEAR


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


def emit_verdict(video_path: str, verdict: str, confidence: float, status: str,
                 motion_score: float, frames_analyzed: int, pipeline: dict,
                 report: str):
    """Emit the atomic INI_SECTION_VIDEO_ANALYZER block AND, on a SEPARATE final
    line, the substring-safe ``TLM_VERDICT::<token>`` a Forker matches. The
    report body is sanitized so a model can never plant a rogue verdict line.
    """
    safe_report = _sanitize_model_text(report)
    logging.info(
        "INI_SECTION_VIDEO_ANALYZER<<<\n"
        f"video_path: {video_path}\n"
        f"verdict: {verdict}\n"
        f"verdict_token: {TLM_PREFIX}{verdict}\n"
        f"confidence: {confidence:.2f}\n"
        f"motion_score: {motion_score}\n"
        f"frames_analyzed: {frames_analyzed}\n"
        f"interpreter_model_1: {pipeline.get('model_1', '')}\n"
        f"interpreter_model_2: {pipeline.get('model_2', '')}\n"
        f"merging_model: {pipeline.get('merging_model', '')}\n"
        f"status: {status}\n"
        "\n"
        f"{safe_report}\n"
        ">>>END_SECTION_VIDEO_ANALYZER"
    )
    # Dedicated, substring-safe verdict line (emitted LAST so it is the final
    # verdict marker in the log for the Forker to match).
    logging.info(f"{TLM_PREFIX}{verdict}")


def main():
    config = load_config()
    write_pid_file()
    if _IS_REANIMATED:
        logging.info(f"🔄 {CURRENT_DIR_NAME} REANIMATED (resuming from pause)")
        logging.info("=" * 60)

    verdict = VERDICT_ANALYSIS_ERROR
    confidence = 0.0
    status = "error"
    motion_score = 0.0
    frames_analyzed = 0
    report = "Video-Analyzer did not complete."
    video_path = ""
    llm_config = config.get('llm', {}) or {}
    pipeline = {
        'host': str(llm_config.get('host') or 'http://localhost:11434'),
        'token': llm_config.get('token', ''),
        'model_1': str(config.get('interpreter_model_1') or '').strip() or DEFAULT_INTERPRETER_MODEL_1,
        'model_2': str(config.get('interpreter_model_2') or '').strip() or DEFAULT_INTERPRETER_MODEL_2,
        'merging_model': str(config.get('merging_model') or '').strip() or DEFAULT_MERGING_MODEL,
        'prompt_1': str(config.get('prompt_interpreter_model_1') or '').strip() or DEFAULT_PROMPT_INTERPRETER_1,
        'prompt_2': str(config.get('prompt_interpreter_model_2') or '').strip() or DEFAULT_PROMPT_INTERPRETER_2,
        'prompt_merge': str(config.get('prompt_merging_model') or '').strip() or DEFAULT_PROMPT_MERGING,
        'prompt_user': str(config.get('prompt_user') or '').strip() or DEFAULT_PROMPT_USER,
        'expected_motion': str(config.get('expected_motion') or '').strip() or DEFAULT_EXPECTED_MOTION,
        'filename': '',
    }

    try:
        target_agents = config.get('target_agents', []) or []
        video_pathfilenames = str(config.get('video_pathfilenames') or '').strip()
        num_frames = max(2, min(32, _coerce_int(config.get('num_frames', 12), 12)))
        motion_gate = bool(config.get('motion_gate', True))
        motion_threshold = _coerce_float(config.get('motion_threshold', 2.0), 2.0)
        roi = str(config.get('roi') or '').strip()

        logging.info("🎬 VIDEO-ANALYZER AGENT STARTED")
        logging.info(f"📼 video_pathfilenames: {video_pathfilenames}")
        logging.info(f"🎯 Expected motion: {pipeline['expected_motion']}")
        logging.info(
            f"🤖 Triple-model @ {pipeline['host']}: '{pipeline['model_1']}' + "
            f"'{pipeline['model_2']}' in PARALLEL -> BARRIER -> merger '{pipeline['merging_model']}'"
        )
        logging.info(f"🎯 Targets: {target_agents}")

        video_path = resolve_video_path(video_pathfilenames) or ""
        pipeline['filename'] = os.path.basename(video_path) if video_path else video_pathfilenames

        if not video_path:
            logging.error("❌ No video to analyze (path did not resolve to a video file).")
            verdict, status = VERDICT_ANALYSIS_ERROR, "error"
            report = f"No video resolved from '{video_pathfilenames}'."
        else:
            try:
                import cv2  # noqa: F401
            except ImportError:
                logging.error(
                    "❌ OpenCV (opencv-python) is not installed in this Python. "
                    "Video-Analyzer needs it to read frames. Install: python -m pip install opencv-python"
                )
                verdict, status = VERDICT_ANALYSIS_ERROR, "engine_unavailable"
                report = "OpenCV not available; cannot extract frames."
            else:
                logging.info(f"🎞️ Extracting up to {num_frames} frames from: {video_path}")
                frames, fps, total = extract_frames(video_path, num_frames)
                frames_analyzed = len(frames)
                logging.info(f"🎞️ Extracted {frames_analyzed} frame(s); fps≈{fps:.2f}; total_frames={total}")

                if frames_analyzed < 2:
                    logging.error("❌ Could not extract at least 2 frames — cannot judge motion.")
                    verdict, status = VERDICT_ANALYSIS_ERROR, "error"
                    report = f"Only {frames_analyzed} frame(s) extractable from {video_path}."
                else:
                    motion_score = compute_motion_score(frames, roi)
                    logging.info(f"📊 Deterministic motion score: {motion_score}% (threshold {motion_threshold}%)")

                    if motion_gate and motion_score < motion_threshold:
                        # Objective short-circuit: nothing moved. No LLM call.
                        logging.info("🛑 MOTION GATE: no motion detected — verdict FAIL_NO_MOTION (no LLM call).")
                        verdict, status = VERDICT_FAIL_NO_MOTION, "motion_gate_fail"
                        confidence = 0.9
                        report = (
                            f"Deterministic motion gate: peak inter-frame motion {motion_score}% is below the "
                            f"{motion_threshold}% threshold across {frames_analyzed} frames — the hardware did not "
                            f"move. Next attempt: check the PWM timer channel / signal wiring / servo power."
                        )
                    else:
                        report, verdict, confidence, status = analyze_video_dual(frames, pipeline)
                        logging.info(f"⚖️ Verdict: {verdict} (confidence {confidence:.2f}, status {status})")
    except Exception as e:
        logging.error(f"❌ Video-Analyzer failed: {e}")
        verdict, status, report = VERDICT_ANALYSIS_ERROR, "error", f"Unhandled error: {e}"

    # Emit the verdict + section (ALWAYS, even on error, so the flow can branch).
    try:
        emit_verdict(video_path, verdict, confidence, status, motion_score,
                     frames_analyzed, pipeline, report)
    except Exception as e:
        logging.error(f"❌ Failed to emit verdict section: {e}")

    # Trigger downstream agents (ALWAYS).
    try:
        target_agents = config.get('target_agents', []) or []
        total_triggered = 0
        if target_agents:
            wait_for_agents_to_stop(target_agents)
            logging.info(f"🚀 Triggering {len(target_agents)} downstream agents...")
            for target in target_agents:
                if start_agent(target):
                    total_triggered += 1
        logging.info(f"🏁 Video-Analyzer agent finished. Triggered {total_triggered}/{len(target_agents)} agents.")
    finally:
        time.sleep(0.4)
        remove_pid_file()

    sys.exit(0)


if __name__ == "__main__":
    main()
