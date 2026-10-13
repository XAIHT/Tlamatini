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
//   DOCKED   — square, anchored top-right inside the chat form, up to 25% of
//              its width. The composer divider can shrink her to 120 px;
//              agent_page_layout.js fits both available dimensions.
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
  var dragging = false, pointerId = null, startX = 0, startY = 0, startSize = 0;
  // ⚠️ RE-ENTRANCY GUARD. `apply()` ends by dispatching a synthetic `resize`
  // so layouts that listen for it re-run — and the window `resize` handler
  // below calls `apply()`. Without this flag those two call each other
  // forever: the first visible run threw "Maximum call stack size exceeded"
  // on every resize. Do not remove it.
  var applying = false;

  function maxSize() {
    var w = window.innerWidth || 900, h = window.innerHeight || 700;
    const canvas = document.getElementById('canvas-container');
    if (w <= 720 && canvas) {
      // The narrow-screen workspace pans; keep her over its canvas so she
      // cannot cover the message input or Send button at high browser zoom.
      w = Math.min(w, canvas.clientWidth);
    }
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

  // Own floating geometry here; docked geometry comes from the composer CSS variable.
  function apply(px, persist) {
    if (!dock || applying) { return; }
    applying = true;
    try { _apply(px, persist); } finally { applying = false; }
  }

  function _apply(px, persist) {
    const focused = dock.contains(document.activeElement) ? document.activeElement : null;
    if (!px) {                                   // ── docked (the default)
      const form = document.getElementById('chat-form');
      if (form && dock.parentNode !== form) form.appendChild(dock);
      dock.classList.remove('tlm-floating');
      dock.style.width = '';
      dock.style.height = '';
      dock.style.top = '';
      dock.style.left = '';
      dock.style.right = '';
      dock.style.bottom = '';
    } else {                                     // ── floating
      const workspace = document.getElementById('chat-workspace');
      if (workspace && dock.parentNode !== workspace) workspace.appendChild(dock);
      px = clampSize(px);
      dock.classList.add('tlm-floating');
      dock.style.width = px + 'px';
      dock.style.height = px + 'px';
    }
    // Reparenting must not lose keyboard resize focus or pan a narrow page.
    if (focused && document.activeElement !== focused) focused.focus({ preventScroll: true });
    if (persist !== false) { save(px || 0); }
    if (handle) {
      handle.setAttribute('aria-valuemin', '0');
      handle.setAttribute('aria-valuemax', String(maxSize()));
      handle.setAttribute('aria-valuenow', String(px || 0));
      handle.setAttribute('aria-valuetext', px ? px + ' pixels' : 'Docked');
    }
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
    if (!dock || dragging || !ev.isPrimary || ev.button !== 0) { return; }
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
    pointerId = ev.pointerId;
    handle.setPointerCapture(pointerId);
    handle.focus({ preventScroll: true });
    document.body.classList.add('tlm-resizing');
  }

  function onMove(ev) {
    if (!dragging || ev.pointerId !== pointerId) { return; }
    if (ev.pointerType === 'mouse' && !(ev.buttons & 1)) { onUp(); return; }
    var p = ev.touches ? ev.touches[0] : ev;
    // Anchored bottom-right: moving the top-left handle up or left grows her.
    var grow = Math.max(startX - p.clientX, startY - p.clientY);
    apply(clampSize(startSize + grow), false);
    if (ev.cancelable) { ev.preventDefault(); }
  }

  function onUp() {
    if (!dragging) { return; }
    dragging = false;
    const previous = pointerId;
    pointerId = null;
    if (handle.hasPointerCapture(previous)) handle.releasePointerCapture(previous);
    document.body.classList.remove('tlm-resizing');
    save(currentSize());
  }

  function onKey(ev) {
    var k = ev.key;
    if (ev.ctrlKey || ev.metaKey || ev.altKey) return;
    if (k === 'Home' || k === 'End') {
      ev.preventDefault(); ev.stopPropagation();
      apply(k === 'Home' ? 0 : maxSize(), true); return;
    }
    if (k !== 'ArrowUp' && k !== 'ArrowDown' && k !== 'ArrowLeft' && k !== 'ArrowRight') { return; }
    ev.preventDefault();
    ev.stopPropagation();
    var cur = currentSize() || MIN;
    var d = (k === 'ArrowUp' || k === 'ArrowLeft') ? STEP : -STEP;
    if (ev.shiftKey) d *= 5;
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

    handle.style.touchAction = 'none';
    handle.addEventListener('pointerdown', onDown);
    handle.addEventListener('pointermove', onMove);
    ['pointerup', 'pointercancel', 'lostpointercapture'].forEach(function (type) {
      handle.addEventListener(type, function (ev) { if (ev.pointerId === pointerId) onUp(); });
    });
    window.addEventListener('blur', onUp);
    window.addEventListener('pagehide', onUp);
    document.addEventListener('visibilitychange', function () { if (document.hidden) onUp(); });
    document.addEventListener('keydown', function (ev) { if (ev.key === 'Escape') onUp(); });
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
