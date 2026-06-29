---
name: project_videoplayer_agent
description: "VideoPlayer (#74) video+audio playback agent — ffpyplayer+OpenCV, canvas + chat_agent_videoplayer"
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

2026-06-04: Added **VideoPlayer** (74th agent type) — on-screen VIDEO playback WITH audio; the screen sibling of [[project_audioplayer_agent]] (AudioPlayer=speakers, VideoPlayer=screen window). On BOTH canvas + Multi-Turn (`chat_agent_videoplayer`).

**Backend decision (user asked: bundle cleanly with PyInstaller, NO external deps, all in requirements.txt):** chose **ffpyplayer** (pip wheel BUNDLES ffmpeg+SDL — no external ffmpeg, no runtime download; decode + synced audio + `set_volume`) for A/V + **OpenCV/cv2** (already bundled for Camcorder) for the WINDOW. ffpyplayer is PRIMARY; if it's unavailable the agent degrades to SILENT cv2 video (volume no-op, logged) — so the core honors the "bundles with no problems" bar even worst-case. Rejected: ffplay-bootstrap (external binary), python-vlc (needs system VLC). build.py: added `--collect-all ffpyplayer` + `_agent_libs` verify. Dep **ffpyplayer==4.5.3** in requirements.txt.

**What it does:** plays `video_file` (.mp4/.mov/.mkv/.avi/.webm). `display_index` picks the monitor (-1=primary; enumerated via ctypes EnumDisplayMonitors). `volume_percent` (capped at 100). **`time_played`**: 0=whole video once; N>0=exactly N s — TRUNCATE longer / LOOP shorter (whole repeats + final partial), via a wall-clock `drive_playback` driver. `window_width`/`window_height` (0=native), `fullscreen`, `keep_aspect` (cv2 WINDOW_KEEPRATIO). cv2 window: namedWindow/resizeWindow/moveWindow/setWindowProperty FULLSCREEN.

**Additional-params analysis (user asked):** OMIT playback-speed/fps (native timing), decode-resolution/codec (intrinsic; window size = display scaling only), audio-track/subtitle (advanced). INCLUDE keep_aspect.

**Observational/output → NOT in Exec Report.** Emits `INI_SECTION_VIDEOPLAYER` (`input_path` full path, `played_seconds`, `play_mode`, `loops`, `backend`, `has_audio`, `status`, …); ALWAYS triggers `target_agents` (error path emits `status:error`).

**Files:** `agent/agents/videoplayer/{videoplayer.py,config.yaml}`; migrations **0118/0119**; chat_agent_registry spec; tools.py `_PROMOTE_SECTION_FIELDS`; agent_contracts `_PARAMETRIZER_OUTPUT_FIELDS`; parametrizer SECTION_AGENT_TYPES; views.update_videoplayer_connection_view + url; CSS `.videoplayer-agent` (midnight→blue→crimson→gold); JS connectors/canvas-core×4/undo×2/file-io + 3 globals + `_mapToolArgsToAgentConfig`. Docs: agents_descriptions.md, agentic_skill.md (#73, FlowCreator→#74), README (counts 73→74, catalog, parametrizer 28→29, Latest v1.16.0), package.json 1.16.0.

**Verification:** `test_videoplayer_agent.py` = 38 tests (fake clock/backend drive REAL truncate/loop math; fake ffpyplayer/cv2 backends; rgb24→bgr; geometry/monitor resolution). ruff + eslint(0 err) + check clean; migrate run; flow-contracts/audioplayer/build-scripts regressions green (83). **Live E2E**: real agent looped a 2s clip to fill time_played=5 (loops=2 + partial) in a 640x360 window via ffpyplayer, exit 0. NOT committed (frozen build needs `python build.py`).
