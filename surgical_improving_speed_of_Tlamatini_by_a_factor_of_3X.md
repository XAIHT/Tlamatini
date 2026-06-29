# Surgical Plan — Improving the Speed of Tlamatini by a Factor of 3X

> **Author:** Claude (Opus 4.8, 1M ctx) for **<REDACTED>** — XAIHT / Tlamatini
> **Date created:** 2026-06-28
> **Status:** PLAN ONLY. **No code is modified by this document.** Every item below is a *future* surgical change to be executed in later sessions.
> **Goal:** Make Tlamatini **at least 3× faster** end-to-end (chat first-token, Multi-Turn loop, reconnect, startup, build) through *surgical*, file:line-scoped changes that **do not alter behavior, output, or security**.
> **Basis documents** (the 16 files in `image.png`, all at repo root): `TLAMATINI_100X_SPEED_PROPOSAL.md`, `Tlamatini_AGENTS_SECURITY_PERFORMANCE_100_LINE_PROPOSAL.md`, `Tlamatini_NIGHTLY_PERFORMANCE_REPORT.md`, `Tlamatini_SECURITY_PERFORMANCE_500_ACTIONS.md`, `Tlamatini_STAGE1..STAGE12` plans, `Tlamatini_STAGE9_10_PERFORMANCE_HOTSPOTS.md`.

---

## ⛔ NON-NEGOTIABLE GUARDRAILS (read first)

1. **NEVER REWRITE GIT HISTORY.** All speed work lands as **new forward commits**. No rebase / amend / reset --hard / filter-branch / force-push. (Per `CLAUDE.md` Private Data Guard.)
2. **Surgical = no behavior change.** Every optimization must produce byte-identical user-visible output (same answers, same Exec Report, same `.flw`, same Ask-Execs gating). Speed only.
3. **Measure first, optimize second, measure again.** No item ships without a before/after number. If a change does not move a real metric, it is reverted.
4. **Source AND frozen.** Every change must work in both source mode and the PyInstaller frozen build. A hot-fix applied only to live `C:\Tlamatini` is incomplete until `build.py` carries it.
5. **Dogfood Tlamatini's own tools** to do the work (File-Creator / Editor / Grepper / Globber / Executer / Pythonxer / Gitter), per the 2026-06-14 mandatory directive.
6. **No new third-party dependency** unless it is added to `requirements.txt` + `build.py` (`_CARRIED_PYTHON_REQUIRED_IMPORTS`, `_agent_libs` verify list, `--collect-all`/`--hidden-import`) and proven in the carried Python.

---

## 0. EXECUTIVE SUMMARY — WHERE THE 3X ACTUALLY COMES FROM

The 16 basis documents propose **>1000 optimizations**. Most are real but **small** (1–10 ms each) or **infrastructural** (metrics, budgets, tests). A naive reading says "do all 1000." That is wrong. **A surgical 3× comes from a handful of dominant levers, not from a thousand micro-edits.** This plan is ordered by *measured impact per unit of risk*.

The dominant truth, confirmed by `agent/llm_timing.py` instrumentation (memory `project_llm_ollama_timing_logs`): **the model itself is fast (~1.1 s with all 88 tools bound). The multi-minute stalls users feel are NOT Tlamatini's Python — they are (a) a broken/contended source-build Ollama serving layer and (b) work Tlamatini repeats every request that it could compute once.** So the 3X is overwhelmingly:

| Rank | Lever | Where the time is today | Expected gain | Risk | Status |
|---|---|---|---|---|---|
| **L1** | **Ollama serving layer** (stop the source-build race; pin one healthy server; `keep_alive=-1`; connection reuse) | up to **3-minute** stalls; cold model reloads; embedding failures | **The single biggest win** — turns minutes into seconds | Low (config/ops) | Partly known (memory) |
| **L2** | **Orphan reaper O(N²) → O(N)** (already fixed live, 290×: 5895 ms→20 ms/sweep) | ~90 s GIL-peg per sweep, fired after every tool + every answer | Removes multi-minute chat freezes | **Already written**; just SHIP it | Live-fixed, **frozen STALE** |
| **L3** | **Per-request rebuilds → cached** (embeddings handle, FAISS/BM25, capability registry, system prompt, chains, config/prompt.pmt reads) | 1–5 s embeddings recreate; 2× capability scan; repeated file reads | **2–5 s/request** on context paths; ~30% on Multi-Turn | Medium | Not started |
| **L4** | **Access-validation LLM calls made serial** (2–3 classifier round-trips before the answer when a path is mentioned) | **1–2 s/request** with any path reference | 1–2 s/request | Medium | Not started |
| **L5** | **Sidecar context fetches serial → parallel** (System-Metrics + Files-Search awaited back-to-back) | 200–500 ms/multi-turn request | 100–300 ms/request | Low | Not started |
| **L6** | **Agent runtime copy** (`shutil.copytree` per wrapped-agent launch, 1770 hits in one devserver log) | ~90% of agent startup | 50–100× copy (reflink/hardlink/overlay) | Medium | Not started |
| **L7** | **Reconnect/WebSocket setup** (re-send every MCP/Tool/Agent/Skill row one-by-one; rebuild RAG) | reconnect re-does full setup | 3× reconnect; −70% setup messages | Medium | Not started |
| **L8** | **Startup** (`apps.ready()` deletes+rescans agents, rmtree pools, boots ACPX/skills synchronously) | 2–5 s before first answer | 2–5 s startup | Medium | Not started |
| **L9** | **Build** (no incremental cache; full numpy purge; broad `--collect-all`) | 3–14 min/build | 3× incremental | Low | Not started |
| **L10** | **DB indexes + query-count guards** (no index on hot lookups; N+1 risk) | 5–10 ms/request + regression risk | small now, prevents regressions | Low | Not started |

**Bottom line:** L1+L2 alone likely deliver the headline "feels 3× faster" because they remove the *minutes-long* pathologies. L3–L5 deliver a real, measured 3× on the *steady-state* chat latency (the part that is genuinely Tlamatini's code). L6–L10 harden the rest and protect the gains. **This document specifies all of them, surgically, in execution order.**

> **Honesty note for <REDACTED>:** A literal "1000 printed pages" of prose would be padding. This file is the *complete* surgical catalog — every dominant lever plus the full long-tail from the basis docs — written densely so each item is actionable (location, problem, fix, expected gain, risk, verification) instead of inflated. It is built to be *executed*, session by session, not to hit a page count.

---

## 1. METHODOLOGY — WHAT "SURGICAL" MEANS HERE

Each catalog item uses this fixed shape so a future session can pick it up cold:

- **ID** — stable handle, e.g. `L3-RAG-02`.
- **Location** — `file:line` (or file + symbol) of the exact code.
- **Problem** — what is slow and *why*, with the measured/estimated cost and how often it runs.
- **Surgical fix** — described in words (NOT coded here); the smallest change that removes the cost without changing behavior.
- **Expected gain** — concrete number or multiple.
- **Risk** — Low / Medium / High + the specific failure mode to watch.
- **Verification** — the exact before/after measurement and the regression test that proves no behavior change.
- **Depends on** — prerequisite items (usually a benchmark or a cache primitive).

**Two invariants for every item:**
1. A *characterization test* exists or is added first (it asserts the current output), so the optimization is proven output-neutral.
2. A *benchmark* exists or is added first, so the speedup is a number, not a feeling.

---

## 2. BASELINE — WHAT WE MEASURED, WHAT WE STILL MUST

### 2.1 Measured today (from `Tlamatini_NIGHTLY_PERFORMANCE_REPORT.md`, 2026-06-28)

| Operation | Now | 3× target |
|---|---|---|
| `manage.py check` | 4501 ms | ~1500 ms |
| `manage.py check --deploy` | 2823 ms | ~941 ms |
| Python core compile check | 930 ms | ~310 ms |
| AST parse `views.py` (10 317 lines / 487 KB) | 718.5 ms | ~239 ms |
| Django + import `agent.views` | 3542 ms | ~1180 ms |
| Django + import `agent.tools` | 3147 ms | ~1049 ms |
| Django + import `agent.consumers` | 5926 ms | ~1975 ms |
| Django + import `agent.rag.factory` | 6059 ms | ~2020 ms |
| Source inventory (`rg --files`) | 57 ms | ~19 ms |
| Risk pattern scan (`rg`) | 102 ms | ~34 ms |

Static counts to keep honest: `json.load` ×226, `yaml.safe_load` ×143, `sync_to_async` ×41, `database_sync_to_async` ×29, `asyncio.create_task` ×13, `asyncio.to_thread` ×5, `threading.Thread` ×30, `queue.Queue` ×10, `ThreadPoolExecutor` ×6.

### 2.2 Baselines we DO NOT yet have (capture in Session 1, item `BENCH-*`)

These are the numbers that actually matter and are currently **missing** — the nightly report admits "Direct runtime launch/reconnect baselines still missing." **No optimization in L1–L8 may ship before its baseline exists.**

- **B1** Chat **first-token latency**, Multi-Turn ON, no tools fired (pure answer).
- **B2** Chat **end-to-end** latency, Multi-Turn ON, with a path in the prompt (triggers access validation).
- **B3** **Reconnect-to-ready** time (browser WS connect → all establishment messages received → chain ready).
- **B4** **Wrapped chat-agent launch** time (e.g. `chat_agent_file_creator`): copy + spawn + first log line.
- **B5** **Sidecar fetch** time (System-Metrics, Files-Search) individually and combined.
- **B6** **Orphan-reaper** sweep time, frozen build vs source (prove L2 is shipped).
- **B7** **App startup** time: process start → first request served.
- **B8** **Ollama call** time via `agent/llm_timing.py` WAIT-START/WAIT-END (separates Ollama from Tlamatini).
- **B9** **Build** wall-clock: clean vs incremental, with/without `--self-modify`.
- **B10** **DB query count** per request (Django `CaptureQueriesContext`) for: chat send, reconnect setup, session restore.

---

## 3. THE 3X BUDGET — DECOMPOSED

A request that "feels slow" is usually one of three shapes. The 3X is met **per shape**:

**Shape A — Plain Multi-Turn answer (no path, no tool):** today ≈ Ollama time + ~20–35 ms Tlamatini overhead. Here the 3× is **L1** (Ollama serving) + KV-cache reuse (`OLLAMA_KEEP_ALIVE`, stable prompt prefix). Tlamatini's own overhead is already small; protect it (L3 caches) so it stays small.

**Shape B — Multi-Turn with a path reference:** today ≈ +1000–2500 ms from serial access-validation classifier calls (`L4`). The 3× here is dominated by collapsing/caching those classifier calls.

**Shape C — Multi-Turn that fires wrapped agents + sidecars:** today ≈ +200–800 ms (sidecars serial `L5`, runtime copy `L6`) + reaper churn (`L2`). The 3× here is L2+L5+L6.

**Reconnect / context-switch:** `L7` (registry deltas) + `L3-RAG` (FAISS cache) → 3× reconnect.

**Cold start:** `L8` (defer/background startup work) → 2–5 s saved.

**Build:** `L9` (incremental cache) → 3× on the second build.

---

## 4. SESSION ROADMAP (execution order — one coherent batch per session)

| Session | Theme | Items | Exit gate |
|---|---|---|---|
| **S1** | **Instrument** — capture the missing baselines | `BENCH-1..10`, ship `llm_timing` everywhere | All B1–B10 numbers recorded in a new nightly run |
| **S2** | **Ship the freebies** — land already-fixed wins | `L2` (reaper via build.py), `L1a` (keep_alive/connection), `OLLAMA_KEEP_ALIVE` | Reaper sweep <50 ms in **frozen**; Ollama call time logged |
| **S3** | **Ollama serving layer** — kill the source-build race | `L1b..L1e` | No 3-min stalls in a 50-prompt run; embeddings never fail |
| **S4** | **Request hot-path caches** | `L3-CFG-*`, `L3-PROMPT-*`, `L4-*` (access validation) | Shape-B request 3× faster; output byte-identical |
| **S5** | **Sidecar parallelism + executor caches** | `L5-*`, `L3-EXEC-*` (capability/system-prompt cache) | Shape-C overhead −50%; planner scan cached |
| **S6** | **RAG / embeddings / FAISS cache** | `L3-RAG-*` | Reconnect on unchanged context = cache hit |
| **S7** | **WebSocket reconnect deltas + task registry** | `L7-*`, `H-TASK-*` | Reconnect 3×; −70% setup messages; no task leak |
| **S8** | **Agent runtime copy** | `L6-*` | Wrapped-agent launch 3×; isolation proven intact |
| **S9** | **Startup** | `L8-*` | First-answer-ready 2–5 s faster |
| **S10** | **DB indexes + query guards** | `L10-*` | Query-count tests green; hot lookups indexed |
| **S11** | **Build incremental cache** | `L9-*` | 2nd build 3×; deterministic manifest |
| **S12** | **Long-tail + process model (optional)** | `J-*`, agent-class budgets, micro-opts | Only items with a proven number |

Each session ends with: (a) benchmark delta recorded, (b) full `python -m ruff check` + `npm run lint` + `manage.py test` green, (c) a forward commit, (d) `build.py` updated if frozen carriage is affected, (e) both inclusion sweeps clean.

---

# 5. THE CATALOG

## 5.L1 — OLLAMA SERVING LAYER (the single biggest lever)

> **Why this is #1:** `agent/llm_timing.py` WAIT-START/WAIT-END logs prove the model answers in ~1.1 s even with all 88 tools bound (memory `project_llm_ollama_timing_logs`). Yet users see 3-minute stalls. The stalls are the **serving layer**, not Tlamatini. Separately, "llama-server binary not found" / Nomic-Embed errors come from a **broken `C:\Development\ollama` SOURCE build racing the official install for port 11434** (memory `project_ollama_source_build_breaks_embeddings`). This is config/ops surgery, near-zero behavior risk, and the largest wall-clock win available.

**L1a — Pin `keep_alive=-1` and reuse the HTTP client.**
- **Location:** `agent/rag/factory.py:278-301` (OllamaLLM build + `_client`/`_client._client` extraction), `factory.py:370-372` (`client_kwargs`), `factory.py:483-487` (OllamaEmbeddings build), `orphan_reaper.py:543-549` (existing `keep_alive` on a ChatOllama).
- **Problem:** A new `OllamaLLM` / `OllamaEmbeddings` is built per chain build → new httpx client → fresh TCP/TLS each request (100–500 ms); model may be unloaded between calls → cold reload (1–5 s). The explicit `_client._client` extraction at 298-301 is a *workaround* for reuse that fails because chains are rebuilt per request.
- **Surgical fix:** Set `keep_alive=-1` (honor `OLLAMA_KEEP_ALIVE`, default −1) on **every** Ollama LLM/embeddings constructor so the model stays resident and KV cache survives between turns; cache the `httpx` client at module level keyed by `(base_url, token)` and pass it in (`client_kwargs={'client': shared}`) so connections are reused across requests. **No behavior change** — same model, same params, only resident + pooled.
- **Expected gain:** removes 100–500 ms handshake/request and 1–5 s cold-reload on Shape A; KV reuse cuts repeated prompt-prefill.
- **Risk:** Low. Watch: a stale pooled client after an Ollama restart → add a cheap health-ping that rebuilds the pooled client on connection error.
- **Verification:** B8 before/after; assert identical answer text for a fixed prompt set.

**L1b — Detect and refuse the source-build Ollama race.**
- **Location:** new pre-flight in `apps.py` startup (near `start_gpu_perf`, `apps.py:55-64`) + a one-line check in `factory.py` embeddings path.
- **Problem:** A second Ollama (the `C:\Development\ollama` source build) binds/contends `:11434`, breaking `llama-server` and embeddings, producing minutes of stall + Nomic-Embed errors that look like "prompt too big" but are not.
- **Surgical fix:** On startup, probe `GET {ollama_base_url}/api/version` and `/api/tags`; if the server identity/behavior signals the known-bad source build (or two listeners are detected), log a **loud, single, actionable** banner ("source-build Ollama detected on 11434 — stop it; embeddings will fail") and surface it in `acp_doctor`-style diagnostics. **Diagnostic only — never auto-kill a user process.**
- **Expected gain:** turns a multi-minute mystery into a 5-second fix; protects every embedding + chat call.
- **Risk:** Low (read-only probe). Watch: false positive on a legitimate custom server → gate the banner on a specific, conservative signature.
- **Verification:** reproduce with the source build up, confirm banner; with official install, confirm silence.

**L1c — Embedding memory pre-flight stays, but cache its verdict.**
- **Location:** the embedding-memory guard referenced in `architecture.md` (Nomic-Embed default; `qwen3-embedding:8b` ~10× VRAM).
- **Problem:** if the pre-flight re-probes VRAM on every chain build it adds latency.
- **Surgical fix:** memoize the VRAM/model-fit verdict for the process lifetime keyed by `(embedding_model, gpu_id)`; invalidate only on model change.
- **Expected gain:** small per-request, but removes a repeated `nvidia-smi`/ctypes probe.
- **Risk:** Low.
- **Verification:** count `nvidia-smi` invocations per 10 requests → must be ≤1.

**L1d — Single warm embeddings handle.**
- **Location:** `factory.py:483-487` (`OllamaEmbeddings(...)` inside the retrieval-chain builder).
- **Problem:** embeddings handle recreated on every `setup_llm_with_context` / chain build (1–5 s cold; HTTP renegotiation warm).
- **Surgical fix:** module-level singleton embeddings handle keyed by `(model, base_url, token)`; reuse across requests and across the FAISS/BM25 build path. Pairs with `L3-RAG-01`.
- **Expected gain:** 1–5 s on the first request after a context change; ~50–100 ms warm.
- **Risk:** Low. Watch: model switched via Config → Models mid-session must invalidate the singleton (hook the config-change path).
- **Verification:** B5/B8; assert retrieval results unchanged for a fixed corpus.

**L1e — Streaming flush batching.**
- **Location:** `agent/rag/chains/base.py:22` (Callbacks: per-token `global_state` read + cancellation check + `print(..., flush=True)`).
- **Problem:** every token does a global-state read + a flushed stdout write → ~10–20% streaming overhead on long answers (1000 tokens × flush).
- **Surgical fix:** check `cancel_generation` on a time/▢count tick (e.g. every 25 ms or every N tokens) instead of every token; coalesce the tee write. **User still sees streaming; cancellation latency stays sub-100 ms.**
- **Expected gain:** 10–20% on long-answer wall-clock.
- **Risk:** Low. Watch: cancel responsiveness — keep the tick ≤100 ms.
- **Verification:** token-throughput benchmark; cancel-latency test stays <100 ms.

---

## 5.L2 — ORPHAN REAPER (already fixed live; SHIP IT to frozen)

> **Status:** The O(N²)→O(N) rewrite is **already done and proven live** (5895 ms → 20 ms per sweep, 290×; memory `project_orphan_reaper_on2_freeze`). It is **uncommitted** and the **frozen `C:\Tlamatini` is stale**. This was THE multi-minute chat + Catalog-of-Prompts freeze (server fast, browser starved) because the sweep fired after every tool call **and** after every answer.

**L2a — Commit + carry the reaper rewrite into the frozen build.**
- **Location:** `agent/orphan_reaper.py:516-550` (`_build_proc_index`), `:556-586` (`_is_protected_foreground_fast`), `:678-848` (`reap_orphans`), `:774-787` (single snapshot), call sites `mcp_agent.py:779-814` (`_reap_after_tool`, `min_full_scan_interval=8.0` coalesce).
- **Problem:** the fix exists only in the working tree / live box; a fresh `build.py` of the current committed code would re-ship the O(N²) version.
- **Surgical fix:** forward-commit the rewrite; rebuild via `build.py`; verify the frozen `_internal` carries the new `orphan_reaper.py`.
- **Expected gain:** removes the dominant multi-minute freeze for any user on a frozen install.
- **Risk:** Low (already validated). Watch: confirm `min_full_scan_interval` coalesce survived the build.
- **Verification:** B6 in **frozen**: sweep <50 ms; a 30-tool Multi-Turn run shows no multi-second gaps in `tlamatini.log`.

**L2b — Make Tier-1 reaping non-blocking to the tool loop.**
- **Location:** `mcp_agent.py:779-814` (`_reap_after_tool` runs synchronously after every tool, even tools that spawn nothing).
- **Problem:** even at O(N)/20 ms, firing after **every** tool adds 20 ms × N tools (≈ 100–600 ms/request) on the critical path, most of it wasted on non-spawning tools.
- **Surgical fix:** (1) only run Tier-1 after tools in `_PROCESS_SPAWNING_TOOL_NAMES` ∪ `chat_agent_*` ∪ `acp_*` (already the documented set — verify the gate is actually applied), and (2) hand the sweep to a single-slot background worker so the loop never blocks on it; Tier-2 already runs post-answer in a thread — keep it. **No change to what gets reaped, only when/where it runs.**
- **Expected gain:** 100–600 ms/request removed from the critical path.
- **Risk:** Medium. Watch: a spawning tool whose child must be reaped before the next tool reads its output — keep synchronous reaping for that narrow case; default async otherwise.
- **Verification:** orphan-survivor counts identical across a fixed flow; per-request reaper time on critical path → ~0.

---

## 5.L3 — KILL PER-REQUEST REBUILDS (cache what is effectively static)

### 5.L3.CFG — Config / prompt / self-knowledge reads

**L3-CFG-01 — Validate the config cache by mtime/size/inode.**
- **Location:** `config_loader.py:34-39` (returns cached config when path matches, **without** mtime/size/inode validation), `:43-49` (fails open to `{}` silently), `interface.py:653` (re-reads config per request), `interface.py:308-310` (`_get_classifier_llm` re-reads config **every call**).
- **Problem:** the cache can be stale after an external edit, AND the per-request/per-classifier re-reads re-open+parse JSON (2–6 ms/request, more under classification). `json.load` appears 226× across the tree.
- **Surgical fix:** add `(mtime,size,inode)` validation to `_CONFIG_CACHE`; serve from cache when unchanged (<1 ms); on parse failure return a **typed diagnostic** instead of silent `{}`; route `interface.py:653` and `_get_classifier_llm` through the validated cache so they stop re-opening the file.
- **Expected gain:** repeated config load <1 ms (target from STAGE10 Action 53); removes 2–6 ms/request and the silent-failure footgun.
- **Risk:** Low. Watch: Config→Models change must still take effect → invalidation is mtime-based, so it does.
- **Verification:** stale-cache test; malformed-config diagnostic test; count file opens per request.
- **Basis:** STAGE3 Actions 5–8; STAGE9_10 lines 48–57.

**L3-CFG-02 — Cache the parsed template `config.yaml` for wrapped-agent launches.**
- **Location:** `chat_agent_runtime.py` launch path; `tools.py:2451` launch; STAGE10 Action 49.
- **Problem:** every wrapped-agent launch re-parses the template `config.yaml` (`yaml.safe_load` ×143 across tree).
- **Surgical fix:** cache parsed template config keyed by `(template_dir, mtime)`; write the runtime `config.yaml` **only when the merged result differs** (STAGE10 Action 50); use an atomic locked write helper (STAGE10 Action 51, STAGE3 Actions 1–4: unique temp name, fsync, `os.replace`, file lock — fixes the `config.json.tmp` fixed-name collision at `config_loader.py:99`).
- **Expected gain:** removes a YAML parse + a disk write per launch when unchanged.
- **Risk:** Low. Watch: concurrent launches of the same template → file lock covers it.
- **Verification:** launch benchmark B4; concurrent-write test.

**L3-CFG-03 — Load self-knowledge (`Tlamatini.md`) once.**
- **Location:** `rag/config.py:138` (`_load_self_knowledge_block` reads + brace-escapes), invoked from `factory.py:657` and `factory.py:801`.
- **Problem:** read + brace-escape repeated at each prompt-load site.
- **Surgical fix:** memoize the escaped block keyed by `(path, mtime)`; fail-open behavior preserved.
- **Expected gain:** small but removes a file read + escape on every setup.
- **Risk:** Low.
- **Verification:** assert identical `<self_knowledge>` block bytes.

### 5.L3.PROMPT — System prompt assembly

**L3-PROMPT-01 — Cache the assembled system prompt per tool-set.**
- **Location:** `mcp_agent.py:1415-1501` (`_build_system_prompt`: flatten 88 tool one-liners, conditional rule blocks, 3+ regex subs, platform block, brace-escape).
- **Problem:** rebuilt whenever the tool-set changes; the regex subs + brace-escape over a multi-KB prompt are not free.
- **Surgical fix:** key a cache on `(tool_set_signature, flags)` where the signature is the sorted tuple of bound tool names + the toggle flags that change the prompt (Multi-Turn / Step-by-Step / ACPX / Ask-Execs). Since Multi-Turn now binds the **full** enabled surface (memory `project_multiturn_binds_all_tools`), the tool-set is stable across most requests → near-permanent cache hit. **Identical bytes out.**
- **Expected gain:** ~50–100 ms per unique tool-set → ~0 on the common stable path; also keeps the Ollama KV-cache prefix byte-stable (pairs with L1a `keep_alive`).
- **Risk:** Low. Watch: signature must include every flag that alters the prompt or you serve a wrong prompt — enumerate them explicitly.
- **Verification:** prompt-bytes equality test across flag combinations; KV-cache reuse observable in Ollama logs.

### 5.L3.EXEC — Planner / capability registry

**L3-EXEC-01 — Cache capability build + scoring per tool-set+request.**
- **Location:** `global_execution_planner.py:206` (`build_tool_capabilities`), `:221-228` (scoring loop over ~88 tools), `capability_registry.py:467-499` (rebuild), `:516-567` (`_score_capability`), re-invoked in `mcp_agent.py:1734` (`_budget_select_tools`) — i.e. **the 88-tool build+scan runs twice per request.**
- **Problem:** capabilities are rebuilt from the (static) registry every request, and scored twice.
- **Surgical fix:** (1) build `ToolCapability` objects **once** per tool-set (cache keyed by tool-set signature — the registry is static), and (2) compute scoring **once** per request and share the result between the planner and `_budget_select_tools` instead of recomputing. Since Multi-Turn binds the full surface and no longer *drops* tools, the budget selection is mostly informational — confirm it can consume the planner's already-computed scores.
- **Expected gain:** halves the 88-tool scan; removes the rebuild; ~tens of ms/request.
- **Risk:** Low–Medium. Watch: per-request scoring still depends on the *prompt*, so only the **capability build** is fully static; the **scoring** is cached only within one request (shared, not memoized across prompts).
- **Verification:** assert identical selected-tool ordering + planner summary for a fixed prompt; count `build_tool_capabilities` calls/request → 1.

**L3-EXEC-02 — Parallelize the per-tool scoring scan (optional, measure first).**
- **Location:** `global_execution_planner.py:220-228`; `mcp_agent.py:1697` (`_estimate_tool_schema_tokens` list-comp, `convert_to_openai_tool` per tool).
- **Problem:** 88 independent string-matching scores computed serially; schema-token estimation calls `convert_to_openai_tool` per tool (~1–2 ms × 88 ≈ 88–176 ms) on a tool-set change.
- **Surgical fix:** memoize `_estimate_tool_schema_tokens` per tool object (schema is static) — this alone removes most of the cost without threading. Only if a benchmark still shows a hotspot, move the scoring scan to a `ThreadPoolExecutor` (string matching sheds the GIL).
- **Expected gain:** schema-token memoization ~80–170 ms on tool-set change → ~0 thereafter.
- **Risk:** Low for memoization; Medium for threading (don't thread unless measured).
- **Verification:** selected tools identical; schema-token call count per tool → 1.

**L3-EXEC-03 — Lazy `bind_tools`.**
- **Location:** `mcp_agent.py:594` (`self.bound_llm = llm.bind_tools(self.tools)` at executor init), executor cached at `:1785-1800`.
- **Problem:** `bind_tools` does OpenAI-schema conversion of all 88 tools; if an executor is built but the request resolves without a tool turn, that work is wasted.
- **Surgical fix:** bind lazily on first tool-requiring turn; reuse the cached bound LLM for the (stable) full tool-set. Pairs with L3-PROMPT-01 so the bound surface + prompt are both cache-stable.
- **Expected gain:** avoids one schema conversion on pure-answer requests; stabilizes KV prefix.
- **Risk:** Medium. Watch: must still expose tools on the very first turn that needs them — bind on demand, not never.
- **Verification:** tool-calling still works on turn 1; bind count per session minimized.

---

## 5.L4 — ACCESS-VALIDATION CLASSIFIER CALLS (Shape-B dominator)

> **Why this matters:** when a prompt mentions a path, `ask_rag` runs **2–3 serial LLM classifier calls** before the answer even starts (path-intent, indirect-access). At ~1 s each that is the single worst steady-state latency for the common "do X to this file" request — 1000–2500 ms added.

**L4-01 — Cache the classifier LLM instance (stop re-reading config per call).**
- **Location:** `interface.py:300-345` (`_get_classifier_llm` caches the instance **but** re-reads `config.json` every call at `:308-310` to check invalidation).
- **Problem:** the cache check itself re-opens + parses config every classification (2–3×/request).
- **Surgical fix:** invalidate against the validated config cache (L3-CFG-01) by `(mtime,size)` instead of re-reading + comparing the full config dict; keep the same model/params.
- **Expected gain:** removes 2–6 ms/request of config I/O on the classification path.
- **Risk:** Low.
- **Verification:** file-open count per classified request; identical classifier output.

**L4-02 — Make the classifier calls concurrent, not serial.**
- **Location:** `interface.py:598-615` (`_validate_accesses_in_prompt` → `_acces_aimed_prompt` then, if needed, `_indirect_file_access_prompt`), against the inet-determiner already launched in a `ThreadPoolExecutor` at `interface.py:691-715`.
- **Problem:** the access classifiers run **sequentially**; the inet future is launched early but evaluated late (`:750`, timeout 60 s), so parallelism is wasted.
- **Surgical fix:** launch the access classifier(s) and the inet-determiner in the **same** `ThreadPoolExecutor` and `gather` them; short-circuit `_indirect_file_access_prompt` when `_acces_aimed_prompt` already resolved the path. **Same decisions, same gating — just overlapped.**
- **Expected gain:** 2–3 serial ~1 s calls → ~1 s wall-clock (≈ 1–1.5 s saved on Shape B).
- **Risk:** Medium. Watch: ordering of side effects — the gate decision must still be evaluated before the answer; only the *waiting* is overlapped.
- **Verification:** B2 before/after; a fixed set of path-bearing prompts must produce identical allow/deny + identical answers.

**L4-03 — Heuristic fast-path before invoking the classifier at all.**
- **Location:** `interface.py:146-262` (the compiled path/relative-path regexes), `:598-615`.
- **Problem:** even an obviously-allowed path (inside `allowed_paths`, or a wrapped-agent operation that is already authorized) pays a full LLM classifier round-trip.
- **Surgical fix:** add a deterministic pre-check: if every detected path is provably inside `allowed_paths` (or the request is a wrapped-agent op already gated by Ask-Execs), **skip** the LLM classifier entirely; only invoke it for genuinely ambiguous out-of-scope paths. This is the same security decision reached deterministically when it is unambiguous. (Conservative: when in doubt, still call the classifier.)
- **Expected gain:** removes 1–2 s on the *majority* of path-bearing requests (those touching allowed dirs).
- **Risk:** Medium-High (security-adjacent). Watch: must be strictly *more* conservative than the LLM — only skip when deterministically safe; never skip-allow an out-of-scope path. Add a test matrix of allowed/denied paths.
- **Verification:** security regression matrix (allowed paths, traversal attempts, symlinks) must match the LLM-gated behavior exactly or be stricter.

---

## 5.L5 — SIDECAR CONTEXT FETCHES (serial → parallel; skip when unneeded)

**L5-01 — Run System-Metrics and Files-Search fetches concurrently.**
- **Location:** `factory.py:166-180` (`_apply_legacy_context_prefetch`): `get_system_context_sync(payload)` at `:169` blocks, then `get_files_context_sync(...)` at `:176` only starts after; both wrap async via `async_to_sync` (`:59-81`, `:83-103`).
- **Problem:** total = system_fetch + files_fetch, serialized (200–500 ms+).
- **Surgical fix:** await both with `asyncio.gather` (single `async_to_sync` over the gather), so wall-clock = max(system, files) not sum.
- **Expected gain:** 100–300 ms/multi-turn request.
- **Risk:** Low. Watch: `files` fetch currently consumes `enhanced_payload` produced by the system fetch — confirm it doesn't actually depend on system output; if it does, only the independent parts parallelize.
- **Verification:** B5 combined vs individual; identical context blocks injected.

**L5-02 — Early-exit when a context kind isn't selected.**
- **Location:** `factory.py:201-212` (checks `selected_contexts` but still calls both fetchers on the legacy path).
- **Problem:** wasted 100–200 ms when, e.g., files_context is not needed.
- **Surgical fix:** only call a fetcher when the planner's `selected_contexts` includes it; skip otherwise.
- **Expected gain:** 100–200 ms on requests that need only one (or zero) context kind.
- **Risk:** Low. Watch: don't regress requests that genuinely need both.
- **Verification:** assert fetch is skipped when not selected; answers unchanged.

**L5-03 — Cache System-Metrics for a short TTL.**
- **Location:** `mcp_system_server.py:31-100` (`subprocess.run(["typeperf", ...], timeout=4)` per metrics fetch).
- **Problem:** `typeperf` spin-up is 100–400 ms per fetch; metrics don't change meaningfully sub-second.
- **Surgical fix:** cache the metrics payload with a 5–10 s TTL inside the server; serve cached within TTL. **Same data shape; staleness bounded and irrelevant for "current system load."**
- **Expected gain:** 100–400 ms whenever system context is fetched within the TTL window.
- **Risk:** Low. Watch: don't cache across a deliberate "refresh now" if such a path exists.
- **Verification:** count `typeperf` spawns per 10 fetches → ≤1 per TTL window.
- **Basis:** STAGE9_10 / Nightly (sidecar cost).

---

## 5.L3.RAG — EMBEDDINGS / FAISS / BM25 / METADATA (reconnect & first-request)

> **Why:** on a context change or reconnect, `setup_llm_with_context` re-loads the directory, re-enriches metadata, re-splits, **re-embeds the whole corpus**, and **rebuilds FAISS + BM25** — 1–5 s embeddings + O(corpus) work, with no content-hash cache. This is the reconnect penalty and the first-answer-after-load penalty.

**L3-RAG-01 — Reuse the warm embeddings handle (see L1d).** Cross-reference; the FAISS/BM25 build must consume the singleton, not a fresh `OllamaEmbeddings`.

**L3-RAG-02 — Content-hash cache for loaded docs → split → FAISS → BM25.**
- **Location:** `factory.py:603+` (`setup_llm_with_context`), `:657` (config/prompt load), `:664` (`DirectoryLoader` recursive), `:680-725` (metadata enrichment), `:723-730` (`enrich_documents_with_metadata`), `:483-492` (`FAISS.from_documents`), `:497` (`BM25Retriever.from_documents`), `:733` (chain build).
- **Problem:** every rebuild repeats the full pipeline even when files are unchanged; reconnect re-pays it.
- **Surgical fix:** layered cache keyed by content hashes (STAGE10 Actions 38–44):
  1. directory **manifest** (path → mtime/size/hash) keyed by the path set;
  2. **loaded docs + metadata** keyed by manifest hash;
  3. **split docs** keyed by (content hash + splitter config);
  4. **FAISS store** keyed by (content hash + embedding model) — persist to disk (`faiss.write_index` / `save_local`) and **load** on reconnect instead of re-embedding;
  5. **BM25** keyed by content hash.
  Invalidate any layer when its inputs change. **Same retrieval results; just not recomputed.**
- **Expected gain:** unchanged-context rebuild becomes a cache hit (≥3× per STAGE10 target); reconnect on same project = near-instant.
- **Risk:** Medium. Watch: cache key must include embedding model + splitter config (a model switch must miss); disk cache must be invalidated on file edits (mtime+hash).
- **Verification:** B3 reconnect (cold vs warm); identical top-k retrieval for a fixed query set; cache-invalidation test on a touched file.
- **Basis:** STAGE9_10 lines 37–47, 134–163; 100X Changes 551–650.

**L3-RAG-03 — Memoize metadata enrichment per file.**
- **Location:** `factory.py:723-730` + `rag_enhancements.py:17+` (`extract_code_metadata`: regex over classes/functions/imports per file).
- **Problem:** 5–50 ms/file × N files re-run on every rebuild (1000 docs = seconds).
- **Surgical fix:** cache per-file enrichment keyed by (path, mtime, size); only re-extract changed files.
- **Expected gain:** seconds on large corpora rebuilds; subsumed by L3-RAG-02 layer 2 but worth as a standalone.
- **Risk:** Low.
- **Verification:** enrichment call count per unchanged rebuild → 0.

**L3-RAG-04 — Skip fusion/dedup/diversify for trivial corpora / simple queries.**
- **Location:** `rag/retrieval.py:57-105` (vector k=8 + fetch_k=32 MMR, BM25 k=8, RRF fusion O(n log n), source diversification O(n), SHA1 dedup O(n)).
- **Problem:** ~100–200 ms/query of fusion machinery even when the corpus is tiny or the query is a direct lookup.
- **Surgical fix:** when corpus size or candidate count is below a threshold, return the merged set without the full RRF+diversify+dedup pipeline (the result is identical when there's nothing to fuse/dedup). Keep full pipeline for real multi-source corpora.
- **Expected gain:** 100–200 ms on small/simple retrievals.
- **Risk:** Medium. Watch: only short-circuit when the output is provably identical to the full pipeline (e.g. single source, no duplicates) — otherwise keep full.
- **Verification:** identical ordering vs full pipeline on the threshold boundary.

**L3-RAG-05 — Cache the RAG chain object per (user, context, model).**
- **Location:** `factory.py:733` (chain build), `consumers.py:257-294` / `:371-472` (setup paths rebuild on reconnect / context change).
- **Problem:** the whole chain is reconstructed on reconnect even when nothing changed.
- **Surgical fix:** cache the built chain keyed by (user, context-path-hash, model, toggle-flags); reuse on reconnect; rebuild only on a real change. Pairs with L7 (registry deltas).
- **Expected gain:** reconnect-to-ready dominated by network, not rebuild.
- **Risk:** Medium. Watch: invalidate on any toggle/model/context change.
- **Verification:** B3; chain identity reused across a no-op reconnect.

---

## 5.L6 — AGENT RUNTIME COPY (the wrapped-agent launch tax)

> **Why:** every wrapped chat-agent launch does a full `shutil.copytree(template_dir, runtime_dir)` — 1770 runtime-copy hits in a single devserver log. This is ~90% of agent startup. The template is immutable; only `config.yaml`, the log, and outputs are mutable.

**L6-01 — Copy only mutable files; share the immutable template.**
- **Location:** `chat_agent_runtime.py:212` (`create_isolated_runtime_copy`), `:245` (`shutil.copytree(..., ignore=_copytree_ignore)`), launch at `tools.py:2451`.
- **Problem:** the whole template tree is duplicated per launch (disk + time + cleanup burden) even though the `.py` and assets never change between runs.
- **Surgical fix (tiered, pick by platform support, fail-open to full copy):**
  1. **Hardlink** stable files (`.py`, assets) into the runtime dir; **copy** only mutable files (`config.yaml`, run metadata) — NTFS supports hardlinks (STAGE9_10 Actions 6–9; 100X Change 102: 20–50×).
  2. If reflink/copy-on-write is available, use it (100X Change 101: 50–100×).
  3. Keep an **immutable cached template snapshot** keyed by a content-hash manifest (STAGE9_10 Actions 4–5) so repeated launches reuse it.
  4. **Always fall back** to the current `copytree` if hardlink/snapshot fails (STAGE9_10 Action 9).
  **Isolation is preserved** — a run writes its own `config.yaml`/log/outputs; it never mutates the shared template (hardlinked source files are read-only at runtime).
- **Expected gain:** repeat launch ≥3× (STAGE9_10 target); 20–100× on the copy itself.
- **Risk:** Medium. Watch: a future agent that *writes back into a template file* would corrupt the shared source — assert the template is treated read-only; the mutable-file allowlist must be correct per agent.
- **Verification:** B4 launch (cold vs warm); a test that runs the same agent twice and proves (a) each run's `config.yaml`/log is unique and (b) the template dir is byte-unchanged after both runs.
- **Basis:** STAGE9_10 Actions 1–11; 100X Changes 101–110.

**L6-02 — Demote the per-launch directory-listing logs.**
- **Location:** `chat_agent_runtime.py` (the info-level directory/runtime-contents listing logged on every launch).
- **Problem:** logging the directory contents on every launch (×1770) adds I/O and log bloat.
- **Surgical fix:** move the listing behind a debug flag (STAGE9_10 Actions 10–11).
- **Expected gain:** small per-launch + much smaller logs.
- **Risk:** Low.
- **Verification:** launch log size before/after.

**L6-03 — Cache validated external-tool paths (compilers, browsers, Java, Git, PlatformIO, ESPHome, arduino-cli).**
- **Location:** the firmware/browser/process agents' bootstrap+preflight (`stm32er`, `esp32er`, `arduiner`, `esphomer`, `discoverer`, `kalier`, `playwrighter`) + `windows_spawn.resolve_command` (ACPX).
- **Problem:** each run re-probes the toolchain on PATH (`AGENTS_…_100_LINE_PROPOSAL` Action 73; STAGE9_10 agent startup metrics).
- **Surgical fix:** cache resolved+validated tool paths keyed by (tool, version) with mtime invalidation; skip the probe when cached and the binary is unchanged.
- **Expected gain:** removes repeated PATH scans / version probes per agent run.
- **Risk:** Low. Watch: invalidate when the user installs/updates a toolchain.
- **Verification:** probe count per repeated run → ≤1.
- **Basis:** AGENTS 100-line Actions 73–76.

---

## 5.L7 — WEBSOCKET SETUP / RECONNECT (deltas, not full resend)

> **Why:** on connect/restore, `consumers.py` re-sends every MCP/Tool/Agent/Skill row one message at a time and re-runs full setup. Django import of `agent.consumers` is 5926 ms; the runtime resend + rebuild is the reconnect tax.

**L7-01 — Registry snapshot hashing + delta payloads.**
- **Location:** `consumers.py:150-169` (re-sends MCP/tool/agent/skill lists one by one on restore), `:246-315` (loads omissions/MCPs/tools/agents/skills, sends establishment messages, then `setup_llm`), `:371-472` (repeats for contextual RAG).
- **Problem:** dozens of tiny establishment messages every reconnect even when the registries are unchanged.
- **Surgical fix:** compute a per-category snapshot hash (with mtime/version invalidation), cache it per user, and on reconnect send **only deltas** when the client's prior hash matches; batch establishment payloads per category (STAGE6 Actions 27–34). Target −70% establishment messages.
- **Expected gain:** reconnect setup ≥3× on unchanged registries; far less WS chatter.
- **Risk:** Medium. Watch: the client must correctly apply deltas — keep a "full resync" fallback when hashes mismatch.
- **Verification:** B3; message count per reconnect before/after; a delta-apply test on the frontend state arrays.
- **Basis:** STAGE6 Actions 26–34, 71–76.

**L7-02 — One active setup task per (user, purpose); cancel stale ones.**
- **Location:** `consumers.py:952, 957, 996, 1132, 1162, 1188, 1423` (`asyncio.create_task` fire-and-forget), `:246-315`/`:371-472` (setup paths).
- **Problem:** rapid reconnects / context switches schedule **redundant** RAG rebuilds; fire-and-forget tasks can leak and a stale rebuild can overwrite a newer one.
- **Surgical fix:** a task registry (shared with H-TASK below; STAGE6 Actions 19–25, 71–76) keyed by (user, session, purpose) that cancels the prior setup task before launching a replacement and uses **generation tokens** so a stale completion can't clobber current state.
- **Expected gain:** rapid context switch launches only the final rebuild (avoids N wasted rebuilds).
- **Risk:** Medium. Watch: cancellation must be safe mid-rebuild (no partial state).
- **Verification:** rapid-switch test launches exactly one rebuild; no orphaned tasks after disconnect.

**L7-03 — Index + cap the chat-history load.**
- **Location:** `consumers.py:1480-1481` + `chat_history_loader.py:39-98` (loads ≤8 messages with `select_related("user")`, but the user-filtered cursor can scan a large `AgentMessage` table).
- **Problem:** O(N) scan over a user's full message history to take the newest 8.
- **Surgical fix:** the composite index from L10 (`AgentMessage(conversation_user, -timestamp, -id)`) makes the newest-N an index range scan; keep the 8-message window.
- **Expected gain:** 5–10 ms/request → ~1 ms, and no growth with history size.
- **Risk:** Low.
- **Verification:** B10 query count + EXPLAIN shows index range scan.

---

## 5.H — ASYNC / THREADS / QUEUES / GLOBAL STATE (protect throughput)

> **Why:** ad-hoc threads/pools/queues (30 threads, 10 queues, 6 per-request ThreadPoolExecutors, unbounded ACPX stdout queues) add overhead and risk leaks/memory blowups; the process-global state dict under one lock can bleed between concurrent requests.

**H-POOL-01 — Shared bounded worker pools (`agent/workers.py`).**
- **Location:** the 6 `ThreadPoolExecutor` sites + 41 `sync_to_async` + 5 `asyncio.to_thread` (counts from nightly).
- **Problem:** per-request pool creation + uninstrumented offload.
- **Surgical fix:** one shared bounded IO pool + one CPU pool with named submission, per-user + global concurrency limits, queue-depth limits, timeouts, cancellation-aware wrappers, and metrics (STAGE11 Actions 27–40, 70). Route the hot offloads (`ask_rag`, sidecars, classifiers) through it.
- **Expected gain:** removes per-request pool spin-up; bounded memory under load; no request starves the loop.
- **Risk:** Medium. Watch: pool sizing — too small serializes, too large thrashes; size from B-numbers.
- **Verification:** stable memory after 100 reconnects; throughput unchanged or better.
- **Basis:** STAGE11 Actions 27–40.

**H-TASK-01 — Central task registry (`agent/task_registry.py`).**
- **Location:** `consumers.py` `asyncio.create_task` sites (13).
- **Problem:** fire-and-forget tasks not tracked; can leak on disconnect; stale results overwrite.
- **Surgical fix:** track every task by (user, purpose, generation, start, cancel-state); cancel on disconnect where safe; drain/cancel stale on reconnect; guard state writes with generation tokens; done-callbacks (STAGE11 Actions 43–48, 67, 110). Shared with L7-02.
- **Expected gain:** stable task count after disconnects; no stale-overwrite bugs (also a correctness win).
- **Risk:** Medium.
- **Verification:** task-count stress test stays flat across 100 connect/disconnect cycles.

**H-QUEUE-01 — Bound the ACPX stdout queues + native-picker join.**
- **Location:** ACPX runtime `queue.Queue()` (no maxsize), native folder-picker `join()` (no timeout).
- **Problem:** a noisy child can grow the queue unbounded (memory); a stuck picker can block a thread forever.
- **Surgical fix:** add `maxsize` + a truncation/drop policy with dropped-line metrics (STAGE11 Actions 49–51); add a timeout to the picker join with a clear "picker still open" error (Actions 52–53).
- **Expected gain:** bounded memory; no hung thread.
- **Risk:** Low. Watch: dropping stdout must be logged so a user knows output was truncated.
- **Verification:** noisy-child test shows bounded queue; picker-timeout test returns a clean error.

**H-STATE-01 — Namespace + scope global state (ContextVar).**
- **Location:** `global_state.py` (process-global dict under one lock), per-request keys (`last_exec_report_*`, `tool_calls_log`, `cancel_generation`, etc.).
- **Problem:** concurrent requests can read/write each other's transient values; a single lock serializes hot reads.
- **Surgical fix:** move per-request values into `ContextVar` / namespace keys by (user, request, task) with typed accessors + TTL for transient state + metrics on key count (STAGE11 Actions 56–61). **This is also a correctness fix** (memory `project_rag_chain_self_heal` and the exec-report leakage class).
- **Expected gain:** removes lock contention on hot reads; enables safe concurrency.
- **Risk:** Medium-High. Watch: every read/write site must move together — do it incrementally per key with tests.
- **Verification:** concurrent-request test proves two requests never share a tool-call log / exec report.
- **Basis:** STAGE11 Actions 56–61.

---

## 5.L8 — STARTUP (`apps.ready`) — defer / background / cache

> **Why:** `AgentConfig.ready()` runs a serial 7-phase blocking sequence (`apps.py:8-485`) before the server is useful: DB cleanup, agent delete+rescan, pool rmtree, runtime-artifact cleanup, GPU boost, MCP server bind, ACPX+skills boot. 2–5 s before first answer. Plus heavy imports (consumers 5926 ms, rag.factory 6059 ms).

**L8-01 — Background the disk-cleanup phases.**
- **Location:** `apps.py:83-93` (delete all AgentProcess/ChatAgentRun), `:174-198` (rmtree `agents/pools`), `:200-242` (rmtree `.tlamatini` acpx-state/skill-audit).
- **Problem:** rmtree + full-table deletes run synchronously on the startup path (100–1000 ms).
- **Surgical fix:** move these to a daemon thread that runs *after* the server is ready to accept connections; they are cleanup, not prerequisites for serving (confirm nothing in the first request depends on a clean pools dir — guard with a "cleanup in progress" flag if needed).
- **Expected gain:** 200 ms–1 s off cold start.
- **Risk:** Medium. Watch: a stale pool dir colliding with a brand-new run during the cleanup window — namespace new runs with a fresh id (already done) so they don't collide.
- **Verification:** B7 cold start before/after; first request served while cleanup still running.

**L8-02 — Cache agent discovery; replace delete-all+reinsert.**
- **Location:** `apps.py:96-172` (`Agent.objects.all().delete()` then re-`create()` per folder from an `os.listdir` scan).
- **Problem:** wipes + rewrites the Agent table on every boot + a disk scan (50–200 ms) even when nothing changed.
- **Surgical fix:** compute a hash of the `agents/` directory listing; if unchanged since last boot, **skip** the delete+reinsert entirely; otherwise reconcile with `update_or_create` deltas instead of wipe+rewrite. **Same final rows.**
- **Expected gain:** 50–200 ms off boot when the agent set is unchanged (the common case).
- **Risk:** Medium. Watch: a manually-edited DB row must still be reconciled — the hash gate is on the *disk* set; reconcile when it changes.
- **Verification:** boot with unchanged agents → 0 Agent writes; add an agent folder → only that row changes.

**L8-03 — Keep ACPX/skills boot on its background thread (verify) + cache CLI probes.**
- **Location:** `apps.py:466-481` (`boot_acpx()` + `boot_skills()`), skills disk scan, ACPX CLI version probes.
- **Problem:** CLI detection + skill registry scan (500–2000 ms) — if any of it blocks `ready()`, it delays first serve.
- **Surgical fix:** confirm both run on a daemon thread (they are documented to); cache CLI-resolvability/version probes (pairs with L6-03) so `acp_doctor` doesn't re-probe; cache the skills disk scan by directory hash (the 30 s staleness cache already exists — verify it covers boot).
- **Expected gain:** removes ACPX/skills cost from the first-serve path.
- **Risk:** Low.
- **Verification:** B7; first request served before ACPX boot completes.

**L8-04 — Lazy / split heavy imports.**
- **Location:** `views.py` (10 317 lines, AST 718 ms, import 3542 ms), `urls.py` (imports all of `views`), `consumers.py` import 5926 ms, `rag/factory.py` import 6059 ms.
- **Problem:** importing the route layer pulls the entire monolith + LangChain/embeddings even for endpoints that don't need them.
- **Surgical fix (after route tests exist):** (1) split `views.py` by domain (`views_config`, `views_pool`, `views_update`, `views_integrations`, registry-driven connection handlers) keeping compatibility imports (STAGE9_10 Actions 16–25); (2) lazy-import the heavy LLM/embeddings stack behind the chain-build path so non-LLM endpoints don't pay it; (3) module-level `__getattr__` for lazy agent imports (100X Change 130). **Pure import-time refactor; no behavior change.**
- **Expected gain:** route-layer import ≥3× (STAGE9_10 target); faster `manage.py check` and management commands.
- **Risk:** Medium. Watch: circular imports + the global side effects some views rely on — add route tests first, split incrementally, measure each split.
- **Verification:** import-time benchmark after each split; full URL-resolution test green.
- **Basis:** STAGE9_10 lines 16–25; 100X Changes 127–130.

---

## 5.L10 — DATABASE (indexes + query-count guards)

> **Why:** SQLite with no indexes on hot lookups → O(N) scans + N+1 risk; no query-count regression guard. Small absolute cost today, but it grows and there's no defense.

**L10-01 — Add the hot-path indexes (only after EXPLAIN proves need).**
- **Location:** `models.py` (`AgentMessage`, `ChatAgentRun`, `AgentProcess`, `SessionState`, `Skill`).
- **Problem:** message load, run listing, PID lookup, session lookup, pruning all scan.
- **Surgical fix:** add via a migration: `AgentMessage(conversation_user, -timestamp, -id)` (10–30× message load), `ChatAgentRun(status, -startedAt)` (10–50× run listing), `ChatAgentRun(finishedAt)` (pruning), `AgentProcess(pid)`, `SessionState(user)`, `Skill.last_loaded_at`; unique constraints on `Mcp.mcpName`/`Tool.toolName`/`Agent.agentName`. Prove each with a query plan first (STAGE11 Action 144, 7).
- **Expected gain:** the index multiples above; protects the chat-history load (L7-03).
- **Risk:** Low. Watch: a migration on the user's DB — carried by the post-update migrate path (`DB/ToLoad` + `manage.py`).
- **Verification:** EXPLAIN before/after; B10.
- **Basis:** STAGE11 index strategy; 100X Changes 11–14.

**L10-02 — select_related / prefetch_related on FK traversals; batch writes.**
- **Location:** the 3 existing select_related sites + the manual dedupe writes at `consumers.py:1497-1546`; `_get_next_integer_pk` `aggregate(Max(pk))` at `consumers.py:71-73`.
- **Problem:** N+1 risk on FK traversal; race-prone manual dedupe; full-scan max-pk.
- **Surgical fix:** add select_related/prefetch_related where a related object is accessed in a loop; replace manual dedupe with `update_or_create`/upsert (STAGE11 Actions 21–26); the unique constraints from L10-01 make the max-pk pattern unnecessary or indexed.
- **Expected gain:** removes N+1; removes the dedupe race (correctness + speed).
- **Risk:** Low.
- **Verification:** query-count test on the affected endpoints.

**L10-03 — Query-count regression tests.**
- **Location:** new tests using `django.test.utils.CaptureQueriesContext`.
- **Problem:** no guard against a future N+1 regression on WebSocket setup, chat-history load, session restore, ACPX list/status, hot config/skills endpoints (STAGE11).
- **Surgical fix:** add tests asserting an upper bound on query count for each hot path; fail CI if exceeded.
- **Expected gain:** prevents silent regressions (protects all DB gains).
- **Risk:** Low.
- **Verification:** the tests themselves (B10).

---

## 5.L9 — BUILD / PACKAGING (incremental cache, metrics, deterministic manifest)

> **Why:** `build.py` is 3–14 min. Dominators: dependency install (75–260 s incl. torch/Playwright), PyInstaller Analyze+Build (70–210 s, 8× `--collect-all`), carried-Python copytree+prune (30–90 s), collectstatic (10–30 s), numpy purge loop (5–15 s even when clean), asset copies (20–60 s), `--self-modify` snapshot (20–120 s). No incremental cache, no metrics, broad collect-all.

**L9-01 — Build metrics + run id.**
- **Location:** `build.py` (currently prints human output, uses `time.time()`).
- **Surgical fix:** `time.perf_counter()`; write `build_metrics.json` + `.md` per run with run id, Python version, platform, requirements hash, carried-Python file count/bytes (pre/post prune), `dist/manage` count/bytes, `pkg.zip` size + compress duration; `--metrics-out` flag (STAGE12 Actions 1–17).
- **Expected gain:** turns "build is slow" into per-phase numbers → targets the real dominator.
- **Risk:** Low.
- **Verification:** B9 recorded per phase.

**L9-02 — Incremental cache (`.tlamatini_build_cache`).**
- **Location:** `build.py` dependency install, carried-Python, Playwright, collectstatic phases.
- **Surgical fix:** fingerprint each phase (deps by Python+requirements-hash+index+flags; carried Python by source interpreter+requirements+prune policy+platform; Playwright by cache path+entries+revision; static by source hashes+settings hash) and **skip** the phase on a fingerprint hit; `--no-cache`, `--cache-readonly`, `--explain-cache`, `--package-only`, `--installer-only`, `--public-package-only` flags; stale-cache cleanup (STAGE12 Actions 46–67). Also: skip the numpy purge loop when numpy isn't installed.
- **Expected gain:** 2nd/incremental build ≥3× (STAGE12 target); package-only ≥2×.
- **Risk:** Low-Medium. Watch: a stale cache shipping wrong bits — fingerprint must include every input; `--no-cache` for releases.
- **Verification:** B9 clean vs warm; manifest hash identical across a no-op rebuild.
- **Basis:** STAGE12 Phase 12.3.

**L9-03 — Trim `--collect-all` to what's actually imported.**
- **Location:** `build.py` PyInstaller command (8× `--collect-all`: django_bootstrap5, autobahn, ffpyplayer, cv2, httpx, websockets, filesearch_pb2*, unstructured).
- **Problem:** each `--collect-all` walks a package tree; over-collection bloats Analyze + the bundle.
- **Surgical fix:** for each, verify whether a narrower `--collect-submodules`/`--hidden-import` suffices (keep `--collect-all` only where the import graph genuinely can't see it, e.g. cv2, ffpyplayer); measure Analyze time per removal.
- **Expected gain:** shorter Analyze; smaller `_internal`.
- **Risk:** Medium. Watch: removing a needed collect breaks the frozen agent at runtime — verify each with the carried-Python import probe + a frozen smoke test.
- **Verification:** frozen smoke test (each media/agent lib imports) + B9 Analyze delta.

**L9-04 — Deterministic manifest + budgets.**
- **Location:** `build.py` packaging (pkg.zip), release folder.
- **Surgical fix:** `build_manifest.json` (every shipped file: path, size, sha256, category, privacy), sorted stable order, forward-slash ZIP entries, reject absolute/`..` entries, `pkg.zip.sha256`, `release_manifest.json`, file-count + byte budgets that fail the public wrapper on regression (STAGE12 Phase 12.2).
- **Expected gain:** reproducible builds; catches accidental bloat that slows ship + download.
- **Risk:** Low.
- **Verification:** identical manifest across no-op rebuild; budget gate test.

---

## 5.J — PROCESS MODEL (longer-term, only with a proven number)

> These are the big-architecture items from `TLAMATINI_100X_SPEED_PROPOSAL.md`. They are **out of scope for the surgical 3×** (they change architecture, risking behavior) but are recorded so the plan is complete. Pursue only after L1–L10 are banked and a benchmark shows the subprocess model is still the dominant remaining cost.

- **J-01 Persistent Python worker pool** (100X Change 111) — pre-warmed ProcessPoolExecutor for agent runs. Gain: agent startup 2–5 s → 20–50 ms. Risk: High (lifecycle, isolation, env injection). 
- **J-02 In-process coroutine I/O agents** (100X Changes 141–142) — run pure-I/O agents (apirer, emailer, googler) as asyncio tasks, not subprocesses. Gain: 100× startup for those. Risk: High (loses subprocess isolation + the orphan-reaper safety model; would need a new sandboxing story).
- **J-03 Event-driven status** (100X Changes 121–122, 151–155) — replace psutil polling with OS signals / FS watchers / shared-memory status board. Gain: 50–100× status checks. Risk: Medium-High (cross-platform).
- **J-04 Shared-memory / ZeroMQ / gRPC agent IPC** (100X Changes 114–116) — replace file-tail with mmap/zmq/grpc. Gain: large on chatty agents. Risk: High.

**Recommendation:** keep J as a research track. The surgical 3× does **not** require it.

---

# 6. VERIFICATION & BENCHMARK HARNESS (the spine of the whole plan)

Nothing ships without a number. Build this in Session 1 so every later session has before/after.

**6.1 The benchmark module (`agent/perf/bench.py`, new, source+frozen safe).**
- One function per `B1..B10`, each returns `{name, ms, meta}` and appends to a dated JSONL under `<app>/Temp/perf/`.
- Reuses the existing `agent/llm_timing.py` WAIT-START/WAIT-END to split Ollama from Tlamatini (so a "slow" run is correctly attributed).
- A `--compare <baseline.jsonl>` mode prints a delta table and **fails** if any metric regressed >5%.

**6.2 Characterization tests (output-neutrality).**
- A fixed corpus of prompts (reuse the `tlamatini-daily-chat-test` 1000-question set, subset for speed) run through `ask_rag` with a **stubbed/deterministic LLM** so answers are reproducible; assert byte-identical answers + Exec Report + `.flw` before and after each optimization.
- Security matrix for `L4`: allowed paths, traversal (`..`), symlinks, out-of-scope paths — must match the LLM-gated decisions exactly or be stricter.

**6.3 Driving it with Tlamatini's own tools.**
- Use `chat_agent_*` / the daily-chat-test Playwright harness for end-to-end B1–B3; `mcp__tlamatini__executer`/`pythonxer` for B4–B10; record into the nightly report.
- **Toggle discipline** (memory `feedback_test_toggle_state`): every chat benchmark sets+verifies Multi-Turn ON, Exec-Report ON, Ask-Execs OFF, and clears history first — otherwise the run returns canned ~144-char replies and the numbers are fiction.

**6.4 Per-session gate (all must pass before commit):**
1. Target metric improved by its claimed amount (or item reverted).
2. No other B-metric regressed >5%.
3. Characterization tests byte-identical.
4. `python -m ruff check` + `npm run lint` + `python manage.py test` green.
5. Frozen carriage updated in `build.py` if touched; both inclusion sweeps clean.
6. Forward commit (no history rewrite); push only with <REDACTED>'s explicit OK.

---

# 7. RISK REGISTER & ROLLBACK

| Risk | Items | Mitigation | Rollback |
|---|---|---|---|
| **Cache serves stale data** | L1c/d, L3-* , L6, L8-02, L9-02 | Every cache key includes the real invalidator (mtime/size/hash/model/flags); fail-open to recompute on miss/error | Feature-flag each cache off via config; recompute path always present |
| **Security skip is wrong** | L4-03 | Strictly *more* conservative than the LLM; security matrix test must match-or-stricter | Disable the heuristic → fall back to LLM classifier |
| **Concurrency bug** | H-STATE-01, H-TASK-01, L7-02, L4-02 | Generation tokens; ContextVar; per-key incremental migration with concurrent-request tests | Revert to single-lock global state |
| **Async reaping misses a child** | L2b | Keep synchronous reaping for spawning tools whose output the next tool reads | Flag back to synchronous reaping |
| **Runtime-copy isolation break** | L6-01 | Template treated read-only; mutable allowlist per agent; template-byte-unchanged test | Fail-open to `shutil.copytree` |
| **Frozen ≠ source** | all | Every change verified in a frozen smoke build; inclusion sweeps | Rebuild from last good commit |
| **Build cache ships wrong bits** | L9-02/03 | Fingerprints cover every input; `--no-cache` for releases; manifest sha256 | `--no-cache` clean build |
| **Import split breaks routes** | L8-04 | Route tests first; split incrementally; compatibility imports | Re-merge module (kept in git history) |
| **History rewrite (forbidden)** | all commits | Forward commits only; Private Data Guard | n/a — never happens |

**Universal rollback:** every optimization lands behind a config flag (default ON once proven) so a regression in the field is a config toggle, not a redeploy.

---

# 8. SESSION-BY-SESSION CHECKLIST (copy into each session)

**S1 — Instrument**
- [ ] `agent/perf/bench.py` with B1–B10; JSONL output under `<app>/Temp/perf/`.
- [ ] Ship `llm_timing` WAIT-START/WAIT-END across factory.py + mcp_agent.py (verify it's active).
- [ ] Record a full baseline nightly run; commit the baseline JSONL.

**S2 — Ship the freebies**
- [ ] Commit the reaper O(N)→ rewrite (L2a); `build.py`; verify frozen sweep <50 ms (B6).
- [ ] L1a `keep_alive=-1` + pooled httpx client; L1e flush batching.
- [ ] `OLLAMA_KEEP_ALIVE` documented + defaulted.

**S3 — Ollama serving layer**
- [ ] L1b source-build race detector banner; L1c VRAM verdict cache; L1d warm embeddings handle.
- [ ] 50-prompt run shows zero multi-minute stalls; embeddings never fail (B8).

**S4 — Request hot-path caches**
- [ ] L3-CFG-01/02/03; L4-01/02/03 (security matrix green).
- [ ] Shape-B request 3× (B2); answers byte-identical.

**S5 — Sidecars + executor caches**
- [ ] L5-01/02/03; L3-PROMPT-01; L3-EXEC-01/02/03.
- [ ] Shape-C overhead −50% (B5); planner build count/request = 1.

**S6 — RAG cache**
- [ ] L3-RAG-01..05; reconnect on unchanged context = cache hit (B3).

**S7 — Reconnect deltas + async hardening**
- [ ] L7-01/02/03; H-POOL-01; H-TASK-01; H-QUEUE-01; H-STATE-01 (incremental).
- [ ] Reconnect 3×; −70% setup messages; task/memory flat over 100 cycles.

**S8 — Runtime copy**
- [ ] L6-01/02/03; wrapped-agent launch 3× (B4); isolation + template-unchanged tests green.

**S9 — Startup**
- [ ] L8-01/02/03; L8-04 (after route tests); first-answer-ready 2–5 s faster (B7).

**S10 — DB**
- [ ] L10-01 (EXPLAIN-justified indexes) via migration; L10-02; L10-03 query-count tests.

**S11 — Build**
- [ ] L9-01 metrics; L9-02 incremental cache; L9-03 collect-all trim (frozen smoke); L9-04 manifest+budgets.
- [ ] 2nd build 3× (B9); manifest deterministic.

**S12 — Long-tail / research**
- [ ] Agent-class startup budgets + harness (AGENTS 100-line); only ship micro-opts with a proven number; evaluate J-track.

---

# 9. TRACEABILITY — basis document → plan item

| Basis document | Feeds plan items |
|---|---|
| `Tlamatini_NIGHTLY_PERFORMANCE_REPORT.md` | §2.1 baselines, B1–B10, import-time targets, static counts |
| `TLAMATINI_100X_SPEED_PROPOSAL.md` | L6 (101–110), J (111–156), L10 (11–14), L8 (127–130), RAG (551–650) |
| `Tlamatini_STAGE9_10_PERFORMANCE_HOTSPOTS.md` | L6 (1–11), L8-04 (16–25), L3-RAG (37–47,134–163), L3-CFG (48–57) |
| `Tlamatini_STAGE11_DATABASE_ASYNC_THREADS_QUEUES_PLAN.md` | L10 (indexes, query-count), H-POOL/TASK/QUEUE/STATE (27–61,67–110) |
| `Tlamatini_STAGE12_BUILD_INSTALLER_UPDATE_PACKAGING_PLAN.md` | L9 (metrics 1–17, manifest 21–45, cache 46–67) |
| `Tlamatini_STAGE6_WEBSOCKET_SESSION_RATE_LIMIT_PLAN.md` | L7-01/02 (19–34,71–76) |
| `Tlamatini_STAGE3_CONFIG_CONTACTS_SECRETS_PLAN.md` | L3-CFG-01/02 (1–8), atomic-write/lock |
| `Tlamatini_AGENTS_…_100_LINE_PROPOSAL.md` | L6-03 (73–76), §12 agent-class budgets/harness (1–16) |
| `Tlamatini_SECURITY_PERFORMANCE_500_ACTIONS.md` | cross-cutting master ordering; the security guardrails wrapping every item |
| STAGE1/2/4/5/7/8 | security context (not perf) — honored as guardrails, not optimizations |

> **Note:** STAGE1–8 are primarily *security*. This plan **inherits** them as constraints (no optimization may weaken a security boundary — path isolation, process-execution safety, WS rate limits, external-MCP boundary, logging/privacy). Where a security item *also* helps speed (config locking/caching, tool-output caps, connect timeouts), it is folded into the matching L-item above.

---

# 10. APPENDICES

### Appendix A — Agent-class performance budgets (from AGENTS 100-line)
Enforce per class once the harness (S1/S12) exists: simple file agents <1 s startup; process agents (executer, stm32er, esp32er, arduiner, node_manager, acpxer) <3 s; browser/hardware (playwrighter, camcorder, videoplayer, kalier) explicit longer budgets. Build a "top-10 slowest agents" dashboard from `bench.py` output; cache validated external tool paths (L6-03); warm pools only for genuinely expensive agents.

### Appendix B — External-MCP latency guardrails (STAGE7, perf-relevant)
Cache each server's tool list with a TTL; cap tool-output bytes + WS frame size; per-server circuit breaker; `get_external_mcp_tools` with no active servers <5 ms; active-server binding must not block chat setup. These also harden security — keep both intents.

### Appendix C — The long tail (do only with a measured number)
- Pre-compile `.pyc`, shared `__pycache__` across runtime copies (100X 127–128).
- Token-count heuristic (`interface.py:56-64`) is already O(n)/<1 ms — leave it.
- Regex patterns are module-level/compiled-once — no action.
- `LLMProgram.objects.get()` (`interface.py:49-54`) — add select_related only if a benchmark shows a traversal cost.
- Zipapp/lazy-hydration templates (100X 104–105) — only if L6 hardlink/reflink proves insufficient.

### Appendix D — What NOT to do (anti-goals)
- Do **not** chase the literal "1000 edits" — most are <10 ms and will not move a B-metric; they add risk without reward.
- Do **not** convert agents to in-process coroutines (J-02) for the 3× — it sacrifices isolation + the reaper safety model for a win the surgical items already deliver.
- Do **not** auto-kill a user's source-build Ollama (L1b is diagnostic only).
- Do **not** weaken any STAGE1–8 security boundary for speed.
- Do **not** apply a fix only to live `C:\Tlamatini`; it is incomplete until `build.py` carries it.

### Appendix E — Expected cumulative result
| Path | Today | After (target) | Dominant items |
|---|---|---|---|
| Plain Multi-Turn answer (Shape A) | Ollama + ~25 ms | Ollama + ~10 ms, no cold reload | L1, L3-PROMPT, L3-EXEC |
| Path-bearing request (Shape B) | +1000–2500 ms | +~600 ms | L4-01/02/03 |
| Tool+sidecar request (Shape C) | +200–800 ms | +~150 ms | L2, L5, L6 |
| Reconnect-to-ready | full rebuild | cache hit (~network) | L7, L3-RAG |
| Cold start | 2–5 s | ~1–2 s | L8 |
| Wrapped-agent launch | ~copytree | 3–100× faster | L6 |
| Incremental build | 3–14 min | ~3× on 2nd build | L9 |
| **The minutes-long freezes** | up to 3 min | **gone** | **L1 + L2** |

**Headline:** L1 (Ollama serving) + L2 (reaper, already written) remove the minutes-long pathologies; L3–L7 deliver a measured ≥3× on real steady-state chat; L8–L10 protect cold start, DB, and build. The 3× is met per request shape, with every step proven by a number and a byte-identical-output test.

---

*End of plan. No code was modified by this document. Execution begins at Session 1 (Instrument).*
