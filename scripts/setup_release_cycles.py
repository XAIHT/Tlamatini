# Tlamatini Author Banner — Angela López Mendoza · @angelahack1
"""Visible, compiled setup validation. Native UI input is performed separately.

Run every command from a verified foreground PowerShell -NoExit console. This
script launches the real clients, watches their actual windows and checks disk
and Windows state. It never invokes source wizard methods or clicks for users.
"""
import argparse
import ctypes
import html
import json
import os
import re
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import time
import winreg
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from build_runtime_assets import file_record
from setup_recovery import checked_path
from setup_windows import WindowsSnapshot
from markdown_canvas_visible import visible_console
import drag_divider_look_visible as photographs

OUT = ROOT / "Temp/setup-release-validation"
EVIDENCE = OUT / "evidence"
RELEASE = OUT / "bin/Installer"
CASES = {1: "01-clean", 2: "02 Ángela's Unicode workspace", 3: "03-user-content",
         4: "04-read-only", 5: "05-lock-and-workers"}
KEEP = ("application", "applications", "content_generated", "context_files", "doc_generated", "Templates")
SENTINEL = b"Tlamatini lifecycle validation - preserve this exact content\n"


def target(case):
    return OUT / "cases" / CASES[case] / "Tlamatini"


def record(case, phase, **data):
    path = EVIDENCE / f"case-{case}-{phase}.json"
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    write_report()


def write_report():
    cards, installed, removed = [], 0, 0
    scope_file = EVIDENCE / 'campaign-scope.json'
    scope = json.loads(scope_file.read_text(encoding='utf-8')) if scope_file.is_file() else {}
    comparable = scope.get('registry_context_comparable', True)
    for case, label in CASES.items():
        statuses = []
        for phase, caption, gui in (("installed", "Installation", "install"),
                                    ("uninstalled", "Uninstallation", "uninstall")):
            disk = EVIDENCE / f"case-{case}-{phase}.json"
            window = EVIDENCE / f"case-{case}-{gui}-window.json"
            passed = (comparable and disk.is_file() and window.is_file()
                      and json.loads(disk.read_text(encoding="utf-8")).get("passed")
                      and json.loads(window.read_text(encoding="utf-8")).get("passed"))
            if passed:
                if phase == "installed": installed += 1
                else: removed += 1
            statuses.append(f'<p class="{"pass" if passed else "pending"}">{caption}: '
                            + ('PASS · real GUI + filesystem verified' if passed else 'Awaiting complete verification') + '</p>')
        images = ''.join(f'<a href="{html.escape(p.name)}"><img loading="lazy" src="{html.escape(p.name)}" '
                         f'alt="{html.escape(p.stem)}"><span>{html.escape(p.stem)}</span></a>'
                         for p in sorted(EVIDENCE.glob(f"case-{case}-*.png")))
        provenance = EVIDENCE / f"case-{case}-install-artifact.json"
        if provenance.is_file():
            statuses.append(f'<p><a href="{provenance.name}">Exact executable and package hashes used for this case</a></p>')
        cards.append(f'<section><h2>{html.escape(label)}</h2>{"".join(statuses)}<div class="photos">{images}</div></section>')
    document = '''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<meta http-equiv="refresh" content="15"><title>Tlamatini · Setup validation</title>
<style>body{margin:0;background:#0e111a;color:#edf2fa;font:16px Segoe UI,sans-serif;padding:38px;line-height:1.5}
main{max-width:1400px;margin:auto}header{border-bottom:1px solid #303d50;padding-bottom:22px;margin-bottom:24px}
h1{font-size:38px;margin:6px 0}h2{font-size:22px}.eyebrow,.pass{color:#79dfce}.pending{color:#ffc08c}
section{border:1px solid #303d50;background:#151b28;border-radius:12px;padding:24px;margin:20px 0}
.photos{display:grid;grid-template-columns:repeat(auto-fit,minmax(270px,1fr));gap:16px}a{color:#a6b4c9;text-decoration:none}
img{width:100%;border-radius:7px}span{display:block;font-size:13px;overflow-wrap:anywhere}p{margin:7px 0}
</style><main><header><div class="eyebrow">TLAMATINI / VISIBLE SETUP VALIDATION</div><h1>Five complete lifecycle scenarios.</h1>'''
    document += (f'<p>Verified complete installations: <strong>{installed}/5</strong> · Verified complete uninstallations: '
                 f'<strong>{removed}/5</strong></p><p>Compiled clients and the full new package. '
                 'Counts require both the real completion window and independent disk/Windows checks. '
                 'Focused setup verification; this is not full application release acceptance.</p></header>')
    if not comparable:
        document += '<section><h2>Earlier launch context</h2><p>' + html.escape(scope['reason']) + '</p><p><a href="desktop-campaign/SUMMARY.html">Open the desktop campaign</a></p></section>'
    if (EVIDENCE / 'pre-result-scrollbar-build.json').is_file():
        document += ('<section><h2>Build and visual evidence</h2>'
                     '<p>Cases 1–4 used the clients built before the result-scrollbar repair. '
                     'Case 5 uses the rebuilt clients. Each case links its exact artifact hashes.</p>'
                     '<p><a href="../../../setup-wizard-visible/result-scrollbar/SUMMARY.html">'
                     '52 source UI checkpoints, including long result text at 96, 144 and 192 DPI</a></p>'
                     '<p>These source presentation checks are separate from the real lifecycle counts.</p></section>')
    crash = EVIDENCE / "crash-agents"
    if (crash / "orphaned.json").is_file():
        prepared = json.loads((crash / "orphaned.json").read_text(encoding="utf-8"))
        cleanup = crash / "worker-cleanup.json"
        cleaned = cleanup.is_file() and json.loads(cleanup.read_text(encoding="utf-8")).get("passed", False)
        rows = ''.join('<li>' + html.escape(row['agent']) + ' · PID ' + str(int(row['pid'])) + '</li>'
                       for row in prepared['agents'])
        document += ('<section><h2>Real application crash and orphaned agents</h2>'
                     '<p>The installed Tlamatini server was terminated without Ctrl+C. '
                     'Four subsequent checks proved that these five real agent/workload processes survived.</p>'
                     f'<ul>{rows}</ul><p class="{"pass" if cleaned else "pending"}">'
                     + ('PASS: compiled uninstaller stopped all owned workers; unrelated Python control survived.'
                        if cleaned else 'Waiting for the real uninstaller to stop the surviving workers.')
                     + '</p><p>This process-cleanup result is separate from the complete file/registry audit below.</p></section>')
    document += ''.join(cards) + '</main></html>'
    (EVIDENCE / "SUMMARY.html").write_text(document, encoding="utf-8")


def photo(name):
    photographs.OUT = EVIDENCE
    path, metadata = photographs.shoter(name + ".png")
    write_report()
    print(f"DESKTOP EVIDENCE: {path}", flush=True)
    return str(path)


def windows(operation, case):
    import psutil
    import win32gui
    import win32process
    found = []
    prefix = "Tlamatini — " + ("Installation" if operation == "install" else "Uninstallation")
    def visit(hwnd, _):
        title = win32gui.GetWindowText(hwnd)
        ready = "Tlamatini Installer" if operation == "install" else "Tlamatini Uninstaller"
        if win32gui.IsWindowVisible(hwnd) and (title.startswith(prefix) or title.startswith(ready)):
            # Source previews and regression fixtures must never count as a
            # compiled completion merely because their titles are identical.
            try:
                _, pid = win32process.GetWindowThreadProcessId(hwnd)
                expected = "installer.exe" if operation == "install" else "uninstaller.exe"
                process = psutil.Process(pid)
                if process.name().casefold() != expected:
                    return
                if operation == "uninstall":
                    args = process.cmdline()
                    selected = (args[args.index("--install-dir")+1]
                                if "--install-dir" in args else str(Path(process.exe()).parent))
                    if os.path.normcase(os.path.abspath(selected)) != os.path.normcase(str(target(case))):
                        return
                found.append((hwnd, title))
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
    win32gui.EnumWindows(visit, None)
    return found


def foreground(hwnd):
    import pywintypes
    import win32api
    import win32con
    import win32gui
    import win32process
    win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
    other, _ = win32process.GetWindowThreadProcessId(win32gui.GetForegroundWindow())
    own = win32api.GetCurrentThreadId()
    try:
        if own != other:
            win32process.AttachThreadInput(own, other, True)
        # Do not synthesize Alt here: on an already-focused Tk window that
        # enters the native system-menu loop and pauses its event callbacks.
        win32gui.SetWindowPos(hwnd, win32con.HWND_TOPMOST, 0, 0, 0, 0,
                             win32con.SWP_NOMOVE | win32con.SWP_NOSIZE | win32con.SWP_SHOWWINDOW)
        if win32gui.GetForegroundWindow() != hwnd:
            try:
                win32gui.SetForegroundWindow(hwnd)
            except pywintypes.error:
                # Windows can return zero after a queued activation. The
                # observed foreground check below decides success, not this
                # request's return value.
                pass
    finally:
        if own != other:
            win32process.AttachThreadInput(own, other, False)
    cloaked = ctypes.c_int()
    # Foreground activation is delivered through the desktop input queue.
    # Allow that request to settle before asserting its observed state.
    for _ in range(10):
        if win32gui.GetForegroundWindow() == hwnd:
            break
        time.sleep(.05)
    ctypes.windll.dwmapi.DwmGetWindowAttribute(ctypes.c_void_p(hwnd), 14, ctypes.byref(cloaked), 4)
    if not win32gui.IsWindowVisible(hwnd) or win32gui.IsIconic(hwnd) or cloaked.value or win32gui.GetForegroundWindow() != hwnd:
        raise RuntimeError("Compiled wizard is not actually visible in the foreground")
    return win32gui.GetWindowRect(hwnd)


def passive_window(hwnd):
    """Observe a manually operated Uninstaller without activating or moving it."""
    import win32gui
    if not win32gui.IsWindowVisible(hwnd) or win32gui.IsIconic(hwnd):
        raise RuntimeError("Please leave the manually operated Uninstaller visible")
    return win32gui.GetWindowRect(hwnd)


def clean_baseline():
    baseline = EVIDENCE / "original-windows-state"
    if baseline.exists():
        raise RuntimeError("Baseline already captured; do not overwrite it")
    for path in (r"Software\Microsoft\Windows\CurrentVersion\Uninstall\Tlamatini", r"Software\XAIHT\Tlamatini"):
        owner = WindowsSnapshot._read_value(path, "InstallLocation")
        if owner and Path(owner["value"]).exists():
            raise RuntimeError("An existing personal installation is present; inspect it before resetting registrations")
    baseline.mkdir()
    WindowsSnapshot(baseline).capture()
    clean = EVIDENCE / "clean-windows-state"
    clean.mkdir()
    data = {"trees": {p: {} for p in WindowsSnapshot.TREES},
            "values": [[p, n, None] for p, n in WindowsSnapshot.VALUES], "shortcut": False}
    (clean / "windows.json").write_text(json.dumps(data), encoding="utf-8")
    WindowsSnapshot(clean).restore()
    print("CLEAN BASELINE: product-owned values and shortcut cleared; original snapshot retained.", flush=True)


def prepare(case):
    dst = target(case)
    if dst.exists():
        raise RuntimeError(f"Case already exists; inspect before reusing: {dst}")
    dst.parent.mkdir(parents=True, exist_ok=True)
    if case == 3:
        for name in KEEP:
            path = dst / name / "preserve-me.txt"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(SENTINEL)
        (dst / "config.json").write_text('{"validation_fixture": "preserve"}', encoding="utf-8")
    print(f"PREPARED CASE {case}: native installer parent directory = {dst.parent}", flush=True)


def verify_integration(case):
    import win32com.client
    dst = target(case)
    config = json.loads((dst / "CreateShortcut.json").read_text(encoding="utf-8"))
    assert os.path.normcase(config["InstallDir"]) == os.path.normcase(str(dst))
    shortcut_path = WindowsSnapshot.desktop_shortcut()
    assert shortcut_path.is_file()
    shortcut = win32com.client.Dispatch("WScript.Shell").CreateShortcut(str(shortcut_path))
    assert os.path.normcase(shortcut.WorkingDirectory) == os.path.normcase(str(dst))
    executable = os.path.normcase(str(dst / "Tlamatini.exe"))
    if Path(shortcut.TargetPath).name.casefold() == "conhost.exe":
        assert os.path.normcase(shortcut.Arguments.strip('"')) == executable
    else:
        assert os.path.normcase(shortcut.TargetPath) == executable
    arp = WindowsSnapshot._read_value(r"Software\Microsoft\Windows\CurrentVersion\Uninstall\Tlamatini", "InstallLocation")
    assert arp and os.path.normcase(arp["value"]) == os.path.normcase(str(dst))
    assert WindowsSnapshot._read_value(r"Software\Microsoft\Windows\CurrentVersion\Uninstall\Tlamatini", "QuietUninstallString") is None
    for progid in ("Tlamatini.FlowFile", "Tlamatini.PromptFlowFile"):
        command = WindowsSnapshot._read_value("Software\\Classes\\"+progid+r"\shell\open\command", "")
        assert command and str(dst).casefold() in command["value"].casefold()
    record(case, "integration", passed=True, target=str(dst), shortcut=str(shortcut_path))
    print(f"PASS WINDOWS INTEGRATION {case}: configured destination, executable shortcut and registrations verified.", flush=True)


def verify_install(case):
    dst = target(case)
    document = json.loads((dst / "runtime-assets.json").read_text(encoding="utf-8"))
    count = 0
    for name, expected in document["files"].items():
        path = checked_path(dst, name)
        if name == "CreateShortcut.json" or (case == 3 and name == "config.json"):
            continue  # Setup target and deliberately pre-existing user configuration.
        if file_record(path) != expected:
            raise AssertionError(f"Installed payload differs: {name}")
        count += 1
        if count % 3000 == 0:
            print(f"Verified installed files: {count:,}", flush=True)
    provenance = EVIDENCE / f"case-{case}-install-artifact.json"
    original = EVIDENCE / f"case-{case}-original-build.json"
    if provenance.is_file():
        build = json.loads(provenance.read_text(encoding="utf-8"))["build"]
    else:
        build = json.loads((original if original.is_file() else OUT / "artifacts.json").read_text(encoding="utf-8"))
    assert file_record(dst / "Uninstaller.exe") == build["Uninstaller.exe"]
    verify_integration(case)
    assert not (dst / "Temp/.setup-recovery").exists()
    if case == 3:
        assert json.loads((dst / "config.json").read_text())["validation_fixture"] == "preserve"
        for name in KEEP:
            assert (dst / name / "preserve-me.txt").read_bytes() == SENTINEL
    if case == 4:
        (dst / "README.md").chmod(stat.S_IREAD)
    record(case, "installed", passed=True, verified_files=count, target=str(dst))
    print(f"PASS COMPLETE INSTALLATION {case}: {count:,} payload files, registrations, shortcut and uninstaller verified.", flush=True)


def verify_uninstall(case):
    dst = target(case)
    assert (dst / "agents").is_dir()
    with zipfile.ZipFile(RELEASE / "pkg.zip") as archive:
        manifest = json.loads(archive.read("runtime-assets.json"))["files"]
    retained_payload = {name: value for name, value in manifest.items()
                        if name.split("/")[0] in {"agents", *KEEP}}
    allowed = {"agents"} | {name.split("/")[0] for name in retained_payload}
    if case == 3:
        allowed.update(KEEP)
    remaining = {p.name for p in dst.iterdir()}
    assert remaining == allowed, f"Unexpected remaining entries: {remaining ^ allowed}"
    for name, expected in retained_payload.items():
        if name in ("agents/.tlamatini-preserved-agents.json", "agents/_tlamatini_agents_manifest.json"):
            continue  # Removal updates its agent-preservation inventory.
        assert file_record(checked_path(dst, name)) == expected, f"Preserved payload changed: {name}"
    assert not WindowsSnapshot.desktop_shortcut().exists()
    assert not WindowsSnapshot._tree(r"Software\Microsoft\Windows\CurrentVersion\Uninstall\Tlamatini"), "Installed Apps key remains"
    for progid in ("Tlamatini.FlowFile", "Tlamatini.PromptFlowFile"):
        assert not WindowsSnapshot._tree("Software\\Classes\\"+progid)
    assert not WindowsSnapshot._tree(r"Software\Tlamatini\FlowCapabilities"), "Flow capabilities remain"
    assert WindowsSnapshot._read_value(r"Software\RegisteredApplications", "TlamatiniFlows") is None
    for extension, progid in ((".flw", "Tlamatini.FlowFile"), (".fpmt", "Tlamatini.PromptFlowFile")):
        for prefix in (r"Software\Classes", r"Software\Microsoft\Windows\CurrentVersion\Explorer\FileExts"):
            assert WindowsSnapshot._read_value(prefix+"\\"+extension+r"\OpenWithProgids", progid) is None
    if case == 3:
        for name in KEEP:
            assert (dst / name / "preserve-me.txt").read_bytes() == SENTINEL
    record(case, "uninstalled", passed=True, retained=sorted(remaining),
           retained_payload_files=len(retained_payload))
    print(f"PASS COMPLETE UNINSTALLATION {case}: application removed; preserved content, registry and shortcut verified.", flush=True)


def watch(case, operation, launch=False, expected_error=False, exclude_windows=()):
    show = foreground if operation == "install" else passive_window
    if launch and operation == "uninstall":
        raise RuntimeError("Uninstaller automation is blocked on this machine. Open it manually, then use watch-uninstall.")
    if launch:
        executable = RELEASE / "Installer.exe" if operation == "install" else target(case) / "Uninstaller.exe"
        record(case, operation+"-artifact", executable=str(executable),
               executable_record=file_record(executable),
               build=json.loads((OUT / "artifacts.json").read_text(encoding="utf-8")))
        subprocess.Popen([str(executable)], cwd=executable.parent)
    started = time.monotonic()
    active_started = None
    previous = None
    seen = False
    checkpoints = set()
    if not launch:
        print("WAITING FOR MANUAL WIZARD: the operation timeout starts when progress begins.", flush=True)
    while active_started is None or time.monotonic() - active_started < 1200:
        found = [row for row in windows(operation, case) if row[0] not in exclude_windows]
        if len(found) > 1:
            raise RuntimeError("More than one setup window is open")
        if not found:
            if seen:
                raise RuntimeError("Wizard closed before an observed completion")
            if launch and time.monotonic() - started > 120:
                raise TimeoutError("Compiled wizard did not open within two minutes")
            time.sleep(1)
            continue
        hwnd, title = found[0]
        request = EVIDENCE / "photo.request"
        if request.is_file():
            label = request.read_text(encoding="utf-8").strip()
            request.unlink()
            if not re.fullmatch(r"[a-zA-Z0-9_-]{1,80}", label):
                raise ValueError("Invalid screenshot request label")
            print(f"NATIVE WINDOW RECTANGLE: {show(hwnd)}", flush=True)
            photo(label)
        if not seen:
            print(f"VISIBLE COMPILED WINDOW: {title}; rectangle={show(hwnd)}", flush=True)
            photo(f"case-{case}-{operation}-ready")
            seen = True
        if title != previous:
            print(f"LIVE: {title}", flush=True)
            previous = title
        match = re.search(r"(\d+)%", title)
        if match:
            if active_started is None:
                active_started = time.monotonic()
            bucket = int(match[1]) // 25
            if bucket not in checkpoints:
                show(hwnd)
                photo(f"case-{case}-{operation}-progress-{bucket}")
                checkpoints.add(bucket)
        if "needs attention" in title or "complete" in title:
            show(hwnd)
            shot = photo(f"case-{case}-{operation}-result")
            passed = "complete" in title
            record(case, operation+"-window", passed=passed, title=title, screenshot=shot,
                   elapsed_seconds=round(time.monotonic()-started, 2))
            if expected_error:
                assert not passed, "Locked-file fixture unexpectedly completed"
                print("EXPECTED ERROR OBSERVED; recovery verification remains.", flush=True)
                return
            if not passed:
                raise RuntimeError(f"Compiled {operation} reported an error; inspect its result screen")
            print("REAL GUI COMPLETION OBSERVED; disk verification remains.", flush=True)
            return
        time.sleep(5)
    raise TimeoutError("Wizard exceeded the bounded 20-minute active-operation observation window")


def locked_uninstall():
    import psutil
    dst = target(5)
    locked = dst / "zz-validation-locked.bin"
    locked.write_bytes(SENTINEL)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateFileW.argtypes = [ctypes.c_wchar_p, ctypes.c_ulong, ctypes.c_ulong,
                                  ctypes.c_void_p, ctypes.c_ulong, ctypes.c_ulong, ctypes.c_void_p]
    kernel.CreateFileW.restype = ctypes.c_void_p
    kernel.CloseHandle.argtypes = [ctypes.c_void_p]
    # Allow reads for the real backup, deny deletion until the first attempt ends.
    handle = kernel.CreateFileW(str(locked), 0x80000000, 1, None, 3, 0, None)
    if handle == ctypes.c_void_p(-1).value:
        raise ctypes.WinError(ctypes.get_last_error())
    worker = subprocess.Popen([sys.executable, "-u", "-c",
        "import time; print('Visible lifecycle fixture: owned agent worker ready', flush=True); time.sleep(1200)"],
        cwd=dst / "agents", env={**os.environ, "TLAMATINI_AGENTS_ROOT": str(dst / "agents")})
    identity = psutil.Process(worker.pid).create_time()
    try:
        print(f"Open {dst / 'Uninstaller.exe'} manually, then click Uninstall and confirm.", flush=True)
        watch(5, "uninstall", launch=False, expected_error=True)
        assert worker.poll() is not None, "Owned agent worker survived removal"
        assert locked.read_bytes() == SENTINEL
        verify_install(5)
        record(5, "locked-recovery", passed=True, worker_pid=worker.pid,
               worker_create_time=identity, worker_exit_code=worker.returncode)
        print("PASS: real compiled uninstall stopped its owned worker and restored files and Windows state after a file lock.", flush=True)
    finally:
        kernel.CloseHandle(handle)
        if worker.poll() is None:
            worker.terminate()
            worker.wait(timeout=5)
    print("LOCK RELEASED. Retry through the real uninstaller window.", flush=True)


def main():
    visible_console()
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("baseline", "prepare", "install", "uninstall", "locked-uninstall", "watch-install", "watch-uninstall", "verify-install", "verify-integration", "verify-uninstall", "restore", "photo"))
    parser.add_argument("--case", type=int, choices=range(1, 6), default=1)
    args = parser.parse_args()
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    if args.action == "baseline": clean_baseline()
    elif args.action == "prepare": prepare(args.case)
    elif args.action == "restore":
        WindowsSnapshot(EVIDENCE / "original-windows-state").restore()
        print("ORIGINAL PRODUCT REGISTRATIONS AND DESKTOP SHORTCUT RESTORED", flush=True)
    elif args.action == "verify-install": verify_install(args.case)
    elif args.action == "verify-integration": verify_integration(args.case)
    elif args.action == "verify-uninstall": verify_uninstall(args.case)
    elif args.action == "locked-uninstall": locked_uninstall()
    elif args.action == "photo": photo(f"case-{args.case}-manual")
    else:
        operation = args.action.removeprefix("watch-")
        watch(args.case, operation, launch=not args.action.startswith("watch-"))


if __name__ == "__main__":
    main()
