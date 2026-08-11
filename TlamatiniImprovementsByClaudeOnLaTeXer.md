# Tlamatini — LaTeX Generation: Full Repair Record

**Date:** 2026-08-11
**Requested by:** Angela López Mendoza (`@angelahack1`)
**Performed by:** Claude (Claude Code), using Tlamatini's own agents throughout
**Subject:** Why Tlamatini could never produce a LaTeX PDF from chat, and every
line changed to fix it.

---

## 0. Executive summary

Angela asked Tlamatini for a "fancy LaTeX implementation and its PDF" explaining
`CompleteOpenMPImplementation.cu`. **Tlamatini produced nothing.** The target
directory `C:\Users\angel\OneDrive\Desktop\OpenMPImplementation` was completely
empty — no `.tex`, no `.pdf`.

Forensics on the live database found **four independent defects**. All four are
now fixed, and the whole job was then re-run through the real chat GUI, where
Tlamatini produced the document **herself**, end to end.

| # | Defect | Consequence | Status |
|---|---|---|---|
| 1 | The byte-exact request channel was **hardcoded to File-Creator** | Every LaTeX `\\` row break was collapsed to `\`; trailing `filename=`/`output_dir=` were swallowed into the document body | **FIXED** |
| 2 | The LLM client timeout was **hardcoded to 120 s** | A full Multi-Turn request always ReadTimeout'd; self-healing retried forever | **FIXED** |
| 3 | The destructive `bisect` repair rung fired **after an infrastructure blip** | A 27-page clean PDF became a 26-page DEGRADED one with a block deleted | **FIXED** |
| 4 | **No stop condition** on a finished document | She kept "improving" a perfect PDF for 50+ iterations until she broke it | **FIXED** |

**Final proof (live chat GUI, visible Chrome):**
`OpenMPCompleteGuide.pdf` — **27 pages, 716,421 bytes, 0 LaTeX errors**, from a
**61,951-character** `.tex` that Tlamatini wrote herself.

---

## 1. The evidence — what the database confessed

The live `tlamatini.log` is truncate-on-start, so it holds nothing about a run
from the previous day. The **database does**. Read read-only from the frozen
install:

```
C:\Tlamatini\_internal\db.sqlite3   ->   table agent_agentmessage
    id | message | timestamp | user_id | conversation_user_id
```

* `user_id` = the **sender** (2 = Tlamatini, 3 = angela)
* `conversation_user_id` = the conversation **owner**

Angela's conversation was **msg 49** (her request) and **msg 50** (the failed
answer, 35,450 chars). Everything after the marker
`<!--TLAMATINI_EXEC_REPORT_BOUNDARY-->` inside msg 50 is the **Exec Report** —
and that is where the run confessed:

```
List of Executer Operations   ... several SUCCESS, then a PowerShell here-string FAILURE
List of Grepper Operations    ... SUCCESS
List of LaTeXer Operations    ... action='validate'          <-- ONE call. EVER.
List of Pythonxer Operations  ... 4 x FAILURE
```

**LaTeXer was never asked to typeset anything.** It was asked only whether MiKTeX
existed. Tlamatini had instead tried to assemble the `.tex` with PowerShell
here-strings and generated Python scripts — all of which failed on quoting — and
finally apologised:

> *"the multi-part file assembly approach through PowerShell was too cumbersome
> to complete… the full `.tex` file was not yet assembled and compiled into a PDF."*

The question was therefore not "why did LaTeXer fail?" but **"why did she refuse
to use LaTeXer at all?"**

---

## 2. DEFECT 1 — the byte-exact channel was hardcoded to one agent

### 2.1 Symptom

A real LaTeX document cannot survive the trip from the chat LLM to the LaTeXer
agent.

### 2.2 Root cause — `agent/tools.py`

The wrapped-agent launcher parses the LLM's free-form request
(`Run LaTeXer with action='compile', input_text='…'`) with a shared parser tuned
for **shell / SQL / Python payloads**. That parser calls
`_unquote_preserving_backslashes`, which deliberately collapses `\\` → `\`.

A byte-exact escape hatch already existed — but it was gated on ONE agent:

```python
if spec.template_dir == "file_creator":      # <-- the bug, in one line
    ...
```

So File-Creator got byte-exact content and **every other agent did not**.

**Why this is catastrophic specifically for LaTeX:** in LaTeX, `\\` is the
**row/line break**. It ends every table row, every `\author{… \\ …}` line, every
matrix row. Collapsing it to `\` produces `\ ` (a control space) and the document
breaks.

### 2.3 Proof, measured before any change

Feeding a realistic table through the real parser:

```
original : \begin{tabular}{ll}\n a & b \\\n c & d \\\n\end{tabular}
received : \begin{tabular}{ll}\n a & b \ \n c & d \ \n\end{tabular}
row-break count  original 2  ->  received 0        <-- every row break destroyed
length           187         ->  185
```

### 2.4 Second half of the defect — swallowed keys

`_split_assignment_segments` (tools.py ~line 564) deliberately keeps a
**multi-line** quoted value open until EOF or an `and|with KEY=` conjunction, so
that interior apostrophes in scripts survive. The side effect: the extremely
common comma style

```
input_text='…multi
line document…', filename='demo.pdf', output_dir='C:\Temp\x'
```

glues `', filename='demo.pdf', output_dir='C:\Temp\x` **into the document body**,
and both keys come back **empty**. Measured:

```
filename   -> ''      (requested 'demo.pdf')
output_dir -> ''      (requested 'C:\Temp\x')
```

So the literal text `', filename='demo.pdf'` would have been **typeset into the
PDF** and the output path silently ignored.

### 2.5 The fix — line by line

#### (a) `agent/chat_agent_registry.py` line 36 — new declarative field

```python
    verbatim_fields: tuple[str, ...] = field(default_factory=tuple)
```

Added to the frozen dataclass `ChatWrappedAgentSpec`, immediately after
`long_running: bool = False`. Each agent now **declares** which of its fields
carry literal source text. Default empty tuple = no behaviour change for the
other 80+ agents.

#### (b) `agent/chat_agent_registry.py` line 197 — File-Creator keeps its guarantee

```python
        verbatim_fields=("content",),
```

Exactly the behaviour the old hardcode gave it, now expressed as data.

#### (c) `agent/chat_agent_registry.py` line 1816 — LaTeXer gains it

```python
        verbatim_fields=("input_text", "content", "find_text", "replace_text"),
```

* `input_text` — the document passed to `action='compile'`
* `content` — the body passed to `action='create_file'`
* `find_text` / `replace_text` — anchors for `action='edit_file'`, which are LaTeX
  fragments and equally escape-sensitive

#### (d) `agent/tools.py` lines 1034–1084 — recover the swallowed keys

```python
_SWALLOWED_TAIL_RE = re.compile(
    r"""(?P<q>['"])\s*[,;]\s*(?=[A-Za-z_][A-Za-z0-9_.]*\s*=)"""
)
```

Line by line: match a quote character, optional spaces, a `,` or `;`, optional
spaces, then **look ahead** (do not consume) for an identifier followed by `=`.
That is the signature of "a new assignment starts here".

```python
def _recover_swallowed_assignments(value_text, runtime_config):
```

* iterates every candidate split point, left to right;
* takes the text after it as a **candidate tail** and parses it with the *same*
  segment splitter the real parser uses;
* **accepts the cut only if EVERY key in that tail already exists in the agent's
  own `config.yaml`.** This is the safety property: a genuine
  `…\end{quote}', banana='yes'` inside real prose is never mistaken for an
  assignment list, because `banana` is not a LaTeXer config key;
* on acceptance, applies those keys with the normal coercion (a Windows path
  *does* want `C:\\Temp` → `C:\Temp`) and returns the cleaned body;
* returns the value **unchanged** on any doubt, and never raises.

#### (e) `agent/tools.py` line 2836 — the hardcode becomes generic

Before:

```python
if spec.template_dir == "file_creator":
    b64_value = runtime_config.get("content_b64")
    ...
```

After:

```python
    for verbatim_field in getattr(spec, "verbatim_fields", ()) or ():
        try:
            b64_value = runtime_config.get("%s_b64" % verbatim_field)
            if isinstance(b64_value, str) and b64_value.strip() != "":
                continue                      # b64 already carries exact bytes
            verbatim_value = _extract_verbatim_assignment(str(request), verbatim_field)
            if verbatim_value is None:
                continue
            verbatim_value, recovered = _recover_swallowed_assignments(
                verbatim_value, runtime_config
            )
            if verbatim_value != runtime_config.get(verbatim_field):
                runtime_config[verbatim_field] = verbatim_value
                logger.info(... "re-extracted VERBATIM (%d chars, no escape decoding)" ...)
            if recovered:
                logger.info(... "recovered swallowed assignments: %s" ...)
        except Exception as exc:
            logger.warning(...)              # never let this break a launch
```

Order matters and is deliberate:

1. **`<field>_b64` wins first.** base64's alphabet contains no quote, backslash,
   comma or newline, so it is immune to *any* transport mangling. If present,
   leave the plain field alone entirely.
2. Otherwise re-extract the plain field from the **raw request** with no escape
   decoding.
3. Then recover any swallowed trailing assignments.
4. `getattr(..., ())` so a spec built before this field existed still works.
5. The whole body is wrapped in `try/except` — a launch must never die here.

#### (f) `agent/agents/latexer/config.yaml` — the parser-immune keys

| line | key |
|---|---|
| 67 | `input_text_b64: ""` |
| 83 | `content_b64: ""` |
| 97 | `find_text_b64: ""` |
| 98 | `replace_text_b64: ""` |

**These must exist in `config.yaml`** — the assignment applier only writes keys
that are already present in the template, so a missing key means the value is
silently dropped.

#### (g) `agent/agents/latexer/latexer.py` — the agent decodes them

* **line 75** — `import base64` (added after `import json`; stdlib only, so the
  agent stays dependency-free and behaves identically frozen and from source)
* **line 4207** — `_B64_FIELDS = ("input_text", "content", "find_text", "replace_text")`
* **lines 4210–4241** — `_decode_b64_fields(config)`:
  * skips a field whose `*_b64` is absent or blank;
  * `base64.b64decode(raw.strip()).decode("utf-8")` then **overwrites** the plain
    field — the b64 channel WINS;
  * a malformed value is **logged and ignored**, keeping the plain field
    (fail-open: decoding must never stop a compile);
  * logs `input_text taken from input_text_b64 (N chars, byte-exact)`.
* **line 4247** — `main()` calls `_decode_b64_fields(config)` immediately after
  `load_config()`, before any preflight or routing sees the config.

#### (h) `agent/chat_agent_registry.py` — teaching the LLM the reliable route

The old `example_request` advertised exactly the shape that breaks:

```
Run LaTeXer with action='compile', input_text='\\section{Results}\n…', filename='results.pdf'
```

(a multi-line `input_text` in comma style — the swallow case). It now teaches
three shapes explicitly:

1. **SHORT FRAGMENT** — plain `input_text`, one line, safe.
2. **REAL DOCUMENT** — write the `.tex` once with `chat_agent_file_creator` using
   `content_b64`, then compile with `tex_path=`.
3. **ONE CALL** — `input_text_b64='<base64 of the whole .tex>'`.

And the `purpose` gained a mandatory paragraph:

> *"for anything beyond a one-line fragment — tables, TikZ, a preamble, ANY `\\`
> row break — do NOT paste the document as plain input_text and NEVER assemble a
> .tex with PowerShell here-strings, Add-Content or a generated Python script
> (that path failed five times and produced no file at all)."*

This is what actually changed her behaviour: in the live re-run the planner
selected `chat_agent_latexer` (score 73) **and** `chat_agent_file_creator`, and
she took route 2.

---

## 3. DEFECT 2 — the LLM client timeout was hardcoded to 120 s

### 3.1 Symptom

Every Multi-Turn attempt died with `ReadTimeout` at **exactly 120.0 s**, and the
self-healing ladder retried forever:

```
[OLLAMA-TIMING] model=glm-5.2:cloud FAILED after 120.0s (waiting on Ollama): timed out
Tactic 'normal' hit a transient network error (ReadTimeout) — switching…
Tactic #2 … Tactic #3 'patient-retry' … Tactic #4 'trim-context' …
```

The identical notes appear in Angela's **original** failed answer, so this
defect had been burning her iterations all along.

### 3.2 Root cause — it was not a broken model

A bare probe of the *same* model answered in **1 second**:

```
POST /api/generate  {"model":"glm-5.2:cloud","prompt":"say OK"}   ->  OK in 1s
```

The difference is **request size**: a full Multi-Turn request carries the entire
system prompt **plus every bound tool schema** (100+ tools). That legitimately
needs longer than a one-line prompt — and the bound was hardcoded:

* `agent/mcp_agent.py` — `client_kwargs.setdefault("timeout", 120.0)`
* `agent/rag/factory.py` — `client_kwargs = {'timeout': 120.0}` (**twice**)

`unified_agent_llm_step_timeout_seconds` existed and was already 180 — but it
governs the *watchdog*, not the HTTP client, so it could not help.

### 3.3 The fix — line by line

#### (a) `agent/mcp_agent.py` lines 206–231 — the resolver

```python
DEFAULT_LLM_CLIENT_TIMEOUT_SECONDS = 120.0


def resolve_llm_client_timeout(config) -> float:
```

* reads `llm_client_timeout_seconds` from `config.json`;
* `None` / `""` / non-numeric / `<= 0` all fall back to **120.0** — a config typo
  must never make the chat hang *longer* than before;
* wrapped in `try/except`, never raises.

#### (b) `agent/mcp_agent.py` lines 629–632 — the call site

```python
        _llm_timeout = resolve_llm_client_timeout(config)
        client_kwargs.setdefault("timeout", _llm_timeout)
        print("--- [LLM-TIMEOUT] one Ollama call may take up to %.0fs "
              "(llm_client_timeout_seconds) ---" % _llm_timeout)
```

`setdefault` is kept so an explicitly-passed or inherited timeout still wins. The
`print` makes the effective value **visible in `tlamatini.log`** — no more
guessing where a timeout came from.

#### (c) `agent/rag/factory.py` — the same value, no import cycle

A small local helper does a **lazy** import inside the function body, so
`agent.rag.factory` never takes a module-level dependency on `agent.mcp_agent`:

```python
def _llm_client_timeout(config):
    try:
        from agent.mcp_agent import resolve_llm_client_timeout
        return resolve_llm_client_timeout(config)
    except Exception:
        return 120.0
```

Both former literals became `client_kwargs = {'timeout': _llm_client_timeout(config)}`
(the prompt-only chain and the retrieval chain).

#### (d) `agent/config.json` lines 19–20

```jsonc
  "unified_agent_llm_step_timeout_seconds": 900,   // was 180
  "llm_client_timeout_seconds": 600,               // new
```

**The watchdog (900) must exceed the client bound (600)**, otherwise the watchdog
abandons the attempt before the HTTP call is allowed to finish — which would
reproduce the original symptom with a different number.

### 3.4 Verified live

```
--- [LLM-TIMEOUT] one Ollama call may take up to 600s (llm_client_timeout_seconds) ---
[OLLAMA-TIMING] Ollama took 23.1s to answer
[OLLAMA-TIMING] Ollama took 66.4s to answer
```

No further `FAILED after 120.0s`. The run progressed to iteration 39+ and
produced the document.

---

## 4. DEFECT 3 — the destructive rung fired on an infrastructure blip

### 4.1 Symptom

A re-compile came back:

```
[7] MODEL    - request: Ollama call failed: timed out
[8] BISECT   + quarantine: quarantined 1 of 110 block(s) after 14 probe(s): block(s) 10
DEGRADED BUILD -- block(s) 10 could not be typeset and were REMOVED from the PDF.
⚠️ LaTeXer compile did not succeed (status=degraded).
```

A clean 27-page PDF became a **26-page** one with a block of Angela's document
deleted.

### 4.2 Root cause

`bisect` is rung 8 — the true last resort — and it is the **only rung that
deletes the author's content**. It is correctly placed last. But rung 7
(`model`) is the last *non-destructive* repair, and when its call merely **timed
out**, the ladder had not actually exhausted its safe options. It proceeded to
cut anyway. A network blip cost Angela a paragraph.

### 4.3 The fix — line by line

#### (a) `agent/agents/latexer/latexer.py` lines 4126–4149 — the discriminator

```python
_MODEL_UNREACHABLE_MARKERS = (
    "timed out", "timeout", "unreachable", "connection", "refused",
    "call failed", "not configured", "no response",
)


def _model_rung_never_answered(trace) -> bool:
```

* walks the ladder trace **backwards** and finds the most recent `model` record;
* returns **True** when that record's detail matches an infrastructure marker
  ("we never reached the model");
* returns **False** when the model actually answered and simply could not help
  (e.g. *"the model's rewrite still does not compile — discarded"*) — a genuinely
  exhausted repair, so bisect **may** proceed;
* returns **False** when rung 7 never ran at all (disabled) — preserving the old
  behaviour;
* on an exception returns **True** — fail-**safe** toward *protecting the
  document*, which is the opposite direction from most fail-open guards in this
  codebase, and deliberately so: losing the user's work is the worst outcome
  available.

#### (b) `agent/agents/latexer/latexer.py` line 4101 — the guard

```python
    if "bisect" in rungs and _model_rung_never_answered(trace):
        trace.append(_repair_record(
            "bisect", "skipped",
            "NOT cutting any content: the model rung could not be reached "
            "(timeout / unreachable), so the non-destructive repairs were never "
            "really exhausted. Fix the model connection (or raise "
            "repair_model_timeout) and re-run; the document is left intact.",
            False))
    elif "bisect" in rungs:
        outcome = _bisect_failing_blocks(...)
```

The skip is **recorded in the audit trace**, so the user is told the ladder
declined to cut and exactly why — it is never silent.

#### (c) `agent/agents/latexer/config.yaml` line 190 — give rung 7 a real chance

```yaml
repair_model_timeout: 600   # was 180 - a 60 KB .tex made the model rung time out,
                            # which used to hand the job to the DESTRUCTIVE bisect
                            # rung and cost Angela a block of her OpenMP guide.
```

A 60 KB `.tex` sent to a cloud model does not answer in 180 s. Raising this is
what stops the timeout happening in the first place; the guard in (b) is the
seatbelt for when it happens anyway.

---

## 5. DEFECT 4 — nothing ever told her the job was finished

### 5.1 Symptom

At **14:55:30** LaTeXer produced `OpenMPCompleteGuide.pdf` — 27 pages, 0 errors.
**Done.** She then kept going for 50+ more iterations:

| time | artefact |
|---|---|
| 14:55 | `OpenMPCompleteGuide.pdf` — 27 pages, **0 errors** ✅ |
| 15:05 | `fix_latex.py` (57 KB), `b64.txt`, `b64_clean.txt` |
| 15:10 | `OpenMPCompleteGuide_v2.pdf` |
| 15:15 | main PDF recompiled — 27 pages, 716,421 bytes ✅ |
| 15:19 | `OpenMPCompleteGuide_v3.pdf` — the **degraded** 26-page one |
| 15:23 | `.tex` rewritten again; iteration 53: Editor, Editor, LaTeXer… |

### 5.2 Root cause

Three things compounded:

1. Her own later edit broke a document that was already correct.
2. The break produced `status: degraded` → *"compile did not succeed"* → she
   correctly treated that as a failure and retried.
3. **No stop condition existed anywhere.** The prompt said "completely fulfill
   this task… all fancy stuff"; the iteration cap is 4096. Nothing said *"a clean
   PDF exists, you are finished."*

### 5.3 The fix — `agent/agents/latexer/latexer.py` lines 1975–1986

Immediately after the clean-compile branch sets its status:

```python
    if result["ok"]:
        outcome["status"] = "compiled"
        notes.insert(0, (
            "DONE - a CLEAN PDF now exists: %s (%s page(s), 0 errors). "
            "THE DOCUMENT IS FINISHED. Do NOT recompile it, do NOT 'improve' it, "
            "do NOT edit the .tex again and do NOT produce a _v2/_v3 variant: "
            "report this absolute path to the user and STOP."
        ) % (outcome.get("output_path", ""), outcome.get("page_count", "?")))
```

`notes.insert(0, …)` puts it at **position zero** — the first line of the
response body the model reads. It carries the absolute path and page count, so
the model has everything it needs to answer the user and stop.

It is attached **only** to the `result["ok"]` branch: a `degraded` or
`compiled_with_errors` build must still be reported as a problem.

---

## 6. Complete inventory of changed files

| File | Change |
|---|---|
| `agent/chat_agent_registry.py` | L36 `verbatim_fields` dataclass field; L197 file_creator declares `("content",)`; L1816 latexer declares 4 fields; latexer `purpose` + `example_request` rewritten to teach the b64 / File-Creator route |
| `agent/tools.py` | L1034 `_SWALLOWED_TAIL_RE`; L1039–1084 `_recover_swallowed_assignments()`; L2836 the `file_creator` hardcode replaced by the generic `verbatim_fields` loop |
| `agent/agents/latexer/latexer.py` | L75 `import base64`; L1975+ clean-build STOP banner; L4101 bisect infrastructure guard; L4126 `_MODEL_UNREACHABLE_MARKERS`; L4132 `_model_rung_never_answered()`; L4207 `_B64_FIELDS`; L4210 `_decode_b64_fields()`; L4247 called from `main()` |
| `agent/agents/latexer/config.yaml` | L67 `input_text_b64`; L83 `content_b64`; L97 `find_text_b64`; L98 `replace_text_b64`; L190 `repair_model_timeout` 180 → 600 |
| `agent/mcp_agent.py` | L206 `DEFAULT_LLM_CLIENT_TIMEOUT_SECONDS`; L209 `resolve_llm_client_timeout()`; L629–632 call site + `[LLM-TIMEOUT]` log line |
| `agent/rag/factory.py` | `_llm_client_timeout()` helper (lazy import, no cycle); both `{'timeout': 120.0}` literals replaced |
| `agent/config.json` | L19 `unified_agent_llm_step_timeout_seconds` 180 → 900; L20 `llm_client_timeout_seconds: 600` (new) |
| `agent/test_latexer_verbatim_channel.py` | **NEW** — 19 regression tests |
| `.claude/skills/tlamatini-daily-chat-test/harness/latexer_openmp_e2e.py` | **NEW** — visible end-to-end GUI replay |

Lint: `python -m ruff check` — **All checks passed** on every touched file.

---

## 7. The 19 regression tests

`Tlamatini/agent/test_latexer_verbatim_channel.py`, run with
`python Tlamatini/manage.py test agent.test_latexer_verbatim_channel -v 2`.

**`LatexerVerbatimChannelTests`**
1. `test_spec_declares_its_literal_fields` — the 4 fields are declared
2. `test_row_breaks_survive_plain_input_text` — **THE regression**: `\\` count in == out
3. `test_trailing_keys_are_not_swallowed_into_the_body` — `filename`/`output_dir` recovered, body clean
4. `test_b64_channel_wins_and_plain_field_is_left_alone`
5. `test_recovery_never_cuts_genuine_latex` — a body containing `', banana='yes'` is untouched

**`LatexerBase64ConfigTests`**
6. `test_agent_decodes_every_declared_literal_field`
7. `test_config_yaml_exposes_every_b64_key` — missing key = silently dropped value
8. `test_b64_overrides_the_plain_field`
9. `test_malformed_b64_is_fail_open`
10. `test_absent_b64_changes_nothing`

**`NeverLoseTheAuthorsWorkTests`**
11. `test_timeout_counts_as_never_answered`
12. `test_a_real_model_verdict_does_not_block_bisect`
13. `test_no_model_rung_keeps_the_old_behaviour`
14. `test_fail_safe_protects_the_document_on_bad_input`
15. `test_ladder_actually_guards_the_bisect_rung` — source contract

**`CleanBuildIsTheEndOfTheJobTests`**
16. `test_clean_compile_emits_an_explicit_stop` — and that it is on the `ok` branch
17. `test_model_repair_timeout_is_generous_enough_for_a_real_document`

**`ByteExactWiringContractTests`**
18. `test_tools_no_longer_hardcodes_file_creator` — **fails if anyone re-adds
    `if spec.template_dir == "file_creator":`**
19. `test_file_creator_keeps_its_byte_exact_content` — the original Java-regex
    corruption stays fixed

Pool agents cannot be imported (module-level side effects truncate their `.log`),
so `_lift_function` / `_lift_constant` **AST-lift** the functions under test out
of `latexer.py` — the same technique `test_django_port_config.py` uses for
`manage.py`.

**Result: `Ran 19 tests … OK`**, executed in a **visible foreground window**,
with a full-desktop screenshot taken by Tlamatini's **Shoter** agent.

---

## 8. The end-to-end proof

`.claude/skills/tlamatini-daily-chat-test/harness/latexer_openmp_e2e.py`

* **Headed Chrome only** — reuses `run_test.Harness`, which refuses headless.
* Logs into the real chat GUI as `angela`, clears history, forces Multi-Turn ON /
  Exec-Report ON / ACPX OFF / Ask-Execs OFF.
* Sends **Angela's request verbatim**, with only the two paths substituted.
* Uses `ask_one()` so a freshly-booted *"Your agent is loading"* reply is waited
  out and resent — never recorded as the answer.
* **The verdict is filesystem truth, not prose**: a `.tex` and a real PDF
  (> 20 KB) must exist on disk. A confident answer with no PDF is a FAIL.
* Screenshots via **Shoter** (`take_shot`), never `PIL.ImageGrab`.
* Uses Angela's original `.cu` automatically when present; otherwise writes an
  equivalent OpenMP fixture (her original was deleted from disk at 12:26 today).

### Result

```
tools.py: file_creator.content re-extracted VERBATIM (61951 chars, no escape decoding)
LATEXER AGENT STARTED (LaTeX typesetting) -> pdflatex
Output written on OpenMPCompleteGuide.pdf (27 pages, 716421 bytes).
LaTeX errors: 0
```

Tlamatini read the source, wrote a 61,951-character `.tex` **byte-exact**, and
compiled a 27-page PDF — the exact job that produced an empty folder before.

A second document was also delivered to Angela's Desktop, rebuilt from the `.tex`
Tlamatini had designed in the failed run (recovered out of DB msg 50):
`CompleteOpenMPImplementation_Explained.pdf` — 10 pages, 0 errors.

---

## 9. Things deliberately NOT changed

* **`_split_assignment_segments` multi-line rule.** Its "stay open until EOF or a
  conjunction" behaviour protects multi-line scripts containing apostrophes
  (`don't`, `node's`). Changing it would touch all 80+ agents. The recovery
  helper solves the LaTeX case without that blast radius.
* **The ladder's rung ORDER.** `bisect` stays strictly last. Only the *condition*
  under which it may run was tightened.
* **LaTeXer's repair-ladder escalation.** It was investigated and found
  **correct** — it escalated because the document genuinely had 5 errors,
  quarantined nothing, and reported `compiled_with_errors` honestly.
* **Grepper.** Its `not_found` was investigated and found **correct** — the
  `.cu` really had been deleted.

---

## 10. Open items

1. **Angela's original `CompleteOpenMPImplementation.cu` was deleted** from
   `C:\Tlamatini\context_files\` at 12:26 on 2026-08-11 and is gone machine-wide.
   The harness replays against the real file the moment it is restored.
2. `latexer.py` line 3894 still carries an in-code fallback of `180` for
   `repair_model_timeout`; the shipped `config.yaml` value (600) is what real runs
   use. Aligning the literal would be tidier.
3. These changes are on the **dev source tree** (`C:\Development\Tlamatini`). A
   `build.py` run is required to carry them into the frozen install
   (`C:\Tlamatini`).

---

## 11. One-line summary

> LaTeXer was never broken. **The road to it was.** Four things — a hardcoded
> byte-exact channel, a hardcoded 120 s timeout, a destructive repair rung that
> fired on a network blip, and no definition of "done" — together turned a
> working typesetting agent into an empty folder. All four are fixed, pinned by
> 19 tests, and proven end to end by Tlamatini building a 27-page PDF herself.

*Prepared for **Angela López Mendoza**, creator of Tlamatini.*
