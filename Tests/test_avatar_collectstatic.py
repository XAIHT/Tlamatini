"""Verify real Django collectstatic preserves avatar assets byte-for-byte.

This isolated collector uses the project's default StaticFilesStorage without
starting agent workers, reading application credentials, or touching databases.
The build uses collectstatic then bundles staticfiles (see build.py).
"""
from hashlib import sha256
from pathlib import Path
import json
import tempfile

from django.conf import settings
from django.contrib.staticfiles.finders import BaseFinder
from django.core.files.storage import FileSystemStorage


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "Tlamatini/agent/static"
FILES = ["agent/css/avatar.css", "agent/js/avatar.js"] + [
    "agent/img/avatar/" + key + ".jpg"
    for key in ("eo_mc", "ec_mc", "eo_mo", "ec_mo")
]


class AvatarFinder(BaseFinder):
    """Limit collection to the files under test, using real source bytes."""

    def list(self, ignore_patterns):
        storage = FileSystemStorage(location=SOURCE)
        for name in FILES:
            yield name, storage

    def find(self, path, find_all=False, **kwargs):
        matches = [str(SOURCE / path)] if path in FILES else []
        return matches if find_all else (matches[0] if matches else None)


def main():
    report_dir = ROOT / "output/avatar_flash_fix"
    report_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="avatar-collectstatic-") as target:
        settings.configure(
            INSTALLED_APPS=["django.contrib.staticfiles"],
            STATIC_URL="/static/", STATIC_ROOT=target,
            STATICFILES_FINDERS=["__main__.AvatarFinder"],
            STORAGES={"staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"}},
        )
        import django
        from django.core.management import call_command
        django.setup()
        call_command("collectstatic", interactive=False, verbosity=0)
        results = []
        for name in FILES:
            original = (SOURCE / name).read_bytes()
            copied = (Path(target) / name).read_bytes()
            assert copied == original, name
            results.append({"asset": name, "bytes": len(original), "sha256": sha256(original).hexdigest(), "collectstatic_exact_copy": True})
        report = {"django": django.get_version(), "storage": settings.STORAGES["staticfiles"]["BACKEND"], "assets": results}
        (report_dir / "collectstatic-results.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(json.dumps(report, indent=2))
        print("PASS: collectstatic copied all six assets exactly; no image conversion/resizing.")


if __name__ == "__main__":
    main()
