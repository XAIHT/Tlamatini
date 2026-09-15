# ══════════════════════════════════════════════════════════════════════════════
#   ✦  T L A M A T I N I  ✦   —   "one who knows"
#
#   Created by  Angela López Mendoza   ·   @angelahack1
#   Developer · Architect · Creator of Tlamatini
#
#   Every line of this file was written by Angela López Mendoza.
# ══════════════════════════════════════════════════════════════════════════════
#   Tlamatini Author Banner — do not remove (releases scrub the name automatically)
"""Catalog of Prompts — the two PPTXer cards (Angela, 2026-09-14).

PPTXer is Multi-Turn-capable, so it is INCOMPLETE without at least one catalog
prompt (``create_new_agent.md`` Step 7.8, a hard completion gate). Two are
seeded because PPTXer has two genuinely different audiences and one card cannot
show both: a plain business deck, and the loud gaming/marketing deck it was
actually built for.

Contract compliance, deliberately all of it:

  * APPEND-ONLY ids. 0201 left the catalog at 122, so these are **123** and
    **124** — appended, never renumbered.

  * ``category='documents'`` — the section PDFer's six cards and LaTeXer's four
    already live in. PPTXer is the third member of the document-authoring
    family and belongs beside them, not in a section of its own.

  * ``sort_rank`` 56 and 58, and NOT the next free slot at 100. The section is
    ordered least-complex → most-complex and zero-setup → prerequisite-bearing:
    PDFer occupies 10-55 and needs nothing installed; LaTeXer occupies 60-90 and
    REQUIRES MiKTeX. PPTXer needs nothing installed either (python-pptx already
    ships), so it sits with the zero-setup half — after PDFer, before LaTeXer.
    That also keeps ``test_latexer_prompts_sit_after_pdfer_in_the_documents_section``
    satisfied and each tool family contiguous. Ranks are seeded in tens
    precisely to leave insertion room like this; rank 10 stays RESERVED for the
    section's existing Step-by-Step opener (prompt 109), and ranks are unique
    within a section.

  * Parameter grammar v1.44.0: ``[[ ... — OPTIONAL, default: X ]]`` collected at
    the TOP with the unfilled-guard sentence beneath, so a one-click demo still
    runs on the stated defaults; ``< >`` marks REPORT slots only, never inputs.
    No hardcoded scratch path (Rules 15/16) — PPTXer writes to its own
    Documents folder.

  * SAFE and repeatable: each card writes ONE new .pptx with an explicit
    non-colliding name into PPTXer's own output folder, mutates nothing else,
    and needs no network, no key and no installation. The daily chat test may
    run them.

  * CLASSIFIER MODES: each card's closing PRE-FLIGHT line names the
    **Multi-Turn** and **Exec report** checkboxes only, so
    ``tools_dialog.js::classifyPromptModes`` badges them Multi-turn +
    Exec-report and clicking one ticks exactly those two. Neither card contains
    an ``acp_*`` token or the hyphenated "step-by-step" token, either of which
    would wrongly tick ACPX / Step-by-Step.

Reverse deletes exactly these two rows.
"""
from django.db import migrations


PPTXER_SIMPLE = (
    "<div style=\"background:linear-gradient(135deg,#0B1F3A 0%,#5A1FB8 38%,"
    "#EC4899 70%,#22D3EE 100%);color:#ffffff;padding:10px 14px;"
    "border-radius:8px;font-weight:600;\">🖼️ PPTXer — turn an answer into a "
    "real presentation</div>\n\n"
    "FILL IN (optional — leave them exactly as they are for a one-click demo):\n"
    "  [[ SUBJECT — OPTIONAL, default: \"How Tlamatini builds a presentation\" ]]\n"
    "  [[ BRAND COLOUR — OPTIONAL, default: #5A1FB8 ]]\n"
    "If you left those unfilled, use the defaults exactly as written above and "
    "do not ask me for them.\n\n"
    "Tlamatini, please do this in order:\n\n"
    "1. Write me a short, well-structured briefing on the SUBJECT — a title, "
    "three or four sections, a few bullets each, and one small table. Keep it "
    "under 400 words.\n\n"
    "2. Then call chat_agent_pptxer ONCE, passing that briefing VERBATIM as "
    "input_text, with predominant_color set to the BRAND COLOUR and "
    "filename='tlamatini_briefing.pptx'. Do NOT set nuance — I want to see "
    "which treatment PPTXer picks on its own.\n\n"
    "3. When it finishes, report back plainly:\n"
    "   · the full path of the .pptx it wrote            → <path>\n"
    "   · how many slides it made                        → <slide_count>\n"
    "   · which treatment it chose, and why              → <nuance>\n"
    "   · which display font it used                     → <font_display>\n"
    "   · whether the layout was verified CLEAN          → <layout_clean>\n"
    "   · and whether that verdict came from PowerPoint's own rendering "
    "→ <ground_truth>\n\n"
    "That last point is the one I care about: PPTXer re-opens the deck it just "
    "wrote and LOOKS at it. If layout_clean is true AND ground_truth is true, "
    "tell me so in plain words — it means the slides were measured on the same "
    "pixels an audience would see, not merely written. If it reports findings "
    "instead, read them out; do not call the deck clean.\n\n"
    "PRE-FLIGHT: tick Multi-Turn and Exec report. Nothing else is needed — no "
    "network, no API key, no installation. End with END-RESPONSE."
)


PPTXER_GAMING = (
    "<div style=\"background:linear-gradient(135deg,#04060C 0%,#7B2FF7 34%,"
    "#F72585 66%,#00F0FF 100%);color:#ffffff;padding:10px 14px;"
    "border-radius:8px;font-weight:600;\">🎮 PPTXer — the same deck, two "
    "different worlds</div>\n\n"
    "FILL IN (optional — leave them exactly as they are for a one-click demo):\n"
    "  [[ GAME OR PRODUCT NAME — OPTIONAL, default: \"Nexus Protocol\" ]]\n"
    "If you left that unfilled, use the default exactly as written above and do "
    "not ask me for it.\n\n"
    "Tlamatini, this one shows what PPTXer is really for. Please:\n\n"
    "1. Invent a short season-launch deck for the GAME OR PRODUCT NAME — a "
    "title, a 'What Changed' section with four bullets, a 'By The Numbers' "
    "section written as four lines in the form NUMBER then LABEL (for example "
    "'3.4M Registered players', '12ms Median server latency'), a small pricing "
    "table, and one short quote from a player. Keep it tight; a slide is not a "
    "page.\n\n"
    "2. Call chat_agent_pptxer with that content as input_text, "
    "nuance='esports_tournament', predominant_color='#12E2A3', "
    "filename='launch_esports.pptx'.\n\n"
    "3. Call chat_agent_pptxer a SECOND time with the SAME input_text, but "
    "nuance='cyberpunk_tech', predominant_color='#00F0FF', "
    "filename='launch_cyberpunk.pptx'.\n\n"
    "4. Then compare them for me. Same words, two different decks — tell me "
    "which display typeface each one chose, what the two palettes came out as, "
    "which ornament each used, and whether BOTH were verified clean:\n"
    "   · esports    → <font_display>, <palette>, <layout_clean>\n"
    "   · cyberpunk  → <font_display>, <palette>, <layout_clean>\n\n"
    "Notice what PPTXer did with the 'By The Numbers' lines: four parallel "
    "NUMBER-then-LABEL bullets are promoted automatically into big stat tiles, "
    "because that is what they are. Tell me if that happened.\n\n"
    "PRE-FLIGHT: tick Multi-Turn and Exec report. Both decks are written to "
    "PPTXer's own Documents folder under names that will not collide with "
    "anything, so this is safe to run as often as you like. End with "
    "END-RESPONSE."
)


_NEW_PROMPTS = (
    (123, 56, PPTXER_SIMPLE),
    (124, 58, PPTXER_GAMING),
)


def add_pptxer_demo_prompts(apps, schema_editor):
    Prompt = apps.get_model('agent', 'Prompt')
    for prompt_id, rank, content in _NEW_PROMPTS:
        Prompt.objects.update_or_create(
            idPrompt=prompt_id,
            defaults={
                'promptName': 'prompt-%d' % prompt_id,
                'promptContent': content,
                'category': 'documents',
                'sort_rank': rank,
            },
        )


def remove_pptxer_demo_prompts(apps, schema_editor):
    Prompt = apps.get_model('agent', 'Prompt')
    Prompt.objects.filter(
        idPrompt__in=[prompt_id for prompt_id, _rank, _content in _NEW_PROMPTS]
    ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('agent', '0203_add_chat_agent_pptxer_tool'),
    ]

    operations = [
        migrations.RunPython(add_pptxer_demo_prompts, remove_pptxer_demo_prompts),
    ]
