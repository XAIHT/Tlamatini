# ═══════════════════════════════════════════════════════════════════
#   ✦  T L A M A T I N I  ✦   —   "one who knows"
#   Created by  Angela López Mendoza · @angelahack1
# ═══════════════════════════════════════════════════════════════════
"""FlowCreator becomes callable from CHAT: prompt in -> .flw file out.

Angela, 2026-07-22: "I JUST NEED A FLOWCREATOR AGENT WRAPPED TO CREATE .FLW
FILES BASED IN A PROMPT ... INPUT: A PROMPT, OUTPUT: A SIMPLE .flw FILE".

Until now FlowCreator was canvas-only: the node's Save button POSTed to
execute_flowcreator/, and the browser JS rendered flow_result.json onto the
canvas. There was no way to say "create me a flow that does X" in chat and get
a file back.

This migration seeds the two DB rows the wrapped tool needs. The code side is:
  * chat_agent_registry.py  -> ChatWrappedAgentSpec(key="flowcreator", ...)
  * agents/flowcreator/flowcreator.py -> now ALSO writes a real .flw (via the
    vendored result_to_flw.convert) and exits NON-ZERO on failure
  * agents/flowcreator/result_to_flw.py -> vendored converter (pool agents can
    never import agent.*, so it ships inside the template dir)

WHY THE EXIT-CODE CHANGE MATTERED: chat_agent_runtime maps exit 0 -> "completed".
flowcreator.py used to `sys.exit(0)` on EVERY path — including "no prompt",
"Ollama unreachable" and "unparseable response" — so a wrapped run that created
nothing would have been reported to the user as a SUCCESS, with a green Exec
Report row. The canvas path is unaffected: check_flowcreator_result_view keys
off the PID file + flow_result.json, never the exit code.

Rows seeded here:
  1. Tool row 'Chat-Agent-FlowCreator' — the wrapper half of the dual enable
     gate (the Agent row 'FlowCreator' already exists from migration 0031), so
     the tool is toggleable under Configure Mcps/Tools.
  2. Catalog prompt — MANDATORY for every Multi-Turn agent. Appended at the
     next free idPrompt (never renumber) with sort_rank 85 so it lands right
     after the ALARM FLOW FORGE demo (#33, rank 80) inside Agents & Flows.
"""
from django.db import migrations

TOOL_DESCRIPTION = 'Chat-Agent-FlowCreator'

DEMO_PROMPT = (
    "Tlamatini, use <b>FlowCreator</b> to CREATE A FLOW for me, please - I want a real "
    "<code>.flw</code> file I can open in the Agentic Control Panel.<br><br>"
    "FILL THIS IN - replace the text inside the [[ ]] brackets:<br>"
    "- WHAT THE FLOW SHOULD DO: [[ DESCRIBE THE OBJECTIVE IN PLAIN WORDS - include the real "
    "paths, patterns, recipients and thresholds. OPTIONAL, default: monitor the GlassFish "
    "server log at C:/glassfish/domains/domain1/logs/server.log and, when an ERROR line "
    "appears, summarize it and send me that summary on Telegram ]]<br>"
    "- FILE NAME: [[ THE .flw FILE NAME - OPTIONAL, default: my_flow.flw ]]<br><br>"
    "If I left the brackets untouched, just use the defaults above - do NOT ask me, go ahead.<br><br>"
    "Tick ONLY the <b>Multi-Turn</b> checkbox. Use ONLY the <code>chat_agent_flowcreator</code> "
    "tool: call it with <code>prompt='&lt;the objective above, in full&gt;'</code> and "
    "<code>flow_filename='&lt;the file name above&gt;'</code>. Pass my WHOLE objective in "
    "<code>prompt</code> - the flow designer only sees that text, so any path or recipient you "
    "leave out will be missing from the flow.<br><br>"
    "When it finishes, read the <code>INI_SECTION_FLOWCREATOR</code> block and tell me: the "
    "<code>status</code>, the <b>full <code>flw_path</code></b> (so I can open the file), the "
    "<code>agent_count</code> and <code>connection_count</code>, and then list the agents it "
    "chose in execution order with one line each explaining why that agent is there. If "
    "<code>status</code> is <code>error</code>, say so plainly and quote the message - do NOT "
    "claim a flow was created. End with END-RESPONSE."
)


def add_rows(apps, schema_editor):
    Tool = apps.get_model('agent', 'Tool')
    Prompt = apps.get_model('agent', 'Prompt')

    if not Tool.objects.filter(toolDescription=TOOL_DESCRIPTION).exists():
        next_id = (Tool.objects.order_by('-idTool').values_list('idTool', flat=True).first() or 0) + 1
        Tool.objects.create(
            idTool=next_id,
            toolName=f'tool-{next_id}',
            toolDescription=TOOL_DESCRIPTION,
            toolContent='true',
        )

    if not Prompt.objects.filter(promptContent=DEMO_PROMPT).exists():
        next_pid = (Prompt.objects.order_by('-idPrompt').values_list('idPrompt', flat=True).first() or 0) + 1
        Prompt.objects.update_or_create(
            idPrompt=next_pid,
            defaults={
                'promptName': f'prompt-{next_pid}',
                'promptContent': DEMO_PROMPT,
                'category': 'agents_flows',
                'hidden': False,
                # 33 (ALARM FLOW FORGE) sits at rank 80; this is its natural sibling.
                'sort_rank': 85,
            },
        )


def remove_rows(apps, schema_editor):
    apps.get_model('agent', 'Tool').objects.filter(toolDescription=TOOL_DESCRIPTION).delete()
    apps.get_model('agent', 'Prompt').objects.filter(promptContent=DEMO_PROMPT).delete()


class Migration(migrations.Migration):

    dependencies = [('agent', '0185_standardize_prompt_params_batch3')]

    operations = [migrations.RunPython(add_rows, remove_rows)]
