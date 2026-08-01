// ═══════════════════════════════════════════════════════════════════
//   ✦  T L A M A T I N I  ✦   —   "one who knows"
//
//   Created by  Angela López Mendoza   ·   @angelahack1
//   Developer · Architect · Creator of Tlamatini
// ═══════════════════════════════════════════════════════════════════
//   Tlamatini Author Banner — do not remove
//
// "BACKEND IS DOWN" BANNER FOR THE ACP DESIGNER
// ============================================
//
// WHY THIS EXISTS
//   The chat page already tells you when the backend dies: agent_page_state.js
//   paints the #connection-status bar ("Live connection lost...") from its
//   WebSocket onclose/onerror. The ACP designer had nothing of the sort: if the
//   server died, the canvas still looked perfectly healthy and every click —
//   Validate, Start, Save — failed silently. You were left staring at a page
//   that looked alive but was talking to nobody.
//
// WHY IT COULD NOT BE COPIED AS-IS
//   The ACP has ZERO WebSockets — it is 129 `fetch` calls. There is no onclose
//   to hang off. Detection here is deliberately different:
//
//     1. fetch WRAPPER — a fetch that rejects with TypeError means, in browser
//        terms, "no network / no server" (a 500 still RESOLVES, with
//        response.ok=false). That gives an immediate warning the moment you act.
//     2. HEARTBEAT every 8 s against /agent/version/ — because the ACP sits
//        idle for long stretches. Without it the server could be dead for half
//        an hour and you would not find out until your next click.
//
//   /agent/version/ was chosen because it is the ONLY route without
//   @login_required (urls.py), so the heartbeat never triggers a login redirect
//   nor disturbs the session, and it is cheap.
//
// WHAT THIS MODULE DELIBERATELY DOES NOT DO
//   It does NOT disable the control buttons (Validate/Start/Stop/Pause/Clear).
//   Those carry their own state machine (running/paused/validated) in
//   acp-control-buttons.js and acp-running-state.js; stomping it from here
//   risks leaving them wedged in an invalid state once the backend returns — a
//   worse bug than the one being fixed. The banner warns; the state machine
//   stays owned by the code that already owns it.
//
// FAIL-OPEN: if anything in here breaks, the ACP must keep working exactly as
// before. Everything is wrapped in try/catch and no error is ever swallowed
// from — or injected into — the code that called fetch.
(function () {
    "use strict";

    // ---- the only part that differs from the Spanish edition ---------------
    var TXT = {
        down: 'Backend connection lost. The Tlamatini server is not responding — ' +
              'restart it and refresh this page before continuing.',
        back: 'The backend is back. You can keep working.'
    };

    var HEARTBEAT_MS = 8000;   // how often we check while nothing is happening
    var OK_VISIBLE_MS = 4000;  // how long the green message stays before hiding

    var bar = null;
    var isDown = false;
    var okTimer = null;
    var started = false;

    function paint(message, tone) {
        if (!bar) { return; }
        bar.textContent = message || '';
        bar.classList.remove('connection-status-hidden',
                             'connection-status-warning',
                             'connection-status-ok');
        bar.classList.add('connection-status-' + tone);
    }

    function hide() {
        if (!bar) { return; }
        bar.textContent = '';
        bar.classList.add('connection-status-hidden');
        bar.classList.remove('connection-status-warning', 'connection-status-ok');
    }

    function markDown() {
        if (isDown) { return; }         // do not repaint on every failed fetch
        isDown = true;
        if (okTimer) { clearTimeout(okTimer); okTimer = null; }
        paint(TXT.down, 'warning');
    }

    function markAlive() {
        if (!isDown) { return; }        // only announce after an actual outage
        isDown = false;
        paint(TXT.back, 'ok');
        if (okTimer) { clearTimeout(okTimer); }
        okTimer = setTimeout(hide, OK_VISIBLE_MS);
    }

    // ---- 1) fetch wrapper: immediate warning -------------------------------
    function wrapFetch() {
        if (typeof window.fetch !== 'function') { return; }
        var original = window.fetch;
        window.fetch = function () {
            var args = arguments;
            var p;
            try {
                p = original.apply(this, args);
            } catch (e) {
                markDown();
                throw e;                // never swallow the caller's error
            }
            return p.then(function (resp) {
                // ANY HTTP response — a 500 included — means the server IS
                // alive. Only a network-level failure counts as an outage.
                markAlive();
                return resp;
            }, function (err) {
                markDown();
                throw err;              // the caller still sees its own error
            });
        };
    }

    // ---- 2) heartbeat: catches an outage even while you are idle -----------
    function heartbeat() {
        // Goes through the wrapped fetch on purpose, so markAlive/markDown are
        // driven from a single place.
        try {
            window.fetch('/agent/version/', {
                method: 'GET',
                cache: 'no-store',
                credentials: 'same-origin'
            })["catch"](function () { /* the wrapper already reported it */ });
        } catch (e) { /* fail-open */ }
    }

    function start() {
        if (started) { return; }
        started = true;
        try {
            bar = document.getElementById('connection-status');
            if (!bar) { return; }       // no bar in the HTML, nothing to drive
            wrapFetch();
            setInterval(heartbeat, HEARTBEAT_MS);
            heartbeat();                // one check on the way in
        } catch (e) { /* fail-open: the ACP must stay usable */ }
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', start);
    } else {
        setTimeout(start, 0);
    }
}());
