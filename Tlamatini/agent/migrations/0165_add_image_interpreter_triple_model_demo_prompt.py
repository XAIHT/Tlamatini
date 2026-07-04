# ═══════════════════════════════════════════════════════════════════
#   ✦  T L A M A T I N I  ✦   —   "one who knows"
#
#   Created by  Angela López Mendoza   ·   @angelahack1
#   Developer · Architect · Creator of Tlamatini
#
#   Every line of this file was written by Angela López Mendoza.
# ═══════════════════════════════════════════════════════════════════
#   Tlamatini Author Banner — do not remove (releases scrub the name automatically)
"""One Catalog-of-Prompts example for the upgraded TRIPLE-MODEL Image-Interpreter
(2026-07-04): interpreter_model_1 (qwen3.5:cloud) + interpreter_model_2
(gemma4:cloud) run IN PARALLEL on two dedicated Ollama connections, a BARRIER
waits for BOTH interpretations, then merging_model (glm-5.2:cloud) fuses them
into one definitive report.

Appended at MAX+1 (contiguity contract: the #prompts-catalog dropdown
enumerates prompt-1..N and BREAKS at the first gap, so we never renumber and
never leave a hole; MAX_PROMPTS=256). The wording ("Multi-Turn checkbox" +
"chat_agent_...") makes the catalog mode-classifier light up Multi-Turn.

The task is SAFE to run repeatedly (the daily chat test may execute it): one
silent screenshot + one read-only vision analysis, no destructive operations.
"""
from django.db import migrations


TRIPLE_MODEL_DEMO_PROMPT = (
    "Tlamatini, run the **IMAGE-INTERPRETER TRIPLE-MODEL DEMO**, please — tick ONLY the "
    "Multi-Turn checkbox. STEP 1: take one silent screenshot with chat_agent_shoter (no viewer "
    "popup — the result carries a top-level output_path). STEP 2: feed that saved PNG to "
    "chat_agent_image_interpreter with images_pathfilenames='<the output_path from STEP 1>' and "
    "prompt_user='Inventory every visible GUI element with its position (% of image), size (%), "
    "colors and exact text; if any person is visible, describe them exhaustively and hypothesize "
    "who they may be, using the file name as a clue.' — the agent will run interpreter_model_1 "
    "(qwen3.5:cloud) and interpreter_model_2 (gemma4:cloud) IN PARALLEL on two dedicated Ollama "
    "connections, wait on the BARRIER until BOTH interpretations arrive, then fuse them with "
    "merging_model (glm-5.2:cloud). STEP 3: report the 5 most interesting findings from the "
    "merged report and say which `status` the INI_SECTION_IMAGE_INTERPRETER block carried "
    "(merged / partial_interpreter_1_only / partial_interpreter_2_only / merge_fallback_concat). "
    "Use ONLY chat_agent_shoter and chat_agent_image_interpreter. End with END-RESPONSE."
)

_NEW_PROMPTS = (TRIPLE_MODEL_DEMO_PROMPT,)


def add_prompts(apps, schema_editor):
    Prompt = apps.get_model('agent', 'Prompt')
    for content in _NEW_PROMPTS:
        if Prompt.objects.filter(promptContent=content).exists():
            continue
        next_id = (Prompt.objects.order_by('-idPrompt').values_list('idPrompt', flat=True).first() or 0) + 1
        Prompt.objects.update_or_create(
            idPrompt=next_id,
            defaults={'promptName': f'prompt-{next_id}', 'promptContent': content},
        )


def remove_prompts(apps, schema_editor):
    Prompt = apps.get_model('agent', 'Prompt')
    Prompt.objects.filter(promptContent__in=list(_NEW_PROMPTS)).delete()


class Migration(migrations.Migration):
    dependencies = [('agent', '0164_dedup_zavuerer_setup_wizards')]
    operations = [migrations.RunPython(add_prompts, remove_prompts)]
