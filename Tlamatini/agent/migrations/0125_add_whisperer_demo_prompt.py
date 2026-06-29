# ═══════════════════════════════════════════════════════════════════
#   ✦  T L A M A T I N I  ✦   —   "one who knows"
#
#   Crafted with heart by  Angela   ·   @angelahack1
#   Developer · Architect · Creator of Tlamatini
#
#   Every line of this file was written by Angela.
# ═══════════════════════════════════════════════════════════════════
#   Tlamatini Author Banner — do not remove (releases scrub the name automatically)
"""
Seed a Catalog-of-Prompts demo for **Whisperer** — Tlamatini's SPEECH-TO-TEXT —
run through the wrapped **chat_agent_whisperer** Multi-Turn tool. This is the
MANDATORY catalog prompt every Multi-Turn-capable agent must ship (CLAUDE.md
directive / create_new_agent.md Step 7.8 / tlamatini-agent-creation Phase 19).

    74  TLAMATINI LISTENS   basic   record 30 seconds of the microphone ->
                                    transcribe the speech to a text string ->
                                    report engine/device/status + the transcript.

SAFE to run repeatedly (the daily chat test may execute it): STT is
observational (it records a short mic clip and writes a transcript .txt), it
mutates no persistent state. Transcription needs `faster-whisper` (local; auto
GPU with CPU fallback) OR a cloud key; if neither is present Whisperer still runs
and reports status `engine_unavailable` (a documented degraded mode, NOT a
crash) — the prompt records that verbatim and continues.

Placement (append, no renumber)
-------------------------------
The catalog dropdown (static/agent/js/tools_dialog.js) enumerates promptName
'prompt-1','prompt-2',... and BREAKS at the first missing slot, so the catalog
must stay a contiguous, gap-free 'prompt-1..N'. Slots 1-73 are occupied (0122
appended the Talker demo at 73); this APPENDS at 74 with no shift of any existing
prompt. Reverse deletes 74. (MAX_PROMPTS=100.)
"""
from django.db import migrations


# Whisperer banner palette — mirrors the ``.canvas-item.whisperer-agent``
# gradient (deep indigo -> royal blue -> sonar cyan -> ice mint).
_BANNER_OPEN = (
    "<div style='padding:18px;border-radius:14px;background:linear-gradient(135deg,"
    "#0a1a3f 0%,#1747c4 33%,#18b6c9 66%,#aef0e6 100%);color:#fff;font-family:Inter,"
    "Segoe UI,sans-serif;text-align:center;text-shadow:0 1px 3px rgba(0,0,0,.5);'>"
)


WHISPERER_LISTENS_DEMO = (
    "Tlamatini, run the **TLAMATINI LISTENS** demo, please &mdash; a basic showcase of your own "
    "SPEECH-TO-TEXT (voice recognition), driven entirely from chat through the wrapped "
    "**chat_agent_whisperer** tool: you OPEN and RECORD your microphone yourself, run the neural "
    "recognizer, and turn the spoken audio into a STRING of text. "
    "PRECONDITIONS you can assume are TRUE (do NOT verify them &mdash; go straight to Step 1): "
    "(a) tick ONLY the **Multi-Turn** checkbox before sending (ACPX is NOT required &mdash; "
    "chat_agent_whisperer is the ONLY tool you may use; do NOT use chat_agent_executer / "
    "chat_agent_pythonxer / acp_spawn); (b) Whisperer is 100% self-sufficient for the microphone "
    "&mdash; it opens, configures and records the mic on its own (no Recorder needed); (c) local "
    "transcription needs `faster-whisper` (it auto-uses the GPU and ALWAYS falls back to CPU) OR a "
    "cloud STT key &mdash; if NEITHER is present Whisperer returns status `engine_unavailable` (a "
    "documented degraded mode, NOT a failure): record it verbatim and CONTINUE. "
    "\n\n"
    "Step 0: open with one HTML banner &mdash; " + _BANNER_OPEN +
    "<h2 style='margin:0;letter-spacing:2px;'>&#127908; TLAMATINI LISTENS &#128483;&#65039;</h2>"
    "<div style='opacity:.92;margin-top:4px;'>Tlamatini Whisperer &mdash; mic in, text out</div></div>. "
    "\n\n"
    "Step 1 (record &amp; transcribe): call **chat_agent_whisperer** with request "
    "\"Transcribe with input_source='mic' and record_seconds=30 and engine='faster-whisper' and "
    "model='base' and device='auto'\". This records 30 seconds of the default microphone and "
    "transcribes it. From the INI_SECTION_WHISPERER block in the run's log_excerpt capture: engine, "
    "model, device (cuda/cpu), language, status (transcribed | empty | engine_unavailable | error), "
    "word_count, transcript_path, and the BODY (the recognized text). "
    "\n\n"
    "Step 2: render an HTML table with class='exec-report-table' titled "
    "'<strong>Tlamatini Listens &mdash; Transcription Report</strong>' and columns <em>engine</em>, "
    "<em>model</em>, <em>device</em>, <em>language</em>, <em>status</em>, <em>words</em>, "
    "<em>saved transcript</em> &mdash; one row, every value verbatim from the INI_SECTION_WHISPERER "
    "block (do NOT re-classify). Light body cells (background:#ffffff;color:#0f172a), green tint for "
    "status transcribed, amber tint for engine_unavailable. Below the table, quote the recognized "
    "transcript text in a blockquote (or '(no speech detected)' when empty). "
    "\n\n"
    "Step 3: close with one HTML banner reusing the Step 0 style printing, in big letters, "
    "'&#9989; TRANSCRIBED' (status transcribed &mdash; show the word count), "
    "'&#128266; NO SPEECH' (status empty), or '&#9881;&#65039; ENGINE UNAVAILABLE' (status "
    "engine_unavailable &mdash; faster-whisper not installed and no cloud key; note the one-line fix "
    "'pip install faster-whisper'), and underneath a one-line metric "
    "'engine: <engine> &middot; device: <device> &middot; words: <word_count>'. "
    "End with END-RESPONSE."
)


_NEW_PROMPTS = (
    (74, WHISPERER_LISTENS_DEMO),
)


def add_whisperer_demo_prompt(apps, schema_editor):
    Prompt = apps.get_model('agent', 'Prompt')
    for prompt_id, content in _NEW_PROMPTS:
        Prompt.objects.update_or_create(
            idPrompt=prompt_id,
            defaults={'promptName': f'prompt-{prompt_id}', 'promptContent': content},
        )


def remove_whisperer_demo_prompt(apps, schema_editor):
    Prompt = apps.get_model('agent', 'Prompt')
    Prompt.objects.filter(idPrompt__in=[pid for pid, _ in _NEW_PROMPTS]).delete()


class Migration(migrations.Migration):
    dependencies = [
        ('agent', '0124_add_chat_agent_whisperer_tool'),
    ]

    operations = [
        migrations.RunPython(add_whisperer_demo_prompt, remove_whisperer_demo_prompt),
    ]
