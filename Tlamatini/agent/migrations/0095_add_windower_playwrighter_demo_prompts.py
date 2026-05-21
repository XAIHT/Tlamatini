"""
Seed four fancy demo prompts that showcase the **Windower** (Win32 window
manager) and **Playwrighter** (scripted browser automation) agents from chat,
so the user can pick them from the Catalog of Prompts and watch each agent
*physically perform* on screen (a real window snapping/maximizing; a real
browser driving itself with headless=false).

Two prompts per agent — one basic, one medium:

    51  WINDOW SPOTLIGHT        Windower    basic   (focus+maximize+list+close)
    52  WINDOW CHOREOGRAPHY     Windower    medium  (restore->tile->move->list->close)
    53  BROWSER SPOTLIGHT       Playwrighter basic  (open example.com, extract+assert+shot)
    54  BROWSER WIZARD          Playwrighter medium (Wikipedia search: fill->click->wait->extract->assert->shot)

Placement (append, no renumber)
-------------------------------
The catalog dropdown (static/agent/js/tools_dialog.js::loadPrompts) enumerates
promptName 'prompt-1', 'prompt-2', ... and BREAKS at the first missing slot, so
the catalog must stay a contiguous, gap-free 'prompt-1..N'. Slots 1-50 are
fully occupied (0090 shifted the Multi-Turn/ACPX block down so the last demo is
the Gemini-pinned ACPX showcase at 50). These four demos therefore APPEND at the
tail (51-54) — contiguity is preserved with no shift of any existing prompt, so
no other Prompt row's idPrompt/promptName changes. Reverse simply deletes 51-54.

Unlike the 0090 Reviewer/Analyzer skill demos, these drive the **wrapped
chat_agent_windower / chat_agent_playwrighter tools**, which are NOT behind the
ACPX/Skill surface — so each prompt reminds the user to tick ONLY the
**Multi-Turn** checkbox (ACPX is not required). Windower is Windows-only (Win32);
Playwrighter needs Playwright installed (`pip install playwright && playwright
install`) and uses headless=false so the browser is visible.
"""
from django.db import migrations


# ── Demo-prompt content ────────────────────────────────────────────────

WINDOWER_BASIC_DEMO = (
    "Tlamatini, run the **WINDOW SPOTLIGHT** demo, please &mdash; a short, "
    "fully-visible showcase of the **Windower** agent (the desktop window "
    "manager) driven from chat through its wrapped **chat_agent_windower** tool. "
    "PRECONDITIONS: tick ONLY the **Multi-Turn** checkbox in the toolbar before "
    "sending (ACPX is NOT required &mdash; Windower is a standard Multi-Turn "
    "tool). This demo is Windows-only (Windower uses the Win32 API). "
    "\n\n"
    "Step 0: open with one HTML banner &mdash; "
    "<div style='padding:18px;border-radius:14px;background:linear-gradient(135deg,#0F2C4D 0%,#1E6FB8 50%,#4FC3F7 100%);color:#ffffff;font-family:Inter,Segoe UI,sans-serif;text-align:center;'>"
    "<h2 style='margin:0;letter-spacing:2px;color:#ffffff;'>&#129003; WINDOW SPOTLIGHT &#129003;</h2>"
    "<div style='opacity:.92;margin-top:4px;color:#ffffff;'>Tlamatini Windower &mdash; bring a real window to the front and watch it grow</div></div>. "
    "\n\n"
    "Step 1: launch Notepad so there is a window to manage &mdash; call "
    "**chat_agent_executer** with script='notepad' and non_blocking=true, then "
    "confirm the window is up with **chat_agent_window_present** (window_title='Notepad'). "
    "\n\n"
    "Step 2: bring it to the foreground and maximize it so the user SEES it move "
    "&mdash; call **chat_agent_windower** with action='maximize' and "
    "window_title='Notepad' and activate_after=true. "
    "\n\n"
    "Step 3: read back the live window with **chat_agent_windower** action='list' "
    "and window_title='Notepad'. From the promoted result fields capture: matched, "
    "match_count, state, left, top, width, height. "
    "\n\n"
    "Step 4: render an HTML table with class='exec-report-table' titled "
    "'<strong>Window Operation</strong>' and two columns <em>field</em> / "
    "<em>value</em>, one row each for action, window_title, matched, state, left, "
    "top, width, height (the promoted INI_SECTION_WINDOWER fields). Keep every body "
    "cell light-background with dark text (background:#ffffff;color:#0f172a; or "
    "striped #f1f5f9). "
    "\n\n"
    "Step 5: clean up &mdash; close the window with **chat_agent_windower** "
    "action='close' and window_title='Notepad'. If a 'Save changes?' dialog appears, "
    "dismiss it WITHOUT saving via **chat_agent_keyboarder** input_sequence=\"alt+n\". "
    "\n\n"
    "Step 6: close with one HTML banner that reuses the Step 0 gradient and prints, "
    "in big white letters, 'WINDOW MANAGED &#10003;', and underneath a one-line "
    "metric 'state: <state> &middot; size: <width>x<height> &middot; at "
    "(<left>,<top>)'. End with END-RESPONSE."
)

WINDOWER_MEDIUM_DEMO = (
    "Tlamatini, run the **WINDOW CHOREOGRAPHY** demo, please &mdash; a richer, "
    "fully-visible showcase that makes a single window dance around the screen "
    "using the **Windower** agent's tile / move / list verbs through its wrapped "
    "**chat_agent_windower** tool. "
    "PRECONDITIONS: tick ONLY the **Multi-Turn** checkbox before sending (ACPX is "
    "NOT required). Windows-only (Win32). Run each window operation as a SEPARATE "
    "chat_agent_windower call and pause briefly between them so the movement is "
    "visible. "
    "\n\n"
    "Step 0: open with one HTML banner &mdash; "
    "<div style='padding:18px;border-radius:14px;background:linear-gradient(135deg,#0F2C4D 0%,#1E6FB8 50%,#4FC3F7 100%);color:#ffffff;font-family:Inter,Segoe UI,sans-serif;text-align:center;'>"
    "<h2 style='margin:0;letter-spacing:2px;color:#ffffff;'>&#129003; WINDOW CHOREOGRAPHY &#129003;</h2>"
    "<div style='opacity:.92;margin-top:4px;color:#ffffff;'>Tlamatini Windower &mdash; tile, snap and slide a live window</div></div>. "
    "\n\n"
    "Step 1: launch Notepad with **chat_agent_executer** script='notepad' and "
    "non_blocking=true, then confirm it with **chat_agent_window_present** "
    "(window_title='Notepad'). "
    "\n\n"
    "Step 2: perform this choreography, ONE chat_agent_windower call per move, each "
    "with window_title='Notepad' and activate_after=true, capturing the promoted "
    "state/left/top/width/height after each call: "
    "(a) action='restore'; "
    "(b) action='arrange' and arrange_mode='left' (snaps to the left half); "
    "(c) action='arrange' and arrange_mode='right' (snaps to the right half); "
    "(d) action='arrange' and arrange_mode='top-left' (top-left quadrant); "
    "(e) action='move_resize' and pos_x=220 and pos_y=160 and width=900 and "
    "height=600 (an explicit rectangle). "
    "\n\n"
    "Step 3: enumerate the whole desktop with **chat_agent_windower** action='list' "
    "(leave window_title empty) and capture match_count (the number of open windows). "
    "\n\n"
    "Step 4: render an HTML table with class='exec-report-table' titled "
    "'<strong>Window Choreography Trace</strong>' and columns <em>step</em>, "
    "<em>action</em>, <em>mode / geometry</em>, <em>state</em>, <em>left</em>, "
    "<em>top</em>, <em>width</em>, <em>height</em> &mdash; one row for each of the "
    "five moves (a)..(e) using that call's promoted fields. Keep every body cell "
    "light-background with dark text (background:#ffffff;color:#0f172a; or striped "
    "#f1f5f9). "
    "\n\n"
    "Step 5: clean up &mdash; **chat_agent_windower** action='close' and "
    "window_title='Notepad'; if a 'Save changes?' dialog appears, dismiss it WITHOUT "
    "saving via **chat_agent_keyboarder** input_sequence=\"alt+n\". "
    "\n\n"
    "Step 6: close with one HTML banner that reuses the Step 0 gradient and prints, "
    "in big white letters, 'CHOREOGRAPHY COMPLETE &#10003;', and underneath a "
    "one-line metric 'moves performed: 5 &middot; open windows seen: <match_count> "
    "&middot; final size: <width>x<height>'. End with END-RESPONSE."
)

PLAYWRIGHTER_BASIC_DEMO = (
    "Tlamatini, run the **BROWSER SPOTLIGHT** demo, please &mdash; a short, "
    "fully-visible showcase of the **Playwrighter** agent driving a REAL browser "
    "through its wrapped **chat_agent_playwrighter** tool. "
    "PRECONDITIONS: tick ONLY the **Multi-Turn** checkbox before sending (ACPX is "
    "NOT required). Playwright must be installed (`pip install playwright && "
    "playwright install`). The demo uses headless=false so you WATCH the browser "
    "open and drive itself, and hold_open_seconds=10 so it stays visible for 10 "
    "seconds before it closes. "
    "\n\n"
    "Step 0: open with one HTML banner &mdash; "
    "<div style='padding:18px;border-radius:14px;background:linear-gradient(135deg,#3D1766 0%,#D90368 50%,#0FA3B1 100%);color:#ffffff;font-family:Inter,Segoe UI,sans-serif;text-align:center;'>"
    "<h2 style='margin:0;letter-spacing:2px;color:#ffffff;'>&#127760; BROWSER SPOTLIGHT &#127760;</h2>"
    "<div style='opacity:.92;margin-top:4px;color:#ffffff;'>Tlamatini Playwrighter &mdash; watch a real browser read a page for you</div></div>. "
    "\n\n"
    "Step 1: call **chat_agent_playwrighter** with start_url='https://example.com' "
    "and headless=false and hold_open_seconds=10 and steps_json='[{\"action\":\"wait_for\",\"selector\":\"h1\"},"
    "{\"action\":\"extract_text\",\"selector\":\"h1\",\"name\":\"heading\"},"
    "{\"action\":\"extract_text\",\"selector\":\"p\",\"name\":\"intro\"},"
    "{\"action\":\"assert_visible\",\"selector\":\"a\"},"
    "{\"action\":\"screenshot\",\"path\":\"C:/Temp/example_spotlight.png\",\"full_page\":true}]'. "
    "\n\n"
    "Step 2: parse the run result and capture the promoted fields status, final_url, "
    "steps_run, assert_result, plus the extracted values 'heading' and 'intro' and "
    "the screenshot path. "
    "\n\n"
    "Step 3: render an HTML table with class='exec-report-table' titled "
    "'<strong>Browser Run</strong>' and two columns <em>field</em> / <em>value</em>, "
    "one row each for start_url, final_url, status, steps_run, assert_result, "
    "heading, screenshot path. Keep every body cell light-background with dark text "
    "(background:#ffffff;color:#0f172a; or striped #f1f5f9). "
    "\n\n"
    "Step 4: render the extracted intro paragraph inside an HTML "
    "<blockquote style='border-left:6px solid #D90368;padding:12px 18px;"
    "background:#ffffff;color:#0f172a;border-radius:8px;'>...intro...</blockquote>. "
    "\n\n"
    "Step 5: close with one HTML banner that reuses the Step 0 gradient and prints, "
    "in big white letters, 'PAGE CAPTURED &#10003;' (if status is ok and "
    "assert_result is pass) or 'BROWSER RUN: <status>' otherwise, and underneath a "
    "one-line metric 'status: <status> &middot; assert: <assert_result> &middot; "
    "steps: <steps_run> &middot; shot: C:/Temp/example_spotlight.png'. End with "
    "END-RESPONSE."
)

PLAYWRIGHTER_MEDIUM_DEMO = (
    "Tlamatini, run the **BROWSER WIZARD** demo, please &mdash; a richer, "
    "fully-visible showcase of the **Playwrighter** agent performing a multi-step "
    "interactive search on Wikipedia (type a query, click search, wait for the "
    "article, read it, assert and screenshot) through its wrapped "
    "**chat_agent_playwrighter** tool. "
    "PRECONDITIONS: tick ONLY the **Multi-Turn** checkbox before sending (ACPX is "
    "NOT required). Playwright must be installed (`pip install playwright && "
    "playwright install`). The demo uses headless=false so you WATCH the browser "
    "fill the form, click and navigate, and hold_open_seconds=10 so it stays "
    "visible for 10 seconds before it closes. "
    "\n\n"
    "Step 0: open with one HTML banner &mdash; "
    "<div style='padding:18px;border-radius:14px;background:linear-gradient(135deg,#3D1766 0%,#D90368 50%,#0FA3B1 100%);color:#ffffff;font-family:Inter,Segoe UI,sans-serif;text-align:center;'>"
    "<h2 style='margin:0;letter-spacing:2px;color:#ffffff;'>&#127760; BROWSER WIZARD &#127760;</h2>"
    "<div style='opacity:.92;margin-top:4px;color:#ffffff;'>Tlamatini Playwrighter &mdash; a real browser searches Wikipedia step by step</div></div>. "
    "\n\n"
    "Step 1: call **chat_agent_playwrighter** with start_url='https://www.wikipedia.org' "
    "and headless=false and hold_open_seconds=10 and steps_json='[{\"action\":\"fill\",\"selector\":\"#searchInput\",\"value\":\"Nahuatl\"},"
    "{\"action\":\"click\",\"selector\":\"button[type=submit]\"},"
    "{\"action\":\"wait_for\",\"selector\":\"#firstHeading\"},"
    "{\"action\":\"extract_text\",\"selector\":\"#firstHeading\",\"name\":\"article_title\"},"
    "{\"action\":\"extract_text\",\"selector\":\"#mw-content-text p\",\"name\":\"first_paragraph\"},"
    "{\"action\":\"assert_text\",\"selector\":\"#firstHeading\",\"contains\":\"Nahuatl\"},"
    "{\"action\":\"screenshot\",\"path\":\"C:/Temp/wikipedia_wizard.png\",\"full_page\":false}]'. "
    "\n\n"
    "Step 2: parse the run result and capture the promoted fields status, final_url, "
    "steps_run, assert_result, plus the extracted values 'article_title' and "
    "'first_paragraph' and the screenshot path. "
    "\n\n"
    "Step 3: render a STEP SCOREBOARD &mdash; a row of three HTML chips of the form "
    "<span style='display:inline-block;padding:8px 16px;margin:3px;border-radius:10px;"
    "font-weight:800;background:CHIP_BG;color:#ffffff;'>LABEL</span>: a 'status: "
    "<status>' chip (CHIP_BG #16a34a when ok, else #dc2626), an 'assert: "
    "<assert_result>' chip (CHIP_BG #16a34a when pass, else #dc2626), and a 'steps: "
    "<steps_run>' chip (CHIP_BG #2563EB). "
    "\n\n"
    "Step 4: render an HTML table with class='exec-report-table' titled "
    "'<strong>Browser Wizard Result</strong>' and two columns <em>field</em> / "
    "<em>value</em>, one row each for start_url, final_url, status, steps_run, "
    "assert_result, article_title, screenshot path. Keep every body cell "
    "light-background with dark text (background:#ffffff;color:#0f172a; or striped "
    "#f1f5f9). "
    "\n\n"
    "Step 5: render the extracted first_paragraph inside an HTML "
    "<blockquote style='border-left:6px solid #0FA3B1;padding:12px 18px;"
    "background:#ffffff;color:#0f172a;border-radius:8px;'>...first_paragraph...</blockquote>. "
    "\n\n"
    "Step 6: close with one HTML banner that reuses the Step 0 gradient and prints, "
    "in big white letters, 'SEARCH COMPLETE &#10003;' (if status is ok and "
    "assert_result is pass) or 'WIZARD: <status>' otherwise, and underneath a "
    "one-line metric 'article: <article_title> &middot; status: <status> &middot; "
    "assert: <assert_result> &middot; steps: <steps_run> &middot; shot: "
    "C:/Temp/wikipedia_wizard.png'. End with END-RESPONSE."
)


# ── Migration ops ──────────────────────────────────────────────────────

_NEW_PROMPTS = (
    (51, WINDOWER_BASIC_DEMO),
    (52, WINDOWER_MEDIUM_DEMO),
    (53, PLAYWRIGHTER_BASIC_DEMO),
    (54, PLAYWRIGHTER_MEDIUM_DEMO),
)


def add_windower_playwrighter_demo_prompts(apps, schema_editor):
    Prompt = apps.get_model('agent', 'Prompt')
    for prompt_id, content in _NEW_PROMPTS:
        Prompt.objects.update_or_create(
            idPrompt=prompt_id,
            defaults={'promptName': f'prompt-{prompt_id}', 'promptContent': content},
        )


def remove_windower_playwrighter_demo_prompts(apps, schema_editor):
    Prompt = apps.get_model('agent', 'Prompt')
    Prompt.objects.filter(idPrompt__in=[pid for pid, _ in _NEW_PROMPTS]).delete()


class Migration(migrations.Migration):
    dependencies = [
        ('agent', '0094_add_chat_agent_windower_tool'),
    ]

    operations = [
        migrations.RunPython(
            add_windower_playwrighter_demo_prompts,
            remove_windower_playwrighter_demo_prompts,
        ),
    ]
