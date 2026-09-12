# ═══════════════════════════════════════════════════════════════════
#   ✦  T L A M A T I N I  ✦   —   "one who knows"
#
#   Created by  Angela López Mendoza   ·   @angelahack1
#   Developer · Architect · Creator of Tlamatini
#
#   Every line of this file was written by Angela López Mendoza.
# ═══════════════════════════════════════════════════════════════════
#   Tlamatini Author Banner — do not remove (releases scrub the name automatically)
"""Catalog of Prompts — the NEW **VOICE COMMANDS** section (Angela, 2026-09-12).

WHAT THIS IS. A voice command is not "record some audio" and it is not "read this
text aloud" — it is **driving Tlamatini BY speaking**: the microphone becomes the
keyboard, Whisperer's transcript becomes the prompt, and Tlamatini then executes
that prompt with her full tool surface. That is a different thing from everything
in *Media & Voice* (which is about PRODUCING or CONSUMING media: record a WAV,
play a file, speak a sentence, transcribe a clip), so it gets its own section.

WHY IT IS ONLY POSSIBLE NOW. Until v1.51.7 Whisperer recorded a FIXED block of
``record_seconds`` (default 30). A spoken prompt that ran long was cut in half,
and a short one left you talking to an empty room — so "say your prompt out loud"
was never trustworthy enough to put on a card. The **sound gate**
(``record_seconds: 0``, the new default) keeps recording while you are still
talking and stops on its own after ``silence_timeout_seconds`` of silence. THAT is
what makes "speak until you are done" a real, shippable feature, and this section
is its user-facing face.

WHY IT IS FIRST IN THE CATALOG. Angela's explicit instruction: this section goes
at the **VERY BEGINNING**, ahead of *Getting Started*. Speaking is the shortest
path to using Tlamatini at all — you talk, she does it — so it is the first thing
a new user should meet. ``views.PROMPT_CATEGORY_ORDER`` therefore gains
``('voice_commands', 'Voice Commands')`` as entry ZERO. The section header renders
uppercase (``.prompt-category-label { text-transform: uppercase }``), so on screen
it reads exactly **VOICE COMMANDS**.

TWO CARDS, DELIBERATELY:

  * **121 — YOUR FIRST VOICE COMMAND** (``sort_rank`` 10). The section's
    Step-by-Step opener. ⚠️ This is NOT optional padding: Angela's standing rule
    is that *every* section opens with a guided wizard, and
    ``test_prompt_catalog_contiguous.py`` enforces it in two places
    (``test_known_section_openers`` fails for any live section missing from its
    map, and ``test_every_section_opens_with_a_genuine_step_by_step_wizard``
    checks the opener's CONTENT names the Step-by-Step checkbox and promises to
    WAIT). A new section shipped with only one card would go RED.
  * **122 — SPEAK YOUR PROMPT** (``sort_rank`` 20). Angela's card, carrying her
    sentence VERBATIM:
        "Tlamatini, using Whisperer record my voice till I finish to tell you a
         prompt, then use the text extracted as a prompt and invoke it, go!."

MODE BADGES — the natures Angela asked for, produced by CONTENT not by a flag.
``tools_dialog.js::classifyPromptModes`` reads the text and decides, and clicking
the card then ticks exactly those boxes (``applyPromptModesToToggles``):

  * 122 names ``invoke_skill`` / ``acp_spawn`` / ``acp_send_and_wait`` in a
    NON-forbidding sentence ⇒ **ACPX** ⇒ ``['multiturn', 'acpx', 'execreport']``
    = Multi-turn + ACPX + Exec-report, exactly as requested. The ACPX tick is not
    decoration: neither the user nor the model knows what the spoken instruction
    will turn out to need, so the ACPX/Skills surface must ALREADY be bound when
    the transcript lands — with ACPX unchecked, ``filter_acpx_tools`` strips it
    before the executor ever sees it, and a spoken "ask Codex about X" would die
    with no tool to serve it. 122 contains NO hyphenated "step-by-step" token, so
    it is never mis-badged as a wizard.
  * 121 names the Step-by-Step checkbox (and says "Step-by-Step mode"), drives
    ``chat_agent_whisperer``, and contains no ``acp_*`` token ⇒
    ``['multiturn', 'stepbystep', 'execreport']`` — the same shape as every other
    section opener.

CONTRACT COMPLIANCE (all of it, on purpose):
  * APPEND-ONLY ids. 0198 left the catalog at 120, so these are **121** and
    **122** — appended, never renumbered
    (``test_ids_are_contiguous_1_to_n_no_gaps``).
  * ``sort_rank`` 10 / 20. Rank 10 is the RESERVED opener slot; ranks are unique
    inside a section; the section reads least-complex → most-complex (rehearse
    with a guided wizard first, then hand the microphone the real controls).
  * Parameter grammar v1.44.0: ``[[ … — OPTIONAL, default: X ]]`` collected at the
    TOP with the unfilled-guard sentence beneath, so a one-click run still works;
    ``< >`` marks REPORT slots only, never inputs.
  * No hardcoded scratch path (Rules 15/16) — Whisperer writes to its own
    Documents folder.
  * SAFE: the opener rehearses with READ-ONLY actions only, and 122 carries an
    explicit brake — an irreversible spoken instruction is quoted back for
    written confirmation instead of being executed blind.

Reverse deletes exactly these two rows.
"""
from django.db import migrations


_BANNER_OPEN = (
    "<div style='padding:18px;border-radius:14px;background:linear-gradient(135deg,"
    "#160a2e 0%,#5B21B6 33%,#2563EB 66%,#22D3EE 100%);color:#fff;font-family:Inter,"
    "Segoe UI,sans-serif;text-align:center;text-shadow:0 1px 3px rgba(0,0,0,.5);'>"
)


# ─────────────────────────────────────────────────────────────────────
#  121 · the section's Step-by-Step opener
# ─────────────────────────────────────────────────────────────────────
FIRST_VOICE_COMMAND = (
    "FILL IN (optional — leave them exactly as they are for a one-click demo):\n"
    "  · Which microphone to listen on: "
    "[[ device_name — OPTIONAL, default: the system default mic ]]\n"
    "  · How many seconds of quiet mean I have stopped talking: "
    "[[ silence_timeout_seconds — OPTIONAL, default: 10 ]]\n"
    "If a fill-in line above is still unfilled, USE ITS STATED DEFAULT and "
    "continue — never stop to ask me.\n\n"

    "Tlamatini, run the YOUR FIRST VOICE COMMAND demo, please — the guided "
    "introduction to talking to you instead of typing. Tick the **Multi-Turn**, "
    "**Exec report** and **Step-by-Step** checkboxes before sending. "
    "Step-by-Step mode is the whole point of this card: perform ONE action, then "
    "STOP and WAIT for my reply before you do the next one. Never put two steps "
    "in a single answer, and never answer a step I have not reached yet.\n\n"

    "Step 0 — open with one HTML banner: " + _BANNER_OPEN +
    "<h2 style='margin:0;letter-spacing:2px;'>🎙️ YOUR FIRST VOICE COMMAND</h2>"
    "<div style='opacity:.92;margin-top:4px;'>the microphone is the keyboard</div>"
    "</div>. Under it, explain in TWO short sentences what a voice command "
    "actually is: I speak, you transcribe what I said with chat_agent_whisperer, "
    "and the words I spoke become the instruction you then carry out — the "
    "microphone replaces the keyboard, nothing else changes. Then ask me to reply "
    "READY once my microphone is plugged in and the room is reasonably quiet. "
    "STOP THERE and WAIT for my READY.\n\n"

    "Step 1 (ONLY after I reply READY) — a listening test, so we find out whether "
    "the machine can hear me at all before we trust it with an instruction. Call "
    "**chat_agent_whisperer** with request \"Transcribe with input_source='mic' "
    "and silence_timeout_seconds={{silence window}} and engine='faster-whisper' "
    "and model='base' and device='auto'\", adding device_name='{{device name}}' "
    "only if I named one. ⚠️ **Leave record_seconds out entirely.** Omitting it "
    "is what arms the SOUND GATE, so the recording lasts exactly as long as I "
    "keep talking and ends by itself after the silence window; passing any number "
    "would switch the gate off and record a fixed block instead. Before you call "
    "it, tell me in ONE line to say a short test sentence out loud now. "
    "Afterwards read the INI_SECTION_WHISPERER block out of the run's "
    "log_excerpt and report, in a small HTML table: status <status>, what you "
    "heard <the recognized text>, how it stopped <stop_reason>, how long it "
    "listened <duration_seconds>, how much of that was my voice <speech_seconds>, "
    "and which engine and device ran it <engine / device>. Then ask me to reply "
    "YES if that is what I said, or NO if it is wrong. STOP and WAIT.\n\n"

    "Step 2 (ONLY after I reply) — if I said NO, tell me the two things that fix "
    "it almost every time (pick another microphone with device_name, or use a "
    "larger model such as 'small' or 'large-v3-turbo') and offer to repeat Step 1; "
    "then STOP and WAIT. If I said YES, now rehearse a REAL voice command: tell me "
    "to speak an instruction this time rather than a sentence, and suggest a "
    "harmless one out loud, for example asking you what the time is or how many "
    "agents you have. Call chat_agent_whisperer exactly as in Step 1, quote the "
    "transcript back to me word for word in a blockquote, and then CARRY OUT what "
    "I said — but for this rehearsal restrict yourself to READ-ONLY work "
    "(answering, listing, counting, summarizing). If what I spoke would write, "
    "delete, send, install, spend money or touch a machine that is not mine, "
    "stop: quote it back, say plainly that the rehearsal stays read-only, and "
    "point me at the SPEAK YOUR PROMPT card in this same section, which is built "
    "for the real thing. Then ask me to reply DONE. STOP and WAIT.\n\n"

    "Step 3 (ONLY after I reply DONE) — close with a VOICE READINESS REPORT: one "
    "HTML table in the Step 0 colours holding microphone <device>, engine and "
    "model <engine / model>, silence window <silence_timeout_seconds>, "
    "transcription quality as I judged it <YES or NO from Step 1>, and whether "
    "the rehearsed command ran <yes / held back because it was not read-only>. "
    "Underneath it, ONE sentence telling me the next card to try is SPEAK YOUR "
    "PROMPT, where whatever I say becomes the prompt you actually run. "
    "End with END-RESPONSE."
)


# ─────────────────────────────────────────────────────────────────────
#  122 · Angela's card — her sentence is the operative instruction
# ─────────────────────────────────────────────────────────────────────
SPEAK_YOUR_PROMPT = (
    "FILL IN (optional — leave them exactly as they are for a one-click demo):\n"
    "  · How many seconds of quiet mean I have finished speaking: "
    "[[ silence_timeout_seconds — OPTIONAL, default: 10 ]]\n"
    "  · The language I will speak in: "
    "[[ language — OPTIONAL, default: auto-detect ]]\n"
    "If a fill-in line above is still unfilled, USE ITS STATED DEFAULT and "
    "continue — never stop to ask me.\n\n"

    "Tlamatini, run the SPEAK YOUR PROMPT demo, please. This is the card where my "
    "VOICE is the prompt, and here is the instruction, in my own words:\n\n"
    "  «Tlamatini, using Whisperer record my voice till I finish to tell you a "
    "prompt, then use the text extracted as a prompt and invoke it, go!.»\n\n"

    "Step 0 — open with one HTML banner: " + _BANNER_OPEN +
    "<h2 style='margin:0;letter-spacing:2px;'>🗣️ SPEAK YOUR PROMPT</h2>"
    "<div style='opacity:.92;margin-top:4px;'>say it — I will do it</div></div>. "
    "Under it, ONE line telling me that recording starts right now, that I should "
    "speak when I am ready, and that you will stop on your own once I have been "
    "quiet for the silence window — so I am never left wondering how long to "
    "wait.\n\n"

    "Step 1 (LISTEN UNTIL I FINISH) — call **chat_agent_whisperer** with request "
    "\"Transcribe with input_source='mic' and "
    "silence_timeout_seconds={{silence window}} and engine='faster-whisper' and "
    "model='base' and device='auto' and language='{{language}}'\". ⚠️ **Leave "
    "record_seconds out entirely.** That parameter is the mode switch: omitting "
    "it (0) is what arms the SOUND GATE, so I can take as long as I need to say "
    "what I want and the recording ends by itself once I stop — passing any "
    "number would cut me off mid-sentence at a fixed length, which is the exact "
    "thing this card exists to prove you no longer have to do. From the "
    "INI_SECTION_WHISPERER block in the run's log_excerpt read: status, "
    "capture_mode, stop_reason, duration_seconds (the length ACTUALLY captured, "
    "never a length requested), speech_seconds, word_count, transcript_path, and "
    "the BODY, which is the recognized text.\n\n"

    "Step 2 (READ IT BACK BEFORE YOU ACT) — quote the transcript to me word for "
    "word in a blockquote, exactly as Whisperer returned it, with no tidying and "
    "no guessing at words you did not get. That quote is now your instruction. "
    "⚠️ HONESTY GATE: if status came back `empty` (the gate stopped a recording "
    "nobody spoke into) or `engine_unavailable` (faster-whisper is not installed "
    "and no cloud key is set — the one-line fix is `pip install faster-whisper`), "
    "then say so plainly and STOP. Inventing a plausible prompt because you could "
    "not hear me is the single worst thing you could do on this card.\n\n"

    "Step 3 (NOW INVOKE IT) — treat that transcript as the prompt I typed, and "
    "carry it out properly: plan it, pick the right tools, run them, and answer "
    "it in full. Do not merely describe what you would have done. One brake, and "
    "only one: if what I spoke would delete or overwrite something, message a "
    "real person, spend money, or reach a machine that is not mine, then do the "
    "safe part, quote the risky part back to me in writing, and ask me to confirm "
    "it in text before you go any further — my voice is enough to start work, and "
    "my typing is what authorises the irreversible kind.\n\n"

    "Step 4 (SHOW YOUR WORK) — finish with an HTML table with "
    "class='exec-report-table' titled '<strong>Voice Command — Run "
    "Report</strong>' holding: what I said <the transcript>, how it was captured "
    "<capture_mode>, why it stopped <stop_reason>, seconds listened "
    "<duration_seconds>, seconds of speech <speech_seconds>, words <word_count>, "
    "which tools you then ran <tool names in order>, and the outcome "
    "<done / partly done and awaiting my written confirmation / could not hear "
    "me>. Then close with one banner in the Step 0 colours reading "
    "'✅ VOICE COMMAND EXECUTED', '✋ WAITING FOR YOUR WRITTEN OK' or "
    "'🔇 I HEARD NOTHING', whichever is the truth.\n\n"

    "PRE-FLIGHT: tick the **Multi-Turn**, **Exec report** and **ACPX** "
    "checkboxes. The ACPX tick is deliberate and load-bearing: neither of us "
    "knows in advance what I am about to say, so your whole tool surface has to "
    "be in your hands already by the time the transcript arrives — the skills "
    "(invoke_skill, list_skills) and the external coding agents (acp_spawn, "
    "acp_send_and_wait) included. With ACPX unticked those tools are filtered out "
    "before you ever see them, and a spoken instruction that happens to need one "
    "would die with nothing to serve it. Whisperer is only the microphone; the "
    "words I speak decide which tools follow. End with END-RESPONSE."
)


# (idPrompt, sort_rank, promptContent) — ids APPENDED after 120 (0198) and never
# renumbered; rank 10 is the reserved Step-by-Step opener slot, 20 is Angela's
# card. Both land in the brand-new 'voice_commands' section.
_NEW_PROMPTS = (
    (121, 10, FIRST_VOICE_COMMAND),
    (122, 20, SPEAK_YOUR_PROMPT),
)


def add_voice_command_prompts(apps, schema_editor):
    Prompt = apps.get_model('agent', 'Prompt')
    for prompt_id, rank, content in _NEW_PROMPTS:
        Prompt.objects.update_or_create(
            idPrompt=prompt_id,
            defaults={
                'promptName': 'prompt-%d' % prompt_id,
                'promptContent': content,
                'category': 'voice_commands',
                'sort_rank': rank,
            },
        )


def remove_voice_command_prompts(apps, schema_editor):
    Prompt = apps.get_model('agent', 'Prompt')
    Prompt.objects.filter(
        idPrompt__in=[prompt_id for prompt_id, _rank, _content in _NEW_PROMPTS]
    ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('agent', '0200_whisperer_demo_prompt_sound_gate'),
    ]

    operations = [
        migrations.RunPython(add_voice_command_prompts, remove_voice_command_prompts),
    ]
