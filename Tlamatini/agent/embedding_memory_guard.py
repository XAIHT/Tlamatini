# ═══════════════════════════════════════════════════════════════════
#   ✦  T L A M A T I N I  ✦   —   "one who knows"
#
#   Created by  Angela López Mendoza   ·   @angelahack1
#   Developer · Architect · Creator of Tlamatini
#
#   Every line of this file was written by Angela López Mendoza.
# ═══════════════════════════════════════════════════════════════════
#   Tlamatini Author Banner — do not remove (releases scrub the name automatically)
"""Embedding-memory pre-flight guard for "Set directory as context".

Why this exists
---------------
On PC / consumer GPUs (e.g. RTX 4070 Laptop, 8 GB VRAM) a heavy
embedding model like ``qwen3-embedding:8b`` occupies ~6.2 GB resident
(~77% of total VRAM). Combined with a chat model that may already be
loaded by Ollama, the daemon thrashes RAM<->VRAM swap on every batch
and the context-load can take hours instead of seconds.

This module pre-flights the workload right before
``setup_llm_with_context`` is scheduled:

* It runs ONLY when an NVIDIA GPU is detected via
  ``gpu_perf._has_nvidia_gpu()``. CPU-only / AMD / Apple Silicon hosts
  skip the entire check silently and the legacy flow is unchanged.
* It predicts the embedding model's resident VRAM via a three-tier
  strategy on the Ollama HTTP API (no new dependencies; uses urllib
  identically to ``gpu_perf.pin_ollama_model``).
* It reads total VRAM via the same ``nvidia-smi`` helper pattern the
  ``gpu_perf`` module already uses.
* When the prediction exceeds the threshold (default 80%) of the
  smallest GPU's total VRAM it returns a structured warning dict;
  otherwise (or on any probe failure) it returns ``None`` and the
  caller proceeds normally.

The guard is FAIL-OPEN by design: a diagnostic must never block the
user. Any unhandled probe error returns ``None``.

Three-tier embedding-model footprint
------------------------------------
A. Model already resident in Ollama (``/api/ps``): use ``size_vram``
   verbatim - exact ground truth, no estimation.
B. Model pulled but not loaded (``/api/show``): use
   ``general.parameter_count`` and ``details.quantization_level`` with
   a standard bits-per-weight table, multiplied by an overhead factor
   (1.40 for >= 1B-parameter models, 2.20 for sub-1B where the
   proportional KV/buffer cost is larger).
C. Model not pulled / cloud model / probe failure: return ``None``
   (fail-open).
"""
from __future__ import annotations

import json
import math
import os
import subprocess
import urllib.error
import urllib.request
from typing import Optional


DEFAULT_THRESHOLD = 0.80

# Multiplier applied to raw weight bytes to estimate the Ollama-resident
# VRAM footprint (weights + KV cache + activation buffers + allocator
# slack). Calibrated on this RTX 4070 Laptop:
#   qwen3-embedding:8b   raw 4.54 GB -> resident 6.24 GB -> factor 1.37
#   Nomic-Embed-Text     raw 0.27 GB -> resident 0.60 GB -> factor 2.22
_OVERHEAD_LARGE = 1.40
_OVERHEAD_SMALL = 2.20
_SMALL_MODEL_THRESHOLD = 1_000_000_000

# Standard llama.cpp / GGUF bits-per-weight averages. Matched
# case-insensitively against /api/show details.quantization_level.
_QUANT_BITS = {
    "F32": 32.0,
    "F16": 16.0,
    "BF16": 16.0,
    "Q8_0": 8.5,
    "Q6_K": 6.56,
    "Q5_K_M": 5.69,
    "Q5_K_S": 5.54,
    "Q5_1": 5.5,
    "Q5_0": 5.5,
    "Q4_K_M": 4.83,
    "Q4_K_S": 4.58,
    "Q4_1": 4.5,
    "Q4_0": 4.55,
    "Q3_K_L": 4.27,
    "Q3_K_M": 3.91,
    "Q3_K_S": 3.5,
    "Q2_K": 2.96,
}
_DEFAULT_BITS_PER_WEIGHT = 5.0

# Mirrors the hardcoded defaults in rag/factory.py::setup_llm_with_context
# so the chunk-count projection matches what FAISS actually processes.
_DEFAULT_EXCLUDED_BASENAMES = (
    "package-lock.json",
    "yarn.lock",
    "pnpm-lock.yaml",
    "bun.lockb",
)


def _run_cmd(cmd: list, timeout: int = 5) -> tuple:
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout, shell=False
        )
        return result.returncode, (result.stdout or "") + (result.stderr or "")
    except FileNotFoundError:
        return 127, f"{cmd[0]}: not found on PATH"
    except subprocess.TimeoutExpired:
        return 124, f"{cmd[0]}: timed out after {timeout}s"
    except Exception as exc:
        return 1, f"{cmd[0]}: {exc}"


def _gpu_total_memory_bytes() -> Optional[int]:
    """Return the smallest single-GPU total VRAM in bytes, or None.

    Compared against the smallest GPU because Ollama loads each model
    into one device by default; using sum-of-totals would silently
    under-report the constraint on heterogeneous multi-GPU rigs.
    """
    code, out = _run_cmd([
        "nvidia-smi",
        "--query-gpu=memory.total",
        "--format=csv,noheader,nounits",
    ])
    if code != 0:
        return None
    totals = []
    for line in (out or "").splitlines():
        s = line.strip()
        if not s:
            continue
        try:
            totals.append(int(float(s)))
        except ValueError:
            continue
    if not totals:
        return None
    return min(totals) * 1024 * 1024


def _ollama_show(base_url: str, model: str, timeout: float = 4.0) -> Optional[dict]:
    if not base_url or not model:
        return None
    url = base_url.rstrip("/") + "/api/show"
    payload = json.dumps({"name": model}).encode("utf-8")
    req = urllib.request.Request(
        url, data=payload, method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read())
    except (urllib.error.URLError, TimeoutError, ValueError, OSError):
        return None
    except Exception:
        return None


def _ollama_ps(base_url: str, timeout: float = 3.0) -> Optional[list]:
    if not base_url:
        return None
    url = base_url.rstrip("/") + "/api/ps"
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            data = json.loads(r.read())
        return list(data.get("models", []))
    except (urllib.error.URLError, TimeoutError, ValueError, OSError):
        return None
    except Exception:
        return None


def _ollama_loaded_vram_bytes(base_url: str, model: str) -> Optional[int]:
    models = _ollama_ps(base_url) or []
    target = (model or "").lower()
    for m in models:
        name = str(m.get("name") or m.get("model") or "").lower()
        if name == target:
            vram = m.get("size_vram") or m.get("size") or 0
            try:
                vram_i = int(vram)
            except (TypeError, ValueError):
                continue
            if vram_i > 0:
                return vram_i
    return None


def _bits_per_weight(quant: Optional[str]) -> float:
    if not quant:
        return _DEFAULT_BITS_PER_WEIGHT
    key = str(quant).strip().upper()
    return _QUANT_BITS.get(key, _DEFAULT_BITS_PER_WEIGHT)


def _predict_vram_from_show(show: dict) -> Optional[int]:
    mi = show.get("model_info") or {}
    det = show.get("details") or {}
    try:
        params = int(mi.get("general.parameter_count") or 0)
    except (TypeError, ValueError):
        params = 0
    if params <= 0:
        return None
    quant_raw = det.get("quantization_level")
    quant = quant_raw if isinstance(quant_raw, str) else None
    bits = _bits_per_weight(quant)
    weights = int(params * bits / 8.0)
    overhead = _OVERHEAD_LARGE if params >= _SMALL_MODEL_THRESHOLD else _OVERHEAD_SMALL
    return int(weights * overhead)


def _extract_embedding_dim(show: dict) -> Optional[int]:
    mi = show.get("model_info") or {}
    for key, val in mi.items():
        if isinstance(key, str) and key.endswith(".embedding_length"):
            try:
                return int(val)
            except (TypeError, ValueError):
                continue
    return None


def _parse_omissions(omissions: Optional[str]) -> tuple:
    basenames = list(_DEFAULT_EXCLUDED_BASENAMES)
    extensions: list = []
    if omissions:
        for tok in str(omissions).split(","):
            t = tok.strip()
            if not t:
                continue
            if t.startswith("*."):
                extensions.append(t[1:])
            else:
                basenames.append(t)
    return tuple(basenames), tuple(extensions)


def _is_excluded(basename: str, basenames: tuple, extensions: tuple) -> bool:
    if basename in basenames:
        return True
    for ext in extensions:
        if basename.endswith(ext):
            return True
    return False


def _estimate_chunks(
    path: str,
    filename: Optional[str],
    omissions: Optional[str],
    chunk_size: int,
    chunk_overlap: int,
    max_chunks_per_file: int,
) -> int:
    """Walk the directory and sum projected chunk counts.

    Uses ``os.path.getsize`` as a proxy for character count - close
    enough for the warning's projection. Honors the same exclusion
    rules ``CustomTextLoader`` enforces so the count matches what FAISS
    will see.
    """
    stride = max(1, chunk_size - chunk_overlap)
    basenames, extensions = _parse_omissions(omissions)
    total = 0
    cap = int(max_chunks_per_file) if max_chunks_per_file and max_chunks_per_file > 0 else 0

    def add_file(filepath: str) -> None:
        nonlocal total
        try:
            size = os.path.getsize(filepath)
        except OSError:
            return
        if size <= 0:
            return
        n = max(1, math.ceil(size / stride))
        if cap > 0:
            n = min(n, cap)
        total += n

    try:
        if filename:
            target = os.path.join(path, filename)
            if os.path.isfile(target) and not _is_excluded(
                os.path.basename(target), basenames, extensions
            ):
                add_file(target)
            return total

        for root, _dirs, files in os.walk(path):
            for f in files:
                if _is_excluded(f, basenames, extensions):
                    continue
                add_file(os.path.join(root, f))
    except Exception:
        return total
    return total


def _has_nvidia_gpu_cached() -> bool:
    """Reuse ``gpu_perf``'s cached ``nvidia-smi -L`` probe."""
    try:
        from .gpu_perf import _has_nvidia_gpu
        return bool(_has_nvidia_gpu())
    except Exception:
        return False


def check_embedding_memory_for_directory(
    path: str,
    config: dict,
    omissions: Optional[str] = "",
    filename: Optional[str] = None,
    threshold: float = DEFAULT_THRESHOLD,
) -> Optional[dict]:
    """Top-level pre-flight check.

    Returns a structured warning dict when:
      * an NVIDIA GPU is detected, AND
      * the configured embedding model's predicted VRAM footprint
        exceeds ``threshold`` (default 80%) of the smallest GPU's
        total VRAM.

    Returns ``None`` in every other case (no GPU, cloud model, model
    fits comfortably, any probe failure). The caller should treat
    ``None`` as "no warning - proceed normally".
    """
    if not _has_nvidia_gpu_cached():
        return None

    model = str(config.get("embeding-model") or "").strip()
    if not model:
        return None
    if model.endswith(":cloud"):
        return None
    base_url = str(config.get("ollama_base_url") or "").strip()
    if not base_url:
        return None

    total_vram = _gpu_total_memory_bytes()
    if not total_vram or total_vram <= 0:
        return None

    predicted = _ollama_loaded_vram_bytes(base_url, model)
    source = "loaded"
    show: Optional[dict] = None
    if predicted is None:
        show = _ollama_show(base_url, model)
        if not show:
            return None
        predicted = _predict_vram_from_show(show)
        source = "predicted"
        if not predicted:
            return None

    if show is None:
        show = _ollama_show(base_url, model) or {}
    embedding_dim = _extract_embedding_dim(show) or 0
    chunk_size = int(config.get("chunk_size", 2000) or 2000)
    chunk_overlap = int(config.get("chunk_overlap", 300) or 300)
    max_chunks = int(config.get("max_chunks_per_file", 20) or 20)
    chunks = _estimate_chunks(
        path, filename, omissions, chunk_size, chunk_overlap, max_chunks
    )
    faiss_ram_bytes = chunks * embedding_dim * 4 if embedding_dim else 0

    fraction = predicted / total_vram
    if fraction < threshold:
        return None

    return {
        "model": model,
        "source": source,
        "predicted_vram_bytes": int(predicted),
        "gpu_total_bytes": int(total_vram),
        "percent": round(fraction * 100.0, 1),
        "threshold_percent": round(threshold * 100.0, 1),
        "chunks_estimate": int(chunks),
        "embedding_dim": int(embedding_dim),
        "faiss_ram_bytes": int(faiss_ram_bytes),
    }


def format_warning_message(warning: dict) -> str:
    """Render a chat-bubble HTML message from a warning dict."""
    if not warning:
        return ""
    mb = warning["predicted_vram_bytes"] / (1024 * 1024)
    total_mb = warning["gpu_total_bytes"] / (1024 * 1024)
    source = (
        "currently resident in VRAM"
        if warning["source"] == "loaded"
        else "estimated from model parameters"
    )
    faiss_mb = (
        warning["faiss_ram_bytes"] / (1024 * 1024)
        if warning.get("faiss_ram_bytes")
        else 0.0
    )
    chunks = warning.get("chunks_estimate", 0)
    embedding_dim = warning.get("embedding_dim", 0)

    lines = [
        "&#9888;&#65039; <b>Embedding-memory warning</b>",
        (
            f"Embedding model <code>{warning['model']}</code> needs "
            f"~{mb:,.0f} MiB of VRAM ({source}), which is "
            f"<b>{warning['percent']:.1f}%</b> of the smallest GPU's "
            f"total ({total_mb:,.0f} MiB) &mdash; above the safety "
            f"threshold of {warning['threshold_percent']:.0f}%."
        ),
    ]
    if chunks > 0 and embedding_dim > 0:
        lines.append(
            f"Projected FAISS vector store (RAM, not VRAM): "
            f"~{faiss_mb:,.0f} MiB across {chunks:,} chunks at "
            f"dim {embedding_dim}."
        )
    lines.append(
        "Context loading will continue, but expect slow embedding "
        "throughput or RAM&harr;VRAM swap. To eliminate the pressure, "
        "switch <code>embeding-model</code> in <code>config.json</code> "
        "to a smaller model (e.g. <code>nomic-embed-text:v1.5</code>) "
        "and restart."
    )
    return "<br>".join(lines)
