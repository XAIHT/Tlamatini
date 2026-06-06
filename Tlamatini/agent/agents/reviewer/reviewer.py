# Reviewer Agent - LLM-powered code review of a git diff
# Action: Triggered by upstream -> resolve git diff -> ask Ollama LLM to
# review it -> parse a verdict -> emit INI_SECTION_REVIEWER -> trigger
# downstream agents (always, so flows can route on the verdict).
#
# Self-contained: does NOT import from agent.* — pool subprocesses run as
# separate Python interpreters with no path back into the Django app.

import os
import sys

# FIX: Disable Intel Fortran runtime Ctrl+C handler
os.environ['FOR_DISABLE_CONSOLE_CTRL_HANDLER'] = '1'

import time
import yaml
import json
import logging
import subprocess

# -- conhost.exe orphan guard ------------------------------------------
# When Tlamatini's runtime launches us with DETACHED_PROCESS we have no
# console attached. Any child we Popen WITHOUT CREATE_NO_WINDOW makes
# Windows allocate a fresh console (and a companion conhost.exe) that
# lingers as an orphan bearing the Tlamatini icon. Default every Popen to
# CREATE_NO_WINDOW unless the caller explicitly asked for a console.
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


def query_ollama(host: str, model: str, prompt: str) -> str:
    """Send a prompt to an Ollama LLM and return the full response text.
    Uses urllib (stdlib) so no external dependencies are needed."""
    url = f"{host.rstrip('/')}/api/generate"
    payload = json.dumps({
        "model": model,
        "prompt": prompt,
        "stream": False
    }).encode("utf-8")

    req = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST"
    )

    try:
        with urllib.request.urlopen(req, timeout=600) as resp:
            body = json.loads(resp.read().decode("utf-8"))
            return body.get("response", "")
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8", errors="replace") if e.fp else ""
        raise RuntimeError(f"Ollama HTTP {e.code}: {error_body}") from e
    except urllib.error.URLError as e:
        raise RuntimeError(f"Cannot reach Ollama at {host}: {e.reason}") from e


# ========================================
# REVIEW HELPERS
# ========================================

VALID_VERDICTS = ("APPROVE", "REQUEST_CHANGES", "COMMENT")


def _run_git(repo_path: str, args: list) -> tuple:
    """Run a git command in repo_path. Returns (returncode, stdout, stderr)."""
    cmd = ["git", "-C", repo_path] + args
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=60,
        )
        return proc.returncode, proc.stdout or "", proc.stderr or ""
    except FileNotFoundError:
        return 127, "", "git executable not found on PATH"
    except subprocess.TimeoutExpired:
        return 124, "", "git command timed out"
    except Exception as e:
        return 1, "", str(e)


def resolve_diff(repo_path: str, diff_ref: str) -> tuple:
    """Resolve the diff to review. Returns (diff_text, stat_text, error)."""
    rc, _, err = _run_git(repo_path, ["rev-parse", "--is-inside-work-tree"])
    if rc != 0:
        return "", "", f"{repo_path!r} is not a git repository ({err.strip()})"

    if diff_ref.strip():
        rc, diff_text, err = _run_git(repo_path, ["diff", diff_ref, "--", "."])
        if rc != 0:
            return "", "", f"git diff {diff_ref} failed: {err.strip()}"
        _, stat_text, _ = _run_git(repo_path, ["diff", diff_ref, "--stat"])
    else:
        # Uncommitted working-tree + staged changes.
        _, unstaged, _ = _run_git(repo_path, ["diff", "HEAD"])
        _, staged, _ = _run_git(repo_path, ["diff", "--staged"])
        diff_text = ""
        if staged.strip():
            diff_text += "# === staged changes ===\n" + staged
        if unstaged.strip():
            diff_text += "\n# === unstaged changes ===\n" + unstaged
        _, stat_text, _ = _run_git(repo_path, ["diff", "HEAD", "--stat"])

    return diff_text, stat_text, ""


def build_review_prompt(diff_text: str, stat_text: str, focus: str, diff_ref: str = "") -> str:
    focus_line = (
        f"The author specifically asked you to focus on: {focus}\n"
        if focus.strip() else ""
    )

    # Tell the model EXACTLY what commit-state it is looking at. A git diff of
    # the working tree shows UNCOMMITTED changes — describing them as
    # "committed" is factually wrong and the #1 false-positive this agent used
    # to produce.
    if diff_ref.strip():
        commit_state = (
            f"COMMIT-STATE: the diff below is `git diff {diff_ref}` — changes that "
            f"are already part of committed history (relative to {diff_ref}). It is "
            "valid to call these 'committed'.\n"
        )
    else:
        commit_state = (
            "COMMIT-STATE: the diff below is the UNCOMMITTED working tree and "
            "staged area (`git diff HEAD` + `git diff --staged`). NOTHING here is in "
            "any commit yet. You MUST NOT describe anything in this diff as "
            "'committed', 'committed to source', or 'pushed' — at most it is "
            "'staged' or 'present in the working tree'.\n"
        )

    # This project (Tlamatini) keeps local credentials in its config files in
    # the working copy and scrubs them to placeholders before any commit. Teach
    # the reviewer that convention so it stops mis-reporting the developer's
    # local keys as leaked/committed secrets.
    secrets_note = (
        "SECRET-HANDLING CONVENTION FOR THIS REPO: the files `agent/config.json` "
        "and `agent/agents/*/config.yaml` legitimately hold local credentials in "
        "the developer's working copy (the 'keyed' mode). Before any commit/push "
        "they are scrubbed back to `<NAME goes here>` placeholders by "
        "`regen_secrets.py --mode push-able`; the real values live only in "
        "`data.keys`, which is gitignored. The committed and pushed versions of "
        "those files therefore contain ONLY placeholders. So:\n"
        "  - A `<...goes here>` placeholder or an empty string is NOT a secret — "
        "never flag it.\n"
        "  - Real-looking credentials in those specific managed files inside an "
        "UNCOMMITTED diff are the expected local 'keyed' state — they are NOT a "
        "leak and are NOT committed. Do NOT report them as 'API keys/passwords "
        "committed to source'. At most emit ONE low-severity informational note "
        "reminding the author to run `regen_secrets.py --mode push-able` before "
        "committing.\n"
        "  - You MUST still hard-flag genuine secrets hard-coded into SOURCE CODE "
        "(.py/.js/.ts/...), secrets in any file outside that managed config set, "
        "and any secret that truly appears in committed history.\n"
    )

    return (
        "You are a rigorous, fair senior software engineer performing a code "
        "review. Review the unified diff below for correctness/logic bugs, "
        "security vulnerabilities (injection, hard-coded secrets, missing authz, "
        "unsafe deserialization), performance problems, and "
        "readability/maintainability issues.\n\n"
        f"{commit_state}\n"
        f"{secrets_note}\n"
        f"{focus_line}"
        "RESPONSE FORMAT — follow exactly:\n"
        "1. The FIRST line MUST be one of:\n"
        "   VERDICT: APPROVE\n"
        "   VERDICT: REQUEST_CHANGES\n"
        "   VERDICT: COMMENT\n"
        "   Use REQUEST_CHANGES if there is any critical or high-severity issue; "
        "COMMENT for only minor issues; APPROVE if the change is sound.\n"
        "2. Then a short summary paragraph.\n"
        "3. Then a bulleted list of findings, each as: "
        "[SEVERITY] file:line — issue — suggested fix.\n"
        "Only comment on lines present in the diff. Do not invent files.\n\n"
        f"CHANGED FILES:\n{stat_text}\n\n"
        f"UNIFIED DIFF:\n{diff_text}\n"
    )


def parse_verdict(review_text: str) -> str:
    """Extract the verdict from the first non-empty line. Defaults to COMMENT."""
    for line in review_text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        upper = stripped.upper()
        if upper.startswith("VERDICT:"):
            candidate = upper.split(":", 1)[1].strip()
            for verdict in VALID_VERDICTS:
                if candidate.startswith(verdict):
                    return verdict
        break
    # Fallback: scan whole text for a verdict token.
    upper_all = review_text.upper()
    for verdict in ("REQUEST_CHANGES", "APPROVE", "COMMENT"):
        if verdict in upper_all:
            return verdict
    return "COMMENT"


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
        repo_path = str(config.get('repo_path', '.') or '.')
        diff_ref = str(config.get('diff_ref', '') or '')
        focus = str(config.get('focus', '') or '')
        max_diff_chars = int(config.get('max_diff_chars', 60000) or 60000)
        llm_config = config.get('llm', {}) or {}
        host = llm_config.get('host', 'http://localhost:11434')
        model = llm_config.get('model', 'llama3')
        target_agents = config.get('target_agents', []) or []

        logging.info("🔍 REVIEWER AGENT STARTED")
        logging.info(f"📂 Repo: {repo_path}")
        logging.info(f"📌 Diff ref: {diff_ref or '(working tree)'}")
        logging.info(f"🤖 Model: {model} @ {host}")
        logging.info(f"🎯 Targets: {target_agents}")
        logging.info("=" * 60)

        verdict = "COMMENT"
        review_text = ""
        status = "ok"
        error_msg = ""

        diff_text, stat_text, diff_err = resolve_diff(repo_path, diff_ref)

        if diff_err:
            status = "error"
            error_msg = diff_err
            review_text = f"Could not resolve diff: {diff_err}"
            logging.error(f"❌ {diff_err}")
        elif not diff_text.strip():
            review_text = "No changes to review for the configured diff ref."
            logging.info("ℹ️ Empty diff — nothing to review.")
        else:
            if len(diff_text) > max_diff_chars:
                logging.info(
                    f"✂️ Diff is {len(diff_text)} chars; truncating to "
                    f"{max_diff_chars} for the LLM."
                )
                diff_text = diff_text[:max_diff_chars] + "\n...[diff truncated]"
            prompt = build_review_prompt(diff_text, stat_text, focus, diff_ref)
            logging.info(f"📝 Sending review prompt ({len(prompt)} chars) to {model}...")
            try:
                review_text = query_ollama(host, model, prompt)
                verdict = parse_verdict(review_text)
                logging.info(f"✅ Review received ({len(review_text)} chars). Verdict: {verdict}")
            except RuntimeError as e:
                status = "error"
                error_msg = str(e)
                review_text = f"LLM review failed: {e}"
                logging.error(f"❌ LLM query failed: {e}")

        # Atomic single-call section emission (parametrizer parser rule:
        # each section must be one logging.info() call).
        logging.info(
            "INI_SECTION_REVIEWER<<<\n"
            f"repo_path: {repo_path}\n"
            f"diff_ref: {diff_ref}\n"
            f"verdict: {verdict}\n"
            f"model: {model}\n"
            f"status: {status}\n"
            f"error: {error_msg}\n"
            f"\n"
            f"{review_text}\n"
            ">>>END_SECTION_REVIEWER"
        )

        # Always trigger downstream agents (success OR error) so flows can
        # route on the section's verdict/status via Parametrizer or Forker.
        total_triggered = 0
        if target_agents:
            wait_for_agents_to_stop(target_agents)
            logging.info(f"🚀 Triggering {len(target_agents)} downstream agents...")
            for target in target_agents:
                if start_agent(target):
                    total_triggered += 1

        logging.info(f"🏁 Reviewer finished. Triggered {total_triggered}/{len(target_agents)} agents.")

    except Exception as e:
        logging.error(f"❌ Reviewer agent error: {e}")
    finally:
        time.sleep(0.4)
        remove_pid_file()

    sys.exit(0)


if __name__ == "__main__":
    main()
