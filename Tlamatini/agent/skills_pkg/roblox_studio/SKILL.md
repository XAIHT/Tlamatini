---
name: roblox-studio
description: Build and edit in Roblox Studio via the Roblox Studio MCP the RIGHT way - preflight the Studio connection, do the whole build in a few big execute_luau scripts (not dozens of tiny calls), make REALISTIC terrain with the Terrain VOXEL api driven by Perlin noise (NEVER stacked Parts or concentric layers - those give ugly blocky stepped pyramids), poll generative jobs, check the console, and fail honestly. Invoke for ANY "in Roblox / Roblox Studio" request - terrain, mountains, parts, scripts, models, materials, assets.
metadata:
  openclaw:
    emoji: "🎮"
  tlamatini:
    runtime: in-process
    requires_tools: []
    requires_mcps: []
    budget:
      max_iterations: 64
      max_seconds: 1800
      max_tokens: 120000
    permissions:
      filesystem: { read: [], write: [] }
      shell:     []
      network:   deny
      db:        deny
    inputs:
      - { name: objective, type: string, required: true, description: "What to build or edit in Roblox Studio." }
    outputs:
      - { name: summary, type: string, required: true, description: "What was built and how to verify it in Studio." }
    triggers:
      keywords: ["roblox","roblox studio","luau","lua script","terrain","mountain","voxel","fillball","fillblock","writevoxels","generate mesh","procedural model","generate material","baseplate","insert asset","studio"]
---
<!--
═══════════════════════════════════════════════════════════════════
  ✦  T L A M A T I N I  ✦   —   "one who knows"
  Created by  Angela López Mendoza   ·   @angelahack1
  Tlamatini Author Banner — do not remove (Angela's name is kept in every build)
═══════════════════════════════════════════════════════════════════
-->

# Roblox Studio — build it right, build it once, make it look REAL

Follow this runbook whenever the user wants something built or edited in **Roblox Studio**. The Roblox tools are the External-MCP tools named `ext__Roblox_Studio__<tool>` (require Multi-Turn + ACPX on). Work as an OPERATOR: preflight, do the work in a FEW big scripts, verify, report — never spray dozens of tiny calls or loop on a failing one.

## STEP 0 — Preflight the connection (ALWAYS, before any build)

1. `external_mcp_status` — confirm `Roblox_Studio` is connected. If not: `external_mcp_reconnect` then `external_mcp_wait` (a first-run stdio child can take a few seconds).
2. `ext__Roblox_Studio__list_roblox_studios` → if more than one, `ext__Roblox_Studio__set_active_studio` on the intended one.
3. `ext__Roblox_Studio__get_studio_state` — confirm a place is open and the plugin is connected.
4. **If NO Studio is connected:** STOP and tell the user in one line: *"Open Roblox Studio with a place, make sure the MCP plugin is running, then say go."* Do not fake a build.

## Tool map — pick the RIGHT tool

| Want to… | Use |
|---|---|
| Run ANY Luau (build terrain/parts/scripts, set properties) | `ext__Roblox_Studio__execute_luau` — your workhorse |
| Wait for an async job (generate_*) to finish | `ext__Roblox_Studio__wait_job_finished` |
| See errors / prints from the last run | `ext__Roblox_Studio__get_console_output` |
| Read the scene tree / find instances | `ext__Roblox_Studio__inspect_instance`, `search_game_tree` |
| AI-generate an organic mesh / model / material | `generate_mesh`, `generate_procedural_model`, `generate_material` (async → poll `wait_job_finished`) |
| Marketplace asset | `search_asset` → `insert_asset` |
| Author/read scripts | `multi_edit`, `script_read`, `script_search`, `script_grep` |
| See the result on screen | `ext__Roblox_Studio__screen_capture` |

**Prefer `execute_luau` for deterministic geometry** (terrain, walls, layouts). Reserve `generate_mesh`/`generate_procedural_model` for organic one-off props the user explicitly wants AI-generated.

## GOLDEN RULES

1. **Batch.** Do the ENTIRE build in ONE (or a few) `execute_luau` script(s) that loop — not one part/mountain per call.
2. **REALISM = Terrain VOXELS + Perlin noise (see the terrain section — this is the #1 thing people get wrong).** Never build landscape from `Part`s and never use symmetric concentric layers — both look fake and blocky.
3. **Wrap every script in `pcall`** and finish with `print("TLM_OK <what happened>")` (else `warn(err)`), then read `get_console_output` to confirm.
4. **Correct Luau types.** `Vector3.new(x,y,z)` needs three NUMBERS; `Region3`/`CFrame` likewise. `"Unable to cast double to Vector3"` = you passed a number where a Vector3 was expected — fix the call, don't retry it unchanged.
5. **Undo-friendly:** wrap edits in `ChangeHistoryService:TryBeginRecording(...)` / `:FinishRecording(...)`.
6. **Never loop on a failing tool.** If a call errors twice, STOP, read `get_console_output`, fix the root cause OR tell the user honestly. (The executor also blocks a call repeated 3×.)
7. **Verify then report.** Never say "done" until `get_console_output` (and ideally `screen_capture`) confirms it.

## TERRAIN & MOUNTAINS — make them REALISTIC (this is where builds go WRONG)

Realistic terrain has **two hard requirements**. Skip either and you get **ugly blocky STEPPED PYRAMIDS (a ziggurat)** — that is a FAIL, not a mountain:

1. **Use `workspace.Terrain` VOXELS — NEVER `Part`s / `WedgePart`s.** Stacked Parts show hard rectangular STEPS. Terrain voxels smooth into continuous rock/snow.
2. **Drive the shape with PERLIN NOISE (`math.noise`) — NEVER concentric symmetric layers.** Concentric shrinking disks/squares = a perfect cone or a stepped ziggurat. Real mountains are IRREGULAR: asymmetric peaks, ridges, spurs, foothills, no two slopes alike.

**The right way — a Perlin-noise HEIGHTMAP written with `Terrain:WriteVoxels` (ONE call, smooth, natural).** For each (x,z): surface height = summed peak falloffs (smoothstep → rounded base, not a sharp tip) **plus multi-octave `math.noise`**; then fill voxels below it — Rock, Snow above a NOISY snowline, Grass at the base:

```lua
local Terrain = workspace.Terrain
local RES = 4                 -- voxel size in studs (4 = detailed, 8 = faster/coarser)
local W   = 512               -- terrain is W x W studs, centered on origin
local peaks = {              -- jitter these; DIFFERENT heights/spreads = natural
  {x=0,   z=0,   h=150, r=175},
  {x=-150,z=-130,h=95,  r=120},
  {x=165, z=140, h=120, r=135},
  {x=-135,z=150, h=62,  r=95 },
  {x=170, z=-125,h=48,  r=80 },
}
local AIR,ROCK,SNOW,GRASS = Enum.Material.Air,Enum.Material.Rock,Enum.Material.Snow,Enum.Material.Grass
local function surfaceY(wx, wz)
  local h = 6                                          -- flat-ish base ground
  for _,p in ipairs(peaks) do
    local dx,dz = wx-p.x, wz-p.z
    local d = math.sqrt(dx*dx + dz*dz)
    local f = math.clamp(1 - d/p.r, 0, 1)
    f = f*f*(3 - 2*f)                                  -- smoothstep => rounded, no cone tip
    h = h + p.h*f
  end
  -- multi-octave value noise: ridges + roughness + asymmetry (THIS is what makes it REAL)
  h = h + math.noise(wx*0.006, wz*0.006, 0.3)*40
        + math.noise(wx*0.015, wz*0.015, 2.7)*15
        + math.noise(wx*0.045, wz*0.045, 6.1)*5
  return math.max(2, h)
end
local ok, err = pcall(function()
  local region = Region3.new(Vector3.new(-W/2,0,-W/2), Vector3.new(W/2,176,W/2)):ExpandToGrid(RES)
  local size   = region.Size/RES
  local origin = region.CFrame.Position - region.Size/2      -- world min corner
  local mats, occ = {}, {}
  for x=1,size.X do mats[x]={} occ[x]={}
    for y=1,size.Y do mats[x][y]={} occ[x][y]={}
      for z=1,size.Z do
        local wx = origin.X + (x-0.5)*RES
        local wy = origin.Y + (y-0.5)*RES
        local wz = origin.Z + (z-0.5)*RES
        local s  = surfaceY(wx, wz)
        if wy <= s then
          occ[x][y][z] = 1
          local snowline = 92 + math.noise(wx*0.02, wz*0.02, 4.0)*22   -- ragged snow edge
          mats[x][y][z] = (wy > snowline and SNOW) or (wy < 9 and GRASS or ROCK)
        else
          occ[x][y][z] = 0; mats[x][y][z] = AIR
        end
      end
    end
  end
  Terrain:WriteVoxels(region, RES, mats, occ)
end)
if ok then
  print(("TLM_OK realistic terrain: %d peaks, %dx%d studs, Perlin-noise ridged, snow-capped"):format(#peaks, W, W))
else
  warn("TLM_FAIL "..tostring(err))
end
```

Tune to the user's spec: number/height/spread of `peaks`, `W` (terrain size), `RES` (detail vs speed — bump to 8 if the volume is huge), the three `math.noise` amplitudes (bigger = rougher ridges). Keep peak centers inside `±W/2`. **`Terrain:WriteVoxels` caps at ~4.19M voxels per call** — for a bigger world, loop the region in ≤~256-stud chunks. Only claim success after the `TLM_OK` line prints.

**Anti-patterns that produce the ugly pyramid — do NOT do these:**
- ❌ Building landscape from `Part`s / `WedgePart`s stacked in layers → hard rectangular steps (this is exactly the ziggurat look).
- ❌ Concentric `FillBlock`/`FillBall` disks of shrinking size with no noise → a smooth cone or a stepped pyramid.
- ❌ Perfectly symmetric peaks, uniform slopes, five identical mountains.

(If for some reason you cannot use `WriteVoxels` and must use `FillBall`, STILL drive each ball's radius and center offset with `math.noise` and overlap MANY small jittered balls so the silhouette is ragged — but the heightmap + `WriteVoxels` above is strongly preferred for realism.)

## GENERATIVE tools (mesh / model / material)

`generate_mesh` / `generate_procedural_model` / `generate_material` kick off an ASYNC job and return a job id. Then `wait_job_finished(job_id)` → place the result with Luau. Use these for organic PROPS (rocks, trees, creatures) — not for large landscape.

## VERIFY & REPORT (always)

1. `get_console_output` — confirm the `TLM_OK` marker printed and there are no red errors / no `TLM_FAIL`.
2. `screen_capture` — aim the camera at the terrain first (`workspace.CurrentCamera.CFrame = CFrame.lookAt(Vector3.new(400,300,400), Vector3.new(0,60,0))` via a quick `execute_luau`), then capture, so you and the user actually SEE that it is natural, not blocky.
3. Tell the user in a couple of lines WHAT was built and HOW to see it (which place; select it in Explorer + press F to frame). Only claim success after verify confirms it.

## FAILURE HANDLING (honest, never silent)

- Studio not connected → the STEP 0 message; do not pretend to build.
- A Luau error / `TLM_FAIL` → read `get_console_output`, fix the actual line (types, nil, WriteVoxels region/array sizing), retry ONCE. If it still fails, report the exact error and stop.
- A generative job that never finishes → report the timeout; fall back to `execute_luau` for deterministic geometry.
- Do NOT report "done" unless the console/verify step actually confirmed it.
