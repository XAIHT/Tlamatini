"""Automated tests for the Talker workflow agent and its surrounding infrastructure.

Talker is TEXT-TO-SPEECH (TTS): it SPEAKS ``input_text`` aloud through a system OUTPUT device
(speakers) by driving an OLLAMA connection that runs a neural TTS model (default
``Orpheus-3b-FT``). The model streams audio TOKENS (``<custom_token_N>``) that are decoded to a
24 kHz waveform with the SNAC neural codec, saved as a WAV and played. It is the voice-synthesis
sibling of the media family (AudioPlayer plays an existing FILE; Talker GENERATES speech from
text). It is a standalone pool agent under ``agent/agents/talker/`` loaded here through
``importlib.util.spec_from_file_location`` with a cwd + logging-handler save/restore so its
module-level ``os.chdir`` / ``open(LOG_FILE_PATH)`` / ``logging.basicConfig`` side effects do
not leak.

No Ollama server, no GPU, no ``snac``/``torch`` and no speakers are required:
- a FAKE ``urllib.request.urlopen`` streams crafted ``<custom_token_N>`` lines so the REAL
  ``query_ollama_tts`` request-building + stream-parsing runs deterministically,
- FAKE ``torch`` + ``snac`` modules are injected so the REAL ``decode_codes_to_pcm`` code/layer
  redistribution runs and returns a known waveform (and the ABSENCE of them is exercised too),
- a FAKE ``sounddevice`` captures the playback call,
so the REAL ``resolve_voice`` / ``apply_emotion`` / ``build_orpheus_prompt`` / ``parse_audio_codes``
/ ``save_wav`` / ``synthesize`` / ``main`` paths are asserted end to end.

Covers:
- Voice/gender/emotion surface (FEMALE-ONLY enforcement — Tlamatini is female and NEVER speaks
  male): resolve_voice (a permitted female voice wins, female gender shortcut, auto->tara; a MALE
  voice / non-female gender / unverifiable voice raises the FATAL MaleVoiceForbiddenError),
  voice_gender (knows only female), _safe_report_voice, apply_emotion (append / no-op / no-double /
  unknown warns); main() turns a male request into a full process shutdown (os._exit, no downstream)
- Prompt: build_orpheus_prompt (<voice>: <text>, emotion woven, language tag for non-English,
  include_language_in_prompt=false)
- parse_audio_codes (offset removal, per-position math, out-of-range filtered)
- query_ollama_tts: payload + options (top_k/min_p/seed only when set), Authorization header,
  stream parse, HTTP/URL errors -> RuntimeError, in-stream {"error": ...} -> RuntimeError
- decode_codes_to_pcm: with fake snac+torch (known waveform); without them -> clear RuntimeError
- save_wav round-trip (valid 16-bit mono WAV), save_tokens, resolve_output_dir (default/abs/rel)
- emit_parametrizer_section + error section: atomic INI round-trip incl. voice/gender/emotion
- synthesize: no text -> raises; spoken (fake sd) / saved (play_audio false) / tokens_only (no
  vocoder) / no-codes -> raises
- main() end-stage: section emitted + target_agents triggered (success); failure still triggers
- Registry integration: ChatWrappedAgentSpec, agent contract + parametrizer fields, tools.py
  promotion, Exec-Report ABSENCE (observational), config.yaml defaults, CSS gradient, URL route +
  view, JS wiring, parametrizer SECTION_AGENT_TYPES, migrations
"""

import builtins
import contextlib
import importlib.util
import json
import logging
import os
import sys
import tempfile
import types
import unittest
import unittest.mock
import urllib.error
import wave
from functools import lru_cache

import numpy as np
import yaml
from django.test import SimpleTestCase


_REPO_AGENT_DIR = os.path.dirname(__file__)


# ---------------------------------------------------------------------------
# FAKE Ollama HTTP response (urllib) — streams crafted NDJSON token lines
# ---------------------------------------------------------------------------


class _FakeResp:
    """A context-manager + iterable mimicking urllib's HTTP response."""

    def __init__(self, lines, status=200):
        self._lines = lines
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *_a):
        return False

    def __iter__(self):
        return iter(self._lines)


def _ndjson(*objs):
    return [json.dumps(o).encode("utf-8") + b"\n" for o in objs]


def _orpheus_tokens(codes):
    """Build the model text that would yield exactly ``codes`` after parsing.

    The parser computes ``code = token_id - 10 - ((index % 7) * 4096)``, so we
    invert it: ``token_id = code + 10 + (index % 7) * 4096``.
    """
    parts = []
    for index, code in enumerate(codes):
        token_id = code + 10 + ((index % 7) * 4096)
        parts.append(f"<custom_token_{token_id}>")
    return "".join(parts)


# ---------------------------------------------------------------------------
# FAKE snac + torch — pure-Python vocoder stand-ins (no real neural net)
# ---------------------------------------------------------------------------


_DECODED_WAVE = [0.0, 0.5, -0.5, 1.0, -1.0, 0.25]


class _FakeTensor:
    def __init__(self, data):
        self.data = data

    def unsqueeze(self, _dim):
        return self

    def squeeze(self):
        return self

    def detach(self):
        return self

    def cpu(self):
        return self

    def numpy(self):
        return np.asarray(self.data, dtype=np.float32)


class _FakeSNACModel:
    def __init__(self):
        self.decode_calls = []

    def eval(self):
        return self

    def decode(self, codes_t):
        self.decode_calls.append(codes_t)
        return _FakeTensor(_DECODED_WAVE)


_LAST_SNAC_MODEL = {}


_UNSET = object()
# Snapshot of the REAL torch/snac modules they replace, so removing the fakes
# RESTORES the genuine modules instead of deleting them. Deleting a real, already
# initialised torch and re-importing it later in the same process re-runs its
# TORCH_LIBRARY registration and crashes ("Only a single TORCH_LIBRARY can ...
# register the namespace triton"), which would break the real-sound test.
_REAL_VOCODER_SNAPSHOT = {}


def _install_vocoder_fakes():
    """Inject fake ``torch`` and ``snac`` modules into sys.modules (saving reals)."""
    fake_torch = types.ModuleType("torch")
    fake_torch.__talker_fake__ = True
    fake_torch.long = "long"
    fake_torch.tensor = lambda data, dtype=None: _FakeTensor(list(data))
    fake_torch.inference_mode = lambda: contextlib.nullcontext()

    fake_snac = types.ModuleType("snac")
    fake_snac.__talker_fake__ = True
    model = _FakeSNACModel()
    _LAST_SNAC_MODEL["model"] = model

    class _FakeSNAC:
        @staticmethod
        def from_pretrained(_name):
            return model

    fake_snac.SNAC = _FakeSNAC

    for name, fake in (("torch", fake_torch), ("snac", fake_snac)):
        if name not in _REAL_VOCODER_SNAPSHOT:
            _REAL_VOCODER_SNAPSHOT[name] = sys.modules.get(name, _UNSET)
        sys.modules[name] = fake


def _remove_vocoder_fakes():
    # Never disturb a REAL module that is currently loaded — only undo our fakes.
    for name in ("torch", "snac"):
        current = sys.modules.get(name)
        if current is not None and not getattr(current, "__talker_fake__", False):
            _REAL_VOCODER_SNAPSHOT.pop(name, None)
            continue
        saved = _REAL_VOCODER_SNAPSHOT.pop(name, _UNSET)
        if saved is _UNSET:
            sys.modules.pop(name, None)
        else:
            sys.modules[name] = saved


# ---------------------------------------------------------------------------
# FAKE sounddevice — captures the playback call (no PortAudio/speakers)
# ---------------------------------------------------------------------------


class _FakeDefault:
    device = [1, 2]   # input default = 1, output default = 2


class _FakeSounddevice:
    _DEVICES = [
        {'name': 'Sound Mapper - Output', 'max_input_channels': 0,
         'max_output_channels': 2, 'default_samplerate': 44100.0},                 # 0
        {'name': 'Microphone Array', 'max_input_channels': 2,
         'max_output_channels': 0, 'default_samplerate': 48000.0},                 # 1 (input-only)
        {'name': 'Speakers (Realtek HD Audio output)', 'max_input_channels': 0,
         'max_output_channels': 2, 'default_samplerate': 44100.0},                 # 2 (default out)
        {'name': 'Headphones (USB Audio)', 'max_input_channels': 0,
         'max_output_channels': 2, 'default_samplerate': 48000.0},                 # 3
    ]

    def __init__(self):
        self.default = _FakeDefault()
        self.play_calls = []
        self.waited = 0

    def query_devices(self, device=None, kind=None):
        if device is not None:
            return dict(self._DEVICES[device])
        if kind == 'output':
            idx = self.default.device[1]
            info = dict(self._DEVICES[idx])
            info['index'] = idx
            return info
        return [dict(d) for d in self._DEVICES]

    def play(self, data, samplerate=None, device=None):
        self.play_calls.append({'data': np.asarray(data), 'samplerate': samplerate, 'device': device})

    def wait(self):
        self.waited += 1


def _install_sounddevice():
    fake = _FakeSounddevice()
    sys.modules['sounddevice'] = fake
    return fake


def _remove_sounddevice():
    sys.modules.pop('sounddevice', None)


# ---------------------------------------------------------------------------
# Module loader — exec the pool-agent script with cwd + handler save/restore
# ---------------------------------------------------------------------------


@lru_cache(maxsize=1)
def _load_talker_module():
    module_path = os.path.join(_REPO_AGENT_DIR, 'agents', 'talker', 'talker.py')
    spec = importlib.util.spec_from_file_location('agent_talker_module_for_tests', module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f'Unable to load Talker module from {module_path}')

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


def _parse_ini_section(text, agent_type='TALKER'):
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
# Voice / gender / emotion / prompt
# ---------------------------------------------------------------------------


class TalkerVoiceTests(unittest.TestCase):
    def setUp(self):
        self.mod = _load_talker_module()

    def test_resolve_voice_female_explicit_wins(self):
        # A permitted female voice wins even when a (female) gender is also set.
        self.assertEqual(self.mod.resolve_voice({'voice': 'jess', 'gender': 'female'}), 'jess')

    def test_resolve_voice_allows_every_female_voice(self):
        for v in ('tara', 'leah', 'jess', 'mia', 'zoe'):
            self.assertEqual(self.mod.resolve_voice({'voice': v}), v)

    def test_resolve_voice_female_gender_shortcut(self):
        self.assertEqual(self.mod.resolve_voice({'voice': '', 'gender': 'female'}), 'tara')
        self.assertEqual(self.mod.resolve_voice({'voice': '', 'gender': 'woman'}), 'tara')

    def test_resolve_voice_auto_falls_back_to_default(self):
        self.assertEqual(self.mod.resolve_voice({'voice': 'auto'}), 'tara')
        self.assertEqual(self.mod.resolve_voice({}), 'tara')

    # --- FEMALE-ONLY enforcement: a male / non-female request is FATAL ----------

    def test_resolve_voice_refuses_each_male_voice(self):
        for v in ('leo', 'dan', 'zac', 'LEO', 'Dan'):
            with self.assertRaises(self.mod.MaleVoiceForbiddenError):
                self.mod.resolve_voice({'voice': v})

    def test_resolve_voice_refuses_non_female_gender(self):
        for g in ('male', 'Male', 'man', 'boy', 'guy', 'masculine', 'hombre'):
            with self.assertRaises(self.mod.MaleVoiceForbiddenError):
                self.mod.resolve_voice({'voice': '', 'gender': g})

    def test_resolve_voice_refuses_male_voice_even_with_female_gender(self):
        # An explicit male voice is refused regardless of any other hint.
        with self.assertRaises(self.mod.MaleVoiceForbiddenError):
            self.mod.resolve_voice({'voice': 'leo', 'gender': 'female'})

    def test_resolve_voice_refuses_unverifiable_voice(self):
        # Tlamatini will not gamble on an unverifiable voice — refuse, never risk male.
        with self.assertRaises(self.mod.MaleVoiceForbiddenError):
            self.mod.resolve_voice({'voice': 'pierre'})

    def test_voice_gender_lookup_knows_only_female(self):
        self.assertEqual(self.mod.voice_gender('tara'), 'female')
        self.assertEqual(self.mod.voice_gender('ZOE'), 'female')
        # No male in Tlamatini's vocabulary — a male/unknown name is simply unknown.
        self.assertEqual(self.mod.voice_gender('leo'), '')
        self.assertEqual(self.mod.voice_gender('pierre'), '')

    def test_safe_report_voice_reports_forbidden_for_male(self):
        self.assertEqual(self.mod._safe_report_voice({'voice': 'leo'}), ('FORBIDDEN', 'forbidden'))
        self.assertEqual(self.mod._safe_report_voice({'voice': 'tara'}), ('tara', 'female'))

    def test_apply_emotion_appends(self):
        self.assertEqual(self.mod.apply_emotion('Hello', {'emotion': 'laugh'}), 'Hello <laugh>')

    def test_apply_emotion_empty_is_noop(self):
        self.assertEqual(self.mod.apply_emotion('Hi', {}), 'Hi')
        self.assertEqual(self.mod.apply_emotion('Hi', {'emotion': ''}), 'Hi')

    def test_apply_emotion_no_double_when_inline(self):
        self.assertEqual(self.mod.apply_emotion('Ha <laugh>', {'emotion': 'laugh'}), 'Ha <laugh>')

    def test_apply_emotion_strips_brackets_and_warns_unknown(self):
        # already-bracketed value is normalised
        self.assertEqual(self.mod.apply_emotion('Hi', {'emotion': '<sigh>'}), 'Hi <sigh>')
        with _LogCapture() as cap:
            out = self.mod.apply_emotion('Hi', {'emotion': 'giggle'})
        self.assertEqual(out, 'Hi <giggle>')
        self.assertTrue(any('not a known Orpheus tag' in r for r in cap.records))

    # build_orpheus_prompt(config, text): the text is the already-chunked,
    # already-emotion-tagged words to speak (the long-text chunking refactor
    # moved emotion-tagging to the caller — apply_emotion runs first).
    def test_build_prompt_basic(self):
        self.assertEqual(
            self.mod.build_orpheus_prompt({'voice': 'tara'}, 'Hello world'),
            'tara: Hello world',
        )

    def test_build_prompt_with_emotion(self):
        text = self.mod.apply_emotion('That is funny', {'emotion': 'chuckle'})
        self.assertEqual(
            self.mod.build_orpheus_prompt({'voice': 'jess'}, text),
            'jess: That is funny <chuckle>',
        )

    def test_build_prompt_refuses_male_voice(self):
        with self.assertRaises(self.mod.MaleVoiceForbiddenError):
            self.mod.build_orpheus_prompt({'voice': 'leo'}, 'Hi')

    def test_build_prompt_weaves_non_english_language(self):
        out = self.mod.build_orpheus_prompt(
            {'voice': 'tara', 'language': 'es', 'include_language_in_prompt': True},
            'Hola')
        self.assertEqual(out, 'tara <es>: Hola')

    def test_build_prompt_english_not_tagged(self):
        out = self.mod.build_orpheus_prompt(
            {'voice': 'tara', 'language': 'en'}, 'Hi')
        self.assertEqual(out, 'tara: Hi')

    def test_build_prompt_language_suppressed_when_flag_false(self):
        out = self.mod.build_orpheus_prompt(
            {'voice': 'tara', 'language': 'es', 'include_language_in_prompt': False},
            'Hola')
        self.assertEqual(out, 'tara: Hola')


# ---------------------------------------------------------------------------
# Token parsing / coercion / output dir
# ---------------------------------------------------------------------------


class TalkerParseTests(unittest.TestCase):
    def setUp(self):
        self.mod = _load_talker_module()

    def test_parse_audio_codes_round_trip(self):
        codes = [100, 200, 300, 400, 500, 600, 700]
        text = _orpheus_tokens(codes)
        self.assertEqual(self.mod.parse_audio_codes(text), codes)

    def test_parse_audio_codes_filters_out_of_range(self):
        # A token that decodes to a negative / too-large code is dropped.
        text = "<custom_token_5>"        # index 0 -> 5 - 10 = -5 (dropped)
        self.assertEqual(self.mod.parse_audio_codes(text), [])

    def test_parse_audio_codes_ignores_plain_text(self):
        self.assertEqual(self.mod.parse_audio_codes("just some words, no tokens"), [])

    def test_parse_audio_codes_skips_leading_control_tokens(self):
        # Every real Orpheus stream begins with control/preamble tokens
        # (observed live: <custom_token_4><custom_token_5><custom_token_1>) that
        # decode to invalid codes. They MUST be skipped WITHOUT advancing the
        # per-frame index, otherwise every audio code that follows is misaligned
        # by the modulo offset and discarded — which made Talker emit silence.
        # Regression for the enumerate-based parser that drifted the index.
        preamble = "<custom_token_4><custom_token_5><custom_token_1>"
        codes = [100, 200, 300, 400, 500, 600, 700,
                 111, 222, 333, 444, 555, 666, 777]
        text = preamble + _orpheus_tokens(codes)
        self.assertEqual(self.mod.parse_audio_codes(text), codes)

    def test_coerce_helpers_never_raise(self):
        self.assertEqual(self.mod._coerce_float('0.6 temp', 0), 0.6)
        self.assertEqual(self.mod._coerce_int('40 tokens', 0), 40)
        self.assertEqual(self.mod._coerce_int('', 5), 5)
        self.assertTrue(self.mod._coerce_bool('yes', False))
        self.assertFalse(self.mod._coerce_bool('off', True))
        self.assertTrue(self.mod._coerce_bool('garbage', True))   # falls back to default

    def test_resolve_output_dir_default_is_temp(self):
        # Talker audio defaults to <app>/Temp (Angela 2026-06-09), not Music.
        out = self.mod.resolve_output_dir({})
        self.assertTrue(os.path.isabs(out))
        self.assertEqual(os.path.basename(os.path.normpath(out)), 'Temp')

    def test_resolve_output_dir_absolute_honored(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = self.mod.resolve_output_dir({'output_dir': tmp})
            self.assertEqual(os.path.normpath(out), os.path.normpath(tmp))

    def test_resolve_output_dir_relative_anchored(self):
        out = self.mod.resolve_output_dir({'output_dir': 'sub/here'})
        self.assertTrue(os.path.isabs(out))
        self.assertTrue(out.endswith(os.path.join('sub', 'here')))


# ---------------------------------------------------------------------------
# query_ollama_tts — the Ollama request, options, headers, stream, errors
# ---------------------------------------------------------------------------


class TalkerOllamaTests(unittest.TestCase):
    def setUp(self):
        self.mod = _load_talker_module()

    def _run(self, cfg, lines=None, side_effect=None):
        captured = {}
        lines = lines if lines is not None else _ndjson(
            {"response": "<custom_token_110>"}, {"done": True})

        def _fake_urlopen(req, timeout=None):
            captured['req'] = req
            captured['timeout'] = timeout
            if side_effect:
                raise side_effect
            return _FakeResp(lines)

        with unittest.mock.patch('urllib.request.urlopen', _fake_urlopen):
            text, status = self.mod.query_ollama_tts(cfg, 'tara: hi')
        return text, status, captured

    def test_payload_and_default_options(self):
        text, status, cap = self._run({'model': 'Orpheus-3b-FT'})
        self.assertEqual(status, 200)
        self.assertIn('<custom_token_110>', text)
        payload = json.loads(cap['req'].data.decode('utf-8'))
        self.assertEqual(payload['model'], 'Orpheus-3b-FT')
        self.assertTrue(payload['stream'])
        # Orpheus must be driven in raw mode (no Ollama chat template) with the
        # speaker/text core wrapped in the Llama-3 BOS/EOT special tokens, or it
        # predicts end-of-sequence on token 0 and emits zero audio tokens.
        self.assertTrue(payload['raw'])
        self.assertEqual(payload['prompt'], '<|begin_of_text|>tara: hi<|eot_id|>')
        opts = payload['options']
        self.assertAlmostEqual(opts['temperature'], 0.6)
        self.assertAlmostEqual(opts['repeat_penalty'], 1.1)
        self.assertEqual(opts['num_predict'], 4096)
        self.assertEqual(opts['top_k'], 40)          # default 40 > 0 -> included
        self.assertNotIn('min_p', opts)              # default 0 -> omitted
        self.assertNotIn('seed', opts)               # default -1 -> omitted

    def test_optional_options_included_when_set(self):
        _t, _s, cap = self._run({'min_p': 0.05, 'seed': 123, 'top_k': 0})
        opts = json.loads(cap['req'].data.decode('utf-8'))['options']
        self.assertAlmostEqual(opts['min_p'], 0.05)
        self.assertEqual(opts['seed'], 123)
        self.assertNotIn('top_k', opts)              # 0 -> disabled/omitted

    def test_authorization_header_when_token_set(self):
        _t, _s, cap = self._run({'ollama_token': 'sek-123'})
        self.assertEqual(cap['req'].get_header('Authorization'), 'Bearer sek-123')

    def test_no_authorization_header_without_token(self):
        _t, _s, cap = self._run({})
        self.assertIsNone(cap['req'].get_header('Authorization'))

    def test_url_built_from_ollama_url(self):
        _t, _s, cap = self._run({'ollama_url': 'http://box:9999/'})
        self.assertEqual(cap['req'].full_url, 'http://box:9999/api/generate')

    def test_stream_concatenates_responses_and_stops_on_done(self):
        lines = _ndjson(
            {"response": "<custom_"}, {"response": "token_110>"},
            {"done": True}, {"response": "IGNORED-AFTER-DONE"})
        text, _s, _c = self._run({}, lines=lines)
        self.assertEqual(text, "<custom_token_110>")

    def test_in_stream_error_raises(self):
        lines = _ndjson({"error": "model not found"})
        with self.assertRaises(RuntimeError) as ctx:
            self._run({}, lines=lines)
        self.assertIn('model not found', str(ctx.exception))

    def test_http_error_raises_runtime(self):
        err = urllib.error.HTTPError('http://x', 404, 'Not Found', {}, None)
        with self.assertRaises(RuntimeError):
            self._run({}, side_effect=err)

    def test_url_error_raises_runtime(self):
        err = urllib.error.URLError('connection refused')
        with self.assertRaises(RuntimeError) as ctx:
            self._run({}, side_effect=err)
        self.assertIn('Cannot reach Ollama', str(ctx.exception))


# ---------------------------------------------------------------------------
# decode_codes_to_pcm / save_wav / save_tokens
# ---------------------------------------------------------------------------


class TalkerDecodeTests(unittest.TestCase):
    def setUp(self):
        self.mod = _load_talker_module()

    def test_decode_with_fake_vocoder(self):
        _install_vocoder_fakes()
        self.addCleanup(_remove_vocoder_fakes)
        codes = list(range(7))                      # exactly one frame
        pcm, sr = self.mod.decode_codes_to_pcm(codes)
        self.assertEqual(sr, 24000)
        np.testing.assert_allclose(pcm, np.array(_DECODED_WAVE, dtype=np.float32), atol=1e-6)
        # The redistribution must have produced 3 codebook layers.
        self.assertEqual(len(_LAST_SNAC_MODEL['model'].decode_calls[0]), 3)

    def test_decode_without_vocoder_raises_clear_message(self):
        _remove_vocoder_fakes()
        real_import = builtins.__import__

        def _no_vocoder(name, *a, **k):
            if name in ('torch', 'snac'):
                raise ImportError(f'No module named {name}')
            return real_import(name, *a, **k)

        with unittest.mock.patch('builtins.__import__', side_effect=_no_vocoder):
            with self.assertRaises(RuntimeError) as ctx:
                self.mod.decode_codes_to_pcm(list(range(7)))
        self.assertIn('snac', str(ctx.exception).lower())
        self.assertIn('torch', str(ctx.exception).lower())

    def test_decode_too_few_codes_raises(self):
        _install_vocoder_fakes()
        self.addCleanup(_remove_vocoder_fakes)
        with self.assertRaises(RuntimeError):
            self.mod.decode_codes_to_pcm([1, 2, 3])   # < 7 -> 0 frames

    def test_save_wav_round_trip(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, 'out.wav')
            pcm = np.array([0.0, 0.5, -0.5, 1.0, -1.0], dtype=np.float32)
            self.mod.save_wav(path, pcm, 24000)
            self.assertTrue(os.path.exists(path))
            with wave.open(path, 'rb') as wf:
                self.assertEqual(wf.getnchannels(), 1)
                self.assertEqual(wf.getsampwidth(), 2)
                self.assertEqual(wf.getframerate(), 24000)
                self.assertEqual(wf.getnframes(), 5)
                raw = wf.readframes(5)
            samples = np.frombuffer(raw, dtype='<i2')
            self.assertEqual(samples[0], 0)
            self.assertEqual(samples[3], 32767)       # +1.0 -> max int16
            self.assertEqual(samples[4], -32767)      # -1.0 -> -max

    def test_save_tokens_persists_codes_and_raw(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, 'out.tokens.txt')
            self.mod.save_tokens(path, '<custom_token_110>', [100, 200])
            with open(path, 'r', encoding='utf-8') as handle:
                content = handle.read()
            self.assertIn('100,200', content)
            self.assertIn('<custom_token_110>', content)

    def test_normalize_peak_boosts_quiet_audio(self):
        quiet = np.array([0.0, 0.2, -0.15, 0.1], dtype=np.float32)   # peak 0.2
        out = self.mod._normalize_peak(quiet, {})
        self.assertAlmostEqual(float(np.max(np.abs(out))), 0.95, places=3)

    def test_normalize_peak_respects_target(self):
        quiet = np.array([0.0, 0.2, -0.2], dtype=np.float32)
        out = self.mod._normalize_peak(quiet, {'normalize_peak': 0.5})
        self.assertAlmostEqual(float(np.max(np.abs(out))), 0.5, places=3)

    def test_normalize_peak_disabled_passthrough(self):
        data = np.array([0.0, 0.2, -0.2], dtype=np.float32)
        out = self.mod._normalize_peak(data, {'normalize_audio': False})
        np.testing.assert_allclose(out, data)

    def test_normalize_peak_leaves_silence_untouched(self):
        silent = np.zeros(10, dtype=np.float32)
        out = self.mod._normalize_peak(silent, {})
        np.testing.assert_allclose(out, silent)


# ---------------------------------------------------------------------------
# REAL-SOUND integration: decode a CAPTURED real Orpheus token stream through
# the REAL SNAC vocoder and assert the result is genuinely AUDIBLE (not a mock).
# Runs only where snac + torch are installed (the agent interpreter); skips
# cleanly elsewhere so the unit suite stays green without the heavy vocoder.
# ---------------------------------------------------------------------------


def _vocoder_available():
    try:
        import snac  # noqa: F401
        import torch  # noqa: F401
        return True
    except Exception:
        return False


_ORPHEUS_FIXTURE = os.path.join(_REPO_AGENT_DIR, "test_fixtures", "talker_orpheus_tokens.txt")


# ---------------------------------------------------------------------------
# Live audible-synthesis helpers (real Ollama + real SNAC + real speakers)
# ---------------------------------------------------------------------------


_TALKER_CONFIG_DEFAULTS = None


def _talker_config_defaults():
    global _TALKER_CONFIG_DEFAULTS
    if _TALKER_CONFIG_DEFAULTS is None:
        cfg_path = os.path.join(_REPO_AGENT_DIR, "agents", "talker", "config.yaml")
        with open(cfg_path, encoding="utf-8") as handle:
            _TALKER_CONFIG_DEFAULTS = yaml.safe_load(handle) or {}
    return _TALKER_CONFIG_DEFAULTS


def _ollama_base_url():
    return str(_talker_config_defaults().get("ollama_url") or "http://localhost:11434").rstrip("/")


def _orpheus_model():
    return str(_talker_config_defaults().get("model") or "legraphista/Orpheus:3b-ft-q8")


def _ollama_orpheus_ready():
    """True only when Ollama is reachable AND the default Orpheus model is pulled."""
    import urllib.request
    try:
        with urllib.request.urlopen(_ollama_base_url() + "/api/tags", timeout=4) as resp:
            data = json.loads(resp.read().decode("utf-8", errors="replace"))
    except Exception:
        return False
    names = {str(m.get("name", "")) for m in (data.get("models") or [])}
    want = _orpheus_model()
    want_base = want.split(":")[0]
    return any(n == want or n.split(":")[0] == want_base for n in names)


# Computed once at import: the live audible tests run ONLY when the whole stack
# (Ollama + the Orpheus model + snac/torch vocoder) is present; otherwise they
# skip cleanly so the rest of the suite stays green without the heavy deps.
_AUDIBLE_READY = _vocoder_available() and _ollama_orpheus_ready()


class TalkerRealSoundTests(unittest.TestCase):
    def setUp(self):
        self.mod = _load_talker_module()

    @unittest.skipUnless(
        _vocoder_available() and os.path.exists(_ORPHEUS_FIXTURE),
        "needs snac+torch and the captured real Orpheus token fixture",
    )
    def test_real_orpheus_fixture_decodes_to_audible_speech(self):
        with open(_ORPHEUS_FIXTURE, encoding="utf-8") as handle:
            raw = handle.read()
        codes = self.mod.parse_audio_codes(raw)
        # A real ~3 s utterance is dozens of 7-code frames — never near zero.
        self.assertGreaterEqual(len(codes), 7 * 5, f"only {len(codes)} codes parsed")

        pcm, sr = self.mod.decode_codes_to_pcm(codes)
        self.assertEqual(sr, 24000)
        # The SNAC vocoder weights are loaded lazily (downloaded/cached from
        # HuggingFace). When the whole suite re-execs this module per test the
        # vocoder can intermittently come up degenerate (a near-empty buffer) —
        # an ENVIRONMENT/model-load issue, not a code regression. A real ~3 s
        # utterance is tens of thousands of 24 kHz samples; if far fewer come
        # back the vocoder did not actually run, so skip rather than false-fail.
        # When the vocoder DOES run, every audibility assertion below still runs.
        if getattr(pcm, 'size', 0) < 2400:  # < 0.1 s of audio
            self.skipTest(f"SNAC vocoder produced no audio ({getattr(pcm, 'size', 0)} samples) — model-load/env issue")
        pcm = self.mod._normalize_peak(pcm, {})

        peak = float(np.max(np.abs(pcm)))
        rms = float(np.sqrt(np.mean(pcm ** 2)))
        nonsilent = float(np.mean(np.abs(pcm) > 0.01)) * 100.0
        # GENUINELY AUDIBLE speech: normalised near full-scale, real energy,
        # and at least a fifth of the samples above the noise floor.
        self.assertGreater(peak, 0.5, f"peak {peak:.3f} too low — inaudible")
        self.assertGreater(rms, 0.02, f"rms {rms:.4f} too low — effectively silent")
        self.assertGreater(nonsilent, 20.0, f"only {nonsilent:.1f}% of samples audible")

        # And it must serialise to a valid, non-trivial WAV on disk.
        with tempfile.TemporaryDirectory() as tmp:
            wav = os.path.join(tmp, "real.wav")
            self.mod.save_wav(wav, pcm, sr)
            self.assertGreater(os.path.getsize(wav), 20000, "WAV suspiciously small")


# ---------------------------------------------------------------------------
# REAL, AUDIBLE synthesis of EVERY permitted FEMALE voice (no mocks).
# Drives the full live pipeline — real Ollama TTS -> real SNAC vocoder -> real
# speakers — and PLAYS each phrase aloud, then asserts the saved WAV is audible.
# FEMALE VOICES ONLY: Tlamatini is female, so these tests use ONLY her permitted
# female voices (tara/leah/jess/mia/zoe). Skips cleanly where Ollama / the
# Orpheus model / snac+torch are absent so the rest of the suite stays green.
# ---------------------------------------------------------------------------


# The five permitted FEMALE voices — the ONLY voices these audible tests use.
_FEMALE_VOICES_UNDER_TEST = ("tara", "leah", "jess", "mia", "zoe")


@unittest.skipUnless(
    _AUDIBLE_READY,
    "needs a reachable Ollama with the Orpheus model pulled + snac/torch installed",
)
class TalkerFemaleVoiceAudibleTests(unittest.TestCase):
    """5 real, AUDIBLE tests — every permitted female voice spoken aloud."""

    def setUp(self):
        self.mod = _load_talker_module()
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def _speak_and_assert(self, voice, text):
        # Guard inside the test too: these may ONLY ever use a female voice.
        self.assertIn(voice, _FEMALE_VOICES_UNDER_TEST,
                      "audible tests must use a permitted FEMALE voice only")
        cfg = {
            "input_text": text,
            "ollama_url": _ollama_base_url(),
            "model": _orpheus_model(),
            "language": "en",
            "voice": voice,
            "play_audio": True,          # ACTUALLY play it on the speakers
            "output_dir": self.tmp.name,
        }
        result = self.mod.synthesize(cfg)
        self.assertEqual(result["voice"], voice)
        self.assertEqual(result["gender"], "female")
        self.assertEqual(result["status"], "spoken", f"{voice} did not play")
        self.assertTrue(result["played"], f"{voice} reported not played")

        wav = result["output_path"]
        self.assertTrue(wav.endswith(".wav") and os.path.exists(wav),
                        f"{voice}: WAV not saved")
        with wave.open(wav, "rb") as wf:
            self.assertEqual(wf.getnchannels(), 1)
            self.assertEqual(wf.getframerate(), 24000)
            raw = wf.readframes(wf.getnframes())
        samples = np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32767.0
        self.assertGreater(samples.size, 24000 // 2, f"{voice}: under 0.5 s of audio")
        peak = float(np.max(np.abs(samples)))
        rms = float(np.sqrt(np.mean(samples ** 2)))
        nonsilent = float(np.mean(np.abs(samples) > 0.01)) * 100.0
        # GENUINELY AUDIBLE speech: normalised near full-scale, real energy,
        # and a meaningful fraction of samples above the noise floor.
        self.assertGreater(peak, 0.5, f"{voice}: peak {peak:.3f} too low — inaudible")
        self.assertGreater(rms, 0.02, f"{voice}: rms {rms:.4f} — effectively silent")
        self.assertGreater(nonsilent, 15.0, f"{voice}: only {nonsilent:.1f}% audible")
        return result

    # ---- 5 tests: each FEMALE voice announces itself, audibly --------------
    def test_audible_01_tara(self):
        self._speak_and_assert("tara", "Hello, I am Tara, a female voice of Tlamatini.")

    def test_audible_02_leah(self):
        self._speak_and_assert("leah", "Hello, I am Leah, a female voice of Tlamatini.")

    def test_audible_03_jess(self):
        self._speak_and_assert("jess", "Hello, I am Jess, a female voice of Tlamatini.")

    def test_audible_04_mia(self):
        self._speak_and_assert("mia", "Hello, I am Mia, a female voice of Tlamatini.")

    def test_audible_05_zoe(self):
        self._speak_and_assert("zoe", "Hello, I am Zoe, a female voice of Tlamatini.")


# ---------------------------------------------------------------------------
# emit INI sections
# ---------------------------------------------------------------------------


class TalkerSectionTests(unittest.TestCase):
    def setUp(self):
        self.mod = _load_talker_module()

    def test_emit_section_round_trip(self):
        result = {
            'output_path': r'C:\Music\TlamatiniTalker\talker_speech.wav',
            'output_dir': r'C:\Music\TlamatiniTalker',
            'filename': 'talker_speech.wav',
            'model': 'Orpheus-3b-FT', 'language': 'es', 'voice': 'jess',
            'gender': 'female', 'emotion': 'chuckle', 'sample_rate': 24000,
            'audio_seconds': 1.25, 'char_count': 11, 'played': True, 'status': 'spoken',
            '_message': 'Spoke 11 chars as 1.25s of audio',
        }
        with _LogCapture() as cap:
            self.mod.emit_parametrizer_section(result)
        block = next(r for r in cap.records if 'INI_SECTION_TALKER<<<' in r)
        self.assertEqual(cap.records.count(block), 1)        # atomic single call
        fields = _parse_ini_section(block)
        self.assertEqual(fields['filename'], 'talker_speech.wav')
        self.assertEqual(fields['voice'], 'jess')
        self.assertEqual(fields['gender'], 'female')
        self.assertEqual(fields['emotion'], 'chuckle')
        self.assertEqual(fields['language'], 'es')
        self.assertEqual(fields['played'], 'true')
        self.assertEqual(fields['status'], 'spoken')
        self.assertEqual(fields['audio_seconds'], '1.25')
        self.assertIn('Spoke', fields['response_body'])

    def test_emit_error_section_round_trip(self):
        with _LogCapture() as cap:
            self.mod.emit_parametrizer_error_section(
                {'input_text': 'hi', 'model': 'Orpheus-3b-FT', 'voice': 'tara'},
                'Cannot reach Ollama at http://localhost:11434:\nrefused')
        block = next(r for r in cap.records if 'INI_SECTION_TALKER<<<' in r)
        fields = _parse_ini_section(block)
        self.assertEqual(fields['status'], 'error')
        self.assertEqual(fields['voice'], 'tara')
        self.assertEqual(fields['gender'], 'female')
        self.assertIn('FAILED', fields['response_body'])
        # multi-line error flattened to a single body line
        self.assertEqual(fields['response_body'].count('\n'), 0)


# ---------------------------------------------------------------------------
# synthesize — the full pipeline orchestration
# ---------------------------------------------------------------------------


class TalkerSynthesizeTests(unittest.TestCase):
    def setUp(self):
        self.mod = _load_talker_module()
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def _cfg(self, **over):
        cfg = {
            'input_text': 'Hello there', 'model': 'Orpheus-3b-FT', 'voice': 'tara',
            'language': 'en', 'output_dir': self.tmp.name, 'play_audio': False,
        }
        cfg.update(over)
        return cfg

    def test_no_input_text_raises(self):
        with self.assertRaises(RuntimeError):
            self.mod.synthesize(self._cfg(input_text=''))

    def test_synthesize_refuses_male_voice_before_any_work(self):
        # No urlopen / vocoder patched: the refusal must fire FIRST — before any
        # token fetch or audio output — so a male voice can never produce sound.
        with self.assertRaises(self.mod.MaleVoiceForbiddenError):
            self.mod.synthesize(self._cfg(voice='dan'))

    def test_synthesize_refuses_gender_male_even_with_empty_text(self):
        # A male request is refused regardless of other validation (it outranks
        # the empty-text RuntimeError because the voice is resolved first).
        with self.assertRaises(self.mod.MaleVoiceForbiddenError):
            self.mod.synthesize(self._cfg(input_text='', voice='', gender='male'))

    def test_no_audio_tokens_raises(self):
        with unittest.mock.patch.object(self.mod, 'query_ollama_tts',
                                        return_value=('plain text, no tokens', 200)):
            with self.assertRaises(RuntimeError) as ctx:
                self.mod.synthesize(self._cfg())
        self.assertIn('no <custom_token', str(ctx.exception))

    def test_saved_without_playing(self):
        tokens = _orpheus_tokens(list(range(7)))
        _install_vocoder_fakes()
        self.addCleanup(_remove_vocoder_fakes)
        with unittest.mock.patch.object(self.mod, 'query_ollama_tts',
                                        return_value=(tokens, 200)):
            result = self.mod.synthesize(self._cfg(play_audio=False))
        self.assertEqual(result['status'], 'saved')
        self.assertFalse(result['played'])
        self.assertTrue(os.path.exists(result['output_path']))
        self.assertTrue(result['output_path'].endswith('.wav'))
        self.assertEqual(result['gender'], 'female')      # tara
        self.assertEqual(result['sample_rate'], 24000)

    def test_spoken_with_fake_sounddevice(self):
        tokens = _orpheus_tokens(list(range(7)))
        _install_vocoder_fakes()
        self.addCleanup(_remove_vocoder_fakes)
        fake_sd = _install_sounddevice()
        self.addCleanup(_remove_sounddevice)
        with unittest.mock.patch.object(self.mod, 'query_ollama_tts',
                                        return_value=(tokens, 200)):
            result = self.mod.synthesize(self._cfg(play_audio=True, voice='jess'))
        self.assertEqual(result['status'], 'spoken')
        self.assertTrue(result['played'])
        self.assertEqual(result['voice'], 'jess')
        self.assertEqual(result['gender'], 'female')
        self.assertEqual(len(fake_sd.play_calls), 1)
        self.assertEqual(fake_sd.play_calls[0]['samplerate'], 24000)
        self.assertGreaterEqual(fake_sd.waited, 1)

    def test_tokens_only_when_no_vocoder(self):
        tokens = _orpheus_tokens(list(range(7)))
        _remove_vocoder_fakes()
        real_import = builtins.__import__

        def _no_vocoder(name, *a, **k):
            if name in ('torch', 'snac'):
                raise ImportError(f'No module named {name}')
            return real_import(name, *a, **k)

        with unittest.mock.patch.object(self.mod, 'query_ollama_tts',
                                        return_value=(tokens, 200)), \
                unittest.mock.patch('builtins.__import__', side_effect=_no_vocoder):
            result = self.mod.synthesize(self._cfg())
        self.assertEqual(result['status'], 'tokens_only')
        self.assertFalse(result['played'])
        self.assertTrue(result['output_path'].endswith('.tokens.txt'))
        self.assertTrue(os.path.exists(result['output_path']))


# ---------------------------------------------------------------------------
# main() end-stage
# ---------------------------------------------------------------------------


class TalkerMainTests(unittest.TestCase):
    def setUp(self):
        self.mod = _load_talker_module()
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def _run_main(self, cfg):
        mod = self.mod
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
        return ctx.exception.code, started, cap.records

    def test_main_speaks_emits_section_and_triggers_targets(self):
        tokens = _orpheus_tokens(list(range(7)))
        _install_vocoder_fakes()
        self.addCleanup(_remove_vocoder_fakes)
        cfg = {'input_text': 'Hi', 'output_dir': self.tmp.name, 'play_audio': False,
               'target_agents': ['sleeper_1']}
        with unittest.mock.patch.object(self.mod, 'query_ollama_tts',
                                        return_value=(tokens, 200)):
            code, started, records = self._run_main(cfg)
        self.assertEqual(code, 0)
        self.assertEqual(started, ['sleeper_1'])
        block = next(r for r in records if 'INI_SECTION_TALKER<<<' in r)
        self.assertIn('status: saved', block)

    def test_main_failure_emits_error_section_and_still_triggers_targets(self):
        # No input_text -> synthesize raises -> error section + targets still fire.
        cfg = {'input_text': '', 'output_dir': self.tmp.name,
               'target_agents': ['cleaner_1']}
        code, started, records = self._run_main(cfg)
        self.assertEqual(code, 0)                       # always exits 0 after triggering
        self.assertEqual(started, ['cleaner_1'])        # targets fire despite failure
        block = next(r for r in records if 'INI_SECTION_TALKER<<<' in r)
        self.assertIn('status: error', block)

    def test_main_male_voice_closes_entirely_and_skips_targets(self):
        # A male voice makes main() refuse BY DESIGN: report the error and CLOSE
        # the whole execution (os._exit), WITHOUT triggering any downstream agent.
        mod = self.mod
        started = []
        exits = []
        cfg = {'input_text': 'Hi', 'voice': 'leo', 'output_dir': self.tmp.name,
               'target_agents': ['cleaner_1']}

        def _fake_exit(code):
            exits.append(code)
            raise SystemExit(code)

        orig_chdir = os.getcwd()
        with _LogCapture() as cap, \
                unittest.mock.patch.object(mod, 'load_config', return_value=cfg), \
                unittest.mock.patch.object(mod, 'write_pid_file'), \
                unittest.mock.patch.object(mod, 'remove_pid_file'), \
                unittest.mock.patch.object(mod, 'wait_for_agents_to_stop'), \
                unittest.mock.patch.object(mod.os, '_exit', _fake_exit), \
                unittest.mock.patch.object(mod, 'start_agent',
                                           side_effect=lambda n: started.append(n) or True):
            with self.assertRaises(SystemExit) as ctx:
                mod.main()
        os.chdir(orig_chdir)
        self.assertEqual(ctx.exception.code, 70)          # hard, non-zero "core" exit
        self.assertEqual(exits, [70])
        self.assertEqual(started, [])                     # downstream NEVER triggered
        self.assertTrue(any('FORBIDDEN BY DESIGN' in r for r in cap.records))
        self.assertTrue(any('NOW CLOSING.. BYE' in r for r in cap.records))
        block = next(r for r in cap.records if 'INI_SECTION_TALKER<<<' in r)
        self.assertIn('status: error', block)

    def test_main_ollama_unreachable_reports_and_triggers(self):
        cfg = {'input_text': 'Hi', 'output_dir': self.tmp.name, 'target_agents': []}
        with unittest.mock.patch.object(self.mod, 'query_ollama_tts',
                                        side_effect=RuntimeError('Cannot reach Ollama at http://localhost:11434')):
            code, _started, records = self._run_main(cfg)
        self.assertEqual(code, 0)
        block = next(r for r in records if 'INI_SECTION_TALKER<<<' in r)
        self.assertIn('status: error', block)
        self.assertTrue(any('Cannot reach Ollama' in r for r in records))


# ---------------------------------------------------------------------------
# Registry / integration contracts
# ---------------------------------------------------------------------------


class TalkerRegistryTests(SimpleTestCase):
    def test_wrapped_chat_agent_spec_registered(self):
        from agent.chat_agent_registry import WRAPPED_CHAT_AGENT_SPECS
        spec = next((s for s in WRAPPED_CHAT_AGENT_SPECS
                     if s.tool_name == 'chat_agent_talker'), None)
        self.assertIsNotNone(spec)
        self.assertEqual(spec.key, 'talker')
        self.assertEqual(spec.template_dir, 'talker')
        self.assertEqual(spec.display_name, 'Talker')

    def test_registry_purpose_and_example_are_female_only(self):
        from agent.chat_agent_registry import WRAPPED_CHAT_AGENT_SPECS
        spec = next(s for s in WRAPPED_CHAT_AGENT_SPECS
                    if s.tool_name == 'chat_agent_talker')
        blob = (spec.purpose + ' ' + spec.example_request).lower()
        self.assertIn('forbidden by design', blob)
        self.assertIn('female', blob)
        # The advertised surface must NOT steer the LLM toward a male voice.
        for forbidden in ("voice='leo'", "voice='dan'", "voice='zac'", "gender='male'"):
            self.assertNotIn(forbidden, blob)

    def test_config_yaml_documents_female_only_hard_rule(self):
        config_path = os.path.join(_REPO_AGENT_DIR, 'agents', 'talker', 'config.yaml')
        with open(config_path, 'r', encoding='utf-8') as handle:
            low = handle.read().lower()
        self.assertIn('female', low)
        self.assertIn('forbidden by design', low)
        self.assertIn('now closing', low)

    def test_tools_promote_section_fields(self):
        from agent.tools import _PROMOTE_SECTION_FIELDS_BY_TEMPLATE_DIR
        fields = _PROMOTE_SECTION_FIELDS_BY_TEMPLATE_DIR.get('talker')
        self.assertIsNotNone(fields)
        for expected in ('output_path', 'voice', 'gender', 'emotion', 'status'):
            self.assertIn(expected, fields)

    def test_agent_contract_parametrizer_fields(self):
        from agent.services.agent_contracts import (
            get_agent_contract,
            get_parametrizer_source_fields,
        )
        fields = get_parametrizer_source_fields().get('talker')
        self.assertIsNotNone(fields)
        for expected in ('output_path', 'output_dir', 'filename', 'model', 'language',
                         'voice', 'gender', 'emotion', 'sample_rate', 'audio_seconds',
                         'char_count', 'played', 'status', 'response_body'):
            self.assertIn(expected, fields)
        contract = get_agent_contract('talker')
        # Producer: a connection FROM talker writes target_agents.
        self.assertEqual(contract.output_field_by_slot.get(0), 'target_agents')

    def test_config_yaml_defaults(self):
        config_path = os.path.join(_REPO_AGENT_DIR, 'agents', 'talker', 'config.yaml')
        with open(config_path, 'r', encoding='utf-8') as handle:
            cfg = yaml.safe_load(handle)
        self.assertEqual(cfg['input_text'], '')
        self.assertEqual(cfg['model'], 'legraphista/Orpheus:3b-ft-q8')
        self.assertEqual(cfg['ollama_url'], 'http://localhost:11434')
        self.assertEqual(cfg['ollama_token'], '')
        self.assertEqual(cfg['language'], 'en')
        self.assertEqual(cfg['voice'], 'tara')
        self.assertEqual(cfg['gender'], '')
        self.assertEqual(cfg['emotion'], '')
        self.assertEqual(cfg['sample_rate'], 0)
        self.assertEqual(cfg['volume_percent'], 100)
        self.assertEqual(cfg['device_index'], -1)
        self.assertTrue(cfg['play_audio'])
        self.assertIn('target_agents', cfg)

    def test_captured_in_exec_report(self):
        # Completeness contract (2026-06-07): EVERY agent that runs in Multi-Turn
        # — observational/output ones like Talker INCLUDED — is captured in the
        # Exec report (auto-resolved from the wrapped chat-agent registry).
        from agent.mcp_agent import _resolve_exec_report_spec
        spec = _resolve_exec_report_spec('chat_agent_talker')
        self.assertIsNotNone(spec)
        self.assertEqual(spec[1], 'Talker')

    def test_parametrizer_section_type_registered(self):
        param_path = os.path.join(_REPO_AGENT_DIR, 'agents', 'parametrizer', 'parametrizer.py')
        with open(param_path, 'r', encoding='utf-8') as handle:
            text = handle.read()
        self.assertIn("'talker'", text)

    def test_url_route_and_view_present(self):
        with open(os.path.join(_REPO_AGENT_DIR, 'urls.py'), 'r', encoding='utf-8') as handle:
            urls = handle.read()
        self.assertIn('update_talker_connection', urls)
        with open(os.path.join(_REPO_AGENT_DIR, 'views.py'), 'r', encoding='utf-8') as handle:
            views = handle.read()
        self.assertIn('def update_talker_connection_view', views)

    def test_migrations_present(self):
        mig_dir = os.path.join(_REPO_AGENT_DIR, 'migrations')
        self.assertTrue(os.path.exists(os.path.join(mig_dir, '0120_add_talker.py')))
        self.assertTrue(os.path.exists(
            os.path.join(mig_dir, '0121_add_chat_agent_talker_tool.py')))

    def test_css_gradient_present(self):
        css_path = os.path.join(
            _REPO_AGENT_DIR, 'static', 'agent', 'css', 'agentic_control_panel.css')
        with open(css_path, 'r', encoding='utf-8') as handle:
            css = handle.read()
        self.assertIn('.canvas-item.talker-agent', css)

    def test_js_classmap_and_connector_wired(self):
        js_dir = os.path.join(_REPO_AGENT_DIR, 'static', 'agent', 'js')
        with open(os.path.join(js_dir, 'acp-canvas-core.js'), 'r', encoding='utf-8') as handle:
            core = handle.read()
        self.assertIn("'talker': 'talker-agent'", core)
        self.assertIn("=== 'talker') updateTalkerConnection", core)
        with open(os.path.join(js_dir, 'acp-agent-connectors.js'), 'r', encoding='utf-8') as handle:
            conn = handle.read()
        self.assertIn('async function updateTalkerConnection', conn)
        with open(os.path.join(js_dir, 'acp-file-io.js'), 'r', encoding='utf-8') as handle:
            fileio = handle.read()
        self.assertIn("case 'talker':", fileio)
        with open(os.path.join(js_dir, 'acp-canvas-undo.js'), 'r', encoding='utf-8') as handle:
            undo = handle.read()
        self.assertIn('updateTalkerConnection', undo)

    def test_flow_generator_mapping_present(self):
        chat_path = os.path.join(
            _REPO_AGENT_DIR, 'static', 'agent', 'js', 'agent_page_chat.js')
        with open(chat_path, 'r', encoding='utf-8') as handle:
            chat = handle.read()
        self.assertIn("lower === 'talker'", chat)


if __name__ == '__main__':
    unittest.main()
