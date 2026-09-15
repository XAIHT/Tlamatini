"""VISIBLE login probe - prints exactly where the chat page is lost.

Headed Chrome. Reports URL, title and selector presence after every step, so we
stop guessing why '#chat-message-input' did not appear.
"""
import os
import sys
import time

BASE = os.environ.get("TLAMATINI_BASE_URL", "http://127.0.0.1:8000")
USER = os.environ.get("TLAMATINI_USER", "user")
PASS = os.environ.get("TLAMATINI_PASS", "changeme")


def report(page, label):
    print("\n--- %s ---" % label)
    print("   url   : %s" % page.url)
    try:
        print("   title : %s" % page.title())
    except Exception as exc:                                   # noqa: BLE001
        print("   title : <%s>" % exc)
    for sel in ("#id_username", "#id_password", "form button[type=submit]",
                "#chat-message-input", "#chat-message-submit", "#chat-log",
                "#go-to-chat", "#multi-turn-enabled"):
        print("   %-32s %s" % (sel, "PRESENT" if page.query_selector(sel) else "-"))
    sys.stdout.flush()


def main():
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False, channel="chrome",
                                    args=["--start-maximized"])
        page = browser.new_context(no_viewport=True).new_page()
        page.goto(BASE + "/", timeout=60000)
        page.wait_for_load_state("domcontentloaded", timeout=30000)
        report(page, "A. login page")

        page.fill("#id_username", USER)
        page.fill("#id_password", PASS)
        page.click("form button[type=submit]")
        page.wait_for_load_state("domcontentloaded", timeout=30000)
        time.sleep(2)
        report(page, "B. after submitting login")

        body = page.inner_text("body")[:400]
        print("\n   body head: %r" % body)

        page.goto(BASE + "/agent/agent/", timeout=60000)
        page.wait_for_load_state("domcontentloaded", timeout=30000)
        time.sleep(3)
        report(page, "C. after goto /agent/agent/")

        print("\n   Browser stays open 40s so you can look at it.")
        time.sleep(40)
        browser.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
