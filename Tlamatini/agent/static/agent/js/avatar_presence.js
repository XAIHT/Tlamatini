// ═══════════════════════════════════════════════════════════════════
//   ✦  T L A M A T I N I  ✦   —   "one who knows"
//
//   Created by  Angela López Mendoza   ·   @angelahack1
//   Developer · Architect · Creator of Tlamatini
// ═══════════════════════════════════════════════════════════════════
//   Tlamatini Author Banner — do not remove
//
// PRESENCE ENGINE — the talking head, composited on a 2D canvas.
// ─────────────────────────────────────────────────────────────────────────
// WHAT THIS REPLACES
//   `avatar.js` used to drive the face with TWO booleans and a metronome:
//
//       setInterval(function(){ if (speaking) mouthOpen = !mouthOpen; }, 150);
//
//   Six-and-two-thirds mouth flaps a second, forever, whatever the sentence.
//   The rate is roughly plausible — conversational Spanish runs 5-7 syllables
//   a second — which is exactly why it ALMOST worked and still read as a
//   puppet: the phase was random, so the mouth was closed on open vowels and
//   open on the /m/ in "Tlamatini". A jaw that is right on average and wrong
//   at every instant is what an audience reads as fake.
//
// THE CONSTRAINTS THIS IS BUILT TO (Angela, 2026-09-11)
//   1. HER FACE NEVER CHANGES. She is the official avatar. This engine adds
//      no artwork whatsoever — it composites the SAME four portraits that
//      already ship (eyes open/closed × mouth closed/open).
//   2. NO GPU, EVER. The target is the President's office PC: a good machine
//      with no graphics card. Everything here is 2D canvas `drawImage`.
//   3. NO LANGUAGE MODEL in the speaking path. The mouth is driven by the
//      browser's own speech engine, which reports where it is in the text.
//   4. SHE ANIMATES ALWAYS — see the `prefers-reduced-motion` note below.
//
// THE TWO IDEAS THAT MAKE FOUR STILLS LOOK ALIVE
//   ── (a) THE BOOLEANS BECOME CONTINUOUS ──
//   Eyes and mouth stop being on/off. `eye` and `mouth` are real numbers in
//   [0,1] and each frame is a convex blend of the four portraits:
//
//       w(eo_mc) = eye·(1-mouth)      w(eo_mo) = eye·mouth
//       w(ec_mc) = (1-eye)·(1-mouth)  w(ec_mo) = (1-eye)·mouth
//
//   Four corner images therefore span a continuous 2-D surface. A blink is a
//   shaped curve (fast close, slow open) instead of a 190 ms hard cut, and
//   the jaw moves smoothly instead of snapping. Nothing was redrawn; the
//   in-between frames were always implied by the corners.
//
//   ── (b) THE MOUTH FOLLOWS THE TEXT, NOT A TIMER ──
//   `speechSynthesis` audio cannot be routed into an AnalyserNode, so the
//   amplitude is genuinely unavailable to us. But the engine fires `boundary`
//   events carrying `charIndex` + `elapsedTime` — it TELLS US where in the
//   sentence it currently is. So we precompute an openness value per
//   character (vowels wide, /m/ /b/ /p/ sealed, punctuation closed) and
//   advance a cursor through that track at the measured speaking rate,
//   RE-ANCHORING on every boundary event. Between anchors we interpolate; at
//   each anchor we snap back to ground truth. That is real synchronisation
//   with the engine's own clock — not a guess, and not a metronome.
//
// PERFORMANCE — WHY THIS IS CHEAP ON A CPU
//   The four portraits are PRE-SCALED once into small offscreen canvases at
//   the exact display size (high-quality downscale, paid once per size
//   change). Per frame we then blit at 1:1. An idle frame costs exactly ONE
//   `drawImage` — the weights collapse to a single corner whenever the eyes
//   are fully open and the mouth is shut, which is most of the time. A blink
//   or a syllable costs two; only the corner cases cost four.
//
// ⚠️ `prefers-reduced-motion` IS DELIBERATELY NOT HONOURED HERE.
//   Angela, 2026-09-11, verbatim: "Make the avatar to be animated even if the
//   accessibility setting for animation were disabled, 'cause this is not an
//   accessibility feature this is a normal broad behavior!" A talking head
//   that does not move is not a talking head. The old code gated blinking and
//   the mouth on that media query; that gate is GONE by instruction. Do not
//   put it back without asking her.
//
// FAIL-OPEN, ALWAYS.
//   `start()` returns false — quietly — if there is no canvas support, no
//   dock, or a portrait that will not decode. `avatar.js` then keeps its
//   original <img> path and the user still sees her face. Nothing in this
//   file may raise into the chat.
(function () {
  'use strict';

  const KEYS = ['eo_mc', 'eo_mo', 'ec_mc', 'ec_mo'];
  const IMG_IDS = {
    eo_mc: 'tlm-s-eo-mc', eo_mo: 'tlm-s-eo-mo',
    ec_mc: 'tlm-s-ec-mc', ec_mo: 'tlm-s-ec-mo'
  };

  // ⚠️ NO BLEED, NO ZOOM. Her portrait is pre-scaled to EXACTLY the frame, so
  // it sits pixel-for-pixel where the original <img> sat. There used to be a
  // 4.5% overscan here to hide a breath/sway transform; both are gone (see
  // `compose`), so overscan would only crop her face for no reason.
  const BLEED = 1.0;
  const MIN_W = 0.004;           // a layer this faint is invisible — skip the blit

  // Motion constants. Everything is a real human figure, not a guess.
  //
  // ⚠️ THE WHOLE-IMAGE MOTION IS GONE — ON PURPOSE. This engine originally
  // added breath (a centred scale), a slow two-harmonic sway and micro-saccades
  // (sub-pixel translations) to the WHOLE portrait. Angela watched the first
  // visible run and ruled on it, 2026-09-11: "the complete image of her moves
  // in offset that look uncomfortable, weird!, make her image do not displace
  // inside the little frame!" She is right — at 120 px in a bordered dock, a
  // drifting portrait reads as a loose photograph, not as a person. Only her
  // EYES and her MOUTH move now. Do not reintroduce a whole-image transform.
  const BLINK_MIN = 2.4, BLINK_MAX = 5.2;   // s between blinks -> 12-20/min
  const BLINK_CLOSE = 55, BLINK_HOLD = 25, BLINK_OPEN = 130;  // ms, asymmetric
  const DOUBLE_BLINK = 0.12;
  const MOUTH_ATTACK = 45, MOUTH_RELEASE = 75;  // ms time constants

  // ── LIP VISIBILITY (Angela, 2026-09-29) ──
  // "make her see her move more her lips, but not so exagerated of course".
  // MEASURED before this change (Temp/lip_gain_lab/simulate_lips.py, the
  // engine re-run on the test phrase and an English one): the mouth PEAKED at
  // 0.59-0.71 and spent 85-89 % of speech as a half-transparent blend of the
  // closed and open portraits, with 0 % of the time clearly open. A ghost of a
  // mouth, not a moving one. Three changes, all bounded by her own artwork:
  //   1. Co-articulation is narrower (0.18/0.64/0.18, was 0.25/0.50/0.25) so a
  //      sealed /m/ /b/ /p/ between vowels actually dips instead of averaging
  //      away.
  //   2. The sampled openness is STRETCHED from [LIP_FLOOR, LIP_CEIL] onto
  //      [0, 1] through a smoothstep, so the jaw commits to open or shut and
  //      spends less time as a double exposure.
  //   3. Release is 75 ms (was 90) so the lips close between syllables.
  // Result: peak 0.89-0.94, 2.6x more lip travel per second, about 3x more
  // visible open-close cycles, clearly open 12-14 % of the time, and the mean
  // opening barely moved (0.39 -> 0.45) — she moves more, she does not gape.
  // ⚠️ NOT EXAGGERATED BY CONSTRUCTION: the ceiling is her own open-mouth
  // portrait. Nothing here can open her mouth wider than the artwork does.
  const COART_SIDE = 0.18, COART_CENTRE = 0.64;
  const LIP_FLOOR = 0.14, LIP_CEIL = 0.70;

  // Frame budget governor. Start conservative; promote ONCE if the machine is
  // clearly fast; demote whenever it is not. Never oscillate.
  const TIERS = [12, 20, 30, 60];
  const START_TIER = 2;          // 30 fps
  const PROMOTE_AFTER = 90;      // frames
  const PROMOTE_UNDER_MS = 1.5;
  const DEMOTE_OVER_RATIO = 0.55;   // of the frame budget
  const DEMOTE_SUSTAIN_MS = 2000;

  // Per-character mouth openness. Spanish has five pure vowels and is
  // syllable-timed, which is why it lip-syncs more cleanly than English.
  const OPEN = {
    'a': 1.00, 'á': 1.00, 'à': 1.00, 'ä': 1.00, 'â': 1.00,
    'e': 0.72, 'é': 0.74, 'è': 0.72, 'ë': 0.72, 'ê': 0.72,
    'o': 0.85, 'ó': 0.87, 'ò': 0.85, 'ö': 0.85, 'ô': 0.85,
    'i': 0.42, 'í': 0.44, 'ì': 0.42, 'ï': 0.42, 'y': 0.40,
    'u': 0.38, 'ú': 0.40, 'ù': 0.38, 'ü': 0.38,
    'm': 0.02, 'b': 0.04, 'p': 0.03,          // lips sealed
    'f': 0.14, 'v': 0.15,                      // lip to teeth
    'w': 0.30, 'q': 0.30,
    ' ': 0.12, '\n': 0.05, '\t': 0.10,
    ',': 0.08, ';': 0.08, ':': 0.08,
    '.': 0.00, '!': 0.00, '?': 0.00, '¡': 0.00, '¿': 0.00
  };
  const OPEN_DEFAULT = 0.30;     // ordinary consonant
  const CHARS_PER_SEC = 14.5;    // fallback rate when no boundary event arrives

  function openness(ch) {
    let v = OPEN[ch];
    if (v === undefined) { v = OPEN[ch.toLowerCase()]; }
    return v === undefined ? OPEN_DEFAULT : v;
  }

  function clamp(v, lo, hi) { return v < lo ? lo : (v > hi ? hi : v); }
  function now() {
    try { return performance.now(); } catch (e) { return Date.now(); }
  }

  // ── state ───────────────────────────────────────────────────────────────
  let dock = null, faceOuter = null, canvas = null, ctx = null;
  let layers = {};             // key -> pre-scaled offscreen canvas
  const srcImgs = {};
  let ready = false, running = false, rafId = 0;

  let eye = 1, mouth = 0;
  let dispW = 0, dispH = 0, dpr = 1;

  let tier = START_TIER, frameCount = 0, promoted = false;
  const costs = [];
  let overSince = 0, lastFrameCost = 0, fpsEma = 0;
  let lastDraw = 0, lastTick = 0;

  let blinkAt = 0, blinkPhase = null, blinkCount = 0;

  let speaking = false, track = null, trackLen = 0;
  let anchorChar = 0, anchorT = 0, rate = CHARS_PER_SEC / 1000, rateKnown = false;
  let boundaryCount = 0, driver = 'idle', speechStart = 0;

  let onTierChange = null;

  // ── asset preparation ───────────────────────────────────────────────────
  function collectImages() {
    let ok = true;
    KEYS.forEach(function (k) {
      const el = document.getElementById(IMG_IDS[k]);
      if (!el || !el.complete || !el.naturalWidth) { ok = false; }
      srcImgs[k] = el;
    });
    return ok;
  }

  // Pre-scale every portrait to the display size ONCE. This is the whole
  // performance story: the expensive high-quality downscale happens on a size
  // change, never inside the animation loop.
  function prescale(w, h) {
    if (w <= 0 || h <= 0) { return false; }
    const bw = Math.max(2, Math.round(w * BLEED));
    const bh = Math.max(2, Math.round(h * BLEED));
    const made = {};
    for (let i = 0; i < KEYS.length; i++) {
      const k = KEYS[i], img = srcImgs[k];
      if (!img || !img.naturalWidth) { return false; }
      const c = document.createElement('canvas');
      c.width = Math.round(bw * dpr);
      c.height = Math.round(bh * dpr);
      const g = c.getContext('2d');
      if (!g) { return false; }
      g.imageSmoothingEnabled = true;
      try { g.imageSmoothingQuality = 'high'; } catch (e) { /* older engines */ }
      // object-fit: cover — the portraits are square-ish, but never assume.
      const sr = img.naturalWidth / img.naturalHeight, dr = bw / bh;
      let sx = 0, sy = 0, sw = img.naturalWidth, sh = img.naturalHeight;
      if (sr > dr) { sw = img.naturalHeight * dr; sx = (img.naturalWidth - sw) / 2; }
      else { sh = img.naturalWidth / dr; sy = (img.naturalHeight - sh) / 2; }
      g.drawImage(img, sx, sy, sw, sh, 0, 0, c.width, c.height);
      made[k] = c;
    }
    layers = made;
    return true;
  }

  function sizeCanvas() {
    if (!canvas || !faceOuter) { return false; }
    const w = Math.round(faceOuter.clientWidth || 0);
    const h = Math.round(faceOuter.clientHeight || 0);
    if (w <= 0 || h <= 0) { return false; }
    if (w === dispW && h === dispH && layers.eo_mc) { return true; }
    dpr = Math.min(2, window.devicePixelRatio || 1);
    dispW = w; dispH = h;
    canvas.width = Math.round(w * dpr);
    canvas.height = Math.round(h * dpr);
    canvas.style.width = w + 'px';
    canvas.style.height = h + 'px';
    return prescale(w, h);
  }

  // ── the composite ───────────────────────────────────────────────────────
  function compose() {
    if (!ctx || !layers.eo_mc) { return; }
    const e = clamp(eye, 0, 1), m = clamp(mouth, 0, 1);
    const w = {
      eo_mc: e * (1 - m), eo_mo: e * m,
      ec_mc: (1 - e) * (1 - m), ec_mo: (1 - e) * m
    };

    // ⚠️ NO TRANSFORM. The portrait is drawn at a FIXED position, every frame,
    // filling the frame exactly. Angela, 2026-09-11: "make her image do not
    // displace inside the little frame!" Everything that moves is INSIDE her
    // face — the eyelids and the jaw — because that is what a person does when
    // they hold your gaze and talk to you. A drifting photograph is not life,
    // it is a loose photograph. Do not add breath, sway, rotation or saccades
    // back into this function.
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, dispW, dispH);
    ctx.translate(dispW / 2, dispH / 2);

    const bw = dispW * BLEED, bh = dispH * BLEED;
    let acc = 0;
    for (let i = 0; i < KEYS.length; i++) {
      const k = KEYS[i], wt = w[k];
      if (wt < MIN_W) { continue; }
      acc += wt;
      ctx.globalAlpha = wt / acc;   // sequential convex blend
      ctx.drawImage(layers[k], -bw / 2, -bh / 2, bw, bh);
    }
    ctx.globalAlpha = 1;
    ctx.setTransform(1, 0, 0, 1, 0, 0);
  }

  // ── blink ───────────────────────────────────────────────────────────────
  function scheduleBlink(t, soon) {
    blinkAt = t + (soon ? 170 : (BLINK_MIN + Math.random() * (BLINK_MAX - BLINK_MIN)) * 1000);
  }

  function stepBlink(t) {
    if (blinkPhase === null) {
      if (t >= blinkAt) { blinkPhase = t; blinkCount++; }
      else { eye = 1; return; }
    }
    const d = t - blinkPhase;
    if (d < BLINK_CLOSE) { eye = 1 - (d / BLINK_CLOSE); }
    else if (d < BLINK_CLOSE + BLINK_HOLD) { eye = 0; }
    else if (d < BLINK_CLOSE + BLINK_HOLD + BLINK_OPEN) {
      const p = (d - BLINK_CLOSE - BLINK_HOLD) / BLINK_OPEN;
      eye = p * p * (3 - 2 * p);          // smoothstep: the lid eases open
    } else {
      eye = 1; blinkPhase = null;
      scheduleBlink(t, Math.random() < DOUBLE_BLINK);
    }
  }

  // ── lip sync ────────────────────────────────────────────────────────────
  function buildTrack(text) {
    const s = String(text || '');
    const a = new Float32Array(s.length || 1);
    for (let i = 0; i < s.length; i++) { a[i] = openness(s.charAt(i)); }
    return a;
  }

  function sampleTrack(pos) {
    if (!track || !trackLen) { return 0; }
    const i = clamp(Math.floor(pos), 0, trackLen - 1);
    // ±1 char window — this IS co-articulation: a shape is bent by its
    // neighbours, which is what stops the jaw flapping between syllables.
    const a = track[clamp(i - 1, 0, trackLen - 1)];
    const b = track[i];
    const c = track[clamp(i + 1, 0, trackLen - 1)];
    return (a * COART_SIDE + b * COART_CENTRE + c * COART_SIDE);
  }

  // Stretch [LIP_FLOOR, LIP_CEIL] onto [0, 1] and ease it, so the lips commit
  // to a shape instead of hovering as a half-blend. Monotonic, so the mouth
  // still follows the text exactly as before, just with more contrast.
  function lipShape(v) {
    const x = clamp((v - LIP_FLOOR) / (LIP_CEIL - LIP_FLOOR), 0, 1);
    return x * x * (3 - 2 * x);
  }

  function stepMouth(t, dt) {
    let target = 0;
    if (speaking && track) {
      let pos = anchorChar + (t - anchorT) * rate;
      if (pos >= trackLen) { pos = trackLen - 1; }
      target = lipShape(sampleTrack(pos));
      // A sustained vowel is never perfectly still.
      target *= 0.93 + 0.07 * Math.sin(t / 47);
      if (!rateKnown && boundaryCount === 0 && (t - speechStart) > 600) {
        driver = 'estimated';
      }
    }
    const tau = target > mouth ? MOUTH_ATTACK : MOUTH_RELEASE;
    mouth += (target - mouth) * (1 - Math.exp(-dt / tau));
    if (mouth < 0.002) { mouth = 0; }
  }

  // ── governor ────────────────────────────────────────────────────────────
  function budgetMs() { return 1000 / TIERS[tier]; }

  function governor(t, cost) {
    costs.push(cost);
    if (costs.length > 60) { costs.shift(); }
    frameCount++;
    lastFrameCost = cost;

    if (!promoted && frameCount === PROMOTE_AFTER) {
      promoted = true;
      const sorted = costs.slice().sort(function (a, b) { return a - b; });
      const med = sorted[Math.floor(sorted.length / 2)] || 0;
      if (med < PROMOTE_UNDER_MS && tier < TIERS.length - 1) {
        tier++;
        if (onTierChange) { onTierChange(TIERS[tier], 'promote', med); }
      }
      return;
    }
    if (costs.length < 20) { return; }
    const s2 = costs.slice().sort(function (a, b) { return a - b; });
    const median = s2[Math.floor(s2.length / 2)] || 0;
    if (median > budgetMs() * DEMOTE_OVER_RATIO) {
      if (!overSince) { overSince = t; }
      else if (t - overSince > DEMOTE_SUSTAIN_MS && tier > 0) {
        tier--; overSince = 0; costs.length = 0;
        if (onTierChange) { onTierChange(TIERS[tier], 'demote', median); }
      }
    } else { overSince = 0; }
  }

  // ── loop ────────────────────────────────────────────────────────────────
  function frame() {
    rafId = 0;
    if (!running) { return; }
    schedule();
    if (document.hidden) { return; }

    const t = now();
    const interval = budgetMs();
    if (lastDraw && (t - lastDraw) < interval - 1.2) { return; }
    const dt = lastTick ? Math.min(120, t - lastTick) : 16;
    lastTick = t; lastDraw = t;

    const t0 = now();
    if (!sizeCanvas()) { return; }

    stepBlink(t);
    stepMouth(t, dt);
    compose();

    const cost = now() - t0;
    fpsEma = fpsEma ? (fpsEma * 0.9 + (1000 / Math.max(1, dt)) * 0.1) : 1000 / Math.max(1, dt);
    governor(t, cost);
  }

  function schedule() {
    if (!running || rafId) { return; }
    try { rafId = requestAnimationFrame(frame); }
    catch (e) { running = false; }
  }

  // ── speech binding ──────────────────────────────────────────────────────
  // We attach with addEventListener so avatar.js's own `utt.onstart` /
  // `utt.onend` assignments keep working untouched.
  function bindUtterance(utt) {
    if (!utt || utt.__tlmBound) { return; }
    utt.__tlmBound = true;
    const text = String(utt.text || '');

    utt.addEventListener('start', function () {
      track = buildTrack(text);
      trackLen = track.length;
      anchorChar = 0; anchorT = now(); speechStart = anchorT;
      boundaryCount = 0; rateKnown = false;
      rate = (CHARS_PER_SEC * (utt.rate || 1)) / 1000;
      speaking = true; driver = 'boundary';
      ensureRunning();
    });

    utt.addEventListener('boundary', function (ev) {
      if (!speaking) { return; }
      const t = now();
      const ci = typeof ev.charIndex === 'number' ? ev.charIndex : anchorChar;
      const dc = ci - anchorChar, dtm = t - anchorT;
      // Re-anchor on ground truth, and learn the real local speaking rate.
      if (dc > 0 && dtm > 40) {
        const r = dc / dtm;
        if (r > 0.002 && r < 0.12) {         // 2-120 chars/s — reject nonsense
          rate = rateKnown ? (rate * 0.6 + r * 0.4) : r;
          rateKnown = true;
        }
      }
      anchorChar = ci; anchorT = t;
      boundaryCount++;
      driver = 'boundary';
    });

    function done() {
      speaking = false; track = null; trackLen = 0;
      driver = 'idle';
    }
    utt.addEventListener('end', done);
    utt.addEventListener('error', done);
  }

  function attachToSpeechSynthesis() {
    try {
      const ss = window.speechSynthesis;
      if (!ss || ss.__tlmPatched) { return; }
      const orig = ss.speak.bind(ss);
      ss.speak = function (u) {
        try { bindUtterance(u); } catch (e) { /* fail-open */ }
        return orig(u);
      };
      ss.__tlmPatched = true;
    } catch (e) { /* fail-open */ }
  }

  // A safety net: if speech is cancelled outside our knowledge, the engine
  // stops reporting `speaking` and the mouth must close. Cheap poll, 4 Hz.
  function speechWatch() {
    try {
      const ss = window.speechSynthesis;
      // ⚠️ A SIMULATED utterance has no engine behind it, so `ss.speaking` is
      // false for the whole run. Without this guard the watchdog cancelled the
      // simulation within 250 ms and the mouth barely opened — which is exactly
      // what the visible regression caught on 2026-09-11 (peak 0.034, r=-0.16).
      if (driver === 'simulated') { return; }
      if (speaking && ss && !ss.speaking && !ss.pending) {
        speaking = false; track = null; trackLen = 0; driver = 'idle';
      }
    } catch (e) { /* fail-open */ }
  }

  function ensureRunning() {
    if (!ready) { return; }
    if (!running) { running = true; lastTick = 0; lastDraw = 0; schedule(); }
  }

  // ── public API ──────────────────────────────────────────────────────────
  const API = {
    start: function (opts) {
      opts = opts || {};
      try {
        dock = document.getElementById('tlm-avatar-dock');
        faceOuter = document.getElementById('tlm-face-outer');
        if (!dock || !faceOuter) { return false; }
        if (!collectImages()) { return false; }

        canvas = document.getElementById('tlm-canvas');
        if (!canvas) {
          canvas = document.createElement('canvas');
          canvas.id = 'tlm-canvas';
          faceOuter.appendChild(canvas);
        }
        ctx = canvas.getContext && canvas.getContext('2d');
        if (!ctx) { return false; }

        onTierChange = typeof opts.onTierChange === 'function' ? opts.onTierChange : null;
        if (!sizeCanvas()) { return false; }

        // Canvas is live: retire the <img> stack it replaces.
        const face = document.getElementById('tlm-face');
        if (face) { face.classList.add('tlm-canvas-live'); }

        ready = true;
        scheduleBlink(now(), false);
        attachToSpeechSynthesis();
        setInterval(speechWatch, 250);
        ensureRunning();
        return true;
      } catch (e) {
        ready = false;
        return false;
      }
    },

    // Called on a dock resize so the portraits are re-scaled at the new size.
    resize: function () {
      try { dispW = 0; dispH = 0; sizeCanvas(); } catch (e) { /* fail-open */ }
    },

    stop: function () {
      running = false;
      if (rafId) { try { cancelAnimationFrame(rafId); } catch (e) { /* noop */ } }
      rafId = 0;
    },

    isReady: function () { return ready; },

    // Inspection surface for the visible regression tests. Everything the
    // test needs to PROVE the face is really moving, and moving with the
    // voice, rather than merely being present.
    stats: function () {
      return {
        ready: ready, running: running, speaking: speaking,
        eye: eye, mouth: mouth,
        fps: Math.round(fpsEma), targetFps: TIERS[tier], tier: tier,
        frameCostMs: Math.round(lastFrameCost * 1000) / 1000,
        frames: frameCount, blinks: blinkCount,
        boundaries: boundaryCount, driver: driver,
        width: dispW, height: dispH,
        layers: Object.keys(layers).length
      };
    },

    // Test hook: drive the mouth track directly, with no audio device and no
    // voice installed, so lip sync is provable on a build server too.
    simulateSpeech: function (text, ms) {
      track = buildTrack(text); trackLen = track.length;
      anchorChar = 0; anchorT = now(); speechStart = anchorT;
      rate = trackLen / Math.max(1, ms || (trackLen / CHARS_PER_SEC * 1000));
      rateKnown = true; boundaryCount = 0; driver = 'simulated';
      speaking = true; ensureRunning();
      const self = this;
      setTimeout(function () { self.endSimulation(); }, ms || 2000);
    },
    endSimulation: function () {
      speaking = false; track = null; trackLen = 0; driver = 'idle';
    },
    opennessOf: function (ch) { return openness(String(ch || ' ').charAt(0)); }
  };

  window.TlamatiniPresence = API;
})();
