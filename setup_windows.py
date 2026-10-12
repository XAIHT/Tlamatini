# Tlamatini Author Banner — Angela López Mendoza · @angelahack1
"""Small, explicitly scoped Windows setup primitives; no application imports."""
import base64
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys


def file_lock_description(path):
    """Ask Restart Manager who holds this file; never close another program."""
    if sys.platform != "win32":
        return ""
    class UniqueProcess(ctypes.Structure):
        _fields_ = [("pid", wintypes.DWORD), ("started", wintypes.FILETIME)]
    class ProcessInfo(ctypes.Structure):
        _fields_ = [("process", UniqueProcess), ("name", wintypes.WCHAR * 256),
                    ("service", wintypes.WCHAR * 64), ("kind", wintypes.DWORD),
                    ("status", wintypes.ULONG), ("session", wintypes.DWORD),
                    ("restartable", wintypes.BOOL)]
    session = wintypes.DWORD()
    manager = ctypes.WinDLL("Rstrtmgr")
    if manager.RmStartSession(ctypes.byref(session), 0, ctypes.create_unicode_buffer(33)):
        return ""
    try:
        paths = (wintypes.LPCWSTR * 1)(os.fspath(path))
        if manager.RmRegisterResources(session, 1, paths, 0, None, 0, None):
            return ""
        needed, count, reason = wintypes.UINT(), wintypes.UINT(), wintypes.DWORD()
        for _ in range(3):
            rows = (ProcessInfo * count.value)() if count.value else None
            result = manager.RmGetList(session, ctypes.byref(needed), ctypes.byref(count), rows, ctypes.byref(reason))
            if result == 0:
                return ", ".join(f"{row.name or 'Process'} (PID {row.process.pid})" for row in (rows or ())[:count.value])
            if result != 234 or needed.value > 1024:
                break
            count.value = needed.value
        return ""
    except OSError:
        return ""
    finally:
        manager.RmEndSession(session)


class WindowsSnapshot:
    """Restore product keys and selected shared values, never UserChoice."""
    TREES = (
        r"Software\Classes\Tlamatini.FlowFile",
        r"Software\Classes\Tlamatini.PromptFlowFile",
        r"Software\Classes\SystemAgent.FlowFile",
        r"Software\Tlamatini\FlowCapabilities",
        r"Software\Tlamatini\FileTypes",
        r"Software\Microsoft\Windows\CurrentVersion\Uninstall\Tlamatini",
    )
    VALUES = [(r"Software\RegisteredApplications", "TlamatiniFlows")] + [
        (r"Software\XAIHT\Tlamatini", name) for name in (
            "InstallLocation", "AgentsRoot", "SourceAgentsRoot", "AgentManifestPath", "Version", "AgentCatalogVersion")
    ] + [(rf"Software\Classes\{ext}", "") for ext in (".flw", ".fpmt")] + [
        (prefix+rf"\{ext}\OpenWithProgids", prog)
        for prefix in (r"Software\Classes", r"Software\Microsoft\Windows\CurrentVersion\Explorer\FileExts")
        for ext, prog in ((".flw", "Tlamatini.FlowFile"), (".flw", "SystemAgent.FlowFile"), (".fpmt", "Tlamatini.PromptFlowFile"))
    ]

    def __init__(self, folder):
        self.folder = Path(folder)

    @staticmethod
    def desktop_shortcut():
        # CSIDL_DESKTOPDIRECTORY respects redirected / OneDrive desktops.
        buffer = ctypes.create_unicode_buffer(32768)
        result = ctypes.windll.shell32.SHGetFolderPathW(None, 0x10, None, 0, buffer)
        if result != 0 or not buffer.value:
            raise RuntimeError("Windows could not resolve the Desktop folder")
        return Path(buffer.value) / "Tlamatini.lnk"

    @staticmethod
    def _encode(value, kind):
        return {"type": kind, "binary": isinstance(value, bytes),
                "value": base64.b64encode(value).decode("ascii") if isinstance(value, bytes) else value}

    @staticmethod
    def _read_value(path, name):
        import winreg
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, path) as key:
                return WindowsSnapshot._encode(*winreg.QueryValueEx(key, name))
        except FileNotFoundError:
            return None

    @staticmethod
    def _tree(path):
        import winreg
        result = {}
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, path) as key:
                subkeys, values, _ = winreg.QueryInfoKey(key)
                result[""] = {name: WindowsSnapshot._encode(value, kind)
                              for name, value, kind in (winreg.EnumValue(key, i) for i in range(values))}
                children = [winreg.EnumKey(key, i) for i in range(subkeys)]
            for child in children:
                for suffix, values in WindowsSnapshot._tree(path+"\\"+child).items():
                    result[child+("\\"+suffix if suffix else "")] = values
        except FileNotFoundError:
            pass
        return result

    def capture(self):
        from setup_recovery import atomic_json
        shortcut = self.desktop_shortcut()
        data = {"trees": {path: self._tree(path) for path in self.TREES},
                "values": [[path, name, self._read_value(path, name)] for path, name in self.VALUES],
                "shortcut": shortcut.is_file()}
        if data["shortcut"]:
            shutil.copy2(shortcut, self.folder / "desktop.lnk")
        atomic_json(self.folder / "windows.json", data)

    @staticmethod
    def _set(path, name, record):
        import winreg
        if record is None:
            try:
                with winreg.OpenKey(winreg.HKEY_CURRENT_USER, path, 0, winreg.KEY_SET_VALUE) as key:
                    winreg.DeleteValue(key, name)
            except FileNotFoundError:
                pass
            WindowsSnapshot._remove_empty(path)
        else:
            value = base64.b64decode(record["value"]) if record["binary"] else record["value"]
            with winreg.CreateKey(winreg.HKEY_CURRENT_USER, path) as key:
                winreg.SetValueEx(key, name, 0, record["type"], value)

    @staticmethod
    def _remove_empty(path):
        import winreg
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, path) as key:
                children, values, _ = winreg.QueryInfoKey(key)
            if not children and not values:
                winreg.DeleteKey(winreg.HKEY_CURRENT_USER, path)
        except FileNotFoundError:
            pass

    def restore(self):
        data = json.loads((self.folder / "windows.json").read_text(encoding="utf-8"))
        if set(data["trees"]) != set(self.TREES):
            raise RuntimeError("Recovery registry scope differs from the product allowlist")
        if [(p, n) for p, n, _ in data["values"]] != self.VALUES:
            raise RuntimeError("Recovery registry values differ from the product allowlist")
        for path, before in data["trees"].items():
            current = self._tree(path)
            for suffix in set(before) | set(current):
                if any(part in (".", "..", "") for part in suffix.split("\\")) and suffix:
                    raise RuntimeError("Unsafe registry recovery suffix")
                full = path + ("\\"+suffix if suffix else "")
                wanted = before.get(suffix, {})
                for name in set(wanted) | set(current.get(suffix, {})):
                    self._set(full, name, wanted.get(name))
            for suffix in sorted(set(current)-set(before), key=len, reverse=True):
                self._remove_empty(path+("\\"+suffix if suffix else ""))
        for path, name, record in data["values"]:
            self._set(path, name, record)
        shortcut = self.desktop_shortcut()
        if data["shortcut"]:
            shutil.copy2(self.folder / "desktop.lnk", shortcut)
        elif shortcut.is_file():
            shortcut.unlink()
        ctypes.windll.shell32.SHChangeNotify(0x08000000, 0, None, None)


class HelperJob:
    """Kill only this helper's process tree when its bounded lifetime ends."""
    def __init__(self):
        class IO(ctypes.Structure):
            _fields_ = [(name, ctypes.c_ulonglong) for name in (
                "ReadOperationCount", "WriteOperationCount", "OtherOperationCount",
                "ReadTransferCount", "WriteTransferCount", "OtherTransferCount")]
        class Basic(ctypes.Structure):
            _fields_ = [("PerProcessUserTimeLimit", ctypes.c_longlong), ("PerJobUserTimeLimit", ctypes.c_longlong),
                        ("LimitFlags", wintypes.DWORD), ("MinimumWorkingSetSize", ctypes.c_size_t),
                        ("MaximumWorkingSetSize", ctypes.c_size_t), ("ActiveProcessLimit", wintypes.DWORD),
                        ("Affinity", ctypes.c_size_t), ("PriorityClass", wintypes.DWORD), ("SchedulingClass", wintypes.DWORD)]
        class Extended(ctypes.Structure):
            _fields_ = [("BasicLimitInformation", Basic), ("IoInfo", IO),
                        ("ProcessMemoryLimit", ctypes.c_size_t), ("JobMemoryLimit", ctypes.c_size_t),
                        ("PeakProcessMemoryUsed", ctypes.c_size_t), ("PeakJobMemoryUsed", ctypes.c_size_t)]
        self.kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        self.kernel.CreateJobObjectW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p]
        self.kernel.CreateJobObjectW.restype = ctypes.c_void_p
        self.kernel.SetInformationJobObject.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
        self.kernel.AssignProcessToJobObject.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        self.kernel.CloseHandle.argtypes = [ctypes.c_void_p]
        self.handle = self.kernel.CreateJobObjectW(None, None)
        if not self.handle:
            raise ctypes.WinError(ctypes.get_last_error())
        limits = Extended()
        limits.BasicLimitInformation.LimitFlags = 0x2000  # KILL_ON_JOB_CLOSE, no breakaway
        if not self.kernel.SetInformationJobObject(self.handle, 9, ctypes.byref(limits), ctypes.sizeof(limits)):
            self.close()
            raise ctypes.WinError(ctypes.get_last_error())

    def assign(self, process):
        if not self.kernel.AssignProcessToJobObject(self.handle, int(process._handle)):
            raise ctypes.WinError(ctypes.get_last_error())

    def close(self):
        if self.handle:
            self.kernel.CloseHandle(self.handle)
            self.handle = None


def run_powershell(script, *, env=None, timeout=120):
    """No interactive prompts, bounded child-process job, no product console flash.

    The visible product wizard owns helper status. Only frozen windowed clients
    suppress an extra helper console; source development calls inherit their
    verified visible console. Neither branch targets unrelated processes.
    """
    script = Path(script).resolve(strict=True)
    executable = Path(os.environ["SystemRoot"]) / "System32/WindowsPowerShell/v1.0/powershell.exe"
    job = HelperJob()
    process = None
    try:
        # The helper cannot start its script (or spawn descendants) before it
        # belongs to the job. Quoting is PowerShell literal-string quoting.
        quoted = str(script).replace("'", "''")
        gate = ("if ([Console]::ReadLine() -ne 'TLAMATINI_SETUP_READY') { exit 125 }; "
                "$ErrorActionPreference = 'Stop'; try { & '" + quoted + "'; "
                "if (-not $?) { exit 1 }; exit $LASTEXITCODE } catch { "
                "[Console]::Error.WriteLine($_.Exception.Message); exit 1 }")
        encoded = base64.b64encode(gate.encode("utf-16le")).decode("ascii")
        process = subprocess.Popen(
            [str(executable), "-NoLogo", "-NoProfile", "-NonInteractive",
             "-ExecutionPolicy", "Bypass", "-EncodedCommand", encoded],
            cwd=script.parent, env=env, stdin=subprocess.PIPE,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, errors="replace",
            close_fds=True,
            creationflags=(subprocess.CREATE_NO_WINDOW
                           if getattr(sys, "frozen", False) and not ctypes.windll.kernel32.GetConsoleWindow()
                           else 0),
        )
        try:
            job.assign(process)
        except Exception:
            process.kill()
            process.wait(timeout=5)
            raise RuntimeError("Windows could not contain the setup helper. No helper was allowed to continue.")
        try:
            output, error = process.communicate(input="TLAMATINI_SETUP_READY\n", timeout=timeout)
        except subprocess.TimeoutExpired as exc:
            job.close()  # Close inherited writers too, before draining their pipes.
            try:
                process.communicate(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
            raise RuntimeError(f"{script.name} exceeded {timeout} seconds. Its helper processes were stopped; retry after checking Windows permissions.") from exc
        if process.returncode:
            raise RuntimeError(f"{script.name} failed (exit {process.returncode}):\n{(error.strip() or output.strip())[-4000:]}")
        if output.strip():
            print(output.strip(), flush=True)
        return output
    finally:
        job.close()
        if process is not None:
            for stream in (process.stdin, process.stdout, process.stderr):
                if stream is not None:
                    stream.close()
