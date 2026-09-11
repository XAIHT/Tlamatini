"""Isolated settings for the requested visible Django avatar tests only."""
from tlamatini.settings import *  # noqa: F403
from pathlib import Path

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
STATIC_VERSION = "avatar-atomic-visible-test-1"
