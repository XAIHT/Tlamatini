# Tlamatini Author Banner — Created by Angela López Mendoza · @angelahack1
"""User input in a setup wizard must not become command takeover or notification consent."""

import json

from django.test import SimpleTestCase, TestCase
from langchain_core.tools import tool

from agent import terminal_guard as guard
from agent.mcp_agent import MultiTurnToolAgentExecutor, _detect_completion_notification_request
from agent.models import Prompt
from agent.test_terminater_reliability import _ScriptedLLM, THE_RUST_USER_SENTENCE


class WizardIntentTests(SimpleTestCase):
    def test_typing_data_does_not_take_over_command_execution(self):
        for text in (
            "Never ask for my password in chat. I will type it only into the console you open.",
            "Let me type my password myself.",
            "I will enter it at the password prompt.",
            "I want to type them",  # ambiguous: commands, credentials or editor text
            "Let me type the email address.",
            "I will do that in the editor.",
            "Yo lo escribo en el editor.",
        ):
            with self.subTest(text=text):
                self.assertEqual(guard.classify_message(text)[0], "")

    def test_typing_commands_still_reserves_execution_for_the_user(self):
        for text in (
            "I will type the commands myself.", "Let me enter each command.",
            "I want to type the command.", "I will press Enter.",
            "Let me run it.", "I will run them, not you.",
        ):
            with self.subTest(text=text):
                self.assertEqual(guard.classify_message(text)[0], "user_runs")

    def test_explicit_program_launch_gives_control_back(self):
        for text in (
            "You will run Django's createsuperuser. I will type my password.",
            "You should execute the installer. Let me type my email myself.",
        ):
            with self.subTest(text=text):
                self.assertEqual(guard.classify_message(text)[0], "lift")

    def test_notification_requires_an_affirmative_request_to_send(self):
        for text in (
            "When the setup is done, tell me here. The email field is optional.",
            "When you finish, tell me the next step in this chat.",
            "When I am done, I will email you.",
            "When finished, do not notify me.",
            "Don't email me when it's done.",
            "When finished, no need to send me a Telegram.",
            "When finished, never send me an email.",
            'Explain this example: "When finished, email me."',
            "Explain this code:\n```text\nWhen finished, notify me.\n```",
            "After finishing the form, show me the email address.",
            "Send me the report now. Explain what happens when the build is done.",
        ):
            with self.subTest(text=text):
                self.assertFalse(_detect_completion_notification_request(text))

    def test_explicit_completion_notifications_still_work(self):
        for text in (
            "When you finish, send me a Telegram.",
            "Email me when it's done.",
            "Once the scan completes, notify me on WhatsApp.",
            "After finishing, send me a notification.",
            "When done, please send the report by email.",
            "Run the tests; when finished, alert me.",
            "When done, don't forget to email me.",
        ):
            with self.subTest(text=text):
                self.assertTrue(_detect_completion_notification_request(text))


class UserCreationCatalogGuardTests(TestCase):
    """Exercise the migrated catalog request through the real tool loop, without OS/account changes."""

    def setUp(self):
        guard.reset()
        self.prompt = Prompt.objects.get(idPrompt=1).promptContent
        self.assertIn("createsuperuser", self.prompt)
        self.assertIn("I will type it only into the console", self.prompt)

    def tearDown(self):
        guard.reset()

    def test_real_catalog_does_not_request_a_notification(self):
        self.assertFalse(_detect_completion_notification_request(self.prompt))

    def test_real_catalog_lifts_a_previous_command_tutorial(self):
        mode = guard.observe("wizard", self.prompt, [{"type": "human", "content": THE_RUST_USER_SENTENCE}])
        self.assertFalse(mode.user_runs)
        self.assertEqual(guard.runner_block("chat_agent_executer", mode), "")

    def test_source_and_frozen_wizard_keep_executer_and_wait_for_input(self):
        for runtime in ("SOURCE", "FROZEN"):
            with self.subTest(runtime=runtime):
                calls = []

                @tool
                def chat_agent_executer(request: str) -> str:
                    """Record a requested command without running it."""
                    calls.append(request)
                    return json.dumps({"status": "completed", "output": (
                        "TLAMATINI_MODE=" + runtime if len(calls) == 1 else "Interactive console launched"
                    )})

                history = [{"type": "human", "content": THE_RUST_USER_SENTENCE}]
                launch = ('"%TLAMATINI_TEMP%\\..\\Tlamatini.exe" createsuperuser' if runtime == "FROZEN"
                          else 'python manage.py createsuperuser')
                for message, request, answer in (
                    (self.prompt, "script='echo TLAMATINI_MODE'", "Detected the runtime. Ready for the next step."),
                    ("Continue", f"script='{launch}' and execute_forked_window=true and non_blocking=true",
                     "Enter your password only in the console, then reply DONE. I will wait."),
                ):
                    llm = _ScriptedLLM([
                        {"calls": [("chat_agent_executer", {"request": request})]}, {"content": answer},
                    ])
                    executor = MultiTurnToolAgentExecutor(llm=llm, system_prompt="test", tools=[chat_agent_executer])
                    result = executor.invoke({"input": message, "chat_history": history,
                                              "ask_execs_user_id": "wizard-" + runtime, "exec_report_enabled": True})
                    self.assertEqual(len(llm.seen), 2, "A guard diverted the model from the requested wizard")
                    self.assertEqual(result["output"], answer)
                    self.assertTrue(result["exec_report_entries"][0]["success"])
                    history.extend([{"type": "human", "content": message}, {"type": "ai", "content": answer}])
                self.assertEqual(len(calls), 2)
                self.assertIn("createsuperuser", calls[1])
