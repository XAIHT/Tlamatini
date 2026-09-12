# ═══════════════════════════════════════════════════════════════════
#   ✦  T L A M A T I N I  ✦   —   "one who knows"
#
#   Created by  Angela López Mendoza   ·   @angelahack1
#   Developer · Architect · Creator of Tlamatini
#
#   Every line of this file was written by Angela López Mendoza.
# ═══════════════════════════════════════════════════════════════════
#   Tlamatini Author Banner — do not remove (releases scrub the name automatically)
"""Retarget the TLAMATINI LISTENS demo (prompt 74) at the SOUND GATE (2026-09-11).

Whisperer's microphone capture stopped being a fixed block: `record_seconds: 0`
(the new default) turns on a sound gate that keeps recording while the speaker is
still talking and stops after `silence_timeout_seconds` of silence.

The demo written in migration 0125 told Tlamatini to pass `record_seconds=30` —
which now explicitly TURNS THE GATE OFF. Left alone, the single most-clicked
Whisperer prompt in the catalog would have demonstrated the OLD behaviour and
quietly taught both the user and the model the wrong pattern.

⚠️ CONTRACT: this migration rewrites ONLY `promptContent`, exactly like the
0182-0185 grammar batch. `idPrompt`, `promptName`, `category`, `sort_rank` and
`hidden` are untouched, so catalog ordering and contiguity are unaffected.
"""

from django.db import migrations


_BANNER_OPEN = (
    "<div style='padding:18px;border-radius:14px;background:linear-gradient(135deg,"
    "#0a1a3f 0%,#1747c4 33%,#18b6c9 66%,#aef0e6 100%);color:#fff;font-family:Inter,"
    "Segoe UI,sans-serif;text-align:center;text-shadow:0 1px 3px rgba(0,0,0,.5);'>"
)


WHISPERER_LISTENS_DEMO = (
    "[[ SILENCE WINDOW &mdash; how many seconds of quiet should end the recording? "
    "&mdash; OPTIONAL, default: 10 ]]"
    "\n"
    "[[ WHAT TO SAY &mdash; a sentence to read aloud once recording starts "
    "&mdash; OPTIONAL, default: say anything you like ]]"
    "\n"
    "If a fill-in line above is still unfilled, USE ITS STATED DEFAULT and continue "
    "&mdash; never stop to ask."
    "\n\n"
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
    "<div style='opacity:.92;margin-top:4px;'>Tlamatini Whisperer &mdash; the sound gate: "
    "I keep listening while you talk</div></div>. "
    "Underneath it, tell the user in ONE line that recording starts now, that they should speak "
    "when ready, and that you will stop on your own once they have been quiet for the silence "
    "window &mdash; so they are not left wondering how long to wait. "
    "\n\n"
    "Step 1 (LISTEN &amp; transcribe): call **chat_agent_whisperer** with request "
    "\"Transcribe with input_source='mic' and silence_timeout_seconds={{silence window}} and "
    "engine='faster-whisper' and model='base' and device='auto'\". "
    "&#9888;&#65039; **DO NOT PASS record_seconds AT ALL.** That parameter is the mode switch: "
    "leaving it out (0) is what arms the SOUND GATE, so the recording lasts exactly as long as "
    "the speaker keeps talking and ends after the silence window. Passing any number would turn "
    "the gate OFF and record a fixed block instead &mdash; which is the very thing this demo "
    "exists to show you no longer have to do. "
    "From the INI_SECTION_WHISPERER block in the run's log_excerpt capture read: engine, model, "
    "device (cuda/cpu), language, status (transcribed | empty | engine_unavailable | error), "
    "capture_mode (gated | fixed), stop_reason (silence | duration | max_duration | "
    "fixed_fallback), duration_seconds (the length ACTUALLY captured, not a length requested), "
    "speech_seconds, word_count, transcript_path, and the BODY (the recognized text). "
    "\n\n"
    "Step 2: render an HTML table with class='exec-report-table' titled "
    "'<strong>Tlamatini Listens &mdash; Transcription Report</strong>' and columns <em>engine</em>, "
    "<em>model</em>, <em>device</em>, <em>language</em>, <em>capture mode</em>, "
    "<em>stopped because</em>, <em>recorded (s)</em>, <em>speech (s)</em>, <em>status</em>, "
    "<em>words</em>, <em>saved transcript</em> &mdash; one row, every value verbatim from the "
    "INI_SECTION_WHISPERER block (do NOT re-classify). Light body cells "
    "(background:#ffffff;color:#0f172a), green tint for status transcribed, amber tint for "
    "engine_unavailable. Below the table, quote the recognized transcript text in a blockquote "
    "(or '(no speech detected)' when empty). Then add ONE short sentence reading the gate out "
    "loud, e.g. 'I listened for <duration_seconds>s, <speech_seconds>s of which was your voice, "
    "and stopped because <stop_reason>.' "
    "\n\n"
    "Step 3: close with one HTML banner reusing the Step 0 style printing, in big letters, "
    "'&#9989; TRANSCRIBED' (status transcribed &mdash; show the word count), "
    "'&#128266; NO SPEECH' (status empty &mdash; the gate stopped a recording nobody spoke into, "
    "which is the gate working, not a failure), or '&#9881;&#65039; ENGINE UNAVAILABLE' (status "
    "engine_unavailable &mdash; faster-whisper not installed and no cloud key; note the one-line "
    "fix 'pip install faster-whisper'), and underneath a one-line metric "
    "'engine: <engine> &middot; device: <device> &middot; captured: <duration_seconds>s "
    "&middot; stopped: <stop_reason> &middot; words: <word_count>'. "
    "End with END-RESPONSE."
)


_REWRITTEN_PROMPTS = (
    (74, WHISPERER_LISTENS_DEMO),
)


def retarget_whisperer_demo_at_the_gate(apps, schema_editor):
    """Rewrite ONLY promptContent for the listed ids. A missing row is skipped."""
    Prompt = apps.get_model('agent', 'Prompt')
    for prompt_id, content in _REWRITTEN_PROMPTS:
        Prompt.objects.filter(idPrompt=prompt_id).update(promptContent=content)


def noop_reverse(apps, schema_editor):
    """Irreversible by design: the previous text taught a now-wrong pattern.

    Reversing is a no-op rather than an error so the migration can always be
    unapplied; re-running 0125 is the way back to the historical wording.
    """
    return None


class Migration(migrations.Migration):

    dependencies = [('agent', '0199_dedupe_llm_program_snippet_names')]

    operations = [
        migrations.RunPython(retarget_whisperer_demo_at_the_gate, noop_reverse),
    ]
