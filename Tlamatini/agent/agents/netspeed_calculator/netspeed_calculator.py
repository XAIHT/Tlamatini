# ═══════════════════════════════════════════════════════════════════
#   ✦  T L A M A T I N I  ✦   —   "one who knows"
#
#   Created by  Angela López Mendoza   ·   @angelahack1
#   Developer · Architect · Creator of Tlamatini
#
#   Every line of this file was written by Angela López Mendoza.
# ═══════════════════════════════════════════════════════════════════
#   Tlamatini Author Banner — do not remove (releases scrub the name automatically)
#
# NetSpeed-Calculator Agent — formal, multi-provider Internet throughput measurement.
#
# Action: Triggered by upstream -> characterize the path (RTT / jitter / loss) -> run a
#         multi-stream, slow-start-excluded, derivative-sampled throughput test against
#         SEVERAL independent KEYLESS public speed-test endpoints -> reject outliers
#         robustly -> fuse the per-provider estimates by inverse-variance / random-effects
#         meta-analysis -> emit INI_SECTION_NETSPEED_CALCULATOR -> and ONLY THEN trigger
#         downstream agents.  The COMPLETE calculation always finishes first.
#
# WHY IT IS NOT A TOY.  Naive speed tests are wrong in four reproducible ways, and this
# agent fixes all four:
#   (1) They measure total_bytes/elapsed, which includes the TCP slow-start ramp and
#       therefore systematically UNDER-reports.  RFC 6349 §3 requires the ramp be
#       excluded; we discard `warmup_seconds` and measure only the steady state.
#   (2) They use ONE connection.  A single loss-based flow is bounded by the Mathis
#       equation BW <= MSS/(RTT*sqrt(p)) and by Window/RTT, so on any high
#       bandwidth-delay-product path one stream cannot fill the link.  We aggregate
#       `parallel_streams` flows and report the measured BDP so the operator can see it.
#   (3) They take an arithmetic mean of noisy slices, so one TCP stall or one CDN burst
#       moves the answer.  We apply Tukey IQR fences (k=1.5) or the Iglewicz-Hoaglin
#       modified z-score (MAD, 3.5) and then a symmetric trimmed mean, and we quote a
#       Student-t interval (n is small; the normal z is simply the wrong quantile).
#   (4) They average providers as if all providers were equally precise.  They are not.
#       We pool by INVERSE-VARIANCE weighting - the maximum-likelihood estimator for
#       independent normal estimates - report Cochran's Q and I^2, and switch to
#       DerSimonian-Laird RANDOM-EFFECTS when the providers genuinely disagree.
#
# NO API KEYS, NO LOGINS, NO ACCOUNTS.  Every endpoint is public.  The network and
# measurement stack is standard-library-only; PyYAML is used only to read config.yaml.
# The agent runs identically in source/frozen builds and never imports agent.*.

import os
import sys

# FIX: Disable Intel Fortran runtime Ctrl+C handler
os.environ['FOR_DISABLE_CONSOLE_CTRL_HANDLER'] = '1'

# ── Tlamatini Temp policy: temporary files ONLY under <app>/Temp ─────────
# Honor TLAMATINI_TEMP (exported by the Tlamatini core, inherited by every spawned agent
# via get_agent_env's os.environ.copy()) so every file this agent writes — the JSON
# result and the human report — lands under <app>/Temp, never C:\Temp / %TEMP% / the OS
# default. Fail-open when the handle is unset.
if (os.environ.get('TLAMATINI_TEMP') or '').strip():
    try:
        import tempfile as _tlt_tempfile
        _tlt_temp_root = os.environ['TLAMATINI_TEMP'].strip()
        os.makedirs(_tlt_temp_root, exist_ok=True)
        _tlt_tempfile.tempdir = _tlt_temp_root
        os.environ['TEMP'] = _tlt_temp_root
        os.environ['TMP'] = _tlt_temp_root
    except Exception:
        pass

import re
import ssl
import json
import math
import time
import yaml
import socket
import logging
import threading
import subprocess
import http.client
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime

# -- conhost.exe orphan guard ------------------------------------------
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

# Set working directory to script location
try:
    script_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(script_dir)
except Exception as e:
    sys.stderr.write(f"Critical Error: Failed to set working directory: {e}\n")

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
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
console_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
logging.getLogger().addHandler(console_handler)


# ========================================
# HELPER FUNCTIONS (copied verbatim from nmapper.py / discoverer.py boilerplate)
# ========================================

def load_config(path: str = "config.yaml") -> dict:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)
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
        return os.environ.get('PYTHON_HOME', '')
    except Exception:
        return os.environ.get('PYTHON_HOME', '')


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


PID_FILE = "agent.pid"


def write_pid_file():
    try:
        with open(PID_FILE, "w") as f:
            f.write(str(os.getpid()))
    except Exception as e:
        logging.error(f"❌ Failed to write PID file: {e}")


def remove_pid_file():
    for _attempt in range(5):
        try:
            if os.path.exists(PID_FILE):
                os.remove(PID_FILE)
            return
        except PermissionError:
            time.sleep(0.1)
        except Exception as e:
            logging.error(f"❌ Failed to remove PID file: {e}")
            return


# ========================================
# CONFIG VALUE COERCION (wrapped Multi-Turn passes everything as strings)
# ========================================

def _cfg(config: dict, key: str, default=""):
    val = config.get(key, default)
    return default if val is None else val


def _as_int(raw, default: int) -> int:
    """Extract the leading integer from anything the wrapped parser hands us.
    'parallel_streams=6 concurrent flows' -> 6.  Never raises."""
    try:
        if isinstance(raw, bool):
            return default
        m = re.search(r"-?\d+", str(raw))
        return int(m.group(0)) if m else default
    except (TypeError, ValueError):
        return default


def _as_float(raw, default: float) -> float:
    """Same contract as _as_int for real-valued knobs ('0.25 s' -> 0.25)."""
    try:
        if isinstance(raw, bool):
            return default
        m = re.search(r"-?\d+(?:\.\d+)?", str(raw))
        return float(m.group(0)) if m else default
    except (TypeError, ValueError):
        return default


def _as_bool(raw, default: bool) -> bool:
    if isinstance(raw, bool):
        return raw
    if raw is None:
        return default
    s = str(raw).strip().lower()
    if s in ("true", "1", "yes", "on"):
        return True
    if s in ("false", "0", "no", "off", ""):
        return False
    return default


# ========================================
# STATISTICS — the part that makes this a measurement, not a guess.
#
# Everything here is pure stdlib maths: numpy/scipy are NOT dependencies of the agent
# pool, and adding one would change the packaging contract for a handful of formulas.
# ========================================

#: Two-sided Student-t critical values.  Used INSTEAD of the normal z because a 10 s
#: test at 0.25 s cadence yields ~32 slices and, after trimming, often n < 30 — where
#: the normal quantile is simply the wrong number and understates the interval.
_T_TABLE_95 = {
    1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571, 6: 2.447, 7: 2.365,
    8: 2.306, 9: 2.262, 10: 2.228, 11: 2.201, 12: 2.179, 13: 2.160, 14: 2.145,
    15: 2.131, 16: 2.120, 17: 2.110, 18: 2.101, 19: 2.093, 20: 2.086, 21: 2.080,
    22: 2.074, 23: 2.069, 24: 2.064, 25: 2.060, 26: 2.056, 27: 2.052, 28: 2.048,
    29: 2.045, 30: 2.042,
}
_T_TABLE_99 = {
    1: 63.657, 2: 9.925, 3: 5.841, 4: 4.604, 5: 4.032, 6: 3.707, 7: 3.499,
    8: 3.355, 9: 3.250, 10: 3.169, 11: 3.106, 12: 3.055, 13: 3.012, 14: 2.977,
    15: 2.947, 16: 2.921, 17: 2.898, 18: 2.878, 19: 2.861, 20: 2.845, 21: 2.831,
    22: 2.819, 23: 2.807, 24: 2.797, 25: 2.787, 26: 2.779, 27: 2.771, 28: 2.763,
    29: 2.756, 30: 2.750,
}
_T_TABLE_90 = {
    1: 6.314, 2: 2.920, 3: 2.353, 4: 2.132, 5: 2.015, 6: 1.943, 7: 1.895,
    8: 1.860, 9: 1.833, 10: 1.812, 11: 1.796, 12: 1.782, 13: 1.771, 14: 1.761,
    15: 1.753, 16: 1.746, 17: 1.740, 18: 1.734, 19: 1.729, 20: 1.725, 21: 1.721,
    22: 1.717, 23: 1.714, 24: 1.711, 25: 1.708, 26: 1.706, 27: 1.703, 28: 1.701,
    29: 1.699, 30: 1.697,
}

#: Iglewicz & Hoaglin (1993) constant: E[MAD] = 0.6745*sigma for a normal sample.
_MAD_SCALE = 0.6745
#: Ratio of the mean-absolute-deviation to sigma for a normal sample (sqrt(pi/2)),
#: used as the documented fallback when the MAD is exactly zero (>50% ties).
_MEANAD_SCALE = 1.2533141


def _t_critical(df: int, conf: float = 0.95) -> float:
    """Two-sided Student-t critical value; falls back to the normal quantile for df>30."""
    if df < 1:
        return 0.0
    if conf >= 0.99:
        table, z = _T_TABLE_99, 2.576
    elif conf >= 0.95:
        table, z = _T_TABLE_95, 1.960
    else:
        table, z = _T_TABLE_90, 1.645
    return table.get(df, z)


def _z_critical(conf: float = 0.95) -> float:
    """Normal quantile — correct for the POOLED meta-analytic interval, where the
    weights are treated as known (the standard fixed-effect / DL convention)."""
    if conf >= 0.99:
        return 2.576
    if conf >= 0.95:
        return 1.960
    return 1.645


def _mean(values) -> float:
    values = list(values)
    return (sum(values) / float(len(values))) if values else 0.0


def _quantile(values, q: float) -> float:
    """Type-7 quantile (the R / numpy default): linear interpolation between order
    statistics.  Chosen deliberately so the IQR fences match what any reviewer would
    reproduce in R or numpy."""
    s = sorted(values)
    n = len(s)
    if n == 0:
        return 0.0
    if n == 1:
        return float(s[0])
    h = (n - 1) * max(0.0, min(1.0, q))
    lo = int(math.floor(h))
    hi = min(lo + 1, n - 1)
    return float(s[lo] + (h - lo) * (s[hi] - s[lo]))


def _median(values) -> float:
    return _quantile(values, 0.5)


def _stdev(values) -> float:
    """Sample standard deviation (Bessel-corrected, n-1) — we are estimating the
    population sigma from a sample, so dividing by n would be biased low."""
    v = list(values)
    n = len(v)
    if n < 2:
        return 0.0
    m = _mean(v)
    return math.sqrt(sum((x - m) ** 2 for x in v) / float(n - 1))


def _tukey_outliers(values) -> set:
    """Tukey's fences: outside [Q1 - 1.5*IQR, Q3 + 1.5*IQR].  This is what removes a
    TCP retransmission stall (low outlier) or a CDN cache burst (high outlier) without
    letting either drag the estimate."""
    v = list(values)
    if len(v) < 4:
        return set()
    q1 = _quantile(v, 0.25)
    q3 = _quantile(v, 0.75)
    iqr = q3 - q1
    if iqr <= 0:
        return set()
    lo, hi = q1 - 1.5 * iqr, q3 + 1.5 * iqr
    return {i for i, x in enumerate(v) if x < lo or x > hi}


def _mad_outliers(values, threshold: float = 3.5) -> set:
    """Iglewicz-Hoaglin modified z-score.  More resistant than Tukey (breakdown point
    50%), which is what we want ACROSS providers where one throttled CDN can be a wild
    point.  Documented zero-MAD fallback to the scaled mean absolute deviation."""
    v = list(values)
    if len(v) < 3:
        return set()
    med = _median(v)
    devs = [abs(x - med) for x in v]
    mad = _median(devs)
    if mad > 0:
        scores = [_MAD_SCALE * d / mad for d in devs]
    else:
        mean_ad = _mean(devs) * _MEANAD_SCALE
        if mean_ad <= 0:
            return set()
        scores = [d / mean_ad for d in devs]
    return {i for i, s in enumerate(scores) if s > threshold}


def _reject_outliers(values, method: str):
    """Return (kept_values, rejected_values) under the configured rule."""
    v = list(values)
    m = (method or "tukey").strip().lower()
    if m == "none" or len(v) < 4:
        return v, []
    idx = _mad_outliers(v) if m == "mad" else _tukey_outliers(v)
    kept = [x for i, x in enumerate(v) if i not in idx]
    rejected = [x for i, x in enumerate(v) if i in idx]
    # Never let the filter eat the sample: if it would leave fewer than 3 points the
    # data is simply that noisy, and silently returning 1 point would be a lie.
    if len(kept) < 3:
        return v, []
    return kept, rejected


def _trimmed_mean(values, trim_percent: float) -> float:
    """Symmetric trimmed mean — the robust location estimator that keeps the efficiency
    of the mean while bounding the influence of the tails."""
    v = sorted(values)
    n = len(v)
    if n == 0:
        return 0.0
    k = int(math.floor(n * max(0.0, min(45.0, trim_percent)) / 100.0))
    if n - 2 * k < 1:
        return _mean(v)
    return _mean(v[k:n - k])


def _rfc3550_jitter(samples_ms) -> float:
    """RFC 3550 §6.4.1 interarrival jitter: J += (|D(i-1,i)| - J)/16.  The exponentially
    weighted estimator every RTP/VoIP stack reports — not a naive stdev, so it matches
    what a Cisco/telecom operator will compare it against."""
    v = list(samples_ms)
    j = 0.0
    for i in range(1, len(v)):
        d = abs(v[i] - v[i - 1])
        j += (d - j) / 16.0
    return j


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance on the IUGG mean-radius sphere.  Used to shortlist Ookla
    servers.  (Euclidean distance on raw lat/lon is wrong away from the equator.)"""
    r = 6371.0088
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2.0) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2.0) ** 2
    return 2.0 * r * math.asin(math.sqrt(max(0.0, min(1.0, a))))


def _bdp_bytes(mbps: float, rtt_ms: float) -> float:
    """Bandwidth-Delay Product in bytes: the in-flight data a single TCP flow must hold
    to saturate this path.  If BDP exceeds the receive window, one stream CANNOT fill
    the link — which is precisely why this agent is multi-stream."""
    return (mbps * 1e6 / 8.0) * (rtt_ms / 1000.0)


def _mathis_ceiling_mbps(rtt_ms: float, loss_fraction: float, mss_bytes: int = 1460) -> float:
    """Mathis et al. (1997) macroscopic TCP model: BW <= MSS/(RTT*sqrt(p)).  The
    theoretical ceiling of ONE loss-based flow.  Reported so an operator can see at a
    glance whether the measurement was limited by the link or by TCP itself."""
    if rtt_ms <= 0 or loss_fraction <= 0:
        return float('inf')
    return (mss_bytes * 8.0) / ((rtt_ms / 1000.0) * math.sqrt(loss_fraction)) / 1e6


def _inverse_variance_meta(points, conf: float = 0.95, i2_threshold: float = 50.0) -> dict:
    """Fuse per-provider estimates.

    ``points`` = [(estimate, standard_error), ...].

    FIXED EFFECT: mu = sum(w_i*x_i)/sum(w_i) with w_i = 1/se_i^2.  That weighting is not
    a preference — it is the maximum-likelihood estimator for independent normal
    estimates with known variances, i.e. the provably minimum-variance linear unbiased
    combination.  A plain arithmetic mean throws that precision information away.

    HETEROGENEITY: Cochran's Q = sum(w_i*(x_i-mu)^2) ~ chi2(k-1) under homogeneity, and
    Higgins & Thompson's I^2 = max(0, (Q-df)/Q)*100 is the % of variance that is real
    disagreement rather than sampling noise.

    RANDOM EFFECTS: when I^2 exceeds the threshold the providers are measuring genuinely
    different things (different CDNs, different peering), so we switch to
    DerSimonian-Laird: tau^2 = max(0,(Q-df)/C), C = sum(w) - sum(w^2)/sum(w), and reweight
    with w*_i = 1/(se_i^2 + tau^2).  Reporting a narrow fixed-effect interval over
    heterogeneous providers would be over-confident, which for a bank or a carrier is
    worse than being imprecise.
    """
    usable = [(float(x), float(se)) for x, se in points
              if se is not None and se > 0 and x == x and x > 0]
    raw_vals = [float(x) for x, _ in points if x == x]

    if len(usable) < 2:
        est = _mean(raw_vals)
        return {
            "estimate": est, "se": 0.0, "ci": 0.0, "q": 0.0, "i2": 0.0,
            "tau2": 0.0, "k": len(raw_vals), "method": "unweighted_mean",
        }

    w = [1.0 / (se * se) for _, se in usable]
    sw = sum(w)
    fixed = sum(wi * xi for wi, (xi, _) in zip(w, usable)) / sw
    q = sum(wi * (xi - fixed) ** 2 for wi, (xi, _) in zip(w, usable))
    k = len(usable)
    df = k - 1
    i2 = max(0.0, (q - df) / q * 100.0) if (q > 0 and df > 0) else 0.0

    z = _z_critical(conf)
    if i2 > i2_threshold and df > 0:
        c = sw - (sum(wi * wi for wi in w) / sw)
        tau2 = max(0.0, (q - df) / c) if c > 0 else 0.0
        wr = [1.0 / ((se * se) + tau2) for _, se in usable]
        swr = sum(wr)
        est = sum(wi * xi for wi, (xi, _) in zip(wr, usable)) / swr
        se_pooled = math.sqrt(1.0 / swr)
        method = "dersimonian_laird_random_effects"
    else:
        tau2 = 0.0
        est = fixed
        se_pooled = math.sqrt(1.0 / sw)
        method = "inverse_variance_fixed_effect"

    return {
        "estimate": est, "se": se_pooled, "ci": z * se_pooled,
        "q": q, "i2": i2, "tau2": tau2, "k": k, "method": method,
    }


# ========================================
# HTTP / TRANSPORT LAYER (stdlib only)
# ========================================

_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
       "Chrome/126.0 Safari/537.36 Tlamatini-NetSpeed-Calculator/1.0")

_BASE_HEADERS = {
    "User-Agent": _UA,
    # identity: a gzip-inflated payload would report throughput that never crossed the
    # wire.  This single header is the difference between a measurement and a fiction.
    "Accept-Encoding": "identity",
    "Cache-Control": "no-cache, no-store",
    "Pragma": "no-cache",
    "Connection": "close",
}


def _ssl_ctx():
    try:
        return ssl.create_default_context()
    except Exception:
        return None


def _open(url: str, timeout: float, data=None, headers: dict = None, method: str = None):
    hdrs = dict(_BASE_HEADERS)
    if headers:
        hdrs.update(headers)
    req = urllib.request.Request(url, data=data, headers=hdrs, method=method)
    if url.lower().startswith("https"):
        return urllib.request.urlopen(req, timeout=timeout, context=_ssl_ctx())
    return urllib.request.urlopen(req, timeout=timeout)


def _read_text(url: str, timeout: float, limit: int = 4_000_000) -> str:
    with _open(url, timeout) as resp:
        return resp.read(limit).decode("utf-8", "replace")


def _bust(url: str, salt) -> str:
    """Append a unique query parameter.  Without it a transparent proxy or a CDN edge
    can serve the SAME object from cache to every stream and the agent would proudly
    measure the local cache instead of the Internet."""
    sep = "&" if "?" in url else "?"
    return f"{url}{sep}nocache={int(time.time() * 1000)}{salt}"


def _tcp_rtt_ms(host: str, port: int, timeout: float):
    """TCP-connect RTT.  Deliberately NOT ICMP: raw sockets need administrator rights on
    Windows, and half the Internet rate-limits or drops ICMP anyway, so a TCP handshake
    to the very port we are about to use is both more portable and more representative."""
    t0 = time.perf_counter()
    sock = None
    try:
        sock = socket.create_connection((host, port), timeout=timeout)
        return (time.perf_counter() - t0) * 1000.0
    except Exception:
        return None
    finally:
        try:
            if sock is not None:
                sock.close()
        except Exception:
            pass


def _latency_profile(host: str, port: int, samples: int, timeout: float) -> dict:
    """Baseline path characterization (RFC 6349 step 1)."""
    rtts, failures = [], 0
    for _ in range(max(3, samples)):
        rtt = _tcp_rtt_ms(host, port, timeout)
        if rtt is None:
            failures += 1
        else:
            rtts.append(rtt)
        time.sleep(0.05)
    total = len(rtts) + failures
    if not rtts:
        return {"ok": False, "min": 0.0, "median": 0.0, "mean": 0.0, "max": 0.0,
                "jitter": 0.0, "loss_pct": 100.0, "samples": 0}
    return {
        "ok": True,
        # MIN, not mean: the minimum RTT is the only sample uncontaminated by transient
        # queueing, so it is the correct baseline for the BDP and for bufferbloat.
        "min": min(rtts),
        "median": _median(rtts),
        "mean": _mean(rtts),
        "max": max(rtts),
        "jitter": _rfc3550_jitter(rtts),
        "loss_pct": (failures / float(total)) * 100.0 if total else 0.0,
        "samples": len(rtts),
    }


# ========================================
# THROUGHPUT ENGINE — multi-stream, warm-up-excluded, derivative-sampled
# ========================================

def _record_error(errors: list, exc) -> None:
    """Keep the first few DISTINCT failures of a transfer.

    Bounded on purpose: six streams retrying for eight seconds would otherwise bury the
    log under thousands of identical lines.  Bounded is NOT the same as hidden — the
    whole point is that a transfer which produced nothing must be able to SAY WHY.  A
    silent 0.00 Mbps is the single most expensive defect this agent can ship: it looks
    exactly like a slow link, so it sends the user hunting their own router."""
    text = "%s: %s" % (type(exc).__name__, exc)
    if text not in errors and len(errors) < 5:
        errors.append(text)


def _download_worker(idx: int, urls: list, counters: list, stop_evt, deadline: float,
                     timeout: float, max_bytes: int, errors: list,
                     cache_bust: bool = True, chunk: int = 65536):
    """One TCP flow.  Writes its running byte total to counters[idx] with a SINGLE store
    per chunk — atomic under the GIL, so the sampler reads a consistent value with no
    lock and therefore no measurement-perturbing contention."""
    n = len(urls)
    k = idx
    salt = 0
    local = 0
    use_bust = bool(cache_bust)
    while not stop_evt.is_set() and time.monotonic() < deadline:
        url = urls[k % n]
        k += 1
        salt += 1
        resp = None
        try:
            resp = _open(_bust(url, f"{idx}-{salt}") if use_bust else url, timeout)
            taken = 0
            while not stop_evt.is_set() and time.monotonic() < deadline:
                buf = resp.read(chunk)
                if not buf:
                    break
                local += len(buf)
                taken += len(buf)
                counters[idx] = local
                if taken >= max_bytes:
                    break
        except Exception as exc:
            _record_error(errors, exc)
            if use_bust and local == 0:
                # SELF-HEAL.  Measured 2026-08-22: *-speed.hetzner.com serves /100MB.bin
                # with HTTP 200, but RESETS the connection the instant the URL carries an
                # unknown query string — so the cache-buster that exists to PROTECT the
                # measurement was destroying it (all six streams, zero bytes, no reason
                # printed).  If nothing has arrived yet, drop the buster and let the next
                # iteration prove the plain URL.  The trade is deliberate and one-sided:
                # a cached object can only make a result look TOO GOOD, while a connection
                # reset makes a working link look like no Internet at all.
                use_bust = False
                _record_error(errors, RuntimeError(
                    "endpoint rejected the cache-buster query string - retrying WITHOUT it"))
            time.sleep(0.05)
        finally:
            try:
                if resp is not None:
                    resp.close()
            except Exception:
                pass


def _upload_worker(idx: int, target: str, counters: list, stop_evt, deadline: float,
                   timeout: float, payload: bytes, payload_bytes: int, errors: list):
    """One upload flow, driven through http.client so bytes are counted AS THEY ARE
    HANDED TO THE SOCKET rather than only when a whole POST completes — which is what
    makes fine-grained derivative sampling possible in this direction too."""
    parsed = urllib.parse.urlsplit(target)
    host = parsed.hostname
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    path = parsed.path or "/"
    if parsed.query:
        path = f"{path}?{parsed.query}"
    view = memoryview(payload)
    step = len(payload)
    local = 0
    while not stop_evt.is_set() and time.monotonic() < deadline:
        conn = None
        try:
            if parsed.scheme == "https":
                conn = http.client.HTTPSConnection(host, port, timeout=timeout, context=_ssl_ctx())
            else:
                conn = http.client.HTTPConnection(host, port, timeout=timeout)
            conn.putrequest("POST", path, skip_host=True, skip_accept_encoding=True)
            conn.putheader("Host", parsed.netloc)
            conn.putheader("User-Agent", _UA)
            conn.putheader("Content-Type", "application/octet-stream")
            conn.putheader("Content-Length", str(payload_bytes))
            conn.putheader("Accept-Encoding", "identity")
            conn.putheader("Connection", "close")
            conn.endheaders()
            sent = 0
            while sent < payload_bytes and not stop_evt.is_set() and time.monotonic() < deadline:
                take = min(step, payload_bytes - sent)
                conn.send(view[:take])
                sent += take
                local += take
                counters[idx] = local
            if sent >= payload_bytes:
                try:
                    conn.getresponse().read()
                except Exception:
                    pass
        except Exception as exc:
            # Same contract as the download side: an upload that moved no bytes must
            # report the reason.  Measured 2026-08-22: a public LibreSpeed backend
            # accepts the connection and then never drains the body, which surfaces
            # here as a write timeout instead of as an unexplained 0.00 Mbps.
            _record_error(errors, exc)
            time.sleep(0.05)
        finally:
            try:
                if conn is not None:
                    conn.close()
            except Exception:
                pass


def _sampler(counters: list, interval: float, deadline: float, stop_evt, out: list, t0: float):
    """Take d(bytes)/dt slices.  Measuring the DERIVATIVE rather than total/elapsed is
    what lets us drop the slow-start ramp cleanly AND makes a constant socket-buffer
    occupancy cancel out of the upload figure instead of inflating it."""
    prev_total = 0
    prev_t = time.monotonic()
    while not stop_evt.is_set() and time.monotonic() < deadline:
        time.sleep(interval)
        now = time.monotonic()
        total = sum(counters)
        dt = now - prev_t
        if dt <= 0:
            continue
        mbps = ((total - prev_total) * 8.0) / dt / 1e6
        out.append((now - t0, mbps))
        prev_total, prev_t = total, now


def _loaded_rtt_sampler(host: str, port: int, timeout: float, deadline: float,
                        stop_evt, out: list):
    """RTT while the link is saturated -> bufferbloat.  A link that is 'fast' but adds
    300 ms of queueing under load is unusable for VoIP, trading or SSH, which is exactly
    the failure mode this agent's professional users care about."""
    while not stop_evt.is_set() and time.monotonic() < deadline:
        rtt = _tcp_rtt_ms(host, port, timeout)
        if rtt is not None:
            out.append(rtt)
        time.sleep(0.4)


def _bufferbloat_grade(delta_ms: float) -> str:
    """Waveform / DSLReports bufferbloat scale (latency INCREASE under load)."""
    if delta_ms < 5:
        return "A+"
    if delta_ms < 30:
        return "A"
    if delta_ms < 60:
        return "B"
    if delta_ms < 200:
        return "C"
    if delta_ms < 400:
        return "D"
    return "F"


def _run_transfer(direction: str, endpoints, streams: int, duration: float, warmup: float,
                  interval: float, timeout: float, max_bytes: int, payload: bytes,
                  payload_bytes: int, rtt_probe=None, cache_bust: bool = True) -> dict:
    """Run ONE direction against ONE provider and reduce it to a robust estimate."""
    streams = max(1, min(32, streams))
    counters = [0] * streams
    stop_evt = threading.Event()
    samples, loaded_rtts = [], []
    # Shared across every stream so a transfer that moved nothing can name its cause.
    errors = []
    t0 = time.monotonic()
    deadline = t0 + warmup + duration

    workers = []
    for i in range(streams):
        if direction == "download":
            th = threading.Thread(target=_download_worker,
                                  args=(i, endpoints, counters, stop_evt, deadline,
                                        timeout, max_bytes, errors, cache_bust),
                                  daemon=True)
        else:
            th = threading.Thread(target=_upload_worker,
                                  args=(i, endpoints, counters, stop_evt, deadline,
                                        timeout, payload, payload_bytes, errors),
                                  daemon=True)
        th.start()
        workers.append(th)

    sampler = threading.Thread(target=_sampler,
                               args=(counters, interval, deadline, stop_evt, samples, t0),
                               daemon=True)
    sampler.start()

    rtt_thread = None
    if rtt_probe:
        rtt_thread = threading.Thread(target=_loaded_rtt_sampler,
                                      args=(rtt_probe[0], rtt_probe[1], timeout,
                                            deadline, stop_evt, loaded_rtts),
                                      daemon=True)
        rtt_thread.start()

    while time.monotonic() < deadline:
        time.sleep(0.1)
    stop_evt.set()
    for th in workers:
        th.join(timeout=3.0)
    sampler.join(timeout=2.0)
    if rtt_thread is not None:
        rtt_thread.join(timeout=2.0)

    total_bytes = sum(counters)
    # RFC 6349: DISCARD the slow-start ramp. Everything before `warmup` is the ramp.
    steady = [mbps for (ts, mbps) in samples if ts >= warmup]
    if len(steady) < 3:
        steady = [mbps for (_, mbps) in samples]

    return {
        "raw_samples": [round(m, 4) for m in steady],
        "all_samples": len(samples),
        "discarded_warmup": len(samples) - len(steady),
        "total_bytes": total_bytes,
        "loaded_rtts": loaded_rtts,
        "streams": streams,
        "errors": errors,
    }


def _reduce(raw, method: str, trim_percent: float, conf: float) -> dict:
    """Outlier rejection -> trimmed mean -> Student-t interval."""
    kept, rejected = _reject_outliers(raw, method)
    if not kept:
        return {"mbps": 0.0, "median": 0.0, "p95": 0.0, "stdev": 0.0, "se": 0.0,
                "ci": 0.0, "cv_pct": 0.0, "n": 0, "rejected": 0, "ok": False}
    trimmed = _trimmed_mean(kept, trim_percent)
    sd = _stdev(kept)
    n = len(kept)
    se = sd / math.sqrt(n) if n > 1 else 0.0
    return {
        "mbps": trimmed,
        "median": _median(kept),
        "p95": _quantile(kept, 0.95),
        "stdev": sd,
        "se": se,
        "ci": _t_critical(n - 1, conf) * se,
        "cv_pct": (sd / trimmed * 100.0) if trimmed > 0 else 0.0,
        "n": n,
        "rejected": len(rejected),
        "ok": trimmed > 0,
    }


# ========================================
# PROVIDER DISCOVERY — every endpoint public, keyless, login-free
# ========================================

PROVIDER_CATALOGUE = {
    "cloudflare": "Cloudflare Speed Test (speed.cloudflare.com) — anycast, download + UPLOAD",
    "ookla":      "Ookla / Speedtest.net server mesh — geo+RTT selected, download + UPLOAD",
    "fast":       "Fast.com / Netflix Open Connect CDN — download",
    "librespeed": "LibreSpeed public server mesh (RTT-selected) — download + UPLOAD",
    "hetzner":    "Hetzner .com datacentre mirrors (RTT-selected) — download",
    "cachefly":   "CacheFly cachefly.cachefly.net — download",
}


def _pick_by_rtt(hosts: list, port: int, timeout: float) -> str:
    """Choose the mirror with the LOWEST measured TCP RTT.

    Mirror lists are published by geography, but geography is only a proxy for network
    distance — peering and transit decide.  Measured live from Mexico City
    (2026-08-22): Hetzner's US mirrors answer in ~265 ms, its German ones in ~391 ms
    and its Singapore one in ~453 ms, so taking 'the first one in the list' would have
    measured a transpacific path and reported it as this machine's Internet speed.
    Falls back to the first host if none answer."""
    best, best_rtt = None, None
    for host in hosts:
        rtt = _tcp_rtt_ms(host, port, min(5.0, timeout))
        if rtt is not None and (best_rtt is None or rtt < best_rtt):
            best, best_rtt = host, rtt
    return best or (hosts[0] if hosts else "")


#: Cloudflare's __down endpoint REJECTS very large `bytes` values with HTTP 403 —
#: measured: bytes=100000000 -> 403 Forbidden, bytes=25000000 -> 200 OK.  Requesting
#: too much therefore yielded ZERO bytes and a silent 0.00 Mbps.  Streams simply
#: re-request when a chunk finishes, so a smaller object costs nothing.
_CF_MAX_DOWN_BYTES = 25_000_000


def _discover_cloudflare(timeout: float, max_bytes: int) -> dict:
    # /meta answers 403 to a non-browser client; cdn-cgi/trace is the stable, public,
    # keyless endpoint every Cloudflare property exposes.
    trace = {}
    try:
        for line in _read_text("https://speed.cloudflare.com/cdn-cgi/trace", timeout).splitlines():
            if "=" in line:
                k, v = line.split("=", 1)
                trace[k.strip()] = v.strip()
    except Exception:
        trace = {}
    size = max(1_000_000, min(int(max_bytes), _CF_MAX_DOWN_BYTES))
    loc = " / ".join(str(x) for x in (trace.get("loc"), trace.get("colo")) if x)
    return {
        "key": "cloudflare",
        "label": "Cloudflare Speed Test",
        "download": [f"https://speed.cloudflare.com/__down?bytes={size}"],
        "upload": "https://speed.cloudflare.com/__up",
        "upload_content_type": "application/octet-stream",
        "upload_prefix": b"",
        "rtt": ("speed.cloudflare.com", 443),
        "location": ("Cloudflare edge " + loc).strip() if loc else "Cloudflare anycast edge",
        "isp": "",
        "client_ip": trace.get("ip", ""),
    }


def _discover_ookla(timeout: float) -> dict:
    client = {}
    try:
        xml = _read_text("https://www.speedtest.net/speedtest-config.php", timeout)
        node = ET.fromstring(xml).find("client")
        if node is not None:
            client = dict(node.attrib)
    except Exception:
        client = {}

    servers = json.loads(_read_text(
        "https://www.speedtest.net/api/js/servers?engine=js&limit=25", timeout))
    if not isinstance(servers, list) or not servers:
        raise RuntimeError("Ookla returned an empty server list")

    # 1) Great-circle shortlist (Haversine, NOT Euclidean lat/lon).
    try:
        lat, lon = float(client.get("lat")), float(client.get("lon"))
        for s in servers:
            s["_km"] = _haversine_km(lat, lon, float(s.get("lat", 0)), float(s.get("lon", 0)))
        servers.sort(key=lambda s: s.get("_km", 1e9))
    except Exception:
        pass

    # 2) Then pick by MEASURED RTT among the shortlist — geographic proximity is a proxy
    #    for network proximity, never a substitute for it (peering and transit decide).
    best, best_rtt = None, None
    for s in servers[:5]:
        hostport = str(s.get("host", ""))
        if ":" not in hostport:
            continue
        h, p = hostport.rsplit(":", 1)
        rtt = _tcp_rtt_ms(h, int(p), min(5.0, timeout))
        if rtt is not None and (best_rtt is None or rtt < best_rtt):
            best, best_rtt = s, rtt
    if best is None:
        best = servers[0]

    upload_url = str(best.get("url", ""))
    base = upload_url.rsplit("/", 1)[0] if "/" in upload_url else ""
    if not base:
        raise RuntimeError("Ookla server exposed no usable URL")
    hostport = str(best.get("host", ""))
    h, p = (hostport.rsplit(":", 1) + ["8080"])[:2] if hostport else ("", "8080")
    return {
        "key": "ookla",
        "label": "Ookla / Speedtest.net",
        "download": [f"{base}/random4000x4000.jpg", f"{base}/random3000x3000.jpg"],
        "upload": upload_url,
        "rtt": (h, int(p)) if h else None,
        "location": "%s (%s, %s)%s" % (
            best.get("sponsor", "?"), best.get("name", "?"), best.get("country", "?"),
            (" — %.0f km" % best["_km"]) if "_km" in best else ""),
        "isp": client.get("isp", ""),
        "client_ip": client.get("ip", ""),
    }


def _discover_fast(timeout: float) -> dict:
    """fast.com's measurement token is a PUBLIC constant embedded in the page bundle —
    reading it is exactly what the browser does, and needs no account, no key and no
    login.  It rotates, so it is scraped fresh rather than hardcoded."""
    html = _read_text("https://fast.com/", timeout)
    m = re.search(r'src="(/app-[0-9a-f]+\.js)"', html)
    if not m:
        raise RuntimeError("fast.com bundle not found")
    js = _read_text("https://fast.com" + m.group(1), timeout)
    tm = re.search(r'token:"([^"]+)"', js)
    if not tm:
        raise RuntimeError("fast.com token not found")
    payload = json.loads(_read_text(
        "https://api.fast.com/netflix/speedtest/v2?https=true&token=%s&urlCount=5"
        % tm.group(1), timeout))
    targets = payload.get("targets") or []
    urls = [t["url"] for t in targets if t.get("url")]
    if not urls:
        raise RuntimeError("fast.com returned no targets")
    loc = ""
    try:
        lc = targets[0].get("location") or {}
        loc = ", ".join(str(x) for x in (lc.get("city"), lc.get("country")) if x)
    except Exception:
        loc = ""
    host = urllib.parse.urlsplit(urls[0]).hostname or ""
    return {
        "key": "fast",
        "label": "Fast.com (Netflix Open Connect)",
        "download": urls,
        "upload": "",
        "rtt": (host, 443) if host else None,
        "location": loc or "Netflix Open Connect",
        "isp": (payload.get("client") or {}).get("isp", ""),
        "client_ip": (payload.get("client") or {}).get("ip", ""),
    }


#: How many published LibreSpeed servers to RTT-probe before choosing.  The list runs
#: to ~22 entries and each probe costs up to `timeout`; 8 is enough to find a near
#: server on any continent without turning discovery into the slowest part of the run.
_LIBRESPEED_PROBE_LIMIT = 8


def _discover_librespeed(timeout: float) -> dict:
    """librespeed.org/backend/ is GONE — measured 2026-08-22: garbage.php and
    empty.php BOTH answer 404, so the hardcoded backend contributed zero bytes.
    LibreSpeed's live surface is its PUBLIC SERVER LIST, the same one the official
    web client consumes (22 servers published, every probed one answering 200).
    Fetch it and choose by MEASURED RTT — a published list is geography, not
    network distance."""
    servers = json.loads(_read_text(
        "https://librespeed.org/backend-servers/servers.php", timeout))
    if not isinstance(servers, list) or not servers:
        raise RuntimeError("LibreSpeed published an empty server list")

    by_host = {}
    for srv in servers:
        base = str(srv.get("server", "")).strip().rstrip("/")
        if base.startswith("//"):          # the list uses protocol-relative URLs
            base = "https:" + base
        if not base.startswith("http"):
            continue
        host = urllib.parse.urlsplit(base).hostname
        if host and host not in by_host:
            by_host[host] = (base, srv)
    if not by_host:
        raise RuntimeError("LibreSpeed list exposed no usable server URL")

    host = _pick_by_rtt(list(by_host)[:_LIBRESPEED_PROBE_LIMIT], 443, timeout)
    base, srv = by_host[host]
    dl = str(srv.get("dlURL") or "garbage.php").lstrip("/")
    ul = str(srv.get("ulURL") or "empty.php").lstrip("/")
    sep = "&" if "?" in dl else "?"
    name = str(srv.get("name") or host)
    return {
        "key": "librespeed",
        "label": "LibreSpeed (%s)" % name,
        "download": ["%s/%s%sckSize=25" % (base, dl, sep)],
        "upload": "%s/%s" % (base, ul),
        "rtt": (host, 443),
        "location": name,
        "isp": "", "client_ip": "",
    }


def _discover_hetzner(timeout: float) -> dict:
    """speed.hetzner.de NO LONGER RESOLVES — measured 2026-08-22: getaddrinfo fails
    outright (the host is gone, not merely refusing), so this provider could never
    contribute a byte.  Hetzner's live surface is its per-datacentre `.com` mirror
    mesh; all six answer 200.  They sit on three continents, so the mirror is chosen
    by MEASURED RTT rather than by list order."""
    mirrors = ["hil-speed.hetzner.com", "ash-speed.hetzner.com",
               "nbg1-speed.hetzner.com", "fsn1-speed.hetzner.com",
               "hel1-speed.hetzner.com", "sin-speed.hetzner.com"]
    host = _pick_by_rtt(mirrors, 443, timeout)
    return {
        "key": "hetzner",
        "label": "Hetzner (%s)" % host,
        "download": ["https://%s/100MB.bin" % host],
        # Measured 2026-08-22: appending ANY unknown query string to the mirror object
        # makes it close the connection without a response, so the cache-buster is
        # declared off here rather than discovered the hard way on every run.  The
        # object is a fixed 100 MB file behind no CDN edge, so there is nothing for a
        # buster to defeat.
        "cache_bust": False,
        "upload": "",
        "rtt": (host, 443),
        "location": "Hetzner mirror %s" % host,
        "isp": "", "client_ip": "",
    }


def _discover_cachefly(timeout: float) -> dict:
    return {
        "key": "cachefly",
        "label": "CacheFly (cachefly.cachefly.net)",
        "download": ["https://cachefly.cachefly.net/100mb.test"],
        "upload": "",
        "rtt": ("cachefly.cachefly.net", 443),
        "location": "CacheFly global CDN",
        "isp": "", "client_ip": "",
    }


def _discover(key: str, timeout: float, max_bytes: int) -> dict:
    if key == "cloudflare":
        return _discover_cloudflare(timeout, max_bytes)
    if key == "ookla":
        return _discover_ookla(timeout)
    if key == "fast":
        return _discover_fast(timeout)
    if key == "librespeed":
        return _discover_librespeed(timeout)
    if key == "hetzner":
        return _discover_hetzner(timeout)
    if key == "cachefly":
        return _discover_cachefly(timeout)
    raise RuntimeError(f"unknown provider '{key}'")


# ========================================
# OUTPUT PATHS
# ========================================

def _app_root() -> str:
    """The Tlamatini app/install root. The core exports TLAMATINI_TEMP as <app>/Temp, so
    the parent of that is <install_dir>. Standalone fallback: a per-user writable dir."""
    temp = (os.environ.get("TLAMATINI_TEMP") or "").strip()
    if temp:
        return os.path.dirname(os.path.normpath(temp))
    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA") or os.path.join(os.path.expanduser("~"), "AppData", "Local")
    else:
        base = os.environ.get("XDG_DATA_HOME") or os.path.join(os.path.expanduser("~"), ".local", "share")
    return os.path.join(base, "Tlamatini")


def _default_output_dir(config: dict) -> str:
    explicit = str(_cfg(config, "output_dir")).strip()
    if explicit:
        return explicit
    temp = (os.environ.get("TLAMATINI_TEMP") or "").strip()
    base = temp if temp else os.path.join(_app_root(), "Temp")
    return os.path.join(base, "NetSpeedCalculator")


# ========================================
# FAIL-SAFE PREFLIGHT
# ========================================

def _preflight(action: str, config: dict, providers: list) -> dict:
    """REFUSE rather than mis-measure. A wrong number is worse than an honest refusal —
    these users make capacity and procurement decisions from it."""
    report = {"ok": True, "errors": [], "warnings": []}

    if action not in ("full", "download", "upload", "latency", "validate", "providers"):
        report["errors"].append(
            "unknown action '%s' (full | download | upload | latency | validate | providers)" % action)

    if action == "providers":
        report["ok"] = not report["errors"]
        return report

    unknown = [p for p in providers if p not in PROVIDER_CATALOGUE]
    if unknown:
        report["errors"].append("unknown provider(s): %s (known: %s)"
                                % (", ".join(unknown), ", ".join(sorted(PROVIDER_CATALOGUE))))
    if not providers:
        report["errors"].append("no providers selected — set `providers` to at least one of: %s"
                                % ", ".join(sorted(PROVIDER_CATALOGUE)))
    elif len(providers) < 3 and action in ("full", "download", "upload"):
        report["warnings"].append(
            "only %d provider(s) selected; 3+ is recommended so a single unavailable or "
            "throttled endpoint cannot decide the result" % len(providers))

    if action in ("full", "upload"):
        up_capable = [p for p in providers if p in ("cloudflare", "ookla", "librespeed")]
        if not up_capable:
            report["errors"].append(
                "no upload-capable provider selected — upload needs at least one of "
                "cloudflare / ookla / librespeed")
        elif len(up_capable) < 2:
            report["warnings"].append(
                "only 1 upload-capable provider (%s); the upload figure cannot be "
                "cross-corroborated" % up_capable[0])

    streams = _as_int(_cfg(config, "parallel_streams", 6), 6)
    if streams < 1 or streams > 32:
        report["errors"].append("parallel_streams must be 1..32 (got %s)" % streams)
    elif streams == 1 and action in ("full", "download", "upload"):
        report["warnings"].append(
            "parallel_streams=1: a single TCP flow is bounded by Window/RTT and by the "
            "Mathis limit, so a high bandwidth-delay-product link WILL be under-reported")

    duration = _as_float(_cfg(config, "test_duration_seconds", 10), 10.0)
    warmup = _as_float(_cfg(config, "warmup_seconds", 2), 2.0)
    interval = _as_float(_cfg(config, "sample_interval_seconds", 0.25), 0.25)
    if duration < 1.0:
        report["errors"].append("test_duration_seconds must be >= 1 (got %s)" % duration)
    if warmup < 0:
        report["errors"].append("warmup_seconds must be >= 0 (got %s)" % warmup)
    if interval <= 0:
        report["errors"].append("sample_interval_seconds must be > 0 (got %s)" % interval)
    elif duration / interval < 8 and action in ("full", "download", "upload"):
        report["warnings"].append(
            "only ~%d steady-state slices per direction; the confidence interval will be "
            "wide (raise test_duration_seconds or lower sample_interval_seconds)"
            % int(duration / interval))

    trim = _as_float(_cfg(config, "trim_percent", 10), 10.0)
    if trim < 0 or trim >= 50:
        report["errors"].append("trim_percent must be 0..49 (got %s)" % trim)

    method = str(_cfg(config, "outlier_rejection", "tukey")).strip().lower()
    if method not in ("tukey", "mad", "none"):
        report["errors"].append("outlier_rejection must be tukey | mad | none (got '%s')" % method)

    agg = str(_cfg(config, "aggregation", "inverse_variance")).strip().lower()
    if agg not in ("inverse_variance", "trimmed_mean", "median"):
        report["errors"].append(
            "aggregation must be inverse_variance | trimmed_mean | median (got '%s')" % agg)

    # DNS is the one hard dependency: with no resolver nothing below can work.
    if action != "validate":
        try:
            socket.getaddrinfo("speed.cloudflare.com", 443)
        except Exception as exc:
            report["warnings"].append(
                "DNS resolution of speed.cloudflare.com failed (%s) — the run continues, "
                "but connectivity looks broken" % exc)

    out_dir = _default_output_dir(config)
    try:
        os.makedirs(out_dir, exist_ok=True)
        probe = os.path.join(out_dir, ".netspeed_write_probe")
        with open(probe, "w", encoding="utf-8") as fh:
            fh.write("ok")
        os.remove(probe)
    except Exception as exc:
        report["warnings"].append("output_dir '%s' is not writable (%s); the report will "
                                  "still be logged" % (out_dir, exc))

    report["ok"] = not report["errors"]
    return report


# ========================================
# STRUCTURED OUTPUT
# ========================================

def _emit_section(fields: dict, body: str) -> None:
    """Emit an INI_SECTION_NETSPEED_CALCULATOR<<< block ATOMICALLY (a single
    logging.info call — a split write can interleave with another thread and corrupt the
    block).  KV header names MUST stay aligned with
    agent_contracts._PARAMETRIZER_OUTPUT_FIELDS['netspeed_calculator'] and
    parametrizer.SECTION_AGENT_TYPES."""
    header = "\n".join(f"{key}: {value}" for key, value in fields.items())
    logging.info("INI_SECTION_NETSPEED_CALCULATOR<<<\n" + header + "\n\n" + body
                 + "\n>>>END_SECTION_NETSPEED_CALCULATOR")


def _fmt(value: float, digits: int = 2) -> str:
    try:
        if value != value or value in (float("inf"), float("-inf")):
            return "n/a"
        return f"{value:.{digits}f}"
    except Exception:
        return "n/a"


def _human_bytes(n: float) -> str:
    for unit in ("B", "KiB", "MiB", "GiB"):
        if abs(n) < 1024.0:
            return f"{n:.1f} {unit}"
        n /= 1024.0
    return f"{n:.1f} TiB"


# ========================================
# MAIN
# ========================================

def _report_dead_transfer(key: str, direction: str, raw: dict, red: dict) -> None:
    """A direction that moved ZERO bytes MUST name its cause — in the log and in the
    saved result.  Without this, a broken endpoint is indistinguishable from a slow
    link: both print 0.00 Mbps, and the user goes looking for a fault in their own
    house.  Every such silence in this agent's history (Cloudflare's 403 on an
    oversized object, Hetzner's reset on a cache-buster) cost a debugging session."""
    if raw.get("total_bytes"):
        return
    reasons = list(raw.get("errors") or [])
    if not reasons:
        reasons = ["no exception was raised — the endpoint accepted the request and "
                   "returned an empty body"]
    red["why"] = reasons
    logging.warning("   ⚠ %s %s produced ZERO bytes — cause:" % (key, direction))
    for reason in reasons:
        logging.warning("        · %s" % reason)


def main():
    config = load_config()
    write_pid_file()
    started_at = time.monotonic()

    try:
        if _IS_REANIMATED:
            logging.info("🔄 NetSpeed-Calculator REANIMATED (resuming from pause)")
            logging.info("=" * 60)

        target_agents = config.get('target_agents', []) or []
        action = str(_cfg(config, "action", "full")).strip().lower() or "full"
        providers = [p.strip().lower() for p in
                     str(_cfg(config, "providers", "")).replace(";", ",").split(",") if p.strip()]
        if not providers:
            providers = ["cloudflare", "ookla", "fast", "librespeed", "hetzner"]

        streams = _as_int(_cfg(config, "parallel_streams", 6), 6)
        duration = _as_float(_cfg(config, "test_duration_seconds", 10), 10.0)
        warmup = _as_float(_cfg(config, "warmup_seconds", 2), 2.0)
        interval = _as_float(_cfg(config, "sample_interval_seconds", 0.25), 0.25)
        timeout = _as_float(_cfg(config, "request_timeout", 30), 30.0)
        max_bytes = _as_int(_cfg(config, "max_bytes_per_stream", 100_000_000), 100_000_000)
        payload_mb = _as_int(_cfg(config, "upload_payload_mb", 8), 8)
        lat_samples = _as_int(_cfg(config, "latency_samples", 12), 12)
        min_ok = _as_int(_cfg(config, "min_successful_providers", 2), 2)
        trim = _as_float(_cfg(config, "trim_percent", 10), 10.0)
        conf = _as_float(_cfg(config, "confidence_level", 0.95), 0.95)
        method = str(_cfg(config, "outlier_rejection", "tukey")).strip().lower() or "tukey"
        agg = str(_cfg(config, "aggregation", "inverse_variance")).strip().lower() or "inverse_variance"
        i2_thr = _as_float(_cfg(config, "heterogeneity_i2_threshold", 50), 50.0)
        do_bloat = _as_bool(_cfg(config, "measure_bufferbloat", True), True)
        save_json = _as_bool(_cfg(config, "save_json", True), True)
        do_preflight = _as_bool(_cfg(config, "preflight", True), True)
        hard_cap = _as_float(_cfg(config, "command_timeout", 300), 300.0)

        logging.info("📡 NETSPEED-CALCULATOR AGENT STARTED")
        logging.info(f"   action={action}  providers={','.join(providers)}")
        logging.info(f"   streams={streams}  window={duration}s  warmup={warmup}s (RFC 6349 ramp discard)")
        logging.info(f"   outlier={method}  trim={trim}%  aggregation={agg}  conf={conf}")

        outcome = {
            "action": action,
            "status": "error",
            "success": "false",
            "providers_attempted": len(providers),
            "providers_ok": 0,
            "providers_failed": 0,
            "download_mbps": "0.00",
            "upload_mbps": "0.00",
            "download_ci95": "0.00",
            "upload_ci95": "0.00",
            "latency_ms": "0.00",
            "jitter_ms": "0.00",
            "packet_loss_pct": "0.00",
            "bufferbloat_ms": "0.00",
            "bufferbloat_grade": "n/a",
            "aggregation": agg,
            "heterogeneity_i2": "0.0",
            "samples": 0,
            "isp": "",
            "client_ip": "",
            "server_location": "",
            "json_path": "",
            "stage": "startup",
        }
        body = ""

        # ---------- preflight (fail-safe: REFUSE, never mis-measure) ----------
        pf = {"ok": True, "errors": [], "warnings": []}
        if do_preflight:
            pf = _preflight(action, config, providers)
            for w in pf["warnings"]:
                logging.warning(f"⚠️ preflight: {w}")
            if not pf["ok"]:
                for e in pf["errors"]:
                    logging.error(f"⛔ preflight: {e}")
                outcome.update({"status": "refused", "stage": "preflight"})
                body = ("⛔ NetSpeed-Calculator REFUSED to run — the measurement could not be "
                        "trusted.\n\nBLOCKERS:\n  - " + "\n  - ".join(pf["errors"]))
                if pf["warnings"]:
                    body += "\n\nWARNINGS:\n  - " + "\n  - ".join(pf["warnings"])

        # ---------- action: providers (read-only catalogue) ----------
        if pf["ok"] and action == "providers":
            lines = ["📇 NetSpeed-Calculator provider catalogue "
                     "(ALL keyless — no API key, no login, no account):", ""]
            for key in sorted(PROVIDER_CATALOGUE):
                mark = "✔ selected" if key in providers else "  available"
                lines.append(f"  [{mark}] {key:<11} {PROVIDER_CATALOGUE[key]}")
            lines += ["", "Upload-capable: cloudflare, ookla, librespeed.",
                      "Download-capable: all of the above."]
            body = "\n".join(lines)
            outcome.update({"status": "listed", "success": "true", "stage": "catalogue"})

        # ---------- measuring actions ----------
        elif pf["ok"]:
            payload = os.urandom(1024 * 1024)          # incompressible: a zero-filled body
            payload_bytes = max(1, payload_mb) * 1024 * 1024   # would be squeezed in transit
            results, failures = [], []
            deadline_all = started_at + hard_cap

            for key in providers:
                if time.monotonic() > deadline_all:
                    failures.append((key, "skipped: command_timeout reached"))
                    logging.warning(f"⏱ skipping {key}: command_timeout reached")
                    continue
                logging.info(f"── provider: {key} ──────────────────────────────")
                try:
                    prov = _discover(key, timeout, max_bytes)
                except Exception as exc:
                    failures.append((key, f"discovery failed: {exc}"))
                    logging.warning(f"⚠️ {key}: discovery failed ({exc}) — skipping, not fatal")
                    continue

                entry = {"key": key, "label": prov["label"], "location": prov["location"],
                         "isp": prov.get("isp", ""), "client_ip": prov.get("client_ip", ""),
                         "latency": None, "download": None, "upload": None,
                         "bufferbloat_ms": None}

                # 1) path characterization
                if prov.get("rtt"):
                    entry["latency"] = _latency_profile(prov["rtt"][0], prov["rtt"][1],
                                                        lat_samples, min(8.0, timeout))
                    if entry["latency"]["ok"]:
                        logging.info("   RTT min=%s ms  median=%s ms  jitter=%s ms  loss=%s%%"
                                     % (_fmt(entry["latency"]["min"]),
                                        _fmt(entry["latency"]["median"]),
                                        _fmt(entry["latency"]["jitter"]),
                                        _fmt(entry["latency"]["loss_pct"], 1)))
                    else:
                        failures.append((key, "unreachable: no TCP handshake completed"))
                        logging.warning(f"⚠️ {key}: unreachable (no TCP handshake) — skipping")
                        continue

                if action == "latency":
                    results.append(entry)
                    continue

                # 2) download
                if action in ("full", "download") and prov.get("download"):
                    raw = _run_transfer("download", prov["download"], streams, duration,
                                        warmup, interval, timeout, max_bytes, payload,
                                        payload_bytes,
                                        rtt_probe=prov.get("rtt") if do_bloat else None,
                                        cache_bust=prov.get("cache_bust", True))
                    red = _reduce(raw["raw_samples"], method, trim, conf)
                    red["bytes"] = raw["total_bytes"]
                    red["discarded_warmup"] = raw["discarded_warmup"]
                    entry["download"] = red
                    if do_bloat and raw["loaded_rtts"] and entry["latency"]:
                        entry["bufferbloat_ms"] = max(
                            0.0, _median(raw["loaded_rtts"]) - entry["latency"]["min"])
                    logging.info("   ⬇ download %s Mbps  (±%s, median %s, p95 %s, n=%d, %d rejected, %s)"
                                 % (_fmt(red["mbps"]), _fmt(red["ci"]), _fmt(red["median"]),
                                    _fmt(red["p95"]), red["n"], red["rejected"],
                                    _human_bytes(raw["total_bytes"])))
                    _report_dead_transfer(key, "download", raw, red)

                # 3) upload
                if action in ("full", "upload") and prov.get("upload"):
                    raw = _run_transfer("upload", prov["upload"], streams, duration,
                                        warmup, interval, timeout, max_bytes, payload,
                                        payload_bytes, rtt_probe=None)
                    red = _reduce(raw["raw_samples"], method, trim, conf)
                    red["bytes"] = raw["total_bytes"]
                    red["discarded_warmup"] = raw["discarded_warmup"]
                    entry["upload"] = red
                    logging.info("   ⬆ upload   %s Mbps  (±%s, median %s, p95 %s, n=%d, %d rejected, %s)"
                                 % (_fmt(red["mbps"]), _fmt(red["ci"]), _fmt(red["median"]),
                                    _fmt(red["p95"]), red["n"], red["rejected"],
                                    _human_bytes(raw["total_bytes"])))
                    _report_dead_transfer(key, "upload", raw, red)
                elif action in ("full", "upload"):
                    logging.info("   ⬆ upload   not supported by this provider — skipped")

                produced = ((entry["download"] and entry["download"]["ok"])
                            or (entry["upload"] and entry["upload"]["ok"]))
                if produced or action == "latency":
                    results.append(entry)
                else:
                    failures.append((key, "no usable samples (transfer produced nothing)"))

            # ================= CROSS-PROVIDER FUSION =================
            # The COMPLETE calculation happens HERE, before a single downstream agent is
            # raised — that ordering is a contract, not an implementation detail.
            logging.info("🧮 Fusing %d provider result(s) — the COMPLETE calculation runs "
                         "to the end BEFORE any downstream agent is raised." % len(results))

            def _pool(direction):
                pts, vals = [], []
                for e in results:
                    r = e.get(direction)
                    if r and r["ok"]:
                        pts.append((r["mbps"], r["se"] if r["se"] > 0 else r["mbps"] * 0.02))
                        vals.append(r["mbps"])
                if not vals:
                    return None
                # Cross-provider robustness: one throttled or peered-badly CDN must not
                # decide the answer.  MAD (50% breakdown) is the right tool across a
                # handful of heterogeneous sources.
                bad = _mad_outliers(vals) if len(vals) >= 3 else set()
                kept_pts = [p for i, p in enumerate(pts) if i not in bad]
                kept_vals = [v for i, v in enumerate(vals) if i not in bad]
                if len(kept_vals) < 2:
                    kept_pts, kept_vals, bad = pts, vals, set()
                if agg == "median":
                    est = _median(kept_vals)
                    meta = {"estimate": est, "se": 0.0, "ci": 0.0, "q": 0.0, "i2": 0.0,
                            "tau2": 0.0, "k": len(kept_vals), "method": "median"}
                elif agg == "trimmed_mean":
                    est = _trimmed_mean(kept_vals, trim)
                    meta = {"estimate": est, "se": 0.0, "ci": 0.0, "q": 0.0, "i2": 0.0,
                            "tau2": 0.0, "k": len(kept_vals), "method": "trimmed_mean"}
                else:
                    meta = _inverse_variance_meta(kept_pts, conf, i2_thr)
                meta["arithmetic_mean"] = _mean(kept_vals)
                meta["median_of_providers"] = _median(kept_vals)
                meta["min"] = min(kept_vals)
                meta["max"] = max(kept_vals)
                meta["outlier_providers"] = sorted(
                    {[e["key"] for e in results if e.get(direction)
                      and e[direction]["ok"]][i] for i in bad}) if bad else []
                return meta

            down_meta = _pool("download") if action in ("full", "download") else None
            up_meta = _pool("upload") if action in ("full", "upload") else None

            lat_all = [e["latency"] for e in results if e.get("latency") and e["latency"]["ok"]]
            lat_min = min((x["min"] for x in lat_all), default=0.0)
            lat_med = _median([x["median"] for x in lat_all]) if lat_all else 0.0
            jitter = _median([x["jitter"] for x in lat_all]) if lat_all else 0.0
            loss = _mean([x["loss_pct"] for x in lat_all]) if lat_all else 0.0
            bloats = [e["bufferbloat_ms"] for e in results if e.get("bufferbloat_ms") is not None]
            bloat = _median(bloats) if bloats else 0.0

            isp = next((e["isp"] for e in results if e.get("isp")), "")
            cip = next((e["client_ip"] for e in results if e.get("client_ip")), "")
            loc = "; ".join(f"{e['key']}={e['location']}" for e in results if e.get("location"))

            n_ok = len(results)
            outcome.update({
                "providers_ok": n_ok,
                "providers_failed": len(failures),
                "latency_ms": _fmt(lat_min),
                "jitter_ms": _fmt(jitter),
                "packet_loss_pct": _fmt(loss, 2),
                "bufferbloat_ms": _fmt(bloat),
                "bufferbloat_grade": _bufferbloat_grade(bloat) if bloats else "n/a",
                "samples": sum((e["download"]["n"] if e.get("download") else 0)
                               + (e["upload"]["n"] if e.get("upload") else 0) for e in results),
                "isp": isp or "(unknown)",
                "client_ip": cip or "(unknown)",
                "server_location": loc[:400],
                "stage": "fusion",
            })
            if down_meta:
                outcome["download_mbps"] = _fmt(down_meta["estimate"])
                outcome["download_ci95"] = _fmt(down_meta["ci"])
                outcome["heterogeneity_i2"] = _fmt(down_meta["i2"], 1)
                outcome["aggregation"] = down_meta["method"]
            if up_meta:
                outcome["upload_mbps"] = _fmt(up_meta["estimate"])
                outcome["upload_ci95"] = _fmt(up_meta["ci"])
                if not down_meta:
                    outcome["aggregation"] = up_meta["method"]

            # ---------------- verdict (honest, never flattering) ----------------
            if action == "validate":
                outcome.update({"status": "validated", "success": "true", "stage": "validate"})
            elif n_ok == 0:
                outcome.update({"status": "unreachable", "success": "false", "stage": "measure"})
            elif n_ok < min_ok:
                outcome.update({"status": "partial", "success": "false", "stage": "measure"})
            else:
                outcome.update({"status": "ok", "success": "true", "stage": "complete"})

            # ---------------- the human report ----------------
            L = []
            L.append("═" * 78)
            L.append("  NetSpeed-Calculator — Internet throughput measurement report")
            L.append("  " + datetime.now().strftime("%Y-%m-%d %H:%M:%S") +
                     "   ·   action=%s" % action)
            L.append("═" * 78)
            L.append("")
            L.append("CLIENT      ISP: %s    public IP: %s" % (isp or "(unknown)", cip or "(unknown)"))
            L.append("PROVIDERS   %d/%d responded (keyless, no login): %s"
                     % (n_ok, len(providers), ", ".join(e["key"] for e in results) or "(none)"))
            if failures:
                for k, why in failures:
                    L.append("            ✗ %-11s %s" % (k, why))
            L.append("")
            L.append("─── HEADLINE ────────────────────────────────────────────────────────────")
            if down_meta:
                L.append("  ⬇ DOWNLOAD   %10s Mbps   (95%% CI ±%s)   = %s MiB/s"
                         % (_fmt(down_meta["estimate"]), _fmt(down_meta["ci"]),
                            _fmt(down_meta["estimate"] * 1e6 / 8.0 / 1048576.0)))
            if up_meta:
                L.append("  ⬆ UPLOAD     %10s Mbps   (95%% CI ±%s)   = %s MiB/s"
                         % (_fmt(up_meta["estimate"]), _fmt(up_meta["ci"]),
                            _fmt(up_meta["estimate"] * 1e6 / 8.0 / 1048576.0)))
            L.append("  ⏱ LATENCY    %10s ms (min/idle)   median %s ms   jitter %s ms (RFC 3550)"
                     % (_fmt(lat_min), _fmt(lat_med), _fmt(jitter)))
            L.append("  📉 LOSS       %10s %%   (TCP-handshake failure proxy)" % _fmt(loss, 2))
            if bloats:
                L.append("  🌊 BUFFERBLOAT %8s ms added under load   → grade %s"
                         % (_fmt(bloat), _bufferbloat_grade(bloat)))
            L.append("")
            L.append("─── PER-PROVIDER ────────────────────────────────────────────────────────")
            L.append("  %-11s %12s %12s %9s %9s  %s"
                     % ("provider", "down Mbps", "up Mbps", "RTT ms", "CV %", "server"))
            for e in results:
                d = e.get("download") or {}
                u = e.get("upload") or {}
                lt = e.get("latency") or {}
                L.append("  %-11s %12s %12s %9s %9s  %s"
                         % (e["key"],
                            _fmt(d.get("mbps", 0.0)) if d.get("ok") else "—",
                            _fmt(u.get("mbps", 0.0)) if u.get("ok") else "—",
                            _fmt(lt.get("min", 0.0)) if lt.get("ok") else "—",
                            _fmt(d.get("cv_pct", 0.0), 1) if d.get("ok") else "—",
                            (e.get("location") or "")[:34]))
            L.append("")
            L.append("─── METHOD & DIAGNOSTICS ────────────────────────────────────────────────")
            L.append("  Standard        RFC 6349 (TCP throughput) · RFC 3550 §6.4.1 (jitter)")
            L.append("  Streams         %d concurrent TCP flows per provider per direction" % streams)
            L.append("  Window          %.1f s steady state, first %.1f s (slow-start ramp) DISCARDED"
                     % (duration, warmup))
            L.append("  Sampling        d(bytes)/dt every %.2f s — never total/elapsed" % interval)
            L.append("  Outliers        %s%s" % (
                {"tukey": "Tukey IQR fences (k=1.5)",
                 "mad": "Iglewicz-Hoaglin modified z-score (MAD, 3.5)",
                 "none": "disabled"}.get(method, method),
                "" if method == "none" else "; then %.0f%% symmetric trimmed mean" % trim))
            L.append("  Interval        Student-t (not normal z) at %.0f%% — n is small" % (conf * 100))
            for meta, name in ((down_meta, "download"), (up_meta, "upload")):
                if not meta:
                    continue
                L.append("  Fusion (%-8s) %s over k=%d provider(s)"
                         % (name + ")", meta["method"], meta["k"]))
                L.append("      Cochran Q=%s   I²=%s%%   τ²=%s   |   plain mean %s · median %s · "
                         "range %s–%s Mbps"
                         % (_fmt(meta["q"], 2), _fmt(meta["i2"], 1), _fmt(meta["tau2"], 3),
                            _fmt(meta["arithmetic_mean"]), _fmt(meta["median_of_providers"]),
                            _fmt(meta["min"]), _fmt(meta["max"])))
                if meta["i2"] > i2_thr:
                    L.append("      ⚠ I² > %.0f%%: providers genuinely DISAGREE (different CDNs / "
                             "peering), so random-effects widened the interval on purpose."
                             % i2_thr)
                if meta.get("outlier_providers"):
                    L.append("      ⚠ excluded as cross-provider outlier(s): %s"
                             % ", ".join(meta["outlier_providers"]))
            if down_meta and lat_min > 0:
                bdp = _bdp_bytes(down_meta["estimate"], lat_min)
                L.append("  BDP             %s in flight needed to fill this path "
                         "(BW × RTT) — %s" % (
                             _human_bytes(bdp),
                             "one TCP stream cannot do it; multi-stream was REQUIRED"
                             if bdp > 262144 else "within a normal receive window"))
                if loss > 0:
                    ceiling = _mathis_ceiling_mbps(lat_min, loss / 100.0)
                    L.append("  Mathis bound    ~%s Mbps for a SINGLE loss-based flow "
                             "(MSS/(RTT·√p)) at the observed loss" % _fmt(ceiling))
            if pf.get("warnings"):
                L.append("")
                L.append("─── PREFLIGHT WARNINGS ──────────────────────────────────────────────────")
                for w in pf["warnings"]:
                    L.append("  ⚠ " + w)
            L.append("")
            L.append("  Units: Mbps = 10⁶ bits/s (the ISP convention). MiB/s = 2²⁰ bytes/s.")
            L.append("  AUTHORIZED USE: this consumes real, possibly metered bandwidth.")
            L.append("═" * 78)
            body = "\n".join(L)

            # ---------------- artifacts ----------------
            if save_json and action != "providers":
                try:
                    out_dir = _default_output_dir(config)
                    os.makedirs(out_dir, exist_ok=True)
                    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    jpath = os.path.join(out_dir, f"netspeed_{stamp}.json")
                    with open(jpath, "w", encoding="utf-8") as fh:
                        json.dump({
                            "generated_at": datetime.now().isoformat(timespec="seconds"),
                            "action": action, "config_used": {
                                "providers": providers, "parallel_streams": streams,
                                "test_duration_seconds": duration, "warmup_seconds": warmup,
                                "sample_interval_seconds": interval,
                                "outlier_rejection": method, "trim_percent": trim,
                                "confidence_level": conf, "aggregation": agg,
                            },
                            "summary": outcome, "download": down_meta, "upload": up_meta,
                            "latency": {"min_ms": lat_min, "median_ms": lat_med,
                                        "jitter_ms": jitter, "loss_pct": loss,
                                        "bufferbloat_ms": bloat},
                            "providers": results,
                            "failures": [{"provider": k, "reason": w} for k, w in failures],
                            "preflight": pf,
                        }, fh, indent=2, default=str)
                    outcome["json_path"] = jpath
                    rpath = os.path.join(out_dir, f"netspeed_{stamp}.txt")
                    with open(rpath, "w", encoding="utf-8") as fh:
                        fh.write(body)
                    logging.info(f"💾 Result saved: {jpath}")
                except Exception as exc:
                    logging.warning(f"⚠️ Could not save the result artifact: {exc}")

        # ---------- emit + trigger ----------
        _emit_section(outcome, body or "(no output)")

        if outcome["success"] == "true":
            logging.info("🏁 NetSpeed-Calculator %s complete: status=%s  ⬇%s Mbps  ⬆%s Mbps"
                         % (action, outcome["status"], outcome["download_mbps"],
                            outcome["upload_mbps"]))
        else:
            logging.warning("⚠️ NetSpeed-Calculator %s did not fully succeed (status=%s, stage=%s)."
                            % (action, outcome["status"], outcome["stage"]))

        # THE COMPLETE CALCULATION IS DONE. Only now may downstream agents be raised —
        # every one of them can read the final, fused numbers from the section above.
        total_triggered = 0
        if target_agents:
            wait_for_agents_to_stop(target_agents)
            logging.info(f"🚀 Calculation COMPLETE — now triggering {len(target_agents)} downstream agents...")
            for target in target_agents:
                if start_agent(target):
                    total_triggered += 1

        logging.info("🏁 NetSpeed-Calculator agent finished. Triggered %d/%d agents."
                     % (total_triggered, len(target_agents)))
    finally:
        time.sleep(0.4)  # Keep LED green briefly
        remove_pid_file()

    sys.exit(0)


if __name__ == "__main__":
    main()
