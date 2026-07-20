# ═══════════════════════════════════════════════════════════════════
#   ✦  T L A M A T I N I  ✦   —   "one who knows"
#   Created by  Angela López Mendoza · @angelahack1
# ═══════════════════════════════════════════════════════════════════
"""Catalog of Prompts — `sort_rank`: decouple DISPLAY ORDER from `idPrompt`.

WHY (Angela, 2026-07-20)
------------------------
Until now the order of the cards inside a section WAS `idPrompt` ascending
(views.list_prompts_view). Combined with the standing append-only rule ("never
renumber; add a new prompt at max(idPrompt)+1") that had one unavoidable
consequence: **every new prompt lands LAST in its section, forever.**

Migration 0180 proved it live — the Kali back-end SETUP WIZARD (the prompt that
must run BEFORE the Kalier demos 73/74/75 can work at all, and the only
Step-by-Step wizard in Security & Recon) got id 97 and was rendered dead last in
its own section. It also broke the `test_grouped_by_category_rank` invariant in
`test_prompt_catalog_contiguous.py`, because id 97 (security_recon, rank 10)
sorts after ids 82-96 (messaging rank 11 / media_voice rank 12).

`sort_rank` fixes the class of bug rather than the instance:

  * `idPrompt` keeps its job — a stable, contiguous, never-renumbered identity.
  * `sort_rank` owns WHERE the card is shown inside its section.
  * A new prompt is STILL appended at the next free idPrompt, and simply gets the
    rank of the slot it belongs in. **No renumber is ever required again.**

Ranks are seeded in steps of 10 starting at 20. The gaps are deliberate:
  * rank 10 is left FREE at the top of every section for the Step-by-Step opener
    (Angela's rule: the first prompt of a section is a guided wizard),
  * the 9-wide gap between neighbours lets a future prompt slot between two
    existing cards without touching either.

`sort_rank = 0` means UNRANKED and deliberately sorts LAST in its section (see
views.list_prompts_view), so a future migration that forgets to set a rank
degrades to "appears at the end" — never to "hijacks the section opener".

ORDER SEEDED HERE
-----------------
Least-complex / least-prerequisite first, then ascending, per the 2026-07-20
section-by-section audit (each section independently audited AND adversarially
re-checked). Guiding rules, in order of force:
  1. a genuine Step-by-Step wizard opens its section (getting_started 1,
     firmware_iot 70+69, security_recon 97, messaging 83);
  2. a prerequisite-establishing prompt precedes the prompts that need it
     (games_3d 56 scaffolds the UE project; messaging 86 adds the contact that
     87/88/89 send to);
  3. zero-prerequisite before hardware/API-key/external-server prompts;
  4. read-only before state-changing;
  5. tool FAMILIES stay contiguous and ascend as blocks (this is why
     firmware_iot stays family-major STM32 → ESP32 → Arduino → ESPHome rather
     than being re-cut tier-major, and why the whole change stays minimal).

Reverse sets every rank back to 0, which restores idPrompt ordering exactly.
NOTE: this migration does NOT renumber any primary key — that is precisely what
`sort_rank` makes unnecessary.
"""
from django.db import migrations, models

# category -> ids in the DISPLAY order the section should read (simple → advanced).
_SECTION_ORDER = {
    # Wizard (1) first — already correct. Then the three zero-prerequisite
    # one-liners (6 time, 7 metrics, 8 dirs) BEFORE the four prompts that only
    # work once the user has run Context ▸ Set directory as context (2, 5, 3, 4),
    # ascending from enumeration to a whole-codebase security audit.
    'getting_started': [1, 6, 7, 8, 2, 5, 3, 4],
    # 9/10 are bare Files-Search one-liners. Then the three wrapped-agent demos
    # in capability order: Globber (glob) → Grepper (regex) → Editor (mutates an
    # existing file). Discovery precedes mutation — the order agents.md itself
    # describes ("Globber = the enumeration step ahead of a Grepper / Editor").
    'files_search': [9, 10, 13, 12, 11],
    # Two bare shell one-liners (15 ping, 16 netstat) before 14, which needs a
    # pre-existing cat_art.py to execute. 17/18 already correctly last.
    'run_execute': [15, 16, 14, 17, 18],
    # Was almost exactly inverted: 19 (whole-project Java 8→17 + Maven migration,
    # the only state-changing, prerequisite-heavy prompt) opened the section.
    # Now: 22 (add JavaDoc to ONE pasted file, purely additive) → 20 (implement X)
    # → 21 (whole Bootstrap page) → 19 (the migration).
    'code_gen': [22, 20, 21, 19],
    # 23 introduces the Qwen vision path; 25 reuses it; 24 is the same prompt on
    # Opus and needs an ANTHROPIC_API_KEY, so it follows 25. 26 (Shoter →
    # triple-model interpret) is the only multi-agent prompt and stays last.
    'images': [23, 25, 24, 26],
    # UNCHANGED: the lifecycle reads parametrize+start → observe → stop, then the
    # multi-agent demos ascend local → web → monitoring → flow-making. The
    # adversarial re-check upheld the existing order against the audit's swap.
    'agents_flows': [27, 28, 29, 30, 31, 32, 33],
    # Only the one load-bearing fix: 38 (Auditor's Replay — spawns NO external
    # CLI) before 37 (End-to-End Pipeline — spawns a real gemini child, writes a
    # file, fires a notifier). 41 stays last: it is the section's only External
    # MCP prompt and the title reads "ACPX, Skills & MCPs".
    'acpx_skills': [34, 35, 36, 38, 37, 39, 40, 41],
    # 46 (Desktop Director) needs no third-party install; 44/45/47 all require
    # `pip install playwright && playwright install` + internet. Moving 46 to
    # position 3 both fixes the prerequisite order AND stops it splitting the
    # Playwrighter family in half. One swap, nothing else moves.
    'desktop_ui': [42, 43, 46, 44, 45, 47],
    # 52 (Blender: 4 calls, graceful degradation) is the lightest prompt and its
    # own one-prompt family. 56 scaffolds the UE 5.8 project the rest of the
    # section drives, so it precedes them. Then Unreal ascends basic (49) →
    # medium (50) → full-surface (48) → advanced/Python (51) → the dependent
    # ForgeArena trilogy 53 → 54 → 55, which must stay in that order.
    'games_3d': [52, 56, 49, 50, 48, 51, 53, 54, 55],
    # Step-by-Step wizards first (70 uses the board's ON-BOARD ST-Link — no
    # external dongle to wire — so it is gentler than 69). Then FAMILY-MAJOR is
    # preserved exactly as the section already had it: STM32 → ESP32 → Arduino →
    # ESPHome, each family already genesis → blinky → HIL. 68 (a single
    # scaffold_build_flash call needing no board) joins the STM32 family as its
    # simplest member instead of trailing the whole section.
    'firmware_iot': [70, 69, 68, 57, 58, 59, 60, 61, 62, 63, 64, 65, 66, 67],
    # 97 (Kali back-end setup wizard, Step-by-Step) opens the section per
    # Angela's rule. Then local-only code checks (71 Reviewer, 72 Analyzer), then
    # Nmapper (local nmap, no server), then Discoverer (78's CVE query is 100%
    # passive so it precedes 77's authorized active probe), then the Kalier
    # demos, which need the Kali VM + MCP-Kali-Server that 97 sets up.
    'security_recon': [97, 71, 72, 79, 80, 81, 76, 78, 77, 73, 74, 75],
    # 83 (Telegrammer wizard, Step-by-Step, needs ONE asset) opens; 84 (WhatsApp
    # wizard, two Meta assets) follows; 85 is the read-only doctor; 86 adds the
    # contact that 87/88/89 send to; then the Zavu family, wizard-before-probe
    # for consistency with the Telegram family (91 → 90 → 92 → 93). 82 (the
    # legacy raw api_id/api_hash Parametrizer call) drops to the tail — it was
    # opening the section.
    'messaging': [83, 84, 85, 86, 87, 88, 89, 91, 90, 92, 93, 82],
    # UNCHANGED: TTS (94) → STT (95) → the two-agent Video-Analyzer loop (96).
    'media_voice': [94, 95, 96],
}

_FIRST_RANK = 20   # rank 10 stays FREE for each section's Step-by-Step opener
_STEP = 10
_TRAILING_BASE = 100_000  # any prompt not listed above sorts after the listed ones


def seed_sort_rank(apps, schema_editor):
    Prompt = apps.get_model('agent', 'Prompt')
    ranked_ids = set()

    for _category, ids in _SECTION_ORDER.items():
        rank = _FIRST_RANK
        for pid in ids:
            # update() (not save()) so a DB missing this id is a silent no-op
            # rather than an exception — the migration must never block a user's
            # upgrade just because their catalog differs.
            if Prompt.objects.filter(idPrompt=pid).update(sort_rank=rank):
                ranked_ids.add(pid)
            rank += _STEP

    # Fail-open: anything the map did not cover (a prompt added by a branch, a
    # user-authored row) still gets a deterministic rank at the END of its
    # section, ordered by idPrompt. Nothing is ever left at 0 by this migration.
    for row in Prompt.objects.exclude(idPrompt__in=ranked_ids).values('idPrompt'):
        Prompt.objects.filter(idPrompt=row['idPrompt']).update(
            sort_rank=_TRAILING_BASE + row['idPrompt']
        )


def clear_sort_rank(apps, schema_editor):
    # Reverse: every rank back to 0 → views.list_prompts_view falls through to
    # idPrompt ordering, i.e. exactly the pre-0181 display order.
    apps.get_model('agent', 'Prompt').objects.update(sort_rank=0)


class Migration(migrations.Migration):

    dependencies = [('agent', '0180_add_kalier_setup_wizard_prompt')]

    operations = [
        migrations.AddField(
            model_name='prompt',
            name='sort_rank',
            field=models.IntegerField(default=0),
        ),
        migrations.RunPython(seed_sort_rank, clear_sort_rank),
    ]
