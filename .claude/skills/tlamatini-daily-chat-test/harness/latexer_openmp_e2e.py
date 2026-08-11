"""VISIBLE end-to-end replay of Angela's OpenMP LaTeX request.

WHAT THIS IS
============
On 2026-08-10 Angela asked Tlamatini (DB ``agent_agentmessage`` id 49):

    "create a fancy LaTex implementation and its PDF (of course), about the
     complete explanation of how does 'CompleteOpenMPImplementation.cu', with
     diagrams and all fancy stuff ... Put all the files neccesary under the
     directory: ..."

Tlamatini produced NOTHING - the target directory was empty. The Exec Report
in her stored answer (id 50) showed LaTeXer had only ever been called with
``action='validate'``, while Pythonxer failed 4x and a PowerShell here-string
failed once: the LLM had been forced into a shell workaround because a real
LaTeX document could not survive the trip to LaTeXer (every ``\\\\`` row break
was collapsed, and the trailing ``, filename='...'`` was glued into the body).

This harness replays THAT request against the live chat GUI and then checks the
FILESYSTEM, not the prose: a .tex AND a real PDF must exist on disk.

RULES HONOURED (Angela, non-negotiable)
=======================================
* HEADED Chrome, always - ``run_test.Harness.launch`` refuses headless.
* Full-desktop screenshots are taken by Tlamatini's own SHOTER agent
  (``shoter_shot.take_shot``) - never PIL.ImageGrab.
* The verdict is filesystem truth. A confident answer with no PDF is a FAIL.

USAGE
=====
    python latexer_openmp_e2e.py
    LATEX_E2E_TIMEOUT=2400 python latexer_openmp_e2e.py
"""

import os
import sys
import glob
import json
import time
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

import run_test as R        # noqa: E402  (imports config, which snapshots creds)
from shoter_shot import take_shot                # noqa: E402
from playwright.sync_api import sync_playwright  # noqa: E402

RUN_TAG = _dt.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
RUN_DIR = os.path.join(HERE, "reports", "openmp_e2e_%s" % RUN_TAG)
SHOTS = os.path.join(RUN_DIR, "shots")
os.makedirs(SHOTS, exist_ok=True)

APP_ROOT = r"C:\Development\Tlamatini"
WORK_ROOT = os.path.join(APP_ROOT, "Temp", "LaTeXerOpenMP_E2E", RUN_TAG)
OUT_DIR = os.path.join(WORK_ROOT, "OpenMPImplementation")
os.makedirs(OUT_DIR, exist_ok=True)

TIMEOUT_S = int(os.environ.get("LATEX_E2E_TIMEOUT", "1800"))

# Angela's ORIGINAL source. It was deleted from disk on 2026-08-11 12:26, so the
# harness falls back to an equivalent fixture -- and replays her request against
# the REAL file automatically the moment she puts it back.
ORIGINAL_CU = r"C:\Tlamatini\context_files\CompleteOpenMPImplementation.cu"

FIXTURE_CU = r"""/* CompleteOpenMPImplementation.cu -- OpenMP feature tour (test fixture).
 *
 * Build (Windows):
 *   nvcc -ccbin "cl.exe" -Xcompiler "/openmp:llvm /openmp:experimental" \
 *        -O2 CompleteOpenMPImplementation.cu -o CompleteOpenMPImplementation.exe
 */
#include <stdio.h>
#include <omp.h>

#if _OPENMP >= 201307
  #define OMP_40 1
#else
  #define OMP_40 0
#endif
#if _OPENMP >= 201511
  #define OMP_45 1
#else
  #define OMP_45 0
#endif

static int tp_counter = 0;
#pragma omp threadprivate(tp_counter)

static void demo_parallel_basic(void)
{
    #pragma omp parallel
    printf("  thread %d of %d\n", omp_get_thread_num(), omp_get_num_threads());
}

static void demo_for_loops(void)
{
    #pragma omp parallel for
    for (int i = 0; i < 8; ++i) printf("  i=%d\n", i);
}

static void demo_schedule(void)
{
    #pragma omp parallel for schedule(dynamic, 2)
    for (int i = 0; i < 8; ++i) printf("  dyn i=%d\n", i);
}

static void demo_sections(void)
{
    #pragma omp parallel sections
    {
        #pragma omp section
        printf("  section A\n");
        #pragma omp section
        printf("  section B\n");
    }
}

static void demo_single_master(void)
{
    #pragma omp parallel
    {
        #pragma omp single
        printf("  single\n");
        #pragma omp master
        printf("  master\n");
    }
}

static void demo_critical_atomic(void)
{
    int counter = 0, guarded = 0;
    #pragma omp parallel for
    for (int i = 0; i < 100; ++i) {
        #pragma omp atomic
        counter++;
        #pragma omp critical(demo)
        guarded++;
    }
    printf("  atomic=%d critical=%d\n", counter, guarded);
}

static void demo_reduction(void)
{
    long total = 0;
    #pragma omp parallel for reduction(+:total)
    for (int i = 1; i <= 1000; ++i) total += i;
    printf("  sum=%ld\n", total);
}

static void demo_tasking(void)
{
    #pragma omp parallel
    #pragma omp single
    {
        for (int i = 0; i < 4; ++i)
            #pragma omp task firstprivate(i)
            printf("  task %d\n", i);
        #pragma omp taskwait
    }
}

static void demo_simd(void)
{
    double acc = 0.0;
    #pragma omp simd reduction(+:acc)
    for (int i = 0; i < 64; ++i) acc += i * 0.5;
    printf("  simd acc=%.1f\n", acc);
}

static void demo_threadprivate_copyin(void)
{
    tp_counter = 7;
    #pragma omp parallel copyin(tp_counter)
    printf("  tp=%d\n", tp_counter);
}

static void demo_firstprivate_lastprivate(void)
{
    int seed = 5, last = 0;
    #pragma omp parallel for firstprivate(seed) lastprivate(last)
    for (int i = 0; i < 8; ++i) last = seed + i;
    printf("  last=%d\n", last);
}

static void demo_locks(void)
{
    omp_lock_t lock;
    int hits = 0;
    omp_init_lock(&lock);
    #pragma omp parallel for
    for (int i = 0; i < 32; ++i) {
        omp_set_lock(&lock);
        hits++;
        omp_unset_lock(&lock);
    }
    omp_destroy_lock(&lock);
    printf("  locked hits=%d\n", hits);
}

static void demo_nowait_barrier(void)
{
    #pragma omp parallel
    {
        #pragma omp for nowait
        for (int i = 0; i < 4; ++i) printf("  nowait %d\n", i);
        #pragma omp barrier
        #pragma omp single
        printf("  past the barrier\n");
    }
}

static void demo_collapse(void)
{
    #pragma omp parallel for collapse(2)
    for (int i = 0; i < 3; ++i)
        for (int j = 0; j < 3; ++j) printf("  (%d,%d)\n", i, j);
}

static void demo_runtime_api(void)
{
    printf("  max_threads=%d procs=%d dynamic=%d\n",
           omp_get_max_threads(), omp_get_num_procs(), omp_get_dynamic());
}

static void demo_if_clause(void)
{
    int n = 4;
    #pragma omp parallel if (n > 100)
    printf("  serial-by-if thread %d\n", omp_get_thread_num());
}

int main(void)
{
    printf("OpenMP version: %d, max threads: %d\n", _OPENMP, omp_get_max_threads());
    demo_parallel_basic();
    demo_for_loops();
    demo_schedule();
    demo_sections();
    demo_single_master();
    demo_critical_atomic();
    demo_reduction();
    demo_tasking();
    demo_simd();
    demo_threadprivate_copyin();
    demo_firstprivate_lastprivate();
    demo_locks();
    demo_nowait_barrier();
    demo_collapse();
    demo_runtime_api();
    demo_if_clause();
    printf("ALL DEMOS COMPLETED\n");
    return 0;
}
"""


def _log(msg):
    print("[%s] %s" % (_dt.datetime.now().strftime("%H:%M:%S"), msg), flush=True)


def resolve_source():
    """Angela's real .cu when present, else an equivalent fixture."""
    if os.path.isfile(ORIGINAL_CU):
        return ORIGINAL_CU, "ORIGINAL (Angela's own file)"
    path = os.path.join(WORK_ROOT, "CompleteOpenMPImplementation.cu")
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(FIXTURE_CU)
    return path, "FIXTURE (the original was deleted on 2026-08-11 12:26)"


def build_prompt(src, out_dir):
    """Angela's request, VERBATIM, with the two paths substituted."""
    return (
        "Tlamatini, create a fancy LaTex implementation and its PDF (of course), "
        "about the complete explanation of how does "
        "'CompleteOpenMPImplementation.cu', with diagrams and all fancy stuff,  "
        "this program its located at: '%s', feel free to use all of the provided "
        "Mcps and Agents in order to completelly fulfill this task, and **Put all "
        "the files neccesary under the directory: '%s'**, go!."
        % (src.replace("\\", "/"), out_dir.replace("\\", "/"))
    )


def force_toggles(page):
    """Multi-Turn ON, Exec report ON, ACPX/Ask-Execs/Internet OFF."""
    return page.evaluate(
        """() => {
            const want = {
                'multi-turn-enabled': true,
                'exec-report-enabled': true,
                'acpx-enabled': false,
                'ask-execs-enabled': false,
                'step-by-step-enabled': false,
            };
            const out = {};
            for (const [id, value] of Object.entries(want)) {
                const el = document.getElementById(id);
                if (!el) { out[id] = 'missing'; continue; }
                if (!el.disabled && el.checked !== value) {
                    el.checked = value;
                    el.dispatchEvent(new Event('change', {bubbles: true}));
                }
                out[id] = el.checked;
            }
            return out;
        }"""
    )


def filesystem_truth(out_dir):
    """The ONLY verdict that counts: what is actually on disk."""
    tex = sorted(glob.glob(os.path.join(out_dir, "**", "*.tex"), recursive=True))
    pdf = sorted(glob.glob(os.path.join(out_dir, "**", "*.pdf"), recursive=True))
    biggest = max((os.path.getsize(p) for p in pdf), default=0)
    return {
        "tex_files": tex, "pdf_files": pdf,
        "tex_count": len(tex), "pdf_count": len(pdf),
        "pdf_bytes": biggest,
    }


def shot(page, name):
    """Full-desktop screenshot, taken by Tlamatini's SHOTER agent."""
    try:
        page.bring_to_front()
    except Exception:
        pass
    time.sleep(0.8)
    try:
        return take_shot(SHOTS, name)
    except Exception as exc:                       # never fail the run on a shot
        _log("screenshot failed (%s) - REPORTING it, not hiding it" % exc)
        return None


def main():
    src, src_kind = resolve_source()
    prompt = build_prompt(src, OUT_DIR)

    _log("=" * 70)
    _log("OpenMP LaTeX E2E - replay of Angela's request (id 49)")
    _log("source   : %s  [%s]" % (src, src_kind))
    _log("output   : %s" % OUT_DIR)
    _log("timeout  : %ds" % TIMEOUT_S)
    _log("=" * 70)

    before = filesystem_truth(OUT_DIR)
    if before["pdf_count"]:
        raise SystemExit("output dir must start empty; found %d pdf(s)"
                         % before["pdf_count"])

    class Args:
        headless = False       # VISIBLE. Angela MUST see it. Non-negotiable.
        slowmo = 0
        user = os.environ.get("TLAMATINI_USER", "angela")
        password = os.environ.get("TLAMATINI_PASS", "")
        judge_model = None
        not_ready_retries = 8
        not_ready_backoff = 20.0
        timeout = TIMEOUT_S

    record = {"run_tag": RUN_TAG, "source": src, "source_kind": src_kind,
              "output_dir": OUT_DIR, "prompt": prompt}

    with sync_playwright() as p:
        harness = R.Harness(Args())
        browser = harness.launch(p)
        try:
            harness.login()
            harness.goto_chat()
            try:
                harness.clear_history()
            except Exception as exc:
                _log("clear history skipped: %s" % exc)
            toggles = force_toggles(harness.page)
            _log("toggles: %s" % toggles)
            record["toggles"] = toggles
            shot(harness.page, "01_before_send.png")

            _log("sending Angela's request ...")
            # ask_one (not _send_and_capture) so a freshly-booted server replying
            # "Your agent is loading. Please wait a moment." is WAITED OUT and the
            # question resent -- never recorded as the answer.
            rec = harness.ask_one(
                {"id": "openmp-e2e", "category": "latexer", "text": prompt},
                TIMEOUT_S * 1000,
            )
            _log("answer: %d chars in %ss (completed=%s)"
                 % (rec["answer_chars"], rec["elapsed_s"], rec["completed"]))
            record["answer_chars"] = rec["answer_chars"]
            record["elapsed_s"] = rec["elapsed_s"]
            record["completed"] = rec["completed"]
            record["answer"] = rec["answer"]
            shot(harness.page, "02_after_answer.png")
        finally:
            try:
                browser.close()
            except Exception:
                pass

    truth = filesystem_truth(OUT_DIR)
    record["filesystem"] = truth

    problems = []
    if truth["tex_count"] == 0:
        problems.append("NO .tex file was written")
    if truth["pdf_count"] == 0:
        problems.append("NO PDF was produced (this was the original failure)")
    elif truth["pdf_bytes"] < 20000:
        problems.append("PDF is suspiciously small (%d bytes)" % truth["pdf_bytes"])
    if not record.get("completed"):
        problems.append("the chat turn never completed")

    record["problems"] = problems
    record["status"] = "PASS" if not problems else "FAIL"

    with open(os.path.join(RUN_DIR, "result.json"), "w", encoding="utf-8") as handle:
        json.dump(record, handle, indent=2)

    _log("-" * 70)
    _log(".tex files : %d" % truth["tex_count"])
    _log("PDF files  : %d  (largest %d bytes)"
         % (truth["pdf_count"], truth["pdf_bytes"]))
    for path in truth["pdf_files"]:
        _log("   PDF -> %s" % path)
    for problem in problems:
        _log("PROBLEM: %s" % problem)
    _log("VERDICT: %s" % record["status"])
    _log("report : %s" % RUN_DIR)
    _log("-" * 70)
    return 0 if record["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
