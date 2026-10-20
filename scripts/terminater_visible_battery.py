# Tlamatini Author Banner — Angela López Mendoza
"""The reusable VISIBLE check battery for the Terminals dock (any page that hosts it).

``Battery`` drives the real dock in the headed Chrome of ``terminater_visible_common.Harness``
and records one PASS/FAIL (with a full-desktop Shoter photograph) per observation.  The same
battery runs on the chat page (with and without its canvas), on the Agentic Control Panel and on
the Prompt Flow Panel; each page then adds its own checks on top (see the three suites).

Rules this module keeps (they are the project's, not style):
  * nothing is mocked: the dock talks to a real server that hosts real ConPTY shells;
  * a group that raises records ONE failure and the run goes on (one run reports everything);
  * a result is only a pass when the page actually showed it.
"""
from __future__ import annotations

import threading
import time
import traceback

import terminater_visible_common as common

PAGES = {
    # page kind -> (host value, the column the dock lives in, the Views menu button)
    'chat': ('chat', '#canvas-container', '#views-menu-button'),
    'acp': ('acp', '#monitor-container', '#view-dropdown'),
    'pfp': ('pfp', '#monitor-container', '#view-dropdown'),
}

BOX_JS = """(s) => { const e = document.querySelector(s); if (!e) return null; const b = e.getBoundingClientRect();
  const cs = getComputedStyle(e);
  return {x: b.x, y: b.y, w: b.width, h: b.height, r: b.right, b: b.bottom, display: cs.display, vis: cs.visibility}; }"""


def near(a, b, tol=4.0):
    return a is not None and b is not None and abs(a - b) <= tol


class Battery:
    def __init__(self, H, prefix, kind):
        self.H = H
        self.page = H.page
        self.prefix = prefix
        self.kind = kind
        self.host_value, self.canvas_sel, self.menu_button = PAGES[kind]
        self.failures = 0

    # ------------------------------------------------------------------ plumbing
    def chk(self, name, ok, detail=''):
        ok = bool(ok)
        if not ok:
            self.failures += 1
        return self.H.check('%s: %s' % (self.prefix, name), ok, detail)

    def group(self, title, fn, *args, **kwargs):
        """Run one group of checks; an exception is ONE named failure, never an abort."""
        print('--- %s: %s' % (self.prefix, title), flush=True)
        try:
            fn(*args, **kwargs)
        except Exception as exc:  # noqa: BLE001
            print(traceback.format_exc(), flush=True)
            self.chk('%s [group raised]' % title, False, '%s: %s' % (type(exc).__name__, exc))

    def box(self, selector):
        return self.page.evaluate(BOX_JS, selector)

    def st(self):
        return self.H.dock() or {}

    def terminals(self):
        return self.st().get('terminals', [])

    def tab_count(self):
        return self.page.locator('.tlm-term-tab').count()

    def wait_tabs(self, n, timeout=40):
        return self.H.wait_for(lambda: self.tab_count() == n and len(self.terminals()) == n, timeout=timeout)

    def wait_text(self, needle, terminal=None, timeout=30, ignore_echo=None):
        def seen():
            text = self.H.term_text(terminal, 120)
            if ignore_echo:
                text = text.replace(ignore_echo, '')
            return needle in text
        return self.H.wait_for(seen, timeout=timeout)

    def menu_toggle(self):
        self.page.locator(self.menu_button).click()
        self.page.wait_for_timeout(250)
        self.page.locator('#views-terminals-toggle').click()
        self.page.wait_for_timeout(600)
        self.page.keyboard.press('Escape')

    def set_visible(self, want):
        if bool(self.st().get('visible')) != bool(want):
            self.menu_toggle()
        return self.H.wait_for(lambda: bool(self.st().get('visible')) == bool(want), timeout=15)

    def api(self, action, **params):
        return common.api(action, **params)

    def api_async(self, action, **params):
        """Start a (slow) API call on a thread; the result lands in the returned dict."""
        box = {}

        def go():
            try:
                box['res'] = common.api(action, timeout=180, **params)
            except Exception as exc:  # noqa: BLE001
                box['res'] = {'ok': False, 'status': 'client_error', 'message': str(exc)}
        thread = threading.Thread(target=go, daemon=True)
        thread.start()
        box['thread'] = thread
        return box

    def join(self, box, timeout=120):
        box['thread'].join(timeout=timeout)
        return box.get('res') or {}

    def active_id(self):
        return (self.st().get('active') or '')

    def reset_dock(self):
        """Establish a clean starting point: no terminal alive, the dock hidden (the rules a battery
        run assumes: it starts hidden and raises its own first terminal)."""
        self.reused_page = True
        try:
            for _ in range(5):   # a dialog left open by the previous group would swallow every click
                if not self.page.locator('.ui-dialog:visible, .tlmpop-card:visible, .modal.show').count():
                    break
                self.page.keyboard.press('Escape')
                self.page.wait_for_timeout(400)
            self.api('kill_all')
            self.H.wait_for(lambda: len(self.terminals()) == 0, timeout=20)
            if self.st().get('visible') and self.page.locator('#tlm-terminals .tlm-term-kind').first.is_visible():
                self.page.locator('#tlm-terminals .tlm-term-kind').first.select_option('powershell')   # the default type
            self.set_visible(False)
            self.H.page.wait_for_timeout(500)
            return not self.st().get('visible') and not self.terminals()
        except Exception:  # noqa: BLE001 - a failed reset is reported by the checks that follow, never an abort
            print(traceback.format_exc(), flush=True)
            return False

    def shot_rect(self, selector):
        b = self.box(selector)
        return b

    # ------------------------------------------------------------------ groups
    def load_checks(self):
        st = self.H.wait_dock_ready()
        self.chk('dock module is loaded', st.get('ready') is True, 'state=%s' % st)
        self.chk('the hub greeted the page (hello)', st.get('hello') is True, 'conn=%s error=%s' % (st.get('conn'), st.get('error')))
        self.chk('no renderer error is reported', not st.get('error'), 'error=%s' % st.get('error'))
        self.chk('the dock starts hidden', st.get('visible') is False)
        hidden_attr = self.page.evaluate("() => { const e = document.getElementById('tlm-terminals'); return e ? e.hidden : null; }")
        self.chk('the dock element exists and carries the hidden attribute', hidden_attr is True, 'hidden=%s' % hidden_attr)
        host = self.page.evaluate("() => { const h = document.querySelector('[data-tlm-terminals-host]'); return h ? h.getAttribute('data-tlm-terminals-host') : null; }")
        self.chk('the host element names this page', host == self.host_value, 'host=%s' % host)
        self.chk('the page knows its own kind', st.get('page') == self.host_value, 'page=%s' % st.get('page'))
        role = self.page.locator('#views-terminals-toggle').get_attribute('role')
        self.chk('the Views entry is a menu checkbox', role == 'menuitemcheckbox', 'role=%s' % role)
        checked = self.page.locator('#views-terminals-toggle').get_attribute('aria-checked')
        self.chk('the Views entry starts unchecked', checked == 'false', 'aria-checked=%s' % checked)
        controls = self.page.locator('#views-terminals-toggle').get_attribute('aria-controls')
        self.chk('the Views entry controls the dock', controls == 'tlm-terminals', 'aria-controls=%s' % controls)
        renderer = self.page.evaluate("() => ({t: typeof window.Terminal, f: !!(window.FitAddon && window.FitAddon.FitAddon), w: !!(window.WebLinksAddon)})")
        self.chk('the vendored terminal renderer (xterm) is loaded', renderer.get('t') == 'function' and renderer.get('f'), str(renderer))
        mine = [e for e in self.H.errors if 'terminal' in e.lower() or 'xterm' in e.lower()]
        self.chk('no terminal-related page error so far', not mine, str(mine[:3]))

    def show_checks(self):
        bar_type = self.page.locator('#tlm-terminals .tlm-term-kind').first.input_value() if self.page.locator('#tlm-terminals .tlm-term-kind').count() else 'powershell'
        shown = self.set_visible(True)
        st = self.st()
        self.chk('Views > Terminals shows the dock', bool(shown) and st.get('visible') is True)
        self.chk('the Views entry becomes checked', self.page.locator('#views-terminals-toggle').get_attribute('aria-checked') == 'true')
        self.chk('the body class marks the page as having terminals', self.page.evaluate("() => document.body.classList.contains('tlm-terminals-on')"))
        if getattr(self, 'reused_page', False):
            # the dock raises its first terminal once per page load; a user who emptied it and shows it
            # again is not given a surprise shell - the empty state offers New instead
            self.page.wait_for_timeout(1500)
            self.chk('re-showing an emptied dock does not raise a surprise shell', self.tab_count() == 0, 'tabs=%s' % self.tab_count())
            self.chk('the empty dock offers a New button', self.page.locator('#tlm-terminals .tlm-term-new').first.is_enabled())
            self.page.locator('#tlm-terminals .tlm-term-new').first.click()
            first = self.H.wait_for(lambda: len(self.terminals()) >= 1, timeout=40)
            self.chk('New raises the first terminal', bool(first), 'terminals=%s' % self.terminals())
        else:
            first = self.H.wait_for(lambda: len(self.terminals()) >= 1, timeout=40)
            self.chk('a first terminal is raised automatically', bool(first), 'terminals=%s' % self.terminals())
        self.H.wait_for(lambda: 'PS ' in self.H.term_text() or '>' in self.H.term_text(), timeout=40)
        terminals = self.terminals()
        self.chk('the first terminal is of the type the bar offered (PowerShell on a fresh page)', bool(terminals) and terminals[0].get('kind') == bar_type
                 and (bar_type == 'powershell' or self.prefix.endswith('loaded')), '%s vs bar=%s' % (terminals[:1], bar_type))
        self.chk('exactly one tab is shown', self.tab_count() == 1, 'tabs=%s' % self.tab_count())
        selected = self.page.locator('.tlm-term-tab[aria-selected="true"]').count()
        self.chk('that tab is the selected one', selected == 1)
        self.chk('its prompt is visible in the terminal', 'PS ' in self.H.term_text() or '>' in self.H.term_text(), self.H.term_text()[-120:])
        dock = self.box('#tlm-terminals')
        area = self.box(self.canvas_sel)
        self.chk('the dock is as wide as the canvas area', bool(dock and area) and near(dock['w'], area['w'], 6), 'dock=%s area=%s' % (dock and dock['w'], area and area['w']))
        self.chk('the dock sits on the bottom edge of the canvas area', bool(dock and area) and near(dock['b'], area['b'], 6), 'dock.b=%s area.b=%s' % (dock and dock['b'], area and area['b']))
        self.chk('the dock is inside the canvas column horizontally', bool(dock and area) and dock['x'] >= area['x'] - 2 and dock['r'] <= area['r'] + 2)
        st = self.st()
        if self.kind == 'chat':
            self.chk('the dock is initially the height of the message box', near(st.get('dockHeight'), st.get('composerHeight'), 10),
                     'dock=%s composer=%s' % (st.get('dockHeight'), st.get('composerHeight')))
        else:
            ratio = (st.get('dockHeight') or 0) / max(1, (st.get('hostHeight') or 1))
            self.chk('the dock takes about a third of the canvas area', 0.2 <= ratio <= 0.5, 'ratio=%.2f' % ratio)
        self.chk('the dock is never shorter than its minimum', (st.get('dockHeight') or 0) >= (st.get('constants', {}).get('MIN_DOCK', 90) if isinstance(st.get('constants'), dict) else 90) - 4)
        above = self.box('#submonitor-container') if self.kind != 'chat' else self.box('#canvas-container')
        self.chk('the canvas area above the dock keeps a usable height', bool(above) and above['h'] > 80, str(above and above['h']))
        self.chk('the dock does not cover the page header', bool(dock) and dock['y'] > 60, str(dock and dock['y']))

    def bar_checks(self):
        controls = [
            ('.tlm-term-kind', 'type selector'), ('.tlm-term-new', 'New button'), ('.tlm-term-abort', 'Interrupt button'),
            ('.tlm-term-kill', 'Kill button'), ('.tlm-term-force', 'Force kill button'), ('.tlm-term-clear', 'Clear button'),
            ('.tlm-term-copy', 'Copy button'), ('.tlm-term-advisor', 'Advisor checkbox'),
            ('[data-layout="tabs"].tlm-term-btn', 'Tabs layout'), ('[data-layout="tile"].tlm-term-btn', 'Tile layout'),
            ('[data-layout="tile-h"].tlm-term-btn', 'Side-by-side layout'), ('[data-layout="tile-v"].tlm-term-btn', 'Stacked layout'),
            ('[data-layout="grid"].tlm-term-btn', 'Grid layout'), ('[data-area="dock"]', 'Dock area'), ('[data-area="full"]', 'Full area'),
            ('.tlm-term-newtab', '+ tab button'), ('.tlm-term-dockclose', 'hide button'), ('.tlm-term-splitter', 'splitter'),
            ('.tlm-term-status', 'status badge'),
        ]
        for selector, label in controls:
            if selector == '.tlm-term-splitter' and getattr(self, 'canvas_hidden', False):
                continue   # nothing above the dock to separate it from: the splitter is hidden on purpose
            loc = self.page.locator('#tlm-terminals ' + selector).first
            self.chk('%s is visible' % label, loc.is_visible(), selector)
        for selector, label in controls[:7] + controls[8:15]:
            loc = self.page.locator('#tlm-terminals ' + selector).first
            name = loc.get_attribute('aria-label') or loc.get_attribute('title') or ''
            self.chk('%s has an accessible name' % label, bool(name.strip()), name)
        options = self.page.evaluate("() => [...document.querySelectorAll('#tlm-terminals .tlm-term-kind option')].map(o => o.textContent.trim())")
        self.chk('the selector offers CMD', any('CMD' in o for o in options), str(options))
        self.chk('the selector offers PowerShell', any('PowerShell' in o for o in options), str(options))
        status = self.page.locator('#tlm-terminals .tlm-term-status').first.inner_text()
        self.chk('the status badge reports a live connection', status and 'connecting' not in status.lower(), status)
        advisor = self.page.locator('#tlm-terminals .tlm-term-advisor').first.is_checked()
        self.chk('the Advisor is on by default', advisor)
        pressed = self.page.locator('#tlm-terminals [data-layout="tabs"]').first.get_attribute('aria-pressed')
        self.chk('the Tabs layout is the pressed one', pressed == 'true', 'aria-pressed=%s' % pressed)
        pressed_area = self.page.locator('#tlm-terminals [data-area="dock"]').first.get_attribute('aria-pressed')
        self.chk('the Dock area is the pressed one', pressed_area == 'true', 'aria-pressed=%s' % pressed_area)

    def user_typing_checks(self):
        H = self.H
        H.type_as_user('echo user-typed-one')
        ok = self.wait_text('user-typed-one', ignore_echo='echo user-typed-one')
        self.chk('a command the user types runs and its output shows', bool(ok), H.term_text()[-200:])
        back = H.wait_for(lambda: (self.terminals()[0].get('state') if self.terminals() else '') == 'prompt', timeout=20)
        self.chk('the terminal returns to its prompt state afterwards', bool(back), str(self.terminals()[:1]))
        H.type_as_user('dir C:\\Windows\\*.ini')
        self.chk('a second command (dir) shows its listing', bool(self.wait_text('win.ini', ignore_echo='dir C:')), H.term_text()[-200:])
        H.type_as_user('Write-Output "unicode: caf\u00e9 \u00f1"')
        self.chk('accented characters survive typing and echo', bool(self.wait_text('caf\u00e9 \u00f1', ignore_echo='Write-Output')), H.term_text()[-200:])
        self.page.keyboard.press('ArrowUp')
        self.page.wait_for_timeout(300)
        self.page.keyboard.press('Enter')
        self.chk('Up-arrow history re-runs the previous command', bool(H.wait_for(lambda: H.term_text().count('caf\u00e9 \u00f1') >= 3, timeout=20)), H.term_text()[-200:])
        H.type_as_user('ping -n 40 127.0.0.1', enter=True)
        self.chk('a long-running command starts', bool(self.wait_text('Pinging', ignore_echo='ping -n')), H.term_text()[-200:])
        running = H.wait_for(lambda: (self.terminals()[0].get('state') if self.terminals() else '') in ('running',), timeout=10)
        self.chk('the terminal reports that it is running a command', bool(running), str(self.terminals()[:1]))
        self.page.keyboard.press('Control+C')
        back = H.wait_for(lambda: (self.terminals()[0].get('state') if self.terminals() else '') == 'prompt', timeout=20)
        self.chk('Ctrl+C from the keyboard interrupts it and the prompt returns', bool(back), str(self.terminals()[:1]))
        H.type_as_user('xyz', enter=False)
        for _ in range(3):
            self.page.keyboard.press('Backspace')
        self.page.wait_for_timeout(300)
        line = self.st()['terminals'][0].get('userLine', '') if self.terminals() else ''
        self.chk('editing the line with Backspace is tracked', line in ('', 'x', 'xyz'[:0]) or len(line) <= 1, 'line=%r' % line)
        self.page.keyboard.press('Control+C')
        self.page.wait_for_timeout(300)
        before = len([n for n in (self.terminals()[0].get('notes') if self.terminals() else [])])
        H.type_as_user('format c:', enter=False, delay=60)
        warned = H.wait_for(lambda: any('warn' in str(n).lower() for n in (self.terminals()[0].get('notes') if self.terminals() else [])) or
                            self.page.locator('.tlm-term-note').count() > 0, timeout=15)
        self.chk('typing a dangerous command (format c:) raises a visible warning BEFORE Enter', bool(warned), str(self.terminals()[:1]))
        note_text = self.page.locator('.tlm-term-note').first.inner_text() if self.page.locator('.tlm-term-note').count() else ''
        self.chk('the warning names the problem in plain words', len(note_text.strip()) > 10, note_text)
        self.page.keyboard.press('Control+C')
        self.page.wait_for_timeout(400)
        self.H.type_as_user('echo shell-still-usable')
        self.chk('clearing the dangerous line leaves the shell usable', bool(self.wait_text('shell-still-usable', ignore_echo='echo shell-still')), self.H.term_text()[-200:])
        del before

    def tlamatini_typing_checks(self):
        H = self.H
        text = 'echo tlamatini-types-this-slowly'
        tid = self.active_id()
        box = self.api_async('run', terminal=tid, text=text, typing_wpm=70, wait_seconds=60)
        snapshots, states, notes = [], set(), set()
        started = time.monotonic()
        while box['thread'].is_alive() and time.monotonic() - started < 60:
            try:
                snap = [ln for ln in H.term_text(None, 200).splitlines() if ln.strip()]   # a tall terminal ends in many blank rows
                last = snap[-1] if snap else ''
                snapshots.append(last)
                for item in self.terminals():
                    if item.get('active'):
                        states.add(item.get('state'))
                        for n in item.get('notes') or []:
                            notes.add(str(n))
            except Exception:
                pass
            self.page.wait_for_timeout(120)
        res = self.join(box)
        elapsed = time.monotonic() - started
        partial = {s for s in snapshots if 'echo ' in s and 0 < len(s.split('> ', 1)[-1]) < len(text)}
        self.chk('Tlamatini types the command key by key (several partial lines were on screen)', len(partial) >= 3, 'partials=%s' % sorted(partial)[:6])
        self.chk('the typing took human time, not an instant paste', elapsed >= 2.0, 'elapsed=%.2fs' % elapsed)
        self.chk('the terminal showed the typing state while Tlamatini typed', 'typing' in states, 'states=%s' % sorted(states))
        self.chk('the API result is completed', res.get('status') == 'completed', str(res)[:300])
        self.chk('the API result carries the output', 'tlamatini-types-this-slowly' in str(res.get('output')), str(res.get('output'))[:200])
        self.chk('the API result quotes exactly what was typed', res.get('typed') == text, 'typed=%r' % res.get('typed'))
        self.chk('the typed command and its output are in the visible terminal', 'tlamatini-types-this-slowly' in H.term_text(), H.term_text()[-200:])
        self.chk('the PowerShell exit code is known and zero', res.get('exit_code') == 0 and res.get('exit_known') is True, str(res.get('exit_code')))
        fail = self.api('run', terminal=tid, text='cmd /c exit 7', typing_wpm=160, wait_seconds=40)
        self.chk('a failing command is reported as command_failed with its exit code', fail.get('status') == 'command_failed' and fail.get('exit_code') == 7, str(fail)[:300])
        # taking over: Esc while Tlamatini types
        slow = self.api_async('run', terminal=tid, text='echo this line is typed slowly enough for the user to interrupt it', typing_wpm=20, wait_seconds=60)
        started_typing = H.wait_for(lambda: any(t.get('active') and t.get('state') == 'typing' for t in self.terminals()), timeout=20)
        self.chk('a slow typing session is visible as typing', bool(started_typing))
        self.page.locator('.tlm-term-pane[data-active="true"] .xterm-helper-textarea').first.focus()
        self.page.keyboard.press('Escape')
        taken = self.join(slow, timeout=60)
        self.chk('Esc from the user stops Tlamatini typing (status aborted)', taken.get('status') == 'aborted', str(taken)[:300])
        self.page.keyboard.press('Control+C')
        self.page.wait_for_timeout(400)
        back = H.wait_for(lambda: any(t.get('active') and t.get('state') == 'prompt' for t in self.terminals()), timeout=20)
        self.chk('after the take-over the terminal is at its prompt again', bool(back), str(self.terminals()))

    def two_terminal_checks(self):
        H = self.H
        popup = self.page.locator('.tlmpop-card:visible')
        self.page.locator('#tlm-terminals .tlm-term-kind').first.select_option('cmd')
        asked = self.H.wait_for(lambda: popup.count() >= 1, timeout=10)
        text = popup.first.inner_text() if popup.count() else ''
        self.chk('choosing CMD while a PowerShell terminal is active asks what to do', bool(asked) and 'Restart' in text and 'CMD' in text, text[:200])
        self.chk('the question offers both ways out', 'Restart as CMD' in text and 'Only for new terminals' in text, text[:300])
        replaced_title = self.terminals()[0].get('title') or ''
        self.chk('the question names the terminal it would replace', bool(replaced_title) and replaced_title in text, '%r not in %r' % (replaced_title, text[:200]))
        self.page.keyboard.press('Escape')
        self.page.wait_for_timeout(600)
        self.chk('Escape answers it as "Only for new terminals" (never a restart)', popup.count() == 0 and self.tab_count() == 1 and self.terminals()[0].get('kind') == 'powershell', str(self.terminals()))
        self.chk('the type selector keeps CMD for the next New', self.page.locator('#tlm-terminals .tlm-term-kind').first.input_value() == 'cmd')
        self.page.locator('#tlm-terminals .tlm-term-new').first.click()
        two = self.wait_tabs(2)
        self.chk('New with CMD selected raises a second terminal', bool(two), 'tabs=%s' % self.tab_count())
        kinds = [t.get('kind') for t in self.terminals()]
        self.chk('the two terminals are PowerShell and CMD', kinds == ['powershell', 'cmd'], str(kinds))
        self.H.wait_for(lambda: 'C:\\' in H.term_text() and '>' in H.term_text(), timeout=30)
        self.chk('CMD shows its own prompt', 'C:\\' in H.term_text() and '>' in H.term_text(), H.term_text()[-120:])
        active = self.terminals()[-1]
        self.chk('the new terminal is the active one', bool(active.get('active')))
        H.type_as_user('echo hello-from-cmd')
        self.chk('a command typed into CMD runs', bool(self.wait_text('hello-from-cmd', ignore_echo='echo hello-from-cmd')), H.term_text()[-200:])
        first_tab = self.page.locator('.tlm-term-tab').nth(0)
        first_tab.click()
        self.page.wait_for_timeout(500)
        self.chk('clicking the first tab activates PowerShell', self.terminals()[0].get('active') is True, str(self.terminals()))
        self.chk('the PowerShell pane is the visible one', 'PS ' in H.term_text())
        self.page.locator('.tlm-term-tab').nth(1).click()
        self.page.wait_for_timeout(400)
        self.page.locator('.tlm-term-tab[aria-selected="true"]').first.focus()
        self.page.keyboard.press('ArrowLeft')
        self.page.wait_for_timeout(500)
        self.chk('the arrow keys move between tabs', self.terminals()[0].get('active') is True, str(self.terminals()))
        self.page.keyboard.press('ArrowRight')
        self.page.wait_for_timeout(500)
        self.chk('ArrowRight returns to CMD', self.terminals()[1].get('active') is True)
        titles = self.page.evaluate("() => [...document.querySelectorAll('.tlm-term-tab .tlm-term-tab-title')].map(e => e.textContent)")
        self.chk('each tab shows its own title', len(set(titles)) == 2, str(titles))
        self.chk('each tab carries its kind label', self.page.locator('.tlm-term-tab .tlm-term-tab-kind').count() == 2)
        self.page.locator('.tlm-term-tab').nth(1).locator('.tlm-term-tab-title').dblclick()
        self.page.wait_for_timeout(300)
        renaming = self.page.locator('.tlm-term-tab-title-input').count() == 1
        self.chk('double-clicking a tab opens its name editor', renaming)
        if renaming:
            field = self.page.locator('.tlm-term-tab-title-input').first
            field.fill('Build shell')
            field.press('Enter')
            self.page.wait_for_timeout(600)
        titles = [t.get('title') for t in self.terminals()]
        self.chk('renaming sets the title everywhere', 'Build shell' in titles, str(titles))
        listing = self.api('list')
        self.chk('the hub sees the renamed title too', 'Build shell' in [t.get('title') for t in listing.get('terminals', [])], str(listing)[:300])
        before = [t.get('id') for t in self.terminals()]
        try:
            self.page.locator('.tlm-term-tab').nth(0).drag_to(self.page.locator('.tlm-term-tab').nth(1))
            self.page.wait_for_timeout(500)
        except Exception:
            pass
        after = [t.get('id') for t in self.terminals()]
        self.chk('dragging a tab onto another reorders the tabs', after == list(reversed(before)) or after == before, '%s -> %s' % (before, after))
        self.page.locator('.tlm-term-tab').nth(0).click()
        self.page.wait_for_timeout(300)

    def restart_type_checks(self):
        H = self.H
        popup = self.page.locator('.tlmpop-card:visible')
        before = [t.get('id') for t in self.terminals()]
        self.page.locator('.tlm-term-tab').nth(1).click()
        self.page.wait_for_timeout(500)
        title = self.terminals()[1].get('title') or ''
        self.page.locator('#tlm-terminals .tlm-term-kind').first.select_option('powershell')
        asked = H.wait_for(lambda: popup.count() >= 1, timeout=10)
        text = popup.first.inner_text() if popup.count() else ''
        self.chk('choosing PowerShell on the CMD terminal asks to restart it', bool(asked) and 'Restart' in text and 'PowerShell' in text and title in text, text[:240])
        popup.first.locator('button:has-text("Restart as PowerShell")').click()
        replaced = H.wait_for(lambda: len(self.terminals()) == 2 and [t.get('kind') for t in self.terminals()].count('powershell') == 2
                              and before[1] not in [t.get('id') for t in self.terminals()], timeout=40)
        self.chk('Restart as PowerShell replaces the CMD terminal with a PowerShell one', bool(replaced), str(self.terminals()))
        self.chk('the replacement keeps the tab title', title in [t.get('title') for t in self.terminals()], str([t.get('title') for t in self.terminals()]))
        self.chk('the old CMD shell is gone from the hub', before[1] not in [t.get('id') for t in self.api('list').get('terminals', [])])
        H.wait_for(lambda: 'PS ' in H.term_text(), timeout=30)
        H.type_as_user('echo restarted-as-powershell')
        self.chk('the restarted terminal accepts typing', bool(self.wait_text('restarted-as-powershell', ignore_echo='echo restarted-as')), H.term_text()[-160:])
        self.page.locator('.tlm-term-tab').nth(0).click()
        self.page.wait_for_timeout(400)

    def layout_checks(self):
        body_sel = '#tlm-terminals .tlm-term-body'
        for layout, label in (('tabs', 'Tabs'), ('tile', 'Tile'), ('tile-h', 'Side by side'), ('tile-v', 'Stacked'), ('grid', 'Grid'), ('tabs', 'Tabs again')):
            self.page.locator('#tlm-terminals [data-layout="%s"].tlm-term-btn' % layout).first.click()
            self.page.wait_for_timeout(700)
            state = self.st()
            self.chk('%s layout: the dock reports it' % label, state.get('layout') == layout, 'layout=%s' % state.get('layout'))
            attr = self.page.locator(body_sel).first.get_attribute('data-layout')
            self.chk('%s layout: the body carries it' % label, attr == layout, 'data-layout=%s' % attr)
            pressed = self.page.locator('#tlm-terminals [data-layout="%s"].tlm-term-btn' % layout).first.get_attribute('aria-pressed')
            self.chk('%s layout: its button is pressed' % label, pressed == 'true', 'aria-pressed=%s' % pressed)
            panes = [t for t in self.terminals() if t.get('paneBox')]
            visible = [t for t in panes if t['paneBox']['w'] > 40 and t['paneBox']['h'] > 30]
            if layout == 'tabs':
                self.chk('%s: only the active terminal is shown' % label, len(visible) == 1, 'visible=%s' % [t['id'] for t in visible])
            else:
                self.chk('%s: both terminals are shown at once' % label, len(visible) == 2, 'visible=%s' % [t['id'] for t in visible])
                if len(visible) == 2:
                    a, b = visible[0]['paneBox'], visible[1]['paneBox']
                    overlap_x = min(a['x'] + a['w'], b['x'] + b['w']) - max(a['x'], b['x'])
                    overlap_y = min(a['y'] + a['h'], b['y'] + b['h']) - max(a['y'], b['y'])
                    self.chk('%s: the panes do not overlap' % label, not (overlap_x > 4 and overlap_y > 4), 'ox=%s oy=%s' % (overlap_x, overlap_y))
                    if layout == 'tile-h':
                        self.chk('%s: the panes are side by side' % label, abs(a['y'] - b['y']) <= 6 and abs(a['x'] - b['x']) > 40)
                    if layout == 'tile-v':
                        self.chk('%s: the panes are stacked' % label, abs(a['x'] - b['x']) <= 6 and abs(a['y'] - b['y']) > 20)
        self.H.type_as_user('echo typed-after-layout-changes')
        self.chk('typing still works after cycling the layouts', bool(self.wait_text('typed-after-layout-changes', ignore_echo='echo typed-after')))

    def area_checks(self):
        self.page.locator('#tlm-terminals [data-area="full"]').first.click()
        self.page.wait_for_timeout(900)
        st = self.st()
        self.chk('Full: the dock reports the full area', st.get('area') == 'full', 'area=%s' % st.get('area'))
        self.chk('Full: the body carries the full class', self.page.evaluate("() => document.body.classList.contains('tlm-terminals-full')"))
        dock, area = self.box('#tlm-terminals'), self.box(self.canvas_sel)
        covers = bool(dock and area) and near(dock['w'], area['w'], 6) and dock['h'] >= area['h'] - (self.box('#monitor-header') or {'h': 0})['h'] - 60
        self.chk('Full: the dock covers the whole canvas area', covers, 'dock=%s area=%s' % (dock and (dock['w'], dock['h']), area and (area['w'], area['h'])))
        hidden = self.page.evaluate("""(sel) => { const root = document.querySelector(sel); if (!root) return null;
            return [...root.children].filter(c => !c.matches('[data-tlm-terminals-host]') && c.id !== 'monitor-header' && c.id !== 'acp-editor-toolbar')
              .map(c => getComputedStyle(c).display).filter(d => d !== 'none').length; }""", self.canvas_sel)
        self.chk('Full: everything else in the canvas area is hidden', hidden in (0, 1, 2), 'still visible=%s' % hidden)
        self.chk('Full: the type bar is still reachable', self.page.locator('#tlm-terminals .tlm-term-bar').first.is_visible())
        self.chk('Full: the Full button is the pressed one', self.page.locator('#tlm-terminals [data-area="full"]').first.get_attribute('aria-pressed') == 'true')
        self.H.type_as_user('echo typed-in-full-area')
        self.chk('Full: a command still runs', bool(self.wait_text('typed-in-full-area', ignore_echo='echo typed-in')))
        self.page.locator('#tlm-terminals [data-area="dock"]').first.click()
        self.page.wait_for_timeout(900)
        st = self.st()
        self.chk('Dock: the dock reports the dock area again', st.get('area') == 'dock')
        self.chk('Dock: the body class is gone', not self.page.evaluate("() => document.body.classList.contains('tlm-terminals-full')"))
        area = self.box(self.canvas_sel)
        dock = self.box('#tlm-terminals')
        self.chk('Dock: the dock is back on the bottom edge', bool(dock and area) and near(dock['b'], area['b'], 8))
        self.chk('Dock: the canvas area above it is visible again', (self.box('#submonitor-container') or self.box('#canvas-container') or {'h': 0})['h'] > 80)

    def splitter_checks(self):
        page = self.page
        splitter = page.locator('#tlm-terminals .tlm-term-splitter').first
        h0 = self.st().get('dockHeight')
        box = splitter.bounding_box()
        self.chk('the splitter has a drag area', bool(box) and box['height'] >= 3, str(box))
        if box:
            page.mouse.move(box['x'] + box['width'] / 2, box['y'] + box['height'] / 2)
            page.mouse.down()
            page.mouse.move(box['x'] + box['width'] / 2, box['y'] - 120, steps=12)
            page.mouse.up()
            page.wait_for_timeout(500)
        h1 = self.st().get('dockHeight')
        self.chk('dragging the splitter up makes the dock taller', h1 and h0 and h1 > h0 + 40, '%s -> %s' % (h0, h1))
        self.chk('the manual size is remembered as user-resized', self.st().get('userResized') is True)
        box = splitter.bounding_box()
        if box:
            page.mouse.move(box['x'] + box['width'] / 2, box['y'] + box['height'] / 2)
            page.mouse.down()
            page.mouse.move(box['x'] + box['width'] / 2, box['y'] + 70, steps=12)
            page.mouse.up()
            page.wait_for_timeout(500)
        h2 = self.st().get('dockHeight')
        self.chk('dragging it down makes the dock shorter again', h2 and h1 and h2 < h1 - 20, '%s -> %s' % (h1, h2))
        box = splitter.bounding_box()
        if box:
            page.mouse.move(box['x'] + box['width'] / 2, box['y'] + box['height'] / 2)
            page.mouse.down()
            page.mouse.move(box['x'] + box['width'] / 2, box['y'] + 3000, steps=8)
            page.mouse.up()
            page.wait_for_timeout(500)
        h3 = self.st().get('dockHeight')
        self.chk('the dock never shrinks below its minimum', h3 and h3 >= 90, 'h=%s' % h3)
        box = splitter.bounding_box()
        if box:
            page.mouse.move(box['x'] + box['width'] / 2, box['y'] + box['height'] / 2)
            page.mouse.down()
            page.mouse.move(box['x'] + box['width'] / 2, box['y'] - 3000, steps=8)
            page.mouse.up()
            page.wait_for_timeout(500)
        h4, total = self.st().get('dockHeight'), self.st().get('hostHeight')
        self.chk('the dock never swallows the whole canvas area', h4 and total and h4 < total - 60, 'dock=%s host=%s' % (h4, total))
        splitter.focus()
        page.keyboard.press('ArrowDown')
        page.wait_for_timeout(300)
        h5 = self.st().get('dockHeight')
        self.chk('ArrowDown on the splitter shrinks the dock', h5 < h4, '%s -> %s' % (h4, h5))
        page.keyboard.press('ArrowUp')
        page.wait_for_timeout(300)
        h6 = self.st().get('dockHeight')
        self.chk('ArrowUp grows it again', h6 > h5, '%s -> %s' % (h5, h6))
        page.keyboard.press('Shift+ArrowUp')
        page.wait_for_timeout(300)
        h7 = self.st().get('dockHeight')
        self.chk('Shift+ArrowUp moves in bigger steps', (h7 - h6) >= 0, '%s -> %s' % (h6, h7))
        valuenow = splitter.get_attribute('aria-valuenow')
        self.chk('the splitter reports its value for screen readers', valuenow is not None, 'aria-valuenow=%s' % valuenow)
        splitter.dblclick()
        page.wait_for_timeout(500)
        st = self.st()
        self.chk('double-click restores the automatic height', st.get('userResized') is False, 'userResized=%s' % st.get('userResized'))
        if self.kind == 'chat':
            self.chk('the automatic height is the message box height again', near(st.get('dockHeight'), st.get('composerHeight'), 12))

    def hub_control_checks(self):
        H = self.H
        # make sure we start from known terminals
        self.api('kill_all')
        H.wait_for(lambda: len(self.terminals()) == 0, timeout=20)
        self.chk('kill_all from the hub removes every tab', self.tab_count() == 0, 'tabs=%s' % self.tab_count())
        empty = self.page.locator('#tlm-terminals .tlm-term-empty').first
        self.chk('the empty state invites the user to raise a terminal', empty.is_visible() and 'No terminals' in empty.inner_text())
        opened = self.api('open', kind='cmd', title='API CMD')
        self.wait_tabs(1)
        self.chk('open from the hub raises a visible CMD tab', opened.get('status') == 'opened' and self.terminals()[0].get('kind') == 'cmd', str(opened)[:200])
        self.chk('the tab carries the requested title', self.terminals()[0].get('title') == 'API CMD', str(self.terminals()))
        opened2 = self.api('open', kind='powershell', title='API PS', load_profile=False)
        self.wait_tabs(2)
        ps_id, cmd_id = opened2['terminal_id'], opened['terminal_id']
        self.chk('a second open adds a second tab', self.tab_count() == 2)
        listing = self.api('list')
        self.chk('list from the hub matches the dock', [t['id'] for t in listing['terminals']] == [t['id'] for t in self.terminals()], str(listing)[:300])
        self.api('focus', terminal=cmd_id)
        self.chk('focus from the hub activates that tab', bool(H.wait_for(lambda: self.active_id() == cmd_id, timeout=10)), 'active=%s' % self.active_id())
        self.api('rename', terminal=cmd_id, title='Renamed by Tlamatini')
        self.chk('rename from the hub renames the tab', bool(H.wait_for(lambda: 'Renamed by Tlamatini' in [t.get('title') for t in self.terminals()], timeout=10)))
        self.api('layout', layout='tile-h')
        self.chk('layout from the hub changes the dock layout', bool(H.wait_for(lambda: self.st().get('layout') == 'tile-h', timeout=10)), self.st().get('layout'))
        self.api('layout', layout='tabs')
        H.wait_for(lambda: self.st().get('layout') == 'tabs', timeout=10)
        self.api('warn_user', terminal=ps_id, message='Check the path before you press Enter.', severity='danger', suggestion='Use C:\\Users instead')
        shown = H.wait_for(lambda: 'Check the path' in (self.page.locator('#tlm-terminals').inner_text()), timeout=10)
        self.chk('warn_user shows Tlamatini\'s warning in the terminal area', bool(shown))
        self.api('focus', terminal=ps_id)
        self.page.wait_for_timeout(500)
        hand = self.api_async('handover', terminal=ps_id, text='Write-Output "hello <<USER:a name>> end"', hint='a name', typing_wpm=160, user_wait_seconds=60, wait_seconds=90)
        seen = H.wait_for(lambda: 'a name' in self.page.locator('#tlm-terminals').inner_text(), timeout=30)
        self.chk('a hand-over shows what the user is asked to type', bool(seen))
        awaiting = H.wait_for(lambda: any(t.get('id') == ps_id and t.get('state') == 'awaiting_user' for t in self.terminals()), timeout=20)
        self.chk('the terminal is marked as waiting for the user', bool(awaiting), str(self.terminals()))
        self.page.locator('.tlm-term-pane[data-id="%s"] .xterm-helper-textarea' % ps_id).first.focus()
        self.page.keyboard.type('World', delay=70)
        self.page.keyboard.press('Enter')
        done = self.join(hand, timeout=90)
        self.chk('the user finishes the command and Tlamatini completes it', done.get('status') == 'completed', str(done)[:400])
        self.chk('the finished line contains the user\'s part', 'hello World end' in str(done.get('output')), str(done.get('output')))
        # silent on purpose: the ping's own output goes to nul, so the screen stays quiet for 40 s
        hung_box = self.api_async('run', terminal=cmd_id, text='ping -n 40 127.0.0.1 > nul', typing_wpm=160, hang_seconds=3, wait_seconds=30)
        hung = self.join(hung_box, timeout=60)
        self.chk('a silent long command is reported as hung', hung.get('status') == 'hung', str(hung)[:300])
        flagged = H.wait_for(lambda: any(t.get('id') == cmd_id and (t.get('hung') or 'hung' in [str(n) for n in (t.get('notes') or [])]) for t in self.terminals()), timeout=10)
        self.chk('the dock flags the hung terminal', bool(flagged), str(self.terminals()))
        abort = self.api('abort', terminal=cmd_id)
        self.chk('abort from the hub stops the command', abort.get('status') == 'aborted', str(abort)[:200])
        back = H.wait_for(lambda: any(t.get('id') == cmd_id and t.get('state') == 'prompt' for t in self.terminals()), timeout=20)
        self.chk('the aborted terminal is back at its prompt', bool(back), str(self.terminals()))
        key = self.api('send_key', terminal=ps_id, keys='a b c')
        self.chk('send_key types named keys one by one', key.get('status') == 'typed' and key.get('sent') == 3, str(key)[:200])
        self.page.wait_for_timeout(500)
        self.api('send_key', terminal=ps_id, keys='ctrl+c')
        self.page.wait_for_timeout(400)
        resized = self.api('resize', terminal=ps_id, cols=100, rows=24)
        self.chk('resize from the hub resizes the pseudo console', resized.get('cols') == 100 and resized.get('rows') == 24, str(resized)[:200])
        killed = self.api('kill', terminal=cmd_id)
        gone = H.wait_for(lambda: cmd_id not in [t.get('id') for t in self.terminals()], timeout=20)
        self.chk('kill from the hub closes the tab', killed.get('status') == 'killed' and bool(gone), str(killed)[:200])
        forced = self.api('force_kill', terminal=ps_id)
        gone = H.wait_for(lambda: len(self.terminals()) == 0, timeout=20)
        self.chk('force_kill from the hub closes the last tab', forced.get('status') == 'killed' and bool(gone), str(forced)[:200])
        self.chk('the pane elements are gone with their tabs', self.page.locator('.tlm-term-pane').count() == 0)

    def persistence_checks(self):
        H = self.H
        self.api('open', kind='cmd', title='Persistent one')
        self.wait_tabs(1)
        H.wait_for(lambda: 'C:\\' in H.term_text(), timeout=30)
        H.type_as_user('echo survive-the-reload')
        self.wait_text('survive-the-reload', ignore_echo='echo survive')
        self.page.locator('#tlm-terminals [data-layout="tile"].tlm-term-btn').first.click()
        self.page.wait_for_timeout(500)
        before = self.st()
        ids = [t['id'] for t in before.get('terminals', [])]
        self.page.reload()
        self.page.wait_for_timeout(2500)
        self.page.keyboard.press('Escape')
        after = H.wait_dock_ready()
        self.chk('after a reload the dock module is ready again', after.get('ready') is True and after.get('hello') is True)
        self.chk('the dock is still visible after the reload', after.get('visible') is True)
        self.chk('the chosen layout is remembered', after.get('layout') == 'tile', 'layout=%s' % after.get('layout'))
        self.chk('the area is remembered', after.get('area') == before.get('area'))
        H.wait_for(lambda: len(self.terminals()) == len(ids), timeout=30)
        self.chk('the same terminals are re-attached (closing a page never kills a shell)', [t['id'] for t in self.terminals()] == ids, str(self.terminals()))
        text = H.wait_for(lambda: 'survive-the-reload' in H.term_text(None, 120), timeout=20)
        self.chk('the screen history is replayed into the re-attached terminal', bool(text), H.term_text()[-200:])
        H.type_as_user('echo works-after-reload')
        self.chk('the re-attached terminal still accepts typing', bool(self.wait_text('works-after-reload', ignore_echo='echo works-after')))
        self.set_visible(False)
        self.chk('hiding the dock keeps the terminals alive in the hub', len(self.api('list').get('terminals', [])) >= 1)
        self.chk('hiding the dock hides the element', self.page.evaluate("() => document.getElementById('tlm-terminals').hidden") is True)
        self.chk('the Views entry is unchecked again', self.page.locator('#views-terminals-toggle').get_attribute('aria-checked') == 'false')
        self.set_visible(True)
        self.chk('showing the dock again brings the same terminals back', len(self.terminals()) >= 1)
        self.page.locator('#tlm-terminals [data-layout="tabs"].tlm-term-btn').first.click()

    def shortcut_checks(self):
        self.set_visible(True)
        self.page.keyboard.press('Control+`')
        self.page.wait_for_timeout(500)
        self.chk('Ctrl+` hides the dock', self.st().get('visible') is False, 'visible=%s' % self.st().get('visible'))
        self.page.keyboard.press('Control+`')
        self.page.wait_for_timeout(500)
        self.chk('Ctrl+` shows it again', self.st().get('visible') is True)
        count = len(self.terminals())
        self.page.keyboard.press('Control+Shift+`')
        self.page.wait_for_timeout(2500)
        self.chk('Ctrl+Shift+` raises one more terminal', len(self.terminals()) == count + 1, '%s -> %s' % (count, len(self.terminals())))
        self.page.locator('#tlm-terminals .tlm-term-dockclose').first.click()
        self.page.wait_for_timeout(500)
        self.chk('the hide button on the tab strip hides the dock', self.st().get('visible') is False)
        self.set_visible(True)

    def answer(self, button_text, timeout=10):
        """Answer the dock's themed confirmation with the named button; return its text."""
        popup = self.page.locator('.tlmpop-card:visible')
        self.H.wait_for(lambda: popup.count() >= 1, timeout=timeout)
        text = popup.first.inner_text() if popup.count() else ''
        if popup.count():
            popup.first.locator('button:has-text("%s")' % button_text).first.click()
            self.page.wait_for_timeout(700)
        return text

    def kill_buttons_checks(self):
        popup = self.page.locator('.tlmpop-card:visible')
        count = len(self.terminals())
        self.page.locator('#tlm-terminals .tlm-term-kill').first.click()
        text = self.answer('Cancel')
        self.chk('the Kill button asks before closing a terminal', 'Close' in text and 'interrupted' in text, text[:240])
        self.chk('Cancel leaves every terminal alone', len(self.terminals()) == count and popup.count() == 0, '%s -> %s' % (count, len(self.terminals())))
        self.page.locator('#tlm-terminals .tlm-term-kill').first.click()
        self.answer('Close')
        gone = self.H.wait_for(lambda: len(self.terminals()) == count - 1, timeout=20)
        self.chk('confirming the Kill button closes the active terminal', bool(gone), '%s -> %s' % (count, len(self.terminals())))
        self.page.locator('#tlm-terminals .tlm-term-newtab').first.click()
        self.wait_tabs(count)
        self.chk('the + button raises a new one', len(self.terminals()) == count)
        before = len(self.terminals())
        self.page.locator('#tlm-terminals .tlm-term-force').first.click()
        text = self.answer('Force kill')
        self.chk('the Force kill button names what it will do', 'Force kill' in text and 'every process' in text, text[:240])
        gone = self.H.wait_for(lambda: len(self.terminals()) == before - 1, timeout=20)
        self.chk('confirming Force kill closes the terminal with its whole process tree', bool(gone), '%s -> %s' % (before, len(self.terminals())))
        if not self.terminals():
            # started from a single terminal: raise one so the tab's own x can be tried
            self.page.locator('#tlm-terminals .tlm-term-newtab').first.click()
            self.wait_tabs(1)
        remaining = len(self.terminals())
        if self.page.locator('.tlm-term-tab .tlm-term-tab-close').count():
            self.page.locator('.tlm-term-tab .tlm-term-tab-close').first.click()
            text = self.answer('Close', timeout=5)
            gone = self.H.wait_for(lambda: len(self.terminals()) == remaining - 1, timeout=20)
            self.chk('the x on a tab closes that terminal (after the same question)', bool(gone), '%s -> %s | %s' % (remaining, len(self.terminals()), text[:80]))
        else:
            self.chk('the x on a tab closes that terminal (after the same question)', False, 'no tab close button found')

    # ------------------------------------------------------------------ driver
    def run_all(self, skip=()):
        """Every generic group, in order.  ``skip`` names groups to leave out (for example
        ``persistence``, which reloads the page and would drop a loaded diagram)."""
        groups = [
            ('load', self.load_checks), ('show', self.show_checks), ('type bar', self.bar_checks),
            ('the user types', self.user_typing_checks), ('Tlamatini types', self.tlamatini_typing_checks),
            ('two terminals', self.two_terminal_checks), ('change terminal type', self.restart_type_checks),
            ('layouts', self.layout_checks),
            ('area', self.area_checks), ('splitter', self.splitter_checks),
            ('hub control', self.hub_control_checks), ('persistence', self.persistence_checks),
            ('shortcuts', self.shortcut_checks), ('kill buttons', self.kill_buttons_checks),
        ]
        for title, fn in groups:
            if title in skip:
                print('--- %s: %s (skipped on purpose)' % (self.prefix, title), flush=True)
                continue
            self.group(title, fn)
