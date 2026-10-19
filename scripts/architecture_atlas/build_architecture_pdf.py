# -*- coding: utf-8 -*-
# Tlamatini Author Banner — Created by Angela López Mendoza · @angelahack1
"""Rebuild Tlamatini-Architecture.pdf in one step.

1. gen_architecture.py writes Temp/architecture/Tlamatini-Architecture.tex from
   application files tracked in git; database history is summarized. The atlas lists exactly what `git ls-files`
   returns, so `git add` new files BEFORE rebuilding.
2. A private copy of Tlamatini's own LaTeXer pool agent typesets that .tex with
   pdflatex into <repo>/Tlamatini-Architecture.pdf (same launch recipe as
   tlamatini_mcp_server.run_agent_blocking: template copy + model registry +
   resolved config.yaml + CONFIG_PATH).
3. The finished PDF is checked: the file index must list every tracked path and
   the atlas sheets must show every file name.

Usage (from anywhere):
    python scripts/architecture_atlas/build_architecture_pdf.py
    python scripts/architecture_atlas/build_architecture_pdf.py --skip-verify
    python scripts/architecture_atlas/build_architecture_pdf.py --output C:/elsewhere/Atlas.pdf

Needs git, a TeX distribution (MiKTeX recommended) and PyYAML; the final check
uses PyMuPDF (both are in requirements.txt). The first MiKTeX run may install
missing packages on demand and take several minutes.

Exit codes: 0 = done and verified, 1 = typesetting failed, 2 = the generator
could not place a tracked file, 3 = the PDF is missing files.
"""
import argparse
import importlib.util
import os
import re
import shutil
import subprocess
import sys
import time
import unicodedata

import yaml

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.environ.get("TLAMATINI_REPO") or os.path.abspath(os.path.join(HERE, os.pardir, os.pardir))
AGENTS_ROOT = os.path.join(ROOT, "Tlamatini", "agent", "agents")
LATEXER_TEMPLATE = os.path.join(AGENTS_ROOT, "latexer")
OUT_DIR = os.path.join(ROOT, "Temp", "architecture")
TEX_PATH = os.path.join(OUT_DIR, "Tlamatini-Architecture.tex")
RUN_DIR = os.path.join(OUT_DIR, "latexer_run")
DEFAULT_PDF = os.path.join(ROOT, "Tlamatini-Architecture.pdf")

# The exact LaTeXer settings that produced the published atlas: a plain,
# reproducible pdflatex build (no repair ladder, no bibliography/index tools).
COMPILE_SETTINGS = {
    "action": "compile",
    "engine": "pdflatex",
    "overwrite": True,
    "repair": False,
    "bibliography": "none",
    "build_index": False,
    "build_glossaries": False,
    "max_passes": 4,
    "keep_aux": True,
    "auto_preamble": False,
    "open_pdf": False,
    "command_timeout": 1200,
    "source_agents": [],
    "target_agents": [],
}


def say(msg):
    print(msg, flush=True)


def git_files():
    out = subprocess.run(["git", "-C", ROOT, "ls-files", "-z"], capture_output=True, check=True).stdout
    return [f for f in out.decode("utf-8", "replace").split("\0")
            if f and not f.startswith("Tlamatini/agent/migrations/")]


def step_generate():
    say("=== 1/3  Generating the LaTeX source from every listed application file ===")
    env = os.environ.copy()
    env["TLAMATINI_REPO"] = ROOT
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    rc = subprocess.run([sys.executable, os.path.join(HERE, "gen_architecture.py")], cwd=ROOT, env=env).returncode
    if rc != 0 or not os.path.isfile(TEX_PATH):
        say("FAILED: gen_architecture.py exited %d (see %s)" % (rc, os.path.join(OUT_DIR, "generator_report.txt")))
        sys.exit(2 if rc == 2 else 1)
    say("OK: %s (%d bytes)" % (TEX_PATH, os.path.getsize(TEX_PATH)))


def _ignore(_dir, names):
    return [n for n in names
            if n == "__pycache__" or n.endswith((".log", ".pid", ".pyc")) or n.startswith("reanim")]


def parse_section(log_text):
    blocks = re.findall(r"INI_SECTION_LATEXER<<<\n(.*?)>>>END_SECTION_LATEXER", log_text, re.S)
    if not blocks:
        return {}
    fields = {}
    for line in blocks[-1].split("\n"):
        if not line.strip():
            break
        key, sep, value = line.partition(": ")
        if sep:
            fields[key.strip()] = value.strip()
    return fields


def step_typeset(pdf_path):
    say("=== 2/3  Typesetting with Tlamatini's LaTeXer agent (pdflatex) ===")
    shutil.rmtree(RUN_DIR, ignore_errors=True)
    shutil.copytree(LATEXER_TEMPLATE, RUN_DIR, ignore=_ignore, dirs_exist_ok=True)

    # Pool copies live outside the agents tree: carry the portable model
    # registry and resolve the "@config" model fields before overriding.
    registry_path = os.path.join(AGENTS_ROOT, "model_settings.py")
    spec = importlib.util.spec_from_file_location("atlas_model_settings", registry_path)
    registry = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(registry)
    shutil.copy2(registry_path, os.path.join(RUN_DIR, "model_settings.py"))

    cfg_path = os.path.join(RUN_DIR, "config.yaml")
    with open(cfg_path, "r", encoding="utf-8-sig") as f:
        cfg = yaml.safe_load(f) or {}
    if "latexer" in getattr(registry, "AGENTS", {}):
        cfg = registry.resolve_agent_models("latexer", cfg, agent_file=registry_path)
    cfg.update(COMPILE_SETTINGS)
    cfg["tex_path"] = TEX_PATH
    cfg["output_dir"] = os.path.dirname(pdf_path)
    cfg["filename"] = os.path.basename(pdf_path)
    with open(cfg_path, "w", encoding="utf-8") as f:
        yaml.dump(cfg, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

    env = os.environ.copy()
    env["TLAMATINI_TEMP"] = os.path.join(ROOT, "Temp")
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    env.setdefault("CONFIG_PATH", os.path.join(ROOT, "Tlamatini", "agent", "config.json"))
    env.pop("AGENT_REANIMATED", None)

    started = time.time()
    rc = subprocess.run([sys.executable, "latexer.py"], cwd=RUN_DIR, env=env).returncode
    log_path = os.path.join(RUN_DIR, os.path.basename(RUN_DIR) + ".log")
    try:
        with open(log_path, "r", encoding="utf-8", errors="replace") as f:
            fields = parse_section(f.read())
    except FileNotFoundError:
        fields = {}
    status = fields.get("status", "no report")
    say("LaTeXer exit %d after %.0f s: status=%s pages=%s errors=%s warnings=%s"
        % (rc, time.time() - started, status, fields.get("page_count", "?"),
           fields.get("errors", "?"), fields.get("warnings", "?")))
    produced = fields.get("output_path", "")
    same = produced and os.path.normcase(os.path.abspath(produced)) == os.path.normcase(os.path.abspath(pdf_path))
    if status != "compiled" or not same or not os.path.isfile(pdf_path):
        say("FAILED: no clean PDF at %s. LaTeXer log: %s" % (pdf_path, log_path))
        sys.exit(1)
    say("OK: %s (%d bytes)" % (pdf_path, os.path.getsize(pdf_path)))


def squash(text):
    text = unicodedata.normalize("NFKC", text)
    return re.sub(r"[\s\u00ad\u2010\u2011\-]+", "", text)


def step_verify(pdf_path):
    say("=== 3/3  Checking that every listed application file is in the PDF ===")
    try:
        import fitz  # PyMuPDF
    except ImportError:
        say("SKIPPED: PyMuPDF is not installed (pip install pymupdf) - the PDF was NOT verified.")
        return
    files = git_files()
    with fitz.open(pdf_path) as doc:
        pages = [page.get_text() for page in doc]
    start = None
    listed = None
    for i, text in enumerate(pages):
        m = re.search(r"File index\W+([\d,]+)\s+tracked files", text)
        if m:
            start, listed = i, int(m.group(1).replace(",", ""))
            break
    if start is None:
        say("FAILED: the PDF has no 'File index' page.")
        sys.exit(3)
    sheets = squash("".join(pages[:start]))
    index = squash("".join(pages[start:]))
    no_index = [p for p in files if squash(p) not in index]
    no_tile = [p for p in files if squash(p.rsplit("/", 1)[-1]) not in sheets]
    say("pages: %d (%d atlas pages + %d index pages); tracked files: %d; index header says %d"
        % (len(pages), start, len(pages) - start, len(files), listed))
    say("missing from the file index: %d; file names missing from the atlas sheets: %d" % (len(no_index), len(no_tile)))
    for p in (no_index + no_tile)[:40]:
        say("   missing: " + p)
    if no_index or no_tile or listed != len(files):
        say("FAILED: the PDF does not cover every listed application file. Did you `git add` new files first?")
        sys.exit(3)
    say("OK: all %d tracked files are present." % len(files))


def main():
    ap = argparse.ArgumentParser(description="Regenerate and verify Tlamatini-Architecture.pdf.")
    ap.add_argument("--output", default=DEFAULT_PDF, help="PDF to write (default: %(default)s)")
    ap.add_argument("--skip-verify", action="store_true", help="do not check the PDF against git ls-files")
    args = ap.parse_args()
    pdf_path = os.path.abspath(args.output)
    say("Repository: %s" % ROOT)
    step_generate()
    step_typeset(pdf_path)
    if not args.skip_verify:
        step_verify(pdf_path)
    say("DONE: %s" % pdf_path)


if __name__ == "__main__":
    main()
