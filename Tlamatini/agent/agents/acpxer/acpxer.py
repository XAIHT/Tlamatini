# ACPXer Agent - Visual ACPX Session Driver
#
# Brings ACPX mechanics into the visual ACP workflow designer. One ACPXer node
# on the canvas drives one ACPX session lifecycle:
#
#     spawn external coding-agent CLI
#         -> dispatch task on stdin
#             -> drain stdout with transport-aware rule (idle + timeout + grace)
#                 -> harvest transcript + last-assistant text
#                     -> kill child + emit INI_SECTION_ACPXER block
#
# Self-contained: does NOT import from agent.acpx so it runs identically in
# source mode and frozen builds (the agent pool runs as separate Python
# subprocesses with no path back into the Django app). The transcript NDJSON
# format and the transport-aware drain rule are deliberate ports of the
# in-process ACPX runtime so transcripts produced here are consumable by
# acp_transcript / acp_relay if ever needed.
#
# Pipeline contract:
#   - Reads config.yaml (agent_id, command override, task, mode, budgets, cwd)
#   - Default agent_id -> command map covers all built-in ACPX agents
#   - Writes <agent_dir>/transcript.ndjson (one line per direction:in/out event)
#   - Emits ONE atomic INI_SECTION_ACPXER<<< ... >>>END_SECTION_ACPXER block
#     so Parametrizer can pipe agent_id / session_id / transcript_path /
#     last_assistant_text into a downstream ACPXer's task.
#   - Triggers target_agents on completion (always, success or failure).

import os
import sys

# FIX: Disable Intel Fortran runtime Ctrl+C handler (must be FIRST)
os.environ['FOR_DISABLE_CONSOLE_CTRL_HANDLER'] = '1'

import time
import json
import uuid
import yaml
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
from queue import Queue, Empty

# Set working directory to script location
try:
    script_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(script_dir)
except Exception as e:
    sys.stderr.write(f"Critical Error: Failed to set working directory: {e}\n")

CURRENT_DIR_NAME = os.path.basename(os.path.dirname(os.path.abspath(__file__)))
LOG_FILE_PATH = f"{CURRENT_DIR_NAME}.log"
TRANSCRIPT_FILE_PATH = "transcript.ndjson"

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


# ---------------------------------------------------------------------------
# ACPX agent registry mirror (kept in sync with agent/acpx/agent_registry.py)
# ---------------------------------------------------------------------------
#
# Each entry: agent_id -> dict with:
#   command, transport, idle_s, timeout_s, grace_s,
#   prompt_flag (str|None), prompt_subargs (list[str])
#
# transport semantics:
#   - "json-acp":       child speaks one JSON envelope per turn ending
#                       with {"done": true}; idle rule arms only AFTER
#                       first event AND idle window.
#   - "tui-repl":       interactive REPL; idle rule arms after grace +
#                       idle window even with zero events.
#   - "one-shot":       child reads one stdin line then exits; close
#                       stdin after dispatch, drain until exit/timeout.
#   - "oneshot-prompt": fresh process per turn with prompt as a CLI arg
#                       behind ``prompt_flag`` (``-p``, ``--prompt``,
#                       ...); stdin closed immediately, all stdout
#                       captured to EOF. ONLY transport that reliably
#                       captures TUI agents' answers on Windows.

_DEFAULT_REGISTRY = {
    # Oneshot-prompt agents (responses actually captured).
    "claude":   {"command": "claude",   "transport": "oneshot-prompt",
                 "idle_s": 10.0, "timeout_s": 180.0, "grace_s": 2.0,
                 "prompt_flag": "-p", "prompt_subargs": []},
    "codex":    {"command": "codex",    "transport": "oneshot-prompt",
                 "idle_s": 10.0, "timeout_s": 180.0, "grace_s": 2.0,
                 "prompt_flag": None, "prompt_subargs": ["exec"]},
    "cursor":   {"command": "cursor-agent", "transport": "oneshot-prompt",
                 "idle_s": 10.0, "timeout_s": 180.0, "grace_s": 2.0,
                 "prompt_flag": "-p", "prompt_subargs": []},
    "gemini":   {"command": "gemini",   "transport": "oneshot-prompt",
                 "idle_s": 10.0, "timeout_s": 180.0, "grace_s": 2.0,
                 "prompt_flag": "-p", "prompt_subargs": []},
    "qwen":     {"command": "qwen-code", "transport": "oneshot-prompt",
                 "idle_s": 10.0, "timeout_s": 180.0, "grace_s": 2.0,
                 "prompt_flag": "-p", "prompt_subargs": []},
    # ACP-server.
    "tlamatini":{"command": "python -m agent.acpx.self_acp_server",
                 "transport": "json-acp",
                 "idle_s": 6.0, "timeout_s": 45.0, "grace_s": 12.0,
                 "prompt_flag": None, "prompt_subargs": []},
    # Legacy TUI-REPLs (no known one-shot flag yet).
    "kiro":     {"command": "kiro",     "transport": "tui-repl",
                 "idle_s": 2.0, "timeout_s": 8.0, "grace_s": 3.0,
                 "prompt_flag": None, "prompt_subargs": []},
    "kimi":     {"command": "kimi",     "transport": "tui-repl",
                 "idle_s": 2.0, "timeout_s": 8.0, "grace_s": 3.0,
                 "prompt_flag": None, "prompt_subargs": []},
    "iflow":    {"command": "iflow",    "transport": "tui-repl",
                 "idle_s": 2.0, "timeout_s": 8.0, "grace_s": 3.0,
                 "prompt_flag": None, "prompt_subargs": []},
    "kilocode": {"command": "kilocode", "transport": "tui-repl",
                 "idle_s": 2.0, "timeout_s": 8.0, "grace_s": 3.0,
                 "prompt_flag": None, "prompt_subargs": []},
    "opencode": {"command": "opencode", "transport": "tui-repl",
                 "idle_s": 2.0, "timeout_s": 8.0, "grace_s": 3.0,
                 "prompt_flag": None, "prompt_subargs": []},
    "pi":       {"command": "pi",       "transport": "tui-repl",
                 "idle_s": 2.0, "timeout_s": 8.0, "grace_s": 3.0,
                 "prompt_flag": None, "prompt_subargs": []},
    "droid":    {"command": "droid",    "transport": "tui-repl",
                 "idle_s": 2.0, "timeout_s": 8.0, "grace_s": 3.0,
                 "prompt_flag": None, "prompt_subargs": []},
    "copilot":  {"command": "copilot",  "transport": "tui-repl",
                 "idle_s": 2.0, "timeout_s": 8.0, "grace_s": 3.0,
                 "prompt_flag": None, "prompt_subargs": []},
}


def load_config(path: str = "config.yaml") -> dict:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except FileNotFoundError:
        logging.error(f"❌ Error: {path} not found.")
        sys.exit(1)
    except Exception as e:
        logging.error(f"❌ Error parsing {path}: {e}")
        sys.exit(1)


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
        still_running = [n for n in agent_names if is_agent_running(n)]
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


def get_python_command() -> list:
    if not getattr(sys, 'frozen', False):
        return [sys.executable]
    python_home = get_user_python_home()
    if python_home:
        py = os.path.join(python_home, 'python.exe' if sys.platform.startswith('win') else 'python3')
        if os.path.exists(py):
            return [py]
    if sys.platform.startswith('win'):
        bundled = os.path.join(os.path.dirname(sys.executable), 'python.exe')
        if os.path.exists(bundled):
            return [bundled]
        return ['python']
    return ['python3']


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
            parts = env.get('PATH', '').split(os.pathsep)
            parts = [p for p in parts if os.path.normpath(p) != os.path.normpath(meipass)]
            env['PATH'] = os.pathsep.join(parts)
    python_home = get_user_python_home()
    if python_home:
        env['PYTHON_HOME'] = python_home
        scripts = os.path.join(python_home, 'Scripts')
        env['PATH'] = f"{python_home};{scripts};{env.get('PATH', '')}"
    return env


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
            with open(os.path.join(agent_dir, "agent.pid"), "w") as f:
                f.write(str(process.pid))
        except Exception as pid_err:
            logging.error(f"⚠️ Failed to write PID file for {agent_name}: {pid_err}")
        logging.info(f"✅ Started agent '{agent_name}' with PID: {process.pid}")
        return True
    except Exception as e:
        logging.error(f"❌ Failed to start agent '{agent_name}': {e}")
        return False


# ---------------------------------------------------------------------------
# Transcript writer (NDJSON, ACPX-compatible format)
# ---------------------------------------------------------------------------

def append_transcript_event(direction: str, text: str, raw: str = "") -> None:
    """Append one ACPX-compatible NDJSON event to the per-session transcript."""
    event = {
        "direction": direction,  # "out" = parent -> child, "in" = child -> parent
        "text": text,
        "raw": raw or text,
        "ts": time.time(),
    }
    try:
        with open(TRANSCRIPT_FILE_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")
    except Exception as e:
        logging.error(f"❌ Transcript write failed: {e}")


def extract_last_assistant_text(events: list) -> str:
    """Mirror agent.acpx.runtime.extract_last_assistant_text:
       prefer envelope-marked assistant events; fall back to all 'in' text."""
    assistant_chunks = []
    log_chunks = []
    for ev in events:
        text = (ev.get("text") or "").strip()
        if not text:
            continue
        # Direct envelope marking (oneshot-prompt and json-acp paths).
        ev_role = str(ev.get("role") or "").lower()
        ev_kind = str(ev.get("event") or "").lower()
        if ev_role in ("assistant", "model", "ai") or ev_kind in (
            "assistant_message", "assistant", "message", "completion", "answer"
        ):
            assistant_chunks.append(text)
            continue
        # Skip stderr-channel logs from oneshot output.
        if str(ev.get("channel") or "").lower() == "stderr":
            continue
        # JSON-ACP envelope smuggled inside a raw stdout line.
        try:
            payload = json.loads(text)
            role = (payload.get("role") or "").lower()
            kind = (payload.get("event") or "").lower()
            if role in ("assistant", "model", "ai") or kind in (
                "assistant_message", "assistant", "message", "completion", "answer"
            ):
                body = payload.get("text") or payload.get("content") or payload.get("message") or ""
                if isinstance(body, list):
                    body = "\n".join(str(b) for b in body)
                if body:
                    assistant_chunks.append(str(body))
                continue
        except (json.JSONDecodeError, ValueError, TypeError):
            pass
        # tui-repl transport: every "in" event is assistant text.
        if ev.get("direction") == "in":
            log_chunks.append(text)
    chosen = assistant_chunks if assistant_chunks else log_chunks
    return "\n".join(chosen).strip()


# ---------------------------------------------------------------------------
# Transport-aware drain (port of agent.acpx.runtime.AcpSession.send_turn)
# ---------------------------------------------------------------------------

def _reader_thread(stream, queue: Queue):
    """Daemon thread that drains a child stdio stream into a queue line-by-line.
    Cross-platform: Windows readline() on a pipe cannot be interrupted, so this
    thread is sacrificed when drain ends - the kill() teardown closes the pipe."""
    try:
        for line in iter(stream.readline, ""):
            if not line:
                break
            queue.put(line.rstrip("\r\n"))
    except Exception:
        pass
    finally:
        queue.put(None)  # sentinel: stream closed


def drain_session(process, transport: str, idle_s: float, timeout_s: float,
                  grace_s: float) -> tuple:
    """Drain child stdout with transport-aware completion rule.

    Returns: (events_list, settle_reason)

    Completion rules (checked every 100ms in this order):
      1. JSON line with {"done": true}                             -> "done"
      2. Stdout closed (process exited)                            -> "child_exited"
      3. now - started_at >= timeout_s                             -> "timeout"
      4. Idle rule fires:
         json-acp: events_seen > 0 AND now - last_event >= idle_s  -> "idle"
         tui-repl/one-shot: now - started >= grace + idle even
           with zero events                                        -> "idle"
    """
    queue: Queue = Queue()
    reader = threading.Thread(
        target=_reader_thread, args=(process.stdout, queue), daemon=True
    )
    reader.start()

    events: list = []
    started_at = time.time()
    last_event_at = started_at
    settle_reason = "timeout"
    events_seen = 0

    while True:
        now = time.time()

        # Rule 3: hard timeout backstop.
        if now - started_at >= timeout_s:
            settle_reason = "timeout"
            break

        # Pull next line (or sentinel/None).
        try:
            line = queue.get(timeout=0.1)
        except Empty:
            line = None

        if line is None:
            # Sentinel from reader -> child closed stdout. Confirm exit.
            if not reader.is_alive() or process.poll() is not None:
                settle_reason = "child_exited"
                break
        else:
            # Got a real line -> record event + transcript.
            events_seen += 1
            last_event_at = time.time()
            ev = {"direction": "in", "text": line, "raw": line, "ts": last_event_at}
            events.append(ev)
            append_transcript_event("in", line)

            # Rule 1: explicit done envelope.
            try:
                payload = json.loads(line)
                if isinstance(payload, dict) and payload.get("done") is True:
                    settle_reason = "done"
                    break
            except (json.JSONDecodeError, ValueError, TypeError):
                pass
            continue  # try next line immediately while queue has stuff

        # Rule 4: transport-aware idle rule.
        elapsed = now - started_at
        idle_for = now - last_event_at
        if transport == "json-acp":
            if events_seen > 0 and idle_for >= idle_s and elapsed >= grace_s:
                settle_reason = "idle"
                break
        else:  # tui-repl or one-shot
            if elapsed >= (grace_s + idle_s) and idle_for >= idle_s:
                settle_reason = "idle"
                break

    return events, settle_reason


# ---------------------------------------------------------------------------
# Spawn + dispatch task
# ---------------------------------------------------------------------------

def resolve_command(agent_id: str, command_override: str) -> dict:
    """Resolve a registry record for ``agent_id`` (with optional command override).

    Returns a dict with keys:
      - argv (list[str]): executable + args after splitting
      - transport (str)
      - idle_s, timeout_s, grace_s (float)
      - prompt_flag (str|None): CLI flag introducing the prompt arg in
                                 ``oneshot-prompt`` mode (None means
                                 the prompt is appended positionally)
      - prompt_subargs (list[str]): optional positional args before the
                                    prompt (e.g. ``["exec"]`` for codex)
    """
    if agent_id in _DEFAULT_REGISTRY:
        rec = dict(_DEFAULT_REGISTRY[agent_id])
    else:
        rec = {"command": agent_id, "transport": "tui-repl",
               "idle_s": 2.0, "timeout_s": 8.0, "grace_s": 3.0,
               "prompt_flag": None, "prompt_subargs": []}
    cmd_str = (command_override or rec["command"]).strip()
    if not cmd_str:
        cmd_str = agent_id
    # Tokenize - shlex would be nice but Windows quoting differs; keep it simple.
    if sys.platform.startswith('win'):
        argv = cmd_str.split()
    else:
        import shlex
        argv = shlex.split(cmd_str)
    rec["argv"] = argv
    return rec


def run_oneshot_prompt(argv: list, prompt_flag, prompt_subargs: list,
                       task: str, cwd, timeout_s: float) -> tuple:
    """Drive one ``oneshot-prompt`` turn: spawn fresh CLI with the prompt
    as a CLI arg, close stdin, capture stdout/stderr to EOF.

    Returns (events, settle_reason). The first event is an
    ``assistant_message`` carrying the captured stdout — extracted by
    extract_last_assistant_text downstream. ``settle_reason`` is one of
    ``"child_exited"`` or ``"timeout"``.
    """
    full_argv = list(argv) + list(prompt_subargs or [])
    flag = (prompt_flag or "").strip() if prompt_flag else ""
    if flag:
        full_argv.append(flag)
    full_argv.append(task)

    append_transcript_event("out", task, raw=json.dumps({
        "argv": full_argv, "transport": "oneshot-prompt"
    }, ensure_ascii=False))

    try:
        process = subprocess.Popen(
            full_argv,
            cwd=cwd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding='utf-8',
            errors='replace',
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0,
        )
    except FileNotFoundError:
        return ([{"event": "error", "text": f"command not on PATH: {full_argv[0]}",
                  "direction": "in"}], "command_not_found")
    except Exception as e:
        return ([{"event": "error", "text": str(e),
                  "direction": "in"}], "spawn_failed")

    try:
        try:
            if process.stdin is not None:
                process.stdin.close()
        except Exception:
            pass
        try:
            stdout_text, stderr_text = process.communicate(timeout=timeout_s)
            settle = "child_exited"
        except subprocess.TimeoutExpired:
            try:
                process.kill()
            except Exception:
                pass
            try:
                stdout_text, stderr_text = process.communicate(timeout=5)
            except Exception:
                stdout_text, stderr_text = "", ""
            settle = "timeout"
    except Exception as e:
        return ([{"event": "error", "text": f"I/O failure: {e}",
                  "direction": "in"}], "io_failed")

    stdout_text = stdout_text or ""
    stderr_text = stderr_text or ""

    events: list = []
    if stdout_text.strip():
        append_transcript_event("in", stdout_text, raw=stdout_text)
        events.append({
            "direction": "in",
            "event": "assistant_message",
            "role": "assistant",
            "text": stdout_text.strip(),
        })
    if stderr_text.strip():
        append_transcript_event("in", stderr_text, raw=stderr_text)
        events.append({
            "direction": "in",
            "event": "log",
            "channel": "stderr",
            "text": stderr_text.strip(),
        })
    if not events:
        # Capture nothing-at-all explicitly so the section block below
        # carries a non-empty body and Parametrizer downstream sees the
        # outcome of the call.
        events.append({
            "direction": "in",
            "event": "log",
            "text": f"(no output; exit_code={process.returncode})",
        })
    return events, settle


def run_acpx_session(config: dict) -> dict:
    """Drive one full ACPX session lifecycle. Returns a result dict."""
    agent_id = (config.get('agent_id') or 'claude').strip()
    task = (config.get('task') or '').strip()
    cwd = (config.get('cwd') or '').strip() or None
    mode = (config.get('mode') or 'session').strip()
    command_override = (config.get('command') or '').strip()

    rec = resolve_command(agent_id, command_override)
    argv = rec["argv"]
    transport = rec["transport"]
    prompt_flag = rec.get("prompt_flag")
    prompt_subargs = rec.get("prompt_subargs") or []

    # Per-call overrides (0 / null means "use registry default").
    idle_s = float(config.get('idle_seconds') or 0) or rec["idle_s"]
    timeout_s = float(config.get('timeout_seconds') or 0) or rec["timeout_s"]
    grace_s = float(config.get('startup_grace_seconds') or 0) or rec["grace_s"]

    session_id = f"acpxer-{uuid.uuid4().hex[:12]}"
    transcript_path = os.path.abspath(TRANSCRIPT_FILE_PATH)

    # Truncate transcript on fresh starts only.
    if not _IS_REANIMATED:
        open(TRANSCRIPT_FILE_PATH, 'w').close()

    logging.info("=" * 60)
    logging.info(f"🚀 ACPXER SESSION: {session_id}")
    logging.info(f"   agent_id:    {agent_id}")
    logging.info(f"   command:     {argv}")
    logging.info(f"   transport:   {transport}")
    if transport == "oneshot-prompt":
        logging.info(f"   prompt_flag: {prompt_flag!r}")
        logging.info(f"   prompt_subargs: {prompt_subargs}")
    logging.info(f"   mode:        {mode}")
    logging.info(f"   cwd:         {cwd or '(inherit)'}")
    logging.info(f"   idle/timeout/grace: {idle_s}s / {timeout_s}s / {grace_s}s")
    logging.info(f"   transcript:  {transcript_path}")
    logging.info(f"   task:        {task[:200]}{'...' if len(task) > 200 else ''}")
    logging.info("=" * 60)

    if not task:
        logging.error("❌ No task configured (config.task is empty)")
        return {
            "ok": False, "session_id": session_id, "agent_id": agent_id,
            "transport": transport, "transcript_path": transcript_path,
            "settle": "no_task", "events_seen": 0, "last_assistant_text": "",
            "error": "No task configured",
        }

    # ── oneshot-prompt fast path: fresh process per turn, captures stdout
    if transport == "oneshot-prompt":
        events, settle_reason = run_oneshot_prompt(
            argv, prompt_flag, prompt_subargs, task, cwd, timeout_s
        )
        last_text = extract_last_assistant_text(events)

        logging.info(f"📡 Oneshot settled: reason={settle_reason}, events={len(events)}")
        if last_text:
            preview = last_text[:300] + ("..." if len(last_text) > 300 else "")
            logging.info(f"💬 Last assistant text ({len(last_text)} chars): {preview}")
        else:
            logging.info("⚠️ No assistant text captured")

        return {
            "ok": settle_reason == "child_exited" and bool(last_text),
            "session_id": session_id,
            "agent_id": agent_id,
            "transport": transport,
            "transcript_path": transcript_path,
            "settle": settle_reason,
            "events_seen": len(events),
            "last_assistant_text": last_text,
            "error": "" if settle_reason == "child_exited" and last_text
                     else (f"Settled on {settle_reason}" if settle_reason != "child_exited"
                           else "No assistant text captured"),
        }

    # ── Legacy long-lived child path (json-acp / tui-repl / one-shot)
    try:
        process = subprocess.Popen(
            argv,
            cwd=cwd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,  # line-buffered
            encoding='utf-8',
            errors='replace',
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0,
        )
    except FileNotFoundError:
        logging.error(f"❌ Command not resolvable on PATH: {argv[0]}")
        return {
            "ok": False, "session_id": session_id, "agent_id": agent_id,
            "transport": transport, "transcript_path": transcript_path,
            "settle": "command_not_found", "events_seen": 0,
            "last_assistant_text": "",
            "error": f"Command '{argv[0]}' not resolvable on PATH",
        }
    except Exception as e:
        logging.error(f"❌ Spawn failed: {e}")
        return {
            "ok": False, "session_id": session_id, "agent_id": agent_id,
            "transport": transport, "transcript_path": transcript_path,
            "settle": "spawn_failed", "events_seen": 0,
            "last_assistant_text": "", "error": str(e),
        }

    # Dispatch task on stdin.
    try:
        envelope = {"task": task, "mode": mode}
        line = json.dumps(envelope) + "\n" if transport == "json-acp" else task + "\n"
        append_transcript_event("out", line.rstrip("\r\n"))
        process.stdin.write(line)
        process.stdin.flush()
        if mode == "one-shot" or transport == "one-shot":
            try:
                process.stdin.close()
            except Exception:
                pass
    except Exception as e:
        logging.error(f"❌ Dispatch failed: {e}")
        try:
            process.terminate()
        except Exception:
            pass
        return {
            "ok": False, "session_id": session_id, "agent_id": agent_id,
            "transport": transport, "transcript_path": transcript_path,
            "settle": "dispatch_failed", "events_seen": 0,
            "last_assistant_text": "", "error": str(e),
        }

    # Drain.
    events, settle_reason = drain_session(
        process, transport, idle_s, timeout_s, grace_s
    )
    last_text = extract_last_assistant_text(events)

    logging.info(f"📡 Drain settled: reason={settle_reason}, events={len(events)}")
    if last_text:
        preview = last_text[:300] + ("..." if len(last_text) > 300 else "")
        logging.info(f"💬 Last assistant text ({len(last_text)} chars): {preview}")

    # Kill (always - graceful close).
    try:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()
        logging.info(f"🛑 Session killed: PID was {process.pid}")
    except Exception as e:
        logging.error(f"⚠️ Kill warning: {e}")

    return {
        "ok": settle_reason in ("done", "idle", "child_exited"),
        "session_id": session_id,
        "agent_id": agent_id,
        "transport": transport,
        "transcript_path": transcript_path,
        "settle": settle_reason,
        "events_seen": len(events),
        "last_assistant_text": last_text,
        "error": "" if settle_reason in ("done", "idle", "child_exited")
                 else f"Settled on {settle_reason}",
    }


def emit_section(result: dict) -> None:
    """Emit ONE atomic INI_SECTION_ACPXER<<< ... >>>END_SECTION_ACPXER block.

    Field contract (consumed by Parametrizer / PARAMETRIZER_SOURCE_OUTPUT_FIELDS):
      - agent_id, session_id, transport, settle, transcript_path
      - response_body = last_assistant_text (so downstream agents can pipe it
        as 'task', 'prompt', 'content', etc.)
    """
    body = result.get("last_assistant_text") or result.get("error") or ""
    logging.info(
        f"INI_SECTION_ACPXER<<<\n"
        f"agent_id: {result.get('agent_id', '')}\n"
        f"session_id: {result.get('session_id', '')}\n"
        f"transport: {result.get('transport', '')}\n"
        f"settle: {result.get('settle', '')}\n"
        f"transcript_path: {result.get('transcript_path', '')}\n"
        f"\n"
        f"{body}\n"
        f">>>END_SECTION_ACPXER"
    )


# ---------------------------------------------------------------------------
# PID + main
# ---------------------------------------------------------------------------

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


def main():
    config = load_config()

    write_pid_file()
    if _IS_REANIMATED:
        logging.info(f"🔄 {CURRENT_DIR_NAME} REANIMATED (resuming from pause)")
        logging.info("=" * 60)
    else:
        logging.info(f"🟢 {CURRENT_DIR_NAME} STARTED")

    try:
        target_agents = config.get('target_agents', []) or []

        # Drive the ACPX session end-to-end.
        result = run_acpx_session(config)
        emit_section(result)

        # Trigger downstream agents regardless of success or failure.
        # ACPXer is an Active agent (like Apirer) - the flow continues even
        # when the external CLI fails so a downstream Raiser/Forker can
        # branch on the failure.
        triggered = 0
        if target_agents:
            wait_for_agents_to_stop(target_agents)
            verdict = "SUCCESS" if result.get("ok") else "ERROR"
            logging.info(
                f"🚀 Triggering {len(target_agents)} downstream agents "
                f"(result: {verdict})..."
            )
            for target in target_agents:
                if start_agent(target):
                    triggered += 1

        logging.info(
            f"🏁 ACPXer finished. settle={result.get('settle')}, "
            f"events={result.get('events_seen')}, "
            f"triggered {triggered}/{len(target_agents)} agents."
        )

    finally:
        time.sleep(0.4)  # keep LED green briefly
        remove_pid_file()

    sys.exit(0)


if __name__ == "__main__":
    main()
