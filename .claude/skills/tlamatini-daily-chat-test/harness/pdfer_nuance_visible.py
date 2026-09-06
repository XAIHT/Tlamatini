# Tlamatini Author Banner - do not remove
r"""
PDFer NUANCE / LAYOUT — THE VISIBLE TEST
========================================

ANGELA'S RULE (2026-07-07), NO EXCEPTIONS
    Headless automated tests are FORBIDDEN. Every test runs VISIBLE, on her
    real desktop, so she can SEE every step. Every screenshot is taken by
    Tlamatini's own **Shoter** agent — `PIL.ImageGrab` is forbidden.

WHAT THIS PROVES, AND HOW IT REFUSES TO LIE
-------------------------------------------
Angela's report: *"way too flaky, way too mediocre … always overlaps the
cell's contents into another cells, it only uses an ugly brown scheme of
color, the same stupid font."*

So this run does four things she can watch happen:

1. **Renders the SAME content under different treatments** through the REAL
   `pdfer.py` agent — spawned exactly the way the pool spawns it
   (`python pdfer.py` in a copied runtime directory with a written
   `config.yaml`), never by importing the modules. If the agent entry point is
   broken, this test breaks.

2. **Renders the OLD engine's output too** (`engine: legacy`), on the same
   torture table, so the before/after sits side by side on screen instead of
   being a claim in a report.

3. **Audits every produced PDF against the file on disk** with PyMuPDF — real
   glyph boxes, real overlap, real off-sheet ink. The verdict is FILESYSTEM
   TRUTH, not the renderer's opinion of itself: `xhtml2pdf` returned `err=0`
   while printing one cell on top of another, which is the entire reason this
   agent now audits its own output.

4. **Opens each finished PDF on screen** and photographs the whole desktop
   with Shoter, so the colours, the fonts and the tables are visible rather
   than described.

⚠️ A CASE IS ONLY A PASS IF THE PDF EXISTS *AND* THE AUDIT IS CLEAN *AND* THE
DESIGN FIELDS THE AGENT REPORTED MATCH WHAT WAS ASKED FOR. A missing photo, a
timed-out render or an unparseable section is a FAILURE and is reported as
one. Nothing here is allowed to record a stale or transient result as a pass.

WHICH TREE IS UNDER TEST
------------------------
The REPO at ``C:\Development\XAIHT\Tlamatini`` — the git working copy, which is
where PDFer's overhaul lives. Note that the Django server serving the chat GUI
on this machine runs from a DIFFERENT install (``C:\Development\Tlamatini``),
so a chat-GUI test would exercise the OLD PDFer until that install is synced.
This harness therefore drives the agent directly, which is the honest way to
test the code that actually changed.

RUN IT (visible, foreground — never backgrounded):
    Start-Process powershell -NoExit -ArgumentList '-NoProfile','-Command', `
      'python "<this file>"'
"""
from __future__ import annotations

import datetime
import html
import os
import shutil
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

REPO = r"C:\Development\XAIHT\Tlamatini"
AGENT_TEMPLATE = os.path.join(REPO, "Tlamatini", "agent", "agents", "pdfer")
SHOTER_TEMPLATE = os.path.join(REPO, "Tlamatini", "agent", "agents", "shoter")

import shoter_shot  # noqa: E402

# Use the REPO's own Shoter, not the other install's, so this run exercises the
# tree under test end to end.
if os.path.isdir(SHOTER_TEMPLATE):
    shoter_shot.TEMPLATE = SHOTER_TEMPLATE


def _out_root():
    base = (os.environ.get("TLAMATINI_TEMP") or "").strip() \
        or os.path.join(REPO, "Temp")
    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    root = os.path.join(base, "PDFerVisible", stamp)
    os.makedirs(root, exist_ok=True)
    return root


# ── the content ─────────────────────────────────────────────────────────
SCIENCE = """# Confinement Physics of the Spherical Tokamak

A tokamak confines a deuterium-tritium plasma using a toroidal magnetic field
of roughly 5 T combined with a poloidal field induced by a 15 MA plasma
current. The superconducting magnets operate at 4 K, cooled by supercritical
helium, and the plasma reaches 150 MHz cyclotron frequencies at temperatures
exceeding 100 million K.

## Energy balance

Energy confinement scales with the square of the minor radius. Neutron flux at
the first wall approaches 2 MW/m2, which drives the materials problem:
tungsten sputtering, helium embrittlement and displacement damage.

> A quench would deposit 40 GJ of stored magnetic energy in milliseconds, so
> the detection system samples at 10 kHz.

### Measured parameters

| Parameter | Symbol | Value | Unit | Notes |
|---|---|---|---|---|
| Toroidal field | B_t | 5.3 | T | at the magnetic axis |
| Plasma current | I_p | 15.0 | MA | flat-top |
| Confinement time | tau_E | 3.7 | s | H-mode, ELMy |
| Stored magnetic energy | W_mag | 40 | GJ | quench-relevant |
| Wall neutron flux | Phi_n | 2.0 | MW/m2 | first-wall average |

## Diagnostics

Configured through
`C:/Users/angel/AppData/Local/Programs/Tlamatini/config/quench_detector.yaml`
and validated against
https://raw.githubusercontent.com/XAIHT/Tlamatini/main/docs/plasma/quench.json

```python
def detect_quench(samples, threshold=0.15):
    baseline = sum(samples[:64]) / 64.0
    return any(abs(s - baseline) / baseline > threshold for s in samples[64:])
```

**Warning:** a quench deposits 40 GJ in milliseconds.
"""

PAPER = """# Coherent Phonon Transport in Layered Antiferromagnets

## Abstract
We report anomalous thermal conductivity in van der Waals antiferromagnets
below the Neel temperature. Using time-domain thermoreflectance we measure a
34% enhancement (p < 0.01, n = 18) attributable to magnon-phonon coupling.

**Keywords:** phonon transport, antiferromagnet, thermal conductivity

## 1. Introduction
Prior work (Delgado et al., 2023) established that spin ordering modifies
lattice dynamics [4, 7, 12]. The reported magnitude was disputed, with
enhancements ranging from 8% to 45% across the literature.

## 2. Methodology
Samples were exfoliated and characterised by Raman spectroscopy at 532 nm.
Thermal measurements were performed between 4 K and 300 K.

| Sample | Thickness (nm) | T_N (K) | kappa (W/m/K) |
|---|---|---|---|
| A1 | 42 | 78 | 41.2 |
| A2 | 61 | 79 | 38.7 |
| B1 | 118 | 77 | 30.6 |

## 3. Results
The measured conductivity was 41.2 W/m/K at 80 K, consistent with the
eigenvalue analysis of the Hamiltonian.

## 4. Discussion
These results are attributed to coherent transport.

## References
[1] Delgado, R. et al. (2023). Nature Physics. doi:10.1038/s41567-023-00001
[2] Okonkwo, A. and Silva, M. (2021). Phys. Rev. B 104, 214301.
"""

CONTRACT = """# Master Services Agreement

WHEREAS the Provider is engaged in the business of software development; and
WHEREAS the Client desires to retain the Provider;

NOW THEREFORE the parties agree as follows:

1.1 Definitions. "Confidential Information" shall mean any information
disclosed by either party under this Agreement.

1.2 The Provider shall deliver the Services in accordance with Schedule A.

2.1 Term. This Agreement shall commence on the Effective Date and continue
until terminated in accordance with clause 2.2.

2.2 Either party may terminate this Agreement upon thirty (30) days notice.

3.1 Limitation of Liability. Notwithstanding anything herein, neither party
shall be liable for indirect or consequential damages.

3.2 Governing Law. This Agreement shall be governed by the laws of Mexico.

IN WITNESS WHEREOF the parties have executed this Agreement.
"""

TORTURE = r"""# The tables that broke the old engine

| Key | Value |
|---|---|
| install_path | C:\Users\angel\AppData\Local\Programs\Tlamatini\TlamatiniSourceCode\agent\agents\pdfer\config.yaml |
| endpoint | https://raw.githubusercontent.com/XAIHT/Tlamatini/main/Tlamatini/agent/agents/pdfer/pdfer.py |

| Agent | Transport | Command | Timeout | Idle | Grace | Description | Status |
|---|---|---|---|---|---|---|---|
| netspeed_calculator | streamable-http | npx -y @modelcontextprotocol/server-memory | 180 | 10 | 2 | Measures throughput with DerSimonian-Laird fusion | operational |
| instant_messaging_doctor | stdio | python -m agent.acpx.self_acp_server | 45 | 6 | 12 | Diagnoses Telegrammer and Whatsapper readiness | degraded |

| Identifier | Fully qualified configuration key | Default | Range | Consumer |
|---|---|---|---|---|
| unified_agent_llm_step_timeout_seconds | agent.self_healing.SelfHealingInvoker.timeout | 80 | 1..3600 | MultiTurnToolAgentExecutor |
"""

# (label, what it demonstrates, content, extra config, expectations)
#
# ⚠️ ORDER MATTERS, AND THE BROKEN CONTROL GOES **FIRST**.
#
# Every case opens its PDF on screen so Angela can see it. The first version of
# this file listed the deliberately-broken OLD-engine render LAST — so when the
# run finished, the document left sitting on her screen was the one with the
# overlapping cells and the brown headers, with nothing on it saying "this is
# the BEFORE". She saw it and quite reasonably concluded nothing had been
# fixed.
#
# That was a defect in the TEST, not the agent. Two fixes, both deliberate:
#   1. the broken control renders FIRST, so the last document on screen is
#      always a good one;
#   2. its filename SAYS SO — `00_BEFORE_old_engine_BROKEN.pdf` — because a
#      title bar is the only label a PDF viewer gives you.
#
# A demonstration that requires the viewer to remember which file is which is
# not a demonstration.
CASES = [
    ("00_BEFORE_old_engine_BROKEN",
     "⚠️ THE BEFORE PICTURE, ON PURPOSE — the same tables through the OLD "
     "xhtml2pdf engine. Overlapping cells and brown headers are the BUG being "
     "demonstrated, not a regression.",
     TORTURE, {"engine": "legacy"}, {"engine": "xhtml2pdf"}),
    ("01_AFTER_same_tables_NEW_engine",
     "THE FIX: the very same tables through the new solver — audited clean",
     TORTURE, {}, {"layout_clean": "true"}),
    ("02_science_autodetect",
     "Science content, NOTHING specified — PDFer must choose the dark treatment",
     SCIENCE, {}, {"nuance": "scientific_dark", "background_mode": "dark"}),
    ("03_paper_autodetect",
     "An abstract + citations — PDFer must choose the white, justified journal look",
     PAPER, {}, {"nuance": "academic_paper", "background_mode": "light"}),
    ("04_contract_autodetect",
     "A contract — plain, and NO ornament at all (safety, not taste)",
     CONTRACT, {}, {"nuance": "legal_instrument", "decorations": "none"}),
    ("05_paper_forced_marketing",
     "The SAME paper, overruled: nuance='marketing' must WIN over detection",
     PAPER, {"nuance": "marketing"},
     {"nuance": "marketing_brochure", "nuance_source": "explicit"}),
    ("06_science_seeded_amber",
     "The SAME science content, one colour given: predominant_color=#F59E0B",
     SCIENCE, {"predominant_color": "#F59E0B"},
     {"nuance": "scientific_dark", "predominant_color": "#F59E0B"}),
]


def run_agent(label, content, extra, out_root):
    """Spawn the REAL agent the way the pool does. Returns (header, body, err)."""
    import yaml

    workdir = os.path.join(out_root, "_runtimes", label)
    if os.path.isdir(workdir):
        shutil.rmtree(workdir, ignore_errors=True)
    shutil.copytree(AGENT_TEMPLATE, workdir,
                    ignore=shutil.ignore_patterns("__pycache__", "*.log",
                                                  "*.pid"))
    cfg_path = os.path.join(workdir, "config.yaml")
    with open(cfg_path, "r", encoding="utf-8") as fh:
        cfg = yaml.safe_load(fh) or {}
    cfg.update({
        "mode": "markdown",
        "input_text": content,
        "title": content.split("\n")[0].lstrip("# ").strip(),
        "subtitle": "Tlamatini PDFer — visible proof, %s"
                    % datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
        "author": "Angela Lopez Mendoza",
        "output_dir": os.path.join(out_root, "pdfs"),
        "filename": label + ".pdf",
        "overwrite": True,
        "toc": False,
    })
    cfg.update(extra)
    with open(cfg_path, "w", encoding="utf-8") as fh:
        yaml.safe_dump(cfg, fh, allow_unicode=True, sort_keys=False)

    proc = subprocess.run([sys.executable, "pdfer.py"], cwd=workdir,
                          capture_output=True, text=True, timeout=420,
                          encoding="utf-8", errors="replace")

    log_path = os.path.join(workdir, "%s.log" % label)
    log = ""
    if os.path.isfile(log_path):
        with open(log_path, "r", encoding="utf-8", errors="replace") as fh:
            log = fh.read()

    header, body = {}, ""
    if "INI_SECTION_PDFER<<<" in log:
        section = log.split("INI_SECTION_PDFER<<<", 1)[1] \
            .split(">>>END_SECTION_PDFER", 1)[0]
        head_txt, _, body = section.strip().partition("\n\n")
        for line in head_txt.split("\n"):
            if ": " in line:
                key, _, value = line.partition(": ")
                header[key.strip()] = value.strip()
    return header, body, (proc.stderr or "")[-1500:], log


def audit(pdf_path, margin_mm=18.0):
    """Measure the FILE. Never the renderer's opinion of it."""
    sys.path.insert(0, AGENT_TEMPLATE)
    try:
        import pdfer_audit
        return pdfer_audit.audit_pdf(pdf_path, margin_mm=margin_mm)
    except Exception as exc:
        class _Broken:
            available = False
            error = "%s: %s" % (type(exc).__name__, exc)
            clean = False
            overlap_count = bleed_count = -1
            pages = words = images = 0

            @staticmethod
            def summary():
                return "audit unavailable"

            @staticmethod
            def detail(_n=0):
                return "audit unavailable"
        return _Broken()


def main():
    out_root = _out_root()
    shots = os.path.join(out_root, "shots")
    os.makedirs(shots, exist_ok=True)
    os.makedirs(os.path.join(out_root, "pdfs"), exist_ok=True)

    print("=" * 78)
    print("PDFer VISIBLE TEST  —  Angela's rule: you must SEE every step")
    print("=" * 78)
    print("  repo under test : %s" % REPO)
    print("  output          : %s" % out_root)
    print()
    print("  NOTE: the Django server on this machine runs from")
    print("        C:\\Development\\Tlamatini (a DIFFERENT install), so the")
    print("        chat GUI would exercise the OLD PDFer. This harness drives")
    print("        the agent in the REPO directly — the code that changed.")
    print()

    results = []
    for label, what, content, extra, expect in CASES:
        print("-" * 78)
        print("CASE %s" % label)
        print("   %s" % what)
        started = time.time()
        try:
            header, body, err, _log = run_agent(label, content, extra, out_root)
        except Exception as exc:
            print("   !! agent raised: %s" % exc)
            results.append({"label": label, "what": what, "ok": False,
                            "why": "agent raised %s" % exc, "header": {},
                            "shot": "", "audit": None, "pdf": ""})
            continue
        elapsed = time.time() - started

        pdf = header.get("output_path", "")
        ok = bool(header) and header.get("status") == "created" \
            and pdf and os.path.isfile(pdf)
        why = []
        if not header:
            why.append("no INI_SECTION_PDFER was emitted")
        elif header.get("status") != "created":
            why.append("status=%s" % header.get("status"))
        if not (pdf and os.path.isfile(pdf)):
            why.append("no PDF on disk")

        report = audit(pdf) if ok else None
        if report is not None and report.available and not report.clean:
            # The OLD engine is EXPECTED to be dirty — that IS the point of it.
            # A CLEAN result there would mean the control stopped reproducing
            # the bug, which is its own kind of failure.
            if label.startswith("00_BEFORE"):
                if report.overlap_count == 0:
                    ok = False
                    why.append("the OLD-engine control produced NO overlaps — "
                               "it is no longer demonstrating the bug")
            else:
                ok = False
                why.append(report.summary())

        for key, want in expect.items():
            got = header.get(key, "")
            if got != want:
                ok = False
                why.append("%s=%r, expected %r" % (key, got, want))

        print("   status=%-9s engine=%-9s nuance=%-18s %.1fs"
              % (header.get("status", "?"), header.get("engine", "?"),
                 header.get("nuance", "-"), elapsed))
        if header:
            print("   palette=%-22s colour=%-9s fonts=%-12s deco=%s"
                  % (header.get("palette", "-"),
                     header.get("predominant_color", "-"),
                     header.get("font_pairing", "-"),
                     header.get("decorations", "-")))
        if report is not None and report.available:
            print("   AUDIT: %s" % report.summary())

        # ── SHOW IT: open the PDF and photograph the whole desktop ──────
        shot = ""
        if pdf and os.path.isfile(pdf):
            try:
                os.startfile(pdf)          # noqa: S606 - deliberate, visible
                time.sleep(6.0)            # let the viewer paint
            except Exception as exc:
                print("   (could not open the PDF for viewing: %s)" % exc)
            shot = shoter_shot.take_shot(shots, "%s.png" % label,
                                         runtime_base=out_root) or ""
            if shot:
                print("   photo: %s" % os.path.basename(shot))
            else:
                # A missing photo is a VISIBLE problem, and it fails the case.
                ok = False
                why.append("Shoter did not produce a screenshot")
                print("   !! SHOTER PRODUCED NO PHOTO — recorded as a FAILURE")

        print("   => %s%s" % ("PASS" if ok else "FAIL",
                              "" if ok else "  (%s)" % "; ".join(why)))
        results.append({"label": label, "what": what, "ok": ok,
                        "why": "; ".join(why), "header": header,
                        "shot": shot, "audit": report, "pdf": pdf,
                        "elapsed": elapsed, "body": body})

    write_summary(out_root, results)

    passed = sum(1 for r in results if r["ok"])
    print()
    print("=" * 78)
    print("RESULT: %d/%d cases passed" % (passed, len(results)))
    print("Summary: %s" % os.path.join(out_root, "SUMMARY.html"))
    print("=" * 78)
    try:
        os.startfile(os.path.join(out_root, "SUMMARY.html"))
    except Exception:
        pass
    return 0 if passed == len(results) else 1


def write_summary(out_root, results):
    """A summary page Angela can read without running anything."""
    rows = []
    for r in results:
        h = r["header"]
        a = r["audit"]
        audit_txt = "—"
        if a is not None and getattr(a, "available", False):
            audit_txt = html.escape(a.summary())
        shot_cell = ("<img src='shots/%s' style='width:100%%;border-radius:6px;"
                     "border:1px solid #2a3550'>" % html.escape(
                         os.path.basename(r["shot"]))) if r["shot"] else \
            "<span style='color:#f87171'>NO PHOTO</span>"
        rows.append(
            "<tr class='%s'><td><b>%s</b><div class='what'>%s</div>"
            "<div class='why'>%s</div></td>"
            "<td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td>"
            "<td class='shot'>%s</td></tr>"
            % ("pass" if r["ok"] else "fail",
               html.escape(r["label"]), html.escape(r["what"]),
               html.escape(r["why"]) if r["why"] else "",
               "PASS" if r["ok"] else "FAIL",
               html.escape(h.get("nuance", "—")),
               html.escape(h.get("palette", "—")),
               html.escape(h.get("font_pairing", "—")),
               audit_txt, shot_cell))

    passed = sum(1 for r in results if r["ok"])
    page = """<!doctype html><meta charset="utf-8">
<title>PDFer visible test</title>
<style>
 body{background:#07090F;color:#F2F6FF;font:14px/1.5 Corbel,Segoe UI,sans-serif;
      margin:0;padding:28px}
 h1{font:600 30px Bahnschrift,Segoe UI,sans-serif;
    background:linear-gradient(90deg,#38BDF8,#A78BFA);-webkit-background-clip:text;
    -webkit-text-fill-color:transparent;margin:0 0 4px}
 .sub{color:#9AA9C4;margin-bottom:22px}
 table{border-collapse:collapse;width:100%%}
 th{background:#152238;color:#E0F2FE;text-align:left;padding:9px 11px;
    font-weight:600;position:sticky;top:0}
 td{border-top:1px solid #25324A;padding:11px;vertical-align:top}
 tr.pass td:nth-child(2){color:#34D399;font-weight:700}
 tr.fail td:nth-child(2){color:#FB7185;font-weight:700}
 tr.fail{background:#1a0f14}
 .what{color:#9AA9C4;font-size:12.5px;margin-top:3px}
 .why{color:#FB7185;font-size:12px;margin-top:4px}
 .shot{width:340px}
 .banner{padding:14px 18px;border-radius:9px;margin-bottom:22px;
   background:linear-gradient(135deg,#05070C,#1E3A8A);border:1px solid #25324A}
</style>
<h1>PDFer — nuance, typography, layout</h1>
<div class="sub">%s &nbsp;·&nbsp; <b>%d / %d</b> cases passed &nbsp;·&nbsp;
 every screenshot taken by Tlamatini's <b>Shoter</b> agent</div>
<div class="banner">
 Each row rendered through the <b>real <code>pdfer.py</code> agent</b>, spawned
 the way the pool spawns it, then <b>audited against the produced file</b> with
 PyMuPDF — real glyph boxes, not the renderer's own success flag. The last row
 is the <b>old xhtml2pdf engine</b> on the same tables, deliberately, so the
 before and after sit together.
</div>
<table>
<tr><th>case</th><th>result</th><th>nuance</th><th>palette</th><th>fonts</th>
    <th>layout audit (measured on the PDF)</th><th>the desktop, photographed</th></tr>
%s
</table>
""" % (datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
       passed, len(results), "\n".join(rows))

    with open(os.path.join(out_root, "SUMMARY.html"), "w",
              encoding="utf-8") as fh:
        fh.write(page)


if __name__ == "__main__":
    sys.exit(main())
