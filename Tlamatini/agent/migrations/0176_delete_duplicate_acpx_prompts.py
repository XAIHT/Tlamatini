# ═══════════════════════════════════════════════════════════════════
#   ✦  T L A M A T I N I  ✦   —   "one who knows"
#
#   Created by  Angela López Mendoza   ·   @angelahack1
#   Developer · Architect · Creator of Tlamatini
#
#   Every line of this file was written by Angela López Mendoza.
# ═══════════════════════════════════════════════════════════════════
#   Tlamatini Author Banner — do not remove
"""PHYSICALLY DELETE the 13 duplicate ACPX catalog prompts (Angela, 2026-07-14).

Migration 0175 grouped the catalog and HID the 13 duplicate ACPX demos (ids
40-52) rather than deleting them, to keep `idPrompt` contiguous. Angela's follow-
up decision was explicit: "I must get rid completely of the duplicates!" — so we
now DELETE those rows outright.

This is a normal FORWARD data change (the sanctioned way to remove data — never a
git-history rewrite). It leaves a GAP at ids 40-52; that is fine because:
  * the primary catalog loader (`views.list_prompts_view` -> `/agent/list_prompts/`)
    returns whatever rows exist, gaps and all;
  * the OFFLINE fallback probe in `tools_dialog.js` was made GAP-TOLERANT in the
    same change (it skips a missing id instead of stopping at it).

So the old "idPrompt must stay contiguous" contract is relaxed: gaps are allowed.
Ids are NEVER renumbered — every surviving prompt keeps its id (33-39 are the
kept, most-portable version of each of the 7 ACPX demos), so nothing that refers
to a prompt by number breaks.
"""

from django.db import migrations

# The 13 duplicate ACPX demos: the "banner" (40-45) and "Gemini-edition" (46-52)
# re-runs of the 7 concepts already covered by 33-39.
_DELETE_IDS = list(range(40, 53))  # 40..52 inclusive


def delete_dups(apps, schema_editor):
    Prompt = apps.get_model("agent", "Prompt")
    Prompt.objects.filter(idPrompt__in=_DELETE_IDS).delete()


class Migration(migrations.Migration):
    dependencies = [("agent", "0175_prompt_category_and_dedup")]

    # Irreversible: the deleted rows were exact duplicates of 33-39, so there is
    # nothing unique to restore. Reverse is a no-op.
    operations = [
        migrations.RunPython(delete_dups, migrations.RunPython.noop),
    ]
