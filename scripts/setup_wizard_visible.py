# Tlamatini Author Banner — Angela López Mendoza · @angelahack1
"""Visible source UI validation, NOT compiled release acceptance.

Run from a verified, foreground PowerShell -NoExit window. Real Tk windows,
whole-desktop Shoter photos, UI-state fixtures only: no package extraction,
registry writes, process termination or uninstallation. --preview leaves a
safe interactive gallery open; its Install/Uninstall buttons only animate a
preview. Never use this gallery to certify the actual installation pipeline.
"""
import argparse
import ctypes
import html
import json
from pathlib import Path
import sys
import time
import tkinter as tk
import traceback

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "Temp/setup-wizard-visible"
sys.path.insert(0, str(ROOT))
import install
import uninstall
import drag_divider_look_visible as photographs
from markdown_canvas_visible import visible_console

photographs.OUT = OUT
RESULTS = []


def visible(root):
    import win32gui
    import win32con
    import win32api
    import win32process
    root.deiconify()
    root.attributes("-topmost", True)
    root.lift()
    root.focus_force()
    root.update()
    hwnd = win32gui.GetAncestor(root.winfo_id(), win32con.GA_ROOT)
    other, _ = win32process.GetWindowThreadProcessId(win32gui.GetForegroundWindow())
    own = win32api.GetCurrentThreadId()
    try:
        if own != other:
            win32process.AttachThreadInput(own, other, True)
        if win32gui.GetForegroundWindow() != hwnd:
            win32api.keybd_event(win32con.VK_MENU, 0, 0, 0)
            win32api.keybd_event(win32con.VK_MENU, 0, win32con.KEYEVENTF_KEYUP, 0)
        win32gui.SetForegroundWindow(hwnd)
    finally:
        if own != other:
            win32process.AttachThreadInput(own, other, False)
    root.update()
    cloaked = ctypes.c_int()
    ctypes.windll.dwmapi.DwmGetWindowAttribute(ctypes.c_void_p(hwnd), 14, ctypes.byref(cloaked), 4)
    if (not root.winfo_viewable() or win32gui.IsIconic(hwnd) or cloaked.value
            or win32gui.GetForegroundWindow() != hwnd):
        raise RuntimeError("Actual foreground wizard visibility could not be confirmed")
    return win32gui.GetWindowText(hwnd)


def pump(root, seconds=1.3):
    end = time.monotonic()+seconds
    while time.monotonic() < end:
        root.update()
        time.sleep(.03)


def whole(control, root):
    assert control.winfo_ismapped(), f"Unmapped {control}"
    assert control.winfo_height() >= control.winfo_reqheight(), f"Clipped height: {control}"
    assert control.winfo_width() >= control.winfo_reqwidth(), f"Clipped width: {control}"
    assert control.winfo_rooty()+control.winfo_height() <= root.winfo_rooty()+root.winfo_height(), f"Outside window: {control}"


def checkpoint(root, name, assertion):
    foreground = visible(root)
    pump(root)
    assertion()
    path, _ = photographs.shoter(f"{len(RESULTS)+1:02}-{name}.png")
    RESULTS.append({"name": name, "photo": path.name, "foreground": foreground, "passed": True})
    print(f"PASS {len(RESULTS):02}: {name} | foreground={foreground}", flush=True)
    (OUT / "results.json").write_text(json.dumps(RESULTS, indent=2), encoding="utf-8")


class InstallerPreview(install.FancyInstaller):
    @staticmethod
    def _find_zip():
        return str(OUT / "preview-only-pkg.zip")

    def _start_install(self):
        preview_run(self)


class UninstallerPreview(uninstall.FancyUninstaller):
    @staticmethod
    def _detect_install_path():
        return str(OUT / "Preview workspace" / "Tlamatini")

    def _start_uninstall(self):
        preview_run(self)


def preview_run(app):
    """Deliberately presentation-only. No filesystem or Windows mutations."""
    if app.ui.state in ("working", "complete"):
        return
    app.ui.begin(app.install_path.get())
    def stage(index=0):
        if index:
            app.ui.mark_step(index-1)
        if index == len(app.STEPS):
            app.ui.update_progress(1)
            app.ui.finish(success=True, target=app.install_path.get(), detail="PREVIEW ONLY\n\nThis gallery demonstrates the completion screen. No installation or removal was performed.")
            return
        app.ui.activate_step(index)
        app.ui.update_progress(index/len(app.STEPS), app.STEPS[index][0])
        app.root.after(1600, stage, index+1)
    stage()


def make(removal=False, scaling=None, versionless=False):
    root = tk.Tk()
    if scaling:
        root.tk.call("tk", "scaling", scaling)
    module = uninstall if removal else install
    saved = module.resolve_version
    if versionless:
        module.resolve_version = lambda: ""
    try:
        app = (UninstallerPreview if removal else InstallerPreview)(root)
    finally:
        module.resolve_version = saved
    if not removal:
        app.install_path.set(str(OUT / "Preview workspace"))
    root.title(f"Tlamatini {'Uninstaller' if removal else 'Installer'} — UI PREVIEW ONLY")
    visible(root)
    return root, app


def assert_ready(root, ui):
    for control in (ui.primary_btn, ui.cancel_btn, ui.browse_btn):
        whole(control, root)
    assert ui.path_entry.winfo_ismapped()
    assert ui.state == "ready"


def assert_busy(root, ui):
    assert ui.state == "working"
    assert not ui.button_row.winfo_ismapped(), "Actions must disappear completely during work"
    assert not ui.primary_btn.winfo_ismapped()
    assert not ui.cancel_btn.winfo_ismapped()
    assert ui.progress_bar.winfo_width() > 150
    whole(ui.footer_label, root)


def assert_details(root, ui, *, at_end=False):
    whole(ui.primary_btn, root)
    assert ui.detail_scroll.winfo_ismapped(), "Result scrollbar must be visible"
    assert ui.detail_scroll.winfo_width() >= ui.detail_scroll.winfo_reqwidth(), "Result scrollbar squeezed out"
    assert ui.detail_scroll.winfo_rootx() + ui.detail_scroll.winfo_width() <= ui.result_frame.winfo_rootx() + ui.result_frame.winfo_width()
    if at_end:
        assert ui.details.yview()[0] > 0, "Scrollbar did not move the details"
        assert ui.details.dlineinfo("end-2c") is not None, "Last result line is unreachable"
    else:
        assert ui.details.yview()[1] < 1, "Long detail fixture does not exercise overflow"


def run_checks():
    for removal in (False, True):
        kind = "uninstall" if removal else "install"
        root, app = make(removal)
        ui = app.ui
        try:
            checkpoint(root, kind+"-ready", lambda: assert_ready(root, ui))
            if removal:
                for name in uninstall.PRESERVED_WHEN_NOT_EMPTY:
                    assert name+"/" in ui.preservation_text
            ui.primary_btn.focus_set()
            checkpoint(root, kind+"-keyboard-focus", lambda: whole(ui.primary_btn, root))
            ui.begin(app.install_path.get())
            for i in range(len(app.STEPS)):
                if i:
                    ui.mark_step(i-1)
                ui.activate_step(i)
                ui.update_progress(sum(weight for _, weight in app.STEPS[:i]), app.STEPS[i][0])
                checkpoint(root, f"{kind}-step-{i+1}", lambda: assert_busy(root, ui))
            ui.close()
            assert root.winfo_exists(), "Window close must not abandon active work"
            root.geometry("680x520")
            checkpoint(root, kind+"-compact-progress", lambda: assert_busy(root, ui))
            app._show_error("Windows could not remove a file because another application is using it.\n\n"
                            + ("C:\\A long workspace name\\Project files\\locked-file.bin\n"*12)
                            + "Close the application holding the file and retry.")
            checkpoint(root, kind+"-error-and-retry", lambda: whole(ui.primary_btn, root))
            assert ui.state == "error" and str(ui.details["state"]) == "disabled"
            ui.cancel_btn.invoke()
            checkpoint(root, kind+"-change-folder", lambda: assert_ready(root, ui))
            ui.begin(app.install_path.get())
            assert all("✓" not in str(label["text"]) for label in ui.check_labels)
            assert ui.progress_bar["value"] == 0
            checkpoint(root, kind+"-retry-reset", lambda: assert_busy(root, ui))
            app._show_success(app.install_path.get())
            checkpoint(root, kind+"-complete", lambda: whole(ui.primary_btn, root))
            assert ui.state == "complete"
            assert ui.primary_btn["text"] == "Close"
        finally:
            root.destroy()
        for scale in (96/72, 144/72, 192/72):
            root, app = make(removal, scaling=scale, versionless=True)
            try:
                checkpoint(root, f"{kind}-versionless-{round(scale*72)}dpi", lambda: assert_ready(root, app.ui))
                root.geometry("800x600")
                app.ui.begin("C:\\" + "Long folder name\\"*18)
                checkpoint(root, f"{kind}-long-path-{round(scale*72)}dpi", lambda: assert_busy(root, app.ui))
                detail = "PREVIEW ONLY: long preservation and recovery details.\n\n" + "\n".join(
                    f"Retained item {index}: C:\\Workspace\\Templates\\Unicode Ángela\\document-{index}.md"
                    for index in range(1, 25)) + "\n\nEND OF RECOVERY DETAILS"
                app.ui.finish(success=True, target=app.install_path.get(), detail=detail)
                pump(root)
                app.ui.canvas.yview_moveto(1)
                checkpoint(root, f"{kind}-long-result-{round(scale*72)}dpi", lambda: assert_details(root, app.ui))
                root.tk.call(app.ui.detail_scroll.cget("command"), "moveto", 1)
                checkpoint(root, f"{kind}-result-bottom-{round(scale*72)}dpi", lambda: assert_details(root, app.ui, at_end=True))
            finally:
                root.destroy()
    # Exercise the real constructor's recoverable missing-package screen.
    root = tk.Tk()
    original = install.FancyInstaller._find_zip
    install.FancyInstaller._find_zip = staticmethod(lambda: None)
    try:
        app = install.FancyInstaller(root)
        checkpoint(root, "install-missing-package", lambda: whole(app.ui.primary_btn, root))
        assert app.ui.state == "error"
        app.ui.primary_btn.invoke()
        assert app.ui.state == "error"
    finally:
        install.FancyInstaller._find_zip = staticmethod(original)
        root.destroy()


def report():
    rows = "".join(f'<section><h2>{html.escape(r["name"])}</h2><a href="{r["photo"]}"><img src="{r["photo"]}"></a></section>' for r in RESULTS)
    (OUT / "SUMMARY.html").write_text(
        '<!doctype html><meta charset="utf-8"><title>Tlamatini setup · visual review</title>'
        '<style>body{background:#0e111a;color:#edf2fa;font:16px Segoe UI;margin:40px}h1{color:#79dfce}'
        'section{margin:32px 0}h2{font-size:18px}img{max-width:100%;max-height:650px;border:1px solid #303d50}</style>'
        f'<h1>Tlamatini setup · {len(RESULTS)} visible checkpoints</h1>'
        '<p>Source Tk UI states at 96, 144 and 192 DPI font scales. Actual foreground windows; full desktop photos by Shoter.</p>'
        '<p>UI preview fixtures only. No installation, uninstallation, registry or shell changes. This is not compiled release acceptance.</p>'
        + rows, encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--preview", choices=("install", "uninstall"))
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    visible_console()
    if args.preview:
        root, app = make(args.preview == "uninstall")
        print("SAFE UI PREVIEW: buttons animate presentation only. Close when finished.", flush=True)
        root.mainloop()
    else:
        try:
            run_checks()
            report()
            print(f"PASS: {len(RESULTS)} visible UI checkpoints. {OUT / 'SUMMARY.html'}", flush=True)
        except Exception:
            traceback.print_exc()
            report()
            raise
