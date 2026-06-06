---
name: project_camcorder_agent
description: "2026-06-03 added Camcorder (#71) webcam photo/video agent (canvas + chat_agent_camcorder)"
metadata: 
  node_type: memory
  type: project
  originSessionId: 6042ffd5-f15d-42d1-a80c-e57e415206ed
---

2026-06-03: added **Camcorder** (#71) — a webcam capture agent (OpenCV `cv2`) on BOTH canvas + Multi-Turn (`chat_agent_camcorder`). Sibling of [[project_playwrighter_agent]]-style capture but for the physical CAMERA (Shoter = screen, Camcorder = camera); observational like Shoter so NOT in the Exec Report.

**Behavior:** `capture_mode` = `photo` (DEFAULT, one shot) or `video` (segment of `video_duration_seconds`, no audio). `camera_index` picks the camera (0=default). **Resolution analysis (user asked):** optional `resolution_width`/`resolution_height` default `0x0` = camera native (robust — webcams only support discrete modes; forcing one snaps to nearest); when set, requested + read-back logged. Saves to the **Pictures known-folder** (`SHGetKnownFolderPath` FOLDERID_Pictures via ctypes, fallback `~/Pictures`) under `TlamatiniCamcorder` with a collision-proof `camcorder_<media>_<YYYYmmdd>_<HHMMSS>_<ms>_cam<idx>.<ext>` name. Emits atomic `INI_SECTION_CAMCORDER` (output_path/output_dir/filename/media_type/camera_index/duration_seconds/resolution/fps/response_body) for Parametrizer; always triggers target_agents. Photo=.jpg, video=.mp4 (`mp4v`).

**Files:** agent `agents/camcorder/{camcorder.py,config.yaml}` (Shoter boilerplate); `update_camcorder_connection_view` (views.py, target-only producer like Shoter) + urls.py route; migrations **0112** (Agent row) + **0113** (Chat-Agent-Camcorder Tool row); `ChatWrappedAgentSpec` in chat_agent_registry.py; `_PARAMETRIZER_OUTPUT_FIELDS['camcorder']` in services/agent_contracts.py; `'camcorder'` in parametrizer.py SECTION_AGENT_TYPES; `opencv-python==4.13.0.92` in requirements.txt. Frontend: CSS gradient (charcoal→REC-red→amber→gold, unique), classMap + mouseup + removeConnection + removeConnectionsFor in acp-canvas-core.js (MORE complete than Shoter, which lacks the remove paths), undo/redo in acp-canvas-undo.js, .flw load in acp-file-io.js, `updateCamcorderConnection` connector, `_mapToolArgsToAgentConfig` branch in agent_page_chat.js, eslint.config.mjs global + 3 `/* global */` headers. Docs: agents_descriptions.md row, agentic_skill.md #70 (FlowCreator bumped to #71), README counts 70→71 / 77→78 tools + §9.5 anchor + Action family + source-agents 25→26.

**Verified:** ruff + eslint (0 errors) clean; 22 camcorder tests + 39 arduiner = 61 green (no shared-registry regression); makemigrations --check clean; wrapped tool exposed as `Camcorder`. **E2E against the REAL camera** (isolated runtime dir): photo 67KB JPEG 640x480 + video 346KB 3s MP4, both saved to `C:\Users\angel\Pictures\TlamatiniCamcorder`. cv2 4.13.0 already in the dev python. **NOT committed.** Naming per [[feedback_agent_naming_conventions]]; docs swept per [[feedback_update_agent_docs]]. Frozen build needs `python build.py` (bundles opencv + the agent dir).
