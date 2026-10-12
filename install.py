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
from setup_wizard import WizardView
from setup_recovery import Recovery, setup_lock
from setup_windows import run_powershell
from uninstall_processes import owned_processes
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import zipfile

from build_runtime_assets import verify_package


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
        ("Registering .flw and .fpmt file associations…", 0.075),
        ("Refreshing Windows Desktop…",        0.05),
    ]

    def __init__(self, root: tk.Tk):
        self.root = root
        self.version = resolve_version()
        title = f"Tlamatini Installer v{self.version}" if self.version else "Tlamatini Installer"
        self.root.title(title)
        self.zip_path = self._find_zip()

        self.install_path = tk.StringVar()
        self._progress_value = 0.0
        self._installing = False

        self._build_ui()
        if not self.zip_path:
            self._show_error("pkg.zip was not found alongside the installer.\n\n"
                             "Keep the complete release folder together, then retry.")

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
        self.ui = WizardView(
            self.root, removal=False, version=self.version,
            path=self.install_path, steps=self.STEPS,
            start=self._start_install, browse=self._browse,
        )
        # Keep the worker and existing integrations on their public UI handles.
        self.path_entry = self.ui.path_entry
        self.browse_btn = self.ui.browse_btn
        self.install_btn = self.ui.primary_btn
        self.cancel_btn = self.ui.cancel_btn
        self.button_row = self.ui.button_row
        self.progress_frame = self.ui.progress_frame
        self.step_label = self.ui.step_label
        self.progress_bar = self.ui.progress_bar
        self.pct_label = self.ui.pct_label
        self.check_labels = self.ui.check_labels
        self.target_label = self.ui.target_label

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

        target = os.path.abspath(target)
        if (os.path.normcase(os.path.realpath(target)) != os.path.normcase(target)
                or os.path.exists(os.path.join(target, ".git"))
                or os.path.isfile(os.path.join(target, "Tlamatini", "manage.py"))
                or os.path.isfile(target)):
            messagebox.showerror("Invalid installation folder",
                                 "Choose a separate application folder. Setup cannot overwrite a source checkout, a file or a redirected directory.")
            return None

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
    def _on_enter_key(self, event=None):
        return self.ui._enter(event)

    # ─── Installation thread ──────────────────────────────────────────
    def _start_install(self):
        if self._installing or self.ui.state == "complete":
            return

        self.zip_path = self._find_zip()
        if not self.zip_path:
            self._show_error("pkg.zip was not found alongside the installer.\n\n"
                             "Keep the complete release folder together, then retry.")
            return

        target = self._validate_path()
        if target is None:
            return

        self._installing = True
        self.ui.begin(target)

        t = threading.Thread(target=self._run_install, args=(target,), daemon=True)
        t.start()

    # ── Progress helpers (always marshal to main thread) ──────────────
    def _set_progress(self, value: float, status: str | None = None):
        self._progress_value = value
        self.root.after(0, self._update_progress_ui, value, status)

    def _update_progress_ui(self, value: float, status: str | None):
        self.ui.update_progress(value, status)

    def _mark_step(self, idx: int, success: bool = True):
        self.root.after(0, self.ui.mark_step, idx, success)

    def _activate_step(self, idx: int):
        self.root.after(0, self.ui.activate_step, idx)

    # ─── Main install pipeline (runs in background thread) ────────────
    # ── User state that must survive a reinstall ──────────────────────────
    # The list lives in ONE place, `preserved_user_state.json`, which
    # apply_update.ps1 and uninstall.py answer to as well. Three private
    # copies is how they drifted: the updater preserved external_mcps.json
    # while the installer preserved nothing.
    _PRESERVE_FALLBACK = (
        "config.json", "external_mcps.json", "contacts.json", "DB",
        "application", "applications", "content_generated", "Temp",
        "context_files", "doc_generated", "documentation", "Templates",
        "Uninstaller.exe",
    )

    @staticmethod
    def _preserved_names() -> set:
        """Read the shared list; fall back to the built-in copy.

        FAIL-SAFE, not fail-open: if the file is missing or unreadable we
        preserve the built-in set anyway. Erring towards keeping the user's
        data is the only acceptable direction — the alternative is deleting
        their API keys because a JSON file did not parse.
        """
        here = os.path.dirname(os.path.abspath(__file__))
        for candidate in (os.path.join(here, "preserved_user_state.json"),
                          os.path.join(here, "_internal",
                                       "preserved_user_state.json")):
            try:
                with open(candidate, "r", encoding="utf-8-sig") as fh:
                    doc = json.load(fh)
                names = doc.get("preserve")
                if isinstance(names, list) and names:
                    return {str(n).strip().lower() for n in names if str(n).strip()}
            except Exception:
                continue
        return {n.lower() for n in FancyInstaller._PRESERVE_FALLBACK}

    @staticmethod
    def _is_preserved_member(member: str, target: str, preserved: set) -> bool:
        """True when this zip member belongs to EXISTING user state.

        Matching is on the TOP-LEVEL name, so `DB/db.sqlite3` is protected by
        the entry `DB`. Nothing is skipped unless it is already on disk — a
        fresh install must still receive its seed files.
        """
        normalized = member.replace("\\", "/").strip("/")
        if not normalized:
            return False
        # The live DB is nested in application code, not the top-level DB/
        # export/import directory. Never replace it (or its WAL companions)
        # with the release's seeded database during an in-place reinstall.
        if normalized.lower() in {"_internal/db.sqlite3", "_internal/db.sqlite3-wal",
                                  "_internal/db.sqlite3-shm", "_internal/db.sqlite3-journal"}:
            return os.path.isfile(os.path.join(target, "_internal", "db.sqlite3"))
        top = normalized.split("/")[0]
        if top.lower() not in preserved:
            return False
        return os.path.exists(os.path.join(target, top))

    def _run_install(self, target: str):
        recovery = None
        self.setup_warnings = []
        try:
            with setup_lock():
                self._set_progress(0, "Checking release integrity and recovery…")
                try:
                    document = verify_package(self.zip_path)
                except Exception as exc:
                    raise RuntimeError(
                        "The release package could not be verified. No installation files were changed.\n\n"
                        "Extract the complete release again, keeping pkg.zip beside Installer.exe, then retry. "
                        "If Windows denied access, close applications holding the package and check its permissions.\n\n"
                        f"Details: {exc}"
                    ) from exc
                if owned_processes(target):
                    raise RuntimeError("Close Tlamatini and its remaining agents before installing into this folder, then retry.")
                recovery = Recovery(target, lambda message: self._set_progress(0, message))
                recovery.recover_previous()
                self._existing_preserved = {name for name in self._preserved_names()
                                            if os.path.exists(os.path.join(target, name))}
                names = [name for name in document["files"] if not self._is_preserved_member(
                    name, target, self._existing_preserved)]
                names += ["runtime-assets.json", "CreateShortcut.json", "Uninstaller.exe", "Tlamatini.lnk", "CreateShortcut_Temp.vbs"]
                # The existing environment patcher can edit older retained code too.
                for parent, _dirs, files in os.walk(os.path.join(target, "Tlamatini")):
                    names += [os.path.relpath(os.path.join(parent, name), target).replace("\\", "/")
                              for name in files if name.endswith(".py")]
                required = sum(record["bytes"] for record in document["files"].values())
                recovery.prepare(names, required_space=required)
                try:
                    self._run_install_steps(target)
                except Exception as exc:
                    self._set_progress(0, "Restoring the previous installation…")
                    try:
                        recovery.rollback()
                    except Exception as rollback_error:
                        raise RuntimeError(f"{exc}\n\n{rollback_error}") from exc
                    raise RuntimeError(f"{exc}\n\nThe previous files and Windows registrations were restored. You can retry.") from exc
                self.setup_notice = "\n".join(filter(None, [recovery.commit(), *self.setup_warnings]))
            self.root.after(0, self._show_success, target)
        except Exception as exc:
            self.root.after(0, self._show_error, str(exc))

    def _run_install_steps(self, target: str):
        self._set_progress(0.0, "Verifying release integrity before installation…")
        existing_db = os.path.join(target, "_internal", "db.sqlite3")
        if os.path.isfile(existing_db):
            # Keep the DB/WAL in place; next startup applies new migrations.
            # Set before extraction so even an interrupted reinstall retries.
            state_dir = os.path.join(target, "DB")
            os.makedirs(state_dir, exist_ok=True)
            with open(os.path.join(state_dir, "post_update_migrate.flag"), "w", encoding="utf-8") as flag:
                flag.write("in-place reinstall: retained existing database and WAL\n")
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
        #
        # PRESERVING USER STATE (Angela, 2026-08-12). This used to extract
        # EVERY member unconditionally, so installing over an existing
        # Tlamatini overwrote `config.json` (every provider key and
        # setting), `external_mcps.json` (the whole External-MCP catalog
        # AND its active set), `contacts.json` and the DB. That is why
        # "every time I reinstall, all the external MCPs go fucked" — the
        # self-updater had a $Preserve list and the installer had none.
        #
        # Now the same list guards both. A preserved item is SKIPPED only
        # when it already exists, so a FRESH install still gets its seed
        # files; only an upgrade-in-place leaves the user's copy alone.
        preserved = self._existing_preserved
        # Capture existence ONCE. Otherwise extracting the first seed file
        # makes its new directory look pre-existing and skips sibling seeds.
        preserved = {name for name in preserved if os.path.exists(os.path.join(target, name))}
        kept: list[str] = []
        step_idx = 1
        self._activate_step(step_idx)
        weight = self.STEPS[step_idx][1]
        with zipfile.ZipFile(self.zip_path, "r") as zf:
            members = zf.namelist()
            total = len(members)
            for i, member in enumerate(members, 1):
                if self._is_preserved_member(member, target, preserved):
                    top = member.replace("\\", "/").split("/")[0]
                    if top not in kept:
                        kept.append(top)
                else:
                    zf.extract(member, target)
                frac = i / total
                self._set_progress(
                    cumulative + weight * frac,
                    f"Extracting files… ({i}/{total})",
                )
        if kept:
            print(f"[INSTALL] Preserved existing user state: {', '.join(sorted(kept))}")
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

        # ── Step 6: register both flow formats ─────────────────────────
        step_idx = 6
        self._activate_step(step_idx)
        self._set_progress(cumulative, "Registering .flw and .fpmt file associations…")
        self._run_ps1("register_flw.ps1", target)
        self._run_ps1("register_fpmt.ps1", target)
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
        dst = os.path.join(target_dir, filename)
        if not os.path.isfile(dst):
            raise FileNotFoundError(f"{filename} not found at {dst}")
        return run_powershell(dst, env=self._get_clean_env())

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
            raise FileNotFoundError(
                f"Uninstaller.exe is missing from the release folder: {src}. "
                "Restore the complete release folder and retry."
            )

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
                # There is no silent-uninstall mode; do not advertise one.
                try:
                    winreg.DeleteValue(key, "QuietUninstallString")
                except FileNotFoundError:
                    pass
                winreg.SetValueEx(key, "URLInfoAbout", 0, winreg.REG_SZ,
                                  "https://github.com/XAIHT/Tlamatini")
                winreg.SetValueEx(key, "NoModify", 0, winreg.REG_DWORD, 1)
                winreg.SetValueEx(key, "NoRepair", 0, winreg.REG_DWORD, 1)
                if size_kb > 0:
                    winreg.SetValueEx(key, "EstimatedSize", 0, winreg.REG_DWORD, size_kb)
            print(f"Registered Tlamatini in Installed apps (HKCU): {key_path}")
        except Exception as e:
            print(f"WARNING: Could not register Installed-apps entry: {e}")
            self.setup_warnings = [*getattr(self, "setup_warnings", []),
                                   f"Windows Installed apps registration needs attention: {e}"]

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
            self.setup_warnings = [*getattr(self, "setup_warnings", []),
                                   f"Companion app discovery needs attention: {de}"]

    # ─── Desktop refresh helper ──────────────────────────────────────
    @staticmethod
    def _restart_explorer():
        """Invalidate associations without deleting caches or waiting on every app."""
        try:
            ctypes.windll.shell32.SHChangeNotify(0x08000000, 0, None, None)
        except OSError as exc:
            print(f"WARNING: Desktop refresh failed: {exc}")

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
        self._installing = False
        self.ui.finish(success=True, target=target, detail=(
            "Tlamatini is installed.\n\nDesktop shortcuts are ready.\n"
            ".flw and .fpmt flow files are now associated with Tlamatini."
            + ("\n\n" + self.setup_notice if getattr(self, "setup_notice", "") else "")
        ))

    def _show_error(self, detail: str):
        self._installing = False
        self.ui.finish(success=False, detail=detail)


# ─── Entry point ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    from setup_logging import configure
    configure("installation")
    # ── Layer 1: reset DLL search path BEFORE anything else ──────────
    # This prevents child processes from discovering vcruntime140*.dll
    # inside PyInstaller's _internal/ directory.
    _reset_dll_search_path()

    # Tell the PyInstaller bootloader splash that Python is now running.
    # This is a no-op when the script is run directly (not from a bundle).
    try:
        if os.environ.get("_PYI_SPLASH_IPC"):
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
        if os.environ.get("_PYI_SPLASH_IPC"):
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
