"""GPU max-performance + Ollama-pinning startup hook for Tlamatini.

Why this exists
---------------
On PC GPUs (RTX 4070 Laptop, 8 GB VRAM) the qwen3-embedding:8b model
sits at ~7.5 GB VRAM — 91% of total. Two failure modes then make context
loading wildly inconsistent (seconds vs. hours):

1. Ollama's default ``keep_alive`` is 5 minutes. After a brief idle window
   the daemon EVICTS the 15.6 GB model from VRAM. The next request must
   reload it from disk, which on a hot/throttling GPU + cold disk cache
   can take many minutes; combined with parallel embed requests during
   a context-load it amplifies to hours of stall.
2. Windows defaults to the "Balanced" power plan. Under embedding bursts
   the CPU clocks down between batches, starving the GPU of work and
   triggering the PC's thermal/power-cap counters.

This module applies the survivable subset of GPU-max-performance levers
that work without admin rights on Windows + consumer GeForce, and pins
the embedding (and chat) model in VRAM via the Ollama keep_alive=-1
contract.

Everything is best-effort: any failed lever is logged and skipped — the
hook NEVER blocks Django startup.

CPU-only / non-NVIDIA hosts
---------------------------
This hook is safe to run on machines without a GPU and on AMD / Apple
Silicon boxes. A one-shot ``nvidia-smi -L`` probe (cached for the
process lifetime) gates the NVIDIA-only Ollama env vars
(``OLLAMA_FLASH_ATTENTION``, ``OLLAMA_KV_CACHE_TYPE``) so they are
neither set on the running process nor persisted via ``setx``. The
universal env vars (``OLLAMA_KEEP_ALIVE=-1`` and the two concurrency
knobs) ARE applied — keep_alive=-1 pins the model in whatever memory
the daemon is using (RAM on CPU, VRAM on GPU). The nvidia-smi
clock/power levers themselves are also already guarded and skip
cleanly when the tool is missing.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import urllib.error
import urllib.request


HIGH_PERFORMANCE_GUID = "8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c"

# Universal Ollama env vars — safe on CPU-only AND any GPU vendor.
# keep_alive=-1 keeps the model resident in whatever memory the daemon
# is using (RAM on CPU, VRAM on GPU). Concurrency knobs are pure
# scheduling and never depend on GPU hardware.
_UNIVERSAL_OLLAMA_ENV = {
    "OLLAMA_KEEP_ALIVE": "-1",
    "OLLAMA_MAX_LOADED_MODELS": "2",
    "OLLAMA_NUM_PARALLEL": "2",
}

# NVIDIA-specific Ollama env vars — applied ONLY when nvidia-smi works.
# OLLAMA_FLASH_ATTENTION=1 requires CUDA; OLLAMA_KV_CACHE_TYPE=q8_0
# requires Flash Attention. Setting either on a CPU-only or non-NVIDIA
# Ollama daemon can prevent some models from loading or trigger silent
# precision fallbacks — keep them gated.
_NVIDIA_ONLY_OLLAMA_ENV = {
    "OLLAMA_FLASH_ATTENTION": "1",
    "OLLAMA_KV_CACHE_TYPE": "q8_0",
}


_NVIDIA_GPU_DETECTED: bool | None = None


def _has_nvidia_gpu() -> bool:
    """Cache-once nvidia-smi probe. Returns False on CPU-only / AMD / Apple."""
    global _NVIDIA_GPU_DETECTED
    if _NVIDIA_GPU_DETECTED is not None:
        return _NVIDIA_GPU_DETECTED
    code, _out = _run(["nvidia-smi", "-L"], timeout=5)
    _NVIDIA_GPU_DETECTED = code == 0
    return _NVIDIA_GPU_DETECTED


def _run(cmd: list[str], timeout: int = 10) -> tuple[int, str]:
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            shell=False,
        )
        output = (result.stdout or "") + (result.stderr or "")
        return result.returncode, output.strip()
    except FileNotFoundError:
        return 127, f"{cmd[0]}: not found on PATH"
    except subprocess.TimeoutExpired:
        return 124, f"{cmd[0]}: timed out after {timeout}s"
    except Exception as exc:
        return 1, f"{cmd[0]}: {exc}"


def _set_ollama_env_vars() -> None:
    """Push ACPX-friendly defaults into the current process env.

    These affect any Ollama child Tlamatini may spawn, and harmonize with
    a future ``ollama serve`` restart that inherits the user env (already
    persisted by ``gpu_perf.persist_ollama_env_for_user`` if invoked).

    The Flash-Attention + KV-cache-quantization pair only ships when an
    NVIDIA GPU is detected — on CPU-only / AMD / Apple Silicon hosts
    they would either be ignored or cause Ollama to refuse certain
    models, so we gate them on a one-shot nvidia-smi probe.
    """
    defaults = dict(_UNIVERSAL_OLLAMA_ENV)
    if _has_nvidia_gpu():
        defaults.update(_NVIDIA_ONLY_OLLAMA_ENV)
    else:
        print("--- [GPU-PERF] No NVIDIA GPU detected — skipping FLASH_ATTENTION / KV_CACHE_TYPE env vars")
    for key, value in defaults.items():
        if not os.environ.get(key):
            os.environ[key] = value
            print(f"--- [GPU-PERF] os.environ[{key}] = {value}")


def _set_windows_high_performance_plan() -> None:
    if not sys.platform.startswith("win"):
        return
    code, out = _run(["powercfg", "/setactive", HIGH_PERFORMANCE_GUID])
    if code == 0:
        print("--- [GPU-PERF] Windows power plan: High Performance")
    else:
        print(f"--- [GPU-PERF] powercfg /setactive returned {code}: {out}")


def _set_self_priority_high() -> None:
    """Bump the Tlamatini Django process to HIGH_PRIORITY_CLASS on Windows."""
    if not sys.platform.startswith("win"):
        return
    try:
        import ctypes

        HIGH_PRIORITY_CLASS = 0x00000080
        handle = ctypes.windll.kernel32.GetCurrentProcess()
        ok = ctypes.windll.kernel32.SetPriorityClass(handle, HIGH_PRIORITY_CLASS)
        if ok:
            print("--- [GPU-PERF] Tlamatini process priority: HIGH")
        else:
            print("--- [GPU-PERF] SetPriorityClass returned 0 (likely OK already or denied)")
    except Exception as exc:
        print(f"--- [GPU-PERF] SetPriorityClass failed: {exc}")


def _query_nvidia_state() -> str | None:
    code, out = _run([
        "nvidia-smi",
        "--query-gpu=name,driver_version,pstate,utilization.gpu,memory.used,memory.total,"
        "clocks.current.graphics,clocks.max.graphics,power.draw,power.limit,temperature.gpu",
        "--format=csv,noheader",
    ])
    if code == 0:
        return out
    return None


def _apply_nvidia_levers() -> None:
    """Best-effort nvidia-smi levers. Most need admin on consumer GeForce.

    We try them anyway: when Tlamatini is launched from an elevated shell
    (e.g. from an installer post-step) they all succeed and the GPU stays
    pinned at maximum customer-boost clocks for the whole session.
    """
    code, out = _run(["nvidia-smi"])
    if code != 0:
        print(f"--- [GPU-PERF] nvidia-smi not available; skipping NVIDIA levers ({out[:120]})")
        return

    # Persistence mode (works on Tesla/Quadro + Linux; consumer GeForce on
    # WDDM returns "not supported" — that's expected).
    pm_code, pm_out = _run(["nvidia-smi", "-pm", "1"])
    if pm_code == 0:
        print("--- [GPU-PERF] Persistence mode enabled")

    # Lock graphics clocks high (needs admin on Windows).
    lgc_code, lgc_out = _run(["nvidia-smi", "-lgc", "2400,3105"])
    if lgc_code == 0:
        print("--- [GPU-PERF] Graphics clocks locked to 2400-3105 MHz")

    # Max out power limit (also needs admin on Windows; default on RTX 4070
    # Laptop is 80 W, max is 140 W).
    pl_code, pl_out = _run(["nvidia-smi", "-pl", "140"])
    if pl_code == 0:
        print("--- [GPU-PERF] Power limit raised to 140 W")

    state = _query_nvidia_state()
    if state:
        print(f"--- [GPU-PERF] Post-apply GPU state: {state}")


def pin_ollama_model(model: str, base_url: str, timeout: int = 5) -> bool:
    """Tell Ollama to keep ``model`` in VRAM forever (keep_alive=-1).

    Uses /api/embed with a 1-token payload to nudge a load; passes
    ``keep_alive=-1`` which Ollama persists on the loaded-model record
    (visible as ``expires_at`` ~ year 2318 in /api/ps).

    Returns True if the pin request was accepted, False otherwise. The
    embed call itself may take a long time if the model is being loaded
    cold — we fire-and-forget by using a short connect timeout and
    swallowing read timeouts (the keep_alive is committed at load time,
    not at response time).
    """
    if not model or not base_url:
        return False
    url = base_url.rstrip("/") + "/api/embed"
    payload = json.dumps({"model": model, "input": "pin", "keep_alive": -1}).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=payload,
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            response.read(1024)  # drain a bit so the keep_alive is committed
        print(f"--- [GPU-PERF] Pinned Ollama model in VRAM (keep_alive=-1): {model}")
        return True
    except urllib.error.URLError as exc:
        # Connection refused = Ollama not running; nothing to pin yet.
        print(f"--- [GPU-PERF] Could not reach Ollama at {url}: {exc}")
        return False
    except TimeoutError:
        # Embed is still computing — but Ollama already accepted keep_alive=-1
        # when it started the load, so the pin is effectively in place.
        print(f"--- [GPU-PERF] Embed pin call timed out but keep_alive=-1 was accepted: {model}")
        return True
    except Exception as exc:
        print(f"--- [GPU-PERF] Pin call failed: {exc}")
        return False


def persist_ollama_env_for_user() -> None:
    """Persist OLLAMA_* perf vars to the Windows user environment.

    They only take effect for the next ``ollama serve`` restart, but
    save the user from re-applying them after a reboot. NVIDIA-specific
    vars (FLASH_ATTENTION, KV_CACHE_TYPE) are persisted ONLY when an
    NVIDIA GPU is present, so a future Ollama daemon on a CPU-only or
    non-NVIDIA host doesn't inherit settings it cannot honor.
    """
    if not sys.platform.startswith("win"):
        return
    pairs = dict(_UNIVERSAL_OLLAMA_ENV)
    if _has_nvidia_gpu():
        pairs.update(_NVIDIA_ONLY_OLLAMA_ENV)
    else:
        print("--- [GPU-PERF] No NVIDIA GPU detected — not persisting FLASH_ATTENTION / KV_CACHE_TYPE to user env")
    for key, value in pairs.items():
        code, out = _run(["setx", key, value], timeout=5)
        if code != 0:
            print(f"--- [GPU-PERF] setx {key} returned {code}: {out[:80]}")
    print("--- [GPU-PERF] Persisted OLLAMA_* user env vars (effective after next 'ollama serve' restart)")


def apply_gpu_max_performance(config: dict | None = None) -> None:
    """Top-level entry point. Runs every survivable max-perf lever.

    Designed to be called from ``AgentConfig.ready()`` on a background
    thread so a slow nvidia-smi or Ollama probe never blocks Daphne.
    """
    print("--- [GPU-PERF] Applying GPU max-performance levers...")
    try:
        _set_ollama_env_vars()
    except Exception as exc:
        print(f"--- [GPU-PERF] env-vars step failed: {exc}")

    try:
        _set_windows_high_performance_plan()
    except Exception as exc:
        print(f"--- [GPU-PERF] power-plan step failed: {exc}")

    try:
        _set_self_priority_high()
    except Exception as exc:
        print(f"--- [GPU-PERF] process-priority step failed: {exc}")

    try:
        _apply_nvidia_levers()
    except Exception as exc:
        print(f"--- [GPU-PERF] nvidia-smi step failed: {exc}")

    try:
        persist_ollama_env_for_user()
    except Exception as exc:
        print(f"--- [GPU-PERF] env-persist step failed: {exc}")

    # Pinning is the highest-leverage fix — do it last so any earlier
    # tweaks (power plan, env vars) are in place first.
    if config:
        base_url = str(config.get("ollama_base_url") or "").strip()
        for cfg_key in ("embeding-model", "unified_agent_model"):
            model = str(config.get(cfg_key) or "").strip()
            # Cloud models (suffix ':cloud') are not served by local Ollama.
            if model and base_url and not model.endswith(":cloud"):
                pin_ollama_model(model, base_url)

    print("--- [GPU-PERF] Apply phase complete.")


def start_in_background(config: dict | None = None) -> None:
    """Fire-and-forget apply on a daemon thread."""
    threading.Thread(
        target=apply_gpu_max_performance,
        args=(config,),
        name="GpuPerfBoot",
        daemon=True,
    ).start()
