# Tlamatini Author Banner — Angela López Mendoza
"""Catalog retirement must work on both new databases and existing installs."""
from importlib import import_module
from types import SimpleNamespace

from django.apps import apps
from django.db import connection
from django.test import TestCase

from .models import Agent, Prompt, Tool
from .services.agent_contracts import get_agent_contracts


cleanup = import_module("agent.migrations.0214_prune_agent_catalog")
REMOVED = {"gatewayer", "gateway_relayer", "node_manager", "zavuerer"}


class CatalogPruningTests(TestCase):
    def test_fresh_database_and_live_registry_exclude_obsolete_entries(self):
        self.assertFalse(Agent.objects.filter(agentDescription__in=cleanup.AGENT_NAMES).exists())
        self.assertFalse(Tool.objects.filter(toolDescription="Chat-Agent-Zavuerer").exists())
        self.assertFalse(Prompt.objects.filter(promptContent__icontains="zavuerer").exists())
        self.assertTrue(REMOVED.isdisjoint(get_agent_contracts()))
        self.assertTrue(Prompt.objects.filter(idPrompt__gt=94).exists())

    def test_upgrade_is_idempotent_and_preserves_other_prompts_and_choices(self):
        for offset, name in enumerate(cleanup.AGENT_NAMES):
            Agent.objects.create(idAgent=9000 + offset, agentName=f"agent-{9000 + offset}",
                                 agentDescription=name, agentContent="false")
        Tool.objects.create(idTool=9000, toolName="tool-9000",
                            toolDescription="Chat-Agent-Zavuerer", toolContent="false")
        for offset, marker in enumerate(cleanup.PROMPT_MARKERS):
            Prompt.objects.create(idPrompt=9000 + offset, promptName=f"prompt-{9000 + offset}",
                                  promptContent=marker)
        survivor = Prompt.objects.create(idPrompt=9010, promptName="prompt-9010",
                                         promptContent="My custom messaging notes", sort_rank=123)
        before_agents = list(Agent.objects.exclude(agentDescription__in=cleanup.AGENT_NAMES)
                             .order_by("idAgent").values())
        before_tools = list(Tool.objects.exclude(toolDescription="Chat-Agent-Zavuerer")
                            .order_by("idTool").values())
        editor = SimpleNamespace(connection=connection)
        cleanup.prune_catalog(apps, editor)
        cleanup.prune_catalog(apps, editor)
        self.test_fresh_database_and_live_registry_exclude_obsolete_entries()
        self.assertEqual(before_agents, list(Agent.objects.order_by("idAgent").values()))
        self.assertEqual(before_tools, list(Tool.objects.order_by("idTool").values()))
        survivor.refresh_from_db()
        self.assertEqual((survivor.idPrompt, survivor.promptName, survivor.sort_rank),
                         (9010, "prompt-9010", 123))
