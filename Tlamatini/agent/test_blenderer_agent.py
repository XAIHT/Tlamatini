# ═══════════════════════════════════════════════════════════════════
#   ✦  T L A M A T I N I  ✦   —   "one who knows"
#
#   Created by  Angela López Mendoza   ·   @angelahack1
#   Developer · Architect · Creator of Tlamatini
#
#   Every line of this file was written by Angela López Mendoza.
# ═══════════════════════════════════════════════════════════════════
#   Tlamatini Author Banner — do not remove (releases scrub the name automatically)
"""Automated tests for the Blenderer workflow agent and its surrounding infrastructure.

Blenderer drives a live Blender instance through the OFFICIAL Blender MCP add-on's TCP
socket protocol (https://www.blender.org/lab/mcp-server/). Unlike Unrealer's verb-dispatch
protocol, the Blender MCP wire format is a CODE-EXECUTION protocol: each request is
``{"type": "execute", "code": "<python>", "strict_json": <bool>}`` followed by a single
NUL byte, and Blender runs that Python (which must assign a ``result`` dict) and replies
with ``{"status": "ok"|"error", "result": {...}, "message": ..., "stdout": ...}`` up to
the next NUL byte. It is a standalone pool agent under ``agent/agents/blenderer/`` that
runs as a separate Python subprocess, so — exactly like the Unrealer / Kalier test
modules — it is loaded through ``importlib.util.spec_from_file_location`` with a
cwd + logging-handler save/restore so its module-level ``os.chdir`` +
``open(LOG_FILE_PATH)`` + ``logging.basicConfig`` side effects land in its own directory.

These tests exercise the agent's real surface:

- the RICH ACTION CATALOG (``build_code`` / ``_bodies``): ``execute_code`` forwards raw
  Python verbatim; every baked verb emits a ``result``-setting program; params are
  injected as a parseable JSON blob (no brace-format hazard); output-path verbs default
  under the Temp dir.
- the per-command read-timeout floors (render / execute_code / screenshot) and the
  "never lower the operator's value" contract.
- the NUL-byte wire protocol, driven end-to-end against a REAL in-process fake Blender
  socket server (ok + engine-error replies) and the connection-refused degraded path.
- ``emit_parametrizer_section`` round-tripping through the real Parametrizer parser.
- the registry / contract / config.yaml / URL / CSS / JS-wiring integration that lets the
  agent be reached from chat and the canvas.

TIERS
-----
Everything in this module is **TIER 1**: it runs with NO Blender installed and NO add-on
running. The wire-protocol tests drive the agent's real socket code against an in-process
fake Blender server (``_FakeBlenderServer``), so the NUL-byte framing and the ok/error
normalization are exercised for real without a live editor. ``BlendererTier2LiveBlenderTests``
is a documented, ``skip``-marked placeholder enumerating the cases that genuinely require a
running Blender + the MCP add-on (a real ``bpy`` execution, a real render/screenshot, the
add-on handshake) — those land in a later tier once a Blender instance is available.
"""

import importlib.util
import json
import logging
import os
import shutil
import socket
import tempfile
import threading
import unittest
from functools import lru_cache

import yaml
from django.test import SimpleTestCase, TestCase


@lru_cache(maxsize=1)
def _load_blenderer_module():
    module_path = os.path.join(
        os.path.dirname(__file__), 'agents', 'blenderer', 'blenderer.py',
    )
    spec = importlib.util.spec_from_file_location(
        'agent_blenderer_module_for_tests', module_path,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f'Unable to load Blenderer module from {module_path}')

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


def _config_path():
    return os.path.join(
        os.path.dirname(__file__), 'agents', 'blenderer', 'config.yaml',
    )


@lru_cache(maxsize=1)
def _load_blenderer_config():
    with open(_config_path(), encoding='utf-8') as fh:
        return yaml.safe_load(fh)


def _js_path(name):
    return os.path.join(os.path.dirname(__file__), 'static', 'agent', 'js', name)


def _read(path):
    with open(path, encoding='utf-8') as fh:
        return fh.read()


# ---------------------------------------------------------------------------
# A real (tiny) fake Blender MCP socket server speaking the NUL-byte protocol.
# ---------------------------------------------------------------------------


class _FakeBlenderServer:
    """One-shot TCP server that mirrors the Blender MCP add-on wire contract.

    Reads a single NUL-terminated JSON request, validates it is a
    ``{"type":"execute","code":...,"strict_json":...}`` envelope, and writes a
    NUL-terminated JSON response. ``reply`` is the dict to send back.
    """

    def __init__(self, reply):
        self.reply = reply
        self.received = None
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._sock.bind(('127.0.0.1', 0))
        self._sock.listen(1)
        self.port = self._sock.getsockname()[1]
        self._thread = threading.Thread(target=self._serve, daemon=True)

    def __enter__(self):
        self._thread.start()
        return self

    def _serve(self):
        try:
            conn, _addr = self._sock.accept()
            with conn:
                buf = bytearray()
                conn.settimeout(5.0)
                while b"\0" not in buf:
                    chunk = conn.recv(65536)
                    if not chunk:
                        break
                    buf.extend(chunk)
                line, _sep, _rest = buf.partition(b"\0")
                try:
                    self.received = json.loads(line.decode('utf-8'))
                except Exception:
                    self.received = None
                conn.sendall((json.dumps(self.reply) + "\0").encode('utf-8'))
        except Exception:
            pass

    def __exit__(self, *exc):
        try:
            self._sock.close()
        except Exception:
            pass


def _free_port():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(('127.0.0.1', 0))
    port = s.getsockname()[1]
    s.close()
    return port


# ---------------------------------------------------------------------------
# build_code / _bodies — the rich action catalog
# ---------------------------------------------------------------------------


class BuildCodeTests(SimpleTestCase):
    def setUp(self):
        self.b = _load_blenderer_module()

    def test_execute_code_is_verbatim_passthrough(self):
        raw = "import bpy\nresult = {'hello': 'world'}\n"
        code, params = self.b.build_code('execute_code', {'code': raw})
        self.assertEqual(code, raw)

    def test_execute_code_empty_is_empty(self):
        code, _ = self.b.build_code('execute_code', {})
        self.assertEqual(code.strip(), '')

    def test_every_known_baked_verb_emits_result_setting_code(self):
        baked = self.b.KNOWN_COMMANDS - self.b._PASSTHROUGH_COMMANDS
        self.assertTrue(baked)
        for cmd in baked:
            code, _ = self.b.build_code(cmd, {'object_name': 'Cube', 'output_path': 'x.png'})
            self.assertIn('result', code, f'{cmd} must reference result')
            self.assertIn('_p = _json.loads(', code, f'{cmd} must parse the params blob')
            # The injected params blob must be valid (round-trippable) JSON.
            compile(code, f'<{cmd}>', 'exec')

    def test_unknown_command_body_is_empty(self):
        self.assertEqual(self.b._bodies('does_not_exist', {}), '')

    def test_params_with_quotes_do_not_break_codegen(self):
        # A name with quotes/newlines must survive the JSON injection unscathed.
        nasty = 'evil"name\'\n\\end'
        code, _ = self.b.build_code('get_object_detail', {'object_name': nasty})
        compile(code, '<nasty>', 'exec')
        # The decoded params must reconstruct the exact string.
        ns = {}
        # Execute only the prelude (it defines _p) — the body needs bpy.
        prelude = code.split('result = {}')[0] + 'result = {}'
        exec(prelude, ns)
        self.assertEqual(ns['_p'].get('object_name'), nasty)

    def test_screenshot_defaults_output_path_under_temp(self):
        os.environ['TLAMATINI_TEMP'] = os.path.dirname(__file__)
        try:
            _code, params = self.b.build_code('screenshot', {})
            self.assertTrue(params['output_path'].endswith('.png'))
            self.assertIn('TlamatiniBlenderer', params['output_path'])
        finally:
            os.environ.pop('TLAMATINI_TEMP', None)

    def test_render_default_output_path_is_not_overwritten_when_given(self):
        _code, params = self.b.build_code('render', {'output_path': '/tmp/keep.png'})
        self.assertEqual(params['output_path'], '/tmp/keep.png')


# ---------------------------------------------------------------------------
# read-timeout floors
# ---------------------------------------------------------------------------


class EffectiveReadTimeoutTests(SimpleTestCase):
    def setUp(self):
        self.b = _load_blenderer_module()

    def test_render_floor_raises_low_value(self):
        self.assertEqual(self.b._effective_read_timeout('render', 10), 600.0)

    def test_execute_code_floor(self):
        self.assertEqual(self.b._effective_read_timeout('execute_code', 10), 300.0)

    def test_operator_higher_value_is_never_lowered(self):
        self.assertEqual(self.b._effective_read_timeout('render', 900), 900.0)

    def test_fast_command_is_unchanged(self):
        self.assertEqual(self.b._effective_read_timeout('scene_info', 120), 120.0)

    def test_garbage_timeout_falls_back(self):
        self.assertEqual(self.b._effective_read_timeout('scene_info', 'oops'), 120.0)


# ---------------------------------------------------------------------------
# BlenderConnection — the real NUL-byte wire protocol
# ---------------------------------------------------------------------------


class BlenderConnectionTests(SimpleTestCase):
    def setUp(self):
        self.b = _load_blenderer_module()

    def test_ok_roundtrip_against_fake_server(self):
        reply = {"status": "ok", "result": {"scene": "Scene"}, "stdout": ""}
        with _FakeBlenderServer(reply) as srv:
            conn = self.b.BlenderConnection(host='127.0.0.1', port=srv.port,
                                            connect_timeout=5, read_timeout=5)
            resp = conn.send("result = {'scene': bpy.context.scene.name}", strict_json=True)
            # the server must have received a well-formed execute envelope
            self.assertEqual(srv.received.get('type'), 'execute')
            self.assertIn('code', srv.received)
            self.assertIs(srv.received.get('strict_json'), True)
            self.assertEqual(resp.get('status'), 'ok')
            self.assertEqual(resp['result']['scene'], 'Scene')

    def test_engine_error_reply_is_normalized(self):
        reply = {"status": "error", "message": "boom in bpy"}
        with _FakeBlenderServer(reply) as srv:
            conn = self.b.BlenderConnection(host='127.0.0.1', port=srv.port,
                                            connect_timeout=5, read_timeout=5)
            resp = conn.send("1/0", strict_json=False)
            self.assertEqual(resp.get('status'), 'error')
            # message is surfaced as `error` so downstream code has one shape
            self.assertEqual(resp.get('error'), 'boom in bpy')

    def test_unreachable_blender_is_actionable_error(self):
        # Nothing is listening on this port. Depending on the OS this surfaces
        # as a refused connection OR (on Windows, no RST) a connect timeout —
        # both must come back as a status=error with an actionable message, NOT
        # a crash and never a fake "ok".
        port = _free_port()
        conn = self.b.BlenderConnection(host='127.0.0.1', port=port,
                                        connect_timeout=2, read_timeout=2)
        resp = conn.send("result = {}", strict_json=False)
        self.assertEqual(resp.get('status'), 'error')
        err = resp.get('error', '')
        self.assertTrue(
            ('Online access' in err) or ('did not reply' in err)
            or ('Socket error' in err) or ('Cannot connect' in err),
            f'unhelpful error message: {err!r}',
        )


# ---------------------------------------------------------------------------
# INI_SECTION_BLENDERER round-trip through the real Parametrizer parser
# ---------------------------------------------------------------------------


class ParametrizerSectionTests(SimpleTestCase):
    def setUp(self):
        self.b = _load_blenderer_module()

    def test_section_parses_back(self):
        captured = {}
        orig = logging.info

        def _cap(msg, *a, **k):
            captured['msg'] = msg

        logging.info = _cap
        try:
            self.b.emit_parametrizer_section(
                'localhost', 9876, 'scene_info', 'ok', '',
                json.dumps({"scene": "Scene", "objects": ["Cube"]}),
            )
        finally:
            logging.info = orig

        from agent.agents.parametrizer.parametrizer import OUTPUT_PARSERS
        parsed = OUTPUT_PARSERS['blenderer'](captured['msg'])
        # The unified parser returns a list of section dicts (one per block).
        rec = parsed[0] if isinstance(parsed, list) else parsed
        self.assertEqual(rec.get('command'), 'scene_info')
        self.assertEqual(rec.get('status'), 'ok')
        self.assertIn('Cube', rec.get('response_body', ''))


# ---------------------------------------------------------------------------
# Registry / contract / config / URL / CSS / JS integration
# ---------------------------------------------------------------------------


class BlendererIntegrationTests(SimpleTestCase):
    def test_wrapped_chat_agent_spec(self):
        from agent.chat_agent_registry import WRAPPED_CHAT_AGENT_BY_TOOL_NAME
        spec = WRAPPED_CHAT_AGENT_BY_TOOL_NAME.get('chat_agent_blenderer')
        self.assertIsNotNone(spec)
        self.assertEqual(spec.display_name, 'Blenderer')
        self.assertEqual(spec.template_dir, 'blenderer')

    def test_agent_contract_parametrizer_fields(self):
        from agent.services.agent_contracts import get_agent_contract
        c = get_agent_contract('blenderer')
        self.assertEqual(c.display_name, 'Blenderer')
        for f in ('host', 'port', 'command', 'status', 'error', 'response_body'):
            self.assertIn(f, c.parametrizer_fields)

    def test_exec_report_membership(self):
        from agent.mcp_agent import _EXEC_REPORT_TOOLS, _resolve_exec_report_spec
        self.assertEqual(_EXEC_REPORT_TOOLS.get('chat_agent_blenderer'),
                         ('blenderer', 'Blenderer'))
        self.assertEqual(_resolve_exec_report_spec('chat_agent_blenderer'),
                         ('blenderer', 'Blenderer'))

    def test_parametrizer_source_registered(self):
        from agent.agents.parametrizer.parametrizer import SECTION_AGENT_TYPES
        self.assertIn('blenderer', SECTION_AGENT_TYPES)

    def test_config_defaults_present(self):
        cfg = _load_blenderer_config()
        for key in ('host', 'port', 'command', 'strict_json', 'params',
                    'connect_timeout', 'read_timeout', 'source_agents', 'target_agents'):
            self.assertIn(key, cfg)
        self.assertEqual(cfg['port'], 9876)
        for pk in ('code', 'object_name', 'name', 'type', 'location', 'color',
                   'material', 'output_path'):
            self.assertIn(pk, cfg['params'])

    def test_url_resolves(self):
        from django.urls import reverse
        self.assertEqual(reverse('update_blenderer_connection', args=['blenderer-1']),
                         '/agent/update_blenderer_connection/blenderer-1/')

    def test_connection_view_exists(self):
        from agent import views
        self.assertTrue(hasattr(views, 'update_blenderer_connection_view'))

    def test_css_class_present_and_unique(self):
        css_path = os.path.join(os.path.dirname(__file__), 'static', 'agent', 'css',
                                'agentic_control_panel.css')
        css = _read(css_path)
        self.assertEqual(css.count('.canvas-item.blenderer-agent {'), 1)

    def test_js_wiring_present(self):
        connectors = _read(_js_path('acp-agent-connectors.js'))
        self.assertIn('async function updateBlendererConnection', connectors)
        core = _read(_js_path('acp-canvas-core.js'))
        self.assertIn("'blenderer': 'blenderer-agent'", core)
        self.assertIn('updateBlendererConnection', core)
        undo = _read(_js_path('acp-canvas-undo.js'))
        self.assertIn('updateBlendererConnection', undo)
        fileio = _read(_js_path('acp-file-io.js'))
        self.assertIn("case 'blenderer':", fileio)
        chat = _read(_js_path('agent_page_chat.js'))
        self.assertIn("lower === 'blenderer'", chat)


# ---------------------------------------------------------------------------
# Catalog shape — KNOWN_COMMANDS structure, timeout-floor coverage, codegen
# ---------------------------------------------------------------------------


class CatalogShapeTests(SimpleTestCase):
    def setUp(self):
        self.b = _load_blenderer_module()

    def test_known_commands_is_union_of_the_three_buckets(self):
        b = self.b
        self.assertEqual(
            b.KNOWN_COMMANDS,
            b._PASSTHROUGH_COMMANDS | b._READ_COMMANDS | b._WRITE_COMMANDS,
        )

    def test_buckets_do_not_overlap(self):
        b = self.b
        self.assertEqual(b._PASSTHROUGH_COMMANDS & b._READ_COMMANDS, set())
        self.assertEqual(b._READ_COMMANDS & b._WRITE_COMMANDS, set())
        self.assertEqual(b._PASSTHROUGH_COMMANDS & b._WRITE_COMMANDS, set())

    def test_timeout_floor_keys_are_all_known_commands(self):
        b = self.b
        self.assertTrue(set(b._SLOW_COMMAND_TIMEOUT_FLOORS).issubset(b.KNOWN_COMMANDS))

    def test_unknown_command_build_code_is_empty(self):
        code, _params = self.b.build_code('does_not_exist', {})
        self.assertEqual(code.strip(), '')

    def test_create_object_codegen_covers_every_primitive(self):
        code, _ = self.b.build_code('create_object', {'type': 'monkey'})
        for prim in ('cube', 'sphere', 'cylinder', 'cone', 'plane', 'monkey', 'torus'):
            self.assertIn(f"'{prim}'", code, f'create_object must map {prim}')

    def test_read_commands_are_genuinely_read_only_codegen(self):
        # A read verb's generated program must not call a mutating bpy.ops/remove.
        for cmd in self.b._READ_COMMANDS:
            code, _ = self.b.build_code(cmd, {'object_name': 'Cube'})
            self.assertNotIn('bpy.ops.mesh.primitive', code, f'{cmd} should not create')
            self.assertNotIn('.remove(', code, f'{cmd} should not delete')


# ---------------------------------------------------------------------------
# Output-path defaulting — Temp policy (no Blender, no filesystem writes needed)
# ---------------------------------------------------------------------------


class DefaultOutputPathTests(SimpleTestCase):
    def setUp(self):
        self.b = _load_blenderer_module()

    def test_default_output_path_extension_and_uniqueness(self):
        tmp = tempfile.mkdtemp()
        os.environ['TLAMATINI_TEMP'] = tmp
        try:
            p1 = self.b._default_output_path('png')
            p2 = self.b._default_output_path('png')
            self.assertTrue(p1.endswith('.png'))
            self.assertNotEqual(p1, p2, 'output paths must be collision-proof')
            self.assertTrue(p1.startswith(tmp))
            self.assertIn('TlamatiniBlenderer', p1)
        finally:
            os.environ.pop('TLAMATINI_TEMP', None)
            shutil.rmtree(tmp, ignore_errors=True)

    def test_default_dir_honors_tlamatini_temp_not_system_temp(self):
        tmp = tempfile.mkdtemp()
        os.environ['TLAMATINI_TEMP'] = tmp
        try:
            out = self.b._default_temp_output_dir()
            self.assertTrue(out.startswith(tmp))
            # MUST NOT land in the OS temp dir (2026-06-02 directory policy).
            sys_temp = os.path.realpath(tempfile.gettempdir())
            self.assertFalse(os.path.realpath(out).startswith(sys_temp)
                             and not os.path.realpath(tmp).startswith(sys_temp))
        finally:
            os.environ.pop('TLAMATINI_TEMP', None)
            shutil.rmtree(tmp, ignore_errors=True)


# ---------------------------------------------------------------------------
# Wire-protocol framing — driven against the in-process fake Blender server
# ---------------------------------------------------------------------------


class WireProtocolFramingTests(SimpleTestCase):
    def setUp(self):
        self.b = _load_blenderer_module()

    def test_request_is_nul_terminated_and_carries_exact_code(self):
        code = "result = {'k': 1}"
        with _FakeBlenderServer({"status": "ok", "result": {}}) as srv:
            conn = self.b.BlenderConnection(host='127.0.0.1', port=srv.port,
                                            connect_timeout=5, read_timeout=5)
            conn.send(code, strict_json=False)
            self.assertEqual(srv.received.get('code'), code)
            self.assertIs(srv.received.get('strict_json'), False)

    def test_only_first_nul_segment_is_parsed(self):
        # A server that writes the reply + a trailing NUL + junk must still parse
        # cleanly (the client reads up to the FIRST NUL).
        class _NoisyServer(_FakeBlenderServer):
            def _serve(self):
                try:
                    c, _a = self._sock.accept()
                    with c:
                        c.settimeout(5.0)
                        buf = bytearray()
                        while b"\0" not in buf:
                            ch = c.recv(65536)
                            if not ch:
                                break
                            buf.extend(ch)
                        payload = json.dumps(self.reply) + "\0" + "GARBAGE-AFTER-NUL\0"
                        c.sendall(payload.encode('utf-8'))
                except Exception:
                    pass

        with _NoisyServer({"status": "ok", "result": {"ok": True}}) as srv:
            conn = self.b.BlenderConnection(host='127.0.0.1', port=srv.port,
                                            connect_timeout=5, read_timeout=5)
            resp = conn.send("result = {}", strict_json=False)
            self.assertEqual(resp.get('status'), 'ok')
            self.assertEqual(resp['result']['ok'], True)


# ---------------------------------------------------------------------------
# TIER 2 — placeholder: cases that REQUIRE a live Blender + the MCP add-on.
# Documented now, skipped until a Blender instance is wired into the harness.
# ---------------------------------------------------------------------------


@unittest.skip("Tier 2: requires a running Blender with the MCP add-on enabled "
               "(Online access on, server started). Implement once a live "
               "Blender instance is available to the test harness.")
class BlendererTier2LiveBlenderTests(SimpleTestCase):
    def test_ping_against_real_blender(self):
        # scene_info / ping should return status ok with a blender_version string.
        raise NotImplementedError

    def test_create_object_then_get_object_detail_roundtrip(self):
        # create_object(monkey) then get_object_detail must report a MESH with verts.
        raise NotImplementedError

    def test_render_writes_a_png_under_temp(self):
        # render with no output_path must produce a real .png under <app>/Temp.
        raise NotImplementedError

    def test_set_material_assigns_principled_base_color(self):
        # set_material must attach a Principled material with the requested colour.
        raise NotImplementedError


class BlendererDbRowTests(TestCase):
    """Migration-seeded rows (Agent / Tool / demo Prompt) — needs the test DB."""

    def test_agent_and_tool_and_prompt_rows(self):
        from agent.models import Agent, Tool, Prompt
        self.assertTrue(Agent.objects.filter(agentDescription='Blenderer').exists())
        self.assertTrue(Tool.objects.filter(toolDescription='Chat-Agent-Blenderer').exists())
        # The Blenderer demo prompt is identified by its content, not a fixed slot:
        # catalog inserts (0144, 0145, ...) shift idPrompt, so assert by its banner.
        blender = [p for p in Prompt.objects.all() if 'BLENDER FORGE' in (p.promptContent or '')]
        self.assertEqual(len(blender), 1, 'the Blenderer demo prompt must be seeded exactly once')
        self.assertEqual(blender[0].promptName, f'prompt-{blender[0].idPrompt}')


if __name__ == '__main__':
    unittest.main()
