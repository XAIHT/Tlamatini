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

// ============================================================
// agent_page_layout.js  –  Drag dividers, resize & title rotation
// ============================================================

// --- Horizontal drag divider (chat <-> canvas) ---
(function () {
    const container = document.getElementById('chat-container');
    const canvas = document.getElementById('canvas-container');
    const chat = document.getElementById('main-chat-container');
    const divider = document.getElementById('drag-divider');
    if (!container || !canvas || !chat || !divider) return;

    let isDragging = false;
    let seamPct;

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
        const left = isCanvasOnLeft();
        const minSeam = left ? 30 : 15;
        const maxSeam = left ? 85 : 70;
        seamPct = clamp(pSeam, minSeam, maxSeam);
        const canvasWidth = left ? seamPct : (100 - seamPct);
        const chatWidth = 100 - canvasWidth;
        canvas.style.width = canvasWidth + '%';
        chat.style.width = chatWidth + '%';
        divider.style.left = seamPct + '%';
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
    // We deliberately bypass apply()'s ergonomic clamp ([15..70] for
    // the chat panel) here: when the browser window is narrow enough
    // that 70% can't fit the toolbar, we allow up to 92% (leaving an
    // 8% sliver for the canvas so the user can still grab the
    // divider). Once the user drags the divider manually, apply()'s
    // standard clamp re-engages.
    const ensureToolbarFitsOneRow = () => {
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
        if (currentChatPct >= requiredChatPct) return;
        const allowedChatPct = Math.min(requiredChatPct, 92);
        const newSeam = left ? (100 - allowedChatPct) : allowedChatPct;
        // Bypass apply()'s clamp on purpose; assign the seam directly.
        seamPct = newSeam;
        const canvasWidthPct = left ? newSeam : (100 - newSeam);
        const chatWidthPct = 100 - canvasWidthPct;
        canvas.style.width = canvasWidthPct + '%';
        chat.style.width = chatWidthPct + '%';
        divider.style.left = newSeam + '%';
    };

    (function init() {
        const r = rect();
        const cr = canvas.getBoundingClientRect();
        const hr = chat.getBoundingClientRect();
        const left = isCanvasOnLeft();
        const seamX = left ? cr.right : hr.right;
        const pct = clamp(((seamX - r.left) / r.width) * 100, 0, 100);
        apply(pct || 66.6667);
        ensureToolbarFitsOneRow();
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

    divider.addEventListener('mousedown', (e) => {
        isDragging = true;
        document.body.classList.add('resizing');
        e.preventDefault();
    });
    window.addEventListener('mousemove', (e) => {
        if (!isDragging) return;
        apply(pctFromXToSeam(e.clientX));
    });
    window.addEventListener('mouseup', () => {
        if (!isDragging) return;
        isDragging = false;
        document.body.classList.remove('resizing');
    });

    divider.addEventListener('touchstart', () => {
        isDragging = true;
        document.body.classList.add('resizing');
    }, { passive: true });
    window.addEventListener('touchmove', (e) => {
        if (!isDragging) return;
        const t = e.touches && e.touches[0];
        if (t) apply(pctFromXToSeam(t.clientX));
    }, { passive: true });
    window.addEventListener('touchend', () => {
        if (!isDragging) return;
        isDragging = false;
        document.body.classList.remove('resizing');
    });

    divider.addEventListener('keydown', (e) => {
        if (e.key === 'ArrowLeft') { apply(seamPct - 1); e.preventDefault(); }
        if (e.key === 'ArrowRight') { apply(seamPct + 1); e.preventDefault(); }
    });

    window.addEventListener('resize', () => apply(seamPct));
})();

// --- Vertical drag divider (chat-log <-> tools/form) ---
(function () {
    const subchatContainer = document.getElementById('subchat-container');
    const chatLogEl = document.getElementById('chat-log');
    const toolsContainer = document.getElementById('tools-chat-form-container');
    const verticalDivider = document.getElementById('vertical-drag-divider');

    if (!subchatContainer || !chatLogEl || !toolsContainer || !verticalDivider) return;

    let isDraggingVertical = false;
    let dividerPct = 90; // last user-requested chat-log share, in percent

    const clamp = (n, lo, hi) => Math.max(lo, Math.min(hi, n));
    const rect = () => subchatContainer.getBoundingClientRect();
    const MIN_LOG_PX = 80;
    const FALLBACK_FORM_FLOOR_PX = 115;

    // The form-container needs enough vertical room for: the toolbar
    // (which wraps to 2 or 3 rows on narrow chat panels), the pasted-image
    // thumbnail chips row (chat_image_paste.js — zero height until a
    // screenshot is pasted or dropped), plus the textarea area + the Send
    // button (min-height 60) + form margins (~10px). This container is given
    // an EXPLICIT pixel height below, so anything added inside it must be
    // counted here or the textarea/Send get pushed off the bottom of the
    // viewport.
    const computeFormMinHeight = () => {
        const toolsDivEl = document.getElementById('tools-div');
        const toolsDivH = (toolsDivEl ? toolsDivEl.offsetHeight : 25) || 25;
        const chipsEl = document.getElementById('chat-image-chips');
        const chipsH = chipsEl ? chipsEl.offsetHeight : 0;
        const formAreaPx = 90; // textarea + Send min-heights + form margins
        return Math.max(FALLBACK_FORM_FLOOR_PX, toolsDivH + chipsH + formAreaPx);
    };

    const pctFromYToDivider = (clientY) => {
        const r = rect();
        const y = clamp(clientY, r.top, r.bottom);
        return ((y - r.top) / r.height) * 100;
    };

    // pDivider = chat-log share (%). null → re-clamp using last value.
    const applyVertical = (pDivider) => {
        if (pDivider != null) {
            dividerPct = clamp(pDivider, 5, 95);
        }
        const total = subchatContainer.clientHeight;
        if (total <= 0) return;
        const dividerH = verticalDivider.offsetHeight || 8;
        const formMinPx = computeFormMinHeight();
        const maxLogPx = Math.max(MIN_LOG_PX, total - dividerH - formMinPx);
        let logPx = (dividerPct / 100) * total;
        logPx = clamp(logPx, MIN_LOG_PX, maxLogPx);
        const formPx = total - dividerH - logPx;
        chatLogEl.style.height = logPx + 'px';
        toolsContainer.style.height = formPx + 'px';
    };

    (function initVertical() {
        applyVertical(90);
    })();

    // Re-clamp whenever the toolbar's height changes (it grows when the user
    // drags the horizontal divider narrow enough for the toggles to wrap onto
    // a second / third row) — and whenever the pasted-image chips row appears
    // or disappears, for exactly the same reason.
    if (typeof ResizeObserver !== 'undefined') {
        const ro = new ResizeObserver(() => applyVertical(null));
        ['tools-div', 'chat-image-chips'].forEach((id) => {
            const el = document.getElementById(id);
            if (el) ro.observe(el);
        });
    }

    verticalDivider.addEventListener('mousedown', (e) => {
        isDraggingVertical = true;
        document.body.classList.add('resizing-vertical');
        e.preventDefault();
    });

    window.addEventListener('mousemove', (e) => {
        if (!isDraggingVertical) return;
        applyVertical(pctFromYToDivider(e.clientY));
    });

    window.addEventListener('mouseup', () => {
        if (!isDraggingVertical) return;
        isDraggingVertical = false;
        document.body.classList.remove('resizing-vertical');
    });

    verticalDivider.addEventListener('touchstart', () => {
        isDraggingVertical = true;
        document.body.classList.add('resizing-vertical');
    }, { passive: true });

    window.addEventListener('touchmove', (e) => {
        if (!isDraggingVertical) return;
        const t = e.touches && e.touches[0];
        if (t) applyVertical(pctFromYToDivider(t.clientY));
    }, { passive: true });

    window.addEventListener('touchend', () => {
        if (!isDraggingVertical) return;
        isDraggingVertical = false;
        document.body.classList.remove('resizing-vertical');
    });

    verticalDivider.addEventListener('keydown', (e) => {
        if (e.key === 'ArrowUp') {
            applyVertical(dividerPct - 1);
            e.preventDefault();
        }
        if (e.key === 'ArrowDown') {
            applyVertical(dividerPct + 1);
            e.preventDefault();
        }
    });

    window.addEventListener('resize', () => applyVertical(null));
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
