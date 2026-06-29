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
Seed a Catalog-of-Prompts demo for **Globber** - Tlamatini's read-only filename
pattern searcher - run through the wrapped **chat_agent_globber** Multi-Turn tool.
Mandatory catalog prompt (CLAUDE.md / create_new_agent.md Step 7.8 /
tlamatini-agent-creation Phase 19).

    78  FILE FINDER   basic   File-Creator seeds 2 throwaway files in a Temp subdir
                              -> chat_agent_globber lists them by glob (newest-first)
                              -> report matches.

SAFE to run repeatedly: it only writes two throwaway files under the app Temp
directory and globs THAT directory (read-only). Slots 1-77 are occupied (0134
appended the Grepper demo at 77); this APPENDS at 78. Reverse deletes 78.
(MAX_PROMPTS=100.)
"""
from django.db import migrations


# Globber banner palette - mirrors the ``.canvas-item.globber-agent`` violet gradient.
_BANNER_OPEN = (
    "<div style='padding:18px;border-radius:14px;background:linear-gradient(135deg,"
    "#1e0a3c 0%,#4c1d95 33%,#8b5cf6 66%,#c4b5fd 100%);color:#fff;font-family:Inter,"
    "Segoe UI,sans-serif;text-align:center;text-shadow:0 1px 3px rgba(0,0,0,.5);'>"
)


FILE_FINDER_DEMO = (
    "Tlamatini, run the **FILE FINDER** demo, please &mdash; a basic showcase of your own "
    "filename pattern searcher, driven from chat through the wrapped **chat_agent_globber** tool "
    "(the glob / find-files equivalent that lists matching file paths, newest-first). Tick ONLY "
    "the **Multi-Turn** checkbox before sending. Use ONLY chat_agent_file_creator (to seed the "
    "scratch files) and chat_agent_globber (to list them). "
    "\\n\\n"
    "Step 0: open with one HTML banner &mdash; " + _BANNER_OPEN +
    "<h2 style='margin:0;letter-spacing:2px;'>&#128193; FILE FINDER</h2>"
    "<div style='opacity:.92;margin-top:4px;'>Tlamatini Globber &mdash; glob in, file paths out</div></div>. "
    "\\n\\n"
    "Step 1 (seed A): call **chat_agent_file_creator** with request \\\"Run File Creator with "
    "file_path='<TEMP>/globber_demo/one.txt' and content='first file'\\\", where <TEMP> is your app "
    "Temp directory (the absolute path the system prompt gives you). "
    "\\n\\n"
    "Step 2 (seed B): call **chat_agent_file_creator** with request \\\"Run File Creator with "
    "file_path='<TEMP>/globber_demo/sub/two.txt' and content='second file'\\\". "
    "\\n\\n"
    "Step 3 (find): call **chat_agent_globber** with request \\\"Run Globber with "
    "pattern='**/*.txt', path='<TEMP>/globber_demo', sort_by='mtime'\\\". From the "
    "INI_SECTION_GLOBBER block in the run's log_excerpt capture status (matches | no_matches | "
    "not_found | error) and matches, plus the file paths in the body (newest first). "
    "\\n\\n"
    "Step 4: render an HTML table with class='exec-report-table' titled "
    "'<strong>File Finder &mdash; Matches</strong>' and columns <em>#</em>, <em>path</em> &mdash; "
    "one row per file path in the INI_SECTION_GLOBBER body, in the order returned. Light body cells "
    "(background:#ffffff;color:#0f172a). "
    "\\n\\n"
    "Step 5: close with one HTML banner reusing the Step 0 style printing, in big letters, "
    "'&#9989; FOUND <matches>' (status matches) or '&#128193; NONE' (status no_matches), and "
    "underneath a one-line metric 'pattern: **/*.txt &middot; matches: <matches>'. "
    "End with END-RESPONSE."
)


_NEW_PROMPTS = (
    (78, FILE_FINDER_DEMO),
)


def add_globber_demo_prompt(apps, schema_editor):
    Prompt = apps.get_model('agent', 'Prompt')
    for prompt_id, content in _NEW_PROMPTS:
        Prompt.objects.update_or_create(
            idPrompt=prompt_id,
            defaults={'promptName': f'prompt-{prompt_id}', 'promptContent': content},
        )


def remove_globber_demo_prompt(apps, schema_editor):
    Prompt = apps.get_model('agent', 'Prompt')
    Prompt.objects.filter(idPrompt__in=[pid for pid, _ in _NEW_PROMPTS]).delete()


class Migration(migrations.Migration):
    dependencies = [
        ('agent', '0136_add_chat_agent_globber_tool'),
    ]

    operations = [
        migrations.RunPython(add_globber_demo_prompt, remove_globber_demo_prompt),
    ]
