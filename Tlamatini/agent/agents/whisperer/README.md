<!--
Tlamatini — Created by Angela López Mendoza · @angelahack1
Tlamatini Author Banner — do not remove
-->
# Whisperer: workflow speech recognition and direct chat dictation

Whisperer records the configured host microphone or transcribes audio files.
The local engine is faster-whisper with the existing GPU/CPU fallback; explicitly
configured cloud engines are also supported. Model choices inherit from
Config → Models → Speech through `@config`, unless this template overrides them.

## Choose the entry point

| Entry point | Behavior |
| --- | --- |
| Chat microphone beside Send | Direct resident `chat_worker.py`; no model decision before capture; real status in chat; silence gate → recognition → automatic normal-form submission or editable draft (Config → Mic) |
| Wrapped `chat_agent_whisperer` / VOICE COMMANDS catalog | Model-mediated workflow invocation with the card's selected modes and instructions |
| Canvas/standalone `whisperer.py` | Existing configured agent lifecycle: microphone/file input, transcript/audio outputs, structured result and downstream targets |

The direct button uses the **Tlamatini host microphone**, including from a remote
browser. It does not create another console or move focus. Its diagnostics flow
through the main app logger. It appends recognized words to the existing draft
and either sends with the current options or leaves it editable for manual Send.
Choose the behavior in Config → Mic, the last Config entry; the button label is Mic. Click again or press
Escape to cancel. Empty audio, errors and cancelled/stale results do not send.

## Shared gate and direct-worker overrides

No duration (`record_seconds: 0`) means gated capture in the standalone agent;
a positive duration requests fixed capture. `silence_gate` can override that
inference. The shipped silence window is 3.5 seconds and the bounded recording
ceiling is 300 seconds. Existing template values remain configurable.

For direct dictation only, the worker forces `input_source: mic`,
`record_seconds: 0`, `silence_gate: on`, `ollama_cleanup: false` and
`target_agents: []`. It refuses the ungated recording fallback. The existing
device, gain, language, recognition and gate settings apply unless a validated
Config → Mic preference overrides that capture/decoding field for the job.
Engine/model credentials remain in Config → Models or the template.

Capture progress is reported outside the audio callback. The local model warms
after first samples and stays cached for later jobs. Cancellation stops capture;
a native recognition/warmup call may finish before the job is released, but its
cancelled result is discarded. The microphone is never opened simply because
the worker was prepared.

## Outputs, diagnostics and verification

Standalone/workflow output contracts and `INI_SECTION_WHISPERER` remain in
`whisperer.py`. The direct worker returns text to the composer and does not
produce those workflow deliverables or an Exec Report tool row. A cloud engine
uses a temporary WAV and attempts cleanup when the job finishes.

The direct worker requires source/carried Python, `numpy`, `sounddevice`
and its configured recognition engine. `agent.chat_voice_runtime` forwards
stdout/stderr into the main Tlamatini console/log. Windows uses a windowless
child process; developer tests still run in a verified visible console.

Read the [complete direct microphone guide](../../../../docs/chat-microphone-design.md)
for the protocol, deployment files, troubleshooting, measurements and limits.
Regression source: `agent/test_whisperer_agent.py` and
`agent/test_chat_voice.py`; browser fixture:
`scripts/chat_microphone_visible.py` (headed Chrome, controlled transport).

## Direct microphone preferences

Config → Mic uses browser-local `tlm_mic_settings_v1`; only capture overrides and
the send/draft choice are stored. Input device/refresh, gain 0–300%, silence
0.3–20 s, cap 5–600 s, automatic/manual threshold, language, English translation,
sample rate, channels, local beam and VAD are available. The shared validator
`chat_voice_settings.py` rejects unsupported keys/types/ranges. Explicit hardware
selection includes name and host API so an index change cannot silently choose
a different input. Opening or refreshing settings enumerates devices only.

Preferences are snapshotted per recording; next-recording edits cannot change
an active run's send/draft behavior. Unset fields inherit the current template;
Reset then Save restores inheritance. Automatic mode remains the default.
Review mode triggers neither a model task nor avatar processing speech before
manual Send. Workflow/standalone configuration and result contracts are unchanged.
