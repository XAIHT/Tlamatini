# Tlamatini Author Banner — Angela López Mendoza · @angelahack1
"""Visible acceptance checks against actual frozen or isolated source Tlamatini.

Launch in a verified foreground PowerShell -NoExit console. The selected real
entry point serves every response; authentication and edits use the normal UI.
"""

from __future__ import annotations

import argparse
import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
import traceback

import psutil
from playwright.sync_api import expect, sync_playwright
import panel_search_title_visible as visible
from flow_files_visible import console_foreground
from prompt_flow_connections_visible import require_browser_foreground

ROOT = Path(__file__).resolve().parents[1]


def fixtures(out, install):
    sample = json.loads(
        (install / "docs/examples/prompting-kickoff.fpmt").read_text(encoding="utf-8")
    )
    note = sample["nodes"][-1]
    sample.update(name="Installed release review", start="input")
    sample["nodes"] = [
        dict(
            id="input",
            type="user_input",
            label="User Input",
            x=60,
            y=50,
            config={"text": "Reply to verify the installed User Input operation."},
        )
    ]
    sample["edges"] = []
    for n, color in enumerate(("#fef3c7", "#dbeafe", "#dcfce7")):
        item = copy.deepcopy(note)
        item.update(id=f"review-{n}", x=60 + 660 * n, y=250)
        item["config"].update(color=color, height=370)
        sample["nodes"].append(item)
    fpmt = out / "Installed review notes ñ.FPMT"
    fpmt.write_text(json.dumps(sample, ensure_ascii=False), encoding="utf-8")
    flw = out / "Installed agents ñ.FLW"
    flw.write_text(
        json.dumps(
            dict(
                schemaVersion=2,
                nodes=[
                    dict(
                        id="sleeper-3",
                        text="Sleeper",
                        left="150px",
                        top="120px",
                        configData=dict(sleep_duration=2, target_agents=["sleeper_7"]),
                    ),
                    dict(
                        id="sleeper-7",
                        text="Sleeper",
                        left="550px",
                        top="120px",
                        configData=dict(
                            sleep_duration=3,
                            source_agents=["sleeper_3"],
                            target_agents=[],
                        ),
                    ),
                ],
                connections=[
                    dict(sourceIndex=0, targetIndex=1, inputSlot=0, outputSlot=0)
                ],
            )
        ),
        encoding="utf-8",
    )
    return fpmt, flw


def geometry(page):
    return page.locator(
        ".pmt-node"
    ).evaluate_all("""nodes => nodes.map(n => ({
      id:n.dataset.id,x:n.style.left,y:n.style.top,width:n.style.width,height:n.style.height,text:n.innerText,
      spans:Array.from(n.querySelectorAll('.pmt-comment-text span')).map(s=>{
        const c=getComputedStyle(s);return [s.textContent,c.fontFamily,c.fontSize,c.fontWeight,c.fontStyle,c.color,c.textDecorationLine];})}))""")


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--install-dir", type=Path, required=True)
    parser.add_argument("--evidence-dir", type=Path, required=True)
    parser.add_argument("--source", action="store_true", help="Run the isolated source installation")
    parser.add_argument("--extended", action="store_true", help="Also exercise configuration, catalog and real chat")
    parser.add_argument("--agent-catalog", action="store_true", help="Inspect and Save/Open all 89 agent types")
    parser.add_argument("--agent-filter", help="Focus the catalog regression on one exact agent name")
    parser.add_argument("--commentary", action="store_true", help="Exercise all rich-commentary editing and round trips")
    parser.add_argument("--acp-editor", action="store_true", help="Exercise ACP editing, connections, zoom and undo")
    parser.add_argument("--output-resize", action="store_true", help="Exercise the complete Run output divider and scrolling contract")
    parser.add_argument("--acp-runtime", action="store_true", help="Start, pause, resume and stop real local agents")
    parser.add_argument("--authentication", action="store_true", help="Check wrong login, nonstaff permissions, logout and user CRUD")
    parser.add_argument("--prompt-runtime", action="store_true", help="Exercise real prompt/scheduled/decision/flush/cancel runtime")
    parser.add_argument("--shell-files", action="store_true", help="Open both installed file associations with Windows ShellExecute")
    parser.add_argument("--mcp-fixture", type=Path, help="Read a preconfigured bounded fixture through actual source/frozen MCP clients")
    args = parser.parse_args()
    install, out = args.install_dir.resolve(), args.evidence_dir.resolve()
    out.mkdir(parents=True, exist_ok=True)
    visible.OUT = out
    console_foreground()
    mode = "source" if args.source else "frozen"
    executable = install / ("Tlamatini/manage.py" if args.source else "Tlamatini.exe")
    assert executable.is_file(), "Application entry point missing"
    command = [sys.executable, "-u", str(executable)] if args.source else [str(executable)]
    config_path = install / ("Tlamatini/agent/config.json" if args.source else "config.json")
    settings = json.loads(config_path.read_text(encoding="utf-8-sig"))
    port = int(settings.get("django_port", 8000))
    service_ports = {port, int(settings.get('mcp_system_server_port', 8765)),
                     int(settings.get('mcp_files_search_server_port', 50051))}
    base = f"http://localhost:{port}"
    assert not any(
        c.status == psutil.CONN_LISTEN and c.laddr.port in service_ports
        for c in psutil.net_connections(kind="tcp")
    ), "A configured application or MCP service port is already in use"
    fpmt, flw = fixtures(out, install)
    profile = out / ("chrome-profile-" + str(time.time_ns()))
    preferences = profile / "Default/Preferences"
    preferences.parent.mkdir(parents=True)
    preferences.write_text(
        json.dumps(
            {
                "credentials_enable_service": False,
                "profile": {"password_manager_enabled": False},
            }
        ),
        encoding="utf-8",
    )
    results, errors, resource_failures = [], [], []
    server = context = pw = None
    outcome = 1

    def checkpoint(case, page, details=None):
        case = case.replace("frozen", mode)
        page.bring_to_front()
        require_browser_foreground(page)
        page.wait_for_timeout(600)
        visible.photograph(case)
        # Shoter's child process may return desktop focus to the console.
        # Re-establish the actual browser surface before the next real input.
        page.bring_to_front()
        require_browser_foreground(page)
        results.append(dict(case=case, status="PASS", mode=mode, details=details))
        (out / "checks.json").write_text(
            json.dumps(results, indent=2), encoding="utf-8"
        )
        print("PASS: " + case, flush=True)

    try:
        pw = sync_playwright().start()
        context = pw.chromium.launch_persistent_context(
            str(profile),
            channel="chrome",
            headless=False,
            no_viewport=True,
            accept_downloads=True,
            slow_mo=100,
            args=["--start-maximized"],
        )
        context.set_default_timeout(30000)
        context.on('response', lambda response: resource_failures.append(
            {'url': response.url, 'status': response.status}
        ) if '/static/' in response.url and response.status >= 400 else None)
        context.on('requestfailed', lambda request: resource_failures.append(
            {'url': request.url, 'failure': request.failure}
        ) if '/static/' in request.url and request.failure != 'net::ERR_ABORTED' else None)
        context.on(
            "page", lambda p: p.on("pageerror", lambda e: errors.append(str(e)))
        )
        page = context.pages[0]
        page.bring_to_front()
        require_browser_foreground(page)
        chrome = (
            Path(os.environ.get("PROGRAMFILES", "C:/Program Files"))
            / "Google/Chrome/Application/chrome.exe"
        )
        env = {
            **os.environ,
            "PYTHONIOENCODING": "utf-8",
            "BROWSER": f'"{chrome.as_posix()}" --user-data-dir="{profile.as_posix()}" %s',
        }
        env.pop("CONFIG_PATH", None)
        if args.source:
            env["CONFIG_PATH"] = str(config_path)
        console_foreground()
        with context.expect_page(timeout=180000) as opened:
            server = subprocess.Popen(
                command + [str(fpmt)],
                cwd=install,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            (out / "owned-server.json").write_text(
                json.dumps(
                    {
                        "pid": server.pid,
                        "created": psutil.Process(server.pid).create_time(),
                    }
                ),
                encoding="utf-8",
            )

            def forward():
                with (out / "frozen-server.log").open("w", encoding="utf-8") as log:
                    for line in server.stdout:
                        log.write(line)
                        log.flush()
                        print(line, end="", flush=True)

            threading.Thread(target=forward, daemon=True).start()
        page = opened.value
        page.wait_for_load_state()
        page.bring_to_front()
        require_browser_foreground(page)
        expect(page.locator("#id_username")).to_be_visible()
        page.locator("#id_username").fill(
            os.environ.get("TLAMATINI_TEST_USERNAME", "user")
        )
        page.locator("#id_password").fill(
            os.environ.get("TLAMATINI_TEST_PASSWORD", "changeme")
        )
        page.locator("button[type=submit], input[type=submit]").first.click()
        expect(page.locator("#filename")).to_have_text(fpmt.name, timeout=60000)
        expect(page.locator(".pmt-node")).to_have_count(4)
        expect(page.locator("#pmt-run-state")).to_have_text("Idle")
        startup_log = (out / 'frozen-server.log').read_text(encoding='utf-8')
        assert 'ERROR during RAG chain setup' not in startup_log, 'Initial chat setup failed; inspect frozen-server.log'
        page.locator("[data-action=fit]").click()
        page.evaluate("document.fonts.ready")
        checkpoint("01-frozen-cold-open-and-normal-login", page)
        original = geometry(page)
        page.evaluate('''() => {
            window.releaseMenuEvents = [];
            window.releaseMenuListeners = [];
            for (const type of ['pointerdown', 'pointerup', 'mousedown', 'mouseup', 'click', 'show.bs.dropdown', 'shown.bs.dropdown', 'hide.bs.dropdown', 'hidden.bs.dropdown']) {
                const listener = event => window.releaseMenuEvents.push({
                    type, target: event.target.outerHTML?.slice(0, 400), prevented: event.defaultPrevented
                });
                document.addEventListener(type, listener, true);
                window.releaseMenuListeners.push([type, listener]);
            }
        }''')
        page.get_by_role("button", name="File", exact=True).click()
        (out / 'file-menu-state.json').write_text(json.dumps(page.evaluate('''() => ({
            bootstrapVersion: window.bootstrap?.Dropdown?.VERSION || null,
            menu: document.querySelector('.dropdown-menu')?.outerHTML,
            toggle: document.querySelector('[data-bs-toggle="dropdown"]')?.outerHTML,
            events: window.releaseMenuEvents,
            viewport: {innerWidth, innerHeight, outerWidth, outerHeight, devicePixelRatio},
            toggleRect: document.querySelector('[data-bs-toggle="dropdown"]').getBoundingClientRect().toJSON(),
            scripts: [...document.scripts].map(script => script.src).filter(Boolean)
        })'''), indent=2), encoding='utf-8')
        page.evaluate('''() => {
            for (const [type, listener] of window.releaseMenuListeners) document.removeEventListener(type, listener, true);
            delete window.releaseMenuListeners;
            delete window.releaseMenuEvents;
        }''')
        page.locator("[data-action=save]").click()
        page.locator("#pmt-field-filename").fill("Installed round trip.fpmt")
        with page.expect_download() as download:
            page.get_by_role("button", name="Download .fpmt", exact=True).click()
        saved = out / "Installed round trip.fpmt"
        download.value.save_as(saved)
        page.get_by_role("button", name="File", exact=True).click()
        with page.expect_file_chooser() as choice:
            page.locator("[data-action=open]").click()
        choice.value.set_files(saved)
        expect(page.locator("#filename")).to_have_text(saved.name)
        page.wait_for_timeout(600)
        assert geometry(page) == original, (
            "Rich note rendering changed after save/open"
        )
        checkpoint("02-frozen-three-rich-notes-identical-roundtrip", page)
        divider = page.locator("#pmt-output-divider")
        divider.focus()
        divider.press("Home")
        expect(divider).to_have_attribute("aria-valuenow", "5")
        assert geometry(page) == original
        checkpoint("03-output-five-percent-stable-content", page)
        divider.focus()
        divider.press("End")
        expect(divider).to_have_attribute("aria-valuenow", "95")
        assert geometry(page) == original
        checkpoint("04-output-ninety-five-percent-stable-content", page)
        divider.press("Home")
        for _ in range(3):
            divider.press("Shift+ArrowUp")
        # Test the real warm executable handoff, preserving the running app.
        console_foreground()
        with context.expect_page(timeout=60000) as opened:
            subprocess.run(
                command + [str(flw)],
                cwd=install,
                env=env,
                check=True,
                timeout=45,
            )
        acp = opened.value
        acp.bring_to_front()
        require_browser_foreground(acp)
        expect(acp.locator("#filename")).to_contain_text(flw.name, timeout=60000)
        expect(acp.locator("#sleeper-3")).to_be_visible()
        expect(acp.locator("#sleeper-7")).to_be_visible()
        assert server.poll() is None
        checkpoint("05-frozen-warm-agent-flow-opens", acp)
        acp.get_by_role("button", name="File", exact=True).click()
        acp.once("dialog", lambda d: d.accept("Installed agents saved.flw"))
        with acp.expect_download() as download:
            acp.locator("#save-as-button").click()
        saved_agents = out / "Installed agents saved.flw"
        download.value.save_as(saved_agents)
        data = json.loads(saved_agents.read_text(encoding="utf-8"))
        assert [n["id"] for n in data["nodes"]] == ["sleeper-3", "sleeper-7"]
        assert data["nodes"][0]["configData"]["target_agents"] == ["sleeper_7"]
        checkpoint("06-frozen-agent-save-preserves-identities", acp)
        broken = out / "Invalid.flw"
        broken.write_text('{"wrong":"format"}', encoding="utf-8")
        acp.get_by_role("button", name="File", exact=True).click()
        with acp.expect_file_chooser() as choice:
            acp.locator("#file-open-button").click()
        choice.value.set_files(broken)
        expect(
            acp.get_by_role("dialog").filter(has_text="Could not open diagram")
        ).to_be_visible()
        expect(acp.locator(".canvas-item")).to_have_count(2)
        checkpoint("07-frozen-invalid-agent-file-preserves-diagram", acp)
        acp.get_by_role("dialog").get_by_role(
            "button", name="OK", exact=True
        ).click()
        chat = context.new_page()
        chat.goto(base + "/agent/agent/")
        expect(chat.locator("#open-button")).to_be_visible()
        doc = out / "Keep the chat document.txt"
        doc.write_text(
            "The installed chat preserves this document when opening either flow editor.",
            encoding="utf-8",
        )
        with chat.expect_file_chooser() as choice:
            chat.locator("#open-button").click()
        choice.value.set_files(doc)
        expect(chat.locator("#filename")).to_contain_text(doc.name)
        for file in (fpmt, flw):
            chat.bring_to_front()
            with chat.expect_file_chooser() as choice:
                chat.locator("#open-button").click()
            with context.expect_page() as opened:
                choice.value.set_files(file)
            target = opened.value
            target.wait_for_load_state()
            confirm = target.locator(".tlmpop-overlay button").filter(
                has_text="Continue"
            )
            if confirm.is_visible():
                confirm.click()
            expect(target.locator("#filename")).to_contain_text(
                file.name, timeout=60000
            )
            expect(chat.locator("#filename")).to_contain_text(doc.name)
            checkpoint("08-chat-routes-" + file.suffix[1:].lower(), target)
        admin = context.new_page()
        admin.goto(base + "/admin/")
        expect(admin.locator("#site-name")).to_be_visible()
        models = admin.locator("#content-main th a").evaluate_all(
            "links=>links.map(a=>({name:a.textContent.trim(),href:a.href}))"
        )
        assert models, "No admin models are listed"
        checkpoint("09-admin-index", admin, {"models": len(models)})
        for model in models:
            response = admin.goto(model["href"])
            assert response and response.status == 200, model["name"]
            expect(admin.locator("#content h1")).to_be_visible()
            assert "Traceback" not in admin.locator("body").inner_text(), model[
                "name"
            ]
            print("ADMIN LIST PASS: " + model["name"], flush=True)
        (out / "admin-models.json").write_text(
            json.dumps(models, indent=2), encoding="utf-8"
        )
        checkpoint("10-all-admin-model-list-pages", admin, {"count": len(models)})
        group_name = "Release test " + str(time.time_ns())
        admin.goto(base + "/admin/auth/group/add/")
        admin.locator("#id_name").fill(group_name)
        admin.locator("input[name=_save]").click()
        expect(admin.locator(".success")).to_contain_text("successfully")
        admin.locator("#result_list").get_by_role("link", name=group_name, exact=True).click()
        admin.locator("#id_name").fill(group_name + " edited")
        admin.locator("input[name=_save]").click()
        admin.locator("#result_list").get_by_role("link", name=group_name + " edited", exact=True).click()
        admin.locator(".deletelink").click()
        admin.locator("input[type=submit]").click()
        expect(admin.locator(".success")).to_contain_text("successfully")
        checkpoint("11-admin-create-edit-delete-test-group", admin)
        if args.mcp_fixture:
            console_foreground()
            probe = Path(__file__).with_name('release_mcp_checks.py').resolve()
            receipt = out / 'live-mcp-clients.json'
            probe_env = {**env, 'TLAMATINI_RELEASE_MCP_FIXTURE': str(args.mcp_fixture.resolve()),
                         'TLAMATINI_RELEASE_MCP_OUTPUT': str(receipt)}
            source = f"exec(compile(open({str(probe)!r}, encoding='utf-8').read(), {str(probe)!r}, 'exec'))"
            subprocess.run(command + ['shell', '-c', source], cwd=install, env=probe_env,
                           timeout=90, check=True)
            probe_result = json.loads(receipt.read_text(encoding='utf-8'))
            assert probe_result['status'] == 'PASS' and probe_result['mode'] == mode
            checkpoint('live-mcp-configured-clients', admin, probe_result)
        if args.shell_files:
            assert not args.source, 'Windows association checks require the installed frozen application'
            from release_shell_file_checks import run_shell_file_checks
            run_shell_file_checks(context, fpmt, flw, install, env['BROWSER'], checkpoint)
        if args.authentication:
            from release_auth_checks import run_auth_checks
            run_auth_checks(admin, base, checkpoint)
        if args.extended:
            from release_extended_checks import run_extended_checks
            run_extended_checks(chat, acp, page, out, checkpoint)
        if args.agent_catalog:
            from release_agent_catalog_checks import run_agent_catalog_checks
            run_agent_catalog_checks(acp, out, checkpoint, only=args.agent_filter)
        if args.commentary:
            from release_commentary_checks import run_commentary_checks
            page.bring_to_front()
            run_commentary_checks(page, out, base, lambda name: checkpoint('commentary-' + name, page), errors)
        if args.acp_editor:
            from release_acp_editor_checks import run_acp_editor_checks
            acp.bring_to_front()
            run_acp_editor_checks(acp, out, lambda name: checkpoint('acp-editor-' + name, acp))
        if args.output_resize:
            from release_output_resize_checks import run_output_resize_checks
            page.bring_to_front()
            run_output_resize_checks(page, out, base, lambda name: checkpoint('output-resize-' + name, page))
        if args.acp_runtime:
            from release_acp_runtime_checks import run_acp_runtime_checks
            run_acp_runtime_checks(acp, out, checkpoint)
        if args.prompt_runtime:
            from release_prompt_runtime_checks import run_prompt_runtime_checks
            run_prompt_runtime_checks(page, out, checkpoint)
        assert not errors, errors
        assert not resource_failures, resource_failures
        final_server_log = (out / 'frozen-server.log').read_text(encoding='utf-8')
        for failure in ('ERROR during RAG chain setup', 'Error fetching system context:',
                        'Error fetching files context:'):
            assert failure not in final_server_log, f'Chat context failed during acceptance: {failure}'
        outcome = 0
        print(
            "INSTALLED PANEL CHECKS PASSED; holding visible for inspection.",
            flush=True,
        )
        admin.wait_for_timeout(10000)
        context.close()
        context = None
    except Exception:
        traceback.print_exc()
        try:
            visible.photograph("failure")
        except Exception:
            traceback.print_exc()
    finally:
        if context:
            try:
                context.close()
            except Exception:
                pass
        if pw:
            pw.stop()
        if server and server.poll() is None:
            try:
                parent = psutil.Process(server.pid)
                family = parent.children(recursive=True) + [parent]
                for proc in reversed(family):
                    try:
                        proc.terminate()
                    except psutil.NoSuchProcess:
                        pass
                _, alive = psutil.wait_procs(family, timeout=10)
                for proc in alive:
                    proc.kill()
            except psutil.NoSuchProcess:
                pass
        # Agent children can outlive their parent and change working directory.
        # Audit the same inherited installation identity used by the uninstaller.
        sys.path.insert(0, str(ROOT))
        from uninstall_processes import stop_owned_workers
        ownership_root = install / 'Tlamatini/agent' if args.source else install
        try:
            worker_cleanup = stop_owned_workers(str(ownership_root))
        except Exception as exc:
            worker_cleanup = {'error': str(exc)}
            outcome = 1
            print('WORKER CLEANUP FAILED: ' + str(exc), flush=True)
        (out / 'worker-cleanup.json').write_text(json.dumps(worker_cleanup, indent=2), encoding='utf-8')
        remaining = [
            c.laddr.port
            for c in psutil.net_connections(kind="tcp")
            if c.status == psutil.CONN_LISTEN and c.laddr.port in service_ports
        ]
        if remaining:
            outcome = 1
            print('SERVICE PORTS REMAIN: ' + str(remaining), flush=True)
        (out / "summary.json").write_text(
            json.dumps(
                dict(
                    exit_code=outcome,
                    checks=results,
                    browser_errors=errors,
                    resource_failures=resource_failures,
                    remaining_app_ports=remaining,
                ),
                indent=2,
            ),
            encoding="utf-8",
        )
    return outcome


if __name__ == "__main__":
    sys.exit(main())
