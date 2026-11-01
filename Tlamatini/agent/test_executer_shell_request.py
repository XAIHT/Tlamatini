"""Keep CMD environment assignments inside Executer's shell script."""
from pathlib import Path
from django.test import SimpleTestCase
import yaml

from .tools import _apply_executer_request


class ExecuterShellRequestTests(SimpleTestCase):
    def apply(self, text):
        config = yaml.safe_load((Path(__file__).parent / "agents/executer/config.yaml").read_text(encoding="utf8"))
        return _apply_executer_request(config, text)

    def test_recorded_command_with_explicit_wrapper_options(self):
        command = r"set PLAYWRIGHT_BROWSERS_PATH=C:\Tlamatini\ms-playwright && uv run --directory C:\Development\MCPS\torrent-search-mcp python -m playwright install chromium"
        result, error, _ = self.apply("Run this command and report the full output: " + command
                                      + "   (use script='" + command + "' and non_blocking=false and timeout=900)")
        self.assertIsNone(error)
        self.assertEqual(result["script"], command)
        self.assertEqual(result["command_timeout_seconds"], 900)
        self.assertIs(result["non_blocking"], False)

    def test_bare_and_prefixed_shell_text_keep_assignments_verbatim(self):
        command = r'set "EXAMPLE=a=b" && echo flag=value'
        for prefix in ("", "Run this command: ", "Ejecuta este comando: "):
            with self.subTest(prefix=prefix):
                config, error, _ = self.apply(prefix + command)
                self.assertIsNone(error)
                self.assertEqual(config["script"], command)

    def test_explicit_configuration_still_checks_unknown_settings(self):
        for prefix in ("", "Execute this command: "):
            _, error, _ = self.apply(prefix + "script='echo ok' and unknown_setting=true")
            self.assertIn("unknown_setting", error)
