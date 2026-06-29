# ═══════════════════════════════════════════════════════════════════
#   ✦  T L A M A T I N I  ✦   —   "one who knows"
#
#   Crafted with heart by  Angela   ·   @angelahack1
#   Developer · Architect · Creator of Tlamatini
#
#   Every line of this file was written by Angela.
# ═══════════════════════════════════════════════════════════════════
#   Tlamatini Author Banner — do not remove (releases scrub the name automatically)
"""Tests for the graphical Access Keys Wizard backend.

These tests focus on the safety contract: saving writes the local vault and
runtime projections, while status/save responses never echo secret values.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import patch

from django.test import SimpleTestCase

from agent.access_key_wizard import (
    get_access_key_wizard_status,
    save_access_key_wizard_settings,
)


class AccessKeyWizardTests(SimpleTestCase):
    def setUp(self):
        super().setUp()
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.config_path = self.root / "Tlamatini" / "agent" / "config.json"
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        self.config_path.write_text(
            json.dumps({
                "ANTHROPIC_API_KEY": "<ANTHROPIC_API_KEY goes here>",
                "GEMINI_API_KEY": "<GEMINI_API_KEY goes here>",
                "ollama_token": "<ollama_token goes here>",
                "acpx": {
                    "permissionMode": "approve-reads",
                    "agents": {},
                },
            }, indent=2) + "\n",
            encoding="utf-8",
        )
        (self.root / "data.keys").write_text(
            "# local vault\nOPENAI_API_KEY=old-openai\n",
            encoding="utf-8",
        )
        self._write_agent_yaml(
            "emailer",
            "smtp:\n  username: alice\n  password: \"<EMAILER_PASSWORD goes here>\"\n",
        )
        self._write_agent_yaml(
            "recmailer",
            "imap:\n  username: alice\n  password: \"<RECMAILER_PASSWORD goes here>\"\n",
        )

    def _write_agent_yaml(self, agent_name: str, text: str) -> None:
        path = self.root / "Tlamatini" / "agent" / "agents" / agent_name / "config.yaml"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def _patch_paths(self):
        return (
            patch("agent.access_key_wizard.find_config_path", return_value=str(self.config_path)),
            patch("agent.config_loader.find_config_path", return_value=str(self.config_path)),
        )

    def test_save_projects_values_without_echoing_secrets(self):
        gemini_secret = "gemini-secret-value"
        openai_secret = "openai-secret-value"
        email_secret = "email app password"

        p1, p2 = self._patch_paths()
        with p1, p2:
            result = save_access_key_wizard_settings({
                "fields": {
                    "GEMINI_API_KEY": gemini_secret,
                    "OPENAI_API_KEY": openai_secret,
                    "EMAILER_PASSWORD": email_secret,
                },
                "commands": {
                    "codex": "C:/Tools/codex.cmd",
                },
                "mirror_google_alias": True,
            })

        self.assertTrue(result["success"])
        response_text = json.dumps(result)
        self.assertNotIn(gemini_secret, response_text)
        self.assertNotIn(openai_secret, response_text)
        self.assertNotIn(email_secret, response_text)

        vault_text = (self.root / "data.keys").read_text(encoding="utf-8")
        self.assertIn(f"GEMINI_API_KEY={gemini_secret}", vault_text)
        self.assertIn(f"GOOGLE_API_KEY={gemini_secret}", vault_text)
        self.assertIn(f"OPENAI_API_KEY={openai_secret}", vault_text)
        self.assertIn(f"EMAILER_PASSWORD={email_secret}", vault_text)

        config = json.loads(self.config_path.read_text(encoding="utf-8"))
        self.assertEqual(config["GEMINI_API_KEY"], gemini_secret)
        self.assertEqual(
            config["acpx"]["agents"]["gemini"]["env"]["GEMINI_API_KEY"],
            gemini_secret,
        )
        self.assertEqual(
            config["acpx"]["agents"]["gemini"]["env"]["GOOGLE_API_KEY"],
            gemini_secret,
        )
        self.assertEqual(
            config["acpx"]["agents"]["codex"]["env"]["OPENAI_API_KEY"],
            openai_secret,
        )
        self.assertEqual(config["acpx"]["agents"]["codex"]["command"], "C:/Tools/codex.cmd")

        emailer_text = (
            self.root / "Tlamatini" / "agent" / "agents" / "emailer" / "config.yaml"
        ).read_text(encoding="utf-8")
        self.assertIn('password: "email app password"', emailer_text)

    def test_status_reports_configured_state_without_secret_values(self):
        secret = "status-secret-value"
        p1, p2 = self._patch_paths()
        with p1, p2:
            save_access_key_wizard_settings({
                "fields": {"ANTHROPIC_API_KEY": secret},
                "commands": {},
            })
            status = get_access_key_wizard_status()

        status_text = json.dumps(status)
        self.assertNotIn(secret, status_text)
        acpx_group = next(group for group in status["groups"] if group["key"] == "acpx")
        anthropic = next(row for row in acpx_group["fields"] if row["key"] == "ANTHROPIC_API_KEY")
        self.assertTrue(anthropic["configured"])
        self.assertTrue(anthropic["sources"]["data_keys"])
        self.assertTrue(anthropic["sources"]["config_json"])
        self.assertTrue(anthropic["sources"]["acpx_env"])

