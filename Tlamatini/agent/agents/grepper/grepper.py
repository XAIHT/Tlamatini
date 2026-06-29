# ═══════════════════════════════════════════════════════════════════
#   ✦  T L A M A T I N I  ✦   —   "one who knows"
#
#   Crafted with heart by  Angela   ·   @angelahack1
#   Developer · Architect · Creator of Tlamatini
#
#   Every line of this file was written by Angela.
# ═══════════════════════════════════════════════════════════════════
#   Tlamatini Author Banner — do not remove (releases scrub the name automatically)
# Grepper Agent - Read-only regex content search across a file or directory tree
# Action: Triggered by upstream -> search -> emit INI_SECTION_GREPPER -> Trigger downstream (always) -> Exit

import os
import sys

# FIX: Disable Intel Fortran runtime Ctrl+C handler
os.environ['FOR_DISABLE_CONSOLE_CTRL_HANDLER'] = '1'

import time
import yaml
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


def load_config(path="config.yaml") -> dict:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)
    except FileNotFoundError:
        logging.error(f"Error: {path} not found.")
        sys.exit(1)
    except Exception as e:
        logging.error(f"Error parsing {path}: {e}")
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
                f"WAITING FOR AGENTS TO STOP: {still_running} still running "
                f"after {int(waited)}s. Will keep waiting..."
            )
            waited = 0.0
        time.sleep(poll_interval)
        waited += poll_interval


def start_agent(agent_name: str) -> bool:
    agent_dir = get_agent_directory(agent_name)
    script_path = get_agent_script_path(agent_name)
    if not os.path.exists(script_path):
        logging.error(f"Agent script not found: {script_path}")
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
            logging.error(f"Failed to write PID file for target {agent_name}: {pid_err}")
        logging.info(f"Started agent '{agent_name}' with PID: {process.pid}")
        return True
    except Exception as e:
        logging.error(f"Failed to start agent '{agent_name}': {e}")
        return False


# PID Management
PID_FILE = "agent.pid"


def write_pid_file():
    try:
        with open(PID_FILE, "w") as f:
            f.write(str(os.getpid()))
    except Exception as e:
        logging.error(f"Failed to write PID file: {e}")


def remove_pid_file():
    for attempt in range(5):
        try:
            if os.path.exists(PID_FILE):
                os.remove(PID_FILE)
            return
        except PermissionError:
            time.sleep(0.1)
        except Exception as e:
            logging.error(f"Failed to remove PID file: {e}")
            return


def _coerce_int(value, default):
    """Robustly coerce a yaml int OR a wrapped-parser string to int (never raises)."""
    try:
        return int(str(value).strip().split()[0])
    except (ValueError, IndexError, AttributeError, TypeError):
        return default


def _coerce_bool(value, default=False):
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    s = str(value).strip().lower()
    if s in ('true', '1', 'yes', 'y', 'on'):
        return True
    if s in ('false', '0', 'no', 'n', 'off', ''):
        return False
    return default


# Directories that are pruned from a recursive walk (noise / huge / VCS).
_PRUNE_DIRS = {'.git', 'node_modules', 'venv', '.venv', '__pycache__',
               'staticfiles', 'dist', 'build', '.mypy_cache', '.ruff_cache'}


def _iter_files(path, glob_pat):
    import fnmatch
    if os.path.isfile(path):
        if not glob_pat or fnmatch.fnmatch(os.path.basename(path), glob_pat):
            yield path
        return
    for root, dirs, files in os.walk(path):
        dirs[:] = [d for d in dirs if d not in _PRUNE_DIRS]
        for name in files:
            if not glob_pat or fnmatch.fnmatch(name, glob_pat):
                yield os.path.join(root, name)


def emit_grepper_section(pattern, path, glob_pat, matches, files_searched, truncated, status, body):
    logging.info(
        "INI_SECTION_GREPPER<<<\n"
        f"pattern: {pattern}\n"
        f"path: {path}\n"
        f"glob: {glob_pat}\n"
        f"matches: {matches}\n"
        f"files_searched: {files_searched}\n"
        f"truncated: {truncated}\n"
        f"status: {status}\n"
        "\n"
        f"{body}\n"
        ">>>END_SECTION_GREPPER"
    )


def main():
    import re
    config = load_config()
    write_pid_file()
    if _IS_REANIMATED:
        logging.info(f"\U0001f504 {CURRENT_DIR_NAME} REANIMATED (resuming from pause)")
        logging.info("=" * 60)
    try:
        pattern = config.get('pattern', '')
        pattern = pattern if isinstance(pattern, str) else str(pattern)
        path = str(config.get('path', '') or '').strip()
        glob_pat = str(config.get('glob', '') or '').strip()
        case_insensitive = _coerce_bool(config.get('case_insensitive', False))
        output_mode = str(config.get('output_mode', 'content') or 'content').strip().lower()
        max_results = _coerce_int(config.get('max_results', 200), 200)
        target_agents = config.get('target_agents', []) or []

        logging.info("\U0001f50d GREPPER AGENT STARTED")
        logging.info(f"\U0001f9ea pattern={pattern!r} path={path!r} glob={glob_pat!r} mode={output_mode}")
        logging.info(f"\U0001f3af Targets: {target_agents}")

        status = "error"
        matches = 0
        files_searched = 0
        truncated = False
        body = ""
        try:
            if not pattern:
                body = "No pattern configured."
                logging.error(f"❌ {body}")
            elif not path or not os.path.exists(path):
                status = "not_found"
                body = f"Path not found: {path}"
                logging.error(f"❌ {body}")
            else:
                try:
                    rx = re.compile(pattern, re.IGNORECASE if case_insensitive else 0)
                except re.error as rex:
                    body = f"Invalid regex: {rex}"
                    logging.error(f"❌ {body}")
                    rx = None
                if rx is not None:
                    content_lines = []
                    file_match_counts = {}
                    for fpath in _iter_files(path, glob_pat):
                        try:
                            with open(fpath, "r", encoding="utf-8", errors="strict") as f:
                                lines = f.readlines()
                        except (UnicodeDecodeError, OSError, PermissionError):
                            continue  # skip binary / unreadable
                        files_searched += 1
                        for i, line in enumerate(lines):
                            if rx.search(line):
                                matches += 1
                                file_match_counts[fpath] = file_match_counts.get(fpath, 0) + 1
                                if output_mode == "content":
                                    content_lines.append(f"{fpath}:{i + 1}:{line.rstrip()}")
                                if matches >= max_results:
                                    truncated = True
                                    break
                        if truncated:
                            break
                    if output_mode == "files":
                        body = "\n".join(sorted(file_match_counts.keys()))
                    elif output_mode == "count":
                        body = "\n".join(f"{c}\t{fp}" for fp, c in sorted(file_match_counts.items()))
                    else:
                        body = "\n".join(content_lines)
                    status = "matches" if matches else "no_matches"
                    if truncated:
                        body += f"\n... (truncated at max_results={max_results})"
                    logging.info(f"✅ {matches} match(es) across {files_searched} file(s); status={status}")
        except Exception as e:
            status = "error"
            body = f"Search failed: {e}"
            logging.error(f"❌ {body}")

        emit_grepper_section(pattern, path, glob_pat, matches, files_searched, truncated, status, body)

        total_triggered = 0
        if target_agents:
            wait_for_agents_to_stop(target_agents)
            for target in target_agents:
                if start_agent(target):
                    total_triggered += 1

        logging.info(
            f"\U0001f3c1 Grepper agent finished. Status: {status}. "
            f"Triggered {total_triggered}/{len(target_agents)} agents."
        )
    finally:
        time.sleep(0.4)
        remove_pid_file()
    sys.exit(0)


if __name__ == "__main__":
    main()
