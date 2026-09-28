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
    var lastSeq = 0;
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
        nodes.segContext = div('ctxg-seg ctxg-seg-context');
        nodes.segHistory = div('ctxg-seg ctxg-seg-history');
        nodes.segLoop = div('ctxg-seg ctxg-seg-loop');
        bar.appendChild(nodes.segPrefix);
        bar.appendChild(nodes.segContext);
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
        nodes.title.title = 'How much Tlamatini sends to her main model on one '
            + 'request: the system prompt, the bound tools, your loaded context, '
            + 'the chat history and the tool loop. Bytes are measured. Tokens say '
            + 'REAL when they are Ollama\'s own prompt_eval_count for that exact '
            + 'request, and est. until Ollama has answered.';

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
        // Ollama's own count for THIS request, once it has answered it.
        var isReal = detail.ratio_is_real === true
            && detail.tokens_real !== null && detail.tokens_real !== undefined;
        var realTokens = isReal ? (Number(detail.tokens_real) || 0) : 0;
        var ctxBytes = Math.max(0, Number(detail.bytes_context) || 0);

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

        var turn = detail.turn || null;
        var turnText = '';
        if (turn && Number(turn.calls) > 0) {
            turnText = ' This answer so far: ' + groupDigits(turn.calls)
                + ' main-model call(s), ' + groupDigits(turn.prompt_tokens)
                + ' prompt + ' + groupDigits(turn.completion_tokens)
                + ' output tokens (REAL, from Ollama).';
        }
        var ceilingText = groupDigits(ceiling) + '-token context ('
            + (detail.ceiling_source || '?') + ')';
        if (isReal) {
            nodes.tokens.textContent = groupDigits(realTokens) + ' tokens REAL · '
                + pct.toFixed(1) + '%';
            nodes.tokens.classList.add('ctxg-real');
            var err = detail.estimate_error_pct;
            nodes.tokens.title = 'REAL: Ollama\'s own prompt_eval_count for this exact '
                + 'request (' + (detail.real_model || detail.model || 'model') + '), of a '
                + ceilingText + '. The chars/4 estimate was ' + groupDigits(tokens)
                + (err !== undefined && err !== null ? (' (' + (err > 0 ? '+' : '') + err + '%)') : '')
                + '.' + turnText;
        } else {
            nodes.tokens.textContent = '≈' + groupDigits(tokens) + ' tokens est. · '
                + pct.toFixed(1) + '% est.';
            nodes.tokens.classList.remove('ctxg-real');
            var last = detail.last_real || null;
            nodes.tokens.title = 'ESTIMATE (~4 characters per token) of a ' + ceilingText
                + ', shown until Ollama answers this request with its own count.'
                + (last ? (' Last REAL count: ' + groupDigits(last.tokens) + ' tokens ('
                    + (last.label || 'previous request') + ').') : '')
                + turnText;
        }

        nodes.zoneWord.textContent = zone.toUpperCase();

        // Name WHICH call this reading came from, so a moving ring is
        // explainable rather than mysterious.
        var source = String(detail.source || 'model');
        var when = String(detail.label || '');
        nodes.titleSub.textContent = when ? (source + ' · ' + when) : source;
        nodes.titleSub.title = (detail.kind === 'rest'
            ? 'What your NEXT message will send, rebuilt with the main chain\'s own '
              + 'code while nothing is running'
            : 'Measured on the ' + source + ' main-model call')
            + (when ? (' - ' + when) : '')
            + (detail.note ? ('. ' + detail.note) : '') + '.';

        // The context block sits inside the history bucket on the wire, so it
        // is carved OUT of it here - never counted twice.
        var denominator = total > 0 ? total : 1;
        var ctxShown = Math.min(ctxBytes, hist);
        var histOnly = Math.max(0, hist - ctxShown);
        nodes.segPrefix.style.width = ((prefix / denominator) * 100).toFixed(2) + '%';
        nodes.segContext.style.width = ((ctxShown / denominator) * 100).toFixed(2) + '%';
        nodes.segHistory.style.width = ((histOnly / denominator) * 100).toFixed(2) + '%';
        nodes.segLoop.style.width = ((loop / denominator) * 100).toFixed(2) + '%';
        nodes.streamsLabel.textContent = 'ctx ' + Math.round((ctxShown / denominator) * 100)
            + '% · hist ' + Math.round((histOnly / denominator) * 100)
            + '% · loop ' + Math.round((loop / denominator) * 100) + '%';
        nodes.streamsLabel.title = 'prefix (system prompt + tools) ' + groupDigits(prefix)
            + ' B · your context ' + groupDigits(ctxShown) + ' B · chat history '
            + groupDigits(histOnly) + ' B · tool loop ' + groupDigits(loop) + ' B ('
            + (Number(detail.loop_messages) || 0) + ' msg)';

        // ONE point per request: the same request is published more than once
        // (estimate first, then Ollama's REAL count, then the answer's totals),
        // and a repeat must update its point, not add a fake step.
        var seq = Number(detail.seq) || 0;
        var point = isReal ? realTokens : tokens;
        if (seq && seq === lastSeq && history.length) {
            history[history.length - 1] = point;
        } else {
            history.push(point);
        }
        lastSeq = seq;
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
        nodes.tokens.textContent = 'measuring your next request…';
        nodes.tokens.title = 'As soon as the agent is ready, Tlamatini rebuilds the '
            + 'request your next message will send and asks Ollama how many tokens '
            + 'it really is.';
        nodes.zoneWord.textContent = 'IDLE';
        nodes.titleSub.textContent = 'sent to the model';
        nodes.streamsLabel.textContent = 'prefix · context · history · loop';
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

    // ── ASK FOR A FRESH READING (Angela, 2026-09-28) ─────────────────────
    // "don't stay static but always dynamic". The server rebuilds what the
    // NEXT message will send and asks Ollama for its real count whenever the
    // answer changes. The server already knows about Clear history, Clear
    // context, context loads, reconnects and finished answers; the page adds
    // the two things only it sees: the socket opening, and the toolbar
    // switches that change which tools are bound (Multi-Turn / ACPX /
    // Step-by-Step). Debounced; silent when the socket is not open, because a
    // gauge must never paint the "connection lost" banner.
    var SOCKET_OPEN_EVENT = 'tlm:chat-socket-open';
    var TOGGLES = [
        ['multi-turn-enabled', 'Multi-Turn'],
        ['acpx-enabled', 'ACPX'],
        ['step-by-step-enabled', 'Step-by-Step']
    ];
    var refreshTimer = null;

    function toggleChecked(id) {
        var el = document.getElementById(id);
        return !!(el && el.checked);
    }

    function requestRefresh(reason) {
        if (refreshTimer) window.clearTimeout(refreshTimer);
        refreshTimer = window.setTimeout(function () {
            refreshTimer = null;
            try {
                if (typeof window.isChatSocketOpen !== 'function' || !window.isChatSocketOpen()) return;
                if (typeof window.sendChatSocketMessage !== 'function') return;
                window.sendChatSocketMessage({
                    type: 'context-gauge-refresh',
                    message: 'context-gauge-refresh',
                    reason: reason,
                    multi_turn_enabled: toggleChecked('multi-turn-enabled'),
                    acpx_enabled: toggleChecked('acpx-enabled'),
                    step_by_step_enabled: toggleChecked('step-by-step-enabled')
                });
            } catch (err) {
                if (window.console && window.console.warn) {
                    window.console.warn('[context-gauge] refresh request skipped:', err);
                }
            }
        }, 250);
    }

    function wireToggles() {
        TOGGLES.forEach(function (pair) {
            var el = document.getElementById(pair[0]);
            if (!el) return;
            el.addEventListener('change', function () {
                requestRefresh(pair[1] + (el.checked ? ' on' : ' off'));
            });
        });
    }

    document.addEventListener(SOCKET_OPEN_EVENT, function () {
        requestRefresh('page opened');
    });
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', wireToggles);
    } else {
        wireToggles();
    }
}());
