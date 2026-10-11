# Tlamatini Author Banner — Angela López Mendoza
"""Native zoom and narrow-window checks, run in the visible source harness."""
import json
import win32api
import win32con


def run_viewport_checks(page, context, out, capture):
    from playwright.sync_api import expect
    records = []
    errors = []
    page.on('pageerror', lambda error: errors.append(str(error)))
    window = page.native_window

    def settle():
        window.activate()
        page.wait_for_timeout(600)
        window.verify()

    def key(vk):
        window.activate()
        win32api.keybd_event(win32con.VK_CONTROL, 0, 0, 0)
        win32api.keybd_event(vk, 0, 0, 0)
        win32api.keybd_event(vk, 0, win32con.KEYEVENTF_KEYUP, 0)
        win32api.keybd_event(win32con.VK_CONTROL, 0, win32con.KEYEVENTF_KEYUP, 0)
        page.wait_for_timeout(350)

    def root_fits():
        settle()
        g = page.evaluate('''() => ({w:innerWidth,h:innerHeight,x:scrollX,y:scrollY,
            sw:document.documentElement.scrollWidth,sh:document.documentElement.scrollHeight,
            body:document.body.getBoundingClientRect().toJSON(),
            workspace:document.getElementById('chat-container').getBoundingClientRect().toJSON()})''')
        assert g['x'] == 0 and g['y'] == 0, g
        assert g['sw'] <= g['w'] + 1 and g['sh'] <= g['h'] + 1, g
        assert g['workspace']['bottom'] <= g['h'] + 1, g
        return g

    def bounded(locator):
        b = locator.bounding_box()
        v = page.evaluate('({w:innerWidth,h:innerHeight})')
        assert b and b['x'] >= -1 and b['y'] >= -1, (b,v)
        assert b['x']+b['width'] <= v['w']+1 and b['y']+b['height'] <= v['h']+1, (b,v)
        return b

    def record(name, photo):
        records.append({'name':name,'ok':True,'root':root_fits(),'native':window.verify()})
        (out/'viewport-checkpoints.json').write_text(json.dumps(records,indent=2),encoding='utf-8')
        capture(photo+'.png')
        print('VIEWPORT PASS:',name,flush=True)

    def menu(parent, item):
        toggle=page.locator('.navbar-toggler')
        if parent and toggle.is_visible() and not page.locator('#navbarMenu').evaluate("e=>e.classList.contains('show')"):
            toggle.click()
        if parent:
            page.locator(parent).click()
        page.locator(item).click()
        settle()

    dialogs = [
        ('omissions','#context-menu-button','#set-omissions','.ui-dialog:visible'),
        ('models','#config-menu-button','#config-models','.ui-dialog:visible'),
        ('external','#external-menu-button','#external-mcps','.emx-panel'),
        ('contacts','#config-menu-button','#config-contacts','.ctb-panel'),
        ('microphone','#config-menu-button','#config-mic','#tlm-mic-overlay .tlm-modal'),
        ('usage','#about-menu-button','#usage-button','#usage-dialog'),
        ('about','#about-menu-button','#about-button','#about-overlay .about-window'),
        ('catalog',None,'#prompts-catalog','#modal .modal-content'),
    ]

    def check_dialogs(label):
        for name,parent,item,panel in dialogs:
            menu(parent,item)
            loc=page.locator(panel).first
            expect(loc).to_be_visible(timeout=15000)
            bounded(loc)
            root_fits()
            fields=loc.locator('input:visible:not([type=hidden]), select:visible, textarea:visible')
            if fields.count():
                field=fields.first
                field.scroll_into_view_if_needed()
                bounded(field)
                assert field.evaluate('e=>{const r=e.getBoundingClientRect();return e.contains(document.elementFromPoint(r.x+r.width/2,r.y+r.height/2));}'), name+' field is covered'
            # Scroll the real body, then bring its dismiss control back into view.
            loc.evaluate('e=>{for(const n of [e,...e.querySelectorAll("*")]) {if (n.scrollHeight>n.clientHeight && /auto|scroll/.test(getComputedStyle(n).overflowY)) n.scrollTop=n.scrollHeight;}}')
            page.wait_for_timeout(250)
            record(label+' '+name+' dialog bounded and internally scrollable',label+'-'+name)
            page.keyboard.press('Escape')
            expect(loc).not_to_be_visible(timeout=5000)
            if page.locator('.navbar-toggler').is_visible() and page.locator('#navbarMenu').evaluate("e=>e.classList.contains('show')"):
                page.locator('.navbar-toggler').click()
            root_fits()

    key(0x30)
    window.resize(1440,900)
    baseline=page.evaluate('devicePixelRatio')
    page.reload(wait_until='domcontentloaded')
    page.wait_for_function('window.TlamatiniAvatarSize')
    page.evaluate('TlamatiniAvatarSize.set(160)')
    page.locator('#vertical-drag-divider').press('Home')
    record('100% complete source workspace','viewport-100')
    check_dialogs('zoom100')

    for _ in range(8):
        key(0x6B)
    zoom=page.evaluate('devicePixelRatio')/baseline
    assert abs(zoom-4) < .01, zoom
    page.reload(wait_until='domcontentloaded')
    page.wait_for_function('window.TlamatiniAvatarSize')
    page.evaluate('TlamatiniAvatarSize.set(0)')
    page.locator('#vertical-drag-divider').press('Home')
    page.locator('#chat-message-submit').scroll_into_view_if_needed()
    bounded(page.locator('#chat-message-submit'))
    record('Native Chrome 400%; composer controls reachable','viewport-400')
    page.evaluate('TlamatiniAvatarSize.set(160)')
    page.locator('#chat-message-submit').scroll_into_view_if_needed()
    assert page.locator('#chat-message-submit').evaluate('e=>{const r=e.getBoundingClientRect();return e.contains(document.elementFromPoint(r.x+r.width/2,r.y+r.height/2));}')
    record('400% floating avatar leaves Send accessible','viewport-400-floating')
    check_dialogs('zoom400')

    key(0x30)
    for _ in range(14):
        key(0x6D)
    minimum=page.evaluate('devicePixelRatio')/baseline
    print('NATIVE CHROME MINIMUM ZOOM:',minimum,flush=True)
    assert minimum <= .25 + .01, minimum
    page.reload(wait_until='domcontentloaded')
    record('Native Chrome minimum zoom '+str(round(minimum*100))+'%','viewport-native-minimum')
    check_dialogs('zoom-minimum')

    key(0x30)
    window.resize(520,800)
    # Chrome has a minimum native window width. Native 125% zoom gives a
    # phone-sized CSS viewport without a viewport larger than its real window.
    key(0x6B)
    key(0x6B)
    page.reload(wait_until='domcontentloaded')
    page.wait_for_function('window.TlamatiniAvatarSize')
    page.evaluate('TlamatiniAvatarSize.set(0)')
    page.locator('#vertical-drag-divider').press('Home')
    page.locator('#chat-message-submit').scroll_into_view_if_needed()
    bounded(page.locator('#chat-message-submit'))
    record('Narrow phone-sized native viewport with minimum workspace','viewport-phone')
    check_dialogs('phone')
    assert not errors,errors
    key(0x30)
    window.resize(1440,900)
    page.reload(wait_until='domcontentloaded')
    page.wait_for_function('window.TlamatiniAvatarSize')
    page.evaluate('TlamatiniAvatarSize.set(160)')
    page.locator('#vertical-drag-divider').press('Home')
    record('Return to 100% without page displacement','viewport-final')
    (out/'viewport-summary.json').write_text(json.dumps({'passed':True,'checks':records,'minimum_native_zoom':minimum,'javascript_errors':errors},indent=2),encoding='utf-8')
    print('ALL VIEWPORT CHECKS PASSED',len(records),flush=True)
    return records
