# ═══════════════════════════════════════════════════════════════════
#   ✦  T L A M A T I N I  ✦   —   "one who knows"
#
#   Created by  Angela López Mendoza   ·   @angelahack1
#   Developer · Architect · Creator of Tlamatini
#
#   Every line of this file was written by Angela López Mendoza.
# ═══════════════════════════════════════════════════════════════════
#   Tlamatini Author Banner — do not remove (releases scrub the name automatically)
# Globber Agent - Read-only filename pattern search (find files by glob)
# Action: Triggered by upstream -> glob -> emit INI_SECTION_GLOBBER -> Trigger downstream (always) -> Exit

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


def _safe_mtime(path):
    try:
        return os.path.getmtime(path)
    except OSError:
        return 0.0


def emit_globber_section(pattern, path, matches, truncated, status, body):
    logging.info(
        "INI_SECTION_GLOBBER<<<\n"
        f"pattern: {pattern}\n"
        f"path: {path}\n"
        f"matches: {matches}\n"
        f"truncated: {truncated}\n"
        f"status: {status}\n"
        "\n"
        f"{body}\n"
        ">>>END_SECTION_GLOBBER"
    )


# Machine-noise directories, pruned unless the caller names one.
NOISE_DIRS = ('.git', '__pycache__', '.ruff_cache', '.mypy_cache',
              '.pytest_cache', 'node_modules', 'site-packages')


def _drop_noise(paths, path, pattern):
    """Filter machine-noise directories out of a hidden-inclusive result."""
    asked = ('%s|%s' % (path, pattern)).lower()
    active = [d for d in NOISE_DIRS if d.lower() not in asked]
    if not active:
        return paths
    kept = []
    for p in paths:
        try:
            parts = {seg.lower() for seg in os.path.normpath(p).split(os.sep)}
        except Exception:
            kept.append(p)
            continue
        if any(d in parts for d in active):
            continue
        kept.append(p)
    return kept


# >>> SHARED GLOB HELPERS (keep byte-identical in grepper.py and globber.py) >>>
# fnmatch/glob only know * ? and [..], so before 2026-10-18 a brace set like
# "*.{js,py}" matched NOTHING (the "{" was read literally), and so did a list
# such as "*.py,*.js". Every expansion below is ADDITIVE: the pattern exactly as
# written is always tried first, so nothing that matched before stops matching
# (a '|' list excepted: '|' cannot be part of a Windows file name).
# agent/test_glob_patterns.py checks that both agents carry the same block.
_GLOB_MAX_PATTERNS = 256
_GLOB_WILDCARDS = '*?[{'


def _glob_class_end(text, i):
    """Index of the ']' closing the [character class] opening at text[i], or -1."""
    j = i + 1
    if j < len(text) and text[j] in '!^':
        j += 1
    if j < len(text) and text[j] == ']':
        j += 1
    while j < len(text) and text[j] != ']':
        j += 1
    return j if j < len(text) else -1


def _glob_first_brace_set(text):
    """(start, end, options) of the first expandable {a,b} set, else None.

    A set with no top-level comma ("{x}"), an unbalanced brace and anything
    inside a [character class] stay literal, exactly as in a POSIX shell.
    """
    i = 0
    n = len(text)
    while i < n:
        char = text[i]
        if char == '[':
            end = _glob_class_end(text, i)
            i = end + 1 if end >= 0 else i + 1
            continue
        if char != '{':
            i += 1
            continue
        depth = 0
        cuts = []
        j = i
        close = -1
        while j < n:
            c = text[j]
            if c == '[':
                end = _glob_class_end(text, j)
                if end >= 0:
                    j = end + 1
                    continue
            elif c == '{':
                depth += 1
            elif c == '}':
                depth -= 1
                if depth == 0:
                    close = j
                    break
            elif c == ',' and depth == 1:
                cuts.append(j)
            j += 1
        if close >= 0 and cuts:
            bounds = [i] + cuts + [close]
            options = [text[bounds[k] + 1:bounds[k + 1]] for k in range(len(bounds) - 1)]
            return i, close, options
        i += 1
    return None


def _glob_brace_expand(pattern, limit=_GLOB_MAX_PATTERNS):
    """'src/{a,b}/*.{js,py}' -> the four plain patterns (nested sets too)."""
    out = []
    pending = [pattern]
    while pending and len(out) < limit:
        current = pending.pop(0)
        found = _glob_first_brace_set(current)
        if found is None:
            if current not in out:
                out.append(current)
            continue
        start, end, options = found
        for option in options:
            pending.append(current[:start] + option + current[end + 1:])
        del pending[limit * 4:]
    return out


def _glob_split_top_level(text, separators):
    """Split on separators that sit outside {braces} and [classes]."""
    parts = []
    current = []
    depth = 0
    i = 0
    while i < len(text):
        char = text[i]
        if char == '[':
            end = _glob_class_end(text, i)
            if end >= 0:
                current.append(text[i:end + 1])
                i = end + 1
                continue
        if char == '{':
            depth += 1
        elif char == '}' and depth:
            depth -= 1
        elif char in separators and depth == 0:
            parts.append(''.join(current))
            current = []
            i += 1
            continue
        current.append(char)
        i += 1
    parts.append(''.join(current))
    return parts


def _glob_pattern_list(pattern):
    """'*.py,*.js' / '*.py;*.js' / '*.py|*.js' -> ['*.py', '*.js'].

    '|' can never be part of a Windows file name, so it always separates.
    ',' and ';' CAN be, so they separate only when at least one piece is a
    wildcard pattern ('test*.py,tests.py'); 'a,b.txt' stays one literal name.
    """
    pieces = []
    for chunk in _glob_split_top_level(pattern, '|'):
        chunk = chunk.strip()
        if not chunk:
            continue
        subs = [s.strip() for s in _glob_split_top_level(chunk, ',;')]
        if (len(subs) > 1 and all(subs)
                and any(w in s for s in subs for w in _GLOB_WILDCARDS)):
            pieces.extend(subs)
        else:
            pieces.append(chunk)
    return pieces


def _glob_variants(pattern, limit=_GLOB_MAX_PATTERNS):
    """Every plain glob a pattern stands for, the pattern as written FIRST.

    A '|' list is the one exception: '|' can never be part of a Windows
    file name, so the list as written could never match - only its pieces.
    """
    pattern = str(pattern or '').strip()
    if not pattern:
        return []
    out = [] if len(_glob_split_top_level(pattern, '|')) > 1 else [pattern]
    for piece in _glob_pattern_list(pattern):
        for plain in _glob_brace_expand(piece, limit):
            if plain and plain not in out:
                out.append(plain)
            if len(out) >= limit:
                return out
    return out


def _glob_spec(variant):
    """A variant with '/' separators and no leading './'."""
    spec = variant.replace('\\', '/')
    while spec.startswith('./'):
        spec = spec[2:]
    return spec


def _path_glob_regex(pattern):
    """Regex for a '/'-separated glob, matched against a relative path.

    Same rules as glob.glob(recursive=True, include_hidden=True): '*' and '?'
    stay inside one folder name, a whole '**' segment spans zero or more
    folders, and braces are literal (variants are already expanded).
    """
    import re
    parts = []
    i = 0
    n = len(pattern)
    while i < n:
        char = pattern[i]
        if char == '*':
            j = i
            while j < n and pattern[j] == '*':
                j += 1
            whole = (j - i >= 2 and (i == 0 or pattern[i - 1] == '/')
                     and (j == n or pattern[j] == '/'))
            if whole and j < n:
                parts.append('(?:.*/)?')
                j += 1
            elif whole:
                parts.append('.*')
            else:
                parts.append('[^/]*')
            i = j
        elif char == '?':
            parts.append('[^/]')
            i += 1
        elif char == '[':
            end = _glob_class_end(pattern, i)
            if end < 0:
                parts.append('\\[')
                i += 1
                continue
            body = pattern[i + 1:end]
            if body[:1] == '!':
                body = '^' + body[1:]
            elif body[:1] == '^':
                body = '\\' + body
            parts.append('[' + body.replace('\\', '\\\\') + ']')
            i = end + 1
        else:
            parts.append(re.escape(char))
            i += 1
    return '(?s:' + ''.join(parts) + r')\Z'


def _glob_dir_prefixes(glob_pat, names_anywhere=True):
    """Fixed leading folders of the patterns, so a walk can skip the rest.

    'Tlamatini/agent/test_*.py' -> ['Tlamatini/agent']. None means "walk
    everything, exactly as before": a leading wildcard ('**/x.py'), an
    absolute path, or - when ``names_anywhere`` (Grepper: a bare name matches
    in every folder) - a plain file-name pattern. For Globber a bare name
    only means the top folder, so it adds no prefix at all ([] = no subfolder
    is needed). Measured 2026-10-18 on this repository: a folder glob that
    walked every release copy under Temp in 34 s came back in 0.13 s.
    """
    prefixes = []
    for variant in _glob_variants(glob_pat):
        spec = _glob_spec(variant)
        if spec.startswith('/') or (len(spec) > 1 and spec[1] == ':'):
            return None
        if '/' not in spec:
            if names_anywhere:
                return None
            continue
        fixed = []
        for segment in spec.split('/')[:-1]:
            if not segment or segment in ('.', '..') or any(ch in segment for ch in '*?['):
                break
            fixed.append(segment)
        if not fixed:
            return None
        prefixes.append('/'.join(fixed))
    if os.name == 'nt':
        prefixes = [p.lower() for p in prefixes]
    return prefixes


def _dir_may_match(rel_dir, prefixes):
    """True when a folder (relative, '/'-separated) can still hold a match."""
    if os.name == 'nt':
        rel_dir = rel_dir.lower()
    for prefix in prefixes:
        if rel_dir == prefix or prefix.startswith(rel_dir + '/') or rel_dir.startswith(prefix + '/'):
            return True
    return False
# <<< SHARED GLOB HELPERS <<<


def _glob_walk(path, pattern, variants):
    """ONE walk for every pattern a brace set or a list stands for.

    glob.glob re-walks the whole tree once per pattern: measured 2026-10-18,
    a six-pattern brace set over this repository took 3 minutes. Same rules as
    glob.glob(recursive=True, include_hidden=True): '*' stays in one folder,
    a '**' segment spans folders, files only, names ignore case on Windows.
    Folders that can never match - and machine noise - are not entered.
    """
    import re
    flags = re.IGNORECASE if os.name == 'nt' else 0
    regexes = []
    for variant in variants:
        try:
            regexes.append(re.compile(_path_glob_regex(_glob_spec(variant)), flags))
        except re.error:
            continue
    prefixes = _glob_dir_prefixes(pattern, names_anywhere=False)
    asked = ('%s|%s' % (path, pattern)).lower()
    noise = {d.lower() for d in NOISE_DIRS if d.lower() not in asked}
    found = []
    for root, dirs, files in os.walk(path):
        rel_root = os.path.relpath(root, path).replace('\\', '/')
        rel_root = '' if rel_root == '.' else rel_root + '/'
        dirs[:] = [d for d in dirs if d.lower() not in noise
                   and (prefixes is None or _dir_may_match(rel_root + d, prefixes))]
        for name in files:
            relative = rel_root + name
            if any(rx.match(relative) for rx in regexes):
                found.append(os.path.join(root, name))
    return found


def main():
    import glob as globmod
    config = load_config()
    write_pid_file()
    if _IS_REANIMATED:
        logging.info(f"\U0001f504 {CURRENT_DIR_NAME} REANIMATED (resuming from pause)")
        logging.info("=" * 60)
    try:
        pattern = str(config.get('pattern', '') or '').strip()
        path = str(config.get('path', '') or '').strip()
        sort_by = str(config.get('sort_by', 'mtime') or 'mtime').strip().lower()
        max_results = _coerce_int(config.get('max_results', 500), 500)
        target_agents = config.get('target_agents', []) or []

        logging.info("\U0001f5c2️ GLOBBER AGENT STARTED")
        logging.info(f"\U0001f9ea pattern={pattern!r} path={path!r} sort_by={sort_by}")
        logging.info(f"\U0001f3af Targets: {target_agents}")

        status = "error"
        matches = 0
        truncated = False
        body = ""
        try:
            if not pattern:
                body = "No pattern configured."
                logging.error(f"❌ {body}")
            elif not path or not os.path.isdir(path):
                status = "not_found"
                body = f"Directory not found: {path}"
                logging.error(f"❌ {body}")
            else:
                # One pattern may stand for several (brace sets, lists).
                variants = _glob_variants(pattern)
                if len(variants) > 1:
                    logging.info(f"\U0001f9e9 pattern understood as {len(variants)} glob(s): {variants}")
                if len(variants) > 1 and not any(os.path.isabs(v) for v in variants):
                    # ONE walk for all of them (glob would walk once per pattern).
                    found = _glob_walk(path, pattern, variants)
                else:
                    found = []
                    seen = set()
                    for variant in variants:
                        search = os.path.join(path, variant)
                        recursive = "**" in variant
                        # include_hidden makes dot-directories visible (Python
                        # 3.11+); fall back when unsupported.
                        try:
                            hits = globmod.glob(search, recursive=recursive,
                                                include_hidden=True)
                        except TypeError:
                            hits = globmod.glob(search, recursive=recursive)
                        for hit in hits:
                            key = os.path.normcase(os.path.abspath(hit))
                            if key not in seen:
                                seen.add(key)
                                found.append(hit)
                found = _drop_noise(found, path, pattern)
                files = [f for f in found if os.path.isfile(f)]
                if sort_by == "mtime":
                    files.sort(key=_safe_mtime, reverse=True)
                elif sort_by == "name":
                    files.sort()
                matches = len(files)
                shown = files
                if matches > max_results:
                    shown = files[:max_results]
                    truncated = True
                body = "\n".join(shown)
                if truncated:
                    body += f"\n... (truncated at max_results={max_results})"
                status = "matches" if matches else "no_matches"
                logging.info(f"✅ {matches} file(s) matched; status={status}")
        except Exception as e:
            status = "error"
            body = f"Glob failed: {e}"
            logging.error(f"❌ {body}")

        emit_globber_section(pattern, path, matches, truncated, status, body)

        total_triggered = 0
        if target_agents:
            wait_for_agents_to_stop(target_agents)
            for target in target_agents:
                if start_agent(target):
                    total_triggered += 1

        logging.info(
            f"\U0001f3c1 Globber agent finished. Status: {status}. "
            f"Triggered {total_triggered}/{len(target_agents)} agents."
        )
    finally:
        time.sleep(0.4)
        remove_pid_file()
    sys.exit(0)


if __name__ == "__main__":
    main()
