# ═══════════════════════════════════════════════════════════════════
#   ✦  T L A M A T I N I  ✦   —   "one who knows"
#
#   Crafted with heart by  Angela   ·   @angelahack1
#   Developer · Architect · Creator of Tlamatini
#
#   Every line of this file was written by Angela.
# ═══════════════════════════════════════════════════════════════════
#   Tlamatini Author Banner — do not remove (releases scrub the name automatically)
"""Automated tests for the AudioPlayer workflow agent and its surrounding infrastructure.

AudioPlayer PLAYS an audio FILE through a system OUTPUT device (speakers / audio out) via
``soundfile`` (decode) + ``sounddevice`` (stream). It is the playback counterpart of the
media family (Shoter = screen, Camcorder = camera, Recorder = microphone-IN, AudioPlayer =
speakers-OUT). It is a standalone pool agent under ``agent/agents/audioplayer/`` loaded here
through ``importlib.util.spec_from_file_location`` with a cwd + logging-handler save/restore
so its module-level ``os.chdir`` / ``open(LOG_FILE_PATH)`` / ``logging.basicConfig`` side
effects do not leak.

No speakers, no PortAudio and no hardware are required: a tiny FAKE ``soundfile`` (returns a
REAL numpy buffer) and a FAKE ``sounddevice`` (an OutputStream that drives the REAL callback to
completion and captures every emitted frame) are injected into ``sys.modules`` so the REAL
``resolve_output_device`` / ``_downmix`` / ``_apply_volume`` / ``play_audio`` truncate+loop
streaming code runs deterministically — and the captured output is asserted frame-for-frame
against the expected truncated / looped / full signal.

Covers:
- Helpers: resolve_audio_file (abs / rel / empty / quoted), _apply_volume (unity no-op, amplify
  clip-count, attenuate, silence), _downmix (stereo->mono mean, no-op, keep-first),
  emit_parametrizer_section + emit_parametrizer_error_section (atomic INI round-trip)
- resolve_output_device: system default (device_arg None), explicit index, by-name substring,
  by-name no-match raises, output list excludes input-only devices
- play_audio against the fakes: whole-file-once (time_played 0), TRUNCATION (file longer than
  time_played), LOOP exact (2x) and LOOP partial (2.5x) with frame-exact content, native vs
  forced sample_rate, channel downmix on a mono device, volume clip accounting, missing/absent file
- main() end-stage: section emitted + target_agents triggered (success); failure emits an error
  section AND still triggers targets; missing soundfile/sounddevice reported not crashed
- Registry integration: ChatWrappedAgentSpec, agent contract + parametrizer fields, tools.py
  top-level promotion, Exec-Report ABSENCE (observational), config.yaml defaults, CSS gradient,
  URL route + view, JS wiring, parametrizer SECTION_AGENT_TYPES, migrations, requirements pin
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
# FAKE soundfile / sounddevice — pure-Python stand-ins (no libsndfile/PortAudio)
# ---------------------------------------------------------------------------


class _FakeSoundfile:
    """Mimics the subset of the soundfile API that audioplayer.py touches."""

    def __init__(self):
        # The test sets (data, samplerate) before calling play_audio.
        self.data = np.zeros((48000, 1), dtype=np.float32)
        self.samplerate = 48000
        self.read_calls = []

    def read(self, path, dtype='float32', always_2d=True):
        self.read_calls.append({'path': path, 'dtype': dtype, 'always_2d': always_2d})
        data = self.data.astype(dtype)
        if always_2d and data.ndim == 1:
            data = data.reshape(-1, 1)
        return data, self.samplerate


class _FakeCallbackStop(Exception):
    pass


class _FakeOutputStream:
    """Drives the REAL callback to completion, capturing every emitted block."""

    def __init__(self, samplerate, channels, dtype, device, callback,
                 finished_callback, blocksize=997):
        self.samplerate = samplerate
        self.channels = channels
        self.dtype = dtype
        self.device = device
        self.callback = callback
        self.finished_callback = finished_callback
        self.blocksize = blocksize
        self._blocks = []

    def __enter__(self):
        guard = 0
        while True:
            guard += 1
            if guard > 5_000_000:           # safety net against an infinite callback
                raise RuntimeError("fake OutputStream callback never stopped")
            outdata = np.zeros((self.blocksize, self.channels), dtype=np.float32)
            try:
                self.callback(outdata, self.blocksize, None, None)
            except _FakeCallbackStop:
                self._blocks.append(outdata.copy())   # final (possibly padded) block
                break
            else:
                self._blocks.append(outdata.copy())
        if self.finished_callback:
            self.finished_callback()
        return self

    def __exit__(self, *_a):
        return False

    @property
    def played(self):
        if not self._blocks:
            return np.zeros((0, self.channels), dtype=np.float32)
        return np.concatenate(self._blocks, axis=0)


class _FakeDefault:
    device = [1, 2]   # input default = 1 (mic), output default = 2 (Speakers)


class _FakeSounddevice:
    """Mimics the subset of the sounddevice OUTPUT API that audioplayer.py touches."""

    CallbackStop = _FakeCallbackStop

    _DEVICES = [
        {'name': 'Sound Mapper - Output', 'max_input_channels': 0,
         'max_output_channels': 2, 'default_samplerate': 44100.0},                 # 0
        {'name': 'Microphone Array (Intel Smart)', 'max_input_channels': 2,
         'max_output_channels': 0, 'default_samplerate': 48000.0},                 # 1 (input-only)
        {'name': 'Speakers (Realtek HD Audio output)', 'max_input_channels': 0,
         'max_output_channels': 2, 'default_samplerate': 44100.0},                 # 2 (default out)
        {'name': 'Headphones (USB Audio)', 'max_input_channels': 0,
         'max_output_channels': 2, 'default_samplerate': 48000.0},                 # 3
        {'name': 'Mono Speaker', 'max_input_channels': 0,
         'max_output_channels': 1, 'default_samplerate': 48000.0},                 # 4
    ]

    def __init__(self):
        self.default = _FakeDefault()
        self.last_stream = None

    def query_devices(self, device=None, kind=None):
        if device is not None:
            return dict(self._DEVICES[device])
        if kind == 'output':
            idx = self.default.device[1]
            info = dict(self._DEVICES[idx])
            info['index'] = idx
            return info
        return [dict(d) for d in self._DEVICES]

    def OutputStream(self, **kwargs):
        stream = _FakeOutputStream(**kwargs)
        self.last_stream = stream
        return stream


def _install_fakes(data=None, samplerate=48000):
    fake_sf = _FakeSoundfile()
    if data is not None:
        fake_sf.data = data
    fake_sf.samplerate = samplerate
    fake_sd = _FakeSounddevice()
    sys.modules['soundfile'] = fake_sf
    sys.modules['sounddevice'] = fake_sd
    return fake_sf, fake_sd


def _remove_fakes():
    sys.modules.pop('soundfile', None)
    sys.modules.pop('sounddevice', None)


# ---------------------------------------------------------------------------
# Module loader — exec the pool-agent script with cwd + handler save/restore
# ---------------------------------------------------------------------------


@lru_cache(maxsize=1)
def _load_audioplayer_module():
    module_path = os.path.join(_REPO_AGENT_DIR, 'agents', 'audioplayer', 'audioplayer.py')
    spec = importlib.util.spec_from_file_location(
        'agent_audioplayer_module_for_tests', module_path,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f'Unable to load AudioPlayer module from {module_path}')

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


def _parse_ini_section(text, agent_type='AUDIOPLAYER'):
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


def _ramp(frames, channels=1, scale=0.5):
    """A deterministic, non-constant signal so loop/truncate content is verifiable."""
    base = (np.arange(frames, dtype=np.float32) % 100) / 100.0 * scale
    if channels == 1:
        return base.reshape(-1, 1)
    return np.stack([base * (c + 1) / channels for c in range(channels)], axis=1).astype(np.float32)


# ---------------------------------------------------------------------------
# Agent-module helper logic
# ---------------------------------------------------------------------------


class AudioPlayerHelperTests(unittest.TestCase):
    def setUp(self):
        self.mod = _load_audioplayer_module()

    def test_resolve_audio_file_empty(self):
        self.assertEqual(self.mod.resolve_audio_file({}), '')
        self.assertEqual(self.mod.resolve_audio_file({'audio_file': '   '}), '')

    def test_resolve_audio_file_absolute_and_quoted(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = os.path.join(tmp, 'clip.wav')
            out = self.mod.resolve_audio_file({'audio_file': f'"{target}"'})
            self.assertEqual(os.path.normpath(out), os.path.normpath(target))
            self.assertTrue(os.path.isabs(out))

    def test_resolve_audio_file_relative_is_anchored_to_script_dir(self):
        out = self.mod.resolve_audio_file({'audio_file': 'sub/beep.wav'})
        self.assertTrue(os.path.isabs(out))
        self.assertTrue(out.endswith(os.path.join('sub', 'beep.wav')))

    def test_apply_volume_unity_is_noop(self):
        buf = np.array([[0.1], [-0.2], [0.9]], dtype=np.float32)
        out, clipped = self.mod._apply_volume(buf, 100)
        self.assertIs(out, buf)
        self.assertEqual(clipped, 0)

    def test_apply_volume_amplify_clips_and_counts(self):
        buf = np.array([[0.8], [-0.8], [0.1]], dtype=np.float32)
        out, clipped = self.mod._apply_volume(buf, 200)   # 0.8*2=1.6 clip, -1.6 clip, 0.2 ok
        self.assertEqual(clipped, 2)
        self.assertAlmostEqual(float(out[0, 0]), 1.0, places=5)
        self.assertAlmostEqual(float(out[1, 0]), -1.0, places=5)
        self.assertAlmostEqual(float(out[2, 0]), 0.2, places=5)

    def test_apply_volume_attenuate(self):
        buf = np.array([[0.6], [-0.4]], dtype=np.float32)
        out, clipped = self.mod._apply_volume(buf, 50)
        self.assertEqual(clipped, 0)
        self.assertAlmostEqual(float(out[0, 0]), 0.3, places=5)
        self.assertAlmostEqual(float(out[1, 0]), -0.2, places=5)

    def test_apply_volume_zero_is_silence(self):
        buf = np.array([[0.5], [-0.9]], dtype=np.float32)
        out, clipped = self.mod._apply_volume(buf, 0)
        self.assertEqual(clipped, 0)
        self.assertTrue((out == 0).all())

    def test_downmix_stereo_to_mono_is_mean(self):
        buf = np.array([[0.2, 0.4], [-0.6, 0.0]], dtype=np.float32)
        out = self.mod._downmix(buf, 1)
        self.assertEqual(out.shape, (2, 1))
        self.assertAlmostEqual(float(out[0, 0]), 0.3, places=5)
        self.assertAlmostEqual(float(out[1, 0]), -0.3, places=5)

    def test_downmix_noop_when_target_ge_source(self):
        buf = np.array([[0.2, 0.4]], dtype=np.float32)
        self.assertIs(self.mod._downmix(buf, 2), buf)
        self.assertIs(self.mod._downmix(buf, 5), buf)

    def test_downmix_keep_first_channels(self):
        buf = np.array([[0.1, 0.2, 0.3, 0.4]], dtype=np.float32)
        out = self.mod._downmix(buf, 2)
        self.assertEqual(out.shape, (1, 2))
        self.assertAlmostEqual(float(out[0, 0]), 0.1, places=5)
        self.assertAlmostEqual(float(out[0, 1]), 0.2, places=5)

    def test_coerce_helpers_never_raise(self):
        self.assertEqual(self.mod._coerce_float('10 seconds', 0), 10.0)
        self.assertEqual(self.mod._coerce_int('48000 Hz', 0), 48000)
        self.assertEqual(self.mod._coerce_int('', 5), 5)
        self.assertEqual(self.mod._coerce_int(None, 7), 7)
        self.assertEqual(self.mod._coerce_float('garbage', 2.5), 2.5)

    def test_emit_parametrizer_section_round_trip(self):
        result = {
            'input_path': r'C:\Music\song.wav', 'device_index': 2,
            'device_name': 'Speakers (Realtek HD Audio output)',
            'file_sample_rate': 44100, 'play_sample_rate': 44100, 'channels': 2,
            'volume_percent': 150.0, 'clipped_samples': 7,
            'file_duration_seconds': 3.5, 'time_played_requested': 10.0,
            'played_seconds': 10.0, 'play_mode': 'looped', 'loops': 2,
            'partial_segment': True, 'format': 'wav',
        }
        with _LogCapture() as cap:
            self.mod.emit_parametrizer_section(result)
        block = next(r for r in cap.records if 'INI_SECTION_AUDIOPLAYER<<<' in r)
        self.assertEqual(cap.records.count(block), 1)        # atomic single call
        fields = _parse_ini_section(block)
        self.assertEqual(fields['input_path'], r'C:\Music\song.wav')
        self.assertEqual(fields['filename'], 'song.wav')
        self.assertEqual(fields['played_seconds'], '10')
        self.assertEqual(fields['play_mode'], 'looped')
        self.assertEqual(fields['loops'], '2')
        self.assertEqual(fields['partial_segment'], 'true')
        self.assertEqual(fields['volume_percent'], '150')
        self.assertEqual(fields['clipped_samples'], '7')
        self.assertEqual(fields['status'], 'played')
        self.assertIn('Played', fields['response_body'])

    def test_emit_error_section_round_trip(self):
        with _LogCapture() as cap:
            self.mod.emit_parametrizer_error_section(
                r'C:\Music\missing.wav', 'Audio file not found:\nline2', 30.0)
        block = next(r for r in cap.records if 'INI_SECTION_AUDIOPLAYER<<<' in r)
        fields = _parse_ini_section(block)
        self.assertEqual(fields['status'], 'error')
        self.assertEqual(fields['play_mode'], 'error')
        self.assertEqual(fields['filename'], 'missing.wav')
        self.assertEqual(fields['time_played_requested'], '30')
        # multi-line error must be flattened to one line inside the block body
        self.assertIn('FAILED', fields['response_body'])
        self.assertNotIn('\n', fields['response_body'].replace('\n', ''))


# ---------------------------------------------------------------------------
# Output-device resolution
# ---------------------------------------------------------------------------


class AudioPlayerDeviceResolutionTests(unittest.TestCase):
    def setUp(self):
        self.mod = _load_audioplayer_module()
        _install_fakes()
        self.addCleanup(_remove_fakes)

    def test_default_device_uses_none_arg_and_resolved_index(self):
        device_arg, device_index, device_name, info = self.mod.resolve_output_device(
            {'device_index': -1})
        self.assertIsNone(device_arg)             # None == sounddevice default
        self.assertEqual(device_index, 2)         # from sd.default.device[1]
        self.assertIn('Speakers', device_name)
        self.assertEqual(int(info['max_output_channels']), 2)

    def test_explicit_index_is_honored(self):
        device_arg, device_index, device_name, _info = self.mod.resolve_output_device(
            {'device_index': 3})
        self.assertEqual(device_arg, 3)
        self.assertEqual(device_index, 3)
        self.assertEqual(device_name, 'Headphones (USB Audio)')

    def test_by_name_substring_resolves_output_device(self):
        device_arg, device_index, device_name, _info = self.mod.resolve_output_device(
            {'device_index': -1, 'device_name': 'headphones'})
        self.assertEqual(device_arg, 3)
        self.assertEqual(device_index, 3)
        self.assertEqual(device_name, 'Headphones (USB Audio)')

    def test_by_name_no_match_raises(self):
        with self.assertRaises(RuntimeError):
            self.mod.resolve_output_device(
                {'device_index': -1, 'device_name': 'no-such-speaker-xyz'})

    def test_list_output_devices_excludes_input_only(self):
        devices = self.mod._list_output_devices()
        names = [n for _i, n, _c, _r in devices]
        self.assertIn('Speakers (Realtek HD Audio output)', names)
        # The input-only "Microphone Array" device must be excluded.
        self.assertFalse(any('Microphone Array' in n for n in names))


# ---------------------------------------------------------------------------
# play_audio — the truncate / loop / full streaming math, frame-exact
# ---------------------------------------------------------------------------


class AudioPlayerPlaybackTests(unittest.TestCase):
    def setUp(self):
        self.mod = _load_audioplayer_module()
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = os.path.join(self.tmp.name, 'clip.wav')
        with open(self.path, 'wb') as handle:
            handle.write(b'RIFF....')   # existence only; the FAKE soundfile supplies samples

    def _play(self, data, samplerate, cfg):
        fake_sf, fake_sd = _install_fakes(data=data, samplerate=samplerate)
        self.addCleanup(_remove_fakes)
        cfg = dict(cfg)
        cfg.setdefault('audio_file', self.path)
        result = self.mod.play_audio(cfg)
        return result, fake_sd.last_stream

    def test_full_plays_whole_file_once(self):
        src = _ramp(48000, channels=1)
        result, stream = self._play(src, 48000, {'time_played': 0})
        self.assertEqual(result['play_mode'], 'full')
        self.assertEqual(result['loops'], 1)
        self.assertFalse(result['partial_segment'])
        self.assertAlmostEqual(result['played_seconds'], 1.0, places=3)
        self.assertEqual(result['play_sample_rate'], 48000)
        played = stream.played[:48000]
        self.assertEqual(played.shape[0], 48000)
        np.testing.assert_allclose(played, src, atol=1e-6)

    def test_truncation_when_file_longer_than_time_played(self):
        src = _ramp(96000, channels=1)             # 2 s @ 48000
        result, stream = self._play(src, 48000, {'time_played': 1})
        self.assertEqual(result['play_mode'], 'truncated')
        self.assertAlmostEqual(result['played_seconds'], 1.0, places=3)
        played = stream.played[:48000]
        self.assertEqual(played.shape[0], 48000)
        np.testing.assert_allclose(played, src[:48000], atol=1e-6)   # first 1 s only

    def test_loop_exact_two_times(self):
        src = _ramp(48000, channels=1)             # 1 s file
        result, stream = self._play(src, 48000, {'time_played': 2})
        self.assertEqual(result['play_mode'], 'looped')
        self.assertEqual(result['loops'], 2)
        self.assertFalse(result['partial_segment'])
        played = stream.played[:96000]
        expected = np.concatenate([src, src], axis=0)
        np.testing.assert_allclose(played, expected, atol=1e-6)

    def test_loop_partial_two_and_a_half_times(self):
        src = _ramp(48000, channels=1)             # 1 s file
        result, stream = self._play(src, 48000, {'time_played': 2.5})
        self.assertEqual(result['play_mode'], 'looped')
        self.assertEqual(result['loops'], 2)
        self.assertTrue(result['partial_segment'])
        target = 120000
        played = stream.played[:target]
        expected = np.concatenate([src, src, src[:24000]], axis=0)
        self.assertEqual(played.shape[0], target)
        np.testing.assert_allclose(played, expected, atol=1e-6)

    def test_forced_sample_rate_changes_play_rate_and_warns(self):
        src = _ramp(48000, channels=1)
        with _LogCapture() as cap:
            result, stream = self._play(src, 48000, {'time_played': 0, 'sample_rate': 44100})
        self.assertEqual(result['file_sample_rate'], 48000)
        self.assertEqual(result['play_sample_rate'], 44100)
        self.assertEqual(stream.samplerate, 44100)
        self.assertTrue(any('pitch' in r.lower() for r in cap.records))

    def test_native_sample_rate_is_read_from_file(self):
        src = _ramp(16000, channels=1)
        result, _stream = self._play(src, 16000, {'time_played': 0, 'sample_rate': 0})
        self.assertEqual(result['file_sample_rate'], 16000)
        self.assertEqual(result['play_sample_rate'], 16000)

    def test_volume_amplify_reports_clipped_samples(self):
        src = np.full((1000, 1), 0.8, dtype=np.float32)   # hot signal
        result, _stream = self._play(src, 48000, {'time_played': 0, 'volume_percent': 200})
        self.assertEqual(result['volume_percent'], 200)
        self.assertEqual(result['clipped_samples'], 1000)   # every sample clips at 0.8*2

    def test_stereo_file_downmixed_on_mono_device(self):
        src = _ramp(2000, channels=2)              # stereo file
        # device_index 4 == "Mono Speaker" (max_output_channels == 1)
        result, stream = self._play(src, 48000, {'time_played': 0, 'device_index': 4})
        self.assertEqual(result['channels'], 1)    # downmixed
        self.assertEqual(stream.channels, 1)
        played = stream.played[:2000]
        expected = np.mean(src, axis=1, keepdims=True)
        np.testing.assert_allclose(played, expected, atol=1e-6)

    def test_missing_audio_file_config_raises(self):
        _install_fakes(data=_ramp(10), samplerate=48000)
        self.addCleanup(_remove_fakes)
        with self.assertRaises(RuntimeError):
            self.mod.play_audio({'audio_file': ''})

    def test_nonexistent_file_raises(self):
        _install_fakes(data=_ramp(10), samplerate=48000)
        self.addCleanup(_remove_fakes)
        with self.assertRaises(RuntimeError):
            self.mod.play_audio({'audio_file': os.path.join(self.tmp.name, 'nope.wav')})

    def test_result_carries_full_input_path(self):
        src = _ramp(100, channels=1)
        result, _stream = self._play(src, 48000, {'time_played': 0})
        self.assertEqual(os.path.normpath(result['input_path']), os.path.normpath(self.path))
        self.assertEqual(result['format'], 'wav')


# ---------------------------------------------------------------------------
# main() end-stage
# ---------------------------------------------------------------------------


class AudioPlayerMainTests(unittest.TestCase):
    def setUp(self):
        self.mod = _load_audioplayer_module()
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = os.path.join(self.tmp.name, 'clip.wav')
        with open(self.path, 'wb') as handle:
            handle.write(b'RIFF....')

    def test_main_plays_emits_section_and_triggers_targets(self):
        mod = self.mod
        _install_fakes(data=_ramp(48000, channels=1), samplerate=48000)
        self.addCleanup(_remove_fakes)
        cfg = {'audio_file': self.path, 'time_played': 0, 'target_agents': ['sleeper_1']}
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
        block = next(r for r in cap.records if 'INI_SECTION_AUDIOPLAYER<<<' in r)
        self.assertIn('status: played', block)

    def test_main_failure_emits_error_section_and_still_triggers_targets(self):
        mod = self.mod
        _install_fakes(data=_ramp(48000, channels=1), samplerate=48000)
        self.addCleanup(_remove_fakes)
        # Nonexistent file -> play_audio raises -> error section + targets still fire.
        cfg = {'audio_file': os.path.join(self.tmp.name, 'gone.wav'),
               'time_played': 5, 'target_agents': ['cleaner_1']}
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
        self.assertEqual(ctx.exception.code, 0)               # always exits 0 after triggering
        self.assertEqual(started, ['cleaner_1'])              # targets fire despite failure
        block = next(r for r in cap.records if 'INI_SECTION_AUDIOPLAYER<<<' in r)
        self.assertIn('status: error', block)

    def test_main_missing_audio_stack_is_reported_not_crashed(self):
        mod = self.mod
        _remove_fakes()
        real_import = builtins.__import__

        def _no_audio(name, *a, **k):
            if name in ('sounddevice', 'soundfile'):
                raise ImportError(f'No module named {name}')
            return real_import(name, *a, **k)

        cfg = {'audio_file': self.path, 'time_played': 0, 'target_agents': []}
        orig_chdir = os.getcwd()
        with _LogCapture() as cap, \
                unittest.mock.patch.object(mod, 'load_config', return_value=cfg), \
                unittest.mock.patch.object(mod, 'write_pid_file'), \
                unittest.mock.patch.object(mod, 'remove_pid_file'), \
                unittest.mock.patch('builtins.__import__', side_effect=_no_audio):
            with self.assertRaises(SystemExit) as ctx:
                mod.main()
        os.chdir(orig_chdir)
        self.assertEqual(ctx.exception.code, 1)
        self.assertTrue(any('soundfile' in r or 'sounddevice' in r for r in cap.records))


# ---------------------------------------------------------------------------
# Registry / integration contracts
# ---------------------------------------------------------------------------


class AudioPlayerRegistryTests(SimpleTestCase):
    def test_wrapped_chat_agent_spec_registered(self):
        from agent.chat_agent_registry import WRAPPED_CHAT_AGENT_SPECS
        spec = next((s for s in WRAPPED_CHAT_AGENT_SPECS
                     if s.tool_name == 'chat_agent_audioplayer'), None)
        self.assertIsNotNone(spec)
        self.assertEqual(spec.key, 'audioplayer')
        self.assertEqual(spec.template_dir, 'audioplayer')
        self.assertEqual(spec.display_name, 'AudioPlayer')

    def test_tools_promote_section_fields(self):
        from agent.tools import _PROMOTE_SECTION_FIELDS_BY_TEMPLATE_DIR
        fields = _PROMOTE_SECTION_FIELDS_BY_TEMPLATE_DIR.get('audioplayer')
        self.assertIsNotNone(fields)
        self.assertIn('input_path', fields)
        self.assertIn('played_seconds', fields)
        self.assertIn('status', fields)

    def test_agent_contract_parametrizer_fields(self):
        from agent.services.agent_contracts import (
            get_agent_contract,
            get_parametrizer_source_fields,
        )
        fields = get_parametrizer_source_fields().get('audioplayer')
        self.assertIsNotNone(fields)
        for expected in ('input_path', 'input_dir', 'filename', 'device_index',
                         'device_name', 'file_sample_rate', 'play_sample_rate',
                         'channels', 'volume_percent', 'played_seconds', 'play_mode',
                         'status', 'response_body'):
            self.assertIn(expected, fields)
        contract = get_agent_contract('audioplayer')
        # Producer: a connection FROM audioplayer writes target_agents.
        self.assertEqual(contract.output_field_by_slot.get(0), 'target_agents')

    def test_config_yaml_defaults(self):
        config_path = os.path.join(_REPO_AGENT_DIR, 'agents', 'audioplayer', 'config.yaml')
        with open(config_path, 'r', encoding='utf-8') as handle:
            cfg = yaml.safe_load(handle)
        self.assertEqual(cfg['audio_file'], '')
        self.assertEqual(cfg['device_index'], -1)
        self.assertEqual(cfg['device_name'], '')
        self.assertEqual(cfg['volume_percent'], 100)
        self.assertEqual(cfg['time_played'], 0)
        self.assertEqual(cfg['sample_rate'], 0)
        self.assertIn('target_agents', cfg)

    def test_captured_in_exec_report(self):
        # Completeness contract (2026-06-07): EVERY agent that runs in Multi-Turn
        # — observational/output ones like AudioPlayer INCLUDED — is captured in
        # the Exec report (auto-resolved from the wrapped chat-agent registry).
        from agent.mcp_agent import _resolve_exec_report_spec
        spec = _resolve_exec_report_spec('chat_agent_audioplayer')
        self.assertIsNotNone(spec)
        self.assertEqual(spec[1], 'AudioPlayer')

    def test_parametrizer_section_type_registered(self):
        param_path = os.path.join(_REPO_AGENT_DIR, 'agents', 'parametrizer', 'parametrizer.py')
        with open(param_path, 'r', encoding='utf-8') as handle:
            text = handle.read()
        self.assertIn("'audioplayer'", text)

    def test_url_route_and_view_present(self):
        with open(os.path.join(_REPO_AGENT_DIR, 'urls.py'), 'r', encoding='utf-8') as handle:
            urls = handle.read()
        self.assertIn('update_audioplayer_connection', urls)
        with open(os.path.join(_REPO_AGENT_DIR, 'views.py'), 'r', encoding='utf-8') as handle:
            views = handle.read()
        self.assertIn('def update_audioplayer_connection_view', views)

    def test_migrations_present(self):
        mig_dir = os.path.join(_REPO_AGENT_DIR, 'migrations')
        self.assertTrue(os.path.exists(os.path.join(mig_dir, '0116_add_audioplayer.py')))
        self.assertTrue(os.path.exists(
            os.path.join(mig_dir, '0117_add_chat_agent_audioplayer_tool.py')))

    def test_css_gradient_present(self):
        css_path = os.path.join(
            _REPO_AGENT_DIR, 'static', 'agent', 'css', 'agentic_control_panel.css')
        with open(css_path, 'r', encoding='utf-8') as handle:
            css = handle.read()
        self.assertIn('.canvas-item.audioplayer-agent', css)

    def test_js_classmap_and_connector_wired(self):
        js_dir = os.path.join(_REPO_AGENT_DIR, 'static', 'agent', 'js')
        with open(os.path.join(js_dir, 'acp-canvas-core.js'), 'r', encoding='utf-8') as handle:
            core = handle.read()
        self.assertIn("'audioplayer': 'audioplayer-agent'", core)
        self.assertIn("=== 'audioplayer') updateAudioPlayerConnection", core)
        with open(os.path.join(js_dir, 'acp-agent-connectors.js'), 'r', encoding='utf-8') as handle:
            conn = handle.read()
        self.assertIn('async function updateAudioPlayerConnection', conn)
        with open(os.path.join(js_dir, 'acp-file-io.js'), 'r', encoding='utf-8') as handle:
            fileio = handle.read()
        self.assertIn("case 'audioplayer':", fileio)

    def test_requirements_pin_soundfile(self):
        req_path = os.path.join(os.path.dirname(os.path.dirname(_REPO_AGENT_DIR)), 'requirements.txt')
        with open(req_path, 'r', encoding='utf-8') as handle:
            reqs = handle.read()
        self.assertIn('soundfile', reqs)


if __name__ == '__main__':
    unittest.main()
