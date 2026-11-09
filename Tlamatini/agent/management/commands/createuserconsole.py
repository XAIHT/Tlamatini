# Tlamatini Author Banner — Created by Angela López Mendoza · @angelahack1
"""The real Django account wizard, without unrelated web/LLM startup checks."""

import os
import sys

from django.contrib.auth.management.commands.createsuperuser import Command as CreateSuperuser
from django.core.checks import Tags


class Command(CreateSuperuser):
    # Preserve model consistency, migrations, duplicate-name checks and password
    # validation. URL checks import the chat stack but do not validate accounts.
    requires_system_checks = [Tags.models]

    def run_from_argv(self, argv):
        try:
            return super().run_from_argv(argv)
        finally:
            # Keep only integrated interactive launches open for their result.
            if (os.environ.get('TLAMATINI_USER_WIZARD') == '1'
                    and '--noinput' not in argv and '--no-input' not in argv
                    and sys.stdin.isatty()):
                try:
                    input('\nPress Enter to close this console. ')
                except (EOFError, KeyboardInterrupt):
                    pass
