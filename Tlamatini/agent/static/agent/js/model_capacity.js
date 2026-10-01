/*
 * ═══════════════════════════════════════════════════════════════════
 *   ✦  T L A M A T I N I  ✦   —   "one who knows"
 *
 *   Created by  Angela López Mendoza   ·   @angelahack1
 *   Developer · Architect · Creator of Tlamatini
 * ═══════════════════════════════════════════════════════════════════
 *   Tlamatini Author Banner — do not remove (releases scrub the name automatically)
 *
 * model_capacity.js — COMPACT MODE, told to the user (Angela, 2026-10-01).
 *
 * The backend fits every request to the model's REAL window
 * (agent/context_fitter.py).  When the configured model cannot hold
 * Tlamatini's complete request she runs in COMPACT mode: only
 * System-Metrics, Files-Search and Current-Time stay active, ACPX is off
 * and the user's External MCPs are paused.  That verdict rides on EVERY
 * context-gauge frame as `detail.capacity`; this module turns it into:
 *
 *   1. a dialog that explains, in plain words, what the model can hold and
 *      what is paused — shown ONCE per model per page, never for a model the
 *      user asked us to stop explaining (localStorage, per model);
 *   2. a badge in the toolbar while compact (click = the dialog again);
 *   3. the ACPX switch LOCKED off while compact, restored exactly as the
 *      user left it when a model that can hold everything comes back;
 *   4. a short notice when full mode returns, and one when Ollama is caught
 *      cutting a request.
 *
 * Contracts: self-contained IIFE, NO cross-file globals (exports only
 * window.TlmModelCapacity); every step is fail-open — a broken notice must
 * never cost the user the chat; the dialog follows dialog_policy.js (✕,
 * Escape and the buttons close it, an outside click does not) and wears the
 * shared .tlmpop-* identity from dialog_theme.css.
 */
(function () {
    'use strict';

    const EVENT_NAME = 'tlm:context-gauge';
    const OVERLAY_ID = 'tlm-compact-overlay';
    const BADGE_ID = 'compact-mode-badge';
    const TOAST_ID = 'tlm-capacity-toast';
    const SUPPRESS_PREFIX = 'tlm_compact_dialog_hidden:';
    const SEEN_PREFIX = 'tlm_compact_dialog_seen:';

    const state = {
        capacity: null,          // latest verdict from the backend
        shownFor: {},            // model -> true (dialog already shown this page)
        acpxSaved: null,         // the ACPX checkbox state before we locked it
        acpxTimer: null,
        lastMode: null,
        lastModel: null,
        cutNoticeAt: 0
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

    function shortTokens(n) {
        const v = Number(n) || 0;
        if (v >= 1000000) { return (Math.round(v / 100000) / 10) + 'M'; }
        if (v >= 1000) { return Math.round(v / 1024) + 'K'; }
        return String(v);
    }

    function el(tag, cls, text) {
        const node = document.createElement(tag);
        if (cls) { node.className = cls; }
        if (text !== undefined && text !== null) { node.textContent = String(text); }
        return node;
    }

    function storageGet(key) {
        try { return window.localStorage.getItem(key); } catch (err) { return null; }
    }

    function storageSet(key, value) {
        try {
            if (value === null) { window.localStorage.removeItem(key); }
            else { window.localStorage.setItem(key, value); }
        } catch (err) { /* private window / blocked storage: fine */ }
    }

    function sessionGet(key) {
        try { return window.sessionStorage.getItem(key); } catch (err) { return null; }
    }

    function sessionSet(key, value) {
        try { window.sessionStorage.setItem(key, value); } catch (err) { /* blocked storage: fine */ }
    }

    function relayout() {
        try { window.dispatchEvent(new Event('resize')); } catch (err) { /* noop */ }
    }

    // ── ACPX lock ────────────────────────────────────────────────────────
    function acpxBox() { return byId('acpx-enabled'); }
    function acpxLabel() { return byId('acpx-toggle'); }

    function lockAcpx(cap) {
        const box = acpxBox();
        const label = acpxLabel();
        if (!box) { return; }
        if (state.acpxSaved === null) {
            state.acpxSaved = { checked: !!box.checked, title: label ? (label.getAttribute('title') || '') : '' };
        }
        box.checked = false;
        box.disabled = true;
        if (label) {
            label.classList.add('toolbar-toggle-disabled', 'compact-locked');
            label.setAttribute('title', 'ACPX is off in Compact mode: ' + (cap.model || 'this model') +
                ' cannot hold it. Choose a larger model in Config ▸ Models to use ACPX.');
        }
        if (!state.acpxTimer) {
            // A catalog prompt can tick boxes programmatically (no change
            // event fires); keep ACPX honest while the model is small.
            state.acpxTimer = window.setInterval(function () {
                const b = acpxBox();
                if (b && b.checked && state.capacity && state.capacity.mode === 'compact') {
                    b.checked = false;
                }
            }, 750);
        }
    }

    function unlockAcpx() {
        const box = acpxBox();
        const label = acpxLabel();
        if (state.acpxTimer) {
            window.clearInterval(state.acpxTimer);
            state.acpxTimer = null;
        }
        if (!box || state.acpxSaved === null) { return; }
        box.disabled = false;
        box.checked = !!state.acpxSaved.checked;
        if (label) {
            label.classList.remove('toolbar-toggle-disabled', 'compact-locked');
            if (state.acpxSaved.title) { label.setAttribute('title', state.acpxSaved.title); }
            else { label.removeAttribute('title'); }
        }
        state.acpxSaved = null;
    }

    // ── Badge ────────────────────────────────────────────────────────────
    function ensureBadge() {
        let badge = byId(BADGE_ID);
        if (badge) { return badge; }
        const host = byId('tools-left');
        if (!host) { return null; }
        badge = el('button', 'compact-mode-badge');
        badge.id = BADGE_ID;
        badge.type = 'button';
        badge.hidden = true;
        badge.addEventListener('click', function () {
            if (state.capacity) { openDialog(state.capacity, true); }
        });
        host.appendChild(badge);
        return badge;
    }

    function showBadge(cap) {
        const badge = ensureBadge();
        if (!badge) { return; }
        badge.textContent = '';
        badge.appendChild(el('span', 'compact-mode-badge-dot'));
        badge.appendChild(el('span', 'compact-mode-badge-text',
            'Compact mode · ' + (cap.model || 'model') + ' · ' + shortTokens(cap.window_tokens)));
        badge.setAttribute('title', 'This model reads ' + fmt(cap.window_tokens) +
            ' tokens at a time, so Tlamatini runs with System-Metrics, Files-Search and ' +
            'Current-Time only. Click for details.');
        badge.setAttribute('aria-label', 'Compact mode is on. Click for details.');
        if (badge.hidden) {
            badge.hidden = false;
            relayout();
        }
    }

    function hideBadge() {
        const badge = byId(BADGE_ID);
        if (badge && !badge.hidden) {
            badge.hidden = true;
            relayout();
        }
    }

    // ── Toast ────────────────────────────────────────────────────────────
    function toast(text, tone) {
        try {
            const old = byId(TOAST_ID);
            if (old && old.parentNode) { old.parentNode.removeChild(old); }
            const t = el('div', 'tlm-capacity-toast' + (tone ? ' tlm-capacity-toast-' + tone : ''), text);
            t.id = TOAST_ID;
            t.setAttribute('role', 'status');
            document.body.appendChild(t);
            window.setTimeout(function () { t.classList.add('is-leaving'); }, 6500);
            window.setTimeout(function () { if (t.parentNode) { t.parentNode.removeChild(t); } }, 7200);
        } catch (err) { /* a notice must never break the page */ }
    }

    // ── Dialog ───────────────────────────────────────────────────────────
    function closeDialog() {
        const overlay = byId(OVERLAY_ID);
        if (!overlay) { return; }
        const box = overlay.querySelector('.tlmcap-dontshow input');
        if (box && state.capacity && state.capacity.model) {
            storageSet(SUPPRESS_PREFIX + state.capacity.model, box.checked ? '1' : null);
        }
        if (overlay.parentNode) { overlay.parentNode.removeChild(overlay); }
        try {
            const input = byId('chat-message-input');
            if (input && !input.disabled) { input.focus(); }
        } catch (err) { /* noop */ }
    }

    function row(list, icon, name, detail, tone) {
        const li = el('li', 'tlmcap-row tlmcap-' + tone);
        li.appendChild(el('span', 'tlmcap-icon', icon));
        const copy = el('span', 'tlmcap-copy');
        copy.appendChild(el('strong', 'tlmcap-name', name));
        if (detail) { copy.appendChild(el('span', 'tlmcap-detail', detail)); }
        li.appendChild(copy);
        list.appendChild(li);
    }

    function openDialog(cap, fromBadge) {
        if (!cap || byId(OVERLAY_ID)) { return; }
        const model = cap.model || 'This model';

        const overlay = el('div', 'tlmpop-overlay tlmcap-overlay');
        overlay.id = OVERLAY_ID;
        overlay.setAttribute('role', 'dialog');
        overlay.setAttribute('aria-modal', 'true');
        overlay.setAttribute('aria-labelledby', 'tlmcap-title');

        const card = el('div', 'tlmpop-card tlmcap-card');
        const head = el('div', 'tlmpop-head');
        const title = el('span', 'tlmpop-title', 'Compact mode — a small model is selected');
        title.id = 'tlmcap-title';
        const x = el('button', 'tlmpop-x', '×');
        x.type = 'button';
        x.setAttribute('aria-label', 'Close');
        x.addEventListener('click', closeDialog);
        head.appendChild(title);
        head.appendChild(x);

        const body = el('div', 'tlmpop-body tlmcap-body');

        const meter = el('div', 'tlmcap-meter');
        const full = Number(cap.full_tokens_estimate) || 0;
        const win = Number(cap.window_tokens) || 0;
        const pct = full > 0 ? Math.max(4, Math.min(100, Math.round(win * 100 / full))) : 100;
        const bar = el('div', 'tlmcap-bar');
        const fill = el('div', 'tlmcap-bar-fill');
        fill.style.width = pct + '%';
        bar.appendChild(fill);
        meter.appendChild(bar);
        const legend = el('div', 'tlmcap-legend');
        legend.appendChild(el('span', 'tlmcap-legend-win', model + ' reads ' + fmt(win) + ' tokens'));
        legend.appendChild(el('span', 'tlmcap-legend-full', 'Complete request ≈ ' + fmt(full)));
        meter.appendChild(legend);

        const lead = el('p', 'tlmpop-msg tlmcap-lead');
        lead.textContent = model + ' can read about ' + fmt(win) + ' tokens at a time, and ' +
            'Tlamatini\'s complete request needs about ' + fmt(full) + '. Sending it anyway would ' +
            'make Ollama silently throw most of it away, so Tlamatini works in Compact mode ' +
            'to keep every answer correct.';

        const grid = el('div', 'tlmcap-grid');
        const keep = el('div', 'tlmcap-col');
        keep.appendChild(el('div', 'tlmcap-col-title tlmcap-on', 'Still active'));
        const keepList = el('ul', 'tlmcap-list');
        row(keepList, '✓', 'System-Metrics', 'live CPU, memory and disk in your questions', 'on');
        row(keepList, '✓', 'Files-Search', 'file-search results in your questions', 'on');
        const keptTools = (cap.tools_kept || []).length;
        row(keepList, keptTools ? '✓' : '–', 'Current-Time',
            keptTools ? 'the only tool bound' : 'switched off in Config ▸ Configure MCPs', keptTools ? 'on' : 'off');
        row(keepList, '✓', 'Your loaded context and recent chat',
            'fitted to the window (' + fmt(cap.history_kept) + ' of ' + fmt(cap.history_total) + ' recent messages)', 'on');
        keep.appendChild(keepList);

        const paused = el('div', 'tlmcap-col');
        paused.appendChild(el('div', 'tlmcap-col-title tlmcap-off', 'Paused for this model'));
        const pausedList = el('ul', 'tlmcap-list');
        row(pausedList, '⏸', 'Agents (' + fmt(cap.agents_paused) + ')', 'files, commands, browser, messaging…', 'off');
        row(pausedList, '⏸', 'ACPX', 'locked off — the switch is greyed out', 'off');
        const ext = cap.external_mcps_paused || [];
        row(pausedList, '⏸', 'External MCPs (' + ext.length + ' active)',
            ext.length ? ext.join(', ') + ' — your selection is kept' : 'none active', 'off');
        const promptKb = Math.round((Number(cap.prompt_chars) || 0) / 1024);
        const promptFullKb = Math.round((Number(cap.prompt_full_chars) || 0) / 1024);
        row(pausedList, '⏸', 'Long rules', 'core rules kept (' + promptKb + ' of ' + promptFullKb + ' KB)', 'off');
        paused.appendChild(pausedList);
        grid.appendChild(keep);
        grid.appendChild(paused);

        const back = el('p', 'tlmpop-sub tlmcap-back');
        back.textContent = 'Everything comes back on its own when you choose a larger model ' +
            '(for example a :cloud model) in Config ▸ Models.';

        const src = el('p', 'tlmcap-source');
        src.textContent = 'Window source: ' + (cap.window_source || 'unknown') +
            '. Reserved for the answer: ' + fmt(cap.reserve_tokens) + ' tokens.';

        const dont = el('label', 'tlmcap-dontshow');
        const dontBox = document.createElement('input');
        dontBox.type = 'checkbox';
        dontBox.checked = storageGet(SUPPRESS_PREFIX + (cap.model || '')) === '1';
        dont.appendChild(dontBox);
        dont.appendChild(el('span', null, ' Don\'t open this automatically again for ' + model));

        body.appendChild(meter);
        body.appendChild(lead);
        body.appendChild(grid);
        body.appendChild(back);
        body.appendChild(src);
        body.appendChild(dont);

        const foot = el('div', 'tlmpop-foot');
        const models = el('button', 'tlmpop-btn tlmcap-models', 'Open Config ▸ Models');
        models.type = 'button';
        models.addEventListener('click', function () {
            closeDialog();
            try {
                if (typeof window.OpenConfigModelsDialog === 'function') {
                    // The menu handler calls e.preventDefault() first.
                    window.OpenConfigModelsDialog({ preventDefault: function () {} });
                }
            } catch (err) { /* the dialog itself is optional */ }
        });
        const ok = el('button', 'tlmpop-btn tlmpop-btn-primary tlmcap-ok', 'Continue in Compact mode');
        ok.type = 'button';
        ok.addEventListener('click', closeDialog);
        foot.appendChild(models);
        foot.appendChild(ok);

        card.appendChild(head);
        card.appendChild(body);
        card.appendChild(foot);
        overlay.appendChild(card);
        // dialog_policy.js: Escape invokes the dialog's own dismiss path.
        overlay.tlmDismiss = closeDialog;
        document.body.appendChild(overlay);
        state.shownFor[cap.model || ''] = true;
        try { ok.focus(); } catch (err) { /* noop */ }
        if (!fromBadge) {
            try { window.console.info('[compact-mode] dialog shown for', cap.model); } catch (err) { /* noop */ }
        }
    }

    // ── The verdict ──────────────────────────────────────────────────────
    function apply(cap, frame) {
        if (!cap || typeof cap !== 'object') { return; }
        const prevMode = state.lastMode;
        const prevModel = state.lastModel;
        state.capacity = cap;
        state.lastMode = cap.mode;
        state.lastModel = cap.model;
        document.documentElement.setAttribute('data-tlm-capacity', cap.mode || 'full');

        if (cap.mode === 'compact') {
            showBadge(cap);
            lockAcpx(cap);
            const model = cap.model || '';
            const suppressed = storageGet(SUPPRESS_PREFIX + model) === '1';
            // Once per model per BROWSER SESSION: a reload must not nag again.
            const seenThisSession = sessionGet(SEEN_PREFIX + model) === '1';
            if (!state.shownFor[model] && !suppressed && !seenThisSession) {
                openDialog(cap, false);
                sessionSet(SEEN_PREFIX + model, '1');
            } else if ((suppressed || seenThisSession) && prevMode !== 'compact' && !state.shownFor[model]) {
                toast('Compact mode: ' + (model || 'this model') + ' reads ' + fmt(cap.window_tokens) +
                      ' tokens — System-Metrics, Files-Search and Current-Time only.', 'warn');
                state.shownFor[model] = true;
            }
        } else {
            hideBadge();
            unlockAcpx();
            const overlay = byId(OVERLAY_ID);
            if (overlay && overlay.parentNode) { overlay.parentNode.removeChild(overlay); }
            if (prevMode === 'compact') {
                toast('Full mode restored: ' + (cap.model || prevModel || 'this model') +
                      ' holds Tlamatini\'s complete request — every agent, ACPX and External MCP is back.', 'ok');
            }
        }

        if (frame && frame.truncated && Date.now() - state.cutNoticeAt > 20000) {
            state.cutNoticeAt = Date.now();
            toast('Ollama cut a request to ' + (cap.model || 'the model') + ' at ' +
                  fmt(frame.tokens_real) + ' tokens. Tlamatini learned the real window and re-fits ' +
                  'every request to it.', 'warn');
        }
    }

    function onFrame(event) {
        try {
            const frame = event && event.detail ? event.detail : null;
            if (frame && frame.capacity) { apply(frame.capacity, frame); }
        } catch (err) {
            try { window.console.warn('[compact-mode] frame skipped:', err); } catch (e) { /* noop */ }
        }
    }

    document.addEventListener(EVENT_NAME, onFrame);

    window.TlmModelCapacity = {
        isCompact: function () { return !!(state.capacity && state.capacity.mode === 'compact'); },
        capacity: function () { return state.capacity ? JSON.parse(JSON.stringify(state.capacity)) : null; },
        open: function () { if (state.capacity) { openDialog(state.capacity, true); } }
    };
}());
