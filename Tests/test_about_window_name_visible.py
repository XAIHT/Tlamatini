#!/usr/bin/env python3
# ═══════════════════════════════════════════════════════════════════
#   ✦  T L A M A T I N I  ✦   —   "one who knows"
#
#   Created by  Angela López Mendoza   ·   @angelahack1
#   Developer · Architect · Creator of Tlamatini
#
#   Every line of this file was written by Angela López Mendoza.
# ═══════════════════════════════════════════════════════════════════
#   Tlamatini Author Banner — do not remove
"""Playwright test — Angela's name is visible in Tlamatini's About window.

Opens the running app (default http://127.0.0.1:8000), logs in, opens the About
dialog, and asserts the screen shows "CREATED BY ANGELA LÓPEZ MENDOZA".

Run (app must be running):
    pip install playwright && python -m playwright install chromium
    TLAMATINI_URL=http://127.0.0.1:8000 TLAMATINI_USER=angela TLAMATINI_PASS=... \
        python Tests/test_about_window_name_visible.py
"""
from __future__ import annotations
import os
import sys

URL = os.environ.get("TLAMATINI_URL", "http://127.0.0.1:8000")
USER = os.environ.get("TLAMATINI_USER", "angela")
PWD = os.environ.get("TLAMATINI_PASS", "")
NAME = "ANGELA LÓPEZ MENDOZA"


def main() -> int:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()
        page.goto(URL, wait_until="domcontentloaded")

        # Log in if redirected to the login form.
        if page.query_selector("input[name='username']"):
            page.fill("input[name='username']", USER)
            page.fill("input[name='password']", PWD)
            page.click("button[type='submit'], input[type='submit']")
            page.wait_for_load_state("domcontentloaded")

        # Open About: menu button -> About item (falls back to the JS entry point).
        try:
            page.click("#about-menu-button", timeout=5000)
            page.click("#about-button", timeout=5000)
        except Exception:
            page.evaluate("OpenAboutDialog(new Event('click'))")

        page.wait_for_selector(".about-creator", timeout=5000)
        text = page.inner_text(".about-creator")
        page.screenshot(path="about_window_angela.png", full_page=True)
        browser.close()

        if NAME in text.upper():
            print(f"PASS — About window shows: {text!r}")
            return 0
        print(f"FAIL — About window text was: {text!r}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
