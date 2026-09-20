# Video-Analyzer: robotics, transcription and summaries

Created by Angela López Mendoza · @angelahack1 — Tlamatini.

`analysis_type` selects one of three tasks. Existing configurations without the key
continue to use `robotics`. All modes accept `video_pathfilenames`: a file, wildcard,
directory (newest video), or Camcorder pool name. They emit one atomic
`INI_SECTION_VIDEO_ANALYZER` block and start downstream agents even on failure.

| Mode | Processing | Routing |
|---|---|---|
| `robotics` (default) | OpenCV motion gate, two independent vision interpreters, merger; `expected_motion` describes the physical test | Existing `TLM_VERDICT::PASS_OK`, `FAIL_NO_MOTION`, `FAIL_WRONG_MOTION`, `UNCLEAR`, `ANALYSIS_ERROR` |
| `transcription` | Decode selected audio tracks, transcribe with local faster-whisper, preserve timestamps; no microphone or vision calls | `TLM_ANALYSIS::TRANSCRIBED`, `NO_AUDIO`, `NO_SPEECH`, `PARTIAL`, `ERROR` |
| `summary` | Transcription plus two independent visual observers per timestamped frame batch, then hierarchical text synthesis | `TLM_ANALYSIS::SUMMARY_COMPLETE`, `PARTIAL`, `ERROR` |

Content modes bypass the motion gate: lectures, slides and static scenes are valid.
They report `verdict: NOT_APPLICABLE` and an empty `verdict_token`, never a robotics
PASS. Robotics accepts PASS only when **both** interpreters explicitly report
`FRAME_VERDICT: PASS_OK`; a missing verdict cannot count as agreement.

## Configuration

```yaml
analysis_type: transcription
video_pathfilenames: 'C:/Clips/lecture.mkv'
audio_tracks: all
transcription:
  model: "@config"  # Config → Models → Speech; a literal value pins this agent.
  device: auto
  compute_type: auto
  language: ''
  task: transcribe
  beam_size: 5
  vad_filter: true
  word_timestamps: false
  chunk_seconds: 120
output_dir: ''
```

`audio_tracks` accepts `all` (default) or comma-separated **audio track ordinals**,
such as `0,1`. Tracks stay separate; stereo channels are downmixed to mono within
each track. A track is not a speaker. An invalid selection reports an error instead
of silently choosing another track. Each selected track is decoded in bounded
30–300 second chunks, at 16 kHz. Stream offsets and timestamp discontinuities are
retained. Chunk boundaries can split speech; use longer chunks when context matters.

The local backend follows Whisperer's GPU auto-detection and CPU/int8 fallback,
including failures while decoding the lazy segment generator. `model` accepts a
faster-whisper model name or local model directory. First use may download weights.
`language: ''` auto-detects; `task: translate` translates to English. This agent's
transcription mode uses the local backend; Whisperer's cloud endpoint and microphone
settings do not apply. Original speech and timestamps remain in the artifacts.

```yaml
analysis_type: summary
video_pathfilenames: 'C:/Clips/lecture.mp4'
audio_tracks: all
summary_prompt: 'Explain the topic, demonstrated steps, decisions and open questions; cite timestamps.'
summary_language: English
summary_frame_interval: 5
summary_max_frames: 120
summary_batch_size: 8
```

Summary frames are uniformly distributed from start to end. `summary_max_frames`
is clamped to 2–600 and `summary_batch_size` to 1–16; frames are resized to at most
1280 pixels on their longest side. Reaching the cap widens sampling intervals
instead of analyzing only the beginning. Missing frame count/rate or unreadable
frames is reported as incomplete coverage. An unreadable sample is retried up to
one second earlier without duplicating the previous frame; any recovered sample
uses its decoded frame index and reports the adjusted timestamp. The existing `interpreter_model_1`,
`interpreter_model_2`, `merging_model`, `llm.host` and `llm.token` select models and
transport. Robotics prompts, `num_frames`, `roi` and `expected_motion` do not steer
content summaries; use `summary_prompt` and `summary_language`.

Visual observations cover scenes, actions, objects, setting, readable on-screen
text, slides, diagrams, numbers and transitions. The synthesis combines these
with timestamped speech into an overview, chronology, concrete facts, procedures,
decisions, action items, conclusions and limitations. Long evidence is reduced in
bounded chunks, including its tail. If synthesis fails, raw observations and speech
remain available; the agent does not claim a completed summary.

This is sampled perception, not exhaustive recovery. Brief events, small text and
unclear speech may be missed. OCR is performed by the vision models. Embedded subtitle
streams are not separately extracted. There is no speaker diarization, identity
recognition or non-speech sound classification. Multiple language/dubbing tracks may
repeat the same content. Summary quality depends on the selected models and sampling.

## Artifacts, statuses and Parametrizer

Content modes create a unique run subdirectory under `output_dir`; the default is
`TLAMATINI_TEMP/video-analysis` (app Temp in standalone source/pool use). Existing
files and the input video are never overwritten. Each run saves:

- `transcript.txt`: track-tagged speech with segment timestamps.
- `segments.json`: track, start/end, text, language, optional word timestamps.
- `report.md`: readable result, coverage warnings, full transcript and visual evidence.
- `analysis.json`: complete structured result and media/track metadata.

Original robotics fields remain. Added fields are `analysis_type`, `analysis_token`,
`duration_seconds`, `audio_status`, `audio_track_count`, `audio_tracks_analyzed`,
`language`, `transcription_device`, `transcript`, `summary`, `transcript_path`,
`segments_path`, `report_path`, `analysis_path`, `segments_json`, `warnings_json`,
and `metadata_json`. Fields absent in robotics are not invented. `confidence` and
`motion_score` are empty in content modes, since no motion verdict was computed.

`transcript` and `summary` are single-line text in the log header. `response_body`
contains the multiline report. Read the files for original line breaks, or parse
`segments_json` for individual utterances. Log markers inside source/model text
are escaped to prevent forged sections and routing tokens; artifact text is original.

| Outcome | `status` | `audio_status` |
|---|---|---|
| Completed transcript | `transcribed` | `transcribed` |
| No audio tracks / no detected speech | `no_matches` | `no_audio` / `no_speech` |
| Completed summary (silent videos are valid) | `analyzed` | `transcribed`, `no_audio` or `no_speech` |
| Some evidence missing or synthesis failed | `partial` | `partial`, `error`, or the completed audio outcome |
| No useful requested analysis | `error` | `error` where applicable |

Parametrizer's source choices come from `services/agent_contracts.py` and the generated
FlowCreator catalog. The generic parser handles all three modes. Example mappings:

- Camcorder `output_path` → Video-Analyzer `video_pathfilenames`.
- Video-Analyzer `transcript` → Talker `input_text`.
- Video-Analyzer `summary` or `response_body` → PDFer `input_text`.
- Video-Analyzer `report_path` → File-Interpreter `path_filenames`.

Keep Parametrizer's one-source/one-target rule and configure `analysis_type` on the
target Video-Analyzer. Use `analysis_token` for content flow branching, including
partial/error routes; a content flow must not wait for `TLM_VERDICT::PASS_OK`.

The wrapped `chat_agent_video_analyzer` tool promotes fields to its result. Process
`status` and semantic `agent_status` remain distinct. Promotion reads the completed
header even when a long transcript exceeds the log excerpt. Promoted values over
16,000 characters are listed in `promoted_fields_truncated`; text is shortened and
oversized JSON is omitted (empty string). Read `analysis_path`/`segments_path` for
the full values. Parametrizer's on-disk log retains the full fields.

## Runtime and validation

The flat `video_content.py` sibling ships with new pools and is refreshed into
existing pools. No `agent.*`/Django import is required. PyAV is explicitly pinned
and included in build import/asset checks; its FFmpeg libraries decode tracks
without an external executable. OpenCV is only needed for visual analysis.

Transcription cost scales with the duration and number of selected tracks and
model/device speed. Summaries add two vision calls per frame batch plus evidence
reduction and final synthesis. `AUDIO:` and `SUMMARY:` logs identify stage progress;
weight downloads and CPU decoding can take longer than a robotics test.

Offline regressions: `python -m unittest Tlamatini.agent.test_video_analyzer_content`.
Original robotics/integration tests: `python Tlamatini/manage.py test agent.test_video_analyzer_agent`.
Regenerate discoverability after contract edits: `python scripts/update_flow_catalog.py`,
then run its `--check` mode. Tests exercise real multi-track media decoding and
copied-pool execution; ASR/LLM replies are mocked unless a live check is explicitly run.

Validation on 2026-09-19 also used a real generated speech/video clip with the
cached base Whisper model on CPU: all three spoken sentences were recovered with
timestamps. A live summary combined that transcript with two visual samples using
the installed `gemma4:cloud` and `jcyhsiao/qwen3.5cloud:latest` observers and
`glm-5.3:cloud` synthesis. On 2026-09-20, the former first interpreter
`qwen3-vl:235b-cloud` returned HTTP 410 with a retirement message. The initial
replacement is `gemma4:cloud`; all three choices now come from Config → Models
unless an explicit agent override is supplied. These checks establish execution and
integration, not exhaustive accuracy for every video, language or model.

## Model configuration and partial coverage

The visual models use `"@config"` in YAML and follow Config → Models → Vision.
The local transcription model follows Speech → Video-Analyzer audio tracks.
Explicit per-agent model names override the global choice. Permanent observer
errors (HTTP 401/403/404/410) stop further calls to that observer in the current
summary run. The healthy observer continues; status remains `partial`. The JSON
report records `visual_coverage`: frames covered by any observer, frames covered
by both, and per-observer failed/skipped batches. Robotics keeps its conservative
verdict checks. See [model configuration](../../../../docs/model_configuration.md).

Saving central model settings affects the next configuration load; restart an
already running agent if needed. Wrapped chat uses global model choices followed
by explicit tool arguments, so a saved canvas override does not govern a separate
chat invocation. A manually copied agent needs its portable `model_settings.py`
helper and an explicit `CONFIG_PATH` outside the normal agents tree. The frozen
web process uses the compiled registry and refreshed portable assets, without
depending on a self-modification source snapshot. Run `check_agent_runtimes` in
source and frozen modes to verify preparation and model loading; this gate does
not establish inference accuracy or provider availability.
