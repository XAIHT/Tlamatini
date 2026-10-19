# Tlamatini Author Banner — Angela López Mendoza
"""Check the live agent catalog and editor in visible Chrome on an isolated DB.

Run from a verified foreground PowerShell -NoExit console. Confirm the console
by creating Temp/agent-catalog-visible/console.confirmed after inspecting it.
The browser pauses for screenshot verification before any interaction. All
screenshots come from Shoter; no application traffic or state is mocked.
"""
from __future__ import annotations

import json
import secrets
import shutil
import subprocess
import sys
import time
import traceback
import urllib.request

from playwright.sync_api import expect, sync_playwright
import panel_search_title_visible as visible

ROOT = visible.ROOT
OUT = ROOT / "Temp/agent-catalog-visible"
visible.OUT = OUT
visible.RUNTIME = OUT / "runtime"
BASE = visible.BASE
REMOVED = ("Gatewayer", "Gateway Relayer", "Node Manager", "Zavuerer")


def main():
    if any("headless" in arg for arg in sys.argv):
        raise SystemExit("Headless execution is forbidden.")
    if not (OUT / "console.confirmed").exists():
        raise SystemExit("Verify the visible foreground console before running.")
    before = visible.listeners()
    if 8001 in before:
        raise SystemExit("Port 8001 is occupied; refusing to replace another server.")
    original = visible.read_discovery()
    server = None
    results = []
    outcome = 1
    try:
        login = OUT / "login.json"
        if not login.exists():
            login.write_text(json.dumps({"username": "catalog-check", "password": secrets.token_urlsafe(24)}), encoding="utf-8")
        env, credentials = visible.prepare_runtime()
        for name in ("agents_descriptions.md", "README.md", "BookOfTlamatini.md"):
            shutil.copy2(ROOT / name, visible.RUNTIME / name)
        subprocess.run([sys.executable, "-u", "Tlamatini/manage.py", "collectstatic", "--noinput"],
                       cwd=visible.RUNTIME, env=env, check=True)
        server = visible.start_server(env)
        deadline = time.monotonic() + 180
        while time.monotonic() < deadline:
            try:
                with urllib.request.urlopen(BASE, timeout=2) as response:
                    if response.status == 200:
                        break
            except (OSError, TimeoutError):
                time.sleep(1)
        else:
            raise TimeoutError("The isolated server did not become ready.")
        visible.restore_discovery(original)
        catalog = json.loads((ROOT / "Tlamatini/agent/agents/flowcreator/flow_catalog.json").read_text(encoding="utf-8"))
        with sync_playwright() as playwright:
            context = playwright.chromium.launch_persistent_context(
                str(OUT / ("chrome-" + str(time.time_ns()))), channel="chrome",
                headless=False, chromium_sandbox=True, no_viewport=True,
                slow_mo=200, accept_downloads=True, args=["--start-maximized"])
            page = context.pages[0]
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.goto(BASE)
            page.bring_to_front()
            visible.visibility_gate("browser", page)
            page.goto(BASE + "/agent/agentic_control_panel/")
            if page.locator("#id_username").is_visible():
                page.locator("#id_username").fill(credentials["username"])
                page.locator("#id_password").fill(credentials["password"])
                page.locator("button[type=submit]").click()
                page.goto(BASE + "/agent/agentic_control_panel/")
            credentials.clear()
            expect(page.locator("#agents-list")).to_have_attribute("aria-busy", "false", timeout=60000)

            def checkpoint(name):
                page.bring_to_front()
                page.wait_for_timeout(900)
                visible.photograph(name)
                results.append({"name": name, "screenshot": name + ".png"})
                (OUT / "results.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
                print("PASS:", name, flush=True)

            def absent(text):
                folded = "".join(ch for ch in text.lower() if ch.isalnum())
                for name in REMOVED:
                    assert "".join(ch for ch in name.lower() if ch.isalnum()) not in folded, name

            expect(page.locator("#agents-list .agent-tool-item")).to_have_count(len(catalog["agents"]))
            absent(page.locator("#agents-list").inner_text())
            checkpoint("01-complete-agent-sidebar")
            search = page.locator("#acp-agent-search")
            for index, name in enumerate(REMOVED, 2):
                search.fill(name)
                expect(page.locator("#agents-list .agent-tool-item:visible")).to_have_count(0)
                checkpoint(f"{index:02d}-removed-search")
            for name in ("Whatsapper", "Telegrammer", "MCP Doctor", "NetSpeed-Calculator"):
                search.fill(name)
                expect(page.locator("#agents-list .agent-tool-item:visible")).to_have_count(1)
            search.fill("")
            page.locator("#acp-example").click()
            expect(page.locator(".canvas-item")).to_have_count(3)
            expect(page.locator(".connection-group")).to_have_count(2)
            checkpoint("06-connected-example")
            page.locator("#sleeper-1").click()
            page.locator("#acp-configure").click()
            page.locator('#canvas-item-list [data-key="duration_ms"]').fill("2000")
            page.get_by_role("dialog", name="Properties: sleeper-1", exact=True).get_by_role("button", name="Save", exact=True).click()
            expect(page.locator("#deployment-result-dialog")).to_be_visible()
            page.keyboard.press("Escape")
            page.locator("#acp-duplicate").click()
            expect(page.locator(".canvas-item")).to_have_count(4)
            page.locator("#acp-undo").click()
            expect(page.locator(".canvas-item")).to_have_count(3)
            page.locator("#acp-redo").click()
            expect(page.locator(".canvas-item")).to_have_count(4)
            checkpoint("07-configure-duplicate-undo-redo")
            page.locator("#sleeper-2").click()
            page.locator("#acp-delete").click()
            expect(page.locator(".canvas-item")).to_have_count(3)
            page.locator("#acp-undo").click()
            expect(page.locator(".canvas-item")).to_have_count(4)
            page.locator("#acp-redo").click()
            expect(page.locator(".canvas-item")).to_have_count(3)
            checkpoint("08-delete-undo-redo")
            page.get_by_role("button", name="File", exact=True).click()
            page.once("dialog", lambda dialog: dialog.accept("catalog-check.flw"))
            with page.expect_download() as download:
                page.locator("#save-as-button").click()
            saved = OUT / "catalog-check.flw"
            download.value.save_as(saved)
            graph = json.loads(saved.read_text(encoding="utf-8"))
            assert len(graph["nodes"]) == 3 and len(graph["connections"]) == 2
            page.get_by_role("button", name="File", exact=True).click()
            page.locator("#file-close-button").click()
            expect(page.locator(".canvas-item")).to_have_count(0)
            page.get_by_role("button", name="File", exact=True).click()
            with page.expect_file_chooser() as chooser:
                page.locator("#file-open-button").click()
            chooser.value.set_files(str(saved))
            expect(page.locator(".canvas-item")).to_have_count(3)
            expect(page.locator(".connection-group")).to_have_count(2)
            checkpoint("09-saved-reopened-connections")
            page.goto(BASE + "/agent/agent/")
            expect(page.locator("#chat-message-input")).to_be_visible(timeout=60000)
            page.locator("#config-menu-button").click()
            page.locator("#enable-agents").click()
            expect(page.locator("#agents-dialog-message")).to_be_visible()
            expect(page.locator('#agents-list input[type="checkbox"]')).to_have_count(len(catalog["agents"]))
            absent(page.locator("#agents-list").inner_text())
            checkpoint("10-configure-agents")
            page.keyboard.press("Escape")
            page.locator("#config-menu-button").click()
            page.locator("#enable-mcps").click()
            expect(page.locator("#tool-mcps-list")).to_be_visible()
            absent(page.locator("#tool-mcps-list").inner_text())
            checkpoint("11-configure-tools")
            page.keyboard.press("Escape")
            page.locator("#config-menu-button").click()
            page.locator("#access-keys-wizard").click()
            expect(page.locator("#access-keys-wizard-nav button").first).to_be_visible()
            assert "zavu" not in page.locator("#access-keys-wizard-nav").inner_text().lower()
            checkpoint("12-access-key-groups")
            page.keyboard.press("Escape")
            page.locator("#prompts-catalog").click()
            expect(page.locator(".prompt-card").first).to_be_visible()
            absent(page.locator("#tools-body").inner_text())
            assert page.locator('.prompt-card[data-full-content*="chat_agent_whatsapper"]').count() > 0
            checkpoint("13-prompt-catalog")
            page.keyboard.press("Escape")
            assert not errors, errors
            checkpoint("14-chat-without-script-errors")
            print("ALL CATALOG VISUAL CHECKS PASSED.", flush=True)
            page.wait_for_timeout(10000)
            context.close()
        outcome = 0
    except Exception:
        traceback.print_exc()
        visible.photograph("failure")
    finally:
        visible.stop_server(server)
        visible.restore_discovery(original)
        after = visible.listeners()
        if after.get(8000) != before.get(8000):
            outcome = 1
        (OUT / "summary.json").write_text(json.dumps({"exit_code": outcome, "checks": results,
            "before_ports": before, "after_ports": after, "mode": "isolated source; visible Chrome",
            "mocked_transports": False}, indent=2), encoding="utf-8")
        print("CATALOG VISUAL EXIT CODE:", outcome, flush=True)
    return outcome


if __name__ == "__main__":
    raise SystemExit(main())
