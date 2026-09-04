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

// Prompt Designer - Layout, Divider, Boot
// LOAD ORDER: #6 (LAST) - Depends on: ALL previous prompt-designer-*.js files

/* global pdContainer, pdAssetsPanel, pdCanvasPanel, pdDivider,
          initPromptDesignerMenu, initPromptDesignerControls,
          initPromptDesignerAssets, initPromptDesignerCanvas */

// ========================================
// TITLE ROTATION
// ========================================

// Hourglass prefix, kept for parity with the Agentic Control Panel: a later
// sprint sets it while a prompt run is in flight.
let pdTitleBusyPrefix = "";                        // eslint-disable-line prefer-const

function rotatePromptDesignerTitle() {
    const baseTitle = " Tlamatini (Prompt Designer)";
    let charIndex = 0;

    const rotate = () => {
        document.title = pdTitleBusyPrefix + (baseTitle.slice(charIndex) + baseTitle.slice(0, charIndex));
        charIndex = (charIndex + 1) % baseTitle.length;
    };
    setInterval(rotate, 100);
}

// ========================================
// DIVIDER / PANEL RESIZE LOGIC
// ========================================

(function initPromptDesignerLayout() {
    rotatePromptDesignerTitle();

    if (!pdContainer || !pdCanvasPanel || !pdAssetsPanel || !pdDivider) return;

    let isDragging = false;
    let seamPct;

    const clamp = (n, lo, hi) => Math.max(lo, Math.min(hi, n));
    const getContainerRect = () => pdContainer.getBoundingClientRect();

    const pctFromXToSeam = (clientX) => {
        const r = getContainerRect();
        const x = clamp(clientX, r.left, r.right);
        return ((x - r.left) / r.width) * 100;
    };

    // The Assets panel is always on the LEFT of the seam and the Prompt
    // Canvas always on the right, so the seam percentage IS the assets width.
    const apply = (pSeam) => {
        seamPct = clamp(pSeam, 15, 70);
        pdAssetsPanel.style.width = seamPct + '%';
        pdCanvasPanel.style.width = (100 - seamPct) + '%';
        pdDivider.style.left = seamPct + '%';
    };

    // Initial layout calculation
    (function init() {
        const r = getContainerRect();
        const ar = pdAssetsPanel.getBoundingClientRect();
        const pct = clamp(((ar.right - r.left) / r.width) * 100, 0, 100);
        apply(pct || 25);
    })();

    // Mouse drag
    pdDivider.addEventListener('mousedown', (e) => {
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
    pdDivider.addEventListener('touchstart', () => {
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
    pdDivider.addEventListener('keydown', (e) => {
        if (e.key === 'ArrowLeft') { apply(seamPct - 1); e.preventDefault(); }
        if (e.key === 'ArrowRight') { apply(seamPct + 1); e.preventDefault(); }
    });

    window.addEventListener('resize', () => apply(seamPct));

    // ========================================
    // BOOT
    // ========================================

    initPromptDesignerMenu();
    initPromptDesignerControls();
    initPromptDesignerAssets();
    initPromptDesignerCanvas();

    console.log('--- [PROMPT-DESIGNER] Ready');

})();
