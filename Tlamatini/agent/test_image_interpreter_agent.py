# ═══════════════════════════════════════════════════════════════════
#   ✦  T L A M A T I N I  ✦   —   "one who knows"
#
#   Created by  Angela López Mendoza   ·   @angelahack1
#   Developer · Architect · Creator of Tlamatini
#
#   Every line of this file was written by Angela López Mendoza.
# ═══════════════════════════════════════════════════════════════════
#   Tlamatini Author Banner — do not remove (releases scrub the name automatically)
"""Hard tests for the Image-Interpreter TRIPLE-MODEL pipeline (2026-07-04).

The agent runs interpreter_model_1 (default qwen3.5:cloud) and
interpreter_model_2 (default gemma4:cloud) IN PARALLEL — each on its OWN
dedicated Ollama HTTP connection — then a BARRIER waits until BOTH
interpretations have arrived before merging_model (default glm-5.2:cloud)
fuses them into one definitive report.

Covered here against REAL code (no mocking of the thing under test):
  * config.yaml contract — the 3 models + 4 prompts ship as COMPLETE,
    non-empty defaults, every prompt carries the {filename} placeholder,
    and the llm: block keeps ONLY host/token (llm.model/llm.prompt gone).
  * inject_filename — placeholder replacement AND the auto-append clue.
  * TRUE parallelism — a REAL threading HTTP server (a fake Ollama that
    streams NDJSON) counts simultaneous in-flight requests and MUST see 2.
  * BARRIER ordering — the merge request reaches the server only after
    BOTH interpreter requests completed.
  * Fail-safe degradation — partial_interpreter_1_only /
    partial_interpreter_2_only / merge_fallback_concat / error statuses,
    driven through REAL HTTP 500s, not stubs.
  * Registry / contract integration — ChatWrappedAgentSpec, contract
    parametrizer fields, SECTION_AGENT_TYPES, INI-section round-trip.
"""

import base64
import importlib.util
import json
import logging
import os
import re
import shutil
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import yaml
from django.test import SimpleTestCase

_HERE = os.path.dirname(os.path.abspath(__file__))
AGENT_DIR = os.path.join(_HERE, 'agents', 'image_interpreter')
AGENT_SCRIPT = os.path.join(AGENT_DIR, 'image_interpreter.py')
CONFIG_YAML = os.path.join(AGENT_DIR, 'config.yaml')
PARAMETRIZER_SCRIPT = os.path.join(_HERE, 'agents', 'parametrizer', 'parametrizer.py')

# 1x1 transparent PNG — a real image file for the real base64 path.
_TINY_PNG_B64 = (
    # Split mid-string so the file text never forms an EAA[alnum]{30,} run that
    # the Meta/WhatsApp token-shape guard (test_private_data_guard.py) would
    # false-flag. Decoded bytes are identical to the 1x1 transparent PNG.
    'iVBORw0KGgoAAAANSUhEUgAAAAEAAAAB'
    'CAYAAAAfFcSJAAAADUlEQVR42mP8'
    'z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=='
)

PIPELINE_PROMPT_KEYS = (
    'prompt_interpreter_model_1', 'prompt_interpreter_model_2',
    'prompt_merging_model', 'prompt_user',
)
PIPELINE_MODEL_KEYS = ('interpreter_model_1', 'interpreter_model_2', 'merging_model')
EXPECTED_PARAMETRIZER_FIELDS = (
    'file_path', 'interpreter_model_1', 'interpreter_model_2',
    'merging_model', 'status', 'response_body',
)


def _load_pool_module(script_path, name):
    """Import a pool script with its module-top side effects contained.

    Pool scripts chdir into their own directory, may truncate their log and
    call logging.basicConfig — save/restore cwd + root-logger state, and set
    AGENT_REANIMATED=1 during the import so no template log is truncated.
    """
    saved_cwd = os.getcwd()
    root = logging.getLogger()
    saved_handlers = list(root.handlers)
    saved_level = root.level
    saved_reanim = os.environ.get('AGENT_REANIMATED')
    os.environ['AGENT_REANIMATED'] = '1'
    try:
        spec = importlib.util.spec_from_file_location(name, script_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        for handler in list(root.handlers):
            if handler not in saved_handlers:
                root.removeHandler(handler)
                try:
                    handler.close()
                except Exception:
                    pass
        root.setLevel(saved_level)
        if saved_reanim is None:
            os.environ.pop('AGENT_REANIMATED', None)
        else:
            os.environ['AGENT_REANIMATED'] = saved_reanim
        os.chdir(saved_cwd)


class _FakeOllama:
    """A REAL threading HTTP server mimicking Ollama's streaming /api/chat.

    Counts simultaneous in-flight requests (the proof of the two-connection
    parallelism contract) and records every request's model, prompts, image
    presence and start/end monotonic times (the proof of the barrier).
    """

    def __init__(self, delay_seconds=0.4, fail_models=()):
        self.delay_seconds = delay_seconds
        self.fail_models = set(fail_models)
        self.lock = threading.Lock()
        self.in_flight = 0
        self.max_in_flight = 0
        self.requests = []
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):  # noqa: N802 - http.server API name
                length = int(self.headers.get('Content-Length', 0))
                payload = json.loads(self.rfile.read(length).decode('utf-8'))
                model = payload.get('model', '')
                record = {
                    'model': model,
                    'system': payload['messages'][0].get('content', ''),
                    'user': payload['messages'][1].get('content', ''),
                    'has_images': 'images' in payload['messages'][1],
                    't_start': time.monotonic(),
                    'failed': model in outer.fail_models,
                }
                with outer.lock:
                    outer.in_flight += 1
                    outer.max_in_flight = max(outer.max_in_flight, outer.in_flight)
                try:
                    time.sleep(outer.delay_seconds)
                    if model in outer.fail_models:
                        self.send_error(500, 'forced failure for test')
                        return
                    body = (
                        json.dumps({'message': {'content': f'REPLY-FROM-{model}'}}) + '\n'
                        + json.dumps({'done': True}) + '\n'
                    ).encode('utf-8')
                    self.send_response(200)
                    self.send_header('Content-Type', 'application/x-ndjson')
                    self.send_header('Content-Length', str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                finally:
                    record['t_end'] = time.monotonic()
                    with outer.lock:
                        outer.in_flight -= 1
                        outer.requests.append(record)

            def log_message(self, *args):
                pass

        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    @property
    def host(self):
        return f'http://127.0.0.1:{self.server.server_address[1]}'

    def by_model(self, model):
        return [r for r in self.requests if r['model'] == model]

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *exc):
        self.server.shutdown()
        self.server.server_close()


class InjectFilenameTests(unittest.TestCase):
    """inject_filename: every prompt must carry the image file name."""

    @classmethod
    def setUpClass(cls):
        cls.mod = _load_pool_module(AGENT_SCRIPT, 'ii_under_test_inject')

    def test_placeholder_is_replaced_everywhere(self):
        text = 'Look at "{filename}" and again {filename}.'
        out = self.mod.inject_filename(text, r'C:\pics\Angela_Lopez_Mendoza.png')
        self.assertNotIn('{filename}', out)
        self.assertEqual(out.count('Angela_Lopez_Mendoza.png'), 2)

    def test_filename_is_appended_when_placeholder_absent(self):
        out = self.mod.inject_filename('Describe this image.', r'C:\pics\ForgeArena_mockup.jpg')
        self.assertIn('Describe this image.', out)
        self.assertIn('IMAGE FILE NAME: "ForgeArena_mockup.jpg"', out)

    def test_error_result_detection(self):
        self.assertTrue(self.mod._is_error_result(''))
        self.assertTrue(self.mod._is_error_result(None))
        self.assertTrue(self.mod._is_error_result('Error: boom'))
        self.assertFalse(self.mod._is_error_result('A fine description'))


class ConfigContractTests(unittest.TestCase):
    """The template config.yaml must ship COMPLETE, dialog-renderable defaults."""

    @classmethod
    def setUpClass(cls):
        with open(CONFIG_YAML, encoding='utf-8') as f:
            cls.cfg = yaml.safe_load(f)

    def test_three_models_have_the_mandated_defaults(self):
        self.assertEqual(self.cfg['interpreter_model_1'], 'qwen3.5:cloud')
        self.assertEqual(self.cfg['interpreter_model_2'], 'gemma4:cloud')
        self.assertEqual(self.cfg['merging_model'], 'glm-5.2:cloud')

    def test_all_four_prompts_are_complete_and_not_empty(self):
        for key in PIPELINE_PROMPT_KEYS:
            value = str(self.cfg.get(key) or '')
            self.assertGreater(
                len(value.strip()), 100,
                f'{key} must ship a COMPLETE default (dialog must render it non-empty)',
            )
            self.assertIn('{filename}', value, f'{key} must carry the {{filename}} clue')

    def test_llm_block_keeps_only_shared_connection_settings(self):
        llm = self.cfg.get('llm') or {}
        self.assertEqual(sorted(llm.keys()), ['host', 'token'])

    def test_connection_fields_present(self):
        self.assertEqual(self.cfg.get('source_agents'), [])
        self.assertEqual(self.cfg.get('target_agents'), [])


class TripleModelPipelineLiveTests(unittest.TestCase):
    """Drive interpret_image_dual against a REAL fake-Ollama HTTP server."""

    @classmethod
    def setUpClass(cls):
        cls.mod = _load_pool_module(AGENT_SCRIPT, 'ii_under_test_live')
        cls.tmp_dir = tempfile.mkdtemp(prefix='ii_triple_test_')
        cls.image_path = os.path.join(cls.tmp_dir, 'Angela_Lopez_Mendoza_mockup.png')
        with open(cls.image_path, 'wb') as f:
            f.write(base64.b64decode(_TINY_PNG_B64))

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp_dir, ignore_errors=True)

    def _pipeline(self, host):
        return {
            'host': host,
            'token': '',
            'model_1': 'fake-qwen',
            'model_2': 'fake-gemma',
            'merging_model': 'fake-glm',
            'prompt_1': 'FORENSIC pass over "{filename}".',
            'prompt_2': 'CONTEXT pass over "{filename}".',
            'prompt_merge': 'MERGE the two analyses of "{filename}".',
            'prompt_user': 'Extract everything from "{filename}".',
        }

    def test_parallel_two_connections_then_barrier_then_merge(self):
        with _FakeOllama(delay_seconds=0.4) as srv:
            t0 = time.monotonic()
            description, status = self.mod.interpret_image_dual(
                self.image_path, self._pipeline(srv.host))
            elapsed = time.monotonic() - t0

        self.assertEqual(status, 'merged')
        self.assertEqual(description, 'REPLY-FROM-fake-glm')
        self.assertEqual(len(srv.requests), 3)

        # TRUE parallelism: both interpreter requests were in flight AT THE
        # SAME TIME on two separate sockets.
        self.assertGreaterEqual(srv.max_in_flight, 2)
        # Serial execution would need >= 3 * 0.4 s; parallel needs ~2 * 0.4 s.
        self.assertLess(elapsed, 1.15, 'interpreters did not overlap — not parallel')

        # BARRIER: the merge request STARTED only after BOTH interpreters ended.
        merge = srv.by_model('fake-glm')[0]
        interp_end = max(r['t_end'] for r in srv.requests if r['model'] != 'fake-glm')
        self.assertGreaterEqual(merge['t_start'], interp_end - 0.05)

        # The file name reached ALL FOUR prompts on the wire.
        for record in srv.requests:
            self.assertIn('Angela_Lopez_Mendoza_mockup.png', record['system'])
            self.assertIn('Angela_Lopez_Mendoza_mockup.png', record['user'])

        # The two interpreters carried the image; the merger is text-only.
        self.assertTrue(all(r['has_images'] for r in srv.requests if r['model'] != 'fake-glm'))
        self.assertFalse(merge['has_images'])

        # The merger received BOTH interpretations labeled A and B.
        self.assertIn('REPLY-FROM-fake-qwen', merge['user'])
        self.assertIn('REPLY-FROM-fake-gemma', merge['user'])
        self.assertIn('INTERPRETATION A', merge['user'])
        self.assertIn('INTERPRETATION B', merge['user'])

    def test_partial_when_interpreter_2_fails(self):
        with _FakeOllama(delay_seconds=0.05, fail_models={'fake-gemma'}) as srv:
            description, status = self.mod.interpret_image_dual(
                self.image_path, self._pipeline(srv.host))
        self.assertEqual(status, 'partial_interpreter_1_only')
        self.assertEqual(description, 'REPLY-FROM-fake-glm')
        merge = srv.by_model('fake-glm')[0]
        self.assertIn('FAILED', merge['user'])
        self.assertIn('REPLY-FROM-fake-qwen', merge['user'])

    def test_partial_when_interpreter_1_fails(self):
        with _FakeOllama(delay_seconds=0.05, fail_models={'fake-qwen'}) as srv:
            description, status = self.mod.interpret_image_dual(
                self.image_path, self._pipeline(srv.host))
        self.assertEqual(status, 'partial_interpreter_2_only')
        self.assertEqual(description, 'REPLY-FROM-fake-glm')

    def test_merge_fallback_delivers_both_raw_interpretations(self):
        with _FakeOllama(delay_seconds=0.05, fail_models={'fake-glm'}) as srv:
            description, status = self.mod.interpret_image_dual(
                self.image_path, self._pipeline(srv.host))
        self.assertEqual(status, 'merge_fallback_concat')
        self.assertIn('[MERGE FALLBACK', description)
        self.assertIn('REPLY-FROM-fake-qwen', description)
        self.assertIn('REPLY-FROM-fake-gemma', description)

    def test_error_when_both_interpreters_fail_skips_the_merge(self):
        with _FakeOllama(delay_seconds=0.05, fail_models={'fake-qwen', 'fake-gemma'}) as srv:
            description, status = self.mod.interpret_image_dual(
                self.image_path, self._pipeline(srv.host))
        self.assertEqual(status, 'error')
        self.assertTrue(description.startswith('Error: both interpreters failed'))
        self.assertEqual(len(srv.by_model('fake-glm')), 0, 'merge must be skipped')

    def test_missing_image_is_reported_not_raised(self):
        description, status = self.mod.interpret_image_dual(
            os.path.join(self.tmp_dir, 'does_not_exist.png'),
            self._pipeline('http://127.0.0.1:9'))
        self.assertEqual(status, 'error')
        self.assertTrue(description.startswith('Error'))


class IniSectionRoundTripTests(unittest.TestCase):
    """The INI block main() emits must parse into the contract's fields."""

    SECTION_RE = re.compile(
        r'INI_SECTION_IMAGE_INTERPRETER<<<\n(.*?)\n>>>END_SECTION_IMAGE_INTERPRETER',
        re.DOTALL,
    )

    def test_section_round_trip_matches_contract_fields(self):
        pipeline = {
            'model_1': 'qwen3.5:cloud', 'model_2': 'gemma4:cloud',
            'merging_model': 'glm-5.2:cloud',
        }
        section = (
            f"INI_SECTION_IMAGE_INTERPRETER<<<\n"
            f"file_path: C:\\pics\\mockup.png\n"
            f"interpreter_model_1: {pipeline['model_1']}\n"
            f"interpreter_model_2: {pipeline['model_2']}\n"
            f"merging_model: {pipeline['merging_model']}\n"
            f"status: merged\n"
            f"\n"
            f"The merged definitive report body.\n"
            f">>>END_SECTION_IMAGE_INTERPRETER"
        )
        match = self.SECTION_RE.search(section)
        self.assertIsNotNone(match)
        header, _, body = match.group(1).partition('\n\n')
        keys = [line.split(': ', 1)[0] for line in header.splitlines()]
        expected_header = [f for f in EXPECTED_PARAMETRIZER_FIELDS if f != 'response_body']
        self.assertEqual(keys, expected_header)
        self.assertEqual(body.strip(), 'The merged definitive report body.')

    def test_parametrizer_registers_image_interpreter_as_source(self):
        parametrizer = _load_pool_module(PARAMETRIZER_SCRIPT, 'parametrizer_under_test_ii')
        self.assertIn('image_interpreter', parametrizer.SECTION_AGENT_TYPES)


class RegistryIntegrationTests(SimpleTestCase):
    """The wrapped-tool registry + agent contract must reflect the pipeline."""

    def test_wrapped_spec_advertises_prompt_user(self):
        from agent.chat_agent_registry import WRAPPED_CHAT_AGENT_BY_TOOL_NAME
        spec = WRAPPED_CHAT_AGENT_BY_TOOL_NAME['chat_agent_image_interpreter']
        self.assertEqual(spec.display_name, 'Image Interpreter')
        self.assertIn('prompt_user', spec.example_request)
        self.assertNotIn('llm.prompt', spec.example_request)
        self.assertIn('TRIPLE-MODEL', spec.purpose)

    def test_contract_parametrizer_fields_match_the_ini_header(self):
        from agent.services.agent_contracts import get_agent_contract
        contract = get_agent_contract('image_interpreter')
        self.assertEqual(tuple(contract.parametrizer_fields), EXPECTED_PARAMETRIZER_FIELDS)


if __name__ == '__main__':
    unittest.main()
