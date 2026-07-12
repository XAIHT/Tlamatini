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
            "textEditorCode",
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

    def test_acp_status_poller_handle_is_mutable(self):
        text = self._read("static", "agent", "js", "acp-undo-manager.js")
        mutable_names = ["agentStatusPollerInterval"]
        for name in mutable_names:
            self.assert_declared_with_let(text, name)
        self.assert_collected_static_is_not_poisoned("agent/js/acp-undo-manager.js", mutable_names)

    # Matches a top-level `const NAME =` (column 0 only — module-level, not a local).
    _TOP_LEVEL_CONST_RE = re.compile(r"^const\s+([A-Za-z_$][\w$]*)\s*=", re.MULTILINE)

    # Matches an assignment TO a bare identifier: `NAME =`, `NAME +=`, `NAME ??=` ...
    # Excludes `NAME ==`/`===` (comparison), `NAME =>` (arrow param) and `x.NAME =`
    # (property write, which is legal on a const).
    @staticmethod
    def _assignment_re(name: str) -> re.Pattern:
        return re.compile(
            rf"(?<![.\w$]){re.escape(name)}\s*(?:=(?![=>])|\+=|-=|\*=|/=|\|\|=|&&=|\?\?=)"
        )

    @staticmethod
    def _redeclaration_re(name: str) -> re.Pattern:
        return re.compile(rf"\b(?:let|var|const|function)\s+{re.escape(name)}\b")

    def test_no_top_level_const_is_reassigned_by_a_sibling_script(self):
        """Name-agnostic const-poison sweep across every browser script.

        The scripts are plain <script> tags sharing ONE global scope, so a top-level
        `const` in one file that a SIBLING file assigns to throws
        "TypeError: Assignment to constant variable" the moment that code path runs.
        Per-file ESLint structurally cannot see the cross-file write, so the mistake
        lints green — it has now shipped twice (the 2026-07-08 const-poison incident,
        and `agentStatusPollerInterval` on 2026-07-11, which trapped the ACP Start
        dialog behind a modal with no closable button).

        The hand-listed tests above only guard names somebody remembered to list.
        This one guards every name, so it catches the NEXT one for free.
        """
        js_dir = ROOT / Path("static", "agent", "js")
        sources = {p.name: p.read_text(encoding="utf-8") for p in sorted(js_dir.glob("*.js"))}

        offenders = []
        for decl_file, decl_text in sources.items():
            for name in self._TOP_LEVEL_CONST_RE.findall(decl_text):
                assignment_re = self._assignment_re(name)
                redeclaration_re = self._redeclaration_re(name)
                for other_file, other_text in sources.items():
                    if other_file == decl_file:
                        continue
                    # A sibling with its own binding of the name shadows the global.
                    if redeclaration_re.search(other_text):
                        continue
                    if assignment_re.search(other_text):
                        offenders.append(
                            f"{name}: declared `const` in {decl_file}, but assigned in {other_file}"
                        )

        self.assertEqual(
            [],
            sorted(offenders),
            msg=(
                "Cross-file const-poison detected. These MUST be declared `let` — a "
                "sibling script reassigns them at runtime:\n  " + "\n  ".join(sorted(offenders))
            ),
        )

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
