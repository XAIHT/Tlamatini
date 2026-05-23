"""Automated tests for the Kalier workflow agent and its surrounding infrastructure.

Kalier bridges Tlamatini to Kali Linux offensive-security tooling through the
MCP-Kali-Server (https://www.kali.org/tools/mcp-kali-server/). It is a standalone
pool agent under ``agent/agents/kalier/`` that runs as a separate Python
subprocess, so — exactly like the Windower / De-Compresser / Parametrizer test
modules — it is loaded through ``importlib.util.spec_from_file_location`` with a
cwd save/restore so its module-level ``os.chdir`` + ``open(LOG_FILE_PATH)`` side
effects land in its own directory.

The agent talks to the MCP-Kali-Server Flask API over HTTP using only the Python
stdlib (``urllib``). Tests NEVER touch a real network: ``urllib.request.urlopen``
is mocked, so the per-action payload builder, the response/envelope normaliser,
and every transport error path (HTTPError / URLError / generic) are exercised
deterministically against canned server responses.

Covers:
- _ACTION_ROUTES: all 12 actions map to the right (method, endpoint)
- _build_payload: per-action body shape (only relevant keys), metasploit
  options as dict AND as a JSON string, bad-JSON fallback, hydra credentials
- _subject_for: the human subject for each action
- _cfg: None-coercion helper
- call_kali_api: tool-success envelope, tool-error envelope, health response,
  HTTPError, URLError (server unreachable), generic exception, password masking
- _emit_section: single atomic INI_SECTION_KALIER block, KV header + body
- main() end-stage: target_agents ALWAYS started + exactly one section,
  unknown-action path, health path
- Registry integration: ChatWrappedAgentSpec, Exec Report row, contract +
  secret_paths, Parametrizer fields, URL route, JS wiring (4 files), CSS
  gradient (unique + monochrome), config.yaml defaults, capability hints,
  agents_descriptions row, agentic_skill #66
- Parametrizer round-trip: SECTION_AGENT_TYPES, OUTPUT_PARSERS parse, source
  base resolution, views registration
- Planner selection: chat_agent_kalier wins on pentest prompts, not on others
- Flow compiler: Starter->Kalier->Parametrizer->Kalier->Ender wiring + .flw
  secret redaction
- Skill: kali-pentest discovered + frontmatter contract
- Demo prompts (57/58/59) + catalog contiguity
- Migration presence: Agent row (0097) + Tool row (0098)
"""

import importlib.util
import io
import json
import logging
import os
import tempfile
import unittest
import urllib.error
from functools import lru_cache
from unittest.mock import patch

import yaml
from django.test import SimpleTestCase, TestCase


@lru_cache(maxsize=1)
def _load_kalier_module():
    module_path = os.path.join(
        os.path.dirname(__file__), 'agents', 'kalier', 'kalier.py',
    )
    spec = importlib.util.spec_from_file_location(
        'agent_kalier_module_for_tests', module_path,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f'Unable to load Kalier module from {module_path}')

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


class _FakeResp:
    """Minimal stand-in for the object returned by urllib.request.urlopen."""

    def __init__(self, body: bytes, status: int = 200):
        self._body = body
        self._status = status

    def read(self):
        return self._body

    def getcode(self):
        return self._status

    def __enter__(self):
        return self

    def __exit__(self, *_a):
        return False


def _envelope(stdout='', stderr='', return_code=0, success=True, timed_out=False):
    return json.dumps({
        'stdout': stdout, 'stderr': stderr, 'return_code': return_code,
        'success': success, 'timed_out': timed_out,
        'partial_results': bool(timed_out and (stdout or stderr)),
    }).encode('utf-8')


# ---------------------------------------------------------------------------
# _ACTION_ROUTES — the MCP-Kali-Server endpoint contract
# ---------------------------------------------------------------------------


class ActionRoutesTests(SimpleTestCase):
    def setUp(self):
        self.k = _load_kalier_module()

    def test_all_twelve_actions_present(self):
        expected = {
            'command', 'nmap', 'gobuster', 'dirb', 'nikto', 'sqlmap',
            'metasploit', 'hydra', 'john', 'wpscan', 'enum4linux', 'health',
        }
        self.assertEqual(set(self.k._ACTION_ROUTES.keys()), expected)

    def test_routes_match_upstream_server_py(self):
        routes = self.k._ACTION_ROUTES
        self.assertEqual(routes['command'], ('POST', 'api/command'))
        self.assertEqual(routes['nmap'], ('POST', 'api/tools/nmap'))
        self.assertEqual(routes['gobuster'], ('POST', 'api/tools/gobuster'))
        self.assertEqual(routes['enum4linux'], ('POST', 'api/tools/enum4linux'))
        self.assertEqual(routes['health'], ('GET', 'health'))

    def test_only_health_is_get(self):
        gets = [a for a, (m, _e) in self.k._ACTION_ROUTES.items() if m == 'GET']
        self.assertEqual(gets, ['health'])


# ---------------------------------------------------------------------------
# _build_payload — per-action request body
# ---------------------------------------------------------------------------


class BuildPayloadTests(SimpleTestCase):
    def setUp(self):
        self.k = _load_kalier_module()

    def test_command(self):
        self.assertEqual(self.k._build_payload('command', {'command': 'whoami'}),
                         {'command': 'whoami'})

    def test_nmap_includes_only_set_optionals(self):
        body = self.k._build_payload('nmap', {'target': '10.0.0.5', 'scan_type': '-sV',
                                              'ports': '22,80', 'additional_args': '-Pn'})
        self.assertEqual(body, {'target': '10.0.0.5', 'scan_type': '-sV',
                                'ports': '22,80', 'additional_args': '-Pn'})

    def test_nmap_omits_empty_optionals(self):
        body = self.k._build_payload('nmap', {'target': '10.0.0.5', 'scan_type': '',
                                              'ports': '', 'additional_args': ''})
        self.assertEqual(body, {'target': '10.0.0.5'})

    def test_gobuster_defaults_mode_dir(self):
        body = self.k._build_payload('gobuster', {'url': 'http://x'})
        self.assertEqual(body['url'], 'http://x')
        self.assertEqual(body['mode'], 'dir')

    def test_sqlmap_optional_data(self):
        body = self.k._build_payload('sqlmap', {'url': 'http://x?id=1', 'data': 'id=1'})
        self.assertEqual(body, {'url': 'http://x?id=1', 'data': 'id=1'})

    def test_hydra_carries_credentials(self):
        body = self.k._build_payload('hydra', {
            'target': '10.0.0.5', 'service': 'ssh', 'username': 'root',
            'password_file': '/usr/share/wordlists/rockyou.txt',
        })
        self.assertEqual(body['target'], '10.0.0.5')
        self.assertEqual(body['service'], 'ssh')
        self.assertEqual(body['username'], 'root')
        self.assertEqual(body['password_file'], '/usr/share/wordlists/rockyou.txt')

    def test_john_payload(self):
        body = self.k._build_payload('john', {'hash_file': '/root/h.txt',
                                             'wordlist': '/usr/share/wordlists/rockyou.txt',
                                             'format': 'raw-md5'})
        self.assertEqual(body['hash_file'], '/root/h.txt')
        self.assertEqual(body['format'], 'raw-md5')

    def test_metasploit_options_dict_passthrough(self):
        body = self.k._build_payload('metasploit', {
            'module': 'exploit/x', 'options': {'RHOSTS': '10.0.0.5', 'RPORT': 21},
        })
        self.assertEqual(body['module'], 'exploit/x')
        self.assertEqual(body['options'], {'RHOSTS': '10.0.0.5', 'RPORT': 21})

    def test_metasploit_options_json_string_parsed(self):
        # The flat wrapped-tool grammar can only deliver a JSON STRING.
        body = self.k._build_payload('metasploit', {
            'module': 'exploit/x', 'options': '{"RHOSTS": "10.0.0.5", "RPORT": 21}',
        })
        self.assertEqual(body['options'], {'RHOSTS': '10.0.0.5', 'RPORT': 21})

    def test_metasploit_bad_json_options_falls_back_to_empty(self):
        body = self.k._build_payload('metasploit', {'module': 'x', 'options': 'not json{'})
        self.assertEqual(body['options'], {})

    def test_health_has_empty_payload(self):
        self.assertEqual(self.k._build_payload('health', {}), {})


# ---------------------------------------------------------------------------
# _subject_for / _cfg
# ---------------------------------------------------------------------------


class SubjectAndCfgTests(SimpleTestCase):
    def setUp(self):
        self.k = _load_kalier_module()

    def test_subject_for_each_action(self):
        self.assertEqual(self.k._subject_for('command', {'command': 'id'}), 'id')
        self.assertEqual(self.k._subject_for('nmap', {'target': '1.2.3.4'}), '1.2.3.4')
        self.assertEqual(self.k._subject_for('gobuster', {'url': 'http://x'}), 'http://x')
        self.assertEqual(self.k._subject_for('metasploit', {'module': 'exploit/y'}), 'exploit/y')
        self.assertEqual(self.k._subject_for('john', {'hash_file': '/h'}), '/h')
        self.assertEqual(self.k._subject_for('health', {}), '(health probe)')

    def test_cfg_coerces_none_to_default(self):
        self.assertEqual(self.k._cfg({'a': None}, 'a', 'fallback'), 'fallback')
        self.assertEqual(self.k._cfg({}, 'b', 'd'), 'd')
        self.assertEqual(self.k._cfg({'c': 'v'}, 'c', 'd'), 'v')


# ---------------------------------------------------------------------------
# call_kali_api — the urllib HTTP bridge (mocked, no real network)
# ---------------------------------------------------------------------------


class CallKaliApiTests(SimpleTestCase):
    def setUp(self):
        self.k = _load_kalier_module()
        self.cfg = {'server_url': 'http://127.0.0.1:5000', 'timeout': 5, 'target': '10.0.0.5'}

    def test_tool_success_envelope(self):
        body = _envelope(stdout='PORT 22/tcp open ssh', return_code=0, success=True)
        with patch('urllib.request.urlopen', return_value=_FakeResp(body, 200)):
            res = self.k.call_kali_api('nmap', self.cfg)
        self.assertTrue(res['ok'])
        self.assertTrue(res['success'])
        self.assertEqual(res['return_code'], 0)
        self.assertFalse(res['timed_out'])
        self.assertIn('22/tcp open ssh', res['response_body'])
        self.assertEqual(res['endpoint'], 'api/tools/nmap')
        self.assertEqual(res['method'], 'POST')

    def test_tool_failure_envelope_preserved(self):
        body = _envelope(stdout='', stderr='1 host down', return_code=1, success=False)
        with patch('urllib.request.urlopen', return_value=_FakeResp(body, 200)):
            res = self.k.call_kali_api('nmap', self.cfg)
        # ok==True (HTTP round-trip fine) but the tool's own success is False.
        self.assertTrue(res['ok'])
        self.assertFalse(res['success'])
        self.assertEqual(res['return_code'], 1)
        self.assertIn('1 host down', res['response_body'])

    def test_timed_out_envelope(self):
        body = _envelope(stdout='partial', return_code=-1, success=True, timed_out=True)
        with patch('urllib.request.urlopen', return_value=_FakeResp(body, 200)):
            res = self.k.call_kali_api('gobuster', {**self.cfg, 'url': 'http://x'})
        self.assertTrue(res['timed_out'])

    def test_server_error_field_envelope(self):
        body = json.dumps({'error': 'Target parameter is required'}).encode('utf-8')
        with patch('urllib.request.urlopen', return_value=_FakeResp(body, 200)):
            res = self.k.call_kali_api('nmap', self.cfg)
        self.assertFalse(res['ok'])
        self.assertFalse(res['success'])
        self.assertIn('Target parameter is required', res['response_body'])

    def test_health_response(self):
        body = json.dumps({'status': 'healthy', 'tools_status': {'nmap': True},
                           'all_essential_tools_available': True}).encode('utf-8')
        with patch('urllib.request.urlopen', return_value=_FakeResp(body, 200)):
            res = self.k.call_kali_api('health', self.cfg)
        self.assertTrue(res['ok'])
        self.assertTrue(res['success'])
        self.assertIn('healthy', res['response_body'])

    def test_http_error_path(self):
        err = urllib.error.HTTPError('http://x', 500, 'Server Error', None,
                                     io.BytesIO(b'boom'))
        with patch('urllib.request.urlopen', side_effect=err):
            res = self.k.call_kali_api('nmap', self.cfg)
        self.assertFalse(res['ok'])
        self.assertEqual(res['return_code'], 500)
        self.assertIn('boom', res['response_body'])

    def test_url_error_unreachable_server(self):
        with patch('urllib.request.urlopen', side_effect=urllib.error.URLError('Connection refused')):
            res = self.k.call_kali_api('nmap', self.cfg)
        self.assertFalse(res['ok'])
        self.assertEqual(res['return_code'], -1)
        self.assertIn('Cannot reach MCP-Kali-Server', res['response_body'])

    def test_generic_exception_path(self):
        with patch('urllib.request.urlopen', side_effect=RuntimeError('weird')):
            res = self.k.call_kali_api('nmap', self.cfg)
        self.assertFalse(res['ok'])
        self.assertIn('weird', res['response_body'])

    def test_password_masked_in_logs(self):
        records = []

        class _H(logging.Handler):
            def emit(self, record):
                records.append(record.getMessage())

        h = _H()
        logging.getLogger().addHandler(h)
        try:
            body = _envelope(stdout='done', success=True)
            cfg = {**self.cfg, 'service': 'ssh', 'username': 'root', 'password': 'SuperSecret123'}
            with patch('urllib.request.urlopen', return_value=_FakeResp(body, 200)):
                self.k.call_kali_api('hydra', cfg)
        finally:
            logging.getLogger().removeHandler(h)
        joined = '\n'.join(records)
        self.assertNotIn('SuperSecret123', joined)
        self.assertIn('***', joined)


# ---------------------------------------------------------------------------
# _emit_section — single atomic INI_SECTION_KALIER block
# ---------------------------------------------------------------------------


class EmitSectionTests(SimpleTestCase):
    def setUp(self):
        self.k = _load_kalier_module()

    def test_single_atomic_block_with_header_and_body(self):
        records = []

        class _H(logging.Handler):
            def emit(self, record):
                records.append(record.getMessage())

        h = _H()
        logging.getLogger().addHandler(h)
        try:
            self.k._emit_section(
                {'action': 'nmap', 'endpoint': 'api/tools/nmap', 'subject': '10.0.0.5',
                 'return_code': 0, 'success': 'true', 'timed_out': 'false',
                 'server_url': 'http://127.0.0.1:5000'},
                'Nmap scan report ...',
            )
        finally:
            logging.getLogger().removeHandler(h)
        blocks = [r for r in records if 'INI_SECTION_KALIER' in r]
        self.assertEqual(len(blocks), 1)
        block = blocks[0]
        self.assertIn('INI_SECTION_KALIER<<<', block)
        self.assertIn('>>>END_SECTION_KALIER', block)
        self.assertIn('action: nmap', block)
        self.assertIn('success: true', block)
        self.assertIn('Nmap scan report ...', block)


# ---------------------------------------------------------------------------
# main() end-stage — target_agents ALWAYS start, exactly one section per run
# ---------------------------------------------------------------------------


class MainEndStageTests(SimpleTestCase):
    def setUp(self):
        self.k = _load_kalier_module()
        self.tmp = tempfile.mkdtemp()
        self.cwd_before = os.getcwd()
        os.chdir(self.tmp)

    def tearDown(self):
        os.chdir(self.cwd_before)
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _capture_main(self, cfg_dict, api_result=None):
        with open(os.path.join(self.tmp, 'config.yaml'), 'w', encoding='utf-8') as f:
            yaml.safe_dump(cfg_dict, f)

        started = []
        records = []

        class _H(logging.Handler):
            def emit(self, record):
                records.append(record.getMessage())

        handler = _H()
        logging.getLogger().addHandler(handler)

        result = api_result if api_result is not None else {
            'ok': True, 'return_code': 0, 'success': True, 'timed_out': False,
            'endpoint': 'api/tools/nmap', 'method': 'POST',
            'server_url': cfg_dict.get('server_url', 'http://127.0.0.1:5000'),
            'response_body': 'PORT 22/tcp open ssh', 'raw': {},
        }
        exit_code = None
        with patch.object(self.k, 'call_kali_api', return_value=result), \
             patch.object(self.k, 'start_agent', side_effect=lambda n: (started.append(n) or True)), \
             patch.object(self.k, 'wait_for_agents_to_stop'), \
             patch.object(self.k, 'time') as time_mock:
            time_mock.sleep = lambda _s: None
            try:
                self.k.main()
            except SystemExit as e:
                exit_code = e.code
        logging.getLogger().removeHandler(handler)
        return exit_code, started, records

    def test_targets_started_and_single_section_on_success(self):
        code, started, records = self._capture_main({
            'action': 'nmap', 'target': '10.0.0.5',
            'server_url': 'http://127.0.0.1:5000',
            'target_agents': ['parametrizer_1', 'notifier_1'],
        })
        self.assertEqual(started, ['parametrizer_1', 'notifier_1'])
        blocks = [r for r in records if 'INI_SECTION_KALIER' in r]
        self.assertEqual(len(blocks), 1)
        self.assertEqual(code, 0)

    def test_targets_started_even_on_transport_failure(self):
        failed = {
            'ok': False, 'return_code': -1, 'success': False, 'timed_out': False,
            'endpoint': 'api/tools/nmap', 'method': 'POST',
            'server_url': 'http://127.0.0.1:5000',
            'response_body': 'Cannot reach MCP-Kali-Server ...', 'raw': {},
        }
        code, started, records = self._capture_main(
            {'action': 'nmap', 'target': '10.0.0.5', 'target_agents': ['downstream_1']},
            api_result=failed,
        )
        # Always triggers downstream so the chain is never stranded.
        self.assertEqual(started, ['downstream_1'])
        self.assertEqual(code, 0)
        blocks = [r for r in records if 'INI_SECTION_KALIER' in r]
        self.assertEqual(len(blocks), 1)

    def test_unknown_action_emits_section_and_does_not_crash(self):
        code, started, records = self._capture_main({
            'action': 'definitely_not_an_action', 'target_agents': ['x_1'],
        })
        self.assertEqual(started, ['x_1'])
        blocks = [r for r in records if 'INI_SECTION_KALIER' in r]
        self.assertEqual(len(blocks), 1)
        self.assertTrue(any('Unknown action' in r for r in records))
        self.assertEqual(code, 0)


# ---------------------------------------------------------------------------
# Registry / contract / config / docs integration
# ---------------------------------------------------------------------------


class RegistryIntegrationTests(SimpleTestCase):
    def _read(self, *parts):
        path = os.path.join(os.path.dirname(__file__), *parts)
        with open(path, 'r', encoding='utf-8') as f:
            return f.read()

    def test_chat_wrapped_agent_spec_is_registered(self):
        from agent.chat_agent_registry import WRAPPED_CHAT_AGENT_BY_TOOL_NAME
        spec = WRAPPED_CHAT_AGENT_BY_TOOL_NAME.get('chat_agent_kalier')
        self.assertIsNotNone(spec, 'chat_agent_kalier must be registered')
        self.assertEqual(spec.key, 'kalier')
        self.assertEqual(spec.template_dir, 'kalier')
        self.assertEqual(spec.tool_description, 'Chat-Agent-Kalier')
        self.assertEqual(spec.display_name, 'Kalier')
        self.assertTrue(spec.long_running)

    def test_exec_report_tool_row_is_registered(self):
        from agent.mcp_agent import _EXEC_REPORT_TOOLS
        self.assertEqual(_EXEC_REPORT_TOOLS.get('chat_agent_kalier'), ('kalier', 'Kalier'))

    def test_get_mcp_tools_binds_chat_agent_kalier(self):
        from agent.tools import get_mcp_tools
        names = [t.name for t in get_mcp_tools()]
        self.assertIn('chat_agent_kalier', names)

    def test_agent_contract_resolves_kalier(self):
        from agent.services.agent_contracts import get_agent_contract
        contract = get_agent_contract('kalier')
        self.assertEqual(contract.agent_type, 'kalier')
        self.assertEqual(contract.output_field_by_slot.get(0), 'target_agents')
        self.assertFalse(contract.never_starts_targets)

    def test_contract_redacts_hydra_password(self):
        from agent.services.agent_contracts import get_agent_contract, redact_config_for_export
        contract = get_agent_contract('kalier')
        self.assertIn('password', contract.secret_paths)
        redacted = redact_config_for_export('kalier', {'password': 'hunter2', 'target': '10.0.0.5'})
        self.assertEqual(redacted['password'], '__REDACTED__')
        self.assertEqual(redacted['target'], '10.0.0.5')

    def test_parametrizer_fields_registered(self):
        from agent.services.agent_contracts import get_parametrizer_source_fields
        fields = get_parametrizer_source_fields().get('kalier')
        self.assertIsNotNone(fields)
        for expected in ('action', 'endpoint', 'method', 'subject', 'return_code',
                         'success', 'timed_out', 'server_url', 'response_body'):
            self.assertIn(expected, fields)

    def test_name_variants_normalize(self):
        from agent.services.agent_paths import normalize_agent_type
        self.assertEqual(normalize_agent_type('Kalier'), 'kalier')
        self.assertEqual(normalize_agent_type('kalier-1'), 'kalier_1')

    def test_url_route_exists(self):
        from django.urls import reverse
        url = reverse('update_kalier_connection', kwargs={'agent_name': 'kalier-1'})
        self.assertIn('update_kalier_connection', url)

    def test_capability_hints_present(self):
        from agent.capability_registry import _EXTRA_HINTS_BY_TOOL_NAME
        hints = _EXTRA_HINTS_BY_TOOL_NAME.get('chat_agent_kalier')
        self.assertIsNotNone(hints)
        for token in ('kali', 'nmap', 'pentest', 'metasploit'):
            self.assertIn(token, hints)

    def test_canvas_classmap_and_js_wiring(self):
        core = self._read('static', 'agent', 'js', 'acp-canvas-core.js')
        self.assertIn("'kalier': 'kalier-agent'", core)
        self.assertIn("'kalier'", core)
        connectors = self._read('static', 'agent', 'js', 'acp-agent-connectors.js')
        self.assertIn('async function updateKalierConnection', connectors)
        undo = self._read('static', 'agent', 'js', 'acp-canvas-undo.js')
        self.assertIn('updateKalierConnection', undo)
        fileio = self._read('static', 'agent', 'js', 'acp-file-io.js')
        self.assertIn("case 'kalier':", fileio)
        chat = self._read('static', 'agent', 'js', 'agent_page_chat.js')
        self.assertIn("lower === 'kalier'", chat)

    def test_css_gradient_is_unique_and_monochrome_green(self):
        css = self._read('static', 'agent', 'css', 'agentic_control_panel.css')
        gradient = '#000000 0%, #00471B 33%, #00892A 66%, #39FF14 100%'
        self.assertEqual(css.count(gradient), 1,
                         'The Kalier canvas gradient must be unique to its rule')
        self.assertIn('.canvas-item.kalier-agent', css)
        exec_css = self._read('static', 'agent', 'css', 'agent_page.css')
        self.assertIn('.exec-report-caption-kalier', exec_css)
        self.assertIn('.exec-report-kalier thead th', exec_css)

    def test_config_yaml_defaults(self):
        cfg = yaml.safe_load(self._read('agents', 'kalier', 'config.yaml'))
        self.assertEqual(cfg.get('action'), 'nmap')
        self.assertEqual(cfg.get('server_url'), 'http://127.0.0.1:5000')
        self.assertEqual(cfg.get('mode'), 'dir')
        self.assertEqual(cfg.get('target_agents'), [])
        self.assertEqual(cfg.get('source_agents'), [])
        # Every action's params must exist as keys (the wrapped-tool config
        # writer ignores any requested key not already present in config.yaml).
        for key in ('command', 'target', 'url', 'scan_type', 'ports', 'wordlist',
                    'data', 'module', 'options', 'service', 'username',
                    'username_file', 'password', 'password_file', 'hash_file',
                    'format', 'additional_args', 'timeout'):
            self.assertIn(key, cfg, f'config.yaml missing key {key!r}')

    def test_agents_descriptions_has_kalier_row(self):
        # agents_descriptions.md ships at the repo root (two levels above the
        # agent app); build.py also copies it next to the frozen exe.
        candidates = [
            os.path.join(os.path.dirname(__file__), '..', '..', 'agents_descriptions.md'),
            os.path.join(os.path.dirname(__file__), '..', 'agents_descriptions.md'),
        ]
        path = next((p for p in candidates if os.path.exists(p)), candidates[0])
        with open(path, 'r', encoding='utf-8') as f:
            self.assertIn('| **Kalier** |', f.read())

    def test_agentic_skill_has_kalier_entry(self):
        skill = self._read('agents', 'flowcreator', 'agentic_skill.md')
        self.assertIn('### 66. Kalier', skill)


# ---------------------------------------------------------------------------
# Parametrizer round-trip — read INI_SECTION_KALIER from Kalier output
# ---------------------------------------------------------------------------


@lru_cache(maxsize=1)
def _load_parametrizer_module():
    module_path = os.path.join(
        os.path.dirname(__file__), 'agents', 'parametrizer', 'parametrizer.py',
    )
    spec = importlib.util.spec_from_file_location('agent_parametrizer_for_kalier_tests', module_path)
    module = importlib.util.module_from_spec(spec)
    root = logging.getLogger()
    handlers_before = list(root.handlers)
    cwd = os.getcwd()
    try:
        spec.loader.exec_module(module)
    finally:
        os.chdir(cwd)
        for handler in list(root.handlers):
            if handler not in handlers_before:
                root.removeHandler(handler)
    return module


class ParametrizerRoundTripTests(SimpleTestCase):
    def setUp(self):
        self.p = _load_parametrizer_module()

    def test_kalier_registered_as_section_source(self):
        self.assertIn('kalier', self.p.SECTION_AGENT_TYPES)
        self.assertIn('kalier', self.p.OUTPUT_PARSERS)

    def test_source_base_resolves_cardinal(self):
        self.assertEqual(self.p.get_source_base_name('kalier_3'), 'kalier')
        self.assertEqual(self.p.get_source_base_name('kalier'), 'kalier')

    def test_parser_extracts_all_kalier_fields(self):
        section = (
            'INI_SECTION_KALIER<<<\n'
            'action: nmap\nendpoint: api/tools/nmap\nmethod: POST\nsubject: 10.0.0.5\n'
            'return_code: 0\nsuccess: true\ntimed_out: false\nserver_url: http://127.0.0.1:5000\n\n'
            'PORT 22/tcp open ssh\n80/tcp open http\n'
            '>>>END_SECTION_KALIER'
        )
        parsed = self.p.OUTPUT_PARSERS['kalier'](section)
        self.assertTrue(parsed)
        fields = parsed[0]
        self.assertEqual(fields['action'], 'nmap')
        self.assertEqual(fields['success'], 'true')
        self.assertEqual(fields['subject'], '10.0.0.5')
        self.assertIn('22/tcp open ssh', fields['response_body'])

    def test_views_registration(self):
        from agent import views
        self.assertIn('kalier', views.PARAMETRIZER_SOURCE_OUTPUT_FIELDS)
        self.assertIn('kalier', views.PARAMETRIZER_ALLOWED_SOURCES)


# ---------------------------------------------------------------------------
# Planner selection — chat_agent_kalier wins on pentest prompts
# ---------------------------------------------------------------------------


class PlannerSelectionTests(SimpleTestCase):
    def _tools(self):
        from types import SimpleNamespace
        from agent.chat_agent_registry import WRAPPED_CHAT_AGENT_BY_TOOL_NAME
        kalier_desc = WRAPPED_CHAT_AGENT_BY_TOOL_NAME['chat_agent_kalier'].purpose

        def mk(n, d):
            return SimpleNamespace(name=n, description=d)
        return [
            mk('chat_agent_kalier', kalier_desc),
            mk('chat_agent_crawler', 'Crawl any URL and capture its content.'),
            mk('execute_command', 'Execute any shell command.'),
            mk('chat_agent_apirer', 'Call any HTTP REST API endpoint.'),
            mk('chat_agent_notifier', 'Show a desktop notification.'),
        ]

    def test_selected_on_pentest_prompts(self):
        from agent.capability_registry import select_tools_for_request
        prompts = [
            'Run an nmap scan of 10.0.0.5 and a kali pentest of the target',
            'Use Kali to enumerate the SMB shares with enum4linux on 10.0.0.5',
            'crack this hash with john the ripper',
            'run metasploit against the box',
        ]
        for p in prompts:
            sel = [t.name for t in select_tools_for_request(p, self._tools(), max_selected=3)]
            self.assertIn('chat_agent_kalier', sel, f'kalier should be selected for: {p!r}')

    def test_not_selected_on_unrelated_prompt(self):
        from agent.capability_registry import select_tools_for_request
        sel = [t.name for t in select_tools_for_request(
            'show me a desktop notification that the backup finished', self._tools(), max_selected=2)]
        self.assertNotIn('chat_agent_kalier', sel)


# ---------------------------------------------------------------------------
# Flow compiler — FlowCreator's output path compiles + redacts for Kalier
# ---------------------------------------------------------------------------


class FlowCompilerIntegrationTests(SimpleTestCase):
    def _payload(self):
        return {
            'schemaVersion': 2,
            'nodes': [
                {'id': 'starter-1', 'text': 'Starter', 'configData': {}},
                {'id': 'kalier-1', 'text': 'Kalier',
                 'configData': {'action': 'nmap', 'target': '10.0.0.5', 'password': 'hunter2'}},
                {'id': 'parametrizer-1', 'text': 'Parametrizer', 'configData': {}},
                {'id': 'kalier-2', 'text': 'Kalier',
                 'configData': {'action': 'gobuster', 'url': 'http://10.0.0.5'}},
                {'id': 'ender-1', 'text': 'Ender', 'configData': {}},
            ],
            'connections': [
                {'sourceId': 'starter-1', 'targetId': 'kalier-1'},
                {'sourceId': 'kalier-1', 'targetId': 'parametrizer-1'},
                {'sourceId': 'parametrizer-1', 'targetId': 'kalier-2'},
                {'sourceId': 'kalier-2', 'targetId': 'ender-1'},
            ],
        }

    def test_kalier_flow_wires_correctly(self):
        from agent.services.flow_compiler import compile_flow_payload
        res = compile_flow_payload(self._payload(), write=False)
        cfg = {a['folder_name']: a['config'] for a in res['agents']}
        self.assertEqual(cfg['starter_1'].get('target_agents'), ['kalier_1'])
        self.assertEqual(cfg['kalier_1'].get('target_agents'), ['parametrizer_1'])
        # Parametrizer reads FROM kalier_1 and writes TO kalier_2.
        self.assertEqual(cfg['parametrizer_1'].get('source_agent'), 'kalier_1')
        self.assertEqual(cfg['parametrizer_1'].get('target_agent'), 'kalier_2')
        self.assertEqual(cfg['kalier_2'].get('source_agents'), ['parametrizer_1'])

    def test_flw_export_redacts_password(self):
        from agent.services.flow_spec import normalize_flow_payload, flow_spec_to_legacy_json
        spec = normalize_flow_payload(self._payload())
        legacy = flow_spec_to_legacy_json(spec, redact=True)
        blob = json.dumps(legacy)
        self.assertNotIn('hunter2', blob)
        self.assertIn('__REDACTED__', blob)


# ---------------------------------------------------------------------------
# Skill — kali-pentest companion
# ---------------------------------------------------------------------------


class KaliPentestSkillTests(SimpleTestCase):
    def test_skill_discovered_and_parsed(self):
        from agent.skills.registry import skill_registry
        skill_registry.reload()
        skill = skill_registry.get('kali-pentest')
        self.assertIsNotNone(skill, 'kali-pentest skill must be discovered from disk')

    def test_skill_requires_kalier_tool(self):
        from agent.skills.registry import skill_registry
        skill_registry.reload()
        skill = skill_registry.get('kali-pentest')
        self.assertIn('chat_agent_kalier', getattr(skill, 'requires_tools', []) or [])

    def test_skill_file_frontmatter_valid(self):
        path = os.path.join(os.path.dirname(__file__), 'skills_pkg', 'kali_pentest', 'SKILL.md')
        self.assertTrue(os.path.exists(path))
        with open(path, 'r', encoding='utf-8') as f:
            text = f.read()
        self.assertIn('name: kali-pentest', text)
        self.assertIn('runtime: in-process', text)


# ---------------------------------------------------------------------------
# Demo prompts + migration presence (need the test DB)
# ---------------------------------------------------------------------------


class DemoPromptTests(TestCase):
    def test_three_kali_demo_prompts_seeded(self):
        from agent.models import Prompt
        for pid in (57, 58, 59):
            p = Prompt.objects.filter(idPrompt=pid).first()
            self.assertIsNotNone(p, f'prompt {pid} must be seeded by migration 0099')
            self.assertEqual(p.promptName, f'prompt-{pid}')
            self.assertIn('KALI', p.promptContent)

    def test_prompt_catalog_is_contiguous(self):
        from agent.models import Prompt
        ids = sorted(Prompt.objects.values_list('idPrompt', flat=True))
        gaps = [n for n in range(ids[0], ids[-1] + 1) if n not in ids]
        self.assertEqual(gaps, [], 'the prompts catalog must stay gap-free for the dropdown')
        self.assertGreaterEqual(ids[-1], 59)


class MigrationPresenceTests(TestCase):
    def test_agent_row_seeded_by_migration_0097(self):
        from agent.models import Agent
        self.assertTrue(
            Agent.objects.filter(agentDescription='Kalier').exists(),
            "Migration 0097 must seed an Agent row with agentDescription='Kalier'",
        )

    def test_tool_row_seeded_by_migration_0098(self):
        from agent.models import Tool
        self.assertTrue(
            Tool.objects.filter(toolDescription='Chat-Agent-Kalier').exists(),
            "Migration 0098 must seed a Tool row with toolDescription='Chat-Agent-Kalier'",
        )


if __name__ == '__main__':
    unittest.main()
