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
Seed a Catalog-of-Prompts demo for **Talker** — Tlamatini's TEXT-TO-SPEECH — run
through the wrapped **chat_agent_talker** Multi-Turn tool. This is the MANDATORY
catalog prompt every Multi-Turn-capable agent must ship (CLAUDE.md ⚠️ directive /
create_new_agent.md Step 7.8 / tlamatini-agent-creation skill Phase 19); Talker
(#75, migrations 0120/0121) shipped without one, so this closes that gap.

    73  TLAMATINI SPEAKS   basic   speak a greeting with voice='tara' -> speak a
                                   second line with voice='leah' -> report a small
                                   table of each call's voice/status/seconds/path.

FEMALE VOICE ONLY by design: Tlamatini is female, so the demo uses ONLY her
permitted female voices (tara/leah/jess/mia/zoe). Talker enforces this itself —
a non-female voice makes it close its execution entirely (see prompt.pmt Rule 17
and talker.py::resolve_voice) — so the demo never asks for anything else.

SAFE to run repeatedly (the daily chat test may execute it): TTS is
observational/output (it plays + saves a WAV), it mutates no persistent state,
and it is NOT in the Exec Report. Audible sound needs snac+torch + a reachable
Ollama serving the Orpheus model; without them Talker still runs and reports
status `tokens_only` (a documented degraded mode, NOT a failure).

Placement (append, no renumber)
-------------------------------
The catalog dropdown (static/agent/js/tools_dialog.js) enumerates promptName
'prompt-1','prompt-2',... and BREAKS at the first missing slot, so the catalog
must stay a contiguous, gap-free 'prompt-1..N'. Slots 1-72 are occupied (0111
appended the Arduiner demos at 70-72); this APPENDS at 73 with no shift of any
existing prompt. Reverse deletes 73. (MAX_PROMPTS=100.)
"""
from django.db import migrations


# Talker banner palette — mirrors the ``.canvas-item.talker-agent`` gradient
# (deep wine -> terracotta -> warm amber -> cream), with a text-shadow so the
# white label stays legible across the bright cream end.
_BANNER_OPEN = (
    "<div style='padding:18px;border-radius:14px;background:linear-gradient(135deg,"
    "#5b1d2e 0%,#c1462e 33%,#f2a35e 66%,#ffe3a3 100%);color:#fff;font-family:Inter,"
    "Segoe UI,sans-serif;text-align:center;text-shadow:0 1px 3px rgba(0,0,0,.5);'>"
)


TALKER_SPEAKS_DEMO = (
    "Tlamatini, run the **TLAMATINI SPEAKS** demo, please &mdash; a basic showcase of your own "
    "TEXT-TO-SPEECH voice, driven entirely from chat through the wrapped **chat_agent_talker** "
    "tool: you synthesise short lines of speech with two of your FEMALE voices and play them on "
    "the speakers, then report what was spoken. "
    "PRECONDITIONS you can assume are TRUE (do NOT verify them &mdash; go straight to Step 1): "
    "(a) tick ONLY the **Multi-Turn** checkbox before sending (ACPX is NOT required &mdash; "
    "chat_agent_talker is the ONLY tool you may use; do NOT use chat_agent_executer / "
    "chat_agent_pythonxer / acp_spawn); (b) hearing the audio needs a reachable Ollama serving "
    "the Orpheus model plus `snac`+`torch` installed &mdash; if they are absent Talker still runs "
    "and returns status `tokens_only` (a documented degraded mode, NOT a failure): record it "
    "verbatim and CONTINUE. "
    "VOICE RULE (by design, non-negotiable): you are FEMALE and you speak ONLY with a female "
    "voice &mdash; tara (preferred), leah, jess, mia, or zoe. Use ONLY these. "
    "Each step is exactly ONE chat_agent_talker call shaped \"Speak with input_text='<text>' and "
    "voice='<female voice>'\". After each call read the JSON return (an INI_SECTION_TALKER block "
    "under the run's log_excerpt) and capture voice / gender / status / audio_seconds / "
    "output_path plus the body. "
    "\n\n"
    "Step 0: open with one HTML banner &mdash; " + _BANNER_OPEN +
    "<h2 style='margin:0;letter-spacing:2px;'>&#128483;&#65039; TLAMATINI SPEAKS &#127908;</h2>"
    "<div style='opacity:.92;margin-top:4px;'>Tlamatini Talker &mdash; her own voice, always female</div></div>. "
    "\n\n"
    "Step 1 (greeting in her default voice): call **chat_agent_talker** with request "
    "\"Speak with input_text='Hello, I am Tlamatini. This is my voice.' and voice='tara'\". "
    "From the INI_SECTION_TALKER block capture voice (tara), gender (female), status "
    "(spoken / saved / tokens_only), audio_seconds and output_path. "
    "\n\n"
    "Step 2 (a second female voice): call **chat_agent_talker** with request "
    "\"Speak with input_text='And this is another of my voices.' and voice='leah'\". "
    "Capture the same fields (voice=leah, gender=female). "
    "\n\n"
    "Step 3: render an HTML table with class='exec-report-table' titled "
    "'<strong>Tlamatini Speaks &mdash; Voice Report</strong>' and columns <em>step</em>, "
    "<em>voice</em>, <em>gender</em>, <em>status</em> (spoken|saved|tokens_only|error), "
    "<em>seconds</em>, <em>saved WAV</em> &mdash; one row per call in execution order, every value "
    "verbatim from the INI_SECTION_TALKER block (do NOT re-classify). Light body cells "
    "(background:#ffffff;color:#0f172a; or striped #f1f5f9), green tint for spoken, amber tint for "
    "tokens_only. "
    "\n\n"
    "Step 4: close with one HTML banner reusing the Step 0 style printing, in big letters, "
    "'&#9989; SPOKEN' (both calls returned status spoken &mdash; the audio played), "
    "'&#128266; SAVED, NOT PLAYED' (status saved), or '&#128221; TOKENS ONLY' (status tokens_only "
    "&mdash; no vocoder/Ollama, the audio tokens were saved instead), and underneath a one-line "
    "metric 'voices: tara, leah &middot; status: <s1>/<s2> &middot; audio: <sec1>s + <sec2>s'. "
    "End with END-RESPONSE."
)


_NEW_PROMPTS = (
    (73, TALKER_SPEAKS_DEMO),
)


def add_talker_demo_prompt(apps, schema_editor):
    Prompt = apps.get_model('agent', 'Prompt')
    for prompt_id, content in _NEW_PROMPTS:
        Prompt.objects.update_or_create(
            idPrompt=prompt_id,
            defaults={'promptName': f'prompt-{prompt_id}', 'promptContent': content},
        )


def remove_talker_demo_prompt(apps, schema_editor):
    Prompt = apps.get_model('agent', 'Prompt')
    Prompt.objects.filter(idPrompt__in=[pid for pid, _ in _NEW_PROMPTS]).delete()


class Migration(migrations.Migration):
    dependencies = [
        ('agent', '0121_add_chat_agent_talker_tool'),
    ]

    operations = [
        migrations.RunPython(add_talker_demo_prompt, remove_talker_demo_prompt),
    ]
