# ═══════════════════════════════════════════════════════════════════
#   ✦  T L A M A T I N I  ✦   —   "one who knows"
#
#   Created by  Angela López Mendoza   ·   @angelahack1
#   Developer · Architect · Creator of Tlamatini
#
#   Every line of this file was written by Angela López Mendoza.
# ═══════════════════════════════════════════════════════════════════
#   Tlamatini Author Banner — do not remove
"""RE-GROUP, RE-SORT and RE-NUMBER the Catalog of Prompts with NO GAPS (Angela,
2026-07-15, explicit request).

Migrations 0175/0176 grouped the catalog into 13 categories and DELETED the 13
duplicate ACPX demos (ids 40-52), which left a GAP in `idPrompt`. Angela's explicit
follow-up: "RE-GROUP THE PROMPTS, RE-SORT, WITH NO-GAPS THE Catalog of Prompts in
the DB." So this migration physically renumbers every Prompt row to a CONTIGUOUS
1..N, ordered by (category display-rank, current idPrompt) — the SAME order the
catalog UI already renders (views.py::PROMPT_CATEGORY_ORDER / list_prompts_view).
`promptName` is rewritten to match ('prompt-<n>').

⚠️ ONE-TIME, DELIBERATE OVERRIDE of the standing "NEVER renumber idPrompt" contract
(Angela authorised it directly). It is safe because NOTHING references a prompt by a
fixed number at runtime: `list_prompts_view` returns every visible row grouped by
`category`; the offline `tools_dialog.js` fallback probes prompt-1..N and is
gap-tolerant; `idPrompt` is not a foreign key from any other table. Only prose docs
mention specific numbers. AFTER this, the forward rule is unchanged: new prompts
still APPEND at max(idPrompt)+1 (which keeps the catalog contiguous until a delete).

Mechanics: `idPrompt` is the PRIMARY KEY, so a naive in-place renumber could collide.
We renumber in TWO phases — first park every row at a high, non-colliding offset in
the target order, then bring them down to 1..N in that same order.

Reverse: one-way (the original ids are not stored). Reverse is a no-op — the catalog
is already correct grouped/sorted; only the raw numbering differs.
"""
from django.db import migrations

# Category display order — MUST mirror views.py::PROMPT_CATEGORY_ORDER (beginner ->
# advanced -> specialized). Any untagged/unknown category falls into 'other' (last).
_CATEGORY_ORDER = [
    'getting_started', 'files_search', 'run_execute', 'code_gen', 'images',
    'agents_flows', 'acpx_skills', 'desktop_ui', 'games_3d', 'firmware_iot',
    'security_recon', 'messaging', 'media_voice', 'other',
]
_RANK = {key: i for i, key in enumerate(_CATEGORY_ORDER)}
_OTHER_RANK = _RANK['other']
_PARK_OFFSET = 1_000_000  # far above any real idPrompt — collision-free parking zone


def _rank(category):
    return _RANK.get((category or '').strip(), _OTHER_RANK)


def regroup_resort_no_gaps(apps, schema_editor):
    Prompt = apps.get_model('agent', 'Prompt')
    rows = list(Prompt.objects.all())
    if not rows:
        return
    # Stable target order: by category rank, then current idPrompt (preserves the
    # curated intra-category order).
    rows.sort(key=lambda p: (_rank(p.category), p.idPrompt))

    # Phase 1 — park every row at PARK_OFFSET + <target position> (all distinct and
    # far above any real id, so no PK collision with not-yet-moved rows).
    for target_pos, p in enumerate(rows, start=1):
        Prompt.objects.filter(idPrompt=p.idPrompt).update(idPrompt=_PARK_OFFSET + target_pos)

    # Phase 2 — bring them down to a contiguous 1..N in the SAME order, and fix the
    # promptName to match.
    for target_pos, _p in enumerate(rows, start=1):
        Prompt.objects.filter(idPrompt=_PARK_OFFSET + target_pos).update(
            idPrompt=target_pos, promptName=f'prompt-{target_pos}',
        )


class Migration(migrations.Migration):
    dependencies = [('agent', '0178_add_stm32_stepwise_blink_camera_prompts')]
    operations = [
        migrations.RunPython(regroup_resort_no_gaps, migrations.RunPython.noop),
    ]
