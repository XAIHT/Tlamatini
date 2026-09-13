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
import tkinter as tk
from ctypes import wintypes
from tkinter import filedialog, messagebox, ttk


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
# keeps reading it after the uninstall).  These five hold the user's OWN
# material — the projects loaded as context, whatever Tlamatini generated, and
# the scratch directory — so they are preserved TOO, but only when they actually
# hold something.  An empty one is installer scaffolding: it goes.
PRESERVED_WHEN_NOT_EMPTY = (
    "application",
    "applications",
    "content_generated",
    "context_files",
    "Temp",
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
        ("Unregistering .flw file association…", 0.15),
        ("Removing application files…",          0.65),
        ("Cleaning up…",                         0.05),
        ("Refreshing Windows Desktop…",          0.05),
    ]

    def __init__(self, root: tk.Tk):
        self.root = root
        self.version = resolve_version()
        title = f"Tlamatini Uninstaller v{self.version}" if self.version else "Tlamatini Uninstaller"
        self.root.title(title)
        self.root.configure(bg=BG_DARK)
        self.root.resizable(False, False)

        # Center window 680×540 on screen
        w, h = 680, 540
        sx = (self.root.winfo_screenwidth()  - w) // 2
        sy = (self.root.winfo_screenheight() - h) // 2
        self.root.geometry(f"{w}x{h}+{sx}+{sy}")

        self.install_path = tk.StringVar(value=self._detect_install_path())
        self._progress_value = 0.0
        self._uninstalling = False
        # Directories left untouched because they held the user's own content.
        # Written by the worker thread, read by the completion dialog — the
        # hand-off happens through root.after(), after the thread is done.
        self.preserved_dirs: list[str] = []
        # How many times the user pressed Retry on the still-running gate.
        self._gate_attempts = 0

        self._build_ui()

    # ─── Auto-detect install path ────────────────────────────────────
    @staticmethod
    def _detect_install_path() -> str:
        """Try to auto-detect the Tlamatini installation directory."""

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

        # 2. Try reading from registry (.flw shell command contains the path)
        try:
            import winreg
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Classes\Tlamatini.FlowFile\shell\open\command",
            )
            cmd, _ = winreg.QueryValueEx(key, "")
            winreg.CloseKey(key)
            # cmd looks like:
            #   cmd.exe /k powershell.exe ... -File "D:\Tlamatini\Tlamatini.ps1" ...
            match = re.search(r'-File\s+"([^"]+)"', cmd)
            if match:
                ps1_path = match.group(1)
                candidate = os.path.dirname(ps1_path)
                if os.path.isdir(candidate):
                    return candidate
        except Exception:
            pass

        return ""

    # ─── UI Construction ─────────────────────────────────────────────
    def _build_ui(self):
        # ── Header ───────────────────────────────────────────────────
        hdr = tk.Frame(self.root, bg=BG_CARD, height=90)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)

        # Red accent line at top (danger theme)
        tk.Frame(hdr, bg=ERROR, height=3).pack(fill="x")

        # Layout: [gear + title-block | spring | version-badge].  fill="both"
        # + expand=True makes the spring push the badge to the right edge.
        hdr_inner = tk.Frame(hdr, bg=BG_CARD)
        hdr_inner.pack(fill="both", expand=True)

        tk.Label(
            hdr_inner, text="⚙", font=(FONT_FAMILY, 28),
            bg=BG_CARD, fg=ERROR,
        ).pack(side="left", padx=(20, 10), pady=(8, 0))

        title_block = tk.Frame(hdr_inner, bg=BG_CARD)
        title_block.pack(side="left", pady=(14, 0))
        tk.Label(
            title_block, text="Tlamatini", font=(FONT_FAMILY, 20, "bold"),
            bg=BG_CARD, fg=FG_PRIMARY,
        ).pack(anchor="w")
        tk.Label(
            title_block, text="Uninstallation Wizard", font=(FONT_FAMILY, 10),
            bg=BG_CARD, fg=FG_SECONDARY,
        ).pack(anchor="w")

        # ── Version badge (pill, danger theme) ───────────────────────
        # Border colour matches the top accent line (red) so the whole
        # header still reads as a coherent danger-themed unit.
        self._build_version_badge(hdr_inner)

        # ── Body card ────────────────────────────────────────────────
        body = tk.Frame(self.root, bg=BG_DARK)
        body.pack(fill="both", expand=True, padx=30, pady=20)

        card = tk.Frame(body, bg=BG_PANEL, highlightbackground=BORDER_COLOR,
                        highlightthickness=1)
        card.pack(fill="both", expand=True)

        inner = tk.Frame(card, bg=BG_PANEL)
        inner.pack(fill="both", expand=True, padx=24, pady=20)

        # ── Path selection ───────────────────────────────────────────
        tk.Label(
            inner, text="INSTALLATION DIRECTORY",
            font=(FONT_FAMILY, 9, "bold"), bg=BG_PANEL, fg=FG_SECONDARY,
        ).pack(anchor="w")

        tk.Label(
            inner,
            text="Select the Tlamatini installation directory to uninstall.",
            font=(FONT_FAMILY, 8), bg=BG_PANEL, fg=FG_DIM,
        ).pack(anchor="w", pady=(0, 8))

        path_row = tk.Frame(inner, bg=BG_PANEL)
        path_row.pack(fill="x", pady=(0, 6))

        self.path_entry = tk.Entry(
            path_row, textvariable=self.install_path,
            font=(FONT_FAMILY, 11), bg=BG_INPUT, fg=FG_PRIMARY,
            insertbackground=ACCENT, relief="flat", bd=0,
            highlightthickness=1, highlightbackground=BORDER_COLOR,
            highlightcolor=ACCENT,
        )
        self.path_entry.pack(side="left", fill="x", expand=True, ipady=6, padx=(0, 8))

        self.browse_btn = self._make_button(path_row, "Browse", self._browse,
                                            width=10, small=True)
        self.browse_btn.pack(side="right")

        # ── Warning label ────────────────────────────────────────────
        tk.Label(
            inner,
            text="⚠  agents/ is always preserved.  application/, applications/,\n"
                 "     content_generated/, context_files/ and Temp/ are preserved\n"
                 "     too when they hold content.  Everything else is removed.",
            font=(FONT_FAMILY, 9), bg=BG_PANEL, fg=WARNING, anchor="w",
            justify="left",
        ).pack(fill="x", pady=(4, 10))

        # ── Separator ────────────────────────────────────────────────
        tk.Frame(inner, bg=BORDER_COLOR, height=1).pack(fill="x", pady=6)

        # ── Progress section (hidden until uninstall starts) ─────────
        self.progress_frame = tk.Frame(inner, bg=BG_PANEL)

        self.step_label = tk.Label(
            self.progress_frame, text="Waiting…",
            font=(FONT_FAMILY, 10), bg=BG_PANEL, fg=FG_PRIMARY, anchor="w",
        )
        self.step_label.pack(fill="x", pady=(6, 4))

        style = ttk.Style()
        style.theme_use("clam")
        style.configure(
            "Danger.Horizontal.TProgressbar",
            troughcolor=PROGRESS_BG, background=PROGRESS_FG,
            darkcolor="#cc0000", lightcolor=ERROR,
            bordercolor=BG_PANEL, thickness=18,
        )

        self.progress_bar = ttk.Progressbar(
            self.progress_frame, style="Danger.Horizontal.TProgressbar",
            orient="horizontal", length=400, mode="determinate",
            maximum=100,
        )
        self.progress_bar.pack(fill="x", pady=(0, 2))

        self.pct_label = tk.Label(
            self.progress_frame, text="0 %",
            font=(FONT_FAMILY, 9, "bold"), bg=BG_PANEL, fg=ERROR, anchor="e",
        )
        self.pct_label.pack(fill="x")

        # ── Step checklist ───────────────────────────────────────────
        self.checklist_frame = tk.Frame(self.progress_frame, bg=BG_PANEL)
        self.checklist_frame.pack(fill="x", pady=(6, 0))
        self.check_labels: list[tk.Label] = []

        for desc, _ in self.STEPS:
            lbl = tk.Label(
                self.checklist_frame,
                text=f"   ○  {desc}",
                font=(FONT_FAMILY, 9), bg=BG_PANEL, fg=FG_DIM, anchor="w",
            )
            lbl.pack(fill="x")
            self.check_labels.append(lbl)

        # ── Buttons ──────────────────────────────────────────────────
        btn_row = tk.Frame(inner, bg=BG_PANEL)
        btn_row.pack(side="bottom", fill="x", pady=(10, 0))

        self.cancel_btn = self._make_button(btn_row, "Cancel", self.root.quit,
                                            cancel=True)
        self.cancel_btn.pack(side="right", padx=(8, 0))

        self.uninstall_btn = self._make_button(btn_row, "⬡  Uninstall",
                                               self._start_uninstall,
                                               danger=True)
        self.uninstall_btn.pack(side="right")

        # Pressing Enter/Return after typing the installation directory triggers
        # the SAME directory verification + uninstallation as clicking Uninstall.
        # Bound on the path entry (focus is in the field after typing) AND on the
        # window (so Enter works even if focus is elsewhere).
        self.path_entry.bind("<Return>", self._on_enter_key)
        self.root.bind("<Return>", self._on_enter_key)

    def _build_version_badge(self, parent: tk.Frame):
        """Render the version pill in the header, or nothing if unresolved.

        ⚠ THIS METHOD BUILDS THE BADGE AND NOTHING ELSE.  It used to carry the
        whole body of the window — the path field, the warning, the progress
        section and both buttons — BELOW its own ``if not self.version: return``,
        so an uninstaller whose version could not be resolved would have painted
        a header over an empty card: no path box, no Uninstall, no Cancel, no way
        to do anything at all.  It never fired only because the version always
        resolves (frozen reads the EXE's VERSIONINFO, source reads the git tag) —
        a latent trap, not a safe design.  The window's contents belong to
        ``_build_ui``; keep them there.
        """
        if not self.version:
            return

        # Outer 1-px frame = pill border (red, matches the danger accent).
        badge_outer = tk.Frame(
            parent, bg=ERROR,
            highlightthickness=0, bd=0,
        )
        badge_outer.pack(side="right", padx=(0, 22), pady=(20, 0))

        # Inner dark fill with 1-px reveal forms the border.
        badge_inner = tk.Frame(badge_outer, bg=BG_INPUT)
        badge_inner.pack(padx=1, pady=1)

        tk.Label(
            badge_inner, text="VERSION",
            font=(FONT_FAMILY, 7, "bold"),
            bg=BG_INPUT, fg=FG_SECONDARY,
        ).pack(padx=14, pady=(5, 0))

        tk.Label(
            badge_inner, text=f"v{self.version}",
            font=(FONT_FAMILY, 12, "bold"),
            bg=BG_INPUT, fg=ERROR,
        ).pack(padx=14, pady=(0, 5))

    # ─── Button factory with hover effects ───────────────────────────
    def _make_button(self, parent, text, command, width=14, small=False,
                     cancel=False, danger=False):
        if cancel:
            bg, hv, fg = BTN_CANCEL_BG, BTN_CANCEL_HV, FG_SECONDARY
        elif danger:
            bg, hv, fg = DANGER_BG, DANGER_HV, FG_PRIMARY
        else:
            bg, hv, fg = BTN_BG, BTN_HOVER, FG_PRIMARY
        fnt = (FONT_FAMILY, 9) if small else (FONT_FAMILY, 10, "bold")

        btn = tk.Button(
            parent, text=text, command=command,
            font=fnt, bg=bg, fg=fg,
            activebackground=hv, activeforeground=FG_PRIMARY,
            relief="flat", bd=0, cursor="hand2",
            padx=14, pady=6, width=width,
        )
        btn.bind("<Enter>", lambda e, b=btn, c=hv: b.config(bg=c))
        btn.bind("<Leave>", lambda e, b=btn, c=bg: b.config(bg=c))
        return btn

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

        # Check if it looks like a Tlamatini installation
        markers = ["Tlamatini.exe", "Tlamatini.ps1", "CreateShortcut.json"]
        found = any(os.path.exists(os.path.join(raw, m)) for m in markers)
        if not found:
            ans = messagebox.askyesno(
                "Not a Tlamatini installation?",
                f"The selected directory does not appear to contain a "
                f"Tlamatini installation:\n{raw}\n\n"
                "None of the expected files (Tlamatini.exe, Tlamatini.ps1) "
                "were found.\n\n"
                "Do you want to continue anyway?",
            )
            if not ans:
                return None

        return raw

    def _confirm_removal(self, raw: str) -> bool:
        """Last chance to back out.

        Asked AFTER the still-running gate, so the user is never made to confirm
        an uninstallation the uninstaller is about to refuse anyway.
        """
        return bool(messagebox.askyesno(
            "Confirm Uninstallation",
            f"This will remove Tlamatini from:\n{raw}\n\n"
            "The agents/ directory is preserved — and so are application/, "
            "applications/, content_generated/, context_files/ and Temp/ "
            "whenever they hold content.\n"
            "All other files will be permanently deleted.\n\n"
            "Do you want to continue?",
        ))

    # ─── Uninstallation thread ───────────────────────────────────────
    def _on_enter_key(self, _event=None):
        """Enter/Return = verify the directory + start the uninstallation (same as
        clicking Uninstall). Returns 'break' so the keypress doesn't bubble to the
        window-level binding and fire twice; _start_uninstall is re-entry-guarded."""
        self._start_uninstall()
        return "break"

    # ─── Still-running gate (modal — Retry / Exit, nothing else) ─────
    def _ensure_tlamatini_not_running(self, target: str) -> bool:
        """Refuse to uninstall while Tlamatini is still running.

        Returns True when nothing is running out of *target*, so the
        uninstallation may proceed.  Returns False otherwise — the user chose
        Exit (or closed the dialog, which counts as Exit) and the whole
        uninstaller has already been shut down.
        """
        running = find_running_tlamatini(target)
        if not running:
            return True
        if self._show_running_gate(target, running):
            return True
        self._shutdown()
        return False

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

        dlg = tk.Toplevel(self.root)
        dlg.title("Tlamatini is still running")
        dlg.configure(bg=BG_DARK)
        dlg.resizable(False, False)
        dlg.transient(self.root)

        w, h = 620, 420
        sx = (dlg.winfo_screenwidth() - w) // 2
        sy = (dlg.winfo_screenheight() - h) // 2
        dlg.geometry(f"{w}x{h}+{sx}+{sy}")

        hdr = tk.Frame(dlg, bg=BG_CARD)
        hdr.pack(fill="x")
        tk.Frame(hdr, bg=ERROR, height=3).pack(fill="x")
        tk.Label(
            hdr, text="⛔  Close Tlamatini before uninstalling",
            font=(FONT_FAMILY, 13, "bold"), bg=BG_CARD, fg=ERROR, anchor="w",
        ).pack(fill="x", padx=20, pady=12)

        body = tk.Frame(dlg, bg=BG_PANEL, highlightbackground=BORDER_COLOR,
                        highlightthickness=1)
        body.pack(fill="both", expand=True, padx=16, pady=14)

        headline = tk.StringVar()
        detail = tk.StringVar()

        self.gate_headline_var = headline
        self.gate_detail_var = detail

        tk.Label(
            body, textvariable=headline, font=(FONT_FAMILY, 10, "bold"),
            bg=BG_PANEL, fg=FG_PRIMARY, anchor="w", justify="left",
            wraplength=w - 80,
        ).pack(fill="x", padx=18, pady=(16, 6))

        tk.Label(
            body,
            text=("Please close it first — preferably with Ctrl+C in the "
                  "Tlamatini console window, which is what lets it shut its "
                  "agents down cleanly.\n\nThen press Retry."),
            font=(FONT_FAMILY, 9), bg=BG_PANEL, fg=FG_SECONDARY,
            anchor="w", justify="left", wraplength=w - 80,
        ).pack(fill="x", padx=18, pady=(0, 10))

        tk.Label(
            body, text="DETECTED", font=(FONT_FAMILY, 8, "bold"),
            bg=BG_PANEL, fg=FG_DIM, anchor="w",
        ).pack(fill="x", padx=18)

        detail_lbl = tk.Label(
            body, textvariable=detail, font=("Consolas", 9),
            bg=BG_INPUT, fg=WARNING, anchor="nw", justify="left",
            wraplength=w - 90,
        )
        detail_lbl.pack(fill="both", expand=True, padx=18, pady=(4, 12))

        btn_row = tk.Frame(body, bg=BG_PANEL)
        btn_row.pack(fill="x", padx=18, pady=(0, 14))

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
            still = find_running_tlamatini(target)
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
        if self._uninstalling:
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
        self.uninstall_btn.config(state="disabled")
        self.browse_btn.config(state="disabled")
        self.path_entry.config(state="disabled")
        self.progress_frame.pack(
            fill="x",
            before=self.progress_frame.master.winfo_children()[-1],
        )

        t = threading.Thread(target=self._run_uninstall, args=(target,),
                             daemon=True)
        t.start()

    # ── Progress helpers (always marshal to main thread) ─────────────
    def _set_progress(self, value: float, status: str | None = None):
        self._progress_value = value
        self.root.after(0, self._update_progress_ui, value, status)

    def _update_progress_ui(self, value: float, status: str | None):
        pct = min(int(value * 100), 100)
        self.progress_bar["value"] = pct
        self.pct_label.config(text=f"{pct} %")
        if status:
            self.step_label.config(text=status)

    def _mark_step(self, idx: int, success: bool = True):
        color = SUCCESS if success else ERROR
        icon  = "✓" if success else "✗"
        desc  = self.STEPS[idx][0]
        self.root.after(0, lambda: self.check_labels[idx].config(
            text=f"   {icon}  {desc}", fg=color,
        ))

    def _activate_step(self, idx: int):
        desc = self.STEPS[idx][0]
        self.root.after(0, lambda: self.check_labels[idx].config(
            text=f"   ▸  {desc}", fg=ACCENT,
        ))

    # ─── Main uninstall pipeline (runs in background thread) ─────────
    def _run_uninstall(self, target: str):
        try:
            cumulative = 0.0

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
            self._set_progress(cumulative, "Unregistering .flw file association…")
            self._run_ps1("unregister_flw.ps1", target)
            cumulative += self.STEPS[step_idx][1]
            self._set_progress(cumulative)
            self._mark_step(step_idx)

            # ── Step 2: remove application files (preserve agents/) ──
            step_idx = 2
            self._activate_step(step_idx)
            weight = self.STEPS[step_idx][1]
            self._remove_files(target, cumulative, weight)
            cumulative += weight
            self._set_progress(cumulative)
            self._mark_step(step_idx)

            # ── Step 3: clean up ─────────────────────────────────────
            step_idx = 3
            self._activate_step(step_idx)
            self._set_progress(cumulative, "Cleaning up…")
            self._unregister_programs_entry()
            self._cleanup_install_dir(target)
            cumulative += self.STEPS[step_idx][1]
            self._set_progress(cumulative)
            self._mark_step(step_idx)

            # ── Step 4: restart explorer ─────────────────────────────
            step_idx = 4
            self._activate_step(step_idx)
            self._set_progress(cumulative, "Refreshing Windows Desktop…")
            self._restart_explorer()
            cumulative += self.STEPS[step_idx][1]
            self._set_progress(1.0, "Uninstallation complete!")
            self._mark_step(step_idx)

            # ── Done ─────────────────────────────────────────────────
            self.root.after(0, self._show_success, target)

        except Exception as exc:
            self.root.after(0, self._show_error, str(exc))

    # ─── PS1 helper ──────────────────────────────────────────────────
    def _run_ps1(self, filename: str, target_dir: str):
        """Run a PS1 script located in target_dir."""
        dst = os.path.join(target_dir, filename)
        if not os.path.isfile(dst):
            # Non-fatal: script may not exist in older installations
            print(f"WARNING: {filename} not found at {dst} — skipping.")
            return

        result = subprocess.run(
            ["powershell", "-ExecutionPolicy", "Bypass", "-NoProfile",
             "-File", dst],
            cwd=target_dir,
            capture_output=True, text=True, timeout=120,
        )
        if result.returncode != 0:
            detail = result.stderr.strip() or result.stdout.strip()
            raise RuntimeError(
                f"{filename} failed (exit {result.returncode}):\n{detail}",
            )

    # ─── File removal (preserve agents/) ─────────────────────────────
    @staticmethod
    def _on_rmtree_error(func, path, exc_info):
        """Handle read-only / locked files during shutil.rmtree."""
        try:
            os.chmod(path, stat.S_IWUSR | stat.S_IREAD)
            func(path)
        except Exception:
            pass

    def _remove_files(self, target: str, cumulative: float, weight: float):
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

        for item in items:
            item_path = os.path.join(target, item)

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
                if os.path.isdir(item_path):
                    shutil.rmtree(item_path, onerror=self._on_rmtree_error)
                else:
                    try:
                        os.chmod(item_path, stat.S_IWUSR | stat.S_IREAD)
                    except Exception:
                        pass
                    os.remove(item_path)
            except Exception:
                pass  # best-effort removal

            processed += 1
            frac = processed / total if total else 1.0
            self._set_progress(
                cumulative + weight * frac,
                f"Removing files… ({processed}/{total})",
            )

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
    def _unregister_programs_entry():
        """Remove the per-user "Installed apps" (Add/Remove Programs) entry that
        install.py wrote under HKCU. Best-effort: never raises into the
        uninstall pipeline, and a missing key counts as success."""
        if sys.platform != "win32":
            return
        try:
            import winreg
            key_path = r"Software\Microsoft\Windows\CurrentVersion\Uninstall\Tlamatini"
            try:
                winreg.DeleteKey(winreg.HKEY_CURRENT_USER, key_path)
                print("Removed Installed-apps entry (HKCU).")
            except FileNotFoundError:
                pass  # already absent
        except Exception as e:
            print(f"WARNING: Could not remove Installed-apps entry: {e}")

    @staticmethod
    def _cleanup_install_dir(target: str):
        """Remove the install directory itself if it is now empty."""
        if not os.path.isdir(target):
            return

        remaining = os.listdir(target)
        if not remaining:
            try:
                os.rmdir(target)
            except Exception:
                pass
        # If only agents/ (or other items) remain, leave the directory

    # ─── Explorer restart robust helper ──────────────────────────────
    @staticmethod
    def _restart_explorer():
        import time
        # Stop Explorer
        subprocess.run(["taskkill", "/f", "/im", "explorer.exe"], capture_output=True)
        time.sleep(0.5)

        # Clear icon cache (best-effort)
        try:
            local_appdata = os.environ.get("LOCALAPPDATA", "")
            if local_appdata:
                icon_db = os.path.join(local_appdata, "IconCache.db")
                if os.path.exists(icon_db):
                    os.remove(icon_db)
                explorer_cache = os.path.join(local_appdata, "Microsoft", "Windows", "Explorer")
                if os.path.exists(explorer_cache):
                    for f in os.listdir(explorer_cache):
                        if f.startswith("iconcache"):
                            try:
                                os.remove(os.path.join(explorer_cache, f))
                            except Exception:
                                pass
        except Exception:
            pass

        # Start Explorer and ensure it is running
        retries = 5
        while retries > 0:
            subprocess.Popen(["explorer.exe"])
            time.sleep(1.5)
            # Verify if it started
            res = subprocess.run(["tasklist", "/FI", "IMAGENAME eq explorer.exe"], capture_output=True, text=True)
            if "explorer.exe" in res.stdout:
                break
            retries -= 1

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
        self.step_label.config(text="✓  Uninstallation complete!", fg=SUCCESS)

        agents_dir = os.path.join(target, "agents")
        agents_note = ""
        if os.path.isdir(agents_dir):
            agents_note = (
                f"\n\nThe agents/ directory was preserved at:\n{agents_dir}"
            )

        messagebox.showinfo(
            "Uninstallation Complete",
            f"Tlamatini has been successfully uninstalled.\n\n"
            f"Location: {target}"
            f"{agents_note}"
            f"{self._preserved_content_note()}\n\n"
            "The .flw file association has been removed\n"
            "and shortcuts have been deleted.",
        )
        self.root.destroy()

    def _show_error(self, detail: str):
        self._uninstalling = False
        self.uninstall_btn.config(state="normal")
        self.browse_btn.config(state="normal")
        self.path_entry.config(state="normal")
        self.step_label.config(text="✗  Uninstallation failed", fg=ERROR)
        messagebox.showerror(
            "Uninstallation Error",
            f"An error occurred during uninstallation:\n\n{detail}",
        )


# ─── Entry point ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    root = tk.Tk()
    root.withdraw()

    app = FancyUninstaller(root)

    root.update_idletasks()

    try:
        root.deiconify()
    except tk.TclError:
        pass

    root.mainloop()
