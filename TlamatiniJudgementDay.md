# Tlamatini — Judge-Merging ("Judgement Day") — Design Document

> **Status:** design only — NO code changes. This document describes a surgical, out-of-risk
> implementation of a multi-model judge-and-merge answering scheme for the Tlamatini chat path.
> **Author intent (<REDACTED>):** add a "Judge-Merging" toolbar checkbox (sibling of Multi-Turn) that
> fans every prompt out to 3 answering models in parallel and uses a 4th "judge/merge" model to
> produce one superior final answer.

---

## 1. Verdict

**Feasible — and it fits Tlamatini's existing patterns almost perfectly.** It is, in essence:

- a new **toolbar mode** (plumbed exactly like `acpx_enabled` / `multi_turn_enabled`),
- one **new isolated chain** (`JudgeMergeChain`) that owns fan-out + barrier + judge,
- a new **Config ▸ Judgement-Merging** dialog that picks + validates the 4 models, and
- a one-time **clear handshake** when the mode is switched on.

No core surgery. The risky logic is quarantined inside one new file.

### Key reality: "connection" = client instance, not a socket

Ollama is **stateless HTTP**. There is no persistent socket to "close" and "re-open". So:

- "close the current connection with Ollama" → drop the current chain's model-client object.
- "open 4 new connections" → build **4 `ChatOllama` client objects** against the same
  `ollama_base_url`, each bound to a different model.

This makes the scheme **cheaper and safer** than it sounds — there is no connection lifecycle to
manage, only object construction.

---

## 2. What it is

A new **Judge-Merging** mode. With it on, each user prompt:

1. fans out to **3 answering models** in parallel (same context to all 3),
2. **barrier-waits** for all 3 answers,
3. is sent — as Q + the 3 answers — to a **4th judge/merge model**, which picks the best answer
   and merges in any **consistent** info the other two had that the best one missed,
4. and the **merged answer** is what the user sees.

---

## 3. End-to-end flow

```
User ticks Judge-Merging
   │
   ├─ config saved + validated?  ──NO──► block tick, open Config ▸ Judgement-Merging dialog
   │                                     (must pick 3 answer models + 1 judge, all validated)
   │
   └─YES─► Confirmation dialog:
           "Chat history and loaded context will be cleared."
           Shows: 3 answering models + the judge/merge model.
              │
        ┌─────┴─────┐
      Cancel      Continue
        │             │
     uncheck,     backend: clear chat history (this session) + clear loaded RAG context
     no-op            + drop current single-model chain
                      + build 4 model clients (3 answer + 1 judge)
                          │
                          ▼
         ── From now on, per user prompt ──
         retrieve context ONCE
              │
              ▼
         fan out identical payload ──► Model A ─┐
                                  ──► Model B ─┤ BARRIER: wait for all 3
                                  ──► Model C ─┘
              │
              ▼
         judge prompt (Q + A + B + C) ──► Judge/Merge model
              │   (pick best → complement with consistent missing info → final)
              ▼
         render merged answer in chat
```

Unticking **Judge-Merging** reverts to normal single-model mode (rebuild the standard chain).

---

## 4. Context loading under Judge-Merging — "context-once, fan-out identical"

**The `Context` menu keeps working unchanged.** The only behavioral change is the one-time clear
when the mode is switched **on**.

1. **At enable time** the currently-loaded context is cleared (part of the Continue handshake).
   This is a one-time reset so the 3 models start from a clean, shared state.
2. **After** the mode is on, the user sets a directory as context **normally** —
   `Context ▸ Set directory as context` is **untouched**. The native folder picker
   (`views.pick_context_directory_view` → `set-directory-as-context`) and the RAG/FAISS load run
   exactly as today.
3. **Per prompt**, `JudgeMergeChain` runs **retrieval ONCE** against the loaded context, then
   injects the **identical `context` blob** into all 3 answering models. So all 3 reason over the
   **same files** — no drift, and **one** retrieval cost instead of three.
4. The whole `pick_context_directory` → `set-directory-as-context` → RAG-load path is reused
   verbatim. `JudgeMergeChain` simply reads the same loaded context the normal chain would.

### Judge-sees-context config flag

The **judge/merge model** always receives the question + the 3 answers. Whether it *also* sees the
loaded context is a config toggle:

- **`judge_sees_context: false` (DEFAULT — "lean")** — the judge merges only what the 3 answering
  models produced. Cheapest; the judge is a pure arbiter/merger.
- **`judge_sees_context: true` ("grounded")** — the judge also gets the same context blob, so it
  can catch a fact that **all 3** answering models missed, or sanity-check a claim against source.
  Costs more tokens; use when correctness against the loaded files matters more than speed.

This flag lives in the `judge_merging` config block (Section 7) and is surfaced in the
Config ▸ Judgement-Merging dialog.

---

## 5. The barrier (concurrency)

`ask_rag` is synchronous and already runs off the event loop via
`sync_to_async(ask_rag, thread_sensitive=False)`. The 3 answering calls run concurrently inside
`JudgeMergeChain` via a `ThreadPoolExecutor` (the same pattern the Googler tool already uses to run
blocking work). The barrier is a `concurrent.futures.wait(..., return_when=ALL_COMPLETED)` (or
`as_completed` with a deadline). The judge call runs **after** the barrier resolves.

**Graceful degrade:** if a model errors or times out, the barrier proceeds with the survivors
(≥1) and the judge prompt is told how many answers it received. All-3-fail → a clean error message,
not a hang.

---

## 6. The judge / merge prompt (the heart)

A single, well-specified prompt to the 4th model:

```
SYSTEM:
You are a Judge-Merger. You receive a user QUESTION and up to 3 candidate ANSWERS produced by
3 different models. Do the following, in order:
  1. Choose the single BEST answer as the BASE.
  2. Scan the other answers for factual content that is MISSING from the BASE and is mutually
     CONSISTENT (agreed/at least non-contradicting). 
  3. Merge ONLY that missing-but-consistent content into the BASE, seamlessly.
  4. Invent nothing. Drop anything contradictory. Do not mention this process.
Output ONLY the final merged answer.
[If judge_sees_context = true, also: "Use the provided CONTEXT to verify claims and to add any
correct fact that ALL candidate answers missed."]

USER:
QUESTION: <the user's prompt>
ANSWER 1 (<model A>): <...>
ANSWER 2 (<model B>): <...>
ANSWER 3 (<model C>): <...>
[CONTEXT: <same context blob> — only when judge_sees_context = true]
```

Optionally the judge can also emit a short machine-readable rationale (which one it picked, what it
merged) that Tlamatini **logs/hides** for transparency — analogous to the Exec Report idea — but the
user only ever sees the final merged answer. Storing the 3 raw answers + rationale in `global_state`
(`last_judge_*`) mirrors how `last_exec_report_*` is handed off today.

---

## 7. Config: the `judge_merging` block (config.json — no DB migration)

Prefer `config.json` over a new DB model (lighter, mirrors how the `acpx` block lives there):

```json
{
  "judge_merging": {
    "answer_models": ["kimi-k2.7-code:cloud", "glm-5.1:cloud", "qwen3.5:397b-cloud"],
    "judge_model": "minimax-m3:cloud",
    "judge_sees_context": false,
    "configured": true,
    "validated": true
  }
}
```

- `configured` — the user saved 3 answer models + 1 judge model.
- `validated` — all 4 were confirmed present/reachable in Ollama at save time.
- The **Judge-Merging checkbox is only enabled when `configured && validated`** — otherwise ticking
  it opens the Config dialog instead.

---

## 8. Surgical change map

| File | Change | Risk |
|---|---|---|
| `agent/rag/chains/judge_merge.py` | **NEW** — owns fan-out + `ThreadPoolExecutor` barrier + judge prompt + degrade. All new logic lives here. | very low (isolated) |
| `agent/rag/factory.py` | When `judge_merging_enabled`, build the 4 model clients and return `JudgeMergeChain` instead of the normal chain | low |
| `agent/rag/interface.py` | Thread `judge_merging_enabled` through `ask_rag`; stash 3 raw answers + judge rationale in `global_state` (`last_judge_*`) | low |
| `agent/consumers.py` | Read `judge_merging_enabled`; handle the enable→confirm→clear handshake; `set-judge-merging-config` + validate handlers; clear session history + loaded context on Continue | medium (the destructive clear) |
| `agent/views.py` + `agent/urls.py` | `GET /agent/ollama_models/` (live `{ollama_base_url}/api/tags` list) + `POST /agent/validate_judge_models/` | low |
| `agent/config.json` | New `judge_merging` block (Section 7) — **no DB migration** | very low |
| `agent/templates/agent/agent_page.html` | Toolbar **Judge-Merging** checkbox + **Config ▸ Judgement-Merging** menu entry + 2 dialog containers + asset includes | low |
| `agent/static/agent/js/agent_page_state.js` | `isJudgeMergingEnabled` / `applyStoredJudgeMergingState` / `syncJudgeMergingAvailability` (gated on `configured && validated`) | low |
| `agent/static/agent/js/agent_page_init.js` | Send `judge_merging_enabled` on submit; drive the confirm dialog + the enable handshake | low |
| `agent/static/agent/js/agent_page_chat.js` | Staged progress UI ("Model A/B/C answering… → Judging…") + render the merged answer | low |
| `agent/static/agent/js/judge_merging_dialog.js` | **NEW** — the Config dialog (4 model dropdowns from `/agent/ollama_models/`, Validate, Save) + the confirm dialog | low |
| `agent/static/agent/css/...` | `.judge-merging-*` dialog + progress styling | trivial |
| `eslint.config.mjs` | new globals for the dialog/state helpers | trivial |

### Plumbing note (do-not-break)

The `judge_merging_enabled` flag rides the same path as `acpx_enabled`:
toolbar → WebSocket per-request → `consumers.receive` → `interface.ask_rag` → `factory`. If it ever
travels through `UnifiedAgentChain.invoke`, it **must** be added to that method's payload-rebuild
**whitelist** — the same drop-on-rebuild bug class that once broke `exec_report_enabled`.

---

## 9. Decisions locked for v1 (out-of-risk)

1. **v1 is a Q&A merge path — no tools.** Judge-Merging is its own mode; grey out
   Multi-Turn / ACPX / Ask-Execs while it is checked (same way Ask-Execs greys out when Multi-Turn
   is off). Merging tool-calling *operator* runs is a much larger problem — explicitly deferred.
2. **Retrieve once, fan out identical payloads** (Section 4) — truly "same context," and 1
   retrieval instead of 3.
3. **Cloud models = no contention.** The example models are `:cloud`, so the 3 run on Ollama's
   servers in parallel with no local VRAM fight. **Local** models on one GPU would *serialize* and
   contend — surface this to the user. `:cloud` models also need an authorized/signed-in Ollama
   (Pro/Max); validation must flag "model not present / not pulled / not authorized".
4. **Staged UX, not streaming.** A merged answer cannot be streamed until the judge finishes, so
   show staged progress, then render the final answer. **4 LLM calls per turn** — real latency and
   cost, by design.
5. **Graceful degrade** (Section 5): a failed/timed-out answering model does not stall the barrier;
   the judge is told how many answers it got; all-3-fail → clean error.
6. **History clear scope = current session only** (non-destructive). To confirm with <REDACTED> if a
   wider wipe is ever wanted.

---

## 10. Open question for <REDACTED>

The clear-on-enable wipes chat history — scoped to the **current session** (recommended,
non-destructive) vs the user's **entire** history. Default in this design: current session only.

---

## 11. Why this is "beyond-excellence" and low-risk

- **One quarantined new file** holds all the novel logic; everything else is the proven
  toolbar-flag + config-block + dialog pattern already used by ACPX and Ask-Execs.
- **No DB migration** (config.json block), so nothing to roll back in the schema.
- **Reuses the entire Context/RAG load path verbatim** — no second code path for context.
- **Fail-safe by construction**: stateless clients (nothing to leak), barrier degrades, validation
  gates the checkbox, and the destructive clear is behind an explicit Continue.
- **Transparent**: the 3 raw answers + judge rationale are captured in `global_state` for an
  optional "show-your-work" panel, mirroring the Exec Report handoff.
