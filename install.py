import os
import sys
import json
import subprocess
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import zipfile


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
        self.root.title("Tlamatini Installer")
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

        hdr_inner = tk.Frame(hdr, bg=BG_CARD)
        hdr_inner.pack(expand=True)

        tk.Label(
            hdr_inner, text="⚙", font=(FONT_FAMILY, 28),
            bg=BG_CARD, fg=ACCENT,
        ).pack(side="left", padx=(20, 10))

        title_block = tk.Frame(hdr_inner, bg=BG_CARD)
        title_block.pack(side="left")
        tk.Label(
            title_block, text="Tlamatini", font=(FONT_FAMILY, 20, "bold"),
            bg=BG_CARD, fg=FG_PRIMARY,
        ).pack(anchor="w")
        tk.Label(
            title_block, text="Installation Wizard", font=(FONT_FAMILY, 10),
            bg=BG_CARD, fg=FG_SECONDARY,
        ).pack(anchor="w")

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

            # ── Step 4: copy Uninstaller.exe into install dir ─────────
            step_idx = 4
            self._activate_step(step_idx)
            self._set_progress(cumulative, "Copying uninstaller…")
            self._copy_uninstaller(target)
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

    # ─── PS1 helper ───────────────────────────────────────────────────
    def _run_ps1(self, filename: str, target_dir: str):
        """Run a PS1 script that was just extracted into target_dir."""
        dst = os.path.join(target_dir, filename)
        if not os.path.isfile(dst):
             raise FileNotFoundError(f"{filename} not found at {dst}")

        result = subprocess.run(
            ["powershell", "-ExecutionPolicy", "Bypass", "-NoProfile", "-File", dst],
            cwd=target_dir,
            capture_output=True, text=True, timeout=120,
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
