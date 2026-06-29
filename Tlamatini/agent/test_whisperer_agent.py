# ═══════════════════════════════════════════════════════════════════
#   ✦  T L A M A T I N I  ✦   —   "one who knows"
#
#   Created by  Angela López Mendoza   ·   @angelahack1
#   Developer · Architect · Creator of Tlamatini
#
#   Every line of this file was written by Angela López Mendoza.
# ═══════════════════════════════════════════════════════════════════
#   Tlamatini Author Banner — do not remove (releases scrub the name automatically)
"""Automated tests for the Whisperer workflow agent and its surrounding infrastructure.

Whisperer is SPEECH-TO-TEXT (STT). It is 100% self-sufficient for the microphone:
it OPENS, CONFIGURES and RECORDS the mic itself (via ``sounddevice`` + ``numpy``) — it does
NOT depend on the Recorder agent — or transcribes a given audio FILE, then runs a neural
recognizer (faster-whisper locally by default, with GPU auto-detect + an ALWAYS-present CPU
fallback; or a cloud Whisper API) and OUTPUTS a STRING of text. It is the speech-to-text
sibling of Talker (text-to-speech).

It is a standalone pool agent under ``agent/agents/whisperer/`` loaded here through
``importlib.util.spec_from_file_location`` with a cwd + logging-handler save/restore so its
module-level ``os.chdir`` / ``open(LOG_FILE_PATH)`` / ``logging.basicConfig`` side effects do
not leak.

No microphone, no PortAudio, no GPU and no model weights are required: tiny FAKE
``sounddevice`` / ``faster_whisper`` / ``ctranslate2`` modules (pure Python) are injected into
``sys.modules`` so the REAL ``record_from_microphone`` / ``resolve_local_device`` /
``transcribe_faster_whisper`` / ``run_whisperer`` / ``emit_parametrizer_section`` code paths run
deterministically.

Covers:
- Helpers: get_documents_dir, resolve_output_dir (default vs honored), build_unique_path
  (collision-proof, whisperer_*.txt shape), _coerce_*, _resample_linear, emit_parametrizer_section
  (atomic INI block round-trip whose body is the transcript)
- record_from_microphone against the FAKE sounddevice: float32 mono audio, channel clamp to the
  device max, downmix, software gain, resample to 16 kHz
- detect_cuda / resolve_local_device: GPU present -> cuda/float16, absent -> cpu/int8, forced
- transcribe_faster_whisper against the FAKE engine: returns the joined transcript; a GPU
  failure AUTOMATICALLY falls back to CPU (the no-GPU guarantee)
- run_whisperer: mic path, file path, engine_unavailable path (no faster-whisper, no cloud key)
- cleanup_with_ollama: no-op when disabled; keeps the raw transcript on any failure
- main() end-stage: section emitted + target_agents triggered (even on error)
- Registry integration: ChatWrappedAgentSpec, agent contract + parametrizer fields, Exec-Report
  capture (observational but still captured, 2026-06-07), config.yaml defaults, CSS gradient
  (unique), URL route, view, JS wiring (6 locations), parametrizer SECTION_AGENT_TYPES,
  migrations, requirements pin, demo-prompt catalog contiguity
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

import numpy as np
import yaml
from django.test import SimpleTestCase


_REPO_AGENT_DIR = os.path.dirname(__file__)


# ---------------------------------------------------------------------------
# FAKE sounddevice — pure-Python stand-in for the PortAudio-backed library
# ---------------------------------------------------------------------------


class _FakeDefault:
    device = [1, 2]  # default input index = 1, output = 2


class _FakeSounddevice:
    """Mimics the subset of the sounddevice API that whisperer.py touches."""

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
        self.fill_value = 0.25  # float32 amplitude the fake mic "captures"

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
        return np.full((frames, channels), self.fill_value, dtype=np.float32)

    def wait(self):
        return None


# ---------------------------------------------------------------------------
# FAKE faster_whisper + ctranslate2
# ---------------------------------------------------------------------------


class _FakeSegment:
    def __init__(self, text):
        self.text = text


class _FakeInfo:
    def __init__(self, language):
        self.language = language


class _FakeWhisperModel:
    """Records the device it was built on; fails on cuda when asked to."""

    fail_on_cuda = False
    built_devices = []

    def __init__(self, model, device='cpu', compute_type='int8'):
        self.model = model
        self.device = device
        self.compute_type = compute_type
        type(self).built_devices.append((device, compute_type))
        if device == 'cuda' and type(self).fail_on_cuda:
            raise RuntimeError("CUDA failed to initialize (no cuDNN)")

    def transcribe(self, audio, language=None, task='transcribe', beam_size=5,
                   vad_filter=True, word_timestamps=False):
        segments = [_FakeSegment(" hello"), _FakeSegment(" world")]
        return iter(segments), _FakeInfo(language or 'en')


class _FakeCtranslate2:
    cuda_count = 0

    def get_cuda_device_count(self):
        return self.cuda_count


def _install_fakes(cuda=0, fail_on_cuda=False):
    sd = _FakeSounddevice()
    sys.modules['sounddevice'] = sd

    fw = type(sys)('faster_whisper')
    _FakeWhisperModel.fail_on_cuda = fail_on_cuda
    _FakeWhisperModel.built_devices = []
    fw.WhisperModel = _FakeWhisperModel
    sys.modules['faster_whisper'] = fw

    ct = _FakeCtranslate2()
    ct.cuda_count = cuda
    sys.modules['ctranslate2'] = ct
    return sd, fw, ct


def _remove_fakes():
    for name in ('sounddevice', 'faster_whisper', 'ctranslate2'):
        sys.modules.pop(name, None)


# ---------------------------------------------------------------------------
# Module loader — exec the pool-agent script with cwd + handler save/restore
# ---------------------------------------------------------------------------


@lru_cache(maxsize=1)
def _load_whisperer_module():
    module_path = os.path.join(_REPO_AGENT_DIR, 'agents', 'whisperer', 'whisperer.py')
    spec = importlib.util.spec_from_file_location(
        'agent_whisperer_module_for_tests', module_path,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f'Unable to load Whisperer module from {module_path}')

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


def _parse_ini_section(text, agent_type='WHISPERER'):
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
# Helpers
# ---------------------------------------------------------------------------


class WhispererHelperTests(unittest.TestCase):
    def setUp(self):
        self.mod = _load_whisperer_module()

    def test_get_documents_dir_nonempty(self):
        path = self.mod.get_documents_dir()
        self.assertTrue(path)
        self.assertIsInstance(path, str)

    def test_resolve_output_dir_default_is_temp(self):
        # Transcripts default to <app>/Temp (Angela 2026-06-09), not Documents.
        out = self.mod.resolve_output_dir({})
        self.assertTrue(os.path.isabs(out))
        self.assertEqual(os.path.basename(os.path.normpath(out)), 'Temp')

    def test_resolve_output_dir_honors_configured_absolute(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = self.mod.resolve_output_dir({'output_dir': tmp})
            self.assertEqual(os.path.normpath(out), os.path.normpath(tmp))

    def test_build_unique_path_is_collision_proof(self):
        with tempfile.TemporaryDirectory() as tmp:
            p1 = self.mod.build_unique_path(tmp, 'txt')
            with open(p1, 'w') as handle:
                handle.write('x')
            p2 = self.mod.build_unique_path(tmp, 'txt')
            self.assertNotEqual(p1, p2)
            self.assertTrue(os.path.basename(p1).startswith('whisperer_'))
            self.assertTrue(os.path.basename(p1).endswith('.txt'))

    def test_coerce_helpers_never_raise(self):
        self.assertEqual(self.mod._coerce_float('5 seconds', 1), 5.0)
        self.assertEqual(self.mod._coerce_int('48000 Hz', 0), 48000)
        self.assertEqual(self.mod._coerce_int('', 5), 5)
        self.assertEqual(self.mod._coerce_int(None, 7), 7)
        self.assertEqual(self.mod._coerce_int('garbage', 3), 3)
        self.assertTrue(self.mod._coerce_bool('true', False))
        self.assertFalse(self.mod._coerce_bool('no', True))
        self.assertTrue(self.mod._coerce_bool('', True))

    def test_resample_linear_changes_length_to_target_rate(self):
        audio = np.ones(48000, dtype=np.float32)
        out = self.mod._resample_linear(audio, 48000, 16000)
        self.assertEqual(len(out), 16000)
        self.assertEqual(out.dtype, np.float32)

    def test_resample_linear_noop_same_rate(self):
        audio = np.ones(100, dtype=np.float32)
        out = self.mod._resample_linear(audio, 16000, 16000)
        self.assertEqual(len(out), 100)

    def test_emit_parametrizer_section_round_trip(self):
        result = {
            'transcript_path': r'C:\X\TlamatiniTranscripts\whisperer_x.txt',
            'audio_path': r'C:\X\TlamatiniTranscripts\whisperer_x.wav',
            'input_source': 'mic',
            'engine': 'faster-whisper',
            'model': 'base',
            'device': 'cpu',
            'language': 'en',
            'duration_seconds': 5.0,
            'segments': 2,
            'word_count': 2,
            'status': 'transcribed',
            'text': 'hello world',
        }
        with _LogCapture() as cap:
            self.mod.emit_parametrizer_section(result)
        blocks = [r for r in cap.records if 'INI_SECTION_WHISPERER<<<' in r]
        self.assertEqual(len(blocks), 1)              # atomic single call
        self.assertIn('>>>END_SECTION_WHISPERER', blocks[0])
        fields = _parse_ini_section(blocks[0])
        self.assertEqual(fields['engine'], 'faster-whisper')
        self.assertEqual(fields['model'], 'base')
        self.assertEqual(fields['device'], 'cpu')
        self.assertEqual(fields['language'], 'en')
        self.assertEqual(fields['status'], 'transcribed')
        self.assertEqual(fields['word_count'], '2')
        # The BODY is the transcript text itself.
        self.assertEqual(fields['response_body'], 'hello world')


# ---------------------------------------------------------------------------
# Microphone capture (self-contained)
# ---------------------------------------------------------------------------


class WhispererMicCaptureTests(unittest.TestCase):
    def setUp(self):
        self.mod = _load_whisperer_module()
        self.sd, _, _ = _install_fakes()
        self.addCleanup(_remove_fakes)

    def test_records_mono_float32_at_16k(self):
        audio, meta = self.mod.record_from_microphone(
            {'device_index': -1, 'record_seconds': 1, 'sample_rate': 0, 'channels': 1})
        self.assertEqual(audio.dtype, np.float32)
        self.assertEqual(audio.ndim, 1)
        self.assertEqual(len(audio), 16000)            # 1s captured at the 16k engine rate
        self.assertEqual(meta['device_index'], 1)      # default device index

    def test_channels_clamped_to_device_max_and_downmixed(self):
        # USB mic (idx 3) is mono; request stereo -> clamp to 1, mono output.
        audio, meta = self.mod.record_from_microphone(
            {'device_index': 3, 'record_seconds': 1, 'channels': 2})
        self.assertEqual(meta['channels'], 1)
        self.assertEqual(self.sd.last_rec['channels'], 1)
        self.assertEqual(audio.ndim, 1)

    def test_capture_at_device_rate_is_resampled_to_16k(self):
        audio, _meta = self.mod.record_from_microphone(
            {'device_index': 1, 'record_seconds': 1, 'sample_rate': 48000, 'channels': 1})
        self.assertEqual(self.sd.last_rec['samplerate'], 48000)  # captured at 48k
        self.assertEqual(len(audio), 16000)                      # resampled down to 16k

    def test_software_gain_applied(self):
        self.sd.fill_value = 0.5
        audio, _meta = self.mod.record_from_microphone(
            {'device_index': 1, 'record_seconds': 1, 'sample_rate': 0,
             'channels': 1, 'input_gain_percent': 200})
        # 0.5 * 2.0 = 1.0 (clipped at 1.0)
        self.assertAlmostEqual(float(audio.max()), 1.0, places=5)

    def test_dirty_numeric_record_seconds_does_not_crash(self):
        audio, meta = self.mod.record_from_microphone(
            {'device_index': -1, 'record_seconds': '5 seconds please', 'sample_rate': 0})
        self.assertEqual(meta['duration_seconds'], 5.0)
        self.assertEqual(len(audio), 16000 * 5)


# ---------------------------------------------------------------------------
# Engine resolution + transcription (GPU auto-detect + CPU fallback)
# ---------------------------------------------------------------------------


class WhispererEngineTests(unittest.TestCase):
    def setUp(self):
        self.mod = _load_whisperer_module()

    def test_detect_cuda_true_when_devices_present(self):
        _install_fakes(cuda=1)
        self.addCleanup(_remove_fakes)
        self.assertTrue(self.mod.detect_cuda())

    def test_detect_cuda_false_when_absent(self):
        _install_fakes(cuda=0)
        self.addCleanup(_remove_fakes)
        self.assertFalse(self.mod.detect_cuda())

    def test_resolve_local_device_auto_gpu(self):
        _install_fakes(cuda=1)
        self.addCleanup(_remove_fakes)
        device, compute = self.mod.resolve_local_device({'device': 'auto'})
        self.assertEqual(device, 'cuda')
        self.assertEqual(compute, 'float16')

    def test_resolve_local_device_auto_cpu(self):
        _install_fakes(cuda=0)
        self.addCleanup(_remove_fakes)
        device, compute = self.mod.resolve_local_device({'device': 'auto'})
        self.assertEqual(device, 'cpu')
        self.assertEqual(compute, 'int8')

    def test_resolve_local_device_forced_cpu(self):
        _install_fakes(cuda=1)
        self.addCleanup(_remove_fakes)
        device, _compute = self.mod.resolve_local_device({'device': 'cpu'})
        self.assertEqual(device, 'cpu')

    def test_transcribe_returns_joined_text(self):
        _install_fakes(cuda=0)
        self.addCleanup(_remove_fakes)
        audio = np.zeros(16000, dtype=np.float32)
        tr = self.mod.transcribe_faster_whisper(audio, {'model': 'base', 'device': 'cpu'})
        self.assertEqual(tr['text'], 'hello world')
        self.assertEqual(tr['segments'], 2)
        self.assertEqual(tr['device'], 'cpu')
        self.assertEqual(tr['engine'], 'faster-whisper')

    def test_gpu_failure_falls_back_to_cpu(self):
        # The no-GPU guarantee: a CUDA build failure auto-retries on CPU.
        _install_fakes(cuda=1, fail_on_cuda=True)
        self.addCleanup(_remove_fakes)
        audio = np.zeros(16000, dtype=np.float32)
        tr = self.mod.transcribe_faster_whisper(audio, {'model': 'base', 'device': 'cuda'})
        self.assertEqual(tr['device'], 'cpu')          # fell back
        self.assertEqual(tr['text'], 'hello world')
        # It tried cuda first, then cpu.
        self.assertIn(('cuda', 'float16'), _FakeWhisperModel.built_devices)
        self.assertIn(('cpu', 'int8'), _FakeWhisperModel.built_devices)


# ---------------------------------------------------------------------------
# Full pipeline
# ---------------------------------------------------------------------------


class WhispererPipelineTests(unittest.TestCase):
    def setUp(self):
        self.mod = _load_whisperer_module()

    def test_run_whisperer_mic_path(self):
        _install_fakes(cuda=0)
        self.addCleanup(_remove_fakes)
        with tempfile.TemporaryDirectory() as tmp:
            result = self.mod.run_whisperer(
                {'input_source': 'mic', 'record_seconds': 1, 'engine': 'faster-whisper',
                 'model': 'base', 'device': 'auto', 'ollama_cleanup': False},
                tmp)
            self.assertEqual(result['status'], 'transcribed')
            self.assertEqual(result['text'], 'hello world')
            self.assertEqual(result['input_source'], 'mic')
            self.assertEqual(result['word_count'], 2)
            self.assertTrue(os.path.exists(result['transcript_path']))
            with open(result['transcript_path'], encoding='utf-8') as f:
                self.assertEqual(f.read(), 'hello world')

    def test_run_whisperer_file_path(self):
        _install_fakes(cuda=0)
        self.addCleanup(_remove_fakes)
        with tempfile.TemporaryDirectory() as tmp:
            audio_file = os.path.join(tmp, 'clip.wav')
            with open(audio_file, 'wb') as f:
                f.write(b'RIFFfake')
            result = self.mod.run_whisperer(
                {'input_source': 'file', 'audio_file': audio_file,
                 'engine': 'faster-whisper', 'model': 'base'},
                tmp)
            self.assertEqual(result['status'], 'transcribed')
            self.assertEqual(result['input_source'], 'file')
            self.assertEqual(os.path.normpath(result['audio_path']),
                             os.path.normpath(audio_file))

    def test_run_whisperer_missing_file_raises(self):
        _install_fakes(cuda=0)
        self.addCleanup(_remove_fakes)
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(RuntimeError):
                self.mod.run_whisperer(
                    {'input_source': 'file', 'audio_file': os.path.join(tmp, 'nope.wav')},
                    tmp)

    def test_engine_unavailable_when_no_faster_whisper_and_no_key(self):
        # sounddevice present (mic), but faster_whisper absent and no cloud key.
        sys.modules['sounddevice'] = _FakeSounddevice()
        self.addCleanup(_remove_fakes)
        real_import = builtins.__import__

        def _no_fw(name, *a, **k):
            if name == 'faster_whisper':
                raise ImportError('No module named faster_whisper')
            return real_import(name, *a, **k)

        with tempfile.TemporaryDirectory() as tmp:
            with unittest.mock.patch.dict(os.environ, {}, clear=False) as _env:
                os.environ.pop('GROQ_API_KEY', None)
                os.environ.pop('OPENAI_API_KEY', None)
                with unittest.mock.patch('builtins.__import__', side_effect=_no_fw):
                    result = self.mod.run_whisperer(
                        {'input_source': 'mic', 'record_seconds': 1,
                         'engine': 'faster-whisper'},
                        tmp)
            self.assertEqual(result['status'], 'engine_unavailable')

    def test_cleanup_with_ollama_disabled_is_noop(self):
        out = self.mod.cleanup_with_ollama('hello world', {'ollama_cleanup': False})
        self.assertEqual(out, 'hello world')

    def test_cleanup_with_ollama_keeps_text_on_failure(self):
        # Enabled but the HTTP call fails -> returns the raw transcript, never raises.
        with unittest.mock.patch.object(self.mod.urllib.request, 'urlopen',
                                        side_effect=OSError('connection refused')):
            out = self.mod.cleanup_with_ollama('raw text', {'ollama_cleanup': True})
        self.assertEqual(out, 'raw text')

    def test_main_emits_section_and_triggers_targets(self):
        mod = self.mod
        _install_fakes(cuda=0)
        self.addCleanup(_remove_fakes)
        with tempfile.TemporaryDirectory() as tmp:
            cfg = {'input_source': 'mic', 'record_seconds': 1, 'engine': 'faster-whisper',
                   'model': 'base', 'device': 'auto', 'output_dir': tmp,
                   'target_agents': ['prompter_1']}
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
            self.assertEqual(started, ['prompter_1'])
            self.assertTrue(any('INI_SECTION_WHISPERER<<<' in r for r in cap.records))

    def test_main_missing_sounddevice_is_reported_not_crashed(self):
        mod = self.mod
        _remove_fakes()
        real_import = builtins.__import__

        def _no_sd(name, *a, **k):
            if name == 'sounddevice':
                raise ImportError('No module named sounddevice')
            return real_import(name, *a, **k)

        with tempfile.TemporaryDirectory() as tmp:
            cfg = {'input_source': 'mic', 'output_dir': tmp, 'target_agents': []}
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


class WhispererRegistryTests(SimpleTestCase):
    def test_wrapped_chat_agent_spec_registered(self):
        from agent.chat_agent_registry import WRAPPED_CHAT_AGENT_SPECS
        spec = next((s for s in WRAPPED_CHAT_AGENT_SPECS
                     if s.tool_name == 'chat_agent_whisperer'), None)
        self.assertIsNotNone(spec)
        self.assertEqual(spec.key, 'whisperer')
        self.assertEqual(spec.template_dir, 'whisperer')
        self.assertEqual(spec.display_name, 'Whisperer')

    def test_agent_contract_parametrizer_fields(self):
        from agent.services.agent_contracts import (
            get_agent_contract,
            get_parametrizer_source_fields,
        )
        fields = get_parametrizer_source_fields().get('whisperer')
        self.assertIsNotNone(fields)
        for expected in ('transcript_path', 'audio_path', 'input_source', 'engine',
                         'model', 'device', 'language', 'duration_seconds', 'segments',
                         'word_count', 'status', 'response_body'):
            self.assertIn(expected, fields)
        contract = get_agent_contract('whisperer')
        self.assertEqual(contract.output_field_by_slot.get(0), 'target_agents')

    def test_config_yaml_defaults(self):
        config_path = os.path.join(_REPO_AGENT_DIR, 'agents', 'whisperer', 'config.yaml')
        with open(config_path, 'r', encoding='utf-8') as handle:
            cfg = yaml.safe_load(handle)
        self.assertEqual(cfg['input_source'], 'mic')
        self.assertEqual(cfg['audio_file'], '')
        self.assertEqual(cfg['record_seconds'], 30)
        self.assertEqual(cfg['device_index'], -1)
        self.assertEqual(cfg['engine'], 'faster-whisper')
        self.assertEqual(cfg['model'], 'base')
        self.assertEqual(cfg['device'], 'auto')
        self.assertEqual(cfg['compute_type'], 'auto')
        self.assertEqual(cfg['language'], '')
        self.assertEqual(cfg['task'], 'transcribe')
        self.assertIn('target_agents', cfg)

    def test_captured_in_exec_report(self):
        # Completeness contract (2026-06-07): EVERY Multi-Turn agent — observational
        # ones like Whisperer INCLUDED — is captured in the Exec report.
        from agent.mcp_agent import _resolve_exec_report_spec
        spec = _resolve_exec_report_spec('chat_agent_whisperer')
        self.assertIsNotNone(spec)
        self.assertEqual(spec[1], 'Whisperer')

    def test_parametrizer_section_type_registered(self):
        param_path = os.path.join(_REPO_AGENT_DIR, 'agents', 'parametrizer', 'parametrizer.py')
        with open(param_path, 'r', encoding='utf-8') as handle:
            text = handle.read()
        self.assertIn("'whisperer'", text)

    def test_url_route_and_view_present(self):
        with open(os.path.join(_REPO_AGENT_DIR, 'urls.py'), 'r', encoding='utf-8') as handle:
            urls = handle.read()
        self.assertIn('update_whisperer_connection', urls)
        with open(os.path.join(_REPO_AGENT_DIR, 'views.py'), 'r', encoding='utf-8') as handle:
            views = handle.read()
        self.assertIn('def update_whisperer_connection_view', views)

    def test_migrations_present(self):
        mig_dir = os.path.join(_REPO_AGENT_DIR, 'migrations')
        self.assertTrue(os.path.exists(os.path.join(mig_dir, '0123_add_whisperer.py')))
        self.assertTrue(os.path.exists(
            os.path.join(mig_dir, '0124_add_chat_agent_whisperer_tool.py')))
        self.assertTrue(os.path.exists(
            os.path.join(mig_dir, '0125_add_whisperer_demo_prompt.py')))

    def test_css_gradient_present(self):
        css_path = os.path.join(
            _REPO_AGENT_DIR, 'static', 'agent', 'css', 'agentic_control_panel.css')
        with open(css_path, 'r', encoding='utf-8') as handle:
            css = handle.read()
        self.assertIn('.canvas-item.whisperer-agent', css)

    def test_js_classmap_and_connector_wired(self):
        js_dir = os.path.join(_REPO_AGENT_DIR, 'static', 'agent', 'js')
        with open(os.path.join(js_dir, 'acp-canvas-core.js'), 'r', encoding='utf-8') as handle:
            core = handle.read()
        self.assertIn("'whisperer': 'whisperer-agent'", core)
        self.assertIn("=== 'whisperer') updateWhispererConnection", core)
        with open(os.path.join(js_dir, 'acp-agent-connectors.js'), 'r', encoding='utf-8') as handle:
            conn = handle.read()
        self.assertIn('async function updateWhispererConnection', conn)
        with open(os.path.join(js_dir, 'acp-canvas-undo.js'), 'r', encoding='utf-8') as handle:
            undo = handle.read()
        self.assertIn('updateWhispererConnection', undo)
        with open(os.path.join(js_dir, 'acp-file-io.js'), 'r', encoding='utf-8') as handle:
            fileio = handle.read()
        self.assertIn("case 'whisperer':", fileio)

    def test_flow_generator_branch_present(self):
        js_path = os.path.join(_REPO_AGENT_DIR, 'static', 'agent', 'js', 'agent_page_chat.js')
        with open(js_path, 'r', encoding='utf-8') as handle:
            chat = handle.read()
        self.assertIn("lower === 'whisperer'", chat)

    def test_requirements_pin_faster_whisper(self):
        req_path = os.path.join(os.path.dirname(os.path.dirname(_REPO_AGENT_DIR)), 'requirements.txt')
        with open(req_path, 'r', encoding='utf-8') as handle:
            reqs = handle.read()
        self.assertIn('faster-whisper', reqs)

    def test_demo_prompt_catalog_contiguous(self):
        # The catalog dropdown breaks at the first gap; the Whisperer demo must
        # APPEND at slot 74 with no renumber.
        mig_path = os.path.join(
            _REPO_AGENT_DIR, 'migrations', '0125_add_whisperer_demo_prompt.py')
        with open(mig_path, 'r', encoding='utf-8') as handle:
            text = handle.read()
        self.assertIn('(74,', text)


if __name__ == '__main__':
    unittest.main()
