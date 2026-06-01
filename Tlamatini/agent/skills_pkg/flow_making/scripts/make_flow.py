#!/usr/bin/env python3
"""
make_flow.py — one-shot driver for the ``flow-making`` skill.

Wraps the existing **FlowCreator** engine end-to-end and emits a canonical
``.flw`` the ACP canvas can load:

  1. Locate the FlowCreator template dir (``agent/agents/flowcreator``), source
     OR frozen layout.
  2. Copy it into a fresh isolated runtime dir (the documented "use Tlamatini's
     agents" launcher pattern — never mutate the template in place).
  3. Write that copy's ``config.yaml`` (JSON is valid YAML, so no PyYAML needed
     and no hand-escaping of the objective).
  4. Run ``python flowcreator.py`` there — it queries the configured Ollama model
     with the full 69-agent ``agentic_skill.md`` catalog and writes
     ``flow_result.json``.
  5. Convert that result to a ``.flw`` via ``result_to_flw.convert`` and write it
     to ``--out``.

Stdlib-only. Invoked by the skill runbook through ``execute_command``.

Usage:
    python make_flow.py --objective "..." --out C:\\path\\flow.flw
                        [--flow-name name] [--model M] [--host URL]
                        [--timeout 600] [--template DIR] [--keep]

The LAST stdout line is machine-readable:
    agent_count=<N> connection_count=<M> flw_path=<abs path>
On failure the process exits non-zero and the last line begins with ``ERROR ``.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from result_to_flw import convert  # noqa: E402  (same-dir helper)

_DEFAULT_HOST = "http://localhost:11434"
_DEFAULT_MODEL = "qwen3.5:397b-cloud"   # matches the FlowCreator template default


def _fail(msg: str) -> int:
    print(f"ERROR {msg}")
    return 1


def _find_template(explicit: str | None) -> Path | None:
    if explicit:
        p = Path(explicit).expanduser().resolve()
        return p if (p / "flowcreator.py").exists() else None
    env = os.environ.get("TLAMATINI_FLOWCREATOR_DIR")
    if env and (Path(env) / "flowcreator.py").exists():
        return Path(env).resolve()
    here = Path(__file__).resolve()
    # scripts -> flow_making -> skills_pkg -> agent (-> Tlamatini -> <install>)
    candidates = [
        here.parents[3] / "agents" / "flowcreator",   # source: agent/agents/flowcreator
        here.parents[4] / "agents" / "flowcreator",   # frozen: <install>/agents/flowcreator
        here.parents[2] / "agents" / "flowcreator",
        here.parents[5] / "agents" / "flowcreator",
    ]
    for c in candidates:
        try:
            if (c / "flowcreator.py").exists():
                return c.resolve()
        except IndexError:
            continue
    return None


def main(argv) -> int:
    ap = argparse.ArgumentParser(description="Generate a .flw from an objective via FlowCreator.")
    ap.add_argument("--objective", required=True, help="One-sentence flow goal.")
    ap.add_argument("--out", required=True, help="Destination .flw path.")
    ap.add_argument("--flow-name", default="", help="Logical flow_filename FlowCreator records.")
    ap.add_argument("--model", default=_DEFAULT_MODEL, help="Ollama model.")
    ap.add_argument("--host", default=_DEFAULT_HOST, help="Ollama host URL.")
    ap.add_argument("--timeout", type=int, default=600, help="Seconds to allow FlowCreator.")
    ap.add_argument("--template", default="", help="Explicit FlowCreator template dir.")
    ap.add_argument("--keep", action="store_true", help="Keep the runtime dir for debugging.")
    args = ap.parse_args(argv[1:])

    if not args.objective.strip():
        return _fail("empty --objective")

    template = _find_template(args.template or None)
    if template is None:
        return _fail("could not locate the FlowCreator template dir "
                     "(pass --template or set TLAMATINI_FLOWCREATOR_DIR)")

    out_path = args.out
    if not out_path.lower().endswith(".flw"):
        out_path += ".flw"
    flow_name = args.flow_name or os.path.basename(out_path)

    runtime_root = tempfile.mkdtemp(prefix="flowmaking_")
    runtime_dir = os.path.join(runtime_root, "flowcreator")
    try:
        shutil.copytree(template, runtime_dir)

        # config.yaml — JSON is valid YAML, so this needs no PyYAML and safely
        # carries any punctuation in the objective.
        cfg = {
            "flow_filename": flow_name,
            "prompt": args.objective,
            "llm": {"host": args.host, "model": args.model},
        }
        with open(os.path.join(runtime_dir, "config.yaml"), "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)

        # Run FlowCreator. It chdirs to its own dir, reads config.yaml there, and
        # writes flow_result.json there, then sys.exit(0).
        try:
            proc = subprocess.run(
                [sys.executable, "flowcreator.py"],
                cwd=runtime_dir,
                timeout=args.timeout,
                capture_output=True,
                text=True,
            )
        except subprocess.TimeoutExpired:
            return _fail(f"FlowCreator timed out after {args.timeout}s "
                         f"(is Ollama running and is model '{args.model}' available?)")

        result_path = os.path.join(runtime_dir, "flow_result.json")
        if not os.path.exists(result_path):
            tail = (proc.stderr or proc.stdout or "").strip()[-400:]
            return _fail(f"FlowCreator produced no flow_result.json (rc={proc.returncode}). "
                         f"Log tail: {tail}")

        with open(result_path, "r", encoding="utf-8") as f:
            result = json.load(f)
        if result.get("status") == "error":
            return _fail(f"FlowCreator: {result.get('message', 'unknown error')}")
        if not result.get("nodes"):
            return _fail("FlowCreator returned an empty flow (no nodes).")

        flw = convert(result)
        if not flw["nodes"]:
            return _fail("conversion produced no nodes")

        out_dir = os.path.dirname(os.path.abspath(out_path))
        if out_dir:
            os.makedirs(out_dir, exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(flw, f, ensure_ascii=False, indent=2)

        print(f"[OK] FlowCreator template: {template}")
        print(f"[OK] wrote {out_path}")
        print(f"agent_count={len(flw['nodes'])} "
              f"connection_count={len(flw['connections'])} "
              f"flw_path={os.path.abspath(out_path)}")
        return 0
    finally:
        if not args.keep:
            shutil.rmtree(runtime_root, ignore_errors=True)
        else:
            print(f"[keep] runtime dir: {runtime_root}")


if __name__ == "__main__":
    sys.exit(main(sys.argv))
