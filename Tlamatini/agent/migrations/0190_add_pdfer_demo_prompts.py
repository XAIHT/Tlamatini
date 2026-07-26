# ═══════════════════════════════════════════════════════════════════
#   ✦  T L A M A T I N I  ✦   —   "one who knows"
#
#   Created by  Angela López Mendoza   ·   @angelahack1
#   Developer · Architect · Creator of Tlamatini
#
#   Every line of this file was written by Angela López Mendoza.
# ═══════════════════════════════════════════════════════════════════
#   Tlamatini Author Banner — do not remove (releases scrub the name automatically)
"""Catalog of Prompts — the NEW 'Documents & PDF' section for PDFer (Angela, 2026-07-26).

PDFer is the first agent in a genuinely new capability family (document AUTHORING),
so it gets its own catalog section — ``documents`` / "Documents & PDF", registered in
``views.PROMPT_CATEGORY_ORDER`` between 'Code & Project Generation' and
'Images & Vision'.

Contract compliance (all of it, deliberately):
  * APPEND-ONLY ids. 0187 left the catalog at 108, so these are 109..113. No existing
    ``idPrompt`` / ``promptName`` / ``category`` / ``sort_rank`` is touched, so the
    catalog stays contiguous and the gap-tolerant offline probe keeps working.
  * ``sort_rank`` decides the order INSIDE the section (migration 0181), so the cards
    read least-complex -> most-complex:
        10  (RESERVED slot) Step-by-Step wizard opener            -> id 109
        20  Markdown -> PDF, zero setup, one call                 -> id 110
        30  turn Tlamatini's OWN answer into a report             -> id 111
        40  images -> a PDF album (needs image files)             -> id 112
        50  full mixed report: capture + prose + cover + polish   -> id 113
    Rank 10 is the reserved Step-by-Step opener slot Angela requires in EVERY section,
    and it is pinned by ``test_prompt_catalog_contiguous`` in BOTH directions
    (``expected_first['documents'] = 109`` plus the content check that the opener
    actually names Step-by-Step and promises to WAIT).
  * Parameter grammar v1.44.0: ``[[ ]]`` = a value the USER fills in, always collected
    in a fill-in block at the TOP with an unfilled-guard line beneath so a one-click
    demo still runs on the stated defaults; ``< >`` = a REPORT slot only. No hardcoded
    scratch path anywhere — PDFer's own default (Documents/TlamatiniPDF) is used, which
    respects the Temp/Templates policy (Rules 15/16).
  * Every prompt drives ``chat_agent_pdfer`` with a realistic, SAFE, repeatable task:
    nothing is deleted, nothing is overwritten (PDFer's ``overwrite`` stays false, so a
    colliding name becomes _2/_3), and nothing is sent to a human.

Reverse deletes exactly these five rows.
"""
from django.db import migrations


# ── rank 10 · id 109 — the section's Step-by-Step opener (RESERVED slot) ──────
WIZARD = (
    "Tlamatini, be my <b>PDFer STEP-BY-STEP WIZARD</b> — walk me from nothing to a real, "
    "styled PDF on my disk, <b>one action at a time</b>. This is the guided tour of the "
    "Documents &amp; PDF section.<br><br>"

    "PRECONDITIONS: tick <b>Multi-Turn</b> AND <b>Step-by-Step</b> in the toolbar (clicking "
    "this card already ticks them). Leave ACPX and Add-internet unticked. <b>Ask Execs</b> is "
    "your choice — PDFer is on the Ask-Execs allowlist because it writes a file, so with it "
    "ticked you will get a Proceed/Deny prompt before each render.<br><br>"

    "FILL THESE IN — replace the text inside the [[ ]] brackets (ALL OPTIONAL; if I leave a "
    "bracket untouched, USE THE DEFAULT and do NOT ask me):<br>"
    "• DOCUMENT TITLE: [[ the title printed on the cover page — OPTIONAL, default: "
    "My First Tlamatini Document ]]<br>"
    "• WHERE TO SAVE IT: [[ a folder path — OPTIONAL, default: leave empty so PDFer uses its "
    "own Documents/TlamatiniPDF folder ]]<br>"
    "• PAGE SIZE: [[ A4 or Letter — OPTIONAL, default: A4 ]]<br><br>"

    "HOW YOU MUST BEHAVE — this is the whole point: perform EXACTLY ONE action per turn, then "
    "STOP and WAIT for me. After each action show me the concrete result, then end with the "
    "single line telling me exactly what to reply (usually <code>READY</code>). Never chain two "
    "steps. Never assume my reply. If a step fails, say plainly what failed and what to check, "
    "and WAIT — never skip ahead, never pretend a PDF was made.<br><br>"

    "THE STEPS:<br><br>"

    "<b>STEP 1 — CHECK THE ENGINE.</b> Call <code>chat_agent_pdfer</code> ONCE with "
    "<code>mode='validate'</code>. This writes NO file; it just reports which PDF backends are "
    "importable. Read the <code>INI_SECTION_PDFER</code> block and show me the six backends "
    "(markdown, xhtml2pdf, pymupdf, reportlab, pillow, pypdf), the <code>status</code> "
    "&lt;status&gt;, and the folder PDFer will save into &lt;output_dir&gt;. Tell me plainly "
    "that PDFer needs NO installation — all six already ship with Tlamatini. Ask me to reply "
    "<code>READY</code>. WAIT.<br><br>"

    "<b>STEP 2 — MAKE THE SIMPLEST POSSIBLE PDF.</b> Call <code>chat_agent_pdfer</code> ONCE "
    "with <code>mode='markdown'</code>, <code>title='&lt;DOCUMENT TITLE&gt;'</code>, "
    "<code>page_size='&lt;PAGE SIZE&gt;'</code>, <code>filename='pdfer_wizard_step2.pdf'</code> "
    "(and <code>output_dir</code> only if I gave one), and this exact "
    "<code>input_text</code>:<br>"
    "<code># Hello from Tlamatini<br><br>This document was written by the **PDFer** agent.<br><br>"
    "| Part | What it does |<br>|---|---|<br>| markdown | text to HTML |<br>"
    "| xhtml2pdf | HTML to PDF |<br></code><br>"
    "Report the <code>status</code> &lt;status&gt;, the FULL <code>output_path</code> "
    "&lt;output_path&gt;, <code>page_count</code> &lt;page_count&gt; and <code>bytes</code> "
    "&lt;bytes&gt;. Tell me to open that file and confirm I can see the title, the bold text "
    "and a REAL two-column table. Ask me to reply <code>READY</code>. WAIT.<br><br>"

    "<b>STEP 3 — ADD A COVER PAGE AND PAGE NUMBERS.</b> Explain in one short paragraph what "
    "<code>title</code>, <code>subtitle</code> and <code>page_numbers</code> do, then call "
    "<code>chat_agent_pdfer</code> ONCE with the same text but "
    "<code>subtitle='Made step by step with Tlamatini'</code>, <code>page_numbers=true</code>, "
    "<code>toc=true</code> and <code>filename='pdfer_wizard_step3.pdf'</code>. Report the new "
    "&lt;output_path&gt; and &lt;page_count&gt;, and tell me the first page is now a cover and "
    "the footer reads 'page N of M'. Ask me to reply <code>READY</code>. WAIT.<br><br>"

    "<b>STEP 4 — SEE THE FAIL-SAFE REFUSE (nothing breaks).</b> Call "
    "<code>chat_agent_pdfer</code> ONCE with <code>mode='markdown'</code> and an EMPTY "
    "<code>input_text</code>. It will NOT crash and it will NOT write an empty file — its "
    "preflight refuses. Show me <code>status</code> = <code>refused</code> and quote the "
    "blocker line. Explain that this is PDFer working as DESIGNED, and that a downstream "
    "Forker on the canvas can branch on that <code>{status}</code>. Ask me to reply "
    "<code>READY</code>. WAIT.<br><br>"

    "<b>STEP 5 — INSPECT WHAT YOU BUILT.</b> Call <code>chat_agent_pdfer</code> ONCE with "
    "<code>mode='info'</code> and <code>input_file</code> set to the &lt;output_path&gt; from "
    "STEP 3. Show me the page count, byte size and the Title/Author/Producer metadata PDFer "
    "stamped in. Ask me to reply <code>READY</code>. WAIT.<br><br>"

    "<b>STEP 6 — WRAP UP.</b> Do NOT call a tool. Print a short table of the three files you "
    "made with their full paths and page counts, then a one-line reminder of the modes I can "
    "use next (<code>markdown</code>, <code>html</code>, <code>text</code>, <code>images</code>, "
    "<code>mixed</code>, <code>merge</code>, <code>info</code>, <code>validate</code>) and that "
    "<code>mode='auto'</code> picks for me. End with END-RESPONSE."
)

# ── rank 20 · id 110 — the simplest possible one-call demo ───────────────────
SIMPLE = (
    "Tlamatini, run the <b>PDFer QUICK DEMO</b>, please — make me one styled PDF in a single "
    "call. Tick ONLY the <b>Multi-Turn</b> checkbox; use ONLY "
    "<code>chat_agent_pdfer</code>.<br><br>"

    "FILL THESE IN — replace the text inside the [[ ]] brackets (ALL OPTIONAL; if I leave a "
    "bracket untouched, USE THE DEFAULT and do NOT ask me first):<br>"
    "• TITLE: [[ the document title — OPTIONAL, default: Tlamatini Agent Cheat-Sheet ]]<br>"
    "• FILE NAME: [[ OPTIONAL, default: tlamatini_cheatsheet.pdf ]]<br><br>"

    "Call <code>chat_agent_pdfer</code> EXACTLY ONCE with <code>mode='markdown'</code>, "
    "<code>title='&lt;TITLE&gt;'</code>, <code>filename='&lt;FILE NAME&gt;'</code>, "
    "<code>page_numbers=true</code>, and an <code>input_text</code> that is a short Markdown "
    "cheat-sheet you write yourself: a <code># </code> heading, one sentence of intro, and a "
    "Markdown table of FIVE Tlamatini agents with a one-line description each (pick five you "
    "genuinely have, e.g. Globber, Grepper, Editor, Shoter, PDFer). Leave "
    "<code>output_dir</code> EMPTY so PDFer saves to its own Documents/TlamatiniPDF folder — "
    "do NOT invent a scratch path.<br><br>"

    "Then report, in a small HTML table: <code>status</code> &lt;status&gt;, the FULL "
    "<code>output_path</code> &lt;output_path&gt;, <code>page_count</code> &lt;page_count&gt;, "
    "<code>bytes</code> &lt;bytes&gt; and <code>engine</code> &lt;engine&gt;. If "
    "<code>status</code> is not <code>created</code>, say so plainly and quote the reason — "
    "never claim a PDF exists when it does not. End with END-RESPONSE."
)

# ── rank 30 · id 111 — the headline use case: your OWN answer becomes a report ─
ANSWER_TO_PDF = (
    "Tlamatini, run the <b>ANSWER → PDF</b> demo, please — answer a question and then turn "
    "<b>your own answer</b> into a real PDF report. Tick ONLY the <b>Multi-Turn</b> checkbox; "
    "use ONLY <code>chat_agent_pdfer</code>.<br><br>"

    "FILL THIS IN — replace the text inside the [[ ]] brackets (OPTIONAL; if I leave it "
    "untouched, USE THE DEFAULT and do NOT ask me first):<br>"
    "• TOPIC: [[ what the report should be about — OPTIONAL, default: how Tlamatini's "
    "Multi-Turn mode, Exec Report and Ask Execs work together ]]<br><br>"

    "STEP 1 — WRITE IT. First compose a genuine, well-structured answer about &lt;TOPIC&gt; "
    "in Markdown: a <code># </code> title, three <code>## </code> sections, at least one "
    "bullet list and at least one Markdown table. Show it to me in the chat.<br><br>"

    "STEP 2 — PRINT IT. Then call <code>chat_agent_pdfer</code> EXACTLY ONCE, passing that "
    "SAME text VERBATIM as <code>input_text</code> — do not summarize it, do not re-write it, "
    "do not drop the table. Use <code>mode='auto'</code> (PDFer sniffs Markdown vs HTML "
    "itself), <code>title</code> set to your report's title, "
    "<code>subtitle='Generated by Tlamatini'</code>, <code>toc=true</code>, "
    "<code>page_numbers=true</code>, and <code>filename='tlamatini_report.pdf'</code>. Leave "
    "<code>output_dir</code> EMPTY so it lands in Documents/TlamatiniPDF.<br><br>"

    "STEP 3 — REPORT. Tell me which mode <code>auto</code> resolved to &lt;mode&gt;, the "
    "<code>status</code> &lt;status&gt;, the FULL <code>output_path</code> &lt;output_path&gt; "
    "and the <code>page_count</code> &lt;page_count&gt;. Finish with one line telling me the "
    "table I wrote is a REAL table in the PDF, not an image. End with END-RESPONSE."
)

# ── rank 40 · id 112 — images -> a PDF album (needs image files) ─────────────
IMAGES = (
    "Tlamatini, run the <b>PDFer IMAGE ALBUM</b> demo, please — turn a folder of pictures into "
    "one PDF. Tick ONLY the <b>Multi-Turn</b> checkbox.<br><br>"

    "FILL THESE IN — replace the text inside the [[ ]] brackets (ALL OPTIONAL; if I leave a "
    "bracket untouched, USE THE DEFAULT and do NOT ask me first):<br>"
    "• PICTURES FOLDER: [[ a folder that contains a few .png/.jpg files — OPTIONAL, default: "
    "your Pictures folder ]]<br>"
    "• HOW MANY: [[ how many images to include — OPTIONAL, default: 4 ]]<br>"
    "• LAYOUT: [[ one-per-page, fit, or grid — OPTIONAL, default: grid ]]<br><br>"

    "STEP 1 — FIND THE PICTURES. Use <code>chat_agent_globber</code> ONCE with "
    "<code>pattern='*.png'</code> (and again with <code>*.jpg</code> if you find none) and "
    "<code>path</code> set to &lt;PICTURES FOLDER&gt;, newest first. Take the first &lt;HOW "
    "MANY&gt; results. If you find NO images at all, STOP and tell me plainly — do NOT invent "
    "file paths and do NOT call PDFer with an empty list.<br><br>"

    "STEP 2 — BUILD THE ALBUM. Call <code>chat_agent_pdfer</code> EXACTLY ONCE with "
    "<code>mode='images'</code>, <code>images</code> set to those paths as a comma-separated "
    "list, <code>image_layout='&lt;LAYOUT&gt;'</code>, <code>grid_columns=2</code>, "
    "<code>image_caption=true</code>, <code>title='My Album'</code> and "
    "<code>filename='pdfer_album.pdf'</code>. Leave <code>output_dir</code> EMPTY.<br><br>"

    "STEP 3 — REPORT. Give me a small HTML table with <code>status</code> &lt;status&gt;, the "
    "FULL <code>output_path</code> &lt;output_path&gt;, <code>images_used</code> "
    "&lt;images_used&gt;, <code>page_count</code> &lt;page_count&gt; and <code>engine</code> "
    "&lt;engine&gt; (it should say pymupdf). If any image path was skipped as missing, say "
    "which. End with END-RESPONSE."
)

# ── rank 50 · id 113 — the full report: capture + prose + cover + polish ─────
MIXED = (
    "Tlamatini, run the <b>PDFer FULL REPORT</b> demo, please — capture the screen, write the "
    "commentary, and bind both into ONE illustrated PDF with a cover page. This is the most "
    "advanced card in this section. Tick ONLY the <b>Multi-Turn</b> checkbox.<br><br>"

    "FILL THESE IN — replace the text inside the [[ ]] brackets (ALL OPTIONAL; if I leave a "
    "bracket untouched, USE THE DEFAULT and do NOT ask me first):<br>"
    "• REPORT TITLE: [[ OPTIONAL, default: Desktop State Report ]]<br>"
    "• TIDY THE TEXT WITH OLLAMA FIRST: [[ yes or no — OPTIONAL, default: no ]]<br>"
    "• PAGE ORIENTATION: [[ portrait or landscape — OPTIONAL, default: landscape ]]<br><br>"

    "STEP 1 — CAPTURE. Call <code>chat_agent_shoter</code> ONCE to take a single screenshot of "
    "my desktop. Read its <code>output_path</code> — that exact path is the image you will "
    "embed. If Shoter fails, STOP and say so; do NOT fabricate an image path.<br><br>"

    "STEP 2 — DESCRIBE. Write a short Markdown commentary yourself: a <code>## </code> "
    "heading, two or three sentences saying what this report is and when it was made, and a "
    "small Markdown table with two rows (Captured at / Captured by).<br><br>"

    "STEP 3 — BIND IT. Call <code>chat_agent_pdfer</code> EXACTLY ONCE with "
    "<code>mode='mixed'</code>, <code>input_text</code> = your commentary from STEP 2, "
    "<code>images</code> = the Shoter <code>output_path</code> from STEP 1, "
    "<code>title='&lt;REPORT TITLE&gt;'</code>, "
    "<code>subtitle='Captured and bound by Tlamatini'</code>, "
    "<code>orientation='&lt;PAGE ORIENTATION&gt;'</code>, <code>image_caption=true</code>, "
    "<code>page_numbers=true</code>, <code>filename='pdfer_full_report.pdf'</code>, and "
    "<code>ollama_polish</code> set to true ONLY if I answered yes to the TIDY question "
    "(otherwise false — false is faster and renders my words verbatim). Leave "
    "<code>output_dir</code> EMPTY.<br><br>"

    "STEP 4 — REPORT. Give me an HTML table with <code>status</code> &lt;status&gt;, "
    "<code>mode</code> &lt;mode&gt;, the FULL <code>output_path</code> &lt;output_path&gt;, "
    "<code>page_count</code> &lt;page_count&gt;, <code>images_used</code> &lt;images_used&gt; "
    "and <code>bytes</code> &lt;bytes&gt;. Then add ONE closing line explaining that the very "
    "same chain works unattended on the canvas as "
    "<code>Starter → Shoter → Parametrizer → PDFer → Ender</code>, because PDFer emits an "
    "<code>INI_SECTION_PDFER</code> block a Parametrizer can read. End with END-RESPONSE."
)


# (idPrompt, sort_rank, promptContent) — ids APPENDED after 108 (0187), never renumbered.
_NEW_PROMPTS = (
    (109, 10, WIZARD),          # RESERVED rank-10 slot: the section's Step-by-Step opener
    (110, 20, SIMPLE),
    (111, 30, ANSWER_TO_PDF),
    (112, 40, IMAGES),
    (113, 50, MIXED),
)


def add_pdfer_demo_prompts(apps, schema_editor):
    Prompt = apps.get_model('agent', 'Prompt')
    for pid, rank, content in _NEW_PROMPTS:
        Prompt.objects.update_or_create(
            idPrompt=pid,
            defaults={
                'promptName': f'prompt-{pid}',
                'promptContent': content,
                'category': 'documents',
                'hidden': False,
                'sort_rank': rank,
            },
        )


def remove_pdfer_demo_prompts(apps, schema_editor):
    Prompt = apps.get_model('agent', 'Prompt')
    Prompt.objects.filter(idPrompt__in=[pid for pid, _rank, _c in _NEW_PROMPTS]).delete()


class Migration(migrations.Migration):
    dependencies = [
        ('agent', '0189_add_chat_agent_pdfer_tool'),
    ]

    operations = [
        migrations.RunPython(add_pdfer_demo_prompts, remove_pdfer_demo_prompts),
    ]
