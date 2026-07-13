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


# Surface Angela's Visual-Studio-2026 usage tip in the Unreal-scaffold Catalog prompt that
# 0173 seeded: in VS, build the GAME PROJECT only — never 'Build Solution'. A full-solution
# build also compiles unrelated engine targets (LiveLinkHub, test harnesses, …) that fail
# for reasons that have nothing to do with the game and just fill the Error List with red
# herrings (verified on Angela's own AngysLastChance build; see its fix.md "Extra Note").
#
# 0173's canonical DEMO already carries the new wording, so a FRESH database seeds it
# directly. This migration patches databases that had ALREADY applied 0173 (where re-running
# 0173 is a no-op) by an in-place string swap of the step-(b) sentence — it does NOT add a
# new Prompt row, so it does not touch idPrompt contiguity. Matched by a stable marker and
# idempotent: a row that already has the new sentence is left untouched.
_MARKER = "SCAFFOLD A NEW UNREAL ENGINE 5.8"

_OLD_B = (
    "(b) Build the solution — the FIRST build compiles the UnrealMCP plugin and takes "
    "several minutes;"
)
_NEW_B = (
    "(b) build MY PROJECT ONLY, NOT the whole solution "
    "— in Solution Explorer right-click the project named after my game (under the 'Games' "
    "folder) and choose Build; do NOT use 'Build Solution', because a full-solution build "
    "also compiles unrelated engine targets (LiveLinkHub, test harnesses, etc.) that fail "
    "for reasons that have nothing to do with my game and just clutter the Error List with "
    "red herrings. This first project build compiles the UnrealMCP plugin and takes several "
    "minutes;"
)


def add_build_project_tip(apps, schema_editor):
    Prompt = apps.get_model('agent', 'Prompt')
    for p in Prompt.objects.filter(promptContent__contains=_MARKER):
        if _OLD_B in p.promptContent and _NEW_B not in p.promptContent:
            p.promptContent = p.promptContent.replace(_OLD_B, _NEW_B)
            p.save(update_fields=['promptContent'])


def remove_build_project_tip(apps, schema_editor):
    Prompt = apps.get_model('agent', 'Prompt')
    for p in Prompt.objects.filter(promptContent__contains=_MARKER):
        if _NEW_B in p.promptContent:
            p.promptContent = p.promptContent.replace(_NEW_B, _OLD_B)
            p.save(update_fields=['promptContent'])


class Migration(migrations.Migration):
    dependencies = [('agent', '0173_add_unreal_scaffold_demo_prompt')]
    operations = [migrations.RunPython(add_build_project_tip, remove_build_project_tip)]
