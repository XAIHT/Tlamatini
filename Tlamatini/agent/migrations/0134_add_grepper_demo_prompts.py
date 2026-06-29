# ═══════════════════════════════════════════════════════════════════
#   ✦  T L A M A T I N I  ✦   —   "one who knows"
#
#   Created by  Angela López Mendoza   ·   @angelahack1
#   Developer · Architect · Creator of Tlamatini
#
#   Every line of this file was written by Angela López Mendoza.
# ═══════════════════════════════════════════════════════════════════
#   Tlamatini Author Banner — do not remove (releases scrub the name automatically)
"""
Seed a Catalog-of-Prompts demo for **Grepper** - Tlamatini's read-only regex
content searcher - run through the wrapped **chat_agent_grepper** Multi-Turn tool.
Mandatory catalog prompt (CLAUDE.md / create_new_agent.md Step 7.8 /
tlamatini-agent-creation Phase 19).

    77  CONTENT HUNT   basic   File-Creator seeds 2 throwaway files under the app
                               Temp dir -> chat_agent_grepper finds a regex across
                               them -> report matches/files_searched.

SAFE to run repeatedly: it only writes two throwaway files under the app Temp
directory and searches THAT directory (read-only). Slots 1-76 are occupied (0131
appended the Editor demo at 76); this APPENDS at 77 with no renumber. Reverse
deletes 77. (MAX_PROMPTS=100.)
"""
from django.db import migrations


# Grepper banner palette - mirrors the ``.canvas-item.grepper-agent`` indigo gradient.
_BANNER_OPEN = (
    "<div style='padding:18px;border-radius:14px;background:linear-gradient(135deg,"
    "#0b1d3a 0%,#1e3a8a 33%,#3b82f6 66%,#93c5fd 100%);color:#fff;font-family:Inter,"
    "Segoe UI,sans-serif;text-align:center;text-shadow:0 1px 3px rgba(0,0,0,.5);'>"
)


CONTENT_HUNT_DEMO = (
    "Tlamatini, run the **CONTENT HUNT** demo, please &mdash; a basic showcase of your own "
    "regex content searcher, driven from chat through the wrapped **chat_agent_grepper** tool "
    "(the grep / find-in-files equivalent that returns matching lines as file:line:match). "
    "Tick ONLY the **Multi-Turn** checkbox before sending. Use ONLY chat_agent_file_creator "
    "(to seed the scratch files) and chat_agent_grepper (to search them). "
    "\\n\\n"
    "Step 0: open with one HTML banner &mdash; " + _BANNER_OPEN +
    "<h2 style='margin:0;letter-spacing:2px;'>&#128269; CONTENT HUNT</h2>"
    "<div style='opacity:.92;margin-top:4px;'>Tlamatini Grepper &mdash; regex in, file:line:match out</div></div>. "
    "\\n\\n"
    "Step 1 (seed A): call **chat_agent_file_creator** with request \\\"Run File Creator with "
    "file_path='<TEMP>/grepper_demo/a.txt' and content='alpha TODO_MARK one'\\\", where <TEMP> is "
    "your app Temp directory (the absolute path the system prompt gives you). "
    "\\n\\n"
    "Step 2 (seed B): call **chat_agent_file_creator** with request \\\"Run File Creator with "
    "file_path='<TEMP>/grepper_demo/b.txt' and content='beta TODO_MARK two'\\\". "
    "\\n\\n"
    "Step 3 (search): call **chat_agent_grepper** with request \\\"Run Grepper with "
    "pattern='TODO_MARK', path='<TEMP>/grepper_demo', glob='*.txt', output_mode='content'\\\". From "
    "the INI_SECTION_GREPPER block in the run's log_excerpt capture status (matches | no_matches | "
    "not_found | error), matches, and files_searched, plus the file:line:match body lines. "
    "\\n\\n"
    "Step 4: render an HTML table with class='exec-report-table' titled "
    "'<strong>Content Hunt &mdash; Matches</strong>' and columns <em>file</em>, <em>line</em>, "
    "<em>text</em> &mdash; one row per file:line:match line in the INI_SECTION_GREPPER body (do NOT "
    "re-classify). Light body cells (background:#ffffff;color:#0f172a). "
    "\\n\\n"
    "Step 5: close with one HTML banner reusing the Step 0 style printing, in big letters, "
    "'&#9989; FOUND <matches>' (status matches) or '&#128269; NO MATCHES' (status no_matches), and "
    "underneath a one-line metric 'pattern: TODO_MARK &middot; files searched: <files_searched>'. "
    "End with END-RESPONSE."
)


_NEW_PROMPTS = (
    (77, CONTENT_HUNT_DEMO),
)


def add_grepper_demo_prompt(apps, schema_editor):
    Prompt = apps.get_model('agent', 'Prompt')
    for prompt_id, content in _NEW_PROMPTS:
        Prompt.objects.update_or_create(
            idPrompt=prompt_id,
            defaults={'promptName': f'prompt-{prompt_id}', 'promptContent': content},
        )


def remove_grepper_demo_prompt(apps, schema_editor):
    Prompt = apps.get_model('agent', 'Prompt')
    Prompt.objects.filter(idPrompt__in=[pid for pid, _ in _NEW_PROMPTS]).delete()


class Migration(migrations.Migration):
    dependencies = [
        ('agent', '0133_add_chat_agent_grepper_tool'),
    ]

    operations = [
        migrations.RunPython(add_grepper_demo_prompt, remove_grepper_demo_prompt),
    ]
