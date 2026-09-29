"""Isolated settings for the requested visible Django avatar tests only.

Restored 2026-09-29 from git (1d222286~1:output/avatar_flash_fix/dev_settings.py).
It used to live under output/, which was cleaned out on 2026-09-15 together
with old screenshots; that cleanup silently broke Tests/run_avatar_tests.py.
It now lives beside the tests that need it.
"""
import time
from pathlib import Path

from tlamatini.settings import *  # noqa: F403

TEST_ROOT = Path(__file__).resolve().parent
RUNTIME_ROOT = TEST_ROOT.parents[1] / "Temp/avatar_flash_fix"
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": RUNTIME_ROOT / "development-test.sqlite3",
    }
}
DEBUG = True
ALLOWED_HOSTS = ["127.0.0.1", "localhost", "testserver"]
SESSION_COOKIE_NAME = "tlm_avatar_test_session"
CSRF_COOKIE_NAME = "tlm_avatar_test_csrf"
STATIC_ROOT = TEST_ROOT.parents[1] / "Tlamatini/staticfiles"
# A fresh tag per server start, so the visible browser can never test a stale,
# cached copy of the avatar code (the old fixed tag allowed exactly that).
STATIC_VERSION = "avatar-visible-test-%d" % int(time.time())
