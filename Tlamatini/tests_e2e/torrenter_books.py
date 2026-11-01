# Tlamatini Author Banner — Created by Angela López Mendoza · @angelahack1
"""Verify publisher PDFs through the authenticated source form, wrapped agent and live queue."""
import argparse
import asyncio
from concurrent.futures import ThreadPoolExecutor
from contextvars import copy_context
import hashlib
import json
import os
import sys
import time
import uuid
from pathlib import Path
from urllib.parse import urlparse

from playwright.sync_api import sync_playwright


def torrent(book, source, salt):
    def encode(data):
        return str(len(data)).encode() + b":" + data

    assert hashlib.sha256(source).hexdigest() == book["sha256"]
    length = 131072
    pieces = b"".join(hashlib.sha1(source[i:i + length]).digest() for i in range(0, len(source), length))
    name = Path(urlparse(book["url"]).path).name.encode()
    info = (b"d6:lengthi" + str(len(source)).encode() + b"e4:name" + encode(name)
            + b"12:piece lengthi131072e6:pieces" + encode(pieces) + b"7:privatei1e6:source" + encode(salt.encode()) + b"e")
    return b"d4:info" + info + b"8:url-listl" + encode(book["url"].encode()) + b"ee"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path, required=True)
    parser.add_argument("--origin", required=True)
    parser.add_argument("--username", required=True)
    parser.add_argument("--receipts", type=Path, required=True)
    parser.add_argument("--browser-port", type=int, required=True)
    args = parser.parse_args()
    if urlparse(args.origin).hostname != "127.0.0.1":
        parser.error("Use the local development server.")
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "tlamatini.settings")
    import django
    django.setup()
    from django.contrib.auth import authenticate
    from agent.chat_agent_registry import WRAPPED_CHAT_AGENT_SPECS
    from agent.tools import _build_wrapped_chat_agent_tool
    from agent.context_governor import bind_user, unbind_user
    user = authenticate(username=args.username, password=os.environ["TLAMATINI_TORRENTER_TEST_PASSWORD"])
    if not user:
        raise RuntimeError("Development login failed.")
    spec = next(s for s in WRAPPED_CHAT_AGENT_SPECS if s.key == "torrenter")
    wrapper = _build_wrapped_chat_agent_tool(spec)
    def call(action, **fields):
        with ThreadPoolExecutor(max_workers=1) as executor:
            response = json.loads(executor.submit(copy_context().run, wrapper.invoke,
                                                  {"action": action, "arguments": fields}).result())
        if not response.get("success"):
            raise RuntimeError(response.get("message", "Torrenter failed"))
        return response["response_body"]

    books = json.loads(args.catalog.read_text(encoding="utf-8-sig"))
    records = json.loads(args.receipts.read_text()) if args.receipts.exists() else {}
    def save():
        pending = args.receipts.with_suffix(".tmp")
        pending.write_text(json.dumps(records, indent=2))
        pending.replace(args.receipts)
    token = bind_user(user.pk)
    try:
        if sys.platform == "win32":
            # Daphne selects the Windows selector loop. Playwright needs a loop
            # that supports subprocess pipes in this standalone test process.
            asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
        with sync_playwright() as pw:
            # The caller starts headed Chrome with headless=False. Verify its native
            # window is visible before attaching, and keep its dashboard tab open.
            import win32gui
            windows = []
            win32gui.EnumWindows(lambda h, _: windows.append(h) if win32gui.IsWindowVisible(h)
                                 and not win32gui.IsIconic(h) and win32gui.GetClassName(h).startswith("Chrome_WidgetWin") else None, None)
            if not windows:
                raise RuntimeError("Open a visible development Chrome window first.")
            browser = pw.chromium.connect_over_cdp(f"http://127.0.0.1:{args.browser_port}")
            context = browser.contexts[0]
            dashboard_url = args.origin + "/agent/torrenter/workspace/"
            dashboard = next(p for p in context.pages if p.url == dashboard_url)
            assert dashboard.get_by_role("heading", level=1, name=args.username, exact=True).is_visible()
            page = context.new_page()
            try:
                for book in books:
                    name = book["name"]
                    if name in records and records[name].get("job_id"):
                        continue
                    records.setdefault(name, {"key": uuid.uuid4().hex})
                    rec = records[name]
                    if "inspection" not in rec:
                        payload = (args.catalog.parent / book["filename"]).read_bytes()
                        page.goto(args.origin + "/agent/torrenter/sources/")
                        page.locator("#torrent").set_input_files({"name":"book.torrent",
                            "mimeType":"application/x-bittorrent","buffer":torrent(book, payload, rec["key"])})
                        page.locator("#torrent").locator("xpath=ancestor::form").locator("button[type=submit]").click()
                        rec["inspection"] = page.locator("#inspection-id").inner_text(timeout=20000)
                        save()
                    meta = call("inspection", inspection_id=rec["inspection"])
                    assert meta["phase"] == "ready" and len(meta["files"]) == 1
                    assert meta["files"][0]["size"] == book["size"]
                    fields = dict(inspection_id=rec["inspection"], metadata_revision=meta["metadata_revision"],
                                  selected_file_ids=[meta["files"][0]["id"]], destination_root_id="downloads",
                                  operation_key=rec["key"], resume_on_boot=False, seed_after_completion=False)
                    receipt = call("download", **fields)
                    rec["job_id"] = receipt["job_id"]
                    rec["operation_id"] = receipt["operation_id"]
                    save()
                    print(args.username, name, "admitted", rec["job_id"], flush=True)
            finally:
                page.close()
                dashboard.bring_to_front()
            deadline = time.monotonic() + 240
            while time.monotonic() < deadline:
                visible = call("list", limit=50)["items"]
                states = {row["job_id"]:row for row in visible}
                for book in books:
                    rec = records[book["name"]]
                    job = states[rec["job_id"]]
                    if rec.get("verified"):
                        continue
                    print(args.username, book["name"], job["phase"], job["verified_bytes"], flush=True)
                    if job["phase"] in ("failed","error"):
                        raise RuntimeError(str(job.get("error") or job["phase"]))
                    if job.get("completed_at"):
                        manifest = call("manifest", job_id=rec["job_id"])
                        item, = manifest["files"]
                        assert manifest["verified"] and item["sha256"] == book["sha256"] and item["size"] == book["size"]
                        rec.update(verified=True, size=item["size"], sha256=item["sha256"],
                                   published=str(Path(manifest["output_root"]) / item["path"]))
                        save()
                if all(records[b["name"]].get("verified") for b in books):
                    dashboard.reload()
                    dashboard.wait_for_function("n => document.querySelectorAll('#rows tr button').length >= n", arg=len(books))
                    print("PASS", args.username, len(books), "verified publisher books visible in the dashboard", flush=True)
                    return
                time.sleep(4)
            raise RuntimeError("Verification deadline expired. Receipts retained for diagnosis.")
    finally:
        unbind_user(token)


if __name__ == "__main__":
    main()

