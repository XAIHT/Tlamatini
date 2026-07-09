# ═══════════════════════════════════════════════════════════════════
#   ✦  T L A M A T I N I  ✦   —   "one who knows"
#
#   Created by  Angela López Mendoza   ·   @angelahack1
#   Developer · Architect · Creator of Tlamatini
#
#   Every line of this file was written by Angela López Mendoza.
# ═══════════════════════════════════════════════════════════════════
#   Tlamatini Author Banner — do not remove (releases scrub the name automatically)
from pathlib import Path
import re
import unittest

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from .models import Prompt


ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = ROOT.parent


class FrontendMutableStateTests(unittest.TestCase):
    """Guards split-script globals that are reassigned by later browser files."""

    def _read(self, *parts: str) -> str:
        return (ROOT / Path(*parts)).read_text(encoding="utf-8")

    def assert_declared_with_let(self, text: str, name: str) -> None:
        self.assertRegex(
            text,
            rf"\blet\s+{re.escape(name)}\s*=",
            msg=f"{name} must stay mutable; browser runtime reassigns it.",
        )
        self.assertNotRegex(
            text,
            rf"\bconst\s+{re.escape(name)}\s*=",
            msg=f"{name} cannot be const because later split JS files assign it.",
        )

    def assert_collected_static_is_not_poisoned(self, relative_path: str, names: list[str]) -> None:
        collected = PROJECT_ROOT / "staticfiles" / relative_path
        if not collected.exists():
            self.skipTest(f"{collected} does not exist; run collectstatic to validate collected assets.")

        text = collected.read_text(encoding="utf-8")
        for name in names:
            self.assertNotRegex(
                text,
                rf"\bconst\s+{re.escape(name)}\s*=",
                msg=f"Collected static asset {relative_path} still has poisoned const for {name}.",
            )

    def _read_collected_static(self, relative_path: str) -> str:
        collected = PROJECT_ROOT / "staticfiles" / relative_path
        if not collected.exists():
            self.skipTest(f"{collected} does not exist; run collectstatic to validate collected assets.")
        return collected.read_text(encoding="utf-8")

    def test_agent_page_runtime_state_is_mutable(self):
        text = self._read("static", "agent", "js", "agent_page_state.js")
        mutable_names = [
            "contextButtonClicked",
            "canvasSettedAsContext",
            "confirmationByUser",
            "canvasLoaded",
            "openEnabled",
            "reConnectEnabled",
            "contextEnabled",
            "cleanCanvasEnabled",
            "actualContextDir",
            "clearContextEnabled",
            "cleanHistoryEnabled",
            "fileTypeOmissions",
            "chatHistory",
            "historyIndex",
            "tempInput",
            "buildingInitial",
            "titleBusyPrefix",
            "mcp1_enabled",
            "mcp2_enabled",
            "tools",
            "agents",
            "skills",
            "installedApps",
        ]
        for name in mutable_names:
            self.assert_declared_with_let(text, name)
        self.assert_collected_static_is_not_poisoned("agent/js/agent_page_state.js", mutable_names)

    def test_acp_runtime_state_is_mutable(self):
        text = self._read("static", "agent", "js", "acp-globals.js")
        mutable_names = [
            "globalRunningState",
            "flowValidationStatus",
            "titleBusyPrefix",
            "isFlowCreatorWaiting",
            "isBusyProcessing",
            "hasUnsavedChanges",
        ]
        for name in mutable_names:
            self.assert_declared_with_let(text, name)
        self.assert_collected_static_is_not_poisoned("agent/js/acp-globals.js", mutable_names)

    def test_changed_state_scripts_force_fresh_browser_cache(self):
        agent_page = self._read("templates", "agent", "agent_page.html")
        acp_page = self._read("templates", "agent", "agentic_control_panel.html")
        self.assertIn("agent_page_state.js' %}?v={{ STATIC_VERSION }}_statefix", agent_page)
        self.assertIn("agent_page_dialogs.js' %}?v={{ STATIC_VERSION }}_dialogfix", agent_page)
        self.assertIn("tools_dialog.js' %}?v={{ STATIC_VERSION }}_promptfix", agent_page)
        self.assertIn("acp-globals.js' %}?v={{ STATIC_VERSION }}_statefix", acp_page)

    def test_prompt_catalog_uses_list_endpoint_without_expected_404_console_noise(self):
        text = self._read("static", "agent", "js", "tools_dialog.js")
        collected = self._read_collected_static("agent/js/tools_dialog.js")
        for asset_text in [text, collected]:
            self.assertIn("/agent/list_prompts/", asset_text)
            self.assertNotIn("404 Error: Prompt not found", asset_text)
            self.assertNotIn("Prompt not found in database:", asset_text)


class PromptCatalogEndpointTests(TestCase):
    def test_list_prompts_returns_ordered_catalog_without_404_probe(self):
        user = get_user_model().objects.create_user(username="catalog-test", password="pw")
        Prompt.objects.all().delete()
        Prompt.objects.create(idPrompt=2, promptName="prompt-2", promptContent="second")
        Prompt.objects.create(idPrompt=1, promptName="prompt-1", promptContent="first")

        self.client.force_login(user)
        response = self.client.get(reverse("list_prompts"))

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(
            payload["prompts"],
            [
                {"index": 1, "name": "prompt-1", "content": "first"},
                {"index": 2, "name": "prompt-2", "content": "second"},
            ],
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
