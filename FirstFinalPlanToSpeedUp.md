# First Final Plan To Speed Up Tlamatini

**Objective**: implement one low-risk speedup batch that improves runtime speed without reducing Tlamatini's virtues: useful logs, readable failures, full agent/tool behavior, source-mode development comfort, and frozen-release usability.

**Chosen improvement**: RELEASE runtime mode plus a useful error-logging contract, combined with the logging hot-path cleanup.

This is one focused improvement because both parts touch the same concern: Tlamatini currently pays too much cost for debugging behavior in normal runtime, but the fix must not make diagnostics worse.

---

## 1. Decision

Implement this first:

1. Add a real RELEASE runtime mode for Django:
   - frozen installs default to `DEBUG=False`;
   - source/development runs keep `DEBUG=True`;
   - `TLAMATINI_RELEASE=1` lets source runs test release behavior;
   - `TLAMATINI_DJANGO_DEBUG=1` remains an emergency override.

2. Add an explicit useful-log guarantee:
   - `DEBUG=False` must hide raw stack traces from the browser;
   - `tlamatini.log` must still receive full error tracebacks, timestamps, request paths, and a short error id;
   - background-thread and async-loop failures must still reach the log where practical.

3. Optimize the logging hot path:
   - buffer `_TeeStream` writes instead of flushing every write;
   - flush immediately for error/exception markers;
   - flush on explicit `flush()`;
   - flush on process exit;
   - add a small lock to prevent concurrent writes from interleaving;
   - gate high-frequency WebSocket receive tracing behind `TLAMATINI_WS_TRACE=1`.

This deliberately does not touch agent selection, tool behavior, flow generation, prompts, RAG semantics, databases, or UI design.

---

## 2. Current Evidence

### 2.1 DEBUG Is Always On

Current evidence:

- `Tlamatini/tlamatini/settings.py` sets `DEBUG = True` unconditionally.
- The `DEBUG=False` static branch already exists:
  - `CompressedManifestStaticFilesStorage`
  - `WHITENOISE_AUTOREFRESH = False`
  - `WHITENOISE_MAX_AGE = 31536000`
- Because `DEBUG` is always true, the release-oriented branch never runs normally.

Runtime cost:

- Django keeps debug query tracking active.
- Template/static behavior stays development-like.
- WhiteNoise auto-refresh and zero max-age keep static serving expensive.
- The browser revalidates frontend assets more often than release mode needs.

### 2.2 The Log Tee Flushes Every Write

Current evidence:

- `Tlamatini/manage.py` defines `_TeeStream.write()`.
- Every write does:
  - write to original console;
  - write to the log file;
  - flush the log file immediately.

Runtime cost:

- Every `print()`, logger line, tool output, and debug trace can force file I/O.
- Busy Multi-Turn runs log many lines.
- File flushing becomes a global serialization point across threads.

### 2.3 WebSocket Receive Tracing Is Always Hot

Current evidence:

- `Tlamatini/agent/consumers.py` prints the first part of every incoming WebSocket frame with `flush=True`.
- It also calls `sys.stdout.flush()` immediately after that print.

Runtime cost:

- Every incoming chat/control frame pays console/log flushing overhead.
- The information is useful during deep tracing, but too expensive for default runtime.

---

## 3. Inputs And Outcomes

| Step | Inputs | Work | Outcome |
|---|---|---|---|
| 1. Baseline measurement | Current worktree, current `DEBUG=True`, current `_TeeStream` | Run the benchmark script below before code changes | Baseline JSON with static/page timings and log-write throughput |
| 2. RELEASE mode | `Tlamatini/tlamatini/settings.py` | Replace unconditional `DEBUG=True` with environment-aware release/debug selection | Frozen installs and `TLAMATINI_RELEASE=1` use release mode; source dev stays debug |
| 3. Useful logging contract | `settings.py`, existing `tlamatini.log` tee, Django logging settings | Add explicit `LOGGING` configuration and friendly release errors | Browser hides raw traces; log file keeps actionable tracebacks |
| 4. Buffered tee | `Tlamatini/manage.py` | Buffer normal writes, flush on threshold/time/error/explicit flush/exit, add lock | Less file-I/O overhead with the same important log content |
| 5. Gated WebSocket trace | `Tlamatini/agent/consumers.py` | Put per-frame receive prints behind `TLAMATINI_WS_TRACE=1` | Default chat receives stop paying high-frequency trace logging cost |
| 6. Optional response-parser print audit | `Tlamatini/agent/services/response_parser.py` | Gate full-answer debug prints behind `TLAMATINI_LOG_LEVEL=DEBUG` or equivalent | Large LLM answers no longer spam the hot path by default |
| 7. Verification | Tests, benchmark script, one intentional failure | Run checks and compare before/after benchmark JSON | Measured speedup plus proof that errors remain diagnosable |

---

## 4. Implementation Plan

### Step 1 - Capture Baseline First

Run the measurement script before editing production code.

Expected baseline outputs:

- `DEBUG` behavior:
  - settings report shows `DEBUG=True`;
  - static assets are served with development caching behavior;
  - request timings for representative static assets and pages are recorded.

- logging behavior:
  - `_TeeStream` benchmark reports the cost of flush-per-write;
  - output JSON stores total seconds, lines/sec, bytes written, and file size.

Outcome:

- A baseline file such as `Temp/first_final_speed_before.json`.
- No code changes yet.

### Step 2 - Add RELEASE Mode

Proposed settings shape:

```python
_release_mode = (
    getattr(sys, "frozen", False)
    or os.environ.get("TLAMATINI_RELEASE", "").lower() in {"1", "true", "yes", "on"}
)
_debug_override = os.environ.get("TLAMATINI_DJANGO_DEBUG")
DEBUG = (
    _debug_override.lower() in {"1", "true", "yes", "on"}
    if _debug_override is not None
    else not _release_mode
)
```

Inputs:

- Current `settings.py`.
- Current frozen/source detection.
- Existing WhiteNoise release branch.

Expected outcome:

- Source development remains friendly by default.
- Frozen builds become release mode by default.
- Source can test release mode without building: `TLAMATINI_RELEASE=1`.
- Emergency debugging is still possible: `TLAMATINI_DJANGO_DEBUG=1`.

Risk control:

- Do not tighten `ALLOWED_HOSTS` in this pass.
- Do not change login/session behavior.
- Do not change static file names.

### Step 3 - Keep The Log File Useful In RELEASE

Release mode must improve speed, not blind the operator.

Required logging behavior:

- `tlamatini.log` remains active in both DEBUG and RELEASE.
- `django.request`, `django.server`, `daphne`, `channels`, and `agent` errors write full tracebacks.
- Log lines include:
  - timestamp;
  - level;
  - logger name;
  - process/thread where practical;
  - request path or WebSocket context where available;
  - short error id for browser-facing failures.

Browser-facing behavior:

- In DEBUG: developer behavior can remain detailed.
- In RELEASE: browser receives friendly failure text and an error id.
- The full traceback goes to `tlamatini.log`, not to the browser.

Expected outcome:

- Faster release behavior.
- No useless log file.
- Better separation between user-facing safety and developer/operator diagnostics.

### Step 4 - Buffer `_TeeStream`

Proposed behavior:

- Normal writes are buffered.
- Flush when:
  - buffer reaches about 8 KB;
  - at least 1 second passed since the last flush;
  - text contains urgent markers such as `ERROR`, `Exception`, `Traceback`, `CRITICAL`, or `!!!`;
  - code calls `flush()`;
  - process exits.

Thread behavior:

- Use a small `threading.RLock`.
- Keep writes ordered inside the tee.
- Continue swallowing console/log write failures defensively, matching current resilience.

Expected outcome:

- Same important log content.
- Much fewer flush calls.
- Less blocking during tool-heavy Multi-Turn runs.

### Step 5 - Gate WebSocket Receive Tracing

Proposed behavior:

- Add:

```python
_WS_TRACE = os.environ.get("TLAMATINI_WS_TRACE", "").lower() in {"1", "true", "yes", "on"}
```

- Only print the per-frame receive log when `_WS_TRACE` is true.
- Do not hide errors, tier-2 reaper messages, permission failures, or operational warnings.

Expected outcome:

- Default runtime stops flushing for every WebSocket frame.
- Deep tracing remains one environment variable away.

### Step 6 - Gate Full Answer Debug Prints

The response parser currently prints large cleaned LLM answers. This can be valuable during parser work, but it is expensive and noisy in normal runtime.

Proposed behavior:

- Keep error and summary logs always available.
- Put full-answer dumps behind a debug log level or explicit environment flag.

Expected outcome:

- Long answers no longer flood `tlamatini.log` by default.
- Parser debugging remains available when needed.

---

## 5. Verification Plan

### Required Tests

Run:

```powershell
python Tlamatini/manage.py check
python Tlamatini/manage.py test agent.tests_perf_3x --verbosity 1
```

Also run a focused chat bridge/parser test pass if available in the current tree.

### Required Manual Verification

1. Start in normal source mode.
2. Confirm source mode still has `DEBUG=True`.
3. Start with `TLAMATINI_RELEASE=1`.
4. Confirm `DEBUG=False`.
5. Trigger one intentional test exception through a safe temporary test path or a local-only test.
6. Confirm:
   - browser gets friendly text and error id;
   - `tlamatini.log` gets full traceback;
   - log contains timestamp and request context;
   - no raw stack trace leaks to the browser in release mode.

### Required Benchmark Verification

Run the benchmark script below before and after the implementation.

Pass criteria:

- Release static/page request timings improve or stay neutral.
- `_TeeStream` write throughput improves materially.
- Log file still contains error lines immediately after an error-marker write.
- No feature behavior changes are introduced.

---

## 6. Proposed Measurement Script

Purpose:

- Measure the real speedup from the two selected proposals:
  - RELEASE mode / `DEBUG=False` runtime behavior;
  - buffered logging / gated hot tracing.
- Produce JSON files that can be compared before and after implementation.

Recommended location for the script during measurement:

- `Temp/bench_first_final_speedup.py`

Recommended usage:

```powershell
# Before implementation
python Temp/bench_first_final_speedup.py --label before --out Temp/first_final_speed_before.json

# After implementation
$env:TLAMATINI_RELEASE="1"
python Temp/bench_first_final_speedup.py --label after --out Temp/first_final_speed_after.json
python Temp/bench_first_final_speedup.py --compare Temp/first_final_speed_before.json Temp/first_final_speed_after.json
```

Script:

```python
#!/usr/bin/env python
"""
bench_first_final_speedup.py

Measures the two chosen speedups:
1. RELEASE / DEBUG behavior through a real local Django server and HTTP requests.
2. _TeeStream logging throughput by extracting the actual _TeeStream class from
   Tlamatini/manage.py with AST, without executing manage.py top-level startup.

The script is intentionally self-contained and writes JSON so before/after
results can be compared without guessing.
"""

from __future__ import annotations

import argparse
import ast
import json
import os
import statistics
import subprocess
import sys
import tempfile
import textwrap
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
MANAGE_PY = REPO_ROOT / "Tlamatini" / "manage.py"
SETTINGS_PY = REPO_ROOT / "Tlamatini" / "tlamatini" / "settings.py"


STATIC_PATHS = [
    "/static/agent/js/agent_page_chat.js",
    "/static/agent/js/acp-running-state.js",
    "/static/agent/css/agent_page.css",
    "/static/agent/css/agentic_control_panel.css",
]


class NullConsole:
    def write(self, data):
        return len(data) if isinstance(data, str) else None

    def flush(self):
        return None

    def fileno(self):
        raise OSError("no fileno")

    def isatty(self):
        return False


def percentile(values, pct):
    if not values:
        return None
    ordered = sorted(values)
    idx = int(round((pct / 100.0) * (len(ordered) - 1)))
    return ordered[idx]


def summarize_seconds(samples):
    return {
        "count": len(samples),
        "min_ms": min(samples) * 1000 if samples else None,
        "median_ms": statistics.median(samples) * 1000 if samples else None,
        "mean_ms": statistics.mean(samples) * 1000 if samples else None,
        "p95_ms": percentile(samples, 95) * 1000 if samples else None,
        "max_ms": max(samples) * 1000 if samples else None,
    }


def run_settings_probe(env):
    code = textwrap.dedent(
        """
        import json
        import os
        import sys
        from pathlib import Path

        repo = Path.cwd()
        sys.path.insert(0, str(repo / "Tlamatini"))
        os.environ.setdefault("DJANGO_SETTINGS_MODULE", "tlamatini.settings")
        from django.conf import settings

        print(json.dumps({
            "DEBUG": bool(settings.DEBUG),
            "STATICFILES_STORAGE": getattr(settings, "STATICFILES_STORAGE", None),
            "WHITENOISE_AUTOREFRESH": getattr(settings, "WHITENOISE_AUTOREFRESH", None),
            "WHITENOISE_MAX_AGE": getattr(settings, "WHITENOISE_MAX_AGE", None),
            "STATIC_ROOT": str(getattr(settings, "STATIC_ROOT", "")),
        }, sort_keys=True))
        """
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=str(REPO_ROOT),
        env=env,
        text=True,
        capture_output=True,
        timeout=30,
    )
    if result.returncode != 0:
        return {
            "ok": False,
            "returncode": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
        }
    return {"ok": True, "settings": json.loads(result.stdout.strip())}


def wait_for_server(base_url, timeout_s=45):
    deadline = time.perf_counter() + timeout_s
    last_error = None
    while time.perf_counter() < deadline:
        try:
            with urllib.request.urlopen(base_url + "/", timeout=2) as response:
                if response.status in (200, 301, 302, 403):
                    return True
        except Exception as exc:
            last_error = repr(exc)
        time.sleep(0.25)
    raise RuntimeError(f"server did not become ready: {last_error}")


def start_server(port, env):
    command = [
        sys.executable,
        "Tlamatini/manage.py",
        "runserver",
        "--noreload",
        f"127.0.0.1:{port}",
    ]
    log_path = REPO_ROOT / "Temp" / f"bench_server_{port}.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_file = log_path.open("w", encoding="utf-8", errors="replace")
    proc = subprocess.Popen(
        command,
        cwd=str(REPO_ROOT),
        env=env,
        stdout=log_file,
        stderr=subprocess.STDOUT,
        text=True,
    )
    return proc, log_file, log_path


def stop_server(proc, log_file):
    if proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=10)
    log_file.close()


def fetch_once(url):
    started = time.perf_counter()
    with urllib.request.urlopen(url, timeout=10) as response:
        body = response.read()
        elapsed = time.perf_counter() - started
        return {
            "seconds": elapsed,
            "status": response.status,
            "bytes": len(body),
            "cache_control": response.headers.get("Cache-Control"),
            "etag": response.headers.get("ETag"),
        }


def benchmark_http(env, samples, port):
    base_url = f"http://127.0.0.1:{port}"
    proc, log_file, server_log = start_server(port, env)
    try:
        wait_for_server(base_url)
        results = {}
        targets = ["/"] + STATIC_PATHS
        for path in targets:
            url = base_url + path
            warmup_errors = []
            for _ in range(5):
                try:
                    fetch_once(url)
                except Exception as exc:
                    warmup_errors.append(repr(exc))
                time.sleep(0.03)

            samples_for_path = []
            statuses = {}
            bytes_seen = []
            headers_seen = []
            errors = []
            for _ in range(samples):
                try:
                    item = fetch_once(url)
                    samples_for_path.append(item["seconds"])
                    statuses[str(item["status"])] = statuses.get(str(item["status"]), 0) + 1
                    bytes_seen.append(item["bytes"])
                    headers_seen.append({
                        "cache_control": item["cache_control"],
                        "etag": item["etag"],
                    })
                except Exception as exc:
                    errors.append(repr(exc))
                time.sleep(0.02)

            results[path] = {
                "timing": summarize_seconds(samples_for_path),
                "statuses": statuses,
                "bytes_min": min(bytes_seen) if bytes_seen else None,
                "bytes_max": max(bytes_seen) if bytes_seen else None,
                "first_headers": headers_seen[0] if headers_seen else None,
                "warmup_errors": warmup_errors[:3],
                "errors": errors[:5],
            }
        return {"ok": True, "server_log": str(server_log), "paths": results}
    except Exception as exc:
        return {"ok": False, "error": repr(exc), "server_log": str(server_log)}
    finally:
        stop_server(proc, log_file)


def extract_teestream_class():
    source = MANAGE_PY.read_text(encoding="utf-8", errors="replace")
    tree = ast.parse(source, filename=str(MANAGE_PY))
    class_node = None
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == "_TeeStream":
            class_node = node
            break
    if class_node is None:
        raise RuntimeError("Could not find _TeeStream in Tlamatini/manage.py")

    module = ast.Module(body=[class_node], type_ignores=[])
    ast.fix_missing_locations(module)
    namespace = {
        "os": os,
        "sys": sys,
        "time": time,
        "threading": threading,
    }
    exec(compile(module, str(MANAGE_PY), "exec"), namespace)
    return namespace["_TeeStream"]


def benchmark_teestream(lines, line_bytes):
    TeeStream = extract_teestream_class()
    payload = ("x" * max(1, line_bytes - 1)) + "\n"
    error_payload = "ERROR benchmark marker: Traceback would be flushed immediately\n"

    with tempfile.TemporaryDirectory() as tmp:
        log_path = Path(tmp) / "tee.log"
        with log_path.open("w", encoding="utf-8", errors="replace") as log_file:
            tee = TeeStream(NullConsole(), log_file)
            started = time.perf_counter()
            for idx in range(lines):
                tee.write(payload)
                if idx and idx % max(1, lines // 5) == 0:
                    tee.write(error_payload)
            tee.flush()
            elapsed = time.perf_counter() - started

        size = log_path.stat().st_size

    return {
        "lines": lines,
        "line_bytes": line_bytes,
        "seconds": elapsed,
        "lines_per_second": lines / elapsed if elapsed else None,
        "bytes_written": size,
    }


def run_benchmark(args):
    env = os.environ.copy()
    env.setdefault("PYTHONUNBUFFERED", "1")
    if args.release:
        env["TLAMATINI_RELEASE"] = "1"
    elif "TLAMATINI_RELEASE" in env:
        env.pop("TLAMATINI_RELEASE")

    result = {
        "label": args.label,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "repo_root": str(REPO_ROOT),
        "release_env": bool(args.release),
        "settings_probe": run_settings_probe(env),
        "tee_benchmark": benchmark_teestream(args.log_lines, args.log_line_bytes),
        "http_benchmark": benchmark_http(env, args.samples, args.port),
    }
    return result


def compare(before_path, after_path):
    before = json.loads(Path(before_path).read_text(encoding="utf-8"))
    after = json.loads(Path(after_path).read_text(encoding="utf-8"))

    def ratio(old, new):
        if old in (None, 0) or new in (None, 0):
            return None
        return old / new

    report = {
        "before": before.get("label"),
        "after": after.get("label"),
        "tee_seconds_before": before["tee_benchmark"]["seconds"],
        "tee_seconds_after": after["tee_benchmark"]["seconds"],
        "tee_speedup": ratio(before["tee_benchmark"]["seconds"], after["tee_benchmark"]["seconds"]),
        "http_paths": {},
    }

    before_paths = before.get("http_benchmark", {}).get("paths", {})
    after_paths = after.get("http_benchmark", {}).get("paths", {})
    for path in sorted(set(before_paths) | set(after_paths)):
        old_med = before_paths.get(path, {}).get("timing", {}).get("median_ms")
        new_med = after_paths.get(path, {}).get("timing", {}).get("median_ms")
        report["http_paths"][path] = {
            "median_ms_before": old_med,
            "median_ms_after": new_med,
            "median_speedup": ratio(old_med, new_med),
            "before_headers": before_paths.get(path, {}).get("first_headers"),
            "after_headers": after_paths.get(path, {}).get("first_headers"),
        }

    print(json.dumps(report, indent=2, sort_keys=True))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--label", default="run")
    parser.add_argument("--out")
    parser.add_argument("--release", action="store_true")
    parser.add_argument("--samples", type=int, default=40)
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--log-lines", type=int, default=50000)
    parser.add_argument("--log-line-bytes", type=int, default=160)
    parser.add_argument("--compare", nargs=2, metavar=("BEFORE_JSON", "AFTER_JSON"))
    args = parser.parse_args()

    if args.compare:
        compare(args.compare[0], args.compare[1])
        return

    result = run_benchmark(args)
    text = json.dumps(result, indent=2, sort_keys=True)
    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(text + "\n", encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
```

### What The Script Really Measures

The script measures two different surfaces because the two selected changes speed up different things:

1. Real Django HTTP behavior:
   - starts a real local `runserver`;
   - imports real Tlamatini settings;
   - serves real static paths and the root page;
   - records request medians and cache headers;
   - lets `TLAMATINI_RELEASE=1` prove whether release static behavior is actually active.

2. Real `_TeeStream` code:
   - parses `Tlamatini/manage.py`;
   - extracts the actual `_TeeStream` class with AST;
   - benchmarks the class without executing `manage.py` startup side effects;
   - before implementation, this measures current flush-every-write behavior;
   - after implementation, it measures the new buffered behavior.

### How To Read The Results

Important fields:

- `settings_probe.settings.DEBUG`
  - before: expected `true`;
  - after with release env: expected `false`.

- `http_benchmark.paths[*].timing.median_ms`
  - request latency by path.

- `http_benchmark.paths[*].first_headers.cache_control`
  - should show stronger release caching on static assets after RELEASE mode is active.

- `tee_benchmark.seconds`
  - total time for the log-write burst.

- `tee_speedup`
  - before seconds divided by after seconds;
  - `2.0` means the benchmarked tee writes are twice as fast.

---

## 7. Expected Outcomes

### Best Expected Outcome

- Static/page runtime improves under release mode.
- `tlamatini.log` remains useful and becomes cleaner.
- Tool-heavy chat turns pay less logging overhead.
- WebSocket frame tracing remains available only when requested.
- Source development stays easy.

### Acceptable Outcome

- Static/page timings improve modestly or stay neutral on source `runserver`.
- Log-write throughput improves clearly.
- RELEASE mode is proven safe through the intentional-error test.

### Stop/Reject Outcome

Reject or revise the implementation if any of these happen:

- `tlamatini.log` loses full tracebacks for server errors.
- Browser shows raw stack traces in RELEASE mode.
- Static files fail under `TLAMATINI_RELEASE=1`.
- WebSocket/chat behavior changes beyond logging.
- The benchmark shows no measurable logging improvement.

---

## 8. Rollback Plan

Fast rollback levers:

- Set `TLAMATINI_DJANGO_DEBUG=1` to force debug mode.
- Set `TLAMATINI_WS_TRACE=1` to restore receive-frame tracing.
- Set `TLAMATINI_LOG_LEVEL=DEBUG` to restore deeper runtime logs if implemented.

Code rollback:

- Revert only the `settings.py`, `manage.py`, and `consumers.py` changes from this batch.
- Do not touch database files, migrations, agents, prompts, tools, or RAG code.

---

## 9. Final Recommendation

Implement this as the first real speedup batch:

1. RELEASE mode with `DEBUG=False`.
2. Explicit useful error logging.
3. Buffered `_TeeStream`.
4. Gated WebSocket receive tracing.
5. Benchmark before and after using the script above.

This gives Tlamatini a speed improvement that is easy to reason about, easy to measure, and respectful of the system's virtues: the app gets faster, but when something fails, the log file remains worth opening.
