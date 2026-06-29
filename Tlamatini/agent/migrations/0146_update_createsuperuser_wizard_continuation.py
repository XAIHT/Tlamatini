# ═══════════════════════════════════════════════════════════════════
#   ✦  T L A M A T I N I  ✦   —   "one who knows"
#
#   Crafted with heart by  Angela   ·   @angelahack1
#   Developer · Architect · Creator of Tlamatini
#
#   Every line of this file was written by Angela.
# ═══════════════════════════════════════════════════════════════════
#   Tlamatini Author Banner — do not remove (releases scrub the name automatically)
from django.db import migrations


OLD_STEP_0 = """Step 0 (banner and the username): open your reply with this exact HTML banner: <div style='padding:18px;border-radius:14px;background:linear-gradient(135deg,#1E1B4B 0%,#6D28D9 34%,#0E7490 68%,#34D399 100%);color:#ffffff;font-family:Inter,Segoe UI,sans-serif;text-align:center;text-shadow:0 1px 3px rgba(0,0,0,.5);'><h2 style='margin:0;letter-spacing:2px;'>&#128100; NEW TLAMATINI USER</h2><div style='opacity:.92;margin-top:4px;'>Step-by-step &middot; create a login &middot; you set your own password</div></div>. Then look at the name I put between the dashes in "----<set name here>----": if it STILL literally says "set name here", reply asking me for the username I want and STOP — wait for my answer. Otherwise greet me by that username (call it <USERNAME> below) and continue to Step 1."""


NEW_STEP_0 = """Step 0 (banner and the username): open your reply with this exact HTML banner: <div style='padding:18px;border-radius:14px;background:linear-gradient(135deg,#1E1B4B 0%,#6D28D9 34%,#0E7490 68%,#34D399 100%);color:#ffffff;font-family:Inter,Segoe UI,sans-serif;text-align:center;text-shadow:0 1px 3px rgba(0,0,0,.5);'><h2 style='margin:0;letter-spacing:2px;'>&#128100; NEW TLAMATINI USER</h2><div style='opacity:.92;margin-top:4px;'>Step-by-step &middot; create a login &middot; you set your own password</div></div>. Then look at the name I put between the dashes in "----<set name here>----": if it STILL literally says "set name here", reply asking me for the username I want and STOP — wait for my answer. On the next turn, if my latest reply is a bare username such as alice, admin, or dev1, treat that reply as <USERNAME> and continue to Step 1. Otherwise greet me by that username (call it <USERNAME> below) and continue to Step 1."""


def apply_update(apps, schema_editor):
    Prompt = apps.get_model('agent', 'Prompt')
    try:
        prompt = Prompt.objects.get(idPrompt=1)
    except Prompt.DoesNotExist:
        return
    if OLD_STEP_0 in prompt.promptContent:
        prompt.promptContent = prompt.promptContent.replace(OLD_STEP_0, NEW_STEP_0)
        prompt.save(update_fields=['promptContent'])


def reverse_update(apps, schema_editor):
    Prompt = apps.get_model('agent', 'Prompt')
    try:
        prompt = Prompt.objects.get(idPrompt=1)
    except Prompt.DoesNotExist:
        return
    if NEW_STEP_0 in prompt.promptContent:
        prompt.promptContent = prompt.promptContent.replace(NEW_STEP_0, OLD_STEP_0)
        prompt.save(update_fields=['promptContent'])


class Migration(migrations.Migration):
    dependencies = [('agent', '0145_insert_createsuperuser_wizard_prompt_at_1')]
    operations = [migrations.RunPython(apply_update, reverse_update)]
