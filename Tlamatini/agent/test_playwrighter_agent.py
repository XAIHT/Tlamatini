# ═══════════════════════════════════════════════════════════════════
#   ✦  T L A M A T I N I  ✦   —   "one who knows"
#
#   Crafted with heart by  Angela   ·   @angelahack1
#   Developer · Architect · Creator of Tlamatini
#
#   Every line of this file was written by Angela.
# ═══════════════════════════════════════════════════════════════════
#   Tlamatini Author Banner — do not remove (releases scrub the name automatically)
"""Automated tests for the Playwrighter workflow agent.

Playwrighter drives a real browser (Playwright) through a declarative step
list and ships on BOTH surfaces (canvas node + wrapped chat_agent_playwrighter).
It is a standalone pool agent under ``agent/agents/playwrighter/``, so — like the
De-Compresser / Windower test modules — it is loaded through
``importlib.util.spec_from_file_location`` with a cwd save/restore so its
module-level ``os.chdir`` + log-file side effects stay in its own directory.

Tests NEVER launch a real browser: ``_run_one_step`` is exercised with a
``MagicMock`` page, and ``run_browser_flow`` is driven against a fake
``playwright.sync_api`` injected into ``sys.modules``. This makes the step
interpreter, the steps_json-wins-over-steps rule, the goto-prepend rule, the
assert roll-up, and the ImportError fallback all deterministic and offline.

Covers:
- _abs_under_script / _truncate helpers
- _run_one_step: every verb (goto/click/dblclick/fill/type/press/select/
  check/uncheck/wait_for/wait/extract_text/extract_attr/screenshot/
  assert_visible/assert_text/download) + required-field and unknown-action errors
- run_browser_flow: ImportError fallback, steps_json wins over YAML steps,
  goto auto-prepend, assert roll-up (pass/fail), browser-kind coercion
- _build_section_body + save_results report writing
- main() end-stage: target_agents always started + exactly one
  INI_SECTION_PLAYWRIGHTER block (success AND error result)
- Registry integration: ChatWrappedAgentSpec, Exec Report row, contract
  discovery, Parametrizer fields, URL route, JS classMap, CSS gradient,
  config.yaml defaults
- Migration presence: Agent row (0091) + Tool row (0092)
"""

import importlib.util
import json
import logging
import os
import shutil
import sys
import tempfile
import types
import unittest
from functools import lru_cache
from unittest.mock import MagicMock, patch

import yaml
from django.test import SimpleTestCase, TestCase


@lru_cache(maxsize=1)
def _load_playwrighter_module():
    module_path = os.path.join(
        os.path.dirname(__file__), 'agents', 'playwrighter', 'playwrighter.py',
    )
    spec = importlib.util.spec_from_file_location(
        'agent_playwrighter_module_for_tests', module_path,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f'Unable to load Playwrighter module from {module_path}')

    module = importlib.util.module_from_spec(spec)
    root = logging.getLogger()
    handlers_before = list(root.handlers)
    current_dir = os.getcwd()
    try:
        spec.loader.exec_module(module)
    finally:
        os.chdir(current_dir)
        for handler in list(root.handlers):
            if handler not in handlers_before:
                root.removeHandler(handler)
    return module


def _make_fake_playwright(page=None):
    """Build a fake ``playwright.sync_api`` module + the page mock the flow
    will drive. Returns (sys_modules_overlay, p_mock, page_mock)."""
    page = page or MagicMock()
    # A concrete final_url so out['final_url'] is a real string, not a Mock.
    page.url = "https://example.com/after"
    p = MagicMock()
    for kind in ("chromium", "firefox", "webkit"):
        getattr(p, kind).launch.return_value.new_context.return_value.new_page.return_value = page
    cm = MagicMock()
    cm.__enter__.return_value = p
    cm.__exit__.return_value = False
    sync_playwright = MagicMock(return_value=cm)
    sync_api = types.ModuleType("playwright.sync_api")
    sync_api.sync_playwright = sync_playwright
    pkg = types.ModuleType("playwright")
    return {"playwright": pkg, "playwright.sync_api": sync_api}, p, page


# ---------------------------------------------------------------------------
# Path / truncation helpers
# ---------------------------------------------------------------------------


class HelperFunctionTests(SimpleTestCase):
    def setUp(self):
        self.pw = _load_playwrighter_module()

    def test_abs_under_script_keeps_absolute_paths(self):
        abs_path = os.path.join(tempfile.gettempdir(), 'shot.png')
        self.assertEqual(self.pw._abs_under_script(abs_path), abs_path)

    def test_abs_under_script_resolves_relative_under_script_dir(self):
        resolved = self.pw._abs_under_script('out.txt')
        self.assertTrue(os.path.isabs(resolved))
        self.assertTrue(resolved.replace('\\', '/').endswith('playwrighter/out.txt'))

    def test_abs_under_script_passthrough_empty(self):
        self.assertEqual(self.pw._abs_under_script(''), '')

    def test_truncate_under_limit_is_unchanged(self):
        self.assertEqual(self.pw._truncate('short', 100), 'short')

    def test_truncate_over_limit_appends_marker(self):
        out = self.pw._truncate('x' * 50, 10)
        self.assertTrue(out.startswith('x' * 10))
        self.assertIn('[truncated]', out)

    def test_coerce_int_handles_ints_strings_floats_and_garbage(self):
        self.assertEqual(self.pw._coerce_int(10), 10)
        self.assertEqual(self.pw._coerce_int('10'), 10)
        self.assertEqual(self.pw._coerce_int('10.7'), 10)
        self.assertEqual(self.pw._coerce_int(None), 0)
        self.assertEqual(self.pw._coerce_int('oops'), 0)
        self.assertEqual(self.pw._coerce_int('oops', default=5), 5)


# ---------------------------------------------------------------------------
# _run_one_step — the declarative step interpreter (MagicMock page)
# ---------------------------------------------------------------------------


class RunOneStepTests(SimpleTestCase):
    def setUp(self):
        self.pw = _load_playwrighter_module()
        self.page = MagicMock()
        self.extracted = {}
        self.asserts = []

    def _step(self, step, idx=1, timeout=5000):
        return self.pw._run_one_step(self.page, step, idx, timeout, self.extracted, self.asserts)

    def test_goto_ok(self):
        res = self._step({'action': 'goto', 'url': 'http://x'})
        self.assertTrue(res['ok'])
        self.assertEqual(res['url'], 'http://x')
        self.page.goto.assert_called_once()

    def test_goto_missing_url_errors(self):
        res = self._step({'action': 'goto'})
        self.assertFalse(res['ok'])
        self.assertIn('url', res['error'])

    def test_goto_invalid_wait_until_coerced(self):
        self._step({'action': 'goto', 'url': 'x', 'wait_until': 'bogus'})
        _args, kwargs = self.page.goto.call_args
        self.assertEqual(kwargs.get('wait_until'), 'domcontentloaded')

    def test_click_ok(self):
        res = self._step({'action': 'click', 'selector': '#btn'})
        self.assertTrue(res['ok'])
        self.page.click.assert_called_once_with('#btn', timeout=5000)

    def test_click_missing_selector_errors(self):
        res = self._step({'action': 'click'})
        self.assertFalse(res['ok'])
        self.assertIn('selector', res['error'])

    def test_dblclick(self):
        self._step({'action': 'dblclick', 'selector': '#d'})
        self.page.dblclick.assert_called_once_with('#d', timeout=5000)

    def test_fill(self):
        self._step({'action': 'fill', 'selector': '#i', 'value': 'hello'})
        self.page.fill.assert_called_once_with('#i', 'hello', timeout=5000)

    def test_type_with_delay(self):
        self._step({'action': 'type', 'selector': '#i', 'text': 'hey', 'delay': 50})
        self.page.type.assert_called_once_with('#i', 'hey', delay=50, timeout=5000)

    def test_press_with_selector(self):
        self._step({'action': 'press', 'selector': '#i', 'key': 'Enter'})
        self.page.press.assert_called_once_with('#i', 'Enter', timeout=5000)

    def test_press_without_selector_uses_keyboard(self):
        self._step({'action': 'press', 'key': 'Escape'})
        self.page.keyboard.press.assert_called_once_with('Escape')

    def test_press_missing_key_errors(self):
        res = self._step({'action': 'press', 'selector': '#i'})
        self.assertFalse(res['ok'])
        self.assertIn('key', res['error'])

    def test_select_check_uncheck(self):
        self._step({'action': 'select', 'selector': '#s', 'value': 'opt'})
        self.page.select_option.assert_called_once_with('#s', 'opt', timeout=5000)
        self._step({'action': 'check', 'selector': '#c'})
        self.page.check.assert_called_once_with('#c', timeout=5000)
        self._step({'action': 'uncheck', 'selector': '#c'})
        self.page.uncheck.assert_called_once_with('#c', timeout=5000)

    def test_wait_for_with_state(self):
        self._step({'action': 'wait_for', 'selector': '#x', 'state': 'attached'})
        self.page.wait_for_selector.assert_called_once_with('#x', state='attached', timeout=5000)

    def test_wait_for_invalid_state_coerced_to_visible(self):
        self._step({'action': 'wait_for', 'selector': '#x', 'state': 'bogus'})
        _args, kwargs = self.page.wait_for_selector.call_args
        self.assertEqual(kwargs.get('state'), 'visible')

    def test_wait_records_ms(self):
        res = self._step({'action': 'wait', 'ms': 250})
        self.page.wait_for_timeout.assert_called_once_with(250)
        self.assertEqual(res['ms'], 250)

    def test_extract_text_with_selector(self):
        self.page.inner_text.return_value = 'Hello World'
        res = self._step({'action': 'extract_text', 'selector': '.t', 'name': 'greeting'})
        self.assertEqual(self.extracted['greeting'], 'Hello World')
        self.assertEqual(res['chars'], len('Hello World'))

    def test_extract_text_without_selector_uses_body(self):
        self.page.inner_text.return_value = 'Body text'
        res = self._step({'action': 'extract_text'}, idx=3)
        self.page.inner_text.assert_called_once_with('body', timeout=5000)
        self.assertEqual(res['name'], 'text_3')
        self.assertEqual(self.extracted['text_3'], 'Body text')

    def test_extract_attr(self):
        self.page.get_attribute.return_value = 'https://h/'
        res = self._step({'action': 'extract_attr', 'selector': 'a', 'attr': 'href', 'name': 'link'})
        self.assertEqual(self.extracted['link'], 'https://h/')
        self.assertEqual(res['attr'], 'href')

    def test_extract_attr_missing_attr_errors(self):
        res = self._step({'action': 'extract_attr', 'selector': 'a'})
        self.assertFalse(res['ok'])
        self.assertIn('attr', res['error'])

    def test_screenshot_records_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            shot = os.path.join(tmp, 'shot.png')
            res = self._step({'action': 'screenshot', 'path': shot})
        self.assertTrue(res['ok'])
        self.assertEqual(res['path'], shot)
        _args, kwargs = self.page.screenshot.call_args
        self.assertEqual(kwargs.get('path'), shot)
        self.assertFalse(kwargs.get('full_page'))

    def test_assert_visible_pass(self):
        self.page.is_visible.return_value = True
        res = self._step({'action': 'assert_visible', 'selector': '#ok'})
        self.assertTrue(res['ok'])
        self.assertTrue(res['passed'])
        self.assertEqual(self.asserts[-1], {'kind': 'visible', 'selector': '#ok', 'passed': True})

    def test_assert_visible_fail_marks_step_not_ok(self):
        self.page.is_visible.return_value = False
        res = self._step({'action': 'assert_visible', 'selector': '#missing'})
        self.assertFalse(res['ok'])
        self.assertFalse(res['passed'])

    def test_assert_text_pass(self):
        self.page.inner_text.return_value = 'Welcome home'
        res = self._step({'action': 'assert_text', 'contains': 'Welcome'})
        self.assertTrue(res['ok'])
        self.assertTrue(res['passed'])

    def test_assert_text_fail(self):
        self.page.inner_text.return_value = 'Welcome home'
        res = self._step({'action': 'assert_text', 'contains': 'Goodbye'})
        self.assertFalse(res['ok'])
        self.assertFalse(res['passed'])

    def test_download_saves_to_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            dest = os.path.join(tmp, 'file.bin')
            download = MagicMock()
            self.page.expect_download.return_value.__enter__.return_value.value = download
            res = self._step({'action': 'download', 'selector': '#dl', 'save_path': dest})
            self.assertTrue(res['ok'])
            self.assertEqual(res['path'], dest)
            download.save_as.assert_called_once_with(dest)

    def test_unknown_action_errors(self):
        res = self._step({'action': 'frobnicate'})
        self.assertFalse(res['ok'])
        self.assertIn('Unknown action', res['error'])


# ---------------------------------------------------------------------------
# run_browser_flow — orchestration with a fake playwright
# ---------------------------------------------------------------------------


class RunBrowserFlowTests(SimpleTestCase):
    def setUp(self):
        self.pw = _load_playwrighter_module()

    def test_import_error_is_reported_not_raised(self):
        # Force the local `from playwright.sync_api import sync_playwright` to
        # fail; the agent must return an error envelope, never raise.
        with patch.dict(sys.modules, {'playwright.sync_api': None}):
            out = self.pw.run_browser_flow({'start_url': 'http://x', 'steps': []})
        self.assertEqual(out['status'], 'error')
        self.assertIn('not installed', out['error'])

    def test_steps_json_wins_over_yaml_steps(self):
        mods, _p, page = _make_fake_playwright()
        page.is_visible.return_value = True
        cfg = {
            'steps': [
                {'action': 'click', 'selector': '#a'},
                {'action': 'click', 'selector': '#a2'},
            ],
            'steps_json': json.dumps([{'action': 'click', 'selector': '#b'}]),
        }
        with patch.dict(sys.modules, mods):
            out = self.pw.run_browser_flow(cfg)
        # steps_json (1 step) replaces the 2 YAML steps; no start_url -> no prepend.
        self.assertEqual(out['steps_total'], 1)
        self.assertEqual(out['steps_run'], 1)

    def test_goto_is_prepended_when_first_step_is_not_goto(self):
        mods, _p, _page = _make_fake_playwright()
        cfg = {
            'start_url': 'http://x',
            'steps_json': json.dumps([{'action': 'click', 'selector': '#b'}]),
        }
        with patch.dict(sys.modules, mods):
            out = self.pw.run_browser_flow(cfg)
        self.assertEqual(out['steps_total'], 2)
        self.assertEqual(out['step_results'][0]['action'], 'goto')

    def test_no_prepend_when_first_step_is_goto(self):
        mods, _p, _page = _make_fake_playwright()
        cfg = {
            'start_url': 'http://x',
            'steps_json': json.dumps([
                {'action': 'goto', 'url': 'http://y'},
                {'action': 'click', 'selector': '#b'},
            ]),
        }
        with patch.dict(sys.modules, mods):
            out = self.pw.run_browser_flow(cfg)
        self.assertEqual(out['steps_total'], 2)
        self.assertEqual(out['step_results'][0]['url'], 'http://y')

    def test_assert_rollup_pass(self):
        mods, _p, page = _make_fake_playwright()
        page.is_visible.return_value = True
        cfg = {'steps_json': json.dumps([{'action': 'assert_visible', 'selector': '#ok'}])}
        with patch.dict(sys.modules, mods):
            out = self.pw.run_browser_flow(cfg)
        self.assertEqual(out['assert_result'], 'pass')
        self.assertEqual(out['status'], 'ok')

    def test_assert_rollup_fail_sets_assert_failed_status(self):
        mods, _p, page = _make_fake_playwright()
        page.is_visible.return_value = False
        cfg = {'steps_json': json.dumps([{'action': 'assert_visible', 'selector': '#missing'}])}
        with patch.dict(sys.modules, mods):
            out = self.pw.run_browser_flow(cfg)
        self.assertEqual(out['assert_result'], 'fail')
        self.assertEqual(out['status'], 'assert_failed')

    def test_invalid_browser_kind_coerced_to_chromium(self):
        mods, p, _page = _make_fake_playwright()
        cfg = {'browser': 'netscape', 'steps_json': json.dumps([{'action': 'wait', 'ms': 1}])}
        with patch.dict(sys.modules, mods):
            self.pw.run_browser_flow(cfg)
        p.chromium.launch.assert_called_once()

    def test_hold_open_seconds_waits_before_close(self):
        # The user asked the browser to stay open before closing. With a single
        # non-wait step, the ONLY wait_for_timeout call must be the linger, and
        # it must be 10s -> 10000 ms.
        mods, _p, page = _make_fake_playwright()
        cfg = {
            'steps_json': json.dumps([{'action': 'click', 'selector': '#x'}]),
            'hold_open_seconds': 10,
        }
        with patch.dict(sys.modules, mods):
            self.pw.run_browser_flow(cfg)
        page.wait_for_timeout.assert_called_once_with(10000)

    def test_hold_open_ms_wins_over_seconds(self):
        mods, _p, page = _make_fake_playwright()
        cfg = {
            'steps_json': json.dumps([{'action': 'click', 'selector': '#x'}]),
            'hold_open_seconds': 9,
            'hold_open_ms': 1500,
        }
        with patch.dict(sys.modules, mods):
            self.pw.run_browser_flow(cfg)
        called_ms = [c.args[0] for c in page.wait_for_timeout.call_args_list if c.args]
        self.assertIn(1500, called_ms)
        self.assertNotIn(9000, called_ms)

    def test_no_hold_open_by_default(self):
        mods, _p, page = _make_fake_playwright()
        cfg = {'steps_json': json.dumps([{'action': 'click', 'selector': '#x'}])}
        with patch.dict(sys.modules, mods):
            self.pw.run_browser_flow(cfg)
        page.wait_for_timeout.assert_not_called()

    def test_hold_open_still_fires_on_mid_flow_error(self):
        # A failed step aborts the loop but the browser is still alive, so the
        # linger must still run — a failed run is exactly when watching helps.
        mods, _p, page = _make_fake_playwright()
        cfg = {
            'steps_json': json.dumps([{'action': 'goto'}]),  # missing url -> error
            'hold_open_seconds': 3,
        }
        with patch.dict(sys.modules, mods):
            out = self.pw.run_browser_flow(cfg)
        self.assertEqual(out['status'], 'error')
        page.wait_for_timeout.assert_called_once_with(3000)

    def test_bad_hold_open_value_does_not_abort_run(self):
        mods, _p, page = _make_fake_playwright()
        cfg = {
            'steps_json': json.dumps([{'action': 'click', 'selector': '#x'}]),
            'hold_open_seconds': 'oops',
        }
        with patch.dict(sys.modules, mods):
            out = self.pw.run_browser_flow(cfg)
        self.assertEqual(out['status'], 'ok')
        page.wait_for_timeout.assert_not_called()


# ---------------------------------------------------------------------------
# Section body + report file
# ---------------------------------------------------------------------------


class SectionAndReportTests(SimpleTestCase):
    def setUp(self):
        self.pw = _load_playwrighter_module()

    def test_build_section_body_includes_extracted_and_trace(self):
        body = self.pw._build_section_body({
            'extracted': {'greeting': 'Hello'},
            'step_results': [{'index': 1, 'action': 'goto', 'ok': True}],
            'error': '',
        })
        self.assertIn('=== EXTRACTED ===', body)
        self.assertIn('greeting', body)
        self.assertIn('=== STEP TRACE ===', body)
        self.assertIn('"action": "goto"', body)

    def test_build_section_body_includes_error(self):
        body = self.pw._build_section_body({
            'extracted': {}, 'step_results': [], 'error': 'boom',
        })
        self.assertIn('ERROR: boom', body)

    def test_save_results_writes_report_header(self):
        with tempfile.TemporaryDirectory() as tmp:
            out_file = os.path.join(tmp, 'results.txt')
            result = {
                'start_url': 'http://x', 'final_url': 'http://x/done',
                'status': 'ok', 'steps_run': 3, 'steps_total': 3,
                'assert_result': 'pass', 'extracted': {}, 'step_results': [], 'error': '',
            }
            path = self.pw.save_results(result, out_file)
            self.assertTrue(os.path.exists(path))
            with open(path, 'r', encoding='utf-8') as f:
                content = f.read()
        self.assertIn('=== PLAYWRIGHTER RESULTS ===', content)
        self.assertIn('Status: ok', content)
        self.assertIn('Steps run: 3/3', content)
        self.assertIn('Assert result: pass', content)


# ---------------------------------------------------------------------------
# main() end-stage contract — run_browser_flow stubbed so no browser launches
# ---------------------------------------------------------------------------


class MainEndStageTests(SimpleTestCase):
    def setUp(self):
        self.pw = _load_playwrighter_module()
        self.tmp = tempfile.mkdtemp()
        self.cwd_before = os.getcwd()
        os.chdir(self.tmp)

    def tearDown(self):
        os.chdir(self.cwd_before)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _canned_result(self, status='ok'):
        return {
            'start_url': 'http://x', 'final_url': 'http://x/done',
            'status': status, 'steps_run': 2, 'steps_total': 2,
            'assert_result': 'pass' if status == 'ok' else 'fail',
            'extracted': {'greeting': 'hi'}, 'step_results': [{'index': 1, 'action': 'goto', 'ok': True}],
            'error': '' if status == 'ok' else 'something failed',
        }

    def _capture_main(self, cfg_dict, result_status='ok'):
        with open(os.path.join(self.tmp, 'config.yaml'), 'w', encoding='utf-8') as f:
            yaml.safe_dump(cfg_dict, f)

        started = []
        records = []

        class _H(logging.Handler):
            def emit(self, record):
                records.append(record.getMessage())

        handler = _H()
        logging.getLogger().addHandler(handler)
        with patch.object(self.pw, 'run_browser_flow', return_value=self._canned_result(result_status)), \
             patch.object(self.pw, 'start_agent', side_effect=lambda n: (started.append(n) or True)), \
             patch.object(self.pw, 'wait_for_agents_to_stop'), \
             patch.object(self.pw, 'time') as time_mock:
            time_mock.sleep = lambda _s: None
            try:
                self.pw.main()
            except SystemExit:
                pass
        logging.getLogger().removeHandler(handler)
        return started, records

    def test_targets_started_and_single_section_on_success(self):
        started, records = self._capture_main({
            'start_url': 'http://x',
            'output_file': os.path.join(self.tmp, 'r.txt'),
            'target_agents': ['parametrizer_1', 'ender_1'],
        })
        self.assertEqual(started, ['parametrizer_1', 'ender_1'])
        blocks = [r for r in records if 'INI_SECTION_PLAYWRIGHTER' in r]
        self.assertEqual(len(blocks), 1)
        self.assertIn('>>>END_SECTION_PLAYWRIGHTER', blocks[0])
        self.assertIn('status: ok', blocks[0])

    def test_targets_started_and_section_emitted_on_error_result(self):
        started, records = self._capture_main({
            'start_url': 'http://x',
            'output_file': os.path.join(self.tmp, 'r.txt'),
            'target_agents': ['forker_1'],
        }, result_status='error')
        # Even on an error result the chain advances and the block is emitted.
        self.assertEqual(started, ['forker_1'])
        blocks = [r for r in records if 'INI_SECTION_PLAYWRIGHTER' in r]
        self.assertEqual(len(blocks), 1)
        self.assertIn('status: error', blocks[0])

    def test_results_file_is_written(self):
        out_file = os.path.join(self.tmp, 'report.txt')
        self._capture_main({
            'start_url': 'http://x',
            'output_file': out_file,
            'target_agents': [],
        })
        self.assertTrue(os.path.exists(out_file))


# ---------------------------------------------------------------------------
# Registry integration
# ---------------------------------------------------------------------------


class RegistryIntegrationTests(SimpleTestCase):
    def test_chat_wrapped_agent_spec_is_registered(self):
        from agent.chat_agent_registry import WRAPPED_CHAT_AGENT_BY_TOOL_NAME
        spec = WRAPPED_CHAT_AGENT_BY_TOOL_NAME.get('chat_agent_playwrighter')
        self.assertIsNotNone(spec, "chat_agent_playwrighter must be registered")
        self.assertEqual(spec.key, 'playwrighter')
        self.assertEqual(spec.template_dir, 'playwrighter')
        self.assertEqual(spec.tool_description, 'Chat-Agent-Playwrighter')
        self.assertEqual(spec.display_name, 'Playwrighter')

    def test_exec_report_tool_row_is_registered(self):
        from agent.mcp_agent import _EXEC_REPORT_TOOLS
        self.assertEqual(_EXEC_REPORT_TOOLS.get('chat_agent_playwrighter'),
                         ('playwrighter', 'Playwrighter'))

    def test_agent_contract_disk_discovery_picks_up_playwrighter(self):
        from agent.services.agent_contracts import get_agent_contract
        contract = get_agent_contract('playwrighter')
        self.assertEqual(contract.agent_type, 'playwrighter')
        self.assertEqual(contract.output_field_by_slot.get(0), 'target_agents')
        self.assertFalse(contract.never_starts_targets)

    def test_parametrizer_fields_registered(self):
        from agent.services.agent_contracts import get_parametrizer_source_fields
        fields = get_parametrizer_source_fields().get('playwrighter')
        self.assertIsNotNone(fields)
        for expected in ('start_url', 'final_url', 'status', 'steps_run',
                         'assert_result', 'response_body'):
            self.assertIn(expected, fields)

    def test_url_route_exists(self):
        from django.urls import reverse
        url = reverse('update_playwrighter_connection', kwargs={'agent_name': 'playwrighter-1'})
        self.assertIn('update_playwrighter_connection', url)

    def test_canvas_classmap_contains_playwrighter(self):
        js_path = os.path.join(os.path.dirname(__file__), 'static', 'agent', 'js', 'acp-canvas-core.js')
        with open(js_path, 'r', encoding='utf-8') as f:
            js_source = f.read()
        self.assertIn("'playwrighter': 'playwrighter-agent'", js_source)

    def test_css_gradient_is_defined_for_canvas_and_sidebar(self):
        # Unlike agents that inherit the sidebar colour via applyAgentToolIconStyle,
        # Playwrighter defines an EXPLICIT sidebar-icon rule too, so its 4-stop
        # gradient legitimately appears twice (.canvas-item.playwrighter-agent +
        # .agent-tool-item[data-content="Playwrighter"] .agent-tool-icon). The
        # distinct hex stops guarantee no collision with any OTHER agent.
        css_path = os.path.join(os.path.dirname(__file__), 'static', 'agent', 'css', 'agentic_control_panel.css')
        with open(css_path, 'r', encoding='utf-8') as f:
            css_source = f.read()
        gradient = '#3D1766 0%, #D90368 33%, #0FA3B1 66%, #6EE7B7 100%'
        self.assertGreaterEqual(css_source.count(gradient), 1,
                                "The Playwrighter canvas gradient must be defined")
        self.assertIn('.canvas-item.playwrighter-agent', css_source)

    def test_config_yaml_defaults(self):
        cfg_path = os.path.join(os.path.dirname(__file__), 'agents', 'playwrighter', 'config.yaml')
        with open(cfg_path, 'r', encoding='utf-8') as f:
            cfg = yaml.safe_load(f)
        self.assertEqual(cfg.get('browser'), 'chromium')
        self.assertTrue(cfg.get('headless'))
        self.assertIn('steps', cfg)
        self.assertEqual(cfg.get('target_agents'), [])
        # The hold-open linger knobs must exist as assignable config paths
        # (default 0) so the wrapped tool can set hold_open_seconds=N.
        self.assertEqual(cfg.get('hold_open_seconds'), 0)
        self.assertEqual(cfg.get('hold_open_ms'), 0)


class MigrationPresenceTests(TestCase):
    def test_agent_row_seeded_by_migration_0091(self):
        from agent.models import Agent
        self.assertTrue(
            Agent.objects.filter(agentDescription='Playwrighter').exists(),
            "Migration 0091 must seed an Agent row with agentDescription='Playwrighter'",
        )

    def test_tool_row_seeded_by_migration_0092(self):
        from agent.models import Tool
        self.assertTrue(
            Tool.objects.filter(toolDescription='Chat-Agent-Playwrighter').exists(),
            "Migration 0092 must seed a Tool row with toolDescription='Chat-Agent-Playwrighter'",
        )


if __name__ == '__main__':
    unittest.main()
