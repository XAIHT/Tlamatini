# ═══════════════════════════════════════════════════════════════════
#   ✦  T L A M A T I N I  ✦   —   "one who knows"
#
#   Created by  Angela López Mendoza   ·   @angelahack1
#   Developer · Architect · Creator of Tlamatini
#
#   Every line of this file was written by Angela López Mendoza.
# ═══════════════════════════════════════════════════════════════════
#   Tlamatini Author Banner — do not remove (releases scrub the name automatically)
"""One Catalog-of-Prompts example for the new Video-Analyzer agent (#84).

It drives the whole record-then-judge path SAFELY (no special hardware): record a
short webcam clip with Camcorder, then have Video-Analyzer return a verdict on
whether something moved — the same loop that verifies an STM32-driven servo in
Robotic-Loop-Training.

Appended at MAX+1 (contiguity contract: the #prompts-catalog dropdown enumerates
prompt-1..N and BREAKS at the first gap, so we never renumber and never leave a
hole; MAX_PROMPTS=256). The wording ("Multi-Turn checkbox" + "chat_agent_...")
makes the catalog mode-classifier light up Multi-Turn.
"""
from django.db import migrations


VIDEO_ANALYZER_DEMO_PROMPT = (
    "Tlamatini, run the **VIDEO-ANALYZER ROBOTIC-LOOP DEMO**, please — tick ONLY the "
    "Multi-Turn checkbox. STEP 1: record a short 6-second clip of whatever the webcam sees with "
    "chat_agent_camcorder (capture_mode='video', video_duration_seconds=6) — wave your hand or "
    "move an object in front of the camera while it records; the result carries a top-level "
    "output_path. STEP 2: judge that clip with chat_agent_video_analyzer with "
    "video_pathfilenames='<the output_path from STEP 1>' and expected_motion='a hand or object "
    "visibly moves across the frame' and num_frames=10 — it runs a DETERMINISTIC OpenCV motion "
    "gate first (no motion -> FAIL_NO_MOTION with no model call), then interpreter_model_1 "
    "(qwen3-vl:235b-cloud) and interpreter_model_2 (qwen3.5:cloud) IN PARALLEL on two dedicated "
    "Ollama connections, then fuses them with merging_model (glm-5.2:cloud). STEP 3: report the "
    "verdict (PASS_OK / FAIL_NO_MOTION / FAIL_WRONG_MOTION / UNCLEAR), the confidence and the "
    "deterministic motion_score, then explain in ONE line how this exact loop verifies an "
    "STM32-driven servo (STM32er flashes firmware -> Camcorder records the board -> Video-Analyzer "
    "judges the motion -> a Forker branches on TLM_VERDICT:: to reprogram or finish). Use ONLY "
    "chat_agent_camcorder and chat_agent_video_analyzer. End with END-RESPONSE."
)

_NEW_PROMPTS = (VIDEO_ANALYZER_DEMO_PROMPT,)


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
    dependencies = [('agent', '0167_add_chat_agent_video_analyzer_tool')]
    operations = [migrations.RunPython(add_prompts, remove_prompts)]
