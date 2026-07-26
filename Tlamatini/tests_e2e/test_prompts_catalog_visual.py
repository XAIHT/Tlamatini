# -*- coding: utf-8 -*-
"""VISIBLE HEADED-BROWSER walk of the COMPLETE Catalog of Prompts (Angela, 2026-07-26).

WHY: Angela's frozen build showed "108 prompts" and no Documents & PDF section,
because its DB was stuck at migration 0187 and PDFer's 0188/0189/0190 never ran.
This test drives the REAL chat GUI in a HEADED Chrome on her desktop, opens the
Catalog of Prompts, and SCROLLS THROUGH EVERY SECTION so she can watch it, while
asserting against the backend's own /agent/list_prompts/ payload:

  * the catalog renders EVERY prompt the backend returns (no gaps, no truncation)
  * the header counter matches that number
  * a "Documents & PDF" section exists with the 5 PDFer prompts (#109-#113)
  * searching "pdf" finds them
  * clicking one really inserts it into the chat box

Full-desktop screenshots (taskbar clock visible) are written per section, plus a
SUMMARY.html. Never headless — Angela's standing rule.
"""
import datetime as _dt
import html as _html
import os
import sys

HARNESS = r'C:\Development\Tlamatini\.claude\skills\tlamatini-daily-chat-test\harness'
OUTDIR = r'C:\Development\Tlamatini\Temp\catalog_visual'
os.makedirs(OUTDIR, exist_ok=True)
RESULT = os.path.join(OUTDIR, 'RESULT.txt')
SUMMARY = os.path.join(OUTDIR, 'SUMMARY.html')

creds = os.path.join(HARNESS, '.creds.env')
if os.path.exists(creds):
    for _ln in open(creds, encoding='utf-8'):
        _ln = _ln.strip()
        if '=' in _ln and not _ln.startswith('#'):
            _k, _v = _ln.split('=', 1)
            os.environ.setdefault(_k.strip(), _v.strip())

sys.path.insert(0, HARNESS)
import run_test as R                              # noqa: E402
from PIL import ImageGrab                         # noqa: E402
from playwright.sync_api import sync_playwright   # noqa: E402

_BASE = os.environ.get('CATALOG_BASE_URL', '').strip()
if _BASE:
    R.C.BASE_URL = _BASE

LINES = []
SHOTS = []
CHECKS = []


def say(msg):
    print(msg, flush=True)
    LINES.append(str(msg))
    with open(RESULT, 'w', encoding='utf-8') as fh:
        fh.write("\n".join(LINES))


def check(name, passed, detail=''):
    CHECKS.append((name, bool(passed), str(detail)))
    say("  [%s] %s %s" % ("PASS" if passed else "FAIL", name,
                          ("- " + detail) if detail else ""))
    return bool(passed)


def shot(tag):
    """FULL DESKTOP screenshot (the whole screen, taskbar clock visible)."""
    path = os.path.join(OUTDIR, "%02d_%s.png" % (len(SHOTS) + 1, tag))
    try:
        img = ImageGrab.grab(all_screens=True)
    except TypeError:                             # pragma: no cover - old Pillow
        img = ImageGrab.grab()
    img.save(path)
    SHOTS.append((tag, path))
    return path


class Args:
    headless = False           # VISIBLE — never flip (Angela's standing rule)
    slowmo = 0
    user = os.environ.get('TLAMATINI_USER', 'angela')
    password = os.environ.get('TLAMATINI_PASS', '')
    judge_model = None
    not_ready_retries = 2
    not_ready_backoff = 8.0
    timeout = 180


# ── page-side helpers ────────────────────────────────────────────────────────
JS_BACKEND_TRUTH = """
async () => {
  const r = await fetch('/agent/list_prompts/', {credentials:'same-origin'});
  if (!r.ok) return {ok:false, status:r.status};
  const p = await r.json();
  return {ok:true,
          total:(p.prompts||[]).length,
          ids:(p.prompts||[]).map(x => Number(x.index)),
          categories:(p.categories||[]).map(c => c.key + '|' + c.label),
          byCat:(p.prompts||[]).reduce((a,x)=>{a[x.category||'other']=(a[x.category||'other']||0)+1;return a;},{})};
}
"""

JS_RENDERED = """
() => {
  const cards = Array.from(document.querySelectorAll('#tools-body .prompt-card'));
  const heads = Array.from(document.querySelectorAll('#tools-body .prompt-category-header'));
  return {
    cardCount: cards.length,
    ids: cards.map(c => Number((c.id||'').replace('prompt-',''))).filter(n => !isNaN(n)),
    badges: cards.map(c => (c.querySelector('.prompt-card-badge')||{}).textContent || ''),
    sections: heads.map(h => ({
      key: h.dataset.category || '',
      label: (h.querySelector('.prompt-category-label')||{}).textContent || '',
      count: Number((h.querySelector('.prompt-category-count')||{}).textContent || 0)
    })),
    counter: (document.getElementById('prompt-search-count')||{}).textContent || ''
  };
}
"""

JS_SCROLLER = """
() => {
  const body = document.getElementById('tools-body');
  let el = body;
  while (el && el !== document.body) {
    const st = getComputedStyle(el);
    if (/(auto|scroll)/.test(st.overflowY) && el.scrollHeight > el.clientHeight + 8) {
      el.dataset.tlmScroller = '1';
      return {found:true, id:el.id||el.className, h:el.scrollHeight, c:el.clientHeight};
    }
    el = el.parentElement;
  }
  if (body) body.dataset.tlmScroller = '1';
  return {found:false, id:(body&&body.id)||'', h:body?body.scrollHeight:0, c:body?body.clientHeight:0};
}
"""


def main():
    started = _dt.datetime.now()
    say("=" * 78)
    say("CATALOG OF PROMPTS — VISIBLE WALK   ·   " + started.isoformat(timespec='seconds'))
    say("base: %s   user: %s" % (R.C.BASE_URL, Args.user))
    say("=" * 78)
    if not Args.password:
        say("FATAL: no password (harness .creds.env)")
        return 2

    with sync_playwright() as p:
        h = R.Harness(Args)
        browser = h.launch(p)
        page = None
        try:
            h.login()
            h.goto_chat()
            page = h.page
            try:
                page.set_viewport_size({"width": 1600, "height": 950})
            except Exception:                      # noqa: BLE001
                pass
            page.wait_for_timeout(1200)
            shot("chat_loaded")

            # ── backend ground truth ─────────────────────────────────────────
            truth = page.evaluate(JS_BACKEND_TRUTH)
            say("")
            say("BACKEND /agent/list_prompts/ : ok=%s total=%s categories=%d"
                % (truth.get('ok'), truth.get('total'), len(truth.get('categories') or [])))
            if not truth.get('ok'):
                check("backend list_prompts reachable", False, "status=%s" % truth.get('status'))
                raise SystemExit(1)
            check("backend list_prompts reachable", True, "%d prompts" % truth['total'])

            # ── open the catalog ─────────────────────────────────────────────
            say("")
            say("Opening the Catalog of Prompts ...")
            page.click('#prompts-catalog')
            page.wait_for_selector('#tools-body .prompt-card', timeout=30000)
            page.wait_for_timeout(1500)
            shot("catalog_opened")

            rendered = page.evaluate(JS_RENDERED)
            say("RENDERED : %d cards, %d sections, counter=%r"
                % (rendered['cardCount'], len(rendered['sections']), rendered['counter']))
            say("")
            say("--- CHECKS ---")

            check("every backend prompt is rendered",
                  rendered['cardCount'] == truth['total'],
                  "rendered %d vs backend %d" % (rendered['cardCount'], truth['total']))

            missing = sorted(set(truth['ids']) - set(rendered['ids']))
            check("no prompt is missing from the catalog", not missing,
                  ("missing ids: %s" % missing) if missing else "all %d ids present"
                  % len(truth['ids']))

            check("header counter matches",
                  str(truth['total']) in (rendered['counter'] or ''),
                  "counter=%r expected %d" % (rendered['counter'], truth['total']))

            check("every backend section is rendered",
                  len(rendered['sections']) == len(truth['categories']),
                  "%d rendered vs %d backend" % (len(rendered['sections']),
                                                 len(truth['categories'])))

            sec_by_key = {s['key']: s for s in rendered['sections']}
            bad_counts = [
                "%s(ui=%s db=%s)" % (k, sec_by_key.get(k, {}).get('count'), v)
                for k, v in (truth['byCat'] or {}).items()
                if k in sec_by_key and sec_by_key[k]['count'] != v]
            check("every section badge count is correct", not bad_counts,
                  ", ".join(bad_counts) if bad_counts else "all sections agree")

            # ── THE PDFer SECTION ────────────────────────────────────────────
            docs = sec_by_key.get('documents')
            check("'Documents & PDF' section exists", docs is not None,
                  ("label=%r count=%s" % (docs['label'], docs['count'])) if docs else
                  "NOT RENDERED — this is exactly what Angela saw on the frozen build")
            pdf_ids = [i for i in (109, 110, 111, 112, 113) if i in set(rendered['ids'])]
            check("all 5 PDFer prompts (#109-#113) are present",
                  len(pdf_ids) == 5, "found %s" % pdf_ids)

            # ── SCROLL THE WHOLE CATALOG, SECTION BY SECTION ─────────────────
            say("")
            info = page.evaluate(JS_SCROLLER)
            say("Scroller: %s (scrollHeight=%s clientHeight=%s)"
                % (info.get('id'), info.get('h'), info.get('c')))
            say("Walking every section so Angela can SEE the whole catalog ...")
            for idx, sec in enumerate(rendered['sections'], start=1):
                page.evaluate(
                    """(key) => {
                        const h = document.querySelector(
                            '#tools-body .prompt-category-header[data-category="' + key + '"]');
                        if (h) {
                            h.scrollIntoView({block:'start', behavior:'instant'});
                            h.style.outline = '4px solid #22D3EE';
                            h.style.outlineOffset = '2px';
                            setTimeout(() => { h.style.outline = ''; }, 2600);
                        }
                    }""", sec['key'])
                page.wait_for_timeout(900)
                tag = "section_%02d_%s" % (idx, (sec['key'] or 'x')[:22])
                shot(tag)
                say("   %2d/%d  %-22s %-28s %d prompt(s)"
                    % (idx, len(rendered['sections']), sec['key'], sec['label'], sec['count']))

            # ── linger on Documents & PDF so she can read the five cards ─────
            if docs:
                say("")
                say("Holding on the Documents & PDF section ...")
                page.evaluate(
                    """() => {
                        const h = document.querySelector(
                            '#tools-body .prompt-category-header[data-category="documents"]');
                        if (h) h.scrollIntoView({block:'start', behavior:'instant'});
                        [109,110,111,112,113].forEach(n => {
                            const c = document.getElementById('prompt-' + n);
                            if (c) { c.style.outline = '3px solid #EC4899';
                                     c.style.outlineOffset = '2px'; }
                        });
                    }""")
                page.wait_for_timeout(2500)
                shot("documents_and_pdf_SECTION")
                titles = page.evaluate(
                    """() => [109,110,111,112,113].map(n => {
                         const c = document.getElementById('prompt-' + n);
                         return c ? ((c.querySelector('.prompt-card-badge')||{}).textContent + ' '
                              + (c.querySelector('.prompt-card-title')||{}).textContent) : null;
                       })""")
                for t in titles:
                    say("     %s" % (t or '<<MISSING>>'))
                check("the 5 PDFer cards render a title", all(titles),
                      "%d/5 titled" % len([t for t in titles if t]))

            # ── search proves they are findable ──────────────────────────────
            say("")
            say("Searching the catalog for 'pdf' ...")
            page.fill('#prompt-search-input', 'pdf')
            page.wait_for_timeout(1400)
            shot("search_pdf")
            hits = page.evaluate(
                """() => Array.from(document.querySelectorAll('#tools-body .prompt-card'))
                        .filter(c => !c.classList.contains('prompt-card-hidden'))
                        .map(c => c.id)""")
            check("searching 'pdf' finds the PDFer prompts",
                  any(i in hits for i in ('prompt-109', 'prompt-110', 'prompt-111',
                                          'prompt-112', 'prompt-113')),
                  "%d visible hit(s)" % len(hits))
            page.fill('#prompt-search-input', '')
            page.wait_for_timeout(900)

            # ── clicking a PDFer prompt really inserts it ────────────────────
            say("")
            say("Clicking prompt #111 to prove insertion ...")
            page.evaluate("""() => { const c = document.getElementById('prompt-111');
                                     if (c) c.scrollIntoView({block:'center'}); }""")
            page.wait_for_timeout(500)
            page.click('#prompt-111')
            page.wait_for_timeout(1600)
            shot("inserted_prompt_111")
            box = page.evaluate(
                """() => { const t = document.querySelector('textarea#chat-message-input')
                          || document.querySelector('#main-chat-container textarea')
                          || document.querySelector('textarea');
                          return t ? t.value.length : -1; }""")
            check("clicking a PDFer prompt inserts it into the chat box", box > 40,
                  "chat box now holds %s chars" % box)

            shot("final_state")
        finally:
            shot("desktop_final")
            try:
                if browser:
                    browser.close()
            except Exception:                      # noqa: BLE001
                pass

    passed = [c for c in CHECKS if c[1]]
    failed = [c for c in CHECKS if not c[1]]
    say("")
    say("=" * 78)
    say("RESULT: %d/%d checks passed%s"
        % (len(passed), len(CHECKS), "" if not failed else "  — FAILURES BELOW"))
    for name, ok, detail in failed:
        say("   FAILED: %s - %s" % (name, detail))
    say("screenshots: %d in %s" % (len(SHOTS), OUTDIR))
    say("elapsed: %.1fs" % (_dt.datetime.now() - started).total_seconds())
    say("=" * 78)

    rows = "".join(
        "<tr class='%s'><td>%s</td><td>%s</td><td>%s</td></tr>"
        % ("ok" if ok else "bad", "PASS" if ok else "FAIL",
           _html.escape(n), _html.escape(d))
        for n, ok, d in CHECKS)
    imgs = "".join(
        "<figure><img src='%s'><figcaption>%s</figcaption></figure>"
        % (_html.escape(os.path.basename(pth)), _html.escape(tag))
        for tag, pth in SHOTS)
    with open(SUMMARY, 'w', encoding='utf-8') as fh:
        fh.write("""<!doctype html><meta charset="utf-8">
<title>Catalog of Prompts - visible walk</title>
<style>
 body{font:15px/1.5 Segoe UI,sans-serif;background:#12141c;color:#e7e9f0;margin:24px}
 h1{margin:0 0 4px} .sub{color:#9aa0b5;margin-bottom:18px}
 table{border-collapse:collapse;width:100%%;margin-bottom:26px}
 td{border-bottom:1px solid #2a2e3e;padding:7px 10px}
 tr.ok td:first-child{color:#3ddc84;font-weight:700}
 tr.bad td:first-child{color:#ff6b6b;font-weight:700}
 figure{margin:0 0 26px} img{max-width:100%%;border:1px solid #333a4d;border-radius:8px}
 figcaption{color:#9aa0b5;padding-top:6px}
 .verdict{font-size:22px;font-weight:700;padding:12px 16px;border-radius:10px;
          background:%s;color:#0d0f16;margin-bottom:20px}
</style>
<h1>Catalog of Prompts — visible walk</h1>
<div class="sub">%s &middot; %s &middot; user %s</div>
<div class="verdict">%d / %d checks passed</div>
<table>%s</table>
%s
""" % ("#3ddc84" if not failed else "#ff6b6b",
            _html.escape(started.isoformat(timespec='seconds')),
            _html.escape(R.C.BASE_URL), _html.escape(Args.user),
            len(passed), len(CHECKS), rows, imgs))
    say("SUMMARY: %s" % SUMMARY)
    return 0 if not failed else 1


if __name__ == '__main__':
    sys.exit(main())
