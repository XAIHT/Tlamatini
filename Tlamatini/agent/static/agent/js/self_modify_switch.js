/*
 * ═══════════════════════════════════════════════════════════════════
 *   ✦  T L A M A T I N I  ✦   —   "one who knows"
 *
 *   Created by  Angela López Mendoza   ·   @angelahack1
 *   Developer · Architect · Creator of Tlamatini
 * ═══════════════════════════════════════════════════════════════════
 *   Tlamatini Author Banner — do not remove (releases scrub the name automatically)
 *
 * self_modify_switch.js — the SELF-MODIFY box (Angela, 2026-10-03).
 *
 * The toolbar's "Self-modify" box (#self-modify-enabled) is the switch in
 * agent/compact_mode.py.  ON: Tlamatini's self-knowledge (Tlamatini.md, ~28K
 * tokens) goes with every request, so she can read, change and rebuild her
 * own source.  OFF: it is not sent - and she will not touch her own code.
 *
 * The box is rendered ONLY in a build that can self-modify (always from
 * source; a frozen build only with `build.py --self-modify`) - in any other
 * build neither the box nor this script is on the page.
 *
 * It can be ticked if and only if the model can hold the self-knowledge on
 * top of the request: otherwise the box is greyed, unticked and 🔒, and a
 * click explains why.  It unlocks by itself when a larger model is chosen.
 *
 * Two sources of truth, both from the server:
 *   - `compact-mode-state` frames (tlm:compact-mode-state): the switch -
 *     self_modify (the user's choice), self_modify_fits, self_modify_locked,
 *     self_modify_tokens, self_modify_need_tokens, model, window_tokens;
 *   - `detail.capacity.self_modify` on every context-gauge frame: what the
 *     last request really did.
 *
 * Contracts: self-contained IIFE, NO cross-file globals (exports only
 * window.TlmSelfModify); every step is fail-open - a broken notice must never
 * cost the user the chat.  The explanation uses tlmAlert (dialog_policy.js).
 */
(function () {
    'use strict';

    const GAUGE_EVENT = 'tlm:context-gauge';
    const STATE_EVENT = 'tlm:compact-mode-state';
    const BOX_ID = 'self-modify-enabled';
    const LABEL_ID = 'self-modify-toggle';
    const TOAST_ID = 'tlm-selfmod-toast';

    const state = {
        sw: null,          // the switch, from compact-mode-state frames
        cap: null,         // capacity.self_modify of the last gauge frame
        lastActive: null,
        pending: false,
        pendingTimer: null
    };

    function byId(id) {
        return document.getElementById(id);
    }

    function fmt(n) {
        const v = Number(n) || 0;
        try {
            return v.toLocaleString('en-US');
        } catch (err) {
            return String(v);
        }
    }

    function send(payload) {
        try {
            if (typeof window.isChatSocketOpen === 'function' && !window.isChatSocketOpen()) { return false; }
            if (typeof window.sendChatSocketMessage !== 'function') { return false; }
            window.sendChatSocketMessage(payload);
            return true;
        } catch (err) {
            return false;
        }
    }

    // ── What the box shows ────────────────────────────────────────────────────
    function view() {
        const s = state.sw || {};
        const cap = state.cap || {};
        const wanted = typeof s.self_modify === 'boolean' ? s.self_modify
            : (typeof cap.wanted === 'boolean' ? cap.wanted : true);
        let fits = null;
        if (typeof cap.fits === 'boolean') { fits = cap.fits; }
        if (typeof s.self_modify_fits === 'boolean') { fits = s.self_modify_fits; }
        return {
            wanted: !!wanted,
            fits: fits,
            locked: fits === false,
            active: !!wanted && fits !== false,
            model: s.model || cap.model || 'This model',
            window: Number(s.window_tokens) || 0,
            tokens: Number(s.self_modify_tokens || cap.tokens) || 0,
            need: Number(s.self_modify_need_tokens || cap.need_tokens) || 0
        };
    }

    function lockedMessage(v) {
        return v.model + ' reads only ' + fmt(v.window) + ' tokens at a time, and your request ' +
            'with Tlamatini\'s self-knowledge needs about ' + fmt(v.need) + ' (the self-knowledge ' +
            'alone is about ' + fmt(v.tokens) + '). Sending it would make Ollama silently throw part ' +
            'of the request away, so Self-modify is locked OFF.\n\nChoose a larger model in ' +
            'Config ▸ Models (or untick some agents in Config ▸ Configure Agents) and the box ' +
            'unlocks by itself.';
    }

    function titleFor(v) {
        if (v.locked) {
            return 'Self-modify is locked OFF: ' + v.model + ' cannot hold Tlamatini\'s self-knowledge ' +
                '(about ' + fmt(v.tokens) + ' tokens) on top of your request. Click for details.';
        }
        if (v.active) {
            return 'Self-modify is ON: Tlamatini\'s self-knowledge' +
                (v.tokens ? ' (about ' + fmt(v.tokens) + ' tokens)' : '') +
                ' goes with every request, so she can read, change and rebuild herself. ' +
                'Untick to save those tokens.';
        }
        return 'Self-modify is OFF: Tlamatini\'s self-knowledge is not sent, and she will not touch ' +
            'her own source code. Tick to switch it on.';
    }

    function paintBox() {
        const box = byId(BOX_ID);
        const label = byId(LABEL_ID);
        if (!box) { return; }
        const v = view();
        box.checked = v.active;
        box.disabled = v.locked || state.pending;
        if (label) {
            label.classList.toggle('compact-locked', v.locked);
            label.classList.toggle('compact-on', v.active);
            label.classList.toggle('toolbar-toggle-disabled', v.locked || state.pending);
            const text = label.querySelector('span');
            if (text) { text.textContent = v.locked ? 'Self-modify 🔒' : 'Self-modify'; }
            label.setAttribute('title', titleFor(v));
            label.setAttribute('aria-disabled', v.locked ? 'true' : 'false');
        }
        document.documentElement.setAttribute('data-tlm-self-modify',
            v.locked ? 'locked' : (v.active ? 'on' : 'off'));
    }

    function setPending(on) {
        state.pending = !!on;
        if (state.pendingTimer) {
            window.clearTimeout(state.pendingTimer);
            state.pendingTimer = null;
        }
        if (on) {
            // Never leave the box greyed out if the answer is lost.
            state.pendingTimer = window.setTimeout(function () { setPending(false); }, 8000);
        }
        paintBox();
    }

    function toast(text, tone) {
        try {
            const old = byId(TOAST_ID);
            if (old && old.parentNode) { old.parentNode.removeChild(old); }
            const t = document.createElement('div');
            t.className = 'tlm-capacity-toast' + (tone ? ' tlm-capacity-toast-' + tone : '');
            t.id = TOAST_ID;
            t.setAttribute('role', 'status');
            t.textContent = text;
            document.body.appendChild(t);
            window.setTimeout(function () { t.classList.add('is-leaving'); }, 6500);
            window.setTimeout(function () { if (t.parentNode) { t.parentNode.removeChild(t); } }, 7200);
        } catch (err) { /* a notice must never break the page */ }
    }

    function explain() {
        const v = view();
        const text = lockedMessage(v);
        try {
            if (typeof window.tlmAlert === 'function') {
                window.tlmAlert(text, 'Self-modify — locked OFF for this model');
                return;
            }
        } catch (err) { /* fall through */ }
        toast(text, 'warn');
    }

    function onBoxChange() {
        const box = byId(BOX_ID);
        if (!box) { return; }
        const want = !!box.checked;
        if (want && view().locked) {
            box.checked = false;
            explain();
            return;
        }
        const sent = send({ type: 'set-self-modify', message: 'set-self-modify', enabled: want });
        if (!sent) {
            box.checked = !want;
            toast('Self-modify was not changed: the connection is not open. Use Reconnect and try again.', 'warn');
            return;
        }
        setPending(true);
    }

    function onLabelClick(event) {
        if (view().locked) {
            // The box is greyed out: a click explains why instead of doing nothing.
            try { event.preventDefault(); } catch (err) { /* noop */ }
            explain();
        }
    }

    function wireBox() {
        const box = byId(BOX_ID);
        const label = byId(LABEL_ID);
        if (box && !box.dataset.tlmSelfModWired) {
            box.dataset.tlmSelfModWired = '1';
            box.addEventListener('change', onBoxChange);
        }
        if (label && !label.dataset.tlmSelfModWired) {
            label.dataset.tlmSelfModWired = '1';
            label.addEventListener('click', onLabelClick);
        }
        paintBox();
    }

    function announce() {
        const v = view();
        // No verdict yet: nothing has changed - the page is only loading.
        if (v.fits === null) { return; }
        if (state.lastActive !== null && state.lastActive !== v.active) {
            if (v.active) {
                toast('Self-modify is ON - Tlamatini\'s self-knowledge goes with every request.', 'ok');
            } else if (v.locked) {
                toast('Self-modify is locked OFF - ' + v.model + ' cannot hold Tlamatini\'s self-knowledge.', 'warn');
            } else {
                toast('Self-modify is OFF - Tlamatini\'s self-knowledge is no longer sent.', 'ok');
            }
        }
        state.lastActive = v.active;
    }

    // ── The switch ────────────────────────────────────────────────────────────
    function onState(event) {
        try {
            const data = event && event.detail ? event.detail : null;
            if (!data || !data.state || typeof data.state !== 'object') { return; }
            state.sw = data.state;
            setPending(false);
            announce();
        } catch (err) {
            try { window.console.warn('[self-modify] state skipped:', err); } catch (e) { /* noop */ }
        }
    }

    // ── The verdict on every gauge frame ──────────────────────────────────────
    function onFrame(event) {
        try {
            const frame = event && event.detail ? event.detail : null;
            const cap = frame && frame.capacity ? frame.capacity.self_modify : null;
            if (!cap || typeof cap !== 'object') { return; }
            state.cap = cap;
            if (state.sw && typeof cap.fits === 'boolean') {
                // The newest verdict wins until the switch frame catches up.
                state.sw.self_modify_fits = cap.fits;
            }
            paintBox();
            announce();
        } catch (err) {
            try { window.console.warn('[self-modify] frame skipped:', err); } catch (e) { /* noop */ }
        }
    }

    document.addEventListener(GAUGE_EVENT, onFrame);
    document.addEventListener(STATE_EVENT, onState);
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', wireBox);
    } else {
        wireBox();
    }

    window.TlmSelfModify = {
        isOn: function () { return view().active; },
        isLocked: function () { return view().locked; },
        view: function () { return JSON.parse(JSON.stringify(view())); }
    };
}());
