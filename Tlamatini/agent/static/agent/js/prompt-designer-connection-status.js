// ═══════════════════════════════════════════════════════════════════
//   ✦  T L A M A T I N I  ✦   —   "one who knows"
//
//   Created by  Angela López Mendoza   ·   @angelahack1
//   Developer · Architect · Creator of Tlamatini
// ═══════════════════════════════════════════════════════════════════
//   Tlamatini Author Banner — do not remove
//
// "BACKEND IS DOWN" BANNER FOR THE PROMPT DESIGNER
// ===============================================
//
// WHY THIS EXISTS
//   Both sibling pages already tell you when the backend dies: the chat paints
//   #connection-status from its WebSocket onclose/onerror (agent_page_state.js),
//   and the ACP designer does it over HTTP (acp-connection-status.js). The
//   Prompt Designer had NOTHING. If the server died, the canvas, the Assets
//   panel and all five toolbar buttons still looked perfectly healthy — the
//   page looked alive while talking to nobody. This closes that last gap so all
//   THREE pages behave the same way.
//
// WHY IT IS ITS OWN FILE AND NOT A REUSE OF acp-connection-status.js
//   The Prompt Designer "owns a completely separate script set and stylesheet,
//   so an edit on either page can never reach across and break the other"
//   (docs/claude/frontend.md). Loading an `acp-*` module here would quietly
//   couple the two designers and put the ACP one edit away from breaking a page
//   it does not belong to. The detection strategy is deliberately identical —
//   the isolation is the point, not a different algorithm.
//
// HOW DETECTION WORKS (and why the emphasis differs from the ACP)
//   Like the ACP this page has ZERO WebSockets, so there is no onclose to hang
//   off. Two mechanisms, same as the ACP:
//
//     1. fetch WRAPPER — a fetch that REJECTS with TypeError means, in browser
//        terms, "no network / no server". A 500 still RESOLVES (with
//        response.ok === false), so only a rejection counts as an outage.
//     2. HEARTBEAT every 8 s against /agent/version/.
//
//   ⚠️ THE WEIGHTING IS NOT THE SAME AS THE ACP'S. The ACP is 129 `fetch`
//   calls, so its wrapper does most of the work and the heartbeat is the
//   backstop. In Sprint 1 the Prompt Designer makes almost NO backend calls at
//   all — every control answers with the themed "Working on it for further
//   sprints" notice — so here it is the other way round: THE HEARTBEAT IS
//   ESSENTIALLY THE WHOLE DETECTOR. Do not "optimise" it away as redundant on
//   the grounds that the wrapper exists; on this page the wrapper may never
//   fire once. The wrapper is kept because Sprint 2+ (Open / Save as) will
//   start making real calls, and it gives an INSTANT warning the moment you act
//   rather than up to 8 s later.
//
//   /agent/version/ is used because it is the ONLY route without
//   @login_required (urls.py), so the heartbeat never triggers a login redirect
//   nor disturbs the session, and it is cheap.
//
// WHAT THIS MODULE DELIBERATELY DOES NOT DO
//   It does NOT disable the toolbar buttons. They ship in the greyed
//   `.pd-control-btn-idle` look but are deliberately NOT `disabled` (a disabled
//   button swallows its own click and the page reads as dead rather than
//   unfinished). Forcing them from here would fight that decision and could
//   leave them wedged once the backend returns. The banner warns; the buttons
//   stay owned by the code that already owns them.
//
// FAIL-OPEN: if anything in here breaks, the Prompt Designer must keep working
// exactly as before. Everything is wrapped in try/catch, and an error is never
// swallowed from — nor injected into — the code that called fetch.
(function () {
    "use strict";

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

    // ---- 1) fetch wrapper: instant warning the moment you act --------------
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

    // ---- 2) heartbeat: on THIS page, the detector that actually fires ------
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
        } catch (e) { /* fail-open: the designer must stay usable */ }
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', start);
    } else {
        setTimeout(start, 0);
    }
}());
