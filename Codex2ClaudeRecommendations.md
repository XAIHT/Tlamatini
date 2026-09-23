# Codex to Claude: Tlamatini skill audit and recommendations

Prepared by Codex on 2026-09-23 for Claude and Angela.

## Mandatory correction: every execution must be visible

**HEADLESS IS FORBIDDEN.** Angela reaffirmed on 2026-09-23 that every command,
automated test, diagnostic, script, build, agent and browser must execute in a
visible, forked foreground window on her real desktop. This governs **every
recommendation and acceptance check below**, including lint and isolated probes:
run commands in visible CMD/PowerShell consoles, browsers with `headless=False`,
and monitor live. If visibility cannot be confirmed, do not run. See
[AGENTS.md](AGENTS.md) and [Claude's execution-policy handoff](TestsVisiblesAndVisibleExecutionFromClaude2Codex.md).

Validation of this follow-up ran in a separate PowerShell console whose native
window checks reported `Visible=True` and `Foreground=True`. All five browser
launch sites across the four corrected runners explicitly use `headless=False`.
Python syntax and focused Ruff checks passed; all 41 skill frontmatter blocks
were preserved and their policy links resolved. Runtime skill validation passed
29 packages with three body-size warnings; both Codex skills validated. The live
application/browser suites were not run during this policy update.

The original audit below is a dated snapshot. Its static outputs do not establish
foreground visibility, and they must not be described as watched UI evidence.
The audit also missed additional harnesses that could honor headless settings;
future execution reviews must inspect launch sites, fallbacks and environment
overrides. Subsequent fixes do not retroactively change the original evidence.

## Executive assessment

The repository contains **41 tracked SKILL.md files representing 36 distinct skill names**: 29 Tlamatini application skills, five maintainer skills copied under both Claude and Gemini, and two Codex documentation skills.

The central issue is that the skill documents, their executable runtime, and their maintenance checklists no longer consistently describe the same behavior. Some recent corrections were appended without removing instructions they supersede. Other contracts are declared but not enforced by the execution path.

The most urgent work is to make skill invocation truthful, deliver the complete applicable procedure, prevent credential inputs from being copied into ordinary audit/output records, and align documented permission and budget guarantees with actual enforcement. Updating prose alone will not resolve those runtime findings. Conversely, several other findings require correcting instructions to match working code, rather than changing that code.

**This report requests follow-up work; it does not implement the recommendations.** The only deliverable created in this task is this Markdown report. Existing application/configuration edits were left untouched. No live credentials were inspected or used in the probes described below.

## Scope and evidence limits

Baseline:

- Repository: C:/Development/XAIHT/Tlamatini.
- HEAD: **158971b297be1163c37ca86bdaf5f949f40dbe3b**.
- Nearest reachable version tag from git describe: **v1.65.5**.
- That tag is annotated and resolves to **b09c4ff66de35d823c21ea88668d7f4ce7250811**. HEAD and the release commit are therefore recorded separately.
- Discovery included hidden and ignored skill directories, excluding dependency, Git, virtual-environment, and cache trees.
- All 41 skill definitions were reviewed, using byte comparisons and content diffs for mirrored copies. Selected supporting scripts, runtime modules, tests, and onboarding documents were inspected.
- This is a complete report of this skill audit, not a claim to have audited every application subsystem or every historical document.
- All 41 discovered definitions are tracked. There is **no finding that these skills are untracked or missing from Git**.
- All 29 application skills currently declare the in-process runtime. Their descriptions below summarize intended capabilities; presence in the registry does not prove successful execution.

Evidence categories:

| Label | Meaning |
|---|---|
| Reproduced | Observed with the existing linter or an isolated, in-memory Python probe. |
| Source-confirmed | Directly supported by inspected implementation and document locations. |
| Documentation conflict | Two active instructions disagree, or instructions disagree with inspected code. |
| Follow-up verification | A risk or unverified capability that needs a targeted test; no live failure is asserted. |

Validation actually performed:

1. File discovery, tracked-file census, skill-name inventory, hashes, and whitespace-aware mirror diffs.
2. The existing skill linter: **exit 1; 28 passed, 1 failed**.
3. Isolated loading of the real skill registry and calls through the real SkillHarness methods, with its audit sink replaced by an in-memory recorder. This avoided creating audit files, launching the application, executing tools, or using a database.
4. A synthetic, unmistakably non-credential marker to check input propagation. No real API key was used.
5. Static comparison against workflow normalization, reporting, model settings, MCP activation, static-version, planner binding, and registry-loading code.

Not performed: Django application test suites, visible browser regressions, a frozen build, installation/update/snapshot sweeps, external API calls, ACPX child launches, penetration testing, or any database operation. No connector is certified healthy by this report.

## Priority map

High = address before relying on the affected execution or maintenance contract. Medium = correct during the skill consistency pass. These are engineering priorities, not CVSS scores.

| ID | Priority | Finding |
|---|---|---|
| R01 | High | In-process invocation reports success with placeholder results. |
| R02 | High | Invocation truncates 15 of 29 skill bodies to 2,000 characters. |
| R03 | High | Permission and budget claims exceed the harness's enforcement. |
| R04 | High | Credential inputs propagate into audit events and returned envelopes. |
| R05 | Medium | Validators disagree; the catalog currently fails its own linter. |
| R06 | High | The flow doctor validates an obsolete workflow shape. |
| R07 | High | Agent-creation guidance still contradicts automatic Exec Report capture. |
| R08 | Medium | Naming instructions still suggest title-casing and migration-first repair. |
| R09 | High | Parametrizer instructions tell Claude to hand-edit a generated list. |
| R10 | High | Ask-Execs coverage is described as automatic when it uses an explicit policy set. |
| R11 | High | The MCP addition recipe can deactivate existing servers. |
| R12 | High | The master agent-creation checklist omits current model and catalog gates. |
| R13 | High | An obsolete prompt-ID renumbering instruction remains active. |
| R14 | Medium | Static-version instructions no longer match the settings expression. |
| R15 | Medium | Claude/Gemini procedures and test inventories have drifted. |
| R16 | Medium | Daily-test instructions contradict the visible-foreground requirement. |
| R17 | Medium | Skill-root precedence contradicts the intended editable-copy preference. |
| R18 | Medium | Planner diagnostics do not explain the final bound tool set. |
| R19 | Medium | CSRF audit categories imply safety without establishing it. |
| R20 | Medium | Dependency and permission metadata do not cover their procedures. |
| R21 | Medium | Current-state facts and the skill inventory need one consistent maintenance path. |
| R22 | Medium | The optional ACPX skill adapter bypasses existing delivery-verdict handling. |

## Detailed recommendations

### R01 — Separate a loaded plan from completed work

**Evidence: reproduced and source-confirmed.**

[SkillHarness._run_in_process](C:/Development/XAIHT/Tlamatini/Tlamatini/agent/skills/harness.py:215) deliberately returns a planning envelope and synthesizes output-shaped placeholders. [_invoke_inner](C:/Development/XAIHT/Tlamatini/Tlamatini/agent/skills/harness.py:204) then returns ok: true after type/shape validation.

The isolated hello-world invocation returned:

~~~json
{
  "hello_world_ok": true,
  "greeting": "<plan-only stub for greeting; the calling agent should replace this with the actual value>",
  "expected": "hello, audit",
  "tokens_used": 0
}
~~~

The [hello-world contract](C:/Development/XAIHT/Tlamatini/Tlamatini/agent/skills_pkg/hello_world/SKILL.md) requires the actual greeting. The [existing harness test](C:/Development/XAIHT/Tlamatini/Tlamatini/agent/tests.py:4115) checks that greeting exists, but not its value. The [ACPX smoke test](C:/Development/XAIHT/Tlamatini/Tlamatini/agent/acpx/tests.py:283) checks discovery and parsing.

The authoring guide already acknowledges this planning design at [create_new_skill.md](C:/Development/XAIHT/Tlamatini/Tlamatini/.skills/create_new_skill.md:59). Therefore the finding is not that a scoped executor was secretly promised everywhere; it is that the public success/output contract does not clearly distinguish plan availability from completed work.

**Impact:** a caller can mistake schema-valid placeholders for verified output. A stub doctor_ok: false or changed: false is also not an observation that the doctor failed or no change was needed.

**Recommendation:** define an explicit execution state such as planned, running, completed, failed. Return pending outputs separately from observations. Either keep this as an honest planning interface or implement a scoped executor; make the choice explicit across the tool description, UI, docs, and tests. Do not merely special-case hello-world while leaving other placeholders ambiguous.

**Acceptance:** the actual greeting is checked if hello-world is executable. Planning-only skills cannot be interpreted as completed operations. At least one real harmless deliverable is verified through the intended execution path.

### R02 — Deliver the whole applicable procedure

**Evidence: reproduced and source-confirmed.**

The harness uses **self.skill.body[:2000]** at [harness.py:242](C:/Development/XAIHT/Tlamatini/Tlamatini/agent/skills/harness.py:242), without returning the complete body or a continuation mechanism in that envelope. The registry's planner preview is independently shorter; it is discovery data, not a replacement for execution instructions.

**15 of 29** current bodies exceed 2,000 characters. For example:

- In create-new-agent, the Central model settings section starts at character offset **6603**.
- In roblox-studio, VERIFY & REPORT starts at offset **6506**.
- Both are outside the invocation excerpt.

These offsets refer to the parsed body, not the file including frontmatter. Other tools or a human could separately read the file; this probe establishes that invoke_skill itself does not supply those instructions.

**Impact:** the caller can receive a partial procedure while the envelope says it has loaded the playbook. Late validation, failure handling, and current contract amendments become unavailable through this path.

**Recommendation:** provide the complete body when execution is requested, or an explicit bounded retrieval protocol that guarantees every required section is read. Include the skill identity/hash and reference locations. Mark previews as previews. Put references behind a supported retrieval path rather than assuming the caller knows the source layout.

**Acceptance:** a sentinel beyond character 2,000 reaches the executing context; required referenced material is retrievable; truncation is explicit and cannot silently count as full loading.

### R03 — Make permission and budget guarantees accurate

**Evidence: source-confirmed.**

[invoke_skill's description](C:/Development/XAIHT/Tlamatini/Tlamatini/agent/acpx/tools.py:639) says the harness enforces permissions and budget. The harness module's introductory documentation describes a scoped tool map. The [authoring guide](C:/Development/XAIHT/Tlamatini/Tlamatini/.skills/create_new_skill.md:161) calls the budget hard-enforced.

The current in-process path only includes permissions, requires_tools, and requires_mcps in the returned envelope. It does not create the claimed scoped execution loop. It ticks one iteration for preparing the plan; subsequent caller actions are outside that harness invocation. Budget.add_tokens is defined but is not called by either runtime path in the inspected harness.

For ACPX, runtime.send returns a collected list. The harness iterates it afterward, so its iteration-time checks do not independently interrupt the blocking send at the skill's wall-clock deadline. The underlying ACPX runtime has its own controls; those are not proof that the skill's declared limits govern this operation.

**Impact:** policy metadata is presented as enforcement even when it is advisory. This is not a demonstrated escape from every application control; it is a concrete mismatch at the skill boundary.

**Recommendation:** document the actual boundary now. If execution scoping is implemented, enforce tool capabilities, resolved filesystem/shell/network scopes, dependency availability, token accounting, cancellation, and deadlines at the dispatcher. Distinguish a planning budget from the eventual execution budget. Preserve existing owner-defined tool policies.

**Acceptance:** denied operations never reach a controlled test tool; budgets stop the actual operation; later caller actions are either attributed to the same controlled invocation or explicitly outside its scope.

### R04 — Redact secret inputs before audit and output serialization

**Evidence: reproduced with synthetic data; source-confirmed.**

The [setup-new-acpx-key input](C:/Development/XAIHT/Tlamatini/Tlamatini/agent/skills_pkg/setup_new_acpx_key/SKILL.md:36) explicitly accepts api_key. The harness records all coerced arguments at [harness.py:180](C:/Development/XAIHT/Tlamatini/Tlamatini/agent/skills/harness.py:180), includes them in the returned plan envelope, and writes that envelope to the audit log.

The in-memory probe established:

~~~json
{
  "synthetic_input_in_returned_envelope": true,
  "synthetic_input_in_audit_events": true,
  "key_probe_ok": true,
  "doctor_ok": false
}
~~~

The real audit sink serializes its event dictionaries to NDJSON. This demonstrates an unredacted data path; it does **not** establish that real credentials have already leaked, been committed, or been sent externally.

**Recommendation:** mark sensitive inputs explicitly and redact them before any log or public envelope is formed. Prefer credential references over literal secrets where the architecture supports that. Check nested payloads, failure details, and exception serialization. Keep the value available only to the authorized operation that needs it.

**Acceptance:** a synthetic marker can reach a controlled credential consumer but is absent from audit files, UI/tool output, and error text. Verification must not print actual credential values or prefixes.

### R05 — Unify validation and repair the present lint failure

**Evidence: reproduced and source-confirmed.**

Running the shipped linter returned exit 1:

~~~text
[FAIL] .../create_new_agent/SKILL.md: body too large (8451 bytes > 8 KiB cap)
[skill-lint] 28 skills passed, 1 failed
~~~

The printed unit is wrong: [lint.py:57](C:/Development/XAIHT/Tlamatini/Tlamatini/agent/skills_pkg/_meta/lint.py:57) uses Python string length, which counts characters. Actual parsed sizes are:

| Skill | Characters | UTF-8 bytes |
|---|---:|---:|
| create-new-agent | 8,451 | 8,763 |
| setup-new-acpx-key | 8,158 | 8,466 |

The second passes the present character-count check while exceeding a literal 8 KiB limit.

[quick_validate.py](C:/Development/XAIHT/Tlamatini/Tlamatini/agent/skills_pkg/skill_creator/scripts/quick_validate.py:31) checks for a few substrings and a 12,288-character whole-file ceiling. It does not actually parse YAML despite its docstring. The parser does not run the shipped JSON schema or comprehensively enforce its ranges. Registry loading does not enforce the linter's body cap.

**Recommendation:** use one shared validation routine for quick validation, catalog lint, and diagnostics, with an explicit policy for runtime rejection versus warnings. Measure encoded bytes if the contract remains KiB. Validate schema ranges, names, dependency metadata, and duplicate policy. Move long detail into references without losing execution-time access; solve R02 at the same time.

**Acceptance:** all 29 packages pass the agreed validator; malformed YAML and invalid budgets fail consistently; multibyte fixtures verify the size unit; quick validation cannot pass a file the canonical parser rejects.

### R06 — Rebuild the flow-doctor procedure around the current schema and contracts

**Evidence: documentation conflict and source-confirmed.**

[Flow doctor lines 47–59](C:/Development/XAIHT/Tlamatini/Tlamatini/agent/skills_pkg/tlamatini_flw_doctor/SKILL.md:47) require version/agents/connections and from/to links. The sibling [flow-from-objective guide](C:/Development/XAIHT/Tlamatini/Tlamatini/agent/skills_pkg/tlamatini_flow_from_objective/SKILL.md:71) explicitly identifies that representation as obsolete.

The actual [normalizer](C:/Development/XAIHT/Tlamatini/Tlamatini/agent/services/flow_spec.py:74) reads nodes, connections, artifacts, and schemaVersion; connections use sourceId/targetId or indexed references plus slots.

The doctor also mixes old terminal/Ender assumptions with a later appendix describing Ender target_agents as a kill list. Execution, observation, and kill relationships need distinct interpretation.

**Recommendation:** replace the obsolete numbered checks, rather than append another correction. Base validation on the current FlowSpec, generated catalog, and AgentContract semantics. Use a supported dry-run validation path without writing user pool configuration. Treat unknown schema versions explicitly.

**Acceptance:** a valid schemaVersion-2 flow passes; bad indices, bad slots, dangling references, incomplete Parametrizer mappings, and invalid execution/kill relationships yield specific findings without modifying the flow.

### R07 — Remove every obsolete Exec Report membership instruction

**Evidence: documentation conflict and source-confirmed.**

The master [.claude agent-creation skill](C:/Development/XAIHT/Tlamatini/.claude/skills/tlamatini-agent-creation/SKILL.md) contains both rules:

- Line 438, step 276: capture is automatic for wrapped agents.
- Line 440, step 278: curated map entries are optional refinements.
- Line 83, step 3: state-changing versus observational decides membership.
- Line 606, step 402: test map membership for state-changing agents and absence for observational agents.
- Line 745, step 515: a missing map entry means no table; an observational entry means a spurious table.

The actual [resolver](C:/Development/XAIHT/Tlamatini/Tlamatini/agent/mcp_agent.py:388) captures registered wrapped agents automatically, except management/polling helpers. Several agent descriptions in CLAUDE.md also retain observational → not in Exec Report wording.

**Recommendation:** replace all old membership gates, checklist items, test advice, and onboarding summaries. Separate capture eligibility from optional caption styling and shared-key grouping. Retain the shared agent_verdict classification contract.

**Acceptance:** every eligible wrapped agent resolves to a report spec; observational agents are covered; curated-map absence is not treated as missing capture; no active instruction recommends suppressing observational results.

### R08 — Make canonical naming the first implementation step everywhere

**Evidence: documentation conflict and source-confirmed.**

The [naming skill](C:/Development/XAIHT/Tlamatini/.claude/skills/tlamatini-agent-naming/SKILL.md:16) correctly identifies the boot resolver as authoritative. The implementation's override map is in [agent_paths.py:102](C:/Development/XAIHT/Tlamatini/Tlamatini/agent/services/agent_paths.py:102).

However:

- [tlamatini-new-acp-agent metadata](C:/Development/XAIHT/Tlamatini/Tlamatini/agent/skills_pkg/tlamatini_new_acp_agent/SKILL.md:34) says the display name is derived as title-case.
- The master skill's step 510, line 740, ends with Fix it in the migration FIRST even while describing the boot override map.

**Recommendation:** establish the exact display name in the resolver, then align the migration, wrapped registry, CSS attributes, labels, and derived identifiers. Remove generic title-casing advice. Preserve intentional hyphens and spaces.

**Acceptance:** a fresh boot, palette, wrapped enable gate, and saved/reloaded flow all retain the exact intended spelling. Use the existing display-name coverage rather than creating a second naming map.

### R09 — Stop treating Parametrizer membership as a manually maintained list

**Evidence: source-confirmed.**

The master skill's [steps 156–159](C:/Development/XAIHT/Tlamatini/.claude/skills/tlamatini-agent-creation/SKILL.md:278) still tell Claude to edit SECTION_AGENT_TYPES and keep two lists coherent. Step 522 corrects an even older three-list rule but remains outdated itself.

The actual [Parametrizer implementation](C:/Development/XAIHT/Tlamatini/Tlamatini/agent/agents/parametrizer/parametrizer.py:132) derives membership:

~~~python
SECTION_AGENT_TYPES = [
    name for name, spec in load_catalog().items()
    if spec["output_fields"]
]
~~~

The runtime skill appendices already say not to maintain a separate hardcoded producer list.

**Recommendation:** register structured output in the canonical contract, regenerate/check the flow catalog, and refresh portable runtime copies. Replace every instruction to append directly to SECTION_AGENT_TYPES. Test that declared output fields agree with emitted fields and the generated catalog.

**Acceptance:** a producer becomes available after contract/catalog updates without hand-editing Parametrizer's membership expression; isolated runtime copies see the same fields.

### R10 — Describe Ask-Execs as the actual explicit policy

**Evidence: source-confirmed.**

The master [step 268](C:/Development/XAIHT/Tlamatini/.claude/skills/tlamatini-agent-creation/SKILL.md:423) says any state-changing wrapped agent is automatically prompted, with no wiring needed.

The implementation uses [_ASK_EXECS_REQUIRED_TOOLS](C:/Development/XAIHT/Tlamatini/Tlamatini/agent/mcp_agent.py:437), and [_requires_exec_permission](C:/Development/XAIHT/Tlamatini/Tlamatini/agent/mcp_agent.py:951) checks membership. The code records deliberate owner decisions, including ungated messaging and visible-operation categories.

**Recommendation:** make classification against the current policy an explicit creation step. Document whether the new tool belongs in the set, with the existing policy as authority. Do not broaden prompts merely because this report identifies inaccurate documentation.

**Acceptance:** appropriate tools prompt when the checkbox is enabled, denied operations do not execute, and deliberately ungated categories remain unchanged.

### R11 — Preserve existing MCP activation state when adding one server

**Evidence: source-confirmed.**

The [adding-external-mcp recipe](C:/Development/XAIHT/Tlamatini/Tlamatini/agent/skills_pkg/adding_external_mcp/SKILL.md:180) activates a new server using a list containing only my-server.

The underlying [set_active](C:/Development/XAIHT/Tlamatini/Tlamatini/agent/external_mcp_manager.py:407) replaces the complete active set and closes clients no longer in that set.

**Impact:** following an add-server recipe literally can disconnect every currently active server.

**Recommendation:** read the current active set, preserve it, merge the requested addition, and handle the five-server limit explicitly. Use the replacement behavior only when replacement was intended. Do not silently pick an existing server to deactivate.

**Acceptance:** adding B while A is active leaves A and B active; attempting a sixth addition reports the capacity conflict without discarding an unrelated active server.

### R12 — Bring the master agent-creation skill up to the current model/catalog contract

**Evidence: documentation omission confirmed by searches.**

The two master agent-creation copies contain no matches for model_settings, check_agent_runtimes, update_flow_catalog, flow_catalog, or @config.

By contrast, [create-new-agent](C:/Development/XAIHT/Tlamatini/Tlamatini/agent/skills_pkg/create_new_agent/SKILL.md:103), the smaller scaffolding skill, CLAUDE.md's Central model selection section, and both inclusion skills describe these current requirements.

**Recommendation:** add explicit completion steps for:

1. Registering configurable model/engine/voice fields in the central model registry.
2. Preserving inheritance and explicit overrides, including optional-empty semantics.
3. Keeping the portable helper and compiled frozen module available through the established path resolvers.
4. Regenerating and checking the canonical flow catalog after contract changes.
5. Checking source and fresh frozen runtimes, including builds without self-modification source.
6. Updating the central field map and relevant prompts/docs.

Inherited guidance elsewhere reduces the chance of a miss, but the self-described exhaustive master checklist should name these gates directly.

**Acceptance:** a maintainer using the master checklist can identify every affected surface; source, copied-pool, and frozen runtime evidence is reported separately.

### R13 — Remove the instruction to renumber existing prompt IDs

**Evidence: documentation conflict and source-confirmed.**

The master skill correctly describes append-only IDs and sort_rank at [step 341](C:/Development/XAIHT/Tlamatini/.claude/skills/tlamatini-agent-creation/SKILL.md:526), but [step 352](C:/Development/XAIHT/Tlamatini/.claude/skills/tlamatini-agent-creation/SKILL.md:539) still instructs shifting existing idPrompt/promptName suffixes to insert earlier.

[CLAUDE.md](C:/Development/XAIHT/Tlamatini/CLAUDE.md:201) describes historical renumbering as a one-time authorized operation. [list_prompts_view](C:/Development/XAIHT/Tlamatini/Tlamatini/agent/views.py:289) orders by category rank, sort_rank, and idPrompt.

**Recommendation:** remove the obsolete insertion rule. Append a new ID and use sort_rank for display order, retaining the section-opener convention. Do not rewrite historical migrations or existing IDs as part of this documentation repair.

**Acceptance:** documentation presents one append-only procedure; a new card can appear in the intended section position without changing any existing identity.

### R14 — Rewrite static cache-refresh guidance around the real expression

**Evidence: source-confirmed.**

The [static-version skill](C:/Development/XAIHT/Tlamatini/Tlamatini/agent/skills_pkg/tlamatini_static_version_bumper/SKILL.md:45) calls STATIC_VERSION an integer, expects a quoted numeric assignment, and permits rotating semver.

The current [settings expression](C:/Development/XAIHT/Tlamatini/Tlamatini/tlamatini/settings.py:250) combines an environment override or startup timestamp with a suffix:

~~~python
STATIC_VERSION = (
    os.environ.get('STATIC_VERSION') or str(int(time.time()))
) + '-ctxspinner-1'
~~~

**Recommendation:** document the intended cache-refresh mechanism, environment override, suffix policy, collected-static synchronization, and restart/reload requirements. Preserve the dynamic expression. Keep product release resolution separate.

**Acceptance:** the recipe works on the current source and cannot replace the expression with a guessed literal or product version. Served assets are verified after an actual frontend change.

### R15 — Establish a deliberate Claude/Gemini synchronization policy

**Evidence: file comparison.**

Three mirrored SKILL.md pairs are byte-identical: naming, self-modify inclusion, and self-update inclusion. Agent creation and daily chat testing have substantive differences.

Missing from the Gemini agent-creation copy are Claude-side additions about existing-agent changes, Whisperer's sentinel/default behavior and monitoring bounds, corrected Parametrizer prose, rendering/measurement lessons, and PDFer style guidance.

The Claude daily-test copy also includes later PDFer, voice-command, and Grepper instructions. Its questions.py has one additional line, and wrapped_questions.py has 14 additional lines after ignoring end-of-line differences.

Fifteen tracked harness files exist only under Claude:

~~~text
_peek.py
_stage.ps1
context_gauge_100.py
context_gauge_visible.py
context_restore_spinner_visible.py
grepper_lines_visible.py
grepper_login_probe.py
monitor.py
pdfer_nuance_visible.py
pptxer_visible.py
preflight.py
uninstaller_visible.py
voice_commands_visible.py
window-test-screen.py
windower_focus.py
~~~

These filenames are relative to tlamatini-daily-chat-test/harness. Their presence is inventory evidence, not a claim that every helper must be copied.

The two inclusion sweep scripts differ by raw hashes but showed **no content differences with end-of-line whitespace ignored**. Do not report that as a functional checker divergence.

**Recommendation:** decide which files are shared and which are intentionally assistant-specific. Generate or check shared copies from one source, with documented exceptions. Correct shared mistakes before propagating them; blind copying would spread the stale instructions in this report.

**Acceptance:** meaningful mirror drift is either eliminated or explicitly recorded; line-ending-only differences do not create false alarms.

### R16 — Resolve foreground/background contradictions in the daily-test recipe

**Follow-up, 2026-09-23:** Claude has corrected step 4 in both maintainer mirrors
to require a visible foreground window. Codex has added the rule to all 41
skills, the root agent instructions and execution runbooks. The four additional
visual runners for Create Flow, voice, self-healing and browser performance now
explicitly launch with `headless=False`; the legacy `HEADLESS` environment
variable cannot select a hidden browser. The original finding below records the
pre-fix audit; it is not a claim that step 4 still permits background execution.

**Evidence: documentation conflict.**

[Lines 23–27](C:/Development/XAIHT/Tlamatini/.claude/skills/tlamatini-daily-chat-test/SKILL.md:23) require visible, headed, foreground operation and forbid run_in_background. [Step 4, line 84](C:/Development/XAIHT/Tlamatini/.claude/skills/tlamatini-daily-chat-test/SKILL.md:84) tells the maintainer to run the long test in the background.

**Recommendation:** remove the conflicting instruction. Explain how a long-running test remains visible while the coordinating assistant monitors progress. Make credentials, the target installation, and completion detection explicit. Preserve the requirement to reject stale, transient, or timed-out answers.

**Acceptance:** one unambiguous launch procedure follows the owner's visible-test requirement; reports identify the tested installation and actual UI evidence.

### R17 — Correct registry precedence and make duplicate handling explicit

**Evidence: source-confirmed; frozen symptom not exercised.**

[SkillRegistry._default_roots](C:/Development/XAIHT/Tlamatini/Tlamatini/agent/skills/registry.py:98) adds the editable install root before the bundled root and describes an intention for the editable copy to win.

[_reload_locked](C:/Development/XAIHT/Tlamatini/Tlamatini/agent/skills/registry.py:182) uses unconditional assignment by skill name, so later roots win. With both copies present, the described precedence is reversed. Build configuration carries both locations.

The skill-creator text also says the registry rejects duplicates, whereas the inspected loader silently replaces an earlier same-name entry. The linter detects duplicates within its scanned tree; that is a different behavior.

**Recommendation:** define root precedence once, normalize/deduplicate roots, and distinguish an intentional override across roots from an accidental collision within one source. Expose the selected source in diagnostics. Preserve the desired user-editable copy behavior.

**Acceptance:** two controlled roots containing different bodies for the same name select the documented winner; an accidental duplicate is visible; frozen behavior is separately verified.

### R18 — Explain both planner ranking and final tool binding

**Evidence: source-confirmed.**

The [planner-trace skill](C:/Development/XAIHT/Tlamatini/Tlamatini/agent/skills_pkg/tlamatini_planner_trace_replay/SKILL.md) focuses on planner scores and the top-N selection cap.

[mcp_agent.py](C:/Development/XAIHT/Tlamatini/Tlamatini/agent/mcp_agent.py:2861) subsequently performs rank-and-budget binding, using the whole enabled surface when it fits and retaining core/planned/high-ranking tools when it does not. It also has an emergency-core fallback. Checkbox filtering and availability are additional factors.

**Recommendation:** report the enabled/requested tool set, planner recommendations, final bound set, token-budget drops, and fallback events separately. If the available log lacks one stage, say so.

**Acceptance:** a why-was-this-tool-missing explanation does not attribute final availability solely to the planner's top-20 default.

### R19 — Replace CSRF safety labels with evidence requirements

**Evidence: documentation finding; no endpoint exploit was attempted.**

The [CSRF audit procedure](C:/Development/XAIHT/Tlamatini/Tlamatini/agent/skills_pkg/tlamatini_csrf_exempt_audit/SKILL.md:48) includes safe-because-internal-tool for an endpoint called by Tlamatini's own JavaScript and safe-because-websocket for a WebSocket-adjacent path. Those descriptions alone do not establish the HTTP endpoint's actual protection. It also says to inspect the view above a decorator; the decorated function follows it.

**Recommendation:** identify the decorated function correctly, then inspect its authentication, allowed methods, state changes, credential mechanism, and relevant origin/token protections. Report justified exemption, protection present, protection missing, or insufficient evidence with a concrete rationale. Do not categorically approve an endpoint based on its caller's name.

**Acceptance:** each classification cites the server-side checks that support it; ambiguous cases stay unresolved. Keep this skill read-only unless remediation is separately requested.

### R20 — Reconcile declared dependencies and permissions with the procedure

**Evidence: documentation/metadata mismatch.**

Examples:

- [roblox-studio](C:/Development/XAIHT/Tlamatini/Tlamatini/agent/skills_pkg/roblox_studio/SKILL.md:9) declares no required tools or MCPs but requires External-MCP supervisors and Studio tools in its procedure.
- [tlamatini-flow-from-objective](C:/Development/XAIHT/Tlamatini/Tlamatini/agent/skills_pkg/tlamatini_flow_from_objective/SKILL.md:9) delegates through invoke_skill without declaring it; its shell list is empty despite a scripted fallback.
- [tlamatini-new-acp-agent](C:/Development/XAIHT/Tlamatini/Tlamatini/agent/skills_pkg/tlamatini_new_acp_agent/SKILL.md:13) has a restricted file-write list that does not cover all the later model-registry/catalog/documentation steps it asks for.
- Network-deny declarations on orchestrating skills need a precise definition of whether downstream API/model calls are in scope. Do not solve ambiguity by granting unrestricted access.

These problems become operational blockers if the documented scoping from R03 is implemented literally.

**Recommendation:** distinguish direct tool requirements, dynamically discovered external capabilities, delegated skill requirements, and downstream effects. Validate the resolved procedure against its scope. Give an explicit unavailable/dependency-missing result when a prerequisite is absent.

**Acceptance:** intended procedures can run within their declared scope, and an undeclared capability cannot silently pass through a newly enforced dispatcher.

### R21 — Separate current facts, historical evidence, and inventory ownership

**Evidence: documentation conflicts and inventory.**

The Codex dossier skills mandate source-derived facts but retain active-looking old release/count examples. The daily-test release section still mixes old counts with instructions to validate the current release. The static-version skill says current annotated release v1.63.0. CLAUDE.md labels v1.64.0 current, while this audit found reachable annotated v1.65.5 and a later HEAD.

CLAUDE.md's permanent-skill inventory discusses two sets and omits the Gemini mirrors and Codex dossier skills. That is an onboarding inventory gap; all four locations are tracked.

The master creation skill also advertises 530+ steps in frontmatter and 700+ in its title, with reused numbering. This is low-impact by itself but makes references harder to maintain.

**Recommendation:** use a generated current-facts block or one canonical facts source. Keep dated historical records explicitly historical. Inventory all four skill locations and state their intended consumers. Use stable section IDs rather than changing advertised step counts.

**Acceptance:** current claims resolve to current source/Git facts, historical counts remain intact as history, and every tracked skill location is discoverable from onboarding.

### R22 — Make the ACPX skill adapter use delivery-aware results

**Evidence: source-confirmed; latent path, not exercised against a live CLI.**

[SkillHarness._run_acpx](C:/Development/XAIHT/Tlamatini/Tlamatini/agent/skills/harness.py:286) scans reversed events for any text/answer and returns answer/events. It does not inspect the child's delivered verdict before the generic success envelope.

The main [ACPX tools](C:/Development/XAIHT/Tlamatini/Tlamatini/agent/acpx/tools.py:66) already avoid reporting success when delivered is false. [extract_last_assistant_text](C:/Development/XAIHT/Tlamatini/Tlamatini/agent/acpx/runtime.py:205) already distinguishes assistant output from log events. The runtime can emit an assistant message, then stderr log text, then a done verdict; the harness's reverse scan can therefore select stderr as the answer.

All shipped skills are currently in-process, so this is a risk for custom/future ACPX-runtime skills, not a claim that one of the 29 bundled skills hit it.

**Recommendation:** use the established assistant-text extraction and shared delivery semantics. Preserve useful failure payloads. Specify how structured declared outputs are decoded, since this path currently produces answer/events rather than arbitrary declared output fields. Apply the actual skill deadline before/during the child operation, as discussed in R03.

**Acceptance:** a delivered answer with stderr retains the answer; a blocked/empty child is not completed successfully; timeout and cleanup are deterministic; structured output validation is meaningful.

## Capabilities requiring follow-up verification, not asserted failures

The GitHub, Gmail, Jira, Notion, Slack, Todoist, Trello, and weather packages are thin integration recipes. This audit did not authenticate with those services or check current upstream API compatibility. Do not claim they work merely because they parse.

For each integration, a future verification should record the supported upstream API/CLI version, credential mechanism and minimum scopes, one read-only result check, pagination and retry behavior, and appropriate validation of action-specific payloads. Where a requested action sends messages or changes remote state, use the user's authorized scope.

Other items worth checking during the consistency pass:

- References resolved from installed skill directories, rather than only from the source checkout.
- Code-review collection of staged versus unstaged changes: avoid duplicate findings when comparing HEAD and the index.
- Security-scan output truncation before JSON parsing: collect a valid full machine-readable result, then summarize it.
- Credential setup readiness: distinguish CLI resolvability from authentication and actual delivery.
- ALLOWED_HOSTS changes: derive the current setting before assuming the wildcard described by the skill is still present.

These are follow-up checks, not additional reproduced defects in this report.

## What Claude should do in what order

### Pass 1 — Correct the execution contract

Address R01–R04 together. Decide whether skill invocation is a planning handoff or a scoped execution service. Make status, output, full instruction delivery, redaction, audit attribution, and enforcement consistent. Reuse the existing runtime and policy layers where appropriate; do not introduce a second competing permission or verdict vocabulary.

### Pass 2 — Repair instructions that can cause incorrect changes

Address R06–R14. Update the numbered procedure, summary, checklist, and pitfalls together. Remove superseded active instructions instead of appending another dated exception. Give special attention to generated Parametrizer data, canonical naming, prompt identity preservation, MCP active-set replacement, and the model settings gate.

### Pass 3 — Make the package inventory maintainable

Address R05 and R15–R21. Share validation, define mirror ownership and root precedence, reconcile declared dependencies, and separate current facts from historical evidence. Then review R22 before advertising custom ACPX-runtime skills as complete.

### Pass 4 — Verify actual behavior at the appropriate surface

Use focused verification tied to the changed behavior:

| Surface | Minimum useful evidence |
|---|---|
| Skill runtime | Honest planning/completion state; exact harmless output; full procedure availability; redacted audit; real enforcement if claimed. |
| Workflow checks | Valid current-schema fixture plus invalid topology/slot/mapping cases; no writes during validation. |
| Agent integration | Canonical name; generated catalogs; central model inheritance/override; automatic report capture; intended Ask-Execs policy. |
| External MCP addition | Existing active server survives addition; capacity handling is explicit. |
| Skill registry | Documented editable/bundled precedence and visible collision handling. |
| Validators | Same malformed/schema/size results at every entry point; all shipped packages pass. |
| UI regression | Visible target installation, real interactions and screenshots; stale/transient content rejected. |
| Packaging/runtime | Source checks, snapshot inclusion, and executed frozen checks reported as separate evidence. |

Respect the repository's existing owner constraints. In particular, this report does not authorize database-mechanics changes, a rebuild/install/update, historical migration rewrites, automatic external messages, commits, or pushes. Retain the existing shared SQLite mechanism and user-state preservation contract; documentation inconsistencies do not justify inventing a database guard.

## Complete skill inventory

Application packages are rooted at [Tlamatini/agent/skills_pkg](C:/Development/XAIHT/Tlamatini/Tlamatini/agent/skills_pkg). All 29 declare in-process. IDs below identify the most relevant recommendations, not independent execution certification.

| Skill name | Intended responsibility | Main audit relevance |
|---|---|---|
| acp-router | Select and operate an ACPX coding-agent session. | R01–R03, readiness verification. |
| adding-external-mcp | Import, activate, diagnose, and verify external MCPs. | R11; full procedure delivery. |
| code-review | Review changes with structured, line-specific findings. | Planning/completion distinction; avoid duplicate diff coverage. |
| create-new-agent | Canonical reference for adding workflow agents. | R02, R05, R12. |
| create-new-mcp | Add native tools or MCP context providers. | Full procedure and reference delivery. |
| flow-making | Run FlowCreator and convert its output into a usable flow. | R01–R03; verify the actual artifact. |
| github | GitHub operations through gh. | Live CLI/auth compatibility not verified. |
| gmail | Gmail search/read/send/reply/labels. | Live API/auth compatibility not verified. |
| hello-world | Exact greeting and harness smoke check. | R01. |
| jira | Issue search/read/create/comments/transitions. | Live API/auth compatibility not verified. |
| kali-pentest | Authorized, scoped assessment through Kalier. | Full procedure, scope and enforcement semantics. |
| notion | Pages, data sources, and blocks. | Live API/auth compatibility not verified. |
| roblox-studio | Studio builds with Luau and verified results. | R02, R20. |
| security-audit | Aggregate installed security scanner findings. | Planning/completion distinction; complete JSON results. |
| setup-new-acpx-key | Configure and verify ACPX credentials. | R04, R05; actual readiness. |
| skill-creator | Author and validate skill packages. | R05, R17, R20. |
| slack | Messages, history, threads, reactions, uploads. | Live API/auth compatibility not verified. |
| summarize | Produce a faithful brief at a target length. | Actual summary versus placeholder. |
| tlamatini-allowed-hosts-tighten | Adjust Django host configuration with a backup. | Verify current setting and actual write outcome. |
| tlamatini-csrf-exempt-audit | Inspect exemptions and recommend justified changes. | R19. |
| tlamatini-exec-report-row-adder | Refine report keys, display names, and CSS. | R07; its body already clarifies automatic capture. |
| tlamatini-flow-from-objective | Compatibility entry point delegating to flow-making. | R06, R20; retain the public name. |
| tlamatini-flw-doctor | Validate flow structure and agent relationships. | R06. |
| tlamatini-new-acp-agent | Execute the visual-agent scaffolding procedure. | R08, R12, R20. |
| tlamatini-planner-trace-replay | Explain planner selection from logs. | R18. |
| tlamatini-static-version-bumper | Refresh browser static-asset caching. | R14. |
| todoist | Tasks and projects. | Live API/auth compatibility not verified. |
| trello | Boards, lists, cards, movement, comments. | Live API/auth compatibility not verified. |
| weather | Current conditions and forecast lookup. | Live API/result compatibility not verified. |

Maintainer/documentation skills:

| Skill name | Locations | Intended responsibility |
|---|---|---|
| tlamatini-agent-creation | .claude/skills and .gemini/skills | End-to-end agent implementation and validation. |
| tlamatini-agent-naming | .claude/skills and .gemini/skills | Exact names and per-surface identifier transforms. |
| tlamatini-daily-chat-test | .claude/skills and .gemini/skills | Visible chat and agent regression harness. |
| tlamatini-self-modify-inclusion | .claude/skills and .gemini/skills | Complete, sanitized rebuildable source snapshots. |
| tlamatini-self-update-inclusion | .claude/skills and .gemini/skills | Release asset carriage and update preservation. |
| full-project-pdf-dossier | .codex/skills | Complete PDF architecture/usage/source dossier. |
| overlap-safe-pptx-dossier | .codex/skills | Complete presentation with layout verification. |

## Reproduction notes

Read-only inventory and document comparison:

~~~powershell
git ls-files -- ':(glob)**/SKILL.md'
git diff --no-index --ignore-space-at-eol -- .gemini/skills/tlamatini-agent-creation/SKILL.md .claude/skills/tlamatini-agent-creation/SKILL.md
git diff --no-index --ignore-space-at-eol -- .gemini/skills/tlamatini-daily-chat-test/SKILL.md .claude/skills/tlamatini-daily-chat-test/SKILL.md
python Tlamatini/agent/skills_pkg/_meta/lint.py
~~~

A no-index diff exits 1 when differences exist; that is expected. The linter's exit 1 is an actual validation failure.

The runtime probes imported the source registry and harness without starting Django. They used SkillHarness.__new__ to attach the actual Skill and Budget plus a MemoryAudit object implementing write/close, then called invoke normally. That exercised dispatch, output construction, and validation while bypassing the real audit sink's filesystem initialization. The credential probe inspected only whether its synthetic marker appeared in returned dictionaries and captured events.

This proves the observed envelope and audit-event contents. It does not prove a live chat displayed them, a real key was persisted, or any external operation ran. Future execution evidence should preserve the same distinction.

## Completion criteria for the follow-up

Claude's follow-up should deliver:

- One truthful skill invocation contract with evidence for every enforcement claim.
- No credential value in ordinary audit or tool-visible records.
- Full procedure availability, with explicit reference retrieval and truncation behavior.
- A clean, consistent validator result for every shipped skill.
- One active instruction per contract, with superseded advice removed from checklists.
- Documented mirror ownership, registry precedence, and an inventory of all skill locations.
- Focused source/UI/frozen evidence, each labeled with what was actually run.
- A concise list of any unresolved items, rather than a blanket claim that every skill works.

