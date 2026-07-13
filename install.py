# ═══════════════════════════════════════════════════════════════════
#   ✦  T L A M A T I N I  ✦   —   "one who knows"
#
#   Created by  Angela López Mendoza   ·   @angelahack1
#   Developer · Architect · Creator of Tlamatini
#
#   Every line of this file was written by Angela López Mendoza.
# ═══════════════════════════════════════════════════════════════════
#   Tlamatini Author Banner — do not remove (releases scrub the name automatically)
import os
import sys
import json
import ctypes
from ctypes import wintypes
import subprocess
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import zipfile


# ─── Version resolution ───────────────────────────────────────────────────────
# Read the version from the running .exe's Win32 ProductVersion (frozen mode)
# so the GUI always matches the value PyInstaller's --version-file baked in
# — i.e. what Right-click → Properties → Details → ProductVersion shows.
# In source mode, derive from git tags (same precedence as
# Tlamatini/agent/version.py).  Empty string is a valid return value; the UI
# degrades gracefully when no version is available.

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

        # Most-likely StringFileInfo language/codepage IDs, in order of
        # priority.  build.py's render_pyinstaller_version_file() writes
        # ``040904B0`` (en-US, Unicode).  The other entries are safety nets.
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
    """Resolve the running installer's version (frozen→EXE, source→git)."""
    if getattr(sys, "frozen", False):
        version = _read_exe_product_version(sys.executable)
        if version:
            return version
    derived = _derive_version_from_git()
    if derived:
        return derived
    return ""


# ─── DLL-locking prevention (PyInstaller --onedir) ────────────────────────────
# When the installer runs as a frozen exe, vcruntime140.dll and
# vcruntime140_1.dll live inside _internal/.  Any child process that
# *inherits* DLL handles — or loads them from the DLL search path —
# will keep those files locked even after the installer exits.
# The three mitigations below prevent that.

def _reset_dll_search_path():
    """Remove the PyInstaller _internal/ dir from the Windows DLL search order.

    Calling SetDllDirectoryW(NULL) tells the loader to stop searching the
    app directory for DLLs, falling back to the standard search sequence
    (System32, Windows, PATH).  This prevents child processes from picking
    up vcruntime140*.dll from _internal/ via DLL search-order inheritance.
    """
    if sys.platform == "win32":
        try:
            ctypes.windll.kernel32.SetDllDirectoryW(None)
        except Exception:
            pass  # non-fatal; best effort


def _free_vc_runtime_handles():
    """Explicitly unload bundled VC runtime DLLs so our reference count drops.

    This is a belt-and-suspenders complement to the search-path fix above.
    If any module in-process has bumped the DLL refcount (e.g. Tkinter or
    subprocess internals), releasing it here helps Windows truly unlock the
    file at installer-exit time.
    """
    if sys.platform != "win32":
        return
    k32 = ctypes.windll.kernel32
    GetModuleHandleW = k32.GetModuleHandleW
    GetModuleHandleW.restype = ctypes.c_void_p
    FreeLibrary = k32.FreeLibrary
    for dll_name in ("vcruntime140.dll", "vcruntime140_1.dll"):
        try:
            handle = GetModuleHandleW(dll_name)
            if handle:
                FreeLibrary(handle)
        except Exception:
            pass  # non-fatal


# ─── Color Palette ────────────────────────────────────────────────────────────
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
PROGRESS_FG   = "#00d4ff"
BORDER_COLOR  = "#2a2a4e"

FONT_FAMILY   = "Segoe UI"


class FancyInstaller:
    """Modern dark-themed installer for Tlamatini."""

    # ── weighted installation steps ──────────────────────────────────
    STEPS = [
        ("Preparing installation directory…",  0.05),
        ("Extracting files…",                  0.60),
        ("Securing agent environments…",       0.05),
        ("Writing configuration…",             0.05),
        ("Copying uninstaller…",               0.05),
        ("Creating shortcuts…",                0.075),
        ("Registering .flw file association…", 0.075),
        ("Refreshing Windows Desktop…",        0.05),
    ]

    def __init__(self, root: tk.Tk):
        self.root = root
        self.version = resolve_version()
        title = f"Tlamatini Installer v{self.version}" if self.version else "Tlamatini Installer"
        self.root.title(title)
        self.root.configure(bg=BG_DARK)
        self.root.resizable(False, False)

        # Center window 680×520 on screen
        w, h = 680, 540
        sx = (self.root.winfo_screenwidth()  - w) // 2
        sy = (self.root.winfo_screenheight() - h) // 2
        self.root.geometry(f"{w}x{h}+{sx}+{sy}")

        self.zip_path = self._find_zip()
        if not self.zip_path:
            messagebox.showerror("Error", "pkg.zip not found alongside the installer.")
            self.root.destroy()
            return

        self.install_path = tk.StringVar()
        self._progress_value = 0.0
        self._installing = False

        self._build_ui()

    # ─── Resource helper ──────────────────────────────────────────────
    @staticmethod
    def _find_zip() -> str | None:
        """Find pkg.zip sitting exactly next to the Installer.exe"""
        if getattr(sys, 'frozen', False):
            base = os.path.dirname(sys.executable)
        else:
            base = os.path.abspath(os.path.dirname(__file__))
            
        p = os.path.join(base, "pkg.zip")
        return p if os.path.isfile(p) else None

    # ─── UI Construction ──────────────────────────────────────────────
    def _build_ui(self):
        # ── Header ───────────────────────────────────────────────────
        hdr = tk.Frame(self.root, bg=BG_CARD, height=90)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)

        # Accent line at top
        tk.Frame(hdr, bg=ACCENT, height=3).pack(fill="x")

        # The header is laid out as: [gear + title-block | spring | version-badge]
        # — fill="x" so the spring expands and pushes the badge to the right edge.
        hdr_inner = tk.Frame(hdr, bg=BG_CARD)
        hdr_inner.pack(fill="both", expand=True)

        tk.Label(
            hdr_inner, text="⚙", font=(FONT_FAMILY, 28),
            bg=BG_CARD, fg=ACCENT,
        ).pack(side="left", padx=(20, 10), pady=(8, 0))

        title_block = tk.Frame(hdr_inner, bg=BG_CARD)
        title_block.pack(side="left", pady=(14, 0))
        tk.Label(
            title_block, text="Tlamatini", font=(FONT_FAMILY, 20, "bold"),
            bg=BG_CARD, fg=FG_PRIMARY,
        ).pack(anchor="w")
        tk.Label(
            title_block, text="Installation Wizard", font=(FONT_FAMILY, 10),
            bg=BG_CARD, fg=FG_SECONDARY,
        ).pack(anchor="w")

        # ── Version badge (pill-shaped, right-anchored) ──────────────
        # Only rendered when a version actually resolved.  The badge is a
        # framed pill whose border colour matches the top accent line so the
        # whole header reads as a coherent unit.
        self._build_version_badge(hdr_inner)

    def _build_version_badge(self, parent: tk.Frame):
        """Render the version pill in the header, or nothing if unresolved."""
        if not self.version:
            return

        # Outer 1-px frame acts as the pill border (cyan).
        badge_outer = tk.Frame(
            parent, bg=ACCENT,
            highlightthickness=0, bd=0,
        )
        badge_outer.pack(side="right", padx=(0, 22), pady=(20, 0))

        # Inner frame holds the labels and provides the dark fill colour.
        badge_inner = tk.Frame(badge_outer, bg=BG_INPUT)
        badge_inner.pack(padx=1, pady=1)  # 1-px reveal = the border

        # "VERSION" caption (small, dim, uppercase) above the number gives the
        # pill a typographic hierarchy that reads cleanly at a glance.
        tk.Label(
            badge_inner, text="VERSION",
            font=(FONT_FAMILY, 7, "bold"),
            bg=BG_INPUT, fg=FG_SECONDARY,
        ).pack(padx=14, pady=(5, 0))

        tk.Label(
            badge_inner, text=f"v{self.version}",
            font=(FONT_FAMILY, 12, "bold"),
            bg=BG_INPUT, fg=ACCENT,
        ).pack(padx=14, pady=(0, 5))

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
            inner, text="SELECT INSTALLATION DIRECTORY",
            font=(FONT_FAMILY, 9, "bold"), bg=BG_PANEL, fg=FG_SECONDARY,
        ).pack(anchor="w")

        tk.Label(
            inner,
            text='A "Tlamatini" folder will be created inside the selected directory.',
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

        # ── Target path display ──────────────────────────────────────
        self.target_label = tk.Label(
            inner, text="", font=(FONT_FAMILY, 8), bg=BG_PANEL, fg=ACCENT,
            anchor="w",
        )
        self.target_label.pack(fill="x", pady=(0, 10))
        self.install_path.trace_add("write", self._on_path_change)

        # ── Separator ────────────────────────────────────────────────
        tk.Frame(inner, bg=BORDER_COLOR, height=1).pack(fill="x", pady=6)

        # ── Progress section (hidden until install starts) ───────────
        self.progress_frame = tk.Frame(inner, bg=BG_PANEL)

        self.step_label = tk.Label(
            self.progress_frame, text="Waiting…",
            font=(FONT_FAMILY, 10), bg=BG_PANEL, fg=FG_PRIMARY, anchor="w",
        )
        self.step_label.pack(fill="x", pady=(6, 4))

        style = ttk.Style()
        style.theme_use("clam")
        style.configure(
            "Fancy.Horizontal.TProgressbar",
            troughcolor=PROGRESS_BG, background=PROGRESS_FG,
            darkcolor=ACCENT_GLOW, lightcolor=ACCENT,
            bordercolor=BG_PANEL, thickness=18,
        )

        self.progress_bar = ttk.Progressbar(
            self.progress_frame, style="Fancy.Horizontal.TProgressbar",
            orient="horizontal", length=400, mode="determinate",
            maximum=100,
        )
        self.progress_bar.pack(fill="x", pady=(0, 2))

        self.pct_label = tk.Label(
            self.progress_frame, text="0 %",
            font=(FONT_FAMILY, 9, "bold"), bg=BG_PANEL, fg=ACCENT, anchor="e",
        )
        self.pct_label.pack(fill="x")

        # ── Step checklist (populated during install) ────────────────
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

        self.install_btn = self._make_button(btn_row, "⬡  Install", self._start_install)
        self.install_btn.pack(side="right")

        # Pressing Enter/Return after typing the installation directory triggers
        # the SAME directory verification + installation as clicking Install.
        # Bound on the path entry (the common case — focus is in the field after
        # typing) AND on the window (so Enter works even if focus is elsewhere).
        self.path_entry.bind("<Return>", self._on_enter_key)
        self.root.bind("<Return>", self._on_enter_key)

    # ─── Button factory with hover effects ────────────────────────────
    def _make_button(self, parent, text, command, width=14, small=False, cancel=False):
        bg  = BTN_CANCEL_BG if cancel else BTN_BG
        hv  = BTN_CANCEL_HV if cancel else BTN_HOVER
        fg  = FG_SECONDARY  if cancel else FG_PRIMARY
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

    # ─── Path helpers ─────────────────────────────────────────────────
    def _on_path_change(self, *_):
        raw = self.install_path.get().strip()
        if raw:
            full = os.path.join(raw, "Tlamatini")
            self.target_label.config(text=f"➜  {full}")
        else:
            self.target_label.config(text="")

    def _browse(self):
        path = filedialog.askdirectory(title="Choose a parent directory for Tlamatini")
        if path:
            self.install_path.set(path)

    # ─── Validation ───────────────────────────────────────────────────
    def _validate_path(self) -> str | None:
        """Return the full install dir or None on failure."""
        raw = self.install_path.get().strip()
        if not raw:
            messagebox.showwarning("No path selected",
                                   "Please select an installation directory.")
            return None

        # Parent must exist
        if not os.path.isdir(raw):
            messagebox.showerror(
                "Invalid path",
                f"The directory does not exist:\n{raw}\n\n"
                "Please select an existing directory.",
            )
            return None

        target = os.path.join(raw, "Tlamatini")

        # Warn if target is not empty
        if os.path.isdir(target) and os.listdir(target):
            ans = messagebox.askyesno(
                "Directory not empty",
                f"The target directory already contains files:\n{target}\n\n"
                "Do you want to choose a different directory?\n\n"
                "Click Yes to choose another directory.\n"
                "Click No to continue and overwrite.",
            )
            if ans:          # user chose "Yes" → pick another
                self._browse()
                return None  # abort this attempt (user can click Install again)

        return target

    # ─── Enter/Return key ─────────────────────────────────────────────
    def _on_enter_key(self, _event=None):
        """Enter/Return = verify the directory + start the installation (same as
        clicking Install). Returns 'break' so the keypress doesn't also bubble to
        the window-level binding and fire twice; _start_install is re-entry-guarded
        anyway, so a double-fire would be harmless."""
        self._start_install()
        return "break"

    # ─── Installation thread ──────────────────────────────────────────
    def _start_install(self):
        if self._installing:
            return

        target = self._validate_path()
        if target is None:
            return

        self._installing = True
        self.install_btn.config(state="disabled")
        self.browse_btn.config(state="disabled")
        self.path_entry.config(state="disabled")
        self.progress_frame.pack(fill="x", before=self.progress_frame.master.winfo_children()[-1])

        t = threading.Thread(target=self._run_install, args=(target,), daemon=True)
        t.start()

    # ── Progress helpers (always marshal to main thread) ──────────────
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

    # ─── Main install pipeline (runs in background thread) ────────────
    def _run_install(self, target: str):
        try:
            cumulative = 0.0  # tracks completed-step weight

            # ── Step 0: create directory ─────────────────────────────
            step_idx = 0
            self._activate_step(step_idx)
            self._set_progress(0.0, "Creating installation directory…")
            os.makedirs(target, exist_ok=True)
            cumulative += self.STEPS[step_idx][1]
            self._set_progress(cumulative)
            self._mark_step(step_idx)

            # ── Step 1: extract pkg.zip ──────────────────────────────
            step_idx = 1
            self._activate_step(step_idx)
            weight = self.STEPS[step_idx][1]
            with zipfile.ZipFile(self.zip_path, "r") as zf:
                members = zf.namelist()
                total = len(members)
                for i, member in enumerate(members, 1):
                    zf.extract(member, target)
                    frac = i / total
                    self._set_progress(
                        cumulative + weight * frac,
                        f"Extracting files… ({i}/{total})",
                    )
            cumulative += weight
            self._set_progress(cumulative)
            self._mark_step(step_idx)

            # ── Step 2: Secure agent environments (PyInstaller fix) ──────
            step_idx = 2
            self._activate_step(step_idx)
            self._set_progress(cumulative, "Securing agent environments…")
            self._patch_agent_environments(os.path.join(target, "Tlamatini"))
            cumulative += self.STEPS[step_idx][1]
            self._set_progress(cumulative)
            self._mark_step(step_idx)

            # ── Step 3: write CreateShortcut.json ────────────────────
            step_idx = 3
            self._activate_step(step_idx)
            self._set_progress(cumulative, "Writing configuration…")
            config_data = {"InstallDir": target.replace("/", "\\")}
            config_path = os.path.join(target, "CreateShortcut.json")
            with open(config_path, "w", encoding="utf-8") as f:
                json.dump(config_data, f, indent=4)
            cumulative += self.STEPS[step_idx][1]
            self._set_progress(cumulative)
            self._mark_step(step_idx)

            # ── Step 4: copy Uninstaller.exe + register in "Installed apps" ──
            step_idx = 4
            self._activate_step(step_idx)
            self._set_progress(cumulative, "Copying uninstaller…")
            self._copy_uninstaller(target)
            # Now that Uninstaller.exe is in place, advertise Tlamatini in the
            # Windows Settings ▸ Apps ▸ Installed apps (and legacy Programs and
            # Features) list with a working Uninstall button. Per-user (HKCU),
            # non-fatal: a registry hiccup must not fail the whole install.
            self._set_progress(cumulative, "Registering with Windows…")
            self._register_programs_entry(target)
            # Companion-app discovery is registered INDEPENDENTLY of the ARP entry
            # above (REQ-S2-INSTALL-001/002/003): a valid installed agents catalog
            # must be discoverable by FlowPills even when Uninstaller.exe is missing
            # or the ARP registration raised. Own fail-open boundary inside.
            self._register_companion_discovery(target)
            cumulative += self.STEPS[step_idx][1]
            self._set_progress(cumulative)
            self._mark_step(step_idx)

            # ── Step 5: run CreateShortcut.ps1 ───────────────────────
            step_idx = 5
            self._activate_step(step_idx)
            self._set_progress(cumulative, "Creating shortcuts…")
            self._run_ps1("CreateShortcut.ps1", target)
            cumulative += self.STEPS[step_idx][1]
            self._set_progress(cumulative)
            self._mark_step(step_idx)

            # ── Step 6: run register_flw.ps1 ─────────────────────────
            step_idx = 6
            self._activate_step(step_idx)
            self._set_progress(cumulative, "Registering .flw file association…")
            self._run_ps1("register_flw.ps1", target)
            cumulative += self.STEPS[step_idx][1]
            self._set_progress(cumulative)
            self._mark_step(step_idx)

            # ── Step 7: Restart Explorer ──────────────────────────────
            step_idx = 7
            self._activate_step(step_idx)
            self._set_progress(cumulative, "Refreshing Windows Desktop…")
            self._restart_explorer()
            cumulative += self.STEPS[step_idx][1]
            self._set_progress(1.0, "Installation complete!")
            self._mark_step(step_idx)

            # ── Done ─────────────────────────────────────────────────
            self.root.after(0, self._show_success, target)

        except Exception as exc:
            self.root.after(0, self._show_error, str(exc))

    @staticmethod
    def _get_clean_env():
        """Retrieve a clean environment without PyInstaller's DLL paths to prevent locking."""
        clean_env = os.environ.copy()
        if getattr(sys, 'frozen', False):
            # Remove _MEIPASS and the exe directory from PATH so child
            # processes never discover vcruntime140*.dll inside _internal/.
            meipass = (sys._MEIPASS if hasattr(sys, '_MEIPASS') else "").lower()
            exe_dir = os.path.dirname(sys.executable).lower()
            internal_dir = os.path.join(exe_dir, "_internal").lower()
            blocked = {meipass, exe_dir, internal_dir}
            paths = clean_env.get("PATH", "").split(os.pathsep)
            paths = [
                p for p in paths
                if p.lower() not in blocked
                and not any(p.lower().startswith(b + os.sep) for b in blocked if b)
            ]
            clean_env["PATH"] = os.pathsep.join(paths)
        return clean_env

    # ─── PS1 helper ───────────────────────────────────────────────────
    def _run_ps1(self, filename: str, target_dir: str):
        """Run a PS1 script that was just extracted into target_dir."""
        dst = os.path.join(target_dir, filename)
        if not os.path.isfile(dst):
             raise FileNotFoundError(f"{filename} not found at {dst}")

        clean_env = self._get_clean_env()
        # close_fds=True  prevents the child from inheriting any open handles
        #                 (e.g. vcruntime140.dll loaded by the PyInstaller bootloader).
        # CREATE_NO_WINDOW avoids flashing a console window during install.
        result = subprocess.run(
            ["powershell", "-ExecutionPolicy", "Bypass", "-NoProfile", "-File", dst],
            cwd=target_dir,
            env=clean_env,
            capture_output=True, text=True, timeout=120,
            close_fds=True,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        if result.returncode != 0:
            detail = result.stderr.strip() or result.stdout.strip()
            raise RuntimeError(f"{filename} failed (exit {result.returncode}):\n{detail}")

    # ─── Uninstaller copy helper ─────────────────────────────────────
    @staticmethod
    def _copy_uninstaller(target_dir: str):
        """Copy Uninstaller.exe from next to the installer into the install dir."""
        import shutil
        if getattr(sys, 'frozen', False):
            base = os.path.dirname(sys.executable)
        else:
            base = os.path.abspath(os.path.dirname(__file__))

        src = os.path.join(base, "Uninstaller.exe")
        if os.path.isfile(src):
            dst = os.path.join(target_dir, "Uninstaller.exe")
            shutil.copy2(src, dst)
        else:
            # Non-fatal: older release packages may not include it
            print(f"WARNING: Uninstaller.exe not found at {src} — skipping copy.")

    # ─── "Installed apps" (Add/Remove Programs) registration ─────────
    def _register_programs_entry(self, target_dir: str):
        """Write the per-user ARP entry so Tlamatini appears in Windows'
        Settings ▸ Apps ▸ Installed apps (and legacy Programs and Features),
        with an Uninstall button that launches the bundled Uninstaller.exe.

        Self-contained (the installer is a standalone frozen exe and cannot
        import agent.*). HKCU only — matches the per-user, non-elevated install.
        Best-effort: never raises into the install pipeline.
        """
        if sys.platform != "win32":
            return
        try:
            import winreg

            install_dir = os.path.abspath(target_dir)
            uninstaller = os.path.join(install_dir, "Uninstaller.exe")
            if not os.path.isfile(uninstaller):
                print("WARNING: Uninstaller.exe missing — skipping Installed-apps registration.")
                return

            icon = os.path.join(install_dir, "Tlamatini.ico")
            exe = os.path.join(install_dir, "Tlamatini.exe")
            display_icon = icon if os.path.isfile(icon) else (
                f"{exe},0" if os.path.isfile(exe) else uninstaller
            )
            quoted_uninstaller = f'"{uninstaller}"'

            # EstimatedSize (KB) for the "Size" column — best-effort, capped.
            size_kb = 0
            try:
                seen = 0
                total = 0
                for root, _dirs, files in os.walk(install_dir):
                    for name in files:
                        seen += 1
                        if seen > 60000:
                            raise StopIteration
                        try:
                            total += os.path.getsize(os.path.join(root, name))
                        except OSError:
                            pass
                size_kb = total // 1024
            except StopIteration:
                size_kb = total // 1024
            except Exception:
                size_kb = 0

            key_path = r"Software\Microsoft\Windows\CurrentVersion\Uninstall\Tlamatini"
            with winreg.CreateKey(winreg.HKEY_CURRENT_USER, key_path) as key:
                winreg.SetValueEx(key, "DisplayName", 0, winreg.REG_SZ, "Tlamatini")
                if self.version:
                    winreg.SetValueEx(key, "DisplayVersion", 0, winreg.REG_SZ, self.version)
                winreg.SetValueEx(key, "Publisher", 0, winreg.REG_SZ, "XAIHT")
                winreg.SetValueEx(key, "DisplayIcon", 0, winreg.REG_SZ, display_icon)
                winreg.SetValueEx(key, "InstallLocation", 0, winreg.REG_SZ, install_dir)
                winreg.SetValueEx(key, "UninstallString", 0, winreg.REG_SZ, quoted_uninstaller)
                winreg.SetValueEx(key, "QuietUninstallString", 0, winreg.REG_SZ, quoted_uninstaller)
                winreg.SetValueEx(key, "URLInfoAbout", 0, winreg.REG_SZ,
                                  "https://github.com/XAIHT/Tlamatini")
                winreg.SetValueEx(key, "NoModify", 0, winreg.REG_DWORD, 1)
                winreg.SetValueEx(key, "NoRepair", 0, winreg.REG_DWORD, 1)
                if size_kb > 0:
                    winreg.SetValueEx(key, "EstimatedSize", 0, winreg.REG_DWORD, size_kb)
            print(f"Registered Tlamatini in Installed apps (HKCU): {key_path}")
        except Exception as e:
            print(f"WARNING: Could not register Installed-apps entry: {e}")

    def _register_companion_discovery(self, target_dir: str):
        """Write the HKCU companion-app discovery key (Software\\XAIHT\\Tlamatini) so
        XAIHT companion apps (Tlamatini-FlowPills) can find the agents root without
        importing Python or scanning drives.

        INDEPENDENT of the Installed-apps/ARP registration and of Uninstaller.exe
        (REQ-S2-INSTALL-001/002/003): an install with a valid agents catalog must be
        discoverable by FlowPills even when ARP registration is skipped or fails.
        Self-contained (the installer is a standalone frozen exe and cannot import
        agent.*). HKCU only, fail-open — never raises into the install pipeline.
        """
        if sys.platform != "win32":
            return
        try:
            import json
            import winreg

            install_dir = os.path.abspath(target_dir)
            agents_root = os.path.join(install_dir, "agents")
            manifest_path = os.path.join(agents_root, "_tlamatini_agents_manifest.json")
            catalog_version = ""
            try:
                if os.path.isfile(manifest_path):
                    # utf-8-sig tolerates a BOM if one was written.
                    with open(manifest_path, encoding="utf-8-sig") as mf:
                        catalog_version = str(json.load(mf).get("agent_catalog_version", "") or "")
            except Exception:
                catalog_version = ""

            disc_key = r"Software\XAIHT\Tlamatini"
            # REQ-S2-INSTALL-004 / REQ-S2-REG-001: write ALL SIX values, empty string
            # when unknown, so no stale value from a previous install survives.
            with winreg.CreateKey(winreg.HKEY_CURRENT_USER, disc_key) as dkey:
                winreg.SetValueEx(dkey, "InstallLocation", 0, winreg.REG_SZ, install_dir)
                winreg.SetValueEx(dkey, "AgentsRoot", 0, winreg.REG_SZ, agents_root)
                winreg.SetValueEx(dkey, "SourceAgentsRoot", 0, winreg.REG_SZ, "")
                winreg.SetValueEx(
                    dkey, "AgentManifestPath", 0, winreg.REG_SZ,
                    manifest_path if os.path.isfile(manifest_path) else "",
                )
                winreg.SetValueEx(dkey, "Version", 0, winreg.REG_SZ, self.version or "")
                winreg.SetValueEx(dkey, "AgentCatalogVersion", 0, winreg.REG_SZ, catalog_version)
            print(f"Registered companion-app discovery (HKCU): {disc_key}")
        except Exception as de:
            print(f"WARNING: Could not register companion-app discovery: {de}")

    # ─── Desktop refresh helper ──────────────────────────────────────
    @staticmethod
    def _restart_explorer():
        """Refresh the Windows desktop to pick up new shortcuts and file associations.

        DESIGN — non-destructive refresh via Win32 API
        ───────────────────────────────────────────────
        Previous versions killed explorer.exe and tried to restart it via a
        detached cmd.exe script.  This was fragile: the ``timeout`` command
        does not work reliably in non-interactive / no-window processes, so
        explorer would die and never come back — leaving the user with a
        blank desktop.

        The correct approach is to **never kill explorer**.  Instead we:
          1. Clear stale icon-cache files (best-effort).
          2. Call ``SHChangeNotify(SHCNE_ASSOCCHANGED)`` — this is the
             official Windows API to tell the shell that file-type
             associations or icon overlays have changed.
          3. Broadcast ``WM_SETTINGCHANGE`` so every top-level window
             (including Explorer) re-reads environment variables and
             registry settings.

        Together these two calls make Explorer refresh its icon overlay,
        file-association, and shortcut caches — without any restart.
        """

        # ── 1. Best-effort icon-cache cleanup ────────────────────────
        try:
            local_appdata = os.environ.get("LOCALAPPDATA", "")
            if local_appdata:
                icon_db = os.path.join(local_appdata, "IconCache.db")
                if os.path.exists(icon_db):
                    os.remove(icon_db)
                explorer_cache = os.path.join(
                    local_appdata, "Microsoft", "Windows", "Explorer"
                )
                if os.path.exists(explorer_cache):
                    for f in os.listdir(explorer_cache):
                        if f.startswith("iconcache"):
                            try:
                                os.remove(os.path.join(explorer_cache, f))
                            except Exception:
                                pass
        except Exception:
            pass

        # ── 2. SHChangeNotify — tell the shell about association changes ─
        try:
            SHCNE_ASSOCCHANGED = 0x08000000
            SHCNF_IDLIST       = 0x0000
            ctypes.windll.shell32.SHChangeNotify(
                SHCNE_ASSOCCHANGED, SHCNF_IDLIST, None, None,
            )
        except Exception:
            pass

        # ── 3. Broadcast WM_SETTINGCHANGE to all top-level windows ───
        try:
            HWND_BROADCAST   = 0xFFFF
            WM_SETTINGCHANGE = 0x001A
            SMTO_ABORTIFHUNG = 0x0002
            result = ctypes.c_long(0)
            ctypes.windll.user32.SendMessageTimeoutW(
                HWND_BROADCAST,
                WM_SETTINGCHANGE,
                0,
                "Environment",
                SMTO_ABORTIFHUNG,
                5000,           # 5-second timeout per window
                ctypes.byref(result),
            )
        except Exception:
            pass

    # ─── Environment Patching helper ──────────────────────────────────
    def _patch_agent_environments(self, tlamatini_dir: str):
        """
        Scans all Python files injected by checking for agent definitions or 
        views.py to inject PyInstaller DLL resolution workarounds dynamically.
        """
        anchor = "    if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):"
        patch = (
            "    # Reset PyInstaller's DLL search path alteration on Windows\n"
            "    # If we don't do this, child Python processes will WinError 1114 when loading C extensions (like torch)\n"
            "    if sys.platform.startswith('win'):\n"
            "        try:\n"
            "            import ctypes\n"
            "            if hasattr(ctypes.windll.kernel32, 'SetDllDirectoryW'):\n"
            "                ctypes.windll.kernel32.SetDllDirectoryW(None)\n"
            "        except Exception:\n"
            "            pass\n\n"
            "    # Remove PyInstaller's _MEIPASS from PATH to prevent DLL conflicts in child processes\n"
            "    if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):"
        )
        
        try:
            import glob
            # Include main views.py and agents logic
            paths_to_check = glob.glob(os.path.join(tlamatini_dir, "agent", "agents", "*", "*.py"))
            paths_to_check.append(os.path.join(tlamatini_dir, "agent", "views.py"))

            for filepath in paths_to_check:
                if not os.path.exists(filepath):
                    continue
                with open(filepath, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                # Check if anchor is present and it hasn't already been patched
                if anchor in content and "SetDllDirectoryW" not in content:
                    content = content.replace(anchor, patch)
                    with open(filepath, 'w', encoding='utf-8') as f:
                        f.write(content)
        except Exception as e:
            print(f"Non-fatal error patching agent environments: {e}")

    # ─── Completion dialogs ───────────────────────────────────────────
    def _show_success(self, target: str):
        self.step_label.config(text="✓  Installation complete!", fg=SUCCESS)
        messagebox.showinfo(
            "Installation Complete",
            f"Tlamatini was installed successfully!\n\n"
            f"Location: {target}\n\n"
            "Shortcuts have been created on your Desktop\n"
            "and .flw files are now associated with Tlamatini.",
        )
        self.root.destroy()

    def _show_error(self, detail: str):
        self._installing = False
        self.install_btn.config(state="normal")
        self.browse_btn.config(state="normal")
        self.path_entry.config(state="normal")
        self.step_label.config(text="✗  Installation failed", fg=ERROR)
        messagebox.showerror(
            "Installation Error",
            f"An error occurred during installation:\n\n{detail}",
        )


# ─── Entry point ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    # ── Layer 1: reset DLL search path BEFORE anything else ──────────
    # This prevents child processes from discovering vcruntime140*.dll
    # inside PyInstaller's _internal/ directory.
    _reset_dll_search_path()

    # Tell the PyInstaller bootloader splash that Python is now running.
    # This is a no-op when the script is run directly (not from a bundle).
    try:
        import pyi_splash
        pyi_splash.update_text("Loading installer…")
    except Exception:
        pass

    root = tk.Tk()
    root.withdraw()             # hide the window while the UI is being built

    app = FancyInstaller(root)

    root.update_idletasks()     # flush geometry/draw events so the window is
                                # fully rendered before the splash disappears

    # Dismiss the splash and reveal the installer window in one beat so there
    # is no visible gap between the two.
    try:
        import pyi_splash
        pyi_splash.close()
    except Exception:
        pass

    try:
        root.deiconify()        # show the fully-built installer window
    except tk.TclError:
        pass                    # window was destroyed during init (e.g. pkg.zip missing)

    root.mainloop()

    # ── Layer 4: release VC runtime DLL handles before exit ──────────
    # This drops our in-process reference count so Windows can truly
    # unlock the files once the process terminates.
    _free_vc_runtime_handles()
