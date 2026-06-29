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
Seed a Catalog-of-Prompts demo for **Editor** - Tlamatini's surgical in-place
file editor - run through the wrapped **chat_agent_editor** Multi-Turn tool.
Mandatory catalog prompt every Multi-Turn-capable agent must ship (CLAUDE.md
directive / create_new_agent.md Step 7.8 / tlamatini-agent-creation Phase 19).

    76  SURGICAL EDIT   basic   File-Creator seeds a throwaway file under the app
                                Temp dir -> chat_agent_editor replaces one exact
                                line -> a second edit proves the 'noop' path ->
                                report status/replacements.

SAFE to run repeatedly (the daily chat test may execute it): it only writes a
throwaway file under the app Temp directory and edits THAT file - no existing
project file is ever touched.

Placement (append, no renumber)
-------------------------------
The catalog dropdown (static/agent/js/tools_dialog.js) enumerates promptName
'prompt-1','prompt-2',... and BREAKS at the first missing slot, so the catalog
must stay a contiguous, gap-free 'prompt-1..N'. Slots 1-75 are occupied (0128
appended the Blenderer demo at 75); this APPENDS at 76 with no shift of any
existing prompt. Reverse deletes 76. (MAX_PROMPTS=100.)
"""
from django.db import migrations


# Editor banner palette - mirrors the ``.canvas-item.editor-agent`` emerald gradient.
_BANNER_OPEN = (
    "<div style='padding:18px;border-radius:14px;background:linear-gradient(135deg,"
    "#022c22 0%,#064e3b 33%,#10b981 66%,#6ee7b7 100%);color:#fff;font-family:Inter,"
    "Segoe UI,sans-serif;text-align:center;text-shadow:0 1px 3px rgba(0,0,0,.5);'>"
)


SURGICAL_EDIT_DEMO = (
    "Tlamatini, run the **SURGICAL EDIT** demo, please &mdash; a basic showcase of your own "
    "surgical file editor, driven from chat through the wrapped **chat_agent_editor** tool: the "
    "find-and-replace operator that changes a file by swapping an EXACT string WITHOUT rewriting "
    "the whole file. Tick ONLY the **Multi-Turn** checkbox before sending. Use ONLY "
    "chat_agent_file_creator (to seed the scratch file) and chat_agent_editor (to edit it). "
    "\\n\\n"
    "Step 0: open with one HTML banner &mdash; " + _BANNER_OPEN +
    "<h2 style='margin:0;letter-spacing:2px;'>&#9999;&#65039; SURGICAL EDIT</h2>"
    "<div style='opacity:.92;margin-top:4px;'>Tlamatini Editor &mdash; find, replace, byte-exact</div></div>. "
    "\\n\\n"
    "Step 1 (seed): call **chat_agent_file_creator** with request \\\"Run File Creator with "
    "file_path='<TEMP>/editor_demo.txt' and content='editor demo file -- status: draft'\\\", where "
    "<TEMP> is your app Temp directory (the absolute path the system prompt gives you). "
    "\\n\\n"
    "Step 2 (edit): call **chat_agent_editor** with request \\\"Run Editor with "
    "file_path='<TEMP>/editor_demo.txt', old_string='status: draft', new_string='status: final', "
    "replace_all=false\\\". From the INI_SECTION_EDITOR block in the run's log_excerpt capture the "
    "status (edited | not_found | not_unique | noop | error) and the replacements count. "
    "\\n\\n"
    "Step 3 (prove no-op): call **chat_agent_editor** AGAIN with request \\\"Run Editor with "
    "file_path='<TEMP>/editor_demo.txt', old_string='status: draft', new_string='status: final', "
    "replace_all=false\\\" and confirm it now reports status 'not_found' (the draft line is gone &mdash; "
    "proof the first edit really applied). "
    "\\n\\n"
    "Step 4: render an HTML table with class='exec-report-table' titled "
    "'<strong>Surgical Edit &mdash; Report</strong>' and columns <em>step</em>, <em>old_string</em>, "
    "<em>new_string</em>, <em>status</em>, <em>replacements</em> &mdash; one row per chat_agent_editor "
    "call you made, every value verbatim from its INI_SECTION_EDITOR block (do NOT re-classify). Light "
    "body cells (background:#ffffff;color:#0f172a), green tint for status edited, grey for not_found. "
    "\\n\\n"
    "Step 5: close with one HTML banner reusing the Step 0 style printing, in big letters, "
    "'&#9989; EDITED' (Step 2 returned status edited) or '&#10060; EDIT FAILED' (quote the status and "
    "message), and underneath a one-line metric 'file: <TEMP>/editor_demo.txt &middot; replacements: <n>'. "
    "End with END-RESPONSE."
)


_NEW_PROMPTS = (
    (76, SURGICAL_EDIT_DEMO),
)


def add_editor_demo_prompt(apps, schema_editor):
    Prompt = apps.get_model('agent', 'Prompt')
    for prompt_id, content in _NEW_PROMPTS:
        Prompt.objects.update_or_create(
            idPrompt=prompt_id,
            defaults={'promptName': f'prompt-{prompt_id}', 'promptContent': content},
        )


def remove_editor_demo_prompt(apps, schema_editor):
    Prompt = apps.get_model('agent', 'Prompt')
    Prompt.objects.filter(idPrompt__in=[pid for pid, _ in _NEW_PROMPTS]).delete()


class Migration(migrations.Migration):
    dependencies = [
        ('agent', '0130_add_chat_agent_editor_tool'),
    ]

    operations = [
        migrations.RunPython(add_editor_demo_prompt, remove_editor_demo_prompt),
    ]
