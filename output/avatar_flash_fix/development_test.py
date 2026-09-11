"""Real development Django server with an isolated database and no agent jobs.

Run with the repository's Python: development_test.py prepare | serve
The plain 'serve' argv intentionally avoids starting agent/MCP worker pools
that would compete with the user's still-running frozen installation.
"""
import os
from pathlib import Path
import sys
import sqlite3

TEST_ROOT = Path(__file__).resolve().parent
PROJECT = TEST_ROOT.parents[1] / "Tlamatini"
sys.path.insert(0, str(PROJECT))
os.environ["DJANGO_SETTINGS_MODULE"] = "dev_settings"
os.environ["FOR_DISABLE_CONSOLE_CTRL_HANDLER"] = "1"

import django
django.setup()
from django.core.management import call_command

if sys.argv[1:] == ["prepare"]:
    from django.conf import settings
    runtime_db = Path(settings.DATABASES['default']['NAME'])
    runtime_db.parent.mkdir(parents=True, exist_ok=True)
    fixture = TEST_ROOT / "development-test.sqlite3"
    if not runtime_db.exists() and fixture.exists():
        with sqlite3.connect(fixture.as_uri() + '?mode=ro', uri=True) as original:
            with sqlite3.connect(runtime_db) as copy:
                original.backup(copy)
    call_command("migrate", interactive=False, verbosity=1)
    from django.contrib.auth import get_user_model
    user, created = get_user_model().objects.get_or_create(username="user")
    user.set_password("changeme")
    user.save(update_fields=["password"])
    print("Local isolated test user ready: user / changeme", flush=True)
    call_command("collectstatic", interactive=False, verbosity=1)
    print("Migration, test account, and project collectstatic completed.", flush=True)
elif sys.argv[1:] == ["serve"]:
    call_command("runserver", "127.0.0.1:8001", use_reloader=False, use_threading=True)
elif sys.argv[1:] == ["collect"]:
    call_command("collectstatic", interactive=False, verbosity=1)
else:
    raise SystemExit("Use prepare, collect, or serve")
