# Tlamatini Author Banner — Angela López Mendoza · @angelahack1
"""Private local setup transcripts, including for windowed executables."""
from datetime import datetime
import os
from pathlib import Path
import sys
import threading

LOG_PATH = None


def registry_context(phase):
    """Log only setup ownership and hive identity, never user configuration."""
    if sys.platform != "win32":
        return
    try:
        import ctypes
        from ctypes import wintypes
        import json
        import winreg
        native = ctypes.WinDLL("ntdll")
        native.NtQueryKey.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p,
                                     wintypes.ULONG, ctypes.POINTER(wintypes.ULONG)]
        native.NtQueryKey.restype = wintypes.LONG
        def key_name(handle):
            size = wintypes.ULONG()
            native.NtQueryKey(wintypes.HANDLE(int(handle)), 3, None, 0, ctypes.byref(size))
            if not 4 <= size.value <= 65536:
                return "unavailable"
            buffer = ctypes.create_string_buffer(size.value)
            code = native.NtQueryKey(wintypes.HANDLE(int(handle)), 3, buffer, size.value, ctypes.byref(size))
            if code:
                return f"unavailable ({code})"
            length = int.from_bytes(buffer.raw[:4], "little")
            return buffer.raw[4:4+length].decode("utf-16le")
        data = {"phase": phase, "pid": os.getpid(), "thread": threading.get_native_id()}
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Software") as current:
            data["current_user_hive"] = key_name(current)
        path = r"Software\Microsoft\Windows\CurrentVersion\Uninstall\Tlamatini"
        data["registry_reads"] = []
        for selected in (path, path.rsplit("\\", 1)[0], r"Software\Classes\Tlamatini.FlowFile"):
            for view in (0, winreg.KEY_WOW64_32KEY, winreg.KEY_WOW64_64KEY):
                row = {"path": selected, "view": view}
                try:
                    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, selected, 0, winreg.KEY_READ | view) as key:
                        row["native_key"] = key_name(key)
                        if selected == path:
                            row["owner"] = winreg.QueryValueEx(key, "InstallLocation")[0]
                except OSError as exc:
                    row["error"] = {"type": type(exc).__name__, "winerror": exc.winerror, "message": str(exc)}
                data["registry_reads"].append(row)
        print("WINDOWS REGISTRY CONTEXT: " + json.dumps(data, ensure_ascii=True), flush=True)
    except Exception as exc:
        print(f"WINDOWS REGISTRY CONTEXT unavailable: {type(exc).__name__}: {exc}", flush=True)


def configure(operation):
    global LOG_PATH
    folder = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "Tlamatini/SetupLogs"
    try:
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / f"{datetime.now():%Y%m%d-%H%M%S}-{operation}-{os.getpid()}.log"
        stream = path.open("a", encoding="utf-8", buffering=1)
    except OSError:
        return  # Logging must never prevent recovery or removal.
    lock = threading.RLock()

    class Transcript:
        encoding = "utf-8"
        def __init__(self, console):
            self.console = console
        def write(self, text):
            with lock:
                try:
                    stream.write(text)
                except OSError:
                    pass
                if self.console is not None:
                    self.console.write(text)
            return len(text)
        def flush(self):
            with lock:
                try:
                    stream.flush()
                except OSError:
                    pass
                if self.console is not None:
                    self.console.flush()
        def isatty(self):
            return bool(self.console is not None and self.console.isatty())

    sys.stdout = Transcript(sys.stdout)
    sys.stderr = Transcript(sys.stderr)
    LOG_PATH = path
    print(f"Tlamatini {operation} | {datetime.now().isoformat(timespec='seconds')} | PID {os.getpid()}", flush=True)
    registry_context("client startup")


def result_detail(detail):
    return detail + (f"\n\nSetup log:\n{LOG_PATH}" if LOG_PATH else "")
