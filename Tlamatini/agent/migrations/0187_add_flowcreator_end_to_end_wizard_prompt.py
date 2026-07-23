# ═══════════════════════════════════════════════════════════════════
#   ✦  T L A M A T I N I  ✦   —   "one who knows"
#   Created by  Angela López Mendoza · @angelahack1
# ═══════════════════════════════════════════════════════════════════
"""Catalog of Prompts — the FLOWCREATOR END-TO-END wizard (Angela, 2026-07-23).

A richer companion to the simple "make me a .flw" demo (#107 from 0186). This is
a full **Step-by-Step** wizard that walks the user all the way from a sentence to
a RUNNING flow:

  a) CREATE a flow with `chat_agent_flowcreator` — "monitor a GlassFish log and,
     on an ERROR, send me a Telegram with a summary" -> a real `.flw` on disk.
  b) OPEN that `.flw` in the Agentic Control Panel (agentic_control_panel.html).
  c) GUIDE the user, one action at a time, to change EVERY parameter that matters
     — the Monitor-Log file path, and the Telegrammer identity / recipient /
     api_id+api_hash or bot token / message — then VALIDATE, optionally fire a
     safe test error, and START the flow so it runs completely.

Contract compliance:
  * Category `agents_flows`; `sort_rank = 90` so it sits right after the simple
    FlowCreator create-demo (#107, rank 85) and the ALARM FLOW FORGE demo
    (#33, rank 80) — least-complex -> most-complex within the section.
  * Appended at the next free `idPrompt` (never renumber). It is a genuine
    Step-by-Step wizard (ticks Multi-Turn + Step-by-Step, ONE action per turn,
    STOP and WAIT for the user's READY between steps).
  * Drives `chat_agent_flowcreator` with a realistic, SAFE objective.
  * SECURITY: the wizard NEVER asks the user to type a Telegram api_id / api_hash
    / bot token into the chat — those go straight into the Telegrammer node's
    config dialog on the canvas. The live "fire a test error" step is opt-in and
    gated on the user confirming their own authorized credentials.
  * Parameter grammar (v1.44.0): `[[ ]]` = a value the USER fills in at the TOP;
    `< >` = a report slot only. No `{{ }}` needed here.

Reverse deletes exactly this row (matched by its unique promptContent).
"""
from django.db import migrations

DEMO_PROMPT = (
    "Tlamatini, be my <b>FLOWCREATOR END-TO-END WIZARD</b> — take me from a plain "
    "sentence all the way to a RUNNING flow that watches my GlassFish log and pings me "
    "on Telegram when it sees an error. Do it <b>one step at a time</b>.<br><br>"

    "PRECONDITIONS: tick <b>Multi-Turn</b> AND <b>Step-by-Step</b> in the toolbar (clicking "
    "this card already ticks them). Leave ACPX, Ask Execs and Add-internet unticked.<br><br>"

    "FILL THESE IN — replace the text inside the [[ ]] brackets (all OPTIONAL; if I leave a "
    "bracket untouched, USE THE DEFAULT and do NOT ask me):<br>"
    "• GLASSFISH LOG PATH: [[ the full path to your server.log — OPTIONAL, default: "
    "C:/glassfish7/glassfish/domains/domain1/logs/server.log ]]<br>"
    "• SEND THE ALERT TO: [[ your Telegram @username, +phone, or a saved contact name — "
    "OPTIONAL, default: @your_telegram_username ]]<br>"
    "• SEND AS: [[ <b>me</b> (from your own Telegram account) or <b>bot</b> (from a BotFather "
    "bot) — OPTIONAL, default: bot ]]<br>"
    "• ALERT MESSAGE PREFIX: [[ a short prefix shown before the error summary — OPTIONAL, "
    "default: \"⚠️ GlassFish ALERT —\" ]]<br>"
    "• FLOW FILE NAME: [[ OPTIONAL, default: glassfish_error_alert.flw ]]<br><br>"

    "🔒 SECURITY RULE (never break it): you will NEVER ask me to type my Telegram "
    "<code>api_id</code> / <code>api_hash</code> / <code>bot_token</code> into this chat. Secret "
    "keys ONLY ever get typed directly into the Telegrammer node's config dialog on the canvas. "
    "If a step would need a secret, you tell me where to paste it on the canvas — you never "
    "collect it here.<br><br>"

    "HOW YOU MUST BEHAVE — this is the whole point: perform EXACTLY ONE action per turn, then "
    "STOP and WAIT for me. After each action, show me the concrete result, then end with the "
    "single line telling me exactly what to reply (usually <code>READY</code>). Never chain two "
    "steps. Never assume my reply. If something fails, tell me plainly what failed and what to "
    "check, and wait — never skip ahead.<br><br>"

    "THE STEPS:<br><br>"

    "<b>STEP 1 — CREATE THE FLOW.</b> Call <code>chat_agent_flowcreator</code> EXACTLY ONCE with "
    "<code>prompt='Monitor the GlassFish server log file at &lt;GLASSFISH LOG PATH&gt; for lines "
    "containing ERROR, SEVERE, FATAL or Exception; when one is found, summarize the error and "
    "send the summary to &lt;SEND THE ALERT TO&gt; on Telegram'</code> and "
    "<code>flow_filename='&lt;FLOW FILE NAME&gt;'</code> (substitute my fill-ins). Read the "
    "<code>INI_SECTION_FLOWCREATOR</code> block and report: the <code>status</code>, the FULL "
    "<code>flw_path</code> &lt;flw_path&gt; (I need it to open the file), the <code>agent_count</code> "
    "and <code>connection_count</code>, and the agents it chose in execution order (you should see "
    "roughly Starter → Monitor-Log → Raiser → Summarizer → Parametrizer → Telegrammer → Ender). "
    "If <code>status</code> is <code>error</code>, say so and quote the message — do NOT pretend a "
    "flow was made. Then ask me to reply <code>READY</code>. WAIT.<br><br>"

    "<b>STEP 2 — OPEN THE FLOW IN THE CONTROL PANEL.</b> Do NOT call a tool. Tell me to open the "
    "<b>Agentic Control Panel</b> (the navbar link, or the URL <code>/agent/agentic_control_panel/</code>), "
    "then <b>File ▸ Open</b> and pick the <code>.flw</code> at the &lt;flw_path&gt; from STEP 1. "
    "Tell me I should now see the whole chain drawn left-to-right on the canvas. Ask me to reply "
    "<code>READY</code> once I can see the flow. WAIT.<br><br>"

    "<b>STEP 3 — SET THE LOG FILE PATH (Monitor-Log).</b> Tell me to double-click the "
    "<b>Monitor-Log</b> node to open its config, set <code>logfile_path</code> to my GLASSFISH LOG "
    "PATH, and (optionally) set <code>keywords</code> to <code>ERROR, SEVERE, FATAL, Exception</code>, "
    "then Save. Explain in one line that this is the file it will watch. Ask me to reply "
    "<code>READY</code>. WAIT.<br><br>"

    "<b>STEP 4 — SET THE TELEGRAM IDENTITY + RECIPIENT (Telegrammer).</b> Tell me to double-click "
    "the <b>Telegrammer</b> node and set: <code>telegram.provider</code> = <code>user</code> if I "
    "chose 'me' or <code>bot</code> if I chose 'bot'; <code>telegram.chat_id</code> (or "
    "<code>contact_name</code>) = my SEND-THE-ALERT-TO value; and <code>message</code> = my ALERT "
    "MESSAGE PREFIX (note: the flow's Parametrizer auto-fills the actual error summary into the "
    "message at runtime, so the prefix is just the lead-in). Save. Ask me to reply <code>READY</code>. "
    "WAIT.<br><br>"

    "<b>STEP 5 — ENTER THE TELEGRAM SECRET KEYS ON THE CANVAS (never in chat).</b> Tell me, in the "
    "SAME Telegrammer node dialog: if I chose <b>bot</b>, paste my BotFather <code>telegram.bot_token</code> "
    "(and make sure I have pressed Start / messaged the bot once from the recipient account); if I "
    "chose <b>me</b>, paste my <code>telegram.api_id</code> and <code>telegram.api_hash</code> from "
    "<code>https://my.telegram.org</code> (a one-time headed Telegram login window will appear the "
    "first time). Point me at <b>Config ▸ Access Keys Wizard</b> as the easy way to set these once. "
    "Remind me these are secrets — I type them into the node, NEVER into this chat. Save. Ask me to "
    "reply <code>READY</code> once the keys are in. WAIT.<br><br>"

    "<b>STEP 6 — VALIDATE THE FLOW.</b> Tell me to click <b>Validate</b> on the canvas and read back "
    "the result. If it is clean, say so. If it shows warnings/errors, help me interpret the first one "
    "and what to fix (a missing connection, an empty required field). Ask me to reply <code>READY</code> "
    "once Validate is clean. WAIT.<br><br>"

    "<b>STEP 7 — OPTIONAL LIVE TEST (opt-in, safe).</b> Ask me whether I want to prove it end-to-end "
    "by writing a single fake <code>ERROR</code> line into the log so Monitor-Log trips and a real "
    "Telegram fires. Only if I reply <code>TESTNOW</code> AND confirm my keys are real and the "
    "recipient is authorized: use <code>chat_agent_file_creator</code> (or "
    "<code>chat_agent_executer</code>) to append one line like "
    "<code>[2026-01-01T00:00:00] SEVERE  Test error injected by the Tlamatini wizard</code> to my "
    "GlassFish log path, then tell me to watch for the Telegram. If I reply <code>SKIP</code>, skip "
    "this step entirely and do NOT write anything. WAIT for <code>TESTNOW</code> or <code>SKIP</code>.<br><br>"

    "<b>STEP 8 — RUN IT.</b> Tell me to click <b>Start</b> (▶) on the canvas and confirm the node LEDs "
    "go green and the Starter kicks off Monitor-Log, which now watches my file. Explain in one line "
    "that the flow will keep running and will Telegram me whenever a matching error appears. Ask me to "
    "reply <code>READY</code> once it is running. WAIT.<br><br>"

    "<b>STEP 9 — WRAP UP.</b> Render one HTML table with class='exec-report-table' titled "
    "'GlassFish → Telegram — What We Built' with columns step / node / what you set — one row per step "
    "2..8, every value the real one I used. Keep body cells light (background:#ffffff;color:#0f172a). "
    "Under it, print: the FULL &lt;flw_path&gt;, a one-line reminder that I can re-open and tweak it "
    "any time from the Control Panel, and how to STOP it (the Stop/⏹ button). End with END-RESPONSE."
)


def add_prompt(apps, schema_editor):
    Prompt = apps.get_model('agent', 'Prompt')
    if Prompt.objects.filter(promptContent=DEMO_PROMPT).exists():
        return
    next_pid = (Prompt.objects.order_by('-idPrompt').values_list('idPrompt', flat=True).first() or 0) + 1
    Prompt.objects.update_or_create(
        idPrompt=next_pid,
        defaults={
            'promptName': f'prompt-{next_pid}',
            'promptContent': DEMO_PROMPT,
            'category': 'agents_flows',
            'hidden': False,
            # 33 (ALARM FLOW FORGE) = rank 80, 107 (simple FlowCreator create-demo)
            # = rank 85; this full end-to-end wizard is the most advanced, so 90.
            'sort_rank': 90,
        },
    )


def remove_prompt(apps, schema_editor):
    apps.get_model('agent', 'Prompt').objects.filter(promptContent=DEMO_PROMPT).delete()


class Migration(migrations.Migration):

    dependencies = [('agent', '0186_add_chat_agent_flowcreator')]

    operations = [migrations.RunPython(add_prompt, remove_prompt)]
