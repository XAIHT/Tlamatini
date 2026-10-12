# Tlamatini Author Banner — Angela López Mendoza · @angelahack1
"""Shared, standalone presentation for the Windows setup tools.

Only Tk and the standard library are needed. Installation, process detection,
preservation and removal remain in install.py / uninstall.py.
"""
import math
import time
import tkinter as tk
from tkinter import ttk

BG = "#0e111a"
PANEL = "#151b28"
CARD = "#1c2535"
LINE = "#303d50"
TEXT = "#edf2fa"
MUTED = "#a6b4c9"
TEAL = "#79dfce"
AMBER = "#ffc08c"
RED = "#ff9eaa"
GREEN = "#91e3b5"
FONT = "Segoe UI"


def native_frame(window):
    """Use the product icon and Windows dark title bar when available."""
    import ctypes
    from pathlib import Path
    import sys
    if sys.platform != "win32":
        return
    icon = Path(getattr(sys, "_MEIPASS", Path(__file__).parent)) / "Tlamatini.ico"
    if icon.is_file():
        try:
            window.iconbitmap(default=str(icon))
        except tk.TclError:
            pass
    def decorate():
        if not window.winfo_exists():
            return
        user = ctypes.windll.user32
        user.GetAncestor.argtypes = [ctypes.c_void_p, ctypes.c_uint]
        user.GetAncestor.restype = ctypes.c_void_p
        hwnd = user.GetAncestor(window.winfo_id(), 2)
        enabled = ctypes.c_int(1)
        ctypes.windll.dwmapi.DwmSetWindowAttribute(
            ctypes.c_void_p(hwnd), 20, ctypes.byref(enabled), ctypes.sizeof(enabled))
        for attribute, color in ((35, 0x1A110E), (36, 0xFAF2ED)):
            value = ctypes.c_uint(color)
            ctypes.windll.dwmapi.DwmSetWindowAttribute(
                ctypes.c_void_p(hwnd), attribute, ctypes.byref(value), ctypes.sizeof(value))
    window.after_idle(decorate)
    window.bind("<Map>", lambda event: decorate() if event.widget == window else None, add="+")


def button(parent, text, command, *, primary=False, danger=False, **kwargs):
    """Native keyboard/focus semantics, with the shared setup palette."""
    color = AMBER if danger else TEAL
    bg, fg = (color, BG) if primary else (CARD, TEXT)
    hover = "#ffe0be" if danger else "#adf4e7"
    control = tk.Button(
        parent, text=text, command=command, font=(FONT, 10, "bold"),
        bg=bg, fg=fg, activebackground=hover if primary else LINE,
        activeforeground=BG if primary else TEXT, disabledforeground=MUTED,
        relief="flat", bd=0, padx=20, pady=10, cursor="hand2",
        highlightthickness=2, highlightbackground=bg, highlightcolor=TEXT,
        takefocus=True, **kwargs,
    )
    control.bind("<Enter>", lambda _e: control.configure(
        bg=hover if primary else LINE) if str(control["state"]) != "disabled" else None)
    control.bind("<Leave>", lambda _e: control.configure(bg=bg))
    control.bind("<Return>", lambda _e: (control.invoke(), "break")[-1])
    return control


class SetupDialog:
    """Resizable modal shell with a scrolling detail area and fixed actions."""
    def __init__(self, parent, title, heading, message):
        self.window = tk.Toplevel(parent)
        window = self.window
        native_frame(window)
        window.title(title)
        window.configure(bg=BG)
        window.transient(parent)
        scale = max(1, float(window.tk.call("tk", "scaling"))/(96/72))
        w = min(round(660*scale), window.winfo_screenwidth()-80)
        h = min(round(500*scale), window.winfo_screenheight()-120)
        window.geometry(f"{w}x{h}+{max(0,(window.winfo_screenwidth()-w)//2)}+{max(0,(window.winfo_screenheight()-h)//2)}")
        window.minsize(min(w, 540), min(h, 360))
        window.columnconfigure(0, weight=1)
        window.rowconfigure(1, weight=1)
        header = tk.Frame(window, bg=BG, padx=24, pady=20)
        header.grid(row=0, column=0, sticky="ew")
        tk.Label(header, text="TLAMATINI  /  BEFORE WE CONTINUE", bg=BG, fg=AMBER,
                 font=(FONT, 9, "bold")).pack(anchor="w", pady=(0, 12))
        title_label = tk.Label(header, text=heading, bg=BG, fg=TEXT, font=(FONT, 18, "bold"), anchor="w", justify="left")
        title_label.pack(fill="x")
        title_label.bind("<Configure>", lambda e: title_label.configure(wraplength=e.width))
        body = tk.Frame(window, bg=PANEL, padx=22, pady=16)
        body.grid(row=1, column=0, sticky="nsew", padx=24)
        self.headline = tk.StringVar(window)
        headline = tk.Label(body, textvariable=self.headline, bg=PANEL, fg=TEXT, font=(FONT, 10, "bold"), anchor="w", justify="left")
        headline.pack(fill="x", pady=(0, 12))
        headline.bind("<Configure>", lambda e: headline.configure(wraplength=e.width))
        explanation = tk.Label(body, text=message, bg=PANEL, fg=MUTED, font=(FONT, 10), anchor="w", justify="left")
        explanation.pack(fill="x", pady=(0, 14))
        explanation.bind("<Configure>", lambda e: explanation.configure(wraplength=e.width))
        area = tk.Frame(body, bg=PANEL)
        area.pack(fill="both", expand=True)
        self.details = tk.Text(area, height=5, wrap="word", bg=BG, fg=AMBER,
                               font=(FONT, 10), relief="flat", padx=12, pady=12)
        self.details.pack(side="left", fill="both", expand=True)
        scrollbar = ttk.Scrollbar(area, command=self.details.yview, style="Setup.Vertical.TScrollbar")
        scrollbar.pack(side="right", fill="y")
        self.details.configure(yscrollcommand=scrollbar.set, state="disabled")
        self.detail = tk.StringVar(window)
        self.detail.trace_add("write", self._details_changed)
        self.actions = tk.Frame(window, bg=BG, padx=24, pady=18)
        self.actions.grid(row=2, column=0, sticky="ew")

    def _details_changed(self, *_):
        self.details.configure(state="normal")
        self.details.delete("1.0", "end")
        self.details.insert("1.0", self.detail.get())
        self.details.configure(state="disabled")


class WizardView:
    """A responsive shell whose action row never competes with the checklist."""

    def __init__(self, root, *, removal, version, path, steps, start, browse,
                 preserved=()):
        self.root, self.removal = root, removal
        native_frame(root)
        self._base_title = root.title()
        self.path, self.steps, self.start = path, steps, start
        self.accent = AMBER if removal else TEAL
        self.operation = "Uninstallation" if removal else "Installation"
        self.action = "Uninstall" if removal else "Install"
        self.state = "ready"
        self.active_step = None
        self._timer = None
        self._started = 0
        self._wraps = []
        self._compact = None
        self.scale = max(1, float(root.tk.call("tk", "scaling")) / (96 / 72))
        root.configure(bg=BG)
        root.resizable(True, True)
        root.columnconfigure(0, weight=1)
        root.rowconfigure(1, weight=1)
        # Reserve space for the title bar and taskbar even with large fonts.
        sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
        w, h = min(round(960*self.scale), sw-60), min(round(720*self.scale), sh-110)
        root.geometry(f"{w}x{h}+{max(0,(sw-w)//2)}+{max(0,(sh-h)//2-24)}")
        root.minsize(min(w, round(620*self.scale)), min(h, round(440*self.scale)))

        header = tk.Frame(root, bg=BG, padx=26, pady=16)
        header.grid(row=0, column=0, sticky="ew")
        tk.Label(header, text="✦", bg=BG, fg=TEAL, font=(FONT, 24)).pack(side="left", padx=(0, 12))
        brand = tk.Frame(header, bg=BG)
        brand.pack(side="left")
        tk.Label(brand, text="TLAMATINI", font=(FONT, 13, "bold"), bg=BG, fg=TEXT).pack(anchor="w")
        tk.Label(brand, text="ONE WHO KNOWS", font=(FONT, 8), bg=BG, fg=MUTED).pack(anchor="w")
        badge = f"{self.operation.upper()}  /  v{version}" if version else self.operation.upper()
        tk.Label(header, text=badge, bg=BG, fg=MUTED, font=(FONT, 9)).pack(side="right")

        self.main = tk.Frame(root, bg=PANEL, highlightthickness=1, highlightbackground=LINE)
        self.main.grid(row=1, column=0, sticky="nsew", padx=20)
        self.main.rowconfigure(0, weight=1)
        self.main.columnconfigure(1, weight=1)
        self.sidebar = tk.Frame(self.main, bg=BG, width=round(246*self.scale))
        self.sidebar.grid(row=0, column=0, sticky="ns")
        self.sidebar.grid_propagate(False)
        self.sidebar.columnconfigure(0, weight=1)
        self.sidebar.rowconfigure(0, weight=1)
        self.art = tk.Canvas(self.sidebar, bg=BG, bd=0, highlightthickness=0)
        self.art.grid(row=0, column=0, sticky="nsew")
        self.art.bind("<Configure>", self._draw_art)
        rail = tk.Frame(self.sidebar, bg=BG, padx=24, pady=24)
        rail.grid(row=1, column=0, sticky="ew")
        self.phases = []
        for i, name in enumerate(("Review" if removal else "Destination", self.operation, "Complete")):
            label = tk.Label(rail, text=f"0{i+1}    {name}", anchor="w",
                             bg=BG, fg=self.accent if i == 0 else MUTED, font=(FONT, 10, "bold"))
            label.pack(fill="x", pady=9)
            self.phases.append(label)

        viewport = tk.Frame(self.main, bg=PANEL)
        viewport.grid(row=0, column=1, sticky="nsew")
        viewport.columnconfigure(0, weight=1)
        viewport.rowconfigure(0, weight=1)
        self.canvas = tk.Canvas(viewport, bg=PANEL, highlightthickness=0, bd=0, takefocus=False)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        style = ttk.Style(root)
        style.theme_use("clam")
        style.configure("Setup.Vertical.TScrollbar", background=LINE, troughcolor=PANEL,
                        bordercolor=PANEL, arrowcolor=MUTED, lightcolor=LINE, darkcolor=LINE)
        style.map("Setup.Vertical.TScrollbar", background=[("active", MUTED), ("!active", LINE)])
        self.scroll = ttk.Scrollbar(viewport, orient="vertical", command=self.canvas.yview,
                                    style="Setup.Vertical.TScrollbar")
        self.scroll.grid(row=0, column=1, sticky="ns")
        self.canvas.configure(yscrollcommand=self.scroll.set)
        self.content = tk.Frame(self.canvas, bg=PANEL, padx=30, pady=26)
        self.content_id = self.canvas.create_window(0, 0, window=self.content, anchor="nw")
        self.canvas.bind("<Configure>", self._resize_content)
        self.content.bind("<Configure>", lambda _e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        root.bind("<MouseWheel>", self._wheel, add="+")
        root.bind("<Configure>", self._resize_window, add="+")
        root.bind("<FocusIn>", self._reveal_focus, add="+")

        self.eyebrow = self.label(self.content, "YOUR NEXT CHAPTER", 9, self.accent, True)
        self.eyebrow.pack(fill="x", pady=(0, 9))
        self.heading = self.label(self.content, "", 25, TEXT, True)
        self.heading.pack(fill="x", pady=(0, 9))
        self.subtitle = self.label(self.content, "", 10, MUTED)
        self.subtitle.pack(fill="x", pady=(0, 24))

        self.setup_frame = tk.Frame(self.content, bg=PANEL)
        self.label(self.setup_frame, "INSTALLATION FOLDER" if removal else "CHOOSE A DESTINATION", 9, MUTED, True).pack(fill="x", pady=(0, 9))
        row = tk.Frame(self.setup_frame, bg=PANEL)
        row.pack(fill="x")
        self.path_entry = tk.Entry(row, textvariable=path, font=(FONT, 11), bg=BG, fg=TEXT,
                                   insertbackground=self.accent, relief="flat", bd=0,
                                   highlightthickness=2, highlightbackground=LINE,
                                   highlightcolor=self.accent, disabledbackground=BG,
                                   disabledforeground=MUTED)
        self.path_entry.pack(side="left", fill="x", expand=True, ipady=10, padx=(0, 8))
        self.browse_btn = button(row, "Browse…", browse)
        self.browse_btn.pack(side="right")
        self.target_label = self.label(self.setup_frame, "", 9, self.accent)
        self.target_label.pack(fill="x", pady=(10, 22))
        path.trace_add("write", self._path_changed)
        self._path_changed()

        self.info = tk.Frame(self.setup_frame, bg=CARD, padx=18, pady=16,
                             highlightbackground=LINE, highlightthickness=1)
        self.info.pack(fill="x")
        self.label(self.info, "YOUR WORK STAYS WITH YOU" if removal else "BUILT FOR YOUR NEXT IDEA", 9, self.accent, True).pack(fill="x", pady=(0, 10))
        self.preservation_text = ("Always kept: agents/\n\nKept when they contain files: "
                                  + ", ".join(name + "/" for name in preserved)
                                  + "\n\nEverything else, including Temp/, is removed.") if removal else (
            "Your local workspace, ready to create.\n\n"
            "Setup extracts Tlamatini, configures its agents, creates Desktop shortcuts "
            "and connects .flw and .fpmt flow files.")
        self.label(self.info, self.preservation_text, 10, MUTED).pack(fill="x")

        self.progress_frame = tk.Frame(self.content, bg=PANEL)
        progress_head = tk.Frame(self.progress_frame, bg=PANEL)
        progress_head.pack(fill="x", pady=(0, 10))
        self.step_label = self.label(progress_head, "Preparing…", 11, TEXT, True)
        self.step_label.pack(side="left", fill="x", expand=True)
        self.pct_label = tk.Label(progress_head, text="0%", font=(FONT, 21, "bold"), bg=PANEL, fg=self.accent)
        self.pct_label.pack(side="right", padx=(12, 0))
        style_name = "Removal.Horizontal.TProgressbar" if removal else "Install.Horizontal.TProgressbar"
        style.configure(style_name, troughcolor=BG, background=self.accent,
                        darkcolor=self.accent, lightcolor=self.accent, bordercolor=BG, thickness=7)
        self.progress_bar = ttk.Progressbar(self.progress_frame, style=style_name, maximum=100)
        self.progress_bar.pack(fill="x", pady=(0, 20))
        self.check_labels = []
        for i, (desc, _) in enumerate(steps):
            label = self.label(self.progress_frame, f"{i+1:02}   {desc.rstrip('…')}", 10, MUTED)
            label.pack(fill="x", pady=6)
            self.check_labels.append(label)

        self.result_frame = tk.Frame(self.content, bg=PANEL)
        self.result_label = self.label(self.result_frame, "", 11, TEXT)
        self.result_label.pack(fill="x", pady=(0, 16))
        detail_area = tk.Frame(self.result_frame, bg=PANEL)
        detail_area.pack(fill="both", expand=True)
        detail_area.columnconfigure(0, weight=1)
        detail_area.rowconfigure(0, weight=1)
        # Reserve the scrollbar's column before giving the text remaining room.
        # Packing the wide text first could squeeze the scrollbar to zero width.
        self.details = tk.Text(detail_area, width=1, height=9, wrap="word", bg=BG, fg=MUTED,
                               font=(FONT, 10), relief="flat", padx=16, pady=14,
                               highlightthickness=1, highlightbackground=LINE,
                               highlightcolor=self.accent, insertbackground=TEXT)
        self.details.grid(row=0, column=0, sticky="nsew")
        self.detail_scroll = ttk.Scrollbar(detail_area, command=self.details.yview,
                                          style="Setup.Vertical.TScrollbar")
        self.detail_scroll.grid(row=0, column=1, sticky="ns")
        self.details.configure(yscrollcommand=self.detail_scroll.set, state="disabled")
        self.details.bind("<Control-a>", lambda _e: (self.details.tag_add("sel", "1.0", "end-1c"), "break")[-1])

        # A separate root grid row guarantees full actions at every body height.
        footer = self.footer = tk.Frame(root, bg=BG, padx=24, pady=18)
        footer.grid(row=2, column=0, sticky="ew")
        footer.columnconfigure(0, weight=1)
        self.footer_label = tk.Label(footer, text="", bg=BG, fg=MUTED, anchor="w", justify="left", font=(FONT, 9))
        self.footer_label.grid(row=0, column=0, sticky="ew", padx=(0, 14))
        self.button_row = tk.Frame(footer, bg=BG)
        self.button_row.grid(row=0, column=1, sticky="e")
        self.cancel_btn = button(self.button_row, "Cancel", self.close)
        self.cancel_btn.pack(side="left", padx=(0, 10))
        self.primary_btn = button(self.button_row, self.action, start, primary=True, danger=removal)
        self.primary_btn.pack(side="left")
        root.protocol("WM_DELETE_WINDOW", self.close)
        root.bind("<Escape>", lambda _e: self.close())
        root.bind("<Return>", self._enter)
        root.bind("<Destroy>", self._destroyed, add="+")
        self.show_setup()

    def label(self, parent, text, size, fg, bold=False):
        control = tk.Label(parent, text=text, font=(FONT, size, "bold" if bold else "normal"),
                           bg=parent["bg"], fg=fg, anchor="w", justify="left", wraplength=400)
        self._wraps.append(control)
        control.bind("<Configure>", lambda e: control.configure(wraplength=max(100, e.width-2)))
        return control

    def _path_changed(self, *_):
        import os
        raw = self.path.get().strip()
        target = raw if self.removal else os.path.join(raw, "Tlamatini") if raw else ""
        self.target_label.configure(text=("Selected: " if self.removal else "Install to: ") + target if target else "A Tlamatini folder will be created inside your selected directory.")

    def _resize_content(self, event):
        self.canvas.itemconfigure(self.content_id, width=event.width)

    def _resize_window(self, event):
        if event.widget != self.root:
            return
        compact = event.width < 850*self.scale
        if compact != self._compact:
            self._compact = compact
            self.sidebar.grid_remove() if compact else self.sidebar.grid()
        self.footer_label.configure(wraplength=max(140, self.footer_label.winfo_width()))

    def _wheel(self, event):
        # Text has its own scroll bindings; never scroll both surfaces at once.
        if event.widget == self.details:
            return
        if self.canvas.bbox("all")[3] > self.canvas.winfo_height():
            self.canvas.yview_scroll(-int(event.delta/120), "units")

    def _reveal_focus(self, event):
        control = event.widget
        if control == self.path_entry or control == self.browse_btn:
            self.canvas.yview_moveto(0)

    def _enter(self, _event):
        if self.state != "working":
            focused = self.root.focus_get()
            if isinstance(focused, tk.Button):
                focused.invoke()
            elif focused != self.details:
                self.primary_btn.invoke()
        return "break"

    def _draw_art(self, event):
        c, w, h = self.art, event.width, event.height
        c.delete("all")
        cx, cy = w/2, h*.48
        r = min(w*.36, h*.30)
        for i in range(28):
            x, y = (i*73+19) % max(w, 1), (i*97+31) % max(h, 1)
            c.create_oval(x, y, x+2, y+2, fill=LINE, outline="")
        for factor in (1.0, 1.28, 1.55):
            a = r*factor
            c.create_oval(cx-a, cy-a, cx+a, cy+a, outline=LINE, width=1)
        c.create_arc(cx-r*1.28, cy-r*1.28, cx+r*1.28, cy+r*1.28,
                     start=35, extent=105, style="arc", outline=self.accent, width=2)
        c.create_arc(cx-r*1.55, cy-r*1.55, cx+r*1.55, cy+r*1.55,
                     start=205, extent=36, style="arc", outline=TEAL, width=2)
        points = [(cx+math.sin(i*math.pi/3)*r*.7, cy-math.cos(i*math.pi/3)*r*.7) for i in range(6)]
        c.create_polygon(*[n for p in points for n in p], fill=CARD, outline=self.accent, width=2)
        for i in (0, 2, 4):
            x, y = points[i]
            c.create_line(cx, cy, x, y, fill=self.accent, width=2)
        c.create_oval(cx-4, cy-4, cx+4, cy+4, fill=self.accent, outline="")
        c.create_text(cx, min(h-22, cy+r*1.55+30), text="INTELLIGENCE, IN YOUR ORBIT",
                      fill=MUTED, font=(FONT, 7))

    def _page(self, frame):
        for page in (self.setup_frame, self.progress_frame, self.result_frame):
            page.pack_forget()
        frame.pack(fill="x")
        self.canvas.yview_moveto(0)

    def _phase(self, index):
        for i, label in enumerate(self.phases):
            label.configure(fg=GREEN if i < index else self.accent if i == index else MUTED)

    def show_setup(self):
        self.state = "ready"
        self.root.title(self._base_title)
        self._phase(0)
        self.eyebrow.configure(text="YOUR WORK. YOUR CHOICE." if self.removal else "YOUR NEXT CHAPTER", fg=self.accent)
        self.heading.configure(text="Leave with your work." if self.removal else "Make room for possibility.", fg=TEXT)
        self.subtitle.configure(text="Review what stays before removing Tlamatini from this computer." if self.removal else "Bring Tlamatini to your workspace. Choose its home; we’ll take care of the setup.")
        self.footer_label.configure(text="You’ll confirm before removal." if self.removal else "Ready when you are.", fg=MUTED)
        self.primary_btn.configure(text=self.action, command=self.start, state="normal")
        self.cancel_btn.configure(text="Cancel", command=self.close)
        self.button_row.grid()
        self.path_entry.configure(state="normal")
        self.browse_btn.configure(state="normal")
        self._page(self.setup_frame)

    def begin(self, target):
        print(f"BEGIN {self.operation}: {target}", flush=True)
        self.state, self.active_step = "working", None
        self.root.title(f"Tlamatini — {self.operation} in progress")
        self._started = time.monotonic()
        self._phase(1)
        self.eyebrow.configure(text="REMOVING TLAMATINI" if self.removal else "SETTING THINGS IN MOTION", fg=self.accent)
        self.heading.configure(text="A considered departure." if self.removal else "Your workspace is taking shape.", fg=TEXT)
        self.subtitle.configure(text=target)
        self.button_row.grid_remove()
        self.path_entry.configure(state="disabled")
        self.browse_btn.configure(state="disabled")
        for i, (desc, _) in enumerate(self.steps):
            self.check_labels[i].configure(text=f"{i+1:02}   {desc.rstrip('…')}", fg=MUTED)
        self.update_progress(0, "Preparing…")
        self._page(self.progress_frame)
        self._tick()

    def update_progress(self, value, status=None):
        pct = max(0, min(int(value*100), 100))
        if self.state == "working":
            self.root.title(f"Tlamatini — {self.operation} in progress · {pct}%")
        self.progress_bar["value"] = pct
        self.pct_label.configure(text=f"{pct}%")
        if status:
            self.step_label.configure(text=status)
            now = time.monotonic()
            if now - getattr(self, "_last_progress_log", 0) >= 10:
                print(f"PROGRESS {pct}%: {status}", flush=True)
                self._last_progress_log = now

    def mark_step(self, idx, success=True):
        self.check_labels[idx].configure(text=f"{'✓' if success else '×'}    {self.steps[idx][0].rstrip('…')}", fg=GREEN if success else RED)

    def activate_step(self, idx):
        print(f"STEP {idx+1}: {self.steps[idx][0]}", flush=True)
        self.active_step = idx
        self.check_labels[idx].configure(text=f"›    {self.steps[idx][0].rstrip('…')}", fg=self.accent)

    def _tick(self):
        self._stop_timer()
        if self.state == "working":
            seconds = int(time.monotonic()-self._started)
            self.footer_label.configure(text=f"{self.operation} in progress  ·  {seconds//60:02}:{seconds%60:02} elapsed\nPlease keep this window open.", fg=MUTED)
            self._timer = self.root.after(1000, self._tick)

    def _stop_timer(self):
        if self._timer is not None:
            self.root.after_cancel(self._timer)
            self._timer = None

    def finish(self, *, success, detail, target=""):
        from setup_logging import result_detail
        print(f"{'COMPLETE' if success else 'FAILED'} {self.operation}: {detail}", flush=True)
        detail = result_detail(detail)
        self.state = "complete" if success else "error"
        self.root.title(f"Tlamatini — {self.operation} {'complete' if success else 'needs attention'}")
        self._stop_timer()
        self._phase(2 if success else 1)
        self.eyebrow.configure(text="ALL SET" if success else "LET’S GET THIS RESOLVED", fg=GREEN if success else RED)
        self.heading.configure(text=("Your next chapter awaits." if self.removal else "Welcome to Tlamatini.") if success else f"{self.operation} needs attention.", fg=TEXT)
        self.subtitle.configure(text=("Tlamatini has been removed. Review the retained files below." if self.removal else "Setup is complete. Open Tlamatini from your Desktop shortcut.") if success else "The operation stopped before completion. Review the details, then try again.")
        self.result_label.configure(text=target if success else "What happened", fg=GREEN if success else RED)
        self.details.configure(state="normal")
        self.details.delete("1.0", "end")
        self.details.insert("1.0", detail)
        self.details.configure(state="disabled")
        self.details.yview_moveto(0)
        self._page(self.result_frame)
        self.button_row.grid()
        self.primary_btn.configure(text="Close" if success else "Retry", command=self.close if success else self.start, state="normal")
        self.cancel_btn.configure(text="Change folder" if not success else "Close", command=self.show_setup if not success else self.close)
        self.cancel_btn.pack_forget() if success else self.cancel_btn.pack(side="left", padx=(0, 10), before=self.primary_btn)
        self.footer_label.configure(text="Finished." if success else "You can retry, change the folder, or close this window.", fg=GREEN if success else MUTED)
        self.primary_btn.focus_set()

    def close(self):
        if self.state == "working":
            self.footer_label.configure(text=f"{self.operation} is still running.\nThis window will be ready to close when it finishes.", fg=self.accent)
            self.root.bell()
            return
        self.root.destroy()

    def _destroyed(self, event):
        if event.widget == self.root:
            self._stop_timer()
