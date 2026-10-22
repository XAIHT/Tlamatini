/*
 * ═══════════════════════════════════════════════════════════════════
 *   ✦  T L A M A T I N I  ✦   —   "one who knows"
 *
 *   Created by  Angela López Mendoza   ·   @angelahack1
 *   Developer · Architect · Creator of Tlamatini
 *
 *   Every line of this file was written by Angela López Mendoza.
 * ═══════════════════════════════════════════════════════════════════
 *   Tlamatini Author Banner — do not remove (releases scrub the name automatically)
 */
// Shared classic-script bindings, consumed by sibling page scripts.
/* exported rotateTitle */


// ============================================================
// agent_page_layout.js  –  Drag dividers, resize & title rotation
// ============================================================

// Keep a drag in the parent document even when it crosses an embedded viewer.
// Both dividers share mouse/pen/touch capture and the same interruption cleanup.
function bindDividerPointerDrag(divider, resizingClass, onMove) {
    return window.TlmSplitters.bindPointer({ element: divider, resizingClass, onMove });
}

// --- Horizontal drag divider (chat <-> canvas) ---
(function () {
    const container = document.getElementById('chat-workspace');
    const canvas = document.getElementById('canvas-container');
    const chat = document.getElementById('main-chat-container');
    const divider = document.getElementById('drag-divider');
    if (!container || !canvas || !chat || !divider) return;

    let seamPct;
    let userResized = false;

    const clamp = (n, lo, hi) => Math.max(lo, Math.min(hi, n));
    const rect = () => container.getBoundingClientRect();
    const isCanvasOnLeft = () => {
        const cr = canvas.getBoundingClientRect();
        const hr = chat.getBoundingClientRect();
        const cCenter = cr.left + cr.width / 2;
        const hCenter = hr.left + hr.width / 2;
        return cCenter < hCenter;
    };

    const pctFromXToSeam = (clientX) => {
        const r = rect();
        const x = clamp(clientX, r.left, r.right);
        return ((x - r.left) / r.width) * 100;
    };

    const apply = (pSeam) => {
        if (document.body.classList.contains('tlm-canvas-hidden') && !document.body.classList.contains('tlm-terminals-on')) return;
        const left = isCanvasOnLeft();
        const minSeam = left ? 30 : 15;
        const maxSeam = left ? 85 : 70;
        seamPct = clamp(pSeam, minSeam, maxSeam);
        const canvasWidth = left ? seamPct : (100 - seamPct);
        const chatWidth = 100 - canvasWidth;
        canvas.style.width = canvasWidth + '%';
        chat.style.width = chatWidth + '%';
        divider.style.left = seamPct + '%';
        window.TlmSplitters.describe(divider, seamPct, minSeam, maxSeam,
            `Chat ${Math.round(chatWidth)}%, canvas ${Math.round(canvasWidth)}%`);
    };

    // Empirical guard: on the primary dev display 688px is the
    // observed one-row minimum for the toolbar. Used as a hard floor
    // in case the dynamic measurement undercounts (font swap timing,
    // browser zoom, per-monitor DPR). The actual measurement may
    // legitimately exceed this (e.g. on a higher-DPI display where
    // the Nunito glyphs end up wider than the system fallback) and
    // takes precedence when it does.
    const TOOLBAR_FLOOR_PX = 688;
    // Buffer absorbs sub-pixel rounding when the computed % is
    // converted back to px by the browser, plus the 2px outline on
    // each side of the tools-chat-form-container, plus a few pixels
    // of slack.
    const TOOLBAR_BUFFER_PX = 32;

    // Measure the toolbar's natural one-row width using an off-screen
    // clone — immune to any parent flex shrink, font-loading state,
    // or width constraint that affects in-place measurement.
    const measureNaturalToolbarWidth = () => {
        const toolsLeft = document.getElementById('tools-left');
        if (!toolsLeft) return 0;
        const clone = toolsLeft.cloneNode(true);
        // Override every flex/sizing rule that the live tools-left
        // inherits, so the clone sizes purely to its content.
        clone.style.cssText = (
            'position: absolute !important;' +
            'left: -99999px !important;' +
            'top: 0 !important;' +
            'visibility: hidden !important;' +
            'display: inline-flex !important;' +
            'align-items: center !important;' +
            'flex: none !important;' +
            'flex-wrap: nowrap !important;' +
            'gap: 4px !important;' +
            'padding: 1px 2px !important;' +
            'width: max-content !important;' +
            'max-width: none !important;' +
            'min-width: 0 !important;'
        );
        document.body.appendChild(clone);
        void clone.offsetWidth; // force layout
        const naturalPx = Math.ceil(clone.getBoundingClientRect().width);
        document.body.removeChild(clone);
        return naturalPx;
    };

    // Bump the chat panel wider if its current width is below the
    // toolbar's natural one-row width. This is what keeps the
    // checkboxes on a single row at page load.
    //
    // Keep at least 320px for the canvas. The chat toolbar can wrap;
    // making it one row must never hide the editor below its controls.
    // Once the user drags the divider, apply() owns the chosen split.
    const ensureToolbarFitsOneRow = () => {
        if (document.body.classList.contains('tlm-canvas-hidden') && !document.body.classList.contains('tlm-terminals-on')) return;
        // Font loading and the delayed initial fit must not undo a user's drag.
        if (userResized) return;
        // Below the desktop working width, retain a usable 320px chat and
        // canvas instead of squeezing either pane into an unusable sliver.
        if (container.clientWidth <= 720) { apply(50); return; }
        const naturalPx = measureNaturalToolbarWidth();
        const containerPx = container.clientWidth;
        if (!containerPx) return;
        const requiredChatPx = Math.max(naturalPx, TOOLBAR_FLOOR_PX)
            + TOOLBAR_BUFFER_PX;
        // Round the percentage UP so the browser's % → px conversion
        // can never round down past the required width.
        const requiredChatPct = Math.ceil(
            (requiredChatPx / containerPx) * 10000
        ) / 100;
        const left = isCanvasOnLeft();
        const currentChatPct = left ? (100 - seamPct) : seamPct;
        const maxChatPct = 100 - (320 / containerPx) * 100;
        const allowedChatPct = Math.min(Math.max(currentChatPct, requiredChatPct), maxChatPct);
        if (Math.abs(currentChatPct - allowedChatPct) < 0.01) return;
        const newSeam = left ? (100 - allowedChatPct) : allowedChatPct;
        // Bypass apply()'s clamp on purpose; assign the seam directly.
        seamPct = newSeam;
        const canvasWidthPct = left ? newSeam : (100 - newSeam);
        const chatWidthPct = 100 - canvasWidthPct;
        canvas.style.width = canvasWidthPct + '%';
        chat.style.width = chatWidthPct + '%';
        divider.style.left = newSeam + '%';
        window.TlmSplitters.describe(divider, newSeam, left ? 100 - maxChatPct : 15, left ? 85 : maxChatPct,
            `Chat ${Math.round(chatWidthPct)}%, canvas ${Math.round(canvasWidthPct)}%`);
    };

    function resetHorizontalLayout() {
        userResized = false;
        canvas.style.width = '';
        chat.style.width = '';
        divider.style.left = '';
        const r = rect();
        const cr = canvas.getBoundingClientRect();
        const hr = chat.getBoundingClientRect();
        const left = isCanvasOnLeft();
        const seamX = left ? cr.right : hr.right;
        const pct = clamp(((seamX - r.left) / r.width) * 100, 0, 100);
        apply(pct || 66.6667);
        ensureToolbarFitsOneRow();
    }

    (function init() {
        resetHorizontalLayout();
        // Re-check after the next paint, when layout / styles have
        // fully settled (catches cases where the synchronous init
        // ran before the body's final width was known).
        requestAnimationFrame(() => {
            requestAnimationFrame(() => ensureToolbarFitsOneRow());
        });
        // Re-check once webfont (Nunito) finishes loading — its glyph
        // widths can be wider than the system fallback, which would
        // otherwise wrap the toolbar moments after init.
        if (document.fonts && document.fonts.ready &&
            typeof document.fonts.ready.then === 'function') {
            document.fonts.ready.then(() => ensureToolbarFitsOneRow());
        }
        // Last-resort fallback for environments where neither rAF
        // nor fonts.ready settles on the final widths (some embedded
        // browser frames).
        setTimeout(() => ensureToolbarFitsOneRow(), 500);
    })();

    const stopDrag = bindDividerPointerDrag(divider, 'resizing', event => {
        userResized = true;
        apply(pctFromXToSeam(event.clientX));
    });
    window.addEventListener('tlm:chat-layout-changing', stopDrag);
    window.addEventListener('tlm:reset-chat-layout', resetHorizontalLayout);

    // Same feel as the vertical divider and the ACP/Prompt Flow dividers:
    // arrows move 1%, Shift+arrows 5%.
    divider.addEventListener('keydown', (e) => {
        const step = e.shiftKey ? 5 : 1;
        if (e.key === 'ArrowLeft') { userResized = true; apply(seamPct - step); e.preventDefault(); }
        if (e.key === 'ArrowRight') { userResized = true; apply(seamPct + step); e.preventDefault(); }
        if (e.key === 'Home') { userResized = true; apply(isCanvasOnLeft() ? 30 : 15); e.preventDefault(); }
        if (e.key === 'End') { userResized = true; apply(isCanvasOnLeft() ? 85 : 70); e.preventDefault(); }
    });

    window.addEventListener('resize', () => {
        // Avatar sizing also emits resize. Preserve the automatic toolbar fit
        // until a real horizontal drag, instead of snapping it back to 70%.
        if (userResized) apply(seamPct);
        else ensureToolbarFitsOneRow();
    });
})();

// --- Vertical drag divider (chat-log <-> tools/form) ---
(function () {
    const subchatContainer = document.getElementById('subchat-container');
    const chatLogEl = document.getElementById('chat-log');
    const toolsContainer = document.getElementById('tools-chat-form-container');
    const verticalDivider = document.getElementById('vertical-drag-divider');

    if (!subchatContainer || !chatLogEl || !toolsContainer || !verticalDivider) return;

    // Keep the requested share separately from the fitted geometry. Docking,
    // wrapped tools and temporary status rows must not erase the user's choice.
    let dividerPct = 90;
    let actualPct = 90;
    let pendingLayout = false;
    let userResized = false;

    const clamp = (n, lo, hi) => Math.max(lo, Math.min(hi, n));
    const rect = () => subchatContainer.getBoundingClientRect();
    const MIN_LOG_PX = 80;
    const COMPOSER_GUARD_PX = 6;
    const DOCKED_AVATAR_MIN_PX = 120;
    const form = document.getElementById('chat-form');
    const actions = toolsContainer.querySelector('.chat-composer-actions');
    const input = document.getElementById('chat-message-input');
    const avatar = document.getElementById('tlm-avatar-dock');
    const isAvatarDocked = () => avatar && !avatar.classList.contains('tlm-floating')
        && avatar.getClientRects().length;
    const naturalAvatarSize = () => Math.max(DOCKED_AVATAR_MIN_PX, form.clientWidth * 0.25);
    const px = value => parseFloat(value) || 0;
    const verticalEdges = style => px(style.paddingTop) + px(style.paddingBottom)
        + px(style.borderTopWidth) + px(style.borderBottomWidth);
    const outerHeight = element => {
        if (!element || !element.getClientRects().length) return 0;
        const style = getComputedStyle(element);
        return element.getBoundingClientRect().height + px(style.marginTop) + px(style.marginBottom);
    };

    // Measure natural controls, never the stretched textarea or avatar height:
    // measuring those would feed the current panel size back into its minimum.
    const computeFormMinHeight = () => {
        const actionsHeight = outerHeight(actions) || 60;
        toolsContainer.style.setProperty('--tlm-composer-actions-height', actionsHeight + 'px');
        const inputStyle = input && getComputedStyle(input);
        const inputEdges = inputStyle ? verticalEdges(inputStyle) : 0;
        const inputMin = inputStyle ? Math.max(
            px(inputStyle.minHeight) + (inputStyle.boxSizing === 'border-box' ? 0 : inputEdges),
            (px(inputStyle.lineHeight) || px(inputStyle.fontSize) * 1.2) + inputEdges
        ) : 0;
        let formAreaPx = Math.max(actionsHeight, inputMin) + COMPOSER_GUARD_PX;
        let naturalFormAreaPx = formAreaPx;
        if (form && isAvatarDocked()) {
            const style = getComputedStyle(avatar);
            const insets = px(style.top) + px(style.bottom);
            // Only the legible minimum constrains a drag. Her current width
            // must never feed back into the composer's minimum height.
            naturalFormAreaPx = Math.max(formAreaPx, naturalAvatarSize() + insets);
            formAreaPx = Math.max(formAreaPx, DOCKED_AVATAR_MIN_PX + insets);
        }
        let formChrome = 0;
        if (form) {
            const style = getComputedStyle(form);
            formChrome = px(style.marginTop) + px(style.marginBottom) + verticalEdges(style);
            form.style.minHeight = Math.ceil(formAreaPx) + 'px';
        }
        const rowsHeight = ['tools-div', 'chat-image-chips', 'context-gauge-row', 'dictation-status']
            .reduce((sum, id) => sum + outerHeight(document.getElementById(id)), 0);
        const chrome = rowsHeight + formChrome + verticalEdges(getComputedStyle(toolsContainer));
        return { minimum: Math.ceil(chrome + formAreaPx), natural: Math.ceil(chrome + naturalFormAreaPx) };
    };

    const fitDockedAvatar = () => {
        if (!form || !isAvatarDocked()) return;
        const style = getComputedStyle(avatar);
        const formStyle = getComputedStyle(form);
        const formRect = form.getBoundingClientRect();
        const availableHeight = formRect.height
            - px(formStyle.borderTopWidth) - px(formStyle.borderBottomWidth)
            - px(style.top) - px(style.bottom);
        // Square, above the action row, at most the original quarter-width column. Both
        // pane dividers can now shrink her, without changing floating presets.
        const size = Math.max(DOCKED_AVATAR_MIN_PX, Math.floor(Math.min(naturalAvatarSize(), availableHeight)));
        form.style.setProperty('--tlm-avatar-docked-size', size + 'px');
        if (actions && actions.getClientRects().length) {
            // Center the whole frame over Mic through Send, including when the
            // action row reaches its minimum width in a narrow chat pane.
            const actionsRect = actions.getBoundingClientRect();
            const actionsCenter = actionsRect.left + actionsRect.width / 2;
            const right = formRect.right - px(formStyle.borderRightWidth) - actionsCenter - size / 2;
            form.style.setProperty('--tlm-avatar-docked-right', right + 'px');
        }
    };

    const pctFromYToDivider = (clientY) => {
        const r = rect();
        const y = clamp(clientY, r.top, r.bottom);
        return ((y - r.top) / r.height) * 100;
    };

    // pDivider = chat-log share (%). null → re-clamp using last value.
    const applyVertical = (pDivider) => {
        if (pDivider != null) {
            userResized = true;
            dividerPct = clamp(pDivider, 0, 100);
        }
        const total = subchatContainer.clientHeight;
        if (total <= 0) return;
        const dividerH = verticalDivider.offsetHeight || 8;
        const formSizes = computeFormMinHeight();
        const formMinPx = formSizes.minimum;
        const minLogPx = Math.min(MIN_LOG_PX, Math.max(0, total - dividerH));
        const maxLogPx = Math.max(minLogPx, total - dividerH - formMinPx);
        let logPx = (dividerPct / 100) * total;
        // Keep the familiar initial portrait until the user moves this bar.
        if (!userResized) logPx = Math.min(logPx, total - dividerH - formSizes.natural);
        logPx = clamp(logPx, minLogPx, maxLogPx);
        const formPx = total - dividerH - logPx;
        chatLogEl.style.height = logPx + 'px';
        toolsContainer.style.height = formPx + 'px';
        // Only an exceptionally short viewport needs scrolling; never clip its controls.
        toolsContainer.style.overflowY = formPx < formMinPx ? 'auto' : '';
        fitDockedAvatar();
        actualPct = logPx / total * 100;
        verticalDivider.setAttribute('aria-valuemin', String(Math.floor(minLogPx / total * 100)));
        verticalDivider.setAttribute('aria-valuemax', String(Math.ceil(maxLogPx / total * 100)));
        verticalDivider.setAttribute('aria-valuenow', String(Math.round(actualPct)));
        verticalDivider.setAttribute('aria-valuetext', 'Message composer ' + Math.round(formPx) + ' pixels high');
    };

    const scheduleLayout = () => {
        if (pendingLayout) return;
        pendingLayout = true;
        requestAnimationFrame(() => { pendingLayout = false; applyVertical(null); });
    };

    (function initVertical() {
        applyVertical(null);
    })();

    // Re-clamp whenever the toolbar's height changes (it grows when the user
    // drags the horizontal divider narrow enough for the toggles to wrap onto
    // a second / third row) — and whenever the pasted-image chips row appears
    // or disappears, for exactly the same reason.
    if (typeof ResizeObserver !== 'undefined') {
        const ro = new ResizeObserver(scheduleLayout);
        ['subchat-container', 'tools-div', 'chat-image-chips', 'context-gauge-row', 'dictation-status', 'chat-form'].forEach((id) => {
            const el = document.getElementById(id);
            if (el) ro.observe(el);
        });
        if (actions) ro.observe(actions);
        if (avatar) ro.observe(avatar);
    }
    if (avatar && typeof MutationObserver !== 'undefined') {
        new MutationObserver(scheduleLayout).observe(avatar, { attributes: true, attributeFilter: ['class'] });
    }

    const stopDrag = bindDividerPointerDrag(verticalDivider, 'resizing-vertical', event => applyVertical(pctFromYToDivider(event.clientY)));
    window.addEventListener('tlm:chat-layout-changing', stopDrag);
    window.addEventListener('tlm:reset-chat-layout', () => {
        dividerPct = 90;
        userResized = false;
        applyVertical(null);
    });

    verticalDivider.addEventListener('keydown', (e) => {
        const step = e.shiftKey ? 5 : 1;
        if (e.key === 'ArrowUp') applyVertical(actualPct - step);
        else if (e.key === 'ArrowDown') applyVertical(actualPct + step);
        else if (e.key === 'Home') applyVertical(100);
        else if (e.key === 'End') applyVertical(0);
        else return;
        e.preventDefault();
    });
    verticalDivider.addEventListener('dblclick', () => applyVertical(100));
    window.addEventListener('resize', scheduleLayout);
    if (document.fonts && document.fonts.ready) document.fonts.ready.then(scheduleLayout);
})();

// --- Views: presentation only; never unload the canvas or change chat context. ---
(function () {
    'use strict';
    const toggle = document.getElementById('views-canvas-toggle');
    const reset = document.getElementById('views-reset-layout');
    const menu = document.getElementById('views-menu-button');
    const canvas = document.getElementById('canvas-container');
    const divider = document.getElementById('drag-divider');
    if (!toggle || !reset || !menu || !canvas || !divider) return;

    // Account-scoped, browser-local preference. Bad/missing storage defaults ON.
    const key = 'tlamatini.chat.views.v1.' + document.body.dataset.layoutUser;
    let visible = true;
    try { visible = localStorage.getItem(key) !== 'hidden'; } catch (_) { /* private mode */ }

    function syncMenu() {
        toggle.setAttribute('aria-checked', String(visible));
    }

    function setCanvasVisible(show, persist = true) {
        visible = Boolean(show);
        window.dispatchEvent(new Event('tlm:chat-layout-changing'));
        // Move keyboard focus out before its element disappears. Do not steal
        // focus from the composer or from a generated-file link.
        const focused = document.activeElement;
        if (!visible && (canvas.contains(focused) || focused === divider)) {
            menu.focus({ preventScroll: true });
        }
        document.body.classList.toggle('tlm-canvas-hidden', !visible);
        window.TlamatiniAvatarSize?.setDockedOnly(!visible);
        syncMenu();
        if (persist) {
            try { localStorage.setItem(key, visible ? 'visible' : 'hidden'); } catch (_) { /* current tab still works */ }
        }
        // Existing layout adapters and the embedded viewer retain their own state.
        window.dispatchEvent(new Event('resize'));
        return visible;
    }

    function resetLayout() {
        setCanvasVisible(true);
        window.TlamatiniAvatarSize?.set(0);
        window.dispatchEvent(new Event('tlm:reset-chat-layout'));
        window.dispatchEvent(new Event('resize'));
    }

    toggle.addEventListener('click', () => setCanvasVisible(!visible));
    reset.addEventListener('click', resetLayout);
    menu.addEventListener('show.bs.dropdown', syncMenu);
    window.addEventListener('storage', event => {
        if (event.key === key || event.key === null) {
            setCanvasVisible(event.newValue !== 'hidden', false);
        }
    });
    window.TlamatiniViews = Object.freeze({
        setCanvasVisible,
        isCanvasVisible: () => visible, setTerminalsVisible: show => window.TlamatiniTerminals?.setVisible(show), isTerminalsVisible: () => Boolean(window.TlamatiniTerminals?.isVisible()),
        resetLayout,
    });

    // Avatar initialization is registered later in the template. Apply after
    // all DOMContentLoaded listeners so a saved floating portrait is docked too.
    const init = () => setTimeout(() => setCanvasVisible(visible, false), 0);
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init, { once: true });
    else init();
})();

// --- Title rotation ---
function rotateTitle() {
    const baseTitle = " Tlamatini";
    let charIndex = 0;

    const rotate = () => {
        document.title = titleBusyPrefix + (baseTitle.slice(charIndex) + baseTitle.slice(0, charIndex));
        charIndex = (charIndex + 1) % baseTitle.length;
    };
    setInterval(rotate, 100);
}
