"""
Seed one end-to-end Unreal MCP demo prompt that exercises the
chat_agent_unrealer wrapped Multi-Turn tool across every Unreal MCP
command category (editor / blueprint / node / umg) in a single guided
Multi-Turn run.

Preconditions documented in the prompt body:
- An Unreal Engine 5 project is already running in dev mode (PIE not
  required — the editor itself listens).
- The Unreal MCP plugin is installed and the in-engine TCP listener
  is bound to 127.0.0.1:55557.

Slot: idPrompt 32 (next free after 0072..0074's ACPX demos which seeded 25-31).
"""
from django.db import migrations


PROMPT_CONTENT = (
    "Tlamatini, run the **Unreal MCP End-to-End Editor Drive** demo, please. "
    "Preconditions you can assume are TRUE for this run (do NOT verify them — "
    "trust them and proceed straight to Step 1): "
    "(a) Unreal Engine 5 is open in dev mode with a project loaded; "
    "(b) the Unreal MCP plugin is installed and its in-engine TCP listener is "
    "bound to **127.0.0.1:55557**; "
    "(c) the Tlamatini **chat_agent_unrealer** wrapped tool is enabled "
    "(it is, by default) and is the ONLY tool you may use to talk to Unreal — "
    "do NOT spin up chat_agent_pythonxer or execute_command with raw socket code, "
    "and do NOT use acp_spawn (that's for external coding-agent CLIs, not for "
    "Unreal's editor plugin). "
    "Every step below MUST be exactly ONE chat_agent_unrealer call whose "
    "request string is shaped "
    "\"Run Unreal command with command='<verb>' and params.<k1>='<v1>' and params.<k2>=<v2> ...\". "
    "After each call, read the wrapped tool's JSON return — the Unreal response "
    "is embedded under the run's `log_excerpt` as an INI_SECTION_UNREALER block — "
    "and capture host/port/command/status/error plus the assistant-visible "
    "`response_body` so you can render the per-step row in Step 9. "
    "If any step returns status='error', record the error verbatim, DO NOT abort, "
    "and continue to the next step so the final table shows the full run shape. "
    "\n\n"
    "Step 0: emit one HTML opening banner: "
    "<div style='padding:18px;border-radius:14px;background:linear-gradient(135deg,#0B1220 0%,#1F3A8A 33%,#10B981 66%,#22D3EE 100%);color:#fff;font-family:Inter,Segoe UI,sans-serif;text-align:center;'>"
    "<h2 style='margin:0;letter-spacing:2px;'>&#127918; UNREAL MCP END-TO-END EDITOR DRIVE &#127918;</h2>"
    "<div style='opacity:.9;margin-top:4px;'>Tlamatini Unrealer &mdash; chat_agent_unrealer over 127.0.0.1:55557</div></div>. "
    "\n\n"
    "Step 1 (editor &mdash; sanity-probe the connection): call "
    "**chat_agent_unrealer** with request "
    "\"Run Unreal command with command='get_actors_in_level'\". "
    "This is your ground-truth that the TCP socket is alive; the response_body "
    "is a JSON dict whose `actors` (or `result.actors`) array lists every actor "
    "currently in the active level. Capture the count for the final table. "
    "\n\n"
    "Step 2 (editor &mdash; spawn a primitive directly into the level): call "
    "**chat_agent_unrealer** with request "
    "\"Run Unreal command with command='spawn_actor' and params.name='TlamatiniProbe_Cube' "
    "and params.type='StaticMeshActor' and params.location=[0,0,150] and params.rotation=[0,0,0]\". "
    "This places a bare StaticMeshActor named TlamatiniProbe_Cube 150 units above the world origin. "
    "It has no mesh assigned yet &mdash; that's expected for this command. "
    "\n\n"
    "Step 3 (editor &mdash; verify the spawn took): call "
    "**chat_agent_unrealer** with request "
    "\"Run Unreal command with command='find_actors_by_name' and params.pattern='TlamatiniProbe_Cube'\". "
    "The response should list at least one match; if zero matches, log the discrepancy "
    "but do not abort. "
    "\n\n"
    "Step 4 (blueprint &mdash; scaffold a new Blueprint class): call "
    "**chat_agent_unrealer** with request "
    "\"Run Unreal command with command='create_blueprint' and params.name='BP_TlamatiniProbe' "
    "and params.parent_class='Actor'\". "
    "This creates a brand-new BP_TlamatiniProbe Blueprint Actor at the Unreal MCP plugin's "
    "default content path. "
    "\n\n"
    "Step 5 (blueprint &mdash; give it a static-mesh component): call "
    "**chat_agent_unrealer** with request "
    "\"Run Unreal command with command='add_component_to_blueprint' and params.blueprint_name='BP_TlamatiniProbe' "
    "and params.component_type='StaticMeshComponent' and params.component_name='ProbeMesh' "
    "and params.location=[0,0,0] and params.rotation=[0,0,0] and params.scale=[1,1,1]\". "
    "\n\n"
    "Step 6 (blueprint &mdash; compile so the editor accepts the new BP): call "
    "**chat_agent_unrealer** with request "
    "\"Run Unreal command with command='compile_blueprint' and params.blueprint_name='BP_TlamatiniProbe'\". "
    "Capture the response's compile status; some plugin builds return "
    "`{\"success\": true}`, others return `{\"status\": \"ok\"}`. Either shape means OK. "
    "\n\n"
    "Step 7 (editor &mdash; spawn an instance of the freshly compiled BP): call "
    "**chat_agent_unrealer** with request "
    "\"Run Unreal command with command='spawn_blueprint_actor' and params.blueprint_name='BP_TlamatiniProbe' "
    "and params.actor_name='TlamatiniProbe_Spawned' and params.location=[200,0,150] and params.rotation=[0,0,0]\". "
    "This drops one BP_TlamatiniProbe instance into the level next to the bare cube from Step 2. "
    "\n\n"
    "Step 8 (umg &mdash; build a simple HUD widget and show it): emit FOUR chat_agent_unrealer "
    "calls in order, capturing the JSON response of each: "
    "(8a) \"Run Unreal command with command='create_umg_widget_blueprint' and params.widget_name='WBP_TlamatiniProbeHUD' "
    "and params.parent_class='UserWidget' and params.path='/Game/UI'\"; "
    "(8b) \"Run Unreal command with command='add_text_block_to_widget' and params.widget_name='WBP_TlamatiniProbeHUD' "
    "and params.text_block_name='ProbeLabel' and params.text='Tlamatini Probe Active' and params.position=[40,40] "
    "and params.size=[320,48] and params.font_size=24 and params.color=[1,1,1,1]\"; "
    "(8c) \"Run Unreal command with command='add_button_to_widget' and params.widget_name='WBP_TlamatiniProbeHUD' "
    "and params.button_name='ProbeDismiss' and params.text='Dismiss' and params.position=[40,108] "
    "and params.size=[160,40] and params.font_size=16 and params.color=[1,1,1,1] "
    "and params.background_color=[0.1,0.1,0.1,1]\"; "
    "(8d) \"Run Unreal command with command='add_widget_to_viewport' and params.widget_name='WBP_TlamatiniProbeHUD' "
    "and params.z_order=10\". "
    "After 8d the widget is on the game viewport &mdash; visible if the user pressed Play, otherwise queued "
    "for the next PIE session. Don't treat absence-of-PIE as failure. "
    "\n\n"
    "Step 9 (render the run report): emit one HTML table with class='exec-report-table' "
    "titled '<strong>Unreal MCP Run Report &mdash; chat_agent_unrealer over 127.0.0.1:55557</strong>' "
    "and columns "
    "<em>step</em>, <em>category</em>, <em>unreal_command</em>, <em>params (compact JSON)</em>, "
    "<em>status</em> (ok|error), <em>headline</em> (one-line summary from response_body or error). "
    "One row per Unreal call (so 12 rows total: 1 for Step 1, 1 for Step 2, 1 for Step 3, "
    "1 for Step 4, 1 for Step 5, 1 for Step 6, 1 for Step 7, and 4 for Steps 8a-d). "
    "Sort rows in execution order. Use the **status** column verbatim from the INI_SECTION_UNREALER "
    "block's status field; do NOT re-classify. Suggested tint: green cell background for ok, "
    "subtle red for error, no row hidden either way &mdash; the goal of this demo is to show the "
    "FULL command surface in one shot. "
    "\n\n"
    "Step 10: close with one HTML banner that prints, in big letters, "
    "either '&#9989; UNREAL MCP FULLY OPERATIONAL' (if every step returned status='ok'), "
    "'&#9888;&#65039; UNREAL MCP PARTIALLY OPERATIONAL' (if at least one step succeeded but "
    "any step returned error), or '&#10060; UNREAL MCP UNREACHABLE' (if Step 1 itself errored "
    "&mdash; in that case the most common cause is that the in-engine plugin's TCP listener "
    "isn't bound yet; suggest checking the Unreal Output Log for 'UnrealMCP listening on 127.0.0.1:55557'). "
    "Underneath the banner, print a one-line metric: "
    "'Total Unreal calls: <N>, ok: <K>, error: <N-K>, level-actor count delta: "
    "<count after Step 7 minus count after Step 1>'. "
    "\n\n"
    "Cleanup note (informational, NOT a step): the demo leaves three new artifacts in the project "
    "(actor TlamatiniProbe_Cube, blueprint BP_TlamatiniProbe with one spawned instance "
    "TlamatiniProbe_Spawned, and widget /Game/UI/WBP_TlamatiniProbeHUD). They are intentionally "
    "kept so the user can inspect them in the editor. To clean them up later, run a follow-up "
    "chat with chat_agent_unrealer calls for delete_actor on each, plus a normal editor "
    "right-click-Delete on BP_TlamatiniProbe and WBP_TlamatiniProbeHUD in the Content Browser. "
    "End with END-RESPONSE."
)


def add_unrealer_demo_prompt(apps, schema_editor):
    Prompt = apps.get_model('agent', 'Prompt')
    Prompt.objects.get_or_create(
        idPrompt=32,
        defaults={
            'promptName': 'prompt-32',
            'promptContent': PROMPT_CONTENT,
        }
    )


def remove_unrealer_demo_prompt(apps, schema_editor):
    Prompt = apps.get_model('agent', 'Prompt')
    Prompt.objects.filter(promptName='prompt-32').delete()


class Migration(migrations.Migration):
    dependencies = [
        ('agent', '0086_add_chat_agent_unrealer_tool'),
    ]

    operations = [
        migrations.RunPython(add_unrealer_demo_prompt, remove_unrealer_demo_prompt),
    ]
