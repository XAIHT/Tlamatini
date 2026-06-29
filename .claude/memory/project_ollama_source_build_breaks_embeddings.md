---
name: project_ollama_source_build_breaks_embeddings
description: "The \"llama-server binary not found\" / Nomic-Embed error is the broken C:\\Development\\ollama source build, NOT prompt size"
metadata: 
  node_type: memory
  type: project
  originSessionId: ae591c58-c2f4-41de-a82f-6e849f86e638
---
<!--
═══════════════════════════════════════════════════════════════════
  ✦  T L A M A T I N I  ✦   —   "one who knows"
  Created by  Angela López Mendoza   ·   @angelahack1
  Developer · Architect · Creator of Tlamatini
  Tlamatini Author Banner — do not remove (Angela's name is kept in every build)
═══════════════════════════════════════════════════════════════════
-->

2026-06-03: User reported a recurring Ollama error (`requested context size too large num_ctx=8192 n_ctx_train=2048`, then **`error starting llama-server: llama-server binary not found (checked: C:\Development\ollama\...)`**) and asked to **shorten prompt.pmt / Tlamatini.md** to fix it. That fix is structurally impossible — surfaced up front per [[feedback_state_constraints_upfront]].

**Real cause:** TWO Ollama servers run on this machine:
- ✅ Official install `C:\Users\angel\AppData\Local\Programs\Ollama\ollama.exe` (v0.24.0) — healthy, owns port 11434, full `lib/ollama` (cuda_v12/13 + ggml DLLs). This is what Tlamatini's `ollama_base_url: http://127.0.0.1:11434` talks to.
- ❌ Source checkout `C:\Development\ollama\ollama.exe` — a from-source Ollama git tree whose `llama-server`/runner was never compiled, so every model load there dies "binary not found". The pasted error's paths all start `C:\Development\ollama\...` → it's THIS build.

**Why prompts are irrelevant:** the failing model is `Nomic-Embed-Text:latest` — the RAG **embedding** model, which only embeds chunks/queries and never sees prompt.pmt/Tlamatini.md. The chat prompts go to `chained-model`/`unified_agent_model` = `kimi-k2.6:cloud` (a CLOUD model, not local Ollama). The `num_ctx 8192 > 2048` line is a benign clamp warning, not the failure.

**Fix applied (user chose "stop the source build"):** killed the `C:\Development\ollama` process; that took the whole Ollama down (official server + tray were tied to it), so relaunched `…\Programs\Ollama\ollama app.exe`. Verified: 11434 owned by the official exe + `/api/embeddings` for Nomic returns a real vector.

**If it recurs:** something auto-starts `C:\Development\ollama\ollama.exe` (boot order / a build script / startup) and it can race for 11434. Find & disable that launcher to make the fix permanent. Did NOT shorten prompt.pmt (60KB) / Tlamatini.md (13KB) — that remains an optional, separate token-cost optimization, unrelated to this error.
