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

Runbook for anything built or edited in **Roblox Studio**. The tools are the External-MCP tools `ext__Roblox_Studio__<tool>` (need Multi-Turn + ACPX on). Work as an OPERATOR: preflight, build in a FEW big scripts, verify, report.

## STEP 0 — Preflight (ALWAYS, before any build)

1. `external_mcp_status` — is `Roblox_Studio` connected? If not: `external_mcp_reconnect`, then `external_mcp_wait` (a first-run stdio child takes seconds).
2. `list_roblox_studios` → if more than one, `set_active_studio` on the intended one.
3. `get_studio_state` — a place must be open with the plugin connected.
4. **No Studio connected:** STOP and say *"Open Roblox Studio with a place, make sure the MCP plugin is running, then say go."* Never fake a build.

## Tool map

| Want to… | Use |
|---|---|
| Run ANY Luau (terrain, parts, scripts, properties) | `execute_luau` — the workhorse |
| Wait for an async `generate_*` job | `wait_job_finished` |
| See errors / prints | `get_console_output` |
| Read the scene tree | `inspect_instance`, `search_game_tree` |
| AI-generate an organic mesh/model/material | `generate_mesh`, `generate_procedural_model`, `generate_material` (async → poll) |
| Marketplace asset | `search_asset` → `insert_asset` |
| Author/read scripts | `multi_edit`, `script_read`, `script_search`, `script_grep` |
| See the result | `screen_capture` |

Use `execute_luau` for deterministic geometry; reserve the generative tools for organic one-off props.

## GOLDEN RULES

1. **Batch** — the ENTIRE build in one or a few looping `execute_luau` scripts, not one part per call.
2. **Realism = Terrain VOXELS + Perlin noise** (below). Never landscape out of `Part`s, never symmetric concentric layers.
3. **Wrap every script in `pcall`**, end with `print("TLM_OK …")` (else `warn(err)`), then confirm via `get_console_output`.
4. **Correct Luau types** — `Vector3.new(x,y,z)` takes three NUMBERS. `"Unable to cast double to Vector3"` means you passed a number where a Vector3 belongs: fix it, don't retry unchanged.
5. **Undo-friendly** — `ChangeHistoryService:TryBeginRecording(...)` / `:FinishRecording(...)`.
6. **Never loop on a failing tool.** Two errors → stop, read the console, fix the cause or say so honestly (the executor blocks a 3× repeat anyway).
7. **Verify, then report.** "Done" only after the console (ideally a capture) confirms it.

## TERRAIN & MOUNTAINS — where builds go WRONG

Two hard requirements; skip either and you get **blocky STEPPED PYRAMIDS** — a FAIL, not a mountain:

1. **`workspace.Terrain` VOXELS, never `Part`s** — stacked parts show hard rectangular steps; voxels smooth into rock/snow.
2. **Shape driven by PERLIN NOISE (`math.noise`), never concentric layers** — concentric shrinking disks give a cone or a ziggurat. Real mountains are irregular: asymmetric peaks, ridges, spurs, no two slopes alike.

**The right way — a Perlin-noise heightmap written with ONE `Terrain:WriteVoxels`.** Per (x,z): height = summed peak falloffs (smoothstep → rounded base) **plus multi-octave `math.noise`**; fill below it — Rock, Snow above a NOISY snowline, Grass at the base:

```lua
local Terrain = workspace.Terrain
local RES = 4                 -- voxel studs (4 = detailed, 8 = faster)
local W   = 512               -- W x W studs, centered on origin
local peaks = {               -- jitter these; DIFFERENT heights/spreads = natural
  {x=0,   z=0,   h=150, r=175},
  {x=-150,z=-130,h=95,  r=120},
  {x=165, z=140, h=120, r=135},
  {x=-135,z=150, h=62,  r=95 },
  {x=170, z=-125,h=48,  r=80 },
}
local AIR,ROCK,SNOW,GRASS = Enum.Material.Air,Enum.Material.Rock,Enum.Material.Snow,Enum.Material.Grass
local function surfaceY(wx, wz)
  local h = 6                                        -- flat-ish base ground
  for _,p in ipairs(peaks) do
    local dx,dz = wx-p.x, wz-p.z
    local f = math.clamp(1 - math.sqrt(dx*dx+dz*dz)/p.r, 0, 1)
    f = f*f*(3 - 2*f)                                -- smoothstep => no cone tip
    h = h + p.h*f
  end
  -- multi-octave noise: ridges + roughness + asymmetry (THIS makes it REAL)
  h = h + math.noise(wx*0.006, wz*0.006, 0.3)*40
        + math.noise(wx*0.015, wz*0.015, 2.7)*15
        + math.noise(wx*0.045, wz*0.045, 6.1)*5
  return math.max(2, h)
end
local ok, err = pcall(function()
  local region = Region3.new(Vector3.new(-W/2,0,-W/2), Vector3.new(W/2,176,W/2)):ExpandToGrid(RES)
  local size   = region.Size/RES
  local origin = region.CFrame.Position - region.Size/2   -- world min corner
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
          local snowline = 92 + math.noise(wx*0.02, wz*0.02, 4.0)*22  -- ragged edge
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
  print(("TLM_OK terrain: %d peaks, %dx%d studs, noise-ridged, snow-capped"):format(#peaks, W, W))
else
  warn("TLM_FAIL "..tostring(err))
end
```

Tune `peaks` (count/height/spread), `W`, `RES` (bump to 8 for huge volumes) and the three noise amplitudes (bigger = rougher). Keep peak centers inside `±W/2`. **`WriteVoxels` caps at ~4.19M voxels per call** — loop the region in ≤~256-stud chunks for a bigger world.

**Never:** landscape from `Part`s/`WedgePart`s; concentric `FillBlock`/`FillBall` disks without noise; perfectly symmetric peaks or identical mountains. If you truly must use `FillBall`, still jitter every radius/center with `math.noise` and overlap many small balls — but the heightmap above is strongly preferred.

## GENERATIVE tools

`generate_mesh` / `generate_procedural_model` / `generate_material` start an ASYNC job returning a job id → `wait_job_finished(job_id)` → place the result with Luau. For organic PROPS, not landscape.

## VERIFY & REPORT (always)

1. `get_console_output` — the `TLM_OK` marker printed, no red errors, no `TLM_FAIL`.
2. `screen_capture` — aim the camera first via a quick `execute_luau` (`workspace.CurrentCamera.CFrame = CFrame.lookAt(Vector3.new(400,300,400), Vector3.new(0,60,0))`), so you both SEE it is natural, not blocky.
3. Say in two lines WHAT was built and HOW to see it (which place; select in Explorer + press F). Claim success only after verifying.

## FAILURE HANDLING (honest, never silent)

- Studio not connected → the STEP 0 message; do not pretend to build.
- Luau error / `TLM_FAIL` → read the console, fix the real line (types, nil, WriteVoxels region/array sizing), retry ONCE, then report the exact error and stop.
- Generative job never finishes → report the timeout, fall back to `execute_luau`.
- Never report "done" unless verify actually confirmed it.
