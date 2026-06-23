"""Tests for the long-running chat-bridge bot — TeleTlamatini — focused on the
post-"Ask Execs" adaptation (2026-06-04).

(WhatsTlamatini was retired; receiving is now handled by Whatsapper directly, so
the chat-bridge bot suite covers only TeleTlamatini.)

TeleTlamatini is a pool subprocess, so it is loaded through
``importlib.util.spec_from_file_location`` with a cwd save/restore so its
module-level ``os.chdir`` + ``open(LOG_FILE_PATH)`` side effects don't leak
into the test process (same convention as ``test_kalier_agent.py``).

What these tests pin (the contract the adaptation must keep):

1. The WS frame classifier explicitly SKIPS the Ask-Execs UI-control frames
   (``exec-permission-request`` / ``exec-permission-response``) so a prompt
   meant for a browser on the same Tlamatini account can never be mistaken for
   a partial/final answer on the bot's socket.
2. The classifier still detects the assembled FINAL frame via the
   ``multi_turn_used`` / ``answer_success`` extras (regression guard).
3. ``_resolve_tlamatini_cfg`` surfaces ``acpx_enabled``, defaulting to False
   when absent.
4. The outbound chat payload HARD-PINS ``ask_execs_enabled: False`` and carries
   ``acpx_enabled`` — verified end-to-end through ``_send_and_collect`` with a
   fake WebSocket.
5. The shipped ``config.yaml`` file carries ``acpx_enabled: true`` +
   ``multi_turn_enabled: true``.
"""

import asyncio
import importlib.util
import json
import logging
import os
import unittest
from functools import lru_cache

import yaml
from django.test import SimpleTestCase


def _load_agent_module(agent_name: str, alias: str):
    module_path = os.path.join(
        os.path.dirname(__file__), 'agents', agent_name, f'{agent_name}.py',
    )
    spec = importlib.util.spec_from_file_location(alias, module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f'Unable to load {agent_name} module from {module_path}')
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


@lru_cache(maxsize=1)
def _load_tele():
    return _load_agent_module('teletlamatini', 'agent_teletlamatini_for_tests')


def _config_path(agent_name: str) -> str:
    return os.path.join(
        os.path.dirname(__file__), 'agents', agent_name, 'config.yaml',
    )


class _FakeWS:
    """Minimal async stand-in for a websockets client connection.

    ``send`` records the decoded payload; ``recv`` yields pre-queued raw frames
    then blocks forever (the collect loop breaks on the FINAL frame before it
    would ever exhaust the queue)."""

    def __init__(self, frames):
        self.sent = []
        self._frames = list(frames)

    async def send(self, raw):
        self.sent.append(json.loads(raw))

    async def recv(self):
        if self._frames:
            return self._frames.pop(0)
        # No more frames — block so the collect loop relies on the FINAL break.
        await asyncio.sleep(3600)

    async def close(self):
        return None


# ---------------------------------------------------------------------------
# 1 + 2 — frame classifier
# ---------------------------------------------------------------------------

class FrameClassifierTests(SimpleTestCase):
    def setUp(self):
        self.tele = _load_tele()

    def test_exec_permission_frames_are_skipped(self):
        mod = self.tele
        # The consumer's exec_permission_request handler emits exactly this
        # shape: {'type': 'exec-permission-request', 'detail': {...}}.
        req = {'type': 'exec-permission-request', 'detail': {'tool_name': 'execute_command'}}
        resp = {'type': 'exec-permission-response', 'request_id': 'abc', 'decision': 'deny'}
        self.assertEqual(mod._classify_frame(req), 'skip')
        self.assertEqual(mod._classify_frame(resp), 'skip')
        # And both types are registered explicitly (not just incidentally
        # skipped via the empty-message path).
        self.assertIn('exec-permission-request', mod._SPECIAL_TYPES_TO_SKIP)
        self.assertIn('exec-permission-response', mod._SPECIAL_TYPES_TO_SKIP)

    def test_final_frame_still_detected(self):
        mod = self.tele
        final_mt = {'username': 'Tlamatini', 'message': 'done', 'multi_turn_used': True}
        final_as = {'username': 'Tlamatini', 'message': 'done', 'answer_success': True}
        self.assertEqual(mod._classify_frame(final_mt), 'final')
        self.assertEqual(mod._classify_frame(final_as), 'final')

    def test_plain_answer_is_partial(self):
        mod = self.tele
        frame = {'username': 'Tlamatini', 'message': 'Your CPU is at 12%.'}
        self.assertEqual(mod._classify_frame(frame), 'partial')


# ---------------------------------------------------------------------------
# 3 — ACPX in the config resolver
# ---------------------------------------------------------------------------

class ResolverAcpxParityTests(SimpleTestCase):
    def setUp(self):
        self.tele = _load_tele()

    def test_acpx_enabled_surfaced(self):
        mod = self.tele
        cfg = mod._resolve_tlamatini_cfg({'tlamatini': {'acpx_enabled': True}})
        self.assertIn('acpx_enabled', cfg)
        self.assertTrue(cfg['acpx_enabled'])

    def test_acpx_defaults_false_when_absent(self):
        mod = self.tele
        cfg = mod._resolve_tlamatini_cfg({'tlamatini': {}})
        self.assertFalse(cfg['acpx_enabled'])

    def test_acpx_without_multiturn_does_not_crash(self):
        # The resolver only warns (non-fatal) in this combination.
        mod = self.tele
        cfg = mod._resolve_tlamatini_cfg(
            {'tlamatini': {'acpx_enabled': True, 'multi_turn_enabled': False}}
        )
        self.assertTrue(cfg['acpx_enabled'])
        self.assertFalse(cfg['multi_turn_enabled'])


# ---------------------------------------------------------------------------
# 4 — outbound payload (end-to-end through _send_and_collect)
# ---------------------------------------------------------------------------

class OutboundPayloadTests(SimpleTestCase):
    def _run_collect(self, mod, acpx_enabled):
        final_frame = json.dumps({
            'username': 'Tlamatini', 'message': '<p>ok</p>', 'multi_turn_used': True,
        })
        ws = _FakeWS([final_frame])
        bridge = mod.TlamatiniBridge(
            base_url='http://127.0.0.1:8000',
            ws_url='ws://127.0.0.1:8000/ws/agent/',
            username='bot',
            password='pw',
            multi_turn_enabled=True,
            exec_report_enabled=True,
            acpx_enabled=acpx_enabled,
            total_timeout=10,
            idle_timeout=1,
        )
        bridge._ws = ws
        html, counters = asyncio.run(bridge._send_and_collect('[test]', 'hi'))
        return ws.sent[0], html, counters

    def test_payload_pins_ask_execs_false_and_carries_acpx(self):
        mod = _load_tele()
        payload, html, counters = self._run_collect(mod, acpx_enabled=True)
        # Ask-Execs must always be explicitly OFF (a bot can't answer a
        # browser Proceed/Deny modal).
        self.assertIn('ask_execs_enabled', payload)
        self.assertIs(payload['ask_execs_enabled'], False)
        # ACPX: the flag is forwarded verbatim.
        self.assertTrue(payload['acpx_enabled'])
        self.assertTrue(payload['multi_turn_enabled'])
        self.assertTrue(payload['exec_report_enabled'])
        # The FINAL frame was collected.
        self.assertEqual(html, '<p>ok</p>')
        self.assertEqual(counters['final'], 1)

    def test_payload_respects_acpx_off(self):
        mod = _load_tele()
        payload, _html, _counters = self._run_collect(mod, acpx_enabled=False)
        self.assertFalse(payload['acpx_enabled'])
        self.assertIs(payload['ask_execs_enabled'], False)


# ---------------------------------------------------------------------------
# 5 — shipped config.yaml carries the parity flags
# ---------------------------------------------------------------------------

class ShippedConfigTests(SimpleTestCase):
    def test_config_enables_acpx_and_multiturn(self):
        agent = 'teletlamatini'
        with open(_config_path(agent), 'r', encoding='utf-8') as f:
            cfg = yaml.safe_load(f) or {}
        tla = cfg.get('tlamatini') or {}
        self.assertTrue(tla.get('acpx_enabled'), f'{agent}: acpx_enabled should be true')
        self.assertTrue(tla.get('multi_turn_enabled'), f'{agent}: multi_turn_enabled should be true')
        self.assertTrue(tla.get('exec_report_enabled'), f'{agent}: exec_report_enabled should be true')


if __name__ == '__main__':
    unittest.main()
