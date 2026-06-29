"""Automated tests for the Camcorder workflow agent and its surrounding infrastructure.

Camcorder captures from a SYSTEM CAMERA (webcam) via OpenCV (``cv2``): a single PHOTO
(the default) or a VIDEO segment of ``video_duration_seconds``. It is a standalone pool
agent under ``agent/agents/camcorder/`` loaded here through
``importlib.util.spec_from_file_location`` with a cwd + logging-handler save/restore so its
module-level ``os.chdir`` / ``open(LOG_FILE_PATH)`` / ``logging.basicConfig`` side effects do
not leak.

No camera, no OpenCV install and no hardware are required: a tiny FAKE ``cv2`` (pure Python)
implements ``VideoCapture`` / ``VideoWriter`` / ``imwrite`` / the ``CAP_*`` constants, and is
injected into ``sys.modules`` so the REAL ``open_camera`` / ``capture_photo`` /
``capture_video`` / ``emit_parametrizer_section`` code paths run deterministically.

Covers:
- Helpers: get_pictures_dir, resolve_output_dir (default vs honored), build_unique_path
  (collision-proof, sequential), emit_parametrizer_section (atomic INI block round-trip)
- capture_photo / capture_video against the FAKE cv2 (file written, resolution read-back,
  fps selection, frames written, requested-resolution honored)
- main() end-stage: section emitted + target_agents triggered; default mode == photo;
  missing-OpenCV path is reported, not crashed
- Registry integration: ChatWrappedAgentSpec, agent contract + parametrizer fields,
  Exec-Report ABSENCE (observational like Shoter), config.yaml defaults, CSS gradient
  (unique), URL route, view, JS wiring, parametrizer SECTION_AGENT_TYPES, migrations,
  requirements pin
"""

import builtins
import importlib.util
import logging
import os
import sys
import tempfile
import unittest
import unittest.mock
from functools import lru_cache

import yaml
from django.test import SimpleTestCase


_REPO_AGENT_DIR = os.path.dirname(__file__)


# ---------------------------------------------------------------------------
# FAKE cv2 — pure-Python stand-in for OpenCV
# ---------------------------------------------------------------------------


class _FakeVideoCapture:
    def __init__(self, index, *_a):
        self.index = index
        self._props = {3: 640.0, 4: 480.0, 5: 30.0}  # WIDTH, HEIGHT, FPS
        self._opened = index != 999  # index 999 simulates "cannot open"

    def isOpened(self):
        return self._opened

    def set(self, prop, val):
        self._props[prop] = float(val)
        return True

    def get(self, prop):
        return self._props.get(prop, 0.0)

    def read(self):
        return True, object()  # truthy frame

    def release(self):
        self._opened = False


class _FakeVideoWriter:
    def __init__(self, path, fourcc, fps, size):
        self.path = path
        self.fps = fps
        self.size = size
        self._opened = True
        self.frames = 0
        # The real writer creates the container file on open.
        with open(path, 'wb') as handle:
            handle.write(b'\x00\x00\x00\x18ftypmp42')

    def isOpened(self):
        return self._opened

    def write(self, _frame):
        self.frames += 1

    def release(self):
        self._opened = False


class _FakeCv2:
    CAP_DSHOW = 700
    CAP_PROP_FRAME_WIDTH = 3
    CAP_PROP_FRAME_HEIGHT = 4
    CAP_PROP_FPS = 5

    VideoCapture = _FakeVideoCapture
    VideoWriter = _FakeVideoWriter

    @staticmethod
    def VideoWriter_fourcc(*_chars):
        return 0x7634706D

    @staticmethod
    def imwrite(path, _frame):
        with open(path, 'wb') as handle:
            handle.write(b'\xff\xd8\xff\xe0JFIF')  # JPEG-ish magic
        return True


# ---------------------------------------------------------------------------
# Module loader — exec the pool-agent script with cwd + handler save/restore
# ---------------------------------------------------------------------------


@lru_cache(maxsize=1)
def _load_camcorder_module():
    module_path = os.path.join(_REPO_AGENT_DIR, 'agents', 'camcorder', 'camcorder.py')
    spec = importlib.util.spec_from_file_location(
        'agent_camcorder_module_for_tests', module_path,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f'Unable to load Camcorder module from {module_path}')

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


class _LogCapture:
    """Context manager that captures root-logger messages into a list."""

    def __init__(self):
        self.records = []

    def __enter__(self):
        outer = self

        class _H(logging.Handler):
            def emit(self, record):
                outer.records.append(record.getMessage())

        self._handler = _H()
        logging.getLogger().addHandler(self._handler)
        return self

    def __exit__(self, *_a):
        logging.getLogger().removeHandler(self._handler)
        return False


def _install_fake_cv2():
    sys.modules['cv2'] = _FakeCv2()


def _remove_fake_cv2():
    sys.modules.pop('cv2', None)


def _parse_ini_section(text, agent_type='CAMCORDER'):
    """Minimal parser mirroring parametrizer's INI_SECTION contract."""
    start = f"INI_SECTION_{agent_type}<<<"
    end = f">>>END_SECTION_{agent_type}"
    body = text.split(start, 1)[1].split(end, 1)[0].strip('\n')
    head, _, tail = body.partition('\n\n')
    fields = {}
    for line in head.split('\n'):
        if ': ' in line:
            key, val = line.split(': ', 1)
            fields[key.strip()] = val.strip()
        elif line.endswith(':'):
            fields[line[:-1].strip()] = ''
    fields['response_body'] = tail.strip()
    return fields


# ---------------------------------------------------------------------------
# Agent-module logic
# ---------------------------------------------------------------------------


class CamcorderHelperTests(unittest.TestCase):
    def setUp(self):
        self.mod = _load_camcorder_module()

    def test_default_temp_output_dir_nonempty(self):
        # Media defaults to <app>/Temp (<REDACTED> 2026-06-09), not the Pictures
        # known-folder — the get_pictures_dir helper was removed with that change.
        path = self.mod._default_temp_output_dir()
        self.assertTrue(path)
        self.assertIsInstance(path, str)

    def test_resolve_output_dir_default_is_temp(self):
        out = self.mod.resolve_output_dir({})
        self.assertTrue(os.path.isabs(out))
        self.assertEqual(os.path.basename(os.path.normpath(out)), 'Temp')

    def test_resolve_output_dir_honors_configured_absolute(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = self.mod.resolve_output_dir({'output_dir': tmp})
            self.assertEqual(os.path.normpath(out), os.path.normpath(tmp))

    def test_build_unique_path_is_collision_proof(self):
        with tempfile.TemporaryDirectory() as tmp:
            p1 = self.mod.build_unique_path(tmp, 'photo', 0, 'jpg')
            # Create it so the next call must dodge the collision.
            with open(p1, 'wb') as handle:
                handle.write(b'x')
            p2 = self.mod.build_unique_path(tmp, 'photo', 0, 'jpg')
            self.assertNotEqual(p1, p2)
            self.assertTrue(os.path.basename(p1).startswith('camcorder_photo_'))
            self.assertTrue(os.path.basename(p1).endswith('_cam0.jpg'))

    def test_emit_parametrizer_section_round_trip_photo(self):
        with _LogCapture() as cap:
            self.mod.emit_parametrizer_section(
                r'C:\X\TlamatiniCamcorder\camcorder_photo_x_cam0.jpg',
                'photo', 0, '640x480', 0, None,
            )
        block = next(r for r in cap.records if 'INI_SECTION_CAMCORDER<<<' in r)
        fields = _parse_ini_section(block)
        self.assertEqual(fields['media_type'], 'photo')
        self.assertEqual(fields['camera_index'], '0')
        self.assertEqual(fields['resolution'], '640x480')
        self.assertEqual(fields['duration_seconds'], '0')
        self.assertTrue(fields['filename'].endswith('.jpg'))
        self.assertIn('output_path', fields)
        self.assertIn('saved to', fields['response_body'])

    def test_emit_parametrizer_section_atomic_single_call(self):
        # The whole block MUST arrive in ONE log record (no interleave risk).
        with _LogCapture() as cap:
            self.mod.emit_parametrizer_section('p.mp4', 'video', 1, '1280x720', 15, 30.0)
        blocks = [r for r in cap.records if 'INI_SECTION_CAMCORDER<<<' in r]
        self.assertEqual(len(blocks), 1)
        self.assertIn('>>>END_SECTION_CAMCORDER', blocks[0])
        fields = _parse_ini_section(blocks[0])
        self.assertEqual(fields['media_type'], 'video')
        self.assertEqual(fields['duration_seconds'], '15')
        self.assertEqual(fields['fps'], '30.000')


class CamcorderCaptureTests(unittest.TestCase):
    def setUp(self):
        self.mod = _load_camcorder_module()
        _install_fake_cv2()
        self.addCleanup(_remove_fake_cv2)

    def test_capture_photo_writes_file_and_reads_resolution(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = {'camera_index': 0, 'warmup_seconds': 0,
                      'resolution_width': 0, 'resolution_height': 0}
            path, resolution = self.mod.capture_photo(config, tmp)
            self.assertTrue(os.path.exists(path))
            self.assertTrue(path.endswith('.jpg'))
            self.assertEqual(resolution, '640x480')

    def test_capture_photo_requested_resolution_is_applied_and_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = {'camera_index': 0, 'warmup_seconds': 0,
                      'resolution_width': 1280, 'resolution_height': 720}
            _path, resolution = self.mod.capture_photo(config, tmp)
            # The fake honors set(), so the read-back must reflect the request.
            self.assertEqual(resolution, '1280x720')

    def test_capture_photo_unopenable_camera_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = {'camera_index': 999, 'warmup_seconds': 0}
            with self.assertRaises(RuntimeError):
                self.mod.capture_photo(config, tmp)

    def test_capture_video_records_segment(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = {'camera_index': 0, 'warmup_seconds': 0,
                      'video_duration_seconds': 0.3, 'video_fps': 20.0,
                      'resolution_width': 0, 'resolution_height': 0}
            path, resolution, fps, duration = self.mod.capture_video(config, tmp)
            self.assertTrue(os.path.exists(path))
            self.assertTrue(path.endswith('.mp4'))
            self.assertEqual(resolution, '640x480')
            # Camera reports 30 fps -> preferred over the 20.0 request.
            self.assertEqual(fps, 30.0)
            self.assertGreaterEqual(duration, 0)

    def test_main_photo_default_emits_section_and_triggers_targets(self):
        mod = self.mod
        with tempfile.TemporaryDirectory() as tmp:
            cfg = {'capture_mode': 'photo', 'camera_index': 0, 'warmup_seconds': 0,
                   'output_dir': tmp, 'target_agents': ['sleeper_1']}
            started = []
            orig_chdir = os.getcwd()
            with _LogCapture() as cap, \
                    unittest.mock.patch.object(mod, 'load_config', return_value=cfg), \
                    unittest.mock.patch.object(mod, 'write_pid_file'), \
                    unittest.mock.patch.object(mod, 'remove_pid_file'), \
                    unittest.mock.patch.object(mod, 'wait_for_agents_to_stop'), \
                    unittest.mock.patch.object(mod, 'start_agent',
                                               side_effect=lambda n: started.append(n) or True):
                with self.assertRaises(SystemExit) as ctx:
                    mod.main()
            os.chdir(orig_chdir)
            self.assertEqual(ctx.exception.code, 0)
            self.assertEqual(started, ['sleeper_1'])
            self.assertTrue(any('INI_SECTION_CAMCORDER<<<' in r for r in cap.records))
            block = next(r for r in cap.records if 'INI_SECTION_CAMCORDER<<<' in r)
            self.assertIn('media_type: photo', block)

    def test_main_missing_opencv_is_reported_not_crashed(self):
        mod = self.mod
        _remove_fake_cv2()  # simulate OpenCV absent

        real_import = builtins.__import__

        def _no_cv2(name, *a, **k):
            if name == 'cv2':
                raise ImportError('No module named cv2')
            return real_import(name, *a, **k)

        with tempfile.TemporaryDirectory() as tmp:
            cfg = {'capture_mode': 'photo', 'output_dir': tmp, 'target_agents': []}
            orig_chdir = os.getcwd()
            with _LogCapture() as cap, \
                    unittest.mock.patch.object(mod, 'load_config', return_value=cfg), \
                    unittest.mock.patch.object(mod, 'write_pid_file'), \
                    unittest.mock.patch.object(mod, 'remove_pid_file'), \
                    unittest.mock.patch('builtins.__import__', side_effect=_no_cv2):
                with self.assertRaises(SystemExit) as ctx:
                    mod.main()
            os.chdir(orig_chdir)
            self.assertEqual(ctx.exception.code, 1)
            self.assertTrue(any('OpenCV' in r for r in cap.records))


# ---------------------------------------------------------------------------
# Registry / integration contracts
# ---------------------------------------------------------------------------


class CamcorderRegistryTests(SimpleTestCase):
    def test_wrapped_chat_agent_spec_registered(self):
        from agent.chat_agent_registry import WRAPPED_CHAT_AGENT_SPECS
        spec = next((s for s in WRAPPED_CHAT_AGENT_SPECS
                     if s.tool_name == 'chat_agent_camcorder'), None)
        self.assertIsNotNone(spec)
        self.assertEqual(spec.key, 'camcorder')
        self.assertEqual(spec.template_dir, 'camcorder')
        self.assertEqual(spec.display_name, 'Camcorder')

    def test_agent_contract_parametrizer_fields(self):
        from agent.services.agent_contracts import (
            get_agent_contract,
            get_parametrizer_source_fields,
        )
        fields = get_parametrizer_source_fields().get('camcorder')
        self.assertIsNotNone(fields)
        for expected in ('output_path', 'output_dir', 'filename', 'media_type',
                         'camera_index', 'duration_seconds', 'resolution', 'response_body'):
            self.assertIn(expected, fields)
        contract = get_agent_contract('camcorder')
        # Producer: a connection FROM camcorder writes target_agents.
        self.assertEqual(contract.output_field_by_slot.get(0), 'target_agents')

    def test_config_yaml_defaults(self):
        config_path = os.path.join(_REPO_AGENT_DIR, 'agents', 'camcorder', 'config.yaml')
        with open(config_path, 'r', encoding='utf-8') as handle:
            cfg = yaml.safe_load(handle)
        self.assertEqual(cfg['capture_mode'], 'photo')   # default == one shot
        self.assertEqual(cfg['camera_index'], 0)
        self.assertEqual(cfg['resolution_width'], 0)
        self.assertEqual(cfg['resolution_height'], 0)
        self.assertEqual(cfg['output_dir'], '')
        self.assertIn('target_agents', cfg)

    def test_captured_in_exec_report(self):
        # Completeness contract (2026-06-07): EVERY agent that runs in Multi-Turn
        # — observational ones like Camcorder INCLUDED — is captured in the Exec
        # report (auto-resolved from the wrapped chat-agent registry).
        from agent.mcp_agent import _resolve_exec_report_spec
        spec = _resolve_exec_report_spec('chat_agent_camcorder')
        self.assertIsNotNone(spec)
        self.assertEqual(spec[1], 'Camcorder')

    def test_parametrizer_section_type_registered(self):
        param_path = os.path.join(_REPO_AGENT_DIR, 'agents', 'parametrizer', 'parametrizer.py')
        with open(param_path, 'r', encoding='utf-8') as handle:
            text = handle.read()
        self.assertIn("'camcorder'", text)

    def test_url_route_and_view_present(self):
        with open(os.path.join(_REPO_AGENT_DIR, 'urls.py'), 'r', encoding='utf-8') as handle:
            urls = handle.read()
        self.assertIn('update_camcorder_connection', urls)
        with open(os.path.join(_REPO_AGENT_DIR, 'views.py'), 'r', encoding='utf-8') as handle:
            views = handle.read()
        self.assertIn('def update_camcorder_connection_view', views)

    def test_migrations_present(self):
        mig_dir = os.path.join(_REPO_AGENT_DIR, 'migrations')
        self.assertTrue(os.path.exists(os.path.join(mig_dir, '0112_add_camcorder.py')))
        self.assertTrue(os.path.exists(
            os.path.join(mig_dir, '0113_add_chat_agent_camcorder_tool.py')))

    def test_css_gradient_unique(self):
        css_path = os.path.join(
            _REPO_AGENT_DIR, 'static', 'agent', 'css', 'agentic_control_panel.css')
        with open(css_path, 'r', encoding='utf-8') as handle:
            css = handle.read()
        self.assertIn('.canvas-item.camcorder-agent', css)

    def test_js_classmap_and_connector_wired(self):
        js_dir = os.path.join(_REPO_AGENT_DIR, 'static', 'agent', 'js')
        with open(os.path.join(js_dir, 'acp-canvas-core.js'), 'r', encoding='utf-8') as handle:
            core = handle.read()
        self.assertIn("'camcorder': 'camcorder-agent'", core)
        self.assertIn("=== 'camcorder') updateCamcorderConnection", core)
        with open(os.path.join(js_dir, 'acp-agent-connectors.js'), 'r', encoding='utf-8') as handle:
            conn = handle.read()
        self.assertIn('async function updateCamcorderConnection', conn)

    def test_requirements_pin_opencv(self):
        req_path = os.path.join(os.path.dirname(os.path.dirname(_REPO_AGENT_DIR)), 'requirements.txt')
        with open(req_path, 'r', encoding='utf-8') as handle:
            reqs = handle.read()
        self.assertIn('opencv-python', reqs)


if __name__ == '__main__':
    unittest.main()
