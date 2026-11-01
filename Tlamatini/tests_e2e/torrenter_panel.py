# Tlamatini Author Banner — Created by Angela López Mendoza · @angelahack1
"""Run and inspect a real Torrenter flow using the visible Agentic Control Panel."""
import argparse
import json
import re
import sys
import time
import uuid
from pathlib import Path

import psutil
import win32api
import win32con
import win32gui
import win32process
from playwright.sync_api import expect, sync_playwright


def foreground_page(page):
    page.bring_to_front()
    title = page.title()
    connection = page.context.browser.new_browser_cdp_session()
    try:
        processes = connection.send("SystemInfo.getProcessInfo")["processInfo"]
        browser_pid = next(item["id"] for item in processes if item["type"] == "browser")
    finally:
        connection.detach()
    # The control panel rotates the characters of its tab title continuously.
    # Chrome and the DOM may report adjacent frames of that same animation.
    def title_key(value):
        return ''.join(char for char in value if char.isalnum()).casefold()
    key = title_key(title)
    def matches(hwnd):
        if not win32gui.IsWindowVisible(hwnd) or not win32gui.GetClassName(hwnd).startswith("Chrome_WidgetWin"):
            return False
        pid = win32process.GetWindowThreadProcessId(hwnd)[1]
        if pid != browser_pid or psutil.Process(pid).name().lower() != "chrome.exe":
            return False
        window_title = win32gui.GetWindowText(hwnd)
        candidate = title_key(window_title.split(" - ")[0])
        return (window_title.startswith(title) or (len(candidate) == len(key) and candidate in key * 2)
                or (hwnd == win32gui.GetForegroundWindow() and page.evaluate("document.hasFocus()")))
    for _ in range(25):
        hwnd = win32gui.GetForegroundWindow()
        if hwnd and matches(hwnd) and not win32gui.IsIconic(hwnd):
            return hwnd
        windows = []
        win32gui.EnumWindows(lambda h, _: windows.append(h) if matches(h) else None, None)
        if windows:
            handle = windows[0]
            if win32gui.IsIconic(handle):
                win32gui.ShowWindow(handle, win32con.SW_RESTORE)
            win32api.keybd_event(win32con.VK_MENU, 0, 0, 0)
            win32api.keybd_event(win32con.VK_MENU, 0, win32con.KEYEVENTF_KEYUP, 0)
            try:
                win32gui.SetForegroundWindow(handle)
            except OSError:
                pass
        time.sleep(.1)
    raise RuntimeError("Could not verify the actual Chrome window for " + title)


def photograph(page, directory, label):
    from shoter_shot import take_shot
    for _ in range(3):
        hwnd = foreground_page(page)
        if not take_shot(str(directory), label + ".png", str(directory)):
            raise RuntimeError("Shoter could not capture the visible panel.")
        if win32gui.GetForegroundWindow() == hwnd:
            return
    raise RuntimeError("Chrome lost the foreground during the photograph.")


def flow(action, arguments):
    nodes = [{"id":"starter-1","text":"Starter","left":"80px","top":"125px","agentPurpose":"Entry point"},
             {"id":"torrenter-1","text":"Torrenter","left":"310px","top":"125px","agentPurpose":"",
              "configData":{"action":action,"arguments":json.dumps(arguments),"wait_for_completion":False}},
             {"id":"ender-1","text":"Ender","left":"550px","top":"125px","agentPurpose":"Finish"}]
    wires = [{"sourceIndex":i,"targetIndex":i+1,"sourceId":nodes[i]["id"],"targetId":nodes[i+1]["id"],
              "inputSlot":0,"outputSlot":0} for i in range(2)]
    return {"schemaVersion":2,"nodes":nodes,"connections":wires,"artifacts":{}}


def exercise(page, directory, label, action, fields, expected, wait=False):
    page.bring_to_front()
    page.locator('#acp-agent-search').fill('Torrenter')
    expect(page.locator('#agents-list [data-content="Torrenter"]')).to_be_visible()
    file = directory / (label + ".flw")
    file.write_text(json.dumps(flow(action, fields)), encoding="utf-8")
    page.locator('#file-dropdown').click()
    with page.expect_file_chooser() as chooser:
        page.locator('#file-open-button').click()
    chooser.value.set_files(str(file))
    tile = page.locator('#canvas-content .torrenter-agent')
    expect(tile).to_be_visible(timeout=45000)
    expect(page.locator('#filename')).to_contain_text(label, timeout=45000)
    expect(page.locator('#canvas-content .canvas-item')).to_have_count(3)
    if action == 'download':
        tile.dblclick()
        switch = page.locator('#canvas-item-dialog-message [data-key="wait_for_completion"]')
        expect(switch).to_be_visible()
        switch.set_checked(wait)
        photograph(page,directory,label+'-setting')
        page.locator('.ui-dialog:visible').get_by_role('button',name=re.compile(r'^(Save|Guardar)$', re.I)).click()
        report=page.locator('#deployment-result-dialog').locator('xpath=..')
        expect(report).to_be_visible(timeout=15000)
        expect(page.locator('#deployment-result-path')).to_contain_text('torrenter_1')
        report.get_by_role('button',name=re.compile(r'^(OK|Aceptar)$',re.I)).click()
        expect(report).to_be_hidden()
    page.locator('#btn-validate').click()
    dialog = page.locator('.ui-dialog:visible').last
    expect(dialog).to_be_visible(timeout=20000)
    print(label,'validation',dialog.inner_text()[:900],flush=True)
    expect(dialog).to_contain_text(re.compile(r'Flow is Valid|flow es válido',re.I))
    photograph(page,directory,label+'-validated')
    page.keyboard.press('Escape')
    expect(dialog).to_have_count(0,timeout=6000)
    page.locator('#btn-start').click()
    # Wait for the start report to settle, then close it through its own controls.
    time.sleep(3)
    print(label,'start report',page.locator('.ui-dialog:visible').all_inner_texts(),flush=True)
    for _ in range(3):
        shown = page.locator('.ui-dialog:visible')
        if not shown.count():
            break
        close = shown.last.locator('button').filter(has_text=re.compile(r'^(OK|Aceptar|Cerrar|Close|Listo|Continue!?|Continuar!?)$',re.I))
        if close.count():
            close.first.click()
        else:
            page.keyboard.press('Escape')
        time.sleep(.5)
    tile.click(button='right')
    page.locator('#ctx-menu-view-log').click()
    log = page.locator('#log-viewer-content')
    expect(log).to_contain_text(expected, timeout=90000)
    # A fast publisher can finish between two polls. Read the complete activation,
    # including its final receipt, rather than the first partial body containing a hash.
    expect(log).to_contain_text(re.compile(r'(?:Finished|Fin) \(UTC\):'), timeout=90000)
    output = log.inner_text()
    if action in ('manifest', 'download'):
        assert 'magnet:?' in output and re.search(r'(Seeds connected|Semillas conectadas): \d+',output)
    (directory/(label+'-log.txt')).write_text(output,encoding='utf8')
    photograph(page,directory,label+'-result')
    print('PASS',label,expected,flush=True)
    return output


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--browser-port',type=int,required=True)
    parser.add_argument('--origin',required=True)
    parser.add_argument('--job',required=True)
    parser.add_argument('--sha256',required=True)
    parser.add_argument('--evidence',type=Path,required=True)
    parser.add_argument('--catalog',type=Path,help="Exercise fresh download and manifest flows using a publisher PDF.")
    parser.add_argument('--wait',action='store_true',help="Check the wait option in the canvas dialog.")
    args=parser.parse_args()
    if not re.fullmatch(r'http://127\.0\.0\.1:\d+',args.origin) or not re.fullmatch(r'[a-f0-9]{64}',args.sha256):
        parser.error("Supply the development loopback origin and verified SHA-256.")
    args.evidence.mkdir(parents=True,exist_ok=True)
    sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'.claude/skills/tlamatini-daily-chat-test/harness'))
    with sync_playwright() as driver:
        # Attach to the operator's visible, headless=False test Chrome.
        context=driver.chromium.connect_over_cdp(f'http://127.0.0.1:{args.browser_port}').contexts[0]
        def panel():
            tab=context.new_page()
            tab.goto(args.origin+'/agent/agentic_control_panel/')
            return tab
        page=panel()
        try:
            exercise(page,args.evidence,'Torrenter-manifest','manifest',{'job_id':args.job},args.sha256)
            if args.catalog:
                from torrenter_books import torrent
                book=next(b for b in json.loads(args.catalog.read_text(encoding='utf-8-sig')) if b['name']=='Think Python')
                source=context.new_page()
                source.goto(args.origin+'/agent/torrenter/sources/')
                key=uuid.uuid4().hex
                payload=torrent(book,(args.catalog.parent/book['filename']).read_bytes(),key)
                source.locator('#torrent').set_input_files({'name':'panel-book.torrent','mimeType':'application/x-bittorrent','buffer':payload})
                source.locator('#torrent').locator('xpath=ancestor::form').locator('button[type=submit]').click()
                inspection=source.locator('#inspection-id').inner_text()
                summary=source.locator('section').filter(has=source.locator('#inspection-id'))
                revision=int(re.search(r'(\d+)\s*$',summary.locator('p').nth(1).inner_text()).group(1))
                file_id=int(summary.locator('tbody tr td').first.inner_text())
                expect(summary).to_contain_text('ready')
                photograph(source,args.evidence,'Torrenter-inspection')
                source.close()
                dashboard=next(t for t in context.pages if t.url==args.origin+'/agent/torrenter/workspace/')
                before=sum('completed' in row for row in dashboard.locator('#rows tr').all_inner_texts())
                page=panel()
                log=exercise(page,args.evidence,'Torrenter-download-'+('yes' if args.wait else 'no'),'download',{
                    'inspection_id':inspection,'metadata_revision':revision,'selected_file_ids':[file_id],
                    'destination_root_id':'downloads','operation_key':key,'seed_after_completion':False
                },book['sha256'] if args.wait else 'operation_id:', wait=args.wait)
                job=re.search(r'^job_id: ([0-9a-f]{32})$',log,re.M).group(1)
                assert 'thinkpython2.pdf' in log and 'magnet:?' in log
                assert bool(re.search(r'^(?:Status|Estado): completed$',log,re.M))==args.wait
                dashboard.bring_to_front()
                # Select the actual new job through its table row. Examine the manifest
                # from the panel only after this additional publication completes.
                deadline=time.monotonic()+100
                while time.monotonic()<deadline:
                    rows=dashboard.locator('#rows tr').all_inner_texts()
                    if sum('completed' in row for row in rows)>before:
                        break
                    time.sleep(1)
                else:
                    raise RuntimeError('The new transfer did not complete in the visible queue.')
                page=panel()
                result=exercise(page,args.evidence,'Torrenter-published','manifest',{'job_id':job},book['sha256'])
                assert f'{book["size"]:,}' in result and 'thinkpython2.pdf' in result and 'magnet:?' in result
                assert page.locator('#log-viewer-content').evaluate('(p) => p.scrollWidth <= p.clientWidth + 1')
                print('PASS new ACP download',job,book['name'],book['sha256'],flush=True)
        except Exception:
            print('Panel at failure:',page.locator('.ui-dialog:visible').all_inner_texts(),flush=True)
            page.screenshot(path=str(args.evidence/'failure.png'))
            raise


if __name__=='__main__':
    main()

