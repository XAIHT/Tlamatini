/*
 * ═══════════════════════════════════════════════════════════════════
 *   ✦  T L A M A T I N I  ✦   —   "one who knows"
 *
 *   Created by  Angela López Mendoza   ·   @angelahack1
 *   Developer · Architect · Creator of Tlamatini
 * ═══════════════════════════════════════════════════════════════════
 *   Tlamatini Author Banner — do not remove (releases scrub the name automatically)
 *
 * model_capacity.js — the COMPACT MODE box, told to the user
 * (Angela, 2026-10-01; the switch 2026-10-02).
 *
 * The toolbar's "Compact mode" box (#compact-mode-enabled) is the switch in
 * agent/compact_mode.py.  Ticking it REALLY unticks every MCP, tool, agent
 * and skill row (Config ▸ Configure MCPs / Configure Agents / ACPX-Skills)
 * except System-Metrics, Files-Search and Current-Time; the user then ticks
 * back - one by one - only what she needs.  Unticking it ticks them ALL
 * again.  A model that cannot hold EVERYTHING activated locks the box ON
 * (strict): it cannot be unticked until a larger model is chosen.
 *
 * Two sources of truth, both from the server:
 *   - `compact-mode-state` frames (re-dispatched as tlm:compact-mode-state):
 *     the switch {active, strict, locked, model, window_tokens,
 *     everything_tokens, version};
 *   - `detail.capacity` on every context-gauge frame: what the last request
 *     really sent (mode, tools_kept, toggles_version, ...).
 * This module turns them into:
 *   1. the box itself - checked = ON; greyed + 🔒 = locked ON;
 *   2. a dialog that explains, in plain words, what the model can hold and
 *      how to add what she needs - opened once per model per browser session
 *      when a small model locks the box, and on a click of the locked box;
 *   3. a short notice when the switch changes and when Ollama cuts a request;
 *   4. a resync request when a gauge frame carries a newer rows version, so
 *      the Configure dialogs always show the REAL rows.
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
    const STATE_EVENT = 'tlm:compact-mode-state';
    const OVERLAY_ID = 'tlm-compact-overlay';
    const BOX_ID = 'compact-mode-enabled';
    const LABEL_ID = 'compact-mode-toggle';
    const TOAST_ID = 'tlm-capacity-toast';
    const SUPPRESS_PREFIX = 'tlm_compact_dialog_hidden:';
    const SEEN_PREFIX = 'tlm_compact_dialog_seen:';

    const state = {
        sw: null,            // the switch, from compact-mode-state frames
        capacity: null,      // what the last request really sent (gauge frames)
        shownFor: {},        // model -> true (dialog already shown this page)
        lastActive: null,
        knownVersion: 0,
        syncAt: 0,
        cutNoticeAt: 0,
        pending: false,      // a set-compact-mode request is on its way
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

    function sw() {
        return state.sw || {};
    }

    function isLocked() {
        const s = sw();
        return !!(s.active && s.locked);
    }

    // ── The box ────────────────────────────────────────────────────────────
    function titleFor(s) {
        if (s.active && s.locked) {
            return 'Compact mode is locked ON: ' + (s.model || 'this model') + ' reads only ' +
                fmt(s.window_tokens) + ' tokens, and everything activated needs about ' +
                fmt(s.everything_tokens) + '. Tick what you need in Config ▸ Configure MCPs / ' +
                'Configure Agents - the CONTEXT-WINDOW gauge shows what it costs. Click for details.';
        }
        if (s.active) {
            return 'Compact mode is ON: only what you ticked in Config ▸ Configure MCPs / ' +
                'Configure Agents is sent. Untick this box to switch EVERYTHING back on.';
        }
        return 'Compact mode: unticks every MCP, tool, agent and skill except System-Metrics, ' +
            'Files-Search and Current-Time, so you send the model only what you pick. Untick it ' +
            'later to switch everything back on.';
    }

    function paintBox() {
        const box = byId(BOX_ID);
        const label = byId(LABEL_ID);
        if (!box) { return; }
        const s = sw();
        const locked = isLocked();
        box.checked = !!s.active;
        box.disabled = locked || state.pending;
        if (label) {
            label.classList.toggle('compact-locked', locked);
            label.classList.toggle('compact-on', !!s.active);
            label.classList.toggle('toolbar-toggle-disabled', locked || state.pending);
            const text = label.querySelector('span');
            if (text) { text.textContent = locked ? 'Compact mode 🔒' : 'Compact mode'; }
            label.setAttribute('title', titleFor(s));
            label.setAttribute('aria-disabled', locked ? 'true' : 'false');
        }
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

    function onBoxChange() {
        const box = byId(BOX_ID);
        if (!box) { return; }
        const want = !!box.checked;
        if (!want && isLocked()) {
            box.checked = true;
            openDialog(true);
            return;
        }
        const sent = send({ type: 'set-compact-mode', message: 'set-compact-mode', enabled: want });
        if (!sent) {
            box.checked = !want;
            toast('Compact mode was not changed: the connection is not open. Use Reconnect and try again.', 'warn');
            return;
        }
        setPending(true);
    }

    function onLabelClick(event) {
        if (isLocked()) {
            // The box is greyed out: a click explains why instead of doing nothing.
            try { event.preventDefault(); } catch (err) { /* noop */ }
            openDialog(true);
        }
    }

    function wireBox() {
        const box = byId(BOX_ID);
        const label = byId(LABEL_ID);
        if (box && !box.dataset.tlmCompactWired) {
            box.dataset.tlmCompactWired = '1';
            box.addEventListener('change', onBoxChange);
        }
        if (label && !label.dataset.tlmCompactWired) {
            label.dataset.tlmCompactWired = '1';
            label.addEventListener('click', onLabelClick);
        }
        paintBox();
    }

    // ── Toast ──────────────────────────────────────────────────────────────
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

    // ── Dialog ─────────────────────────────────────────────────────────────
    function closeDialog() {
        const overlay = byId(OVERLAY_ID);
        if (!overlay) { return; }
        const box = overlay.querySelector('.tlmcap-dontshow input');
        const model = sw().model || '';
        if (box && model) {
            storageSet(SUPPRESS_PREFIX + model, box.checked ? '1' : null);
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

    function openConfigure(fnName) {
        closeDialog();
        try {
            if (typeof window[fnName] === 'function') {
                // The menu handlers call e.preventDefault() first.
                window[fnName]({ preventDefault: function () {} });
            }
        } catch (err) { /* the dialog itself is optional */ }
    }

    function openDialog(fromUser) {
        if (byId(OVERLAY_ID)) { return; }
        const s = sw();
        const cap = state.capacity || {};
        const model = s.model || cap.model || 'This model';
        const locked = isLocked();

        const overlay = el('div', 'tlmpop-overlay tlmcap-overlay');
        overlay.id = OVERLAY_ID;
        overlay.setAttribute('role', 'dialog');
        overlay.setAttribute('aria-modal', 'true');
        overlay.setAttribute('aria-labelledby', 'tlmcap-title');

        const card = el('div', 'tlmpop-card tlmcap-card');
        const head = el('div', 'tlmpop-head');
        const title = el('span', 'tlmpop-title',
            locked ? 'Compact mode — locked ON for this model' : (s.active ? 'Compact mode is ON' : 'Compact mode'));
        title.id = 'tlmcap-title';
        const x = el('button', 'tlmpop-x', '×');
        x.type = 'button';
        x.setAttribute('aria-label', 'Close');
        x.addEventListener('click', closeDialog);
        head.appendChild(title);
        head.appendChild(x);

        const body = el('div', 'tlmpop-body tlmcap-body');

        const win = Number(s.window_tokens || cap.window_tokens) || 0;
        const every = Number(s.everything_tokens || cap.everything_tokens) || 0;
        const meter = el('div', 'tlmcap-meter');
        const pct = every > 0 ? Math.max(4, Math.min(100, Math.round(win * 100 / every))) : 100;
        const bar = el('div', 'tlmcap-bar');
        const fill = el('div', 'tlmcap-bar-fill');
        fill.style.width = pct + '%';
        bar.appendChild(fill);
        meter.appendChild(bar);
        const legend = el('div', 'tlmcap-legend');
        legend.appendChild(el('span', 'tlmcap-legend-win', model + ' reads ' + fmt(win) + ' tokens'));
        legend.appendChild(el('span', 'tlmcap-legend-full', 'Everything activated ≈ ' + fmt(every)));
        meter.appendChild(legend);

        const lead = el('p', 'tlmpop-msg tlmcap-lead');
        if (locked) {
            lead.textContent = model + ' can read about ' + fmt(win) + ' tokens at a time, and ' +
                'Tlamatini with everything activated needs about ' + fmt(every) + '. Sending it all ' +
                'would make Ollama silently throw most of it away, so Compact mode is locked ON: ' +
                'every MCP, tool, agent and skill was unticked except System-Metrics, Files-Search ' +
                'and Current-Time - and you add back only what you need.';
        } else {
            lead.textContent = 'Compact mode is ON: Tlamatini sends ' + model + ' only what you ' +
                'ticked. Untick the Compact mode box to switch every MCP, tool, agent and skill ' +
                'back on.';
        }

        const grid = el('div', 'tlmcap-grid');
        const keep = el('div', 'tlmcap-col');
        keep.appendChild(el('div', 'tlmcap-col-title tlmcap-on', 'Sent with your next message'));
        const keepList = el('ul', 'tlmcap-list');
        const kept = (cap.tools_kept || []).filter(function (n) { return !!n; });
        row(keepList, '✓', 'System-Metrics · Files-Search', 'as ticked in Config ▸ Configure MCPs', 'on');
        if (kept.length) {
            row(keepList, '✓', kept.length + ' tool(s) you ticked', kept.slice(0, 8).join(', ') +
                (kept.length > 8 ? ', …' : ''), 'on');
        } else {
            row(keepList, '–', 'No tools', 'tick Current-Time or an agent to add one', 'off');
        }
        row(keepList, '✓', 'Your loaded context and recent chat',
            'fitted to the window (' + fmt(cap.history_kept) + ' of ' + fmt(cap.history_total) + ' recent messages)', 'on');
        keep.appendChild(keepList);

        const how = el('div', 'tlmcap-col');
        how.appendChild(el('div', 'tlmcap-col-title tlmcap-off', 'Add what you need'));
        const howList = el('ul', 'tlmcap-list');
        row(howList, '1', 'Config ▸ Configure Agents', 'tick an agent (for example PDFer or ESPHomer) - its tool is ticked with it', 'off');
        row(howList, '2', 'Config ▸ Configure MCPs', 'tick or untick tools, System-Metrics and Files-Search', 'off');
        row(howList, '3', 'Watch the CONTEXT-WINDOW gauge', 'green fits; red or past 100% means not everything will work', 'off');
        const ext = cap.external_mcps_paused || [];
        row(howList, '⏸', 'External MCPs (' + ext.length + ' paused)',
            ext.length ? ext.join(', ') + ' - restored when Compact mode is switched off' : 'none were active', 'off');
        how.appendChild(howList);
        grid.appendChild(keep);
        grid.appendChild(how);

        const back = el('p', 'tlmpop-sub tlmcap-back');
        back.textContent = locked
            ? 'The lock lifts on its own when you choose a model that can hold everything (for example a :cloud model) in Config ▸ Models.'
            : 'Your choices are kept exactly as you leave them until you untick Compact mode.';

        const src = el('p', 'tlmcap-source');
        src.textContent = 'Window source: ' + (cap.window_source || 'measured') +
            '. Reserved for the answer: ' + fmt(cap.reserve_tokens) + ' tokens.';

        const dont = el('label', 'tlmcap-dontshow');
        const dontBox = document.createElement('input');
        dontBox.type = 'checkbox';
        dontBox.checked = storageGet(SUPPRESS_PREFIX + (s.model || '')) === '1';
        dont.appendChild(dontBox);
        dont.appendChild(el('span', null, ' Don\'t open this automatically again for ' + model));

        body.appendChild(meter);
        body.appendChild(lead);
        body.appendChild(grid);
        body.appendChild(back);
        body.appendChild(src);
        body.appendChild(dont);

        const foot = el('div', 'tlmpop-foot');
        const agents = el('button', 'tlmpop-btn tlmcap-agents', 'Open Configure Agents');
        agents.type = 'button';
        agents.addEventListener('click', function () { openConfigure('OpenAgentsDialog'); });
        const models = el('button', 'tlmpop-btn tlmcap-models', 'Open Config ▸ Models');
        models.type = 'button';
        models.addEventListener('click', function () { openConfigure('OpenConfigModelsDialog'); });
        const ok = el('button', 'tlmpop-btn tlmpop-btn-primary tlmcap-ok', 'OK');
        ok.type = 'button';
        ok.addEventListener('click', closeDialog);
        foot.appendChild(agents);
        foot.appendChild(models);
        foot.appendChild(ok);

        card.appendChild(head);
        card.appendChild(body);
        card.appendChild(foot);
        overlay.appendChild(card);
        // dialog_policy.js: Escape invokes the dialog's own dismiss path.
        overlay.tlmDismiss = closeDialog;
        document.body.appendChild(overlay);
        try { ok.focus(); } catch (err) { /* noop */ }
        if (!fromUser) {
            try { window.console.info('[compact-mode] dialog shown for', model); } catch (err) { /* noop */ }
        }
    }

    function maybeOpenForModel(s) {
        if (!(s.active && s.locked)) { return; }
        const model = s.model || '';
        if (!model || state.shownFor[model]) { return; }
        state.shownFor[model] = true;
        if (storageGet(SUPPRESS_PREFIX + model) === '1' || sessionGet(SEEN_PREFIX + model) === '1') {
            return;
        }
        sessionSet(SEEN_PREFIX + model, '1');
        openDialog(false);
    }

    // ── The switch ─────────────────────────────────────────────────────────
    function applySwitch(s, kind) {
        if (!s || typeof s !== 'object') { return; }
        const prevActive = state.lastActive;
        state.sw = s;
        state.lastActive = !!s.active;
        if (Number(s.version) > state.knownVersion) { state.knownVersion = Number(s.version); }
        setPending(false);
        document.documentElement.setAttribute('data-tlm-compact',
            s.active ? (s.locked ? 'locked' : 'on') : 'off');
        if (prevActive !== null && prevActive !== !!s.active) {
            if (s.active) {
                toast('Compact mode is ON - only what you tick in Config ▸ Configure MCPs / ' +
                      'Configure Agents is sent.', 'warn');
            } else {
                toast('Compact mode is OFF - every MCP, tool, agent and skill is back.', 'ok');
            }
        }
        if (kind === 'refused' && s.locked) {
            toast('Compact mode stays ON: ' + (s.model || 'this model') + ' cannot hold everything activated.', 'warn');
        }
        maybeOpenForModel(s);
    }

    function onState(event) {
        try {
            const data = event && event.detail ? event.detail : null;
            if (data && data.state) { applySwitch(data.state, data.kind || 'state'); }
        } catch (err) {
            try { window.console.warn('[compact-mode] state skipped:', err); } catch (e) { /* noop */ }
        }
    }

    // ── The verdict on every gauge frame ───────────────────────────────────
    function applyCapacity(cap, frame) {
        if (!cap || typeof cap !== 'object') { return; }
        state.capacity = cap;
        document.documentElement.setAttribute('data-tlm-capacity', cap.mode || 'full');
        // A frame can be newer than the switch this tab knows (another tab, or
        // the automatic switch): ask for the switch and the REAL rows.
        const version = Number(cap.toggles_version) || 0;
        const s = sw();
        const stale = version > state.knownVersion ||
            (typeof cap.compact_active === 'boolean' && state.sw && cap.compact_active !== !!s.active) ||
            (typeof cap.strict === 'boolean' && state.sw && cap.strict !== !!s.strict);
        if (stale && Date.now() - state.syncAt > 1500) {
            state.syncAt = Date.now();
            if (version > state.knownVersion) { state.knownVersion = version; }
            send({ type: 'compact-mode-sync', message: 'compact-mode-sync' });
        }
        if (frame && frame.truncated && Date.now() - state.cutNoticeAt > 20000) {
            state.cutNoticeAt = Date.now();
            toast('CONTEXT-WINDOW exceeded: ' + (cap.model || 'the model') + ' read only ' +
                  fmt(frame.window_real || frame.tokens_real) + ' of about ' +
                  fmt(frame.tokens_sent_estimate || frame.tokens_estimated) +
                  ' tokens sent. Untick agents or tools so the request fits.', 'warn');
        }
    }

    function onFrame(event) {
        try {
            const frame = event && event.detail ? event.detail : null;
            if (frame && frame.capacity) { applyCapacity(frame.capacity, frame); }
        } catch (err) {
            try { window.console.warn('[compact-mode] frame skipped:', err); } catch (e) { /* noop */ }
        }
    }

    document.addEventListener(EVENT_NAME, onFrame);
    document.addEventListener(STATE_EVENT, onState);
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', wireBox);
    } else {
        wireBox();
    }

    window.TlmModelCapacity = {
        isCompact: function () { return !!sw().active; },
        isLocked: function () { return isLocked(); },
        capacity: function () { return state.capacity ? JSON.parse(JSON.stringify(state.capacity)) : null; },
        state: function () { return state.sw ? JSON.parse(JSON.stringify(state.sw)) : null; },
        open: function () { openDialog(true); }
    };
}());
