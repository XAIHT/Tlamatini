# Tlamatini Author Banner — Angela López Mendoza
"""VISIBLE proof that #drag-divider has the same look and feel as #vertical-drag-divider.

Runs the REAL source app on an isolated database (Temp/drag-divider-look), opens a
HEADED Chrome on the real desktop and checks the three pages that carry a
#drag-divider: the Chat page, the Agentic Control Panel and the Prompt Flow Panel.

For every page it checks, in this order:
  1. accessible  - role=separator, vertical orientation, a label and a tooltip
  2. pill        - the teal grip pill (4x42 CSS px, #55BBAA, radius 2) is drawn,
                   centred, and REALLY PAINTED (pixels read from Shoter's photo)
  3. idle        - the line is grey (#8a8c98 at 0.8) when nothing touches it
  4. hover       - the line turns teal under the mouse (computed + pixels)
  5. drag        - while held: body.resizing, teal line, the seam moves (photo
                   taken with the mouse button still down)
  6. released    - after release the line is grey again
  7. keyboard    - focus ring 2px teal, teal line; Shift+arrow moves 5x an arrow
On the Chat page it also checks that #vertical-drag-divider did not change and
that the new pill is exactly its pill turned on its side.

HEADLESS IS FORBIDDEN. Every photo is taken by Tlamatini's Shoter agent (whole
desktop); Pillow is only used to READ and crop those photos. Nothing outside
Temp/drag-divider-look is written; no production database or config is touched.
"""
import asyncio
from datetime import datetime, timezone
import html
import importlib.util
import json
import os
from pathlib import Path
import secrets
import sys
import threading
import time
import traceback

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'Temp/drag-divider-look'
PORT = 8873
BASE = f'http://127.0.0.1:{PORT}'
TEAL = (85, 187, 170)
GREY = (138, 140, 152)
PAGES = [
    ('chat', '/agent/agent/', 'Chat page'),
    ('acp', '/agent/agentic_control_panel/', 'Agentic Control Panel'),
    ('pfp', '/agent/prompt_flow_panel/', 'Prompt Flow Panel'),
]
_shoter_module = None
LOG = None


def log(*parts):
    line = ' '.join(str(p) for p in parts)
    stamp = datetime.now().strftime('%H:%M:%S')
    print(f'[{stamp}] {line}', flush=True)
    if LOG is not None:
        with open(LOG, 'a', encoding='utf-8') as handle:
            handle.write(f'[{stamp}] {line}\n')


def shoter(name):
    """Whole-desktop photo by Tlamatini's Shoter agent; returns (path, metadata)."""
    global _shoter_module
    old_cwd = Path.cwd()
    os.environ['AGENT_REANIMATED'] = '1'
    meta = {}
    try:
        if _shoter_module is None:
            spec = importlib.util.spec_from_file_location(
                'divider_shoter', ROOT / 'Tlamatini/agent/agents/shoter/shoter.py')
            _shoter_module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(_shoter_module)
        path = _shoter_module.capture_screenshot(str(OUT), all_screens=True,
                                                 filename=name, metadata=meta)
    finally:
        os.chdir(old_cwd)
    return Path(path), meta


STATE_JS = r"""(sel) => {
  const el = document.querySelector(sel);
  if (!el) return null;
  const r = el.getBoundingClientRect();
  const b = getComputedStyle(el, '::before');
  const a = getComputedStyle(el, '::after');
  const s = getComputedStyle(el);
  return {
    rect: {x: r.left, y: r.top, w: r.width, h: r.height},
    before: {content: b.content, w: b.width, h: b.height, top: b.top, left: b.left,
             bg: b.backgroundColor, radius: b.borderTopLeftRadius},
    after: {bg: a.backgroundColor, op: a.opacity},
    outline: {style: s.outlineStyle, width: s.outlineWidth, color: s.outlineColor},
    cursor: s.cursor,
    role: el.getAttribute('role'), orient: el.getAttribute('aria-orientation'),
    label: el.getAttribute('aria-label') || '', title: el.getAttribute('title') || '',
    focused: document.activeElement === el,
    focusVisible: el.matches(':focus-visible'),
    resizing: document.body.classList.contains('resizing'),
    view: {w: innerWidth, h: innerHeight, dpr: devicePixelRatio}
  };
}"""

TEAL_CSS = 'rgb(85, 187, 170)'
GREY_CSS = 'rgb(138, 140, 152)'


def px(value):
    try:
        return float(str(value).replace('px', ''))
    except ValueError:
        return float('nan')


def near(color, target, tol=34):
    return all(abs(int(c) - int(t)) <= tol for c, t in zip(color[:3], target))


class Photo:
    """Maps CSS pixels of the test page onto Shoter's physical-pixel photo."""

    def __init__(self, path, meta, window, page):
        from PIL import Image
        import win32gui
        self.path = path
        self.image = Image.open(path).convert('RGB')
        g = page.evaluate('({w: innerWidth, h: innerHeight, dpr: devicePixelRatio})')
        self.dpr = g['dpr']
        cx, cy = win32gui.ClientToScreen(window.hwnd, (0, 0))
        _, _, cw, ch = win32gui.GetClientRect(window.hwnd)
        # The page viewport is the bottom of Chrome's client area (tabs and
        # toolbar sit above it).
        self.vx = cx + (cw - round(g['w'] * self.dpr))
        self.vy = cy + (ch - round(g['h'] * self.dpr))
        self.ox = meta.get('capture_left', 0)
        self.oy = meta.get('capture_top', 0)
        self.mapped = meta.get('coordinate_space') == 'physical_screen'

    def to_img(self, x, y):
        return (round(self.vx + x * self.dpr - self.ox), round(self.vy + y * self.dpr - self.oy))

    def count(self, box, target, tol=34):
        """(matching, total) pixels in a CSS-pixel box (x0, y0, x1, y1)."""
        x0, y0 = self.to_img(box[0], box[1])
        x1, y1 = self.to_img(box[2], box[3])
        hit = total = 0
        for yy in range(max(0, y0), min(self.image.height, y1)):
            for xx in range(max(0, x0), min(self.image.width, x1)):
                total += 1
                if near(self.image.getpixel((xx, yy)), target, tol):
                    hit += 1
        return hit, total

    def zoom(self, center, name, size=(70, 150), scale=4):
        from PIL import Image
        cx, cy = self.to_img(*center)
        w, h = round(size[0] * self.dpr), round(size[1] * self.dpr)
        crop = self.image.crop((cx - w // 2, cy - h // 2, cx + w // 2, cy + h // 2))
        crop = crop.resize((crop.width * scale, crop.height * scale), Image.NEAREST)
        target = OUT / name
        crop.save(target)
        return target


def run_page(page, window, key, label, results):
    def record(name, ok, detail, photo=None, zoom=None):
        results.append({'page': label, 'check': name, 'ok': bool(ok), 'detail': detail,
                        'photo': photo.path.name if photo else '', 'zoom': zoom.name if zoom else ''})
        log(('PASS' if ok else 'FAIL'), f'{label} :: {name} :: {detail}')

    def state(sel='#drag-divider'):
        return page.evaluate(STATE_JS, sel)

    def snap(name):
        window.verify()
        path, meta = shoter(f'{key}-{name}.png')
        window.verify()
        return Photo(path, meta, window, page)

    def park_mouse():
        # Somewhere neutral and far from the divider: the page header area.
        view = page.evaluate('({w: innerWidth, h: innerHeight})')
        page.mouse.move(view['w'] - 30, view['h'] - 12)
        page.wait_for_timeout(350)

    s = state()
    if s is None:
        record('divider present', False, '#drag-divider not found on the page')
        return
    log(f'{label}: divider rect {s["rect"]}, dpr {s["view"]["dpr"]}')

    # 1. accessible
    ok = (s['role'] == 'separator' and s['orient'] == 'vertical' and s['label'].strip()
          and 'Shift' in s['title'] and s['cursor'] == 'col-resize')
    record('accessible', ok, f"role={s['role']} orientation={s['orient']} label='{s['label']}' "
                             f"cursor={s['cursor']} title='{s['title']}'")

    # 2. pill (computed)
    b = s['before']
    expected_top = s['rect']['h'] / 2 - 21
    ok = (b['content'] in ('""', "''") and px(b['w']) == 4 and px(b['h']) == 42
          and b['bg'] == TEAL_CSS and px(b['radius']) == 2 and abs(px(b['top']) - expected_top) <= 1)
    record('pill computed style', ok, f"content={b['content']} size={b['w']}x{b['h']} bg={b['bg']} "
                                      f"radius={b['radius']} top={b['top']} (expected {expected_top:.1f}px)")

    if key == 'chat':
        v = state('#vertical-drag-divider')
        vb = v['before'] if v else {}
        ok = (v is not None and px(vb.get('w')) == px(b['h']) and px(vb.get('h')) == px(b['w'])
              and vb.get('bg') == b['bg'] and vb.get('radius') == b['radius'])
        record('pill = vertical pill turned on its side', ok,
               f"vertical {vb.get('w')}x{vb.get('h')} {vb.get('bg')} r={vb.get('radius')} vs "
               f"drag {b['w']}x{b['h']} {b['bg']} r={b['radius']}")
        va = v['after'] if v else {}
        ok = v is not None and va.get('bg') == GREY_CSS and abs(float(va.get('op', 0)) - 0.8) < 0.01
        record('vertical divider unchanged (idle)', ok, f"line={va.get('bg')} opacity={va.get('op')}")

    # 3. idle (+ real pixels of the pill)
    park_mouse()
    page.evaluate('document.activeElement && document.activeElement.blur()')
    s = state()
    r = s['rect']
    pill_box = (r['x'] + 2, r['y'] + r['h'] / 2 - 21, r['x'] + 6, r['y'] + r['h'] / 2 + 21)
    line_box = (r['x'] + 2, r['y'] + r['h'] * 0.25 - 10, r['x'] + 6, r['y'] + r['h'] * 0.25 + 10)
    pill_center = (r['x'] + 4, r['y'] + r['h'] / 2)
    photo = snap('1-idle')
    zoom = photo.zoom(pill_center, f'{key}-1-idle-zoom.png')
    pill_hit, pill_total = photo.count(pill_box, TEAL)
    line_hit, line_total = photo.count(line_box, TEAL)
    ok = (s['after']['bg'] == GREY_CSS and abs(float(s['after']['op']) - 0.8) < 0.01
          and photo.mapped and pill_total and pill_hit / pill_total >= 0.6 and line_hit == 0)
    record('idle: grey line, teal pill painted', ok,
           f"line={s['after']['bg']} opacity={s['after']['op']}; teal pixels in pill "
           f"{pill_hit}/{pill_total}; teal pixels on the line {line_hit}/{line_total}", photo, zoom)

    # 4. hover (mouse on the line, below the pill, photo samples above the pill)
    page.mouse.move(r['x'] + r['w'] / 2, r['y'] + r['h'] * 0.75)
    page.wait_for_timeout(400)
    s = state()
    photo = snap('2-hover')
    zoom = photo.zoom((r['x'] + 4, r['y'] + r['h'] * 0.25), f'{key}-2-hover-zoom.png')
    line_hit, line_total = photo.count(line_box, TEAL)
    ok = (s['after']['bg'] == TEAL_CSS and float(s['after']['op']) == 1.0
          and line_total and line_hit / line_total >= 0.25)
    record('hover: line turns teal', ok, f"line={s['after']['bg']} opacity={s['after']['op']}; "
                                         f"teal pixels on the line {line_hit}/{line_total}", photo, zoom)

    # 5. drag (photo while the button is still held)
    start_x = r['x'] + r['w'] / 2
    mid_y = r['y'] + r['h'] / 2
    page.mouse.move(start_x, mid_y)
    page.mouse.down()
    direction = -1 if (start_x / s['view']['w']) > 0.5 else 1
    for i in range(1, 9):
        page.mouse.move(start_x + direction * i * 10, mid_y)
        page.wait_for_timeout(40)
    page.wait_for_timeout(300)
    held = state()
    hr = held['rect']
    photo = snap('3-dragging')
    zoom = photo.zoom((hr['x'] + 4, hr['y'] + hr['h'] * 0.25), f'{key}-3-dragging-zoom.png')
    drag_line = (hr['x'] + 2, hr['y'] + hr['h'] * 0.25 - 10, hr['x'] + 6, hr['y'] + hr['h'] * 0.25 + 10)
    line_hit, line_total = photo.count(drag_line, TEAL)
    moved = hr['x'] - r['x']
    ok = (held['resizing'] and held['after']['bg'] == TEAL_CSS and abs(moved) >= 20
          and line_total and line_hit / line_total >= 0.25)
    record('drag: teal while held, seam moves', ok,
           f"body.resizing={held['resizing']} line={held['after']['bg']} moved={moved:+.1f}px; "
           f"teal pixels on the line {line_hit}/{line_total}", photo, zoom)
    page.mouse.up()

    # 6. released
    park_mouse()
    page.evaluate('document.activeElement && document.activeElement.blur()')
    s = state()
    ok = (not s['resizing']) and s['after']['bg'] == GREY_CSS
    record('released: back to grey', ok, f"body.resizing={s['resizing']} line={s['after']['bg']}")

    # 7. keyboard: focus ring, then arrow vs Shift+arrow
    page.keyboard.press('Shift')
    page.evaluate("document.querySelector('#drag-divider').focus({focusVisible: true})")
    s = state()
    if not s['focusVisible']:
        page.evaluate('document.activeElement && document.activeElement.blur()')
        for _ in range(160):
            page.keyboard.press('Tab')
            if page.evaluate("document.activeElement && document.activeElement.id === 'drag-divider'"):
                break
        s = state()
    o = s['outline']
    r = s['rect']
    photo = snap('4-keyboard-focus')
    zoom = photo.zoom((r['x'] + 4, r['y'] + r['h'] / 2), f'{key}-4-keyboard-focus-zoom.png')
    ok = (s['focused'] and s['focusVisible'] and o['style'] == 'solid' and px(o['width']) == 2
          and o['color'] == TEAL_CSS and s['after']['bg'] == TEAL_CSS)
    record('keyboard focus: teal ring + teal line', ok,
           f"focused={s['focused']} focus-visible={s['focusVisible']} outline={o['style']} "
           f"{o['width']} {o['color']} line={s['after']['bg']}", photo, zoom)

    toward_centre = 'ArrowLeft' if (r['x'] / s['view']['w']) > 0.5 else 'ArrowRight'
    x0 = page.evaluate("document.querySelector('#drag-divider').getBoundingClientRect().left")
    page.keyboard.press(toward_centre)
    page.wait_for_timeout(250)
    x1 = page.evaluate("document.querySelector('#drag-divider').getBoundingClientRect().left")
    page.keyboard.press(f'Shift+{toward_centre}')
    page.wait_for_timeout(250)
    x2 = page.evaluate("document.querySelector('#drag-divider').getBoundingClientRect().left")
    single, big = abs(x1 - x0), abs(x2 - x1)
    ratio = big / single if single else 0
    ok = single > 0.5 and 4.0 <= ratio <= 6.0
    record('keyboard: Shift+arrow = 5 arrow steps', ok,
           f"{toward_centre}: {single:.1f}px, Shift+{toward_centre}: {big:.1f}px (x{ratio:.2f})")
    page.evaluate('document.activeElement && document.activeElement.blur()')


def write_summary(results, started):
    passed = sum(1 for r in results if r['ok'])
    rows = []
    for r in results:
        pics = ''.join(
            f'<a href="{html.escape(n)}" target="_blank"><img src="{html.escape(n)}" loading="lazy"></a>'
            for n in (r['zoom'], r['photo']) if n)
        rows.append(
            f"<tr class={'ok' if r['ok'] else 'bad'}><td>{'PASS' if r['ok'] else 'FAIL'}</td>"
            f"<td>{html.escape(r['page'])}</td><td>{html.escape(r['check'])}</td>"
            f"<td><code>{html.escape(r['detail'])}</code></td><td class=pics>{pics}</td></tr>")
    page = f"""<!doctype html><meta charset=utf-8><title>Divider Look Test</title>
<style>
:root {{ color-scheme: dark; }}
body {{ background:#202129; color:#e8e8ee; font:15px/1.45 Segoe UI, sans-serif; margin:20px; }}
h1 {{ font-size:20px; }} table {{ border-collapse:collapse; width:100%; }}
td {{ border-bottom:1px solid #3a3b47; padding:8px; vertical-align:top; }}
tr.ok td:first-child {{ color:#55BBAA; font-weight:700; }} tr.bad td:first-child {{ color:#ff6b6b; font-weight:700; }}
code {{ white-space:pre-wrap; font-size:12px; color:#c8c9d4; }}
.pics img {{ max-height:220px; margin:0 6px 6px 0; border:1px solid #3a3b47; }}
</style>
<h1>#drag-divider look and feel — {passed}/{len(results)} checks passed</h1>
<p>Started {html.escape(started)} · source app, isolated database · headed Chrome · photos by Shoter (whole desktop).
Left image of each row = 4× zoom of the bar; right = the full-desktop photo. Click to open full size.</p>
<table>{''.join(rows)}</table>"""
    (OUT / 'SUMMARY.html').write_text(page, encoding='utf-8')
    return passed


def main():
    global LOG
    if any('headless' in arg.lower() for arg in sys.argv[1:]):
        raise SystemExit('HEADLESS IS FORBIDDEN. Use a verified visible console.')
    if sys.platform == 'win32':
        import ctypes
        ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
    OUT.mkdir(parents=True, exist_ok=True)
    for old in OUT.glob('*.png'):
        old.unlink()
    LOG = OUT / 'console.log'
    LOG.write_text('', encoding='utf-8')
    started = datetime.now().isoformat(timespec='seconds')
    log('DRAG-DIVIDER LOOK TEST — VISIBLE. Output folder:', OUT)
    sys.path.insert(0, str(ROOT / 'Tlamatini'))
    os.environ['DJANGO_SETTINGS_MODULE'] = 'tlamatini.settings'
    import tlamatini.settings as project_settings
    project_settings.DATABASES['default']['NAME'] = OUT / 'isolated-browser.sqlite3'
    project_settings.STATIC_ROOT = OUT / 'collected-static'
    import django
    django.setup()
    from django.core.management import call_command
    log('REAL SOURCE APP: migrating ONLY the isolated database in Temp/drag-divider-look')
    call_command('migrate', interactive=False, verbosity=0)
    call_command('collectstatic', interactive=False, verbosity=0)
    from django.contrib.auth import get_user_model
    username = 'divider-review'
    password = secrets.token_urlsafe(24)
    user, _ = get_user_model().objects.get_or_create(username=username)
    user.set_password(password)
    user.save()
    from django.contrib.staticfiles.handlers import ASGIStaticFilesHandler
    from tlamatini.asgi import application
    import uvicorn
    server = uvicorn.Server(uvicorn.Config(ASGIStaticFilesHandler(application), host='127.0.0.1',
                                           port=PORT, log_level='warning', loop='asyncio'))
    thread = threading.Thread(target=server.run, name='DividerSourceServer', daemon=True)
    thread.start()
    for _ in range(150):
        if server.started:
            break
        time.sleep(.1)
    if not server.started:
        log('STOPPED: the isolated source server did not start on port', PORT)
        return 3
    log('Server up on', BASE)
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    from playwright.sync_api import sync_playwright
    from chat_composer_visible_window import VisibleWindow
    results = []
    summary = {'passed': False}
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel='chrome', headless=False,
                                             chromium_sandbox=True, slow_mo=120)
        context = browser.new_context(no_viewport=True)
        context.add_init_script("localStorage.setItem('tlm_voice_settings', JSON.stringify({mode:'silent'}));")
        # Layout test only: model and microphone sockets are answered by nobody.
        context.route_web_socket('**/ws/**', lambda socket: socket.on_message(lambda message: None))
        page = context.new_page()
        window = VisibleWindow(page, context)
        log('REAL CHROME WINDOW:', window.resize(1440, 900))
        page.goto(BASE + '/', wait_until='domcontentloaded', timeout=60000)
        page.bring_to_front()
        gate = OUT / 'browser-visible-confirmed'
        gate.unlink(missing_ok=True)
        window.verify()
        shoter('0-browser-waiting.png')
        log('BROWSER WAITING: Claude inspects 0-browser-waiting.png, then creates browser-visible-confirmed.')
        while not gate.exists():
            page.wait_for_timeout(500)
        log('Browser confirmed visible. Logging in as the isolated test user.')
        if page.locator('#id_username').count():
            page.locator('#id_username').fill(username)
            page.locator('#id_password').fill(password)
            page.locator('button[type="submit"],input[type="submit"]').first.click()
            page.wait_for_load_state('domcontentloaded')
        password = None
        try:
            for key, path, label in PAGES:
                log('=' * 60)
                log('PAGE:', label, path)
                page.goto(BASE + path, wait_until='load', timeout=60000)
                page.wait_for_timeout(1800)
                window.activate()
                try:
                    run_page(page, window, key, label, results)
                except Exception:
                    log(traceback.format_exc())
                    shoter(f'{key}-failure.png')
                    results.append({'page': label, 'check': 'page run', 'ok': False,
                                    'detail': traceback.format_exc(), 'photo': f'{key}-failure.png', 'zoom': ''})
        finally:
            passed = write_summary(results, started)
            summary = {'at': datetime.now(timezone.utc).isoformat(), 'checks': results,
                       'passed': bool(results) and passed == len(results)}
            (OUT / 'summary.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
            log('=' * 60)
            log(f'RESULT: {passed}/{len(results)} checks passed ->', 'ALL PASS' if summary['passed'] else 'FAILURES')
            log('Report:', OUT / 'SUMMARY.html')
        window.release()
        page.goto(BASE + '/agent/agent/', wait_until='load')
        log('BROWSER STAYS OPEN on the Chat page so Angela can try the bar herself.')
        log('Create Temp/drag-divider-look/close.confirmed (or close Chrome) to finish.')
        close = OUT / 'close.confirmed'
        close.unlink(missing_ok=True)
        try:
            while not close.exists() and not page.is_closed():
                page.wait_for_timeout(500)
        except Exception:
            pass
        try:
            context.close()
            browser.close()
        except Exception:
            pass
    server.should_exit = True
    thread.join(timeout=10)
    return 0 if summary['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
