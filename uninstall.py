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

import json
import os
import re
import shutil
import stat
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk


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
        self.root.title("Tlamatini Uninstaller")
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

        hdr_inner = tk.Frame(hdr, bg=BG_CARD)
        hdr_inner.pack(expand=True)

        tk.Label(
            hdr_inner, text="⚙", font=(FONT_FAMILY, 28),
            bg=BG_CARD, fg=ERROR,
        ).pack(side="left", padx=(20, 10))

        title_block = tk.Frame(hdr_inner, bg=BG_CARD)
        title_block.pack(side="left")
        tk.Label(
            title_block, text="Tlamatini", font=(FONT_FAMILY, 20, "bold"),
            bg=BG_CARD, fg=FG_PRIMARY,
        ).pack(anchor="w")
        tk.Label(
            title_block, text="Uninstallation Wizard", font=(FONT_FAMILY, 10),
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
            text="⚠  The agents/ directory will be preserved.\n"
                 "     All other application files will be removed.",
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
        """Return the validated install dir path or None on failure."""
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

        # Final confirmation
        ans = messagebox.askyesno(
            "Confirm Uninstallation",
            f"This will remove Tlamatini from:\n{raw}\n\n"
            "The agents/ directory will be preserved.\n"
            "All other files will be permanently deleted.\n\n"
            "Do you want to continue?",
        )
        if not ans:
            return None

        return raw

    # ─── Uninstallation thread ───────────────────────────────────────
    def _start_uninstall(self):
        if self._uninstalling:
            return

        target = self._validate_path()
        if target is None:
            return

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
        """Remove all files and directories in *target* except agents/."""
        if not os.path.isdir(target):
            return

        items = os.listdir(target)
        total = len(items)
        processed = 0

        for item in items:
            # ── PRESERVE the agents directory ────────────────────────
            if item.lower() == "agents":
                processed += 1
                frac = processed / total if total else 1.0
                self._set_progress(
                    cumulative + weight * frac,
                    "Skipping agents/ (preserved)…",
                )
                continue

            item_path = os.path.join(target, item)
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
            f"{agents_note}\n\n"
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
