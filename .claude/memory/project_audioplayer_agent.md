---
name: project_audioplayer_agent
description: "AudioPlayer (#73) audio-playback workflow agent — soundfile+sounddevice, canvas + chat_agent_audioplayer"
metadata: 
  node_type: memory
  type: project
  originSessionId: 1aab0e43-c804-4922-bd35-e7fe3f7a807a
---
<!--
═══════════════════════════════════════════════════════════════════
  ✦  T L A M A T I N I  ✦   —   "one who knows"
  Created by  Angela López Mendoza   ·   @angelahack1
  Developer · Architect · Creator of Tlamatini
  Tlamatini Author Banner — do not remove (Angela's name is kept in every build)
═══════════════════════════════════════════════════════════════════
-->

2026-06-04: Added **AudioPlayer** (73rd agent type) — the audio PLAYBACK counterpart of [[project_recorder_agent]] (mic-IN); completes the media-I/O family Shoter(screen)/Camcorder(camera)/Recorder(mic-in)/AudioPlayer(speakers-OUT). On BOTH canvas + Multi-Turn (`chat_agent_audioplayer`).

**What it does:** plays an `audio_file` (WAV/FLAC/OGG/AIFF, MP3 with recent libsndfile) via `soundfile` (decode) + `sounddevice` `OutputStream` (stream). Plays to the system DEFAULT output by default, or `device_index`/`device_name`. `volume_percent` = SOFTWARE gain (NOT OS slider; clip count reported). **`time_played`**: 0 = whole file once; N>0 = exactly N s — TRUNCATE a longer file / LOOP a shorter one (full repeats + final partial), done with a **streaming wrap-around callback** so a huge duration over a tiny file never allocates a giant buffer. `sample_rate` 0 = file's native rate (correct pitch; override forces output rate + pitch-shift warning, no resample). Does NOT change the Windows OS default endpoint (stated as an up-front constraint — [[feedback_state_constraints_upfront]]).

**Sampling-rate analysis (user asked):** rate is READ from the file, so it is NOT a required param — `sample_rate: 0` default. Mirrors the project's `0 = native` convention.

**Observational/output → NOT in Exec Report** (like Shoter/Recorder/Camcorder; mutates no persistent state). Emits atomic `INI_SECTION_AUDIOPLAYER` (`input_path` full path, `played_seconds`, `play_mode`, `loops`, `status`, …) for Parametrizer; ALWAYS triggers `target_agents` (success OR failure — error path emits `status: error` section).

**Files:** `agent/agents/audioplayer/{audioplayer.py,config.yaml}`; migrations **0116/0117**; `chat_agent_registry` spec; `tools.py` `_PROMOTE_SECTION_FIELDS_BY_TEMPLATE_DIR['audioplayer']`; `agent_contracts._PARAMETRIZER_OUTPUT_FIELDS`; `parametrizer.SECTION_AGENT_TYPES`; `views.update_audioplayer_connection_view` + url; CSS `.audioplayer-agent` (indigo→violet→magenta→amber); JS connectors/canvas-core×4/undo×2/file-io + 3 global decls + `_mapToolArgsToAgentConfig`. New dep **soundfile==0.12.1** (requirements.txt + build.py `_agent_libs`). Docs: agents_descriptions.md, agentic_skill.md (#72, FlowCreator→#73), README (counts 72→73, catalog, parametrizer 27→28, Latest blurb v1.15.0), package.json 1.15.0.

**Verification:** `test_audioplayer_agent.py` = 43 tests (fake soundfile+sounddevice drive REAL truncate/loop/full math frame-exact); ruff + eslint(0 err) clean; migrate run; build-scripts + recorder regressions green. **Live E2E**: ran the real agent foreground — looped a 1s tone 3× for `time_played:3` through the default Realtek speakers, emitted the INI block, exit 0. NOT committed (frozen build needs `python build.py`).
