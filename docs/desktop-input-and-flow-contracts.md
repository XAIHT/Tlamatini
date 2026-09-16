# Desktop input and flow contracts

Implementation update, 2026-09-15. GUI-Manager is still **design only**; it is not an installed agent or tool. See [its design](GUI-Manager-design.md). The [generated inventory](agent-coverage.md) lists every installed agent.

## What changed

| Component | Implemented behavior |
|---|---|
| Mouser | Physical Windows coordinates, explicit coordinate spaces, negative monitor origins, screenshot transforms, unique window/template selection, inspected cursor/geometry and honest delivery status. |
| Keyboarder | Window-bound Unicode SendInput, focus checks during delivery, modifier cleanup, literal-text mode, partial-delivery counts and nonzero failure exit. |
| Shoter | Capture rectangle, image dimensions, monitor geometry and capture time accompany the screenshot. Unproven geometry is marked `unknown`. |
| Parametrizer | Parser registration from current contracts; CRLF and empty values preserved; typed numeric/Boolean mappings; incomplete mappings do not write or launch the target; interrupted desktop segments are not automatically replayed. |
| FlowCreator | Selects from all installed agents, then designs using relevant guide sections and current schemas. Validates generated references, branches, cardinal names, singletons, configuration types and mapping fields before publishing. |
| FlowHypervisor | Execution matrix uses contract output slots, including Counter branches. Kill lists and observation/data dependencies are labeled separately. Current config timing and persistent desktop receipts supplement incremental logs. |

## Coordinate and input contract

Mouser supports `inspect`, `random`, `localized`, `click`, `drag`, `scroll`, `click_at_window`, and `locate_image`. `inspect` sends no input. `coordinate_space` is one of:

| Space | Meaning |
|---|---|
| `screen` | Physical virtual-desktop pixels, including negative coordinates. Default. |
| `desktop` | Pixel offsets from the virtual-desktop bounding rectangle's origin. |
| `normalized` | Fractions in `[0,1]` across the desktop bounding rectangle. Monitor gaps remain invalid. |
| `window` | Pixel offsets within `window_area` (`client` by default, or `window`). |
| `window_normalized` | Fractions in `[0,1]` within the selected window area. |
| `screenshot` | Pixels in the actual image analyzed, transformed through explicit capture geometry. |

For a screenshot coordinate, the transform is `screen_x = capture_left + image_x * capture_width / image_width`, with the corresponding Y transform. Supply all six geometry fields. The capture rectangle must describe the same image content; a crop needs an adjusted physical rectangle, and a resize needs the dimensions of the resized image. Letterboxing, stale screenshots, window movement and guessed image sizes are not solved by this transform. Never copy Shoter's `coordinate_space: screen` directly into Mouser for an image-space target: set Mouser's space to `screenshot` explicitly.

```yaml
# Example only: a known point in a resized 4480x1440 desktop capture.
movement_type: localized
coordinate_space: screenshot
capture_left: -1920
capture_top: 0
capture_width: 4480
capture_height: 1440
image_width: 2240
image_height: 720
end_posx: 480
end_posy: 270
button_click: left
```

This resolves to `(-960, 540)` physical pixels. It does not establish that a button occupies that point. Window anchors are geometric locations, not semantic control selectors. `locate_image` searches all monitors for a unique template match at the displayed scale; it does not recognize arbitrary natural-language button descriptions. Prefer a verified `window_handle` or a unique `window_title`; `window_match_index: -1` rejects ambiguity. Reobserve before input if the desktop changed.

The Mouser canvas dialog exposes all eight modes, including `inspect`. Coordinates remain editable for localized movement and dragging; click controls are enabled for the applicable click modes. Coordinate inputs accept fractions for normalized spaces. Existing pool folders receive the new helper modules during deployment or refresh, alongside the main scripts.

Keyboarder's `input_mode: text` sends the literal Unicode `text` value; `sequence` preserves the comma/key/chord grammar in `input_sequence`. `typing_interval_ms` controls text pacing; `stride_delay` controls sequence pacing. Bind `window_title`/`window_handle` where possible. Without either, Keyboarder binds the initial foreground window. It checks ownership during delivery and stops on focus loss; it does not prove the intended child edit control owns focus. Initially held modifiers are refused. Unicode characters and surrogate pairs use checked Windows SendInput rather than keyboard-layout-dependent typing.

Both agents publish `action_status` and `status`: `input_sent` is delivery, `observed` is inspection, and `error` can include partial changes. Keyboarder reports `characters_sent`, `commands_sent`, `commands_total`, HWND/PID, backend and `verification: input_delivery_only`. Mouser reports actual `end_posx/end_posy`, separate requested coordinates, `clicked`, locator and desktop geometry. Wrapper process status and application outcome are distinct. Target agents are still notified after failure, so branch on the receipt before further input. Do not replay a failed click, typing segment or shortcut blindly.

Shoter publishes `output_path`, `image_width`, `image_height`, `capture_left/top/width/height`, `captured_at`, `coordinate_space`, `monitors_json`, and existing output fields. Geometry marked `unknown` is unsuitable for pointer mapping. Image-Interpreter describes images and Video-Analyzer judges recorded motion; neither currently supplies a dependable semantic Windows control tree. Analyzer scans source code; it is not a desktop locator.

## Parametrizer

The current catalog has **53 declared structured-output producers**, including Keyboarder. Every producer's declared fields populate the parser registry. The generic parser accepts LF/CRLF, blank values, colon-bearing URLs and a body separated by a blank line. An empty value remains a field rather than disappearing.

Mappings remain a single-source, single-target queue with backup, execution, restoration and committed source offsets. Scalar mappings preserve the target's existing Boolean, integer or floating-point type when conversion is valid; strings remain strings, and scalar-to-list wrapping remains supported. Nullable targets have no inferred scalar type. A missing field, failed marker replacement or invalid conversion rejects the segment before writing the target config or starting it. All configured mappings must succeed.

For a generated flow, put mappings in the Parametrizer node's `_parametrizer_mappings` array; the normal compiler writes `interconnection-scheme.csv`. Example:

```json
{"source_field":"image_width","target_param":"image_width"}
```

Map all relevant Shoter geometry fields, and separately obtain a grounded image-space target. Do not interpret `input_sent` as successful editing or a completed save. A resumed Parametrizer segment targeting Mouser/Keyboarder at `config_applied` or `waiting_target` stops for inspection, retaining its progress/backup evidence. After resolving the actual application state, deliberately reconcile that saved segment or redeploy a corrected flow; restarting repeatedly does not authorize a replay. Completed/restoration-pending segments keep the existing commit behavior.

## FlowCreator and coverage maintenance

The previous guide contained entries for all 89 agents, but several entries were stale and the generated graph was insufficiently checked. In particular, Counter's `target_agents_l/g` were omitted, dangling references disappeared silently, and every leaf was attached to every Ender. Ender connections are now explicit. `target_agents` on Ender remains its kill list; its execution output is `output_agents`.

The first model request presents the complete capability roster. The second includes global flow rules, the selected agents' detailed guide sections and their current contract/schema records. Starter, Ender and Parametrizer are always available in the design stage. A guide-coverage check requires a reference section for every installed type. Unknown or unselected types fail validation, including the unimplemented GUI-Manager.

The validator checks configuration names/types, existing references, branch slots, dual inputs, singleton/system-agent wiring and Parametrizer source/target fields. It does not prove that credentials, application state, external services or an arbitrary user objective are valid. Omitted configuration values still come from deployment templates. Empty/dynamic maps such as HTTP headers allow application-specific entries. Schemas infer types from templates, with explicit support for fractional Mouser coordinates.

`llm.num_ctx` requests a context size (default 65536); provider support must be checked for the selected model. `llm.max_prompt_chars` (180000) bounds requests without pretending to be an exact token counter. `llm.repair_attempts` (2, allowed 0–3) bounds validation repair requests. Oversized prompts fail explicitly. An invalid result is not published as a successful flow; a `.flw` write failure and early configuration error exit nonzero.

The authoritative registry is `services/agent_contracts.py`, combined with installed `config.yaml` schemas and agent descriptions. `services/flow_knowledge.py` exports a catalog containing names/types, never local template values. Pool compilation and isolated chat deployment refresh `flow_catalog.json`, the standalone helper and applicable guide. Direct template execution uses the shipped catalog. Existing already-running processes require redeployment/restart to pick up code changes.

After adding an agent or changing its configuration/structured output:

1. Update its template, canonical contract, detailed guide and agent description.
2. Run `python scripts/update_flow_catalog.py` to regenerate the shipped catalog and inventory.
3. Run `python scripts/update_flow_catalog.py --check` and `python Tlamatini/agent/test_flow_knowledge.py -q`.
4. Check the intended live integration separately when its external dependencies are available.

The generated inventory measures catalog/contract coverage, not successful execution of all possible combinations. GUI control should be serialized within an interactive session; the proposed GUI-Manager's global broker is not implemented by these changes.

## FlowHypervisor

The matrix represents declared execution relationships. Counter uses both branch fields; Parametrizer includes its singular target; Ender's kill list, passive output links and watched logs are not launch edges. Passive behavior is preserved even when a builtin contract overrides credential metadata. Only directories with an agent script and configuration are discovered.

Each cycle reloads configurations and includes lifecycle facts, source dependencies and desktop timing parameters. It rereads bounded current log tails for the latest complete Mouser/Keyboarder/Shoter receipt so an error is not forgotten just because the next incremental log slice is empty. This remains an LLM watchdog: it does not inspect UI Automation trees, verify a saved document, relaunch input agents or implement GUI-Manager. A stopped PID is not proof of success. Long typing and configured random mouse movement must not be labeled stuck using a universal five-second threshold.

## Verification scope

Offline regression tests cover all installed agent identities/reference sections/config schemas, `.flw` conversion, compiler branch/mapping integration, parser coverage, CRLF/empty fields, typed mappings, partial-mapping rejection, replay protection, monitoring semantics and failure exits. Existing desktop regressions exercise native input through mocks; the prior read-only Mouser inspection verified this machine's geometry without sending input. These tests do not claim live verification of all 89 agents, a multi-monitor hardware setup, Notepad editing, or PowerPoint automation.

Validation on 2026-09-15: 31 flow-knowledge tests, 38 desktop-input tests, 17 existing flow-contract/Parametrizer/Shoter tests and 17 migrated catalog-membership tests passed (103 focused tests). The broader 73-test run including build checks passed 72; its existing dependency audit still flags local PDF/LaTeX/PPTX helper imports and unlisted `fontTools`. These changes do not claim that release packaging is clean. Ruff, JavaScript syntax/mode checks and the generated-catalog freshness check passed. The flow tests include a repaired model response producing real `.flw`/canvas files with model calls mocked; no live LLM or desktop interaction is claimed by that test.
