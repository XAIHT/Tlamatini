# Tlamatini Author Banner — Angela López Mendoza
"""Real-template/browser state regressions. Transport responses are deterministic.

Imported by run_menu_state_checks.py in a verified visible foreground console.
The browser must be headed and verified before this suite is released.
No production server, model, account, context or database is modified.
"""
import json
import mimetypes
from pathlib import Path
import unittest
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / 'Tlamatini/agent/static'
BUSY_MENUS = ('open-button', 'save-as-button', 'context-menu-button',
              'skills-menu-button', 'external-menu-button', 'config-menu-button',
              'db-menu-button', 're-connect-button')
TRANSPORT = r"""
window.__menuTransport = {sockets: [], sent: [], throwSend: false};
class FixtureWebSocket {
  static CONNECTING = 0; static OPEN = 1; static CLOSING = 2; static CLOSED = 3;
  constructor(url) { this.url = url; this.readyState = 1;
    window.__menuTransport.sockets.push(this);
    setTimeout(() => this.onopen?.({}), 0); }
  send(text) { if (window.__menuTransport.throwSend) throw Error('Injected transport failure');
    window.__menuTransport.sent.push(JSON.parse(text)); }
  close() { this.readyState = 3; this.onclose?.({code: 1006}); }
  addEventListener(name, callback) { this['on' + name] = callback; }
  removeEventListener() {}
}
window.WebSocket = FixtureWebSocket;
sessionStorage.clear(); localStorage.clear();
localStorage.setItem('tlm_voice_settings', JSON.stringify({mode: 'silent'}));
"""


class MenuBrowserChecks(unittest.TestCase):
    browser = None
    html = ''
    panel_html = ''
    asset_root = STATIC
    mode = 'source'
    artifacts = ROOT / 'Temp/menu-state-tests'
    coverage = []
    snapshots = []
    capture = None

    def setUp(self):
        self.errors = []
        self.requests = []
        self.fail_config_save = False
        self.defer_config_load = False
        self.pending_config_route = None
        self.photographed = set()
        self.context = self.browser.new_context(viewport={'width': 1500, 'height': 1000})
        self.context.add_init_script(TRANSPORT)
        self.context.route('**/*', self.route)
        self.page = self.context.new_page()
        self.page.on('pageerror', lambda error: self.errors.append(str(error)))
        self.cdp = self.context.new_cdp_session(self.page)
        self.cdp.send('Profiler.enable')
        self.cdp.send('Profiler.startPreciseCoverage', {'callCount': True, 'detailed': True})
        self.page.goto('http://tlamatini.test/agent/agent/', wait_until='load')
        self.page.wait_for_function("typeof restoreMenuControlsAfterOperation === 'function' && typeof renderInitialMessages === 'function'")
        self.page.bring_to_front()

    def tearDown(self):
        try:
            self.coverage.append({'test': self.id(), 'mode': self.mode,
                                  'scripts': self.cdp.send('Profiler.takePreciseCoverage')['result']})
            self.snapshots.append({'test': self.id(), 'mode': self.mode,
                                   'state': self.state(), 'errors': self.errors,
                                   'requests': self.requests})
        finally:
            if self.capture:
                self.page.bring_to_front()
                self.page.wait_for_timeout(200)
                self.capture(f'{self.mode}-{self._testMethodName}-final.png')
            (self.artifacts / 'state-snapshots.json').write_text(json.dumps(self.snapshots, indent=2), encoding='utf-8')
            self.context.close()
        self.assertEqual(self.errors, [], 'Browser exceptions must not be hidden by a passing DOM assertion')

    def route(self, route):
        parsed = urlsplit(route.request.url)
        pathname = unquote(parsed.path)
        if parsed.hostname != 'tlamatini.test':
            route.fulfill(status=503, content_type='application/json', body='{"error":"external network disabled in fixture"}')
            return
        if pathname.startswith('/static/'):
            target = (self.asset_root / pathname.removeprefix('/static/')).resolve()
            if not target.is_relative_to(self.asset_root.resolve()) or not target.is_file():
                self.errors.append('Missing static asset: ' + pathname)
                route.fulfill(status=404, body='missing')
            else:
                mime = mimetypes.guess_type(target.name)[0] or 'application/octet-stream'
                body = target.read_bytes()
                if target.name == 'agent_page_state.js' and self._testMethodName == 'test_buffered_restore_before_onload':
                    body += b'\nchatSocket.onmessage({data:JSON.stringify({type:"session-restored",loading:true})});\n'
                route.fulfill(status=200, content_type=mime, body=body)
            return
        if pathname == '/agent/agent/':
            route.fulfill(content_type='text/html', body=self.html)
            return
        if pathname == '/agent/prompt_flow_panel/':
            route.fulfill(content_type='text/html', body=self.panel_html)
            return
        self.requests.append({'path': pathname, 'method': route.request.method,
                              'body': route.request.post_data})
        if self.defer_config_load and pathname.startswith('/agent/load_config_section/'):
            self.pending_config_route = route
            return
        data = {'success': True, 'apps': [], 'models': [], 'agents': [], 'skills': [],
                'tools': [], 'servers': [], 'categories': [], 'fields': [], 'values': {},
                'runtime': {}, 'results': [], 'installed': True, 'status': 'ok'}
        if pathname == '/agent/pick_context_directory/':
            data = {'success': True, 'path': 'C:/Tlamatini/Temp/menu-fixture'}
        if pathname == '/agent/load_config_section/models/':
            data = {'success': True, 'values': {'fixture_model': 'original'},
                    'fields': [{'key': 'fixture_model', 'label': 'Fixture model',
                                'group': 'Fixture', 'kind': 'text', 'optional': False}]}
        if pathname == '/agent/save_config_models/' and self.fail_config_save:
            route.fulfill(status=500, content_type='application/json',
                          body='{"success":false,"error":"Injected save failure"}')
            return
        route.fulfill(content_type='application/json', body=json.dumps(data))

    def emit(self, data):
        self.page.evaluate('(data) => chatSocket.onmessage({data: JSON.stringify(data)})', data)

    def message(self, text):
        self.emit({'username': 'Tlamatini', 'message': text})

    def state(self):
        if self.page.locator('#pmt-play').count():
            return self.page.evaluate('''() => ({panel: true,
                state: document.getElementById('pmt-run-state').textContent,
                playDisabled: document.getElementById('pmt-play').disabled,
                pauseDisabled: document.getElementById('pmt-pause').disabled,
                stopDisabled: document.getElementById('pmt-stop').disabled})''')
        return self.page.evaluate('''() => ({
          busy: inLongOperation, loading: lapseLoadingContext, cancelled: userCancelledRun,
          title: titleBusyPrefix, spinner: document.querySelectorAll('#wait-spinner').length,
          readonly: chatInput.readOnly, inputDisabled: chatInput.disabled,
          submit: chatSubmitButton.textContent, submitDisabled: chatSubmitButton.disabled,
          reconnect: reConnectEnabled, context: contextEnabled,
          menus: Object.fromEntries([...document.querySelectorAll('#menu-editor > li > a')].map(e =>
            [e.id, {toggle: e.getAttribute('data-bs-toggle'), disabled: e.classList.contains('disabled'),
              pointer: e.style.pointerEvents, opacity: e.style.opacity}])),
          openIn: getComputedStyle(openInDropdownItem).display,
          clearContext: getComputedStyle(clearContextButton).display
        })''')

    def assert_busy(self, loading=False):
        state = self.state()
        self.assertTrue(state['busy'])
        self.assertEqual(state['loading'], loading)
        self.assertEqual(state['spinner'], 1)
        self.assertTrue(self.page.locator('#wait-spinner').is_visible())
        self.assertEqual(state['title'], '⏳ ')
        self.assertTrue(state['readonly'])
        self.assertEqual(state['submit'], 'Cancel')
        self.assertFalse(state['submitDisabled'])
        for name in BUSY_MENUS:
            with self.subTest(menu=name):
                self.assertTrue(state['menus'][name]['disabled'])
                self.assertEqual(state['menus'][name]['pointer'], 'none')
                self.assertIsNone(state['menus'][name]['toggle'])
        self.assertFalse(state['menus']['panels-menu-button']['disabled'])
        self.assertEqual(state['menus']['panels-menu-button']['toggle'], 'dropdown')
        self.assertFalse(state['menus']['about-menu-button']['disabled'])
        self.assertEqual(state['openIn'], 'none')
        label = 'loading' if loading else 'invoking'
        if self.capture and label not in self.photographed:
            self.photographed.add(label)
            self.page.bring_to_front()
            self.page.wait_for_timeout(200)
            self.capture(f'{self.mode}-{self._testMethodName}-{label}.png')

    def assert_idle(self):
        state = self.state()
        self.assertFalse(state['busy'])
        self.assertFalse(state['loading'])
        self.assertEqual(state['spinner'], 0)
        self.assertEqual(state['title'], '')
        self.assertFalse(state['readonly'])
        self.assertEqual(state['submit'], 'Send')
        for name in BUSY_MENUS:
            with self.subTest(menu=name):
                self.assertFalse(state['menus'][name]['disabled'])
                self.assertNotEqual(state['menus'][name]['pointer'], 'none')
                expected = 'dropdown' if name.endswith('-menu-button') else None
                self.assertEqual(state['menus'][name]['toggle'], expected)

    def busy(self, context=False):
        self.message('Your agent is loading the context.' if context else 'Your request is being processed by Tlamatini.')

    def finish(self):
        self.message('Ready. The operation completed successfully.')

    def test_menu_hierarchy_and_real_dialog_handlers(self):
        self.assert_idle()
        self.assertEqual(self.page.locator('#panels-menu-button').inner_text(), 'Panels')
        self.assertEqual(self.page.locator('#mcps-menu-button, #agents-menu-button').count(), 0)
        for entry in ('enable-mcps', 'enable-agents'):
            self.assertEqual(self.page.locator('#' + entry).evaluate("e => e.closest('ul').getAttribute('aria-labelledby')"), 'config-menu-button')
            self.page.locator('#config-menu-button').click()
            self.page.locator('#' + entry).click()
            dialog = self.page.locator('.ui-dialog:visible').last
            self.assertTrue(dialog.is_visible())
            self.page.mouse.click(5, 200)
            self.assertTrue(dialog.is_visible(), 'Outside click must not dismiss configuration')
            self.page.keyboard.press('Escape')
            self.page.wait_for_function("!document.querySelector('.ui-dialog:not([style*=\"display: none\"])')")
        self.assert_idle()

    def test_context_loading_progress_welcome_and_ready(self):
        self.emit({'type': 'session-restored', 'loading': True,
                   'context_path': 'C:/Tlamatini/Temp/menu-fixture', 'context_type': 'directory'})
        self.assert_busy(loading=True)
        for text in ('Welcome back, session and context restored.', 'Welcome back, session restored.'):
            self.message(text)
            self.assert_busy(loading=True)
        self.busy(context=True)
        self.assert_busy(loading=True)
        self.finish()
        self.assert_idle()

    def test_context_confirmation_cannot_reopen_open_in_while_busy(self):
        self.page.evaluate("installedApps = [{id:'explorer', name:'Explorer', available:true}]; renderOpenInMenu()")
        self.busy(context=True)
        self.emit({'type': 'context-path-set', 'context_path': 'C:/Tlamatini/Temp/menu-fixture', 'context_type': 'directory'})
        self.assert_busy(loading=True)
        self.finish()
        self.assert_idle()
        self.assertNotEqual(self.state()['openIn'], 'none')

    def test_duplicate_busy_and_history_render_preserve_one_spinner(self):
        self.busy(context=True)
        for _ in range(3):
            self.busy(context=True)
            self.page.evaluate("renderInitialMessages([{username:'Tlamatini',message:'Old final answer'}, {username:'Tlamatini',message:'Your request is being processed by Tlamatini.'}])")
            self.assert_busy(loading=True)
        self.page.evaluate('window.onload()')
        self.assert_busy(loading=True)
        self.finish()
        self.assert_idle()

    def test_invocation_progress_self_healing_and_completion(self):
        self.page.locator('#chat-message-input').fill('Deterministic menu test')
        self.page.locator('#chat-message-submit').click()
        self.assertTrue(self.page.evaluate("__menuTransport.sent.some(x => x.message === 'Deterministic menu test')"))
        self.busy()
        for text in ('🔁 Tactic #1: retrying', "Tactic 'fallback': continuing the run", 'Referenced rephrase: fixture'):
            self.message(text)
            self.assert_busy()
        self.emit({'username': 'ping', 'message': ''})
        self.emit({'type': 'context-gauge', 'detail': {}})
        self.assert_busy()
        self.finish()
        self.assert_idle()

    def test_configuration_cannot_open_through_direct_handlers_while_busy(self):
        for loading in (False, True):
            self.busy(context=loading)
            for handler in ('OpenMcpsDialog', 'OpenAgentsDialog', 'OpenConfigModelsDialog', 'OpenConfigUrlsDialog', 'OpenOmissionsDialog'):
                with self.subTest(handler=handler, loading=loading):
                    self.page.evaluate('(name) => window[name]({preventDefault(){}})', handler)
                    self.assertEqual(self.page.locator('.ui-dialog:visible').count(), 0)
                    self.assert_busy(loading=loading)
            self.finish()

    def test_cancel_dialog_dismiss_and_confirm_then_late_progress(self):
        self.busy(context=True)
        self.page.locator('#chat-message-submit').click()
        self.page.keyboard.press('Escape')
        self.assert_busy(loading=True)
        self.page.locator('#chat-message-submit').click()
        self.page.locator('.ui-dialog:visible button').filter(has_text='Continue').click()
        self.page.wait_for_timeout(350)
        self.assertTrue(self.page.evaluate("__menuTransport.sent.some(x => x.type === 'cancel-current')"))
        self.assert_idle()
        self.message('🔁 Tactic #2: stale cancelled operation')
        self.assert_idle()
        self.page.locator('#chat-message-input').fill('Next operation')
        self.page.locator('#chat-message-submit').click()
        self.busy()
        self.assert_busy()
        self.assertFalse(self.state()['cancelled'])

    def test_disconnection_during_loading_leaves_reconnect_clickable(self):
        self.busy(context=True)
        self.page.evaluate("applyDisconnectedSocketUi('Fixture connection loss')")
        state = self.state()
        self.assertEqual(state['spinner'], 0)
        self.assertEqual(state['title'], '')
        self.assertFalse(state['busy'])
        self.assertFalse(state['loading'])
        self.assertTrue(state['inputDisabled'])
        self.assertTrue(state['submitDisabled'])
        self.assertEqual(state['submit'], 'Disconnected')
        self.assertTrue(state['reconnect'])
        self.assertFalse(state['menus']['re-connect-button']['disabled'])
        self.assertNotEqual(state['menus']['re-connect-button']['pointer'], 'none')
        self.page.evaluate('restoreConnectedSocketUi()')
        self.assert_idle()

    def test_failed_send_never_enters_a_new_busy_run(self):
        self.page.evaluate('__menuTransport.throwSend = true')
        self.page.locator('#chat-message-input').fill('Cannot send')
        self.page.locator('#chat-message-submit').click()
        self.assertFalse(self.state()['busy'])
        self.assertEqual(self.state()['spinner'], 0)
        self.assertEqual(self.state()['submit'], 'Disconnected')

    def test_context_errors_and_pdf_failures_release_every_menu(self):
        for text in ('Outside the application root', 'Not a valid directory', 'Directory does not exist'):
            with self.subTest(message=text):
                self.busy(context=True)
                self.message(text)
                self.assert_idle()
                self.assertEqual(self.state()['clearContext'], 'none')
        for frame in ({'type': 'pdf-canvas-context-error', 'message': 'Fixture PDF error'},
                      {'type': 'pdf-canvas-context-finished', 'success': False, 'context_token': 'fixture'}):
            self.busy(context=True)
            self.emit(frame)
            self.assert_idle()

    def test_reconnect_and_history_clear_restore_menu_locks(self):
        for reset in ('Reconnect', 'CleanHistory'):
            self.busy()
            # Recovery entry points can be called after a transport recovery has
            # reopened their logical gate; they must clear stale visual locks too.
            self.page.evaluate('reConnectEnabled = true; cleanHistoryEnabled = true')
            self.page.evaluate('(name) => window[name]({preventDefault(){}})', reset)
            if reset == 'CleanHistory':
                self.page.locator('.ui-dialog:visible button').filter(has_text='Continue').click()
            self.assert_idle()

    def test_independent_hourglass_sources_do_not_clear_each_other(self):
        self.page.evaluate("setTitleBusy(true, 'pdf-fixture')")
        self.busy()
        self.finish()
        self.assertEqual(self.state()['title'], '⏳ ')
        self.page.evaluate("setTitleBusy(false, 'pdf-fixture')")
        self.assert_idle()

    def test_panels_remain_openable_while_chat_is_busy(self):
        self.busy()
        self.page.locator('#panels-menu-button').click()
        self.assertTrue(self.page.locator('#prompt-flow-panel').is_visible())
        with self.page.expect_popup() as popup_info:
            self.page.locator('#prompt-flow-panel').click()
        popup = popup_info.value
        popup.wait_for_load_state('load')
        self.assertEqual(urlsplit(popup.url).path, '/agent/prompt_flow_panel/')
        self.assertIn('Prompt Flow Panel', popup.title())
        self.assertEqual(popup.locator('#pmt-world').count(), 1)
        self.assert_busy()

    def test_buffered_restore_before_onload(self):
        self.assert_busy(loading=True)
        self.finish()
        self.assert_idle()

    def test_restored_session_without_loading_stays_idle(self):
        self.emit({'type': 'session-restored', 'loading': False,
                   'context_path': 'C:/Tlamatini/Temp/fixture.txt', 'context_type': 'file',
                   'context_filename': 'fixture.txt'})
        self.assert_idle()
        self.assertEqual(self.page.evaluate('actualContextDir'), 'C:/Tlamatini/Temp')

    def test_loading_closes_previously_open_config_dropdown(self):
        for menu in ('config', 'context', 'skills', 'external', 'db'):
            with self.subTest(menu=menu):
                toggle = self.page.locator(f'#{menu}-menu-button')
                dropdown = self.page.locator(f'ul[aria-labelledby="{menu}-menu-button"]')
                toggle.click()
                self.assertTrue(dropdown.is_visible())
                self.busy(context=True)
                self.assertFalse(dropdown.is_visible())
                toggle.press('Enter')
                self.assertFalse(dropdown.is_visible())
                self.assert_busy(loading=True)
                self.finish()
                toggle.click()
                self.assertTrue(dropdown.is_visible())
                self.page.keyboard.press('Escape')

    def test_context_directory_menu_sends_selected_path_and_waits_for_ready(self):
        self.page.locator('#context-menu-button').click()
        self.page.locator('#set-dir-context').click()
        self.page.wait_for_function("__menuTransport.sent.some(x => x.type === 'set-directory-as-context')")
        self.assertEqual(self.page.evaluate("__menuTransport.sent.find(x => x.type === 'set-directory-as-context').message"), 'C:/Tlamatini/Temp/menu-fixture')
        self.busy(context=True)
        self.assert_busy(loading=True)
        self.emit({'type': 'context-path-set', 'context_path': 'C:/Tlamatini/Temp/menu-fixture', 'context_type': 'directory'})
        self.assert_busy(loading=True)
        self.finish()
        self.assert_idle()

    def test_configure_agents_keeps_its_protocol_after_menu_move(self):
        self.emit({'username': 'system', 'type': 'agent', 'message': 'fixture-agent|Fixture Agent|true'})
        self.page.locator('#config-menu-button').click()
        self.page.locator('#enable-agents').click()
        self.page.locator('#fixture-agent').uncheck()
        self.page.locator('.ui-dialog:visible button').filter(has_text='Continue').click()
        self.assertTrue(self.page.evaluate("__menuTransport.sent.some(x => x.type === 'set-agents' && x.message.includes('fixture-agent=Fixture Agent=false'))"))
        self.assert_idle()

    def test_configure_mcps_keeps_both_protocols_after_menu_move(self):
        self.emit({'username': 'system', 'type': 'mcp', 'message': 'mcp-1|Fixture MCP|true'})
        self.emit({'username': 'system', 'type': 'tool', 'message': 'fixture-tool|Fixture Tool|true'})
        self.page.locator('#config-menu-button').click()
        self.page.locator('#enable-mcps').click()
        self.page.locator('#mcp-1').uncheck()
        self.page.locator('#fixture-tool').uncheck()
        self.page.locator('.ui-dialog:visible button').filter(has_text='Continue').click()
        self.assertTrue(self.page.evaluate("__menuTransport.sent.some(x => x.type === 'set-mcps' && x.message.split(',')[0].endsWith('=false'))"))
        self.assertTrue(self.page.evaluate("__menuTransport.sent.some(x => x.type === 'set-tools' && x.message.includes('fixture-tool=Fixture Tool=false'))"))
        self.assert_idle()

    def test_config_save_failure_retry_and_reconnect_notice(self):
        self.page.evaluate('OpenConfigModelsDialog({preventDefault(){}})')
        field = self.page.locator('[data-config-key="fixture_model"]')
        field.wait_for(state='visible')
        field.fill('changed')
        self.fail_config_save = True
        alerts = []
        self.page.on('dialog', lambda dialog: (alerts.append(dialog.message), dialog.accept()))
        save = self.page.locator('.ui-dialog:visible button').filter(has_text='Save')
        save.click()
        self.page.wait_for_function("document.querySelector('#config-models-fixture-model').closest('.ui-dialog').querySelector('.ui-dialog-buttonpane button').disabled === false")
        self.assertTrue(field.is_visible())
        self.assertTrue(any('Saving the configuration failed' in message for message in alerts))
        self.fail_config_save = False
        save.click()
        notice = self.page.locator('#config-reconnect-required-dialog-message')
        notice.wait_for(state='visible')
        self.assertFalse(field.is_visible())
        self.assertTrue(any(r['path'] == '/agent/save_config_models/' and json.loads(r['body'])['fixture_model'] == 'changed' for r in self.requests))
        self.page.keyboard.press('Escape')
        self.assert_idle()
        self.page.locator('#re-connect-button').click()
        self.assertTrue(self.page.evaluate("__menuTransport.sent.some(x => x.type === 'reconnect-llm-agent')"))
        self.assert_idle()

    def test_config_response_arriving_after_loading_starts_cannot_open_dialog(self):
        for handler in ('OpenConfigModelsDialog', 'OpenConfigUrlsDialog'):
            with self.subTest(handler=handler):
                self.defer_config_load = True
                self.pending_config_route = None
                with self.page.expect_request('**/load_config_section/**'):
                    self.page.evaluate('(name) => window[name]({preventDefault(){}})', handler)
                self.busy(context=True)
                self.assertIsNotNone(self.pending_config_route)
                with self.page.expect_response('**/load_config_section/**'):
                    self.pending_config_route.fulfill(content_type='application/json',
                                                      body='{"success":true,"values":{},"fields":[]}')
                self.page.wait_for_timeout(100)
                self.assertEqual(self.page.locator('.ui-dialog:visible').count(), 0)
                self.assert_busy(loading=True)
                self.finish()
                self.defer_config_load = False
                self.page.evaluate('(name) => window[name]({preventDefault(){}})', handler)
                self.page.locator('.ui-dialog:visible').wait_for(state='visible')
                self.page.keyboard.press('Escape')
                self.assert_idle()

    def test_logout_cancel_preserves_the_active_operation(self):
        self.busy()
        self.page.locator('#logout-button').click()
        self.page.keyboard.press('Escape')
        self.assert_busy()
        self.assertFalse(self.page.evaluate("__menuTransport.sent.some(x => x.type === 'cancel-all')"))

    def test_canvas_controls_follow_loaded_state_after_completion(self):
        for loaded in (False, True):
            self.page.evaluate('(value) => { canvasLoaded = value; }', loaded)
            self.busy()
            self.assertTrue(self.page.locator('#clean-canvas-button').is_disabled())
            self.finish()
            self.assert_idle()
            for button in ('clean-canvas-button', 'reopen-canvas-button', 'copy-canvas-button'):
                self.assertEqual(self.page.locator('#' + button).is_disabled(), not loaded)

    def test_runtime_toggles_remain_usable_while_menus_are_locked(self):
        self.page.locator('#multi-turn-enabled').check()
        self.page.locator('#ask-execs-enabled').check()
        self.busy()
        self.assert_busy()
        self.page.locator('#ask-execs-enabled').uncheck()
        self.assertTrue(self.page.evaluate("__menuTransport.sent.some(x => x.type === 'set-ask-execs-runtime' && x.ask_execs_runtime_enabled === false)"))
        self.assert_busy()

    def test_panel_play_pause_stop_and_stale_event_states(self):
        self.page.goto('http://tlamatini.test/agent/prompt_flow_panel/', wait_until='load')
        self.page.locator('#pmt-file-input').set_input_files(str(ROOT / 'docs/examples/prompting-kickoff.fpmt'))
        self.page.wait_for_function("document.querySelectorAll('.pmt-node').length > 0")
        self.assertEqual(self.page.evaluate('__menuTransport.sent.length'), 0)
        self.page.locator('#pmt-play').click()
        self.page.evaluate("__menuTransport.sockets[0].onmessage({data:JSON.stringify({event:'ready'})})")
        self.page.wait_for_function("__menuTransport.sent.some(x=>x.action==='start')")
        def event(**data):
            self.page.evaluate('(data) => __menuTransport.sockets[0].onmessage({data:JSON.stringify(data)})', data)
        event(event='state', status='running', run_id='current')
        self.assertTrue(self.page.locator('#pmt-play').is_disabled())
        self.assertTrue(self.page.locator('[data-action="open"]').is_disabled())
        self.assertFalse(self.page.locator('#pmt-pause').is_disabled())
        event(event='state', status='completed', run_id='stale')
        self.assertEqual(self.page.locator('#pmt-run-state').inner_text(), 'running')
        self.page.locator('#pmt-pause').click()
        self.assertTrue(self.page.evaluate("__menuTransport.sent.some(x=>x.action==='pause' && x.run_id==='current')"))
        event(event='state', status='paused', run_id='current')
        self.page.locator('#pmt-pause').click()
        self.assertTrue(self.page.evaluate("__menuTransport.sent.some(x=>x.action==='resume')"))
        event(event='state', status='running', run_id='current')
        self.page.locator('#pmt-stop').click()
        event(event='state', status='stopping', run_id='current')
        self.assertTrue(self.page.locator('#pmt-play').is_disabled())
        event(event='state', status='stopped', run_id='current')
        self.assertFalse(self.page.locator('#pmt-play').is_disabled())
        self.assertTrue(self.page.locator('#pmt-pause').is_disabled())
        self.assertTrue(self.page.locator('#pmt-stop').is_disabled())
        self.assertFalse(self.page.locator('[data-action="open"]').is_disabled())
