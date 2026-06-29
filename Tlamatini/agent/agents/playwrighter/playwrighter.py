# ═══════════════════════════════════════════════════════════════════
#   ✦  T L A M A T I N I  ✦   —   "one who knows"
#
#   Created by  Angela López Mendoza   ·   @angelahack1
#   Developer · Architect · Creator of Tlamatini
#
#   Every line of this file was written by Angela López Mendoza.
# ═══════════════════════════════════════════════════════════════════
#   Tlamatini Author Banner — do not remove (releases scrub the name automatically)
# Playwrighter Agent — scripted, interactive browser automation via Playwright.
#
# Action: Triggered by upstream -> launch a real browser (Chromium/Firefox/
#         WebKit) -> run an ordered list of declarative steps (goto / click /
#         fill / wait_for / extract_text / screenshot / assert / download) ->
#         persist results + an INI_SECTION_PLAYWRIGHTER block -> trigger
#         downstream agents (on success OR failure, so a Forker can branch on
#         the section's status/assert_result).
#
# Self-contained: this pool agent runs as a separate Python subprocess with no
# path back into the Django app, so it uses playwright.sync_api directly (no
# ThreadPoolExecutor needed — that is only required by the in-process wrapped
# tool, which runs inside Django Channels' asyncio loop).

import os
import sys

# FIX: Disable Intel Fortran runtime Ctrl+C handler
os.environ['FOR_DISABLE_CONSOLE_CTRL_HANDLER'] = '1'

import json
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
from typing import Any, Dict, List

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
    for _attempt in range(5):
        try:
            if os.path.exists(PID_FILE):
                os.remove(PID_FILE)
            return
        except PermissionError:
            time.sleep(0.1)
        except Exception as e:
            logging.error(f"Failed to remove PID file: {e}")
            return


# ============================================================
# Playwright Step Interpreter
# ============================================================

_VALID_BROWSERS = ("chromium", "firefox", "webkit")
_VALID_WAIT_UNTIL = ("load", "domcontentloaded", "networkidle", "commit")
_VALID_WAIT_STATES = ("visible", "hidden", "attached", "detached")
# Steps that DO NOT need a selector to be present.
_NO_SELECTOR_ACTIONS = ("goto", "wait", "screenshot")


def _abs_under_script(path: str) -> str:
    """Resolve a (possibly relative) path under the agent's own directory."""
    if not path:
        return path
    return path if os.path.isabs(path) else os.path.join(script_dir, path)


def _truncate(text: str, limit: int = 200000) -> str:
    if text and len(text) > limit:
        return text[:limit] + "\n...[truncated]"
    return text


def _coerce_int(value: Any, default: int = 0) -> int:
    """Best-effort int coercion (handles ints, numeric strings, floats).

    The wrapped-tool config path can hand us an int (``hold_open_seconds=10``)
    or, on odd LLM phrasing, a string ("10" / "10.0"); never raise on a bad
    value — fall back to ``default`` so a malformed linger value cannot abort
    an otherwise-good browser run."""
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _run_one_step(page, step: Dict[str, Any], idx: int, default_timeout: int,
                  extracted: Dict[str, str], asserts: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Execute a single declarative step. Returns a per-step result dict.

    Never raises — a failed step is recorded with ``ok=False`` and the caller
    decides whether to keep going (we do, so the section + downstream still
    fire and a Forker can branch on the final status)."""
    action = str(step.get("action", "")).strip().lower()
    selector = step.get("selector")
    timeout = int(step.get("timeout", 0) or 0) or default_timeout
    result: Dict[str, Any] = {"index": idx, "action": action, "ok": True}

    try:
        if action == "goto":
            url = step.get("url", "")
            if not url:
                raise ValueError("goto step requires a 'url'")
            wait_until = str(step.get("wait_until", "domcontentloaded"))
            if wait_until not in _VALID_WAIT_UNTIL:
                wait_until = "domcontentloaded"
            page.goto(url, wait_until=wait_until, timeout=timeout)
            result["url"] = url

        elif action == "click":
            page.click(selector, timeout=timeout)

        elif action == "dblclick":
            page.dblclick(selector, timeout=timeout)

        elif action == "fill":
            page.fill(selector, str(step.get("value", "")), timeout=timeout)

        elif action == "type":
            delay = int(step.get("delay", 0) or 0)
            page.type(selector, str(step.get("text", "")), delay=delay, timeout=timeout)

        elif action == "press":
            key = str(step.get("key", ""))
            if not key:
                raise ValueError("press step requires a 'key'")
            if selector:
                page.press(selector, key, timeout=timeout)
            else:
                page.keyboard.press(key)

        elif action == "select":
            page.select_option(selector, str(step.get("value", "")), timeout=timeout)

        elif action == "check":
            page.check(selector, timeout=timeout)

        elif action == "uncheck":
            page.uncheck(selector, timeout=timeout)

        elif action == "wait_for":
            state = str(step.get("state", "visible"))
            if state not in _VALID_WAIT_STATES:
                state = "visible"
            page.wait_for_selector(selector, state=state, timeout=timeout)

        elif action == "wait":
            ms = int(step.get("ms", 1000) or 0)
            page.wait_for_timeout(ms)
            result["ms"] = ms

        elif action == "extract_text":
            if selector:
                text = page.inner_text(selector, timeout=timeout)
            else:
                text = page.inner_text("body", timeout=timeout)
            text = _truncate((text or "").strip())
            name = str(step.get("name") or f"text_{idx}")
            extracted[name] = text
            result["name"] = name
            result["chars"] = len(text)

        elif action == "extract_attr":
            attr = str(step.get("attr", ""))
            if not attr:
                raise ValueError("extract_attr step requires an 'attr'")
            value = page.get_attribute(selector, attr, timeout=timeout) or ""
            name = str(step.get("name") or f"attr_{idx}")
            extracted[name] = value
            result["name"] = name
            result["attr"] = attr

        elif action == "screenshot":
            path = _abs_under_script(str(step.get("path") or f"playwrighter_step_{idx}.png"))
            full_page = bool(step.get("full_page", False))
            os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
            page.screenshot(path=path, full_page=full_page)
            result["path"] = path

        elif action == "assert_visible":
            visible = page.is_visible(selector)
            asserts.append({"kind": "visible", "selector": selector, "passed": bool(visible)})
            result["passed"] = bool(visible)
            if not visible:
                result["ok"] = False

        elif action == "assert_text":
            contains = str(step.get("contains", ""))
            if selector:
                haystack = page.inner_text(selector, timeout=timeout)
            else:
                haystack = page.inner_text("body", timeout=timeout)
            passed = contains in (haystack or "")
            asserts.append({"kind": "text", "contains": contains, "passed": passed})
            result["passed"] = passed
            if not passed:
                result["ok"] = False

        elif action == "download":
            save_path = _abs_under_script(str(step.get("save_path") or ""))
            with page.expect_download(timeout=timeout) as dl_info:
                page.click(selector, timeout=timeout)
            download = dl_info.value
            if not save_path:
                save_path = _abs_under_script(download.suggested_filename)
            os.makedirs(os.path.dirname(save_path) or ".", exist_ok=True)
            download.save_as(save_path)
            result["path"] = save_path

        else:
            raise ValueError(f"Unknown action: {action!r}")

        # Selector-requiring actions must actually have one.
        if action not in _NO_SELECTOR_ACTIONS and action in (
            "click", "dblclick", "fill", "type", "select", "check", "uncheck",
            "wait_for", "extract_attr", "assert_visible", "download",
        ) and not selector:
            raise ValueError(f"{action} step requires a 'selector'")

    except Exception as e:
        result["ok"] = False
        result["error"] = str(e)
        logging.error(f"Step {idx} ({action}) failed: {e}")
    else:
        logging.info(f"Step {idx} ({action}) ok"
                     + (f" -> {result.get('name')}" if result.get('name') else ""))
    return result


def run_browser_flow(config: Dict) -> Dict[str, Any]:
    """Drive a browser through the configured steps. Returns a result dict
    with status, final_url, extracted values, per-step results and asserts."""
    out: Dict[str, Any] = {
        "start_url": config.get("start_url", ""),
        "final_url": "",
        "status": "ok",
        "steps_total": 0,
        "steps_run": 0,
        "assert_result": "n/a",
        "extracted": {},
        "step_results": [],
        "error": "",
    }

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        out["status"] = "error"
        out["error"] = ("Playwright is not installed. Install with: "
                        "pip install playwright && playwright install")
        logging.error(out["error"])
        return out

    browser_kind = str(config.get("browser", "chromium")).lower()
    if browser_kind not in _VALID_BROWSERS:
        browser_kind = "chromium"
    headless = bool(config.get("headless", True))
    default_timeout = int(config.get("timeout_ms", 30000) or 30000)
    nav_wait_until = str(config.get("nav_wait_until", "domcontentloaded"))
    if nav_wait_until not in _VALID_WAIT_UNTIL:
        nav_wait_until = "domcontentloaded"
    user_agent = str(config.get("user_agent", "") or "")
    vw = int(config.get("viewport_width", 1920) or 1920)
    vh = int(config.get("viewport_height", 1080) or 1080)
    storage_state_in = _abs_under_script(str(config.get("storage_state_in", "") or ""))
    storage_state_out = _abs_under_script(str(config.get("storage_state_out", "") or ""))
    start_url = str(config.get("start_url", "") or "")

    # "Hold open" linger: keep the browser visible AFTER the last step finishes
    # and BEFORE we tear it down, so a human can actually watch the result. This
    # is what makes an explicit "wait N seconds before closing the browser"
    # request real — without it the finally block closes the browser the instant
    # the final step returns. hold_open_seconds is the natural unit; hold_open_ms
    # is the finer-grained alias and wins when both are > 0. Honored regardless
    # of headless (harmless when headless=true).
    hold_open_ms = _coerce_int(config.get("hold_open_ms", 0))
    hold_open_seconds = _coerce_int(config.get("hold_open_seconds", 0))
    hold_open_total_ms = hold_open_ms if hold_open_ms > 0 else hold_open_seconds * 1000

    steps = config.get("steps") or []
    if not isinstance(steps, list):
        steps = []

    # Chat / wrapped-tool path: the LLM passes the whole script as a single
    # JSON string (``steps_json='[{...},{...}]'``) because the flat key=value
    # request grammar cannot express a list-of-dicts. When present it WINS
    # over the YAML ``steps`` (which is the canvas-friendly authoring form).
    steps_json = config.get("steps_json")
    if steps_json:
        try:
            parsed = json.loads(steps_json) if isinstance(steps_json, str) else steps_json
            if isinstance(parsed, list):
                steps = [s for s in parsed if isinstance(s, dict)]
                logging.info(f"Using steps_json ({len(steps)} steps) instead of config steps")
            else:
                logging.warning("steps_json did not decode to a list; ignoring it")
        except Exception as e:
            logging.warning(f"steps_json provided but failed to parse as JSON: {e}")

    # If there's a start_url and the first step isn't already a goto, prepend one.
    effective_steps: List[Dict[str, Any]] = []
    first_is_goto = bool(steps) and str(steps[0].get("action", "")).lower() == "goto"
    if start_url and not first_is_goto:
        effective_steps.append({"action": "goto", "url": start_url, "wait_until": nav_wait_until})
    effective_steps.extend(s for s in steps if isinstance(s, dict))
    out["steps_total"] = len(effective_steps)

    extracted: Dict[str, str] = {}
    asserts: List[Dict[str, Any]] = []

    try:
        with sync_playwright() as p:
            launcher = getattr(p, browser_kind)
            launch_args = {"headless": headless}
            if browser_kind == "chromium":
                launch_args["args"] = [
                    '--disable-blink-features=AutomationControlled',
                    '--no-first-run',
                    '--no-default-browser-check',
                ]
            browser = launcher.launch(**launch_args)

            context_args: Dict[str, Any] = {"viewport": {"width": vw, "height": vh}}
            if user_agent:
                context_args["user_agent"] = user_agent
            if storage_state_in and os.path.exists(storage_state_in):
                context_args["storage_state"] = storage_state_in
                logging.info(f"Loaded storage_state from {storage_state_in}")

            context = browser.new_context(**context_args)
            page = context.new_page()

            try:
                for i, step in enumerate(effective_steps, 1):
                    res = _run_one_step(page, step, i, default_timeout, extracted, asserts)
                    out["step_results"].append(res)
                    out["steps_run"] += 1
                    if not res.get("ok") and res.get("error"):
                        # A hard error (not a soft assert) aborts the remaining
                        # steps but we still report + trigger downstream.
                        out["status"] = "error"
                        out["error"] = res.get("error", "")
                        break

                try:
                    out["final_url"] = page.url
                except Exception:
                    pass

                # Persist session if requested.
                if storage_state_out:
                    try:
                        os.makedirs(os.path.dirname(storage_state_out) or ".", exist_ok=True)
                        context.storage_state(path=storage_state_out)
                        logging.info(f"Saved storage_state to {storage_state_out}")
                    except Exception as ss_err:
                        logging.warning(f"Could not save storage_state: {ss_err}")

                # Hold the browser open for the configured linger so a human can
                # watch the final state before it closes. Runs on success OR a
                # mid-flow error (a failed run is still worth seeing), while the
                # page/browser are still alive — the very next thing the finally
                # block does is tear them down.
                if hold_open_total_ms > 0:
                    try:
                        logging.info(
                            f"Holding browser open for {hold_open_total_ms} ms "
                            f"before close (headless={headless})"
                        )
                        page.wait_for_timeout(hold_open_total_ms)
                    except Exception as hold_err:
                        logging.warning(f"hold-open wait interrupted: {hold_err}")
            finally:
                try:
                    context.close()
                except Exception:
                    pass
                browser.close()

    except Exception as e:
        out["status"] = "error"
        out["error"] = str(e)
        logging.error(f"Playwright run failed: {e}")

    out["extracted"] = extracted

    # Roll up assertion verdicts.
    if asserts:
        all_passed = all(a.get("passed") for a in asserts)
        out["assert_result"] = "pass" if all_passed else "fail"
        if not all_passed and out["status"] == "ok":
            out["status"] = "assert_failed"

    return out


def _build_section_body(result: Dict[str, Any]) -> str:
    """Compose the human-readable body stored under ``response_body``: the
    extracted key/values first, then a compact JSON of the per-step trace."""
    lines: List[str] = []
    extracted = result.get("extracted") or {}
    if extracted:
        lines.append("=== EXTRACTED ===")
        for name, value in extracted.items():
            lines.append(f"[{name}]")
            lines.append(value)
            lines.append("")
    if result.get("error"):
        lines.append(f"ERROR: {result['error']}")
        lines.append("")
    try:
        trace = json.dumps(result.get("step_results", []), ensure_ascii=False, indent=2, default=str)
    except Exception:
        trace = repr(result.get("step_results", []))
    lines.append("=== STEP TRACE ===")
    lines.append(trace)
    return _truncate("\n".join(lines), 256 * 1024)


def save_results(result: Dict[str, Any], output_file: str) -> str:
    """Save the run report to a file. Returns the absolute file path."""
    output_file = _abs_under_script(output_file)
    os.makedirs(os.path.dirname(output_file) or ".", exist_ok=True)

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write("=== PLAYWRIGHTER RESULTS ===\n")
        f.write(f"Start URL: {result.get('start_url', '')}\n")
        f.write(f"Final URL: {result.get('final_url', '')}\n")
        f.write(f"Status: {result.get('status', '')}\n")
        f.write(f"Steps run: {result.get('steps_run', 0)}/{result.get('steps_total', 0)}\n")
        f.write(f"Assert result: {result.get('assert_result', 'n/a')}\n")
        f.write(f"Timestamp: {timestamp}\n")
        f.write("=" * 60 + "\n\n")
        f.write(_build_section_body(result))
        f.write("\n")

    return os.path.abspath(output_file)


# ========================================
# MAIN
# ========================================

def main():
    config = load_config()

    write_pid_file()
    if _IS_REANIMATED:
        logging.info(f"REANIMATED {CURRENT_DIR_NAME} (resuming from pause)")
        logging.info("=" * 60)

    try:
        start_url = config.get('start_url', '')
        browser = config.get('browser', 'chromium')
        headless = config.get('headless', True)
        output_file = config.get('output_file', 'playwrighter_results.txt')
        target_agents = config.get('target_agents', []) or []

        logging.info("PLAYWRIGHTER AGENT STARTED")
        logging.info(f"Start URL: {start_url}")
        logging.info(f"Browser: {browser} (headless={headless})")
        logging.info(f"Steps: {len(config.get('steps') or [])}")
        logging.info(f"Targets: {target_agents}")
        logging.info("=" * 60)

        result = run_browser_flow(config)

        saved_path = save_results(result, output_file)
        logging.info(f"Results saved to: {saved_path}")
        logging.info(
            f"Run finished: status={result.get('status')} "
            f"steps={result.get('steps_run')}/{result.get('steps_total')} "
            f"assert={result.get('assert_result')}"
        )

        # Emit a single atomic INI_SECTION block for Parametrizer + Exec Report.
        body = _build_section_body(result)
        logging.info(
            "INI_SECTION_PLAYWRIGHTER<<<\n"
            f"start_url: {result.get('start_url', '')}\n"
            f"final_url: {result.get('final_url', '')}\n"
            f"status: {result.get('status', '')}\n"
            f"steps_run: {result.get('steps_run', 0)}\n"
            f"assert_result: {result.get('assert_result', 'n/a')}\n"
            f"\n"
            f"{body}\n"
            ">>>END_SECTION_PLAYWRIGHTER"
        )

        # Always trigger downstream agents (success OR failure) so flows can
        # route on the section's status / assert_result via Parametrizer.
        total_triggered = 0
        if target_agents:
            wait_for_agents_to_stop(target_agents)
            logging.info(f"Triggering {len(target_agents)} downstream agents...")
            for target in target_agents:
                if start_agent(target):
                    total_triggered += 1

        logging.info(f"Playwrighter agent finished. Triggered {total_triggered}/{len(target_agents)} agents.")

    except Exception as e:
        logging.error(f"Playwrighter agent error: {e}")
    finally:
        time.sleep(0.4)
        remove_pid_file()

    sys.exit(0)


if __name__ == "__main__":
    main()
