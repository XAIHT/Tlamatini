# ═══════════════════════════════════════════════════════════════════
#   ✦  T L A M A T I N I  ✦   —   "one who knows"
#
#   Created by  Angela López Mendoza   ·   @angelahack1
#   Developer · Architect · Creator of Tlamatini
#
#   Every line of this file was written by Angela López Mendoza.
# ═══════════════════════════════════════════════════════════════════
#   Tlamatini Author Banner — do not remove (releases scrub the name automatically)
r"""
VISIBLE end-to-end test of the NEW **Prompt Designer** page.

ANGELA'S RULE: there is no --headless flag and there never will be. This runs a
HEADED real Chrome on her actual desktop, and every screenshot is taken by
Tlamatini's own **Shoter** agent — never PIL.ImageGrab.

WHAT IT PROVES (filesystem/DOM truth, never prose):
  1. The chat navbar carries a **Designer** menu whose only entry is **Prompts**.
  2. That entry opens **prompt_designer.html** in a new tab.
  3. The page paints the approved design: brand "Tlamatini (Prompt Designer)",
     a "Assets:" panel on the left, a "Prompt Canvas:" panel on the right, and
     the five toolbar buttons Validate / Start / Stop / Pause / Clear.
  4. EVERY control answers with the themed popup carrying EXACTLY
     "Working on it for further sprints" — the five toolbar buttons, the three
     File-menu entries, the Assets panel and the Prompt Canvas.
     A control that stays silent is a FAILURE, not a pass.

USAGE (from a VISIBLE foreground window):
    python prompt_designer_visible.py
    set TLAMATINI_BASE_URL=http://127.0.0.1:8000   (default)
    set TLAMATINI_USER / TLAMATINI_PASS            (default user / changeme)
"""
from __future__ import annotations

import os
import sys
import time

from playwright.sync_api import sync_playwright

import shoter_shot

BASE = os.environ.get("TLAMATINI_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
USER = os.environ.get("TLAMATINI_USER", "user")
PASS = os.environ.get("TLAMATINI_PASS", "changeme")

NOTICE = "Working on it for further sprints"
SHOTS = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                     "reports", "prompt_designer")

results: list[tuple[str, bool, str]] = []


def check(label: str, ok: bool, detail: str = "") -> bool:
    results.append((label, bool(ok), detail))
    print(("   [PASS] " if ok else "   [FAIL] ") + label
          + (("  ->  " + detail) if detail else ""))
    return bool(ok)


def shot(name: str) -> None:
    path = shoter_shot.take_shot(SHOTS, name, runtime_base=SHOTS)
    print("   photo: %s" % (path or "!! Shoter left no photo"))


def dialog_text(page) -> str:
    """Read the themed pdAlert popup that is currently open."""
    node = page.locator("#confirmation-secondary-dialog-legend")
    if node.count() == 0:
        return ""
    try:
        if not node.is_visible():
            return ""
    except Exception:
        return ""
    return (node.inner_text() or "").strip()


def dismiss_dialog(page) -> None:
    """Press the popup's own OK button — the dismissal the policy expects."""
    ok = page.locator(".ui-dialog-buttonpane button", has_text="OK")
    if ok.count():
        ok.first.click()
        page.wait_for_timeout(250)


def expect_notice(page, label: str, clicker) -> None:
    """Activate a control and assert it answers with the sprint notice."""
    try:
        clicker()
    except Exception as exc:                       # noqa: BLE001
        check("%s -> notice" % label, False, "click failed: %s" % str(exc)[:90])
        return
    page.wait_for_timeout(450)
    text = dialog_text(page)
    check("%s -> notice" % label, text == NOTICE,
          "got %r" % (text or "<no dialog>"))
    dismiss_dialog(page)


def main() -> int:
    if "--headless" in sys.argv:
        print("!! HEADLESS IS FORBIDDEN. This test only runs visible.")
        return 2

    os.makedirs(SHOTS, exist_ok=True)
    print("=" * 70)
    print(" PROMPT DESIGNER - VISIBLE TEST   target: %s" % BASE)
    print("=" * 70)

    with sync_playwright() as pw:
        try:
            browser = pw.chromium.launch(headless=False, channel="chrome",
                                         args=["--start-maximized"])
        except Exception:
            browser = pw.chromium.launch(headless=False,
                                         args=["--start-maximized"])
        context = browser.new_context(no_viewport=True)
        page = context.new_page()

        # ---- 1. login ------------------------------------------------
        page.goto(BASE + "/", timeout=30_000)
        page.fill("#id_username", USER)
        page.fill("#id_password", PASS)
        page.click("form button[type=submit]")
        page.wait_for_load_state("networkidle", timeout=30_000)
        page.goto(BASE + "/agent/agent/", timeout=30_000)
        page.wait_for_selector("#navbar-container", timeout=30_000)
        check("logged in and chat page reached", True)

        # ---- 2. the Designer menu ------------------------------------
        menu = page.locator("#designer-menu-button")
        check("navbar has a Designer menu", menu.count() == 1)
        check("Designer menu is labelled 'Designer'",
              (menu.inner_text() or "").strip() == "Designer",
              (menu.inner_text() or "").strip())
        menu.click()
        page.wait_for_timeout(400)
        entry = page.locator("#prompt-designer")
        check("Designer menu has exactly one entry", entry.count() == 1)
        check("that entry is named 'Prompts'",
              (entry.inner_text() or "").strip() == "Prompts",
              (entry.inner_text() or "").strip())
        shot("01_designer_menu_open.png")

        # ---- 3. open it ----------------------------------------------
        with context.expect_page() as popup:
            entry.click()
        pd = popup.value
        pd.wait_for_load_state("domcontentloaded", timeout=30_000)
        pd.bring_to_front()
        pd.wait_for_selector("#designer-container", timeout=30_000)
        pd.wait_for_timeout(700)
        check("Prompts opened the Prompt Designer page",
              "/prompt_designer/" in pd.url, pd.url)

        # ---- 4. the approved design ----------------------------------
        brand = (pd.locator(".navbar-brand").inner_text() or "").strip()
        check("brand reads 'Tlamatini (Prompt Designer)'",
              brand == "Tlamatini (Prompt Designer)", brand)

        assets = (pd.locator("#assets-header-title").inner_text() or "").strip()
        check("left panel header reads 'Assets:'", assets == "Assets:", assets)

        canvas = (pd.locator("#promptcanvas-header-title").inner_text() or "").strip()
        check("right panel header reads 'Prompt Canvas:'",
              canvas == "Prompt Canvas:", canvas)

        check("File menu is present", pd.locator("#pd-file-dropdown").count() == 1)

        expected_buttons = ["Validate", "Start", "Stop", "Pause", "Clear"]
        painted = [(t or "").strip() for t in
                   pd.locator("#promptcanvas-controls .pd-control-btn").all_inner_texts()]
        check("toolbar paints Validate / Start / Stop / Pause / Clear in order",
              painted == expected_buttons, str(painted))

        check("the Assets panel is empty, as designed",
              pd.locator("#assets-list").inner_html().strip() == "")

        shot("02_prompt_designer_page.png")

        # ---- 5. every toolbar button answers -------------------------
        print("\n-- toolbar buttons --")
        for bid, label in [("pd-btn-validate", "Validate"),
                           ("pd-btn-start", "Start"),
                           ("pd-btn-stop", "Stop"),
                           ("pd-btn-pause", "Pause"),
                           ("pd-btn-clear", "Clear")]:
            expect_notice(pd, "toolbar %s" % label,
                          lambda i=bid: pd.locator("#" + i).click())

        # one photo WITH the popup on screen, so the notice is visible
        pd.locator("#pd-btn-start").click()
        pd.wait_for_timeout(500)
        shot("03_sprint_notice_dialog.png")
        dismiss_dialog(pd)

        # ---- 6. every File-menu entry answers ------------------------
        print("\n-- File menu --")
        for eid, label in [("pd-file-open-button", "Open"),
                           ("pd-file-save-as-button", "Save as"),
                           ("pd-file-close-button", "Close")]:
            def click_entry(i=eid):
                pd.locator("#pd-file-dropdown").click()
                pd.wait_for_timeout(300)
                pd.locator("#" + i).click()
            expect_notice(pd, "File > %s" % label, click_entry)

        # ---- 7. the two surfaces answer ------------------------------
        print("\n-- surfaces --")
        expect_notice(pd, "Prompt Canvas surface",
                      lambda: pd.locator("#subpromptcanvas-container").click(
                          position={"x": 400, "y": 300}))
        expect_notice(pd, "Assets panel surface",
                      lambda: pd.locator("#main-assets-container").click(
                          position={"x": 80, "y": 300}))

        shot("04_after_all_controls.png")
        time.sleep(2)
        context.close()
        browser.close()

    # ---- verdict -----------------------------------------------------
    passed = sum(1 for _, ok, _ in results if ok)
    total = len(results)
    print("\n" + "=" * 70)
    for label, ok, detail in results:
        if not ok:
            print(" FAILED: %s  (%s)" % (label, detail))
    print(" PROMPT DESIGNER VISIBLE TEST: %d/%d checks passed" % (passed, total))
    print("=" * 70)
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
