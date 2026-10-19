# Tlamatini Author Banner — Angela López Mendoza
"""Remove obsolete catalog entries without renumbering surviving rows.

Earlier migrations remain unchanged so existing databases can upgrade through
the same dependency graph and prompt IDs keep their historical meaning.
"""
from django.db import migrations
from django.db.models import Q


AGENT_NAMES = (
    "Gatewayer", "Gateway Relayer", "Gateway-Relayer", "GatewayRelayer",
    "Node Manager", "Node-Manager", "NodeManager", "Zavuerer",
)
PROMPT_MARKERS = (
    "run the **ZAVUERER** demo",
    "please set up **Zavuerer** with me ONE step at a time",
    "use chat_agent_zavuerer to send a quick **SMS**",
    "reach me the smart way with **Zavuerer**",
    "hold my hand and set up **Zavuerer** with me from zero",
)


def prune_catalog(apps, schema_editor):
    alias = schema_editor.connection.alias
    Agent = apps.get_model("agent", "Agent")
    Tool = apps.get_model("agent", "Tool")
    Prompt = apps.get_model("agent", "Prompt")
    Agent.objects.using(alias).filter(agentDescription__in=AGENT_NAMES).delete()
    Tool.objects.using(alias).filter(toolDescription="Chat-Agent-Zavuerer").delete()
    obsolete_prompts = Q()
    for marker in PROMPT_MARKERS:
        obsolete_prompts |= Q(promptContent__icontains=marker)
    Prompt.objects.using(alias).filter(obsolete_prompts).delete()


class Migration(migrations.Migration):
    dependencies = [("agent", "0213_usage_ledger")]
    operations = [migrations.RunPython(prune_catalog, migrations.RunPython.noop)]
