import itertools
import logging
import os
import shutil
import subprocess
import sys
import threading
import time
import uuid
from datetime import timedelta

import psutil
from django.utils import timezone

from .config_loader import get_int_config_value
from .global_state import global_state
from .models import ChatAgentRun

logger = logging.getLogger(__name__)


CHAT_RUNTIME_ROOT_NAME = "_chat_runs_"
DEFAULT_CHAT_AGENT_LIMIT_RUNS = 256
RUNNING_STATUSES = {"created", "running"}
FINAL_STATUSES = {"completed", "failed", "stopped"}

# Thread-safe global sequence counter so every runtime copy gets a unique,
# monotonically increasing index that shows execution order at a glance.
_run_sequence_lock = threading.Lock()
_run_sequence_counter = itertools.count(1)
_run_sequence_initialized = False

RUNTIME_IGNORE_FILES = {
    "agent.pid",
    "agent.status",
    "notification.json",
    "reanim.pos",
}


def _get_agents_root() -> str:
    if getattr(sys, "frozen", False):
        root = os.path.join(os.path.dirname(sys.executable), "agents")
        logger.info("[ChatRuntime._get_agents_root] FROZEN mode -> agents_root = %s", root)
    else:
        module_dir = os.path.dirname(os.path.abspath(__file__))
        root = os.path.join(module_dir, "agents")
        logger.info("[ChatRuntime._get_agents_root] SOURCE mode -> module_dir = %s, agents_root = %s", module_dir, root)
    logger.info("[ChatRuntime._get_agents_root] agents_root exists? %s", os.path.isdir(root))
    return root


def get_chat_runtime_root() -> str:
    root = os.path.join(_get_agents_root(), "pools", CHAT_RUNTIME_ROOT_NAME)
    logger.info("[ChatRuntime.get_chat_runtime_root] chat_runtime_root = %s", root)
    logger.info("[ChatRuntime.get_chat_runtime_root] exists? %s", os.path.isdir(root))
    return root


def _initialize_sequence_from_existing(runtime_root: str) -> None:
    """Seed the sequence counter from existing directories so that a server
    restart never reuses a sequence number from a previous session."""
    global _run_sequence_counter, _run_sequence_initialized
    if _run_sequence_initialized:
        return
    with _run_sequence_lock:
        if _run_sequence_initialized:
            return
        max_seq = 0
        try:
            if os.path.isdir(runtime_root):
                import re
                seq_pattern = re.compile(r"^.+_(\d{3,})_[0-9a-f]+$")
                for entry in os.scandir(runtime_root):
                    if entry.is_dir():
                        match = seq_pattern.match(entry.name)
                        if match:
                            seq_val = int(match.group(1))
                            if seq_val > max_seq:
                                max_seq = seq_val
        except Exception as exc:
            logger.warning("[ChatRuntime._initialize_sequence] Could not scan existing dirs: %s", exc)
        _run_sequence_counter = itertools.count(max_seq + 1)
        _run_sequence_initialized = True
        logger.info("[ChatRuntime._initialize_sequence] Sequence counter initialized to start at %d", max_seq + 1)


def ensure_chat_runtime_root() -> str:
    runtime_root = get_chat_runtime_root()
    already_exists = os.path.isdir(runtime_root)
    logger.info("[ChatRuntime.ensure_chat_runtime_root] runtime_root = %s, already_exists = %s", runtime_root, already_exists)
    try:
        os.makedirs(runtime_root, exist_ok=True)
        logger.info("[ChatRuntime.ensure_chat_runtime_root] os.makedirs OK -> directory now exists? %s", os.path.isdir(runtime_root))
    except Exception as exc:
        logger.error("[ChatRuntime.ensure_chat_runtime_root] FAILED to create runtime_root: %s -> %s", runtime_root, exc)
        raise
    _initialize_sequence_from_existing(runtime_root)
    return runtime_root


def _copytree_ignore(_dir: str, names: list[str]) -> set[str]:
    ignored: set[str] = set()
    for name in names:
        lowered = name.lower()
        if name in RUNTIME_IGNORE_FILES or lowered == "__pycache__":
            ignored.add(name)
            continue
        if lowered.endswith(".log") or lowered.endswith(".pos") or lowered.endswith(".flg"):
            ignored.add(name)
    return ignored


def _resolve_python_executable() -> str:
    python_home = os.environ.get("PYTHON_HOME", "").strip()
    if python_home:
        candidate = os.path.join(
            python_home,
            "python.exe" if sys.platform.startswith("win") else "python3",
        )
        if os.path.isfile(candidate):
            logger.info("[ChatRuntime._resolve_python_executable] Using PYTHON_HOME: %s", candidate)
            return candidate
        logger.info("[ChatRuntime._resolve_python_executable] PYTHON_HOME set to %s but candidate %s not found", python_home, candidate)

    if getattr(sys, "frozen", False):
        bundled = os.path.join(
            os.path.dirname(sys.executable),
            "python.exe" if sys.platform.startswith("win") else "python3",
        )
        if os.path.isfile(bundled):
            logger.info("[ChatRuntime._resolve_python_executable] FROZEN mode, using bundled: %s", bundled)
            return bundled
        fallback = "python" if sys.platform.startswith("win") else "python3"
        logger.info("[ChatRuntime._resolve_python_executable] FROZEN mode, bundled not found at %s, falling back to PATH: %s", bundled, fallback)
        return fallback

    logger.info("[ChatRuntime._resolve_python_executable] SOURCE mode, using sys.executable: %s", sys.executable)
    return sys.executable


def _build_child_env() -> dict:
    env = os.environ.copy()

    if sys.platform.startswith("win"):
        try:
            import ctypes

            if hasattr(ctypes.windll.kernel32, "SetDllDirectoryW"):
                ctypes.windll.kernel32.SetDllDirectoryW(None)
        except Exception:
            pass

    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        meipass = getattr(sys, "_MEIPASS")
        if meipass:
            path_parts = env.get("PATH", "").split(os.pathsep)
            path_parts = [
                part
                for part in path_parts
                if os.path.normpath(part) != os.path.normpath(meipass)
            ]
            env["PATH"] = os.pathsep.join(path_parts)

    return env


def _handle_state_key(run_id: str) -> str:
    return f"chat_agent_run_handle_{run_id}"


def _get_handle(run_id: str):
    return global_state.get_state(_handle_state_key(run_id))


def _set_handle(run_id: str, process) -> None:
    global_state.set_state(_handle_state_key(run_id), process)


def _clear_handle(run_id: str) -> None:
    global_state.set_state(_handle_state_key(run_id), None)


def _is_live_process(pid: int | None):
    if not pid:
        return None
    try:
        process = psutil.Process(pid)
        if process.status() == psutil.STATUS_ZOMBIE:
            return None
        return process
    except Exception:
        return None


def _read_runtime_pid(runtime_dir: str) -> int | None:
    pid_path = os.path.join(runtime_dir, "agent.pid")
    if not os.path.exists(pid_path):
        return None
    try:
        with open(pid_path, "r", encoding="utf-8") as file_handle:
            return int(file_handle.read().strip())
    except Exception:
        return None


def _runtime_log_path(runtime_dir: str) -> str:
    runtime_name = os.path.basename(os.path.abspath(runtime_dir))
    return os.path.join(runtime_dir, f"{runtime_name}.log")


def _next_run_sequence() -> int:
    """Return the next globally unique run sequence number (thread-safe)."""
    with _run_sequence_lock:
        return next(_run_sequence_counter)


def create_isolated_runtime_copy(template_dir: str, runtime_prefix: str) -> tuple[str, str, str]:
    logger.info("[ChatRuntime.create_isolated_runtime_copy] CALLED with template_dir = %s, runtime_prefix = %s", template_dir, runtime_prefix)
    logger.info("[ChatRuntime.create_isolated_runtime_copy] template_dir exists? %s, is_dir? %s", os.path.exists(template_dir), os.path.isdir(template_dir))

    # List template contents for debugging
    if os.path.isdir(template_dir):
        try:
            template_contents = os.listdir(template_dir)
            logger.info("[ChatRuntime.create_isolated_runtime_copy] template_dir contents: %s", template_contents)
        except Exception as exc:
            logger.warning("[ChatRuntime.create_isolated_runtime_copy] Could not list template_dir: %s", exc)

    runtime_root = ensure_chat_runtime_root()
    run_id = uuid.uuid4().hex
    short_id = run_id[:8]
    seq = _next_run_sequence()

    # Build a unique directory name that preserves execution order:
    #   {prefix}_{sequence:03d}_{short_run_id}
    # e.g. executer_001_a1b2c3d4, executer_002_e5f6g7h8
    # This ensures every run gets its own directory — failed runs are
    # never overwritten, so the user can inspect the full history.
    runtime_name = f"{runtime_prefix}_{seq:03d}_{short_id}"
    runtime_dir = os.path.join(runtime_root, runtime_name)
    log_path = _runtime_log_path(runtime_dir)

    logger.info("[ChatRuntime.create_isolated_runtime_copy] runtime_root = %s", runtime_root)
    logger.info("[ChatRuntime.create_isolated_runtime_copy] run_id = %s (short: %s)", run_id, short_id)
    logger.info("[ChatRuntime.create_isolated_runtime_copy] sequence = %d", seq)
    logger.info("[ChatRuntime.create_isolated_runtime_copy] runtime_dir = %s", runtime_dir)
    logger.info("[ChatRuntime.create_isolated_runtime_copy] log_path = %s", log_path)

    try:
        shutil.copytree(template_dir, runtime_dir, ignore=_copytree_ignore)
        logger.info("[ChatRuntime.create_isolated_runtime_copy] shutil.copytree SUCCESS -> runtime_dir exists? %s", os.path.isdir(runtime_dir))
    except Exception as exc:
        logger.error("[ChatRuntime.create_isolated_runtime_copy] shutil.copytree FAILED: template=%s -> runtime=%s, error: %s", template_dir, runtime_dir, exc)
        raise

    # List the copied runtime contents for debugging
    if os.path.isdir(runtime_dir):
        try:
            runtime_contents = os.listdir(runtime_dir)
            logger.info("[ChatRuntime.create_isolated_runtime_copy] runtime_dir contents after copy: %s", runtime_contents)
        except Exception as exc:
            logger.warning("[ChatRuntime.create_isolated_runtime_copy] Could not list runtime_dir: %s", exc)
    else:
        logger.error("[ChatRuntime.create_isolated_runtime_copy] runtime_dir DOES NOT EXIST after copytree: %s", runtime_dir)

    return run_id, runtime_dir, log_path


def resolve_runtime_script_path(runtime_dir: str, template_dir_name: str) -> str | None:
    logger.info("[ChatRuntime.resolve_runtime_script_path] runtime_dir = %s, template_dir_name = %s", runtime_dir, template_dir_name)
    primary = os.path.join(runtime_dir, f"{template_dir_name}.py")
    logger.info("[ChatRuntime.resolve_runtime_script_path] primary script path = %s, exists? %s", primary, os.path.isfile(primary))
    if os.path.isfile(primary):
        return primary

    candidates: list[str] = []
    with os.scandir(runtime_dir) as entries:
        for entry in entries:
            if entry.is_file() and entry.name.endswith(".py") and entry.name != "__init__.py":
                candidates.append(os.path.abspath(entry.path))
    logger.info("[ChatRuntime.resolve_runtime_script_path] fallback .py candidates: %s", candidates)
    if len(candidates) == 1:
        return candidates[0]
    logger.warning("[ChatRuntime.resolve_runtime_script_path] Could not resolve script: primary not found, %d candidates", len(candidates))
    return None


def register_chat_agent_run(
    *,
    run_id: str,
    tool_description: str,
    template_dir: str,
    runtime_dir: str,
    log_path: str,
    request_text: str,
) -> ChatAgentRun:
    logger.info("[ChatRuntime.register_chat_agent_run] Registering run:")
    logger.info("[ChatRuntime.register_chat_agent_run]   run_id            = %s", run_id)
    logger.info("[ChatRuntime.register_chat_agent_run]   tool_description  = %s", tool_description)
    logger.info("[ChatRuntime.register_chat_agent_run]   template_dir      = %s", template_dir)
    logger.info("[ChatRuntime.register_chat_agent_run]   runtime_dir       = %s", runtime_dir)
    logger.info("[ChatRuntime.register_chat_agent_run]   log_path          = %s", log_path)
    logger.info("[ChatRuntime.register_chat_agent_run]   runtime_dir exists? %s", os.path.isdir(runtime_dir))
    logger.info("[ChatRuntime.register_chat_agent_run]   request_text      = %.200s", request_text)
    return ChatAgentRun.objects.create(
        runId=run_id,
        toolDescription=tool_description,
        templateAgentDir=template_dir,
        runtimeDir=runtime_dir,
        logPath=log_path,
        requestText=request_text,
        status="created",
    )


def start_chat_agent_subprocess(run: ChatAgentRun, script_path: str):
    python_executable = _resolve_python_executable()
    logger.info("[ChatRuntime.start_chat_agent_subprocess] python_executable = %s", python_executable)
    logger.info("[ChatRuntime.start_chat_agent_subprocess] python_executable exists? %s", os.path.isfile(python_executable) if os.path.isabs(python_executable) else "PATH-relative")
    logger.info("[ChatRuntime.start_chat_agent_subprocess] script_path = %s", script_path)
    logger.info("[ChatRuntime.start_chat_agent_subprocess] script_path exists? %s", os.path.isfile(script_path))
    logger.info("[ChatRuntime.start_chat_agent_subprocess] cwd (runtimeDir) = %s", run.runtimeDir)
    logger.info("[ChatRuntime.start_chat_agent_subprocess] cwd exists? %s", os.path.isdir(run.runtimeDir))

    child_env = _build_child_env()
    kwargs = {
        "cwd": run.runtimeDir,
        "env": child_env,
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
        "stdin": subprocess.DEVNULL,
    }

    if sys.platform.startswith("win"):
        kwargs["creationflags"] = (
            subprocess.CREATE_NEW_PROCESS_GROUP
            | subprocess.CREATE_NO_WINDOW
            | subprocess.DETACHED_PROCESS
        )
    else:
        kwargs["start_new_session"] = True

    logger.info("[ChatRuntime.start_chat_agent_subprocess] Launching: %s %s (cwd=%s)", python_executable, script_path, run.runtimeDir)
    process = subprocess.Popen([python_executable, script_path], **kwargs)
    run.pid = process.pid
    run.status = "running"
    run.save(update_fields=["pid", "status"])
    _set_handle(run.runId, process)
    logger.info("[ChatRuntime.start_chat_agent_subprocess] Process launched with PID = %d, run_id = %s", process.pid, run.runId)
    return process


def reconcile_chat_agent_run(run: ChatAgentRun) -> ChatAgentRun:
    changed_fields: list[str] = []
    process = _is_live_process(run.pid)

    if process is None:
        runtime_pid = _read_runtime_pid(run.runtimeDir)
        if runtime_pid and runtime_pid != run.pid:
            runtime_process = _is_live_process(runtime_pid)
            if runtime_process is not None:
                run.pid = runtime_pid
                run.status = "running"
                changed_fields.extend(["pid", "status"])
                process = runtime_process

    if process is not None:
        if run.status != "running":
            run.status = "running"
            changed_fields.append("status")
    elif run.status in RUNNING_STATUSES:
        handle = _get_handle(run.runId)
        exit_code = None
        if handle is not None:
            try:
                exit_code = handle.poll()
            except Exception:
                exit_code = None

        if exit_code is not None:
            run.exitCode = exit_code
            run.status = "completed" if exit_code == 0 else "failed"
            changed_fields.extend(["exitCode", "status"])
            _clear_handle(run.runId)
        else:
            run.status = "completed"
            changed_fields.append("status")
        if run.finishedAt is None:
            run.finishedAt = timezone.now()
            changed_fields.append("finishedAt")

    if changed_fields:
        run.save(update_fields=changed_fields)
    return run


def tail_runtime_log(log_path: str, *, max_lines: int = 80, max_chars: int = 12000) -> str:
    if not log_path or not os.path.exists(log_path):
        return ""
    try:
        with open(log_path, "r", encoding="utf-8", errors="replace") as file_handle:
            lines = file_handle.readlines()
        excerpt = "".join(lines[-max_lines:])
        if len(excerpt) > max_chars:
            excerpt = excerpt[-max_chars:]
        return excerpt.strip()
    except Exception as exc:
        return f"<log read error: {exc}>"


def wait_briefly_for_initial_state(run: ChatAgentRun, *, seconds: int) -> ChatAgentRun:
    deadline = time.time() + max(seconds, 0)
    while time.time() < deadline:
        reconcile_chat_agent_run(run)
        if run.status in FINAL_STATUSES:
            return run
        time.sleep(0.35)
    return reconcile_chat_agent_run(run)


def get_chat_agent_run(run_id: str) -> ChatAgentRun | None:
    if not run_id:
        return None
    try:
        return ChatAgentRun.objects.get(runId=run_id)
    except ChatAgentRun.DoesNotExist:
        return None


def get_chat_agent_limit_runs() -> int:
    return get_int_config_value(
        "chat_agent_limit_runs",
        DEFAULT_CHAT_AGENT_LIMIT_RUNS,
        minimum=1,
    )


def list_chat_agent_runs(*, limit: int | None = None) -> list[ChatAgentRun]:
    if limit is None:
        effective_limit = get_chat_agent_limit_runs()
    else:
        try:
            effective_limit = max(int(limit), 1)
        except (TypeError, ValueError):
            effective_limit = get_chat_agent_limit_runs()
    runs = list(ChatAgentRun.objects.order_by("-startedAt")[:effective_limit])
    return [reconcile_chat_agent_run(run) for run in runs]


def _terminate_process_tree(process) -> dict:
    try:
        parent = psutil.Process(process.pid)
    except psutil.NoSuchProcess:
        return {"stopped_pids": [], "surviving_pids": [], "errors": []}

    errors: list[str] = []
    seen: set[int] = set()
    ordered: list[psutil.Process] = []
    try:
        children = parent.children(recursive=True)
    except Exception:
        children = []

    for item in children + [parent]:
        if item.pid not in seen:
            seen.add(item.pid)
            ordered.append(item)

    for item in reversed(ordered):
        try:
            item.terminate()
        except psutil.NoSuchProcess:
            continue
        except Exception as exc:
            errors.append(f"terminate {item.pid}: {exc}")

    _gone, alive = psutil.wait_procs(ordered, timeout=3)
    if alive:
        for item in alive:
            try:
                item.kill()
            except psutil.NoSuchProcess:
                continue
            except Exception as exc:
                errors.append(f"kill {item.pid}: {exc}")
        _gone, alive = psutil.wait_procs(alive, timeout=3)

    gone_ids = sorted(process.pid for process in _gone)
    alive_ids = sorted(process.pid for process in alive)
    return {"stopped_pids": gone_ids, "surviving_pids": alive_ids, "errors": errors}


def stop_chat_agent_run(run: ChatAgentRun) -> dict:
    run = reconcile_chat_agent_run(run)
    process = _is_live_process(run.pid)
    if process is None:
        runtime_pid = _read_runtime_pid(run.runtimeDir)
        process = _is_live_process(runtime_pid)

    termination = {"stopped_pids": [], "surviving_pids": [], "errors": []}
    if process is not None:
        termination = _terminate_process_tree(process)

    if not termination["surviving_pids"]:
        run.status = "stopped"
        run.finishedAt = timezone.now()
        run.save(update_fields=["status", "finishedAt"])
        _clear_handle(run.runId)

    return termination


def serialize_chat_agent_run(run: ChatAgentRun, *, include_log_excerpt: bool = False) -> dict:
    run = reconcile_chat_agent_run(run)
    payload = {
        "run_id": run.runId,
        "tool_description": run.toolDescription,
        "template_agent": run.templateAgentDir,
        "runtime_dir": run.runtimeDir,
        "log_path": run.logPath,
        "pid": run.pid,
        "status": run.status,
        "exit_code": run.exitCode,
        "started_at": run.startedAt.isoformat() if run.startedAt else None,
        "finished_at": run.finishedAt.isoformat() if run.finishedAt else None,
    }
    if include_log_excerpt:
        payload["log_excerpt"] = tail_runtime_log(run.logPath)
    return payload


def prune_old_chat_runs(*, keep_days: int = 7) -> int:
    cutoff = timezone.now() - timedelta(days=max(keep_days, 1))
    stale_runs = list(ChatAgentRun.objects.filter(startedAt__lt=cutoff))
    for run in stale_runs:
        reconcile_chat_agent_run(run)
        if run.status in RUNNING_STATUSES:
            continue
        try:
            if run.runtimeDir and os.path.isdir(run.runtimeDir):
                shutil.rmtree(run.runtimeDir, ignore_errors=True)
        except Exception:
            pass
        run.delete()
    return len(stale_runs)
