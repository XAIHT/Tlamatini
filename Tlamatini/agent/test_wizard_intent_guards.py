# Tlamatini Author Banner — Created by Angela López Mendoza · @angelahack1
"""User input in a setup wizard must not become command takeover or notification consent."""

import importlib
import json

from django.apps import apps
from django.test import SimpleTestCase, TestCase
from langchain_core.tools import tool

from agent import terminal_guard as guard
from agent.mcp_agent import MultiTurnToolAgentExecutor, _detect_completion_notification_request
from agent.models import Prompt
from agent.test_terminater_reliability import _ScriptedLLM, THE_RUST_USER_SENTENCE


wizard_migration = importlib.import_module(
    "agent.migrations.0219_user_wizard_graphical_notifications"
)


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

    def test_real_catalog_requests_local_checkpoints_without_premature_completion_debt(self):
        self.assertFalse(_detect_completion_notification_request(self.prompt))
        self.assertIn("I explicitly request local graphical Notifier alerts", self.prompt)
        for label in ("Username needed", "Console input needed", "Error creating user",
                      "Warning: console not visible", "User ready"):
            self.assertIn("target.search_strings='" + label + "'", self.prompt)
        self.assertIn("not email, Telegram, WhatsApp or other external messages", self.prompt)
        self.assertIn("a launched window or a typed command is not success", self.prompt)

    def test_historical_catalog_still_does_not_authorize_notifications(self):
        self.assertFalse(_detect_completion_notification_request(wizard_migration.OLD_WIZARD_PROMPT))

    def test_migration_updates_only_the_known_default_and_is_reversible(self):
        row = Prompt.objects.get(idPrompt=1)
        metadata = (row.promptName, row.category, row.sort_rank, row.hidden)
        row.promptContent = wizard_migration.OLD_WIZARD_PROMPT
        row.save(update_fields=["promptContent"])
        wizard_migration.apply_update(apps, None)
        row.refresh_from_db()
        self.assertEqual(row.promptContent, wizard_migration.WIZARD_PROMPT)
        self.assertEqual((row.promptName, row.category, row.sort_rank, row.hidden), metadata)
        wizard_migration.reverse_update(apps, None)
        row.refresh_from_db()
        self.assertEqual(row.promptContent, wizard_migration.OLD_WIZARD_PROMPT)
        customized = wizard_migration.OLD_WIZARD_PROMPT + "\nMy custom instruction."
        row.promptContent = customized
        row.save(update_fields=["promptContent"])
        wizard_migration.apply_update(apps, None)
        wizard_migration.reverse_update(apps, None)
        row.refresh_from_db()
        self.assertEqual(row.promptContent, customized)

    def test_real_catalog_lifts_a_previous_command_tutorial(self):
        mode = guard.observe("wizard", self.prompt, [{"type": "human", "content": THE_RUST_USER_SENTENCE}])
        self.assertFalse(mode.user_runs)
        self.assertEqual(guard.runner_block("chat_agent_executer", mode), "")

    def test_source_and_frozen_wizard_keep_executer_and_wait_for_input(self):
        for runtime in ("SOURCE", "FROZEN"):
            with self.subTest(runtime=runtime):
                calls = []
                notifications = []

                @tool
                def chat_agent_executer(request: str) -> str:
                    """Record a requested command without running it."""
                    calls.append(request)
                    return json.dumps({"status": "completed", "output": (
                        "TLAMATINI_MODE=" + runtime if len(calls) == 1 else "Interactive console launched"
                    )})

                @tool
                def chat_agent_notifier(request: str) -> str:
                    """Record a local graphical alert without displaying one."""
                    notifications.append(request)
                    return json.dumps({"status": "completed", "output": "Notification file created"})

                history = [{"type": "human", "content": THE_RUST_USER_SENTENCE}]
                launch = ('"%TLAMATINI_TEMP%\\..\\Tlamatini.exe" createsuperuser' if runtime == "FROZEN"
                          else 'python manage.py createsuperuser')
                for message, request, answer in (
                    (self.prompt, "script='echo TLAMATINI_MODE'", "Detected the runtime. Ready for the next step."),
                    ("Continue", f"script='{launch}' and execute_forked_window=true and non_blocking=true",
                     "Enter your password only in the console, then reply DONE. I will wait."),
                ):
                    script = [{"calls": [("chat_agent_executer", {"request": request})]}]
                    if message == "Continue":
                        script.append({"calls": [("chat_agent_notifier", {"request":
                            "target.mode='oneshot' and target.search_strings='Console input needed' "
                            "and target.outcome_detail='Use the console, then confirm its success in chat.' "
                            "and target.sound_enabled=true"})]})
                    script.append({"content": answer})
                    llm = _ScriptedLLM(script)
                    executor = MultiTurnToolAgentExecutor(
                        llm=llm, system_prompt="test", tools=[chat_agent_executer, chat_agent_notifier]
                    )
                    result = executor.invoke({"input": message, "chat_history": history,
                                              "ask_execs_user_id": "wizard-" + runtime, "exec_report_enabled": True})
                    self.assertEqual(len(llm.seen), len(script),
                                     "A guard diverted the model from the requested wizard")
                    self.assertEqual(result["output"], answer)
                    self.assertTrue(result["exec_report_entries"][0]["success"])
                    history.extend([{"type": "human", "content": message}, {"type": "ai", "content": answer}])
                self.assertEqual(len(calls), 2)
                self.assertIn("createsuperuser", calls[1])
                self.assertEqual(len(notifications), 1)
                self.assertNotIn("User ready", notifications[0])

    def test_local_checkpoint_calls_survive_error_nowindow_and_success_continuations(self):
        for reply, label in (
            ("ERROR: The username is already taken.", "Error creating user"),
            ("NOWINDOW", "Warning: console not visible"),
            ("DONE: I saw Superuser created successfully in the console.", "User ready"),
        ):
            with self.subTest(reply=reply):
                alerts = []

                @tool
                def chat_agent_notifier(request: str) -> str:
                    """Record the local alert without sending any message."""
                    alerts.append(request)
                    return json.dumps({"status": "completed", "output": "Notification file created"})

                answer = "Follow the next step in chat."
                request = ("target.mode='oneshot' and target.search_strings='" + label +
                           "' and target.outcome_detail='Follow the next step in chat.' "
                           "and target.sound_enabled=true")
                llm = _ScriptedLLM([
                    {"calls": [("chat_agent_notifier", {"request": request})]},
                    {"content": answer},
                ])
                executor = MultiTurnToolAgentExecutor(
                    llm=llm, system_prompt="test", tools=[chat_agent_notifier]
                )
                result = executor.invoke({
                    "input": reply,
                    "chat_history": [{"type": "human", "content": self.prompt},
                                     {"type": "ai", "content": "Complete the console prompts, then reply."}],
                    "ask_execs_user_id": "wizard-checkpoint-" + label,
                    "exec_report_enabled": True,
                })
                self.assertEqual(alerts, [request])
                self.assertEqual(len(llm.seen), 2)
                self.assertEqual(result["output"], answer)
