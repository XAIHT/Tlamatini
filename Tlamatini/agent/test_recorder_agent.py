"""Automated tests for the Recorder workflow agent and its surrounding infrastructure.

Recorder captures AUDIO from a system input device (MICROPHONE) via ``sounddevice`` and
saves a WAV (written with the stdlib ``wave`` module). It is the audio sibling of Camcorder
(camera) / Shoter (screen). It is a standalone pool agent under ``agent/agents/recorder/``
loaded here through ``importlib.util.spec_from_file_location`` with a cwd + logging-handler
save/restore so its module-level ``os.chdir`` / ``open(LOG_FILE_PATH)`` / ``logging.basicConfig``
side effects do not leak.

No microphone, no PortAudio and no hardware are required: a tiny FAKE ``sounddevice`` (pure
Python, returns a REAL int16 numpy buffer) is injected into ``sys.modules`` so the REAL
``resolve_input_device`` / ``record_audio`` / WAV write / ``emit_parametrizer_section`` code
paths run deterministically — and the produced WAV is validated with the stdlib ``wave``
reader (channels / rate / sample width / frame count == duration).

Covers:
- Helpers: get_music_dir, resolve_output_dir (default vs honored), build_unique_path
  (collision-proof, sequential, recorder_..._dev<tag>.wav shape), emit_parametrizer_section
  (atomic INI block round-trip)
- resolve_input_device: system default (device_arg None), explicit index, by-name substring,
  channel clamp to device max
- record_audio against the FAKE sounddevice: real WAV written + header read-back, sample_rate
  default == device native (0), explicit sample_rate honored, channel clamp, frame count
  matches duration
- main() end-stage: section emitted + target_agents triggered; missing-sounddevice path is
  reported, not crashed
- Registry integration: ChatWrappedAgentSpec, agent contract + parametrizer fields,
  Exec-Report ABSENCE (observational like Shoter/Camcorder), config.yaml defaults, CSS gradient
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
import wave
from functools import lru_cache

import numpy as np
import yaml
from django.test import SimpleTestCase


_REPO_AGENT_DIR = os.path.dirname(__file__)


# ---------------------------------------------------------------------------
# FAKE sounddevice — pure-Python stand-in for the PortAudio-backed library
# ---------------------------------------------------------------------------


class _FakeDefault:
    # default input index = 1 (the "Microphone Array" below), output = 2
    device = [1, 2]


class _FakeSounddevice:
    """Mimics the subset of the sounddevice API that recorder.py touches."""

    default = _FakeDefault()

    _DEVICES = [
        {'name': 'Sound Mapper - Input', 'max_input_channels': 2,
         'max_output_channels': 0, 'default_samplerate': 44100.0},
        {'name': 'Microphone Array (Intel Smart)', 'max_input_channels': 2,
         'max_output_channels': 0, 'default_samplerate': 48000.0},
        {'name': 'Speakers (Realtek HD Audio output)', 'max_input_channels': 0,
         'max_output_channels': 2, 'default_samplerate': 44100.0},
        {'name': 'USB Audio Mic', 'max_input_channels': 1,
         'max_output_channels': 0, 'default_samplerate': 16000.0},
    ]

    def __init__(self):
        self.last_rec = None
        self.fill_value = 0  # tests set this to craft a "hot" buffer for gain/clip

    def query_devices(self, device=None, kind=None):
        if device is not None:
            return dict(self._DEVICES[device])
        if kind == 'input':
            idx = self.default.device[0]
            info = dict(self._DEVICES[idx])
            info['index'] = idx
            return info
        return [dict(d) for d in self._DEVICES]

    def rec(self, frames, samplerate, channels, dtype, device):
        self.last_rec = {
            'frames': frames, 'samplerate': samplerate,
            'channels': channels, 'dtype': dtype, 'device': device,
        }
        # Return a REAL int16 buffer so the genuine wave-write path runs.
        return np.full((frames, channels), self.fill_value, dtype=np.int16)

    def wait(self):
        return None


def _install_fake_sounddevice():
    fake = _FakeSounddevice()
    sys.modules['sounddevice'] = fake
    return fake


def _remove_fake_sounddevice():
    sys.modules.pop('sounddevice', None)


# ---------------------------------------------------------------------------
# Module loader — exec the pool-agent script with cwd + handler save/restore
# ---------------------------------------------------------------------------


@lru_cache(maxsize=1)
def _load_recorder_module():
    module_path = os.path.join(_REPO_AGENT_DIR, 'agents', 'recorder', 'recorder.py')
    spec = importlib.util.spec_from_file_location(
        'agent_recorder_module_for_tests', module_path,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f'Unable to load Recorder module from {module_path}')

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


def _parse_ini_section(text, agent_type='RECORDER'):
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


class RecorderHelperTests(unittest.TestCase):
    def setUp(self):
        self.mod = _load_recorder_module()

    def test_default_temp_output_dir_nonempty(self):
        # Media defaults to <app>/Temp (<REDACTED> 2026-06-09), not the Music
        # known-folder — the get_music_dir helper was removed with that change.
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
            p1 = self.mod.build_unique_path(tmp, '1', 'wav')
            with open(p1, 'wb') as handle:
                handle.write(b'x')
            p2 = self.mod.build_unique_path(tmp, '1', 'wav')
            self.assertNotEqual(p1, p2)
            self.assertTrue(os.path.basename(p1).startswith('recorder_'))
            self.assertTrue(os.path.basename(p1).endswith('_dev1.wav'))

    def test_build_unique_path_default_device_tag(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = self.mod.build_unique_path(tmp, 'default', 'wav')
            self.assertTrue(os.path.basename(p).endswith('_devdefault.wav'))

    def test_emit_parametrizer_section_round_trip(self):
        result = {
            'output_path': r'C:\X\TlamatiniRecords\recorder_x_dev1.wav',
            'device_index': 1,
            'device_name': 'Microphone Array (Intel Smart)',
            'sample_rate': 48000,
            'channels': 1,
            'duration_seconds': 5.0,
            'gain_percent': 150.0,
            'clipped_samples': 42,
        }
        with _LogCapture() as cap:
            self.mod.emit_parametrizer_section(result)
        block = next(r for r in cap.records if 'INI_SECTION_RECORDER<<<' in r)
        fields = _parse_ini_section(block)
        self.assertEqual(fields['device_index'], '1')
        self.assertEqual(fields['device_name'], 'Microphone Array (Intel Smart)')
        self.assertEqual(fields['sample_rate'], '48000')
        self.assertEqual(fields['channels'], '1')
        self.assertEqual(fields['duration_seconds'], '5')
        self.assertEqual(fields['gain_percent'], '150')
        self.assertEqual(fields['clipped_samples'], '42')
        self.assertEqual(fields['format'], 'wav')
        self.assertTrue(fields['filename'].endswith('.wav'))
        self.assertIn('output_path', fields)
        self.assertIn('saved to', fields['response_body'])

    def test_emit_parametrizer_section_atomic_single_call(self):
        result = {
            'output_path': 'r.wav', 'device_index': -1, 'device_name': 'X',
            'sample_rate': 44100, 'channels': 2, 'duration_seconds': 3.5,
        }
        with _LogCapture() as cap:
            self.mod.emit_parametrizer_section(result)
        blocks = [r for r in cap.records if 'INI_SECTION_RECORDER<<<' in r]
        self.assertEqual(len(blocks), 1)
        self.assertIn('>>>END_SECTION_RECORDER', blocks[0])
        fields = _parse_ini_section(blocks[0])
        self.assertEqual(fields['channels'], '2')
        self.assertEqual(fields['duration_seconds'], '3.5')

    def test_apply_gain_unity_is_noop(self):
        buf = np.array([[100], [-200], [30000]], dtype=np.int16)
        out, clipped = self.mod._apply_gain(buf, 100)
        self.assertIs(out, buf)            # unity -> exact same object, untouched
        self.assertEqual(clipped, 0)

    def test_apply_gain_amplify_clips_and_counts(self):
        # 200% on a hot buffer: 20000->40000 (clip 32767), -20000->-40000
        # (clip -32768), 100->200 (no clip). Exactly 2 samples clip.
        buf = np.array([[20000], [-20000], [100]], dtype=np.int16)
        out, clipped = self.mod._apply_gain(buf, 200)
        self.assertEqual(clipped, 2)
        self.assertEqual(int(out[0, 0]), 32767)
        self.assertEqual(int(out[1, 0]), -32768)
        self.assertEqual(int(out[2, 0]), 200)

    def test_apply_gain_attenuate(self):
        buf = np.array([[10000], [-8000]], dtype=np.int16)
        out, clipped = self.mod._apply_gain(buf, 50)
        self.assertEqual(clipped, 0)
        self.assertEqual(int(out[0, 0]), 5000)
        self.assertEqual(int(out[1, 0]), -4000)

    def test_apply_gain_zero_is_silence(self):
        buf = np.array([[12345], [-9999]], dtype=np.int16)
        out, clipped = self.mod._apply_gain(buf, 0)
        self.assertEqual(clipped, 0)
        self.assertTrue((out == 0).all())


class RecorderDeviceResolutionTests(unittest.TestCase):
    def setUp(self):
        self.mod = _load_recorder_module()
        _install_fake_sounddevice()
        self.addCleanup(_remove_fake_sounddevice)

    def test_default_device_uses_none_arg_and_resolved_index(self):
        device_arg, device_index, device_name, info = self.mod.resolve_input_device(
            {'device_index': -1})
        self.assertIsNone(device_arg)              # None == sounddevice default
        self.assertEqual(device_index, 1)          # from sd.default.device[0]
        self.assertIn('Microphone Array', device_name)
        self.assertEqual(int(info['default_samplerate']), 48000)

    def test_explicit_index_is_honored(self):
        device_arg, device_index, device_name, _info = self.mod.resolve_input_device(
            {'device_index': 3})
        self.assertEqual(device_arg, 3)
        self.assertEqual(device_index, 3)
        self.assertEqual(device_name, 'USB Audio Mic')

    def test_by_name_substring_resolves_input_device(self):
        device_arg, device_index, device_name, _info = self.mod.resolve_input_device(
            {'device_index': -1, 'device_name': 'usb'})
        self.assertEqual(device_arg, 3)
        self.assertEqual(device_index, 3)
        self.assertEqual(device_name, 'USB Audio Mic')

    def test_by_name_no_match_raises(self):
        with self.assertRaises(RuntimeError):
            self.mod.resolve_input_device(
                {'device_index': -1, 'device_name': 'no-such-mic-xyz'})

    def test_list_input_devices_excludes_output_only(self):
        devices = self.mod._list_input_devices()
        names = [n for _i, n, _c, _r in devices]
        self.assertIn('USB Audio Mic', names)
        # The output-only "Speakers" device must be excluded.
        self.assertFalse(any('Speakers' in n for n in names))


class RecorderRecordTests(unittest.TestCase):
    def setUp(self):
        self.mod = _load_recorder_module()
        self.fake = _install_fake_sounddevice()
        self.addCleanup(_remove_fake_sounddevice)

    def _read_wav(self, path):
        with wave.open(path, 'rb') as wf:
            return {
                'channels': wf.getnchannels(),
                'rate': wf.getframerate(),
                'sampwidth': wf.getsampwidth(),
                'frames': wf.getnframes(),
            }

    def test_record_writes_valid_wav_with_native_rate(self):
        with tempfile.TemporaryDirectory() as tmp:
            # device_index -1 (default == idx 1, native 48000), sample_rate 0 -> native.
            result = self.mod.record_audio(
                {'device_index': -1, 'record_seconds': 1, 'sample_rate': 0, 'channels': 1},
                tmp)
            self.assertTrue(os.path.exists(result['output_path']))
            self.assertTrue(result['output_path'].endswith('.wav'))
            self.assertEqual(result['sample_rate'], 48000)  # device native default
            hdr = self._read_wav(result['output_path'])
            self.assertEqual(hdr['channels'], 1)
            self.assertEqual(hdr['rate'], 48000)
            self.assertEqual(hdr['sampwidth'], 2)           # int16
            self.assertEqual(hdr['frames'], 48000)          # 1s * 48000

    def test_explicit_sample_rate_is_honored(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = self.mod.record_audio(
                {'device_index': 3, 'record_seconds': 2, 'sample_rate': 16000, 'channels': 1},
                tmp)
            self.assertEqual(result['sample_rate'], 16000)
            self.assertEqual(result['duration_seconds'], 2)
            hdr = self._read_wav(result['output_path'])
            self.assertEqual(hdr['rate'], 16000)
            self.assertEqual(hdr['frames'], 32000)          # 2s * 16000

    def test_channels_clamped_to_device_max(self):
        with tempfile.TemporaryDirectory() as tmp:
            # USB mic (idx 3) is mono (max_input_channels == 1); request stereo.
            result = self.mod.record_audio(
                {'device_index': 3, 'record_seconds': 1, 'sample_rate': 16000, 'channels': 2},
                tmp)
            self.assertEqual(result['channels'], 1)         # clamped down
            self.assertEqual(self.fake.last_rec['channels'], 1)

    def test_record_default_gain_is_unity_and_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = self.mod.record_audio(
                {'device_index': 1, 'record_seconds': 1, 'sample_rate': 16000, 'channels': 1},
                tmp)
            self.assertEqual(result['gain_percent'], 100)
            self.assertEqual(result['clipped_samples'], 0)

    def test_record_gain_amplifies_and_counts_clips(self):
        self.fake.fill_value = 20000   # hot buffer: 20000 * 2.0 -> clips
        with tempfile.TemporaryDirectory() as tmp:
            result = self.mod.record_audio(
                {'device_index': 1, 'record_seconds': 1, 'sample_rate': 16000,
                 'channels': 1, 'input_gain_percent': 200},
                tmp)
            self.assertEqual(result['gain_percent'], 200)
            # Every one of the 16000 mono samples clips at this gain.
            self.assertEqual(result['clipped_samples'], 16000)

    def test_record_dirty_gain_value_coerces(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = self.mod.record_audio(
                {'device_index': 1, 'record_seconds': 1, 'sample_rate': 16000,
                 'channels': 1, 'input_gain_percent': '150 percent'},
                tmp)
            self.assertEqual(result['gain_percent'], 150)

    def test_dirty_numeric_record_seconds_does_not_crash(self):
        # Real incident: the wrapped request parser captured trailing words,
        # writing record_seconds == "1 from the default microphone". A naive
        # float(...) crashed the capture; _coerce_float must extract the 1.
        with tempfile.TemporaryDirectory() as tmp:
            result = self.mod.record_audio(
                {'device_index': -1, 'record_seconds': '1 from the default microphone',
                 'sample_rate': '48000 Hz', 'channels': 1},
                tmp)
            self.assertTrue(os.path.exists(result['output_path']))
            self.assertEqual(result['duration_seconds'], 1.0)
            self.assertEqual(result['sample_rate'], 48000)
            hdr = self._read_wav(result['output_path'])
            self.assertEqual(hdr['frames'], 48000)

    def test_coerce_helpers_never_raise(self):
        self.assertEqual(self.mod._coerce_float('1 from the default microphone', 5), 1.0)
        self.assertEqual(self.mod._coerce_int('48000 Hz', 0), 48000)
        self.assertEqual(self.mod._coerce_int('', 5), 5)
        self.assertEqual(self.mod._coerce_int(None, 7), 7)
        self.assertEqual(self.mod._coerce_int('-1', 0), -1)
        self.assertEqual(self.mod._coerce_int('garbage', 3), 3)

    def test_zero_or_negative_duration_falls_back(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = self.mod.record_audio(
                {'device_index': 1, 'record_seconds': 0, 'sample_rate': 48000, 'channels': 1},
                tmp)
            self.assertEqual(result['duration_seconds'], 5.0)   # default fallback

    def test_main_emits_section_and_triggers_targets(self):
        mod = self.mod
        with tempfile.TemporaryDirectory() as tmp:
            cfg = {'device_index': -1, 'record_seconds': 1, 'sample_rate': 48000,
                   'channels': 1, 'output_dir': tmp, 'target_agents': ['sleeper_1']}
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
            self.assertTrue(any('INI_SECTION_RECORDER<<<' in r for r in cap.records))
            block = next(r for r in cap.records if 'INI_SECTION_RECORDER<<<' in r)
            self.assertIn('format: wav', block)

    def test_main_missing_sounddevice_is_reported_not_crashed(self):
        mod = self.mod
        _remove_fake_sounddevice()  # simulate the library absent

        real_import = builtins.__import__

        def _no_sd(name, *a, **k):
            if name == 'sounddevice':
                raise ImportError('No module named sounddevice')
            return real_import(name, *a, **k)

        with tempfile.TemporaryDirectory() as tmp:
            cfg = {'device_index': -1, 'output_dir': tmp, 'target_agents': []}
            orig_chdir = os.getcwd()
            with _LogCapture() as cap, \
                    unittest.mock.patch.object(mod, 'load_config', return_value=cfg), \
                    unittest.mock.patch.object(mod, 'write_pid_file'), \
                    unittest.mock.patch.object(mod, 'remove_pid_file'), \
                    unittest.mock.patch('builtins.__import__', side_effect=_no_sd):
                with self.assertRaises(SystemExit) as ctx:
                    mod.main()
            os.chdir(orig_chdir)
            self.assertEqual(ctx.exception.code, 1)
            self.assertTrue(any('sounddevice' in r for r in cap.records))


# ---------------------------------------------------------------------------
# Registry / integration contracts
# ---------------------------------------------------------------------------


class RecorderRegistryTests(SimpleTestCase):
    def test_wrapped_chat_agent_spec_registered(self):
        from agent.chat_agent_registry import WRAPPED_CHAT_AGENT_SPECS
        spec = next((s for s in WRAPPED_CHAT_AGENT_SPECS
                     if s.tool_name == 'chat_agent_recorder'), None)
        self.assertIsNotNone(spec)
        self.assertEqual(spec.key, 'recorder')
        self.assertEqual(spec.template_dir, 'recorder')
        self.assertEqual(spec.display_name, 'Recorder')

    def test_agent_contract_parametrizer_fields(self):
        from agent.services.agent_contracts import (
            get_agent_contract,
            get_parametrizer_source_fields,
        )
        fields = get_parametrizer_source_fields().get('recorder')
        self.assertIsNotNone(fields)
        for expected in ('output_path', 'output_dir', 'filename', 'device_index',
                         'device_name', 'sample_rate', 'channels', 'duration_seconds',
                         'gain_percent', 'clipped_samples', 'format', 'response_body'):
            self.assertIn(expected, fields)
        contract = get_agent_contract('recorder')
        # Producer: a connection FROM recorder writes target_agents.
        self.assertEqual(contract.output_field_by_slot.get(0), 'target_agents')

    def test_config_yaml_defaults(self):
        config_path = os.path.join(_REPO_AGENT_DIR, 'agents', 'recorder', 'config.yaml')
        with open(config_path, 'r', encoding='utf-8') as handle:
            cfg = yaml.safe_load(handle)
        self.assertEqual(cfg['device_index'], -1)   # default == system default mic
        self.assertEqual(cfg['device_name'], '')
        self.assertEqual(cfg['record_seconds'], 5)
        self.assertEqual(cfg['sample_rate'], 0)      # 0 == device native default
        self.assertEqual(cfg['channels'], 1)
        self.assertEqual(cfg['input_gain_percent'], 100)   # default == unity
        self.assertEqual(cfg['output_dir'], '')
        self.assertIn('target_agents', cfg)

    def test_captured_in_exec_report(self):
        # Completeness contract (2026-06-07): EVERY agent that runs in Multi-Turn
        # — observational ones like Recorder INCLUDED — is captured in the Exec
        # report (auto-resolved from the wrapped chat-agent registry).
        from agent.mcp_agent import _resolve_exec_report_spec
        spec = _resolve_exec_report_spec('chat_agent_recorder')
        self.assertIsNotNone(spec)
        self.assertEqual(spec[1], 'Recorder')

    def test_parametrizer_section_type_registered(self):
        param_path = os.path.join(_REPO_AGENT_DIR, 'agents', 'parametrizer', 'parametrizer.py')
        with open(param_path, 'r', encoding='utf-8') as handle:
            text = handle.read()
        self.assertIn("'recorder'", text)

    def test_url_route_and_view_present(self):
        with open(os.path.join(_REPO_AGENT_DIR, 'urls.py'), 'r', encoding='utf-8') as handle:
            urls = handle.read()
        self.assertIn('update_recorder_connection', urls)
        with open(os.path.join(_REPO_AGENT_DIR, 'views.py'), 'r', encoding='utf-8') as handle:
            views = handle.read()
        self.assertIn('def update_recorder_connection_view', views)

    def test_migrations_present(self):
        mig_dir = os.path.join(_REPO_AGENT_DIR, 'migrations')
        self.assertTrue(os.path.exists(os.path.join(mig_dir, '0114_add_recorder.py')))
        self.assertTrue(os.path.exists(
            os.path.join(mig_dir, '0115_add_chat_agent_recorder_tool.py')))

    def test_css_gradient_present(self):
        css_path = os.path.join(
            _REPO_AGENT_DIR, 'static', 'agent', 'css', 'agentic_control_panel.css')
        with open(css_path, 'r', encoding='utf-8') as handle:
            css = handle.read()
        self.assertIn('.canvas-item.recorder-agent', css)

    def test_js_classmap_and_connector_wired(self):
        js_dir = os.path.join(_REPO_AGENT_DIR, 'static', 'agent', 'js')
        with open(os.path.join(js_dir, 'acp-canvas-core.js'), 'r', encoding='utf-8') as handle:
            core = handle.read()
        self.assertIn("'recorder': 'recorder-agent'", core)
        self.assertIn("=== 'recorder') updateRecorderConnection", core)
        with open(os.path.join(js_dir, 'acp-agent-connectors.js'), 'r', encoding='utf-8') as handle:
            conn = handle.read()
        self.assertIn('async function updateRecorderConnection', conn)
        with open(os.path.join(js_dir, 'acp-file-io.js'), 'r', encoding='utf-8') as handle:
            fileio = handle.read()
        self.assertIn("case 'recorder':", fileio)

    def test_requirements_pin_sounddevice(self):
        req_path = os.path.join(os.path.dirname(os.path.dirname(_REPO_AGENT_DIR)), 'requirements.txt')
        with open(req_path, 'r', encoding='utf-8') as handle:
            reqs = handle.read()
        self.assertIn('sounddevice', reqs)


if __name__ == '__main__':
    unittest.main()
