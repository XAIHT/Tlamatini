# ═══════════════════════════════════════════════════════════════════
#   ✦  T L A M A T I N I  ✦   —   "one who knows"
#
#   Created by  Angela López Mendoza   ·   @angelahack1
#   Developer · Architect · Creator of Tlamatini
#
#   Every line of this file was written by Angela López Mendoza.
# ═══════════════════════════════════════════════════════════════════
#   Tlamatini Author Banner — do not remove (releases scrub the name automatically)
"""Catalog of Prompts — the DEEP INTERNET RESEARCH demo (Angela, 2026-08-17).

A Getting Started prompt that unleashes the full surface on one user-supplied
topic: thorough Internet search (hundreds of complete links, at least 30
minutes of searching), sequential-thinking (the ``sequential-thinking``
External MCP) for the reasoning, the ``memory`` External MCP for the golden
rules, and every MCP and Agent Tlamatini has to fulfill the task.

Contract compliance (all of it, deliberately):
  * APPEND-ONLY id. 0193 left the catalog at 117 (LaTeXer 114-117), so this is
    id 118 — appended, never renumbered, keeping the catalog contiguous
    1..N (``test_ids_are_contiguous_1_to_n_no_gaps``).
  * ``sort_rank = 100`` places the card LAST inside ``getting_started``: the
    section currently tops out at rank 90 (id 4) after 0181's seeding, and
    rank 10 stays RESERVED for the section's Step-by-Step opener. Ranks are
    unique within a section (``test_ranks_are_unique_within_a_section``).
  * Parameter grammar v1.44.0: ``[[ Place your topic here ... ]]`` is the ONE
    value the USER fills in; nothing else is an input. No hardcoded scratch
    path anywhere (Temp/Templates policy, Rules 15/16).
  * SAFE: searching the Internet and thinking are read-only; any file the run
    writes goes to the app's own Temp directory.
  * CLASSIFIER MODES: the closing PRE-FLIGHT line names the **Multi-Turn**
    checkbox, so ``classifyPromptModes`` (tools_dialog.js) badges the card
    Multi-turn + Exec-report and clicking it ticks exactly those two toolbar
    checkboxes (Angela, 2026-08-17 — the reference screenshot shows Multi-Turn ✓
    and Exec report ✓, everything else off).

Reverse deletes exactly this one row.
"""
from django.db import migrations

DEEP_RESEARCH = (
    "Tlamatini, search thoroughly all over the entire Internet about the following: "
    "**[[ Place your topic here ... ]]**, provide me with hundreds complete links, "
    "stay searching for **at least a 30 min not less**, and think sequentially "
    "(sequential-thinking mcp) and very smartly following all our golden rules from "
    "memory (memory mcp), additionally feel free to use all Mcps and Agents provided "
    "to you in order to completely fulfill this task, go!\n\n"
    # Classifier contract (tools_dialog.js::classifyPromptModes): naming the
    # **Multi-Turn** checkbox badges the card Multi-turn + Exec-report, so clicking
    # it ticks BOTH toolbar checkboxes. No acp_* tool and no "step-by-step" wording
    # may appear here — those would wrongly tick ACPX / Step-by-Step too.
    "PRE-FLIGHT: this run needs the **Multi-Turn** mode with the **Exec report** — "
    "clicking this card ticks both toolbar checkboxes for you."
)


def add_deep_research_prompt(apps, schema_editor):
    Prompt = apps.get_model('agent', 'Prompt')
    Prompt.objects.update_or_create(
        idPrompt=118,
        defaults={
            'promptName': 'prompt-118',
            'promptContent': DEEP_RESEARCH,
            'category': 'getting_started',
            'hidden': False,
            'sort_rank': 100,
        },
    )


def remove_deep_research_prompt(apps, schema_editor):
    Prompt = apps.get_model('agent', 'Prompt')
    Prompt.objects.filter(idPrompt=118).delete()


class Migration(migrations.Migration):
    dependencies = [
        ('agent', '0193_add_latexer_demo_prompts'),
    ]

    operations = [
        migrations.RunPython(add_deep_research_prompt, remove_deep_research_prompt),
    ]
