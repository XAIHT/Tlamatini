# Tlamatini Author Banner — Angela López Mendoza · @angelahack1
"""One module tool and a guided-editor catalog example; no Agent row."""
from django.db import migrations


PROMPT_NAME = "INTERACTOR — Build a Dockerfile together"
PROMPT = (
    "Tlamatini, help me create a Dockerfile for a Java application with a servlet and a landing page, "
    "using your text editor. Use the Interactor module and Multi-Turn. No path is provided: create "
    "Dockerfile in Tlamatini Temp. Read the current canvas first and preserve any unsaved work. "
    "Type only the first small known segment, then stop at the first field I must choose. Explain "
    "the choice in chat, with recommendations and optional local completions for that field. "
    "Let me type my answer and click Continue in chat. Read my fresh unsaved text before each "
    "next step. Do not finish the file or run Docker for me. End each teaching turn with END-RESPONSE."
)


def seed(apps, schema_editor):
    Tool = apps.get_model("agent", "Tool")
    if not Tool.objects.filter(toolDescription="Interactor").exists():
        last = Tool.objects.order_by("-idTool").first()
        number = last.idTool + 1 if last else 1
        Tool.objects.create(idTool=number, toolName=f"tool-{number}", toolDescription="Interactor", toolContent="true")
    Prompt = apps.get_model("agent", "Prompt")
    if not Prompt.objects.filter(promptName=PROMPT_NAME).exists():
        last = Prompt.objects.order_by("-idPrompt").first()
        Prompt.objects.create(idPrompt=last.idPrompt + 1 if last else 1, promptName=PROMPT_NAME,
                              promptContent=PROMPT, category="code_gen", sort_rank=95)


def reverse(apps, schema_editor):
    apps.get_model("agent", "Tool").objects.filter(toolDescription="Interactor").delete()
    apps.get_model("agent", "Prompt").objects.filter(promptName=PROMPT_NAME).delete()


class Migration(migrations.Migration):
    dependencies = [("agent", "0217_add_terminater_demo_prompts")]
    operations = [migrations.RunPython(seed, reverse)]
