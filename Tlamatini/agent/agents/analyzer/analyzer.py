# Analyzer Agent - deterministic static-analysis / security scanner
# Action: Triggered by upstream -> run every installed scanner over
# target_path -> aggregate findings -> emit INI_SECTION_ANALYZER ->
# trigger downstream agents (always, so flows can route on `status`).
#
# Self-contained: does NOT import from agent.* — pool subprocesses run as
# separate Python interpreters with no path back into the Django app.
# No LLM is used; the output is reproducible.

import os
import sys

# FIX: Disable Intel Fortran runtime Ctrl+C handler
os.environ['FOR_DISABLE_CONSOLE_CTRL_HANDLER'] = '1'

import time
import yaml
import json
import shutil
import logging
import subprocess

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
from typing import Dict

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


# ========================================
# HELPER FUNCTIONS (from shoter.py boilerplate)
# ========================================

def load_config(path: str = "config.yaml") -> Dict:
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


# PID Management
PID_FILE = "agent.pid"


def write_pid_file():
    try:
        with open(PID_FILE, "w") as f:
            f.write(str(os.getpid()))
    except Exception as e:
        logging.error(f"❌ Failed to write PID file: {e}")


def remove_pid_file():
    for _ in range(5):
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
# SCANNER ADAPTERS
# ========================================
#
# Each scanner is best-effort: it runs only if its executable resolves on
# PATH, captures stdout even on a non-zero exit (these tools exit non-zero
# precisely because they found issues), and reports a finding count plus
# the raw output. Counting is heuristic — JSON where the tool offers it,
# line/marker counts otherwise — so the agent never hard-depends on a
# specific tool version's schema.

SUPPORTED_TOOLS = ("ruff", "bandit", "semgrep", "eslint", "gitleaks", "pip-audit")


def _which(name: str) -> str:
    return shutil.which(name) or ""


def _run(cmd: list, timeout: int = 180) -> tuple:
    """Run a scanner. Returns (returncode, stdout, stderr)."""
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
        return proc.returncode, proc.stdout or "", proc.stderr or ""
    except FileNotFoundError:
        return 127, "", f"{cmd[0]} not found"
    except subprocess.TimeoutExpired:
        return 124, "", f"{cmd[0]} timed out after {timeout}s"
    except Exception as e:
        return 1, "", str(e)


def _count_json_list(text: str, key: str = "") -> int:
    """Count items in a JSON array, or in obj[key] when key is given."""
    try:
        data = json.loads(text)
    except Exception:
        return -1
    if key:
        if isinstance(data, dict) and isinstance(data.get(key), list):
            return len(data[key])
        return -1
    if isinstance(data, list):
        return len(data)
    return -1


def scan_ruff(target: str) -> dict:
    rc, out, err = _run([_which("ruff"), "check", target, "--output-format", "json"])
    count = _count_json_list(out)
    return {"tool": "ruff", "count": count, "rc": rc, "output": out or err}


def scan_bandit(target: str) -> dict:
    rc, out, err = _run([_which("bandit"), "-r", target, "-f", "json"])
    count = _count_json_list(out, key="results")
    return {"tool": "bandit", "count": count, "rc": rc, "output": out or err}


def scan_semgrep(target: str) -> dict:
    rc, out, err = _run(
        [_which("semgrep"), "--config", "auto", "--json", "--quiet", target],
        timeout=300,
    )
    count = _count_json_list(out, key="results")
    return {"tool": "semgrep", "count": count, "rc": rc, "output": out or err}


def scan_eslint(target: str) -> dict:
    rc, out, err = _run([_which("eslint"), target, "-f", "json"])
    count = -1
    try:
        data = json.loads(out)
        if isinstance(data, list):
            count = sum(len(f.get("messages", [])) for f in data if isinstance(f, dict))
    except Exception:
        count = -1
    return {"tool": "eslint", "count": count, "rc": rc, "output": out or err}


def scan_gitleaks(target: str) -> dict:
    # gitleaks exits 1 when leaks are found; capture verbose stdout and
    # count the per-finding markers.
    rc, out, err = _run([_which("gitleaks"), "detect", "--source", target, "--no-banner", "-v"])
    blob = out or err
    count = blob.count("Finding:") if blob else -1
    return {"tool": "gitleaks", "count": count, "rc": rc, "output": blob}


def scan_pip_audit(target: str) -> dict:
    # Prefer a requirements file inside target; otherwise audit the dir.
    req = ""
    if os.path.isdir(target):
        for name in ("requirements.txt", "requirements-dev.txt"):
            candidate = os.path.join(target, name)
            if os.path.exists(candidate):
                req = candidate
                break
    cmd = [_which("pip-audit"), "-f", "json"]
    cmd += ["-r", req] if req else []
    rc, out, err = _run(cmd, timeout=300)
    count = _count_json_list(out, key="dependencies")
    if count == -1:
        count = _count_json_list(out)
    return {"tool": "pip-audit", "count": count, "rc": rc, "output": out or err}


SCANNER_FUNCS = {
    "ruff": scan_ruff,
    "bandit": scan_bandit,
    "semgrep": scan_semgrep,
    "eslint": scan_eslint,
    "gitleaks": scan_gitleaks,
    "pip-audit": scan_pip_audit,
}


def select_tools(requested: list) -> tuple:
    """Return (tools_to_run, unavailable) honoring requested subset / auto."""
    if requested:
        wanted = [str(t).strip().lower() for t in requested if str(t).strip()]
        wanted = [t for t in wanted if t in SUPPORTED_TOOLS]
    else:
        wanted = list(SUPPORTED_TOOLS)
    available = [t for t in wanted if _which(t)]
    unavailable = [t for t in wanted if not _which(t)]
    return available, unavailable


# ========================================
# MAIN
# ========================================

def main():
    config = load_config()
    write_pid_file()
    if _IS_REANIMATED:
        logging.info(f"🔄 {CURRENT_DIR_NAME} REANIMATED (resuming from pause)")
        logging.info("=" * 60)

    try:
        target_path = str(config.get('target_path', '.') or '.')
        requested = config.get('tools', []) or []
        if not isinstance(requested, list):
            requested = [requested]
        min_severity = str(config.get('min_severity', 'low') or 'low')
        max_report_chars = int(config.get('max_report_chars', 60000) or 60000)
        target_agents = config.get('target_agents', []) or []

        logging.info("🛡️ ANALYZER AGENT STARTED")
        logging.info(f"📂 Target: {target_path}")
        logging.info(f"🎯 Targets: {target_agents}")
        logging.info("=" * 60)

        available, unavailable = select_tools(requested)
        if unavailable:
            logging.info(f"⚠️ Scanners not on PATH (skipped): {unavailable}")

        results = []
        total_findings = 0
        any_error = False

        if not os.path.exists(target_path):
            any_error = True
            logging.error(f"❌ target_path does not exist: {target_path}")
        else:
            for tool in available:
                logging.info(f"▶️ Running {tool} on {target_path}...")
                try:
                    result = SCANNER_FUNCS[tool](target_path)
                except Exception as e:
                    result = {"tool": tool, "count": -1, "rc": 1, "output": f"runner error: {e}"}
                results.append(result)
                if result["count"] >= 0:
                    total_findings += result["count"]
                    logging.info(f"   {tool}: {result['count']} finding(s)")
                else:
                    any_error = True
                    logging.warning(f"   {tool}: output could not be parsed (rc={result['rc']})")

        # Determine status.
        if not available and not any_error:
            status = "error"  # nothing could run
        elif any_error and total_findings == 0:
            status = "error"
        elif total_findings > 0:
            status = "findings"
        else:
            status = "clean"

        # Build the human-readable report body.
        report_lines = []
        for r in results:
            count_label = r["count"] if r["count"] >= 0 else "unparsed"
            report_lines.append(f"### {r['tool']} (findings: {count_label}, exit: {r['rc']})")
            snippet = (r["output"] or "").strip()
            report_lines.append(snippet if snippet else "(no output)")
            report_lines.append("")
        if unavailable:
            report_lines.append(f"### skipped (not installed): {', '.join(unavailable)}")
        report_body = "\n".join(report_lines).strip() or "No scanners produced output."
        if len(report_body) > max_report_chars:
            report_body = report_body[:max_report_chars] + "\n...[report truncated]"

        tools_run = ",".join(r["tool"] for r in results)

        # Atomic single-call section emission (parametrizer parser rule:
        # each section must be one logging.info() call).
        logging.info(
            "INI_SECTION_ANALYZER<<<\n"
            f"target_path: {target_path}\n"
            f"tools_run: {tools_run}\n"
            f"tools_skipped: {','.join(unavailable)}\n"
            f"total_findings: {total_findings}\n"
            f"min_severity: {min_severity}\n"
            f"status: {status}\n"
            f"\n"
            f"{report_body}\n"
            ">>>END_SECTION_ANALYZER"
        )
        logging.info(f"📊 Analyzer status={status}, total_findings={total_findings}")

        # Always trigger downstream agents (clean OR findings OR error) so
        # flows can route on the section's status via Parametrizer / Forker.
        total_triggered = 0
        if target_agents:
            wait_for_agents_to_stop(target_agents)
            logging.info(f"🚀 Triggering {len(target_agents)} downstream agents...")
            for target in target_agents:
                if start_agent(target):
                    total_triggered += 1

        logging.info(f"🏁 Analyzer finished. Triggered {total_triggered}/{len(target_agents)} agents.")

    except Exception as e:
        logging.error(f"❌ Analyzer agent error: {e}")
    finally:
        time.sleep(0.4)
        remove_pid_file()

    sys.exit(0)


if __name__ == "__main__":
    main()
