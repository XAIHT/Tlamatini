# ═══════════════════════════════════════════════════════════════════
#   ✦  T L A M A T I N I  ✦   —   "one who knows"
#
#   Crafted with heart by  Angela   ·   @angelahack1
#   Developer · Architect · Creator of Tlamatini
#
#   Every line of this file was written by Angela.
# ═══════════════════════════════════════════════════════════════════
#   Tlamatini Author Banner — do not remove (releases scrub the name automatically)
"""
Seed a Catalog-of-Prompts demo for **Blenderer** — Tlamatini's BLENDER bridge —
run through the wrapped **chat_agent_blenderer** Multi-Turn tool. This is the
MANDATORY catalog prompt every Multi-Turn-capable agent must ship (CLAUDE.md
directive / create_new_agent.md Step 7.8 / tlamatini-agent-creation Phase 19).

    75  BLENDER FORGE   basic   create a Suzanne (monkey) -> give it a colour ->
                                render a still to the Temp dir -> report
                                version/object/render-path + status.

SAFE to run repeatedly (the daily chat test may execute it): it only adds one
object + one material to the live scene and renders a small still under the app
Temp dir. Blenderer talks to the OFFICIAL Blender MCP add-on socket
(localhost:9876); if Blender is not running / the add-on server is not started,
chat_agent_blenderer returns status `error` with an actionable connection
message (a documented degraded mode, NOT a crash) — the prompt records that
verbatim and finishes gracefully.

Placement (append, no renumber)
-------------------------------
The catalog dropdown (static/agent/js/tools_dialog.js) enumerates promptName
'prompt-1','prompt-2',... and BREAKS at the first missing slot, so the catalog
must stay a contiguous, gap-free 'prompt-1..N'. Slots 1-74 are occupied (0125
appended the Whisperer demo at 74); this APPENDS at 75 with no shift of any
existing prompt. Reverse deletes 75. (MAX_PROMPTS=100.)
"""
from django.db import migrations


# Blenderer banner palette — mirrors the ``.canvas-item.blenderer-agent``
# gradient (deep blue -> Blender blue -> Blender orange -> warm amber).
_BANNER_OPEN = (
    "<div style='padding:18px;border-radius:14px;background:linear-gradient(135deg,"
    "#15334f 0%,#2a6fb3 33%,#ea7600 66%,#f7b733 100%);color:#fff;font-family:Inter,"
    "Segoe UI,sans-serif;text-align:center;text-shadow:0 1px 3px rgba(0,0,0,.5);'>"
)


BLENDER_FORGE_DEMO = (
    "Tlamatini, run the **BLENDER FORGE** demo, please &mdash; a basic showcase of your own "
    "3D-modelling bridge, driven entirely from chat through the wrapped **chat_agent_blenderer** "
    "tool, which speaks the OFFICIAL Blender MCP add-on's socket protocol (you ARE the client &mdash; "
    "no external LLM client needed). "
    "PRECONDITIONS you can assume are TRUE (do NOT verify them &mdash; go straight to Step 1): "
    "(a) tick ONLY the **Multi-Turn** checkbox before sending (ACPX is NOT required &mdash; "
    "chat_agent_blenderer is the ONLY tool you may use; do NOT use chat_agent_executer / "
    "chat_agent_pythonxer / acp_spawn); (b) Blender is expected to be running with the Blender MCP "
    "add-on enabled, 'Online access' on, and the server started &mdash; but if it is NOT reachable, "
    "chat_agent_blenderer returns status `error` with a clear connection message (a documented "
    "degraded mode, NOT a failure): record it verbatim, SKIP the remaining Blender steps, and go "
    "straight to the closing banner. "
    "\n\n"
    "Step 0: open with one HTML banner &mdash; " + _BANNER_OPEN +
    "<h2 style='margin:0;letter-spacing:2px;'>&#127912; BLENDER FORGE &#129412;</h2>"
    "<div style='opacity:.92;margin-top:4px;'>Tlamatini Blenderer &mdash; chat in, 3D out</div></div>. "
    "\n\n"
    "Step 1 (probe): call **chat_agent_blenderer** with request \"Run Blender command with "
    "command='ping'\". From the INI_SECTION_BLENDERER block in the run's log_excerpt capture status "
    "(ok | error) and, on ok, the blender_version_string and scene. If status is error, note the "
    "message and JUMP to Step 5. "
    "\n\n"
    "Step 2 (model): call **chat_agent_blenderer** with request \"Run Blender command with "
    "command='create_object' and params.type='monkey' and params.name='ForgeSuzanne' and "
    "params.location=[0,0,2]\". Capture the created object name from the response. "
    "\n\n"
    "Step 3 (colour): call **chat_agent_blenderer** with request \"Run Blender command with "
    "command='set_material' and params.object_name='ForgeSuzanne' and params.color=[0.92,0.46,0.0] "
    "and params.material='ForgeOrange'\". Capture the material name. "
    "\n\n"
    "Step 4 (render): call **chat_agent_blenderer** with request \"Run Blender command with "
    "command='render'\" (no output_path &mdash; Blenderer defaults the .png under the app Temp dir). "
    "From the INI_SECTION_BLENDERER block capture the rendered file path and whether it exists. "
    "\n\n"
    "Step 5: render an HTML table with class='exec-report-table' titled "
    "'<strong>Blender Forge &mdash; Build Report</strong>' and columns <em>step</em>, <em>command</em>, "
    "<em>status</em>, <em>detail</em> &mdash; one row per chat_agent_blenderer call you made, every "
    "value verbatim from its INI_SECTION_BLENDERER block (do NOT re-classify). Light body cells "
    "(background:#ffffff;color:#0f172a), green tint for status ok, red tint for status error. "
    "\n\n"
    "Step 6: close with one HTML banner reusing the Step 0 style printing, in big letters, "
    "'&#9989; FORGED' (every Blender step returned ok &mdash; show the rendered path) or "
    "'&#9881;&#65039; BLENDER UNREACHABLE' (Step 1 errored &mdash; quote the connection message and "
    "the one-line fix 'enable the Blender MCP add-on, turn on Online access, and start the server'), "
    "and underneath a one-line metric 'version: <blender_version_string> &middot; object: "
    "<created> &middot; render: <rendered path>'. "
    "End with END-RESPONSE."
)


_NEW_PROMPTS = (
    (75, BLENDER_FORGE_DEMO),
)


def add_blenderer_demo_prompt(apps, schema_editor):
    Prompt = apps.get_model('agent', 'Prompt')
    for prompt_id, content in _NEW_PROMPTS:
        Prompt.objects.update_or_create(
            idPrompt=prompt_id,
            defaults={'promptName': f'prompt-{prompt_id}', 'promptContent': content},
        )


def remove_blenderer_demo_prompt(apps, schema_editor):
    Prompt = apps.get_model('agent', 'Prompt')
    Prompt.objects.filter(idPrompt__in=[pid for pid, _ in _NEW_PROMPTS]).delete()


class Migration(migrations.Migration):
    dependencies = [
        ('agent', '0127_add_chat_agent_blenderer_tool'),
    ]

    operations = [
        migrations.RunPython(add_blenderer_demo_prompt, remove_blenderer_demo_prompt),
    ]
