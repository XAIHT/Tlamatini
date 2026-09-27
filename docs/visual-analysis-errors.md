# Image and video failures, dialogs and recovery

Created by Angela López Mendoza · @angelahack1 — Tlamatini.

Image/video analysis uses the configured model identities. A failed observer,
merger, malformed response, incomplete stream or empty answer is an error. A
single surviving observer, concatenated raw answers, speech-only replacement for
a requested visual summary, and fabricated confidence are not successful results.
Configuration inheritance (`"@config"`) resolves the user's selected models before
execution; it is not permission to switch models after a failure.

**Fatal describes the failed analysis attempt. It never shuts down Tlamatini,
cancels its run, disables its retry engine, or replaces its recovery tactics.**
The existing self-healing watchdog, tactic ladder, user cancellation and tool
self-correction remain active. Recovery may retry the configured models and repair
the request or environment. The existing CUDA-to-CPU transcription tactic retains
the same Whisper model; a device retry never accepts the failed transcript. Video
sampling may recover a nearby decodable frame with its actual timestamp, but cannot
silently omit an unrecoverable sample. Model changes require the user's choice.

## Accumulated visible errors

Chat and Agentic Control Panel share one non-modal **Fatal analysis errors** dialog.
Each failed attempt adds an entry and updates the count. The dialog uses the shared
Tlamatini theme, a titlebar X, a separate Dismiss button and the existing notification
sound/taskbar attention request. Error text is rendered as text, never executable
HTML. The list scrolls; it does not cover the desktop as it grows.

Dismiss hides the dialog without deleting its history or cancelling work. Repeated
polls do not duplicate entries or reopen dismissed errors. A new failure reopens
the accumulated list. Background controls and recovery remain usable while it is
open. Sound depends on browser playback permission; the visible dialog remains.

Standalone image/video runtimes publish uniquely identified events in their
existing `notification.json` channel. Fatal events remain available across polls;
ordinary Notifier events keep their existing consume-once behavior. Runtime
deployment refreshes `visual_errors.py` alongside the model resolver. Direct image
tools use a per-request event sink and the `visual-analysis-error` WebSocket event.
The reporting layer does not control retries or cancellation.

Release asset mappings require the portable helper and this guide; self-modify
snapshots require both reporting modules, their regression coverage and the visible
browser harness. The prompt catalog's forward migration `0210` updates only known
obsolete result descriptions, preserving custom surrounding text, IDs and ordering.
Historical migrations remain unchanged.

PDF image preparation reports failures in the same accumulated dialog. Its native
progress modal closes on failure so it cannot hide the shared dialog in the browser
top layer. Incomplete PDF visual context is not loaded; the rest of Tlamatini remains
available. Choosing text-only processing before starting a PDF job is a user choice,
not an automatic fallback after image analysis fails.

## Results and flow routing

Image success is `merged`; a complete video summary is `analyzed`. Legitimate
robotics findings (`FAIL_NO_MOTION`, `FAIL_WRONG_MOTION`, `UNCLEAR`), no audio tracks
and no detected speech remain supported. Missing model evidence is not a robotics
finding. Legacy `partial_interpreter_*` and `merge_fallback_concat` results are
classified as incomplete work, never green success.

A failed standalone attempt emits an error section and returns a nonzero exit code.
Configured downstream routes still run, allowing Forker/Raiser/recovery flows to
handle the explicit error. The wrapped chat tool remains retryable. Consumers must
check `status`/`agent_status` before using an interpretation; diagnostic error text
is not an analysis report.

## Verification

All commands and tests must run in a verified visible foreground console, left open
afterward. Browser tests explicitly use `headless=False`; hidden execution is
forbidden. Follow [the visible execution policy](../TestsVisiblesAndVisibleExecutionFromClaude2Codex.md).

Run the image/video, PDF, fatal-dialog delivery, status vocabulary, model selection,
self-healing, tool recovery, cancellation, dialog theme/dismissal, flow contract and
context-governor suites together. `scripts/visual_fatal_dialog_visible.py` exercises
the actual shared renderer/poller and both panel styles in visible Chrome; Shoter
captures the desktop. Provider responses are controlled in these regressions, so
they verify error/recovery behavior rather than live model availability or accuracy.

### Verified on 2026-09-27

| Visible run | Result |
|---|---|
| Image/video, PDF backend, fatal delivery, self-healing, tool recovery, cancellation, verdicts, model settings, flow contracts, dialogs and context governor | 418 tests passed; no skips |
| Prompt catalog, including all migrations in an isolated in-memory test database | 15 tests passed |
| Complete PDF canvas browser suite in visible Chrome | 11 tests passed |
| Shared dialog renderer/poller in chat and ACP styles, including X, Dismiss, Escape, accumulation and continuing work | 60 browser checks passed |

This is **444 passing automated tests plus 60 browser checks**. Shoter captured
both dialog styles and the images were inspected. Static collection refreshed 540
assets; the changed served dialog assets match source. Catalog generation/check
covered all 89 agent types.

The repository-wide inventory covered 240 test/harness-related files and 63
visual-related documentation files; all 219 Python files in that test inventory
parsed successfully. This is a static audit of the broader suite, not a claim that
every repository test was executed. Historical validation entries remain dated
and explicitly identify superseded partial-result behavior.

The live application database was not migrated during verification. The catalog
update was tested through Django's isolated test database and follows the normal
application migration lifecycle. No live-provider inference accuracy, frozen
executable rebuild, or installed-app restart is claimed by these checks.
