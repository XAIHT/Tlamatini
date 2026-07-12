# ═══════════════════════════════════════════════════════════════════
#   ✦  T L A M A T I N I  ✦   —   "one who knows"
#
#   Created by  Angela López Mendoza   ·   @angelahack1
#   Developer · Architect · Creator of Tlamatini
#
#   Every line of this file was written by Angela López Mendoza.
# ═══════════════════════════════════════════════════════════════════
#   Tlamatini Author Banner — do not remove (releases scrub the name automatically)
from django.db import migrations


# Catalog-of-prompts SCAFFOLD: lets a user create a BRAND-NEW Unreal Engine 5.8
# C++ project — fully wired with the UnrealMCP editor plugin and ready to open in
# Visual Studio 2026 — by filling ONLY two [[ ... ]] markers: the project NAME and
# the DIRECTORY it goes in. Tlamatini (Multi-Turn) runs the deterministic scaffolder
# scaffold_unreal_project.py (in the XaihtUnrealEngineMCP repo), which copies +
# renames the MCPGameProject template, sets EngineAssociation 5.8, auto-discovers
# the UE 5.8 engine, and generates the Visual Studio solution. SAFE for the daily
# chat test: if a marker is unfilled (or the name is not a valid C++ module id) it
# creates NOTHING and just asks the user to fix it. Markers use [[ ]] (no angle
# brackets) so an HTML card preview can't eat them.
#
# Preconditions (documented in the prompt body): the user has Unreal Engine 5.8 and
# Visual Studio 2026 (with the C++ / Game-dev workload) installed. The scaffolder is
# registry-independent (it finds UE 5.8 on disk), so it works even when 5.8 is not
# registered as an engine association.
DEMO = (
    "Tlamatini, SCAFFOLD A NEW UNREAL ENGINE 5.8 C++ PROJECT for me, ready to open in "
    "Visual Studio 2026 with the UnrealMCP plugin already wired in. I filled in the two "
    "fields below — the ONLY two things you need from me: the project's NAME and the "
    "DIRECTORY it should be created in.\n"
    "\n"
    "NEW UNREAL PROJECT\n"
    "- project name:        [[ TYPE THE PROJECT NAME HERE, e.g. MyAwesomeGame — letters, digits and underscores ONLY, no spaces or dashes, must not start with a digit ]]\n"
    "- directory location:  [[ THE PARENT FOLDER TO CREATE IT IN, e.g. C:\\Users\\angel\\Documents\\UnrealProjects ]]\n"
    "\n"
    "FIRST, a safety check — do this before touching anything: if EITHER line above still "
    "shows a [[ ... ]] marker (so I have not filled it in), do NOT create anything and run "
    "nothing — just tell me which field to fill and stop. Also, if the project name has a "
    "space or a dash, or starts with a digit, do NOT proceed — explain that it must be a "
    "valid Unreal C++ module name (letters / digits / underscore, no leading digit) and ask "
    "me to rename it. Only continue when BOTH fields are filled AND the name is valid.\n"
    "\n"
    "THEN, in Multi-Turn, using ONLY your own tools (Executer / Gitter / File-Interpreter), "
    "do exactly this, in order:\n"
    "\n"
    "1) LOCATE THE SCAFFOLDER. The deterministic scaffolder lives at "
    "C:\\Development\\XaihtUnrealEngineMCP\\scaffold_unreal_project.py (its repo also holds "
    "the MCPGameProject template and the UnrealMCP editor plugin). Use Executer to check "
    "whether that file exists (e.g. `if exist \"C:\\Development\\XaihtUnrealEngineMCP\\scaffold_unreal_project.py\" (echo FOUND) else (echo MISSING)`). "
    "If it is MISSING, clone the repo first with Gitter (command='custom', custom_command="
    "'clone https://github.com/XAIHT/XaihtUnrealEngineMCP.git C:\\Development\\XaihtUnrealEngineMCP') "
    "— create C:\\Development first if needed. Do NOT continue until the scaffolder file exists.\n"
    "\n"
    "2) RUN THE SCAFFOLDER (one command does everything). Use Executer to run EXACTLY this, "
    "substituting my two values and KEEPING the quotes around the directory (it may contain "
    "spaces):\n"
    "   python \"C:\\Development\\XaihtUnrealEngineMCP\\scaffold_unreal_project.py\" --name <PROJECT NAME> --dest \"<DIRECTORY LOCATION>\"\n"
    "That single command copies the template, renames every module file and token to my "
    "project name, bundles the UnrealMCP plugin, sets EngineAssociation to 5.8, auto-finds "
    "my installed UE 5.8 engine, and GENERATES the Visual Studio solution (.sln). Its final "
    "stdout line starts with `SCAFFOLD_RESULT:` followed by JSON — READ that JSON. If its "
    "\"ok\" is false, show me the \"error\" verbatim and stop. If \"ok\" is true, capture "
    "\"project_dir\", \"uproject\" and \"solution\" for the report.\n"
    "\n"
    "3) OPEN IT IN VISUAL STUDIO. If \"solution\" is a real .sln path, use Executer to open "
    "it on my desktop:\n"
    "   start \"\" \"<solution>\"\n"
    "(that launches Visual Studio 2026 on the .sln). If \"solution\" is empty, do NOT invent "
    "one — show me the note the script printed under \"notes\" and point me at the .uproject "
    "so I can right-click it and choose 'Generate Visual Studio project files' myself.\n"
    "\n"
    "4) CONFIRM + INSTRUCT. Emit a short, tidy HTML summary showing: the project FOLDER, the "
    ".uproject path, the .sln path, and the engine root that was used. Then give me these "
    "exact next steps for Visual Studio 2026: (a) set the configuration to 'Development "
    "Editor' and the platform to 'Win64'; (b) Build the solution — the FIRST build compiles "
    "the UnrealMCP plugin and takes several minutes; (c) press F5 (or Ctrl+F5) to launch the "
    "Unreal Editor with my project. Add this note verbatim: once the editor is running, the "
    "bundled UnrealMCP plugin AUTOMATICALLY starts its TCP listener on 127.0.0.1:55557 (it is "
    "a UEditorSubsystem whose Initialize() starts the server), so you — Tlamatini — can "
    "immediately drive the live editor with the chat_agent_unrealer tool; there is no extra "
    "'start server' step.\n"
    "\n"
    "Do NOT attempt to compile or launch the engine yourself from chat (a full editor build "
    "is long and belongs in Visual Studio). Your job in this prompt is to PRODUCE the "
    "ready-to-open, ready-to-compile project and hand it to me in Visual Studio 2026.\n"
    "\n"
    "Tick ONLY the Multi-Turn checkbox. End with END-RESPONSE."
)


def add_demo_prompt(apps, schema_editor):
    Prompt = apps.get_model('agent', 'Prompt')
    if Prompt.objects.filter(promptContent=DEMO).exists():
        return
    next_id = (Prompt.objects.order_by('-idPrompt').values_list('idPrompt', flat=True).first() or 0) + 1
    Prompt.objects.update_or_create(
        idPrompt=next_id,
        defaults={'promptName': f'prompt-{next_id}', 'promptContent': DEMO},
    )


def remove_demo_prompt(apps, schema_editor):
    Prompt = apps.get_model('agent', 'Prompt')
    Prompt.objects.filter(promptContent=DEMO).delete()


class Migration(migrations.Migration):
    dependencies = [('agent', '0172_add_nmapper_demo_prompts')]
    operations = [migrations.RunPython(add_demo_prompt, remove_demo_prompt)]
