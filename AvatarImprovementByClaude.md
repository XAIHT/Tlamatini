# The Avatar — from a 150 ms metronome to a talking head

**Date:** 2026-09-11 · **Baseline:** v1.51.5 · **Author of Tlamatini:** Angela López Mendoza
**Result:** 74 / 74 visible checks passed · her face unchanged · no GPU · no language model

---

## 0. What Angela asked for

Verbatim, because every decision below traces back to one of these lines.

> *"CHECK THE WRONG FUCKING IMPLEMENTATION OF THE AVATAR IN TLAMATINI IT LOOKS I THINK LIKE A
> STUPID ELEMENTARY SCHOOL AVATAR … make Tlamatini our image girl look fluid realistic speaking
> in the chat … this application is gonna be used by the PRESIDENT OF UNITED STATES OF MEXICO"*

Then, after the first design was read:

> *"We can't count in the fact that for the first demos they will use a computer with GPU … so we
> cant count in the LLM generates the audio! please remake the design to be the best able with a
> machine with no GPU and no LLM generated audio"*

Then the four rulings that shaped the build:

1. **"She is the official avatar the face should not be changed at all!"**
2. **"the image(s) of her must be sizeable from 120px as the minimum … you decide."**
3. **"Make the avatar to be animated even if the accessibility setting for animation were
   disabled, 'cause this is not an accessibility feature this is a normal broad behavior!"**
4. **"Make a powerful strong and vast automated tests visually for me (not headless!!), and make
   the automated tests scripts permanent/persistent!"**

And finally, mid-run, watching the first visible test on her own desktop:

5. **"the complete image of her moves in offset that look uncomfortable, weird!, make her image do
   not displace inside the little frame!"**

---

## 1. What was actually wrong

The audit was performed **read-only**, with Tlamatini's own Globber, Grepper and
Image-Interpreter agents. Every number here was measured, not estimated.

### F-01 · The lip sync was a metronome. It had never listened to the audio.

`agent/static/agent/js/avatar.js:310-315`, before:

```js
setInterval(function(){
  sp = speechSynthesis.speaking && !speechSynthesis.paused;
  if (sp) { stt.mouthOpen = !stt.mouthOpen; render(); }
}, 150);
```

That was the entire lip-sync engine. A timer flipped the mouth open and shut every 150 ms for as
long as the browser reported that *something* was being spoken. It never opened an audio buffer,
never measured amplitude, never saw a phoneme.

**The cruel part is that the rate was almost right.** 150 ms gives 6.67 mouth movements per
second; conversational Spanish runs about 5-7 syllables per second. So it looked vaguely like
speech and was wrong at every single instant — closed on open vowels, open on the `/m/` in
"Tlamatini". *A jaw that is correct on average and wrong on every frame is precisely what an
audience reads as a puppet.*

### F-02 · There were four frames in total

```
eo_mc.jpg   eyes open   · mouth closed
ec_mc.jpg   eyes closed · mouth closed
eo_mo.jpg   eyes open   · mouth OPEN
ec_mo.jpg   eyes closed · mouth OPEN
                          ── 2 × 2 = 4 states ──
```

Animators have used nine mouth shapes since the Preston Blair charts of 1947; the Disney
convention uses twelve; the Meta/Oculus real-time set uses fifteen. Tlamatini had **two**. So
`/m/ /b/ /p/`, `/f/ /v/`, `/o/ /u/` and `/a/` all rendered as the same picture.

### F-03 · The face was synchronised to the wrong voice entirely

The avatar watched `window.speechSynthesis` — the browser's built-in text-to-speech. Tlamatini's
*real* voice is the **Talker** agent: Orpheus-3b through Ollama, SNAC-decoded to a 24 kHz WAV.
Two different voices, two engines, two clocks, no channel between them. **The face had literally
never heard Tlamatini's good voice.** On a single desktop they come out of the same speakers,
which is why nobody noticed.

### F-04 · The artwork is generative stock, in the wrong genre

Not an opinion — the file was put through Tlamatini's **own** Image-Interpreter agent (Qwen3.5 ∥
Gemma 4, merged by GLM-5.3, run `image_interpreter__1789083524_6`). It returned, unprompted:

> *"AMATEUR / FAN-ART GRADE. […] it screams 'Cyberpunk Girl Asset' rather than 'Bespoke Brand
> Identity.'"*

Its specifics: violet contact-lens irises, cyan-and-magenta split lighting (*"the most overused
trope in AI art"*), no pore structure at all, generic white blob catchlights, JPEG banding in the
background gradient, glowing tactical armour. It also caught the mismatch that matters most:
**Tlamatini means "one who knows"**, and the picture is a science-fiction combatant.

**⚠️ NOTHING WAS DONE ABOUT F-04, BY INSTRUCTION.** Angela: *"She is the official avatar the face
should not be changed at all!"* The finding is recorded here for the record only. Every
improvement below was built from the four existing JPGs, untouched.

### F-05 · She does not speak Spanish

`agent/agents/talker/talker.py:353`

```python
_FEMALE_VOICES = ("tara", "leah", "jess", "mia", "zoe")
#                  └─ every one an ENGLISH voice; Orpheus's base model is English-only
```

The principal is the President of Mexico. **Still open** — see §8.

---

## 2. The architecture that replaced it

New file: **`agent/static/agent/js/avatar_presence.js`**. A 2-D canvas compositor. No GPU, no
WebGL, no language model, no new artwork, no new dependency.

### (a) The booleans became continuous

Eyes and mouth stopped being on/off. `eye` and `mouth` are real numbers in `[0,1]`, and every
frame is a convex blend of the four portraits:

```
w(eo_mc) = eye·(1-mouth)      w(eo_mo) = eye·mouth
w(ec_mc) = (1-eye)·(1-mouth)  w(ec_mo) = (1-eye)·mouth
```

Four corner images therefore span a **continuous 2-D surface**. A blink became a shaped curve
(55 ms close, 25 ms hold, 130 ms smoothstep open — fast close, slow open, the way a real lid
moves) instead of a 190 ms hard cut. The jaw moves smoothly instead of snapping. *Nothing was
redrawn; the in-between frames were always implied by the corners.*

The blend is sequential and self-normalising, so it is exact for any number of layers:

```js
acc = 0;
for each layer with weight w > 0.004:
    acc += w;  ctx.globalAlpha = w / acc;  ctx.drawImage(layer, …);
```

### (b) The mouth follows the TEXT, not a timer

`speechSynthesis` audio **cannot** be routed into an `AnalyserNode` — the amplitude is genuinely
unavailable to a web page. But the engine fires `boundary` events carrying `charIndex` and
`elapsedTime`: **it tells us where in the sentence it currently is.**

So the engine precomputes an openness value per character (vowels wide, `/m/ /b/ /p/` sealed,
punctuation closed), advances a cursor through that track at the measured speaking rate, and
**re-anchors on every boundary event**. Between anchors it interpolates; at each anchor it snaps
back to ground truth. A ±1-character weighted window (0.25 / 0.5 / 0.25) *is* co-articulation —
a shape bent by its neighbours — and an attack/release envelope (45 ms / 90 ms) keeps the jaw
from ever snapping.

Spanish helps here: five pure vowels against English's twelve-plus, and syllable-timed rather
than stress-timed, so viseme durations are far more regular.

**Fallbacks, in order:** real `boundary` events → a rate estimated from `elapsedTime` (`driver:
'estimated'`) → the legacy `<img>` path if the canvas cannot start at all.

### (c) Why it is cheap on a CPU

The four portraits are **pre-scaled once** into small offscreen canvases at the exact display
size, with a high-quality downscale paid only on a size change. Per frame the engine then blits
at 1:1. **An idle frame costs exactly ONE `drawImage`** — the weights collapse to a single corner
whenever the eyes are open and the mouth is shut, which is most of the time. A blink or a
syllable costs two; only the corners cost four.

Measured: **0.2 ms per composited frame.**

A governor holds a rolling median of frame costs across 60 frames: it promotes **once** (30 → 60
fps) if the machine is clearly fast, and demotes (60 → 30 → 20 → 12) whenever it is not. It never
oscillates.

---

## 3. ⚠️ The ruling that changed the design mid-flight — SHE DOES NOT MOVE IN THE FRAME

The first build added what every "living portrait" adds: breath (a centred scale at ~14/min),
a two-harmonic sway, a 0.0035 rad rotation, and sub-pixel micro-saccades — all applied to the
**whole portrait** as a canvas transform, with a 4.5 % overscan to stop the dock background
showing at the edges.

Angela watched the first visible run and ruled on it immediately:

> *"the complete image of her moves in offset that look uncomfortable, weird!, make her image do
> not displace inside the little frame!"*

**She was right, and it is worth writing down why.** At 120 px inside a bordered dock, a drifting
portrait does not read as a living person — it reads as a *loose photograph*. The dock frame is a
fixed reference the eye locks onto, so any movement of the whole image is perceived as the
picture sliding, not as the subject breathing. The technique is borrowed from full-bleed
cinematics where there is no visible frame to betray it.

**All whole-image motion was deleted**, and the overscan with it (`BLEED = 1.0`), so her portrait
now sits pixel-for-pixel exactly where the original `<img>` sat. **Only her eyelids and her jaw
move.**

This is pinned by check **B3**, which is deliberately inverted from what you would expect: while
nothing about her face is changing (`eye >= 0.999 && mouth <= 0.001`), consecutive frames must be
**pixel-identical**. Measured: **100 % of 188 quiet frames** (normal) and **100 % of 550 quiet
frames** (reduced-motion). Any reintroduced breath, sway or jitter collapses that number
immediately.

---

## 4. Sizing — 120 px floor, resizable, persistent

New file: **`agent/static/agent/js/avatar_size.js`**.

| | |
|---|---|
| **Docked** (default, untouched) | Exactly today's layout. A user who never touches the handle sees **no difference at all** — the feature is opt-in, so it cannot regress anybody. |
| **Floating** | The moment she is resized she becomes `position: fixed`, anchored bottom-right, at an explicit square size. She grows **up and left**, over the page, so she can reach presentation size without fighting the chat for room. |

* Drag the handle (top-left — the corner that moves when she grows, since she is anchored
  bottom-right), **or** arrow keys ±20 px, **or** double-click to cycle **160 → 240 → 360 → 520 →
  docked**.
* **120 px is a FLOOR, not a default.** Asking for 50 px returns 120 px. Measured in the test.
* The size is remembered in `localStorage` and restored on the next visit (measured: 240 px
  restored after a reload).
* The handle swallows its own clicks, so resizing her never triggers the dock's greet/mute.

---

## 5. ⚠️ `prefers-reduced-motion` is deliberately NOT honoured

Angela: *"this is not an accessibility feature this is a normal broad behavior!"*

The old code gated blinking **and** the mouth on that media query. **The gate is gone by
instruction.** She blinks, and she speaks, on every machine.

This is the kind of rule a later "accessibility cleanup" silently reverts, so **the entire
74-check suite is run a second time with `reduced_motion="reduce"` emulated** and asserts she is
still animating (checks C1 / C2). Do not put the gate back without asking her.

---

## 6. The tests — visible, vast, permanent

**`Tests/test_avatar_presence_visible.py`** (74 checks) + **`Tests/run_presence_tests.ps1`**,
wired into the existing runner as `Tests/run_avatar_tests.py --presence` / `--presence-only`.

```bash
powershell -ExecutionPolicy Bypass -File Tests\run_presence_tests.ps1
```

* **Headless is refused outright** — `--headless` exits 2 with an explanation. Chrome opens
  headed, on Angela's real desktop.
* **Chrome runs with `--disable-gpu --disable-software-rasterizer --use-gl=swiftshader`**,
  because the target machine is the President's office PC.
* **Every screenshot is taken by Shoter**, Tlamatini's own agent, capturing the whole desktop.
  `PIL.ImageGrab` is never imported. 12 photos per run.
* **It never touches the real database.** It delegates to the existing isolated Django on port
  8001 with its own fixture DB and a `user/changeme` login.
* Output: a dark-themed `SUMMARY.html` + `results.json` under `Temp/avatar_presence/`.

### Why it is hard to fool

The defect this suite exists to prevent is not *"the avatar is missing"* — it is *"the avatar is
present and looks alive while being driven by a timer"*. A test that only checked the canvas
existed would have passed against the old metronome. So:

| Check | What it proves | Measured |
|---|---|---|
| **B3** | her portrait does not drift | **100 %** of quiet frames pixel-identical |
| **D1** | she blinks on a human schedule | 3 blinks / 14 s |
| **D2** | the blink is CONTINUOUS, not a cut | 102 intermediate eyelid values |
| **D3** | the canvas really repaints when she blinks | 121 distinct frames / 14 s |
| **E2/E3** | the mouth really opens and really closes | peak 0.593, floor 0.000 |
| **E4** | the mouth is continuous — *a metronome yields 2* | **202 distinct mouth values** |
| **E5** | **the mouth follows the TEXT** | **Pearson r = 0.835** against the phonetic track |
| **E8** | the canvas really repaints while speaking | 132 distinct frames |
| **C1/C2** | she animates under reduced-motion | 98 frames, 58 fps |
| **F2** | the 120 px floor holds | asked 50 px, got 120 px |
| **F4/F5** | she re-scales, not stretches | 106 → 346 px, backing store grows |
| **F9** | her size survives a reload | restored 240 px |
| **G1** | a frame costs almost nothing | **0.2 ms** |
| **G2** | **she survives a 6× slower CPU** | **57 fps**, GPU disabled |
| **H1** | no uncaught JavaScript errors | clean |

The correlation check (E5) samples the mouth **inside the page on `requestAnimationFrame`** —
polling from Python over the CDP wire would alias against a 60 fps animation and could not prove
continuity. The pixel checks hash a 16×16 patch of real `getImageData` output.

### The suite caught two real bugs on its first run

1. **`Maximum call stack size exceeded`** — `avatar_size.js::apply()` ended by dispatching a
   synthetic `resize`, and the window `resize` handler called `apply()`. They called each other
   forever. Fixed with a re-entrancy guard (`applying`). *Neither eslint nor a static reading
   would ever have found this.*
2. **The lip sync was being killed within 250 ms** — the `speechWatch` poll cancels speech when
   `speechSynthesis.speaking` goes false, and a *simulated* utterance has no engine behind it, so
   `ss.speaking` was false for the whole run. Measured symptom: mouth peak **0.034**, correlation
   **r = −0.161**. Fixed by skipping the watchdog when `driver === 'simulated'`. After the fix:
   peak **0.593**, **r = 0.835**.

A third defect was found in the test itself: it produced an **empty report** when the suite
aborted before the first check. A permanent regression that cannot say what went wrong is
indistinguishable from one nobody ran — so `login_and_open()` now names the exact failure, and
each suite is wrapped so an abort is recorded as a `SUITE ABORTED` row.

---

## 7. Files

**Added**

| File | Role |
|---|---|
| `Tlamatini/agent/static/agent/js/avatar_presence.js` | the compositor: continuous blend, boundary-driven lip sync, blink, governor |
| `Tlamatini/agent/static/agent/js/avatar_size.js` | resize handle, presets, persistence, the 120 px floor |
| `Tests/test_avatar_presence_visible.py` | the 74-check visible regression |
| `Tests/run_presence_tests.ps1` | one-command visible launcher |
| `AvatarImprovementByClaude.md` | this record |

**Changed**

| File | Change |
|---|---|
| `Tlamatini/agent/static/agent/js/avatar.js` | metronome + reduced-motion gate removed; delegates to the engine; keeps the `<img>` path as the fallback |
| `Tlamatini/agent/static/agent/css/avatar.css` | canvas, resize handle, floating mode |
| `Tlamatini/agent/templates/agent/agent_page.html` | two new `<script>` tags |
| `Tests/run_avatar_tests.py` | `--presence` / `--presence-only` |

Both new JS files are self-contained IIFEs declaring **no cross-file globals** (the
`chat_image_paste.js` / `welcome_enter_default.js` shape). `npm run lint` → **0 errors**, 40 JS
files parse cleanly; `ruff check` → clean. `STATIC_VERSION` needs no bump — it is derived from
`time.time()` in `settings.py`.

---

## 8. Contracts — do NOT revert

1. **HER FACE NEVER CHANGES.** No new artwork. Everything is composited from the four existing
   JPGs. F-04 above is recorded for information only.
2. **NO WHOLE-IMAGE TRANSFORM.** No breath, no sway, no rotation, no saccades, no overscan. Only
   the eyelids and the jaw move. Pinned by **B3** at 100 %.
3. **NO `prefers-reduced-motion` GATE.** She animates everywhere. Pinned by **C1 / C2**.
4. **NO GPU, EVER, AT RUNTIME.** 2-D canvas only. The test runs Chrome with the GPU disabled on
   purpose; do not "optimise" this into WebGL.
5. **NO LANGUAGE MODEL IN THE SPEAKING PATH.** The mouth is driven by the browser's own speech
   engine. Orpheus is welcome offline and forbidden on the critical path.
6. **DECODE AND PRE-SCALE ONCE**, never inside the animation loop. A decode during playback is a
   10-30 ms stall, which at 60 fps is two dropped frames, which on a face reads as a twitch.
7. **THE `<img>` STACK STAYS IN THE DOM.** It is both the fallback face and the decode source the
   engine pre-scales from. `_presenceLive()` is checked live on every legacy tick, so the old
   path stands down by itself the moment the canvas takes over.
8. **FAIL-OPEN EVERYWHERE.** No canvas, no dock, a portrait that will not decode, a
   `localStorage` that throws — every one of them leaves the avatar exactly as it was. Nothing in
   the presence layer may raise into the chat.
9. **THE TEST IS NEVER HEADLESS AND NEVER USES PILLOW.** Both are refused in code, not by
   convention.

---

## 9. Honest limits — what was NOT done

* **She still speaks English (F-05).** This is the one finding that outranks everything above and
  it is **untouched**: it needs a Mexican-Spanish CPU-only voice in Talker (Piper, MIT, ~60 MB,
  `es_MX`; or Kokoro, Apache-2.0) behind the existing female-voice allow-list. Nothing in this
  pass addresses it.
* **Fifteen visemes were not possible.** With four source images the mouth is a single
  open/closed axis, so `/o/` and `/a/` share a shape. The phonetic track still drives *how far*
  the jaw opens per character, which is what produces the 0.835 correlation — but true viseme
  shapes would need artwork, and the artwork is frozen by instruction.
* **Windows SAPI 5 emits its own viseme stream** and would give frame-exact timing without any
  phonetic guessing. Not wired up: it needs a server-side change in Talker, which was out of
  scope for a face-only pass.
* **`.claude/skills/tlamatini-daily-chat-test/harness/shoter_shot.py` has a stale hardcoded
  `TEMPLATE`** pointing at `C:\Development\Tlamatini\…`, which is not where this repository
  lives. The new test re-points it at run time rather than editing shared harness state. Worth
  fixing at the source.

---

*Prepared for **Angela López Mendoza**, creator of Tlamatini. Every measurement in this document
came from a run on her own machine, in a visible browser, photographed by her own agent.*
