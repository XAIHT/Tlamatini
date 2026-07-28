# Asymmetric Localization of an LLM Operator System

### Why a Spanish Tlamatini must not translate, and what must change instead

**Author of the system under study:** Angela López Mendoza (XAIHT / Tlamatini)
**Analysis:** Claude Opus 5, multi-agent forensic study of the Tlamatini codebase at commit `3e6d514f` (v1.47.0)
**Date:** 2026-07-27
**Status:** Research paper — no Tlamatini source code was modified in its production.

---

## Abstract

We study the problem of delivering a Spanish-language build of **Tlamatini**, a locally deployed LLM *operator* system (86 workflow agents, 44 direct tools, a Multi-Turn tool loop, a visual flow designer) whose users may bind an arbitrary set of backend models. The conventional engineering answer — a Spanish→English→Spanish translation pivot with a capability probe deciding when to engage it — is, we argue, **the wrong architecture for this class of system**, and the probe conventionally proposed for it is **not a valid measurement instrument**.

We advance three claims and support each with verified external evidence and with direct measurement of the system.

1. **The capability premise is false.** For Spanish specifically, the model-side gap is 1–4 accuracy points on knowledge and reasoning [xuan2025mmluprox; thellmann2024european], approximately **zero on tool selection** (GPT‑5 pass^3: ES 0.93 vs EN 0.92 — Spanish is its *best* language [almeida2025ticketbench]), and mechanistically attributable to an *understanding* stage that is already near-saturated for Spanish (93.9% → 94.7% under a perfect understanding intervention, versus Swahili 29.3% → 88.0% [kang2026whygaps]). There is no capability deficit for a pivot to recover.

2. **The real defect is substrate monolingualism, and it is severe.** Tlamatini's *deterministic control plane* — not its model — is monolingually English at the tokenizer level. We counted **≈2,389 hardcoded English lexical items** across the routing, planning, validation and classification paths, **none** containing a non-ASCII character, and we executed the real scoring function over the real 64-agent registry with twelve matched prompt pairs: **English top‑1 tool selection 10/12; Spanish top‑1 0/12**, with the semantically correct tool scoring *exactly zero* in 7 of 12 Spanish cases. This is not degradation; it is a different program.

3. **The correct architecture is Asymmetric Localization.** Program text (system prompt, tool names, JSON schemas, protocol sentinels) stays English and byte-stable; user content passes through untranslated; the answer is generated natively in Spanish; and the deterministic core is made *language-neutral* rather than bilingual. We formalize the two invariants this requires — the **Identifier/Label Separation Theorem** and its previously unstated inverse, the **Label Round-Trip Prohibition** — and show that the inverse is violated in three places in the current code, two of which would cause *permanent, silent, unrecoverable* capability loss if the GUI were naively translated.

We further show that Asymmetric Localization is not free: an English system prompt places every request in the **cross-lingual condition**, empirically the harder one for output-language fidelity (GPT‑4o line-level pass rate 99.3% monolingual → 95.8% cross-lingual [marchisio2024langconfusion]). We specify the precise, evidence-backed compensation (few-shot exemplars: 1.1% → 95.0% in the same study; low temperature: 97.2% → 86.5% degradation from T=0 to T=1) and a **read-only** output guard, and we argue from first principles that a *repairing* guard driven by an uncalibrated detector is a corruption engine rather than a safety net.

Finally we give a falsifiable evaluation protocol: parity stated as a pre-registered **non-inferiority** hypothesis (δ = 0.05 on programmatic task success), analysed with Tango's score confidence interval on paired proportions, powered at 250 paired items, gated on **assay sensitivity** via deliberately degraded positive controls, and measured with a judge whose *differential* language bias is quantified before it is trusted.

---

## 1. Introduction

### 1.1 The request, stated precisely

Tlamatini must become fully usable in Spanish: its graphical interface translated, its processing conducted in Spanish, and — the binding constraint — the Spanish build must be **as effective as the English build, or better**, across a heterogeneous and user-selected set of backend models (local Ollama models, Anthropic Claude, cloud models such as `glm-5.2:cloud`, and vision models).

The word *effective* is doing heavy lifting. Tlamatini is not a chat assistant that produces prose. It is an **operator**: it selects among 86 agents and 44 tools, extracts byte-exact arguments (Windows paths, filenames, flags, ports, serial devices, firmware board identifiers), sequences multi-step plans, gates destructive actions behind a permission broker, and emits machine-parsed protocol tokens that other programs branch on. "Effective" therefore means *the machine does the right thing*, not *the sentence reads well*. This distinction determines the entire architecture, and it is the distinction that a translation-pivot design erases.

### 1.2 The prior proposal and why it must be re-examined

The engineering study handed to us (`LLMSpanishEnglishResearch.md`) frames the decision as a binary between direct multilingual execution and an ES→EN→ES pivot, correctly enumerates the pivot's failure modes (compound error, pragmatics stripping, fluency masking), and then proposes a *dynamic router*: probe the target model with a Spanish control prompt; if it passes, run direct; if it fails, engage the pivot through a fallback translator.

That document's diagnosis of pivot pathology is sound and we adopt it. Its *remedy* has three defects we must correct before building anything.

**Defect 1 — the probe is not a measurement.** The primary probe is:

> *"Instrucción: Responde ÚNICAMENTE con la palabra 'CONFIRMADO' si puedes entender y procesar este mensaje en español perfectamente."*

This is a **self-report elicited by an instruction**, and it conflates three unrelated constructs: (a) whether the model can follow a one-token output constraint, (b) whether it *believes* it understands Spanish, and (c) whether it can *generate* competent Spanish under production conditions. Only (a) is actually measured. Every model Tlamatini would plausibly run saturates (a) at ≈1.0, so the item has no variance and therefore no discriminative power: it is an offset, not a test.

The fallback probe is worse. It generates one sentence and counts membership in a marker list `["el","la","es","que","una","estrella","sol"]`, passing at ≥3 matches. Portuguese (*"o sol é uma estrela que..."* → `es`, `que`, `una`-adjacent), Italian, Catalan and Galician all trip it; so does a fluent Spanish *hallucination*; so does a Spanish sentence that answers the wrong question. It measures orthographic surface, not competence, and it cannot distinguish "the model speaks Spanish" from "the model emitted Spanish-looking characters."

**Defect 2 — the output is a boolean where the decision needs a vector.** A single bit cannot express the empirically distinct facts that a model may be excellent at Spanish prose, adequate at Spanish instruction-following, and *unreliable at emitting a byte-exact `INI_SECTION_STM32ER<<<` block under a Spanish instruction*. For an operator system the last of these is the one that breaks production, and it is precisely the one a prose probe cannot see.

**Defect 3 — the fallback is the wrong fallback.** Engaging an ES→EN→ES pivot for an operator request does not degrade gracefully; it destroys the payload. We formalize this in §4.

**Defect 4 — the transport is provider-specific.** The reference implementation hardcodes `http://localhost:11434` and Ollama's `/api/generate`. Tlamatini's users bind Anthropic and cloud endpoints as first-class backends. A probe that cannot see the model the user actually selected certifies nothing.

None of this is a criticism of the prior document's contribution — its failure-mode taxonomy is correct and we build on it. But a probe that cannot fail is not a gate, and a fallback that corrupts arguments is not a safety net.

### 1.3 Contributions

- **§3** An empirical characterization of *substrate monolingualism* in a real 700-file operator codebase, with executed measurements rather than inspection.
- **§4** A formal argument against translation pivots for operator systems, with a literal-preservation decay model that explains why the pivot's harm is superlinear in the number of arguments.
- **§5** Two invariants — the Identifier/Label Separation Theorem and the Label Round-Trip Prohibition — with three verified violations in the current system.
- **§6** The Asymmetric Localization architecture, its token-cost model, and its explicitly acknowledged liability (the cross-lingual language-fidelity tax) with the evidence-backed compensation.
- **§7** A capability probe with construct validity: production-cell framing, elicitation gates for machine sentinels, per-path routing, and calibration against data the project already owns.
- **§8** A falsifiable non-inferiority evaluation protocol with assay sensitivity.
- **§9** Threats to validity, stated honestly.

### 1.4 Method

All codebase claims in this paper were produced by fourteen parallel analysis agents reading the repository directly (684 tool invocations), each required to attach `file:line` evidence it had observed. Every scientific claim was then subjected to an adversarial verification pass: an independent agent re-fetched each of the ~71 cited works to confirm title, authors, year and identifier, and separately re-verified the numeric values against the source tables. That pass found **one misattributed reference**, which we removed (see §10.4), and roughly ten metadata corrections, which we applied. Two further adversarial agents attempted to refute the architecture; their surviving objections are incorporated into the design rather than rebutted, and are recorded in §10.

---

## 2. The System Under Study

Tlamatini's relevant structure is a five-layer stack in which **the language boundary cuts across four of the five layers**, which is why localization is not a presentation-layer concern.

| Layer | Content | Language exposure |
|---|---|---|
| Presentation | 4 Django templates (1,109 lines), 32 vanilla-JS modules, 10 stylesheets (~203 KB) | ~261 literal strings in templates; the *majority* of dialog chrome is injected from JS literals at runtime |
| Protocol | WebSocket frames, 18 families of machine sentinel (`END-RESPONSE`, `BEGIN-CODE<<<…>>>`, `INI_SECTION_<T><<<`, `TLM_VERDICT::`, `VERDICT: APPROVE\|REQUEST_CHANGES\|COMMENT`, …) | Must be **byte-invariant** across languages |
| Deterministic control plane | Capability scoring, execution planner, prompt-shape gate, access validation, internet classifier, argument parser, failure classifier | **≈2,389 hardcoded English lexemes**, zero non-ASCII |
| Model interface | `prompt.pmt` (310+ lines, 19 numbered rules), tool schemas, tool descriptions | English program text, doubling as scoring input |
| Data | 86 agent display names, 113 catalog prompts, `agents_descriptions.md`, `Tool`/`Mcp`/`Agent`/`Skill` rows | Mixed: some rows are *identifiers*, some are *labels*, and the code does not distinguish them |

Two structural facts govern everything downstream.

**Fact A — there is no internationalization infrastructure whatsoever.** Across 701 files there are exactly two matches for the entire i18n vocabulary: `LANGUAGE_CODE = 'en-us'` and `USE_I18N = True`, both Django defaults, at `Tlamatini/tlamatini/settings.py:200,204`. There are zero `{% trans %}` tags, zero `gettext` calls, no `LOCALE_PATHS`, no `LocaleMiddleware`, no `locale/` directory. All four templates hardcode `<html lang="en">`. This is a greenfield decision, not a migration.

**Fact B — human-readable names are load-bearing program identifiers.** An agent's display name (`STM32er`, `File-Creator`, `Kyber-KeyGen`) is simultaneously: the sidebar label; the value of a `data-content` attribute matched by **56 case-sensitive CSS attribute selectors**; the operand of ~512 lowercased string comparisons in the canvas connection handlers; the key of the enable gate `agent_<display>_status`; the caption of the Exec Report; and the discriminant in 138 `case` labels in the `.flw` loader. The project's own documentation already records that changing a hyphen to a space in one of these names *silently stops canvas connections from being persisted, with no error anywhere*. The naming convention is not cosmetic; it is an ABI.

---

## 3. Substrate Monolingualism: Measured, Not Inferred

This section reports what the system actually does when addressed in Spanish. These are not projections; the analysis executed the real functions against the real registries.

### 3.1 The tokenizer destroys Spanish before any logic runs

The single tokenizer used by every scoring path is

```python
_TOKEN_RE = re.compile(r"[a-z0-9_]+")     # capability_registry.py:20
```

Applied after lowercasing, **every non-ASCII byte is a delimiter**, and single-character fragments are dropped. Measured against the live function:

| Spanish input | Tokens produced |
|---|---|
| `código` | `['digo']` |
| `análisis` | `['lisis']` |
| `ejecución` | `['ejecuci']` |
| `contraseña` | `['contrase']` |
| `años` | `['os']` |
| `envía` | `['env']` |
| `configuración` | `['configuraci']` |

Three consequences follow. First, the token-overlap term of the scorer (worth up to +10) is **structurally zero** for accented Spanish: a fragment can never equal an English hint token. Second, behaviour is **non-deterministic across keyboards**: `ejecucion` tokenizes to `['ejecucion']` but `ejecución` to `['ejecuci']`, so the same intent scores differently depending on whether the user typed the accent. Third, the defect propagates: `global_execution_planner` and the Multi-Turn tool-budget selector both import this tokenizer, so one line of code compromises three independent consumers.

### 3.2 Tool selection collapses to zero, and then goes negative

Running the real `_score_capability` over the real 64-specification registry with twelve matched English/Spanish prompt pairs:

| | English | Spanish |
|---|---|---|
| Top-1 correct tool | **10 / 12** | **0 / 12** |
| Correct tool scored exactly 0 | 0 / 12 | **7 / 12** |

The English scores are healthy (`send_email` 44, `shoter` 34, `summarize` 32, `grepper` 32). The Spanish scores are not merely weak — the ranking is **actively adversarial**, because phrase matching is unbounded substring containment (`phrase in request_text`) rather than word-boundary matching, and 107 of the registry's alias/hint phrases are ≤4 characters.

The canonical demonstration: for the Spanish prompt *"envía un correo de prueba a soporte"* ("send a test email to support"), `chat_agent_unrealer` scores **24 and ranks first**, because its alias `ue` and its hint `ue` both match inside **prue**ba (+12, +10). The semantically correct `chat_agent_send_email` scores **0** and does not appear in the positive list at all. The substring `ue` occurs in *que, puede, fue, aunque, muestra, respuesta, nuevo, bueno* — a large fraction of all Spanish sentences — making Unrealer a permanent phantom top hit. It took top-1 in 4 of the 12 Spanish cases.

Other verified homograph traps: `uno`/`ino` (Arduiner) inside *uno, camino, destino, término*; `pio` (ESP32er) inside *limpio, propio, principio*; `pod` (Kuberneter) inside *poder, podemos*; `pid` and `api` (PSer, Apirer) both inside *rápido*; `ls` (Globber) inside *falso, pulsar*; `git` (Gitter) inside *digital, legítimo*; `spa` (Playwrighter) inside *espacio, España*. And a subtler one: the Spanish word *imagen* **contains** the English `image`, which is a hint for both Image-Interpreter and Dockerer; they tie at 10 and the tie-break is *registry index*, so **Dockerer outranks Image-Interpreter on "interpreta la imagen"**.

Compounding this, the 37-word stopword list is English-only, so Spanish function words survive into the token set. Because `chat_agent_de_compresser` splits into tokens `('chat','agent','de','compresser')`, the Spanish preposition **`de` awards +2 to De-Compresser on essentially every Spanish sentence**.

### 3.3 The planner then fails *closed*

The two consumers of the score disagree on polarity. `capability_registry.select_tools_for_request` fails **open** (returns the full tool list when nothing scores). `global_execution_planner._select_planner_tool_names` fails **closed**: when nothing crosses threshold it returns empty tuples and the note *"No tool or agent capability crossed the planner threshold"*, `build_global_execution_plan` sets `execution_mode='direct_model'`, and the summary line **"Selected tools/agents: none"** is injected into the system prompt.

Verified: the Spanish prompt *"Borra los archivos temporales de esa carpeta"* ("delete the temporary files in that folder") produces zero positive-scoring capabilities, so the planner explicitly tells the model that no tool stage is needed — **for a destructive file operation**.

There is a second-order effect. When the full tool surface exceeds the context budget, bind order is decided by the same scorer; under Spanish input the planner set is empty and virtually every score is zero, so the sort key degenerates to `(0, 0, name)` and the surviving non-core tools are selected **alphabetically**. The Spanish operator is left with the 16 English-named core tools and whatever specialist agents happen to sort early.

### 3.4 The prompt gate rejects Spanish outright

`is_valid_prompt` admits a prompt if it ends in `?`, or begins with one of 119 English question-words, or matches one of 36 English multiword patterns, or if NLTK's **English** POS tagger labels the first token a verb. Executed against the live function with NLTK installed:

| Spanish prompt | Verdict |
|---|---|
| `Toma una captura de pantalla del escritorio` | **rejected** |
| `Crea un archivo llamado notas.txt` | **rejected** |
| `Ejecuta el comando dir` | **rejected** |
| `Envía un correo a soporte` | **rejected** |
| `Muéstrame los archivos del proyecto` | **rejected** |
| `Por favor analiza este documento` | **rejected** |
| `Necesito que borres los archivos temporales` | **rejected** |
| `¿Qué hora es?` | accepted — *because of the `?`* |
| `Resume este texto` | accepted — *because `resume` is an English homograph* |

Seven of eight well-formed Spanish commands are refused, in English (*"Please rephrase your input as a clear question or command…"*). Both acceptances are accidents. The gate is bypassed only when Multi-Turn, ACPX or Step-by-Step is on — so it is precisely the *plain-chat* Spanish user, the least technical one, who is blocked.

### 3.5 A Spanish conjunction corrupts file paths

The wrapped chat-agent argument parser recognizes exactly two natural-language separators, `and` and `with`:

```python
_CONJUNCTION_ASSIGNMENT_RE = re.compile(
    r'(and|with)\s+[A-Za-z_][A-Za-z0-9_.\-]*\s*=', re.IGNORECASE)   # tools.py:431
```

Executed against the real parser:

```
Input : Crea un archivo con filepath='C:/Temp/a.txt' y content='hola'
Parsed: {'requested_key': 'filepath',
         'value': "C:/Temp/a.txt' y content='hola"}
```

This is not a routing miss. It is **data corruption**: File-Creator would create a file literally named `C:/Temp/a.txt' y content='hola`, and every subsequent parameter is silently lost. The same failure occurs with *con* and *además*. The irony is exact: `con` is the Spanish translation of the `with` the parser does handle.

### 3.6 A Spanish failure is recorded as a success

`_result_is_failure` correctly reads structured JSON status fields, but for plain-text results it tests eleven English prefixes (`error:`, `unable to`, `cannot`, `permission denied`, `unauthorized`, …). Spanish and OS-localized equivalents — *No se puede*, *No se pudo*, *Acceso denegado*, *Excepción:*, *El sistema no puede encontrar la ruta especificada* — match nothing, so the call is scored **SUCCESS**.

This single classifier feeds the Exec Report verdict, the corrective-feedback loop, the repetition breaker, **and the Create-Flow button**, which builds a downloadable `.flw` from only the successfully-executed calls. A failed Spanish-locale step is therefore silently baked into a saved workflow as a working node.

### 3.7 Failures with no Spanish prompt involved at all

Two mechanisms fail on a Spanish *machine*, regardless of the user's language. `Monitor-Netstat` runs `netstat -an` with `text=True` and no codepage forcing, then greps for `LISTENING`; a Spanish Windows prints **`ESCUCHANDO`**. And Forker/Raiser/Stopper do case-sensitive substring matching of user-authored patterns against logs, with no "pattern never matched" warning — so a Spanish pattern simply causes the flow to hang silently in its polling loop.

### 3.8 What survives — and why it matters

The analysis explicitly verified that the **safety, audit and deduplication layer is language-neutral by construction**: the Ask-Execs permission allowlist, the Exec-Report map, shell inference, the dedup signature and the wrapped-run status are all keyed on *tool names*, JSON argument keys and exit codes, never on prose. The Parametrizer's `INI_SECTION` grammar is ASCII-structural, reads logs as UTF‑8 with `errors='replace'`, and writes YAML with `allow_unicode=True`.

This bounds the blast radius precisely, and it is the most important positive finding in the study:

> **A Spanish operator keeps the permission gate and the audit trail. What they lose is the ability to have the correct tool selected in the first place.**

The failure is one of *routing and parsing*, not of *safety*. That is what makes the problem tractable.

### 3.9 Summary of the measured surface

| Surface | Magnitude | Nature |
|---|---|---|
| Template strings | ~261 literal + majority injected from JS | Translatable chrome |
| JS `:contains("English")` selectors | **66** across 6 files (18× `Cancel`, 11× `Continue`, 9× `Save`, 8× `OK`, 2× `Proceed`, 2× `Deny`, …) | Button *labels used as selectors* |
| CSS attribute selectors on display names | **56** `.agent-tool-item[data-content="Name"]` | Identifier, case-sensitive |
| Canvas lowercased name comparisons | ~512 | Identifier |
| `.flw` loader `case` labels | 138 | Identifier |
| Hardcoded English lexemes in control plane | **≈2,389** (0 non-ASCII) | Deterministic logic |
| Fixed-pixel layout declarations | 125 across 7 stylesheets, plus 22 fixed dialog widths | Expansion risk (ES text +15–30%) |
| Machine sentinel families | 18 | **Byte-invariant** |
| Catalog prompts | 113 rows | Dual: UI content *and* model input |

---

## 4. The Formal Case Against a Translation Pivot for Operator Systems

The prior study models pivot degradation multiplicatively:

$$F_{\text{system}} = (1-\epsilon_1)\,(1-\epsilon_2)\,F_{\text{LLM}}$$

This is correct but **weak**, because it treats fidelity as a continuous quality scalar. For an operator system the relevant loss is not continuous. We give the stronger model.

### 4.1 Operator success is conjunctive over literals

Let a request carry $k$ **literals** that must survive to the tool call byte-exactly: absolute paths, filenames, flags, port numbers, board identifiers, git refs, agent names. Let $p$ be the per-literal probability that one machine-translation hop preserves a literal exactly. Task success requires *all* of them:

$$P(\text{args intact}) = p^{k}$$

Two properties make this devastating where prose translation is benign.

**It is conjunctive.** A prose translation that damages one word in twenty loses 5% of quality. A tool call that damages one path in twenty **fails completely**. There is no partial credit at the filesystem.

**It is superlinear in task complexity.** Tlamatini's real requests are literal-dense. A modest firmware instruction — *"crea el proyecto en `C:\Tlamatini\Templates\leg_ctrl`, con board `bluepill_f103c8`, compílalo y flashéalo por el ST-LINK a 115200"* — carries $k \approx 6$. Even at a generous $p = 0.98$:

| $p$ | $k=2$ | $k=4$ | $k=6$ | $k=10$ |
|---|---|---|---|---|
| 0.99 | 0.980 | 0.961 | 0.941 | 0.904 |
| 0.98 | 0.960 | 0.922 | 0.886 | 0.817 |
| 0.95 | 0.903 | 0.815 | 0.735 | 0.599 |

An 11% absolute failure rate injected at $k=6, p=0.98$ dwarfs the 1–4 point model-side Spanish gap the pivot was introduced to close. **The remedy is an order of magnitude worse than the disease.**

And $p$ is not close to 1 for exactly these tokens. MT systems are trained to *translate*, and a Windows path with a Spanish folder name (`C:\Usuarios\angela\Documentos\informe_año.pdf`) is precisely the input an MT system is most likely to "helpfully" normalize, transliterate, or strip diacritics from. The published multilingual tool-calling literature independently identifies this as the dominant failure mode: models "select correct tools and understand intent but generate parameter values in non-English languages, violating the English-only execution interface" [luo2026lostinexecution], corroborated by schema-violation and language-matching findings in the International Tool Calling dataset [zhang2026itc].

### 4.2 Fluency masking is an epistemic harm, not merely a quality harm

The prior study names "fluency masking" correctly. We sharpen it. The EN→ES stage is a **fluency-restoring operator**: it takes text of arbitrary correctness and emits grammatical, idiomatic Spanish. Its effect on the user's ability to detect an error is to *reduce the mutual information between the output's surface form and its correctness*.

In the direct architecture, a model that misunderstood a Spanish request usually produces text that reads slightly off — an awkward paraphrase, a mismatched register, a hedge. Those are the cues a competent user reads to catch the error. Run the same wrong answer through an MT polisher and the cues are gone: the output is fluent, confident, and wrong. **The pivot does not merely add errors; it removes the user's error-detection channel.** For a system that executes destructive operations behind a permission dialog whose text the user is expected to read and judge, this is a safety property, not an aesthetic one.

### 4.3 Latency and the Multi-Turn multiplier

Tlamatini's Multi-Turn executor is configured for up to 4,096 iterations and wraps every model step in a self-healing invoker with an 80 s watchdog. A pivot adds two model round-trips **per turn**. In a ten-tool operator run that is twenty extra model calls, twenty extra failure surfaces for the self-healing ladder to absorb, and twenty extra opportunities for the tool-call arguments to be re-translated. The project's own stated north star is per-request chat latency. A pivot is directly opposed to it.

### 4.4 What the literature actually says

The historical case for translate-test is real but **narrowly scoped to low-resource, non-Latin-script languages**. MEGA finds translate-test gains "even more substantial" on IndicXNLI and XStoryCloze and >30% relative improvement for Burmese, Tamil and Telugu, while "performing similarly to monolingual approaches for high-resource languages" [ahuja2023mega]. For real user queries in high-resource languages, translation *loses*: prompting with original queries has the higher win rate for Japanese, Chinese **and Spanish** [liu2024translationall].

We report the honest counter-evidence. Self-translate (asking the model to translate its own input to English) beat direct inference on five benchmarks with gains *larger* for high-resource languages [etxaniz2024selftranslate]. But those measurements are on XGLM‑7.5B, LLaMA‑1‑30B, BLOOM and PolyLM — 2023-era base models whose Spanish was far weaker than anything Tlamatini would bind. Extrapolating them to 2026 instruction-tuned models is not supported, and the mechanistic evidence points the other way: the understanding-stage deficit that self-translate repairs is worth **+0.8 points for Spanish** and +58.7 for Swahili [kang2026whygaps].

### 4.5 Verdict

The pivot is **dominated**: it costs latency and two error surfaces, it injects a conjunctive failure mode of ~10% at realistic literal density, it destroys the user's error-detection channel, and it recovers a capability gap that is ~1–4 points on prose and ~0 on tool selection.

We therefore **eliminate the pivot as an automatic fallback**. If a bound model genuinely cannot serve Spanish (§7), the correct behaviour is not to silently translate — it is to serve English **with an explicit, user-visible notice and a model-switch suggestion**. A silent architecture switch mid-conversation is worse than an honest limitation.

---

## 5. Two Invariants

### 5.1 The four-family classification

Every human-readable string in the system belongs to exactly one family. The current codebase does not make this distinction, which is the root cause of most localization risk.

| Family | Definition | Translatable? | Examples |
|---|---|---|---|
| **MACHINE TOKEN** | Emitted by one component, parsed by another; byte-identity is the contract | **Never** | `END-RESPONSE`, `BEGIN-CODE<<<f>>>`, `INI_SECTION_STM32ER<<<`, `TLM_VERDICT::PASS_OK`, `VERDICT: REQUEST_CHANGES` |
| **IDENTIFIER** | Compared, routed on, persisted, or used as a key | **Never** — but may acquire a *separate* presentation label | `STM32er`, `chat_agent_grepper`, `System-Metrics`, `Files-Search`, config keys |
| **TRANSLATABLE CHROME** | Rendered to a human and never read back | **Yes** | Button captions, dialog titles, tooltips, exec-report column headers |
| **MODEL-FACING PROSE** | Read by the LLM as instruction | **Only behind a capability gate** | `prompt.pmt` rules, tool descriptions |

### 5.2 Theorem 1 — Identifier/Label Separation

> **Every rendered string must be a pure function of an identifier, and no identifier may be a function of a rendered string.**
>
> Formally, let $\mathcal{I}$ be the identifier space and $\mathcal{L}$ the rendered-label space. Localization introduces $\text{render}_\ell : \mathcal{I} \to \mathcal{L}$ for locale $\ell$. The system is localization-safe **iff** every control-flow decision, persistence write, selector match and cache key is a function of $\mathcal{I}$ alone, and $\text{render}_\ell$ has no inverse anywhere in the program.

Under this theorem, the 56 CSS attribute selectors, the ~512 canvas comparisons, the 138 `.flw` case labels, the `agent_<display>_status` gate and the Exec Report `agent_key` are all safe *provided* the display name remains a pure identifier and the localized label is carried in a **separate field**. This is the design's spine, and it means: **agent display names are never translated, in any locale, ever.** Only their *descriptions* (tooltips, the Description dialog, `agents_descriptions.md` Description cells) are.

### 5.3 Theorem 2 — the Label Round-Trip Prohibition

Theorem 1 constrains the render direction. The adversarial review discovered that the *inverse* direction is unguarded and is violated in the live code. We state it as a separate invariant because it is the one that causes permanent damage:

> **No rendered label may be read back out of the presentation layer and used as state.** Concretely: no value obtained from `.innerText` / `.textContent` may flow into a persisted column, a WebSocket payload, a dataset key, a filesystem path, or a selector.

Three verified violations exist today.

**V1 (CRITICAL, permanent, unrecoverable).** The two MCP checkbox labels are bare text nodes in `agent_page.html:315,318` (`System-Metrics`, `Files-Search`). `agent_page_init.js:266` builds the persisted payload from `label_mcp1.innerText`; `consumers.py::save_mcp` writes it into `Mcp.mcpDescription`; and `factory.py:730,734,881,885` compares that column against the literals `'System-Metrics'` / `'Files-Search'` byte-for-byte. `apps.py` rebuilds only the `Agent` table on boot — **`Mcp` is never rebuilt, and the database survives self-update.** Therefore: translate those two labels, and the first time the user opens *Config ▸ Mcps* and clicks Continue, both MCP context providers are disabled **forever**, and re-ticking the boxes cannot revive them.

**V2 (CRITICAL).** The same echo exists for `Tool` and `Agent` descriptions (`agent_page_init.js:283,322` → `save_tool` / `save_agent`). For tools the mismatch fails *open*, so every Configure-Tools checkbox becomes a permanent no-op that lies to the user. For agents it is worse: a localized `agentDescription` desynchronizes the `agent_<display>_status` gate, makes all 56 CSS selectors miss, and makes `_resolveCanonicalAgentName` resolve nothing — so **every successfully executed agent is classed "missing" and silently dropped from the generated `.flw`**.

**V3 (HIGH).** The canvas node's visible label *is* an identifier in two places: `acp-canvas-core.js:562` re-derives the agent name as `originalItem.textContent.split(' (')[0]` on every Ctrl+Drag clone, and `acp-canvas-core.js:1692` serializes the entire connection graph from `c.source.innerText`. The `" ("` cardinal separator is therefore a **wire format**, not decoration.

### 5.4 Corollary — the invariant must be machine-checked in both directions

A theorem enforced only by discipline is not enforced. The design must ship an executable guard: a test that scans the JS tree for any `.innerText` / `.textContent` value flowing into a WebSocket payload, a `fetch` body, a dataset key or a selector, and fails on any new occurrence. The three sites above are the current population; the invariant is only real once the population is pinned at zero.

A second corollary follows for the pseudo-locale used to test layout expansion: a bracket-sentinelled pseudo-locale (`[Ĝéñéŕàţé Ƒļöŵ……]`) must **not** be applied to canvas labels until V3 is fixed, or the very harness meant to prove layout safety becomes the source of a data bug by corrupting `split(' (')[0]`.

---

## 6. Asymmetric Localization

### 6.1 Four planes, three languages

The architecture assigns a language to each plane independently. This is the whole idea, and it is why "translate everything" and "translate nothing" are both wrong.

| Plane | Content | Language | Rationale |
|---|---|---|---|
| **Program text** | System prompt, tool names, JSON schemas, enum values, sentinels | **English, byte-stable** | It is code. Models are strongest on it, it carries no user information, and it must be prompt-cache-stable |
| **User content** | The prompt, pasted text, file contents, arguments | **Untranslated, verbatim** | Zero MT hops ⇒ $p^k = 1$ ⇒ literal fidelity preserved |
| **Answer** | The visible response prose | **Native Spanish, generated directly** | One generation, no pivot; the model's own Spanish is 1–4 points from its English and ~0 on tool selection |
| **Deterministic core** | Scoring, planning, gates, classifiers | **Language-neutral** | Not bilingual — *neutral*. Fold to a canonical form and score on canonical English keys |

The fourth row is the intellectually distinctive one. The intuitive fix for §3 is "add Spanish keywords everywhere" — a bilingual core. That is a maintenance catastrophe: 2,389 lexemes × N languages, each new agent requiring translated hints, and the tuned English behaviour perturbed on every edit. The correct fix is **normalize-then-map**: fold the input to a canonical form, then expand it into the *existing, tuned* canonical English hint tokens via a small data-only lexicon. The scorer's English behaviour is then provably unchanged (an identity guarantee on ASCII input), and the language layer is additive.

### 6.2 The policy, formally

For a request with user text $x$ in language $\ell_u$, target answer language $\ell_a$, and bound model $m$:

$$\text{Prompt}(x) = S_{\text{en}} \;\Vert\; D(\ell_a) \;\Vert\; E_{\ell_a} \;\Vert\; x$$

where $S_{\text{en}}$ is the byte-stable English system prompt, $D(\ell_a)$ is a short output-envelope directive, and $E_{\ell_a}$ is a small set of Spanish few-shot exemplars (§6.4). Reasoning language is **unconstrained**. The answer is generated once, in $\ell_a$.

$D(\ell_a)$ must be expressed as an **output-format rule, never a cognition rule** — "responde en español", not "piensa en español" — and must carry an explicit machine-token carve-out naming every sentinel family as literal ASCII exempt from the language instruction.

### 6.3 The token-cost model

Spanish fertility (tokens per word) is tokenizer-specific by a factor of about four [nayeem2025strr]:

| Tokenizer | EN | ES | Penalty |
|---|---|---|---|
| GPT‑4o | 1.22 | 1.36 | **+11.5%** |
| Aya‑Expanse‑32B | 1.24 | 1.33 | +7.3% |
| Mistral‑Small‑24B | 1.27 | 1.42 | +11.8% |
| DeepSeek‑V3 | 1.23 | 1.55 | +26.0% |
| Qwen2.5‑72B | 1.25 | 1.61 | +28.8% |
| Llama‑3.1‑70B | 1.23 | 1.61 | **+30.9%** |

Applying this to Tlamatini's actual prompt shape (a ~2,000-token English system prompt plus a short user turn), the three candidate designs cost:

| Design | Model calls | Instruction tokens | Answer tokens | Literal fidelity |
|---|---|---|---|---|
| Full-Spanish prompt | 1 | 2,000 → **2,230–2,620** | +11–31% | intact |
| **Asymmetric (chosen)** | **1** | **2,000 (unchanged)** | **+11–31%** | **intact** |
| ES→EN→ES pivot | **3** | 2,000 + 2×MT | +11–31% + MT output | **$p^k$** |

Asymmetric Localization pays the fertility tax **only on tokens that carry user information**, and pays it zero times on the instruction block — which is also the block that must stay byte-identical for the KV/prompt cache to hit. Under Ollama's `keep_alive` behaviour and Anthropic prompt caching, a translated system prompt would additionally *fork the cache per language*, doubling cold-start cost. This is a second, independent reason to keep $S_{\text{en}}$ locale-independent: the directive $D(\ell_a)$ must ride in a **per-request message**, not be baked into the cached prefix.

### 6.4 The liability we are buying, and its exact compensation

Honesty requires stating the cost. An English system prompt with a Spanish answer requirement is the **cross-lingual condition**, and it is measurably harder for output-language fidelity than the monolingual condition [marchisio2024langconfusion]:

| Model | Monolingual LPR | Cross-lingual LPR |
|---|---|---|
| Command R+ | 99.3% | 97.6% |
| GPT‑4o | 99.3% | **95.8%** |
| Llama‑3‑70B‑Instruct | 46.0% (avg) | **30.3%** (avg) |

So roughly 4% of GPT‑4o answers, and a *majority* of Llama‑3‑70B answers, will contain at least one off-target line. Three interventions from the same study compensate, and all three are cheap:

1. **Few-shot exemplars — the highest-leverage intervention documented.** Command R Base moves from **1.1% → 95.0%** cross-lingual LPR with five exemplars. Two to five short Spanish exemplars of the desired answer shape simultaneously anchor language, format and register, and are nearly free under prompt caching.
2. **Low temperature.** Word-level pass rate falls 97.2% (T=0.0) → 96.3% (0.3) → 94.2% (0.7) → **86.5% (T=1.0)**. For an operator path there is no upside to T > 0.3 and a >10-point language-fidelity collapse as the downside.
3. **Re-assert every turn.** Multi-IF shows instruction adherence decaying 0.877 → 0.707 from turn 1 to turn 3 — a 17-point drop that is **four times larger than the Spanish penalty of 4.0 points at turn 3** [he2024multiif]. For a loop that can run thousands of iterations, turn depth is the dominant threat, not language. The directive must be re-injected adjacent to the current turn, not stated once ~100 lines upstream.

Which yields a design principle worth stating plainly:

> **In a Multi-Turn operator system, instruction decay across turns is a larger threat to Spanish output than Spanish itself.**

### 6.5 Do not force the model to think in Spanish

The intuitive strengthening — "reason in Spanish so the reasoning matches the answer" — is contraindicated. Prompt interventions that compel target-language reasoning traces "improve readability and oversight but **reduce answer accuracy**" [qi2025thinkinglanguage]. This is coherent with the mechanistic evidence that English-centric models compute in an English-like latent space regardless of I/O language [wendler2024dollamas], that this replicates causally on newer models via activation steering [schut2025thinkenglish], and that the layer structure is understand → English-thinking → language-specific generation [zhao2024mwork].

The practical corollary is counter-intuitive and important: **let the model think in whatever language it prefers, and constrain only the final surface.** The internal English pivot is not a bug to be corrected; it is load-bearing, and it is also the reason the Spanish gap is small in the first place.

### 6.6 Making the deterministic core language-neutral

Three surgical changes fix §3.1–§3.3, and each carries an **identity guarantee on ASCII input** so the tuned English behaviour is provably unchanged.

1. **NFKD-folding tokenizer.** Normalize, strip combining marks, then apply the existing `[a-z0-9_]+` rule: `código → codigo`, `análisis → analisis`. Output is byte-identical to today for pure-ASCII input. This alone converts the token-overlap term from structurally-zero to functional, and it eliminates the accent-dependent nondeterminism.
2. **Word-boundary phrase matching.** Replace `phrase in request_text` with boundary-aware containment, falling back to plain containment when the phrase's own edges are non-alphanumeric (so multi-word and punctuated hints are unaffected). This kills the `ue`-in-*prueba* class of adversarial hit outright. **It is independently valuable in English** — `api` inside *rapid*, `ls` inside *false* are English collisions too.
3. **Canonical-key expansion.** A data-only lexicon maps Spanish intent terms to hint tokens **that already exist in the registry** (enforced by a test), and appends them to the scored text. No new hints are ever invented, so the scorer's tuned behaviour is the only behaviour.

The English path must be pinned by a golden corpus of ~200 prompts asserting byte-identical scores before and after. That test is what makes this change safe to ship.

Two further corrections belong to the same pass, and both are **language-independent bug fixes**: the failure classifier's polarity must gain a localized positive branch *without* changing the "unknown ⇒ success" default (§3.6), and `Monitor-Netstat` must spawn its child with an invariant locale and decode UTF‑8 explicitly (§3.7).

> **Sequencing constraint (non-negotiable).** Seeding Spanish into pool-agent output while the eleven English failure prefixes still decide `call_success` makes a Spanish error score SUCCESS, which puts a failing agent into a saved `.flw`. The classifier fix and the language seeding must land in the **same commit**, or neither.

### 6.7 Retrieval is a separate, unnoticed casualty

One finding deserves its own line because it is silent and it invalidates measurements rather than merely degrading them. Tlamatini's default embedding model is `Nomic-Embed-Text` (v1.5), which is **English-only**. A Spanish query against an English-indexed corpus therefore embeds into a space where the query and its answers are not neighbours, and BM25 adds nothing because the lexical overlap is also absent.

The consequence is twofold. In production, Spanish RAG retrieval is degraded in a way no error message reveals. In *evaluation*, any cross-lingual cosine computed with that model is meaningless noise that **looks plausible**. The remedy is a multilingual encoder (`bge-m3`, XLM‑RoBERTa backbone, 100+ languages, 8,192-token context, already in the Ollama library) — used at minimum for the evaluation harness, and considered for the retrieval path with a documented VRAM cost, since the project already ships an embedding-memory pre-flight guard for exactly this reason.

---

## 7. A Capability Probe With Construct Validity

§1.2 rejected the prior probe. This section specifies its replacement. The governing standard is the one that applies to any measurement instrument: **an item that no model fails measures nothing, and an item whose noise exceeds its own tolerance measures nothing.**

### 7.1 Probe the production cell, not the easy one

The single most important correction: probe the **cross-lingual** condition (English system prompt, Spanish answer required), because that is what production runs and, per §6.4, it is the *harder* cell. A probe framed as Spanish-instruction → Spanish-answer certifies a condition that never occurs and licenses one that was never tested.

### 7.2 Dimensions, with discrimination required

Each dimension is admitted to the weighted score **only if at least one model in a pre-registered reference panel fails it**. This single rule eliminates the saturated-item defect.

| Dimension | What it measures | Design requirement |
|---|---|---|
| **D1 Answer-language fidelity** | LPR/WPR on *masked prose* | ≥8 long items; masking is mandatory (§7.3) |
| **D2 Drift** | Language change *within* one answer | Symmetric score: penalize drifting *into* the target language too, not only out of it |
| **D3 Tool-call fidelity** | Correct tool + byte-exact arguments from a Spanish instruction | Bind a realistic surface (≥20 tools), not 3 |
| **D4 Multi-step operator** | A ≥3-call chained Spanish task | Mandatory: MAPS puts the Spanish long-horizon agentic drop at **−11.7 points** [hofman2025maps]; a single-call battery structurally cannot see it |
| **D5 Sentinel preservation** | Byte-exact emission of machine tokens | **Elicitation, not observation** (§7.4) |

Dimension weighting must be inverse-variance ($1/\mathrm{SE}^2$), not hand-assigned; a 2-item dimension whose standard error is 0.2–0.3 cannot carry a 0.10 tolerance.

Probing must use **production generation parameters**, not `temperature=0, seed=1729`. Probing at T=0 systematically measures the best case — the same study that motivates the low-temperature recommendation shows a 10.7-point WPR collapse from T=0 to T=1. And at T=0 with a fixed seed, $k=3$ repeats are three copies of one sample: three times the cost for zero variance information.

### 7.3 Language identification must run only on masked prose

A Tlamatini answer legitimately contains HTML tables (mandated by Rule 6), `BEGIN-CODE` blocks, Windows paths, agent display names and an `END-RESPONSE` sentinel. Language identification over that raw text produces false confusion flags on *correct* Spanish answers. Every LID call — in the probe, in the router, and in the guard — must therefore run over a **masked** projection with code, paths, sentinels, identifiers and quoted spans removed.

Four detector defects from the reviewed design must be corrected, and they generalize to any implementation:

- **No diacritic back door.** A rule of the form `if any(ch in 'ñáéíóúü¿¡'): score_es += 3` lets **one accent decide the verdict** — and the project's own protected brand string *Angela López Mendoza* contains **ó**, as does the path `C:\Users\angel\Música\`. A diacritic signal may only be a capped density ratio over masked prose.
- **No degenerate confidence.** `(best − second) / total` returns 1.0 whenever the loser scores zero, independent of evidence volume: *"status del server"* yields **maximum confidence Spanish on one matched token**. Confidence must be evidence-weighted, e.g. $\frac{b-s}{t}\left(1-e^{-t/\tau}\right)$, with a hard floor of ≥4 matched function words before any verdict other than `und`.
- **Out-of-set rejection.** A closed {en, es} set resolves Portuguese, Galician and Catalan confidently to `es`. Include them as **decoy classes** plus an absolute likelihood floor, so out-of-set input yields `und`.
- **Technical Spanish must pass.** A word-level pass rate demanding ≥0.98 "words not in the other language's lexicon" is *unpassable* on legitimate Spanish technical prose — *"el flag `--noreload`"*, *"el Exec Report muestra"*, *commit*, *endpoint*, *log*. Exclude termbase literals and a domain-loanword allowlist before computing it, or the metric behaves oppositely in probe and production.

### 7.4 Sentinel checks must elicit, not observe

Checking whether sentinels *happened* to survive across a prose battery is a test whose base rate is near zero — it almost cannot fire. Each sentinel family needs **one item that forces its emission**, scored pass/fail per family. The minimum set must include the *silent-failure* families, not just the visible ones:

- `VERDICT: APPROVE|REQUEST_CHANGES|COMMENT` — the Reviewer defaults to `COMMENT` on an unparsed verdict, so a Spanish *"VEREDICTO: SOLICITAR CAMBIOS"* silently becomes a **pass**, and a downstream Forker routes a failed review down the success path.
- `TLM_VERDICT::` and the Video-Analyzer token set — the hardware-loop verdict.
- The Monitor outcome words.
- A Rule‑6 HTML table.

### 7.5 The route is a vector, not a scalar

Because D3/D4 measure a different construct than D1/D2, the probe must emit **per-path routes** — `{qa_route, operator_route}` — not a single tier. A model that writes beautiful Spanish but mangles a `chat_agent_stm32er` argument list should serve Spanish prose and English-scaffolded operator turns. Never redistribute D3/D4's weight onto the prose dimensions when a model lacks tool binding; mark the operator path `unmeasured` and route it conservatively.

### 7.6 Thresholds must be calibrated on owned data

Every cut-off must be derived, not asserted, and stored with its calibration date and panel. Tlamatini already owns the right corpus: the **113 Catalog-of-Prompts bodies** are in-domain, contain code, paths and HTML, and already require Spanish renderings for the evaluation. Draw the ROC on them plus FLORES‑200 dev for the out-of-set decoys, choose the LID operating point by **cost asymmetry** (a false "wrong language" triggers action on a correct answer; a false "right language" is a no-op) at FPR ≤ 0.5%, and *report* the resulting TPR rather than choosing it. Route cuts come from the largest observed gap across a ≥5-model reference panel spanning known-good to known-bad; **if no gap exists, the suite does not discriminate and must be redesigned.**

This is the same assay-sensitivity discipline §8 demands of the evaluation harness, applied to the probe. A probe exempt from it is an opinion.

### 7.7 Staleness, and the fingerprint that does not exist

A content-digest cache key works for local Ollama tags and **fails for exactly the production defaults**: `glm-5.2:cloud` is a moving alias whose digest is a stub, and Anthropic returns no `system_fingerprint` (an OpenAI field). For those, the stated threat — a model silently updated under the same name — is unmitigated by digest. The correct treatment is to classify any model whose digest is not a content hash as **undigestable**, give it a short TTL (24–72 h), and run a once-daily single-call **canary** whose response hash acts as a poor-man's fingerprint.

TTL direction must also be inverted from the intuitive choice: **short on the permissive verdict, long on the restrictive one.** A stale "native" verdict means a regressed model silently mangles sentinels on every request; a stale "English" verdict merely costs unnecessary English.

### 7.8 Language must be conversation-sticky

A per-message detector with no memory oscillates, and the oscillation is user-triggerable: turn 3 *"ok"* (too short → `und`), turn 4 *"y ahora el log"* (es), turn 5 a pasted command (no function words → `und`). If `und` falls back to the UI language, the conversation alternates ES/EN/ES/EN, producing a mixed-language history that then degrades the history-aware chain and the question rewriter.

Therefore: **resolve language once per conversation, with hysteresis.** Switch only on ≥2 consecutive turns of sufficient length detecting the other language above threshold, or on an explicit user action. An `und` verdict inherits the conversation language and must never fall back to the UI language.

This also disposes of a serious performance trap. If the answer-language directive lives in the *cached chain's* prompt, a language flip forces a full chain rebuild — embeddings, FAISS and BM25 over the loaded context — **on the request path**, in a system whose north star is latency. The fix is architectural, not defensive: make the chain-level prompt block **locale-independent** (a mirroring rule) and carry the actual language only in a per-request message. The rebuild then never happens, and the English prefix stays byte-stable for the prompt cache — the same property §6.3 requires for cost.

---

## 8. The Output Guard Must Be Read-Only in v1

The natural completion of §6.4 is a guard that detects an off-target answer and repairs it. We argue against shipping the repair, and the argument is worth stating because it generalizes.

**The guard's trigger is the detector.** Per §7.3 the detector is, before calibration, unreliable in exactly the ways that produce false positives on Tlamatini's own content. A repair pass fires on a false positive by *rewriting a correct answer*.

**The rewrite is durable.** Tlamatini's response pipeline has a strict ordering contract: strip artifacts → append exec-report → append denial banner → `save_message` → broadcast. A guard that mutates the answer writes through `save_message` and is therefore **replayed on every chat reload, forever**. A false repair is not a transient glitch; it is a permanently corrupted record.

**The invariant a naive guard checks is vacuous.** If the guard runs after the pipeline's strip step, its acceptance test ("identical `END-RESPONSE` / `BEGIN-CODE` counts before and after") compares **zero to zero**, because `END-RESPONSE` was already substituted away upstream and is additionally consumed by the LLM `stop=` list. The guard structurally cannot see the failure it exists to prevent. Sentinel-integrity checking must therefore be split: a **read-only detector on the raw model output**, before any stripping, and only then any repair on the stripped body.

**Repair can loop.** If the repair call is routed through the existing self-healing invoker (defaults: 4,096 tactics × 80 s), a cosmetic polish pass on an answer the user has already earned can retry thousands of times inside the response pipeline. Any repair must use a raw single invocation under a hard timeout, with the future abandoned on expiry and the cancellation epoch re-checked *after* the call returns.

**Therefore:** ship v1 with `detect + log + measure`. Emit a grep-able `--- [I18N-GUARD]` line, record LPR/WPR, never mutate. Gate the repair capability on a *measured* production false-positive rate below the calibrated threshold. This is the same philosophy as the codebase's existing binary-content guard, whose contract is explicitly fail-open because "a guard that wrongly drops a file silently deletes the user's real context."

The same reasoning condemns a pivot tier implemented as a re-use of the repair path: its acceptance validation would reject on exactly the long operator answers with tables and paths, and rejection returns English silently — delivering English to the users who explicitly asked for Spanish, without telling them.

---

## 9. Proving Parity: A Falsifiable Evaluation Protocol

A claim of "as effective or better" must be a **testable hypothesis**, not a demo. This section specifies the protocol.

### 9.1 Parity is non-inferiority, not equality

Let $\theta_{ES}$ and $\theta_{EN}$ be true task-success probabilities and $\Delta = \theta_{ES} - \theta_{EN}$. Test

$$H_0:\ \Delta \le -\delta \qquad\text{versus}\qquad H_1:\ \Delta > -\delta$$

at one-sided $\alpha = 0.05$. Parity is claimed **only if** the lower bound of the one-sided 95% CI for $\Delta$ exceeds $-\delta$.

The naive alternative — test $H_0: \Delta = 0$ and report $p > 0.05$ — is not merely weaker, it is **perversely incentivized**: a smaller, noisier study is *more* likely to produce a non-significant result and therefore *more* likely to be spun as "no difference." Under non-inferiority a small study produces a wide interval whose lower bound falls below $-\delta$, and correctly **fails** to establish parity. Bad measurement is punished rather than rewarded.

### 9.2 The margin must be justified three ways

$\delta$ is pre-registered and set to the minimum of three independent bounds:

1. **Operational relevance.** At $\theta_{EN} = 0.85$, a 5 pp drop raises the failure rate from 0.15 to 0.20 — one third more failures.
2. **Fraction-of-effect retention.** Measure $M_2 = \theta_{EN} - \theta_{\text{baseline}}$ against the same product with tools unbound (pure advice, no operator loop). If $\theta_{EN}=0.85$ and $\theta_{\text{base}}=0.20$, then $M_2 = 0.65$ and retaining $f = 0.90$ gives $\delta \le 0.065$.
3. **Measurement floor.** $\delta$ must exceed the harness's own run-to-run reproducibility $\sigma_{\text{run}}$. You cannot certify a margin finer than your own noise.

Primary: $\delta = 0.05$ absolute on pooled task success. Report sensitivity at $\delta \in \{0.03, 0.05, 0.10\}$. Use a *relative* margin (failure-rate ratio ≤ 1.33) for per-stratum secondaries, because an absolute 5 pp bar is nonsense at a stratum with base rate 0.99.

### 9.3 Assay sensitivity — the requirement that makes it falsifiable

A non-inferiority design in which the harness *cannot detect a real deficit* is unfalsifiable. The protocol must therefore include **deliberately degraded positive controls** and demonstrate that the pipeline rejects non-inferiority for each:

- a Spanish arm with the tool-usage rules removed from the system prompt;
- an arm where 10% of Spanish prompts have their literal path/filename arguments corrupted;
- an arm running a deliberately weaker model.

**Pre-specify that the parity conclusion is void unless all positive controls fail non-inferiority at the same $\delta$.** This is the ICH E10 assay-sensitivity requirement, and its omission is the single most common defect in bilingual model evaluations.

### 9.4 Paired analysis and sample size

The same task is executed in both languages, so outcomes are paired. Note a category error to avoid: **McNemar's test (exact or mid-p) tests equality and cannot test a margin.** Use it as a companion, not as the parity test. For the margin, use **Tango's score-based confidence interval** for the paired difference of proportions, via Yang et al.'s non-iterative closed form so the harness needs no root-finder.

Sample size is driven by the **discordance rate** $p_d$, not the base rate:

$$n_{\text{pairs}} = \frac{(z_{1-\alpha}+z_{1-\beta})^2\,p_d}{\delta^2} = 2473\,p_d \quad (\Delta=0,\ \delta=0.05)$$

| $\rho$ | $p_d$ | $n_{\text{pairs}}$ | expected discordant $m$ |
|---|---|---|---|
| 0.00 | 0.255 | 631 | 161 |
| 0.60 | 0.102 | 253 | 26 |
| 0.70 | 0.077 | 190 | 15 |
| 0.80 | 0.051 | 127 | 6 |

The $\rho=0$ row reproduces the unpaired answer of 631 per arm (1,262 runs), which is the correct sanity check; pairing buys a 5–20× reduction. **Recommendation: a 50-item pilot to estimate $p_d$ and $\sigma_{\text{run}}$, then $n = 250$ paired items per model**, with a floor of ~25 expected discordant pairs (below that, asymptotics are worthless and the claim rests on exact methods with wide intervals).

Multiplicity is handled in three tiers: **one unadjusted pre-registered primary**; a fixed-sequence gatekeeping ladder at full $\alpha$ for the key secondaries (Argument Exactness → Tool-Selection Accuracy → Answer-Language Correctness → Ask-Execs Gating Parity); and Benjamini–Hochberg FDR at $q = 0.10$ for the exploratory model × stratum × metric grid. Bonferroni over a 126-cell grid would cost a **2.84× increase in required runs** to control a criterion far stricter than an exploratory analysis needs. State explicitly that in a non-inferiority framing, the "discovery" whose false rate FDR bounds is **the parity claim itself**.

### 9.5 Metrics for an operator system

The primary endpoint is **programmatic**, not textual and not a judge: an executable success predicate per item, evaluated against the state of the machine in a fresh sandbox (file exists at the exact path with the exact SHA‑256; exit code 0; a regex matches the pool agent's log; the generated `.flw` compiles in dry-run). **The disk does not speak Spanish or English**, which is exactly why this endpoint is immune to language-similarity confounds. Incomplete, crashed or timed-out runs count as **failures** — dropping them biases toward parity, the anti-conservative direction.

| Metric | Definition | Judge needed |
|---|---|---|
| **Task Success Rate** (primary) | Executable predicate holds | No |
| Tool-Selection Accuracy | Exact multiset / sequence match vs gold, management tools excluded | No |
| **Argument Exactness** | Byte-identical after **NFC only** — never casefold, never strip accents | No |
| **Literal Drift Rate** | Any path/number/flag differs between the ES and EN runs of the same item | No — and **gold-free** |
| Plan-Length Parity | \|L_ES − L_EN\| ≤ 1 | No |
| Nonexistent-Tool Invocation | Emitted a tool not in the bound surface | No |
| Ask-Execs Gating Parity | Identical set of gated tools triggered in both arms | No |
| Answer-Language Correctness | LPR/WPR on **masked** text | No |
| Refusal justification / prose adequacy | — | Yes (minority of surface) |

Two of these deserve emphasis. **Literal Drift Rate** is the sharpest cross-language signal available and needs no gold labels at all: both runs were given the *same frozen literals*, so any divergence is unambiguously language-induced. And **Ask-Execs Gating Parity** is a *safety* endpoint, not a quality one — a Spanish prompt that routes to an ungated near-synonym tool is a security regression and deserves its own hypothesis in the gatekeeping ladder. This matters concretely because Spanish agent-security attack success is measured at **60.2% versus 53.4% in English** [hofman2025maps]: English-tuned injection defenses under-protect Spanish users.

**BLEU is inadmissible here**, for a construct-validity reason stronger than its usual critique: the Spanish and English answers are *supposed* to differ in surface form, so n-gram overlap across the pair is near-zero by design and carries no parity information. chrF++ and BERTScore are monolingual by construction; COMET's estimand (translation quality against a source) does not exist here. Only a **cross-lingual sentence-embedding cosine** measures the right construct — and it must be calibrated against a mismatched-pair null (report matched-vs-mismatched AUC; flag at the 5th percentile of the matched distribution, never at an absolute cosine).

### 9.6 Dependencies: add none

The release archive has already breached the 2 GiB GitHub ceiling once and `torch-cpu` is a documented blocker in this build. Therefore: compute cross-lingual similarity by POSTing to the **already-present Ollama `/api/embed`** with stdlib `urllib`, switching the *evaluation-only* embedding to `bge-m3`; implement chrF++ inline in ~50 lines of stdlib for *within-language* comparisons only; and explicitly reject `sentence-transformers`, `torch` and `unbabel-comet`. Likewise the language identifier: a stopword + character-trigram classifier in pure Python is sufficient for a closed {en, es} set and avoids a fastText C++ extension in a PyInstaller build.

### 9.7 The judge must be measured before it is trusted

LLM judges carry four documented biases — position, verbosity, self-preference, and **language bias**, the decisive one here: judges are biased toward higher scores and human agreement is lower for non-English [hada2024]. A judge that inflates Spanish would *manufacture* parity; one that deflates it would destroy a true claim. Either way the endpoint is invalid until the differential is quantified.

Protocol: pointwise rubric-anchored discrete scores (0/1/2/3 with written anchors), never pairwise A/B and never a 1–10 scale; blinded language labels; an odd panel of 3–5 judges from **different model families**, no judge scoring its own family's output; and a **language-bias gate** — ~30 calibration items per language scored by a native Mexican-Spanish reviewer who is also a Tlamatini operator, reporting $b_{ES} - b_{EN}$ with a bootstrap CI. If that CI excludes zero, correct or discard the judge. Report Cohen's κ *and* Gwet's AC1 per language, because at an 85% base rate the skewed marginals collapse κ toward zero even at high raw agreement.

### 9.8 Determinism must be measured, not configured

Temperature 0 does **not** make an LLM deterministic on shared infrastructure: the forward pass is not batch-invariant, so a request's output depends on the batch it lands in — i.e. on other users' concurrent traffic [he2025_nondeterminism]. For cloud endpoints determinism is unobtainable. Therefore: set T=0/top_k=1/seed where the backend accepts them and **document which arms could not be seeded**; run $k=5$ repeats; report a variance-components model ($\sigma_{\text{item}}$, $\sigma_{\text{run}}$, ICC); and separately prove the *scoring harness* is byte-deterministic with a record-replay golden fixture, which cleanly partitions harness bugs from model stochasticity.

Five Tlamatini-specific state hazards must be pinned before every batch: the `Agent` table is deleted and rebuilt on every server start, so **snapshot and assert identical enabled Tool/Agent/Skill sets across arms**; freeze the clock; reset the sandbox and agent pool between items; re-assert the toolbar toggles at every send; and read all subprocess output with `encoding='utf-8', errors='replace'` — a cp1252 read corrupts Spanish *before* scoring and manufactures parity failures that are pure harness artefacts. Finally, log `recovery_events` and treat "succeeded only after N self-healing tactics" as a distinct sensitivity stratum: **if the Spanish arm needs more retries to reach the same outcome, that is an inferiority even at equal terminal success.**

### 9.9 Corpus construction

250 paired items across 7 risk-weighted strata (pure QA 40 as a *negative control*; single-tool 50; multi-tool ≥3 calls 45; path/identifier-heavy 40; hardware in dry-run 25; messaging with sandbox recipients only 20; flow authoring 30).

The source of truth is a **language-neutral task spec** — intent, required tools, required argument literals, an executable predicate — of which the English and Spanish prompts are two *renderings*. Literals are byte-identical in both by construction and enforced by an automated diff; this is precisely what makes Argument Exactness and Literal Drift Rate valid. Translation follows an ISO‑17100-style workflow (translate → independent revision → in-country review by a native Mexican-Spanish Tlamatini operator). **Machine translation and back-translation QA are rejected**: MT errors would be confounded with product errors and MT systematically simplifies syntax, making the Spanish arm *artificially easy*; back-translation agreement measures MT self-consistency, not adequacy.

Two further requirements are easy to miss and both bias the result toward a false parity claim if omitted. **Counterbalanced authorship**: roughly half the items must be authored Spanish-first, or the Spanish set inherits English discourse structure and the study overestimates parity. And **deliberate locale traps** (~15% of items): decimal comma, es‑MX date order, accented and ñ filenames, 24-hour times, the *billón* false friend, mixed UTF‑8/cp1252, plus register variation (tú/usted, *computadora* vs *ordenador*) and realistic code-switching (*"hazle un git push al repo"*).

One operational warning: the messaging agents are deliberately **not** gated by Ask-Execs, so a messaging stratum run without sandbox recipients will contact real people — and Zavuerer bills per send.

---

## 10. Threats to Validity

### 10.1 Construct

The primary endpoint measures *machine outcomes*, which is right for an operator but blind to answer quality a user would care about (tone, clarity, register). The judge covers that residue but only after passing the language-bias gate, so if the gate fails, part of the construct is unmeasured and the paper must say so rather than substitute a text-similarity proxy.

### 10.2 External

Tlamatini's user is in Mexico; most published Spanish benchmarks measure Peninsular Spanish. "Spanish" is not one language — this is precisely why La Leaderboard exists — and results measured on European Spanish do not automatically transfer. The corpus's in-country review is the mitigation, not a solution.

The evidence base for the *asymmetric* choice specifically (English instructions + target-language content and answer) has direct experimental support for **Arabic** [kmainasi2024nativevsnonnative] and from an English reasoning scaffold [huang2023xlt], **not from a Spanish-specific controlled study**, and there is counter-evidence that original-language prompting wins for real Spanish user queries [liu2024translationall]. It is therefore presented here as a **design hypothesis to be measured on Tlamatini's own traffic**, with the ablation designed to vary one axis at a time (English-instruction vs Spanish-instruction, both with Spanish content and Spanish answer), not as an established finding.

### 10.3 Internal

Public multilingual suites carry contamination risk — MEGAVERSE explicitly warns that several evaluated models are likely contaminated with multilingual evaluation benchmarks [ahuja2024megaverse] — so any Spanish-vs-English delta from a public suite may be a delta in memorization. This is one reason the protocol's primary endpoint is a private, spec-derived corpus.

Translated benchmarks also confound translationese with capability: the 13-point Llama‑3.1‑70B HellaSwag EN→ES gap sits beside a 3-point MMLU gap in the *same* evaluation of the *same* model [thellmann2024european], a pattern far better explained by translation artifacts in a narrative task than by a 13-point Spanish commonsense deficit. Global-MMLU independently finds 28% of MMLU questions culturally sensitive and 84.9% of geography questions North-America/Europe-centric [singh2024globalmmlu].

Finally, one measurement in §3 is bounded: the 0/12 result characterizes the **scorer**, and Multi-Turn binds the full tool surface when it fits, so a Spanish prompt may still succeed on the model's own tool choice. The deterministic damage is confined to the planner's DAG, the system-prompt summary line, and the bind ranking when the surface overflows — which is exactly why the paper claims *"the correct tool is not reliably selected"* rather than *"Spanish does not work at all."*

### 10.4 Bibliographic integrity

Every reference below was re-fetched and confirmed by an independent verification agent: title, authors, year and identifier resolve to the cited work in all cases, and every HIGH-confidence numeric claim was checked against the source table digit-by-digit.

One reference was **removed for misattribution**: a paper on African-language tokenization was originally cited for Spanish fertility figures, but a full-text search confirms the words *Spanish*, *French* and *Portuguese* never appear in it. All Spanish fertility values in §6.3 come from [nayeem2025strr], which was verified independently. We record this because a paper that claims rigor must show how its own errors were caught, and because the incident illustrates the class of failure — a *real* paper cited for a number it does not contain — that citation checking by title alone would miss.

---

## 11. Conclusion

The question "should the Spanish Tlamatini translate?" turns out to be the wrong question, because it presumes the deficit is in the model. It is not. For Spanish the model-side gap is 1–4 points on reasoning, approximately zero on tool selection, and mechanistically attributable to a stage that is already saturated. The deficit is in the **substrate**: an ASCII-only tokenizer, 2,389 English lexemes in deterministic control paths, an English-only prompt gate, an argument parser that corrupts data on a Spanish conjunction, and a failure classifier that scores Spanish errors as successes.

That reframing changes what must be built. Not a translation bridge, but three things:

1. **Asymmetric Localization** — English program text, verbatim user content, natively generated Spanish answers, and a language-*neutral* deterministic core. It costs one model call, pays the token tax only on user-bearing tokens, and preserves literal fidelity exactly ($p^k = 1$).
2. **Two enforced invariants** — Identifier/Label Separation and the Label Round-Trip Prohibition — both machine-checked, because the second is already violated in three places and two of those violations would cause permanent, silent capability loss.
3. **Measurement discipline at both ends** — a capability probe with construct validity and calibrated thresholds, and a pre-registered non-inferiority protocol with assay sensitivity, so "as effective or better" becomes a claim that can be *falsified* rather than asserted.

The honest cost is stated rather than hidden: an English system prompt places every request in the cross-lingual condition, which is measurably harder for output-language fidelity, and the compensation is few-shot Spanish exemplars, low temperature, per-turn re-assertion of the directive, and a **read-only** guard that measures before it is ever allowed to repair.

If those hold, there is a real possibility the Spanish build is not merely at parity but **better than today's English build** — because three of the required fixes (word-boundary phrase matching, the failure-classifier polarity, and the locale-invariant subprocess environment) repair defects that damage the English path too. Localization, done as described here, is not a translation project. It is a correctness project that happens to be discovered by asking the system to speak Spanish.

---

## References

Every entry below was independently re-verified (title, authors, year, identifier) during the adversarial pass described in §1.4 and §10.4.

**Multilingual capability and evaluation**

- [ahuja2023mega] Ahuja K. et al. *MEGA: Multilingual Evaluation of Generative AI.* EMNLP 2023, pp. 4232–4267. arXiv:2303.12528.
- [ahuja2024megaverse] Ahuja S. et al. *MEGAVERSE: Benchmarking LLMs Across Languages, Modalities, Models and Tasks.* NAACL 2024, pp. 2598–2637. arXiv:2311.07463.
- [xuan2025mmluprox] Xuan W. et al. *MMLU-ProX: A Multilingual Benchmark for Advanced LLM Evaluation.* arXiv:2503.10497.
- [thellmann2024european] Thellmann K. et al. *Towards Multilingual LLM Evaluation for European Languages.* arXiv:2410.08928 (v2 title; v1 read "Cross-Lingual").
- [singh2024globalmmlu] Singh S., Romanou A., Fourrier C. et al. *Global MMLU: Understanding and Addressing Cultural and Linguistic Biases in Multilingual Evaluation.* arXiv:2412.03304.
- [he2024multiif] He Y., Jin D., Wang C. et al. *Multi-IF: Benchmarking LLMs on Multi-Turn and Multilingual Instructions Following.* arXiv:2410.15553.
- [bandarkar2024belebele] Bandarkar L. et al. *The Belebele Benchmark: a Parallel Reading Comprehension Dataset in 122 Language Variants.* ACL 2024, pp. 749–775. arXiv:2308.16884.
- [artetxe2020xquad] Artetxe M., Ruder S., Yogatama D. *On the Cross-lingual Transferability of Monolingual Representations.* ACL 2020. arXiv:1910.11856.
- [lewis2020mlqa] Lewis P. et al. *MLQA: Evaluating Cross-lingual Extractive Question Answering.* ACL 2020. arXiv:1910.07475.
- [clark2020tydiqa] Clark J.H. et al. *TyDi QA.* TACL 2020. arXiv:2003.05002. — **contains no Spanish**; must not be cited as Spanish evidence.
- [baucells2025iberobench] Baucells I. et al. *IberoBench: A Benchmark for LLM Evaluation in Iberian Languages.* COLING 2025, pp. 10491–10519.
- [grandury2025laleaderboard] Grandury M. et al. *La Leaderboard: … Spanish Varieties and Languages of Spain and Latin America.* ACL 2025, pp. 32482–32524.

**Translation pivots, latent language, and language fidelity**

- [ahuja2023mega] (translate-test scoping — see above).
- [liu2024translationall] Liu C., Zhang W., Zhao Y., Luu A.T., Bing L. *Is Translation All You Need?* NAACL 2025. arXiv:2403.10258.
- [artetxe2023revisiting] Artetxe M., Goswami V., Bhosale S., Fan A., Zettlemoyer L. *Revisiting Machine Translation for Cross-lingual Classification.* EMNLP 2023, pp. 6355–6368. arXiv:2305.14240.
- [etxaniz2024selftranslate] Etxaniz J., Azkune G., Soroa A., Lopez de Lacalle O., Artetxe M. *Do Multilingual Language Models Think Better in English?* NAACL 2024 (Short), pp. 550–564. arXiv:2308.01223.
- [wendler2024dollamas] Wendler C., Veselovsky V., Monea G., West R. *Do Llamas Work in English? On the Latent Language of Multilingual Transformers.* ACL 2024, pp. 15366–15394. arXiv:2402.10588.
- [schut2025thinkenglish] Schut L., Gal Y., Farquhar S. *Do Multilingual LLMs Think In English?* arXiv:2502.15603.
- [zhao2024mwork] Zhao Y., Zhang W., Chen G., Kawaguchi K., Bing L. *How do Large Language Models Handle Multilingualism?* NeurIPS 2024. arXiv:2402.18815.
- [qi2025thinkinglanguage] Qi J., Chen S., Xiong Z., Fernández R., Bitterman D.S., Bisazza A. *When Models Reason in Your Language: Controlling Thinking Language Comes at the Cost of Accuracy.* Findings of EMNLP 2025. arXiv:2505.22888.
- [marchisio2024langconfusion] Marchisio K., Ko W.-Y., Bérard A., Dehaze T., Ruder S. *Understanding and Mitigating Language Confusion in LLMs.* EMNLP 2024, pp. 6653–6677. arXiv:2406.20052. Code: `github.com/for-ai/language-confusion`.
- [huang2023xlt] Huang H., Tang T., Zhang D., Zhao W.X., Song T., Xia Y., Wei F. *Cross-Lingual-Thought Prompting.* Findings of EMNLP 2023, pp. 12365–12394. arXiv:2305.07004.
- [qin2023clp] Qin L., Chen Q., Wei F., Huang S., Che W. *Cross-lingual Prompting.* EMNLP 2023, pp. 2695–2709. arXiv:2310.14799.
- [kmainasi2024nativevsnonnative] Kmainasi M.B. et al. *Native vs Non-Native Language Prompting: A Comparative Analysis.* arXiv:2409.07054. — Arabic only.

**Tokenization cost**

- [nayeem2025strr] Nayeem M.T., Alqahtani S., Laskar M.T.R., Mohiuddin T., Bari M.S. *Beyond Fertility: Analyzing STRR as a Metric for Multilingual Tokenization Evaluation.* NeurIPS 2025 Workshop. arXiv:2510.09947. — source of all EN/ES fertility values in §6.3.
- [petrov2023tokenizerunfairness] Petrov A., La Malfa E., Torr P., Bibi A. *Language Model Tokenizers Introduce Unfairness Between Languages.* NeurIPS 2023. arXiv:2305.15425.

**Tool calling and agentic behaviour in non-English**

- [almeida2025ticketbench] Sales Almeida T., Alves Santos J.G., Laitz T., Kerche Bonás G. *Ticket-Bench: A Kickoff for Multilingual and Regionalized Agent Evaluation.* arXiv:2509.14477.
- [hofman2025maps] Hofman O. et al. *MAPS: A Multilingual Benchmark for Agent Performance and Security.* Findings of EACL 2026. arXiv:2505.15935.
- [luo2026lostinexecution] Luo Z., Kutralingam T.P., Okoani O.N., Xu W., Wei H., Hu X. *Lost in Execution: On the Multilingual Robustness of Tool Calling in LLMs* (MLCL). ACL 2026. arXiv:2601.05366.
- [zhang2026itc] Zhang Z., Zhu Y. *Enhancing Tool Calling in LLMs with the International Tool Calling Dataset.* arXiv:2603.05515.
- [kang2026whygaps] Kang D., Hwang S., Kim D., Kim H., Lee G.G. *Why Do Multilingual Reasoning Gaps Emerge in Reasoning Language Models?* Findings of ACL 2026. arXiv:2510.27269.

**Evaluation methodology and statistics**

- [piaggio2012] Piaggio G., Elbourne D.R., Pocock S.J., Evans S.J.W., Altman D.G. *Reporting of Noninferiority and Equivalence Randomized Trials: CONSORT 2010 Extension.* JAMA 2012;308(24):2594–2604.
- [tango1998] Tango T. *Equivalence test and confidence interval for the difference in proportions for the paired-sample design.* Statistics in Medicine 1998;17(8):891–908.
- [yang2013] Yang Z., Sun X., Hardin J.W. *A non-iterative implementation of Tango's score confidence interval.* Statistics in Medicine 2013;32(8):1336–1342.
- [fagerland2013] Fagerland M.W., Lydersen S., Laake P. *The McNemar test for binary matched-pairs data: mid-p and asymptotic are better than exact conditional.* BMC Med Res Methodol 2013;13:91.
- [fagerland2014] Fagerland M.W., Lydersen S., Laake P. *Recommended tests and confidence intervals for paired binomial proportions.* Statistics in Medicine 2014;33(16):2850–2875.
- [liu2002] Liu J.-P., Hsueh H.-M., Hsieh E., Chen J.J. *Tests for equivalence or non-inferiority for paired binary data.* Statistics in Medicine 2002;21(2):231–245.
- [benjamini1995] Benjamini Y., Hochberg Y. *Controlling the False Discovery Rate.* JRSS‑B 1995;57(1):289–300.
- [efron1987] Efron B. *Better Bootstrap Confidence Intervals.* JASA 1987;82(397):171–185.
- [mcnemar1947] McNemar Q. *Note on the sampling error of the difference between correlated proportions.* Psychometrika 1947;12(2):153–157.
- [ich_e9_e10] ICH E9 (Statistical Principles for Clinical Trials) and ICH E10 (Choice of Control Group; assay sensitivity).
- [iso17100] ISO 17100:2015 — *Translation services: Requirements for translation services.*

**Metrics and judges**

- [callisonburch2006] Callison-Burch C., Osborne M., Koehn P. *Re-evaluating the Role of BLEU in Machine Translation Research.* EACL 2006, pp. 249–256.
- [popovic2017] Popović M. *chrF++: words helping character n-grams.* WMT 2017, pp. 612–618.
- [rei2020] Rei R., Stewart C., Farinha A.C., Lavie A. *COMET: A Neural Framework for MT Evaluation.* EMNLP 2020, pp. 2685–2702.
- [zhang2020] Zhang T., Kishore V., Wu F., Weinberger K.Q., Artzi Y. *BERTScore.* ICLR 2020.
- [feng2022] Feng F., Yang Y., Cer D., Arivazhagan N., Wang W. *Language-agnostic BERT Sentence Embedding (LaBSE).* ACL 2022, pp. 878–891.
- [zheng2023] Zheng L. et al. *Judging LLM-as-a-Judge with MT-Bench and Chatbot Arena.* NeurIPS 2023 D&B. arXiv:2306.05685.
- [wang2023] Wang P. et al. *Large Language Models are not Fair Evaluators.* ACL 2024. arXiv:2305.17926.
- [panickssery2024] Panickssery A., Bowman S.R., Feng S. *LLM Evaluators Recognize and Favor Their Own Generations.* NeurIPS 2024.
- [hada2024] Hada R. et al. *Are LLM-based Evaluators the Solution to Scaling Up Multilingual Evaluation?* Findings of EACL 2024, pp. 1051–1070. arXiv:2309.07462.
- [cohen1960] Cohen J. *A Coefficient of Agreement for Nominal Scales.* Educ Psychol Meas 1960;20(1):37–46.
- [gwet2008] Gwet K.L. *Computing inter-rater reliability and its variance in the presence of high agreement.* Br J Math Stat Psychol 2008;61(1):29–48.
- [feinstein1990] Feinstein A.R., Cicchetti D.V. *High agreement but low kappa.* J Clin Epidemiol 1990;43(6):543–549.
- [krippendorff2004] Krippendorff K. *Content Analysis: An Introduction to Its Methodology*, 2nd ed. Sage.
- [he2025_nondeterminism] He H. et al. *Defeating Nondeterminism in LLM Inference.* Thinking Machines Lab, 10 Sept 2025.

**Encoders referenced for the evaluation harness**

- [bgem3] BAAI. *BGE‑M3* (XLM‑RoBERTa backbone, 100+ languages, 8,192-token context). Model card: `huggingface.co/BAAI/bge-m3`; distribution: `ollama.com/library/bge-m3`.
- [nomic_v15] Nomic AI. *nomic-embed-text-v1.5* — **English-only**; the basis for rejecting it as a cross-lingual encoder.
- [nomic_v2] Nomic AI. *nomic-embed-text-v2-moe* — multilingual alternative, ~100 languages.

---

*Companion document: `DESIGN.md` — the implementable architecture, diagrams, module map, integration points, phased rollout and test plan. Reference Python under `reference_impl/`.*


