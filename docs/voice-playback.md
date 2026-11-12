<!-- Tlamatini Author Banner — Created by Angela López Mendoza · @angelahack1 -->
# Voice playback and browser handoff

> Latest released version: **[v1.93.5](changes/2026-11-12-v1.93.5.md)**.

Choose **Config → Voice** to read answers aloud, announce completion, or remain
silent. Covering, minimizing or unfocusing the browser does not deliberately
pause speech. The shared queue is used by chat and editor/terminal narration.

If the browser cannot begin or finish a speech chunk, it retries that chunk and
can hand the remaining text to Windows speech on the computer running Tlamatini.
Closing or reloading a page during ordinary chat speech also attempts that
handoff. If an answer finishes with no chat page open for the account, the host
reads the answer or announces completion according to the account's last
reported voice mode. Tlamatini must still be running.

## Controls and requirements

- **Silent**, zero volume and microphone listening suppress speech. Escape
  stops speech unless a dialog consumed Escape to close itself. The avatar and
  cancellation controls retain their stop behavior. Ctrl+Shift+M toggles mute.
- The browser reports its voice, language, rate, pitch and volume to the host.
  Host settings and speech jobs belong to the signed-in account. Host requests
  require the normal authenticated, CSRF-protected application routes.
- Host playback uses Windows System.Speech and the host computer's audio device,
  not a remote browser's speakers. It needs an enabled female Windows voice.
  The English edition may use another installed female voice if no language
  match is available; the Spanish edition requires the Spanish language.
  An unavailable compatible voice leaves playback unavailable.
- The host helper is internal and creates no extra console. Its diagnostics go
  to the application's existing log. Voice settings and jobs are kept in
  process memory; they do not survive an application restart.
- Host messages are limited to 20,000 characters. A failed or interrupted chunk
  can repeat because the browser cannot prove which words the engine already
  pronounced. Page closure handoff is best effort; it is not an audio delivery
  guarantee during browser crashes, network loss or application shutdown.

## Interaction narration

Editor and terminal narration use the same queue, user mute and stop controls.
They retain their action cancellation, tab ownership and before-typing receipt
requirements. Page closure does **not** hand interaction narration over as an
independent chat message. Mute or microphone listening skips narration; explicit cancellation stops the
step. An unavailable voice offers Continue without voice or Stop. See
[Live Editor and Terminater settings](interaction-settings.md).

## Implementation and verification

`static/agent/js/voice_runtime.js` owns the shared browser queue and recovery;
`host_voice.py` owns account speech jobs and the Windows worker;
`host_voice_views.py` serves settings, speak, status and stop. The worker queues
messages and invokes its owned PowerShell child without a shell or visible
console. Spanish spoken-name aliases are applied before speech.

From a verified visible foreground development console, the focused checks are:

```powershell
# From the repository root:
node scripts/voice_runtime_cases.mjs
# From this edition's Tlamatini Django directory:
python manage.py test agent.test_host_voice
```

The browser cases use a controlled speech engine to exercise recovery, queue
order, host handoff and cancellation. Python cases cover account isolation,
settings, host lifecycle and route protections. These checks do not prove
audible delivery on every device. The real-browser harness is
`.claude/skills/tlamatini-daily-chat-test/harness/voice_unstoppable_visible.py`;
run it with a real configured voice and inspect its desktop evidence.
