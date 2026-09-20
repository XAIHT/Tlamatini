# Model configuration

Config → Models manages **38 model, engine and voice settings** for core services
and **21 model-backed agents**. This reference describes the implemented registry
as reviewed on **2026-09-20**. Defaults below are application defaults, not a promise
that a provider will continue to serve a particular model.

## Use the dialog

1. Open **Config → Models**. Choose a category or search by agent/model name.
2. Set Ollama names from the configured server's catalog. Use local Whisper names,
   Hugging Face IDs or model directories for local speech fields; enter provider
   IDs for cloud speech and Claude. Engines and voices have dedicated selectors.
3. Click **Save**. All 38 settings are submitted together, including hidden tabs;
   unrelated settings and credentials in the active `config.json` are preserved.
4. Reconnect chat when prompted so its model clients are rebuilt. Agents pick up
   settings on their next configuration load. Restart a running monitor or speech
   agent when a new choice must take effect immediately.

The form uses two columns on wider screens and one on narrow screens, with a
scrollable body and search across the categories. Save does not download weights,
start an agent, enable transcript cleanup, test inference or grant provider access.
Credentials and server URLs retain their existing configuration surfaces.

| Category | Fields | Coverage |
|---|---:|---|
| Core | 7 | Embedding, reasoning, prompts, Multi-Turn, file search and web processing |
| Vision | 7 | Image and video observer pairs and mergers; Claude image analysis |
| Speech | 7 | Talker model/voice, Whisperer engine/models, video audio transcription |
| Workflows | 6 | Crawler, FlowCreator, FlowHypervisor, Prompter, PSer, Reviewer |
| Documents | 5 | File-Interpreter, Summarizer, PDFer, PPTXer, LaTeXer |
| Monitoring & messaging | 6 | Monitor-Log, Monitor Netstat, Notifier, RecMailer, Instant-Messaging-Doctor, TeleTlamatini |

## Complete setting reference

The tables are checked against
[`model_settings.py`](../Tlamatini/agent/agents/model_settings.py). Keys are stored
at the top level of `config.json`. **Keep the existing spelling `embeding-model`.**
The agent path is relative to its `config.yaml`; `—` denotes an in-process service.
An absent/null global key, or a blank required key, uses its fallback key when one
is declared, then the initial default. Explicit blank optional keys remain blank.
The fallback relationship is used only when the dedicated setting is missing:
saving a dedicated value means later Unified model changes do not override it.

### Core

| Global key / label | Agent YAML path | Initial default | Kind / fallback |
|---|---|---|---|
| `embeding-model` — Embedding / memory | — | `Nomic-Embed-Text:latest` | ollama |
| `chained-model` — Chained reasoning | — | `glm-5.3:cloud` | ollama |
| `access_aimed_prompt_model` — Access aimed prompts | — | `glm-5.3:cloud` | ollama |
| `unified_agent_model` — Unified / Multi-Turn | — | `glm-5.3:cloud` | ollama |
| `mcp_files_search_model` — MCP file search | — | `glm-5.3:cloud` | ollama |
| `internet_classifier_model` — Internet classifier | — | `glm-5.3:cloud` | ollama |
| `web_summarizer_model` — Web search summaries | — | `glm-5.3:cloud` | ollama |

### Vision

| Global key / label | Agent YAML path | Initial default | Kind / fallback |
|---|---|---|---|
| `image_interpreter_model` — Image interpreter 1 | `image_interpreter.interpreter_model_1` | `jcyhsiao/qwen3.5cloud:latest` | ollama |
| `image_interpreter_model_2` — Image interpreter 2 | `image_interpreter.interpreter_model_2` | `gemma4:cloud` | ollama |
| `image_merging_model` — Image merger | `image_interpreter.merging_model` | `glm-5.3:cloud` | ollama |
| `video_interpreter_model` — Video interpreter 1 | `video_analyzer.interpreter_model_1` | `gemma4:cloud` | ollama |
| `video_interpreter_model_2` — Video interpreter 2 | `video_analyzer.interpreter_model_2` | `jcyhsiao/qwen3.5cloud:latest` | ollama |
| `video_merging_model` — Video merger | `video_analyzer.merging_model` | `glm-5.3:cloud` | ollama |
| `claude_image_model` — Claude image analysis | — | `claude-opus-4-5-20251101` | provider |

### Speech

| Global key / label | Agent YAML path | Initial default | Kind / fallback |
|---|---|---|---|
| `talker_model` — Talker · speech generation | `talker.model` | `legraphista/Orpheus:3b-ft-q8` | ollama |
| `talker_voice` — Talker · voice | `talker.voice` | `tara` | choice |
| `whisperer_engine` — Whisperer · recognition engine | `whisperer.engine` | `faster-whisper` | choice |
| `whisperer_model` — Whisperer · local speech model | `whisperer.model` | `base` | local |
| `whisperer_cloud_model` — Whisperer · cloud speech model | `whisperer.cloud_model` | Empty (provider default) | provider; optional |
| `whisperer_cleanup_model` — Whisperer · transcript cleanup | `whisperer.cleanup_model` | `glm-5.3:cloud` | ollama; fallback `unified_agent_model` |
| `video_transcription_model` — Video-Analyzer · audio tracks | `video_analyzer.transcription.model` | `base` | local |

### Workflows

| Global key / label | Agent YAML path | Initial default | Kind / fallback |
|---|---|---|---|
| `crawler_model` — Crawler | `crawler.llm.model` | `glm-5.3:cloud` | ollama; fallback `unified_agent_model` |
| `flowcreator_model` — FlowCreator | `flowcreator.llm.model` | `glm-5.3:cloud` | ollama; fallback `unified_agent_model` |
| `flowhypervisor_model` — FlowHypervisor | `flowhypervisor.llm.model` | `glm-5.3:cloud` | ollama; fallback `unified_agent_model` |
| `prompter_model` — Prompter | `prompter.llm.model` | `glm-5.3:cloud` | ollama; fallback `unified_agent_model` |
| `pser_model` — PSer | `pser.llm.model` | `glm-5.3:cloud` | ollama; fallback `unified_agent_model` |
| `reviewer_model` — Reviewer | `reviewer.llm.model` | `glm-5.3:cloud` | ollama; fallback `unified_agent_model` |

### Documents

| Global key / label | Agent YAML path | Initial default | Kind / fallback |
|---|---|---|---|
| `file_interpreter_model` — File-Interpreter | `file_interpreter.llm.model` | `glm-5.3:cloud` | ollama; fallback `unified_agent_model` |
| `summarizer_model` — Summarizer | `summarizer.llm.model` | `glm-5.3:cloud` | ollama; fallback `unified_agent_model` |
| `pdfer_model` — PDFer · design and polish | `pdfer.ollama_model` | `glm-5.3:cloud` | ollama; fallback `unified_agent_model` |
| `pptxer_model` — PPTXer · design and polish | `pptxer.ollama_model` | `glm-5.3:cloud` | ollama; fallback `unified_agent_model` |
| `latexer_model` — LaTeXer · repair | `latexer.repair_model` | `glm-5.3:cloud` | ollama; optional; fallback `unified_agent_model` |

### Monitoring & messaging

| Global key / label | Agent YAML path | Initial default | Kind / fallback |
|---|---|---|---|
| `monitor_log_model` — Monitor-Log | `monitor_log.llm.model` | `glm-5.3:cloud` | ollama; fallback `unified_agent_model` |
| `monitor_netstat_model` — Monitor-Netstat | `monitor_netstat.llm.model` | `glm-5.3:cloud` | ollama; fallback `unified_agent_model` |
| `notifier_model` — Notifier | `notifier.llm.model` | `glm-5.3:cloud` | ollama; fallback `unified_agent_model` |
| `recmailer_model` — RecMailer | `recmailer.llm.model` | `glm-5.3:cloud` | ollama; fallback `unified_agent_model` |
| `instant_messaging_doctor_model` — Instant-Messaging-Doctor | `instant_messaging_doctor.ollama.model` | `glm-5.3:cloud` | ollama; fallback `unified_agent_model` |
| `teletlamatini_model` — TeleTlamatini · completeness check | `teletlamatini.completeness_check.model` | `glm-5.3:cloud` | ollama; fallback `unified_agent_model` |

## Speech and model compatibility

- **Talker:** `talker_model` must produce Orpheus-compatible audio tokens. A normal
  chat model cannot replace it. Supported `talker_voice` values are `tara`, `leah`,
  `jess`, `mia`, `zoe`. The SNAC 24 kHz decoder is a required internal format
  dependency, not a second freely interchangeable speech model.
  Config → Voice controls the chat avatar's browser `speechSynthesis` voice,
  rate and volume separately; it does not select Talker's server-side model.
- **Whisperer:** `whisperer_engine` is `faster-whisper`, `cloud-groq` or
  `cloud-openai`. The local model accepts a Whisper size, Hugging Face ID or local
  model directory. First local use may download weights. An empty cloud model
  selects the implementation's provider default: `whisper-large-v3` for Groq or
  `whisper-1` for OpenAI. Cloud credentials remain `cloud_api_key` in the agent or
  `GROQ_API_KEY` / `OPENAI_API_KEY` in its environment; `cloud_base_url` remains
  a separate endpoint override. These names describe code defaults, not a live
  availability check of either service.
- **Transcript cleanup:** choosing `whisperer_cleanup_model` selects the Ollama
  postprocessor; it does not enable cleanup or send microphone audio to Ollama.
  `ollama_cleanup: true` enables that stage. Recording device, language, silence gate, duration and prompts
  remain agent configuration.
- **Video audio:** `video_transcription_model` independently controls local
  faster-whisper processing of video audio tracks. Whisperer's microphone,
  cloud engine and cloud model choices do not change Video-Analyzer transcription.
- **Vision:** Image-Interpreter and Video-Analyzer each have two independent
  vision-capable observers and a text merger. A catalog entry alone does not
  prove vision support, tool support, context capacity or account entitlement.
  `claude_image_model` is the separate Anthropic image path, using its existing key.
- **LaTeXer:** an explicitly empty `latexer_model` disables model repair. Empty
  optional fields are meaningful; do not fill them with a guessed model.
- Agents with no AI model have no selector. External ACPX coding-agent CLIs and
  external MCP servers keep their own provider configuration. This dialog does
  not replace their credentials, endpoints, CLI settings or external model IDs.

## Global choices, overrides and Parametrizer

New templates use the quoted YAML string `"@config"`. A missing registered field
also inherits. In a canvas agent or standalone agent, a literal value wins over
the saved global choice. Existing workflows are not rewritten on Save. To opt an
old workflow into central settings, change its model fields to `"@config"`.

```yaml
# Video-Analyzer: follow all central model choices.
interpreter_model_1: "@config"
interpreter_model_2: "@config"
merging_model: "@config"
transcription:
  model: "@config"
```

```yaml
# FlowCreator: either inherit or deliberately pin this agent.
llm:
  model: "@config"  # A literal model tag here is a per-agent override.
```

| Launch path | Resolution order (last choice wins) |
|---|---|
| Canvas / standalone agent | Initial defaults → saved globals for missing or `@config` fields; literal YAML values stay explicit |
| Wrapped chat tool | Template → global model settings (forced for registered fields) → explicit tool arguments |
| Standalone MCP wrapper | Template → inherited globals → explicit invocation overrides |

Wrapped chat deliberately starts from globals even if a shipped template contains
a literal model. Do not promise that a canvas override changes a separate chat run.
Parametrizer and FlowCreator must preserve `"@config"` and user-supplied literal
strings; they must not replace inheritance with a suggested or remembered model.
For video content routing, use `analysis_token`, `transcript`, `summary`,
`response_body` and artifact paths from the current contract. `analysis_type` is
an agent task choice, not a Models setting. See the
[Video-Analyzer contract](../Tlamatini/agent/agents/video_analyzer/README.md).

## Source, frozen and copied runtimes

| Context | Configuration and registry |
|---|---|
| Source app | `Tlamatini/agent/config.json`; registry `Tlamatini/agent/agents/model_settings.py` |
| Installed app | `config.json` beside `Tlamatini.exe`, e.g. `C:/Tlamatini/config.json`; portable registry `agents/model_settings.py` |
| Explicit configuration | `CONFIG_PATH` selects another config file in both modes; use an absolute path |
| Isolated agent / reusable pool | Runtime preparation copies or refreshes the portable helper from `get_agents_root()` |
| Manually copied agent outside an `agents` tree | Carry its helper/dependencies and set `CONFIG_PATH` to the intended app config |

Portable loaders discover the app config above an ancestor named `agents`, unless
`CONFIG_PATH` overrides it. Missing/unreadable global configuration falls back to
registry defaults; malformed JSON logs a warning. Do not interpret a successful
load of defaults as proof that the intended config file was found. Parent objects
such as `llm` must retain their mapping shape; inheritance does not repair malformed
agent schemas. The registry contains no credentials.

Frozen web services import the **compiled** `agent.agents.model_settings` module.
Synthetic `_internal/.../__file__` paths are not agent template paths. Loose helper
files come from the resolved agents directory. Non-model agents such as
File-Creator do not depend on a loose model registry. A self-modification snapshot
is optional and is not required to run the installed application. Monitor-Log,
Monitor-Netstat and RecMailer read UTF-8 YAML, including a Windows BOM.

Self-update preserves the user's global configuration. New absent keys receive
registry defaults when loaded; Save persists all current values. Preserved literal
model choices are not silently migrated away. The self-modification snapshot must
carry the registry, runtime preparation, verification command, regression tests
and this guide. See [carriage and build gates](self-management-carriage.md).

## Validation and API contract

Authenticated `GET /agent/load_config_section/models/` returns `success`, `section`,
`values` and the `fields` metadata used to build the form. Authenticated
`POST /agent/save_config_models/` accepts an object containing **all 38 keys** as
strings. Read and merge the current values before posting a programmatic update;
a one-key patch is rejected. Extra payload keys do not become config updates.

Validation trims outer whitespace; required values cannot be empty; values must
be at most 512 characters with no control characters. Engine/voice choices must
match their enumerations. The global dialog rejects `@config` (only agent fields
inherit). Field errors return HTTP 400 and no settings are written. Success returns
the written path and `updated_keys`; the atomic config merge preserves unrelated
settings. This endpoint does not perform provider inference or compatibility tests.

The browser checks **changed Ollama fields** against the configured server's
catalog. Unchanged existing choices are not all revalidated on each save.
Local/provider fields are not Ollama catalog entries and can be saved independently
of Ollama. An unreachable catalog can block a changed Ollama choice; it is not
evidence that a local Whisper name or provider model ID is invalid.

## Video summaries and HTTP failures

Video-Analyzer initially uses `gemma4:cloud` and
`jcyhsiao/qwen3.5cloud:latest`, merged by `glm-5.3:cloud`. Its local audio model
initially uses `base`. `robotics` remains the default task; `transcription` extracts
timestamped audio tracks and `summary` combines speech with sampled visual evidence.

The former `qwen3-vl:235b-cloud` selection returned HTTP 410 with an explicit
retirement message on 2026-09-20. HTTP errors retain model, status and server
explanation. During summaries, observer failures with 401, 403, 404 or 410 disable
that observer for the remaining batches of **that run**. The healthy observer
continues, the result remains `partial`, and `visual_coverage` distinguishes frames
seen by any observer from frames seen by both, including failed/skipped batches.
Transient failures do not disable later batches. Robotics keeps conservative
verdict rules: missing evidence cannot become `PASS_OK`.

| Symptom | Action |
|---|---|
| HTTP 410 / retired vision model | Change the relevant Vision slot; inspect literal overrides in existing flows; start a new run |
| HTTP 401/403 | Check provider sign-in, credentials and model access; retries cannot create permission |
| HTTP 404 | Check the exact model ID and configured endpoint before selecting another model |
| Saved choice does not affect a running agent | Restart/reload it; inspect explicit YAML/tool overrides and `CONFIG_PATH` |
| Talker returns text or cannot decode audio | Choose an Orpheus-compatible audio-token model and supported voice |
| Whisperer cloud request needs credentials | Configure its provider key separately; a model name is not an API key |
| File-Creator fails at `_internal/.../model_settings.py` | Install a build with the compiled-registry fix and run the gate below; do not invent an `_internal` source tree |
| YAML text is corrupted on Windows | Use UTF-8 and the corrected loaders; include the default-codepage check below |

## Maintainer contract and verification

When adding an AI-backed agent, register every selectable model/engine/voice field
in `FIELDS` with its group, default, YAML path, kind, choices, fallback and optional
semantics. Load through the portable resolver, put `"@config"` in new templates,
and preserve explicit overrides. Core services must actually consume their saved
key. Keep credentials out of registry metadata. Update the
[new-agent guide](../Tlamatini/.agents/workflows/create_new_agent.md),
[new-MCP guide](../Tlamatini/.mcps/create_new_mcp.md), planner catalogs, prompts and
this reference in the same change. Regenerate catalogs with
`python scripts/update_flow_catalog.py` and check with its `--check` option.

Run from the repository root in PowerShell:

```powershell
python Tlamatini/manage.py check_agent_runtimes
python -X utf8=0 Tlamatini/manage.py check_agent_runtimes
& 'C:/Tlamatini/Tlamatini.exe' check_agent_runtimes
python Tlamatini/manage.py test agent.test_model_settings agent.test_flow_knowledge agent.test_video_analyzer_agent agent.test_video_analyzer_content agent.test_talker_agent agent.test_whisperer_agent agent.test_image_interpreter_agent --noinput
```

`check_agent_runtimes` prepares every installed template in private scratch space,
executes actual model/YAML loaders, refreshes stale helpers and planning catalogs,
then runs File-Creator and compares exact output bytes. It does not call providers,
send messages or exercise other desktop/hardware workflows. The build must carry
this command and execute it in the new frozen executable **before ZIP creation**.
File-only inclusion sweeps complement this execution check; they do not replace it.

On 2026-09-20, source, Windows default encoding, fresh frozen, frozen without a
self-modification snapshot and installed modes each passed **89 runtime setups,
21 model loaders and 3 planning catalog refreshes** plus File-Creator execution.
Wrapped-chat and standalone MCP File-Creator paths also completed. Focused
regressions passed **394 tests, with 5 skipped**. A visible installed-dialog check
saved Talker voice `jess`, confirmed the actual loader read it, restored `tara`,
and reconnected chat. These are dated checks, not a claim that every model service
or all 89 agents' external actions were exercised. See
[verification evidence](model-configuration-verification.md).
