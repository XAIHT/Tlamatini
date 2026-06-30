# ═══════════════════════════════════════════════════════════════════
#   ✦  T L A M A T I N I  ✦   —   "one who knows"
#
#   Created by  Angela López Mendoza   ·   @angelahack1
#   Developer · Architect · Creator of Tlamatini
#
#   Every line of this file was written by Angela López Mendoza.
# ═══════════════════════════════════════════════════════════════════
#   Tlamatini Author Banner — do not remove (releases scrub the name automatically)
"""De-duplicate the Zavuerer catalog-of-prompts setup wizards.

Migrations 0162 and 0163 BOTH seeded a "set up Zavuerer step-by-step" wizard:
  - 0162 SETUP_PROMPT   — a short 3-step setup wizard, and
  - 0163 GET_KEY_WIZARD — the fuller 6-step hold-your-hand wizard.
Two near-identical setup cards therefore showed up in the #prompts-catalog modal.

This collapses them to ONE: it keeps the full 6-step content, moves it into the
EARLIER of the two slots (so the catalog stays contiguous — the dropdown breaks
at the first gap), and deletes the later duplicate slot (the 6-step wizard sat in
the LAST slot, so removing it leaves no gap). Matched by a distinctive opening
substring so it works on any install regardless of the exact idPrompt values, and
is a safe no-op if only one (or neither) wizard is present.
"""
from django.db import migrations

# Distinctive opening phrases unique to each wizard (substring match — robust to
# whitespace drift; never collides with the other three Zavuerer prompts).
SETUP_MARKER = "please set up **Zavuerer** with me ONE step at a time"
GETKEY_MARKER = "hold my hand and set up **Zavuerer** with me from zero"


def dedup_setup_wizards(apps, schema_editor):
    Prompt = apps.get_model('agent', 'Prompt')
    setup = Prompt.objects.filter(promptContent__contains=SETUP_MARKER).order_by('idPrompt').first()
    getkey = Prompt.objects.filter(promptContent__contains=GETKEY_MARKER).order_by('idPrompt').first()
    if not (setup and getkey):
        return  # only one (or neither) wizard present — nothing to de-duplicate
    good_content = getkey.promptContent          # keep the full 6-step wizard text
    keep_id = min(setup.idPrompt, getkey.idPrompt)  # earlier slot stays (gap-free)
    drop_id = max(setup.idPrompt, getkey.idPrompt)  # later slot (the last one) goes
    Prompt.objects.filter(idPrompt=keep_id).update(promptContent=good_content)
    Prompt.objects.filter(idPrompt=drop_id).delete()


class Migration(migrations.Migration):
    dependencies = [('agent', '0163_add_zavuerer_get_key_wizard_prompt')]
    operations = [migrations.RunPython(dedup_setup_wizards, migrations.RunPython.noop)]
