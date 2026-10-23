/* Tlamatini Author Banner — Angela López Mendoza */
/* Terminater dock — the Terminals area.

   ONE self-contained module that three pages mount (chat, Agentic Control Panel,
   Prompt Flow Panel).  It owns: the tab strip, the type bar (CMD / PowerShell),
   the xterm.js panes, tiling, the hand-over / hung / warning overlays and the
   WebSocket to the hub (`ws/terminals/`).  The terminals themselves live on the
   SERVER, so closing or reloading a page never kills a shell, and Tlamatini can
   raise / type into / kill them whether or not this page is open.

   A host element opts in with  data-tlm-terminals-host="chat|acp|pfp".  Any
   element with  data-tlm-terminals-toggle  becomes a "Terminals" check item.

   Contracts (do NOT weaken):
   * keystrokes the user types are sent in order and are NEVER swallowed here —
     the server decides (it drops them only while Tlamatini is typing, and tells
     the user how to take over: Esc);
   * the dock never kills a terminal without the user's action or Tlamatini's
     request; hiding the dock keeps every shell alive;
   * every failure is fail-open: a missing renderer or a dead socket shows a
     message in the dock, it never breaks the host page.                       */
(() => {
    'use strict';
    if (window.TlamatiniTerminals) return;

    const KINDS = {
        cmd: { label: 'CMD', short: 'CMD' },
        powershell: { label: 'PowerShell', short: 'PS' },
        pwsh: { label: 'PowerShell 7', short: 'PS7' },
    };
    const LAYOUTS = ['tabs', 'tile', 'tile-h', 'tile-v', 'grid'];
    const AREAS = ['dock', 'full'];
    const LAYOUT_TEXT = { tabs: 'Tabs', tile: 'Tile', 'tile-h': 'Side by side', 'tile-v': 'Stacked', grid: 'Grid' };
    const STATE_TEXT = {
        starting: 'starting', prompt: 'ready', typing: 'Tlamatini is typing', awaiting_user: 'your turn',
        running: 'running', exited: 'exited', closed: 'closed',
    };
    const THEME = {
        background: '#0d1219', foreground: '#d6e2ee', cursor: '#55bbaa', cursorAccent: '#0d1219',
        selectionBackground: '#2f6f69aa', black: '#1b222d', red: '#ff7b86', green: '#5fe0a0', yellow: '#f2c15b',
        blue: '#6cb2ff', magenta: '#d99bff', cyan: '#5fd6e6', white: '#d6e2ee', brightBlack: '#6f8197',
        brightRed: '#ff9da9', brightGreen: '#8bf0be', brightYellow: '#ffdc8a', brightBlue: '#9ccbff',
        brightMagenta: '#e8bfff', brightCyan: '#9be9f4', brightWhite: '#f4f8fc',
    };
    const MIN_DOCK = 96;
    const RESERVE_FOR_CANVAS = 90;

    const S = {
        inited: false, page: 'chat', host: null, root: null, els: {}, user: 'anon', storeKey: '',
        visible: false, layout: 'tabs', area: 'dock', heightPct: 0, userResized: false,
        terms: new Map(), order: [], active: '', kinds: ['cmd', 'powershell'], max: 12,
        ws: null, conn: 'idle', backoff: 500, reconnectTimer: 0, fatal: 0, hello: false, openPending: 0,
        autoOpened: false, fontSize: 13, error: '', kindPin: '',
    };
    const listeners = new Set();
    let interaction = {};
    function applyInteraction(settings) {
        interaction = settings;
        S.fontSize = settings.terminal_font || 13;
        S.terms.forEach(T => {
            if (T.term) { T.term.options.fontSize = S.fontSize; T.term.options.cursorBlink = settings.cursor_blink !== false; T.term.options.cursorStyle = settings.cursor_style || 'block'; }
        });
        if (S.inited) {
            if (settings.terminal_layout) {
                setLayout(settings.terminal_layout, false);
                if (S.hello) send({ t: 'layout', layout: settings.terminal_layout, show: S.visible });
            }
            if (settings.shell && S.els.kind && S.kinds.includes(settings.shell)) { S.els.kind.value = settings.shell; S.kindPin = settings.shell; }
            scheduleFitAll();
        }
    }
    function narrationPresence() { send({ t: 'narration_presence', visible: !document.hidden && document.hasFocus() }); }

    /* ── tiny helpers ───────────────────────────────────────────────────── */
    const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v));
    function h(tag, attrs, ...kids) {
        const node = document.createElement(tag);
        for (const [k, v] of Object.entries(attrs || {})) {
            if (v === false || v === null || v === undefined) continue;
            if (k === 'class') node.className = v;
            else if (k === 'text') node.textContent = v;
            else if (k.startsWith('on') && typeof v === 'function') node.addEventListener(k.slice(2), v);
            else node.setAttribute(k, v === true ? '' : String(v));
        }
        for (const kid of kids.flat()) {
            if (kid === null || kid === undefined || kid === false) continue;
            node.append(kid.nodeType ? kid : document.createTextNode(String(kid)));
        }
        return node;
    }
    function storeGet() {
        try { return JSON.parse(localStorage.getItem(S.storeKey) || '{}') || {}; } catch (_) { return {}; }
    }
    function storeSet() {
        try {
            localStorage.setItem(S.storeKey, JSON.stringify({
                visible: S.visible, layout: S.layout, area: S.area, heightPct: S.heightPct, userResized: S.userResized,
            }));
        } catch (_) { /* private mode: this tab still works */ }
    }
    function emit(type, detail) {
        const payload = Object.assign({ type }, detail || {});
        listeners.forEach(fn => { try { fn(payload); } catch (_) { /* a bad listener must not break the dock */ } });
        try { window.dispatchEvent(new CustomEvent('tlm:terminals-' + type, { detail: payload })); } catch (_) { /* ignore */ }
    }
    function askConfirm(primary, secondary, title, options) {
        if (typeof window.tlmConfirm === 'function') {
            return Promise.resolve(window.tlmConfirm(primary, secondary, title, options)).then(Boolean);
        }
        return Promise.resolve(window.confirm(primary + (secondary ? '\n\n' + secondary : '')));
    }
    function kindText(kind) { return (KINDS[kind] || { label: String(kind || '?') }).label; }
    function kindShort(kind) { return (KINDS[kind] || { short: String(kind || '?').slice(0, 3).toUpperCase() }).short; }

    /* ── socket ─────────────────────────────────────────────────────────── */
    function setConn(state) {
        S.conn = state;
        if (S.els.status) {
            S.els.status.dataset.conn = state === 'up' ? 'up' : (state === 'down' ? 'down' : 'wait');
        }
        updateStatus();
        emit('conn', { conn: state });
    }
    function send(frame) {
        const ws = S.ws;
        if (!ws || ws.readyState !== 1) return false;
        try { ws.send(JSON.stringify(frame)); return true; } catch (_) { return false; }
    }
    function connect() {
        if (S.fatal || (S.ws && (S.ws.readyState === 0 || S.ws.readyState === 1))) return;
        let ws;
        try {
            ws = new WebSocket((location.protocol === 'https:' ? 'wss://' : 'ws://') + location.host + '/ws/terminals/');
        } catch (_) { scheduleReconnect(); return; }
        S.ws = ws;
        setConn('connecting');
        ws.onopen = () => { S.backoff = 500; setConn('up'); };
        ws.onmessage = event => {
            let msg;
            try { msg = JSON.parse(event.data); } catch (_) { return; }
            if (msg && typeof msg === 'object') { try { handle(msg); } catch (err) { console.error('terminals:', err); } }
        };
        ws.onclose = event => {
            S.ws = null; S.hello = false;
            setConn('down');
            if (event && [4401, 4403, 4404].includes(event.code)) {
                S.fatal = event.code;
                S.error = event.code === 4404 ? 'Terminals are switched off on this server.' : 'Sign in again to use terminals.';
                updateStatus();
                return;
            }
            scheduleReconnect();
        };
        ws.onerror = () => { /* onclose follows */ };
    }
    function scheduleReconnect() {
        if (S.fatal || S.reconnectTimer) return;
        S.reconnectTimer = setTimeout(() => {
            S.reconnectTimer = 0;
            S.backoff = Math.min(8000, Math.round(S.backoff * 1.6));
            connect();
        }, S.backoff);
    }

    /* ── model ──────────────────────────────────────────────────────────── */
    function getTerm(id) { return S.terms.get(id) || null; }
    function ensureTerm(info) {
        let T = getTerm(info.id);
        if (T) { Object.assign(T.info, info); T.kind = info.kind; T.title = info.title; T.state = info.state; return T; }
        T = {
            id: info.id, kind: info.kind, title: info.title, state: info.state || 'starting', info: Object.assign({}, info),
            term: null, fit: null, pane: null, tab: null, host: null, overlay: null, notes: new Map(),
            promptEnd: null, lastLine: null, typedAt: 0, lineTimer: 0, fitTimer: 0, resizeTimer: 0, hung: false, input: '',
            cwd: info.cwd || '', last: null, pending: [],
        };
        S.terms.set(T.id, T);
        if (!S.order.includes(T.id)) S.order.push(T.id);
        buildPane(T);
        return T;
    }
    function removeTerm(id) {
        const T = getTerm(id);
        if (!T) return;
        clearTimeout(T.lineTimer); clearTimeout(T.fitTimer); clearTimeout(T.resizeTimer);
        try { if (T.ro) T.ro.disconnect(); } catch (_) { /* ignore */ }
        try { if (T.term) T.term.dispose(); } catch (_) { /* ignore */ }
        if (T.pane) T.pane.remove();
        S.terms.delete(id);
        S.order = S.order.filter(x => x !== id);
        if (S.active === id) S.active = S.order[S.order.length - 1] || '';
        renderTabs(); layoutPanes(); updateBar();
        emit('removed', { id });
    }

    /* ── building the dock ──────────────────────────────────────────────── */
    function buildRoot() {
        const kindSelect = h('select', { class: 'tlm-term-kind', 'aria-label': 'Terminal type', title: 'Terminal type for new terminals (and the active one)' });
        const btn = (cls, icon, label, title, onclick, extra) => h('button', Object.assign({ type: 'button', class: 'tlm-term-btn ' + cls, title, 'aria-label': label, onclick }, extra || {}), h('span', { class: 'ic', 'aria-hidden': 'true' }, icon), h('span', { class: 'lb' }, label));
        const layoutBtns = LAYOUTS.map(l => h('button', {
            type: 'button', class: 'tlm-term-btn', 'data-layout': l, 'aria-pressed': 'false', title: LAYOUT_TEXT[l] + ' layout', 'aria-label': LAYOUT_TEXT[l] + ' layout',
            onclick: () => setLayout(l, true),
        }, h('span', { class: 'ic', 'aria-hidden': 'true' }, { tabs: '▭', tile: '▦', 'tile-h': '◫', 'tile-v': '☰', grid: '▩' }[l]), h('span', { class: 'lb' }, { tabs: 'Tabs', tile: 'Tile', 'tile-h': 'Side', 'tile-v': 'Stack', grid: 'Grid' }[l])));
        const areaBtns = AREAS.map(a => h('button', {
            type: 'button', class: 'tlm-term-btn', 'data-area': a, 'aria-pressed': 'false',
            title: a === 'dock' ? 'Lower part of the canvas area' : 'Cover the whole canvas area',
            'aria-label': a === 'dock' ? 'Dock to the lower part of the canvas area' : 'Cover the whole canvas area',
            onclick: () => setArea(a, true),
        }, h('span', { class: 'ic', 'aria-hidden': 'true' }, a === 'dock' ? '⬓' : '⛶'), h('span', { class: 'lb' }, a === 'dock' ? 'Dock' : 'Full')));
        const advisor = h('input', { type: 'checkbox', class: 'tlm-term-advisor', checked: true });
        advisor.addEventListener('change', () => {
            const T = getTerm(S.active);
            if (T) send({ t: 'advisor', id: T.id, on: advisor.checked });
        });
        const els = {
            splitter: h('div', {
                class: 'tlm-term-splitter', tabindex: '0', role: 'separator', 'aria-orientation': 'horizontal',
                'aria-label': 'Resize the Terminals area', title: 'Drag to resize · Up/Down to adjust · Shift for larger steps · double-click to fit',
            }),
            tabs: h('div', { class: 'tlm-term-tabs', role: 'tablist', 'aria-label': 'Terminals' }),
            kind: kindSelect, advisor,
            newBtn: btn('tlm-primary tlm-term-new', '＋', 'New', 'Raise a new terminal of the selected type', () => openTerminal(kindSelect.value)),
            abortBtn: btn('tlm-term-abort', '⏹', 'Interrupt', 'Interrupt the running command (Ctrl+C, then stop its processes)', () => withActive(T => send({ t: 'abort', id: T.id }))),
            killBtn: btn('tlm-term-kill', '✖', 'Kill', 'Close this terminal', () => killActive(false)),
            forceBtn: btn('tlm-danger tlm-term-force', '☠', 'Force kill', 'Kill this terminal and everything it started', () => killActive(true)),
            clearBtn: btn('tlm-term-clear', '⌫', 'Clear', 'Clear the screen of this terminal', () => withActive(T => { try { T.term.clear(); } catch (_) { /* ignore */ } })),
            copyBtn: btn('tlm-term-copy', '⧉', 'Copy', 'Copy the selected text', () => withActive(T => copyText(T.term && T.term.getSelection ? T.term.getSelection() : ''))),
            layoutGroup: h('span', { class: 'tlm-term-group', role: 'group', 'aria-label': 'Layout' }, layoutBtns),
            areaGroup: h('span', { class: 'tlm-term-group', role: 'group', 'aria-label': 'Area' }, areaBtns),
            status: h('span', { class: 'tlm-term-status', role: 'status', 'aria-live': 'polite', 'data-conn': 'wait' }, 'connecting…'),
            body: h('div', { class: 'tlm-term-body', 'data-layout': 'tabs' }),
            empty: h('div', { class: 'tlm-term-empty' },
                h('strong', null, 'No terminals yet'),
                h('span', null, 'Pick CMD or PowerShell and press “New”, or ask Tlamatini to raise one for you.')),
            newTab: h('button', { type: 'button', class: 'tlm-term-newtab', title: 'New terminal', 'aria-label': 'New terminal', onclick: () => openTerminal(kindSelect.value) }, '+'),
            dockClose: h('button', { type: 'button', class: 'tlm-term-dockclose', title: 'Hide the Terminals area (terminals keep running)', 'aria-label': 'Hide the Terminals area', onclick: () => setVisible(false, true) }, '▾'),
        };
        els.layoutGroup.append();
        const bar = h('div', { class: 'tlm-term-bar', role: 'toolbar', 'aria-label': 'Terminal controls' },
            h('label', null, 'Type', kindSelect),
            els.newBtn,
            h('span', { class: 'tlm-term-sep', 'aria-hidden': 'true' }),
            els.abortBtn, els.killBtn, els.forceBtn, els.clearBtn, els.copyBtn,
            h('span', { class: 'tlm-term-sep', 'aria-hidden': 'true' }),
            h('label', { title: 'Warn me about dangerous or mistyped commands in this terminal' }, advisor, 'Advisor'),
            h('span', { class: 'tlm-term-sep', 'aria-hidden': 'true' }),
            btn('', '⚙', 'Settings', 'Configure Live Editor and Terminater', () => window.TlamatiniInteractionSettings?.open('terminal')),
            els.layoutGroup, els.areaGroup,
            els.status);
        els.body.append(els.empty);
        const root = h('section', {
            class: 'tlm-terminals', id: 'tlm-terminals', role: 'region', 'aria-label': 'Terminals', hidden: true,
            'data-page': S.page, 'data-layout': 'tabs', 'data-area': 'dock',
        }, els.splitter, els.tabs, bar, els.body);
        els.tabs.append(els.newTab, h('span', { class: 'tlm-term-tabs-spacer' }), els.dockClose);
        S.els = els;
        S.root = root;
        fillKinds();
        kindSelect.addEventListener('change', onKindChange);
        els.tabs.addEventListener('keydown', onTabsKey);
        return root;
    }
    function fillKinds() {
        const select = S.els.kind;
        if (!select) return;
        const keep = select.value || 'powershell';
        select.textContent = '';
        const order = ['cmd', 'powershell', 'pwsh'].filter(k => S.kinds.includes(k));
        (order.length ? order : ['cmd', 'powershell']).forEach(k => select.append(h('option', { value: k }, kindText(k))));
        select.value = [...select.options].some(o => o.value === keep) ? keep : (select.options[0] ? select.options[0].value : 'powershell');
    }

    function buildPane(T) {
        const xtermHost = h('div', { class: 'tlm-term-xterm' });
        const stateLabel = h('span', { class: 'tlm-term-pane-state' }, '');
        const head = h('div', { class: 'tlm-term-pane-head', title: 'Click to focus this terminal' },
            h('span', { class: 'tlm-term-tab-kind' }, kindShort(T.kind)), h('span', { class: 'tlm-term-pane-title' }, T.title), stateLabel);
        const overlay = h('div', { class: 'tlm-term-overlay', 'aria-live': 'polite' });
        // The notes strip sits ABOVE the terminal in the pane's own column: it takes its own room, so a note can
        // never cover the lines of a command that is being typed (it used to float over the first rows).
        const pane = h('div', { class: 'tlm-term-pane', 'data-id': T.id, 'data-kind': T.kind, 'data-state': T.state }, head, overlay, xtermHost);
        pane.addEventListener('mousedown', () => { if (S.active !== T.id) activate(T.id, true); });
        T.pane = pane; T.host = xtermHost; T.overlay = overlay; T.stateLabel = stateLabel; T.head = head;
        S.els.body.append(pane);
        createXterm(T);
        T.ro = (typeof ResizeObserver !== 'undefined') ? new ResizeObserver(() => scheduleFit(T)) : null;
        if (T.ro) T.ro.observe(xtermHost);
    }

    function createXterm(T) {
        const Term = window.Terminal;
        if (typeof Term !== 'function') {
            S.error = 'The terminal renderer (xterm.js) did not load.';
            T.host.textContent = S.error;
            updateStatus();
            return;
        }
        const term = new Term({
            allowProposedApi: true, cursorBlink: interaction.cursor_blink !== false, cursorStyle: interaction.cursor_style || 'block', scrollback: 10000, convertEol: false,
            fontFamily: "'Cascadia Mono','Cascadia Code',Consolas,'Courier New',monospace", fontSize: S.fontSize, lineHeight: 1.12,
            theme: THEME, windowsPty: { backend: 'conpty', buildNumber: 22621 }, rightClickSelectsWord: true,
            smoothScrollDuration: 0,
        });
        try {
            if (window.FitAddon && window.FitAddon.FitAddon) { T.fit = new window.FitAddon.FitAddon(); term.loadAddon(T.fit); }
        } catch (_) { T.fit = null; }
        try {
            if (window.WebLinksAddon && window.WebLinksAddon.WebLinksAddon) term.loadAddon(new window.WebLinksAddon.WebLinksAddon());
        } catch (_) { /* links are a nicety */ }
        term.open(T.host);
        T.term = term;

        term.attachCustomKeyEventHandler(event => {
            if (event.type !== 'keydown') return true;
            if (event.ctrlKey && event.key === '`') return false;                 // page-level toggle
            if (event.altKey && event.key === 'Enter') { send({ t: 'handback', id: T.id }); return false; }
            if (event.ctrlKey && event.shiftKey && (event.key === 'C' || event.key === 'c')) { copyText(term.getSelection()); return false; }
            if (event.ctrlKey && !event.shiftKey && (event.key === 'c' || event.key === 'C') && term.hasSelection()) { copyText(term.getSelection()); term.clearSelection(); return false; }
            if (event.ctrlKey && (event.key === 'PageDown' || event.key === 'PageUp')) { cycleTab(event.key === 'PageDown' ? 1 : -1); return false; }
            return true;
        });
        term.onData(data => {
            if (!data) return;
            send({ t: 'in', id: T.id, d: data });
            T.typedAt = Date.now();
            scheduleLine(T);
        });
        term.onResize(size => {
            clearTimeout(T.resizeTimer);
            T.resizeTimer = setTimeout(() => send({ t: 'resize', id: T.id, cols: size.cols, rows: size.rows }), 80);
        });
        try {
            term.parser.registerOscHandler(133, data => {
                const b = term.buffer.active;
                const mark = String(data || '').charAt(0);
                if (mark === 'B') T.promptEnd = { x: b.cursorX, y: b.baseY + b.cursorY };
                if (mark === 'A') T.promptEnd = null;
                return true;
            });
        } catch (_) { /* OSC tracking is an enhancement; the server falls back to its own */ }
        // flush output that arrived before the renderer existed
        T.pending.splice(0).forEach(chunk => term.write(chunk));
        scheduleFit(T);
    }

    function copyText(text) {
        if (!text) return;
        try {
            if (navigator.clipboard && navigator.clipboard.writeText) { navigator.clipboard.writeText(text); return; }
        } catch (_) { /* fall through */ }
        try {
            const area = h('textarea', { style: 'position:fixed;opacity:0' }, text);
            document.body.append(area); area.select(); document.execCommand('copy'); area.remove();
        } catch (_) { /* nothing more to try */ }
    }

    /* what the user is typing, read from xterm's own screen (ground truth) */
    function scheduleLine(T) {
        clearTimeout(T.lineTimer);
        T.lineTimer = setTimeout(() => {
            if (!T.term || !T.promptEnd || !['prompt', 'awaiting_user'].includes(T.state)) return;
            const b = T.term.buffer.active;
            const cur = b.baseY + b.cursorY;
            let text = '';
            for (let y = T.promptEnd.y; y <= cur; y += 1) {
                const line = b.getLine(y);
                if (!line) break;
                text += line.translateToString(y === cur, y === T.promptEnd.y ? T.promptEnd.x : 0);
            }
            text = text.replace(/\s+$/, '');
            if (text !== T.lastLine) { T.lastLine = text; send({ t: 'line', id: T.id, text }); }
        }, 45);
    }

    /* ── notes (typing / hand-over / hung / warnings) ───────────────────── */
    function setNote(T, kind, opts) {
        clearNote(T, kind);
        if (!opts) return;
        const text = h('span', { class: 'tlm-term-note-text' });
        if (opts.html) text.innerHTML = opts.html; else text.textContent = opts.text || '';
        const note = h('div', { class: 'tlm-term-note', 'data-kind': kind, role: opts.severity === 'danger' ? 'alert' : 'status' }, text);
        if (opts.severity) note.dataset.severity = opts.severity;
        (opts.actions || []).forEach(a => note.append(h('button', { type: 'button', onclick: () => { a.run(); if (a.dismiss !== false) clearNote(T, kind); } }, a.label)));
        if (opts.closable !== false) note.append(h('button', { type: 'button', class: 'tlm-term-note-x', 'aria-label': 'Dismiss', title: 'Dismiss', onclick: () => clearNote(T, kind) }, '✕'));
        T.overlay.append(note);
        T.notes.set(kind, note);
        if (opts.ttl) { note._ttl = setTimeout(() => clearNote(T, kind), opts.ttl); }
    }
    function clearNote(T, kind) {
        const old = T.notes.get(kind);
        if (old) { clearTimeout(old._ttl); old.remove(); T.notes.delete(kind); }
    }
    /* A short, passing message ("You took over", "Tlamatini is typing - press Esc") is shown in the status line: it takes
       no room from the terminal and never covers a character of it. */
    function showNotice(T, text, ttl) {
        clearTimeout(T.noticeTimer);
        T.notice = text || '';
        T.noticeTimer = ttl ? setTimeout(() => clearNotice(T), ttl) : null;
        updateStatus();
    }
    function clearNotice(T) {
        if (!T.notice && !T.noticeTimer) return;
        clearTimeout(T.noticeTimer);
        T.notice = ''; T.noticeTimer = null;
        updateStatus();
    }
    const escapeHtml = s => String(s == null ? '' : s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

    function applyState(T, state, extra) {
        const previous = T.state;
        T.state = state;
        T.pane.dataset.state = state;
        if (T.tab) T.tab.dataset.state = state;
        if (T.stateLabel) T.stateLabel.textContent = STATE_TEXT[state] || state;
        if (state !== 'running') { T.hung = false; if (T.tab) delete T.tab.dataset.flag; clearNote(T, 'hung'); clearNote(T, 'input'); }
        // "Tlamatini is typing — press Esc to take over" is told by the status line and the pane's state label, never
        // by a box over the terminal: a banner here hid the very first characters of the command being typed, and a
        // note that comes and goes would also re-fit (resize) the shell while Tlamatini types.
        clearNote(T, 'typing');
        if (state === 'awaiting_user') {
            const hint = (extra && extra.hint) || T.info.handover_hint || 'your part';
            const secret = Boolean(extra && extra.secret);
            const resume = !extra || extra.resume !== false;
            setNote(T, 'handover', {
                html: `<strong>Your turn.</strong> Tlamatini typed part of the command. Type <code>${escapeHtml(hint)}</code>${secret ? ' (private — Tlamatini will not see it)' : ''}, then press <strong>Enter</strong>${resume ? ' — she will finish the line' : ' to run it'}.`,
                actions: resume ? [{ label: 'Continue ▶', run: () => send({ t: 'handback', id: T.id }) }] : [],
                closable: false,
            });
            // Tell the page first: a modal dialog that is open over it (the Agentic Control Panel's "Startup
            // Complete") traps every key, so the page must be able to step aside BEFORE the terminal takes focus.
            if (previous !== 'awaiting_user') emit('handover', { id: T.id, hint, secret });
            focusTerm(T);
        } else if (previous === 'awaiting_user') { clearNote(T, 'handover'); }
        updateTab(T); updateBar();
    }

    /* ── server frames ──────────────────────────────────────────────────── */
    function handle(m) {
        const kind = m.t;
        if (kind === 'narration') {
            if (document.hidden) { send({ t: 'narration_receipt', id: m.id, status: 'cancel' }); return undefined; }
            window.TlamatiniInteractionSpeech?.narrate(m).then(status => send({ t: 'narration_receipt', id: m.id, status }));
            return undefined;
        }
        if (kind === 'narration_cancel') { window.TlamatiniInteractionSpeech?.cancel(m); return undefined; }
        if (kind === 'hello') { const result = onHello(m); applyInteraction(interaction); narrationPresence(); return result; }
        if (kind === 'pong') return undefined;
        if (kind === 'error') { S.error = m.message || 'Terminal request failed.'; updateStatus(); emit('error', m); return undefined; }
        if (kind === 'ui') { applyUi(m.ui || {}, m.active); return undefined; }
        if (kind === 'opened') {
            const T = ensureTerm(m.terminal);
            if (m.ui) applyUi(m.ui, T.id); else activate(T.id, false);
            renderTabs(); layoutPanes(); updateBar();
            emit('opened', { id: T.id });
            return undefined;
        }
        if (kind === 'removed') { removeTerm(m.id); if (m.active) activate(m.active, false); return undefined; }
        const T = getTerm(m.id);
        if (!T) return undefined;
        switch (kind) {
            case 'out':
                if (T.term) {
                    // The shell echoes a key AFTER it was typed: re-read the line once the echo is on the screen,
                    // or the last character of what the user typed would be missing from what the advisor judges.
                    T.term.write(m.d || '', () => { if (T.typedAt && Date.now() - T.typedAt < 2500) scheduleLine(T); });
                } else T.pending.push(m.d || '');
                break;
            case 'replay':
                if (T.term) { T.term.reset(); T.term.write(m.d || ''); } else { T.pending = [m.d || '']; }
                break;
            case 'resync': send({ t: 'snapshot', id: T.id }); break;
            case 'state': applyState(T, m.state, m); break;
            case 'exit':
                T.info.exit_code = m.exit_code; applyState(T, 'exited', m);
                if (T.term) T.term.write('\r\n\x1b[90m[process exited' + (m.exit_code == null ? '' : ' with code ' + m.exit_code) + ']\x1b[0m\r\n');
                break;
            case 'closed': applyState(T, 'closed', m); break;
            case 'command': T.last = m.command; updateBar(); emit('command', { id: T.id, command: m.command }); break;
            case 'hung':
                T.hung = true; if (T.tab) T.tab.dataset.flag = 'hung';
                setNote(T, 'hung', {
                    html: `No output for <strong>${Math.round(m.idle_seconds || 0)}s</strong> — <code>${escapeHtml(m.command || 'the command')}</code> looks hung.`,
                    severity: 'danger',
                    actions: [
                        { label: 'Interrupt', run: () => send({ t: 'abort', id: T.id }) },
                        { label: 'Force kill', run: () => send({ t: 'kill', id: T.id, force: true }) },
                        { label: 'Keep waiting', run: () => {} },
                    ],
                });
                break;
            case 'input_request':
                setNote(T, 'input', { html: `The program is asking: <code>${escapeHtml(m.hint || '')}</code> — answer in the terminal.`, ttl: 0 });
                break;
            case 'handover': T.info.handover_hint = m.hint; break;
            case 'warn':
                setNote(T, 'warn', {
                    html: `<strong>${escapeHtml(m.source === 'tlamatini' ? 'Tlamatini' : 'Advisor')}:</strong> ${escapeHtml(m.message)}${m.suggestion ? ` Try <code>${escapeHtml(m.suggestion)}</code>.` : ''}`,
                    severity: m.severity || 'warning', ttl: m.severity === 'danger' ? 0 : 14000,
                });
                emit('warn', { id: T.id, warning: m });
                break;
            case 'notice':
                // "Tlamatini is typing - press Esc to take over" is already what the status line says while she types.
                if (!(T.state === 'typing' && /^Tlamatini is typing/i.test(m.message || ''))) showNotice(T, m.message || '', 3500);
                break;
            case 'title_set': T.title = m.title; T.info.title = m.title; updateTab(T); updateBar(); break;
            case 'title': T.osTitle = m.title; if (T.tab) T.tab.title = `${T.title} — ${m.title}`; break;
            case 'cwd': T.cwd = m.cwd; T.info.cwd = m.cwd; updateBar(); break;
            case 'clear': try { T.term.clear(); } catch (_) { /* ignore */ } break;
            default: break;
        }
        return undefined;
    }

    function onHello(m) {
        S.hello = true; S.error = '';
        S.kinds = (m.kinds && m.kinds.length) ? m.kinds : S.kinds;
        S.max = m.max || S.max;
        fillKinds();
        const seen = new Set();
        (m.terminals || []).forEach(info => {
            seen.add(info.id);
            const T = ensureTerm(info);
            const replay = (m.replay || {})[info.id] || '';
            if (T.term) { T.term.reset(); if (replay) T.term.write(replay); } else if (replay) { T.pending = [replay]; }
            applyState(T, info.state, { hint: info.handover_hint });
        });
        [...S.terms.keys()].forEach(id => { if (!seen.has(id)) removeTerm(id); });
        S.order = (m.terminals || []).map(t => t.id);
        const ui = m.ui || {};
        // the user's own saved layout wins; push it so the server (and Tlamatini) agree with it
        const stored = storeGet();
        if (stored.layout && LAYOUTS.includes(stored.layout) && stored.layout !== ui.layout) send({ t: 'layout', layout: stored.layout, show: Boolean(ui.visible) });
        if (stored.area && AREAS.includes(stored.area) && stored.area !== ui.area) send({ t: 'layout', area: stored.area, show: Boolean(ui.visible) });
        applyUi({ visible: Boolean(ui.visible), focus: m.active || ui.focus }, m.active);
        renderTabs(); layoutPanes(); updateBar();
        if (S.visible && S.order.length === 0 && !S.autoOpened) {
            Promise.resolve(window.TlamatiniInteractionSettings?.ready).then(() => {
                if (S.visible && S.order.length === 0 && !S.autoOpened) {
                    S.autoOpened = true; openTerminal(interaction.shell || S.els.kind.value);
                }
            });
        }
        emit('hello', { terminals: S.order.length });
    }

    function applyUi(ui, activeId) {
        let changed = false;
        if (ui.layout && LAYOUTS.includes(ui.layout) && ui.layout !== S.layout) { S.layout = ui.layout; changed = true; }
        if (ui.area && AREAS.includes(ui.area) && ui.area !== S.area) { S.area = ui.area; changed = true; }
        const wantFocus = activeId || ui.focus;
        if (wantFocus && getTerm(wantFocus) && S.active !== wantFocus) { S.active = wantFocus; changed = true; }
        if (typeof ui.visible === 'boolean' && ui.visible !== S.visible) setVisible(ui.visible, false);
        if (changed) { storeSet(); renderTabs(); layoutPanes(); updateBar(); syncBodyClasses(); applyHeight(); }
    }

    /* ── actions ────────────────────────────────────────────────────────── */
    function withActive(fn) { const T = getTerm(S.active); if (T) fn(T); }
    function openTerminal(kind, title) {
        if (!send({ t: 'open', kind: kind || interaction.shell || '', title: title || '' })) {
            S.error = 'Not connected to the terminal hub yet.'; updateStatus(); return false;
        }
        S.openPending += 1;
        S.kindPin = '';   // the chosen type has been used; the bar follows the active terminal again
        return true;
    }
    function killActive(force) {
        const T = getTerm(S.active);
        if (!T) return;
        askConfirm(
            force ? `Force kill “${T.title}”?` : `Close “${T.title}”?`,
            force ? 'The shell and every process it started are killed immediately.' : 'A running command is interrupted and the shell is closed.',
            force ? 'Force kill terminal' : 'Close terminal',
            { confirmLabel: force ? 'Force kill' : 'Close', cancelLabel: 'Cancel', danger: true, focusCancel: true },
        ).then(ok => { if (ok) send({ t: 'kill', id: T.id, force: Boolean(force) }); });
    }
    function onKindChange() {
        const T = getTerm(S.active);
        const wanted = S.els.kind.value;
        if (!T || T.kind === wanted || ['exited', 'closed'].includes(T.state)) return;
        askConfirm(
            `Restart “${T.title}” as ${kindText(wanted)}?`,
            `The current shell is closed and a new ${kindText(wanted)} terminal opens in its place. Choose “Only for new terminals” to keep this one and raise ${kindText(wanted)} terminals with New.`,
            'Change terminal type', { confirmLabel: 'Restart as ' + kindText(wanted), cancelLabel: 'Only for new terminals', focusCancel: true },
        ).then(ok => {
            if (ok) { const title = T.title; S.kindPin = ''; send({ t: 'kill', id: T.id, force: false }); openTerminal(wanted, title); }
            else { S.kindPin = wanted; S.els.kind.value = wanted; }   // keep the choice: the next New raises this type
        });
    }
    // Selecting a tab only moves the "selected" marker.  Rebuilding the strip on every click would
    // destroy the tab under the pointer between the two clicks of a double-click (rename never
    // fired) and would drop the keyboard focus the arrow keys depend on.
    function syncTabSelection() {
        const tabs = S.els.tabs ? [...S.els.tabs.querySelectorAll('.tlm-term-tab')] : [];
        if (tabs.length !== S.order.length || tabs.some((t, i) => t.dataset.id !== S.order[i])) { renderTabs(); return; }
        tabs.forEach(tab => {
            const on = tab.dataset.id === S.active;
            tab.setAttribute('aria-selected', on ? 'true' : 'false');
            tab.tabIndex = on ? 0 : -1;
        });
    }
    function activate(id, notify, keepFocus) {
        if (!getTerm(id)) return;
        S.active = id;
        syncTabSelection(); layoutPanes(); updateBar();
        if (notify) send({ t: 'focus', id });
        if (!keepFocus) focusTerm(getTerm(id));   // keyboard navigation among the tabs keeps its focus on the tabs
    }
    function cycleTab(dir) {
        if (S.order.length < 2) return;
        const i = S.order.indexOf(S.active);
        activate(S.order[(i + dir + S.order.length) % S.order.length], true);
    }
    function focusTerm(T) {
        if (!T || !T.term || !S.visible || S.root.hidden) return;
        setTimeout(() => {
            // the clicks of a double-click also select the tab, and that must never pull the keyboard
            // out of the name field the double-click just opened
            if (S.els.tabs && S.els.tabs.querySelector('.tlm-term-tab-title-input')) return;
            try { T.term.focus(); } catch (_) { /* ignore */ }
        }, 0);
    }

    /* ── tabs ───────────────────────────────────────────────────────────── */
    function renderTabs() {
        const tabs = S.els.tabs;
        if (!tabs) return;
        tabs.querySelectorAll('.tlm-term-tab').forEach(n => n.remove());
        const anchor = S.els.newTab;
        S.order.forEach(id => {
            const T = getTerm(id);
            if (!T) return;
            const title = h('span', { class: 'tlm-term-tab-title' }, T.title);
            const tab = h('div', {
                class: 'tlm-term-tab', role: 'tab', tabindex: S.active === id ? '0' : '-1', 'data-id': id, 'data-kind': T.kind, 'data-state': T.state,
                'aria-selected': S.active === id ? 'true' : 'false', draggable: 'true', title: `${T.title} — ${kindText(T.kind)}`,
            }, h('span', { class: 'tlm-term-tab-kind' }, kindShort(T.kind)), title, h('span', { class: 'tlm-term-tab-dot', 'aria-hidden': 'true' }),
            h('button', { type: 'button', class: 'tlm-term-tab-close', 'aria-label': `Close ${T.title}`, title: 'Close this terminal', tabindex: '-1' }, '×'));
            if (T.hung) tab.dataset.flag = 'hung';
            tab.addEventListener('click', ev => {
                if (ev.target.closest('.tlm-term-tab-close')) { S.active = id; killActive(false); return; }
                activate(id, true);
            });
            tab.addEventListener('auxclick', ev => { if (ev.button === 1) { ev.preventDefault(); S.active = id; killActive(false); } });
            title.addEventListener('dblclick', ev => { ev.stopPropagation(); renameTab(T, title); });
            tab.addEventListener('dragstart', ev => { tab.classList.add('tlm-dragging'); ev.dataTransfer.setData('text/plain', id); ev.dataTransfer.effectAllowed = 'move'; });
            tab.addEventListener('dragend', () => tab.classList.remove('tlm-dragging'));
            tab.addEventListener('dragover', ev => { ev.preventDefault(); tab.classList.add('tlm-drop-target'); });
            tab.addEventListener('dragleave', () => tab.classList.remove('tlm-drop-target'));
            tab.addEventListener('drop', ev => {
                ev.preventDefault(); tab.classList.remove('tlm-drop-target');
                const from = ev.dataTransfer.getData('text/plain');
                if (!from || from === id) return;
                S.order = S.order.filter(x => x !== from);
                S.order.splice(S.order.indexOf(id), 0, from);
                renderTabs(); layoutPanes();
            });
            T.tab = tab;
            tabs.insertBefore(tab, anchor);
        });
    }
    function updateTab(T) {
        if (!T.tab) return;
        T.tab.dataset.state = T.state; T.tab.dataset.kind = T.kind;
        const title = T.tab.querySelector('.tlm-term-tab-title');
        if (title && !title.querySelector('input')) title.textContent = T.title;
        const kind = T.tab.querySelector('.tlm-term-tab-kind');
        if (kind) kind.textContent = kindShort(T.kind);
        T.tab.title = `${T.title} — ${kindText(T.kind)}`;
        if (T.head) { T.head.querySelector('.tlm-term-pane-title').textContent = T.title; T.head.querySelector('.tlm-term-tab-kind').textContent = kindShort(T.kind); }
    }
    function renameTab(T, titleEl) {
        const input = h('input', { class: 'tlm-term-tab-title-input', value: T.title, 'aria-label': 'Terminal name', maxlength: '40' });
        titleEl.textContent = '';
        titleEl.append(input);
        input.focus(); input.select();
        const done = commit => {
            const value = input.value.trim();
            input.remove();
            titleEl.textContent = T.title;
            if (commit && value && value !== T.title) { T.title = value; send({ t: 'rename', id: T.id, title: value }); updateTab(T); }
        };
        input.addEventListener('keydown', ev => { if (ev.key === 'Enter') { ev.preventDefault(); done(true); } else if (ev.key === 'Escape') { ev.stopPropagation(); done(false); } });
        input.addEventListener('blur', () => done(true));
        input.addEventListener('click', ev => ev.stopPropagation());
    }
    function onTabsKey(ev) {
        const tab = ev.target.closest && ev.target.closest('.tlm-term-tab');
        if (!tab) return;
        if (ev.key === 'ArrowRight' || ev.key === 'ArrowLeft') {
            ev.preventDefault();
            const i = S.order.indexOf(tab.dataset.id);
            const next = S.order[clamp(i + (ev.key === 'ArrowRight' ? 1 : -1), 0, S.order.length - 1)];
            activate(next, true, true);
            const el = S.els.tabs.querySelector(`.tlm-term-tab[data-id="${next}"]`);
            if (el) el.focus();
        } else if (ev.key === 'Enter' || ev.key === ' ') { ev.preventDefault(); activate(tab.dataset.id, true); }
        else if (ev.key === 'Delete') { ev.preventDefault(); S.active = tab.dataset.id; killActive(false); }
        else if (ev.key === 'F2') { ev.preventDefault(); const T = getTerm(tab.dataset.id); if (T) renameTab(T, tab.querySelector('.tlm-term-tab-title')); }
    }

    /* ── layout / bar / status ──────────────────────────────────────────── */
    function layoutPanes() {
        const body = S.els.body;
        if (!body) return;
        body.dataset.layout = S.layout;
        const n = S.order.length;
        body.style.setProperty('--tlm-term-cols', String(Math.max(1, Math.ceil(Math.sqrt(Math.max(1, n))))));
        S.els.empty.hidden = n > 0;
        S.order.forEach((id, i) => {
            const T = getTerm(id);
            if (!T) return;
            T.pane.dataset.active = String(id === S.active);
            T.pane.style.order = String(i);
            body.append(T.pane);
        });
        body.append(S.els.empty);
        S.root.dataset.layout = S.layout;
        scheduleFitAll();
    }
    function updateBar() {
        const els = S.els;
        if (!els.kind) return;
        const T = getTerm(S.active);
        els.layoutGroup.querySelectorAll('[data-layout]').forEach(b => b.setAttribute('aria-pressed', String(b.dataset.layout === S.layout)));
        els.areaGroup.querySelectorAll('[data-area]').forEach(b => b.setAttribute('aria-pressed', String(b.dataset.area === S.area)));
        const live = Boolean(T) && !['exited', 'closed'].includes(T.state);
        els.abortBtn.disabled = !(T && ['running', 'awaiting_user', 'typing'].includes(T.state));
        els.killBtn.disabled = !live;
        els.forceBtn.disabled = !T;
        els.clearBtn.disabled = !T;
        els.copyBtn.disabled = !T;
        els.advisor.disabled = !T;
        els.newBtn.disabled = S.conn !== 'up' || S.order.length >= S.max;
        els.newTab.disabled = els.newBtn.disabled;
        if (T) {
            if (S.kindPin && [...els.kind.options].some(o => o.value === S.kindPin)) els.kind.value = S.kindPin;
            else if ([...els.kind.options].some(o => o.value === T.kind)) els.kind.value = T.kind;
            els.advisor.checked = T.info.advisor !== false;
        }
        updateStatus();
    }
    function updateStatus() {
        const el = S.els.status;
        if (!el) return;
        const T = getTerm(S.active);
        let text;
        if (S.fatal || S.error) text = S.error;
        else if (S.conn !== 'up') text = S.conn === 'connecting' ? 'connecting…' : 'reconnecting…';
        else if (T) {
            const hint = T.notice || (T.state === 'typing' ? 'press Esc to take over' : '');
            text = `${kindText(T.kind)} · ${STATE_TEXT[T.state] || T.state}${hint ? ' — ' + hint : ''}${T.cwd ? ' · ' + T.cwd : ''}`;
        }
        else text = 'connected';
        el.textContent = text;
        el.title = text;
    }

    /* ── geometry ───────────────────────────────────────────────────────── */
    function composerHeight() {
        const c = document.getElementById('tools-chat-form-container');
        return c ? Math.round(c.getBoundingClientRect().height) : 0;
    }
    // The host wrapper is `display: contents`, so the box that matters is its parent column.
    function region() { return (S.host && S.host.parentElement) || S.host; }
    function hostHeight() { const r = region(); return r ? r.clientHeight : 0; }
    function dockHeightNow() { return S.root && !S.root.hidden ? Math.round(S.root.getBoundingClientRect().height) : 0; }
    function applyHeight() {
        const root = S.root;
        if (!root) return;
        if (S.area === 'full') { root.style.removeProperty('--tlm-term-h'); root.classList.add('tlm-term-full'); scheduleFitAll(); return; }
        root.classList.remove('tlm-term-full');
        const total = hostHeight();
        let height;
        if (S.userResized && S.heightPct > 0) height = Math.round(total * S.heightPct / 100);
        else height = composerHeight() || Math.round(total * 0.34);
        height = clamp(height, MIN_DOCK, Math.max(MIN_DOCK, total - RESERVE_FOR_CANVAS));
        root.style.setProperty('--tlm-term-h', height + 'px');
        const splitter = S.els.splitter;
        if (splitter) {
            const pct = total ? Math.round(height / total * 1000) / 10 : 0;
            splitter.setAttribute('aria-valuemin', '8'); splitter.setAttribute('aria-valuemax', '85');
            splitter.setAttribute('aria-valuenow', String(pct)); splitter.setAttribute('aria-valuetext', 'Terminals area ' + height + ' pixels high');
        }
        scheduleFitAll();
    }
    function syncBodyClasses() {
        document.body.classList.toggle('tlm-terminals-on', S.visible);
        document.body.classList.toggle('tlm-terminals-full', S.visible && S.area === 'full');
        document.querySelectorAll('[data-tlm-terminals-toggle]').forEach(el => el.setAttribute('aria-checked', String(S.visible)));
        if (S.root) { S.root.dataset.area = S.area; S.root.classList.toggle('tlm-term-full', S.area === 'full'); }
    }
    function scheduleFit(T) {
        if (!T || !T.term) return;
        cancelAnimationFrame(T.fitTimer);
        T.fitTimer = requestAnimationFrame(() => {
            if (!S.visible || !T.pane.offsetParent || !T.host.clientWidth || !T.host.clientHeight) return;
            try { if (T.fit) T.fit.fit(); } catch (_) { /* hidden or detached */ }
        });
    }
    function scheduleFitAll() { S.terms.forEach(scheduleFit); }

    /* ── show / hide / layout API ───────────────────────────────────────── */
    function setVisible(show, persist) {
        show = Boolean(show);
        const was = S.visible;
        S.visible = show;
        S.root.hidden = !show;
        syncBodyClasses();
        if (persist !== false) storeSet();
        // the user's own show/hide is told to the hub too: otherwise the hub keeps answering "visible"
        // and a page reload would open the dock the user just closed
        if (persist !== false && S.hello && was !== show) send({ t: 'layout', show });
        if (show) {
            applyHeight(); layoutPanes(); updateBar();
            requestAnimationFrame(() => { scheduleFitAll(); focusTerm(getTerm(S.active)); });
            if (!was && S.hello && S.order.length === 0 && !S.autoOpened && persist) { S.autoOpened = true; openTerminal(S.els.kind.value || 'powershell'); }
        }
        window.dispatchEvent(new Event('resize'));
        emit('visible', { visible: show });
        return S.visible;
    }
    function setLayout(layout, notify) {
        if (!LAYOUTS.includes(layout)) return false;
        S.layout = layout; storeSet(); layoutPanes(); updateBar();
        if (notify) send({ t: 'layout', layout, show: true });
        emit('layout', { layout });
        return true;
    }
    function setArea(area, notify) {
        if (!AREAS.includes(area)) return false;
        S.area = area; storeSet(); syncBodyClasses(); applyHeight(); updateBar();
        if (notify) send({ t: 'layout', area, show: true });
        window.dispatchEvent(new Event('resize'));
        emit('area', { area });
        return true;
    }
    function resetLayout() {
        S.userResized = false; S.heightPct = 0; S.layout = 'tabs'; S.area = 'dock';
        storeSet(); syncBodyClasses(); applyHeight(); layoutPanes(); updateBar();
        send({ t: 'layout', layout: 'tabs', area: 'dock' });
    }

    /* ── wiring ─────────────────────────────────────────────────────────── */
    function bindSplitter() {
        const splitter = S.els.splitter;
        splitter.addEventListener('dblclick', () => { S.userResized = false; S.heightPct = 0; storeSet(); applyHeight(); });
        if (!window.TlmSplitters || !window.TlmSplitters.bind) return;
        const pctNow = () => { const total = hostHeight(); return total ? dockHeightNow() / total * 100 : 0; };
        const setPct = pct => {
            S.userResized = true;
            S.heightPct = clamp(pct, 8, 85);
            storeSet(); applyHeight();
        };
        window.TlmSplitters.bind({
            element: splitter, axis: 'y', keyDirection: -1,
            value: pctNow,
            atPointer: y => { const r = region().getBoundingClientRect(); return r.height ? (r.bottom - y) / r.height * 100 : 0; },
            apply: setPct, before: () => { S.userResized = true; },
            min: 8, max: 85,
        });
    }
    function bindToggles() {
        document.querySelectorAll('[data-tlm-terminals-toggle]').forEach(el => {
            el.addEventListener('click', ev => { ev.preventDefault(); setVisible(!S.visible, true); });
        });
        document.addEventListener('keydown', ev => {
            if (ev.ctrlKey && !ev.altKey && !ev.metaKey && ev.key === '`') {
                ev.preventDefault();
                if (ev.shiftKey) { if (!S.visible) setVisible(true, true); openTerminal(S.els.kind.value); } else setVisible(!S.visible, true);
            }
        }, true);
    }
    function init(options) {
        if (S.inited) return window.TlamatiniTerminals;
        const opts = options || {};
        const host = opts.host || document.querySelector('[data-tlm-terminals-host]');
        if (!host) return null;
        S.inited = true;
        S.host = host;
        S.page = opts.page || host.getAttribute('data-tlm-terminals-host') || 'chat';
        S.user = String(opts.user || document.body.dataset.tlmUser || document.body.dataset.layoutUser || 'anon');
        S.storeKey = 'tlamatini.terminals.v1.' + S.user;
        const saved = storeGet();
        S.layout = LAYOUTS.includes(saved.layout) ? saved.layout : 'tabs';
        S.area = AREAS.includes(saved.area) ? saved.area : 'dock';
        S.heightPct = Number(saved.heightPct) || 0;
        S.userResized = Boolean(saved.userResized) && S.heightPct > 0;
        const root = buildRoot();
        host.append(root);
        bindSplitter();
        bindToggles();
        window.TlamatiniInteractionSettings?.ready.then(() => applyInteraction(window.TlamatiniInteractionSettings.snapshot()));
        window.addEventListener('tlm:interaction-settings', event => applyInteraction(event.detail));
        document.addEventListener('visibilitychange', narrationPresence);
        window.addEventListener('focus', narrationPresence);
        window.addEventListener('blur', narrationPresence);
        const narrationHeartbeat = setInterval(narrationPresence, 10000);
        window.addEventListener('pagehide', () => { clearInterval(narrationHeartbeat); window.TlamatiniInteractionSpeech?.cancel(); });
        if (typeof ResizeObserver !== 'undefined') {
            const ro = new ResizeObserver(() => { if (S.visible) applyHeight(); });
            ro.observe(region());
            const composer = document.getElementById('tools-chat-form-container');
            if (composer) ro.observe(composer);
        }
        window.addEventListener('resize', () => { if (S.visible) applyHeight(); });
        window.addEventListener('tlm:chat-layout-changing', () => { setTimeout(() => { if (S.visible) applyHeight(); }, 30); });
        window.addEventListener('tlm:reset-chat-layout', () => resetLayout());
        window.addEventListener('beforeunload', () => { try { if (S.ws) S.ws.close(); } catch (_) { /* ignore */ } });
        syncBodyClasses();
        if (saved.visible) setVisible(true, false);
        connect();
        return window.TlamatiniTerminals;
    }

    /* ── introspection for tests and for the other modules ──────────────── */
    function textOf(id, lines) {
        const T = getTerm(id || S.active);
        if (!T || !T.term) return '';
        const b = T.term.buffer.active;
        const total = b.length;
        const from = Math.max(0, total - (lines || 60));
        const out = [];
        for (let y = from; y < total; y += 1) { const line = b.getLine(y); if (line) out.push(line.translateToString(true)); }
        while (out.length && !out[out.length - 1]) out.pop();
        return out.join('\n');
    }
    function state() {
        return {
            ready: S.inited, visible: S.visible, layout: S.layout, area: S.area, active: S.active, conn: S.conn, hello: S.hello,
            kinds: S.kinds.slice(), max: S.max, page: S.page, error: S.error, order: S.order.slice(), dockHeight: dockHeightNow(),
            hostHeight: hostHeight(), composerHeight: composerHeight(), userResized: S.userResized, heightPct: S.heightPct,
            terminals: S.order.map(id => {
                const T = getTerm(id);
                return T && {
                    id, kind: T.kind, title: T.title, state: T.state, cwd: T.cwd, cols: T.term ? T.term.cols : 0, rows: T.term ? T.term.rows : 0,
                    hung: T.hung, notes: [...T.notes.keys()], active: S.active === id, userLine: T.lastLine,
                    paneBox: T.pane ? (r => ({ w: Math.round(r.width), h: Math.round(r.height), x: Math.round(r.x), y: Math.round(r.y) }))(T.pane.getBoundingClientRect()) : null,
                };
            }).filter(Boolean),
        };
    }

    window.TlamatiniTerminals = Object.freeze({
        init, state, textOf, setVisible: show => setVisible(show, true), isVisible: () => S.visible,
        toggle: () => setVisible(!S.visible, true), setLayout: l => setLayout(l, true), setArea: a => setArea(a, true),
        open: (kind, title) => openTerminal(kind, title), activate: id => activate(id, true), resetLayout,
        isReady: () => S.hello, onEvent: fn => { listeners.add(fn); return () => listeners.delete(fn); },
        constants: Object.freeze({ LAYOUTS: LAYOUTS.slice(), AREAS: AREAS.slice(), MIN_DOCK }),
    });
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', () => init(), { once: true });
    else setTimeout(() => init(), 0);
})();
