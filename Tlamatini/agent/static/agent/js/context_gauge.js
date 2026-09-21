/* =====================================================================
 * context_gauge.js — the context ring in the chat window
 * (Angela López Mendoza, 2026-09-20 — Context Governor, step 1)
 * ---------------------------------------------------------------------
 * Renders ONE row between the toolbar and the message box showing how big
 * the request about to go to the model really is.
 *
 * WHY THE SERVER SENDS THE NUMBER: this page never sees the system prompt,
 * the chat history as it is actually sent, or the ~109 bound tool schemas.
 * Anything measured here would be a guess. So the backend measures and
 * pushes a `context-gauge` frame; `agent_page_chat.js` re-dispatches it as
 * the DOM event this file listens for.
 *
 * CONTRACTS (design Part IV / Part V — do NOT weaken):
 *   · BYTES ARE MEASURED, TOKENS ARE ESTIMATED, and the GUI says which is
 *     which. The byte count is the headline with no qualifier; the token
 *     figure and the percentage always carry "est.". Showing them with
 *     equal confidence is the same quiet lie as a green Exec Report row
 *     on a failed agent.
 *   · The exact integer is NEVER rounded away — it is always one hover
 *     away, with thousands separators.
 *   · NO GAUGE DATA ⇒ NO GAUGE. Before the first frame the row stays
 *     `display:none` at zero height and the page is exactly as it was.
 *   · Colour is never the only signal; the zone WORD and the numbers
 *     carry it too.
 *   · FAIL OPEN. Every path is guarded: a malformed frame leaves the last
 *     good reading on screen. A broken gauge must never cost the chat.
 *
 * Self-contained IIFE declaring NO cross-file globals — the shape of
 * chat_image_paste.js and welcome_enter_default.js.
 * ===================================================================== */

(function () {
    'use strict';

    var ROW_ID = 'context-gauge-row';
    var EVENT_NAME = 'tlm:context-gauge';
    var RING_RADIUS = 14;
    var RING_CIRCUMFERENCE = 2 * Math.PI * RING_RADIUS;
    var DEFAULT_HISTORY = 12;
    var SVG_NS = 'http://www.w3.org/2000/svg';

    var built = false;
    var history = [];
    var nodes = {};

    function groupDigits(value) {
        try {
            return Number(value).toLocaleString();
        } catch (err) {
            return String(value);
        }
    }

    function svg(tag, attrs) {
        var el = document.createElementNS(SVG_NS, tag);
        Object.keys(attrs || {}).forEach(function (key) {
            el.setAttribute(key, attrs[key]);
        });
        return el;
    }

    function div(className) {
        var el = document.createElement('div');
        if (className) el.className = className;
        return el;
    }

    // Built once, at page load (Angela, 2026-09-21: the row must be on screen
    // from the moment the chat opens, not only after the first measurement).
    function build(row) {
        var ring = svg('svg', {
            'class': 'ctxg-ring',
            viewBox: '0 0 36 36',
            role: 'img',
            'aria-label': 'Context fill'
        });
        ring.appendChild(svg('circle', {
            'class': 'ctxg-ring-track', cx: 18, cy: 18, r: RING_RADIUS
        }));
        nodes.ringValue = svg('circle', {
            'class': 'ctxg-ring-value',
            cx: 18, cy: 18, r: RING_RADIUS,
            'stroke-dasharray': RING_CIRCUMFERENCE,
            'stroke-dashoffset': RING_CIRCUMFERENCE
        });
        ring.appendChild(nodes.ringValue);
        nodes.ringPct = svg('text', { 'class': 'ctxg-ring-pct', x: 18, y: 18 });
        nodes.ringPct.textContent = '0%';
        ring.appendChild(nodes.ringPct);

        var legend = div('ctxg-legend');
        nodes.bytes = div('ctxg-bytes');
        nodes.tokens = div('ctxg-tokens');
        legend.appendChild(nodes.bytes);
        legend.appendChild(nodes.tokens);

        nodes.zoneWord = div('ctxg-zone-word');
        nodes.zoneWord.textContent = 'GREEN';

        var spark = svg('svg', {
            'class': 'ctxg-spark',
            viewBox: '0 0 100 26',
            preserveAspectRatio: 'none',
            role: 'img',
            'aria-label': 'Context size over the last model steps'
        });
        nodes.sparkLine = svg('polyline', { 'class': 'ctxg-spark-line', points: '' });
        nodes.sparkMark = svg('circle', { 'class': 'ctxg-spark-mark', cx: -10, cy: -10, r: 1.8 });
        spark.appendChild(nodes.sparkLine);
        spark.appendChild(nodes.sparkMark);

        var streams = div('ctxg-streams');
        var bar = div('ctxg-bar');
        nodes.segPrefix = div('ctxg-seg ctxg-seg-prefix');
        nodes.segHistory = div('ctxg-seg ctxg-seg-history');
        nodes.segLoop = div('ctxg-seg ctxg-seg-loop');
        bar.appendChild(nodes.segPrefix);
        bar.appendChild(nodes.segHistory);
        bar.appendChild(nodes.segLoop);
        nodes.streamsLabel = div('ctxg-streams-label');
        streams.appendChild(bar);
        streams.appendChild(nodes.streamsLabel);

        // THE LEGEND, at the far left of the line (Angela, 2026-09-21):
        // "the user doesn't know what the fuck that graph is". A number with
        // no name is a puzzle, not information — so the row says what it is
        // before it says how big it is, and the second line names WHICH call
        // produced the reading (one-shot / multi-turn / acpx).
        nodes.title = div('ctxg-title');
        var titleMain = div('ctxg-title-main');
        titleMain.textContent = 'CONTEXT';
        nodes.titleSub = div('ctxg-title-sub');
        nodes.titleSub.textContent = 'sent to the model';
        nodes.title.appendChild(titleMain);
        nodes.title.appendChild(nodes.titleSub);
        nodes.title.title = 'How much conversation Tlamatini is sending to the '
            + 'model on this request: the system prompt, the bound tools, the '
            + 'chat history and the tool loop. Bytes are measured; tokens and '
            + 'the percentage are estimates.';

        row.appendChild(nodes.title);
        row.appendChild(ring);
        row.appendChild(legend);
        row.appendChild(nodes.zoneWord);
        row.appendChild(spark);
        row.appendChild(streams);
        built = true;
    }

    function renderSparkline(limit) {
        if (!nodes.sparkLine) return;
        while (history.length > limit) history.shift();
        if (history.length < 2) {
            nodes.sparkLine.setAttribute('points', '');
            nodes.sparkMark.setAttribute('cx', -10);
            return;
        }
        // Scaled to this run's own peak, so the SHAPE of the growth is what
        // you read. Against a fixed ceiling most real runs would be a flat
        // line on the floor and show nothing.
        var peak = 1;
        var i;
        for (i = 0; i < history.length; i++) {
            if (history[i] > peak) peak = history[i];
        }
        var step = 100 / (history.length - 1);
        var points = [];
        var x = 0;
        var y = 0;
        for (i = 0; i < history.length; i++) {
            x = i * step;
            y = 24 - (history[i] / peak) * 22;
            points.push(x.toFixed(1) + ',' + y.toFixed(1));
        }
        nodes.sparkLine.setAttribute('points', points.join(' '));
        nodes.sparkMark.setAttribute('cx', x.toFixed(1));
        nodes.sparkMark.setAttribute('cy', y.toFixed(1));
    }

    function render(detail) {
        var row = document.getElementById(ROW_ID);
        if (!row || !detail || detail.ok === false) return;

        if (!built) build(row);

        var total = Number(detail.bytes_total) || 0;
        var prefix = Number(detail.bytes_prefix) || 0;
        var hist = Number(detail.bytes_history) || 0;
        var loop = Number(detail.bytes_loop) || 0;
        var ratio = Number(detail.ratio) || 0;
        var pct = Math.max(0, Math.min(100, ratio * 100));
        var zone = String(detail.zone || 'green');
        var tokens = Number(detail.tokens_estimated) || 0;
        var ceiling = Number(detail.ceiling_tokens) || 0;

        row.setAttribute('data-zone', zone);
        row.classList.add('ctxg-visible');

        nodes.ringValue.setAttribute(
            'stroke-dashoffset',
            (RING_CIRCUMFERENCE * (1 - pct / 100)).toFixed(2)
        );
        // The ring's percentage is an ESTIMATE (the ceiling is in tokens),
        // so it is the small figure and it is labelled as one below.
        nodes.ringPct.textContent = Math.round(pct) + '%';

        // The measurement, unqualified — and the exact integer on hover.
        nodes.bytes.textContent = (detail.bytes_human || (total + ' B'));
        nodes.bytes.title = groupDigits(total) + ' bytes exactly — measured, '
            + 'the literal size of the request on the wire';

        nodes.tokens.textContent = '≈' + groupDigits(tokens) + ' tokens est. · '
            + pct.toFixed(1) + '% est.';
        nodes.tokens.title = 'Estimated at ~4 characters per token, of a '
            + groupDigits(ceiling) + '-token ceiling (' + (detail.ceiling_source || '?')
            + '). Tokens are ESTIMATED; the byte figure above is MEASURED.';

        nodes.zoneWord.textContent = zone.toUpperCase();

        // Name WHICH call this reading came from, so a moving ring is
        // explainable rather than mysterious.
        var source = String(detail.source || 'model');
        var when = String(detail.label || '');
        nodes.titleSub.textContent = when ? (source + ' · ' + when) : source;
        nodes.titleSub.title = 'Last measured on a ' + source + ' call'
            + (when ? (' while ' + when) : '');

        var denominator = total > 0 ? total : 1;
        nodes.segPrefix.style.width = ((prefix / denominator) * 100).toFixed(2) + '%';
        nodes.segHistory.style.width = ((hist / denominator) * 100).toFixed(2) + '%';
        nodes.segLoop.style.width = ((loop / denominator) * 100).toFixed(2) + '%';
        nodes.streamsLabel.textContent = 'loop ' + Math.round((loop / denominator) * 100)
            + '% · ' + (Number(detail.loop_messages) || 0) + ' msg';
        nodes.streamsLabel.title = 'prefix ' + groupDigits(prefix) + ' B · history '
            + groupDigits(hist) + ' B · tool loop ' + groupDigits(loop) + ' B';

        history.push(total);
        renderSparkline(Number(detail.history_turns) || DEFAULT_HISTORY);
    }

    // ── ALWAYS ON SCREEN ──────────────────────────────────────────────────
    // Angela, 2026-09-21: "make the graph stay always visible and showing
    // always since the page opens".
    //
    // So the row is built and shown at load, in an honest IDLE state: nothing
    // has been measured yet, so it SAYS so. It deliberately does NOT draw a
    // zero — the next request is never 0 bytes, and a fabricated reading is
    // worse than a missing one. The first real frame replaces every field.
    function bootIdle() {
        var row = document.getElementById(ROW_ID);
        if (!row) return;
        if (!built) build(row);

        row.setAttribute('data-zone', 'idle');
        row.classList.add('ctxg-visible');

        nodes.ringValue.setAttribute('stroke-dashoffset', RING_CIRCUMFERENCE);
        nodes.ringPct.textContent = '--';
        nodes.bytes.textContent = '--';
        nodes.bytes.title = 'Nothing has been measured yet on this page.';
        nodes.tokens.textContent = 'waiting for the first request';
        nodes.tokens.title = 'The gauge fills the moment Tlamatini builds a '
            + 'request for the model.';
        nodes.zoneWord.textContent = 'IDLE';
        nodes.titleSub.textContent = 'sent to the model';
        nodes.streamsLabel.textContent = 'prefix · history · tool loop';
    }

    function bootSafely() {
        try {
            bootIdle();
        } catch (err) {
            // The gauge must never cost the chat page. Stay silent on screen
            // and explain once in the console.
            if (window.console && window.console.warn) {
                window.console.warn('[context-gauge] idle boot skipped:', err);
            }
        }
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', bootSafely);
    } else {
        bootSafely();
    }

    document.addEventListener(EVENT_NAME, function (event) {
        try {
            render(event && event.detail);
        } catch (err) {
            // A broken gauge must never cost the chat. Leave the last good
            // reading on screen and say so once, in the console only.
            if (window.console && window.console.warn) {
                window.console.warn('[context-gauge] render skipped:', err);
            }
        }
    });
}());
