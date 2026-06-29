# ═══════════════════════════════════════════════════════════════════
#   ✦  T L A M A T I N I  ✦   —   "one who knows"
#
#   Crafted with heart by  Angela   ·   @angelahack1
#   Developer · Architect · Creator of Tlamatini
#
#   Every line of this file was written by Angela.
# ═══════════════════════════════════════════════════════════════════
#   Tlamatini Author Banner — do not remove (releases scrub the name automatically)
# Keyboarder Agent - Issues keyboard sequences simulating the user pressing keys

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

try:
    import pyautogui
    pyautogui.FAILSAFE = False
except ImportError:
    pass

# Set working directory to script location
try:
    script_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(script_dir)
except Exception as e:
    sys.stderr.write(f"Critical Error: Failed to set working directory: {e}\n")

# Use directory name for log file
CURRENT_DIR_NAME = os.path.basename(os.path.dirname(os.path.abspath(__file__)))
LOG_FILE_PATH = f"{CURRENT_DIR_NAME}.log"

_IS_REANIMATED = os.environ.get('AGENT_REANIMATED') == '1'
if not _IS_REANIMATED:
    open(LOG_FILE_PATH, 'w').close()

logging.basicConfig(
    filename=LOG_FILE_PATH, level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s', encoding='utf-8'
)
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
console_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
logging.getLogger().addHandler(console_handler)

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
            logging.error(f"❌ WAITING FOR AGENTS TO STOP: {still_running} still running after {int(waited)}s. Will keep waiting...")
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

def split_sequence(seq_str):
    """Tokenize a Keyboarder ``input_sequence`` into ``[(type, value), ...]``.

    The format is comma-separated tokens; quoted tokens (``'foo bar'`` or
    ``"foo bar"``) are typed literally, unquoted tokens are key-press
    commands (``enter``, ``ctrl+s``).

    **Apostrophe / quote escaping inside a quoted literal:**

    * SQL / YAML-single-quoted style: ``''`` decodes to ``'`` inside a
      single-quoted literal, ``""`` decodes to ``"`` inside a double-quoted
      one (so ``'Hi, I''m Tlamatini'`` types ``Hi, I'm Tlamatini``).
    * Backslash style: ``\\'`` decodes to ``'`` and ``\\"`` to ``"`` (so
      ``'Hi, I\\'m Tlamatini'`` is equivalent).

    **Robust fallback:** if a tokenization yields exactly one unquoted token
    and that token isn't a recognized key / ``+``-chord of recognized keys,
    treat the entire raw input as a literal string and type it. This makes
    the agent forgiving when an LLM forgets the quotes around literal text
    (``Hi!, I'm Tlamatini`` types literally instead of being parsed as
    ``Hi!`` + ``I'm Tlamatini``, which would silently no-op).
    """
    # Pass 1 — comma-split, tracking which quote (if any) is active and
    # honouring backslash + SQL-doubling escapes. The "is this quote a
    # closer or an internal apostrophe?" disambiguation mirrors the
    # wrapper's ``_closes_outer_quote`` heuristic: a quote char inside a
    # quoted literal is a closer ONLY if it is followed (after optional
    # whitespace) by a comma or end-of-input. Otherwise it's an internal
    # apostrophe — common in ``'Hi!, I'm Tlamatini'`` — and the state
    # stays open. Without this, the closing ``'`` toggles the state back
    # on after the internal one, swallowing the rest of the sequence.
    raw_tokens = []
    current = []
    in_single = False
    in_double = False
    escape_next = False
    n = len(seq_str)
    i = 0

    def _is_quote_closer(idx, quote_char):
        probe = idx + 1
        while probe < n and seq_str[probe] in (' ', '\t'):
            probe += 1
        if probe >= n:
            return True
        return seq_str[probe] == ','

    while i < n:
        char = seq_str[i]
        if escape_next:
            current.append(char)
            escape_next = False
            i += 1
            continue
        if char == '\\' and (in_single or in_double):
            current.append(char)
            escape_next = True
            i += 1
            continue
        if char == "'" and not in_double:
            # SQL-style ``''`` doubling collapses to one literal apostrophe
            # WITHOUT toggling the quote state.
            if in_single and i + 1 < n and seq_str[i + 1] == "'":
                current.append("'")
                current.append("'")
                i += 2
                continue
            if in_single and not _is_quote_closer(i, "'"):
                # Internal apostrophe (e.g. in ``I'm``); stay inside the
                # literal so the matching closing ``'`` lands the token.
                current.append("'")
                i += 1
                continue
            in_single = not in_single
            current.append(char)
            i += 1
            continue
        if char == '"' and not in_single:
            if in_double and i + 1 < n and seq_str[i + 1] == '"':
                current.append('"')
                current.append('"')
                i += 2
                continue
            if in_double and not _is_quote_closer(i, '"'):
                current.append('"')
                i += 1
                continue
            in_double = not in_double
            current.append(char)
            i += 1
            continue
        if char == ',' and not in_single and not in_double:
            raw_tokens.append("".join(current).strip())
            current = []
            i += 1
            continue
        current.append(char)
        i += 1
    if current:
        raw_tokens.append("".join(current).strip())

    parsed = []
    for token in raw_tokens:
        if not token:
            continue
        if (token.startswith("'") and token.endswith("'") and len(token) >= 2) or \
           (token.startswith('"') and token.endswith('"') and len(token) >= 2):
            outer = token[0]
            inner = token[1:-1]
            inner = _decode_literal_escapes(inner, outer)
            parsed.append(('string', inner))
            continue
        keys = [k.strip().lower() for k in token.split('+') if k.strip()]
        if keys:
            parsed.append(('keys', keys))

    # Robust fallback: a single unquoted token that doesn't resolve to known
    # keys becomes a literal string. Also covers the LLM-forgot-the-quotes
    # case (``Hi!, I'm Tlamatini`` arrives unquoted; without this, every
    # token would silently no-op on press()).
    if len(parsed) >= 1 and all(t == 'keys' for t, _ in parsed):
        unrecognized = any(
            not _all_keys_recognized(value)
            for kind, value in parsed
            if kind == 'keys'
        )
        if unrecognized:
            return [('string', seq_str.strip())]

    return parsed


def _decode_literal_escapes(inner, outer_quote):
    """Decode ``''`` / ``""`` and ``\\'`` / ``\\"`` inside a quoted literal."""
    if not inner:
        return inner
    out = []
    i = 0
    n = len(inner)
    while i < n:
        char = inner[i]
        if char == '\\' and i + 1 < n:
            nxt = inner[i + 1]
            if nxt == outer_quote or nxt == '\\':
                out.append(nxt)
                i += 2
                continue
        if char == outer_quote and i + 1 < n and inner[i + 1] == outer_quote:
            out.append(outer_quote)
            i += 2
            continue
        out.append(char)
        i += 1
    return ''.join(out)


# Set of pyautogui-recognized key names (lowercased). Used by the robust
# fallback in split_sequence to decide whether an unquoted token is a real
# key or just a piece of literal text the LLM forgot to quote.
_RECOGNIZED_KEYS: set = {
    'a','b','c','d','e','f','g','h','i','j','k','l','m','n','o','p','q','r','s',
    't','u','v','w','x','y','z',
    '0','1','2','3','4','5','6','7','8','9',
    'enter','return','tab','space','spacebar','backspace','del','delete','esc',
    'escape','home','end','pageup','pagedown','pgup','pgdn','insert','ins',
    'up','down','left','right',
    'f1','f2','f3','f4','f5','f6','f7','f8','f9','f10','f11','f12',
    'shift','shiftleft','shiftright','ctrl','ctrlleft','ctrlright','control',
    'alt','altleft','altright','altgr','win','winleft','winright','windows',
    'window','command','option','meta','fn','capslock','caps','mayus','mayuscula',
    'numlock','scrolllock','printscreen','pause','apps',
    '<-(left arrow)','->(right arrow)','down arrow','up arrow',
}


def _all_keys_recognized(keys):
    """Return True if every key in ``keys`` is a recognized key name."""
    for k in keys:
        if k.strip().lower() not in _RECOGNIZED_KEYS:
            return False
    return True


def get_pyautogui_key(key):
    """Normalize key names"""
    key_map = {
        'control': 'ctrl',
        'mayus': 'capslock',
        'mayuscula': 'capslock',
        'caps': 'capslock',
        '<-(left arrow)': 'left',
        '->(right arrow)': 'right',
        'down arrow': 'down',
        'up arrow': 'up',
        'enter': 'enter',
        'escape': 'esc',
        'windows': 'win',
        'window': 'win',
        'altgr': 'altright',
    }
    return key_map.get(key, key)

def main():
    config = load_config()
    write_pid_file()
    
    if _IS_REANIMATED:
        logging.info(f"🔄 {CURRENT_DIR_NAME} REANIMATED (resuming from pause)")
        logging.info("=" * 60)

    try:
        target_agents = config.get('target_agents', [])
        input_sequence = config.get('input_sequence', "")
        stride_delay = config.get('stride_delay', 50)
        
        logging.info("⌨️ KEYBOARDER AGENT STARTED")
        logging.info(f"⚡ Input Sequence: {input_sequence}")
        
        if 'pyautogui' not in sys.modules:
            logging.error("❌ pyautogui module not found. Please 'pip install pyautogui'")
        else:
            parsed_cmds = split_sequence(input_sequence)
            delay_sec = stride_delay / 1000.0
            for type_val, value in parsed_cmds:
                if type_val == 'string':
                    logging.info(f"   Typing literal string: '{value}'")
                    pyautogui.write(value, interval=0.01)
                elif type_val == 'keys':
                    norm_keys = [get_pyautogui_key(k) for k in value]
                    logging.info(f"   Executing keys: {norm_keys}")
                    try:
                        if len(norm_keys) == 1:
                            pyautogui.press(norm_keys[0])
                        else:
                            pyautogui.hotkey(*norm_keys)
                    except Exception as e:
                        logging.error(f"❌ Error pressing keys {norm_keys}: {e}")
                time.sleep(delay_sec)
                
            logging.info("✅ Key Sequence completed.")
        
        # Trigger downstream agents
        total_triggered = 0
        if target_agents:
            wait_for_agents_to_stop(target_agents)
            logging.info(f"🚀 Triggering {len(target_agents)} downstream agents...")
            for target in target_agents:
                if start_agent(target):
                    total_triggered += 1

        logging.info(f"🏁 Keyboarder agent finished. Triggered {total_triggered}/{len(target_agents)} agents.")
    finally:
        time.sleep(0.4)
        remove_pid_file()

    sys.exit(0)

if __name__ == "__main__":
    main()
