"""uninstaller_visible.py — VISIBLE end-to-end test of the Tlamatini Uninstaller.

Golden rule of this repository: NO HEADLESS TESTS.  This harness puts the REAL
uninstall.py GUI on Angela's real desktop, against a REAL throw-away
installation, with a REAL process running out of it, so Tlamatini's own Mouser /
Keyboarder / Shoter agents can drive it and photograph every step.

WHAT IS REAL HERE
  * the real ``FancyUninstaller`` imported from uninstall.py — not a copy
  * a real installation tree on disk, really deleted at the end
  * a real running process — a copy of cmd.exe named ``Tlamatini.exe`` living
    INSIDE that tree — so the still-running gate has something true to find
  * the real modal gate, the real Retry loop, the real completion dialog

WHAT IS DELIBERATELY NOT REAL, AND WHY
  * ``_unregister_programs_entry()`` would delete Angela's OWN HKCU
    "Installed apps" key for the REAL Tlamatini installation
  * ``_restart_explorer()`` would kill and restart her actual desktop
  Both are stubbed, and each stub SAYS SO in the console and in result.json.
  Nothing else is patched — in particular the still-running detection, the
  preserve rules and every dialog are the shipping code, untouched.

SAFETY BELT
  ``_detect_install_path()`` can auto-fill Angela's REAL ``C:\\Tlamatini`` from
  the registry.  A 250 ms poll therefore FORCES the path entry back to the fake
  installation and aborts loudly if it is ever pointed anywhere else, so this
  test can only ever delete its own scratch tree.

Usage:
    python uninstaller_visible.py            # set up + show the GUI
    python uninstaller_visible.py --verify   # verify the tree afterwards only
"""

import json
import os
import shutil
import subprocess
import sys
import threading
import time
import tkinter as tk
from pathlib import Path

HARNESS_DIR = Path(__file__).resolve().parent
REPO_ROOT = HARNESS_DIR.parents[3]
sys.path.insert(0, str(REPO_ROOT))

# Temp/Templates policy (Rule 15): every scratch file of this harness lives
# under <repo>/Temp, never %TEMP% and never C:\Temp.
RUN_ROOT = REPO_ROOT / "Temp" / "UninstallerVisibleTest"
FAKE_INSTALL = RUN_ROOT / "FakeTlamatini"
SHOTS_DIR = RUN_ROOT / "shots"
COORDS_PATH = RUN_ROOT / "coords.json"
RESULT_PATH = RUN_ROOT / "result.json"
STATE_PATH = RUN_ROOT / "state.json"


# ── The fake installation ────────────────────────────────────────────────────
# Each entry: (relative path, kind, expectation after the uninstallation)
#   kind "file" / "dir"
#   expectation True  = MUST still exist
#   expectation False = MUST be gone
LAYOUT = [
    # markers that make _validate_path() accept the directory
    ("Tlamatini.ps1",                       "file", False),
    ("CreateShortcut.json",                 "file", False),
    # always preserved
    ("agents/shoter/shoter.py",             "file", True),
    ("agents/shoter/config.yaml",           "file", True),
    ("agents/_tlamatini_agents_manifest.json", "file", True),
    # preserved BECAUSE they hold content
    ("application/MyProject/main.py",       "file", True),
    ("content_generated/report.md",         "file", True),
    ("Temp/scratch.tmp",                    "file", True),
    # NOT preserved: no file at any depth
    ("applications",                        "dir",  False),
    ("context_files/empty_subfolder",       "dir",  False),
    # ordinary installation files — all must go
    ("config.json",                         "file", False),
    ("tlamatini.log",                       "file", False),
    ("_internal/base_library.zip",          "file", False),
    ("_internal/agent/prompt.pmt",          "file", False),
    ("python/python.exe.txt",               "file", False),
]

EXPECTED_PRESERVED_LEGEND = ["application", "content_generated", "Temp"]
EXPECTED_REMOVED_DIRS = ["applications", "context_files"]


def log(msg):
    print(msg, flush=True)


def banner(msg):
    log("")
    log("=" * 78)
    log(f"  {msg}")
    log("=" * 78)


# ── Setup ────────────────────────────────────────────────────────────────────
def build_fake_installation() -> Path:
    """Create the throw-away installation this test will really delete."""
    if FAKE_INSTALL.exists():
        shutil.rmtree(FAKE_INSTALL, ignore_errors=True)
    FAKE_INSTALL.mkdir(parents=True, exist_ok=True)
    SHOTS_DIR.mkdir(parents=True, exist_ok=True)

    for rel, kind, _expected in LAYOUT:
        target = FAKE_INSTALL / rel
        if kind == "dir":
            target.mkdir(parents=True, exist_ok=True)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(
                f"throw-away test content for {rel}\n", encoding="utf-8",
            )

    # Tlamatini.exe = a real, runnable copy of cmd.exe.  It is both the marker
    # _validate_path() looks for AND the process the gate must detect, so the
    # detection is exercised against a genuine running image inside the tree.
    comspec = os.environ.get("COMSPEC", r"C:\Windows\System32\cmd.exe")
    shutil.copy2(comspec, FAKE_INSTALL / "Tlamatini.exe")
    log(f"  fake installation : {FAKE_INSTALL}")
    log(f"  Tlamatini.exe     : copy of {comspec}")
    return FAKE_INSTALL


def start_fake_tlamatini() -> subprocess.Popen:
    """Launch the fake Tlamatini in its own VISIBLE console window.

    A copy of cmd.exe, running from inside the installation directory — exactly
    the shape the gate has to catch, and visible on screen so Angela can watch
    it being detected and then closed.
    """
    exe = FAKE_INSTALL / "Tlamatini.exe"
    creation = 0
    if sys.platform == "win32":
        creation = subprocess.CREATE_NEW_CONSOLE
    proc = subprocess.Popen(
        [str(exe), "/k",
         "title Tlamatini (simulated instance) && "
         "echo. && echo   *** SIMULATED TLAMATINI INSTANCE *** && "
         "echo   This console stands in for a running Tlamatini. && "
         "echo   The uninstaller must REFUSE to run while I am alive. && echo."],
        cwd=str(FAKE_INSTALL),
        creationflags=creation,
    )
    log(f"  fake instance PID : {proc.pid}  (running from the installation)")
    return proc


# ── Coordinate export so Mouser can click REAL pixels ────────────────────────
def _collect_buttons(widget, out):
    try:
        children = widget.winfo_children()
    except Exception:
        return
    for child in children:
        try:
            if isinstance(child, tk.Button) and child.winfo_ismapped():
                text = " ".join(str(child.cget("text")).split())
                out[text] = [
                    child.winfo_rootx() + child.winfo_width() // 2,
                    child.winfo_rooty() + child.winfo_height() // 2,
                ]
        except Exception:
            pass
        _collect_buttons(child, out)


def dpi_scale() -> float:
    """Physical pixels per logical pixel on the primary display.

    ⚠ MEASURED THE HARD WAY (2026-09-13).  Tk reports widget positions in the
    DPI-VIRTUALISED space its process sees (1707x1067 on a 150 % 2560x1600
    screen), while pyautogui — which is what Mouser drives — moves the cursor in
    REAL pixels.  Publishing only Tk's numbers sent every click to two thirds of
    the intended position, which on a dialog full of buttons means clicking the
    WRONG one and believing the test drove the app.  ``GetDeviceCaps`` answers
    honestly even from a DPI-unaware process, so the factor is measured, never
    assumed.  Fail-open to 1.0.
    """
    try:
        import ctypes
        HORZRES, DESKTOPHORZRES = 8, 118
        dc = ctypes.windll.user32.GetDC(0)
        try:
            logical = ctypes.windll.gdi32.GetDeviceCaps(dc, HORZRES)
            physical = ctypes.windll.gdi32.GetDeviceCaps(dc, DESKTOPHORZRES)
        finally:
            ctypes.windll.user32.ReleaseDC(0, dc)
        if logical > 0 and physical > 0:
            return physical / logical
    except Exception:
        pass
    return 1.0


_SCALE = dpi_scale()


def export_coords(root, app):
    """Publish every visible button's SCREEN centre, 4x a second.

    The application tells us where its own buttons are; Mouser then physically
    clicks those pixels.  Nothing is invoked programmatically.

    ``buttons`` are Tk's own (logical) coordinates; ``click_at`` are the REAL
    pixels a driver must aim at.  Always drive from ``click_at``.
    """
    data = {"ts": time.time(), "buttons": {}, "click_at": {}, "windows": [],
            "dpi_scale": _SCALE, "path_entry": ""}
    try:
        _collect_buttons(root, data["buttons"])
        data["click_at"] = {
            name: [round(x * _SCALE), round(y * _SCALE)]
            for name, (x, y) in data["buttons"].items()
        }
        for win in [root] + list(root.winfo_children()):
            if isinstance(win, tk.Toplevel) or win is root:
                try:
                    if win.winfo_viewable():
                        data["windows"].append(win.title())
                except Exception:
                    pass
        data["screen"] = [root.winfo_screenwidth(), root.winfo_screenheight()]
        data["path_entry"] = app.install_path.get()
        data["gate_headline"] = str(getattr(app, "gate_headline_var", "") and
                                    app.gate_headline_var.get())
        data["gate_detail"] = str(getattr(app, "gate_detail_var", "") and
                                  app.gate_detail_var.get())
        data["gate_attempts"] = app._gate_attempts
        data["preserved_dirs"] = list(app.preserved_dirs)
    except Exception as exc:
        data["error"] = str(exc)

    try:
        tmp = COORDS_PATH.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
        os.replace(tmp, COORDS_PATH)
    except Exception:
        pass


def keep_on_top(root):
    """Hold the test in front of everything else on the desktop.

    A visible test that another window covers is not a visible test — and a
    driver clicking published coordinates would be clicking whatever floated
    over them.  Re-asserted every tick because media players and browsers
    re-raise themselves.
    """
    try:
        root.attributes("-topmost", True)
        for child in root.winfo_children():
            if isinstance(child, tk.Toplevel) and child.winfo_exists():
                child.attributes("-topmost", True)
    except Exception:
        pass


def guard_path(app):
    """SAFETY BELT: the uninstaller may only ever act on the fake install."""
    current = app.install_path.get().strip()
    if os.path.normcase(current) != os.path.normcase(str(FAKE_INSTALL)):
        log(f"!! SAFETY: path entry was '{current}' — forcing it back.")
        app.install_path.set(str(FAKE_INSTALL))


# ── Verification ─────────────────────────────────────────────────────────────
def verify_tree(preserved_dirs) -> dict:
    checks = []

    for rel, kind, expected in LAYOUT:
        path = FAKE_INSTALL / rel
        exists = path.exists()
        checks.append({
            "what": f"{rel} {'exists' if expected else 'removed'}",
            "ok": exists == expected,
            "detail": f"expected exists={expected}, got exists={exists}",
        })

    reported = list(dict.fromkeys(preserved_dirs))
    checks.append({
        "what": "legend names exactly the directories that held content",
        "ok": sorted(reported) == sorted(EXPECTED_PRESERVED_LEGEND),
        "detail": f"reported={reported} expected={EXPECTED_PRESERVED_LEGEND}",
    })
    for name in EXPECTED_REMOVED_DIRS:
        checks.append({
            "what": f"legend does NOT name the empty directory {name}",
            "ok": name not in reported,
            "detail": f"reported={reported}",
        })
    checks.append({
        "what": "legend is dynamic, not the static five-name list",
        "ok": len(reported) < 5,
        "detail": f"reported {len(reported)} of 5 candidate directories",
    })

    return {
        "passed": all(c["ok"] for c in checks),
        "checks": checks,
        "preserved_dirs": reported,
    }


def write_result(payload):
    RUN_ROOT.mkdir(parents=True, exist_ok=True)
    RESULT_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")


# ── Main ─────────────────────────────────────────────────────────────────────
def main():
    RUN_ROOT.mkdir(parents=True, exist_ok=True)

    if "--verify" in sys.argv:
        state = json.loads(STATE_PATH.read_text(encoding="utf-8"))
        result = verify_tree(state.get("preserved_dirs", []))
        write_result(result)
        log(json.dumps(result, indent=2))
        return 0 if result["passed"] else 1

    banner("TLAMATINI UNINSTALLER — VISIBLE END-TO-END TEST")
    log("  Every step happens on your real desktop, on a throw-away")
    log("  installation.  Your real C:\\Tlamatini is never touched.")
    log("")

    # ⚠ DPI awareness is deliberately NOT touched.  The shipped Uninstaller.exe
    # manifest does not request it, so leaving it alone keeps this window in the
    # same coordinate space the real one lives in — and that is also the space
    # Mouser drives (pyautogui is DPI-unaware, so SetCursorPos is virtualised the
    # same way).  coords.json publishes the screen size it saw, so the driver can
    # tell the two spaces apart instead of guessing.

    build_fake_installation()
    fake_proc = start_fake_tlamatini()

    import uninstall

    # The two calls that would reach OUTSIDE the throw-away tree.
    def _stub_registry():
        log("  [STUBBED] _unregister_programs_entry() — would delete the REAL "
            "HKCU Installed-apps key.")

    def _stub_explorer():
        log("  [STUBBED] _restart_explorer() — would kill and restart the REAL "
            "Windows desktop.")

    uninstall.FancyUninstaller._unregister_programs_entry = staticmethod(_stub_registry)
    uninstall.FancyUninstaller._restart_explorer = staticmethod(_stub_explorer)
    log("  Two machine-wide side effects are stubbed (see the banner above).")
    log("  Everything else is the shipping uninstaller, unpatched.")

    root = tk.Tk()
    root.withdraw()
    app = uninstall.FancyUninstaller(root)
    app.install_path.set(str(FAKE_INSTALL))

    # ── Event trace ──────────────────────────────────────────────────────
    # A test that cannot say WHO pressed what is a test nobody can trust.
    # These wrappers only OBSERVE; every one calls straight through.
    def trace(name, fn):
        def wrapped(*a, **k):
            log(f"  [TRACE {time.strftime('%H:%M:%S')}] {name}")
            return fn(*a, **k)
        return wrapped

    app._start_uninstall = trace("Uninstall pressed", app._start_uninstall)
    # The buttons captured their command when __init__ built them, so rewire
    # them too — otherwise a real click bypasses the trace entirely.
    app.uninstall_btn.config(command=app._start_uninstall)
    app.cancel_btn.config(command=trace("Cancel pressed", app.root.quit))
    app._show_running_gate = trace("gate opened", app._show_running_gate)
    app._shutdown = trace("EXIT chosen -> uninstaller shutting down",
                          app._shutdown)
    app._confirm_removal = trace("confirmation asked", app._confirm_removal)
    app._show_success = trace("completion dialog", app._show_success)
    root.bind_all("<Key>", lambda e: log(
        f"  [KEY {time.strftime('%H:%M:%S')}] {e.keysym}"), add="+")
    root.bind_all("<Button-1>", lambda e: log(
        f"  [CLICK {time.strftime('%H:%M:%S')}] screen ({e.x_root},{e.y_root}) "
        f"on {e.widget}"), add="+")

    def poll():
        guard_path(app)
        keep_on_top(root)
        export_coords(root, app)
        try:
            root.after(250, poll)
        except Exception:
            pass

    poll()
    root.update_idletasks()
    root.deiconify()
    root.lift()

    log("")
    log("  GUI is up.  Driving it now with Mouser / Keyboarder…")
    log(f"  coordinates → {COORDS_PATH}")

    # Never leave a GUI hanging on Angela's desktop if the driver dies.
    def watchdog():
        time.sleep(900)
        log("!! watchdog: 15 minutes elapsed — closing the test window.")
        try:
            root.destroy()
        except Exception:
            pass

    threading.Thread(target=watchdog, daemon=True).start()

    root.mainloop()
    log(f"  [TRACE {time.strftime('%H:%M:%S')}] the GUI closed — verifying")

    preserved = list(app.preserved_dirs)
    STATE_PATH.write_text(
        json.dumps({"preserved_dirs": preserved,
                    "gate_attempts": app._gate_attempts}, indent=2),
        encoding="utf-8",
    )

    try:
        fake_proc.kill()
    except Exception:
        pass

    banner("VERIFYING THE TREE ON DISK")
    result = verify_tree(preserved)
    result["gate_attempts"] = app._gate_attempts
    write_result(result)

    for check in result["checks"]:
        log(f"  [{'PASS' if check['ok'] else 'FAIL'}] {check['what']}")
        if not check["ok"]:
            log(f"         {check['detail']}")

    banner("RESULT: " + ("PASS — every check is true"
                         if result["passed"] else "FAIL — see above"))
    log(f"  preserved directories reported to the user: {result['preserved_dirs']}")
    log(f"  retries the user needed on the gate       : {app._gate_attempts}")
    log("")
    log("  This window stays open so you can read it.  Close it when done.")
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
