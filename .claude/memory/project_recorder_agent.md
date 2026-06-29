---
name: project_recorder_agent
description: "Recorder (#72) microphone/audio-capture agent added on canvas + Multi-Turn"
metadata: 
  node_type: memory
  type: project
  originSessionId: a66c5e04-f5f4-4bef-b32f-f340ba2b10a1
---
<!--
═══════════════════════════════════════════════════════════════════
  ✦  T L A M A T I N I  ✦   —   "one who knows"
  Created by  Angela López Mendoza   ·   @angelahack1
  Developer · Architect · Creator of Tlamatini
  Tlamatini Author Banner — do not remove (Angela's name is kept in every build)
═══════════════════════════════════════════════════════════════════
-->

2026-06-03: Added **Recorder** (agent #72) — microphone / audio-input capture via `sounddevice` → WAV (written with stdlib `wave`). Audio sibling of [[project_camcorder_agent]] (camera) and Shoter (screen); **observational → NOT in Exec Report**. Both canvas + Multi-Turn (`chat_agent_recorder`).

**Config**: `device_index` (-1=system default mic; else PortAudio index), `device_name` (substring match alt), `record_seconds` (default 5), `sample_rate` (0=device NATIVE default — the analysis answer: expose the param but default to querying the device, robust; else 44100/48000/16000), `channels` (1=mono default, clamped to device max), `output_dir` (""=Music/TlamatiniRecords). Always logs the numbered input-device list at startup. Saves `recorder_<YYYYmmdd>_<HHMMSS>_<ms>_dev<tag>.wav` to the **Music** known-folder (FOLDERID_Music) /TlamatiniRecords. Emits `INI_SECTION_RECORDER` (output_path, output_dir, filename, device_index, device_name, sample_rate, channels, duration_seconds, format; body=response_body) + always triggers target_agents.

**Robustness fix**: numeric config reads go through `_coerce_float`/`_coerce_int` (extract leading number, never raise) — caught the real wrapped-parser incident where `record_seconds` became `"1 from the default microphone"` and `float()` crashed the capture. Also added `recorder` + `camcorder` to `tools.py::_PROMOTE_SECTION_FIELDS_BY_TEMPLATE_DIR` so the wrapped tool surfaces `output_path` top-level (camcorder claimed it but was never wired — latent bug fixed).

**Wiring**: `sounddevice==0.5.1` in requirements.txt + build.py `_agent_libs`. Migrations 0114 (Agent row, idAgent 56) / 0115 (chat_agent_recorder Tool); ChatWrappedAgentSpec; update_recorder_connection_view + URL; parametrizer SECTION_AGENT_TYPES + agent_contracts `_PARAMETRIZER_OUTPUT_FIELDS`; CSS deep-ocean-teal gradient (#001219/005f73/0a9396/94d2bd); JS connector + core×classMap+3 + undo×2 + file-io + globals×3 + eslint global + Flow-Generator branch. Docs: agentic_skill.md #71 (FlowCreator→#72), agents_descriptions.md, README counts 71→72 + parametrizer sources 26→27, CLAUDE.md structure tree.

**input_gain_percent** (added 2026-06-03, follow-up): SOFTWARE/digital gain % (100=unity default, 200=+6dB, 50=−6dB, 0=silence) applied to the int16 buffer before WAV write via `_apply_gain` (widen→×factor→count clips→round→clip to int16 rail). Reports `gain_percent` + `clipped_samples` in the section. HARDWARE mic level is NOT controllable via sounddevice/PortAudio (would need WASAPI IAudioEndpointVolume/pycaw — Windows-only, fragile index→endpoint map; declined). Wired through config/section/agent_contracts/tools-promote/Flow-Generator/registry/agentic_skill/agents_descriptions.

E2E verified live (real mic, 11 devices, valid WAV) on the source instance AND via the wrapped `chat_agent_recorder` tool (status=completed, output_path top-level). 37 recorder tests (test_recorder_agent.py) + 69 across related suites green; ruff/eslint clean. **Not committed.** Frozen build needs `python build.py` (recorder.py is a pool agent run under PYTHON_HOME; sounddevice must be pip-installed there — build.py installs requirements.txt into PYTHON_HOME). Naming per [[feedback_agent_naming_conventions]].
