"""Visible, dev-only Backup DB / Set DB round-trip regression test.

This test launches a headed Chromium window, drives the real Tlamatini DB menu,
restarts the source development server for every staged database, and checks
SQLite integrity plus exact ``agent_agentmessage`` correspondence.  It copies
the source fixtures before using them and always restores the original dev DB.

Run from the repository root (port 8000 must be free)::

    python Tlamatini/tests_e2e/test_db_backup_set_visible.py

Optional environment variables:
``TLAMATINI_DB_FIXTURES`` (two ``;``-separated db.sqlite3 paths),
``TLAMATINI_DB_ROOT``, ``TLAMATINI_USER``, ``TLAMATINI_PASS``,
``TLAMATINI_DB_TEST_PORT``, and ``TLAMATINI_DB_TEST_SLOWMO``.
"""

from __future__ import annotations

import hashlib
import json
import os
import signal
import socket
import sqlite3
import subprocess
import sys
import time
import urllib.request
from contextlib import closing
from datetime import datetime
from pathlib import Path

from playwright.sync_api import Page, sync_playwright


APP_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = APP_DIR.parent
LIVE_DB = APP_DIR / "db.sqlite3"
STAGE_DB = APP_DIR / "DB" / "ToLoad" / "db.sqlite3"
INSTALLED_ROOT = Path(r"C:\Tlamatini").resolve()
FIXTURE_ROOT = Path(
    os.environ.get(
        "TLAMATINI_DB_ROOT",
        r"C:\Users\angel\OneDrive\Desktop\TlamatiniDatabases",
    )
)
USER = os.environ.get("TLAMATINI_USER", "user")
PASSWORD = os.environ.get("TLAMATINI_PASS", "changeme")
PORT = int(os.environ.get("TLAMATINI_DB_TEST_PORT", "8000"))
SLOW_MO = int(os.environ.get("TLAMATINI_DB_TEST_SLOWMO", "80"))
BASE_URL = f"http://127.0.0.1:{PORT}"


def _refuse_installed_tree() -> None:
    app = APP_DIR.resolve()
    if app == INSTALLED_ROOT or INSTALLED_ROOT in app.parents:
        raise RuntimeError(
            f"REFUSING to run against installed Tlamatini tree: {app}"
        )
    if not (APP_DIR / "manage.py").is_file() or not (REPO_ROOT / ".git").exists():
        raise RuntimeError(f"Not a source development checkout: {APP_DIR}")


def _sqlite_snapshot(source: Path, target: Path) -> None:
    """Copy a live/offline SQLite DB with the SQLite backup API (WAL-safe)."""
    target.parent.mkdir(parents=True, exist_ok=True)
    for suffix in ("", "-wal", "-shm", "-journal"):
        candidate = Path(str(target) + suffix)
        if candidate.exists():
            candidate.unlink()
    uri = f"file:{source.resolve().as_posix()}?mode=ro"
    with closing(sqlite3.connect(uri, uri=True, timeout=30)) as src:
        with closing(sqlite3.connect(target, timeout=30)) as dst:
            src.backup(dst)
            dst.execute("PRAGMA journal_mode=DELETE")
            dst.commit()
    if _fingerprint(target)["quick_check"] != "ok":
        raise AssertionError(f"Snapshot failed SQLite quick_check: {target}")


def _fingerprint(path: Path) -> dict[str, object]:
    uri = f"file:{path.resolve().as_posix()}?mode=ro"
    with closing(sqlite3.connect(uri, uri=True, timeout=30)) as connection:
        quick_check = connection.execute("PRAGMA quick_check").fetchone()[0]
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        if "agent_agentmessage" not in tables:
            raise AssertionError(f"Not a compatible Tlamatini DB: {path}")
        messages = connection.execute(
            "SELECT * FROM agent_agentmessage ORDER BY id"
        ).fetchall()
        migrations = connection.execute(
            "SELECT app, name FROM django_migrations ORDER BY app, name"
        ).fetchall()
    return {
        "path": str(path),
        "quick_check": quick_check,
        "message_count": len(messages),
        "message_digest": hashlib.sha256(repr(messages).encode()).hexdigest(),
        "migration_digest": hashlib.sha256(repr(migrations).encode()).hexdigest(),
        "table_count": len(tables),
        "wal": Path(str(path) + "-wal").exists(),
        "shm": Path(str(path) + "-shm").exists(),
    }


def _assert_correspondence(actual: Path, expected: Path, label: str) -> dict[str, object]:
    got = _fingerprint(actual)
    want = _fingerprint(expected)
    assert got["quick_check"] == "ok", f"{label}: live quick_check failed"
    assert want["quick_check"] == "ok", f"{label}: expected quick_check failed"
    assert got["message_count"] == want["message_count"], (
        f"{label}: message count {got['message_count']} != {want['message_count']}"
    )
    assert got["message_digest"] == want["message_digest"], (
        f"{label}: exact message rows do not correspond"
    )
    return {"label": label, "actual": got, "expected": want, "passed": True}


def _fixtures() -> tuple[Path, Path]:
    configured = os.environ.get("TLAMATINI_DB_FIXTURES", "").strip()
    if configured:
        paths = [Path(item.strip()) for item in configured.split(";") if item.strip()]
        if len(paths) != 2:
            raise RuntimeError("TLAMATINI_DB_FIXTURES must contain exactly two paths")
        return paths[0], paths[1]
    preferred = (
        FIXTURE_ROOT / "WiresharkMCPSamples" / "db.sqlite3",
        FIXTURE_ROOT / "MCPResearchReport" / "db.sqlite3",
    )
    if all(path.is_file() for path in preferred):
        return preferred
    candidates = []
    for path in FIXTURE_ROOT.rglob("db.sqlite3"):
        try:
            fp = _fingerprint(path)
        except (AssertionError, sqlite3.Error):
            continue
        candidates.append((int(fp["message_count"]), path))
    by_count: dict[int, Path] = {}
    for count, path in sorted(candidates):
        by_count.setdefault(count, path)
    if len(by_count) < 2:
        raise RuntimeError(f"Need two compatible DB fixtures under {FIXTURE_ROOT}")
    counts = sorted(by_count)
    return by_count[counts[-2]], by_count[counts[-1]]


def _port_is_free() -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        return sock.connect_ex(("127.0.0.1", PORT)) != 0


class DevServer:
    def __init__(self, log_path: Path) -> None:
        self.log_path = log_path
        self.process: subprocess.Popen[bytes] | None = None
        self._log = None

    def start(self) -> None:
        if not _port_is_free():
            raise RuntimeError(f"Port {PORT} is already in use; stop that server first")
        self._log = self.log_path.open("ab")
        flags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
        self.process = subprocess.Popen(
            [
                sys.executable,
                "manage.py",
                "runserver",
                "--noreload",
                f"127.0.0.1:{PORT}",
            ],
            cwd=APP_DIR,
            stdout=self._log,
            stderr=subprocess.STDOUT,
            creationflags=flags,
        )
        deadline = time.time() + 180
        last_error: Exception | None = None
        while time.time() < deadline:
            if self.process.poll() is not None:
                raise RuntimeError(
                    f"Development server exited with {self.process.returncode}; "
                    f"see {self.log_path}"
                )
            try:
                urllib.request.urlopen(BASE_URL + "/", timeout=2).close()
                return
            except Exception as exc:  # noqa: BLE001 - readiness polling
                last_error = exc
                time.sleep(0.4)
        raise RuntimeError(f"Server readiness timed out: {last_error}")

    def stop(self) -> None:
        process = self.process
        if process is None:
            return
        if process.poll() is None:
            try:
                if os.name == "nt":
                    process.send_signal(signal.CTRL_BREAK_EVENT)
                else:
                    process.terminate()
                process.wait(timeout=20)
            except (OSError, subprocess.TimeoutExpired):
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=10)
        self.process = None
        if self._log is not None:
            self._log.close()
            self._log = None
        deadline = time.time() + 15
        while not _port_is_free() and time.time() < deadline:
            time.sleep(0.25)

    def restart(self) -> None:
        self.stop()
        self.start()


def _login(page: Page) -> None:
    page.goto(BASE_URL + "/agent/agent/", wait_until="domcontentloaded")
    if page.locator("#id_username").count():
        page.locator("#id_username").fill(USER)
        page.locator("#id_password").fill(PASSWORD)
        page.get_by_role("button", name="Login", exact=True).click()
        page.wait_for_load_state("domcontentloaded")
    page.goto(BASE_URL + "/agent/agent/", wait_until="domcontentloaded")
    page.wait_for_selector("#chat-message-input", timeout=60_000)


def _open_db_item(page: Page, item: str) -> None:
    page.get_by_role("button", name="DB", exact=True).click()
    page.get_by_role("link", name=item, exact=True).click()


def _ui_backup(page: Page, target_dir: Path) -> Path:
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / "db.sqlite3"
    if target.exists():
        target.unlink()
    _open_db_item(page, "Backup database")
    page.locator("#backup-db-target-dir").fill(str(target_dir))
    page.wait_for_function(
        "document.querySelector('#backup-db-status').textContent.includes('Directory exists')"
    )
    with page.expect_event("dialog", timeout=60_000) as dialog_info:
        page.get_by_role("button", name="Backup", exact=True).click()
    dialog = dialog_info.value
    assert "successfully" in dialog.message.lower(), dialog.message
    dialog.dismiss()
    assert target.is_file(), f"Backup was not created: {target}"
    return target


def _ui_set(page: Page, source: Path) -> None:
    _open_db_item(page, "Set DB")
    page.locator("#set-db-source-path").fill(str(source))
    page.wait_for_function(
        "document.querySelector('#set-db-status').textContent.includes('File exists')"
    )
    page.get_by_role("button", name="Set", exact=True).click()
    page.get_by_text("Database staged for next session", exact=True).wait_for()
    page.get_by_role("button", name="OK", exact=True).click()
    assert STAGE_DB.is_file(), "Set DB did not create DB/ToLoad/db.sqlite3"
    staged = _fingerprint(STAGE_DB)
    expected = _fingerprint(source)
    assert staged["message_digest"] == expected["message_digest"]
    assert not Path(str(STAGE_DB) + "-wal").exists()
    assert not Path(str(STAGE_DB) + "-shm").exists()


def _screenshot(page: Page, out_dir: Path, number: int, name: str) -> None:
    page.screenshot(path=out_dir / f"{number:02d}_{name}.png", full_page=True)


def main() -> int:
    _refuse_installed_tree()
    if not _port_is_free():
        raise RuntimeError(f"Port {PORT} is busy. This test only manages the dev server.")

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = REPO_ROOT / "Temp" / f"db_backup_set_visible_{stamp}"
    out_dir.mkdir(parents=True)
    server = DevServer(out_dir / "server.log")
    results: list[dict[str, object]] = []
    original_snapshot = out_dir / "fixtures" / "original_dev" / "db.sqlite3"
    fixture_a_snapshot = out_dir / "fixtures" / "fixture_a" / "db.sqlite3"
    fixture_b_snapshot = out_dir / "fixtures" / "fixture_b" / "db.sqlite3"
    source_a, source_b = _fixtures()
    print(f"DEV-ONLY headed DB test: {APP_DIR}", flush=True)
    print(f"Fixture A: {source_a}", flush=True)
    print(f"Fixture B: {source_b}", flush=True)

    _sqlite_snapshot(LIVE_DB, original_snapshot)
    _sqlite_snapshot(source_a, fixture_a_snapshot)
    _sqlite_snapshot(source_b, fixture_b_snapshot)
    if _fingerprint(fixture_a_snapshot)["message_digest"] == _fingerprint(
        fixture_b_snapshot
    )["message_digest"]:
        raise AssertionError("The two fixtures must contain different message histories")

    restored_original = False
    browser = None
    try:
        server.start()
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=False, slow_mo=SLOW_MO)
            context = browser.new_context(viewport={"width": 1500, "height": 940})
            page = context.new_page()
            _login(page)
            _screenshot(page, out_dir, 1, "original_dev")

            original_ui_backup = _ui_backup(page, out_dir / "ui_backup_original")
            results.append(
                _assert_correspondence(
                    original_ui_backup, LIVE_DB, "backup original live DB"
                )
            )
            assert not Path(str(original_ui_backup) + "-wal").exists()
            assert not Path(str(original_ui_backup) + "-shm").exists()
            _screenshot(page, out_dir, 2, "original_backup_complete")

            _ui_set(page, fixture_a_snapshot)
            server.restart()
            _login(page)
            results.append(_assert_correspondence(LIVE_DB, fixture_a_snapshot, "set A"))
            assert not STAGE_DB.exists(), "Staged A was not consumed at startup"
            _screenshot(page, out_dir, 3, "fixture_a_loaded")

            backup_a = _ui_backup(page, out_dir / "ui_backup_fixture_a")
            results.append(_assert_correspondence(backup_a, LIVE_DB, "backup A"))
            _screenshot(page, out_dir, 4, "fixture_a_backed_up")

            _ui_set(page, fixture_b_snapshot)
            server.restart()
            _login(page)
            results.append(_assert_correspondence(LIVE_DB, fixture_b_snapshot, "set B"))
            assert not STAGE_DB.exists(), "Staged B was not consumed at startup"
            _screenshot(page, out_dir, 5, "fixture_b_loaded")

            _ui_set(page, backup_a)
            server.restart()
            _login(page)
            results.append(
                _assert_correspondence(LIVE_DB, fixture_a_snapshot, "restore backup A")
            )
            _screenshot(page, out_dir, 6, "backup_a_restored")

            _ui_set(page, original_ui_backup)
            server.restart()
            _login(page)
            results.append(
                _assert_correspondence(LIVE_DB, original_snapshot, "restore original")
            )
            assert not STAGE_DB.exists(), "Original staged DB was not consumed"
            restored_original = True
            _screenshot(page, out_dir, 7, "original_restored")
            (out_dir / "RESULT.json").write_text(
                json.dumps(
                    {
                        "passed": True,
                        "headed": True,
                        "installed_tree_touched": False,
                        "source_fixtures": [str(source_a), str(source_b)],
                        "checks": results,
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )
            print(f"PASS: {len(results)}/6 correspondence checks", flush=True)
            print(f"Artifacts: {out_dir}", flush=True)
            page.wait_for_timeout(2_000)
            context.close()
            browser.close()
            browser = None
        return 0
    finally:
        if browser is not None:
            try:
                browser.close()
            except Exception:  # noqa: BLE001 - Playwright may already be stopped
                pass
        try:
            server.stop()
        finally:
            if not restored_original:
                # Fail-safe cleanup: restore the consistent pre-test dev snapshot
                # through the pre-Django staging location, then launch once to
                # consume it even when the visible-browser assertions fail.
                _sqlite_snapshot(original_snapshot, STAGE_DB)
                server.start()
                server.stop()
                cleanup = _assert_correspondence(
                    LIVE_DB, original_snapshot, "fail-safe restore"
                )
                print(
                    f"Fail-safe original DB restore: {cleanup['passed']}",
                    flush=True,
                )


if __name__ == "__main__":
    raise SystemExit(main())
