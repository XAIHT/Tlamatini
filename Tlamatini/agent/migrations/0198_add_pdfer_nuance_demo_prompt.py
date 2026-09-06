# ═══════════════════════════════════════════════════════════════════
#   ✦  T L A M A T I N I  ✦   —   "one who knows"
#
#   Created by  Angela López Mendoza   ·   @angelahack1
#   Developer · Architect · Creator of Tlamatini
#
#   Every line of this file was written by Angela López Mendoza.
# ═══════════════════════════════════════════════════════════════════
#   Tlamatini Author Banner — do not remove (releases scrub the name automatically)
"""Catalog of Prompts — the PDFer NUANCE demo (Angela, 2026-09-06).

PDFer's 2026-09 overhaul gave it two new parameters — ``nuance`` and
``predominant_color`` — and the ability to read a document and decide how it
should LOOK before rendering it. None of that is discoverable from the five
existing PDFer cards, which were written when every PDF came out in the same
brown scheme and the same font. This card is the one that shows it.

It deliberately renders the SAME content TWICE, with the treatment as the only
variable, because that is the demonstration: the point is not "PDFer can make a
dark PDF", it is "PDFer decides, and you can overrule it".

Contract compliance (all of it, deliberately):
  * APPEND-ONLY id. 0197 left the catalog at 119, so this is **120** — appended,
    never renumbered (``test_ids_are_contiguous_1_to_n_no_gaps``).
  * ``category='documents'`` — the section PDFer's other five cards and
    LaTeXer's four already live in.
  * ``sort_rank = 55`` — and NOT the next free slot at 100, which is what a
    naive "append at the end" would have chosen. The section holds PDFer at
    10-50 and LaTeXer at 60-90, and
    ``test_latexer_prompts_sit_after_pdfer_in_the_documents_section`` enforces
    Angela's rule that **every PDFer card must precede every LaTeXer card**:
    PDFer needs nothing installed, LaTeXer needs MiKTeX, and a section reads
    zero-setup before prerequisite-bearing. This is a PDFer card, so it belongs
    with the PDFer family — the ranks are seeded in steps of ten precisely to
    leave insertion room like this. 55 places it last among the PDFer cards
    (it is the most complex of them: two renders and a comparison) while
    keeping the tool families contiguous. Rank 10 stays RESERVED for the
    section's Step-by-Step opener; ranks are unique within a section
    (``test_ranks_are_unique_within_a_section``).
  * Parameter grammar v1.44.0: ``[[ ... — OPTIONAL, default: X ]]`` collected at
    the TOP with the unfilled-guard sentence beneath, so a one-click demo still
    runs; ``< >`` marks REPORT slots only, never inputs. No hardcoded scratch
    path (Rules 15/16) — PDFer writes to its own Documents folder.
  * SAFE and repeatable: it writes two new PDFs with explicit non-colliding
    names into PDFer's own output folder, mutates nothing else, needs no
    network, no key and no installation.
  * CLASSIFIER MODES: the closing PRE-FLIGHT line names the **Multi-Turn** and
    **Exec report** checkboxes only, so ``classifyPromptModes``
    (``tools_dialog.js``) badges the card Multi-turn + Exec-report and clicking
    it ticks exactly those two. No ``acp_*`` tool and no "step-by-step" wording
    appears, either of which would wrongly tick ACPX / Step-by-Step.

Reverse deletes exactly this one row.
"""
from django.db import migrations

NUANCE_DEMO = (
    "<div style=\"background:linear-gradient(135deg,#07090F 0%,#1E3A8A 40%,"
    "#38BDF8 70%,#22D3EE 100%);color:#ffffff;padding:10px 14px;"
    "border-radius:8px;font-weight:600;\">📕 PDFer — the same words, two "
    "different documents</div>\n\n"
    "FILL IN (optional — leave them exactly as they are for a one-click "
    "demo):\n"
    "  · A colour for the second document: "
    "[[ predominant_color — OPTIONAL, default: #B4451F ]]\n"
    "  · A treatment to force on the second document: "
    "[[ nuance — OPTIONAL, default: academic_paper ]]\n"
    "If you left the blanks above untouched, use the stated defaults and run "
    "anyway — do not ask me to fill them in.\n\n"
    "Tlamatini, I want to see PDFer CHOOSE a design, and then see me overrule "
    "it. Render the SAME content twice with chat_agent_pdfer, changing "
    "nothing but the treatment.\n\n"
    "Use this content for BOTH documents, exactly as written:\n\n"
    "---\n"
    "# Confinement Physics of the Spherical Tokamak\n\n"
    "A tokamak confines a deuterium-tritium plasma using a toroidal magnetic "
    "field of roughly 5 T combined with a poloidal field induced by a 15 MA "
    "plasma current. The superconducting magnets operate at 4 K, cooled by "
    "supercritical helium.\n\n"
    "## Measured parameters\n\n"
    "| Parameter | Symbol | Value | Unit | Notes |\n"
    "|---|---|---|---|---|\n"
    "| Toroidal field | B_t | 5.3 | T | at the magnetic axis |\n"
    "| Plasma current | I_p | 15.0 | MA | flat-top |\n"
    "| Confinement time | tau_E | 3.7 | s | H-mode, ELMy |\n"
    "| Stored magnetic energy | W_mag | 40 | GJ | quench-relevant |\n\n"
    "## Diagnostics\n\n"
    "The quench detector is configured through "
    "`C:/Users/angel/AppData/Local/Programs/Tlamatini/config/"
    "quench_detector.yaml` and validated against "
    "https://raw.githubusercontent.com/XAIHT/Tlamatini/main/docs/plasma/"
    "quench.json\n\n"
    "**Warning:** a quench deposits 40 GJ in milliseconds.\n"
    "---\n\n"
    "**DOCUMENT 1 — let PDFer decide.** Call chat_agent_pdfer with "
    "mode='markdown', that content as input_text, "
    "title='Confinement Physics of the Spherical Tokamak', "
    "filename='tokamak_auto.pdf', and NOTHING about the appearance. Do not "
    "pass nuance and do not pass predominant_color: I want to see what it "
    "picks on its own.\n\n"
    "**DOCUMENT 2 — overrule it.** Call chat_agent_pdfer again with the SAME "
    "content and title, filename='tokamak_forced.pdf', plus the nuance and "
    "predominant_color from the fill-in block above.\n\n"
    "Then tell me, in plain language and in a small HTML table:\n"
    "  · what treatment PDFer chose by itself, and how sure it was → "
    "<nuance / nuance_confidence / nuance_source>\n"
    "  · what the two palettes came out as → <palette and predominant_color "
    "for each>\n"
    "  · which typefaces each document was set in → <font_pairing for each>\n"
    "  · whether it decided decoration was safe here → <decorations>\n"
    "  · **whether the layout was verified clean** — PDFer re-opens each "
    "finished PDF and measures the real letters on the page for overlapping "
    "text and anything running off the sheet → <layout_clean and overlaps for "
    "each>\n"
    "  · the two files it wrote → <output_path for each>\n\n"
    "Pay attention to that table in the content: it holds a Windows path and "
    "a long URL, which is exactly the shape that used to print across the "
    "next column. Confirm from the audit whether it did.\n\n"
    "PRE-FLIGHT: tick ONLY the Multi-Turn and Exec report checkboxes. Use "
    "ONLY chat_agent_pdfer — no shell, no Python, no other agent. Nothing here "
    "needs the internet, a key or an installation. End with END-RESPONSE."
)

# (idPrompt, sort_rank, promptContent) — the id is APPENDED after 119 (0197) and
# never renumbered; the RANK is 55, which slots this card in with the other
# PDFer cards (10-50) and BEFORE LaTeXer's (60-90) rather than at the end of the
# section. See the module docstring: ids append, ranks are placed.
_NEW_PROMPTS = (
    (120, 55, NUANCE_DEMO),
)


def add_demo_prompts(apps, schema_editor):
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


def remove_demo_prompts(apps, schema_editor):
    Prompt = apps.get_model('agent', 'Prompt')
    Prompt.objects.filter(
        idPrompt__in=[prompt_id for prompt_id, _rank, _c in _NEW_PROMPTS]
    ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('agent', '0197_add_netspeed_calculator_demo_prompt'),
    ]

    operations = [
        migrations.RunPython(add_demo_prompts, remove_demo_prompts),
    ]
