# ═══════════════════════════════════════════════════════════════════
#   ✦  T L A M A T I N I  ✦   —   "one who knows"
#
#   Created by  Angela López Mendoza   ·   @angelahack1
#   Developer · Architect · Creator of Tlamatini
#
#   Every line of this file was written by Angela López Mendoza.
# ═══════════════════════════════════════════════════════════════════
#   Tlamatini Author Banner — do not remove (releases scrub the name automatically)
"""Automated tests for the Zavuerer workflow agent and its surrounding wiring.

Zavuerer bridges Tlamatini to **Zavu** (https://www.zavu.dev) — ONE unified
messaging API for SMS / WhatsApp / Telegram / Email / Voice. It is a standalone
pool agent under ``agent/agents/zavuerer/`` that runs as a separate Python
subprocess, so — exactly like the Kalier / Windower / De-Compresser test modules
— it is loaded through ``importlib.util.spec_from_file_location`` with a cwd
save/restore so its module-level ``os.chdir`` + ``open(LOG_FILE_PATH)`` side
effects land in its own directory.

The agent talks to the Zavu REST API over HTTP using only the Python stdlib
(``urllib``). Tests NEVER touch a real network: ``urllib.request.urlopen`` is
mocked, so the payload builder, the response/envelope normaliser, and every
transport error path (HTTPError / URLError) are exercised deterministically.

Covers:
- _ACTION_ROUTES + _VALID_CHANNELS
- _build_payload: send body shape (to/text/channel/fallbackEnabled + optional
  subject/from), health empty body; _coerce_bool
- call_zavu_api: success envelope, failed-status envelope, HTTPError (401 hint),
  URLError (unreachable)
- _emit_section: single atomic INI_SECTION_ZAVUERER block, KV header + body
- Registry: ChatWrappedAgentSpec, Exec Report row, get_mcp_tools binding
- Contract + secret_paths (zavu_api_key redaction), Parametrizer fields
- URL route, capability hints, DB rows (Agent / Tool / demo Prompt)
- File wiring: JS (classMap / connectors / undo / file-io / chat), CSS gradient
  (unique) + exec-report rules, parametrizer.py SECTION_AGENT_TYPES, config.yaml
  defaults, agents_descriptions row, agentic_skill #83, eslint global
"""

import importlib.util
import io
import json
import logging
import os
import unittest
import urllib.error
from functools import lru_cache
from unittest.mock import patch

import yaml
from django.test import SimpleTestCase, TestCase


@lru_cache(maxsize=1)
def _load_zavuerer_module():
    module_path = os.path.join(
        os.path.dirname(__file__), 'agents', 'zavuerer', 'zavuerer.py',
    )
    spec = importlib.util.spec_from_file_location(
        'agent_zavuerer_module_for_tests', module_path,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f'Unable to load Zavuerer module from {module_path}')

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


# ---------------------------------------------------------------------------
# Action routes + payload builder
# ---------------------------------------------------------------------------


class ZavuererRoutesAndPayloadTests(SimpleTestCase):
    def setUp(self):
        self.z = _load_zavuerer_module()

    def test_action_routes(self):
        self.assertEqual(self.z._ACTION_ROUTES['send'], ('POST', 'messages'))
        self.assertEqual(self.z._ACTION_ROUTES['health'], ('GET', 'health'))

    def test_valid_channels(self):
        for ch in ('auto', 'sms', 'whatsapp', 'telegram', 'voice', 'email'):
            self.assertIn(ch, self.z._VALID_CHANNELS)

    def test_build_payload_send_core(self):
        body = self.z._build_payload('send', {
            'to': '+14155551234', 'text': 'hi', 'channel': 'auto', 'fallback': True,
        })
        self.assertEqual(body['to'], '+14155551234')
        self.assertEqual(body['text'], 'hi')
        self.assertEqual(body['channel'], 'auto')
        self.assertTrue(body['fallbackEnabled'])
        self.assertNotIn('subject', body)
        self.assertNotIn('from', body)

    def test_build_payload_send_optional(self):
        body = self.z._build_payload('send', {
            'to': 'a@b.com', 'text': 'hi', 'channel': 'email',
            'subject': 'Hello', 'from_sender': 'me', 'fallback': False,
        })
        self.assertEqual(body['subject'], 'Hello')
        self.assertEqual(body['from'], 'me')
        self.assertFalse(body['fallbackEnabled'])

    def test_build_payload_health_empty(self):
        self.assertEqual(self.z._build_payload('health', {}), {})

    def test_coerce_bool(self):
        self.assertTrue(self.z._coerce_bool('true'))
        self.assertTrue(self.z._coerce_bool(True))
        self.assertTrue(self.z._coerce_bool('yes'))
        self.assertFalse(self.z._coerce_bool('false'))
        self.assertFalse(self.z._coerce_bool(''))


# ---------------------------------------------------------------------------
# call_zavu_api — HTTP envelope normalisation (urlopen mocked)
# ---------------------------------------------------------------------------


class ZavuererCallApiTests(SimpleTestCase):
    def setUp(self):
        self.z = _load_zavuerer_module()

    def _cfg(self, **over):
        base = {
            'zavu_api_key': 'k_test', 'zavu_base_url': 'https://api.zavu.dev/v1',
            'to': '+14155551234', 'text': 'hi', 'channel': 'auto',
            'fallback': True, 'timeout': 30,
        }
        base.update(over)
        return base

    def test_send_success(self):
        resp = json.dumps({'id': 'msg_123', 'channel': 'whatsapp', 'status': 'queued'}).encode()
        with patch('urllib.request.urlopen', return_value=_FakeResp(resp, 200)):
            out = self.z.call_zavu_api('send', self._cfg())
        self.assertTrue(out['ok'])
        self.assertTrue(out['success'])
        self.assertEqual(out['message_id'], 'msg_123')
        self.assertEqual(out['channel'], 'whatsapp')
        self.assertEqual(out['status'], 'queued')

    def test_send_failed_status_is_not_success(self):
        resp = json.dumps({'id': 'm1', 'channel': 'sms', 'status': 'failed'}).encode()
        with patch('urllib.request.urlopen', return_value=_FakeResp(resp, 200)):
            out = self.z.call_zavu_api('send', self._cfg())
        self.assertTrue(out['ok'])      # HTTP round-trip happened
        self.assertFalse(out['success'])  # but the message failed

    def test_http_error_401_hints_key(self):
        err = urllib.error.HTTPError(
            'https://api.zavu.dev/v1/messages', 401, 'Unauthorized', {},
            io.BytesIO(b'{"error":"bad key"}'),
        )
        with patch('urllib.request.urlopen', side_effect=err):
            out = self.z.call_zavu_api('send', self._cfg())
        self.assertFalse(out['ok'])
        self.assertFalse(out['success'])
        self.assertEqual(out['status'], 'failed')
        self.assertIn('zavu.dev', out['response_body'])

    def test_urlerror_unreachable(self):
        with patch('urllib.request.urlopen', side_effect=urllib.error.URLError('refused')):
            out = self.z.call_zavu_api('send', self._cfg())
        self.assertFalse(out['ok'])
        self.assertEqual(out['status'], 'unreachable')
        self.assertIn('Cannot reach', out['response_body'])


# ---------------------------------------------------------------------------
# _emit_section — atomic INI_SECTION_ZAVUERER
# ---------------------------------------------------------------------------


class ZavuererEmitSectionTests(SimpleTestCase):
    def setUp(self):
        self.z = _load_zavuerer_module()

    def test_emit_section_atomic(self):
        records = []
        handler = logging.Handler()
        handler.emit = lambda r: records.append(r.getMessage())
        root = logging.getLogger()
        root.addHandler(handler)
        try:
            self.z._emit_section({
                'action': 'send', 'channel': 'sms', 'to': '+1', 'status': 'queued',
                'message_id': 'm1', 'success': 'true', 'base_url': 'x',
            }, 'body here')
        finally:
            root.removeHandler(handler)
        blocks = [r for r in records if 'INI_SECTION_ZAVUERER' in r]
        self.assertEqual(len(blocks), 1)
        block = blocks[0]
        self.assertIn('INI_SECTION_ZAVUERER<<<', block)
        self.assertIn('>>>END_SECTION_ZAVUERER', block)
        self.assertIn('status: queued', block)
        self.assertIn('body here', block)


# ---------------------------------------------------------------------------
# Registry / Exec Report / Contract / URL / hints / DB wiring
# ---------------------------------------------------------------------------


class ZavuererWiringTests(TestCase):
    def test_registry_spec(self):
        from agent.chat_agent_registry import WRAPPED_CHAT_AGENT_BY_TOOL_NAME
        spec = WRAPPED_CHAT_AGENT_BY_TOOL_NAME.get('chat_agent_zavuerer')
        self.assertIsNotNone(spec, 'chat_agent_zavuerer must be registered')
        self.assertEqual(spec.key, 'zavuerer')
        self.assertEqual(spec.template_dir, 'zavuerer')
        self.assertEqual(spec.tool_description, 'Chat-Agent-Zavuerer')
        self.assertEqual(spec.display_name, 'Zavuerer')

    def test_exec_report_row(self):
        from agent.mcp_agent import _EXEC_REPORT_TOOLS
        self.assertEqual(_EXEC_REPORT_TOOLS.get('chat_agent_zavuerer'), ('zavuerer', 'Zavuerer'))

    def test_get_mcp_tools_binds_chat_agent_zavuerer(self):
        from agent.tools import get_mcp_tools
        names = {t.name for t in get_mcp_tools()}
        self.assertIn('chat_agent_zavuerer', names)

    def test_agent_contract_resolves_zavuerer(self):
        from agent.services.agent_contracts import get_agent_contract
        contract = get_agent_contract('zavuerer')
        self.assertEqual(contract.agent_type, 'zavuerer')
        self.assertIn('zavu_api_key', contract.secret_paths)

    def test_parametrizer_source_fields(self):
        from agent.services.agent_contracts import get_parametrizer_source_fields
        fields = get_parametrizer_source_fields().get('zavuerer')
        self.assertTrue(fields)
        for f in ('action', 'channel', 'to', 'status', 'message_id', 'success', 'response_body'):
            self.assertIn(f, fields)

    def test_url_route(self):
        from django.urls import reverse
        url = reverse('update_zavuerer_connection', kwargs={'agent_name': 'zavuerer-1'})
        self.assertIn('update_zavuerer_connection', url)

    def test_capability_hints(self):
        from agent.capability_registry import _EXTRA_HINTS_BY_TOOL_NAME
        hints = _EXTRA_HINTS_BY_TOOL_NAME.get('chat_agent_zavuerer')
        self.assertTrue(hints)
        self.assertIn('zavuerer', hints)

    def test_db_rows_present(self):
        from agent.models import Agent, Prompt, Tool
        self.assertTrue(Agent.objects.filter(agentDescription='Zavuerer').exists())
        self.assertTrue(Tool.objects.filter(toolDescription='Chat-Agent-Zavuerer').exists())
        self.assertTrue(Prompt.objects.filter(promptContent__contains='ZAVUERER').exists())


# ---------------------------------------------------------------------------
# File-based wiring (CSS / JS / docs / config) — read straight from disk
# ---------------------------------------------------------------------------


class ZavuererFileWiringTests(SimpleTestCase):
    def _read(self, *parts):
        path = os.path.join(os.path.dirname(__file__), *parts)
        with open(path, encoding='utf-8') as f:
            return f.read()

    def _read_root(self, *parts):
        root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
        with open(os.path.join(root, *parts), encoding='utf-8') as f:
            return f.read()

    def test_js_classmap_connectors_handlers(self):
        core = self._read('static', 'agent', 'js', 'acp-canvas-core.js')
        self.assertIn("'zavuerer': 'zavuerer-agent'", core)
        self.assertIn("=== 'zavuerer'", core)
        conn = self._read('static', 'agent', 'js', 'acp-agent-connectors.js')
        self.assertIn('async function updateZavuererConnection', conn)
        self.assertIn('/agent/update_zavuerer_connection/', conn)
        undo = self._read('static', 'agent', 'js', 'acp-canvas-undo.js')
        self.assertIn('updateZavuererConnection', undo)
        fileio = self._read('static', 'agent', 'js', 'acp-file-io.js')
        self.assertIn("case 'zavuerer'", fileio)
        chat = self._read('static', 'agent', 'js', 'agent_page_chat.js')
        self.assertIn("lower === 'zavuerer'", chat)

    def test_css_gradient_unique_and_exec_report(self):
        panel = self._read('static', 'agent', 'css', 'agentic_control_panel.css')
        self.assertIn('.canvas-item.zavuerer-agent', panel)
        grad = 'linear-gradient(135deg, #14B8A6 0%, #3B82F6 33%, #8B5CF6 66%, #F43F5E 100%)'
        self.assertEqual(panel.count(grad), 1, 'The Zavuerer canvas gradient must be unique to its rule')
        page = self._read('static', 'agent', 'css', 'agent_page.css')
        self.assertIn('.exec-report-caption-zavuerer', page)
        self.assertIn('.exec-report-zavuerer thead th', page)
        self.assertIn('.exec-report-zavuerer .exec-report-cmd', page)

    def test_parametrizer_section_types(self):
        para = self._read('agents', 'parametrizer', 'parametrizer.py')
        self.assertIn("'zavuerer'", para)

    def test_config_yaml_defaults(self):
        cfg = yaml.safe_load(self._read('agents', 'zavuerer', 'config.yaml'))
        for key in ('action', 'zavu_api_key', 'zavu_base_url', 'to', 'channel',
                    'text', 'fallback', 'timeout', 'source_agents', 'target_agents'):
            self.assertIn(key, cfg)
        self.assertEqual(cfg['action'], 'send')
        # NEVER hardcode a credential — the key default must be an empty string.
        self.assertEqual(cfg['zavu_api_key'], '')

    def test_docs(self):
        descs = self._read_root('agents_descriptions.md')
        self.assertIn('| **Zavuerer** |', descs)
        skill = self._read('agents', 'flowcreator', 'agentic_skill.md')
        self.assertIn('### 83. Zavuerer', skill)

    def test_eslint_global(self):
        cfg = self._read_root('eslint.config.mjs')
        self.assertIn('updateZavuererConnection', cfg)


class ZavuererKeyWizardTests(TestCase):
    """The Access Keys Wizard + global zavu_api_key injection for chat_agent_zavuerer."""

    def test_config_json_has_zavu_api_key(self):
        from agent.config_loader import load_config
        cfg = load_config(force_reload=True)
        self.assertIn('zavu_api_key', cfg)

    def test_wizard_exposes_zavu_field(self):
        from agent.access_key_wizard import AGENT_YAML_RELATIVE_PATHS, FIELD_BY_KEY
        self.assertIn('ZAVU_API_KEY', FIELD_BY_KEY)
        field = FIELD_BY_KEY['ZAVU_API_KEY']
        self.assertEqual(field.json_key, 'zavu_api_key')
        self.assertEqual(field.yaml_rules, (('zavuerer', ('zavu_api_key',), True),))
        self.assertIn('zavuerer', AGENT_YAML_RELATIVE_PATHS)

    def test_seed_injects_configured_zavu_api_key(self):
        from unittest.mock import patch
        from agent import tools
        cfg = {'zavu_api_key': ''}
        with patch.object(tools, 'get_config_value', return_value='sk-zavu-test-123'):
            tools._seed_global_agent_defaults('zavuerer', cfg)
        self.assertEqual(cfg['zavu_api_key'], 'sk-zavu-test-123')

    def test_seed_empty_key_leaves_blank(self):
        from unittest.mock import patch
        from agent import tools
        cfg = {'zavu_api_key': ''}
        with patch.object(tools, 'get_config_value', return_value=''):
            tools._seed_global_agent_defaults('zavuerer', cfg)
        self.assertEqual(cfg['zavu_api_key'], '')

    def test_catalog_has_setup_and_two_samples(self):
        from agent.models import Prompt
        self.assertTrue(Prompt.objects.filter(promptContent__contains='set up **Zavuerer** with me ONE step').exists())
        self.assertTrue(Prompt.objects.filter(promptContent__contains='send a quick **SMS**').exists())
        self.assertTrue(Prompt.objects.filter(promptContent__contains='reach me the smart way with **Zavuerer**').exists())


if __name__ == '__main__':
    unittest.main()
