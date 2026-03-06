// Agentic Control Panel - Layout, Divider, Agent List, Canvas Initialization
// LOAD ORDER: #10 - Depends on: ALL previous acp-*.js files

// ========================================
// TITLE ROTATION
// ========================================

function rotateTitle() {
    const baseTitle = " Tlamatini (Agentic Control Panel)";
    let charIndex = 0;

    const rotate = () => {
        document.title = titleBusyPrefix + (baseTitle.slice(charIndex) + baseTitle.slice(0, charIndex));
        charIndex = (charIndex + 1) % baseTitle.length;
    };
    setInterval(rotate, 100);
}

// ========================================
// DIVIDER / PANEL RESIZE LOGIC
// ========================================

(function initLayout() {
    rotateTitle();

    if (!container || !canvas || !chat || !divider) return;

    let isDragging = false;
    let seamPct;

    const clamp = (n, lo, hi) => Math.max(lo, Math.min(hi, n));
    const getContainerRect = () => container.getBoundingClientRect();

    const isCanvasOnLeft = () => {
        const cr = canvas.getBoundingClientRect();
        const hr = chat.getBoundingClientRect();
        return (cr.left + cr.width / 2) < (hr.left + hr.width / 2);
    };

    const pctFromXToSeam = (clientX) => {
        const r = getContainerRect();
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

    // Initial layout calculation
    (function init() {
        const r = getContainerRect();
        const cr = canvas.getBoundingClientRect();
        const hr = chat.getBoundingClientRect();
        const left = isCanvasOnLeft();
        const seamX = left ? cr.right : hr.right;
        const pct = clamp(((seamX - r.left) / r.width) * 100, 0, 100);
        apply(pct || 66.6667);
        updateSaveButtonState();
    })();

    // Mouse drag
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

    // Touch drag
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

    // Keyboard nudge
    divider.addEventListener('keydown', (e) => {
        if (e.key === 'ArrowLeft') { apply(seamPct - 1); e.preventDefault(); }
        if (e.key === 'ArrowRight') { apply(seamPct + 1); e.preventDefault(); }
    });

    window.addEventListener('resize', () => apply(seamPct));

    // ========================================
    // AGENTS LIST & CANVAS INITIALIZATION
    // ========================================

    // Populate the agents list in the sidebar
    populateAgentsList();

    // Initialize all canvas event listeners
    initCanvasEvents();

})();
