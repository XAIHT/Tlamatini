// ═══════════════════════════════════════════════════════════════════
//   ✦  T L A M A T I N I  ✦   —   "one who knows"
//
//   Created by  Angela López Mendoza   ·   @angelahack1
//   Developer · Architect · Creator of Tlamatini
// ═══════════════════════════════════════════════════════════════════
//   Tlamatini Author Banner — do not remove
//
// AVATAR SIZING — she is resizable, from 120 px up to most of the screen.
// ─────────────────────────────────────────────────────────────────────────
// Angela, 2026-09-11: "the image(s) of her must be sizeable from 120px as the
// minimum, I don't know if you can make it sizeable or better, you decide."
//
// TWO STATES, AND THE DEFAULT IS UNCHANGED
//   DOCKED   — exactly today's layout: absolutely positioned inside the chat
//              form container, 25% width, anchored top-right. A user who never
//              touches the handle sees no difference at all. That is the point:
//              the feature is opt-in, so it cannot regress anybody's layout.
//   FLOATING — the moment she is resized she becomes `position: fixed`,
//              anchored bottom-right of the viewport, at an explicit square
//              size. She then grows UP and LEFT, over the page, so she can
//              reach presentation size without fighting the chat layout for
//              room. This is the mode for a demonstration.
//
// WHY THE HANDLE SITS AT THE TOP-LEFT
//   Because she is anchored bottom-right when floating, the top-left corner is
//   the one that moves when she grows. Dragging it away from the anchor makes
//   her bigger, which is the direction every window manager on earth has
//   trained people to expect.
//
// CONTROLS
//   drag the handle        — free resize, 120 px floor, clamped to the viewport
//   double-click the handle— cycle 160 → 240 → 360 → 520 → back to DOCKED
//   arrow keys (focused)   — ±20 px, so this is reachable without a mouse
//   the size is remembered in localStorage and restored on the next visit
//
// ⚠️ THE 120 px FLOOR IS A FLOOR, NOT A DEFAULT. It is the smallest size at
//   which her face is still legible; nothing may resize her below it.
//
// FAIL-OPEN. A missing dock, a missing handle, or a localStorage that throws
// all leave the avatar exactly as it was. Nothing here may raise into the chat.
(function () {
  'use strict';

  var STORE = 'tlm_avatar_size';
  var MIN = 120;                         // Angela's floor. Never go under it.
  var PRESETS = [160, 240, 360, 520, 0]; // 0 == back to the docked layout
  var STEP = 20;

  var dock = null, handle = null;
  var dragging = false, startX = 0, startY = 0, startSize = 0;
  // ⚠️ RE-ENTRANCY GUARD. `apply()` ends by dispatching a synthetic `resize`
  // so layouts that listen for it re-run — and the window `resize` handler
  // below calls `apply()`. Without this flag those two call each other
  // forever: the first visible run threw "Maximum call stack size exceeded"
  // on every resize. Do not remove it.
  var applying = false;

  function maxSize() {
    var w = window.innerWidth || 900, h = window.innerHeight || 700;
    return Math.max(MIN, Math.floor(Math.min(w - 40, h - 40) * 0.92));
  }

  function clampSize(px) {
    var m = maxSize();
    if (px < MIN) { return MIN; }
    if (px > m) { return m; }
    return Math.round(px);
  }

  function load() {
    try {
      var v = parseInt(window.localStorage.getItem(STORE) || '0', 10);
      return isNaN(v) ? 0 : v;
    } catch (e) { return 0; }
  }

  function save(px) {
    try { window.localStorage.setItem(STORE, String(px || 0)); }
    catch (e) { /* private mode — the size simply will not persist */ }
  }

  // Applying a size is the ONLY place the dock's geometry is written.
  function apply(px, persist) {
    if (!dock || applying) { return; }
    applying = true;
    try { _apply(px, persist); } finally { applying = false; }
  }

  function _apply(px, persist) {
    if (!px) {                                   // ── docked (the default)
      dock.classList.remove('tlm-floating');
      dock.style.width = '';
      dock.style.height = '';
      dock.style.top = '';
      dock.style.left = '';
      dock.style.right = '';
      dock.style.bottom = '';
    } else {                                     // ── floating
      px = clampSize(px);
      dock.classList.add('tlm-floating');
      dock.style.width = px + 'px';
      dock.style.height = px + 'px';
    }
    if (persist !== false) { save(px || 0); }
    // The dock's ResizeObserver re-runs layoutFace(), which re-scales the
    // portraits through TlamatiniPresence.resize(). Nudge it directly too, so
    // a browser without ResizeObserver still repaints at the new size.
    try {
      if (window.TlamatiniPresence && window.TlamatiniPresence.resize) {
        window.TlamatiniPresence.resize();
      }
    } catch (e) { /* fail-open */ }
    try { window.dispatchEvent(new Event('resize')); } catch (e) { /* fail-open */ }
  }

  function currentSize() {
    if (!dock || !dock.classList.contains('tlm-floating')) { return 0; }
    return Math.round(dock.getBoundingClientRect().width) || 0;
  }

  function nextPreset() {
    var cur = currentSize();
    for (var i = 0; i < PRESETS.length; i++) {
      if (PRESETS[i] && cur && Math.abs(PRESETS[i] - cur) < 24) {
        return PRESETS[(i + 1) % PRESETS.length];
      }
    }
    return cur ? 0 : PRESETS[0];
  }

  function onDown(ev) {
    if (!dock) { return; }
    ev.preventDefault();
    ev.stopPropagation();                 // never let the dock's click fire
    dragging = true;
    var p = ev.touches ? ev.touches[0] : ev;
    startX = p.clientX; startY = p.clientY;
    var r = dock.getBoundingClientRect();
    startSize = dock.classList.contains('tlm-floating')
      ? Math.round(r.width)
      : Math.round(Math.min(r.width, r.height)) || MIN;
    if (!dock.classList.contains('tlm-floating')) { apply(startSize, false); }
    document.body.classList.add('tlm-resizing');
  }

  function onMove(ev) {
    if (!dragging) { return; }
    var p = ev.touches ? ev.touches[0] : ev;
    // Anchored bottom-right: moving the top-left handle up or left grows her.
    var grow = Math.max(startX - p.clientX, startY - p.clientY);
    apply(clampSize(startSize + grow), false);
    if (ev.cancelable) { ev.preventDefault(); }
  }

  function onUp() {
    if (!dragging) { return; }
    dragging = false;
    document.body.classList.remove('tlm-resizing');
    save(currentSize());
  }

  function onKey(ev) {
    var k = ev.key;
    if (k !== 'ArrowUp' && k !== 'ArrowDown' && k !== 'ArrowLeft' && k !== 'ArrowRight') { return; }
    ev.preventDefault();
    ev.stopPropagation();
    var cur = currentSize() || MIN;
    var d = (k === 'ArrowUp' || k === 'ArrowLeft') ? STEP : -STEP;
    var next = cur + d;
    apply(next < MIN ? 0 : next, true);
  }

  function build() {
    dock = document.getElementById('tlm-avatar-dock');
    if (!dock) { return false; }
    handle = document.getElementById('tlm-avatar-resize');
    if (!handle) {
      handle = document.createElement('div');
      handle.id = 'tlm-avatar-resize';
      handle.setAttribute('role', 'slider');
      handle.setAttribute('tabindex', '0');
      handle.setAttribute('aria-label',
        'Resize Tlamatini. Drag, or use the arrow keys. Double-click to cycle sizes.');
      handle.title = 'Drag to resize  ·  Double-click to cycle sizes  ·  Arrow keys';
      dock.appendChild(handle);
    }

    handle.addEventListener('mousedown', onDown);
    handle.addEventListener('touchstart', onDown, { passive: false });
    window.addEventListener('mousemove', onMove);
    window.addEventListener('touchmove', onMove, { passive: false });
    window.addEventListener('mouseup', onUp);
    window.addEventListener('touchend', onUp);
    handle.addEventListener('keydown', onKey);
    handle.addEventListener('dblclick', function (ev) {
      ev.preventDefault(); ev.stopPropagation();
      apply(nextPreset(), true);
    });
    // A click on the handle must never reach the dock (which would greet or
    // silence her). The handle does one job.
    handle.addEventListener('click', function (ev) { ev.stopPropagation(); });

    window.addEventListener('resize', function () {
      var cur = currentSize();
      if (cur) { apply(clampSize(cur), false); }
    });
    return true;
  }

  function init() {
    if (!build()) { return; }
    apply(load(), false);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else { init(); }

  window.TlamatiniAvatarSize = {
    set: function (px) { apply(px ? clampSize(px) : 0, true); },
    get: currentSize,
    min: function () { return MIN; },
    max: maxSize,
    presets: function () { return PRESETS.slice(); },
    cycle: function () { apply(nextPreset(), true); return currentSize(); }
  };
})();
