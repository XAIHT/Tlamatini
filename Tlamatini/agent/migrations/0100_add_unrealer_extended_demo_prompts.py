"""
Seed three Catalog-of-Prompts demos that exercise the **extended** Unreal MCP
command surface — the System / Level / Asset / Material categories plus
``take_screenshot`` — none of which the original Unrealer demo (idPrompt 25,
migration 0087) touches. 0087 drives editor / blueprint / node / umg only; these
three drive the rest, at basic / medium / hard complexity:

    60  UNREAL SNAPSHOT          basic     get_current_level -> spawn_actor ->
                                           take_screenshot -> save_current_level
                                           (the observe->act loop, shortest new win)
    61  UNREAL SCENE FORGE       medium    get_current_level -> list_assets ->
                                           create_folder -> create_material ->
                                           create_material_instance ->
                                           set_material_parameter -> spawn_actor ->
                                           assign_material -> take_screenshot ->
                                           save_current_level (content authoring)
    62  UNREAL PYTHON & INTROSPECT  hard   execute_console_command (via the agent's
                                           console_command remap) -> get_class_info ->
                                           list_assets -> execute_python (the universal
                                           in-editor escape hatch, multi-line code passed
                                           as a triple-quoted params.code) -> take_screenshot

All three drive the wrapped **chat_agent_unrealer** Multi-Turn tool, exactly like
idPrompt 25. They are deliberately runnable against the same live editor: each opens
with the preconditions (UE5 open in dev mode, the Unreal MCP plugin's TCP listener
bound to 127.0.0.1:55557) and reminds the user to tick ONLY the **Multi-Turn**
checkbox — chat_agent_unrealer is NOT behind the ACPX / Skill surface, so ACPX is not
required (same as the Kalier 0099 and Windower 0095/0096 demos).

Placement (append, no renumber)
-------------------------------
The catalog dropdown (static/agent/js/tools_dialog.js::loadPrompts) enumerates
promptName 'prompt-1', 'prompt-2', ... and BREAKS at the first missing slot, so the
catalog must stay a contiguous, gap-free 'prompt-1..N'. Slots 1-59 are fully occupied
(0099 appended the three KALI demos at 57-59). These three therefore APPEND at the tail
(60-62) — contiguity is preserved with no shift of any existing prompt, so no other
Prompt row's idPrompt/promptName changes. Reverse simply deletes 60-62.
(MAX_PROMPTS=100, so there is ample room.)

Honesty note baked into the prompts: a freshly-created (blank) Material declares no
named parameters, so ``set_material_parameter`` may legitimately return status='error'
("parameter not found"). Demo 61 records that verbatim and continues — the goal is to
show the full Material command surface and its real failure modes, mirroring how the
0087 demo treats a meshless spawn as "expected, not a failure".
"""
from django.db import migrations


# A reusable Unreal-themed banner palette (navy -> royal-blue -> emerald -> cyan),
# the same family the original idPrompt-25 demo uses so the Unreal MCP demos read as
# one branded set in the catalog.
_BANNER_OPEN = (
    "<div style='padding:18px;border-radius:14px;background:linear-gradient(135deg,"
    "#0B1220 0%,#1F3A8A 33%,#10B981 66%,#22D3EE 100%);color:#fff;font-family:Inter,"
    "Segoe UI,sans-serif;text-align:center;'>"
)


UNREAL_SNAPSHOT_DEMO = (
    "Tlamatini, run the **UNREAL SNAPSHOT** demo, please &mdash; a basic, end-to-end "
    "showcase of the *observe&rarr;act loop* on a live Unreal Engine 5 editor: it reads "
    "the current level, spawns one actor, captures a viewport screenshot to disk so you "
    "can SEE the change, and saves the level &mdash; all from chat through the wrapped "
    "**chat_agent_unrealer** tool. "
    "PRECONDITIONS you can assume are TRUE (do NOT verify them &mdash; trust them and go "
    "straight to Step 1): (a) UE5 is open in dev mode with a project loaded; (b) the "
    "Unreal MCP plugin is installed and its in-engine TCP listener is bound to "
    "**127.0.0.1:55557**; (c) tick ONLY the **Multi-Turn** checkbox before sending "
    "(ACPX is NOT required &mdash; chat_agent_unrealer is the ONLY tool you may use to "
    "talk to Unreal; do NOT use chat_agent_pythonxer / execute_command / acp_spawn). "
    "Every step is exactly ONE chat_agent_unrealer call shaped "
    "\"Run Unreal command with command='<verb>' and params.<k>=<v> ...\". After each call, "
    "read the JSON return (the Unreal response is an INI_SECTION_UNREALER block under the "
    "run's log_excerpt) and capture command/status/error plus response_body. If a step "
    "returns status='error', record it verbatim, DO NOT abort, continue. "
    "\n\n"
    "Step 0: open with one HTML banner &mdash; " + _BANNER_OPEN +
    "<h2 style='margin:0;letter-spacing:2px;'>&#128247; UNREAL SNAPSHOT &#128247;</h2>"
    "<div style='opacity:.9;margin-top:4px;'>Tlamatini Unrealer &mdash; spawn &rarr; screenshot &rarr; save</div></div>. "
    "\n\n"
    "Step 1 (level &mdash; where are we): call **chat_agent_unrealer** with request "
    "\"Run Unreal command with command='get_current_level'\". Capture the level name / "
    "package path / actor count from response_body. If THIS errors, the plugin listener "
    "is almost certainly not bound &mdash; skip to the closing banner with an "
    "'UNREACHABLE' verdict and suggest checking the UE Output Log for "
    "'UnrealMCP listening on 127.0.0.1:55557'. "
    "\n\n"
    "Step 2 (editor &mdash; spawn something to look at): call **chat_agent_unrealer** with "
    "request \"Run Unreal command with command='spawn_actor' and "
    "params.name='SnapshotProbe_Cube' and params.type='StaticMeshActor' and "
    "params.location=[0,0,200] and params.rotation=[0,0,0]\". "
    "\n\n"
    "Step 3 (editor &mdash; OBSERVE the change): call **chat_agent_unrealer** with request "
    "\"Run Unreal command with command='take_screenshot' and "
    "params.filepath='C:/Temp/unreal_snapshot.png'\". Note that params.filepath is a DISK "
    "path on the machine running the editor (NOT a /Game content path), so the agent does "
    "not rewrite it. Capture the saved path the plugin returns. "
    "\n\n"
    "Step 4 (level &mdash; persist): call **chat_agent_unrealer** with request "
    "\"Run Unreal command with command='save_current_level'\". "
    "\n\n"
    "Step 5: render an HTML table with class='exec-report-table' titled "
    "'<strong>Unreal Snapshot &mdash; Run Report</strong>' and columns <em>step</em>, "
    "<em>category</em>, <em>unreal_command</em>, <em>status</em> (ok|error), "
    "<em>headline</em> (one-line summary from response_body or error) &mdash; one row per "
    "call in execution order. Use the status verbatim from the INI_SECTION_UNREALER block; "
    "do NOT re-classify. Light body cells (background:#ffffff;color:#0f172a; or striped "
    "#f1f5f9), green tint for ok and subtle red for error, no row hidden. "
    "\n\n"
    "Step 6: close with one HTML banner reusing the Step 0 style that prints, in big "
    "letters, '&#9989; SNAPSHOT CAPTURED' (if every step returned ok), "
    "'&#9888;&#65039; SNAPSHOT PARTIAL' (if some ok, some error), or "
    "'&#10060; UNREAL UNREACHABLE' (if Step 1 errored), and underneath a one-line metric "
    "'level: <name> &middot; calls ok: <K>/<N> &middot; screenshot: "
    "C:/Temp/unreal_snapshot.png'. End with END-RESPONSE."
)


UNREAL_SCENE_FORGE_DEMO = (
    "Tlamatini, run the **UNREAL SCENE FORGE** demo, please &mdash; a medium-complexity "
    "content-authoring pipeline that exercises the Unreal MCP **Asset** and **Material** "
    "categories (plus a level read/save and a screenshot), driven entirely from chat "
    "through the wrapped **chat_agent_unrealer** tool: it inventories the project, makes a "
    "content folder, authors a material + material instance, tints the instance, spawns a "
    "mesh actor, assigns the material to it, screenshots the result and saves the level. "
    "PRECONDITIONS you can assume are TRUE (do NOT verify; go straight to Step 1): (a) UE5 "
    "open in dev mode with a project loaded; (b) the Unreal MCP plugin's TCP listener is "
    "bound to **127.0.0.1:55557**; (c) tick ONLY the **Multi-Turn** checkbox (ACPX is NOT "
    "required). Use ONLY chat_agent_unrealer to talk to Unreal, ONE call per step shaped "
    "\"Run Unreal command with command='<verb>' and params.<k>=<v> ...\". Read each JSON "
    "return (the Unreal response is an INI_SECTION_UNREALER block under log_excerpt), "
    "capture command/status/error/response_body, and on status='error' record it verbatim "
    "and CONTINUE (do not abort). "
    "\n\n"
    "Step 0: open with one HTML banner &mdash; " + _BANNER_OPEN +
    "<h2 style='margin:0;letter-spacing:2px;'>&#127912; UNREAL SCENE FORGE &#127912;</h2>"
    "<div style='opacity:.9;margin-top:4px;'>Tlamatini Unrealer &mdash; folder &middot; material &middot; assign &middot; shoot</div></div>. "
    "\n\n"
    "Step 1 (level): \"Run Unreal command with command='get_current_level'\" &mdash; capture "
    "the level name and actor count as the 'before' baseline. "
    "\n\n"
    "Step 2 (system &mdash; inventory): \"Run Unreal command with command='list_assets' and "
    "params.path='/Game' and params.recursive=true\". Capture the asset count from "
    "response_body (count or result.count). "
    "\n\n"
    "Step 3 (asset &mdash; make a home for our content): \"Run Unreal command with "
    "command='create_folder' and params.path='/Game/TlamatiniForge'\". "
    "\n\n"
    "Step 4 (material &mdash; create the base material): \"Run Unreal command with "
    "command='create_material' and params.name='M_TlamatiniForge' and "
    "params.path='/Game/TlamatiniForge'\". Capture the created material path. "
    "\n\n"
    "Step 5 (material &mdash; derive an instance): \"Run Unreal command with "
    "command='create_material_instance' and params.name='MI_TlamatiniForge' and "
    "params.parent_material='/Game/TlamatiniForge/M_TlamatiniForge' and "
    "params.path='/Game/TlamatiniForge'\". "
    "\n\n"
    "Step 6 (material &mdash; tint it): \"Run Unreal command with "
    "command='set_material_parameter' and "
    "params.material='/Game/TlamatiniForge/MI_TlamatiniForge' and params.parameter='BaseColor' "
    "and params.value=[1,0,0]\". IMPORTANT &mdash; a brand-new BLANK material declares no "
    "named parameters, so this step MAY legitimately return status='error' "
    "(\"parameter 'BaseColor' not found\"). That is EXPECTED for a material created in "
    "Step 4 with no parameter graph; record the error verbatim and CONTINUE. (In a real "
    "project you would point params.material at a parent material that actually exposes a "
    "BaseColor parameter, or add the parameter via an execute_python step first.) "
    "\n\n"
    "Step 7 (editor &mdash; something to paint): \"Run Unreal command with "
    "command='spawn_actor' and params.name='ForgeProbe_Cube' and "
    "params.type='StaticMeshActor' and params.location=[0,0,200]\". "
    "\n\n"
    "Step 8 (material &mdash; assign): \"Run Unreal command with command='assign_material' "
    "and params.actor='ForgeProbe_Cube' and "
    "params.material='/Game/TlamatiniForge/MI_TlamatiniForge' and params.slot=0\". "
    "\n\n"
    "Step 9 (editor &mdash; OBSERVE): \"Run Unreal command with command='take_screenshot' "
    "and params.filepath='C:/Temp/unreal_scene_forge.png'\" (a disk path on the editor host; "
    "not normalized). "
    "\n\n"
    "Step 10 (level &mdash; persist material + level): \"Run Unreal command with "
    "command='save_all'\" so the new content folder, material, instance and the level are "
    "all written to disk. "
    "\n\n"
    "Step 11: render an HTML table with class='exec-report-table' titled "
    "'<strong>Unreal Scene Forge &mdash; Run Report</strong>' and columns <em>step</em>, "
    "<em>category</em> (level|system|asset|material|editor), <em>unreal_command</em>, "
    "<em>params (compact JSON)</em>, <em>status</em> (ok|error), <em>headline</em> "
    "&mdash; one row per call in execution order, status verbatim from the "
    "INI_SECTION_UNREALER block (do NOT re-classify). Light body cells "
    "(background:#ffffff;color:#0f172a; or striped #f1f5f9); green tint ok, subtle red "
    "error, nothing hidden. "
    "\n\n"
    "Step 12: close with one HTML banner reusing the Step 0 style printing "
    "'&#9989; SCENE FORGED' (every step ok), '&#9888;&#65039; SCENE FORGE PARTIAL' "
    "(set_material_parameter is the expected soft-fail; if ONLY it errored you may still "
    "call it a successful demo of the surface), or '&#10060; UNREAL UNREACHABLE' (Step 1 "
    "errored), and underneath a one-line metric 'assets before: <N> &middot; created: "
    "folder+material+instance &middot; calls ok: <K>/<N> &middot; screenshot: "
    "C:/Temp/unreal_scene_forge.png'. End with END-RESPONSE."
)


UNREAL_PYTHON_INTROSPECT_DEMO = (
    "Tlamatini, run the **UNREAL PYTHON & INTROSPECTION** demo, please &mdash; an advanced "
    "showcase of the Unreal MCP **System** category: it runs an editor console command, "
    "reflects an engine class, enumerates assets, and then uses **execute_python** &mdash; "
    "the universal in-editor escape hatch that can reach ANYTHING in UE5's `unreal` Python "
    "API &mdash; before screenshotting the viewport, all from chat through the wrapped "
    "**chat_agent_unrealer** tool. "
    "PRECONDITIONS you can assume are TRUE (do NOT verify; go straight to Step 1): (a) UE5 "
    "open in dev mode with a project loaded; (b) the Unreal MCP plugin's TCP listener is "
    "bound to **127.0.0.1:55557**; (c) the project has the **Python Editor Script Plugin** "
    "enabled (required for execute_python); (d) tick ONLY the **Multi-Turn** checkbox "
    "(ACPX is NOT required). Use ONLY chat_agent_unrealer, ONE call per step. Read each "
    "JSON return (INI_SECTION_UNREALER block under log_excerpt), capture "
    "command/status/error/response_body, and on status='error' record verbatim and "
    "CONTINUE. "
    "\n\n"
    "Step 0: open with one HTML banner &mdash; " + _BANNER_OPEN +
    "<h2 style='margin:0;letter-spacing:2px;'>&#128013; UNREAL PYTHON &amp; INTROSPECTION &#128013;</h2>"
    "<div style='opacity:.9;margin-top:4px;'>Tlamatini Unrealer &mdash; console &middot; reflect &middot; list &middot; execute_python</div></div>. "
    "\n\n"
    "Step 1 (system &mdash; console / CVar): call **chat_agent_unrealer** with request "
    "\"Run Unreal command with command='execute_console_command' and "
    "params.console_command='stat fps'\". NOTE: the console line goes in "
    "params.console_command (NOT params.command) &mdash; the Unrealer agent remaps it to the "
    "wire's params.command automatically so it does not collide with the top-level command "
    "selector. This toggles the on-screen FPS stat. "
    "\n\n"
    "Step 2 (system &mdash; reflection): call **chat_agent_unrealer** with request "
    "\"Run Unreal command with command='get_class_info' and params.class_name='StaticMeshActor'\". "
    "From response_body capture the parent class and a few of the property names it reports "
    "&mdash; this is how you discover valid property names before a set_actor_property call. "
    "\n\n"
    "Step 3 (system &mdash; asset enumeration): call **chat_agent_unrealer** with request "
    "\"Run Unreal command with command='list_assets' and params.path='/Game' and "
    "params.recursive=true\". Capture the asset count. "
    "\n\n"
    "Step 4 (system &mdash; THE escape hatch, execute_python): call **chat_agent_unrealer** "
    "with a request whose params.code is a TRIPLE-QUOTED multi-line Python literal (use "
    "''' ... ''' so the newlines and inner quotes survive the parser), exactly: "
    "\"Run Unreal command with command='execute_python' and params.code='''import unreal\n"
    "actors = unreal.EditorLevelLibrary.get_all_level_actors()\n"
    "unreal.log('Tlamatini execute_python: %d actors in the active level' % len(actors))\n"
    "ver = unreal.SystemLibrary.get_engine_version()\n"
    "unreal.log('Engine version: %s' % ver)\n"
    "len(actors)'''\". "
    "The execute_python handler returns `success`, `result` (the repr of the last "
    "expression &mdash; here the actor count) and `log` (the unreal.log lines). Capture the "
    "actor count and the engine-version log line from response_body. If this step errors "
    "with a 'Python' / 'plugin' message, the Python Editor Script Plugin is probably "
    "disabled &mdash; record it and continue. "
    "\n\n"
    "Step 5 (editor &mdash; OBSERVE): call **chat_agent_unrealer** with request "
    "\"Run Unreal command with command='take_screenshot' and "
    "params.filepath='C:/Temp/unreal_python_introspection.png'\". "
    "\n\n"
    "Step 6: render a STATUS SCOREBOARD &mdash; a row of HTML chips of the form "
    "<span style='display:inline-block;padding:8px 16px;margin:3px;border-radius:10px;"
    "font-weight:800;background:CHIP_BG;color:#ffffff;'>LABEL</span>: a 'console: <ok|err>' "
    "chip, a 'reflect: <ok|err>' chip, a 'list_assets: <ok|err>' chip, a "
    "'execute_python: <ok|err>' chip (CHIP_BG #16a34a when ok else #dc2626), and an "
    "'actors: <N>' chip (CHIP_BG #2563EB). "
    "\n\n"
    "Step 7: render an HTML table with class='exec-report-table' titled "
    "'<strong>Unreal Python &amp; Introspection &mdash; Run Report</strong>' and columns "
    "<em>step</em>, <em>unreal_command</em>, <em>status</em> (ok|error), <em>headline</em> "
    "(parent class for get_class_info; asset count for list_assets; actor count + engine "
    "version for execute_python; etc.) &mdash; one row per call in execution order, status "
    "verbatim from the INI_SECTION_UNREALER block. Light body cells "
    "(background:#ffffff;color:#0f172a; or striped #f1f5f9). "
    "\n\n"
    "Step 8: close with one HTML banner reusing the Step 0 style printing "
    "'&#9989; PYTHON BRIDGE LIVE' (if execute_python returned ok), "
    "'&#9888;&#65039; SYSTEM SURFACE PARTIAL' (some system calls ok, some error), or "
    "'&#10060; UNREAL UNREACHABLE' (if Step 1 errored), and underneath a one-line metric "
    "'engine: <version> &middot; actors: <N> &middot; assets: <M> &middot; system calls ok: "
    "<K>/4 &middot; screenshot: C:/Temp/unreal_python_introspection.png'. End with "
    "END-RESPONSE."
)


_NEW_PROMPTS = (
    (60, UNREAL_SNAPSHOT_DEMO),
    (61, UNREAL_SCENE_FORGE_DEMO),
    (62, UNREAL_PYTHON_INTROSPECT_DEMO),
)


def add_unrealer_extended_demo_prompts(apps, schema_editor):
    Prompt = apps.get_model('agent', 'Prompt')
    for prompt_id, content in _NEW_PROMPTS:
        Prompt.objects.update_or_create(
            idPrompt=prompt_id,
            defaults={'promptName': f'prompt-{prompt_id}', 'promptContent': content},
        )


def remove_unrealer_extended_demo_prompts(apps, schema_editor):
    Prompt = apps.get_model('agent', 'Prompt')
    Prompt.objects.filter(idPrompt__in=[pid for pid, _ in _NEW_PROMPTS]).delete()


class Migration(migrations.Migration):
    dependencies = [
        ('agent', '0099_add_kalier_demo_prompts'),
    ]

    operations = [
        migrations.RunPython(
            add_unrealer_extended_demo_prompts,
            remove_unrealer_extended_demo_prompts,
        ),
    ]
