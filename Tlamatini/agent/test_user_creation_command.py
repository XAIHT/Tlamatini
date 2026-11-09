# Tlamatini Author Banner — Created by Angela López Mendoza · @angelahack1
"""Account-command dispatch, privacy and frozen-carriage contracts; no build runs."""

import ast
import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.contrib.auth.management.commands.createsuperuser import Command as CreateSuperuser
from django.core.checks import Tags
from django.core.management import get_commands, load_command_class
from django.test import SimpleTestCase

from agent.management.commands.createuserconsole import Command


ROOT = Path(__file__).resolve().parents[2]
MANAGE = ROOT / "Tlamatini" / "manage.py"


def source_function(name):
    tree = ast.parse(MANAGE.read_text(encoding="utf-8-sig"))
    return next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == name)


def compile_functions(names, namespace):
    module = ast.Module(body=[source_function(name) for name in names], type_ignores=[])
    exec(compile(module, str(MANAGE), "exec"), namespace)
    return namespace


class AccountCommandContractTests(SimpleTestCase):
    def test_django_discovers_the_custom_command_in_the_agent_app(self):
        self.assertEqual(get_commands()["createuserconsole"], "agent")
        self.assertIsInstance(load_command_class("agent", "createuserconsole"), Command)

    def test_account_interaction_and_password_validation_are_inherited_from_django(self):
        self.assertIs(Command.handle, CreateSuperuser.handle)
        self.assertEqual(Command.requires_system_checks, [Tags.models])
        self.assertTrue(Command.requires_migrations_checks)

    def invoke(self, *, args=(), enabled=True, tty=True, error=None):
        argv = ["Tlamatini.exe", "createuserconsole", *args]
        with (
            patch.dict(os.environ, {"TLAMATINI_USER_WIZARD": "1" if enabled else "0"}),
            patch("agent.management.commands.createuserconsole.sys.stdin") as stdin,
            patch("builtins.input", return_value="") as wait,
            patch.object(CreateSuperuser, "run_from_argv", return_value="done", side_effect=error),
        ):
            stdin.isatty.return_value = tty
            if error is None:
                self.assertEqual(Command().run_from_argv(argv), "done")
            else:
                with self.assertRaises(type(error)):
                    Command().run_from_argv(argv)
        return wait

    def test_owned_interactive_console_remains_open_after_success(self):
        self.invoke().assert_called_once()

    def test_owned_interactive_console_remains_open_after_failure(self):
        self.invoke(error=SystemExit(1)).assert_called_once()

    def test_noninteractive_noinput_does_not_wait(self):
        self.invoke(args=("--noinput",)).assert_not_called()

    def test_noninteractive_no_input_alias_does_not_wait(self):
        self.invoke(args=("--no-input",)).assert_not_called()

    def test_unowned_command_does_not_wait(self):
        self.invoke(enabled=False).assert_not_called()

    def test_redirected_input_does_not_wait(self):
        self.invoke(tty=False).assert_not_called()

    def test_both_account_commands_skip_the_shared_log_tee(self):
        for command in ("createsuperuser", "createuserconsole"):
            with self.subTest(command=command):
                namespace = compile_functions(("_setup_log_tee",), {
                    "sys": SimpleNamespace(argv=["Tlamatini.exe", command]),
                })
                with patch("builtins.open", side_effect=AssertionError("Account input must not open a log")):
                    namespace["_setup_log_tee"]()

    def test_frozen_custom_command_is_not_replaced_by_server_startup(self):
        argv = ["C:/Installed App/Tlamatini.exe", "createuserconsole"]
        runtime = SimpleNamespace(argv=list(argv), frozen=True, executable=argv[0])
        namespace = compile_functions(("_apply_configured_port", "main"), {
            "sys": runtime,
            "os": SimpleNamespace(environ={}, chdir=Mock(), path=os.path),
            "_SERVER_COMMANDS": ("runserver", "startserver"),
            "_FLOW_FILE_OPEN": None,
            "_apply_console_quick_edit_policy": Mock(),
            "_enable_console_colors": Mock(),
            "_resolve_django_port": Mock(side_effect=AssertionError("No web port needed")),
            "_schedule_browser_open": Mock(side_effect=AssertionError("No browser should open")),
            "_run_post_update_migrate_if_flagged": Mock(side_effect=AssertionError("No server migration branch")),
        })
        with patch("django.core.management.execute_from_command_line") as execute:
            namespace["main"]()
        execute.assert_called_once_with(argv)
        self.assertEqual(runtime.argv, argv)

    def test_frozen_build_explicitly_collects_and_proves_dynamic_account_modules(self):
        source = (ROOT / "build.py").read_text(encoding="utf-8-sig")
        tree = ast.parse(source)
        assignments = {
            target.id: node.value
            for node in tree.body if isinstance(node, ast.Assign)
            for target in node.targets if isinstance(target, ast.Name)
        }
        modules = set(ast.literal_eval(assignments["_FROZEN_ACCOUNT_WIZARD_MODULES"]))
        self.assertIn("agent.user_creation_wizard", modules)
        self.assertIn("agent.management.commands.createuserconsole", modules)
        required = assignments["_FROZEN_REQUIRED_AGENT_MODULES"]
        self.assertTrue(any(isinstance(node, ast.Starred) and isinstance(node.value, ast.Name)
                            and node.value.id == "_FROZEN_ACCOUNT_WIZARD_MODULES"
                            for node in required.elts))
        self.assertIn("for module in _FROZEN_ACCOUNT_WIZARD_MODULES", source)
        # Follow only constant dynamic imports used by this handler's shipped cards.
        # This catches a missing historical template dependency without executing build.py.
        pending, checked = list(modules), set()
        while pending:
            name = pending.pop()
            if name in checked:
                continue
            checked.add(name)
            path = ROOT / "Tlamatini" / Path(*name.split(".")).with_suffix(".py")
            self.assertTrue(path.is_file(), str(path))
            module_tree = ast.parse(path.read_text(encoding="utf-8-sig"))
            for node in ast.walk(module_tree):
                if not isinstance(node, ast.Call) or not node.args:
                    continue
                function = node.func
                called = function.id if isinstance(function, ast.Name) else getattr(function, "attr", "")
                if called != "import_module" or not isinstance(node.args[0], ast.Constant):
                    continue
                dependency = node.args[0].value
                if isinstance(dependency, str) and dependency.startswith("agent.migrations."):
                    self.assertIn(dependency, modules, f"Missing explicit frozen dependency: {dependency}")
                    pending.append(dependency)

