# ═══════════════════════════════════════════════════════════════════
#   ✦  T L A M A T I N I  ✦   —   "one who knows"
#
#   Created by  Angela López Mendoza   ·   @angelahack1
#   Developer · Architect · Creator of Tlamatini
#
#   Every line of this file was written by Angela López Mendoza.
# ═══════════════════════════════════════════════════════════════════
#   Tlamatini Author Banner — do not remove (releases scrub the name automatically)
# uninstall.py — Tlamatini Uninstaller
#
# GUI application that:
#   a) Removes all installed files EXCEPT the agents/ directory
#   b) Unregisters the .flw file association from the system
#   c) Removes desktop and local shortcuts
#
# The install path is auto-detected from CreateShortcut.json (next to the exe)
# or from the Windows registry (.flw association).  The user can also browse
# to select the directory manually.

import ctypes
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import threading
import tempfile
import time
from setup_wizard import WizardView, SetupDialog, button as wizard_button
from setup_recovery import Recovery, setup_lock, checked_path, remove_tree, atomic_json
from setup_windows import run_powershell
import tkinter as tk
from ctypes import wintypes
from tkinter import filedialog, messagebox
from uninstall_processes import owned_processes, main_application, stop_owned_workers

# Keep a retryable uninstaller and its registration helpers until all other
# application files and the owned Installed Apps entry have been removed.
UNINSTALL_SUPPORT_FILES = frozenset({
    "uninstaller.exe", "createshortcut.json", "tlamatini.ps1",
    "removeshortcut.ps1", "unregister_flw.ps1", "unregister_fpmt.ps1",
    "flow_file_associations.ps1",
})

# ─── Removing a file Windows still holds (the uninstaller's own EXE) ────────
# A file can be impossible to DELETE for a few seconds while it is perfectly
# possible to RENAME: antivirus scanning it, or Explorer / Settings reading its
# icon, map the EXE as an image, and Windows refuses DeleteFile ("Access is
# denied", WinError 5) on a mapped image while still allowing a move.  So the
# uninstaller does what professional uninstallers do instead of failing:
#   1. retry the delete for SUPPORT_DELETE_RETRY_SECONDS;
#   2. still held: MOVE it into a uniquely named PENDING folder inside the
#      installation, so the original name is free immediately;
#   3. when the uninstaller closes, a hidden cleanup (schedule_cleanup) deletes
#      that pending folder, the uninstaller's own Temp copy and the now-empty
#      installation folder, retrying until Windows lets go.
# The cleanup only ever deletes recursively a folder whose name carries one of
# the two random prefixes below, so a quick reinstall into the same folder can
# never lose its fresh Uninstaller.exe to a cleanup from the previous run.
SUPPORT_DELETE_RETRY_SECONDS = 8.0
UNINSTALL_TARGET_SECONDS = 180
UNINSTALL_LIMIT_SECONDS = 300
CLEANUP_RECEIPT = ".tlamatini-removal.json"
STAGING_PREFIX = "Tlamatini-Uninstaller-"
PENDING_PREFIX = ".tlamatini-uninstall-pending-"
CLEANUP_ATTEMPTS = 90          # one attempt every ~2 s: about three minutes
STALE_STAGING_SECONDS = 600    # older Temp copies are leftovers of past runs


def removal_cleanup_pending(target):
    """Recognize only completed removal, never an interrupted rollback."""
    if Recovery.removal_cleanup_pending(target):
        return True
    try:
        path = checked_path(target, CLEANUP_RECEIPT)
        with path.open(encoding="utf-8") as stream:
            receipt = json.load(stream)
        info = os.stat(target, follow_symlinks=False)
        return (receipt.get("schema") == 1 and receipt.get("state") == "removed"
                and receipt.get("identity") == [info.st_dev, info.st_ino]
                and os.path.normcase(receipt.get("target", "")) == os.path.normcase(os.path.abspath(target)))
    except (OSError, ValueError, RuntimeError):
        return False


# ─── Version resolution ───────────────────────────────────────────────────────
# Read the version from the running .exe's Win32 ProductVersion (frozen mode)
# so the GUI always matches the value PyInstaller's --version-file baked in.
# In source mode, derive from git tags (same precedence as
# Tlamatini/agent/version.py).  Empty string is valid; UI degrades gracefully.

def _read_exe_product_version(exe_path: str) -> str:
    """Read the Win32 ``ProductVersion`` string from an EXE's VERSIONINFO."""
    if sys.platform != "win32":
        return ""
    try:
        ver = ctypes.windll.version
        get_size = ver.GetFileVersionInfoSizeW
        get_size.argtypes = [wintypes.LPCWSTR, ctypes.POINTER(wintypes.DWORD)]
        get_size.restype = wintypes.DWORD

        get_info = ver.GetFileVersionInfoW
        get_info.argtypes = [wintypes.LPCWSTR, wintypes.DWORD,
                             wintypes.DWORD, ctypes.c_void_p]
        get_info.restype = wintypes.BOOL

        query = ver.VerQueryValueW
        query.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR,
                          ctypes.POINTER(ctypes.c_void_p),
                          ctypes.POINTER(wintypes.UINT)]
        query.restype = wintypes.BOOL

        handle = wintypes.DWORD(0)
        size = get_size(exe_path, ctypes.byref(handle))
        if not size:
            return ""

        buf = ctypes.create_string_buffer(size)
        if not get_info(exe_path, 0, size, buf):
            return ""

        for codepage in ("040904B0", "040904E4", "000004B0"):
            sub = f"\\StringFileInfo\\{codepage}\\ProductVersion"
            value = ctypes.c_void_p(0)
            length = wintypes.UINT(0)
            if query(buf, sub, ctypes.byref(value), ctypes.byref(length)):
                if value.value and length.value > 0:
                    return ctypes.wstring_at(value.value, length.value).rstrip("\x00")
    except Exception:
        return ""
    return ""


def _derive_version_from_git() -> str:
    """Return the most recent reachable ``v*`` tag, stripped of the ``v``."""
    try:
        cwd = os.path.dirname(os.path.abspath(__file__))
        result = subprocess.run(
            ["git", "describe", "--tags", "--abbrev=0", "--match", "v[0-9]*"],
            cwd=cwd, capture_output=True, text=True, timeout=5,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return ""
    if result.returncode != 0:
        return ""
    tag = (result.stdout or "").strip()
    return tag[1:] if tag.startswith("v") else tag


def resolve_version() -> str:
    """Resolve the running uninstaller's version (frozen→EXE, source→git)."""
    if getattr(sys, "frozen", False):
        version = _read_exe_product_version(sys.executable)
        if version:
            return version
    derived = _derive_version_from_git()
    if derived:
        return derived
    return ""


# ─── Is Tlamatini still running? ─────────────────────────────────────────────
# Uninstalling while Tlamatini is still up leaves half an installation behind:
# Windows refuses to delete a running .exe, a loaded .dll, or a file one of the
# pool agents still holds open — so the user ends up with a broken directory and
# nothing on screen explaining why.  The uninstaller therefore REFUSES to start
# while any process is running out of the very directory it is about to erase,
# and asks the user to close Tlamatini first (Ctrl+C in its console is the clean
# way, because that is what lets the Tier-3 reaper and the pool cleanup run).
#
# ⚠ FAIL-OPEN CONTRACT (do NOT weaken).  The gate blocks ONLY on positive,
# evidence-backed detection.  If the detector itself cannot run — an OS call
# fails, a future Windows, a non-Windows host — it reports "nothing found" and
# the uninstallation proceeds.  A detector that cannot run must never lock a
# user out of removing her own software, and the dialog deliberately offers no
# "continue anyway" button, so a false positive would be a dead end.

TH32CS_SNAPPROCESS = 0x00000002
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
_MAX_PATH_W = 260


class _PROCESSENTRY32W(ctypes.Structure):
    """Windows ``PROCESSENTRY32W`` — one entry of a Toolhelp process snapshot."""

    _fields_ = [
        ("dwSize",              wintypes.DWORD),
        ("cntUsage",            wintypes.DWORD),
        ("th32ProcessID",       wintypes.DWORD),
        ("th32DefaultHeapID",   ctypes.POINTER(ctypes.c_ulong)),
        ("th32ModuleID",        wintypes.DWORD),
        ("cntThreads",          wintypes.DWORD),
        ("th32ParentProcessID", wintypes.DWORD),
        ("pcPriClassBase",      ctypes.c_long),
        ("dwFlags",             wintypes.DWORD),
        ("szExeFile",           ctypes.c_wchar * _MAX_PATH_W),
    ]


def _kernel32():
    """Return kernel32 with the snapshot prototypes declared, or None."""
    try:
        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        k32.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
        k32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
        k32.Process32FirstW.argtypes = [wintypes.HANDLE,
                                        ctypes.POINTER(_PROCESSENTRY32W)]
        k32.Process32FirstW.restype = wintypes.BOOL
        k32.Process32NextW.argtypes = [wintypes.HANDLE,
                                       ctypes.POINTER(_PROCESSENTRY32W)]
        k32.Process32NextW.restype = wintypes.BOOL
        k32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        k32.OpenProcess.restype = wintypes.HANDLE
        k32.QueryFullProcessImageNameW.argtypes = [
            wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR,
            ctypes.POINTER(wintypes.DWORD),
        ]
        k32.QueryFullProcessImageNameW.restype = wintypes.BOOL
        k32.CloseHandle.argtypes = [wintypes.HANDLE]
        k32.CloseHandle.restype = wintypes.BOOL
        return k32
    except Exception:
        return None


def _process_image_path(k32, pid: int) -> str:
    """Full path of *pid*'s executable, or "" when Windows will not say."""
    try:
        handle = k32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    except Exception:
        return ""
    if not handle:
        return ""
    try:
        size = wintypes.DWORD(_MAX_PATH_W * 4)
        buf = ctypes.create_unicode_buffer(size.value)
        if k32.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size)):
            return buf.value
        return ""
    except Exception:
        return ""
    finally:
        try:
            k32.CloseHandle(handle)
        except Exception:
            pass


def iter_processes():
    """Yield ``(pid, image_name, image_path)`` for every process we can see.

    ``image_path`` is "" when Windows refuses to disclose it.  Never raises —
    an unavailable snapshot simply yields nothing (see the fail-open contract).
    """
    if sys.platform != "win32":
        return
    k32 = _kernel32()
    if k32 is None:
        return
    invalid = ctypes.c_void_p(-1).value
    try:
        snapshot = k32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    except Exception:
        return
    if not snapshot or snapshot == invalid:
        return
    try:
        entry = _PROCESSENTRY32W()
        entry.dwSize = ctypes.sizeof(_PROCESSENTRY32W)
        ok = k32.Process32FirstW(snapshot, ctypes.byref(entry))
        while ok:
            pid = int(entry.th32ProcessID)
            yield pid, str(entry.szExeFile), _process_image_path(k32, pid)
            ok = k32.Process32NextW(snapshot, ctypes.byref(entry))
    finally:
        try:
            k32.CloseHandle(snapshot)
        except Exception:
            pass


def _is_inside(path: str, directory: str) -> bool:
    """True when *path* lives inside *directory*, at any depth."""
    try:
        p = os.path.normcase(os.path.abspath(path))
        d = os.path.normcase(os.path.abspath(directory))
    except Exception:
        return False
    if not p or not d:
        return False
    return p == d or p.startswith(os.path.join(d, ""))


def own_image_path() -> str:
    """Normalised path of the image THIS uninstaller is running from."""
    try:
        raw = sys.executable if getattr(sys, "frozen", False) else (sys.argv[0] or "")
        return os.path.normcase(os.path.abspath(raw)) if raw else ""
    except Exception:
        return ""


def find_running_tlamatini(install_dir: str) -> list[dict]:
    """Every process running OUT OF *install_dir* — one record each.

    A record is ``{"pid": int, "name": str, "path": str, "evidence": str}``.

    The uninstaller's OWN process is never reported: ``Uninstaller.exe`` lives
    INSIDE the installation it removes, so without that exclusion the gate would
    detect itself and nobody could ever uninstall anything.  Returns an empty
    list both when nothing is running AND when detection is impossible.
    """
    if not install_dir or not os.path.isdir(install_dir):
        return []

    own_pid = os.getpid()
    own_path = own_image_path()

    # Top-level .exe names of the installation — used ONLY as a fallback for a
    # process whose image path Windows will not disclose.
    fallback_names = set()
    try:
        for entry in os.listdir(install_dir):
            if entry.lower().endswith(".exe"):
                fallback_names.add(entry.lower())
    except Exception:
        pass
    fallback_names.discard(os.path.basename(own_path))

    found: list[dict] = []
    try:
        for pid, name, path in iter_processes():
            if pid == own_pid or pid == 0:
                continue
            if path:
                if own_path and os.path.normcase(os.path.abspath(path)) == own_path:
                    continue  # a twin uninstaller is not a running Tlamatini
                if _is_inside(path, install_dir):
                    found.append({
                        "pid": pid, "name": name, "path": path,
                        "evidence": "running from the installation directory",
                    })
            elif name and name.lower() in fallback_names:
                found.append({
                    "pid": pid, "name": name, "path": "",
                    "evidence": "image path unreadable - matched by name",
                })
    except Exception:
        return []  # fail open: an unusable detector never blocks the user
    return found


# ─── Directories that survive the uninstallation ─────────────────────────────
# ``agents/`` is ALWAYS preserved (a companion app such as Tlamatini-FlowPills
# keeps reading it after the uninstall).  These six hold the user's OWN
# material — the projects loaded as context, whatever Tlamatini generated
# (content_generated/, doc_generated/), and Templates/ (the default home of
# every project the firmware/engine/document agents scaffold: STM32er, ESP32er,
# Arduiner, ESPHomer, Unrealer, LaTeXer — i.e. the user's own CODE) — so they
# are preserved TOO, but only when they actually hold something.  An empty one
# is installer scaffolding: it goes.
#
# Temp/ is NOT here on purpose: it is throwaway scratch and is ERASED with the
# rest of the installation (Angela, 2026-10-09: "and 'Temp' should be erased!").
#
# ⚠ Templates/ and doc_generated/ were MISSING here until 2026-10-09, while the
# self-update swap (apply_update.ps1 $Preserve) had always kept both.  Angela
# uninstalled C:\Tlamatini and lost the code she kept in Templates/.  Angela's
# rule: application, applications, content_generated, context_files,
# doc_generated and Templates are KEPT whenever they hold something.
PRESERVED_WHEN_NOT_EMPTY = (
    "application",
    "applications",
    "content_generated",
    "context_files",
    "doc_generated",
    "Templates",
)

_PRESERVED_WHEN_NOT_EMPTY_LOWER = frozenset(
    name.lower() for name in PRESERVED_WHEN_NOT_EMPTY
)


def directory_has_content(path: str) -> bool:
    """True when *path* holds at least one FILE, at any depth.

    ⚠ FAIL-SAFE — deliberately the OPPOSITE of the process gate above.  A
    directory we cannot read counts as "has content", because wrongly deleting
    the user's own material is the worst outcome available here, while wrongly
    keeping an empty folder costs nothing.  ``os.walk`` swallows permission
    errors silently, so they are captured through ``onerror`` rather than being
    mistaken for emptiness.
    """
    if not path or not os.path.isdir(path):
        return False
    unreadable = []
    try:
        for _root, _dirs, files in os.walk(
            path, onerror=lambda _err: unreadable.append(1),
        ):
            if files:
                return True
    except Exception:
        return True
    return bool(unreadable)


# ─── Color Palette (matches Installer) ──────────────────────────────────────
BG_DARK       = "#0f0f1a"
BG_PANEL      = "#1a1a2e"
BG_CARD       = "#16213e"
BG_INPUT      = "#0f3460"
FG_PRIMARY    = "#e0e0ff"
FG_SECONDARY  = "#8888aa"
FG_DIM        = "#555577"
ACCENT        = "#00d4ff"
ACCENT_HOVER  = "#00f0ff"
ACCENT_GLOW   = "#0099cc"
SUCCESS       = "#00e676"
WARNING       = "#ffab40"
ERROR         = "#ff5252"
BTN_BG        = "#0f3460"
BTN_HOVER     = "#1a4a8a"
BTN_CANCEL_BG = "#2a1a2e"
BTN_CANCEL_HV = "#3d2244"
PROGRESS_BG   = "#1a1a2e"
PROGRESS_FG   = "#ff5252"
BORDER_COLOR  = "#2a2a4e"
DANGER_BG     = "#3d1a1a"
DANGER_HV     = "#5a2a2a"

FONT_FAMILY   = "Segoe UI"


class FancyUninstaller:
    """Modern dark-themed uninstaller for Tlamatini."""

    # ── weighted uninstallation steps ────────────────────────────────
    STEPS = [
        ("Removing shortcuts…",                  0.10),
        ("Unregistering .flw and .fpmt file associations…", 0.15),
        ("Removing application files…",          0.65),
        ("Cleaning up…",                         0.05),
        ("Refreshing Windows Desktop…",          0.05),
    ]

    def __init__(self, root: tk.Tk):
        self.root = root
        self.version = resolve_version()
        title = f"Tlamatini Uninstaller v{self.version}" if self.version else "Tlamatini Uninstaller"
        self.root.title(title)
        self.install_path = tk.StringVar(value=self._detect_install_path())
        self._progress_value = 0.0
        self._uninstalling = False
        # Directories left untouched because they held the user's own content.
        # Written by the worker thread, read by the completion dialog — the
        # hand-off happens through root.after(), after the thread is done.
        self.preserved_dirs: list[str] = []
        # How many times the user pressed Retry on the still-running gate.
        self._gate_attempts = 0
        # Files Windows still held when they were removed; the hidden cleanup
        # deletes them after this window closes (see schedule_cleanup).
        self.removal_target = ""
        self.pending_dir = ""
        self.deferred_files: list[str] = []
        self.deferred_in_place: list[str] = []

        self._build_ui()

    # ─── Auto-detect install path ────────────────────────────────────
    @staticmethod
    def _detect_install_path() -> str:
        """Try to auto-detect the Tlamatini installation directory."""

        if len(sys.argv) == 3 and sys.argv[1] == "--install-dir":
            return os.path.abspath(sys.argv[2])

        # 1. Check for CreateShortcut.json next to this executable
        if getattr(sys, 'frozen', False):
            base = os.path.dirname(sys.executable)
        else:
            base = os.path.abspath(os.path.dirname(__file__))

        config_path = os.path.join(base, "CreateShortcut.json")
        if os.path.isfile(config_path):
            try:
                with open(config_path, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                install_dir = config.get("InstallDir", "")
                if install_dir and os.path.isdir(install_dir):
                    return install_dir
            except Exception:
                pass

        # Both current conhost commands and legacy PowerShell commands are valid.
        try:
            import winreg
            for prog_id in ('Tlamatini.FlowFile', 'Tlamatini.PromptFlowFile'):
                try:
                    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, rf'Software\Classes\{prog_id}') as key:
                        try:
                            candidate = winreg.QueryValueEx(key, 'TlamatiniInstallDir')[0]
                            if os.path.isfile(os.path.join(candidate, 'Uninstaller.exe')):
                                return candidate
                        except OSError:
                            pass
                    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, rf'Software\Classes\{prog_id}\shell\open\command') as key:
                        command = winreg.QueryValueEx(key, '')[0]
                    for quoted_path in re.findall(r'"([^"]+)"', command):
                        if os.path.basename(quoted_path).lower() in ('tlamatini.exe', 'tlamatini.ps1'):
                            candidate = os.path.dirname(quoted_path)
                            if os.path.isdir(candidate):
                                return candidate
                except OSError:
                    continue
        except ImportError:
            pass

        return ""

    # ─── UI Construction ─────────────────────────────────────────────
    def _build_ui(self):
        self.ui = WizardView(
            self.root, removal=True, version=self.version,
            path=self.install_path, steps=self.STEPS,
            start=self._start_uninstall, browse=self._browse,
            preserved=PRESERVED_WHEN_NOT_EMPTY,
        )
        # Keep the worker and existing integrations on their public UI handles.
        self.path_entry = self.ui.path_entry
        self.browse_btn = self.ui.browse_btn
        self.uninstall_btn = self.ui.primary_btn
        self.cancel_btn = self.ui.cancel_btn
        self.button_row = self.ui.button_row
        self.progress_frame = self.ui.progress_frame
        self.step_label = self.ui.step_label
        self.progress_bar = self.ui.progress_bar
        self.pct_label = self.ui.pct_label
        self.check_labels = self.ui.check_labels
        self.target_label = self.ui.target_label

    def _make_button(self, parent, text, command, width=14, small=False,
                     cancel=False, danger=False):
        return wizard_button(parent, text, command, primary=not cancel,
                             danger=danger, width=width)

    # ─── Path helper ─────────────────────────────────────────────────
    def _browse(self):
        path = filedialog.askdirectory(
            title="Select the Tlamatini installation directory",
        )
        if path:
            self.install_path.set(path)

    # ─── Validation ──────────────────────────────────────────────────
    def _validate_path(self) -> str | None:
        """Return the validated install dir path or None on failure.

        Existence + "does this look like a Tlamatini installation" only.  The
        still-running gate and the final confirmation run afterwards, in
        ``_start_uninstall``, in that order.
        """
        raw = self.install_path.get().strip()
        if not raw:
            messagebox.showwarning("No path selected",
                                   "Please select the installation directory.")
            return None

        if not os.path.isdir(raw):
            messagebox.showerror(
                "Invalid path",
                f"The directory does not exist:\n{raw}",
            )
            return None

        raw = os.path.abspath(raw)
        # A typo must never turn uninstall into removal of a drive, a shared
        # system directory, the development checkout, or a redirected folder.
        protected = {os.path.normcase(os.path.abspath(path)) for path in (
            os.path.expanduser("~"), os.environ.get("WINDIR", ""),
            os.environ.get("ProgramFiles", ""), os.environ.get("ProgramFiles(x86)", ""),
        ) if path}
        redirected = os.path.normcase(os.path.realpath(raw)) != os.path.normcase(raw)
        source_checkout = (os.path.exists(os.path.join(raw, ".git"))
                           or os.path.isfile(os.path.join(raw, "Tlamatini", "manage.py")))
        if (os.path.dirname(raw) == raw or os.path.normcase(raw) in protected
                or redirected or source_checkout):
            messagebox.showerror(
                "Invalid installation directory",
                "Select the installed Tlamatini folder. A drive root, shared system "
                "folder, source checkout or redirected directory cannot be uninstalled.",
            )
            return None

        # Check if it looks like a Tlamatini installation. Arbitrary directories
        # are never accepted, even if the user clicks through a warning.
        markers = ["Tlamatini.exe", "Tlamatini.ps1", "CreateShortcut.json"]
        found = (any(os.path.isfile(os.path.join(raw, m)) for m in markers)
                 or Recovery.pending(raw) or removal_cleanup_pending(raw))
        if not found:
            messagebox.showerror(
                "Not a Tlamatini installation",
                f"The selected directory does not appear to contain a "
                f"Tlamatini installation:\n{raw}\n\nSelect the installed application folder.",
            )
            return None

        return raw

    def _confirm_removal(self, raw: str) -> bool:
        """Last chance to back out.

        Asked AFTER the still-running gate, so the user is never made to confirm
        an uninstallation the uninstaller is about to refuse anyway.
        """
        if removal_cleanup_pending(raw) and not os.path.isfile(os.path.join(raw, "Tlamatini.exe")):
            return bool(messagebox.askyesno(
                "Finish Uninstallation", f"Tlamatini was already removed from:\n{raw}\n\n"
                "Finish removing the remaining temporary application files?\n"
                "Your preserved content and agents will remain untouched."))
        return bool(messagebox.askyesno(
            "Confirm Uninstallation",
            f"This will remove Tlamatini from:\n{raw}\n\n"
            "The agents/ directory is preserved — and so are application/, "
            "applications/, content_generated/, context_files/, doc_generated/ "
            "and Templates/ whenever they hold content.\n"
            "All other files will be permanently deleted.\n\n"
            "Remaining workers launched from this installation, including "
            "agents and their child processes, will be stopped.\n\n"
            "Do you want to continue?",
        ))

    # ─── Uninstallation thread ───────────────────────────────────────
    def _on_enter_key(self, event=None):
        return self.ui._enter(event)

    # ─── Still-running gate (modal — Retry / Exit, nothing else) ─────
    def _ensure_tlamatini_not_running(self, target: str) -> bool:
        """Refuse to uninstall while Tlamatini is still running.

        Returns True when nothing is running out of *target*, so the
        uninstallation may proceed.  Returns False otherwise — the user chose
        Exit (or closed the dialog, which counts as Exit) and the whole
        uninstaller has already been shut down.
        """
        running = self._blocking_processes(target)
        if not running:
            return True
        if self._show_running_gate(target, running):
            return True
        self._shutdown()
        return False

    @staticmethod
    def _blocking_processes(target):
        workers = {row["pid"] for row in owned_processes(target)
                   if not main_application(row, target)}
        # The main app must close normally. Proven leftover workers are stopped
        # only AFTER the user confirms removal, never merely by opening the GUI.
        return [row for row in find_running_tlamatini(target) if row["pid"] not in workers]

    def _show_running_gate(self, target: str, running: list[dict]) -> bool:
        """The modal dialog.  True = clear to proceed, False = Exit.

        Retry re-runs the detection IN PLACE: still running keeps the same
        dialog open and re-states what was found; clear closes it and the
        uninstallation continues.  There is deliberately no third button — a
        "continue anyway" would walk the user straight into the broken,
        half-deleted installation this gate exists to prevent.
        """
        self._gate_attempts = 0
        outcome = {"proceed": False}

        dialog = SetupDialog(
            self.root, "Tlamatini is still running", "Close Tlamatini to continue.",
            "Close the main application normally so it can finish its work. "
            "In the Tlamatini console, Ctrl+C requests a clean shutdown. Then select Retry.",
        )
        dlg = dialog.window
        headline, detail = dialog.headline, dialog.detail
        self.gate_headline_var, self.gate_detail_var = headline, detail
        detail_lbl = dialog.details
        btn_row = dialog.actions

        def _render(found: list[dict]):
            if self._gate_attempts:
                headline.set(
                    f"STILL RUNNING — retry #{self._gate_attempts} detected "
                    f"{len(found)} Tlamatini process(es) in:\n{target}"
                )
            else:
                headline.set(
                    f"{len(found)} Tlamatini process(es) are running in:\n{target}"
                )
            detail.set("\n".join(
                f"  {rec['name']}   (PID {rec['pid']})   {rec['evidence']}"
                for rec in found
            ))
            detail_lbl.config(fg=ERROR if self._gate_attempts else WARNING)

        def _retry():
            self._gate_attempts += 1
            still = self._blocking_processes(target)
            if not still:
                outcome["proceed"] = True
                dlg.destroy()
                return
            _render(still)
            try:
                dlg.bell()
            except Exception:
                pass

        def _exit():
            outcome["proceed"] = False
            dlg.destroy()

        self.gate_exit_btn = self._make_button(btn_row, "Exit", _exit,
                                               cancel=True)
        self.gate_exit_btn.pack(side="right", padx=(8, 0))
        self.gate_retry_btn = self._make_button(btn_row, "⟳  Retry", _retry,
                                                danger=True)
        self.gate_retry_btn.pack(side="right")

        _render(running)

        dlg.protocol("WM_DELETE_WINDOW", _exit)   # the titlebar X is Exit
        dlg.bind("<Return>", lambda _e: _retry())
        dlg.bind("<Escape>", lambda _e: _exit())
        self.gate_retry_btn.focus_set()

        dlg.update_idletasks()
        try:
            dlg.grab_set()      # modal: nothing else in the app answers
            dlg.lift()
            dlg.focus_force()
        except tk.TclError:
            pass
        self.root.wait_window(dlg)
        return bool(outcome["proceed"])

    def _shutdown(self):
        """Shut the uninstaller down completely (the gate's Exit button)."""
        try:
            self.root.destroy()
        except Exception:
            pass

    def _start_uninstall(self):
        if self._uninstalling or self.ui.state == "complete":
            return

        target = self._validate_path()
        if target is None:
            return

        # Nothing may be running out of the directory we are about to erase.
        # Exit inside the gate closes the uninstaller, so there is nothing to
        # clean up here — just stop.
        if not self._ensure_tlamatini_not_running(target):
            return

        if not self._confirm_removal(target):
            return

        self.preserved_dirs = []
        self._uninstalling = True
        self.ui.begin(target)

        t = threading.Thread(target=self._run_uninstall, args=(target,),
                             daemon=True)
        t.start()

    # ── Progress helpers (always marshal to main thread) ─────────────
    def _set_progress(self, value: float, status: str | None = None):
        if value is not None and getattr(self, "_removal_phase", False):
            value = .2 + .75 * value
        self._progress_value = value
        self.root.after(0, self._update_progress_ui, value, status)

    def _update_progress_ui(self, value: float, status: str | None):
        self.ui.update_progress(value, status)

    def _mark_step(self, idx: int, success: bool = True):
        self.root.after(0, self.ui.mark_step, idx, success)

    def _activate_step(self, idx: int):
        self.root.after(0, self.ui.activate_step, idx)

    # ─── Main uninstall pipeline (runs in background thread) ─────────
    def _run_uninstall(self, target: str):
        from setup_logging import registry_context
        registry_context("uninstallation worker start")
        recovery = None
        self._removal_phase = False
        self._uninstall_started = time.monotonic()
        self._cleanup_deadline = self._uninstall_started + UNINSTALL_LIMIT_SECONDS
        self.cleanup_warnings = []
        try:
            if removal_cleanup_pending(target) and not os.path.isfile(os.path.join(target, "Tlamatini.exe")):
                self._cleanup_recovery = Recovery(target)
                if self._cleanup_recovery.journal.exists():
                    self._cleanup_recovery.load()
                self.preserved_dirs = [name for name in PRESERVED_WHEN_NOT_EMPTY
                                       if directory_has_content(os.path.join(target, name))]
                self.removal_target = target
                self._run_cleanup_retry(target)
                return
            with setup_lock():
                self._set_progress(0, "Stopping remaining agent workers…")
                self.cleanup_report = stop_owned_workers(target)
                self._set_progress(0, "Inspecting installed files and preserved content…")
                recovery = Recovery(
                    target, lambda message: self._set_progress(getattr(self, "_progress_value", 0), message),
                    progress=lambda fraction: self._set_progress(.2 * fraction),
                    rollback_progress=lambda fraction: self._set_progress(fraction),
                )
                recovery.cleanup_deadline = self._cleanup_deadline
                if Recovery.pending(target):
                    self.root.after(0, self.ui.begin_recovery, "An interrupted setup operation must be restored before removal can continue.")
                    recovery.recover_previous()
                    self.root.after(0, lambda: self.ui.begin(target, reset_clock=False))
                else:
                    recovery.recover_previous()
                kept = ["agents"] + [name for name in PRESERVED_WHEN_NOT_EMPTY
                                     if directory_has_content(os.path.join(target, name))]
                recovery.prepare_removal(kept)
                self._recovery = recovery
                self._removal_phase = True
                try:
                    self._run_uninstall_steps(target)
                except Exception as exc:
                    import traceback
                    traceback.print_exc()
                    self._removal_phase = False
                    self.root.after(0, self.ui.begin_recovery, str(exc))
                    self._set_progress(0, "Restoring the previous installation…")
                    # Failed removal must never schedule deletion of restored files.
                    self.deferred_in_place = []
                    self.removal_target = ""
                    try:
                        recovery.rollback()
                    except Exception as rollback_error:
                        raise RuntimeError(f"{exc}\n\n{rollback_error}") from exc
                    raise RuntimeError(f"{exc}\n\nThe installation files and Windows registrations were restored. You can retry.") from exc
                self._removal_phase = False
                self._set_progress(None, "Deleting application files…")
                recovery.cleanup_deadline = self._cleanup_deadline
                self._cleanup_recovery = recovery
                recovery.commit(defer_cleanup=True)
                self._finish_committed_cleanup(target, recovery)
                self.setup_notice = "\n".join(self.cleanup_warnings)
                try:
                    self._cleanup_install_dir(target)
                except OSError as exc:
                    self.setup_notice += f"\nEmpty-folder cleanup can be retried: {exc}"
            self._set_progress(None if self.setup_notice else 1,
                               "Application removed; cleanup needs attention." if self.setup_notice
                               else "Uninstallation complete!")
            elapsed = time.monotonic() - self._uninstall_started
            print(f"UNINSTALL ELAPSED: {elapsed:.2f}s; target {UNINSTALL_TARGET_SECONDS}s; "
                  f"limit {UNINSTALL_LIMIT_SECONDS}s; cleanup warnings: {len(self.cleanup_warnings)}", flush=True)
            self.root.after(0, self._show_success, target)
        except Exception as exc:
            self.root.after(0, self._show_error, str(exc))
        finally:
            self._recovery = None
            self._removal_phase = False

    def _run_uninstall_steps(self, target: str):
        cumulative = 0.0
        self.removal_target = target

        self._set_progress(0.0, "Stopping remaining agent workers…")

        # ── Step 0: remove shortcuts ─────────────────────────────
        step_idx = 0
        self._activate_step(step_idx)
        self._set_progress(0.0, "Removing shortcuts…")
        self._run_ps1("RemoveShortcut.ps1", target)
        cumulative += self.STEPS[step_idx][1]
        self._set_progress(cumulative)
        self._mark_step(step_idx)

        # ── Step 1: unregister .flw file association ─────────────
        step_idx = 1
        self._activate_step(step_idx)
        self._set_progress(cumulative, "Unregistering .flw and .fpmt file associations…")
        self._run_ps1("unregister_flw.ps1", target)
        self._run_ps1("unregister_fpmt.ps1", target)
        cumulative += self.STEPS[step_idx][1]
        self._set_progress(cumulative)
        self._mark_step(step_idx)

        # ── Step 2: remove application files (preserve agents/) ──
        step_idx = 2
        self._activate_step(step_idx)
        weight = self.STEPS[step_idx][1]
        self._remove_files(target, cumulative, weight, keep_support=True)
        cumulative += weight
        self._set_progress(cumulative)
        self._mark_step(step_idx)

        # ── Step 3: clean up ─────────────────────────────────────
        step_idx = 3
        self._activate_step(step_idx)
        self._set_progress(cumulative, "Cleaning up…")
        self._unregister_programs_entry(target)
        self._remove_uninstall_support(target)
        self._cleanup_install_dir(target)
        cumulative += self.STEPS[step_idx][1]
        self._set_progress(cumulative)
        self._mark_step(step_idx)

        # ── Step 4: notify the shell without closing Explorer ────
        step_idx = 4
        self._activate_step(step_idx)
        self._set_progress(cumulative, "Refreshing Windows Desktop…")
        self._restart_explorer()
        cumulative += self.STEPS[step_idx][1]
        self._set_progress(1.0, "Windows integration removed. Finishing file cleanup…")
        self._mark_step(step_idx)

        # ── Done ─────────────────────────────────────────────────


    # ─── PS1 helper ──────────────────────────────────────────────────
    def _run_ps1(self, filename: str, target_dir: str):
        dst = os.path.join(target_dir, filename)
        if not os.path.isfile(dst):
            raise FileNotFoundError(
                f"The removal helper {filename} is missing from {target_dir}. "
                "Restore the complete installation with its Installer, then retry removal."
            )
        remaining = getattr(self, "_cleanup_deadline", time.monotonic() + UNINSTALL_LIMIT_SECONDS) - time.monotonic()
        if remaining <= 30:
            raise TimeoutError("The removal time limit was reached before file deletion. Restoring the installation.")
        return run_powershell(dst, timeout=min(30, remaining - 30))

    # ─── File removal (preserve agents/) ─────────────────────────────
    @staticmethod
    def _on_rmtree_error(func, path, exc_info):
        """Handle read-only / locked files during shutil.rmtree."""
        try:
            os.chmod(path, stat.S_IWUSR | stat.S_IREAD)
            func(path)
        except Exception:
            raise

    def _remove_files(self, target: str, cumulative: float, weight: float, *, keep_support=False):
        """Remove everything in *target* except what has to survive.

        ALWAYS kept: ``agents/``.  Kept WHENEVER IT HOLDS CONTENT: every name in
        ``PRESERVED_WHEN_NOT_EMPTY``.  Each directory kept for its content is
        recorded in ``self.preserved_dirs`` so the completion dialog can name it
        — the directory names only, never the files inside them.
        """
        if not os.path.isdir(target):
            return

        items = os.listdir(target)
        total = len(items)
        processed = 0
        failures = []
        self.preserved_dirs = []

        for item in items:
            item_path = os.path.join(target, item)

            if keep_support and item.lower() in UNINSTALL_SUPPORT_FILES:
                processed += 1
                continue

            # ── PRESERVE the agents directory (always) ───────────────
            if item.lower() == "agents":
                # Leave a companion-app marker + re-stamp the manifest so
                # Tlamatini-FlowPills can find these PRESERVED agents (PROP-003).
                try:
                    self._write_preserved_agents_marker(item_path, target)
                except Exception:
                    pass
                processed += 1
                frac = processed / total if total else 1.0
                self._set_progress(
                    cumulative + weight * frac,
                    "Skipping agents/ (preserved)…",
                )
                continue

            # ── PRESERVE a user-content directory that is NOT empty ──
            # The user's own material outranks a tidy uninstall: an empty one is
            # installer scaffolding and goes, one holding a single file stays
            # whole — exactly the way agents/ does.
            if (item.lower() in _PRESERVED_WHEN_NOT_EMPTY_LOWER
                    and os.path.isdir(item_path)
                    and directory_has_content(item_path)):
                self.preserved_dirs.append(item)
                processed += 1
                frac = processed / total if total else 1.0
                self._set_progress(
                    cumulative + weight * frac,
                    f"Skipping {item}/ (your content is preserved)…",
                )
                continue

            try:
                if item.lower() == "temp" and getattr(self, "_recovery", None):
                    # Cache cleanup follows commit. A locked temporary directory
                    # must never trigger restoration of the application payload.
                    pass
                elif getattr(self, "_recovery", None) and self._recovery.data.get("mode") == "removal":
                    self._recovery.stage_removal(item)
                elif os.path.islink(item_path):
                    os.unlink(item_path)
                elif getattr(os.path, "isjunction", lambda _: False)(item_path):
                    os.rmdir(item_path)
                elif os.path.isdir(item_path):
                    shutil.rmtree(item_path, onerror=self._on_rmtree_error)
                else:
                    try:
                        os.chmod(item_path, stat.S_IWUSR | stat.S_IREAD)
                    except Exception:
                        pass
                    os.remove(item_path)
            except OSError as exc:
                failures.append(f"{item}: {exc}")

            processed += 1
            frac = processed / total if total else 1.0
            self._set_progress(
                cumulative + weight * frac,
                f"Removing files… ({processed}/{total})",
            )

        if failures:
            raise RuntimeError(
                "Some application files could not be removed. Close programs "
                "using this installation and retry.\n\n" + "\n".join(failures[:12])
            )

    def _cleanup_temporary_files(self, target):
        """Report cache residue separately; never roll back a removed application."""
        folder = checked_path(target, "Temp")
        if not folder.exists():
            return
        try:
            with os.scandir(folder) as entries:
                paths = [entry.name for entry in entries if entry.name != ".setup-recovery"]
        except OSError as exc:
            self.cleanup_warnings.append(f"Temporary files remain at {folder}: {exc}")
            return
        for name in paths:
            try:
                path = checked_path(folder, name)
                remove_tree(path, lambda message: self._set_progress(None, message),
                            deadline=self._cleanup_deadline)
            except (OSError, RuntimeError, ValueError) as exc:
                warning = f"Temporary cleanup could not finish for {folder / name}: {exc}"
                print(f"[UNINSTALL] {warning}", flush=True)
                self.cleanup_warnings.append(warning)
        try:
            folder.rmdir()
        except FileNotFoundError:
            pass
        except OSError as exc:
            if not self.cleanup_warnings and not (folder / ".setup-recovery").exists():
                warning = f"Temporary cleanup could not finish for {folder}: {exc}"
                print(f"[UNINSTALL] {warning}", flush=True)
                self.cleanup_warnings.append(warning)

    def _remove_uninstall_support(self, target: str):
        """Remove retry support only after application and registry removal.

        Leave the installation marker until last.  Every helper goes through
        the ladder described above SUPPORT_DELETE_RETRY_SECONDS: delete with
        retries, then move aside into the pending folder.  The uninstaller's
        OWN running image (when it could not relocate to Temp) is never moved:
        a PyInstaller program re-reads its own file for every later import, so
        it is left for the cleanup that runs once this process has exited.
        Only a file that can be neither deleted nor moved stops the uninstall,
        and then the installed worker and marker still support an honest retry.
        """
        self.deferred_files = []
        self.deferred_in_place = []
        own = own_image_path()
        names = [name for name in os.listdir(target)
                 if name.lower() in UNINSTALL_SUPPORT_FILES]
        last = {"uninstaller.exe": 1, "tlamatini.ps1": 2, "createshortcut.json": 3}
        names.sort(key=lambda name: (last.get(name.lower(), 0), name))
        for name in names:
            path = os.path.join(target, name)
            if not os.path.isfile(path):
                continue
            if own and os.path.normcase(os.path.abspath(path)) == own:
                self.deferred_in_place.append(path)
                continue
            if getattr(self, "_recovery", None) and self._recovery.data.get("mode") == "removal":
                self._recovery.stage_removal(name)
                continue
            if self._delete_or_move_aside(target, path) == "deferred":
                self.deferred_files.append(name)

    def _delete_or_move_aside(self, target: str, path: str) -> str:
        """Delete *path*, or move it into the pending folder.

        Returns ``"removed"`` or ``"deferred"``; raises only when Windows
        refuses both the delete and the move.
        """
        deadline = time.monotonic() + SUPPORT_DELETE_RETRY_SECONDS
        delay = 0.1
        while True:
            try:
                os.chmod(path, stat.S_IWUSR | stat.S_IREAD)
            except OSError:
                pass
            try:
                os.remove(path)
                return "removed"
            except FileNotFoundError:
                return "removed"
            except OSError as exc:
                held = exc
            if time.monotonic() >= deadline:
                break
            time.sleep(delay)
            delay = min(delay * 2, 1.0)
        name = os.path.basename(path)
        try:
            os.replace(path, os.path.join(self._pending_folder(target), name))
        except OSError as exc:
            raise RuntimeError(
                f"Could not remove {name}: another program keeps it open (an "
                "antivirus scan or an Explorer window showing this folder are "
                f"the usual causes). Close it and press Uninstall again.\n\n{held}"
            ) from exc
        print(f"{name} was still held by Windows ({held}); moved aside for "
              "deletion after the uninstaller closes.")
        return "deferred"

    def _pending_folder(self, target: str) -> str:
        """The uniquely named folder that receives files Windows still holds."""
        current = getattr(self, "pending_dir", "")
        if not current or not os.path.isdir(current):
            self.pending_dir = tempfile.mkdtemp(prefix=PENDING_PREFIX, dir=target)
        return self.pending_dir

    def _write_preserved_agents_marker(self, agents_dir: str, original_install: str):
        """Leave ``.tlamatini-preserved-agents.json`` in the preserved agents/
        directory (Tlamatini-FlowPills PROP-003) and re-stamp the agents manifest's
        kind to ``preserved``. Best-effort — never raises into the uninstall pipeline.

        The XAIHT discovery registry key is intentionally NOT removed here: its
        ``AgentsRoot`` still points at these preserved agents, so a companion app
        can keep finding them after uninstall (FlowPills AC-002)."""
        if not os.path.isdir(agents_dir):
            return
        import json
        from datetime import datetime, timezone

        manifest_path = os.path.join(agents_dir, "_tlamatini_agents_manifest.json")
        agent_count = None
        manifest_catalog = ""
        # Prefer the shipped manifest for count/catalog, and re-stamp its kind so
        # it truthfully reports ``preserved`` after the app binaries are gone.
        try:
            if os.path.isfile(manifest_path):
                with open(manifest_path, encoding="utf-8") as mf:
                    manifest = json.load(mf)
                agent_count = manifest.get("agent_count")
                manifest_catalog = str(manifest.get("agent_catalog_version", "") or "")
                if manifest.get("agents_root_kind") != "preserved":
                    manifest["agents_root_kind"] = "preserved"
                    try:
                        with open(manifest_path, "w", encoding="utf-8") as mf:
                            json.dump(manifest, mf, indent=2)
                    except Exception:
                        pass
        except Exception:
            pass
        if agent_count is None:
            agent_count = self._count_complete_agents(agents_dir)
        # Checksum the (re-stamped) manifest so a companion app can verify it
        # (requirement: "manifest path/checksum"). Computed AFTER the kind re-stamp
        # above, so the hash matches the FINAL on-disk manifest.
        manifest_sha256 = ""
        try:
            if os.path.isfile(manifest_path):
                import hashlib

                h = hashlib.sha256()
                with open(manifest_path, "rb") as mfb:
                    for chunk in iter(lambda: mfb.read(1 << 16), b""):
                        h.update(chunk)
                manifest_sha256 = h.hexdigest()
        except Exception:
            manifest_sha256 = ""
        marker = {
            "product": "Tlamatini",
            "preserved": True,
            "note": (
                "Tlamatini application binaries were removed by the uninstaller, "
                "but this agents/ directory was intentionally preserved."
            ),
            "original_install_path": os.path.abspath(original_install),
            "uninstalled_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "version": getattr(self, "version", "") or "",
            "agent_count": agent_count,
            "agent_catalog_version": manifest_catalog,
            "manifest_path": manifest_path if os.path.isfile(manifest_path) else "",
            "manifest_sha256": manifest_sha256,
        }
        try:
            marker_path = os.path.join(agents_dir, ".tlamatini-preserved-agents.json")
            with open(marker_path, "w", encoding="utf-8") as f:
                json.dump(marker, f, indent=2)
        except Exception:
            pass

    @staticmethod
    def _count_complete_agents(agents_dir: str) -> int:
        """Count complete direct-child agent templates (``<type>.py`` + ``config.yaml``),
        skipping ``pools`` / ``__pycache__``. Mirrors FlowPills REQ-VAL-003."""
        count = 0
        try:
            for name in os.listdir(agents_dir):
                if name in ("pools", "__pycache__"):
                    continue
                sub = os.path.join(agents_dir, name)
                if not os.path.isdir(sub):
                    continue
                has_script = os.path.isfile(os.path.join(sub, name + ".py"))
                has_config = os.path.isfile(os.path.join(sub, "config.yaml"))
                if has_script and has_config:
                    count += 1
        except Exception:
            return count
        return count

    @staticmethod
    def _unregister_programs_entry(target: str):
        """Remove the per-user "Installed apps" (Add/Remove Programs) entry that
        install.py wrote under HKCU. A missing key counts as success; denied
        removal must be reported as incomplete, rather than silently succeeding."""
        if sys.platform != "win32":
            return
        from setup_logging import registry_context
        registry_context("before Installed-apps removal")
        try:
            import winreg
            key_path = r"Software\Microsoft\Windows\CurrentVersion\Uninstall\Tlamatini"
            try:
                key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path)
            except FileNotFoundError:
                print("Installed-apps entry is already absent (HKCU).")
                return
            with key:
                try:
                    owner = winreg.QueryValueEx(key, "InstallLocation")[0]
                except FileNotFoundError as exc:
                    raise RuntimeError("The Installed-apps entry has no installation owner. Repair it with the Installer before retrying.") from exc
            if not isinstance(owner, str) or not os.path.isabs(owner):
                raise RuntimeError("The Installed-apps entry has an invalid installation owner. Repair it with the Installer before retrying.")
            if os.path.normcase(os.path.abspath(owner)) != os.path.normcase(os.path.abspath(target)):
                print("Keeping Installed-apps entry owned by another installation.")
                return
            winreg.DeleteKey(winreg.HKEY_CURRENT_USER, key_path)
            try:
                remaining = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path)
            except FileNotFoundError:
                print("Removed and verified Installed-apps entry (HKCU).")
            else:
                remaining.Close()
                raise RuntimeError("Windows still reports the Installed-apps entry after its removal. Retry after closing other setup windows.")
        except Exception as e:
            raise RuntimeError(f"Could not remove the Installed-apps entry: {e}") from e

    @staticmethod
    def _cleanup_install_dir(target: str):
        """Remove the install directory itself if it is now empty."""
        if not os.path.isdir(target):
            return

        remaining = os.listdir(target)
        if not remaining:
            try:
                os.rmdir(target)
            except FileNotFoundError:
                pass
        # If only agents/ (or other items) remain, leave the directory

    # ─── Refresh shell associations without closing user windows ─────
    @staticmethod
    def _restart_explorer():
        """Notify the shell; never terminate Explorer or erase its global cache."""
        if sys.platform != "win32":
            return
        try:
            ctypes.windll.shell32.SHChangeNotify(0x08000000, 0, None, None)
        except OSError as exc:
            print(f"WARNING: Shell refresh failed: {exc}")


    # ─── Completion dialogs ──────────────────────────────────────────
    def _preserved_content_note(self) -> str:
        """The legend naming the directories kept because they held content.

        Empty string when there were none — the completion dialog must never
        print a static list of every candidate directory, only the ones actually
        found with something inside.  Directory NAMES only: what the user keeps
        in them is hers, and the uninstaller does not enumerate it.
        """
        names = list(dict.fromkeys(self.preserved_dirs))
        if not names:
            return ""
        head = (
            "\n\nContent was detected in the directory below, so it was "
            "left untouched:"
            if len(names) == 1 else
            "\n\nContent was detected in the directories below, so they were "
            "left untouched:"
        )
        return head + "\n" + "\n".join(f"    •  {name}" for name in names)

    def _show_success(self, target: str):
        self._uninstalling = False
        agents_dir = os.path.join(target, "agents")
        agents_note = (f"\n\nThe agents/ directory was preserved at:\n{agents_dir}"
                       if os.path.isdir(agents_dir) else "")
        self.ui.finish(success=True, target=target,
                       cleanup_retry=(lambda: self._retry_cleanup(target))
                       if getattr(self, "setup_notice", "") else None, detail=(
            "Shortcuts and .flw / .fpmt file associations have been removed."
            + agents_note + self._preserved_content_note() + self._deferred_note()
            + ("\n\n" + self.setup_notice if getattr(self, "setup_notice", "") else "")
        ))

    def _retry_cleanup(self, target):
        """Retry this operation's residue only, never the uninstall transaction."""
        if self._uninstalling:
            return
        self._uninstalling = True
        self.ui.begin(target)
        self.ui.heading.configure(text="Finishing file cleanup.")
        for label in self.ui.check_labels:
            label.pack_forget()
        threading.Thread(target=self._run_cleanup_retry, args=(target,), daemon=True).start()

    def _run_cleanup_retry(self, target):
        self.cleanup_warnings = []
        self.setup_notice = ""
        self._cleanup_deadline = time.monotonic() + UNINSTALL_LIMIT_SECONDS
        try:
            with setup_lock():
                # A new install must never inherit deletion from an older run.
                if os.path.exists(os.path.join(target, "Tlamatini.exe")):
                    raise RuntimeError("An application is present again. Cleanup stopped to protect the new installation.")
                recovery = self._cleanup_recovery
                if recovery.journal.exists():
                    current = Recovery(target, lambda message: self._set_progress(None, message))
                    current.load()
                    if (current.data != recovery.data or current.data.get("state") != "committed"
                            or current.data.get("outcome") != "removed"):
                        raise RuntimeError("Setup recovery changed since this removal. Cleanup stopped; files were kept.")
                    recovery = current
                elif recovery.folder.exists():
                    raise RuntimeError(f"Recovery journal is unavailable. Files were kept at {recovery.folder}.")
                elif recovery.data is None and not removal_cleanup_pending(target):
                    raise RuntimeError("The completed-removal receipt is unavailable. Files were kept.")
                self._finish_committed_cleanup(target, recovery)
                self._cleanup_install_dir(target)
        except Exception as exc:
            self.cleanup_warnings.append(str(exc))
        self.setup_notice = "\n".join(self.cleanup_warnings)
        self.root.after(0, self._show_success, target)

    def _finish_committed_cleanup(self, target, recovery):
        """Retain a small identity-bound receipt until ALL temporary data is gone.

        This survives closing the wizard after a Temp lock even when the large
        quarantine and its journal have already been removed. It never re-runs
        Windows integration removal or touches preserved content directories.
        """
        info = os.stat(target, follow_symlinks=False)
        receipt = checked_path(target, CLEANUP_RECEIPT)
        atomic_json(receipt, {"schema": 1, "state": "removed", "target": os.path.abspath(target),
                              "identity": [info.st_dev, info.st_ino]})
        if recovery.folder.exists():
            recovery.cleanup_deadline = self._cleanup_deadline
            try:
                recovery.discard()
            except OSError as exc:
                self.cleanup_warnings.append(f"Application cleanup remains at {recovery.folder}: {exc}")
        self._cleanup_temporary_files(target)
        if not self.cleanup_warnings:
            receipt.unlink()

    def _deferred_note(self) -> str:
        """Say plainly which files are deleted only after this window closes.

        Empty when everything was deleted on the spot.  Never claims the files
        are already gone: the cleanup that removes them runs after exit.
        """
        names = list(dict.fromkeys(
            list(getattr(self, "deferred_files", []))
            + [os.path.basename(p) for p in getattr(self, "deferred_in_place", [])]
        ))
        if not names:
            return ""
        return (
            "\n\nWindows was still holding " + ", ".join(names) + " (usually an "
            "antivirus scan or Explorer reading its icon), so it was set aside. "
            "It is deleted automatically a few seconds after you close this "
            "window, together with the installation folder if nothing else "
            "is left in it."
        )

    def _show_error(self, detail: str):
        self._uninstalling = False
        self.ui.finish(success=False, detail=detail)



def relocate_installed_uninstaller() -> bool:
    """Run the frozen GUI from Temp so its installed EXE can be removed.

    The original bootloader exits before the user confirms removal. A fresh
    PyInstaller environment prevents the child borrowing its parent's extraction
    directory, which is deleted when that parent exits. No removal is automatic:
    the ordinary running-process gate and confirmation still apply.
    """
    if not getattr(sys, "frozen", False) or sys.platform != "win32":
        return False
    source = os.path.abspath(sys.executable)
    install_dir = os.path.dirname(source)
    if not os.path.isfile(os.path.join(install_dir, "Tlamatini.exe")):
        return False
    # Fail-open: when the copy or the launch fails, the uninstaller runs in
    # place instead of crashing; its own EXE is then left to the cleanup.
    staging = ""
    try:
        staging = tempfile.mkdtemp(prefix=STAGING_PREFIX)
        worker = os.path.join(staging, "Uninstaller.exe")
        shutil.copy2(source, worker)
        subprocess.Popen(
            [worker, "--install-dir", install_dir], cwd=staging,
            env={**os.environ, "PYINSTALLER_RESET_ENVIRONMENT": "1"},
        )
    except Exception as exc:
        print(f"WARNING: could not relocate the uninstaller to Temp ({exc}); "
              "running in place.")
        if staging:
            shutil.rmtree(staging, ignore_errors=True)
        return False
    return True


def relocated_staging_dir() -> str:
    """The Temp folder THIS process runs from when it is the relocated copy.

    Empty for the installed copy, for a source run, and whenever the answer is
    uncertain: the cleanup deletes this folder recursively, so a guess is never
    good enough.
    """
    if not getattr(sys, "frozen", False):
        return ""
    try:
        folder = os.path.dirname(os.path.realpath(sys.executable))
        temp = os.path.realpath(tempfile.gettempdir())
    except Exception:
        return ""
    if not os.path.basename(folder).startswith(STAGING_PREFIX):
        return ""
    if os.path.normcase(os.path.dirname(folder)) != os.path.normcase(temp):
        return ""
    return folder


def sweep_stale_staging(keep: str = "") -> None:
    """Delete Temp copies that earlier runs left behind.  Never raises.

    Only real folders named with STAGING_PREFIX and older than
    STALE_STAGING_SECONDS; a link or junction is never followed, and *keep*
    (this process's own folder) is never touched.
    """
    try:
        now = time.time()
        for entry in os.scandir(tempfile.gettempdir()):
            if not entry.name.startswith(STAGING_PREFIX):
                continue
            if entry.is_symlink() or not entry.is_dir(follow_symlinks=False):
                continue
            if getattr(os.path, "isjunction", lambda _p: False)(entry.path):
                continue
            if keep and os.path.normcase(entry.path) == os.path.normcase(keep):
                continue
            try:
                if now - entry.stat(follow_symlinks=False).st_mtime < STALE_STAGING_SECONDS:
                    continue
            except OSError:
                continue
            shutil.rmtree(entry.path, ignore_errors=True)
    except Exception:
        pass


def build_cleanup_command(trees=(), files=(), empty_dirs=(),
                          attempts: int = CLEANUP_ATTEMPTS) -> str:
    """The hidden ``cmd.exe`` line that deletes what this process could not.

    It refuses anything it cannot prove is ours: a folder deleted recursively
    must carry STAGING_PREFIX or PENDING_PREFIX, a single file must be an
    ``Uninstaller.exe``, a folder in *empty_dirs* is only removed when empty,
    and every path must be absolute and free of characters cmd.exe interprets.
    Every ~2 s it retries until the trees and files are gone, then exits.
    Returns "" when there is nothing safe to do.
    """
    def safe(path):
        return (bool(path) and os.path.isabs(path)
                and not any(ch in path for ch in '"%\r\n'))

    trees = [p for p in trees if safe(p) and os.path.basename(
        os.path.normpath(p)).startswith((STAGING_PREFIX, PENDING_PREFIX))]
    files = [p for p in files
             if safe(p) and os.path.basename(p).lower() == "uninstaller.exe"]
    empty_dirs = [p for p in empty_dirs if safe(p)]
    if not (trees or files or empty_dirs):
        return ""
    steps = [f'rd /s /q "{p}"' for p in trees]
    steps += [f'del /f /q "{p}"' for p in files]
    steps += [f'rd "{p}"' for p in empty_dirs]
    body = " & ".join(f"{step} 2>nul" for step in steps)
    done = "".join(f'if not exist "{p}" ' for p in trees + files) + "exit"
    comspec = os.environ.get("COMSPEC") or "cmd.exe"
    return (f'"{comspec}" /d /q /s /c "for /l %i in (1,1,{int(attempts)}) do '
            f'@(ping -n 3 127.0.0.1 >nul & {body} & {done})"')


def schedule_cleanup(command: str) -> bool:
    """Start the hidden cleanup, which outlives this process.  Never raises.

    No window (CREATE_NO_WINDOW keeps even ping's console hidden), its own
    process group, and a working directory outside every folder it deletes.
    It first asks to break away from a job object so the program that launched
    the uninstaller cannot take the cleanup down with it.
    """
    if not command or sys.platform != "win32":
        return False
    base = 0x08000000 | 0x00000200   # CREATE_NO_WINDOW | CREATE_NEW_PROCESS_GROUP
    for flags in (base | 0x01000000, base):   # | CREATE_BREAKAWAY_FROM_JOB
        try:
            subprocess.Popen(
                command, creationflags=flags, close_fds=True,
                cwd=os.environ.get("SystemRoot") or None,
                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return True
        except OSError:
            continue
    return False


def cleanup_after_exit(app) -> bool:
    """Hand everything this process could not delete to the hidden cleanup:
    its own Temp copy, the pending folder, its own EXE when it ran in place,
    and the installation folder once it is empty.  Never raises."""
    try:
        trees = []
        staging = relocated_staging_dir()
        if staging:
            trees.append(staging)
        pending = getattr(app, "pending_dir", "") or ""
        if pending and os.path.isdir(pending):
            trees.append(pending)
        files = [p for p in getattr(app, "deferred_in_place", []) or []
                 if os.path.isfile(p)]
        target = getattr(app, "removal_target", "") or ""
        empty = [target] if target and os.path.isdir(target) else []
        return schedule_cleanup(build_cleanup_command(trees, files, empty))
    except Exception:
        return False


# ─── Entry point ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    from setup_logging import configure
    configure("uninstallation")
    if relocate_installed_uninstaller():
        sys.exit(0)
    sweep_stale_staging(keep=relocated_staging_dir())
    app = None
    try:
        root = tk.Tk()
        root.withdraw()

        app = FancyUninstaller(root)

        root.update_idletasks()

        try:
            root.deiconify()
        except tk.TclError:
            pass

        root.mainloop()
    finally:
        # Last one out turns off the lights: after success, an error or Exit,
        # the Temp copy and anything set aside are removed once this ends.
        cleanup_after_exit(app)
