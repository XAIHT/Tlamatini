# Tlamatini — Created by Angela López Mendoza · @angelahack1
# Tlamatini Author Banner — do not remove
"""Direct resident Whisperer bridge. No speech/model imports in Django."""
import atexit
import hmac
import json
import logging
import os
import secrets
import socket
import subprocess
import sys
import threading
import time

from .path_guard import get_app_temp_root
from .services.agent_paths import get_agents_root

log = logging.getLogger(__name__)
MAX_FRAME = 131072
TERMINAL_EVENTS = frozenset({"result", "empty", "error", "cancelled"})


def worker_launch():
    """Use the same source/carried interpreter boundary as wrapped agents."""
    from .chat_agent_runtime import _resolve_python_executable
    executable = _resolve_python_executable()
    if getattr(sys, "frozen", False) and not os.path.isfile(executable):
        raise RuntimeError("Tlamatini's carried Python is missing. Repair the installation.")
    script = get_agents_root() / "whisperer" / "chat_worker.py"
    if not script.is_file():
        raise RuntimeError("The Whisperer chat worker is missing from this installation.")
    return executable, script


class VoiceRuntime:
    def __init__(self):
        self._startup = threading.Lock()
        self._state = threading.Lock()
        self._write = threading.Lock()
        self.connection = None
        self.process = None
        self.active = None
        self.options = {}
        self._options_lock = threading.Lock()
        self._options_received = threading.Event()

    def ensure_ready(self):
        with self._startup:
            if self.connection is not None:
                return
            executable, script = worker_launch()
            token = secrets.token_hex(32)
            env = os.environ.copy()
            env["TLAMATINI_VOICE_TOKEN"] = token
            env["TLAMATINI_TEMP"] = get_app_temp_root()
            env["PYTHONUNBUFFERED"] = "1"
            env["PYTHONIOENCODING"] = "utf-8"
            # The child must not inherit the frozen web process's DLL directory.
            if getattr(sys, "frozen", False):
                bundle = os.path.normcase(str(getattr(sys, "_MEIPASS", "")))
                env["PATH"] = os.pathsep.join(p for p in env.get("PATH", "").split(os.pathsep)
                                            if os.path.normcase(p) != bundle)
                for key in ("PYTHONHOME", "PYTHONPATH"):
                    env.pop(key, None)
                if os.name == "nt":
                    import ctypes
                    ctypes.windll.kernel32.SetDllDirectoryW(None)
            with socket.socket() as listener:
                listener.bind(("127.0.0.1", 0))
                listener.listen(2)
                listener.settimeout(30)
                port = listener.getsockname()[1]
                # This is an internal product service, not a developer test console.
                # Windows must never create a second console or steal chat focus,
                # including when the packaged parent has no console handles.
                flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
                self.process = subprocess.Popen(
                    [executable, "-u", str(script), str(port)],
                    cwd=str(script.parent), env=env, creationflags=flags,
                    stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace")
                threading.Thread(target=self._relay_output, args=(self.process,),
                                 name="chat-whisperer-log", daemon=True).start()
                deadline = time.monotonic() + 30
                connection = None
                reader = None
                candidate = None
                try:
                    while time.monotonic() < deadline:
                        candidate, _ = listener.accept()
                        candidate.settimeout(10)
                        reader = candidate.makefile("rb")
                        hello = json.loads(reader.readline(MAX_FRAME + 1))
                        if not hmac.compare_digest(str(hello.get("token", "")), token):
                            reader.close()
                            candidate.close()
                            continue
                        connection = candidate
                        ready = json.loads(reader.readline(MAX_FRAME + 1))
                        if ready.get("event") != "ready":
                            raise RuntimeError("Whisperer did not become ready.")
                        self.options = {key: ready[key] for key in ("devices", "defaults", "devices_error")
                                        if key in ready}
                        connection.settimeout(None)
                        self.connection = connection
                        threading.Thread(target=self._read, args=(connection, reader),
                                         name="chat-whisperer-events", daemon=True).start()
                        log.info("Direct Whisperer worker ready; microphone remains closed.")
                        return
                    raise TimeoutError("Whisperer startup timed out.")
                except Exception:
                    if reader:
                        reader.close()
                    if candidate:
                        candidate.close()
                    process, self.process = self.process, None
                    self._stop_process(process)
                    raise

    @staticmethod
    def _relay_output(process):
        """Drain worker diagnostics into the application's existing console/log."""
        if process.stdout is None:
            return
        try:
            with process.stdout as output:
                for line in output:
                    message = line.rstrip()
                    if message:
                        log.info("[Whisperer] %s", message)
        except (OSError, ValueError):
            log.exception("Could not read Whisperer diagnostics.")

    @staticmethod
    def _stop_process(process):
        """Reap this runtime's child; never leave a shell or worker behind."""
        if process is None:
            return
        try:
            process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            process.terminate()
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=2)

    def _send(self, message):
        payload = (json.dumps(message) + "\n").encode("utf-8")
        with self._write:
            connection = self.connection
            if connection is None:
                raise RuntimeError("Whisperer is disconnected.")
            connection.sendall(payload)

    def get_options(self, refresh=False):
        """Refresh device/config metadata without opening a microphone."""
        if not refresh:
            return self.options.copy()
        with self._options_lock:
            self.ensure_ready()
            self._options_received.clear()
            self._send({"action": "options"})
            if not self._options_received.wait(5):
                raise TimeoutError("Microphone input list is unavailable.")
            return self.options.copy()

    def start(self, run_id, emit, capture_settings=None):
        self.ensure_ready()
        with self._state:
            if self.active is not None:
                raise RuntimeError("The microphone is already in use by another dictation.")
            self.active = (run_id, emit)
        try:
            self._send({"action": "start", "run_id": run_id, "settings": capture_settings or {}})
        except Exception:
            with self._state:
                self.active = None
            raise

    def cancel(self, run_id):
        with self._state:
            active = self.active
        if active and active[0] == run_id:
            try:
                self._send({"action": "cancel", "run_id": run_id})
            except (OSError, RuntimeError):
                pass

    def _read(self, connection, reader):
        try:
            while True:
                line = reader.readline(MAX_FRAME + 1)
                if not line:
                    break
                if len(line) > MAX_FRAME:
                    raise ValueError("Oversized Whisperer frame.")
                event = json.loads(line)
                if event.get("event") == "options":
                    self.options = {key: event[key] for key in ("devices", "defaults", "devices_error")
                                    if key in event}
                    self._options_received.set()
                    continue
                with self._state:
                    active = self.active
                    if not active or event.get("run_id") != active[0]:
                        continue
                    if event.get("event") in TERMINAL_EVENTS:
                        self.active = None
                active[1](event)
        except Exception:
            log.exception("Direct Whisperer connection failed.")
        finally:
            reader.close()
            connection.close()
            with self._state:
                active = None
                if self.connection is connection:
                    self.connection = None
                    active, self.active = self.active, None
            if active:
                active[1]({"event": "error", "run_id": active[0],
                           "message": "Whisperer disconnected. Your draft is unchanged."})

    def close(self):
        with self._startup:
            connection = self.connection
            if connection:
                try:
                    self._send({"action": "shutdown"})
                    connection.shutdown(socket.SHUT_RDWR)
                except (OSError, RuntimeError):
                    pass
                connection.close()
            process, self.process = self.process, None
            self._stop_process(process)


runtime = VoiceRuntime()
atexit.register(runtime.close)
