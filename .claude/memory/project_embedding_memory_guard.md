---
name: project-embedding-memory-guard
description: "2026-05-12 — Embedding-memory pre-flight guard added (NVIDIA-GPU-only, fail-open) for the \"Set directory as context\" flow"
metadata: 
  node_type: memory
  type: project
  originSessionId: 1cfc5822-06bf-4a70-bc69-7ef135188875
---

2026-05-12: Added `Tlamatini/agent/embedding_memory_guard.py` — emits a chat-bubble warning when the configured Ollama embedding model is predicted to occupy more than 80% of total GPU VRAM. Wired into `agent/consumers.py::setup_contextual_rag_chain` after the `MSG_AGENT_LOADING_CONTEXT` broadcast and before the `asyncio.to_thread(setup_llm_with_context, ...)` call.

**Why**: angelahack1's RTX 4070 Laptop (8 GiB VRAM) shows ~77.9% saturation with `qwen3-embedding:8b` resident alone, jumping to ~91% once a chat model is also loaded — leading to the multi-hour stalls documented in `agent/config.json`'s `_embedding_model_comment`. The guard catches this *before* `FAISS.from_documents` triggers the embed burst.

**How to apply**:
- Gated by `gpu_perf._has_nvidia_gpu()` — CPU-only / AMD / Apple Silicon hosts skip the entire check (no-op).
- Three-tier estimation: (A) `/api/ps` `size_vram` exact, (B) `/api/show` `parameter_count × bits_per_weight × overhead`, (C) any failure returns `None` (fail-open).
- Calibration on this machine: factor 1.40 for ≥1B-param models, 2.20 for sub-1B (weights vs. measured resident).
- `_QUANT_BITS` is the standard llama.cpp/GGUF bits-per-weight table (Q4_K_M=4.83 etc.).
- Test file `agent/test_embedding_memory_guard.py` — 21 tests, all pass; broader sweep `test_embedding_memory_guard + test_flow_contracts + test_password_quoting` = 59 pass.
- Threshold default 0.80, override via `threshold=` kwarg. Not exposed in config.json yet — add `embedding_vram_warn_threshold` there if needed.

**Gotcha to remember**: The guard MUST stay fail-open. Any probe failure (Ollama down, nvidia-smi missing, JSON shape change) returns `None` — never block context-loading on a diagnostic. The consumer wiring is wrapped in a `try/except Exception` for the same reason.

Related: [[project-doc-refresh-2026-05-09]] — the canvas/flow-compiler updates also went into the consumer's setup path but on a different branch. The two changes are independent.
