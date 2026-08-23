# Tlamatini Author Banner - do not remove
r"""
PLAYWRIGHTER LAUNCHER for the visible harnesses.

Angela, 2026-08-12: *"perhaps are you using Playwrighter or your shit?"* - the
harnesses were driving raw `playwright.sync_api` themselves. This is the
equivalent of `shoter_shot.py` for the browser: it copies the PLAYWRIGHTER
agent template into a runtime dir, writes its `config.yaml`, runs
`python playwrighter.py`, and hands back what the agent extracted.

So the browser is driven by TLAMATINI'S OWN AGENT, the photos are taken by
Tlamatini's own Shoter (the agent's `shoter` step), and the harness is left
with the part that is genuinely a test: deciding pass or fail.

Why a launcher and not the MCP tool: these harnesses run standalone, in a
visible foreground window, against a dev server - they must not depend on a
live chat session.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile

# The agent template. Resolved from the repo, with an env override so a
# frozen install can point at its own agents/ directory.
_DEFAULT_AGENTS = r"C:\Development\Tlamatini\Tlamatini\agent\agents"
AGENTS_ROOT = os.environ.get("TLAMATINI_AGENTS_ROOT", _DEFAULT_AGENTS)
TEMPLATE = os.path.join(AGENTS_ROOT, "playwrighter")


class PlaywrighterError(RuntimeError):
    """The agent could not be launched at all (missing template / crash)."""


def _prepare(runtime_base: str) -> str:
    os.makedirs(runtime_base, exist_ok=True)
    runtime = tempfile.mkdtemp(prefix="playwrighter_", dir=runtime_base)
    if not os.path.isdir(TEMPLATE):
        raise PlaywrighterError(
            "Playwrighter template not found at %s - set TLAMATINI_AGENTS_ROOT"
            % TEMPLATE)
    for entry in os.listdir(TEMPLATE):
        src = os.path.join(TEMPLATE, entry)
        if os.path.isfile(src):
            shutil.copy2(src, os.path.join(runtime, entry))
    return runtime


def _parse_extracted(text: str) -> dict:
    """Pull the ``[name]`` / value pairs out of the agent's results file.

    The agent writes each extraction as a ``[name]`` line followed by its
    value and a blank line, so the parse is deliberately literal - a value
    that itself contains blank lines is joined back together rather than
    truncated.
    """
    values: dict = {}
    if "=== EXTRACTED ===" not in text:
        return values
    body = text.split("=== EXTRACTED ===", 1)[1]
    body = body.split("=== STEP TRACE ===", 1)[0]
    current = None
    buffer: list = []
    for raw in body.splitlines():
        line = raw.rstrip("\r")
        if line.startswith("[") and line.endswith("]") and len(line) > 2:
            if current is not None:
                values[current] = "\n".join(buffer).strip()
            current = line[1:-1]
            buffer = []
        elif current is not None:
            buffer.append(line)
    if current is not None:
        values[current] = "\n".join(buffer).strip()
    return values


def run_steps(steps, runtime_base: str, start_url: str = "",
              storage_state_in: str = "", headless: bool = False,
              hold_open_seconds: int = 1, timeout_ms: int = 30000,
              timeout: int = 900, viewport=(1920, 1080)) -> dict:
    """Drive the browser with PLAYWRIGHTER and return its result.

    Returns ``{ok, status, steps_run, steps_total, extracted, trace, log}``.
    Never raises for a FAILED step - a step failure is data the caller must
    report, not an exception that hides it. Only an un-launchable agent
    raises (PlaywrighterError).
    """
    runtime = _prepare(runtime_base)
    try:
        cfg = os.path.join(runtime, "config.yaml")
        with open(cfg, "w", encoding="utf-8", newline="\n") as fh:
            fh.write("start_url: %s\n" % json.dumps(start_url or "about:blank"))
            fh.write("browser: chromium\n")
            # HEADED, always: Angela must be able to WATCH the run.
            fh.write("headless: %s\n" % ("true" if headless else "false"))
            fh.write("browser_channel: chrome\n")
            fh.write("timeout_ms: %d\n" % timeout_ms)
            fh.write("viewport_width: %d\n" % viewport[0])
            fh.write("viewport_height: %d\n" % viewport[1])
            fh.write("hold_open_seconds: %d\n" % hold_open_seconds)
            if storage_state_in:
                fh.write("storage_state_in: %s\n" % json.dumps(storage_state_in))
            fh.write("output_file: playwrighter_results.txt\n")
            fh.write("steps_json: %s\n" % json.dumps(json.dumps(steps)))
            fh.write("target_agents: []\n")

        proc = subprocess.run(
            [sys.executable, "playwrighter.py"], cwd=runtime, timeout=timeout,
            capture_output=True, text=True, encoding="utf-8", errors="replace")

        results_path = os.path.join(runtime, "playwrighter_results.txt")
        results = ""
        if os.path.isfile(results_path):
            with open(results_path, encoding="utf-8", errors="replace") as fh:
                results = fh.read()

        log_path = os.path.join(runtime, os.path.basename(runtime) + ".log")
        log = ""
        if os.path.isfile(log_path):
            with open(log_path, encoding="utf-8", errors="replace") as fh:
                log = fh.read()

        # The agent writes "Status: ok" (capitalised) in its results header.
        # Matching it case-sensitively left every run reporting "unknown" —
        # a harness that cannot read its own tool's verdict is not a check.
        status = "unknown"
        for line in results.splitlines():
            if line.strip().lower().startswith("status:"):
                status = line.split(":", 1)[1].strip().lower()
                break

        trace = []
        if "=== STEP TRACE ===" in results:
            raw = results.split("=== STEP TRACE ===", 1)[1].strip()
            try:
                trace = json.loads(raw)
            except Exception:
                trace = []

        return {
            "ok": status == "ok",
            "status": status,
            "extracted": _parse_extracted(results),
            "trace": trace,
            "steps_run": sum(1 for s in trace if s.get("ok")),
            "steps_total": len(steps),
            "log": log or (proc.stdout or "") + (proc.stderr or ""),
            "runtime": runtime,
        }
    finally:
        # The runtime dir is deliberately KEPT: it holds the agent's own log,
        # which is the evidence for anything that went wrong.
        pass


def failed_steps(result: dict) -> list:
    """The steps that did not succeed, for an honest report."""
    return [s for s in (result.get("trace") or []) if not s.get("ok")]
