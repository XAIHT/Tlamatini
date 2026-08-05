# ═══════════════════════════════════════════════════════════════════
#   ✦  T L A M A T I N I  ✦   —   "one who knows"
#
#   Created by  Angela López Mendoza   ·   @angelahack1
#   Developer · Architect · Creator of Tlamatini
#
#   Every line of this file was written by Angela López Mendoza.
# ═══════════════════════════════════════════════════════════════════
#   Tlamatini Author Banner — do not remove (releases scrub the name automatically)
"""Seed the LaTeXer Catalog-of-Prompts demos (Angela, 2026-08-05).

MANDATORY GATE: a Multi-Turn agent shipped WITHOUT at least one catalog prompt is
INCOMPLETE. LaTeXer gets four, appended at ids 114-117 after PDFer's 109-113 — ids are
APPENDED, never renumbered.

They live in the existing ``documents`` category alongside PDFer and are ranked 60/70/
80/90, i.e. AFTER every PDFer card. That ordering is deliberate and follows the
least-complex → most-complex rule: PDFer needs NOTHING installed, whereas LaTeXer needs
**MiKTeX** on the machine, so a reader meets the zero-setup document tool first and the
one with a prerequisite second. Rank 10 of this section is already held by PDFer's
Step-by-Step opener (a section has exactly one), so LaTeXer's own wizard takes 60.

Every prompt drives ``chat_agent_latexer`` with a realistic, SAFE, repeatable task:
they only ever write into LaTeXer's own output folder, never delete anything the user
cares about, and never enable ``shell_escape``. The daily chat test may run them.
Reverse deletes exactly these four rows.
"""
from django.db import migrations


# ── rank 60 · id 114 — LaTeXer's guided Step-by-Step tour ────────────────────
WIZARD = (
    "Tlamatini, be my <b>LaTeXer STEP-BY-STEP WIZARD</b> — walk me from nothing to a real, "
    "typeset LaTeX PDF on my disk, <b>one action at a time</b>.<br><br>"

    "PRECONDITIONS: tick <b>Multi-Turn</b> AND <b>Step-by-Step</b> in the toolbar (clicking "
    "this card already ticks them). Leave ACPX and Add-internet unticked. <b>Ask Execs</b> is "
    "your choice — LaTeXer is on the Ask-Execs allowlist because it writes files and runs a "
    "real compiler, so with it ticked you get a Proceed/Deny prompt before each run.<br><br>"

    "THE ONE PREREQUISITE: <b>MiKTeX</b> (https://miktex.org/download). Tlamatini does not "
    "bundle a TeX distribution — they are several gigabytes. MiKTeX is installed once and "
    "then LaTeXer works forever, because MiKTeX downloads any missing LaTeX package "
    "automatically while a document is building. STEP 1 checks this for me.<br><br>"

    "FILL THESE IN — replace the text inside the [[ ]] brackets (ALL OPTIONAL; if I leave a "
    "bracket untouched, USE THE DEFAULT and do NOT ask me):<br>"
    "• DOCUMENT TITLE: [[ the title on the first page — OPTIONAL, default: "
    "My First LaTeX Document ]]<br>"
    "• MY NAME: [[ the author line — OPTIONAL, default: Tlamatini ]]<br>"
    "• LANGUAGE: [[ en or es — OPTIONAL, default: en ]]<br><br>"

    "HOW YOU MUST BEHAVE — this is the whole point: perform EXACTLY ONE action per turn, then "
    "STOP and WAIT for me. After each action show me the concrete result, then end with the "
    "single line telling me exactly what to reply (usually <code>READY</code>). Never chain two "
    "steps. Never assume my reply. If a step fails, say plainly what failed and what to check, "
    "and WAIT — never skip ahead, and NEVER claim a PDF was produced when "
    "<code>status</code> says otherwise.<br><br>"

    "THE STEPS:<br><br>"

    "<b>STEP 1 — IS LaTeX INSTALLED?</b> Call <code>chat_agent_latexer</code> ONCE with "
    "<code>action='validate'</code>. This writes NO file. Read the "
    "<code>INI_SECTION_LATEXER</code> block and show me &lt;distribution&gt;, the engine path, "
    "and which of latexmk / biber / bibtex / makeindex were found. If "
    "&lt;distribution&gt; is <code>miktex</code>, tell me I am fully set up. If it is "
    "<code>none</code>, tell me plainly that I must install <b>MiKTeX</b> from "
    "https://miktex.org/download (or that I can reply <code>INSTALL</code> and you will call "
    "<code>action='install'</code> to download and launch the official installer for me), and "
    "STOP there. Otherwise ask me to reply <code>READY</code>. WAIT.<br><br>"

    "<b>STEP 2 — TYPESET SOMETHING IN ONE CALL.</b> Call <code>chat_agent_latexer</code> ONCE "
    "with <code>action='compile'</code>, <code>title='&lt;DOCUMENT TITLE&gt;'</code>, "
    "<code>author='&lt;MY NAME&gt;'</code>, <code>document_language='&lt;LANGUAGE&gt;'</code>, "
    "<code>filename='latexer_wizard_step2.pdf'</code> and this exact "
    "<code>input_text</code>: <code>Hello from Tlamatini. LaTeX sets real mathematics: "
    "$E = mc^2$.</code><br>"
    "Point out that I passed a bare FRAGMENT — no <code>\\\\documentclass</code>, no "
    "<code>\\\\begin{document}</code> — and LaTeXer wrapped it in a proper preamble for me "
    "(that is <code>auto_preamble</code>). Report &lt;status&gt;, the FULL &lt;output_path&gt;, "
    "&lt;page_count&gt; and &lt;passes&gt;. Tell me to open the file. Ask me to reply "
    "<code>READY</code>. WAIT.<br><br>"

    "<b>STEP 3 — REAL MATHEMATICS AND A CROSS-REFERENCE.</b> Call "
    "<code>chat_agent_latexer</code> ONCE with <code>action='compile'</code>, "
    "<code>filename='latexer_wizard_step3.pdf'</code> and an <code>input_text</code> that "
    "contains a numbered <code>equation</code> environment with a <code>\\\\label</code>, and a "
    "sentence referring back to it with <code>\\\\eqref</code>. Report &lt;passes&gt; and "
    "explain in ONE short paragraph why LaTeX needed more than one pass: the first pass does "
    "not yet know the equation's number, so LaTeXer keeps re-running until the references "
    "stop changing. Ask me to reply <code>READY</code>. WAIT.<br><br>"

    "<b>STEP 4 — LINT WITHOUT COMPILING.</b> Call <code>chat_agent_latexer</code> ONCE with "
    "<code>action='validate_tex'</code> and an <code>input_text</code> that is deliberately "
    "broken — an <code>\\\\begin{itemize}</code> with no matching <code>\\\\end</code>. Show me "
    "the error it names and the line number. Explain that this check is STATIC: it reads the "
    "source and needs no LaTeX installed at all. Ask me to reply <code>READY</code>. "
    "WAIT.<br><br>"

    "<b>STEP 5 — SEE THE FAIL-SAFE REFUSE (nothing breaks).</b> Call "
    "<code>chat_agent_latexer</code> ONCE with <code>action='compile'</code> and NO source at "
    "all — no <code>input_text</code>, no <code>tex_path</code>, no <code>project_dir</code>. "
    "It will NOT crash and will NOT write an empty PDF: its preflight refuses. Show me "
    "&lt;status&gt; = <code>refused</code> and quote the blocker. Explain that this is LaTeXer "
    "working as DESIGNED, and that a Forker on the canvas can branch on that "
    "<code>{status}</code>. Ask me to reply <code>READY</code>. WAIT.<br><br>"

    "<b>STEP 6 — WRAP UP.</b> Do NOT call a tool. Print a short table of the files you made "
    "with their full paths and page counts, then one line listing the actions I can use next "
    "(<code>compile</code>, <code>compile_project</code>, <code>scaffold_compile</code>, "
    "<code>create_from_template</code>, <code>edit_file</code>, <code>structure</code>, "
    "<code>clean</code>). End with END-RESPONSE."
)

# ── rank 70 · id 115 — the simplest possible one-call demo ───────────────────
SIMPLE = (
    "Tlamatini, run the <b>LaTeXer QUICK DEMO</b>, please — typeset one real LaTeX PDF in a "
    "single call. Tick ONLY the <b>Multi-Turn</b> checkbox; use ONLY "
    "<code>chat_agent_latexer</code>.<br><br>"

    "FILL THESE IN — replace the text inside the [[ ]] brackets (ALL OPTIONAL; if I leave a "
    "bracket untouched, USE THE DEFAULT and do NOT ask me first):<br>"
    "• TITLE: [[ the document title — OPTIONAL, default: Mathematics, Set Properly ]]<br>"
    "• LANGUAGE: [[ en or es — OPTIONAL, default: en ]]<br><br>"

    "SAFETY CHECK — this only writes ONE new PDF into LaTeXer's own output folder. It "
    "overwrites nothing of mine and deletes nothing. Requires <b>MiKTeX</b> "
    "(https://miktex.org/download); if it is missing, LaTeXer will REFUSE cleanly and tell me "
    "so — report that instead of pretending a PDF exists.<br><br>"

    "THE TASK: call <code>chat_agent_latexer</code> EXACTLY ONCE with "
    "<code>action='compile'</code>, <code>title='&lt;TITLE&gt;'</code>, "
    "<code>document_language='&lt;LANGUAGE&gt;'</code>, "
    "<code>filename='latexer_quick_demo.pdf'</code>, and an <code>input_text</code> holding a "
    "short section that shows off what LaTeX does best — an inline formula, a displayed "
    "integral, and a small <code>itemize</code> list. Then report the "
    "<code>INI_SECTION_LATEXER</code> values: &lt;status&gt;, the FULL &lt;output_path&gt; I "
    "should open, &lt;page_count&gt;, &lt;bytes&gt;, &lt;engine&gt; and &lt;distribution&gt;. "
    "If &lt;status&gt; is anything other than <code>compiled</code>, quote the blocker or the "
    "LaTeX errors verbatim and do NOT call it a success. End with END-RESPONSE."
)

# ── rank 80 · id 116 — a real paper: bibliography + cross-references ─────────
PAPER = (
    "Tlamatini, run the <b>LaTeXer ACADEMIC PAPER DEMO</b>, please — build a small paper with "
    "a real bibliography and working cross-references, the thing LaTeX exists for. Tick ONLY "
    "the <b>Multi-Turn</b> checkbox; use ONLY <code>chat_agent_latexer</code> and "
    "<code>chat_agent_file_creator</code>.<br><br>"

    "FILL THESE IN — replace the text inside the [[ ]] brackets (ALL OPTIONAL; if I leave a "
    "bracket untouched, USE THE DEFAULT and do NOT ask me first):<br>"
    "• PAPER TITLE: [[ the title — OPTIONAL, default: A Short Note on Typesetting ]]<br>"
    "• AUTHOR: [[ the author line — OPTIONAL, default: Tlamatini ]]<br><br>"

    "SAFETY CHECK — everything is written into a NEW folder under Tlamatini's own Templates "
    "directory. Nothing existing is touched. Requires <b>MiKTeX</b> "
    "(https://miktex.org/download); on the first run MiKTeX may pause to download the "
    "biblatex package automatically — that is normal and it only happens once.<br><br>"

    "STEP 1 — WRITE THE BIBLIOGRAPHY. Use <code>chat_agent_file_creator</code> ONCE to write "
    "<code>refs.bib</code> into a new folder <code>latexer_paper_demo</code> under Tlamatini's "
    "Templates directory, containing TWO <code>@book</code> entries with the keys "
    "<code>knuth1984</code> and <code>lamport1994</code> (Knuth's The TeXbook, and Lamport's "
    "LaTeX: A Document Preparation System).<br><br>"

    "STEP 2 — WRITE THE PAPER. Use <code>chat_agent_file_creator</code> ONCE to write "
    "<code>main.tex</code> into that SAME folder: an <code>article</code> that loads "
    "<code>biblatex</code> with <code>backend=biber</code>, calls "
    "<code>\\\\addbibresource{refs.bib}</code>, has a titled section with a "
    "<code>\\\\label</code>, a second section that refers back to it with "
    "<code>\\\\ref</code>, cites BOTH keys with <code>\\\\cite</code>, and ends with "
    "<code>\\\\printbibliography</code>.<br><br>"

    "STEP 3 — TYPESET THE WHOLE PROJECT. Call <code>chat_agent_latexer</code> EXACTLY ONCE "
    "with <code>action='compile_project'</code> and <code>project_dir</code> set to that "
    "folder. Do NOT name a main file — let LaTeXer auto-detect the master document.<br><br>"

    "THEN REPORT: &lt;status&gt;, the FULL &lt;output_path&gt;, &lt;page_count&gt;, "
    "&lt;bibliography&gt; (it should say <code>biber</code>, chosen automatically from the "
    "source) and &lt;passes&gt;. Explain in ONE short paragraph what those passes did: "
    "typeset once, run biber to resolve the citations, then typeset again until the numbers "
    "stop moving. Tell me to open the PDF and check that the two citations appear as [1] and "
    "[2] with a real reference list at the end. If &lt;status&gt; is not "
    "<code>compiled</code>, quote the errors verbatim. End with END-RESPONSE."
)

# ── rank 90 · id 117 — templates, in one call ────────────────────────────────
TEMPLATE = (
    "Tlamatini, run the <b>LaTeXer TEMPLATE DEMO</b>, please — turn one of the built-in "
    "templates into a finished PDF in a single call. Tick ONLY the <b>Multi-Turn</b> "
    "checkbox; use ONLY <code>chat_agent_latexer</code>.<br><br>"

    "FILL THESE IN — replace the text inside the [[ ]] brackets (ALL OPTIONAL; if I leave a "
    "bracket untouched, USE THE DEFAULT and do NOT ask me first):<br>"
    "• TEMPLATE: [[ one of article, report, book, beamer, letter, cv, homework, "
    "spanish-article — OPTIONAL, default: beamer ]]<br>"
    "• TITLE: [[ the title — OPTIONAL, default: Tlamatini Typesets ]]<br>"
    "• AUTHOR: [[ the author line — OPTIONAL, default: Tlamatini ]]<br><br>"

    "SAFETY CHECK — this creates ONE new .tex in a fresh folder under Tlamatini's Templates "
    "directory and ONE new PDF in LaTeXer's output folder. Nothing existing is overwritten. "
    "Requires <b>MiKTeX</b> (https://miktex.org/download); with beamer the first build may "
    "pause while MiKTeX downloads the beamer class automatically — normal, and only "
    "once.<br><br>"

    "THE TASK: call <code>chat_agent_latexer</code> EXACTLY ONCE with "
    "<code>action='scaffold_compile'</code>, <code>template='&lt;TEMPLATE&gt;'</code>, "
    "<code>title='&lt;TITLE&gt;'</code>, <code>author='&lt;AUTHOR&gt;'</code>, "
    "<code>content</code> set to one or two sentences that suit that template, and "
    "<code>filename='latexer_template_demo.pdf'</code>. That single action scaffolds the "
    "source from the template, typesets it, and delivers the PDF.<br><br>"

    "THEN REPORT: &lt;status&gt;, the &lt;tex_path&gt; of the source it generated (so I can "
    "edit it later), the FULL &lt;output_path&gt; of the PDF, and &lt;page_count&gt;. Finish "
    "with ONE line telling me how to change that source afterwards — "
    "<code>action='edit_file'</code> with <code>edit_mode</code>, <code>find_text</code> and "
    "<code>replace_text</code> — and then re-run <code>action='compile'</code> on the same "
    "<code>tex_path</code>. If &lt;status&gt; is not <code>compiled</code>, quote the blocker "
    "or the LaTeX errors verbatim. End with END-RESPONSE."
)


# (idPrompt, sort_rank, promptContent) — ids APPENDED after 113 (0190), never renumbered.
_NEW_PROMPTS = (
    (114, 60, WIZARD),
    (115, 70, SIMPLE),
    (116, 80, PAPER),
    (117, 90, TEMPLATE),
)


def add_latexer_demo_prompts(apps, schema_editor):
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


def remove_latexer_demo_prompts(apps, schema_editor):
    Prompt = apps.get_model('agent', 'Prompt')
    Prompt.objects.filter(idPrompt__in=[pid for pid, _rank, _c in _NEW_PROMPTS]).delete()


class Migration(migrations.Migration):
    dependencies = [
        ('agent', '0192_add_chat_agent_latexer_tool'),
    ]

    operations = [
        migrations.RunPython(add_latexer_demo_prompts, remove_latexer_demo_prompts),
    ]
