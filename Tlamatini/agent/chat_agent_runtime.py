import os
import shutil
import subprocess
import sys
import time
import uuid
from datetime import timedelta

import psutil
from django.utils import timezone

from .global_state import global_state
from .models import ChatAgentRun


CHAT_RUNTIME_ROOT_NAME = "__chat_runs__"
RUNNING_STATUSES = {"created", "running"}
FINAL_STATUSES = {"completed", "failed", "stopped"}
RUNTIME_IGNORE_FILES = {
    "agent.pid",
    "agent.status",
    "notification.json",
    "reanim.pos",
}


def _get_agents_root() -> str:
    if getattr(sys, "frozen", False):
        return os.path.join(os.path.dirname(sys.executable), "agents")
    module_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(module_dir, "agents")


def get_chat_runtime_root() -> str:
    return os.path.join(_get_agents_root(), "pools", CHAT_RUNTIME_ROOT_NAME)


def ensure_chat_runtime_root() -> str:
    runtime_root = get_chat_runtime_root()
    os.makedirs(runtime_root, exist_ok=True)
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
            return candidate

    if getattr(sys, "frozen", False):
        bundled = os.path.join(
            os.path.dirname(sys.executable),
            "python.exe" if sys.platform.startswith("win") else "python3",
        )
        if os.path.isfile(bundled):
            return bundled
        return "python" if sys.platform.startswith("win") else "python3"

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


def create_isolated_runtime_copy(template_dir: str, runtime_prefix: str) -> tuple[str, str, str]:
    runtime_root = ensure_chat_runtime_root()
    run_id = uuid.uuid4().hex
    runtime_name = f"{runtime_prefix}__chat__{run_id[:12]}"
    runtime_dir = os.path.join(runtime_root, runtime_name)
    shutil.copytree(template_dir, runtime_dir, ignore=_copytree_ignore)
    return run_id, runtime_dir, _runtime_log_path(runtime_dir)


def resolve_runtime_script_path(runtime_dir: str, template_dir_name: str) -> str | None:
    primary = os.path.join(runtime_dir, f"{template_dir_name}.py")
    if os.path.isfile(primary):
        return primary

    candidates: list[str] = []
    with os.scandir(runtime_dir) as entries:
        for entry in entries:
            if entry.is_file() and entry.name.endswith(".py") and entry.name != "__init__.py":
                candidates.append(os.path.abspath(entry.path))
    if len(candidates) == 1:
        return candidates[0]
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

    process = subprocess.Popen([python_executable, script_path], **kwargs)
    run.pid = process.pid
    run.status = "running"
    run.save(update_fields=["pid", "status"])
    _set_handle(run.runId, process)
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


def list_chat_agent_runs(*, limit: int = 20) -> list[ChatAgentRun]:
    runs = list(ChatAgentRun.objects.order_by("-startedAt")[:limit])
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
