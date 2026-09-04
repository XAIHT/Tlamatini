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

// Prompt Designer - Prompt Canvas surface (right column)
// LOAD ORDER: #5 - Depends on: prompt-designer-globals.js

/* global pdSubCanvas, pdCanvasContent, pdSprintNotice */

// ========================================
// CANVAS SURFACE
// ========================================
//
// The Designer's canvas obeys the SAME two-layer DOM contract the Agentic
// Control Panel does: #subpromptcanvas-container is the scrolling VIEWPORT
// and #prompt-canvas-content is the coordinate frame every block will be
// positioned in. Later sprints must measure against the CONTENT layer — its
// rect already carries the scroll offset — never against the viewport.

/**
 * Keep the content layer at least as large as the blocks it holds, so the
 * viewport grows scrollbars instead of clipping. Called on load and on every
 * resize; a later sprint calls it after every drop, drag and undo.
 */
function updatePromptCanvasContentSize() {
    if (!pdCanvasContent || !pdSubCanvas) return;

    let maxRight = pdSubCanvas.clientWidth;
    let maxBottom = pdSubCanvas.clientHeight;

    pdCanvasContent.querySelectorAll('.prompt-canvas-item').forEach((item) => {
        maxRight = Math.max(maxRight, item.offsetLeft + item.offsetWidth + 40);
        maxBottom = Math.max(maxBottom, item.offsetTop + item.offsetHeight + 40);
    });

    pdCanvasContent.style.width = `${maxRight}px`;
    pdCanvasContent.style.height = `${maxBottom}px`;
}

function initPromptDesignerCanvas() {              // eslint-disable-line no-unused-vars
    if (!pdSubCanvas) return;

    // A press on the empty canvas — where a prompt block will one day be
    // dropped — answers rather than doing nothing at all.
    pdSubCanvas.addEventListener('click', (event) => {
        pdSprintNotice('Prompt Canvas', event);
    });

    // Right-click would open the block context menu.
    pdSubCanvas.addEventListener('contextmenu', (event) => {
        pdSprintNotice('Prompt Canvas ▸ context menu', event);
    });

    // Dropping an asset onto the canvas is the Designer's core gesture.
    pdSubCanvas.addEventListener('dragover', (event) => {
        event.preventDefault();
    });
    pdSubCanvas.addEventListener('drop', (event) => {
        pdSprintNotice('Prompt Canvas ▸ drop', event);
    });

    window.addEventListener('resize', updatePromptCanvasContentSize);
    updatePromptCanvasContentSize();

    console.log('--- [PROMPT-DESIGNER] Prompt Canvas wired');
}
