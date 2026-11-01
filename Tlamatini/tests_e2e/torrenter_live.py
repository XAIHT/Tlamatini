# Tlamatini Author Banner — Created by Angela López Mendoza · @angelahack1
"""Visible development acceptance for the installed Jobs service and an enrolled test account."""

import argparse
import getpass
import hashlib
import json
import os
import sys
import time
import urllib.request
import uuid
from pathlib import Path

from playwright.sync_api import sync_playwright
import win32console
import win32gui


def metainfo():
    url = "https://raw.githubusercontent.com/python/cpython/v3.12.10/LICENSE"
    with urllib.request.urlopen(url, timeout=15) as response:
        payload = response.read(16385)
    expected = "3b2f81fe21d181c499c59a256c8e1968455d6689d269aa85373bfb6af41da3bf"
    assert len(payload) == 13936 and hashlib.sha256(payload).hexdigest() == expected

    def string(data):
        return str(len(data)).encode() + b":" + data

    # Single-piece v1 metainfo; salt identifies this test's own disposable transfer.
    info = (
        b"d6:lengthi13936e4:name7:LICENSE12:piece lengthi16384e6:pieces20:"
        + hashlib.sha1(payload).digest()
        + b"6:source32:"
        + uuid.uuid4().hex.encode()
        + b"e"
    )
    return b"d4:info" + info + b"8:url-listl" + string(url.encode()) + b"ee", expected


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--username", required=True)
    parser.add_argument("--port", type=int, default=18084)
    args = parser.parse_args()
    console = win32console.GetConsoleWindow()
    if (
        not console
        or not win32gui.IsWindowVisible(console)
        or win32gui.IsIconic(console)
        or console != win32gui.GetForegroundWindow()
    ):
        parser.error(
            "Run from a visible, foreground development console on the interactive desktop."
        )
    password = os.environ.pop(
        "TLAMATINI_TORRENTER_TEST_PASSWORD", None
    ) or getpass.getpass("Development account password: ")
    torrent, expected = metainfo()
    base = f"http://127.0.0.1:{args.port}"
    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            channel="chrome", headless=False, args=["--start-maximized"]
        )
        page = browser.new_page(no_viewport=True)
        page.bring_to_front()
        for _ in range(80):
            hwnd = win32gui.GetForegroundWindow()
            if (
                win32gui.IsWindowVisible(hwnd)
                and not win32gui.IsIconic(hwnd)
                and win32gui.GetClassName(hwnd).startswith("Chrome_WidgetWin")
                and "Chrome" in win32gui.GetWindowText(hwnd)
            ):
                break
            time.sleep(0.1)
        else:
            raise RuntimeError("Cannot verify foreground Chrome.")
        page.goto(base + "/?next=/agent/torrenter/sources/")
        page.locator("#id_username").fill(args.username)
        page.locator("#id_password").fill(password)
        page.get_by_role("button", name="Login").click()
        page.locator("#torrent").set_input_files(
            {
                "name": "acceptance.torrent",
                "mimeType": "application/x-bittorrent",
                "buffer": torrent,
            }
        )
        page.get_by_role("button", name="Inspect metadata").click()
        inspection = page.locator("#inspection-id").inner_text(timeout=18000)
        page.get_by_text("LICENSE", exact=True).first.wait_for()
        page.wait_for_timeout(2500)
        browser.close()
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "tlamatini.settings")
    import django

    django.setup()
    from django.contrib.auth import authenticate
    from agent.chat_agent_registry import WRAPPED_CHAT_AGENT_SPECS
    from agent.context_governor import bind_user, unbind_user
    from agent.tools import _build_wrapped_chat_agent_tool

    account = authenticate(username=args.username, password=password)
    if account is None:
        parser.error("Sign in with an existing enrolled development account.")
    spec = next(s for s in WRAPPED_CHAT_AGENT_SPECS if s.key == "torrenter")
    wrapper = _build_wrapped_chat_agent_tool(spec)

    def call(action, **fields):
        result = json.loads(wrapper.invoke({"action": action, "arguments": fields}))
        if not result.get("success"):
            raise RuntimeError(result.get("message", "Torrenter action failed"))
        return result["response_body"]

    binding = bind_user(account.pk)
    try:
        meta = call("inspection", inspection_id=inspection)
        assert meta["phase"] == "ready" and [item["id"] for item in meta["files"]] == [
            0
        ]
        fields = dict(
            inspection_id=inspection,
            metadata_revision=meta["metadata_revision"],
            selected_file_ids=[0],
            destination_root_id="downloads",
            operation_key=uuid.uuid4().hex,
        )
        receipt = call("download", **fields)
        job = receipt["job_id"]
        print(
            "Admitted test job", job, "operation", receipt["operation_id"], flush=True
        )
        assert call("download", **fields)["operation_id"] == receipt["operation_id"]
        for _ in range(12):
            state = call("wait", job_id=job, wait_seconds=5)
            manifest = call("manifest", job_id=job)
            print(state["phase"], state["verified_bytes"], "verified bytes", flush=True)
            if manifest["verified"]:
                break
        assert manifest["verified"] and len(manifest["files"]) == 1
        assert (
            manifest["files"][0]["sha256"] == expected
            and manifest["files"][0]["size"] == 13936
        )
        print("PASS independently matched SHA-256", expected, flush=True)
        print(
            "Completed test job retained for inspection in XT or Tlamatini:",
            job,
            flush=True,
        )
    finally:
        unbind_user(binding)


if __name__ == "__main__":
    main()
