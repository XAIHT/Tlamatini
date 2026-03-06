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

    (function init() {
        const r = rect();
        const cr = canvas.getBoundingClientRect();
        const hr = chat.getBoundingClientRect();
        const left = isCanvasOnLeft();
        const seamX = left ? cr.right : hr.right;
        const pct = clamp(((seamX - r.left) / r.width) * 100, 0, 100);
        apply(pct || 66.6667);
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
    let dividerPct;

    const clamp = (n, lo, hi) => Math.max(lo, Math.min(hi, n));
    const rect = () => subchatContainer.getBoundingClientRect();

    const pctFromYToDivider = (clientY) => {
        const r = rect();
        const y = clamp(clientY, r.top, r.bottom);
        return ((y - r.top) / r.height) * 100;
    };

    const applyVertical = (pDivider) => {
        const minDivider = 20;
        const maxDivider = 90;
        dividerPct = clamp(pDivider, minDivider, maxDivider);
        const chatLogHeight = dividerPct;
        const toolsHeight = 100 - dividerPct;
        chatLogEl.style.height = chatLogHeight + '%';
        toolsContainer.style.height = toolsHeight + '%';
    };

    (function initVertical() {
        applyVertical(90);
    })();

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

    window.addEventListener('resize', () => applyVertical(dividerPct));
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
