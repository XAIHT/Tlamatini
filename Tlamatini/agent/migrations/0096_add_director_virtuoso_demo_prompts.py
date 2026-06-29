# ═══════════════════════════════════════════════════════════════════
#   ✦  T L A M A T I N I  ✦   —   "one who knows"
#
#   Crafted with heart by  Angela   ·   @angelahack1
#   Developer · Architect · Creator of Tlamatini
#
#   Every line of this file was written by Angela.
# ═══════════════════════════════════════════════════════════════════
#   Tlamatini Author Banner — do not remove (releases scrub the name automatically)
"""
Seed two ADVANCED demo prompts that go beyond the basic/medium Windower &
Playwrighter showcases (0095) by conducting several desktop-UI / browser agents
together in one flow — far more *visual*: a real window is staged, clicked into
with the mouse and typed into with the keyboard before it dances around the
screen; a real browser types a query key-by-key, submits with the Enter key,
scrolls with the keyboard and captures three staged screenshots.

    55  DESKTOP DIRECTOR    Windower+Mouser+Keyboarder   advanced
                            (stage -> mouse-click-to-focus -> live keyboard typing
                             -> tile/maximize/restore/pin choreography -> list -> close)
    56  BROWSER VIRTUOSO    Playwrighter                 advanced
                            (visible per-key typing -> Enter-key submit -> article
                             -> attribute extract -> keyboard scroll -> 3 screenshots)

Placement (append, no renumber)
-------------------------------
The catalog dropdown (static/agent/js/tools_dialog.js::loadPrompts) enumerates
promptName 'prompt-1', 'prompt-2', ... and BREAKS at the first missing slot, so
the catalog must stay a contiguous, gap-free 'prompt-1..N'. Slots 1-54 are fully
occupied (0095 appended the four desktop/browser demos at 51-54). These two demos
therefore APPEND at the tail (55-56) — contiguity is preserved with no shift of
any existing prompt, so no other Prompt row's idPrompt/promptName changes.
Reverse simply deletes 55-56. (MAX_PROMPTS=100, so there is ample room.)

Like 0095 (and unlike the 0090 Reviewer/Analyzer skill demos), these drive the
wrapped chat_agent_* tools, which are NOT behind the ACPX/Skill surface — so each
prompt reminds the user to tick ONLY the **Multi-Turn** checkbox (ACPX is not
required). DESKTOP DIRECTOR is Windows-only (Win32 + PyAutoGUI). BROWSER VIRTUOSO
needs Playwright installed (`pip install playwright && playwright install`) and
uses headless=false so the browser is visible.
"""
from django.db import migrations


# ── Demo-prompt content ────────────────────────────────────────────────

WINDOWER_DIRECTOR_DEMO = (
    "Tlamatini, run the **DESKTOP DIRECTOR** demo, please &mdash; a rich, "
    "fully-visible showcase that conducts the WHOLE desktop-UI trio in one flow: "
    "the **Windower** agent stages and moves a real window, the **Mouser** agent "
    "clicks into it to place the caret, and the **Keyboarder** agent types live "
    "text into it &mdash; then Windower makes the now-text-filled window dance "
    "around the screen. All driven from chat through the wrapped "
    "**chat_agent_windower** / **chat_agent_mouser** / **chat_agent_keyboarder** "
    "tools. "
    "PRECONDITIONS: tick ONLY the **Multi-Turn** checkbox in the toolbar before "
    "sending (ACPX is NOT required). Windows-only (Windower uses the Win32 API, "
    "Mouser uses PyAutoGUI). Run each window operation as a SEPARATE "
    "chat_agent_windower call and pause briefly between them so every move is "
    "visible. "
    "\n\n"
    "Step 0: open with one HTML banner &mdash; "
    "<div style='padding:18px;border-radius:14px;background:linear-gradient(135deg,#0B1E3A 0%,#1E6FB8 38%,#22D3EE 72%,#A7F3D0 100%);color:#ffffff;font-family:Inter,Segoe UI,sans-serif;text-align:center;'>"
    "<h2 style='margin:0;letter-spacing:2px;color:#ffffff;'>&#127916; DESKTOP DIRECTOR &#127916;</h2>"
    "<div style='opacity:.92;margin-top:4px;color:#ffffff;'>Tlamatini &mdash; window, mouse and keyboard, conducted as one</div></div>. "
    "\n\n"
    "Step 1: launch Notepad so there is a window to direct &mdash; call "
    "**chat_agent_executer** with script='notepad' and non_blocking=true, then "
    "confirm the window is up with **chat_agent_window_present** "
    "(window_title='Notepad'). "
    "\n\n"
    "Step 2: STAGE the window center-screen &mdash; call **chat_agent_windower** "
    "with action='move_resize' and window_title='Notepad' and pos_x=360 and "
    "pos_y=180 and width=900 and height=560 and activate_after=true. Capture the "
    "promoted state/left/top/width/height. "
    "\n\n"
    "Step 3: focus the editing area with the MOUSE &mdash; call "
    "**chat_agent_mouser** with movement_type='click_at_window' and "
    "window_title='Notepad' and window_anchor='center' and button_click='left'. "
    "Capture the promoted fields located_via, clicked, end_posx, end_posy (this "
    "places the text caret so the next step types into the right window). "
    "\n\n"
    "Step 4: type live with the KEYBOARD &mdash; call **chat_agent_keyboarder** "
    "with input_sequence=\"'TLAMATINI', enter, 'in ixtli, in yollotl', enter, "
    "'the face, the heart -- that is wisdom', enter, enter, 'window, mouse and "
    "keyboard in concert.'\" and stride_delay=70 (the deliberate stride makes the "
    "keystrokes visible as they land). "
    "\n\n"
    "Step 5: now make the text-filled window DANCE &mdash; ONE chat_agent_windower "
    "call per move, each with window_title='Notepad' and activate_after=true, "
    "capturing the promoted state/left/top/width/height after each call: "
    "(a) action='arrange' and arrange_mode='left' (snaps to the left half); "
    "(b) action='arrange' and arrange_mode='right' (snaps to the right half); "
    "(c) action='arrange' and arrange_mode='top-right' (top-right quadrant); "
    "(d) action='maximize' (fills the screen); "
    "(e) action='restore' (back to normal size); "
    "(f) action='topmost' (pin it always-on-top). "
    "\n\n"
    "Step 6: enumerate the whole desktop with **chat_agent_windower** action='list' "
    "(leave window_title empty) and capture match_count (the number of open "
    "windows). "
    "\n\n"
    "Step 7: render an HTML table with class='exec-report-table' titled "
    "'<strong>Desktop Director Trace</strong>' and columns <em>step</em>, "
    "<em>agent</em>, <em>action</em>, <em>detail</em>, <em>state</em>, "
    "<em>left</em>, <em>top</em>, <em>width</em>, <em>height</em> &mdash; one row "
    "for the Mouser focus click (agent 'Mouser', action 'click_at_window', detail "
    "'located_via=<located_via>, at (<end_posx>,<end_posy>)'), one row for the "
    "Keyboarder type (agent 'Keyboarder', action 'type', detail '4 lines, stride "
    "70ms'), then one row for EACH of the six window moves (a)..(f) (agent "
    "'Windower') using that call's promoted fields. Keep every body cell "
    "light-background with dark text (background:#ffffff;color:#0f172a; or striped "
    "#f1f5f9). "
    "\n\n"
    "Step 8: clean up &mdash; **chat_agent_windower** action='untopmost' and "
    "window_title='Notepad' (unpin), then **chat_agent_windower** action='close' "
    "and window_title='Notepad'. If a 'Save changes?' dialog appears, dismiss it "
    "WITHOUT saving via **chat_agent_keyboarder** input_sequence=\"alt+n\". "
    "\n\n"
    "Step 9: close with one HTML banner that reuses the Step 0 gradient and prints, "
    "in big white letters, 'DESKTOP DIRECTED &#10003;', and underneath a one-line "
    "metric 'moves performed: 6 &middot; open windows seen: <match_count> &middot; "
    "final state: <state> &middot; caret click: <clicked>'. End with END-RESPONSE."
)

PLAYWRIGHTER_VIRTUOSO_DEMO = (
    "Tlamatini, run the **BROWSER VIRTUOSO** demo, please &mdash; a rich, "
    "fully-visible showcase of the **Playwrighter** agent driving a REAL browser "
    "like a touch-typist: it types a search query character-by-character (you "
    "WATCH each key land), submits with the Enter KEY (not a click), follows the "
    "result into the article, reads it, pulls a page attribute, scrolls to the "
    "bottom with the keyboard, asserts, and captures three staged screenshots "
    "&mdash; all through its wrapped **chat_agent_playwrighter** tool. "
    "PRECONDITIONS: tick ONLY the **Multi-Turn** checkbox before sending (ACPX is "
    "NOT required). Playwright must be installed (`pip install playwright && "
    "playwright install`). The demo uses headless=false so you WATCH the browser "
    "type and navigate, and hold_open_seconds=12 so it stays visible for 12 "
    "seconds before it closes. "
    "\n\n"
    "Step 0: open with one HTML banner &mdash; "
    "<div style='padding:18px;border-radius:14px;background:linear-gradient(135deg,#3D1766 0%,#D90368 38%,#0FA3B1 72%,#6EE7B7 100%);color:#ffffff;font-family:Inter,Segoe UI,sans-serif;text-align:center;'>"
    "<h2 style='margin:0;letter-spacing:2px;color:#ffffff;'>&#127908; BROWSER VIRTUOSO &#127908;</h2>"
    "<div style='opacity:.92;margin-top:4px;color:#ffffff;'>Tlamatini Playwrighter &mdash; a real browser types, submits and reads, key by key</div></div>. "
    "\n\n"
    "Step 1: call **chat_agent_playwrighter** with start_url='https://www.wikipedia.org' "
    "and headless=false and hold_open_seconds=12 and "
    "steps_json='[{\"action\":\"wait_for\",\"selector\":\"#searchInput\"},"
    "{\"action\":\"type\",\"selector\":\"#searchInput\",\"text\":\"Nahuatl\",\"delay\":140},"
    "{\"action\":\"screenshot\",\"path\":\"C:/Temp/virtuoso_1_typed.png\"},"
    "{\"action\":\"press\",\"key\":\"Enter\",\"selector\":\"#searchInput\"},"
    "{\"action\":\"wait_for\",\"selector\":\"#firstHeading\"},"
    "{\"action\":\"extract_text\",\"selector\":\"#firstHeading\",\"name\":\"article_title\"},"
    "{\"action\":\"extract_text\",\"selector\":\"#mw-content-text p\",\"name\":\"lead_paragraph\"},"
    "{\"action\":\"extract_attr\",\"selector\":\"link[rel=canonical]\",\"attr\":\"href\",\"name\":\"canonical_url\"},"
    "{\"action\":\"assert_text\",\"selector\":\"#firstHeading\",\"contains\":\"Nahuatl\"},"
    "{\"action\":\"assert_visible\",\"selector\":\"#bodyContent\"},"
    "{\"action\":\"screenshot\",\"path\":\"C:/Temp/virtuoso_2_article.png\",\"full_page\":false},"
    "{\"action\":\"press\",\"key\":\"End\"},"
    "{\"action\":\"wait\",\"ms\":800},"
    "{\"action\":\"screenshot\",\"path\":\"C:/Temp/virtuoso_3_bottom.png\",\"full_page\":true}]'. "
    "\n\n"
    "Step 2: parse the run result and capture the promoted fields status, "
    "final_url, steps_run, assert_result, plus the extracted values "
    "'article_title', 'lead_paragraph' and 'canonical_url' and the three "
    "screenshot paths. "
    "\n\n"
    "Step 3: render a STEP SCOREBOARD &mdash; a row of HTML chips of the form "
    "<span style='display:inline-block;padding:8px 16px;margin:3px;border-radius:10px;"
    "font-weight:800;background:CHIP_BG;color:#ffffff;'>LABEL</span>: a 'status: "
    "<status>' chip (CHIP_BG #16a34a when ok, else #dc2626), an 'assert: "
    "<assert_result>' chip (CHIP_BG #16a34a when pass, else #dc2626), a 'steps: "
    "<steps_run>' chip (CHIP_BG #2563EB), and a 'shots: 3' chip (CHIP_BG #0FA3B1). "
    "\n\n"
    "Step 4: render an HTML table with class='exec-report-table' titled "
    "'<strong>Browser Virtuoso Result</strong>' and two columns <em>field</em> / "
    "<em>value</em>, one row each for start_url, final_url, status, steps_run, "
    "assert_result, article_title, canonical_url, and one row per screenshot path "
    "(virtuoso_1_typed / virtuoso_2_article / virtuoso_3_bottom). Keep every body "
    "cell light-background with dark text (background:#ffffff;color:#0f172a; or "
    "striped #f1f5f9). "
    "\n\n"
    "Step 5: render the extracted lead_paragraph inside an HTML "
    "<blockquote style='border-left:6px solid #0FA3B1;padding:12px 18px;"
    "background:#ffffff;color:#0f172a;border-radius:8px;'>...lead_paragraph...</blockquote>. "
    "\n\n"
    "Step 6: close with one HTML banner that reuses the Step 0 gradient and prints, "
    "in big white letters, 'VIRTUOSO PERFORMANCE &#10003;' (if status is ok and "
    "assert_result is pass) or 'VIRTUOSO: <status>' otherwise, and underneath a "
    "one-line metric 'article: <article_title> &middot; status: <status> &middot; "
    "assert: <assert_result> &middot; steps: <steps_run> &middot; shots: 3'. End "
    "with END-RESPONSE."
)


# ── Migration ops ──────────────────────────────────────────────────────

_NEW_PROMPTS = (
    (55, WINDOWER_DIRECTOR_DEMO),
    (56, PLAYWRIGHTER_VIRTUOSO_DEMO),
)


def add_director_virtuoso_demo_prompts(apps, schema_editor):
    Prompt = apps.get_model('agent', 'Prompt')
    for prompt_id, content in _NEW_PROMPTS:
        Prompt.objects.update_or_create(
            idPrompt=prompt_id,
            defaults={'promptName': f'prompt-{prompt_id}', 'promptContent': content},
        )


def remove_director_virtuoso_demo_prompts(apps, schema_editor):
    Prompt = apps.get_model('agent', 'Prompt')
    Prompt.objects.filter(idPrompt__in=[pid for pid, _ in _NEW_PROMPTS]).delete()


class Migration(migrations.Migration):
    dependencies = [
        ('agent', '0095_add_windower_playwrighter_demo_prompts'),
    ]

    operations = [
        migrations.RunPython(
            add_director_virtuoso_demo_prompts,
            remove_director_virtuoso_demo_prompts,
        ),
    ]
