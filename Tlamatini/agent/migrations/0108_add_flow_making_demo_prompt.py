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
Seed one Catalog-of-Prompts demo for the **flow-making** skill — turning a plain
objective into a downloadable, canvas-loadable `.flw` by driving the FlowCreator
engine (full 69-agent catalog) end-to-end from chat, through `invoke_skill`.

    69  ALARM FLOW FORGE   builds `alarm_every_3_hours.flw` (a recurring
                           "every 3 hours, Telegram me that another 3-hour lap
                           passed" workflow) and saves it to the user's Desktop
                           Flows folder. ONE invoke_skill('flow-making', ...) call.

Why this prompt is phrased around `invoke_skill` (not just "create a flow"):
- `list_skills` / `invoke_skill` are ACPX-surface tools (`agent.acpx.ACPX_TOOL_NAMES`);
  with the ACPX toolbar toggle OFF they are filtered out and the skill is invisible.
- The catalog auto-sets the toolbar toggles from the prompt text via
  `tools_dialog.js::classifyPromptModes` — which tags a prompt **ACPX** (⇒ also
  Multi-Turn) only when it literally mentions `invoke_skill` / `list_skills` /
  an `acp_*` tool. Naming `invoke_skill` here makes the catalog click auto-enable
  BOTH **Multi-Turn** and **ACPX**, and pushes the planner to select `invoke_skill`.

Placement (append, no renumber)
-------------------------------
The catalog dropdown (static/agent/js/tools_dialog.js) enumerates promptName
'prompt-1','prompt-2',... and BREAKS at the first missing slot, so the catalog
must stay a contiguous, gap-free 'prompt-1..N'. Slots 1-68 are occupied (0107
appended the ESP32er demos at 66-68); this APPENDS at 69 with no shift of any
existing prompt. Reverse deletes 69. (MAX_PROMPTS=100.)
"""
from django.db import migrations


# Flow / water banner palette (deep navy -> teal -> aqua -> sea-foam), echoing the
# "flow" theme, with a text-shadow so the white label stays legible over the
# bright sea-foam end.
_BANNER_OPEN = (
    "<div style='padding:18px;border-radius:14px;background:linear-gradient(135deg,"
    "#06283D 0%,#0E7C86 38%,#1CA7AB 68%,#9BE7D9 100%);color:#fff;font-family:Inter,"
    "Segoe UI,sans-serif;text-align:center;text-shadow:0 1px 3px rgba(0,0,0,.5);'>"
)


ALARM_FLOW_FORGE_DEMO = (
    "Tlamatini, run the **ALARM FLOW FORGE** demo, please &mdash; a one-call showcase of the "
    "**flow-making** skill that turns a plain-language objective into a real, canvas-loadable "
    "`.flw` workflow by driving the FlowCreator engine (it already knows the full 69-agent "
    "catalog and the connection rules). The goal: build a flow named "
    "**alarm_every_3_hours.flw** that, every 3 hours, sends me a Telegram message saying that "
    "another 3-hour lap has passed &mdash; and save it to my Desktop Flows folder. "
    "PRECONDITIONS you can assume are TRUE (do NOT verify them &mdash; trust them and go straight "
    "to Step 1): (a) tick **Multi-Turn** AND **ACPX** before sending (this catalog entry "
    "auto-enables both &mdash; the flow-making skill is reached via **invoke_skill**, an "
    "ACPX-surface tool); (b) Ollama is running locally and the FlowCreator model is available "
    "(the skill queries it to design the flow); (c) do NOT hand-author the `.flw` yourself and "
    "do NOT use acp_spawn / chat_agent_executer &mdash; the ONE tool you call is **invoke_skill**. "
    "\n\n"
    "Step 0: open with one HTML banner &mdash; " + _BANNER_OPEN +
    "<h2 style='margin:0;letter-spacing:2px;'>&#127754; ALARM FLOW FORGE &#9200;</h2>"
    "<div style='opacity:.92;margin-top:4px;'>Tlamatini flow-making &mdash; objective &middot; FlowCreator &middot; .flw</div></div>. "
    "\n\n"
    "Step 1 (forge the flow): call **invoke_skill** with skill_name='flow-making' and "
    "args_json='{\"objective\":\"Every 3 hours, send me a Telegram message telling me that "
    "another 3-hour lap has passed.\",\"out_path\":\"C:/Users/angel/OneDrive/Desktop/Flows/"
    "alarm_every_3_hours.flw\",\"flow_name\":\"alarm_every_3_hours.flw\"}'. The skill copies "
    "the FlowCreator template to an isolated runtime dir, writes its config, runs FlowCreator "
    "(which designs a recurring Telegram-alert flow &mdash; typically Starter &rarr; Telegrammer "
    "&rarr; a 3-hour Sleeper looping back, terminated cleanly), and converts the result into a "
    "schemaVersion-2 `.flw`. The Desktop\\Flows folder is created automatically if it does not "
    "exist. "
    "\n\n"
    "Step 2 (read the result): from the invoke_skill return, capture **flw_path**, "
    "**agent_count**, and **connection_count** and report them in one short HTML table. If the "
    "skill returns ok=false (or its log shows a line beginning with `ERROR`), surface that "
    "message VERBATIM and STOP &mdash; the usual cause is 'Cannot reach Ollama' / 'FlowCreator "
    "timed out' (start Ollama or pass a different model) &mdash; do NOT fabricate a `.flw`. "
    "\n\n"
    "Step 3: close with one HTML banner &mdash; " + _BANNER_OPEN +
    "<h2 style='margin:0;letter-spacing:1px;'>&#9989; FLOW FORGED</h2>"
    "<div style='opacity:.92;margin-top:4px;'>Open it on the ACP designer (Open &#9656; select the "
    ".flw) &mdash; then fill the Telegrammer bot-token and `@username` recipient and press Start.</div></div>. "
    "Remind me that the generated Telegrammer node ships with placeholder credentials I must set "
    "before the alarm can actually send."
)


_NEW_PROMPTS = (
    (69, ALARM_FLOW_FORGE_DEMO),
)


def add_flow_making_demo_prompt(apps, schema_editor):
    Prompt = apps.get_model('agent', 'Prompt')
    for prompt_id, content in _NEW_PROMPTS:
        Prompt.objects.update_or_create(
            idPrompt=prompt_id,
            defaults={'promptName': f'prompt-{prompt_id}', 'promptContent': content},
        )


def remove_flow_making_demo_prompt(apps, schema_editor):
    Prompt = apps.get_model('agent', 'Prompt')
    Prompt.objects.filter(idPrompt__in=[pid for pid, _ in _NEW_PROMPTS]).delete()


class Migration(migrations.Migration):
    dependencies = [
        ('agent', '0107_add_esp32er_demo_prompts'),
    ]
    operations = [
        migrations.RunPython(add_flow_making_demo_prompt, remove_flow_making_demo_prompt),
    ]
