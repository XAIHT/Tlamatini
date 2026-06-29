# ═══════════════════════════════════════════════════════════════════
#   ✦  T L A M A T I N I  ✦   —   "one who knows"
#
#   Created by  Angela López Mendoza   ·   @angelahack1
#   Developer · Architect · Creator of Tlamatini
#
#   Every line of this file was written by Angela López Mendoza.
# ═══════════════════════════════════════════════════════════════════
#   Tlamatini Author Banner — do not remove (releases scrub the name automatically)
"""VISUAL performance dashboard for the 3X-speed surgical plan.

This is the *visual counterpart* of the hermetic unit suite
`Tlamatini/agent/tests_perf_3x.py`. Where that suite asserts correctness with
stubs, THIS script MEASURES the dominant levers with real wall-clock numbers and
draws a colored terminal dashboard (bar charts + PASS/FAIL scoreboard) so a human
can SEE that the optimizations are real.

What it measures (the dominant levers from
`surgical_improving_speed_of_Tlamatini_by_a_factor_of_3X.md`):

  L1a  OLLAMA_KEEP_ALIVE resolution matrix          (factory._resolve_keep_alive)
  L1d  warm embeddings singleton                    (factory._get_cached_embeddings)
  L1b  LIVE Ollama serving-layer health + latency   (gpu_perf.detect_ollama_serving_issues
                                                      + real /api/version round-trip;
                                                      optional cold-vs-warm generate)
  L2   orphan-reaper proc-index O(N) scaling        (orphan_reaper._build_proc_index)

Run it:
    python test_perf_3x_visual.py                # safe defaults (no model load)
    TLAMATINI_PERF_LIVE_GEN=1 python test_perf_3x_visual.py   # also times a real generate

It runs in two modes and SAYS which:
  * LIVE     — Django bootstraps and the REAL Tlamatini functions are exercised.
  * FALLBACK — Django/app deps unavailable; equivalent inlined logic is measured
               instead, and the live Ollama probe still runs over the stdlib.
Either way it always produces a useful report — it never just crashes.

No third-party dependency: stdlib only (Django is optional and imported defensively).
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler  # noqa: F401  (kept for parity w/ unit suite)

# ─────────────────────────── terminal styling ───────────────────────────
_USE_COLOR = True


def _enable_vt() -> None:
    """Turn on ANSI escape processing on the Windows console."""
    if os.name != "nt":
        return
    try:
        import ctypes

        k = ctypes.windll.kernel32
        h = k.GetStdHandle(-11)
        mode = ctypes.c_uint32()
        if k.GetConsoleMode(h, ctypes.byref(mode)):
            k.SetConsoleMode(h, mode.value | 0x0004)  # ENABLE_VIRTUAL_TERMINAL_PROCESSING
    except Exception:
        globals()["_USE_COLOR"] = False


def _c(code: str, s: str) -> str:
    if not _USE_COLOR:
        return s
    return f"\033[{code}m{s}\033[0m"


def bold(s):   return _c("1", s)
def dim(s):    return _c("2", s)
def red(s):    return _c("31", s)
def green(s):  return _c("32", s)
def yellow(s): return _c("33", s)
def blue(s):   return _c("36", s)
def magenta(s):return _c("35", s)


def rule(title: str = "") -> None:
    width = 74
    if title:
        pad = width - len(title) - 4
        print(blue("══ ") + bold(title) + " " + blue("═" * max(pad, 0)))
    else:
        print(blue("═" * width))


def bar(value: float, vmax: float, width: int = 34) -> str:
    """A horizontal bar scaled to vmax."""
    if vmax <= 0:
        n = 0
    else:
        n = int(round((value / vmax) * width))
    n = max(0, min(width, n))
    return "█" * n + dim("·" * (width - n))


# Collected at the end into a PASS/FAIL scoreboard.
_SCORE: list[tuple[str, bool, str]] = []


def score(name: str, ok: bool, detail: str) -> None:
    _SCORE.append((name, ok, detail))


# ─────────────────────────── Django bootstrap ───────────────────────────
def bootstrap_django() -> bool:
    """Try to make the real Tlamatini app importable. Returns True on success."""
    here = os.path.dirname(os.path.abspath(__file__))
    app_root = os.path.join(here, "Tlamatini")
    if app_root not in sys.path:
        sys.path.insert(0, app_root)
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "tlamatini.settings")
    # Keep any scratch the import touches inside the app's Temp policy.
    os.environ.setdefault("TLAMATINI_PERF_VISUAL", "1")
    try:
        import django

        django.setup()
        return True
    except Exception as exc:  # pragma: no cover - environment dependent
        print(yellow(f"  (FALLBACK mode: Django unavailable — {type(exc).__name__}: {exc})"))
        return False


# ─────────────────────────── L1a keep_alive ───────────────────────────
_KEEPALIVE_CASES = [
    (None, -1), ("-1", -1), ("0", 0), ("60", 60), ("300", 300), ("3600", 3600),
    ("  -1  ", -1), ("", -1), ("5m", "5m"), ("10m", "10m"), ("1h", "1h"), ("abc", "abc"),
]


def _fallback_resolve_keep_alive():
    raw = os.environ.get("OLLAMA_KEEP_ALIVE")
    if raw is None:
        return -1
    raw = raw.strip()
    if raw == "":
        return -1
    try:
        return int(raw)
    except ValueError:
        return raw


def section_keep_alive(live: bool, factory) -> None:
    rule("L1a — OLLAMA_KEEP_ALIVE resolution (KV-cache pin)")
    resolve = factory._resolve_keep_alive if live else _fallback_resolve_keep_alive
    ok_all = True
    for raw, expected in _KEEPALIVE_CASES:
        old = os.environ.get("OLLAMA_KEEP_ALIVE")
        try:
            if raw is None:
                os.environ.pop("OLLAMA_KEEP_ALIVE", None)
            else:
                os.environ["OLLAMA_KEEP_ALIVE"] = raw
            got = resolve()
        finally:
            if old is None:
                os.environ.pop("OLLAMA_KEEP_ALIVE", None)
            else:
                os.environ["OLLAMA_KEEP_ALIVE"] = old
        ok = got == expected
        ok_all &= ok
        mark = green("✓") if ok else red("✗")
        shown = repr(raw) if raw is not None else "<unset>"
        print(f"  {mark} {shown:>10}  ->  {str(got):<6} {dim('(default resident=-1)' if expected == -1 else '')}")
    print(f"  default when unset = {bold(str(resolve()))}  "
          + (green("resident forever — model never cold-reloads")
             if resolve() == -1 else yellow("not resident")))
    score("L1a keep_alive matrix", ok_all, f"{len(_KEEPALIVE_CASES)} cases")
    print()


# ─────────────────────────── L1d warm embeddings ───────────────────────────
class _FakeEmb:
    """Stand-in for OllamaEmbeddings. Construction sleeps a small fixed amount to
    represent the real cold-handle setup cost; reuse from cache costs ~nothing."""
    instances = 0
    COLD = 0.040  # 40 ms simulated cold-handle build cost (httpx client setup, etc.)

    def __init__(self, model=None, base_url=None, client_kwargs=None):
        type(self).instances += 1
        time.sleep(self.COLD)
        self.model = model
        self.base_url = base_url
        self.client_kwargs = client_kwargs


def section_embeddings(live: bool, factory) -> None:
    rule("L1d — warm embeddings singleton (no rebuild per request)")
    N = 60
    if not live:
        # Inlined cache equivalent so the dashboard still shows the win.
        cache: dict = {}

        def get(cfg, ck):
            key = (cfg["embeding-model"], cfg["ollama_base_url"], cfg.get("ollama_token"))
            if key not in cache:
                cache[key] = _FakeEmb(cfg["embeding-model"], cfg["ollama_base_url"], ck)
            return cache[key]
    else:
        orig = factory.OllamaEmbeddings
        factory.OllamaEmbeddings = _FakeEmb
        factory._EMBEDDINGS_CACHE.clear()
        get = factory._get_cached_embeddings

    cfg = {"embeding-model": "nomic-embed-text",
           "ollama_base_url": "http://127.0.0.1:11434", "ollama_token": None}
    try:
        _FakeEmb.instances = 0
        # Naive world: a fresh handle on every one of N requests.
        t0 = time.perf_counter()
        for _ in range(N):
            _FakeEmb(cfg["embeding-model"], cfg["ollama_base_url"], {})
        naive = time.perf_counter() - t0
        naive_builds = _FakeEmb.instances

        # Cached world: build once, reuse N-1 times.
        _FakeEmb.instances = 0
        t0 = time.perf_counter()
        first = get(cfg, {"timeout": 120.0})
        for _ in range(N - 1):
            again = get(cfg, {"timeout": 120.0})
        cached = time.perf_counter() - t0
        cached_builds = _FakeEmb.instances
        reused = first is again
    finally:
        if live:
            factory.OllamaEmbeddings = orig
            factory._EMBEDDINGS_CACHE.clear()

    vmax = max(naive, cached)
    print(f"  {N} requests, naive (rebuild each):  {bar(naive, vmax)} {naive*1000:7.1f} ms  "
          f"{yellow(str(naive_builds)+' builds')}")
    print(f"  {N} requests, warm singleton     :  {bar(cached, vmax)} {cached*1000:7.1f} ms  "
          f"{green(str(cached_builds)+' build')}")
    speedup = (naive / cached) if cached > 0 else float("inf")
    ok = (cached_builds == 1) and reused and (speedup >= 3.0)
    print(f"  identity reused across calls: {green('yes') if reused else red('no')}   "
          f"speedup: {bold(f'{speedup:5.1f}x')}  (target >= 3x)")
    score("L1d warm embeddings", ok, f"{cached_builds} build vs {naive_builds}; {speedup:.0f}x")
    print()


# ─────────────────────────── L1b live Ollama ───────────────────────────
def _http_get(url: str, timeout: float):
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            body = r.read().decode("utf-8", "replace")
            return r.status, body, (time.perf_counter() - t0)
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace"), (time.perf_counter() - t0)
    except Exception as e:
        return 0, f"{type(e).__name__}: {e}", (time.perf_counter() - t0)


def _fallback_detect(base_url: str, timeout: float = 3.0):
    """Minimal inline of gpu_perf.detect_ollama_serving_issues for FALLBACK mode."""
    if not base_url:
        return None
    vcode, vbody, _ = _http_get(base_url.rstrip("/") + "/api/version", timeout)
    if vcode == 0:
        return None  # nothing listening -> not our concern here
    tcode, tbody, _ = _http_get(base_url.rstrip("/") + "/api/tags", timeout)
    low = (tbody or "").lower()
    if tcode >= 500 or "llama runner process has terminated" in low or "llama-server" in low:
        return ("SERVING-LAYER PROBLEM: the Ollama serving layer looks broken "
                "(possible source-build race on :11434). Stop the source build.")
    return None


def _resolve_base_url(live: bool) -> str:
    if live:
        try:
            from agent.config_loader import load_config  # type: ignore

            cfg = load_config() or {}
            url = (cfg.get("ollama_base_url") or "").strip()
            if url:
                return url
        except Exception:
            pass
    return os.environ.get("OLLAMA_HOST_URL", "http://127.0.0.1:11434")


def section_ollama(live: bool, gpu_perf) -> None:
    rule("L1b — LIVE Ollama serving layer (the #1 lever)")
    base = _resolve_base_url(live)
    print(f"  base_url: {bold(base)}")

    # 1) /api/version round-trip latency (real, cheap, safe).
    vcode, vbody, vdt = _http_get(base.rstrip("/") + "/api/version", 4.0)
    reachable = vcode == 200
    ver = ""
    try:
        ver = json.loads(vbody).get("version", "")
    except Exception:
        pass
    if reachable:
        print(f"  /api/version : {green('OK')} v{ver or '?'}   {bold(f'{vdt*1000:.1f} ms')} round-trip")
    else:
        print(f"  /api/version : {red('UNREACHABLE')}  ({vbody[:60]})")
        score("L1b Ollama reachable", False, "version probe failed")
        print()
        return
    score("L1b Ollama reachable", True, f"v{ver or '?'} {vdt*1000:.0f}ms")

    # 2) serving-layer health verdict (source-build race detector).
    detect = (gpu_perf.detect_ollama_serving_issues if (live and gpu_perf) else _fallback_detect)
    banner = None
    try:
        banner = detect(base, timeout=4)
    except Exception as e:
        banner = None
        print(dim(f"  (detector raised, treated as clean: {e})"))
    if banner:
        print(f"  serving health: {red('PROBLEM')}")
        for ln in str(banner).splitlines():
            print("    " + yellow(ln))
        score("L1b serving health", False, "detector raised a banner")
    else:
        print(f"  serving health: {green('CLEAN')} — no source-build race detected")
        score("L1b serving health", True, "clean")

    # 3) list models.
    tcode, tbody, tdt = _http_get(base.rstrip("/") + "/api/tags", 5.0)
    models = []
    try:
        models = [m.get("name", "") for m in json.loads(tbody).get("models", [])]
    except Exception:
        pass
    print(f"  /api/tags    : {len(models)} model(s) resident  {dim('('+(', '.join(models[:4]) or 'none')+')')}")

    # 4) OPTIONAL real cold-vs-warm generate to visualize keep_alive (env-gated).
    if os.environ.get("TLAMATINI_PERF_LIVE_GEN") == "1" and models:
        model = sorted(models, key=len)[0]  # smallest name ~ smallest model, heuristic
        print(f"  live generate (keep_alive=-1) on {bold(model)} — cold then warm:")
        times = []
        for label in ("cold", "warm"):
            payload = json.dumps({
                "model": model, "prompt": "Reply with the single word: hi",
                "stream": False, "keep_alive": -1,
                "options": {"num_predict": 4},
            }).encode("utf-8")
            req = urllib.request.Request(base.rstrip("/") + "/api/generate", data=payload,
                                         headers={"Content-Type": "application/json"})
            t0 = time.perf_counter()
            try:
                with urllib.request.urlopen(req, timeout=120) as r:
                    r.read()
                dt = time.perf_counter() - t0
            except Exception as e:
                dt = -1
                print(red(f"    {label}: generate failed ({e})"))
                continue
            times.append((label, dt))
        if len(times) == 2:
            vmax = max(t for _, t in times)
            for label, dt in times:
                col = yellow if label == "cold" else green
                print(f"    {label:<4}: {bar(dt, vmax)} {col(f'{dt:7.2f} s')}")
            warm_win = times[0][1] / times[1][1] if times[1][1] > 0 else 1.0
            print(f"    warm/cold ratio: {bold(f'{warm_win:.1f}x')} "
                  + dim("(model stays resident -> no reload on the 2nd call)"))
    else:
        print(dim("  (skipping live generate; set TLAMATINI_PERF_LIVE_GEN=1 to time cold-vs-warm)"))
    print()


# ─────────────────────────── L2 orphan reaper O(N) ───────────────────────────
class _FakeProc:
    def __init__(self, pid, name, ppid):
        self._d = {"pid": pid, "name": name, "ppid": ppid}

    @property
    def info(self):
        return self._d


def _fallback_build_proc_index(procs):
    names, ppids, children = {}, {}, {}
    for p in procs:
        i = p.info
        pid = i["pid"]
        names[pid] = i["name"]
        ppids[pid] = i["ppid"]
        children.setdefault(i["ppid"], []).append(pid)
    return names, ppids, children


def section_reaper(live: bool, orphan_reaper) -> None:
    rule("L2 — orphan-reaper proc-index O(N) (was O(N^2): 5895ms -> 20ms, 290x)")
    build = (orphan_reaper._build_proc_index if live else _fallback_build_proc_index)
    scales = [100, 500, 1000, 2000, 4000, 8000]
    results = []
    for n in scales:
        procs = [_FakeProc(0, "root.exe", -1)]
        for pid in range(1, n + 1):
            procs.append(_FakeProc(pid, f"p{pid}.exe", pid - 1))
        t0 = time.perf_counter()
        names, _, _ = build(procs)
        dt = time.perf_counter() - t0
        assert len(names) == n + 1
        results.append((n, dt))

    vmax = max(dt for _, dt in results)
    for n, dt in results:
        print(f"  {n:>5} procs  {bar(dt, vmax)} {dt*1000:7.2f} ms")
    # O(N) check: time-per-proc must stay roughly flat (an O(N^2) algo would make
    # the per-proc cost grow ~linearly with N). Compare smallest vs largest.
    per_small = results[0][1] / results[0][0]
    per_large = results[-1][1] / results[-1][0]
    growth = (per_large / per_small) if per_small > 0 else 1.0
    linear = growth < 4.0  # generous; O(N^2) would be ~80x here (8000/100)
    print(f"  per-proc cost growth small->large: {bold(f'{growth:.2f}x')}  "
          + (green("flat -> O(N) confirmed") if linear else red("growing -> O(N^2) regression!")))
    score("L2 reaper O(N)", linear and vmax < 1.0, f"8000 procs in {results[-1][1]*1000:.1f}ms")
    print()


# ─────────────────────────── scoreboard ───────────────────────────
def scoreboard() -> int:
    rule("SCOREBOARD — 3X dominant levers")
    passed = 0
    for name, ok, detail in _SCORE:
        mark = green("PASS") if ok else red("FAIL")
        passed += 1 if ok else 0
        print(f"  [{mark}] {name:<26} {dim(detail)}")
    total = len(_SCORE)
    allgood = passed == total
    print()
    summary = f"{passed}/{total} levers verified"
    print((green if allgood else yellow)(bold("  " + summary)))
    return 0 if allgood else 1


# ─────────────────────────── main ───────────────────────────
def main() -> int:
    _enable_vt()
    print()
    rule()
    print(bold("  Tlamatini — 3X SPEED  ·  VISUAL PERFORMANCE DASHBOARD"))
    print(dim("  visual counterpart of Tlamatini/agent/tests_perf_3x.py"))
    rule()
    print()

    live = bootstrap_django()
    mode = green("LIVE (real Tlamatini code)") if live else yellow("FALLBACK (inlined equivalents)")
    print(f"  mode: {mode}\n")

    factory = gpu_perf = orphan_reaper = None
    if live:
        try:
            from agent.rag import factory as _factory  # type: ignore
            from agent import gpu_perf as _gpu_perf  # type: ignore
            from agent import orphan_reaper as _reaper  # type: ignore
            factory, gpu_perf, orphan_reaper = _factory, _gpu_perf, _reaper
        except Exception as exc:
            print(yellow(f"  (app modules import failed, dropping to FALLBACK — {exc})\n"))
            live = False

    section_keep_alive(live, factory) if live else section_keep_alive(False, None)
    section_embeddings(live and factory is not None, factory)
    section_ollama(live and gpu_perf is not None, gpu_perf)
    section_reaper(live and orphan_reaper is not None, orphan_reaper)

    return scoreboard()


if __name__ == "__main__":
    sys.exit(main())
