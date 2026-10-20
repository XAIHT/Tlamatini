# Tlamatini — Created by Angela López Mendoza · @angelahack1
# Tlamatini Author Banner — do not remove
"""The Django-side home of the Terminater terminals.

One ``TerminalHub`` (the engine in ``agents/terminater/terminater_engine.py``)
lives in the Django process.  Three things talk to it:

  * the browser   -> ``terminal_consumer.TerminalConsumer`` (``ws/terminals/``),
                     authenticated by the user's session;
  * pool agents   -> ``terminal_views.terminater_api_view`` over loopback HTTP,
                     authenticated by a per-run token that only a same-machine,
                     same-user process can read (``rendezvous_path()``);
  * the in-process Prompt Flow Panel runner -> ``get_hub().call(...)`` directly.

The engine file is loaded BY PATH from the agents tree instead of being imported
as ``agent.agents...``: that tree ships loose next to the executable in a frozen
build, travels with every pool copy of the template, and keeps ONE definition of
the engine for the web process, the pool agent and the test suites.

CONTRACTS (do NOT weaken)
-------------------------
1. Nothing in this module raises into a caller that merely asks a question:
   ``live_pids()`` / ``hub_status()`` are fail-open, because the process reapers
   call them on their hot path.
2. ``live_pids()`` never CREATES the hub -- a reaper must not spawn machinery.
3. The token is compared in constant time and never logged.
4. Every shell is killed (whole tree) when Tlamatini exits.
"""

from __future__ import annotations

import atexit
import hmac
import importlib.util
import json
import logging
import os
import re
import secrets
import sys
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger(__name__)

_ENGINE: Any = None
_HUB: Any = None
_LOCK = threading.RLock()
_TOKEN: str = ""
_PORT: int = 0
_ATEXIT_DONE = False

ENV_TOKEN = "TLAMATINI_TERMINATER_TOKEN"
ENV_URL = "TLAMATINI_TERMINATER_URL"
RENDEZVOUS_NAME = ".terminater_hub.json"


# --------------------------------------------------------------------------- #
# Loading the engine                                                           #
# --------------------------------------------------------------------------- #

def engine_dir() -> Path:
    from .services.agent_paths import get_agents_root

    return get_agents_root() / "terminater"


def load_engine() -> Any:
    """Import ``terminater_engine`` from the agents tree (once). Raises RuntimeError."""
    global _ENGINE
    with _LOCK:
        if _ENGINE is not None:
            return _ENGINE
        existing = sys.modules.get("terminater_engine")
        if existing is not None and hasattr(existing, "TerminalHub"):
            _ENGINE = existing
            return _ENGINE
        folder = engine_dir()
        path = folder / "terminater_engine.py"
        if not path.is_file():
            raise RuntimeError(f"Terminater engine not found at {path}")
        if str(folder) not in sys.path:
            sys.path.insert(0, str(folder))
        spec = importlib.util.spec_from_file_location("terminater_engine", str(path))
        if spec is None or spec.loader is None:
            raise RuntimeError(f"Terminater engine cannot be loaded from {path}")
        module = importlib.util.module_from_spec(spec)
        sys.modules["terminater_engine"] = module
        try:
            spec.loader.exec_module(module)
        except Exception:
            sys.modules.pop("terminater_engine", None)
            raise
        _ENGINE = module
        return _ENGINE


def _cfg(key: str, default: Any) -> Any:
    try:
        from .config_loader import get_config_value

        value = get_config_value(key, default)
        return default if value is None or value == "" else value
    except Exception:  # noqa: BLE001
        return default


def terminals_enabled() -> bool:
    return bool(_cfg("terminater_enabled", True))


def _auto_max_terminals() -> int:
    """Sized from the machine, never from the core count alone (design-for-modest-PCs).

    Each terminal costs two threads, a shell and a console host: on a 4-core box
    with little RAM a dozen is a lot; on a workstation it is nothing.
    """
    cores = os.cpu_count() or 4
    wanted = min(12, max(4, cores))
    try:
        import psutil  # type: ignore

        gib = psutil.virtual_memory().total / (1024 ** 3)
        if gib < 6:
            wanted = min(wanted, 4)
        elif gib < 10:
            wanted = min(wanted, 6)
    except Exception:  # noqa: BLE001
        pass
    return wanted


def get_hub() -> Any:
    """The one hub of this process (created on first use)."""
    global _HUB
    with _LOCK:
        if _HUB is not None:
            return _HUB
        engine = load_engine()
        try:
            max_terminals = int(_cfg("terminater_max_terminals", 0)) or _auto_max_terminals()
        except (TypeError, ValueError):
            max_terminals = _auto_max_terminals()
        try:
            hang = float(_cfg("terminater_hang_seconds", engine.HANG_SECONDS_DEFAULT))
        except (TypeError, ValueError):
            hang = engine.HANG_SECONDS_DEFAULT
        _HUB = engine.TerminalHub(max_terminals=max_terminals, hang_seconds=hang)
        _register_exit()
        logger.info("--- [TERMINATER] hub ready: up to %s terminals, hang window %ss", max_terminals, hang)
        return _HUB


def hub_exists() -> bool:
    return _HUB is not None


def _register_exit() -> None:
    global _ATEXIT_DONE
    if _ATEXIT_DONE:
        return
    _ATEXIT_DONE = True
    atexit.register(shutdown)


def shutdown() -> None:
    """Kill every shell (whole tree).  Safe to call twice."""
    global _HUB
    hub = _HUB
    _HUB = None
    if hub is not None:
        try:
            hub.shutdown()
        except Exception:  # noqa: BLE001
            logger.exception("--- [TERMINATER] shutdown failed")
    try:
        path = rendezvous_path()
        if path.is_file():
            data = json.loads(path.read_text(encoding="utf-8"))
            if data.get("pid") == os.getpid():
                path.unlink()
    except Exception:  # noqa: BLE001
        pass


# --------------------------------------------------------------------------- #
# Guards (the reapers call these)                                              #
# --------------------------------------------------------------------------- #

def live_pids() -> Set[int]:
    """PIDs of live terminal shells + their descendants. Never creates the hub."""
    out: Set[int] = set()
    hub = _HUB
    if hub is None:
        return out
    try:
        for pid in hub.live_pids():
            out.add(int(pid))
            try:
                import psutil  # type: ignore

                for child in psutil.Process(pid).children(recursive=True):
                    out.add(int(child.pid))
            except Exception:  # noqa: BLE001
                pass
    except Exception:  # noqa: BLE001
        return set()
    return out


# --------------------------------------------------------------------------- #
# Rendezvous: how a pool agent finds this hub                                  #
# --------------------------------------------------------------------------- #

def rendezvous_path() -> Path:
    try:
        from .path_guard import get_app_temp_root

        root = Path(get_app_temp_root())
    except Exception:  # noqa: BLE001
        root = Path(os.environ.get("TLAMATINI_TEMP") or os.path.join(os.getcwd(), "Temp"))
    return root / RENDEZVOUS_NAME


def _discover_port() -> int:
    if _PORT:
        return _PORT
    argv = " ".join(sys.argv)
    m = re.search(r"(?:runserver|startserver)\s+(?:\S*:)?(\d{2,5})\b", argv)
    if m:
        return int(m.group(1))
    try:
        return int(_cfg("django_port", 8000))
    except (TypeError, ValueError):
        return 8000


def note_server_port(port: int) -> None:
    """The consumer/view learned the port Django REALLY listens on: publish it."""
    global _PORT
    try:
        port = int(port)
    except (TypeError, ValueError):
        return
    if port and port != _PORT:
        _PORT = port
        ensure_ready()


def ensure_ready() -> Dict[str, str]:
    """Create the token, export it to this process's environment (so every pool
    agent inherits it) and publish the rendezvous file.  Cheap and idempotent."""
    global _TOKEN
    with _LOCK:
        if not _TOKEN:
            _TOKEN = secrets.token_urlsafe(32)
        url = f"http://127.0.0.1:{_discover_port()}"
        os.environ[ENV_TOKEN] = _TOKEN
        os.environ[ENV_URL] = url
        try:
            path = rendezvous_path()
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(".tmp")
            tmp.write_text(json.dumps({"url": url, "token": _TOKEN, "pid": os.getpid(),
                                       "written": time.time()}), encoding="utf-8")
            os.replace(tmp, path)
            try:
                os.chmod(path, 0o600)
            except OSError:
                pass
        except Exception:  # noqa: BLE001 -- the env vars alone already serve spawned agents
            logger.warning("--- [TERMINATER] could not write the rendezvous file", exc_info=True)
        return {"url": url, "token": _TOKEN}


def token_ok(candidate: str) -> bool:
    expected = _TOKEN
    if not expected or not candidate:
        return False
    return hmac.compare_digest(str(candidate).encode("utf-8"), expected.encode("utf-8"))


# --------------------------------------------------------------------------- #
# The API (used by the loopback view, the Prompt Flow runner and the tests)    #
# --------------------------------------------------------------------------- #

def run_action(action: str, params: Optional[Dict[str, Any]] = None, wait: bool = True) -> Dict[str, Any]:
    """Run one action.  Slow ones return ``{"job": id}`` unless ``wait``."""
    if not terminals_enabled():
        return {"ok": False, "status": "refused", "code": "disabled",
                "message": "Terminater is switched off (terminater_enabled=false)."}
    try:
        hub = get_hub()
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "status": "unavailable", "code": "hub_unavailable",
                "message": f"The terminal hub could not start: {exc}"}
    params = dict(params or {})
    name = re.sub(r"[\s\-]+", "_", str(action or "").strip().lower())
    engine = load_engine()
    name = engine._ACTION_ALIASES.get(name, name)
    if name == "ping":
        return {"ok": True, "status": "listed", "pong": True, "pid": os.getpid(),
                "conpty": engine._cp.conpty_available()}
    if name == "job":
        job = hub.job(str(params.get("id") or params.get("job") or ""))
        if job.get("state") == "done":
            res = dict(job["result"] or {})
            res["job_state"] = "done"
            return res
        return {"ok": True, "job_state": job.get("state", "unknown"), "status": "started"}
    if wait or name not in hub.SLOW:
        return hub.call(name, params)
    return {"ok": True, "job": hub.submit(name, params), "job_state": "running", "status": "started"}


def hub_status(user: Optional[str] = None) -> Dict[str, Any]:
    """Cheap, fail-open summary used by the page and the tests."""
    try:
        if _HUB is None:
            return {"hub": False, "terminals": []}
        return {"hub": True, **_HUB.call("list", {"user": user})}
    except Exception as exc:  # noqa: BLE001
        return {"hub": False, "error": str(exc), "terminals": []}


def terminal_kinds() -> List[str]:
    try:
        return list(load_engine().available_kinds())
    except Exception:  # noqa: BLE001
        return []


def reset_for_tests() -> None:  # pragma: no cover - used by the suites only
    shutdown()
    global _TOKEN
    _TOKEN = ""
