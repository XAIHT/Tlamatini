# ═══════════════════════════════════════════════════════════════════
#   ✦  T L A M A T I N I  ✦   —   "one who knows"
#
#   Created by  Angela López Mendoza   ·   @angelahack1
#   Developer · Architect · Creator of Tlamatini
#
#   Every line of this file was written by Angela López Mendoza.
# ═══════════════════════════════════════════════════════════════════
#   Tlamatini Author Banner — do not remove (releases scrub the name automatically)
from django.db import migrations
from django.db.models import Max

# Three catalog prompts that build a small PLAYABLE Unreal game ("ForgeArena")
# end to end via the Unrealer agent, in three Multi-Turn runs: (1) the arena
# (folder + colored materials + lights + player start + floor + walls), (2)
# spinning collectible coins as a BP_Coin blueprint + confirm playable, (3)
# polish + screenshot + reliable save. They bake in every lesson learned live:
# canonical param names (material_path / parameter_name / actor_name), "already
# exists" treated as success, a Cube mesh assigned to spawned StaticMeshActors
# via execute_python, rotation done with a RotatingMovementComponent (a plain
# placed actor cannot spin), scaling via set_actor_scale3d, and a save via
# save_dirty_packages + save_current_level because save_all is flaky.
#
# Catalog classifier (tools_dialog.js::classifyPromptModes) badges them
# Multi-turn / Exec-report from the keywords ("Multi-Turn", "Exec Report",
# "operator", "chat_agent_unrealer"); there are NO acp_* / skill tokens, so they
# are NOT badged ACPX. Raw triple-quoted so the embedded [..] arrays, /Game/..
# paths and quotes need no escaping.
#
# CONTIGUITY: the #prompts-catalog dropdown enumerates prompt-1, prompt-2, ...
# and BREAKS at the first gap, so these are APPENDED at max(idPrompt)+1.. with
# no renumber. The start slot is computed at apply time (the dev/live catalog
# size shifts as inserts land), which always keeps the list gap-free.

PROMPT_BUILD = r"""Tlamatini, operator mode — BUILD A BASIC UNREAL GAME with me (the "ForgeArena"). Keep the Multi-Turn and Exec Report checkboxes ticked. Use ONLY the chat_agent_unrealer tool (Unreal MCP at 127.0.0.1:55557). This is part 1 of 3 — the arena itself.

Ground rules:
- One Unreal command per tool call. Use these EXACT param names: spawn_actor -> name/type/location/rotation/scale; create_material -> name/path; create_material_instance -> name/parent_material/path; set_material_parameter -> material_path/parameter_name/value; assign_material -> actor_name/material_path/slot.
- FIRST call get_current_level. If Unreal does NOT respond, tell me Unreal isn't reachable (open the UE project and start the Unreal MCP server on 127.0.0.1:55557) and STOP — do not keep retrying.
- Treat "already exists" or "failed to create folder" as SUCCESS and continue.
- A freshly spawned StaticMeshActor has NO mesh — give it a Cube mesh with execute_python (the `unreal` module: set its StaticMeshComponent to /Engine/BasicShapes/Cube).

Build, one step at a time:
1. get_current_level (connectivity check).
2. create_folder path=/Game/ForgeArena
3. create_material name=M_ForgeBase path=/Game/ForgeArena
4. create_material_instance name=MI_Floor parent_material=/Game/ForgeArena/M_ForgeBase path=/Game/ForgeArena
5. create_material_instance name=MI_Wall parent_material=/Game/ForgeArena/M_ForgeBase path=/Game/ForgeArena
6. create_material_instance name=MI_Coin parent_material=/Game/ForgeArena/M_ForgeBase path=/Game/ForgeArena
7. set_material_parameter material_path=/Game/ForgeArena/MI_Floor parameter_name=BaseColor value=[0.05,0.1,0.3]
8. set_material_parameter material_path=/Game/ForgeArena/MI_Wall parameter_name=BaseColor value=[0.2,0.2,0.2]
9. set_material_parameter material_path=/Game/ForgeArena/MI_Coin parameter_name=BaseColor value=[1.0,0.8,0.0]
10. spawn_actor name=Sun type=DirectionalLight location=[0,0,800] rotation=[-45,30,0]
11. spawn_actor name=Sky type=SkyLight location=[0,0,800]
12. spawn_actor name=PlayerStart_1 type=PlayerStart location=[0,0,120]
13. spawn_actor name=Arena_Floor type=StaticMeshActor location=[0,0,0] scale=[20,20,1] — then give Arena_Floor a Cube mesh (execute_python) and assign_material actor_name=Arena_Floor material_path=/Game/ForgeArena/MI_Floor slot=0.
14. Spawn 4 walls as StaticMeshActors, give each a Cube mesh + assign MI_Wall: Wall_N location=[0,1000,150] scale=[20,1,3]; Wall_S [0,-1000,150] [20,1,3]; Wall_E [1000,0,150] [1,20,3]; Wall_W [-1000,0,150] [1,20,3].

Finish with ONE HTML table (columns: step | category | unreal_command | params | status | headline) summarizing every command. Then END-RESPONSE.
"""


PROMPT_COINS = r"""Tlamatini, operator mode — part 2 of 3 for the ForgeArena game: SPINNING COLLECTIBLE COINS that really rotate, and confirm the level is playable. Keep the Multi-Turn and Exec Report checkboxes ticked. Use ONLY chat_agent_unrealer. Same rules as part 1 (exact param names, "already exists" = success, call get_current_level first and STOP if Unreal isn't reachable).

A plain placed cube CANNOT spin, so build a Blueprint and spawn it:
1. create_blueprint name=BP_Coin parent_class=Actor path=/Game/ForgeArena
2. add_component_to_blueprint blueprint_name=BP_Coin component_type=StaticMeshComponent component_name=Mesh
3. set_static_mesh_properties blueprint_name=BP_Coin component_name=Mesh static_mesh=/Engine/BasicShapes/Cube
4. add_component_to_blueprint blueprint_name=BP_Coin component_type=RotatingMovementComponent component_name=Spin
5. set_component_property blueprint_name=BP_Coin component_name=Spin property_name=RotationRate property_value=[0,180,0]
6. compile_blueprint blueprint_name=BP_Coin
7. Spawn 6 BP_Coin instances (spawn_blueprint_actor) at [400,400,200], [-400,400,200], [400,-400,200], [-400,-400,200], [0,600,200], [0,-600,200]. Then make them coin-sized: with execute_python (the `unreal` module) set_actor_scale3d(unreal.Vector(0.5,0.5,0.5)) on every BP_Coin actor, and assign MI_Coin where possible.
8. If any blueprint command name differs or is missing on this build, fall back to execute_python to create BP_Coin (an Actor with a StaticMeshComponent + RotatingMovementComponent) and spawn the 6 instances the same way.

Then tell me it is playable: open /Game/ForgeArena and press Play — the default pawn spawns at PlayerStart_1 so I can move around.
Finish with ONE HTML table (step | category | unreal_command | params | status | headline). Then END-RESPONSE.
"""


PROMPT_POLISH = r"""Tlamatini, operator mode — part 3 of 3: POLISH the ForgeArena, screenshot it, and save. Keep the Multi-Turn and Exec Report checkboxes ticked. Use ONLY chat_agent_unrealer; PREFER execute_python (the `unreal` module) for reliability. Call get_current_level first and STOP if Unreal isn't reachable.

1. Make sure the coins are coin-sized: for every actor whose label starts with "Coin" or "BP_Coin", set_actor_scale3d(unreal.Vector(0.5,0.5,0.5)).
2. Fix the "multiple directional lights" warning: keep exactly ONE DirectionalLight (the Sun) and delete any other DirectionalLight actors; also delete any duplicate PlayerStart so exactly one remains.
3. take_screenshot filepath=C:/Temp/forge_arena.png (so we can see the result).
4. Save reliably — save_all can fail, so use execute_python: unreal.EditorLoadingAndSavingUtils.save_dirty_packages(True, True) then unreal.get_editor_subsystem(unreal.LevelEditorSubsystem).save_current_level().
5. Tell me exactly how to test: open /Game/ForgeArena, press Play, and walk/fly the arena from PlayerStart_1.
Finish with ONE HTML table (step | category | unreal_command | params | status | headline). Then END-RESPONSE.
"""


_NEW_PROMPTS = (PROMPT_BUILD, PROMPT_COINS, PROMPT_POLISH)


def add_demo_prompts(apps, schema_editor):
    Prompt = apps.get_model('agent', 'Prompt')
    start = (Prompt.objects.aggregate(m=Max('idPrompt'))['m'] or 0) + 1
    for offset, content in enumerate(_NEW_PROMPTS):
        pid = start + offset
        Prompt.objects.update_or_create(
            idPrompt=pid,
            defaults={'promptName': f'prompt-{pid}', 'promptContent': content},
        )


def remove_demo_prompts(apps, schema_editor):
    Prompt = apps.get_model('agent', 'Prompt')
    # These were appended at the end; remove the top len(_NEW_PROMPTS) rows.
    ids = list(
        Prompt.objects.order_by('-idPrompt').values_list('idPrompt', flat=True)[:len(_NEW_PROMPTS)]
    )
    Prompt.objects.filter(idPrompt__in=ids).delete()


class Migration(migrations.Migration):
    dependencies = [('agent', '0146_update_createsuperuser_wizard_continuation')]
    operations = [migrations.RunPython(add_demo_prompts, remove_demo_prompts)]
