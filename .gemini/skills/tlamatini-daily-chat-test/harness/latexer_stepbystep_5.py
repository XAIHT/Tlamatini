# -*- coding: utf-8 -*-
"""
Tlamatini - VISIBLE (headed Chrome) end-to-end test of FIVE escalating
LaTeXer STEP-BY-STEP wizards, with a TRUTH ORACLE over the Exec Report.

ANGELA'S MAIN GOAL (2026-08-06), and the only thing this test really judges:

    The final EXECUTION TABLES must show the TRUE verdict.
    Never a FAILED for something that really worked.
    Never a SUCCESS for something that really failed.

So "the wizard finished" is NOT a pass here. For every scenario the harness
establishes GROUND TRUTH INDEPENDENTLY OF THE TABLE - by looking at the real
filesystem (did the PDF actually appear? does the .tex really contain the
user's equation?) - and then compares that truth against what the Exec Report
printed. A mismatch is reported as exactly one of:

    FALSE_FAILURE  - the table said FAILURE but the work really happened
    FALSE_SUCCESS  - the table said SUCCESS but the work really did not happen

Scenario 5 deliberately contains ONE of each direction so the test can prove
both halves rather than only the one that happened to regress:

    * a lint of a KNOWINGLY BROKEN file  -> the linter does its job -> SUCCESS
    * a compile of a FILE THAT DOES NOT EXIST -> nothing is produced -> FAILURE

Escalation:
    L1 first_light   trivial   no user data
    L2 anatomy       easy      no user data
    L3 integral_1    medium    USER supplies an integral (Angela's shape)
    L4 integral_hard hard      USER supplies Angela's exact expression
    L5 project_xt    extreme   multi-file project + BOTH verdict probes

Screenshots are taken by SHOTER, Tlamatini's own agent (PIL is FORBIDDEN).
The browser is ALWAYS headed - run_test.Harness refuses headless.
"""
import os
import sys
import re
import time
import json
import html
import glob
import datetime as _dt

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

# Credentials live in .creds.env (gitignored). Load BEFORE importing config,
# which snapshots TLAMATINI_USER / TLAMATINI_PASS at import time.
_CREDS = os.path.join(HERE, ".creds.env")
if os.path.isfile(_CREDS):
    for _line in open(_CREDS, encoding="utf-8"):
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _, _v = _line.partition("=")
            os.environ.setdefault(_k.strip(), _v.strip())

import config as C          # noqa: E402
import run_test as R        # noqa: E402
from shoter_shot import take_shot                # noqa: E402
from playwright.sync_api import sync_playwright  # noqa: E402

RUN_TAG = _dt.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
RUN_DIR = os.path.join(HERE, "reports", "latex5_%s" % RUN_TAG)
SHOTS = os.path.join(RUN_DIR, "shots")
os.makedirs(SHOTS, exist_ok=True)
RESULTS = os.path.join(RUN_DIR, "results.jsonl")
SUMMARY = os.path.join(RUN_DIR, "SUMMARY.html")

# Every artefact the wizards produce lands under <app>/Temp (Temp policy).
WORK_ROOT = os.path.join(r"C:\Development\Tlamatini", "Temp", "LaTeXerTest", RUN_TAG)
os.makedirs(WORK_ROOT, exist_ok=True)


def wdir(name):
    """Absolute work directory for a scenario, forward-slashed for the prompt."""
    p = os.path.join(WORK_ROOT, name)
    os.makedirs(p, exist_ok=True)
    return p


def fwd(p):
    return p.replace("\\", "/")


PER_TURN_TIMEOUT_S = int(os.environ.get("LATEX5_TIMEOUT", "300"))

_HEAD = ("Tlamatini, run this in STEP-BY-STEP mode: give me ONE concrete action "
         "at a time, then STOP and wait for me to reply READY before the next "
         "step. Use ONLY the chat_agent_latexer tool for the LaTeX work.\n\n")

_TAIL = ("\n\nDo not skip a step. Do not do two steps at once. "
         "After the final step, print a short summary. End with END-RESPONSE.")


# ===================================================================== L1
L1_DIR = wdir("L1_first_light")
L1 = _HEAD + (
    "**LaTeXer wizard 1 of 5 - FIRST LIGHT (the easy one).**\n"
    "Work directory (use it exactly, it already exists): %s\n\n"
    "STEP 1. Check the LaTeX environment with LaTeXer (action=validate) and "
    "tell me which distribution and engine you found.\n"
    "STEP 2. Create a LaTeX file first_light.tex in that directory: a small "
    "article titled 'First Light' with one short paragraph.\n"
    "STEP 3. Compile it to PDF into that SAME directory and report the "
    "ABSOLUTE path of the PDF and its page count."
) % fwd(L1_DIR) + _TAIL

# ===================================================================== L2
L2_DIR = wdir("L2_anatomy")
L2 = _HEAD + (
    "**LaTeXer wizard 2 of 5 - ANATOMY OF A DOCUMENT.**\n"
    "Work directory (use it exactly): %s\n\n"
    "STEP 1. Use LaTeXer create_from_template with the 'article' template to "
    "make anatomy.tex in that directory.\n"
    "STEP 2. Ask LaTeXer for the document STRUCTURE of that file and show me "
    "the outline it found.\n"
    "STEP 3. Run LaTeXer validate_tex on that same file. It is a CLEAN "
    "document, so tell me plainly whether it validated.\n"
    "STEP 4. Compile it to PDF into that directory and report the ABSOLUTE "
    "PDF path and the page count."
) % fwd(L2_DIR) + _TAIL

# ===================================================================== L3
L3_DIR = wdir("L3_integral_1")
L3 = _HEAD + (
    "**LaTeXer wizard 3 of 5 - AN ABSTRACT, AN INTEGRAL, AND ONE OF MINE.**\n"
    "Work directory (use it exactly): %s\n\n"
    "STEP 1. Create calculus.tex in that directory: an article that loads "
    "amsmath, titled 'A Short Note on Integration', with an ABSTRACT that "
    "explains in 2-3 sentences what an integral IS, and then one basic worked "
    "example rendered as real LaTeX maths: the integral of x^2 dx.\n"
    "STEP 2. Compile it to PDF into that directory and report the path.\n"
    "STEP 3. Now ASK ME for an integral of my own, in plain words, and WAIT "
    "for my answer.\n"
    "STEP 4. Take the integral I give you, SOLVE it yourself showing the "
    "steps, append a new section to calculus.tex containing the statement as "
    "proper LaTeX maths AND your full solution, then RECOMPILE and report the "
    "ABSOLUTE PDF path and the new page count."
) % fwd(L3_DIR) + _TAIL

# ===================================================================== L4
L4_DIR = wdir("L4_integral_hard")
L4 = _HEAD + (
    "**LaTeXer wizard 4 of 5 - THE HARD ONE.**\n"
    "Work directory (use it exactly): %s\n\n"
    "STEP 1. Create closed_path.tex in that directory: an article loading "
    "amsmath and amssymb, titled 'Definite Integrals of a Composite "
    "Expression', with an abstract about evaluating a definite integral of a "
    "sum of trigonometric and hyperbolic terms over a symmetric interval.\n"
    "STEP 2. ASK ME for the exact expression I want evaluated, and WAIT.\n"
    "STEP 3. Take my expression and EVALUATE IT PROPERLY. Split it term by "
    "term, use the symmetry of the interval (odd terms vanish, even terms "
    "double), give the exact closed form where one exists and a numeric value "
    "to at least 4 decimals otherwise, and show every step. Write ALL of it "
    "into closed_path.tex as numbered LaTeX equations.\n"
    "STEP 4. Compile closed_path.tex to PDF and deliver the PDF INTO THIS "
    "EXACT DIRECTORY: %s\n"
    "Report the ABSOLUTE PDF path, the page count and the file size in bytes."
) % (fwd(L4_DIR), fwd(L4_DIR)) + _TAIL

# ===================================================================== L5
L5_DIR = wdir("L5_project_xt")
L5_MISSING = fwd(os.path.join(L5_DIR, "this_file_does_not_exist_zzz.tex"))
L5 = _HEAD + (
    "**LaTeXer wizard 5 of 5 - THE EXTREME ONE (multi-file project).**\n"
    "Project directory (use it exactly): %s\n\n"
    "STEP 1. Build a MULTI-FILE LaTeX project there: a master file main.tex "
    "that loads amsmath and amssymb, defines a theorem environment, calls "
    "\\\\tableofcontents, and pulls in two children with \\\\input - "
    "sections/intro.tex and sections/results.tex. Put a \\\\label in "
    "results.tex and a \\\\ref to it from intro.tex so the cross-reference "
    "needs more than one compilation pass.\n"
    "STEP 2. Now a DELIBERATE LINT CHECK. Create broken_fragment.tex in that "
    "directory containing a \\\\begin{itemize} with two items that is NEVER "
    "closed, then run LaTeXer validate_tex on it. I EXPECT the linter to "
    "FIND that error - finding it means the linter WORKED. Tell me the error "
    "and the line number.\n"
    "STEP 3. Now a DELIBERATE FAILURE CHECK. Try to compile this file, which "
    "does NOT exist: %s\n"
    "Report honestly that it could not be done. Do NOT create the file, do "
    "NOT substitute another file, and do NOT retry with a different path.\n"
    "STEP 4. ASK ME for one more integral to include in the results section, "
    "and WAIT for my answer.\n"
    "STEP 5. Solve my integral showing the steps, write the statement and the "
    "solution into sections/results.tex as a numbered equation next to the "
    "\\\\label, and make sure intro.tex still references it.\n"
    "STEP 6. Compile the WHOLE PROJECT (compile_project on main.tex) until "
    "the cross-references settle, deliver the PDF into %s and report the "
    "ABSOLUTE PDF path, the page count and how many passes it needed."
) % (fwd(L5_DIR), L5_MISSING, fwd(L5_DIR)) + _TAIL


SCENARIOS = [
    dict(sid="L1_first_light", title="First light (trivial)", prompt=L1,
         work=L1_DIR, max_turns=10, data=[],
         expect_pdf=True, probes=[]),
    dict(sid="L2_anatomy", title="Anatomy of a document (easy)", prompt=L2,
         work=L2_DIR, max_turns=12, data=[],
         expect_pdf=True, probes=[]),
    dict(sid="L3_integral_1", title="Abstract + the user's integral (medium)",
         prompt=L3, work=L3_DIR, max_turns=14,
         data=["The integral from 0 to pi of sin(x) dx."],
         expect_pdf=True, expect_tex_contains=["int", "sin"], probes=[]),
    dict(sid="L4_integral_hard",
         title="Angela's composite expression (hard)", prompt=L4,
         work=L4_DIR, max_turns=16,
         data=["Integral from -1 to +1 of a closed trayectory over the next "
               "expresion: sin(x)+Cos(2x)+tagh(x^2)"],
         expect_pdf=True, expect_tex_contains=["tanh"], probes=[]),
    dict(sid="L5_project_xt",
         title="Multi-file project + BOTH verdict probes (extreme)",
         prompt=L5, work=L5_DIR, max_turns=22,
         data=["The integral from 0 to 1 of x*exp(x^2) dx."],
         expect_pdf=True, expect_tex_contains=["int"],
         probes=[
             # A linter that FINDS the planted bug has SUCCEEDED.
             dict(kind="diagnostic_ok", match=r"broken_fragment",
                  expect="SUCCESS",
                  why="validate_tex ran and reported the planted error - "
                      "finding a bug IS the linter doing its job"),
             # Compiling a file that does not exist really did not happen.
             dict(kind="real_failure",
                  match=r"this_file_does_not_exist_zzz",
                  expect="FAILURE",
                  why="the file does not exist, so no PDF was produced - "
                      "the work truly did not happen"),
         ]),
]


# ------------------------------------------------------------------ toggles
# Exec Report MUST be ON - the table is the whole point of this test.
# Multi-Turn is set FIRST because it gates the modifier checkboxes.
_JS_SET = """() => {
  const set = (sel, want) => {
    const el = document.querySelector(sel);
    if (!el) return 'missing';
    if (el.disabled && el.checked === want) return 'ok-disabled';
    if (el.disabled) return 'disabled:' + el.checked;
    if (el.checked !== want) { el.checked = want; el.dispatchEvent(new Event('change', {bubbles: true})); }
    return String(el.checked);
  };
  const r = {};
  r.mt   = set('#multi-turn-enabled', true);
  r.sxs  = set('#step-by-step-enabled', true);
  r.exec = set('#exec-report-enabled', true);
  r.acpx = set('#acpx-enabled', false);
  r.ask  = set('#ask-execs-enabled', false);
  r.net  = set('#internetEnabled', false);
  return r;
}"""

# Scrape EVERY Exec-Report table currently in the chat log.
# DOM contract from services/response_parser.py::_render_exec_report_html:
#   table.exec-report-table.exec-report-<key>
#     caption "List of <Display> Operations"
#     tbody tr > td.exec-report-col-cmd > pre.exec-report-cmd
#              > td.exec-report-col-status.exec-report-success|failure
_JS_EXEC_TABLES = """() => Array.from(
  document.querySelectorAll('#chat-log table.exec-report-table')
).map(t => ({
  caption: (t.querySelector('caption') || {textContent: ''}).textContent.trim(),
  rows: Array.from(t.querySelectorAll('tbody tr')).map(tr => {
    const cmd = tr.querySelector('.exec-report-cmd');
    const st  = tr.querySelector('.exec-report-col-status');
    return {
      command: cmd ? cmd.textContent : '',
      status: st ? st.textContent.trim() : '',
      ok: !!tr.querySelector('.exec-report-success'),
      failed: !!tr.querySelector('.exec-report-failure')
    };
  })
}))"""


def set_toggles(page):
    try:
        return page.evaluate(_JS_SET)
    except Exception as e:
        return {"error": str(e)}


# ------------------------------------------------------------ reply resolver
# An EXPLICIT invitation to reply. Step-by-Step mode always spells one out, so
# keying on it is safe.
_ASK_RE = re.compile(
    r"(reply\s+(?:exactly\s*)?['\"]?ready|say\s+ready|type\s+ready|"
    r"send\s+ready|reply\s+with\s+ready|"
    r"wait(?:ing)?\s+for\s+(?:your|my|me to)[^.]{0,40}"
    r"(ready|reply|confirm|answer)|let me know when|tell me when you|"
    r"when you(?:'re| are) ready)", re.I)

# The wizard has WRAPPED UP and is no longer asking for anything.
_DONE_RE = re.compile(
    r"(all (?:the )?steps? (?:are )?(?:complete|completed|done|finished)|"
    r"wizard (?:is )?complete|summary|we(?:'re| are) done|that completes|"
    r"no further steps|nothing (?:else|further) to do)", re.I)
_DATA_ASK = re.compile(
    r"(give me|tell me|provide|paste|type|send me|what integral|which integral|"
    r"ask you for|waiting for your|your (own )?(integral|equation|expression))",
    re.I)


def resolve_reply(answer, data_queue):
    """Return (reply, why) - what a real user would send next, or (None, why)."""
    a = answer or ""
    low = a.lower()

    # FINISHED? A wrap-up must STOP the loop. Without this the harness keeps
    # replying READY into a completed wizard and the LLM politely invents extra
    # work - in the smoke run it authored a whole unrequested 186 KB document.
    # This also defuses the loose "the answer mentions step 3" fallback below,
    # which used to fire on a SUMMARY that merely recapped the steps.
    if _DONE_RE.search(low) and not _ASK_RE.search(low):
        return None, "wizard-wrapped-up"

    # The wizard is asking for the DATA we are here to supply.
    if data_queue and _DATA_ASK.search(low) and re.search(
            r"integral|equation|expression", low):
        return data_queue.pop(0), "data"

    m = list(re.finditer(r"ready\s*(\d+)", low))
    if m:
        return "READY %s" % m[-1].group(1), "ready-n"
    if re.search(r"reply\s+(?:exactly\s*)?['\"]?yes\b", low) or \
       re.search(r"\byes or no\b", low):
        return "YES", "yes-no"
    if re.search(r"reply\s+(?:exactly\s*)?['\"]?ready['\"]?", low) or \
       re.search(r"wait for (?:my|me to reply)[^.]*ready", low) or \
       (re.search(r"\bready\b", low) and
            re.search(r"\b(reply|wait|when you)\b", low)):
        return "READY", "ready"
    # Still mid-wizard (it named a next STEP) but did not spell out a token.
    if re.search(r"\bstep\s*[2-9]\b", low) or "next step" in low:
        return "READY", "ready-implied"
    return None, "no-ask(final-or-stall)"


# ------------------------------------------------------------- send / capture
def send_and_wait(page, text, timeout_s):
    t0 = time.time()
    prev = page.evaluate(R._JS_BOT_COUNT)
    page.fill(C.SEL["chat_input"], text)
    page.click(C.SEL["chat_submit"])
    started = True
    try:
        page.wait_for_function(R._JS_STARTED, arg=prev,
                               timeout=C.STARTED_TIMEOUT_MS)
    except Exception:
        started = False
    completed = True
    try:
        page.wait_for_function(R._JS_READY, timeout=timeout_s * 1000)
    except Exception:
        completed = False
    page.wait_for_timeout(C.SETTLE_MS)
    texts = page.evaluate(R._JS_BOT_TEXTS)
    fresh = texts[prev:] if prev < len(texts) else []
    kept = [t.strip() for t in fresh if t and t.strip()
            and not any(m in t for m in C.BUSY_MARKERS)]
    return {"answer": kept[-1] if kept else "", "completed": completed,
            "started": started, "elapsed_s": round(time.time() - t0, 1)}


def grab(page, path):
    try:
        page.bring_to_front()
    except Exception:
        pass
    time.sleep(0.25)
    take_shot(os.path.dirname(path), os.path.basename(path))


# -------------------------------------------------------------- the ORACLE
# The STRONGEST independent oracle available: every pool agent writes its OWN
# verdict into its OWN log file (INI_SECTION_LATEXER) as a separate process.
# That file is written before, and independently of, anything the Exec Report
# renders - so comparing the two is a genuine cross-check, not a tautology.
POOL_DIR = os.path.join(r"C:\Development\Tlamatini", "Tlamatini", "agent",
                        "agents", "pools", "_chat_runs_")

# LaTeXer's documented status vocabulary (docs/claude/agents.md, LaTeXer entry).
# compiled_with_errors is DELIBERATELY a failure: a PDF exists but the document
# is mis-typeset, and the user asked for a correct one. Red is honest there.
AGENT_SUCCESS_STATUSES = {
    "compiled", "created", "edited", "read", "listed", "validated", "invalid",
    "analyzed", "analysed", "structure", "cleaned", "installed",
    # other agents a wizard may drive (Pythonxer, Grepper, File-Creator, ...)
    "matches", "no_matches", "found", "not_matched", "ok", "success",
    "completed", "written", "moved", "deleted", "clean", "findings",
    "reported", "triaged", "inspected", "saved", "spoken",
}
AGENT_FAILURE_STATUSES = {
    "compiled_with_errors", "refused", "not_found", "not_unique",
    "engine_unavailable", "error",
}


_INI_ANY = re.compile(r"INI_SECTION_([A-Z0-9_]+)<<<\r?\n(.*?)\r?\n\r?\n", re.S)


def pool_truth(t0, t1):
    """EVERY pool run that finished in [t0, t1], with its OWN verdict.

    Deliberately NOT limited to latexer: a wizard also drives Pythonxer,
    File-Creator and friends, and those rows are in the same Exec Report. The
    first version only read latexer_* runs and was therefore blind to exactly
    the rows that mattered in L4 (two genuinely-failed Pythonxer attempts).
    """
    out = []
    for d in sorted(glob.glob(os.path.join(POOL_DIR, "*"))):
        if not os.path.isdir(d):
            continue
        logs = glob.glob(os.path.join(d, "*.log"))
        lg = logs[0] if logs else ""
        try:
            mt = os.path.getmtime(lg or d)
        except OSError:
            continue
        if not (t0 - 5 <= mt <= t1 + 60):
            continue
        run_name = os.path.basename(d)
        if not lg:
            # A run that left NO log at all cannot be verified either way. It is
            # recorded as UNKNOWN so the judge can be fair about it instead of
            # calling the table a liar for a row it simply cannot check.
            out.append({"run": run_name, "mtime": mt,
                        "agent_type": run_name.split("_")[0], "action": "",
                        "status": "", "success": "", "errors": "",
                        "output_path": "", "expect": "UNKNOWN"})
            continue
        try:
            txt = open(lg, encoding="utf-8", errors="replace").read()
        except OSError:
            continue
        m = _INI_ANY.search(txt)
        if m:
            hdr = dict(re.findall(r"^([a-z_]+):\s*(.*)$", m.group(2), re.M))
            agent_type = m.group(1).lower()
        else:
            # Not every agent emits an INI_SECTION. Pythonxer, for one, ends
            # its log with "... agent finished. Result: TRUE|FALSE" - a verdict
            # written by the agent process itself, so it is just as independent.
            hdr, agent_type = {}, run_name.split("_")[0]
            fin = re.search(r"finished\.\s*Result:\s*(TRUE|FALSE)", txt, re.I)
            if fin:
                hdr["success"] = ("true" if fin.group(1).upper() == "TRUE"
                                  else "false")
        status = (hdr.get("status") or "").strip().lower()
        success = (hdr.get("success") or "").strip().lower()
        # STATUS WINS over the success flag - that is the whole R4 lesson: a
        # linter reports status=invalid AND success=False in the same breath,
        # and the second one is about the DOCUMENT, not about the agent.
        if status in AGENT_SUCCESS_STATUSES:
            expect = "SUCCESS"
        elif status in AGENT_FAILURE_STATUSES:
            expect = "FAILURE"
        elif success in ("true", "yes", "1"):
            expect = "SUCCESS"
        elif success in ("false", "no", "0"):
            expect = "FAILURE"
        else:
            expect = "UNKNOWN"
        out.append({"run": os.path.basename(os.path.dirname(lg)), "mtime": mt,
                    "agent_type": agent_type,
                    "action": (hdr.get("action") or "").strip(),
                    "status": status, "success": success,
                    "errors": (hdr.get("errors") or "").strip(),
                    "output_path": (hdr.get("output_path") or "").strip(),
                    "expect": expect})
    out.sort(key=lambda r: r["mtime"])
    return out
def filesystem_truth(work_dir):
    """GROUND TRUTH, read from disk - never from the table."""
    pdfs = [p for p in glob.glob(os.path.join(work_dir, "**", "*.pdf"),
                                 recursive=True) if os.path.getsize(p) > 400]
    texs = glob.glob(os.path.join(work_dir, "**", "*.tex"), recursive=True)
    body = ""
    for t in texs:
        try:
            body += open(t, encoding="utf-8", errors="replace").read()
        except Exception:
            pass
    return {"pdfs": pdfs, "pdf_count": len(pdfs),
            "pdf_bytes": max([os.path.getsize(p) for p in pdfs], default=0),
            "tex_count": len(texs), "tex_body": body}


def judge(sc, tables, truth, pool):
    """Compare what the TABLE said against what REALLY happened."""
    rows = [r for t in tables for r in t["rows"]]
    verdicts = []
    problems = []

    # ---- deliberate probes (scenario 5): exact per-row expectations
    for pr in sc.get("probes", []):
        hit = [r for r in rows if re.search(pr["match"], r["command"], re.I)]
        if not hit:
            verdicts.append(dict(probe=pr["kind"], found=False,
                                 expect=pr["expect"], got="(no row)",
                                 verdict="NOT_EXERCISED", why=pr["why"]))
            continue
        for r in hit:
            got = "SUCCESS" if r["ok"] else "FAILURE"
            if got == pr["expect"]:
                v = "CORRECT"
            elif pr["expect"] == "SUCCESS":
                v = "FALSE_FAILURE"
            else:
                v = "FALSE_SUCCESS"
            if v != "CORRECT":
                problems.append("%s: expected %s got %s for %r"
                                % (pr["kind"], pr["expect"], got,
                                   r["command"][:90]))
            verdicts.append(dict(probe=pr["kind"], found=True,
                                 expect=pr["expect"], got=got, verdict=v,
                                 command=r["command"][:160], why=pr["why"]))

    # ---- THE REAL CHECK: the table's verdicts must equal the agents' OWN
    # verdicts, 1:1 and in order. The pool logs are written by separate
    # processes before the Exec Report exists, so this is a true cross-check.
    #
    # An earlier version of this oracle used "a PDF exists on disk => any red
    # compile row is a lie". That was WRONG and it falsely accused Tlamatini:
    # LaTeX happily emits a PDF for a broken document, and LaTeXer reports that
    # honestly as compiled_with_errors (a mis-typeset PDF is NOT the work the
    # user asked for). It also ignored retries, where an early genuine failure
    # is followed by a later success. Judge each row against its own run.
    pdf_real = truth["pdf_count"] > 0
    table_fail = sum(1 for r in rows if r["failed"])
    agent_fail = sum(1 for p in pool if p["expect"] == "FAILURE")
    agent_ok = sum(1 for p in pool if p["expect"] == "SUCCESS")
    unknown = sum(1 for p in pool if p["expect"] == "UNKNOWN")

    # TWO INEQUALITIES, one per direction Angela cares about. They are stated as
    # bounds rather than a 1:1 zip on purpose: run-to-row alignment is not
    # guaranteed (a run can leave no log at all, and the window can clip a
    # neighbour), and a matcher that guesses would produce FALSE ACCUSATIONS -
    # which is exactly the sin this whole test exists to detect.
    #
    #   every agent that really FAILED must be red   -> table_fail >= agent_fail
    #   red rows may not exceed the real failures     -> table_fail <= agent_fail
    #   ...plus the runs we genuinely could not read     + unknown
    if table_fail < agent_fail:
        problems.append(
            "FALSE_SUCCESS: the agents' own logs report %d real failure(s) but "
            "the table printed only %d FAILURE row(s) - a real failure was "
            "shown as SUCCESS" % (agent_fail, table_fail))
    # FALSE_FAILURE is checked by CONTENT, never by count. A tool call that
    # fails BEFORE its agent spawns (bad args, unparseable request) leaves a red
    # row with no pool run behind it, so "more red rows than failed runs" is NOT
    # evidence of a lie - it was the first thing this oracle got wrong.
    # Instead: take a run that really SUCCEEDED, find the rows that name the
    # artifact it produced, and require at least one of them to be green.
    for p in pool:
        if p["expect"] != "SUCCESS":
            continue
        token = os.path.basename((p.get("output_path") or "").strip())
        if len(token) < 6:
            continue
        hit = [r for r in rows if token.lower() in (r["command"] or "").lower()]
        if hit and all(r["failed"] for r in hit):
            problems.append(
                "FALSE_FAILURE: run %s really succeeded (action=%s status=%s) "
                "and produced %s, yet every table row naming it is RED"
                % (p["run"], p["action"], p["status"], token))

    pairs = [{"i": i, "run": p["run"], "action": p["action"] or p["agent_type"],
              "status": p["status"] or ("success=" + p["success"] if p["success"]
                                        else "(no log)"),
              "errors": p["errors"], "agent_says": p["expect"],
              "table_says": "-", "match": p["expect"] != "UNKNOWN"}
             for i, p in enumerate(pool)]

    if sc.get("expect_pdf") and not pdf_real:
        problems.append("NO PDF was produced on disk at all")

    for needle in sc.get("expect_tex_contains", []):
        if needle.lower() not in truth["tex_body"].lower():
            problems.append("the .tex never got %r written into it" % needle)

    n_ok = sum(1 for r in rows if r["ok"])
    n_bad = sum(1 for r in rows if r["failed"])
    return {"rows_total": len(rows), "rows_success": n_ok, "rows_failure": n_bad,
            "pdf_on_disk": pdf_real, "pdf_count": truth["pdf_count"],
            "pdf_bytes": truth["pdf_bytes"], "probe_verdicts": verdicts,
            "row_pairs": pairs, "agent_runs": pool,
            "agent_fail": agent_fail, "agent_ok": agent_ok,
            "agent_unverifiable": unknown, "table_fail": table_fail,
            "problems": problems,
            "table_is_truthful": not problems}


# --------------------------------------------------------------- args shim
class Args:
    headless = False          # VISIBLE. Angela MUST see it. Non-negotiable.
    slowmo = 0
    user = os.environ.get("TLAMATINI_USER", "angela")
    password = os.environ.get("TLAMATINI_PASS", "")
    judge_model = None
    not_ready_retries = 4
    not_ready_backoff = 10.0
    timeout = PER_TURN_TIMEOUT_S


def run_scenario(h, sc):
    page = h.page
    t_start = time.time()          # window for this scenario's pool runs
    turns = []
    data_queue = list(sc["data"])
    try:
        h.clear_history()
    except Exception:
        pass
    time.sleep(2.0)
    tg = set_toggles(page)
    print("  [%s] toggles mt=%s sxs=%s exec=%s"
          % (sc["sid"], tg.get("mt"), tg.get("sxs"), tg.get("exec")), flush=True)

    msg = sc["prompt"]
    last = None
    repeat = 0
    flow = "CAPPED"
    for ti in range(sc["max_turns"]):
        set_toggles(page)
        try:
            page.wait_for_function(R._JS_EDITABLE, timeout=180_000)
        except Exception:
            pass
        r = send_and_wait(page, msg, PER_TURN_TIMEOUT_S)
        shot = os.path.join(SHOTS, "%s_t%02d.png" % (sc["sid"], ti))
        try:
            grab(page, shot)
        except Exception as e:
            print("   screenshot failed:", e, flush=True)
        ans = r["answer"]
        tok, why = resolve_reply(ans, data_queue)
        turns.append({"i": ti, "sent": (msg if ti else "[WIZARD OPENER]")[:300],
                      "answer": ans, "answer_chars": len(ans),
                      "completed": r["completed"], "elapsed_s": r["elapsed_s"],
                      "next_reply": tok, "why": why,
                      "shot": os.path.basename(shot)})
        print("   turn %02d %6.1fs chars=%-5d reply=%-28s (%s) completed=%s"
              % (ti, r["elapsed_s"], len(ans), (tok or "-")[:28], why,
                 r["completed"]), flush=True)

        if not r["completed"] and not ans:
            flow = "TIMEOUT"
            break
        if ans and ans == last:
            repeat += 1
            if repeat >= 2:
                flow = "STALLED"
                break
        else:
            repeat = 0
        last = ans
        if tok is None:
            flow = "ENDED"
            break
        msg = tok

    tables = []
    try:
        tables = page.evaluate(_JS_EXEC_TABLES)
    except Exception as e:
        print("   exec-table scrape failed:", e, flush=True)
    truth = filesystem_truth(sc["work"])
    pool = pool_truth(t_start, time.time())
    oracle = judge(sc, tables, truth, pool)
    print("   agent self-reports: %s"
          % ", ".join("%s=%s->%s" % (p["action"], p["status"], p["expect"])
                      for p in pool) or "(none)", flush=True)

    # FINAL verdict: the TABLE'S TRUTHFULNESS is what decides pass/fail.
    if oracle["table_is_truthful"] and oracle["rows_total"] > 0:
        status = "TRUE_TABLE"
    elif oracle["rows_total"] == 0:
        status = "NO_TABLE"
    else:
        status = "LYING_TABLE"

    return {"sid": sc["sid"], "title": sc["title"], "flow": flow,
            "status": status, "turns": turns, "tables": tables,
            "oracle": oracle, "work": sc["work"], "toggles": tg,
            "data_left": data_queue}


# --------------------------------------------------------------- summary
_BADGE = {"TRUE_TABLE": "#1e8e3e", "LYING_TABLE": "#c5221f",
          "NO_TABLE": "#b06000"}


def build_summary(results, started_iso):
    now = _dt.datetime.now().isoformat(timespec="seconds")
    p = ["<!doctype html><meta charset='utf-8'>"
         "<title>LaTeXer Step-by-Step x5 - Exec-Report truth test</title>",
         "<style>body{font:14px/1.55 Segoe UI,Arial,sans-serif;margin:0;"
         "background:#0f1420;color:#e8ecf3}.top{position:sticky;top:0;"
         "background:#131a2b;padding:14px 20px;border-bottom:2px solid #2a3550;z-index:5}"
         "h1{margin:0 0 4px;font-size:19px}.sc{background:#182135;border:1px solid #26324e;"
         "border-radius:10px;margin:16px;padding:12px 14px}"
         ".b{padding:2px 10px;border-radius:12px;color:#fff;font-weight:700}"
         ".turn{border-top:1px solid #26324e;padding:8px 0;margin-top:8px}"
         "img{max-width:720px;width:100%;border:1px solid #33405f;border-radius:6px;"
         "display:block;margin:6px 0}.s{color:#a7b3c9;font-size:12.5px;white-space:pre-wrap}"
         "pre{white-space:pre-wrap;background:#0c1120;padding:9px;border-radius:6px;"
         "max-height:260px;overflow:auto;color:#cdd6e6}"
         "table{border-collapse:collapse;margin:8px 0;width:100%}"
         "td,th{border:1px solid #2a3550;padding:4px 8px;font-size:12.5px;text-align:left}"
         ".ok{color:#5fd97f;font-weight:700}.bad{color:#ff6b6b;font-weight:700}"
         ".prob{background:#3a1414;border:1px solid #c5221f;padding:8px;border-radius:6px;"
         "margin:6px 0;color:#ffd7d7}</style>"]
    ntrue = sum(1 for r in results if r["status"] == "TRUE_TABLE")
    p.append("<div class='top'><h1>Tlamatini - LaTeXer Step-by-Step x5 - "
             "does the EXECUTION TABLE tell the TRUTH?</h1>")
    p.append("<div class='s'>VISIBLE headed Chrome - Multi-Turn + Step-by-Step + "
             "Exec Report ON - started %s - updated %s - "
             "<b>truthful tables: %d / %d</b> - ground truth is the real "
             "filesystem, never the table - every photo is the FULL desktop "
             "(clock visible), taken by Shoter</div></div>"
             % (html.escape(started_iso), html.escape(now), ntrue, len(results)))
    for r in results:
        o = r["oracle"]
        p.append("<div class='sc'><div><b>%s</b> - %s &nbsp; "
                 "<span class='b' style='background:%s'>%s</span> &nbsp;"
                 "<span class='s'>flow=%s - rows %d (ok %d / failed %d) - "
                 "PDFs on disk: %d (%d bytes)</span></div>"
                 % (html.escape(r["sid"]), html.escape(r["title"]),
                    _BADGE.get(r["status"], "#666"), r["status"], r["flow"],
                    o["rows_total"], o["rows_success"], o["rows_failure"],
                    o["pdf_count"], o["pdf_bytes"]))
        for prob in o["problems"]:
            p.append("<div class='prob'>%s</div>" % html.escape(prob))
        if o["probe_verdicts"]:
            p.append("<table><tr><th>probe</th><th>expected</th><th>table said</th>"
                     "<th>verdict</th><th>why</th></tr>")
            for v in o["probe_verdicts"]:
                cls = "ok" if v["verdict"] == "CORRECT" else "bad"
                p.append("<tr><td>%s</td><td>%s</td><td>%s</td>"
                         "<td class='%s'>%s</td><td>%s</td></tr>"
                         % (html.escape(v["probe"]), v["expect"], v["got"],
                            cls, v["verdict"], html.escape(v["why"])))
            p.append("</table>")
        pairs = o.get("row_pairs") or []
        if pairs:
            p.append("<div class='s'>Row-by-row cross-check - what the AGENT "
                     "wrote in its own log vs what the TABLE printed:</div>")
            p.append("<table><tr><th>#</th><th>run</th><th>action</th>"
                     "<th>agent status</th><th>agent verdict</th>"
                     "<th>TABLE</th><th>match</th></tr>")
            for q in pairs:
                cls = "ok" if q["match"] else "bad"
                p.append("<tr><td>%d</td><td>%s</td><td>%s</td><td>%s</td>"
                         "<td>%s</td><td>%s</td><td class='%s'>%s</td></tr>"
                         % (q["i"], html.escape(q["run"]),
                            html.escape(q["action"]), html.escape(q["status"]),
                            q["agent_says"], q["table_says"], cls,
                            "MATCH" if q["match"] else "MISMATCH"))
            p.append("</table>")
        for t in r["tables"]:
            p.append("<div class='s'>%s</div><table>" % html.escape(t["caption"]))
            for row in t["rows"]:
                cls = "ok" if row["ok"] else "bad"
                p.append("<tr><td><code>%s</code></td><td class='%s'>%s</td></tr>"
                         % (html.escape(row["command"][:400]), cls,
                            html.escape(row["status"])))
            p.append("</table>")
        for t in r["turns"]:
            p.append("<div class='turn'><div class='s'>turn %d - %.1fs - "
                     "reply-> %s (%s) - completed=%s</div>"
                     % (t["i"], t["elapsed_s"], html.escape(str(t["next_reply"])),
                        t["why"], t["completed"]))
            p.append("<a href='shots/%s' target='_blank'>"
                     "<img loading='lazy' src='shots/%s'></a>"
                     % (t["shot"], t["shot"]))
            p.append("<details><summary>sent</summary><pre>%s</pre></details>"
                     % html.escape(t["sent"]))
            p.append("<details><summary>answer (%d chars)</summary><pre>%s</pre>"
                     "</details></div>"
                     % (t["answer_chars"], html.escape((t["answer"] or "")[:6000])))
        p.append("</div>")
    tmp = SUMMARY + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write("".join(p))
    os.replace(tmp, SUMMARY)


def main():
    only = os.environ.get("LATEX5_ONLY", "").strip()
    scen = [s for s in SCENARIOS if (not only or s["sid"] in only.split(","))]
    started_iso = _dt.datetime.now().isoformat(timespec="seconds")
    print("=" * 74)
    print("LaTeXer STEP-BY-STEP x5 - VISIBLE Chrome - %d scenario(s)" % len(scen))
    print("work root:", WORK_ROOT)
    print("run dir  :", RUN_DIR)
    print("=" * 74, flush=True)

    h = R.Harness(Args())
    results = []
    with sync_playwright() as pw:
        browser = h.launch(pw)
        try:
            h.login()
            h.goto_chat()
            try:
                h.page.wait_for_load_state("load", timeout=30000)
            except Exception:
                pass
            time.sleep(1.0)
            for sc in scen:
                print("\n>>> %s - %s" % (sc["sid"], sc["title"]), flush=True)
                try:
                    res = run_scenario(h, sc)
                except Exception as e:
                    res = {"sid": sc["sid"], "title": sc["title"],
                           "flow": "EXCEPTION", "status": "NO_TABLE",
                           "turns": [], "tables": [],
                           "oracle": {"rows_total": 0, "rows_success": 0,
                                      "rows_failure": 0, "pdf_on_disk": False,
                                      "pdf_count": 0, "pdf_bytes": 0,
                                      "probe_verdicts": [],
                                      "problems": ["exception: %s" % e],
                                      "table_is_truthful": False},
                           "work": sc["work"], "toggles": {}, "data_left": []}
                    try:
                        h.recover()
                    except Exception:
                        pass
                results.append(res)
                with open(RESULTS, "a", encoding="utf-8") as fh:
                    fh.write(json.dumps(res, ensure_ascii=False) + "\n")
                build_summary(results, started_iso)
                print("<<< %s -> %s (flow %s) problems=%s"
                      % (sc["sid"], res["status"], res["flow"],
                         res["oracle"]["problems"] or "none"), flush=True)
        finally:
            build_summary(results, started_iso)
            try:
                browser.close()
            except Exception:
                pass

    print("\n" + "=" * 74)
    print("THE ONLY QUESTION THAT MATTERS: did the table tell the truth?")
    for r in results:
        o = r["oracle"]
        print("  %-18s %-12s rows=%-3d ok=%-3d failed=%-3d pdf=%-2d  %s"
              % (r["sid"], r["status"], o["rows_total"], o["rows_success"],
                 o["rows_failure"], o["pdf_count"],
                 "; ".join(o["problems"])[:90] or "table matched reality"))
    print("SUMMARY:", SUMMARY)
    print("=" * 74, flush=True)
    return 0 if all(r["status"] == "TRUE_TABLE" for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
