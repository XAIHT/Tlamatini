# Tlamatini Author Banner — Angela López Mendoza · @angelahack1
"""Real frozen-app crash campaign, from a verified visible -NoExit console.

Deploys unmodified agent templates through the authenticated product endpoints.
Chrome is explicitly headed. Only recorded test identities may be terminated.
The real Uninstaller is operated manually when desktop automation blocks it.
"""
import argparse
import ctypes
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import time

import psutil

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from markdown_canvas_visible import visible_console
from setup_release_cycles import EVIDENCE, target, photo, windows, foreground, passive_window
from uninstall_processes import owned_processes

DST = target(5)
OUT = EVIDENCE / "crash-agents"
BASE = "http://127.0.0.1:8896/agent"
SESSION = "setup-crash-validation"


def save(name, data):
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / (name + ".json")).write_text(json.dumps(data, indent=2), encoding="utf-8")


def read(name):
    return json.loads((OUT / (name + ".json")).read_text(encoding="utf-8"))


def identity(pid):
    p = psutil.Process(pid)
    return dict(pid=p.pid, created=p.create_time(), executable=p.exe(), parent=p.ppid())


def same_alive(row):
    try:
        p = psutil.Process(row["pid"])
        return p.create_time() == row["created"] and p.is_running()
    except psutil.NoSuchProcess:
        return False


def terminate_recorded(row):
    if same_alive(row):
        p = psutil.Process(row["pid"])
        p.kill()
        p.wait(timeout=10)


def prepare():
    assert (DST / "Tlamatini.exe").is_file(), "Complete the actual installation first"
    assert (EVIDENCE / "case-5-installed.json").is_file(), "Verify installation first"
    OUT.mkdir(parents=True, exist_ok=True)
    if (OUT / "credentials.json").exists():
        raise RuntimeError("Crash fixture already prepared; inspect before repeating")
    for port in (8896, 8897, 8898):
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", port))
    config_path = DST / "config.json"
    data = json.loads(config_path.read_text(encoding="utf-8-sig"))
    data.update(django_port=8896, console_quick_edit=False,
                mcp_system_server_host="127.0.0.1", mcp_system_server_port=8897,
                mcp_system_client_uri="ws://127.0.0.1:8897",
                mcp_files_search_server_host="127.0.0.1", mcp_files_search_server_port=8898,
                mcp_files_search_client_uri="127.0.0.1:8898")
    config_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    credentials = {"username": "setup_crash_validation", "password": secrets.token_urlsafe(30)}
    save("credentials", credentials)
    code = ("import os; from django.contrib.auth import get_user_model; "
            "u,_=get_user_model().objects.get_or_create(username='setup_crash_validation'); "
            "u.set_password(os.environ['TLAMATINI_VALIDATION_PASSWORD']); "
            "u.is_staff=True; u.is_superuser=True; u.save(); "
            "print('ISOLATED TEST ACCOUNT READY')")
    env = {**os.environ, "TLAMATINI_VALIDATION_PASSWORD": credentials["password"]}
    subprocess.run([str(DST / "Tlamatini.exe"), "shell", "-c", code], cwd=DST,
                   env=env, check=True, timeout=180)
    print("PREPARED: installed runtime, isolated local ports and normal-login test account", flush=True)


def serve():
    assert (OUT / "credentials.json").is_file()
    env = {**os.environ, "TLAMATINI_COMMAND_TIMEOUT": "1800", "PYTHONIOENCODING": "utf-8"}
    p = subprocess.Popen([str(DST / "Tlamatini.exe"), "runserver", "--noreload", "127.0.0.1:8896"],
                         cwd=DST, env=env)
    save("server", identity(p.pid))
    print(f"REAL FROZEN SERVER PID {p.pid}; abrupt termination is an intentional test step", flush=True)
    deadline = time.monotonic() + 1800
    while p.poll() is None and time.monotonic() < deadline:
        print(f"LIVE FROZEN SERVER: PID {p.pid}", flush=True)
        time.sleep(10)
    if p.poll() is None:
        terminate_recorded(read("server"))
        raise TimeoutError("Crash campaign exceeded 30 minutes")
    save("server-exit", {"return_code": p.returncode})
    print(f"FROZEN SERVER EXIT: {p.returncode}; agent survival must be independently checked", flush=True)


def payload(label):
    marker = OUT / (label + "-ready.json")
    return ("import json\nimport os\nfrom pathlib import Path\nimport threading\n"
            f"os.chdir({str(OUT)!r})\n"
            f"Path({str(marker)!r}).write_text(json.dumps({{'pid': os.getpid()}}), encoding='utf-8')\n"
            f"print('REAL {label.upper()} PAYLOAD: stalled, awaiting uninstall cleanup', flush=True)\n"
            "threading.Event().wait(1800)\n")


def wait_file(path, seconds=60):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if path.is_file():
            return
        print(f"WAITING FOR REAL AGENT: {path.name}", flush=True)
        time.sleep(5)
    raise TimeoutError(f"Real agent did not reach its blocked workload: {path.name}")


def agents():
    from playwright.sync_api import sync_playwright
    credentials = read("credentials")
    server = read("server")
    assert same_alive(server), "The installed Tlamatini server must actually be running"
    assert os.path.normcase(server["executable"]) == os.path.normcase(str(DST / "Tlamatini.exe"))
    control = None
    worker_records = []
    import win32gui
    previous_windows = set()
    win32gui.EnumWindows(lambda hwnd, _: previous_windows.add(hwnd), None)
    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel="chrome", headless=False, slow_mo=150)
        page = browser.new_page(viewport={"width": 1360, "height": 900})
        page.goto(BASE + "/", wait_until="domcontentloaded", timeout=120000)
        page.bring_to_front()
        title = page.title()
        browser_windows = []
        win32gui.EnumWindows(lambda hwnd, _: browser_windows.append(hwnd) if (
            win32gui.IsWindowVisible(hwnd) and win32gui.GetClassName(hwnd) == "Chrome_WidgetWin_1"
            and hwnd not in previous_windows and title in win32gui.GetWindowText(hwnd)) else None, None)
        if len(browser_windows) != 1:
            raise RuntimeError("Cannot uniquely verify the actual headed test browser")
        foreground(browser_windows[0])
        print("REAL HEADED BROWSER VERIFIED VISIBLE BEFORE LOGIN", flush=True)
        page.locator('#id_username').fill(credentials["username"])
        page.locator('#id_password').fill(credentials["password"])
        page.get_by_role("button", name="Login", exact=True).click()
        page.wait_for_url("**/welcome/", timeout=60000)
        page.goto(BASE + "/agentic_control_panel/", wait_until="domcontentloaded", timeout=60000)
        print("REAL HEADED LOGIN AND AGENTIC CONTROL PANEL LOADED", flush=True)
        photo("case-5-real-app-before-crash")
        token = next(c["value"] for c in page.context.cookies() if c["name"] == "csrftoken")
        headers = {"X-CSRFToken": token, "X-Agent-Session-ID": SESSION, "Referer": BASE + "/agentic_control_panel/"}

        def post(route, body):
            response = page.request.post(BASE + route, data=body, headers=headers, timeout=30000)
            assert response.ok, f"Real endpoint refused {route}: HTTP {response.status}"
            result = response.json()
            assert result.get("success"), f"Real endpoint failed {route}: {result}"
            return result

        child = OUT / "executer-child.py"
        child.write_text(payload("executer"), encoding="utf-8")
        command = subprocess.list2cmdline([str(DST / "python/python.exe"), "-u", str(child)])
        configs = {
            "starter-901": {"target_agents": ["sleeper_901", "pythonxer_901", "executer_901"], "exit_after_start": False},
            "sleeper-901": {"duration_ms": 1800000, "target_agents": []},
            "pythonxer-901": {"script": payload("pythonxer"), "execute_forked_window": True, "target_agents": []},
            "executer-901": {"script": command, "execute_forked_window": True, "non_blocking": False, "target_agents": []},
        }
        for name, config in configs.items():
            post(f"/deploy_agent_template/{name}/", {})
            post(f"/save_agent_config/{name}/", config)
            print(f"REAL PRODUCT DEPLOYED AND CONFIGURED: {name}", flush=True)
        launched = post("/execute_starter_agent/starter-901/", {})
        print(f"REAL STARTER LAUNCHED BY TLAMATINI: PID {launched['pid']}", flush=True)
        for label in ("pythonxer", "executer"):
            wait_file(OUT / (label + "-ready.json"), 90)
        pool = DST / "agents/pools" / SESSION
        for name in ("sleeper_901", "pythonxer_901", "executer_901"):
            pidfile = pool / name / "agent.pid"
            wait_file(pidfile)
            row = identity(int(pidfile.read_text().strip()))
            row["agent"] = name
            worker_records.append(row)
        for label in ("pythonxer", "executer"):
            row = identity(read(label + "-ready")["pid"])
            row["agent"] = label + "_payload_changed_cwd"
            worker_records.append(row)
        # Same executable name, different ownership. A stale PID file points at
        # this process; an uninstaller that trusts PID files must fail this test.
        control_env = {k: v for k, v in os.environ.items() if k != "TLAMATINI_AGENTS_ROOT"}
        control = subprocess.Popen([sys.executable, "-u", "-c",
            "import time; print('UNRELATED PYTHON CONTROL MUST SURVIVE', flush=True); time.sleep(1800)"],
            cwd=OUT, env=control_env)
        sentinel = identity(control.pid)
        stale = pool / "stale_pid_control"
        stale.mkdir()
        (stale / "agent.pid").write_text(str(control.pid), encoding="ascii")
        snapshot = owned_processes(str(DST))
        assert control.pid not in {r["pid"] for r in snapshot}
        save("before-crash", {"server": server, "agents": worker_records, "unrelated_control": sentinel,
                              "owned_snapshot": snapshot})
        # Kill only the proved main application identities, without Ctrl+C,
        # process-tree termination, cleanup endpoints or the product reaper.
        main_rows = [identity(r["pid"]) for r in snapshot
                     if os.path.normcase(r.get("path", "")) == os.path.normcase(str(DST / "Tlamatini.exe"))
                     and "runserver" in psutil.Process(r["pid"]).cmdline()]
        assert main_rows, "No actual frozen application identity was found"
        for row in reversed(main_rows):
            terminate_recorded(row)
        assert not same_alive(server)
        assert all(same_alive(row) for row in worker_records), "Tlamatini's crash did not leave the required agents alive"
        sleeper = next(r for r in worker_records if r["agent"] == "sleeper_901")
        psutil.Process(sleeper["pid"]).suspend()
        for check in range(4):
            time.sleep(5)
            assert all(same_alive(row) for row in worker_records), "An agent exited before the uninstall test"
            assert same_alive(sentinel), "Unrelated control died before the uninstall test"
            print(f"PROVED ORPHANS AFTER ABRUPT APP EXIT: {len(worker_records)} alive, check {check+1}/4", flush=True)
        save("orphaned", {"passed": True, "agents": worker_records, "unrelated_control": sentinel,
                          "suspended_agent": sleeper, "main_app_exits": main_rows})
        photo("case-5-real-orphaned-agents")
        print(f"MANUAL UNINSTALL READY: {DST / 'Uninstaller.exe'}", flush=True)
        print("Click Uninstall and confirm. This observer never clicks or launches the blocked Uninstaller.", flush=True)
        deadline = time.monotonic() + 1200
        while time.monotonic() < deadline:
            survivors = [r for r in worker_records if same_alive(r)]
            assert same_alive(sentinel), "UNINSTALLER KILLED AN UNRELATED PROCESS"
            print("LIVE ORPHANS:", [r["pid"] for r in survivors], "; unrelated control alive", flush=True)
            if not survivors:
                remaining = owned_processes(str(DST))
                assert not remaining, f"Owned descendants or sidecars survived: {remaining}"
                save("worker-cleanup", {"passed": True, "stopped": worker_records, "unrelated_survived": sentinel})
                print("PASS REAL CRASH CLEANUP: every recorded agent/payload stopped; unrelated Python survived", flush=True)
                break
            time.sleep(5)
        else:
            raise TimeoutError("Real orphan cleanup was not observed within 20 minutes")
        # Keep the visible browser open until the actual wizard reaches a result.
        deadline = time.monotonic() + 1200
        while time.monotonic() < deadline:
            assert same_alive(sentinel), "Unrelated control died during file removal"
            found = windows("uninstall", 5)
            if found and any("complete" in title or "needs attention" in title for _, title in found):
                for hwnd, title in found:
                    passive_window(hwnd)
                    photo("case-5-orphan-uninstall-result")
                    print("REAL UNINSTALL RESULT:", title, flush=True)
                    save("result", {"title": title, "unrelated_survived_until_result": same_alive(sentinel),
                                    "owned_survivors": owned_processes(str(DST))})
                break
            time.sleep(5)
        else:
            raise TimeoutError("Uninstaller did not reach a result within 20 minutes")
        terminate_recorded(sentinel)
        page.wait_for_timeout(10000)
        browser.close()


if __name__ == "__main__":
    visible_console()
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("prepare", "serve", "agents"))
    args = parser.parse_args()
    globals()[args.action]()
