# Tlamatini Author Banner — Angela López Mendoza
"""Visible real-browser flow-file lifecycle checks; launch via PowerShell -NoExit.

Uses only a separate source installation, normal login, actual server endpoints,
file pickers/downloads and Windows-native registry tests. Headless is forbidden.
Shoter captures the entire desktop. All task-owned processes stop in finally.
"""

from __future__ import annotations
import copy
import ctypes
import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import sys
import threading
import time
import traceback

import psutil
from playwright.sync_api import expect, sync_playwright
import panel_search_title_visible as visible
from prompt_flow_connections_visible import require_browser_foreground

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "Temp/flow-files-visible"
visible.OUT = OUT
visible.RUNTIME = ROOT / "Temp/prompt-commentary-visible/runtime"
BASE = "http://localhost:8001"


def console_foreground():
    user = ctypes.windll.user32
    kernel = ctypes.windll.kernel32
    kernel.GetConsoleWindow.restype = ctypes.c_void_p
    user.GetForegroundWindow.restype = ctypes.c_void_p
    user.IsWindowVisible.argtypes = [ctypes.c_void_p]
    user.IsIconic.argtypes = [ctypes.c_void_p]
    user.SetForegroundWindow.argtypes = [ctypes.c_void_p]
    hwnd = kernel.GetConsoleWindow()
    # Transfer focus only to this harness's known console, then verify it.
    # Windows may deny a plain SetForegroundWindow after Chrome receives input.
    user.keybd_event(0x12, 0, 0, 0)
    try:
        user.SetForegroundWindow(hwnd)
    finally:
        user.keybd_event(0x12, 0, 2, 0)
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        if (
            hwnd
            and user.IsWindowVisible(hwnd)
            and not user.IsIconic(hwnd)
            and user.GetForegroundWindow() == hwnd
        ):
            return
        time.sleep(0.2)
    raise RuntimeError("Execution requires this visible foreground console.")


def start_file_server(env, path):
    console_foreground()
    server = subprocess.Popen(
        [sys.executable, "-u", "Tlamatini/manage.py", str(path)],
        cwd=visible.RUNTIME,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    (OUT / "owned-server.json").write_text(
        json.dumps(
            {"pid": server.pid, "created": psutil.Process(server.pid).create_time()}
        ),
        encoding="utf-8",
    )

    def forward():
        with (OUT / "server.log").open("w", encoding="utf-8") as logfile:
            for line in server.stdout:
                logfile.write(line)
                logfile.flush()
                print("[8001] " + line, end="", flush=True)

    threading.Thread(target=forward, daemon=True).start()
    return server


def main():
    if any("headless" in arg for arg in sys.argv[1:]):
        raise SystemExit("Headless execution is forbidden.")
    console_foreground()
    OUT.mkdir(parents=True, exist_ok=True)
    visible.photograph("00-visible-console")
    before = visible.listeners()
    if any(port in before for port in (8001, 8766, 50052)):
        raise RuntimeError(
            "Isolated test ports are occupied; refusing to stop another instance."
        )
    original = visible.read_discovery()
    credentials = {"username": "user", "password": secrets.token_urlsafe(32)}
    (OUT / "login.json").write_text(json.dumps(credentials), encoding="utf-8")
    server = None
    profile = None
    results = []
    outcome = 1
    try:
        sys.argv.append("--resume")
        env, credentials = visible.prepare_runtime()
        assets = (
            "manage.py",
            "agent/flow_file_open.py",
            "agent/flow_file_views.py",
            "agent/views.py",
            "agent/urls.py",
            "agent/services/__init__.py",
            "agent/services/prompt_flow_panel.py",
            "agent/test_flow_file_open.py",
            "agent/test_flow_file_views.py",
            "agent/templates/agent/login.html",
            "agent/templates/agent/agentic_control_panel.html",
            "agent/templates/agent/prompt_flow_panel.html",
            "tlamatini/settings.py",
            "agent/static/agent/js/agent_page_canvas.js",
            "agent/static/agent/js/acp-file-io.js",
            "agent/static/agent/js/prompt-flow-panel.js",
            "agent/static/agent/js/prompt-flow-panel-model.js",
        )
        for asset in assets:
            shutil.copy2(
                ROOT / "Tlamatini" / asset, visible.RUNTIME / "Tlamatini" / asset
            )
        for name in ("README.md", "agents_descriptions.md"):
            shutil.copy2(ROOT / name, visible.RUNTIME / name)
        destination = visible.RUNTIME / "docs/examples/prompting-kickoff.fpmt"
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / "docs/examples/prompting-kickoff.fpmt", destination)
        manage = [sys.executable, "-u", "Tlamatini/manage.py"]
        subprocess.run(
            manage
            + [
                "shell",
                "-c",
                "import os; from django.contrib.auth import get_user_model; "
                'u=get_user_model().objects.get(username="user"); '
                'u.set_password(os.environ["FLOW_TEST_PASSWORD"]); u.save(update_fields=["password"])',
            ],
            cwd=visible.RUNTIME,
            env={**env, "FLOW_TEST_PASSWORD": credentials["password"]},
            check=True,
        )
        if "--skip-unit" not in sys.argv:
            subprocess.run(
                manage
                + [
                    "test",
                    "agent.test_flow_file_open",
                    "agent.test_flow_file_views",
                    "agent.test_prompt_flow_panel",
                    "--noinput",
                ],
                cwd=visible.RUNTIME,
                env=env,
                check=True,
            )
        subprocess.run(
            manage + ["collectstatic", "--noinput"],
            cwd=visible.RUNTIME,
            env=env,
            check=True,
        )
        sample = json.loads(destination.read_text(encoding="utf-8"))
        note = sample["nodes"][-1]
        sample.update(name="Windows opening · three review notes", start="input")
        sample["nodes"] = [
            {
                "id": "input",
                "type": "user_input",
                "label": "Ask only when Play is pressed",
                "x": 60,
                "y": 50,
                "config": {"text": "This must never run merely by opening the file."},
            }
        ]
        sample["edges"] = []
        for n, color in enumerate(("#fef3c7", "#dbeafe", "#dcfce7")):
            item = copy.deepcopy(note)
            item.update(id=f"review-{n}", x=60 + 660 * n, y=250)
            item["config"]["color"] = color
            item["config"]["height"] = 370
            sample["nodes"].append(item)
        fpmt = OUT / "Review notes with spaces ñ.FPMT"
        fpmt.write_text(json.dumps(sample, ensure_ascii=False), encoding="utf-8")
        flw = OUT / "Agent flow with spaces ñ.FLW"
        flw.write_text(
            json.dumps(
                {
                    "schemaVersion": 2,
                    "nodes": [
                        {
                            "id": "sleeper-3",
                            "text": "Sleeper",
                            "left": "150px",
                            "top": "120px",
                            "configData": {
                                "sleep_duration": 2,
                                "target_agents": ["sleeper_7"],
                            },
                        },
                        {
                            "id": "sleeper-7",
                            "text": "Sleeper",
                            "left": "550px",
                            "top": "120px",
                            "configData": {
                                "sleep_duration": 3,
                                "source_agents": ["sleeper_3"],
                                "target_agents": [],
                            },
                        },
                    ],
                    "connections": [
                        {
                            "sourceIndex": 0,
                            "targetIndex": 1,
                            "inputSlot": 0,
                            "outputSlot": 0,
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        invalid = OUT / "Broken.flw"
        invalid.write_text('{"wrong":"format"}', encoding="utf-8")
        text = OUT / "Keep this chat document.txt"
        text.write_text(
            "This text stays in the chat canvas while a flow opens in its own editor.",
            encoding="utf-8",
        )
        profile = OUT / ("chrome-profile-" + str(time.time_ns()))
        preferences = profile / "Default/Preferences"
        preferences.parent.mkdir(parents=True, exist_ok=True)
        preferences.write_text(
            json.dumps(
                {
                    "credentials_enable_service": False,
                    "profile": {"password_manager_enabled": False},
                }
            ),
            encoding="utf-8",
        )
        with sync_playwright() as playwright:
            context = playwright.chromium.launch_persistent_context(
                str(profile),
                channel="chrome",
                headless=False,
                chromium_sandbox=True,
                no_viewport=True,
                slow_mo=120,
                accept_downloads=True,
                args=["--start-maximized"],
            )
            errors = []

            def attach(page):
                page.on("pageerror", lambda error: errors.append(str(error)))
                page.on(
                    "dialog",
                    lambda dialog: dialog.accept()
                    if dialog.type == "beforeunload"
                    else None,
                )

            context.on("page", attach)
            blank = context.pages[0]
            blank.goto("about:blank")
            blank.bring_to_front()
            require_browser_foreground(blank)
            chrome = (
                Path(os.environ.get("PROGRAMFILES", "C:/Program Files"))
                / "Google/Chrome/Application/chrome.exe"
            )
            # The real OS opener targets this visible isolated Chrome profile.
            env["BROWSER"] = (
                f'"{chrome.as_posix()}" --user-data-dir="{profile.as_posix()}" %s'
            )
            with context.expect_page(timeout=180000) as opened:
                server = start_file_server(env, fpmt)
            page = opened.value
            page.wait_for_load_state()
            page.bring_to_front()
            require_browser_foreground(page)
            expect(page.locator("#id_username")).to_be_visible()
            visible.photograph("01-cold-open-login-destination")
            page.locator("#id_username").fill(credentials["username"])
            page.locator("#id_password").fill(credentials["password"])
            page.locator("button[type=submit], input[type=submit]").first.click()
            expect(page.locator("#filename")).to_have_text(fpmt.name)
            expect(page.locator(".pmt-node")).to_have_count(4)
            expect(page.locator("#pmt-run-state")).to_have_text("Idle")
            page.locator("[data-action=fit]").click()
            page.evaluate("document.fonts.ready")
            visible.restore_discovery(original)

            def checkpoint(name, target=None):
                target = target or page
                target.bring_to_front()
                require_browser_foreground(target)
                target.wait_for_timeout(1000)
                visible.photograph(name)
                results.append(name)
                (OUT / "checks.json").write_text(
                    json.dumps(results, indent=2), encoding="utf-8"
                )
                print("PASS:", name, flush=True)

            def confirm_replace(target):
                button = target.locator(".tlmpop-overlay button").filter(
                    has_text="Continue"
                )
                if button.is_visible():
                    button.click()

            def geometry(target):
                return target.locator(".pmt-node").evaluate_all("""items => items.map(node => ({
                    id: node.dataset.id, x: node.style.left, y: node.style.top,
                    width: node.style.width, height: node.style.height,
                    text: node.innerText,
                    spans: Array.from(node.querySelectorAll('.pmt-comment-text span')).map(span => {
                        const c=getComputedStyle(span); return [span.textContent,c.fontFamily,c.fontSize,c.fontWeight,c.fontStyle,c.color,c.textDecorationLine];
                    })
                }))""")

            checkpoint("02-cold-file-open-three-rich-notes-idle")
            original_geometry = geometry(page)
            page.get_by_role("button", name="File", exact=True).click()
            page.locator("[data-action=save]").click()
            page.locator("#pmt-field-filename").fill("Round trip review.fpmt")
            with page.expect_download() as download:
                page.get_by_role("button", name="Download .fpmt", exact=True).click()
            saved = OUT / "Round trip review.fpmt"
            download.value.save_as(saved)
            page.get_by_role("button", name="File", exact=True).click()
            with page.expect_file_chooser() as chooser:
                page.locator("[data-action=open]").click()
            chooser.value.set_files(str(saved))
            expect(page.locator("#filename")).to_have_text(saved.name)
            page.wait_for_timeout(600)
            assert geometry(page) == original_geometry, (
                "Saved and reopened note rendering changed."
            )
            checkpoint("03-rich-notes-save-open-identical")
            # Existing-instance invocation exits instead of starting another server.
            console_foreground()
            with context.expect_page(timeout=60000) as incoming:
                subprocess.run(
                    manage + [str(flw)],
                    cwd=visible.RUNTIME,
                    env=env,
                    check=True,
                    timeout=40,
                )
            acp = incoming.value
            acp.bring_to_front()
            require_browser_foreground(acp)
            expect(acp.locator("#filename")).to_contain_text(flw.name, timeout=60000)
            expect(acp.locator(".canvas-item")).to_have_count(2)
            assert server.poll() is None
            assert visible.listeners().get(8001) == server.pid
            checkpoint("04-warm-agent-flow-opens-without-second-server", acp)
            expect(acp.locator("#sleeper-3")).to_be_visible()
            expect(acp.locator("#sleeper-7")).to_be_visible()
            acp.get_by_role("button", name="File", exact=True).click()
            acp.once("dialog", lambda dialog: dialog.accept("Agent round trip.flw"))
            with acp.expect_download() as download:
                acp.locator("#save-as-button").click()
            agent_saved = OUT / "Agent round trip.flw"
            download.value.save_as(agent_saved)
            agent_data = json.loads(agent_saved.read_text(encoding="utf-8"))
            assert [node["id"] for node in agent_data["nodes"]] == [
                "sleeper-3",
                "sleeper-7",
            ]
            assert agent_data["nodes"][0]["configData"]["target_agents"] == [
                "sleeper_7"
            ]
            assert len(agent_data["connections"]) == 1
            checkpoint("04b-agent-ids-and-references-survive-save", acp)
            # Invalid file must not clear or rename the current agent diagram.
            acp.get_by_role("button", name="File", exact=True).click()
            with acp.expect_file_chooser() as chooser:
                acp.locator("#file-open-button").click()
            chooser.value.set_files(str(invalid))
            expect(
                acp.get_by_role("dialog").filter(has_text="Could not open diagram")
            ).to_be_visible()
            expect(acp.locator(".canvas-item")).to_have_count(2)
            expect(acp.locator("#filename")).to_contain_text(agent_saved.name)
            checkpoint("05-invalid-agent-file-keeps-current-diagram", acp)
            acp.get_by_role("dialog").get_by_role(
                "button", name="OK", exact=True
            ).click()
            # Main-chat Open leaves the existing document untouched for both types.
            chat = context.new_page()
            chat.goto(BASE + "/agent/agent/")
            chat.bring_to_front()
            require_browser_foreground(chat)
            with chat.expect_file_chooser() as chooser:
                chat.locator("#open-button").click()
            chooser.value.set_files(str(text))
            expect(chat.locator("#filename")).to_contain_text(text.name)
            for number, file in enumerate((fpmt, flw), start=6):
                chat.bring_to_front()
                require_browser_foreground(chat)
                with chat.expect_file_chooser() as chooser:
                    chat.locator("#open-button").click()
                with context.expect_page() as incoming:
                    chooser.value.set_files(str(file))
                opened_page = incoming.value
                opened_page.wait_for_load_state()
                opened_page.bring_to_front()
                require_browser_foreground(opened_page)
                if file == fpmt:
                    opened_page.wait_for_timeout(1000)
                    confirm_replace(opened_page)
                    expect(opened_page.locator(".pmt-node")).to_have_count(4)
                    expect(opened_page.locator("#pmt-run-state")).to_have_text("Idle")
                    opened_page.locator("[data-action=fit]").click()
                else:
                    expect(opened_page.locator(".canvas-item")).to_have_count(
                        2, timeout=60000
                    )
                expect(opened_page.locator("#filename")).to_contain_text(file.name)
                expect(chat.locator("#filename")).to_contain_text(text.name)
                checkpoint(
                    f"0{number}-chat-opens-{file.suffix[1:].lower()}-in-correct-editor",
                    opened_page,
                )
            assert not errors, errors
            checkpoint("08-chat-document-preserved", chat)
            print(
                "ALL FLOW-FILE VISUAL CHECKS PASSED. Holding visible for inspection.",
                flush=True,
            )
            chat.wait_for_timeout(12000)
            context.close()
        outcome = 0
    except Exception:
        traceback.print_exc()
        try:
            visible.photograph("failure")
        except Exception:
            traceback.print_exc()
    finally:
        # Chromium is task-owned only when its unique profile path matches.
        if profile is not None:
            for process in psutil.process_iter(["pid", "name", "cmdline"]):
                try:
                    args = process.info["cmdline"] or []
                    if any(
                        arg.replace("\\", "/").lower()
                        == ("--user-data-dir=" + profile.as_posix()).lower()
                        for arg in args
                    ):
                        children = process.children(recursive=True)
                        for child in reversed(children):
                            try:
                                child.terminate()
                            except psutil.NoSuchProcess:
                                pass
                        process.terminate()
                        _, alive = psutil.wait_procs(children + [process], timeout=5)
                        for child in alive:
                            child.kill()
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
        visible.stop_server(server)
        visible.restore_discovery(original)
        after = visible.listeners()
        if before.get(8000) != after.get(8000):
            outcome = 1
        summary = {
            "exit_code": outcome,
            "checks": results,
            "before_ports": before,
            "after_ports": after,
        }
        (OUT / "summary.json").write_text(
            json.dumps(summary, indent=2), encoding="utf-8"
        )
        print("FLOW FILE VISUAL EXIT:", outcome, flush=True)
    return outcome


if __name__ == "__main__":
    raise SystemExit(main())
